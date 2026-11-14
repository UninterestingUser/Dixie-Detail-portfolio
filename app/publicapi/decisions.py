"""The owner's decisions on website requests, from the control app
(control-app.md, handling-website-bookings.md):

- a quote request is priced by hand, which makes a quote record, the price
  of record (decision 0059), then booked from that quote into an open time
  or declined with a reason;
- an offline request is priced for the day the owner picks and booked, at
  that price or the one the customer saw, or declined;
- a second vehicle the same day is approved, which books its quote, or
  declined.

Booking any of them goes through the same availability check as the
website (appointments.booking.book_request), puts the address and vehicle
the request brought on the record, raises its review flags
(customers.matching) and assigns the only qualified staff member
(decisions 0061 and 0069).
"""

from django.db import transaction
from django.utils import timezone

from appointments import booking
from appointments.models import AppointmentLine
from customers import matching
from pricebook.models import PricedLine
from pricebook.pricing import PricingError, hand_description, issue_hand_quote
from staff.authorization import auto_assign

from .models import QuoteRequest, SecondVehicleRequest, TimeRequest

SHOWN_PRICE_LINE = "Price shown while the server was offline"


class DecisionError(ValueError):
    """The request can't be decided as asked."""


def after_booking(appointment, intake):
    """Put the request's address and vehicle on the record, raise its review
    flags and assign the only qualified staff member. Returns the person
    assigned, or None when the assign-staff prompt is needed."""
    matching.release(appointment, intake)
    return auto_assign(appointment)


def decline(item, reason, user):
    if item.status != item.Status.NEW and not (isinstance(item, QuoteRequest) and item.status == QuoteRequest.Status.REPLIED):
        raise DecisionError("Only an open request can be declined.")
    if not reason.strip():
        raise DecisionError("Give the reason for declining.")
    item.status = item.Status.DECLINED
    item.decline_reason = reason.strip()[:300]
    if isinstance(item, QuoteRequest):
        item.closed_at = timezone.now()
    else:
        item.decided_at, item.decided_by = timezone.now(), user
    item.save()
    return item


# Quote requests -----------------------------------------------------------------


@transaction.atomic
def price_quote_request(item, service, vehicle_class, amount, minutes, user, crew_size=1, size_variant=None):
    """Record the owner's hand price and time on site as a quote: one line,
    the price before tax, with the sales tax at the request's address today.
    A request at a condition level booked by quote carries its level and
    add-ons into the quote (decision 0103). The quote never changes; pricing
    again makes a new one."""
    if item.status not in (QuoteRequest.Status.NEW, QuoteRequest.Status.REPLIED):
        raise DecisionError("Only an open request can be priced.")
    # The level and add-ons the customer asked for go with the service they
    # asked for; a service the owner changes is priced on its own.
    asked = item.service is not None and service == item.service
    level = item.condition_level if asked else None
    add_ons = list(item.add_ons.all()) if asked else []
    if size_variant is None and vehicle_class == item.vehicle_class:
        size_variant = item.size_variant
    try:
        quote = issue_hand_quote(
            service, vehicle_class, amount, minutes,
            description=hand_description(service, level, add_ons, reference=item.reference),
            crew_size=crew_size, size_variant=size_variant, condition_level=level, add_ons=add_ons,
            address=item.service_address,
        )
    except PricingError as error:
        raise DecisionError(str(error)) from error
    item.quote, item.priced_at, item.priced_by = quote, timezone.now(), user
    item.status = QuoteRequest.Status.REPLIED
    item.save()
    return quote


@transaction.atomic
def book_quote_request(item, start, user, may_override=False, override_reason=""):
    """Book the request from its hand-priced quote. The job keeps the
    request's description and photos (the job page shows them)."""
    if item.status not in (QuoteRequest.Status.NEW, QuoteRequest.Status.REPLIED) or item.appointment_id:
        raise DecisionError("This request is already booked or closed.")
    if item.quote is None:
        raise DecisionError("Price the request first.")
    appointment = booking.book_request(
        item.quote, item.customer, item.vehicle, start, address=item.service_address, user=user,
        may_override=may_override, override_reason=override_reason,
        notes=f"From quote request {item.reference}: {item.description}",
    )
    item.appointment, item.status = appointment, QuoteRequest.Status.BOOKED
    item.save()
    return appointment, after_booking(appointment, item.intake)


# Offline requests ---------------------------------------------------------------


def offline_inputs(item):
    """What the offline request was priced from on arrival, to price it again
    for the day the owner picks, or None when it couldn't be priced."""
    quote = item.quote
    if quote is None:
        return None
    return booking.JobInputs(quote.service, quote.vehicle_class, quote.size_variant, quote.condition_level, list(quote.add_ons.all()))


def price_for_day(item, day):
    """The request priced from the pricebook in effect on day, with the tax
    at its address then. A new quote, the price of record if booked."""
    inputs = offline_inputs(item)
    if inputs is None or item.service_address is None:
        raise DecisionError("This request couldn't be priced. Book it from the customer's page instead.")
    return inputs.quote(on=day, address=item.service_address)


@transaction.atomic
def book_time_request(item, start, user, may_override=False, override_reason="", honor_shown=False):
    """Book an offline request at the time picked, priced for that day. With
    honor_shown, an adjustment line makes the total before tax the price the
    customer saw, with the reason kept on the line."""
    if item.status != TimeRequest.Status.NEW:
        raise DecisionError("This request is already booked or declined.")
    quote = price_for_day(item, booking.local_date(start))
    appointment = booking.book_request(
        quote, item.customer, item.vehicle, start, address=item.service_address, user=user,
        may_override=may_override, override_reason=override_reason,
        preferred_payment_method=item.inputs.get("payment_method", ""),
        notes=item.preferred_note,
    )
    if honor_shown and item.shown_total is not None:
        difference = item.shown_total - quote.total_before_tax
        if difference:
            AppointmentLine.objects.create(
                appointment=appointment, position=quote.lines.count(), kind=PricedLine.Kind.ADJUSTMENT,
                description=SHOWN_PRICE_LINE, amount=difference,
                reason=f"The customer saw {item.shown_total} (pricebook version {item.shown_pricebook_version}) while the server was offline.",
            )
    item.appointment, item.status = appointment, TimeRequest.Status.BOOKED
    item.decided_at, item.decided_by = timezone.now(), user
    item.save()
    return appointment, after_booking(appointment, item.intake)


# A second vehicle the same day ------------------------------------------------


@transaction.atomic
def approve_second_vehicle(item, start, user, may_override=False, override_reason=""):
    """Book the second vehicle's quote, as the customer was shown it, at the
    time picked: the customer's own unless the owner chose another."""
    if item.status != SecondVehicleRequest.Status.NEW:
        raise DecisionError("This request is already booked or declined.")
    appointment = booking.book_request(
        item.web_quote.quote, item.customer, item.vehicle, start, address=item.service_address, user=user,
        may_override=may_override, override_reason=override_reason,
        preferred_payment_method=item.payment_method,
    )
    item.appointment, item.status = appointment, SecondVehicleRequest.Status.BOOKED
    item.decided_at, item.decided_by = timezone.now(), user
    item.save()
    return appointment, after_booking(appointment, item.intake)
