"""Finding vehicle models by name the way every source writes them, and
writing one source's model-year facts.

Nothing here changes a vehicle model whose source is "owner", and an import
writes only rows of its own source, so the owner's own model-year rows are
never touched either.
"""

import re
from collections import defaultdict

from django.db.models import Max, Min
from django.utils import timezone
from simple_history.utils import bulk_create_with_history, bulk_update_with_history

from vehicles.models import VehicleModel, VehicleModelYear

from .facts import FACT_FIELDS

OWNER = VehicleModel.Source.OWNER
BATCH = 2000


def name_key(text):
    """A make or model name as it is matched across sources: capitals and
    digits only, so the EPA's "F150" and vPIC's "F-150" are one model."""
    return re.sub(r"[^A-Z0-9]", "", text.upper())


class Catalog:
    """Every vehicle model, by vehicle type, make and model name."""

    def __init__(self):
        self.models = defaultdict(list)
        self.makes = {}
        self.new = []
        for vehicle_model in VehicleModel.objects.order_by("pk"):
            self._index(vehicle_model)

    def _index(self, vehicle_model):
        key = (vehicle_model.vehicle_type, name_key(vehicle_model.make), name_key(vehicle_model.model))
        self.models[key].append(vehicle_model)
        self.makes.setdefault(name_key(vehicle_model.make), vehicle_model.make)

    def find(self, vehicle_type, make, model, year):
        """The model of that name whose year range holds the year, or the
        nearest one when the owner has split a model by years."""
        found = self.models.get((vehicle_type, name_key(make), name_key(model)))
        if not found:
            return None

        def distance(vehicle_model):
            low, high = vehicle_model.year_from or year, vehicle_model.year_to or year
            return max(low - year, 0, year - high)

        return min(found, key=distance)

    def find_or_add(self, vehicle_type, make, model, year, source):
        """The model of that name, or a new one (saved by save_new) spelled
        as the catalog already spells its make."""
        vehicle_model = self.find(vehicle_type, make, model, year)
        if vehicle_model is None:
            vehicle_model = VehicleModel(
                make=self.makes.get(name_key(make), make), model=model, vehicle_type=vehicle_type, source=source
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
    VehicleModelYear.objects.bulk_create(created, batch_size=BATCH)
    VehicleModelYear.objects.bulk_update(changed, [*FACT_FIELDS, "last_seen"], batch_size=BATCH)
    for start in range(0, len(unchanged), BATCH):
        VehicleModelYear.objects.filter(pk__in=unchanged[start:start + BATCH]).update(last_seen=now)

    model_ids = {model_id for model_id, _ in by_model_year}
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
