"""Canceling a job and removing one created by mistake (decision 0095)."""

import datetime
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from appointments import booking
from appointments.models import Appointment, AppointmentLine, MatchFlag, RecurringSeries
from billing.methods import PaymentMethod
from billing.models import Payment
from pricebook.models import Quote
from scheduling import availability
from scheduling.models import RuleOverride
from staff.models import Assignment

from .fixtures import JobsTestCase, local, open_day


class CancelTestCase(JobsTestCase):
    def setUp(self):
        super().setUp()
        self.day = open_day(10)
        self.job = self.book(self.day)

    def book(self, day, hour=8):
        return booking.book(self.customer, self.vehicle, local(day, hour), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1),
                            address=self.address)

    def press(self, job=None, **data):
        return self.client.post(reverse("appointment-cancel", args=[(job or self.job).pk]), data)


class CancelButtonTests(CancelTestCase):
    def test_the_popup_is_on_booked_jobs_for_managers(self):
        page = self.client.get(reverse("appointment", args=[self.job.pk]))
        self.assertContains(page, 'data-opens="cancel-dialog">Cancel job</button>')
        for label in ("Customer canceled", "Dixie Detail canceled", "Created by mistake", "Keep the job"):
            self.assertContains(page, label)
        self.assertContains(page, "Remove this job for good? This can't be undone.")
        self.assertNotContains(page, "This visit only")  # not a series
        self.client.force_login(self.helper_user)
        self.assertNotContains(self.client.get(reverse("appointment", args=[self.job.pk])), "Cancel job")

    def test_customer_canceled(self):
        response = self.press(cancel="customer")
        self.assertRedirects(response, reverse("appointment", args=[self.job.pk]))
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.canceled_by, self.job.canceled_by_user), ("canceled", "customer", self.owner_user))
        self.assertAlmostEqual(self.job.canceled_at, timezone.now(), delta=datetime.timedelta(minutes=1))
        page = self.client.get(reverse("appointment", args=[self.job.pk]))
        self.assertContains(page, "Customer canceled")
        self.assertContains(page, "notice")
        self.assertNotContains(page, "Cancel job")

    def test_dixie_detail_canceled(self):
        self.press(cancel="business")
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.canceled_by), ("canceled", "business"))

    def test_only_a_manager_can_cancel(self):
        self.client.force_login(self.helper_user)
        self.press(cancel="customer")
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "booked")

    def test_created_by_mistake_asks_once_more(self):
        page = self.press(cancel="mistake")
        self.assertContains(page, "Remove this job for good?")
        self.assertContains(page, "This can't be undone.")
        self.assertTrue(Appointment.objects.filter(pk=self.job.pk).exists())
        response = self.press(remove="yes")
        self.assertRedirects(response, reverse("customer", args=[self.customer.pk]))
        self.assertFalse(Appointment.objects.filter(pk=self.job.pk).exists())

    def test_a_removed_job_leaves_nothing_behind(self):
        pk, quote = self.job.pk, self.job.quote_id
        Assignment.objects.create(appointment=self.job, staff_member=self.owner)
        MatchFlag.objects.create(appointment=self.job, customer=self.customer, field="name", booked_value="Patricia Example")
        RuleOverride.objects.create(appointment=self.job, rules_broken=["Sunday is a closed day"], reason="Invented")
        self.job.notes = "Changed once"
        self.job.save()
        booking.reprice(self.job, booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 2), "Heavier soiling")
        earlier_quote, quote = quote, Appointment.objects.get(pk=pk).quote_id
        self.press(remove="yes")
        self.assertFalse(Appointment.history.filter(id=pk).exists())
        self.assertFalse(AppointmentLine.history.filter(appointment_id=pk).exists())
        self.assertFalse(AppointmentLine.objects.filter(appointment_id=pk).exists())
        self.assertFalse(Assignment.objects.filter(appointment_id=pk).exists())
        self.assertFalse(MatchFlag.objects.filter(appointment_id=pk).exists())
        self.assertFalse(RuleOverride.objects.filter(appointment_id=pk).exists())
        self.assertFalse(Quote.objects.filter(pk__in=[earlier_quote, quote]).exists())

    def test_a_job_with_a_payment_cannot_be_removed(self):
        Payment.objects.create(appointment=self.job, method=PaymentMethod.CASH, amount=Decimal("50.00"), paid_at=timezone.now())
        response = self.press(remove="yes")
        self.assertRedirects(response, reverse("appointment", args=[self.job.pk]), fetch_redirect_response=False)
        self.assertTrue(Appointment.objects.filter(pk=self.job.pk).exists())
        page = self.client.get(reverse("appointment", args=[self.job.pk]))
        self.assertContains(page, "This job has a payment recorded, so it can&#x27;t be removed. Cancel it instead.")


class SeriesTests(CancelTestCase):
    def setUp(self):
        super().setUp()
        first = open_day(10)
        self.series = booking.book_series(self.customer, self.vehicle, local(first, 9),
                                          booking.JobInputs(self.monthly, self.crossover, self.two_rows), "monthly", 4)
        self.visits = list(self.series.appointments.order_by("scheduled_start"))

    def test_the_popup_asks_which_visits(self):
        page = self.client.get(reverse("appointment", args=[self.visits[1].pk]))
        self.assertContains(page, "This visit only")
        self.assertContains(page, "This and later visits")
        self.assertContains(page, "the 2 booked after it")

    def test_this_visit_only(self):
        self.press(self.visits[1], cancel="customer", visits="this")
        self.assertEqual([v.status for v in self.series.appointments.order_by("scheduled_start")], ["booked", "canceled", "booked", "booked"])

    def test_this_and_later_visits(self):
        self.press(self.visits[1], cancel="business", visits="later")
        visits = list(self.series.appointments.order_by("scheduled_start"))
        self.assertEqual([v.status for v in visits], ["booked", "canceled", "canceled", "canceled"])
        self.assertEqual({v.canceled_by for v in visits[1:]}, {"business"})
        self.series.refresh_from_db()
        self.assertTrue(self.series.active)
        self.press(self.visits[0], cancel="business", visits="this")
        self.series.refresh_from_db()
        self.assertFalse(self.series.active)

    def test_removing_this_and_later_visits(self):
        self.press(self.visits[2], remove="yes", visits="later")
        self.assertEqual(list(self.series.appointments.order_by("scheduled_start")), self.visits[:2])
        self.press(self.visits[0], remove="yes", visits="later")
        self.assertFalse(RecurringSeries.objects.filter(pk=self.series.pk).exists())


class CanceledTimeIsFreeTests(CancelTestCase):
    def test_a_canceled_job_frees_its_time_at_once(self):
        job = booking.job_to_place(booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1), self.day)
        start = local(self.day)
        self.assertTrue(availability.check(job, start))
        self.press(cancel="customer")
        self.assertEqual(availability.check(job, start), [])
        day = availability.open_times(job, self.day, self.day)[0]
        self.assertIn(timezone.localtime(start).time(), [slot.local_time for slot in day.open_slots])

    def test_a_canceled_job_leaves_the_schedule(self):
        self.press(cancel="customer")
        page = self.client.get(reverse("schedule"), {"view": "day", "date": self.day.isoformat()})
        self.assertNotContains(page, reverse("appointment", args=[self.job.pk]))


class CustomerPageTests(CancelTestCase):
    def test_canceled_jobs_are_listed_below_the_appointments(self):
        kept = self.book(open_day(20))
        self.job.scheduled_start = local(self.day, 8)
        self.job.save()
        Appointment.objects.filter(pk=self.job.pk).update(
            status="canceled", canceled_by="customer", canceled_by_user=self.owner_user,
            canceled_at=local(self.day, 8) - datetime.timedelta(days=2, hours=3),
        )
        page = self.client.get(reverse("customer", args=[self.customer.pk])).content.decode()
        self.assertLess(page.index(">Appointments<"), page.index(">Canceled jobs<"))
        canceled = page[page.index(">Canceled jobs<"):]
        self.assertIn("Customer canceled", canceled)
        self.assertIn("2 days, 3 hours&#x27; notice", canceled)
        self.assertIn("Full Detail", canceled)
        self.assertIn("Quoted $250.00", canceled)
        self.assertIn("2019 Toyota RAV4, blue", canceled)
        self.assertNotIn(reverse("appointment", args=[kept.pk]), canceled)

    def test_a_job_canceled_before_this_change_shows_canceled_with_no_detail(self):
        Appointment.objects.filter(pk=self.job.pk).update(status="canceled")
        page = self.client.get(reverse("customer", args=[self.customer.pk])).content.decode()
        canceled = page[page.index(">Canceled jobs<"):]
        self.assertIn('status-canceled">Canceled<', canceled)
        self.assertNotIn("notice", canceled)
        self.assertContains(self.client.get(reverse("appointment", args=[self.job.pk])), "<strong>Canceled.</strong>")


class NoticeFilterTests(JobsTestCase):
    def test_wording(self):
        from control.templatetags.control import notice_given

        hours = lambda n: datetime.timedelta(hours=n)  # noqa: E731
        self.assertEqual(notice_given(hours(-1)), "Canceled after the start time")
        self.assertEqual(notice_given(datetime.timedelta(minutes=20)), "Less than an hour's notice")
        self.assertEqual(notice_given(hours(1)), "1 hour's notice")
        self.assertEqual(notice_given(hours(5)), "5 hours' notice")
        self.assertEqual(notice_given(hours(24)), "1 day's notice")
        self.assertEqual(notice_given(hours(49)), "2 days, 1 hour's notice")
