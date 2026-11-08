"""Test records and the exact consent wording (public-api.md): a test flag
on customers, and the words shown with each consent answer from the
website. The flag has a database default, so rows written by code that
predates it still save."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("customers", "0004_address_google_search_and_verified_by")]

    operations = [
        migrations.AddField(
            model_name="consent",
            name="wording",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="customer",
            name="is_test",
            field=models.BooleanField(db_default=False, default=False, verbose_name="test record"),
        ),
        migrations.AddField(
            model_name="historicalcustomer",
            name="is_test",
            field=models.BooleanField(db_default=False, default=False, verbose_name="test record"),
        ),
    ]
