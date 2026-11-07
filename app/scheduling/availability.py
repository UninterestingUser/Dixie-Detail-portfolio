"""The availability check: one function for every case (decision 0056,
scheduling-and-calendars.md).

A start time is open when all six conditions hold:

1. Open day: an open weekday, not closed by a date exception or an all-day
   Time Off event, between the minimum notice and the furthest bookable date.
2. Start times: the time is in that day's list of start times, or, after a
   job already on the day, it is that job's placed start or later, on the
   rounding step (decision 0094).
3. Time Off: the time on site doesn't overlap a timed Time Off event, plus
   the buffer.
4. Jobs per day: an empty day takes any job. A day with a job takes another
   only when every job on it is a service that can share a day, each within
   its maximum, and the day stays within the jobs-per-day setting or, if
   higher, the largest maximum among its services.
5. Gap between jobs: a later job starts no earlier than the earlier job's
   end (after breakdown) plus the drive between the two addresses, at least
   the minimum gap, rounded up by the rounding setting.
6. Closing time: when the day holds more than one job, the last one ends by
   closing time. A single job may run past closing.

Every rule is in Eastern time: the notice counts from today's date in
Eastern time, so it turns over at midnight Eastern, and start times are
Eastern clock times, so they stay put across the change to and from daylight
saving time. Lengths of time are added in UTC, so a job across the change
lasts exactly its minutes.

The check reads everything it needs for a range of dates in a handful of
queries (load_rules), so 90 days are answered at once.
"""

import datetime
import math
from collections import Counter
from dataclasses import dataclass, field

from django.db.models import Prefetch, Q
from django.utils import timezone

from appointments.models import Appointment, AppointmentLine
from geo import drive
from pricebook.models import PricedLine

from .models import WEEKDAYS, DateException, OpenWeekday, SchedulingSettings, SharedService, TimeOffEvent

UTC = datetime.timezone.utc

RULE_NAMES = {
    "day": "Open day",
    "start_time": "Start times",
    "time_off": "Time Off",
    "capacity": "Jobs per day",
    "gap": "Gap between jobs",
    "closing": "Closing time",
}


def clock(moment):
    """8:00 AM as "8:00 AM", in Eastern time."""
    if isinstance(moment, datetime.datetime):
        moment = timezone.localtime(moment).time()
    return moment.strftime("%-I:%M %p")


def plural(number, word):
    return f"{number} {word}{'' if number == 1 else 's'}"


@dataclass(frozen=True)
class Reason:
    """Why a start time is closed, under one of the six rules."""

    rule: str
    text: str

    def __str__(self):
        return f"{RULE_NAMES[self.rule]}: {self.text}"


@dataclass(frozen=True)
class Job:
    """A job to place: its time on site, its main service and where it is.
    service_id is None for a job with no service from the pricebook, which
    can't share a day; point is None when the address has no location, and
    the gap is then the minimum gap alone."""

    minutes: int
    service_id: int = None
    service_name: str = "A custom job"
    point: tuple = None


@dataclass(frozen=True)
class Booked:
    """A job already on the schedule, as the check sees it."""

    pk: int
    start: datetime.datetime  # UTC
    minutes: int
    service_id: int
    service_name: str
    point: tuple

    @property
    def end(self):
        return self.start + datetime.timedelta(minutes=self.minutes)


@dataclass
class Slot:
    """One start time on one day, open when it has no reasons. placed_after
    is the start of the job it is placed after, for a later job."""

    start: datetime.datetime
    reasons: list
    placed_after: datetime.datetime = None

    @property
    def is_open(self):
        return not self.reasons

    @property
    def local_time(self):
        return timezone.localtime(self.start).time()


@dataclass
class Day:
    date: datetime.date
    # Why the whole day is closed, when it is.
    reasons: list
    slots: list
    jobs: list = field(default_factory=list)
    closes_at: datetime.time = None

    @property
    def open_slots(self):
        return [slot for slot in self.slots if slot.is_open]

    @property
    def closed_slots(self):
        return [slot for slot in self.slots if not slot.is_open]


@dataclass
class Rules:
    """The settings and calendar facts for a range of dates."""

    settings: SchedulingSettings
    weekdays: dict
    shared: dict  # service id -> maximum per day
    exceptions: dict
    all_day_off: list  # (first date, last date, summary)
    timed_off: list  # (start, end, summary), UTC
    booked: dict  # date -> [Booked]
    drives: dict = field(default_factory=dict)

    def jobs_on(self, day, exclude=None):
        return [job for job in self.booked.get(day, []) if job.pk != exclude]

    def drive_minutes(self, origin, destination, departure):
        """The drive in minutes, or None without both points. Remembered for
        the pair and the Eastern hour, as geo.drive caches it."""
        if origin is None or destination is None:
            return None
        key = (origin, destination, timezone.localtime(departure).hour)
        if key not in self.drives:
            self.drives[key] = drive.drive_time(origin, destination, departure)
        return self.drives[key].minutes


def local_midnight(day):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time())).astimezone(UTC)


def at(day, time):
    """The moment a clock time happens on a day in Eastern time, in UTC, or
    None when the clocks skip it (2:30 AM on the day daylight saving time
    starts). A time that happens twice, on the day it ends, is the first."""
    naive = datetime.datetime.combine(day, time)
    moment = timezone.make_aware(naive).astimezone(UTC)
    if timezone.localtime(moment).replace(tzinfo=None) != naive:
        return None
    return moment


def round_up(moment, step):
    """Round up to the next step of minutes. Steps divide the hour, and
    Eastern time is a whole number of hours from UTC, so this is the same
    quarter hour on the Eastern clock."""
    seconds = step * 60
    stamp = moment.timestamp()
    return datetime.datetime.fromtimestamp(math.ceil(stamp / seconds) * seconds, UTC)


def main_service(appointment):
    """(service id, name) of a booked job's main service, or (None, "A custom job")."""
    if appointment.quote_id and appointment.quote.service_id:
        return appointment.quote.service_id, appointment.quote.service.name
    for line in appointment.lines.all():
        if line.kind == PricedLine.Kind.SERVICE and line.service_id:
            return line.service_id, line.service.name
    return None, "A custom job"


def booked_from(appointment):
    service_id, name = main_service(appointment)
    address = appointment.service_address
    return Booked(
        appointment.pk,
        appointment.scheduled_start.astimezone(UTC),
        appointment.time_on_site_minutes or 0,
        service_id,
        name,
        address.point if address else None,
    )


def job_from(appointment):
    """A booked job as a job to place, to check it against the rules."""
    booked = booked_from(appointment)
    return Job(booked.minutes, booked.service_id, booked.service_name, booked.point)


def load_rules(first, last):
    """Everything the check needs from first to last, inclusive."""
    settings = SchedulingSettings.get()
    start, end = local_midnight(first), local_midnight(last + datetime.timedelta(days=1))
    weekdays = {row.weekday: row for row in OpenWeekday.objects.all()}
    shared = dict(SharedService.objects.values_list("service_id", "max_per_day"))
    exceptions = {row.date: row for row in DateException.objects.filter(date__gte=first, date__lte=last)}
    events = TimeOffEvent.objects.filter(
        Q(all_day=True, first_date__lte=last, last_date__gte=first)
        | Q(all_day=False, starts_at__lt=end + datetime.timedelta(days=1), ends_at__gt=start - datetime.timedelta(days=1))
    )
    all_day_off, timed_off = [], []
    for event in events:
        if event.all_day:
            all_day_off.append((event.first_date, event.last_date, event.summary or "Time off"))
        else:
            timed_off.append((event.starts_at.astimezone(UTC), event.ends_at.astimezone(UTC), event.summary or "Time off"))
    appointments = (
        Appointment.objects.filter(scheduled_start__gte=start, scheduled_start__lt=end)
        .exclude(status=Appointment.Status.CANCELED)
        .select_related("service_address", "quote__service")
        .prefetch_related(Prefetch(
            "lines", queryset=AppointmentLine.objects.filter(kind=PricedLine.Kind.SERVICE).select_related("service")
        ))
        .order_by("scheduled_start")
    )
    booked = {}
    for appointment in appointments:
        booked.setdefault(timezone.localtime(appointment.scheduled_start).date(), []).append(booked_from(appointment))
    return Rules(settings, weekdays, shared, exceptions, all_day_off, timed_off, booked)


@dataclass(frozen=True)
class Hours:
    opens: datetime.time
    closes: datetime.time
    starts: list
    # "on Tuesdays" or "on this date", for the reasons.
    where: str


def hours_on(rules, day):
    """(Hours, None) for an open day, or (None, Reason) when the weekday or
    a date exception closes it."""
    exception = rules.exceptions.get(day)
    weekday = rules.weekdays.get(day.weekday())
    if exception and exception.kind == DateException.Kind.CLOSED:
        return None, Reason("day", f"Closed{': ' + exception.reason if exception.reason else ' on this date'}")
    if exception:
        starts = exception.start_times or [
            time for time in (weekday.start_times if weekday and weekday.is_open else [])
            if exception.opens_at <= time < exception.closes_at
        ]
        return Hours(exception.opens_at, exception.closes_at, sorted(starts), "on this date"), None
    if weekday is None or not weekday.is_open:
        return None, Reason("day", f"{WEEKDAYS[day.weekday()]} is a closed day")
    return Hours(weekday.opens_at, weekday.closes_at, sorted(weekday.start_times), f"on {WEEKDAYS[day.weekday()]}s"), None


def window_reason(rules, day, today):
    earliest = today + datetime.timedelta(days=rules.settings.minimum_notice_days)
    latest = today + datetime.timedelta(days=rules.settings.furthest_bookable_days)
    if day < earliest:
        return Reason("day", f"Too soon: bookings need {plural(rules.settings.minimum_notice_days, 'day')}' notice, "
                             f"so the first date is {earliest:%a %b %-d}")
    if day > latest:
        return Reason("day", f"Too far ahead: bookings go up to {plural(rules.settings.furthest_bookable_days, 'day')} ahead, "
                             f"to {latest:%a %b %-d}")
    return None


def day_reasons(rules, day, today, window=True):
    """Why the whole day is closed: the weekday, a date exception, an all-day
    Time Off event, and, with window, the notice and the furthest date."""
    hours, closed = hours_on(rules, day)
    reasons = [closed] if closed else []
    for first, last, summary in rules.all_day_off:
        if first <= day <= last:
            reasons.append(Reason("day", f"Time Off all day: {summary}"))
    if window:
        reason = window_reason(rules, day, today)
        if reason:
            reasons.append(reason)
    return hours, reasons


def earliest_after(rules, earlier_end, earlier_point, later_point):
    """When a later job can start after an earlier one ends: the drive
    between them, at least the minimum gap, rounded up. Returns (start, text)."""
    minutes = rules.drive_minutes(earlier_point, later_point, earlier_end)
    gap = max(minutes or 0, rules.settings.minimum_gap_minutes)
    start = round_up(earlier_end + datetime.timedelta(minutes=gap), rules.settings.round_start_up_to_minutes)
    if minutes is None:
        how = f"the {rules.settings.minimum_gap_minutes}-minute minimum gap; no drive time without both locations"
    elif minutes < rules.settings.minimum_gap_minutes:
        how = f"a {minutes}-minute drive, so the {rules.settings.minimum_gap_minutes}-minute minimum gap"
    else:
        how = f"a {minutes}-minute drive"
    return start, how


def capacity_reasons(rules, job, others):
    if not others:
        return []
    services = [(other.service_id, other.service_name) for other in others] + [(job.service_id, job.service_name)]
    names = dict(services)
    loners = [name for service_id, name in services if service_id not in rules.shared]
    if loners:
        return [Reason("capacity", f"The day already has {plural(len(others), 'job')}, and {loners[0]} can't share a day")]
    reasons = []
    for service_id, count in Counter(service_id for service_id, _ in services).items():
        if count > rules.shared[service_id]:
            reasons.append(Reason("capacity", f"{names[service_id]} is limited to {rules.shared[service_id]} a day"))
    limit = max(rules.settings.jobs_per_day, *(rules.shared[service_id] for service_id, _ in services))
    if len(services) > limit and not reasons:
        reasons.append(Reason("capacity", f"The day would hold {len(services)} jobs; the most it can hold is {limit}"))
    return reasons


def placed_starts(rules, job, others):
    """For each job already on the day, the earliest a later job can start
    after it: (start, the earlier job)."""
    return [(earliest_after(rules, other.end, other.point, job.point)[0], other) for other in others]


def slot_reasons(rules, job, start, day, hours, others, check_start_time=True):
    """Conditions 2 to 6 for one start time on an open day."""
    reasons = []
    end = start + datetime.timedelta(minutes=job.minutes)
    step = rules.settings.round_start_up_to_minutes

    if check_start_time and hours is not None:
        local = timezone.localtime(start).time()
        before = [other for other in others if other.start <= start]
        after_a_job = before and start == round_up(start, step) and all(
            start >= earliest_after(rules, other.end, other.point, job.point)[0] for other in before
        )
        if local not in hours.starts and not after_a_job:
            reasons.append(Reason("start_time", f"{clock(local)} is not a start time {hours.where}"))

    buffer = datetime.timedelta(minutes=rules.settings.time_off_buffer_minutes)
    for off_start, off_end, summary in rules.timed_off:
        if start < off_end + buffer and off_start - buffer < end:
            reasons.append(Reason("time_off", f"Overlaps {summary}, {clock(off_start)} to {clock(off_end)}"))

    reasons += capacity_reasons(rules, job, others)

    for other in others:
        if other.start <= start:
            earliest, how = earliest_after(rules, other.end, other.point, job.point)
            if start < earliest:
                reasons.append(Reason("gap", f"Too close to the {clock(other.start)} job, which ends at {clock(other.end)}: "
                                             f"the earliest start after it is {clock(earliest)} ({how})"))
        else:
            earliest, how = earliest_after(rules, end, job.point, other.point)
            if other.start < earliest:
                reasons.append(Reason("gap", f"Ends at {clock(end)}, too close to the {clock(other.start)} job, "
                                             f"which would have to start at {clock(earliest)} or later ({how})"))

    if others and hours is not None:
        closing = at(day, hours.closes) or local_midnight(day + datetime.timedelta(days=1))
        last_end = max([end] + [other.end for other in others])
        if last_end > closing:
            reasons.append(Reason("closing", f"With {plural(len(others) + 1, 'job')} the day would run to {clock(last_end)}, "
                                             f"past closing at {clock(hours.closes)}; only a job alone may run past closing"))
    return reasons


def check(job, start, *, rules=None, now=None, exclude=None, window=True):
    """Every rule a job starting at start (aware) would break, as Reasons;
    an empty list means the time is open. exclude is an appointment's pk to
    leave out, for checking a booked job against the rules. window=False
    skips the notice and the furthest date, which a booked job has passed."""
    start = start.astimezone(UTC)
    day = timezone.localtime(start).date()
    rules = rules or load_rules(day, day)
    today = timezone.localdate(now or timezone.now())
    hours, reasons = day_reasons(rules, day, today, window)
    return reasons + slot_reasons(rules, job, start, day, hours, rules.jobs_on(day, exclude), check_start_time=hours is not None)


def open_times(job, first, last, *, rules=None, now=None):
    """For each date from first to last, the start times with the reasons
    each closed one is closed (Day). A day with a job on it also offers the
    placed start after each job, when it falls before closing."""
    rules = rules or load_rules(first, last)
    today = timezone.localdate(now or timezone.now())
    days = []
    for offset in range((last - first).days + 1):
        day = first + datetime.timedelta(days=offset)
        hours, reasons = day_reasons(rules, day, today)
        others = rules.jobs_on(day)
        slots = []
        if hours is not None:
            listed = []
            for time in hours.starts:
                moment = at(day, time)
                if moment is None:
                    slots.append(Slot(local_midnight(day), [Reason("start_time", f"{clock(time)} does not happen on {day:%b %-d}: the clocks go forward")]))
                else:
                    listed.append(moment)
            placed = {}
            closing = at(day, hours.closes)
            for moment, other in placed_starts(rules, job, others):
                if moment not in listed and (closing is None or moment < closing):
                    placed.setdefault(moment, other)
            for moment in sorted(set(listed) | set(placed)):
                slot_rules = reasons or slot_reasons(rules, job, moment, day, hours, others)
                after = placed.get(moment)
                slots.append(Slot(moment, list(slot_rules), after.start if after else None))
        slots.sort(key=lambda slot: slot.start)
        days.append(Day(day, reasons, slots, others, hours.closes if hours else None))
    return days
