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
from django.views.decorators.http import require_safe

from appointments.models import Appointment
from billing.models import Payment
from customers.models import Customer
from vehicles.models import Vehicle

from .context_processors import brand_colors
from .forms import CustomerForm, VehicleForm
from .search import find_customers


@require_safe
def home(request):
    """The control app opens on today's schedule."""
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
        rows.append({
            "appointment": appointment,
            "lines": list(appointment.lines.all()),
            "total": total,
            "payments": payments,
            "paid": paid,
            "balance": total - paid,
            "is_canceled": appointment.status == Appointment.Status.CANCELED,
        })
    return rows


@require_safe
def customer(request, pk):
    customer = get_object_or_404(Customer, pk=pk)
    context = {
        "customer": customer,
        "second_contacts": customer.second_contacts.all(),
        "addresses": customer.addresses.order_by("-active", "line1"),
        "vehicles": customer.vehicles.select_related("vehicle_class", "size_variant").order_by("make", "model", "year", "color"),
        "appointments": appointment_rows(customer),
    }
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
    return render(request, "control/vehicle_form.html", {"form": form, "customer": customer, "vehicle": vehicle})


@require_safe
def account(request):
    return render(request, "control/account.html")


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
