"""Size-based vehicle classes (decisions 0082 and 0083): box volume as a
fact, seat rows for the size-based classes, the rules of
data/size-classes.yaml, and the steps that follow them.

Box volume is length x width x height / 1,728 in cubic feet. Each
dimension is the median of the model year's trims, read as classification
reads a measured fact (the owner's own figures first, then the Canadian
specifications), as the vehicle size report computes it. A model year with
no dimensions takes the box volume of the nearest measured model year of
the same model, the newer on a tie, "inherited from" that year. apply()
saves each model year's box volume as a ModelYearSize.

The rules are the launch rules classification.seed creates from
data/size-classes.yaml and are tried in order like any rules. finish()
then takes three steps, in this order:

1. Pickups in every model year, then the pickup line: a model a pickup rule
   catches in any model year is a pickup in all of them (decision 0085); a
   pickup that has a box volume goes on its side of the pickup line, and
   one with no box volume in any year keeps the class of its rule, from its
   EPA label.
2. The EPA size class fallback: a model with no measurements in any year
   matches no box-volume rule; it takes the class where most measured model
   years of its EPA size class land (the fallback table), or, with no EPA
   size class either, waits in the review queue as any model year no rule
   matches does.
3. Smoothing: a short run of model years between two runs of one class
   takes that class.
4. The three-row floor: a Small model year with three seat rows, whatever
   made it three rows, is Medium (decision 0086).

Model overrides and review queue decisions beat all three, and are never
smoothed.
"""

import copy
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache

from django.conf import settings
from django.utils import timezone

from vehicles.models import ModelYearClassification, ModelYearSize, VehicleClass, VehicleModelYear

from .rules import FACTS, condition_errors
from .seed import SeedError, read_data

Source = VehicleModelYear.Source
Method = ModelYearClassification.Method
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
def _seat_settings(data_dir):
    data = read_data(DATA_FILE, data_dir)
    settings_ = data["seat_rows"]
    return {
        "one_row": frozenset(settings_["one_row_epa_classes"]),
        "one_row_only_in": frozenset(settings_["one_row_only_in"]),
        "always_three_classes": frozenset(settings_["always_three_classes"]),
        "minivan_epa": frozenset(settings_["minivan_epa_classes"]),
        "minivan_models": tuple(data["minivan_models"]),
    }


def seat_rows(model_year, vehicle_class=None):
    """The size variant values a model year's facts give for a size-based
    class (data/size-classes.yaml, decision 0085): always {3} in Full-size,
    for an EPA minivan class, and for a listed minivan with no EPA size
    class; {1} for an EPA two seater, but only in Small (two rows in a larger
    class); otherwise {3} or {2, 3} (asked) from the third-row data, or {2}."""
    from .rules import NONE, Outcome, test_condition

    found = _seat_settings(settings.DATA_DIR)
    if vehicle_class is not None and vehicle_class.name in found["always_three_classes"]:
        return {3}
    classes = model_year.values("epa_size_class")
    if classes & found["minivan_epa"]:
        return {3}
    if not classes and test_condition(model_year, "model", list(found["minivan_models"])).outcome == Outcome.HOLDS:
        return {3}
    if classes and classes <= found["one_row"]:
        if vehicle_class is None or vehicle_class.name in found["one_row_only_in"]:
            return {1}
        return {2}
    rows = {int(count) for count in model_year.values("seat_rows") if count != NONE}
    return rows or {2}


def main_epa_class(model_year):
    """The EPA size class most of the model year's rows give, or ""."""
    counts = Counter()
    for row in model_year.sources_for(FACTS["epa_size_class"]).values():
        spread = (row.distribution or {}).get("epa_size_classes")
        counts.update(spread if isinstance(spread, dict) and spread else {name: 1 for name in row.epa_size_classes})
    return max(sorted(counts), key=lambda name: counts[name]) if counts else ""


# The rules and the steps after them.


@lru_cache(maxsize=4)
def _scheme(data_dir):
    data = read_data(DATA_FILE, data_dir)
    lines = {line["name"]: line["at"] for line in data["lines"]}
    names = {entry["name"] for entry in read_data("vehicle-classes.yaml", data_dir)["classes"]}
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
            raise SeedError(f"Size rule {rule['name']!r}: {rule['class']!r} is not a class in vehicle-classes.yaml.")
    for line in [*data["lines"], data["pickup_line"], {"name": "three_row_floor", **data["three_row_floor"]}]:
        for side in ("below", "above"):
            if line[side] not in names:
                raise SeedError(f"Line {line['name']!r}: {line[side]!r} is not a class in vehicle-classes.yaml.")
    return data


def read_scheme(data_dir=None):
    """data/size-classes.yaml with each rule's line names replaced by their
    box volumes, checked against the classes of data/vehicle-classes.yaml."""
    return copy.deepcopy(_scheme(data_dir or settings.DATA_DIR))


@dataclass
class Scheme:
    """The catalog as the size-based rules classify it, for the reports."""

    data: dict
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
    def pickup_line(self):
        return self.data["pickup_line"]

    @property
    def pickup_classes(self):
        """The classes on either side of the pickup line."""
        return {self.pickup_line["below"], self.pickup_line["above"]}

    @property
    def size_classes(self):
        """The classes on either side of the box-volume lines."""
        return {line[side] for line in self.lines for side in ("below", "above")}


def winner(counts):
    """The class with the most model years; the first by name on a tie."""
    return max(sorted(counts), key=lambda name: counts[name])


def by_box_volume(model_year, result):
    """Whether a box-volume rule gave the model year its class, from its own measurements."""
    return (
        result.method == Method.RULE
        and result.rule is not None
        and "box_volume" in result.rule.conditions
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


def classes_by_name():
    return {found.name: found for found in VehicleClass.objects.all()}


# What a model's pickup years may turn into a pickup: years the rules, the
# EPA size class fallback or nothing classed, never an override, a queue
# decision or the photo cards.
PICKUP_MODEL_FROM = {Method.RULE, Method.EPA_FALLBACK, Method.REVIEW}


def apply_pickup_models(results, line, classes, variants):
    """Make every model year of a model that a pickup rule catches in any
    model year a pickup, in place (decision 0085): it takes the class its
    pickup years mostly have, which the pickup line then settles where it
    has a box volume. Returns the ids of the models it changed."""
    from .engine import Result, size_for, year_spans

    sides = {line["below"], line["above"]}
    pickups = defaultdict(list)
    for (model_id, year), (model_year, result) in results.items():
        if result.method == Method.RULE and result.vehicle_class is not None and result.vehicle_class.name in sides:
            pickups[model_id].append((year, result))
    changed = set()
    for key, (model_year, result) in list(results.items()):
        found = pickups.get(key[0])
        if not found or result.method not in PICKUP_MODEL_FROM:
            continue
        if result.method == Method.RULE and result.vehicle_class is not None and result.vehicle_class.name in sides:
            continue
        counts = Counter(found_result.vehicle_class.name for _, found_result in found)
        vehicle_class = classes[winner(counts)]
        _, nearest = min(found, key=lambda entry: (abs(entry[0] - key[1]), -entry[0]))
        spans = year_spans([(model_year.vehicle_model, year, "") for year, _ in found])
        years = ", ".join(str(first) if first == last else f"{first}-{last}" for _, first, last, _ in spans)
        reason = f"a pickup in every model year: {years} are pickups by rule {nearest.rule.position} ({nearest.rule.name})"
        size, ask = size_for(vehicle_class, model_year, variants)
        results[key] = (model_year, Result(vehicle_class, size, ask, Method.PICKUP_MODEL, rule=nearest.rule, reasons=[reason]))
        changed.add(key[0])
    return changed


def apply_pickup_line(results, line, classes, variants):
    """Put each pickup that has a box volume on its side of the pickup line,
    in place. One with no box volume keeps the class its EPA label gives."""
    from .engine import Result, size_for

    sides = {line["below"], line["above"]}
    for key, (model_year, result) in results.items():
        if result.method not in (Method.RULE, Method.PICKUP_MODEL) or result.vehicle_class is None or result.vehicle_class.name not in sides:
            continue
        if model_year.box_volume is None:
            continue
        above = model_year.box_volume.value >= line["at"]
        vehicle_class = classes[line["above"] if above else line["below"]]
        size, ask = size_for(vehicle_class, model_year, variants)
        side = "at or over" if above else "under"
        if result.method == Method.PICKUP_MODEL:
            reason = f"{result.reasons[0]}, {side} the {line['at']} cu ft pickup line"
        else:
            reason = f"a pickup by rule {result.rule.position} ({result.rule.name}), {side} the {line['at']} cu ft pickup line"
        results[key] = (model_year, Result(vehicle_class, size, ask, Method.PICKUP_LINE, rule=result.rule, reasons=[reason]))


def apply_fallback(results, counts, classes, variants):
    """Give each model year with no box volume that no rule matched the
    class of its EPA size class in the fallback table, in place."""
    from .engine import Kind, Result, size_for

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


# What smoothing may change: classes the rules and the steps gave, never an
# override, a queue decision, a year carried from the nearest one, or a year
# already smoothed.
SMOOTHABLE = {Method.RULE, Method.PICKUP_LINE, Method.PICKUP_MODEL, Method.EPA_FALLBACK}


def runs_of(entries):
    """[(class name, [(year, ModelYear, Result)])] for one model's classified
    years in order, each run one class."""
    runs = []
    for entry in entries:
        result = entry[2]
        if result.vehicle_class is None or result.in_review:
            continue
        if runs and runs[-1][0] == result.vehicle_class.name:
            runs[-1][1].append(entry)
        else:
            runs.append((result.vehicle_class.name, [entry]))
    return runs


def smooth(results, variants, max_years):
    """Give each run of up to max_years model years between two runs of one
    class that class, in place, until no such run is left. Returns
    [(vehicle model, first, last, old class name, new class name)]."""
    from .engine import Result, size_for, years_text

    by_model = defaultdict(list)
    for (model_id, year), (model_year, result) in results.items():
        by_model[model_id].append((year, model_year, result))
    smoothed = []
    for model_id, entries in by_model.items():
        while True:
            entries = sorted((year, *results[(model_id, year)]) for year, _, _ in entries)
            runs = runs_of(entries)
            found = next(
                (
                    index
                    for index in range(1, len(runs) - 1)
                    if runs[index - 1][0] == runs[index + 1][0]
                    and len(runs[index][1]) <= max_years
                    and all(result.method in SMOOTHABLE for _, _, result in runs[index][1])
                ),
                None,
            )
            if found is None:
                break
            run = runs[found][1]
            target = runs[found - 1][1][-1][2].vehicle_class
            first, last = run[0][0], run[-1][0]
            for year, model_year, result in run:
                size, ask = size_for(target, model_year, variants)
                reason = f"smoothed: {years_text(first, last)} lies between two runs of {target}; {result.because} gives {result.vehicle_class}"
                results[(model_id, year)] = (model_year, Result(target, size, ask, Method.SMOOTHED, rule=result.rule, reasons=[reason]))
            smoothed.append((run[0][1].vehicle_model, first, last, runs[found][0], target.name))
    return smoothed


def finish(results, variants, classes=None, data_dir=None):
    """The steps after the rules, in place: pickups in every model year,
    the pickup line, the EPA size class fallback, smoothing and the
    three-row floor. Returns the smoothed runs."""
    data = read_scheme(data_dir)
    classes = classes or classes_by_name()
    apply_pickup_models(results, data["pickup_line"], classes, variants)
    apply_pickup_line(results, data["pickup_line"], classes, variants)
    apply_fallback(results, fallback_counts(results), classes, variants)
    smoothed = smooth(results, variants, data["smoothing"]["max_years"])
    apply_three_row_floor(results, data["three_row_floor"], classes, variants)
    return smoothed


# What the three-row floor may lift: classes the rules and the steps gave,
# never a model override or a review queue decision.
FLOOR_FROM = {Method.RULE, Method.EPA_FALLBACK, Method.SMOOTHED}


def apply_three_row_floor(results, floor, classes, variants):
    """Give each model year of the class below that has three seat rows,
    once seat rows are final, the class above, in place (decision 0086)."""
    from .engine import Result, size_for

    above = classes[floor["above"]]
    for key, (model_year, result) in results.items():
        if result.method not in FLOOR_FROM or result.vehicle_class is None or result.vehicle_class.name != floor["below"]:
            continue
        if seat_rows(model_year, result.vehicle_class) != {3}:
            continue
        size, ask = size_for(above, model_year, variants)
        reason = f"three seat rows, so at least {above}; {result.because} gives {result.vehicle_class}"
        results[key] = (model_year, Result(above, size, ask, Method.THREE_ROW_FLOOR, rule=result.rule, reasons=[reason]))


def classify_scheme(model_years=None):
    """The Scheme: the whole catalog classified with the saved rules,
    overrides and decisions, as classify_vehicles would apply them. Saves
    nothing."""
    from .engine import classify_catalog

    results = classify_catalog(model_years=model_years)
    return Scheme(read_scheme(), results, fallback_counts(results))


# A customer's vehicle with no year.


def dimensions_of(model_year):
    found = {}
    for name in DIMENSIONS:
        values, _ = trims_of(model_year, name)
        found[name] = tenth(median(values))
    return found if all(value is not None for value in found.values()) else None


def newest_generation(entries, spread=1):
    """(Result, first year, last year) for the newest generation of one
    model, entries [(year, ModelYear, Result)]: its newest measured model
    year and the years before it whose length, width and height each stay
    within spread inches, with any later years that have no measurements.
    The Result is the class most of its classified years have, the newest on
    a tie. None when none of them has a class."""
    entries = sorted(entries, key=lambda entry: entry[0])
    measured = [(year, dimensions_of(model_year)) for year, model_year, _ in entries]
    measured = [(year, found) for year, found in measured if found]
    if measured:
        newest = measured[-1][0]
        first = newest
        kept = [measured[-1][1]]
        for year, found in reversed(measured[:-1]):
            trial = kept + [found]
            if any(max(row[name] for row in trial) - min(row[name] for row in trial) > spread for name in DIMENSIONS):
                break
            kept, first = trial, year
        generation = [entry for entry in entries if entry[0] >= first]
    else:
        generation = entries
    classified = [(year, result) for year, _, result in generation if result.vehicle_class is not None and not result.in_review]
    if not classified:
        return None
    counts = Counter(result.vehicle_class.name for _, result in classified)
    top = max(counts.values())
    result = next(result for _, result in reversed(classified) if counts[result.vehicle_class.name] == top)
    return result, generation[0][0], generation[-1][0]


# What the price book must price.


def produced(results, variants):
    """{(class name, size variant value or None): [model year names]} for
    every class and size the rules give a model year, online-booked classes
    only: a seat-row class by the rows its facts give (both when asked), a
    cab-style class by cab (every size it has when the facts do not say),
    and a class with one price by itself."""
    from .engine import fact_sizes

    found = defaultdict(list)
    for (model_id, year), (model_year, result) in results.items():
        vehicle_class = result.vehicle_class
        if vehicle_class is None or result.in_review or vehicle_class.booking != VehicleClass.Booking.ONLINE:
            continue
        offered = variants.get(vehicle_class.pk, {})
        if not offered and vehicle_class.size_variant_measures == VehicleClass.Measures.NONE:
            values = {None}
        else:
            values = fact_sizes(vehicle_class, model_year)
            if None in values:
                values = (values - {None}) | set(offered)
            if result.size_variant is not None:
                values.add(result.size_variant.value)
        name = f"{year} {model_year.vehicle_model.make} {model_year.vehicle_model.model}"
        for value in values:
            found[(vehicle_class.name, value)].append(name)
    return dict(found)
