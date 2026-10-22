"""What classify_vehicles loads from data/ before it classifies.

- The launch rules and model overrides in data/vehicle-classes.yaml. Each
  one created from the file remembers what it was created as, so a later
  change to the file reaches it, and a new entry is added, while the owner's
  own rules and anything the owner edited or deleted are left alone and
  listed in the report.
- The owner-approved third-row list, data/third-row-seating.yaml, on every
  run, as model-year records with source "seat_list": always is three seat
  rows, never is two, and optional is both, so the customer is asked. Its
  makes and models are matched to the catalog by the names in
  data/vehicle-names.yaml, as the import matches them. A row that matches no
  model, or none of the model's catalog years, is listed in the report
  instead of guessed.
"""

from collections import Counter
from dataclasses import dataclass, field

import yaml
from django.conf import settings
from django.utils import timezone

from vehicles.models import ClassificationRule, ModelOverride, VehicleClass, VehicleModel, VehicleModelYear
from vehicles.vehicle_data.catalog import write
from vehicles.vehicle_data.facts import Facts
from vehicles.vehicle_data.names import load_names

from .rules import condition_errors

SEAT_LIST = VehicleModelYear.Source.SEAT_LIST
VEHICLE = VehicleModel.VehicleType.VEHICLE
SEAT_ROWS = {"always": [3], "never": [2], "optional": [2, 3]}
RULE_STEP = 10
OVERRIDE_NOTE = "(launch override, data/vehicle-classes.yaml)"


class SeedError(ValueError):
    """The data files cannot be loaded as they are."""


@dataclass
class SeedReport:
    # What changed in the launch rules and overrides, one line each.
    launch_set: list = field(default_factory=list)
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


def models_named(make, model, names=None):
    """The car, truck and van models of this make and name, however the
    catalog spells them (data/vehicle-names.yaml)."""
    names = names or load_names()
    key = (names.make_key(make), names.model_key(make, model))
    return [
        vehicle_model
        for vehicle_model in VehicleModel.objects.filter(vehicle_type=VEHICLE).order_by("pk")
        if (names.make_key(vehicle_model.make), names.model_key(vehicle_model.make, vehicle_model.model)) == key
    ]


def rule_entry(entry, position):
    errors = condition_errors(entry["conditions"])
    if errors:
        raise SeedError(f"Launch rule {entry['name']!r}: {' '.join(errors)}")
    class_named(entry["class"])
    return {
        "name": entry["name"],
        "class": entry["class"],
        "conditions": entry["conditions"],
        "note": entry.get("note", ""),
        "position": position,
        "active": True,
    }


def rule_now(rule):
    return {
        "name": rule.name,
        "class": rule.vehicle_class.name,
        "conditions": rule.conditions,
        "note": rule.note,
        "position": rule.position,
        "active": rule.active,
    }


def set_rule(rule, entry):
    rule.name, rule.conditions, rule.note = entry["name"], entry["conditions"], entry["note"]
    rule.position, rule.active = entry["position"], entry["active"]
    rule.vehicle_class = class_named(entry["class"])
    rule.seeded_from = entry


def sync_rules(data, report):
    entries = {}
    for index, entry in enumerate(data["launch_rules"], start=1):
        entries[entry["name"]] = rule_entry(entry, index * RULE_STEP)
    seeded = {rule.seeded_from["name"]: rule for rule in ClassificationRule.objects.exclude(seeded_from=None).select_related("vehicle_class")}
    ever = set(
        ClassificationRule.history.exclude(seeded_from=None).values_list("seeded_from__name", flat=True)
    )
    for name, rule in seeded.items():
        entry = entries.get(name)
        if rule_now(rule) != rule.seeded_from:
            if entry != rule.seeded_from:
                report.launch_set.append(f"kept your edited rule {rule.position} ({rule.name}); the launch set has a different version")
            continue
        if entry is None:
            report.launch_set.append(f"removed launch rule {rule.position} ({rule.name}), no longer in the launch set")
            rule.delete()
        elif entry != rule.seeded_from:
            set_rule(rule, entry)
            rule.save()
            report.launch_set.append(f"updated launch rule {rule.position} ({rule.name})")
    for name, entry in entries.items():
        if name in seeded:
            continue
        if name in ever:
            report.launch_set.append(f"not added again: launch rule {name}, which you deleted")
            continue
        rule = ClassificationRule()
        set_rule(rule, entry)
        rule.save()
        report.launch_set.append(f"added launch rule {rule.position} ({rule.name})")


def override_key(entry):
    names = load_names()
    return [
        names.make_key(entry["make"]),
        names.model_key(entry["make"], entry["model"]),
        entry.get("year_from"),
        entry.get("year_to"),
    ]


def override_entry(entry):
    class_named(entry["class"])
    return {
        "key": override_key(entry),
        "make": entry["make"],
        "model": entry["model"],
        "year_from": entry.get("year_from"),
        "year_to": entry.get("year_to"),
        "class": entry["class"],
        "note": f"{entry.get('note', '')} {OVERRIDE_NOTE}".strip(),
    }


def override_now(override, entry):
    return {
        **entry,
        "year_from": override.year_from,
        "year_to": override.year_to,
        "class": override.vehicle_class.name,
        "note": override.note,
        "size": [override.size_variant_id, override.ask_size],
    }


def set_override(override, entry):
    override.year_from, override.year_to = entry["year_from"], entry["year_to"]
    override.vehicle_class = class_named(entry["class"])
    override.size_variant, override.ask_size = None, False
    override.note = entry["note"]
    override.seeded_from = entry


def describe(entry):
    years = f" {entry['year_from'] or ''}-{entry['year_to'] or ''}" if entry["year_from"] or entry["year_to"] else ""
    return f"{entry['make']} {entry['model']}{years} -> {entry['class']}"


def sync_overrides(data, report):
    entries = [override_entry(entry) for entry in data["model_overrides"]]
    by_key = {tuple(entry["key"]): entry for entry in entries}
    seeded = list(ModelOverride.objects.exclude(seeded_from=None).select_related("vehicle_class", "vehicle_model"))
    ever = {
        (model_id, tuple(seeded_from["key"]))
        for model_id, seeded_from in ModelOverride.history.exclude(seeded_from=None).values_list("vehicle_model_id", "seeded_from")
    }
    have = set()
    for override in seeded:
        key = tuple(override.seeded_from["key"])
        if (override.vehicle_model_id, key) in have:
            override.delete()  # Two models merged into one: one launch override is enough.
            continue
        have.add((override.vehicle_model_id, key))
        entry = by_key.get(key)
        before = {**override.seeded_from, "size": [None, False]}
        if override_now(override, override.seeded_from) != before:
            if entry != override.seeded_from:
                report.launch_set.append(f"kept your edited override {describe(override.seeded_from)}; the launch set has a different version")
            continue
        if entry is None:
            report.launch_set.append(f"removed launch override {describe(override.seeded_from)}, no longer in the launch set")
            override.delete()
        elif entry != override.seeded_from:
            set_override(override, entry)
            override.save()
            report.launch_set.append(f"updated launch override {describe(entry)}")
    for entry in entries:
        found = models_named(entry["make"], entry["model"])
        if not found:
            report.unmatched_overrides.append(f"{describe(entry)}: no catalog model of this name")
        for vehicle_model in found:
            key = (vehicle_model.pk, tuple(entry["key"]))
            if key in have:
                continue
            if key in ever:
                report.launch_set.append(f"not added again: launch override {describe(entry)}, which you deleted")
                continue
            override = ModelOverride(vehicle_model=vehicle_model, set_at=timezone.now())
            set_override(override, entry)
            override.save()
            have.add(key)
            report.launch_set.append(f"added launch override {describe(entry)} ({vehicle_model.year_from}-{vehicle_model.year_to})")


def sync_launch_set(report, data_dir=None):
    """Bring the launch rules and overrides in step with data/vehicle-classes.yaml."""
    data = read_data("vehicle-classes.yaml", data_dir)
    sync_rules(data, report)
    sync_overrides(data, report)


def sync_seat_list(report, data_dir=None):
    """Write the third-row list as seat_list model-year records, replacing
    the last run's."""
    entries = read_data("third-row-seating.yaml", data_dir)["models"]
    names = load_names(data_dir)

    catalog = {}
    years = {}
    for vehicle_model in VehicleModel.objects.filter(vehicle_type=VEHICLE).order_by("pk"):
        key = (names.make_key(vehicle_model.make), names.model_key(vehicle_model.make, vehicle_model.model))
        catalog.setdefault(key, []).append(vehicle_model)
    for model_id, year in (
        VehicleModelYear.objects.exclude(source=SEAT_LIST).values_list("vehicle_model_id", "year").distinct()
    ):
        years.setdefault(model_id, set()).add(year)

    by_model_year = {}
    for entry in entries:
        first, last = entry["first_year"], entry.get("last_year")
        label = f"{entry['make']} {' / '.join(entry['models'])} {first}-{last or ''}: {entry['third_row']}"
        if entry["third_row"] not in SEAT_ROWS:
            raise SeedError(f"{label}: third_row is always, never or optional.")
        found = [
            model
            for name in entry["models"]
            for model in catalog.get((names.make_key(entry["make"]), names.model_key(entry["make"], name)), [])
        ]
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
