"""The vehicle size report: it changes nothing, groups model years into size
ranges, takes the median of the trims, works out box volume, and counts
customers' vehicles and completed jobs without naming anyone."""

import csv
import datetime
import io
from decimal import Decimal

from django.apps import apps
from django.core.management import call_command
from django.utils import timezone

from appointments.models import Appointment
from customers.models import Customer
from vehicles import size_report
from vehicles.models import ModelYearClassification, Vehicle
from vehicles.test_classification import SMALL_SUVS, ClassificationTestCase, Source, add_facts, add_model

Method = ModelYearClassification.Method


def spread(values):
    return [float(value) for value in values]


class SizeReportTestCase(ClassificationTestCase):
    def classify(self, vehicle_model, year, class_name=None):
        """Store a model year's class as classify_vehicles would; no class
        puts it in the review queue."""
        vehicle_class = self.vehicle_class(class_name) if class_name else None
        return ModelYearClassification.objects.create(
            vehicle_model=vehicle_model, year=year, vehicle_class=vehicle_class,
            method=Method.RULE if vehicle_class else Method.REVIEW, in_review=vehicle_class is None,
        )

    def add_year(self, vehicle_model, year, class_name, lengths=(180,), width=72, height=66, epa=SMALL_SUVS, rows=(2,), **facts):
        """One model year in a class, with the Canadian trims' lengths."""
        self.classify(vehicle_model, year, class_name)
        add_facts(vehicle_model, year=year, epa_size_classes=list(epa), **facts)
        if rows:
            add_facts(vehicle_model, Source.SEAT_LIST, year=year, seat_rows=list(rows))
        if lengths:
            add_facts(
                vehicle_model, Source.CANADA, year=year,
                length_min=min(lengths), length_max=max(lengths), width_min=width, width_max=width,
                height_min=height, height_max=height, curb_weight_min=3500, curb_weight_max=3500,
                distribution={
                    "length": spread(sorted(lengths)), "width": spread([width] * len(lengths)),
                    "height": spread([height] * len(lengths)), "curb_weight": [3500] * len(lengths),
                },
            )

    def ranges(self):
        return size_report.build()

    def run_report(self, output_format="summary"):
        out = io.StringIO()
        call_command("vehicle_size_report", "--format", output_format, stdout=out)
        return out.getvalue()


class SizeRangeTests(SizeReportTestCase):
    def test_the_median_of_the_trims_is_each_years_figure(self):
        model = add_model("Acme", "Roamer", year_from=2020, year_to=2020)
        self.add_year(model, 2020, "Crossovers & Wagons", lengths=(180, 182, 190))
        (found,) = self.ranges()
        self.assertEqual(found.measure("length"), Decimal("182.0"))
        self.assertEqual(found.trims, 3)
        self.assertEqual((found.shortest, found.longest), (Decimal("180.0"), Decimal("190.0")))

    def test_box_volume_is_length_times_width_times_height_over_1728(self):
        model = add_model("Acme", "Roamer", year_from=2020, year_to=2020)
        self.add_year(model, 2020, "Crossovers & Wagons", lengths=(180,), width=72, height=66)
        (found,) = self.ranges()
        self.assertEqual(found.box_volume, Decimal("495.0"))

    def test_years_within_one_inch_make_one_range_and_a_bigger_step_starts_another(self):
        model = add_model("Acme", "Roamer", year_from=2015, year_to=2019)
        for year, length in ((2015, 180), (2016, 180.5), (2017, 181), (2018, 181.2), (2019, 181.4)):
            self.add_year(model, year, "Crossovers & Wagons", lengths=(length,))
        found = self.ranges()
        # 2018 would spread the length 1.2 inches from 2015's.
        self.assertEqual([found_range.years_label for found_range in found], ["2015-2017", "2018-2019"])

    def test_width_or_height_alone_also_split_a_range(self):
        model = add_model("Acme", "Roamer", year_from=2015, year_to=2016)
        self.add_year(model, 2015, "Crossovers & Wagons", height=66)
        self.add_year(model, 2016, "Crossovers & Wagons", height=68)
        self.assertEqual(len(self.ranges()), 2)

    def test_a_class_change_or_a_gap_in_years_starts_a_new_range(self):
        model = add_model("Acme", "Roamer", year_from=2015, year_to=2019)
        self.add_year(model, 2015, "Crossovers & Wagons")
        self.add_year(model, 2016, "Midsize SUVs")
        self.add_year(model, 2018, "Midsize SUVs")
        self.assertEqual([found.years_label for found in self.ranges()], ["2015", "2016", "2018"])

    def test_years_with_no_dimensions_are_their_own_marked_range(self):
        model = add_model("Acme", "Roamer", year_from=2015, year_to=2017)
        self.add_year(model, 2015, "Crossovers & Wagons", lengths=())
        self.add_year(model, 2016, "Crossovers & Wagons", lengths=())
        self.add_year(model, 2017, "Crossovers & Wagons")
        first, second = self.ranges()
        self.assertEqual(first.years_label, "2015-2016")
        self.assertFalse(first.has_dimensions)
        self.assertIsNone(first.box_volume)
        self.assertEqual(first.csv_row()[-1], "missing")
        self.assertEqual(second.csv_row()[-1], "")

    def test_scope_is_the_four_classes_and_queue_years_in_car_wagon_or_suv_classes(self):
        sedan = add_model("Acme", "Sedan", year_from=2020, year_to=2020)
        self.add_year(sedan, 2020, "Coupes & Sedans", epa=["Midsize Cars"], rows=(), body_styles=["four-door"])
        pickup = add_model("Acme", "Hauler", year_from=2020, year_to=2020)
        self.add_year(pickup, 2020, "Full-size Trucks", epa=["Standard Pickup Trucks 4WD"], rows=())
        queued = add_model("Acme", "Unsure", year_from=2020, year_to=2020)
        self.add_year(queued, 2020, None, epa=["Small Station Wagons"], rows=())
        queued_pickup = add_model("Acme", "Unsure Hauler", year_from=2020, year_to=2020)
        self.add_year(queued_pickup, 2020, None, epa=["Small Pickup Trucks 2WD"], rows=())
        found = {found.vehicle_model.model: found for found in self.ranges()}
        self.assertEqual(set(found), {"Sedan", "Unsure"})
        self.assertEqual(found["Unsure"].vehicle_class, "in queue")
        self.assertEqual(found["Unsure"].kind, "wagon")
        self.assertEqual(found["Sedan"].doors, "4")

    def test_seat_rows_come_from_the_third_row_data(self):
        model = add_model("Acme", "Roamer", year_from=2020, year_to=2022)
        self.add_year(model, 2020, "Midsize SUVs", rows=(2,))
        self.add_year(model, 2021, "Midsize SUVs", rows=(2, 3))
        self.add_year(model, 2022, "Midsize SUVs", rows=(3,))
        self.assertEqual([found.seat_rows for found in self.ranges()], ["2", "optional", "3"])

    def test_epa_size_classes_are_shown_without_their_drive(self):
        self.assertEqual(size_report.epa_base("Small Sport Utility Vehicle 4WD"), "Small Sport Utility Vehicle")
        self.assertEqual(size_report.epa_base("Sport Utility Vehicle - 2WD"), "Sport Utility Vehicle")
        self.assertEqual(size_report.epa_base("Special Purpose Vehicles/4wd"), "Special Purpose Vehicles")
        self.assertEqual(size_report.epa_base("Midsize Cars"), "Midsize Cars")


class CustomerCountTests(SizeReportTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.customer = Customer.objects.create(first_name="Pat", last_name="Example", mobile="4235550101")

    def vehicle(self, vehicle_model=None, year=None, class_name=None, **fields):
        return Vehicle.objects.create(
            customer=self.customer, vehicle_model=vehicle_model, year=year, make="Acme", model="Roamer",
            vehicle_class=self.vehicle_class(class_name) if class_name else None, **fields,
        )

    def job(self, vehicle, status=Appointment.Status.COMPLETED):
        Appointment.objects.create(
            customer=self.customer, vehicle=vehicle, status=status,
            scheduled_start=timezone.make_aware(datetime.datetime(2025, 6, 1, 9)),
        )

    def setUp(self):
        self.model = add_model("Acme", "Roamer", year_from=2015, year_to=2016)
        self.add_year(self.model, 2015, "Crossovers & Wagons", lengths=(170,))
        self.add_year(self.model, 2016, "Crossovers & Wagons", lengths=(180,))
        older = self.vehicle(self.model, 2015, "Crossovers & Wagons")
        self.job(older)
        self.job(older)
        newer = self.vehicle(self.model, 2016, "Crossovers & Wagons")
        self.job(newer, Appointment.Status.BOOKED)
        self.vehicle(self.model, None, "Midsize SUVs")
        self.vehicle(None, 2016, "Crossovers & Wagons")
        self.vehicle(None, None)

    def test_each_range_counts_its_years_vehicles_and_completed_jobs(self):
        older, newer = self.ranges()
        self.assertEqual((older.vehicles, older.jobs, older.vehicles_no_year), (1, 2, 1))
        self.assertEqual((newer.vehicles, newer.jobs, newer.vehicles_no_year), (1, 0, 1))

    def test_customer_totals_split_linked_with_a_year_with_no_year_and_unlinked(self):
        totals = dict(size_report.customer_totals())
        self.assertEqual(totals["Crossovers & Wagons"], (2, 0, 1))
        self.assertEqual(totals["Midsize SUVs"], (0, 1, 0))
        self.assertEqual(totals["no class"], (0, 0, 1))

    def test_an_older_range_a_customer_owns_joins_the_ladder(self):
        two, _, _ = size_report.suv_ladders(self.ranges())
        self.assertEqual([found.years_label for found in two], ["2015", "2016"])

    def test_the_report_changes_no_rows(self):
        counts = lambda: {model._meta.label: model._default_manager.count() for model in apps.get_models()}  # noqa: E731
        before = counts()
        self.run_report("summary")
        self.run_report("csv")
        self.assertEqual(counts(), before)
        # The read-only setting ends with the report.
        self.vehicle(None, None)

    def test_the_summary_has_every_section_and_names_no_customer(self):
        text = self.run_report()
        for heading in ("CROSSOVERS AND SUVS", "CANDIDATE LINES", "CARS AND WAGONS", "CUSTOMER VEHICLES BY THEIR RECORDED CLASS", "DATA GAPS"):
            self.assertIn(heading, text)
        self.assertIn("Acme Roamer 2015", text)
        for private in ("Pat", "Example", "4235550101"):
            self.assertNotIn(private, text)

    def test_the_csv_has_a_row_per_size_range_with_units_in_the_headers(self):
        rows = list(csv.DictReader(io.StringIO(self.run_report("csv"))))
        self.assertEqual([row["years"] for row in rows], ["2015", "2016"])
        self.assertEqual(rows[0]["length (in)"], "170.0")
        self.assertEqual(rows[0]["box volume (cu ft)"], "467.5")
        self.assertEqual(rows[0]["customer vehicles"], "1")
        self.assertEqual(rows[0]["completed jobs"], "2")
        self.assertEqual(rows[0]["seat rows"], "2")
