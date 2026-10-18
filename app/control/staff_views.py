"""The staff page and the service page: two views of the one authorization
record (decision 0061). Only a manager changes authorizations."""

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST, require_safe

from pricebook.models import Service
from staff.authorization import (
    authorizable_services,
    authorized_service_ids,
    services_for_staff,
    set_authorization,
    staff_for_service,
    user_is_manager,
)
from staff.models import StaffMember


@require_safe
def staff_list(request):
    members = StaffMember.objects.order_by("-active", "name").prefetch_related("authorizations")
    rows = [(member, len(authorized_service_ids(member))) for member in members]
    return render(request, "control/staff_list.html", {"rows": rows, "service_count": authorizable_services().count()})


@require_safe
def staff_member(request, pk):
    member = get_object_or_404(StaffMember, pk=pk)
    context = {"member": member, "rows": services_for_staff(member), "can_edit": user_is_manager(request.user)}
    return render(request, "control/staff_member.html", context)


@require_safe
def service_list(request):
    return render(request, "control/service_list.html", {"services": authorizable_services()})


@require_safe
def service(request, pk):
    service = get_object_or_404(authorizable_services(), pk=pk)
    context = {"service": service, "rows": staff_for_service(service), "can_edit": user_is_manager(request.user)}
    return render(request, "control/service.html", context)


@require_POST
def authorization_toggle(request, staff_pk, service_pk):
    """Turn one authorization on or off, from either page (htmx swaps the row)."""
    if not user_is_manager(request.user):
        raise PermissionDenied("Only a manager can change authorizations.")
    member = get_object_or_404(StaffMember, pk=staff_pk)
    service = get_object_or_404(Service, pk=service_pk)
    authorized = request.POST.get("authorized") == "on"
    error = ""
    try:
        set_authorization(member, service, authorized, user=request.user)
    except ValueError as problem:
        error = str(problem)
    authorized = member.is_manager or member.authorizations.filter(service=service).exists()
    context = {"member": member, "service": service, "authorized": authorized, "can_edit": True, "error": error}
    template = "control/_toggle_service.html" if request.POST.get("from") == "staff" else "control/_toggle_staff.html"
    return render(request, template, context)
