"""Booking, re-pricing and changing jobs from the control app.

Every price comes from the pricing engine through a quote (decision 0059):
booking issues a quote and copies its lines, and changing a job's services
issues a new quote, with the owner's reason kept in the change history. The
owner may book any date; the availability rules arrive in Phase 3.
"""

import calendar
import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.scheduling import time_on_site
from pricebook.models import PricebookVersion, PricedLine, PricingRules, Service
from pricebook.pricing import crew_service_minutes, issue_quote

from .models import Appointment, AppointmentLine, RecurringSeries

# The lines a quote gives a job. Custom, on-site adjustment and no-charge
# lines are the owner's own and are kept when a job is re-priced.
QUOTED_KINDS = [PricedLine.Kind.SERVICE, PricedLine.Kind.ADD_ON, PricedLine.Kind.CONDITION, PricedLine.Kind.PROMOTION]
ZERO = Decimal("0.00")


class BookingError(ValueError):
    """The job cannot be booked or changed as asked."""


@dataclass
class JobInputs:
    """What a job is priced from."""

    service: Service
    vehicle_class: object
    size_variant: object = None
    condition_level: int = None
    add_ons: list = field(default_factory=list)
    promotions: list = field(default_factory=list)
    crew_size: int = None

    def quote(self, on, version=None):
        return issue_quote(
            self.service,
            self.vehicle_class,
            size_variant=self.size_variant,
            condition_level=self.condition_level,
            add_ons=self.add_ons,
            promotions=self.promotions,
            crew_size=self.crew_size,
            on=on,
            version=version or version_for(on),
            check_promotion_dates=False,
        )


def version_for(day):
    """The published pricebook in effect on a day. A day before the first
    version took effect, such as a past job entered late, uses today's."""
    return PricebookVersion.current(day) or PricebookVersion.current()


def inputs_from_appointment(appointment):
    """The inputs a job was priced from: its quote's, or for a job booked
    without one, such as an imported job, read from its lines. None when
    nothing on it came from the pricebook."""
    quote = appointment.quote
    if quote is not None:
        return JobInputs(
            quote.service,
            quote.vehicle_class,
            quote.size_variant,
            quote.condition_level,
            list(quote.add_ons.all()),
            list(quote.promotions.all()),
            appointment.crew_size,
        )
    lines = list(appointment.lines.select_related("service", "vehicle_class", "size_variant", "promotion"))
    main = next((line for line in lines if line.kind == PricedLine.Kind.SERVICE and line.service), None)
    if main is None or main.vehicle_class is None:
        return None
    return JobInputs(
        main.service,
        main.vehicle_class,
        next((line.size_variant for line in lines if line.size_variant), None),
        main.condition_level,
        [line.service for line in lines if line.kind == PricedLine.Kind.ADD_ON and line.service],
        [line.promotion for line in lines if line.kind == PricedLine.Kind.PROMOTION and line.promotion],
        appointment.crew_size,
    )


def local_date(moment):
    return timezone.localtime(moment).date()


@transaction.atomic
def book(customer, vehicle, start, inputs, *, address=None, notes="", series=None, source=Appointment.Source.OWNER):
    """Book one job: issue a quote priced from the pricebook in effect on its
    date, and copy the quote's lines onto the new appointment."""
    quote = inputs.quote(on=local_date(start))
    return Appointment.book_from_quote(
        quote,
        customer=customer,
        vehicle=vehicle,
        service_address=address,
        scheduled_start=start,
        source=source,
        notes=notes,
        series=series,
        status=Appointment.Status.BOOKED,
    )


def add_months(day, months):
    """The same day of the month, months later, or that month's last day."""
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return day.replace(year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1]))


def series_dates(first, frequency, visits):
    """The visit dates of a repeating series, from the first visit."""
    step = 1 if frequency == RecurringSeries.Frequency.MONTHLY else 3
    return [add_months(first, step * number) for number in range(visits)]


@transaction.atomic
def book_series(customer, vehicle, first_start, inputs, frequency, visits, *, address=None, notes=""):
    """Book a repeating Monthly or Quarterly Maintenance series: one job per
    visit at the same time of day, each priced from the pricebook in effect
    on its own date."""
    if inputs.service.kind != Service.Kind.MAINTENANCE_PLAN:
        raise BookingError("Only a maintenance plan can be booked as a repeating series.")
    if not 2 <= visits <= 24:
        raise BookingError("A series has 2 to 24 visits.")
    first = timezone.localtime(first_start)
    dates = series_dates(first.date(), frequency, visits)
    series = RecurringSeries.objects.create(
        customer=customer, vehicle=vehicle, service=inputs.service, frequency=frequency,
        starts_on=dates[0], ends_on=dates[-1], notes=notes,
    )
    for day in dates:
        start = timezone.make_aware(datetime.datetime.combine(day, first.time().replace(tzinfo=None)))
        book(customer, vehicle, start, inputs, address=address, notes=notes, series=series)
    return series


def _replace_quoted_lines(appointment, quote):
    kept = list(appointment.lines.exclude(kind__in=QUOTED_KINDS).order_by("position", "id"))
    appointment.lines.filter(kind__in=QUOTED_KINDS).delete()
    position = 0
    for quote_line in quote.lines.all():
        AppointmentLine.objects.create(
            appointment=appointment,
            **{name: getattr(quote_line, name) for name in PricedLine.COPIED_FIELDS} | {"position": position},
        )
        position += 1
    for line in kept:
        line.position = position
        line.save(update_fields=["position"])
        position += 1


@transaction.atomic
def reprice(appointment, inputs, reason, version=None):
    """Change a booked job's services: issue a new quote and replace the lines
    it priced. The owner's reason is kept in the job's change history."""
    if appointment.status != Appointment.Status.BOOKED:
        raise BookingError("Only a booked job can be re-priced; completed and canceled jobs keep their prices.")
    if not reason.strip():
        raise BookingError("Give a reason for changing the job's services.")
    quote = inputs.quote(on=local_date(appointment.scheduled_start), version=version)
    _replace_quoted_lines(appointment, quote)
    appointment.quote = quote
    appointment.crew_size = quote.crew_size
    appointment.setup_minutes = quote.setup_minutes
    appointment.service_minutes = quote.service_minutes
    appointment.breakdown_minutes = quote.breakdown_minutes
    appointment._change_reason = reason.strip()
    appointment.save()
    return appointment


def one_person_service_hours(appointment):
    hours = [line.one_person_service_hours for line in appointment.lines.all() if line.one_person_service_hours is not None]
    return sum(hours, Decimal("0")) if hours else None


def pricing_rules_for(appointment):
    """The crew rules of the version the job was priced from, or of the
    version in effect on its date."""
    line = appointment.lines.filter(pricebook_version__isnull=False).select_related("pricebook_version").first()
    version = line.pricebook_version if line else PricebookVersion.current(local_date(appointment.scheduled_start))
    return PricingRules.objects.filter(version=version).first() if version else None


@transaction.atomic
def change_crew_size(appointment, crew_size):
    """Recalculate the service time and time on site for a different crew:
    the crew factor on the service hours, and setup and breakdown divided by
    the crew (decision 0061). The price does not change."""
    if crew_size not in (1, 2):
        raise BookingError("A crew is one or two people.")
    if crew_size == appointment.crew_size:
        return appointment
    appointment.crew_size = crew_size
    hours, rules = one_person_service_hours(appointment), pricing_rules_for(appointment)
    if hours is not None and rules is not None:
        stay = time_on_site(crew_service_minutes(hours, crew_size, rules), crew_size)
        appointment.setup_minutes = stay.setup_minutes
        appointment.service_minutes = stay.service_minutes
        appointment.breakdown_minutes = stay.breakdown_minutes
    appointment._change_reason = f"Crew changed to {crew_size}"
    appointment.save()
    return appointment


def overlapping(appointment):
    """Other jobs that day, not canceled, whose time on site overlaps this one's."""
    day = local_date(appointment.scheduled_start)
    start = appointment.scheduled_start
    end = appointment.ends_at or start
    found = []
    for other in Appointment.objects.exclude(pk=appointment.pk).exclude(status=Appointment.Status.CANCELED).filter(
        scheduled_start__date=day
    ).select_related("customer"):
        other_end = other.ends_at or other.scheduled_start
        if (other.scheduled_start < end and start < other_end) or other.scheduled_start == start:
            found.append(other)
    return found


@transaction.atomic
def set_status(appointment, status):
    """Booked, completed or canceled. Completing records when."""
    if status not in (Appointment.Status.BOOKED, Appointment.Status.COMPLETED, Appointment.Status.CANCELED):
        raise BookingError("A job is booked, completed or canceled.")
    appointment.status = status
    if status == Appointment.Status.COMPLETED:
        appointment.completed_at = appointment.completed_at or timezone.now()
    else:
        appointment.completed_at = None
    appointment._change_reason = f"Marked {appointment.get_status_display().lower()}"
    appointment.save()
    return appointment


ADJUSTMENT_DESCRIPTION = "On-site adjustment"


@transaction.atomic
def set_final_price(appointment, final_price, reason):
    """Make the job's total the final price with one on-site adjustment line
    for the difference, carrying its reason. A final price equal to the total
    without an adjustment removes the adjustment."""
    if appointment.status == Appointment.Status.CANCELED:
        raise BookingError("A canceled job has no final price.")
    if final_price < 0:
        raise BookingError("The final price cannot be below zero.")
    appointment.lines.filter(kind=PricedLine.Kind.ADJUSTMENT, description=ADJUSTMENT_DESCRIPTION).delete()
    difference = final_price - appointment.total_before_tax
    if difference:
        if not reason.strip():
            raise BookingError("Give the reason for the on-site adjustment.")
        last = appointment.lines.order_by("-position").first()
        AppointmentLine.objects.create(
            appointment=appointment,
            position=(last.position + 1) if last else 0,
            kind=PricedLine.Kind.ADJUSTMENT,
            description=ADJUSTMENT_DESCRIPTION,
            amount=difference,
            reason=reason.strip(),
        )
    return appointment
