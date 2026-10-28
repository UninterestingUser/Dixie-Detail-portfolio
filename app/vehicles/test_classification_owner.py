"""The owner's dry-run fixes and the owner's changes from the control app
(decisions 0075 and 0076): model years the EPA has not published, Canadian
trims split by nameplate, review queue suggestions and decisions, rules in
plain words, moving a rule, and the change log."""

from django.contrib.auth import get_user_model

from vehicles.classification import owner
from vehicles.classification.engine import apply, classify_catalog, not_yet_published
from vehicles.classification.lookup import How, classify
from vehicles.classification.rules import describe_conditions
from vehicles.models import (
    ClassificationChange,
    ClassificationRule,
    ModelOverride,
    ModelYearClassification,
    ReviewDecision,
)
from vehicles.test_classification import SMALL_SUVS, ClassificationTestCase, Source, add_facts, add_model, classified
from vehicles.vehicle_data.canada import facts_by_model_year
from vehicles.vehicle_data.names import load_names
from vehicles.vehicle_data.run import SourceReport

PICKUPS = ["Standard Pickup Trucks 4WD"]
Method = ModelYearClassification.Method


class NotYetPublishedTests(ClassificationTestCase):
    """A model year only vPIC lists so far, such as next year's F-150, takes
    the class and size of the model's nearest classified year."""

    def setUp(self):
        self.pickups = self.rule(10, {"epa_size_class": PICKUPS}, "Full-size Trucks", name="EPA standard pickups")
        self.f150 = add_model("Ford", "F-150", year_from=2025, year_to=2027)
        for year in (2025, 2026):
            add_facts(self.f150, year=year, epa_size_classes=PICKUPS)
            add_facts(self.f150, Source.CANADA, year=year, cab_styles=["crew"])
        add_facts(self.f150, Source.VPIC, year=2027, source_vehicle_types=["Truck"])

    def test_it_takes_the_nearest_classified_years_class_and_size_and_says_so(self):
        result = self.result(self.f150, 2027)
        self.assertEqual((result.method, result.carried_from, result.vehicle_class.name), (Method.CARRIED, 2026, "Full-size Trucks"))
        self.assertEqual((result.size_variant.value, result.ask_size, result.rule), (2, False, self.pickups))
        self.assertEqual(result.because, "from the 2026 model year, rule 10: EPA standard pickups; the EPA has not published this year yet")
        apply(classify_catalog())
        found = classify(2027, "Ford", "F-150")
        self.assertEqual((found.how, found.carried_from, found.vehicle_class.name), (How.NEAREST_YEAR, 2026, "Full-size Trucks"))
        self.assertIn("the EPA has not published this year yet", found.because)

    def test_it_is_classified_again_when_the_epa_data_arrives(self):
        apply(classify_catalog())
        add_facts(self.f150, year=2027, epa_size_classes=PICKUPS)
        apply(classify_catalog())
        row = classified(self.f150, 2027)
        self.assertEqual((row.method, row.carried_from, row.rule), (Method.RULE, None, self.pickups))

    def test_an_override_for_the_year_still_wins(self):
        ModelOverride.objects.create(vehicle_model=self.f150, year_from=2027, vehicle_class=self.vehicle_class("Large"))
        self.assertEqual(self.result(self.f150, 2027).method, Method.OVERRIDE)

    def test_only_the_epas_newest_years_count_as_unpublished(self):
        # An old year the EPA skipped is not "not yet published": it goes by the rules.
        old = add_model("Test", "Old", year_from=2010, year_to=2011)
        add_facts(old, year=2010, epa_size_classes=PICKUPS)
        add_facts(old, Source.VPIC, year=2011, source_vehicle_types=["Truck"])
        results = classify_catalog()
        self.assertEqual(results[(old.pk, 2011)][1].reasons, ["no rule matches: no dimensions in any year and no EPA size class"])
        self.assertEqual(not_yet_published([found for found, _ in results.values()], 2), {(self.f150.pk, 2027)})

    def test_a_model_the_epa_never_lists_goes_by_the_rules(self):
        heavy = add_model("Ford", "F-250", year_from=2026, year_to=2027)
        self.rule(5, {"epa_size_class": ["none"], "model_word": ["F-250"]}, "Full-size Trucks")
        for year in (2026, 2027):
            add_facts(heavy, Source.VPIC, year=year, source_vehicle_types=["Truck"])
        self.assertEqual(self.result(heavy, 2027).method, Method.RULE)

    def test_with_no_classified_year_it_waits_in_the_queue(self):
        lonely = add_model("Test", "Lonely", year_from=2026, year_to=2027)
        add_facts(lonely, year=2026, epa_size_classes=["Vans"])
        add_facts(lonely, Source.VPIC, year=2027, source_vehicle_types=["Truck"])
        self.assertTrue(self.result(lonely, 2027).in_review)


class CanadianNameplateTests(ClassificationTestCase):
    def test_a_canadian_suv_trim_goes_to_the_suv_nameplate(self):
        sedan = add_model("Mercedes-Benz", "EQE", year_from=2025, year_to=2025)
        suv = add_model("Mercedes-Benz", "EQE SUV", year_from=2025, year_to=2025)
        add_facts(sedan, year=2025, epa_size_classes=["Midsize Cars"])
        add_facts(suv, year=2025, epa_size_classes=["Standard Sport Utility Vehicle 4WD"])
        rows = [
            ("Mercedes-Benz", 2025, {"Make": "MERCEDES-BENZ", "Model": "EQE CLASS 350 4DR SEDAN", "CW": "5456.4"}),
            ("Mercedes-Benz", 2025, {"Make": "MERCEDES-BENZ", "Model": "EQE CLASS 350 4DR SUV", "CW": "5643.8"}),
            ("Mercedes-Benz", 2025, {"Make": "MERCEDES-BENZ", "Model": "EQE CLASS AMG 4DR SUV", "CW": "5789.3"}),
        ]
        report = SourceReport("canada")
        grouped = facts_by_model_year(rows, report, load_names())
        self.assertEqual(report.unmatched, [])
        self.assertEqual(grouped[(sedan.pk, 2025)].values()["curb_weight_max"], 5456)
        self.assertEqual(grouped[(suv.pk, 2025)].values()["curb_weight_min"], 5644)
        self.assertEqual(grouped[(suv.pk, 2025)].values()["curb_weight_max"], 5789)

    def test_the_sedan_spellings_are_one_vehicle(self):
        names = load_names()
        self.assertEqual(names.model("Mercedes-Benz", "EQE-Class Sedan"), "EQE")
        self.assertEqual(names.model("Mercedes-Benz", "EQS-Class SUV"), "EQS SUV")


class SuggestionTests(ClassificationTestCase):
    def setUp(self):
        self.heavy = self.rule(10, {"epa_size_class": SMALL_SUVS, "curb_weight": {"over": 4500}}, "Large")
        self.small = self.rule(20, {"epa_size_class": SMALL_SUVS}, "Medium")

    def test_a_straddle_suggests_the_rules_class_and_is_filed_as_split(self):
        straddler = add_model("Test", "Straddler")
        add_facts(straddler, epa_size_classes=SMALL_SUVS)
        add_facts(straddler, Source.CANADA, curb_weight_min=4300, curb_weight_max=4700)
        add_facts(straddler, Source.SEAT_LIST, seat_rows=[3])
        result = self.result(straddler)
        self.assertEqual((result.suggested_class.name, result.suggested_size.value, result.kinds), ("Large", 3, ["split"]))

    def test_no_rule_suggests_the_nearest_classified_year(self):
        odd = add_model("Test", "Odd", year_from=2018, year_to=2019)
        add_facts(odd, year=2018, epa_size_classes=SMALL_SUVS)
        add_facts(odd, year=2019, epa_size_classes=["Special Purpose Vehicle 2WD"])
        result = self.result(odd, 2019)
        self.assertEqual((result.kinds, result.suggested_class.name, result.suggested_ask), (["no_rule"], "Medium", False))
        apply(classify_catalog())
        row = classified(odd)
        self.assertEqual((row.review_kinds, row.suggested_class.name, row.suggested_ask_size), (["no_rule"], "Medium", False))

    def test_disagreeing_sources_are_filed_as_such(self):
        disputed = add_model("Test", "Disputed")
        add_facts(disputed, epa_size_classes=SMALL_SUVS)
        add_facts(disputed, Source.CANADA, curb_weight_min=4600, curb_weight_max=4800)
        add_facts(disputed, Source.VPIC, curb_weight_min=4000, curb_weight_max=4200)
        self.assertEqual(self.result(disputed).kinds, ["disagree"])


class DecisionTests(ClassificationTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("owner-test", password="made-up-password")
        self.rule(10, {"epa_size_class": SMALL_SUVS}, "Medium")
        self.odd = add_model("Test", "Odd")
        add_facts(self.odd, epa_size_classes=["Vans"])
        self.rav4 = add_model("Toyota", "RAV4")
        add_facts(self.rav4, epa_size_classes=SMALL_SUVS)
        apply(classify_catalog())

    def test_a_decision_settles_the_model_year_and_is_logged(self):
        decided, skipped = owner.decide([classified(self.odd)], self.user, "class", self.vehicle_class("Fullsize SUVs & Minivans"))
        self.assertEqual((len(decided), skipped), (1, []))
        row = classified(self.odd)
        self.assertEqual((row.in_review, row.method, row.vehicle_class.name, row.decision), (False, Method.DECISION, "Fullsize SUVs & Minivans", decided[0]))
        change = ClassificationChange.objects.get(kind=ClassificationChange.Kind.DECISION)
        self.assertEqual((change.made_by, change.vehicle_model), (self.user, self.odd))
        self.assertEqual(list(change.effects.values_list("year", "before", "after")), [(2019, "no class", "Fullsize SUVs & Minivans (always three rows), leaves the review queue")])
        self.assertEqual(classify(2019, "Test", "Odd").how, How.QUEUE_DECISION)

    def test_the_photo_cards_take_it_out_of_the_queue_with_no_class(self):
        owner.decide([classified(self.odd)], self.user, "photo_cards")
        row = classified(self.odd)
        self.assertEqual((row.in_review, row.method, row.vehicle_class), (False, Method.PHOTO_CARDS, None))
        result = classify(2019, "Test", "Odd")
        self.assertEqual((result.how, len(result.photo_cards)), (How.PHOTO_CARDS, 8))

    def test_a_model_year_with_no_suggestion_cannot_be_accepted(self):
        decided, skipped = owner.decide([classified(self.odd)], self.user, "accept")
        self.assertEqual((decided, len(skipped)), ([], 1))
        self.assertFalse(ReviewDecision.objects.exists())

    def test_a_model_override_beats_a_decision_and_clearing_a_decision_puts_it_back(self):
        owner.decide([classified(self.odd)], self.user, "photo_cards")
        owner.set_override(self.odd, self.user, self.vehicle_class("Large"), note="Checked")
        self.assertEqual(classified(self.odd).method, Method.OVERRIDE)
        owner.clear_override(ModelOverride.objects.get(), self.user)
        owner.clear_decision(ReviewDecision.objects.get(), self.user)
        self.assertTrue(classified(self.odd).in_review)

    def test_reclassifying_one_model_leaves_the_others_alone(self):
        rav4_row = classified(self.rav4)
        ModelYearClassification.objects.filter(pk=rav4_row.pk).update(classified_at=rav4_row.classified_at.replace(year=2020))
        owner.decide([classified(self.odd)], self.user, "photo_cards")
        self.assertEqual(classified(self.rav4).classified_at.year, 2020)

    def test_the_third_row_flag_is_the_owners_own_seat_rows(self):
        owner.set_third_row(self.rav4, self.user, "always", note="Checked the brochure")
        self.assertEqual(classified(self.rav4).size_variant.value, 3)
        owner.set_third_row(self.rav4, self.user, "clear")
        # With no third-row data, a size-based class is two rows.
        self.assertEqual(classified(self.rav4).size_variant.value, 2)
        self.assertEqual(ClassificationChange.objects.filter(kind=ClassificationChange.Kind.THIRD_ROW).count(), 2)


class PlainWordsTests(ClassificationTestCase):
    def test_conditions_in_plain_words(self):
        self.assertEqual(
            describe_conditions({"epa_size_class": ["Small Sport Utility Vehicle 2WD"], "curb_weight": {"over": 4000}}),
            "EPA size class Small Sport Utility Vehicle 2WD and curb weight over 4,000 lb",
        )
        self.assertEqual(describe_conditions({"year": {"to": 2012}, "length": {"over": 215, "up_to": 230.5}}), "model year up to 2012 and length over 215 in and up to 230.5 in")
        self.assertEqual(describe_conditions({"epa_size_class": ["none"], "model": ["Express", "Savana", "Transit"]}), "model is or begins with Express, Savana or Transit and no EPA size class listed")
        self.assertEqual(describe_conditions({"vehicle_type": ["motorcycle"], "seat_rows": [3]}), "vehicle type motorcycle and 3 seat rows")
        self.assertEqual(describe_conditions({}), "every model year")


class MoveTests(ClassificationTestCase):
    def test_a_move_changes_only_the_moved_rule_when_there_is_room(self):
        first, second, third = (self.rule(position, {"make": [str(position)]}, "Large") for position in (10, 20, 30))
        moved = owner.moved(third, "up")
        self.assertEqual([(rule.pk, rule.position) for rule in moved], [(third.pk, 15)])
        self.assertEqual(owner.moved(first, "up"), [])
        self.assertEqual(ClassificationRule.objects.get(pk=third.pk).position, 30)

    def test_with_no_room_the_rules_are_numbered_again(self):
        first, second = self.rule(10, {"make": ["A"]}, "Large"), self.rule(11, {"make": ["B"]}, "Large")
        third = self.rule(12, {"make": ["C"]}, "Large")
        moved = {rule.pk: rule.position for rule in owner.moved(third, "up")}
        self.assertEqual(moved, {third.pk: 20, second.pk: 30})
