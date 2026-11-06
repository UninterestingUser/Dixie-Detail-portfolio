"""Sales tax for a service address (sales-tax.md, decisions 0025 and 0037).

1. A Tennessee address's coordinates are matched against the Department of
   Revenue's rate boundaries (TaxBoundary) to find its city or county.
2. One that will not match, or has no coordinates, takes its county's rate
   and is flagged for the owner to check.
3. An address outside Tennessee, such as the approved one in Georgia, takes
   its state's per-state rate (Georgia 0% for now).
4. The tax is worked out at the approved rate in effect on the day of
   service: state and local tax each rounded to the cent, an exact half cent
   up. The taxable amount is the price before tax: promotions have already
   reduced it, and tips are never part of it.

The sourcing rule is one setting (LocationSettings.tax_sourcing): with the
business-location rule, every job takes the home base's rate instead.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q
from django.utils import timezone

from geo import service_area
from geo.models import LocationSettings

from .models import TaxBoundary, TaxJurisdiction, TaxRate

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def to_cents(amount):
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


# Point in polygon. GeoJSON rings are [longitude, latitude] pairs; the first
# ring of each polygon is its outline and the rest are holes.


def _in_ring(ring, x, y):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def geometry_contains(geometry, latitude, longitude):
    x, y = float(longitude), float(latitude)
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    for polygon in polygons:
        if _in_ring(polygon[0], x, y) and not any(_in_ring(hole, x, y) for hole in polygon[1:]):
            return True
    return False


def match_point(latitude, longitude):
    """The Tennessee jurisdiction whose boundary holds the point, or None."""
    candidates = TaxBoundary.objects.filter(
        min_latitude__lte=latitude, max_latitude__gte=latitude,
        min_longitude__lte=longitude, max_longitude__gte=longitude,
    ).select_related("jurisdiction")
    for boundary in candidates:
        if geometry_contains(boundary.geometry, latitude, longitude):
            return boundary.jurisdiction
    return None


@dataclass(frozen=True)
class JurisdictionMatch:
    jurisdiction: TaxJurisdiction | None
    needs_check: bool
    note: str = ""
    # The county the boundary is in, when it matched.
    county: str = ""


def county_jurisdiction(state, county):
    if not county:
        return None
    return TaxJurisdiction.objects.filter(
        state=state, kind=TaxJurisdiction.Kind.COUNTY, county__iexact=service_area.nice_county(county)
    ).first()


def match_place(state, county, point):
    """Which jurisdiction's rate applies at a place."""
    state = (state or "").upper()
    if state != service_area.home_state():
        jurisdiction = TaxJurisdiction.objects.filter(state=state, kind=TaxJurisdiction.Kind.STATE).first()
        if jurisdiction is None:
            return JurisdictionMatch(None, True, f"No sales tax rate is on file for {state or 'this state'}.")
        return JurisdictionMatch(jurisdiction, False)
    if point is not None:
        jurisdiction = match_point(*point)
        if jurisdiction is not None:
            return JurisdictionMatch(jurisdiction, False, county=jurisdiction.county)
    fallback = county_jurisdiction(state, county)
    reason = "did not match a tax rate boundary" if point is not None else "has no map coordinates"
    if fallback is None:
        return JurisdictionMatch(None, True, f"The address {reason}, and no county rate is on file for it.")
    return JurisdictionMatch(fallback, True, f"The address {reason}; it takes {fallback.county} County's rate.")


def match_address(address):
    return match_place(address.state, address.county, address.point)


def assign_jurisdiction(address):
    """Store the address's jurisdiction and flag on it (not saved), and set
    its county from the matched boundary."""
    found = match_address(address)
    address.tax_jurisdiction = found.jurisdiction
    address.tax_needs_check = found.needs_check
    address.tax_note = found.note
    if found.county:
        address.county = found.county
    return found


def rate_on(jurisdiction, day):
    """The approved rate in effect on day. Before the first rate took
    effect, the earliest approved rate."""
    approved = TaxRate.objects.filter(jurisdiction=jurisdiction, approved_at__isnull=False)
    rate = (
        approved.filter(effective_from__lte=day)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=day))
        .order_by("-effective_from")
        .first()
    )
    return rate or approved.order_by("effective_from").first()


@dataclass(frozen=True)
class TaxLine:
    """The tax line of a quote or invoice."""

    taxable_amount: Decimal
    jurisdiction: TaxJurisdiction | None
    state_rate: Decimal
    local_rate: Decimal
    state_tax: Decimal
    local_tax: Decimal
    needs_check: bool
    note: str = ""

    @property
    def rate(self):
        return self.state_rate + self.local_rate

    @property
    def sales_tax(self):
        return self.state_tax + self.local_tax


def tax_line(address, taxable_amount, day):
    """The sales tax on taxable_amount for a job at address on day."""
    place = LocationSettings.get()
    if place.tax_sourcing == LocationSettings.TaxSourcing.BUSINESS_LOCATION:
        found = match_place(place.home_state, "", place.home)
    else:
        found = match_address(address)
    taxable = to_cents(max(taxable_amount, ZERO))
    rate = rate_on(found.jurisdiction, day) if found.jurisdiction else None
    if rate is None:
        note = found.note or f"No approved sales tax rate is on file for {found.jurisdiction}."
        return TaxLine(taxable, found.jurisdiction, ZERO, ZERO, ZERO, ZERO, True, note)
    return TaxLine(
        taxable_amount=taxable,
        jurisdiction=found.jurisdiction,
        state_rate=rate.state_rate,
        local_rate=rate.local_rate,
        state_tax=to_cents(taxable * rate.state_rate / 100),
        local_tax=to_cents(taxable * rate.local_rate / 100),
        needs_check=found.needs_check,
        note=found.note,
    )


def taxable_amount_of(appointment):
    """A job's taxable amount: the sum of its lines, promotions taking their
    discount off. Tips are recorded on payments, never as lines, so they are
    never taxed."""
    return sum((line.amount for line in appointment.lines.all()), ZERO)


def tax_line_for_appointment(appointment):
    """The tax line for an appointment's invoice, at the rate in effect on its
    day of service, or None when it has no service address."""
    if appointment.service_address is None:
        return None
    day = timezone.localtime(appointment.scheduled_start).date()
    return tax_line(appointment.service_address, taxable_amount_of(appointment), day)
