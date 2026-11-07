from django.db import migrations, models

API_CHOICES = [
    ("place_details", "Google Place Details"),
    ("text_search", "Google Text Search"),
    ("routes", "Google Routes"),
    ("census_geocoder", "Census geocoder"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("geo", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="locationsettings",
            name="text_search_daily_cap",
            field=models.PositiveIntegerField(default=300),
        ),
        migrations.AddField(
            model_name="historicallocationsettings",
            name="text_search_daily_cap",
            field=models.PositiveIntegerField(default=300),
        ),
        migrations.AlterField(
            model_name="apiusage",
            name="api",
            field=models.CharField(choices=API_CHOICES, max_length=20),
        ),
    ]
