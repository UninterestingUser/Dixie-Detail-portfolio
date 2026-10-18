"""The owner and helpers, their job assignments and what each is paid.

No helper names, ages or pay totals belong in code, tests or docs (decision 0053).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from simple_history.models import HistoricalRecords

from core.fields import MoneyField, PhoneField, phone_check


class PayType(models.TextChoices):
    """How a helper is paid, which sets the GnuCash account for their pay
    (decision 0053). Both are a flat amount per job."""

    # The owner's accountant's advice for family helpers: posts to
    # Expenses:Professional Services.
    FAMILY_HELPER = "family_helper", "Family helper"
    # Planned: normal wages per job. The GnuCash account and payroll are a
    # later decision.
    EMPLOYEE = "employee", "Employee"


class StaffMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        HELPER = "helper", "Helper"

    name = models.CharField(max_length=150)
    role = models.CharField(max_length=10, choices=Role.choices)
    # Every helper has one; the owner has none.
    pay_type = models.CharField(max_length=20, choices=PayType.choices, blank=True)
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
        constraints = [
            phone_check("phone", "staff_phone_10_digits"),
            models.CheckConstraint(
                condition=Q(role="owner", pay_type="") | (Q(role="helper") & ~Q(pay_type="")),
                name="helper_has_pay_type",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def is_manager(self):
        """Managers are authorized for every service and may assign someone
        not yet authorized, for training (decision 0061). Only the owner today."""
        return self.role == self.Role.OWNER


class ServiceAuthorization(models.Model):
    """One staff member authorized to perform one service (decision 0061).

    The staff page and the service page both edit these rows, so there is
    nothing to keep in sync. Managers need no rows: they are authorized for
    every service, so a new service starts with only managers authorized.
    """

    staff_member = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="authorizations")
    service = models.ForeignKey("pricebook.Service", on_delete=models.CASCADE, related_name="authorizations")
    granted_at = models.DateTimeField(auto_now_add=True)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    # Granting and removing are both kept, with who did it.
    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["staff_member", "service"], name="one_authorization_per_service")
        ]

    def __str__(self):
        return f"{self.staff_member}: {self.service}"


class StaffPayout(models.Model):
    """Money paid to a helper, settling one or more assignments.

    The helper's pay type is copied when the payout is made, so the GnuCash
    account for past pay stays right if the helper's pay type changes later.
    """

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CHECK = "check", "Check"
        VENMO = "venmo", "Venmo"
        PAYPAL = "paypal", "PayPal"
        CASH_APP = "cash_app", "Cash App"
        BANK_TRANSFER = "bank_transfer", "Bank transfer"

    staff_member = models.ForeignKey(StaffMember, on_delete=models.PROTECT, related_name="payouts")
    pay_type = models.CharField(max_length=20, choices=PayType.choices)
    amount = MoneyField()
    method = models.CharField(max_length=20, choices=Method.choices)
    paid_on = models.DateField()
    notes = models.TextField(blank=True)
    export_batch = models.ForeignKey(
        "bookkeeping.ExportBatch", on_delete=models.PROTECT, null=True, blank=True, related_name="staff_payouts"
    )
    # Where an imported payout came from, so a re-run updates it (decision 0051).
    import_key = models.CharField(max_length=60, unique=True, null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=~Q(pay_type=""), name="payout_has_pay_type")]

    def __str__(self):
        return f"{self.amount} to {self.staff_member} on {self.paid_on}"

    def save(self, *args, **kwargs):
        if self._state.adding and not self.pay_type:
            self.pay_type = self.staff_member.pay_type
        super().save(*args, **kwargs)


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
    # Why a manager assigned someone not yet authorized for every service on
    # the job, such as training (decision 0061). Empty otherwise.
    training_reason = models.CharField(max_length=200, blank=True)
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
