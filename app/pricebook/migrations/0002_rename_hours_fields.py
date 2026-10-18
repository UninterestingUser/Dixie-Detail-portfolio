# The price matrix holds service time only (decision 0058), and the full-day
# flag counts one-person time on site.

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pricebook", "0001_initial"),
    ]

    operations = [
        migrations.RenameField("price", "one_person_hours", "one_person_service_hours"),
        migrations.RenameField("historicalprice", "one_person_hours", "one_person_service_hours"),
        migrations.RenameField("pricingrules", "job_time_rounding_minutes", "service_time_rounding_minutes"),
        migrations.RenameField("historicalpricingrules", "job_time_rounding_minutes", "service_time_rounding_minutes"),
        migrations.RenameField("pricingrules", "full_day_threshold_hours", "full_day_time_on_site_hours"),
        migrations.RenameField("historicalpricingrules", "full_day_threshold_hours", "full_day_time_on_site_hours"),
    ]
