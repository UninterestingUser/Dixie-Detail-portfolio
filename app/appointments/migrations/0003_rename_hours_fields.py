# Lines hold one-person service hours (decision 0058), and an appointment's
# job length becomes its service minutes beside setup and breakdown (decision 0056).

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0002_initial"),
    ]

    operations = [
        migrations.RenameField("appointmentline", "one_person_hours", "one_person_service_hours"),
        migrations.RenameField("historicalappointmentline", "one_person_hours", "one_person_service_hours"),
        migrations.RenameField("appointment", "job_minutes", "service_minutes"),
        migrations.RenameField("historicalappointment", "job_minutes", "service_minutes"),
    ]
