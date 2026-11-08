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

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from appointments import booking
from appointments.models import AppointmentLine
from billing.tax import tax_line
from core.scheduling import current_values
from customers import matching
from pricebook.models import PricebookVersion, PricedLine, PricingRules, Quote, QuoteLine
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


def split_minutes(minutes, crew_size):
    """Setup, service time and breakdown for a time on site typed by hand:
    the setup and breakdown settings for the crew, the rest service time."""
    values = current_values()
    setup = round(values.setup_minutes_one_person / crew_size)
    breakdown = round(values.breakdown_minutes_one_person / crew_size)
    service = minutes - setup - breakdown
    if service < 15:
        raise DecisionError(f"The time on site must be at least {setup + breakdown + 15} minutes: setup and breakdown take {setup + breakdown}.")
    return setup, service, breakdown


@transaction.atomic
def price_quote_request(item, service, vehicle_class, amount, minutes, user, crew_size=1, size_variant=None):
    """Record the owner's hand price and time on site as a quote: one line,
    the price before tax, with the sales tax at the request's address today.
    The quote never changes; pricing again makes a new one."""
    if item.status not in (QuoteRequest.Status.NEW, QuoteRequest.Status.REPLIED):
        raise DecisionError("Only an open request can be priced.")
    if amount is None or amount <= 0:
        raise DecisionError("Enter the price before tax.")
    if minutes is None or minutes % 15:
        raise DecisionError("Enter the time on site in steps of 15 minutes.")
    if crew_size not in (1, 2):
        raise DecisionError("A crew is one or two people.")
    version = PricebookVersion.current()
    if version is None:
        raise DecisionError("No pricebook version is published.")
    setup, service_minutes, breakdown = split_minutes(minutes, crew_size)
    one_person_hours = Decimal(service_minutes * crew_size) / 60
    rules = PricingRules.objects.filter(version=version).first()
    one_person_minutes = setup * crew_size + service_minutes * crew_size + breakdown * crew_size
    full_day = bool(rules and one_person_minutes >= rules.full_day_time_on_site_hours * 60)
    tax = tax_line(item.service_address, amount, timezone.localdate())
    quote = Quote.objects.create(
        pricebook_version=version,
        service=service,
        vehicle_class=vehicle_class,
        size_variant=size_variant,
        crew_size=crew_size,
        total_before_tax=amount,
        service_address=item.service_address,
        tax_jurisdiction=tax.jurisdiction,
        taxable_amount=tax.taxable_amount,
        state_rate=tax.state_rate,
        local_rate=tax.local_rate,
        state_tax=tax.state_tax,
        local_tax=tax.local_tax,
        tax_rate=tax.rate,
        sales_tax=tax.sales_tax,
        tax_needs_check=tax.needs_check,
        total=amount + tax.sales_tax,
        one_person_service_hours=one_person_hours,
        service_minutes=service_minutes,
        setup_minutes=setup,
        breakdown_minutes=breakdown,
        time_on_site_minutes=minutes,
        full_day=full_day,
    )
    QuoteLine.objects.create(
        quote=quote,
        position=0,
        kind=PricedLine.Kind.SERVICE,
        description=f"{service.name}, priced by hand (quote request {item.reference})",
        amount=amount,
        one_person_service_hours=one_person_hours,
        vehicle_class_name=vehicle_class.name,
        size_variant_value=size_variant.value if size_variant else None,
        size_variant_label=size_variant.label if size_variant else "",
        service=service,
        pricebook_version=version,
        vehicle_class=vehicle_class,
        size_variant=size_variant,
    )
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
