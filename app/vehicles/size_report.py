"""Size ranges and box volume from the measured dimensions in the vehicle
catalog. The apply_size_classes report (classification/size_preview.py)
builds its ladders from them. This began as the vehicle_size_report
command, which gathered the facts for decision 0082 from the body-type
classes; the command was removed on 2026-11-04, once those classes were
retired and the apply_size_classes and classify_vehicles reports had
replaced it.

It reads only facts already in the database and changes nothing. build()
covers the catalog model years in the body-type classes Coupes & Sedans,
Crossovers & Wagons and Midsize SUVs, Fullsize SUVs & Minivans (retired by
apply_size_classes, decision 0083, after which only the review queue's part
is left), and the model years waiting in the review queue with no class
whose EPA size class is a car, station-wagon or SUV class ("in queue").

A model's consecutive model years make one size range while they keep the
same class and seat rows and their length, width and height each stay
within 1 inch. Where trims differ, each model year's figure is the median of
its trims, read as classification reads a measured fact (the owner's own
figures first); a range's figure is the median of its years'. Box volume,
length x width x height / 1,728, is a rough measure of bulk in cubic feet.
Customers appear only as counts.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q

from appointments.models import Appointment
from vehicles.classification.engine import catalog_model_years, years_text
from vehicles.classification.rules import FACTS
from vehicles.classification.sizes import median, tenth, trims_of
from vehicles.models import ModelYearClassification, Vehicle

COUPES = "Coupes & Sedans"
CROSSOVERS = "Crossovers & Wagons"
MIDSIZE = "Midsize SUVs"
FULLSIZE = "Fullsize SUVs & Minivans"
SCOPE = (COUPES, CROSSOVERS, MIDSIZE, FULLSIZE)
IN_QUEUE = "in queue"
CAR_CLASSES = ("Two Seaters", "Minicompact Cars", "Subcompact Cars", "Compact Cars", "Midsize Cars", "Large Cars")
DIMENSIONS = ("length", "width", "height")
MEASURES = ("length", "width", "height", "wheelbase", "curb_weight")
# How far a range's length, width and height may each spread, in inches.
SPREAD = Decimal(1)
CUBIC_INCHES = Decimal(1728)
NEWEST_FROM = 2015
DOORS = {"two-door": "2", "four-door": "4", "hatchback": "hatchback"}
DRIVE = re.compile(r"\s*(?:-\s*|/)?[24]wd$", re.IGNORECASE)


def epa_base(name):
    """An EPA size class without its drive: "Small Sport Utility Vehicle 4WD"
    -> "Small Sport Utility Vehicle"."""
    return DRIVE.sub("", name).strip()


def epa_kind(base):
    """"car", "wagon", "suv" or "" for an EPA size class without its drive."""
    lowered = base.lower()
    if base in CAR_CLASSES:
        return "car"
    if "station wagon" in lowered:
        return "wagon"
    if "sport utility" in lowered or "special purpose" in lowered:
        return "suv"
    return ""


def whole(value):
    return value.quantize(Decimal(1), ROUND_HALF_UP) if value is not None else None


@dataclass
class YearFacts:
    """One model year's facts as the size ranges use them."""

    year: int
    vehicle_class: str
    seat_rows: str
    doors: set
    # {EPA size class without its drive: rows}
    epa: dict
    measures: dict
    trims: int = 0
    shortest: Decimal = None
    longest: Decimal = None

    @property
    def has_dimensions(self):
        return all(self.measures.get(name) is not None for name in DIMENSIONS)


def seat_rows_label(model_year):
    """"2", "3", "optional" (both sold) or "" when no source lists them."""
    rows = {int(value) for value in model_year.values("seat_rows")}
    if rows == {2}:
        return "2"
    if rows == {3}:
        return "3"
    if {2, 3} <= rows:
        return "optional"
    return ""


def year_facts(model_year, class_name):
    epa = defaultdict(int)
    for row in model_year.sources_for(FACTS["epa_size_class"]).values():
        spread = (row.distribution or {}).get("epa_size_classes")
        counts = spread if isinstance(spread, dict) and spread else {name: 1 for name in row.epa_size_classes}
        for name, count in counts.items():
            epa[epa_base(name)] += count
    measures = {}
    for name in MEASURES:
        values, _ = trims_of(model_year, name)
        found = median(values)
        measures[name] = whole(found) if name == "curb_weight" else tenth(found)
    lengths, spread = trims_of(model_year, "length")
    doors = {DOORS[style] for style in model_year.values("body_style") if style in DOORS}
    return YearFacts(
        model_year.year, class_name, seat_rows_label(model_year), doors, dict(epa), measures,
        trims=len(lengths) if spread else 0,
        shortest=min(lengths) if lengths else None,
        longest=max(lengths) if lengths else None,
    )


@dataclass
class SizeRange:
    """Consecutive model years of one model with the same class and seat
    rows whose length, width and height each stay within 1 inch."""

    vehicle_model: object
    years: list = field(default_factory=list)
    vehicles: int = 0
    jobs: int = 0
    vehicles_no_year: int = 0

    def fits(self, facts):
        last = self.years[-1]
        if facts.year != last.year + 1 or facts.vehicle_class != last.vehicle_class or facts.seat_rows != last.seat_rows:
            return False
        if not self.has_dimensions or not facts.has_dimensions:
            return self.has_dimensions == facts.has_dimensions
        for name in DIMENSIONS:
            values = [found.measures[name] for found in self.years] + [facts.measures[name]]
            if max(values) - min(values) > SPREAD:
                return False
        return True

    @property
    def first(self):
        return self.years[0].year

    @property
    def last(self):
        return self.years[-1].year

    @property
    def years_label(self):
        return years_text(self.first, self.last)

    @property
    def name(self):
        return f"{self.vehicle_model.make} {self.vehicle_model.model} {self.years_label}"

    @property
    def vehicle_class(self):
        return self.years[0].vehicle_class

    @property
    def seat_rows(self):
        return self.years[0].seat_rows

    @property
    def has_dimensions(self):
        return self.years[0].has_dimensions

    @property
    def doors(self):
        found = set().union(*(facts.doors for facts in self.years))
        return ", ".join(sorted(found, key=lambda door: (not door.isdigit(), door)))

    @property
    def epa_counts(self):
        counts = defaultdict(int)
        for facts in self.years:
            for name, count in facts.epa.items():
                counts[name] += count
        return counts

    @property
    def epa_main(self):
        """The EPA size class most of the range's rows give, or ""."""
        counts = self.epa_counts
        return max(sorted(counts), key=lambda name: counts[name]) if counts else ""

    @property
    def kind(self):
        """"car", "wagon" or "suv" by the main EPA size class; a model in a
        car class with no EPA class counts as a car."""
        kind = epa_kind(self.epa_main)
        if not kind and self.vehicle_class == COUPES:
            return "car"
        return kind

    def measure(self, name):
        found = median([facts.measures[name] for facts in self.years if facts.measures[name] is not None])
        return whole(found) if name == "curb_weight" else tenth(found)

    @property
    def box_volume(self):
        """Length x width x height / 1,728, in cubic feet."""
        if not self.has_dimensions:
            return None
        length, width, height = (self.measure(name) for name in DIMENSIONS)
        return tenth(length * width * height / CUBIC_INCHES)

    @property
    def trims(self):
        return max(facts.trims for facts in self.years)

    @property
    def shortest(self):
        found = [facts.shortest for facts in self.years if facts.shortest is not None]
        return tenth(min(found)) if found else None

    @property
    def longest(self):
        found = [facts.longest for facts in self.years if facts.longest is not None]
        return tenth(max(found)) if found else None



def size_ranges(vehicle_model, years):
    """[SizeRange] for one model's YearFacts, oldest first."""
    found = []
    for facts in sorted(years, key=lambda facts: facts.year):
        if found and found[-1].fits(facts):
            found[-1].years.append(facts)
        else:
            found.append(SizeRange(vehicle_model, [facts]))
    return found


def in_scope():
    """{(model id, year): class name or "in queue"} for the model years in
    scope; queue years are checked for their EPA size class afterwards."""
    found = {}
    rows = ModelYearClassification.objects.filter(
        Q(vehicle_class__name__in=SCOPE) | Q(in_review=True, vehicle_class__isnull=True)
    ).select_related("vehicle_class")
    for row in rows:
        found[(row.vehicle_model_id, row.year)] = row.vehicle_class.name if row.vehicle_class_id else IN_QUEUE
    return found


def customer_counts():
    """({(model id, year): vehicles}, {(model id, year): completed jobs},
    {model id: vehicles with no year}, {model id: their completed jobs})."""
    vehicles, jobs = defaultdict(int), defaultdict(int)
    no_year, no_year_jobs = defaultdict(int), defaultdict(int)
    for model_id, year in Vehicle.objects.filter(vehicle_model__isnull=False).values_list("vehicle_model_id", "year"):
        if year is None:
            no_year[model_id] += 1
        else:
            vehicles[(model_id, year)] += 1
    completed = Appointment.objects.filter(status=Appointment.Status.COMPLETED, vehicle__vehicle_model__isnull=False)
    for model_id, year in completed.values_list("vehicle__vehicle_model_id", "vehicle__year"):
        if year is None:
            no_year_jobs[model_id] += 1
        else:
            jobs[(model_id, year)] += 1
    return vehicles, jobs, no_year, no_year_jobs


def build():
    """Every SizeRange in scope, by make, model and year."""
    scope = in_scope()
    model_ids = sorted({model_id for model_id, _ in scope})
    by_model = defaultdict(list)
    models = {}
    for model_year in catalog_model_years(model_ids):
        key = (model_year.vehicle_model.pk, model_year.year)
        if key not in scope:
            continue
        facts = year_facts(model_year, scope[key])
        if facts.vehicle_class == IN_QUEUE and not any(epa_kind(name) for name in facts.epa):
            continue
        models[key[0]] = model_year.vehicle_model
        by_model[key[0]].append(facts)
    vehicles, jobs, no_year, _ = customer_counts()
    ranges = []
    for model_id, years in by_model.items():
        for found in size_ranges(models[model_id], years):
            found.vehicles = sum(vehicles.get((model_id, facts.year), 0) for facts in found.years)
            found.jobs = sum(jobs.get((model_id, facts.year), 0) for facts in found.years)
            found.vehicles_no_year = no_year.get(model_id, 0)
            ranges.append(found)
    return sorted(ranges, key=lambda found: (found.vehicle_model.make, found.vehicle_model.model, found.vehicle_model.pk, found.first))


def ladder(ranges, newest_from=NEWEST_FROM):
    """One line per model, its newest size range from 2015 (newest_from) on,
    plus any older range a customer owns, sorted by box volume. Ranges with
    no dimensions are left out."""
    by_model = defaultdict(list)
    for found in ranges:
        if found.has_dimensions:
            by_model[found.vehicle_model.pk].append(found)
    chosen = []
    for found in by_model.values():
        recent = [candidate for candidate in found if candidate.last >= newest_from]
        newest = max(recent, key=lambda candidate: candidate.last) if recent else None
        chosen.extend(candidate for candidate in found if candidate is newest or candidate.vehicles)
    return sorted(chosen, key=lambda found: (found.box_volume, found.measure("length"), found.name))


def steps(lines, key, count=5):
    """The count largest steps in key between neighbors once sorted by it."""
    ordered = sorted(lines, key=lambda found: (key(found), found.name))
    pairs = [(key(upper) - key(lower), lower, upper) for lower, upper in zip(ordered, ordered[1:])]
    return sorted(pairs, key=lambda pair: (-pair[0], pair[1].name))[:count]
