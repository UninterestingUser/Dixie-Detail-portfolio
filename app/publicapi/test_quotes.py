"""Addresses, quotes and open times through the public API."""

import datetime
from decimal import Decimal

from django.utils import timezone

from customers.models import Address, Customer
from pricebook.models import Quote
from publicapi.models import VerifiedPlace, WebQuote
from scheduling.models import DateException

from .testing import CLEVELAND, COHUTTA, KNOXVILLE, TOWN_ONLY, ApiTestCase, open_day


class AddressTests(ApiTestCase):
    def test_a_place_in_the_area_with_its_tax_line(self):
        place = self.place(CLEVELAND)
        self.assertEqual(place["address"]["line1"], "100 Example St NW")
        self.assertEqual(place["address"]["city"], "Cleveland")
        self.assertTrue(place["in_area"])
        self.assertEqual(place["tax"], {"rate_percent": "9.75", "jurisdiction": "Cleveland, TN"})
        self.assertFalse(place["approved_out_of_area"])
        # The server looked it up with the session token, which ends the session.
        (url, call), = self.google.urls("https://places.googleapis.com/v1/places/")
        self.assertEqual(call["params"]["sessionToken"], "session-token-1")
        self.assertTrue(VerifiedPlace.objects.filter(token=place["place"]).exists())

    def test_an_address_outside_the_area_is_refused_politely(self):
        response = self.client.post_json("addresses", {"place_id": KNOXVILLE})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "outside_area")
        self.assertIn("outside the area we serve", response.json()["message"])
        self.assertFalse(VerifiedPlace.objects.exists())

    def test_an_approved_out_of_area_address_passes_when_the_place_matches(self):
        refused = self.client.post_json("addresses", {"place_id": COHUTTA})
        self.assertEqual(refused.json()["error"], "outside_area")
        customer = Customer.objects.create(first_name="Casey", mobile="4235550177")
        approved = Address.objects.create(
            customer=customer, line1="400 Made Up Lane", city="Cohutta", state="GA", zip_code="30710", approved_out_of_area=True
        )
        place = self.place(COHUTTA)
        self.assertTrue(place["approved_out_of_area"])
        self.assertEqual(place["tax"]["jurisdiction"], "Georgia, GA")
        self.assertEqual(place["tax"]["rate_percent"], "0")
        self.assertEqual(VerifiedPlace.objects.get(token=place["place"]).approved_address, approved)
        # Nothing from the approved customer's record is in the answer.
        self.assertNotIn("Casey", str(place))
        self.assertNotIn("Lane", str(place))

    def test_a_place_that_is_not_a_street_address(self):
        response = self.client.post_json("addresses", {"place_id": TOWN_ONLY})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "not_an_address")

    def test_strict_input(self):
        self.assertEqual(self.client.post_json("addresses", {"place_id": "../../etc"}).status_code, 400)
        self.assertEqual(self.client.post_json("addresses", {"place_id": CLEVELAND, "latitude": 35}).json()["field"], "latitude")
        self.assertEqual(self.google.calls, [])


class QuoteTests(ApiTestCase):
    def test_a_quote_before_the_address(self):
        quote = self.quote(condition=2, add_ons=[self.seats.pk])
        self.assertEqual(len(quote["number"]), 10)
        self.assertEqual(quote["vehicle"]["class"]["name"], "Medium")
        self.assertEqual(quote["vehicle"]["description"], "2019 Toyota RAV4")
        kinds = [line["kind"] for line in quote["lines"]]
        self.assertEqual(kinds, ["service", "condition", "add_on"])
        stored = Quote.objects.get(web__number=quote["number"])
        self.assertEqual(Decimal(quote["total_before_tax"]), stored.total_before_tax)
        self.assertEqual(sum(Decimal(line["amount"]) for line in quote["lines"]), stored.total_before_tax)
        self.assertIsNone(quote["sales_tax"])
        self.assertEqual(quote["total"], quote["total_before_tax"])
        self.assertEqual(quote["time_on_site_minutes"], stored.time_on_site_minutes)
        self.assertEqual(quote["service_minutes"], stored.service_minutes)
        self.assertIs(quote["full_day"], stored.full_day)
        expires = datetime.datetime.fromisoformat(quote["expires_at"])
        self.assertAlmostEqual((expires - timezone.now()).total_seconds(), 7200, delta=60)

    def test_the_worked_example_from_the_pricing_rules(self):
        # pricing.md: a two-row Medium Full Detail at the second level with
        # Seat Extraction is $355 before tax, 6 hours of service, 7 on site.
        quote = self.quote(condition=2, add_ons=[self.seats.pk])
        self.assertEqual(quote["total_before_tax"], "355.00")
        self.assertEqual(quote["service_minutes"], 360)
        self.assertEqual(quote["time_on_site_minutes"], 420)
        self.assertFalse(quote["full_day"])

    def test_with_the_address_the_quote_carries_sales_tax(self):
        place = self.place()
        quote = self.quote(place=place["place"])
        self.assertEqual(quote["sales_tax"]["rate_percent"], "9.75")
        self.assertEqual(quote["address"], "100 Example St NW, Cleveland, TN 37311")
        total = Decimal(quote["total_before_tax"])
        self.assertEqual(Decimal(quote["sales_tax"]["amount"]), (total * Decimal("0.07")).quantize(Decimal("0.01")) + (total * Decimal("0.0275")).quantize(Decimal("0.01")))
        self.assertEqual(Decimal(quote["total"]), total + Decimal(quote["sales_tax"]["amount"]))
        # The quote keeps no link to a customer's address.
        self.assertIsNone(Quote.objects.get(web__number=quote["number"]).service_address)

    def test_a_changed_input_makes_a_new_quote(self):
        first = self.quote(condition=1)
        second = self.quote(condition=2)
        self.assertNotEqual(first["number"], second["number"])
        self.assertEqual(WebQuote.objects.count(), 2)
        self.assertEqual(Quote.objects.get(web__number=first["number"]).condition_level, 1)

    def test_the_full_day_flag(self):
        # 6 hours + 10% + 2 hours of Seat Extraction.
        quote = self.quote({"year": 2019, "make": "Toyota", "model": "Highlander"}, size=3, condition=2, add_ons=[self.seats.pk])
        self.assertTrue(quote["full_day"], quote)

    def test_the_size_question_must_be_answered(self):
        response = self.client.post_json("quotes", {"vehicle": {"year": 2019, "make": "Toyota", "model": "Highlander"}, "service": self.full_detail.pk, "condition": 1})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "size_question")
        self.assertEqual(response.json()["question"]["key"], "third_row")

    def test_a_condition_is_needed_for_a_detail(self):
        response = self.client.post_json("quotes", {"vehicle": {"year": 2019, "make": "Toyota", "model": "RAV4"}, "service": self.full_detail.pk})
        self.assertEqual(response.json()["field"], "condition")

    def test_a_motorcycle_gets_motorcycle_detail_with_no_condition_or_add_ons(self):
        bike = {"year": 2020, "make": "Honda", "model": "Gold Wing", "type": "motorcycle"}
        quote = self.quote(bike, self.motorcycle_detail)
        self.assertEqual(quote["total_before_tax"], "100.00")
        # Motorcycle Detail takes no condition level (decision 0103).
        self.assertEqual(self.quote(bike, self.motorcycle_detail, expect=400, condition=1)["field"], "condition")
        self.assertIsNone(quote["condition_level"])
        self.assertEqual(quote["time_on_site_minutes"], 180)
        self.assertEqual(self.quote(bike, self.full_detail, expect=422)["error"], "not_offered")
        # No add-on goes with Motorcycle Detail (decision 0106).
        refused = self.quote(bike, self.motorcycle_detail, expect=400, add_ons=[self.seats.pk])
        self.assertEqual((refused["field"], refused["message"]), ("add_ons", "Seat Extraction can't be added to Motorcycle Detail."))

    def test_a_photo_card(self):
        quote = self.quote({"photo_card": self.small.pk}, condition=1, size=2)
        self.assertEqual(quote["vehicle"]["class"]["name"], "Small")
        self.assertEqual(quote["vehicle"]["description"], "Small (picked from the photo cards)")
        # Small has one row or two, and no question settles it from a card.
        asked = self.quote({"photo_card": self.small.pk}, expect=422)
        self.assertEqual(asked["error"], "size_question")
        self.assertEqual([choice["answer"] for choice in asked["question"]["choices"]], [1, 2])

    def test_a_vehicle_not_in_the_catalog_is_sent_to_the_photo_cards(self):
        response = self.quote({"year": 1969, "make": "Chevrolet", "model": "Camaro"}, expect=422)
        self.assertEqual(response["error"], "photo_card_needed")
        self.assertEqual(len(response["photo_cards"]), 8)

    def test_a_class_booked_by_quote_cant_be_quoted(self):
        van = self.quote({"year": 2021, "make": "Ford", "model": "Transit 250"}, expect=422)
        self.assertEqual(van["error"], "ask_for_quote")
        card = self.quote({"photo_card": self.vans.pk}, expect=422)
        self.assertEqual(card["error"], "ask_for_quote")

    def test_maintenance_plans_and_unknown_fields_are_refused(self):
        self.assertEqual(self.quote(service=self.monthly, expect=400)["field"], "service")
        self.assertEqual(self.quote(expect=400, price="1.00")["field"], "price")
        self.assertEqual(self.quote(expect=400, add_ons=[self.full_detail.pk])["field"], "add_ons")
        self.assertEqual(self.quote(expect=400, place="not-a-real-place-token")["field"], "place")


class OpenTimesTests(ApiTestCase):
    def test_open_times_for_the_quotes_time_on_site_and_address(self):
        quote = self.quote(place=self.place()["place"])
        data = self.client.get_api("open-times", {"quote": quote["number"]}).json()
        self.assertEqual(len(data["days"]), 14)
        day = open_day(2)
        found = {item["date"]: item for item in data["days"]}
        times = found[day.isoformat()]["times"]
        self.assertEqual([slot["label"] for slot in times], ["8:00 AM", "8:30 AM", "9:00 AM"])
        self.assertEqual(set(times[0]), {"start", "label"})

    def test_closed_days_show_no_times_and_never_why(self):
        quote = self.quote(place=self.place()["place"])
        day = open_day(5)
        DateException.objects.create(date=day, kind=DateException.Kind.CLOSED, reason="Family wedding")
        data = self.client.get_api("open-times", {"quote": quote["number"], "from": day.isoformat(), "days": 1})
        self.assertEqual(data.json()["days"], [{"date": day.isoformat(), "times": []}])
        self.assertNotIn("wedding", data.content.decode())

    def test_no_google_calls_while_browsing_times(self):
        quote = self.quote(place=self.place()["place"])
        self.google.calls.clear()
        self.client.get_api("open-times", {"quote": quote["number"], "days": 31})
        self.assertEqual(self.google.urls("https://routes.googleapis.com/"), [])

    def test_a_quote_without_an_address(self):
        quote = self.quote()
        response = self.client.get_api("open-times", {"quote": quote["number"]})
        self.assertEqual(response.json()["error"], "address_needed")

    def test_an_unknown_quote(self):
        response = self.client.get_api("open-times", {"quote": "ZZZZZZZZZZ"})
        self.assertEqual(response.status_code, 404)


class AddOnRuleTests(ApiTestCase):
    """The API offers only the add-ons that go with the chosen service and
    refuses any other (decision 0106)."""

    @classmethod
    def setUpTestData(cls):
        from pricebook.models import Service

        super().setUpTestData()
        cls.interior = Service.objects.get(name="Interior Only")
        cls.carpet = Service.objects.get(name="Carpet Extraction")
        cls.headlights = Service.objects.get(name="Headlight Restoration")

    def test_the_pricebook_lists_the_add_ons_each_service_takes(self):
        services = {service["name"]: service for service in self.client.get_api("services").json()["services"]}
        names = {service["id"]: name for name, service in services.items()}
        offered = {name: sorted(names[pk] for pk in service["add_ons"]) for name, service in services.items()}
        self.assertEqual(offered["Full Detail"], ["Carpet Extraction", "Headlight Restoration", "Seat Extraction"])
        self.assertEqual(offered["Interior Only"], ["Carpet Extraction", "Seat Extraction"])
        for name in ("Exterior Only", "1-Step Paint Correction", "2-Step Paint Correction"):
            self.assertEqual(offered[name], ["Headlight Restoration"])
        self.assertEqual(offered["Motorcycle Detail"], [])
        self.assertEqual(services["Headlight Restoration"]["kind"], "add_on")
        self.assertEqual(offered["Headlight Restoration"], [])

    def test_a_quote_refuses_an_add_on_that_doesnt_go_with_the_service(self):
        for service, add_on in ((self.exterior, self.seats), (self.exterior, self.carpet), (self.interior, self.headlights)):
            with self.subTest(service=service.name, add_on=add_on.name):
                answer = self.quote(service=service, expect=400, add_ons=[add_on.pk])
                self.assertEqual(answer["field"], "add_ons")
                self.assertEqual(answer["message"], f"{add_on.name} can't be added to {service.name}.")
        quote = self.quote(service=self.full_detail, add_ons=[self.carpet.pk, self.headlights.pk, self.seats.pk])
        self.assertEqual(sorted(item["name"] for item in quote["add_ons"]), ["Carpet Extraction", "Headlight Restoration", "Seat Extraction"])
        self.assertFalse(Quote.objects.filter(service=self.exterior).exists())

    def test_the_price_table_has_only_the_add_ons_that_fit(self):
        jobs = self.client.get_api("price-table").json()["jobs"]
        sets = {(job["service"], tuple(job["add_ons"])) for job in jobs if job["class_id"] == self.medium.pk and job["size"] == 2}
        self.assertIn((self.exterior.pk, (self.headlights.pk,)), sets)
        self.assertNotIn((self.exterior.pk, (self.seats.pk,)), sets)
        self.assertIn((self.full_detail.pk, tuple(sorted([self.carpet.pk, self.headlights.pk, self.seats.pk]))), sets)
        self.assertFalse(any(self.headlights.pk in add_ons for service, add_ons in sets if service == self.interior.pk))
        self.assertFalse(any(job["service"] == self.headlights.pk for job in jobs))
