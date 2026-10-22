"""NHTSA vPIC's GetModelsForMakeYear: the pickups and vans the EPA leaves
out, and motorcycle models, for the makes in data/vehicle-data-import.yaml.

One call per make, model year and vehicle type. A model the EPA already has
under another spelling ("F-150" for the EPA's "F150") is matched to it; the
rest are added with source NHTSA.
"""

import json
import urllib.parse
from collections import defaultdict

from vehicles.models import VehicleModel

from .facts import Facts
from .fetch import slug

VEHICLE = VehicleModel.VehicleType.VEHICLE
MOTORCYCLE = VehicleModel.VehicleType.MOTORCYCLE
# Shared by every vPIC call, including the Canadian specifications, so the
# pause applies between any two of them.
PACE = "vpic"


def models_url(base, make, year, vehicle_type):
    quote = lambda text: urllib.parse.quote(text, safe="")  # noqa: E731
    return f"{base}GetModelsForMakeYear/make/{quote(make)}/modelyear/{year}/vehicletype/{quote(vehicle_type)}?format=json"


def check_results(body):
    """vPIC answers JSON with a Results list."""
    try:
        data = json.loads(body)
    except ValueError as error:
        raise ValueError("not JSON") from error
    if not isinstance(data, dict) or not isinstance(data.get("Results"), list):
        raise ValueError("no Results list")


def results(body):
    return json.loads(body)["Results"]


def queries(config):
    """(make, vPIC vehicle type, catalog vehicle type) for every query."""
    for make in config.truck_makes:
        for vehicle_type in config.truck_vehicle_types:
            yield make, vehicle_type, VEHICLE
    for make in config.motorcycle_makes:
        yield make, "motorcycle", MOTORCYCLE


def collect(fetcher, config, report, log):
    """{(vehicle type, make, model, year): Facts}."""
    plan = [(*query, year) for query in queries(config) for year in config.years]
    found = {}
    other_makes = defaultdict(set)
    for done, (make, vpic_type, vehicle_type, year) in enumerate(plan, start=1):
        body = fetcher.get(
            models_url(config.vpic_url, make.name, year, vpic_type),
            f"vpic/{slug(make.name)}-{year}-{slug(vpic_type)}.json",
            check=check_results,
            pace=PACE,
        )
        for result in results(body):
            vpic_make = (result.get("Make_Name") or "").strip().upper()
            model = (result.get("Model_Name") or "").strip()
            if vpic_make not in make.vpic_names:
                other_makes[(make.name, vpic_make)].add(year)
                continue
            if not model:
                report.reject(f"vPIC {year} {make.name}: a model with no name (model id {result.get('Model_ID')})")
                continue
            facts = found.setdefault((vehicle_type, make.name, model, year), Facts(id_fields=("make_id", "model_id")))
            facts.add("source_vehicle_types", (result.get("VehicleTypeName") or "").strip())
            if result.get("Make_ID") is not None and result.get("Model_ID") is not None:
                facts.ids.add((result["Make_ID"], result["Model_ID"]))
        if done % 100 == 0:
            log(f"vPIC: {done:,} of {len(plan):,} model lists")
    for (name, vpic_make), years in sorted(other_makes.items()):
        report.reject(
            f"vPIC make {vpic_make}, returned when asking for {name} in {len(years)} model year(s)"
            f" ({min(years)} to {max(years)}): not one of {name}'s vpic_names in data/vehicle-data-import.yaml"
        )
    return found
