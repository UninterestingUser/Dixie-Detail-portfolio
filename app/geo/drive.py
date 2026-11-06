"""Drive times, from Google's Routes API with traffic predicted for the time
of day, cached by the two points and the hour (DriveTime).

When Google can't be asked (no key, the day's cap reached, or no answer),
the drive time is estimated from the straight-line distance, a road factor
and an average speed (LocationSettings), and marked estimated. Estimates are
not cached, so the next request asks Google again.
"""

import datetime
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

from . import google
from .models import DriveTime, LocationSettings

EARTH_RADIUS_MILES = 3958.8
METERS_PER_MILE = 1609.344
FIVE_PLACES = Decimal("0.00001")


@dataclass(frozen=True)
class Drive:
    minutes: int
    meters: int
    estimated: bool
    # "google", "cache" or "estimate".
    source: str


def _key(point):
    return tuple(Decimal(str(value)).quantize(FIVE_PLACES, rounding=ROUND_HALF_UP) for value in point)


def straight_line_miles(origin, destination):
    lat1, lon1, lat2, lon2 = (math.radians(float(value)) for value in (*origin, *destination))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def estimate(origin, destination, settings=None):
    """The fallback: straight-line miles times the road factor, at the
    average speed, rounded up to the minute."""
    settings = settings or LocationSettings.get()
    road_miles = straight_line_miles(origin, destination) * float(settings.estimate_road_factor)
    minutes = math.ceil(road_miles / settings.estimate_speed_mph * 60)
    return Drive(minutes, round(road_miles * METERS_PER_MILE), True, "estimate")


def drive_time(origin, destination, departure):
    """The drive from origin to destination, each (latitude, longitude),
    leaving at departure (an aware datetime)."""
    settings = LocationSettings.get()
    (olat, olon), (dlat, dlon) = _key(origin), _key(destination)
    hour = timezone.localtime(departure).hour
    pair = {
        "origin_latitude": olat, "origin_longitude": olon,
        "destination_latitude": dlat, "destination_longitude": dlon, "hour": hour,
    }
    fresh_after = timezone.now() - datetime.timedelta(days=settings.drive_time_cache_days)
    cached = DriveTime.objects.filter(**pair, fetched_at__gte=fresh_after).first()
    if cached:
        return Drive(math.ceil(cached.seconds / 60), cached.meters, False, "cache")
    try:
        seconds, meters = google.compute_route(origin, destination, departure)
    except google.GoogleUnavailable:
        return estimate(origin, destination, settings)
    DriveTime.objects.update_or_create(**pair, defaults={"seconds": seconds, "meters": meters, "fetched_at": timezone.now()})
    return Drive(math.ceil(seconds / 60), meters, False, "google")


def drive_from_home(address, arrival):
    """The drive from the home base to address, arriving at arrival, or None
    when either has no coordinates. Traffic is predicted for the departure,
    which is the arrival less the straight-line estimate."""
    home = LocationSettings.get().home
    if home is None or address is None or address.point is None:
        return None
    departure = arrival - datetime.timedelta(minutes=estimate(home, address.point).minutes)
    return drive_time(home, address.point, departure)
