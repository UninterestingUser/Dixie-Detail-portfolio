"""The "needs you" list on the home screen (control-app.md): everything
waiting for the owner, newest first, with a count.

- new website bookings since the user last cleared them;
- review flags from quiet matching, one item per job;
- website jobs with no staff, the assign-staff prompt (decisions 0061 and 0069);
- requests waiting for a decision: quote requests, offline requests and a
  second vehicle the same day;
- Time Off over a booked job (decision 0098), and sales tax rates waiting
  for approval (sales-tax.md).

Push notifications come in Phase 4. Until then the Jobs calendar event on
the phone is the alert for a new booking.
"""

from dataclasses import dataclass

from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, MatchFlag
from billing.models import TaxRate
from calendars.models import CalendarFlag
from publicapi.models import QuoteRequest, SecondVehicleRequest, TimeRequest

from .models import SeenMarker

# The most items the home screen lists; the count is always the full number.
SHOWN = 30


@dataclass
class Item:
    kind: str
    when: object
    title: str
    detail: str
    url: str
    is_test: bool = False


def when_text(moment):
    local = timezone.localtime(moment)
    return f"{local:%a %b} {local.day}, {local:%-I:%M %p}"


def seen_at(user):
    marker = SeenMarker.objects.filter(user=user).first() if user.is_authenticated else None
    return marker.website_bookings_seen_at if marker else None


def mark_seen(user, moment=None):
    SeenMarker.objects.update_or_create(user=user, defaults={"website_bookings_seen_at": moment or timezone.now()})


def new_bookings(user):
    """Website bookings made since the user last cleared them."""
    found = Appointment.objects.filter(source=Appointment.Source.WEBSITE, reference__isnull=False).select_related("customer", "vehicle")
    since = seen_at(user)
    if since is not None:
        found = found.filter(created_at__gt=since)
    return found.order_by("-created_at")


def items(user):
    """[Item], newest first."""
    found = []
    for job in new_bookings(user)[:100]:
        found.append(Item(
            "booking", job.created_at, f"New booking: {job.customer}",
            f"{when_text(job.scheduled_start)} · {job.vehicle or 'no vehicle'}", reverse("appointment", args=[job.pk]), job.is_test,
        ))
    flagged = {}
    for flag in MatchFlag.objects.filter(resolution="").select_related("appointment__customer").order_by("created_at"):
        flagged.setdefault(flag.appointment, []).append(flag)
    for job, flags in flagged.items():
        fields = ", ".join(dict.fromkeys(flag.get_field_display().lower() for flag in flags))
        found.append(Item(
            "review", flags[-1].created_at, f"Check the booking: {job.customer}",
            f"The {fields} differ{'s' if len(flags) == 1 else ''} from the record", reverse("match-review", args=[job.pk]), job.is_test,
        ))
    unstaffed = (
        Appointment.objects.filter(source=Appointment.Source.WEBSITE, status=Appointment.Status.BOOKED, scheduled_start__gte=timezone.now(), assignments__isnull=True)
        .select_related("customer").order_by("-created_at")
    )
    for job in unstaffed[:100]:
        found.append(Item(
            "staff", job.created_at, f"Assign staff: {job.customer}", f"{when_text(job.scheduled_start)}",
            reverse("appointment", args=[job.pk]) + "#staff-heading", job.is_test,
        ))
    for item in QuoteRequest.objects.filter(status=QuoteRequest.Status.NEW).select_related("customer"):
        found.append(Item(
            "quote_request", item.created_at, f"Quote request: {item.customer}", item.vehicle_text or "Vehicle not given",
            reverse("quote-request", args=[item.pk]), item.is_test,
        ))
    for item in TimeRequest.objects.filter(status=TimeRequest.Status.NEW).select_related("customer"):
        detail = "Sent while the server was offline" + (", price differs" if item.price_differs else "")
        found.append(Item("time_request", item.received_at, f"Offline request: {item.customer}", detail,
                          reverse("time-request", args=[item.pk]), item.is_test))
    for item in SecondVehicleRequest.objects.filter(status=SecondVehicleRequest.Status.NEW).select_related("customer", "vehicle"):
        found.append(Item(
            "second_vehicle", item.created_at, f"Second vehicle the same day: {item.customer}",
            f"{when_text(item.start)} · {item.vehicle}", reverse("second-vehicle-request", args=[item.pk]), item.is_test,
        ))
    for flag in CalendarFlag.objects.filter(outcome=CalendarFlag.Outcome.OPEN, kind=CalendarFlag.Kind.CLASH).select_related("appointment__customer"):
        found.append(Item(
            "clash", flag.created_at, f"Time Off over a booked job: {flag.appointment.customer if flag.appointment else flag.summary}",
            flag.summary, reverse("schedule") + "#calendar-flags-heading",
        ))
    for rate in TaxRate.objects.filter(approved_at__isnull=True, rejected_at__isnull=True).select_related("jurisdiction"):
        found.append(Item("tax_rate", rate.found_at, f"New sales tax rate: {rate.jurisdiction}",
                          f"{rate.combined_rate}% from {rate.effective_from:%b %-d, %Y}", reverse("sales-tax")))
    found.sort(key=lambda item: item.when, reverse=True)
    return found


def summary(user):
    """{"items": the newest SHOWN, "count": all of them, "new_bookings": how many}."""
    found = items(user)
    bookings = [item.when for item in found if item.kind == "booking"]
    return {
        "newest_booking": max(bookings) if bookings else None,
        "items": found[:SHOWN],
        "count": len(found),
        "more": max(len(found) - SHOWN, 0),
        "new_bookings": sum(1 for item in found if item.kind == "booking"),
    }
