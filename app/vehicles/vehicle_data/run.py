"""Runs the import for each source asked for, in order, and records each run.

A real run commits each source on its own, so a failed vPIC run keeps the
EPA's work. A dry run does everything inside one transaction that is rolled
back at the end, so the Canadian specifications are matched against the
models the same dry run would add, and the report shows what a real run
would write. Either way every source attempted gets a VehicleDataImportRun.
"""

import contextlib
from collections import Counter
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from vehicles.models import VehicleDataImportRun, VehicleModel, VehicleModelYear

from . import canada, epa, vpic
from .catalog import Catalog, group_by_model_year, merge_duplicates, place, write

SOURCES = ("epa", "vpic", "canada")
Source = VehicleModelYear.Source
Result = VehicleDataImportRun.Result


@dataclass
class SourceReport:
    source: str
    started_at: object = None
    finished_at: object = None
    result: str = ""
    message: str = ""
    counts: Counter = field(default_factory=Counter)
    added_models: list = field(default_factory=list)
    # Base models split into nameplates, and models merged or renamed, by data/vehicle-names.yaml.
    split: list = field(default_factory=list)
    merged: list = field(default_factory=list)
    unmatched: list = field(default_factory=list)
    rejected: list = field(default_factory=list)
    # The ids behind "models added" and "models changed", so the monthly
    # refresh counts a model once however many sources changed it.
    added_model_ids: set = field(default_factory=set)
    changed_model_ids: set = field(default_factory=set)

    @property
    def label(self):
        return Source(self.source).label

    def reject(self, text):
        self.rejected.append(text)


def store(keyed_facts, source, model_source, report, config):
    """Write facts keyed by (vehicle type, make, model, year), adding the
    models the catalog does not have, after merging the models that are one
    vehicle."""
    reason = f"{Source(source).label} import"
    report.merged.extend(merge_duplicates(config.names, reason))
    catalog = Catalog(config.names)
    placed = place(catalog, keyed_facts, model_source)
    catalog.save_new(reason)
    report.changed_model_ids |= write(source, group_by_model_year(placed), report, catalog.new, reason)
    report.added_model_ids |= {vehicle_model.pk for vehicle_model in catalog.new}
    return catalog.new


def write_epa(collected, report, config):
    store(collected, Source.EPA, VehicleModel.Source.EPA, report, config)


def write_vpic(collected, report, config):
    for vehicle_model in store(collected, Source.VPIC, VehicleModel.Source.NHTSA, report, config):
        kind = ", motorcycle" if vehicle_model.vehicle_type == VehicleModel.VehicleType.MOTORCYCLE else ""
        report.added_models.append(
            f"{vehicle_model.make} {vehicle_model.model} ({vehicle_model.year_from}-{vehicle_model.year_to}{kind})"
        )


def write_canada(collected, report, config):
    report.merged.extend(merge_duplicates(config.names, "Canadian specifications import"))
    grouped = canada.facts_by_model_year(collected, report, config.names)
    report.changed_model_ids |= write(Source.CANADA, grouped, report, reason="Canadian specifications import")


COLLECT = {"epa": epa.collect, "vpic": vpic.collect, "canada": canada.collect}
WRITE = {"epa": write_epa, "vpic": write_vpic, "canada": write_canada}


def run(sources, *, dry_run, fetcher, config, log=None):
    """A SourceReport for each source attempted. Stops at the first source
    that fails; its report says why."""
    log = log or (lambda text: None)
    reports = []
    try:
        with transaction.atomic() if dry_run else contextlib.nullcontext():
            for source in sources:
                report = SourceReport(source, started_at=timezone.now())
                reports.append(report)
                downloaded, from_cache = fetcher.downloaded, fetcher.from_cache
                try:
                    log(f"{report.label}: fetching")
                    collected = COLLECT[source](fetcher, config, report, log)
                    log(f"{report.label}: writing")
                    with transaction.atomic():
                        WRITE[source](collected, report, config)
                    report.result = Result.SUCCEEDED
                except Exception as error:  # noqa: BLE001 - recorded, and the command fails
                    report.result = Result.FAILED
                    report.message = f"{type(error).__name__}: {error}"
                finally:
                    report.finished_at = timezone.now()
                    report.counts["files downloaded"] += fetcher.downloaded - downloaded
                    report.counts["files from the cache"] += fetcher.from_cache - from_cache
                if report.result == Result.FAILED:
                    break
            if dry_run:
                transaction.set_rollback(True)
    finally:
        for report in reports:
            VehicleDataImportRun.objects.create(
                source=report.source,
                dry_run=dry_run,
                started_at=report.started_at,
                finished_at=report.finished_at or timezone.now(),
                result=report.result or Result.FAILED,
                counts={**report.counts, "unmatched": len(report.unmatched), "rejected": len(report.rejected)},
                message=report.message,
            )
    return reports
