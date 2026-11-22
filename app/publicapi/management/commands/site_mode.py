"""The requests-only switch (decision 0128). Run by ops/site-mode.sh:

    python manage.py site_mode              # prints the mode
    python manage.py site_mode requests     # booking paused; requests only
    python manage.py site_mode normal
"""

import logging

from django.core.management.base import BaseCommand
from django.utils import timezone

from publicapi.models import SiteMode

log = logging.getLogger("publicapi")


class Command(BaseCommand):
    help = "Show or set the website's mode: normal, or requests (booking paused; the request form only)."

    def add_arguments(self, parser):
        parser.add_argument("mode", nargs="?", choices=[SiteMode.NORMAL, SiteMode.REQUESTS])
        parser.add_argument("--reason", default="", help="A few words saying why, kept with the switch.")

    def handle(self, *args, mode=None, reason="", **options):
        if mode:
            SiteMode.objects.update_or_create(pk=1, defaults={"mode": mode, "changed_at": timezone.now(), "reason": reason[:200]})
            log.warning("Site mode set to %s%s", mode, f" ({reason})" if reason else "")
        row = SiteMode.objects.filter(pk=1).first()
        current = row.mode if row else SiteMode.NORMAL
        since = f" since {timezone.localtime(row.changed_at):%Y-%m-%d %H:%M %Z}" if row else ""
        self.stdout.write(f"site mode: {current}{since}{f' ({row.reason})' if row and row.reason else ''}")
