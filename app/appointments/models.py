"""Appointments, their line snapshots, repeating series and closed days."""

from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from simple_history.models import HistoricalRecords

from billing.methods import PaymentMethod
from core.fields import MoneyField
from pricebook.models import PricedLine, Quote, Service


class RecurringSeries(models.Model):
    """Repeating Monthly or Quarterly Maintenance visits, booked by the owner."""

    class Frequency(models.TextChoices):
        MONTHLY = "monthly", "Monthly"
        QUARTERLY = "quarterly", "Quarterly"

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="series")
    vehicle = models.ForeignKey("vehicles.Vehicle", on_delete=models.PROTECT)
    service = models.ForeignKey(Service, on_delete=models.PROTECT)
    frequency = models.CharField(max_length=10, choices=Frequency.choices)
    starts_on = models.DateField()
    ends_on = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "recurring series"

    def __str__(self):
        return f"{self.get_frequency_display()} {self.service} for {self.customer}"


class Appointment(models.Model):
    """One job: one vehicle at one address on one day, with its priced lines."""

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        BOOKED = "booked", "Booked"
        COMPLETED = "completed", "Completed"
        CANCELED = "canceled", "Canceled"

    class Source(models.TextChoices):
        WEBSITE = "website", "Website"
        OWNER = "owner", "Owner"
        IMPORT = "import", "Imported"

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="appointments"
    )
    vehicle = models.ForeignKey(
        "vehicles.Vehicle", on_delete=models.PROTECT, null=True, blank=True, related_name="appointments"
    )
    service_address = models.ForeignKey(
        "customers.Address", on_delete=models.PROTECT, null=True, blank=True, related_name="appointments"
    )
    # Stored in UTC, shown in Eastern (decision 0048).
    scheduled_start = models.DateTimeField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.BOOKED)
    source = models.CharField(max_length=10, choices=Source.choices)
    crew_size = models.PositiveSmallIntegerField(choices=[(1, "1"), (2, "2")], default=1)
    # The times as booked, so a later settings or pricebook change never
    # alters them (decision 0056). Time on site is their sum. Empty on
    # imported jobs that did not record them.
    setup_minutes = models.PositiveIntegerField(null=True, blank=True)
    service_minutes = models.PositiveIntegerField(
        null=True, blank=True, help_text="Service time for the crew, rounded to 15 minutes."
    )
    breakdown_minutes = models.PositiveIntegerField(null=True, blank=True)
    # The quote a booking was made from (decision 0059). A quote books one appointment.
    quote = models.OneToOneField(
        Quote, on_delete=models.PROTECT, null=True, blank=True, related_name="appointment"
    )
    preferred_payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, blank=True)
    series = models.ForeignKey(
        RecurringSeries, on_delete=models.PROTECT, null=True, blank=True, related_name="appointments"
    )
    jobs_calendar_event_id = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    baserow_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-scheduled_start"]
        indexes = [models.Index(fields=["scheduled_start"])]

    def __str__(self):
        return f"{self.customer} on {self.scheduled_start:%Y-%m-%d}"

    @property
    def total_before_tax(self):
        return sum((line.amount for line in self.lines.all()), Decimal("0.00"))

    @property
    def is_no_charge(self):
        return self.lines.filter(kind=AppointmentLine.Kind.NO_CHARGE).exists()

    @property
    def time_on_site_minutes(self):
        """Setup + service time + breakdown, or None when any is missing."""
        parts = (self.setup_minutes, self.service_minutes, self.breakdown_minutes)
        return None if None in parts else sum(parts)

    @classmethod
    @transaction.atomic
    def book_from_quote(cls, quote, **fields):
        """Book an appointment from a quote: the quote's lines become its line
        snapshot exactly, and its crew and times are copied as booked. The
        price is never taken from anywhere else (decision 0059).

        fields are the appointment's own details, such as customer,
        scheduled_start and source.
        """
        if Appointment.objects.filter(quote=quote).exists():
            raise ValueError(f"Quote {quote.pk} is already booked.")
        appointment = cls.objects.create(
            quote=quote,
            crew_size=quote.crew_size,
            setup_minutes=quote.setup_minutes,
            service_minutes=quote.service_minutes,
            breakdown_minutes=quote.breakdown_minutes,
            **fields,
        )
        for quote_line in quote.lines.all():
            AppointmentLine.objects.create(
                appointment=appointment,
                **{name: getattr(quote_line, name) for name in PricedLine.COPIED_FIELDS},
            )
        return appointment


class AppointmentLine(PricedLine):
    """One priced line on an appointment, copied when it is booked.

    This is the line snapshot (decision 0033): every value is copied from the
    quote it was booked from (decision 0059), or from the pricebook, so a later
    pricebook change cannot alter a booked or completed job. The links to the
    service, promotion, version, vehicle class and size variant are for
    reporting; the copied fields are what was charged.
    """

    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="lines")
    reason = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(kind__in=["adjustment", "no_charge"]) | ~Q(reason=""),
                name="line_adjustment_has_reason",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=["service", "add_on", "condition", "custom"], amount__gte=0)
                | Q(kind__in=["promotion", "no_charge"], amount__lte=0)
                | Q(kind="adjustment"),
                name="line_amount_sign_matches_kind",
            ),
        ]

    @classmethod
    def snapshot(cls, appointment, price, **fields):
        """A new, unsaved line copied from a price in a published version."""
        if not price.version.is_published:
            raise ValueError("Appointments are priced from a published pricebook version.")
        service = price.service
        kind = cls.Kind.ADD_ON if service.kind == Service.Kind.ADD_ON else cls.Kind.SERVICE
        return cls(
            appointment=appointment,
            kind=kind,
            description=service.name,
            amount=price.price,
            one_person_service_hours=price.one_person_service_hours,
            vehicle_class_name=price.vehicle_class.name,
            size_variant_value=price.size_variant.value if price.size_variant else None,
            size_variant_label=price.size_variant.label if price.size_variant else "",
            vehicle_class=price.vehicle_class,
            size_variant=price.size_variant,
            service=service,
            pricebook_version=price.version,
            **fields,
        )


    @classmethod
    def for_promotion(cls, appointment, promotion, amount, **fields):
        """A new, unsaved promotion line taking the promotion's discount off
        amount. A voucher applies this way too (decision 0054)."""
        return cls(
            appointment=appointment,
            kind=cls.Kind.PROMOTION,
            description=promotion.name,
            amount=-promotion.discount_on(amount),
            promotion=promotion,
            **fields,
        )


class MatchFlag(models.Model):
    """A difference between a booking and the customer record it was quietly
    matched to, waiting for the owner (returning-customers.md, decision 0034)."""

    class Field(models.TextChoices):
        NAME = "name", "Name"
        ADDRESS = "address", "Address"
        VEHICLE = "vehicle", "Vehicle"

    class Resolution(models.TextChoices):
        UPDATE_RECORD = "update_record", "Update the record"
        KEEP_RECORD = "keep_record", "Keep the record"
        ADD_ALONGSIDE = "add_alongside", "Add alongside"
        MOVE_TO_NEW_CUSTOMER = "move_to_new_customer", "Move the booking to a new customer"

    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="match_flags")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="match_flags")
    field = models.CharField(max_length=10, choices=Field.choices)
    booked_value = models.TextField()
    record_value = models.TextField(blank=True)
    resolution = models.CharField(max_length=30, choices=Resolution.choices, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_field_display()} differs on {self.appointment}"


class RepricingDecision(models.Model):
    """The owner's choice for one booked job when a pricebook version is
    published (pricebook-changes.md). Every choice is logged."""

    class Choice(models.TextChoices):
        KEEP = "keep", "Keep booked price"
        USE_NEW = "use_new", "Use new price"
        CUSTOM = "custom", "Custom amount"

    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="repricing_decisions")
    pricebook_version = models.ForeignKey("pricebook.PricebookVersion", on_delete=models.PROTECT)
    choice = models.CharField(max_length=10, choices=Choice.choices)
    old_amount = MoneyField()
    new_amount = MoneyField()
    decided_at = models.DateTimeField(auto_now_add=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    def __str__(self):
        return f"{self.get_choice_display()} for {self.appointment}"


class DayClosure(models.Model):
    """A day closed for booking: a holiday, a day off or a Time Off calendar event."""

    class Source(models.TextChoices):
        CONTROL_APP = "control_app", "Control app"
        TIME_OFF_CALENDAR = "time_off_calendar", "Time Off calendar"

    date = models.DateField(unique=True)
    reason = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices)
    calendar_event_id = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["date"]

    def __str__(self):
        return f"Closed {self.date}"
