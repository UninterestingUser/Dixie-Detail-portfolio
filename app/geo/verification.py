"""Verifying an address: its parts, coordinates, county and tax jurisdiction.

- A website address arrives as a Google place ID (with the autocomplete
  session token). The server looks the place up itself with the server key
  (google.place_details) and takes the parts, coordinates and county from
  Google's answer. Coordinates sent from a browser are never trusted.
- An address the owner types in the control app is checked with the Census
  Bureau's free geocoder, which gives the coordinates and county.
- An address neither can find, such as a new street, can be marked verified
  by hand, with the county and, if the owner has them, coordinates.

Each then gets its tax jurisdiction (billing.tax.assign_jurisdiction).
"""

from decimal import Decimal

from django.utils import timezone

from billing.tax import assign_jurisdiction
from customers.models import Address

from . import census, google
from .service_area import nice_county


class VerificationError(ValueError):
    """The address cannot be verified as given."""


def _coordinate(value):
    return Decimal(str(round(float(value), 6)))


def _finish(address, method):
    address.verification = method
    address.verified_at = timezone.now()
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
    for name, value in parts.items():
        setattr(address, name, value)
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


def verify_by_hand(address, county="", latitude=None, longitude=None):
    """Mark address verified by the owner, with the county and coordinates
    they give (not saved). Without coordinates the address cannot match a rate
    boundary, so it takes its county's rate and is flagged."""
    address.county = nice_county(county) if county else address.county
    address.latitude = _coordinate(latitude) if latitude is not None else None
    address.longitude = _coordinate(longitude) if longitude is not None else None
    address.google_place_id = ""
    return _finish(address, Address.Verification.BY_HAND)
