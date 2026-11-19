"""The Reviews screen (decision 0109): managers add, edit, reorder, show or
hide and delete the reviews the website shows, and every saved change asks
for a website rebuild. Every name and review here is invented."""

import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from marketing.models import Review
from staff.models import PayType, StaffMember

from .fixtures import TailnetClient

HOOK = "https://api.cloudflare.example/pages/webhooks/deploy_hooks/made-up-hook-id"


def review(name, position, **fields):
    return Review.objects.create(name=name, text=f"Invented review by {name}.", reviewed_on=datetime.date(2026, 11, 1), position=position, **fields)


@override_settings(CLOUDFLARE_PAGES_DEPLOY_HOOK=HOOK)
class ReviewsScreenTests(TestCase):
    client_class = TailnetClient

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner_user = User.objects.create_user("owner", password="an-invented-password-1")
        cls.helper_user = User.objects.create_user("helper", password="an-invented-password-1")
        StaffMember.objects.create(name="Owner Person", role=StaffMember.Role.OWNER, user=cls.owner_user)
        StaffMember.objects.create(name="Helper One", role=StaffMember.Role.HELPER, pay_type=PayType.FAMILY_HELPER, user=cls.helper_user)

    def setUp(self):
        self.client.force_login(self.owner_user)

    def rebuilds(self, call):
        """Run call, committing, and return how many rebuilds it asked for."""
        fake = mock.MagicMock(status=200)
        fake.__enter__.return_value = fake
        with mock.patch("urllib.request.urlopen", return_value=fake) as urlopen, self.captureOnCommitCallbacks(execute=True):
            response = call()
        for each in urlopen.call_args_list:
            self.assertEqual((each.args[0].full_url, each.args[0].get_method()), (HOOK, "POST"))
        return response, len(urlopen.call_args_list)

    def test_only_managers_see_or_change_reviews(self):
        one = review("Pat Q.", 0)
        self.client.force_login(self.helper_user)
        for name, args in [("site-reviews", []), ("site-review-new", []), ("site-review", [one.pk]), ("site-review-delete", [one.pk])]:
            self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 403, name)
        for name in ["site-review-move", "site-review-shown", "site-review-delete"]:
            self.assertEqual(self.client.post(reverse(name, args=[one.pk])).status_code, 403, name)
        self.assertNotContains(self.client.get(reverse("account")), reverse("site-reviews"))
        self.client.force_login(self.owner_user)
        self.assertContains(self.client.get(reverse("account")), reverse("site-reviews"))

    def test_adding_a_review_saves_it_last_and_asks_for_a_rebuild(self):
        review("Pat Q.", 0)
        page = self.client.get(reverse("site-review-new"))
        self.assertContains(page, "First name and last initial, as on Google.")
        data = {"name": "  Lee   Z. ", "text": " Invented text. ", "reviewed_on": "2026-11-12", "stars": "5", "google_url": "https://g.co/kgs/example", "shown": "on"}
        response, asked = self.rebuilds(lambda: self.client.post(reverse("site-review-new"), data))
        self.assertRedirects(response, reverse("site-reviews"))
        self.assertEqual(asked, 1)
        added = Review.objects.get(name="Lee Z.")
        self.assertEqual((added.text, added.stars, added.position, added.shown), ("Invented text.", 5, 1, True))
        self.assertEqual(added.history.count(), 1)

    def test_the_rating_and_link_are_optional_and_a_link_must_be_https(self):
        data = {"name": "Sam R.", "text": "Invented.", "reviewed_on": "2026-11-12", "stars": "", "google_url": "", "shown": "on"}
        _, asked = self.rebuilds(lambda: self.client.post(reverse("site-review-new"), data))
        self.assertEqual(asked, 1)
        self.assertIsNone(Review.objects.get().stars)
        response, asked = self.rebuilds(lambda: self.client.post(reverse("site-review-new"), {**data, "google_url": "http://example.com/review"}))
        self.assertEqual(asked, 0)
        self.assertContains(response, "Give the link that starts with https://.")

    def test_editing_a_review(self):
        one = review("Pat Q.", 0)
        data = {"name": "Pat Q.", "text": "Changed.", "reviewed_on": "2026-11-01", "stars": "4", "google_url": "", "shown": "on"}
        _, asked = self.rebuilds(lambda: self.client.post(reverse("site-review", args=[one.pk]), data))
        one.refresh_from_db()
        self.assertEqual((one.text, one.stars, asked), ("Changed.", 4, 1))

    def test_moving_a_review_up_or_down(self):
        first, second, third = review("A. One", 0), review("B. Two", 1), review("C. Three", 2)
        _, asked = self.rebuilds(lambda: self.client.post(reverse("site-review-move", args=[third.pk]), {"direction": "up"}))
        self.assertEqual(list(Review.objects.values_list("name", flat=True)), ["A. One", "C. Three", "B. Two"])
        self.assertEqual(asked, 1)
        self.rebuilds(lambda: self.client.post(reverse("site-review-move", args=[first.pk]), {"direction": "down"}))
        self.assertEqual(list(Review.objects.values_list("name", flat=True)), ["C. Three", "A. One", "B. Two"])
        # Past either end, nothing moves and nothing is rebuilt.
        _, asked = self.rebuilds(lambda: self.client.post(reverse("site-review-move", args=[second.pk]), {"direction": "down"}))
        self.assertEqual(asked, 0)

    def test_hiding_and_showing_a_review(self):
        one = review("Pat Q.", 0)
        _, asked = self.rebuilds(lambda: self.client.post(reverse("site-review-shown", args=[one.pk]), {}))
        one.refresh_from_db()
        self.assertEqual((one.shown, asked), (False, 1))
        self.assertContains(self.client.get(reverse("site-reviews")), "Hidden")
        self.rebuilds(lambda: self.client.post(reverse("site-review-shown", args=[one.pk]), {"shown": "on"}))
        one.refresh_from_db()
        self.assertTrue(one.shown)

    def test_deleting_a_review_asks_first(self):
        one, two = review("Pat Q.", 0), review("Lee Z.", 1)
        self.assertContains(self.client.get(reverse("site-review-delete", args=[one.pk])), "Delete for good")
        self.assertTrue(Review.objects.filter(pk=one.pk).exists())
        _, asked = self.rebuilds(lambda: self.client.post(reverse("site-review-delete", args=[one.pk])))
        self.assertFalse(Review.objects.filter(pk=one.pk).exists())
        two.refresh_from_db()
        self.assertEqual((two.position, asked), (0, 1))

    def test_a_failed_rebuild_never_stops_a_save(self):
        data = {"name": "Sam R.", "text": "Invented.", "reviewed_on": "2026-11-12", "stars": "", "google_url": "", "shown": "on"}
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")), self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("site-review-new"), data)
        self.assertTrue(Review.objects.filter(name="Sam R.").exists())
