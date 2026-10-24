"""The fixes from the owner's first classify_vehicles dry run: nameplates and
aliases (data/vehicle-names.yaml), the full-size SUV overrides, the
three-row rule, majority voting, the narrowed rules, the report and the
third-row list. Every example the owner named has a test here."""

import dataclasses
import importlib
import io
import shutil
import tempfile
from fractions import Fraction
from pathlib import Path

import yaml
from django.apps import apps
from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from customers.models import Customer
from vehicles.classification.engine import classify_catalog, majority_share
from vehicles.classification.seed import SeedReport, sync_launch_set, sync_seat_list
from vehicles.models import ClassificationRule, ModelOverride, Vehicle, VehicleClass, VehicleModel, VehicleModelYear
from vehicles.test_classification import SMALL_SUVS, ClassificationTestCase, add_facts, add_model
from vehicles.test_vehicle_data import CONFIG, no_network, write_epa_zip
from vehicles.vehicle_data.catalog import merge_duplicates
from vehicles.vehicle_data.fetch import Fetcher
from vehicles.vehicle_data.names import Names, load_names
from vehicles.vehicle_data.run import run

Source = VehicleModelYear.Source
NHTSA = VehicleModel.Source.NHTSA
OWNER = VehicleModel.Source.OWNER
STANDARD_SUVS = ["Standard Sport Utility Vehicle 2WD", "Standard Sport Utility Vehicle 4WD"]
HEADER = "id,year,make,model,baseModel,VClass,drive,pv2,lv2,pv4,lv4,hpv,hlv,trany,displ"


def epa_csv(rows):
    """rows: (year, make, EPA model, base model, VClass)."""
    lines = [HEADER]
    for number, (year, make, model, base, size_class) in enumerate(rows, start=50000):
        lines.append(f"{number},{year},{make},{model},{base},{size_class},4-Wheel Drive,0,0,0,0,0,0,Automatic (S8),2.0")
    return "\n".join(lines) + "\n"


def import_epa(rows, names=None, years=(2010, 2026)):
    cache = Path(tempfile.mkdtemp())
    try:
        write_epa_zip(cache, epa_csv(rows))
        config = dataclasses.replace(
            CONFIG, year_from=years[0], year_to=years[1], names=load_names() if names is None else names
        )
        fetcher = Fetcher(cache, opener=no_network, sleep=lambda seconds: None)
        return run(["epa"], dry_run=False, fetcher=fetcher, config=config)[0]
    finally:
        shutil.rmtree(cache)


def models(make):
    return sorted(VehicleModel.objects.filter(make=make).values_list("model", flat=True))


class NameplateTests(SimpleTestCase):
    """Item 1: an EPA base model is split into the nameplates customers know."""

    def test_each_named_base_model_splits(self):
        names = load_names()
        for make, base, epa_model, expected in (
            ("Hyundai", "Santa Fe", "Santa Fe Sport AWD", "Santa Fe Sport"),
            ("Hyundai", "Santa Fe", "Santa Fe XL AWD", "Santa Fe XL"),
            ("Hyundai", "Santa Fe", "Santa Fe Hybrid AWD", "Santa Fe"),
            ("Jeep", "Grand Cherokee", "Grand Cherokee L 4WD", "Grand Cherokee L"),
            ("Jeep", "Grand Cherokee", "Grand Cherokee 4WD", "Grand Cherokee"),
            ("Volkswagen", "Atlas", "Atlas Cross Sport 4motion", "Atlas Cross Sport"),
            ("Volkswagen", "Atlas", "Atlas SEL 4motion", "Atlas"),
            ("Lexus", "RX", "RX 350 L AWD", "RX 350L"),
            ("Lexus", "RX", "RX 450h L AWD", "RX 450hL"),
            ("Lexus", "RX", "RX 350 AWD", "RX"),
            ("Mitsubishi", "Outlander", "Outlander Sport 4WD", "Outlander Sport"),
            ("Mitsubishi", "Outlander", "Outlander PHEV", "Outlander PHEV"),
            ("Buick", "Encore", "Encore GX AWD", "Encore GX"),
            ("Buick", "Encore", "Encore AWD", "Encore"),
            ("Land Rover", "Range Rover", "New Range Rover Sport P360 MHEV", "Range Rover Sport"),
            ("Land Rover", "Range Rover", "Range Rover Velar P300", "Range Rover Velar"),
            ("Land Rover", "Range Rover", "Range Rover Evoque MHEV", "Range Rover Evoque"),
            ("Land Rover", "Range Rover", "Range Rover LWB MHEV", "Range Rover"),
            ("Land Rover", "Defender", "Defender 90 MHEV", "Defender 90"),
            ("Land Rover", "Defender", "Defender 110", "Defender 110"),
            ("Land Rover", "Defender", "Defender 130 Outbound", "Defender 130"),
            ("GMC", "Yukon", "Yukon C1500 XL 2WD", "Yukon XL"),
            ("Cadillac", "Escalade", "Escalade ESV AWD", "Escalade ESV"),
            ("Lincoln", "Navigator", "Navigator L 4WD", "Navigator L"),
            ("Ford", "Expedition", "Expedition MAX 4WD", "Expedition MAX"),
            ("Mercedes-Benz", "EQE", "EQE 350 4matic (SUV)", "EQE SUV"),
            ("Mercedes-Benz", "EQE", "EQE 350 4matic", "EQE"),
        ):
            with self.subTest(epa_model=epa_model):
                self.assertEqual(names.nameplate(make, base, epa_model), expected)


class AliasTests(SimpleTestCase):
    """Item 2: one vehicle, one name, shown the way customers expect."""

    def test_each_named_duplicate_has_one_name(self):
        names = load_names()
        for make, spelling, expected in (
            ("Mercedes-Benz", "EQB-Class", "EQB"),
            ("Mercedes-Benz", "EQE-Class SUV", "EQE SUV"),
            ("Mercedes-Benz", "EQS-Class SUV", "EQS SUV"),
            ("Mercedes-Benz", "ML-Class", "ML"),
            ("Mercedes-Benz", "M-Class", "ML"),
            ("Mercedes-Benz", "GLE-Class", "GLE"),
            ("Jeep", "Wrangler/TJ", "Wrangler"),
            ("Ford", "F150", "F-150"),
            ("Ford", "F-150 Lightning", "F-150"),
            ("Ford", "F250", "F-250"),
            ("Mazda", "5", "Mazda5"),
            ("Chevrolet", "Captiva", "Captiva Sport"),
        ):
            with self.subTest(spelling=spelling):
                self.assertEqual(names.model(make, spelling), expected)
        self.assertEqual(names.model("Toyota", "RAV4"), "RAV4")
        self.assertEqual(names.make_key("RAM TRUCKS"), names.make_key("Ram"))


class SplitImportTests(TestCase):
    def setUp(self):
        call_command("load_pricebook", stdout=io.StringIO())

    def test_the_import_splits_base_models_and_lists_them(self):
        rows = [
            (2017, "Hyundai", "Santa Fe AWD", "Santa Fe", "Small Sport Utility Vehicle 4WD"),
            (2017, "Hyundai", "Santa Fe Sport AWD", "Santa Fe", "Small Sport Utility Vehicle 4WD"),
            (2018, "Hyundai", "Santa Fe Sport AWD", "Santa Fe", "Small Sport Utility Vehicle 4WD"),
        ]
        import_epa(rows, names=Names(), years=(2017, 2018))
        santa_fe = VehicleModel.objects.get(make="Hyundai", model="Santa Fe")
        override = ModelOverride.objects.create(vehicle_model=santa_fe, vehicle_class=VehicleClass.objects.get(name="Midsize SUVs"))
        self.assertEqual(santa_fe.model_years.count(), 2)

        report = import_epa(rows, years=(2017, 2018))
        self.assertEqual(models("Hyundai"), ["Santa Fe", "Santa Fe Sport"])
        self.assertIn("Hyundai Santa Fe: Santa Fe Sport (2017-2018) split out (data/vehicle-names.yaml)", report.split)
        santa_fe.refresh_from_db()
        # 2018 had only the Sport, so its row moved; the override stays with the Santa Fe.
        self.assertEqual(list(santa_fe.model_years.values_list("year", flat=True)), [2017])
        self.assertEqual((santa_fe.year_from, santa_fe.year_to), (2017, 2017))
        self.assertEqual(report.counts["model years moved to another model"], 1)
        override.refresh_from_db()
        self.assertEqual(override.vehicle_model, santa_fe)
        sport = VehicleModel.objects.get(make="Hyundai", model="Santa Fe Sport")
        self.assertEqual(sorted(sport.model_years.values_list("year", flat=True)), [2017, 2018])

    def test_an_owner_model_spelled_another_way_still_gets_its_facts(self):
        owner = add_model("Mercedes-Benz", "GLE-Class", source=OWNER, year_from=2016, year_to=2019)
        import_epa([(2018, "Mercedes-Benz", "GLE350 4matic", "GLE-Class", "Standard Sport Utility Vehicle 4WD")])
        self.assertEqual(models("Mercedes-Benz"), ["GLE-Class"])
        self.assertTrue(owner.model_years.filter(year=2018, source=Source.EPA).exists())


class MergeTests(TestCase):
    def setUp(self):
        self.names = load_names()
        call_command("load_pricebook", stdout=io.StringIO())

    def test_duplicates_merge_into_the_name_customers_know(self):
        epa = add_model("Mercedes-Benz", "EQB", year_from=2022, year_to=2023)
        add_facts(epa, year=2022, epa_size_classes=SMALL_SUVS)
        vpic = add_model("Mercedes-Benz", "EQB-Class", source=NHTSA, year_from=2024, year_to=2024)
        add_facts(vpic, Source.VPIC, year=2024, source_vehicle_types=["Multipurpose Passenger Vehicle (MPV)"])
        override = ModelOverride.objects.create(vehicle_model=vpic, vehicle_class=VehicleClass.objects.get(name="Midsize SUVs"))
        vehicle = Vehicle.objects.create(customer=Customer.objects.create(first_name="Pat"), vehicle_model=vpic, year=2024)

        f150 = add_model("Ford", "F150", year_from=2022, year_to=2022)
        add_facts(f150, year=2022, epa_size_classes=["Standard Pickup Trucks 4WD"], source_ids=[1], distribution={"epa_size_classes": {"Standard Pickup Trucks 4WD": 1}})
        lightning = add_model("Ford", "F-150 Lightning", year_from=2022, year_to=2022)
        add_facts(lightning, year=2022, epa_size_classes=["Standard Pickup Trucks 2WD"], source_ids=[2], distribution={"epa_size_classes": {"Standard Pickup Trucks 2WD": 1}})
        add_model("Mercedes-Benz", "GLE-Class")

        lines = merge_duplicates(self.names, "test")
        self.assertEqual(models("Mercedes-Benz"), ["EQB", "GLE"])
        self.assertEqual(models("Ford"), ["F-150"])
        eqb = VehicleModel.objects.get(model="EQB")
        self.assertEqual(sorted(eqb.model_years.values_list("year", flat=True)), [2022, 2024])
        self.assertEqual((eqb.year_from, eqb.year_to), (2022, 2024))
        override.refresh_from_db()
        vehicle.refresh_from_db()
        self.assertEqual((override.vehicle_model, vehicle.vehicle_model), (eqb, eqb))
        row = VehicleModel.objects.get(model="F-150").model_years.get()
        self.assertEqual(row.epa_size_classes, ["Standard Pickup Trucks 2WD", "Standard Pickup Trucks 4WD"])
        self.assertEqual(row.source_ids, [1, 2])
        self.assertEqual(row.distribution["epa_size_classes"], {"Standard Pickup Trucks 2WD": 1, "Standard Pickup Trucks 4WD": 1})
        self.assertTrue(any(line.startswith("merged Mercedes-Benz EQB-Class (2024-2024, NHTSA) into Mercedes-Benz EQB") for line in lines))
        self.assertTrue(any(line.startswith("merged Ford F-150 Lightning") for line in lines))
        self.assertTrue(any("to GLE" in line and line.startswith("renamed Mercedes-Benz GLE-Class") for line in lines))
        self.assertTrue(any("to F-150" in line for line in lines))
        self.assertEqual(merge_duplicates(self.names, "test"), [])

    def test_the_owners_model_is_kept_with_its_name(self):
        owner = add_model("Jeep", "Wrangler/TJ", source=OWNER, year_from=2003, year_to=2006)
        epa = add_model("Jeep", "Wrangler", year_from=2003, year_to=2020)
        add_facts(epa, year=2005)
        merge_duplicates(self.names, "test")
        self.assertEqual(models("Jeep"), ["Wrangler/TJ"])
        self.assertTrue(owner.model_years.filter(year=2005).exists())

    def test_two_owner_records_for_one_year_are_left_for_the_owner(self):
        first = add_model("Mercedes-Benz", "ML", year_from=2012, year_to=2012)
        add_facts(first, Source.OWNER, year=2012, curb_weight_min=4800, curb_weight_max=4800)
        second = add_model("Mercedes-Benz", "ML-Class", year_from=2012, year_to=2012)
        add_facts(second, Source.OWNER, year=2012, curb_weight_min=4900, curb_weight_max=4900)
        lines = merge_duplicates(self.names, "test")
        self.assertEqual(models("Mercedes-Benz"), ["ML", "ML-Class"])
        self.assertIn("both have the owner's own figures for 2012", lines[0])


class LaunchSetTests(ClassificationTestCase):
    """Item 3 and the way launch entries follow the data file."""

    def sync(self, data_dir=None):
        report = SeedReport()
        sync_launch_set(report, data_dir)
        return report

    def test_full_size_suvs_are_priced_with_the_suburban(self):
        named = [
            ("Chevrolet", "Tahoe"), ("GMC", "Yukon"), ("GMC", "Yukon XL"), ("Cadillac", "Escalade"),
            ("Cadillac", "Escalade ESV"), ("Lincoln", "Navigator"), ("Lincoln", "Navigator L"), ("Nissan", "Armada"),
            ("Infiniti", "QX56"), ("Infiniti", "QX80"), ("Ford", "Expedition MAX"),
            ("Ford", "Expedition EL"), ("Chevrolet", "Suburban HD"), ("Chevrolet", "Suburban"),
        ]
        for make, name in named:
            add_facts(add_model(make, name), epa_size_classes=STANDARD_SUVS)
        # The Wagoneer and Grand Wagoneer from 2022 only: the 1989 to 1990
        # Wagoneer is the old compact one, and the 1984 to 1991 Grand Wagoneer
        # a different vehicle too.
        grand = add_model("Jeep", "Grand Wagoneer", year_from=1990, year_to=2023)
        wagoneer = add_model("Jeep", "Wagoneer", year_from=1990, year_to=2023)
        for vehicle_model in (grand, wagoneer):
            for year in (1990, 2023):
                add_facts(vehicle_model, year=year, epa_size_classes=["Special Purpose Vehicles"] if year == 1990 else STANDARD_SUVS)
        self.sync()
        results = classify_catalog()
        for make, name in named:
            with self.subTest(model=name):
                result = results[(VehicleModel.objects.get(make=make, model=name).pk, 2019)][1]
                self.assertEqual((result.vehicle_class.name, result.method), ("Fullsize SUVs & Minivans", "override"))
        for vehicle_model in (grand, wagoneer):
            with self.subTest(model=vehicle_model.model):
                self.assertEqual(vehicle_model.overrides.get().year_from, 2022)
                self.assertEqual(results[(vehicle_model.pk, 2023)][1].vehicle_class.name, "Fullsize SUVs & Minivans")
                self.assertNotEqual(results[(vehicle_model.pk, 1990)][1].method, "override")

    def test_an_unedited_launch_rule_follows_the_file_and_an_edited_one_is_kept(self):
        self.sync()
        data = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, data)
        classes = yaml.safe_load((settings.DATA_DIR / "vehicle-classes.yaml").read_text())
        for entry in classes["launch_rules"]:
            if entry["name"] in ("Small SUVs over 4,500 lb", "EPA car classes"):
                entry["note"] = "Changed in the file."
        classes["launch_rules"].append({"name": "A new launch rule", "class": "Midsize SUVs", "conditions": {"make": ["Test"]}})
        (data / "vehicle-classes.yaml").write_text(yaml.safe_dump(classes))
        edited = ClassificationRule.objects.get(name="EPA car classes")
        edited.note = "The owner's note."
        edited.save()
        report = self.sync(data)
        self.assertEqual(ClassificationRule.objects.get(name="Small SUVs over 4,500 lb").note, "Changed in the file.")
        self.assertEqual(ClassificationRule.objects.get(name="EPA car classes").note, "The owner's note.")
        self.assertTrue(ClassificationRule.objects.filter(name="A new launch rule").exists())
        self.assertIn("kept your edited rule 130 (EPA car classes); the launch set has a different version", report.launch_set)
        self.assertIn("updated launch rule 80 (Small SUVs over 4,500 lb)", report.launch_set)

    def test_the_first_launch_set_is_brought_in_step(self):
        """Rules seeded by the first version, never edited, follow the new file."""
        old = ClassificationRule.objects.create(
            position=70, name="Older SUVs over 4,500 lb", vehicle_class=self.vehicle_class("Midsize SUVs"),
            conditions={"epa_size_class": ["Special Purpose Vehicles"], "curb_weight": {"over": 4500}},
        )
        mine = ClassificationRule.objects.create(position=5, name="My own rule", vehicle_class=self.vehicle_class("Midsize SUVs"), conditions={"make": ["Test"]})
        migration = importlib.import_module("vehicles.migrations.0005_names_and_launch_set")
        migration.mark_first_launch_set(apps, None)
        self.sync()
        old.refresh_from_db()
        self.assertEqual(old.conditions["year"], {"to": 2012})
        self.assertEqual(old.position, 90)
        mine.refresh_from_db()
        self.assertIsNone(mine.seeded_from)
        self.assertEqual(ClassificationRule.objects.filter(name="Older SUVs over 4,500 lb").count(), 1)


class ThreeRowAndMajorityTests(ClassificationTestCase):
    """Items 4, 5 and 6 with the launch rules and the third-row list from data/."""

    def classify(self):
        report = SeedReport()
        sync_launch_set(report)
        sync_seat_list(report)
        return classify_catalog()

    def epa(self, vehicle_model, year, counts):
        add_facts(vehicle_model, year=year, epa_size_classes=sorted(counts), distribution={"epa_size_classes": counts})

    def test_three_row_suvs_keep_one_price_across_the_years(self):
        cases = {
            ("Hyundai", "Palisade"): (2020, 2024), ("Kia", "Telluride"): (2020, 2024), ("Mazda", "CX-9"): (2016, 2022),
            ("Mazda", "CX-90"): (2024, 2025), ("Toyota", "Highlander"): (2015, 2021), ("Honda", "Pilot"): (2012, 2020),
            ("Volkswagen", "Atlas"): (2018, 2022), ("Acura", "MDX"): (2011, 2020),
        }
        for (make, name), (first, second) in cases.items():
            vehicle_model = add_model(make, name, year_from=first, year_to=second)
            # The EPA calls one year small and the other standard, or mixes them in a year.
            self.epa(vehicle_model, first, {"Small Sport Utility Vehicle 2WD": 2, "Standard Sport Utility Vehicle 4WD": 3})
            self.epa(vehicle_model, second, {"Standard Sport Utility Vehicle 4WD": 4})
        sienna = add_model("Toyota", "Sienna")
        self.epa(sienna, 2019, {"Minivan - 2WD": 3})
        results = self.classify()
        for (make, name), years in cases.items():
            vehicle_model = VehicleModel.objects.get(make=make, model=name)
            for year in years:
                with self.subTest(model=name, year=year):
                    result = results[(vehicle_model.pk, year)][1]
                    self.assertEqual((result.vehicle_class.name, result.size_variant.value), ("Midsize SUVs", 3))
                    self.assertEqual(result.rule.name, "Three-row SUVs")
        self.assertEqual(results[(sienna.pk, 2019)][1].vehicle_class.name, "Fullsize SUVs & Minivans")

    def test_an_override_beats_the_three_row_rule(self):
        tahoe = add_model("Chevrolet", "Tahoe")
        self.epa(tahoe, 2019, {"Standard Sport Utility Vehicle 4WD": 4})
        add_facts(tahoe, Source.OWNER, seat_rows=[3])
        self.assertEqual(self.classify()[(tahoe.pk, 2019)][1].vehicle_class.name, "Fullsize SUVs & Minivans")

    def test_the_majority_of_rows_decides_and_the_split_is_shown_otherwise(self):
        self.assertEqual(majority_share(), Fraction(2, 3))
        silverado = add_model("Chevrolet", "Silverado", year_from=2024, year_to=2025)
        self.epa(silverado, 2024, {"Standard Pickup Trucks 4WD": 8, "Special Purpose Vehicle 4WD": 2})
        add_facts(silverado, Source.CANADA, year=2024, curb_weight_min=4600, curb_weight_max=5800)
        sierra = add_model("GMC", "Sierra")
        self.epa(sierra, 2019, {"Standard Pickup Trucks 2WD": 5, "Standard Pickup Trucks 4WD": 5, "Special Purpose Vehicle 2WD": 1})
        heavy = add_model("Test", "Heavy Crossover")
        self.epa(heavy, 2019, {"Small Sport Utility Vehicle 4WD": 4})
        add_facts(heavy, Source.CANADA, curb_weight_min=4300, curb_weight_max=4800, distribution={"curb_weight": [4300, 4600, 4700, 4800]})
        even = add_model("Test", "Even")
        self.epa(even, 2019, {"Compact Cars": 3, "Small Station Wagons": 3})
        results = self.classify()
        self.assertEqual(results[(silverado.pk, 2024)][1].vehicle_class.name, "Fullsize Trucks")
        self.assertEqual(results[(sierra.pk, 2019)][1].vehicle_class.name, "Fullsize Trucks")
        self.assertEqual(results[(heavy.pk, 2019)][1].rule.name, "Small SUVs over 4,500 lb")
        result = results[(even.pk, 2019)][1]
        self.assertTrue(result.in_review)
        self.assertIn("its trims split on the EPA size class condition: 3 of 6 rows (50%) meet it", result.reasons[0])
        # With every row needing to agree, the Silverado would wait for the owner.
        self.assertTrue(classify_catalog(share=Fraction(1))[(silverado.pk, 2024)][1].in_review)

    def test_the_heavy_pickup_rule_needs_a_heavy_duty_series_or_gvwr(self):
        def vpic_truck(make, name, **fields):
            vehicle_model = add_model(make, name, source=NHTSA)
            add_facts(vehicle_model, Source.VPIC, source_vehicle_types=["Truck"])
            for source, values in fields.items():
                add_facts(vehicle_model, source, **values)
            return vehicle_model

        heavy = [vpic_truck("Ford", "F-250"), vpic_truck("Ford", "F-350 Super Duty"), vpic_truck("Chevrolet", "Silverado HD"),
                 vpic_truck("Ram", "2500"), vpic_truck("GMC", "Sierra 3500HD"),
                 vpic_truck("Test", "Big Hauler", **{Source.OWNER: {"gvwr_min": 9900, "gvwr_max": 9900}})]
        minivans = [vpic_truck("Chevrolet", "Astro"), vpic_truck("Dodge", "Caravan"), vpic_truck("Chevrolet", "Lumina APV")]
        light = [vpic_truck("Dodge", "Dakota"), vpic_truck("Ford", "Explorer Sport Trac")]
        results = self.classify()
        for vehicle_model in heavy:
            with self.subTest(model=vehicle_model.model):
                self.assertEqual(results[(vehicle_model.pk, 2019)][1].vehicle_class.name, "Fullsize Trucks")
        for vehicle_model in minivans:
            with self.subTest(model=vehicle_model.model):
                self.assertEqual(results[(vehicle_model.pk, 2019)][1].vehicle_class.name, "Fullsize SUVs & Minivans")
        for vehicle_model in light:
            with self.subTest(model=vehicle_model.model):
                self.assertTrue(results[(vehicle_model.pk, 2019)][1].in_review)

    def test_the_older_suv_rules_keep_to_suv_classes_and_their_years(self):
        silverado = add_model("Chevrolet", "Silverado", year_from=2024, year_to=2026)
        for year in (2024, 2026):
            self.epa(silverado, year, {"Special Purpose Vehicle 4WD": 3, "Standard Pickup Trucks 4WD": 3})
            add_facts(silverado, Source.CANADA, year=year, curb_weight_min=4700, curb_weight_max=5200)
        explorer = add_model("Ford", "Explorer", year_from=1995, year_to=2005)
        self.epa(explorer, 1995, {"Special Purpose Vehicles": 4})
        self.epa(explorer, 2005, {"Sport Utility Vehicle - 4WD": 4})
        for year in (1995, 2005):
            add_facts(explorer, Source.CANADA, year=year, curb_weight_min=4600, curb_weight_max=4700)
        results = self.classify()
        for year in (2024, 2026):
            result = results[(silverado.pk, year)][1]
            self.assertNotIn("SUVs", result.because)
        self.assertEqual(results[(explorer.pk, 1995)][1].rule.name, "Special purpose SUVs over 4,500 lb")
        self.assertEqual(results[(explorer.pk, 2005)][1].rule.name, "Older SUVs over 4,500 lb")


class ReportTests(ClassificationTestCase):
    def test_counts_per_class_and_size_and_models_in_different_classes(self):
        rav4 = add_model("Toyota", "RAV4", year_from=2018, year_to=2019)
        add_facts(rav4, year=2018, epa_size_classes=SMALL_SUVS)
        add_facts(rav4, year=2019, epa_size_classes=STANDARD_SUVS)
        out = io.StringIO()
        call_command("classify_vehicles", "--dry-run", stdout=out)
        output = out.getvalue()
        self.assertIn("Model years by class and size", output)
        self.assertIn("  Crossovers & Wagons: 1\n    two rows: 1\n", output)
        self.assertIn("Models whose years are in different classes, for the owner to look at (1)", output)
        self.assertIn("  Toyota RAV4: 2018: Crossovers & Wagons; 2019: Midsize SUVs", output)


class ThirdRowMatchingTests(TestCase):
    """Item 8: the 28 rows the first dry run could not match now match the
    catalog as the import names it from the EPA's own spellings."""

    def test_the_rows_that_did_not_match_now_match(self):
        suv = "Small Sport Utility Vehicle 4WD"
        rows = [
            (2021, "Buick", "Encore GX AWD", "Encore", suv),
            (2013, "Chevrolet", "Captiva FWD", "Captiva", suv),
            (2016, "Hyundai", "Santa Fe Sport AWD", "Santa Fe", suv),
            (2019, "Hyundai", "Santa Fe XL AWD", "Santa Fe", suv),
            (2022, "Jeep", "Grand Cherokee L 4WD", "Grand Cherokee", suv),
            (2021, "Land Rover", "Defender 90 MHEV", "Defender", suv),
            (2021, "Land Rover", "Defender 110 MHEV", "Defender", suv),
            (2024, "Land Rover", "Defender 130 P300 MHEV", "Defender", suv),
            (2019, "Land Rover", "Range Rover Evoque", "Range Rover", suv),
            (2020, "Land Rover", "Range Rover Sport", "Range Rover", suv),
            (2023, "Land Rover", "New Range Rover Sport P360 MHEV", "Range Rover", suv),
            (2019, "Land Rover", "Range Rover Velar P300", "Range Rover", suv),
            (2019, "Lexus", "RX 350 L AWD", "RX", suv),
            (2019, "Lexus", "RX 450h L AWD", "RX", suv),
            (2012, "Mazda", "5", "5", "Small Station Wagons"),
            (2024, "Mercedes-Benz", "EQE 350 4matic (SUV)", "EQE", suv),
            (2024, "Mercedes-Benz", "EQS 450 4matic (SUV)", "EQS", suv),
            (2012, "Mercedes-Benz", "GL450 4matic", "GL-Class", suv),
            (2016, "Mercedes-Benz", "GLA250 4matic", "GLA-Class", suv),
            (2021, "Mercedes-Benz", "GLB250 4matic", "GLB-Class", suv),
            (2017, "Mercedes-Benz", "GLC300 4matic", "GLC-Class", suv),
            (2018, "Mercedes-Benz", "GLE350 4matic", "GLE-Class", suv),
            (2021, "Mercedes-Benz", "GLE350 4matic", "GLE-Class", suv),
            (2012, "Mercedes-Benz", "GLK350 4matic", "GLK-Class", suv),
            (2012, "Mercedes-Benz", "ML350 4matic", "ML-Class", suv),
            (2019, "Mitsubishi", "Outlander PHEV", "Outlander", suv),
            (2023, "Mitsubishi", "Outlander PHEV", "Outlander", suv),
            (2015, "Mitsubishi", "Outlander Sport 4WD", "Outlander", suv),
            (2021, "Volkswagen", "Atlas Cross Sport 4motion", "Atlas", suv),
        ]
        import_epa(rows)
        report = SeedReport()
        sync_seat_list(report)
        first_unmatched = [
            "Buick Encore GX", "Chevrolet Captiva Sport", "Hyundai Santa Fe Sport", "Hyundai Santa Fe XL",
            "Jeep Grand Cherokee L", "Land Rover Defender 90", "Land Rover Defender 110", "Land Rover Defender 130",
            "Land Rover Range Rover Evoque", "Land Rover Range Rover Sport", "Land Rover Range Rover Velar",
            "Lexus RX 350L / RX 450hL", "Mazda Mazda5", "Mercedes-Benz EQE SUV", "Mercedes-Benz EQS SUV",
            "Mercedes-Benz GL / GLS", "Mercedes-Benz GLA", "Mercedes-Benz GLB", "Mercedes-Benz GLC",
            "Mercedes-Benz GLE", "Mercedes-Benz GLK", "Mercedes-Benz ML", "Mitsubishi Outlander PHEV",
            "Mitsubishi Outlander Sport", "Volkswagen Atlas Cross Sport",
        ]
        still = [line for line in report.unmatched_seat_rows if any(line.startswith(name + " 2") for name in first_unmatched)]
        self.assertEqual(still, [])
        self.assertEqual(
            VehicleModelYear.objects.get(vehicle_model__model="RX 350L", year=2019, source=Source.SEAT_LIST).seat_rows, [3]
        )
        self.assertEqual(
            VehicleModelYear.objects.get(vehicle_model__model="Santa Fe Sport", year=2016, source=Source.SEAT_LIST).seat_rows, [2]
        )
