"""Addresses, quotes and open times for the website (public-api.md).

- An address arrives as a Google place ID. The server looks it up itself
  (geo.verification), refuses one outside the service area unless it
  matches an address the owner approved (decision 0037), and keeps it as a
  VerifiedPlace the website refers to by its token.
- A quote is the pricing engine's Quote, issued for the inputs as given,
  with a public number and an expiry (WebQuote). It never changes: a changed
  input makes a new quote.
- Open times come from the availability check with the quote's time on site
  and the place's location. Drives not already cached are estimated, so
  visitors browsing times never spend the day's Google Routes calls; the
  booking checks the time again with real drive times.
"""

import datetime
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from billing.tax import tax_line
from customers.models import Address
from geo import google, service_area
from geo.verification import VerificationError, address_from_place, split_line1
from pricebook.models import PricebookVersion, Service
from pricebook.pricing import BookedByQuote, NotPriced, PricingError, issue_quote
from scheduling import availability
from scheduling.models import SchedulingSettings

from . import catalog, validate
from .http import ApiError, bad_request
from .models import VerifiedPlace, WebQuote, new_reference

OUTSIDE_AREA = (
    "Sorry, that address is outside the area we serve. If you think we can still help, "
    "call or text (423) 380-9120."
)


def money(amount):
    return f"{amount:.2f}"


def percent(rate):
    text = f"{Decimal(rate):f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


# Addresses --------------------------------------------------------------------


def same_place(approved, address):
    """Whether an approved address is the place picked: the same Google
    place, or the same house number, street and ZIP code."""
    if approved.google_place_id and approved.google_place_id == address.google_place_id:
        return True
    number, street = split_line1(approved.line1)
    picked_number, picked_street = split_line1(address.line1)
    return bool(number) and number == picked_number and street == picked_street and (
        (approved.zip_code or "")[:5] == (address.zip_code or "")[:5]
    )


def approved_match(address):
    for approved in Address.objects.filter(approved_out_of_area=True, active=True):
        if same_place(approved, address):
            return approved
    return None


def tax_json(address_or_quote, today=None):
    """The tax line for a place before there is a price: the rate and where
    it comes from. With a quote, the amount too."""
    if hasattr(address_or_quote, "sales_tax"):
        quote = address_or_quote
        if quote.tax_jurisdiction is None and not quote.tax_rate:
            return None
        return {
            "rate_percent": percent(quote.tax_rate),
            "amount": money(quote.sales_tax),
            "jurisdiction": str(quote.tax_jurisdiction) if quote.tax_jurisdiction else "",
        }
    line = tax_line(address_or_quote, Decimal("100.00"), today or timezone.localdate())
    return {"rate_percent": percent(line.rate), "jurisdiction": str(line.jurisdiction) if line.jurisdiction else ""}


def place_json(place):
    return {
        "place": place.token,
        "address": {
            "line1": place.line1,
            "line2": place.line2,
            "city": place.city,
            "state": place.state,
            "zip_code": place.zip_code,
            "one_line": place.one_line,
        },
        "in_area": True,
        "approved_out_of_area": place.approved_address_id is not None,
        "tax": tax_json(place.as_address()),
        "reminder": "We bring everything else, but we need water and power at the vehicle.",
    }


LOOKUPS_USED = (
    "We can't look up addresses online any more today. Type your address and send your booking as a request, "
    "and we'll confirm by text or call."
)


def verify_place(place_id, session_token="", public=True):
    """Look a place up, check the service area, and keep it. Raises
    ApiError for anything the website can't use. A website lookup (public)
    counts against the public share of the day's Google calls; past it the
    answer is lookups_used_up, and the site takes a typed address and a
    request instead (decision 0115). The server's own checks, such as an
    offline request arriving, use the reserve (public=False)."""
    try:
        address = address_from_place(None, place_id, session_token, public=public)
    except VerificationError as error:
        raise ApiError(422, "not_an_address", str(error)) from error
    except google.PublicShareUsed as error:
        raise ApiError(429, "lookups_used_up", LOOKUPS_USED) from error
    except google.GoogleUnavailable as error:
        raise ApiError(503, "unavailable", "We couldn't look that address up just now. Please try again in a minute.") from error
    except ValueError as error:
        raise bad_request("place_id") from error
    approved = approved_match(address)
    address.approved_out_of_area = approved is not None
    if not service_area.check(address).in_area:
        raise ApiError(422, "outside_area", OUTSIDE_AREA)
    return VerifiedPlace.objects.create(
        google_place_id=place_id,
        line1=address.line1,
        line2=address.line2,
        city=address.city,
        state=address.state,
        zip_code=address.zip_code,
        county=address.county,
        latitude=address.latitude,
        longitude=address.longitude,
        tax_jurisdiction=address.tax_jurisdiction,
        tax_needs_check=address.tax_needs_check,
        tax_note=address.tax_note,
        approved_address=approved,
    )


def find_place(token, field="place"):
    place = VerifiedPlace.objects.filter(token=token).first()
    if place is None:
        raise bad_request(field, "Please pick the address again.")
    return place


# Quotes -----------------------------------------------------------------------


def parse_service(value, field="service"):
    service_id = validate.integer(value, field, 1, 2**31 - 1)
    service = catalog.bookable_services().filter(pk=service_id, kind=Service.Kind.MAIN).first()
    if service is None:
        raise bad_request(field)
    return service


def parse_add_ons(value, field="add_ons"):
    ids = validate.id_list(value, field)
    add_ons = list(catalog.bookable_services().filter(pk__in=ids, kind=Service.Kind.ADD_ON))
    if len(add_ons) != len(ids):
        raise bad_request(field)
    return add_ons


def check_add_ons(service, add_ons, on=None, field="add_ons"):
    """Refuse an add-on that doesn't go with the service in the pricebook
    in effect on the day (today by default), or any add-on without a
    service (decision 0106). The website offers only those that fit."""
    if not add_ons:
        return
    if service is None:
        raise bad_request(field, "Pick a service to add an add-on to.")
    version = PricebookVersion.current(on) or catalog.published_version()
    fits = version.add_on_ids_for(service)
    unfit = [add_on for add_on in add_ons if add_on.pk not in fits]
    if unfit:
        names = " and ".join(add_on.name for add_on in unfit)
        raise bad_request(field, f"{names} can't be added to {service.name}.")


def priced_vehicle(found):
    """Refuse a vehicle the site can't price yet, saying what to do next."""
    if found.needs_photo_card:
        raise ApiError(422, "photo_card_needed", "Pick the picture closest to your vehicle.", photo_cards=catalog.cards_json())
    if found.booked_by_quote:
        raise ApiError(
            422, "ask_for_quote",
            f"{found.vehicle_class.name} are priced by hand. Ask for a quote and we'll reply with a price.",
        )
    if found.question is not None:
        raise ApiError(422, "size_question", found.question.text, question=catalog.question_json(found.question))
    return found


CONDITION_NOT_TAKEN = "Only Full Detail and Interior Only take a condition level."
LEVEL_BY_QUOTE = (
    "{service} at condition level {level} is priced by hand. Ask for a quote and we'll reply with a price."
)


def check_condition(service, condition_level, on=None, field="condition"):
    """The condition level for a service, by the pricebook in effect on the
    day (today by default): required for a service that takes one, refused
    for any other (decision 0103). Returns the ConditionLevel, or None."""
    version = PricebookVersion.current(on) or catalog.published_version()
    if not version.takes_condition_level(service):
        if condition_level is not None:
            raise bad_request(field, CONDITION_NOT_TAKEN)
        return None
    if condition_level is None:
        raise bad_request(field, "Pick the vehicle's condition.")
    level = version.condition_levels.filter(level=condition_level).first()
    if level is None:
        raise bad_request(field)
    return level


def level_by_quote(service, level, add_ons):
    """The answer for a level booked by quote: no price or time, and what a
    quote request needs to carry."""
    return ApiError(
        422, "ask_for_quote", LEVEL_BY_QUOTE.format(service=service.name, level=level.level),
        quote_request={"service": service.pk, "condition": level.level, "add_ons": [add_on.pk for add_on in add_ons]},
    )


@transaction.atomic
def issue(found, service, condition_level, add_ons, place=None, on=None, answered=None):
    """Price the job and keep it as a website quote. answered is the
    customer's answer to the size question, kept to price it again. A
    condition level booked by quote is refused with ask_for_quote: it has no
    price or time, and goes to a quote request (decision 0103)."""
    priced_vehicle(found)
    level = check_condition(service, condition_level, on)
    check_add_ons(service, add_ons, on)
    if level is not None and level.booked_by_quote:
        raise level_by_quote(service, level, add_ons)
    try:
        quote = issue_quote(
            service,
            found.vehicle_class,
            tax_address=place.as_address() if place else None,
            size_variant=found.size_variant,
            condition_level=condition_level,
            add_ons=add_ons,
            on=on,
        )
    except NotPriced as error:
        raise ApiError(422, "not_offered", "That service or add-on isn't offered for this vehicle.") from error
    except BookedByQuote as error:
        raise level_by_quote(service, level, add_ons) from error
    except PricingError as error:
        raise ApiError(422, "not_offered", "That combination can't be priced. Please change it and try again.") from error
    return WebQuote.objects.create(
        quote=quote,
        number=new_reference(10),
        expires_at=timezone.now() + datetime.timedelta(minutes=settings.QUOTE_LIFETIME_MINUTES),
        place=place,
        vehicle_year=found.year,
        vehicle_make=found.make or "",
        vehicle_model_name=found.model or "",
        vehicle_model=found.vehicle_model,
        photo_card=found.photo_card,
        size_answer={"size": answered} if answered is not None else {},
    )


def vehicle_input(web):
    """The vehicle as first given, to price it again."""
    if web.photo_card:
        return {"photo_card": web.quote.vehicle_class_id, "year": web.vehicle_year, "make": web.vehicle_make, "model": web.vehicle_model_name}
    kind = web.vehicle_model.vehicle_type if web.vehicle_model else catalog.VEHICLE
    return {"year": web.vehicle_year, "make": web.vehicle_make, "model": web.vehicle_model_name, "type": kind}


def reissue(web, on=None):
    """A fresh quote for the same inputs, priced now (or for the day on).
    The vehicle is looked up again, so a class changed since is used."""
    quote = web.quote
    found = catalog.resolve(vehicle_input(web), (web.size_answer or {}).get("size"))
    if found.question is not None and quote.size_variant is not None:
        found = catalog.settle(found, quote.size_variant.value)
    return issue(found, quote.service, quote.condition_level, list(quote.add_ons.all()), web.place, on=on, answered=(web.size_answer or {}).get("size"))


def changed_for_day(web, day):
    """Whether the quote's price would differ on the day of service: another
    pricebook version in effect then, or another tax rate."""
    quote = web.quote
    version = PricebookVersion.current(day) or PricebookVersion.current()
    if version is not None and version.pk != quote.pricebook_version_id:
        return True
    if web.place is not None:
        line = tax_line(web.place.as_address(), quote.total_before_tax, day)
        if (line.state_rate, line.local_rate) != (quote.state_rate, quote.local_rate):
            return True
    return False


def find_quote(number, field="quote"):
    web = WebQuote.objects.select_related("quote__service", "quote__vehicle_class", "quote__size_variant", "place").filter(number=number).first()
    if web is None:
        raise ApiError(404, "not_found", "That quote wasn't found. Please start again.", field=field)
    return web


def quote_json(web):
    quote = web.quote
    return {
        "number": web.number,
        "expires_at": web.expires_at.isoformat(),
        "pricebook_version": quote.pricebook_version.number,
        "vehicle": {
            "description": web.vehicle_text,
            "class": catalog.class_json(quote.vehicle_class),
            "size": catalog.size_json(quote.size_variant),
        },
        "service": {"id": quote.service_id, "name": quote.service.name},
        "add_ons": [{"id": add_on.pk, "name": add_on.name} for add_on in quote.add_ons.order_by("name")],
        "condition_level": quote.condition_level,
        "lines": [
            {"kind": line.kind, "description": line.description, "amount": money(line.amount)}
            for line in quote.lines.all()
        ],
        "total_before_tax": money(quote.total_before_tax),
        "address": web.place.one_line if web.place else None,
        "sales_tax": tax_json(quote) if web.place else None,
        "total": money(quote.total),
        "service_minutes": quote.service_minutes,
        "time_on_site_minutes": quote.time_on_site_minutes,
        "full_day": quote.full_day,
    }


# Open times -------------------------------------------------------------------

MAX_DAYS = 31


def open_times_json(web, first=None, days=14):
    if web.place is None:
        raise ApiError(422, "address_needed", "Enter the service address first.")
    row = SchedulingSettings.get()
    today = timezone.localdate()
    earliest = today + datetime.timedelta(days=row.minimum_notice_days)
    latest = today + datetime.timedelta(days=row.furthest_bookable_days)
    first = max(first or earliest, earliest)
    last = min(first + datetime.timedelta(days=min(days, MAX_DAYS) - 1), latest)
    result = {"quote": web.number, "expired": web.expired, "from": first.isoformat(), "to": last.isoformat(), "days": []}
    if first > last:
        return result
    from appointments.booking import job_from_quote

    rules = availability.load_rules(first, last)
    rules.ask_google = False
    job = job_from_quote(web.quote, web.place.as_address())
    for day in availability.open_times(job, first, last, rules=rules):
        # Only open times, never why a time is closed: the reasons name
        # other customers' jobs and the owner's Time Off.
        result["days"].append(
            {
                "date": day.date.isoformat(),
                "times": [
                    {"start": timezone.localtime(slot.start).isoformat(), "label": availability.clock(slot.start)}
                    for slot in day.open_slots
                ],
            }
        )
    return result
