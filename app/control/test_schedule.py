"""The Schedule screen's views (decision 0096)."""

import datetime

from django.urls import reverse
from django.utils import timezone

from appointments import booking
from appointments.models import Appointment
from scheduling.models import DateException
from staff.models import Assignment

from . import schedule_views
from .fixtures import JobsTestCase, local, open_day


def a_tuesday(weeks_ahead=2):
    today = timezone.localdate()
    return today + datetime.timedelta(days=(1 - today.weekday()) % 7 + 7 * weeks_ahead)


class ScheduleViewTestCase(JobsTestCase):
    def setUp(self):
        super().setUp()
        self.day = a_tuesday()
        self.job = self.book(self.day)

    def book(self, day, hour=8, minute=0):
        return booking.book(self.customer, self.vehicle, local(day, hour, minute),
                            booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1))

    def get(self, view=None, day=None, **params):
        if view:
            params["view"] = view
        if day:
            params["date"] = day.isoformat()
        return self.client.get(reverse("schedule"), params)


class ViewChoiceTests(ScheduleViewTestCase):
    def test_with_nothing_remembered_it_opens_in_schedule(self):
        page = self.get()
        self.assertEqual(page.context["view"], "schedule")
        self.assertNotIn(schedule_views.COOKIE, page.cookies)

    def test_the_last_view_used_is_remembered_in_a_cookie(self):
        page = self.get("week")
        cookie = page.cookies[schedule_views.COOKIE]
        self.assertEqual(cookie.value, "week")
        self.assertTrue(cookie["max-age"])
        self.assertEqual(self.get().context["view"], "week")
        self.get("month")
        self.assertEqual(self.get().context["view"], "month")

    def test_each_device_keeps_its_own_view(self):
        self.get("day")
        phone = self.client_class()
        phone.force_login(self.owner_user)
        self.assertEqual(phone.get(reverse("schedule")).context["view"], "schedule")

    def test_an_unknown_view_is_the_schedule_list(self):
        page = self.get("year")
        self.assertEqual(page.context["view"], "schedule")
        self.assertNotIn(schedule_views.COOKIE, page.cookies)

    def test_the_menu_offers_every_view(self):
        page = self.get("day", self.day)
        for label in ("Schedule", "Day", "3 Days", "Week", "Month"):
            self.assertContains(page, f">{label}</a>")
        self.assertContains(page, 'class="view-menu"')

    def test_every_view_has_today_previous_and_next(self):
        for view, step in (("day", 1), ("3day", 3), ("week", 7), ("schedule", 7)):
            with self.subTest(view=view):
                page = self.get(view, self.day)
                anchor = schedule_views.week_start(self.day) if view == "week" else self.day
                self.assertContains(page, f'href="?view={view}">Today</a>')
                self.assertContains(page, f'data-swipe="previous" href="?view={view}&amp;date={(anchor - datetime.timedelta(days=step)).isoformat()}"')
                self.assertContains(page, f'data-swipe="next" href="?view={view}&amp;date={(anchor + datetime.timedelta(days=step)).isoformat()}"')
        page = self.get("month", datetime.date(2027, 1, 15))
        self.assertContains(page, 'data-swipe="previous" href="?view=month&amp;date=2026-12-01"')
        self.assertContains(page, 'data-swipe="next" href="?view=month&amp;date=2027-02-01"')

    def test_home_is_the_schedule(self):
        self.assertRedirects(self.client.get("/"), reverse("schedule"))


class ScheduleListTests(ScheduleViewTestCase):
    def test_days_with_jobs_from_the_day_on_and_today_even_when_empty(self):
        later = self.book(self.day + datetime.timedelta(days=7))
        page = self.get("schedule")
        days = [day for day, _ in page.context["days"]]
        self.assertEqual(days, [timezone.localdate(), self.day, self.day + datetime.timedelta(days=7)])
        self.assertContains(page, "No jobs today.")
        self.assertContains(page, "Pat Example")
        self.assertContains(page, reverse("appointment", args=[later.pk]))
        self.assertContains(page, "No later jobs booked.")
        # Earlier days load above as it scrolls up.
        self.assertContains(page, f'hx-get="{reverse("schedule-more")}?before={timezone.localdate().isoformat()}"')

    def test_scrolling_down_loads_later_days_and_up_loads_earlier_ones(self):
        for weeks in range(1, schedule_views.CHUNK + 3):
            self.book(self.day + datetime.timedelta(days=7 * weeks))
        page = self.get("schedule")
        self.assertEqual(len(page.context["days"]), schedule_views.CHUNK + 1)  # today, then CHUNK days with jobs
        after = page.context["after"]
        more = self.client.get(reverse("schedule-more"), {"after": after.isoformat()})
        self.assertEqual(len(more.context["days"]), 3)
        self.assertContains(more, "No later jobs booked.")
        earlier = self.client.get(reverse("schedule-more"), {"before": after.isoformat()})
        self.assertEqual(earlier.context["days"][-1][0], after - datetime.timedelta(days=1))
        self.assertEqual(len(earlier.context["days"]), schedule_views.CHUNK)
        self.assertContains(earlier, "?before=")

    def test_past_days_load_upward_without_end(self):
        past = timezone.localdate() - datetime.timedelta(days=30)
        old = Appointment.objects.create(customer=self.customer, vehicle=self.vehicle, scheduled_start=local(past, 9),
                                         status=Appointment.Status.COMPLETED, source=Appointment.Source.OWNER)
        earlier = self.client.get(reverse("schedule-more"), {"before": timezone.localdate().isoformat()})
        self.assertEqual([day for day, _ in earlier.context["days"]], [past])
        self.assertContains(earlier, reverse("appointment", args=[old.pk]))
        self.assertContains(earlier, "No earlier jobs.")

    def test_days_with_no_jobs_are_skipped(self):
        page = self.get("schedule", self.day - datetime.timedelta(days=1))
        self.assertEqual([day for day, _ in page.context["days"]], [self.day])


class TimeGridTests(ScheduleViewTestCase):
    def test_the_day_view_shows_each_job_as_a_block(self):
        page = self.get("day", self.day)
        self.assertContains(page, 'class="timegrid-job status-booked"')
        self.assertContains(page, "Pat Example")
        self.assertContains(page, "2019 Toyota RAV4, blue")
        self.assertContains(page, "Full Detail")
        self.assertContains(page, "8:00 AM to 1:00 PM")
        self.assertContains(page, "No staff assigned")
        self.assertContains(page, reverse("appointment", args=[self.job.pk]))
        column = page.context["columns"][0]
        block = column.blocks[0]
        self.assertEqual((block.start, block.end, block.lanes), (8 * 60, 13 * 60, 1))

    def test_the_hours_cover_the_working_day_and_stretch_to_fit(self):
        page = self.get("day", self.day)
        self.assertEqual(page.context["hours"][0], datetime.time(8))
        late = self.book(self.day + datetime.timedelta(days=1), 19, 30)
        late.scheduled_start = local(self.day, 19, 30)
        late.save()
        early = self.book(self.day + datetime.timedelta(days=2))
        early.scheduled_start = local(self.day, 6, 15)
        early.save()
        hours = self.get("day", self.day).context["hours"]
        self.assertEqual((hours[0], hours[-1]), (datetime.time(6), datetime.time(23)))  # the 7:30 PM job runs to 12:30 AM, cut at midnight

    def test_three_days_and_the_week_from_sunday(self):
        page = self.get("3day", self.day)
        self.assertEqual([c.day for c in page.context["columns"]], [self.day + datetime.timedelta(days=n) for n in range(3)])
        page = self.get("week", self.day)
        days = [c.day for c in page.context["columns"]]
        self.assertEqual(days[0].weekday(), 6)  # Sunday
        self.assertEqual(days[0], self.day - datetime.timedelta(days=2))
        self.assertEqual(len(days), 7)

    def test_closed_days_are_shaded(self):
        DateException.objects.create(date=self.day + datetime.timedelta(days=1), kind=DateException.Kind.CLOSED, reason="Truck in the shop")
        columns = self.get("week", self.day).context["columns"]
        closed = {c.day: c.closed for c in columns if c.closed}
        self.assertEqual(set(closed), {self.day - datetime.timedelta(days=2), self.day + datetime.timedelta(days=1)})
        self.assertIn("Closed: Truck in the shop", closed[self.day + datetime.timedelta(days=1)])
        self.assertContains(self.get("week", self.day), 'class="timegrid-column closed')

    def test_today_has_a_line_at_the_current_time(self):
        page = self.get("week", timezone.localdate())
        self.assertContains(page, 'class="now-line"', count=1)
        self.assertNotContains(self.get("week", self.day + datetime.timedelta(days=14)), 'class="now-line"')

    def test_overlapping_jobs_sit_side_by_side(self):
        other = self.book(self.day + datetime.timedelta(days=1))
        other.scheduled_start = local(self.day, 10)
        other.save()
        blocks = self.get("day", self.day).context["columns"][0].blocks
        self.assertEqual([(b.lane, b.lanes) for b in blocks], [(0, 2), (1, 2)])

    def test_booked_and_completed_jobs_look_different_and_staff_shows(self):
        self.job.status = Appointment.Status.COMPLETED
        self.job.save()
        Assignment.objects.create(appointment=self.job, staff_member=self.owner)
        page = self.get("day", self.day)
        self.assertContains(page, 'class="timegrid-job status-completed"')
        self.assertNotContains(page, "No staff assigned")


class MonthTests(ScheduleViewTestCase):
    def test_a_grid_of_weeks_from_sunday(self):
        page = self.get("month", self.day)
        weeks = page.context["weeks"]
        first = self.day.replace(day=1)
        self.assertEqual(weeks[0][0]["day"], schedule_views.week_start(first))
        self.assertTrue(all(week[0]["day"].weekday() == 6 for week in weeks))
        self.assertContains(page, self.day.strftime("%B %Y"))
        cell = next(c for week in weeks for c in week if c["day"] == self.day)
        self.assertEqual(cell["jobs"], [self.job])

    def test_a_day_with_too_many_shows_more_and_opens_in_day_view(self):
        for hour in (10, 12, 14):
            job = self.book(self.day + datetime.timedelta(days=1))
            job.scheduled_start = local(self.day, hour)
            job.save()
        page = self.get("month", self.day)
        self.assertContains(page, "+2 more")
        self.assertContains(page, f'class="month-more" href="?view=day&amp;date={self.day.isoformat()}"')
        self.assertContains(page, f'class="month-date" href="?view=day&amp;date={self.day.isoformat()}"')


class CanceledJobsLeaveTheScheduleTests(ScheduleViewTestCase):
    def test_a_canceled_job_is_on_no_view(self):
        booking.cancel(self.job, "customer", self.owner_user)
        url = reverse("appointment", args=[self.job.pk])
        for view in ("schedule", "day", "3day", "week", "month"):
            with self.subTest(view=view):
                self.assertNotContains(self.get(view, self.day), url)


class OpenDayFixtureTests(JobsTestCase):
    def test_open_day_is_never_sunday(self):
        self.assertNotEqual(open_day(0).weekday(), 6)
