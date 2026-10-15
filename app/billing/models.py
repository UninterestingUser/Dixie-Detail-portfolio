"""Sales tax rates, invoices, gift cards, payments and refunds."""

from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from billing.methods import PaymentMethod
from core.fields import MoneyField, PercentField


class TaxJurisdiction(models.Model):
    """A state, county or city whose sales tax rate applies to an address."""

    class Kind(models.TextChoices):
        STATE = "state", "State"
        COUNTY = "county", "County"
        CITY = "city", "City"

    state = models.CharField(max_length=2)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=Kind.choices)

    class Meta:
        ordering = ["state", "name"]
        constraints = [
            models.UniqueConstraint(fields=["state", "name", "kind"], name="unique_tax_jurisdiction")
        ]

    def __str__(self):
        return f"{self.name}, {self.state}"


class TaxRate(models.Model):
    """A jurisdiction's rates from a date (sales-tax.md). A job is taxed at the
    rate in effect on the day of service."""

    jurisdiction = models.ForeignKey(TaxJurisdiction, on_delete=models.PROTECT, related_name="rates")
    state_rate = PercentField()
    local_rate = PercentField()
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["jurisdiction", "-effective_from"]
        constraints = [
            models.UniqueConstraint(fields=["jurisdiction", "effective_from"], name="one_rate_per_start_date")
        ]

    def __str__(self):
        return f"{self.jurisdiction}: {self.state_rate}% + {self.local_rate}% from {self.effective_from}"


class Invoice(models.Model):
    """The bill for a completed appointment, with the tax as charged. Rates and
    amounts are copied so a later rate change cannot alter it."""

    appointment = models.OneToOneField(
        "appointments.Appointment", on_delete=models.PROTECT, related_name="invoice"
    )
    number = models.CharField(max_length=20, unique=True)
    issued_at = models.DateTimeField(default=timezone.now)
    tax_jurisdiction = models.ForeignKey(TaxJurisdiction, on_delete=models.PROTECT, null=True, blank=True)
    state_rate = PercentField()
    local_rate = PercentField()
    taxable_amount = MoneyField()
    state_tax = MoneyField()
    local_tax = MoneyField()
    total = MoneyField()

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return f"Invoice {self.number}"


class GiftCardBalanceError(Exception):
    """Raised when a payment would take a gift card below zero."""


class GiftCard(models.Model):
    """A gift card sold as a dollar balance, sales tax included (decision 0054).

    The balance is money owed until it is used, and can be spent across several
    jobs. Each use is a gift-card payment on a job; the balance is the amount
    sold less those payments, and never goes below zero.
    """

    code = models.CharField(max_length=40, unique=True)
    amount = MoneyField(help_text="The balance when sold, sales tax included.")
    buyer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="gift_cards_bought"
    )
    # A recipient who is not yet a customer is named here until they book.
    recipient = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="gift_cards_received",
    )
    recipient_name = models.CharField(max_length=150, blank=True)
    sold_at = models.DateTimeField()
    sale_method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    sale_reference = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    export_batch = models.ForeignKey(
        "bookkeeping.ExportBatch", on_delete=models.PROTECT, null=True, blank=True, related_name="gift_cards"
    )

    class Meta:
        ordering = ["-sold_at"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="gift_card_amount_positive"),
        ]

    def __str__(self):
        return f"Gift card {self.code}"

    def used(self, excluding=None):
        payments = self.payments.all()
        if excluding is not None:
            payments = payments.exclude(pk=excluding)
        return payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    @property
    def balance(self):
        return self.amount - self.used()

    def redeem(self, appointment, amount_due, paid_at, **fields):
        """Pay as much of amount_due as the balance allows, and return the
        payment. The rest of the bill is paid another way."""
        with transaction.atomic():
            card = GiftCard.objects.select_for_update().get(pk=self.pk)
            amount = min(card.balance, amount_due)
            if amount <= 0:
                raise GiftCardBalanceError(f"Gift card {card.code} has no balance left.")
            return Payment.objects.create(
                appointment=appointment,
                method=PaymentMethod.GIFT_CARD,
                gift_card=card,
                amount=amount,
                paid_at=paid_at,
                reference=card.code,
                **fields,
            )


class Payment(models.Model):
    """Money, or goods in a trade, received for an appointment.

    A job paid two ways has two payments. A gift card or prepayment is a
    payment recorded before the job. The tip may be negative: a customer who
    paid less than the total is recorded with a negative tip. A gift-card
    payment uses a card's balance; the one imported gift-card job has no card
    and stays a plain prepayment (decision 0054).
    """

    appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.PROTECT, related_name="payments"
    )
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    # Toward the job, excluding the tip. For a trade, the value of the goods.
    amount = MoneyField()
    tip = MoneyField(default=0)
    paid_at = models.DateTimeField()
    reference = models.CharField(
        max_length=200, blank=True, help_text="Processor reference, check number or gift card number."
    )
    goods_description = models.TextField(blank=True, help_text="For a trade: what was received.")
    gift_card = models.ForeignKey(
        GiftCard, on_delete=models.PROTECT, null=True, blank=True, related_name="payments"
    )
    processor_fee = MoneyField(null=True, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    export_batch = models.ForeignKey(
        "bookkeeping.ExportBatch", on_delete=models.PROTECT, null=True, blank=True, related_name="payments"
    )

    class Meta:
        ordering = ["paid_at"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gte=0), name="payment_amount_not_negative"),
            models.CheckConstraint(
                condition=~Q(method="trade") | ~Q(goods_description=""),
                name="trade_records_goods",
            ),
            models.CheckConstraint(
                condition=Q(gift_card__isnull=True) | Q(method="gift_card"),
                name="gift_card_payment_method",
            ),
        ]

    def __str__(self):
        return f"{self.get_method_display()} {self.amount} for {self.appointment}"

    def save(self, *args, **kwargs):
        if self.gift_card_id is None:
            return super().save(*args, **kwargs)
        with transaction.atomic():
            # Lock the card so two payments cannot both spend the same balance.
            card = GiftCard.objects.select_for_update().get(pk=self.gift_card_id)
            if self.amount > card.amount - card.used(excluding=self.pk):
                raise GiftCardBalanceError(f"Gift card {card.code} does not have {self.amount} left.")
            super().save(*args, **kwargs)


class Refund(models.Model):
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    amount = MoneyField()
    tax_refunded = MoneyField(default=0)
    reason = models.TextField()
    refunded_at = models.DateTimeField()
    export_batch = models.ForeignKey(
        "bookkeeping.ExportBatch", on_delete=models.PROTECT, null=True, blank=True, related_name="refunds"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="refund_amount_positive"),
            models.CheckConstraint(condition=~Q(reason=""), name="refund_has_reason"),
        ]

    def __str__(self):
        return f"Refund {self.amount} on {self.payment}"
