"""The pricebook: services, and numbered versions holding prices and rules.

Prices are loaded from data/price-matrix.csv and the rules from
data/pricing-rules.yaml; no price is written in code. A version is edited as
a draft and, once published, never changes (decision 0033). A change is a new
draft that becomes the next version.
"""

from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core.fields import HoursField, MoneyField, PercentField
from vehicles.models import SIZE_VARIANTS


class PublishedVersionError(Exception):
    """Raised on an attempt to change a published pricebook version."""


class PricebookVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    number = models.PositiveIntegerField(unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    effective_date = models.DateField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status="draft") | Q(effective_date__isnull=False, published_at__isnull=False),
                name="published_version_has_dates",
            )
        ]

    def __str__(self):
        return f"Pricebook version {self.number} ({self.get_status_display()})"

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED

    def save(self, *args, **kwargs):
        if self.pk and PricebookVersion.objects.filter(pk=self.pk, status=self.Status.PUBLISHED).exists():
            raise PublishedVersionError(f"Version {self.number} is published and cannot change.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_published:
            raise PublishedVersionError(f"Version {self.number} is published and cannot be deleted.")
        return super().delete(*args, **kwargs)

    def publish(self, effective_date):
        self.status = self.Status.PUBLISHED
        self.effective_date = effective_date
        self.published_at = timezone.now()
        self.save()


class VersionContent(models.Model):
    """A row that belongs to one pricebook version and is locked once that
    version is published."""

    version = models.ForeignKey(PricebookVersion, on_delete=models.CASCADE)

    class Meta:
        abstract = True

    def refuse_if_published(self):
        if PricebookVersion.objects.filter(
            pk=self.version_id, status=PricebookVersion.Status.PUBLISHED
        ).exists():
            raise PublishedVersionError("This pricebook version is published and cannot change.")

    def save(self, *args, **kwargs):
        self.refuse_if_published()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.refuse_if_published()
        return super().delete(*args, **kwargs)


class Service(models.Model):
    """A service the business sells or has sold (data/services.yaml)."""

    class Kind(models.TextChoices):
        MAIN = "main", "Main service"
        ADD_ON = "add_on", "Add-on"
        MAINTENANCE_PLAN = "maintenance_plan", "Maintenance plan"
        CUSTOM = "custom", "Custom line"

    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    description = models.TextField(blank=True)
    condition_applies = models.BooleanField(default=False)
    customer_bookable = models.BooleanField(
        default=False, help_text="Offered on the website. Maintenance plans and custom lines are not."
    )
    on_price_list = models.BooleanField(
        default=True, help_text="Off for past services that are no longer priced."
    )
    default_crew_size = models.PositiveSmallIntegerField(choices=[(1, "1"), (2, "2")], default=1)

    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Price(VersionContent):
    """One cell of the price matrix: a service's price and one-person hours for
    a vehicle class and, where it matters, a size variant."""

    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="prices")
    vehicle_class = models.ForeignKey("vehicles.VehicleClass", on_delete=models.PROTECT)
    size_variant = models.PositiveSmallIntegerField(choices=SIZE_VARIANTS, null=True, blank=True)
    price = MoneyField()
    one_person_hours = HoursField()

    history = HistoricalRecords()

    class Meta:
        default_related_name = "prices"
        constraints = [
            models.UniqueConstraint(
                fields=["version", "service", "vehicle_class", "size_variant"],
                nulls_distinct=False,
                name="one_price_per_matrix_cell",
            ),
            models.CheckConstraint(condition=Q(price__gte=0), name="price_not_negative"),
        ]

    def __str__(self):
        size = f", size {self.size_variant}" if self.size_variant else ""
        return f"{self.service} / {self.vehicle_class}{size}: {self.price}"


class DerivedPriceRule(VersionContent):
    """A service priced as a percentage of another service for the same vehicle
    class and size variant, with that service's hours: Quarterly Maintenance at
    80% and Monthly Maintenance at 50% of Full Detail (pricing.md)."""

    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="+")
    base_service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="+")
    percent = PercentField()

    history = HistoricalRecords()

    class Meta:
        default_related_name = "derived_price_rules"
        constraints = [
            models.UniqueConstraint(fields=["version", "service"], name="one_derived_rule_per_service")
        ]

    def __str__(self):
        return f"{self.service} = {self.percent}% of {self.base_service}"


class ConditionLevel(VersionContent):
    """One of the three condition levels and the percentage it adds."""

    level = models.PositiveSmallIntegerField(choices=[(1, "1"), (2, "2"), (3, "3")])
    adjustment_percent = PercentField()
    label = models.CharField(max_length=60, blank=True)
    description = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        default_related_name = "condition_levels"
        ordering = ["level"]
        constraints = [
            models.UniqueConstraint(fields=["version", "level"], name="one_condition_level_per_number")
        ]

    def __str__(self):
        return f"Condition level {self.level} (+{self.adjustment_percent}%)"


class PricingRules(VersionContent):
    """The crew and job-length numbers that go with a pricebook version."""

    version = models.OneToOneField(PricebookVersion, on_delete=models.CASCADE, related_name="rules")
    two_person_time_factor = models.DecimalField(max_digits=4, decimal_places=3)
    job_time_rounding_minutes = models.PositiveSmallIntegerField()
    full_day_threshold_hours = HoursField()

    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = "pricing rules"

    def __str__(self):
        return f"Pricing rules for version {self.version.number}"
