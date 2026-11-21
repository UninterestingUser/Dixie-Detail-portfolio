"""Confirming website bookings from new customers (decision 0112) and the
one answer for a booking that becomes a request (decision 0113), through
the public API: who is confirmed at once, the reasons, the queued text,
the two caps, and that no answer says whether a number has a booking."""

import datetime

from django.utils import timezone

from appointments import confirmation
from appointments.models import Appointment
from customers.models import Customer
from messaging.models import Message
from scheduling.models import SchedulingSettings

from .testing import ApiTestCase, eastern, open_day


class ConfirmationTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.place_token = self.place()["place"]
        # The launch values (data/booking-rules.yaml), which ApiTestCase lifts.
        SchedulingSettings.objects.filter(pk=1).update(unconfirmed_per_number=1, unconfirmed_new_customers=5)

    MOTORCYCLE = {"year": 2020, "make": "Honda", "model": "Gold Wing", "type": "motorcycle"}

    def post(self, day=3, mobile="4235550142", text_consent=True, hour=8, motorcycle=False, **changes):
        """A booking at hour on open_day(day), or on day when it is a date."""
        if motorcycle:
            quote = self.quote(vehicle=self.MOTORCYCLE, service=self.motorcycle_detail, place=self.place_token)
        else:
            quote = self.quote(place=self.place_token)
        consents = {"version": "2026-11-18", "appointment": text_consent}
        date = day if isinstance(day, datetime.date) else open_day(day)
        return self.client.post_json(
            "bookings", self.booking_body(quote, eastern(date, hour), mobile=mobile, consents=consents, **changes)
        )

    def booked(self, response):
        self.assertEqual(response.status_code, 201, response.content)
        answer = response.json()
        return Appointment.objects.get(reference=answer["reference"]), answer

    def known_customer(self, mobile="4235550142"):
        """A customer with one completed job, months ago."""
        customer = Customer.objects.create(first_name="Jordan", last_name="Sample", mobile=mobile)
        Appointment.objects.create(
            customer=customer, scheduled_start=timezone.now() - datetime.timedelta(days=90),
            status=Appointment.Status.COMPLETED, source=Appointment.Source.OWNER,
        )
        return customer


class WhoIsConfirmedTests(ConfirmationTestCase):
    def test_a_new_customer_with_text_consent_waits_for_a_text_reply(self):
        appointment, answer = self.booked(self.post())
        self.assertEqual(appointment.confirmation, Appointment.Confirmation.UNCONFIRMED)
        self.assertEqual(appointment.unconfirmed_reason, Appointment.UnconfirmedReason.TEXT_REPLY)
        self.assertEqual(answer["confirmation"], "text")
        # It still holds its time.
        self.assertEqual(appointment.status, Appointment.Status.BOOKED)
        self.assertEqual(self.post(mobile="4235550198").json()["error"], "time_taken")

    def test_the_confirmation_request_is_queued_not_sent(self):
        appointment, _ = self.booked(self.post())
        [message] = Message.objects.all()
        self.assertEqual(message.kind, Message.Kind.CONFIRMATION_REQUEST)
        self.assertEqual((message.direction, message.status), (Message.Direction.OUTBOUND, Message.Status.QUEUED))
        self.assertEqual((message.customer, message.appointment, message.phone), (appointment.customer, appointment, "4235550142"))
        local = timezone.localtime(appointment.scheduled_start)
        self.assertEqual(
            message.body,
            f"Dixie Detail: Please confirm your Full Detail on {local:%A, %B} {local.day} at 8:00 AM. Reply YES to confirm, "
            "or call or text (423) 380-9120 to change it. Reply STOP to opt out.",
        )

    def test_a_new_customer_without_text_consent_gets_a_call(self):
        appointment, answer = self.booked(self.post(text_consent=False))
        self.assertEqual(appointment.unconfirmed_reason, Appointment.UnconfirmedReason.CALL)
        self.assertEqual(answer["confirmation"], "call")
        self.assertFalse(Message.objects.exists())

    def test_a_known_customer_is_confirmed_at_once(self):
        customer = self.known_customer()
        appointment, answer = self.booked(self.post())
        self.assertEqual(appointment.customer, customer)
        self.assertEqual(appointment.confirmation, Appointment.Confirmation.CONFIRMED)
        self.assertEqual(appointment.confirmed_how, Appointment.ConfirmedHow.KNOWN_CUSTOMER)
        self.assertIsNotNone(appointment.confirmed_at)
        self.assertEqual(answer["confirmation"], "confirmed")
        self.assertFalse(Message.objects.exists())

    def test_a_returning_customer_with_no_completed_job_is_not_known(self):
        self.booked(self.post(day=3))
        Appointment.objects.update(status=Appointment.Status.CANCELED)
        appointment, answer = self.booked(self.post(day=4))
        self.assertEqual(answer["confirmation"], "text")
        self.assertTrue(appointment.intake["matched"])

    def test_confirming_is_kept_in_the_change_history(self):
        appointment, _ = self.booked(self.post())
        confirmation.confirm(appointment, Appointment.ConfirmedHow.TEXT_REPLY)
        appointment.refresh_from_db()
        self.assertEqual((appointment.confirmation, appointment.unconfirmed_reason), (Appointment.Confirmation.CONFIRMED, ""))
        latest = appointment.history.first()
        self.assertEqual(latest.history_change_reason, "Confirmed: text reply")
        self.assertEqual(appointment.history.last().confirmation, Appointment.Confirmation.UNCONFIRMED)
        with self.assertRaisesMessage(confirmation.ConfirmationError, "already confirmed"):
            confirmation.confirm(appointment, Appointment.ConfirmedHow.MANAGER)


class CapTests(ConfirmationTestCase):
    def test_one_open_unconfirmed_booking_per_new_number(self):
        self.booked(self.post(day=3))
        response = self.post(day=4)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], "request_instead")
        self.assertEqual(response.json()["preferred_day"], open_day(4).isoformat())
        self.assertEqual(Appointment.objects.count(), 1)
        # Another number still books.
        self.booked(self.post(day=4, mobile="4235550111"))

    def test_at_most_five_new_customer_bookings_at_once(self):
        for number in range(5):
            self.booked(self.post(day=3 + number, mobile=f"42355501{number:02d}"))
        response = self.post(day=9, mobile="4235550198")
        self.assertEqual(response.json()["error"], "request_instead")
        self.assertEqual(Appointment.objects.count(), 5)

    def test_a_known_customer_is_never_capped(self):
        for number in range(5):
            self.booked(self.post(day=3 + number, mobile=f"42355501{number:02d}"))
        self.known_customer(mobile="4235550188")
        _, answer = self.booked(self.post(day=9, mobile="4235550188"))
        self.assertEqual(answer["confirmation"], "confirmed")

    def test_a_confirmed_canceled_or_past_booking_frees_its_place(self):
        first, _ = self.booked(self.post(day=3))
        confirmation.confirm(first, Appointment.ConfirmedHow.MANAGER)
        second, _ = self.booked(self.post(day=4))
        second.status = Appointment.Status.CANCELED
        second.save()
        third, _ = self.booked(self.post(day=5))
        Appointment.objects.filter(pk=third.pk).update(scheduled_start=timezone.now() - datetime.timedelta(hours=1))
        self.booked(self.post(day=6))

    def test_test_records_count_only_against_test_records(self):
        with self.settings(TEST_PHONE_NUMBERS=["(423) 555-0100"]):
            for _ in range(2):
                SchedulingSettings.objects.filter(pk=1).update(unconfirmed_per_number=1000)
                self.booked(self.post(day=3 + _, mobile="4235550100"))
            SchedulingSettings.objects.filter(pk=1).update(unconfirmed_per_number=1, unconfirmed_new_customers=2)
            self.booked(self.post(day=6, mobile="4235550111"))
            self.assertEqual(self.post(day=7, mobile="4235550100").json()["error"], "request_instead")

    def test_the_caps_are_scheduling_settings(self):
        SchedulingSettings.objects.filter(pk=1).update(unconfirmed_per_number=2)
        self.booked(self.post(day=3))
        self.booked(self.post(day=4))
        self.assertEqual(self.post(day=5).json()["error"], "request_instead")


class OneAnswerTests(ConfirmationTestCase):
    """Every booking that becomes a request gets the same answer (decision
    0113), so the answer never says whether a number has a booking."""

    def answer_for(self, day, mobile, **changes):
        response = self.post(day=day, mobile=mobile, **changes)
        self.assertEqual(response.status_code, 409, response.content)
        return response.json()

    def test_the_caps_and_a_job_that_day_give_identical_answers(self):
        """At launch only Motorcycle Detail and Monthly Maintenance share a
        day, so each case asks for a second motorcycle at noon on a day that
        has one at 8:00: the time is open, and only the reason differs."""
        days = sorted({open_day(n) for n in range(3, 30)})
        day, others = days[0], days[1:]
        self.known_customer(mobile="4235550188")
        self.booked(self.post(day=day, mobile="4235550188", motorcycle=True))
        # A known customer with a job that day.
        same_day = self.answer_for(day, "4235550188", hour=12, motorcycle=True)
        # A new number's own cap.
        self.booked(self.post(day=others[0], mobile="4235550111"))
        per_number = self.answer_for(day, "4235550111", hour=12, motorcycle=True)
        # Everyone's cap.
        for number, other in enumerate(others[1:5]):
            self.booked(self.post(day=other, mobile=f"42355502{number:02d}"))
        everyone = self.answer_for(day, "4235550299", hour=12, motorcycle=True)
        self.assertEqual(per_number, same_day)
        self.assertEqual(per_number, everyone)
        self.assertEqual(set(per_number), {"error", "message", "preferred_day"})
        self.assertEqual(per_number["preferred_day"], day.isoformat())
        for word in ("already", "booking for this number", "another", "limit", "unconfirmed"):
            self.assertNotIn(word, per_number["message"].lower())
        # Below the caps, a new number books that same time.
        Appointment.objects.filter(customer__mobile="42355502" "03").update(status=Appointment.Status.CANCELED)
        self.booked(self.post(day=day, mobile="4235550277", hour=12, motorcycle=True))

    def test_a_taken_time_is_refused_before_the_caps_are_looked_at(self):
        self.booked(self.post(day=3, mobile="4235550111"))
        capped = self.post(day=3, mobile="4235550111")
        stranger = self.post(day=3, mobile="4235550122")
        self.assertEqual(capped.json(), stranger.json())
        self.assertEqual(capped.json()["error"], "time_taken")

    def test_the_request_form_comes_in_marked_from_a_booking(self):
        import uuid

        from publicapi.models import TimeRequest

        from .test_quote_requests import signed
        from .testing import BASE, CLEVELAND, PublicClient

        body = {
            "request_id": str(uuid.uuid4()), "submitted_at": timezone.now().isoformat(),
            "vehicle": {"year": 2019, "make": "Toyota", "model": "RAV4"}, "condition": 1, "service": self.full_detail.pk,
            "place_id": CLEVELAND, "preferred_start": eastern(open_day(4), 8).isoformat(),
            "first_name": "Avery", "mobile": "4235550123", "payment_method": "card",
            "consents": {"version": "2026-11-18", "appointment": True}, "shown": {"total": "100.00", "pricebook_version": 1},
            "from_booking": True,
        }
        raw, headers = signed(body)
        response = PublicClient(origin=None, visitor="104.16.0.1").post(f"{BASE}time-requests", raw, content_type="application/json", headers=headers)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(TimeRequest.objects.get().from_booking)
