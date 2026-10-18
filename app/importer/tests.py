"""The Baserow and Setmore import, on invented rows in the exports' formats.

Every name, number and address here is made up; real exports never enter the
repository (CLAUDE.md).
"""

import csv
import datetime
import io
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from appointments.models import Appointment, AppointmentLine
from billing.methods import PaymentMethod
from billing.models import Payment
from bookkeeping.models import ExportBatch
from customers.models import Address, Customer, SecondContact
from importer import parsing
from importer.run import ALREADY_IN_BOOKS
from importer.sources import BASEROW_TABLES, SETMORE_COLUMNS, SourceError, load
from promotions.models import Promotion
from staff.models import Assignment, StaffMember, StaffPayout
from vehicles.models import Vehicle

CUSTOMERS = [
    # id, Name, First Name, Last Name, Phone, Email, Address, City, State, ZIP, Vehicles, Created on, Last modified, Autonumber, Appointments
    ["1", "Pat Example - 14235550101", "Pat", "Example", "14235550101", "", "100 Sample Rd", "Calhoun", "TN", "37309",
     "Toyota RAV4", "05/22/2025", "10/01/2026", "1", "Pat Example - 14235550101 - Toyota RAV4"],
    ["2", "Lee Sample - 4235550102", "Lee", "Sample", "4235550102", "lee@example.com", "200 Test Ave", "Riceville", "TN",
     "3730", "Honda Civic, Harley", "06/01/2025", "10/01/2026", "2", ""],
    ["3", "Sam Nophone - ", "Sam", "Nophone", "", "", "", "", "", "", "", "07/01/2025", "07/01/2025", "3", ""],
]
VEHICLES = [
    # id, Vehicle, Year, Make, Model, Vehicle Type, Seating, Color, Customer, Appointments
    ["11", "Toyota RAV4", "2019", "Toyota", "RAV4", "Crossovers & Wagons", "2 Rows", "Blue",
     "Pat Example - 4235550101", "Pat Example - 14235550101 - Toyota RAV4"],
    ["12", "Honda Civic", "", "Honda", "Civic", "Coupes & Sedans", "2 Rows", "", "Lee Sample - 4235550102", ""],
    ["13", "Harley ", "", "Harley", "", "", "", "", "Lee Sample - 4235550102", ""],
    # A second record for the same car: Lee's jobs cannot tell the two apart by name.
    ["15", "Honda Civic", "", "Honda", "Civic", "Coupes & Sedans", "2 Rows", "", "Lee Sample - 4235550102", ""],
    ["14", "Ghost Car", "", "", "", "Midsize SUVs", "", "", "Nobody Here - 4235550199", ""],
]
APPOINTMENTS = [
    # id, Appointment, Date, Status, Customer, Vehicle, Vehicle Type, Service Name, Service Summary, Promo Price,
    # List Price, Promotion, Promo Type, Promo Value, Price Override, Final Price, Notes, Bookkeeping, Hours, Staff,
    # Auto Promo, Wages Due, Employees Paid, Job Wage Rate, Total Wages
    ["21", "Pat Example - 14235550101 - Toyota RAV4", "10/21/2026 03:30 PM", "Completed", "Pat Example - 4235550101",
     "Toyota RAV4", "Crossovers & Wagons", "Crossovers & Wagons - Full Detail (2 Rows),Seat Extraction (2 Rows)", "",
     "290", "$330", "Friends & Family", "Fixed Price", "290", "", "$290", "Dog hair", "Pat Example - 14235550101 10/21/2026 03:30 PM",
     "8:00", "Owner Person, Helper Person", "", "Helper Person", "1", "$0", "$0"],
    ["22", "Lee Sample - 4235550102 - Honda Civic", "01/15/2026 02:00 PM", "Completed", "Lee Sample - 4235550102",
     "Honda Civic", "Coupes & Sedans", "Coupes & Sedans - Interior Detail (2 Rows)", "", "150", "$150", "", "", "0",
     "$140", "$140", "", "Lee Sample - 4235550102 01/15/2026 02:00 PM", "", "Owner Person", "", "", "0", "$0", "$0"],
    ["23", "Lee Sample - 4235550102 - Harley", "03/02/2026 01:00 PM", "Completed", "Lee Sample - 4235550102", "Harley",
     "", "", "", "100", "$100", "", "", "0", "", "$100", "", "Lee Sample - 4235550102 03/02/2026 01:00 PM", "",
     "Owner Person", "", "", "0", "$0", "$0"],
    ["24", "Pat Example - 14235550101 - Toyota RAV4", "02/02/2026 03:00 PM", "Completed", "Pat Example - 4235550101",
     "Toyota RAV4", "Crossovers & Wagons", "Crossovers & Wagons - Exterior Detail", "", "120", "$120", "", "", "0", "",
     "$0", "", "", "", "Owner Person", "", "", "0", "$0", "$0"],
    ["25", "Pat Example - 14235550101 - Toyota RAV4", "12/11/2026 01:00 PM", "Booked", "Pat Example - 4235550101",
     "Toyota RAV4", "Crossovers & Wagons", "Crossovers & Wagons - Monthly Maintenance (2 Rows)", "", "125", "$125", "",
     "", "0", "", "$125", "", "Pat Example - 14235550101 12/11/2026 01:00 PM", "", "Owner Person", "", "", "0", "$0", "$0"],
    ["26", "Nobody - ", "03/03/2026 01:00 PM", "Completed", "Nobody Here - 4235550199", "", "", "Headlight Restoration",
     "", "95", "$95", "", "", "0", "", "$95", "", "", "", "", "", "", "0", "$0", "$0"],
]
BOOKKEEPING = [
    # id, Name, Appointment, Invoice, Customer Paid, Tip, Payment Method, Date, Customer, Staff, Wages Due, Wage Override, Profit
    ["31", "Pat Example - 14235550101 10/21/2026 03:30 PM", "Pat Example - 14235550101 - Toyota RAV4", "$290", "$1,310",
     "$1,020", "Cash,Venmo", "10/21/2026 09:00 PM", "Pat Example - 14235550101", "Owner Person, Helper Person", "$0", "$75", "$215"],
    ["32", "Lee Sample - 4235550102 01/15/2026 02:00 PM", "", "$140", "$135", "'-$5", "Cash.App", "01/15/2026 07:00 PM",
     "Lee Sample - 4235550102", "Owner Person", "$0", "", "$135"],
    ["33", "Lee Sample - 4235550102 03/02/2026 01:00 PM", "", "$100", "$100", "$0", "Check", "03/02/2026 06:00 PM",
     "Lee Sample - 4235550102", "Owner Person", "$0", "", "$100"],
    ["34", "Pat Example - 14235550101 12/11/2026 01:00 PM", "", "$125", "$125", "$0", "Check", "10/01/2026 04:00 PM",
     "Pat Example - 14235550101", "Owner Person", "$0", "", "$125"],
    ["35", "Orphan row", "", "$50", "$50", "$0", "Cash", "01/01/2026 01:00 PM", "", "", "$0", "", "$50"],
]
SETMORE = [
    # Name, Email, Email1, Phone, Phone1, Company, Address, Notes
    ["Pat Example", "pat@example.com", "", "+14235550101", "", "", "", ""],
    ["Pat's Partner null", "", "", "+14235550103", "", "", "", ""],
    ["Skip Me null", "", "", "+14235550104", "", "", "", ""],
    ["Stranger Person", "", "", "+14235550105", "", "", "", ""],
]
CORRECTIONS = """\
# import-corrections.yaml (invented test data)
meta:
  version: 3
customer_fixes:
  - baserow_id: 2
    name_on_export: Lee Sample
    set:
      zip: "37309"
    reason: ZIP was missing a digit
  - baserow_id: 3
    name_on_export: Somebody Else
    flag: Ask for a phone number
    reason: No number on file
second_contacts:
  - customer_baserow_id: 1
    customer_name_on_export: Pat Example
    contact_name: Pat's Partner
    contact_phone: "4235550103"
    source: Setmore
  - customer_baserow_id: 2
    customer_name_on_export: Lee Sample
    contact_name: Lee's Partner
    contact_phone: same as the customer
    source: Setmore
setmore_merged_into_baserow: []
setmore_not_imported:
  - Skip Me null
appointment_fixes:
  - baserow_id: 22
    customer_name_on_export: Lee Sample
    set:
      vehicle_baserow_id: 15
    reason: Lee has two Honda Civic records; this job was the second one
  - baserow_id: 23
    customer_name_on_export: Lee Sample
    set:
      vehicle_baserow_id: 11
    reason: Wrong id, for the test
  - baserow_id: 24
    customer_name_on_export: Pat Example
    no_charge:
      reason: Gift
    reason: Final price $0 is a gift
  - baserow_id: 25
    customer_name_on_export: Pat Example
    prepaid:
      method: check
      amount: "125.00"
      received: 2026-10-01
      note: Paid ahead
    reason: Imports as already paid; Bookkeeping records it
bookkeeping_fixes:
  - bookkeeping_id: 31
    customer_name_on_export: Pat Example
    set:
      customer_paid: "310.00"
      tip: "20.00"
    reason: Typo in the export
checks:
  - Appointment 21 is 10/21/2026 03:30 PM UTC and must show 11:30 AM Eastern.
to_confirm:
  - baserow_id: 3
    name_on_export: Sam Nophone
    question: Is this customer still active?
"""


def write_csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        writer.writerows(rows)


class ImportTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_pricebook", stdout=io.StringIO())

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder)
        write_csv(self.folder / "export - Customers.csv", BASEROW_TABLES["Customers"], CUSTOMERS)
        write_csv(self.folder / "BaserowExport - Vehicles - Grid.csv", BASEROW_TABLES["Vehicles"], VEHICLES)
        write_csv(self.folder / "export - Appointments.csv", BASEROW_TABLES["Appointments"], APPOINTMENTS)
        write_csv(self.folder / "BaserowExport - Bookkeeping - Grid.csv", BASEROW_TABLES["Bookkeeping"], BOOKKEEPING)
        write_csv(self.folder / "SetmoreContacts.csv", SETMORE_COLUMNS, SETMORE)
        (self.folder / "import-corrections.yaml").write_text(CORRECTIONS)

    def run_import(self, *args):
        output = io.StringIO()
        call_command("import_baserow", str(self.folder), "--owner", "Owner Person", *args, stdout=output)
        return output.getvalue()


class ParsingTests(TestCase):
    def test_money(self):
        self.assertEqual(parsing.money("$1,234"), Decimal("1234.00"))
        self.assertEqual(parsing.money("'-$5"), Decimal("-5.00"))
        self.assertEqual(parsing.money("290"), Decimal("290.00"))
        self.assertIsNone(parsing.money(""))
        with self.assertRaises(ValueError):
            parsing.money("about $5")

    def test_dates_are_utc_and_show_in_eastern(self):
        moment = parsing.utc_datetime("10/21/2026 03:30 PM")
        self.assertEqual(timezone.localtime(moment).strftime("%Y-%m-%d %H:%M"), "2026-10-21 11:30")
        winter = parsing.utc_datetime("01/15/2026 02:00 PM")
        self.assertEqual(timezone.localtime(winter).strftime("%H:%M"), "09:00")

    def test_hours_seating_and_phone(self):
        self.assertEqual(parsing.minutes("7:30"), 450)
        self.assertIsNone(parsing.minutes(""))
        self.assertEqual(parsing.seating("1 Row"), 1)
        self.assertEqual(parsing.seating("3 Rows"), 3)
        self.assertEqual(parsing.phone("14235550101"), "4235550101")
        self.assertEqual(parsing.phone("+1 (423) 555-0101"), "4235550101")
        self.assertEqual(parsing.phone("555-0101"), "")

    def test_service_names(self):
        items = parsing.services("Fullsize Trucks - Interior Detail (2 Rows),Carpet Extraction (2 Rows),Headlight Restoration")
        self.assertEqual(
            [(i.vehicle_class, i.service, i.rows) for i in items],
            [("Fullsize Trucks", "Interior Only", 2), ("", "Carpet Extraction", 2), ("", "Headlight Restoration", None)],
        )
        [item] = parsing.services("Coupes & Sedans - Paint Correction 1-Step")
        self.assertEqual((item.vehicle_class, item.service), ("Coupes & Sedans", "1-Step Paint Correction"))

    def test_links(self):
        self.assertEqual(parsing.Link.parse("Pat Example - 14235550101"), parsing.Link("pat example", "4235550101"))
        self.assertEqual(parsing.Link.parse("Sam Nophone - "), parsing.Link("sam nophone", ""))


class SourceTests(ImportTestCase):
    def test_files_are_found_by_table_name(self):
        tables, corrections, files = load(self.folder)
        self.assertEqual(files["Vehicles"], "BaserowExport - Vehicles - Grid.csv")
        self.assertEqual(files["Customers"], "export - Customers.csv")
        self.assertEqual(files["Setmore"], "SetmoreContacts.csv")
        # The byte-order mark is not part of the first column's name.
        self.assertEqual(tables["Customers"][0]["id"], "1")
        self.assertEqual(corrections["meta"]["version"], 3)

    def test_two_files_for_one_table_are_refused(self):
        write_csv(self.folder / "older - Customers.csv", BASEROW_TABLES["Customers"], [])
        with self.assertRaises(SourceError):
            load(self.folder)

    def test_a_missing_column_is_refused(self):
        write_csv(self.folder / "export - Customers.csv", BASEROW_TABLES["Customers"][:-1], [])
        with self.assertRaises(SourceError):
            load(self.folder)


class DryRunTests(ImportTestCase):
    def test_dry_run_changes_nothing_and_reports(self):
        report = self.run_import()
        self.assertIn("DRY RUN", report)
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Appointment.objects.count(), 0)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertFalse(StaffMember.objects.exists())
        self.assertIn("customers created: 3", report)
        self.assertIn("Customers id 2: set zip (ZIP was missing a digit)", report)
        # Rows it could not place, with the reason.
        self.assertIn("Vehicles id 14: its customer 'Nobody Here - 4235550199' is not a customer", report)
        self.assertIn("Appointments id 26: its customer", report)
        self.assertIn("Bookkeeping id 35: no appointment names this Bookkeeping row", report)
        self.assertIn("the corrections file names this row 'Somebody Else'", report)
        self.assertIn("Is this customer still active?", report)
        self.assertIn("must show 11:30 AM Eastern", report)

    def test_without_the_fix_two_same_named_vehicles_are_left_blank(self):
        corrections = CORRECTIONS.replace("      vehicle_baserow_id: 15\n", "      vehicle_baserow_id: 99\n")
        (self.folder / "import-corrections.yaml").write_text(corrections)
        report = self.run_import()
        self.assertIn("Appointments id 22: set vehicle_baserow_id: no imported vehicle has Baserow id 99", report)
        self.assertIn("Appointments id 22: the customer has 2 vehicles named 'Honda Civic'; vehicle left blank", report)

    def test_staff_without_an_owner_are_reported(self):
        output = io.StringIO()
        call_command("import_baserow", str(self.folder), stdout=output)
        self.assertIn("run with --owner", output.getvalue())

    def test_the_report_shows_helper_payouts(self):
        report = self.run_import()
        self.assertIn("Helper pay: every helper's pay and payout (1)", report)
        self.assertIn("Appointments id 21: $75.00 to Helper Person, paid 2026-10-21 as cash (Wage Override in Baserow)", report)


class HelperPayTests(ImportTestCase):
    def fix_job_21(self, helper_pay, staff=None):
        """Add an appointment fix for job 21, and optionally change its Staff."""
        lines = "".join(f"      {name}: \"{amount}\"\n" for name, amount in helper_pay.items())
        corrections = CORRECTIONS.replace(
            "appointment_fixes:\n",
            f"appointment_fixes:\n  - baserow_id: 21\n    helper_pay:\n{lines}    reason: Pay agreed by text\n",
        )
        (self.folder / "import-corrections.yaml").write_text(corrections)
        if staff:
            rows = [row[:] for row in APPOINTMENTS]
            rows[0][19] = staff
            write_csv(self.folder / "export - Appointments.csv", BASEROW_TABLES["Appointments"], rows)

    def test_the_owner_is_never_a_helper(self):
        # An earlier run without --owner made the owner a helper.
        StaffMember.objects.create(name="Owner Person", role=StaffMember.Role.HELPER, pay_type="family_helper")
        report = self.run_import("--apply")
        owner = StaffMember.objects.get(name="Owner Person")
        self.assertEqual((owner.role, owner.pay_type), (StaffMember.Role.OWNER, ""))
        self.assertIn("staff 'Owner Person': the owner, never a helper: changed from helper to owner", report)
        payout = StaffPayout.objects.get()
        self.assertEqual((payout.staff_member.name, payout.amount), ("Helper Person", Decimal("75.00")))
        self.assertIsNone(Assignment.objects.get(appointment__baserow_id=21, staff_member=owner).pay_override)

    def test_a_wage_override_with_only_the_owner_on_the_job_is_not_pay(self):
        self.fix_job_21({}, staff="Owner Person")
        report = self.run_import("--apply")
        self.assertFalse(StaffPayout.objects.exists())
        self.assertIn("Appointments id 21: a Wage Override with 0 helpers on the job; helper pay not recorded", report)

    def test_helper_pay_replaces_the_wage_override(self):
        self.fix_job_21({"Helper Person": "60.00"})
        report = self.run_import("--apply")
        payout = StaffPayout.objects.get()
        self.assertEqual((payout.staff_member.name, payout.amount), ("Helper Person", Decimal("60.00")))
        self.assertIn("Appointments id 21: helper pay $60.00 to Helper Person (Pay agreed by text)", report)
        self.assertIn("helper_pay totals $60.00, the Wage Override is $75.00; helper_pay is used", report)
        self.assertIn("$60.00 to Helper Person, paid 2026-10-21 as cash (corrections file: Pay agreed by text)", report)

    def test_helper_pay_splits_the_pay_between_two_helpers(self):
        self.fix_job_21({"Helper Person": "45.00", "Other Helper": "30.00"}, staff="Owner Person, Helper Person, Other Helper")
        report = self.run_import("--apply")
        self.assertEqual(
            sorted(StaffPayout.objects.values_list("staff_member__name", "amount")),
            [("Helper Person", Decimal("45.00")), ("Other Helper", Decimal("30.00"))],
        )
        self.assertNotIn("helper_pay totals", report)
        self.assertIn("Helper pay: every helper's pay and payout (2)", report)
        # A re-run updates the same two payouts.
        self.run_import("--apply")
        self.assertEqual(StaffPayout.objects.count(), 2)

    def test_two_helpers_without_helper_pay_are_reported(self):
        self.fix_job_21({}, staff="Owner Person, Helper Person, Other Helper")
        report = self.run_import()
        self.assertIn("Appointments id 21: a Wage Override with 2 helpers on the job; helper pay not recorded", report)

    def test_helper_pay_for_the_owner_or_someone_off_the_job_is_refused(self):
        self.fix_job_21({"Owner Person": "75.00", "Nobody Else": "10.00"})
        report = self.run_import("--apply")
        self.assertIn("Appointments id 21: helper_pay names 'Owner Person', the owner, who is never a helper", report)
        self.assertIn("Appointments id 21: helper_pay names 'Nobody Else', who is not in the job's Staff column", report)
        # The Wage Override rule applies instead.
        payout = StaffPayout.objects.get()
        self.assertEqual((payout.staff_member.name, payout.amount), ("Helper Person", Decimal("75.00")))


class ApplyTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.report = self.run_import("--apply")

    def test_customers_addresses_and_corrections(self):
        self.assertEqual(Customer.objects.count(), 3)
        pat = Customer.objects.get(baserow_id=1)
        self.assertEqual(pat.mobile, "4235550101")
        # Setmore filled the blank email; it never overwrites Baserow.
        self.assertEqual(pat.email, "pat@example.com")
        lee = Customer.objects.get(baserow_id=2)
        self.assertEqual(lee.email, "lee@example.com")
        self.assertEqual(Address.objects.get(customer=lee).zip_code, "37309")
        sam = Customer.objects.get(baserow_id=3)
        self.assertEqual(sam.mobile, "")
        self.assertIn("Ask for a phone number", sam.notes)
        self.assertFalse(Address.objects.filter(customer=sam).exists())

    def test_second_contacts_and_setmore(self):
        partner = SecondContact.objects.get(customer__baserow_id=1)
        self.assertEqual((partner.name, partner.phone), ("Pat's Partner", "4235550103"))
        shared = SecondContact.objects.get(customer__baserow_id=2)
        self.assertEqual(shared.phone, "4235550102")
        self.assertIn("Setmore contacts skipped as agreed: 1", self.report)
        self.assertIn("Setmore contacts not imported (Setmore only fills gaps): 1", self.report)
        self.assertFalse(Customer.objects.filter(first_name="Stranger").exists())

    def test_vehicles(self):
        self.assertEqual(Vehicle.objects.count(), 4)
        rav4 = Vehicle.objects.get(baserow_id=11)
        self.assertEqual((rav4.vehicle_class.name, rav4.size_variant.value, rav4.year), ("Crossovers & Wagons", 2, 2019))
        harley = Vehicle.objects.get(baserow_id=13)
        self.assertIsNone(harley.vehicle_class)

    def test_a_job_keeps_the_price_charged(self):
        job = Appointment.objects.get(baserow_id=21)
        self.assertEqual(job.status, Appointment.Status.COMPLETED)
        self.assertEqual(job.source, Appointment.Source.IMPORT)
        self.assertEqual(timezone.localtime(job.scheduled_start).strftime("%Y-%m-%d %H:%M"), "2026-10-21 11:30")
        self.assertEqual(job.vehicle.baserow_id, 11)
        lines = [(line.kind, line.description, line.amount) for line in job.lines.all()]
        self.assertEqual(
            lines,
            [
                (AppointmentLine.Kind.SERVICE, "Full Detail", Decimal("330.00")),
                (AppointmentLine.Kind.ADD_ON, "Seat Extraction (price included in the first line)", Decimal("0.00")),
                (AppointmentLine.Kind.PROMOTION, "Friends & Family", Decimal("-40.00")),
            ],
        )
        self.assertEqual(job.total_before_tax, Decimal("290.00"))
        self.assertFalse(Promotion.objects.get(name="Friends & Family").active)

    def test_a_fix_names_the_vehicle_by_its_baserow_id(self):
        self.assertEqual(Appointment.objects.get(baserow_id=22).vehicle.baserow_id, 15)
        self.assertIn("Appointments id 22: linked to vehicle 15 (Lee has two Honda Civic records", self.report)
        self.assertNotIn("Appointments id 22: the customer has 2 vehicles", self.report)

    def test_a_fix_naming_another_customers_vehicle_is_refused(self):
        self.assertIn("Appointments id 23: set vehicle_baserow_id: vehicle 11 belongs to another customer", self.report)
        # The usual matching still applies.
        self.assertEqual(Appointment.objects.get(baserow_id=23).vehicle.baserow_id, 13)

    def test_hours_are_the_time_on_site_split_by_the_crew(self):
        job = Appointment.objects.get(baserow_id=21)
        self.assertEqual(job.crew_size, 2)
        self.assertEqual((job.setup_minutes, job.service_minutes, job.breakdown_minutes), (15, 450, 15))
        self.assertEqual(job.time_on_site_minutes, 480)
        self.assertIsNone(Appointment.objects.get(baserow_id=22).service_minutes)

    def test_old_service_names_override_custom_and_no_charge(self):
        interior = Appointment.objects.get(baserow_id=22)
        self.assertEqual(interior.lines.first().service.name, "Interior Only")
        adjustment = interior.lines.get(kind=AppointmentLine.Kind.ADJUSTMENT)
        self.assertEqual((adjustment.amount, adjustment.reason), (Decimal("-10.00"), "Price override in Baserow"))
        self.assertEqual(interior.total_before_tax, Decimal("140.00"))
        motorcycle = Appointment.objects.get(baserow_id=23)
        self.assertEqual([line.kind for line in motorcycle.lines.all()], [AppointmentLine.Kind.CUSTOM])
        self.assertEqual(motorcycle.total_before_tax, Decimal("100.00"))
        gift = Appointment.objects.get(baserow_id=24)
        self.assertEqual(gift.lines.first().service.name, "Exterior Only")
        self.assertTrue(gift.is_no_charge)
        self.assertEqual(gift.lines.get(kind=AppointmentLine.Kind.NO_CHARGE).reason, "Gift")
        self.assertEqual(gift.total_before_tax, Decimal("0.00"))

    def test_payments_come_from_bookkeeping_and_are_already_in_the_books(self):
        split = Payment.objects.get(import_key="bookkeeping:31")
        # The corrections file fixed the amounts; one payment, split between two methods.
        self.assertEqual((split.amount, split.tip), (Decimal("290.00"), Decimal("20.00")))
        self.assertEqual((split.method, split.split_method), (PaymentMethod.CASH, PaymentMethod.VENMO))
        negative = Payment.objects.get(import_key="bookkeeping:32")
        self.assertEqual((negative.method, negative.amount, negative.tip), (PaymentMethod.CASH_APP_DIRECT, Decimal("140.00"), Decimal("-5.00")))
        batch = ExportBatch.objects.get(file_name=ALREADY_IN_BOOKS)
        self.assertFalse(Payment.objects.filter(export_batch__isnull=True).exists())
        self.assertEqual(set(Payment.objects.values_list("export_batch", flat=True)), {batch.pk})
        self.assertEqual(batch.date_from, datetime.date(2026, 1, 15))
        # The gift job has no payment.
        self.assertFalse(Payment.objects.filter(appointment__baserow_id=24).exists())

    def test_a_prepaid_booked_job_is_already_paid_once(self):
        booked = Appointment.objects.get(baserow_id=25)
        self.assertEqual(booked.status, Appointment.Status.BOOKED)
        [payment] = booked.payments.all()
        self.assertEqual((payment.method, payment.amount), (PaymentMethod.CHECK, Decimal("125.00")))
        self.assertIn("prepaid: found in Bookkeeping", self.report)

    def test_staff_assignments_and_helper_pay(self):
        owner = StaffMember.objects.get(name="Owner Person")
        helper = StaffMember.objects.get(name="Helper Person")
        self.assertEqual(owner.role, StaffMember.Role.OWNER)
        self.assertEqual((helper.role, helper.pay_type), (StaffMember.Role.HELPER, "family_helper"))
        assignment = Assignment.objects.get(appointment__baserow_id=21, staff_member=helper)
        self.assertEqual(assignment.pay, Decimal("75.00"))
        payout = StaffPayout.objects.get()
        self.assertEqual((payout.amount, payout.staff_member, assignment.payout), (Decimal("75.00"), helper, payout))
        self.assertIsNotNone(payout.export_batch)

    def test_a_second_run_updates_instead_of_duplicating(self):
        counts = [model.objects.count() for model in (Customer, Address, Vehicle, Appointment, AppointmentLine, Payment, Assignment, StaffPayout, SecondContact, Promotion)]
        changed = [row[:] for row in CUSTOMERS]
        changed[0][5] = ""
        changed[1][2] = "Leigh"
        write_csv(self.folder / "export - Customers.csv", BASEROW_TABLES["Customers"], changed)
        report = self.run_import("--apply")
        self.assertIn("customers updated: 3", report)
        self.assertEqual(
            [model.objects.count() for model in (Customer, Address, Vehicle, Appointment, AppointmentLine, Payment, Assignment, StaffPayout, SecondContact, Promotion)],
            counts,
        )
        self.assertEqual(Customer.objects.get(baserow_id=2).first_name, "Leigh")


class PricebookFirstTests(TestCase):
    def test_the_pricebook_must_be_loaded_first(self):
        from django.core.management.base import CommandError

        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder)
        for name, table in (("Customers", CUSTOMERS), ("Vehicles", VEHICLES), ("Appointments", APPOINTMENTS), ("Bookkeeping", BOOKKEEPING)):
            write_csv(folder / f"export - {name}.csv", BASEROW_TABLES[name], table)
        write_csv(folder / "SetmoreContacts.csv", SETMORE_COLUMNS, SETMORE)
        (folder / "import-corrections.yaml").write_text(CORRECTIONS)
        with self.assertRaisesMessage(CommandError, "run load_pricebook"):
            call_command("import_baserow", str(folder), "--apply", stdout=io.StringIO())
        self.assertFalse(Customer.objects.exists())
