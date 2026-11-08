"""The review queue for quiet matching (returning-customers.md): each
difference between a website booking and the customer record it matched,
both versions side by side, with the four actions. Every choice is logged
on the flag, with who and when (customers.matching.resolve)."""

from django.contrib import messages
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_safe

from appointments.models import Appointment, MatchFlag
from customers import matching


@require_safe
def match_reviews(request):
    """Every job with a difference still open, newest first."""
    jobs = (
        Appointment.objects.annotate(open_flags=Count("match_flags", filter=Q(match_flags__resolution="")), flagged_at=Max("match_flags__created_at"))
        .filter(open_flags__gt=0).select_related("customer", "vehicle").order_by("-flagged_at")
    )
    return render(request, "control/match_reviews.html", {"jobs": jobs})


def flag_rows(appointment):
    rows = []
    for flag in appointment.match_flags.select_related("booked_address", "booked_vehicle", "resolved_by").order_by("created_at", "id"):
        rows.append({
            "flag": flag,
            "record": [str(item) for item in matching.choices_of(flag)] if flag.record_choices else flag.record_value.splitlines(),
            "choices": matching.choices_of(flag) if flag.field == MatchFlag.Field.VEHICLE else [],
            "actions": matching.actions_for(flag),
        })
    return rows


@require_safe
def match_review(request, pk):
    appointment = get_object_or_404(Appointment.objects.select_related("customer", "vehicle", "service_address"), pk=pk)
    return render(request, "control/match_review.html", {
        "appointment": appointment,
        "rows": flag_rows(appointment),
        "intake": appointment.intake or {},
    })


@require_POST
def match_resolve(request, pk):
    flag = get_object_or_404(MatchFlag.objects.select_related("appointment", "customer"), pk=pk)
    resolution = request.POST.get("resolution", "")
    try:
        result = matching.resolve(flag, resolution, request.user, choice=request.POST.get("choice"))
    except matching.ResolveError as error:
        messages.error(request, str(error))
    else:
        if resolution == MatchFlag.Resolution.MOVE_TO_NEW_CUSTOMER:
            messages.success(request, f"Moved the booking to a new customer, {result}.")
        else:
            messages.success(request, f"{flag.get_field_display()}: {flag.resolution_note}.")
    return redirect("match-review", pk=flag.appointment_id)
