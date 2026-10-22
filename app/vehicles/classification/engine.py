"""Classifying the whole catalog, one model year at a time.

For each model year: a model override covering the year wins; otherwise the
active rules are tried in order and the first that holds gives the vehicle
class. A model year that no rule holds for, or whose facts straddle a rule
or whose sources disagree about one, goes to the review queue instead of
going live. The size variant is then set from the facts the class's size
variant measures, or left for the customer to answer.

preview() works all of this out for a proposed set of rules and overrides
without saving anything; apply() saves it as each model year's
ModelYearClassification.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from simple_history.utils import bulk_update_with_history

from vehicles.models import (
    ClassificationRule,
    ModelOverride,
    ModelYearClassification,
    SizeVariant,
    VehicleClass,
    VehicleModel,
    VehicleModelYear,
)

from .rules import ModelYear, Outcome, parse_share, test_rule
from .seed import read_data

Method = ModelYearClassification.Method
Measures = VehicleClass.Measures
BATCH = 2000
LINKS = ("vehicle_class", "size_variant", "rule", "override")

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
    reasons: list = field(default_factory=list)

    @property
    def in_review(self):
        return self.method == Method.REVIEW

    @property
    def because(self):
        """What gave the answer, for reports."""
        if self.override is not None:
            return f"model override ({self.override.note or 'no note'})"
        if self.rule is not None:
            return f"rule {self.rule.position}: {self.rule.name}"
        return "review queue: " + "; ".join(self.reasons)


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
    return {None}


def size_for(vehicle_class, model_year, variants):
    """(size variant, ask) for a model year in this class. A class with no
    size variants has one price; one with a single size variant, such as
    Fullsize SUVs & Minivans, always has it. Otherwise the facts must give
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


def classify_model_year(model_year, rules, overrides, variants, share=1):
    """The Result for one model year: rules sorted by position, overrides
    those of its model."""
    override = next((found for found in overrides if found.covers(model_year.year)), None)
    if override is not None:
        if override.size_variant is not None:
            size, ask = override.size_variant, False
        elif override.ask_size and variants.get(override.vehicle_class.pk):
            size, ask = None, True
        else:
            size, ask = size_for(override.vehicle_class, model_year, variants)
        return Result(override.vehicle_class, size, ask, Method.OVERRIDE, override=override)
    for rule in rules:
        tested = test_rule(model_year, rule.conditions, share)
        if tested.outcome == Outcome.HOLDS:
            size, ask = size_for(rule.vehicle_class, model_year, variants)
            return Result(rule.vehicle_class, size, ask, Method.RULE, rule=rule)
        if tested.outcome == Outcome.STRADDLES:
            reasons = [f"rule {rule.position} ({rule.name}): {reason}" for reason in tested.reasons]
            return Result(method=Method.REVIEW, rule=rule, reasons=reasons)
    return Result(method=Method.REVIEW, reasons=["no rule matches"])


def catalog_model_years():
    """Every model year in the catalog with its facts: each year a source
    lists, and every year of an owner's model the sources do not list."""
    models = VehicleModel.objects.in_bulk()
    rows = defaultdict(list)
    for row in VehicleModelYear.objects.order_by("pk").iterator(chunk_size=BATCH):
        rows[(row.vehicle_model_id, row.year)].append(row)
    for vehicle_model in models.values():
        if vehicle_model.source == VehicleModel.Source.OWNER and vehicle_model.year_from and vehicle_model.year_to:
            for year in range(vehicle_model.year_from, vehicle_model.year_to + 1):
                rows.setdefault((vehicle_model.pk, year), [])
    return [ModelYear(models[model_id], year, found) for (model_id, year), found in sorted(rows.items())]


def classify_catalog(rules=None, overrides=None, model_years=None, share=None):
    """{(model id, year): (ModelYear, Result)} for the whole catalog. rules
    and overrides default to those saved; pass a proposed set to preview it.
    share defaults to the majority share in data/vehicle-classes.yaml."""
    share = majority_share() if share is None else share
    if rules is None:
        rules = ClassificationRule.objects.select_related("vehicle_class")
    if overrides is None:
        overrides = ModelOverride.objects.select_related("vehicle_class", "size_variant")
    rules = sorted((rule for rule in rules if rule.active), key=lambda rule: (rule.position, rule.pk or 0))
    by_model = defaultdict(list)
    for override in overrides:
        by_model[override.vehicle_model_id].append(override)
    for found in by_model.values():
        # An override for some years beats one for the whole model.
        found.sort(key=lambda override: (override.year_from is None and override.year_to is None, -(override.pk or 0)))
    variants = active_variants()
    model_years = catalog_model_years() if model_years is None else model_years
    return {
        (model_year.vehicle_model.pk, model_year.year): (
            model_year,
            classify_model_year(model_year, rules, by_model.get(model_year.vehicle_model.pk, []), variants, share),
        )
        for model_year in model_years
    }


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


def preview(rules=None, overrides=None):
    """Every model year whose class or size variant would change, or that
    would enter or leave the review queue, if this set of rules and
    overrides (by default those saved) were applied. Nothing is saved."""
    return changes(classify_catalog(rules, overrides))


def _stored_values(row, names):
    return {name: getattr(row, f"{name}_id" if name in LINKS else name) for name in names}


@transaction.atomic
def apply(results):
    """Save the results as each model year's classification and set each
    model's ask_size. Returns counts."""
    now = timezone.now()
    stored = {(row.vehicle_model_id, row.year): row for row in ModelYearClassification.objects.all()}
    created, updated = [], []
    counts = defaultdict(int)
    fields = [
        "vehicle_class", "size_variant", "ask_size", "method", "rule", "override", "in_review", "review_reasons",
        "classified_at",
    ]
    for (model_id, year), (_, result) in results.items():
        row = stored.get((model_id, year))
        if row is None:
            row = ModelYearClassification(vehicle_model_id=model_id, year=year)
        values = {
            "in_review": result.in_review,
            "review_reasons": result.reasons,
            "rule": result.rule if result.rule is not None and result.rule.pk else None,
            "override": result.override if result.override is not None and result.override.pk else None,
        }
        if result.in_review:
            # Waits for the owner; one already live keeps its class meanwhile.
            if row.vehicle_class_id is None:
                values.update(vehicle_class=None, size_variant=None, ask_size=False, method=Method.REVIEW)
            else:
                values.pop("rule")
                values.pop("override")
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
    gone = [row.pk for key, row in stored.items() if key not in results]
    ModelYearClassification.objects.filter(pk__in=gone).delete()
    counts["model years no longer in the catalog"] += len(gone)

    asks = set(
        ModelYearClassification.objects.filter(ask_size=True, vehicle_class__isnull=False).values_list(
            "vehicle_model_id", flat=True
        )
    )
    flips = [
        vehicle_model
        for vehicle_model in VehicleModel.objects.all()
        if vehicle_model.ask_size != (vehicle_model.pk in asks)
    ]
    for vehicle_model in flips:
        vehicle_model.ask_size = not vehicle_model.ask_size
    if flips:
        bulk_update_with_history(
            flips, VehicleModel, ["ask_size"], batch_size=BATCH, default_change_reason="classify_vehicles"
        )
    counts["models whose ask_size changed"] = len(flips)
    counts["model years in the review queue"] = ModelYearClassification.objects.filter(in_review=True).count()
    return dict(counts)
