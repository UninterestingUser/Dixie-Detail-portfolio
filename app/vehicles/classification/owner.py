"""The owner's changes to classification from the control app (decision
0076): rules, model overrides, the third-row flag, review queue decisions,
class settings and vehicle overrides. Each is saved, applied at once, and
logged with who made it and each model year it changed.

A rule or class setting reaches every model, so it is previewed first
(engine.preview) and applied to the whole catalog when the owner confirms.
The others reach one model, or the model years picked in the review queue,
and are applied to those models only.
"""

import copy

from django.db import transaction
from django.utils import timezone

from vehicles.models import (
    ClassificationChange,
    ClassificationRule,
    ModelOverride,
    ModelYearClassification,
    ReviewDecision,
    VehicleModelYear,
)

from .engine import class_label, reclassify, record, size_label

Kind = ClassificationChange.Kind
OWNER = VehicleModelYear.Source.OWNER
POSITION_STEP = 10
# The third-row flag as seat rows, as in data/third-row-seating.yaml.
THIRD_ROW = {"always": [3], "never": [2], "optional": [2, 3]}


def rule_label(rule):
    return f"rule {rule.position} ({rule.name})"


def years_label(year_from, year_to):
    if year_from is None and year_to is None:
        return "all years"
    if year_from == year_to:
        return str(year_from)
    if year_from is None:
        return f"up to {year_to}"
    if year_to is None:
        return f"{year_from} and later"
    return f"{year_from} to {year_to}"


# Rules: every change is a proposal first, previewed against the whole
# catalog, then saved and applied.


def saved_rules():
    return list(ClassificationRule.objects.select_related("vehicle_class"))


def proposed_rules(changed):
    """Every rule, with the changed ones (unsaved copies, or new rules) in
    place of the saved."""
    rules = {rule.pk: rule for rule in saved_rules()}
    for index, rule in enumerate(changed):
        rules[rule.pk if rule.pk else f"new {index}"] = rule
    return list(rules.values())


def moved(rule, direction):
    """The rules whose positions change when rule moves one place up or
    down, as unsaved copies. Only the moved rule changes when there is room
    between its new neighbors; otherwise every rule is numbered again in
    steps of 10. [] when it is already first or last."""
    rules = sorted(saved_rules(), key=lambda found: (found.position, found.pk))
    index = next(place for place, found in enumerate(rules) if found.pk == rule.pk)
    target = index - 1 if direction == "up" else index + 1
    if not 0 <= target < len(rules):
        return []
    order = rules[:index] + rules[index + 1:]
    order.insert(target, rules[index])
    before = order[target - 1].position if target > 0 else -1
    after = order[target + 1].position if target + 1 < len(order) else before + 2 * POSITION_STEP
    if after - before >= 2:
        copied = copy.copy(rules[index])
        copied.position = (before + after) // 2
        return [copied]
    changed = []
    for place, found in enumerate(order, start=1):
        if found.position != place * POSITION_STEP:
            copied = copy.copy(found)
            copied.position = place * POSITION_STEP
            changed.append(copied)
    return changed


@transaction.atomic
def save_rules(changed, summary, user):
    """Save the proposed rules and apply them to the whole catalog."""
    for rule in changed:
        rule.full_clean()
        rule.save()
    return reclassify(Kind.RULE, summary, user=user)


# Class settings.


@transaction.atomic
def save_class(vehicle_class, summary, user):
    vehicle_class.full_clean()
    vehicle_class.save()
    return reclassify(Kind.CLASS_SETTING, summary, user=user)


# Model overrides and the third-row flag, for one model.


def override_label(override):
    size = (
        override.size_variant.label if override.size_variant
        else "always ask the size" if override.ask_size else "size from the facts"
    )
    return f"{years_label(override.year_from, override.year_to)}: {override.vehicle_class}, {size}"


@transaction.atomic
def set_override(vehicle_model, user, vehicle_class, size_variant=None, ask_size=False, year_from=None, year_to=None, note=""):
    """Set the model's override for these years, replacing one for exactly
    the same years."""
    override = ModelOverride.objects.filter(vehicle_model=vehicle_model, year_from=year_from, year_to=year_to).first()
    if override is None:
        override = ModelOverride(vehicle_model=vehicle_model, year_from=year_from, year_to=year_to)
    override.vehicle_class, override.size_variant, override.ask_size = vehicle_class, size_variant, ask_size
    override.set_by, override.set_at, override.note = user, timezone.now(), note
    override.save()
    summary = f"Set the override for {vehicle_model.make} {vehicle_model.model}, {override_label(override)}"
    if note:
        summary += f". Note: {note}"
    return reclassify(Kind.OVERRIDE, summary, user=user, model_ids=[vehicle_model.pk], vehicle_model=vehicle_model)


@transaction.atomic
def clear_override(override, user):
    vehicle_model = override.vehicle_model
    summary = f"Cleared the override for {vehicle_model.make} {vehicle_model.model}, {override_label(override)}"
    override.delete()
    return reclassify(Kind.OVERRIDE, summary, user=user, model_ids=[vehicle_model.pk], vehicle_model=vehicle_model)


def model_years_of(vehicle_model):
    """Every year of the model the catalog has."""
    years = set(VehicleModelYear.objects.filter(vehicle_model=vehicle_model).values_list("year", flat=True))
    years |= set(ModelYearClassification.objects.filter(vehicle_model=vehicle_model).values_list("year", flat=True))
    return sorted(years)


@transaction.atomic
def set_third_row(vehicle_model, user, flag, year_from=None, year_to=None, note=""):
    """Record the owner's own seat rows for the model's years in the range:
    always (three rows), never (two) or optional (both, so the customer is
    asked), or "clear" to remove them. The owner's figures beat the
    third-row list and NHTSA."""
    years = [
        year for year in model_years_of(vehicle_model)
        if (year_from is None or year >= year_from) and (year_to is None or year <= year_to)
    ]
    for year in years:
        row = VehicleModelYear.objects.filter(vehicle_model=vehicle_model, year=year, source=OWNER).first()
        if flag == "clear":
            if row is not None:
                row.seat_rows = []
                row.save()
            continue
        if row is None:
            row = VehicleModelYear(vehicle_model=vehicle_model, year=year, source=OWNER)
        row.seat_rows = THIRD_ROW[flag]
        row.save()
    action = "Cleared the third-row flag" if flag == "clear" else f"Set the third-row flag to {flag}"
    summary = f"{action} for {vehicle_model.make} {vehicle_model.model}, {years_label(year_from, year_to)} ({len(years)} model years)"
    if note:
        summary += f". Note: {note}"
    return reclassify(Kind.THIRD_ROW, summary, user=user, model_ids=[vehicle_model.pk], vehicle_model=vehicle_model)


# Review queue decisions, for one model year or many.


def decision_label(decision):
    if decision.vehicle_class is None:
        return "the photo cards"
    size = decision.size_variant.label if decision.size_variant else "always ask the size" if decision.ask_size else ""
    return class_label(decision.vehicle_class, size)


@transaction.atomic
def decide(classifications, user, choice, vehicle_class=None, size_variant=None, ask_size=False, note=""):
    """Settle model years in the review queue. choice is "accept" (each
    one's suggested class and size), "class" (vehicle_class, with its size
    fixed, always asked or from the facts) or "photo_cards". Returns
    (decided, skipped): a model year with no suggestion cannot be accepted."""
    decided, skipped = [], []
    for found in classifications:
        if choice == "accept":
            if found.suggested_class_id is None:
                skipped.append(found)
                continue
            # The suggested size, or, when it is asked, from the facts, which ask it too.
            values = {"vehicle_class": found.suggested_class, "size_variant": found.suggested_size_variant, "ask_size": False}
        elif choice == "class":
            values = {"vehicle_class": vehicle_class, "size_variant": size_variant, "ask_size": ask_size}
        else:
            values = {"vehicle_class": None, "size_variant": None, "ask_size": False}
        decision, _ = ReviewDecision.objects.get_or_create(vehicle_model=found.vehicle_model, year=found.year, defaults=values)
        for name, value in values.items():
            setattr(decision, name, value)
        decision.decided_by, decision.decided_at, decision.note = user, timezone.now(), note
        decision.save()
        decided.append(decision)
    if decided:
        if len(decided) == 1:
            one = decided[0]
            summary = f"Review queue: {one.year} {one.vehicle_model.make} {one.vehicle_model.model} -> {decision_label(one)}"
        elif choice == "accept":
            summary = f"Review queue: accepted the suggested class for {len(decided)} model years"
        else:
            summary = f"Review queue: {len(decided)} model years -> {decision_label(decided[0])}"
        if note:
            summary += f". Note: {note}"
        models = {decision.vehicle_model_id for decision in decided}
        reclassify(
            Kind.DECISION, summary, user=user, model_ids=sorted(models),
            vehicle_model=decided[0].vehicle_model if len(models) == 1 else None,
        )
    return decided, skipped


@transaction.atomic
def clear_decision(decision, user):
    vehicle_model = decision.vehicle_model
    summary = f"Cleared the review queue decision for {decision.year} {vehicle_model.make} {vehicle_model.model} ({decision_label(decision)})"
    decision.delete()
    return reclassify(Kind.DECISION, summary, user=user, model_ids=[vehicle_model.pk], vehicle_model=vehicle_model)


# A customer's vehicle.


@transaction.atomic
def override_vehicle(vehicle, user, vehicle_class=None, size_variant=None, note="", clear=False):
    """Set or clear one customer's vehicle's own class, which beats the
    catalog. Logged on the vehicle's catalog model, when it has one."""
    if clear:
        vehicle.clear_override()
        summary = f"Cleared the class override on {vehicle} ({vehicle.customer})"
    else:
        vehicle.override_class(vehicle_class, size_variant, user=user, note=note)
        size = size_label(size_variant, False, vehicle_class) if size_variant else ""
        summary = f"Set the class of {vehicle} ({vehicle.customer}) to {class_label(vehicle_class, size)}"
        if note:
            summary += f". Note: {note}"
    return record(Kind.VEHICLE_OVERRIDE, summary, user=user, vehicle_model=vehicle.vehicle_model)
