"""Import customers, vehicles, appointments and payments from the Baserow and
Setmore exports (docs/operations/importing-baserow.md).

  python manage.py import_baserow [FOLDER] [--owner NAME] [--apply]

FOLDER is the folder of export files, /srv/import by default, where the
one-off container mounts it read-only. Without --apply this is a dry run:
everything is imported inside a transaction that is then rolled back, so the
report shows exactly what --apply would do and nothing changes.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from importer.run import ImportRefused, run
from importer.sources import SourceError, load

DEFAULT_FOLDER = "/srv/import"


class Command(BaseCommand):
    help = "Import the Baserow and Setmore exports. A dry run unless --apply is given."

    def add_arguments(self, parser):
        parser.add_argument("folder", nargs="?", default=DEFAULT_FOLDER, help=f"The export folder (default {DEFAULT_FOLDER}).")
        parser.add_argument("--apply", action="store_true", help="Write the import. Without it nothing changes.")
        parser.add_argument(
            "--owner",
            help="The owner's name as written in Baserow's Staff column, needed the first time staff are created.",
        )

    def handle(self, *args, folder, apply, owner, **options):
        try:
            tables, corrections, files = load(Path(folder))
        except SourceError as error:
            raise CommandError(str(error)) from error
        try:
            report = run(tables, corrections, apply=apply, owner_name=owner)
        except ImportRefused as error:
            raise CommandError(str(error)) from error
        report.files = files
        self.print_report(report, apply)

    def print_report(self, report, apply):
        write = self.stdout.write
        write("APPLIED: the import was written." if apply else "DRY RUN: nothing was changed. Run again with --apply to write it.")
        write("\nFiles")
        for table, name in report.files.items():
            write(f"  {table}: {name}")
        write("\nCounts")
        for kind, count in sorted(report.counts.items()):
            write(f"  {kind}: {count}")
        sections = (
            ("Corrections applied", report.corrections),
            ("Warnings", report.warnings),
            ("Could not place", report.unplaced),
            ("Questions in the corrections file, left alone", report.questions),
            ("Expected results from the corrections file: compare with the counts above", report.checks),
        )
        for title, lines in sections:
            write(f"\n{title} ({len(lines)})")
            for line in lines:
                write(f"  {line}")
