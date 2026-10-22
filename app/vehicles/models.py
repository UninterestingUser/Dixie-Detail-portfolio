"""Vehicle classes and their size variants, the vehicle catalog with its
facts per model year, and customers' vehicles.

Vehicle classes and size variants are records, not choices in code: adding,
renaming or retiring one needs no code change or migration. The launch set is
in data/vehicle-classes.yaml. Nothing is deleted; a retired class or size
variant stays for history and is no longer offered or priced.
"""

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords


class VehicleClass(models.Model):
    """A group of vehicles that share prices, such as Midsize SUVs."""

    class PriceBasis(models.TextChoices):
        # The only basis built. Another, such as per foot of length for RVs,
        # would be a new choice here and a new basis in pricebook.pricing
        # (decision 0060).
        PRICE_LIST = "price_list", "Fixed price list"

    name = models.CharField(max_length=60, unique=True)
    size_variant_measures = models.CharField(
        max_length=60,
        blank=True,
        help_text="What the size variant measures, such as doors, cab style or seat rows."
        " Empty for a class with a single price, such as motorcycles.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True, help_text="Off when the class is retired.")
    price_basis = models.CharField(
        max_length=20,
        choices=PriceBasis.choices,
        default=PriceBasis.PRICE_LIST,
        help_text="How the class is priced. Only the fixed price list is built.",
    )

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
    """A make and model that a customer picks and a vehicle class applies to,
    such as "Toyota RAV4". Its facts are kept per model year and per source in
    VehicleModelYear; year_from and year_to span its model years.

    import_vehicle_data fills these from EPA and NHTSA data
    (vehicle-classification.md). It never changes a record whose source is
    "owner". The owner can split one make and model into several records by
    year range, such as two generations with different vehicle classes, and
    the import then files each model year under the record whose range holds it.
    """

    class Source(models.TextChoices):
        EPA = "epa", "EPA"
        NHTSA = "nhtsa", "NHTSA"
        OWNER = "owner", "Owner"

    class VehicleType(models.TextChoices):
        VEHICLE = "vehicle", "Car, truck or van"
        MOTORCYCLE = "motorcycle", "Motorcycle"

    make = models.CharField(max_length=60)
    model = models.CharField(max_length=100)
    year_from = models.PositiveSmallIntegerField(null=True, blank=True)
    year_to = models.PositiveSmallIntegerField(null=True, blank=True)
    # Motorcycles share the booking form's year, make and model lists with
    # cars, and a motorcycle and a car of the same name are different models.
    vehicle_type = models.CharField(max_length=12, choices=VehicleType.choices, default=VehicleType.VEHICLE)
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


class VehicleModelYear(models.Model):
    """One source's facts about one model year of a vehicle model, such as
    the EPA's facts about the 2019 Toyota RAV4.

    A source lists a model year several times (the EPA once per engine and
    transmission, the Canadian specifications once per trim), so each fact is
    the set of values or the range across those rows. Each source has its own
    row, so one source never overwrites another. A row with source "owner"
    holds the owner's own figures, and no import touches it.
    """

    class Source(models.TextChoices):
        EPA = "epa", "EPA FuelEconomy.gov"
        VPIC = "vpic", "NHTSA vPIC"
        CANADA = "canada", "NHTSA vPIC Canadian specifications"
        OWNER = "owner", "Owner"

    vehicle_model = models.ForeignKey(VehicleModel, on_delete=models.PROTECT, related_name="model_years")
    year = models.PositiveSmallIntegerField()
    source = models.CharField(max_length=10, choices=Source.choices)

    epa_size_classes = models.JSONField(
        default=list, blank=True, help_text="EPA size classes, such as Small Sport Utility Vehicle 4WD."
    )
    drives = models.JSONField(default=list, blank=True, help_text="Such as Front-Wheel Drive.")
    body_styles = models.JSONField(
        default=list,
        blank=True,
        help_text='Any of two-door, four-door and hatchback, or "unknown" when the source lists none,'
        " as the EPA does for pickups, vans and most SUVs.",
    )
    source_vehicle_types = models.JSONField(
        default=list, blank=True, help_text="The source's own vehicle types, such as vPIC's Truck or Motorcycle."
    )
    # Ranges across the source's rows for the model year. Volumes are in
    # cubic feet, weights in pounds and lengths in inches.
    passenger_volume_min = models.PositiveSmallIntegerField(null=True, blank=True)
    passenger_volume_max = models.PositiveSmallIntegerField(null=True, blank=True)
    luggage_volume_min = models.PositiveSmallIntegerField(null=True, blank=True)
    luggage_volume_max = models.PositiveSmallIntegerField(null=True, blank=True)
    gvwr_min = models.PositiveIntegerField(null=True, blank=True)
    gvwr_max = models.PositiveIntegerField(null=True, blank=True)
    curb_weight_min = models.PositiveIntegerField(null=True, blank=True)
    curb_weight_max = models.PositiveIntegerField(null=True, blank=True)
    length_min = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    length_max = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    width_min = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    width_max = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    height_min = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    height_max = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    wheelbase_min = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    wheelbase_max = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)

    source_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="The source's own ids for the rows behind this one: EPA vehicle ids,"
        " vPIC make and model ids, or the Canadian specifications' trim names.",
    )
    first_seen = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now, help_text="The last import that found this row.")

    class Meta:
        ordering = ["vehicle_model", "year", "source"]
        constraints = [
            models.UniqueConstraint(fields=["vehicle_model", "year", "source"], name="one_model_year_per_source")
        ]

    def __str__(self):
        return f"{self.year} {self.vehicle_model.make} {self.vehicle_model.model} ({self.get_source_display()})"


class VehicleDataImportRun(models.Model):
    """One run of import_vehicle_data for one source, so the monthly refresh
    can tell when each source last loaded and what it changed."""

    class Result(models.TextChoices):
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    source = models.CharField(max_length=10, choices=VehicleModelYear.Source.choices)
    dry_run = models.BooleanField()
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField()
    result = models.CharField(max_length=10, choices=Result.choices)
    counts = models.JSONField(default=dict, blank=True)
    message = models.TextField(blank=True, help_text="Why a failed run stopped.")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        kind = "dry run" if self.dry_run else "run"
        return f"{self.get_source_display()} {kind} {self.started_at:%Y-%m-%d %H:%M}: {self.result}"


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
        """Year, make and model, then the color, such as "2019 Honda Accord,
        silver", so a customer's identical vehicles can be told apart
        wherever vehicles are listed or picked (decision 0067)."""
        name = " ".join(str(part) for part in (self.year, self.make, self.model) if part) or "Vehicle"
        return f"{name}, {self.color.strip()}" if self.color.strip() else name

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
