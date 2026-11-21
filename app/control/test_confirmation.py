"""Unconfirmed jobs in the control app (decision 0112): yellow in every
schedule view and on the job page with the reason, the banner of those
starting soon, "Call to confirm" on "needs you", Mark confirmed for
managers, the settings, and every control app booking confirmed."""

import datetime

from django.urls import reverse
from django.utils import timezone

from appointments import booking
from appointments.models import Appointment
from scheduling.models import SchedulingSettings

from . import needs_you
from .fixtures import JobsTestCase, local, open_day


class UnconfirmedTestCase(JobsTestCase):
    def book(self, day=None, hour=8):
        inputs = booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1)
        return booking.book(self.customer, self.vehicle, local(day or open_day(10), hour), inputs, address=self.address)

    def unconfirmed(self, job, reason=Appointment.UnconfirmedReason.CALL):
        Appointment.objects.filter(pk=job.pk).update(
            confirmation=Appointment.Confirmation.UNCONFIRMED, unconfirmed_reason=reason, confirmed_how="", confirmed_at=None,
        )
        job.refresh_from_db()
        return job


class ControlAppBookingTests(UnconfirmedTestCase):
    def test_a_booking_made_in_the_control_app_is_confirmed(self):
        job = self.book()
        self.assertEqual(job.confirmation, Appointment.Confirmation.CONFIRMED)
        self.assertEqual(job.confirmed_how, Appointment.ConfirmedHow.CONTROL_APP)
        self.assertIsNotNone(job.confirmed_at)

    def test_a_website_request_booked_in_the_control_app_is_confirmed(self):
        day = open_day(10)
        quote = booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1).quote(on=day, address=self.address)
        job = booking.book_request(quote, self.customer, self.vehicle, local(day, 8), address=self.address, user=self.owner_user)
        self.assertEqual(job.source, Appointment.Source.WEBSITE)
        self.assertEqual((job.confirmation, job.confirmed_how), (Appointment.Confirmation.CONFIRMED, Appointment.ConfirmedHow.CONTROL_APP))
        self.assertEqual(job.confirmed_by, self.owner_user)


class YellowTests(UnconfirmedTestCase):
    def test_every_schedule_view_shows_it_yellow_with_the_reason(self):
        day = open_day(10)
        job = self.unconfirmed(self.book(day))
        for view in ("schedule", "day", "3day", "week", "month"):
            with self.subTest(view):
                page = self.client.get(reverse("schedule"), {"view": view, "date": day.isoformat()})
                self.assertContains(page, " unconfirmed")
                if view == "month":
                    self.assertContains(page, 'title="Unconfirmed: call to confirm"')
                else:
                    self.assertContains(page, "Unconfirmed: call to confirm")
        page = self.client.get(reverse("appointment", args=[job.pk]))
        self.assertContains(page, '<div class="heading unconfirmed">', html=False)
        self.assertContains(page, "Not confirmed yet")
        self.assertContains(page, "Unconfirmed: call to confirm")
        self.assertContains(page, f"tel:+1{self.customer.mobile}")

    def test_a_confirmed_job_is_not_yellow_and_says_how(self):
        day = open_day(10)
        job = self.book(day)
        page = self.client.get(reverse("schedule"), {"view": "schedule", "date": day.isoformat()})
        self.assertNotContains(page, "Unconfirmed:")
        page = self.client.get(reverse("appointment", args=[job.pk]))
        self.assertNotContains(page, "Not confirmed yet")
        self.assertContains(page, "Confirmed: booked in the control app")


class BannerTests(UnconfirmedTestCase):
    def test_the_banner_lists_unconfirmed_jobs_within_48_hours(self):
        now = timezone.now()
        soon = self.unconfirmed(self.book())
        Appointment.objects.filter(pk=soon.pk).update(scheduled_start=now + datetime.timedelta(hours=30))
        later = self.unconfirmed(self.book(open_day(20)), Appointment.UnconfirmedReason.TEXT_REPLY)
        Appointment.objects.filter(pk=later.pk).update(scheduled_start=now + datetime.timedelta(hours=60))
        page = self.client.get(reverse("schedule"), {"view": "month"})
        self.assertContains(page, "Not confirmed, starting within 48 hours")
        banner = page.content.decode().split('class="unconfirmed-banner"')[1].split("</section>")[0]
        self.assertIn(reverse("appointment", args=[soon.pk]), banner)
        self.assertNotIn(reverse("appointment", args=[later.pk]), banner)
        self.assertIn(f"tel:+1{self.customer.mobile}", banner)
        self.assertIn("Mark confirmed", banner)

    def test_the_hours_are_a_setting(self):
        now = timezone.now()
        later = self.unconfirmed(self.book(open_day(20)), Appointment.UnconfirmedReason.TEXT_REPLY)
        Appointment.objects.filter(pk=later.pk).update(scheduled_start=now + datetime.timedelta(hours=60))
        SchedulingSettings.objects.filter(pk=1).update(unconfirmed_banner_hours=72)
        page = self.client.get(reverse("schedule"))
        self.assertContains(page, "Not confirmed, starting within 72 hours")
        self.assertContains(page, "Waiting for a text reply")

    def test_no_banner_without_unconfirmed_jobs(self):
        self.book()
        self.assertNotContains(self.client.get(reverse("schedule")), "unconfirmed-banner")

    def test_the_settings_are_on_the_scheduling_settings_screen(self):
        page = self.client.get("/settings/scheduling/")
        for label in ("Unconfirmed bookings per new customer&#x27;s number", "Unconfirmed bookings from new customers at once",
                      "List unconfirmed jobs starting within, hours"):
            self.assertContains(page, label)


class NeedsYouTests(UnconfirmedTestCase):
    def test_a_job_with_no_text_consent_is_call_to_confirm(self):
        job = self.unconfirmed(self.book())
        [item] = needs_you.items()
        self.assertEqual((item.kind, item.title, item.appointment_id), ("call_to_confirm", "Call to confirm: Pat Example", job.pk))
        page = self.client.get(reverse("schedule"))
        section = page.content.decode().split('class="needs-you"')[1].split("</section>")[0]
        self.assertIn("Call to confirm: Pat Example", section)
        self.assertIn(f"tel:+1{self.customer.mobile}", section)
        self.assertIn(reverse("appointment-confirm", args=[job.pk]), section)
        self.assertIn("Mark confirmed", section)

    def test_a_job_waiting_for_a_text_reply_is_not_an_item(self):
        self.unconfirmed(self.book(), Appointment.UnconfirmedReason.TEXT_REPLY)
        self.assertEqual(needs_you.items(), [])

    def test_a_confirmed_or_canceled_job_leaves_the_list(self):
        job = self.unconfirmed(self.book())
        Appointment.objects.filter(pk=job.pk).update(status=Appointment.Status.CANCELED)
        self.assertEqual(needs_you.items(), [])


class MarkConfirmedTests(UnconfirmedTestCase):
    def test_a_manager_marks_it_confirmed_with_a_note(self):
        job = self.unconfirmed(self.book())
        response = self.client.post(reverse("appointment-confirm", args=[job.pk]), {"note": "Confirmed by phone", "next": "/schedule/"})
        self.assertRedirects(response, "/schedule/", fetch_redirect_response=False)
        job.refresh_from_db()
        self.assertEqual(job.confirmation, Appointment.Confirmation.CONFIRMED)
        self.assertEqual((job.confirmed_how, job.confirmed_by, job.confirmation_note), (Appointment.ConfirmedHow.MANAGER, self.owner_user, "Confirmed by phone"))
        self.assertEqual(job.history.first().history_change_reason, "Confirmed: marked by a manager")
        self.assertEqual(needs_you.items(), [])
        page = self.client.get(reverse("appointment", args=[job.pk]))
        self.assertContains(page, "Confirmed: marked by a manager")
        self.assertContains(page, "Note: Confirmed by phone")

    def test_only_a_manager_can(self):
        job = self.unconfirmed(self.book())
        self.client.force_login(self.helper_user)
        self.client.post(reverse("appointment-confirm", args=[job.pk]))
        job.refresh_from_db()
        self.assertEqual(job.confirmation, Appointment.Confirmation.UNCONFIRMED)
        self.assertNotContains(self.client.get(reverse("appointment", args=[job.pk])), "Mark confirmed")

    def test_it_goes_back_only_to_this_site(self):
        job = self.unconfirmed(self.book())
        response = self.client.post(reverse("appointment-confirm", args=[job.pk]), {"next": "https://example.com/"})
        self.assertRedirects(response, reverse("appointment", args=[job.pk]), fetch_redirect_response=False)
