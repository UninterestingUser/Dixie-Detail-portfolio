import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("publicapi", "0007_offline_problems_and_lookup_sessions"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteMode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mode", models.CharField(choices=[("normal", "Normal"), ("requests", "Requests only")], default="normal", max_length=10)),
                ("changed_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("reason", models.CharField(blank=True, max_length=200)),
            ],
        ),
    ]
