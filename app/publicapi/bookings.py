"""A website booking (public-api.md, booking-flow.md step 7).

The booking names a quote, a start time, the customer's name, mobile
number, preferred payment method, optional color, the two consent answers
and a Turnstile token. In one transaction the server checks the token, the
quote's age and the time, locks the day (so two visitors can't book the
same time), and books the quote as issued: its lines become the
appointment's line snapshot (decisions 0033 and 0059). An expired quote, or
one the day of service would price differently, returns a fresh quote to
confirm, never a silent new price.

Each booking is matched quietly on its mobile number (customers.matching,
returning-customers.md): a returning customer's booking goes on their
record, and any difference is flagged for the owner. A returning customer
who already has a job that day gets a request the owner approves instead
of a booking (SecondVehicleRequest). Nothing in the answer comes from a
customer's record: the summary is built from the quote, the place and what
this booking sent. A one-person job with exactly one qualified staff member
is assigned to them; any other job waits on the home screen for a manager
(decisions 0061 and 0069).
"""

import datetime
import re

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from appointments import booking
from appointments.models import Appointment
from billing.methods import website_methods
from customers import matching
from scheduling.availability import local_midnight
from staff.authorization import auto_assign

from . import consent, quotes, turnstile, validate
from .http import ApiError, bad_request
from .models import SecondVehicleRequest, new_reference

ORIGIN_SOURCE = "Website"


def parse(data):
    validate.only(data, ["quote", "start", "first_name", "mobile", "payment_method", "consents", "turnstile"], ["last_name", "color"])
    method = data["payment_method"]
    if method not in {choice.value for choice in website_methods()}:
        raise bad_request("payment_method")
    return {
        "quote": validate.number(data["quote"], "quote"),
        "start": validate.moment(data["start"], "start"),
        "first_name": validate.text(data["first_name"], "first_name", 100),
        "last_name": validate.text(data.get("last_name"), "last_name", 100, required=False),
        "mobile": validate.phone(data["mobile"]),
        "payment_method": method,
        "color": validate.text(data.get("color"), "color", 40, required=False),
        "consents": consent.parse(data["consents"]),
        "turnstile": data["turnstile"],
    }


def is_test_number(mobile):
    """Whether a 10-digit number is on TEST_PHONE_NUMBERS, written in any format."""
    listed = {re.sub(r"\D", "", number)[-10:] for number in settings.TEST_PHONE_NUMBERS}
    return mobile in listed


def given(first_name, last_name, mobile, place=None, vehicle=None, smoke_test=False):
    """A booking or request as typed, for quiet matching. place is the
    verified place; vehicle holds Vehicle fields."""
    return matching.Given(
        first_name=first_name, last_name=last_name, mobile=mobile,
        address=place.as_address() if place is not None else None, vehicle=vehicle,
        is_test=smoke_test or is_test_number(mobile),
    )


def take_in(form_given, answers, mobile, hold=False, when=None):
    """Match the booking or request, put it on its customer and record the
    consent answers there. Returns the Intake."""
    intake = matching.take_in(form_given, source=ORIGIN_SOURCE, hold=hold)
    intake.consent_ids = [row.pk for row in consent.record(intake.customer, mobile, answers, when=when)]
    return intake


def quote_vehicle(web, color=""):
    """The vehicle of a website quote, as Vehicle fields."""
    quote = web.quote
    return {
        "vehicle_model": web.vehicle_model, "year": web.vehicle_year, "make": web.vehicle_make, "model": web.vehicle_model_name,
        "color": color, "vehicle_class": quote.vehicle_class, "size_variant": quote.size_variant,
    }


def same_day_job(customer, day):
    """The customer's job on that day, not canceled, or None."""
    if customer is None:
        return None
    return (
        Appointment.objects.filter(
            customer=customer, scheduled_start__gte=local_midnight(day),
            scheduled_start__lt=local_midnight(day + datetime.timedelta(days=1)),
        ).exclude(status=Appointment.Status.CANCELED).order_by("scheduled_start").first()
    )


REFERENCE_MODELS = ("appointments.Appointment", "publicapi.QuoteRequest", "publicapi.SecondVehicleRequest")


def unique_reference(model=None, length=8):
    """A reference no booking or request has, so one the customer reads out
    always finds one record."""
    from django.apps import apps

    models = [apps.get_model(name) for name in REFERENCE_MODELS]
    for _ in range(10):
        reference = new_reference(length)
        if not any(found.objects.filter(reference=reference).exists() for found in models):
            return reference
    raise RuntimeError("No free reference after 10 tries.")


def ics_text(value):
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_time(moment):
    return moment.astimezone(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")


def calendar_file(reference, start, minutes, title, location, description):
    """A one-event iCalendar file, in UTC so every calendar app reads it the same."""
    end = start + datetime.timedelta(minutes=minutes)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Dixie Detail//Booking//EN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{reference}@dixiedetail.com",
        f"DTSTAMP:{ics_time(timezone.now())}",
        f"DTSTART:{ics_time(start)}",
        f"DTEND:{ics_time(end)}",
        f"SUMMARY:{ics_text(title)}",
        f"LOCATION:{ics_text(location)}",
        f"DESCRIPTION:{ics_text(description)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"


def hours_text(minutes):
    hours, rest = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if rest:
        parts.append(f"{rest} minutes")
    return " ".join(parts) or "0 minutes"


def summary(web, start, color, payment_method):
    """What was booked, from the quote, the place and this booking only."""
    quote = web.quote
    local = timezone.localtime(start)
    method_label = dict((choice.value, choice.label) for choice in website_methods())[payment_method]
    return {
        "service": quote.service.name,
        "add_ons": [add_on.name for add_on in quote.add_ons.order_by("name")],
        "vehicle": web.vehicle_text,
        "color": color,
        "date": local.date().isoformat(),
        "arrival": f"{local:%A, %B} {local.day} at {local:%-I:%M %p}",
        "time_on_site": "Full day" if quote.full_day else hours_text(quote.time_on_site_minutes),
        "address": web.place.one_line,
        "total_before_tax": quotes.money(quote.total_before_tax),
        "sales_tax": quotes.money(quote.sales_tax),
        "total": quotes.money(quote.total),
        "payment_method": method_label,
        "notes": [
            "The final price is confirmed when we see the vehicle.",
            "Nothing is charged until the job is done.",
            "Please have water and power available near the vehicle.",
        ],
    }


def fresh_quote_error(code, message, web, day=None):
    fresh = quotes.reissue(web, on=day)
    return ApiError(409, code, message, quote=quotes.quote_json(fresh))


SECOND_VEHICLE_MESSAGE = (
    "Thanks! We've got your request for this time. Because there's already a booking for this number that day, "
    "we'll confirm this one by text or call. Your request number is {reference}."
)


def book(request, data):
    """Book a website quote. Returns (status, answer)."""
    form = parse(data)
    web = quotes.find_quote(form["quote"])
    if web.place is None:
        raise ApiError(422, "address_needed", "Enter the service address first.")
    start = form["start"]
    day = timezone.localtime(start).date()
    # One transaction: the token, the quote's age, the time and the booking.
    with transaction.atomic():
        smoke_test = turnstile.check(request, form["turnstile"])
        if Appointment.objects.filter(quote_id=web.quote_id).exists() or SecondVehicleRequest.objects.filter(web_quote=web).exists():
            raise ApiError(409, "quote_used", "That quote has already been booked. Please start again for another booking.")
        if web.expired:
            error = fresh_quote_error("quote_expired", "Your quote has expired. Here is a fresh one to confirm.", web, day)
            return error.status, {"error": error.code, "message": error.message, **error.extra}
        if quotes.changed_for_day(web, day):
            error = fresh_quote_error(
                "quote_changed", "The price for that date is different. Please confirm the new price to book it.", web, day
            )
            return error.status, {"error": error.code, "message": error.message, **error.extra}
        typed = given(form["first_name"], form["last_name"], form["mobile"], web.place, quote_vehicle(web, form["color"]), smoke_test)
        # The day is locked before looking for the customer's job that day, so
        # two bookings at once can't both miss each other.
        booking.lock_day(day)
        customer, _ = matching.find_match(typed.mobile, typed.is_test, typed.first_name, typed.last_name)
        other = same_day_job(customer, day)
        try:
            with transaction.atomic():
                if other is not None:
                    second = write_second_vehicle_request(web, form, start, typed, other)
                    return 202, second_vehicle_answer(web, second, form)
                appointment = write_booking(web, form, start, typed)
        except booking.RulesBroken as error:
            raise ApiError(409, "time_taken", "That time is no longer open. Please pick another time.") from error
        except IntegrityError as error:
            raise ApiError(409, "quote_used", "That quote has already been booked. Please start again for another booking.") from error
    return 201, booking_answer(web, appointment, form)


def write_booking(web, form, start, typed):
    """Match the booking, then book the quote as issued on the customer it
    matched, with the address and vehicle as booked; raise the review flags
    and assign the only qualified staff member."""
    intake = take_in(typed, form["consents"], form["mobile"])
    appointment = booking.book_online(
        intake.customer, intake.vehicle, start, None, address=intake.address, quote=web.quote,
        preferred_payment_method=form["payment_method"],
        reference=unique_reference(),
        is_test=intake.customer.is_test,
        intake=intake.as_json(),
    )
    matching.raise_flags(appointment, appointment.intake)
    auto_assign(appointment)
    return appointment


def write_second_vehicle_request(web, form, start, typed, other):
    """A returning customer already has a job that day: the time must still
    be open, but the booking becomes a request the owner approves."""
    from calendars.sync import refresh_time_off_for_booking

    refresh_time_off_for_booking()
    booking.check_online(None, start, web.place.as_address(), web.quote)
    intake = take_in(typed, form["consents"], form["mobile"], hold=True)
    return SecondVehicleRequest.objects.create(
        reference=unique_reference(),
        web_quote=web,
        customer=intake.customer,
        service_address=intake.address,
        vehicle=intake.vehicle,
        start=start,
        payment_method=form["payment_method"],
        same_day_appointment=other,
        intake=intake.as_json(),
        is_test=intake.customer.is_test,
    )


def second_vehicle_answer(web, second, form):
    return {
        "request": second.reference,
        "status": "requested",
        "message": SECOND_VEHICLE_MESSAGE.format(reference=second.reference),
        "summary": summary(web, second.start, form["color"], form["payment_method"]),
    }


def booking_answer(web, appointment, form):
    details = summary(web, appointment.scheduled_start, form["color"], form["payment_method"])
    title = f"Dixie Detail: {details['service']}"
    description = "\n".join(
        [f"Booking reference {appointment.reference}", f"{details['vehicle']}", f"Total {details['total']} (confirmed when we see the vehicle)",
         "Questions: call or text (423) 380-9120."]
    )
    return {
        "reference": appointment.reference,
        "summary": details,
        "calendar_file": {
            "name": f"dixie-detail-{appointment.reference}.ics",
            "content_type": "text/calendar",
            "content": calendar_file(
                appointment.reference, appointment.scheduled_start, web.quote.time_on_site_minutes, title,
                web.place.one_line, description,
            ),
        },
    }
