"""Booking through the public API: the quote booked as issued, consent,
the Turnstile check, an expired or changed quote, a taken time, the
double-booking race, test numbers, and that no customer data leaks."""

import datetime
import io
import threading
from unittest import mock

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings

from appointments.models import Appointment
from calendars.events import appointment_events
from customers.models import Address, Consent, Customer
from geo.fixtures import FakeServices, import_fixture_rates, with_google_key
from pricebook.models import PricebookVersion, PricedLine, Quote, Service
from publicapi.models import WebQuote
from vehicles.models import Vehicle, VehicleClass

from .consent import wording
from .testing import CLEVELAND, PLACES, ApiTestCase, PublicClient, add_model, booking_body, day_after, eastern, lookup_session, open_day, siteverify


class BookingTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.place_token = self.place()["place"]

    def book(self, quote=None, start=None, expect=201, **changes):
        quote = quote or self.quote(place=self.place_token, add_ons=[self.seats.pk])
        start = start or eastern(open_day(3), 8)
        response = self.client.post_json("bookings", self.booking_body(quote, start, **changes))
        self.assertEqual(response.status_code, expect, response.content)
        return quote, response.json()

    def test_a_booking_books_the_quote_as_issued(self):
        quote, answer = self.book()
        appointment = Appointment.objects.get(reference=answer["reference"])
        stored = Quote.objects.get(web__number=quote["number"])
        self.assertEqual(appointment.quote, stored)
        self.assertEqual(appointment.source, Appointment.Source.WEBSITE)
        self.assertEqual(appointment.status, Appointment.Status.BOOKED)
        self.assertEqual(appointment.preferred_payment_method, "cash")
        self.assertEqual(appointment.time_on_site_minutes, stored.time_on_site_minutes)
        copied = [[getattr(line, name) for name in PricedLine.COPIED_FIELDS] for line in appointment.lines.all()]
        quoted = [[getattr(line, name) for name in PricedLine.COPIED_FIELDS] for line in stored.lines.all()]
        self.assertEqual(copied, quoted)
        self.assertEqual(appointment.scheduled_start, eastern(open_day(3), 8))
        self.assertFalse(appointment.is_test)

    def test_a_new_customer_vehicle_and_address(self):
        _, answer = self.book()
        appointment = Appointment.objects.get(reference=answer["reference"])
        customer = appointment.customer
        self.assertEqual((customer.first_name, customer.last_name, customer.mobile), ("Jordan", "Sample", "4235550142"))
        self.assertEqual(customer.source, "Website")
        self.assertEqual(appointment.vehicle.color, "silver")
        self.assertEqual((appointment.vehicle.year, appointment.vehicle.make, appointment.vehicle.model), (2019, "Toyota", "RAV4"))
        self.assertEqual(appointment.vehicle.vehicle_model, self.rav4)
        self.assertEqual(appointment.vehicle.vehicle_class, self.medium)
        address = appointment.service_address
        self.assertEqual(address.customer, customer)
        self.assertEqual(address.verification, Address.Verification.GOOGLE_PLACE)
        self.assertEqual(address.tax_jurisdiction.name, "Cleveland")
        # A second booking from the same number matches the customer quietly.
        self.book(start=eastern(day_after(open_day(3)), 8))
        self.assertEqual(Customer.objects.filter(mobile="4235550142").count(), 1)

    def test_consent_records_the_exact_wording_the_time_and_the_source(self):
        _, answer = self.book()
        customer = Appointment.objects.get(reference=answer["reference"]).customer
        # One consent, appointment texts, which now covers the review request
        # after the service (decision 0108).
        [row] = Consent.objects.filter(customer=customer)
        words = wording()["versions"]["2026-11-18"]
        self.assertEqual((row.kind, row.granted), (Consent.Kind.APPOINTMENT, True))
        self.assertEqual(row.wording, words["appointment"])
        self.assertIn("a review request after the service", row.wording)
        self.assertEqual(row.source, Consent.Source.WEB_FORM)
        self.assertEqual(row.wording_version, "2026-11-18")
        self.assertEqual(row.phone, "4235550142")
        self.assertIsNotNone(row.recorded_at)
        self.assertTrue(customer.has_consent(Consent.Kind.APPOINTMENT))

    def test_an_answer_with_the_old_follow_up_box_is_taken_and_only_appointment_consent_recorded(self):
        """An offline request held from the old page, or a page not rebuilt
        yet, sends version 2026-10-13 with two answers."""
        _, answer = self.book(consents={"version": "2026-10-13", "appointment": False, "follow_up": True})
        customer = Appointment.objects.get(reference=answer["reference"]).customer
        [row] = Consent.objects.filter(customer=customer)
        self.assertEqual((row.kind, row.granted, row.wording_version), (Consent.Kind.APPOINTMENT, False, "2026-10-13"))
        self.assertEqual(row.wording, wording()["versions"]["2026-10-13"]["appointment"])
        self.assertFalse(Consent.objects.filter(kind=Consent.Kind.FOLLOW_UP).exists())
        self.book(expect=400, consents={"version": "2026-11-18", "appointment": True, "follow_up": "yes"}, start=eastern(open_day(4), 8))

    def test_the_calendar_file_shows_the_total_with_a_dollar_sign(self):
        _, answer = self.book()
        content = answer["calendar_file"]["content"]
        self.assertIn(f"Total ${answer['summary']['total']} (confirmed when we see the vehicle)", content)
        self.assertNotIn("Total $ ", content)

    def test_an_unknown_consent_version_is_refused(self):
        self.book(expect=400, consents={"version": "1999-01-01", "appointment": True, "follow_up": True})
        self.assertFalse(Appointment.objects.exists())

    def test_the_answer_has_a_reference_summary_and_calendar_file(self):
        quote, answer = self.book()
        self.assertEqual(len(answer["reference"]), 8)
        summary = answer["summary"]
        self.assertEqual(summary["service"], "Full Detail")
        self.assertEqual(summary["add_ons"], ["Seat Extraction"])
        self.assertEqual(summary["vehicle"], "2019 Toyota RAV4")
        self.assertEqual(summary["address"], "100 Example St NW, Cleveland, TN 37311")
        self.assertEqual(summary["total"], quote["total"])
        self.assertTrue(summary["arrival"].endswith("at 8:00 AM"))
        ics = answer["calendar_file"]
        self.assertEqual(ics["content_type"], "text/calendar")
        self.assertIn("BEGIN:VEVENT", ics["content"])
        start = eastern(open_day(3), 8).astimezone(datetime.UTC)
        self.assertIn(f"DTSTART:{start:%Y%m%dT%H%M%SZ}", ics["content"])
        end = start + datetime.timedelta(minutes=quote["time_on_site_minutes"])
        self.assertIn(f"DTEND:{end:%Y%m%dT%H%M%SZ}", ics["content"])
        self.assertIn(f"UID:{answer['reference']}@dixiedetail.com", ics["content"])

    def test_a_failed_turnstile_check_books_nothing(self):
        _, answer = self.book(expect=403, turnstile="a-token-cloudflare-refuses")
        self.assertEqual(answer["error"], "turnstile_failed")
        self.assertFalse(Appointment.objects.exists())
        self.assertFalse(Customer.objects.exists())
        self.assertEqual(self.siteverify.call_args.args, ("a-token-cloudflare-refuses", "198.51.100.7"))

    def test_without_the_secret_key_nothing_is_booked(self):
        with override_settings(TURNSTILE_SECRET_KEY=""):
            _, answer = self.book(expect=403)
        self.assertEqual(answer["error"], "turnstile_failed")
        self.siteverify.assert_not_called()

    def test_an_expired_quote_returns_a_fresh_one_to_confirm(self):
        quote = self.quote(place=self.place_token)
        WebQuote.objects.filter(number=quote["number"]).update(expires_at=eastern(open_day(-10), 8))
        _, answer = self.book(quote, expect=409)
        self.assertEqual(answer["error"], "quote_expired")
        fresh = answer["quote"]
        self.assertNotEqual(fresh["number"], quote["number"])
        self.assertEqual(fresh["total"], quote["total"])
        self.assertEqual(fresh["vehicle"], quote["vehicle"])
        self.assertFalse(Appointment.objects.exists())
        # Never a silent new price: the fresh quote books only when sent.
        _, booked = self.book(fresh)
        self.assertEqual(Appointment.objects.get(reference=booked["reference"]).quote.web.number, fresh["number"])

    def test_a_quote_priced_differently_on_the_day_returns_a_fresh_one(self):
        quote = self.quote(place=self.place_token)
        day = open_day(5)
        PricebookVersion.new_draft().publish(day)
        _, answer = self.book(quote, eastern(day, 8), expect=409)
        self.assertEqual(answer["error"], "quote_changed")
        self.assertEqual(answer["quote"]["pricebook_version"], PricebookVersion.current(day).number)
        self.book(answer["quote"], eastern(day, 8))

    def test_a_quote_books_once(self):
        quote, _ = self.book()
        _, answer = self.book(quote, eastern(open_day(4), 8), expect=409)
        self.assertEqual(answer["error"], "quote_used")

    def test_a_taken_time_is_refused_without_saying_why(self):
        self.book()
        _, answer = self.book(expect=409)
        self.assertEqual(answer["error"], "time_taken")
        self.assertEqual(set(answer), {"error", "message"})
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 1)

    def test_a_time_not_offered_is_refused(self):
        _, answer = self.book(start=eastern(open_day(3), 13, 15), expect=409)
        self.assertEqual(answer["error"], "time_taken")

    def test_strict_input(self):
        self.assertEqual(self.book(expect=400, price="1.00")[1]["field"], "price")
        self.assertEqual(self.book(expect=400, payment_method="check")[1]["field"], "payment_method")
        self.assertEqual(self.book(expect=400, mobile="555-0142")[1]["field"], "mobile")
        self.assertEqual(self.book(expect=400, start="2026-12-08 08:00")[1]["field"], "start")
        self.assertEqual(self.book(expect=400, first_name="x" * 101)[1]["field"], "first_name")
        self.assertFalse(Appointment.objects.exists())

    def test_cash_app_is_saved_as_cash_app_pay_and_shown_as_cash_app(self):
        _, answer = self.book(payment_method="cash_app")
        appointment = Appointment.objects.get(reference=answer["reference"])
        self.assertEqual(appointment.preferred_payment_method, "cash_app_pay")
        self.assertEqual(answer["summary"]["payment_method"], "Cash App")
        # The two routes are for recording payments; a gift card and the
        # owner-only methods are never taken from the website.
        for method in ("gift_card", "trade"):
            self.assertEqual(self.book(expect=400, payment_method=method)[1]["field"], "payment_method")

    def test_a_number_on_the_test_list_makes_test_records(self):
        _, answer = self.book(mobile="(423) 555-0199")
        appointment = Appointment.objects.get(reference=answer["reference"])
        self.assertTrue(appointment.is_test)
        self.assertTrue(appointment.customer.is_test)
        # Kept off the Jobs calendar.
        self.assertEqual(appointment_events(appointment, 10), {})

    def test_no_response_shows_anything_from_a_customers_record(self):
        existing = Customer.objects.create(first_name="Robin", last_name="Existing", mobile="4235550142", email="robin@example.com")
        Address.objects.create(customer=existing, line1="999 Private Rd", city="Hidden", state="TN", zip_code="37311")
        Vehicle.objects.create(customer=existing, year=1999, make="Ferrari", model="F355", color="rosso")
        quote, answer = self.book()
        text = str(answer) + str(quote)
        for private in ("Robin", "Existing", "robin@example.com", "999 Private", "Hidden", "Ferrari", "F355", "rosso"):
            self.assertNotIn(private, text)
        # The booking's own name isn't echoed either: the summary needs none.
        self.assertNotIn("Jordan", text)


@with_google_key
class DoubleBookingRaceTests(TransactionTestCase):
    """Two visitors send a booking for the same time at the same moment.
    Each request has its own database connection, as in gunicorn; the day's
    lock makes the second wait and then see the first job."""

    def setUp(self):
        call_command("load_pricebook", stdout=io.StringIO())
        import_fixture_rates()
        add_model("Toyota", "RAV4", VehicleClass.objects.get(name="Medium"), 2)
        self.google = FakeServices(places=PLACES)
        patch = self.google.patch()
        patch.start()
        self.addCleanup(patch.stop)
        self.full_detail = Service.objects.get(name="Full Detail")

    def quote(self, client):
        place = client.post_json("addresses", {"place_id": CLEVELAND, "lookup_session": lookup_session(client)}).json()["place"]
        body = {"vehicle": {"year": 2019, "make": "Toyota", "model": "RAV4"}, "service": self.full_detail.pk, "condition": 1, "place": place}
        return client.post_json("quotes", body).json()

    def test_only_one_of_two_bookings_at_once_gets_the_time(self):
        first, second = PublicClient(visitor="198.51.100.1"), PublicClient(visitor="198.51.100.2")
        quotes = [self.quote(first), self.quote(second)]
        start = eastern(open_day(3), 8)
        # Both requests are inside their transaction, past the Turnstile
        # check, before either checks the time.
        barrier = threading.Barrier(2, timeout=20)

        def slow_siteverify(token, remote_ip):
            barrier.wait()
            return siteverify(token, remote_ip)

        results = [None, None]

        def send(index, client):
            try:
                body = booking_body(quotes[index], start, mobile=f"423555010{index}")
                results[index] = client.post_json("bookings", body)
            finally:
                connection.close()

        with mock.patch("publicapi.turnstile.siteverify", side_effect=slow_siteverify), \
                mock.patch("calendars.sync.refresh_time_off_for_booking", return_value=False):
            threads = [threading.Thread(target=send, args=(index, client)) for index, client in enumerate((first, second))]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(60)
        statuses = sorted(result.status_code for result in results)
        self.assertEqual(statuses, [201, 409], [result.content for result in results])
        refused = next(result for result in results if result.status_code == 409)
        self.assertEqual(refused.json()["error"], "time_taken")
        self.assertEqual(Appointment.objects.filter(scheduled_start=start).count(), 1)
