"""Shared set-up for the public API tests: the real pricebook, the test
files' tax rates and recorded Google answers, a small invented catalog, and
a client that comes in by the public door like a browser on the website.
Turnstile is replaced; nothing touches the network."""

import datetime
import io
import json
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from geo.fixtures import FakeServices, import_fixture_rates, with_google_key
from pricebook.models import Service
from scheduling.models import SchedulingSettings
from vehicles.models import ModelYearClassification, SizeVariant, VehicleClass, VehicleModel

SITE = "http://localhost:4321"
BASE = "/api/public/v1/"
CLEVELAND = "ChIJmadeUpCleveland0001"
COHUTTA = "ChIJmadeUpCohutta000001"
KNOXVILLE = "ChIJmadeUpKnoxville0001"
TOWN_ONLY = "ChIJmadeUpTownOnly00001"
PLACES = {
    CLEVELAND: "place_cleveland.json",
    COHUTTA: "place_cohutta.json",
    KNOXVILLE: "place_knoxville.json",
    TOWN_ONLY: "place_town_only.json",
}
GOOD_TOKEN = "a-turnstile-token-the-fake-accepts"
CONSENTS = {"version": "2026-10-13", "appointment": True, "follow_up": False}


def siteverify(token, remote_ip):
    """Cloudflare's answer, as the fake gives it: only GOOD_TOKEN passes."""
    return {"success": token == GOOD_TOKEN, "error-codes": [] if token == GOOD_TOKEN else ["invalid-input-response"]}


def jpeg(size=(640, 480), color="navy", exif=None, image_format="JPEG", mode="RGB"):
    out = io.BytesIO()
    image = Image.new(mode, size, color)
    kwargs = {"exif": exif} if exif is not None else {}
    image.save(out, image_format, **kwargs)
    return out.getvalue()


def gps_exif():
    """EXIF holding a camera make and a GPS position, to check none survives."""
    exif = Image.Exif()
    exif[0x010F] = "MadeUpCameraCo"  # Make
    gps = {1: "N", 2: (35.0, 9.0, 36.0), 3: "W", 4: (84.0, 52.0, 34.0)}
    exif[0x8825] = gps  # GPSInfo
    return exif


class PublicClient(Client):
    """A browser on the website: no tailnet label, the site's Origin, and a
    made-up visitor address from Cloudflare."""

    def __init__(self, *args, visitor="198.51.100.7", origin=SITE, **kwargs):
        headers = {"CF-Connecting-IP": visitor}
        if origin:
            headers["Origin"] = origin
        super().__init__(*args, headers={**headers, **kwargs.pop("headers", {})}, **kwargs)

    def post_json(self, path, body, **kwargs):
        return self.post(BASE + path, data=json.dumps(body), content_type="application/json", **kwargs)

    def get_api(self, path, params=None, **kwargs):
        return self.get(BASE + path, params or {}, **kwargs)


def open_day(days_ahead=7):
    """A Monday to Saturday at least days_ahead from today."""
    day = timezone.localdate() + datetime.timedelta(days=days_ahead)
    return day + datetime.timedelta(days=1) if day.weekday() == 6 else day


def eastern(day, hour, minute=0):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour, minute)))


def add_model(make, name, vehicle_class, size, year=2019, ask_size=False, vehicle_type=VehicleModel.VehicleType.VEHICLE):
    """A catalog model with one classified model year."""
    vehicle_model = VehicleModel.objects.create(
        make=make, model=name, year_from=year, year_to=year, vehicle_type=vehicle_type, source=VehicleModel.Source.EPA
    )
    ModelYearClassification.objects.create(
        vehicle_model=vehicle_model, year=year, vehicle_class=vehicle_class,
        size_variant=SizeVariant.objects.get(vehicle_class=vehicle_class, value=size) if size else None,
        ask_size=ask_size, method=ModelYearClassification.Method.RULE,
    )
    return vehicle_model


def booking_body(quote, start, **changes):
    """A booking as the website sends it; a change of None leaves a field out."""
    body = {
        "quote": quote["number"],
        "start": start if isinstance(start, str) else start.isoformat(),
        "first_name": "Jordan",
        "last_name": "Sample",
        "mobile": "(423) 555-0142",
        "payment_method": "cash",
        "color": "silver",
        "consents": dict(CONSENTS),
        "turnstile": GOOD_TOKEN,
    }
    body.update(changes)
    return {key: value for key, value in body.items() if value is not None}


@with_google_key
class ApiTestCase(TestCase):
    client_class = PublicClient

    @classmethod
    def setUpTestData(cls):
        call_command("load_pricebook", stdout=io.StringIO())
        import_fixture_rates()
        SchedulingSettings.get()
        cls.medium = VehicleClass.objects.get(name="Medium")
        cls.large = VehicleClass.objects.get(name="Large")
        cls.small = VehicleClass.objects.get(name="Small")
        cls.vans = VehicleClass.objects.get(name="Full-size Vans")
        cls.motorcycles = VehicleClass.objects.get(name="Motorcycles")
        cls.full_detail = Service.objects.get(name="Full Detail")
        cls.exterior = Service.objects.get(name="Exterior Only")
        cls.motorcycle_detail = Service.objects.get(name="Motorcycle Detail")
        cls.seats = Service.objects.get(name="Seat Extraction")
        cls.monthly = Service.objects.get(name="Monthly Maintenance")
        cls.rav4 = cls.add_model("Toyota", "RAV4", cls.medium, 2)
        cls.highlander = cls.add_model("Toyota", "Highlander", cls.large, None, ask_size=True)
        cls.accord = cls.add_model("Honda", "Accord", cls.small, 2, year=2020)
        cls.gold_wing = cls.add_model("Honda", "Gold Wing", cls.motorcycles, None, year=2020, vehicle_type=VehicleModel.VehicleType.MOTORCYCLE)
        cls.transit = cls.add_model("Ford", "Transit 250", cls.vans, None, year=2021)

    add_model = staticmethod(lambda *args, **kwargs: add_model(*args, **kwargs))

    def setUp(self):
        super().setUp()
        self.photo_dir = tempfile.mkdtemp(prefix="dixie-photos-")
        self.addCleanup(shutil.rmtree, self.photo_dir, ignore_errors=True)
        settings_patch = override_settings(QUOTE_PHOTO_DIR=Path(self.photo_dir))
        settings_patch.enable()
        self.addCleanup(settings_patch.disable)
        self.google = FakeServices(places=PLACES)
        google_patch = self.google.patch()
        google_patch.start()
        self.addCleanup(google_patch.stop)
        turnstile_patch = mock.patch("publicapi.turnstile.siteverify", side_effect=siteverify)
        self.siteverify = turnstile_patch.start()
        self.addCleanup(turnstile_patch.stop)
        # Booking copies the Time Off calendar first; it isn't connected here.
        time_off = mock.patch("calendars.sync.refresh_time_off_for_booking", return_value=False)
        time_off.start()
        self.addCleanup(time_off.stop)

    # Helpers ---------------------------------------------------------------

    def place(self, place_id=CLEVELAND):
        response = self.client.post_json("addresses", {"place_id": place_id, "session_token": "session-token-1"})
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def quote(self, vehicle=None, service=None, expect=201, **body):
        payload = {"vehicle": vehicle or {"year": 2019, "make": "Toyota", "model": "RAV4"}, "service": (service or self.full_detail).pk}
        if (service or self.full_detail).condition_applies:
            payload["condition"] = 1
        payload.update(body)
        response = self.client.post_json("quotes", payload)
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def booking_body(self, quote, start, **changes):
        return booking_body(quote, start, **changes)

    def first_open(self, quote):
        times = self.client.get_api("open-times", {"quote": quote["number"], "days": 31}).json()
        return next(datetime.datetime.fromisoformat(slot["start"]) for day in times["days"] for slot in day["times"])

    @contextmanager
    def now(self, moment):
        with mock.patch("django.utils.timezone.now", return_value=moment):
            yield
