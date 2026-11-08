"""What the control app remembers for each user."""

from django.conf import settings
from django.db import models


class SeenMarker(models.Model):
    """When a user last cleared the new website bookings from the "needs
    you" list on the home screen (control-app.md)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seen_marker")
    website_bookings_seen_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Seen marker for {self.user}"
