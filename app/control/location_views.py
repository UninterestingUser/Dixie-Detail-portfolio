"""Addresses, the location and drive-time settings, and sales tax rates.

Every signed-in user can look at the sales tax rates; only a manager
approves a rate, changes a per-state rate, changes the location settings or
approves an out-of-area address. The location settings hold the owner's
home, so only managers see them.
"""

import datetime
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from appointments.models import Appointment
from billing import tax_rates
from billing.models import TaxJurisdiction, TaxRate
from billing.tax import rate_on
from customers.models import Address, Customer
from geo import census, http, service_area
from geo.google import quota_day
from geo.models import ApiUsage, LocationSettings
from geo.verification import verify_by_hand, verify_typed
from staff.authorization import user_is_manager

from .forms import AddressForm, ApproveRateForm, LocationSettingsForm, StateRateForm
from .templatetags.control import percent


def require_manager(request, what):
    if not user_is_manager(request.user):
        raise PermissionDenied(f"Only a manager can {what}.")


def verification_text(address):
    """How the address was verified, with who set a location by hand."""
    if not address.verified:
        return "Not verified"
    if address.verification == Address.Verification.BY_HAND and address.verified_by:
        who = address.verified_by.get_full_name() or address.verified_by.get_username()
        return f"Verified (location set by hand by {who})"
    return f"Verified ({address.get_verification_display()})"


def address_summary(address):
    """One line on how an address verified and what tax and area it gets."""
    parts = [verification_text(address)]
    if address.county:
        parts.append(f"{address.county} County")
    if address.tax_jurisdiction:
        parts.append(f"tax: {address.tax_jurisdiction.name}")
    parts.append(service_area.check(address).reason)
    return ", ".join(parts)


def address_form(request, customer_pk=None, pk=None):
    if pk:
        address = get_object_or_404(Address.objects.select_related("customer"), pk=pk)
        customer = address.customer
    else:
        customer = get_object_or_404(Customer, pk=customer_pk)
        address = Address(customer=customer, state=service_area.home_state())
    can_approve = user_is_manager(request.user)
    form = AddressForm(request.POST or None, instance=address, can_approve=can_approve)
    if request.method == "POST" and form.is_valid():
        address = form.save(commit=False)
        data = form.cleaned_data
        reason = "Saved in the control app"
        if data["by_hand"]:
            verify_by_hand(address, *data["point"], user=request.user, county=data["hand_county"].strip())
            reason = "Location set by hand in the control app"
        elif form.parts_changed() or not address.verified or address.verification == Address.Verification.BY_HAND:
            try:
                outcome = verify_typed(address)
            except http.FetchError:
                form.add_error(None, "The Census geocoder could not be reached. Try again in a minute, or set the location by hand.")
            else:
                if not outcome.matched:
                    form.add_error(None, f"Neither the Census geocoder nor Google found this address ({outcome.reason}). "
                                         "Check the street, city and ZIP code, or set the location by hand.")
        if not form.errors:
            address._change_reason = reason
            address.save()
            messages.success(request, f"Saved {address}. {address_summary(address)}.")
            if address.tax_needs_check:
                messages.warning(request, f"Check the sales tax: {address.tax_note}")
            return redirect("customer", pk=customer.pk)
    context = {"form": form, "customer": customer, "address": address if address.pk else None}
    return render(request, "control/address_form.html", context)


def month_usage(day):
    """This month's call counts per outside service, Pacific dates."""
    first = day.replace(day=1)
    totals = {row["api"]: row for row in ApiUsage.objects.filter(day__gte=first, day__lte=day).values("api").annotate(calls=Sum("calls"), refused=Sum("refused"))}
    today = {usage.api: usage for usage in ApiUsage.objects.filter(day=day)}
    settings = LocationSettings.get()
    caps = {
        ApiUsage.Api.PLACE_DETAILS: settings.place_details_daily_cap,
        ApiUsage.Api.TEXT_SEARCH: settings.text_search_daily_cap,
        ApiUsage.Api.ROUTES: settings.routes_daily_cap,
    }
    return [
        {
            "label": label,
            "month": totals.get(api, {}).get("calls", 0),
            "refused": totals.get(api, {}).get("refused", 0),
            "today": getattr(today.get(api), "calls", 0),
            "cap": caps.get(api),
        }
        for api, label in ApiUsage.Api.choices
    ]


def location_settings(request):
    require_manager(request, "see or change the location settings")
    settings = LocationSettings.get()
    form = LocationSettingsForm(request.POST or None, instance=settings)
    if request.method == "POST" and form.is_valid():
        settings = form.save(commit=False)
        data = form.cleaned_data
        if form.home_changed() and data["home_latitude"] is None and settings.home_line1:
            try:
                match = census.geocode(settings.home_line1, settings.home_city, settings.home_state, settings.home_zip_code)
            except http.FetchError:
                match = None
                form.add_error(None, "The Census geocoder could not be reached. Try again, or give the coordinates.")
            else:
                if match is None:
                    form.add_error(None, "The Census geocoder did not find the home base. Check it, or give the coordinates.")
                else:
                    settings.home_latitude = Decimal(str(round(match["latitude"], 6)))
                    settings.home_longitude = Decimal(str(round(match["longitude"], 6)))
        if not form.errors:
            settings._change_reason = "Changed in the control app"
            settings.save()
            messages.success(request, "Saved the location settings.")
            return redirect("location-settings")
    day = quota_day()
    context = {"form": form, "settings": settings, "usage": month_usage(day), "month": day}
    return render(request, "control/location_settings.html", context)


@require_safe
def sales_tax(request):
    today = timezone.localdate()
    jurisdictions = TaxJurisdiction.objects.order_by("state", "county", "kind", "name")
    five = {service_area.county_key(county) for county in service_area.counties()}
    rows = [{"jurisdiction": j, "rate": rate_on(j, today), "has_boundary": hasattr(j, "boundary")} for j in jurisdictions]
    pending = TaxRate.objects.filter(approved_at__isnull=True, rejected_at__isnull=True).select_related("jurisdiction")
    context = {
        "service_area_rows": [row for row in rows if row["jurisdiction"].kind != TaxJurisdiction.Kind.STATE and service_area.county_key(row["jurisdiction"].county) in five],
        "other_rows": [row for row in rows if row["jurisdiction"].kind != TaxJurisdiction.Kind.STATE and service_area.county_key(row["jurisdiction"].county) not in five],
        "state_rows": [row for row in rows if row["jurisdiction"].kind == TaxJurisdiction.Kind.STATE],
        "pending": [{"rate": rate, "current": rate_on(rate.jurisdiction, today), "form": ApproveRateForm(prefix=f"r{rate.pk}", initial={"effective_from": rate.effective_from})} for rate in pending],
        "flagged": Address.objects.filter(tax_needs_check=True, active=True).select_related("customer", "tax_jurisdiction"),
        "state_form": StateRateForm(initial={"effective_from": today}),
        "can_edit": user_is_manager(request.user),
    }
    return render(request, "control/sales_tax.html", context)


@require_POST
def rate_approve(request, pk):
    require_manager(request, "approve a sales tax rate")
    rate = get_object_or_404(TaxRate.objects.select_related("jurisdiction"), pk=pk)
    form = ApproveRateForm(request.POST, prefix=f"r{rate.pk}")
    if not form.is_valid():
        messages.error(request, "Give the date the new rate takes effect.")
        return redirect("sales-tax")
    try:
        tax_rates.approve_rate(rate, form.cleaned_data["effective_from"], request.user)
    except tax_rates.RateError as error:
        messages.error(request, str(error))
        return redirect("sales-tax")
    start = timezone.make_aware(datetime.datetime.combine(rate.effective_from, datetime.time()))
    booked = Appointment.objects.filter(
        status=Appointment.Status.BOOKED, scheduled_start__gte=start, service_address__tax_jurisdiction=rate.jurisdiction
    ).count()
    messages.success(
        request,
        f"Approved {percent(rate.combined_rate)}% for {rate.jurisdiction} from {rate.effective_from:%B %-d, %Y}."
        + (f" {booked} booked job(s) there on or after that day will be taxed at the new rate; their price before tax does not change." if booked else ""),
    )
    return redirect("sales-tax")


@require_POST
def rate_reject(request, pk):
    require_manager(request, "reject a sales tax rate")
    rate = get_object_or_404(TaxRate.objects.select_related("jurisdiction"), pk=pk)
    try:
        tax_rates.reject_rate(rate, request.user)
    except tax_rates.RateError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Rejected the new rate for {rate.jurisdiction}. The current rate stays.")
    return redirect("sales-tax")


@require_POST
def state_rate(request, pk):
    require_manager(request, "change a per-state rate")
    jurisdiction = get_object_or_404(TaxJurisdiction, pk=pk)
    form = StateRateForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Give a rate from 0 to 20 percent and the date it takes effect.")
        return redirect("sales-tax")
    try:
        rate = tax_rates.set_state_rate(jurisdiction, form.cleaned_data["percent"], form.cleaned_data["effective_from"], request.user)
    except tax_rates.RateError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"{jurisdiction} is taxed at {percent(rate.state_rate)}% from {rate.effective_from:%B %-d, %Y}.")
    return redirect("sales-tax")
