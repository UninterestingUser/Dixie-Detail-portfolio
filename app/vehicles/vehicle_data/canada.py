"""vPIC's GetCanadianVehicleSpecifications: curb weight, length, width,
height and wheelbase per trim, by model year and make, attached to the
matching catalog models, with the cab style a pickup's trim name gives
("TACOMA DOUBLE CAB L/BOX 2WD"). It never adds a model.

A Canadian row names the model and trim together, such as "RAV4 AWD LE / XLE
4DR SUV". It matches the catalog model of that make and year whose whole name,
in capitals and digits only, begins it and ends where one of its words ends
("RAV4"; "3 Series" for "3-SERIES 330i"); the longest such name wins. A row
that matches none, matches two equally, or goes on with a series number after
the name ("SILVERADO 2500HD" against "Silverado") is listed for the owner
instead of guessed.
"""

import json
import re
import urllib.parse
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from vehicles.models import VehicleModel, VehicleModelYear

from .catalog import name_key
from .facts import Facts
from .fetch import slug
from .vpic import PACE, check_results

CANADA = VehicleModelYear.Source.CANADA
VEHICLE = VehicleModel.VehicleType.VEHICLE
# The Canadian specifications' codes for the facts kept.
SPECS = {"CW": "curb_weight", "OL": "length", "OW": "width", "OH": "height", "WB": "wheelbase"}
# A series number after a model name, such as 1500, 2500HD, 350, HD or the 6
# of "RS 6": the row may be a different, often heavier, model. Wheelbases
# such as the 159 of "PROMASTER 2500 159 IN. WB" are not series numbers.
SERIES = re.compile(r"^(?:(?:\d|\d{1,2}[05]0)(?:HD)?|HD)$")
TENTH = Decimal("0.1")
# Cab styles as the trim names write them: one word, or a word before CAB.
CAB_WORDS = {"SUPERCAB": "extended", "SUPERCREW": "crew", "CREWCAB": "crew", "CREWMAX": "crew"}
BEFORE_CAB = {
    "REG": "regular", "REGULAR": "regular", "SINGLE": "regular", "STANDARD": "regular",
    "SUPER": "extended", "EXT": "extended", "EXTENDED": "extended", "XTRA": "extended", "EXTRA": "extended",
    "KING": "extended", "ACCESS": "extended", "QUAD": "extended", "DOUBLE": "extended", "CLUB": "extended",
    "CREW": "crew", "MEGA": "crew",
}


def spec_url(base, year, make, units):
    make = urllib.parse.quote(make, safe="")
    return f"{base}GetCanadianVehicleSpecifications/?year={year}&make={make}&model=&units={units}&format=json"


def words(name):
    """A model name as words of capitals and digits: "CR-V EX/L" ->
    ["CRV", "EX", "L"]."""
    return [word for word in (name_key(part) for part in re.split(r"[\s/]+", name)) if word]


def cab_style(trim):
    """regular, extended or crew from a trim name as words(), or None."""
    for index, word in enumerate(trim):
        if word in CAB_WORDS:
            return CAB_WORDS[word]
        if word == "CAB" and index and trim[index - 1] in BEFORE_CAB:
            return BEFORE_CAB[trim[index - 1]]
        if word == "CREW" and index and trim[index - 1] == "SUPER":
            return "crew"
    return None


def measure(name, text):
    """Pounds as a whole number, inches to a tenth; nothing for a blank or zero."""
    try:
        value = Decimal(text)
    except (InvalidOperation, TypeError):
        return None
    if not value.is_finite() or value <= 0:
        return None
    return int(value.quantize(Decimal(1), ROUND_HALF_UP)) if name == "curb_weight" else value.quantize(TENTH, ROUND_HALF_UP)


def catalog_years():
    """{(make key, year): {model id: (name key, name)}} for every car, truck
    and van model year another source lists."""
    found = defaultdict(dict)
    rows = (
        VehicleModelYear.objects.exclude(source=CANADA)
        .filter(vehicle_model__vehicle_type=VEHICLE)
        .values_list("vehicle_model_id", "vehicle_model__make", "vehicle_model__model", "year")
        .distinct()
    )
    for model_id, make, model, year in rows:
        found[(name_key(make), year)][model_id] = (name_key(model), model)
    return found


def collect(fetcher, config, report, log):
    """[(make asked for, year, {spec code: value})] for every make and model
    year in the catalog."""
    # One call per make however the catalog spells it ("MINI" and "Mini").
    spellings = {}
    for make in VehicleModel.objects.filter(vehicle_type=VEHICLE).order_by("pk").values_list("make", flat=True):
        spellings.setdefault(name_key(make), make)
    plan = sorted((spellings[make_key], year) for make_key, year in catalog_years() if year in config.years)
    found = []
    for done, (make, year) in enumerate(plan, start=1):
        body = fetcher.get(
            spec_url(config.canada_url, year, make, config.canada_units),
            f"canada/{slug(make)}-{year}.json",
            check=check_results,
            pace=PACE,
        )
        for result in json.loads(body)["Results"]:
            specs = {spec.get("Name"): (spec.get("Value") or "").strip() for spec in result.get("Specs") or []}
            found.append((make, year, specs))
        if done % 100 == 0:
            log(f"Canadian specifications: {done:,} of {len(plan):,} makes and model years")
    return found


def match(options, trim):
    """(model id, None), or (None, why it is left for the owner). trim is the
    Canadian name as words()."""
    # Each run of whole words from the start, joined: "3", "3SERIES", ...
    starts = {"".join(trim[:count]): count for count in range(1, len(trim) + 1)}
    hits = [(len(key), model_id, name) for model_id, (key, name) in options.items() if key and key in starts]
    if not hits:
        return None, "no catalog model of this make and year begins this name"
    longest = max(length for length, _, _ in hits)
    best = sorted((name, model_id) for length, model_id, name in hits if length == longest)
    if len(best) > 1:
        return None, f"matches {' and '.join(name for name, _ in best)} equally"
    name, model_id = best[0]
    used = starts[name_key(name)]
    following = trim[used] if len(trim) > used else ""
    if SERIES.match(following):
        return None, f"begins with {name} but goes on with {following}, which may be a heavier series"
    return model_id, None


def facts_by_model_year(rows, report, make_names=None):
    """make_names maps a Canadian make name to the catalog's, such as RAM
    TRUCKS to Ram (data/vehicle-data-import.yaml)."""
    make_names = {name_key(canadian): name_key(make) for canadian, make in (make_names or {}).items()}
    options = catalog_years()
    grouped = {}
    for make, year, specs in rows:
        trim, row_make = specs.get("Model", ""), specs.get("Make") or make
        label = f"{year} {row_make} {trim}".strip()
        if not trim:
            report.reject(f"Canadian specifications {year} {make}: a row with no model name")
            continue
        if make_names.get(name_key(row_make), name_key(row_make)) != name_key(make):
            report.reject(f"{label}: returned when asking for {make}")
            continue
        values = {name: measure(name, specs.get(code)) for code, name in SPECS.items()}
        if all(value is None for value in values.values()):
            report.reject(f"{label}: no weight or dimensions")
            continue
        trim_words = words(trim)
        model_id, why = match(options.get((name_key(make), year), {}), trim_words)
        if model_id is None:
            report.unmatched.append(f"{label}: {why}")
            continue
        facts = grouped.setdefault((model_id, year), Facts())
        for name, value in values.items():
            facts.measure(name, value)
        facts.add("cab_styles", cab_style(trim_words))
        facts.ids.add(trim)
    return grouped
