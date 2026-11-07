import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

CHOICES = [
    ("google_place", "Google place"),
    ("census", "Census geocoder"),
    ("google_search", "Google address search"),
    ("by_hand", "Location set by hand"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0003_address_verification"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="address",
            name="verified_by",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="+", to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="historicaladdress",
            name="verified_by",
            field=models.ForeignKey(
                blank=True, db_constraint=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+", to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="address",
            name="verification",
            field=models.CharField(blank=True, choices=CHOICES, help_text="How the address was verified; empty if it is not.", max_length=20),
        ),
        migrations.AlterField(
            model_name="historicaladdress",
            name="verification",
            field=models.CharField(blank=True, choices=CHOICES, help_text="How the address was verified; empty if it is not.", max_length=20),
        ),
    ]
