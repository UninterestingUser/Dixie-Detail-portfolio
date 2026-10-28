"""The vehicle catalog screens (decision 0076): who may see and change them,
looking a vehicle up, the preview before a rule or class setting is saved,
the review queue's actions, overrides and the history on a model's screen."""

import re

from django.test import Client
from django.urls import reverse

from vehicles.classification.engine import apply, classify_catalog
from vehicles.models import (
    ClassificationChange,
    ClassificationRule,
    ModelOverride,
    ModelYearClassification,
    ReviewDecision,
    VehicleClass,
    VehicleModel,
    VehicleModelYear,
)

from .fixtures import TAILNET, JobsTestCase

Source = VehicleModelYear.Source
SMALL_SUVS = ["Small Sport Utility Vehicle 2WD", "Small Sport Utility Vehicle 4WD"]


def add_model(make, name, year_from=2019, year_to=2019):
    return VehicleModel.objects.create(make=make, model=name, source=VehicleModel.Source.EPA, year_from=year_from, year_to=year_to)


def add_facts(vehicle_model, source=Source.EPA, year=2019, **fields):
    return VehicleModelYear.objects.create(vehicle_model=vehicle_model, year=year, source=source, **fields)


def classified(vehicle_model, year=2019):
    return ModelYearClassification.objects.get(vehicle_model=vehicle_model, year=year)


class CatalogTestCase(JobsTestCase):
    """A small catalog: a RAV4 a rule settles, and two model years in the
    review queue, one with a suggestion (its trims straddle the weight rule)
    and one without (no rule matches)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.midsize = VehicleClass.objects.get(name="Large")
        cls.heavy = ClassificationRule.objects.create(
            position=10, name="Small SUVs over 4,500 lb", vehicle_class=cls.midsize,
            conditions={"epa_size_class": SMALL_SUVS, "curb_weight": {"over": 4500}},
        )
        cls.small = ClassificationRule.objects.create(
            position=20, name="EPA small SUVs", vehicle_class=cls.crossover, conditions={"epa_size_class": SMALL_SUVS},
        )
        cls.rav4 = add_model("Toyota", "RAV4")
        add_facts(cls.rav4, epa_size_classes=SMALL_SUVS)
        add_facts(cls.rav4, Source.SEAT_LIST, seat_rows=[2])
        add_facts(cls.rav4, Source.CANADA, curb_weight_min=3400, curb_weight_max=3700)
        cls.straddler = add_model("Test", "Straddler", 2018, 2018)
        add_facts(cls.straddler, year=2018, epa_size_classes=SMALL_SUVS)
        add_facts(cls.straddler, Source.CANADA, year=2018, curb_weight_min=4300, curb_weight_max=4700)
        cls.odd = add_model("Test", "Odd")
        add_facts(cls.odd, epa_size_classes=["Vans"])
        apply(classify_catalog())

    def as_helper(self):
        self.client.force_login(self.helper_user)


class PermissionTests(CatalogTestCase):
    def screens(self):
        return [
            reverse("catalog"), f"{reverse('catalog')}?model_id={self.rav4.pk}&year=2019", reverse("rules"), reverse("rule-new"),
            reverse("rule-edit", args=[self.small.pk]), reverse("vehicle-classes"), reverse("vehicle-class", args=[self.crossover.pk]),
            reverse("review-queue"), f"{reverse('catalog-makes')}?year=2019",
        ]

    def test_signed_out_every_screen_sends_you_to_sign_in(self):
        client = Client(headers=TAILNET)
        for url in self.screens():
            with self.subTest(url=url):
                response = client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("sign-in"), response["Location"])
        self.assertEqual(client.post(reverse("review-act"), {"do": "photo"}).status_code, 302)

    def test_every_signed_in_user_can_look(self):
        self.as_helper()
        for url in self.screens():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_only_a_manager_changes_anything(self):
        self.as_helper()
        override = ModelOverride.objects.create(vehicle_model=self.rav4, vehicle_class=self.midsize)
        decision = ReviewDecision.objects.create(vehicle_model=self.odd, year=2019)
        queued = classified(self.straddler, 2018)
        posts = [
            (reverse("model-override", args=[self.rav4.pk]), {"vehicle_class": self.midsize.pk}),
            (reverse("override-clear", args=[override.pk]), {}),
            (reverse("third-row", args=[self.rav4.pk]), {"flag": "always"}),
            (reverse("decision-clear", args=[decision.pk]), {}),
            (reverse("rule-new"), {"name": "New", "position": 5, "vehicle_class": self.midsize.pk, "active": "on", "condition_rows": 1, "fact-0": "make", "values-0": "Toyota"}),
            (reverse("rule-action", args=[self.small.pk]), {"action": "toggle"}),
            (reverse("vehicle-class", args=[self.crossover.pk]), {"size_variant_measures": "none", "booking": "online", "photo_card": "x"}),
            (reverse("review-act"), {"do": f"photo:{queued.pk}"}),
            (reverse("vehicle-override", args=[self.vehicle.pk]), {"override-vehicle_class": self.midsize.pk}),
        ]
        for url, data in posts:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, data).status_code, 403)
        self.assertEqual(ClassificationRule.objects.count(), 2)
        self.assertTrue(ModelOverride.objects.filter(pk=override.pk).exists())
        self.assertTrue(classified(self.straddler, 2018).in_review)
        self.assertEqual(VehicleClass.objects.get(pk=self.crossover.pk).size_variant_measures, "seats")
        self.assertFalse(ClassificationChange.objects.exists())

    def test_a_helper_sees_no_controls_to_change(self):
        self.as_helper()
        page = self.client.get(f"{reverse('catalog')}?model_id={self.rav4.pk}&year=2019")
        self.assertContains(page, "Only a manager can change overrides.")
        self.assertNotContains(page, "Set an override")
        self.assertNotContains(self.client.get(reverse("rules")), "Add a rule")
        self.assertNotContains(self.client.get(reverse("review-queue")), 'name="selected"')


class LookupScreenTests(CatalogTestCase):
    def test_year_make_and_model_show_the_class_facts_and_how(self):
        page = self.client.get(reverse("catalog"), {"year": 2019, "make": "toyota", "model": "rav-4"})
        self.assertContains(page, "2019 Toyota RAV4")
        self.assertContains(page, "<strong>Medium</strong>", html=False)
        self.assertContains(page, "two rows")
        self.assertContains(page, "Fixed price list")
        self.assertContains(page, "rule 20: EPA small SUVs")
        for source in ("EPA FuelEconomy.gov", "Third-row seating list", "NHTSA vPIC Canadian specifications"):
            self.assertContains(page, source)
        self.assertContains(page, "3,400 to 3,700 lb")

    def test_the_lists_narrow_by_year_and_make(self):
        self.assertContains(self.client.get(reverse("catalog-makes"), {"year": 2019}), '<option value="Toyota">')
        self.assertNotContains(self.client.get(reverse("catalog-makes"), {"year": 2018}), "Toyota")
        models = self.client.get(reverse("catalog-models"), {"year": 2019, "make": "Test"})
        self.assertContains(models, '<option value="Odd">')
        self.assertNotContains(models, "RAV4")

    def test_a_vehicle_not_in_the_catalog_gets_the_photo_cards(self):
        self.assertContains(self.client.get(reverse("catalog"), {"year": 2019, "make": "Toyota", "model": "Nothing"}), "photo cards")
        self.assertContains(self.client.get(reverse("catalog"), {"year": 1975, "make": "Ford", "model": "Bronco"}), "The catalog starts in 1984")

    def test_a_test_price_from_the_pricebook(self):
        two_rows = self.crossover.size_variants.get(value=2)
        page = self.client.post(reverse("catalog-price"), {
            "service": self.full_detail.pk, "vehicle_class": self.crossover.pk, "size_variant": two_rows.pk, "condition_level": 1,
        })
        self.assertContains(page, "$250.00")
        self.assertContains(page, "nothing is saved")


class RulePreviewTests(CatalogTestCase):
    def new_rule(self, **changes):
        data = {
            "name": "Toyotas are midsize", "position": 5, "vehicle_class": self.midsize.pk, "active": "on", "note": "",
            "condition_rows": 3, "fact-0": "make", "values-0": "Toyota", "fact-1": "", "fact-2": "",
        }
        data.update(changes)
        return data

    def test_the_rule_list_is_in_plain_words(self):
        page = self.client.get(reverse("rules"))
        self.assertContains(page, "EPA size class Small Sport Utility Vehicle 2WD or Small Sport Utility Vehicle 4WD and curb weight over 4,500 lb → Large")

    def test_saving_shows_the_preview_and_changes_nothing(self):
        page = self.client.post(reverse("rule-new"), self.new_rule())
        self.assertContains(page, "Preview")
        self.assertContains(page, "Medium → Large")
        self.assertContains(page, "1 model year of 1 model")
        self.assertContains(page, "Toyota RAV4 2019: Medium (two rows) -&gt; Large (two rows)")
        self.assertEqual(ClassificationRule.objects.count(), 2)
        self.assertEqual(classified(self.rav4).vehicle_class, self.crossover)
        self.assertFalse(ClassificationChange.objects.exists())

    def test_confirming_the_preview_saves_and_applies_it_and_it_shows_in_the_models_history(self):
        page = self.client.post(reverse("rule-new"), self.new_rule())
        fingerprint = re.search(r'name="fingerprint" value="([0-9a-f]+)"', page.content.decode()).group(1)
        response = self.client.post(reverse("rule-new"), {**self.new_rule(), "confirm": "1", "fingerprint": fingerprint})
        self.assertRedirects(response, reverse("rules"))
        rule = ClassificationRule.objects.get(name="Toyotas are midsize")
        self.assertEqual(rule.conditions, {"make": ["Toyota"]})
        self.assertEqual((classified(self.rav4).vehicle_class, classified(self.rav4).rule), (self.midsize, rule))
        change = ClassificationChange.objects.get(kind=ClassificationChange.Kind.RULE)
        self.assertEqual(change.made_by, self.owner_user)
        history = self.client.get(f"{reverse('catalog')}?model_id={self.rav4.pk}&year=2019")
        self.assertContains(history, "Add rule 5 (Toyotas are midsize)")
        self.assertContains(history, "2019: Medium (two rows) -&gt; Large (two rows)")
        self.assertContains(history, "owner")

    def test_a_preview_that_no_longer_matches_is_shown_again(self):
        response = self.client.post(reverse("rule-new"), {**self.new_rule(), "confirm": "1", "fingerprint": "stale"})
        self.assertContains(response, "The catalog changed since that preview")
        self.assertFalse(ClassificationRule.objects.filter(name="Toyotas are midsize").exists())

    def test_a_bad_condition_is_refused_before_the_preview(self):
        page = self.client.post(reverse("rule-new"), self.new_rule(**{"fact-0": "curb_weight", "low-0": "heavy"}))
        self.assertContains(page, "curb weight: enter a number.")
        page = self.client.post(reverse("rule-new"), self.new_rule(**{"fact-0": "year", "low-0": "", "high-0": ""}))
        self.assertContains(page, "needs at least one end of the range")
        self.assertEqual(ClassificationRule.objects.count(), 2)

    def test_editing_a_rule_keeps_its_conditions_in_rows(self):
        page = self.client.get(reverse("rule-edit", args=[self.heavy.pk]))
        self.assertContains(page, "Small Sport Utility Vehicle 2WD\nSmall Sport Utility Vehicle 4WD</textarea>")
        self.assertContains(page, 'name="low-1" value="4500"')

    def test_disabling_and_moving_a_rule_are_previewed_too(self):
        page = self.client.post(reverse("rule-action", args=[self.small.pk]), {"action": "toggle"})
        self.assertContains(page, "Disable rule 20 (EPA small SUVs)")
        self.assertContains(page, "enters the review queue")
        self.assertTrue(ClassificationRule.objects.get(pk=self.small.pk).active)
        fingerprint = re.search(r'name="fingerprint" value="([0-9a-f]+)"', page.content.decode()).group(1)
        self.client.post(reverse("rule-action", args=[self.small.pk]), {"action": "toggle", "confirm": "1", "fingerprint": fingerprint})
        self.assertFalse(ClassificationRule.objects.get(pk=self.small.pk).active)
        self.assertTrue(classified(self.rav4).in_review)

        page = self.client.post(reverse("rule-action", args=[self.small.pk]), {"action": "up"})
        self.assertContains(page, "Move rule 20 (EPA small SUVs) up, to position 4")
        self.assertEqual(ClassificationRule.objects.get(pk=self.small.pk).position, 20)


class ClassSettingsTests(CatalogTestCase):
    def data(self, **changes):
        data = {"size_variant_measures": "seats", "booking": "online", "photo_card": self.crossover.photo_card}
        data.update(changes)
        return data

    def test_a_change_to_what_the_size_measures_is_previewed_then_applied(self):
        url = reverse("vehicle-class", args=[self.crossover.pk])
        page = self.client.post(url, self.data(size_variant_measures="doors"))
        self.assertContains(page, "Medium → Medium")
        self.assertContains(page, "(two rows) -&gt; Medium (ask)")
        self.assertEqual(VehicleClass.objects.get(pk=self.crossover.pk).size_variant_measures, "seats")
        fingerprint = re.search(r'name="fingerprint" value="([0-9a-f]+)"', page.content.decode()).group(1)
        self.assertRedirects(self.client.post(url, {**self.data(size_variant_measures="doors"), "confirm": "1", "fingerprint": fingerprint}), reverse("vehicle-classes"))
        self.assertEqual(VehicleClass.objects.get(pk=self.crossover.pk).size_variant_measures, "doors")
        self.assertTrue(classified(self.rav4).ask_size)
        self.assertTrue(ClassificationChange.objects.filter(kind=ClassificationChange.Kind.CLASS_SETTING, effects__vehicle_model=self.rav4).exists())

    def test_a_booking_change_shows_which_model_years_it_reaches(self):
        page = self.client.post(reverse("vehicle-class", args=[self.crossover.pk]), self.data(booking="quote"))
        self.assertContains(page, "1 model year would be asked for a quote instead of booked online.")
        self.assertContains(page, "Toyota RAV4 2019")
        self.assertEqual(VehicleClass.objects.get(pk=self.crossover.pk).booking, "online")

    def test_a_caption_saves_at_once(self):
        response = self.client.post(reverse("vehicle-class", args=[self.crossover.pk]), self.data(photo_card="Small SUVs and wagons"))
        self.assertRedirects(response, reverse("vehicle-classes"))
        self.assertEqual(VehicleClass.objects.get(pk=self.crossover.pk).photo_card, "Small SUVs and wagons")
        self.assertEqual(ClassificationChange.objects.get().made_by, self.owner_user)


class ReviewQueueScreenTests(CatalogTestCase):
    def test_the_queue_lists_newest_years_first_with_reasons_facts_and_suggestions(self):
        page = self.client.get(reverse("review-queue"))
        text = page.content.decode()
        self.assertLess(text.index("2019 Test Odd"), text.index("2018 Test Straddler"))
        self.assertContains(page, "no rule matches")
        self.assertContains(page, "its range, 4300 to 4700, spans it")
        self.assertContains(page, "Curb weight 4,300 to 4,700 lb")
        self.assertContains(page, "Suggested: <strong>Large (two rows)</strong>", html=False)
        self.assertContains(page, "No suggestion")

    def test_filters_by_year_and_reason(self):
        self.assertNotContains(self.client.get(reverse("review-queue"), {"year": 2018}), "2019 Test Odd")
        page = self.client.get(reverse("review-queue"), {"reason": "no_rule"})
        self.assertContains(page, "2019 Test Odd")
        self.assertNotContains(page, "2018 Test Straddler")

    def test_one_tap_accepts_the_suggestion(self):
        queued = classified(self.straddler, 2018)
        response = self.client.post(reverse("review-act"), {"do": f"accept:{queued.pk}", "next": reverse("review-queue")})
        self.assertRedirects(response, reverse("review-queue"))
        row = classified(self.straddler, 2018)
        self.assertEqual((row.in_review, row.vehicle_class, row.ask_size), (False, self.midsize, False))
        self.assertEqual(ReviewDecision.objects.get().decided_by, self.owner_user)

    def test_pick_another_class_and_set_the_size(self):
        queued = classified(self.odd)
        three_rows = self.midsize.size_variants.get(value=3)
        self.client.post(reverse("review-act"), {"do": f"pick:{queued.pk}", f"class-{queued.pk}": self.midsize.pk, f"size-{queued.pk}": three_rows.pk})
        row = classified(self.odd)
        self.assertEqual((row.vehicle_class, row.size_variant, row.method), (self.midsize, three_rows, "decision"))
        # A size of another class is refused.
        queued = classified(self.straddler, 2018)
        self.client.post(reverse("review-act"), {"do": f"pick:{queued.pk}", f"class-{queued.pk}": self.crossover.pk, f"size-{queued.pk}": three_rows.pk})
        self.assertTrue(classified(self.straddler, 2018).in_review)
        # Or always ask it.
        self.client.post(reverse("review-act"), {"do": f"pick:{queued.pk}", f"class-{queued.pk}": self.crossover.pk, f"size-{queued.pk}": "ask"})
        self.assertTrue(classified(self.straddler, 2018).ask_size)

    def test_many_at_once_to_their_suggestions_or_the_photo_cards(self):
        picked = [classified(self.straddler, 2018).pk, classified(self.odd).pk]
        response = self.client.post(reverse("review-act"), {"do": "accept", "selected": picked, "note": "Older vehicles"}, follow=True)
        self.assertContains(response, "Settled 1 model year. 1 had no suggestion to accept and wait in the queue.")
        self.assertFalse(classified(self.straddler, 2018).in_review)
        self.assertTrue(classified(self.odd).in_review)
        self.client.post(reverse("review-act"), {"do": "photo", "selected": [classified(self.odd).pk]})
        row = classified(self.odd)
        self.assertEqual((row.in_review, row.method, row.vehicle_class), (False, "photo_cards", None))
        self.assertEqual(ModelYearClassification.objects.filter(in_review=True).count(), 0)
        change = ClassificationChange.objects.filter(kind=ClassificationChange.Kind.DECISION).last()
        self.assertIn("Note: Older vehicles", change.summary)

    def test_the_home_screen_counts_the_queue_while_it_is_not_empty(self):
        self.assertContains(self.client.get(reverse("schedule")), "2 model years wait in the vehicle review queue")
        self.client.post(reverse("review-act"), {"do": "photo", "selected": [row.pk for row in ModelYearClassification.objects.filter(in_review=True)]})
        self.assertNotContains(self.client.get(reverse("schedule")), "review queue")


class OverrideScreenTests(CatalogTestCase):
    def url(self):
        return f"{reverse('catalog')}?model_id={self.rav4.pk}&year=2019"

    def test_set_and_clear_a_model_override_with_a_note(self):
        response = self.client.post(reverse("model-override", args=[self.rav4.pk]), {
            "vehicle_class": self.midsize.pk, "size": "ask", "year_from": "", "year_to": "", "note": "Checked on site", "year": 2019,
        })
        self.assertRedirects(response, self.url())
        override = ModelOverride.objects.get()
        self.assertEqual((override.vehicle_class, override.ask_size, override.set_by, override.note), (self.midsize, True, self.owner_user, "Checked on site"))
        self.assertEqual(classified(self.rav4).method, "override")
        page = self.client.get(self.url())
        self.assertContains(page, "Set by owner")
        self.assertContains(page, "Note: Checked on site")
        self.client.post(reverse("override-clear", args=[override.pk]), {"year": 2019})
        self.assertFalse(ModelOverride.objects.exists())
        self.assertEqual(classified(self.rav4).method, "rule")

    def test_a_size_of_another_class_is_refused(self):
        three_rows = self.midsize.size_variants.get(value=3)
        self.client.post(reverse("model-override", args=[self.rav4.pk]), {"vehicle_class": self.crossover.pk, "size": three_rows.pk})
        self.assertFalse(ModelOverride.objects.exists())

    def test_the_third_row_flag(self):
        self.client.post(reverse("third-row", args=[self.rav4.pk]), {"flag": "always", "year_from": 2019, "year_to": 2019})
        self.assertEqual(classified(self.rav4).size_variant.value, 3)
        self.assertContains(self.client.get(self.url()), "Set the third-row flag to always")

    def test_a_vehicle_override_on_the_customers_vehicle_screen(self):
        self.vehicle.vehicle_model = self.rav4
        self.vehicle.save()
        page = self.client.get(reverse("vehicle-edit", args=[self.vehicle.pk]))
        self.assertContains(page, "The catalog gives the 2019 Toyota RAV4")
        self.client.post(reverse("vehicle-override", args=[self.vehicle.pk]), {
            "override-vehicle_class": self.midsize.pk, "override-size_variant": self.midsize.size_variants.get(value=3).pk, "override-note": "Lifted",
        })
        self.vehicle.refresh_from_db()
        self.assertTrue(self.vehicle.class_overridden)
        self.assertEqual((self.vehicle.vehicle_class, self.vehicle.class_override_by, self.vehicle.class_override_note), (self.midsize, self.owner_user, "Lifted"))
        self.assertContains(self.client.get(self.url()), "Customers' vehicles with their own class")
        self.client.post(reverse("vehicle-override", args=[self.vehicle.pk]), {"clear": "1"})
        self.vehicle.refresh_from_db()
        self.assertFalse(self.vehicle.class_overridden)
        self.assertEqual(ClassificationChange.objects.filter(kind=ClassificationChange.Kind.VEHICLE_OVERRIDE, vehicle_model=self.rav4).count(), 2)
