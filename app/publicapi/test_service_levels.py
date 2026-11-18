"""The public API and condition levels (decision 0103): the condition is taken
only with Full Detail and Interior Only, Level 3 is "ask for a quote" with
no price or time and can't be booked, and a quote request carries the
service, the level and the add-ons."""

import datetime
from decimal import Decimal

from django.utils import timezone

from pricebook.models import ConditionLevel, PricebookVersion, Quote, Service
from publicapi.models import QuoteRequest, WebQuote

from .testing import ApiTestCase
from .test_quote_requests import QuoteRequestTestCase

RAV4 = {"year": 2019, "make": "Toyota", "model": "RAV4"}


class ConditionTests(ApiTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.interior = Service.objects.get(name="Interior Only")
        cls.headlights = Service.objects.get(name="Headlight Restoration")
        cls.paint = Service.objects.get(name="1-Step Paint Correction")

    def test_only_full_detail_and_interior_only_take_a_condition(self):
        for service in (self.exterior, self.paint):
            with self.subTest(service=service.name):
                answer = self.quote(RAV4, service, expect=400, condition=1)
                self.assertEqual(answer["field"], "condition")
                self.assertIn("Only Full Detail and Interior Only", answer["message"])
                # Without one, it is quoted with no condition level.
                quote = self.quote(RAV4, service)
                self.assertIsNone(quote["condition_level"])
                self.assertEqual([line["kind"] for line in quote["lines"]], ["service"])

    def test_headlight_restoration_is_an_add_on_not_a_service(self):
        answer = self.quote(RAV4, self.headlights, expect=400)
        self.assertEqual(answer["field"], "service")
        quote = self.quote(RAV4, self.exterior, add_ons=[self.headlights.pk])
        self.assertEqual([(line["kind"], line["amount"]) for line in quote["lines"]][1:], [("add_on", "95.00")])

    def test_levels_1_and_2_price_as_before(self):
        self.assertEqual(self.quote(RAV4, condition=1)["total_before_tax"], "250.00")
        self.assertEqual(self.quote(RAV4, condition=2)["total_before_tax"], "275.00")
        self.assertEqual(self.quote(RAV4, self.interior, condition=2)["total_before_tax"], "176.00")

    def test_level_3_is_ask_for_a_quote_with_no_price_or_time(self):
        for service in (self.full_detail, self.interior):
            with self.subTest(service=service.name):
                answer = self.quote(RAV4, service, expect=422, condition=3, add_ons=[self.seats.pk])
                self.assertEqual(answer["error"], "ask_for_quote")
                self.assertEqual(answer["quote_request"], {"service": service.pk, "condition": 3, "add_ons": [self.seats.pk]})
                for key in ("total", "total_before_tax", "lines", "time_on_site_minutes", "number"):
                    self.assertNotIn(key, answer)
        self.assertFalse(WebQuote.objects.exists())
        self.assertFalse(Quote.objects.exists())

    def test_the_pricebook_marks_level_3_ask_for_a_quote(self):
        levels = self.client.get_api("services").json()["condition_levels"]
        self.assertEqual([(level["level"], level["booked_by_quote"], level["adds_percent"]) for level in levels],
                         [(1, False, "0"), (2, False, "10"), (3, True, None)])


class BookingAtLevelThreeTests(ApiTestCase):
    """A quote at Level 3 issued under the old rules, booked for a day the new
    rules are in effect, is refused."""

    def test_the_booking_endpoint_refuses_level_3(self):
        current = PricebookVersion.current()
        old = PricebookVersion.new_draft()
        level = ConditionLevel.objects.get(version=old, level=3)
        level.adjustment_percent, level.booked_by_quote = Decimal("20"), False
        level.save()
        old.publish(timezone.localdate())
        place = self.place()
        quote = self.quote(RAV4, condition=3, place=place["place"])
        self.assertEqual(quote["total_before_tax"], "300.00")

        new = PricebookVersion.new_draft()
        level = ConditionLevel.objects.get(version=new, level=3)
        level.adjustment_percent, level.booked_by_quote = Decimal("0"), True
        level.save()
        effective = timezone.localdate() + datetime.timedelta(days=1)
        new.publish(effective)
        self.assertNotEqual(current, new)

        times = self.client.get_api("open-times", {"quote": quote["number"], "from": (effective + datetime.timedelta(days=7)).isoformat()}).json()
        start = next(slot["start"] for day in times["days"] for slot in day["times"])
        response = self.client.post_json("bookings", self.booking_body(quote, start))
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["error"], "ask_for_quote")
        self.assertFalse(WebQuote.objects.exclude(number=quote["number"]).exists())


class LevelThreeQuoteRequestTests(QuoteRequestTestCase):
    def level_3(self, expect=201, **changes):
        body = {"vehicle": RAV4, "service": self.full_detail.pk, "condition": 3, "add_ons": [self.seats.pk],
                "description": "Two dogs, heavy hair and a spilled milkshake.", **changes}
        return self.send(expect=expect, **body)

    def test_a_quote_request_carries_the_service_level_and_add_ons(self):
        answer = self.level_3()
        request = QuoteRequest.objects.get(reference=answer["reference"])
        self.assertEqual((request.service, request.condition_level), (self.full_detail, 3))
        self.assertEqual(list(request.add_ons.all()), [self.seats])
        self.assertEqual((request.vehicle_class, request.size_variant.value), (self.medium, 2))
        self.assertIsNone(request.quote)

    def test_a_level_with_a_price_is_booked_online(self):
        for level in (1, 2):
            with self.subTest(level=level):
                self.assertEqual(self.level_3(expect=422, condition=level)["error"], "book_online")
        self.assertEqual(self.level_3(expect=422, condition=None)["error"], "book_online")

    def test_a_service_without_a_level_refuses_one(self):
        self.assertEqual(self.level_3(expect=400, service=self.exterior.pk)["field"], "condition")
        self.assertEqual(self.level_3(expect=400, service="not_sure")["field"], "condition")

    def test_a_service_not_offered_for_the_vehicle_is_refused(self):
        bike = {"year": 2020, "make": "Honda", "model": "Gold Wing", "type": "motorcycle"}
        self.assertEqual(self.level_3(expect=422, vehicle=bike, add_ons=[])["error"], "not_offered")

    def test_a_van_request_can_carry_a_level_and_add_ons_too(self):
        answer = self.send(condition=2, add_ons=[self.seats.pk])
        request = QuoteRequest.objects.get(reference=answer["reference"])
        self.assertEqual((request.vehicle_class, request.condition_level), (self.vans, 2))
        self.assertEqual(list(request.add_ons.all()), [self.seats])
        self.assertEqual(self.send(expect=400, service=self.exterior.pk, condition=2)["field"], "condition")

