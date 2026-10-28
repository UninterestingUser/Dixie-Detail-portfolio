import csv
import datetime
from decimal import Decimal

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from appointments import booking
from appointments.models import RepricingDecision
from pricebook import publishing
from pricebook.models import Price, PricebookVersion

from .fixtures import JobsTestCase, local


def matrix_rows():
    with (settings.DATA_DIR / "price-matrix.csv").open(newline="") as file:
        return list(csv.DictReader(file))


class PricebookTestCase(JobsTestCase):
    def start_draft(self):
        self.client.post(reverse("pricebook-new-draft"))
        return PricebookVersion.objects.get(status=PricebookVersion.Status.DRAFT)

    def draft_data(self, draft, **changes):
        """The draft form as it stands, with some cells changed."""
        data = {}
        for price in draft.prices.all():
            data[f"price-{price.pk}"] = str(price.price)
            data[f"hours-{price.pk}"] = str(price.one_person_service_hours)
        for rule in draft.derived_price_rules.all():
            data[f"derived-{rule.pk}"] = str(rule.percent)
        for level in draft.condition_levels.all():
            data[f"condition-{level.pk}"] = str(level.adjustment_percent)
        data.update(changes)
        return data

    def full_detail_price(self, version):
        return Price.objects.get(version=version, service=self.full_detail, vehicle_class=self.crossover, size_variant=self.two_rows)


class PriceMatrixTests(PricebookTestCase):
    def test_prices_are_laid_out_like_the_price_matrix(self):
        page = self.client.get(reverse("pricebook"), follow=True)
        self.assertContains(page, "Pricebook version 1")
        self.assertContains(page, "In effect today")
        text = page.content.decode()
        for row in matrix_rows():
            with self.subTest(row=row):
                self.assertIn(f"${Decimal(row['price_usd']):,.2f}", text)
        # Services in the file's order, and the file's first row first.
        first = matrix_rows()[0]
        services = list(dict.fromkeys(row["service"] for row in matrix_rows()))
        positions = [text.index(f">{name}</h2>") for name in services]
        self.assertEqual(positions, sorted(positions))
        self.assertLess(text.index(first["vehicle_class"].replace("&", "&amp;")), text.index(services[1] + "</h2>"))
        self.assertContains(page, "Monthly Maintenance</strong>:")

    def test_a_published_version_has_no_inputs(self):
        page = self.client.get(reverse("pricebook-version", args=[1]))
        self.assertNotContains(page, 'name="price-')
        self.assertContains(page, "Start a draft")


class DraftTests(PricebookTestCase):
    def test_start_a_draft_and_edit_it(self):
        draft = self.start_draft()
        self.assertEqual(draft.number, 2)
        self.assertEqual(draft.prices.count(), PricebookVersion.objects.get(number=1).prices.count())
        cell = self.full_detail_price(draft)
        page = self.client.get(reverse("pricebook-version", args=[2]))
        self.assertContains(page, f'name="price-{cell.pk}"')
        self.client.post(reverse("pricebook-save", args=[2]), self.draft_data(draft, **{f"price-{cell.pk}": "$265", f"hours-{cell.pk}": "5.25"}))
        cell.refresh_from_db()
        self.assertEqual((cell.price, cell.one_person_service_hours), (Decimal("265.00"), Decimal("5.25")))
        # The published version is untouched.
        self.assertEqual(self.full_detail_price(PricebookVersion.objects.get(number=1)).price, Decimal("250.00"))

    def test_a_bad_number_saves_nothing(self):
        draft = self.start_draft()
        cell = self.full_detail_price(draft)
        other = draft.prices.exclude(pk=cell.pk).first()
        response = self.client.post(reverse("pricebook-save", args=[2]), self.draft_data(draft, **{f"price-{cell.pk}": "lots", f"price-{other.pk}": "1"}), follow=True)
        self.assertContains(response, "enter a number")
        other_before = other.price
        other.refresh_from_db()
        self.assertEqual(other.price, other_before)

    def test_remove_a_price_and_discard_a_draft(self):
        draft = self.start_draft()
        cell = self.full_detail_price(draft)
        self.client.post(reverse("pricebook-save", args=[2]), self.draft_data(draft, **{f"remove-{cell.pk}": "on"}))
        self.assertFalse(Price.objects.filter(pk=cell.pk).exists())
        self.client.post(reverse("pricebook-discard", args=[2]))
        self.assertFalse(PricebookVersion.objects.filter(number=2).exists())

    def test_one_draft_at_a_time(self):
        self.start_draft()
        self.client.post(reverse("pricebook-new-draft"))
        self.assertEqual(PricebookVersion.objects.filter(status=PricebookVersion.Status.DRAFT).count(), 1)

    def test_a_published_version_cannot_be_saved(self):
        self.assertEqual(self.client.post(reverse("pricebook-save", args=[1]), {}).status_code, 403)

    def test_only_a_manager_changes_the_pricebook(self):
        self.client.force_login(self.helper_user)
        self.assertEqual(self.client.get(reverse("pricebook-version", args=[1])).status_code, 200)
        self.assertEqual(self.client.post(reverse("pricebook-new-draft")).status_code, 403)
        self.assertFalse(PricebookVersion.objects.filter(number=2).exists())


class ThreeBookedJobs(PricebookTestCase):
    """Three booked jobs, and a draft that raises their Full Detail price to $300."""

    def setUp(self):
        super().setUp()
        self.day = timezone.localdate() + datetime.timedelta(days=30)
        inputs = booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1)
        self.first = booking.book(self.customer, self.vehicle, local(self.day), inputs)
        self.second = booking.book(self.customer, self.vehicle, local(self.day + datetime.timedelta(days=1)), inputs)
        self.third = booking.book(self.customer, self.vehicle, local(self.day + datetime.timedelta(days=2)), inputs)
        self.draft = self.start_draft()
        cell = self.full_detail_price(self.draft)
        self.client.post(reverse("pricebook-save", args=[2]), self.draft_data(self.draft, **{f"price-{cell.pk}": "300"}))
        self.url = reverse("pricebook-publish", args=[2])
        self.today = timezone.localdate().isoformat()


class PublishTests(ThreeBookedJobs):
    def test_the_affected_jobs_screen(self):
        page = self.client.get(self.url, {"effective_date": self.today})
        self.assertContains(page, "3 booked jobs on or after")
        self.assertContains(page, "Price changes from $250.00 to $300.00")
        self.assertContains(page, "Keep booked price ($250.00)")
        self.assertContains(page, "Use new price ($300.00)")
        later = self.client.get(self.url, {"effective_date": (self.day + datetime.timedelta(days=3)).isoformat()})
        self.assertContains(later, "No booked job on or after that date changes.")

    def test_publish_with_a_choice_for_each_job_and_every_choice_logged(self):
        self.client.post(self.url, {
            "effective_date": self.today, "publish": "yes",
            f"choice-{self.first.pk}": "keep",
            f"choice-{self.second.pk}": "use_new",
            f"choice-{self.third.pk}": "custom", f"amount-{self.third.pk}": "275",
        })
        self.draft.refresh_from_db()
        self.assertEqual((self.draft.status, self.draft.effective_date), ("published", timezone.localdate()))
        totals = [job.total_before_tax for job in (self.first, self.second, self.third)]
        self.assertEqual(totals, [Decimal("250.00"), Decimal("300.00"), Decimal("275.00")])
        self.second.refresh_from_db()
        self.assertEqual(self.second.quote.pricebook_version, self.draft)
        log = {d.appointment_id: (d.choice, d.old_amount, d.new_amount, d.decided_by) for d in RepricingDecision.objects.all()}
        self.assertEqual(log, {
            self.first.pk: ("keep", Decimal("250.00"), Decimal("250.00"), self.owner_user),
            self.second.pk: ("use_new", Decimal("250.00"), Decimal("300.00"), self.owner_user),
            self.third.pk: ("custom", Decimal("250.00"), Decimal("275.00"), self.owner_user),
        })
        self.assertContains(self.client.get(reverse("pricebook-version", args=[2])), "Use new price: $250.00 to $300.00")

    def test_keep_all_is_the_default(self):
        self.client.post(self.url, {"effective_date": self.today, "all": "keep"})
        self.assertEqual({d.choice for d in RepricingDecision.objects.all()}, {"keep"})
        self.assertEqual(self.first.total_before_tax, Decimal("250.00"))

    def test_use_new_for_all(self):
        self.client.post(self.url, {"effective_date": self.today, "all": "use_new"})
        self.assertEqual([j.total_before_tax for j in (self.first, self.second, self.third)], [Decimal("300.00")] * 3)

    def test_a_series_is_decided_once(self):
        series = booking.book_series(self.customer, self.vehicle, local(self.day + datetime.timedelta(days=5)),
                                     booking.JobInputs(self.monthly, self.crossover, self.two_rows), "monthly", 3)
        page = self.client.get(self.url, {"effective_date": self.today})
        self.assertContains(page, "every visit left (3)")
        self.client.post(self.url, {"effective_date": self.today, "publish": "yes", f"series-{series.pk}": "use_new"})
        self.assertEqual({v.total_before_tax for v in series.appointments.all()}, {Decimal("150.00")})  # 50% of $300

    def test_the_effective_date_is_today_or_later(self):
        yesterday = (timezone.localdate() - datetime.timedelta(days=1)).isoformat()
        page = self.client.post(self.url, {"effective_date": yesterday, "publish": "yes"})
        self.assertContains(page, "today or later")
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, "draft")

    def test_completed_jobs_never_change(self):
        booking.set_status(self.first, "completed")
        self.client.post(self.url, {"effective_date": self.today, "all": "use_new"})
        self.assertEqual(self.first.total_before_tax, Decimal("250.00"))
        self.assertFalse(RepricingDecision.objects.filter(appointment=self.first).exists())

    def test_online_bookings_use_the_new_prices_from_the_effective_date(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        self.client.post(self.url, {"effective_date": tomorrow.isoformat(), "all": "keep"})
        today_job = booking.book(self.customer, self.vehicle, local(timezone.localdate()), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1))
        later_job = booking.book(self.customer, self.vehicle, local(self.day + datetime.timedelta(days=9)), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1))
        self.assertEqual((today_job.total_before_tax, later_job.total_before_tax), (Decimal("250.00"), Decimal("300.00")))


class BookedJobReviewTests(ThreeBookedJobs):
    """A version published without logging any choice, as apply_size_classes
    publishes, leaves each booked job it prices differently for the owner."""

    def setUp(self):
        super().setUp()
        publishing.publish(self.draft, timezone.localdate(), {}, log_choices=False)
        self.review = reverse("pricebook-booked-jobs", args=[2])

    def test_every_booked_job_keeps_its_quoted_price_until_the_owner_chooses(self):
        self.assertEqual([job.total_before_tax for job in (self.first, self.second, self.third)], [Decimal("250.00")] * 3)
        self.assertContains(self.client.get(reverse("pricebook-version", args=[2])), "3 booked jobs this version prices differently wait for your choice")
        page = self.client.get(self.review)
        self.assertContains(page, "Keep quoted price ($250.00)")
        self.assertContains(page, "Use new price ($300.00)")
        self.client.post(self.review, {f"choice-{self.first.pk}": "use_new", f"choice-{self.second.pk}": "keep", f"choice-{self.third.pk}": "keep"})
        self.first.refresh_from_db()
        self.assertEqual(self.first.total_before_tax, Decimal("300.00"))
        self.assertEqual(RepricingDecision.objects.count(), 3)
        self.assertContains(self.client.get(self.review), "No booked job waits for a choice.")

    def test_only_a_manager_chooses(self):
        self.client.force_login(self.helper_user)
        self.assertEqual(self.client.post(self.review, {"all": "use_new"}).status_code, 403)
        self.assertFalse(RepricingDecision.objects.exists())
