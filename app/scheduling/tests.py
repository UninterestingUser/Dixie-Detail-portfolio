"""The scheduling settings, the availability check's six conditions, the
manager override, settings changes and the open-times view."""

import datetime
import time
from decimal import Decimal
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from appointments import booking
from appointments.models import Appointment
from control.fixtures import JobsTestCase
from customers.models import Address
from geo.drive import Drive
from pricebook.models import Service
from vehicles.models import Vehicle, VehicleClass

from . import availability
from .availability import Job, check, open_times
from .models import AffectedJob, DateException, OpenWeekday, SchedulingSettings, SharedService, TimeOffEvent, launch_rules

UTC = datetime.timezone.utc


def eastern(day, hour, minute=0, fold=0):
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour, minute)).replace(fold=fold))


# A Tuesday, and "now" a week before it, so the day is inside the notice and
# the furthest date.
TUESDAY = datetime.date(2026, 12, 8)
NOW = eastern(datetime.date(2026, 12, 1), 12)


def rules_text(reasons):
    return [str(reason) for reason in reasons]


class SchedulingTestCase(JobsTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.motorcycle = Service.objects.get(name="Motorcycle Detail")
        cls.motorcycles = VehicleClass.objects.get(name="Motorcycles")
        cls.bike = Vehicle.objects.create(customer=cls.customer, year=2020, make="Honda", model="Gold Wing", vehicle_class=cls.motorcycles)
        cls.second = Address.objects.create(customer=cls.customer, line1="200 Sample Rd", city="Calhoun", state="TN", zip_code="37309")

    def setUp(self):
        super().setUp()
        SchedulingSettings.get()  # seeded from data/booking-rules.yaml

    def settings(self, **values):
        row = SchedulingSettings.get()
        for name, value in values.items():
            setattr(row, name, value)
        row.save()
        return row

    def book(self, service, start, minutes=None, address=None, status=Appointment.Status.BOOKED):
        """Book a job, with its time on site set to minutes when given."""
        if service == self.motorcycle:
            inputs = booking.JobInputs(service, self.motorcycles)
            vehicle = self.bike
        else:
            inputs = booking.JobInputs(service, self.crossover, self.two_rows, 1 if service.condition_applies else None)
            vehicle = self.vehicle
        appointment = booking.book(self.customer, vehicle, start, inputs, address=address)
        if minutes is not None:
            setup = appointment.setup_minutes
            appointment.service_minutes = minutes - setup - appointment.breakdown_minutes
            appointment.save()
        if status != Appointment.Status.BOOKED:
            appointment.status = status
            appointment.save()
        return appointment

    def job(self, service=None, minutes=180, point=None):
        service = service or self.monthly
        return Job(minutes, service.pk, service.name, point)

    def located(self, address, latitude, longitude):
        address.latitude, address.longitude = Decimal(latitude), Decimal(longitude)
        address.save()
        return address.point


class SettingsSeedTests(SchedulingTestCase):
    def test_the_settings_are_seeded_from_booking_rules(self):
        rules = launch_rules()
        row = SchedulingSettings.get()
        self.assertEqual(
            (row.minimum_notice_days, row.furthest_bookable_days, row.setup_minutes_one_person, row.breakdown_minutes_one_person,
             row.jobs_per_day, row.minimum_gap_minutes, row.round_start_up_to_minutes, row.time_off_buffer_minutes),
            (rules["minimum_notice_days"], rules["furthest_bookable_days"], 30, 30, 1, 30, 15, 0),
        )
        self.assertEqual(row.round_start_up_to_minutes, 15)  # confirmed by the owner on 2026-11-04 (decision 0093)
        days = list(OpenWeekday.objects.order_by("weekday"))
        self.assertEqual([day.is_open for day in days], [True] * 6 + [False])
        self.assertEqual(days[0].start_times, [datetime.time(8), datetime.time(8, 30), datetime.time(9)])
        self.assertEqual((days[5].opens_at, days[5].closes_at), (datetime.time(8), datetime.time(18)))
        self.assertEqual(dict(SharedService.objects.values_list("service__name", "max_per_day")),
                         {"Monthly Maintenance": 2, "Motorcycle Detail": 2})

    def test_setup_and_breakdown_come_from_the_settings(self):
        from core.scheduling import time_on_site

        self.assertEqual(time_on_site(300, 1).total_minutes, 360)
        self.settings(setup_minutes_one_person=60)
        self.assertEqual(time_on_site(300, 1).setup_minutes, 60)
        self.assertEqual(time_on_site(300, 1).total_minutes, 390)


class OpenDayTests(SchedulingTestCase):
    """Condition 1."""

    def test_a_launch_weekday_is_open_at_its_start_times(self):
        day = open_times(self.job(), TUESDAY, TUESDAY, now=NOW)[0]
        self.assertEqual([slot.local_time for slot in day.open_slots], [datetime.time(8), datetime.time(8, 30), datetime.time(9)])

    def test_sunday_is_closed(self):
        sunday = TUESDAY - datetime.timedelta(days=2)
        day = open_times(self.job(), sunday, sunday, now=NOW)[0]
        self.assertEqual((rules_text(day.reasons), day.slots), (["Open day: Sunday is a closed day"], []))

    def test_a_date_exception_closes_the_day(self):
        DateException.objects.create(date=TUESDAY, kind=DateException.Kind.CLOSED, reason="Family wedding")
        self.assertEqual(rules_text(check(self.job(), eastern(TUESDAY, 8), now=NOW)), ["Open day: Closed: Family wedding"])

    def test_an_all_day_time_off_event_closes_every_day_it_covers(self):
        TimeOffEvent.objects.create(event_id="invented-1", summary="Vacation", all_day=True, first_date=TUESDAY,
                                    last_date=TUESDAY + datetime.timedelta(days=1), copied_at=NOW)
        days = open_times(self.job(), TUESDAY, TUESDAY + datetime.timedelta(days=2), now=NOW)
        self.assertEqual([bool(day.open_slots) for day in days], [False, False, True])
        self.assertIn("Open day: Time Off all day: Vacation", rules_text(days[0].reasons))

    def test_the_notice_and_the_furthest_date(self):
        today = timezone.localdate(NOW)
        days = open_times(self.job(), today, today + datetime.timedelta(days=92), now=NOW)
        open_dates = [day.date for day in days if day.open_slots]
        self.assertEqual(open_dates[0], today + datetime.timedelta(days=2))  # no same-day or next-day booking
        self.assertEqual(open_dates[-1], today + datetime.timedelta(days=90))
        self.assertTrue(rules_text(days[1].reasons)[0].startswith("Open day: Too soon: bookings need 2 days' notice"))
        self.assertTrue(rules_text(days[91].reasons)[0].startswith("Open day: Too far ahead: bookings go up to 90 days ahead"))

    def test_the_notice_turns_over_at_midnight_eastern(self):
        # 11:59 PM Eastern on Monday is already Tuesday in UTC. The notice
        # still counts from Monday, so Wednesday is open.
        monday, wednesday = TUESDAY - datetime.timedelta(days=1), TUESDAY + datetime.timedelta(days=1)
        before_midnight = eastern(monday, 23, 59)
        self.assertEqual(before_midnight.astimezone(UTC).date(), TUESDAY)
        self.assertEqual(check(self.job(), eastern(wednesday, 8), now=before_midnight), [])
        after_midnight = eastern(TUESDAY, 0, 1)
        self.assertEqual(rules_text(check(self.job(), eastern(wednesday, 8), now=after_midnight)),
                         ["Open day: Too soon: bookings need 2 days' notice, so the first date is Thu Dec 10"])


class StartTimeTests(SchedulingTestCase):
    """Condition 2."""

    def test_a_time_off_the_list_is_closed(self):
        self.assertEqual(rules_text(check(self.job(), eastern(TUESDAY, 10), now=NOW)),
                         ["Start times: 10:00 AM is not a start time on Tuesdays"])

    def test_start_times_are_per_weekday(self):
        SchedulingSettings.get()
        saturday = OpenWeekday.objects.get(weekday=5)
        saturday.start_times = [datetime.time(9), datetime.time(13)]
        saturday.save()
        day = open_times(self.job(), TUESDAY + datetime.timedelta(days=4), TUESDAY + datetime.timedelta(days=4), now=NOW)[0]
        self.assertEqual([slot.local_time for slot in day.open_slots], [datetime.time(9), datetime.time(13)])

    def test_different_hours_use_the_weekday_times_within_them_or_their_own(self):
        DateException.objects.create(date=TUESDAY, kind=DateException.Kind.HOURS, opens_at=datetime.time(8, 30), closes_at=datetime.time(12))
        day = open_times(self.job(), TUESDAY, TUESDAY, now=NOW)[0]
        self.assertEqual([slot.local_time for slot in day.open_slots], [datetime.time(8, 30), datetime.time(9)])
        DateException.objects.filter(date=TUESDAY).update(start_times=[datetime.time(10)])
        self.assertEqual(rules_text(check(self.job(), eastern(TUESDAY, 9), now=NOW)), ["Start times: 9:00 AM is not a start time on this date"])


class TimeOffTests(SchedulingTestCase):
    """Condition 3."""

    def setUp(self):
        super().setUp()
        TimeOffEvent.objects.create(event_id="invented-2", summary="Dentist", starts_at=eastern(TUESDAY, 11), ends_at=eastern(TUESDAY, 12), copied_at=NOW)

    def test_a_timed_event_blocks_only_its_own_time(self):
        self.assertEqual(rules_text(check(self.job(minutes=240), eastern(TUESDAY, 8), now=NOW)),
                         ["Time Off: Overlaps Dentist, 11:00 AM to 12:00 PM"])
        # Three hours from 8:00 ends at 11:00, as the event starts.
        self.assertEqual(check(self.job(minutes=180), eastern(TUESDAY, 8), now=NOW), [])

    def test_the_buffer_setting(self):
        self.settings(time_off_buffer_minutes=30)
        self.assertEqual([r.rule for r in check(self.job(minutes=180), eastern(TUESDAY, 8), now=NOW)], ["time_off"])
        self.assertEqual(check(self.job(minutes=150), eastern(TUESDAY, 8), now=NOW), [])


class JobsPerDayTests(SchedulingTestCase):
    """Condition 4: one job a day, except Monthly Maintenance and Motorcycle
    Detail, up to two a day each, or one of each (decision 0072)."""

    def placed(self, service, minutes=180):
        return check(self.job(service, minutes), eastern(TUESDAY, 11, 30), now=NOW)

    def test_two_monthly_maintenance_jobs(self):
        self.book(self.monthly, eastern(TUESDAY, 8), minutes=180)
        self.assertEqual(self.placed(self.monthly), [])

    def test_two_motorcycle_details(self):
        self.book(self.motorcycle, eastern(TUESDAY, 8), minutes=180)
        self.assertEqual(self.placed(self.motorcycle), [])

    def test_one_of_each(self):
        self.book(self.motorcycle, eastern(TUESDAY, 8), minutes=180)
        self.assertEqual(self.placed(self.monthly), [])

    def test_not_a_third(self):
        self.book(self.monthly, eastern(TUESDAY, 8), minutes=120)
        self.book(self.motorcycle, eastern(TUESDAY, 10, 30), minutes=120)
        reasons = check(self.job(self.motorcycle, 120), eastern(TUESDAY, 13), now=NOW)
        self.assertEqual(rules_text(reasons), ["Jobs per day: The day would hold 3 jobs; the most it can hold is 2"])

    def test_a_service_within_its_own_maximum(self):
        SharedService.objects.filter(service=self.monthly).update(max_per_day=1)
        self.book(self.monthly, eastern(TUESDAY, 8), minutes=180)
        self.assertEqual(rules_text(self.placed(self.monthly)), ["Jobs per day: Monthly Maintenance is limited to 1 a day"])

    def test_a_full_detail_does_not_share(self):
        self.book(self.full_detail, eastern(TUESDAY, 8), minutes=180)
        self.assertEqual(rules_text(self.placed(self.monthly)),
                         ["Jobs per day: The day already has 1 job, and Full Detail can't share a day"])
        self.assertEqual([r.rule for r in check(self.job(self.full_detail), eastern(TUESDAY + datetime.timedelta(days=1), 8), now=NOW)], [])

    def test_a_canceled_job_does_not_count(self):
        self.book(self.full_detail, eastern(TUESDAY, 8), minutes=180, status=Appointment.Status.CANCELED)
        self.assertEqual(check(self.job(self.full_detail), eastern(TUESDAY, 8), now=NOW), [])

    def test_two_regular_jobs_a_day_are_only_settings(self):
        self.settings(jobs_per_day=2)
        SharedService.objects.create(service=self.full_detail, max_per_day=2)
        self.book(self.full_detail, eastern(TUESDAY, 8), minutes=180)
        self.assertEqual(self.placed(self.full_detail), [])


class GapTests(SchedulingTestCase):
    """Condition 5: the drive, at least 30 minutes, rounded up to the quarter hour."""

    def setUp(self):
        super().setUp()
        self.first_point = self.located(self.address, "35.161200", "-84.877000")
        self.second_point = self.located(self.second, "35.200000", "-84.800000")
        # An 8:00 Monthly Maintenance job of 3 hours on site, ending at 11:00.
        self.first = self.book(self.monthly, eastern(TUESDAY, 8), minutes=180, address=self.address)

    def drive(self, minutes):
        return mock.patch.object(availability.drive, "drive_time", return_value=Drive(minutes, 1000, False, "google"))

    def placed_start(self, minutes):
        with self.drive(minutes):
            day = open_times(self.job(point=self.second_point), TUESDAY, TUESDAY, now=NOW)[0]
        return [slot for slot in day.slots if slot.placed_after][0]

    def test_a_second_job_is_placed_by_the_drive_time(self):
        slot = self.placed_start(42)  # 11:00 + 42 minutes = 11:42, rounded up to 11:45
        self.assertEqual((slot.local_time, slot.is_open, slot.placed_after), (datetime.time(11, 45), True, self.first.scheduled_start))
        # The listed 8:00 to 9:00 times fall inside the first job.
        with self.drive(42):
            day = open_times(self.job(point=self.second_point), TUESDAY, TUESDAY, now=NOW)[0]
        self.assertEqual([s.local_time for s in day.open_slots], [datetime.time(11, 45)])
        self.assertEqual([r.rule for s in day.closed_slots for r in s.reasons], ["gap", "gap", "gap"])

    def test_the_drive_is_asked_from_the_first_address_leaving_at_its_end(self):
        with self.drive(42) as drive_time:
            check(self.job(point=self.second_point), eastern(TUESDAY, 11, 45), now=NOW)
        origin, destination, departure = drive_time.call_args.args
        self.assertEqual((origin, destination, departure), (self.first_point, self.second_point, eastern(TUESDAY, 11)))

    def test_the_30_minute_minimum(self):
        self.assertEqual(self.placed_start(10).local_time, datetime.time(11, 30))
        with self.drive(10):
            reasons = check(self.job(point=self.second_point), eastern(TUESDAY, 11, 15), now=NOW)
        self.assertIn("Gap between jobs: Too close to the 8:00 AM job, which ends at 11:00 AM: the earliest start after it is 11:30 AM "
                      "(a 10-minute drive, so the 30-minute minimum gap)", rules_text(reasons))

    def test_the_rounding(self):
        self.assertEqual(self.placed_start(31).local_time, datetime.time(11, 45))
        self.assertEqual(self.placed_start(45).local_time, datetime.time(11, 45))
        self.assertEqual(self.placed_start(46).local_time, datetime.time(12, 0))
        self.settings(round_start_up_to_minutes=1)
        self.assertEqual(self.placed_start(31).local_time, datetime.time(11, 31))

    def test_without_locations_the_gap_is_the_minimum(self):
        day = open_times(self.job(), TUESDAY, TUESDAY, now=NOW)[0]
        self.assertEqual([slot.local_time for slot in day.open_slots], [datetime.time(11, 30)])

    def test_the_owner_can_book_later_than_the_placed_start(self):
        with self.drive(42):
            self.assertEqual(check(self.job(point=self.second_point), eastern(TUESDAY, 13), now=NOW), [])
            self.assertEqual([r.rule for r in check(self.job(point=self.second_point), eastern(TUESDAY, 13, 5), now=NOW)], ["start_time"])

    def test_a_job_before_a_booked_one_leaves_the_gap_too(self):
        self.first.scheduled_start = eastern(TUESDAY, 12)
        self.first.save()
        with self.drive(20):
            # 8:00 + 3 hours = 11:00, + 30 minutes = 11:30, before the 12:00 job: fine.
            self.assertEqual(check(self.job(point=self.second_point), eastern(TUESDAY, 8), now=NOW), [])
            reasons = check(self.job(point=self.second_point), eastern(TUESDAY, 9), now=NOW)
        self.assertEqual(rules_text(reasons), ["Gap between jobs: Ends at 12:00 PM, too close to the 12:00 PM job, which would have to "
                                               "start at 12:30 PM or later (a 20-minute drive, so the 30-minute minimum gap)"])


class ClosingTimeTests(SchedulingTestCase):
    """Condition 6."""

    def test_a_lone_job_may_run_past_closing(self):
        self.assertEqual(check(self.job(self.full_detail, minutes=11 * 60), eastern(TUESDAY, 9), now=NOW), [])

    def test_with_two_jobs_the_last_ends_by_closing(self):
        self.book(self.monthly, eastern(TUESDAY, 8), minutes=360)  # to 2:00 PM, so a second starts at 2:30
        self.assertEqual(check(self.job(minutes=210), eastern(TUESDAY, 14, 30), now=NOW), [])  # ends at 6:00 PM
        self.assertEqual(rules_text(check(self.job(minutes=225), eastern(TUESDAY, 14, 30), now=NOW)),
                         ["Closing time: With 2 jobs the day would run to 6:15 PM, past closing at 6:00 PM; only a job alone may run past closing"])

    def test_a_placed_start_at_or_after_closing_is_not_offered(self):
        self.book(self.monthly, eastern(TUESDAY, 8), minutes=600)  # to 6:00 PM
        day = open_times(self.job(), TUESDAY, TUESDAY, now=NOW)[0]
        self.assertFalse([slot for slot in day.slots if slot.placed_after])


class DaylightSavingTimeTests(SchedulingTestCase):
    """Start times are Eastern clock times; lengths of time are real minutes."""

    END = datetime.date(2027, 11, 7)  # a Sunday: clocks go back from 2:00 AM EDT to 1:00 AM EST
    START = datetime.date(2027, 3, 14)  # a Sunday: clocks go forward from 2:00 AM EST to 3:00 AM EDT

    def open_all_night(self, day, starts):
        DateException.objects.create(date=day, kind=DateException.Kind.HOURS, opens_at=datetime.time(0), closes_at=datetime.time(23),
                                     start_times=starts)

    def test_the_day_daylight_saving_time_ends(self):
        now = eastern(self.END - datetime.timedelta(days=10), 12)
        self.open_all_night(self.END, [datetime.time(0, 30), datetime.time(8)])
        # A 2-hour job from 12:30 AM EDT ends at 1:30 AM EST, after the clocks go back.
        first = self.book(self.motorcycle, eastern(self.END, 0, 30), minutes=120)
        self.assertEqual(first.ends_at.astimezone(UTC), datetime.datetime(2027, 11, 7, 6, 30, tzinfo=UTC))
        day = open_times(self.job(self.motorcycle, 120), self.END, self.END, now=now)[0]
        placed = [slot for slot in day.slots if slot.placed_after][0]
        # 1:30 AM EST + the 30-minute gap = 2:00 AM EST, 2.5 real hours after the 12:30 AM EDT start.
        self.assertEqual(placed.start, datetime.datetime(2027, 11, 7, 7, 0, tzinfo=UTC))
        self.assertEqual((placed.local_time, placed.is_open), (datetime.time(2, 0), True))
        eight = [slot for slot in day.slots if slot.local_time == datetime.time(8)][0]
        self.assertEqual(eight.start, datetime.datetime(2027, 11, 7, 13, 0, tzinfo=UTC))  # 8:00 AM EST
        self.assertTrue(eight.is_open)

    def test_a_weekday_start_time_keeps_its_clock_time_across_the_change(self):
        now = eastern(datetime.date(2027, 10, 20), 12)
        friday, monday = datetime.date(2027, 11, 5), datetime.date(2027, 11, 8)
        days = open_times(self.job(), friday, monday, now=now)
        self.assertEqual(days[0].open_slots[0].start, datetime.datetime(2027, 11, 5, 12, 0, tzinfo=UTC))  # 8:00 AM EDT
        self.assertEqual(days[3].open_slots[0].start, datetime.datetime(2027, 11, 8, 13, 0, tzinfo=UTC))  # 8:00 AM EST

    def test_a_start_time_the_clocks_skip(self):
        now = eastern(self.START - datetime.timedelta(days=10), 12)
        self.open_all_night(self.START, [datetime.time(2, 30), datetime.time(8)])
        day = open_times(self.job(), self.START, self.START, now=now)[0]
        self.assertEqual(rules_text(day.closed_slots[0].reasons), ["Start times: 2:30 AM does not happen on Mar 14: the clocks go forward"])
        self.assertEqual([slot.start for slot in day.open_slots], [datetime.datetime(2027, 3, 14, 12, 0, tzinfo=UTC)])  # 8:00 AM EDT


class NinetyDaysTests(SchedulingTestCase):
    def test_ninety_days_at_once_in_a_few_queries(self):
        for offset in range(2, 90, 3):
            day = TUESDAY + datetime.timedelta(days=offset)
            if day.weekday() != 6:
                self.book(self.monthly, eastern(day, 8), minutes=180)
        SchedulingSettings.get()
        started = time.monotonic()
        with CaptureQueriesContext(connection) as queries:
            days = open_times(self.job(), TUESDAY, TUESDAY + datetime.timedelta(days=89), now=NOW)
        self.assertEqual(len(days), 90)
        self.assertLessEqual(len(queries), 10)
        self.assertLess(time.monotonic() - started, 2)


class WebsiteBookingTests(SchedulingTestCase):
    """The website can only book an open time; it can never override."""

    def inputs(self):
        return booking.JobInputs(self.full_detail, self.crossover, self.two_rows, 1)

    def test_an_open_time_books_from_the_website(self):
        day = timezone.localdate() + datetime.timedelta(days=5)
        day += datetime.timedelta(days=1) if day.weekday() == 6 else datetime.timedelta()
        appointment = booking.book_online(self.customer, self.vehicle, eastern(day, 8), self.inputs(), address=self.address)
        self.assertEqual(appointment.source, Appointment.Source.WEBSITE)

    def test_a_closed_time_is_refused(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        with self.assertRaises(booking.RulesBroken) as raised:
            booking.book_online(self.customer, self.vehicle, eastern(tomorrow, 10, 15), self.inputs())
        self.assertIn("Too soon", str(raised.exception))
        self.assertFalse(Appointment.objects.exists())


class SettingsScreenTests(SchedulingTestCase):
    def form_data(self, **changes):
        settings = SchedulingSettings.get()
        data = {name: getattr(settings, name) for name in (
            "minimum_notice_days", "furthest_bookable_days", "setup_minutes_one_person", "breakdown_minutes_one_person",
            "time_on_site_rounding_minutes", "jobs_per_day", "minimum_gap_minutes", "round_start_up_to_minutes",
            "time_off_buffer_minutes", "time_off_check_minutes", "stale_copy_warning_minutes")}
        for row in OpenWeekday.objects.all():
            if row.is_open:
                data[f"day{row.weekday}-is_open"] = "on"
                data[f"day{row.weekday}-opens_at"] = row.opens_at.strftime("%H:%M")
                data[f"day{row.weekday}-closes_at"] = row.closes_at.strftime("%H:%M")
                data[f"day{row.weekday}-start_times"] = ", ".join(t.strftime("%H:%M") for t in row.start_times)
        for shared in SharedService.objects.all():
            data[f"share{shared.service_id}-shares"] = "on"
            data[f"share{shared.service_id}-max_per_day"] = shared.max_per_day
        data.update(changes)
        return data

    def test_the_screens_load(self):
        for name in ("scheduling-settings", "open-times", "scheduling-waiting"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_a_change_is_saved_with_history(self):
        self.client.post(reverse("scheduling-settings"), self.form_data(minimum_notice_days=3, **{"day5-start_times": "09:00, 13:00"}))
        self.assertEqual(SchedulingSettings.get().minimum_notice_days, 3)
        self.assertEqual(OpenWeekday.objects.get(weekday=5).start_times, [datetime.time(9), datetime.time(13)])
        self.assertEqual(SchedulingSettings.get().history.first().history_user, self.owner_user)
        self.assertEqual(OpenWeekday.objects.get(weekday=5).history.count(), 2)

    def test_opening_sunday_and_letting_full_detail_share(self):
        data = self.form_data(**{"day6-is_open": "on", "day6-opens_at": "10:00", "day6-closes_at": "16:00", "day6-start_times": "10:00",
                                 f"share{self.full_detail.pk}-shares": "on", f"share{self.full_detail.pk}-max_per_day": "1"})
        self.client.post(reverse("scheduling-settings"), data)
        self.assertTrue(OpenWeekday.objects.get(weekday=6).is_open)
        self.assertEqual(SharedService.objects.get(service=self.full_detail).max_per_day, 1)

    def test_a_start_time_outside_the_hours_is_refused(self):
        response = self.client.post(reverse("scheduling-settings"), self.form_data(**{"day0-start_times": "07:00"}))
        self.assertContains(response, "07:00 is outside the hours.")

    def test_only_a_manager_changes_them(self):
        self.client.force_login(self.helper_user)
        self.assertEqual(self.client.get(reverse("scheduling-settings")).status_code, 200)
        self.assertEqual(self.client.post(reverse("scheduling-settings"), self.form_data(minimum_notice_days=5)).status_code, 403)

    def test_a_change_lists_the_booked_jobs_it_leaves_outside_the_rules(self):
        day = timezone.localdate() + datetime.timedelta(days=10)
        day += datetime.timedelta(days=1) if day.weekday() == 6 else datetime.timedelta()
        at_eight = self.book(self.full_detail, eastern(day, 8))
        at_nine = self.book(self.full_detail, eastern(day + datetime.timedelta(days=1 if day.weekday() != 5 else 2), 9))
        times = {f"day{n}-start_times": "09:00" for n in range(6)}
        response = self.client.post(reverse("scheduling-settings"), self.form_data(**times), follow=True)
        affected = AffectedJob.objects.get()
        self.assertEqual((affected.appointment, affected.rules_broken), (at_eight, [f"Start times: 8:00 AM is not a start time on {day:%A}s"]))
        self.assertContains(response, "1 booked job now falls outside the rules")
        self.assertContains(response, "Keep as booked")
        # The job never moves on its own.
        at_eight.refresh_from_db()
        self.assertEqual(timezone.localtime(at_eight.scheduled_start).time(), datetime.time(8))
        self.client.post(reverse("scheduling-change", args=[affected.change.pk]), {f"keep-{affected.pk}": "on"})
        affected.refresh_from_db()
        self.assertEqual((affected.choice, affected.decided_by), ("keep", self.owner_user))
        self.assertFalse(AffectedJob.objects.filter(appointment=at_nine).exists())

    def test_closing_a_booked_date_lists_its_job_and_moving_it_records_the_reschedule(self):
        day = timezone.localdate() + datetime.timedelta(days=10)
        day += datetime.timedelta(days=1) if day.weekday() == 6 else datetime.timedelta()
        job = self.book(self.full_detail, eastern(day, 8), address=self.address)
        self.client.post(reverse("date-exception-add"), {"date": day.isoformat(), "kind": "closed", "reason": "Truck in the shop"})
        affected = AffectedJob.objects.get()
        self.assertEqual(affected.rules_broken, ["Open day: Closed: Truck in the shop"])
        later = day + datetime.timedelta(days=1 if day.weekday() != 5 else 2)
        self.client.post(reverse("appointment-edit", args=[job.pk]), self.booking_data(later, crew_size="1"))
        affected.refresh_from_db()
        self.assertEqual(affected.choice, "rescheduled")

    def test_the_open_times_view(self):
        page = self.client.get(reverse("open-times"), {"service": self.monthly.pk, "vehicle_class": self.crossover.pk,
                                                       "size_variant": self.two_rows.pk, "crew_size": "2"})
        self.assertContains(page, "Monthly Maintenance")
        self.assertContains(page, "Sunday is a closed day")
        self.assertContains(page, "Too soon")
        self.assertContains(page, "8:00 AM")
        self.assertEqual(page.content.decode().count('<li class="card">'), 90)
