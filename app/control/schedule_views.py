"""The Schedule screen's views, like the Google Calendar app (decision 0096):
Schedule, a list of the days with jobs that loads more as it scrolls; Day,
3 Days and Week, with hour rows and a column a day; and Month, a grid.

Weeks start on Sunday. Canceled jobs are on none of them. The last view
used is remembered on each device in a cookie; with none, the screen opens
in Schedule.
"""

import calendar
import datetime
from dataclasses import dataclass, field

from django.db.models import Prefetch
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_safe

from appointments.models import Appointment
from scheduling.availability import day_reasons, load_rules, local_midnight
from scheduling.models import OpenWeekday
from staff.models import Assignment
from vehicles.models import ModelYearClassification, VehicleDataRefresh

VIEWS = {"schedule": "Schedule", "day": "Day", "3day": "3 Days", "week": "Week", "month": "Month"}
COOKIE = "schedule_view"
COOKIE_AGE = 400 * 24 * 60 * 60
# Days with jobs the Schedule list loads at a time, each way.
CHUNK = 14
# Jobs a month box shows before "+N more".
MONTH_BOX = 3
# The working day when no day in view is open.
DEFAULT_HOURS = (8, 17)
DAY = datetime.timedelta(days=1)


def parse_date(text):
    try:
        return datetime.date.fromisoformat(text)
    except (TypeError, ValueError):
        return timezone.localdate()


def week_start(day):
    """The Sunday on or before day."""
    return day - datetime.timedelta(days=(day.weekday() + 1) % 7)


def add_months(day, months):
    index = day.month - 1 + months
    return datetime.date(day.year + index // 12, index % 12 + 1, 1)


def jobs(first, last):
    """The jobs from first to last, inclusive, by start, without canceled jobs."""
    return (
        Appointment.objects.filter(scheduled_start__gte=local_midnight(first), scheduled_start__lt=local_midnight(last + DAY))
        .exclude(status=Appointment.Status.CANCELED)
        .select_related("customer", "vehicle", "service_address")
        .prefetch_related("lines", Prefetch("assignments", queryset=Assignment.objects.select_related("staff_member")))
        .order_by("scheduled_start")
    )


def by_day(first, last):
    found = {}
    for appointment in jobs(first, last):
        found.setdefault(timezone.localtime(appointment.scheduled_start).date(), []).append(appointment)
    return found


def closed_days(first, last):
    """{date: [reason text]} for the closed days from first to last: a
    closed weekday, a closed date or Time Off all day."""
    rules = load_rules(first, last)
    today = timezone.localdate()
    found, day = {}, first
    while day <= last:
        _, reasons = day_reasons(rules, day, today, window=False)
        if reasons:
            found[day] = [reason.text for reason in reasons]
        day += DAY
    return found


# The Schedule list ------------------------------------------------------------


def job_dates(**lookups):
    """The Eastern dates that have jobs, by the given scheduled_start lookups."""
    return (
        Appointment.objects.filter(**lookups).exclude(status=Appointment.Status.CANCELED)
        .annotate(day=TruncDate("scheduled_start")).values_list("day", flat=True).distinct()
    )


def groups(first, last):
    """[(date, jobs)] for the days with jobs from first to last, with today
    even when it has none."""
    found = by_day(first, last)
    today = timezone.localdate()
    if first <= today <= last:
        found.setdefault(today, [])
    return sorted(found.items())


def later_chunk(day):
    """The days from day on, up to CHUNK days with jobs, and the date to load
    from next, or None when no later job is booked."""
    dates = list(job_dates(scheduled_start__gte=local_midnight(day)).order_by("day")[:CHUNK])
    today = timezone.localdate()
    if len(dates) == CHUNK:
        return groups(day, dates[-1]), dates[-1] + DAY
    last = max(dates + ([today] if today >= day else []), default=None)
    return (groups(day, last) if last else []), None


def earlier_chunk(day):
    """The days before day, back to CHUNK days with jobs, and the date to
    load before next, or None when no earlier job is booked."""
    dates = list(job_dates(scheduled_start__lt=local_midnight(day)).order_by("-day")[:CHUNK])
    today = timezone.localdate()
    if len(dates) == CHUNK:
        return groups(dates[-1], day - DAY), dates[-1]
    first = min(dates + ([today] if today < day else []), default=None)
    return (groups(first, day - DAY) if first else []), None


@require_safe
def schedule_more(request):
    """More of the Schedule list as it scrolls (htmx): later days after=,
    or earlier days before=."""
    if "before" in request.GET:
        days, before = earlier_chunk(parse_date(request.GET["before"]))
        context = {"days": days, "before": before, "earlier": True}
    else:
        days, after = later_chunk(parse_date(request.GET.get("after")))
        context = {"days": days, "after": after}
    context["today"] = timezone.localdate()
    return render(request, "control/_schedule_days.html", context)


# Day, 3 Days and Week ------------------------------------------------------


@dataclass
class Block:
    appointment: Appointment
    start: int  # minutes since midnight, Eastern
    end: int
    lane: int = 0
    lanes: int = 1
    style: str = ""


@dataclass
class Column:
    day: datetime.date
    closed: list
    blocks: list = field(default_factory=list)
    now: str = ""


def minutes_of(moment):
    local = timezone.localtime(moment)
    return local.hour * 60 + local.minute


def place(appointment, day):
    start = minutes_of(appointment.scheduled_start)
    ends_at = appointment.ends_at
    if ends_at is None:
        end = start + 60
    elif timezone.localtime(ends_at).date() > day:
        end = 24 * 60
    else:
        end = max(minutes_of(ends_at), start + 15)
    return Block(appointment, start, end)


def set_lanes(blocks):
    """Side by side where jobs overlap: each cluster of overlapping jobs
    shares the column's width, each job in the first lane free at its start."""
    cluster, cluster_end = [], 0

    def close():
        lanes = max(block.lane for block in cluster) + 1
        for block in cluster:
            block.lanes = lanes

    for block in sorted(blocks, key=lambda b: (b.start, b.end)):
        if cluster and block.start >= cluster_end:
            close()
            cluster = []
        lane_ends = {}
        for other in cluster:
            lane_ends[other.lane] = max(lane_ends.get(other.lane, 0), other.end)
        block.lane = next(lane for lane in range(len(cluster) + 1) if lane_ends.get(lane, 0) <= block.start)
        cluster_end = max(cluster_end if cluster else 0, block.end)
        cluster.append(block)
    if cluster:
        close()


def working_hours(days, closed):
    """(first hour, last hour) of the open days' hours, or the default."""
    weekdays = {row.weekday: row for row in OpenWeekday.objects.filter(is_open=True)}
    open_rows = [weekdays[day.weekday()] for day in days if day.weekday() in weekdays and day not in closed]
    if not open_rows:
        open_rows = list(weekdays.values())
    if not open_rows:
        return DEFAULT_HOURS
    first = min(row.opens_at for row in open_rows)
    last = max(row.closes_at for row in open_rows)
    return first.hour, last.hour + (1 if last.minute else 0)


def time_grid(days):
    """The columns and hour rows for days: the working day, stretched to fit
    any job outside it."""
    found = by_day(days[0], days[-1])
    closed = closed_days(days[0], days[-1])
    columns = []
    for day in days:
        column = Column(day, closed.get(day, []), [place(appointment, day) for appointment in found.get(day, [])])
        set_lanes(column.blocks)
        columns.append(column)
    first_hour, last_hour = working_hours(days, closed)
    blocks = [block for column in columns for block in column.blocks]
    if blocks:
        first_hour = min(first_hour, min(block.start for block in blocks) // 60)
        last_hour = max(last_hour, -(-max(block.end for block in blocks) // 60))
    span = (last_hour - first_hour) * 60
    for column in columns:
        for block in column.blocks:
            top = (block.start - first_hour * 60) / span * 100
            height = (block.end - block.start) / span * 100
            width = 100 / block.lanes
            block.style = f"top:{top:.3f}%;height:{height:.3f}%;left:{block.lane * width:.3f}%;width:{width:.3f}%"
    now = timezone.localtime()
    for column in columns:
        minute = now.hour * 60 + now.minute
        if column.day == now.date() and first_hour * 60 <= minute <= last_hour * 60:
            column.now = f"top:{(minute - first_hour * 60) / span * 100:.3f}%"
    hours = [datetime.time(hour) for hour in range(first_hour, last_hour)]
    return {"columns": columns, "hours": hours, "first_minute": first_hour * 60, "last_minute": last_hour * 60}


# Month -------------------------------------------------------------------------


def month_grid(day):
    first = day.replace(day=1)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    start, end = week_start(first), week_start(last) + 6 * DAY
    found = by_day(start, end)
    closed = closed_days(start, end)
    weeks, cell = [], start
    while cell <= end:
        week = []
        for _ in range(7):
            day_jobs = found.get(cell, [])
            shown = day_jobs if len(day_jobs) <= MONTH_BOX else day_jobs[: MONTH_BOX - 1]
            week.append({
                "day": cell, "in_month": cell.month == first.month, "closed": cell in closed,
                "jobs": shown, "more": len(day_jobs) - len(shown),
            })
            cell += DAY
        weeks.append(week)
    return weeks


# The screen --------------------------------------------------------------------


def chosen_view(request):
    view = request.GET.get("view") or request.COOKIES.get(COOKIE) or "schedule"
    return view if view in VIEWS else "schedule"


def span_title(first, last):
    if first == last:
        return first.strftime("%A, %B %-d, %Y")
    if first.year != last.year:
        return f"{first:%b %-d, %Y} to {last:%b %-d, %Y}"
    if first.month != last.month:
        return f"{first:%b %-d} to {last:%b %-d, %Y}"
    return f"{first:%B %-d} to {last.day}, {last.year}"


@require_safe
def schedule(request):
    view = chosen_view(request)
    day = parse_date(request.GET.get("date"))
    today = timezone.localdate()
    context = {
        "view": view,
        "views": VIEWS,
        "day": day,
        "today": today,
        # The home screen says when model years wait in the review queue (decision 0076).
        "queue_count": ModelYearClassification.objects.filter(in_review=True).count(),
        # And, beside it, how the last monthly vehicle data refresh went (decision 0081).
        "last_refresh": VehicleDataRefresh.objects.first(),
    }
    if view == "schedule":
        days, after = later_chunk(day)
        context.update(days=days, after=after, before=day, title=day.strftime("%B %Y"), step=7)
    elif view == "month":
        first = day.replace(day=1)
        context.update(weeks=month_grid(day), title=first.strftime("%B %Y"),
                       previous=add_months(first, -1), next=add_months(first, 1))
    else:
        count = {"day": 1, "3day": 3, "week": 7}[view]
        first = week_start(day) if view == "week" else day
        days = [first + offset * DAY for offset in range(count)]
        context.update(time_grid(days), title=span_title(days[0], days[-1]), step=count, first=first)
    if "step" in context:
        anchor = context.get("first", day)
        context.update(previous=anchor - context["step"] * DAY, next=anchor + context["step"] * DAY)
    response = render(request, "control/schedule.html", context)
    if "view" in request.GET and request.GET["view"] in VIEWS:
        response.set_cookie(COOKIE, view, max_age=COOKIE_AGE, samesite="Lax", httponly=True, secure=request.is_secure())
    return response
