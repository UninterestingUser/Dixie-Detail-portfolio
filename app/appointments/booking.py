"""Booking, re-pricing and changing jobs from the control app.

Every price comes from the pricing engine through a quote (decision 0059):
booking issues a quote and copies its lines, and changing a job's services
issues a new quote, with the owner's reason kept in the change history.

Every booking is checked against the scheduling rules (scheduling.availability).
The website can only book an open time. The owner can book outside a rule in
the control app after a warning naming it, with a reason that is logged
(RuleOverride).
"""

import calendar
import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.scheduling import time_on_site
from geo.drive import drive_from_home
from pricebook.models import PricebookVersion, PricedLine, PricingRules, Quote, Service
from pricebook.pricing import crew_service_minutes, issue_quote, price_job
from scheduling import availability
from scheduling.models import RuleOverride

from .models import Appointment, AppointmentLine, MatchFlag, RecurringSeries

# The lines a quote gives a job. Custom, on-site adjustment and no-charge
# lines are the owner's own and are kept when a job is re-priced.
QUOTED_KINDS = [PricedLine.Kind.SERVICE, PricedLine.Kind.ADD_ON, PricedLine.Kind.CONDITION, PricedLine.Kind.PROMOTION]
ZERO = Decimal("0.00")


class BookingError(ValueError):
    """The job cannot be booked or changed as asked."""


class RulesBroken(BookingError):
    """The job breaks scheduling rules. broken is [(start, [Reason])]."""

    def __init__(self, broken):
        self.broken = broken
        super().__init__("; ".join(f"{timezone.localtime(start):%a %b %-d, %-I:%M %p}: {', '.join(map(str, reasons))}" for start, reasons in broken))


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

    def quote(self, on, version=None, address=None):
        return issue_quote(
            self.service,
            self.vehicle_class,
            address=address,
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


def job_to_place(inputs, day, address=None, appointment=None):
    """The job as the availability check sees it: the time on site priced
    for its date, its main service and its address's location. A job not
    priced from the pricebook keeps its booked time on site."""
    point = address.point if address is not None else None
    if inputs is None:
        minutes = appointment.time_on_site_minutes if appointment is not None else None
        return availability.Job(minutes or 0, point=point)
    job = price_job(
        inputs.service, inputs.vehicle_class, size_variant=inputs.size_variant, condition_level=inputs.condition_level,
        add_ons=inputs.add_ons, crew_size=inputs.crew_size, on=day, version=version_for(day), check_promotion_dates=False,
    )
    return availability.Job(job.time_on_site.total_minutes, inputs.service.pk, inputs.service.name, point)


def rules_broken(inputs, starts, address=None, appointment=None):
    """[(start, [Reason])] for each start that breaks a scheduling rule.
    appointment is the job being changed, left out of its own day."""
    exclude = appointment.pk if appointment is not None else None
    found = []
    for start in starts:
        job = job_to_place(inputs, local_date(start), address, appointment)
        reasons = availability.check(job, start, exclude=exclude)
        if reasons:
            found.append((start, reasons))
    return found


# The rules that can be judged before the services are chosen: the day, the
# arrival time, Time Off, and sharing the day, with the new job taken as a
# regular one that can't share (decision 0097).
RULES_WITHOUT_SERVICES = {"day", "start_time", "time_off", "capacity"}


def rules_broken_without_services(start, address=None, appointment=None):
    """[(start, [Reason])] for a start, before the job's services are known:
    only the rules in RULES_WITHOUT_SERVICES."""
    job = availability.Job(0, None, "a job with no services chosen yet", address.point if address is not None else None)
    exclude = appointment.pk if appointment is not None else None
    reasons = [reason for reason in availability.check(job, start, exclude=exclude) if reason.rule in RULES_WITHOUT_SERVICES]
    return [(start, reasons)] if reasons else []


def log_override(appointment, reasons, reason, user, action=RuleOverride.Action.BOOKED):
    """Log a manager's booking or move outside the rules: the rules broken,
    in the alert's plain words, the reason, the start, who and when."""
    return RuleOverride.objects.create(
        appointment=appointment, action=action, start=appointment.scheduled_start,
        rules_broken=[broken.text for broken in reasons], reason=reason.strip(), made_by=user,
    )


@transaction.atomic
def book_online(customer, vehicle, start, inputs, *, address=None, notes=""):
    """A booking from the website: only an open time, never an override."""
    broken = rules_broken(inputs, [start], address)
    if broken:
        raise RulesBroken(broken)
    return book(customer, vehicle, start, inputs, address=address, notes=notes, source=Appointment.Source.WEBSITE)


@transaction.atomic
def book(customer, vehicle, start, inputs, *, address=None, notes="", series=None, source=Appointment.Source.OWNER):
    """Book one job: issue a quote priced from the pricebook in effect on its
    date, with the sales tax for its address, copy the quote's lines onto the
    new appointment, and work out the drive from the home base."""
    quote = inputs.quote(on=local_date(start), address=address)
    drive = drive_from_home(address, start)
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
        drive_minutes=drive.minutes if drive else None,
        drive_estimated=drive.estimated if drive else False,
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


def series_starts(first_start, frequency, visits):
    """The start of each visit of a series, at the same Eastern time of day."""
    first = timezone.localtime(first_start)
    return [
        timezone.make_aware(datetime.datetime.combine(day, first.time().replace(tzinfo=None)))
        for day in series_dates(first.date(), frequency, visits)
    ]


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
    quote = inputs.quote(on=local_date(appointment.scheduled_start), version=version, address=appointment.service_address)
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
    """Booked or completed. Completing records when. A job is canceled with
    cancel(), and a canceled job stays canceled."""
    if appointment.status == Appointment.Status.CANCELED:
        raise BookingError("A canceled job stays canceled. Book a new job instead.")
    if status not in (Appointment.Status.BOOKED, Appointment.Status.COMPLETED):
        raise BookingError("A job is marked booked or completed. Use Cancel job to cancel it.")
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


# Canceling and removing jobs (decision 0095).


def visits_from(appointment, later=False):
    """The job, or with later, it and its series' later booked visits."""
    if not later or appointment.series_id is None:
        return [appointment]
    return list(
        Appointment.objects.filter(
            series_id=appointment.series_id, scheduled_start__gte=appointment.scheduled_start, status=Appointment.Status.BOOKED,
        ).order_by("scheduled_start")
    )


def end_series_if_done(series):
    """A series with no booked visits left stops repeating."""
    if series is not None and not series.appointments.filter(status=Appointment.Status.BOOKED).exists():
        series.active = False
        series.save(update_fields=["active"])


@transaction.atomic
def cancel(appointment, canceled_by, user, later=False):
    """Cancel a booked job, or with later, it and its series' later visits.
    Each stays as the same record, marked canceled, with who canceled (the
    customer or the business), who pressed the button and when. A canceled
    job frees its time at once: the availability check and every list of
    booked jobs leave it out."""
    if appointment.status != Appointment.Status.BOOKED:
        raise BookingError("Only a booked job can be canceled.")
    if canceled_by not in Appointment.CanceledBy.values:
        raise BookingError("Say who canceled: the customer or Dixie Detail.")
    now = timezone.now()
    jobs = visits_from(appointment, later)
    for job in jobs:
        job.status = Appointment.Status.CANCELED
        job.canceled_by = canceled_by
        job.canceled_at = now
        job.canceled_by_user = user
        job.completed_at = None
        job._change_reason = Appointment.CanceledBy(canceled_by).label
        job.save()
    end_series_if_done(appointment.series)
    return jobs


def removal_refused(jobs):
    """Why these jobs can't be removed for good, or None."""
    for job in jobs:
        if job.payments.exists():
            return "This job has a payment recorded, so it can't be removed. Cancel it instead." if len(jobs) == 1 else (
                f"The {local_date(job.scheduled_start):%b %-d} visit has a payment recorded, so these visits can't be removed. Cancel them instead."
            )
        if hasattr(job, "invoice"):
            return "This job has an invoice, so it can't be removed. Cancel it instead."
        if job.assignments.filter(payout__isnull=False).exists():
            return "A staff member was paid for this job, so it can't be removed. Cancel it instead."
    return None


@transaction.atomic
def remove(appointment, later=False):
    """Delete a job created by mistake, or with later, it and its series'
    later visits, as if they never existed: their lines, staff assignments,
    flags, override and review records, change history, and every quote
    they were priced from that nothing else uses. A series left with no
    visits goes too. A job with a payment can't be removed."""
    jobs = visits_from(appointment, later)
    refused = removal_refused(jobs)
    if refused:
        raise BookingError(refused)
    ids = [job.pk for job in jobs]
    quote_ids = set(Appointment.history.filter(id__in=ids, quote__isnull=False).values_list("quote_id", flat=True))
    series = appointment.series
    MatchFlag.objects.filter(appointment_id__in=ids).delete()
    Appointment.objects.filter(pk__in=ids).delete()
    # Deleting adds a last history record; remove it with the rest.
    Appointment.history.filter(id__in=ids).delete()
    AppointmentLine.history.filter(appointment_id__in=ids).delete()
    Quote.objects.filter(pk__in=quote_ids, appointment__isnull=True).delete()
    if series is not None:
        if series.appointments.exists():
            end_series_if_done(series)
        else:
            series.delete()
    return len(ids)
