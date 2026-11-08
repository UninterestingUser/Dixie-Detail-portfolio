"""The Full-size Vans photo card now leads to a quote request, where photos
are optional (decision 0099): its caption changes from "Send us a photo for
a quote" to "Ask for a quote", unless the owner has already changed it."""

from django.db import migrations

OLD = "Send us a photo for a quote"
NEW = "Ask for a quote"


def forward(apps, schema_editor):
    apps.get_model("vehicles", "VehicleClass").objects.filter(name="Full-size Vans", photo_card=OLD).update(photo_card=NEW)


def backward(apps, schema_editor):
    apps.get_model("vehicles", "VehicleClass").objects.filter(name="Full-size Vans", photo_card=NEW).update(photo_card=OLD)


class Migration(migrations.Migration):
    dependencies = [("vehicles", "0012_three_row_floor")]

    operations = [migrations.RunPython(forward, backward)]
