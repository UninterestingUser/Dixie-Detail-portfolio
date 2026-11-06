"""Calls to Google Maps Platform from the server, each counted and capped.

Every call goes through take_call, which counts it in ApiUsage for the
Pacific day (Google's quota day) and refuses it once the day's cap in
LocationSettings is reached, so a loop cannot run up a bill. Each call asks
for the fewest fields, to stay at the cheapest price tier:

- Place Details (New): address components, formatted address and location
  only, all Essentials fields. The place name would be billed at the Pro
  rate. The website's autocomplete session token is passed on, so the
  details call ends the session and the autocomplete requests before it are
  not billed.
- Routes computeRoutes: duration and distance only, with traffic predicted
  for the departure time (routing preference TRAFFIC_AWARE).

Address autocomplete runs in the customer's browser with the public browser
key, so the server never sees it; Google's own daily limit for it, set in
Google Cloud, is its cap.
"""

import datetime
import re
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import http
from .models import ApiUsage, LocationSettings

PACIFIC = ZoneInfo("America/Los_Angeles")
PLACES_URL = "https://places.googleapis.com/v1/places"
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
PLACE_DETAILS_FIELDS = "addressComponents,formattedAddress,location"
ROUTES_FIELDS = "routes.duration,routes.distanceMeters"
# Place IDs and session tokens are letters, digits, "-" and "_".
PLACE_ID = re.compile(r"^[A-Za-z0-9_-]{10,300}$")
SESSION_TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class GoogleUnavailable(Exception):
    """Google was not asked or did not answer: no key, the day's cap is
    reached, or the call failed. Callers fall back (drive times) or refuse
    (a place that cannot be looked up)."""


class CapReached(GoogleUnavailable):
    pass


def quota_day(now=None):
    """Today's date in Pacific time, the day Google's daily quotas count."""
    return (now or timezone.now()).astimezone(PACIFIC).date()


def take_call(api, cap=None):
    """Count one call to api today, or raise CapReached once cap calls have
    been made today. A refused call is counted as refused."""
    day = quota_day()
    ApiUsage.objects.get_or_create(api=api, day=day)
    with transaction.atomic():
        usage = ApiUsage.objects.select_for_update().get(api=api, day=day)
        refused = cap is not None and usage.calls >= cap
        if refused:
            usage.refused += 1
            usage.save(update_fields=["refused"])
        else:
            usage.calls += 1
            usage.save(update_fields=["calls"])
    # Raised after the block, so the refusal is counted, not rolled back.
    if refused:
        raise CapReached(f"{usage.get_api_display()} reached today's cap of {cap} calls")


def server_key():
    key = settings.GOOGLE_MAPS_SERVER_KEY
    if not key:
        raise GoogleUnavailable("no Google Maps server key (Bitwarden secret GOOGLE_MAPS_SERVER_KEY)")
    return key


def place_details(place_id, session_token=""):
    """The place's address components, formatted address and location, as
    Google's JSON. The server looks the place up itself; nothing from the
    browser but the place ID and session token is used."""
    if not PLACE_ID.match(place_id or ""):
        raise ValueError("That is not a Google place ID.")
    if session_token and not SESSION_TOKEN.match(session_token):
        raise ValueError("That is not an autocomplete session token.")
    key = server_key()
    take_call(ApiUsage.Api.PLACE_DETAILS, LocationSettings.get().place_details_daily_cap)
    params = {"languageCode": "en", "regionCode": "us"}
    if session_token:
        params["sessionToken"] = session_token
    try:
        return http.request_json(
            f"{PLACES_URL}/{place_id}", params=params,
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": PLACE_DETAILS_FIELDS},
        )
    except http.FetchError as error:
        raise GoogleUnavailable(str(error)) from error


def _lat_lng(point):
    return {"location": {"latLng": {"latitude": float(point[0]), "longitude": float(point[1])}}}


def compute_route(origin, destination, departure=None):
    """(seconds, meters) for driving from origin to destination, each a
    (latitude, longitude), with traffic predicted for departure. Google only
    predicts for the future, so a past departure asks for now."""
    key = server_key()
    take_call(ApiUsage.Api.ROUTES, LocationSettings.get().routes_daily_cap)
    body = {
        "origin": _lat_lng(origin),
        "destination": _lat_lng(destination),
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
    }
    if departure and departure > timezone.now() + datetime.timedelta(minutes=1):
        body["departureTime"] = departure.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")
    try:
        answer = http.request_json(
            ROUTES_URL, method="POST", body=body,
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": ROUTES_FIELDS},
        )
        route = answer["routes"][0]
        return int(route["duration"].rstrip("s")), int(route.get("distanceMeters", 0))
    except http.FetchError as error:
        raise GoogleUnavailable(str(error)) from error
    except (KeyError, IndexError, ValueError, AttributeError) as error:
        raise GoogleUnavailable("Routes answered without a route") from error
