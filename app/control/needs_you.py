"""The "needs you" list on the home screen (control-app.md): only what needs
a decision, newest first, with a count (decision 0107):

- a new customer's booking with no text consent, to call and confirm
  (decision 0112), with call and text links and "Mark confirmed";
- quote requests to price, offline requests to price and book, and booking
  requests: a website booking taken as a request because the number has a
  job that day or is past a confirmation cap (decision 0113);
- returning-customer differences: review flags from quiet matching;
- Time Off over a booked job (decision 0098), and a job the calendar sync
  keeps failing to push;
- sales tax rates waiting for approval (sales-tax.md).

A new booking is not an item, and neither is staffing: every new booking
gets the default staff (decision 0107). Push notifications come in Phase 4
and will announce new bookings; until then the Jobs calendar event on the
phone is the notice. An appointment has at most one item: when several
things need a decision on one job, the item names them all.
"""

import uuid
from dataclasses import dataclass, field

from django.urls import reverse
from django.utils import timezone

from appointments.confirmation import open_unconfirmed
from appointments.models import Appointment, MatchFlag
from billing.models import TaxRate
from calendars.models import CalendarFlag, SyncTask
from publicapi.models import QuoteRequest, SecondVehicleRequest, TimeRequest

# The most items the home screen lists; the count is always the full number.
SHOWN = 30
# A calendar push that has failed this many times in a row is listed; the
# worker keeps trying, but one failure is usually just a slow moment at Google.
FAILED_PUSHES = 3


@dataclass
class Item:
    kind: str
    when: object
    title: str
    detail: str
    url: str
    is_test: bool = False
    # The appointment the item is about, so a job is listed once.
    appointment_id: int = None
    also: list = field(default_factory=list)
    # Call and text links (request_views.contact_links), and where "Mark
    # confirmed" posts, for a job to confirm.
    contact: dict = None
    confirm_url: str = ""


def when_text(moment):
    local = timezone.localtime(moment)
    return f"{local:%a %b} {local.day}, {local:%-I:%M %p}"


def failed_pushes():
    """[(appointment, task)] for each job whose calendar push keeps failing."""
    tasks = {}
    for task in SyncTask.objects.filter(link__startswith="job:", attempts__gte=FAILED_PUSHES):
        try:
            tasks[uuid.UUID(task.link.removeprefix("job:")).hex] = task
        except ValueError:
            continue
    if not tasks:
        return []
    found = Appointment.objects.filter(calendar_key__in=[uuid.UUID(key) for key in tasks]).select_related("customer")
    return [(job, tasks[job.calendar_key.hex]) for job in found]


def one_per_appointment(found):
    """Fold the items about one appointment into its first one."""
    kept, by_job = [], {}
    for item in found:
        first = by_job.get(item.appointment_id) if item.appointment_id is not None else None
        if first is None:
            kept.append(item)
            if item.appointment_id is not None:
                by_job[item.appointment_id] = item
            continue
        first.also.append(item.title.split(":")[0])
        first.when = max(first.when, item.when)
    for item in kept:
        if item.also:
            item.detail += " · Also: " + ", ".join(dict.fromkeys(item.also)).lower()
    return kept


def items(user=None):
    """[Item], newest first."""
    from .request_views import contact_links

    found = []
    # First, so a job's other items fold into this one and keep its buttons.
    to_call = open_unconfirmed().filter(unconfirmed_reason=Appointment.UnconfirmedReason.CALL).select_related("customer")
    for job in to_call.order_by("scheduled_start"):
        found.append(Item(
            "call_to_confirm", job.created_at, f"Call to confirm: {job.customer}",
            f"{when_text(job.scheduled_start)} · a new customer, no text consent", reverse("appointment", args=[job.pk]),
            job.is_test, appointment_id=job.pk, contact=contact_links(job.customer),
            confirm_url=reverse("appointment-confirm", args=[job.pk]),
        ))
    flagged = {}
    for flag in MatchFlag.objects.filter(resolution="").select_related("appointment__customer").order_by("created_at"):
        flagged.setdefault(flag.appointment, []).append(flag)
    for job, flags in flagged.items():
        fields = ", ".join(dict.fromkeys(flag.get_field_display().lower() for flag in flags))
        found.append(Item(
            "review", flags[-1].created_at, f"Check the booking: {job.customer}",
            f"The {fields} differ{'s' if len(flags) == 1 else ''} from the record", reverse("match-review", args=[job.pk]), job.is_test,
            appointment_id=job.pk,
        ))
    for item in QuoteRequest.objects.filter(status=QuoteRequest.Status.NEW).select_related("customer"):
        found.append(Item(
            "quote_request", item.created_at, f"Quote request: {item.customer}",
            (item.vehicle_text or "Vehicle not given") + (" · priced, not booked" if item.quote_id else ""),
            reverse("quote-request", args=[item.pk]), item.is_test,
        ))
    for item in TimeRequest.objects.filter(status=TimeRequest.Status.NEW).select_related("customer"):
        detail = "Sent while the server was offline" + (", price differs" if item.price_differs else "")
        found.append(Item("time_request", item.received_at, f"Offline request: {item.customer}", detail,
                          reverse("time-request", args=[item.pk]), item.is_test))
    for item in SecondVehicleRequest.objects.filter(status=SecondVehicleRequest.Status.NEW).select_related("customer", "vehicle"):
        found.append(Item(
            "second_vehicle", item.created_at, f"Booking request: {item.customer}",
            f"{when_text(item.start)} · {item.vehicle} · {item.get_reason_display().lower()}", reverse("second-vehicle-request", args=[item.pk]), item.is_test,
        ))
    for flag in CalendarFlag.objects.filter(outcome=CalendarFlag.Outcome.OPEN, kind=CalendarFlag.Kind.CLASH).select_related("appointment__customer"):
        job = flag.appointment
        found.append(Item(
            "clash", flag.created_at, f"Time Off over a booked job: {job.customer if job else flag.summary}",
            flag.summary, reverse("schedule") + "#calendar-flags-heading", job.is_test if job else False,
            appointment_id=job.pk if job else None,
        ))
    for job, task in failed_pushes():
        found.append(Item(
            "sync", task.created_at, f"Calendar sync failing: {job.customer}",
            f"{when_text(job.scheduled_start)} · not on the Jobs calendar after {task.attempts} tries", reverse("appointment", args=[job.pk]),
            job.is_test, appointment_id=job.pk,
        ))
    for rate in TaxRate.objects.filter(approved_at__isnull=True, rejected_at__isnull=True).select_related("jurisdiction"):
        found.append(Item("tax_rate", rate.found_at, f"New sales tax rate: {rate.jurisdiction}",
                          f"{rate.combined_rate}% from {rate.effective_from:%b %-d, %Y}", reverse("sales-tax")))
    found = one_per_appointment(found)
    found.sort(key=lambda item: item.when, reverse=True)
    return found


def summary(user=None):
    """{"items": the newest SHOWN, "count": all of them, "more": how many aren't shown}."""
    found = items(user)
    return {"items": found[:SHOWN], "count": len(found), "more": max(len(found) - SHOWN, 0)}
