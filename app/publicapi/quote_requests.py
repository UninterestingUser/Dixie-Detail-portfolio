"""Quote requests: the path for any job the site can't price: any vehicle
in a class booked by quote, today Full-size Vans (decision 0099), and Full
Detail or Interior Only at a condition level booked by quote, today Level 3
(decision 0103). A class or level the owner later sets to "Ask for a
quote" uses it with no new code. The request carries the service, the
condition level and the add-ons the customer wants.

1. The website opens an upload session after a Turnstile check.
2. Each photo uploads on its own as the customer picks it, so one slow
   photo never loses the form. Each is checked and saved as a clean JPEG
   (photos.py). Up to QUOTE_REQUEST_MAX_PHOTOS per request.
3. The request names the session's photos it keeps. It is not an
   appointment and holds no time; the owner replies with a price.

While the server is offline, or the address suggestions are down, the
website still takes the request, without photos: Cloudflare's piece holds it
and replays it, signed, to `quote-requests/offline` (receive_offline), as it
does a "request a time" form (time_requests, decision 0100). The customer is
told photos can be sent later by text.

Photos never attached to a sent request are deleted after a day, and a
closed request's photos QUOTE_REQUEST_PHOTO_DAYS after it closed
(cleanup.py). The description stays.
"""

import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from pricebook.models import Price
from pricebook.pricing import NotPriced, base_price

from . import bookings, catalog, consent, lenient, photos, quotes, turnstile, validate
from .http import ApiError, bad_request, not_found, visitor_key
from .models import QuotePhoto, QuoteRequest, UploadSession

SESSION_HOURS = 6
THANKS = (
    "Thanks! We've got your request and will reply with a price, usually within a day. "
    "Your request number is {reference}."
)


def open_session(request, data):
    validate.only(data, ["turnstile"])
    smoke_test = turnstile.check(request, data["turnstile"])
    session = UploadSession.objects.create(
        visitor=visitor_key(request),
        is_smoke_test=smoke_test,
        expires_at=timezone.now() + datetime.timedelta(hours=SESSION_HOURS),
    )
    return 201, {
        "session": session.token,
        "expires_at": session.expires_at.isoformat(),
        "max_photos": settings.QUOTE_REQUEST_MAX_PHOTOS,
        "max_megabytes": settings.QUOTE_REQUEST_PHOTO_MAX_MB,
    }


def live_session(token):
    session = UploadSession.objects.filter(token=token, expires_at__gt=timezone.now()).first()
    if session is None:
        raise not_found("That upload has expired. Please reload the page and add the photos again.")
    if session.photos.filter(request__isnull=False).exists():
        raise ApiError(409, "session_used", "Those photos were already sent with a request.")
    return session


def upload(request, token):
    """One photo, sent as multipart form data in the field "photo"."""
    validate.token(token, "session")
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    # The form's own fields take a few hundred bytes around the photo.
    if length > photos.max_bytes() + 65_536:
        raise photos.too_large()
    if not request.content_type == "multipart/form-data":
        raise bad_request("photo")
    session = live_session(token)
    if session.photos.count() >= settings.QUOTE_REQUEST_MAX_PHOTOS:
        raise ApiError(422, "too_many_photos", f"A request can have up to {settings.QUOTE_REQUEST_MAX_PHOTOS} photos.")
    if set(request.FILES) != {"photo"} or len(request.FILES.getlist("photo")) != 1 or request.POST:
        raise bad_request("photo")
    uploaded = request.FILES["photo"]
    if uploaded.size > photos.max_bytes():
        raise photos.too_large()
    jpeg, width, height = photos.clean_jpeg(uploaded.read(photos.max_bytes() + 1))
    name = photos.store(jpeg)
    with transaction.atomic():
        # Counted again under a lock, so two uploads at once can't pass the limit.
        UploadSession.objects.select_for_update().get(pk=session.pk)
        if session.photos.count() >= settings.QUOTE_REQUEST_MAX_PHOTOS:
            photos.delete_file(name)
            raise ApiError(422, "too_many_photos", f"A request can have up to {settings.QUOTE_REQUEST_MAX_PHOTOS} photos.")
        photo = QuotePhoto.objects.create(session=session, file_name=name, width=width, height=height, bytes=len(jpeg))
    return 201, {"photo": photo.public_id, "width": width, "height": height}


def remove(request, token, photo_id):
    validate.token(token, "session")
    validate.token(photo_id, "photo")
    session = live_session(token)
    photo = session.photos.filter(public_id=photo_id, request__isnull=True).first()
    if photo is None:
        raise not_found()
    photos.delete_photos([photo])
    return 200, {"deleted": True}


def parse(data):
    validate.only(
        data,
        ["vehicle", "service", "description", "place", "first_name", "mobile", "consents", "turnstile"],
        ["last_name", "preferred_days", "session", "photos", "size", "condition", "add_ons"],
    )
    service = data["service"]
    if service != "not_sure":
        service = quotes.parse_service(service)
    else:
        service = None
    condition = validate.integer(data.get("condition"), "condition", 1, 3, required=False)
    if service is None and condition is not None:
        raise bad_request("condition", quotes.CONDITION_NOT_TAKEN)
    photo_ids = data.get("photos") or []
    if not isinstance(photo_ids, list) or len(photo_ids) > settings.QUOTE_REQUEST_MAX_PHOTOS:
        raise ApiError(422, "too_many_photos", f"A request can have up to {settings.QUOTE_REQUEST_MAX_PHOTOS} photos.")
    photo_ids = [validate.token(item, "photos") for item in photo_ids]
    if len(set(photo_ids)) != len(photo_ids):
        raise bad_request("photos")
    if photo_ids and not data.get("session"):
        raise bad_request("session")
    return {
        "vehicle": catalog.parse_vehicle(data["vehicle"], free_text_with_card=True),
        "size": validate.integer(data.get("size"), "size", 1, 9, required=False),
        "service": service,
        "condition": condition,
        "add_ons": quotes.parse_add_ons(data.get("add_ons")),
        "description": validate.text(data["description"], "description", 2000, multiline=True),
        "place": validate.token(data["place"], "place"),
        "first_name": validate.text(data["first_name"], "first_name", 100),
        "last_name": validate.text(data.get("last_name"), "last_name", 100, required=False),
        "mobile": validate.phone(data["mobile"]),
        "consents": consent.parse(data["consents"]),
        "preferred_days": validate.text(data.get("preferred_days"), "preferred_days", 300, required=False, multiline=True),
        "session": validate.token(data["session"], "session") if data.get("session") else None,
        "photos": photo_ids,
        "turnstile": data["turnstile"],
    }


def offered(version, service, vehicle_class, size_variant):
    """Whether the pricebook prices a service for the class, and for the size
    when it is known (a size question may still be unanswered)."""
    if size_variant is None:
        return Price.objects.filter(version=version, service=service, vehicle_class=vehicle_class).exists()
    try:
        base_price(version, service, vehicle_class, size_variant)
    except NotPriced:
        return False
    return True


def by_quote_job(vehicle, size, service, condition, add_ons):
    """(the vehicle, the condition level) of a job the site can't price: a
    vehicle in a class booked by quote, or a service at a condition level
    booked by quote. Any other job is booked online."""
    found = catalog.resolve(vehicle, size)
    if found.needs_photo_card:
        raise ApiError(422, "photo_card_needed", "Pick the picture closest to your vehicle.", photo_cards=catalog.cards_json())
    level = quotes.check_condition(service, condition) if service is not None and condition is not None else None
    quotes.check_add_ons(service, add_ons)
    if found.booked_by_quote:
        return found, level
    if level is not None and level.booked_by_quote:
        # The class is booked online, so the service and add-ons must be
        # ones the pricebook offers for it, such as no Full Detail for a motorcycle.
        version = catalog.published_version()
        if not all(offered(version, item, found.vehicle_class, found.size_variant) for item in [service, *add_ons]):
            raise ApiError(422, "not_offered", "That service or add-on isn't offered for this vehicle.")
        return found, level
    if level is not None:
        raise ApiError(422, "book_online", f"{service.name} at condition level {level.level} can be booked online with a price right away.")
    raise ApiError(422, "book_online", f"{found.vehicle_class.name} can be booked online with a price right away.")


def vehicle_fields(found):
    """The request's vehicle as Vehicle fields. A van picked from the photo
    cards with no make or model typed has nothing to match on, so it is
    always flagged against a returning customer's vehicles."""
    size = found.size_variant
    return {
        "vehicle_model": found.vehicle_model, "year": found.year, "make": found.make or "", "model": found.model or "",
        "color": "", "vehicle_class": found.vehicle_class, "size_variant": size,
    }


def send(request, data):
    form = parse(data)
    found, level = by_quote_job(form["vehicle"], form["size"], form["service"], form["condition"], form["add_ons"])
    place = quotes.find_place(form["place"])
    with transaction.atomic():
        smoke_test = turnstile.check(request, form["turnstile"])
        kept = []
        if form["session"]:
            session = live_session(form["session"])
            UploadSession.objects.select_for_update().get(pk=session.pk)
            kept = list(session.photos.filter(public_id__in=form["photos"], request__isnull=True))
            if len(kept) != len(form["photos"]):
                raise bad_request("photos", "A photo didn't finish uploading. Please add it again.")
            smoke_test = smoke_test or session.is_smoke_test
        # Matched quietly like a booking; an address or vehicle it brings is
        # kept off the record until the request is booked.
        typed = bookings.given(form["first_name"], form["last_name"], form["mobile"], place, vehicle_fields(found), smoke_test)
        intake = bookings.take_in(typed, form["consents"], form["mobile"], hold=True)
        customer = intake.customer
        quote_request = QuoteRequest.objects.create(
            reference=bookings.unique_reference(),
            customer=customer,
            service_address=intake.address,
            vehicle=intake.vehicle,
            intake=intake.as_json(),
            vehicle_year=found.year,
            vehicle_make=found.make or "",
            vehicle_model_name=found.model or "",
            vehicle_class=found.vehicle_class,
            size_variant=found.size_variant,
            photo_card=found.photo_card,
            service=form["service"],
            condition_level=level.level if level is not None else None,
            description=form["description"],
            preferred_days=form["preferred_days"],
            is_test=customer.is_test,
        )
        quote_request.add_ons.set(form["add_ons"])
        QuotePhoto.objects.filter(pk__in=[photo.pk for photo in kept]).update(request=quote_request)
        if form["session"]:
            # Photos picked but left out of the request go now.
            photos.delete_photos(session.photos.filter(request__isnull=True))
    return 201, {
        "reference": quote_request.reference,
        "photos": len(kept),
        "message": THANKS.format(reference=quote_request.reference),
    }


# Offline quote requests ---------------------------------------------------------

OFFLINE_THANKS = (
    "Thanks! We've got your request and will reply with a price, usually within a day. "
    "If you have photos, text them to (423) 380-9120."
)


OFFLINE_REQUIRED = ["request_id", "submitted_at", "vehicle", "service", "description", "first_name", "mobile", "consents"]
OFFLINE_OPTIONAL = ["last_name", "preferred_days", "size", "condition", "add_ons", "place_id", "address", "session_token"]


def parse_offline(data):
    """A quote request the website held while the server was offline: the
    request form's fields, less the photos and Turnstile (checked by
    Cloudflare when it was sent), plus the website's request id, when it was
    sent, and the address as a place id or as typed. Each field is read on
    its own, and one that can't be read is left empty with its problem
    listed (decision 0114). Returns (form, Lenient)."""
    from .time_requests import NO_NAME, typed_place

    form = {"request_id": lenient.request_id(data)}
    read = lenient.Lenient(data, OFFLINE_REQUIRED, OFFLINE_OPTIONAL)
    get = data.get
    service = read.take(
        "Service", lambda: quotes.parse_service(data["service"]) if data["service"] != "not_sure" else None
    )
    condition = read.take("Condition", lambda: validate.integer(get("condition"), "condition", 1, 3, required=False))
    if service is None and condition is not None:
        read.note(f"Condition: {quotes.CONDITION_NOT_TAKEN}")
        condition = None
    form["service"], form["condition"] = service, condition
    form["submitted_at"] = read.take("When it was sent", lambda: validate.moment(data["submitted_at"], "submitted_at"))
    form["vehicle"] = read.take("Vehicle", lambda: catalog.parse_vehicle(data["vehicle"], free_text_with_card=True))
    form["size"] = read.take("Size", lambda: validate.integer(get("size"), "size", 1, 9, required=False))
    form["add_ons"] = read.take("Add-ons", lambda: quotes.parse_add_ons(get("add_ons")), [])
    form["description"] = read.take(
        "Description", lambda: validate.text(data["description"], "description", 2000, multiline=True), ""
    )
    form["place_id"], form["address"] = read.take("Address", lambda: typed_place(data), (None, ""))
    form["session_token"] = read.take("Address", lambda: validate.text(get("session_token"), "session_token", 64, required=False), "")
    form["first_name"] = read.take("First name", lambda: validate.text(data["first_name"], "first_name", 100), NO_NAME)
    form["last_name"] = read.take("Last name", lambda: validate.text(get("last_name"), "last_name", 100, required=False), "")
    form["mobile"] = read.take("Mobile number", lambda: validate.phone(data["mobile"]), "")
    form["consents"] = read.take("Text consent", lambda: consent.parse(data["consents"]))
    form["preferred_days"] = read.take(
        "Preferred days", lambda: validate.text(get("preferred_days"), "preferred_days", 300, required=False, multiline=True), ""
    )
    return form, read


def typed_vehicle(vehicle):
    """The vehicle as the customer typed it, when it can't be resolved."""
    return {
        "year": vehicle.get("year"), "make": vehicle.get("make") or "", "model": vehicle.get("model") or "",
        "vehicle_class": None, "size_variant": None, "vehicle_model": None, "photo_card": "photo_card" in vehicle,
    }


def receive_offline(request, data):
    """Keep a replayed quote request. Nothing the customer sent is lost: an
    address that can't be checked, or a job the site would book online, is
    kept with the problem noted for the owner, as an offline "request a
    time" form is, and so is anything that can't be read (decision 0114). A
    second replay of the same request id changes nothing."""
    from .time_requests import check_signature, unchecked_address

    check_signature(request)
    form, read = parse_offline(data)
    if QuoteRequest.objects.filter(request_id=form["request_id"]).exists():
        return 200, {"received": True, "duplicate": True}
    unreadable = bool(read.problems)
    found, level = None, None
    if form["vehicle"] is not None:
        try:
            found, level = by_quote_job(form["vehicle"], form["size"], form["service"], form["condition"], form["add_ons"])
        except ApiError as error:
            read.note(f"Vehicle or service: {error.message}")
    place = None
    if form["place_id"] is None:
        read.note(unchecked_address(form["address"]) if form["address"] else "No address given")
    else:
        try:
            # The server's reserve of Google calls, not the public share (decision 0115).
            place = quotes.verify_place(form["place_id"], form["session_token"], public=False)
        except ApiError as error:
            read.note(f"Address: {error.message}")
    vehicle = typed_vehicle(form["vehicle"] or {}) if found is None else None
    with transaction.atomic():
        typed = bookings.given(
            form["first_name"], form["last_name"], form["mobile"], place,
            vehicle_fields(found) if found is not None else None,
        )
        intake = bookings.take_in(typed, form["consents"], form["mobile"], hold=True, when=form["submitted_at"] or timezone.now())
        customer = intake.customer
        quote_request = QuoteRequest.objects.create(
            reference=bookings.unique_reference(),
            request_id=form["request_id"],
            customer=customer,
            service_address=intake.address,
            address_text=form["address"] if place is None and form["address"] else "",
            vehicle=intake.vehicle,
            intake=intake.as_json(),
            vehicle_year=(found.year if found else vehicle["year"]),
            vehicle_make=(found.make if found else vehicle["make"]) or "",
            vehicle_model_name=(found.model if found else vehicle["model"]) or "",
            vehicle_class=found.vehicle_class if found else None,
            size_variant=found.size_variant if found else None,
            photo_card=found.photo_card if found else vehicle["photo_card"],
            service=form["service"],
            condition_level=(level.level if level is not None else form["condition"]),
            description=form["description"],
            preferred_days=form["preferred_days"],
            problem=read.problem_text(),
            # Kept as sent when anything couldn't be read, so nothing is lost.
            as_sent=data if unreadable else None,
            is_test=customer.is_test,
        )
        quote_request.add_ons.set(form["add_ons"])
    return 201, {"received": True, "reference": quote_request.reference}
