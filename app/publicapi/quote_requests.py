"""Quote requests: the path for any job the site can't price, which is any
vehicle in a class booked by quote, today Full-size Vans (decision 0099).
A class the owner later sets to "Ask for a quote", such as RVs or boats,
uses it with no new code.

1. The website opens an upload session after a Turnstile check.
2. Each photo uploads on its own as the customer picks it, so one slow
   photo never loses the form. Each is checked and saved as a clean JPEG
   (photos.py). Up to QUOTE_REQUEST_MAX_PHOTOS per request.
3. The request names the session's photos it keeps. It is not an
   appointment and holds no time; the owner replies with a price.

Photos never attached to a sent request are deleted after a day, and a
closed request's photos QUOTE_REQUEST_PHOTO_DAYS after it closed
(cleanup.py). The description stays.
"""

import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import bookings, catalog, consent, photos, quotes, turnstile, validate
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
        ["last_name", "preferred_days", "session", "photos"],
    )
    service = data["service"]
    if service != "not_sure":
        service = quotes.parse_service(service)
    else:
        service = None
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
        "service": service,
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


def by_quote_vehicle(vehicle):
    """The vehicle's class, which must be booked by quote: any other vehicle
    is booked online."""
    found = catalog.resolve(vehicle)
    if found.needs_photo_card:
        raise ApiError(422, "photo_card_needed", "Pick the picture closest to your vehicle.", photo_cards=catalog.cards_json())
    if not found.booked_by_quote:
        raise ApiError(422, "book_online", f"{found.vehicle_class.name} can be booked online with a price right away.")
    return found


def send(request, data):
    form = parse(data)
    found = by_quote_vehicle(form["vehicle"])
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
        customer = bookings.new_customer(form["first_name"], form["last_name"], form["mobile"], smoke_test)
        address = place.as_address(customer)
        address.save()
        consent.record(customer, form["mobile"], form["consents"])
        quote_request = QuoteRequest.objects.create(
            reference=bookings.unique_reference(QuoteRequest),
            customer=customer,
            service_address=address,
            vehicle_year=found.year,
            vehicle_make=found.make or "",
            vehicle_model_name=found.model or "",
            vehicle_class=found.vehicle_class,
            photo_card=found.photo_card,
            service=form["service"],
            description=form["description"],
            preferred_days=form["preferred_days"],
            is_test=customer.is_test,
        )
        QuotePhoto.objects.filter(pk__in=[photo.pk for photo in kept]).update(request=quote_request)
        if form["session"]:
            # Photos picked but left out of the request go now.
            photos.delete_photos(session.photos.filter(request__isnull=True))
    return 201, {
        "reference": quote_request.reference,
        "photos": len(kept),
        "message": THANKS.format(reference=quote_request.reference),
    }
