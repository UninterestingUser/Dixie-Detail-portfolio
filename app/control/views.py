"""The control app's pages (decision 0046): the shell, and finding, viewing,
adding and editing customers and their vehicles. The schedule and jobs, staff
and pricebook are in their own modules."""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.utils.cache import patch_vary_headers
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST, require_safe

from appointments.models import Appointment
from billing.models import Payment
from customers.models import Customer
from pricebook.models import PricedLine
from staff.authorization import user_is_manager
from vehicles.classification.lookup import classify
from vehicles.models import Vehicle

from . import needs_you
from .context_processors import brand_colors
from .forms import CustomerForm, VehicleForm, VehicleOverrideForm
from .location_views import address_summary
from .search import find_customers


@require_safe
def home(request):
    """The control app opens on today's schedule."""
    return redirect("schedule")


@require_POST
def needs_you_seen(request):
    """Clear the new website bookings from the "needs you" list, up to the
    newest one the page showed, so a booking that came in meanwhile stays."""
    from django.utils.dateparse import parse_datetime

    moment = parse_datetime(request.POST.get("until", "") or "")
    needs_you.mark_seen(request.user, moment)
    return redirect("schedule")


@require_safe
def customers(request):
    """Search by name or phone. htmx asks for just the results as the owner types."""
    query = request.GET.get("q", "")
    found, more = find_customers(query)
    context = {"query": query, "customers": found, "more": more}
    template = "control/_customer_results.html" if request.headers.get("HX-Request") else "control/customers.html"
    response = render(request, template, context)
    # The same address gives a whole page or just the results.
    patch_vary_headers(response, ["HX-Request"])
    return response


SERVICE_KINDS = (PricedLine.Kind.SERVICE, PricedLine.Kind.ADD_ON, PricedLine.Kind.CUSTOM)


def appointment_rows(customer):
    """Every appointment, newest first, with its price and what was paid."""
    appointments = customer.appointments.select_related("vehicle", "service_address").prefetch_related(
        "lines", Prefetch("payments", queryset=Payment.objects.order_by("paid_at"))
    )
    rows = []
    for appointment in appointments:
        total = appointment.total_before_tax
        payments = list(appointment.payments.all())
        paid = sum((payment.amount for payment in payments), Decimal("0.00"))
        lines = list(appointment.lines.all())
        rows.append({
            "appointment": appointment,
            "lines": lines,
            "services": [line.description for line in lines if line.kind in SERVICE_KINDS],
            "total": total,
            "payments": payments,
            "paid": paid,
            "balance": total - paid,
            "is_canceled": appointment.status == Appointment.Status.CANCELED,
        })
    return rows


def with_summaries(addresses):
    """Each address with how it was verified, its tax and its area."""
    addresses = list(addresses)
    for address in addresses:
        address.summary = address_summary(address)
    return addresses


@require_safe
def customer(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    context = {
        "customer": customer,
        "second_contacts": customer.second_contacts.all(),
        "addresses": with_summaries(customer.addresses.select_related("tax_jurisdiction", "verified_by").order_by("-active", "line1")),
        "vehicles": customer.vehicles.select_related("vehicle_class", "size_variant").order_by("-active", "make", "model", "year", "color"),
    }
    # Canceled jobs are listed apart, below the appointments (decision 0095).
    rows = appointment_rows(customer)
    context["appointments"] = [row for row in rows if not row["is_canceled"]]
    context["canceled"] = [row for row in rows if row["is_canceled"]]
    return render(request, "control/customer.html", context)


def customer_form(request, pk=None):
    customer = get_object_or_404(Customer, pk=pk) if pk else None
    form = CustomerForm(request.POST or None, instance=customer)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"Saved {saved}.")
        return redirect("customer", pk=saved.pk)
    return render(request, "control/customer_form.html", {"form": form, "customer": customer})


def vehicle_form(request, customer_pk=None, pk=None):
    if pk:
        vehicle = get_object_or_404(Vehicle.objects.select_related("customer"), pk=pk)
        customer = vehicle.customer
    else:
        customer = get_object_or_404(Customer, pk=customer_pk)
        vehicle = Vehicle(customer=customer)
    form = VehicleForm(request.POST or None, instance=vehicle)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"Saved {saved}.")
        return redirect("customer", pk=customer.pk)
    context = {"form": form, "customer": customer, "vehicle": vehicle}
    if vehicle.pk:
        # The vehicle's own class override, beside what the catalog gives it (decision 0076).
        context.update(
            catalog=classify(vehicle.year, vehicle.make, vehicle.model) if vehicle.year and vehicle.make and vehicle.model else None,
            override_form=VehicleOverrideForm(
                prefix="override",
                initial={"vehicle_class": vehicle.vehicle_class, "size_variant": vehicle.size_variant, "note": vehicle.class_override_note},
            ),
            can_override=user_is_manager(request.user),
        )
    return render(request, "control/vehicle_form.html", context)


@require_safe
def account(request):
    return render(request, "control/account.html", {"is_manager": user_is_manager(request.user)})


# Installing the app (decision 0046). These three are reached before sign-in:
# the browser fetches the manifest and the service worker without the
# session, and the offline page is shown when the server cannot be reached.


@login_not_required
@require_safe
def manifest(request):
    colors = brand_colors()
    data = {
        "id": "/",
        "name": "Dixie Detail Control",
        "short_name": "Dixie Detail",
        "description": "Run Dixie Detail: customers, vehicles and jobs.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": colors["white"],
        "theme_color": colors["navy"],
        "icons": [
            {"src": static("control/icons/icon-192.png"), "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": static("control/icons/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": static("control/icons/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return JsonResponse(data, content_type="application/manifest+json")


@login_not_required
@require_safe
@cache_control(no_cache=True)
def service_worker(request):
    # Served from the root so it controls every page.
    return render(request, "control/sw.js", content_type="text/javascript")


@login_not_required
@require_safe
def offline(request):
    return render(request, "control/offline.html")
