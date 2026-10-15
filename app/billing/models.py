"""Sales tax rates, invoices, payments and refunds."""

from django.conf import settings
from django.db import models
from django.db.models import Q
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


class Payment(models.Model):
    """Money, or goods in a trade, received for an appointment.

    A job paid two ways has two payments. A gift card or prepayment is a
    payment recorded before the job. The tip may be negative: a customer who
    paid less than the total is recorded with a negative tip.
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
        ]

    def __str__(self):
        return f"{self.get_method_display()} {self.amount} for {self.appointment}"


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
