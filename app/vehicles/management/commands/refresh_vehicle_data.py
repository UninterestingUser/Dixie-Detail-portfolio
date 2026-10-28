"""The monthly vehicle data refresh (docs/operations/monitoring.md), run by
ops/vehicle-refresh.sh in a one-off app container with the download cache
attached:

  python manage.py refresh_vehicle_data

It runs import_vehicle_data --source all --refresh, then, if that
succeeded, classify_vehicles --refresh, which classifies new model years
with the size-based rules once apply_size_classes has switched to them
(decision 0083). A refresh adds new models and model years and updates
facts; a class or size change to a model with an override, an approval or
customers' jobs is held in the review queue (decision 0081). The refresh is
recorded as a VehicleDataRefresh, which the control app's home screen shows.

Its log holds only the model years newly sent to the review queue and, as
its last line, the one-line summary the Healthchecks ping carries. The two
commands' full reports are printed only when the refresh fails, before the
summary, so the failure ping's log tail shows what went wrong.
"""

import io


from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from vehicles.models import VehicleDataRefresh

from .classify_vehicles import Command as ClassifyCommand
from .classify_vehicles import spans
from .import_vehicle_data import Command as ImportCommand

Result = VehicleDataRefresh.Result


class Command(BaseCommand):
    help = "The monthly vehicle data refresh: import every source with fresh downloads, then classify."

    def handle(self, *args, **options):
        refresh = VehicleDataRefresh(started_at=timezone.now(), result=Result.FAILED)
        importer, classifier = ImportCommand(), ClassifyCommand()
        report = io.StringIO()
        streams = {"stdout": report, "stderr": report}
        try:
            call_command(importer, source="all", refresh=True, **streams)
            call_command(classifier, refresh=True, **streams)
            refresh.result = Result.SUCCEEDED
        except Exception as error:
            refresh.message = str(error) or type(error).__name__
            self.stdout.write(report.getvalue())
            raise CommandError(refresh.message) from error
        finally:
            queued = [(change.vehicle_model, change.year, change.because) for change in getattr(classifier, "found", []) if change.entering_review]
            if queued:
                self.stdout.write(f"Newly in the review queue ({len(queued):,} model years):")
                for line in spans(queued):
                    self.stdout.write(f"  {line}")
            reports = getattr(importer, "reports", [])
            added = set().union(*(report.added_model_ids for report in reports))
            refresh.models_added = len(added)
            refresh.models_changed = len(set().union(*(report.changed_model_ids for report in reports)) - added)
            refresh.sent_to_queue = sum(1 for change in getattr(classifier, "found", []) if change.entering_review)
            refresh.held = len(getattr(classifier, "held", []))
            refresh.finished_at = timezone.now()
            refresh.save()
            self.stdout.write(f"\n{refresh.summary}")
