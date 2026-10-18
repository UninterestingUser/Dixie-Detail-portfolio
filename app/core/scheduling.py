"""Time on site, and the scheduling launch values it reads.

Time on site = setup + service time + breakdown, rounded to the nearest 15
minutes (decision 0056). Setup and breakdown are minutes for one person,
divided by the number of people on the job. Until Phase 3 adds the settings screen, the values come from
data/booking-rules.yaml.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from functools import cache

import yaml
from django.conf import settings


@dataclass(frozen=True)
class SchedulingValues:
    setup_minutes_one_person: int
    breakdown_minutes_one_person: int
    time_on_site_rounding_minutes: int


@cache
def launch_values():
    """The setup, breakdown and rounding launch values from data/booking-rules.yaml."""
    rules = yaml.safe_load((settings.DATA_DIR / "booking-rules.yaml").read_text())
    return SchedulingValues(
        setup_minutes_one_person=int(rules["setup_minutes_one_person"]),
        breakdown_minutes_one_person=int(rules["breakdown_minutes_one_person"]),
        time_on_site_rounding_minutes=int(rules["time_on_site_rounding_minutes"]),
    )


def round_to_nearest(minutes, step):
    """Round minutes to the nearest step, an exact half step up."""
    steps = (Decimal(minutes) / step).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(steps) * step


@dataclass(frozen=True)
class TimeOnSite:
    setup_minutes: int
    service_minutes: int
    breakdown_minutes: int
    # The sum, rounded to the nearest rounding step.
    total_minutes: int

    @property
    def hours(self):
        return Decimal(self.total_minutes) / 60


def time_on_site(service_minutes, crew_size, values=None):
    """Setup and breakdown, divided by the number of people, around the crew's
    service time: 30 + 30 minutes for one person, 15 + 15 for two at launch.
    The total is rounded to the nearest 15 minutes (the rounding launch value)."""
    if crew_size not in (1, 2):
        raise ValueError("A crew is one or two people.")
    values = values or launch_values()
    setup = round_to_nearest(Decimal(values.setup_minutes_one_person) / crew_size, 1)
    breakdown = round_to_nearest(Decimal(values.breakdown_minutes_one_person) / crew_size, 1)
    total = round_to_nearest(setup + service_minutes + breakdown, values.time_on_site_rounding_minutes)
    return TimeOnSite(setup, service_minutes, breakdown, total)


def format_minutes(minutes):
    """90 as "1.5 hours", 30 as "30 minutes"."""
    if minutes < 60:
        return f"{minutes} minutes"
    hours = Decimal(minutes) / 60
    text = f"{hours.quantize(Decimal('0.01')):f}".rstrip("0").rstrip(".")
    return f"{text} hour" if text == "1" else f"{text} hours"
