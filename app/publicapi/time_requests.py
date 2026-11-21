"""Offline "request a time" forms (decision 0100).

While the server is offline, the website's form becomes a "request a time"
form, priced from the last published pricebook, and Cloudflare holds what
the customer sends. When the server is back, Cloudflare's piece (Phase 3
Step 6) replays each one here. A Turnstile token would have expired by
then, so Cloudflare checks it when the customer sends the form, and signs
each replay with the Bitwarden secret OFFLINE_REQUESTS_SIGNING_KEY:

    X-Dixie-Timestamp: seconds since 1970, within 5 minutes of now
    X-Dixie-Signature: hex HMAC-SHA256 of "<timestamp>.<raw body>"

A request is not an appointment. It is priced on arrival from the pricebook
in effect, and flagged for the owner when that price differs from the one
the customer saw. The website's request id makes a second replay harmless.

The address is a Google place id, looked up on arrival, or, when the
website's address suggestions were down too (such as once the day's Google
limit is used up), the address as typed, kept unchecked with a note for the
owner. The vehicle is the year, make and model, or the photo card the
customer picked with whatever year, make and model they typed.
"""

import hashlib
import hmac
import time
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from billing.methods import saved_method

from . import bookings, catalog, consent, lenient, quotes, validate
from .http import ApiError, bad_request
from .models import TimeRequest

SIGNATURE_WINDOW_SECONDS = 300


def refused():
    return ApiError(401, "unsigned", "This address only takes requests from the website.")


def check_signature(request):
    key = settings.OFFLINE_REQUESTS_SIGNING_KEY
    if not key:
        raise refused()
    stamp = request.headers.get("X-Dixie-Timestamp", "")
    signature = request.headers.get("X-Dixie-Signature", "")
    if not stamp.isdigit() or abs(time.time() - int(stamp)) > SIGNATURE_WINDOW_SECONDS:
        raise refused()
    expected = hmac.new(key.encode(), stamp.encode() + b"." + request.body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.lower()):
        raise refused()


REQUIRED = ["request_id", "submitted_at", "vehicle", "service", "first_name", "mobile", "payment_method", "consents", "shown"]
OPTIONAL = ["size", "condition", "add_ons", "preferred_start", "preferred_note", "last_name", "color", "session_token", "place_id", "address"]
NO_NAME = "(no name given)"


def read_shown(shown):
    validate.only(shown, ["total", "pricebook_version"], field="shown")
    try:
        total = Decimal(str(shown["total"])).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as error:
        raise bad_request("shown.total") from error
    if not Decimal("0") <= total < Decimal("100000"):
        raise bad_request("shown.total")
    return total, validate.integer(shown["pricebook_version"], "shown.pricebook_version", 1, 100_000)


def read_payment_method(value):
    method = saved_method(value)
    if method is None:
        raise bad_request("payment_method")
    return method.value


def parse(data):
    """The form's fields, each read on its own (decision 0114): one that
    can't be read is left empty and its problem listed, so the request is
    kept whatever it holds. Returns (form, Lenient)."""
    form = {"request_id": lenient.request_id(data)}
    read = lenient.Lenient(data, REQUIRED, OPTIONAL)
    get = data.get
    form["submitted_at"] = read.take("When it was sent", lambda: validate.moment(data["submitted_at"], "submitted_at"))
    form["vehicle"] = read.take("Vehicle", lambda: catalog.parse_vehicle(data["vehicle"], free_text_with_card=True))
    form["size"] = read.take("Size", lambda: validate.integer(get("size"), "size", 1, 9, required=False))
    form["condition"] = read.take("Condition", lambda: validate.integer(get("condition"), "condition", 1, 3, required=False))
    form["service"] = read.take("Service", lambda: quotes.parse_service(data["service"]))
    form["add_ons"] = read.take("Add-ons", lambda: quotes.parse_add_ons(get("add_ons")), [])
    form["place_id"], form["address"] = read.take("Address", lambda: typed_place(data), (None, ""))
    form["session_token"] = read.take("Address", lambda: validate.text(get("session_token"), "session_token", 64, required=False), "")
    form["preferred_start"] = read.take(
        "Preferred time", lambda: validate.moment(data["preferred_start"], "preferred_start") if get("preferred_start") else None
    )
    form["preferred_note"] = read.take(
        "Note", lambda: validate.text(get("preferred_note"), "preferred_note", 300, required=False, multiline=True), ""
    )
    form["first_name"] = read.take("First name", lambda: validate.text(data["first_name"], "first_name", 100), NO_NAME)
    form["last_name"] = read.take("Last name", lambda: validate.text(get("last_name"), "last_name", 100, required=False), "")
    form["mobile"] = read.take("Mobile number", lambda: validate.phone(data["mobile"]), "")
    form["payment_method"] = read.take("Payment method", lambda: read_payment_method(data["payment_method"]), "")
    form["color"] = read.take("Color", lambda: validate.text(get("color"), "color", 40, required=False), "")
    form["consents"] = read.take("Text consent", lambda: consent.parse(data["consents"]))
    form["shown_total"], form["shown_version"] = read.take("Price shown", lambda: read_shown(data["shown"]), (None, None))
    return form, read


def typed_place(data, field="place_id"):
    """(place id, None) or (None, typed address): exactly one is given."""
    place_id, address = data.get("place_id"), data.get("address")
    if (place_id is None) == (address is None):
        raise bad_request(field, "Send the place id from the address suggestions, or the address as typed.")
    if place_id is not None:
        if not isinstance(place_id, str) or not 10 <= len(place_id) <= 300:
            raise bad_request("place_id")
        return place_id, ""
    return None, validate.text(address, "address", 200)


def unchecked_address(text):
    return f"Address typed while address suggestions were down, not checked: {text}"


def price_on_arrival(form):
    """(place or None, web quote or None, problem): the request priced now.
    The address is looked up from the server's reserve of Google calls, not
    the website's public share (decision 0115)."""
    place, problem = None, ""
    if form["place_id"] is None:
        # Priced without sales tax: there is no checked address to tax.
        problem = unchecked_address(form["address"]) if form["address"] else "No address given"
    else:
        try:
            place = quotes.verify_place(form["place_id"], form["session_token"], public=False)
        except ApiError as error:
            return None, None, f"Address: {error.message}"
    if form["vehicle"] is None or form["service"] is None:
        return place, None, "; ".join(filter(None, [problem, "Not priced: the vehicle or service couldn't be read"]))
    try:
        found = catalog.resolve(form["vehicle"], form["size"])
        web = quotes.issue(found, form["service"], form["condition"], form["add_ons"], place, answered=form["size"])
    except ApiError as error:
        return place, None, "; ".join(filter(None, [problem, f"Not priced: {error.message}"]))
    return place, web, problem


def receive(request, data):
    """Keep a replayed request, whatever it holds (decision 0114). Refused
    only for a bad signature, a body that can't be read, or no request id."""
    check_signature(request)
    form, read = parse(data)
    existing = TimeRequest.objects.filter(request_id=form["request_id"]).first()
    if existing is not None:
        return 200, {"received": True, "duplicate": True}
    unreadable = bool(read.problems)
    with transaction.atomic():
        place, web, problem = price_on_arrival(form)
        read.note(problem)
        # Matched quietly like a booking; an address or vehicle it brings is
        # kept off the record until the request is booked. A number that
        # can't be read matches nobody.
        typed = bookings.given(
            form["first_name"], form["last_name"], form["mobile"], place,
            bookings.quote_vehicle(web, form["color"]) if web else None,
        )
        intake = bookings.take_in(typed, form["consents"], form["mobile"], hold=True, when=form["submitted_at"] or timezone.now())
        customer = intake.customer
        quote = web.quote if web else None
        problems = read.problem_text()
        TimeRequest.objects.create(
            request_id=form["request_id"],
            customer=customer,
            service_address=intake.address,
            vehicle=intake.vehicle,
            intake=intake.as_json(),
            submitted_at=form["submitted_at"] or timezone.now(),
            preferred_start=form["preferred_start"],
            preferred_note=form["preferred_note"],
            inputs={
                "vehicle": form["vehicle"],
                "vehicle_text": web.vehicle_text if web else "",
                "size": form["size"],
                "condition": form["condition"],
                "service": form["service"].name if form["service"] else "",
                "add_ons": [add_on.name for add_on in form["add_ons"]],
                "color": form["color"],
                "payment_method": form["payment_method"],
                "place_id": form["place_id"],
                "address": form["address"],
            },
            shown_total=form["shown_total"],
            shown_pricebook_version=form["shown_version"],
            quote=quote,
            price_differs=quote is not None and form["shown_total"] is not None and quote.total_before_tax != form["shown_total"],
            problem=problems,
            # Kept as sent when anything couldn't be read, so nothing is lost.
            as_sent=data if unreadable else None,
            is_test=customer.is_test,
        )
    return 201, {"received": True}
