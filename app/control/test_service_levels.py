"""The control app and condition levels (decision 0103): the field shows only
for Full Detail and Interior Only with Level 1 preselected, Level 3 is booked
with a hand price and time on site kept as a quote record, with the Level 2
price shown for reference, and a Level 3 quote request is priced the same way."""

import re
from decimal import Decimal

from django.urls import reverse

from appointments.models import Appointment
from pricebook.models import PricedLine, Service
from pricebook.pricing import price_job
from publicapi.models import QuoteRequest
from publicapi.testing import CONSENTS, GOOD_TOKEN

from .fixtures import JobsTestCase, open_day
from .test_website_bookings import ControlTestCase


class BookingFormTests(JobsTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.exterior = Service.objects.get(name="Exterior Only")
        cls.interior = Service.objects.get(name="Interior Only")

    def new_page(self):
        return self.client.get(reverse("appointment-new", args=[self.customer.pk])).content.decode()

    def test_level_1_is_preselected(self):
        page = self.new_page()
        self.assertRegex(page, r'<option value="1"[^>]*selected[^>]*>1: adds nothing</option>')
        self.assertIn('<option value="2">2: adds 10%</option>', page)
        self.assertRegex(page, r'<option value="3" data-by-quote="1">3: priced by hand</option>')

    def test_only_full_detail_and_interior_only_show_the_level(self):
        page = self.new_page()
        marked = set(re.findall(r'<option value="(\d+)"[^>]*data-takes-level="1"', page))
        self.assertEqual(marked, {str(self.full_detail.pk), str(self.interior.pk)})
        self.assertIn('data-shows-with="condition"', page)
        self.assertIn('data-shows-with="hand-price"', page)

    def test_exterior_only_is_booked_with_no_level(self):
        day = open_day(10)
        self.client.post(reverse("appointment-new", args=[self.customer.pk]),
                         self.booking_data(day, service=self.exterior.pk, size_variant="", condition_level="2"))
        job = Appointment.objects.get()
        self.assertEqual([(line.kind, line.condition_level) for line in job.lines.all()], [(PricedLine.Kind.SERVICE, None)])
        self.assertEqual(job.total_before_tax, price_job(self.exterior, self.crossover).total_before_tax)

    def test_level_2_prices_as_before(self):
        page = self.client.post(reverse("appointment-price-new", args=[self.customer.pk]), self.booking_data(open_day(10), condition_level="2"))
        self.assertContains(page, "Condition level 2 (+10%)")
        self.assertContains(page, "$275.00")

    def test_level_3_asks_for_the_price_and_time_with_level_2_for_reference(self):
        page = self.client.post(reverse("appointment-price-new", args=[self.customer.pk]),
                                self.booking_data(open_day(10), condition_level="3", add_ons=[self.seats.pk]))
        self.assertContains(page, "priced by hand: enter the price before tax")
        self.assertContains(page, "priced by hand: enter the time on site")
        # $250 + $25 + $80 for Seat Extraction at Level 2.
        self.assertContains(page, "For reference, at condition level 2: $355.00 before tax, 7 hours on site")
        response = self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(open_day(10), condition_level="3"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Appointment.objects.exists())

    def test_level_3_is_booked_with_a_hand_price_as_a_quote_record(self):
        day = open_day(10)
        data = self.booking_data(day, condition_level="3", add_ons=[self.seats.pk], hand_price="425.00", hand_minutes="480")
        live = self.client.post(reverse("appointment-price-new", args=[self.customer.pk]), data)
        self.assertContains(live, "Full Detail, condition level 3, with Seat Extraction, priced by hand")
        self.assertContains(live, "$425.00")
        response = self.client.post(reverse("appointment-new", args=[self.customer.pk]), data)
        self.assertEqual(response.status_code, 302, response.content)
        job = Appointment.objects.get()
        quote = job.quote
        self.assertTrue(quote.priced_by_hand)
        self.assertEqual((quote.condition_level, list(quote.add_ons.all())), (3, [self.seats]))
        self.assertEqual((quote.total_before_tax, quote.time_on_site_minutes), (Decimal("425.00"), 480))
        self.assertEqual(job.total_before_tax, Decimal("425.00"))
        self.assertEqual(job.setup_minutes + job.service_minutes + job.breakdown_minutes, 480)
        self.assertEqual([(line.kind, line.condition_level) for line in job.lines.all()], [(PricedLine.Kind.SERVICE, 3)])
        # Editing it shows the hand price and leaves it alone.
        edit = self.client.get(reverse("appointment-edit", args=[job.pk])).content.decode()
        self.assertIn('name="hand_price" value="425.00"', edit)
        self.assertIn('name="hand_minutes" value="480"', edit)
        self.client.post(reverse("appointment-edit", args=[job.pk]), {**data, "notes": "Gate code 1234"})
        job.refresh_from_db()
        self.assertEqual((job.quote_id, job.notes), (quote.pk, "Gate code 1234"))

    def test_the_hand_time_must_be_in_quarter_hours(self):
        data = self.booking_data(open_day(10), condition_level="3", hand_price="425.00", hand_minutes="470")
        self.assertContains(self.client.post(reverse("appointment-price-new", args=[self.customer.pk]), data), "Use steps of 15 minutes.")


class LevelThreeQuoteRequestScreenTests(ControlTestCase):
    def send_level_3(self):
        body = {
            "vehicle": {"year": 2019, "make": "Toyota", "model": "RAV4"}, "service": self.full_detail.pk, "condition": 3,
            "add_ons": [self.seats.pk], "description": "Two dogs, heavy hair.", "place": self.place_token, "first_name": "Morgan",
            "mobile": "423-555-0160", "consents": dict(CONSENTS), "turnstile": GOOD_TOKEN,
        }
        response = self.client.post_json("quote-requests", body)
        self.assertEqual(response.status_code, 201, response.content)
        return QuoteRequest.objects.get(reference=response.json()["reference"])

    def test_the_screen_shows_the_level_add_ons_and_level_2_for_reference(self):
        item = self.send_level_3()
        page = self.tailnet.get(f"/requests/quotes/{item.pk}/")
        self.assertContains(page, "<dt>Condition level</dt><dd>3, priced by hand</dd>", html=False)
        self.assertContains(page, "<dt>Add-ons wanted</dt><dd>Seat Extraction</dd>", html=False)
        self.assertContains(page, "For reference, at condition level 2: $355.00 before tax")

    def test_the_hand_price_carries_the_level_and_add_ons(self):
        item = self.send_level_3()
        response = self.tailnet.post(f"/requests/quotes/{item.pk}/price/", {
            "price-service": self.full_detail.pk, "price-vehicle_class": self.medium.pk, "price-amount": "450.00",
            "price-time_on_site_minutes": 480, "price-crew_size": 1,
        })
        self.assertEqual(response.status_code, 302, response.content)
        item.refresh_from_db()
        quote = item.quote
        self.assertTrue(quote.priced_by_hand)
        self.assertEqual((quote.condition_level, list(quote.add_ons.all()), quote.size_variant), (3, [self.seats], item.size_variant))
        self.assertEqual(quote.lines.get().description, f"Full Detail, condition level 3, with Seat Extraction, priced by hand (quote request {item.reference})")
