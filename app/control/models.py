"""The control app's own records: sign-in failures and lockouts (decision
0124). Its first model, the "needs you" seen marker, went with the
new-booking items (decision 0107)."""

from django.conf import settings
from django.db import models


class SignInFailure(models.Model):
    """One failed sign-in, kept for the lockout window, then cleaned up."""

    username = models.CharField(max_length=150, db_index=True)
    # Empty when the address isn't a person's own (see control.lockout).
    address = models.CharField(max_length=45, blank=True, db_index=True)
    at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-at"]


class SignInLockout(models.Model):
    """Sign-ins refused for one username or from one address until `until`,
    unless a manager clears it first."""

    class Kind(models.TextChoices):
        USERNAME = "username", "Username"
        ADDRESS = "address", "Address"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    value = models.CharField(max_length=150)
    failures = models.PositiveIntegerField()
    started_at = models.DateTimeField()
    until = models.DateTimeField(db_index=True)
    cleared_at = models.DateTimeField(null=True, blank=True)
    cleared_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.value} until {self.until:%Y-%m-%d %H:%M}"
