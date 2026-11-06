"""Loading Tennessee's sales tax rates and rate boundaries, and checking them.

The Department of Revenue publishes its rate boundaries as a map service,
updated quarterly: one area per city and one per county's unincorporated
part, each with the state's situs code and its local rate. The state rate
(7%) is in data/service-area.yaml.

- import_tax_rates loads, for the five counties, every area's rate and
  boundary, and for every other Tennessee county its county rate (no
  boundary), so an approved out-of-area Tennessee address can take its
  county's rate. A jurisdiction's first rate is approved as it is loaded; a
  rate that differs from the approved one is stored waiting for the owner's
  approval. Boundaries are replaced when they changed.
- import_tax_rates --check, run every morning by dixie-tax-rate-check.timer,
  only compares the rates and stores any change for approval. It never
  changes a boundary or adds a jurisdiction; it reports them so the owner
  runs the import.
- The per-state rates for states outside Tennessee (Georgia 0%) are seeded
  from the data file when missing; after that the owner keeps them in the
  control app.
"""

import datetime
import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from geo import http, service_area

from .models import TaxBoundary, TaxJurisdiction, TaxRate
from .tax import rate_on

SERVICE_URL = "https://tnmap.tn.gov/arcgis/rest/services/COMMUNITY/REVENUE_TAX_RATE_BOUNDARIES/MapServer/0/query"
FIELDS = "SITUS,COUNTY,COUNTYFIPS,CITY,TAXRATE"
UNINCORPORATED = "(UNINCORPORATED)"


class TaxDataError(Exception):
    """The state's data could not be fetched or read."""


@dataclass
class Row:
    """One area from the state's data."""

    code: str
    county: str
    city: str  # "" for a county's unincorporated area
    local_rate: Decimal
    geometry: dict | None = None

    @property
    def kind(self):
        return TaxJurisdiction.Kind.CITY if self.city else TaxJurisdiction.Kind.COUNTY

    @property
    def name(self):
        return self.city if self.city else f"{self.county} County"


def nice_name(text):
    return service_area.nice_county(text)


def parse_feature(feature):
    props = feature.get("properties") or feature.get("attributes") or {}
    try:
        code = (props["SITUS"] or "").strip()
        county = nice_name(props["COUNTY"])
        city = (props.get("CITY") or "").strip()
        local_rate = Decimal(str(props["TAXRATE"]).strip())
    except (KeyError, InvalidOperation, AttributeError) as error:
        raise TaxDataError(f"An area in the state's data could not be read: {props}") from error
    if not code or not county:
        raise TaxDataError(f"An area in the state's data has no situs code or county: {props}")
    city = "" if city.upper() == UNINCORPORATED or not city else nice_name(city)
    return Row(code, county, city, local_rate, feature.get("geometry"))


def query(where, geometry):
    """Every feature matching where, page by page."""
    features, offset = [], 0
    while True:
        params = {
            "where": where, "outFields": FIELDS, "returnGeometry": "true" if geometry else "false",
            "outSR": "4326", "f": "geojson", "resultOffset": offset, "orderByFields": "SITUS",
        }
        try:
            answer = http.request_json(SERVICE_URL, params=params, timeout=120)
        except http.FetchError as error:
            raise TaxDataError(f"The state's rate boundaries could not be fetched: {error}") from error
        if "error" in answer or "features" not in answer:
            raise TaxDataError(f"The state's map service answered with an error: {answer.get('error')}")
        page = answer["features"]
        features.extend(page)
        more = answer.get("exceededTransferLimit") or (answer.get("properties") or {}).get("exceededTransferLimit")
        if not more or not page:
            return features
        offset += len(page)


def fetch_rows(geometry=True):
    """The five counties' areas (with boundaries when geometry) and every
    Tennessee county's unincorporated rate."""
    names = ", ".join(f"'{county.upper()}'" for county in service_area.counties())
    rows = {}
    for feature in query("CITY = '(Unincorporated)'", geometry=False):
        row = parse_feature(feature)
        rows[row.code] = row
    for feature in query(f"COUNTY IN ({names})", geometry=geometry):
        row = parse_feature(feature)
        rows[row.code] = row
    return list(rows.values())


def geometry_hash(geometry):
    return hashlib.sha256(json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def bounding_box(geometry):
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    points = [point for polygon in polygons for ring in polygon for point in ring]
    longitudes, latitudes = [p[0] for p in points], [p[1] for p in points]
    six = Decimal("0.000001")
    return {
        "min_latitude": Decimal(str(min(latitudes))).quantize(six),
        "max_latitude": Decimal(str(max(latitudes))).quantize(six),
        "min_longitude": Decimal(str(min(longitudes))).quantize(six),
        "max_longitude": Decimal(str(max(longitudes))).quantize(six),
    }


@dataclass
class Report:
    lines: list = field(default_factory=list)
    unchanged: int = 0
    new_jurisdictions: int = 0
    rate_changes: int = 0
    boundaries_changed: int = 0
    waiting: int = 0

    def add(self, text):
        self.lines.append(text)


def _percent(value):
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _rate_text(state_rate, local_rate):
    return f"{_percent(state_rate)}% + {_percent(local_rate)}% = {_percent(state_rate + local_rate)}%"


def _flag_change(jurisdiction, current, state_rate, local_rate, today, write, report):
    pending = TaxRate.objects.filter(jurisdiction=jurisdiction, approved_at__isnull=True, rejected_at__isnull=True)
    same = {"state_rate": state_rate, "local_rate": local_rate}
    if pending.filter(**same).exists():
        report.add(f"  {jurisdiction}: change to {_rate_text(state_rate, local_rate)} is already waiting for approval")
        return
    if TaxRate.objects.filter(jurisdiction=jurisdiction, rejected_at__isnull=False, effective_from__gt=current.effective_from, **same).exists():
        report.add(f"  {jurisdiction}: the state still shows {_rate_text(state_rate, local_rate)}, which the owner rejected")
        return
    report.rate_changes += 1
    report.add(
        f"  {jurisdiction}: rate changed from {_rate_text(current.state_rate, current.local_rate)}"
        f" to {_rate_text(state_rate, local_rate)}; waiting for the owner's approval"
    )
    if write:
        pending.delete()
        latest = TaxRate.objects.filter(jurisdiction=jurisdiction).aggregate(latest=Max("effective_from"))["latest"]
        start = max(today, latest + datetime.timedelta(days=1))
        TaxRate.objects.create(jurisdiction=jurisdiction, effective_from=start, **same)


@transaction.atomic
def apply(rows, *, mode, today=None):
    """Compare the state's rows with the stored rates and boundaries.
    mode is "dry_run" (change nothing), "check" (store rate changes for
    approval only) or "import" (also add jurisdictions, approve first rates
    and replace boundaries)."""
    today = today or timezone.localdate()
    importing = mode == "import"
    flagging = mode in ("import", "check")
    state_rate = service_area.tennessee_state_rate()
    report = Report()
    now = timezone.now()

    for row in sorted(rows, key=lambda row: row.code):
        jurisdiction = TaxJurisdiction.objects.filter(code=row.code).first()
        if jurisdiction is None:
            report.new_jurisdictions += 1
            report.add(f"  new: {row.name} ({row.county} County, code {row.code}) at {_rate_text(state_rate, row.local_rate)}")
            if importing:
                jurisdiction = TaxJurisdiction.objects.create(
                    state="TN", code=row.code, name=row.name, kind=row.kind, county=row.county
                )
                TaxRate.objects.create(
                    jurisdiction=jurisdiction, state_rate=state_rate, local_rate=row.local_rate,
                    effective_from=today, approved_at=now,
                )
        else:
            if importing and (jurisdiction.name, jurisdiction.county) != (row.name, row.county):
                jurisdiction.name, jurisdiction.county = row.name, row.county
                jurisdiction.save(update_fields=["name", "county"])
            current = rate_on(jurisdiction, today)
            if current is None:
                report.add(f"  {jurisdiction}: no approved rate; {_rate_text(state_rate, row.local_rate)} from the state")
                if importing:
                    TaxRate.objects.create(
                        jurisdiction=jurisdiction, state_rate=state_rate, local_rate=row.local_rate,
                        effective_from=today, approved_at=now,
                    )
            elif (current.state_rate, current.local_rate) == (state_rate, row.local_rate):
                report.unchanged += 1
            else:
                _flag_change(jurisdiction, current, state_rate, row.local_rate, today, flagging, report)

        if row.geometry is not None:
            digest = geometry_hash(row.geometry)
            boundary = TaxBoundary.objects.filter(jurisdiction__code=row.code).first()
            if boundary is None or boundary.geometry_hash != digest:
                report.boundaries_changed += 1
                report.add(f"  boundary {'added' if boundary is None else 'changed'}: {row.name} ({row.county} County)")
                if importing:
                    TaxBoundary.objects.update_or_create(
                        jurisdiction=jurisdiction,
                        defaults={"geometry": row.geometry, "geometry_hash": digest, "imported_at": now, **bounding_box(row.geometry)},
                    )

    if any(row.geometry is not None for row in rows):
        codes = {row.code for row in rows if row.geometry is not None}
        for boundary in TaxBoundary.objects.exclude(jurisdiction__code__in=codes).select_related("jurisdiction"):
            report.boundaries_changed += 1
            report.add(f"  boundary removed: {boundary.jurisdiction} is no longer in the state's data")
            if importing:
                boundary.delete()

    for state, rate in service_area.per_state_rates().items():
        if TaxJurisdiction.objects.filter(code=state).exists():
            continue
        name = service_area.area()["sales_tax"]["per_state_rates"][state].get("name", state)
        report.new_jurisdictions += 1
        report.add(f"  new: {name} at {_percent(rate)}% (per-state rate from data/service-area.yaml)")
        if importing:
            jurisdiction = TaxJurisdiction.objects.create(state=state, code=state, name=name, kind=TaxJurisdiction.Kind.STATE)
            TaxRate.objects.create(jurisdiction=jurisdiction, state_rate=rate, local_rate=0, effective_from=today, approved_at=now)

    report.waiting = TaxRate.objects.filter(approved_at__isnull=True, rejected_at__isnull=True).count()
    if mode == "dry_run":
        transaction.set_rollback(True)
    return report


class RateError(ValueError):
    """The rate cannot be approved or set as asked."""


def _close_previous(jurisdiction, effective_from, exclude_pk):
    """End the approved rate that runs into effective_from the day before."""
    previous = (
        TaxRate.objects.filter(jurisdiction=jurisdiction, approved_at__isnull=False, effective_from__lt=effective_from)
        .exclude(pk=exclude_pk)
        .order_by("-effective_from")
        .first()
    )
    if previous and (previous.effective_to is None or previous.effective_to >= effective_from):
        previous.effective_to = effective_from - datetime.timedelta(days=1)
        previous._change_reason = "Ended by a newer approved rate"
        previous.save(update_fields=["effective_to"])


def _check_start(jurisdiction, effective_from, exclude_pk=None):
    clash = TaxRate.objects.filter(jurisdiction=jurisdiction, effective_from=effective_from).exclude(pk=exclude_pk)
    if clash.exists():
        raise RateError(f"{jurisdiction} already has a rate starting {effective_from:%B %-d, %Y}; pick another date.")
    later = TaxRate.objects.filter(jurisdiction=jurisdiction, approved_at__isnull=False, effective_from__gt=effective_from)
    if later.exclude(pk=exclude_pk).exists():
        raise RateError(f"{jurisdiction} has an approved rate starting after {effective_from:%B %-d, %Y}.")


@transaction.atomic
def approve_rate(rate, effective_from, user=None):
    """The owner approves a waiting rate from effective_from; the rate before
    it ends the day before. Returns the rate."""
    if not rate.is_pending:
        raise RateError("That rate is not waiting for approval.")
    _check_start(rate.jurisdiction, effective_from, exclude_pk=rate.pk)
    rate.effective_from = effective_from
    rate.approved_at = timezone.now()
    rate.approved_by = user
    rate._change_reason = "Approved by the owner"
    rate.save()
    _close_previous(rate.jurisdiction, effective_from, rate.pk)
    return rate


@transaction.atomic
def reject_rate(rate, user=None):
    if not rate.is_pending:
        raise RateError("That rate is not waiting for approval.")
    rate.rejected_at = timezone.now()
    rate._change_reason = "Rejected by the owner"
    rate.save(update_fields=["rejected_at"])
    return rate


@transaction.atomic
def set_state_rate(jurisdiction, percent, effective_from, user=None):
    """The owner sets a per-state rate, such as Georgia's, from a date."""
    if jurisdiction.kind != TaxJurisdiction.Kind.STATE:
        raise RateError("Only a per-state rate is set by hand; Tennessee's come from the state's data.")
    if not Decimal(0) <= percent <= Decimal(20):
        raise RateError("Enter a rate from 0 to 20 percent.")
    _check_start(jurisdiction, effective_from)
    rate = TaxRate.objects.create(
        jurisdiction=jurisdiction, state_rate=percent, local_rate=Decimal(0), effective_from=effective_from,
        approved_at=timezone.now(), approved_by=user,
    )
    _close_previous(jurisdiction, effective_from, rate.pk)
    return rate
