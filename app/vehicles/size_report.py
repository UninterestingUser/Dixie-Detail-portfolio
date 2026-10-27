"""The vehicle size report: the measured size of every model in the car,
crossover and SUV classes, gathered for the owner's decision on how to
split them (docs/operations/classifying-vehicles.md#vehicle-size-report).

It reads only facts already in the database and changes nothing. In scope
are the catalog model years now in Coupes & Sedans, Crossovers & Wagons and
Midsize SUVs, Fullsize SUVs & Minivans for comparison, and the model years
waiting in the review queue with no class whose EPA size class is a car,
station-wagon or SUV class ("in queue").

A model's consecutive model years make one size range while they keep the
same class and seat rows and their length, width and height each stay
within 1 inch. Where trims differ, each model year's figure is the median of
its trims, read as classification reads a measured fact (the owner's own
figures first); a range's figure is the median of its years'. Box volume,
length x width x height / 1,728, is a rough measure of bulk in cubic feet.
Customers appear only as counts.
"""

import csv
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
NO_CLASS = "no class"
CAR_CLASSES = ("Two Seaters", "Minicompact Cars", "Subcompact Cars", "Compact Cars", "Midsize Cars", "Large Cars")
DIMENSIONS = ("length", "width", "height")
MEASURES = ("length", "width", "height", "wheelbase", "curb_weight")
# How far a range's length, width and height may each spread, in inches.
SPREAD = Decimal(1)
CUBIC_INCHES = Decimal(1728)
NEWEST_FROM = 2015
DOORS = {"two-door": "2", "four-door": "4", "hatchback": "hatchback"}
DRIVE = re.compile(r"\s*(?:-\s*|/)?[24]wd$", re.IGNORECASE)

COLUMNS = (
    "make", "model", "years", "first year", "last year", "current class", "seat rows", "doors", "EPA size class",
    "length (in)", "width (in)", "height (in)", "wheelbase (in)", "curb weight (lb)", "box volume (cu ft)",
    "trims with specs", "shortest trim length (in)", "longest trim length (in)", "customer vehicles",
    "completed jobs", "customer vehicles with no year (whole model)", "missing dimensions",
)


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
    """One model year's facts as the report uses them."""

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
    rows whose length, width and height each stay within 1 inch: one row of
    the report."""

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
    def epa_classes(self):
        return "; ".join(sorted(self.epa_counts))

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

    @property
    def is_car(self):
        return self.vehicle_class == COUPES or any(epa_kind(name) == "car" for name in self.epa_counts)

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

    def csv_row(self):
        blank = lambda value: "" if value is None else value  # noqa: E731
        return [
            self.vehicle_model.make, self.vehicle_model.model, self.years_label, self.first, self.last,
            self.vehicle_class, self.seat_rows, self.doors if self.is_car else "", self.epa_classes,
            *(blank(self.measure(name)) for name in MEASURES), blank(self.box_volume),
            self.trims or "", blank(self.shortest), blank(self.longest),
            self.vehicles, self.jobs, self.vehicles_no_year, "" if self.has_dimensions else "missing",
        ]


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


def write_csv(ranges, out):
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for found in ranges:
        writer.writerow(found.csv_row())


# The summary.


def ladder(ranges, newest_from=NEWEST_FROM):
    """One line per model, its newest size range from 2015 (newest_from) on,
    plus any older range a customer owns, sorted by box volume. Ranges with
    no dimensions are left to the data gaps."""
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


def customers_note(found):
    count = found.vehicles
    return f"  * {count} customer vehicle{'s' if count != 1 else ''}" if count else ""


def ladder_line(found, epa=False):
    rows = "" if found.seat_rows in ("2", "3") else f", rows {found.seat_rows or '?'}"
    detail = f"{found.epa_main or 'no EPA class'}, {found.vehicle_class}" if epa else found.vehicle_class
    return f"  {found.box_volume:>6} cu ft  {found.measure('length'):>6} in  {found.name}  ({detail}{rows}){customers_note(found)}"


def steps(lines, key, count=5):
    """The count largest steps in key between neighbors once sorted by it."""
    ordered = sorted(lines, key=lambda found: (key(found), found.name))
    pairs = [(key(upper) - key(lower), lower, upper) for lower, upper in zip(ordered, ordered[1:])]
    return sorted(pairs, key=lambda pair: (-pair[0], pair[1].name))[:count]


def suv_ladders(ranges):
    """(2-row, 3-row, Fullsize SUVs & Minivans) ladders. An optional third
    row goes on the 3-row ladder; unknown seat rows on the 2-row."""
    crossovers = [
        found for found in ranges
        if (found.vehicle_class in (CROSSOVERS, MIDSIZE) and found.kind != "wagon")
        or (found.vehicle_class == IN_QUEUE and found.kind == "suv")
    ]
    two = ladder([found for found in crossovers if found.seat_rows in ("2", "")])
    three = ladder([found for found in crossovers if found.seat_rows in ("3", "optional")])
    fullsize = ladder([found for found in ranges if found.vehicle_class == FULLSIZE])
    return two, three, fullsize


def summary(ranges, out):
    write = lambda line="": out.write(line + "\n")  # noqa: E731
    two, three, fullsize = suv_ladders(ranges)
    write("VEHICLE SIZE REPORT (read only; nothing was changed)")
    write("Box volume is length x width x height / 1,728, a rough measure of bulk. Each figure is the median")
    write("of the trims, then of the model years in the range. * marks lines with customer vehicles.")
    write("A line is a model's newest size range from 2015 on, plus any older range a customer owns.")

    write()
    write("CROSSOVERS AND SUVS")
    for title, lines in (("2-row", two), ("3-row (optional third row included)", three), (f"{FULLSIZE}, for comparison", fullsize)):
        write()
        write(f"{title}: {len(lines)} lines")
        for found in lines:
            write(ladder_line(found))

    write()
    write("CANDIDATE LINES ON THE 2-ROW LADDER")
    for title, key, unit in (
        ("Largest steps in box volume", lambda found: found.box_volume, "cu ft"),
        ("Largest steps in length", lambda found: found.measure("length"), "in"),
    ):
        write()
        write(f"{title}:")
        for step, lower, upper in steps(two, key):
            write(f"  +{step} {unit}: {lower.name} ({key(lower)} {unit}, {lower.vehicle_class})"
                  f" | {upper.name} ({key(upper)} {unit}, {upper.vehicle_class})")

    write()
    write("CARS AND WAGONS")
    cars = [found for found in ranges if found.vehicle_class == COUPES or (found.vehicle_class == IN_QUEUE and found.kind == "car")]
    wagons = [found for found in ranges if found.vehicle_class in (CROSSOVERS, IN_QUEUE) and found.kind == "wagon"]
    for title, lines in ((COUPES, ladder(cars)), (f"Wagons in {CROSSOVERS} (EPA station-wagon classes)", ladder(wagons))):
        write()
        write(f"{title}: {len(lines)} lines")
        for found in lines:
            write(ladder_line(found, epa=True))
    write()
    write(f"EPA car classes in {COUPES} (every size range, by its main EPA size class):")
    by_epa = defaultdict(lambda: [set(), 0])
    for found in ranges:
        if found.vehicle_class == COUPES:
            by_epa[found.epa_main or "no EPA class"][0].add(found.vehicle_model.pk)
            by_epa[found.epa_main or "no EPA class"][1] += found.vehicles
    order = {name: index for index, name in enumerate(CAR_CLASSES)}
    for name in sorted(by_epa, key=lambda name: (order.get(name, len(order)), name)):
        model_ids, count = by_epa[name]
        write(f"  {name}: {len(model_ids)} models, {count} customer vehicles")

    write()
    write("CUSTOMER VEHICLES BY THEIR RECORDED CLASS")
    write("  class: linked with a year / linked with no year / unlinked")
    for name, (dated, undated, unlinked) in customer_totals():
        write(f"  {name}: {dated} / {undated} / {unlinked}")

    write()
    write("DATA GAPS")
    for line in data_gaps(ranges):
        write(line)


def customer_totals():
    """[(class name, (linked with a year, linked with no year, unlinked))]
    for every customer vehicle, by the class the vehicle record holds."""
    counts = defaultdict(lambda: [0, 0, 0])
    sort = {}
    for vehicle in Vehicle.objects.select_related("vehicle_class").only("vehicle_model_id", "year", "vehicle_class"):
        name = vehicle.vehicle_class.name if vehicle.vehicle_class_id else NO_CLASS
        sort[name] = (vehicle.vehicle_class.sort_order, name) if vehicle.vehicle_class_id else (10**6, name)
        column = 2 if vehicle.vehicle_model_id is None else (0 if vehicle.year is not None else 1)
        counts[name][column] += 1
    return [(name, tuple(counts[name])) for name in sorted(counts, key=lambda name: sort[name])]


def data_gaps(ranges):
    """Lines on the in-scope models with no dimensions in any year, and the
    years missing them in models that have some."""
    by_model = defaultdict(list)
    for found in ranges:
        by_model[found.vehicle_model.pk].append(found)
    none, others = [], defaultdict(int)
    partial_years = partial_vehicles = 0
    for found in by_model.values():
        missing = [candidate for candidate in found if not candidate.has_dimensions]
        if not missing:
            continue
        if len(missing) < len(found):
            partial_years += sum(len(candidate.years) for candidate in missing)
            partial_vehicles += sum(candidate.vehicles for candidate in missing)
            continue
        vehicles = sum(candidate.vehicles for candidate in found) + found[0].vehicles_no_year
        if vehicles:
            none.append((found, vehicles))
        else:
            others[found[-1].vehicle_class] += 1
    lines = [
        f"Models with no dimensions in any year in scope, holding customer vehicles (with or without a year): {len(none)}"
    ]
    for found, vehicles in sorted(none, key=lambda pair: (-pair[1], pair[0][0].name)):
        spans = ", ".join(f"{candidate.years_label} ({candidate.vehicle_class})" for candidate in found)
        lines.append(f"  {found[0].vehicle_model.make} {found[0].vehicle_model.model} {spans}: {vehicles} customer vehicles")
    total = sum(others.values())
    lines.append(f"Models with no dimensions and no customer vehicles, by the class of their newest range: {total}")
    for name in sorted(others):
        lines.append(f"  {name}: {others[name]}")
    lines.append(
        f"Model years with no dimensions in models that have them in other years: {partial_years},"
        f" holding {partial_vehicles} customer vehicles"
    )
    return lines
