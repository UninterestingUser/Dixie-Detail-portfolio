"""The owner and helpers, their job assignments and what each is paid."""

from django.conf import settings
from django.db import models

from core.fields import MoneyField, PhoneField, phone_check


class StaffMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        HELPER = "helper", "Helper"

    name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=Role.choices)
    phone = PhoneField(blank=True)
    # A helper without a login, such as a family member, has no user.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_member"
    )
    default_job_pay = MoneyField(
        null=True, blank=True, help_text="Flat pay per job. Empty for the owner."
    )
    starting_address = models.CharField(
        max_length=300, blank=True, help_text="Where this person's drive times start."
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [phone_check("phone", "staff_phone_10_digits")]

    def __str__(self):
        return self.name


class StaffPayout(models.Model):
    """Money paid to a helper, settling one or more assignments. Posts to the
    Professional Services expense account in GnuCash."""

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CHECK = "check", "Check"
        VENMO = "venmo", "Venmo"
        PAYPAL = "paypal", "PayPal"
        CASH_APP = "cash_app", "Cash App"
        BANK_TRANSFER = "bank_transfer", "Bank transfer"

    staff_member = models.ForeignKey(StaffMember, on_delete=models.PROTECT, related_name="payouts")
    amount = MoneyField()
    method = models.CharField(max_length=20, choices=Method.choices)
    paid_on = models.DateField()
    notes = models.TextField(blank=True)
    export_batch = models.ForeignKey(
        "bookkeeping.ExportBatch", on_delete=models.PROTECT, null=True, blank=True, related_name="staff_payouts"
    )

    def __str__(self):
        return f"{self.amount} to {self.staff_member} on {self.paid_on}"


class Assignment(models.Model):
    """A staff member on a job, with the flat pay for that job.

    The staff member's per-job pay is copied when they are assigned, so a later
    change to it does not alter past jobs. An override replaces it for this job.
    """

    appointment = models.ForeignKey(
        "appointments.Appointment", on_delete=models.CASCADE, related_name="assignments"
    )
    staff_member = models.ForeignKey(StaffMember, on_delete=models.PROTECT, related_name="assignments")
    default_pay = MoneyField(null=True, blank=True)
    pay_override = MoneyField(null=True, blank=True)
    override_reason = models.CharField(max_length=200, blank=True)
    payout = models.ForeignKey(
        StaffPayout, on_delete=models.SET_NULL, null=True, blank=True, related_name="assignments"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["appointment", "staff_member"], name="one_assignment_per_person")
        ]

    def __str__(self):
        return f"{self.staff_member} on {self.appointment}"

    @property
    def pay(self):
        return self.pay_override if self.pay_override is not None else self.default_pay

    def save(self, *args, **kwargs):
        if self._state.adding and self.default_pay is None:
            self.default_pay = self.staff_member.default_job_pay
        super().save(*args, **kwargs)
