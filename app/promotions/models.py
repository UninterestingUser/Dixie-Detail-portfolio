"""Named promotions, such as Friends & Family, Multi-Vehicle or a seasonal
offer, and free vouchers (decision 0054)."""

from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.db.models import Q
from simple_history.models import HistoricalRecords

from core.fields import MoneyField


class Promotion(models.Model):
    class Kind(models.TextChoices):
        PERCENT_OFF = "percent_off", "Percentage off"
        AMOUNT_OFF = "amount_off", "Dollar amount off"
        FIXED_PRICE = "fixed_price", "Fixed price"
        VOUCHER = "voucher", "Free voucher"

    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    # A percentage for percent_off; dollars for amount_off, fixed_price and voucher.
    value = models.DecimalField(max_digits=10, decimal_places=2)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    promo_code = models.CharField(max_length=40, unique=True, null=True, blank=True)
    banner_text = models.CharField(max_length=200, blank=True)
    on_website = models.BooleanField(
        default=False, help_text="Usable in online booking. Otherwise the owner applies it."
    )
    services = models.ManyToManyField(
        "pricebook.Service", blank=True, help_text="Leave empty to apply to every service."
    )
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    history = HistoricalRecords(m2m_fields=[services])

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=Q(value__gte=0), name="promotion_value_not_negative"),
            models.CheckConstraint(
                condition=~Q(kind="percent_off") | Q(value__lte=100),
                name="promotion_percent_at_most_100",
            ),
            models.CheckConstraint(
                condition=Q(starts_on__isnull=True) | Q(ends_on__isnull=True) | Q(ends_on__gte=models.F("starts_on")),
                name="promotion_ends_after_start",
            ),
            models.CheckConstraint(
                condition=~Q(kind="voucher") | Q(promo_code__isnull=False),
                name="voucher_has_code",
            ),
        ]

    def __str__(self):
        return self.name

    def discount_on(self, amount):
        """How much this promotion takes off an amount before tax, never more
        than the amount itself."""
        if self.kind in (self.Kind.AMOUNT_OFF, self.Kind.VOUCHER):
            return min(self.value, amount)
        if self.kind == self.Kind.FIXED_PRICE:
            return max(amount - self.value, Decimal("0.00"))
        # Rounded to the nearest cent, an exact half cent up (decision 0055).
        return (amount * self.value / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
