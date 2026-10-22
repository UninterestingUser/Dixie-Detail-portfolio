"""Vehicle classification: rule order, overrides, size variants, the
preview, the review queue, the lookup and classify_vehicles. The catalog is
built record by record, or loaded from the import's fixture files; nothing
touches the network."""

import io
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

import yaml
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase, override_settings

from customers.models import Customer
from pricebook.models import Price, PricebookVersion, Service
from pricebook.pricing import NotPriced, price_job
from vehicles.classification.engine import apply, classify_catalog, preview
from vehicles.classification.lookup import How, classify
from vehicles.classification.rules import condition_errors
from vehicles.classification.seed import SeedReport, read_data, sync_seat_list
from vehicles.models import (
    ClassificationRule,
    ModelOverride,
    ModelYearClassification,
    Vehicle,
    VehicleClass,
    VehicleModel,
    VehicleModelYear,
)
from vehicles.test_vehicle_data import CachedFixtures
from vehicles.vehicle_data.canada import cab_style, words

Source = VehicleModelYear.Source
VEHICLE = VehicleModel.VehicleType.VEHICLE
MOTORCYCLE = VehicleModel.VehicleType.MOTORCYCLE
SMALL_SUVS = ["Small Sport Utility Vehicle 2WD", "Small Sport Utility Vehicle 4WD"]


def add_model(make, name, vehicle_type=VEHICLE, source=VehicleModel.Source.EPA, year_from=2019, year_to=2019):
    return VehicleModel.objects.create(
        make=make, model=name, vehicle_type=vehicle_type, source=source, year_from=year_from, year_to=year_to
    )


def add_facts(vehicle_model, source=Source.EPA, year=2019, **fields):
    return VehicleModelYear.objects.create(vehicle_model=vehicle_model, year=year, source=source, **fields)


def classified(vehicle_model, year=2019):
    return ModelYearClassification.objects.get(vehicle_model=vehicle_model, year=year)


class ClassificationTestCase(TestCase):
    """The seven vehicle classes from data/, via the pricebook load."""

    @classmethod
    def setUpTestData(cls):
        call_command("load_pricebook", stdout=io.StringIO())

    def vehicle_class(self, name):
        return VehicleClass.objects.get(name=name)

    def size(self, class_name, value):
        return self.vehicle_class(class_name).size_variants.get(value=value)

    def rule(self, position, conditions, class_name, name="", active=True):
        return ClassificationRule.objects.create(
            position=position,
            name=name or f"rule {position}",
            conditions=conditions,
            vehicle_class=self.vehicle_class(class_name),
            active=active,
        )

    def result(self, vehicle_model, year=2019, **inputs):
        return classify_catalog(**inputs)[(vehicle_model.pk, year)][1]


class RuleOrderTests(ClassificationTestCase):
    def setUp(self):
        self.rav4 = add_model("Toyota", "RAV4")
        add_facts(self.rav4, epa_size_classes=SMALL_SUVS)
        add_facts(self.rav4, Source.SEAT_LIST, seat_rows=[2])

    def test_the_first_rule_that_holds_wins(self):
        heavy = self.rule(10, {"epa_size_class": SMALL_SUVS, "curb_weight": {"over": 4500}}, "Midsize SUVs")
        small = self.rule(20, {"epa_size_class": SMALL_SUVS}, "Crossovers & Wagons")
        self.rule(30, {"make": ["Toyota"]}, "Fullsize Trucks")
        # No curb weight is known, so the first rule fails and the second wins.
        self.assertEqual(self.result(self.rav4).rule, small)
        add_facts(self.rav4, Source.CANADA, curb_weight_min=4600, curb_weight_max=4700)
        self.assertEqual(self.result(self.rav4).rule, heavy)
        self.assertEqual(self.result(self.rav4).vehicle_class, self.vehicle_class("Midsize SUVs"))

    def test_position_not_creation_order_sets_the_order_and_inactive_rules_are_skipped(self):
        self.rule(20, {"epa_size_class": SMALL_SUVS}, "Crossovers & Wagons")
        first = self.rule(10, {"make": ["TOYOTA"]}, "Midsize SUVs")
        self.assertEqual(self.result(self.rav4).rule, first)
        first.active = False
        first.save()
        self.assertEqual(self.result(self.rav4).vehicle_class, self.vehicle_class("Crossovers & Wagons"))

    def test_conditions_on_make_model_year_and_vehicle_type(self):
        rule = self.rule(10, {"model": ["RAV 4"], "year": {"from": 2019, "to": 2024}, "vehicle_type": ["vehicle"]}, "Midsize SUVs")
        self.assertEqual(self.result(self.rav4).rule, rule)
        rule.conditions["year"] = {"from": 2020}
        rule.save()
        self.assertTrue(self.result(self.rav4).in_review)

    def test_a_model_name_condition_matches_whole_words_from_the_start(self):
        promaster = add_model("Ram", "ProMaster 2500", source=VehicleModel.Source.NHTSA)
        add_facts(promaster, Source.VPIC, source_vehicle_types=["Truck"])
        pro = add_model("Ram", "Pro Master", source=VehicleModel.Source.NHTSA)
        add_facts(pro, Source.VPIC, source_vehicle_types=["Truck"])
        prom = add_model("Ram", "Prom", source=VehicleModel.Source.NHTSA)
        add_facts(prom, Source.VPIC, source_vehicle_types=["Truck"])
        self.rule(10, {"model": ["ProMaster"], "epa_size_class": ["none"]}, "Fullsize SUVs & Minivans")
        results = classify_catalog()
        self.assertEqual(results[(promaster.pk, 2019)][1].vehicle_class.name, "Fullsize SUVs & Minivans")
        self.assertEqual(results[(pro.pk, 2019)][1].vehicle_class.name, "Fullsize SUVs & Minivans")
        self.assertTrue(results[(prom.pk, 2019)][1].in_review)

    def test_the_conditions_are_checked(self):
        self.assertEqual(condition_errors({"epa_size_class": SMALL_SUVS, "curb_weight": {"over": 4500}}), [])
        for bad in ({"colour": ["red"]}, {"curb_weight": 4500}, {"curb_weight": {"above": 4500}}, {"make": "Ford"},
                    {"vehicle_type": ["boat"]}, {"year": {"from": "2019"}}):
            with self.subTest(conditions=bad):
                self.assertTrue(condition_errors(bad))
        rule = ClassificationRule(position=1, name="bad", conditions={"colour": ["red"]}, vehicle_class=self.vehicle_class("Midsize SUVs"))
        with self.assertRaises(ValidationError):
            rule.full_clean()

    def test_every_launch_rule_in_the_data_file_is_valid(self):
        data = read_data("vehicle-classes.yaml")
        for entry in data["launch_rules"]:
            with self.subTest(rule=entry["name"]):
                self.assertEqual(condition_errors(entry["conditions"]), [])
                self.vehicle_class(entry["class"])
        for entry in data["model_overrides"]:
            self.vehicle_class(entry["class"])


class OverrideTests(ClassificationTestCase):
    def setUp(self):
        self.wrangler = add_model("Jeep", "Wrangler", year_from=2018, year_to=2019)
        for year in (2018, 2019):
            add_facts(self.wrangler, year=year, epa_size_classes=["Small Sport Utility Vehicle 4WD"])
        self.rule(10, {"epa_size_class": SMALL_SUVS}, "Crossovers & Wagons")

    def test_a_model_override_beats_every_rule(self):
        override = ModelOverride.objects.create(
            vehicle_model=self.wrangler, vehicle_class=self.vehicle_class("Light Pickups & Offroad"), note="Offroad"
        )
        result = self.result(self.wrangler)
        self.assertEqual((result.vehicle_class.name, result.method, result.override), ("Light Pickups & Offroad", "override", override))
        # No cab style is known, so the customer is asked.
        self.assertTrue(result.ask_size)

    def test_an_override_for_some_years_beats_one_for_the_whole_model(self):
        ModelOverride.objects.create(vehicle_model=self.wrangler, vehicle_class=self.vehicle_class("Light Pickups & Offroad"))
        ModelOverride.objects.create(
            vehicle_model=self.wrangler, year_from=2019, vehicle_class=self.vehicle_class("Midsize SUVs"),
            size_variant=self.size("Midsize SUVs", 2),
        )
        self.assertEqual(self.result(self.wrangler, 2018).vehicle_class.name, "Light Pickups & Offroad")
        result = self.result(self.wrangler, 2019)
        self.assertEqual((result.vehicle_class.name, result.size_variant.value, result.ask_size), ("Midsize SUVs", 2, False))

    def test_an_override_can_always_ask_the_size(self):
        add_facts(self.wrangler, Source.SEAT_LIST, seat_rows=[2])
        ModelOverride.objects.create(vehicle_model=self.wrangler, vehicle_class=self.vehicle_class("Midsize SUVs"), ask_size=True)
        self.assertTrue(self.result(self.wrangler).ask_size)

    def test_every_override_records_who_set_it_when_and_a_note(self):
        user = get_user_model().objects.create_user("owner-test", password="made-up-password")
        override = ModelOverride.objects.create(
            vehicle_model=self.wrangler, vehicle_class=self.vehicle_class("Light Pickups & Offroad"), set_by=user, note="Lifted"
        )
        self.assertEqual((override.set_by, override.note), (user, "Lifted"))
        self.assertIsNotNone(override.set_at)

    def test_a_vehicle_override_beats_the_model_override_and_the_rules(self):
        ModelOverride.objects.create(vehicle_model=self.wrangler, vehicle_class=self.vehicle_class("Light Pickups & Offroad"))
        apply(classify_catalog())
        customer = Customer.objects.create(first_name="Pat")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_model=self.wrangler, year=2019, make="Jeep", model="Wrangler")
        self.assertEqual(classify(2019, "Jeep", "Wrangler", vehicle=vehicle).how, How.MODEL_OVERRIDE)
        user = get_user_model().objects.create_user("owner-test", password="made-up-password")
        vehicle.override_class(self.vehicle_class("Fullsize Trucks"), self.size("Fullsize Trucks", 2), user=user, note="Lifted on 37s")
        result = classify(2019, "Jeep", "Wrangler", vehicle=vehicle)
        self.assertEqual((result.how, result.vehicle_class.name, result.size_variant.value), (How.VEHICLE_OVERRIDE, "Fullsize Trucks", 2))
        self.assertEqual((vehicle.class_override_by, vehicle.class_override_note), (user, "Lifted on 37s"))
        self.assertIsNotNone(vehicle.class_override_at)


class SizeVariantTests(ClassificationTestCase):
    def sized(self, class_name, **fields):
        vehicle_model = add_model("Test", f"Model {VehicleModel.objects.count()}")
        sources = {"seat_rows": Source.SEAT_LIST, "cab_styles": Source.CANADA}
        add_facts(vehicle_model, **{name: value for name, value in fields.items() if name not in sources})
        for name, value in fields.items():
            if name in sources:
                add_facts(vehicle_model, sources[name], **{name: value})
        ModelOverride.objects.create(vehicle_model=vehicle_model, vehicle_class=self.vehicle_class(class_name))
        result = self.result(vehicle_model)
        return "ask" if result.ask_size else getattr(result.size_variant, "value", None)

    def test_cars_by_doors(self):
        self.assertEqual(self.sized("Coupes & Sedans", body_styles=["two-door"]), 1)
        self.assertEqual(self.sized("Coupes & Sedans", body_styles=["four-door"]), 2)
        self.assertEqual(self.sized("Coupes & Sedans", body_styles=["two-door", "four-door"]), "ask")
        # The EPA does not give a hatchback's doors.
        self.assertEqual(self.sized("Coupes & Sedans", body_styles=["hatchback"]), "ask")
        self.assertEqual(self.sized("Coupes & Sedans", body_styles=["unknown"]), "ask")

    def test_pickups_by_cab_asked_only_when_there_is_more_than_one(self):
        self.assertEqual(self.sized("Fullsize Trucks", cab_styles=["regular"]), 1)
        self.assertEqual(self.sized("Fullsize Trucks", cab_styles=["extended", "crew"]), 2)
        self.assertEqual(self.sized("Light Pickups & Offroad", cab_styles=["regular", "crew"]), "ask")
        self.assertEqual(self.sized("Light Pickups & Offroad"), "ask")

    def test_crossovers_and_midsize_suvs_by_the_third_row_flag(self):
        self.assertEqual(self.sized("Crossovers & Wagons", seat_rows=[2]), 2)
        self.assertEqual(self.sized("Midsize SUVs", seat_rows=[3]), 3)
        self.assertEqual(self.sized("Midsize SUVs", seat_rows=[2, 3]), "ask")
        self.assertEqual(self.sized("Crossovers & Wagons"), "ask")

    def test_a_class_with_one_size_or_none_never_asks(self):
        self.assertEqual(self.sized("Fullsize SUVs & Minivans"), 3)
        self.assertIsNone(self.sized("Motorcycles"))

    def test_the_third_row_list_comes_before_nhtsa_and_the_owner_before_both(self):
        vehicle_model = add_model("Test", "Seats")
        add_facts(vehicle_model, epa_size_classes=SMALL_SUVS)
        add_facts(vehicle_model, Source.VPIC, seat_rows=[3])
        self.rule(10, {"epa_size_class": SMALL_SUVS}, "Crossovers & Wagons")
        self.assertEqual(self.result(vehicle_model).size_variant.value, 3)
        add_facts(vehicle_model, Source.SEAT_LIST, seat_rows=[2])
        self.assertEqual(self.result(vehicle_model).size_variant.value, 2)
        add_facts(vehicle_model, Source.OWNER, seat_rows=[2, 3])
        self.assertTrue(self.result(vehicle_model).ask_size)

    def test_the_canadian_trim_names_give_the_cab_style(self):
        for trim, expected in (
            ("TACOMA DOUBLE CAB L/BOX 2WD", "extended"),
            ("2500 NEW GEN REG CAB L/BOX 2WD", "regular"),
            ("F-250 SD P/U SUPERCAB L/BOX", "extended"),
            ("F-150 HYBRID P/U SUPERCREW 6.5-FT BOX 4X4", "crew"),
            ("F-250 SUPER DUTY CREW CAB 4WD", "crew"),
            ("CANYON CREWCAB 2WD", "crew"),
            ("TUNDRA CREWMAX L/BOX 4WD", "crew"),
            ("911 CARRERA 2DR CABRIOLET", None),
            ("RAV4 AWD LE / XLE 4DR SUV", None),
        ):
            with self.subTest(trim=trim):
                self.assertEqual(cab_style(words(trim)), expected)


class ReviewQueueTests(ClassificationTestCase):
    def setUp(self):
        self.heavy = self.rule(10, {"epa_size_class": SMALL_SUVS, "curb_weight": {"over": 4500}}, "Midsize SUVs")
        self.small = self.rule(20, {"epa_size_class": SMALL_SUVS}, "Crossovers & Wagons")

    def test_no_rule_matches(self):
        odd = add_model("Test", "Odd")
        add_facts(odd, epa_size_classes=["Special Purpose Vehicle 2WD"])
        result = self.result(odd)
        self.assertTrue(result.in_review)
        self.assertEqual(result.reasons, ["no rule matches"])

    def test_trims_straddle_a_threshold(self):
        straddler = add_model("Test", "Straddler")
        add_facts(straddler, epa_size_classes=SMALL_SUVS)
        add_facts(straddler, Source.CANADA, curb_weight_min=4300, curb_weight_max=4700)
        result = self.result(straddler)
        self.assertTrue(result.in_review)
        self.assertEqual(result.rule, self.heavy)
        self.assertIn("split on the curb weight condition: its range, 4300 to 4700, spans it", result.reasons[0])

    def test_trims_straddle_two_epa_size_classes(self):
        bronco = add_model("Ford", "Bronco")
        add_facts(bronco, epa_size_classes=["Small Sport Utility Vehicle 4WD", "Standard Sport Utility Vehicle 4WD"])
        self.assertIn("split on the EPA size class condition: 1 of 2 rows (50%) meet it", self.result(bronco).reasons[0])

    def test_two_sources_disagree_on_a_fact_a_rule_uses(self):
        disputed = add_model("Test", "Disputed")
        add_facts(disputed, epa_size_classes=SMALL_SUVS)
        add_facts(disputed, Source.CANADA, curb_weight_min=4600, curb_weight_max=4800)
        add_facts(disputed, Source.VPIC, curb_weight_min=4000, curb_weight_max=4200)
        result = self.result(disputed)
        self.assertTrue(result.in_review)
        self.assertIn("sources disagree on the curb weight condition", result.reasons[0])
        # The owner's own figure settles it.
        add_facts(disputed, Source.OWNER, curb_weight_min=4100, curb_weight_max=4100)
        self.assertEqual(self.result(disputed).rule, self.small)

    def test_a_live_model_year_keeps_its_class_while_it_waits(self):
        rav4 = add_model("Toyota", "RAV4")
        add_facts(rav4, epa_size_classes=SMALL_SUVS)
        add_facts(rav4, Source.SEAT_LIST, seat_rows=[2])
        apply(classify_catalog())
        self.assertEqual(classified(rav4).vehicle_class.name, "Crossovers & Wagons")
        add_facts(rav4, Source.CANADA, curb_weight_min=4300, curb_weight_max=4700)
        apply(classify_catalog())
        row = classified(rav4)
        self.assertTrue(row.in_review)
        self.assertEqual(row.vehicle_class.name, "Crossovers & Wagons")
        self.assertEqual(classify(2019, "Toyota", "RAV4").vehicle_class.name, "Crossovers & Wagons")

    def test_a_new_model_year_in_the_queue_does_not_go_live(self):
        odd = add_model("Test", "Odd")
        add_facts(odd, epa_size_classes=["Vans"])
        apply(classify_catalog())
        self.assertIsNone(classified(odd).vehicle_class)
        result = classify(2019, "Test", "Odd")
        self.assertEqual(result.how, How.REVIEW_QUEUE)
        self.assertEqual(len(result.photo_cards), 7)


class PreviewTests(ClassificationTestCase):
    def setUp(self):
        self.rav4 = add_model("Toyota", "RAV4", year_from=2018)
        for year in (2018, 2019):
            add_facts(self.rav4, year=year, epa_size_classes=SMALL_SUVS)
            add_facts(self.rav4, Source.SEAT_LIST, year=year, seat_rows=[2])
        self.small = self.rule(20, {"epa_size_class": SMALL_SUVS}, "Crossovers & Wagons")
        apply(classify_catalog())

    def test_a_proposed_rule_lists_every_model_year_that_would_change_and_saves_nothing(self):
        proposed = ClassificationRule(
            position=10, name="Toyotas are midsize", conditions={"make": ["Toyota"]},
            vehicle_class=self.vehicle_class("Midsize SUVs"),
        )
        found = preview(rules=[proposed, self.small])
        self.assertEqual([change.year for change in found], [2018, 2019])
        change = found[0]
        self.assertEqual((change.old_class.name, change.old_size), ("Crossovers & Wagons", "two rows"))
        self.assertEqual((change.new_class.name, change.new_size), ("Midsize SUVs", "two rows"))
        self.assertEqual(change.because, "rule 10: Toyotas are midsize")
        self.assertEqual(ClassificationRule.objects.count(), 1)
        self.assertEqual(classified(self.rav4).vehicle_class.name, "Crossovers & Wagons")

    def test_a_proposed_override_and_a_size_change_are_listed(self):
        override = ModelOverride(vehicle_model=self.rav4, year_from=2019, vehicle_class=self.vehicle_class("Crossovers & Wagons"), ask_size=True)
        found = preview(overrides=[override])
        self.assertEqual([(change.year, change.old_size, change.new_size) for change in found], [(2019, "two rows", "ask")])
        self.assertFalse(ModelOverride.objects.exists())

    def test_nothing_changes_when_nothing_was_changed(self):
        self.assertEqual(preview(), [])


class LookupTests(ClassificationTestCase):
    def setUp(self):
        self.civic = add_model("Honda", "Civic")
        add_facts(self.civic, epa_size_classes=["Compact Cars"], body_styles=["two-door", "four-door", "hatchback"])
        self.rule(10, {"vehicle_type": ["motorcycle"]}, "Motorcycles")
        self.rule(20, {"epa_size_class": ["Compact Cars"]}, "Coupes & Sedans")
        apply(classify_catalog())

    def test_the_size_question_and_its_answer(self):
        result = classify(2019, "Honda", "Civic")
        self.assertEqual((result.how, result.vehicle_class.name, result.size_variant), (How.RULE, "Coupes & Sedans", None))
        self.assertEqual(result.question.key, "doors")
        self.assertEqual(result.price_basis, VehicleClass.PriceBasis.PRICE_LIST)
        self.assertEqual(result.vehicle_type, VEHICLE)
        answered = classify(2019, "honda", "CIVIC", {"doors": 4})
        self.assertEqual((answered.size_variant.value, answered.question), (2, None))
        with self.assertRaises(ValueError):
            classify(2019, "Honda", "Civic", {"doors": 3})

    def test_years_before_1984_and_models_not_in_the_catalog_get_the_photo_cards(self):
        for year, make, name in ((1969, "Ford", "Mustang"), (2019, "Ford", "Mustang"), (2030, "Honda", "Civic")):
            with self.subTest(vehicle=(year, make, name)):
                result = classify(year, make, name)
                self.assertEqual(result.how, How.PHOTO_CARDS)
                self.assertIsNone(result.vehicle_class)
                cards = [card.vehicle_class.name for card in result.photo_cards]
                self.assertEqual(len(cards), 7)
                self.assertIn("Motorcycles", cards)

    def test_a_motorcycle_and_a_car_of_the_same_name(self):
        gold_wing = add_model("Honda", "Gold Wing", MOTORCYCLE, VehicleModel.Source.NHTSA)
        add_facts(gold_wing, Source.VPIC, source_vehicle_types=["Motorcycle"])
        apply(classify_catalog())
        result = classify(2019, "Honda", "Gold Wing")
        self.assertEqual((result.vehicle_class.name, result.vehicle_type, result.question), ("Motorcycles", MOTORCYCLE, None))


class MotorcycleTests(ClassificationTestCase):
    def setUp(self):
        self.fat_boy = add_model("Harley-Davidson", "Fat Boy", MOTORCYCLE, VehicleModel.Source.NHTSA)
        add_facts(self.fat_boy, Source.VPIC, source_vehicle_types=["Motorcycle"])
        self.rule(10, {"vehicle_type": ["motorcycle"]}, "Motorcycles")
        apply(classify_catalog())

    def test_a_motorcycle_is_100_dollars_whatever_the_condition_level(self):
        result = classify(2019, "Harley-Davidson", "Fat Boy")
        self.assertEqual((result.vehicle_class.name, result.size_variant, result.question), ("Motorcycles", None, None))
        detail = Service.objects.get(name="Motorcycle Detail")
        self.assertFalse(detail.condition_applies)
        for level in (None, 1, 2, 3):
            with self.subTest(condition_level=level):
                job = price_job(detail, result.vehicle_class, result.size_variant, condition_level=level)
                self.assertEqual(job.total_before_tax, Decimal("100.00"))
                self.assertEqual(len(job.lines), 1)
                self.assertIsNone(job.lines[0].condition_level)
                # 1 hour of service, 2 hours on site with setup and breakdown.
                self.assertEqual(job.service_minutes, 60)
                self.assertEqual(job.time_on_site.total_minutes, 120)
                self.assertEqual(job.crew_size, 1)

    def test_motorcycle_detail_is_offered_only_for_motorcycles_and_takes_no_add_ons(self):
        detail = Service.objects.get(name="Motorcycle Detail")
        motorcycles = self.vehicle_class("Motorcycles")
        self.assertEqual(
            list(Price.objects.filter(service=detail).values_list("vehicle_class__name", flat=True)), ["Motorcycles"]
        )
        self.assertEqual(list(Price.objects.filter(vehicle_class=motorcycles).values_list("service__name", flat=True)), ["Motorcycle Detail"])
        with self.assertRaises(NotPriced):
            price_job(detail, motorcycles, add_ons=[Service.objects.get(name="Seat Extraction")])
        with self.assertRaises(NotPriced):
            price_job(detail, self.vehicle_class("Coupes & Sedans"))

    def test_the_motorcycles_class_settings(self):
        motorcycles = self.vehicle_class("Motorcycles")
        self.assertEqual(motorcycles.size_variant_measures, VehicleClass.Measures.NONE)
        self.assertEqual(motorcycles.booking, VehicleClass.Booking.ONLINE)
        self.assertEqual(motorcycles.photo_card, "Motorcycles")
        self.assertFalse(motorcycles.size_variants.exists())
        rules = yaml.safe_load((settings.DATA_DIR / "booking-rules.yaml").read_text())["services_sharing_a_day"]
        self.assertIn({"service": "Motorcycle Detail", "max_per_day": 2}, rules)
        self.assertIn({"service": "Monthly Maintenance", "max_per_day": 2}, rules)


class ClassifyVehiclesCommandTests(CachedFixtures, ClassificationTestCase):
    """classify_vehicles on the catalog the import loads from its fixtures,
    with the launch rules and the third-row list from data/."""

    def setUp(self):
        super().setUp()
        self.run_import()

    def command(self, *args):
        out = io.StringIO()
        call_command("classify_vehicles", *args, stdout=out)
        return out.getvalue()

    def test_the_rav4_worked_example(self):
        """Decision 0065: a 2019 Toyota RAV4 is Crossovers & Wagons with two
        rows, and a level 2 Full Detail with Seat Extraction is $355."""
        self.command()
        result = classify(2019, "Toyota", "RAV4")
        self.assertEqual((result.how, result.vehicle_class.name, result.size_variant.value), (How.RULE, "Crossovers & Wagons", 2))
        self.assertEqual(result.rule.name, "EPA small SUVs and station wagons")
        job = price_job(
            Service.objects.get(name="Full Detail"), result.vehicle_class, result.size_variant,
            condition_level=2, add_ons=[Service.objects.get(name="Seat Extraction")],
        )
        self.assertEqual(job.total_before_tax, Decimal("355.00"))
        self.assertEqual(job.time_on_site.total_minutes, 480)

    def test_the_launch_set_on_the_fixture_catalog(self):
        self.command()
        expected = {
            ("Toyota", "Camry"): ("Coupes & Sedans", 2),
            ("Honda", "Civic"): ("Coupes & Sedans", "ask"),
            ("Ford", "F150"): ("Fullsize Trucks", 2),          # SUPERCREW in the Canadian trim name
            ("Ford", "F-250"): ("Fullsize Trucks", 2),         # vPIC only; CREW CAB
            ("Ford", "F-350"): ("Fullsize Trucks", "ask"),     # vPIC only; no cab style known
            ("Ford", "Transit"): ("Fullsize SUVs & Minivans", 3),
            ("Ford", "Expedition"): ("Fullsize SUVs & Minivans", 3),  # the launch model override
            ("Harley-Davidson", "Fat Boy"): ("Motorcycles", None),
        }
        for (make, name), (class_name, size) in expected.items():
            with self.subTest(vehicle=(make, name)):
                result = classify(2019, make, name)
                self.assertEqual(result.vehicle_class.name, class_name)
                self.assertEqual("ask" if result.question else getattr(result.size_variant, "value", None), size)
        self.assertEqual(classify(2019, "Ford", "Expedition").how, How.MODEL_OVERRIDE)
        self.assertTrue(VehicleModel.objects.get(make="Honda", model="Civic").ask_size)
        self.assertFalse(VehicleModel.objects.get(make="Toyota", model="RAV4").ask_size)

    def test_a_dry_run_prints_the_preview_and_changes_nothing(self):
        output = self.command("--dry-run")
        self.assertIn("DRY RUN", output)
        self.assertIn("Toyota RAV4 2019: no class -> Crossovers & Wagons (two rows) (rule 140: EPA small SUVs and station wagons)", output)
        self.assertFalse(ModelYearClassification.objects.exists())
        self.assertFalse(ClassificationRule.objects.exists())
        self.assertFalse(VehicleModelYear.objects.filter(source=Source.SEAT_LIST).exists())

    def test_a_rerun_changes_nothing_and_a_deleted_launch_rule_is_not_added_again(self):
        self.command()
        rules = ClassificationRule.objects.count()
        self.assertEqual(rules, len(read_data("vehicle-classes.yaml")["launch_rules"]))
        self.assertIn("Launch rules and overrides (data/vehicle-classes.yaml): 0 changes", self.command("--dry-run"))
        ClassificationRule.objects.filter(name="Motorcycles").delete()
        output = self.command()
        self.assertEqual(ClassificationRule.objects.count(), rules - 1)
        self.assertIn("not added again: launch rule Motorcycles, which you deleted", output)
        self.assertIn("Fat Boy 2019: Motorcycles (one price) -> Motorcycles (one price), enters the review queue", output)

    def test_it_never_changes_an_override_a_customer_vehicle_or_an_owner_record(self):
        self.command()
        expedition = VehicleModel.objects.get(make="Ford", model="Expedition")
        override = expedition.overrides.get()
        owner_row = add_facts(VehicleModel.objects.get(make="Toyota", model="RAV4"), Source.OWNER, seat_rows=[2])
        customer = Customer.objects.create(first_name="Pat")
        vehicle = Vehicle.objects.create(
            customer=customer, year=2019, make="Toyota", model="RAV4", vehicle_class=self.vehicle_class("Midsize SUVs")
        )
        before = (override.history.count(), owner_row.seat_rows, vehicle.vehicle_class_id)
        self.command()
        override.refresh_from_db()
        owner_row.refresh_from_db()
        vehicle.refresh_from_db()
        self.assertEqual((override.history.count(), owner_row.seat_rows, vehicle.vehicle_class_id), before)
        self.assertEqual(classify(2019, "Ford", "Expedition").override, override)

    def test_the_third_row_list_is_matched_and_unmatched_rows_listed(self):
        output = self.command()
        rav4 = VehicleModelYear.objects.get(vehicle_model__model="RAV4", year=2019, source=Source.SEAT_LIST)
        self.assertEqual(rav4.seat_rows, [2])
        self.assertIn("Acura MDX 2010-: always: no catalog model of this make and name", output)
        self.assertNotIn("Toyota RAV4 2010-", output)

    def test_an_empty_catalog_is_refused(self):
        VehicleModelYear.objects.all().delete()
        VehicleModel.objects.all().delete()
        with self.assertRaisesMessage(CommandError, "run import_vehicle_data first"):
            self.command()


class ThirdRowListTests(ClassificationTestCase):
    """The list's year ranges, optional rows and make aliases, on a small list."""

    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.data)
        shutil.copy(settings.DATA_DIR / "vehicle-data-import.yaml", self.data)
        shutil.copy(settings.DATA_DIR / "vehicle-names.yaml", self.data)
        self.highlander = add_model("Toyota", "Highlander", year_from=2012, year_to=2014)
        for year in (2012, 2013, 2014):
            add_facts(self.highlander, year=year, epa_size_classes=SMALL_SUVS)
        self.ram = add_model("Ram", "1500 Classic")
        add_facts(self.ram)

    def sync(self, models):
        (self.data / "third-row-seating.yaml").write_text(yaml.safe_dump({"models": models}))
        report = SeedReport()
        sync_seat_list(report, data_dir=self.data)
        return report

    def seat_rows(self, vehicle_model, year):
        return VehicleModelYear.objects.get(vehicle_model=vehicle_model, year=year, source=Source.SEAT_LIST).seat_rows

    def test_year_ranges_optional_rows_and_aliases(self):
        report = self.sync([
            {"make": "Toyota", "models": ["Highlander"], "first_year": 2010, "last_year": 2013, "third_row": "optional"},
            {"make": "toyota", "models": ["HIGHLANDER"], "first_year": 2014, "last_year": None, "third_row": "always"},
            {"make": "RAM TRUCKS", "models": ["1500 Classic"], "first_year": 2019, "last_year": None, "third_row": "never"},
            {"make": "Toyota", "models": ["Highlander"], "first_year": 2020, "last_year": None, "third_row": "always"},
            {"make": "Kia", "models": ["Telluride"], "first_year": 2020, "last_year": None, "third_row": "always"},
        ])
        self.assertEqual([self.seat_rows(self.highlander, year) for year in (2012, 2013, 2014)], [[2, 3], [2, 3], [3]])
        self.assertEqual(self.seat_rows(self.ram, 2019), [2])
        self.assertEqual(
            report.unmatched_seat_rows,
            [
                "Toyota Highlander 2020-: always: the catalog has the model, but not in these years",
                "Kia Telluride 2020-: always: no catalog model of this make and name",
            ],
        )
        # The list never stretches a model's years.
        self.highlander.refresh_from_db()
        self.assertEqual((self.highlander.year_from, self.highlander.year_to), (2012, 2014))

    def test_a_year_the_list_drops_loses_its_row(self):
        self.sync([{"make": "Toyota", "models": ["Highlander"], "first_year": 2010, "last_year": None, "third_row": "always"}])
        report = self.sync([{"make": "Toyota", "models": ["Highlander"], "first_year": 2014, "last_year": None, "third_row": "always"}])
        self.assertEqual(report.counts["model years removed"], 2)
        self.assertEqual(VehicleModelYear.objects.filter(source=Source.SEAT_LIST).count(), 1)


class LoadPricebookAddsNewCellsTests(TestCase):
    """On the server version 1 is already published without Motorcycle
    Detail; load_pricebook puts the new price in a draft for the owner."""

    def setUp(self):
        self.data = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.data)
        for path in settings.DATA_DIR.iterdir():
            if path.is_file():
                shutil.copy(path, self.data)
        matrix = (settings.DATA_DIR / "price-matrix.csv").read_text().splitlines()
        (self.data / "price-matrix.csv").write_text("\n".join(line for line in matrix if "Motorcycle" not in line) + "\n")
        classes = yaml.safe_load((settings.DATA_DIR / "vehicle-classes.yaml").read_text())
        classes["classes"] = [entry for entry in classes["classes"] if entry["name"] != "Motorcycles"]
        (self.data / "vehicle-classes.yaml").write_text(yaml.safe_dump(classes))
        services = yaml.safe_load((settings.DATA_DIR / "services.yaml").read_text())
        services["services"] = [entry for entry in services["services"] if entry["name"] != "Motorcycle Detail"]
        (self.data / "services.yaml").write_text(yaml.safe_dump(services))
        with override_settings(DATA_DIR=self.data):
            call_command("load_pricebook", stdout=io.StringIO())

    def test_the_new_service_goes_into_a_draft(self):
        self.assertFalse(VehicleClass.objects.filter(name="Motorcycles").exists())
        out = io.StringIO()
        call_command("load_pricebook", stdout=out)
        self.assertIn("Added vehicle class Motorcycles.", out.getvalue())
        self.assertIn("Added service Motorcycle Detail.", out.getvalue())
        draft = PricebookVersion.objects.get(number=2)
        self.assertFalse(draft.is_published)
        self.assertEqual(draft.prices.get(service__name="Motorcycle Detail").price, Decimal("100.00"))
        self.assertEqual(draft.prices.count(), PricebookVersion.objects.get(number=1).prices.count() + 1)
        # Run again while the draft is open: refused, nothing changed.
        with self.assertRaisesMessage(CommandError, "draft version 2 is open"):
            call_command("load_pricebook", stdout=io.StringIO())
        self.assertEqual(PricebookVersion.objects.count(), 2)


class CommandHelpersTests(SimpleTestCase):
    def test_consecutive_years_are_joined(self):
        from vehicles.management.commands.classify_vehicles import spans

        rav4 = VehicleModel(pk=1, make="Toyota", model="RAV4")
        rows = [(rav4, 2019, "a"), (rav4, 2018, "a"), (rav4, 2021, "a"), (rav4, 2022, "b")]
        self.assertEqual(spans(rows), ["Toyota RAV4 2018-2019: a", "Toyota RAV4 2021: a", "Toyota RAV4 2022: b"])
