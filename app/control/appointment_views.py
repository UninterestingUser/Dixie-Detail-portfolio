"""The schedule, booking and changing jobs, and assigning staff to them."""

import datetime

from django.contrib import messages
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from appointments import booking
from appointments.models import Appointment
from billing.models import Payment
from core.scheduling import time_on_site
from customers.models import Customer
from pricebook.pricing import PricingError, price_job
from staff.authorization import CrewError, assign_crew, auto_assign, staff_choices, uncovered_services, job_services, user_is_manager
from staff.models import Assignment, StaffMember

from .forms import AppointmentForm, FinalPriceForm


def parse_date(text):
    try:
        return datetime.date.fromisoformat(text)
    except (TypeError, ValueError):
        return timezone.localdate()


def day_appointments(first, last):
    """Jobs from the first to the last day, by start, with what the list shows."""
    return (
        Appointment.objects.filter(scheduled_start__date__gte=first, scheduled_start__date__lte=last)
        .select_related("customer", "vehicle", "service_address")
        .prefetch_related("lines", Prefetch("assignments", queryset=Assignment.objects.select_related("staff_member")))
        .order_by("scheduled_start")
    )


@require_safe
def schedule_day(request):
    day = parse_date(request.GET.get("date"))
    context = {
        "day": day,
        "today": timezone.localdate(),
        "previous": day - datetime.timedelta(days=1),
        "next": day + datetime.timedelta(days=1),
        "appointments": day_appointments(day, day),
    }
    return render(request, "control/schedule_day.html", context)


@require_safe
def schedule_week(request):
    day = parse_date(request.GET.get("date"))
    monday = day - datetime.timedelta(days=day.weekday())
    days = [monday + datetime.timedelta(days=offset) for offset in range(7)]
    by_day = {d: [] for d in days}
    for appointment in day_appointments(days[0], days[-1]):
        by_day[timezone.localtime(appointment.scheduled_start).date()].append(appointment)
    context = {
        "monday": monday,
        "sunday": days[-1],
        "today": timezone.localdate(),
        "previous": monday - datetime.timedelta(days=7),
        "next": monday + datetime.timedelta(days=7),
        "days": [(d, by_day[d]) for d in days],
    }
    return render(request, "control/schedule_week.html", context)


def initial_for_vehicle(vehicle):
    if vehicle is None:
        return {}
    return {"vehicle_class": vehicle.vehicle_class_id, "size_variant": vehicle.size_variant_id}


def appointment_new(request, customer_pk):
    customer = get_object_or_404(Customer, pk=customer_pk)
    vehicle = customer.vehicles.filter(pk=request.GET.get("vehicle")).first() or customer.vehicles.order_by("pk").first()
    initial = {
        "date": parse_date(request.GET.get("date")),
        "time": datetime.time(8, 0),
        "vehicle": vehicle,
        "address": customer.addresses.filter(active=True).first(),
        **initial_for_vehicle(vehicle),
    }
    form = AppointmentForm(request.POST or None, customer=customer, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            if data.get("repeat"):
                series = booking.book_series(
                    customer, data["vehicle"], form.start(), form.inputs(), data["repeat"], data["visits"],
                    address=data.get("address"), notes=data["notes"],
                )
                appointments = list(series.appointments.order_by("scheduled_start"))
                messages.success(request, f"Booked {len(appointments)} visits, {series.get_frequency_display().lower()}.")
            else:
                appointments = [booking.book(customer, data["vehicle"], form.start(), form.inputs(), address=data.get("address"), notes=data["notes"])]
                messages.success(request, "Booked.")
        except (PricingError, booking.BookingError) as error:
            form.add_error(None, str(error))
        else:
            for appointment in appointments:
                after_booking(request, appointment)
            return redirect("appointment", pk=appointments[0].pk)
    return render(request, "control/appointment_form.html", {"form": form, "customer": customer, "appointment": None})


def after_booking(request, appointment):
    """Assign the only qualified person automatically (decision 0061), and
    warn of another job overlapping this one."""
    member = auto_assign(appointment)
    if member and appointment.series_id is None:
        messages.info(request, f"Assigned {member}, the only qualified staff member.")
    warn_overlaps(request, appointment)


def warn_overlaps(request, appointment):
    for other in booking.overlapping(appointment):
        when = timezone.localtime(other.scheduled_start).strftime("%a %b %-d at %-I:%M %p")
        messages.warning(request, f"This job overlaps {other.customer}'s job on {when}.")


def edit_initial(appointment):
    start = timezone.localtime(appointment.scheduled_start)
    initial = {
        "vehicle": appointment.vehicle_id,
        "address": appointment.service_address_id,
        "date": start.date(),
        "time": start.time().replace(second=0, microsecond=0),
        "notes": appointment.notes,
        "crew_size": appointment.crew_size,
    }
    inputs = booking.inputs_from_appointment(appointment)
    if inputs:
        initial.update(
            service=inputs.service.pk,
            vehicle_class=inputs.vehicle_class.pk,
            size_variant=inputs.size_variant.pk if inputs.size_variant else None,
            condition_level=inputs.condition_level,
            add_ons=[add_on.pk for add_on in inputs.add_ons],
        )
    return initial, inputs


def same_inputs(old, new):
    return old is not None and (
        old.service.pk, old.vehicle_class.pk, getattr(old.size_variant, "pk", None), old.condition_level,
        sorted(a.pk for a in old.add_ons), old.crew_size,
    ) == (
        new.service.pk, new.vehicle_class.pk, getattr(new.size_variant, "pk", None), new.condition_level,
        sorted(a.pk for a in new.add_ons), new.crew_size,
    )


def appointment_edit(request, pk):
    appointment = get_object_or_404(Appointment.objects.select_related("customer"), pk=pk)
    initial, old_inputs = edit_initial(appointment)
    form = AppointmentForm(request.POST or None, customer=appointment.customer, editing=True, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        new_inputs = form.inputs()
        try:
            changed_services = new_inputs is not None and not same_inputs(old_inputs, new_inputs)
            if changed_services:
                booking.reprice(appointment, new_inputs, data["reason"])
            appointment.refresh_from_db()
            appointment.vehicle = data["vehicle"]
            appointment.service_address = data.get("address")
            appointment.scheduled_start = form.start()
            appointment.notes = data["notes"]
            appointment._change_reason = data["reason"] or "Details changed"
            appointment.save()
        except (PricingError, booking.BookingError) as error:
            form.add_error("reason" if "reason" in str(error) else None, str(error))
        else:
            messages.success(request, "Saved." + (" The job was re-priced." if changed_services else ""))
            warn_overlaps(request, appointment)
            return redirect("appointment", pk=appointment.pk)
    context = {"form": form, "customer": appointment.customer, "appointment": appointment}
    return render(request, "control/appointment_form.html", context)


@require_POST
def appointment_price(request, customer_pk=None, pk=None):
    """The live price for the booking form, from the pricing engine, as the
    owner changes the service, add-ons, condition, crew or date (htmx)."""
    appointment = get_object_or_404(Appointment, pk=pk) if pk else None
    customer = appointment.customer if appointment else get_object_or_404(Customer, pk=customer_pk)
    form = AppointmentForm(request.POST, customer=customer, editing=bool(appointment))
    context = {"errors": [], "job": None}
    if form.is_valid() and form.inputs() is None:
        context["errors"] = ["Not priced from the pricebook. Pick a service to price it."]
    elif form.is_valid():
        inputs = form.inputs()
        try:
            job = price_job(
                inputs.service, inputs.vehicle_class, size_variant=inputs.size_variant,
                condition_level=inputs.condition_level, add_ons=inputs.add_ons, crew_size=inputs.crew_size,
                on=form.cleaned_data["date"], version=booking.version_for(form.cleaned_data["date"]),
            )
        except PricingError as error:
            context["errors"] = [str(error)]
        else:
            context["job"] = job
            context["stay"] = job.time_on_site
            context["changes_price"] = appointment is not None and not same_inputs(booking.inputs_from_appointment(appointment), inputs)
    else:
        context["errors"] = [error for errors in form.errors.values() for error in errors]
    return render(request, "control/_live_price.html", context)


def appointment_context(appointment, **extra):
    choices = staff_choices(appointment)
    assigned = {assignment.staff_member_id: assignment for assignment in appointment.assignments.all()}
    payments = list(appointment.payments.order_by("paid_at"))
    total = appointment.total_before_tax
    context = {
        "appointment": appointment,
        "lines": list(appointment.lines.all()),
        "total": total,
        "payments": payments,
        "paid": sum((p.amount for p in payments), 0),
        "stay": time_on_site(appointment.service_minutes, appointment.crew_size) if appointment.service_minutes is not None else None,
        "staff_choices": choices,
        "assigned": assigned,
        "final_form": FinalPriceForm(initial={"final_price": total}),
        "history": appointment.history.order_by("-history_date")[:10],
        "series_count": appointment.series.appointments.count() if appointment.series_id else 0,
    }
    context.update(extra)
    return context


@require_safe
def appointment(request, pk):
    appointment = get_object_or_404(
        Appointment.objects.select_related("customer", "vehicle", "service_address", "series", "quote"), pk=pk
    )
    return render(request, "control/appointment.html", appointment_context(appointment))


@require_POST
def appointment_status(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    try:
        booking.set_status(appointment, request.POST.get("status", ""))
    except booking.BookingError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Marked {appointment.get_status_display().lower()}.")
    return redirect("appointment", pk=pk)


@require_POST
def appointment_final_price(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    form = FinalPriceForm(request.POST)
    if form.is_valid():
        try:
            booking.set_final_price(appointment, form.cleaned_data["final_price"], form.cleaned_data["reason"])
        except booking.BookingError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Final price saved.")
            return redirect("appointment", pk=pk)
    return render(request, "control/appointment.html", appointment_context(appointment, final_form=form), status=400)


@require_POST
def appointment_staff(request, pk):
    """Assign the crew. Someone not yet authorized needs a manager, a warning
    and a reason; a crew size other than the job's recalculates its time on
    site, with a warning if it now overlaps another job (decision 0061)."""
    appointment = get_object_or_404(Appointment, pk=pk)
    members = list(StaffMember.objects.filter(pk__in=request.POST.getlist("staff"), active=True))
    reason = request.POST.get("training_reason", "")
    confirmed = request.POST.get("confirm") == "yes"
    gaps = uncovered_services(members, job_services(appointment))
    if len(members) > 2:
        messages.error(request, "A crew is one or two people.")
        return redirect("appointment", pk=pk)
    if gaps and not (confirmed and reason.strip()):
        warning = {
            "members": members,
            "gaps": gaps,
            "is_manager": user_is_manager(request.user),
            "reason": reason,
            "needs_reason": confirmed and not reason.strip(),
        }
        return render(request, "control/appointment.html", appointment_context(appointment, staff_warning=warning), status=400)
    try:
        assign_crew(appointment, members, training_reason=reason, by_manager=user_is_manager(request.user))
    except CrewError as error:
        messages.error(request, str(error))
        return redirect("appointment", pk=pk)
    if members and len(members) != appointment.crew_size:
        booking.change_crew_size(appointment, len(members))
        stay = time_on_site(appointment.service_minutes, appointment.crew_size) if appointment.service_minutes is not None else None
        if stay:
            messages.info(request, f"Crew of {len(members)}: time on site is now {stay.total_minutes // 60}:{stay.total_minutes % 60:02d}.")
        warn_overlaps(request, appointment)
    messages.success(request, "Staff saved." if members else "No one is assigned.")
    return redirect("appointment", pk=pk)
