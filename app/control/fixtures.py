"""Shared set-up for the control app's tests: the real pricebook, an invented
customer and invented staff."""

import datetime
import io

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone

from customers.models import Address, Customer
from pricebook.models import Service
from staff.models import PayType, StaffMember
from vehicles.models import SizeVariant, Vehicle, VehicleClass

TAILNET = {"X-Dixie-Entrance": "tailnet"}


class TailnetClient(Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, headers={**TAILNET, **kwargs.pop("headers", {})}, **kwargs)


def local(day, hour=8, minute=0):
    """A moment in Eastern time."""
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour, minute)))


class JobsTestCase(TestCase):
    """The pricebook as loaded from data/, a customer with a crossover, the
    owner (a manager, signed in) and two invented helpers."""

    client_class = TailnetClient

    @classmethod
    def setUpTestData(cls):
        call_command("load_pricebook", stdout=io.StringIO())
        User = get_user_model()
        cls.owner_user = User.objects.create_user("owner", password="an-invented-password-1")
        cls.helper_user = User.objects.create_user("helper", password="an-invented-password-1")
        cls.owner = StaffMember.objects.create(name="Owner Person", role=StaffMember.Role.OWNER, user=cls.owner_user)
        cls.helper = StaffMember.objects.create(name="Helper One", role=StaffMember.Role.HELPER, pay_type=PayType.FAMILY_HELPER, user=cls.helper_user)
        cls.second_helper = StaffMember.objects.create(name="Helper Two", role=StaffMember.Role.HELPER, pay_type=PayType.FAMILY_HELPER)
        cls.customer = Customer.objects.create(first_name="Pat", last_name="Example", mobile="4235550101")
        cls.address = Address.objects.create(customer=cls.customer, line1="100 Sample Rd", city="Calhoun", state="TN", zip_code="37309")
        cls.crossover = VehicleClass.objects.get(name="Crossovers & Wagons")
        cls.two_rows = SizeVariant.objects.get(vehicle_class=cls.crossover, value=2)
        cls.vehicle = Vehicle.objects.create(customer=cls.customer, year=2019, make="Toyota", model="RAV4", color="blue",
                                             vehicle_class=cls.crossover, size_variant=cls.two_rows)
        cls.full_detail = Service.objects.get(name="Full Detail")
        cls.monthly = Service.objects.get(name="Monthly Maintenance")
        cls.carpet = Service.objects.get(name="Carpet Extraction")
        cls.seats = Service.objects.get(name="Seat Extraction")

    def setUp(self):
        self.client.force_login(self.owner_user)

    def booking_data(self, day, **changes):
        data = {
            "vehicle": self.vehicle.pk,
            "address": self.address.pk,
            "date": day.isoformat(),
            "time": "08:00",
            "service": self.full_detail.pk,
            "vehicle_class": self.crossover.pk,
            "size_variant": self.two_rows.pk,
            "condition_level": "1",
            "crew_size": "",
            "repeat": "",
            "visits": "12",
            "notes": "",
        }
        data.update(changes)
        return {key: value for key, value in data.items() if value is not None}
