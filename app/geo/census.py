"""The Census Bureau's free geocoder, for addresses the owner types.

It needs no key. A match gives the coordinates and the county; the owner's
own spelling of the street, city and ZIP code is kept. Calls are counted in
ApiUsage, with no cap.
"""

from . import http
from .google import take_call
from .models import ApiUsage

URL = "https://geocoding.geo.census.gov/geocoder/geographies/address"


def geocode(line1, city, state, zip_code):
    """{"latitude", "longitude", "county", "matched_address"} for the best
    match, or None when the geocoder finds no match. Raises
    http.FetchError when the geocoder cannot be reached."""
    take_call(ApiUsage.Api.CENSUS_GEOCODER)
    answer = http.request_json(
        URL,
        params={
            "street": line1, "city": city, "state": state, "zip": zip_code,
            "benchmark": "Public_AR_Current", "vintage": "Current_Current",
            "layers": "Counties", "format": "json",
        },
        timeout=20,
    )
    matches = (answer.get("result") or {}).get("addressMatches") or []
    if not matches:
        return None
    match = matches[0]
    counties = (match.get("geographies") or {}).get("Counties") or []
    return {
        "latitude": match["coordinates"]["y"],
        "longitude": match["coordinates"]["x"],
        "county": counties[0].get("BASENAME", "") if counties else "",
        "matched_address": match.get("matchedAddress", ""),
    }
