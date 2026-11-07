"""Sales tax: loading and checking Tennessee's rates, the tax line on a
quote, tips and promotions, and the Georgia exception. The state's map
service is replaced by geo.fixtures.FakeServices (no network)."""

import datetime
import io
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from appointments import booking
from billing import tax_rates
from billing.models import Payment, TaxBoundary, TaxJurisdiction, TaxRate
from billing.tax import match_point, rate_on, tax_line, tax_line_for_appointment
from control.fixtures import JobsTestCase, local
from customers.models import Address
from geo.fixtures import FakeServices, import_fixture_rates
from geo.models import LocationSettings
from pricebook.models import PricebookVersion
from pricebook.pricing import issue_quote
from promotions.models import Promotion

TODAY = datetime.date(2026, 11, 6)


def rate_of(code, day=TODAY):
    return rate_on(TaxJurisdiction.objects.get(code=code), day)


class ImportTaxRatesTests(TestCase):
    def test_the_import_loads_rates_boundaries_and_the_georgia_rate(self):
        report = import_fixture_rates(today=TODAY)
        self.assertEqual(report.new_jurisdictions, 6)  # 4 with boundaries, Knox County, Georgia
        cleveland = TaxJurisdiction.objects.get(code="0601")
        self.assertEqual((cleveland.name, cleveland.kind, cleveland.county), ("Cleveland", "city", "Bradley"))
        self.assertEqual(TaxJurisdiction.objects.get(code="0600").name, "Bradley County")
        self.assertEqual((rate_of("0601").state_rate, rate_of("0601").local_rate), (Decimal("7.000"), Decimal("2.750")))
        self.assertEqual(rate_of("3301").combined_rate, Decimal("9.250"))
        self.assertEqual(TaxBoundary.objects.count(), 4)
        self.assertFalse(TaxBoundary.objects.filter(jurisdiction__code="4700").exists())
        georgia = TaxJurisdiction.objects.get(code="GA")
        self.assertEqual((georgia.kind, rate_of("GA").combined_rate), ("state", Decimal("0.000")))

    def test_points_match_cities_and_county_areas_with_holes(self):
        import_fixture_rates(today=TODAY)
        self.assertEqual(match_point(Decimal("35.16"), Decimal("-84.88")).name, "Cleveland")
        self.assertEqual(match_point(Decimal("35.05"), Decimal("-84.95")).name, "Bradley County")
        self.assertEqual(match_point(Decimal("35.05"), Decimal("-85.30")).name, "Chattanooga")
        self.assertIsNone(match_point(Decimal("34.96"), Decimal("-84.95")))  # Georgia

    def test_dry_run_changes_nothing(self):
        out = io.StringIO()
        with FakeServices().patch():
            call_command("import_tax_rates", "--dry-run", stdout=out)
        self.assertIn("new: Cleveland (Bradley County, code 0601) at 7% + 2.75% = 9.75%", out.getvalue())
        self.assertIn("(dry run, nothing changed)", out.getvalue())
        self.assertFalse(TaxJurisdiction.objects.exists())

    def test_a_second_import_finds_nothing_new(self):
        import_fixture_rates(today=TODAY)
        report = import_fixture_rates(today=TODAY)
        self.assertEqual((report.new_jurisdictions, report.rate_changes, report.boundaries_changed), (0, 0, 0))
        self.assertEqual(report.unchanged, 5)  # Georgia is the owner's setting, not compared


class RateChangeTests(TestCase):
    """The scheduled check flags a changed rate; it applies only once approved."""

    def setUp(self):
        import_fixture_rates(today=TODAY)
        self.cleveland = TaxJurisdiction.objects.get(code="0601")

    def check_with_rate(self, local_rate, today):
        rows = [tax_rates.Row("0601", "Bradley", "Cleveland", Decimal(local_rate))]
        return tax_rates.apply(rows, mode="check", today=today)

    def test_a_change_waits_for_approval_and_is_not_used(self):
        report = self.check_with_rate("3.00", TODAY + datetime.timedelta(days=30))
        self.assertEqual((report.rate_changes, report.waiting), (1, 1))
        pending = TaxRate.objects.get(jurisdiction=self.cleveland, approved_at__isnull=True)
        self.assertTrue(pending.is_pending)
        self.assertEqual(rate_of("0601", TODAY + datetime.timedelta(days=60)).local_rate, Decimal("2.750"))
        # The same change found again the next morning is not stored twice.
        self.assertEqual(self.check_with_rate("3.00", TODAY + datetime.timedelta(days=31)).rate_changes, 0)
        self.assertEqual(TaxRate.objects.filter(jurisdiction=self.cleveland, approved_at__isnull=True).count(), 1)

    def test_an_approved_change_applies_from_its_date_and_ends_the_old_rate(self):
        self.check_with_rate("3.00", TODAY + datetime.timedelta(days=30))
        pending = TaxRate.objects.get(jurisdiction=self.cleveland, approved_at__isnull=True)
        start = datetime.date(2027, 1, 1)
        tax_rates.approve_rate(pending, start)
        self.assertEqual(rate_of("0601", datetime.date(2026, 12, 31)).local_rate, Decimal("2.750"))
        self.assertEqual(rate_of("0601", start).local_rate, Decimal("3.000"))
        old = TaxRate.objects.get(jurisdiction=self.cleveland, local_rate=Decimal("2.75"))
        self.assertEqual(old.effective_to, datetime.date(2026, 12, 31))

    def test_a_rejected_change_is_not_flagged_again(self):
        self.check_with_rate("3.00", TODAY + datetime.timedelta(days=30))
        tax_rates.reject_rate(TaxRate.objects.get(jurisdiction=self.cleveland, approved_at__isnull=True))
        report = self.check_with_rate("3.00", TODAY + datetime.timedelta(days=31))
        self.assertEqual((report.rate_changes, report.waiting), (0, 0))

    def test_the_check_command_exits_2_while_a_change_waits(self):
        self.check_with_rate("3.00", TODAY + datetime.timedelta(days=30))
        with FakeServices().patch(), self.assertRaises(SystemExit) as exit_:
            call_command("import_tax_rates", "--check", stdout=io.StringIO())
        self.assertEqual(exit_.exception.code, 2)

    def test_georgia_is_a_setting_the_owner_changes(self):
        georgia = TaxJurisdiction.objects.get(code="GA")
        tax_rates.set_state_rate(georgia, Decimal("4"), datetime.date(2027, 1, 1))
        self.assertEqual(rate_of("GA", datetime.date(2026, 12, 31)).state_rate, Decimal("0.000"))
        self.assertEqual(rate_of("GA", datetime.date(2027, 1, 1)).state_rate, Decimal("4.000"))
        with self.assertRaises(tax_rates.RateError):
            tax_rates.set_state_rate(self.cleveland, Decimal("1"), datetime.date(2027, 2, 1))


class QuoteTaxTests(JobsTestCase):
    """The quote's tax line: taxable amount, state and local tax, jurisdiction."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        import_fixture_rates(today=TODAY)

        def address(line1, lat, lon, county, state="TN", **fields):
            return Address.objects.create(
                customer=cls.customer, line1=line1, city="Somewhere", state=state, zip_code="37311",
                latitude=Decimal(lat), longitude=Decimal(lon), county=county, verification="census", **fields,
            )

        cls.cleveland = address("100 Example St NW", "35.1612", "-84.8770", "Bradley")
        cls.chattanooga = address("200 Sample Ave", "35.0456", "-85.3097", "Hamilton")
        cls.rural = address("300 Pretend Rd SE", "35.0510", "-84.9480", "Bradley")
        cls.edge = address("900 Edge Rd", "35.3500", "-84.6000", "Bradley")
        cls.cohutta = address("400 Made Up Ln", "34.9600", "-84.9500", "Whitfield", state="GA", approved_out_of_area=True)

    def quote(self, address, **inputs):
        # The pricebook loaded for the tests takes effect on the real date,
        # which is after TODAY from 2026-11-07 on, so name its version.
        return issue_quote(
            self.full_detail, self.crossover, size_variant=self.two_rows, condition_level=1,
            address=address, on=TODAY, version=PricebookVersion.current(), **inputs,
        )

    def test_a_cleveland_quote(self):
        quote = self.quote(self.cleveland)
        self.assertEqual(quote.taxable_amount, quote.total_before_tax)
        self.assertEqual((quote.state_rate, quote.local_rate, quote.tax_rate), (Decimal("7"), Decimal("2.75"), Decimal("9.75")))
        self.assertEqual(quote.state_tax, (quote.total_before_tax * Decimal("0.07")).quantize(Decimal("0.01")))
        self.assertEqual(quote.sales_tax, quote.state_tax + quote.local_tax)
        self.assertEqual(quote.total, quote.total_before_tax + quote.sales_tax)
        self.assertEqual(quote.tax_jurisdiction.name, "Cleveland")
        self.assertFalse(quote.tax_needs_check)

    def test_chattanooga_and_unincorporated_rates(self):
        self.assertEqual(self.quote(self.chattanooga).tax_rate, Decimal("9.25"))
        rural = self.quote(self.rural)
        self.assertEqual((rural.tax_jurisdiction.name, rural.tax_rate), ("Bradley County", Decimal("9.75")))

    def test_an_address_that_will_not_match_is_flagged_on_the_quote(self):
        quote = self.quote(self.edge)
        self.assertEqual((quote.tax_jurisdiction.name, quote.tax_rate), ("Bradley County", Decimal("9.75")))
        self.assertTrue(quote.tax_needs_check)

    def test_the_georgia_exception_has_no_tennessee_tax(self):
        quote = self.quote(self.cohutta)
        self.assertEqual((quote.tax_jurisdiction.name, quote.sales_tax), ("Georgia", Decimal("0.00")))
        self.assertEqual(quote.total, quote.total_before_tax)

    def test_a_quote_without_an_address_has_no_tax_yet(self):
        quote = self.quote(None)
        self.assertEqual((quote.sales_tax, quote.total), (Decimal("0.00"), quote.total_before_tax))

    def test_promotions_reduce_the_taxable_amount(self):
        promotion = Promotion.objects.create(name="Invented Twenty Off", kind=Promotion.Kind.AMOUNT_OFF, value=Decimal("20"))
        full = self.quote(self.cleveland)
        promoted = self.quote(self.cleveland, promotions=[promotion])
        self.assertEqual(promoted.taxable_amount, full.taxable_amount - Decimal("20.00"))
        self.assertEqual(promoted.state_tax, (promoted.taxable_amount * Decimal("0.07")).quantize(Decimal("0.01"), rounding="ROUND_HALF_UP"))
        self.assertEqual(promoted.local_tax, (promoted.taxable_amount * Decimal("0.0275")).quantize(Decimal("0.01"), rounding="ROUND_HALF_UP"))

    def test_tips_stay_out_of_the_taxable_amount(self):
        appointment = booking.book(self.customer, self.vehicle, local(TODAY), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1), address=self.cleveland)
        before = tax_line_for_appointment(appointment)
        Payment.objects.create(appointment=appointment, method="cash", amount=appointment.total_before_tax, tip=Decimal("40.00"), paid_at=timezone.now())
        after = tax_line_for_appointment(appointment)
        self.assertEqual(after.taxable_amount, appointment.total_before_tax)
        self.assertEqual(after.sales_tax, before.sales_tax)
        self.assertEqual(appointment.quote.sales_tax, before.sales_tax)

    def test_each_part_is_rounded_to_the_cent_half_up(self):
        line = tax_line(self.cleveland, Decimal("10.10"), TODAY)
        # 10.10 x 7% = 0.707 -> 0.71; 10.10 x 2.75% = 0.27775 -> 0.28.
        self.assertEqual((line.state_tax, line.local_tax, line.sales_tax), (Decimal("0.71"), Decimal("0.28"), Decimal("0.99")))

    def test_the_business_location_rule_uses_the_home_base_rate(self):
        settings = LocationSettings.get()
        settings.home_state, settings.home_latitude, settings.home_longitude = "TN", Decimal("35.05"), Decimal("-85.30")
        settings.tax_sourcing = LocationSettings.TaxSourcing.BUSINESS_LOCATION
        settings.save()
        line = tax_line(self.cohutta, Decimal("100.00"), TODAY)
        self.assertEqual((line.jurisdiction.name, line.rate), ("Chattanooga", Decimal("9.250")))

    def test_the_rate_in_effect_on_the_day_of_service(self):
        cleveland = TaxJurisdiction.objects.get(code="0601")
        tax_rates.apply([tax_rates.Row("0601", "Bradley", "Cleveland", Decimal("3.00"))], mode="check", today=TODAY)
        tax_rates.approve_rate(TaxRate.objects.get(jurisdiction=cleveland, approved_at__isnull=True), datetime.date(2027, 1, 1))
        self.assertEqual(tax_line(self.cleveland, Decimal("100"), datetime.date(2026, 12, 31)).local_tax, Decimal("2.75"))
        self.assertEqual(tax_line(self.cleveland, Decimal("100"), datetime.date(2027, 1, 1)).local_tax, Decimal("3.00"))
