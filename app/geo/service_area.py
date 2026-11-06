"""The service area: the five Tennessee counties in data/service-area.yaml,
plus any address the owner has approved (decision 0037)."""

import re
from dataclasses import dataclass
from decimal import Decimal
from functools import cache

import yaml
from django.conf import settings


@cache
def area():
    """The service area's facts from data/service-area.yaml."""
    return yaml.safe_load((settings.DATA_DIR / "service-area.yaml").read_text())


def county_key(name):
    """ "Bradley County", "BRADLEY" and "bradley" all as "bradley"."""
    name = (name or "").strip().lower()
    return name.removesuffix(" county").strip()


@cache
def counties():
    """The county names as written in the data file, such as "McMinn"."""
    return tuple(county["name"] for county in area()["counties"])


def home_state():
    return area()["state"]


def tennessee_state_rate():
    """The state rate, from the data file, as a Decimal percentage."""
    return Decimal(str(area()["sales_tax"]["tennessee_state_rate_percent"]))


def per_state_rates():
    """{"GA": Decimal("0.0"), ...}: rates for states outside Tennessee."""
    return {
        state: Decimal(str(values["rate_percent"]))
        for state, values in (area()["sales_tax"].get("per_state_rates") or {}).items()
    }


def nice_county(name):
    """A county name as the data file spells it when it is one of the five,
    otherwise title case with "Mc" kept: "MCMINN" as "McMinn"."""
    key = county_key(name)
    for county in counties():
        if county_key(county) == key:
            return county
    return re.sub(r"\bMc(\w)", lambda match: "Mc" + match.group(1).upper(), key.title())


@dataclass(frozen=True)
class AreaCheck:
    in_area: bool
    reason: str


def check(address):
    """Whether the address is in the service area, and why."""
    if address.approved_out_of_area:
        return AreaCheck(True, "Approved out-of-area address")
    if (address.state or "").upper() != home_state():
        return AreaCheck(False, f"Outside Tennessee ({address.state or 'no state'})")
    key = county_key(address.county)
    if not key:
        return AreaCheck(False, "County unknown: verify the address")
    if key in {county_key(county) for county in counties()}:
        return AreaCheck(True, f"{nice_county(address.county)} County")
    return AreaCheck(False, f"{nice_county(address.county)} County is outside the service area")
