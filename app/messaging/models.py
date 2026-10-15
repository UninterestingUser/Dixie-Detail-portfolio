"""Text message templates and the log of every text sent and received."""

from django.db import models

from core.fields import PhoneField, phone_check


class MessageTemplate(models.Model):
    """Editable wording for one automated text (data/message-templates.yaml)."""

    class Consent(models.TextChoices):
        APPOINTMENT = "appointment", "Appointment texts"
        FOLLOW_UP = "follow_up", "Follow-up texts"

    key = models.SlugField(max_length=40, unique=True)
    text = models.TextField()
    consent = models.CharField(max_length=20, choices=Consent.choices)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.key


class Message(models.Model):
    class Direction(models.TextChoices):
        OUTBOUND = "outbound", "Sent"
        INBOUND = "inbound", "Received"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENT = "sent", "Sent"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"
        RECEIVED = "received", "Received"

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, null=True, blank=True, related_name="messages"
    )
    appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.SET_NULL, null=True, blank=True, related_name="messages"
    )
    template = models.ForeignKey(MessageTemplate, on_delete=models.SET_NULL, null=True, blank=True)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    phone = PhoneField()
    body = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices)
    provider_message_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [phone_check("phone", "message_phone_10_digits")]

    def __str__(self):
        return f"{self.get_direction_display()} {self.created_at:%Y-%m-%d %H:%M}"
