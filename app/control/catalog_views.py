"""The vehicle catalog screens (decision 0076): looking a vehicle up by year,
make and model, with its class, facts, how the class was reached, a test
price, its overrides and history; the classification rules; the vehicle
class settings; and the review queue.

Every signed-in user can look; only a manager changes anything. A change to
a rule or a class setting that reaches the catalog is previewed first and
applied only when the manager confirms it (engine.preview); the others reach
one model, or the model years picked in the review queue, and apply at once.
"""

from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html_join
from django.views.decorators.http import require_POST, require_safe

from pricebook.models import PricebookVersion
from pricebook.pricing import PricingError, price_job
from staff.authorization import user_is_manager
from vehicles.classification import owner
from vehicles.classification.engine import (
    because,
    class_label,
    fingerprint,
    group_changes,
    preview,
    record,
    size_label,
    year_spans,
    years_text,
)
from vehicles.classification.lookup import find_model, first_catalog_year, stored_classification
from vehicles.classification.rules import FACTS, NONE, condition_errors, describe_conditions, in_order
from vehicles.classification.seed import rule_now
from vehicles.models import (
    ClassificationChange,
    ClassificationEffect,
    ClassificationRule,
    ModelOverride,
    ModelYearClassification,
    ReviewDecision,
    Vehicle,
    VehicleClass,
    VehicleModel,
    VehicleModelYear,
)

from .forms import (
    ModelOverrideForm,
    RuleForm,
    TestPriceForm,
    ThirdRowForm,
    VehicleClassSettingsForm,
    VehicleOverrideForm,
    size_choices,
)

Method = ModelYearClassification.Method
ReviewKind = ModelYearClassification.ReviewKind
QUEUE_PAGE = 50
# A preview lists at most this many lines in each group; the counts are always whole.
PREVIEW_LINES = 300
BLANK_CONDITION_ROWS = 2


def require_manager(request):
    if not user_is_manager(request.user):
        raise PermissionDenied("Only a manager can change how vehicles are classified.")


def queue_count():
    return ModelYearClassification.objects.filter(in_review=True).count()


def nav_context(request, here):
    return {"catalog_here": here, "queue_count": queue_count(), "can_edit": user_is_manager(request.user)}


# Facts, as the catalog screen and the review queue show them.

LISTED = [
    ("epa_size_classes", "EPA size class"), ("body_styles", "Body style"), ("drives", "Drive"),
    ("cab_styles", "Cab style"), ("seat_rows", "Seat rows"), ("source_vehicle_types", "vPIC vehicle type"),
]
MEASURED = [
    ("curb_weight", "Curb weight", "lb"), ("gvwr", "GVWR", "lb"), ("length", "Length", "in"), ("width", "Width", "in"),
    ("height", "Height", "in"), ("wheelbase", "Wheelbase", "in"), ("passenger_volume", "Passenger volume", "cu ft"),
    ("luggage_volume", "Luggage volume", "cu ft"),
]
# The facts the review queue shows for each model year.
QUEUE_FACTS = {"epa_size_classes", "body_styles", "cab_styles", "seat_rows", "source_vehicle_types", "curb_weight", "length"}


def number(value):
    if isinstance(value, int):
        return f"{value:,}"
    return f"{Decimal(value):,.1f}".removesuffix(".0")


def fact_lines(row, only=None):
    """[(label, text)] for each fact the record gives."""
    lines = []
    for field, label in LISTED:
        values = getattr(row, field)
        if values and (only is None or field in only):
            lines.append((label, ", ".join(str(value) for value in values)))
    for field, label, unit in MEASURED:
        low, high = getattr(row, f"{field}_min"), getattr(row, f"{field}_max")
        if low is None or (only is not None and field not in only):
            continue
        text = number(low) if low == high else f"{number(low)} to {number(high)}"
        lines.append((label, f"{text} {unit}"))
    return lines


def size_text(found):
    """The size of a stored classification or lookup result, in words."""
    if found.vehicle_class is None:
        return ""
    if getattr(found, "ask_size", False) or getattr(found, "question", None):
        return "asked"
    return found.size_variant.label if found.size_variant else "one price"


# Looking a vehicle up.


def parse_int(text):
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def catalog_years():
    found = ModelYearClassification.objects.order_by("-year").values_list("year", flat=True).distinct()
    return list(found)


@require_safe
def catalog(request):
    """Pick year, make and model, and see the class, size, price basis, the
    facts from each source, how the class was reached, a test price, the
    model's overrides and its history."""
    year = parse_int(request.GET.get("year"))
    make, model_name = request.GET.get("make", "").strip(), request.GET.get("model", "").strip()
    context = {**nav_context(request, "search"), "year": year, "make": make, "model_name": model_name, "years": catalog_years()}
    vehicle_model = None
    if request.GET.get("model_id"):
        vehicle_model = VehicleModel.objects.filter(pk=parse_int(request.GET["model_id"])).first()
        if vehicle_model is None:
            raise Http404("No such model.")
        context["make"], context["model_name"] = vehicle_model.make, vehicle_model.model
    elif year and make and model_name:
        if year < first_catalog_year():
            context["not_found"] = f"The catalog starts in {first_catalog_year()}. Older vehicles choose from the photo cards."
        else:
            vehicle_model = find_model(year, make, model_name)
            if vehicle_model is None:
                context["not_found"] = f"No {year} {make} {model_name} in the catalog. The customer chooses from the photo cards."
    if year:
        context["makes"] = makes_for(year)
        if make:
            context["models"] = models_for(year, make)
    if vehicle_model is not None:
        context.update(model_context(request, vehicle_model, year))
    return render(request, "control/catalog.html", context)


def makes_for(year):
    return sorted(
        set(VehicleModelYear.objects.filter(year=year).values_list("vehicle_model__make", flat=True).distinct())
        | set(ModelYearClassification.objects.filter(year=year).values_list("vehicle_model__make", flat=True).distinct())
    )


def models_for(year, make):
    found = ModelYearClassification.objects.filter(year=year, vehicle_model__make__iexact=make)
    return sorted(set(found.values_list("vehicle_model__model", flat=True)))


def options(values):
    return HttpResponse(format_html_join("", '<option value="{}"></option>', ((value,) for value in values)))


@require_safe
def catalog_makes(request):
    """The makes of a model year, for the make list (htmx)."""
    year = parse_int(request.GET.get("year"))
    return options(makes_for(year) if year else [])


@require_safe
def catalog_models(request):
    """The models of a make in a model year, for the model list (htmx)."""
    year, make = parse_int(request.GET.get("year")), request.GET.get("make", "").strip()
    return options(models_for(year, make) if year and make else [])


def model_years(vehicle_model):
    """Each classified year of the model, newest first, with its class and how."""
    rows = []
    stored = ModelYearClassification.objects.filter(vehicle_model=vehicle_model).select_related(
        "vehicle_class", "size_variant", "rule", "override", "decision"
    )
    for found in sorted(stored, key=lambda found: -found.year):
        rows.append({"year": found.year, "found": found, "label": class_label(found.vehicle_class, size_text(found)), "how": because(found)})
    return rows


def model_history(vehicle_model):
    """Every change that reached the model, newest first, each with the
    model's years it changed."""
    changes = list(
        ClassificationChange.objects.filter(Q(vehicle_model=vehicle_model) | Q(effects__vehicle_model=vehicle_model))
        .distinct()
        .select_related("made_by")[:50]
    )
    effects = defaultdict(list)
    for effect in ClassificationEffect.objects.filter(change__in=changes, vehicle_model=vehicle_model):
        effects[effect.change_id].append((vehicle_model, effect.year, f"{effect.before} -> {effect.after}"))
    return [
        {"change": change, "lines": [(years_text(first, last), detail) for _, first, last, detail in year_spans(effects[change.pk])]}
        for change in changes
    ]


def model_context(request, vehicle_model, year):
    years = model_years(vehicle_model)
    if year is None or year not in {row["year"] for row in years}:
        requested = year
        year = years[0]["year"] if years else None
        if requested is not None and year is not None:
            messages.info(request, f"The catalog has no {requested} {vehicle_model.make} {vehicle_model.model}; showing {year}.")
    result = stored_classification(vehicle_model, year) if year else None
    sources = [
        {"source": row.get_source_display(), "lines": fact_lines(row), "last_seen": row.last_seen, "owner": row.source == VehicleModelYear.Source.OWNER}
        for row in VehicleModelYear.objects.filter(vehicle_model=vehicle_model, year=year).order_by("source")
    ]
    initial = {"vehicle_class": getattr(result, "vehicle_class", None), "year_from": year, "year_to": year}
    price_initial = {"vehicle_class": getattr(result, "vehicle_class", None), "size_variant": getattr(result, "size_variant", None), "condition_level": 1}
    return {
        "vehicle_model": vehicle_model,
        "year": year,
        "result": result,
        "result_size": size_text(result) if result and result.vehicle_class else "",
        "model_years": years,
        "sources": sources,
        "overrides": vehicle_model.overrides.select_related("vehicle_class", "size_variant", "set_by").order_by("year_from", "year_to"),
        "decisions": vehicle_model.review_decisions.select_related("vehicle_class", "size_variant", "decided_by").order_by("-year"),
        "override_form": ModelOverrideForm(initial=initial, auto_id="override-%s"),
        "third_row_form": ThirdRowForm(initial={"year_from": year, "year_to": year}, auto_id="third-row-%s"),
        "price_form": TestPriceForm(initial=price_initial, auto_id="price-%s"),
        "history": model_history(vehicle_model),
        "vehicles": Vehicle.objects.filter(vehicle_model=vehicle_model).exclude(class_override_at=None).select_related("customer", "vehicle_class", "size_variant"),
    }


def model_url(vehicle_model, year=None):
    url = f"{reverse('catalog')}?model_id={vehicle_model.pk}"
    return f"{url}&year={year}" if year else url


def changed_message(found):
    if not found:
        return "No model year changed class or size."
    return f"{len(found):,} model year{'s' if len(found) != 1 else ''} changed class, size or review status."


@require_POST
def catalog_price(request):
    """A test price for a service, class, size and condition level, from
    the pricebook in effect today (htmx)."""
    form = TestPriceForm(request.POST, auto_id="price-%s")
    context = {"errors": [], "job": None}
    if not form.is_valid():
        context["errors"] = [error for errors in form.errors.values() for error in errors]
    else:
        data = form.cleaned_data
        size = data.get("size_variant")
        if size is not None and size.vehicle_class_id != data["vehicle_class"].pk:
            context["errors"] = ["Pick a size of the vehicle class above, or leave it blank."]
        else:
            try:
                job = price_job(
                    data["service"], data["vehicle_class"], size_variant=size,
                    condition_level=data["condition_level"] if data["service"].condition_applies else None,
                )
            except PricingError as error:
                context["errors"] = [str(error)]
            else:
                context.update(job=job, stay=job.time_on_site, test_price=True)
    return render(request, "control/_live_price.html", context)


@require_POST
def model_override(request, pk):
    require_manager(request)
    vehicle_model = get_object_or_404(VehicleModel, pk=pk)
    form = ModelOverrideForm(request.POST, auto_id="override-%s")
    year = parse_int(request.POST.get("year"))
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, f"Override not saved: {error}")
        return redirect(model_url(vehicle_model, year))
    data = form.cleaned_data
    found = owner.set_override(
        vehicle_model, request.user, data["vehicle_class"], data["size_variant"], data["ask_size"],
        data["year_from"], data["year_to"], data["note"].strip(),
    )
    messages.success(request, f"Override saved. {changed_message(found)}")
    return redirect(model_url(vehicle_model, year))


@require_POST
def override_clear(request, pk):
    require_manager(request)
    override = get_object_or_404(ModelOverride.objects.select_related("vehicle_model", "vehicle_class", "size_variant"), pk=pk)
    vehicle_model = override.vehicle_model
    found = owner.clear_override(override, request.user)
    messages.success(request, f"Override cleared. {changed_message(found)}")
    return redirect(model_url(vehicle_model, parse_int(request.POST.get("year"))))


@require_POST
def third_row(request, pk):
    require_manager(request)
    vehicle_model = get_object_or_404(VehicleModel, pk=pk)
    form = ThirdRowForm(request.POST, auto_id="third-row-%s")
    year = parse_int(request.POST.get("year"))
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, f"Third-row flag not saved: {error}")
        return redirect(model_url(vehicle_model, year))
    data = form.cleaned_data
    found = owner.set_third_row(vehicle_model, request.user, data["flag"], data["year_from"], data["year_to"], data["note"].strip())
    messages.success(request, f"Third-row flag saved. {changed_message(found)}")
    return redirect(model_url(vehicle_model, year))


@require_POST
def decision_clear(request, pk):
    require_manager(request)
    decision = get_object_or_404(ReviewDecision.objects.select_related("vehicle_model", "vehicle_class", "size_variant"), pk=pk)
    vehicle_model = decision.vehicle_model
    found = owner.clear_decision(decision, request.user)
    messages.success(request, f"Review queue decision cleared. {changed_message(found)}")
    return redirect(model_url(vehicle_model, parse_int(request.POST.get("year"))))


# A customer's vehicle.


@require_POST
def vehicle_override(request, pk):
    """Set or clear one customer's vehicle's own class, from its edit screen."""
    require_manager(request)
    vehicle = get_object_or_404(Vehicle.objects.select_related("customer", "vehicle_model"), pk=pk)
    if "clear" in request.POST:
        owner.override_vehicle(vehicle, request.user, clear=True)
        messages.success(request, f"{vehicle} goes by the catalog's class again.")
        return redirect("vehicle-edit", pk=pk)
    form = VehicleOverrideForm(request.POST, prefix="override")
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, f"Class override not saved: {error}")
        return redirect("vehicle-edit", pk=pk)
    data = form.cleaned_data
    owner.override_vehicle(vehicle, request.user, data["vehicle_class"], data["size_variant"], data["note"].strip())
    messages.success(request, f"{vehicle} now has its own class: {class_label(data['vehicle_class'], data['size_variant'].label if data['size_variant'] else '')}.")
    return redirect("vehicle-edit", pk=pk)


# Previews.


def preview_context(found, summary, posted, action, back, stale=False):
    """What the preview page shows: the changes grouped by old and new
    class, and the form that confirms them."""
    groups = group_changes(found)
    for group in groups:
        group.more = max(len(group.lines) - PREVIEW_LINES, 0)
        group.lines = group.lines[:PREVIEW_LINES]
    return {
        "summary": summary,
        "groups": groups,
        "count": len(found),
        "models": len({change.vehicle_model.pk for change in found}),
        "entering": sum(1 for change in found if change.entering_review),
        "leaving": sum(1 for change in found if change.leaving_review),
        "posted": [(name, value) for name, value in posted if name not in ("csrfmiddlewaretoken", "confirm", "fingerprint", "back")],
        "fingerprint": fingerprint(found),
        "action": action,
        "back": back,
        "stale": stale,
    }


def posted_items(request):
    return [(name, value) for name in request.POST for value in request.POST.getlist(name)]


# Rules.


def rule_rows(rules):
    rows = []
    for rule in rules:
        launch = rule.seeded_from is not None
        rows.append({
            "rule": rule,
            "words": f"{describe_conditions(rule.conditions)} → {rule.vehicle_class}",
            "launch": launch,
            "edited": launch and rule_now(rule) != rule.seeded_from,
        })
    return rows


@require_safe
def rules(request):
    """The ordered rules, in plain words."""
    found = ClassificationRule.objects.select_related("vehicle_class").order_by("position", "pk")
    context = {
        **nav_context(request, "rules"),
        "rows": rule_rows(found),
        "changes": ClassificationChange.objects.filter(
            kind__in=[ClassificationChange.Kind.RULE, ClassificationChange.Kind.CLASS_SETTING, ClassificationChange.Kind.RUN]
        ).select_related("made_by")[:20],
    }
    return render(request, "control/rules.html", context)


def condition_rows(post):
    """The condition rows as posted: fact, values (one per line), and the
    two ends of a range."""
    try:
        count = min(max(int(post.get("condition_rows", 0)), 0), 60)
    except ValueError:
        count = 0
    return [
        {
            "fact": post.get(f"fact-{index}", "").strip(),
            "values": post.get(f"values-{index}", ""),
            "low": post.get(f"low-{index}", "").strip(),
            "high": post.get(f"high-{index}", "").strip(),
        }
        for index in range(count)
    ]


def rows_from(conditions):
    """Condition rows for the form from a rule's conditions."""
    rows = []
    for key, value in in_order(conditions or {}):
        fact = FACTS.get(key)
        row = {"fact": key, "values": "", "low": "", "high": ""}
        if fact is not None and fact.kind in ("year", "measured") and isinstance(value, dict):
            low, high = ("from", "to") if fact.kind == "year" else ("over", "up_to")
            row["low"], row["high"] = value.get(low, ""), value.get(high, "")
        elif isinstance(value, list):
            row["values"] = "\n".join(str(found) for found in value)
        rows.append(row)
    return rows


def as_number(text, label):
    try:
        value = Decimal(text.replace(",", ""))
    except ArithmeticError:
        raise ValueError(f"{label}: enter a number.") from None
    return int(value) if value == value.to_integral_value() else float(value)


def conditions_from(rows):
    """(conditions, errors) from the condition rows. A row with no fact is left out."""
    conditions, errors = {}, []
    for row in rows:
        key = row["fact"]
        if not key:
            continue
        fact = FACTS.get(key)
        if fact is None:
            errors.append(f"{key} is not a fact a rule can use.")
            continue
        if key in conditions:
            errors.append(f"The {fact.label} condition is given twice; combine its values in one row.")
            continue
        if fact.kind in ("year", "measured"):
            ends = ("from", "to") if fact.kind == "year" else ("over", "up_to")
            bounds = {}
            for end, text in zip(ends, (row["low"], row["high"]), strict=True):
                if str(text).strip():
                    try:
                        bounds[end] = as_number(str(text), fact.label)
                    except ValueError as error:
                        errors.append(str(error))
            if not bounds:
                errors.append(f"The {fact.label} condition needs at least one end of the range.")
                continue
            conditions[key] = bounds
            continue
        values = [line.strip() for line in row["values"].splitlines() if line.strip()]
        if not values:
            errors.append(f"The {fact.label} condition needs at least one value, one per line.")
            continue
        if key == "seat_rows":
            values = [int(value) if value.isdigit() else value.lower() for value in values]
        elif key == "vehicle_type":
            values = [value.lower() for value in values]
        else:
            values = [NONE if value.lower() == NONE else value for value in values]
        conditions[key] = values
    if not errors:
        errors = condition_errors(conditions)
    return conditions, errors


def rule_form_context(request, form, rows, rule, errors=()):
    return {
        **nav_context(request, "rules"),
        "form": form,
        "rule": rule,
        "rows": rows + [{"fact": "", "values": "", "low": "", "high": ""}] * BLANK_CONDITION_ROWS,
        "facts": FACTS.values(),
        "condition_errors": errors,
    }


def rule_form(request, pk=None):
    """Add or edit a rule. Saving shows the preview first; nothing changes
    until the manager confirms it."""
    rule = get_object_or_404(ClassificationRule.objects.select_related("vehicle_class"), pk=pk) if pk else None
    if request.method != "POST":
        if rule is None:
            last = ClassificationRule.objects.order_by("-position").first()
            initial = {"position": (last.position if last else 0) + owner.POSITION_STEP, "active": True}
        else:
            initial = {}
        form = RuleForm(instance=rule, initial=initial)
        return render(request, "control/rule_form.html", rule_form_context(request, form, rows_from(rule.conditions if rule else {}), rule))
    require_manager(request)
    # The form changes the record it is given, so it gets a copy, and rule stays as saved.
    form = RuleForm(request.POST, instance=ClassificationRule.objects.get(pk=pk) if rule else ClassificationRule())
    rows = condition_rows(request.POST)
    conditions, errors = conditions_from(rows)
    if "back" in request.POST or not form.is_valid() or errors:
        filled = [row for row in rows if row["fact"]]
        return render(request, "control/rule_form.html", rule_form_context(request, form, filled, rule, errors))
    proposed = form.save(commit=False)
    proposed.conditions = conditions
    try:
        proposed.full_clean()
    except ValidationError as error:
        filled = [row for row in rows if row["fact"]]
        return render(request, "control/rule_form.html", rule_form_context(request, form, filled, rule, error.messages))
    words = f"{describe_conditions(conditions)} → {proposed.vehicle_class}"
    if rule is None:
        summary = f"Add rule {proposed.position} ({proposed.name}): {words}"
    else:
        summary = f"Change {owner.rule_label(rule)} to {proposed.position} ({proposed.name}): {words}"
        if not proposed.active:
            summary += " (disabled)"
    action = reverse("rule-edit", args=[rule.pk]) if rule else reverse("rule-new")
    return confirm_or_preview(request, [proposed], summary, action, back_to_form=True)


@require_POST
def rule_action(request, pk):
    """Move a rule up or down, or disable or enable it, with the same preview."""
    require_manager(request)
    rule = get_object_or_404(ClassificationRule.objects.select_related("vehicle_class"), pk=pk)
    action = request.POST.get("action")
    if action in ("up", "down"):
        changed = owner.moved(rule, action)
        if not changed:
            messages.info(request, f"{owner.rule_label(rule).capitalize()} is already {'first' if action == 'up' else 'last'}.")
            return redirect("rules")
        new_position = next((found.position for found in changed if found.pk == rule.pk), rule.position)
        summary = f"Move {owner.rule_label(rule)} {action}, to position {new_position}"
        if len(changed) > 1:
            summary += f"; the rules are numbered again in steps of {owner.POSITION_STEP}"
    elif action == "toggle":
        copied = ClassificationRule.objects.select_related("vehicle_class").get(pk=pk)
        copied.active = not rule.active
        changed = [copied]
        summary = f"{'Enable' if copied.active else 'Disable'} {owner.rule_label(rule)}"
    else:
        raise Http404("No such action.")
    return confirm_or_preview(request, changed, summary, reverse("rule-action", args=[pk]))


def confirm_or_preview(request, changed, summary, action, back_to_form=False):
    """Show the preview of these rule changes, or, when the manager confirms
    the preview they saw, save and apply them."""
    found = preview(owner.proposed_rules(changed))
    if "confirm" in request.POST:
        if request.POST.get("fingerprint") == fingerprint(found):
            applied = owner.save_rules(changed, summary, request.user)
            messages.success(request, f"Saved: {summary}. {changed_message(applied)}")
            return redirect("rules")
        stale = True
    else:
        stale = False
    context = {
        **nav_context(request, "rules"),
        **preview_context(found, summary, posted_items(request), action, reverse("rules"), stale),
        "back_to_form": back_to_form,
    }
    return render(request, "control/classification_preview.html", context)


# Class settings.


@require_safe
def vehicle_classes(request):
    live = dict(
        ModelYearClassification.objects.exclude(vehicle_class=None).values_list("vehicle_class").annotate(count=Count("pk"))
    )
    found = VehicleClass.objects.prefetch_related("size_variants")
    rows = [{"vehicle_class": vehicle_class, "model_years": live.get(vehicle_class.pk, 0)} for vehicle_class in found]
    return render(request, "control/vehicle_classes.html", {**nav_context(request, "classes"), "rows": rows})


def booking_lines(vehicle_class):
    """The live model years of a class, joined into year ranges, for the
    preview of a change to how the class is booked."""
    stored = ModelYearClassification.objects.filter(vehicle_class=vehicle_class).select_related("vehicle_model")
    rows = [(found.vehicle_model, found.year, "") for found in stored]
    return [(model, years_text(first, last)) for model, first, last, _ in year_spans(rows)]


def vehicle_class_form(request, pk):
    """Edit a class's settings. A change to what its size variant measures,
    or to whether it is booked online, is previewed first."""
    vehicle_class = get_object_or_404(VehicleClass, pk=pk)
    context = nav_context(request, "classes")
    if request.method != "POST":
        context.update(form=VehicleClassSettingsForm(instance=vehicle_class), vehicle_class=vehicle_class)
        return render(request, "control/vehicle_class_form.html", context)
    require_manager(request)
    saved = VehicleClass.objects.get(pk=pk)
    form = VehicleClassSettingsForm(request.POST, instance=vehicle_class)
    if "back" in request.POST or not form.is_valid():
        context.update(form=form, vehicle_class=saved)
        return render(request, "control/vehicle_class_form.html", context)
    proposed = form.save(commit=False)
    changed = [name for name in form.fields if getattr(proposed, name) != getattr(saved, name)]
    if not changed:
        messages.info(request, f"Nothing changed for {saved}.")
        return redirect("vehicle-classes")
    summary = f"{saved}: " + "; ".join(
        f"{proposed._meta.get_field(name).verbose_name} from {display(saved, name)} to {display(proposed, name)}" for name in changed
    )
    measures = "size_variant_measures" in changed
    booking = "booking" in changed
    if not measures and not booking:
        proposed.save()
        record(ClassificationChange.Kind.CLASS_SETTING, summary, user=request.user)
        messages.success(request, f"Saved: {summary}.")
        return redirect("vehicle-classes")
    found = preview(classes={proposed.pk: proposed}) if measures else []
    if "confirm" in request.POST and request.POST.get("fingerprint") == fingerprint(found):
        if measures:
            applied = owner.save_class(proposed, summary, request.user)
            messages.success(request, f"Saved: {summary}. {changed_message(applied)}")
        else:
            proposed.save()
            record(ClassificationChange.Kind.CLASS_SETTING, summary, user=request.user)
            messages.success(request, f"Saved: {summary}.")
        return redirect("vehicle-classes")
    context.update(preview_context(found, summary, posted_items(request), reverse("vehicle-class", args=[pk]), reverse("vehicle-classes"), "confirm" in request.POST))
    context["back_to_form"] = True
    if booking:
        lines = booking_lines(saved)
        context["booking"] = {
            "to": proposed.get_booking_display(),
            "count": ModelYearClassification.objects.filter(vehicle_class=saved).count(),
            "lines": lines[:PREVIEW_LINES],
            "more": max(len(lines) - PREVIEW_LINES, 0),
            "quote": proposed.booking == VehicleClass.Booking.QUOTE,
        }
    context["measures"] = measures
    return render(request, "control/classification_preview.html", context)


def display(instance, name):
    shown = getattr(instance, f"get_{name}_display", None)
    value = shown() if shown else getattr(instance, name)
    return f'"{value}"' if value else "nothing"


# The review queue.


def queue_items(page_items):
    """The facts that matter for each model year on the page."""
    keys = {(found.vehicle_model_id, found.year) for found in page_items}
    rows = defaultdict(list)
    for row in VehicleModelYear.objects.filter(
        vehicle_model_id__in={key[0] for key in keys}, year__in={key[1] for key in keys}
    ).order_by("source"):
        if (row.vehicle_model_id, row.year) in keys:
            lines = fact_lines(row, QUEUE_FACTS)
            if lines:
                rows[(row.vehicle_model_id, row.year)].append((row.get_source_display(), lines))
    items = []
    for found in page_items:
        suggestion = None
        if found.suggested_class is not None:
            size = "asked" if found.suggested_ask_size else size_label(found.suggested_size_variant, False, found.suggested_class)
            suggestion = class_label(found.suggested_class, size)
        items.append({
            "found": found,
            "facts": rows.get((found.vehicle_model_id, found.year), []),
            "suggestion": suggestion,
            "live": class_label(found.vehicle_class, size_text(found)) if found.vehicle_class else "",
        })
    return items


@require_safe
def review_queue(request):
    """The model years waiting for the owner, newest model years first,
    filtered by year and by reason."""
    waiting = ModelYearClassification.objects.filter(in_review=True)
    year, kind = parse_int(request.GET.get("year")), request.GET.get("reason", "")
    found = waiting
    if year:
        found = found.filter(year=year)
    if kind in ReviewKind.values:
        found = found.filter(review_kinds__contains=[kind])
    found = found.select_related("vehicle_model", "vehicle_class", "size_variant", "suggested_class", "suggested_size_variant").order_by(
        "-year", "vehicle_model__make", "vehicle_model__model", "vehicle_model_id"
    )
    page = Paginator(found, QUEUE_PAGE).get_page(request.GET.get("page"))
    classes = VehicleClass.objects.offered()
    context = {
        **nav_context(request, "queue"),
        "page": page,
        "items": queue_items(page.object_list),
        "total": found.count(),
        "year": year,
        "reason": kind,
        "reasons": ReviewKind.choices,
        "years": list(waiting.order_by("-year").values_list("year", flat=True).distinct()),
        "classes": classes,
        "sizes": size_choices(classes),
        "here": request.get_full_path(),
    }
    return render(request, "control/review_queue.html", context)


@require_POST
def review_act(request):
    """One tap on a model year (accept its suggestion, pick another class
    and size, or the photo cards), or the same for every model year picked."""
    require_manager(request)
    action, _, target = request.POST.get("do", "").partition(":")
    note = request.POST.get("note", "").strip()
    if target:
        picked = ModelYearClassification.objects.filter(pk=parse_int(target), in_review=True)
    else:
        picked = ModelYearClassification.objects.filter(pk__in=[parse_int(pk) for pk in request.POST.getlist("selected")], in_review=True)
    picked = list(picked.select_related("vehicle_model", "suggested_class", "suggested_size_variant"))
    back = request.POST.get("next", "")
    back = back if back.startswith(reverse("review-queue")) else reverse("review-queue")
    if not picked:
        messages.info(request, "Pick at least one model year.")
        return redirect(back)
    if action == "accept":
        decided, skipped = owner.decide(picked, request.user, "accept", note=note)
    elif action == "photo":
        decided, skipped = owner.decide(picked, request.user, "photo_cards", note=note)
    elif action == "pick" and target:
        vehicle_class = VehicleClass.objects.filter(pk=parse_int(request.POST.get(f"class-{target}")), active=True).first()
        choice = request.POST.get(f"size-{target}", "")
        size = None
        if choice and choice != "ask":
            size = vehicle_class.size_variants.filter(pk=parse_int(choice)).first() if vehicle_class else None
            if size is None:
                messages.error(request, "Pick a size of the vehicle class you chose, or leave the size to the facts.")
                return redirect(back)
        if vehicle_class is None:
            messages.error(request, "Pick a vehicle class.")
            return redirect(back)
        decided, skipped = owner.decide(picked, request.user, "class", vehicle_class, size, choice == "ask", note=note)
    else:
        raise Http404("No such action.")
    text = f"Settled {len(decided)} model year{'s' if len(decided) != 1 else ''}."
    if skipped:
        text += f" {len(skipped)} had no suggestion to accept and wait in the queue."
    messages.success(request, text)
    return redirect(back)
