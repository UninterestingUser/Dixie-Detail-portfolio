"""Vehicle classes, the vehicle catalogue and customers' vehicles."""

from django.db import models
from django.db.models import Q
from simple_history.models import HistoricalRecords

SIZE_VARIANTS = [(1, "1"), (2, "2"), (3, "3")]


class VehicleClass(models.Model):
    """One of the six groups that set a price (data/vehicle-classes.yaml)."""

    class Measure(models.TextChoices):
        DOORS = "doors", "Doors"
        SEAT_ROWS = "seat_rows", "Seat rows"
        CAB_STYLE = "cab_style", "Cab style"

    name = models.CharField(max_length=60, unique=True)
    size_variant_measures = models.CharField(max_length=10, choices=Measure.choices)
    sort_order = models.PositiveSmallIntegerField(default=0)

    history = HistoricalRecords()

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "vehicle classes"

    def __str__(self):
        return self.name


class VehicleModel(models.Model):
    """A make and model over a range of years, with its vehicle class and size
    rule. Phase 2 fills these from EPA and NHTSA data (vehicle-classification.md)."""

    class SizeRule(models.TextChoices):
        ONE = "1", "1"
        TWO = "2", "2"
        THREE = "3", "3"
        ASK = "ask", "Ask the customer"

    class Source(models.TextChoices):
        EPA = "epa", "EPA"
        NHTSA = "nhtsa", "NHTSA"
        OWNER = "owner", "Owner"

    make = models.CharField(max_length=60)
    model = models.CharField(max_length=100)
    year_from = models.PositiveSmallIntegerField(null=True, blank=True)
    year_to = models.PositiveSmallIntegerField(null=True, blank=True)
    vehicle_class = models.ForeignKey(VehicleClass, on_delete=models.PROTECT, null=True, blank=True)
    size_rule = models.CharField(max_length=3, choices=SizeRule.choices, blank=True)
    source = models.CharField(max_length=10, choices=Source.choices)

    history = HistoricalRecords()

    class Meta:
        ordering = ["make", "model", "year_from"]

    def __str__(self):
        years = f"{self.year_from or '?'}-{self.year_to or ''}"
        return f"{self.make} {self.model} ({years})"


class Vehicle(models.Model):
    """A customer's vehicle. Year, make, model, class and size variant may be
    missing on older records; they are kept and flagged to fill in."""

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="vehicles"
    )
    vehicle_model = models.ForeignKey(VehicleModel, on_delete=models.PROTECT, null=True, blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    make = models.CharField(max_length=60, blank=True)
    model = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=40, blank=True)
    # Null for a vehicle not yet classed, or one off the price list such as a motorcycle.
    vehicle_class = models.ForeignKey(VehicleClass, on_delete=models.PROTECT, null=True, blank=True)
    size_variant = models.PositiveSmallIntegerField(choices=SIZE_VARIANTS, null=True, blank=True)
    notes = models.TextField(blank=True)
    baserow_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(size_variant__isnull=True) | Q(size_variant__in=[1, 2, 3]),
                name="vehicle_size_variant_1_to_3",
            )
        ]

    def __str__(self):
        return " ".join(str(part) for part in (self.year, self.make, self.model) if part) or "Vehicle"

    @property
    def missing_details(self):
        """The details still to fill in, such as ["year", "size variant"]."""
        missing = {
            "year": self.year,
            "make": self.make,
            "model": self.model,
            "vehicle class": self.vehicle_class_id,
            "size variant": self.size_variant,
        }
        return [name for name, value in missing.items() if not value]
