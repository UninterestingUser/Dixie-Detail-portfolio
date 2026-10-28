"""What publishing a pricebook draft would change (pricebook-changes.md).

Completed jobs are never touched. affected_jobs() lists every booked job on
or after the effective date whose price, service hours or service the draft
would change, so the owner can decide each one; publish() publishes the draft
and applies and logs the owner's choice for each.

A job booked in a class since retired, as the body-type classes were by the
switch to the size-based classes (decision 0083), is re-priced in its
vehicle's class now. apply_size_classes publishes with every booked job
keeping its quoted price and logs no choice, so the owner decides each later
on the version's booked-job review (undecided_jobs() and decide()). Such a
job with no vehicle, or whose vehicle has no live class or no size variant,
is not re-priced: it keeps its quoted price and is listed to check by hand.
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
    # The class and size it is re-priced in, when its own class is retired.
    new_class: object = None
    new_size: object = None
    # Booked in a retired class with no vehicle, or a vehicle with no live
    # class or size variant: not re-priced, keeps its quoted price.
    check_by_hand: bool = False

    def describe(self):
        """The job without the customer's name: id, date and vehicle."""
        return describe_appointment(self.appointment)


def describe_appointment(appointment):
    """An appointment as command output shows it: id, date and vehicle, never the customer."""
    day = f"appointment {appointment.pk} on {timezone.localtime(appointment.scheduled_start):%Y-%m-%d}"
    vehicle = appointment.vehicle
    if vehicle is None:
        return f"{day}, no vehicle"
    name = " ".join(str(part) for part in (vehicle.year, vehicle.make, vehicle.model) if part) or "no year, make or model"
    return f"{day}, vehicle {vehicle.pk}: {name}"


CHECK_BY_HAND = "no vehicle or class: check by hand"


class RepriceFailed(ValueError):
    """Re-pricing one booked job failed for a reason nobody foresaw."""


def affected_jobs(version, effective_date):
    """The booked, not-yet-completed jobs from effective_date on that version
    would change, re-priced from the inputs their lines were booked with."""
    from appointments.models import Appointment

    start = timezone.make_aware(datetime.datetime.combine(effective_date, datetime.time.min))
    appointments = (
        Appointment.objects.filter(status=Appointment.Status.BOOKED, scheduled_start__gte=start)
        .select_related("vehicle__vehicle_class", "vehicle__size_variant")
        .prefetch_related("lines__service", "lines__promotion", "lines__vehicle_class", "lines__size_variant")
        .order_by("scheduled_start")
    )
    affected = []
    for appointment in appointments:
        try:
            job = _reprice(appointment, version)
        except Exception as error:
            raise RepriceFailed(f"re-pricing {describe_appointment(appointment)}: {type(error).__name__}: {error}") from error
        if job is not None:
            affected.append(job)
    return affected


def vehicle_class_and_size(vehicle):
    """(class, size variant) to re-price a job in its vehicle's class, or
    None when the vehicle is missing, has no live class, or has no size
    variant of a class that has them."""
    if vehicle is None or vehicle.vehicle_class is None or not vehicle.vehicle_class.active:
        return None
    vehicle_class, size_variant = vehicle.vehicle_class, vehicle.size_variant
    if vehicle_class.size_variants.filter(active=True).exists():
        if size_variant is None or size_variant.vehicle_class_id != vehicle_class.pk:
            return None
    return vehicle_class, size_variant


def _reprice(appointment, version):
    lines = [line for line in appointment.lines.all() if line.kind in PRICED_KINDS]
    main = next((line for line in lines if line.kind == PricedLine.Kind.SERVICE and line.service), None)
    if main is None or main.vehicle_class is None:
        return None  # Nothing priced from the pricebook, such as a custom job.
    booked_total = sum((line.amount for line in lines), Decimal("0.00"))
    booked_hours = sum((line.one_person_service_hours or 0 for line in lines), Decimal("0"))
    result = AffectedJob(appointment, booked_total, booked_hours)
    vehicle_class = main.vehicle_class
    size_variant = next((line.size_variant for line in lines if line.size_variant), None)
    if not vehicle_class.active:
        found = vehicle_class_and_size(appointment.vehicle)
        if found is None:
            result.check_by_hand = True
            result.reasons.append(CHECK_BY_HAND)
            return result
        vehicle_class, size_variant = found
        result.new_class, result.new_size = vehicle_class, size_variant
    try:
        job = price_job(
            main.service,
            vehicle_class,
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


def check_choice(job, choice, amount):
    if choice == "use_new" and job.new_total is None:
        raise PublishError(f"{job.describe()} can no longer be priced; keep it or give a custom amount.")
    if choice == "custom" and (amount is None or amount < 0):
        raise PublishError(f"Give a custom amount for {job.describe()}.")
    if choice not in ("keep", "use_new", "custom"):
        raise PublishError(f"Unknown choice {choice!r}.")


def decide(version, job, choice, amount=None, user=None):
    """Apply and log the owner's choice for one affected job of a published version."""
    from appointments.booking import inputs_from_appointment, reprice, set_final_price
    from appointments.models import RepricingDecision

    check_choice(job, choice, amount)
    appointment = job.appointment
    if choice == "use_new":
        inputs = inputs_from_appointment(appointment)
        if job.new_class is not None:
            inputs.vehicle_class, inputs.size_variant = job.new_class, job.new_size
        reprice(appointment, inputs, f"New price from pricebook version {version.number}", version=version)
    elif choice == "custom":
        set_final_price(appointment, amount, f"Custom amount chosen for pricebook version {version.number}")
    appointment.refresh_from_db()
    return RepricingDecision.objects.create(
        appointment=appointment,
        pricebook_version=version,
        choice=choice,
        old_amount=job.booked_total,
        new_amount=appointment.total_before_tax if choice != "keep" else job.booked_total,
        decided_by=user,
    )


@transaction.atomic
def publish(version, effective_date, choices, user=None, log_choices=True):
    """Publish a draft and apply the owner's choice for every affected job.

    choices maps an appointment id to ("keep", None), ("use_new", None) or
    ("custom", amount). A job with no choice keeps its booked price, the
    default. A job the draft can no longer price can only be kept or given a
    custom amount. Every choice is logged with the old and new amounts;
    with log_choices off, as apply_size_classes publishes, none is, and the
    owner decides each job later on the booked-job review.
    """
    affected = affected_jobs(version, effective_date)
    for job in affected:
        check_choice(job, *choices.get(job.appointment.pk, ("keep", None)))
    version.publish(effective_date)
    if log_choices:
        for job in affected:
            decide(version, job, *choices.get(job.appointment.pk, ("keep", None)), user=user)
    return affected


def undecided_jobs(version):
    """The affected jobs of a published version with no logged choice yet."""
    from appointments.models import RepricingDecision

    if not version.is_published:
        return []
    decided = set(RepricingDecision.objects.filter(pricebook_version=version).values_list("appointment_id", flat=True))
    return [job for job in affected_jobs(version, version.effective_date) if job.appointment.pk not in decided]
