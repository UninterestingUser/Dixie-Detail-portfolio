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

from scheduling.models import RuleOverride

from .fixtures import JobsTestCase, local, open_day


class LivePriceTests(JobsTestCase):
    def price(self, **changes):
        day = open_day(10)
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
        self.day = open_day(14)

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

    def test_any_date_can_be_booked_by_a_manager_with_a_reason(self):
        sunday = timezone.localdate() - datetime.timedelta(days=timezone.localdate().weekday() + 1)
        data = self.booking_data(sunday, time="19:30")
        page = self.client.post(reverse("appointment-new", args=[self.customer.pk]), data)
        self.assertContains(page, "Sunday is a closed day")
        self.assertContains(page, "Too soon")
        self.assertContains(page, "Booking off hours is allowed. Give the reason below and it will be logged with the job.")
        self.assertContains(page, "Give the reason for booking off hours.")
        self.assertFalse(Appointment.objects.exists())
        self.client.post(reverse("appointment-new", args=[self.customer.pk]), {**data, "override_reason": "Entered late"})
        appointment = Appointment.objects.get()
        self.assertEqual(appointment.scheduled_start, timezone.make_aware(datetime.datetime.combine(sunday, datetime.time(19, 30))))
        override = RuleOverride.objects.get()
        self.assertEqual((override.appointment, override.reason, override.made_by, override.action), (appointment, "Entered late", self.owner_user, "booked"))
        self.assertEqual(override.start, appointment.scheduled_start)
        self.assertIn("Sunday is a closed day", override.rules_broken)

    def test_only_a_manager_can_book_outside_the_rules(self):
        self.client.force_login(self.helper_user)
        data = self.booking_data(self.day, time="10:15", override_reason="Customer asked")
        page = self.client.post(reverse("appointment-new", args=[self.customer.pk]), data)
        self.assertContains(page, "10:15 AM is not a start time")
        self.assertContains(page, "Only a manager can book off hours. Pick another time.")
        self.assertNotContains(page, 'name="override_reason"')
        self.assertFalse(Appointment.objects.exists())

    def test_a_booking_inside_the_rules_needs_no_reason(self):
        self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(self.day, time="08:30"))
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertFalse(RuleOverride.objects.exists())

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
        # The visits are more than 90 days ahead, past the furthest bookable date.
        data = self.booking_data(first, service=self.monthly.pk, condition_level="", repeat="monthly", visits="3", time="09:00")
        self.assertContains(self.client.post(reverse("appointment-new", args=[self.customer.pk]), data), "Too far ahead")
        response = self.client.post(reverse("appointment-new", args=[self.customer.pk]), {**data, "override_reason": "Booked for next year"})
        series = RecurringSeries.objects.get()
        self.assertEqual(RuleOverride.objects.filter(appointment__series=series).count(), 3)
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
        self.day = open_day(14)
        self.job = booking.book(self.customer, self.vehicle, local(self.day), booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1))

    def test_every_job_screen_loads(self):
        for name in ("appointment", "appointment-edit"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=[self.job.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("appointment-new", args=[self.customer.pk])).status_code, 200)

    def test_changing_the_time_does_not_reprice(self):
        lines = list(self.job.lines.values_list("description", "amount"))
        quote = self.job.quote_id
        self.client.post(reverse("appointment-edit", args=[self.job.pk]), self.booking_data(self.day, time="09:00", crew_size="1"))
        self.job.refresh_from_db()
        self.assertEqual(timezone.localtime(self.job.scheduled_start).time(), datetime.time(9, 0))
        self.assertEqual((list(self.job.lines.values_list("description", "amount")), self.job.quote_id), (lines, quote))

    def test_moving_a_job_outside_the_rules_needs_a_reason(self):
        data = self.booking_data(self.day, time="09:30", crew_size="1")
        self.assertContains(self.client.post(reverse("appointment-edit", args=[self.job.pk]), data), "9:30 AM is not a start time")
        self.job.refresh_from_db()
        self.assertEqual(timezone.localtime(self.job.scheduled_start).time(), datetime.time(8, 0))
        self.client.post(reverse("appointment-edit", args=[self.job.pk]), {**data, "override_reason": "Customer's gate opens at 9:30"})
        self.job.refresh_from_db()
        self.assertEqual(timezone.localtime(self.job.scheduled_start).time(), datetime.time(9, 30))
        override = self.job.rule_overrides.get()
        self.assertEqual((override.reason, override.action, override.start), ("Customer's gate opens at 9:30", "moved", self.job.scheduled_start))

    def test_changing_only_the_notes_is_not_checked(self):
        self.job.scheduled_start = local(self.day, 10, 15)
        self.job.service_address = self.address
        self.job.save()
        self.client.post(reverse("appointment-edit", args=[self.job.pk]), self.booking_data(self.day, time="10:15", crew_size="1", notes="Dog in the yard"))
        self.job.refresh_from_db()
        self.assertEqual(self.job.notes, "Dog in the yard")

    def test_changing_the_services_needs_a_reason_and_reprices(self):
        data = self.booking_data(self.day, condition_level="2", crew_size="1")
        self.assertContains(self.client.post(reverse("appointment-edit", args=[self.job.pk]), data), "Give a reason")
        self.job.refresh_from_db()
        self.assertEqual(self.job.total_before_tax, Decimal("250.00"))
        self.client.post(reverse("appointment-edit", args=[self.job.pk]), {**data, "reason": "Heavier soiling than described"})
        self.job.refresh_from_db()
        job = price_job(self.full_detail, self.crossover, self.two_rows, condition_level=2)
        self.assertEqual(self.job.total_before_tax, job.total_before_tax)
        self.assertEqual(self.job.service_minutes, job.service_minutes)
        self.assertTrue(self.job.history.filter(history_change_reason="Heavier soiling than described").exists())

    def test_status_booked_and_completed(self):
        for status in ("completed", "booked"):
            self.client.post(reverse("appointment-status", args=[self.job.pk]), {"status": status})
            self.job.refresh_from_db()
            self.assertEqual(self.job.status, status)
            self.assertEqual(self.job.completed_at is not None, status == "completed")
        for status in ("requested", "canceled"):
            self.client.post(reverse("appointment-status", args=[self.job.pk]), {"status": status})
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


class AddOnRuleTests(JobsTestCase):
    """The booking form applies the pricebook's add-on rules, with a
    manager's override and a reason, logged like the scheduling rules
    (decision 0106)."""

    def setUp(self):
        super().setUp()
        self.day = open_day(14)
        from pricebook.models import Service

        self.exterior = Service.objects.get(name="Exterior Only")
        self.headlights = Service.objects.get(name="Headlight Restoration")

    def post(self, **changes):
        data = self.booking_data(self.day, **{"service": self.exterior.pk, "condition_level": "", "add_ons": [self.seats.pk], **changes})
        return self.client.post(reverse("appointment-new", args=[self.customer.pk]), data)

    def test_headlight_restoration_is_an_add_on_on_the_form(self):
        page = self.client.get(reverse("appointment-new", args=[self.customer.pk]))
        self.assertContains(page, f'value="{self.headlights.pk}"')
        self.assertNotContains(page, f'<option value="{self.headlights.pk}">Headlight Restoration</option>', html=False)
        self.post(add_ons=[self.headlights.pk])
        appointment = Appointment.objects.get()
        self.assertEqual([line.kind for line in appointment.lines.all()], [PricedLine.Kind.SERVICE, PricedLine.Kind.ADD_ON])
        self.assertFalse(RuleOverride.objects.exists())

    def test_a_manager_adds_one_outside_the_rules_with_a_reason_that_is_logged(self):
        page = self.post()
        self.assertContains(page, "Seat Extraction doesn&#x27;t go with Exterior Only: give the reason for adding it.")
        self.assertFalse(Appointment.objects.exists())
        self.post(add_on_reason="Customer's dog got into the back seat")
        appointment = Appointment.objects.get()
        self.assertIn("Seat Extraction", [line.description for line in appointment.lines.all()])
        override = RuleOverride.objects.get(appointment=appointment)
        self.assertEqual(override.action, RuleOverride.Action.ADD_ONS)
        self.assertEqual(override.rules_broken, ["Seat Extraction doesn't go with Exterior Only"])
        self.assertEqual(override.reason, "Customer's dog got into the back seat")
        self.assertEqual(override.made_by, self.owner_user)
        # The job page shows it with the other overrides.
        self.assertContains(self.client.get(reverse("appointment", args=[appointment.pk])), "Customer&#x27;s dog got into the back seat")

    def test_anyone_else_picks_another(self):
        self.helper.authorizations.create(service=self.exterior)
        self.client.force_login(self.helper_user)
        page = self.post(add_on_reason="Trying anyway")
        self.assertContains(page, "Pick another, or ask a manager to add it with a reason.")
        self.assertNotContains(page, 'name="add_on_reason"')
        self.assertFalse(Appointment.objects.exists())

    def test_the_live_price_names_the_rule(self):
        page = self.client.post(reverse("appointment-price-new", args=[self.customer.pk]),
                                self.booking_data(self.day, service=self.exterior.pk, condition_level="", add_ons=[self.seats.pk]))
        self.assertContains(page, "Seat Extraction doesn&#x27;t go with Exterior Only")

    def test_changing_a_job_booked_with_an_override_keeps_its_add_ons(self):
        self.post(add_on_reason="Asked for it")
        appointment = Appointment.objects.get()
        data = self.booking_data(self.day, service=self.exterior.pk, condition_level="", add_ons=[self.seats.pk], notes="Gate code 1234", reason="")
        response = self.client.post(reverse("appointment-edit", args=[appointment.pk]), data)
        self.assertEqual(response.status_code, 302, response.content)
        appointment.refresh_from_db()
        self.assertEqual(appointment.notes, "Gate code 1234")
        self.assertEqual(RuleOverride.objects.filter(appointment=appointment).count(), 1)


class DefaultStaffBookingTests(JobsTestCase):
    def setUp(self):
        super().setUp()
        from scheduling.models import SchedulingSettings

        self.day = open_day(14)
        SchedulingSettings.get()
        SchedulingSettings.objects.filter(pk=1).update(default_staff=self.owner)

    def test_a_control_app_booking_gets_the_default_staff_whoever_else_qualifies(self):
        self.helper.authorizations.create(service=self.full_detail)
        response = self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(self.day), follow=True)
        self.assertEqual([a.staff_member for a in Assignment.objects.all()], [self.owner])
        self.assertContains(response, "Assigned Owner Person, the default staff. Change the crew on the job if needed.")

    def test_a_two_person_job_gets_the_default_staff_and_room_for_one_more(self):
        self.client.post(reverse("appointment-new", args=[self.customer.pk]), self.booking_data(self.day, crew_size="2"))
        appointment = Appointment.objects.get()
        self.assertEqual([a.staff_member for a in appointment.assignments.all()], [self.owner])
        self.assertEqual(appointment.crew_size, 2)
