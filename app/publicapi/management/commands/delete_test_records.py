from django.core.management.base import BaseCommand

from publicapi import test_records


class Command(BaseCommand):
    help = "Delete every test customer (made by api_smoke_test or from a test number) and everything of theirs."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Count what would be deleted and change nothing.")

    def handle(self, *args, **options):
        found = test_records.delete(dry_run=options["dry_run"])
        prefix = "Would delete: " if options["dry_run"] else ""
        self.stdout.write(prefix + str(found))
