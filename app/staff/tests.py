import datetime
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment
from customers.models import Customer
from staff.models import Assignment, PayType, StaffMember, StaffPayout

# Invented pay figures.
JOB_PAY = Decimal("60.00")


class HelperPayTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        customer = Customer.objects.create(first_name="Pat")
        cls.appointment = Appointment.objects.create(
            customer=customer, scheduled_start=timezone.now(), source=Appointment.Source.OWNER
        )

    def helper(self, pay_type, name="Helper"):
        return StaffMember.objects.create(
            name=name, role=StaffMember.Role.HELPER, pay_type=pay_type, default_job_pay=JOB_PAY
        )

    def test_every_helper_needs_a_pay_type(self):
        with self.assertRaises(IntegrityError):
            StaffMember.objects.create(name="Helper", role=StaffMember.Role.HELPER)

    def test_owner_has_no_pay_type(self):
        owner = StaffMember.objects.create(name="Owner", role=StaffMember.Role.OWNER)
        self.assertEqual(owner.pay_type, "")

    def test_flat_pay_and_override_work_for_both_pay_types(self):
        for pay_type in PayType:
            with self.subTest(pay_type=pay_type):
                assignment = Assignment.objects.create(appointment=self.appointment, staff_member=self.helper(pay_type, pay_type))
                self.assertEqual(assignment.pay, JOB_PAY)
                assignment.pay_override = Decimal("75.00")
                assignment.save()
                self.assertEqual(assignment.pay, Decimal("75.00"))

    def test_payout_keeps_the_pay_type_it_was_made_under(self):
        helper = self.helper(PayType.FAMILY_HELPER)
        payout = StaffPayout.objects.create(
            staff_member=helper, amount=JOB_PAY, method=StaffPayout.Method.CASH, paid_on=datetime.date(2026, 10, 14)
        )
        helper.pay_type = PayType.EMPLOYEE
        helper.save()
        payout.refresh_from_db()
        self.assertEqual(payout.pay_type, PayType.FAMILY_HELPER)
