"""Website requests in the control app: quote requests with their photos
(decision 0099) and offline "request a time" forms (decision 0100). The
photos are served only here, to a signed-in user over the tailnet; no
public endpoint ever returns one."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from appointments.models import Appointment
from publicapi.models import QuotePhoto, QuoteRequest, TimeRequest
from publicapi.photos import path_of
from staff.authorization import user_is_manager


def open_counts():
    """For the schedule's notice: new requests, and offline requests whose
    price differs from what the customer saw."""
    return {
        "quote_requests": QuoteRequest.objects.filter(status=QuoteRequest.Status.NEW, is_test=False).count(),
        "time_requests": TimeRequest.objects.filter(status=TimeRequest.Status.NEW, is_test=False).count(),
        "price_differs": TimeRequest.objects.filter(status=TimeRequest.Status.NEW, price_differs=True, is_test=False).count(),
    }


@require_safe
def requests(request):
    show_all = request.GET.get("show") == "all"
    quote_requests = QuoteRequest.objects.select_related("customer", "vehicle_class", "service", "service_address").prefetch_related("photos")
    time_requests = TimeRequest.objects.select_related("customer", "quote")
    if not show_all:
        quote_requests = quote_requests.filter(status__in=[QuoteRequest.Status.NEW, QuoteRequest.Status.REPLIED])
        time_requests = time_requests.filter(status=TimeRequest.Status.NEW)
    return render(request, "control/requests.html", {
        "quote_requests": quote_requests[:200], "time_requests": time_requests[:200], "show_all": show_all,
    })


@require_safe
def quote_request(request, pk):
    found = get_object_or_404(QuoteRequest.objects.select_related("customer", "vehicle_class", "service", "service_address", "appointment"), pk=pk)
    return render(request, "control/quote_request.html", {
        "item": found,
        "statuses": QuoteRequest.Status.choices,
        "jobs": Appointment.objects.filter(customer=found.customer).order_by("-scheduled_start")[:20],
        "is_manager": user_is_manager(request.user),
    })


@require_POST
def quote_request_status(request, pk):
    if not user_is_manager(request.user):
        raise PermissionDenied("Only a manager can change a request.")
    found = get_object_or_404(QuoteRequest, pk=pk)
    status = request.POST.get("status", "")
    if status not in QuoteRequest.Status.values:
        raise Http404("No such status.")
    found.status = status
    found.closed_at = timezone.now() if status in QuoteRequest.CLOSED else None
    job = request.POST.get("appointment", "")
    if job.isdigit():
        found.appointment = get_object_or_404(Appointment, pk=int(job), customer=found.customer)
    elif job == "none":
        found.appointment = None
    found.save()
    messages.success(request, f"Request {found.reference} is now {found.get_status_display().lower()}.")
    return redirect("quote-request", pk=found.pk)


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


@require_safe
def time_request(request, pk):
    found = get_object_or_404(TimeRequest.objects.select_related("customer", "quote", "service_address", "appointment"), pk=pk)
    return render(request, "control/time_request.html", {
        "item": found,
        "lines": found.quote.lines.all() if found.quote else [],
        "statuses": TimeRequest.Status.choices,
        "jobs": Appointment.objects.filter(customer=found.customer).order_by("-scheduled_start")[:20],
        "is_manager": user_is_manager(request.user),
    })


@require_POST
def time_request_status(request, pk):
    if not user_is_manager(request.user):
        raise PermissionDenied("Only a manager can change a request.")
    found = get_object_or_404(TimeRequest, pk=pk)
    status = request.POST.get("status", "")
    if status not in TimeRequest.Status.values:
        raise Http404("No such status.")
    found.status = status
    job = request.POST.get("appointment", "")
    if job.isdigit():
        found.appointment = get_object_or_404(Appointment, pk=int(job), customer=found.customer)
    found.save()
    messages.success(request, "Request updated.")
    return redirect("time-request", pk=found.pk)
