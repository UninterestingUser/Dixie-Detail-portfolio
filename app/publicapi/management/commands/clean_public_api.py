"""Run nightly by ops/api-cleanup.sh (dixie-api-cleanup.timer)."""

from django.core.management.base import BaseCommand

from publicapi import cleanup


class Command(BaseCommand):
    help = "Delete unattached and expired quote request photos, stray files, unused places and old rate counts."

    def handle(self, *args, **options):
        self.stdout.write(str(cleanup.run()))
