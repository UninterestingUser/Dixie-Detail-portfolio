"""Vehicle classes and their size variants, the vehicle catalog with its
facts per model year, the classification rules and overrides with each model
year's result, and customers' vehicles.

Vehicle classes and size variants are records, not choices in code: adding,
renaming or retiring one needs no code change or migration. The launch set is
in data/vehicle-classes.yaml. Nothing is deleted; a retired class or size
variant stays for history and is no longer offered or priced.
"""

from django.conf import settings
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

    class Measures(models.TextChoices):
        DOORS = "doors", "Doors"
        CAB_STYLE = "cab style", "Cab style"
        SEAT_ROWS = "seat rows", "Seat rows"
        NONE = "none", "None (one price)"

    class Booking(models.TextChoices):
        ONLINE = "online", "Booked online"
        QUOTE = "quote", "Ask for a quote"

    name = models.CharField(max_length=60, unique=True)
    size_variant_measures = models.CharField(
        max_length=60,
        choices=Measures.choices,
        default=Measures.NONE,
        help_text="What the size variant measures. None for a class with a single price, such as Motorcycles.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True, help_text="Off when the class is retired.")
    price_basis = models.CharField(
        max_length=20,
        choices=PriceBasis.choices,
        default=PriceBasis.PRICE_LIST,
        help_text="How the class is priced. Only the fixed price list is built.",
    )
    booking = models.CharField(
        max_length=10,
        choices=Booking.choices,
        default=Booking.ONLINE,
        help_text="Whether customers book the class online or ask for a quote.",
    )
    photo_card = models.CharField(
        max_length=120,
        blank=True,
        help_text="The caption of the class's photo card, shown when a vehicle is not in the catalog.",
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
    VehicleModelYear; year_from and year_to span its model years. Its vehicle
    class and size variant are worked out per model year by classify_vehicles
    (ModelYearClassification), or set by the owner with a ModelOverride.

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
    ask_size = models.BooleanField(
        default=False,
        help_text="The booking form asks the size (doors, cab or third row) for at least one model year."
        " Set by classify_vehicles; each model year's answer is in its classification.",
    )
    source = models.CharField(max_length=10, choices=Source.choices)

    history = HistoricalRecords()

    class Meta:
        ordering = ["make", "model", "year_from"]

    def __str__(self):
        years = f"{self.year_from or '?'}-{self.year_to or ''}"
        return f"{self.make} {self.model} ({years})"


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
        # data/third-row-seating.yaml, the owner-approved list, written by
        # classify_vehicles.
        SEAT_LIST = "seat_list", "Third-row seating list"
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
    cab_styles = models.JSONField(
        default=list,
        blank=True,
        help_text="Any of regular, extended and crew, from the Canadian specifications' trim names.",
    )
    seat_rows = models.JSONField(
        default=list,
        blank=True,
        help_text="The numbers of seat rows sold, such as [2, 3] for an optional third row.",
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


class ClassificationRule(models.Model):
    """One rule of the ordered list that gives a model year its vehicle class
    (decision 0060). The first active rule, by position, whose conditions all
    hold wins. conditions maps a fact to what it must be, such as
    {"epa_size_class": ["Small Sport Utility Vehicle 4WD"], "curb_weight": {"over": 4500}};
    the facts and their forms are in vehicles.classification.rules.FACTS.
    A saved change takes effect when classify_vehicles next applies the rules.
    """

    position = models.PositiveSmallIntegerField(help_text="Rules are tried from the lowest position up.")
    name = models.CharField(max_length=120)
    conditions = models.JSONField(default=dict, blank=True)
    vehicle_class = models.ForeignKey(VehicleClass, on_delete=models.PROTECT, related_name="+")
    active = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return f"{self.position}. {self.name} -> {self.vehicle_class}"

    def clean(self):
        from django.core.exceptions import ValidationError

        from .classification.rules import condition_errors

        errors = condition_errors(self.conditions)
        if errors:
            raise ValidationError({"conditions": errors})


class ModelOverride(models.Model):
    """The owner's vehicle class for a vehicle model, which beats every rule,
    such as Jeep Wrangler to Light Pickups & Offroad. It covers the model's
    years from year_from to year_to, or all of them when both are empty. The
    size variant is fixed, always asked, or, with neither, worked out from the
    facts as for any vehicle of the class."""

    vehicle_model = models.ForeignKey(VehicleModel, on_delete=models.PROTECT, related_name="overrides")
    year_from = models.PositiveSmallIntegerField(null=True, blank=True)
    year_to = models.PositiveSmallIntegerField(null=True, blank=True)
    vehicle_class = models.ForeignKey(VehicleClass, on_delete=models.PROTECT, related_name="+")
    size_variant = models.ForeignKey(SizeVariant, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    ask_size = models.BooleanField(default=False, help_text="Always ask the customer the size.")
    # Empty for the launch overrides seeded from data/vehicle-classes.yaml.
    set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    set_at = models.DateTimeField(default=timezone.now)
    note = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["vehicle_model", "year_from"]

    def __str__(self):
        years = f" {self.year_from or ''}-{self.year_to or ''}" if self.year_from or self.year_to else ""
        return f"{self.vehicle_model.make} {self.vehicle_model.model}{years} -> {self.vehicle_class}"

    def covers(self, year):
        return (self.year_from is None or year >= self.year_from) and (self.year_to is None or year <= self.year_to)

    def save(self, *args, **kwargs):
        check_size_variant_class(self.size_variant, self.vehicle_class_id)
        super().save(*args, **kwargs)


class ModelYearClassification(models.Model):
    """The vehicle class and size of one model year, as classify_vehicles
    last applied the rules and overrides: what the booking form uses.

    A model year no rule settles cleanly waits in the review queue
    (in_review, with the reasons) instead of going live. One that was live
    before keeps its earlier class while it waits; a new one has none, and
    the booking form falls back to the photo cards.
    """

    class Method(models.TextChoices):
        RULE = "rule", "Rule"
        OVERRIDE = "override", "Model override"
        REVIEW = "review", "Review queue"

    vehicle_model = models.ForeignKey(VehicleModel, on_delete=models.PROTECT, related_name="classifications")
    year = models.PositiveSmallIntegerField()
    vehicle_class = models.ForeignKey(VehicleClass, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    size_variant = models.ForeignKey(SizeVariant, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    ask_size = models.BooleanField(default=False, help_text="The booking form asks the size.")
    method = models.CharField(max_length=10, choices=Method.choices)
    rule = models.ForeignKey(ClassificationRule, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    override = models.ForeignKey(ModelOverride, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    in_review = models.BooleanField(default=False)
    review_reasons = models.JSONField(default=list, blank=True)
    classified_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["vehicle_model", "year"]
        constraints = [
            models.UniqueConstraint(fields=["vehicle_model", "year"], name="one_classification_per_model_year")
        ]

    def __str__(self):
        found = self.vehicle_class or "no class"
        return f"{self.year} {self.vehicle_model.make} {self.vehicle_model.model}: {found}"

    @property
    def live(self):
        return self.vehicle_class_id is not None


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
    # A per-vehicle override, such as for a lifted or modified vehicle: when
    # set, this vehicle's class and size variant beat the model override and
    # the rules.
    class_override_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    class_override_at = models.DateTimeField(null=True, blank=True)
    class_override_note = models.TextField(blank=True)
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
    def class_overridden(self):
        return self.class_override_at is not None and self.vehicle_class_id is not None

    def override_class(self, vehicle_class, size_variant=None, user=None, note=""):
        """Set this vehicle's own class and size variant, which then beat the
        model override and the rules."""
        self.vehicle_class, self.size_variant = vehicle_class, size_variant
        self.class_override_by, self.class_override_at, self.class_override_note = user, timezone.now(), note
        self.save()

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
