"""The records behind the public API (docs/reference/public-api.md).

- VerifiedPlace: a service address picked on the website and looked up by
  the server, in the service area or approved. Quotes, bookings and quote
  requests refer to it by its token; nothing from the browser but the
  Google place ID is used.
- WebQuote: a website quote's public number, its expiry and what the
  customer entered, beside the pricebook's Quote (decision 0059).
- QuoteRequest and QuotePhoto: a job the site can't price, with optional
  photos (decision 0099).
- TimeRequest: a "request a time" form sent while the server was offline
  and replayed later (decision 0100).
- SecondVehicleRequest: a booking request, a website booking taken as a
  request the owner approves: the number has a job that day, or the
  booking would pass a confirmation cap (decisions 0112 and 0113).
- UploadSession, RateCount and SmokeTestPass: the abuse controls.
"""

import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.fields import MoneyField

# Letters and digits that can't be mistaken for each other: no 0, 1, I, L,
# O or U.
REFERENCE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_reference(length=8):
    return "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(length))


def new_token():
    return secrets.token_urlsafe(24)


class VerifiedPlace(models.Model):
    """An address the customer picked from Google's suggestions, looked up
    by the server with its own key, in the service area or approved by the
    owner. Out-of-area places are refused and never stored."""

    token = models.CharField(max_length=40, unique=True, default=new_token)
    google_place_id = models.CharField(max_length=300)
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    zip_code = models.CharField(max_length=10)
    county = models.CharField(max_length=100, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    tax_jurisdiction = models.ForeignKey("billing.TaxJurisdiction", on_delete=models.PROTECT, null=True, blank=True)
    tax_needs_check = models.BooleanField(default=False)
    tax_note = models.CharField(max_length=300, blank=True)
    # The owner's approved out-of-area address this place matched, if any
    # (decision 0037).
    approved_address = models.ForeignKey(
        "customers.Address", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.line1}, {self.city}, {self.state} {self.zip_code}"

    @property
    def point(self):
        return (self.latitude, self.longitude)

    @property
    def one_line(self):
        unit = f" {self.line2}" if self.line2 else ""
        return f"{self.line1}{unit}, {self.city}, {self.state} {self.zip_code}"

    def as_address(self, customer=None):
        """An unsaved Address with this place's parts, verification and tax."""
        from customers.models import Address

        return Address(
            customer=customer,
            line1=self.line1,
            line2=self.line2,
            city=self.city,
            state=self.state,
            zip_code=self.zip_code,
            county=self.county,
            latitude=self.latitude,
            longitude=self.longitude,
            google_place_id=self.google_place_id,
            verification=Address.Verification.GOOGLE_PLACE,
            verified_at=self.created_at or timezone.now(),
            tax_jurisdiction=self.tax_jurisdiction,
            tax_needs_check=self.tax_needs_check,
            tax_note=self.tax_note,
            approved_out_of_area=self.approved_address_id is not None,
        )


class WebQuote(models.Model):
    """A quote issued to the website: the pricebook Quote it wraps, which
    never changes, its public number and expiry, and the vehicle as the
    customer entered it. A changed input makes a new quote."""

    quote = models.OneToOneField("pricebook.Quote", on_delete=models.CASCADE, related_name="web")
    number = models.CharField(max_length=12, unique=True)
    expires_at = models.DateTimeField()
    place = models.ForeignKey(VerifiedPlace, on_delete=models.PROTECT, null=True, blank=True, related_name="quotes")
    # The vehicle as entered: year, make and model from the lists, or a
    # photo card.
    vehicle_year = models.PositiveSmallIntegerField(null=True, blank=True)
    vehicle_make = models.CharField(max_length=60, blank=True)
    vehicle_model_name = models.CharField(max_length=100, blank=True)
    vehicle_model = models.ForeignKey("vehicles.VehicleModel", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    photo_card = models.BooleanField(default=False)
    size_answer = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Website quote {self.number}"

    @property
    def expired(self):
        return timezone.now() >= self.expires_at

    @property
    def vehicle_text(self):
        named = " ".join(str(part) for part in (self.vehicle_year, self.vehicle_make, self.vehicle_model_name) if part)
        if self.photo_card:
            # The year, make and model the customer typed, if any, from an
            # offline request (time_requests).
            card = f"{self.quote.vehicle_class.name} (picked from the photo cards)"
            return f"{named}, {card}" if named else card
        return named


class QuoteRequest(models.Model):
    """A job the site can't price: a vehicle in a class booked by quote
    (decision 0099), or Full Detail or Interior Only at a condition level
    booked by quote (decision 0103). Not an appointment, and it holds no
    time: the owner replies with a price."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        REPLIED = "replied", "Price sent"
        BOOKED = "booked", "Booked"
        DECLINED = "declined", "Declined"
        DONE = "done", "Job done"
        CANCELED = "canceled", "Canceled"

    # A closed request's photos are deleted QUOTE_REQUEST_PHOTO_DAYS after it closed.
    CLOSED = (Status.DECLINED, Status.DONE, Status.CANCELED)

    reference = models.CharField(max_length=12, unique=True)
    # Set for a request the website held while the server was offline and
    # Cloudflare replayed (decision 0100): made by the website, so a second
    # replay changes nothing. Such a request has no photos.
    request_id = models.UUIDField(unique=True, null=True, blank=True)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="quote_requests")
    # Empty for an offline request whose address could not be checked; the
    # address as typed is then in address_text, and problem says why.
    service_address = models.ForeignKey("customers.Address", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    address_text = models.CharField(max_length=200, blank=True)
    # Everything to check, such as an address that couldn't be looked up or
    # a field that couldn't be read (decision 0114).
    problem = models.TextField(blank=True)
    # An offline request with a field that couldn't be read, exactly as it
    # arrived, so nothing the customer sent is lost (decision 0114).
    as_sent = models.JSONField(null=True, blank=True)
    # The vehicle record quiet matching gave the request: the customer's own,
    # or a new one held off the record until the request is booked.
    vehicle = models.ForeignKey("vehicles.Vehicle", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    vehicle_year = models.PositiveSmallIntegerField(null=True, blank=True)
    vehicle_make = models.CharField(max_length=60, blank=True)
    vehicle_model_name = models.CharField(max_length=100, blank=True)
    vehicle_class = models.ForeignKey("vehicles.VehicleClass", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    photo_card = models.BooleanField(default=False)
    size_variant = models.ForeignKey("vehicles.SizeVariant", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    # Empty when the customer chose "Not sure".
    service = models.ForeignKey("pricebook.Service", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    # The condition level, for a service that takes one, and the add-ons the
    # customer wants (decision 0103).
    condition_level = models.PositiveSmallIntegerField(null=True, blank=True)
    add_ons = models.ManyToManyField("pricebook.Service", blank=True, related_name="+")
    description = models.TextField()
    preferred_days = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    closed_at = models.DateTimeField(null=True, blank=True)
    # The owner's price, entered by hand: a quote record, the price of
    # record (decision 0059).
    quote = models.OneToOneField("pricebook.Quote", on_delete=models.PROTECT, null=True, blank=True, related_name="quote_request")
    priced_at = models.DateTimeField(null=True, blank=True)
    priced_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    # The people checked under Crew when it was priced: assigned when it is
    # booked, and their number is the quote's crew size.
    crew = models.ManyToManyField("staff.StaffMember", blank=True, related_name="+")
    decline_reason = models.CharField(max_length=300, blank=True)
    # How quiet matching placed it (customers.matching), for the review
    # flags raised when it is booked.
    intake = models.JSONField(null=True, blank=True)
    # The job booked from it, once there is one; its completion or
    # cancellation closes the request. The job page shows the description
    # and photos.
    appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name="quote_requests"
    )
    photos_deleted_at = models.DateTimeField(null=True, blank=True)
    photos_deleted_count = models.PositiveSmallIntegerField(default=0)
    is_test = models.BooleanField("test record", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Quote request {self.reference}"

    @property
    def vehicle_text(self):
        named = " ".join(str(part) for part in (self.vehicle_year, self.vehicle_make, self.vehicle_model_name) if part)
        if self.photo_card:
            card = f"{self.vehicle_class.name} photo card" if self.vehicle_class else "photo card"
            return f"{named} ({card})" if named else card.capitalize()
        return named

    def closed_on(self):
        """When the request closed, for deleting its photos, or None while open."""
        if self.status in self.CLOSED:
            return self.closed_at
        if self.appointment is not None:
            return self.appointment.completed_at or self.appointment.canceled_at
        return None


class LookupSession(models.Model):
    """Opened after a Turnstile check at the booking form's location step,
    so the public address lookups (POST addresses) can't be called in a
    loop (decision 0115). It allows ADDRESS_LOOKUP_SESSION_LOOKUPS lookups
    within ADDRESS_LOOKUP_SESSION_MINUTES."""

    token = models.CharField(max_length=40, unique=True, default=new_token)
    visitor = models.CharField(max_length=64)
    lookups = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"Lookup session from {self.created_at:%Y-%m-%d %H:%M}"


class UploadSession(models.Model):
    """Opened after a Turnstile check, so photos can upload one by one as
    the customer picks them. Photos never attached to a sent request are
    deleted after a day."""

    token = models.CharField(max_length=40, unique=True, default=new_token)
    visitor = models.CharField(max_length=64)
    is_smoke_test = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def __str__(self):
        return f"Upload session from {self.created_at:%Y-%m-%d %H:%M}"


class QuotePhoto(models.Model):
    """One photo, saved as a new JPEG under a random name with every piece
    of metadata removed. Seen only in the control app."""

    session = models.ForeignKey(UploadSession, on_delete=models.SET_NULL, null=True, blank=True, related_name="photos")
    request = models.ForeignKey(QuoteRequest, on_delete=models.CASCADE, null=True, blank=True, related_name="photos")
    # The public id the website refers to it by, and the file's own name.
    public_id = models.CharField(max_length=40, unique=True, default=new_token)
    file_name = models.CharField(max_length=60, unique=True)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    bytes = models.PositiveIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["uploaded_at", "id"]

    def __str__(self):
        return self.file_name


class TimeRequest(models.Model):
    """A "request a time" form the website held while the server was
    offline, replayed by Cloudflare when it came back (decision 0100). Not
    an appointment: priced on arrival, and flagged when that price differs
    from the one the customer saw."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        BOOKED = "booked", "Booked"
        DECLINED = "declined", "Declined"

    request_id = models.UUIDField(unique=True, help_text="Made by the website, so a second replay changes nothing.")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="time_requests")
    service_address = models.ForeignKey("customers.Address", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    vehicle = models.ForeignKey("vehicles.Vehicle", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    submitted_at = models.DateTimeField(help_text="When the customer sent the form.")
    received_at = models.DateTimeField(auto_now_add=True)
    preferred_start = models.DateTimeField(null=True, blank=True)
    preferred_note = models.CharField(max_length=300, blank=True)
    # What the form held: vehicle, size answer, condition, service, add-ons,
    # color and payment method, as validated.
    inputs = models.JSONField(default=dict)
    shown_total = MoneyField(null=True, blank=True)
    shown_pricebook_version = models.PositiveIntegerField(null=True, blank=True)
    # Priced on arrival from the pricebook in effect, or empty with the reason.
    quote = models.ForeignKey("pricebook.Quote", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    price_differs = models.BooleanField(default=False)
    # Everything to check (decision 0114).
    problem = models.TextField(blank=True)
    # The request exactly as it arrived, when a field couldn't be read.
    as_sent = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    decline_reason = models.CharField(max_length=300, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    intake = models.JSONField(null=True, blank=True)
    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    is_test = models.BooleanField("test record", default=False)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self):
        return f"Time request from {self.submitted_at:%Y-%m-%d %H:%M}"


class SecondVehicleRequest(models.Model):
    """A booking request: a website booking the server took as a request
    instead of booking it (decision 0113), because the number already has a
    job that day (usually a second vehicle), or because one more unconfirmed
    booking would pass a cap (decision 0112). Called a booking request in
    the control app; the model keeps its first name. It is not an
    appointment and holds no time: the owner approves it, which books the
    quote the customer saw through the availability check, or declines it
    with a reason. The customer is never told the reason."""

    class Status(models.TextChoices):
        NEW = "new", "New"
        BOOKED = "booked", "Booked"
        DECLINED = "declined", "Declined"

    class Reason(models.TextChoices):
        SAME_DAY = "same_day", "Another job that day"
        OVER_CAP = "over_cap", "Past the limit on unconfirmed bookings"

    reference = models.CharField(max_length=12, unique=True)
    web_quote = models.OneToOneField(WebQuote, on_delete=models.PROTECT, related_name="second_vehicle_request")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="second_vehicle_requests")
    service_address = models.ForeignKey("customers.Address", on_delete=models.PROTECT, related_name="+")
    vehicle = models.ForeignKey("vehicles.Vehicle", on_delete=models.PROTECT, related_name="+")
    start = models.DateTimeField(help_text="The time the customer picked.")
    payment_method = models.CharField(max_length=20, blank=True)
    # The customer's job that day when the request came in.
    same_day_appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # Why it wasn't booked, for the owner only. Requests from before
    # decision 0113 were all same-day.
    reason = models.CharField(max_length=10, choices=Reason.choices, default=Reason.SAME_DAY, db_default=Reason.SAME_DAY)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    decline_reason = models.CharField(max_length=300, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    intake = models.JSONField(null=True, blank=True)
    appointment = models.ForeignKey("appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    is_test = models.BooleanField("test record", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Booking request {self.reference}"


class RateCount(models.Model):
    """Requests from one visitor address in one window, by kind. The address
    is kept only as a keyed hash."""

    kind = models.CharField(max_length=20)
    visitor = models.CharField(max_length=64)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind", "visitor", "window_start"], name="one_rate_count_per_window")]


class SmokeTestPass(models.Model):
    """A one-time pass api_smoke_test makes on the server, accepted in place
    of a Turnstile token. Only something with the database can make one."""

    token = models.CharField(max_length=40, unique=True, default=new_token)
    expires_at = models.DateTimeField()
    uses_left = models.PositiveSmallIntegerField(default=3)


class SiteMode(models.Model):
    """The one row (pk 1) of the requests-only switch (decision 0128). In
    requests mode the public API's booking and quote endpoints answer 503,
    which the website treats as "server unavailable", so customers get the
    request form; the offline request endpoints keep working. Set with
    ops/site-mode.sh. No row means normal."""

    NORMAL = "normal"
    REQUESTS = "requests"
    MODES = [(NORMAL, "Normal"), (REQUESTS, "Requests only")]

    mode = models.CharField(max_length=10, choices=MODES, default=NORMAL)
    changed_at = models.DateTimeField(default=timezone.now)
    reason = models.CharField(max_length=200, blank=True)

    @classmethod
    def current(cls):
        row = cls.objects.filter(pk=1).first()
        return row.mode if row else cls.NORMAL

    def __str__(self):
        return self.get_mode_display()
