"""The pricebook: prices laid out like data/price-matrix.csv, editing a draft,
and publishing it with an effective date after deciding each affected job
(pricebook-changes.md). Only a manager changes the pricebook."""

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import cache

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from appointments.models import RepricingDecision
from pricebook.models import PricebookVersion, PublishedVersionError
from pricebook.pricing import base_price
from pricebook.publishing import PublishError, affected_jobs, decide, publish, undecided_jobs
from staff.authorization import user_is_manager

from .forms import PublishForm


def require_manager(request):
    if not user_is_manager(request.user):
        raise PermissionDenied("Only a manager can change the pricebook.")


@cache
def matrix_order():
    """Each (service, vehicle class, size) in the order of data/price-matrix.csv."""
    with (settings.DATA_DIR / "price-matrix.csv").open(newline="") as file:
        rows = list(csv.DictReader(file))
    services = list(dict.fromkeys(row["service"] for row in rows))
    cells = {(row["service"], row["vehicle_class"], row["size_variant"] or ""): index for index, row in enumerate(rows)}
    return services, cells


@dataclass
class RuleCell:
    """A maintenance plan's price, worked out from its rule rather than stored."""

    service: object
    vehicle_class: object
    size_variant: object
    price: Decimal
    one_person_service_hours: Decimal
    rule: object
    pk = None


def rule_cells(version, prices):
    """The cells the price matrix lists for each derived service, priced by the
    pricing engine from its base service's cells."""
    cells = []
    for rule in version.derived_price_rules.select_related("service", "base_service"):
        for price in prices:
            if price.service_id == rule.base_service_id:
                base = base_price(version, rule.service, price.vehicle_class, price.size_variant)
                cells.append(RuleCell(rule.service, price.vehicle_class, price.size_variant, base.price, base.one_person_service_hours, rule))
    return cells


def grouped_prices(version):
    """The version's prices grouped by service, each group in matrix order,
    with the maintenance plans' prices from their rules, as the file lists them."""
    services, cells = matrix_order()
    prices = list(version.prices.select_related("service", "vehicle_class", "size_variant"))
    prices += rule_cells(version, prices)

    def place(price):
        key = (price.service.name, price.vehicle_class.name, str(price.size_variant.value) if price.size_variant else "")
        return cells.get(key, len(cells)), price.vehicle_class.sort_order, getattr(price.size_variant, "value", 0)

    groups = {}
    for price in sorted(prices, key=place):
        groups.setdefault(price.service, []).append(price)
    order = {name: index for index, name in enumerate(services)}
    return sorted(groups.items(), key=lambda item: (order.get(item[0].name, len(order)), item[0].name))


@require_safe
def pricebook(request):
    current = PricebookVersion.current()
    version = current or PricebookVersion.objects.order_by("-number").first()
    if version is None:
        return render(request, "control/pricebook_empty.html")
    return redirect("pricebook-version", number=version.number)


@require_safe
def pricebook_version(request, number):
    version = get_object_or_404(PricebookVersion, number=number)
    context = {
        "version": version,
        "current": PricebookVersion.current(),
        "versions": PricebookVersion.objects.order_by("-number"),
        "groups": grouped_prices(version),
        "derived": version.derived_price_rules.select_related("service", "base_service"),
        "conditions": version.condition_levels.all(),
        "rules": getattr(version, "rules", None),
        "decisions": RepricingDecision.objects.filter(pricebook_version=version).select_related("appointment__customer", "decided_by").order_by("decided_at"),
        "can_edit": user_is_manager(request.user),
        "draft": PricebookVersion.objects.filter(status=PricebookVersion.Status.DRAFT).first(),
        # Only the newest published version's booked jobs can still be decided.
        "undecided": len(undecided_jobs(version)) if version == PricebookVersion.objects.filter(status=PricebookVersion.Status.PUBLISHED).order_by("-number").first() else 0,
    }
    return render(request, "control/pricebook_version.html", context)


@require_POST
def pricebook_new_draft(request):
    require_manager(request)
    draft = PricebookVersion.objects.filter(status=PricebookVersion.Status.DRAFT).first()
    if draft is None:
        draft = PricebookVersion.new_draft(notes=request.POST.get("notes", ""))
        messages.success(request, f"Started draft version {draft.number}, a copy of the latest published prices.")
    return redirect("pricebook-version", number=draft.number)


def decimal_from(text, field):
    try:
        value = Decimal(text.strip().lstrip("$").replace(",", ""))
    except (InvalidOperation, AttributeError):
        raise ValueError(f"{field}: enter a number.") from None
    if value < 0:
        raise ValueError(f"{field}: cannot be below zero.")
    return value


@require_POST
def pricebook_save_draft(request, number):
    """Save every price, service time, rule and condition percentage on the draft."""
    require_manager(request)
    version = get_object_or_404(PricebookVersion, number=number)
    if version.is_published:
        raise PermissionDenied("A published version never changes.")
    errors = []
    with transaction.atomic():
        for price in version.prices.select_related("service", "vehicle_class", "size_variant"):
            label = f"{price.service} / {price.vehicle_class}{f' / {price.size_variant.label}' if price.size_variant else ''}"
            if request.POST.get(f"remove-{price.pk}") == "on":
                price.delete()
                continue
            try:
                price.price = decimal_from(request.POST.get(f"price-{price.pk}", ""), f"{label} price").quantize(Decimal("0.01"))
                price.one_person_service_hours = decimal_from(request.POST.get(f"hours-{price.pk}", ""), f"{label} hours")
            except ValueError as error:
                errors.append(str(error))
                continue
            price.save()
        for rule in version.derived_price_rules.select_related("service"):
            try:
                rule.percent = decimal_from(request.POST.get(f"derived-{rule.pk}", ""), f"{rule.service} percentage")
                rule.save()
            except ValueError as error:
                errors.append(str(error))
        for level in version.condition_levels.all():
            try:
                level.adjustment_percent = decimal_from(request.POST.get(f"condition-{level.pk}", ""), f"Condition level {level.level}")
                level.save()
            except ValueError as error:
                errors.append(str(error))
        version.notes = request.POST.get("notes", version.notes)
        version.save()
        if errors:
            transaction.set_rollback(True)
    if errors:
        for error in errors:
            messages.error(request, error)
    else:
        messages.success(request, f"Draft version {version.number} saved.")
    return redirect("pricebook-version", number=number)


@require_POST
def pricebook_discard_draft(request, number):
    require_manager(request)
    version = get_object_or_404(PricebookVersion, number=number)
    try:
        version.delete()
    except PublishedVersionError as error:
        messages.error(request, str(error))
        return redirect("pricebook-version", number=number)
    messages.success(request, f"Draft version {number} discarded.")
    return redirect("pricebook")


def choices_from(request, jobs):
    """Each affected job's choice from the form: "keep", "use_new" or a custom
    amount. "Keep all" and "Use new for all" set every job at once, and a
    series choice sets every visit left in that series."""
    everything = request.POST.get("all")
    choices = {}
    for job in jobs:
        appointment = job.appointment
        choice = everything or request.POST.get(f"series-{appointment.series_id}") or request.POST.get(f"choice-{appointment.pk}", "keep")
        if choice == "use_new" and job.new_total is None:
            choice = "keep"
        amount = None
        if choice == "custom":
            try:
                amount = decimal_from(request.POST.get(f"amount-{appointment.pk}", ""), f"{appointment}").quantize(Decimal("0.01"))
            except ValueError:
                amount = None
        choices[appointment.pk] = (choice, amount)
    return choices


def pricebook_publish(request, number):
    """Pick the effective date, see every booked job the draft would change,
    decide each, and publish."""
    require_manager(request)
    version = get_object_or_404(PricebookVersion, number=number)
    if version.is_published:
        return redirect("pricebook-version", number=number)
    form = PublishForm(request.POST or request.GET or None, initial={"effective_date": timezone.localdate()})
    jobs = affected_jobs(version, form.cleaned_data["effective_date"]) if form.is_valid() else None
    if request.method == "POST" and form.is_valid() and ("publish" in request.POST or "all" in request.POST):
        choices = choices_from(request, jobs)
        try:
            publish(version, form.cleaned_data["effective_date"], choices, user=request.user)
        except (PublishError, ValueError) as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Published version {version.number}, in effect from {form.cleaned_data['effective_date']:%b %-d, %Y}.")
            return redirect("pricebook-version", number=number)
    series = {}
    for job in jobs or []:
        if job.appointment.series_id:
            series.setdefault(job.appointment.series, []).append(job)
    context = {"version": version, "form": form, "jobs": jobs, "series": [(s, j) for s, j in series.items() if len(j) > 1]}
    return render(request, "control/pricebook_publish.html", context)


def pricebook_booked_jobs(request, number):
    """The booked-job review of a published version: each booked job it
    prices differently that has no choice logged yet, as apply_size_classes
    leaves them (decision 0083), with its quoted price and its new one. Every
    job keeps its quoted price until the owner chooses."""
    version = get_object_or_404(PricebookVersion, number=number)
    if not version.is_published:
        return redirect("pricebook-publish", number=number)
    jobs = undecided_jobs(version)
    if request.method == "POST":
        require_manager(request)
        choices = choices_from(request, jobs)
        try:
            with transaction.atomic():
                for job in jobs:
                    decide(version, job, *choices[job.appointment.pk], user=request.user)
        except (PublishError, ValueError) as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Saved the choice for {len(jobs)} booked job{'s' if len(jobs) != 1 else ''}.")
            return redirect("pricebook-version", number=number)
    series = {}
    for job in jobs:
        if job.appointment.series_id:
            series.setdefault(job.appointment.series, []).append(job)
    context = {
        "version": version,
        "jobs": jobs,
        "series": [(found, found_jobs) for found, found_jobs in series.items() if len(found_jobs) > 1],
        "can_edit": user_is_manager(request.user),
    }
    return render(request, "control/pricebook_booked_jobs.html", context)
