"""Location settings, outside-service call counts and cached drive times.

The home base is the owner's home: it lives only in the database, set in the
control app, never in the repository or the docs.
"""

from decimal import Decimal

from django.db import models
from simple_history.models import HistoricalRecords


class LocationSettings(models.Model):
    """The one row of location, drive-time and Google settings (pk 1),
    edited on the control app's settings screen, with change history."""

    class TaxSourcing(models.TextChoices):
        SERVICE_ADDRESS = "service_address", "The service address's rate"
        BUSINESS_LOCATION = "business_location", "The home base's rate"

    # The home base: where drive times start. Verified like any address.
    home_line1 = models.CharField("home base street", max_length=200, blank=True)
    home_city = models.CharField("home base city", max_length=100, blank=True)
    home_state = models.CharField("home base state", max_length=2, blank=True)
    home_zip_code = models.CharField("home base ZIP code", max_length=10, blank=True)
    home_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    home_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Daily caps on Google calls, counted per Pacific day as Google counts
    # its quotas. They sit below the limits set in Google Cloud (322 a day
    # for each Places method, 161 for Routes), so the fallbacks start before
    # Google refuses.
    place_details_daily_cap = models.PositiveIntegerField(default=300)
    # The website's public share of it (decision 0115): the public address
    # lookups (POST addresses) stop here, and the rest of the cap is the
    # reserve for the control app and the server's own address checks, such
    # as an offline request looked up when it arrives.
    place_details_public_daily_cap = models.PositiveIntegerField(
        "Place Details public share", default=250,
        help_text="Website address lookups a day. The rest of the Place Details cap is kept for the control app.",
    )
    text_search_daily_cap = models.PositiveIntegerField(default=300)
    routes_daily_cap = models.PositiveIntegerField(default=150)

    # The fallback drive time, from straight-line distance, when Google can't
    # be reached or the cap is reached.
    estimate_road_factor = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("1.30"),
        help_text="Road distance as a multiple of straight-line distance.",
    )
    estimate_speed_mph = models.PositiveSmallIntegerField(default=40, help_text="Average driving speed.")
    drive_time_cache_days = models.PositiveSmallIntegerField(
        default=30, help_text="How long a drive time from Google is reused for the same addresses and hour."
    )

    # Decision 0025: one setting, in case the accountant advises otherwise.
    tax_sourcing = models.CharField(
        max_length=20, choices=TaxSourcing.choices, default=TaxSourcing.SERVICE_ADDRESS
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "location settings"
        verbose_name_plural = "location settings"

    def __str__(self):
        return "Location settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings

    @property
    def home(self):
        """The home base as (latitude, longitude), or None when it is not set."""
        if self.home_latitude is None or self.home_longitude is None:
            return None
        return (self.home_latitude, self.home_longitude)


class ApiUsage(models.Model):
    """How many calls the system made to one outside service on one day.
    Days are Pacific dates, the day Google's quotas use."""

    class Api(models.TextChoices):
        PLACE_DETAILS = "place_details", "Google Place Details"
        TEXT_SEARCH = "text_search", "Google Text Search"
        ROUTES = "routes", "Google Routes"
        CENSUS_GEOCODER = "census_geocoder", "Census geocoder"

    api = models.CharField(max_length=20, choices=Api.choices)
    day = models.DateField()
    calls = models.PositiveIntegerField(default=0)
    # Calls not made because the day's cap was reached.
    refused = models.PositiveIntegerField(default=0)
    # Of those, the website's public lookups (decision 0115): calls made,
    # and calls refused once the public share was used.
    public_calls = models.PositiveIntegerField(default=0, db_default=0)
    public_refused = models.PositiveIntegerField(default=0, db_default=0)

    class Meta:
        ordering = ["-day", "api"]
        constraints = [models.UniqueConstraint(fields=["api", "day"], name="one_usage_row_per_api_and_day")]

    def __str__(self):
        return f"{self.get_api_display()} on {self.day}: {self.calls}"


class DriveTime(models.Model):
    """A drive time from Google, cached by the two points and the hour of the
    day (Eastern) it was asked for, so an open-times search does not call
    Google for every slot. Points are rounded to 5 decimal places (about a
    meter). Estimates are never cached."""

    origin_latitude = models.DecimalField(max_digits=8, decimal_places=5)
    origin_longitude = models.DecimalField(max_digits=8, decimal_places=5)
    destination_latitude = models.DecimalField(max_digits=8, decimal_places=5)
    destination_longitude = models.DecimalField(max_digits=8, decimal_places=5)
    hour = models.PositiveSmallIntegerField(help_text="Hour of the day, Eastern, 0 to 23.")
    seconds = models.PositiveIntegerField()
    meters = models.PositiveIntegerField()
    fetched_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["origin_latitude", "origin_longitude", "destination_latitude", "destination_longitude", "hour"],
                name="one_drive_time_per_pair_and_hour",
            )
        ]

    def __str__(self):
        return f"{self.seconds // 60} min at {self.hour}:00"

