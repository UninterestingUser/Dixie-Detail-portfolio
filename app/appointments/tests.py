import datetime
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment, AppointmentLine
from customers.models import Customer
from pricebook.models import Price, PricebookVersion, Service
from promotions.models import Promotion
from vehicles.models import SizeVariant, Vehicle, VehicleClass

# Invented test figures, not the business's prices.
VERSION_1_PRICE = Decimal("100.00")
VERSION_2_PRICE = Decimal("125.00")


class LineSnapshotTests(TestCase):
    """A booked appointment's lines never change when the pricebook does (decision 0033)."""

    @classmethod
    def setUpTestData(cls):
        cls.vehicle_class = VehicleClass.objects.create(name="Test Class", size_variant_measures="seat rows")
        cls.two_rows = SizeVariant.objects.create(vehicle_class=cls.vehicle_class, value=2, label="two rows")
        cls.service = Service.objects.create(name="Test Detail", kind=Service.Kind.MAIN)
        cls.version_1 = PricebookVersion.objects.create(number=1)
        cls.price_1 = Price.objects.create(
            version=cls.version_1,
            service=cls.service,
            vehicle_class=cls.vehicle_class,
            size_variant=cls.two_rows,
            price=VERSION_1_PRICE,
            one_person_service_hours=Decimal("6"),
        )
        cls.version_1.publish(timezone.localdate())
        customer = Customer.objects.create(first_name="Pat", mobile="4235550142")
        vehicle = Vehicle.objects.create(
            customer=customer, year=2019, make="Toyota", model="RAV4", vehicle_class=cls.vehicle_class, size_variant=cls.two_rows
        )
        cls.appointment = Appointment.objects.create(
            customer=customer,
            vehicle=vehicle,
            scheduled_start=timezone.make_aware(datetime.datetime(2026, 11, 3, 8, 0)),
            source=Appointment.Source.OWNER,
        )
        cls.line = AppointmentLine.snapshot(cls.appointment, cls.price_1)
        cls.line.save()

    def test_snapshot_copies_the_price(self):
        self.assertEqual(self.line.amount, VERSION_1_PRICE)
        self.assertEqual(self.line.one_person_service_hours, Decimal("6"))
        self.assertEqual(self.line.description, "Test Detail")
        self.assertEqual(self.line.vehicle_class_name, "Test Class")
        self.assertEqual(self.line.size_variant_value, 2)
        self.assertEqual(self.line.size_variant_label, "two rows")
        self.assertEqual(self.line.pricebook_version, self.version_1)

    def test_new_version_does_not_change_booked_line(self):
        version_2 = PricebookVersion.objects.create(number=2)
        Price.objects.create(
            version=version_2,
            service=self.service,
            vehicle_class=self.vehicle_class,
            size_variant=self.two_rows,
            price=VERSION_2_PRICE,
            one_person_service_hours=Decimal("7"),
        )
        version_2.publish(timezone.localdate() + datetime.timedelta(days=15))
        self.service.name = "Renamed Detail"
        self.service.save()

        line = AppointmentLine.objects.get(pk=self.line.pk)
        self.assertEqual(line.amount, VERSION_1_PRICE)
        self.assertEqual(line.one_person_service_hours, Decimal("6"))
        self.assertEqual(line.description, "Test Detail")
        self.assertEqual(self.appointment.total_before_tax, VERSION_1_PRICE)

    def test_only_published_prices_can_be_booked(self):
        draft = PricebookVersion.objects.create(number=3)
        price = Price.objects.create(
            version=draft,
            service=self.service,
            vehicle_class=self.vehicle_class,
            size_variant=self.two_rows,
            price=VERSION_2_PRICE,
            one_person_service_hours=Decimal("6"),
        )
        with self.assertRaises(ValueError):
            AppointmentLine.snapshot(self.appointment, price)


class NewVehicleClassTests(TestCase):
    """Vehicle classes are records: a new one needs no code change, and renaming
    or retiring one never changes a past job."""

    @classmethod
    def setUpTestData(cls):
        cls.sedans = VehicleClass.objects.create(name="Test Sedans", size_variant_measures="doors")
        cls.four_doors = SizeVariant.objects.create(vehicle_class=cls.sedans, value=2, label="four doors")
        cls.service = Service.objects.create(name="Test Detail", kind=Service.Kind.MAIN)
        cls.version_1 = PricebookVersion.objects.create(number=1)
        price = Price.objects.create(
            version=cls.version_1,
            service=cls.service,
            vehicle_class=cls.sedans,
            size_variant=cls.four_doors,
            price=VERSION_1_PRICE,
            one_person_service_hours=Decimal("5"),
        )
        cls.version_1.publish(timezone.localdate())
        cls.customer = Customer.objects.create(first_name="Pat")
        cls.past_job = Appointment.objects.create(
            customer=cls.customer, scheduled_start=timezone.now(), source=Appointment.Source.OWNER
        )
        cls.past_line = AppointmentLine.snapshot(cls.past_job, price)
        cls.past_line.save()

    def test_seventh_class_gets_prices_in_a_new_version_without_code_change(self):
        # A class with a single price: no doors, cab style or seat rows.
        motorcycles = VehicleClass.objects.create(name="Test Motorcycles")
        self.assertFalse(motorcycles.size_variants.exists())
        version_2 = PricebookVersion.objects.create(number=2)
        price = Price.objects.create(
            version=version_2,
            service=self.service,
            vehicle_class=motorcycles,
            price=VERSION_2_PRICE,
            one_person_service_hours=Decimal("3"),
        )
        version_2.publish(timezone.localdate() + datetime.timedelta(days=15))

        bike = Vehicle.objects.create(
            customer=self.customer, year=2020, make="Honda", model="Gold Wing", vehicle_class=motorcycles
        )
        self.assertEqual(bike.missing_details, [])
        job = Appointment.objects.create(
            customer=self.customer, vehicle=bike, scheduled_start=timezone.now(), source=Appointment.Source.OWNER
        )
        line = AppointmentLine.snapshot(job, price)
        line.save()
        self.assertEqual(line.vehicle_class_name, "Test Motorcycles")
        self.assertIsNone(line.size_variant_value)
        self.assertEqual(line.amount, VERSION_2_PRICE)

        past = AppointmentLine.objects.get(pk=self.past_line.pk)
        self.assertEqual(past.amount, VERSION_1_PRICE)
        self.assertEqual(past.vehicle_class_name, "Test Sedans")
        self.assertEqual(past.size_variant_label, "four doors")

    def test_renaming_or_retiring_a_class_never_changes_a_past_job(self):
        self.sedans.name = "Renamed Sedans"
        self.sedans.active = False
        self.sedans.save()
        self.four_doors.label = "renamed"
        self.four_doors.active = False
        self.four_doors.save()

        past = AppointmentLine.objects.get(pk=self.past_line.pk)
        self.assertEqual(past.vehicle_class_name, "Test Sedans")
        self.assertEqual(past.size_variant_value, 2)
        self.assertEqual(past.size_variant_label, "four doors")
        self.assertEqual(past.vehicle_class, self.sedans)  # kept for history, not deleted

    def test_retired_class_cannot_be_priced_again(self):
        self.sedans.active = False
        self.sedans.save()
        draft = PricebookVersion.objects.create(number=3)
        with self.assertRaises(ValueError):
            Price.objects.create(
                version=draft,
                service=self.service,
                vehicle_class=self.sedans,
                size_variant=self.four_doors,
                price=VERSION_2_PRICE,
                one_person_service_hours=Decimal("5"),
            )

    def test_size_variant_must_belong_to_the_class(self):
        other = VehicleClass.objects.create(name="Test Trucks", size_variant_measures="cab style")
        with self.assertRaises(ValueError):
            Vehicle.objects.create(customer=self.customer, vehicle_class=other, size_variant=self.four_doors)


class LineRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        customer = Customer.objects.create(first_name="Pat")
        cls.appointment = Appointment.objects.create(
            customer=customer, scheduled_start=timezone.now(), source=Appointment.Source.OWNER
        )

    def line(self, **fields):
        return AppointmentLine.objects.create(appointment=self.appointment, description="Line", **fields)

    def test_on_site_adjustment_needs_a_reason(self):
        with self.assertRaises(IntegrityError):
            self.line(kind=AppointmentLine.Kind.ADJUSTMENT, amount=Decimal("-20.00"))

    def test_no_charge_gift_needs_a_reason_and_brings_total_to_zero(self):
        self.line(kind=AppointmentLine.Kind.SERVICE, amount=VERSION_1_PRICE)
        self.line(kind=AppointmentLine.Kind.NO_CHARGE, amount=-VERSION_1_PRICE, reason="Birthday gift")
        self.assertTrue(self.appointment.is_no_charge)
        self.assertEqual(self.appointment.total_before_tax, Decimal("0.00"))

    def test_promotion_cannot_add_to_the_price(self):
        with self.assertRaises(IntegrityError):
            self.line(kind=AppointmentLine.Kind.PROMOTION, amount=Decimal("10.00"))


class VoucherTests(TestCase):
    """A free voucher is a promotion with a code and a dollar value (decision 0054)."""

    @classmethod
    def setUpTestData(cls):
        customer = Customer.objects.create(first_name="Pat")
        cls.appointment = Appointment.objects.create(
            customer=customer, scheduled_start=timezone.now(), source=Appointment.Source.OWNER
        )
        AppointmentLine.objects.create(
            appointment=cls.appointment, kind=AppointmentLine.Kind.SERVICE, description="Service", amount=VERSION_1_PRICE
        )

    def voucher(self, value):
        return Promotion.objects.create(
            name=f"Voucher {value}", kind=Promotion.Kind.VOUCHER, value=Decimal(value), promo_code=f"V{value}"
        )

    def test_voucher_applies_as_a_promotion_line(self):
        voucher = self.voucher("25.00")
        line = AppointmentLine.for_promotion(self.appointment, voucher, self.appointment.total_before_tax)
        line.save()
        self.assertEqual(line.kind, AppointmentLine.Kind.PROMOTION)
        self.assertEqual(line.promotion, voucher)
        self.assertEqual(line.amount, Decimal("-25.00"))
        self.assertEqual(self.appointment.total_before_tax, VERSION_1_PRICE - Decimal("25.00"))

    def test_voucher_never_takes_more_than_the_job(self):
        line = AppointmentLine.for_promotion(self.appointment, self.voucher("500.00"), VERSION_1_PRICE)
        line.save()
        self.assertEqual(self.appointment.total_before_tax, Decimal("0.00"))

    def test_percentage_promotion_rounds_to_the_nearest_cent(self):
        # Decision 0055. Invented percentages and amounts.
        cases = [
            ("15.000", "133.33", "20.00"),  # 19.9995
            ("10.000", "133.33", "13.33"),  # 13.333
            ("12.500", "0.20", "0.03"),  # 0.025, an exact half cent, rounds up
        ]
        for percent, amount, expected in cases:
            with self.subTest(percent=percent, amount=amount):
                promotion = Promotion(name="Test", kind=Promotion.Kind.PERCENT_OFF, value=Decimal(percent))
                self.assertEqual(promotion.discount_on(Decimal(amount)), Decimal(expected))

    def test_percentage_promotion_applies_as_a_promotion_line(self):
        promotion = Promotion.objects.create(
            name="Test percent", kind=Promotion.Kind.PERCENT_OFF, value=Decimal("15")
        )
        line = AppointmentLine.for_promotion(self.appointment, promotion, VERSION_1_PRICE)
        line.save()
        self.assertEqual(line.amount, Decimal("-15.00"))

    def test_voucher_needs_a_code(self):
        with self.assertRaises(IntegrityError):
            Promotion.objects.create(name="No code", kind=Promotion.Kind.VOUCHER, value=Decimal("25.00"))
