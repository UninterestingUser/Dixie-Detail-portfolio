"""Book a test job through the public address end to end, send a test quote
request with one photo, check both arrived, then delete both
(public-api.md). Run on the server:

    docker compose run --rm --no-deps -T app python manage.py api_smoke_test

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
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from PIL import Image

from appointments.models import Appointment
from customers.models import Customer
from publicapi import consent, test_records
from publicapi.models import QuoteRequest, SmokeTestPass
from publicapi.photos import path_of
from publicapi.turnstile import SMOKE_TEST_PREFIX

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


def test_photo():
    out = io.BytesIO()
    Image.new("RGB", (64, 48), "navy").save(out, "JPEG")
    return out.getvalue()


class Command(BaseCommand):
    help = "Book a test job and send a test quote request with one photo through the public address, then delete both."

    def add_arguments(self, parser):
        parser.add_argument("--url", default=settings.API_SMOKE_TEST_URL, help="The public address (default API_SMOKE_TEST_URL).")
        parser.add_argument("--place-id", default=settings.API_SMOKE_TEST_PLACE_ID, help="A Google place ID in the service area (default API_SMOKE_TEST_PLACE_ID).")

    def say(self, text):
        self.stdout.write(f"api-smoke-test: {text}")

    def handle(self, *args, **options):
        if not settings.TEST_PHONE_NUMBERS:
            raise CommandError("Set TEST_PHONE_NUMBERS in .env: the smoke test books from the first one.")
        if not options["place_id"]:
            raise CommandError("Set API_SMOKE_TEST_PLACE_ID in .env, or pass --place-id.")
        api = Api(options["url"])
        smoke = SmokeTestPass.objects.create(expires_at=timezone.now() + datetime.timedelta(minutes=10), uses_left=3)
        token = SMOKE_TEST_PREFIX + smoke.token
        made = {"booking": None, "request": None}
        try:
            self.run(api, options["place_id"], token, made)
        finally:
            self.clean_up(made)
            smoke.delete()
        self.say("PASS")

    def run(self, api, place_id, token, made):
        mobile = settings.TEST_PHONE_NUMBERS[0]
        consents = {"version": consent.current()["version"], "appointment": False, "follow_up": False}

        pricebook = api.ok("GET", "services")
        service = next((item for item in pricebook["services"] if item["name"] == SERVICE), None)
        if service is None:
            raise CommandError(f"{SERVICE} is not in the published pricebook.")
        self.say(f"pricebook version {pricebook['pricebook_version']}, {len(pricebook['services'])} services")

        lookup = api.ok("GET", "vehicles/lookup", params=VEHICLE)
        if lookup["class"] is None:
            raise CommandError("The 2019 Toyota RAV4 went to the photo cards.")
        size = lookup["question"]["choices"][-1]["answer"] if lookup["question"] else None
        self.say(f"2019 Toyota RAV4 is {lookup['class']['name']}")

        place = api.ok("POST", "addresses", body={"place_id": place_id})
        self.say(f"address in the area, tax {place['tax']['rate_percent']}%")

        body = {"vehicle": VEHICLE, "service": service["id"], "condition": 1, "place": place["place"]}
        if size is not None:
            body["size"] = size
        quote = api.ok("POST", "quotes", body=body)
        self.say(f"quote {quote['number']}: total {quote['total']}, {quote['time_on_site_minutes']} minutes on site")

        times = api.ok("GET", "open-times", params={"quote": quote["number"], "days": 31})
        start = next((slot["start"] for day in times["days"] for slot in day["times"]), None)
        if start is None:
            raise CommandError("No open time in the next 31 days to book the test job at.")

        booked = api.ok("POST", "bookings", body={
            "quote": quote["number"], "start": start, "first_name": "Smoke", "last_name": "Test", "mobile": mobile,
            "payment_method": "cash", "consents": consents, "turnstile": token,
        })
        made["booking"] = booked["reference"]
        appointment = Appointment.objects.filter(reference=booked["reference"]).first()
        if appointment is None or not appointment.is_test:
            raise CommandError("The booking did not arrive as a test record.")
        self.say(f"booked {booked['reference']} for {booked['summary']['arrival']}")

        card = next((item for item in api.ok("GET", "vehicles/photo-cards")["photo_cards"] if item["booked_by_quote"]), None)
        if card is None:
            raise CommandError("No vehicle class is booked by quote, so no quote request can be sent.")
        session = api.ok("POST", "quote-requests/uploads", body={"turnstile": token})
        data, content_type = multipart("photo", "smoke-test.jpg", test_photo(), "image/jpeg")
        photo = api.ok("POST", f"quote-requests/uploads/{session['session']}/photos", data=data, content_type=content_type)
        sent = api.ok("POST", "quote-requests", body={
            "vehicle": {"photo_card": card["class_id"]}, "service": "not_sure", "description": "Smoke test: please ignore.",
            "place": place["place"], "first_name": "Smoke", "last_name": "Test", "mobile": mobile, "consents": consents,
            "session": session["session"], "photos": [photo["photo"]], "turnstile": token,
        })
        made["request"] = sent["reference"]
        request = QuoteRequest.objects.filter(reference=sent["reference"]).first()
        if request is None or not request.is_test or request.photos.count() != 1:
            raise CommandError("The quote request or its photo did not arrive.")
        if not path_of(request.photos.get().file_name).exists():
            raise CommandError("The quote request's photo file is missing from the photo folder.")
        self.say(f"quote request {sent['reference']} with 1 photo")

    def clean_up(self, made):
        customers = set()
        if made["booking"]:
            customers |= set(Appointment.objects.filter(reference=made["booking"]).values_list("customer_id", flat=True))
        if made["request"]:
            customers |= set(QuoteRequest.objects.filter(reference=made["request"]).values_list("customer_id", flat=True))
        if customers:
            found = test_records.delete(Customer.objects.filter(pk__in=customers, is_test=True))
            self.say(str(found))
