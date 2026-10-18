"""What publishing a pricebook draft would change (pricebook-changes.md).

Completed jobs are never touched. affected_jobs() lists every booked job on
or after the effective date whose price, service hours or service the draft
would change, so the owner can decide each one; publish() publishes the draft
and applies and logs the owner's choice for each.
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.scheduling import round_to_nearest, time_on_site

from .models import PricedLine
from .pricing import PricingError, price_job

PRICED_KINDS = [PricedLine.Kind.SERVICE, PricedLine.Kind.ADD_ON, PricedLine.Kind.CONDITION, PricedLine.Kind.PROMOTION]


@dataclass
class AffectedJob:
    appointment: object
    booked_total: Decimal
    booked_service_hours: Decimal
    # None when the draft can no longer price the job, such as a removed service.
    new_total: Decimal = None
    new_service_hours: Decimal = None
    reasons: list = field(default_factory=list)
    # The new service hours push a job that was not a full day into one.
    becomes_full_day: bool = False


def affected_jobs(version, effective_date):
    """The booked, not-yet-completed jobs from effective_date on that version
    would change, re-priced from the inputs their lines were booked with."""
    from appointments.models import Appointment

    start = timezone.make_aware(datetime.datetime.combine(effective_date, datetime.time.min))
    appointments = (
        Appointment.objects.filter(status=Appointment.Status.BOOKED, scheduled_start__gte=start)
        .prefetch_related("lines__service", "lines__promotion", "lines__vehicle_class", "lines__size_variant")
        .order_by("scheduled_start")
    )
    affected = []
    for appointment in appointments:
        job = _reprice(appointment, version)
        if job is not None:
            affected.append(job)
    return affected


def _reprice(appointment, version):
    lines = [line for line in appointment.lines.all() if line.kind in PRICED_KINDS]
    main = next((line for line in lines if line.kind == PricedLine.Kind.SERVICE and line.service), None)
    if main is None or main.vehicle_class is None:
        return None  # Nothing priced from the pricebook, such as a custom job.
    booked_total = sum((line.amount for line in lines), Decimal("0.00"))
    booked_hours = sum((line.one_person_service_hours or 0 for line in lines), Decimal("0"))
    result = AffectedJob(appointment, booked_total, booked_hours)
    size_variant = next((line.size_variant for line in lines if line.size_variant), None)
    try:
        job = price_job(
            main.service,
            main.vehicle_class,
            size_variant=size_variant,
            condition_level=main.condition_level,
            add_ons=[line.service for line in lines if line.kind == PricedLine.Kind.ADD_ON],
            promotions=[line.promotion for line in lines if line.kind == PricedLine.Kind.PROMOTION],
            crew_size=appointment.crew_size,
            version=version,
            check_promotion_dates=False,
        )
    except PricingError as error:
        result.reasons.append(f"Can no longer be priced: {error}")
        return result
    result.new_total = job.total_before_tax
    result.new_service_hours = job.one_person_service_hours
    if job.total_before_tax != booked_total:
        result.reasons.append(f"Price changes from ${booked_total} to ${job.total_before_tax}")
    if job.one_person_service_hours != booked_hours:
        result.reasons.append(f"Service hours change from {booked_hours:g} to {job.one_person_service_hours:g}")
        booked_stay = time_on_site(round_to_nearest(booked_hours * 60, 1), 1)
        result.becomes_full_day = job.full_day and booked_stay.total_minutes < job.full_day_time_on_site_hours * 60
    return result if result.reasons else None


class PublishError(ValueError):
    """The draft cannot be published with these choices."""


@transaction.atomic
def publish(version, effective_date, choices, user=None):
    """Publish a draft and apply the owner's choice for every affected job.

    choices maps an appointment id to ("keep", None), ("use_new", None) or
    ("custom", amount). A job with no choice keeps its booked price, the
    default. A job the draft can no longer price can only be kept or given a
    custom amount. Every choice is logged with the old and new amounts.
    """
    from appointments.booking import inputs_from_appointment, reprice, set_final_price
    from appointments.models import RepricingDecision

    affected = affected_jobs(version, effective_date)
    for job in affected:
        choice, amount = choices.get(job.appointment.pk, ("keep", None))
        if choice == "use_new" and job.new_total is None:
            raise PublishError(f"{job.appointment} can no longer be priced; keep it or give a custom amount.")
        if choice == "custom" and (amount is None or amount < 0):
            raise PublishError(f"Give a custom amount for {job.appointment}.")
        if choice not in ("keep", "use_new", "custom"):
            raise PublishError(f"Unknown choice {choice!r}.")
    version.publish(effective_date)
    for job in affected:
        appointment = job.appointment
        choice, amount = choices.get(appointment.pk, ("keep", None))
        if choice == "use_new":
            reprice(appointment, inputs_from_appointment(appointment), f"New price from pricebook version {version.number}", version=version)
        elif choice == "custom":
            set_final_price(appointment, amount, f"Custom amount chosen when pricebook version {version.number} was published")
        appointment.refresh_from_db()
        RepricingDecision.objects.create(
            appointment=appointment,
            pricebook_version=version,
            choice=choice,
            old_amount=job.booked_total,
            new_amount=appointment.total_before_tax if choice != "keep" else job.booked_total,
            decided_by=user,
        )
    return affected
