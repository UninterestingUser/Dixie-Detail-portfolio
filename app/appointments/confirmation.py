"""Confirming bookings from new customers (decision 0112, booking-flow.md).

A website booking from a number that quietly matches a customer with at
least one completed job, and every booking made in the control app, is
confirmed at once. Any other website booking holds its time but starts
unconfirmed: with text consent, a confirmation request text is queued for
Phase 4's sender and the job waits for a reply; without it, the job goes
on "needs you" as "Call to confirm". A manager can mark any job confirmed.

The caps keep a stranger from filling the calendar with unconfirmed
bookings: at most UNCONFIRMED_PER_NUMBER open unconfirmed bookings for one
new customer's number, and at most UNCONFIRMED_NEW_CUSTOMERS at once
(scheduling settings). Past either, the booking becomes a request instead
(publicapi.bookings).
"""

import datetime

import yaml
from django.conf import settings as django_settings
from django.db import transaction
from django.utils import timezone

from .models import Appointment

TEXT = (
    "Dixie Detail: Please confirm your {service} on {day} at {time}. Reply YES to confirm, "
    "or call or text {phone} to change it. Reply STOP to opt out."
)
# Phase 4: a reply that confirms the soonest unconfirmed job for its number,
# in any case, with punctuation ignored (text-messages.md).
CONFIRMING_REPLIES = {"YES", "Y", "CONFIRM"}


def business_phone():
    """The business number as data/business.yaml writes it, "(423) 380-9120"."""
    return yaml.safe_load((django_settings.DATA_DIR / "business.yaml").read_text())["phone"]["number"]


def is_known_customer(customer):
    """A customer with at least one completed job."""
    return customer is not None and customer.appointments.filter(status=Appointment.Status.COMPLETED).exists()


def open_unconfirmed(now=None):
    """Booked jobs not yet confirmed, from now on."""
    return Appointment.objects.filter(
        status=Appointment.Status.BOOKED, confirmation=Appointment.Confirmation.UNCONFIRMED,
        scheduled_start__gte=now or timezone.now(),
    )


def over_a_cap(customer, is_test, settings):
    """Whether one more unconfirmed booking would pass a cap: the customer's
    own (a new number has none yet), or all new customers' together. Test
    records count only against test records, so a smoke test never blocks
    a real customer."""
    lock_caps()
    found = open_unconfirmed().filter(is_test=is_test)
    if customer is not None and found.filter(customer=customer).count() >= settings.unconfirmed_per_number:
        return True
    return found.count() >= settings.unconfirmed_new_customers


# The key of the lock that has the caps counted one booking at a time, so
# two bookings on different days can't both take the last place.
CAPS_LOCK = (4_102, 0)


def lock_caps():
    """Hold the caps until the transaction ends (a PostgreSQL advisory lock,
    released at commit or rollback)."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", list(CAPS_LOCK))


def unconfirmed_fields(text_consent):
    """The fields a new customer's website booking starts with."""
    reason = Appointment.UnconfirmedReason.TEXT_REPLY if text_consent else Appointment.UnconfirmedReason.CALL
    return {"confirmation": Appointment.Confirmation.UNCONFIRMED, "unconfirmed_reason": reason}


def confirmed_fields(how, user=None, note=""):
    return {
        "confirmation": Appointment.Confirmation.CONFIRMED, "unconfirmed_reason": "", "confirmed_how": how,
        "confirmed_at": timezone.now(), "confirmed_by": user, "confirmation_note": note.strip()[:300],
    }


class ConfirmationError(ValueError):
    """The job can't be confirmed as asked."""


@transaction.atomic
def confirm(appointment, how, user=None, note=""):
    """Mark the job confirmed, recording how, when and by whom, in its change
    history. A text reply (Phase 4) uses how=TEXT_REPLY."""
    if appointment.status == Appointment.Status.CANCELED:
        raise ConfirmationError("A canceled job can't be confirmed.")
    if appointment.confirmation == Appointment.Confirmation.CONFIRMED:
        raise ConfirmationError("This job is already confirmed.")
    for name, value in confirmed_fields(how, user, note).items():
        setattr(appointment, name, value)
    appointment._change_reason = f"Confirmed: {Appointment.ConfirmedHow(how).label.lower()}"
    appointment.save()
    return appointment


def request_text(appointment, phone):
    """The confirmation request text for a job, such as "… your Full Detail
    on Thursday, December 3 at 8:00 AM …"."""
    local = timezone.localtime(appointment.scheduled_start)
    service = appointment.quote.service.name if appointment.quote_id else "detail"
    return TEXT.format(service=service, day=f"{local:%A, %B} {local.day}", time=f"{local:%-I:%M %p}", phone=phone)


def queue_request(appointment):
    """Store the confirmation request text as a queued outgoing message for
    Phase 4's sender. Nothing is sent now."""
    from messaging.models import Message

    return Message.objects.create(
        customer=appointment.customer, appointment=appointment, direction=Message.Direction.OUTBOUND,
        kind=Message.Kind.CONFIRMATION_REQUEST, phone=appointment.customer.mobile,
        body=request_text(appointment, business_phone()), status=Message.Status.QUEUED,
    )


def soon(hours, now=None):
    """Unconfirmed jobs that start within hours, soonest first."""
    now = now or timezone.now()
    return open_unconfirmed(now).filter(scheduled_start__lt=now + datetime.timedelta(hours=hours)).select_related(
        "customer"
    ).order_by("scheduled_start")
