"""The public API's read-only endpoints: the pricebook, the booking form's
options, the year, make and model lists, the lookup and the photo cards.
These are the contract the website build and the booking form rely on."""

from decimal import Decimal

from pricebook.models import Price, PricebookVersion

from .testing import SITE, ApiTestCase


class PricebookTests(ApiTestCase):
    def test_services_and_prices_come_from_the_published_pricebook(self):
        response = self.client.get_api("services")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "public, max-age=300")
        data = response.json()
        version = PricebookVersion.current()
        self.assertEqual(data["pricebook_version"], version.number)
        self.assertEqual(set(data), {"pricebook_version", "effective_date", "classes", "condition_levels", "services"})
        names = [service["name"] for service in data["services"]]
        self.assertIn("Full Detail", names)
        self.assertIn("Seat Extraction", names)
        # Maintenance plans and custom lines are never offered on the website.
        self.assertNotIn("Monthly Maintenance", names)
        self.assertNotIn("Misc Services", names)
        full = next(service for service in data["services"] if service["name"] == "Full Detail")
        cheapest = Price.objects.filter(version=version, service=self.full_detail).order_by("price").first().price
        self.assertEqual(Decimal(full["from_price"]), cheapest)
        self.assertTrue(full["condition_applies"])
        self.assertEqual(full["kind"], "service")
        for price in full["prices"]:
            self.assertEqual(set(price), {"class_id", "size", "price"})
        # Level 3 has no percentage: it is booked by quote (decision 0103).
        self.assertEqual([level["adds_percent"] for level in data["condition_levels"]], ["0", "10", None])
        self.assertEqual([level["booked_by_quote"] for level in data["condition_levels"]], [False, False, True])
        takes = {service["name"] for service in data["services"] if service["condition_applies"]}
        self.assertEqual(takes, {"Full Detail", "Interior Only"})

    def test_classes_with_sizes_and_the_quote_class_has_no_price(self):
        classes = {item["name"]: item for item in self.client.get_api("services").json()["classes"]}
        self.assertEqual(len(classes), 8)
        self.assertTrue(classes["Full-size Vans"]["booked_by_quote"])
        self.assertIsNone(classes["Full-size Vans"]["from_price"])
        self.assertEqual(classes["Full-size Vans"]["photo_card"], "Ask for a quote")
        self.assertEqual([size["value"] for size in classes["Medium"]["sizes"]], [2, 3])
        self.assertEqual(classes["Motorcycles"]["sizes"], [])
        self.assertEqual(classes["Motorcycles"]["from_price"], "100.00")

    def test_booking_options(self):
        data = self.client.get_api("booking-options").json()
        methods = {method["value"] for method in data["payment_methods"]}
        self.assertIn("cash", methods)
        # Owner-only methods and gift cards are never offered (decision 0053).
        self.assertFalse(methods & {"check", "trade", "gift_card"})
        self.assertEqual(data["consent"]["version"], "2026-11-18")
        self.assertTrue(data["consent"]["appointment"].startswith("I agree to receive text messages from Dixie Detail"))
        # One consent checkbox (decision 0108).
        self.assertEqual(sorted(data["consent"]), ["appointment", "links", "version"])
        self.assertEqual(data["quote_lifetime_minutes"], 120)
        self.assertEqual(data["photos"]["max_per_request"], 6)
        self.assertEqual(data["photos"]["max_megabytes"], 15)
        self.assertIn("image/heic", data["photos"]["types"])


class VehicleListTests(ApiTestCase):
    def test_years_then_makes_then_models(self):
        years = self.client.get_api("vehicles/years").json()
        self.assertEqual(years["years"], [2021, 2020, 2019])
        self.assertEqual(self.client.get_api("vehicles/makes", {"year": 2020}).json()["makes"], ["Honda"])
        self.assertEqual(self.client.get_api("vehicles/makes", {"year": 2019}).json()["makes"], ["Toyota"])
        models = self.client.get_api("vehicles/models", {"year": 2019, "make": "toyota"}).json()
        self.assertEqual(models["make"], "Toyota")
        self.assertEqual([model["name"] for model in models["models"]], ["Highlander", "RAV4"])

    def test_motorcycles_are_labeled(self):
        models = self.client.get_api("vehicles/models", {"year": 2020, "make": "Honda"}).json()["models"]
        self.assertEqual(
            models,
            [
                {"name": "Accord", "type": "vehicle", "motorcycle": False},
                {"name": "Gold Wing", "type": "motorcycle", "motorcycle": True},
            ],
        )

    def test_a_bad_year_or_an_unknown_parameter_is_refused(self):
        self.assertEqual(self.client.get_api("vehicles/makes", {"year": "abc"}).status_code, 400)
        self.assertEqual(self.client.get_api("vehicles/makes", {"year": 2019, "extra": 1}).json()["field"], "extra")
        self.assertEqual(self.client.get_api("vehicles/models", {"year": 2019, "make": "<script>"}).status_code, 400)


class LookupTests(ApiTestCase):
    def lookup(self, **params):
        response = self.client.get_api("vehicles/lookup", params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_a_catalog_vehicle_gets_its_class_and_size(self):
        found = self.lookup(year=2019, make="Toyota", model="RAV4")
        self.assertEqual(found["class"]["name"], "Medium")
        self.assertEqual(found["size"], {"value": 2, "label": "two rows"})
        self.assertIsNone(found["question"])
        self.assertFalse(found["booked_by_quote"])
        self.assertEqual(found["message"], "Medium identified.")

    def test_the_size_question_and_its_answer(self):
        found = self.lookup(year=2019, make="Toyota", model="Highlander")
        self.assertEqual(found["question"]["key"], "third_row")
        self.assertEqual(found["question"]["choices"], [{"answer": 3, "label": "Yes"}, {"answer": 2, "label": "No"}])
        answered = self.lookup(year=2019, make="Toyota", model="Highlander", size=3)
        self.assertEqual(answered["size"]["value"], 3)
        self.assertIsNone(answered["question"])
        self.assertEqual(self.client.get_api("vehicles/lookup", {"year": 2019, "make": "Toyota", "model": "Highlander", "size": 1}).status_code, 400)

    def test_a_motorcycle(self):
        found = self.lookup(year=2020, make="Honda", model="Gold Wing", type="motorcycle")
        self.assertEqual(found["class"]["name"], "Motorcycles")
        self.assertTrue(found["vehicle"]["motorcycle"])
        self.assertIsNone(found["size"])
        self.assertIsNone(found["question"])

    def test_a_vehicle_not_in_the_catalog_gets_the_photo_cards(self):
        found = self.lookup(year=1969, make="Chevrolet", model="Camaro")
        self.assertIsNone(found["class"])
        cards = {card["name"]: card for card in found["photo_cards"]}
        self.assertEqual(len(cards), 8)
        self.assertTrue(cards["Full-size Vans"]["booked_by_quote"])
        self.assertEqual(cards["Full-size Vans"]["caption"], "Ask for a quote")
        self.assertEqual(cards["Small"]["examples"], ["Civic", "Corolla", "Camry", "Accord", "Crosstrek"])

    def test_a_full_size_van_is_booked_by_quote(self):
        found = self.lookup(year=2021, make="Ford", model="Transit 250")
        self.assertEqual(found["class"]["name"], "Full-size Vans")
        self.assertTrue(found["booked_by_quote"])
        self.assertIn("Ask for a quote", found["message"])

    def test_photo_cards(self):
        cards = self.client.get_api("vehicles/photo-cards").json()["photo_cards"]
        self.assertEqual([card["name"] for card in cards][:1], ["Small"])
        self.assertEqual(set(cards[0]), {"class_id", "name", "caption", "examples", "photo", "booked_by_quote"})


class CorsTests(ApiTestCase):
    def test_the_sites_origin_is_allowed(self):
        response = self.client.get_api("services")
        self.assertEqual(response["Access-Control-Allow-Origin"], SITE)
        self.assertIn("Origin", response["Vary"])

    def test_a_preflight_from_the_site(self):
        response = self.client.options("/api/public/v1/quotes", headers={"Access-Control-Request-Method": "POST"})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["Access-Control-Allow-Origin"], SITE)
        self.assertIn("POST", response["Access-Control-Allow-Methods"])
        self.assertEqual(response["Access-Control-Allow-Headers"], "Content-Type")

    def test_another_origin_is_refused(self):
        other = self.client_class(origin="https://evil.example")
        preflight = other.options("/api/public/v1/quotes", headers={"Access-Control-Request-Method": "POST"})
        self.assertEqual(preflight.status_code, 403)
        self.assertFalse(preflight.has_header("Access-Control-Allow-Origin"))
        response = other.get_api("services")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "forbidden")
        self.assertFalse(response.has_header("Access-Control-Allow-Origin"))

    def test_no_origin_is_allowed_for_servers(self):
        response = self.client_class(origin=None).get_api("services")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.has_header("Access-Control-Allow-Origin"))


class DoorTests(ApiTestCase):
    def test_the_public_door_reaches_the_api_and_nothing_else(self):
        self.assertEqual(self.client.get_api("services").status_code, 200)
        self.assertEqual(self.client.get("/customers/").status_code, 404)
        self.assertEqual(self.client.get("/requests/").status_code, 404)

    def test_errors_are_generic_json(self):
        response = self.client.post_json("services", {})
        self.assertEqual(response.status_code, 405)
        self.assertEqual(set(response.json()), {"error", "message"})
        response = self.client.post("/api/public/v1/quotes", data="not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("Traceback", response.content.decode())

    def test_a_crash_is_a_generic_error(self):
        from unittest import mock

        with mock.patch("publicapi.catalog.pricebook", side_effect=RuntimeError("secret detail")):
            response = self.client.get_api("services")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"], "server_error")
        self.assertNotIn("secret detail", response.content.decode())


class RateLimitTests(ApiTestCase):
    def test_each_visitor_address_has_its_own_limit(self):
        from django.test import override_settings

        limits = {"read": (3, 10), "quote": (3, 10), "address": (2, 10), "booking": (2, 60), "quote_request": (2, 60),
                  "upload_session": (2, 60), "photo": (2, 60), "offline": (2, 10)}
        with override_settings(PUBLIC_API_RATE_LIMITS=limits):
            for _ in range(3):
                self.assertEqual(self.client.get_api("vehicles/years").status_code, 200)
            refused = self.client.get_api("vehicles/years")
            self.assertEqual(refused.status_code, 429)
            self.assertEqual(refused.json()["error"], "rate_limited")
            other = self.client_class(visitor="203.0.113.9")
            self.assertEqual(other.get_api("vehicles/years").status_code, 200)
        from publicapi.models import RateCount

        # The address is kept only as a keyed hash.
        self.assertFalse(RateCount.objects.filter(visitor__contains="198.51").exists())
