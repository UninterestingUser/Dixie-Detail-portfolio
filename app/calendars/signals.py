"""Queue a Jobs calendar push whenever what it shows changes (decision 0098):
an appointment, its lines, or a closed date. The task is written in the same
transaction as the change, so it is never lost and never pushed before the
change is saved. Anything else the events show, such as the customer's
phone or the address, is caught by the worker's regular Jobs check."""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from appointments.models import Appointment, AppointmentLine
from scheduling.models import DateException

from .events import closed_link, job_link
from .sync import enqueue


@receiver(post_save, sender=Appointment)
@receiver(post_delete, sender=Appointment)
def appointment_changed(sender, instance, raw=False, **kwargs):
    if not raw:
        enqueue(job_link(instance))


@receiver(post_save, sender=AppointmentLine)
@receiver(post_delete, sender=AppointmentLine)
def line_changed(sender, instance, raw=False, **kwargs):
    if raw:
        return
    key = Appointment.objects.filter(pk=instance.appointment_id).values_list("calendar_key", flat=True).first()
    if key is not None:
        enqueue(f"job:{key.hex}")


@receiver(pre_save, sender=DateException)
def date_exception_moving(sender, instance, raw=False, **kwargs):
    if not raw and instance.pk:
        before = DateException.objects.filter(pk=instance.pk).values_list("date", flat=True).first()
        if before and before != instance.date:
            enqueue(closed_link(before))


@receiver(post_save, sender=DateException)
@receiver(post_delete, sender=DateException)
def date_exception_changed(sender, instance, raw=False, **kwargs):
    if not raw:
        enqueue(closed_link(instance.date))
