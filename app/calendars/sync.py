"""The Google Calendar sync (decisions 0057 and 0098).

- The queue. Saving an appointment, its lines or a closed date adds its link
  to SyncTask in the same database transaction (calendars.signals), so a
  booking never waits for Google and no change is lost. The worker
  (manage.py calendar_worker) pushes each due link within seconds, and
  tries again later, with a growing wait, while Google is down. A link
  changed again while it was being pushed is pushed again.
- The Jobs check. Every Time Off check, and in full every night
  (manage.py sync_calendars), the worker compares the Jobs calendar from
  today on with what the database says it should hold: an event edited or
  deleted in Google is put back and noted, a leftover app event is
  deleted, and an event added by hand is copied as busy time and flagged.
- The Time Off copy. Every few minutes (the Time Off check setting), and
  again when a booking is sent, the worker copies the Time Off calendar
  into TimeOffEvent, which the availability check reads, then flags each
  booked job that Time Off now covers.

The Jobs calendar and the Time Off calendar never change an appointment.
"""

import datetime
import logging
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field

from django.db import connection, transaction
from django.utils import timezone

from appointments.models import Appointment
from scheduling.availability import local_midnight
from scheduling.models import SchedulingSettings, TimeOffEvent

from . import events, google
from .models import CalendarEvent, CalendarFlag, SyncState, SyncTask

log = logging.getLogger(__name__)

# How long a worker holds a claimed task before another may take it.
CLAIM = datetime.timedelta(minutes=2)
# The wait before trying a failed push again: 30 seconds, doubling, at most 15 minutes.
FIRST_WAIT, LONGEST_WAIT = 30, 15 * 60
# How far ahead the Time Off copy reaches: past the furthest bookable date,
# for jobs a manager booked further out.
TIME_OFF_DAYS_AHEAD = 400
# A Time Off copy younger than this is fresh enough for a booking being sent.
FRESH_FOR_BOOKING = datetime.timedelta(minutes=1)
# Seconds a booking being sent waits for Google's Time Off before using the last copy.
BOOKING_TIMEOUT = 5
# Any number unique to this lock, shared by the worker and sync_calendars.
LOCK_ID = 7_202_611


def today():
    return timezone.localdate()


@contextmanager
def calendar_lock():
    """One writer to the Jobs calendar at a time: the worker, or the nightly
    full check, never both, so neither mistakes the other's change for an
    edit made in Google."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", [LOCK_ID])
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", [LOCK_ID])


# The queue ---------------------------------------------------------------------


def enqueue(link, now=None):
    """Push link soon. A link already waiting is pushed again from scratch,
    with its version raised so a push of the older state does not clear it."""
    now = now or timezone.now()
    with connection.cursor() as cursor:
        cursor.execute(
            f"""INSERT INTO {SyncTask._meta.db_table} (link, version, due_at, attempts, last_error, created_at)
                VALUES (%s, 1, %s, 0, '', %s)
                ON CONFLICT (link) DO UPDATE SET version = {SyncTask._meta.db_table}.version + 1,
                    due_at = EXCLUDED.due_at, attempts = 0, last_error = ''""",
            [link, now, now],
        )


def claim(now, limit=25):
    """Take up to limit due tasks, skipping any another worker holds."""
    table = SyncTask._meta.db_table
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            f"""UPDATE {table} SET claimed_until = %s
                WHERE id IN (SELECT id FROM {table}
                             WHERE due_at <= %s AND (claimed_until IS NULL OR claimed_until < %s)
                             ORDER BY due_at LIMIT %s FOR UPDATE SKIP LOCKED)
                RETURNING id, link, version, attempts""",
            [now + CLAIM, now, now, limit],
        )
        return cursor.fetchall()


def wait_after(attempts):
    return datetime.timedelta(seconds=min(FIRST_WAIT * 2 ** max(attempts - 1, 0), LONGEST_WAIT))


@dataclass
class Report:
    created: int = 0
    updated: int = 0
    deleted: int = 0
    restored: int = 0
    by_hand: int = 0
    checked: int = 0
    pushed: int = 0
    failed: int = 0
    clashes: int = 0
    errors: list = field(default_factory=list)

    def line(self):
        return (f"{self.checked} events checked, {self.created} created, {self.updated} updated, "
                f"{self.restored} put back after an edit in Google, {self.deleted} deleted, "
                f"{self.by_hand} added by hand, {self.clashes} Time Off clashes open")


def process_queue(now=None, report=None):
    """Push every due task. Stops quietly when the calendars are not connected."""
    report = report or Report()
    if not google.connected():
        return report
    now = now or timezone.now()
    api = google.client()
    for task_id, link, version, attempts in claim(now):
        try:
            push_link(api, link, report)
        except google.CalendarError as error:
            report.failed += 1
            report.errors.append(f"{link}: {error}")
            log.warning("Calendar push of %s failed: %s", link, error)
            SyncTask.objects.filter(pk=task_id, version=version).update(
                attempts=attempts + 1, last_error=str(error)[:500], due_at=now + wait_after(attempts + 1), claimed_until=None,
            )
            SyncTask.objects.filter(pk=task_id).update(claimed_until=None)
        else:
            report.pushed += 1
            # Done, unless the link changed again while it was pushed.
            if not SyncTask.objects.filter(pk=task_id, version=version).delete()[0]:
                SyncTask.objects.filter(pk=task_id).update(claimed_until=None)
    return report


# Writing events ------------------------------------------------------------


def put_event(api, calendar_id, event_id, body):
    """Make the event exactly body: update it, which also brings back an
    event deleted in Google, or create it when Google has never had it."""
    try:
        return api.update_event(calendar_id, event_id, body)
    except google.NotFound:
        try:
            return api.insert_event(calendar_id, event_id, body)
        except google.Conflict:
            return api.update_event(calendar_id, event_id, body)


def record(event_id, kind, link, body, now):
    CalendarEvent.objects.update_or_create(
        event_id=event_id, defaults={"kind": kind, "link": link, "fingerprint": events.fingerprint(body), "synced_at": now},
    )
    if kind == "job":
        key = link.partition(":")[2]
        Appointment.objects.filter(calendar_key=key).exclude(jobs_calendar_event_id=event_id).update(jobs_calendar_event_id=event_id)


def delete_event(api, calendar_id, event_id):
    try:
        api.delete_event(calendar_id, event_id)
    except google.NotFound:
        pass
    CalendarEvent.objects.filter(event_id=event_id).delete()


def push_link(api, link, report=None):
    """Make the Jobs calendar match the database for one link: write each
    event it should have, and delete the ones it no longer should."""
    report = report or Report()
    now = timezone.now()
    calendar_id = google.jobs_calendar()
    wanted = events.for_link(link)
    known = set(CalendarEvent.objects.filter(link=link).values_list("event_id", flat=True))
    for event_id, (kind, body) in wanted.items():
        put_event(api, calendar_id, event_id, body)
        record(event_id, kind, link, body, now)
        if event_id in known:
            report.updated += 1
        else:
            report.created += 1
    for event_id in known - set(wanted):
        delete_event(api, calendar_id, event_id)
        report.deleted += 1
    if link.startswith("job:") and not any(kind == "job" for kind, _ in wanted.values()):
        Appointment.objects.filter(calendar_key=link.partition(":")[2]).exclude(jobs_calendar_event_id="").update(jobs_calendar_event_id="")
    return report


# The Jobs check ---------------------------------------------------------------


def busy_copy(event, calendar):
    """A TimeOffEvent's fields for a Google event, or None for an event with
    no start (Google leaves those out, but be safe)."""
    start, end = event.get("start") or {}, event.get("end") or {}
    fields = {"summary": (event.get("summary") or "")[:300], "copied_at": timezone.now(), "calendar": calendar}
    if "date" in start:
        first = datetime.date.fromisoformat(start["date"])
        last = datetime.date.fromisoformat(end["date"]) - datetime.timedelta(days=1) if "date" in end else first
        return {**fields, "all_day": True, "first_date": first, "last_date": max(first, last), "starts_at": None, "ends_at": None}
    if "dateTime" in start:
        starts = datetime.datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
        ends = datetime.datetime.fromisoformat(end["dateTime"].replace("Z", "+00:00")) if "dateTime" in end else starts
        return {**fields, "all_day": False, "first_date": timezone.localtime(starts).date(),
                "last_date": timezone.localtime(ends).date(), "starts_at": starts, "ends_at": ends}
    return None


def replace_copy(calendar, found):
    """Make TimeOffEvent hold exactly found ({event ID: fields}) for calendar."""
    with transaction.atomic():
        TimeOffEvent.objects.filter(calendar=calendar).exclude(event_id__in=list(found)).delete()
        for event_id, fields in found.items():
            TimeOffEvent.objects.update_or_create(calendar=calendar, event_id=event_id, defaults=fields)


def flag_reset(event_id, kind, link, body, what):
    appointment = None
    if link.startswith("job:"):
        appointment = Appointment.objects.filter(calendar_key=link.partition(":")[2]).first()
    detail = "Deleted in Google" if what is None else f"Changed in Google ({', '.join(what)})"
    start = events.moment_of(body.get("start"))
    CalendarFlag.objects.create(
        kind=CalendarFlag.Kind.RESET, appointment=appointment, event_id=event_id, summary=body["summary"][:300],
        detail=f"{detail}; put back as the app has it.",
        starts_at=datetime.datetime.fromisoformat(start) if "T" in start else None,
    )


def check_jobs(api, report=None, now=None):
    """Compare the Jobs calendar from today on with the database and repair
    every difference (decision 0057, Jobs calendar rules 3 to 6)."""
    report = report or Report()
    now = now or timezone.now()
    calendar_id = google.jobs_calendar()
    first = today()
    in_google = {event["id"]: event for event in api.list_events(calendar_id, local_midnight(first), show_deleted=True)}
    wanted = events.everything(first)
    known = {row.event_id: row for row in CalendarEvent.objects.filter(event_id__in=list(wanted) + list(in_google))}

    for event_id, (kind, link, body) in wanted.items():
        report.checked += 1
        event = in_google.get(event_id)
        row = known.get(event_id)
        if event is None or event.get("status") == "cancelled":
            put_event(api, calendar_id, event_id, body)
            if row is not None:
                # The app wrote it before, so it was deleted in Google.
                flag_reset(event_id, kind, link, body, None)
                report.restored += 1
            else:
                report.created += 1
            record(event_id, kind, link, body, now)
        elif events.fingerprint(event) != events.fingerprint(body):
            edited = row is not None and row.fingerprint != events.fingerprint(event)
            put_event(api, calendar_id, event_id, body)
            if edited:
                flag_reset(event_id, kind, link, body, events.differences(event, body))
                report.restored += 1
            else:
                report.updated += 1
            record(event_id, kind, link, body, now)
        elif row is None or row.fingerprint != events.fingerprint(body):
            record(event_id, kind, link, body, now)

    by_hand = {}
    for event_id, event in in_google.items():
        if event_id in wanted or event.get("status") == "cancelled":
            continue
        if events.is_ours(event):
            # An app event for a job no longer on the calendar, such as a
            # cancellation whose push has not gone through yet.
            delete_event(api, calendar_id, event_id)
            report.deleted += 1
        else:
            copy = busy_copy(event, TimeOffEvent.Calendar.JOBS)
            if copy is not None:
                by_hand[event_id] = (event, copy)
    replace_copy(TimeOffEvent.Calendar.JOBS, {event_id: copy for event_id, (_, copy) in by_hand.items()})
    flag_by_hand(by_hand)
    report.by_hand = len(by_hand)
    SyncState.objects.filter(pk=SyncState.get().pk).update(jobs_checked_at=now, jobs_error="")
    return report


def flag_by_hand(by_hand):
    """One open flag per event added to Jobs by hand; a flag whose event is
    gone, moved to Time Off or deleted, closes itself."""
    open_flags = CalendarFlag.objects.filter(kind=CalendarFlag.Kind.BY_HAND, outcome=CalendarFlag.Outcome.OPEN)
    open_flags.exclude(event_id__in=list(by_hand)).update(outcome=CalendarFlag.Outcome.CLEARED, closed_at=timezone.now())
    flagged = set(open_flags.values_list("event_id", flat=True))
    for event_id, (event, copy) in by_hand.items():
        if event_id not in flagged:
            CalendarFlag.objects.create(
                kind=CalendarFlag.Kind.BY_HAND, event_id=event_id, summary=(event.get("summary") or "(no title)")[:300],
                starts_at=copy["starts_at"] or local_midnight(copy["first_date"]),
                detail="Counted as busy time. Move it to the Time Off calendar, or delete it.",
            )


# The Time Off copy ------------------------------------------------------------


def copy_time_off(api, now=None):
    """Copy every Time Off event, repeating ones visit by visit, into
    TimeOffEvent. Free/Busy is ignored: every event blocks time."""
    now = now or timezone.now()
    first = today() - datetime.timedelta(days=1)
    found = {}
    for event in api.list_events(google.time_off_calendar(), local_midnight(first),
                                 local_midnight(first + datetime.timedelta(days=TIME_OFF_DAYS_AHEAD))):
        if event.get("status") == "cancelled":
            continue
        copy = busy_copy(event, TimeOffEvent.Calendar.TIME_OFF)
        if copy is not None:
            found[event["id"]] = copy
    replace_copy(TimeOffEvent.Calendar.TIME_OFF, found)
    SyncState.objects.filter(pk=SyncState.get().pk).update(time_off_copied_at=now, time_off_error="", time_off_error_at=None)
    return len(found)


def note_time_off_error(error, now=None):
    SyncState.objects.filter(pk=SyncState.get().pk).update(time_off_error=str(error)[:500], time_off_error_at=now or timezone.now())


def covers(event, appointment, buffer):
    """Whether a Time Off event lands on the appointment's time on site."""
    start = appointment.scheduled_start
    end = appointment.ends_at or start + events.UNKNOWN_LENGTH
    if event.all_day:
        first, last = timezone.localtime(start).date(), timezone.localtime(end - datetime.timedelta(microseconds=1)).date()
        return event.first_date <= last and first <= event.last_date
    return start < event.ends_at + buffer and event.starts_at - buffer < end


def find_clashes(now=None):
    """Flag each booked job from today on that a Time Off event covers,
    once per job and event. Nothing is moved or canceled (decision 0057):
    the owner keeps, reschedules or cancels it. A flag whose clash has gone,
    because the job or the event moved, closes itself."""
    now = now or timezone.now()
    buffer = datetime.timedelta(minutes=SchedulingSettings.get().time_off_buffer_minutes)
    time_off = list(TimeOffEvent.objects.filter(calendar=TimeOffEvent.Calendar.TIME_OFF))
    found = {}
    if time_off:
        jobs = Appointment.objects.filter(status=Appointment.Status.BOOKED, scheduled_start__gte=local_midnight(today()))
        for appointment in jobs.select_related("customer"):
            for event in time_off:
                if covers(event, appointment, buffer):
                    found[(appointment.pk, event.event_id)] = (appointment, event)
    flags = CalendarFlag.objects.filter(kind=CalendarFlag.Kind.CLASH)
    for flag in flags.filter(outcome=CalendarFlag.Outcome.OPEN):
        if (flag.appointment_id, flag.event_id) not in found:
            flag.outcome, flag.closed_at = CalendarFlag.Outcome.CLEARED, now
            flag.save(update_fields=["outcome", "closed_at"])
    # A clash the owner kept stays kept; one that cleared and came back is flagged again.
    settled = set(flags.filter(outcome__in=[CalendarFlag.Outcome.OPEN, CalendarFlag.Outcome.KEPT]).values_list("appointment_id", "event_id"))
    for key, (appointment, event) in found.items():
        if key not in settled:
            CalendarFlag.objects.create(
                kind=CalendarFlag.Kind.CLASH, appointment=appointment, event_id=event.event_id,
                summary=(event.summary or "Time off")[:300], starts_at=appointment.scheduled_start,
                detail="Time Off covers this booked job. Keep it, reschedule it or cancel it.",
            )
    return CalendarFlag.objects.filter(kind=CalendarFlag.Kind.CLASH, outcome=CalendarFlag.Outcome.OPEN).count()


def refresh_time_off(now=None, timeout=None):
    """Copy Time Off and flag clashes. Returns False, with the error noted,
    when Google could not be asked; the last copy is kept."""
    now = now or timezone.now()
    try:
        api = google.client()
        with google.short_timeout(api, timeout) if timeout else nullcontext():
            copy_time_off(api, now)
    except google.NotConnected:
        return False
    except google.CalendarError as error:
        note_time_off_error(error, now)
        log.warning("Time Off copy failed: %s", error)
        return False
    find_clashes(now)
    return True


def refresh_time_off_for_booking():
    """Called as a booking is sent: copy Time Off again unless the copy is
    under a minute old. Google being down never stops the booking; the
    check then uses the last copy."""
    if not google.connected():
        return False
    copied = SyncState.get().time_off_copied_at
    if copied and timezone.now() - copied < FRESH_FOR_BOOKING:
        return True
    return refresh_time_off(timeout=BOOKING_TIMEOUT)


# Rounds --------------------------------------------------------------------


def check_round(now=None):
    """The worker's regular round, every Time Off check: copy Time Off, flag
    clashes, and check the Jobs calendar."""
    now = now or timezone.now()
    report = Report()
    if not google.connected():
        return report
    refresh_time_off(now)
    try:
        with calendar_lock():
            check_jobs(google.client(), report, now)
    except google.CalendarError as error:
        SyncState.objects.filter(pk=SyncState.get().pk).update(jobs_error=str(error)[:500])
        report.errors.append(str(error))
    report.clashes = CalendarFlag.objects.filter(kind=CalendarFlag.Kind.CLASH, outcome=CalendarFlag.Outcome.OPEN).count()
    return report


def full_check(now=None):
    """The nightly full check and the first run (manage.py sync_calendars):
    push the queue, copy Time Off, compare every future appointment with the
    Jobs calendar and repair any difference. Raises CalendarError when
    Google could not be asked, so the run is reported as failed."""
    now = now or timezone.now()
    api = google.client()
    report = Report()
    with calendar_lock():
        process_queue(now, report)
        copy_time_off(api, now)
        find_clashes(now)
        check_jobs(api, report, now)
    SyncState.objects.filter(pk=SyncState.get().pk).update(full_check_at=now)
    report.clashes = CalendarFlag.objects.filter(kind=CalendarFlag.Kind.CLASH, outcome=CalendarFlag.Outcome.OPEN).count()
    return report


# The control app's warning ---------------------------------------------------


def time_off_warning(now=None):
    """The warning the control app shows when the Time Off copy is too old to
    trust, or None."""
    now = now or timezone.now()
    if not google.connected():
        return "The Google calendars are not connected, so Time Off is not being copied and jobs are not on the Jobs calendar."
    state = SyncState.get()
    limit = datetime.timedelta(minutes=SchedulingSettings.get().stale_copy_warning_minutes)
    if state.time_off_copied_at is None:
        return "The Time Off calendar has not been copied yet, so days off in Google don't block bookings."
    age = now - state.time_off_copied_at
    if age > limit:
        minutes = int(age.total_seconds() // 60)
        when = f"{minutes // 60} hour{'s' if minutes // 60 != 1 else ''}" if minutes >= 120 else f"{minutes} minutes"
        why = f" Last error: {state.time_off_error}." if state.time_off_error else ""
        return (f"The Time Off calendar was last copied {when} ago. Time off added in Google since then "
                f"doesn't block bookings yet.{why}")
    return None
