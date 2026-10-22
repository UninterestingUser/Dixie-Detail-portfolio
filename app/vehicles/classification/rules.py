"""The facts a classification rule can test, and how a condition is tested
against one model year.

A rule's conditions map a fact to what it must be:

- a listed fact (EPA size class, drive, body style, cab style, seat rows,
  vPIC vehicle type) or the vehicle type takes a list of values. "none"
  matches a model year no source gives a value for.
- make takes a list of names, and model a list of names the model's name is
  or begins with in whole words ("ProMaster" matches "ProMaster 2500"), both
  compared on capitals and digits only, as the import matches names.
- year takes {"from": 2013, "to": 2019}, either end optional.
- a measured fact (GVWR, curb weight, the four dimensions, the volumes)
  takes {"over": 4500} and/or {"up_to": 6000}, in pounds, inches or cubic feet.

Trims differ, so a condition holds when it holds for every trim, fails when
it holds for none, and straddles when it holds for some: all of a model
year's EPA size classes are in the list, or its whole curb weight range is
over the threshold. A model year whose facts straddle a rule, or whose
sources disagree about a fact the rule tests, goes to the review queue.

Each fact is read from the owner's own model-year record when it has one.
Otherwise every source that gives the fact is read, and they must agree,
except seat rows, which come from the first source in its list that has
them: the owner-approved third-row list, then NHTSA.
"""

from dataclasses import dataclass

from vehicles.models import VehicleModel, VehicleModelYear
from vehicles.vehicle_data.canada import words
from vehicles.vehicle_data.catalog import name_key

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
    kind: str  # "model", "names", "model names", "year", "listed" or "measured"
    field: str = ""
    # For seat rows only: the first of these sources with a value is used.
    first_of: tuple = ()


FACTS = {
    fact.key: fact
    for fact in (
        Fact("vehicle_type", "vehicle type", "model", "vehicle_type"),
        Fact("make", "make", "names", "make"),
        Fact("model", "model", "model names", "model"),
        Fact("year", "model year", "year"),
        Fact("epa_size_class", "EPA size class", "listed", "epa_size_classes"),
        Fact("drive", "drive", "listed", "drives"),
        Fact("body_style", "body style", "listed", "body_styles"),
        Fact("cab_style", "cab style", "listed", "cab_styles"),
        Fact("seat_rows", "seat rows", "listed", "seat_rows", first_of=(Source.SEAT_LIST, Source.VPIC)),
        Fact("source_vehicle_type", "vPIC vehicle type", "listed", "source_vehicle_types"),
        Fact("gvwr", "GVWR", "measured", "gvwr"),
        Fact("curb_weight", "curb weight", "measured", "curb_weight"),
        Fact("length", "length", "measured", "length"),
        Fact("width", "width", "measured", "width"),
        Fact("height", "height", "measured", "height"),
        Fact("wheelbase", "wheelbase", "measured", "wheelbase"),
        Fact("passenger_volume", "passenger volume", "measured", "passenger_volume"),
        Fact("luggage_volume", "luggage volume", "measured", "luggage_volume"),
    )
}
VEHICLE_TYPES = set(VehicleModel.VehicleType.values)


def condition_errors(conditions):
    """What is wrong with a rule's conditions, as a list of sentences."""
    if not isinstance(conditions, dict):
        return ["Conditions are a mapping of fact to value."]
    errors = []
    for key, value in conditions.items():
        fact = FACTS.get(key)
        if fact is None:
            errors.append(f"{key!r} is not a fact a rule can use; the facts are {', '.join(FACTS)}.")
        elif fact.kind in ("year", "measured"):
            ends = ("from", "to") if fact.kind == "year" else ("over", "up_to")
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
        self._prefixes = None

    @property
    def model_prefixes(self):
        if self._prefixes is None:
            parts = words(self.vehicle_model.model)
            self._prefixes = {"".join(parts[:count]) for count in range(1, len(parts) + 1)}
        return self._prefixes

    def listed(self, fact):
        """{source: set of values} for the sources to read, owner first."""
        owner = self.rows.get(Source.OWNER)
        if owner is not None and getattr(owner, fact.field):
            return {Source.OWNER: set(getattr(owner, fact.field))}
        if fact.first_of:
            for source in fact.first_of:
                row = self.rows.get(source)
                if row is not None and getattr(row, fact.field):
                    return {source: set(getattr(row, fact.field))}
            return {}
        return {source: set(getattr(row, fact.field)) for source, row in self.rows.items() if getattr(row, fact.field)}

    def measured(self, fact):
        """{source: (lowest, highest)}, owner first."""
        found = {}
        for source, row in self.rows.items():
            low, high = getattr(row, f"{fact.field}_min"), getattr(row, f"{fact.field}_max")
            if low is not None and high is not None:
                found[source] = (low, high)
        if Source.OWNER in found:
            return {Source.OWNER: found[Source.OWNER]}
        return found

    def values(self, key):
        """The combined values of a listed fact, for sizes and reports."""
        found = set()
        for values in self.listed(FACTS[key]).values():
            found |= values
        return found


def _combine(outcomes):
    if Outcome.FAILS in outcomes:
        return Outcome.FAILS
    if Outcome.STRADDLES in outcomes:
        return Outcome.STRADDLES
    return Outcome.HOLDS


def _test_set(values, wanted):
    hits = len(values & wanted)
    if hits == len(values):
        return Outcome.HOLDS
    return Outcome.FAILS if hits == 0 else Outcome.STRADDLES


def _test_range(low, high, bounds):
    outcomes = []
    if "over" in bounds:
        over = bounds["over"]
        outcomes.append(Outcome.HOLDS if low > over else Outcome.FAILS if high <= over else Outcome.STRADDLES)
    if "up_to" in bounds:
        up_to = bounds["up_to"]
        outcomes.append(Outcome.HOLDS if high <= up_to else Outcome.FAILS if low > up_to else Outcome.STRADDLES)
    return _combine(outcomes)


def _by_source(per_source):
    """One outcome from each source's: the sources must agree."""
    if not per_source:
        return None
    found = set(per_source.values())
    return found.pop() if len(found) == 1 else Outcome.DISAGREE


def test_condition(model_year, key, wanted):
    """Whether one condition holds for the model year: an Outcome."""
    fact = FACTS[key]
    vehicle_model = model_year.vehicle_model
    if fact.kind == "model":
        return Outcome.HOLDS if getattr(vehicle_model, fact.field) in wanted else Outcome.FAILS
    if fact.kind == "names":
        keys = {name_key(name) for name in wanted}
        return Outcome.HOLDS if name_key(getattr(vehicle_model, fact.field)) in keys else Outcome.FAILS
    if fact.kind == "model names":
        keys = {name_key(name) for name in wanted}
        return Outcome.HOLDS if keys & model_year.model_prefixes else Outcome.FAILS
    if fact.kind == "year":
        low, high = wanted.get("from"), wanted.get("to")
        inside = (low is None or model_year.year >= low) and (high is None or model_year.year <= high)
        return Outcome.HOLDS if inside else Outcome.FAILS
    if fact.kind == "listed":
        wanted = {str(value) for value in wanted}
        per_source = {
            source: _test_set({str(value) for value in values}, wanted)
            for source, values in model_year.listed(fact).items()
        }
        found = _by_source(per_source)
        if found is None:
            return Outcome.HOLDS if NONE in wanted else Outcome.FAILS
        return found
    # A measured fact no source gives does not hold.
    per_source = {source: _test_range(low, high, wanted) for source, (low, high) in model_year.measured(fact).items()}
    return _by_source(per_source) or Outcome.FAILS


@dataclass
class RuleResult:
    outcome: str
    # The conditions that straddle or whose sources disagree, for the review queue.
    reasons: list


def test_rule(model_year, conditions):
    """Whether a rule's conditions all hold, any fails, or the model year
    must be reviewed because a condition straddles or its sources disagree."""
    reasons = []
    for key, wanted in conditions.items():
        outcome = test_condition(model_year, key, wanted)
        if outcome == Outcome.FAILS:
            return RuleResult(Outcome.FAILS, [])
        if outcome == Outcome.STRADDLES:
            reasons.append(f"its trims straddle the {FACTS[key].label} condition")
        elif outcome == Outcome.DISAGREE:
            reasons.append(f"its sources disagree on the {FACTS[key].label} condition")
    if reasons:
        return RuleResult(Outcome.STRADDLES, reasons)
    return RuleResult(Outcome.HOLDS, [])
