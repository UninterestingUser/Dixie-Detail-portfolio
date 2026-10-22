"""The EPA's FuelEconomy.gov table: vehicles.csv inside vehicles.csv.zip.

The table has one row per engine and transmission of a model year. The
catalog's model is the EPA's base model ("RAV4" for "RAV4 AWD" and "RAV4
Hybrid AWD"), the name a customer knows, and each model year keeps the facts
of all its rows: every size class and drive, the body styles, and the range
of passenger and luggage volume.
"""

import csv
import io
import zipfile

from vehicles.models import VehicleModel

from .facts import Facts

VEHICLE = VehicleModel.VehicleType.VEHICLE
CACHE_NAME = "epa/vehicles.csv.zip"
# The EPA has no door field. A body style is listed when its passenger or
# luggage volume is not zero; all are zero for pickups, vans and most SUVs.
BODY_STYLE_VOLUMES = (("two-door", "pv2", "lv2"), ("four-door", "pv4", "lv4"), ("hatchback", "hpv", "hlv"))


def check_zip(body):
    try:
        names = zipfile.ZipFile(io.BytesIO(body)).namelist()
    except zipfile.BadZipFile as error:
        raise ValueError("not a zip file") from error
    if not any(name.lower().endswith(".csv") for name in names):
        raise ValueError("no CSV file in the zip file")


def rows(body):
    archive = zipfile.ZipFile(io.BytesIO(body))
    name = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
    return csv.DictReader(io.StringIO(archive.read(name).decode("utf-8-sig", errors="replace")))


def volume(text):
    try:
        return int(float(text or 0))
    except ValueError:
        return 0


def read(body, years, report):
    """{(vehicle type, make, model, year): Facts} for every model year in years."""
    found = {}
    for line, row in enumerate(rows(body), start=2):
        where = f"EPA line {line} (id {row.get('id') or '?'})"
        make = (row.get("make") or "").strip()
        model = (row.get("baseModel") or "").strip() or (row.get("model") or "").strip()
        try:
            year = int(row.get("year") or "")
        except ValueError:
            report.reject(f"{where}: no model year")
            continue
        if not make or not model:
            report.reject(f"{where}: no make or model")
            continue
        if year not in years:
            report.counts["EPA rows outside the model years, skipped"] += 1
            continue
        facts = found.setdefault((VEHICLE, make, model, year), Facts())
        facts.add("epa_size_classes", (row.get("VClass") or "").strip())
        facts.add("drives", (row.get("drive") or "").strip())
        for style, passenger, luggage in BODY_STYLE_VOLUMES:
            passenger, luggage = volume(row.get(passenger)), volume(row.get(luggage))
            if passenger or luggage:
                facts.add("body_styles", style)
            facts.measure("passenger_volume", passenger or None)
            facts.measure("luggage_volume", luggage or None)
        if (row.get("id") or "").strip().isdigit():
            facts.ids.add(int(row["id"]))
    for facts in found.values():
        if not facts.listed["body_styles"]:
            facts.add("body_styles", "unknown")
    return found


def collect(fetcher, config, report, log):
    body = fetcher.get(config.epa_url, CACHE_NAME, check=check_zip)
    return read(body, config.years, report)
