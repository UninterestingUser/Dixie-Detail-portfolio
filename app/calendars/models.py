"""The Google Calendar sync's own records (decision 0098): the queue of
changes to push to the Jobs calendar, what was last written there, the flags
for the owner, and when each part last ran.

PostgreSQL stays the only record of appointments. Nothing here is ever read
back into an appointment.
"""

from django.conf import settings
from django.db import models


class SyncState(models.Model):
    """One row: when the Time Off copy and the Jobs check last ran, and the
    last error from Google, for the control app's warning."""

    time_off_copied_at = models.DateTimeField(null=True, blank=True)
    time_off_error = models.CharField(max_length=500, blank=True)
    time_off_error_at = models.DateTimeField(null=True, blank=True)
    jobs_checked_at = models.DateTimeField(null=True, blank=True)
    jobs_error = models.CharField(max_length=500, blank=True)
    full_check_at = models.DateTimeField(null=True, blank=True)
    worker_seen_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def __str__(self):
        return "Calendar sync state"


class SyncTask(models.Model):
    """One link waiting to be pushed to the Jobs calendar: an appointment's
    events ("job:<calendar key>") or a closed day's ("closed:<date>"). A
    later change to the same link folds into the same row and bumps its
    version, so the worker never pushes an old state as the last one."""

    link = models.CharField(max_length=80, unique=True)
    version = models.PositiveIntegerField(default=1)
    due_at = models.DateTimeField()
    # Held by a worker until this time; a worker that stops lets it go.
    claimed_until = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_at"]
        indexes = [models.Index(fields=["due_at"])]

    def __str__(self):
        return self.link


class CalendarEvent(models.Model):
    """An event the app wrote to the Jobs calendar, and a fingerprint of what
    it wrote, so the check can tell an edit made in Google from a change in
    the app still on its way."""

    class Kind(models.TextChoices):
        JOB = "job", "Job"
        DRIVE = "drive", "Drive to job"
        CLOSED = "closed", "Closed"

    event_id = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    link = models.CharField(max_length=80, db_index=True)
    fingerprint = models.CharField(max_length=64)
    synced_at = models.DateTimeField()

    def __str__(self):
        return self.event_id


class CalendarFlag(models.Model):
    """Something on a calendar the owner should know about, on the control
    app's home screen:

    - clash: a Time Off event over a booked job, to keep, reschedule or cancel;
    - by_hand: an event added to the Jobs calendar by hand, counted as busy
      until it is moved to Time Off or deleted;
    - reset: a Jobs event edited or deleted in Google, put back as the app has it.

    A clash or by-hand flag closes itself when its cause goes away."""

    class Kind(models.TextChoices):
        CLASH = "clash", "Time Off over a booked job"
        BY_HAND = "by_hand", "Added to the Jobs calendar by hand"
        RESET = "reset", "Jobs event put back"

    class Outcome(models.TextChoices):
        OPEN = "", "Open"
        KEPT = "kept", "Kept"
        CLEARED = "cleared", "Cleared"
        SEEN = "seen", "Seen"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.CASCADE, null=True, blank=True, related_name="calendar_flags"
    )
    event_id = models.CharField(max_length=200, blank=True)
    summary = models.CharField(max_length=300, blank=True)
    detail = models.CharField(max_length=500, blank=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    outcome = models.CharField(max_length=10, choices=Outcome.choices, blank=True, default="")
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["kind", "outcome"])]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.summary}"
