"""The differences screen and the approval list (decisions 0077 and 0083):
the three choices for a vehicle whose class differs from the catalog's, a
vehicle left in a retired class, who may change anything, what the approval
list holds, recording who approved what and when, and approvals cleared by
a later change."""

import datetime
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone

from appointments.models import Appointment, AppointmentLine
from vehicles.classification import approvals, owner
from vehicles.classification.engine import apply, classify_catalog
from vehicles.models import ClassificationChange, ModelApproval, ModelOverride, Vehicle

from .test_catalog import SMALL_SUVS, CatalogTestCase, add_facts, add_model, classified


class DifferencesTestCase(CatalogTestCase):
    """The customer's 2019 RAV4 was imported as a Large with three
    rows; the catalog says Medium, two rows. A second RAV4,
    imported as the catalog has it, shows what a per-model override does."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.three_rows = cls.midsize.size_variants.get(value=3)
        Vehicle.objects.filter(pk=cls.vehicle.pk).update(vehicle_model=cls.rav4, vehicle_class=cls.midsize, size_variant=cls.three_rows)
        cls.vehicle.refresh_from_db()
        cls.other = Vehicle.objects.create(
            customer=cls.customer, year=2019, make="Toyota", model="RAV4", color="red", vehicle_model=cls.rav4,
            vehicle_class=cls.crossover, size_variant=cls.two_rows,
        )
        cls.past = Appointment.objects.create(
            customer=cls.customer, vehicle=cls.vehicle, scheduled_start=timezone.make_aware(datetime.datetime(2025, 5, 1, 9)),
            status=Appointment.Status.COMPLETED, source=Appointment.Source.IMPORT,
        )
        AppointmentLine.objects.create(
            appointment=cls.past, kind=AppointmentLine.Kind.SERVICE, description="Full Detail", amount=Decimal("300.00"),
            vehicle_class=cls.midsize, vehicle_class_name="Large", size_variant=cls.three_rows, size_variant_value=3,
        )

    def act(self, choice, vehicle=None, **data):
        return self.client.post(reverse("difference-act", args=[(vehicle or self.vehicle).pk]), {"do": choice, **data})


class DifferencesScreenTests(DifferencesTestCase):
    def test_the_screen_lists_each_vehicle_that_differs_with_the_three_choices(self):
        response = self.client.get(reverse("differences"))
        self.assertContains(response, "2019 Toyota RAV4, blue")
        self.assertNotContains(response, "2019 Toyota RAV4, red")
        self.assertContains(response, "Large (three rows)")
        self.assertContains(response, "Medium (two rows)")
        for choice in ("keep", "accept", "model"):
            self.assertContains(response, f'value="{choice}"')

    def test_keep_imported_sets_a_per_vehicle_override(self):
        self.act("keep", note="Lifted")
        self.vehicle.refresh_from_db()
        self.assertTrue(self.vehicle.class_overridden)
        self.assertEqual((self.vehicle.vehicle_class, self.vehicle.size_variant), (self.midsize, self.three_rows))
        self.assertEqual((self.vehicle.class_override_by, self.vehicle.class_override_note), (self.owner_user, "Lifted"))
        self.assertEqual(self.client.get(reverse("differences")).context["rows"], [])
        self.assertEqual(ClassificationChange.objects.get().kind, ClassificationChange.Kind.VEHICLE_OVERRIDE)

    def test_accept_gives_the_vehicle_the_catalogs_class_and_leaves_past_jobs_alone(self):
        self.act("accept")
        self.vehicle.refresh_from_db()
        self.assertEqual((self.vehicle.vehicle_class, self.vehicle.size_variant), (self.crossover, self.two_rows))
        self.assertFalse(self.vehicle.class_overridden)
        line = self.past.lines.get()
        self.assertEqual((line.vehicle_class, line.vehicle_class_name, line.amount), (self.midsize, "Large", Decimal("300.00")))
        change = ClassificationChange.objects.get()
        self.assertEqual((change.kind, change.made_by, change.vehicle_model), (ClassificationChange.Kind.VEHICLE_CLASS, self.owner_user, self.rav4))
        self.assertNotIn("Example", change.summary)

    def test_a_per_model_override_gives_every_vehicle_of_the_model_this_class(self):
        self.act("model")
        override = ModelOverride.objects.get(vehicle_model=self.rav4)
        self.assertEqual((override.vehicle_class, override.year_from, override.year_to, override.set_by), (self.midsize, 2019, 2019, self.owner_user))
        # The class differed, so the size comes from the facts: two rows, from the third-row list.
        self.assertIsNone(override.size_variant)
        self.assertEqual(classified(self.rav4).vehicle_class, self.midsize)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.vehicle_class, self.midsize)
        # The blue RAV4 still differs in size (the facts give two rows), and the
        # red one, imported as the catalog had it, now differs in class.
        rows = self.client.get(reverse("differences")).context["rows"]
        self.assertEqual([row["difference"].vehicle for row in rows], [self.vehicle, self.other])

    def test_a_vehicle_that_no_longer_differs_is_left_alone(self):
        self.act("accept")
        self.act("keep")
        self.vehicle.refresh_from_db()
        self.assertFalse(self.vehicle.class_overridden)

    def test_only_a_manager_chooses(self):
        self.as_helper()
        self.assertEqual(self.client.get(reverse("differences")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("differences")), 'value="accept"')
        for choice in ("keep", "accept", "model"):
            self.assertEqual(self.act(choice).status_code, 403)
        self.vehicle.refresh_from_db()
        self.assertEqual(self.vehicle.vehicle_class, self.midsize)
        self.assertFalse(ModelOverride.objects.exists())


class ApprovalListTests(DifferencesTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # A model near the 580 cu ft line, whose years are in two classes:
        # 2018 by the weight rule, 2019 by the small SUV rule.
        cls.mixed = add_model("Test", "Mixed", 2018, 2019)
        measured = {"length_min": 231.2, "length_max": 231.2, "width_min": 72, "width_max": 72, "height_min": 60, "height_max": 60}
        add_facts(cls.mixed, year=2018, epa_size_classes=SMALL_SUVS)
        add_facts(cls.mixed, year=2018, source="canada", curb_weight_min=4800, curb_weight_max=4900, **measured)
        add_facts(cls.mixed, year=2019, epa_size_classes=SMALL_SUVS)
        add_facts(cls.mixed, year=2019, source="canada", **measured)
        # The older Tahoe is on the spot-check list; only its years to 2006 show.
        cls.tahoe = add_model("Chevrolet", "Tahoe", 2005, 2008)
        for year in (2005, 2006):
            add_facts(cls.tahoe, year=year, epa_size_classes=SMALL_SUVS)
        for year in (2007, 2008):
            add_facts(cls.tahoe, year=year, epa_size_classes=["Standard Sport Utility Vehicle 4WD"])
        apply(classify_catalog())

    def listed(self):
        found, _ = approvals.approval_list()
        return {item.vehicle_model: item for item in found}

    def approve(self, vehicle_model, first, last, **data):
        return self.client.post(reverse("approval-act"), {"do": f"approve:{vehicle_model.pk}:{first}-{last}", **data})

    def test_the_list_holds_the_job_history_the_spot_checks_and_the_near_line_models(self):
        listed = self.listed()
        self.assertTrue(any(reason.startswith(approvals.JOB_HISTORY) for reason in listed[self.rav4].reasons))
        self.assertEqual(listed[self.mixed].reasons, ["near a line: 2018-2019 at 578.0 cu ft, near the 580 cu ft line (Medium | Large)"])
        self.assertNotIn(self.odd, listed)
        tahoe = listed[self.tahoe]
        self.assertEqual(tahoe.reasons, ["spot-check list (to 2006)"])
        self.assertEqual([(found.first, found.last) for found in tahoe.ranges], [(2005, 2006)])
        ranges = listed[self.mixed].ranges
        self.assertEqual([(found.first, found.last, found.vehicle_class) for found in ranges], [(2018, 2018, self.midsize), (2019, 2019, self.crossover)])
        self.assertEqual(ranges[1].how, "rule 20: EPA small SUVs")
        # A size-based class is two rows unless the third-row data says otherwise.
        self.assertEqual(ranges[1].size, "two rows")

    def test_each_model_shows_once_with_its_ranges(self):
        response = self.client.get(reverse("approvals"))
        self.assertContains(response, "Test Mixed", count=1)
        self.assertContains(response, "rule 10: Small SUVs over 4,500 lb")
        self.assertContains(response, f'value="approve:{self.mixed.pk}:2018-2018"')

    def test_approving_records_who_and_when(self):
        self.approve(self.mixed, 2018, 2018, **{f"note-{self.mixed.pk}:2018-2018": "Checked the weight"})
        approval = ModelApproval.objects.get()
        self.assertEqual((approval.approved_by, approval.note, approval.vehicle_class), (self.owner_user, "Checked the weight", self.midsize))
        self.assertIsNotNone(approval.approved_at)
        self.assertEqual(ClassificationChange.objects.get().kind, ClassificationChange.Kind.APPROVAL)
        self.assertFalse(self.listed()[self.mixed].approved)
        self.approve(self.mixed, 2019, 2019)
        self.assertTrue(self.listed()[self.mixed].approved)
        shown = lambda url: [item.vehicle_model for item in self.client.get(url).context["page"].object_list]  # noqa: E731
        self.assertNotIn(self.mixed, shown(reverse("approvals")))
        self.assertIn(self.mixed, shown(reverse("approvals") + "?show=approved"))

    def test_a_rule_change_that_alters_an_approved_range_clears_it(self):
        self.approve(self.mixed, 2018, 2018)
        self.approve(self.mixed, 2019, 2019)
        self.approve(self.rav4, 2019, 2019)
        # Moving the weight line to 5,000 lb sends the 2018 Mixed to the small SUV rule.
        self.heavy.conditions = {"epa_size_class": SMALL_SUVS, "curb_weight": {"over": 5000}}
        owner.save_rules([self.heavy], "Move the weight line", self.owner_user)
        # Both years are now Medium; it stays on the list, near the line.
        mixed = self.listed()[self.mixed]
        self.assertTrue(mixed.reasons[0].startswith(approvals.NEAR_LINE))
        self.assertFalse(mixed.approved)
        self.assertEqual([(found.first, found.last) for found in mixed.ranges], [(2018, 2019)])
        cleared = ModelApproval.objects.exclude(cleared_at=None)
        self.assertEqual(cleared.count(), 2)
        self.assertEqual({approval.cleared_by.summary for approval in cleared}, {"Move the weight line"})
        self.assertEqual(mixed.ranges[0].cleared.cleared_by.summary, "Move the weight line")
        # The RAV4 was not touched, so it stays approved.
        self.assertTrue(self.listed()[self.rav4].approved)
        self.assertContains(self.client.get(reverse("approvals")), "cleared on")

    def test_an_override_on_an_approved_model_clears_it(self):
        self.approve(self.rav4, 2019, 2019)
        owner.set_override(self.rav4, self.owner_user, self.crossover, self.two_rows)
        # Same class, but now reached by a model override with a fixed size.
        self.assertFalse(self.listed()[self.rav4].approved)
        self.assertIsNotNone(ModelApproval.objects.get().cleared_at)

    def test_a_change_that_does_not_reach_the_model_keeps_its_approval(self):
        self.approve(self.rav4, 2019, 2019)
        owner.set_override(self.mixed, self.owner_user, self.midsize)
        self.assertTrue(self.listed()[self.rav4].approved)

    def test_change_sets_an_override_for_the_range_and_approves_it(self):
        target = f"{self.mixed.pk}:2019-2019"
        size = self.midsize.size_variants.get(value=2)
        self.client.post(reverse("approval-act"), {"do": f"change:{target}", f"class-{target}": self.midsize.pk, f"size-{target}": size.pk})
        override = ModelOverride.objects.get(vehicle_model=self.mixed)
        self.assertEqual((override.year_from, override.year_to, override.vehicle_class, override.size_variant), (2019, 2019, self.midsize, size))
        approval = ModelApproval.objects.get(cleared_at=None)
        self.assertEqual((approval.year_from, approval.year_to, approval.vehicle_class, approval.approved_by), (2019, 2019, self.midsize, self.owner_user))

    def test_a_range_that_changed_since_the_screen_was_shown_is_refused(self):
        response = self.approve(self.mixed, 2018, 2019)
        self.assertFalse(ModelApproval.objects.exists())
        self.assertRedirects(response, reverse("approvals"), fetch_redirect_response=False)

    def test_a_range_in_the_review_queue_cannot_be_approved(self):
        apply(classify_catalog())
        self.approve(self.straddler, 2018, 2018)
        self.assertFalse(ModelApproval.objects.exists())

    def test_only_a_manager_approves_or_changes(self):
        self.as_helper()
        self.assertEqual(self.client.get(reverse("approvals")).status_code, 200)
        self.assertEqual(self.approve(self.mixed, 2018, 2018).status_code, 403)
        self.assertFalse(ModelApproval.objects.exists())


class RetiredClassTests(DifferencesTestCase):
    """A vehicle left in a retired class when the size-based classes were applied."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from vehicles.models import VehicleClass

        cls.old = VehicleClass.objects.get(name="Fullsize SUVs & Minivans")
        cls.minivan = Vehicle.objects.create(customer=cls.customer, make="Honda", model="Odyssey EX", vehicle_class=cls.old)

    def test_the_screen_proposes_a_class_and_the_owner_picks_one(self):
        page = self.client.get(reverse("differences"))
        self.assertContains(page, "Left in a retired class")
        self.assertContains(page, "a minivan, proposed from its recorded class")
        response = self.client.post(reverse("retired-act", args=[self.minivan.pk]), {"vehicle_class": self.midsize.pk, "note": "Checked"})
        self.assertRedirects(response, reverse("differences"))
        self.minivan.refresh_from_db()
        self.assertEqual(self.minivan.vehicle_class, self.midsize)
        self.assertEqual(ClassificationChange.objects.get().kind, ClassificationChange.Kind.VEHICLE_CLASS)
        self.assertNotContains(self.client.get(reverse("differences")), "Left in a retired class")

    def test_only_a_manager_picks(self):
        self.as_helper()
        self.assertEqual(self.client.post(reverse("retired-act", args=[self.minivan.pk]), {"vehicle_class": self.midsize.pk}).status_code, 403)
