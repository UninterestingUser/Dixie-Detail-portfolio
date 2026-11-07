"""Booked jobs a scheduling settings change leaves outside the rules.

A change applies to bookings made after it, and booked jobs never move. So
after each change the booked jobs from today on are checked against the
rules before and after it, and a job that now breaks a rule it did not
break before is listed for the owner to keep or reschedule, the way a
pricebook publish lists affected jobs. The notice and the furthest date are
not checked: a booked job has already passed them.
"""

import datetime

from django.db import transaction
from django.utils import timezone

from appointments.models import Appointment

from .availability import job_from, load_rules, slot_reasons, day_reasons
from .models import AffectedJob, SettingsChange


def booked_range():
    """(first, last) dates of the booked jobs from today on, or None."""
    upcoming = Appointment.objects.filter(status=Appointment.Status.BOOKED, scheduled_start__gte=timezone.now())
    last = upcoming.order_by("-scheduled_start").values_list("scheduled_start", flat=True).first()
    if last is None:
        return None
    return timezone.localdate(), timezone.localtime(last).date()


def snapshot():
    """The rules for every booked job from today on, to compare after a change."""
    found = booked_range()
    return load_rules(*found) if found else None


def broken(rules, appointment):
    """The rules a booked job breaks under rules, as text."""
    day = timezone.localtime(appointment.scheduled_start).date()
    today = timezone.localdate()
    hours, reasons = day_reasons(rules, day, today, window=False)
    others = rules.jobs_on(day, exclude=appointment.pk)
    reasons += slot_reasons(rules, job_from(appointment), appointment.scheduled_start.astimezone(datetime.timezone.utc),
                            day, hours, others, check_start_time=hours is not None)
    return [str(reason) for reason in reasons]


@transaction.atomic
def record(before, summary, user):
    """Compare the booked jobs under the rules before a change (a snapshot()
    taken before saving it) with the rules now. Returns the SettingsChange
    listing the jobs that now break a rule, or None when there are none."""
    if before is None:
        return None
    after = load_rules(*booked_range()) if booked_range() else None
    if after is None:
        return None
    rows = []
    upcoming = Appointment.objects.filter(status=Appointment.Status.BOOKED, scheduled_start__gte=timezone.now())
    for appointment in upcoming.select_related("service_address", "quote__service").prefetch_related("lines__service"):
        old, new = set(broken(before, appointment)), broken(after, appointment)
        added = [reason for reason in new if reason not in old]
        if added:
            rows.append((appointment, added))
    if not rows:
        return None
    change = SettingsChange.objects.create(summary=summary, made_by=user)
    AffectedJob.objects.bulk_create(AffectedJob(change=change, appointment=appointment, rules_broken=reasons) for appointment, reasons in rows)
    return change


def waiting():
    """Affected jobs still waiting for the owner's choice, on booked jobs."""
    return AffectedJob.objects.filter(choice="", appointment__status=Appointment.Status.BOOKED)


def decide(affected, choice, user):
    affected.choice = choice
    affected.decided_at = timezone.now()
    affected.decided_by = user
    affected.save()


def job_moved(appointment, user, canceled=False):
    """Record the owner's choice on every listing still waiting for this job
    when it is moved or canceled."""
    choice = AffectedJob.Choice.CANCELED if canceled else AffectedJob.Choice.RESCHEDULED
    for affected in AffectedJob.objects.filter(appointment=appointment, choice=""):
        decide(affected, choice, user)
