"""Verify every existing customer address: the Census geocoder, then Google.

    python manage.py verify_addresses --dry-run   # report only
    python manage.py verify_addresses             # store coordinates, county and tax jurisdiction
    python manage.py verify_addresses --all       # also re-check addresses already verified
    python manage.py verify_addresses --no-google # the Census geocoder only

Each address the Census geocoder cannot find is searched with Google, and
Google's match is used only if its house number, street and ZIP code agree
with the stored address. Google is asked in a dry run too: its calls count
against the daily caps. Once Google cannot be asked (no key, a cap reached),
the rest of the run uses the Census geocoder only.

Reports how each address was matched (by Census, by Google or set by hand)
or why it was not, by customer and address ID, never by name or street. A
location set by hand is reported and kept, even with --all; the owner
changes it in the control app. An address marked by hand with no location,
such as one carried over from the old "verified" flag, is checked like an
unverified one.
"""

import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from customers.models import Address
from geo import http, service_area
from geo.verification import verify_typed

HOW = {
    Address.Verification.CENSUS: "by Census",
    Address.Verification.GOOGLE_SEARCH: "by Google",
    Address.Verification.BY_HAND: "set by hand",
}
REASONS = {
    Address.Verification.CENSUS: "Verified with the Census geocoder (verify_addresses)",
    Address.Verification.GOOGLE_SEARCH: "Verified with a Google address search (verify_addresses)",
}


class Command(BaseCommand):
    help = "Verify customer addresses with the Census geocoder, then Google, and set their tax jurisdictions."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report only; change nothing.")
        parser.add_argument("--all", action="store_true", help="Re-check addresses that are already verified.")
        parser.add_argument("--no-google", action="store_true", help="Use the Census geocoder only.")
        parser.add_argument("--pause", type=float, default=0.2, help="Seconds between geocoder calls (default 0.2).")

    def notes(self, address, counts):
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
        return "; ".join(notes)

    def handle(self, *args, dry_run=False, all=False, no_google=False, pause=0.2, **options):
        addresses = Address.objects.select_related("customer", "tax_jurisdiction").order_by("customer_id", "pk")
        if not all:
            addresses = addresses.filter(Q(verification="") | Q(verification=Address.Verification.BY_HAND))
        counts = {
            "by Census": 0, "by Google": 0, "set by hand": 0, "unmatched": 0, "not checked": 0,
            "outside the area": 0, "tax needs a check": 0,
        }
        ask_google = not no_google
        checked = 0
        for address in addresses:
            where = f"customer {address.customer_id} address {address.pk}"
            if address.verification == Address.Verification.BY_HAND and address.point:
                counts["set by hand"] += 1
                self.stdout.write(f"{where}: set by hand, kept ({self.notes(address, counts)})")
                continue
            if checked and pause:
                time.sleep(pause)
            checked += 1
            try:
                outcome = verify_typed(address, ask_google=ask_google)
            except http.FetchError as error:
                counts["not checked"] += 1
                self.stdout.write(f"{where}: not checked, the Census geocoder could not be reached ({error})")
                continue
            if outcome.google_off:
                ask_google = False
                self.stdout.write(f"{outcome.reason}; the rest of this run uses the Census geocoder only")
            if not outcome.matched:
                counts["unmatched"] += 1
                self.stdout.write(f"{where}: unmatched ({outcome.reason})")
                continue
            how = HOW[outcome.method]
            counts[how] += 1
            self.stdout.write(f"{where}: matched {how} ({self.notes(address, counts)})")
            if not dry_run:
                with transaction.atomic():
                    address._change_reason = REASONS[outcome.method]
                    address.save()
        summary = ", ".join(f"{count} {name}" for name, count in counts.items())
        prefix = "verify_addresses (dry run, nothing changed)" if dry_run else "verify_addresses"
        self.stdout.write(f"{prefix}: {summary}")
