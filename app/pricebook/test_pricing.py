"""The pricebook load, the pricing engine, time on site, quotes and publishing,
checked against the real data files (data/price-matrix.csv and the rules)."""

import csv
import datetime
import io
from decimal import Decimal

import yaml
from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment, AppointmentLine
from core.scheduling import time_on_site
from customers.models import Customer
from pricebook.models import (
    DerivedPriceRule,
    Price,
    PricebookVersion,
    PricedLine,
    PublishedVersionError,
    QuoteChangeError,
    Service,
)
from pricebook.pricing import NotPriced, PricingError, base_price, issue_quote, price_job
from pricebook.publishing import affected_jobs
from promotions.models import Promotion
from vehicles.models import VehicleClass


def read_matrix():
    with (settings.DATA_DIR / "price-matrix.csv").open(newline="") as file:
        return list(csv.DictReader(file))


def hours(minutes):
    return Decimal(minutes) / 60


class PricebookTestCase(TestCase):
    """Loads the pricebook from data/ once for each test class."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_pricebook", stdout=io.StringIO())
        cls.version = PricebookVersion.objects.get(number=1)

    def service(self, name):
        return Service.objects.get(name=name)

    def vehicle_class(self, name):
        return VehicleClass.objects.get(name=name)

    def size(self, class_name, value):
        return self.vehicle_class(class_name).size_variants.get(value=value)

    def rav4(self, **inputs):
        """The worked example in data/pricing-rules.yaml, with any input changed."""
        inputs = {
            "size_variant": self.size("Medium", 2),
            "condition_level": 2,
            "add_ons": [self.service("Seat Extraction")],
            **inputs,
        }
        return price_job(self.service("Full Detail"), self.vehicle_class("Medium"), **inputs)


class LoadPricebookTests(PricebookTestCase):
    def test_version_1_is_published_effective_today(self):
        self.assertTrue(self.version.is_published)
        self.assertEqual(self.version.effective_date, timezone.localdate())

    def test_every_cell_of_the_price_matrix_matches_the_database(self):
        rows = read_matrix()
        self.assertEqual(len(rows), 91)
        for row in rows:
            vehicle_class = self.vehicle_class(row["vehicle_class"])
            size_variant = vehicle_class.size_variants.get(value=row["size_variant"]) if row["size_variant"] else None
            found = base_price(self.version, self.service(row["service"]), vehicle_class, size_variant)
            with self.subTest(row=row):
                self.assertEqual(found.price, Decimal(row["price_usd"]))
                self.assertEqual(found.one_person_service_hours, Decimal(row["one_person_service_hours"]))
                self.assertEqual(found.size_variant, size_variant)

    def test_maintenance_plans_are_rules_not_prices(self):
        maintenance = Service.objects.filter(kind=Service.Kind.MAINTENANCE_PLAN)
        self.assertFalse(Price.objects.filter(version=self.version, service__in=maintenance).exists())
        self.assertEqual(DerivedPriceRule.objects.filter(version=self.version).count(), 2)
        self.assertEqual(Price.objects.filter(version=self.version).count(), 91 - 22)

    def test_running_it_again_changes_nothing(self):
        counts = [model.objects.count() for model in (Price, Price.history.model, Service, VehicleClass)]
        output = io.StringIO()
        call_command("load_pricebook", stdout=output)
        self.assertIn("Nothing was changed", output.getvalue())
        self.assertEqual([model.objects.count() for model in (Price, Price.history.model, Service, VehicleClass)], counts)
        self.assertEqual(PricebookVersion.objects.count(), 1)


class PricingEngineTests(PricebookTestCase):
    def test_rav4_worked_example(self):
        rules = yaml.safe_load((settings.DATA_DIR / "pricing-rules.yaml").read_text())["worked_example"]
        job = self.rav4()
        self.assertEqual([line.amount for line in job.lines], [Decimal(line["price"]) for line in rules["lines"]])
        self.assertEqual(job.total_before_tax, Decimal("355.00"))
        self.assertEqual(job.total_before_tax, Decimal(rules["total_before_tax"]))
        # 4 hours, plus 10% for condition level 2, plus 1.5 hours of Seat Extraction (decision 0065).
        self.assertEqual(job.one_person_service_hours, Decimal("5.9"))
        self.assertEqual(job.one_person_service_hours, Decimal(str(rules["one_person_service_hours"])))
        self.assertEqual(job.service_minutes, 360)
        self.assertEqual(job.time_on_site.total_minutes, 420)
        self.assertEqual(hours(job.time_on_site.total_minutes), Decimal(str(rules["time_on_site_hours"])))
        self.assertFalse(job.full_day)
        self.assertIs(job.full_day, rules["full_day"])

    def test_monthly_maintenance_with_two_people_takes_2_25_to_4_5_hours_on_site(self):
        monthly = self.service("Monthly Maintenance")
        self.assertEqual(monthly.default_crew_size, 2)
        stays = []
        for row in read_matrix():
            if row["service"] != "Monthly Maintenance":
                continue
            vehicle_class = self.vehicle_class(row["vehicle_class"])
            job = price_job(monthly, vehicle_class, size_variant=vehicle_class.size_variants.get(value=row["size_variant"]))
            self.assertEqual(job.crew_size, 2)
            self.assertEqual(job.time_on_site.setup_minutes, 15)
            self.assertEqual(job.time_on_site.breakdown_minutes, 15)
            stays.append(job.time_on_site.total_minutes)
        self.assertEqual((hours(min(stays)), hours(max(stays))), (Decimal("2.25"), Decimal("4.5")))

    def test_two_people_take_60_percent_rounded_to_15_minutes(self):
        job = price_job(
            self.service("Full Detail"),
            self.vehicle_class("Large"),
            size_variant=self.size("Large", 2),
            condition_level=1,
            crew_size=2,
        )
        self.assertEqual(job.one_person_service_hours, Decimal("5"))
        self.assertEqual(hours(job.service_minutes), Decimal("3"))
        self.assertEqual(hours(job.time_on_site.total_minutes), Decimal("3.5"))

    def test_headlight_restoration_takes_2_5_hours_on_site_for_one_person(self):
        headlights = self.service("Headlight Restoration")
        # Every class offered but Motorcycles, whose only service is Motorcycle
        # Detail, and Full-size Vans, which are quoted by hand.
        for vehicle_class in VehicleClass.objects.offered().exclude(name="Motorcycles").exclude(booking=VehicleClass.Booking.QUOTE):
            job = price_job(headlights, vehicle_class)
            with self.subTest(vehicle_class=vehicle_class):
                self.assertEqual(job.total_before_tax, Decimal("95.00"))
                self.assertEqual(hours(job.time_on_site.total_minutes), Decimal("2.5"))

    def test_full_day_flag_starts_at_8_hours_on_site_for_one_person(self):
        rows = read_matrix()
        seven = next(row for row in rows if row["one_person_service_hours"] == "7")
        six_and_a_half = next(row for row in rows if row["one_person_service_hours"] == "6.5" and not row["service"].endswith("Maintenance"))
        for row, full_day in ((seven, True), (six_and_a_half, False)):
            vehicle_class = self.vehicle_class(row["vehicle_class"])
            size_variant = vehicle_class.size_variants.get(value=row["size_variant"]) if row["size_variant"] else None
            for crew_size in (1, 2):
                job = price_job(
                    self.service(row["service"]), vehicle_class, size_variant=size_variant, condition_level=1, crew_size=crew_size
                )
                with self.subTest(row=row, crew_size=crew_size):
                    self.assertEqual(hours(job.one_person_time_on_site.total_minutes), Decimal(row["one_person_service_hours"]) + 1)
                    # The flag counts one-person time on site, whatever the crew.
                    self.assertIs(job.full_day, full_day)

    def test_condition_never_changes_add_ons(self):
        carpet = self.service("Carpet Extraction")
        seats = self.service("Seat Extraction")
        add_on_prices = None
        for level, percent in ((1, 0), (2, 10), (3, 20)):
            job = self.rav4(condition_level=level, add_ons=[carpet, seats])
            add_ons = [line.amount for line in job.lines if line.kind == PricedLine.Kind.ADD_ON]
            add_on_prices = add_on_prices or add_ons
            self.assertEqual(add_ons, add_on_prices)
            self.assertEqual(add_ons, [Decimal("70.00"), Decimal("80.00")])
            condition = [line.amount for line in job.lines if line.kind == PricedLine.Kind.CONDITION]
            self.assertEqual(condition, [Decimal(250 * percent // 100)] if percent else [])

    def test_condition_adjustment_rounds_to_the_whole_dollar(self):
        job = price_job(
            self.service("Exterior Only"),
            self.vehicle_class("Medium"),
            condition_level=3,
        )
        # 20% of $120.
        self.assertEqual(job.lines[1].amount, Decimal("24.00"))
        job = price_job(self.service("Interior Only"), self.vehicle_class("Full-size Trucks"), size_variant=self.size("Full-size Trucks", 1), condition_level=2)
        # 10% of $125 is $12.50, rounded to $13.
        self.assertEqual(job.lines[1].amount, Decimal("13.00"))

    def test_condition_does_not_apply_to_maintenance_or_headlights(self):
        job = price_job(self.service("Headlight Restoration"), self.vehicle_class("Large"), condition_level=3)
        self.assertEqual(job.total_before_tax, Decimal("95.00"))
        self.assertIsNone(job.lines[0].condition_level)

    def test_a_service_with_condition_needs_a_level(self):
        with self.assertRaises(PricingError):
            price_job(self.service("Full Detail"), self.vehicle_class("Medium"), size_variant=self.size("Medium", 2))

    def test_a_missing_combination_cannot_be_priced(self):
        with self.assertRaises(NotPriced):
            price_job(self.service("Full Detail"), self.vehicle_class("Motorcycles"), condition_level=1)
        # An add-on is priced by size, so it needs one.
        with self.assertRaises(NotPriced):
            price_job(
                self.service("Exterior Only"),
                self.vehicle_class("Large"),
                condition_level=1,
                add_ons=[self.service("Carpet Extraction")],
            )
        # A service off the price list, or an add-on alone, is not a job.
        with self.assertRaises(PricingError):
            price_job(self.service("PPF Removal"), self.vehicle_class("Large"))
        with self.assertRaises(PricingError):
            price_job(self.service("Seat Extraction"), self.vehicle_class("Large"), size_variant=self.size("Large", 2))

    def test_a_size_variant_must_belong_to_the_class(self):
        with self.assertRaises(PricingError):
            price_job(
                self.service("Full Detail"),
                self.vehicle_class("Large"),
                size_variant=self.size("Small", 2),
                condition_level=1,
            )

    def test_percentage_promotion_rounds_to_the_cent(self):
        promotion = Promotion.objects.create(name="Test Offer", kind=Promotion.Kind.PERCENT_OFF, value=Decimal("12.5"))
        job = self.rav4(promotions=[promotion])
        # 12.5% of $355 is $44.375 (decision 0055).
        self.assertEqual(job.lines[-1].amount, Decimal("-44.38"))
        self.assertEqual(job.total_before_tax, Decimal("310.62"))

    def test_promotion_applies_only_to_its_services(self):
        promotion = Promotion.objects.create(name="Seats Offer", kind=Promotion.Kind.AMOUNT_OFF, value=Decimal("100"))
        promotion.services.set([self.service("Seat Extraction")])
        job = self.rav4(promotions=[promotion])
        # Never more than the $80 it applies to.
        self.assertEqual(job.lines[-1].amount, Decimal("-80.00"))
        with self.assertRaises(PricingError):
            price_job(self.service("Headlight Restoration"), self.vehicle_class("Large"), promotions=[promotion])

    def test_promotion_outside_its_dates_is_refused(self):
        today = timezone.localdate()
        expired = Promotion.objects.create(
            name="Old Offer", kind=Promotion.Kind.AMOUNT_OFF, value=Decimal("10"), ends_on=today - datetime.timedelta(days=1)
        )
        with self.assertRaises(PricingError):
            self.rav4(promotions=[expired])

    def test_time_on_site_divides_setup_and_breakdown_by_the_crew(self):
        self.assertEqual(time_on_site(300, 1).total_minutes, 360)
        stay = time_on_site(195, 2)
        self.assertEqual((stay.setup_minutes, stay.breakdown_minutes, stay.total_minutes), (15, 15, 225))


class ConditionLengthensServiceTimeTests(PricebookTestCase):
    """The condition percentage also lengthens the main service (decision 0065)."""

    def full_detail(self, class_name, size, level, crew_size=None, **inputs):
        return price_job(
            self.service("Full Detail"),
            self.vehicle_class(class_name),
            size_variant=self.size(class_name, size),
            condition_level=level,
            crew_size=crew_size,
            **inputs,
        )

    def test_one_row_small_full_detail_at_level_3(self):
        job = self.full_detail("Small", 1, 3)
        # 3 hours plus 20% is 3.6, rounded once to 3.5.
        self.assertEqual(job.one_person_service_hours, Decimal("3.6"))
        self.assertEqual(hours(job.service_minutes), Decimal("3.5"))
        self.assertEqual(hours(job.time_on_site.total_minutes), Decimal("4.5"))

    def test_two_person_large_full_detail_at_level_3(self):
        job = self.full_detail("Large", 2, 3, crew_size=2)
        # 5 hours plus 20% is 6; 60% of that is 3.6, rounded once to 3.5.
        self.assertEqual(job.one_person_service_hours, Decimal("6"))
        self.assertEqual(hours(job.service_minutes), Decimal("3.5"))
        self.assertEqual(hours(job.time_on_site.total_minutes), Decimal("4"))
        self.assertEqual((job.time_on_site.setup_minutes, job.time_on_site.breakdown_minutes), (15, 15))

    def test_level_1_changes_nothing(self):
        for service_name, class_name, size in (
            ("Full Detail", "Large", 2),
            ("Interior Only", "Small", 2),
            ("Exterior Only", "Full-size Trucks", None),
        ):
            vehicle_class = self.vehicle_class(class_name)
            size_variant = self.size(class_name, size) if size else None
            job = price_job(self.service(service_name), vehicle_class, size_variant=size_variant, condition_level=1)
            base = base_price(self.version, self.service(service_name), vehicle_class, size_variant)
            with self.subTest(service=service_name):
                self.assertEqual(len(job.lines), 1)
                self.assertEqual(job.total_before_tax, base.price)
                self.assertEqual(job.one_person_service_hours, base.one_person_service_hours)

    def test_the_condition_line_carries_its_extra_time_unrounded(self):
        job = self.full_detail("Full-size Trucks", 2, 2)
        [condition] = [line for line in job.lines if line.kind == PricedLine.Kind.CONDITION]
        # 10% of 6 hours.
        self.assertEqual(condition.one_person_service_hours, Decimal("0.6"))
        quote = issue_quote(
            self.service("Full Detail"),
            self.vehicle_class("Full-size Trucks"),
            size_variant=self.size("Full-size Trucks", 2),
            condition_level=2,
        )
        self.assertEqual(quote.lines.get(kind=PricedLine.Kind.CONDITION).one_person_service_hours, Decimal("0.6"))
        self.assertEqual(quote.one_person_service_hours, Decimal("6.6"))

    def test_interior_and_exterior_only_are_lengthened_too(self):
        interior = price_job(
            self.service("Interior Only"), self.vehicle_class("Small"), size_variant=self.size("Small", 2), condition_level=3
        )
        exterior = price_job(self.service("Exterior Only"), self.vehicle_class("Large"), condition_level=2)
        # 2 hours + 20%, and 2 hours + 10%.
        self.assertEqual(interior.one_person_service_hours, Decimal("2.4"))
        self.assertEqual(exterior.one_person_service_hours, Decimal("2.2"))

    def test_add_ons_never_change_with_condition(self):
        for level in (1, 2, 3):
            job = self.full_detail(
                "Medium", 3, level, add_ons=[self.service("Carpet Extraction"), self.service("Seat Extraction")]
            )
            add_ons = [(line.amount, line.one_person_service_hours) for line in job.lines if line.kind == PricedLine.Kind.ADD_ON]
            with self.subTest(level=level):
                self.assertEqual(add_ons, [(Decimal("90.00"), Decimal("2")), (Decimal("100.00"), Decimal("2"))])

    def test_maintenance_plans_never_change_with_condition(self):
        for name in ("Monthly Maintenance", "Quarterly Maintenance"):
            plain = price_job(self.service(name), self.vehicle_class("Large"), size_variant=self.size("Large", 3))
            for level in (1, 2, 3):
                job = price_job(
                    self.service(name), self.vehicle_class("Large"), size_variant=self.size("Large", 3), condition_level=level
                )
                with self.subTest(service=name, level=level):
                    self.assertEqual(len(job.lines), 1)
                    self.assertEqual(job.total_before_tax, plain.total_before_tax)
                    self.assertEqual(job.one_person_service_hours, plain.one_person_service_hours)
                    self.assertEqual(job.time_on_site, plain.time_on_site)


class MaintenanceFollowsFullDetailTests(PricebookTestCase):
    def test_maintenance_follows_a_changed_full_detail_price(self):
        crossover = self.vehicle_class("Medium")
        two_rows = self.size("Medium", 2)
        full_detail = self.service("Full Detail")
        draft = PricebookVersion.new_draft()
        price = Price.objects.get(version=draft, service=full_detail, vehicle_class=crossover, size_variant=two_rows)
        price.price = Decimal("300.00")
        price.save()
        draft.publish(timezone.localdate())

        self.assertEqual(PricebookVersion.current(), draft)
        monthly = price_job(self.service("Monthly Maintenance"), crossover, size_variant=two_rows)
        quarterly = price_job(self.service("Quarterly Maintenance"), crossover, size_variant=two_rows)
        self.assertEqual(monthly.total_before_tax, Decimal("150.00"))
        self.assertEqual(quarterly.total_before_tax, Decimal("240.00"))
        self.assertEqual(monthly.one_person_service_hours, Decimal("4"))
        # Version 1 is unchanged.
        old = price_job(self.service("Monthly Maintenance"), crossover, size_variant=two_rows, version=self.version)
        self.assertEqual(old.total_before_tax, Decimal("125.00"))


class QuoteAndBookingTests(PricebookTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(first_name="Pat", mobile="4235550142")
        self.promotion = Promotion.objects.create(name="Test Offer", kind=Promotion.Kind.PERCENT_OFF, value=Decimal("12.5"))
        self.quote = issue_quote(
            self.service("Full Detail"),
            self.vehicle_class("Medium"),
            size_variant=self.size("Medium", 2),
            condition_level=2,
            add_ons=[self.service("Seat Extraction")],
            promotions=[self.promotion],
        )

    def book(self, quote, days=20):
        start = timezone.make_aware(datetime.datetime.combine(timezone.localdate() + datetime.timedelta(days=days), datetime.time(8)))
        return Appointment.book_from_quote(quote, customer=self.customer, scheduled_start=start, source=Appointment.Source.OWNER)

    def test_quote_holds_inputs_totals_and_times(self):
        quote = self.quote
        self.assertEqual(quote.pricebook_version, self.version)
        self.assertEqual(list(quote.add_ons.all()), [self.service("Seat Extraction")])
        self.assertEqual(list(quote.promotions.all()), [self.promotion])
        self.assertEqual(quote.total_before_tax, Decimal("310.62"))
        self.assertEqual((quote.tax_rate, quote.sales_tax, quote.total), (Decimal("0"), Decimal("0"), Decimal("310.62")))
        self.assertEqual(quote.one_person_service_hours, Decimal("5.9"))
        self.assertEqual((quote.setup_minutes, quote.service_minutes, quote.breakdown_minutes), (30, 360, 30))
        self.assertEqual(quote.time_on_site_minutes, 420)
        self.assertFalse(quote.full_day)
        condition = quote.lines.get(kind=PricedLine.Kind.CONDITION)
        self.assertEqual(condition.one_person_service_hours, Decimal("0.4"))
        self.assertEqual(quote.lines.count(), 4)

    def test_a_quote_never_changes(self):
        self.quote.total = Decimal("1.00")
        with self.assertRaises(QuoteChangeError):
            self.quote.save()
        line = self.quote.lines.first()
        line.amount = Decimal("1.00")
        with self.assertRaises(QuoteChangeError):
            line.save()

    def test_an_appointment_booked_from_a_quote_keeps_its_lines_exactly(self):
        appointment = self.book(self.quote)
        quote_lines = list(self.quote.lines.all())
        booked = list(appointment.lines.all())
        self.assertEqual(len(booked), len(quote_lines))
        for quote_line, line in zip(quote_lines, booked):
            for name in PricedLine.COPIED_FIELDS:
                with self.subTest(field=name, line=quote_line.description):
                    self.assertEqual(getattr(line, name), getattr(quote_line, name))
        self.assertEqual(appointment.total_before_tax, self.quote.total_before_tax)
        self.assertEqual(appointment.time_on_site_minutes, self.quote.time_on_site_minutes)
        self.assertEqual(appointment.quote, self.quote)

        # A later pricebook change does not reach the booked job.
        draft = PricebookVersion.new_draft()
        for price in Price.objects.filter(version=draft):
            price.price += 50
            price.save()
        draft.publish(timezone.localdate())
        appointment.refresh_from_db()
        self.assertEqual([line.amount for line in appointment.lines.all()], [line.amount for line in quote_lines])

    def test_a_quote_books_one_appointment(self):
        self.book(self.quote)
        with self.assertRaises(ValueError):
            self.book(self.quote, days=21)

    def test_quotes_come_from_a_published_version(self):
        draft = PricebookVersion.new_draft()
        with self.assertRaises(PricingError):
            issue_quote(self.service("Headlight Restoration"), self.vehicle_class("Large"), version=draft)


class PublishingTests(PricebookTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(first_name="Pat", mobile="4235550142")
        self.crossover = self.vehicle_class("Medium")
        self.two_rows = self.size("Medium", 2)

    def book(self, service_name, days, **inputs):
        quote = issue_quote(self.service(service_name), self.crossover, size_variant=self.two_rows, **inputs)
        start = timezone.make_aware(datetime.datetime.combine(timezone.localdate() + datetime.timedelta(days=days), datetime.time(8)))
        return Appointment.book_from_quote(quote, customer=self.customer, scheduled_start=start, source=Appointment.Source.OWNER)

    def test_a_draft_copies_the_published_version(self):
        draft = PricebookVersion.new_draft()
        self.assertEqual(draft.number, 2)
        self.assertFalse(draft.is_published)
        self.assertEqual(Price.objects.filter(version=draft).count(), Price.objects.filter(version=self.version).count())
        self.assertEqual(DerivedPriceRule.objects.filter(version=draft).count(), 2)
        self.assertEqual(PricebookVersion.current(), self.version)

    def test_publishing_needs_an_effective_date_today_or_later(self):
        draft = PricebookVersion.new_draft()
        with self.assertRaises(ValueError):
            draft.publish(timezone.localdate() - datetime.timedelta(days=1))
        later = timezone.localdate() + datetime.timedelta(days=30)
        draft.publish(later)
        # Not in effect until its date.
        self.assertEqual(PricebookVersion.current(), self.version)
        self.assertEqual(PricebookVersion.current(later), draft)
        with self.assertRaises(PublishedVersionError):
            draft.publish(later)

    def test_affected_jobs_lists_booked_jobs_the_change_touches(self):
        touched = self.book("Full Detail", days=20, condition_level=2)
        maintenance = self.book("Monthly Maintenance", days=21)
        untouched = self.book("Headlight Restoration", days=22)
        before = self.book("Full Detail", days=5, condition_level=1)
        completed = self.book("Full Detail", days=25, condition_level=1)
        completed.status = Appointment.Status.COMPLETED
        completed.save()

        draft = PricebookVersion.new_draft()
        price = Price.objects.get(version=draft, service=self.service("Full Detail"), vehicle_class=self.crossover, size_variant=self.two_rows)
        price.price = Decimal("300.00")
        price.one_person_service_hours = Decimal("7")
        price.save()

        effective = timezone.localdate() + datetime.timedelta(days=10)
        affected = {job.appointment: job for job in affected_jobs(draft, effective)}
        self.assertEqual(set(affected), {touched, maintenance})
        self.assertNotIn(untouched, affected)
        self.assertNotIn(before, affected)
        self.assertNotIn(completed, affected)
        # $250 + 10% becomes $300 + 10%.
        self.assertEqual((affected[touched].booked_total, affected[touched].new_total), (Decimal("275.00"), Decimal("330.00")))
        self.assertTrue(affected[touched].becomes_full_day)
        self.assertEqual(affected[maintenance].new_total, Decimal("150.00"))

    def test_affected_jobs_lists_a_job_whose_service_is_removed(self):
        booked = self.book("Headlight Restoration", days=20)
        draft = PricebookVersion.new_draft()
        Price.objects.filter(version=draft, service=self.service("Headlight Restoration")).delete()
        [job] = affected_jobs(draft, timezone.localdate())
        self.assertEqual(job.appointment, booked)
        self.assertIsNone(job.new_total)
        self.assertIn("no longer be priced", job.reasons[0])


class QuoteCommandTests(PricebookTestCase):
    def test_quote_prints_lines_total_service_time_and_time_on_site(self):
        output = io.StringIO()
        call_command(
            "quote",
            "--service", "Full Detail",
            "--class", "Medium",
            "--size", "2",
            "--condition", "2",
            "--add-on", "Seat Extraction",
            stdout=output,
        )
        text = output.getvalue()
        for expected in ("Full Detail", "$250.00", "Condition level 2 (+10%)", "$25.00", "Seat Extraction", "$80.00", "$355.00",
                         "Service time: 5.9 hours", "Time on site: 7 hours"):
            self.assertIn(expected, text)
