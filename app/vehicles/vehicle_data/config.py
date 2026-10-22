"""The import's settings, read from data/: the sources' addresses from
integrations.yaml, the makes, model years and pacing from
vehicle-data-import.yaml, and the names customers know from
vehicle-names.yaml."""

from dataclasses import dataclass, field

import yaml
from django.conf import settings
from django.utils import timezone

from .names import Names, load_names

EPA = "EPA FuelEconomy.gov"
VPIC = "NHTSA vPIC"
CANADA = "NHTSA vPIC Canadian vehicle specifications"


@dataclass(frozen=True)
class QueryMake:
    """A make to ask vPIC for: the catalog's spelling and the vPIC make
    names whose models are accepted."""

    name: str
    vpic_names: frozenset


@dataclass(frozen=True)
class Config:
    epa_url: str
    vpic_url: str
    canada_url: str
    year_from: int
    year_to: int
    pause_seconds: float
    retries: int
    backoff_seconds: float
    truck_vehicle_types: tuple
    truck_makes: tuple
    motorcycle_makes: tuple
    canada_units: str
    names: Names = field(default_factory=Names)

    @property
    def years(self):
        return range(self.year_from, self.year_to + 1)


def query_makes(entries):
    return tuple(
        QueryMake(entry["name"], frozenset(name.upper() for name in entry["vpic_names"])) for entry in entries
    )


def load_config(data_dir=None, today=None):
    data_dir = data_dir or settings.DATA_DIR
    services = yaml.safe_load((data_dir / "integrations.yaml").read_text())["services"]
    urls = {service["name"]: service.get("url") for service in services}
    rules = yaml.safe_load((data_dir / "vehicle-data-import.yaml").read_text())
    vpic = rules["vpic"]
    today = today or timezone.localdate()
    return Config(
        epa_url=urls[EPA],
        vpic_url=urls[VPIC],
        canada_url=urls[CANADA],
        year_from=int(rules["year_from"]),
        # The next model year is on sale from the middle of this one.
        year_to=today.year + 1,
        pause_seconds=float(vpic["pause_seconds"]),
        retries=int(vpic["retries"]),
        backoff_seconds=float(vpic["backoff_seconds"]),
        truck_vehicle_types=tuple(vpic["truck_vehicle_types"]),
        truck_makes=query_makes(vpic["truck_makes"]),
        motorcycle_makes=query_makes(vpic["motorcycle_makes"]),
        canada_units=rules["canada"]["units"],
        names=load_names(data_dir),
    )
