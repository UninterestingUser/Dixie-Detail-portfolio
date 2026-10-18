"""Load the pricebook from data/ as pricebook version 1, effective today.

Reads data/vehicle-classes.yaml (vehicle classes and size variants),
data/services.yaml, data/pricing-rules.yaml and data/price-matrix.csv, whose
hours are one-person service hours without setup and breakdown (decision
0058). Maintenance plans are stored as derived price rules, not prices, after
checking that their rows in the matrix agree with the rule.

Running it again changes nothing: once version 1 exists, the command only
reports whether it still matches the data files. A later change is a new
draft, published with an effective date (pricebook-changes.md).
"""

import csv
from decimal import Decimal

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from pricebook.models import ConditionLevel, DerivedPriceRule, Price, PricebookVersion, PricingRules, Service
from pricebook.pricing import NotPriced, base_price, to_cents
from vehicles.models import SizeVariant, VehicleClass

MATRIX_COLUMNS = ["service", "vehicle_class", "size_variant", "one_person_service_hours", "price_usd"]
SERVICE_KINDS = {
    "main": Service.Kind.MAIN,
    "add-on": Service.Kind.ADD_ON,
    "maintenance plan": Service.Kind.MAINTENANCE_PLAN,
}
MAINTENANCE_PERCENT_KEYS = {
    "Quarterly Maintenance": "quarterly_percent_of_full_detail",
    "Monthly Maintenance": "monthly_percent_of_full_detail",
}


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
        classes = read_yaml("vehicle-classes.yaml")["classes"]
        services = read_yaml("services.yaml")
        rules = read_yaml("pricing-rules.yaml")
        matrix = read_matrix()

        version = PricebookVersion.objects.filter(number=1).first()
        if version is not None:
            self.report_existing(version, matrix, rules)
            return

        with transaction.atomic():
            self.load_classes(classes)
            self.load_services(services)
            version = PricebookVersion.objects.create(number=1, notes="Loaded from data/ by load_pricebook.")
            self.load_rules(version, rules)
            count = self.load_prices(version, matrix, rules)
            version.publish(timezone.localdate())
        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded pricebook version 1, effective {version.effective_date}: {count} prices"
                f" and {DerivedPriceRule.objects.filter(version=version).count()} derived price rules"
                f" covering all {len(matrix)} cells of the price matrix."
            )
        )

    def load_classes(self, classes):
        for order, entry in enumerate(classes):
            vehicle_class, _ = VehicleClass.objects.get_or_create(
                name=entry["name"],
                defaults={"size_variant_measures": entry["size_variant_measures"], "sort_order": order},
            )
            for value, label in entry.get("size_variants", {}).items():
                SizeVariant.objects.get_or_create(
                    vehicle_class=vehicle_class, value=int(value), defaults={"label": label}
                )

    def load_services(self, services):
        for entry in services["services"]:
            Service.objects.get_or_create(
                name=entry["name"],
                defaults={
                    "kind": SERVICE_KINDS[entry["kind"]],
                    "description": entry.get("description", ""),
                    "condition_applies": entry["condition_applies"],
                    "customer_bookable": "customer" in entry["booked_by"],
                    "default_crew_size": entry.get("default_crew", 1),
                },
            )
        for entry in services["custom_lines"]:
            Service.objects.get_or_create(
                name=entry["name"], defaults={"kind": Service.Kind.CUSTOM, "description": entry.get("use", "")}
            )
        for entry in services["history_only_services"]:
            Service.objects.get_or_create(
                name=entry["name"], defaults={"kind": Service.Kind.MAIN, "on_price_list": False}
            )

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

    def load_prices(self, version, matrix, rules):
        derived = {rule.service.name: rule for rule in DerivedPriceRule.objects.filter(version=version)}
        base_name = rules["maintenance_plans"]["base_service"]
        base_rows = {
            (row["vehicle_class"], row["size_variant"]): row for row in matrix if row["service"] == base_name
        }
        count = 0
        for row in matrix:
            try:
                service = Service.objects.get(name=row["service"])
                vehicle_class = VehicleClass.objects.get(name=row["vehicle_class"])
                size_variant = (
                    SizeVariant.objects.get(vehicle_class=vehicle_class, value=row["size_variant"])
                    if row["size_variant"] is not None
                    else None
                )
            except (Service.DoesNotExist, VehicleClass.DoesNotExist, SizeVariant.DoesNotExist) as error:
                raise CommandError(f"price-matrix.csv row {row}: {error}") from error
            rule = derived.get(service.name)
            if rule is None:
                Price.objects.create(
                    version=version,
                    service=service,
                    vehicle_class=vehicle_class,
                    size_variant=size_variant,
                    price=row["price"],
                    one_person_service_hours=row["hours"],
                )
                count += 1
                continue
            # A maintenance plan's row must agree with its rule, which is what is stored.
            base = base_rows.get((row["vehicle_class"], row["size_variant"]))
            if base is None:
                raise CommandError(f"{service} has no {base_name} price to follow for {row}.")
            expected = to_cents(base["price"] * rule.percent / 100)
            if row["price"] != expected or row["hours"] != base["hours"]:
                raise CommandError(
                    f"price-matrix.csv says {service} for {vehicle_class} size {row['size_variant']} is"
                    f" ${row['price']} and {row['hours']} hours; the rule gives ${expected} and {base['hours']} hours."
                )
        return count

    def report_existing(self, version, matrix, rules):
        differences = []
        for row in matrix:
            try:
                vehicle_class = VehicleClass.objects.get(name=row["vehicle_class"])
                size_variant = (
                    vehicle_class.size_variants.get(value=row["size_variant"]) if row["size_variant"] else None
                )
                found = base_price(version, Service.objects.get(name=row["service"]), vehicle_class, size_variant)
            except (NotPriced, Service.DoesNotExist, VehicleClass.DoesNotExist, SizeVariant.DoesNotExist):
                differences.append(f"not in version 1: {row}")
                continue
            if (found.price, found.one_person_service_hours) != (row["price"], row["hours"]):
                differences.append(
                    f"{row['service']} / {row['vehicle_class']} size {row['size_variant']}: version 1 has"
                    f" ${found.price} and {found.one_person_service_hours} hours, the file ${row['price']}"
                    f" and {row['hours']} hours"
                )
        if differences:
            for difference in differences:
                self.stderr.write(f"  {difference}")
            raise CommandError(
                f"Pricebook version 1 already exists and differs from the data files in {len(differences)} place(s)."
                " Nothing was changed. Make the change as a new pricebook draft."
            )
        self.stdout.write("Pricebook version 1 is already loaded and matches the data files. Nothing was changed.")
