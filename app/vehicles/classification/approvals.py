"""The approval list (Phase 2 Step 4, decisions 0079 and 0083): every model
in the job history, the spot-check list in data/approval-spot-checks.yaml,
every model with recent model years near a size line, and every model
approved before, each shown as its year ranges for the owner to approve or
change. The list started over when the size-based classes were applied: the
approvals before were archived. A spot-check entry or a near-line model
limited to some years shows only the ranges that overlap them.

A year range is a run of consecutive model years with the same vehicle
class, size and "how" line. An approval keeps the range as it was approved.
engine.record() calls clear_changed() after every change, and an approval
whose range no longer exists exactly as approved is cleared, so the model
shows again.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone

from vehicles.models import ClassificationChange, ModelApproval, ModelYearClassification, ModelYearSize, VehicleModel
from vehicles.vehicle_data.names import load_names

from . import owner
from .engine import because, record
from .seed import read_data

Kind = ClassificationChange.Kind


def size_rule(found):
    """The size of a stored classification, in words: a size variant's
    label, "asked", "one price", or "" for no class."""
    if found.vehicle_class is None:
        return ""
    if found.ask_size:
        return "asked"
    return found.size_variant.label if found.size_variant else "one price"


@dataclass
class YearRange:
    vehicle_model: VehicleModel
    first: int
    last: int
    vehicle_class: object
    size: str
    how: str
    # Waiting in the review queue: with no class, or keeping an earlier one meanwhile.
    in_review: bool
    approval: ModelApproval = None
    # The latest approval a change cleared, to say why the range shows again.
    cleared: ModelApproval = None

    @property
    def years(self):
        return str(self.first) if self.first == self.last else f"{self.first} to {self.last}"

    @property
    def key(self):
        return (self.vehicle_model.pk, self.first, self.last, getattr(self.vehicle_class, "pk", None), self.size, self.how)

    @property
    def target(self):
        """How the approval list's form names the range: "model id:first-last"."""
        return f"{self.vehicle_model.pk}:{self.first}-{self.last}"

    @property
    def measures(self):
        """What the class's size variant measures, such as "seat rows", or ""."""
        if self.vehicle_class is None or self.vehicle_class.size_variant_measures == self.vehicle_class.Measures.NONE:
            return ""
        return self.vehicle_class.size_variant_measures

    @property
    def can_approve(self):
        return self.vehicle_class is not None and not self.in_review


def approval_key(approval):
    return (approval.vehicle_model_id, approval.year_from, approval.year_to, approval.vehicle_class_id, approval.size, approval.how)


def model_ranges(model_ids):
    """{model id: [YearRange]}, oldest years first, with each range's
    current approval and the latest cleared one."""
    stored = (
        ModelYearClassification.objects.filter(vehicle_model_id__in=model_ids)
        .select_related("vehicle_model", "vehicle_class", "size_variant", "rule", "override", "decision")
        .order_by("vehicle_model_id", "year")
    )
    ranges = defaultdict(list)
    for found in stored:
        detail = (found.vehicle_class, size_rule(found), because(found), found.in_review)
        current = ranges[found.vehicle_model_id][-1] if ranges[found.vehicle_model_id] else None
        if (
            current is not None
            and current.last == found.year - 1
            and (getattr(current.vehicle_class, "pk", None), current.size, current.how, current.in_review)
            == (getattr(found.vehicle_class, "pk", None), *detail[1:])
        ):
            current.last = found.year
            continue
        ranges[found.vehicle_model_id].append(YearRange(found.vehicle_model, found.year, found.year, *detail))
    approved, cleared = {}, {}
    for approval in ModelApproval.objects.filter(vehicle_model_id__in=model_ids).select_related("approved_by", "cleared_by").order_by("approved_at", "pk"):
        if approval.cleared_at is None:
            approved[approval_key(approval)] = approval
        else:
            cleared[approval.vehicle_model_id, approval.year_from, approval.year_to] = approval
    for found in ranges.values():
        for year_range in found:
            year_range.approval = approved.get(year_range.key)
            if year_range.approval is None:
                year_range.cleared = next(
                    (
                        approval
                        for (model_id, first, last), approval in reversed(list(cleared.items()))
                        if model_id == year_range.vehicle_model.pk and first <= year_range.last and last >= year_range.first
                    ),
                    None,
                )
    return dict(ranges)


def range_of(vehicle_model, year):
    """The model's YearRange that holds the year, or None."""
    return next((found for found in model_ranges([vehicle_model.pk]).get(vehicle_model.pk, []) if found.first <= year <= found.last), None)


def clear_changed(change):
    """Clear every approval whose range no longer exists exactly as it was
    approved, naming the change that altered it. Returns how many."""
    active = list(ModelApproval.objects.filter(cleared_at=None))
    if not active:
        return 0
    ranges = model_ranges({approval.vehicle_model_id for approval in active})
    current = {year_range.key for found in ranges.values() for year_range in found if year_range.can_approve}
    stale = [approval.pk for approval in active if approval_key(approval) not in current]
    if stale:
        ModelApproval.objects.filter(pk__in=stale).update(cleared_at=timezone.now(), cleared_by=change if change.pk else None)
    return len(stale)


# What the approval list holds.

JOB_HISTORY = "job history"
SPOT_CHECK = "spot-check list"
NEAR_LINE = "near a line"
# A model approved before stays on the list, so one a change cleared shows again.
APPROVED_BEFORE = "approved before"


@dataclass
class ListedModel:
    vehicle_model: VehicleModel
    reasons: list = field(default_factory=list)
    ranges: list = field(default_factory=list)
    # The (first, last) years the reasons cover; None for every year.
    windows: list = None

    @property
    def approved(self):
        return bool(self.ranges) and all(found.approval is not None for found in self.ranges)


def spot_checks(data_dir=None):
    """[(entry, [VehicleModel])] for each entry of the spot-check list, the
    models being every catalog model of that make and name."""
    names = load_names(data_dir)
    by_name = defaultdict(list)
    for vehicle_model in VehicleModel.objects.order_by("pk"):
        by_name[names.make_key(vehicle_model.make), names.model_key(vehicle_model.make, vehicle_model.model)].append(vehicle_model)
    entries = read_data("approval-spot-checks.yaml", data_dir)["models"]
    return [
        (entry, by_name.get((names.make_key(entry["make"]), names.model_key(entry["make"], str(entry["model"]))), []))
        for entry in entries
    ]


def near_line_models(data_dir=None):
    """{model id: [(first, last, reason)]} for every run of a model's live
    model years, from newest_from on, whose box volume is within near_line
    cubic feet of a size line, or of the pickup line for a pickup
    (data/size-classes.yaml)."""
    from .engine import years_text
    from .sizes import read_scheme

    data = read_scheme(data_dir)
    near = data["near_line"]
    lines = [(line, {line["below"], line["above"]}) for line in [*data["lines"], data["pickup_line"]]]
    classes = {
        (model_id, year): name
        for model_id, year, name in ModelYearClassification.objects.filter(year__gte=data["newest_from"], in_review=False)
        .exclude(vehicle_class=None)
        .values_list("vehicle_model_id", "year", "vehicle_class__name")
    }
    hits = defaultdict(list)
    for size in ModelYearSize.objects.filter(year__gte=data["newest_from"]).order_by("vehicle_model_id", "year"):
        name = classes.get((size.vehicle_model_id, size.year))
        for line, sides in lines:
            if name in sides and abs(size.box_volume - line["at"]) <= near:
                hits[(size.vehicle_model_id, line["at"], line["below"], line["above"])].append((size.year, size.box_volume))
    found = defaultdict(list)
    for (model_id, at, below, above), years in hits.items():
        runs = []
        for year, volume in years:
            if runs and runs[-1][-1][0] == year - 1:
                runs[-1].append((year, volume))
            else:
                runs.append([(year, volume)])
        for run in runs:
            volumes = [volume for _, volume in run]
            shown = f"{min(volumes)}" if min(volumes) == max(volumes) else f"{min(volumes)} to {max(volumes)}"
            reason = f"{NEAR_LINE}: {years_text(run[0][0], run[-1][0])} at {shown} cu ft, near the {at} cu ft line ({below} | {above})"
            found[model_id].append((run[0][0], run[-1][0], reason))
    return dict(found)


def entry_years(entry):
    """" (2024 on)", " (to 2006)" or "" for a spot-check entry's years."""
    first, last = entry.get("year_from"), entry.get("year_to")
    if first and last:
        return f" ({first} to {last})"
    if first:
        return f" ({first} on)"
    return f" (to {last})" if last else ""


def approval_list(data_dir=None):
    """([ListedModel] by make and model, [spot-check entries not in the catalog])."""
    # linking imports this module, so it is imported here.
    from vehicles.linking import job_history_models

    reasons = defaultdict(list)
    # {model id: [(first, last)]}; None in it for a reason that covers every year.
    windows = defaultdict(list)
    # By make and model, so a model is listed whether or not its vehicles have a year (decision 0080).
    for model_id, count in sorted(job_history_models().items()):
        reasons[model_id].append(f"{JOB_HISTORY} ({count} vehicle{'s' if count != 1 else ''})")
        windows[model_id].append(None)
    missing = []
    for entry, found in spot_checks(data_dir):
        if not found:
            missing.append(entry)
        years = entry_years(entry)
        for vehicle_model in found:
            reasons[vehicle_model.pk].append(f"{SPOT_CHECK}{years}: {entry['why']}" if entry.get("why") else f"{SPOT_CHECK}{years}")
            windows[vehicle_model.pk].append((entry.get("year_from"), entry.get("year_to")) if years else None)
    for model_id, runs in near_line_models(data_dir).items():
        for first, last, reason in runs:
            reasons[model_id].append(reason)
            windows[model_id].append((first, last))
    for model_id in set(ModelApproval.objects.values_list("vehicle_model", flat=True)) - set(reasons):
        reasons[model_id].append(APPROVED_BEFORE)
        windows[model_id].append(None)
    ranges = model_ranges(list(reasons))
    models = VehicleModel.objects.in_bulk(list(reasons))
    listed = []
    for model_id, found in reasons.items():
        shown = ranges.get(model_id, [])
        if None not in windows[model_id]:
            shown = [
                year_range
                for year_range in shown
                if any((first is None or year_range.last >= first) and (last is None or year_range.first <= last) for first, last in windows[model_id])
            ]
        listed.append(ListedModel(models[model_id], found, shown, None if None in windows[model_id] else windows[model_id]))
    listed.sort(key=lambda item: (item.vehicle_model.make, item.vehicle_model.model, item.vehicle_model.year_from or 0, item.vehicle_model.pk))
    return listed, missing


# The owner's taps.


class RangeChanged(ValueError):
    """The year range is no longer as the screen showed it."""


def find_range(vehicle_model, first, last):
    found = next((found for found in model_ranges([vehicle_model.pk]).get(vehicle_model.pk, []) if (found.first, found.last) == (first, last)), None)
    if found is None:
        raise RangeChanged(f"{vehicle_model.make} {vehicle_model.model} no longer has the range {first} to {last}; look again.")
    return found


def range_label(year_range):
    model = year_range.vehicle_model
    return f"{model.make} {model.model} {year_range.years}: {year_range.vehicle_class}, size {year_range.size} ({year_range.how})"


@transaction.atomic
def approve(vehicle_model, first, last, user, note=""):
    """Approve one year range as it stands now."""
    year_range = find_range(vehicle_model, first, last)
    if not year_range.can_approve:
        raise RangeChanged("A range waiting in the review queue cannot be approved; change it instead.")
    if year_range.approval is not None:
        return year_range.approval
    approval = ModelApproval.objects.create(
        vehicle_model=vehicle_model, year_from=first, year_to=last, vehicle_class=year_range.vehicle_class,
        size=year_range.size, how=year_range.how[:300], approved_by=user if getattr(user, "pk", None) else None, note=note,
    )
    summary = f"Approved {range_label(year_range)}"
    if note:
        summary += f". Note: {note}"
    record(Kind.APPROVAL, summary, user=user, vehicle_model=vehicle_model)
    return approval


@transaction.atomic
def change(vehicle_model, first, last, user, vehicle_class, size_variant=None, ask_size=False, note=""):
    """Give a year range another class with a model override for exactly
    those years, then approve what it became: the owner chose it."""
    find_range(vehicle_model, first, last)
    owner.set_override(vehicle_model, user, vehicle_class, size_variant, ask_size, first, last, note or "Set on the approval list")
    approvals = []
    for year_range in model_ranges([vehicle_model.pk]).get(vehicle_model.pk, []):
        if first <= year_range.first and year_range.last <= last and year_range.can_approve:
            approvals.append(approve(vehicle_model, year_range.first, year_range.last, user, note))
    return approvals
