import datetime
from decimal import Decimal

from django.test import TestCase

from pricebook.models import Price, PricebookVersion, PublishedVersionError, Service
from vehicles.models import VehicleClass


class PublishedVersionTests(TestCase):
    """A published pricebook version never changes (decision 0033)."""

    @classmethod
    def setUpTestData(cls):
        vehicle_class = VehicleClass.objects.create(name="Test Class", size_variant_measures="doors")
        service = Service.objects.create(name="Test Detail", kind=Service.Kind.MAIN)
        cls.version = PricebookVersion.objects.create(number=1)
        cls.price = Price.objects.create(
            version=cls.version,
            service=service,
            vehicle_class=vehicle_class,
            size_variant=1,
            price=Decimal("100.00"),
            one_person_hours=Decimal("4"),
        )
        cls.version.publish(datetime.date(2026, 10, 1))

    def test_price_in_published_version_cannot_change(self):
        price = Price.objects.get(pk=self.price.pk)
        price.price = Decimal("150.00")
        with self.assertRaises(PublishedVersionError):
            price.save()
        with self.assertRaises(PublishedVersionError):
            price.delete()

    def test_published_version_cannot_change_or_be_deleted(self):
        version = PricebookVersion.objects.get(pk=self.version.pk)
        version.effective_date = datetime.date(2027, 1, 1)
        with self.assertRaises(PublishedVersionError):
            version.save()
        with self.assertRaises(PublishedVersionError):
            version.delete()
