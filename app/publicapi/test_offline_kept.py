"""Offline requests are kept whatever they hold (decision 0114): a problem
with the content is listed for the owner, never refused. Only a bad
signature, a body that can't be read, or no request id is refused, and a
second replay is stored once."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from control.fixtures import TailnetClient
from customers.models import Consent
from geo.google import take_call
from geo.models import ApiUsage, LocationSettings
from publicapi.models import QuoteRequest, TimeRequest

from .test_quote_requests import TimeRequestTests, signed
from .test_site_support import OfflineQuoteRequestTests
from .testing import BASE, PublicClient


class TimeRequestKeptTests(TimeRequestTests):
    def kept(self, **changes):
        self.send(self.body(**changes))
        return TimeRequest.objects.get()

    def test_an_unknown_vehicle_is_kept_unpriced(self):
        item = self.kept(vehicle={"year": 2019, "make": "Nowhere", "model": "Imaginary"})
        self.assertIsNone(item.quote)
        self.assertIn("Not priced", item.problem)

    def test_a_malformed_phone_number_is_kept_without_matching_or_consent(self):
        item = self.kept(mobile="12")
        self.assertIn("Mobile number: couldn't be read as sent", item.problem)
        self.assertEqual(item.customer.mobile, "")
        self.assertFalse(Consent.objects.exists())
        self.assertEqual(item.as_sent["mobile"], "12")

    def test_an_address_that_cant_be_matched_is_kept(self):
        item = self.kept(place_id="ChIJmadeUpNowhere00001")
        self.assertIsNone(item.service_address)
        self.assertIn("Address:", item.problem)

    def test_every_field_wrong_is_still_kept(self):
        body = self.body(
            submitted_at="yesterday", vehicle="a truck", service=99999, first_name="", mobile="none", payment_method="gold",
            consents={"version": "1999-01-01", "appointment": True}, shown={"total": "lots"}, preferred_start="soon", surprise=1,
        )
        self.send(body)
        item = TimeRequest.objects.get()
        for problem in ("When it was sent", "Vehicle", "Service", "Mobile number", "Payment method", "Text consent",
                        "Price shown", "Preferred time", "Not used: surprise", "Not sent: first_name"):
            self.assertIn(problem, item.problem)
        self.assertEqual(item.customer.first_name, "(no name given)")
        self.assertEqual(item.as_sent, json.loads(json.dumps(body)))
        self.assertIsNone(item.quote)

    def test_a_clean_request_keeps_no_copy(self):
        self.assertIsNone(self.kept().as_sent)

    def test_only_a_bad_signature_an_unreadable_body_or_no_request_id_is_refused(self):
        body = self.body()
        self.send(body, expect=401, key="a-wrong-key")
        raw, headers = signed(body)
        client = PublicClient(origin=None, visitor="104.16.0.1")
        unreadable = client.post(f"{BASE}time-requests", b"{not json", content_type="application/json", headers=signed({})[1])
        self.assertEqual(unreadable.status_code, 401)  # signed for a different body
        raw = b"{not json"
        import hashlib
        import hmac
        import time

        stamp = str(int(time.time()))
        signature = hmac.new(b"made-up-offline-signing-key-for-tests", stamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
        self.assertEqual(client.post(f"{BASE}time-requests", raw, content_type="application/json",
                                     headers={"X-Dixie-Timestamp": stamp, "X-Dixie-Signature": signature}).status_code, 400)
        self.assertEqual(self.send([1, 2], expect=400)["error"], "bad_request")
        self.assertEqual(self.send(self.body(request_id="not-a-uuid"), expect=400)["field"], "request_id")
        self.assertFalse(TimeRequest.objects.exists())

    def test_a_request_sent_twice_is_stored_once(self):
        body = self.body(mobile="12")
        self.send(body)
        self.assertTrue(self.send(body, expect=200)["duplicate"])
        self.assertEqual(TimeRequest.objects.count(), 1)

    def test_the_address_uses_the_reserve_when_the_public_share_is_used(self):
        LocationSettings.objects.filter(pk=LocationSettings.get().pk).update(place_details_public_daily_cap=0)
        item = self.kept()
        self.assertIsNotNone(item.service_address)
        usage = ApiUsage.objects.get(api=ApiUsage.Api.PLACE_DETAILS)
        self.assertEqual((usage.calls, usage.public_calls), (1, 0))

    def test_it_shows_on_needs_you_with_something_to_check(self):
        item = self.kept(mobile="12")
        owner = get_user_model().objects.create_user("owner", password="an-invented-password-1")
        tailnet = TailnetClient()
        tailnet.force_login(owner)
        self.assertContains(tailnet.get("/schedule/"), "Sent while the server was offline, something to check")
        page = tailnet.get(f"/requests/offline/{item.pk}/")
        self.assertContains(page, "Mobile number: couldn&#x27;t be read as sent")
        self.assertContains(page, "The request as it arrived")


class OfflineQuoteRequestKeptTests(OfflineQuoteRequestTests):
    def test_unreadable_fields_are_kept_with_the_problems(self):
        body = self.body(vehicle="a van", service="washing", description="", mobile="4235", condition=7)
        answer = self.send(body)
        item = QuoteRequest.objects.get(reference=answer["reference"])
        for problem in ("Vehicle", "Service", "Description", "Mobile number", "Condition"):
            self.assertIn(problem, item.problem)
        self.assertEqual(item.as_sent["vehicle"], "a van")
        self.assertEqual(item.customer.mobile, "")
        self.assertEqual(self.send(body, expect=200), {"received": True, "duplicate": True})

    def test_a_clean_request_keeps_no_copy(self):
        answer = self.send(self.body())
        self.assertIsNone(QuoteRequest.objects.get(reference=answer["reference"]).as_sent)


class TakeCallTests(TestCase):
    def test_the_public_share_stops_public_calls_and_keeps_the_reserve(self):
        for _ in range(2):
            take_call(ApiUsage.Api.PLACE_DETAILS, 3, public_cap=2)
        from geo.google import CapReached, PublicShareUsed

        with self.assertRaises(PublicShareUsed):
            take_call(ApiUsage.Api.PLACE_DETAILS, 3, public_cap=2)
        take_call(ApiUsage.Api.PLACE_DETAILS, 3)
        with self.assertRaises(CapReached):
            take_call(ApiUsage.Api.PLACE_DETAILS, 3)
        usage = ApiUsage.objects.get(api=ApiUsage.Api.PLACE_DETAILS)
        self.assertEqual((usage.calls, usage.public_calls, usage.refused, usage.public_refused), (3, 2, 2, 1))
