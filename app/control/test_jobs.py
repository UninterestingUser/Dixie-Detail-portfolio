import datetime
from decimal import Decimal
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from appointments import booking
from appointments.models import Appointment, RecurringSeries
from pricebook.models import PricedLine
from pricebook.pricing import price_job
from staff.models import Assignment

from .fixtures import JobsTestCase, local


class ScheduleTests(JobsTestCase):
    def setUp(self):
        super().setUp()
        self.day = timezone.localdate() + datetime.timedelta(days=10)
        self.job = booking.book(self.customer, self.vehicle, local(self.day), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1))

    def test_the_day_list(self):
        page = self.client.get(reverse("schedule"), {"date": self.day.isoformat()})
        self.assertContains(page, "Pat Example")
        self.assertContains(page, "2019 Toyota RAV4, blue")
        self.assertContains(page, "8:00 AM to 1:00 PM")  # 4 hours of service, plus setup and breakdown
        self.assertContains(page, "Full Detail · $250.00")
        self.assertContains(self.client.get(reverse("schedule"), {"date": (self.day + datetime.timedelta(days=1)).isoformat()}), "No jobs on this day.")

    def test_the_week_list(self):
        page = self.client.get(reverse("schedule-week"), {"date": self.day.isoformat()})
        self.assertContains(page, self.day.strftime("%A, %b ") + str(self.day.day))
        self.assertContains(page, "Pat Example")

    def test_home_is_today(self):
        self.assertRedirects(self.client.get("/"), reverse("schedule"))
        self.assertEqual(self.client.get(reverse("schedule")).status_code, 200)


class LivePriceTests(JobsTestCase):
    def price(self, **changes):
        day = timezone.localdate() + datetime.timedelta(days=10)
        return self.client.post(reverse("appointment-price-new", args=[self.customer.pk]), self.booking_data(day, **changes))

    def test_the_price_comes_from_the_pricing_engine(self):
        job = price_job(self.full_detail, self.crossover, self.two_rows, condition_level=2, add_ons=[self.carpet])
        page = self.price(condition_level="2", add_ons=[self.carpet.pk])
        self.assertContains(page, f"${job.total_before_tax:,}")
        self.assertContains(page, "Condition level 2 (+10%)")
        self.assertContains(page, "Carpet Extraction")
        self.assertContains(page, "Service time")
        self.assertContains(page, "Time on site")

    def test_the_crew_changes_the_service_time_and_time_on_site(self):
        one = price_job(self.full_detail, self.crossover, self.two_rows, condition_level=1, crew_size=1)
        two = price_job(self.full_detail, self.crossover, self.two_rows, condition_level=1, crew_size=2)
        self.assertNotEqual(one.service_minutes, two.service_minutes)
        self.assertContains(self.price(crew_size="1"), f"{one.time_on_site.total_minutes / 60:g} hours".replace(".0 ", " "))
        page = self.price(crew_size="2")
        self.assertContains(page, "for 2 people")
        self.assertContains(page, "setup 15 min, breakdown 15 min")

    def test_a_missing_condition_level_is_explained(self):
        self.assertContains(self.price(condition_level=""), "Full Detail needs a condition level.")


class BookingTests(JobsTestCase):
    def setUp(self):
        super().setUp()
        self.day = timezone.localdate() + datetime.timedelta(days=14)

    def test_book_a_job(self):
        response = self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(self.day, condition_level="2", add_ons=[self.seats.pk], notes="Gate code 1234"))
        appointment = Appointment.objects.get()
        self.assertRedirects(response, reverse("appointment", args=[appointment.pk]))
        job = price_job(self.full_detail, self.crossover, self.two_rows, condition_level=2, add_ons=[self.seats])
        self.assertEqual(appointment.total_before_tax, job.total_before_tax)
        self.assertEqual([line.description for line in appointment.lines.all()], [line.description for line in job.lines])
        self.assertIsNotNone(appointment.quote)
        self.assertEqual((appointment.status, appointment.source, appointment.vehicle, appointment.service_address), ("booked", "owner", self.vehicle, self.address))
        self.assertEqual(timezone.localtime(appointment.scheduled_start).time(), datetime.time(8, 0))
        self.assertEqual(appointment.time_on_site_minutes, job.time_on_site.total_minutes)

    def test_any_date_can_be_booked(self):
        sunday = timezone.localdate() - datetime.timedelta(days=timezone.localdate().weekday() + 1)
        self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(sunday, time="19:30"))
        self.assertEqual(Appointment.objects.get().scheduled_start, timezone.make_aware(datetime.datetime.combine(sunday, datetime.time(19, 30))))

    def test_the_only_qualified_person_is_assigned_automatically(self):
        self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(self.day))
        self.assertEqual([a.staff_member for a in Assignment.objects.all()], [self.owner])

    def test_no_automatic_assignment_when_two_are_qualified(self):
        self.helper.authorizations.create(service=self.full_detail)
        self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(self.day))
        self.assertFalse(Assignment.objects.exists())

    def test_no_automatic_assignment_for_a_two_person_job(self):
        self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(self.day, crew_size="2"))
        self.assertFalse(Assignment.objects.exists())

    def test_automatic_assignment_is_a_setting(self):
        with mock.patch("staff.authorization.automatic_assignment", return_value=False):
            self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(self.day))
        self.assertFalse(Assignment.objects.exists())

    def test_a_maintenance_plan_as_a_single_visit(self):
        self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(self.day, service=self.monthly.pk, condition_level=""))
        appointment = Appointment.objects.get()
        self.assertIsNone(appointment.series)
        self.assertEqual(appointment.crew_size, 2)  # Monthly Maintenance defaults to two people

    def test_a_maintenance_plan_as_a_repeating_series(self):
        first = datetime.date(timezone.localdate().year + 1, 1, 31)
        response = self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(first, service=self.monthly.pk, condition_level="", repeat="monthly", visits="3", time="09:00"))
        series = RecurringSeries.objects.get()
        visits = list(series.appointments.order_by("scheduled_start"))
        self.assertRedirects(response, reverse("appointment", args=[visits[0].pk]))
        self.assertEqual([timezone.localtime(v.scheduled_start).date() for v in visits],
                         [first, datetime.date(first.year, 2, 28 if first.year % 4 else 29), datetime.date(first.year, 3, 31)])
        self.assertTrue(all(timezone.localtime(v.scheduled_start).time() == datetime.time(9, 0) for v in visits))
        self.assertEqual(len({v.quote_id for v in visits}), 3)
        self.assertEqual((series.frequency, series.starts_on, series.ends_on), ("monthly", first, datetime.date(first.year, 3, 31)))

    def test_quarterly_series_dates(self):
        self.assertEqual(
            booking.series_dates(datetime.date(2026, 11, 30), "quarterly", 3),
            [datetime.date(2026, 11, 30), datetime.date(2027, 2, 28), datetime.date(2027, 5, 30)],
        )

    def test_only_a_maintenance_plan_repeats(self):
        response = self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(self.day, repeat="monthly", visits="3"))
        self.assertContains(response, "Only a maintenance plan can repeat.")
        self.assertFalse(Appointment.objects.exists())


class ChangingAJobTests(JobsTestCase):
    def setUp(self):
        super().setUp()
        self.day = timezone.localdate() + datetime.timedelta(days=14)
        self.job = booking.book(self.customer, self.vehicle, local(self.day), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1))

    def test_every_job_screen_loads(self):
        for name in ("appointment", "appointment-edit"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=[self.job.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("appointment-new", args=[self.customer.pk])).status_code, 200)

    def test_changing_the_time_does_not_reprice(self):
        lines = list(self.job.lines.values_list("description", "amount"))
        quote = self.job.quote_id
        self.client.post(reverse("appointment-edit", args=[self.job.pk]), self.booking_data(self.day, time="09:30", crew_size="1"))
        self.job.refresh_from_db()
        self.assertEqual(timezone.localtime(self.job.scheduled_start).time(), datetime.time(9, 30))
        self.assertEqual((list(self.job.lines.values_list("description", "amount")), self.job.quote_id), (lines, quote))

    def test_changing_the_services_needs_a_reason_and_reprices(self):
        data = self.booking_data(self.day, condition_level="3", crew_size="1")
        self.assertContains(self.client.post(reverse("appointment-edit", args=[self.job.pk]), data), "Give a reason")
        self.job.refresh_from_db()
        self.assertEqual(self.job.total_before_tax, Decimal("250.00"))
        self.client.post(reverse("appointment-edit", args=[self.job.pk]), {**data, "reason": "Heavier soiling than described"})
        self.job.refresh_from_db()
        job = price_job(self.full_detail, self.crossover, self.two_rows, condition_level=3)
        self.assertEqual(self.job.total_before_tax, job.total_before_tax)
        self.assertEqual(self.job.service_minutes, job.service_minutes)
        self.assertTrue(self.job.history.filter(history_change_reason="Heavier soiling than described").exists())

    def test_status_booked_completed_canceled(self):
        for status in ("completed", "canceled", "booked"):
            self.client.post(reverse("appointment-status", args=[self.job.pk]), {"status": status})
            self.job.refresh_from_db()
            self.assertEqual(self.job.status, status)
            self.assertEqual(self.job.completed_at is not None, status == "completed")
        self.client.post(reverse("appointment-status", args=[self.job.pk]), {"status": "requested"})
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, "booked")

    def test_the_final_price_with_an_on_site_adjustment(self):
        url = reverse("appointment-final-price", args=[self.job.pk])
        self.assertContains(self.client.post(url, {"final_price": "230.00", "reason": ""}), "Give the reason", status_code=400)
        self.client.post(url, {"final_price": "230.00", "reason": "One seat left out"})
        self.assertEqual(self.job.total_before_tax, Decimal("230.00"))
        adjustment = self.job.lines.get(kind=PricedLine.Kind.ADJUSTMENT)
        self.assertEqual((adjustment.amount, adjustment.reason), (Decimal("-20.00"), "One seat left out"))
        self.client.post(url, {"final_price": "275.00", "reason": "Pet hair"})
        self.assertEqual(self.job.lines.filter(kind=PricedLine.Kind.ADJUSTMENT).count(), 1)
        self.assertEqual(self.job.total_before_tax, Decimal("275.00"))
        self.client.post(url, {"final_price": "250.00", "reason": ""})
        self.assertFalse(self.job.lines.filter(kind=PricedLine.Kind.ADJUSTMENT).exists())
        page = self.client.get(reverse("appointment", args=[self.job.pk]))
        self.assertContains(page, "Total before tax")
