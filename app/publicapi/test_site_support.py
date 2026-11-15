"""What the website (Phase 3, Step 6) needs from the server: the price table
it bakes in for the offline form, offline requests with a typed address or
a photo card, offline quote requests, and the rebuild when a pricebook
version is published or takes effect."""

import datetime
import io
import uuid
from decimal import Decimal
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import override_settings
from django.utils import timezone

from pricebook.models import PricebookVersion
from pricebook.pricing import price_job
from pricebook.publishing import publish
from pricebook.site_rebuild import due_today, request_rebuild
from publicapi.models import QuoteRequest, TimeRequest

from .test_quote_requests import signed
from .testing import BASE, CLEVELAND, CONSENTS, ApiTestCase, PublicClient, eastern, open_day

HOOK = "https://api.cloudflare.example/pages/webhooks/deploy_hooks/made-up-hook-id"


class PriceTableTests(ApiTestCase):
    def table(self):
        response = self.client.get_api("price-table")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def find(self, jobs, **match):
        return [job for job in jobs if all(job[key] == value for key, value in match.items())]

    def test_every_total_comes_from_the_pricing_engine(self):
        table = self.table()
        self.assertEqual(table["pricebook_version"], PricebookVersion.current().number)
        [job] = self.find(table["jobs"], class_id=self.medium.pk, size=2, service=self.full_detail.pk, condition=2, add_ons=[self.seats.pk])
        expected = price_job(self.full_detail, self.medium, self.medium.size_variants.get(value=2), condition_level=2, add_ons=[self.seats])
        self.assertEqual(job["total_before_tax"], f"{expected.total_before_tax:.2f}")
        self.assertEqual(job["time_on_site_minutes"], expected.time_on_site.total_minutes)
        self.assertEqual(job["total_before_tax"], "355.00")

    def test_only_what_can_be_booked_online(self):
        jobs = self.table()["jobs"]
        # No class booked by quote, no Level 3, no level for a service without one.
        self.assertFalse(self.find(jobs, class_id=self.vans.pk))
        self.assertFalse(self.find(jobs, condition=3))
        self.assertTrue(all(job["condition"] is None for job in self.find(jobs, service=self.exterior.pk)))
        # A motorcycle has Motorcycle Detail alone, with no add-on.
        bikes = self.find(jobs, class_id=self.motorcycles.pk)
        self.assertEqual([(job["service"], job["add_ons"]) for job in bikes], [(self.motorcycle_detail.pk, [])])
        self.assertFalse(self.find(jobs, service=self.monthly.pk))


class OfflineTimeRequestTests(ApiTestCase):
    def body(self, **changes):
        body = {
            "request_id": str(uuid.uuid4()),
            "submitted_at": eastern(open_day(-1), 21).isoformat(),
            "vehicle": {"photo_card": self.medium.pk, "year": 2018, "make": "Subaru", "model": "Outback"},
            "size": 2,
            "condition": 2,
            "service": self.full_detail.pk,
            "add_ons": [self.seats.pk],
            "address": "100 Example St NW, Cleveland, TN 37311",
            "first_name": "Avery",
            "mobile": "4235550123",
            "payment_method": "card",
            "consents": dict(CONSENTS),
            "shown": {"total": "355.00", "pricebook_version": 1},
        }
        body.update(changes)
        return {key: value for key, value in body.items() if value is not None}

    def send(self, body, expect=201):
        raw, headers = signed(body)
        response = PublicClient(origin=None, visitor="104.16.0.1").post(f"{BASE}time-requests", raw, content_type="application/json", headers=headers)
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def test_a_typed_address_is_kept_unchecked_and_the_job_still_priced(self):
        self.send(self.body())
        request = TimeRequest.objects.get()
        self.assertIsNone(request.service_address)
        self.assertIn("not checked: 100 Example St NW, Cleveland, TN 37311", request.problem)
        self.assertEqual(request.inputs["address"], "100 Example St NW, Cleveland, TN 37311")
        # Priced without tax, from the photo card the customer picked.
        self.assertEqual(request.quote.total_before_tax, Decimal("355.00"))
        self.assertEqual(request.quote.sales_tax, Decimal("0.00"))
        self.assertFalse(request.price_differs)
        self.assertIn("2018 Subaru Outback", request.inputs["vehicle_text"])

    def test_a_place_id_or_an_address_but_not_both(self):
        self.assertEqual(self.send(self.body(place_id=CLEVELAND), expect=400)["field"], "place_id")
        self.assertEqual(self.send(self.body(address=None), expect=400)["field"], "place_id")
        self.send(self.body(address=None, place_id=CLEVELAND))
        self.assertIsNotNone(TimeRequest.objects.get().service_address)


class OfflineQuoteRequestTests(ApiTestCase):
    def body(self, **changes):
        body = {
            "request_id": str(uuid.uuid4()),
            "submitted_at": eastern(open_day(-1), 21).isoformat(),
            "vehicle": {"year": 2021, "make": "Ford", "model": "Transit 250"},
            "service": self.full_detail.pk,
            "description": "Work van, very dirty inside.",
            "place_id": CLEVELAND,
            "first_name": "Morgan",
            "mobile": "4235550160",
            "consents": dict(CONSENTS),
        }
        body.update(changes)
        return {key: value for key, value in body.items() if value is not None}

    def send(self, body, expect=201, **sign):
        raw, headers = signed(body, **sign)
        response = PublicClient(origin=None, visitor="104.16.0.1").post(
            f"{BASE}quote-requests/offline", raw, content_type="application/json", headers=headers,
        )
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def test_a_van_request_is_kept_without_photos(self):
        answer = self.send(self.body(preferred_days="Mornings"))
        request = QuoteRequest.objects.get(reference=answer["reference"])
        self.assertEqual((request.vehicle_class, request.service, request.problem), (self.vans, self.full_detail, ""))
        self.assertIsNotNone(request.service_address)
        self.assertFalse(request.photos.exists())
        self.assertEqual(request.preferred_days, "Mornings")

    def test_a_level_3_request_carries_its_service_level_and_add_ons(self):
        answer = self.send(self.body(vehicle={"year": 2019, "make": "Toyota", "model": "RAV4"}, condition=3, add_ons=[self.seats.pk]))
        request = QuoteRequest.objects.get(reference=answer["reference"])
        self.assertEqual((request.service, request.condition_level, list(request.add_ons.all())), (self.full_detail, 3, [self.seats]))

    def test_nothing_is_lost(self):
        # A typed address, and a job the site would book online: both kept, with the problems noted.
        answer = self.send(self.body(vehicle={"year": 2019, "make": "Toyota", "model": "RAV4"}, place_id=None, address="12 Example Rd, Athens, TN"))
        request = QuoteRequest.objects.get(reference=answer["reference"])
        self.assertIsNone(request.service_address)
        self.assertEqual(request.address_text, "12 Example Rd, Athens, TN")
        self.assertIn("can be booked online", request.problem)
        self.assertIn("not checked", request.problem)

    def test_signed_only_and_a_second_replay_changes_nothing(self):
        body = self.body()
        self.send(body, expect=401, key="a-wrong-key")
        self.send(body)
        self.assertEqual(self.send(body, expect=200), {"received": True, "duplicate": True})
        self.assertEqual(QuoteRequest.objects.count(), 1)


@override_settings(CLOUDFLARE_PAGES_DEPLOY_HOOK=HOOK)
class RebuildTests(ApiTestCase):
    def response(self, status=200):
        fake = mock.MagicMock(status=status)
        fake.__enter__.return_value = fake
        return fake

    def test_publishing_asks_for_a_rebuild_once_it_commits(self):
        draft = PricebookVersion.new_draft()
        with mock.patch("urllib.request.urlopen", return_value=self.response()) as urlopen:
            with self.captureOnCommitCallbacks(execute=True):
                publish(draft, timezone.localdate(), {})
        [call] = urlopen.call_args_list
        self.assertEqual((call.args[0].full_url, call.args[0].get_method()), (HOOK, "POST"))

    def test_no_hook_asks_for_nothing_and_a_failure_never_stops_a_publish(self):
        with override_settings(CLOUDFLARE_PAGES_DEPLOY_HOOK=""), mock.patch("urllib.request.urlopen") as urlopen:
            self.assertFalse(request_rebuild("test"))
        urlopen.assert_not_called()
        draft = PricebookVersion.new_draft()
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")), self.captureOnCommitCallbacks(execute=True):
            publish(draft, timezone.localdate(), {})
        self.assertTrue(PricebookVersion.objects.get(pk=draft.pk).is_published)

    def test_the_nightly_check_rebuilds_on_a_later_effective_date(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        draft = PricebookVersion.new_draft()
        draft.publish(tomorrow)
        self.assertIsNone(due_today())
        self.assertEqual(due_today(tomorrow), PricebookVersion.objects.get(pk=draft.pk))
        out = io.StringIO()
        call_command("rebuild_website", "--if-due", stdout=out)
        self.assertIn("no rebuild needed", out.getvalue())
        with mock.patch("pricebook.site_rebuild.timezone.localdate", return_value=tomorrow), \
                mock.patch("pricebook.models.timezone.localdate", return_value=tomorrow), \
                mock.patch("urllib.request.urlopen", return_value=self.response()) as urlopen:
            call_command("rebuild_website", "--if-due", stdout=out)
        urlopen.assert_called_once()
        self.assertIn("takes effect today", out.getvalue())

    def test_a_refused_rebuild_fails_the_command(self):
        with mock.patch("urllib.request.urlopen", return_value=self.response(status=500)), self.assertRaises(CommandError):
            call_command("rebuild_website", stdout=io.StringIO())
