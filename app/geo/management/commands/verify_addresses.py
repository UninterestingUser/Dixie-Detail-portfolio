"""Verify every existing customer address with the Census geocoder.

    python manage.py verify_addresses --dry-run   # report only
    python manage.py verify_addresses             # store coordinates, county and tax jurisdiction
    python manage.py verify_addresses --all       # also re-check addresses already verified

Reports each address as matched or unmatched by customer and address ID,
never by name or street. Addresses verified from a Google place or by hand
are left alone unless --all is given.
"""

import time

from django.core.management.base import BaseCommand
from django.db import transaction

from customers.models import Address
from geo import http, service_area
from geo.verification import verify_with_census


class Command(BaseCommand):
    help = "Verify customer addresses with the Census geocoder and set their tax jurisdictions."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report only; change nothing.")
        parser.add_argument("--all", action="store_true", help="Re-check addresses that are already verified.")
        parser.add_argument("--pause", type=float, default=0.2, help="Seconds between geocoder calls (default 0.2).")

    def handle(self, *args, dry_run=False, all=False, pause=0.2, **options):
        addresses = Address.objects.select_related("customer").order_by("customer_id", "pk")
        if not all:
            addresses = addresses.filter(verification="")
        counts = {"matched": 0, "unmatched": 0, "not checked": 0, "outside the area": 0, "tax needs a check": 0}
        for number, address in enumerate(addresses):
            if number and pause:
                time.sleep(pause)
            where = f"customer {address.customer_id} address {address.pk}"
            try:
                matched = verify_with_census(address)
            except http.FetchError as error:
                counts["not checked"] += 1
                self.stdout.write(f"{where}: not checked, the geocoder could not be reached ({error})")
                continue
            if not matched:
                counts["unmatched"] += 1
                self.stdout.write(f"{where}: unmatched")
                continue
            counts["matched"] += 1
            area = service_area.check(address)
            notes = [f"{address.county} County" if address.county else "no county"]
            if address.tax_jurisdiction:
                notes.append(f"tax: {address.tax_jurisdiction.name}")
            if address.tax_needs_check:
                counts["tax needs a check"] += 1
                notes.append(f"tax needs a check: {address.tax_note}")
            if not area.in_area:
                counts["outside the area"] += 1
                notes.append(area.reason)
            self.stdout.write(f"{where}: matched ({'; '.join(notes)})")
            if not dry_run:
                with transaction.atomic():
                    address._change_reason = "Verified with the Census geocoder (verify_addresses)"
                    address.save()
        summary = ", ".join(f"{count} {name}" for name, count in counts.items())
        prefix = "verify_addresses (dry run, nothing changed)" if dry_run else "verify_addresses"
        self.stdout.write(f"{prefix}: {summary}")
