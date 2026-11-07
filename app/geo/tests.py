"""Verified addresses, the service area and drive times, with the outside
services replaced by geo.fixtures.FakeServices (no network)."""

import datetime
import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from customers.models import Address, Customer
from geo import drive, google, service_area
from geo.fixtures import MADE_UP_KEY, FakeServices, import_fixture_rates, with_google_key
from geo.models import ApiUsage, DriveTime, LocationSettings
from geo.verification import (
    VerificationError, address_from_place, parse_location, split_line1, street_key, verify_by_hand,
    verify_typed, verify_with_census,
)

NEW_STREET = "410 Newbuild Way NE"


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


@with_google_key
class GoogleSearchTests(AddressTestCase):
    """A typed address the Census map does not have, such as a street in a
    new neighborhood, is searched with Google; the match is used only if it
    agrees with the typed address."""

    def verify(self, address, searches=None, places=None):
        fake = FakeServices(
            searches={NEW_STREET: "search_new_street.json"} if searches is None else searches,
            places={"ChIJmadeUpNewbuild00001": "place_new_street.json"} if places is None else places,
        )
        with fake.patch():
            outcome = verify_typed(address)
        return outcome, fake

    def test_a_new_street_is_matched_by_google(self):
        address = self.typed("410 Newbuild Way Northeast", zip_code="37312")
        outcome, fake = self.verify(address, searches={"410 Newbuild Way Northeast": "search_new_street.json"})
        self.assertEqual((outcome.method, outcome.reason), ("google_search", ""))
        address.save()
        address.refresh_from_db()
        self.assertEqual(address.verification, Address.Verification.GOOGLE_SEARCH)
        self.assertEqual((address.latitude, address.longitude), (Decimal("35.180000"), Decimal("-84.860000")))
        self.assertEqual(address.google_place_id, "ChIJmadeUpNewbuild00001")
        # The tax comes from the location and the boundaries, as usual.
        self.assertEqual((address.county, address.tax_jurisdiction.name, address.tax_needs_check), ("Bradley", "Cleveland", False))
        # The owner's own spelling is kept.
        self.assertEqual((address.line1, address.zip_code), ("410 Newbuild Way Northeast", "37312"))
        self.assertTrue(fake.urls("https://geocoding.geo.census.gov/"))

    def test_the_calls_ask_for_the_fewest_fields_and_are_counted(self):
        _, fake = self.verify(self.typed(NEW_STREET, zip_code="37312"))
        [(_, search)] = fake.urls("https://places.googleapis.com/v1/places:searchText")
        self.assertEqual(search["headers"]["X-Goog-FieldMask"], "places.id")
        self.assertEqual(search["body"]["textQuery"], "410 Newbuild Way NE, Cleveland, TN 37312")
        self.assertEqual(search["headers"]["X-Goog-Api-Key"], MADE_UP_KEY)
        [(_, details)] = fake.urls("https://places.googleapis.com/v1/places/")
        self.assertEqual(details["headers"]["X-Goog-FieldMask"], "addressComponents,formattedAddress,location")
        self.assertNotIn("sessionToken", details["params"])
        self.assertEqual(ApiUsage.objects.get(api=ApiUsage.Api.TEXT_SEARCH).calls, 1)
        self.assertEqual(ApiUsage.objects.get(api=ApiUsage.Api.PLACE_DETAILS).calls, 1)

    def test_a_different_house_number_leaves_the_address_unmatched(self):
        address = self.typed("412 Newbuild Way NE", zip_code="37312")
        outcome, _ = self.verify(address, searches={"412 Newbuild Way NE": "search_new_street.json"})
        self.assertFalse(outcome.matched)
        self.assertEqual(outcome.reason, "Google's best match has a different house number")
        self.assertFalse(address.verified)
        self.assertIsNone(address.point)

    def test_a_different_street_or_zip_code_leaves_the_address_unmatched(self):
        address = self.typed("410 Newbuild Ct NE", zip_code="37311")
        outcome, _ = self.verify(address, searches={"410 Newbuild Ct NE": "search_new_street.json"})
        self.assertEqual(outcome.reason, "Google's best match has a different street and ZIP code")
        self.assertFalse(address.verified)

    def test_a_match_that_is_not_a_street_address_is_not_used(self):
        address = self.typed(NEW_STREET, zip_code="37312")
        outcome, _ = self.verify(address, places={"ChIJmadeUpNewbuild00001": "place_town_only.json"})
        self.assertEqual(outcome.reason, "Google's best match is not a street address")
        self.assertFalse(address.verified)

    def test_nothing_found_by_google(self):
        address = self.typed("1 Nowhere Ln")
        outcome, fake = self.verify(address)
        self.assertEqual(outcome.reason, "Google found no match")
        self.assertFalse(fake.urls("https://places.googleapis.com/v1/places/"))

    def test_without_a_key_google_is_not_asked(self):
        address = self.typed(NEW_STREET, zip_code="37312")
        with self.settings(GOOGLE_MAPS_SERVER_KEY=""):
            outcome, fake = self.verify(address)
        self.assertTrue(outcome.google_off)
        self.assertIn("Google not asked: no Google Maps server key", outcome.reason)
        self.assertFalse(fake.urls("https://places.googleapis.com/"))

    def test_the_text_search_cap(self):
        settings = LocationSettings.get()
        settings.text_search_daily_cap = 0
        settings.save()
        outcome, fake = self.verify(self.typed(NEW_STREET, zip_code="37312"))
        self.assertTrue(outcome.google_off)
        self.assertIn("reached today's cap of 0 calls", outcome.reason)
        self.assertFalse(fake.urls("https://places.googleapis.com/"))
        self.assertEqual(ApiUsage.objects.get(api=ApiUsage.Api.TEXT_SEARCH).refused, 1)

    def test_a_census_match_does_not_ask_google(self):
        fake = FakeServices(census={"100 Example St NW": "census_cleveland.json"})
        with fake.patch():
            outcome = verify_typed(self.typed("100 Example St NW"))
        self.assertEqual(outcome.method, "census")
        self.assertFalse(fake.urls("https://places.googleapis.com/"))

    def test_streets_are_compared_in_one_form(self):
        self.assertEqual(street_key("Pretend Rd SE"), street_key("Pretend Road Southeast"))
        self.assertEqual(street_key("N. First Street"), street_key("N 1st St"))
        self.assertEqual(split_line1("410 Newbuild Way NE Apt 2"), ("410", "NEWBUILD WAY NE"))
        self.assertEqual(split_line1("410 Newbuild Way NE #2"), ("410", "NEWBUILD WAY NE"))
        self.assertEqual(split_line1("Newbuild Way"), ("", "NEWBUILD WAY"))


class ByHandTests(AddressTestCase):
    """The owner pastes the location from Google Maps for an address neither
    the Census geocoder nor Google can find."""

    def test_pasted_locations(self):
        self.assertEqual(parse_location("35.18, -84.86"), (Decimal("35.180000"), Decimal("-84.860000")))
        self.assertEqual(parse_location(" (35.1812345, -84.8601234) "), (Decimal("35.181235"), Decimal("-84.860123")))
        self.assertEqual(parse_location("35.18 -84.86"), (Decimal("35.180000"), Decimal("-84.860000")))
        for wrong in ("", "Cleveland", "35.18", "-84.86, 35.18", "135.1, -84.8", "35.18, 84.86"):
            with self.subTest(wrong=wrong), self.assertRaises(VerificationError):
                parse_location(wrong)

    def test_the_location_sets_the_tax_and_records_who_set_it(self):
        owner = get_user_model().objects.create_user("owner-example")
        address = verify_by_hand(self.typed(NEW_STREET, zip_code="37312"), Decimal("35.18"), Decimal("-84.86"), user=owner)
        address.save()
        address.refresh_from_db()
        self.assertEqual((address.verification, address.verified_by), (Address.Verification.BY_HAND, owner))
        self.assertEqual((address.county, address.tax_jurisdiction.name, address.tax_needs_check), ("Bradley", "Cleveland", False))
        self.assertTrue(service_area.check(address).in_area)

    def test_outside_tennessee_the_county_given_is_used(self):
        address = verify_by_hand(
            self.typed("5 Sample Ln", city="Cohutta", state="GA", zip_code="30710"),
            Decimal("34.96"), Decimal("-84.95"), county="whitfield",
        )
        self.assertEqual((address.county, address.tax_jurisdiction.name), ("Whitfield", "Georgia"))

    def test_coordinates_are_needed(self):
        with self.assertRaises(VerificationError):
            verify_by_hand(self.typed(NEW_STREET), None, None)

    def test_a_later_census_match_clears_who_set_it(self):
        owner = get_user_model().objects.create_user("owner-example")
        address = verify_by_hand(self.typed("100 Example St NW"), Decimal("35.16"), Decimal("-84.87"), user=owner)
        with FakeServices(census={"100 Example St NW": "census_cleveland.json"}).patch():
            verify_with_census(address)
        self.assertIsNone(address.verified_by)


@with_google_key
class VerifyAddressesCommandTests(AddressTestCase):
    def setUp(self):
        def create(line1, zip_code="37311", **fields):
            return Address.objects.create(customer=self.customer, line1=line1, city="Cleveland", state="TN", zip_code=zip_code, **fields)

        self.census = create("100 Example St NW")
        self.google = create(NEW_STREET, zip_code="37312")
        self.unmatched = create("412 Newbuild Way NE", zip_code="37312")
        self.by_hand = create("9 Fresh Paint Ct", verification="by_hand", latitude=Decimal("35.18"), longitude=Decimal("-84.86"),
                              county="Bradley")

    def run_command(self, *args):
        out = io.StringIO()
        fake = FakeServices(
            census={"100 Example St NW": "census_cleveland.json"},
            searches={NEW_STREET: "search_new_street.json", "412 Newbuild Way NE": "search_new_street.json"},
            places={"ChIJmadeUpNewbuild00001": "place_new_street.json"},
        )
        with fake.patch():
            call_command("verify_addresses", *args, "--pause", "0", stdout=out)
        return out.getvalue()

    def test_dry_run_reports_how_each_address_matched_by_id_and_changes_nothing(self):
        out = self.run_command("--dry-run")
        where = f"customer {self.customer.pk} address"
        self.assertIn(f"{where} {self.census.pk}: matched by Census (Bradley County; tax: Cleveland)", out)
        self.assertIn(f"{where} {self.google.pk}: matched by Google (Bradley County; tax: Cleveland)", out)
        self.assertIn(f"{where} {self.unmatched.pk}: unmatched (Google's best match has a different house number)", out)
        self.assertIn(f"{where} {self.by_hand.pk}: set by hand, kept (Bradley County)", out)
        self.assertIn("1 by Census, 1 by Google, 1 set by hand, 1 unmatched, 0 not checked", out)
        for private in ("Pat", "Example St", "Newbuild", "Fresh Paint"):
            self.assertNotIn(private, out)
        self.census.refresh_from_db()
        self.google.refresh_from_db()
        self.assertFalse(self.census.verified or self.google.verified)

    def test_a_real_run_stores_the_verification(self):
        self.run_command()
        self.census.refresh_from_db()
        self.google.refresh_from_db()
        self.assertEqual((self.census.verification, self.census.tax_jurisdiction.name), ("census", "Cleveland"))
        self.assertEqual((self.google.verification, self.google.tax_jurisdiction.name), ("google_search", "Cleveland"))
        self.assertEqual(self.google.history.first().history_change_reason, "Verified with a Google address search (verify_addresses)")
        self.assertFalse(Address.objects.get(pk=self.unmatched.pk).verified)

    def test_by_hand_without_a_location_is_checked(self):
        self.census.verification = "by_hand"
        self.census.save()
        self.run_command()
        self.census.refresh_from_db()
        self.assertEqual((self.census.verification, self.census.tax_jurisdiction.name), ("census", "Cleveland"))

    def test_all_never_replaces_a_location_set_by_hand(self):
        self.run_command("--all")
        self.by_hand.refresh_from_db()
        self.assertEqual((self.by_hand.verification, self.by_hand.latitude), ("by_hand", Decimal("35.180000")))

    def test_no_google(self):
        out = self.run_command("--dry-run", "--no-google")
        self.assertIn(f"address {self.google.pk}: unmatched (the Census geocoder found no match)", out)

    def test_once_google_cannot_be_asked_the_run_stops_asking(self):
        settings = LocationSettings.get()
        settings.text_search_daily_cap = 0
        settings.save()
        out = self.run_command("--dry-run")
        self.assertEqual(out.count("the rest of this run uses the Census geocoder only"), 1)
        self.assertIn(f"address {self.unmatched.pk}: unmatched (the Census geocoder found no match)", out)
        self.assertEqual(ApiUsage.objects.get(api=ApiUsage.Api.TEXT_SEARCH).refused, 1)


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
