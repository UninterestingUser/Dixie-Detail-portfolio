"""Address lookup sessions and the public share of Place Details (decision
0115): /addresses needs a session opened with a Turnstile token, a session
allows ADDRESS_LOOKUP_SESSION_LOOKUPS lookups within its minutes, and the
lookups stop at the day's public share, keeping the reserve."""

import datetime

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from control.fixtures import TailnetClient
from geo.models import ApiUsage, LocationSettings
from publicapi.models import LookupSession

from .testing import CLEVELAND, GOOD_TOKEN, ApiTestCase


class LookupSessionTests(ApiTestCase):
    def look_up(self, session, expect=201):
        response = self.client.post_json("addresses", {"place_id": CLEVELAND, "session_token": "s-1", "lookup_session": session})
        self.assertEqual(response.status_code, expect, response.content)
        return response.json()

    def test_a_session_is_opened_with_a_turnstile_token(self):
        answer = self.client.post_json("addresses/sessions", {"turnstile": GOOD_TOKEN}).json()
        self.assertEqual(answer["lookups"], 10)
        self.assertLess(datetime.datetime.fromisoformat(answer["expires_at"]), timezone.now() + datetime.timedelta(minutes=31))
        refused = self.client.post_json("addresses/sessions", {"turnstile": "refused"})
        self.assertEqual(refused.json()["error"], "turnstile_failed")

    def test_no_lookup_without_a_session(self):
        self.assertEqual(self.client.post_json("addresses", {"place_id": CLEVELAND}).status_code, 400)
        self.assertEqual(self.look_up("not-a-session", expect=403)["error"], "lookup_session")
        self.assertFalse(ApiUsage.objects.filter(api=ApiUsage.Api.PLACE_DETAILS).exists())

    @override_settings(ADDRESS_LOOKUP_SESSION_LOOKUPS=2)
    def test_a_session_allows_its_lookups_then_ends(self):
        session = self.lookup()
        self.look_up(session)
        self.look_up(session)
        self.assertEqual(self.look_up(session, expect=403)["error"], "lookup_session")

    def test_a_session_expires(self):
        session = self.lookup()
        LookupSession.objects.update(expires_at=timezone.now() - datetime.timedelta(seconds=1))
        self.assertEqual(self.look_up(session, expect=403)["error"], "lookup_session")

    def test_past_the_public_share_the_site_is_told_to_take_a_typed_address(self):
        LocationSettings.objects.filter(pk=LocationSettings.get().pk).update(place_details_daily_cap=300, place_details_public_daily_cap=1)
        self.look_up(self.lookup())
        answer = self.look_up(self.lookup(), expect=429)
        self.assertEqual(answer["error"], "lookups_used_up")
        self.assertIn("Type your address", answer["message"])
        owner = get_user_model().objects.create_user("owner", password="an-invented-password-1")
        tailnet = TailnetClient()
        tailnet.force_login(owner)
        self.assertContains(tailnet.get("/schedule/"), "The website's address lookups for today ran out")
        # The control app keeps the reserve.
        from geo.google import place_details

        place_details(CLEVELAND)
        usage = ApiUsage.objects.get(api=ApiUsage.Api.PLACE_DETAILS)
        self.assertEqual((usage.calls, usage.public_calls, usage.public_refused), (2, 1, 1))

    def test_no_notice_while_the_share_lasts(self):
        self.look_up(self.lookup())
        owner = get_user_model().objects.create_user("owner", password="an-invented-password-1")
        tailnet = TailnetClient()
        tailnet.force_login(owner)
        self.assertNotContains(tailnet.get("/schedule/"), "data-lookups-used-up")

    def test_the_share_is_on_the_location_settings_screen_and_fits_in_the_cap(self):
        from control.forms import LocationSettingsForm

        form = LocationSettingsForm(data={
            "home_line1": "100 Example St NW", "home_city": "Cleveland", "home_state": "TN", "home_zip_code": "37311",
            "place_details_daily_cap": "300", "place_details_public_daily_cap": "301", "text_search_daily_cap": "300",
            "routes_daily_cap": "150", "estimate_road_factor": "1.30", "estimate_speed_mph": "40", "drive_time_cache_days": "30",
            "tax_sourcing": "service_address",
        }, instance=LocationSettings.get())
        self.assertFalse(form.is_valid())
        self.assertIn("place_details_public_daily_cap", form.errors)
