"""Customers, their second contacts, service addresses and text consents."""

from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from core.fields import PhoneField, format_phone, phone_check


class Customer(models.Model):
    """A person or company the business works for."""

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    company = models.CharField(max_length=150, blank=True)
    # Some imported customers have no number; they are kept (data-migration.md).
    mobile = PhoneField(blank=True, db_index=True)
    email = models.EmailField(blank=True)
    source = models.CharField(
        max_length=100, blank=True, help_text="Where the customer came from, such as a referral."
    )
    notes = models.TextField(blank=True)
    # The Baserow row this customer was imported from (decision 0051).
    baserow_id = models.PositiveIntegerField(null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["last_name", "first_name"]
        constraints = [phone_check("mobile", "customer_mobile_10_digits")]

    def __str__(self):
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    @property
    def mobile_display(self):
        return format_phone(self.mobile)

    def has_consent(self, kind):
        """Whether the customer's latest recorded answer for this kind is yes."""
        latest = self.consents.filter(kind=kind).order_by("-recorded_at", "-id").first()
        return bool(latest and latest.granted)


class SecondContact(models.Model):
    """Another person on a customer's record, such as a spouse, with their own
    name and number. A booking under that number matches the customer."""

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="second_contacts")
    name = models.CharField(max_length=150)
    phone = PhoneField(db_index=True)
    relationship = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [phone_check("phone", "second_contact_phone_10_digits")]

    def __str__(self):
        return f"{self.name} ({self.customer})"


class Address(models.Model):
    """A place where a job is done. It sets the sales tax and the drive time."""

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="addresses")
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    zip_code = models.CharField(max_length=10)
    county = models.CharField(max_length=100, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    google_place_id = models.CharField(max_length=300, blank=True)
    verified = models.BooleanField(
        default=False, help_text="Picked from Google's suggestions or checked by the owner."
    )
    tax_jurisdiction = models.ForeignKey(
        "billing.TaxJurisdiction", on_delete=models.PROTECT, null=True, blank=True
    )
    approved_out_of_area = models.BooleanField(
        default=False, help_text="Outside the service area, allowed by the owner (decision 0037)."
    )
    active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        verbose_name_plural = "addresses"

    def __str__(self):
        return f"{self.line1}, {self.city}, {self.state} {self.zip_code}"


class Consent(models.Model):
    """One recorded answer to a text consent question (text-messages.md).

    Rows are never edited: a STOP reply or a change of mind adds a new row
    with granted=False, so the consent history is kept.
    """

    class Kind(models.TextChoices):
        APPOINTMENT = "appointment", "Appointment texts"
        FOLLOW_UP = "follow_up", "Follow-up texts"

    class Source(models.TextChoices):
        WEB_FORM = "web_form", "Website booking form"
        PHONE = "phone", "Asked on the phone"
        TEXT_REPLY = "text_reply", "Text reply (STOP or START)"
        IMPORT = "import", "Imported"

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="consents")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    granted = models.BooleanField()
    phone = PhoneField()
    source = models.CharField(max_length=20, choices=Source.choices)
    wording_version = models.CharField(max_length=40, blank=True)
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-recorded_at"]
        constraints = [phone_check("phone", "consent_phone_10_digits")]

    def __str__(self):
        answer = "yes" if self.granted else "no"
        return f"{self.customer}: {self.get_kind_display()} {answer}"
