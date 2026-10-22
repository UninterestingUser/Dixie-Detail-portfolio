"""Load the vehicle catalog from the EPA, NHTSA vPIC and vPIC's Canadian
specifications (docs/operations/importing-vehicle-data.md).

  python manage.py import_vehicle_data [--source epa|vpic|canada|all] [--dry-run] [--refresh]

Downloads are cached in the folder named by the setting
VEHICLE_DATA_CACHE_DIR, so a rerun does not fetch again; --refresh fetches
every file again. With --dry-run everything is imported inside a transaction
that is then rolled back, so the report shows what a real run would write.
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from vehicles.models import VehicleDataImportRun
from vehicles.vehicle_data.config import load_config
from vehicles.vehicle_data.fetch import Fetcher
from vehicles.vehicle_data.run import SOURCES, run

COUNTS = (
    "models added", "models changed", "models unchanged",
    "model years added", "model years changed", "model years unchanged",
    "owner's models: facts recorded, model left alone",
    "files downloaded", "files from the cache",
)


class Command(BaseCommand):
    help = "Load the vehicle catalog from the EPA, NHTSA vPIC and the Canadian specifications."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=[*SOURCES, "all"], default="all", help="Which source to load (default all).")
        parser.add_argument("--dry-run", action="store_true", help="Show what would change, and change nothing.")
        parser.add_argument("--refresh", action="store_true", help="Download every file again instead of using the cache.")

    def handle(self, *args, source, dry_run, refresh, **options):
        cache_dir = settings.VEHICLE_DATA_CACHE_DIR
        if not cache_dir.is_dir() or not os.access(cache_dir, os.W_OK):
            raise CommandError(
                f"The download cache {cache_dir} (setting VEHICLE_DATA_CACHE_DIR) is missing or cannot be"
                " written. Mount it as docs/operations/importing-vehicle-data.md shows."
            )
        config = load_config()
        fetcher = Fetcher(
            cache_dir,
            pause_seconds=config.pause_seconds,
            retries=config.retries,
            backoff_seconds=config.backoff_seconds,
            refresh=refresh,
            log=self.stderr.write,
        )
        reports = run(SOURCES if source == "all" else (source,), dry_run=dry_run, fetcher=fetcher, config=config, log=self.stderr.write)
        self.print_report(reports, dry_run)
        failed = [report for report in reports if report.result == VehicleDataImportRun.Result.FAILED]
        if failed:
            raise CommandError(f"{failed[0].label} failed: {failed[0].message}")

    def print_report(self, reports, dry_run):
        write = self.stdout.write
        write("DRY RUN: nothing was changed. Run again without --dry-run to write it." if dry_run else "APPLIED: the import was written.")
        for report in reports:
            seconds = (report.finished_at - report.started_at).total_seconds()
            write(f"\n{report.label}: {report.result} in {seconds:,.0f} seconds")
            for name in COUNTS:
                write(f"  {name}: {report.counts.get(name, 0):,}")
            for name, count in sorted(report.counts.items()):
                if name not in COUNTS:
                    write(f"  {name}: {count:,}")
            if report.message:
                write(f"  Stopped: {report.message}")
            sections = (
                ("Models added", report.added_models),
                ("Canadian rows not matched to a model, left for the owner", report.unmatched),
                ("Rejected", report.rejected),
            )
            for title, lines in sections:
                if lines or title == "Rejected":
                    write(f"\n  {title} ({len(lines):,})")
                    for line in lines:
                        write(f"    {line}")
