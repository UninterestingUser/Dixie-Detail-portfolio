"""Booking outside the rules inline: the alert under the date and time, the
reason box, the check at submit, and the reason shown on the job (decision 0096)."""

import datetime

from django.urls import reverse
from django.utils import timezone

from appointments import booking
from appointments.models import Appointment
from scheduling.models import RuleOverride

from .fixtures import JobsTestCase, local, open_day

ALLOWED = "Booking off hours is allowed. Give the reason below and it will be logged with the job."


def next_sunday():
    today = timezone.localdate()
    return today + datetime.timedelta(days=(6 - today.weekday()) % 7 + 7)


class LiveAlertTests(JobsTestCase):
    def live(self, day, **changes):
        return self.client.post(reverse("appointment-price-new", args=[self.customer.pk]), self.booking_data(day, **changes))

    def alert(self, response):
        """The out-of-band alert in a live response, or None when absent."""
        html = response.content.decode()
        if 'id="rules-alert" hx-swap-oob="true"' not in html:
            return None
        return html[html.index('id="rules-alert"'):]

    def test_the_alert_appears_when_the_date_breaks_a_rule(self):
        alert = self.alert(self.live(next_sunday()))
        self.assertIn("Sunday is a closed day", alert)
        self.assertIn(ALLOWED, alert)
        self.assertIn('name="override_reason"', alert)
        self.assertNotIn("Give the reason for booking off hours.", alert)  # not until the form is sent

    def test_the_alert_goes_away_when_the_choice_fits(self):
        alert = self.alert(self.live(open_day(10)))
        self.assertIsNotNone(alert)
        self.assertNotIn("notice rules-alert", alert)
        self.assertNotIn('name="override_reason"', alert)

    def test_the_time_and_the_services_are_checked_too(self):
        day = open_day(10)
        self.assertIn("10:15 AM is not a start time", self.alert(self.live(day, time="10:15")))
        booking.book(self.customer, self.vehicle, local(day), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1))
        # A Monthly Maintenance can share the day with another; a Full Detail can't.
        self.assertIn("can't share a day", self.alert(self.live(day, time="08:00")).replace("&#x27;", "'"))

    def test_the_reason_typed_is_kept_while_the_alert_shows(self):
        alert = self.alert(self.live(next_sunday(), override_reason="Customer works weekdays"))
        self.assertIn("Customer works weekdays", alert)

    def test_the_alert_is_left_alone_without_a_date_or_time(self):
        self.assertIsNone(self.alert(self.live(next_sunday(), time="")))
        self.assertIsNone(self.alert(self.live(next_sunday(), date="not a date")))

    def test_the_form_checks_on_every_change_except_the_reason(self):
        page = self.client.get(reverse("appointment-new", args=[self.customer.pk]))
        self.assertContains(page, "hx-trigger=\"change[target.name!='override_reason'&&target.name!='add_on_reason'], load\"")
        self.assertContains(page, '<div id="rules-alert">')
        self.assertNotContains(page, "outside the rules</button>")

    def test_a_new_booking_opens_on_the_first_bookable_date(self):
        page = self.client.get(reverse("appointment-new", args=[self.customer.pk]))
        day = page.context["form"].initial["date"]
        self.assertGreaterEqual(day, timezone.localdate() + datetime.timedelta(days=2))
        self.assertNotEqual(day.weekday(), 6)


class BeforeTheServicesTests(JobsTestCase):
    """The alert appears as soon as a date or time that breaks a rule is
    picked, before any service is chosen (decision 0097)."""

    def live(self, day, **changes):
        return self.client.post(reverse("appointment-price-new", args=[self.customer.pk]), self.booking_data(day, **changes))

    def alert(self, response):
        html = response.content.decode().replace("&#x27;", "'")
        self.assertIn('id="rules-alert" hx-swap-oob="true"', html)
        return html[html.index('id="rules-alert"'):]

    def no_services(self, day, **changes):
        return self.live(day, service="", condition_level="", **changes)

    def test_a_closed_day_shows_the_alert_with_no_services_chosen(self):
        alert = self.alert(self.no_services(next_sunday()))
        self.assertIn("Sunday is a closed day", alert)
        self.assertIn(ALLOWED, alert)
        self.assertIn('name="override_reason"', alert)

    def test_and_with_the_services_only_partly_chosen(self):
        self.assertIn("Sunday is a closed day", self.alert(self.live(next_sunday(), condition_level="")))

    def test_the_date_window_and_the_arrival_time(self):
        self.assertIn("10:15 AM is not a start time", self.alert(self.no_services(open_day(10), time="10:15")))
        too_soon = timezone.localdate() + datetime.timedelta(days=1)
        self.assertIn('notice rules-alert', self.alert(self.no_services(too_soon)))
        self.assertNotIn('notice rules-alert', self.alert(self.no_services(open_day(10))))

    def test_a_day_with_a_job_shows_the_alert_at_once(self):
        day = open_day(10)
        booking.book(self.customer, self.vehicle, local(day, 13), booking.JobInputs(self.monthly, self.crossover, self.two_rows))
        alert = self.alert(self.no_services(day))
        self.assertIn("The day already has 1 job, and a job with no services chosen yet can't share a day", alert)
        # Once a service that may share the day is chosen, the alert goes away.
        alert = self.alert(self.live(day, service=self.monthly.pk, condition_level=""))
        self.assertNotIn("notice rules-alert", alert)
        # A Full Detail can't share the day, so it stays.
        self.assertIn("can't share a day", self.alert(self.live(day)))

    def test_the_rules_that_need_the_services_wait_for_them(self):
        day = open_day(10)
        booking.book(self.customer, self.vehicle, local(day, 8), booking.JobInputs(self.monthly, self.crossover, self.two_rows))
        # Arriving after the morning job: with no services, only sharing the
        # day is judged, never the length of the job.
        alert = self.alert(self.no_services(day, time="12:00"))
        self.assertNotIn("Ends at", alert)
        self.assertNotIn("past closing", alert)
        self.assertNotIn("Too close", alert)

    def test_a_job_being_changed_is_checked_before_its_services_are_chosen_too(self):
        day = open_day(10)
        job = booking.book(self.customer, self.vehicle, local(day), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1), address=self.address)
        live = self.client.post(reverse("appointment-price", args=[job.pk]), self.booking_data(next_sunday(), condition_level=""))
        self.assertIn("Sunday is a closed day", self.alert(live))
        # Left where it is, its own day doesn't count against it.
        live = self.client.post(reverse("appointment-price", args=[job.pk]), self.booking_data(day, condition_level=""))
        self.assertNotIn("notice rules-alert", self.alert(live))


class SubmitTests(JobsTestCase):
    def book(self, day, **changes):
        return self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(day, **changes))

    def test_the_reason_is_required_while_the_alert_shows(self):
        page = self.book(next_sunday())
        self.assertContains(page, "Sunday is a closed day")
        self.assertContains(page, ALLOWED)
        self.assertContains(page, "Give the reason for booking off hours.")
        self.assertFalse(Appointment.objects.exists())
        self.book(next_sunday(), override_reason="   ")
        self.assertFalse(Appointment.objects.exists())

    def test_the_one_book_button_books_with_the_reason(self):
        response = self.book(next_sunday(), override_reason="Customer works weekdays")
        appointment = Appointment.objects.get()
        self.assertRedirects(response, reverse("appointment", args=[appointment.pk]))
        self.assertEqual(appointment.rule_overrides.get().reason, "Customer works weekdays")

    def test_a_reason_for_a_choice_that_fits_is_not_logged(self):
        self.book(open_day(10), override_reason="Typed before changing the date")
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertFalse(RuleOverride.objects.exists())

    def test_the_server_checks_again_when_the_slot_was_taken_in_the_meantime(self):
        day = open_day(10)
        # The live check found the time open...
        live = self.client.post(reverse("appointment-price-new", args=[self.customer.pk]), self.booking_data(day))
        self.assertNotContains(live, "notice rules-alert")
        # ...then someone else booked the day before the form was sent.
        booking.book(self.customer, self.vehicle, local(day), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1))
        page = self.book(day)
        self.assertContains(page, "notice rules-alert")
        self.assertContains(page, ALLOWED)
        self.assertContains(page, "Give the reason for booking off hours.")
        self.assertEqual(Appointment.objects.count(), 1)

    def test_changing_a_job_uses_the_same_alert(self):
        day = open_day(10)
        job = booking.book(self.customer, self.vehicle, local(day), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1), address=self.address)
        url = reverse("appointment-edit", args=[job.pk])
        live = self.client.post(reverse("appointment-price", args=[job.pk]), self.booking_data(next_sunday(), crew_size="1"))
        self.assertContains(live, "Sunday is a closed day")
        page = self.client.post(url, self.booking_data(next_sunday(), crew_size="1"))
        self.assertContains(page, "Give the reason for booking off hours.")
        self.client.post(url, self.booking_data(next_sunday(), crew_size="1", override_reason="Only day the customer is home"))
        job.refresh_from_db()
        self.assertEqual(timezone.localtime(job.scheduled_start).date(), next_sunday())


class ReasonOnTheJobTests(JobsTestCase):
    def test_the_job_shows_each_time_it_was_booked_or_moved_outside_the_rules(self):
        self.client.post(reverse("appointment-new", args=[self.customer.pk]),
                         self.booking_data(next_sunday(), override_reason="Customer works weekdays"))
        job = Appointment.objects.get()
        later = next_sunday() + datetime.timedelta(days=7)
        self.client.post(reverse("appointment-edit", args=[job.pk]),
                         self.booking_data(later, crew_size="1", override_reason="Customer asked for the next Sunday"))
        page = self.client.get(reverse("appointment", args=[job.pk]))
        self.assertContains(page, "Booked off hours")
        self.assertContains(page, f"Booked for {next_sunday():%a, %b} {next_sunday().day}")
        self.assertContains(page, f"Moved for {later:%a, %b} {later.day}")
        self.assertContains(page, "Sunday is a closed day", count=2)
        self.assertContains(page, "Reason: Customer works weekdays")
        self.assertContains(page, "Reason: Customer asked for the next Sunday")
        self.assertContains(page, f"owner, {timezone.localdate():%b} {timezone.localdate().day}, {timezone.localdate().year}", count=2)

    def test_a_reason_logged_before_this_change_shows_too(self):
        day = next_sunday()
        job = booking.book(self.customer, self.vehicle, local(day), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1))
        # As Step 2 logged it: the rule's name in front, no action or start recorded.
        RuleOverride.objects.create(appointment=job, rules_broken=["Open day: Closed on Sundays"], reason="Sunday test booking", made_by=self.owner_user)
        page = self.client.get(reverse("appointment", args=[job.pk]))
        self.assertContains(page, "Open day: Closed on Sundays")
        self.assertContains(page, "Reason: Sunday test booking")

    def test_the_migration_fills_in_overrides_logged_before_this_change(self):
        import importlib

        from django.apps import apps

        migration = importlib.import_module("scheduling.migrations.0002_override_action_and_start")
        day = next_sunday()
        job = booking.book(self.customer, self.vehicle, local(day), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1))
        at_booking = RuleOverride.objects.create(appointment=job, rules_broken=["Open day: Closed on Sundays"], reason="Booked", start=None, action="booked")
        moved = RuleOverride.objects.create(appointment=job, rules_broken=["Open day: Closed on Sundays"], reason="Moved", start=None, action="booked")
        RuleOverride.objects.filter(pk=moved.pk).update(made_at=job.created_at + datetime.timedelta(hours=2))
        migration.fill_in(apps, None)
        at_booking.refresh_from_db()
        moved.refresh_from_db()
        self.assertEqual((at_booking.action, at_booking.start), ("booked", job.scheduled_start))
        self.assertEqual((moved.action, moved.start), ("moved", job.scheduled_start))
