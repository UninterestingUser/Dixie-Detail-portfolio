"""Load Tennessee's sales tax rates and rate boundaries, or check the rates.

    python manage.py import_tax_rates --dry-run   # show what would change
    python manage.py import_tax_rates             # load (see billing/tax_rates.py)
    python manage.py import_tax_rates --check     # the morning check: flag rate changes only

The last line is the summary. With --check, the exit status is 2 when any
rate change is waiting for the owner's approval, or the state lists an area
the import has not loaded yet, so the check's Healthchecks
ping reports it (ops/tax-rate-check.sh).
"""

from django.core.management.base import BaseCommand, CommandError

from billing import tax_rates


class Command(BaseCommand):
    help = "Load Tennessee's sales tax rates and boundaries, or check the rates for changes."

    def add_arguments(self, parser):
        modes = parser.add_mutually_exclusive_group()
        modes.add_argument("--dry-run", action="store_true", help="Show what would change and change nothing.")
        modes.add_argument("--check", action="store_true", help="Compare the rates only, and store changes for approval.")

    def handle(self, *args, dry_run=False, check=False, **options):
        mode = "dry_run" if dry_run else "check" if check else "import"
        try:
            rows = tax_rates.fetch_rows(geometry=mode != "check")
        except tax_rates.TaxDataError as error:
            raise CommandError(str(error)) from error
        report = tax_rates.apply(rows, mode=mode)
        for line in report.lines:
            self.stdout.write(line)
        prefix = {"dry_run": "Tax rate import (dry run, nothing changed)", "check": "Tax rate check", "import": "Tax rate import"}[mode]
        self.stdout.write(
            f"{prefix}: {len(rows)} areas from the state, {report.unchanged} unchanged, "
            f"{report.rate_changes} rate change(s) found, {report.new_jurisdictions} new, "
            f"{report.boundaries_changed} boundary change(s); {report.waiting} waiting for approval in the control app"
        )
        if check and (report.waiting or report.new_jurisdictions):
            raise SystemExit(2)
