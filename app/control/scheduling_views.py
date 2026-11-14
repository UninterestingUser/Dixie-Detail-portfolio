"""The scheduling settings screen, date exceptions, the booked jobs a change
leaves outside the rules, and the open-times view (decision 0056).

Only a manager changes the scheduling settings. Every signed-in user can see
them and the open-times view, which the owner uses to test the rules.
"""

import datetime

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from appointments import booking
from geo.models import LocationSettings
from pricebook.pricing import PricingError
from scheduling import availability, changes
from scheduling.models import WEEKDAYS, AffectedJob, DateException, OpenWeekday, SchedulingSettings, SettingsChange, SharedService
from staff.authorization import user_is_manager

from .location_views import require_manager
from .scheduling_forms import (
    DateExceptionForm, OpenTimesForm, SchedulingSettingsForm, SharedServiceForm, WeekdayForm, sharing_candidates,
)

OPEN_TIMES_DAYS = 90


def weekday_forms(data=None):
    rows = {row.weekday: row for row in OpenWeekday.objects.all()}
    forms = []
    for number, name in enumerate(WEEKDAYS):
        row = rows.get(number)
        initial = {"is_open": row.is_open, "opens_at": row.opens_at, "closes_at": row.closes_at, "start_times": row.start_times} if row else {}
        forms.append((number, name, WeekdayForm(data, prefix=f"day{number}", initial=initial)))
    return forms


def sharing_forms(data=None):
    shared = {row.service_id: row for row in SharedService.objects.all()}
    forms = []
    for service in sharing_candidates():
        row = shared.get(service.pk)
        initial = {"shares": row is not None, "max_per_day": row.max_per_day if row else None}
        forms.append((service, SharedServiceForm(data, prefix=f"share{service.pk}", initial=initial)))
    return forms


def after_change(request, before, summary):
    """List the booked jobs the change left outside the rules, if any."""
    change = changes.record(before, summary, request.user)
    if change is None:
        messages.success(request, f"{summary}. No booked job is outside the new rules.")
        return redirect("scheduling-settings")
    count = change.affected_jobs.count()
    jobs = "1 booked job now falls" if count == 1 else f"{count} booked jobs now fall"
    messages.warning(request, f"{summary}. {jobs} outside the rules: keep or reschedule each.")
    return redirect("scheduling-change", pk=change.pk)


def scheduling_settings(request):
    settings = SchedulingSettings.get()
    can_edit = user_is_manager(request.user)
    data = request.POST if request.method == "POST" else None
    if data is not None:
        require_manager(request, "change the scheduling settings")
    form = SchedulingSettingsForm(data, instance=settings)
    days, sharing = weekday_forms(data), sharing_forms(data)
    if data is not None and form.is_valid() and all(f.is_valid() for _, _, f in days) and all(f.is_valid() for _, f in sharing):
        before = changes.snapshot()
        with transaction.atomic():
            settings = form.save(commit=False)
            settings._change_reason = "Changed in the control app"
            settings.save()
            for number, _, day_form in days:
                values = day_form.cleaned_data
                row, _ = OpenWeekday.objects.get_or_create(weekday=number)
                new = (values["is_open"], values["opens_at"] if values["is_open"] else None,
                       values["closes_at"] if values["is_open"] else None, values["start_times"] if values["is_open"] else [])
                if new != (row.is_open, row.opens_at, row.closes_at, row.start_times):
                    row.is_open, row.opens_at, row.closes_at, row.start_times = new
                    row._change_reason = "Changed in the control app"
                    row.save()
            for service, share_form in sharing:
                values = share_form.cleaned_data
                row = SharedService.objects.filter(service=service).first()
                if values["shares"] and row is None:
                    SharedService.objects.create(service=service, max_per_day=values["max_per_day"])
                elif values["shares"] and row.max_per_day != values["max_per_day"]:
                    row.max_per_day = values["max_per_day"]
                    row.save()
                elif not values["shares"] and row is not None:
                    row.delete()
        return after_change(request, before, "Saved the scheduling settings")
    context = {
        "form": form,
        "days": days,
        "sharing": sharing,
        "can_edit": can_edit,
        "exceptions": DateException.objects.filter(date__gte=timezone.localdate()),
        "exception_form": DateExceptionForm(),
        "home": LocationSettings.get().home is not None,
        "waiting": changes.waiting().count(),
        "history": settings.history.order_by("-history_date")[:5],
    }
    return render(request, "control/scheduling_settings.html", context)


@require_POST
def date_exception_add(request):
    require_manager(request, "change the scheduling settings")
    try:
        day = datetime.date.fromisoformat(request.POST.get("date", ""))
    except ValueError:
        day = None
    # A date that already has an exception gets the new one in its place.
    form = DateExceptionForm(request.POST, instance=DateException.objects.filter(date=day).first() if day else None)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{form.fields[field].label if field in form.fields else 'Date exception'}: {error}")
        return redirect("scheduling-settings")
    before = changes.snapshot()
    exception = form.save(commit=False)
    exception._change_reason = "Set in the control app"
    exception.save()
    return after_change(request, before, f"{exception.date:%a %b %-d, %Y} is {exception.get_kind_display().lower()}")


@require_POST
def date_exception_delete(request, pk):
    require_manager(request, "change the scheduling settings")
    exception = get_object_or_404(DateException, pk=pk)
    before = changes.snapshot()
    when = f"{exception.date:%a %b %-d, %Y}"
    exception.delete()
    return after_change(request, before, f"Removed the exception on {when}")


def scheduling_change(request, pk):
    """The booked jobs a settings change left outside the rules, to keep or
    reschedule. Rescheduling is done on the job's own screen."""
    change = get_object_or_404(SettingsChange, pk=pk)
    jobs = change.affected_jobs.select_related("appointment__customer", "appointment__vehicle", "decided_by")
    if request.method == "POST":
        require_manager(request, "decide the jobs a settings change affects")
        for affected in jobs.filter(choice=""):
            if request.POST.get(f"keep-{affected.pk}") == "on" or request.POST.get("all") == "keep":
                changes.decide(affected, AffectedJob.Choice.KEEP, request.user)
        messages.success(request, "Saved.")
        return redirect("scheduling-change", pk=pk)
    context = {"change": change, "jobs": jobs, "can_edit": user_is_manager(request.user)}
    return render(request, "control/scheduling_change.html", context)


@require_safe
def scheduling_waiting(request):
    """Every booked job still waiting for a keep-or-reschedule choice."""
    context = {"jobs": changes.waiting().select_related("appointment__customer", "change"), "can_edit": user_is_manager(request.user)}
    return render(request, "control/scheduling_waiting.html", context)


@require_safe
def open_times(request):
    """The next 90 days of start times for a job, open or with the reasons
    it is closed, to test the rules."""
    form = OpenTimesForm(request.GET or None)
    context = {"form": form, "days": None}
    if form.is_bound and form.is_valid():
        data = form.cleaned_data
        first = data.get("first") or timezone.localdate()
        last = first + datetime.timedelta(days=OPEN_TIMES_DAYS - 1)
        service = data["service"]
        # The engine drops a level the service doesn't take (decision 0103).
        inputs = booking.JobInputs(service, data["vehicle_class"], data.get("size_variant"), data.get("condition_level"),
                                   crew_size=data.get("crew_size") or service.default_crew_size)
        try:
            job = booking.job_to_place(inputs, first)
        except PricingError as error:
            form.add_error(None, str(error))
        else:
            job = availability.Job(job.minutes, job.service_id, job.service_name, data.get("location"))
            context.update(days=availability.open_times(job, first, last), job=job, first=first, last=last)
    return render(request, "control/open_times.html", context)
