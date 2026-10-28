"""Classifying the whole catalog, one model year at a time.

For each model year: a model override covering the year wins, then the
owner's review queue decision for it. A model year the EPA has not
published yet takes the class and size of the model's nearest classified
year (decision 0075). Otherwise the active rules are tried in order and the
first that holds gives the vehicle class. A model year that no rule holds
for, or whose facts straddle a rule or whose sources disagree about one,
goes to the review queue instead of going live, with a suggested class. The
size variant is then set from the facts the class's size variant measures,
or left for the customer to answer. Once the size-based classes are live,
classification.sizes.finish() then takes its steps: the pickup line, the
EPA size class fallback and smoothing.

preview() works all of this out for a proposed set of rules and overrides
without saving anything; apply() saves it as each model year's
ModelYearClassification, and record() logs what it changed.
"""

import copy
import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from simple_history.utils import bulk_update_with_history

from vehicles.models import (
    ClassificationChange,
    ClassificationEffect,
    ClassificationRule,
    ModelOverride,
    ModelYearClassification,
    ReviewDecision,
    SizeVariant,
    VehicleClass,
    VehicleModel,
    VehicleModelYear,
)

from .rules import ModelYear, Outcome, parse_share, test_rule
from .seed import read_data

Method = ModelYearClassification.Method
Kind = ModelYearClassification.ReviewKind
Measures = VehicleClass.Measures
EPA = VehicleModelYear.Source.EPA
BATCH = 2000
LINKS = ("vehicle_class", "size_variant", "rule", "override", "decision", "suggested_class", "suggested_size_variant")
REVIEW_KINDS = {Outcome.STRADDLES: Kind.SPLIT, Outcome.DISAGREE: Kind.DISAGREE}

# The size variant each fact value gives; None where the fact does not settle it.
DOORS = {"two-door": 1, "four-door": 2}
CABS = {"regular": 1, "extended": 2, "crew": 2}


@dataclass
class Result:
    vehicle_class: object = None
    size_variant: object = None
    ask_size: bool = False
    method: str = Method.REVIEW
    rule: object = None
    override: object = None
    decision: object = None
    carried_from: int = None
    reasons: list = field(default_factory=list)
    kinds: list = field(default_factory=list)
    # For the review queue: the class to accept with one tap, and its size.
    suggested_class: object = None
    suggested_size: object = None
    suggested_ask: bool = False

    @property
    def in_review(self):
        return self.method == Method.REVIEW

    @property
    def because(self):
        """What gave the answer, for reports and the control app."""
        return because(self)


def because(found):
    """How a Result or a stored ModelYearClassification was reached, in words."""
    if found.method == Method.PHOTO_CARDS:
        return "sent to the photo cards from the review queue"
    if found.method == Method.EPA_FALLBACK:
        return "EPA size class fallback: " + "; ".join(found.review_reasons if hasattr(found, "review_reasons") else found.reasons)
    if found.method in (Method.PICKUP_LINE, Method.SMOOTHED):
        return "; ".join(found.review_reasons if hasattr(found, "review_reasons") else found.reasons)
    if found.method == Method.DECISION:
        return "review queue decision" + (f" ({found.decision.note})" if found.decision is not None and found.decision.note else "")
    if found.method == Method.REVIEW:
        return "review queue: " + "; ".join(found.review_reasons if hasattr(found, "review_reasons") else found.reasons)
    if found.override is not None:
        given = f"model override ({found.override.note or 'no note'})"
    elif found.rule is not None:
        given = f"rule {found.rule.position}: {found.rule.name}"
    else:
        given = found.get_method_display() if hasattr(found, "get_method_display") else str(found.method)
    if found.method == Method.CARRIED:
        return f"from the {found.carried_from} model year, {given}; the EPA has not published this year yet"
    return given


def active_variants():
    """{vehicle class id: {value: size variant}} for the active size variants."""
    found = defaultdict(dict)
    for variant in SizeVariant.objects.filter(active=True).select_related("vehicle_class"):
        found[variant.vehicle_class_id][variant.value] = variant
    return found


def fact_sizes(vehicle_class, model_year):
    """The size variant values the model year's facts give for this class,
    with None for a trim the facts do not settle."""
    if vehicle_class.size_variant_measures == Measures.DOORS:
        styles = model_year.values("body_style")
        return {DOORS.get(style) for style in styles} if styles else {None}
    if vehicle_class.size_variant_measures == Measures.CAB_STYLE:
        cabs = model_year.values("cab_style")
        return {CABS.get(cab) for cab in cabs} if cabs else {None}
    if vehicle_class.size_variant_measures == Measures.SEAT_ROWS:
        rows = model_year.values("seat_rows")
        return {int(count) for count in rows} if rows else {None}
    if vehicle_class.size_variant_measures == Measures.SEATS:
        from .sizes import seat_rows

        return seat_rows(model_year)
    return {None}


def size_for(vehicle_class, model_year, variants):
    """(size variant, ask) for a model year in this class. A class with no
    size variants has one price; one with a single size variant, such as
    Full-size, always has it. Otherwise the facts must give
    one size for every trim, or the customer is asked."""
    offered = variants.get(vehicle_class.pk, {})
    if not offered:
        return None, False
    if len(offered) == 1:
        return next(iter(offered.values())), False
    sizes = fact_sizes(vehicle_class, model_year)
    if len(sizes) == 1:
        value = next(iter(sizes))
        if value in offered:
            return offered[value], False
    return None, True


def majority_share(data_dir=None):
    """The share of a model year's rows that decides a condition, from
    data/vehicle-classes.yaml (two-thirds at launch)."""
    return parse_share(read_data("vehicle-classes.yaml", data_dir)["rule_settings"]["majority_share"])


def chosen_size(chosen, model_year, variants):
    """(size variant, ask) for a model override or queue decision: fixed,
    always asked, or worked out from the facts."""
    if chosen.size_variant is not None:
        return chosen.size_variant, False
    if chosen.ask_size and variants.get(chosen.vehicle_class.pk):
        return None, True
    return size_for(chosen.vehicle_class, model_year, variants)


def classify_model_year(model_year, rules, overrides, variants, share=1, decision=None):
    """The Result for one model year: rules sorted by position, overrides
    those of its model, decision the owner's queue decision for the year."""
    override = next((found for found in overrides if found.covers(model_year.year)), None)
    if override is not None:
        size, ask = chosen_size(override, model_year, variants)
        return Result(override.vehicle_class, size, ask, Method.OVERRIDE, override=override)
    if decision is not None:
        if decision.vehicle_class is None:
            return Result(method=Method.PHOTO_CARDS, decision=decision)
        size, ask = chosen_size(decision, model_year, variants)
        return Result(decision.vehicle_class, size, ask, Method.DECISION, decision=decision)
    return classify_by_rules(model_year, rules, variants, share)


def classify_by_rules(model_year, rules, variants, share=1):
    for rule in rules:
        tested = test_rule(model_year, rule.conditions, share)
        if tested.outcome == Outcome.HOLDS:
            size, ask = size_for(rule.vehicle_class, model_year, variants)
            return Result(rule.vehicle_class, size, ask, Method.RULE, rule=rule)
        if tested.outcome == Outcome.STRADDLES:
            reasons = [f"rule {rule.position} ({rule.name}): {reason}" for reason in tested.reasons]
            kinds = sorted({REVIEW_KINDS[kind] for kind in tested.kinds})
            return Result(method=Method.REVIEW, rule=rule, reasons=reasons, kinds=kinds)
    return Result(method=Method.REVIEW, reasons=["no rule matches"], kinds=[Kind.NO_RULE])


def nearest_classified(year, others):
    """The Result of the nearest year in others, {year: Result}, that has a
    class and was not itself carried; the later of two equally near."""
    found = [
        (abs(other - year), -other, other)
        for other, result in others.items()
        if other != year and result.vehicle_class is not None and not result.in_review and result.method != Method.CARRIED
    ]
    if not found:
        return None, None
    _, _, other = min(found)
    return other, others[other]


def unpublished_window(data_dir=None):
    """How many of the EPA's newest model years a model year must be among
    to take its class from the nearest classified year, from
    data/vehicle-classes.yaml."""
    return int(read_data("vehicle-classes.yaml", data_dir)["rule_settings"]["epa_unpublished_years"])


def not_yet_published(model_years, window):
    """The (model id, year) keys of model years the EPA has not published
    yet: no EPA row, a later year than any the EPA lists for the model, and
    among the EPA's `window` newest model years or after them, such as a 2027
    F-150 that only vPIC lists so far."""
    epa_years = defaultdict(set)
    for model_year in model_years:
        if EPA in model_year.rows:
            epa_years[model_year.vehicle_model.pk].add(model_year.year)
    if not epa_years:
        return set()
    newest = max(max(years) for years in epa_years.values())
    return {
        (model_year.vehicle_model.pk, model_year.year)
        for model_year in model_years
        if EPA not in model_year.rows
        and epa_years.get(model_year.vehicle_model.pk)
        and model_year.year > max(epa_years[model_year.vehicle_model.pk])
        and model_year.year > newest - window
    }


def catalog_model_years(model_ids=None):
    """Every model year in the catalog with its facts: each year a source
    lists, and every year of an owner's model the sources do not list.
    model_ids limits it to those models."""
    models = VehicleModel.objects.in_bulk(model_ids)
    rows = defaultdict(list)
    found = VehicleModelYear.objects.order_by("pk")
    if model_ids is not None:
        found = found.filter(vehicle_model_id__in=model_ids)
    for row in found.iterator(chunk_size=BATCH):
        rows[(row.vehicle_model_id, row.year)].append(row)
    for vehicle_model in models.values():
        if vehicle_model.source == VehicleModel.Source.OWNER and vehicle_model.year_from and vehicle_model.year_to:
            for year in range(vehicle_model.year_from, vehicle_model.year_to + 1):
                rows.setdefault((vehicle_model.pk, year), [])
    return [ModelYear(models[model_id], year, found) for (model_id, year), found in sorted(rows.items())]


def classify_catalog(
    rules=None, overrides=None, model_years=None, share=None, decisions=None, classes=None, window=None, variants=None,
    size_steps=None,
):
    """{(model id, year): (ModelYear, Result)} for the whole catalog. rules,
    overrides and decisions default to those saved; pass a proposed set to
    preview it. classes, {pk: VehicleClass}, puts proposed class settings in
    place of the saved ones, and variants, {class pk: {value: SizeVariant}},
    proposed size variants in place of the active ones. share and window
    default to the settings in data/vehicle-classes.yaml. size_steps, by
    default whether the size-based classes are live, takes the steps of
    classification.sizes.finish() after the rules."""
    from .sizes import attach_box_volumes, classes_by_name, finish
    from .switch import switched

    share = majority_share() if share is None else share
    window = unpublished_window() if window is None else window
    if rules is None:
        rules = ClassificationRule.objects.select_related("vehicle_class")
    if overrides is None:
        overrides = ModelOverride.objects.select_related("vehicle_class", "size_variant")
    if decisions is None:
        decisions = ReviewDecision.objects.select_related("vehicle_class", "size_variant")
    if classes:
        rules, overrides, decisions = (with_classes(found, classes) for found in (rules, overrides, decisions))
    rules = sorted((rule for rule in rules if rule.active), key=lambda rule: (rule.position, rule.pk or 0))
    by_model = defaultdict(list)
    for override in overrides:
        by_model[override.vehicle_model_id].append(override)
    for found in by_model.values():
        # An override for some years beats one for the whole model.
        found.sort(key=lambda override: (override.year_from is None and override.year_to is None, -(override.pk or 0)))
    decided = {(decision.vehicle_model_id, decision.year): decision for decision in decisions}
    variants = active_variants() if variants is None else variants
    model_years = catalog_model_years() if model_years is None else model_years
    if not all(model_year.sized for model_year in model_years):
        attach_box_volumes(model_years)
    pending = not_yet_published(model_years, window)

    results = {}
    for model_year in model_years:
        key = (model_year.vehicle_model.pk, model_year.year)
        overridden = by_model.get(key[0], [])
        if key in pending and key not in decided and not any(found.covers(model_year.year) for found in overridden):
            continue  # Worked out below, from the model's other years.
        results[key] = (model_year, classify_model_year(model_year, rules, overridden, variants, share, decided.get(key)))
    if switched() if size_steps is None else size_steps:
        by_name = classes_by_name()
        for proposed in (classes or {}).values():
            by_name[proposed.name] = proposed
        finish(results, variants, by_name)

    by_model_years = defaultdict(dict)
    for (model_id, year), (_, result) in results.items():
        by_model_years[model_id][year] = result
    for model_year in model_years:
        key = (model_year.vehicle_model.pk, model_year.year)
        if key in results:
            continue
        other, nearest = nearest_classified(model_year.year, by_model_years[key[0]])
        if nearest is None:
            result = classify_by_rules(model_year, rules, variants, share)
        else:
            result = Result(
                nearest.vehicle_class, nearest.size_variant, nearest.ask_size, Method.CARRIED,
                rule=nearest.rule, override=nearest.override, decision=nearest.decision, carried_from=other,
            )
        results[key] = (model_year, result)

    for (model_id, year), (model_year, result) in results.items():
        if result.in_review:
            suggest(result, model_year, by_model_years[model_id], variants)
    return results


def suggest(result, model_year, others, variants):
    """The class the review queue offers to accept with one tap: the class
    of the rule the model year straddles, or of the model's nearest
    classified year, with the size its facts give."""
    if result.rule is not None:
        vehicle_class = result.rule.vehicle_class
    else:
        _, nearest = nearest_classified(model_year.year, others)
        vehicle_class = nearest.vehicle_class if nearest is not None else None
    if vehicle_class is not None:
        result.suggested_class = vehicle_class
        result.suggested_size, result.suggested_ask = size_for(vehicle_class, model_year, variants)


def with_classes(records, classes):
    """Copies of rules, overrides or decisions, each with its vehicle class
    swapped for the proposed one in classes, {pk: VehicleClass}."""
    found = []
    for record in records:
        if record.vehicle_class_id in classes:
            record = copy.copy(record)
            record.vehicle_class = classes[record.vehicle_class_id]
        found.append(record)
    return found


@dataclass
class Change:
    """One model year whose live class or size, or review status, would change."""

    vehicle_model: object
    year: int
    old_class: object
    old_size: str
    new_class: object
    new_size: str
    because: str
    entering_review: bool = False
    leaving_review: bool = False


def size_label(size_variant, ask, vehicle_class):
    if vehicle_class is None:
        return ""
    if ask:
        return "ask"
    return size_variant.label if size_variant is not None else "one price"


def class_label(vehicle_class, size):
    """"Medium (two rows)", or "no class"."""
    if vehicle_class is None:
        return "no class"
    return f"{vehicle_class} ({size})" if size else str(vehicle_class)


def _live(stored):
    """(class, size variant, ask) as stored, or Nones for no live class."""
    if stored is None or stored.vehicle_class_id is None:
        return None, None, False
    return stored.vehicle_class, stored.size_variant, stored.ask_size


def _effective(result, stored):
    """What apply() would store live: a model year sent to the review queue
    keeps the class it had."""
    if result.in_review:
        return _live(stored)
    return result.vehicle_class, result.size_variant, result.ask_size


def changes(results, stored=None):
    """[Change] between saved classifications and new results."""
    if stored is None:
        stored = {
            (row.vehicle_model_id, row.year): row
            for row in ModelYearClassification.objects.select_related("vehicle_class", "size_variant")
        }
    found = []
    for key, (model_year, result) in results.items():
        before = stored.get(key)
        old_class, old_size, old_ask = _live(before)
        new_class, new_size, new_ask = _effective(result, before)
        was_review = bool(before and before.in_review)
        same = (
            getattr(old_class, "pk", None) == getattr(new_class, "pk", None)
            and getattr(old_size, "pk", None) == getattr(new_size, "pk", None)
            and old_ask == new_ask
        )
        if same and was_review == result.in_review:
            continue
        found.append(
            Change(
                model_year.vehicle_model,
                model_year.year,
                old_class,
                size_label(old_size, old_ask, old_class),
                new_class,
                size_label(new_size, new_ask, new_class),
                result.because,
                entering_review=result.in_review and not was_review,
                leaving_review=was_review and not result.in_review,
            )
        )
    return found


def preview(rules=None, overrides=None, **proposed):
    """Every model year whose class or size variant would change, or that
    would enter or leave the review queue, if this set of rules and
    overrides (by default those saved) were applied. Nothing is saved."""
    return changes(classify_catalog(rules, overrides, **proposed))


def change_detail(change):
    detail = f"{class_label(change.old_class, change.old_size)} -> {class_label(change.new_class, change.new_size)}"
    if change.entering_review:
        detail += ", enters the review queue"
    elif change.leaving_review:
        detail += ", leaves the review queue"
    return detail


def fingerprint(found):
    """A short digest of a list of Changes, so a preview the owner confirms
    can be checked against what saving would now do."""
    text = "\n".join(
        sorted(f"{change.vehicle_model.pk} {change.year} {change_detail(change)} {change.because}" for change in found)
    )
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def year_spans(rows):
    """[(vehicle model, year, detail)] -> [(vehicle model, first, last, detail)],
    joining consecutive years of one model with the same detail."""
    spans = []
    current = None
    for vehicle_model, year, detail in sorted(rows, key=lambda row: (row[0].make, row[0].model, row[0].pk, row[1])):
        if current and current[0].pk == vehicle_model.pk and current[3] == detail and current[2] == year - 1:
            current[2] = year
            continue
        if current:
            spans.append(tuple(current))
        current = [vehicle_model, year, year, detail]
    if current:
        spans.append(tuple(current))
    return spans


def years_text(first, last):
    return str(first) if first == last else f"{first}-{last}"


@dataclass
class ChangeGroup:
    """The changes from one class to another, for a preview."""

    old: str
    new: str
    model_years: int
    models: int
    # [(vehicle model, "2019-2024", detail)]
    lines: list


def group_changes(found):
    """[ChangeGroup] by old and new class, largest first. A size or review
    change within a class is its own group."""
    groups = defaultdict(list)
    for change in found:
        old = str(change.old_class) if change.old_class else "no class"
        new = str(change.new_class) if change.new_class else "no class"
        groups[(old, new)].append(change)
    result = []
    for (old, new), changed in groups.items():
        rows = [(change.vehicle_model, change.year, f"{change_detail(change)} ({change.because})") for change in changed]
        lines = [(model, years_text(first, last), detail) for model, first, last, detail in year_spans(rows)]
        result.append(ChangeGroup(old, new, len(changed), len({change.vehicle_model.pk for change in changed}), lines))
    return sorted(result, key=lambda group: (-group.model_years, group.old, group.new))


@transaction.atomic
def record(kind, summary, found=(), user=None, vehicle_model=None):
    """Log one change, with each model year it changed, and clear every
    approval whose year range it altered."""
    change = ClassificationChange.objects.create(
        kind=kind, summary=summary, made_by=user if getattr(user, "pk", None) else None, vehicle_model=vehicle_model
    )
    ClassificationEffect.objects.bulk_create(
        [
            ClassificationEffect(
                change=change,
                vehicle_model=found_change.vehicle_model,
                year=found_change.year,
                before=class_label(found_change.old_class, found_change.old_size)[:120],
                after=change_detail(found_change).split(" -> ", 1)[1][:200],
            )
            for found_change in found
        ],
        batch_size=BATCH,
    )
    # An approval on the approval list whose year range this altered shows again.
    from .approvals import clear_changed

    clear_changed(change)
    return change


@transaction.atomic
def reclassify(kind, summary, user=None, model_ids=None, vehicle_model=None):
    """Apply the saved rules, overrides and decisions, to the whole catalog
    or only to model_ids, and log the change. Returns the Changes."""
    model_years = catalog_model_years(model_ids) if model_ids is not None else None
    results = classify_catalog(model_years=model_years)
    found = changes(results)
    apply(results, partial=model_ids is not None)
    record(kind, summary, found, user=user, vehicle_model=vehicle_model)
    return found


def _stored_values(row, names):
    return {name: getattr(row, f"{name}_id" if name in LINKS else name) for name in names}


@transaction.atomic
def apply(results, partial=False):
    """Save the results as each model year's classification and set each
    model's ask_size. Returns counts. partial results cover only some
    models, so the others' classifications are left alone."""
    now = timezone.now()
    stored = {(row.vehicle_model_id, row.year): row for row in ModelYearClassification.objects.select_related("vehicle_class")}
    created, updated = [], []
    counts = defaultdict(int)
    fields = [
        "vehicle_class", "size_variant", "ask_size", "method", "rule", "override", "decision", "carried_from",
        "in_review", "review_reasons", "review_kinds", "suggested_class", "suggested_size_variant",
        "suggested_ask_size", "classified_at",
    ]
    saved = lambda found: found if found is not None and found.pk else None  # noqa: E731
    for (model_id, year), (_, result) in results.items():
        row = stored.get((model_id, year))
        if row is None:
            row = ModelYearClassification(vehicle_model_id=model_id, year=year)
        values = {
            "in_review": result.in_review,
            "review_reasons": result.reasons,
            "review_kinds": [str(kind) for kind in result.kinds],
            "suggested_class": result.suggested_class,
            "suggested_size_variant": result.suggested_size,
            "suggested_ask_size": result.suggested_ask,
            "rule": saved(result.rule),
            "override": saved(result.override),
            "decision": saved(result.decision),
            "carried_from": result.carried_from,
        }
        if result.in_review:
            # Waits for the owner; one already live keeps its class meanwhile,
            # unless that class is retired.
            if row.vehicle_class_id is None or not row.vehicle_class.active:
                values.update(vehicle_class=None, size_variant=None, ask_size=False, method=Method.REVIEW)
            else:
                for name in ("rule", "override", "decision", "carried_from"):
                    values.pop(name)
        else:
            values.update(
                vehicle_class=result.vehicle_class,
                size_variant=result.size_variant,
                ask_size=result.ask_size,
                method=result.method,
            )
        before = _stored_values(row, values)
        for name, value in values.items():
            setattr(row, name, value)
        after = _stored_values(row, values)
        if row.pk is None:
            row.classified_at = now
            created.append(row)
            counts["model years classified for the first time"] += 1
        elif before != after:
            row.classified_at = now
            updated.append(row)
            counts["model years changed"] += 1
        else:
            counts["model years unchanged"] += 1
    ModelYearClassification.objects.bulk_create(created, batch_size=BATCH)
    ModelYearClassification.objects.bulk_update(updated, fields, batch_size=BATCH)
    # A model year the catalog no longer has, such as one moved to a nameplate, loses its classification.
    model_ids = {model_id for model_id, _ in results}
    gone = [row.pk for key, row in stored.items() if key not in results and (not partial or key[0] in model_ids)]
    ModelYearClassification.objects.filter(pk__in=gone).delete()
    counts["model years no longer in the catalog"] += len(gone)

    asks = set(
        ModelYearClassification.objects.filter(ask_size=True, vehicle_class__isnull=False).values_list(
            "vehicle_model_id", flat=True
        )
    )
    flips = [
        vehicle_model
        for vehicle_model in (VehicleModel.objects.filter(pk__in=model_ids) if partial else VehicleModel.objects.all())
        if vehicle_model.ask_size != (vehicle_model.pk in asks)
    ]
    for vehicle_model in flips:
        vehicle_model.ask_size = not vehicle_model.ask_size
    if flips:
        bulk_update_with_history(
            flips, VehicleModel, ["ask_size"], batch_size=BATCH, default_change_reason="classify_vehicles"
        )
    counts["models whose ask_size changed"] = len(flips)
    from .sizes import save_box_volumes

    counts.update(save_box_volumes([model_year for model_year, _ in results.values()], partial=partial))
    counts["model years in the review queue"] = ModelYearClassification.objects.filter(in_review=True).count()
    return dict(counts)
