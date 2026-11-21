"""Book a test job through the public address end to end, send a test quote
request with one photo, check both arrived, then delete both
(public-api.md). Run on the server:

    docker compose run --rm --no-deps -T app python manage.py api_smoke_test

Two more scenarios try Step 5's screens (handling-website-bookings.md):

    --scenario returning  makes a test customer with two identical vehicles
                          and an address elsewhere, then books three times
                          through the public address with the new address:
                          a color that picks one vehicle, a blank color and
                          a color that matches neither.
    --scenario quote      sends a test quote request for a Full-size Vans
                          vehicle with two photos.
    --keep                leaves what it made, for the owner to try the
                          review queue and the request screens;
                          delete_test_records removes it afterwards.

It goes out through Cloudflare like a customer's browser, so it tests the
tunnel, Caddy's public port, the entrance check and every endpoint the
booking form uses. It can't solve a Turnstile widget, so it makes a
one-time pass in the database instead (turnstile.py). The records are
marked test from the start: the first number in TEST_PHONE_NUMBERS, kept
out of reports and the Jobs calendar.
"""

import datetime
import io
import json
import re
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from PIL import Image

from appointments.models import Appointment, MatchFlag
from customers.models import Address, Customer
from publicapi import consent, test_records
from publicapi.models import QuoteRequest, SmokeTestPass
from publicapi.photos import path_of
from publicapi.turnstile import SMOKE_TEST_PREFIX
from vehicles.classification.lookup import classify
from vehicles.models import Vehicle

USER_AGENT = "dixie-detail-smoke-test/1.0"
VEHICLE = {"year": 2019, "make": "Toyota", "model": "RAV4"}
SERVICE = "Exterior Only"


class Api:
    def __init__(self, base):
        self.base = base.rstrip("/") + "/api/public/v1/"

    def call(self, method, path, body=None, params=None, data=None, content_type="application/json"):
        url = self.base + path + (f"?{urlencode(params)}" if params else "")
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode()
        if data is not None:
            headers["Content-Type"] = content_type
        try:
            with urlopen(Request(url, data=data, method=method, headers=headers), timeout=60) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            try:
                answer = json.load(error)
            except ValueError:
                answer = {}
            return error.code, answer
        except (URLError, TimeoutError, OSError) as error:
            raise CommandError(f"{method} {path}: could not reach {self.base}: {error}") from error

    def ok(self, method, path, expect=(200, 201), **kwargs):
        status, answer = self.call(method, path, **kwargs)
        if status not in expect:
            raise CommandError(f"{method} {path} answered {status}: {answer.get('error')} {answer.get('message', '')}".strip())
        return answer


def multipart(field, name, content, content_type):
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{name}\"\r\n"
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def test_photo(color="navy"):
    out = io.BytesIO()
    Image.new("RGB", (64, 48), color).save(out, "JPEG")
    return out.getvalue()


# The returning scenario's three color answers, and what each should give:
# the one vehicle the color picks, or a flag listing both.
COLOR_ANSWERS = [("dark blue", "picks the Dark Blue one"), ("", "is blank"), ("Red", "matches neither")]


class Command(BaseCommand):
    help = "Book a test job and send a test quote request through the public address, then delete them (see --scenario and --keep)."

    def add_arguments(self, parser):
        parser.add_argument("--url", default=settings.API_SMOKE_TEST_URL, help="The public address (default API_SMOKE_TEST_URL).")
        parser.add_argument("--place-id", default=settings.API_SMOKE_TEST_PLACE_ID, help="A Google place ID in the service area (default API_SMOKE_TEST_PLACE_ID).")
        parser.add_argument(
            "--scenario", choices=["basic", "returning", "quote"], default="basic",
            help="basic: a booking and a quote request with one photo (the default). returning: a returning customer with "
            "two identical vehicles books three times. quote: a Full-size Vans quote request with two photos.",
        )
        parser.add_argument("--keep", action="store_true", help="Leave what it made for the owner to try; delete_test_records removes it.")

    def say(self, text):
        self.stdout.write(f"api-smoke-test: {text}")

    def handle(self, *args, **options):
        if not settings.TEST_PHONE_NUMBERS:
            raise CommandError("Set TEST_PHONE_NUMBERS in .env: the smoke test books from the first one.")
        if not options["place_id"]:
            raise CommandError("Set API_SMOKE_TEST_PLACE_ID in .env, or pass --place-id.")
        mobile = test_mobile()
        if options["scenario"] != "basic" and Customer.objects.filter(mobile=mobile, is_test=True).exists():
            raise CommandError("Test records from an earlier run are still here. Run delete_test_records first.")
        api = Api(options["url"])
        smoke = SmokeTestPass.objects.create(expires_at=timezone.now() + datetime.timedelta(minutes=10), uses_left=10)
        token = SMOKE_TEST_PREFIX + smoke.token
        made = {"bookings": [], "requests": [], "customers": []}
        try:
            scenario = {"basic": self.basic, "returning": self.returning, "quote": self.vans_quote_request}[options["scenario"]]
            scenario(api, options["place_id"], token, made)
        finally:
            if options["keep"]:
                self.say("kept the test records: delete_test_records removes them")
            else:
                self.clean_up(made)
            smoke.delete()
        self.say("PASS")

    # Steps shared by the scenarios ----------------------------------------------

    def consents(self):
        return {"version": consent.current()["version"], "appointment": False}

    def service(self, api):
        pricebook = api.ok("GET", "services")
        service = next((item for item in pricebook["services"] if item["name"] == SERVICE), None)
        if service is None:
            raise CommandError(f"{SERVICE} is not in the published pricebook.")
        self.say(f"pricebook version {pricebook['pricebook_version']}, {len(pricebook['services'])} services")
        return service

    def size(self, api):
        lookup = api.ok("GET", "vehicles/lookup", params=VEHICLE)
        if lookup["class"] is None:
            raise CommandError("The 2019 Toyota RAV4 went to the photo cards.")
        self.say(f"2019 Toyota RAV4 is {lookup['class']['name']}")
        return lookup["question"]["choices"][-1]["answer"] if lookup["question"] else None

    def place(self, api, place_id):
        place = api.ok("POST", "addresses", body={"place_id": place_id})
        self.say(f"address in the area, tax {place['tax']['rate_percent']}%")
        return place

    def get_quote(self, api, service, size, place):
        body = {"vehicle": VEHICLE, "service": service["id"], "place": place["place"]}
        if service["condition_applies"]:
            # Only Full Detail and Interior Only take a condition level (decision 0103).
            body["condition"] = 1
        if size is not None:
            body["size"] = size
        return api.ok("POST", "quotes", body=body)

    def open_start(self, api, quote, skip_days=()):
        times = api.ok("GET", "open-times", params={"quote": quote["number"], "days": 31})
        for day in times["days"]:
            if day["date"] in skip_days:
                continue
            for slot in day["times"]:
                return day["date"], slot["start"]
        raise CommandError("No open time in the next 31 days to book the test job at.")

    def book(self, api, quote, start, token, made, color=None):
        body = {
            "quote": quote["number"], "start": start, "first_name": "Smoke", "last_name": "Test", "mobile": test_mobile(),
            "payment_method": "cash", "consents": self.consents(), "turnstile": token,
        }
        if color:
            body["color"] = color
        booked = api.ok("POST", "bookings", body=body, expect=(201,))
        made["bookings"].append(booked["reference"])
        appointment = Appointment.objects.filter(reference=booked["reference"]).first()
        if appointment is None or not appointment.is_test:
            raise CommandError("The booking did not arrive as a test record.")
        return booked, appointment

    def send_request(self, api, token, made, vehicle, description, photos, place):
        session = api.ok("POST", "quote-requests/uploads", body={"turnstile": token})
        ids = []
        for number, color in enumerate(photos, 1):
            data, content_type = multipart("photo", f"smoke-test-{number}.jpg", test_photo(color), "image/jpeg")
            ids.append(api.ok("POST", f"quote-requests/uploads/{session['session']}/photos", data=data, content_type=content_type)["photo"])
        sent = api.ok("POST", "quote-requests", body={
            "vehicle": vehicle, "service": "not_sure", "description": description,
            "place": place["place"], "first_name": "Smoke", "last_name": "Test", "mobile": test_mobile(), "consents": self.consents(),
            "session": session["session"], "photos": ids, "turnstile": token,
        })
        made["requests"].append(sent["reference"])
        request = QuoteRequest.objects.filter(reference=sent["reference"]).first()
        if request is None or not request.is_test or request.photos.count() != len(photos):
            raise CommandError("The quote request or its photos did not arrive.")
        for photo in request.photos.all():
            if not path_of(photo.file_name).exists():
                raise CommandError("A quote request's photo file is missing from the photo folder.")
        return sent, request

    def quote_card(self, api):
        card = next((item for item in api.ok("GET", "vehicles/photo-cards")["photo_cards"] if item["booked_by_quote"]), None)
        if card is None:
            raise CommandError("No vehicle class is booked by quote, so no quote request can be sent.")
        return card

    # The scenarios ------------------------------------------------------------------

    def basic(self, api, place_id, token, made):
        service, size = self.service(api), self.size(api)
        place = self.place(api, place_id)
        quote = self.get_quote(api, service, size, place)
        self.say(f"quote {quote['number']}: total {quote['total']}, {quote['time_on_site_minutes']} minutes on site")
        _, start = self.open_start(api, quote)
        booked, _ = self.book(api, quote, start, token, made)
        self.say(f"booked {booked['reference']} for {booked['summary']['arrival']}")
        card = self.quote_card(api)
        sent, _ = self.send_request(api, token, made, {"photo_card": card["class_id"]}, "Smoke test: please ignore.", ["navy"], place)
        self.say(f"quote request {sent['reference']} with 1 photo")

    def returning(self, api, place_id, token, made):
        """A returning customer with two identical vehicles books three times,
        at a new address, with each kind of color answer (decision 0067)."""
        service, size = self.service(api), self.size(api)
        place = self.place(api, place_id)
        customer = make_returning_customer()
        made["customers"].append(customer.pk)
        self.say(f"test customer {customer} with two 2019 Toyota RAV4s, white and dark blue, and an address elsewhere")
        used_days = []
        for number, (color, meaning) in enumerate(COLOR_ANSWERS, 1):
            quote = self.get_quote(api, service, size, place)
            day, start = self.open_start(api, quote, used_days)
            used_days.append(day)
            booked, appointment = self.book(api, quote, start, token, made, color=color)
            if appointment.customer_id != customer.pk:
                raise CommandError(f"Booking {number} did not match the test customer.")
            flags = list(appointment.match_flags.all())
            vehicle_flags = [flag for flag in flags if flag.field == MatchFlag.Field.VEHICLE]
            if color == "dark blue":
                if vehicle_flags or (appointment.vehicle.color != "Dark Blue"):
                    raise CommandError("The color didn't pick the Dark Blue vehicle.")
            elif not (vehicle_flags and vehicle_flags[0].identical_vehicles):
                raise CommandError(f"Booking {number}'s color {meaning}, but no identical-vehicles flag was raised.")
            fields = ", ".join(flag.get_field_display().lower() for flag in flags) or "no"
            self.say(f"booking {number} ({booked['reference']}): the color {meaning}; {fields} flag(s)")
        address_flags = MatchFlag.objects.filter(customer=customer, field=MatchFlag.Field.ADDRESS).count()
        if address_flags != 1:
            raise CommandError(f"Expected one address flag for the new address, found {address_flags}.")
        self.say("review queue: one address flag and two identical-vehicle flags")

    def vans_quote_request(self, api, place_id, token, made):
        """A quote request for a Full-size Vans vehicle with two photos."""
        place = self.place(api, place_id)
        card = self.quote_card(api)
        vehicle = {"photo_card": card["class_id"], "year": 2021, "make": "Ford", "model": "Transit"}
        sent, request = self.send_request(
            api, token, made, vehicle, "Smoke test: a work van, very dirty inside. Please ignore.", ["navy", "maroon"], place,
        )
        self.say(f"quote request {sent['reference']} for a {request.vehicle_text} with 2 photos")

    def clean_up(self, made):
        customers = set(made["customers"])
        if made["bookings"]:
            customers |= set(Appointment.objects.filter(reference__in=made["bookings"]).values_list("customer_id", flat=True))
        if made["requests"]:
            customers |= set(QuoteRequest.objects.filter(reference__in=made["requests"]).values_list("customer_id", flat=True))
        if customers:
            found = test_records.delete(Customer.objects.filter(pk__in=customers, is_test=True))
            self.say(str(found))


def test_mobile():
    return re.sub(r"\D", "", settings.TEST_PHONE_NUMBERS[0])[-10:]


def make_returning_customer():
    """A test customer, as if booked before, with two identical vehicles told
    apart only by color, an address that isn't the smoke test's place, and
    one completed job, so their bookings are confirmed at once and the caps
    on unconfirmed bookings don't apply (decision 0112)."""
    customer = Customer.objects.create(first_name="Smoke", last_name="Test", mobile=test_mobile(), source="Smoke test", is_test=True)
    Address.objects.create(customer=customer, line1="1 Example Test Lane", city="Cleveland", state="TN", zip_code="37311")
    Appointment.objects.create(
        customer=customer, scheduled_start=timezone.now() - datetime.timedelta(days=60), status=Appointment.Status.COMPLETED,
        source=Appointment.Source.OWNER, is_test=True, notes="Smoke test: a past job, so the customer is known.",
    )
    found = classify(VEHICLE["year"], VEHICLE["make"], VEHICLE["model"])
    for color in ("White", "Dark Blue"):
        Vehicle.objects.create(
            customer=customer, vehicle_model=found.vehicle_model, year=VEHICLE["year"], make=VEHICLE["make"], model=VEHICLE["model"],
            color=color, vehicle_class=found.vehicle_class, size_variant=found.size_variant,
        )
    return customer
