"""Who may perform which service, and assigning staff to a job (decision 0061).

Authorizations are ServiceAuthorization rows; managers need none, because
they are authorized for every service. A job's crew is qualified when the
people on it are, together, authorized for every service on the job.
"""

from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Q

from core.scheduling import automatic_assignment
from pricebook.models import PricedLine, Service

from .models import Assignment, ServiceAuthorization, StaffMember


class CrewError(ValueError):
    """The crew cannot be assigned as asked."""


def authorizable_services():
    """Every active service, add-ons included; history-only services and
    custom lines are left out."""
    return Service.objects.filter(
        on_price_list=True, kind__in=[Service.Kind.MAIN, Service.Kind.ADD_ON, Service.Kind.MAINTENANCE_PLAN]
    ).order_by("kind", "name")


def authorized_service_ids(member):
    if member.is_manager:
        return set(authorizable_services().values_list("pk", flat=True))
    return set(member.authorizations.values_list("service_id", flat=True))


def set_authorization(member, service, authorized, user=None):
    """Grant or remove one authorization. A manager's cannot be removed."""
    if member.is_manager:
        raise ValueError(f"{member} is a manager and is authorized for every service.")
    if not authorizable_services().filter(pk=service.pk).exists():
        raise ValueError(f"{service} is not an active service.")
    if authorized:
        ServiceAuthorization.objects.get_or_create(staff_member=member, service=service, defaults={"granted_by": user})
    else:
        for row in ServiceAuthorization.objects.filter(staff_member=member, service=service):
            row.delete()


def user_is_manager(user):
    """A signed-in user who may act as a manager: a superuser, or someone
    whose staff record is a manager's."""
    if user.is_superuser:
        return True
    member = getattr(user, "staff_member", None)
    return bool(member and member.active and member.is_manager)


def job_services(appointment):
    """The services on a job that need authorization, in line order."""
    services = []
    for line in appointment.lines.select_related("service"):
        if line.kind in (PricedLine.Kind.SERVICE, PricedLine.Kind.ADD_ON) and line.service and line.service not in services:
            services.append(line.service)
    return services


@dataclass
class StaffChoice:
    member: StaffMember
    qualified: bool
    missing: list = field(default_factory=list)


def staff_choices(appointment):
    """Every active staff member for the assign-staff control: qualified staff
    first, then the rest with the services they are not authorized for."""
    services = job_services(appointment)
    choices = []
    for member in StaffMember.objects.filter(active=True).prefetch_related("authorizations"):
        allowed = authorized_service_ids(member)
        missing = [service for service in services if service.pk not in allowed]
        choices.append(StaffChoice(member, not missing, missing))
    choices.sort(key=lambda choice: (not choice.qualified, not choice.member.is_manager, choice.member.name))
    return choices


def uncovered_services(members, services):
    """The services no one in the crew is authorized for."""
    allowed = set()
    for member in members:
        allowed |= authorized_service_ids(member)
    return [service for service in services if service.pk not in allowed]


@transaction.atomic
def assign_crew(appointment, members, training_reason="", by_manager=False):
    """Put these people on the job. Together they must be authorized for every
    service on it, unless a manager assigns them anyway with a reason, which
    is recorded on each person missing a service the crew lacks. Returns the
    services the crew was not authorized for."""
    members = list(dict.fromkeys(members))
    if len(members) > 2:
        raise CrewError("A crew is one or two people.")
    services = job_services(appointment)
    gaps = uncovered_services(members, services)
    if gaps:
        if not by_manager:
            raise CrewError("Only a manager can assign someone not yet authorized.")
        if not training_reason.strip():
            raise CrewError("Give the reason for assigning someone not yet authorized, such as training.")
    gap_ids = {service.pk for service in gaps}
    appointment.assignments.exclude(staff_member__in=members).delete()
    for member in members:
        lacks = gap_ids - authorized_service_ids(member)
        assignment, _ = Assignment.objects.get_or_create(appointment=appointment, staff_member=member)
        assignment.training_reason = training_reason.strip() if lacks else ""
        assignment.save()
    return gaps


def auto_assign(appointment):
    """Assign the only qualified active staff member to a one-person job, when
    the setting is on (decision 0061). Returns the person, or None when the
    prompt is needed: two or more qualified, none, or a two-person job."""
    if not automatic_assignment() or appointment.crew_size != 1 or appointment.assignments.exists():
        return None
    qualified = [choice.member for choice in staff_choices(appointment) if choice.qualified]
    if len(qualified) != 1:
        return None
    assign_crew(appointment, qualified)
    return qualified[0]


def services_for_staff(member):
    """Each authorizable service and whether this person is authorized for it."""
    allowed = authorized_service_ids(member)
    return [(service, service.pk in allowed) for service in authorizable_services()]


def staff_for_service(service):
    """Each active staff member and whether they are authorized for this service."""
    rows = []
    for member in StaffMember.objects.filter(Q(active=True)).order_by("name"):
        rows.append((member, member.is_manager or member.authorizations.filter(service=service).exists()))
    return rows
