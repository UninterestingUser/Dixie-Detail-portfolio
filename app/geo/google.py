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
- Text Search (New): place IDs only (field mask places.id), the IDs Only
  tier, which Google does not charge for. It is the fallback for an address
  the owner typed that the Census geocoder cannot find; the one place ID it
  gives is then looked up with Place Details as above, without a session.
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
TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
PLACE_DETAILS_FIELDS = "addressComponents,formattedAddress,location"
TEXT_SEARCH_FIELDS = "places.id"
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


class PublicShareUsed(CapReached):
    """The website's public share of the day's calls is used up; the reserve
    is kept for the control app (decision 0115)."""


def take_call(api, cap=None, public_cap=None):
    """Count one call to api today, or raise CapReached once cap calls have
    been made today. A refused call is counted as refused. With public_cap,
    the call is one of the website's public lookups: it is refused, with
    PublicShareUsed, once public_cap of those have been made today, so the
    rest of the cap stays for the control app."""
    day = quota_day()
    ApiUsage.objects.get_or_create(api=api, day=day)
    public = public_cap is not None
    with transaction.atomic():
        usage = ApiUsage.objects.select_for_update().get(api=api, day=day)
        over_cap = cap is not None and usage.calls >= cap
        over_share = public and usage.public_calls >= public_cap
        refused = over_cap or over_share
        fields = []
        if refused:
            usage.refused += 1
            fields.append("refused")
            if public:
                usage.public_refused += 1
                fields.append("public_refused")
        else:
            usage.calls += 1
            fields.append("calls")
            if public:
                usage.public_calls += 1
                fields.append("public_calls")
        usage.save(update_fields=fields)
    # Raised after the block, so the refusal is counted, not rolled back.
    if over_share and not over_cap:
        raise PublicShareUsed(f"{usage.get_api_display()} used today's public share of {public_cap} calls")
    if refused:
        raise CapReached(f"{usage.get_api_display()} reached today's cap of {cap} calls")


def public_share_used(day=None):
    """Whether today's public share of Place Details is used up, for the
    control app's notice (decision 0115)."""
    usage = ApiUsage.objects.filter(api=ApiUsage.Api.PLACE_DETAILS, day=day or quota_day()).first()
    return usage is not None and (usage.public_refused > 0 or usage.public_calls >= LocationSettings.get().place_details_public_daily_cap)


def server_key():
    key = settings.GOOGLE_MAPS_SERVER_KEY
    if not key:
        raise GoogleUnavailable("no Google Maps server key (Bitwarden secret GOOGLE_MAPS_SERVER_KEY)")
    return key


def place_details(place_id, session_token="", public=False):
    """The place's address components, formatted address and location, as
    Google's JSON. The server looks the place up itself; nothing from the
    browser but the place ID and session token is used. public is a
    website lookup, counted against the public share (decision 0115)."""
    if not PLACE_ID.match(place_id or ""):
        raise ValueError("That is not a Google place ID.")
    if session_token and not SESSION_TOKEN.match(session_token):
        raise ValueError("That is not an autocomplete session token.")
    key = server_key()
    location = LocationSettings.get()
    take_call(
        ApiUsage.Api.PLACE_DETAILS, location.place_details_daily_cap,
        public_cap=location.place_details_public_daily_cap if public else None,
    )
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


def text_search(query):
    """The place ID of Google's best match for query, a typed address, or
    None when Google finds nothing."""
    key = server_key()
    take_call(ApiUsage.Api.TEXT_SEARCH, LocationSettings.get().text_search_daily_cap)
    body = {"textQuery": query, "languageCode": "en", "regionCode": "us", "pageSize": 1}
    try:
        answer = http.request_json(
            TEXT_SEARCH_URL, method="POST", body=body,
            headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": TEXT_SEARCH_FIELDS},
        )
    except http.FetchError as error:
        raise GoogleUnavailable(str(error)) from error
    places = answer.get("places") or []
    place_id = places[0].get("id", "") if places else ""
    return place_id if PLACE_ID.match(place_id) else None


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
