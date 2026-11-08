"""A website booking (public-api.md, booking-flow.md step 7).

The booking names a quote, a start time, the customer's name, mobile
number, preferred payment method, optional color, the two consent answers
and a Turnstile token. In one transaction the server checks the token, the
quote's age and the time, locks the day (so two visitors can't book the
same time), and books the quote as issued: its lines become the
appointment's line snapshot (decisions 0033 and 0059). An expired quote, or
one the day of service would price differently, returns a fresh quote to
confirm, never a silent new price.

Until quiet matching (Phase 3 Step 5), each booking creates a new customer.
Nothing in the answer comes from a customer's record: the summary is built
from the quote, the place and what this booking sent.
"""

import datetime
import re

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from appointments import booking
from appointments.models import Appointment
from billing.methods import website_methods
from customers.models import Customer
from vehicles.models import Vehicle

from . import consent, quotes, turnstile, validate
from .http import ApiError, bad_request
from .models import new_reference

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


def new_customer(first_name, last_name, mobile, smoke_test=False):
    """A new customer for a website booking or request. Quiet matching
    (Phase 3 Step 5) will put returning customers on their record instead."""
    return Customer.objects.create(
        first_name=first_name, last_name=last_name, mobile=mobile, source=ORIGIN_SOURCE,
        is_test=smoke_test or is_test_number(mobile),
    )


def unique_reference(model, length=8):
    for _ in range(10):
        reference = new_reference(length)
        if not model.objects.filter(reference=reference).exists():
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
        if Appointment.objects.filter(quote_id=web.quote_id).exists():
            raise ApiError(409, "quote_used", "That quote has already been booked. Please start again for another booking.")
        if web.expired:
            error = fresh_quote_error("quote_expired", "Your quote has expired. Here is a fresh one to confirm.", web, day)
            return error.status, {"error": error.code, "message": error.message, **error.extra}
        if quotes.changed_for_day(web, day):
            error = fresh_quote_error(
                "quote_changed", "The price for that date is different. Please confirm the new price to book it.", web, day
            )
            return error.status, {"error": error.code, "message": error.message, **error.extra}
        try:
            with transaction.atomic():
                appointment = write_booking(web, form, start, smoke_test)
        except booking.RulesBroken as error:
            raise ApiError(409, "time_taken", "That time is no longer open. Please pick another time.") from error
        except IntegrityError as error:
            raise ApiError(409, "quote_used", "That quote has already been booked. Please start again for another booking.") from error
    return 201, booking_answer(web, appointment, form)


def write_booking(web, form, start, smoke_test):
    quote = web.quote
    customer = new_customer(form["first_name"], form["last_name"], form["mobile"], smoke_test)
    address = web.place.as_address(customer)
    address.save()
    vehicle = Vehicle.objects.create(
        customer=customer,
        vehicle_model=web.vehicle_model,
        year=web.vehicle_year,
        make=web.vehicle_make,
        model=web.vehicle_model_name,
        color=form["color"],
        vehicle_class=quote.vehicle_class,
        size_variant=quote.size_variant,
    )
    consent.record(customer, form["mobile"], form["consents"])
    return booking.book_online(
        customer, vehicle, start, None, address=address, quote=quote,
        preferred_payment_method=form["payment_method"],
        reference=unique_reference(Appointment),
        is_test=customer.is_test,
    )


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
