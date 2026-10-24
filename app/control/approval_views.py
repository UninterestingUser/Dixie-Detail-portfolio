"""Phase 2 Step 4 in the control app (decisions 0077 and 0079): the differences screen,
where the owner settles each customer's vehicle whose own class differs
from the catalog's, and the approval list, where the owner approves or
changes each year range of every model in the job history, the spot-check
list and every model whose years are in different classes.

Every signed-in user can look; only a manager changes anything.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST, require_safe

from vehicles import linking
from vehicles.classification import approvals
from vehicles.models import ModelYearClassification, Vehicle, VehicleClass, VehicleModel

from .catalog_views import changed_message, nav_context, parse_int, require_manager
from .forms import size_choices

APPROVAL_PAGE = 25


# The differences screen.


@require_safe
def differences(request):
    found = linking.differences()
    rows = []
    for difference in found:
        first, last = linking.model_span(difference.vehicle)
        rows.append({"difference": difference, "span": str(first) if first == last else f"{first} to {last}"})
    context = {
        **nav_context(request, "differences"),
        "rows": rows,
        "unlinked": Vehicle.objects.filter(vehicle_model=None).count(),
    }
    return render(request, "control/differences.html", context)


@require_POST
def difference_act(request, pk):
    """One tap on a vehicle: keep its imported class as its own override,
    take the catalog's, or give every vehicle of the model its class."""
    require_manager(request)
    vehicle = get_object_or_404(Vehicle.objects.select_related("vehicle_model", "vehicle_class", "size_variant", "customer"), pk=pk)
    stored = ModelYearClassification.objects.filter(vehicle_model=vehicle.vehicle_model, year=vehicle.year).select_related(
        "vehicle_class", "size_variant"
    ).first()
    if linking.differs(vehicle, stored) is None:
        messages.info(request, f"{vehicle} no longer differs from the catalog.")
        return redirect("differences")
    action, note = request.POST.get("do"), request.POST.get("note", "").strip()
    if action == "keep":
        linking.keep_imported(vehicle, request.user, note)
        messages.success(request, f"{vehicle} keeps its imported class, {linking.own_label(vehicle)}, as its own override.")
    elif action == "accept":
        linking.accept_catalog(vehicle, stored, request.user, note)
        messages.success(request, f"{vehicle} now has the catalog's class, {linking.own_label(vehicle)}.")
    elif action == "model":
        first, last = linking.model_span(vehicle)
        found = linking.override_model(vehicle, request.user, note)
        model = vehicle.vehicle_model
        messages.success(request, f"Every {first} to {last} {model.make} {model.model} is now {vehicle.vehicle_class}. {changed_message(found)}")
    else:
        messages.error(request, "Pick one of the three choices.")
    return redirect("differences")


# The approval list.

SHOWS = {"waiting": "Waiting", "approved": "Approved", "all": "All"}
REASONS = [approvals.JOB_HISTORY, approvals.SPOT_CHECK, approvals.MIXED, approvals.APPROVED_BEFORE]


@require_safe
def approval_list(request):
    listed, missing = approvals.approval_list()
    show = request.GET.get("show", "waiting")
    show = show if show in SHOWS else "waiting"
    reason = request.GET.get("reason", "")
    shown = listed
    if reason in REASONS:
        shown = [item for item in shown if any(found.startswith(reason) for found in item.reasons)]
    if show == "waiting":
        shown = [item for item in shown if not item.approved]
    elif show == "approved":
        shown = [item for item in shown if item.approved]
    page = Paginator(shown, APPROVAL_PAGE).get_page(request.GET.get("page"))
    classes = VehicleClass.objects.filter(active=True)
    context = {
        **nav_context(request, "approvals"),
        "page": page,
        "total": len(listed),
        "approved": sum(1 for item in listed if item.approved),
        "shown": len(shown),
        "show": show,
        "shows": SHOWS.items(),
        "reason": reason,
        "reasons": REASONS,
        "missing": missing,
        "classes": classes,
        "sizes": size_choices(classes),
        "here": request.get_full_path(),
    }
    return render(request, "control/approvals.html", context)


@require_POST
def approval_act(request):
    """Approve one year range as shown, or change it to another class and
    size, which sets a model override for exactly its years."""
    require_manager(request)
    action, _, target = request.POST.get("do", "").partition(":")
    model_id, _, years = target.partition(":")
    first, _, last = years.partition("-")
    vehicle_model = get_object_or_404(VehicleModel, pk=parse_int(model_id))
    first, last = parse_int(first), parse_int(last)
    note = request.POST.get(f"note-{target}", "").strip()
    back = request.POST.get("next", "")
    back = back if back.startswith(reverse("approvals")) else reverse("approvals")
    name = f"{vehicle_model.make} {vehicle_model.model}"
    try:
        if action == "approve":
            approvals.approve(vehicle_model, first, last, request.user, note)
            messages.success(request, f"Approved {name} {first} to {last}.")
        elif action == "change":
            vehicle_class = VehicleClass.objects.filter(pk=parse_int(request.POST.get(f"class-{target}")), active=True).first()
            if vehicle_class is None:
                messages.error(request, "Pick a vehicle class.")
                return redirect(back)
            choice = request.POST.get(f"size-{target}", "")
            size = None
            if choice and choice != "ask":
                size = vehicle_class.size_variants.filter(pk=parse_int(choice)).first()
                if size is None:
                    messages.error(request, "Pick a size of the vehicle class you chose, or leave the size to the facts.")
                    return redirect(back)
            approvals.change(vehicle_model, first, last, request.user, vehicle_class, size, choice == "ask", note)
            messages.success(request, f"{name} {first} to {last} is now {vehicle_class}, and approved.")
        else:
            messages.error(request, "Pick Approve or Change.")
    except approvals.RangeChanged as error:
        messages.error(request, str(error))
    return redirect(back)
