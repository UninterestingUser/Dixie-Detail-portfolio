"""The address form, the location settings screen and the sales tax screen."""

import datetime
from decimal import Decimal

from django.urls import reverse

from billing import tax_rates
from billing.models import TaxRate
from geo.fixtures import FakeServices, import_fixture_rates, with_google_key
from geo.models import LocationSettings

from .fixtures import JobsTestCase, open_day


class LocationScreensTestCase(JobsTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        import_fixture_rates()

    def address_data(self, **changes):
        data = {"line1": "100 Example St NW", "line2": "", "city": "Cleveland", "state": "tn", "zip_code": "37311",
                "notes": "", "active": "on", "by_hand": "", "location": "", "hand_county": ""}
        data.update(changes)
        return data


class AddressFormTests(LocationScreensTestCase):
    def post(self, data, pk=None):
        url = reverse("address-edit", args=[pk]) if pk else reverse("address-new", args=[self.customer.pk])
        fake = FakeServices(
            census={"100 Example St NW": "census_cleveland.json"},
            searches={"410 Newbuild Way NE": "search_new_street.json", "412 Newbuild Way NE": "search_new_street.json"},
            places={"ChIJmadeUpNewbuild00001": "place_new_street.json"},
        )
        with fake.patch():
            return self.client.post(url, data, follow=True)

    def test_a_typed_address_is_verified_with_the_census_geocoder(self):
        response = self.post(self.address_data())
        address = self.customer.addresses.get(line1="100 Example St NW")
        self.assertEqual((address.verification, address.state, address.county), ("census", "TN", "Bradley"))
        self.assertEqual(address.tax_jurisdiction.name, "Cleveland")
        self.assertContains(response, "Verified (Census geocoder), Bradley County, tax: Cleveland, Bradley County")

    @with_google_key
    def test_an_address_the_census_map_lacks_is_matched_by_google(self):
        response = self.post(self.address_data(line1="410 Newbuild Way NE", zip_code="37312"))
        address = self.customer.addresses.get(line1="410 Newbuild Way NE")
        self.assertEqual((address.verification, address.tax_jurisdiction.name), ("google_search", "Cleveland"))
        self.assertContains(response, "Verified (Google address search), Bradley County, tax: Cleveland")

    @with_google_key
    def test_an_address_neither_finds_is_not_saved_until_its_location_is_set_by_hand(self):
        data = self.address_data(line1="412 Newbuild Way NE", zip_code="37312")
        response = self.post(data)
        self.assertContains(response, "Neither the Census geocoder nor Google found this address "
                                      "(Google&#x27;s best match has a different house number)")
        self.assertFalse(self.customer.addresses.filter(line1="412 Newbuild Way NE").exists())
        response = self.post({**data, "by_hand": "on"})
        self.assertContains(response, "Paste the latitude and longitude from Google Maps")
        response = self.post({**data, "by_hand": "on", "location": "-84.86, 35.18"})
        self.assertContains(response, "That point is not in the United States")
        response = self.post({**data, "by_hand": "on", "location": "35.18, -84.86"})
        address = self.customer.addresses.get(line1="412 Newbuild Way NE")
        self.assertEqual((address.verification, address.verified_by, address.tax_jurisdiction.name, address.tax_needs_check),
                         ("by_hand", self.owner_user, "Cleveland", False))
        self.assertEqual(address.county, "Bradley")
        self.assertEqual(address.history.first().history_user, self.owner_user)
        self.assertEqual(address.history.first().history_change_reason, "Location set by hand in the control app")
        self.assertContains(response, "location set by hand by")
        # Editing it again shows the location it was given.
        form = self.client.get(reverse("address-edit", args=[address.pk]))
        self.assertContains(form, 'value="35.180000, -84.860000"')

    def test_without_a_google_key_the_message_says_so(self):
        response = self.post(self.address_data(line1="12 New Street"))
        self.assertContains(response, "Google not asked: no Google Maps server key")

    def test_only_a_manager_approves_an_out_of_area_address(self):
        self.client.force_login(self.helper_user)
        self.post(self.address_data(approved_out_of_area="on"))
        self.assertFalse(self.customer.addresses.get(line1="100 Example St NW").approved_out_of_area)


class LocationSettingsTests(LocationScreensTestCase):
    def settings_data(self, **changes):
        data = {"home_line1": "100 Example St NW", "home_city": "Cleveland", "home_state": "TN", "home_zip_code": "37311",
                "home_latitude": "", "home_longitude": "", "place_details_daily_cap": "300", "place_details_public_daily_cap": "250", "text_search_daily_cap": "300", "routes_daily_cap": "150",
                "estimate_road_factor": "1.30", "estimate_speed_mph": "40", "drive_time_cache_days": "30",
                "tax_sourcing": "service_address"}
        data.update(changes)
        return data

    def test_the_home_base_is_looked_up_and_saved_in_the_database(self):
        with FakeServices(census={"100 Example St NW": "census_cleveland.json"}).patch():
            self.client.post(reverse("location-settings"), self.settings_data())
        self.assertEqual(LocationSettings.get().home, (Decimal("35.161200"), Decimal("-84.877000")))
        self.assertEqual(LocationSettings.get().history.count(), 2)

    def test_only_managers_see_the_settings(self):
        self.client.force_login(self.helper_user)
        self.assertEqual(self.client.get(reverse("location-settings")).status_code, 403)

    def test_a_booking_records_the_drive_from_home(self):
        settings = LocationSettings.get()
        settings.home_latitude, settings.home_longitude = Decimal("35.100000"), Decimal("-84.900000")
        settings.save()
        self.address.latitude, self.address.longitude = Decimal("35.161200"), Decimal("-84.877000")
        self.address.save()
        day = open_day(10)
        self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(day))
        appointment = self.customer.appointments.get()
        self.assertEqual((appointment.drive_minutes, appointment.drive_estimated), (9, True))
        self.assertContains(self.client.get(reverse("appointment", args=[appointment.pk])), "Estimated")


class SalesTaxScreenTests(LocationScreensTestCase):
    def setUp(self):
        super().setUp()
        tax_rates.apply([tax_rates.Row("0601", "Bradley", "Cleveland", Decimal("3.00"))], mode="check")
        self.pending = TaxRate.objects.get(approved_at__isnull=True)

    def test_the_screen_lists_rates_and_waiting_changes(self):
        response = self.client.get(reverse("sales-tax"))
        self.assertContains(response, "Cleveland")
        self.assertContains(response, "the state shows 7% state + 3% local = 10%")
        self.assertContains(response, "Georgia")

    def test_a_manager_approves_a_change(self):
        start = datetime.date.today() + datetime.timedelta(days=30)
        self.client.post(reverse("rate-approve", args=[self.pending.pk]), {f"r{self.pending.pk}-effective_from": start.isoformat()})
        self.pending.refresh_from_db()
        self.assertIsNotNone(self.pending.approved_at)
        self.assertEqual((self.pending.effective_from, self.pending.approved_by), (start, self.owner_user))

    def test_a_helper_cannot_approve(self):
        self.client.force_login(self.helper_user)
        response = self.client.post(reverse("rate-approve", args=[self.pending.pk]), {f"r{self.pending.pk}-effective_from": "2027-01-01"})
        self.assertEqual(response.status_code, 403)

    def test_the_job_screen_shows_the_tax_line(self):
        self.address.latitude, self.address.longitude, self.address.county = Decimal("35.161200"), Decimal("-84.877000"), "Bradley"
        self.address.save()
        day = open_day(10)
        self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(day))
        response = self.client.get(reverse("appointment", args=[self.customer.appointments.get().pk]))
        self.assertContains(response, "Sales tax, Cleveland (9.75%)")
