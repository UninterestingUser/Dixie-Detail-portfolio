"""Linking customers' vehicles to the vehicle catalog (Phase 2 Step 4,
decision 0077), and the differences between a vehicle's own class and the
catalog's.

A vehicle is matched by its year, make and model with the names in
data/vehicle-names.yaml: make spellings such as "Chevy", the other spellings
of one model, and trim words such as "LE" or "XLT" that may follow the model
name. The longest start of the model field that names a catalog model of
the make, sold in the vehicle's year, wins, and only when every word after
it is a trim word. Two catalog models that fit equally are both listed and
neither is linked: the matcher never guesses.

Linking sets the vehicle's catalog model and fills a missing vehicle class
or size variant from the catalog. It never changes a class the vehicle
already has: the owner settles each difference on the differences screen
(keep_imported, accept_catalog, override_model). Past appointments keep
their lines (decision 0059), except the imported motorcycle jobs
(decision 0078, motorcycle_jobs).
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction

from appointments.models import Appointment, AppointmentLine
from pricebook.management.commands.load_pricebook import read_matrix
from pricebook.models import Service
from vehicles.classification import owner
from vehicles.classification.approvals import range_of, size_rule
from vehicles.classification.engine import class_label, record
from vehicles.classification.seed import read_data
from vehicles.models import ClassificationChange, ModelYearClassification, Vehicle, VehicleClass, VehicleModel
from vehicles.vehicle_data.names import load_names, name_key, words

Kind = ClassificationChange.Kind
LINKED = "linked"
NOT_FOUND = "not found"
SEVERAL = "more than one candidate"
CHANGE_REASON = "link_vehicles"


def describe(vehicle):
    """A vehicle as the report shows it: its id, year, make, model and color,
    never its customer."""
    return f"vehicle {vehicle.pk}: {vehicle}"


def describe_model(vehicle_model):
    kind = ", motorcycle" if vehicle_model.vehicle_type == VehicleModel.VehicleType.MOTORCYCLE else ""
    years = f"{vehicle_model.year_from or '?'}-{vehicle_model.year_to or ''}"
    return f"{vehicle_model.make} {vehicle_model.model} ({years}{kind}, catalog model {vehicle_model.pk})"


@dataclass
class Match:
    status: str
    vehicle_model: VehicleModel = None
    # The catalog models that fit equally, for SEVERAL.
    candidates: list = field(default_factory=list)
    reason: str = ""
    # The trim words left off the model field, such as ["LE"].
    dropped: list = field(default_factory=list)


class Catalog:
    """The catalog's models by make and name, read once for a run."""

    def __init__(self, names=None):
        self.names = names or load_names()
        self.by_make = defaultdict(list)
        self.keys = {}
        for vehicle_model in VehicleModel.objects.order_by("make", "model", "year_from", "pk"):
            self.by_make[self.names.make_key(vehicle_model.make)].append(vehicle_model)
            self.keys[vehicle_model.pk] = self.names.model_key(vehicle_model.make, vehicle_model.model)

    def named(self, make, model):
        """Every catalog model of this make and name, all years."""
        key = self.names.model_key(make, model)
        return [found for found in self.by_make.get(self.names.make_key(make), []) if self.keys[found.pk] == key]


def sold_in(vehicle_model, year):
    return (vehicle_model.year_from or year) <= year <= (vehicle_model.year_to or year)


def tokens(model):
    """The model field as words, keeping each word's spelling: "CR-V EX-L" -> ["CR-V", "EX-L"]."""
    return [part for part in re.split(r"[\s/()]+", model or "") if name_key(part)]


def match(catalog, year, make, model):
    """The Match for one year, make and model."""
    make, model = (make or "").strip(), (model or "").strip()
    if not make or not model:
        return Match(NOT_FOUND, reason="no make or model recorded")
    if year is None:
        return Match(NOT_FOUND, reason="no year recorded")
    if not catalog.by_make.get(catalog.names.make_key(make)):
        return Match(NOT_FOUND, reason=f"no catalog make {make!r}; add its spelling to make_aliases in data/vehicle-names.yaml")
    parts = tokens(model)
    reasons = []
    for end in range(len(parts), 0, -1):
        name, left = " ".join(parts[:end]), parts[end:]
        named = catalog.named(make, name)
        if not named:
            continue
        shown = f"{named[0].make} {named[0].model}"
        left_words = [word for part in left for word in words(part)]
        blocked = [part for part in left if not set(words(part)) <= catalog.names.trim_words]
        plates = set(left_words) & catalog.names.nameplate_words(make, name)
        if blocked or plates:
            # A shorter start leaves these words too, so nothing shorter fits.
            extra = " ".join(blocked or sorted(plates))
            why = "names one of its nameplates" if plates and not blocked else "is not a trim word in data/vehicle-names.yaml"
            reasons.append(f"nearest is the {shown}, but {extra!r} {why}")
            break
        in_year = [found for found in named if sold_in(found, year)]
        if len(in_year) == 1:
            return Match(LINKED, in_year[0], dropped=left)
        if in_year:
            return Match(SEVERAL, candidates=in_year, dropped=left)
        spans = ", ".join(f"{found.year_from or '?'} to {found.year_to or 'now'}" for found in named)
        reasons.append(f"the catalog has the {shown} for {spans}, not {year}")
    return Match(NOT_FOUND, reason="; ".join(reasons) or "no catalog model of this make and name")


# The catalog's class for a vehicle, and how the vehicle's own differs.


def stored_for(vehicles):
    """{(model id, year): ModelYearClassification} for linked vehicles."""
    keys = {(vehicle.vehicle_model_id, vehicle.year) for vehicle in vehicles if vehicle.vehicle_model_id and vehicle.year}
    if not keys:
        return {}
    found = ModelYearClassification.objects.filter(
        vehicle_model_id__in={key[0] for key in keys}, year__in={key[1] for key in keys}
    ).select_related("vehicle_model", "vehicle_class", "size_variant", "rule", "override", "decision")
    return {(row.vehicle_model_id, row.year): row for row in found if (row.vehicle_model_id, row.year) in keys}


def fills(vehicle, stored):
    """{field: value} for the details the catalog fills in: a missing class,
    with its size when the catalog fixes it, or a missing size of the class
    the vehicle has. Nothing while the model year waits in the review queue."""
    if stored is None or stored.vehicle_class_id is None or stored.in_review:
        return {}
    fixed = stored.size_variant if not stored.ask_size else None
    if vehicle.vehicle_class_id is None:
        return {"vehicle_class": stored.vehicle_class, **({"size_variant": fixed} if fixed else {})}
    if vehicle.vehicle_class_id == stored.vehicle_class_id and vehicle.size_variant_id is None and fixed is not None:
        return {"size_variant": fixed}
    return {}


def own_label(vehicle):
    size = vehicle.size_variant.label if vehicle.size_variant else ""
    return class_label(vehicle.vehicle_class, size)


def catalog_label(stored):
    return class_label(stored.vehicle_class, size_rule(stored))


def differs(vehicle, stored):
    """"class" or "size" when the vehicle's own class or size variant differs
    from the catalog's live one, else None. A vehicle with its own override
    has been settled, and a size the catalog asks is the customer's answer."""
    if vehicle.class_overridden or vehicle.vehicle_class_id is None:
        return None
    if stored is None or stored.vehicle_class_id is None:
        return None
    if vehicle.vehicle_class_id != stored.vehicle_class_id:
        return "class"
    if stored.ask_size or stored.size_variant_id is None or vehicle.size_variant_id is None:
        return None
    return "size" if vehicle.size_variant_id != stored.size_variant_id else None


@dataclass
class Difference:
    vehicle: Vehicle
    stored: ModelYearClassification
    kind: str

    @property
    def imported(self):
        return own_label(self.vehicle)

    @property
    def catalog(self):
        return catalog_label(self.stored)


def differences(vehicles=None):
    """[Difference] for every linked vehicle whose own class or size differs."""
    if vehicles is None:
        vehicles = Vehicle.objects.filter(vehicle_model__isnull=False).select_related(
            "customer", "vehicle_model", "vehicle_class", "size_variant"
        )
    vehicles = list(vehicles)
    stored = stored_for(vehicles)
    found = []
    for vehicle in vehicles:
        row = stored.get((vehicle.vehicle_model_id, vehicle.year))
        kind = differs(vehicle, row)
        if kind:
            found.append(Difference(vehicle, row, kind))
    return sorted(found, key=lambda difference: (difference.vehicle.make, difference.vehicle.model, difference.vehicle.year or 0, difference.vehicle.pk))


# The owner's three choices on the differences screen.


def model_span(vehicle):
    """(first, last): the vehicle's catalog model years around its year that
    share its class, size and how, which a per-model override covers."""
    found = range_of(vehicle.vehicle_model, vehicle.year)
    return (found.first, found.last) if found else (vehicle.year, vehicle.year)


@transaction.atomic
def keep_imported(vehicle, user, note=""):
    """Keep the vehicle's own class and size as its per-vehicle override,
    such as for a lifted or modified vehicle."""
    return owner.override_vehicle(
        vehicle, user, vehicle.vehicle_class, vehicle.size_variant, note=note or "Kept the imported class on the differences screen"
    )


@transaction.atomic
def accept_catalog(vehicle, stored, user, note=""):
    """Give the vehicle the catalog's class, with the catalog's size when it
    fixes one, or the vehicle's own size when it belongs to that class."""
    before = own_label(vehicle)
    vehicle.vehicle_class = stored.vehicle_class
    if stored.size_variant_id and not stored.ask_size:
        vehicle.size_variant = stored.size_variant
    elif vehicle.size_variant is not None and vehicle.size_variant.vehicle_class_id != stored.vehicle_class_id:
        vehicle.size_variant = None
    vehicle._change_reason = "Took the catalog's class on the differences screen"
    vehicle.save()
    summary = f"Vehicle {vehicle.pk} ({vehicle}) takes the catalog's class: {before} -> {own_label(vehicle)}"
    if note:
        summary += f". Note: {note}"
    return record(Kind.VEHICLE_CLASS, summary, user=user, vehicle_model=vehicle.vehicle_model)


@transaction.atomic
def override_model(vehicle, user, note=""):
    """Give every vehicle of the model, in the years around this one that
    the catalog classes alike, this vehicle's class with a model override.
    A class that differs takes its size from the facts; a size that differs
    is fixed for those years. Returns the Changes."""
    first, last = model_span(vehicle)
    stored = ModelYearClassification.objects.filter(vehicle_model=vehicle.vehicle_model, year=vehicle.year).first()
    same_class = stored is not None and stored.vehicle_class_id == vehicle.vehicle_class_id
    size = vehicle.size_variant if same_class else None
    return owner.set_override(
        vehicle.vehicle_model, user, vehicle.vehicle_class, size, False, first, last,
        note or f"From vehicle {vehicle.pk} on the differences screen",
    )


# The imported motorcycle jobs (decision 0078).


def motorcycle_names(data_dir=None):
    """(class name, service name, price) for motorcycles, from data/: the
    class with vehicle type motorcycle, the service offered only for it, and
    that service's price in data/price-matrix.csv."""
    class_name = next(
        entry["name"] for entry in read_data("vehicle-classes.yaml", data_dir)["classes"] if entry.get("vehicle_type") == "motorcycle"
    )
    service_name = next(
        entry["name"] for entry in read_data("services.yaml", data_dir)["services"] if entry.get("offered_for") == [class_name]
    )
    price = next(
        (row["price"] for row in read_matrix() if row["service"] == service_name and row["vehicle_class"] == class_name), None
    )
    return class_name, service_name, price


@dataclass
class MotorcycleJob:
    appointment: Appointment
    vehicle: Vehicle
    amount: Decimal
    done: bool  # already has the class and service

    def describe(self):
        return f"appointment {self.appointment.pk} on {self.appointment.scheduled_start:%Y-%m-%d}, {describe(self.vehicle)}: ${self.amount:,.2f}"


def motorcycle_jobs(vehicles, class_name):
    """[MotorcycleJob] for the imported appointments of these vehicles that
    are linked to a motorcycle model and were imported with no class, or
    have the motorcycle class."""
    found = []
    for vehicle in vehicles:
        if vehicle.vehicle_model is None or vehicle.vehicle_model.vehicle_type != VehicleModel.VehicleType.MOTORCYCLE:
            continue
        if vehicle.vehicle_class is not None and vehicle.vehicle_class.name != class_name:
            continue
        for appointment in vehicle.appointments.filter(source=Appointment.Source.IMPORT).prefetch_related("lines"):
            lines = list(appointment.lines.all())
            done = bool(lines) and not any(line.vehicle_class_id is None for line in lines)
            found.append(MotorcycleJob(appointment, vehicle, appointment.total_before_tax, done))
    return found


def give_motorcycle_class(job, vehicle_class, service):
    """The motorcycle job's lines with no class get the Motorcycles class,
    and its first custom line the Motorcycle Detail service. Every amount
    stays as imported, and so do the payments (decision 0066)."""
    if job.vehicle.vehicle_class_id is None:
        job.vehicle.vehicle_class = vehicle_class
        job.vehicle._change_reason = CHANGE_REASON
        job.vehicle.save()
    first = True
    for line in job.appointment.lines.filter(vehicle_class__isnull=True).order_by("position", "pk"):
        line.vehicle_class, line.vehicle_class_name = vehicle_class, vehicle_class.name
        if first and line.kind == AppointmentLine.Kind.CUSTOM:
            line.kind, line.service, line.description = AppointmentLine.Kind.SERVICE, service, service.name
            first = False
        line._change_reason = f"{CHANGE_REASON}: imported motorcycle job (decision 0078)"
        line.save()


# A run.


@dataclass
class Linked:
    vehicle: Vehicle
    vehicle_model: VehicleModel
    dropped: list
    filled: dict
    # Linked by an earlier run, or moved by an import merge.
    before: bool


@dataclass
class Report:
    linked: list = field(default_factory=list)  # [Linked]
    not_found: list = field(default_factory=list)  # [(vehicle, Match)]
    several: list = field(default_factory=list)  # [(vehicle, Match)]
    # Linked before to another model than the one that matches now; the link is kept.
    kept_link: list = field(default_factory=list)  # [(vehicle, Match)]
    differences: list = field(default_factory=list)  # [Difference]
    # Linked, but the catalog has no live class for the year, or waits in the review queue.
    no_class_yet: list = field(default_factory=list)  # [(vehicle, ModelYearClassification or None)]
    motorcycle_jobs: list = field(default_factory=list)  # [MotorcycleJob]
    # Not linked and with no class: a motorcycle the names did not find would be here.
    unlinked_classless: list = field(default_factory=list)  # [vehicle]
    motorcycle: tuple = ()  # (class name, service name, price)


@transaction.atomic
def link_vehicles(apply=False):
    """Match every customer's vehicle to the catalog and, when apply is
    true, link it, fill what the catalog can fill, and give the imported
    motorcycle jobs their class and service. A vehicle linked before keeps
    its link. Returns a Report."""
    catalog = Catalog()
    report = Report(motorcycle=motorcycle_names())
    vehicles = list(Vehicle.objects.select_related("vehicle_model", "vehicle_class", "size_variant").order_by("make", "model", "year", "pk"))
    dropped = {}
    for vehicle in vehicles:
        found = match(catalog, vehicle.year, vehicle.make, vehicle.model)
        if vehicle.vehicle_model_id is not None:
            if found.status != LINKED or found.vehicle_model.pk != vehicle.vehicle_model_id:
                report.kept_link.append((vehicle, found))
            continue
        if found.status == LINKED:
            vehicle.vehicle_model = found.vehicle_model
            dropped[vehicle.pk] = found.dropped
        elif found.status == SEVERAL:
            report.several.append((vehicle, found))
        else:
            report.not_found.append((vehicle, found))

    stored = stored_for(vehicles)
    for vehicle in vehicles:
        if vehicle.vehicle_model is None:
            if vehicle.vehicle_class_id is None:
                report.unlinked_classless.append(vehicle)
            continue
        row = stored.get((vehicle.vehicle_model.pk, vehicle.year))
        before = vehicle.pk not in dropped
        filled = fills(vehicle, row)
        report.linked.append(Linked(vehicle, vehicle.vehicle_model, dropped.get(vehicle.pk, []), filled, before))
        if row is None or row.vehicle_class_id is None or row.in_review:
            report.no_class_yet.append((vehicle, row))
        for name, value in filled.items():
            setattr(vehicle, name, value)
        if apply and (filled or not before):
            vehicle._change_reason = CHANGE_REASON
            vehicle.save()
        kind = differs(vehicle, row)
        if kind:
            report.differences.append(Difference(vehicle, row, kind))

    class_name, service_name, _ = report.motorcycle
    report.motorcycle_jobs = motorcycle_jobs([vehicle for vehicle in vehicles if vehicle.vehicle_model is not None], class_name)
    if apply:
        vehicle_class = VehicleClass.objects.get(name=class_name)
        service = Service.objects.get(name=service_name)
        for job in report.motorcycle_jobs:
            if not job.done:
                give_motorcycle_class(job, vehicle_class, service)
        newly = sum(1 for linked in report.linked if not linked.before)
        filled = sum(1 for linked in report.linked if linked.filled)
        given = sum(1 for job in report.motorcycle_jobs if not job.done)
        record(Kind.LINK, f"link_vehicles linked {newly:,} vehicles, filled details on {filled:,} and gave {given:,} imported motorcycle jobs their class and service")
    return report
