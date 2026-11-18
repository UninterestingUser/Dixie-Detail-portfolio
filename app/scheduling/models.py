"""The scheduling settings, the local copy of the Time Off calendar, and the
records the availability check leaves behind (decision 0056).

Every scheduling rule is a setting, seeded from data/booking-rules.yaml the
first time it is read and changed on the control app's scheduling settings
screen, with change history. A change applies to bookings made after it:
each appointment keeps its own start, setup, service and breakdown minutes
and crew size as booked.
"""

import datetime

import yaml
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from simple_history.models import HistoricalRecords

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
# Rounding steps divide the hour, so rounding a time up gives the same
# quarter hour in Eastern time as in UTC, on every day of the year.
ROUNDING_CHOICES = [(1, "No rounding"), (5, "5 minutes"), (10, "10 minutes"), (15, "15 minutes"),
                    (20, "20 minutes"), (30, "30 minutes"), (60, "The hour")]


def parse_time(text):
    return datetime.time.fromisoformat(str(text))


def launch_rules():
    """data/booking-rules.yaml, which seeds the settings."""
    return yaml.safe_load((settings.DATA_DIR / "booking-rules.yaml").read_text())


class SchedulingSettings(models.Model):
    """The one row of numeric scheduling settings (pk 1). The weekly pattern,
    the services that can share a day and the date exceptions are their own
    records beside it."""

    minimum_notice_days = models.PositiveSmallIntegerField(
        help_text="Days between today (Eastern) and the first bookable date. 2 means no same-day or next-day booking."
    )
    furthest_bookable_days = models.PositiveSmallIntegerField(help_text="The furthest date bookable, in days from today.")
    setup_minutes_one_person = models.PositiveSmallIntegerField(help_text="Divided by the number of people on the job.")
    breakdown_minutes_one_person = models.PositiveSmallIntegerField(help_text="Divided by the number of people on the job.")
    time_on_site_rounding_minutes = models.PositiveSmallIntegerField(
        choices=ROUNDING_CHOICES, help_text="Time on site is rounded to the nearest step."
    )
    jobs_per_day = models.PositiveSmallIntegerField(
        help_text="Jobs a day. Services that can share a day may go past it, up to their own maximums."
    )
    minimum_gap_minutes = models.PositiveSmallIntegerField(
        help_text="The least time between one job's end (after breakdown) and the next job's start, even when the drive is shorter."
    )
    round_start_up_to_minutes = models.PositiveSmallIntegerField(
        choices=ROUNDING_CHOICES, help_text="A later job's earliest start is rounded up to the next step."
    )
    time_off_buffer_minutes = models.PositiveSmallIntegerField(
        help_text="Kept clear before and after a timed Time Off event."
    )
    time_off_check_minutes = models.PositiveSmallIntegerField(help_text="How often the Time Off calendar is copied.")
    stale_copy_warning_minutes = models.PositiveSmallIntegerField(
        help_text="The control app warns when the last Time Off copy is older than this."
    )
    leave_buffer_minutes = models.PositiveSmallIntegerField(
        default=10, help_text="Added to the drive time to set the leave time: the Drive to job block and the time-to-leave alert."
    )
    # Assigned to every new booking, from the website or the control app,
    # whoever else qualifies (decision 0107). Seeded by name from
    # data/booking-rules.yaml (staff_assignment.default_staff).
    default_staff = models.ForeignKey(
        "staff.StaffMember", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        help_text="Assigned to every new booking. The crew can still be changed on the job.",
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "scheduling settings"
        verbose_name_plural = "scheduling settings"

    def __str__(self):
        return "Scheduling settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        """The settings, seeded from data/booking-rules.yaml the first time."""
        found = cls.objects.filter(pk=1).first()
        return found or seed_from_launch_values()


class OpenWeekday(models.Model):
    """One weekday's hours and the start times offered on it. A closed
    weekday has no hours and no start times."""

    weekday = models.PositiveSmallIntegerField(unique=True, choices=list(enumerate(WEEKDAYS)), help_text="0 is Monday.")
    is_open = models.BooleanField(default=False)
    opens_at = models.TimeField(null=True, blank=True)
    closes_at = models.TimeField(null=True, blank=True)
    # The start time is the arrival time, when setup starts.
    start_times = ArrayField(models.TimeField(), default=list, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["weekday"]

    def __str__(self):
        return WEEKDAYS[self.weekday]


class SharedService(models.Model):
    """A service that can share a day with another job, and how many of it a
    day can hold. Both jobs' services must be listed for them to share."""

    service = models.OneToOneField("pricebook.Service", on_delete=models.CASCADE, related_name="sharing")
    max_per_day = models.PositiveSmallIntegerField(default=2)

    history = HistoricalRecords()

    class Meta:
        ordering = ["service__name"]

    def __str__(self):
        return f"{self.service}, up to {self.max_per_day} a day"


class DateException(models.Model):
    """One date closed, or open with different hours, set in the control
    app. A different-hours date offers its own start times, or when it has
    none, the weekday's start times that fall within its hours."""

    class Kind(models.TextChoices):
        CLOSED = "closed", "Closed all day"
        HOURS = "hours", "Different hours"

    date = models.DateField(unique=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    opens_at = models.TimeField(null=True, blank=True)
    closes_at = models.TimeField(null=True, blank=True)
    start_times = ArrayField(models.TimeField(), default=list, blank=True)
    reason = models.CharField(max_length=200, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"{self.date}: {self.get_kind_display().lower()}"


class TimeOffEvent(models.Model):
    """The local copy of one event that blocks time: an event on the Dixie
    Detail Time Off calendar, or one added to the Jobs calendar by hand
    (decision 0057). The calendar sync fills it (calendars.sync). An all-day
    event closes every date from first_date to last_date; a timed event
    blocks only its own time, plus the buffer setting."""

    class Calendar(models.TextChoices):
        TIME_OFF = "time_off", "Time Off"
        JOBS = "jobs", "Jobs, added by hand"

    calendar = models.CharField(max_length=10, choices=Calendar.choices, default=Calendar.TIME_OFF)
    event_id = models.CharField(max_length=200)
    summary = models.CharField(max_length=300, blank=True)
    all_day = models.BooleanField(default=False)
    first_date = models.DateField(null=True, blank=True)
    last_date = models.DateField(null=True, blank=True, help_text="The last date covered, inclusive.")
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    copied_at = models.DateTimeField()

    class Meta:
        ordering = ["first_date", "starts_at"]
        constraints = [models.UniqueConstraint(fields=["calendar", "event_id"], name="one_copy_per_calendar_event")]

    def __str__(self):
        return self.summary or self.event_id


class RuleOverride(models.Model):
    """A manager booking or moving a job outside the scheduling rules in the
    control app, or adding an add-on that doesn't go with its service: the
    rules broken, as the warning named them, and the reason. The website can
    never override."""

    class Action(models.TextChoices):
        BOOKED = "booked", "Booked"
        MOVED = "moved", "Moved"
        CHANGED = "changed", "Services changed"
        # An add-on that doesn't go with the job's service (decision 0106).
        ADD_ONS = "add_ons", "Add-on outside the rules"

    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.CASCADE, related_name="rule_overrides")
    action = models.CharField(max_length=10, choices=Action.choices, default=Action.BOOKED)
    # The start the job was booked or moved to, outside the rules.
    start = models.DateTimeField(null=True, blank=True)
    # The alert's lines, such as "Sunday is a closed day".
    rules_broken = ArrayField(models.CharField(max_length=300))
    reason = models.TextField()
    made_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    made_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-made_at"]

    def __str__(self):
        return f"Override on {self.appointment}"


class SettingsChange(models.Model):
    """One save of the scheduling settings that left booked jobs outside the
    new rules. Its affected jobs wait for the owner to keep or reschedule."""

    summary = models.CharField(max_length=300)
    made_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    made_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-made_at"]

    def __str__(self):
        return self.summary


class AffectedJob(models.Model):
    """A booked job a settings change left outside the rules, and the owner's
    choice. Keeping it changes nothing; rescheduling is done on the job's own
    screen, and is recorded when the job is moved or canceled."""

    class Choice(models.TextChoices):
        KEEP = "keep", "Kept as booked"
        RESCHEDULED = "rescheduled", "Rescheduled"
        CANCELED = "canceled", "Canceled"

    change = models.ForeignKey(SettingsChange, on_delete=models.CASCADE, related_name="affected_jobs")
    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.CASCADE, related_name="settings_reviews")
    rules_broken = ArrayField(models.CharField(max_length=300))
    choice = models.CharField(max_length=12, choices=Choice.choices, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["appointment__scheduled_start"]
        constraints = [models.UniqueConstraint(fields=["change", "appointment"], name="one_review_per_change_and_job")]

    def __str__(self):
        return f"{self.appointment}: {self.get_choice_display() or 'waiting'}"


def launch_default_staff_name(rules=None):
    """The name data/booking-rules.yaml gives as the default staff, or ""."""
    return (((rules or launch_rules()).get("staff_assignment") or {}).get("default_staff") or "").strip()


def launch_default_staff(rules=None, staff_model=None):
    """The active staff member data/booking-rules.yaml names as the default
    staff, matched by name ignoring case, or None. staff_model is for a
    migration's historical model."""
    if staff_model is None:
        from staff.models import StaffMember as staff_model
    name = launch_default_staff_name(rules)
    return staff_model.objects.filter(name__iexact=name, active=True).order_by("pk").first() if name else None


@transaction.atomic
def seed_from_launch_values():
    """Create the settings, the weekly pattern and the services that share a
    day from data/booking-rules.yaml, where they do not exist yet. A service
    not in the pricebook yet is skipped; it can be added on the screen."""
    from pricebook.models import Service

    rules = launch_rules()
    gap = rules["gap_between_jobs"]
    time_off = rules["calendars"]["time_off"]
    row, _ = SchedulingSettings.objects.get_or_create(pk=1, defaults={
        "minimum_notice_days": rules["minimum_notice_days"],
        "furthest_bookable_days": rules["furthest_bookable_days"],
        "setup_minutes_one_person": rules["setup_minutes_one_person"],
        "breakdown_minutes_one_person": rules["breakdown_minutes_one_person"],
        "time_on_site_rounding_minutes": rules["time_on_site_rounding_minutes"],
        "jobs_per_day": rules["jobs_per_day"],
        "minimum_gap_minutes": gap["minimum_minutes"],
        "round_start_up_to_minutes": gap["round_start_up_to_minutes"],
        "time_off_buffer_minutes": time_off["timed_event_buffer_minutes"],
        "time_off_check_minutes": time_off["check_every_minutes"],
        "stale_copy_warning_minutes": time_off["stale_copy_warning_minutes"],
        "leave_buffer_minutes": rules["time_to_leave_alert"]["buffer_minutes"],
        "default_staff": launch_default_staff(rules),
    })
    open_days = set(rules["open_weekdays"])
    for number, name in enumerate(WEEKDAYS):
        hours = rules["working_hours"].get(name) or {}
        OpenWeekday.objects.get_or_create(weekday=number, defaults={
            "is_open": name in open_days,
            "opens_at": parse_time(hours["open"]) if name in open_days else None,
            "closes_at": parse_time(hours["close"]) if name in open_days else None,
            "start_times": [parse_time(t) for t in rules["start_times_online"].get(name, [])] if name in open_days else [],
        })
    for entry in rules["services_sharing_a_day"]:
        service = Service.objects.filter(name=entry["service"]).first()
        if service is not None:
            SharedService.objects.get_or_create(service=service, defaults={"max_per_day": entry["max_per_day"]})
    return row
