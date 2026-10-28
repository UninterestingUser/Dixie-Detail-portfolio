"""Load the pricebook from data/ as pricebook version 1, effective today.

Reads data/vehicle-classes.yaml (vehicle classes and size variants),
data/services.yaml, data/pricing-rules.yaml and data/price-matrix.csv, whose
hours are one-person service hours without setup and breakdown (decision
0058). Maintenance plans are stored as derived price rules, not prices. The
price book check (pricebook.checks, decision 0083) runs first, and nothing
is loaded if it fails. In an empty database the retired classes the file
lists are created retired, for the job history.

Once version 1 exists, running it again changes no published price. It adds
any vehicle class, size variant or service the data files have and the
database does not, fills in a class's photo card and example models where it
has none, and compares the matrix with the latest published version. If they
differ, the whole matrix is loaded as a new draft for the owner to publish
(pricebook-changes.md). A class the file renames is found under its old name
until apply_size_classes renames it, and a new class made while the
body-type classes are still live waits as pending, not offered, until
apply_size_classes publishes the draft and switches to it.
"""

import csv
from decimal import Decimal

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from pricebook.checks import MAINTENANCE_PERCENT_KEYS, cell_name, check
from pricebook.models import ConditionLevel, DerivedPriceRule, Price, PricebookVersion, PricingRules, Service
from pricebook.pricing import NotPriced, base_price
from vehicles.classification.switch import switched
from vehicles.models import SizeVariant, VehicleClass

MATRIX_COLUMNS = ["service", "vehicle_class", "size_variant", "one_person_service_hours", "price_usd"]
SERVICE_KINDS = {
    "main": Service.Kind.MAIN,
    "add-on": Service.Kind.ADD_ON,
    "maintenance plan": Service.Kind.MAINTENANCE_PLAN,
}
BOOKING = {"online": VehicleClass.Booking.ONLINE, "ask for a quote": VehicleClass.Booking.QUOTE}


def read_yaml(name):
    return yaml.safe_load((settings.DATA_DIR / name).read_text())


def read_matrix():
    with (settings.DATA_DIR / "price-matrix.csv").open(newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames != MATRIX_COLUMNS:
            raise CommandError(f"price-matrix.csv columns are {reader.fieldnames}, expected {MATRIX_COLUMNS}.")
        return [
            {
                "service": row["service"],
                "vehicle_class": row["vehicle_class"],
                "size_variant": int(row["size_variant"]) if row["size_variant"] else None,
                "hours": Decimal(row["one_person_service_hours"]),
                "price": Decimal(row["price_usd"]),
            }
            for row in reader
        ]


class Command(BaseCommand):
    help = "Load data/price-matrix.csv, services.yaml and pricing-rules.yaml as pricebook version 1, effective today."

    def handle(self, *args, **options):
        data = read_yaml("vehicle-classes.yaml")
        services = read_yaml("services.yaml")
        rules = read_yaml("pricing-rules.yaml")
        matrix = read_matrix()
        problems = check(matrix)
        if problems:
            for problem in problems:
                self.stderr.write(f"  {problem}")
            raise CommandError(f"data/price-matrix.csv fails the price book check in {len(problems)} place(s). Nothing was changed.")

        if PricebookVersion.objects.filter(number=1).exists():
            self.update_existing(data, services, rules, matrix)
            return

        with transaction.atomic():
            self.load_classes(data)
            self.load_services(services)
            version = PricebookVersion.objects.create(number=1, notes="Loaded from data/ by load_pricebook.")
            self.load_rules(version, rules)
            count = self.load_prices(version, matrix, rules, data)
            version.publish(timezone.localdate())
        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded pricebook version 1, effective {version.effective_date}: {count} prices"
                f" and {DerivedPriceRule.objects.filter(version=version).count()} derived price rules"
                f" covering all {len(matrix)} cells of the price matrix."
            )
        )

    def load_classes(self, data):
        """Add the classes and size variants the database lacks, with their
        settings. An existing class keeps the owner's settings; only a
        missing photo card or example list is filled in. A class the file
        renames is left under its old name for apply_size_classes, a new one
        is pending while the body-type classes are live, and a retired one is
        created retired. Returns what was added."""
        added = []
        live = switched()
        entries = [(entry, True) for entry in data["classes"]] + [(entry, False) for entry in data.get("retired_classes") or []]
        for order, (entry, current) in enumerate(entries):
            if current and entry.get("renamed_from") and VehicleClass.objects.filter(name=entry["renamed_from"]).exists():
                if not VehicleClass.objects.filter(name=entry["name"]).exists():
                    continue
            vehicle_class, created = VehicleClass.objects.get_or_create(
                name=entry["name"],
                defaults={
                    "size_variant_measures": entry["size_variant_measures"],
                    "sort_order": order,
                    "booking": BOOKING[entry.get("booking", "online")],
                    "photo_card": entry["photo_card"],
                    "photo_card_examples": entry.get("photo_card_examples") or [],
                    "active": current,
                    "pending": current and not live,
                },
            )
            if created:
                state = "" if current and live else (" (pending until apply_size_classes)" if current else " (retired)")
                added.append(f"vehicle class {vehicle_class}{state}")
            elif current and (not vehicle_class.photo_card or (not vehicle_class.photo_card_examples and entry.get("photo_card_examples"))):
                vehicle_class.photo_card = vehicle_class.photo_card or entry["photo_card"]
                vehicle_class.photo_card_examples = vehicle_class.photo_card_examples or entry.get("photo_card_examples") or []
                vehicle_class.save()
                added.append(f"photo card for {vehicle_class}")
            for value, label in (entry.get("size_variants") or {}).items():
                _, created = SizeVariant.objects.get_or_create(
                    vehicle_class=vehicle_class, value=int(value), defaults={"label": label}
                )
                if created:
                    added.append(f"size variant {value} of {vehicle_class}")
        return added

    @staticmethod
    def class_named(name, data):
        """The class a matrix row names: by its name, or by the old name of a
        class the file renames and apply_size_classes has not renamed yet."""
        found = VehicleClass.objects.filter(name=name).first()
        if found is None:
            old = next((entry.get("renamed_from") for entry in data["classes"] if entry["name"] == name), None)
            found = VehicleClass.objects.filter(name=old).first() if old else None
        if found is None:
            raise VehicleClass.DoesNotExist(f"No vehicle class {name!r}.")
        return found

    def load_services(self, services):
        """Add the services the database lacks. Returns their names."""
        added = []
        for entry in services["services"]:
            service, created = Service.objects.get_or_create(
                name=entry["name"],
                defaults={
                    "kind": SERVICE_KINDS[entry["kind"]],
                    "description": entry.get("description", ""),
                    "condition_applies": entry["condition_applies"],
                    "customer_bookable": "customer" in entry["booked_by"],
                    "default_crew_size": entry.get("default_crew", 1),
                },
            )
            if created:
                added.append(f"service {service}")
        for entry in services["custom_lines"]:
            Service.objects.get_or_create(
                name=entry["name"], defaults={"kind": Service.Kind.CUSTOM, "description": entry.get("use", "")}
            )
        for entry in services["history_only_services"]:
            Service.objects.get_or_create(
                name=entry["name"], defaults={"kind": Service.Kind.MAIN, "on_price_list": False}
            )
        return added

    def load_rules(self, version, rules):
        crew = rules["crew"]
        PricingRules.objects.create(
            version=version,
            two_person_time_factor=Decimal(str(crew["two_person_time_factor"])),
            service_time_rounding_minutes=crew["service_time_rounding_minutes"],
            full_day_time_on_site_hours=Decimal(str(rules["full_day_flag"]["threshold_one_person_time_on_site_hours"])),
        )
        for level in rules["condition_levels"]["levels"]:
            ConditionLevel.objects.create(
                version=version,
                level=level["level"],
                adjustment_percent=Decimal(str(level["adjustment_percent"])),
                label=level.get("mockup_label", ""),
            )
        plans = rules["maintenance_plans"]
        base_service = Service.objects.get(name=plans["base_service"])
        for name, key in MAINTENANCE_PERCENT_KEYS.items():
            DerivedPriceRule.objects.create(
                version=version,
                service=Service.objects.get(name=name),
                base_service=base_service,
                percent=Decimal(str(plans[key])),
            )

    def load_prices(self, version, matrix, rules, data):
        """Store the matrix's prices; the maintenance plans, which the check
        found to follow their rules, are the rules themselves."""
        derived = {rule.service.name for rule in DerivedPriceRule.objects.filter(version=version)}
        count = 0
        for row in matrix:
            if row["service"] in derived:
                continue
            try:
                service = Service.objects.get(name=row["service"])
                vehicle_class = self.class_named(row["vehicle_class"], data)
                size_variant = (
                    SizeVariant.objects.get(vehicle_class=vehicle_class, value=row["size_variant"])
                    if row["size_variant"] is not None
                    else None
                )
            except (Service.DoesNotExist, VehicleClass.DoesNotExist, SizeVariant.DoesNotExist) as error:
                raise CommandError(f"price-matrix.csv row {row}: {error}") from error
            Price.objects.create(
                version=version,
                service=service,
                vehicle_class=vehicle_class,
                size_variant=size_variant,
                price=row["price"],
                one_person_service_hours=row["hours"],
            )
            count += 1
        return count

    def update_existing(self, data, services, rules, matrix):
        """Version 1 exists: add what the database lacks, and load the matrix
        as a new draft when it differs from the latest published version."""
        latest = PricebookVersion.objects.filter(status=PricebookVersion.Status.PUBLISHED).order_by("-number").first()
        with transaction.atomic():
            added = self.load_classes(data) + self.load_services(services)
            differences, dropped = self.compare(latest, matrix, data)
            draft = None
            if differences:
                open_draft = PricebookVersion.objects.filter(status=PricebookVersion.Status.DRAFT).first()
                if open_draft is not None:
                    raise CommandError(
                        f"data/price-matrix.csv differs from version {latest.number} in {len(differences)} place(s), and draft"
                        f" version {open_draft.number} is open. Publish or discard it, then run load_pricebook again."
                        " Nothing was changed."
                    )
                last = PricebookVersion.objects.order_by("-number").first()
                draft = PricebookVersion.objects.create(
                    number=last.number + 1, notes="The price book in data/price-matrix.csv, loaded by load_pricebook."
                )
                self.load_rules(draft, rules)
                self.load_prices(draft, matrix, rules, data)
        for line in added:
            self.stdout.write(f"Added {line}.")
        if draft is None:
            if added:
                self.stdout.write(f"Pricebook version {latest.number} matches the data files; no price was changed.")
            else:
                self.stdout.write(
                    f"Pricebook version {latest.number} is already loaded and matches the data files. Nothing was changed."
                )
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Draft version {draft.number} holds data/price-matrix.csv, which differs from version {latest.number}"
                f" in {len(differences)} place(s):"
            )
        )
        for line in differences:
            self.stdout.write(f"  {line}")
        if dropped:
            self.stdout.write(f"Version {latest.number} prices {len(dropped)} cell(s) the draft does not:")
            for line in dropped:
                self.stdout.write(f"  {line}")
        if VehicleClass.objects.filter(pending=True).exists():
            self.stdout.write(
                "It prices classes not offered yet: publish it with apply_size_classes --effective YYYY-MM-DD,"
                " which switches the catalog to them in the same step (docs/operations/classifying-vehicles.md)."
            )
        else:
            self.stdout.write("Publish it from the control app's pricebook page, with an effective date.")

    def compare(self, version, matrix, data):
        """([how each matrix cell differs from the version], [cells the version
        prices that the matrix does not])."""
        differences, seen = [], set()
        for row in matrix:
            try:
                vehicle_class = self.class_named(row["vehicle_class"], data)
                service = Service.objects.get(name=row["service"])
                size_variant = vehicle_class.size_variants.get(value=row["size_variant"]) if row["size_variant"] else None
                seen.add((service.pk, vehicle_class.pk, getattr(size_variant, "pk", None)))
                found = base_price(version, service, vehicle_class, size_variant)
            except NotPriced:
                differences.append(f"{cell_name(row)}: new, ${row['price']} and {row['hours']} hours")
                continue
            except (Service.DoesNotExist, VehicleClass.DoesNotExist, SizeVariant.DoesNotExist):
                differences.append(f"{cell_name(row)}: new, ${row['price']} and {row['hours']} hours")
                continue
            if vehicle_class.name != row["vehicle_class"]:
                differences.append(f"{cell_name(row)}: the class is now {vehicle_class.name}, renamed by apply_size_classes")
            if (found.price, found.one_person_service_hours) != (row["price"], row["hours"]):
                differences.append(
                    f"{cell_name(row)}: version {version.number} has ${found.price} and"
                    f" {found.one_person_service_hours} hours, the file ${row['price']} and {row['hours']} hours"
                )
        dropped = [
            f"{price.service} / {price.vehicle_class}{f' size {price.size_variant.value}' if price.size_variant else ''}"
            for price in Price.objects.filter(version=version).select_related("service", "vehicle_class", "size_variant")
            if (price.service_id, price.vehicle_class_id, price.size_variant_id) not in seen
        ]
        return differences, dropped
