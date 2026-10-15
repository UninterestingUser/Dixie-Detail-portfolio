"""Review requests and follow-up campaigns. Where each customer came from is
Customer.source."""

from django.conf import settings
from django.db import models


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
