"""Apply the classification rules and overrides to every model year in the
vehicle catalog (docs/reference/vehicle-classification.md).

  python manage.py classify_vehicles [--dry-run] [--refresh]
  python manage.py classify_vehicles --scheme size --dry-run

First it brings the launch rules and model overrides in step with
data/vehicle-classes.yaml (leaving alone any the owner edited or deleted)
and loads the third-row list, data/third-row-seating.yaml. With --dry-run it prints the
preview, every model year whose class or size would change or that would
enter or leave the review queue, and changes nothing. It never changes a
model override, a customer's vehicle, or anything with source "owner".

With --refresh, as the monthly refresh runs it, a model year whose class or
size would change is held in the review queue instead when its model has a
model override, an approval or customers' jobs (classification.guard).

With --scheme size --dry-run it previews the size-based classes of
data/size-classes.yaml (decision 0082, classification.sizes) instead, and
changes nothing. The size-based classes cannot be applied yet.
"""

from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from vehicles.classification.engine import apply, change_detail, changes, classify_catalog, record, year_spans, years_text
from vehicles.classification.guard import hold
from vehicles.classification.seed import SeedError, SeedReport, sync_launch_set, sync_seat_list
from vehicles.classification.size_preview import write_report
from vehicles.classification.sizes import classify_scheme
from vehicles.models import ClassificationChange, VehicleModel


def spans(rows):
    """[(vehicle model, year, detail)] -> ["Make Model 2019-2024: detail"],
    joining consecutive years of one model with the same detail."""
    return [f"{model.make} {model.model} {years_text(first, last)}: {detail}" for model, first, last, detail in year_spans(rows)]


class Command(BaseCommand):
    help = "Apply the vehicle classification rules and overrides to the catalog."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print the preview and change nothing.")
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="As the monthly refresh: hold class changes to models with an override, an approval or jobs in the review queue.",
        )
        parser.add_argument(
            "--scheme",
            choices=("body", "size"),
            default="body",
            help="body (the live classes, the default) or size: preview the size-based classes of data/size-classes.yaml.",
        )

    def handle(self, *args, dry_run, refresh, scheme="body", **options):
        if not VehicleModel.objects.exists():
            raise CommandError("The vehicle catalog is empty: run import_vehicle_data first.")
        if scheme == "size":
            return self.preview_sizes(dry_run, refresh)
        seeded = SeedReport()
        with transaction.atomic():
            try:
                sync_launch_set(seeded)
                sync_seat_list(seeded)
            except SeedError as error:
                raise CommandError(str(error)) from error
            results = classify_catalog()
            held = hold(results) if refresh else []
            found = changes(results)
            counts = None if dry_run else apply(results)
            if dry_run:
                transaction.set_rollback(True)
            else:
                summary = f"classify_vehicles applied the rules: {len(found):,} model years changed"
                if refresh:
                    summary = f"Monthly refresh: {summary}, {len(held):,} held in the review queue"
                record(ClassificationChange.Kind.RUN, summary, found)
        # Kept on the command for refresh_vehicle_data, which runs this one.
        self.found, self.held = found, held
        self.print_report(dry_run, seeded, results, found, counts, held if refresh else None)

    def preview_sizes(self, dry_run, refresh):
        """The size-based classes' dry run: loads the third-row list as any
        run does, classifies in memory, prints, and rolls everything back."""
        if not dry_run or refresh:
            raise CommandError("The size-based classes can only be previewed for now: use --scheme size --dry-run, without --refresh.")
        with transaction.atomic():
            try:
                sync_seat_list(SeedReport())
                found = classify_scheme()
            except SeedError as error:
                raise CommandError(str(error)) from error
            write_report(found, self.stdout)
            transaction.set_rollback(True)

    def print_report(self, dry_run, seeded, results, found, counts, held=None):
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
        for method, label in (
            ("rule", "by a rule"),
            ("override", "by a model override"),
            ("decision", "by a review queue decision"),
            ("carried", "from the nearest classified year, the EPA not having published it yet"),
            ("photo_cards", "sent to the photo cards from the review queue"),
            ("review", "in the review queue"),
        ):
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
            if result.vehicle_class is None:
                continue
            by_class[result.vehicle_class.name, result.vehicle_class.sort_order] += 1
            size = "ask" if result.ask_size else (result.size_variant.label if result.size_variant else "one price")
            by_size[result.vehicle_class.name, size] += 1
        for (name, _), count in sorted(by_class.items(), key=lambda item: item[0][1]):
            write(f"  {name}: {count:,}")
            for (class_name, size), sized in sorted(by_size.items()):
                if class_name == name:
                    write(f"    {size}: {sized:,}")

        rows = [(change.vehicle_model, change.year, f"{change_detail(change)} ({change.because})") for change in found]
        write(f"\n{'Would change' if dry_run else 'Changed'} ({len(found):,} model years)")
        for line in spans(rows):
            write(f"  {line}")

        if held is not None:
            write(f"\nHeld in the review queue: the refresh may not change these on its own ({len(held):,} model years)")
            for line in spans([(model_year.vehicle_model, model_year.year, f"{old} -> {new}") for model_year, old, new in held]):
                write(f"  {line}")

        classes = defaultdict(list)
        for model_year, result in results.values():
            if result.vehicle_class is not None:
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
