"""The monthly vehicle data refresh (Phase 2 Step 5, decision 0081): what a
refresh may change on its own, what it holds in the review queue with the
old and new values, models a source stops listing, and refresh_vehicle_data's
record and summary. Nothing touches the network."""

import contextlib
import datetime
import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment
from control.tests import TailnetClient
from customers.models import Customer
from vehicles.classification import approvals, owner
from vehicles.classification.engine import apply, classify_catalog
from vehicles.models import (
    ClassificationChange,
    ModelApproval,
    ModelOverride,
    ModelYearClassification,
    Vehicle,
    VehicleDataRefresh,
    VehicleModel,
    VehicleModelYear,
)
from vehicles.test_classification import SMALL_SUVS, ClassificationTestCase, add_facts, add_model, classified
from vehicles.test_vehicle_data import CONFIG, CachedFixtures, no_network, write_epa_zip
from vehicles.vehicle_data.fetch import Fetcher

Source = VehicleModelYear.Source
Kind = ModelYearClassification.ReviewKind
STANDARD_SUVS = ["Standard Sport Utility Vehicle 4WD"]


def refresh_classes():
    out = io.StringIO()
    call_command("classify_vehicles", "--refresh", stdout=out)
    return out.getvalue()


class HoldTestCase(ClassificationTestCase):
    """Small SUVs are Crossovers & Wagons and standard ones Midsize SUVs, both
    sized by seat rows. Four made-up models start as two-row Crossovers &
    Wagons: one with nothing to protect it, one with a model override for
    other years, one approved on the approval list, and one in the job
    history. Rules 1 and 2 come before every launch rule classify_vehicles
    loads, and made-up names keep the third-row list off the models, so
    their seat rows come from vPIC."""

    client_class = TailnetClient

    def setUp(self):
        self.rule(1, {"epa_size_class": SMALL_SUVS}, "Crossovers & Wagons", name="small SUVs")
        self.rule(2, {"epa_size_class": STANDARD_SUVS}, "Midsize SUVs", name="standard SUVs")
        self.free = self.suv("Free")
        self.overridden = self.suv("Overridden")
        ModelOverride.objects.create(
            vehicle_model=self.overridden, year_from=2010, year_to=2015, vehicle_class=self.vehicle_class("Midsize SUVs")
        )
        self.approved = self.suv("Approved")
        self.driven = self.suv("Driven")
        customer = Customer.objects.create(first_name="Pat")
        vehicle = Vehicle.objects.create(customer=customer, vehicle_model=self.driven, year=2019, make="Acme", model="Driven")
        Appointment.objects.create(
            customer=customer, vehicle=vehicle, scheduled_start=timezone.make_aware(datetime.datetime(2025, 6, 1, 9)),
            status=Appointment.Status.COMPLETED,
        )
        apply(classify_catalog())
        approvals.approve(self.approved, 2019, 2019, None)
        self.crossover = self.vehicle_class("Crossovers & Wagons")
        self.midsize = self.vehicle_class("Midsize SUVs")

    def suv(self, name, year=2019, size_classes=SMALL_SUVS, rows=(2,)):
        vehicle_model = VehicleModel.objects.filter(make="Acme", model=name).first() or add_model("Acme", name, year_from=year, year_to=year)
        add_facts(vehicle_model, year=year, epa_size_classes=size_classes)
        add_facts(vehicle_model, Source.VPIC, year=year, seat_rows=list(rows))
        return vehicle_model

    def new_facts(self, vehicle_model, year=2019, **fields):
        VehicleModelYear.objects.filter(vehicle_model=vehicle_model, year=year, source=Source.EPA).update(**fields)

    def assert_live(self, vehicle_model, vehicle_class, rows, in_review=False, year=2019):
        found = classified(vehicle_model, year)
        self.assertEqual(
            (found.vehicle_class, found.size_variant, found.in_review),
            (vehicle_class, self.size(vehicle_class.name, rows), in_review),
        )
        return found


class WhatARefreshChangesOnItsOwnTests(HoldTestCase):
    def test_a_model_with_nothing_to_protect_it_takes_the_new_class(self):
        self.new_facts(self.free, epa_size_classes=STANDARD_SUVS)
        refresh_classes()
        self.assert_live(self.free, self.midsize, 2)

    def test_new_models_and_model_years_go_live_when_the_rules_classify_them_cleanly(self):
        added = self.suv("Added")
        self.suv("Driven", year=2020)
        refresh_classes()
        self.assert_live(added, self.crossover, 2)
        # A new year of a model in the job history is an addition, not a change.
        self.assert_live(self.driven, self.crossover, 2, year=2020)

    def test_a_new_model_year_no_rule_settles_waits_in_the_queue_with_no_class(self):
        self.suv("Driven", year=2020, size_classes=["Special Purpose Vehicle 4WD"])
        refresh_classes()
        found = classified(self.driven, 2020)
        self.assertEqual((found.vehicle_class, found.in_review), (None, True))

    def test_updated_facts_that_leave_the_class_alone_change_nothing(self):
        self.new_facts(self.driven, drives=["All-Wheel Drive"])
        refresh_classes()
        self.assert_live(self.driven, self.crossover, 2)


class WhatARefreshHoldsTests(HoldTestCase):
    def test_a_protected_models_class_change_waits_with_the_old_and_new_values(self):
        for vehicle_model in (self.overridden, self.approved, self.driven):
            self.new_facts(vehicle_model, epa_size_classes=STANDARD_SUVS)
        out = refresh_classes()
        for vehicle_model, why in (
            (self.overridden, "it has a model override"),
            (self.approved, "it has an approval on the approval list"),
            (self.driven, "it is in the job history"),
        ):
            with self.subTest(model=vehicle_model.model):
                found = self.assert_live(vehicle_model, self.crossover, 2, in_review=True)
                self.assertEqual(found.review_kinds, [Kind.HELD])
                (reason,) = found.review_reasons
                self.assertIn("from Crossovers & Wagons (two rows) to Midsize SUVs (two rows)", reason)
                self.assertIn("rule 2: standard SUVs", reason)
                self.assertIn(why, reason)
                self.assertEqual((found.suggested_class, found.suggested_size_variant), (self.midsize, self.size("Midsize SUVs", 2)))
        self.assertIn("Held in the review queue: the refresh may not change these on its own (3 model years)", out)
        self.assertIn("Acme Approved 2019: Crossovers & Wagons (two rows) -> Midsize SUVs (two rows)", out)

    def test_a_size_variant_change_is_held_too(self):
        VehicleModelYear.objects.filter(vehicle_model=self.driven, source=Source.VPIC).update(seat_rows=[3])
        refresh_classes()
        found = self.assert_live(self.driven, self.crossover, 2, in_review=True)
        self.assertIn("to Crossovers & Wagons (three rows)", found.review_reasons[0])

    def test_classify_vehicles_by_hand_applies_the_change(self):
        self.new_facts(self.driven, epa_size_classes=STANDARD_SUVS)
        call_command("classify_vehicles", stdout=io.StringIO())
        self.assert_live(self.driven, self.midsize, 2)

    def test_a_held_model_year_stays_held_after_the_hold_clears_its_approval(self):
        self.new_facts(self.approved, epa_size_classes=STANDARD_SUVS)
        refresh_classes()
        # The range now waits in the queue, so the approval list shows it again.
        self.assertIsNotNone(ModelApproval.objects.get(vehicle_model=self.approved).cleared_at)
        refresh_classes()
        found = self.assert_live(self.approved, self.crossover, 2, in_review=True)
        self.assertIn("an earlier refresh held it", found.review_reasons[0])

    def test_accepting_the_suggestion_settles_it_and_the_next_refresh_leaves_it(self):
        self.new_facts(self.driven, epa_size_classes=STANDARD_SUVS)
        refresh_classes()
        owner.decide([classified(self.driven)], get_user_model().objects.create_user("owner"), "accept")
        self.assert_live(self.driven, self.midsize, 2)
        refresh_classes()
        self.assert_live(self.driven, self.midsize, 2)

    def test_facts_that_change_back_release_the_hold(self):
        self.new_facts(self.driven, epa_size_classes=STANDARD_SUVS)
        refresh_classes()
        self.new_facts(self.driven, epa_size_classes=SMALL_SUVS)
        refresh_classes()
        self.assert_live(self.driven, self.crossover, 2)

    def test_the_review_queue_lists_held_model_years_under_their_own_reason(self):
        self.new_facts(self.driven, epa_size_classes=STANDARD_SUVS)
        refresh_classes()
        self.client.force_login(get_user_model().objects.create_user("staff"))
        response = self.client.get(reverse("review-queue"), {"reason": Kind.HELD})
        self.assertContains(response, "2019 Acme Driven")
        self.assertContains(response, "Live meanwhile: Crossovers &amp; Wagons (two rows)")
        self.assertContains(response, "Suggested: <strong>Midsize SUVs (two rows)</strong>")


class ModelsASourceStopsListingTests(CachedFixtures, TestCase):
    def test_they_are_kept_with_the_date_a_source_last_listed_them(self):
        self.run_import(["epa"])
        camry = VehicleModel.objects.get(make="Toyota", model="Camry")
        row = camry.model_years.get(source=Source.EPA)
        lines = self.epa_csv.splitlines()
        self.epa_csv = "\n".join(line for line in lines if ",Camry," not in line) + "\n"
        write_epa_zip(self.cache, self.epa_csv)
        self.run_import(["epa"])
        kept = VehicleModel.objects.get(pk=camry.pk).model_years.get(source=Source.EPA)
        self.assertEqual(kept.last_seen, row.last_seen)
        rav4 = VehicleModel.objects.get(make="Toyota", model="RAV4").model_years.get(source=Source.EPA)
        self.assertGreater(rav4.last_seen, row.last_seen)


class RefreshCommandTests(CachedFixtures, ClassificationTestCase):
    """refresh_vehicle_data runs the import with fresh downloads, then
    classify_vehicles --refresh, and records the refresh. The fixture cache
    stands in for the downloads."""

    def run_refresh(self, fail=None):
        def fetcher(cache_dir, refresh, **options):
            self.assertTrue(refresh)
            return Fetcher(self.cache, opener=no_network, sleep=lambda seconds: None)

        out = io.StringIO()
        with (
            override_settings(VEHICLE_DATA_CACHE_DIR=self.cache),
            mock.patch("vehicles.management.commands.import_vehicle_data.Fetcher", fetcher),
            mock.patch("vehicles.management.commands.import_vehicle_data.load_config", lambda: CONFIG),
            mock.patch("vehicles.management.commands.import_vehicle_data.run", side_effect=fail) if fail else contextlib.nullcontext(),
        ):
            try:
                call_command("refresh_vehicle_data", stdout=out, stderr=io.StringIO())
            finally:
                self.output = out.getvalue()
        return VehicleDataRefresh.objects.get()

    def test_a_refresh_imports_classifies_and_records_its_counts(self):
        refresh = self.run_refresh()
        self.assertEqual(refresh.result, VehicleDataRefresh.Result.SUCCEEDED)
        self.assertEqual(refresh.models_added, VehicleModel.objects.count())
        self.assertEqual(refresh.sent_to_queue, ModelYearClassification.objects.filter(in_review=True).count())
        self.assertEqual(refresh.held, 0)
        self.assertIn("APPLIED: the import was written.", self.output)
        self.assertIn("APPLIED: the classifications were saved.", self.output)
        self.assertEqual(self.output.strip().splitlines()[-1], refresh.summary)
        self.assertTrue(refresh.summary.startswith(f"Vehicle data refresh succeeded: {refresh.models_added} models added, 0 changed,"))

    def test_a_second_refresh_counts_a_model_changed_by_two_sources_once(self):
        self.run_refresh()
        VehicleDataRefresh.objects.all().delete()
        VehicleModelYear.objects.filter(source=Source.EPA).update(drives=[])
        refresh = self.run_refresh()
        self.assertEqual(refresh.models_added, 0)
        changed = VehicleModel.objects.filter(model_years__source=Source.EPA).distinct().count()
        self.assertEqual(refresh.models_changed, changed)

    def test_a_failed_import_is_recorded_and_classification_does_not_run(self):
        with self.assertRaises(CommandError):
            self.run_refresh(fail=RuntimeError("vPIC answered 503\nthree times"))
        self.assertFalse(ClassificationChange.objects.filter(kind=ClassificationChange.Kind.RUN).exists())
        refresh = VehicleDataRefresh.objects.get()
        self.assertEqual(refresh.result, VehicleDataRefresh.Result.FAILED)
        self.assertEqual(
            self.output.strip().splitlines()[-1],
            "Vehicle data refresh failed: vPIC answered 503 three times. So far: 0 models added, 0 changed,"
            " 0 model years sent to the review queue.",
        )


class HomeScreenTests(TestCase):
    client_class = TailnetClient
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user("staff"))

    def test_the_last_refresh_shows_beside_the_review_queue_count(self):
        started = timezone.make_aware(datetime.datetime(2026, 11, 1, 4, 21))
        VehicleDataRefresh.objects.create(
            started_at=started - datetime.timedelta(days=31), finished_at=started, result="failed", message="old"
        )
        VehicleDataRefresh.objects.create(
            started_at=started, finished_at=started, result="succeeded", models_added=12, models_changed=340, sent_to_queue=7, held=3
        )
        response = self.client.get(reverse("schedule"))
        self.assertContains(
            response,
            "Last vehicle data refresh: Sun, Nov 1, 4:21 AM, succeeded: 12 models added, 340 changed,"
            " 7 model years sent to the review queue (3 class changes held).",
        )

    def test_a_failed_refresh_says_why(self):
        now = timezone.now()
        VehicleDataRefresh.objects.create(started_at=now, finished_at=now, result="failed", message="NHTSA vPIC failed: timed out")
        response = self.client.get(reverse("schedule"))
        self.assertContains(response, "failed (NHTSA vPIC failed: timed out)")

    def test_nothing_shows_before_the_first_refresh(self):
        self.assertNotContains(self.client.get(reverse("schedule")), "vehicle data refresh")
