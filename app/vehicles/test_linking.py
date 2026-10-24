"""Linking customers' vehicles to the catalog (decisions 0077 and 0078): the
make spellings, aliases and trim words in data/vehicle-names.yaml, the
never-guess rule, what linking fills and never changes, the report, and
the imported motorcycle jobs."""

import datetime
import io
from decimal import Decimal

from django.core.management import call_command
from django.test import SimpleTestCase
from django.utils import timezone

from appointments.models import Appointment, AppointmentLine
from billing.models import Payment
from customers.models import Customer
from vehicles.classification.engine import apply, classify_catalog
from vehicles.linking import LINKED, NOT_FOUND, SEVERAL, Catalog, link_vehicles, match
from vehicles.models import ClassificationChange, ClassificationRule, Vehicle, VehicleClass, VehicleModel
from vehicles.test_classification import SMALL_SUVS, ClassificationTestCase, Source, add_facts, add_model
from vehicles.vehicle_data.names import load_names

MOTORCYCLE = VehicleModel.VehicleType.MOTORCYCLE
PICKUPS = ["Standard Pickup Trucks 4WD"]


class NamesTests(SimpleTestCase):
    """The spellings live in data/vehicle-names.yaml, not in code."""

    def test_customer_make_spellings(self):
        names = load_names()
        for spelling, make in (("Chevy", "Chevrolet"), ("Mercedes", "Mercedes-Benz"), ("Mercedes Benz", "Mercedes-Benz"), ("VW", "Volkswagen")):
            with self.subTest(spelling=spelling):
                self.assertEqual(names.make_key(spelling), names.make_key(make))

    def test_trim_words_are_read_as_words(self):
        names = load_names()
        self.assertTrue({"LE", "XLT", "EXL", "CREW", "CAB"} <= names.trim_words)
        # Words that name another vehicle are never trim words.
        self.assertFalse({"SPORT", "XL", "L", "HD", "2500"} & names.trim_words)

    def test_a_nameplates_words_are_known_for_its_base_model(self):
        names = load_names()
        self.assertIn("S", names.nameplate_words("Jeep", "Wagoneer"))
        self.assertIn("SPORT", names.nameplate_words("Hyundai", "Santa Fe"))


class LinkTestCase(ClassificationTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.customer = Customer.objects.create(first_name="Pat", last_name="Example", mobile="4235550101")
        cls.crossover = VehicleClass.objects.get(name="Crossovers & Wagons")
        cls.midsize = VehicleClass.objects.get(name="Midsize SUVs")
        cls.motorcycles = VehicleClass.objects.get(name="Motorcycles")
        for position, conditions, class_name in (
            (10, {"vehicle_type": ["motorcycle"]}, "Motorcycles"),
            (20, {"epa_size_class": SMALL_SUVS}, "Crossovers & Wagons"),
            (30, {"epa_size_class": PICKUPS}, "Fullsize Trucks"),
            (40, {"epa_size_class": ["Midsize Cars"]}, "Coupes & Sedans"),
        ):
            ClassificationRule.objects.create(
                position=position, name=f"rule {position}", conditions=conditions, vehicle_class=VehicleClass.objects.get(name=class_name)
            )

        cls.rav4 = add_model("Toyota", "RAV4", year_from=2015, year_to=2019)
        cls.camry = add_model("Toyota", "Camry", year_from=2015, year_to=2019)
        cls.f150 = add_model("Ford", "F-150", year_from=2015, year_to=2019)
        cls.silverado = add_model("Chevrolet", "Silverado", year_from=2015, year_to=2019)
        cls.crv = add_model("Honda", "CR-V", year_from=2015, year_to=2019)
        cls.gle = add_model("Mercedes-Benz", "GLE", year_from=2015, year_to=2019)
        for vehicle_model in (cls.rav4, cls.crv, cls.gle):
            for year in range(2015, 2020):
                add_facts(vehicle_model, year=year, epa_size_classes=SMALL_SUVS)
                add_facts(vehicle_model, Source.SEAT_LIST, year=year, seat_rows=[2])
        for vehicle_model in (cls.f150, cls.silverado):
            for year in range(2015, 2020):
                add_facts(vehicle_model, year=year, epa_size_classes=PICKUPS)
        for year in range(2015, 2020):
            add_facts(cls.camry, year=year, epa_size_classes=["Midsize Cars"], body_styles=["four-door"])
        apply(classify_catalog())

    def vehicle(self, year, make, model, vehicle_class=None, size=None, **fields):
        return Vehicle.objects.create(
            customer=self.customer, year=year, make=make, model=model, vehicle_class=vehicle_class, size_variant=size, **fields
        )

    def found(self, year, make, model):
        return match(Catalog(), year, make, model)


class MatchingTests(LinkTestCase):
    def test_spelling_differences_and_trim_words_find_the_model(self):
        for year, make, model, expected, dropped in (
            (2019, "Chevy", "Silverado 1500 LT", "silverado", ["LT"]),
            (2019, "Chevy", "Silverado", "silverado", []),
            (2018, "Mercedes", "GLE-Class", "gle", []),
            (2017, "Ford", "F150", "f150", []),
            (2017, "ford", "F 150 XLT SuperCrew", "f150", ["XLT", "SuperCrew"]),
            (2016, "Toyota", "Camry LE", "camry", ["LE"]),
            (2016, "Honda", "CR-V EX-L AWD", "crv", ["EX-L", "AWD"]),
            (2019, "Toyota", "rav 4", "rav4", []),
        ):
            with self.subTest(make=make, model=model):
                found = self.found(year, make, model)
                self.assertEqual(found.status, LINKED)
                self.assertEqual(found.vehicle_model, getattr(self, expected))
                self.assertEqual(found.dropped, dropped)

    def test_words_that_are_not_trim_words_are_never_dropped(self):
        found = self.found(2019, "Chevrolet", "Silverado 2500HD")
        self.assertEqual((found.status, found.vehicle_model), (NOT_FOUND, None))
        self.assertIn("nearest is the Chevrolet Silverado", found.reason)
        self.assertIn("2500HD", found.reason)

    def test_a_trim_word_that_names_a_nameplate_is_never_dropped(self):
        wagoneer = add_model("Jeep", "Wagoneer", year_from=2022, year_to=2026)
        self.assertEqual(self.found(2022, "Jeep", "Wagoneer Series II").status, NOT_FOUND)
        found = self.found(2022, "Jeep", "Wagoneer S")
        self.assertEqual(found.status, NOT_FOUND)
        self.assertIn("nameplates", found.reason)
        self.assertEqual(self.found(2022, "Jeep", "Wagoneer 4x4").vehicle_model, wagoneer)

    def test_a_year_outside_the_models_years_is_not_found(self):
        found = self.found(2012, "Toyota", "RAV4")
        self.assertEqual(found.status, NOT_FOUND)
        self.assertIn("2015 to 2019, not 2012", found.reason)

    def test_missing_details_and_unknown_makes_are_not_found(self):
        self.assertEqual(self.found(None, "Toyota", "RAV4").reason, "no year recorded")
        self.assertEqual(self.found(2019, "", "RAV4").reason, "no make or model recorded")
        self.assertIn("make_aliases", self.found(2019, "Chevvy", "Silverado").reason)


class NeverGuessTests(LinkTestCase):
    def test_two_candidates_are_listed_and_neither_is_linked(self):
        car = add_model("Honda", "Gold Wing", year_from=2015, year_to=2019)
        bike = VehicleModel.objects.create(
            make="Honda", model="Gold Wing", year_from=2015, year_to=2019, vehicle_type=MOTORCYCLE, source=VehicleModel.Source.NHTSA
        )
        found = self.found(2018, "Honda", "Gold Wing")
        self.assertEqual(found.status, SEVERAL)
        self.assertEqual(set(found.candidates), {car, bike})

        vehicle = self.vehicle(2018, "Honda", "Gold Wing")
        report = link_vehicles(apply=True)
        vehicle.refresh_from_db()
        self.assertIsNone(vehicle.vehicle_model)
        self.assertEqual([listed for listed, _ in report.several], [vehicle])

    def test_two_owner_records_covering_the_year_are_both_listed(self):
        add_model("Toyota", "Camry", year_from=2018, year_to=2019)
        found = self.found(2018, "Toyota", "Camry")
        self.assertEqual((found.status, len(found.candidates)), (SEVERAL, 2))
        # Outside the overlap, the one model is found.
        self.assertEqual(self.found(2016, "Toyota", "Camry").vehicle_model, self.camry)


class LinkRunTests(LinkTestCase):
    def test_linking_sets_the_model_and_fills_a_missing_size(self):
        vehicle = self.vehicle(2019, "Toyota", "RAV4", self.crossover)
        link_vehicles(apply=True)
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.vehicle_model, self.rav4)
        self.assertEqual(vehicle.size_variant, self.size("Crossovers & Wagons", 2))
        self.assertEqual(vehicle.missing_details, [])
        self.assertEqual(vehicle.history.first().history_change_reason, "link_vehicles")

    def test_linking_fills_a_missing_class(self):
        vehicle = self.vehicle(2019, "Toyota", "RAV4")
        link_vehicles(apply=True)
        vehicle.refresh_from_db()
        self.assertEqual((vehicle.vehicle_class, vehicle.size_variant.value), (self.crossover, 2))

    def test_a_class_the_vehicle_has_never_changes(self):
        three_rows = self.size("Midsize SUVs", 3)
        vehicle = self.vehicle(2019, "Toyota", "RAV4", self.midsize, three_rows)
        report = link_vehicles(apply=True)
        vehicle.refresh_from_db()
        self.assertEqual((vehicle.vehicle_model, vehicle.vehicle_class, vehicle.size_variant), (self.rav4, self.midsize, three_rows))
        self.assertEqual([(found.vehicle, found.kind) for found in report.differences], [(vehicle, "class")])

    def test_a_size_that_differs_is_listed(self):
        vehicle = self.vehicle(2019, "Toyota", "RAV4", self.crossover, self.size("Crossovers & Wagons", 3))
        report = link_vehicles(apply=True)
        self.assertEqual([(found.vehicle, found.kind) for found in report.differences], [(vehicle, "size")])

    def test_a_dry_run_changes_nothing(self):
        vehicle = self.vehicle(2019, "Toyota", "RAV4")
        out = io.StringIO()
        call_command("link_vehicles", "--dry-run", stdout=out)
        vehicle.refresh_from_db()
        self.assertIsNone(vehicle.vehicle_model)
        self.assertIsNone(vehicle.vehicle_class)
        self.assertFalse(ClassificationChange.objects.exists())
        self.assertIn("DRY RUN", out.getvalue())
        self.assertIn(f"vehicle {vehicle.pk}: 2019 Toyota RAV4 -> Toyota RAV4", out.getvalue())

    def test_a_rerun_keeps_an_earlier_link(self):
        vehicle = self.vehicle(2019, "Toyota", "RAV4", vehicle_model=self.crv)
        report = link_vehicles(apply=True)
        vehicle.refresh_from_db()
        self.assertEqual(vehicle.vehicle_model, self.crv)
        self.assertEqual([listed for listed, _ in report.kept_link], [vehicle])

    def test_the_report_names_vehicles_never_customers(self):
        self.vehicle(2019, "Toyota", "RAV4", self.midsize, color="blue")
        self.vehicle(2019, "Chevy", "Silverado 2500HD")
        self.vehicle(2019, "Toyota", "Camry", vehicle_model=self.rav4)
        out = io.StringIO()
        call_command("link_vehicles", stdout=out)
        text = out.getvalue()
        for heading in ("Linked (", "Not found (", "More than one candidate (", "Class or size variant differs"):
            self.assertIn(heading, text)
        self.assertIn("2019 Toyota RAV4, blue", text)
        self.assertNotIn("Pat", text)
        self.assertNotIn("Example", text)
        self.assertNotIn("4235550101", text)


class MotorcycleJobTests(LinkTestCase):
    """The exception (decision 0078): the imported motorcycle jobs get the
    Motorcycles class and the Motorcycle Detail service; amounts and
    payments stay as imported."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.sportster = VehicleModel.objects.create(
            make="Harley-Davidson", model="Sportster", year_from=2015, year_to=2019, vehicle_type=MOTORCYCLE, source=VehicleModel.Source.NHTSA
        )
        for year in range(2015, 2020):
            add_facts(cls.sportster, Source.VPIC, year=year, source_vehicle_types=["Motorcycle"])
        apply(classify_catalog())

    def job(self, vehicle, amount, baserow_id):
        appointment = Appointment.objects.create(
            customer=self.customer, vehicle=vehicle, scheduled_start=timezone.make_aware(datetime.datetime(2025, 6, 1, 9)),
            status=Appointment.Status.COMPLETED, source=Appointment.Source.IMPORT, baserow_id=baserow_id,
        )
        AppointmentLine.objects.create(appointment=appointment, kind=AppointmentLine.Kind.CUSTOM, description="Misc Services", amount=amount)
        Payment.objects.create(appointment=appointment, method="cash", amount=amount, paid_at=appointment.scheduled_start)
        return appointment

    def test_the_motorcycle_jobs_get_the_class_and_service_and_keep_their_amounts(self):
        bike = self.vehicle(2018, "Harley", "Sportster")
        flat, other = self.job(bike, Decimal("100.00"), 1), self.job(bike, Decimal("120.00"), 2)
        out = io.StringIO()
        call_command("link_vehicles", stdout=out)
        bike.refresh_from_db()
        self.assertEqual((bike.vehicle_model, bike.vehicle_class), (self.sportster, self.motorcycles))
        for appointment, amount in ((flat, Decimal("100.00")), (other, Decimal("120.00"))):
            line = appointment.lines.get()
            self.assertEqual((line.kind, line.service.name, line.description), (AppointmentLine.Kind.SERVICE, "Motorcycle Detail", "Motorcycle Detail"))
            self.assertEqual((line.vehicle_class, line.vehicle_class_name), (self.motorcycles, "Motorcycles"))
            self.assertEqual(line.amount, amount)
            self.assertEqual(appointment.payments.get().amount, amount)
        text = out.getvalue()
        self.assertIn(f"appointment {other.pk}", text)
        self.assertEqual(text.count("CHECK: the amount is not $100.00"), 1)
        self.assertIn("$120.00 (given)  CHECK", text)

    def test_other_past_jobs_never_change(self):
        car = self.vehicle(2019, "Toyota", "RAV4", self.midsize)
        appointment = self.job(car, Decimal("250.00"), 3)
        link_vehicles(apply=True)
        line = appointment.lines.get()
        self.assertEqual((line.kind, line.vehicle_class, line.service), (AppointmentLine.Kind.CUSTOM, None, None))

    def test_a_rerun_leaves_the_motorcycle_jobs_as_they_are(self):
        bike = self.vehicle(2018, "Harley-Davidson", "Sportster")
        appointment = self.job(bike, Decimal("100.00"), 4)
        link_vehicles(apply=True)
        changes = appointment.lines.get().history.count()
        report = link_vehicles(apply=True)
        self.assertEqual(appointment.lines.get().history.count(), changes)
        self.assertTrue(all(job.done for job in report.motorcycle_jobs))

    def test_a_dry_run_lists_the_jobs_and_changes_nothing(self):
        bike = self.vehicle(2018, "Harley", "Sportster")
        appointment = self.job(bike, Decimal("100.00"), 5)
        out = io.StringIO()
        call_command("link_vehicles", "--dry-run", stdout=out)
        self.assertIn("(to give)", out.getvalue())
        self.assertEqual(appointment.lines.get().kind, AppointmentLine.Kind.CUSTOM)
        bike.refresh_from_db()
        self.assertIsNone(bike.vehicle_class)
