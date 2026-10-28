"""Switching to the size-based classes in one step (decision 0083):
apply_size_classes --effective YYYY-MM-DD [--dry-run].

In one transaction, so the classes and the prices never disagree, run()
renames the classes data/vehicle-classes.yaml renames, offers the pending
ones, retires the body-type classes, archives the old rules, model
overrides, review queue decisions and approvals, creates the size-based
rules and overrides of data/size-classes.yaml, classifies the whole catalog
with them, sets each customer's vehicle's class, runs the price book check
on the draft and publishes it with the effective date. A failed check rolls
everything back. A dry run does all of it, prints the same report and rolls
back.

Retired classes stay for history: past appointments and their quote lines
keep the class they had. Every booked job keeps its quoted price, the price
of record (decision 0059); the report lists each with its price under the
new book, and the owner decides each on the version's booked-job review.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from vehicles.models import (
    ClassificationChange,
    ClassificationRule,
    ModelApproval,
    ModelOverride,
    ModelYearClassification,
    ReviewDecision,
    Vehicle,
    VehicleClass,
)
from vehicles.vehicle_data.names import name_key, words

from .seed import read_data

Measures = VehicleClass.Measures
CHANGE_REASON = "apply_size_classes"


class SwitchError(ValueError):
    """The size-based classes cannot be applied as things stand."""


@lru_cache(maxsize=4)
def _class_data(data_dir):
    data = read_data("vehicle-classes.yaml", data_dir)
    retired = tuple(entry["name"] for entry in data.get("retired_classes") or [])
    renamed = tuple((entry["renamed_from"], entry["name"]) for entry in data["classes"] if entry.get("renamed_from"))
    return retired, renamed


def retired_names():
    """The body-type classes data/vehicle-classes.yaml lists as retired."""
    return _class_data(settings.DATA_DIR)[0]


def renames():
    """{old name: new name} for the classes data/vehicle-classes.yaml renames."""
    return dict(_class_data(settings.DATA_DIR)[1])


def switched():
    """Whether the size-based classes are live: none of the retired classes is still active."""
    return not VehicleClass.objects.filter(name__in=retired_names(), active=True).exists()


def archived_at(model):
    """When the model's records were last archived, or None."""
    return model.all_objects.aggregate(last=Max("archived_at"))["last"]


def is_minivan(model, names):
    """Whether a model name is or begins with one of the minivan names, in whole words."""
    found = words(model or "")
    starts = {"".join(found[:count]) for count in range(1, len(found) + 1)}
    return any(name_key(name) in starts for name in names)


def proposed_class(vehicle, data):
    """(class name or None, reason) proposed for a vehicle left in a retired
    class, from its recorded class (data/size-classes.yaml)."""
    if vehicle.vehicle_class is None:
        return None, "no recorded class: needs a year, make and model"
    recorded = vehicle.vehicle_class.name
    proposed = data["unlinked_vehicles"].get(recorded)
    if proposed is None:
        return None, "its recorded class has no proposed class"
    if recorded == data["minivans_recorded_in"] and is_minivan(vehicle.model, data["minivan_models"]):
        return data["minivan_class"], "a minivan, proposed from its recorded class"
    return proposed, "proposed from its recorded class"


def vehicle_name(vehicle):
    """A customer's vehicle as the reports show it: id, year, make and model only."""
    name = " ".join(str(part) for part in (vehicle.year, vehicle.make, vehicle.model) if part)
    return f"vehicle {vehicle.pk}: {name or 'no year, make or model'}"


@dataclass
class VehicleChange:
    vehicle: Vehicle
    before: str
    after: str
    reason: str
    # "set": the class was set; "proposed": left in a retired class for the
    # differences screen; "kept": its own override in a live class stands.
    kind: str


@dataclass
class Before:
    """What the switch replaces, as it was, for the report."""

    stored: dict = field(default_factory=dict)
    overrides: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    approvals: list = field(default_factory=list)
    rules: int = 0
    vehicles: dict = field(default_factory=dict)

    @classmethod
    def capture(cls):
        from .engine import class_label

        found = cls()
        found.stored = {
            (row.vehicle_model_id, row.year): row.vehicle_class.name if row.vehicle_class_id else "in queue"
            for row in ModelYearClassification.objects.select_related("vehicle_class")
        }
        found.overrides = list(ModelOverride.objects.select_related("vehicle_model", "vehicle_class").order_by("vehicle_model__make", "vehicle_model__model", "year_from"))
        found.decisions = list(ReviewDecision.objects.select_related("vehicle_model", "vehicle_class"))
        found.approvals = list(
            ModelApproval.objects.filter(cleared_at=None).select_related("vehicle_model", "vehicle_class").order_by("vehicle_model__make", "vehicle_model__model", "year_from")
        )
        found.rules = ClassificationRule.objects.count()
        found.vehicles = {
            vehicle.pk: class_label(vehicle.vehicle_class, vehicle.size_variant.label if vehicle.size_variant else "") if vehicle.vehicle_class else "no class"
            for vehicle in Vehicle.objects.select_related("vehicle_class", "size_variant")
        }
        return found


def archive(model, now, history=True):
    """Archive every live record of a model; returns how many."""
    found = list(model.objects.all())
    if history:
        for record in found:
            record.archived_at = now
            record._change_reason = CHANGE_REASON
            record.save()
    else:
        model.objects.filter(pk__in=[record.pk for record in found]).update(archived_at=now)
    return len(found)


def switch_classes():
    """Rename, offer and retire classes as data/vehicle-classes.yaml says. Returns what changed."""
    done = []
    for old, new in renames().items():
        vehicle_class = VehicleClass.objects.filter(name=old).first()
        if vehicle_class is not None and not VehicleClass.objects.filter(name=new).exists():
            vehicle_class.name = new
            vehicle_class._change_reason = CHANGE_REASON
            vehicle_class.save()
            done.append(f"renamed {old} to {new}")
    for vehicle_class in VehicleClass.objects.filter(pending=True):
        vehicle_class.pending = False
        vehicle_class._change_reason = CHANGE_REASON
        vehicle_class.save()
        done.append(f"offered {vehicle_class}")
    for vehicle_class in VehicleClass.objects.filter(name__in=retired_names(), active=True):
        vehicle_class.active = False
        vehicle_class._change_reason = CHANGE_REASON
        vehicle_class.save()
        done.append(f"retired {vehicle_class}")
    return done


def size_for_vehicle(vehicle, result, variants):
    """The size variant a vehicle takes in its new class: the one the
    catalog fixes, else its own when it belongs to the class or counts the
    same seat rows, else none (asked at its next booking)."""
    if result.size_variant is not None and not result.ask_size:
        return result.size_variant
    old = vehicle.size_variant
    if old is None:
        return None
    if old.vehicle_class_id == result.vehicle_class.pk:
        return old
    seat_classes = (Measures.SEAT_ROWS, Measures.SEATS)
    if old.vehicle_class.size_variant_measures in seat_classes and result.vehicle_class.size_variant_measures in seat_classes:
        return variants.get(result.vehicle_class.pk, {}).get(old.value)
    return None


def new_result_for(vehicle, results, by_model, spread):
    """(Result or None, reason, confirm year) for one customer's vehicle."""
    from .engine import years_text
    from .sizes import newest_generation

    if vehicle.vehicle_model_id is None:
        return None, "not linked to the catalog", False
    if vehicle.year is None:
        found = newest_generation(by_model.get(vehicle.vehicle_model_id, []), spread)
        if found is None:
            return None, "no year, and no model year of its model has a class", False
        result, first, last = found
        return result, f"no year: its model's newest generation, {years_text(first, last)}; confirm the year at the next visit", True
    found = results.get((vehicle.vehicle_model_id, vehicle.year))
    if found is None:
        return None, f"the catalog has no {vehicle.year} for its model", False
    result = found[1]
    if result.vehicle_class is None or result.in_review:
        return None, "its model year waits in the review queue", False
    return result, result.because, False


def update_vehicles(results, variants, data, before):
    """Set each customer's vehicle's class from the new classification.
    A vehicle with no year takes its model's newest generation, flagged to
    confirm the year; one left in a retired class goes on the differences
    screen with a proposed class. Returns [VehicleChange]."""
    from .engine import class_label

    by_model = defaultdict(list)
    for (model_id, year), (model_year, result) in results.items():
        by_model[model_id].append((year, model_year, result))
    changes = []
    for vehicle in Vehicle.objects.select_related("vehicle_model", "vehicle_class", "size_variant__vehicle_class").order_by("pk"):
        old_class = vehicle.vehicle_class
        if vehicle.class_overridden and old_class.active:
            changes.append(VehicleChange(vehicle, before.vehicles[vehicle.pk], before.vehicles[vehicle.pk], "its own override stands", "kept"))
            continue
        result, reason, confirm = new_result_for(vehicle, results, by_model, data["newest_generation_spread"])
        if result is None:
            if old_class is not None and not old_class.active:
                proposed, why = proposed_class(vehicle, data)
                changes.append(VehicleChange(vehicle, before.vehicles[vehicle.pk], f"proposed {proposed or 'no class'}", f"{reason}; {why}: on the differences screen", "proposed"))
            continue
        size = size_for_vehicle(vehicle, result, variants)
        if vehicle.class_overridden:
            reason += "; its own override named a retired class and was cleared"
            vehicle.class_override_by, vehicle.class_override_at, vehicle.class_override_note = None, None, ""
        vehicle.vehicle_class, vehicle.size_variant, vehicle.confirm_year = result.vehicle_class, size, confirm
        vehicle._change_reason = CHANGE_REASON
        vehicle.save()
        after = class_label(vehicle.vehicle_class, size.label if size else ("ask" if result.ask_size else ""))
        changes.append(VehicleChange(vehicle, before.vehicles[vehicle.pk], after, reason, "set"))
    return changes


@dataclass
class Outcome:
    scheme: object
    before: Before
    classes: list
    archived: dict
    seeded: object
    counts: dict
    vehicles: list
    problems: list
    jobs: list
    version: object
    effective: object


def run(effective, dry_run, out, user=None):
    """Apply the size-based classes with the draft price book, effective on
    the date given, and write the report to out. A dry run rolls everything
    back. Raises SwitchError, after rolling back, when it cannot apply."""
    from pricebook.checks import check, version_cells
    from pricebook.models import PricebookVersion
    from pricebook.publishing import publish

    from .engine import active_variants, apply, changes, classify_catalog, record
    from .seed import SeedReport, sync_launch_set, sync_seat_list
    from .size_preview import write_report
    from .sizes import Scheme, fallback_counts, produced, read_scheme

    today = timezone.localdate()
    if switched():
        raise SwitchError("The size-based classes are already applied.")
    if effective < today:
        raise SwitchError("The effective date must be today or later.")
    if not dry_run and effective != today:
        raise SwitchError(
            f"Apply the size-based classes on the day they take effect: run this on {effective:%Y-%m-%d}, or give today's"
            " date. The classes switch when it runs, so the prices must take effect the same day."
        )
    draft = PricebookVersion.objects.filter(status=PricebookVersion.Status.DRAFT).first()
    if draft is None or not draft.prices.filter(vehicle_class__pending=True).exists():
        raise SwitchError("No draft holds the new price book: run load_pricebook first, which loads data/price-matrix.csv as a draft.")

    with transaction.atomic():
        before = Before.capture()
        now = timezone.now()
        classes = switch_classes()
        archived = {
            "rules": archive(ClassificationRule, now),
            "model overrides": archive(ModelOverride, now),
            "review queue decisions": archive(ReviewDecision, now),
            "approvals": archive(ModelApproval, now, history=False),
        }
        seeded = SeedReport()
        sync_launch_set(seeded)
        sync_seat_list(seeded)
        results = classify_catalog()
        found = changes(results)
        counts = apply(results)
        summary = f"apply_size_classes switched to the size-based classes, effective {effective:%Y-%m-%d}: {len(found):,} model years changed"
        record(ClassificationChange.Kind.SIZE_SWITCH, summary, found, user=user)
        variants = active_variants()
        data = read_scheme()
        vehicles = update_vehicles(results, variants, data, before)
        problems = check(version_cells(draft), produced(results, variants))
        jobs = publish(draft, effective, {}, user=user, log_choices=False)
        scheme = Scheme(data, results, fallback_counts(results))
        outcome = Outcome(scheme, before, classes, archived, seeded, counts, vehicles, problems, jobs, draft, effective)
        write_report(outcome, out, dry_run)
        if dry_run or problems:
            transaction.set_rollback(True)
    if problems and not dry_run:
        raise SwitchError(f"The draft price book fails the check in {len(problems):,} place(s); nothing was changed.")
    return outcome
