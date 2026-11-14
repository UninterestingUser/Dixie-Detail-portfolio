"""Booking, changing and canceling jobs, and assigning staff to them. The
schedule's views are in schedule_views."""

import datetime

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_safe

from appointments import booking
from appointments.models import Appointment
from billing.tax import tax_line, tax_line_for_appointment
from calendars import sync as calendar_sync
from core.scheduling import time_on_site
from customers.models import Customer
from geo import service_area
from geo.drive import drive_from_home
from pricebook.pricing import PricingError, hand_description, price_job, reference_price
from scheduling import changes as scheduling_changes
from scheduling.models import DateException, OpenWeekday, RuleOverride, SchedulingSettings
from staff.authorization import CrewError, assign_crew, auto_assign, staff_choices, uncovered_services, job_services, user_is_manager
from staff.models import StaffMember

from .forms import AppointmentForm, FinalPriceForm


def parse_date(text, default=None):
    try:
        return datetime.date.fromisoformat(text)
    except (TypeError, ValueError):
        return default or timezone.localdate()


def first_bookable_date():
    """The first date past the minimum notice that is open, for a new
    booking's date: a date that needs no reason, as far as the day goes."""
    settings = SchedulingSettings.get()
    day = timezone.localdate() + datetime.timedelta(days=settings.minimum_notice_days)
    open_weekdays = set(OpenWeekday.objects.filter(is_open=True).values_list("weekday", flat=True))
    closed_dates = set(DateException.objects.filter(kind=DateException.Kind.CLOSED, date__gte=day).values_list("date", flat=True))
    for _ in range(366):
        if day.weekday() in open_weekdays and day not in closed_dates:
            return day
        day += datetime.timedelta(days=1)
    return timezone.localdate()


def initial_for_vehicle(vehicle):
    if vehicle is None:
        return {}
    return {"vehicle_class": vehicle.vehicle_class_id, "size_variant": vehicle.size_variant_id}


def appointment_new(request, customer_pk):
    customer = get_object_or_404(Customer, pk=customer_pk)
    vehicle = customer.vehicles.filter(pk=request.GET.get("vehicle")).first() or customer.vehicles.filter(active=True).order_by("pk").first()
    initial = {
        "date": parse_date(request.GET.get("date"), default=first_bookable_date()),
        "time": datetime.time(8, 0),
        "vehicle": vehicle,
        "address": customer.addresses.filter(active=True).first(),
        **initial_for_vehicle(vehicle),
    }
    form = AppointmentForm(request.POST or None, customer=customer, initial=initial)
    alert = None
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        # Time Off is copied again as the booking is sent; with Google down,
        # the check uses the last copy (decision 0057).
        calendar_sync.refresh_time_off_for_booking()
        try:
            broken = rules_broken(form)
            alert = rules_alert(request, form, broken, submitted=True)
            if alert and not alert["go_ahead"]:
                raise booking.RulesBroken(broken)
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
        except booking.RulesBroken:
            pass
        except (PricingError, booking.BookingError) as error:
            form.add_error(None, str(error))
        else:
            log_overrides(request, appointments, broken, data, RuleOverride.Action.BOOKED)
            for appointment in appointments:
                after_booking(request, appointment)
            return redirect("appointment", pk=appointments[0].pk)
    context = {"form": form, "customer": customer, "appointment": None, "alert": alert,
               "time_off_warning": calendar_sync.time_off_warning()}
    return render(request, "control/appointment_form.html", context)


def is_moved(form, appointment):
    data = form.cleaned_data
    return form.start() != appointment.scheduled_start or data.get("address") != appointment.service_address


def services_changed(form, appointment):
    new_inputs = form.inputs()
    return new_inputs is not None and not same_inputs(booking.inputs_from_appointment(appointment), new_inputs)


def rules_broken(form, appointment=None):
    """[(start, [Reason])] for each start the form's choice puts outside the
    scheduling rules: each visit of a new booking, or a changed job when its
    date, time, address or services changed. A change to anything else, such
    as the notes, is not checked. May raise PricingError."""
    data = form.cleaned_data
    if appointment is None:
        repeat = data.get("repeat")
        starts = booking.series_starts(form.start(), repeat, data["visits"]) if repeat else [form.start()]
        return booking.rules_broken(form.inputs(), starts, data.get("address"))
    if not (is_moved(form, appointment) or services_changed(form, appointment)):
        return []
    inputs = form.inputs() or booking.inputs_from_appointment(appointment)
    return booking.rules_broken(inputs, [form.start()], data.get("address"), appointment)


def rules_broken_so_far(form, appointment=None):
    """While the services aren't all chosen yet, the rules the date, time and
    address break on their own, or None without a date and time."""
    data = form.cleaned_data
    if data.get("date") is None or data.get("time") is None:
        return None
    start = form.start()
    if appointment is not None and start == appointment.scheduled_start and data.get("address") == appointment.service_address:
        return []
    return booking.rules_broken_without_services(start, data.get("address"), appointment)


def rules_alert(request, form, broken, submitted=False):
    """The alert under the date and time while the choice breaks a rule, or
    None when it fits. A manager goes ahead by giving a reason; anyone else
    picks another time. At submit, a manager without a reason gets an error
    on the reason box. The website never books outside the rules."""
    if not broken:
        return None
    is_manager = user_is_manager(request.user)
    reason = form.cleaned_data.get("override_reason", "").strip()
    if submitted and is_manager and not reason:
        form.add_error("override_reason", "Give the reason for booking off hours.")
    return {
        "broken": [(start, [r.text for r in reasons]) for start, reasons in broken],
        "dated": len(broken) > 1 or bool(form.cleaned_data.get("repeat")),
        "is_manager": is_manager,
        "go_ahead": is_manager and bool(reason),
    }


def log_overrides(request, appointments, broken, data, action):
    by_start = {start: reasons for start, reasons in broken}
    for appointment in appointments:
        reasons = by_start.get(appointment.scheduled_start)
        if reasons:
            booking.log_override(appointment, reasons, data["override_reason"], request.user, action)
    if broken:
        messages.warning(request, "Booked off hours. The reason is logged with the job.")


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
            hand_price=inputs.hand_amount,
            hand_minutes=inputs.hand_minutes,
        )
    return initial, inputs


def same_inputs(old, new):
    return old is not None and (
        old.service.pk, old.vehicle_class.pk, getattr(old.size_variant, "pk", None), old.condition_level,
        sorted(a.pk for a in old.add_ons), old.crew_size, old.hand_amount, old.hand_minutes,
    ) == (
        new.service.pk, new.vehicle_class.pk, getattr(new.size_variant, "pk", None), new.condition_level,
        sorted(a.pk for a in new.add_ons), new.crew_size, new.hand_amount, new.hand_minutes,
    )


def appointment_edit(request, pk):
    appointment = get_object_or_404(Appointment.objects.select_related("customer"), pk=pk)
    initial, old_inputs = edit_initial(appointment)
    form = AppointmentForm(request.POST or None, customer=appointment.customer, editing=True, initial=initial)
    alert = None
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        new_inputs = form.inputs()
        broken = []
        calendar_sync.refresh_time_off_for_booking()
        try:
            changed_services = new_inputs is not None and not same_inputs(old_inputs, new_inputs)
            moved = is_moved(form, appointment)
            broken = rules_broken(form, appointment)
            alert = rules_alert(request, form, broken, submitted=True)
            if alert and not alert["go_ahead"]:
                raise booking.RulesBroken(broken)
            if changed_services:
                booking.reprice(appointment, new_inputs, data["reason"])
            appointment.refresh_from_db()
            appointment.vehicle = data["vehicle"]
            appointment.service_address = data.get("address")
            appointment.scheduled_start = form.start()
            appointment.notes = data["notes"]
            drive = drive_from_home(appointment.service_address, appointment.scheduled_start)
            appointment.drive_minutes = drive.minutes if drive else None
            appointment.drive_estimated = drive.estimated if drive else False
            appointment._change_reason = data["reason"] or "Details changed"
            appointment.save()
        except booking.RulesBroken:
            pass
        except (PricingError, booking.BookingError) as error:
            form.add_error("reason" if "reason" in str(error) else None, str(error))
        else:
            messages.success(request, "Saved." + (" The job was re-priced." if changed_services else ""))
            action = RuleOverride.Action.MOVED if moved else RuleOverride.Action.CHANGED
            log_overrides(request, [appointment], broken, data, action)
            if moved:
                scheduling_changes.job_moved(appointment, request.user)
            warn_overlaps(request, appointment)
            return redirect("appointment", pk=appointment.pk)
    context = {"form": form, "customer": appointment.customer, "appointment": appointment, "alert": alert,
               "time_off_warning": calendar_sync.time_off_warning()}
    return render(request, "control/appointment_form.html", context)


def level_reference(form):
    """For a level priced by hand, the job at the highest level with a price
    (Level 2), shown beside the hand price for reference (decision 0103)."""
    data = form.cleaned_data
    service, vehicle_class = data.get("service"), data.get("vehicle_class")
    if service is None or vehicle_class is None:
        return None
    job = reference_price(
        service, vehicle_class, size_variant=data.get("size_variant"), add_ons=list(data.get("add_ons") or []),
        crew_size=data.get("crew_size") or service.default_crew_size, on=data.get("date"),
    )
    return {"job": job, "stay": job.time_on_site} if job else None


@require_POST
def appointment_price(request, customer_pk=None, pk=None):
    """The live price for the booking form, from the pricing engine, as the
    owner changes the service, add-ons, condition, crew or date, and the
    rules alert below the date and time, swapped in out of band (htmx)."""
    appointment = get_object_or_404(Appointment, pk=pk) if pk else None
    customer = appointment.customer if appointment else get_object_or_404(Customer, pk=customer_pk)
    form = AppointmentForm(request.POST, customer=customer, editing=bool(appointment))
    context = {"errors": [], "job": None}
    if form.is_valid() and form.inputs() is None:
        context["errors"] = ["Not priced from the pricebook. Pick a service to price it."]
    elif form.is_valid() and form.inputs().priced_by_hand:
        inputs = form.inputs()
        context["hand"] = {
            "description": hand_description(inputs.service, inputs.condition_level, inputs.add_ons),
            "amount": inputs.hand_amount,
            "minutes": inputs.hand_minutes,
            "crew_size": inputs.crew_size,
        }
        address = form.cleaned_data.get("address")
        if address is not None:
            context["tax"] = tax_line(address, inputs.hand_amount, form.cleaned_data["date"])
            context["total_with_tax"] = inputs.hand_amount + context["tax"].sales_tax
        context["changes_price"] = appointment is not None and not same_inputs(booking.inputs_from_appointment(appointment), inputs)
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
            address = form.cleaned_data.get("address")
            if address is not None:
                context["tax"] = tax_line(address, job.total_before_tax, form.cleaned_data["date"])
                context["total_with_tax"] = job.total_before_tax + context["tax"].sales_tax
            context["changes_price"] = appointment is not None and not same_inputs(booking.inputs_from_appointment(appointment), inputs)
    else:
        context["errors"] = [error for errors in form.errors.values() for error in errors]
    if form.by_quote:
        context["reference"] = level_reference(form)
    # The availability check, as the date, time or anything else that
    # affects it changes: the full check once the job can be priced, and
    # before that the rules the date and time break on their own.
    broken = None
    if form.is_valid() and (appointment is not None or form.inputs() is not None):
        try:
            broken = rules_broken(form, appointment)
        except (PricingError, booking.BookingError):
            pass
    if broken is None:
        broken = rules_broken_so_far(form, appointment)
    if broken is not None:
        context["alert"] = rules_alert(request, form, broken)
        context["alert_known"] = True
    context["form"] = form
    return render(request, "control/_live_price.html", context)


def appointment_context(appointment, user=None, **extra):
    choices = staff_choices(appointment)
    assigned = {assignment.staff_member_id: assignment for assignment in appointment.assignments.all()}
    payments = list(appointment.payments.order_by("paid_at"))
    total = appointment.total_before_tax
    tax = tax_line_for_appointment(appointment)
    context = {
        "tax": tax,
        "total_with_tax": total + tax.sales_tax if tax else total,
        "area": service_area.check(appointment.service_address) if appointment.service_address else None,
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
        "later_visits": later_visits(appointment),
        "overrides": list(appointment.rule_overrides.select_related("made_by").order_by("made_at")),
        "calendar_flags": list(appointment.calendar_flags.order_by("-created_at")[:10]),
        "is_manager": user_is_manager(user) if user is not None else False,
        # A website booking's review flags, and the quote request a job was
        # booked from, with its description and photos for whoever does it.
        "open_flags": appointment.match_flags.filter(resolution="").count(),
        "resolved_flags": appointment.match_flags.exclude(resolution="").count(),
        "quote_requests": list(appointment.quote_requests.prefetch_related("photos")),
    }
    context.update(extra)
    return context


@require_safe
def appointment(request, pk):
    appointment = get_object_or_404(
        Appointment.objects.select_related("customer", "vehicle", "service_address", "series", "quote"), pk=pk
    )
    return render(request, "control/appointment.html", appointment_context(appointment, request.user))


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


def later_visits(appointment):
    """How many booked visits of the job's series come after it."""
    if appointment.series_id is None or appointment.status != Appointment.Status.BOOKED:
        return 0
    return appointment.series.appointments.filter(
        status=Appointment.Status.BOOKED, scheduled_start__gt=appointment.scheduled_start
    ).count()


@require_POST
def appointment_cancel(request, pk):
    """The Cancel job popup's buttons, managers only (decision 0095): the
    customer canceled or Dixie Detail canceled marks the job canceled;
    created by mistake removes it for good after a second confirmation
    (remove=yes). For a series visit, visits=later applies to it and the
    later visits too."""
    appointment = get_object_or_404(Appointment.objects.select_related("customer", "series"), pk=pk)
    if not user_is_manager(request.user):
        messages.error(request, "Only a manager can cancel a job.")
        return redirect("appointment", pk=pk)
    later = request.POST.get("visits") == "later"
    if request.POST.get("remove") == "yes":
        customer = appointment.customer
        try:
            count = booking.remove(appointment, later)
        except booking.BookingError as error:
            messages.error(request, str(error))
            return redirect("appointment", pk=pk)
        messages.success(request, "Removed the job for good." if count == 1 else f"Removed {count} visits for good.")
        return redirect("customer", pk=customer.pk)
    choice = request.POST.get("cancel", "")
    if choice == "mistake":
        # Without the popup's second step: ask once more on a page.
        return render(request, "control/appointment_remove.html", {"appointment": appointment, "later": later})
    try:
        jobs = booking.cancel(appointment, choice, request.user, later)
    except booking.BookingError as error:
        messages.error(request, str(error))
        return redirect("appointment", pk=pk)
    for job in jobs:
        scheduling_changes.job_moved(job, request.user, canceled=True)
    who = Appointment.CanceledBy(choice).label
    messages.success(request, f"{who}. The time is free again." if len(jobs) == 1 else f"{who}: {len(jobs)} visits canceled. Their times are free again.")
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
    return render(request, "control/appointment.html", appointment_context(appointment, request.user, final_form=form), status=400)


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
        return render(request, "control/appointment.html", appointment_context(appointment, request.user, staff_warning=warning), status=400)
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
