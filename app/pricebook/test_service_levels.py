"""Condition levels (the website's service levels) apply only to Full Detail
and Interior Only, and Level 3 is booked by quote (decision 0103): the
engine, the hand quote, load_pricebook and the booked-job review."""

import datetime
import io
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment
from customers.models import Customer
from pricebook.models import ConditionLevel, ConditionService, PricebookVersion, PricedLine, Service
from pricebook.pricing import BookedByQuote, issue_hand_quote, issue_quote, price_job, reference_price
from pricebook.publishing import affected_jobs, publish
from vehicles.models import VehicleClass

NO_LEVEL = ["Exterior Only", "1-Step Paint Correction", "2-Step Paint Correction", "Headlight Restoration", "Motorcycle Detail"]
TAKE_A_LEVEL = ["Full Detail", "Interior Only"]


class ServiceLevelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_pricebook", stdout=io.StringIO())
        cls.version = PricebookVersion.objects.get(number=1)
        cls.medium = VehicleClass.objects.get(name="Medium")
        cls.two_rows = cls.medium.size_variants.get(value=2)
        cls.motorcycles = VehicleClass.objects.get(name="Motorcycles")

    def service(self, name):
        return Service.objects.get(name=name)

    def priced(self, name, level=None, **inputs):
        if name == "Motorcycle Detail":
            return price_job(self.service(name), self.motorcycles, condition_level=level, **inputs)
        size = self.two_rows if name in TAKE_A_LEVEL else None
        return price_job(self.service(name), self.medium, size_variant=size, condition_level=level, **inputs)


class WhichServicesTakeALevelTests(ServiceLevelTestCase):
    def test_only_full_detail_and_interior_only_take_a_level(self):
        for service in Service.objects.filter(kind=Service.Kind.MAIN, on_price_list=True):
            with self.subTest(service=service.name):
                self.assertEqual(self.version.takes_condition_level(service), service.name in TAKE_A_LEVEL)
        self.assertEqual(
            sorted(ConditionService.objects.filter(version=self.version).values_list("service__name", flat=True)),
            TAKE_A_LEVEL,
        )

    def test_level_1_adds_nothing_level_2_adds_10_percent_and_level_3_is_booked_by_quote(self):
        levels = {level.level: level for level in ConditionLevel.objects.filter(version=self.version)}
        self.assertEqual((levels[1].adjustment_percent, levels[1].booked_by_quote), (Decimal("0"), False))
        self.assertEqual((levels[2].adjustment_percent, levels[2].booked_by_quote), (Decimal("10"), False))
        self.assertEqual((levels[3].adjustment_percent, levels[3].booked_by_quote), (Decimal("0"), True))

    def test_the_other_services_take_no_level_at_all(self):
        for name in NO_LEVEL:
            plain = self.priced(name)
            for level in (1, 2, 3):
                job = self.priced(name, level)
                with self.subTest(service=name, level=level):
                    self.assertEqual(len(job.lines), 1)
                    self.assertIsNone(job.condition_level)
                    self.assertIsNone(job.lines[0].condition_level)
                    self.assertEqual(job.total_before_tax, plain.total_before_tax)
                    self.assertEqual(job.one_person_service_hours, plain.one_person_service_hours)

    def test_exterior_only_loses_its_10_and_20_percent(self):
        quote = issue_quote(self.service("Exterior Only"), self.medium, condition_level=2)
        self.assertIsNone(quote.condition_level)
        self.assertFalse(quote.lines.filter(kind=PricedLine.Kind.CONDITION).exists())
        self.assertEqual(quote.total_before_tax, Decimal("120.00"))


class LevelsOneAndTwoTests(ServiceLevelTestCase):
    def test_full_detail_and_interior_only_price_as_before(self):
        # Medium two rows: Full Detail $250 and 4 hours, Interior Only $160 and 2.5 hours.
        expected = {
            ("Full Detail", 1): (Decimal("250.00"), Decimal("4")),
            ("Full Detail", 2): (Decimal("275.00"), Decimal("4.4")),
            ("Interior Only", 1): (Decimal("160.00"), Decimal("2.5")),
            ("Interior Only", 2): (Decimal("176.00"), Decimal("2.75")),
        }
        for (name, level), (total, hours) in expected.items():
            job = self.priced(name, level)
            with self.subTest(service=name, level=level):
                self.assertEqual((job.total_before_tax, job.one_person_service_hours), (total, hours))

    def test_a_level_is_still_needed(self):
        with self.assertRaisesMessage(Exception, "needs a condition level"):
            self.priced("Full Detail")


class LevelThreeTests(ServiceLevelTestCase):
    def test_level_3_has_no_price_or_time(self):
        for name in TAKE_A_LEVEL:
            with self.subTest(service=name):
                with self.assertRaises(BookedByQuote):
                    self.priced(name, 3)
                with self.assertRaises(BookedByQuote):
                    issue_quote(self.service(name), self.medium, size_variant=self.two_rows, condition_level=3)

    def test_the_reference_price_is_level_2(self):
        seats = self.service("Seat Extraction")
        job = reference_price(self.service("Full Detail"), self.medium, self.two_rows, [seats])
        self.assertEqual(job.condition_level, 2)
        self.assertEqual(job.total_before_tax, Decimal("355.00"))
        # Nothing to refer to for a service with no level, or a size not known.
        self.assertIsNone(reference_price(self.service("Exterior Only"), self.medium))
        self.assertIsNone(reference_price(self.service("Full Detail"), self.medium))

    def test_a_hand_quote_records_the_price_time_level_and_add_ons(self):
        seats = self.service("Seat Extraction")
        quote = issue_hand_quote(
            self.service("Full Detail"), self.medium, Decimal("425.00"), 480,
            description="Full Detail, condition level 3, with Seat Extraction, priced by hand",
            size_variant=self.two_rows, condition_level=3, add_ons=[seats],
        )
        self.assertTrue(quote.priced_by_hand)
        self.assertEqual((quote.condition_level, list(quote.add_ons.all())), (3, [seats]))
        self.assertEqual((quote.total_before_tax, quote.time_on_site_minutes), (Decimal("425.00"), 480))
        # 30 minutes of setup and 30 of breakdown for one person; the rest is service.
        self.assertEqual((quote.setup_minutes, quote.service_minutes, quote.breakdown_minutes), (30, 420, 30))
        [line] = quote.lines.all()
        self.assertEqual((line.kind, line.amount, line.condition_level), (PricedLine.Kind.SERVICE, Decimal("425.00"), 3))
        self.assertTrue(quote.full_day)


class NewVersionTests(ServiceLevelTestCase):
    """A version with the rules before decision 0103, then load_pricebook
    with the new data files, as on the server."""

    def setUp(self):
        old = PricebookVersion.new_draft(notes="The rules before decision 0103.")
        ConditionService.objects.create(version=old, service=self.service("Exterior Only"))
        level = ConditionLevel.objects.get(version=old, level=3)
        level.adjustment_percent, level.booked_by_quote = Decimal("20"), False
        level.save()
        old.publish(timezone.localdate())
        self.old = old
        self.customer = Customer.objects.create(first_name="Pat", mobile="4235550142")

    def book(self, name, days, level=None, size=True, completed=False):
        quote = issue_quote(
            self.service(name), self.medium, size_variant=self.two_rows if size else None, condition_level=level, version=self.old,
        )
        start = timezone.make_aware(datetime.datetime.combine(timezone.localdate() + datetime.timedelta(days=days), datetime.time(8)))
        appointment = Appointment.book_from_quote(quote, customer=self.customer, scheduled_start=start, source=Appointment.Source.OWNER)
        if completed:
            appointment.status = Appointment.Status.COMPLETED
            appointment.save()
        return appointment

    def lines(self, appointment):
        return [(line.kind, line.amount, line.one_person_service_hours, line.condition_level) for line in appointment.lines.order_by("position")]

    def test_load_pricebook_puts_the_new_rules_in_a_draft(self):
        out = io.StringIO()
        call_command("load_pricebook", stdout=out)
        draft = PricebookVersion.objects.get(status=PricebookVersion.Status.DRAFT)
        self.assertIn(f"Exterior Only: takes a condition level in version {self.old.number}, not in the file", out.getvalue())
        self.assertIn(f"Condition level 3: version {self.old.number} has +20%, the file booked by quote", out.getvalue())
        self.assertEqual(draft.condition_service_ids(), {self.service(name).pk for name in TAKE_A_LEVEL})
        self.assertTrue(draft.condition_levels.get(level=3).booked_by_quote)
        # The old version keeps its rules.
        self.assertTrue(self.old.takes_condition_level(self.service("Exterior Only")))

    def test_booked_jobs_keep_their_quoted_prices_and_past_jobs_their_condition_lines(self):
        exterior = self.book("Exterior Only", 20, level=2, size=False)
        level_3 = self.book("Full Detail", 21, level=3)
        level_2 = self.book("Full Detail", 22, level=2)
        past = self.book("Interior Only", 23, level=3, completed=True)
        before = {job.pk: self.lines(job) for job in (exterior, level_3, level_2, past)}
        call_command("load_pricebook", stdout=io.StringIO())
        draft = PricebookVersion.objects.get(status=PricebookVersion.Status.DRAFT)

        effective = timezone.localdate() + datetime.timedelta(days=10)
        affected = {job.appointment: job for job in affected_jobs(draft, effective)}
        # Exterior Only would lose its 10%; Level 3 can't be priced; Level 2 is unchanged.
        self.assertEqual(set(affected), {exterior, level_3})
        self.assertEqual((affected[exterior].booked_total, affected[exterior].new_total), (Decimal("132.00"), Decimal("120.00")))
        self.assertIsNone(affected[level_3].new_total)
        self.assertIn("priced by hand", affected[level_3].reasons[0])

        publish(draft, effective, {})
        for job in (exterior, level_3, level_2, past):
            with self.subTest(appointment=job.pk):
                self.assertEqual(self.lines(job), before[job.pk])
        self.assertIn((PricedLine.Kind.CONDITION, Decimal("50.00"), Decimal("0.8"), 3), self.lines(level_3))

    def test_a_job_priced_by_hand_is_never_listed(self):
        quote = issue_hand_quote(
            self.service("Full Detail"), self.medium, Decimal("425.00"), 480, description="Full Detail, priced by hand",
            size_variant=self.two_rows, condition_level=3,
        )
        start = timezone.make_aware(datetime.datetime.combine(timezone.localdate() + datetime.timedelta(days=20), datetime.time(8)))
        Appointment.book_from_quote(quote, customer=self.customer, scheduled_start=start, source=Appointment.Source.OWNER)
        call_command("load_pricebook", stdout=io.StringIO())
        draft = PricebookVersion.objects.get(status=PricebookVersion.Status.DRAFT)
        self.assertEqual(affected_jobs(draft, timezone.localdate() + datetime.timedelta(days=10)), [])
