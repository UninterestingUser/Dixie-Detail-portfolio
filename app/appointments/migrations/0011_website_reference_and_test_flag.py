"""A website booking's reference, and the test flag (public-api.md)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("appointments", "0010_calendar_key")]

    operations = [
        migrations.AddField(
            model_name="appointment",
            name="is_test",
            field=models.BooleanField(db_default=False, default=False, verbose_name="test record"),
        ),
        migrations.AddField(
            model_name="appointment",
            name="reference",
            field=models.CharField(blank=True, max_length=12, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="historicalappointment",
            name="is_test",
            field=models.BooleanField(db_default=False, default=False, verbose_name="test record"),
        ),
        migrations.AddField(
            model_name="historicalappointment",
            name="reference",
            field=models.CharField(blank=True, db_index=True, max_length=12, null=True),
        ),
    ]
