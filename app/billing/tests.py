from decimal import Decimal

from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from appointments.models import Appointment
from billing.methods import PaymentMethod, website_methods
from billing.models import Payment
from customers.models import Customer


class PaymentMethodTests(SimpleTestCase):
    def test_check_and_trade_are_never_offered_on_the_website(self):
        offered = website_methods()
        self.assertNotIn(PaymentMethod.CHECK, offered)
        self.assertNotIn(PaymentMethod.TRADE, offered)
        self.assertNotIn(PaymentMethod.GIFT_CARD, offered)
        self.assertIn(PaymentMethod.CARD, offered)


class PaymentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        customer = Customer.objects.create(first_name="Pat")
        cls.appointment = Appointment.objects.create(
            customer=customer, scheduled_start=timezone.now(), source=Appointment.Source.OWNER
        )

    def pay(self, method, amount, **fields):
        return Payment.objects.create(
            appointment=self.appointment, method=method, amount=Decimal(amount), paid_at=timezone.now(), **fields
        )

    def test_trade_must_record_the_goods(self):
        with self.assertRaises(IntegrityError):
            self.pay(PaymentMethod.TRADE, "150.00")

    def test_trade_with_goods_is_accepted(self):
        payment = self.pay(PaymentMethod.TRADE, "150.00", goods_description="Two cords of firewood")
        self.assertEqual(payment.amount, Decimal("150.00"))

    def test_split_payment_and_short_payment_as_negative_tip(self):
        self.pay(PaymentMethod.CASH, "100.00")
        self.pay(PaymentMethod.CHECK, "45.00", tip=Decimal("-5.00"), reference="1042")
        payments = self.appointment.payments.all()
        self.assertEqual(sum(p.amount for p in payments), Decimal("145.00"))
        self.assertEqual(sum(p.tip for p in payments), Decimal("-5.00"))
