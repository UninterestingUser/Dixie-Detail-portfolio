from decimal import Decimal

from django.db import IntegrityError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from appointments.models import Appointment
from billing.methods import PaymentMethod, website_methods
from billing.models import GiftCard, GiftCardBalanceError, Payment
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


class GiftCardTests(TestCase):
    """A gift card's balance is spent across jobs and never goes below zero (decision 0054)."""

    @classmethod
    def setUpTestData(cls):
        buyer = Customer.objects.create(first_name="Pat")
        cls.job_1 = Appointment.objects.create(
            customer=buyer, scheduled_start=timezone.now(), source=Appointment.Source.OWNER
        )
        cls.job_2 = Appointment.objects.create(
            customer=buyer, scheduled_start=timezone.now(), source=Appointment.Source.OWNER
        )
        cls.card = GiftCard.objects.create(
            code="GC-TEST-1",
            amount=Decimal("200.00"),
            buyer=buyer,
            recipient_name="Sam",
            sold_at=timezone.now(),
            sale_method=PaymentMethod.CARD,
        )

    def test_balance_goes_down_across_two_jobs(self):
        self.card.redeem(self.job_1, Decimal("120.00"), timezone.now())
        self.assertEqual(self.card.balance, Decimal("80.00"))
        self.card.redeem(self.job_2, Decimal("50.00"), timezone.now())
        self.assertEqual(self.card.balance, Decimal("30.00"))

    def test_card_never_goes_below_zero_and_the_rest_is_paid_another_way(self):
        self.card.redeem(self.job_1, Decimal("120.00"), timezone.now())
        payment = self.card.redeem(self.job_2, Decimal("150.00"), timezone.now())
        self.assertEqual(payment.amount, Decimal("80.00"))
        self.assertEqual(self.card.balance, Decimal("0.00"))
        Payment.objects.create(
            appointment=self.job_2, method=PaymentMethod.CASH, amount=Decimal("70.00"), paid_at=timezone.now()
        )
        self.assertEqual(sum(p.amount for p in self.job_2.payments.all()), Decimal("150.00"))
        with self.assertRaises(GiftCardBalanceError):
            self.card.redeem(self.job_2, Decimal("10.00"), timezone.now())

    def test_payment_larger_than_the_balance_is_refused(self):
        with self.assertRaises(GiftCardBalanceError):
            Payment.objects.create(
                appointment=self.job_1,
                method=PaymentMethod.GIFT_CARD,
                gift_card=self.card,
                amount=Decimal("200.01"),
                paid_at=timezone.now(),
            )

    def test_imported_gift_card_prepayment_needs_no_card(self):
        payment = Payment.objects.create(
            appointment=self.job_1, method=PaymentMethod.GIFT_CARD, amount=Decimal("90.00"), paid_at=timezone.now()
        )
        self.assertIsNone(payment.gift_card)
