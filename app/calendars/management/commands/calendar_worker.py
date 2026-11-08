"""The calendar worker (decision 0098): runs for as long as the stack does,
in its own container.

Every few seconds it pushes the queued Jobs calendar changes. Every Time Off
check (5 minutes at launch) it copies the Time Off calendar, flags clashes
and checks the Jobs calendar for edits made in Google. The queue is in
PostgreSQL, so a restart loses nothing: a task a stopped worker held is
taken again once its claim runs out.
"""

import logging
import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from calendars import google, sync
from calendars.models import SyncState
from scheduling.models import SchedulingSettings

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Push Jobs calendar changes and copy the Time Off calendar, until stopped."

    def add_arguments(self, parser):
        parser.add_argument("--every", type=float, default=5, help="Seconds between looks at the queue.")
        parser.add_argument("--once", action="store_true", help="Do one pass and stop (for tests).")

    def handle(self, *args, every, once, **options):
        self.stopping = False
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        last_round = None
        self.stdout.write("Calendar worker started" + ("" if google.connected() else "; the calendars are not connected, so it waits"))
        while not self.stopping:
            now = timezone.now()
            try:
                SyncState.objects.filter(pk=SyncState.get().pk).update(worker_seen_at=now)
                if google.connected():
                    with sync.calendar_lock():
                        report = sync.process_queue(now)
                    for error in report.errors:
                        self.stderr.write(f"Push failed, will retry: {error}")
                    minutes = SchedulingSettings.get().time_off_check_minutes
                    if last_round is None or (now - last_round).total_seconds() >= minutes * 60:
                        last_round = now
                        report = sync.check_round(now)
                        self.stdout.write(f"Calendar round: {report.line()}" + (f"; errors: {'; '.join(report.errors)}" if report.errors else ""))
            except Exception:  # noqa: BLE001 - keep running; the next pass tries again
                log.exception("Calendar worker pass failed")
            if once:
                break
            self.sleep(every)
            # A connection the database dropped while it slept is opened again.
            close_old_connections()

    def stop(self, *args):
        self.stopping = True

    def sleep(self, seconds):
        end = time.monotonic() + seconds
        while not self.stopping and time.monotonic() < end:
            time.sleep(min(0.5, end - time.monotonic()))
