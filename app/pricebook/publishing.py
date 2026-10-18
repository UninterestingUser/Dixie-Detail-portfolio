"""What publishing a pricebook draft would change (pricebook-changes.md).

Completed jobs are never touched. affected_jobs() lists every booked job on
or after the effective date whose price, service hours or service the draft
would change, so the owner can decide each one. The control app screen that
asks the owner comes later; this is the list it shows.
"""

import datetime
from dataclasses import dataclass, field
from decimal import Decimal

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
