"""The Baserow and Setmore import (docs/reference/data-migration.md, decisions
0036 and 0051).

run() imports every table inside one transaction. A dry run rolls the
transaction back at the end, so its report shows exactly what --apply would
write. Records are found by their Baserow ids, so a later run with fresh
exports updates what an earlier run wrote instead of duplicating it.
"""

import datetime
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from appointments.models import Appointment, AppointmentLine
from billing.methods import PaymentMethod
from billing.models import Payment
from bookkeeping.models import ExportBatch
from core.fields import normalize_phone
from core.scheduling import launch_values, round_to_nearest
from customers.models import Address, Customer, SecondContact
from pricebook.models import Service
from promotions.models import Promotion
from staff.models import Assignment, PayType, StaffMember, StaffPayout
from vehicles.classification.switch import renames
from vehicles.models import Vehicle, VehicleClass

from . import parsing
from .parsing import Link, squash

ZERO = Decimal("0.00")

# The ExportBatch that holds every imported payment and payout. They are
# already in the owner's GnuCash books, so the Phase 6 export, which sends
# only what no batch holds, never sends them again.
ALREADY_IN_BOOKS = "Already in GnuCash: Baserow import"

METHODS = {
    "cash": PaymentMethod.CASH,
    "venmo": PaymentMethod.VENMO,
    # Cash App direct to the owner's $cashtag (corrections file, rules.payment_methods).
    "cash.app": PaymentMethod.CASH_APP_DIRECT,
    "cash app": PaymentMethod.CASH_APP_DIRECT,
    "paypal": PaymentMethod.PAYPAL,
    "card": PaymentMethod.CARD,
    "check": PaymentMethod.CHECK,
    "trade": PaymentMethod.TRADE,
    "gift card": PaymentMethod.GIFT_CARD,
    "bitcoin": PaymentMethod.BITCOIN,
}
STATUSES = {"completed": Appointment.Status.COMPLETED, "booked": Appointment.Status.BOOKED}
PROMO_KINDS = {"percentage off": Promotion.Kind.PERCENT_OFF, "fixed price": Promotion.Kind.FIXED_PRICE}
CUSTOMER_FIELDS = {"first_name", "last_name", "email", "company", "phone"}
ADDRESS_FIELDS = {"address": "line1", "city": "city", "state": "state", "zip": "zip_code"}


def method(text):
    """A payment method written as in Baserow ("Cash.App") or as the system's
    own code ("cash_app_direct")."""
    text = squash(text).lower()
    found = METHODS.get(text) or next((m for m in PaymentMethod if m.value == text), None)
    if found is None:
        raise ValueError(f"unknown payment method {text!r}")
    return found


class ImportRefused(Exception):
    """The database is not ready for the import."""


@dataclass
class Report:
    files: dict = field(default_factory=dict)
    counts: Counter = field(default_factory=Counter)
    corrections: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    unplaced: list = field(default_factory=list)
    questions: list = field(default_factory=list)
    checks: list = field(default_factory=list)
    helper_pay: list = field(default_factory=list)

    def count(self, kind, created=None):
        if created is None:
            self.counts[kind] += 1
        else:
            self.counts[f"{kind} {'created' if created else 'updated'}"] += 1

    def correction(self, where, text):
        self.corrections.append(f"{where}: {text}")

    def warn(self, where, text):
        self.warnings.append(f"{where}: {text}")

    def cannot_place(self, where, why):
        self.unplaced.append(f"{where}: {why}")

    def pay(self, where, text):
        self.helper_pay.append(f"{where}: {text}")


class Importer:
    def __init__(self, tables, corrections, owner_name=None, report=None):
        self.tables = tables
        self.corrections = corrections or {}
        self.owner_name = squash(owner_name).lower() if owner_name else None
        self.report = report or Report()
        self.customers = {}  # Baserow id -> Customer
        self.addresses = {}  # Baserow customer id -> Address
        self.vehicles = {}  # Baserow id -> Vehicle
        self.classes = {vehicle_class.name: vehicle_class for vehicle_class in VehicleClass.objects.all()}
        # Baserow names two classes as they were before apply_size_classes renamed them (decision 0083).
        for old, new in renames().items():
            if new in self.classes:
                self.classes.setdefault(old, self.classes[new])
        self.services = {service.name: service for service in Service.objects.all()}
        self.batch = None
        self.payment_dates = []

    # Corrections ----------------------------------------------------------

    def fixes(self, section, key="baserow_id"):
        found = {}
        for entry in self.corrections.get(section) or []:
            found[int(entry[key])] = entry
        return found

    def check_name(self, where, entry, name_key, actual):
        expected = entry.get(name_key)
        if expected and squash(expected).lower() != squash(actual).lower():
            self.report.warn(where, f"the corrections file names this row {expected!r}, the export {actual!r}")

    # Customers ------------------------------------------------------------

    def import_customers(self):
        fixes = self.fixes("customer_fixes")
        rows = self.tables["Customers"]
        self.customer_rows = rows
        for row in rows:
            where = f"Customers id {row['id']}"
            baserow_id = int(row["id"])
            values = {
                "first_name": squash(row["First Name"]),
                "last_name": squash(row["Last Name"]),
                "email": squash(row["Email"]),
                "phone": parsing.phone(row["Phone"]),
            }
            if squash(row["Phone"]) and not values["phone"]:
                self.report.warn(where, "the phone number has fewer than 10 digits and was left blank")
            address = {
                "line1": squash(row["Address"]),
                "city": squash(row["City"]),
                "state": squash(row["State"]).upper(),
                "zip_code": squash(row["ZIP"]),
            }
            approved_out_of_area = False
            notes = []
            fix = fixes.pop(baserow_id, None)
            if fix:
                self.check_name(where, fix, "name_on_export", f"{values['first_name']} {values['last_name']}")
                for name, value in (fix.get("set") or {}).items():
                    if name in CUSTOMER_FIELDS:
                        values[name] = parsing.phone(str(value)) if name == "phone" else squash(str(value))
                    elif name in ADDRESS_FIELDS:
                        address[ADDRESS_FIELDS[name]] = squash(str(value))
                    elif name == "approved_out_of_area":
                        approved_out_of_area = bool(value)
                    else:
                        self.report.warn(where, f"the corrections file sets {name!r}, which the import does not know")
                        continue
                    self.report.correction(where, f"set {name} ({fix.get('reason', 'no reason given')})")
                for name, value in (fix.get("keep") or {}).items():
                    current = address.get(ADDRESS_FIELDS.get(name, name), values.get(name))
                    if squash(str(value)).lower() != squash(str(current)).lower():
                        self.report.warn(where, f"the corrections file keeps {name} as given, but the export now differs")
                    self.report.correction(where, f"kept {name} as it is ({fix.get('reason', 'no reason given')})")
                if fix.get("flag"):
                    notes.append(f"Import flag: {fix['flag']}")
                    self.report.correction(where, "flagged for the owner")
            if not values["first_name"]:
                self.report.cannot_place(where, "no first name")
                continue
            customer, created = Customer.objects.update_or_create(
                baserow_id=baserow_id,
                defaults={
                    "first_name": values["first_name"],
                    "last_name": values["last_name"],
                    "company": values.get("company", ""),
                    "mobile": values["phone"],
                    "email": values["email"],
                    "notes": "\n".join(notes),
                },
            )
            if squash(row["Created on"]):
                try:
                    created_on = parsing.date(row["Created on"])
                    Customer.objects.filter(pk=customer.pk).update(
                        created_at=timezone.make_aware(datetime.datetime.combine(created_on, datetime.time(12)))
                    )
                except ValueError as error:
                    self.report.warn(where, str(error))
            self.report.count("customers", created)
            if not values["phone"]:
                self.report.count("customers with no phone number")
            self.customers[baserow_id] = customer
            if address["line1"]:
                self.addresses[baserow_id], created = Address.objects.update_or_create(
                    import_key=f"customer:{baserow_id}",
                    defaults={**address, "customer": customer, "approved_out_of_area": approved_out_of_area},
                )
                self.report.count("addresses", created)
        for baserow_id, fix in fixes.items():
            self.report.cannot_place(f"customer_fixes baserow_id {baserow_id}", "no customer with that id in the export")
        self.index_customer_links()

    def index_customer_links(self):
        self.customer_by_display = {}
        self.customer_by_link = defaultdict(list)
        self.customer_by_name = defaultdict(list)
        for row in self.customer_rows:
            customer = self.customers.get(int(row["id"]))
            if customer is None:
                continue
            self.customer_by_display[squash(row["Name"])] = customer
            link = Link.parse(row["Name"])
            self.customer_by_link[link].append(customer)
            self.customer_by_name[link.name].append(customer)

    def customer_for(self, value):
        """The customer a link cell names: the exact display string, else the
        same name and last 10 digits of the phone, else a name only one
        customer has. None when it cannot be told."""
        text = squash(value)
        if not text:
            return None
        if text in self.customer_by_display:
            return self.customer_by_display[text]
        link = Link.parse(text)
        for candidates in (self.customer_by_link.get(link, []), self.customer_by_name.get(link.name, [])):
            if len(candidates) == 1:
                return candidates[0]
        return None

    # Setmore and second contacts -----------------------------------------

    def import_setmore(self):
        merged = {}
        for entry in self.corrections.get("setmore_merged_into_baserow") or []:
            merged[self.setmore_name(entry["setmore_name"]).lower()] = entry
        not_imported = {self.setmore_name(name).lower() for name in self.corrections.get("setmore_not_imported") or []}
        second = {
            parsing.phone(str(entry["contact_phone"])) for entry in self.corrections.get("second_contacts") or []
        }
        by_phone = {customer.mobile: customer for customer in self.customers.values() if customer.mobile}
        for number, row in enumerate(self.tables["Setmore"], start=2):
            name = self.setmore_name(row["Name"])
            where = f"Setmore line {number}"
            phones = [p for p in (parsing.phone(row["Phone"]), parsing.phone(row["Phone1"])) if p]
            emails = [e for e in (squash(row["Email"]), squash(row["Email1"])) if e]
            customer, how = None, ""
            entry = merged.pop(name.lower(), None)
            if entry:
                customer = self.customers.get(int(entry["baserow_id"]))
                how = f"merged into Baserow customer {entry['baserow_id']} ({entry.get('reason', 'no reason given')})"
                if customer is None:
                    self.report.cannot_place(where, f"setmore_merged_into_baserow names customer {entry['baserow_id']}, not in the export")
                    continue
            else:
                customer = next((by_phone[p] for p in phones if p in by_phone), None)
                how = "matched by phone number"
            if customer is None:
                if name.lower() in not_imported:
                    self.report.count("Setmore contacts skipped as agreed")
                elif any(p in second for p in phones):
                    self.report.count("Setmore contacts imported as second contacts")
                else:
                    self.report.count("Setmore contacts not imported (Setmore only fills gaps)")
                continue
            self.report.count("Setmore contacts matched to a customer")
            # Setmore fills gaps only; it never overwrites Baserow.
            filled = []
            if not customer.email and emails:
                customer.email = emails[0]
                filled.append("email")
            if not customer.mobile and phones:
                customer.mobile = phones[0]
                filled.append("phone")
            if filled:
                customer.save()
                self.report.correction(where, f"filled a blank {' and '.join(filled)} on customer {customer.baserow_id}, {how}")
                self.report.count("customers filled in from Setmore")
        for name in merged:
            self.report.cannot_place("setmore_merged_into_baserow", f"no Setmore contact named {name!r}")

    @staticmethod
    def setmore_name(value):
        """Drop Setmore's " null" placeholder for a missing last name."""
        name = squash(value)
        return name[: -len(" null")] if name.lower().endswith(" null") else name

    def import_second_contacts(self):
        for entry in self.corrections.get("second_contacts") or []:
            where = f"second_contacts for customer {entry['customer_baserow_id']}"
            customer = self.customers.get(int(entry["customer_baserow_id"]))
            if customer is None:
                self.report.cannot_place(where, "no customer with that id in the export")
                continue
            self.check_name(where, entry, "customer_name_on_export", str(customer))
            given = squash(str(entry.get("contact_phone", "")))
            if given.lower().startswith("same as the customer"):
                # The second contact shares the customer's number.
                given = customer.mobile
            try:
                number = normalize_phone(given)
            except Exception:
                number = ""
            if not number:
                self.report.cannot_place(where, "the contact's phone number is not 10 digits")
                continue
            _, created = SecondContact.objects.update_or_create(
                customer=customer,
                phone=number,
                defaults={"name": squash(entry["contact_name"]), "notes": f"Imported; source: {entry.get('source', '')}"},
            )
            self.report.count("second contacts", created)
            self.report.correction(where, "added a second contact")

    # Vehicles -------------------------------------------------------------

    def import_vehicles(self):
        self.vehicle_rows = self.tables["Vehicles"]
        for row in self.vehicle_rows:
            where = f"Vehicles id {row['id']}"
            customer = self.customer_for(row["Customer"])
            if customer is None:
                self.report.cannot_place(where, f"its customer {squash(row['Customer'])!r} is not a customer in the export")
                continue
            vehicle_class, size_variant = None, None
            class_name = squash(row["Vehicle Type"])
            if class_name:
                vehicle_class = self.classes.get(class_name)
                if vehicle_class is None:
                    self.report.warn(where, f"unknown vehicle class {class_name!r}; imported with no class")
            else:
                # Motorcycles: past records with no vehicle class (corrections file, rules.motorcycles).
                self.report.count("vehicles with no vehicle class")
            try:
                rows = parsing.seating(row["Seating"])
                vehicle_year = parsing.year(row["Year"])
            except ValueError as error:
                self.report.warn(where, str(error))
                rows, vehicle_year = None, None
            if vehicle_class and rows:
                size_variant = vehicle_class.size_variants.filter(value=rows).first()
                if size_variant is None:
                    self.report.warn(where, f"{vehicle_class} has no size {rows}; size left to fill in")
            vehicle, created = Vehicle.objects.update_or_create(
                baserow_id=int(row["id"]),
                defaults={
                    "customer": customer,
                    "year": vehicle_year,
                    "make": squash(row["Make"]),
                    "model": squash(row["Model"]),
                    "color": squash(row["Color"]),
                    "vehicle_class": vehicle_class,
                    "size_variant": size_variant,
                },
            )
            self.vehicles[int(row["id"])] = vehicle
            self.report.count("vehicles", created)
            if vehicle.missing_details:
                self.report.count("vehicles with details to fill in")

    def fixed_vehicle(self, where, value, customer, fix):
        """The vehicle an appointment_fixes entry names by its Baserow id, for a
        customer with two vehicles of the same name. None, with the reason
        reported, when it cannot be used; the usual matching then applies."""
        try:
            vehicle = self.vehicles.get(int(value))
        except (TypeError, ValueError):
            self.report.cannot_place(where, f"set vehicle_baserow_id: {value!r} is not a Baserow id")
            return None
        if vehicle is None:
            self.report.cannot_place(where, f"set vehicle_baserow_id: no imported vehicle has Baserow id {value}")
            return None
        if vehicle.customer_id != customer.pk:
            self.report.cannot_place(where, f"set vehicle_baserow_id: vehicle {value} belongs to another customer")
            return None
        self.report.correction(where, f"linked to vehicle {value} ({fix.get('reason', 'no reason given')})")
        return vehicle

    def vehicle_for(self, row, customer):
        """The vehicle an appointment names, told apart by its customer and,
        where one customer has two of the same name, by the vehicle's own
        Appointments column."""
        name = squash(row["Vehicle"])
        if not name:
            return None
        candidates = [
            vehicle_row
            for vehicle_row in self.vehicle_rows
            if squash(vehicle_row["Vehicle"]) == name and int(vehicle_row["id"]) in self.vehicles
        ]
        candidates = [r for r in candidates if self.vehicles[int(r["id"])].customer_id == customer.pk]
        if len(candidates) > 1:
            display = squash(row["Appointment"])
            linked = [r for r in candidates if display and display in squash(r["Appointments"])]
            candidates = linked or candidates
        if len(candidates) > 1:
            # Two of the customer's vehicles share a name: the appointment's
            # vehicle class and seat rows may tell them apart.
            items = parsing.services(row["Service Name"])
            rows = items[0].rows if items else None
            same = [
                r
                for r in candidates
                if squash(r["Vehicle Type"]) == squash(row["Vehicle Type"])
                and (rows is None or parsing.seating_or_none(r["Seating"]) in (rows, None))
            ]
            candidates = same if len(same) == 1 else candidates
        if len(candidates) == 1:
            return self.vehicles[int(candidates[0]["id"])]
        where = f"Appointments id {row['id']}"
        if candidates:
            self.report.warn(where, f"the customer has {len(candidates)} vehicles named {name!r}; vehicle left blank")
        else:
            self.report.warn(where, f"no vehicle named {name!r} belongs to its customer; vehicle left blank")
        return None

    # Appointments ---------------------------------------------------------

    def import_appointments(self):
        fixes = self.fixes("appointment_fixes")
        bookkeeping_fixes = self.fixes("bookkeeping_fixes", key="bookkeeping_id")
        bookkeeping = defaultdict(list)
        for book_row in self.tables["Bookkeeping"]:
            bookkeeping[squash(book_row["Name"])].append(book_row)
        used_bookkeeping = set()
        promotions = {}
        staff = self.staff_members()

        for row in self.tables["Appointments"]:
            where = f"Appointments id {row['id']}"
            baserow_id = int(row["id"])
            fix = fixes.pop(baserow_id, {})
            customer = self.customer_for(row["Customer"])
            if customer is None:
                self.report.cannot_place(where, f"its customer {squash(row['Customer'])!r} is not a customer in the export")
                continue
            if fix:
                self.check_name(where, fix, "customer_name_on_export", str(customer))
                if fix.get("date_on_export") and not squash(str(fix["date_on_export"])).startswith(squash(row["Date"])):
                    self.report.warn(where, f"the corrections file expects the date {fix['date_on_export']!r}, the export has {row['Date']!r}")
            status = STATUSES.get(squash(row["Status"]).lower())
            try:
                start = parsing.utc_datetime(row["Date"])
                hours = parsing.minutes(row["Hours"])
                list_price = parsing.money(row["List Price"])
                promo_price = parsing.money(row["Promo Price"])
                final_price = parsing.money(row["Final Price"])
                override = parsing.money(row["Price Override"])
            except ValueError as error:
                self.report.cannot_place(where, str(error))
                continue
            if status is None:
                self.report.cannot_place(where, f"unknown status {row['Status']!r}")
                continue
            vehicle = None
            for name, value in (fix.get("set") or {}).items():
                if name == "final_price":
                    final_price = parsing.money(str(value))
                    self.report.correction(where, f"set final price ({fix.get('reason', 'no reason given')})")
                elif name == "vehicle_baserow_id":
                    vehicle = self.fixed_vehicle(where, value, customer, fix)
                else:
                    self.report.warn(where, f"the corrections file sets {name!r}, which the import does not know")

            names = parsing.split_list(row["Staff"])
            crew_size = min(max(len(names), 1), 2)
            values = launch_values()
            times = {"setup_minutes": None, "service_minutes": None, "breakdown_minutes": None}
            if hours is not None:
                # Hours is the whole time on site; setup and breakdown are split by the crew.
                setup = round_to_nearest(Decimal(values.setup_minutes_one_person) / crew_size, 1)
                breakdown = round_to_nearest(Decimal(values.breakdown_minutes_one_person) / crew_size, 1)
                times = {
                    "setup_minutes": setup,
                    "service_minutes": max(hours - setup - breakdown, 0),
                    "breakdown_minutes": breakdown,
                }
            notes = "\n".join(part for part in (squash(row["Notes"]), squash(row["Service Summary"]) and f"Service summary: {squash(row['Service Summary'])}") if part)
            appointment, created = Appointment.objects.update_or_create(
                baserow_id=baserow_id,
                defaults={
                    "customer": customer,
                    "vehicle": vehicle or self.vehicle_for(row, customer),
                    "service_address": self.addresses.get(customer.baserow_id),
                    "scheduled_start": start,
                    "status": status,
                    "source": Appointment.Source.IMPORT,
                    "crew_size": crew_size,
                    "completed_at": start if status == Appointment.Status.COMPLETED else None,
                    "notes": notes,
                    **times,
                },
            )
            self.report.count(f"{status} appointments", created)
            if hours is None:
                self.report.count(f"{status} appointments with no hours recorded")

            appointment.lines.all().delete()
            self.add_lines(appointment, row, list_price, promo_price, final_price, override, fix, promotions, where)

            # Payments: the Bookkeeping row named in the appointment, with any fixes.
            book_rows = bookkeeping.get(squash(row["Bookkeeping"]), []) if squash(row["Bookkeeping"]) else []
            if squash(row["Bookkeeping"]) and len(book_rows) != 1:
                self.report.cannot_place(where, f"its Bookkeeping value matches {len(book_rows)} Bookkeeping rows, not one")
                book_rows = []
            book_row = book_rows[0] if book_rows else None
            if book_row:
                used_bookkeeping.add(book_row["id"])
            self.import_payments(appointment, row, book_row, fix, bookkeeping_fixes, where)
            self.import_staff(appointment, row, book_row, names, staff, fix, where)

        for book_row in self.tables["Bookkeeping"]:
            if book_row["id"] not in used_bookkeeping:
                self.report.cannot_place(f"Bookkeeping id {book_row['id']}", "no appointment names this Bookkeeping row")
        for baserow_id in fixes:
            self.report.cannot_place(f"appointment_fixes baserow_id {baserow_id}", "no appointment with that id in the export")
        for baserow_id in set(bookkeeping_fixes) - {int(i) for i in used_bookkeeping}:
            self.report.cannot_place(f"bookkeeping_fixes bookkeeping_id {baserow_id}", "no imported appointment uses that Bookkeeping row")

    def add_lines(self, appointment, row, list_price, promo_price, final_price, override, fix, promotions, where):
        """Lines at the price actually charged: the services at the list price,
        any promotion, then an adjustment or a no-charge line so the lines add
        up to the final price."""
        items = parsing.services(row["Service Name"])
        job_class = self.classes.get(squash(row["Vehicle Type"]))
        price = list_price if list_price is not None else (final_price or ZERO)
        position = 0

        def add(**fields):
            nonlocal position
            AppointmentLine.objects.create(appointment=appointment, position=position, **fields)
            position += 1
            self.report.count("appointment lines")

        if not items:
            self.report.warn(where, "no service recorded; imported as a custom line")
            add(kind=AppointmentLine.Kind.CUSTOM, description="Imported job (no service recorded)", amount=price)
        for index, item in enumerate(items):
            vehicle_class = self.classes.get(item.vehicle_class) or job_class
            service = self.services.get(item.service)
            amount = price if index == 0 else ZERO
            description = item.service if index == 0 else f"{item.service} (price included in the first line)"
            size_variant = (
                vehicle_class.size_variants.filter(value=item.rows).first() if vehicle_class and item.rows else None
            )
            snapshot = {
                "vehicle_class": vehicle_class,
                "vehicle_class_name": vehicle_class.name if vehicle_class else "",
                "size_variant": size_variant,
                "size_variant_value": size_variant.value if size_variant else None,
                "size_variant_label": size_variant.label if size_variant else "",
            }
            if service is None or service.kind == Service.Kind.CUSTOM or vehicle_class is None:
                # Misc Services, a service not on any list, or a vehicle with no
                # class such as a motorcycle: a custom line at the price charged.
                if service is None and item.service != "Misc Services":
                    self.report.warn(where, f"unknown service {item.service!r}; imported as a custom line")
                add(kind=AppointmentLine.Kind.CUSTOM, description=description, amount=amount, service=service, **snapshot)
                continue
            kind = AppointmentLine.Kind.ADD_ON if service.kind == Service.Kind.ADD_ON else AppointmentLine.Kind.SERVICE
            add(kind=kind, description=description, amount=amount, service=service, **snapshot)
        total = price

        names = [name for name in (squash(row["Promotion"]), squash(row["Auto Promo"])) if name]
        if names and promo_price is not None and promo_price < price:
            promotion = self.promotion(names[0], row, promotions)
            add(kind=AppointmentLine.Kind.PROMOTION, description=promotion.name, amount=promo_price - price, promotion=promotion)
            total = promo_price

        no_charge = fix.get("no_charge")
        if final_price is None:
            final_price = total
        if final_price == 0 and appointment.status == Appointment.Status.COMPLETED:
            reason = (no_charge or {}).get("reason") or "Final price $0 in Baserow"
            if no_charge:
                self.report.correction(where, f"no-charge job ({fix.get('reason', reason)})")
            else:
                self.report.warn(where, "final price $0 with no reason in the corrections file; imported as a no-charge job")
            if total:
                add(kind=AppointmentLine.Kind.NO_CHARGE, description="No charge", amount=-total, reason=reason)
            self.report.count("no-charge jobs")
        elif final_price != total:
            reason = "Price override in Baserow" if override is not None else "Final price in Baserow"
            add(kind=AppointmentLine.Kind.ADJUSTMENT, description="Price adjustment", amount=final_price - total, reason=reason)

    def promotion(self, name, row, promotions):
        """The promotion a past job used, created inactive for the owner to
        review if it does not exist yet."""
        if name in promotions:
            return promotions[name]
        promotion = Promotion.objects.filter(name=name).first()
        if promotion is None:
            kind = PROMO_KINDS.get(squash(row["Promo Type"]).lower(), Promotion.Kind.AMOUNT_OFF)
            value = parsing.money(row["Promo Value"]) or ZERO
            if kind == Promotion.Kind.PERCENT_OFF:
                value = min(value, Decimal("100"))
            promotion = Promotion.objects.create(
                name=name,
                kind=kind,
                value=value,
                active=False,
                notes="Created by the Baserow import from past jobs. Check it before turning it on.",
            )
            self.report.count("promotions created (inactive)")
        promotions[name] = promotion
        return promotion

    # Payments -------------------------------------------------------------

    def already_in_books(self):
        if self.batch is None:
            today = timezone.localdate()
            self.batch, _ = ExportBatch.objects.get_or_create(
                file_name=ALREADY_IN_BOOKS,
                defaults={
                    "date_from": today,
                    "date_to": today,
                    "notes": "Payments and payouts imported from Baserow, already in the owner's GnuCash books."
                    " The GnuCash export never sends them again.",
                },
            )
        return self.batch

    def save_payment(self, appointment, key, where, **fields):
        fields.setdefault("export_batch", self.already_in_books())
        _, created = Payment.objects.update_or_create(import_key=key, defaults={"appointment": appointment, **fields})
        self.payment_dates.append(fields["paid_at"])
        self.report.count("payments", created)

    def import_payments(self, appointment, row, book_row, fix, bookkeeping_fixes, where):
        try:
            self._import_payments(appointment, row, book_row, fix, bookkeeping_fixes, where)
        except (ValueError, KeyError, TypeError) as error:
            self.report.cannot_place(where, f"payment: {error}")

    def _import_payments(self, appointment, row, book_row, fix, bookkeeping_fixes, where):
        keys = []
        if fix.get("payment"):
            given = fix["payment"]
            payment_method = method(given["method"])
            key = f"appointment:{appointment.baserow_id}:payment"
            self.save_payment(
                appointment,
                key,
                where,
                method=payment_method,
                amount=parsing.money(str(given["amount"])),
                tip=ZERO,
                paid_at=appointment.scheduled_start,
                goods_description=str(given.get("received", "")) if payment_method == PaymentMethod.TRADE else "",
                notes=str(given.get("received", "")) if payment_method != PaymentMethod.TRADE else "",
            )
            keys.append(key)
            self.report.correction(where, f"payment from the corrections file ({fix.get('reason', 'no reason given')})")
        elif book_row is not None:
            key = f"bookkeeping:{book_row['id']}"
            if self.bookkeeping_payment(appointment, row, book_row, fix, bookkeeping_fixes, key, where):
                keys.append(key)
        if fix.get("prepaid"):
            keys.extend(self.prepaid(appointment, fix, keys, where))
        # A re-run drops imported payments the exports no longer give.
        Payment.objects.filter(appointment=appointment, import_key__isnull=False).exclude(import_key__in=keys).delete()

    def prepaid(self, appointment, fix, keys, where):
        """A job paid before it happens. When Bookkeeping already records the
        payment, the entry is a check that it does; otherwise it is the payment."""
        prepaid = fix["prepaid"]
        amount = parsing.money(str(prepaid["amount"]))
        payment_method = method(prepaid["method"])
        reason = fix.get("reason", "no reason given")
        self.report.count("prepaid jobs")
        found = Payment.objects.filter(appointment=appointment, import_key__in=keys).first()
        if found is not None:
            if (found.method, found.amount + found.tip) != (payment_method, amount) and found.amount != amount:
                self.report.warn(where, "the prepayment in Bookkeeping differs from the corrections file's prepaid entry")
            else:
                self.report.correction(where, "prepaid: found in Bookkeeping as the corrections file expects")
            return []
        received = prepaid.get("received")
        if isinstance(received, datetime.date):
            paid_at = timezone.make_aware(datetime.datetime.combine(received, datetime.time(12)))
        else:
            paid_at = parsing.utc_datetime(str(received))
        key = f"appointment:{appointment.baserow_id}:prepaid"
        self.save_payment(
            appointment, key, where, method=payment_method, amount=amount, tip=ZERO, paid_at=paid_at,
            notes=str(prepaid.get("note", "Prepaid")),
        )
        self.report.correction(where, f"prepaid payment from the corrections file ({reason})")
        return [key]

    def bookkeeping_payment(self, appointment, row, book_row, fix, bookkeeping_fixes, key, where):
        book_where = f"Bookkeeping id {book_row['id']}"
        values = {
            "invoice": book_row["Invoice"],
            "customer_paid": book_row["Customer Paid"],
            "tip": book_row["Tip"],
            "payment_method": book_row["Payment Method"],
        }
        book_fix = bookkeeping_fixes.get(int(book_row["id"]))
        if book_fix:
            self.check_name(book_where, book_fix, "customer_name_on_export", str(appointment.customer))
            for name, value in (book_fix.get("set") or {}).items():
                if name not in values:
                    self.report.warn(book_where, f"the corrections file sets {name!r}, which the import does not know")
                    continue
                values[name] = str(value)
                self.report.correction(book_where, f"set {name} ({book_fix.get('reason', 'no reason given')})")
        try:
            paid = parsing.money(values["customer_paid"])
            tip = parsing.money(values["tip"]) or ZERO
            paid_at = parsing.utc_datetime(book_row["Date"]) if squash(book_row["Date"]) else appointment.scheduled_start
            methods = [method(text) for text in parsing.split_list(values["payment_method"])]
        except ValueError as error:
            self.report.cannot_place(book_where, str(error))
            return False
        expect = fix.get("expect") or {}
        for name, expected in expect.items():
            actual = {"final_price": appointment.total_before_tax, "customer_paid": paid, "tip": tip}.get(name)
            if name == "payment_method":
                ok = [method(t) for t in parsing.split_list(str(expected))] == methods
            else:
                ok = actual == parsing.money(str(expected))
            if not ok:
                self.report.warn(where, f"the corrections file expects {name} {expected}, the import has a different value")
        if expect:
            self.report.correction(where, f"checked expected values ({fix.get('reason', 'no reason given')})")
        if paid is None or (paid == 0 and not methods):
            # Nothing was paid: a no-charge job, or a booked one not yet paid.
            if appointment.status == Appointment.Status.COMPLETED and appointment.total_before_tax > 0:
                self.report.warn(book_where, "a completed job with no payment recorded")
            return False
        if not methods:
            self.report.cannot_place(book_where, "a payment with no payment method")
            return False
        if len(methods) > 2:
            self.report.cannot_place(book_where, "more than two payment methods")
            return False
        amount = paid - tip
        if amount < 0:
            self.report.cannot_place(book_where, "the tip is more than the customer paid")
            return False
        self.save_payment(
            appointment,
            key,
            where,
            method=methods[0],
            # One payment split between two methods; the split was never recorded
            # (corrections file, rules.payment_methods).
            split_method=methods[1] if len(methods) == 2 else "",
            amount=amount,
            tip=tip,
            paid_at=paid_at,
        )
        if len(methods) == 2:
            self.report.count("split payments")
        if tip < 0:
            self.report.count("payments with a negative tip")
        return True

    # Staff ----------------------------------------------------------------

    def staff_members(self):
        """Every staff name in the exports, matched to a staff member by name.
        A name with no record is created: the owner when it is the --owner
        name, otherwise a family helper, the only pay type in use. The owner
        is never a helper (corrections file, rules.helper_pay): a record with
        the --owner name that an earlier run made a helper becomes the owner."""
        names = {
            name for row in self.tables["Appointments"] for name in parsing.split_list(row["Staff"])
        }
        found = {}
        for name in sorted(names):
            member = StaffMember.objects.filter(name__iexact=name).first()
            if member is not None and member.role != StaffMember.Role.OWNER and name.lower() == self.owner_name:
                member.role, member.pay_type, member.default_job_pay = StaffMember.Role.OWNER, "", None
                member.save(update_fields=["role", "pay_type", "default_job_pay"])
                self.report.correction(f"staff {name!r}", "the owner, never a helper: changed from helper to owner")
            if member is None:
                if self.owner_name is None and not StaffMember.objects.filter(role=StaffMember.Role.OWNER).exists():
                    self.report.cannot_place(f"staff {name!r}", "not a staff member yet; run with --owner \"<the owner's name as in Baserow>\"")
                    continue
                if name.lower() == self.owner_name:
                    member = StaffMember.objects.create(name=name, role=StaffMember.Role.OWNER)
                else:
                    member = StaffMember.objects.create(name=name, role=StaffMember.Role.HELPER, pay_type=PayType.FAMILY_HELPER)
                self.report.count("staff members created")
            found[name.lower()] = member
        return found

    def import_staff(self, appointment, row, book_row, names, staff, fix, where):
        members = [staff[name.lower()] for name in names if name.lower() in staff]
        Assignment.objects.filter(appointment=appointment).exclude(staff_member__in=members).delete()
        # The owner is never a helper, so with the owner and one helper on the
        # job, the Wage Override is that helper's (corrections file, rules.helper_pay).
        helpers = [member for member in members if member.role != StaffMember.Role.OWNER]
        wage = parsing.money(book_row["Wage Override"]) if book_row else None
        paid = squash(row["Employees Paid"]) == "1"
        pay = self.fixed_helper_pay(where, fix, names, staff)
        if pay:
            total = sum(pay.values())
            if wage is not None and wage != total:
                self.report.warn(where, f"helper_pay totals ${total}, the Wage Override is ${wage}; helper_pay is used")
            reason = f"corrections file: {fix.get('reason', 'no reason given')}"
        elif wage is not None and len(helpers) == 1:
            # Wage Override is the amount paid to the helper for the job.
            pay = {helpers[0]: wage}
            reason = "Wage Override in Baserow"
        else:
            pay = {}
            if wage is not None:
                self.report.warn(where, f"a Wage Override with {len(helpers)} helpers on the job; helper pay not recorded")
            elif paid:
                self.report.warn(where, "Employees Paid is 1 but no Wage Override gives the amount; helper pay not recorded")

        payout_prefix = f"appointment:{appointment.baserow_id}:helper-pay"
        kept = []
        for member in members:
            fields = {"pay_override": None, "override_reason": "", "payout": None}
            if member in pay:
                amount = pay[member]
                fields.update(pay_override=amount, override_reason=reason)
                paid_on = timezone.localtime(appointment.scheduled_start).date()
                if paid:
                    key = f"{payout_prefix}:{member.pk}"
                    payout, created = StaffPayout.objects.update_or_create(
                        import_key=key,
                        defaults={
                            "staff_member": member,
                            "pay_type": member.pay_type,
                            "amount": amount,
                            # Baserow does not record how a helper was paid.
                            "method": StaffPayout.Method.CASH,
                            "paid_on": paid_on,
                            "notes": "Imported from Baserow; how it was paid was not recorded, so it is entered as cash.",
                            "export_batch": self.already_in_books(),
                        },
                    )
                    kept.append(key)
                    fields["payout"] = payout
                    self.report.count("helper payouts", created)
                    self.report.pay(where, f"${amount} to {member.name}, paid {paid_on} as cash ({reason})")
                else:
                    self.report.pay(where, f"${amount} to {member.name}, not paid: Employees Paid is not 1 ({reason})")
            _, created = Assignment.objects.update_or_create(appointment=appointment, staff_member=member, defaults=fields)
            self.report.count("staff assignments", created)
        StaffPayout.objects.filter(
            Q(import_key=payout_prefix) | Q(import_key__startswith=f"{payout_prefix}:")
        ).exclude(import_key__in=kept).delete()

    def fixed_helper_pay(self, where, fix, names, staff):
        """helper_pay: {Name: amount} in an appointment fix, the pay of each
        named helper on the job, used in place of the Wage Override."""
        pay = {}
        on_job = {name.lower() for name in names}
        for name, value in (fix.get("helper_pay") or {}).items():
            member = staff.get(squash(name).lower())
            try:
                amount = parsing.money(str(value))
            except ValueError as error:
                self.report.cannot_place(where, f"helper_pay for {name!r}: {error}")
                continue
            if squash(name).lower() not in on_job or member is None:
                self.report.cannot_place(where, f"helper_pay names {name!r}, who is not in the job's Staff column")
            elif member.role == StaffMember.Role.OWNER:
                self.report.cannot_place(where, f"helper_pay names {name!r}, the owner, who is never a helper")
            elif amount is None:
                self.report.cannot_place(where, f"helper_pay for {name!r} has no amount")
            else:
                pay[member] = amount
                self.report.correction(where, f"helper pay ${amount} to {member.name} ({fix.get('reason', 'no reason given')})")
        return pay

    # The whole run ---------------------------------------------------------

    def run(self):
        if not self.classes or not self.services:
            raise ImportRefused("The pricebook is not loaded: run load_pricebook before the import.")
        self.import_customers()
        self.import_second_contacts()
        self.import_setmore()
        self.import_vehicles()
        self.import_appointments()
        if self.batch is not None and self.payment_dates:
            dates = [timezone.localtime(moment).date() for moment in self.payment_dates]
            ExportBatch.objects.filter(pk=self.batch.pk).update(date_from=min(dates), date_to=max(dates))
        for entry in self.corrections.get("to_confirm") or []:
            self.report.questions.append(f"{entry.get('baserow_id')}: {entry.get('question')} (left alone)")
        for check in self.corrections.get("checks") or []:
            if isinstance(check, dict):
                self.report.checks.extend(f"{key}: {value}" for key, value in check.items())
            else:
                self.report.checks.append(str(check))
        return self.report


def run(tables, corrections, apply=False, owner_name=None):
    """Import everything; roll it all back unless apply is true."""
    report = Report()
    with transaction.atomic():
        Importer(tables, corrections, owner_name=owner_name, report=report).run()
        if not apply:
            transaction.set_rollback(True)
    return report
