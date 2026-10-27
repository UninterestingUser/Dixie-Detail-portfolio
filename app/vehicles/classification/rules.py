"""The facts a classification rule can test, and how a condition is tested
against one model year.

A rule's conditions map a fact to what it must be:

- a listed fact (EPA size class, drive, body style, cab style, seat rows,
  vPIC vehicle type) or the vehicle type takes a list of values. "none"
  matches a model year no source gives a value for.
- make takes a list of names; model a list of names the model's name is or
  begins with in whole words ("ProMaster" matches "ProMaster 2500"); and
  model_word a list of words or phrases the model's name contains ("HD"
  matches "Silverado HD", "Super Duty" matches "F-250 Super Duty"). Names are
  compared on capitals and digits only, as the import matches them.
- year takes {"from": 2013, "to": 2019}, either end optional.
- a measured fact (GVWR, curb weight, the four dimensions, the volumes)
  takes {"over": 4500} and/or {"up_to": 6000}, in pounds, inches or cubic feet,
  or {"at_least": 490} and/or {"under": 580} where the line itself belongs
  to the upper side.
- box volume takes the same forms, in cubic feet. It is one figure per model
  year, the median trim's length x width x height / 1,728, or the nearest
  measured year's (classification.sizes), so it never straddles.

Trims differ, so a condition is decided by what most of a model year's rows
say: it holds when at least the majority share of them (two-thirds at
launch, in data/vehicle-classes.yaml) meet it, fails when that share do
not, and otherwise the model year straddles it and goes to the review
queue, with the split in the reason. Seat rows are not trims but what was
sold, so an optional third row ([2, 3]) simply does not meet [3]. A record
with no spread of its rows, such as the owner's own figures, is decided on
its whole set or range.

Each fact is read from the owner's own model-year record when it has one.
Otherwise every source that gives the fact is read, and they must agree,
except seat rows, which come from the first source in its list that has
them: the owner-approved third-row list, then NHTSA.
"""

from dataclasses import dataclass
from fractions import Fraction

from vehicles.models import VehicleModel, VehicleModelYear
from vehicles.vehicle_data.names import contains, name_key, words

Source = VehicleModelYear.Source
NONE = "none"


class Outcome:
    HOLDS = "holds"
    FAILS = "fails"
    STRADDLES = "straddles"
    DISAGREE = "disagree"


@dataclass(frozen=True)
class Fact:
    key: str
    label: str
    kind: str  # "model", "names", "model names", "model words", "year", "listed", "measured" or "box volume"
    field: str = ""
    # For seat rows only: the first of these sources with a value is used.
    first_of: tuple = ()
    # False where the values are alternatives sold, not trims: a model year
    # meets the condition only when all of them do.
    by_majority: bool = True


FACTS = {
    fact.key: fact
    for fact in (
        Fact("vehicle_type", "vehicle type", "model", "vehicle_type"),
        Fact("make", "make", "names", "make"),
        Fact("model", "model", "model names", "model"),
        Fact("model_word", "model name", "model words", "model"),
        Fact("year", "model year", "year"),
        Fact("epa_size_class", "EPA size class", "listed", "epa_size_classes"),
        Fact("drive", "drive", "listed", "drives"),
        Fact("body_style", "body style", "listed", "body_styles"),
        Fact("cab_style", "cab style", "listed", "cab_styles"),
        Fact("seat_rows", "seat rows", "listed", "seat_rows", first_of=(Source.SEAT_LIST, Source.VPIC), by_majority=False),
        Fact("source_vehicle_type", "vPIC vehicle type", "listed", "source_vehicle_types"),
        Fact("gvwr", "GVWR", "measured", "gvwr"),
        Fact("curb_weight", "curb weight", "measured", "curb_weight"),
        Fact("length", "length", "measured", "length"),
        Fact("width", "width", "measured", "width"),
        Fact("height", "height", "measured", "height"),
        Fact("wheelbase", "wheelbase", "measured", "wheelbase"),
        Fact("passenger_volume", "passenger volume", "measured", "passenger_volume"),
        Fact("luggage_volume", "luggage volume", "measured", "luggage_volume"),
        Fact("box_volume", "box volume", "box volume", "box_volume"),
    )
}
VEHICLE_TYPES = set(VehicleModel.VehicleType.values)
# The ends a measured condition can give.
BOUNDS = ("over", "up_to", "at_least", "under")


def parse_share(text):
    """"2/3" or 0.75 as a Fraction between one half and one."""
    share = Fraction(str(text))
    if not Fraction(1, 2) < share <= 1:
        raise ValueError(f"The majority share {text} must be over one half and at most 1.")
    return share


def condition_errors(conditions):
    """What is wrong with a rule's conditions, as a list of sentences."""
    if not isinstance(conditions, dict):
        return ["Conditions are a mapping of fact to value."]
    errors = []
    for key, value in conditions.items():
        fact = FACTS.get(key)
        if fact is None:
            errors.append(f"{key!r} is not a fact a rule can use; the facts are {', '.join(FACTS)}.")
        elif fact.kind in ("year", "measured", "box volume"):
            ends = ("from", "to") if fact.kind == "year" else BOUNDS
            if (
                not isinstance(value, dict)
                or not value
                or set(value) - set(ends)
                or not all(isinstance(number, (int, float)) and not isinstance(number, bool) for number in value.values())
            ):
                errors.append(f"{key} takes {{{', '.join(repr(end) + ': a number' for end in ends)}}}, either or both.")
        elif not isinstance(value, list) or not value:
            errors.append(f"{key} takes a list of values.")
        elif key == "vehicle_type" and set(value) - VEHICLE_TYPES:
            errors.append(f"vehicle_type takes {', '.join(sorted(VEHICLE_TYPES))}.")
        elif key == "seat_rows" and not all(isinstance(rows, int) or rows == NONE for rows in value):
            errors.append("seat_rows takes numbers of rows, such as [3].")
    return errors


class ModelYear:
    """One model year of a vehicle model with each source's facts."""

    def __init__(self, vehicle_model, year, rows=()):
        self.vehicle_model = vehicle_model
        self.year = year
        self.rows = {row.source: row for row in rows}
        self._words = None
        # A classification.sizes.BoxVolume, or None, once attach_box_volumes() has run.
        self.box_volume = None
        self.sized = False

    @property
    def model_words(self):
        if self._words is None:
            self._words = words(self.vehicle_model.model)
        return self._words

    def sources_for(self, fact):
        """The records to read for a listed fact, owner first."""
        has = lambda row: bool(getattr(row, fact.field))  # noqa: E731
        owner = self.rows.get(Source.OWNER)
        if owner is not None and has(owner):
            return {Source.OWNER: owner}
        if fact.first_of:
            for source in fact.first_of:
                row = self.rows.get(source)
                if row is not None and has(row):
                    return {source: row}
            return {}
        return {source: row for source, row in self.rows.items() if has(row)}

    def listed(self, fact):
        """{source: set of values} for the sources to read, owner first."""
        return {source: set(getattr(row, fact.field)) for source, row in self.sources_for(fact).items()}

    def measured(self, fact):
        """{source: record} for the sources with a range, owner first."""
        found = {
            source: row
            for source, row in self.rows.items()
            if getattr(row, f"{fact.field}_min") is not None and getattr(row, f"{fact.field}_max") is not None
        }
        if Source.OWNER in found:
            return {Source.OWNER: found[Source.OWNER]}
        return found

    def values(self, key):
        """The combined values of a listed fact, for sizes and reports."""
        found = set()
        for values in self.listed(FACTS[key]).values():
            found |= values
        return found


@dataclass(frozen=True)
class Tested:
    outcome: str
    # How the rows split, for the review queue: "5 of 8 rows (63%)".
    split: str = ""


def _decide(meeting, total, share, by_majority=True):
    if meeting == total:
        return Tested(Outcome.HOLDS)
    if meeting == 0:
        return Tested(Outcome.FAILS)
    if not by_majority:
        return Tested(Outcome.FAILS)
    if Fraction(meeting, total) >= share:
        return Tested(Outcome.HOLDS)
    if Fraction(total - meeting, total) >= share:
        return Tested(Outcome.FAILS)
    return Tested(Outcome.STRADDLES, f"{meeting} of {total} rows ({meeting / total:.0%}) meet it")


def _meets(value, bounds):
    return (
        ("over" not in bounds or value > bounds["over"])
        and ("up_to" not in bounds or value <= bounds["up_to"])
        and ("at_least" not in bounds or value >= bounds["at_least"])
        and ("under" not in bounds or value < bounds["under"])
    )


def _test_listed(row, fact, wanted, share):
    spread = (row.distribution or {}).get(fact.field)
    if isinstance(spread, dict) and spread:
        total = sum(spread.values())
        meeting = sum(count for value, count in spread.items() if value in wanted)
        return _decide(meeting, total, share, fact.by_majority)
    values = {str(value) for value in getattr(row, fact.field)}
    return _decide(len(values & wanted), len(values), share, fact.by_majority)


def _test_measured(row, fact, bounds, share):
    spread = (row.distribution or {}).get(fact.field)
    if isinstance(spread, list) and spread:
        return _decide(sum(1 for value in spread if _meets(value, bounds)), len(spread), share)
    # With only the range, the whole range must be on one side.
    low, high = getattr(row, f"{fact.field}_min"), getattr(row, f"{fact.field}_max")
    if _meets(low, bounds) and _meets(high, bounds):
        return Tested(Outcome.HOLDS)
    if not _meets(low, bounds) and not _meets(high, bounds) and _same_side(low, high, bounds):
        return Tested(Outcome.FAILS)
    return Tested(Outcome.STRADDLES, f"its range, {low} to {high}, spans it")


def _same_side(low, high, bounds):
    """Whether the whole range is beyond the same end of the bounds."""
    below = lambda value: ("over" in bounds and value <= bounds["over"]) or ("at_least" in bounds and value < bounds["at_least"])  # noqa: E731
    above = lambda value: ("up_to" in bounds and value > bounds["up_to"]) or ("under" in bounds and value >= bounds["under"])  # noqa: E731
    return (below(low) and below(high)) or (above(low) and above(high))


def _by_source(per_source):
    """One result from each source's: the sources must agree."""
    if not per_source:
        return None
    outcomes = {tested.outcome for tested in per_source.values()}
    if len(outcomes) > 1:
        return Tested(Outcome.DISAGREE)
    return next(iter(per_source.values()))


def test_condition(model_year, key, wanted, share=Fraction(1)):
    """Whether one condition holds for the model year: a Tested."""
    fact = FACTS[key]
    vehicle_model = model_year.vehicle_model
    if fact.kind == "model":
        return Tested(Outcome.HOLDS if getattr(vehicle_model, fact.field) in wanted else Outcome.FAILS)
    if fact.kind == "names":
        keys = {name_key(name) for name in wanted}
        return Tested(Outcome.HOLDS if name_key(getattr(vehicle_model, fact.field)) in keys else Outcome.FAILS)
    if fact.kind == "model names":
        found = model_year.model_words
        starts = {"".join(found[:count]) for count in range(1, len(found) + 1)}
        return Tested(Outcome.HOLDS if {name_key(name) for name in wanted} & starts else Outcome.FAILS)
    if fact.kind == "model words":
        found = model_year.model_words
        return Tested(Outcome.HOLDS if any(contains(found, words(str(phrase))) for phrase in wanted) else Outcome.FAILS)
    if fact.kind == "year":
        low, high = wanted.get("from"), wanted.get("to")
        inside = (low is None or model_year.year >= low) and (high is None or model_year.year <= high)
        return Tested(Outcome.HOLDS if inside else Outcome.FAILS)
    if fact.kind == "listed":
        wanted = {str(value) for value in wanted}
        per_source = {source: _test_listed(row, fact, wanted, share) for source, row in model_year.sources_for(fact).items()}
        found = _by_source(per_source)
        if found is None:
            return Tested(Outcome.HOLDS if NONE in wanted else Outcome.FAILS)
        return found
    if fact.kind == "box volume":
        # One figure per model year; none, with no measured year, does not hold.
        found = model_year.box_volume
        return Tested(Outcome.HOLDS if found is not None and _meets(found.value, wanted) else Outcome.FAILS)
    # A measured fact no source gives does not hold.
    per_source = {source: _test_measured(row, fact, wanted, share) for source, row in model_year.measured(fact).items()}
    return _by_source(per_source) or Tested(Outcome.FAILS)


@dataclass
class RuleResult:
    outcome: str
    # The conditions that straddle or whose sources disagree, for the review queue.
    reasons: list
    # Outcome.STRADDLES or Outcome.DISAGREE for each reason.
    kinds: list = None


def test_rule(model_year, conditions, share=Fraction(1)):
    """Whether a rule's conditions hold, any fails, or the model year must be
    reviewed because a condition straddles or its sources disagree."""
    reasons, kinds = [], []
    for key, wanted in conditions.items():
        tested = test_condition(model_year, key, wanted, share)
        if tested.outcome == Outcome.FAILS:
            return RuleResult(Outcome.FAILS, [])
        if tested.outcome == Outcome.STRADDLES:
            reasons.append(f"its trims split on the {FACTS[key].label} condition: {tested.split}")
            kinds.append(Outcome.STRADDLES)
        elif tested.outcome == Outcome.DISAGREE:
            reasons.append(f"its sources disagree on the {FACTS[key].label} condition")
            kinds.append(Outcome.DISAGREE)
    if reasons:
        return RuleResult(Outcome.STRADDLES, reasons, kinds)
    return RuleResult(Outcome.HOLDS, [])


# Writing a rule out in plain words, for the control app's rule list and
# preview: "EPA size class Small Sport Utility Vehicle 2WD or Small Sport
# Utility Vehicle 4WD and curb weight over 4,500 lb -> Midsize SUVs".

UNITS = {
    "gvwr": "lb", "curb_weight": "lb", "length": "in", "width": "in", "height": "in", "wheelbase": "in",
    "passenger_volume": "cu ft", "luggage_volume": "cu ft", "box_volume": "cu ft",
}
WORDS = (("over", "over"), ("up_to", "up to"), ("at_least", "at least"), ("under", "under"))


def either(values):
    """["a", "b", "c"] -> "a, b or c"."""
    values = [str(value) for value in values]
    return values[0] if len(values) == 1 else f"{', '.join(values[:-1])} or {values[-1]}"


def _number(value):
    return f"{value:,}" if isinstance(value, int) or float(value).is_integer() else str(value)


def describe_condition(key, value):
    """One condition in plain words, such as "curb weight over 4,500 lb"."""
    fact = FACTS.get(key)
    if fact is None:
        return f"{key} {value}"
    if fact.kind == "year":
        low, high = value.get("from"), value.get("to")
        if low is not None and high is not None:
            return f"model year {low} to {high}"
        return f"model year {low} or later" if low is not None else f"model year up to {high}"
    if fact.kind in ("measured", "box volume"):
        unit = UNITS.get(key, "")
        parts = [f"{word} {_number(value[end])} {unit}".strip() for end, word in WORDS if end in value]
        return f"{fact.label} {' and '.join(parts)}"
    values = [str(found) for found in value]
    named = [found for found in values if found != NONE]
    if key == "model":
        return f"model is or begins with {either(named)}"
    if key == "model_word":
        return f"model name contains {either(named)}"
    if key == "seat_rows":
        return f"{either(named)} seat rows" + (" or none listed" if NONE in values else "")
    if key == "vehicle_type":
        labels = dict(VehicleModel.VehicleType.choices)
        return f"vehicle type {either(labels.get(found, found).lower() for found in named)}"
    if not named:
        return f"no {fact.label} listed"
    return f"{fact.label} {either(named)}" + (" or none listed" if NONE in values else "")


def in_order(conditions):
    """A rule's conditions as (fact, value) in the order of FACTS: what the
    vehicle is, then its classes, then its measures. The database keeps no
    order of its own."""
    order = {key: index for index, key in enumerate(FACTS)}
    return sorted(conditions.items(), key=lambda item: (order.get(item[0], len(order)), item[0]))


def describe_conditions(conditions):
    """A rule's conditions in plain words, joined with "and"."""
    if not conditions:
        return "every model year"
    return " and ".join(describe_condition(key, value) for key, value in in_order(conditions))
