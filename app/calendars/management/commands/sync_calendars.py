"""The first run and the nightly full check of the Google calendars
(decision 0098).

    python manage.py sync_calendars --dry-run   # print what it would write
    python manage.py sync_calendars             # write it, and repair the rest

Without --dry-run it pushes the queue, copies the Time Off calendar, flags
clashes, then compares every appointment and closed date from today on with
the Jobs calendar and repairs any difference. Its last line is the summary
that ops/calendar-check.sh sends to Healthchecks. It exits 1 when Google
could not be asked.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from calendars import events, google, sync


class Command(BaseCommand):
    help = "Check the Google calendars against the database and repair any difference."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print the Jobs events the database calls for, and change nothing.")

    def handle(self, *args, dry_run, **options):
        if dry_run:
            return self.dry_run()
        try:
            report = sync.full_check()
        except google.NotConnected as error:
            raise CommandError(str(error)) from error
        except google.CalendarError as error:
            self.stdout.write(f"Calendar check failed: {error}")
            raise CommandError(f"Calendar check failed: {error}") from error
        for error in report.errors:
            self.stdout.write(f"Push failed, will retry: {error}")
        self.stdout.write(f"Calendar check: {report.line()}.")

    def dry_run(self):
        wanted = events.everything(timezone.localdate())
        for event_id, (kind, link, body) in wanted.items():
            start = body["start"].get("dateTime") or body["start"]["date"]
            end = body["end"].get("dateTime") or body["end"]["date"]
            self.stdout.write(f"{start} to {end}  {body['summary']}")
            if body.get("location"):
                self.stdout.write(f"    {body['location']}")
            for line in body.get("description", "").splitlines():
                self.stdout.write(f"    {line}")
        jobs = sum(1 for kind, _, _ in wanted.values() if kind == "job")
        drives = sum(1 for kind, _, _ in wanted.values() if kind == "drive")
        closed = sum(1 for kind, _, _ in wanted.values() if kind == "closed")
        self.stdout.write(f"Dry run: {jobs} job events, {drives} Drive to job blocks and {closed} Closed days would be on the Jobs calendar. Nothing was changed.")
