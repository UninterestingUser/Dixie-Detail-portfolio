"""Website requests in the control app (control-app.md,
handling-website-bookings.md): quote requests with their photos (decision
0099), offline "request a time" forms (decision 0100) and a second vehicle
the same day. Each is priced, booked into a time through the availability
check, or declined with a reason (publicapi.decisions). The photos are
served only here, to a signed-in user over the tailnet; no public endpoint
ever returns one."""

import datetime
from decimal import Decimal
from functools import lru_cache
from urllib.parse import quote as url_quote

import yaml
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from appointments import booking
from billing.tax import tax_line
from core.scheduling import format_minutes
from customers.models import Consent
from geo.drive import drive_time, estimate
from geo.models import LocationSettings
from pricebook.models import PricebookVersion
from pricebook.pricing import PricingError, reference_price
from publicapi import decisions
from publicapi.models import QuotePhoto, QuoteRequest, SecondVehicleRequest, TimeRequest
from publicapi.photos import path_of
from staff.authorization import user_is_manager

from .request_forms import BookTimeForm, DeclineForm, HandPriceForm, OfflineBookForm


@lru_cache
def business_phone():
    return yaml.safe_load((settings.DATA_DIR / "business.yaml").read_text())["phone"]["number"]


def require_manager(request, what):
    if not user_is_manager(request.user):
        raise PermissionDenied(f"Only a manager can {what}.")


@require_safe
def requests(request):
    show_all = request.GET.get("show") == "all"
    quote_requests = QuoteRequest.objects.select_related("customer", "vehicle_class", "service", "service_address").prefetch_related("photos")
    time_requests = TimeRequest.objects.select_related("customer", "quote")
    second = SecondVehicleRequest.objects.select_related("customer", "vehicle")
    if not show_all:
        quote_requests = quote_requests.filter(status__in=[QuoteRequest.Status.NEW, QuoteRequest.Status.REPLIED])
        time_requests = time_requests.filter(status=TimeRequest.Status.NEW)
        second = second.filter(status=SecondVehicleRequest.Status.NEW)
    return render(request, "control/requests.html", {
        "quote_requests": quote_requests[:200], "time_requests": time_requests[:200], "second_vehicle_requests": second[:200],
        "show_all": show_all,
    })


# Shared pieces ------------------------------------------------------------------


def drive_info(address):
    """The drive from the home base to the address for a morning arrival,
    from the cache or estimated, never asking Google: the request screens
    don't spend the day's Routes calls."""
    home = LocationSettings.get().home
    if home is None or address is None or address.point is None:
        return None
    arrival = timezone.make_aware(datetime.datetime.combine(timezone.localdate() + datetime.timedelta(days=1), datetime.time(8)))
    departure = arrival - datetime.timedelta(minutes=estimate(home, address.point).minutes)
    return drive_time(home, address.point, departure, ask_google=False)


def tax_preview(address):
    """The tax line's jurisdiction and rate at the address today."""
    if address is None:
        return None
    return tax_line(address, Decimal("100.00"), timezone.localdate())


def contact_links(customer, body=""):
    """Call and text links for the customer's mobile number. The text link is
    offered only with appointment-text consent on record (text-messages.md)."""
    if not customer.mobile:
        return None
    links = {"call": f"tel:+1{customer.mobile}", "number": customer.mobile_display, "text": None}
    if customer.has_consent(Consent.Kind.APPOINTMENT):
        links["text"] = f"sms:+1{customer.mobile}" + (f"?&body={url_quote(body)}" if body else "")
    return links


def book_form_for(start, form_class=BookTimeForm, data=None):
    initial = {}
    if start is not None:
        local = timezone.localtime(start)
        initial = {"date": local.date(), "time": local.time().replace(second=0, microsecond=0)}
    return form_class(data, prefix="book", initial=initial)


def run_booking(request, form, book):
    """Book through book(start, may_override, override_reason). Returns the
    job, or None with the rules alert or errors on the form."""
    if not form.is_valid():
        return None, None
    is_manager = user_is_manager(request.user)
    reason = form.cleaned_data.get("override_reason", "")
    try:
        appointment, member = book(form.start(), is_manager, reason)
    except booking.RulesBroken as error:
        alert = {"broken": [(start, [r.text for r in reasons]) for start, reasons in error.broken], "is_manager": is_manager}
        if is_manager and not reason.strip():
            form.add_error("override_reason", "Give the reason for booking off hours, or pick another time.")
        return None, alert
    except (decisions.DecisionError, booking.BookingError, PricingError) as error:
        form.add_error(None, str(error))
        return None, None
    messages.success(request, "Booked.")
    if member is not None:
        messages.info(request, f"Assigned {member}. Change the crew on the job if needed.")
    elif appointment.status == appointment.Status.BOOKED:
        messages.info(request, "No staff assigned: pick the crew on the job.")
    if appointment.match_flags.filter(resolution="").exists():
        messages.warning(request, "The request differs from the customer's record. Check the differences from the job.")
    return appointment, None


def decline_view(request, item, page):
    require_manager(request, "decline a request")
    form = DeclineForm(request.POST, prefix="decline")
    if form.is_valid():
        try:
            decisions.decline(item, form.cleaned_data["reason"], request.user)
        except decisions.DecisionError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, "Declined. Let the customer know yourself, by text or call.")
    else:
        messages.error(request, "Give the reason for declining.")
    return redirect(page, pk=item.pk)


# Quote requests -----------------------------------------------------------------


def price_text(item):
    """A text to send the price yourself, until Phase 4's texts."""
    quote = item.quote
    if quote is None:
        return ""
    add_ons = [add_on.name for add_on in quote.add_ons.order_by("name")]
    what = quote.service.name + (f" with {' and '.join(add_ons)}" if add_ons else "")
    return (
        f"Dixie Detail: Thanks for your quote request {item.reference}. {what} for your "
        f"{item.vehicle_text or 'vehicle'} is ${quote.total:,.2f} with tax, about {format_minutes(quote.time_on_site_minutes)} on site. "
        f"Reply or call {business_phone()} to pick a day."
    )


def level_priced_by_hand(item):
    version = PricebookVersion.current()
    return bool(item.condition_level and version and version.condition_levels.filter(level=item.condition_level, booked_by_quote=True).exists())


def quote_request_page(request, item, price_form=None, book_form=None, alert=None, status=200):
    is_manager = user_is_manager(request.user)
    quote = item.quote
    if price_form is None:
        initial = {"vehicle_class": item.vehicle_class, "service": item.service}
        if quote is not None:
            initial.update(service=quote.service, vehicle_class=quote.vehicle_class, amount=quote.total_before_tax,
                           time_on_site_minutes=quote.time_on_site_minutes, crew=[member.pk for member in item.crew.all()])
        price_form = HandPriceForm(prefix="price", initial=initial)
    add_ons = list(item.add_ons.order_by("name"))
    reference = None
    if item.condition_level is not None and item.service is not None and item.vehicle_class is not None:
        # A level priced by hand shows the job at Level 2 beside it (decision 0103).
        job = reference_price(item.service, item.vehicle_class, item.size_variant, add_ons)
        reference = {"job": job, "stay": job.time_on_site} if job else None
    context = {
        "item": item,
        "add_ons": add_ons,
        "reference": reference,
        "level_priced_by_hand": level_priced_by_hand(item),
        "drive": drive_info(item.service_address),
        "tax": tax_preview(item.service_address),
        "contact": contact_links(item.customer, price_text(item)),
        "quote": quote,
        "quote_lines": list(quote.lines.all()) if quote else [],
        "price_form": price_form,
        "book_form": book_form or book_form_for(None),
        "decline_form": DeclineForm(prefix="decline"),
        "alert": alert,
        "is_manager": is_manager,
        "is_open": item.status in (QuoteRequest.Status.NEW, QuoteRequest.Status.REPLIED) and item.appointment_id is None,
    }
    return render(request, "control/quote_request.html", context, status=status)


def quote_request_object(pk):
    return get_object_or_404(
        QuoteRequest.objects.select_related(
            "customer", "vehicle_class", "size_variant", "service", "service_address", "appointment", "vehicle", "quote"
        ), pk=pk,
    )


@require_safe
def quote_request(request, pk):
    return quote_request_page(request, quote_request_object(pk))


@require_POST
def quote_request_price(request, pk):
    require_manager(request, "price a quote request")
    item = quote_request_object(pk)
    form = HandPriceForm(request.POST, prefix="price")
    if form.is_valid():
        data = form.cleaned_data
        try:
            decisions.price_quote_request(
                item, data["service"], data["vehicle_class"], data["amount"], data["time_on_site_minutes"], request.user,
                crew=data["crew"],
            )
        except decisions.DecisionError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Priced. Send the price to the customer yourself, by text or call.")
            return redirect("quote-request", pk=item.pk)
    return quote_request_page(request, item, price_form=form, status=422)


@require_POST
def quote_request_book(request, pk):
    item = quote_request_object(pk)
    form = book_form_for(None, data=request.POST)
    appointment, alert = run_booking(
        request, form, lambda start, may, reason: decisions.book_quote_request(item, start, request.user, may, reason)
    )
    if appointment is not None:
        return redirect("appointment", pk=appointment.pk)
    return quote_request_page(request, item, book_form=form, alert=alert, status=422)


@require_POST
def quote_request_decline(request, pk):
    return decline_view(request, quote_request_object(pk), "quote-request")


@require_safe
def quote_photo(request, pk):
    """One photo, to a signed-in user only. The file name is never in the URL."""
    photo = get_object_or_404(QuotePhoto, pk=pk, request__isnull=False)
    try:
        path = path_of(photo.file_name)
    except ValueError as error:
        raise Http404("No such photo.") from error
    if not path.exists():
        raise Http404("The photo file is missing.")
    response = FileResponse(path.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response


# Offline requests ---------------------------------------------------------------


def time_request_object(pk):
    return get_object_or_404(TimeRequest.objects.select_related("customer", "quote", "service_address", "appointment", "vehicle"), pk=pk)


def time_request_page(request, item, book_form=None, alert=None, status=200):
    return render(request, "control/time_request.html", {
        "item": item,
        "lines": list(item.quote.lines.all()) if item.quote else [],
        "contact": contact_links(item.customer),
        "drive": drive_info(item.service_address),
        "book_form": book_form or book_form_for(item.preferred_start, OfflineBookForm),
        "decline_form": DeclineForm(prefix="decline"),
        "alert": alert,
        "is_manager": user_is_manager(request.user),
        "can_book": item.status == TimeRequest.Status.NEW and item.quote_id is not None and item.service_address_id is not None,
    }, status=status)


@require_safe
def time_request(request, pk):
    return time_request_page(request, time_request_object(pk))


@require_POST
def time_request_book(request, pk):
    item = time_request_object(pk)
    form = book_form_for(None, OfflineBookForm, data=request.POST)
    honor = form.is_valid() and form.cleaned_data.get("honor_shown")
    appointment, alert = run_booking(
        request, form,
        lambda start, may, reason: decisions.book_time_request(item, start, request.user, may, reason, honor_shown=honor),
    )
    if appointment is not None:
        return redirect("appointment", pk=appointment.pk)
    return time_request_page(request, item, book_form=form, alert=alert, status=422)


@require_POST
def time_request_decline(request, pk):
    return decline_view(request, time_request_object(pk), "time-request")


# A second vehicle the same day --------------------------------------------------


def second_vehicle_object(pk):
    return get_object_or_404(
        SecondVehicleRequest.objects.select_related(
            "customer", "service_address", "vehicle", "web_quote__quote", "same_day_appointment__vehicle", "appointment",
        ), pk=pk,
    )


def second_vehicle_page(request, item, book_form=None, alert=None, status=200):
    return render(request, "control/second_vehicle_request.html", {
        "item": item,
        "quote": item.web_quote.quote,
        "lines": list(item.web_quote.quote.lines.all()),
        "contact": contact_links(item.customer),
        "book_form": book_form or book_form_for(item.start),
        "decline_form": DeclineForm(prefix="decline"),
        "alert": alert,
        "is_manager": user_is_manager(request.user),
        "is_open": item.status == SecondVehicleRequest.Status.NEW,
    }, status=status)


@require_safe
def second_vehicle_request(request, pk):
    return second_vehicle_page(request, second_vehicle_object(pk))


@require_POST
def second_vehicle_book(request, pk):
    item = second_vehicle_object(pk)
    form = book_form_for(None, data=request.POST)
    appointment, alert = run_booking(
        request, form, lambda start, may, reason: decisions.approve_second_vehicle(item, start, request.user, may, reason)
    )
    if appointment is not None:
        return redirect("appointment", pk=appointment.pk)
    return second_vehicle_page(request, item, book_form=form, alert=alert, status=422)


@require_POST
def second_vehicle_decline(request, pk):
    return decline_view(request, second_vehicle_object(pk), "second-vehicle-request")
