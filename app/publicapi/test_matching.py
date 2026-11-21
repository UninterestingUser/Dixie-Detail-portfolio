"""Quiet matching of website bookings (returning-customers.md, decisions
0034 and 0067), the staff rule (decisions 0061 and 0069) and a second
vehicle the same day (booking-flow.md), through the public API."""

from django.test import override_settings

from appointments.models import Appointment, MatchFlag
from customers import matching
from customers.models import Address, Consent, Customer, SecondContact
from publicapi.models import SecondVehicleRequest
from staff.models import ServiceAuthorization, StaffMember
from vehicles.models import Vehicle

from .testing import CLEVELAND, ApiTestCase, day_after, eastern, open_day


class MatchingTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.place_token = self.place()["place"]
        self.owner = StaffMember.objects.create(name="Owner Example", role=StaffMember.Role.OWNER)

    def returning(self, first="Jordan", last="Sample", mobile="4235550142", address=True, vehicles=(("White",),), **fields):
        """A customer as if booked before: the Cleveland address (written the
        long way) and a 2019 Toyota RAV4 for each color given."""
        customer = Customer.objects.create(first_name=first, last_name=last, mobile=mobile, **fields)
        if address:
            Address.objects.create(customer=customer, line1="100 Example Street Northwest", city="Cleveland", state="TN", zip_code="37311")
        for (color,) in vehicles:
            Vehicle.objects.create(customer=customer, year=2019, make="Toyota", model="RAV4", color=color, vehicle_class=self.medium)
        return customer

    def book(self, start=None, expect=201, vehicle=None, **changes):
        quote = self.quote(vehicle=vehicle, place=self.place_token)
        response = self.client.post_json("bookings", self.booking_body(quote, start or eastern(open_day(3), 8), **changes))
        self.assertEqual(response.status_code, expect, response.content)
        answer = response.json()
        if expect == 201:
            return Appointment.objects.get(reference=answer["reference"]), answer
        return None, answer

    def flags(self, appointment, field=None):
        found = appointment.match_flags.all()
        return list(found.filter(field=field) if field else found)


class MatchingTests(MatchingTestCase):
    def test_a_new_number_makes_a_new_customer_with_no_flags(self):
        appointment, _ = self.book()
        self.assertFalse(appointment.intake["matched"])
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(self.flags(appointment), [])

    def test_a_returning_customer_is_matched_on_ten_digits_with_no_flag(self):
        customer = self.returning(vehicles=(("Silver",),))
        appointment, answer = self.book(mobile="(423) 555-0142", color="silver")
        self.assertEqual(appointment.customer, customer)
        self.assertTrue(appointment.intake["matched"])
        self.assertEqual(Customer.objects.count(), 1)
        # The same address written the short way, and the same vehicle.
        self.assertEqual(appointment.service_address, customer.addresses.get())
        self.assertEqual(appointment.vehicle, customer.vehicles.get())
        self.assertEqual(self.flags(appointment), [])
        # Nothing from the record is in the answer.
        self.assertNotIn("Silver", str(answer))
        self.assertEqual(answer["summary"]["color"], "silver")

    def test_the_consent_answers_go_on_the_matched_customer(self):
        customer = self.returning()
        appointment, _ = self.book()
        self.assertEqual(Consent.objects.filter(customer=customer).count(), 1)
        self.assertEqual(sorted(appointment.intake["consent_ids"]), sorted(Consent.objects.values_list("pk", flat=True)))

    def test_an_unverified_record_address_takes_the_places_location(self):
        customer = self.returning()
        address = customer.addresses.get()
        self.assertIsNone(address.point)
        appointment, _ = self.book()
        address.refresh_from_db()
        self.assertEqual(appointment.service_address, address)
        self.assertIsNotNone(address.point)
        self.assertEqual(address.line1, "100 Example Street Northwest")
        self.assertEqual(address.google_place_id, CLEVELAND)

    def test_a_second_contact_booking_under_their_own_name_matches_without_a_flag(self):
        customer = self.returning(mobile="4235550100")
        SecondContact.objects.create(customer=customer, name="Riley Sample", phone="4235550142")
        appointment, _ = self.book(first_name="Riley", last_name="Sample")
        self.assertEqual(appointment.customer, customer)
        self.assertTrue(appointment.intake["contact_id"])
        self.assertEqual(self.flags(appointment, MatchFlag.Field.NAME), [])

    def test_a_different_name_still_books_and_is_flagged_with_both_versions(self):
        customer = self.returning()
        appointment, _ = self.book(first_name="Casey", last_name="Other")
        self.assertEqual(appointment.customer, customer)
        flag = self.flags(appointment, MatchFlag.Field.NAME)[0]
        self.assertEqual((flag.booked_value, flag.record_value), ("Casey Other", "Jordan Sample"))

    def test_a_missing_last_name_or_other_capitals_is_not_a_different_name(self):
        self.returning()
        appointment, _ = self.book(first_name="JORDAN", last_name=None)
        self.assertEqual(self.flags(appointment, MatchFlag.Field.NAME), [])

    def test_a_different_address_still_books_on_it_and_is_flagged(self):
        customer = self.returning()
        customer.addresses.update(line1="9 Elsewhere Road", zip_code="37312")
        appointment, _ = self.book()
        self.assertEqual(appointment.customer, customer)
        # The job uses the address as booked.
        self.assertEqual(appointment.service_address.line1, "100 Example St NW")
        self.assertEqual(appointment.service_address.google_place_id, CLEVELAND)
        flag = self.flags(appointment, MatchFlag.Field.ADDRESS)[0]
        self.assertEqual(flag.booked_address, appointment.service_address)
        self.assertIn("9 Elsewhere Road", flag.record_value)
        self.assertEqual(customer.addresses.filter(active=True).count(), 2)

    def test_a_different_vehicle_still_books_on_it_and_is_flagged(self):
        customer = self.returning()
        customer.vehicles.update(make="Honda", model="Accord")
        appointment, _ = self.book()
        self.assertEqual((appointment.vehicle.make, appointment.vehicle.model), ("Toyota", "RAV4"))
        flag = self.flags(appointment, MatchFlag.Field.VEHICLE)[0]
        self.assertFalse(flag.identical_vehicles)
        self.assertEqual(flag.booked_vehicle, appointment.vehicle)
        self.assertIn("Honda Accord", flag.record_value)

    def test_the_same_make_and_model_is_the_same_vehicle_when_a_year_is_missing(self):
        customer = self.returning()
        customer.vehicles.update(year=None, make="toyota", model="Rav-4")
        appointment, _ = self.book()
        self.assertEqual(appointment.vehicle, customer.vehicles.get())
        self.assertEqual(self.flags(appointment), [])

    def test_a_different_year_is_a_different_vehicle(self):
        customer = self.returning()
        customer.vehicles.update(year=2015)
        appointment, _ = self.book()
        self.assertNotEqual(appointment.vehicle, customer.vehicles.get(year=2015))
        self.assertEqual(len(self.flags(appointment, MatchFlag.Field.VEHICLE)), 1)

    def test_the_color_picks_between_identical_vehicles(self):
        customer = self.returning(vehicles=(("White",), ("Dark Blue",)))
        appointment, _ = self.book(color="  dark   BLUE ")
        self.assertEqual(appointment.vehicle, customer.vehicles.get(color="Dark Blue"))
        self.assertEqual(self.flags(appointment), [])
        self.assertEqual(Vehicle.objects.count(), 2)

    def test_a_blank_color_is_flagged_with_the_identical_vehicles_listed(self):
        customer = self.returning(vehicles=(("White",), ("Dark Blue",)))
        appointment, _ = self.book(color=None)
        flag = self.flags(appointment, MatchFlag.Field.VEHICLE)[0]
        self.assertTrue(flag.identical_vehicles)
        self.assertEqual(sorted(flag.record_choices), sorted(customer.vehicles.filter(color__in=["White", "Dark Blue"]).values_list("pk", flat=True)))
        self.assertIn("White", flag.record_value)
        self.assertIn("Dark Blue", flag.record_value)

    def test_a_color_matching_neither_is_flagged_too(self):
        self.returning(vehicles=(("White",), ("Dark Blue",)))
        appointment, _ = self.book(color="Red")
        self.assertTrue(self.flags(appointment, MatchFlag.Field.VEHICLE)[0].identical_vehicles)

    def test_with_only_one_such_vehicle_the_color_changes_nothing(self):
        customer = self.returning(vehicles=(("White",),))
        appointment, _ = self.book(color="Red")
        self.assertEqual(appointment.vehicle, customer.vehicles.get())
        self.assertEqual(self.flags(appointment), [])

    def test_the_color_never_changes_the_price(self):
        self.returning(vehicles=(("White",), ("Dark Blue",)))
        first, _ = self.book(color="White")
        second, _ = self.book(color=None, start=eastern(day_after(open_day(3)), 8))
        self.assertEqual(first.total_before_tax, second.total_before_tax)

    def test_test_bookings_match_only_test_customers(self):
        real = self.returning()
        with override_settings(TEST_PHONE_NUMBERS=["4235550142"]):
            appointment, _ = self.book()
        self.assertNotEqual(appointment.customer, real)
        self.assertTrue(appointment.customer.is_test)

    def test_of_several_customers_sharing_the_number_the_named_one_comes_first(self):
        self.returning(first="Jordan")
        other = self.returning(first="Casey", last="Sample", address=False, vehicles=())
        appointment, _ = self.book(first_name="Casey")
        self.assertEqual(appointment.customer, other)

    def test_a_vehicle_no_longer_on_the_record_is_not_matched(self):
        customer = self.returning()
        customer.vehicles.update(active=False)
        appointment, _ = self.book()
        self.assertNotEqual(appointment.vehicle, customer.vehicles.get(active=False))


class StaffRuleTests(MatchingTestCase):
    def test_a_one_person_job_with_one_qualified_person_is_assigned(self):
        appointment, _ = self.book()
        self.assertEqual([a.staff_member for a in appointment.assignments.all()], [self.owner])

    def test_two_qualified_people_leave_it_for_the_prompt(self):
        helper = StaffMember.objects.create(name="Helper Example", role=StaffMember.Role.HELPER, pay_type="family_helper")
        for service in (self.full_detail,):
            ServiceAuthorization.objects.create(staff_member=helper, service=service)
        appointment, _ = self.book()
        self.assertFalse(appointment.assignments.exists())

    def test_no_qualified_person_leaves_it_for_the_prompt(self):
        self.owner.active = False
        self.owner.save()
        appointment, _ = self.book()
        self.assertFalse(appointment.assignments.exists())


class SecondVehicleTests(MatchingTestCase):
    """At launch a day takes one job, and only Motorcycle Detail and Monthly
    Maintenance share a day, so a second motorcycle is the case the website
    can offer (scheduling-and-calendars.md)."""

    MOTORCYCLE = {"year": 2020, "make": "Honda", "model": "Gold Wing", "type": "motorcycle"}

    def motorcycle_quote(self, vehicle=None):
        return self.quote(vehicle=vehicle or self.MOTORCYCLE, service=self.motorcycle_detail, place=self.place_token)

    def same_day_start(self, quote, day):
        """Noon, after the 8:00 job: past its placed start with the fake
        Google's 33-minute drive between the two jobs."""
        return eastern(day, 12).isoformat()

    def two_motorcycles(self):
        from vehicles.models import VehicleModel

        from .testing import add_model

        add_model("Harley-Davidson", "Road King", self.motorcycles, None, year=2020, vehicle_type=VehicleModel.VehicleType.MOTORCYCLE)
        customer = self.returning(vehicles=())
        day = open_day(3)
        first = self.client.post_json("bookings", self.booking_body(self.motorcycle_quote(), eastern(day, 8)))
        self.assertEqual(first.status_code, 201, first.content)
        second_quote = self.motorcycle_quote({"year": 2020, "make": "Harley-Davidson", "model": "Road King", "type": "motorcycle"})
        body = self.booking_body(second_quote, self.same_day_start(second_quote, day), color="Black")
        return customer, Appointment.objects.get(reference=first.json()["reference"]), body

    def test_a_second_vehicle_the_same_day_comes_in_as_a_request(self):
        """The same answer as any booking that becomes a request (decision
        0113): it never mentions the booking the number already has."""
        customer, first, body = self.two_motorcycles()
        response = self.client.post_json("bookings", body)
        self.assertEqual(response.status_code, 202, response.content)
        answer = response.json()
        self.assertEqual(answer["status"], "requested")
        self.assertIn("confirm it by text or call", answer["message"])
        self.assertNotIn("already", answer["message"])
        self.assertNotIn("calendar_file", answer)
        # Not an appointment: the customer still has one job that day.
        self.assertEqual(Appointment.objects.filter(customer=customer).count(), 1)
        request = SecondVehicleRequest.objects.get(reference=answer["request"])
        self.assertEqual((request.customer, request.same_day_appointment), (customer, first))
        self.assertEqual(request.reason, SecondVehicleRequest.Reason.SAME_DAY)
        self.assertEqual(request.web_quote.number, body["quote"])
        # The vehicle it brought waits off the record until it is booked.
        self.assertFalse(request.vehicle.active)
        self.assertEqual(request.intake["flags"][0]["field"], MatchFlag.Field.VEHICLE)
        # Nothing from the record is in the answer.
        self.assertNotIn("Gold Wing", str(answer))

    def test_a_new_customer_never_gets_a_request(self):
        day = open_day(3)
        first = self.client.post_json("bookings", self.booking_body(self.motorcycle_quote(), eastern(day, 8), mobile="4235550111"))
        self.assertEqual(first.status_code, 201)
        quote = self.motorcycle_quote()
        response = self.client.post_json("bookings", self.booking_body(quote, self.same_day_start(quote, day), mobile="4235550122"))
        self.assertEqual(response.status_code, 201, response.content)

    def test_the_time_must_still_be_open(self):
        """A taken time is refused the same way whatever the number holds,
        so the answer can't tell anyone the number has a job that day."""
        self.returning()
        self.book(start=eastern(open_day(3), 8))
        response = self.client.post_json("bookings", self.booking_body(self.quote(place=self.place_token), eastern(open_day(3), 8)))
        self.assertEqual((response.status_code, response.json()["error"]), (409, "time_taken"))
        stranger = self.client.post_json(
            "bookings", self.booking_body(self.quote(place=self.place_token), eastern(open_day(3), 8), mobile="4235550188")
        )
        self.assertEqual(stranger.json(), response.json())

    def test_a_canceled_job_that_day_does_not_count(self):
        self.returning()
        first, _ = self.book(start=eastern(open_day(3), 8))
        Appointment.objects.filter(pk=first.pk).update(status=Appointment.Status.CANCELED)
        second, _ = self.book(start=eastern(open_day(3), 8))
        self.assertEqual(second.customer, first.customer)

    def test_the_quote_cant_be_booked_again(self):
        _, _, body = self.two_motorcycles()
        self.assertEqual(self.client.post_json("bookings", body).status_code, 202)
        self.assertEqual(self.client.post_json("bookings", body).json()["error"], "quote_used")


class MatchingUnitTests(MatchingTestCase):
    def test_street_words_are_written_either_way(self):
        self.assertEqual(matching.street_key("100 Example Street Northwest"), matching.street_key("100 example st. NW"))

    def test_a_customer_number_comes_before_a_second_contact(self):
        contact_owner = self.returning(first="Pat", mobile="4235550100")
        SecondContact.objects.create(customer=contact_owner, name="Jordan Sample", phone="4235550142")
        own = self.returning(first="Jordan", mobile="4235550142")
        self.assertEqual(matching.find_match("4235550142", first_name="Jordan"), (own, None))
