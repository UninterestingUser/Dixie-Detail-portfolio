"""Ask Cloudflare Pages to rebuild the website (pricebook.site_rebuild).

    python manage.py rebuild_website            ask now
    python manage.py rebuild_website --if-due   only when a version published
                                                earlier takes effect today

ops/api-cleanup.sh runs it with --if-due every night, so prices on the site
change on a version's effective date as well as when it is published.
"""

from django.core.management.base import BaseCommand, CommandError

from pricebook.site_rebuild import due_today, request_rebuild


class Command(BaseCommand):
    help = "Ask Cloudflare Pages to rebuild the website, so it shows the pricebook in effect."

    def add_arguments(self, parser):
        parser.add_argument("--if-due", action="store_true", help="Only when a version published earlier takes effect today.")

    def handle(self, *args, if_due=False, **options):
        if if_due:
            version = due_today()
            if version is None:
                self.stdout.write("No pricebook version takes effect today; no rebuild needed.")
                return
            reason = f"pricebook version {version.number} takes effect today"
        else:
            reason = "asked for by hand"
        if not request_rebuild(reason):
            raise CommandError("The website rebuild was not asked for: no deploy hook is set, or Cloudflare refused it. See the log.")
        self.stdout.write(self.style.SUCCESS(f"Website rebuild asked for: {reason}."))
