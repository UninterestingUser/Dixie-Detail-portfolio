"""The monthly vehicle data refresh (docs/operations/monitoring.md), run by
ops/vehicle-refresh.sh in a one-off app container with the download cache
attached:

  python manage.py refresh_vehicle_data

It runs import_vehicle_data --source all --refresh, then, if that
succeeded, classify_vehicles --refresh, each printing its usual report. A
refresh adds new models and model years and updates facts; a class or size
change to a model with an override, an approval or customers' jobs is held
in the review queue (decision 0081). The refresh is recorded as a
VehicleDataRefresh, which the control app's home screen shows, and its last
line of output is the one-line summary the Healthchecks ping carries.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from vehicles.models import VehicleDataRefresh

from .classify_vehicles import Command as ClassifyCommand
from .import_vehicle_data import Command as ImportCommand

Result = VehicleDataRefresh.Result


class Command(BaseCommand):
    help = "The monthly vehicle data refresh: import every source with fresh downloads, then classify."

    def handle(self, *args, **options):
        refresh = VehicleDataRefresh(started_at=timezone.now(), result=Result.FAILED)
        importer, classifier = ImportCommand(), ClassifyCommand()
        streams = {"stdout": self.stdout._out, "stderr": self.stderr._out}
        try:
            call_command(importer, source="all", refresh=True, **streams)
            call_command(classifier, refresh=True, **streams)
            refresh.result = Result.SUCCEEDED
        except Exception as error:
            refresh.message = str(error) or type(error).__name__
            raise CommandError(refresh.message) from error
        finally:
            reports = getattr(importer, "reports", [])
            added = set().union(*(report.added_model_ids for report in reports))
            refresh.models_added = len(added)
            refresh.models_changed = len(set().union(*(report.changed_model_ids for report in reports)) - added)
            refresh.sent_to_queue = sum(1 for change in getattr(classifier, "found", []) if change.entering_review)
            refresh.held = len(getattr(classifier, "held", []))
            refresh.finished_at = timezone.now()
            refresh.save()
            self.stdout.write(f"\n{refresh.summary}")
