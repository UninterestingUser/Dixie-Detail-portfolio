"""Vehicle classes and their size variants, the vehicle catalogue and
customers' vehicles.

Vehicle classes and size variants are records, not choices in code: adding,
renaming or retiring one needs no code change or migration. The launch set is
in data/vehicle-classes.yaml. Nothing is deleted; a retired class or size
variant stays for history and is no longer offered or priced.
"""

from django.db import models
from simple_history.models import HistoricalRecords


class VehicleClass(models.Model):
    """A group of vehicles that share prices, such as Midsize SUVs."""

    name = models.CharField(max_length=60, unique=True)
    size_variant_measures = models.CharField(
        max_length=60,
        blank=True,
        help_text="What the size variant measures, such as doors, cab style or seat rows."
        " Empty for a class with a single price, such as motorcycles.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True, help_text="Off when the class is retired.")

    history = HistoricalRecords()

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "vehicle classes"

    def __str__(self):
        return self.name


class SizeVariant(models.Model):
    """One size within a vehicle class, such as "two doors" or "three rows".

    The value is the number in the price matrix's size column. A class with
    no size variants has one price per service.
    """

    vehicle_class = models.ForeignKey(VehicleClass, on_delete=models.PROTECT, related_name="size_variants")
    value = models.PositiveSmallIntegerField()
    label = models.CharField(max_length=100)
    active = models.BooleanField(default=True, help_text="Off when the size variant is retired.")

    history = HistoricalRecords()

    class Meta:
        ordering = ["vehicle_class", "value"]
        constraints = [
            models.UniqueConstraint(fields=["vehicle_class", "value"], name="one_size_variant_per_value")
        ]

    def __str__(self):
        return f"{self.vehicle_class}: {self.value} ({self.label})"


def check_size_variant_class(size_variant, vehicle_class_id):
    """Refuse a size variant that belongs to a different vehicle class."""
    if size_variant is not None and size_variant.vehicle_class_id != vehicle_class_id:
        raise ValueError(f"{size_variant} does not belong to that vehicle class.")


class VehicleModel(models.Model):
    """A make and model over a range of years, with its vehicle class and size
    rule. Phase 2 fills these from EPA and NHTSA data (vehicle-classification.md)."""

    class Source(models.TextChoices):
        EPA = "epa", "EPA"
        NHTSA = "nhtsa", "NHTSA"
        OWNER = "owner", "Owner"

    make = models.CharField(max_length=60)
    model = models.CharField(max_length=100)
    year_from = models.PositiveSmallIntegerField(null=True, blank=True)
    year_to = models.PositiveSmallIntegerField(null=True, blank=True)
    vehicle_class = models.ForeignKey(VehicleClass, on_delete=models.PROTECT, null=True, blank=True)
    # The size every vehicle of this model has, or empty with ask_size set
    # when the customer is asked, such as for an optional third row.
    size_variant = models.ForeignKey(SizeVariant, on_delete=models.PROTECT, null=True, blank=True)
    ask_size = models.BooleanField(default=False)
    source = models.CharField(max_length=10, choices=Source.choices)

    history = HistoricalRecords()

    class Meta:
        ordering = ["make", "model", "year_from"]

    def __str__(self):
        years = f"{self.year_from or '?'}-{self.year_to or ''}"
        return f"{self.make} {self.model} ({years})"

    def save(self, *args, **kwargs):
        check_size_variant_class(self.size_variant, self.vehicle_class_id)
        super().save(*args, **kwargs)


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
    size_variant = models.ForeignKey(SizeVariant, on_delete=models.PROTECT, null=True, blank=True)
    notes = models.TextField(blank=True)
    baserow_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    def __str__(self):
        return " ".join(str(part) for part in (self.year, self.make, self.model) if part) or "Vehicle"

    def save(self, *args, **kwargs):
        check_size_variant_class(self.size_variant, self.vehicle_class_id)
        super().save(*args, **kwargs)

    @property
    def missing_details(self):
        """The details still to fill in, such as ["year", "size variant"]."""
        missing = [
            name
            for name, value in (
                ("year", self.year),
                ("make", self.make),
                ("model", self.model),
                ("vehicle class", self.vehicle_class_id),
            )
            if not value
        ]
        # A class with no size variants, such as motorcycles, needs none.
        if self.size_variant_id is None and self.vehicle_class and self.vehicle_class.size_variants.exists():
            missing.append("size variant")
        return missing
