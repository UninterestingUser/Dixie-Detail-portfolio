"""Switch to the size-based vehicle classes and publish the new price book in
one step (decision 0083, docs/operations/classifying-vehicles.md):

  python manage.py apply_size_classes --effective YYYY-MM-DD --dry-run
  python manage.py apply_size_classes --effective YYYY-MM-DD

load_pricebook must first load data/price-matrix.csv as a draft. In one
transaction it publishes the draft with the effective date, switches every
model year to the size-based classes, retires the body-type classes, archives
the old rules, overrides, review queue decisions and approvals, and sets each
customer's vehicle's class (vehicles.classification.switch). A draft that
fails the price book check changes nothing. --dry-run does all of it, prints
the same report and rolls back; without it, the effective date must be today.
"""

import datetime

from django.core.management.base import BaseCommand, CommandError

from vehicles.classification.seed import SeedError
from vehicles.classification.switch import SwitchError, run
from vehicles.models import VehicleModel


def day(text):
    try:
        return datetime.date.fromisoformat(text)
    except ValueError:
        raise CommandError(f"{text!r} is not a date: give it as YYYY-MM-DD.") from None


class Command(BaseCommand):
    help = "Switch to the size-based vehicle classes and publish the new price book, in one step."

    def add_arguments(self, parser):
        parser.add_argument("--effective", required=True, type=day, help="The date the new price book takes effect, YYYY-MM-DD.")
        parser.add_argument("--dry-run", action="store_true", help="Print the report and change nothing.")

    def handle(self, *args, effective, dry_run, **options):
        if not VehicleModel.objects.exists():
            raise CommandError("The vehicle catalog is empty: run import_vehicle_data first.")
        try:
            self.outcome = run(effective, dry_run, self.stdout)
        except (SwitchError, SeedError) as error:
            raise CommandError(str(error)) from error
