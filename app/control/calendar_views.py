"""The calendar flags on the control app's home screen (decisions 0057 and
0098): Time Off over a booked job, events added to the Jobs calendar by
hand, and Jobs events put back after an edit in Google."""

from django.contrib import messages
from django.db.models import Case, When
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from calendars.models import CalendarFlag
from staff.authorization import user_is_manager


def open_flags():
    return (
        CalendarFlag.objects.filter(outcome=CalendarFlag.Outcome.OPEN)
        .select_related("appointment__customer", "appointment__vehicle")
        # Clashes first: they need a decision about a customer's job.
        .order_by(Case(When(kind=CalendarFlag.Kind.CLASH, then=0), default=1), "starts_at", "created_at")
    )


@require_POST
def calendar_flag(request, pk):
    """Keep a job Time Off covers (managers), or mark a put-back event seen."""
    flag = get_object_or_404(CalendarFlag, pk=pk, outcome=CalendarFlag.Outcome.OPEN)
    action = request.POST.get("action")
    if flag.kind == CalendarFlag.Kind.CLASH and action == "keep":
        if not user_is_manager(request.user):
            messages.error(request, "Only a manager can keep a job that Time Off covers.")
            return redirect("schedule")
        flag.outcome = CalendarFlag.Outcome.KEPT
        messages.success(request, "Kept. The job stays booked.")
    elif flag.kind == CalendarFlag.Kind.RESET and action == "seen":
        flag.outcome = CalendarFlag.Outcome.SEEN
    else:
        return redirect("schedule")
    flag.closed_at, flag.closed_by = timezone.now(), request.user
    flag.save(update_fields=["outcome", "closed_at", "closed_by"])
    return redirect(request.POST.get("next") or "schedule")
