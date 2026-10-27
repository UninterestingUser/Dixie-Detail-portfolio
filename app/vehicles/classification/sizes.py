"""Size-based vehicle classes (decision 0082): box volume as a fact, seat
rows for the size-based classes, and the size scheme of
data/size-classes.yaml, classified in memory for
classify_vehicles --scheme size --dry-run.

Box volume is length x width x height / 1,728 in cubic feet. Each
dimension is the median of the model year's trims, read as classification
reads a measured fact (the owner's own figures first, then the Canadian
specifications), as the vehicle size report computes it. A model year with
no dimensions takes the box volume of the nearest measured model year of
the same model, the newer on a tie, "inherited from" that year. apply()
saves each model year's box volume as a ModelYearSize.

The size scheme's rules are tried in order like any rules. A model with no
measurements in any year matches no box-volume rule; it takes the class
where most measured model years of its EPA size class land (the fallback
table), or, with no EPA size class either, waits in the review queue as any
model year no rule matches does. Model overrides, review queue decisions
and approvals name the old classes and are not carried into the scheme.

The dry run creates no class or pricebook record: a class the database does
not have yet, such as Small, is built in memory with its size variants, and
a renamed class (Light Pickups) is a copy of the old record under its new
name, keeping its size variants.
"""

import copy
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache

from django.conf import settings
from django.utils import timezone

from vehicles.models import ClassificationRule, ModelYearSize, SizeVariant, VehicleClass, VehicleModelYear

from .rules import FACTS, condition_errors
from .seed import SeedError, read_data

Source = VehicleModelYear.Source
DATA_FILE = "size-classes.yaml"
DIMENSIONS = ("length", "width", "height")
TENTH = Decimal("0.1")
CUBIC_INCHES = Decimal(1728)
BATCH = 2000


def median(values):
    return Decimal(str(statistics.median(values))) if values else None


def tenth(value):
    return value.quantize(TENTH, ROUND_HALF_UP) if value is not None else None


def trims_of(model_year, name):
    """(each trim's value of a measured fact in one model year, whether the
    record gave a spread of trims): from the record classification reads,
    the owner's own first, then the Canadian specifications, or the two
    ends of a range with no spread."""
    rows = model_year.measured(FACTS[name])
    if not rows:
        return [], False
    row = rows.get(Source.OWNER) or rows.get(Source.CANADA) or rows[sorted(rows)[0]]
    spread = (row.distribution or {}).get(name)
    if isinstance(spread, list) and spread:
        return [Decimal(str(value)) for value in spread], True
    return [getattr(row, f"{name}_min"), getattr(row, f"{name}_max")], False


def measured_box_volume(model_year):
    """The model year's own box volume in cubic feet, or None without all
    three dimensions."""
    found = []
    for name in DIMENSIONS:
        values, _ = trims_of(model_year, name)
        if not values:
            return None
        found.append(tenth(median(values)))
    length, width, height = found
    return tenth(length * width * height / CUBIC_INCHES)


@dataclass(frozen=True)
class BoxVolume:
    value: Decimal
    inherited_from: int = None

    @property
    def source(self):
        return "inherited" if self.inherited_from else "measured"

    def __str__(self):
        inherited = f", inherited from {self.inherited_from}" if self.inherited_from else ""
        return f"{self.value} cu ft{inherited}"


def box_volumes(model_years):
    """{(model id, year): BoxVolume} for every model year that has one."""
    by_model = defaultdict(list)
    for model_year in model_years:
        by_model[model_year.vehicle_model.pk].append((model_year.year, measured_box_volume(model_year)))
    found = {}
    for model_id, years in by_model.items():
        measured = {year: value for year, value in years if value is not None}
        for year, value in years:
            if value is not None:
                found[(model_id, year)] = BoxVolume(value)
            elif measured:
                nearest = min(measured, key=lambda other: (abs(other - year), -other))
                found[(model_id, year)] = BoxVolume(measured[nearest], nearest)
    return found


def attach_box_volumes(model_years):
    """Set each ModelYear's box_volume, for the box-volume condition."""
    found = box_volumes(model_years)
    for model_year in model_years:
        model_year.box_volume = found.get((model_year.vehicle_model.pk, model_year.year))
        model_year.sized = True


def save_box_volumes(model_years, partial=False):
    """Save each model year's box volume as a ModelYearSize. partial, as for
    engine.apply(), leaves other models' alone. Returns counts."""
    now = timezone.now()
    model_ids = {model_year.vehicle_model.pk for model_year in model_years}
    stored = ModelYearSize.objects.all()
    if partial:
        stored = stored.filter(vehicle_model_id__in=model_ids)
    stored = {(row.vehicle_model_id, row.year): row for row in stored}
    created, updated, keys = [], [], set()
    for model_year in model_years:
        if not model_year.sized:
            attach_box_volumes(model_years)
        found = model_year.box_volume
        if found is None:
            continue
        key = (model_year.vehicle_model.pk, model_year.year)
        keys.add(key)
        row = stored.get(key)
        if row is None:
            created.append(ModelYearSize(vehicle_model_id=key[0], year=key[1], box_volume=found.value, inherited_from=found.inherited_from, computed_at=now))
        elif (row.box_volume, row.inherited_from) != (found.value, found.inherited_from):
            row.box_volume, row.inherited_from, row.computed_at = found.value, found.inherited_from, now
            updated.append(row)
    ModelYearSize.objects.bulk_create(created, batch_size=BATCH)
    ModelYearSize.objects.bulk_update(updated, ["box_volume", "inherited_from", "computed_at"], batch_size=BATCH)
    gone = [row.pk for key, row in stored.items() if key not in keys]
    ModelYearSize.objects.filter(pk__in=gone).delete()
    return {"box volumes saved or changed": len(created) + len(updated), "box volumes removed": len(gone)}


# Seat rows for the size-based classes.


@lru_cache(maxsize=4)
def _one_row_classes(data_dir):
    return frozenset(read_data(DATA_FILE, data_dir)["seat_rows"]["one_row_epa_classes"])


def seat_rows(model_year):
    """The size variant values a model year's facts give for a size-based
    class: {1} for an EPA two seater, {3} or {2, 3} (asked) from the
    third-row data, and otherwise {2}."""
    classes = model_year.values("epa_size_class")
    if classes and classes <= _one_row_classes(settings.DATA_DIR):
        return {1}
    rows = {int(count) for count in model_year.values("seat_rows")}
    return rows or {2}


def main_epa_class(model_year):
    """The EPA size class most of the model year's rows give, or ""."""
    counts = Counter()
    for row in model_year.sources_for(FACTS["epa_size_class"]).values():
        spread = (row.distribution or {}).get("epa_size_classes")
        counts.update(spread if isinstance(spread, dict) and spread else {name: 1 for name in row.epa_size_classes})
    return max(sorted(counts), key=lambda name: counts[name]) if counts else ""


# The scheme.


def read_scheme(data_dir=None):
    """data/size-classes.yaml with each rule's line names replaced by their
    box volumes, checked."""
    data = read_data(DATA_FILE, data_dir)
    lines = {line["name"]: line["at"] for line in data["lines"]}
    names = {entry["name"] for entry in data["classes"]}
    for rule in data["rules"]:
        bounds = rule["conditions"].get("box_volume")
        if bounds is not None:
            unknown = [value for value in bounds.values() if isinstance(value, str) and value not in lines]
            if unknown:
                raise SeedError(f"Size rule {rule['name']!r}: no line named {unknown[0]!r} in {DATA_FILE}.")
            rule["conditions"]["box_volume"] = {end: lines.get(value, value) for end, value in bounds.items()}
        errors = condition_errors(rule["conditions"])
        if errors:
            raise SeedError(f"Size rule {rule['name']!r}: {' '.join(errors)}")
        if rule["class"] not in names:
            raise SeedError(f"Size rule {rule['name']!r}: {rule['class']!r} is not a class in {DATA_FILE}.")
    return data


def scheme_classes(data, variants):
    """{name: VehicleClass} for the scheme's classes. One the database has
    is used as it is; a renamed one is a copy under its new name; a new one
    is built in memory, with a made-up negative id, and its size variants
    are added to variants, {class pk: {value: SizeVariant}}."""
    existing = {found.name: found for found in VehicleClass.objects.all()}
    classes = {}
    temporary = 0
    for order, entry in enumerate(data["classes"], start=1):
        name = entry["name"]
        if name in existing:
            classes[name] = existing[name]
        elif "renamed_from" in entry:
            if entry["renamed_from"] not in existing:
                raise SeedError(f"No vehicle class {entry['renamed_from']!r} to rename to {name!r}: run load_pricebook first.")
            classes[name] = copy.copy(existing[entry["renamed_from"]])
            classes[name].name = name
        elif "size_variant_measures" in entry:
            temporary -= 1
            found = VehicleClass(
                pk=temporary, name=name, size_variant_measures=entry["size_variant_measures"], sort_order=order,
                booking=VehicleClass.Booking.QUOTE if entry.get("booking") == "quote" else VehicleClass.Booking.ONLINE,
                photo_card=entry.get("photo_card", ""),
            )
            variants[found.pk] = {}
            for value, label in (entry.get("size_variants") or {}).items():
                temporary -= 1
                variants[found.pk][int(value)] = SizeVariant(pk=temporary, vehicle_class=found, value=int(value), label=label)
            classes[name] = found
        else:
            raise SeedError(f"No vehicle class {name!r}: run load_pricebook first.")
    return classes


def scheme_rules(data, classes):
    """The scheme's rules as unsaved ClassificationRule records, in order."""
    return [
        ClassificationRule(
            position=index * 10, name=entry["name"], conditions=entry["conditions"], vehicle_class=classes[entry["class"]],
            active=True, note=entry.get("note", ""),
        )
        for index, entry in enumerate(data["rules"], start=1)
    ]


@dataclass
class Scheme:
    """The size scheme classified in memory."""

    data: dict
    classes: dict
    rules: list
    # {(model id, year): (ModelYear, Result)}, as classify_catalog returns.
    results: dict
    # {EPA size class: Counter of class names}, from measured model years.
    fallback_counts: dict = field(default_factory=dict)

    @property
    def fallback_table(self):
        """{EPA size class: class name} where most of its measured model years land."""
        return {epa: winner(counts) for epa, counts in self.fallback_counts.items()}

    @property
    def lines(self):
        return self.data["lines"]

    @property
    def pickup_classes(self):
        """The classes the scheme's pickup rules give."""
        return {rule.vehicle_class.name for rule in self.rules if "box_volume" not in rule.conditions and rule.vehicle_class.size_variant_measures == VehicleClass.Measures.CAB_STYLE}

    @property
    def size_classes(self):
        """The classes a box-volume rule gives."""
        return {rule.vehicle_class.name for rule in self.rules if "box_volume" in rule.conditions}


def winner(counts):
    """The class with the most model years; the first by name on a tie."""
    return max(sorted(counts), key=lambda name: counts[name])


def by_box_volume(model_year, result):
    """Whether a box-volume rule gave the model year its class, from its own measurements."""
    return (
        result.rule is not None
        and "box_volume" in result.rule.conditions
        and not result.in_review
        and model_year.box_volume is not None
        and model_year.box_volume.inherited_from is None
    )


def fallback_counts(results):
    """{EPA size class: Counter of class names} over measured model years
    classified by a box-volume rule, by each one's main EPA size class."""
    counts = defaultdict(Counter)
    for model_year, result in results.values():
        if by_box_volume(model_year, result):
            epa = main_epa_class(model_year)
            if epa:
                counts[epa][result.vehicle_class.name] += 1
    return dict(counts)


def apply_fallback(results, counts, classes, variants):
    """Give each model year with no box volume that no rule matched the
    class of its EPA size class in the fallback table, in place."""
    from .engine import Kind, Method, Result, size_for

    for key, (model_year, result) in results.items():
        if model_year.box_volume is not None or not result.in_review or Kind.NO_RULE not in result.kinds:
            continue
        epa = main_epa_class(model_year)
        if not epa:
            result.reasons = ["no rule matches: no dimensions in any year and no EPA size class"]
            continue
        if epa not in counts:
            result.reasons = [f"no rule matches: no dimensions in any year, and no measured model year is in {epa}"]
            continue
        vehicle_class = classes[winner(counts[epa])]
        size, ask = size_for(vehicle_class, model_year, variants)
        reason = f"no dimensions in any year; most measured {epa} model years are {vehicle_class}"
        results[key] = (model_year, Result(vehicle_class, size, ask, Method.EPA_FALLBACK, reasons=[reason]))


def classify_scheme(data_dir=None, model_years=None):
    """The Scheme: data/size-classes.yaml's rules applied to the whole
    catalog in memory, with no overrides or queue decisions, and the
    EPA-class fallback. Saves nothing."""
    from .engine import active_variants, catalog_model_years, classify_catalog

    data = read_scheme(data_dir)
    variants = active_variants()
    classes = scheme_classes(data, variants)
    rules = scheme_rules(data, classes)
    model_years = catalog_model_years() if model_years is None else model_years
    attach_box_volumes(model_years)
    results = classify_catalog(rules=rules, overrides=[], decisions=[], model_years=model_years, variants=variants)
    counts = fallback_counts(results)
    apply_fallback(results, counts, classes, variants)
    return Scheme(data, classes, rules, results, counts)
