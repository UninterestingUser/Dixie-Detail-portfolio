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
"""

import hashlib
import hmac
import time
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction

from billing.methods import website_methods

from . import bookings, catalog, consent, quotes, validate
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


def parse(data):
    validate.only(
        data,
        ["request_id", "submitted_at", "vehicle", "service", "place_id", "first_name", "mobile", "payment_method", "consents", "shown"],
        ["size", "condition", "add_ons", "preferred_start", "preferred_note", "last_name", "color", "session_token"],
    )
    try:
        request_id = uuid.UUID(str(data["request_id"]))
    except ValueError as error:
        raise bad_request("request_id") from error
    if data["payment_method"] not in {choice.value for choice in website_methods()}:
        raise bad_request("payment_method")
    shown = validate.only(data["shown"], ["total", "pricebook_version"], field="shown")
    try:
        shown_total = Decimal(str(shown["total"])).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as error:
        raise bad_request("shown.total") from error
    if not Decimal("0") <= shown_total < Decimal("100000"):
        raise bad_request("shown.total")
    place_id = data["place_id"]
    if not isinstance(place_id, str) or not 10 <= len(place_id) <= 300:
        raise bad_request("place_id")
    return {
        "request_id": request_id,
        "submitted_at": validate.moment(data["submitted_at"], "submitted_at"),
        "vehicle": catalog.parse_vehicle(data["vehicle"]),
        "size": validate.integer(data.get("size"), "size", 1, 9, required=False),
        "condition": validate.integer(data.get("condition"), "condition", 1, 3, required=False),
        "service": quotes.parse_service(data["service"]),
        "add_ons": quotes.parse_add_ons(data.get("add_ons")),
        "place_id": place_id,
        "session_token": validate.text(data.get("session_token"), "session_token", 64, required=False),
        "preferred_start": validate.moment(data["preferred_start"], "preferred_start") if data.get("preferred_start") else None,
        "preferred_note": validate.text(data.get("preferred_note"), "preferred_note", 300, required=False, multiline=True),
        "first_name": validate.text(data["first_name"], "first_name", 100),
        "last_name": validate.text(data.get("last_name"), "last_name", 100, required=False),
        "mobile": validate.phone(data["mobile"]),
        "payment_method": data["payment_method"],
        "color": validate.text(data.get("color"), "color", 40, required=False),
        "consents": consent.parse(data["consents"]),
        "shown_total": shown_total,
        "shown_version": validate.integer(shown["pricebook_version"], "shown.pricebook_version", 1, 100_000),
    }


def price_on_arrival(form):
    """(place or None, web quote or None, problem): the request priced now."""
    try:
        place = quotes.verify_place(form["place_id"], form["session_token"])
    except ApiError as error:
        return None, None, f"Address: {error.message}"
    try:
        found = catalog.resolve(form["vehicle"], form["size"])
        web = quotes.issue(found, form["service"], form["condition"], form["add_ons"], place, answered=form["size"])
    except ApiError as error:
        return place, None, f"Not priced: {error.message}"
    return place, web, ""


def receive(request, data):
    check_signature(request)
    form = parse(data)
    existing = TimeRequest.objects.filter(request_id=form["request_id"]).first()
    if existing is not None:
        return 200, {"received": True, "duplicate": True}
    with transaction.atomic():
        place, web, problem = price_on_arrival(form)
        # Matched quietly like a booking; an address or vehicle it brings is
        # kept off the record until the request is booked.
        typed = bookings.given(
            form["first_name"], form["last_name"], form["mobile"], place,
            bookings.quote_vehicle(web, form["color"]) if web else None,
        )
        intake = bookings.take_in(typed, form["consents"], form["mobile"], hold=True, when=form["submitted_at"])
        customer = intake.customer
        quote = web.quote if web else None
        TimeRequest.objects.create(
            request_id=form["request_id"],
            customer=customer,
            service_address=intake.address,
            vehicle=intake.vehicle,
            intake=intake.as_json(),
            submitted_at=form["submitted_at"],
            preferred_start=form["preferred_start"],
            preferred_note=form["preferred_note"],
            inputs={
                "vehicle": form["vehicle"],
                "vehicle_text": web.vehicle_text if web else "",
                "size": form["size"],
                "condition": form["condition"],
                "service": form["service"].name,
                "add_ons": [add_on.name for add_on in form["add_ons"]],
                "color": form["color"],
                "payment_method": form["payment_method"],
                "place_id": form["place_id"],
            },
            shown_total=form["shown_total"],
            shown_pricebook_version=form["shown_version"],
            quote=quote,
            price_differs=quote is not None and quote.total_before_tax != form["shown_total"],
            problem=problem[:300],
            is_test=customer.is_test,
        )
    return 201, {"received": True}
