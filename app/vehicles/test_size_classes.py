"""The size-based vehicle classes (decisions 0082 and 0083): box volume as a
fact, the rule order and the edges of each line, vans before pickups and the
pickup line, the three-row floor, seat rows, smoothing, the model overrides,
the EPA size class fallback, the newest-generation rule for customers'
vehicles with no year, the price book check, and apply_size_classes, which
switches everything in one transaction and changes nothing on a dry run."""

import datetime
import io
from decimal import Decimal
from unittest import mock

from django.apps import apps
from django.core.management import CommandError, call_command
from django.utils import timezone

from appointments import booking
from appointments.models import Appointment, RepricingDecision
from customers.models import Customer
from pricebook.checks import check, version_cells
from pricebook.management.commands.load_pricebook import Command as LoadPricebook
from pricebook.management.commands.load_pricebook import read_matrix, read_yaml
from pricebook.models import Price, PricebookVersion, PublishedVersionError, Service
from pricebook.publishing import decide, undecided_jobs
from vehicles import linking
from vehicles.classification.engine import Method, active_variants, apply, catalog_model_years, classify_by_rules, classify_catalog
from vehicles.classification.rules import ModelYear
from vehicles.classification.seed import SeedReport, sync_launch_set
from vehicles.classification.sizes import (
    BoxVolume,
    apply_pickup_line,
    apply_three_row_floor,
    box_volumes,
    classes_by_name,
    newest_generation,
    read_scheme,
)
from vehicles.classification.switch import is_minivan, switched
from vehicles.models import (
    ClassificationRule,
    ModelApproval,
    ModelOverride,
    ModelYearClassification,
    ModelYearSize,
    ReviewDecision,
    Vehicle,
    VehicleClass,
)
from vehicles.test_classification import SMALL_SUVS, ClassificationTestCase, Source, add_facts, add_model

STANDARD_SUVS = ["Standard Sport Utility Vehicle 4WD"]


def dimensions(lengths, width=72, height=60):
    """Canadian specifications for trims of these lengths. At 72 by 60
    inches, box volume is 2.5 cubic feet per inch of length."""
    return {
        "length_min": min(lengths), "length_max": max(lengths), "width_min": width, "width_max": width,
        "height_min": height, "height_max": height,
        "distribution": {
            "length": [float(length) for length in sorted(lengths)], "width": [float(width)] * len(lengths),
            "height": [float(height)] * len(lengths),
        },
    }


def cell(row):
    return (row["service"], row["vehicle_class"], row["size_variant"])


class SizeClassTestCase(ClassificationTestCase):
    def add_year(self, vehicle_model, year, lengths=None, epa=(), rows=None, **facts):
        if epa or facts:
            add_facts(vehicle_model, year=year, epa_size_classes=list(epa), **facts)
        if rows:
            add_facts(vehicle_model, Source.SEAT_LIST, year=year, seat_rows=list(rows))
        if lengths:
            add_facts(vehicle_model, Source.CANADA, year=year, **dimensions(lengths))

    def seed(self):
        sync_launch_set(SeedReport())

    def classified(self):
        self.seed()
        return classify_catalog()

    def result(self, results, vehicle_model, year):
        return results[(vehicle_model.pk, year)][1]


class BoxVolumeTests(SizeClassTestCase):
    def test_box_volume_is_the_median_trims_dimensions_and_a_year_without_takes_the_nearest(self):
        model = add_model("Acme", "Roamer", year_from=2018, year_to=2021)
        self.add_year(model, 2018, epa=SMALL_SUVS)
        self.add_year(model, 2019, lengths=(180, 182, 190))
        self.add_year(model, 2020, epa=SMALL_SUVS)
        self.add_year(model, 2021, lengths=(200,))
        found = box_volumes(catalog_model_years([model.pk]))
        self.assertEqual(found[(model.pk, 2019)], BoxVolume(Decimal("455.0")))
        self.assertEqual(found[(model.pk, 2021)], BoxVolume(Decimal("500.0")))
        # 2020 is as near 2019 as 2021, so takes the newer.
        self.assertEqual(found[(model.pk, 2020)], BoxVolume(Decimal("500.0"), 2021))
        self.assertEqual(str(found[(model.pk, 2018)]), "455.0 cu ft, inherited from 2019")

    def test_applying_the_rules_saves_each_model_years_box_volume(self):
        model = add_model("Acme", "Roamer", year_from=2019, year_to=2020)
        self.add_year(model, 2019, lengths=(200,), epa=SMALL_SUVS)
        self.add_year(model, 2020, epa=SMALL_SUVS)
        apply(self.classified())
        saved = {row.year: (row.box_volume, row.inherited_from) for row in ModelYearSize.objects.filter(vehicle_model=model)}
        self.assertEqual(saved, {2019: (Decimal("500.0"), None), 2020: (Decimal("500.0"), 2019)})


class RuleTests(SizeClassTestCase):
    """One model year at a time, with its box volume given exactly."""

    def setUp(self):
        self.seed()
        self.rules = list(ClassificationRule.objects.select_related("vehicle_class"))
        self.variants = active_variants()
        self.model = add_model("Acme", "Box")

    def classify(self, volume, rows=None, epa=(), model=None, **facts):
        model = model or self.model
        found = []
        if rows:
            found.append(add_facts(model, Source.SEAT_LIST, year=2019, seat_rows=list(rows)))
        if epa or facts:
            found.append(add_facts(model, year=2019, epa_size_classes=list(epa), **facts))
        model_year = ModelYear(model, 2019, found)
        model_year.box_volume = BoxVolume(Decimal(volume)) if volume is not None else None
        model_year.sized = True
        results = {(model.pk, 2019): (model_year, classify_by_rules(model_year, self.rules, self.variants))}
        data = read_scheme()
        apply_pickup_line(results, data["pickup_line"], classes_by_name(), self.variants)
        apply_three_row_floor(results, data["three_row_floor"], classes_by_name(), self.variants)
        for row in found:
            row.delete()
        return results[(model.pk, 2019)][1]

    def test_each_line_belongs_to_the_class_above_it(self):
        for volume, expected in (
            ("0.1", "Small"), ("489.9", "Small"), ("490.0", "Medium"), ("579.9", "Medium"), ("580.0", "Large"),
            ("699.9", "Large"), ("700.0", "Full-size"), ("864.9", "Full-size"), ("865.0", "Full-size Vans"), ("1200", "Full-size Vans"),
        ):
            with self.subTest(volume=volume):
                self.assertEqual(self.classify(volume).vehicle_class.name, expected)

    def test_a_three_row_vehicle_under_the_medium_line_is_medium(self):
        three = self.classify("400", rows=[3])
        self.assertEqual((three.vehicle_class.name, three.size_variant.value), ("Medium", 3))
        # An optional third row does not count; its size is asked.
        optional = self.classify("400", rows=[2, 3])
        self.assertEqual((optional.vehicle_class.name, optional.ask_size), ("Small", True))
        self.assertEqual(self.classify("600", rows=[3]).vehicle_class.name, "Large")

    def test_seat_rows_are_one_for_two_seaters_and_otherwise_two_unless_listed(self):
        self.assertEqual(self.classify("400", epa=["Two Seaters"]).size_variant.value, 1)
        self.assertEqual(self.classify("400").size_variant.value, 2)
        self.assertEqual(self.classify("400", rows=[2]).size_variant.value, 2)

    def test_full_size_vans_are_quoted_and_have_one_price(self):
        vans = self.classify("900")
        self.assertEqual(vans.vehicle_class.booking, VehicleClass.Booking.QUOTE)
        self.assertIsNone(vans.size_variant)
        self.assertFalse(vans.ask_size)

    def test_the_lines_are_settings_in_the_data_file(self):
        data = read_scheme()
        self.assertEqual({line["name"]: line["at"] for line in data["lines"]}, {"medium": 490, "large": 580, "full-size": 700, "full-size vans": 865})
        self.assertEqual(data["pickup_line"]["at"], 760)
        medium = next(rule for rule in self.rules if rule.name == "Medium")
        self.assertEqual(medium.conditions, {"box_volume": {"at_least": 490, "under": 580}})

    def test_vans_come_before_the_pickup_rules_and_are_classed_by_size(self):
        truck = {"source_vehicle_types": ["Truck"]}
        for name, volume, expected in (
            ("Express 2500", "900", "Full-size Vans"),
            ("ProMaster 3500", "1100", "Full-size Vans"),
            ("Transit-350 HD", "950", "Full-size Vans"),
            ("Transit Connect", "520", "Medium"),
            ("ProMaster City", "560", "Medium"),
            ("NV200", "470", "Small"),
            ("Metris", "640", "Large"),
            ("Sierra 2500HD", "900", "Full-size Trucks"),
        ):
            with self.subTest(model=name):
                model = add_model("Acme", name)
                self.assertEqual(self.classify(volume, model=model, **truck).vehicle_class.name, expected)

    def test_the_pickup_line_is_760_and_a_pickup_with_no_box_volume_keeps_its_epa_label(self):
        small, standard = ["Small Pickup Trucks 4WD"], ["Standard Pickup Trucks 4WD"]
        for volume, epa, expected in (
            ("759.9", small, "Light Pickups"),
            ("760.0", small, "Full-size Trucks"),
            ("759.9", standard, "Light Pickups"),
            ("760.0", standard, "Full-size Trucks"),
            (None, small, "Light Pickups"),
            (None, standard, "Full-size Trucks"),
        ):
            with self.subTest(volume=volume, epa=epa):
                result = self.classify(volume, epa=epa)
                self.assertEqual(result.vehicle_class.name, expected)
                self.assertEqual(result.method, Method.RULE if volume is None else Method.PICKUP_LINE)
        heavy = add_model("Ford", "F-350 Super Duty")
        self.assertEqual(self.classify(None, model=heavy, source_vehicle_types=["Truck"]).vehicle_class.name, "Full-size Trucks")
        self.assertIn("at or over the 760 cu ft pickup line", self.classify("760.0", epa=small).because)


class SchemeTests(SizeClassTestCase):
    def test_the_santa_cruz_and_maverick_are_pickups(self):
        santa_cruz = add_model("Hyundai", "Santa Cruz", year_from=2022, year_to=2022)
        self.add_year(santa_cruz, 2022, lengths=(195,), epa=["Small Sport Utility Vehicle 4WD"])
        maverick = add_model("Ford", "Maverick", year_from=2022, year_to=2022)
        self.add_year(maverick, 2022, lengths=(200,), epa=["Small Pickup Trucks 2WD"])
        results = self.classified()
        self.assertEqual(self.result(results, santa_cruz, 2022).vehicle_class.name, "Light Pickups")
        self.assertEqual(self.result(results, maverick, 2022).vehicle_class.name, "Light Pickups")

    def test_a_model_with_no_measurements_takes_its_epa_size_class_majority(self):
        for name, length in (("One", 200), ("Two", 204), ("Three", 180)):
            model = add_model("Acme", name)
            self.add_year(model, 2019, lengths=(length,), epa=["Midsize Cars"])
        unmeasured = add_model("Acme", "Unmeasured")
        self.add_year(unmeasured, 2019, epa=["Midsize Cars"])
        lonely = add_model("Acme", "Lonely")
        self.add_year(lonely, 2019, epa=["Compact Cars"])
        bare = add_model("Acme", "Bare")
        add_facts(bare, Source.VPIC, year=2019, source_vehicle_types=["Passenger Car"])
        results = self.classified()
        result = self.result(results, unmeasured, 2019)
        self.assertEqual((result.vehicle_class.name, result.method), ("Medium", Method.EPA_FALLBACK))
        self.assertIn("most measured Midsize Cars model years are Medium", result.because)
        self.assertIsNone(self.result(results, lonely, 2019).vehicle_class)
        self.assertIn("no EPA size class", self.result(results, bare, 2019).because)

    def flip(self, years_between):
        """A model in Medium for four years, then Large for years_between years, then Medium again."""
        last = 2010 + 4 + years_between + 4 - 1
        model = add_model("Acme", f"Flip {years_between}", year_from=2010, year_to=last)
        for year in range(2010, last + 1):
            large = 2014 <= year < 2014 + years_between
            self.add_year(model, year, lengths=(240 if large else 200,), epa=SMALL_SUVS)
        return model

    def test_a_run_of_up_to_six_years_between_two_runs_of_one_class_takes_that_class(self):
        six, seven = self.flip(6), self.flip(7)
        results = self.classified()
        for year in range(2014, 2020):
            result = self.result(results, six, year)
            self.assertEqual((result.vehicle_class.name, result.method), ("Medium", Method.SMOOTHED))
        self.assertIn("smoothed: 2014-2019 lies between two runs of Medium; rule 100: Large gives Large", result.because)
        self.assertEqual(self.result(results, six, 2013).method, Method.RULE)
        self.assertEqual({self.result(results, seven, year).vehicle_class.name for year in range(2014, 2021)}, {"Large"})
        out = io.StringIO()
        call_command("classify_vehicles", "--dry-run", stdout=out)
        self.assertIn("Smoothed: runs of model years given the class around them (1)", out.getvalue())
        self.assertIn("Acme Flip 6 2014-2019: Medium, smoothed from Large", out.getvalue())

    def test_an_override_is_never_smoothed(self):
        model = self.flip(2)
        self.seed()
        ModelOverride.objects.create(vehicle_model=model, year_from=2014, year_to=2015, vehicle_class=self.vehicle_class("Large"))
        results = classify_catalog()
        self.assertEqual({self.result(results, model, year).method for year in (2014, 2015)}, {Method.OVERRIDE})

    def test_the_three_model_overrides(self):
        q4 = add_model("Audi", "Q4 e-tron", year_from=2021, year_to=2026)
        cayenne = add_model("Porsche", "Cayenne", year_from=2025, year_to=2026)
        ix = add_model("BMW", "iX", year_from=2025, year_to=2026)
        for year in range(2021, 2027):
            self.add_year(q4, year, lengths=(240,), epa=SMALL_SUVS)
        for year in (2025, 2026):
            self.add_year(cayenne, year, lengths=(290,), epa=STANDARD_SUVS)
            self.add_year(ix, year, lengths=(240,), epa=STANDARD_SUVS)
        results = self.classified()
        self.assertEqual(self.result(results, q4, 2021).vehicle_class.name, "Large")
        for year in range(2022, 2027):
            result = self.result(results, q4, year)
            self.assertEqual((result.vehicle_class.name, result.method), ("Medium", Method.OVERRIDE))
        self.assertEqual(self.result(results, cayenne, 2025).vehicle_class.name, "Full-size")
        self.assertEqual(self.result(results, cayenne, 2026).vehicle_class.name, "Large")
        self.assertEqual(self.result(results, ix, 2025).vehicle_class.name, "Large")
        self.assertEqual(self.result(results, ix, 2026).vehicle_class.name, "Medium")

    def test_the_newest_generation_is_its_newest_years_within_an_inch(self):
        model = add_model("Acme", "Grower", year_from=2015, year_to=2025)
        for year in range(2015, 2025):
            self.add_year(model, year, lengths=(180 if year < 2020 else 240 + (year - 2020) * 0.2,), epa=SMALL_SUVS)
        self.add_year(model, 2025, epa=SMALL_SUVS)
        results = self.classified()
        entries = [(year, *results[(model.pk, year)]) for year in range(2015, 2026)]
        result, first, last = newest_generation(entries)
        self.assertEqual((result.vehicle_class.name, first, last), ("Large", 2020, 2025))
        self.assertIsNone(newest_generation([]))


class PriceBookCheckTests(SizeClassTestCase):
    def test_the_price_book_in_data_passes(self):
        self.assertEqual(check(read_matrix()), [])

    def test_the_maintenance_plans_follow_full_detail(self):
        matrix = [row for row in read_matrix() if cell(row) != ("Quarterly Maintenance", "Medium", 2)]
        for row in matrix:
            if cell(row) == ("Monthly Maintenance", "Small", 2):
                row["price"] = Decimal("120")
            if cell(row) == ("Quarterly Maintenance", "Large", 3):
                row["hours"] = Decimal("5")
        problems = check(matrix)
        self.assertIn("Monthly Maintenance / Small size 2 is $120; 50% of Full Detail is $115.00.", problems)
        self.assertIn("Quarterly Maintenance / Large size 3 is 5 hours; Full Detail is 6.", problems)
        self.assertIn("Quarterly Maintenance / Medium size 2 is missing: Full Detail has a price there.", problems)

    def test_every_class_and_row_count_the_rules_can_give_needs_a_full_detail_price(self):
        matrix = [row for row in read_matrix() if cell(row) != ("Full Detail", "Large", 3)]
        self.assertTrue(any(problem.startswith("Large size 3 has no Full Detail price") for problem in check(matrix)))
        # A class and size the classified catalog gives counts too; a quote-only class needs no price.
        produced = {("Full-size", 2): ["2024 Acme Big"], ("Full-size Vans", None): ["2024 Acme Van"], ("Motorcycles", None): ["2024 Acme Bike"]}
        self.assertEqual(check(read_matrix(), produced), ["Full-size size 2 has no Full Detail price, but the rules can give it: 2024 Acme Big."])

    def test_load_pricebook_refuses_a_price_book_that_fails(self):
        matrix = [row for row in read_matrix() if cell(row)[:2] != ("Full Detail", "Medium")]
        with mock.patch("pricebook.management.commands.load_pricebook.read_matrix", return_value=matrix):
            with self.assertRaisesMessage(CommandError, "fails the price book check"):
                call_command("load_pricebook", stdout=io.StringIO(), stderr=io.StringIO())


class BodyTypeWorld(SizeClassTestCase):
    """The database as the server has it before apply_size_classes: the
    body-type classes live and priced in version 1, the old rules, an
    override, a decision and an approval, customers' vehicles and their jobs,
    and load_pricebook's draft of the new price book."""

    @classmethod
    def setUpTestData(cls):
        command = LoadPricebook(stdout=io.StringIO())
        command.load_classes(read_yaml("vehicle-classes.yaml"))
        command.load_services(read_yaml("services.yaml"))
        old_names = {"Light Pickups": "Light Pickups & Offroad", "Full-size Trucks": "Fullsize Trucks"}
        for vehicle_class in VehicleClass.objects.all():
            if not vehicle_class.active:
                vehicle_class.active = True
            elif vehicle_class.name in old_names:
                vehicle_class.name = old_names[vehicle_class.name]
            elif vehicle_class.name != "Motorcycles":
                vehicle_class.pending = True
            vehicle_class.save()
        cls.crossover = VehicleClass.objects.get(name="Crossovers & Wagons")
        cls.two_rows = cls.crossover.size_variants.get(value=2)
        version = PricebookVersion.objects.create(number=1)
        command.load_rules(version, read_yaml("pricing-rules.yaml"))
        Price.objects.create(
            version=version, service=Service.objects.get(name="Full Detail"), vehicle_class=cls.crossover,
            size_variant=cls.two_rows, price=Decimal("250"), one_person_service_hours=Decimal("5"),
        )
        version.publish(timezone.localdate())
        call_command("load_pricebook", stdout=io.StringIO())
        cls.customer = Customer.objects.create(first_name="Pat", last_name="Example", mobile="4235550101")

    def setUp(self):
        self.assertFalse(switched())
        self.draft = PricebookVersion.objects.get(number=2)
        self.grower = add_model("Acme", "Grower", year_from=2018, year_to=2020)
        self.add_year(self.grower, 2018, lengths=(180,), epa=SMALL_SUVS)
        for year in (2019, 2020):
            self.add_year(self.grower, year, lengths=(240,), epa=SMALL_SUVS)
        self.old_rule = ClassificationRule.objects.create(position=10, name="EPA small SUVs", conditions={"epa_size_class": SMALL_SUVS}, vehicle_class=self.crossover)
        self.override = ModelOverride.objects.create(vehicle_model=self.grower, year_from=2018, year_to=2018, vehicle_class=self.crossover)
        self.decision = ReviewDecision.objects.create(vehicle_model=self.grower, year=2020, vehicle_class=self.crossover)
        apply(classify_catalog())
        self.approval = ModelApproval.objects.create(
            vehicle_model=self.grower, year_from=2019, year_to=2019, vehicle_class=self.crossover, size="two rows", how="rule 10: EPA small SUVs"
        )
        self.linked = Vehicle.objects.create(
            customer=self.customer, vehicle_model=self.grower, year=2019, make="Acme", model="Grower", vehicle_class=self.crossover, size_variant=self.two_rows
        )
        self.no_year = Vehicle.objects.create(customer=self.customer, vehicle_model=self.grower, make="Acme", model="Grower", vehicle_class=self.crossover)
        self.unlinked = Vehicle.objects.create(
            customer=self.customer, make="Acme", model="Sienna XLE", vehicle_class=VehicleClass.objects.get(name="Fullsize SUVs & Minivans")
        )
        inputs = booking.JobInputs(Service.objects.get(name="Full Detail"), self.crossover, self.two_rows, 1)
        today = timezone.localdate()
        at = lambda day: timezone.make_aware(datetime.datetime.combine(day, datetime.time(8)))  # noqa: E731
        self.past = booking.book(self.customer, self.linked, at(today - datetime.timedelta(days=30)), inputs)
        booking.set_status(self.past, Appointment.Status.COMPLETED)
        self.future = booking.book(self.customer, self.linked, at(today + datetime.timedelta(days=10)), inputs)

    def apply_sizes(self, *extra, effective=None):
        out = io.StringIO()
        call_command("apply_size_classes", "--effective", (effective or timezone.localdate()).isoformat(), *extra, stdout=out)
        return out.getvalue()


class LoadPricebookDraftTests(BodyTypeWorld):
    def test_the_new_price_book_is_a_draft_whose_classes_wait(self):
        self.assertFalse(self.draft.is_published)
        self.assertTrue(VehicleClass.objects.get(name="Small").pending)
        self.assertNotIn("Small", [found.name for found in VehicleClass.objects.offered()])
        # Light Pickups is priced under its old name until the switch renames it.
        self.assertTrue(self.draft.prices.filter(vehicle_class__name="Light Pickups & Offroad").exists())
        with self.assertRaises(PublishedVersionError):
            self.draft.publish(timezone.localdate())

    def test_classify_vehicles_keeps_the_body_type_rules_until_the_switch(self):
        out = io.StringIO()
        call_command("classify_vehicles", stdout=out)
        self.assertIn("The size-based classes are not applied yet", out.getvalue())
        self.assertEqual(list(ClassificationRule.objects.all()), [self.old_rule])


class ApplyTests(BodyTypeWorld):
    def test_a_dry_run_changes_nothing(self):
        counts = lambda: {model._meta.label: model._base_manager.count() for model in apps.get_models()}  # noqa: E731
        stored = list(ModelYearClassification.objects.values_list("vehicle_model_id", "year", "vehicle_class_id", "method"))
        before = counts()
        text = self.apply_sizes("--dry-run")
        self.assertEqual(counts(), before)
        self.assertEqual(list(ModelYearClassification.objects.values_list("vehicle_model_id", "year", "vehicle_class_id", "method")), stored)
        self.assertFalse(switched())
        self.assertFalse(PricebookVersion.objects.get(number=2).is_published)
        for heading in (
            "DRY RUN", "The switch", "Price book check: passed", "Model years by new class", "EPA size class fallback",
            "Near a line", "Smoothed", "Models whose class changes", "Model overrides archived", "Approvals archived",
            "Customer vehicles", "Booked jobs", "Pickup ladder", "Pickup check", "Van check",
        ):
            self.assertIn(heading, text)
        self.assertIn("retired Crossovers & Wagons", text)
        self.assertIn("renamed Light Pickups & Offroad to Light Pickups", text)
        for private in ("Pat", "Example", "4235550101"):
            self.assertNotIn(private, text)

    def test_it_applies_everything_in_one_step(self):
        self.assertIn("APPLIED", self.apply_sizes())
        self.assertTrue(switched())
        draft = PricebookVersion.objects.get(number=2)
        self.assertEqual((draft.is_published, draft.effective_date), (True, timezone.localdate()))
        self.assertEqual(PricebookVersion.current(), draft)
        self.assertFalse(VehicleClass.objects.get(name="Small").pending)
        self.assertTrue(VehicleClass.objects.filter(name="Light Pickups").exists())
        self.assertTrue(VehicleClass.objects.filter(name="Full-size Trucks").exists())
        self.assertFalse(VehicleClass.objects.get(name="Crossovers & Wagons").active)
        self.assertNotIn("Crossovers & Wagons", [found.name for found in VehicleClass.objects.offered()])
        # The old rules, override, decision and approval are archived and kept for history.
        for model, record in ((ClassificationRule, self.old_rule), (ModelOverride, self.override), (ReviewDecision, self.decision), (ModelApproval, self.approval)):
            with self.subTest(model=model.__name__):
                self.assertFalse(model.objects.filter(pk=record.pk).exists())
                self.assertIsNotNone(model.all_objects.get(pk=record.pk).archived_at)
        self.assertEqual(ClassificationRule.objects.count(), len(read_scheme()["rules"]))
        classes = dict(ModelYearClassification.objects.filter(vehicle_model=self.grower).values_list("year", "vehicle_class__name"))
        self.assertEqual(classes, {2018: "Small", 2019: "Large", 2020: "Large"})

    def test_customers_vehicles_take_the_new_classes(self):
        self.apply_sizes()
        self.linked.refresh_from_db()
        self.assertEqual((self.linked.vehicle_class.name, self.linked.size_variant.value, self.linked.confirm_year), ("Large", 2, False))
        # No year: the newest generation's class, flagged to confirm the year.
        self.no_year.refresh_from_db()
        self.assertEqual((self.no_year.vehicle_class.name, self.no_year.confirm_year), ("Large", True))
        # Not linked: left in its retired class, with a proposed class on the differences screen.
        self.unlinked.refresh_from_db()
        self.assertEqual(self.unlinked.vehicle_class.name, "Fullsize SUVs & Minivans")
        [proposal] = linking.retired_class_vehicles()
        self.assertEqual((proposal.vehicle, proposal.proposed.name), (self.unlinked, "Large"))

    def test_booked_jobs_keep_their_quoted_price_and_past_jobs_their_class(self):
        self.apply_sizes()
        self.future.refresh_from_db()
        self.assertEqual(self.future.total_before_tax, Decimal("250.00"))
        self.assertEqual(self.future.lines.get().vehicle_class, self.crossover)
        self.past.refresh_from_db()
        line = self.past.lines.get()
        self.assertEqual((line.vehicle_class, line.vehicle_class_name), (self.crossover, "Crossovers & Wagons"))
        self.assertEqual(self.past.quote.vehicle_class, self.crossover)
        # The booked-job review lists the future job with its price under the new book.
        draft = PricebookVersion.objects.get(number=2)
        [job] = undecided_jobs(draft)
        self.assertEqual(job.appointment, self.future)
        self.assertEqual((job.booked_total, job.new_total, job.new_class.name), (Decimal("250.00"), Decimal("280.00"), "Large"))
        self.assertFalse(RepricingDecision.objects.exists())
        decide(draft, job, "use_new")
        self.future.refresh_from_db()
        self.assertEqual(self.future.total_before_tax, Decimal("280.00"))
        self.assertEqual(self.future.lines.get().vehicle_class.name, "Large")
        self.assertEqual(undecided_jobs(draft), [])

    def test_a_draft_that_fails_the_check_changes_nothing(self):
        self.draft.prices.filter(service__name="Full Detail", vehicle_class__name="Large", size_variant__value=3).delete()
        with self.assertRaisesMessage(CommandError, "fails the check"):
            self.apply_sizes()
        self.assertFalse(switched())
        self.assertFalse(PricebookVersion.objects.get(number=2).is_published)
        self.assertTrue(ClassificationRule.objects.filter(pk=self.old_rule.pk).exists())

    def test_the_effective_date_is_the_day_it_runs(self):
        tomorrow = timezone.localdate() + datetime.timedelta(days=1)
        with self.assertRaisesMessage(CommandError, "on the day they take effect"):
            self.apply_sizes(effective=tomorrow)
        self.assertIn("DRY RUN", self.apply_sizes("--dry-run", effective=tomorrow))
        self.apply_sizes()
        with self.assertRaisesMessage(CommandError, "already applied"):
            self.apply_sizes()

    def test_the_check_counts_every_class_and_size_the_catalog_gives(self):
        cells = version_cells(self.draft)
        self.assertEqual(check(cells), [])
        self.assertEqual(
            check(cells, {("Medium", 1): ["2019 Acme Roadster"]}),
            ["Medium size 1 has no Full Detail price, but the rules can give it: 2019 Acme Roadster."],
        )


class MinivanTests(SizeClassTestCase):
    def test_minivans_are_recognized_by_whole_words(self):
        self.assertTrue(is_minivan("Grand Caravan SXT", ["Grand Caravan"]))
        self.assertTrue(is_minivan("Town & Country", ["Town & Country"]))
        self.assertFalse(is_minivan("Questor", ["Quest"]))


class JobsToCheckByHandTests(BodyTypeWorld):
    """Booked jobs in a retired class that cannot be re-priced in a vehicle's
    new class: no vehicle, a vehicle with no class, a vehicle with no size."""

    def setUp(self):
        super().setUp()
        inputs = booking.JobInputs(Service.objects.get(name="Full Detail"), self.crossover, self.two_rows, 1)
        day = timezone.localdate() + datetime.timedelta(days=12)
        at = lambda hour: timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour)))  # noqa: E731
        classless = Vehicle.objects.create(customer=self.customer, make="Acme", model="Mystery")
        sizeless = Vehicle.objects.create(
            customer=self.customer, make="Acme", model="Hauler", vehicle_class=VehicleClass.objects.get(name="Light Pickups & Offroad")
        )
        self.by_hand = [
            booking.book(self.customer, None, at(8), inputs),
            booking.book(self.customer, classless, at(10), inputs),
            booking.book(self.customer, sizeless, at(12), inputs),
        ]

    def test_the_dry_run_lists_them_in_their_own_section_and_changes_nothing(self):
        counts = lambda: {model._meta.label: model._base_manager.count() for model in apps.get_models()}  # noqa: E731
        before = counts()
        text = self.apply_sizes("--dry-run")
        self.assertEqual(counts(), before)
        section = text.split("Booked jobs to check by hand", 1)[1].split("\nBooked jobs from", 1)[0]
        self.assertIn("(3)", section)
        for appointment in self.by_hand:
            self.assertIn(f"appointment {appointment.pk} on ", section)
        self.assertIn(f"appointment {self.by_hand[0].pk} on {(timezone.localdate() + datetime.timedelta(days=12)):%Y-%m-%d}, no vehicle", section)
        self.assertEqual(section.count("no vehicle or class: check by hand"), 3)
        for private in ("Pat", "Example", "4235550101"):
            self.assertNotIn(private, text)

    def test_they_keep_their_quoted_price_and_wait_on_the_booked_job_review(self):
        self.apply_sizes()
        draft = PricebookVersion.objects.get(number=2)
        jobs = {job.appointment: job for job in undecided_jobs(draft)}
        for appointment in self.by_hand:
            appointment.refresh_from_db()
            self.assertEqual(appointment.total_before_tax, Decimal("250.00"))
            self.assertTrue(jobs[appointment].check_by_hand)
            self.assertIsNone(jobs[appointment].new_total)
        self.assertFalse(jobs[self.future].check_by_hand)

    def test_a_failure_partway_says_what_and_where_and_changes_nothing(self):
        def broken(appointment, version):
            raise RuntimeError("an unexpected gap")

        with mock.patch("pricebook.publishing._reprice", broken):
            with self.assertRaises(CommandError) as raised:
                self.apply_sizes()
        message = str(raised.exception)
        self.assertIn("stopped while publishing the draft and re-pricing booked jobs", message)
        self.assertRegex(message, r"re-pricing appointment \d+ on \d{4}-\d{2}-\d{2}")
        self.assertIn("RuntimeError: an unexpected gap. Nothing was changed.", message)
        self.assertNotIn("Pat", message)
        self.assertFalse(switched())
        self.assertFalse(PricebookVersion.objects.get(number=2).is_published)
        self.assertTrue(ClassificationRule.objects.filter(pk=self.old_rule.pk).exists())


class FollowUpRuleTests(SizeClassTestCase):
    """The fixes from the owner's first apply_size_classes dry run (decision 0085)."""

    def test_minivans_are_always_three_rows(self):
        odyssey = add_model("Honda", "Odyssey", year_from=2020, year_to=2020)
        self.add_year(odyssey, 2020, lengths=(260,), epa=["Minivan - 2WD"])
        # A Sienna year with no EPA size class is a minivan by the list in data.
        sienna = add_model("Toyota", "Sienna", year_from=2021, year_to=2021)
        add_facts(sienna, Source.VPIC, year=2021, source_vehicle_types=["Multipurpose Passenger Vehicle (MPV)"])
        add_facts(sienna, Source.CANADA, year=2021, **dimensions([270]))
        results = self.classified()
        for model, year in ((odyssey, 2020), (sienna, 2021)):
            with self.subTest(model=model.model):
                result = self.result(results, model, year)
                self.assertEqual((result.vehicle_class.name, result.size_variant.value, result.ask_size), ("Large", 3, False))

    def test_full_size_is_always_three_rows_and_the_check_counts_only_three(self):
        from vehicles.classification.sizes import produced

        big = add_model("Acme", "Big Two Row", year_from=2024, year_to=2024)
        self.add_year(big, 2024, lengths=(300,), epa=STANDARD_SUVS, rows=[2])
        results = self.classified()
        result = self.result(results, big, 2024)
        self.assertEqual((result.vehicle_class.name, result.size_variant.value), ("Full-size", 3))
        found = produced(results, active_variants())
        self.assertIn(("Full-size", 3), found)
        self.assertNotIn(("Full-size", 2), found)

    def test_one_row_is_only_in_small(self):
        sl = add_model("Mercedes-Benz", "500SL", year_from=1990, year_to=1990)
        self.add_year(sl, 1990, lengths=(200,), epa=["Two Seaters"])
        roadster = add_model("Acme", "Roadster", year_from=1990, year_to=1990)
        self.add_year(roadster, 1990, lengths=(170,), epa=["Two Seaters"])
        results = self.classified()
        result = self.result(results, sl, 1990)
        self.assertEqual((result.vehicle_class.name, result.size_variant.value), ("Medium", 2))
        result = self.result(results, roadster, 1990)
        self.assertEqual((result.vehicle_class.name, result.size_variant.value), ("Small", 1))

    def test_a_pickup_in_any_model_year_is_a_pickup_in_all_of_them(self):
        tundra = add_model("Toyota", "Tundra", year_from=1995, year_to=2001)
        for year in range(1995, 2000):
            self.add_year(tundra, year, lengths=(260,), epa=["Special Purpose Vehicle 2WD"])
        for year in (2000, 2001):
            self.add_year(tundra, year, lengths=(320,), epa=["Standard Pickup Trucks 4WD"])
        titan = add_model("Nissan", "Titan", year_from=2002, year_to=2006)
        for year in (2002, 2003):
            add_facts(titan, Source.CANADA, year=year, **dimensions([290]))
        for year in (2004, 2005, 2006):
            self.add_year(titan, year, lengths=(320,), epa=["Standard Pickup Trucks 4WD"])
        f150 = add_model("Ford", "F-150", year_from=2004, year_to=2004)
        self.add_year(f150, 2004, lengths=(300,), epa=["Standard Pickup Trucks 4WD"])
        unmeasured = add_model("Acme", "Old Hauler", year_from=1999, year_to=2000)
        add_facts(unmeasured, Source.VPIC, year=1999, source_vehicle_types=["Multipurpose Passenger Vehicle (MPV)"])
        add_facts(unmeasured, year=2000, epa_size_classes=["Standard Pickup Trucks 2WD"])
        results = self.classified()
        # Older full-size pickups that measure under 760 cu ft are Light Pickups (the owner's decision).
        for year in range(1995, 2000):
            result = self.result(results, tundra, year)
            self.assertEqual((result.vehicle_class.name, result.method), ("Light Pickups", Method.PICKUP_LINE))
        self.assertIn("a pickup in every model year: 2000-2001 are pickups by rule", result.because)
        self.assertEqual({self.result(results, tundra, year).vehicle_class.name for year in (2000, 2001)}, {"Full-size Trucks"})
        self.assertEqual({self.result(results, titan, year).vehicle_class.name for year in (2002, 2003)}, {"Light Pickups"})
        self.assertEqual(self.result(results, f150, 2004).vehicle_class.name, "Light Pickups")
        # With no box volume, it takes the class its pickup years have.
        result = self.result(results, unmeasured, 1999)
        self.assertEqual((result.vehicle_class.name, result.method), ("Full-size Trucks", Method.PICKUP_MODEL))

    def test_full_size_vans_by_nameplate_whatever_they_measure(self):
        express = add_model("Chevrolet", "Express Passenger", year_from=2010, year_to=2010)
        self.add_year(express, 2010, lengths=(260,), epa=["Vans, Passenger Type"])
        e250 = add_model("Ford", "E-250", year_from=2008, year_to=2008)
        add_facts(e250, Source.VPIC, year=2008, source_vehicle_types=["Truck"])
        add_facts(e250, Source.CANADA, year=2008, **dimensions([280]))
        sprinter = add_model("Freightliner", "Sprinter", year_from=2008, year_to=2008)
        self.add_year(sprinter, 2008, lengths=(180,), source_vehicle_types=["Truck"])
        connect = add_model("Ford", "Transit Connect", year_from=2015, year_to=2015)
        self.add_year(connect, 2015, lengths=(210,), epa=["Special Purpose Vehicle 2WD"])
        city = add_model("Ram", "ProMaster City", year_from=2015, year_to=2015)
        self.add_year(city, 2015, lengths=(220,), epa=["Special Purpose Vehicle 2WD"])
        results = self.classified()
        for model, year in ((express, 2010), (e250, 2008), (sprinter, 2008)):
            with self.subTest(model=model.model):
                self.assertEqual(self.result(results, model, year).vehicle_class.name, "Full-size Vans")
        self.assertEqual(self.result(results, connect, 2015).vehicle_class.name, "Medium")
        self.assertEqual(self.result(results, city, 2015).vehicle_class.name, "Medium")

    def test_the_escalade_override(self):
        escalade = add_model("Cadillac", "Escalade", year_from=2007, year_to=2015)
        for year in range(2007, 2016):
            self.add_year(escalade, year, lengths=(260,), epa=STANDARD_SUVS, rows=[3])
        results = self.classified()
        for year in range(2007, 2015):
            result = self.result(results, escalade, year)
            self.assertEqual((result.vehicle_class.name, result.method, result.size_variant.value), ("Full-size", Method.OVERRIDE, 3))
        self.assertEqual(self.result(results, escalade, 2015).vehicle_class.name, "Large")

    def test_the_report_lists_a_smooth_away_from_the_newest_generation(self):
        model = add_model("Acme", "Backwards", year_from=2001, year_to=2015)
        for year in range(2001, 2016):
            if year < 2005 or 2007 <= year <= 2010:
                length = 240
            else:
                length = 200 if year < 2011 else 205
            self.add_year(model, year, lengths=(length,), epa=SMALL_SUVS)
        forwards = add_model("Acme", "Forwards", year_from=2010, year_to=2019)
        for year in range(2010, 2020):
            self.add_year(forwards, year, lengths=(240 if year in (2014, 2015) else 200,), epa=SMALL_SUVS)
        out = io.StringIO()
        self.seed()
        call_command("classify_vehicles", "--dry-run", stdout=out)
        text = out.getvalue().split("Smoothed away from the newest generation's class, worth a look", 1)[1].split("\n\n", 1)[0]
        self.assertIn("(1)", text)
        self.assertIn("Acme Backwards 2005-2006: Large, smoothed from Medium; the newest generation, 2011-2015, is Medium", text)
        self.assertNotIn("Forwards", text)


class ThreeRowFloorTests(SizeClassTestCase):
    """The three-row floor runs once seat rows are final (decision 0086)."""

    def test_a_minivan_under_the_medium_line_is_medium_with_three_rows(self):
        caravan = add_model("Dodge", "Caravan", year_from=1988, year_to=1988)
        self.add_year(caravan, 1988, lengths=(190,), epa=["Minivan - 2WD"])
        # A listed minivan with no EPA size class, and a model the third-row data marks always three rows.
        voyager = add_model("Plymouth", "Voyager", year_from=1990, year_to=1990)
        add_facts(voyager, Source.VPIC, year=1990, source_vehicle_types=["Multipurpose Passenger Vehicle (MPV)"])
        add_facts(voyager, Source.CANADA, year=1990, **dimensions([185]))
        mazda5 = add_model("Mazda", "Mazda5", year_from=2008, year_to=2008)
        self.add_year(mazda5, 2008, lengths=(180,), epa=["Compact Cars"], rows=[3])
        # An optional third row does not count: it stays Small, with the size asked.
        optional = add_model("Acme", "Maybe Three", year_from=2008, year_to=2008)
        self.add_year(optional, 2008, lengths=(180,), epa=SMALL_SUVS, rows=[2, 3])
        results = self.classified()
        for model, year in ((caravan, 1988), (voyager, 1990), (mazda5, 2008)):
            with self.subTest(model=model.model):
                result = self.result(results, model, year)
                self.assertEqual((result.vehicle_class.name, result.size_variant.value, result.method), ("Medium", 3, Method.THREE_ROW_FLOOR))
        self.assertIn("three seat rows, so at least Medium; rule 120: Small gives Small", self.result(results, caravan, 1988).because)
        result = self.result(results, optional, 2008)
        self.assertEqual((result.vehicle_class.name, result.ask_size), ("Small", True))

    def test_the_price_book_check_no_longer_sees_small_with_three_rows(self):
        from vehicles.classification.sizes import produced

        caravan = add_model("Dodge", "Caravan", year_from=1988, year_to=1988)
        self.add_year(caravan, 1988, lengths=(190,), epa=["Minivan - 2WD"])
        found = produced(self.classified(), active_variants())
        self.assertNotIn(("Small", 3), found)
        self.assertEqual(check(read_matrix(), found), [])
