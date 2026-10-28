"""Print the vehicle size report (vehicles.size_report): the measured size
of every model in the body-type car, crossover and SUV classes, gathered
for the owner's decision on how to split them (decision 0082). Those
classes are retired once apply_size_classes has run (decision 0083).

  python manage.py vehicle_size_report [--format csv|summary]

It reads only facts already in the database, makes no network calls and
changes nothing: it runs in a read-only transaction that is rolled back.
--format csv prints every size range for a spreadsheet; --format summary
(the default) prints the readable report. Customers appear only as counts.
"""

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from vehicles.size_report import build, summary, write_csv


class Command(BaseCommand):
    help = "Print the read-only vehicle size report for the car, crossover and SUV classes."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=("csv", "summary"), default="summary", help="csv or summary (default).")

    def handle(self, *args, **options):
        with transaction.atomic():
            with connection.cursor() as cursor:
                # PostgreSQL refuses any write from here on.
                cursor.execute("SET TRANSACTION READ ONLY")
            ranges = build()
            if options["format"] == "csv":
                write_csv(ranges, self.stdout)
            else:
                summary(ranges, self.stdout)
            # Rolled back, so even the read-only setting ends with the report.
            transaction.set_rollback(True)
