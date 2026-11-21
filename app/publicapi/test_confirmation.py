"""Confirming website bookings from new customers (decision 0112) and the
one answer for a booking that becomes a request (decision 0113), through
the public API: who is confirmed at once, the reasons, the queued text,
the two caps, the booking request kept with its quote, and that no answer
says whether a number has a booking."""

import datetime

from django.utils import timezone

from appointments import confirmation
from appointments.models import Appointment
from customers.models import Customer
from messaging.models import Message
from publicapi.models import SecondVehicleRequest
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
        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(response.json()["status"], "requested")
        self.assertEqual(Appointment.objects.count(), 1)
        request = SecondVehicleRequest.objects.get(reference=response.json()["request"])
        self.assertEqual(request.reason, SecondVehicleRequest.Reason.OVER_CAP)
        self.assertEqual(request.start, eastern(open_day(4), 8))
        self.assertIsNone(request.same_day_appointment)
        # Another number still books.
        self.booked(self.post(day=4, mobile="4235550111"))

    def test_at_most_five_new_customer_bookings_at_once(self):
        for number in range(5):
            self.booked(self.post(day=3 + number, mobile=f"42355501{number:02d}"))
        response = self.post(day=9, mobile="4235550198")
        self.assertEqual(response.json()["status"], "requested")
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
            self.assertEqual(self.post(day=7, mobile="4235550100").json()["status"], "requested")

    def test_the_caps_are_scheduling_settings(self):
        SchedulingSettings.objects.filter(pk=1).update(unconfirmed_per_number=2)
        self.booked(self.post(day=3))
        self.booked(self.post(day=4))
        self.assertEqual(self.post(day=5).json()["status"], "requested")


class OneAnswerTests(ConfirmationTestCase):
    """Every booking that becomes a request gets the same answer (decision
    0113), so the answer never says whether a number has a booking."""

    def answer_for(self, day, mobile, **changes):
        response = self.post(day=day, mobile=mobile, **changes)
        self.assertEqual(response.status_code, 202, response.content)
        answer = response.json()
        # The request number is the request's own; everything else must match.
        reference = answer.pop("request")
        answer["message"] = answer["message"].replace(reference, "REFERENCE")
        return answer

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
        self.assertEqual(set(per_number), {"status", "message", "summary"})
        for word in ("already", "booking for this number", "another", "limit", "unconfirmed"):
            self.assertNotIn(word, per_number["message"].lower())
        reasons = sorted(SecondVehicleRequest.objects.values_list("reason", flat=True))
        self.assertEqual(reasons, ["over_cap", "over_cap", "same_day"])
        # Below the caps, a new number books that same time.
        Appointment.objects.filter(customer__mobile="4235550203").update(status=Appointment.Status.CANCELED)
        self.booked(self.post(day=day, mobile="4235550277", hour=12, motorcycle=True))

    def test_a_taken_time_is_refused_before_the_caps_are_looked_at(self):
        self.booked(self.post(day=3, mobile="4235550111"))
        capped = self.post(day=3, mobile="4235550111")
        stranger = self.post(day=3, mobile="4235550122")
        self.assertEqual(capped.json(), stranger.json())
        self.assertEqual(capped.json()["error"], "time_taken")
        self.assertFalse(SecondVehicleRequest.objects.exists())


class BookingRequestTests(ConfirmationTestCase):
    def test_approving_a_capped_request_books_the_quote_the_customer_saw(self):
        from django.contrib.auth import get_user_model

        from publicapi import decisions
        from publicapi.models import WebQuote

        self.booked(self.post(day=3))
        response = self.post(day=4)
        request = SecondVehicleRequest.objects.get(reference=response.json()["request"])
        user = get_user_model().objects.create_user("owner", password="an-invented-password-1")
        job, _ = decisions.approve_second_vehicle(request, request.start, user)
        self.assertEqual(job.quote, WebQuote.objects.get(number=request.web_quote.number).quote)
        self.assertEqual(job.total_before_tax, request.web_quote.quote.total_before_tax)
        # Booked by the owner in the control app, so confirmed.
        self.assertEqual(job.confirmed_how, Appointment.ConfirmedHow.CONTROL_APP)
        self.assertEqual(job.customer, Appointment.objects.exclude(pk=job.pk).get().customer)
