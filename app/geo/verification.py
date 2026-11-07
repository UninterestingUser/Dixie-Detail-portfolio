"""Verifying an address: its parts, coordinates, county and tax jurisdiction.

- A website address arrives as a Google place ID (with the autocomplete
  session token). The server looks the place up itself with the server key
  (google.place_details) and takes the parts, coordinates and county from
  Google's answer. Coordinates sent from a browser are never trusted.
- An address the owner types in the control app is checked with the Census
  Bureau's free geocoder, which gives the coordinates and county
  (verify_typed). The Census map lacks streets in new neighborhoods, so when
  it finds nothing, Google's Text Search is asked for the address and its
  one best match is looked up with Place Details. The match is used only if
  its house number, street and ZIP code agree with the typed address; the
  owner's own spelling is kept either way.
- For an address neither finds, the owner pastes the location from Google
  Maps (verify_by_hand), and the address records who set it.

Each then gets its tax jurisdiction from its coordinates and the Tennessee
boundaries (billing.tax.assign_jurisdiction).
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from billing.tax import assign_jurisdiction
from customers.models import Address

from . import census, google
from .service_area import nice_county


class VerificationError(ValueError):
    """The address cannot be verified as given."""


@dataclass(frozen=True)
class Outcome:
    """How verify_typed went. method is the Address.Verification value, or
    empty when the address stays unmatched, with the reason. google_off is
    set when Google could not be asked at all (no key, the day's cap reached
    or no answer), so a long run can stop asking."""

    method: str
    reason: str = ""
    google_off: bool = False

    @property
    def matched(self):
        return bool(self.method)


def _coordinate(value):
    return Decimal(str(round(float(value), 6)))


def _finish(address, method, user=None):
    address.verification = method
    address.verified_at = timezone.now()
    address.verified_by = user
    assign_jurisdiction(address)
    # Tells Address.save these parts were just verified.
    address._verified_now = True
    return address


def parts_from_place(answer):
    """Address parts, coordinates and county from a Place Details answer.
    Only a street address in the United States is accepted."""
    found = {}
    for component in answer.get("addressComponents") or []:
        for kind in component.get("types") or []:
            found.setdefault(kind, component)

    def text(kind, short=False):
        component = found.get(kind)
        return (component.get("shortText" if short else "longText") or "").strip() if component else ""

    if text("country", short=True) != "US":
        raise VerificationError("Pick an address in the United States.")
    if not text("street_number") or not text("route"):
        raise VerificationError("Pick a street address with a house number, not a town or a road.")
    location = answer.get("location") or {}
    if "latitude" not in location or "longitude" not in location:
        raise VerificationError("Google gave no location for that place.")
    city = text("locality") or text("postal_town") or text("sublocality") or text("administrative_area_level_3")
    county = text("administrative_area_level_2")
    return {
        "house_number": text("street_number"),
        "street": text("route", short=True),
        "line1": f"{text('street_number')} {text('route', short=True)}",
        "line2": text("subpremise"),
        "city": city,
        "state": text("administrative_area_level_1", short=True),
        "zip_code": text("postal_code"),
        "county": nice_county(county) if county else "",
        "latitude": _coordinate(location["latitude"]),
        "longitude": _coordinate(location["longitude"]),
    }


def address_from_place(customer, place_id, session_token="", address=None):
    """A verified, unsaved Address for customer from a Google place ID.
    Raises VerificationError, google.GoogleUnavailable or ValueError."""
    parts = parts_from_place(google.place_details(place_id, session_token))
    address = address or Address(customer=customer)
    for name in ("line1", "line2", "city", "state", "zip_code", "county", "latitude", "longitude"):
        setattr(address, name, parts[name])
    address.google_place_id = place_id
    return _finish(address, Address.Verification.GOOGLE_PLACE)


def verify_with_census(address):
    """Check address with the Census geocoder. On a match, set its
    coordinates, county and jurisdiction (not saved) and return True; return
    False when there is no match. Raises http.FetchError when the geocoder
    cannot be reached."""
    match = census.geocode(address.line1, address.city, address.state, address.zip_code)
    if match is None:
        return False
    address.latitude = _coordinate(match["latitude"])
    address.longitude = _coordinate(match["longitude"])
    address.county = nice_county(match["county"]) if match["county"] else ""
    address.google_place_id = ""
    _finish(address, Address.Verification.CENSUS)
    return True


# Comparing a typed street with Google's. Both sides are put in the same
# form: capitals, no punctuation, the usual USPS abbreviations, and anything
# from a unit word on dropped, so "300 Pretend Road Southeast" and Google's
# "300" + "Pretend Rd SE" agree.
ABBREVIATIONS = {
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
    "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW",
    "ALLEY": "ALY", "AVENUE": "AVE", "AV": "AVE", "BEND": "BND", "BOULEVARD": "BLVD",
    "CENTER": "CTR", "CIRCLE": "CIR", "COURT": "CT", "COVE": "CV", "CREEK": "CRK",
    "CROSSING": "XING", "DRIVE": "DR", "ESTATES": "ESTS", "EXTENSION": "EXT",
    "EXPRESSWAY": "EXPY", "FORK": "FRK", "GARDENS": "GDNS", "GLEN": "GLN", "GROVE": "GRV",
    "HEIGHTS": "HTS", "HIGHWAY": "HWY", "HILL": "HL", "HILLS": "HLS", "HOLLOW": "HOLW",
    "KNOLL": "KNL", "LAKE": "LK", "LANDING": "LNDG", "LANE": "LN", "MEADOW": "MDW",
    "MEADOWS": "MDWS", "MILL": "ML", "MOUNT": "MT", "MOUNTAIN": "MTN", "ORCHARD": "ORCH",
    "PARKWAY": "PKWY", "PLACE": "PL", "PLAZA": "PLZ", "POINT": "PT", "RIDGE": "RDG",
    "ROAD": "RD", "ROUTE": "RTE", "SPRING": "SPG", "SPRINGS": "SPGS", "SQUARE": "SQ",
    "STREET": "ST", "SUMMIT": "SMT", "TERRACE": "TER", "TRACE": "TRCE", "TRAIL": "TRL",
    "TURNPIKE": "TPKE", "VALLEY": "VLY", "VIEW": "VW", "VILLAGE": "VLG", "VISTA": "VIS",
    "WOODS": "WDS",
    "FIRST": "1ST", "SECOND": "2ND", "THIRD": "3RD", "FOURTH": "4TH", "FIFTH": "5TH",
    "SIXTH": "6TH", "SEVENTH": "7TH", "EIGHTH": "8TH", "NINTH": "9TH", "TENTH": "10TH",
}
UNIT_WORDS = {"APT", "APARTMENT", "UNIT", "STE", "SUITE", "LOT", "BLDG", "BUILDING", "TRLR", "#"}


def _words(text):
    words = re.sub(r"[^A-Z0-9#]+", " ", (text or "").upper().replace("#", " # ")).split()
    for position, word in enumerate(words):
        if word in UNIT_WORDS:
            words = words[:position]
            break
    return [ABBREVIATIONS.get(word, word) for word in words]


def street_key(street):
    return " ".join(_words(street))


def split_line1(line1):
    """(house number, street key) of a typed first line."""
    words = _words(line1)
    if words and words[0][0].isdigit():
        return words[0], " ".join(words[1:])
    return "", " ".join(words)


def differences(address, parts):
    """The parts of a Google match that do not agree with address: any of
    house number, street and ZIP code."""
    number, street = split_line1(address.line1)
    found = []
    if not number or number != parts["house_number"].upper():
        found.append("house number")
    if not street or street != street_key(parts["street"]):
        found.append("street")
    if (address.zip_code or "").strip()[:5] != parts["zip_code"][:5]:
        found.append("ZIP code")
    return found


def _joined(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def verify_with_google(address):
    """Ask Google for a typed address the Census geocoder could not find.
    On a match that agrees, set its coordinates, county and jurisdiction
    (not saved). Never raises for Google's sake: returns an Outcome."""
    query = ", ".join(part for part in (address.line1, address.city, f"{address.state} {address.zip_code}".strip()) if part)
    try:
        place_id = google.text_search(query)
        if place_id is None:
            return Outcome("", "Google found no match")
        parts = parts_from_place(google.place_details(place_id))
    except google.GoogleUnavailable as error:
        return Outcome("", f"Google not asked: {error}", google_off=True)
    except VerificationError:
        return Outcome("", "Google's best match is not a street address")
    differ = differences(address, parts)
    if differ:
        return Outcome("", f"Google's best match has a different {_joined(differ)}")
    address.latitude = parts["latitude"]
    address.longitude = parts["longitude"]
    address.county = parts["county"]
    address.google_place_id = place_id
    _finish(address, Address.Verification.GOOGLE_SEARCH)
    return Outcome(Address.Verification.GOOGLE_SEARCH)


def verify_typed(address, ask_google=True):
    """Verify an address the owner typed: the Census geocoder, then Google
    when the geocoder finds nothing and ask_google is set. Raises
    http.FetchError when the Census geocoder cannot be reached."""
    if verify_with_census(address):
        return Outcome(Address.Verification.CENSUS)
    if not ask_google:
        return Outcome("", "the Census geocoder found no match")
    return verify_with_google(address)


# A location pasted from Google Maps: "35.16123, -84.87701". Right-clicking
# a spot in Google Maps shows its coordinates, latitude first; clicking them
# copies them.
LOCATION = re.compile(r"^\s*\(?\s*(-?\d{1,3}(?:\.\d+)?)\s*[,\s]\s*(-?\d{1,3}(?:\.\d+)?)\s*\)?\s*$")


def parse_location(text):
    """(latitude, longitude) from a pasted location, or VerificationError.
    The point must be in the United States, which also catches the two
    numbers pasted the wrong way round."""
    match = LOCATION.match(text or "")
    if not match:
        raise VerificationError("Paste the latitude and longitude from Google Maps, such as 35.16123, -84.87701.")
    try:
        latitude, longitude = (_coordinate(value) for value in match.groups())
    except (InvalidOperation, ValueError) as error:
        raise VerificationError("Those are not coordinates.") from error
    if not (17 <= latitude <= 72 and -180 <= longitude <= -64):
        raise VerificationError("That point is not in the United States. Paste the latitude first, then the longitude, as Google Maps copies them.")
    return latitude, longitude


def verify_by_hand(address, latitude, longitude, user=None, county=""):
    """Set address's location by hand (not saved): the coordinates the owner
    pasted, and who set them. The tax comes from the location as usual. In
    Tennessee the boundary gives the county; county is used where none
    matches, and for an address in another state."""
    if latitude is None or longitude is None:
        raise VerificationError("Give the latitude and longitude.")
    address.county = nice_county(county) if county else address.county
    address.latitude = _coordinate(latitude)
    address.longitude = _coordinate(longitude)
    address.google_place_id = ""
    return _finish(address, Address.Verification.BY_HAND, user)
