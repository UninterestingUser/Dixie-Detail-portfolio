"""Website bookings in the control app (control-app.md,
handling-website-bookings.md): each review queue action, the assign-staff
prompt, a second vehicle the same day, the offline request screen, the
quote request screen, the "needs you" list and the smoke test scenarios."""

import datetime
import io
import json
import uuid
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from appointments.models import Appointment, MatchFlag
from billing.models import TaxRate
from calendars.models import CalendarFlag
from customers.models import Address, Consent, Customer, SecondContact
from pricebook.models import PricedLine
from publicapi.models import QuoteRequest, SecondVehicleRequest, TimeRequest
from publicapi.test_matching import MatchingTestCase, SecondVehicleTests
from publicapi.test_quote_requests import signed
from publicapi.testing import BASE, CLEVELAND, CONSENTS, GOOD_TOKEN, PublicClient, eastern, jpeg, open_day
from scheduling.models import RuleOverride
from staff.models import StaffMember
from vehicles.models import Vehicle

from .fixtures import TailnetClient


class ControlTestCase(MatchingTestCase):
    def setUp(self):
        super().setUp()
        # An invented home base, so the request screens show a drive.
        from geo.models import LocationSettings

        LocationSettings.objects.filter(pk=LocationSettings.get().pk).update(home_latitude=Decimal("35.300000"), home_longitude=Decimal("-84.800000"))
        self.user = get_user_model().objects.create_user("owner", password="an-invented-password-1")
        self.owner.user = self.user
        self.owner.save()
        self.tailnet = TailnetClient()
        self.tailnet.force_login(self.user)

    def flag(self, appointment, field):
        return appointment.match_flags.get(field=field)

    def resolve(self, flag, resolution, choice=None, expect=302):
        data = {"resolution": resolution}
        if choice is not None:
            data["choice"] = choice
        response = self.tailnet.post(f"/review/flags/{flag.pk}/", data)
        self.assertEqual(response.status_code, expect)
        flag.refresh_from_db()
        return response


class ReviewQueueTests(ControlTestCase):
    def test_the_review_page_shows_both_versions_side_by_side(self):
        customer = self.returning()
        customer.addresses.update(line1="9 Elsewhere Road", zip_code="37312")
        appointment, _ = self.book(first_name="Casey", last_name="Other")
        page = self.tailnet.get(f"/review/{appointment.pk}/")
        self.assertContains(page, "Casey Other")
        self.assertContains(page, "Jordan Sample")
        self.assertContains(page, "9 Elsewhere Road")
        self.assertContains(page, "100 Example St NW")
        for label in ("Change the name on the record", "Keep the record&#x27;s name", "Add as a second contact", "Move the booking to a new customer"):
            self.assertContains(page, label)
        self.assertContains(self.tailnet.get("/review/"), "2 differences")
        self.assertContains(self.tailnet.get(f"/appointments/{appointment.pk}/"), "Check 2 differences from the record")

    def test_name_update_the_record(self):
        customer = self.returning()
        appointment, _ = self.book(first_name="Jordyn", last_name="Sample-Lee")
        flag = self.flag(appointment, MatchFlag.Field.NAME)
        self.resolve(flag, MatchFlag.Resolution.UPDATE_RECORD)
        customer.refresh_from_db()
        self.assertEqual(str(customer), "Jordyn Sample-Lee")
        self.assertEqual(flag.resolution, MatchFlag.Resolution.UPDATE_RECORD)
        self.assertEqual(flag.resolved_by, self.user)
        self.assertIsNotNone(flag.resolved_at)
        self.assertIn("Jordyn Sample-Lee", flag.resolution_note)
        self.assertIn("Name changed from the website booking", customer.history.first().history_change_reason)

    def test_name_keep_the_record(self):
        customer = self.returning()
        appointment, _ = self.book(first_name="Jo")
        flag = self.flag(appointment, MatchFlag.Field.NAME)
        self.resolve(flag, MatchFlag.Resolution.KEEP_RECORD)
        customer.refresh_from_db()
        self.assertEqual(str(customer), "Jordan Sample")
        self.assertEqual(flag.resolution, MatchFlag.Resolution.KEEP_RECORD)

    def test_name_add_alongside_makes_a_second_contact(self):
        customer = self.returning()
        appointment, _ = self.book(first_name="Riley", last_name="Sample")
        self.resolve(self.flag(appointment, MatchFlag.Field.NAME), MatchFlag.Resolution.ADD_ALONGSIDE)
        contact = SecondContact.objects.get(customer=customer)
        self.assertEqual((contact.name, contact.phone), ("Riley Sample", "4235550142"))
        # Next time, the second contact matches without a flag.
        later, _ = self.book(first_name="Riley", last_name="Sample", start=eastern(open_day(5), 8))
        self.assertFalse(later.match_flags.filter(field=MatchFlag.Field.NAME).exists())

    def test_address_update_the_record(self):
        customer = self.returning()
        old = customer.addresses.get()
        Address.objects.filter(pk=old.pk).update(line1="9 Elsewhere Road", zip_code="37312")
        appointment, _ = self.book()
        self.resolve(self.flag(appointment, MatchFlag.Field.ADDRESS), MatchFlag.Resolution.UPDATE_RECORD)
        old.refresh_from_db()
        self.assertFalse(old.active)
        self.assertEqual(list(customer.addresses.filter(active=True)), [appointment.service_address])

    def test_address_keep_the_record_leaves_the_job_on_the_booked_address(self):
        customer = self.returning()
        customer.addresses.update(line1="9 Elsewhere Road", zip_code="37312")
        appointment, _ = self.book()
        self.resolve(self.flag(appointment, MatchFlag.Field.ADDRESS), MatchFlag.Resolution.KEEP_RECORD)
        appointment.refresh_from_db()
        self.assertFalse(appointment.service_address.active)
        self.assertEqual(appointment.service_address.line1, "100 Example St NW")
        self.assertEqual(customer.addresses.filter(active=True).get().line1, "9 Elsewhere Road")

    def test_address_add_alongside(self):
        customer = self.returning()
        customer.addresses.update(line1="9 Elsewhere Road", zip_code="37312")
        appointment, _ = self.book()
        self.resolve(self.flag(appointment, MatchFlag.Field.ADDRESS), MatchFlag.Resolution.ADD_ALONGSIDE)
        self.assertEqual(customer.addresses.filter(active=True).count(), 2)

    def test_vehicle_update_the_record_with_a_pick(self):
        customer = self.returning(vehicles=(("White",), ("Red",)))
        customer.vehicles.filter(color="White").update(make="Honda", model="Accord")
        customer.vehicles.filter(color="Red").update(make="Ford", model="Escape")
        appointment, _ = self.book()
        flag = self.flag(appointment, MatchFlag.Field.VEHICLE)
        self.resolve(flag, MatchFlag.Resolution.UPDATE_RECORD)
        self.assertFalse(flag.resolution, "A pick is needed with more than one vehicle")
        replaced = customer.vehicles.get(make="Honda")
        self.resolve(flag, MatchFlag.Resolution.UPDATE_RECORD, choice=replaced.pk)
        replaced.refresh_from_db()
        self.assertFalse(replaced.active)
        self.assertTrue(customer.vehicles.get(make="Ford").active)
        self.assertTrue(appointment.vehicle.active)
        self.assertIn("replaces", flag.resolution_note)

    def test_vehicle_keep_the_record(self):
        customer = self.returning()
        customer.vehicles.update(make="Honda", model="Accord")
        appointment, _ = self.book()
        self.resolve(self.flag(appointment, MatchFlag.Field.VEHICLE), MatchFlag.Resolution.KEEP_RECORD)
        appointment.vehicle.refresh_from_db()
        self.assertFalse(appointment.vehicle.active)
        self.assertTrue(customer.vehicles.get(make="Honda").active)

    def test_vehicle_add_alongside(self):
        customer = self.returning()
        customer.vehicles.update(make="Honda", model="Accord")
        appointment, _ = self.book()
        self.resolve(self.flag(appointment, MatchFlag.Field.VEHICLE), MatchFlag.Resolution.ADD_ALONGSIDE)
        self.assertEqual(customer.vehicles.filter(active=True).count(), 2)

    def test_identical_vehicles_pick_the_one_it_was_and_record_the_color(self):
        customer = self.returning(vehicles=(("White",), ("",)))
        appointment, _ = self.book(color="Pearl")
        flag = self.flag(appointment, MatchFlag.Field.VEHICLE)
        booked = appointment.vehicle
        self.assertTrue(flag.identical_vehicles)
        page = self.tailnet.get(f"/review/{appointment.pk}/")
        self.assertContains(page, "Which vehicle?")
        self.assertContains(page, "color given: Pearl")
        blank = customer.vehicles.get(pk__in=flag.record_choices, color="")
        self.resolve(flag, MatchFlag.Resolution.UPDATE_RECORD, choice=blank.pk)
        appointment.refresh_from_db()
        blank.refresh_from_db()
        self.assertEqual(appointment.vehicle, blank)
        self.assertEqual(blank.color, "Pearl")
        self.assertFalse(Vehicle.objects.filter(pk=booked.pk).exists())
        self.assertEqual(customer.vehicles.count(), 2)

    def test_identical_vehicles_pick_and_keep_the_record(self):
        customer = self.returning(vehicles=(("White",), ("Dark Blue",)))
        appointment, _ = self.book(color="Navy")
        flag = self.flag(appointment, MatchFlag.Field.VEHICLE)
        dark_blue = customer.vehicles.get(color="Dark Blue")
        self.resolve(flag, MatchFlag.Resolution.KEEP_RECORD)
        self.assertFalse(flag.resolution, "Keeping the record still needs a pick")
        self.resolve(flag, MatchFlag.Resolution.KEEP_RECORD, choice=dark_blue.pk)
        appointment.refresh_from_db()
        dark_blue.refresh_from_db()
        self.assertEqual(appointment.vehicle, dark_blue)
        self.assertEqual(dark_blue.color, "Dark Blue")

    def test_identical_vehicles_add_alongside(self):
        customer = self.returning(vehicles=(("White",), ("Dark Blue",)))
        appointment, _ = self.book(color=None)
        self.resolve(self.flag(appointment, MatchFlag.Field.VEHICLE), MatchFlag.Resolution.ADD_ALONGSIDE)
        self.assertEqual(customer.vehicles.filter(active=True).count(), 3)

    def test_move_the_booking_to_a_new_customer(self):
        customer = self.returning()
        customer.addresses.update(line1="9 Elsewhere Road", zip_code="37312")
        appointment, _ = self.book(first_name="Casey", last_name="Other", color="White")
        consents = list(Consent.objects.filter(pk__in=appointment.intake["consent_ids"]))
        name = self.flag(appointment, MatchFlag.Field.NAME)
        self.resolve(name, MatchFlag.Resolution.MOVE_TO_NEW_CUSTOMER)
        appointment.refresh_from_db()
        moved_to = appointment.customer
        self.assertNotEqual(moved_to, customer)
        self.assertEqual((str(moved_to), moved_to.mobile), ("Casey Other", "4235550142"))
        # The address the booking brought goes with it; the matched vehicle
        # stays on the record and the new customer gets a copy.
        self.assertEqual(appointment.service_address.customer, moved_to)
        self.assertEqual(appointment.vehicle.customer, moved_to)
        self.assertEqual(customer.vehicles.count(), 1)
        self.assertEqual(Consent.objects.filter(customer=moved_to).count(), len(consents))
        self.assertFalse(Consent.objects.filter(customer=customer).exists())
        # Every flag on the job is closed with that choice.
        self.assertFalse(appointment.match_flags.filter(resolution="").exists())
        self.assertEqual(set(appointment.match_flags.values_list("resolution", flat=True)), {MatchFlag.Resolution.MOVE_TO_NEW_CUSTOMER})

    def test_a_resolved_flag_cant_be_resolved_again(self):
        self.returning()
        appointment, _ = self.book(first_name="Casey")
        flag = self.flag(appointment, MatchFlag.Field.NAME)
        self.resolve(flag, MatchFlag.Resolution.KEEP_RECORD)
        response = self.tailnet.post(f"/review/flags/{flag.pk}/", {"resolution": MatchFlag.Resolution.UPDATE_RECORD}, follow=True)
        self.assertContains(response, "already been resolved")
        self.assertEqual(Customer.objects.get(pk=flag.customer_id).first_name, "Jordan")


class AssignStaffPromptTests(ControlTestCase):
    def test_a_website_job_with_no_staff_is_on_the_home_screen(self):
        StaffMember.objects.create(name="Helper Example", role=StaffMember.Role.OWNER)
        appointment, _ = self.book()
        self.assertFalse(appointment.assignments.exists())
        page = self.tailnet.get("/schedule/")
        self.assertContains(page, f"Assign staff: {appointment.customer}")
        self.assertContains(page, f"/appointments/{appointment.pk}/#staff-heading")


class SecondVehicleScreenTests(ControlTestCase, SecondVehicleTests):
    def request(self):
        customer, first, body = self.two_motorcycles()
        answer = self.client.post_json("bookings", body).json()
        return customer, SecondVehicleRequest.objects.get(reference=answer["request"])

    def test_approve_books_the_quote_at_the_time_picked(self):
        customer, item = self.request()
        page = self.tailnet.get(f"/requests/second-vehicle/{item.pk}/")
        self.assertContains(page, "Second vehicle the same day")
        self.assertContains(page, "Road King")
        local = timezone.localtime(item.start)
        response = self.tailnet.post(f"/requests/second-vehicle/{item.pk}/book/", {"book-date": local.date(), "book-time": local.strftime("%H:%M")})
        self.assertEqual(response.status_code, 302, response.content)
        item.refresh_from_db()
        self.assertEqual(item.status, SecondVehicleRequest.Status.BOOKED)
        job = item.appointment
        self.assertEqual(job.quote, item.web_quote.quote)
        self.assertEqual(job.customer, customer)
        self.assertEqual(job.preferred_payment_method, "cash")
        # The vehicle goes on the record and its flag is raised on the job.
        item.vehicle.refresh_from_db()
        self.assertTrue(item.vehicle.active)
        self.assertTrue(job.match_flags.filter(field=MatchFlag.Field.VEHICLE).exists())
        self.assertEqual(item.decided_by, self.user)

    def test_decline_with_a_reason(self):
        _, item = self.request()
        self.tailnet.post(f"/requests/second-vehicle/{item.pk}/decline/", {"decline-reason": "Only one truck fits the driveway."})
        item.refresh_from_db()
        self.assertEqual((item.status, item.decline_reason), (SecondVehicleRequest.Status.DECLINED, "Only one truck fits the driveway."))
        self.assertIsNone(item.appointment)


class OfflineRequestScreenTests(ControlTestCase):
    def send(self, **changes):
        body = {
            "request_id": str(uuid.uuid4()),
            "submitted_at": eastern(open_day(-1), 21).isoformat(),
            "vehicle": {"year": 2019, "make": "Toyota", "model": "RAV4"},
            "condition": 1,
            "service": self.full_detail.pk,
            "place_id": CLEVELAND,
            "preferred_start": eastern(open_day(4), 8).isoformat(),
            "first_name": "Avery",
            "mobile": "4235550123",
            "payment_method": "card",
            "consents": dict(CONSENTS),
            "shown": {"total": "100.00", "pricebook_version": 1},
            **changes,
        }
        raw, headers = signed(body)
        response = PublicClient(origin=None).post(f"{BASE}time-requests", raw, content_type="application/json", headers=headers)
        self.assertEqual(response.status_code, 201, response.content)
        return TimeRequest.objects.get(request_id=body["request_id"])

    def book(self, item, start, **extra):
        local = timezone.localtime(start)
        return self.tailnet.post(f"/requests/offline/{item.pk}/book/", {"book-date": local.date(), "book-time": local.strftime("%H:%M"), **extra})

    def test_the_screen_shows_the_price_the_customer_saw_beside_todays(self):
        item = self.send()
        page = self.tailnet.get(f"/requests/offline/{item.pk}/")
        self.assertContains(page, "Today's price before tax")
        self.assertContains(page, "The customer saw")
        self.assertContains(page, "$100.00")
        self.assertContains(page, "Honor the price the customer saw")

    def test_book_at_todays_price(self):
        item = self.send()
        response = self.book(item, item.preferred_start)
        self.assertEqual(response.status_code, 302, response.content)
        item.refresh_from_db()
        self.assertEqual(item.status, TimeRequest.Status.BOOKED)
        job = item.appointment
        self.assertEqual(job.total_before_tax, item.quote.total_before_tax)
        self.assertEqual(job.preferred_payment_method, "card")
        self.assertEqual(job.source, Appointment.Source.WEBSITE)
        self.assertTrue(job.assignments.exists())

    def test_book_at_the_price_the_customer_saw(self):
        item = self.send()
        self.book(item, item.preferred_start, **{"book-honor_shown": "on"})
        item.refresh_from_db()
        job = item.appointment
        self.assertEqual(job.total_before_tax, Decimal("100.00"))
        line = job.lines.get(kind=PricedLine.Kind.ADJUSTMENT)
        self.assertIn("while the server was offline", line.reason)

    def test_a_time_outside_the_rules_needs_a_managers_reason(self):
        item = self.send()
        sunday = open_day(7)
        sunday += datetime.timedelta(days=(6 - sunday.weekday()) % 7)
        response = self.book(item, eastern(sunday, 8))
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "Give the reason for booking off hours", status_code=422)
        response = self.book(item, eastern(sunday, 8), **{"book-override_reason": "Customer's only free day."})
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(RuleOverride.objects.get().appointment, item.appointment)

    def test_decline(self):
        item = self.send()
        self.tailnet.post(f"/requests/offline/{item.pk}/decline/", {"decline-reason": "Booked by phone instead."})
        item.refresh_from_db()
        self.assertEqual(item.status, TimeRequest.Status.DECLINED)

    def test_a_returning_customers_offline_request_is_matched_and_flagged_when_booked(self):
        customer = self.returning(mobile="4235550123", first="Avery", last="")
        customer.addresses.update(line1="9 Elsewhere Road", zip_code="37312")
        item = self.send()
        self.assertEqual(item.customer, customer)
        self.assertFalse(item.service_address.active)
        self.book(item, item.preferred_start)
        item.refresh_from_db()
        item.service_address.refresh_from_db()
        self.assertTrue(item.service_address.active)
        self.assertTrue(item.appointment.match_flags.filter(field=MatchFlag.Field.ADDRESS).exists())


def upload_file(content):
    return SimpleUploadedFile("photo.jpg", content, content_type="image/jpeg")


class QuoteRequestScreenTests(ControlTestCase):
    def send(self, photos=2, **changes):
        session = self.client.post_json("quote-requests/uploads", {"turnstile": GOOD_TOKEN}).json()["session"]
        ids = [
            self.client.post(f"{BASE}quote-requests/uploads/{session}/photos", {"photo": upload_file(jpeg())}).json()["photo"]
            for _ in range(photos)
        ]
        body = {
            "vehicle": {"year": 2021, "make": "Ford", "model": "Transit 250"}, "service": self.full_detail.pk,
            "description": "Work van, very dirty inside.", "place": self.place_token, "first_name": "Morgan", "last_name": "Fleet",
            "mobile": "423-555-0160", "consents": dict(CONSENTS), "preferred_days": "Weekday mornings", "turnstile": GOOD_TOKEN,
            "session": session, "photos": ids, **changes,
        }
        response = self.client.post_json("quote-requests", body)
        self.assertEqual(response.status_code, 201, response.content)
        return QuoteRequest.objects.get(reference=response.json()["reference"])

    def price(self, item, amount="425.00", minutes=360, crew=1, client=None):
        return (client or self.tailnet).post(f"/requests/quotes/{item.pk}/price/", {
            "price-service": self.full_detail.pk, "price-vehicle_class": self.vans.pk, "price-amount": amount,
            "price-time_on_site_minutes": minutes, "price-crew_size": crew,
        })

    def book(self, item, start):
        local = timezone.localtime(start)
        return self.tailnet.post(f"/requests/quotes/{item.pk}/book/", {"book-date": local.date(), "book-time": local.strftime("%H:%M")})

    def test_the_screen_shows_everything_needed_to_price_it(self):
        item = self.send()
        page = self.tailnet.get(f"/requests/quotes/{item.pk}/")
        self.assertContains(page, "2021 Ford Transit 250")
        self.assertContains(page, "Full Detail")
        self.assertContains(page, "Work van, very dirty inside.")
        self.assertContains(page, "100 Example St NW")
        self.assertContains(page, "from the home base")
        self.assertContains(page, "Cleveland, 9.75%")
        self.assertContains(page, "Weekday mornings")
        self.assertContains(page, 'href="tel:+14235550160"')
        # Two photos, each a link to the full size.
        for photo in item.photos.all():
            self.assertContains(page, f'<a href="/requests/photos/{photo.pk}/" target="_blank"', count=1)
        self.assertContains(page, 'href="sms:+14235550160"')

    def test_no_text_link_without_consent(self):
        item = self.send(consents={**CONSENTS, "appointment": False})
        page = self.tailnet.get(f"/requests/quotes/{item.pk}/")
        self.assertNotContains(page, "sms:")
        self.assertContains(page, "No consent to texts on record")

    def test_price_by_hand_makes_the_quote_of_record(self):
        item = self.send()
        response = self.price(item)
        self.assertEqual(response.status_code, 302, response.content)
        item.refresh_from_db()
        quote = item.quote
        self.assertEqual(item.status, QuoteRequest.Status.REPLIED)
        self.assertEqual(quote.total_before_tax, Decimal("425.00"))
        self.assertEqual(quote.time_on_site_minutes, 360)
        self.assertEqual(quote.setup_minutes + quote.service_minutes + quote.breakdown_minutes, 360)
        self.assertEqual(quote.vehicle_class, self.vans)
        self.assertEqual(quote.tax_rate, Decimal("9.750"))
        self.assertEqual(quote.total, quote.total_before_tax + quote.sales_tax)
        self.assertEqual(quote.lines.get().amount, Decimal("425.00"))
        page = self.tailnet.get(f"/requests/quotes/{item.pk}/")
        self.assertContains(page, "Dixie%20Detail%3A%20Thanks%20for%20your%20quote%20request")
        self.assertContains(page, "Send the price to the customer yourself")

    def test_only_a_manager_prices(self):
        item = self.send()
        helper_user = get_user_model().objects.create_user("helper", password="an-invented-password-2")
        helper = TailnetClient()
        helper.force_login(helper_user)
        self.assertEqual(self.price(item, client=helper).status_code, 403)

    def test_book_from_the_quote_into_an_open_time(self):
        item = self.send()
        self.price(item)
        item.refresh_from_db()
        response = self.book(item, eastern(open_day(4), 8))
        self.assertEqual(response.status_code, 302, response.content)
        item.refresh_from_db()
        job = item.appointment
        self.assertEqual(item.status, QuoteRequest.Status.BOOKED)
        self.assertEqual(job.quote, item.quote)
        self.assertEqual(job.total_before_tax, Decimal("425.00"))
        self.assertEqual(job.time_on_site_minutes, 360)
        self.assertEqual(job.vehicle, item.vehicle)
        self.assertTrue(job.vehicle.active)
        # The job keeps the description and photos for whoever does it.
        page = self.tailnet.get(f"/appointments/{job.pk}/")
        self.assertContains(page, "Work van, very dirty inside.")
        for photo in item.photos.all():
            self.assertContains(page, f"/requests/photos/{photo.pk}/")
        self.assertEqual([a.staff_member for a in job.assignments.all()], [self.owner])

    def test_booking_goes_through_the_availability_check(self):
        item = self.send()
        self.price(item)
        self.book(item, eastern(open_day(4), 8))
        other = self.send(photos=0, mobile="4235550161")
        self.price(other)
        response = self.book(other, eastern(open_day(4), 8))
        self.assertEqual(response.status_code, 422)
        other.refresh_from_db()
        self.assertIsNone(other.appointment)

    def test_a_two_person_job_always_gets_the_prompt(self):
        item = self.send(photos=0)
        self.price(item, crew=2, minutes=240)
        item.refresh_from_db()
        self.book(item, eastern(open_day(4), 8))
        item.refresh_from_db()
        self.assertFalse(item.appointment.assignments.exists())
        self.assertContains(self.tailnet.get("/schedule/"), "Assign staff: Morgan Fleet")

    def test_it_cant_be_booked_before_it_is_priced(self):
        item = self.send(photos=0)
        response = self.book(item, eastern(open_day(4), 8))
        self.assertContains(response, "Price the request first", status_code=422)

    def test_decline_with_a_reason(self):
        item = self.send(photos=0)
        self.tailnet.post(f"/requests/quotes/{item.pk}/decline/", {"decline-reason": "Too far for a van this size."})
        item.refresh_from_db()
        self.assertEqual((item.status, item.decline_reason), (QuoteRequest.Status.DECLINED, "Too far for a van this size."))
        self.assertIsNotNone(item.closed_at)

    def test_a_returning_customers_request_is_matched_and_flagged_when_booked(self):
        customer = self.returning(first="Morgan", last="Fleet", mobile="4235550160")
        item = self.send(photos=0)
        self.assertEqual(item.customer, customer)
        # The van waits off the record until the request is booked.
        self.assertFalse(item.vehicle.active)
        self.price(item)
        self.book(item, eastern(open_day(4), 8))
        item.refresh_from_db()
        self.assertTrue(item.appointment.match_flags.filter(field=MatchFlag.Field.VEHICLE).exists())


class NeedsYouTests(ControlTestCase):
    def test_everything_waiting_is_listed_newest_first_with_a_count(self):
        appointment, _ = self.book()
        customer = self.returning(first="Pat", mobile="4235550100")
        customer.addresses.update(line1="9 Elsewhere Road", zip_code="37312")
        flagged, _ = self.book(first_name="Pat", mobile="4235550100", start=eastern(open_day(5), 8))
        CalendarFlag.objects.create(kind=CalendarFlag.Kind.CLASH, appointment=appointment, summary="Dentist")
        TaxRate.objects.create(jurisdiction=appointment.service_address.tax_jurisdiction, state_rate=Decimal("7"), local_rate=Decimal("3"),
                               effective_from=timezone.localdate() + datetime.timedelta(days=60))
        page = self.tailnet.get("/schedule/")
        self.assertContains(page, "Needs you")
        self.assertContains(page, f"New booking: {appointment.customer}")
        self.assertContains(page, "Check the booking: Pat Sample")
        self.assertContains(page, "Time Off over a booked job")
        self.assertContains(page, "New sales tax rate")
        content = page.content.decode()
        self.assertLess(content.index("New sales tax rate"), content.index(f"New booking: {appointment.customer}"))
        # Two new bookings, one review, a clash and a rate.
        self.assertContains(page, '<span class="badge">5</span>')
        self.assertTrue(flagged.match_flags.exists())

    def test_clearing_the_new_bookings_keeps_one_that_came_in_meanwhile(self):
        first, _ = self.book()
        page = self.tailnet.get("/schedule/")
        self.assertContains(page, "Clear the new bookings")
        until = page.context["needs_you"]["newest_booking"]
        later, _ = self.book(mobile="4235550111", start=eastern(open_day(5), 8))
        self.tailnet.post("/needs-you/seen/", {"until": until.isoformat()})
        page = self.tailnet.get("/schedule/")
        self.assertNotContains(page, f'needs-booking" href="/appointments/{first.pk}/"')
        self.assertContains(page, f'needs-booking" href="/appointments/{later.pk}/"')

    def test_requests_waiting_for_a_decision_are_listed(self):
        QuoteRequestScreenTests.send(self, photos=0)
        self.assertContains(self.tailnet.get("/schedule/"), "Quote request: Morgan Fleet")


class SmokeScenarioTests(ControlTestCase):
    def run_smoke(self, *args):
        client = PublicClient(origin=None)

        def call(api, method, path, body=None, params=None, data=None, content_type="application/json"):
            url = BASE + path
            if method == "GET":
                response = client.get(url, params or {})
            elif body is not None:
                response = client.post(url, json.dumps(body), content_type="application/json")
            else:
                response = client.generic(method, url, data, content_type=content_type)
            return response.status_code, response.json()

        output = io.StringIO()
        with override_settings(TEST_PHONE_NUMBERS=["(423) 555-0199"]), mock.patch("publicapi.management.commands.api_smoke_test.Api.call", call):
            call_command("api_smoke_test", *args, place_id=CLEVELAND, stdout=output)
        return output.getvalue()

    def test_returning_books_with_each_kind_of_color_answer_and_keep_leaves_them(self):
        text = self.run_smoke("--scenario", "returning", "--keep")
        self.assertIn("the color picks the Dark Blue one; address flag(s)", text)
        self.assertIn("the color is blank; vehicle flag(s)", text)
        self.assertIn("the color matches neither; vehicle flag(s)", text)
        self.assertIn("kept the test records", text)
        self.assertTrue(text.strip().endswith("PASS"))
        customer = Customer.objects.get(is_test=True)
        self.assertEqual(customer.appointments.count(), 3)
        self.assertEqual(MatchFlag.objects.filter(resolution="").count(), 3)
        self.assertContains(self.tailnet.get("/review/"), "Smoke Test")
        call_command("delete_test_records", stdout=io.StringIO())
        self.assertFalse(Customer.objects.exists())
        self.assertFalse(MatchFlag.objects.exists())

    def test_returning_refuses_to_run_over_an_earlier_runs_records(self):
        Customer.objects.create(first_name="Smoke", mobile="4235550199", is_test=True)
        from django.core.management.base import CommandError

        with self.assertRaisesMessage(CommandError, "Run delete_test_records first"):
            self.run_smoke("--scenario", "returning")

    def test_quote_sends_a_vans_request_with_two_photos_and_cleans_up(self):
        text = self.run_smoke("--scenario", "quote")
        self.assertIn("with 2 photos", text)
        self.assertIn("Deleted 1 test customer(s), 0 appointment(s), 1 quote request(s) with 2 photo(s)", text)
        self.assertFalse(QuoteRequest.objects.exists())

    def test_quote_with_keep_leaves_the_request_for_the_screen(self):
        self.run_smoke("--scenario", "quote", "--keep")
        item = QuoteRequest.objects.get()
        self.assertEqual(item.photos.count(), 2)
        self.assertEqual(item.vehicle_class, self.vans)
        self.assertContains(self.tailnet.get(f"/requests/quotes/{item.pk}/"), "Ford Transit")
