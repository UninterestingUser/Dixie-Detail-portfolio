"""Review requests, the reviews the website shows, and follow-up campaigns.
Where each customer came from is Customer.source."""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from simple_history.models import HistoricalRecords


class ReviewRequest(models.Model):
    """The review request sent after a paid job, and whether a review followed."""

    appointment = models.OneToOneField(
        "appointments.Appointment", on_delete=models.CASCADE, related_name="review_request"
    )
    message = models.ForeignKey("messaging.Message", on_delete=models.SET_NULL, null=True, blank=True)
    sent_at = models.DateTimeField()
    review_received_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Review request for {self.appointment}"


class Campaign(models.Model):
    """Follow-up texts sent to a chosen group of customers with follow-up consent."""

    name = models.CharField(max_length=150)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class CampaignRecipient(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="recipients")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="+")
    message = models.ForeignKey("messaging.Message", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["campaign", "customer"], name="one_recipient_per_campaign")
        ]

    def __str__(self):
        return f"{self.customer} in {self.campaign}"


class Review(models.Model):
    """A customer review the website shows (decision 0109), kept only here
    so customers' names never enter the repository. A manager adds them
    on the control app's Reviews screen, copied from Google."""

    name = models.CharField(
        "Reviewer's name", max_length=60, help_text="First name and last initial, as on Google."
    )
    text = models.TextField("Review", max_length=3000)
    reviewed_on = models.DateField("Date of the review")
    stars = models.PositiveSmallIntegerField(
        "Star rating", null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    google_url = models.URLField(
        "Link to the Google review", max_length=500, blank=True, help_text="Optional. Starts with https://."
    )
    shown = models.BooleanField("Shown on the website", default=True)
    position = models.PositiveIntegerField(default=0, help_text="Lower first.")
    history = HistoricalRecords()

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return f"Review by {self.name}"
