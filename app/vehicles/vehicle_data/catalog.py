"""Finding vehicle models by name the way every source writes them, and
writing one source's model-year facts.

Nothing here changes a vehicle model whose source is "owner", and an import
writes only rows of its own source, so the owner's own model-year rows are
never touched either.
"""

from collections import defaultdict

from django.db.models import Max, Min
from django.utils import timezone
from simple_history.utils import bulk_create_with_history, bulk_update_with_history

from vehicles.models import (
    ModelOverride,
    ModelYearClassification,
    Vehicle,
    VehicleModel,
    VehicleModelYear,
)

from .facts import FACT_FIELDS, merge_rows
from .names import Names, name_key

OWNER = VehicleModel.Source.OWNER
BATCH = 2000
__all__ = ["name_key", "Catalog", "merge_duplicates", "place", "group_by_model_year", "write"]


def distance(vehicle_model, year):
    """How many years the model's range is from the year: 0 inside it."""
    low, high = vehicle_model.year_from or year, vehicle_model.year_to or year
    return max(low - year, 0, year - high)


class Catalog:
    """Every vehicle model, by vehicle type, make and the name customers
    know (data/vehicle-names.yaml), so an owner's model spelled "GLE-Class"
    is found for the GLE."""

    def __init__(self, names=None):
        self.names = names or Names()
        self.models = defaultdict(list)
        self.makes = {}
        self.new = []
        for vehicle_model in VehicleModel.objects.order_by("pk"):
            self._index(vehicle_model)

    def key(self, vehicle_type, make, model):
        return (vehicle_type, self.names.make_key(make), self.names.model_key(make, model))

    def _index(self, vehicle_model):
        self.models[self.key(vehicle_model.vehicle_type, vehicle_model.make, vehicle_model.model)].append(vehicle_model)
        self.makes.setdefault(self.names.make_key(vehicle_model.make), vehicle_model.make)

    def find(self, vehicle_type, make, model, year):
        """The model of that name whose year range holds the year, or the
        nearest one when the owner has split a model by years."""
        found = self.models.get(self.key(vehicle_type, make, model))
        if not found:
            return None
        return min(found, key=lambda vehicle_model: distance(vehicle_model, year))

    def find_or_add(self, vehicle_type, make, model, year, source):
        """The model of that name, or a new one (saved by save_new) spelled
        as the catalog already spells its make, with the name customers know."""
        vehicle_model = self.find(vehicle_type, make, model, year)
        if vehicle_model is None:
            vehicle_model = VehicleModel(
                make=self.makes.get(self.names.make_key(make), make),
                model=self.names.model(make, model),
                vehicle_type=vehicle_type,
                source=source,
            )
            self.new.append(vehicle_model)
            self._index(vehicle_model)
        if vehicle_model.pk is None:
            vehicle_model.year_from = min(vehicle_model.year_from or year, year)
            vehicle_model.year_to = max(vehicle_model.year_to or year, year)
        return vehicle_model

    def save_new(self, reason):
        if self.new:
            bulk_create_with_history(self.new, VehicleModel, batch_size=BATCH, default_change_reason=reason)


def place(catalog, keyed_facts, source):
    """{(vehicle type, make, model, year): Facts} -> [(model, year, Facts)],
    adding the models the catalog does not have (unsaved until save_new)."""
    return [
        (catalog.find_or_add(vehicle_type, make, model, year, source), year, facts)
        for (vehicle_type, make, model, year), facts in sorted(keyed_facts.items())
    ]


def group_by_model_year(placed):
    """[(model, year, Facts)] -> {(model id, year): Facts}, once the models
    are saved. Two names that are one model, such as "MINI" and "Mini", are
    merged."""
    grouped = {}
    for vehicle_model, year, facts in placed:
        key = (vehicle_model.pk, year)
        if key in grouped:
            grouped[key].merge(facts)
        else:
            grouped[key] = facts
    return grouped


def write(source, by_model_year, report, new_models=(), reason=""):
    """Write one source's facts, {(model id, year): Facts}, and count what
    was added, changed and unchanged. Rows the source no longer lists are
    kept; their last_seen shows when it last did."""
    now = timezone.now()
    existing = {(row.vehicle_model_id, row.year): row for row in VehicleModelYear.objects.filter(source=source)}
    created, changed, unchanged = [], [], []
    models_changed = set()
    for (model_id, year), facts in by_model_year.items():
        values = facts.values()
        row = existing.get((model_id, year))
        if row is None:
            created.append(
                VehicleModelYear(
                    vehicle_model_id=model_id, year=year, source=source, first_seen=now, last_seen=now, **values
                )
            )
            models_changed.add(model_id)
        elif any(getattr(row, name) != value for name, value in values.items()):
            for name, value in values.items():
                setattr(row, name, value)
            row.last_seen = now
            changed.append(row)
            models_changed.add(model_id)
        else:
            unchanged.append(row.pk)
    # A row this run does not list, all of whose source ids it now files
    # elsewhere, was moved, such as the Santa Fe Sport rows once filed under
    # the Santa Fe: it goes. Other rows the source stopped listing are kept.
    # Ids are compared within a model year: vPIC's and the Canadian ones repeat across years.
    written_ids = {
        (year, _id_key(found)) for (_, year), facts in by_model_year.items() for found in facts.values()["source_ids"]
    }
    moved = [
        row
        for key, row in existing.items()
        if key not in by_model_year
        and row.source_ids
        and all((row.year, _id_key(found)) in written_ids for found in row.source_ids)
    ]
    VehicleModelYear.objects.filter(pk__in=[row.pk for row in moved]).delete()
    report.counts["model years moved to another model"] += len(moved)

    VehicleModelYear.objects.bulk_create(created, batch_size=BATCH)
    VehicleModelYear.objects.bulk_update(changed, [*FACT_FIELDS, "last_seen"], batch_size=BATCH)
    for start in range(0, len(unchanged), BATCH):
        VehicleModelYear.objects.filter(pk__in=unchanged[start:start + BATCH]).update(last_seen=now)

    model_ids = {model_id for model_id, _ in by_model_year} | {row.vehicle_model_id for row in moved}
    new_ids = {vehicle_model.pk for vehicle_model in new_models}
    models_changed |= refresh_year_ranges(model_ids - new_ids, reason)
    owners = set(VehicleModel.objects.filter(pk__in=model_ids, source=OWNER).values_list("pk", flat=True))

    report.counts["model years added"] += len(created)
    report.counts["model years changed"] += len(changed)
    report.counts["model years unchanged"] += len(unchanged)
    report.counts["models added"] += len(new_ids)
    report.counts["models changed"] += len(models_changed - new_ids)
    report.counts["models unchanged"] += len(model_ids - new_ids - models_changed)
    report.counts["owner's models: facts recorded, model left alone"] += len(owners)


def _id_key(found):
    return tuple(sorted(found.items())) if isinstance(found, dict) else found


def refresh_year_ranges(model_ids, reason):
    """Stretch each model's year range over all its model years, except the
    owner's models, which keep the range the owner gave. Returns the ids changed."""
    spans = (
        VehicleModelYear.objects.filter(vehicle_model_id__in=model_ids)
        .values("vehicle_model_id")
        .annotate(first=Min("year"), last=Max("year"))
    )
    models = VehicleModel.objects.exclude(source=OWNER).in_bulk(model_ids)
    changed = []
    for span in spans:
        vehicle_model = models.get(span["vehicle_model_id"])
        if vehicle_model and (vehicle_model.year_from, vehicle_model.year_to) != (span["first"], span["last"]):
            vehicle_model.year_from, vehicle_model.year_to = span["first"], span["last"]
            changed.append(vehicle_model)
    if changed:
        bulk_update_with_history(
            changed, VehicleModel, ["year_from", "year_to"], batch_size=BATCH, default_change_reason=reason
        )
    return {vehicle_model.pk for vehicle_model in changed}


def _label(vehicle_model):
    return f"{vehicle_model.make} {vehicle_model.model} ({vehicle_model.year_from or '?'}-{vehicle_model.year_to or ''}, {vehicle_model.get_source_display()})"


def merge_duplicates(names, reason):
    """Merge the catalog models that are one vehicle by data/vehicle-names.yaml,
    and give each the name customers know. Returns lines for the report.

    The owner's models are kept, with their names, and the others fold into
    the owner's model whose years are nearest. Otherwise the model already
    named the way customers know it is kept, or the oldest. Each model year,
    override and customer's vehicle of a merged model moves to the one kept;
    its classifications go, and classify_vehicles works them out again. Two
    owner records for the same model year cannot be merged, so that model is
    left alone and listed.
    """
    groups = defaultdict(list)
    for vehicle_model in VehicleModel.objects.order_by("pk"):
        key = (vehicle_model.vehicle_type, names.make_key(vehicle_model.make), names.model_key(vehicle_model.make, vehicle_model.model))
        groups[key].append(vehicle_model)
    lines = []
    renamed = []
    for group in groups.values():
        shown = names.model(group[0].make, group[0].model)
        owners = [vehicle_model for vehicle_model in group if vehicle_model.source == OWNER]
        if owners:
            keep = owners
        else:
            exact = [vehicle_model for vehicle_model in group if vehicle_model.model == shown]
            keep = [(exact or group)[0]]
        for vehicle_model in keep:
            if vehicle_model.source != OWNER and vehicle_model.model != shown:
                renamed.append((vehicle_model, shown))
        for duplicate in group:
            if duplicate in keep:
                continue
            target = min(keep, key=lambda vehicle_model: distance(vehicle_model, duplicate.year_from or 0))
            problem = _merge(duplicate, keep)
            if problem:
                lines.append(f"not merged, left for the owner: {_label(duplicate)} into {_label(target)}: {problem}")
            else:
                lines.append(f"merged {_label(duplicate)} into {target.make} {target.model}")
    for vehicle_model, shown in renamed:
        vehicle_model.refresh_from_db()
        lines.append(f"renamed {_label(vehicle_model)} to {shown}")
        vehicle_model.model = shown
        vehicle_model._change_reason = reason
        vehicle_model.save()
    return lines


def _merge(duplicate, keep):
    """Move everything of duplicate onto the kept models; a reason when it
    cannot be done."""
    rows = list(duplicate.model_years.all())

    def target_for(year):
        return min(keep, key=lambda vehicle_model: distance(vehicle_model, year))

    existing = {
        (row.vehicle_model_id, row.year, row.source): row
        for row in VehicleModelYear.objects.filter(vehicle_model__in=keep)
    }
    for row in rows:
        other = existing.get((target_for(row.year).pk, row.year, row.source))
        if other is not None and row.source == VehicleModelYear.Source.OWNER:
            return f"both have the owner's own figures for {row.year}"
    for row in rows:
        target = target_for(row.year)
        other = existing.get((target.pk, row.year, row.source))
        if other is None:
            row.vehicle_model = target
            row.save()
            existing[(target.pk, row.year, row.source)] = row
        else:
            merge_rows(other, row)
            other.save()
            row.delete()
    for override in ModelOverride.objects.filter(vehicle_model=duplicate):
        override.vehicle_model = target_for(override.year_from or duplicate.year_from or 0)
        override.save()
    for vehicle in Vehicle.objects.filter(vehicle_model=duplicate):
        vehicle.vehicle_model = target_for(vehicle.year or duplicate.year_from or 0)
        vehicle.save()
    ModelYearClassification.objects.filter(vehicle_model=duplicate).delete()
    duplicate.delete()
    refresh_year_ranges({vehicle_model.pk for vehicle_model in keep}, f"merged {duplicate.make} {duplicate.model}")
    return None
