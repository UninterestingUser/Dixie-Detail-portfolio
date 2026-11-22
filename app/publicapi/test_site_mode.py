"""The requests-only switch (decision 0128): in requests mode the booking
and quote endpoints answer 503, which the website treats as "server
unavailable", while the offline request endpoints and the health page keep
working; normal mode changes nothing."""

import io
import json

from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from .models import SiteMode

ORIGIN = "https://dixiedetail.example"
PUBLIC = {"X-Dixie-Entrance": "public", "Origin": ORIGIN}


def paused(answer):
    """True when the answer is the requests-only switch's. Without a
    published pricebook the API answers 503 unavailable for itself, which
    isn't the switch."""
    return answer.status_code == 503 and json.loads(answer.content).get("error") == "requests_only"


@override_settings(PUBLIC_API_CORS_ORIGINS=[ORIGIN])
class SiteModeTests(TestCase):
    def switch(self, mode, **options):
        out = io.StringIO()
        call_command("site_mode", *([mode] if mode else []), stdout=out, **options)
        return out.getvalue()

    def test_normal_mode_answers_as_always(self):
        self.assertEqual(SiteMode.current(), SiteMode.NORMAL)
        self.assertFalse(paused(Client().get("/api/public/v1/services", headers=PUBLIC)))

    def test_requests_mode_refuses_booking_and_quotes_with_a_503(self):
        self.assertIn("site mode: requests", self.switch("requests", reason="moving to the new host"))
        client = Client()
        for method, path in [
            ("get", "/api/public/v1/vehicles/years"),
            ("get", "/api/public/v1/services"),
            ("post", "/api/public/v1/quotes"),
            ("get", "/api/public/v1/open-times"),
            ("post", "/api/public/v1/bookings"),
            ("post", "/api/public/v1/quote-requests"),
            ("post", "/api/public/v1/quote-requests/uploads"),
            ("post", "/api/public/v1/addresses/sessions"),
        ]:
            answer = getattr(client, method)(path, headers=PUBLIC)
            self.assertTrue(paused(answer), path)
            # The browser can read the answer: the site's own origin is allowed.
            self.assertEqual(answer["Access-Control-Allow-Origin"], ORIGIN, path)

    def test_requests_mode_keeps_the_offline_endpoints_and_health(self):
        self.switch("requests")
        client = Client()
        for path in ("/api/public/v1/time-requests", "/api/public/v1/quote-requests/offline"):
            answer = client.post(path, data="{}", content_type="application/json", headers=PUBLIC)
            self.assertFalse(paused(answer), path)
        self.assertEqual(client.get("/health", headers=PUBLIC).status_code, 200)

    def test_back_to_normal(self):
        self.switch("requests")
        self.assertIn("site mode: normal", self.switch("normal"))
        self.assertFalse(paused(Client().get("/api/public/v1/services", headers=PUBLIC)))
        self.assertIn("site mode: normal", self.switch(None))

    def test_an_unreadable_mode_counts_as_normal(self):
        from unittest import mock

        from django.db import DatabaseError

        with mock.patch.object(SiteMode, "current", side_effect=DatabaseError("made-up outage")), self.assertLogs("publicapi", "ERROR"):
            self.assertFalse(paused(Client().get("/api/public/v1/services", headers=PUBLIC)))

    def test_the_control_app_is_never_affected(self):
        self.switch("requests")
        answer = Client().get("/sign-in/", headers={"X-Dixie-Entrance": "tailnet"})
        self.assertEqual(answer.status_code, 200)
