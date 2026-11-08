"""The Google Calendar API, called as the service account both calendars are
shared with (decisions 0006 and 0098).

The service account's JSON key is a Bitwarden secret, handed to the app as a
file on an in-memory mount (settings GOOGLE_SERVICE_ACCOUNT_JSON). The app signs a
short token request with it (the OAuth 2.0 JWT bearer flow) and asks only
for the calendar.events scope: it reads and writes events on the calendars
shared with it, and sees nothing else in the Workspace. The access token
lives in memory for its hour.

Tests never reach this module's network calls: they install a fake client
(calendars.testing) with use_client().
"""

import base64
import json
import time
from contextlib import contextmanager
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.conf import settings

API = "https://www.googleapis.com/calendar/v3"
SCOPE = "https://www.googleapis.com/auth/calendar.events"
USER_AGENT = "dixie-detail/1.0"


class CalendarError(Exception):
    """Google could not be reached or refused the call; the change is tried
    again later."""


class NotConnected(CalendarError):
    """No service account key or calendar IDs: the sync waits."""


class NotFound(CalendarError):
    pass


class Conflict(CalendarError):
    pass


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class GoogleCalendar:
    """The few Calendar API calls the sync makes."""

    def __init__(self, key_json, timeout=15):
        key = json.loads(key_json)
        self.email = key["client_email"]
        self.private_key = key["private_key"]
        self.token_uri = key.get("token_uri", "https://oauth2.googleapis.com/token")
        self.timeout = timeout
        self.token, self.token_expires = None, 0

    # Signing in ---------------------------------------------------------

    def assertion(self, now):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        header = b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = b64(json.dumps({
            "iss": self.email, "scope": SCOPE, "aud": self.token_uri, "iat": now, "exp": now + 3600,
        }).encode())
        signing_input = f"{header}.{claims}".encode()
        key = serialization.load_pem_private_key(self.private_key.encode(), password=None)
        signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        return f"{header}.{claims}.{b64(signature)}"

    def access_token(self):
        now = int(time.time())
        if self.token and now < self.token_expires - 60:
            return self.token
        body = urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": self.assertion(now)}).encode()
        answer = self.send(Request(self.token_uri, data=body, method="POST", headers={
            "Content-Type": "application/x-www-form-urlencoded", "User-Agent": USER_AGENT,
        }))
        self.token, self.token_expires = answer["access_token"], now + int(answer.get("expires_in", 3600))
        return self.token

    # Calls -----------------------------------------------------------------

    def send(self, request):
        try:
            with urlopen(request, timeout=self.timeout) as response:
                data = response.read()
        except HTTPError as error:
            if error.code in (404, 410):
                raise NotFound(f"Google Calendar answered {error.code}") from error
            if error.code == 409:
                raise Conflict("Google Calendar answered 409") from error
            raise CalendarError(f"Google Calendar answered {error.code}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise CalendarError(f"Google Calendar could not be reached: {error}") from error
        try:
            return json.loads(data) if data else {}
        except ValueError as error:
            raise CalendarError("Google Calendar did not answer with JSON") from error

    def call(self, method, path, *, params=None, body=None):
        url = f"{API}{path}" + (f"?{urlencode(params)}" if params else "")
        headers = {"Authorization": f"Bearer {self.access_token()}", "User-Agent": USER_AGENT, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        return self.send(Request(url, data=data, method=method, headers=headers))

    @staticmethod
    def events_path(calendar_id, event_id=None):
        path = f"/calendars/{quote(calendar_id, safe='')}/events"
        return path + (f"/{quote(event_id, safe='')}" if event_id else "")

    def list_events(self, calendar_id, time_min, time_max=None, show_deleted=False):
        """Every event from time_min (to time_max), repeating events expanded
        into their single visits."""
        params = {"singleEvents": "true", "timeMin": time_min.isoformat(), "maxResults": "2500",
                  "showDeleted": "true" if show_deleted else "false"}
        if time_max is not None:
            params["timeMax"] = time_max.isoformat()
        found, page = [], None
        while True:
            answer = self.call("GET", self.events_path(calendar_id), params={**params, **({"pageToken": page} if page else {})})
            found += answer.get("items", [])
            page = answer.get("nextPageToken")
            if not page:
                return found

    def get_event(self, calendar_id, event_id):
        return self.call("GET", self.events_path(calendar_id, event_id))

    def insert_event(self, calendar_id, event_id, body):
        # sendUpdates=none: nobody is emailed. The events have no guests anyway.
        return self.call("POST", self.events_path(calendar_id), params={"sendUpdates": "none"}, body={**body, "id": event_id})

    def update_event(self, calendar_id, event_id, body):
        return self.call("PUT", self.events_path(calendar_id, event_id), params={"sendUpdates": "none"}, body=body)

    def delete_event(self, calendar_id, event_id):
        self.call("DELETE", self.events_path(calendar_id, event_id), params={"sendUpdates": "none"})


_client = None
_override = None


def connected():
    return bool(_override or (settings.GOOGLE_SERVICE_ACCOUNT_JSON and settings.GOOGLE_CALENDAR_JOBS_ID and settings.GOOGLE_CALENDAR_TIME_OFF_ID))


def client():
    """The Calendar client, or NotConnected when the key or the calendar IDs
    are missing."""
    global _client
    if _override is not None:
        return _override
    if not connected():
        raise NotConnected("The Google calendars are not connected: no service account key or calendar IDs.")
    if _client is None:
        _client = GoogleCalendar(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
    return _client


def jobs_calendar():
    return settings.GOOGLE_CALENDAR_JOBS_ID or "jobs"


def time_off_calendar():
    return settings.GOOGLE_CALENDAR_TIME_OFF_ID or "time-off"


@contextmanager
def short_timeout(api, seconds):
    """Give up on Google sooner, for a call made while someone waits, such
    as the Time Off copy as a booking is sent."""
    if not hasattr(api, "timeout"):
        yield api
        return
    before, api.timeout = api.timeout, seconds
    try:
        yield api
    finally:
        api.timeout = before


@contextmanager
def use_client(fake):
    """Use fake as the client, for tests."""
    global _override
    before, _override = _override, fake
    try:
        yield fake
    finally:
        _override = before
