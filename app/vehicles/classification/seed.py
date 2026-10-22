"""What classify_vehicles loads from data/ before it classifies.

- The launch rules and model overrides in data/vehicle-classes.yaml, once:
  when there are no rules yet. After that they are the owner's to edit.
- The owner-approved third-row list, data/third-row-seating.yaml, on every
  run, as model-year records with source "seat_list": always is three seat
  rows, never is two, and optional is both, so the customer is asked. Its
  makes and models are matched to the catalog on capitals and digits only,
  as the import matches names, with the import's make aliases. A row that
  matches no model, or none of the model's catalog years, is listed in the
  report instead of guessed.
"""

from collections import Counter
from dataclasses import dataclass, field

import yaml
from django.conf import settings
from django.utils import timezone

from vehicles.models import ClassificationRule, ModelOverride, VehicleClass, VehicleModel, VehicleModelYear
from vehicles.vehicle_data.catalog import name_key, write
from vehicles.vehicle_data.facts import Facts

from .rules import condition_errors

SEAT_LIST = VehicleModelYear.Source.SEAT_LIST
VEHICLE = VehicleModel.VehicleType.VEHICLE
SEAT_ROWS = {"always": [3], "never": [2], "optional": [2, 3]}
RULE_STEP = 10


class SeedError(ValueError):
    """The data files cannot be loaded as they are."""


@dataclass
class SeedReport:
    rules_seeded: int = 0
    overrides_seeded: int = 0
    unmatched_overrides: list = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    unmatched_seat_rows: list = field(default_factory=list)


def read_data(name, data_dir=None):
    return yaml.safe_load(((data_dir or settings.DATA_DIR) / name).read_text())


def class_named(name):
    try:
        return VehicleClass.objects.get(name=name)
    except VehicleClass.DoesNotExist:
        raise SeedError(f"No vehicle class {name!r}: run load_pricebook first.") from None


def models_named(make, model):
    """The car, truck and van models of this make and name, however the
    catalog spells them."""
    make_key, model_key = name_key(make), name_key(model)
    return [
        vehicle_model
        for vehicle_model in VehicleModel.objects.filter(vehicle_type=VEHICLE).order_by("pk")
        if name_key(vehicle_model.make) == make_key and name_key(vehicle_model.model) == model_key
    ]


def seed_launch_set(report, data_dir=None):
    """The launch rules and model overrides, when there are no rules yet."""
    if ClassificationRule.objects.exists():
        return
    data = read_data("vehicle-classes.yaml", data_dir)
    for index, entry in enumerate(data["launch_rules"], start=1):
        errors = condition_errors(entry["conditions"])
        if errors:
            raise SeedError(f"Launch rule {entry['name']!r}: {' '.join(errors)}")
        ClassificationRule.objects.create(
            position=index * RULE_STEP,
            name=entry["name"],
            conditions=entry["conditions"],
            vehicle_class=class_named(entry["class"]),
            note=entry.get("note", ""),
        )
        report.rules_seeded += 1
    for entry in data["model_overrides"]:
        vehicle_class = class_named(entry["class"])
        found = models_named(entry["make"], entry["model"])
        if not found:
            report.unmatched_overrides.append(f"{entry['make']} {entry['model']}: no catalog model of this name")
        for vehicle_model in found:
            ModelOverride.objects.create(
                vehicle_model=vehicle_model,
                vehicle_class=vehicle_class,
                set_at=timezone.now(),
                note=f"{entry.get('note', '')} (launch override, data/vehicle-classes.yaml)".strip(),
            )
            report.overrides_seeded += 1


def sync_seat_list(report, data_dir=None):
    """Write the third-row list as seat_list model-year records, replacing
    the last run's."""
    entries = read_data("third-row-seating.yaml", data_dir)["models"]
    aliases = read_data("vehicle-data-import.yaml", data_dir).get("canada", {}).get("make_names") or {}
    aliases = {name_key(other): name_key(make) for other, make in aliases.items()}

    catalog = {}
    years = {}
    for vehicle_model in VehicleModel.objects.filter(vehicle_type=VEHICLE).order_by("pk"):
        catalog.setdefault((name_key(vehicle_model.make), name_key(vehicle_model.model)), []).append(vehicle_model)
    for model_id, year in (
        VehicleModelYear.objects.exclude(source=SEAT_LIST).values_list("vehicle_model_id", "year").distinct()
    ):
        years.setdefault(model_id, set()).add(year)

    by_model_year = {}
    for entry in entries:
        make_key = name_key(entry["make"])
        make_key = aliases.get(make_key, make_key)
        first, last = entry["first_year"], entry.get("last_year")
        label = f"{entry['make']} {' / '.join(entry['models'])} {first}-{last or ''}: {entry['third_row']}"
        if entry["third_row"] not in SEAT_ROWS:
            raise SeedError(f"{label}: third_row is always, never or optional.")
        found = [model for name in entry["models"] for model in catalog.get((make_key, name_key(name)), [])]
        if not found:
            report.unmatched_seat_rows.append(f"{label}: no catalog model of this make and name")
            continue
        placed = False
        for vehicle_model in found:
            for year in sorted(years.get(vehicle_model.pk, ())):
                if year >= first and (last is None or year <= last):
                    facts = by_model_year.setdefault((vehicle_model.pk, year), Facts())
                    for rows in SEAT_ROWS[entry["third_row"]]:
                        facts.add("seat_rows", rows)
                    facts.ids.add(label)
                    placed = True
        if not placed:
            report.unmatched_seat_rows.append(f"{label}: the catalog has the model, but not in these years")

    write(SEAT_LIST, by_model_year, report, reason="Third-row seating list")
    # The list is the whole truth for its rows: a year it no longer covers loses its row.
    stale = [
        row.pk
        for row in VehicleModelYear.objects.filter(source=SEAT_LIST).only("pk", "vehicle_model_id", "year")
        if (row.vehicle_model_id, row.year) not in by_model_year
    ]
    VehicleModelYear.objects.filter(pk__in=stale).delete()
    report.counts["model years removed"] += len(stale)
