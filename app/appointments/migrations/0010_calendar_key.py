"""Each appointment's link to its events on the Jobs calendar (decision 0098):
added empty, filled with a new key for each existing appointment (and its
history rows the same key), then made required and unique."""

import uuid

from django.db import migrations, models


def fill_in(apps, schema_editor):
    Appointment = apps.get_model("appointments", "Appointment")
    for appointment in Appointment.objects.filter(calendar_key__isnull=True).only("pk"):
        Appointment.objects.filter(pk=appointment.pk).update(calendar_key=uuid.uuid4())
    schema_editor.execute(
        "UPDATE appointments_historicalappointment h SET calendar_key = a.calendar_key "
        "FROM appointments_appointment a WHERE h.id = a.id"
    )
    # History of appointments removed for good keeps a key of its own.
    Historical = apps.get_model("appointments", "HistoricalAppointment")
    for row in Historical.objects.filter(calendar_key__isnull=True).only("history_id"):
        Historical.objects.filter(history_id=row.history_id).update(calendar_key=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [("appointments", "0009_cancellation_details")]

    operations = [
        migrations.AddField(model_name="appointment", name="calendar_key", field=models.UUIDField(editable=False, null=True)),
        migrations.AddField(model_name="historicalappointment", name="calendar_key", field=models.UUIDField(editable=False, null=True)),
        migrations.RunPython(fill_in, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="appointment", name="calendar_key",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name="historicalappointment", name="calendar_key",
            field=models.UUIDField(db_index=True, default=uuid.uuid4, editable=False),
        ),
    ]
