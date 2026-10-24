"""Link every customer's vehicle to its model in the vehicle catalog
(docs/operations/linking-vehicles.md, decision 0077).

  python manage.py link_vehicles [--dry-run]

Each vehicle is matched by year, make and model with the names in
data/vehicle-names.yaml. A match sets the vehicle's catalog model and fills
a missing class or size variant from the catalog; a class the vehicle
already has never changes here, and differences wait for the owner on the
control app's differences screen. The imported motorcycle jobs get the
Motorcycles class and the Motorcycle Detail service, with their amounts and
payments as imported (decision 0078). With --dry-run it prints the report
and changes nothing. The report names vehicles by id, year, make, model and
color only, never by customer.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from vehicles.linking import catalog_label, describe, describe_model, link_vehicles
from vehicles.models import VehicleModel


class Command(BaseCommand):
    help = "Link customers' vehicles to the vehicle catalog."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print the report and change nothing.")

    def handle(self, *args, dry_run, **options):
        if not VehicleModel.objects.exists():
            raise CommandError("The vehicle catalog is empty: run import_vehicle_data and classify_vehicles first.")
        with transaction.atomic():
            report = link_vehicles(apply=not dry_run)
            if dry_run:
                transaction.set_rollback(True)
        self.print_report(dry_run, report)

    def print_report(self, dry_run, report):
        write = self.stdout.write
        write("DRY RUN: nothing was changed. Run again without --dry-run to apply it." if dry_run else "APPLIED: the links were saved.")

        newly = [linked for linked in report.linked if not linked.before]
        write(f"\nLinked ({len(report.linked):,} vehicles: {len(newly):,} {'to link' if dry_run else 'newly linked'}, {len(report.linked) - len(newly):,} linked before)")
        for linked in report.linked:
            line = f"  {describe(linked.vehicle)} -> {describe_model(linked.vehicle_model)}"
            if linked.dropped:
                line += f"; trim words left off: {' '.join(linked.dropped)}"
            if linked.filled:
                filled = ", ".join(
                    f"{name.replace('_', ' ')} {getattr(value, 'label', value)}" for name, value in linked.filled.items()
                )
                line += f"; {'fills' if dry_run else 'filled'} {filled}"
            if linked.before:
                line += " (linked before)"
            write(line)

        write(f"\nNot found ({len(report.not_found):,} vehicles, left unlinked)")
        for vehicle, found in report.not_found:
            write(f"  {describe(vehicle)}: {found.reason}")

        write(f"\nMore than one candidate ({len(report.several):,} vehicles, left unlinked for the owner)")
        for vehicle, found in report.several:
            write(f"  {describe(vehicle)}: " + "; ".join(describe_model(candidate) for candidate in found.candidates))

        if report.kept_link:
            write(f"\nLinked before to another model than the one that matches now ({len(report.kept_link):,} vehicles, links kept)")
            for vehicle, found in report.kept_link:
                now = describe_model(found.vehicle_model) if found.vehicle_model else found.status
                write(f"  {describe(vehicle)}: linked to {describe_model(vehicle.vehicle_model)}; matches {now}")

        write(f"\nClass or size variant differs from the catalog ({len(report.differences):,} vehicles, for the owner on the differences screen)")
        for difference in report.differences:
            write(
                f"  {describe(difference.vehicle)}: imported {difference.imported}; catalog {difference.catalog}"
                f" ({difference.stored.vehicle_model.make} {difference.stored.vehicle_model.model}, {difference.kind} differs)"
            )

        write(f"\nLinked, but the catalog has no settled class for the year ({len(report.no_class_yet):,} vehicles)")
        for vehicle, stored in report.no_class_yet:
            if stored is None:
                why = "not classified: run classify_vehicles"
            elif stored.vehicle_class_id is None:
                why = "waiting in the review queue"
            else:
                why = f"waiting in the review queue, live meanwhile as {catalog_label(stored)}"
            write(f"  {describe(vehicle)}: {why}")

        class_name, service_name, price = report.motorcycle
        write(f"\nImported motorcycle jobs ({len(report.motorcycle_jobs):,}): the {class_name} class and the {service_name} service; amounts and payments stay as imported")
        for job in report.motorcycle_jobs:
            state = "done before" if job.done else ("to give" if dry_run else "given")
            flag = "" if price is None or job.amount == price else f"  CHECK: the amount is not ${price:,.2f}, for the owner to decide"
            write(f"  {job.describe()} ({state}){flag}")
        if report.unlinked_classless:
            write(f"\nNot linked and with no vehicle class ({len(report.unlinked_classless):,} vehicles; a motorcycle here needs a spelling in data/vehicle-names.yaml)")
            for vehicle in report.unlinked_classless:
                write(f"  {describe(vehicle)}")
