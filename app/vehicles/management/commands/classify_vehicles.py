"""Apply the classification rules and overrides to every model year in the
vehicle catalog (docs/reference/vehicle-classification.md).

  python manage.py classify_vehicles [--dry-run]

First it brings the launch rules and model overrides in step with
data/vehicle-classes.yaml (leaving alone any the owner edited or deleted)
and loads the third-row list, data/third-row-seating.yaml. With --dry-run it prints the
preview, every model year whose class or size would change or that would
enter or leave the review queue, and changes nothing. It never changes a
model override, a customer's vehicle, or anything with source "owner".
"""

from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from vehicles.classification.engine import apply, changes, classify_catalog
from vehicles.classification.seed import SeedError, SeedReport, sync_launch_set, sync_seat_list
from vehicles.models import VehicleModel


def spans(rows):
    """[(vehicle model, year, detail)] -> ["Make Model 2019-2024: detail"],
    joining consecutive years of one model with the same detail."""
    lines = []
    current = None
    for vehicle_model, year, detail in sorted(rows, key=lambda row: (row[0].make, row[0].model, row[0].pk, row[1])):
        if current and current[0].pk == vehicle_model.pk and current[3] == detail and current[2] == year - 1:
            current[2] = year
            continue
        if current:
            lines.append(current)
        current = [vehicle_model, year, year, detail]
    if current:
        lines.append(current)
    return [
        f"{model.make} {model.model} {first}{'' if first == last else f'-{last}'}: {detail}"
        for model, first, last, detail in lines
    ]


def describe(vehicle_class, size):
    if vehicle_class is None:
        return "no class"
    return f"{vehicle_class} ({size})" if size else str(vehicle_class)


class Command(BaseCommand):
    help = "Apply the vehicle classification rules and overrides to the catalog."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print the preview and change nothing.")

    def handle(self, *args, dry_run, **options):
        if not VehicleModel.objects.exists():
            raise CommandError("The vehicle catalog is empty: run import_vehicle_data first.")
        seeded = SeedReport()
        with transaction.atomic():
            try:
                sync_launch_set(seeded)
                sync_seat_list(seeded)
            except SeedError as error:
                raise CommandError(str(error)) from error
            results = classify_catalog()
            found = changes(results)
            counts = None if dry_run else apply(results)
            if dry_run:
                transaction.set_rollback(True)
        self.print_report(dry_run, seeded, results, found, counts)

    def print_report(self, dry_run, seeded, results, found, counts):
        write = self.stdout.write
        write("DRY RUN: nothing was changed. Run again without --dry-run to apply it." if dry_run else "APPLIED: the classifications were saved.")
        write(f"\nLaunch rules and overrides (data/vehicle-classes.yaml): {len(seeded.launch_set):,} changes")
        for line in seeded.launch_set:
            write(f"  {line}")
        for line in seeded.unmatched_overrides:
            write(f"  Override not applied: {line}")

        write("\nThird-row seating list (data/third-row-seating.yaml)")
        for name in ("model years added", "model years changed", "model years unchanged", "model years removed"):
            write(f"  {name}: {seeded.counts.get(name, 0):,}")
        write(f"\n  Rows not matched to the catalog, left for the owner ({len(seeded.unmatched_seat_rows):,})")
        for line in seeded.unmatched_seat_rows:
            write(f"    {line}")

        methods = Counter(result.method for _, result in results.values())
        write(f"\nModel years: {len(results):,}")
        for method, label in (("rule", "by a rule"), ("override", "by a model override"), ("review", "in the review queue")):
            write(f"  {label}: {methods.get(method, 0):,}")
        asks = sum(1 for _, result in results.values() if result.ask_size)
        write(f"  the booking form asks the size: {asks:,}")
        if counts:
            for name, count in counts.items():
                write(f"  {name}: {count:,}")

        write("\nModel years by class and size (classified ones; the review queue is listed below)")
        by_class = Counter()
        by_size = Counter()
        for _, result in results.values():
            if result.in_review:
                continue
            by_class[result.vehicle_class.name, result.vehicle_class.sort_order] += 1
            size = "ask" if result.ask_size else (result.size_variant.label if result.size_variant else "one price")
            by_size[result.vehicle_class.name, size] += 1
        for (name, _), count in sorted(by_class.items(), key=lambda item: item[0][1]):
            write(f"  {name}: {count:,}")
            for (class_name, size), sized in sorted(by_size.items()):
                if class_name == name:
                    write(f"    {size}: {sized:,}")

        rows = []
        for change in found:
            detail = f"{describe(change.old_class, change.old_size)} -> {describe(change.new_class, change.new_size)}"
            if change.entering_review:
                detail += ", enters the review queue"
            elif change.leaving_review:
                detail += ", leaves the review queue"
            rows.append((change.vehicle_model, change.year, f"{detail} ({change.because})"))
        write(f"\n{'Would change' if dry_run else 'Changed'} ({len(found):,} model years)")
        for line in spans(rows):
            write(f"  {line}")

        classes = defaultdict(list)
        for model_year, result in results.values():
            if not result.in_review:
                classes[model_year.vehicle_model.pk].append((model_year.year, result.vehicle_class.name, model_year.vehicle_model))
        mixed = []
        for found in classes.values():
            if len({name for _, name, _ in found}) > 1:
                vehicle_model = found[0][2]
                prefix = f"{vehicle_model.make} {vehicle_model.model} "
                parts = [line[len(prefix):] for line in spans([(model, year, name) for year, name, model in found])]
                mixed.append(f"{prefix.strip()}: " + "; ".join(parts))
        write(f"\nModels whose years are in different classes, for the owner to look at ({len(mixed):,})")
        for line in sorted(mixed):
            write(f"  {line}")

        waiting = [
            (model_year.vehicle_model, model_year.year, "; ".join(result.reasons))
            for model_year, result in results.values()
            if result.in_review
        ]
        write(f"\nWaiting in the review queue ({len(waiting):,} model years)")
        for line in spans(waiting):
            write(f"  {line}")
