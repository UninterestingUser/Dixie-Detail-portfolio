"""The pricebook: services, numbered versions holding prices and rules, and
the quotes priced from them.

Prices are loaded from data/price-matrix.csv and the rules from
data/pricing-rules.yaml by the load_pricebook command; no price is written in
code. A version is edited as a draft and, once published, never changes
(decision 0033). A change is a new draft that becomes the next version. The
prices themselves are worked out by pricebook.pricing.
"""

from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core.fields import HoursField, MoneyField, PercentField
from vehicles.models import check_size_variant_class


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
        """Publish a draft with an effective date, today or later
        (pricebook-changes.md). From then on the version never changes."""
        if self.is_published:
            raise PublishedVersionError(f"Version {self.number} is already published.")
        if effective_date < timezone.localdate():
            raise ValueError("The effective date must be today or later.")
        self.status = self.Status.PUBLISHED
        self.effective_date = effective_date
        self.published_at = timezone.now()
        self.save()

    @classmethod
    def current(cls, on=None):
        """The published version in effect on a date (today by default), or
        None before the first one takes effect."""
        on = on or timezone.localdate()
        return (
            cls.objects.filter(status=cls.Status.PUBLISHED, effective_date__lte=on)
            .order_by("-effective_date", "-number")
            .first()
        )

    @classmethod
    @transaction.atomic
    def new_draft(cls, notes=""):
        """A new draft numbered after every existing version, holding a copy of
        the latest published version's prices and rules to edit."""
        last = cls.objects.order_by("-number").first()
        draft = cls.objects.create(number=(last.number + 1) if last else 1, notes=notes)
        source = cls.objects.filter(status=cls.Status.PUBLISHED).order_by("-number").first()
        if source:
            for model in (Price, DerivedPriceRule, ConditionLevel, PricingRules):
                rows = model.objects.filter(version=source)
                if model is Price:
                    # A retired class or size variant is not priced again.
                    rows = rows.filter(vehicle_class__active=True).exclude(size_variant__active=False)
                for row in rows:
                    row.pk = None
                    row.id = None
                    row._state.adding = True
                    row.version = draft
                    row.save()
        return draft


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
    """One cell of the price matrix: a service's price and one-person service
    hours (setup and breakdown not included, decision 0058) for a vehicle class and, where it matters, a size variant. A class with no size
    variants, or a service that ignores size, has no size variant."""

    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="prices")
    vehicle_class = models.ForeignKey("vehicles.VehicleClass", on_delete=models.PROTECT)
    size_variant = models.ForeignKey("vehicles.SizeVariant", on_delete=models.PROTECT, null=True, blank=True)
    price = MoneyField()
    one_person_service_hours = HoursField()

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
        size = f", size {self.size_variant.value}" if self.size_variant else ""
        return f"{self.service} / {self.vehicle_class}{size}: {self.price}"

    def save(self, *args, **kwargs):
        check_size_variant_class(self.size_variant, self.vehicle_class_id)
        # A retired class or size variant is kept for history but not priced again.
        if self._state.adding and not self.vehicle_class.active:
            raise ValueError(f"{self.vehicle_class} is retired and cannot be priced.")
        if self._state.adding and self.size_variant and not self.size_variant.active:
            raise ValueError(f"{self.size_variant} is retired and cannot be priced.")
        super().save(*args, **kwargs)


class DerivedPriceRule(VersionContent):
    """A service priced as a percentage of another service for the same vehicle
    class and size variant, with that service's service hours: Quarterly
    Maintenance at 80% and Monthly Maintenance at 50% of Full Detail (pricing.md)."""

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
    """The crew and service-time numbers that go with a pricebook version. The
    full-day flag counts one-person time on site (decision 0058)."""

    version = models.OneToOneField(PricebookVersion, on_delete=models.CASCADE, related_name="rules")
    two_person_time_factor = models.DecimalField(max_digits=4, decimal_places=3)
    service_time_rounding_minutes = models.PositiveSmallIntegerField()
    full_day_time_on_site_hours = HoursField()

    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = "pricing rules"

    def __str__(self):
        return f"Pricing rules for version {self.version.number}"


class PricedLine(models.Model):
    """The fields a priced line carries, shared by quote lines and appointment
    lines so a booked appointment copies its quote's lines exactly (decision 0059).

    Every value is a copy; the links to the service, promotion, version,
    vehicle class and size variant are for reporting.
    """

    class Kind(models.TextChoices):
        SERVICE = "service", "Service"
        ADD_ON = "add_on", "Add-on"
        CONDITION = "condition", "Condition adjustment"
        CUSTOM = "custom", "Custom line"
        PROMOTION = "promotion", "Promotion"
        ADJUSTMENT = "adjustment", "On-site adjustment"
        NO_CHARGE = "no_charge", "No charge (gift)"

    position = models.PositiveSmallIntegerField(default=0)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    description = models.CharField(max_length=200)
    # Positive for a charge, negative for a promotion or a no-charge gift.
    amount = MoneyField()
    # Exact: a condition line carries the base hours times its percentage,
    # unrounded (decision 0065), which can need up to seven decimal places.
    one_person_service_hours = HoursField(max_digits=10, decimal_places=7, null=True, blank=True)
    # The vehicle class and size variant as priced, copied so renaming or
    # retiring either never changes a past job.
    vehicle_class_name = models.CharField(max_length=60, blank=True)
    size_variant_value = models.PositiveSmallIntegerField(null=True, blank=True)
    size_variant_label = models.CharField(max_length=100, blank=True)
    condition_level = models.PositiveSmallIntegerField(null=True, blank=True)
    service = models.ForeignKey(Service, on_delete=models.PROTECT, null=True, blank=True)
    promotion = models.ForeignKey("promotions.Promotion", on_delete=models.PROTECT, null=True, blank=True)
    pricebook_version = models.ForeignKey(PricebookVersion, on_delete=models.PROTECT, null=True, blank=True)
    vehicle_class = models.ForeignKey("vehicles.VehicleClass", on_delete=models.PROTECT, null=True, blank=True)
    size_variant = models.ForeignKey("vehicles.SizeVariant", on_delete=models.PROTECT, null=True, blank=True)

    # The fields copied from a quote line onto an appointment line.
    COPIED_FIELDS = [
        "position",
        "kind",
        "description",
        "amount",
        "one_person_service_hours",
        "vehicle_class_name",
        "size_variant_value",
        "size_variant_label",
        "condition_level",
        "service",
        "promotion",
        "pricebook_version",
        "vehicle_class",
        "size_variant",
    ]

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.description}: {self.amount}"


class QuoteChangeError(Exception):
    """Raised on an attempt to change a quote after it was issued."""


class Quote(models.Model):
    """A priced job issued by the server before booking: the price of record
    (decision 0059). The website books with a reference to a quote, never a
    price from the browser, and the quote's lines become the appointment's
    line snapshot. A quote never changes once issued; pricebook.pricing.issue_quote
    creates it.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    pricebook_version = models.ForeignKey(PricebookVersion, on_delete=models.PROTECT, related_name="quotes")
    # What was asked for.
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="+")
    vehicle_class = models.ForeignKey("vehicles.VehicleClass", on_delete=models.PROTECT, related_name="+")
    size_variant = models.ForeignKey(
        "vehicles.SizeVariant", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    condition_level = models.PositiveSmallIntegerField(null=True, blank=True)
    add_ons = models.ManyToManyField(Service, blank=True, related_name="+")
    promotions = models.ManyToManyField("promotions.Promotion", blank=True, related_name="+")
    crew_size = models.PositiveSmallIntegerField(choices=[(1, "1"), (2, "2")])
    # What it came to.
    total_before_tax = MoneyField()
    # Sales tax is zero until Phase 3 adds the rate for the service address.
    tax_rate = PercentField(default=0)
    sales_tax = MoneyField(default=0)
    total = MoneyField()
    # The exact sum of the lines' hours, before the crew factor and rounding.
    one_person_service_hours = HoursField(max_digits=10, decimal_places=7)
    service_minutes = models.PositiveIntegerField(help_text="Service time for the crew.")
    setup_minutes = models.PositiveIntegerField()
    breakdown_minutes = models.PositiveIntegerField()
    time_on_site_minutes = models.PositiveIntegerField()
    full_day = models.BooleanField(help_text="One-person time on site at or above the full-day threshold.")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Quote {self.pk}: {self.service} for {self.vehicle_class}, {self.total}"

    def save(self, *args, **kwargs):
        if self.pk and Quote.objects.filter(pk=self.pk).exists():
            raise QuoteChangeError("A quote never changes once issued.")
        super().save(*args, **kwargs)


class QuoteLine(PricedLine):
    """One priced line of a quote."""

    quote = models.ForeignKey(Quote, on_delete=models.CASCADE, related_name="lines")

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=["service", "add_on", "condition"], amount__gte=0)
                | Q(kind="promotion", amount__lte=0),
                name="quote_line_amount_sign_matches_kind",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and QuoteLine.objects.filter(pk=self.pk).exists():
            raise QuoteChangeError("A quote never changes once issued.")
        super().save(*args, **kwargs)
