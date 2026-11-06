"""Verified addresses, the service area and drive times, with the outside
services replaced by geo.fixtures.FakeServices (no network)."""

import datetime
import io
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from customers.models import Address, Customer
from geo import drive, google, service_area
from geo.fixtures import MADE_UP_KEY, FakeServices, import_fixture_rates, with_google_key
from geo.models import ApiUsage, DriveTime, LocationSettings
from geo.verification import VerificationError, address_from_place, verify_by_hand, verify_with_census


class AddressTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        import_fixture_rates()
        cls.customer = Customer.objects.create(first_name="Pat", last_name="Example", mobile="4235550101")

    def typed(self, line1, city="Cleveland", state="TN", zip_code="37311", **fields):
        return Address(customer=self.customer, line1=line1, city=city, state=state, zip_code=zip_code, **fields)


class CensusTests(AddressTestCase):
    """An address the owner types is checked with the Census geocoder."""

    def test_a_cleveland_address(self):
        address = self.typed("100 Example St NW")
        with FakeServices(census={"100 Example St NW": "census_cleveland.json"}).patch():
            self.assertTrue(verify_with_census(address))
        address.save()
        address.refresh_from_db()
        self.assertEqual(address.verification, Address.Verification.CENSUS)
        self.assertEqual((address.latitude, address.longitude), (Decimal("35.161200"), Decimal("-84.877000")))
        self.assertEqual(address.county, "Bradley")
        self.assertEqual(address.tax_jurisdiction.name, "Cleveland")
        self.assertFalse(address.tax_needs_check)
        self.assertTrue(service_area.check(address).in_area)
        self.assertEqual(ApiUsage.objects.get(api=ApiUsage.Api.CENSUS_GEOCODER).calls, 1)

    def test_an_unincorporated_county_address(self):
        address = self.typed("300 Pretend Rd SE", zip_code="37323")
        with FakeServices(census={"300 Pretend Rd SE": "census_rural_bradley.json"}).patch():
            self.assertTrue(verify_with_census(address))
        self.assertEqual(address.tax_jurisdiction.name, "Bradley County")
        self.assertEqual(address.tax_jurisdiction.kind, "county")
        self.assertFalse(address.tax_needs_check)

    def test_an_address_the_geocoder_cannot_find(self):
        address = self.typed("1 Nowhere Ln")
        with FakeServices().patch():
            self.assertFalse(verify_with_census(address))
        self.assertFalse(address.verified)
        self.assertIsNone(address.point)

    def test_an_address_that_will_not_match_a_boundary_takes_its_county_rate_and_is_flagged(self):
        address = self.typed("900 Edge Rd", city="Charleston", zip_code="37310")
        with FakeServices(census={"900 Edge Rd": "census_edge_of_bradley.json"}).patch():
            self.assertTrue(verify_with_census(address))
        self.assertEqual(address.tax_jurisdiction.name, "Bradley County")
        self.assertTrue(address.tax_needs_check)
        self.assertIn("did not match a tax rate boundary", address.tax_note)

    def test_changing_a_verified_address_clears_its_verification(self):
        address = self.typed("100 Example St NW")
        with FakeServices(census={"100 Example St NW": "census_cleveland.json"}).patch():
            verify_with_census(address)
        address.save()
        address.line1 = "102 Example St NW"
        address.save()
        address.refresh_from_db()
        self.assertFalse(address.verified)
        self.assertIsNone(address.tax_jurisdiction)

    def test_verified_by_hand_without_coordinates_takes_the_county_rate(self):
        address = verify_by_hand(self.typed("12 New Street"), county="bradley")
        self.assertEqual(address.verification, Address.Verification.BY_HAND)
        self.assertEqual(address.county, "Bradley")
        self.assertEqual(address.tax_jurisdiction.name, "Bradley County")
        self.assertTrue(address.tax_needs_check)
        self.assertIn("has no map coordinates", address.tax_note)


@with_google_key
class GooglePlaceTests(AddressTestCase):
    """A website address arrives as a place ID; the server looks it up itself."""

    def place(self, place_id, file_name, token="a1b2c3d4-0000-4000-8000-000000000001"):
        fake = FakeServices(places={place_id: file_name})
        with fake.patch():
            address = address_from_place(self.customer, place_id, token)
        return address, fake

    def test_a_chattanooga_place(self):
        address, fake = self.place("ChIJmadeUpChattanooga01", "place_chattanooga.json")
        self.assertEqual(
            (address.line1, address.city, address.state, address.zip_code, address.county),
            ("200 Sample Ave", "Chattanooga", "TN", "37402", "Hamilton"),
        )
        self.assertEqual(address.verification, Address.Verification.GOOGLE_PLACE)
        self.assertEqual(address.google_place_id, "ChIJmadeUpChattanooga01")
        self.assertEqual(address.tax_jurisdiction.name, "Chattanooga")
        self.assertTrue(service_area.check(address).in_area)

    def test_the_lookup_asks_only_for_essentials_fields_and_ends_the_session(self):
        _, fake = self.place("ChIJmadeUpCleveland0001", "place_cleveland.json")
        [(url, kwargs)] = fake.urls("https://places.googleapis.com/")
        self.assertEqual(kwargs["headers"]["X-Goog-FieldMask"], "addressComponents,formattedAddress,location")
        self.assertNotIn("displayName", kwargs["headers"]["X-Goog-FieldMask"])
        self.assertEqual(kwargs["params"]["sessionToken"], "a1b2c3d4-0000-4000-8000-000000000001")
        # The key goes in a header, never in the URL.
        self.assertEqual(kwargs["headers"]["X-Goog-Api-Key"], MADE_UP_KEY)
        self.assertNotIn(MADE_UP_KEY, url)
        self.assertEqual(ApiUsage.objects.get(api=ApiUsage.Api.PLACE_DETAILS).calls, 1)

    def test_only_a_street_address_is_accepted(self):
        with self.assertRaises(VerificationError):
            self.place("ChIJmadeUpTownOnly00001", "place_town_only.json")

    def test_anything_but_a_place_id_is_refused_before_calling_google(self):
        fake = FakeServices()
        with fake.patch(), self.assertRaises(ValueError):
            address_from_place(self.customer, "../places/other?x=1")
        self.assertEqual(fake.calls, [])

    def test_the_georgia_exception(self):
        address, _ = self.place("ChIJmadeUpCohutta000001", "place_cohutta.json")
        self.assertEqual((address.state, address.county), ("GA", "Whitfield"))
        self.assertFalse(service_area.check(address).in_area)
        address.approved_out_of_area = True
        self.assertTrue(service_area.check(address).in_area)
        self.assertEqual(address.tax_jurisdiction.name, "Georgia")
        self.assertFalse(address.tax_needs_check)

    def test_an_address_outside_the_area(self):
        address, _ = self.place("ChIJmadeUpKnoxville0001", "place_knoxville.json")
        area = service_area.check(address)
        self.assertFalse(area.in_area)
        self.assertEqual(area.reason, "Knox County is outside the service area")
        # It has no boundary here, so if the owner approved it, it would take
        # Knox County's rate and be flagged.
        self.assertEqual(address.tax_jurisdiction.name, "Knox County")
        self.assertTrue(address.tax_needs_check)

    def test_the_daily_cap_stops_the_calls(self):
        settings = LocationSettings.get()
        settings.place_details_daily_cap = 1
        settings.save()
        self.place("ChIJmadeUpCleveland0001", "place_cleveland.json")
        with self.assertRaises(google.CapReached):
            self.place("ChIJmadeUpCleveland0001", "place_cleveland.json")
        usage = ApiUsage.objects.get(api=ApiUsage.Api.PLACE_DETAILS)
        self.assertEqual((usage.calls, usage.refused), (1, 1))

    def test_without_a_key_google_is_not_called(self):
        fake = FakeServices(places={"ChIJmadeUpCleveland0001": "place_cleveland.json"})
        with self.settings(GOOGLE_MAPS_SERVER_KEY=""), fake.patch(), self.assertRaises(google.GoogleUnavailable):
            address_from_place(self.customer, "ChIJmadeUpCleveland0001")
        self.assertEqual(fake.calls, [])


class VerifyAddressesCommandTests(AddressTestCase):
    def setUp(self):
        self.matched = Address.objects.create(customer=self.customer, line1="100 Example St NW", city="Cleveland", state="TN", zip_code="37311")
        self.unmatched = Address.objects.create(customer=self.customer, line1="1 Nowhere Ln", city="Cleveland", state="TN", zip_code="37311")

    def run_command(self, *args):
        out = io.StringIO()
        with FakeServices(census={"100 Example St NW": "census_cleveland.json"}).patch():
            call_command("verify_addresses", *args, "--pause", "0", stdout=out)
        return out.getvalue()

    def test_dry_run_reports_by_id_and_changes_nothing(self):
        out = self.run_command("--dry-run")
        self.assertIn(f"customer {self.customer.pk} address {self.matched.pk}: matched (Bradley County; tax: Cleveland)", out)
        self.assertIn(f"customer {self.customer.pk} address {self.unmatched.pk}: unmatched", out)
        self.assertIn("1 matched, 1 unmatched", out)
        for private in ("Pat", "Example St", "Nowhere"):
            self.assertNotIn(private, out)
        self.matched.refresh_from_db()
        self.assertFalse(self.matched.verified)

    def test_a_real_run_stores_the_verification(self):
        self.run_command()
        self.matched.refresh_from_db()
        self.assertEqual(self.matched.verification, Address.Verification.CENSUS)
        self.assertEqual(self.matched.tax_jurisdiction.name, "Cleveland")
        self.assertFalse(Address.objects.get(pk=self.unmatched.pk).verified)


class DriveTimeTests(TestCase):
    home = (Decimal("35.100000"), Decimal("-84.900000"))
    job = (Decimal("35.161200"), Decimal("-84.877000"))

    def departure(self, hour=8):
        day = timezone.localdate() + datetime.timedelta(days=3)
        return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour)))

    def test_without_google_the_drive_time_is_estimated_and_not_cached(self):
        result = drive.drive_time(self.home, self.job, self.departure())
        self.assertTrue(result.estimated)
        self.assertEqual(result.source, "estimate")
        # About 4.4 straight-line miles, times 1.3, at 40 mph.
        self.assertEqual(result.minutes, 9)
        self.assertFalse(DriveTime.objects.exists())

    @with_google_key
    def test_google_answers_are_cached_by_pair_and_hour(self):
        fake = FakeServices()
        with fake.patch():
            first = drive.drive_time(self.home, self.job, self.departure(8))
            again = drive.drive_time(self.home, self.job, self.departure(8) + datetime.timedelta(minutes=30))
            later = drive.drive_time(self.home, self.job, self.departure(15))
        self.assertEqual((first.minutes, first.source, first.estimated), (33, "google", False))
        self.assertEqual(again.source, "cache")
        self.assertEqual(later.source, "google")
        self.assertEqual(len(fake.urls("https://routes.googleapis.com/")), 2)
        self.assertEqual(ApiUsage.objects.get(api=ApiUsage.Api.ROUTES).calls, 2)
        body = fake.urls("https://routes.googleapis.com/")[0][1]["body"]
        self.assertEqual(body["routingPreference"], "TRAFFIC_AWARE")
        self.assertIn("departureTime", body)

    @with_google_key
    def test_google_unreachable_falls_back_to_the_estimate(self):
        with FakeServices(routes=None).patch():
            result = drive.drive_time(self.home, self.job, self.departure())
        self.assertTrue(result.estimated)
        self.assertFalse(DriveTime.objects.exists())

    @with_google_key
    def test_past_the_cap_the_drive_time_is_estimated(self):
        settings = LocationSettings.get()
        settings.routes_daily_cap = 0
        settings.save()
        fake = FakeServices()
        with fake.patch():
            result = drive.drive_time(self.home, self.job, self.departure())
        self.assertTrue(result.estimated)
        self.assertEqual(fake.calls, [])
        self.assertEqual(ApiUsage.objects.get(api=ApiUsage.Api.ROUTES).refused, 1)

    def test_drive_from_home_needs_a_home_base(self):
        address = Address(line1="x", city="y", state="TN", zip_code="1", latitude=self.job[0], longitude=self.job[1])
        self.assertIsNone(drive.drive_from_home(address, self.departure()))
        settings = LocationSettings.get()
        settings.home_latitude, settings.home_longitude = self.home
        settings.save()
        self.assertEqual(drive.drive_from_home(address, self.departure()).minutes, 9)
