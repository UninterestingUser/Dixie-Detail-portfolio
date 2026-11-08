"""The Google Calendar sync (decisions 0057 and 0098), against a fake Google
Calendar: no network."""

import datetime
import io
import json
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django.utils import timezone

from appointments import booking
from appointments.models import Appointment
from control.fixtures import JobsTestCase, local, open_day
from scheduling import availability
from scheduling.models import DateException, SchedulingSettings, TimeOffEvent

from . import events, google, sync
from .models import CalendarEvent, CalendarFlag, SyncState, SyncTask
from .testing import FakeCalendar

JOBS, TIME_OFF = "jobs", "time-off"


def all_day(day, days=1, **extra):
    return {"start": {"date": day.isoformat()}, "end": {"date": (day + datetime.timedelta(days=days)).isoformat()}, **extra}


def timed(start, end, **extra):
    return {"start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()}, **extra}


class SyncTestCase(JobsTestCase):
    def setUp(self):
        super().setUp()
        self.google = FakeCalendar()
        patcher = google.use_client(self.google)
        patcher.__enter__()
        self.addCleanup(patcher.__exit__, None, None, None)
        self.day = open_day(10)

    def book(self, day=None, hour=8, inputs=None):
        inputs = inputs or booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1)
        return booking.book(self.customer, self.vehicle, local(day or self.day, hour), inputs, address=self.address)

    def push(self, now=None):
        return sync.process_queue(now)

    def job_events(self):
        return {k: v for k, v in self.google.live(JOBS).items() if v["extendedProperties"]["private"]["dixie"] == "job"}

    def later(self, **delta):
        return timezone.now() + datetime.timedelta(**delta)


class JobEventTests(SyncTestCase):
    def test_one_event_covers_the_whole_time_on_site(self):
        job = self.book()
        self.push()
        event = self.google.live(JOBS)[events.job_event_id(job.calendar_key.hex)]
        self.assertEqual(event["summary"], "Full Detail · 2019 Toyota RAV4, blue")
        self.assertEqual(event["location"], "100 Sample Rd, Calhoun, TN 37309")
        self.assertEqual(events.moment_of(event["start"]), job.scheduled_start.astimezone(datetime.timezone.utc).isoformat())
        self.assertEqual(events.moment_of(event["end"]), job.ends_at.isoformat())
        notes = event["description"]
        self.assertIn(f"Customer: Pat Example, {self.customer.mobile_display}", notes)
        self.assertIn("Services: Full Detail", notes)
        self.assertIn("Total: $", notes)
        self.assertIn("Payment: not chosen", notes)
        job.refresh_from_db()
        self.assertEqual(job.jobs_calendar_event_id, events.job_event_id(job.calendar_key.hex))

    def test_the_link_is_on_the_appointment_and_in_private_properties(self):
        job = self.book()
        self.push()
        event = self.google.live(JOBS)[job.jobs_calendar_event_id or events.job_event_id(job.calendar_key.hex)]
        self.assertEqual(event["extendedProperties"]["private"], {"dixie": "job", "dixie_link": f"job:{job.calendar_key.hex}"})
        self.assertNotIn("attendees", event)

    def test_customers_are_never_guests(self):
        self.book()
        self.push()
        for event in self.google.live(JOBS).values():
            self.assertNotIn("attendees", event)
            self.assertNotIn("organizer", event)

    def test_the_drive_to_job_block_runs_from_the_leave_time(self):
        job = self.book()
        job.drive_minutes = 32
        job.save()
        self.push()
        drive = self.google.live(JOBS)[events.drive_event_id(job.calendar_key.hex)]
        self.assertEqual(drive["summary"], "Drive to job")
        leave = job.scheduled_start - datetime.timedelta(minutes=42)
        self.assertEqual(events.moment_of(drive["start"]), leave.astimezone(datetime.timezone.utc).isoformat())
        self.assertEqual(events.moment_of(drive["end"]), job.scheduled_start.astimezone(datetime.timezone.utc).isoformat())
        self.assertEqual(drive["reminders"]["overrides"], [{"method": "popup", "minutes": 0}])
        self.assertEqual(drive["extendedProperties"]["private"]["dixie_link"], f"job:{job.calendar_key.hex}")

    def test_the_leave_buffer_is_a_setting(self):
        settings = SchedulingSettings.get()
        settings.leave_buffer_minutes = 20
        settings.save()
        job = self.book()
        job.drive_minutes = 30
        job.save()
        self.push()
        drive = self.google.live(JOBS)[events.drive_event_id(job.calendar_key.hex)]
        leave = job.scheduled_start - datetime.timedelta(minutes=50)
        self.assertEqual(events.moment_of(drive["start"]), leave.astimezone(datetime.timezone.utc).isoformat())

    def test_no_drive_block_without_a_drive_time(self):
        job = self.book()
        self.push()
        self.assertNotIn(events.drive_event_id(job.calendar_key.hex), self.google.live(JOBS))


class QueueTests(SyncTestCase):
    def test_booking_moving_and_canceling_go_through_the_queue(self):
        job = self.book()
        self.assertTrue(SyncTask.objects.filter(link=f"job:{job.calendar_key.hex}").exists())
        self.assertEqual(self.google.calls, [])  # the booking itself never calls Google
        self.push()
        self.assertFalse(SyncTask.objects.exists())
        job.scheduled_start = local(self.day, 9)
        job.save()
        self.push()
        event = self.google.live(JOBS)[events.job_event_id(job.calendar_key.hex)]
        self.assertEqual(events.moment_of(event["start"]), local(self.day, 9).astimezone(datetime.timezone.utc).isoformat())
        booking.cancel(job, "customer", self.owner_user)
        self.push()
        self.assertEqual(self.google.live(JOBS), {})

    def test_a_removed_job_loses_its_events(self):
        job = self.book()
        job.drive_minutes = 20
        job.save()
        self.push()
        self.assertEqual(len(self.google.live(JOBS)), 2)
        booking.remove(job)
        self.push()
        self.assertEqual(self.google.live(JOBS), {})
        self.assertFalse(CalendarEvent.objects.exists())

    def test_google_down_during_a_booking(self):
        self.google.down = True
        response = self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(self.day))
        job = Appointment.objects.get()
        self.assertRedirects(response, reverse("appointment", args=[job.pk]))
        self.push()
        task = SyncTask.objects.get()
        self.assertEqual(task.attempts, 1)
        self.assertIn("fake outage", task.last_error)
        self.assertGreater(task.due_at, timezone.now())
        # Not due yet: nothing is tried.
        calls = len(self.google.calls)
        self.push()
        self.assertEqual(len(self.google.calls), calls)
        # Still down at the next try: the wait grows.
        first_wait = task.due_at
        self.push(task.due_at)
        task.refresh_from_db()
        self.assertEqual(task.attempts, 2)
        self.assertGreater(task.due_at - first_wait, datetime.timedelta(seconds=30))
        # Google is back.
        self.google.down = False
        self.push(task.due_at)
        self.assertFalse(SyncTask.objects.exists())
        self.assertIn(events.job_event_id(job.calendar_key.hex), self.google.live(JOBS))

    def test_a_change_made_while_its_link_is_pushed_is_pushed_again(self):
        job = self.book()
        original = sync.push_link

        def push_and_change(api, link, report=None):
            original(api, link, report)
            sync.enqueue(link)

        with mock.patch.object(sync, "push_link", push_and_change):
            self.push()
        self.assertTrue(SyncTask.objects.filter(link=f"job:{job.calendar_key.hex}", claimed_until=None).exists())

    def test_a_task_held_by_a_stopped_worker_is_taken_again(self):
        job = self.book()
        SyncTask.objects.update(claimed_until=timezone.now() + datetime.timedelta(minutes=1))
        self.push()
        self.assertEqual(self.google.live(JOBS), {})
        self.push(self.later(minutes=2))
        self.assertIn(events.job_event_id(job.calendar_key.hex), self.google.live(JOBS))

    def test_changes_to_the_same_job_fold_into_one_task(self):
        job = self.book()
        job.notes = "Gate code 1234"
        job.save()
        self.assertEqual(SyncTask.objects.count(), 1)
        self.assertGreater(SyncTask.objects.get().version, 1)

    def test_nothing_is_tried_while_the_calendars_are_not_connected(self):
        with google.use_client(None):
            self.book()
            self.assertFalse(google.connected())
            self.push()
        self.assertEqual(self.google.calls, [])
        self.assertTrue(SyncTask.objects.exists())

    def test_the_worker_runs_a_pass(self):
        self.book()
        out = io.StringIO()
        call_command("calendar_worker", "--once", stdout=out)
        self.assertFalse(SyncTask.objects.exists())
        self.assertIn("Calendar round:", out.getvalue())
        self.assertIsNotNone(SyncState.get().worker_seen_at)


class AppVersionWinsTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        self.job = self.book()
        self.push()
        self.event_id = events.job_event_id(self.job.calendar_key.hex)

    def test_an_event_edited_in_google_is_put_back_and_noted(self):
        start = self.google.live(JOBS)[self.event_id]["start"]
        self.google.edit_by_hand(JOBS, self.event_id, summary="Moved by hand", start={"dateTime": local(self.day, 11).isoformat()})
        report = sync.check_jobs(self.google)
        event = self.google.live(JOBS)[self.event_id]
        self.assertEqual(event["summary"], "Full Detail · 2019 Toyota RAV4, blue")
        self.assertEqual(events.moment_of(event["start"]), events.moment_of(start))
        self.assertEqual(report.restored, 1)
        flag = CalendarFlag.objects.get(kind="reset")
        self.assertEqual(flag.appointment, self.job)
        self.assertEqual(flag.detail, "Changed in Google (title, time); put back as the app has it.")
        self.job.refresh_from_db()
        self.assertEqual(self.job.scheduled_start, local(self.day, 8))  # Google never changes an appointment
        page = self.client.get(reverse("schedule"))
        self.assertContains(page, "Put back on the Jobs calendar: Full Detail")
        self.assertContains(self.client.get(reverse("appointment", args=[self.job.pk])), "Changed in Google (title, time)")
        self.client.post(reverse("calendar-flag", args=[flag.pk]), {"action": "seen"})
        flag.refresh_from_db()
        self.assertEqual(flag.outcome, "seen")

    def test_an_event_deleted_in_google_is_recreated(self):
        self.google.delete_by_hand(JOBS, self.event_id)
        sync.check_jobs(self.google)
        self.assertIn(self.event_id, self.google.live(JOBS))
        self.assertEqual(CalendarFlag.objects.get(kind="reset").detail, "Deleted in Google; put back as the app has it.")

    def test_a_change_in_the_app_not_yet_pushed_is_not_called_an_edit(self):
        self.job.notes = "x"
        self.job.scheduled_start = local(self.day, 9)
        self.job.save()
        report = sync.check_jobs(self.google)
        self.assertEqual(report.restored, 0)
        self.assertEqual(report.updated, 1)
        self.assertFalse(CalendarFlag.objects.exists())

    def test_a_leftover_event_of_a_canceled_job_is_deleted(self):
        Appointment.objects.filter(pk=self.job.pk).update(status="canceled")  # no signal: as if the push were lost
        SyncTask.objects.all().delete()
        sync.check_jobs(self.google)
        self.assertEqual(self.google.live(JOBS), {})

    def test_an_event_added_by_hand_is_busy_and_flagged_never_deleted(self):
        other = open_day(12)
        hand = self.google.add_by_hand(JOBS, timed(local(other, 7), local(other, 12), summary="Dentist", transparency="transparent"))
        sync.check_jobs(self.google)
        sync.check_jobs(self.google)
        self.assertIn(hand, self.google.live(JOBS))
        flag = CalendarFlag.objects.get(kind="by_hand")
        self.assertEqual(flag.summary, "Dentist")
        copy = TimeOffEvent.objects.get(calendar="jobs")
        self.assertEqual(copy.event_id, hand)
        job = booking.job_to_place(booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1), other)
        reasons = availability.check(job, local(other, 8))
        self.assertTrue(any("Dentist" in reason.text for reason in reasons))
        self.assertContains(self.client.get(reverse("schedule")), "Added to the Jobs calendar by hand: Dentist")
        # Deleted (or moved to Time Off) in Google: the busy time and the flag go.
        self.google.delete_by_hand(JOBS, hand)
        sync.check_jobs(self.google)
        self.assertFalse(TimeOffEvent.objects.filter(calendar="jobs").exists())
        flag.refresh_from_db()
        self.assertEqual(flag.outcome, "cleared")

    def test_closed_days_show_as_all_day_closed_events(self):
        closed = open_day(15)
        exception = DateException.objects.create(date=closed, kind=DateException.Kind.CLOSED, reason="Family trip")
        self.push()
        event = self.google.live(JOBS)[events.closed_event_id(closed)]
        self.assertEqual(event["summary"], "Closed")
        self.assertEqual(event["description"], "Family trip")
        self.assertEqual((event["start"], event["end"]), ({"date": closed.isoformat()}, {"date": (closed + datetime.timedelta(days=1)).isoformat()}))
        exception.delete()
        self.push()
        self.assertNotIn(events.closed_event_id(closed), self.google.live(JOBS))

    def test_a_different_hours_day_is_not_closed(self):
        DateException.objects.create(date=open_day(15), kind=DateException.Kind.HOURS, opens_at=datetime.time(9), closes_at=datetime.time(12))
        self.push()
        self.assertNotIn(events.closed_event_id(open_day(15)), self.google.live(JOBS))


class NightlyCheckTests(SyncTestCase):
    def test_the_full_check_repairs_every_difference_and_reports(self):
        kept = self.book()
        moved = self.book(open_day(12))
        self.push()
        # Lost in Google, edited in Google, and one never written.
        self.google.calendars[JOBS].pop(events.job_event_id(kept.calendar_key.hex))
        CalendarEvent.objects.filter(event_id=events.job_event_id(kept.calendar_key.hex)).delete()
        self.google.edit_by_hand(JOBS, events.job_event_id(moved.calendar_key.hex), location="Somewhere else")
        unwritten = self.book(open_day(14))
        SyncTask.objects.all().delete()
        out = io.StringIO()
        call_command("sync_calendars", stdout=out)
        self.assertEqual(len(self.job_events()), 3)
        self.assertEqual(self.google.live(JOBS)[events.job_event_id(moved.calendar_key.hex)]["location"], "100 Sample Rd, Calhoun, TN 37309")
        self.assertIn(events.job_event_id(unwritten.calendar_key.hex), self.google.live(JOBS))
        summary = out.getvalue().strip().splitlines()[-1]
        self.assertEqual(summary, "Calendar check: 3 events checked, 2 created, 0 updated, 1 put back after an edit in Google, "
                                  "0 deleted, 0 added by hand, 0 Time Off clashes open.")
        self.assertIsNotNone(SyncState.get().full_check_at)

    def test_past_jobs_are_left_alone(self):
        past = timezone.localdate() - datetime.timedelta(days=3)
        Appointment.objects.create(customer=self.customer, vehicle=self.vehicle, scheduled_start=local(past, 9),
                                   status=Appointment.Status.COMPLETED, source=Appointment.Source.OWNER)
        SyncTask.objects.all().delete()
        call_command("sync_calendars", stdout=io.StringIO())
        self.assertEqual(self.google.live(JOBS), {})

    def test_google_down_fails_the_run(self):
        self.google.down = True
        with self.assertRaises(CommandError):
            call_command("sync_calendars", stdout=io.StringIO())

    def test_not_connected_fails_the_run(self):
        with google.use_client(None), self.assertRaisesMessage(CommandError, "not connected"):
            call_command("sync_calendars", stdout=io.StringIO())

    def test_the_first_run_dry_run_prints_and_changes_nothing(self):
        job = self.book()
        job.drive_minutes = 25
        job.save()
        DateException.objects.create(date=open_day(15), kind=DateException.Kind.CLOSED, reason="Family trip")
        out = io.StringIO()
        call_command("sync_calendars", "--dry-run", stdout=out)
        text = out.getvalue()
        self.assertIn("Full Detail · 2019 Toyota RAV4, blue", text)
        self.assertIn("100 Sample Rd, Calhoun, TN 37309", text)
        self.assertIn("Drive to job", text)
        self.assertIn("Closed", text)
        self.assertIn("Dry run: 1 job events, 1 Drive to job blocks and 1 Closed days would be on the Jobs calendar. Nothing was changed.", text)
        self.assertEqual(self.google.calls, [])
        call_command("sync_calendars", stdout=io.StringIO())
        self.assertEqual(len(self.google.live(JOBS)), 3)


class TimeOffTests(SyncTestCase):
    def check(self, day, hour=8):
        job = booking.job_to_place(booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1), day)
        return availability.check(job, local(day, hour))

    def test_an_all_day_event_closes_its_days(self):
        first = open_day(20)
        self.google.add_by_hand(TIME_OFF, all_day(first, 2, summary="Beach", transparency="transparent"))
        self.assertTrue(sync.refresh_time_off())
        for day in (first, first + datetime.timedelta(days=1)):
            self.assertTrue(any("Beach" in reason.text for reason in self.check(day)), day)
        after = first + datetime.timedelta(days=2)
        if after.weekday() != 6:
            self.assertFalse(any("Beach" in reason.text for reason in self.check(after)))

    def test_a_timed_event_blocks_its_time_plus_the_buffer(self):
        day = open_day(20)
        self.google.add_by_hand(TIME_OFF, timed(local(day, 14), local(day, 15), summary="Dentist"))
        sync.refresh_time_off()
        self.assertFalse(self.check(day, 8))  # a job that ends at 1:00 PM fits before it
        self.assertTrue(any("Dentist" in reason.text for reason in self.check(day, 10)))
        settings = SchedulingSettings.get()
        settings.time_off_buffer_minutes = 90
        settings.save()
        self.assertTrue(any("Dentist" in reason.text for reason in self.check(day, 8)))

    def test_a_repeating_event_counts_visit_by_visit(self):
        first = open_day(20)
        self.google.add_by_hand(TIME_OFF, timed(local(first, 8), local(first, 10), summary="Weekly class",
                                                recurrence=["RRULE:FREQ=WEEKLY;COUNT=3"]))
        sync.refresh_time_off()
        self.assertEqual(TimeOffEvent.objects.filter(calendar="time_off").count(), 3)
        for week in range(3):
            day = first + datetime.timedelta(days=7 * week)
            self.assertTrue(any("Weekly class" in reason.text for reason in self.check(day)), day)
        self.assertFalse(any("Weekly class" in r.text for r in self.check(first + datetime.timedelta(days=21))))

    def test_deleting_an_event_reopens_its_time(self):
        day = open_day(20)
        event_id = self.google.add_by_hand(TIME_OFF, all_day(day, summary="Off"))
        sync.refresh_time_off()
        self.assertTrue(self.check(day))
        self.google.delete_by_hand(TIME_OFF, event_id)
        sync.refresh_time_off()
        self.assertFalse(self.check(day))

    def test_google_down_keeps_the_last_copy_and_notes_the_error(self):
        day = open_day(20)
        self.google.add_by_hand(TIME_OFF, all_day(day, summary="Off"))
        sync.refresh_time_off()
        self.google.down = True
        self.assertFalse(sync.refresh_time_off())
        self.assertTrue(self.check(day))
        self.assertIn("fake outage", SyncState.get().time_off_error)

    def test_a_booking_being_sent_copies_time_off_again(self):
        day = open_day(20)
        sync.refresh_time_off(self.later(minutes=-5))
        SyncState.get()
        SyncState.objects.update(time_off_copied_at=self.later(minutes=-5))
        self.google.add_by_hand(TIME_OFF, all_day(day, summary="Just added"))
        page = self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(day))
        self.assertContains(page, "Just added")
        self.assertFalse(Appointment.objects.exists())

    def test_a_booking_goes_ahead_with_the_last_copy_while_google_is_down(self):
        day = open_day(20)
        SyncState.get()
        SyncState.objects.update(time_off_copied_at=self.later(minutes=-5))
        self.google.add_by_hand(TIME_OFF, all_day(day, summary="Just added"))
        self.google.down = True
        response = self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(day))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Appointment.objects.exists())

    def test_the_website_booking_copies_time_off_too(self):
        day = open_day(20)
        self.google.add_by_hand(TIME_OFF, all_day(day, summary="Just added"))
        with self.assertRaises(booking.RulesBroken):
            booking.book_online(self.customer, self.vehicle, local(day), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1))

    def test_a_copy_under_a_minute_old_is_not_fetched_again(self):
        sync.refresh_time_off()
        calls = len(self.google.calls)
        sync.refresh_time_off_for_booking()
        self.assertEqual(len(self.google.calls), calls)


class StaleWarningTests(SyncTestCase):
    def test_a_copy_older_than_the_setting_shows_a_warning(self):
        SyncState.get()
        SyncState.objects.update(time_off_copied_at=self.later(minutes=-30))
        self.assertIsNone(sync.time_off_warning())
        self.assertNotContains(self.client.get(reverse("schedule")), "Time Off calendar was last copied")
        SyncState.get()
        SyncState.objects.update(time_off_copied_at=self.later(minutes=-61), time_off_error="Google Calendar answered 503")
        warning = sync.time_off_warning()
        self.assertIn("The Time Off calendar was last copied 61 minutes ago", warning)
        self.assertIn("Google Calendar answered 503", warning)
        self.assertContains(self.client.get(reverse("schedule")), "Time Off calendar was last copied 61 minutes ago")
        self.assertContains(self.client.get(reverse("appointment-new", args=[self.customer.pk])), "last copied 61 minutes ago")

    def test_never_copied_and_not_connected(self):
        self.assertIn("has not been copied yet", sync.time_off_warning())
        with google.use_client(None):
            self.assertIn("not connected", sync.time_off_warning())


class ClashTests(SyncTestCase):
    def setUp(self):
        super().setUp()
        self.job = self.book()

    def test_time_off_over_a_booked_job_is_flagged_never_acted_on(self):
        event_id = self.google.add_by_hand(TIME_OFF, all_day(self.day, summary="Sick day"))
        sync.refresh_time_off()
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.scheduled_start), ("booked", local(self.day, 8)))
        flag = CalendarFlag.objects.get(kind="clash")
        self.assertEqual((flag.appointment, flag.event_id, flag.summary), (self.job, event_id, "Sick day"))
        page = self.client.get(reverse("schedule"))
        self.assertContains(page, "Time Off over a booked job: Sick day")
        self.assertContains(page, 'value="keep">Keep</button>')
        self.assertContains(page, f'href="{reverse("appointment-edit", args=[self.job.pk])}">Reschedule</a>')
        self.assertContains(page, f'href="{reverse("appointment", args=[self.job.pk])}#cancel">Cancel</a>')
        # Checked again: still one flag.
        sync.refresh_time_off()
        self.assertEqual(CalendarFlag.objects.filter(kind="clash").count(), 1)

    def test_keep(self):
        self.google.add_by_hand(TIME_OFF, all_day(self.day, summary="Sick day"))
        sync.refresh_time_off()
        flag = CalendarFlag.objects.get()
        self.client.force_login(self.helper_user)
        self.client.post(reverse("calendar-flag", args=[flag.pk]), {"action": "keep"})
        flag.refresh_from_db()
        self.assertEqual(flag.outcome, "")
        self.client.force_login(self.owner_user)
        self.client.post(reverse("calendar-flag", args=[flag.pk]), {"action": "keep"})
        flag.refresh_from_db()
        self.assertEqual((flag.outcome, flag.closed_by), ("kept", self.owner_user))
        sync.refresh_time_off()
        self.assertFalse(CalendarFlag.objects.filter(outcome="").exists())  # kept stays kept
        self.assertNotContains(self.client.get(reverse("schedule")), "Time Off over a booked job")

    def test_a_clash_clears_when_the_job_moves_or_the_time_off_goes(self):
        event_id = self.google.add_by_hand(TIME_OFF, timed(local(self.day, 10), local(self.day, 11), summary="Call"))
        sync.refresh_time_off()
        self.assertEqual(CalendarFlag.objects.get().outcome, "")
        self.google.delete_by_hand(TIME_OFF, event_id)
        sync.refresh_time_off()
        self.assertEqual(CalendarFlag.objects.get().outcome, "cleared")

    def test_a_timed_event_beside_the_job_is_no_clash(self):
        self.google.add_by_hand(TIME_OFF, timed(local(self.day, 14), local(self.day, 15), summary="After"))
        sync.refresh_time_off()
        self.assertFalse(CalendarFlag.objects.exists())

    def test_a_canceled_job_is_no_clash(self):
        booking.cancel(self.job, "customer", self.owner_user)
        self.google.add_by_hand(TIME_OFF, all_day(self.day, summary="Sick day"))
        sync.refresh_time_off()
        self.assertFalse(CalendarFlag.objects.exists())


class GoogleClientTests(JobsTestCase):
    def test_the_token_request_is_signed_with_the_service_account_key(self):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        client = google.GoogleCalendar(json.dumps({"client_email": "sync@example.iam.gserviceaccount.com", "private_key": pem,
                                                   "token_uri": "https://oauth2.googleapis.com/token"}))
        token = client.assertion(1_800_000_000)
        header, claims, signature = token.split(".")
        import base64

        def decode(part):
            return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))

        body = json.loads(decode(claims))
        self.assertEqual(body["scope"], "https://www.googleapis.com/auth/calendar.events")
        self.assertEqual(body["iss"], "sync@example.iam.gserviceaccount.com")
        self.assertEqual(body["exp"] - body["iat"], 3600)
        key.public_key().verify(decode(signature), f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())

    def test_not_connected_without_a_key(self):
        self.assertFalse(google.connected())
        with self.assertRaises(google.NotConnected):
            google.client()

    def test_event_ids_use_only_letters_google_allows(self):
        import re
        import uuid

        key = uuid.uuid4().hex
        for event_id in (events.job_event_id(key), events.drive_event_id(key), events.closed_event_id(datetime.date(2026, 12, 25))):
            self.assertRegex(event_id, re.compile(r"^[a-v0-9]{5,1024}$"))


class CalendarKeyMigrationTests(JobsTestCase):
    def test_every_appointment_has_its_own_key(self):
        a = booking.book(self.customer, self.vehicle, local(open_day(10)), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1))
        b = booking.book(self.customer, self.vehicle, local(open_day(11)), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1))
        self.assertNotEqual(a.calendar_key, b.calendar_key)
