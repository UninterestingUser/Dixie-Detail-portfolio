"""The size-based vehicle classes (decision 0082): box volume as a fact, the
rule order and the edges of each line, the three-row floor, seat rows, the
EPA size class fallback, customers' vehicles with no year, and a dry run
that changes nothing."""

import io
from decimal import Decimal

from django.apps import apps
from django.core.management import CommandError, call_command

from customers.models import Customer
from vehicles.classification.engine import Method, active_variants, apply, catalog_model_years, classify_by_rules, classify_catalog
from vehicles.classification.rules import ModelYear
from vehicles.classification.size_preview import Preview, is_minivan
from vehicles.classification.sizes import BoxVolume, box_volumes, classify_scheme, read_scheme, scheme_classes, scheme_rules
from vehicles.models import ModelYearClassification, ModelYearSize, Vehicle
from vehicles.test_classification import SMALL_SUVS, ClassificationTestCase, Source, add_facts, add_model


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


class SizeClassTestCase(ClassificationTestCase):
    def add_year(self, vehicle_model, year, lengths=None, epa=(), rows=None, **facts):
        if epa or facts:
            add_facts(vehicle_model, year=year, epa_size_classes=list(epa), **facts)
        if rows:
            add_facts(vehicle_model, Source.SEAT_LIST, year=year, seat_rows=list(rows))
        if lengths:
            add_facts(vehicle_model, Source.CANADA, year=year, **dimensions(lengths))

    def scheme(self):
        return classify_scheme()

    def result(self, scheme, vehicle_model, year):
        return scheme.results[(vehicle_model.pk, year)][1]


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

    def test_a_model_with_no_measured_year_has_no_box_volume(self):
        model = add_model("Acme", "Unmeasured")
        self.add_year(model, 2019, epa=SMALL_SUVS)
        self.assertEqual(box_volumes(catalog_model_years([model.pk])), {})

    def test_applying_the_rules_saves_each_model_years_box_volume(self):
        model = add_model("Acme", "Roamer", year_from=2019, year_to=2020)
        self.add_year(model, 2019, lengths=(200,), epa=SMALL_SUVS)
        self.add_year(model, 2020, epa=SMALL_SUVS)
        apply(classify_catalog())
        saved = {row.year: (row.box_volume, row.inherited_from) for row in ModelYearSize.objects.filter(vehicle_model=model)}
        self.assertEqual(saved, {2019: (Decimal("500.0"), None), 2020: (Decimal("500.0"), 2019)})


class RuleTests(SizeClassTestCase):
    def setUp(self):
        data = read_scheme()
        self.variants = active_variants()
        self.classes = scheme_classes(data, self.variants)
        self.rules = scheme_rules(data, self.classes)
        self.model = add_model("Acme", "Box")

    def classify(self, volume, rows=None, epa=()):
        found = []
        if rows:
            found.append(add_facts(self.model, Source.SEAT_LIST, year=2019, seat_rows=list(rows)))
        if epa:
            found.append(add_facts(self.model, year=2019, epa_size_classes=list(epa)))
        model_year = ModelYear(self.model, 2019, found)
        model_year.box_volume, model_year.sized = BoxVolume(Decimal(volume)), True
        result = classify_by_rules(model_year, self.rules, self.variants)
        for row in found:
            row.delete()
        return result

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
        self.assertEqual(vans.vehicle_class.booking, "quote")
        self.assertIsNone(vans.size_variant)
        self.assertFalse(vans.ask_size)

    def test_the_lines_are_settings_in_the_data_file(self):
        lines = {line["name"]: line["at"] for line in read_scheme()["lines"]}
        self.assertEqual(lines, {"medium": 490, "large": 580, "full-size": 700, "full-size vans": 865})
        medium = next(rule for rule in self.rules if rule.name == "Medium")
        self.assertEqual(medium.conditions, {"box_volume": {"at_least": 490, "under": 580}})


class SchemeTests(SizeClassTestCase):
    def test_pickups_come_first_and_keep_their_split(self):
        santa_cruz = add_model("Hyundai", "Santa Cruz", year_from=2022, year_to=2022)
        self.add_year(santa_cruz, 2022, lengths=(195,), epa=["Small Sport Utility Vehicle 4WD"])
        maverick = add_model("Ford", "Maverick", year_from=2022, year_to=2022)
        self.add_year(maverick, 2022, lengths=(200,), epa=["Small Pickup Trucks 2WD"])
        f150 = add_model("Ford", "F-150", year_from=2022, year_to=2022)
        self.add_year(f150, 2022, lengths=(240,), epa=["Standard Pickup Trucks 4WD"])
        scheme = self.scheme()
        self.assertEqual(self.result(scheme, santa_cruz, 2022).vehicle_class.name, "Light Pickups")
        self.assertEqual(self.result(scheme, maverick, 2022).vehicle_class.name, "Light Pickups")
        self.assertEqual(self.result(scheme, f150, 2022).vehicle_class.name, "Fullsize Trucks")
        # Light Pickups is the old class under its new name, with its cab-style sizes.
        self.assertEqual(scheme.classes["Light Pickups"].pk, self.vehicle_class("Light Pickups & Offroad").pk)

    def test_overrides_are_not_carried_into_the_scheme(self):
        from vehicles.models import ModelOverride

        wrangler = add_model("Jeep", "Wrangler", year_from=2020, year_to=2020)
        self.add_year(wrangler, 2020, lengths=(170,), epa=["Small Sport Utility Vehicle 4WD"])
        ModelOverride.objects.create(vehicle_model=wrangler, vehicle_class=self.vehicle_class("Light Pickups & Offroad"))
        self.assertEqual(self.result(self.scheme(), wrangler, 2020).vehicle_class.name, "Small")

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
        scheme = self.scheme()
        self.assertEqual(scheme.fallback_table, {"Midsize Cars": "Medium"})
        self.assertEqual(dict(scheme.fallback_counts["Midsize Cars"]), {"Medium": 2, "Small": 1})
        result = self.result(scheme, unmeasured, 2019)
        self.assertEqual((result.vehicle_class.name, result.method), ("Medium", Method.EPA_FALLBACK))
        self.assertIn("most measured Midsize Cars model years are Medium", result.because)
        self.assertIsNone(self.result(scheme, lonely, 2019).vehicle_class)
        bare_result = self.result(scheme, bare, 2019)
        self.assertIsNone(bare_result.vehicle_class)
        self.assertIn("no EPA size class", bare_result.because)


class CustomerVehicleTests(SizeClassTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.customer = Customer.objects.create(first_name="Pat", last_name="Example", mobile="4235550101")

    def setUp(self):
        self.steady = add_model("Acme", "Steady", year_from=2018, year_to=2019)
        self.add_year(self.steady, 2018, lengths=(200,))
        self.add_year(self.steady, 2019, lengths=(201,))
        self.grower = add_model("Acme", "Grower", year_from=2018, year_to=2019)
        self.add_year(self.grower, 2018, lengths=(180,))
        self.add_year(self.grower, 2019, lengths=(240,))

    def vehicle(self, vehicle_model=None, year=None, class_name=None, model="Steady"):
        return Vehicle.objects.create(
            customer=self.customer, vehicle_model=vehicle_model, year=year, make="Acme", model=model,
            vehicle_class=self.vehicle_class(class_name) if class_name else None,
        )

    def new_for(self, vehicle):
        return Preview(self.scheme(), io.StringIO()).new_for(vehicle)

    def test_a_linked_vehicle_takes_its_model_years_class(self):
        self.assertEqual(self.new_for(self.vehicle(self.grower, 2019))[0], "Large (two rows)")

    def test_a_vehicle_with_no_year_gets_a_class_only_when_every_model_year_has_the_same(self):
        self.assertEqual(self.new_for(self.vehicle(self.steady))[0], "Medium")
        new, reason = self.new_for(self.vehicle(self.grower, model="Grower"))
        self.assertEqual(new, "year needed")
        self.assertIn("Large, Small", reason)

    def test_an_unlinked_vehicle_gets_a_proposed_class_from_its_recorded_class(self):
        for model, class_name, expected in (
            ("Civic", "Coupes & Sedans", "Small"),
            ("RAV4", "Crossovers & Wagons", "Medium"),
            ("4Runner", "Midsize SUVs", "Large"),
            ("Tahoe", "Fullsize SUVs & Minivans", "Full-size"),
            ("Sienna XLE", "Fullsize SUVs & Minivans", "Large"),
            ("Tacoma", "Light Pickups & Offroad", "Light Pickups"),
            ("F-150", "Fullsize Trucks", "Fullsize Trucks"),
        ):
            with self.subTest(model=model):
                new, reason = self.new_for(self.vehicle(class_name=class_name, model=model))
                self.assertEqual(new, expected)
                self.assertIn("for review", reason)
        self.assertEqual(self.new_for(self.vehicle(model="Mystery"))[0], "unclassified")

    def test_minivans_are_recognized_by_whole_words(self):
        self.assertTrue(is_minivan("Grand Caravan SXT", ["Grand Caravan"]))
        self.assertTrue(is_minivan("Town & Country", ["Town & Country"]))
        self.assertFalse(is_minivan("Questor", ["Quest"]))


class DryRunTests(CustomerVehicleTests):
    def run_dry(self, *extra):
        out = io.StringIO()
        call_command("classify_vehicles", "--scheme", "size", "--dry-run", *extra, stdout=out)
        return out.getvalue()

    def test_the_dry_run_changes_no_rows(self):
        self.vehicle(self.grower, 2019, "Crossovers & Wagons")
        apply(classify_catalog())
        counts = lambda: {model._meta.label: model._default_manager.count() for model in apps.get_models()}  # noqa: E731
        stored = list(ModelYearClassification.objects.values_list("vehicle_model_id", "year", "vehicle_class_id", "method"))
        before = counts()
        text = self.run_dry()
        self.assertEqual(counts(), before)
        self.assertEqual(list(ModelYearClassification.objects.values_list("vehicle_model_id", "year", "vehicle_class_id", "method")), stored)
        for heading in (
            "Model years by new class", "EPA size class fallback", "Near a line", "Models whose class changes",
            "Model overrides, not carried forward", "Approvals, not carried forward", "Customer vehicles",
            "that the new rules do not treat as pickups", "Pickup ladder", "Pickup check",
        ):
            self.assertIn(heading, text)
        self.assertIn("Acme Grower: 2018 Small; 2019 Large", text)
        for private in ("Pat", "Example", "4235550101"):
            self.assertNotIn(private, text)

    def test_the_size_scheme_cannot_be_applied_yet(self):
        with self.assertRaises(CommandError):
            call_command("classify_vehicles", "--scheme", "size", stdout=io.StringIO())
