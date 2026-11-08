"""What the Jobs calendar should hold, built from the database (decision 0098).

Each booked or completed appointment has a job event covering its whole time
on site and, when its drive from the home base is known, a "Drive to job"
block from the leave time to the arrival time. Each date closed in the
control app has an all-day "Closed" event. Canceled and removed jobs have
none.

The events' IDs are made from a link the app keeps, so the app can find,
restore or delete them without asking Google first: "job" or "drive" and the
appointment's calendar key, or "closed" and the date. Google allows the
letters a to v and digits in an ID, which these are. Each event also carries
the link in its private extended properties, which only this service
account sees; an event without them was added by hand.
"""

import datetime
import hashlib
import json
import uuid

from django.utils import timezone

from appointments.models import Appointment, AppointmentLine
from scheduling.availability import local_midnight
from scheduling.models import DateException, SchedulingSettings

TIME_ZONE = "America/New_York"
# The private extended properties every app-written event carries.
KIND_PROPERTY = "dixie"
LINK_PROPERTY = "dixie_link"
ON_THE_CALENDAR = (Appointment.Status.BOOKED, Appointment.Status.COMPLETED)
# A job imported without its times shows as an hour.
UNKNOWN_LENGTH = datetime.timedelta(hours=1)
SERVICE_KINDS = (AppointmentLine.Kind.SERVICE, AppointmentLine.Kind.CUSTOM)
LISTED_KINDS = (AppointmentLine.Kind.SERVICE, AppointmentLine.Kind.ADD_ON, AppointmentLine.Kind.CUSTOM)


def job_link(appointment):
    return f"job:{appointment.calendar_key.hex}"


def closed_link(day):
    return f"closed:{day.isoformat()}"


def job_event_id(key_hex):
    return f"job{key_hex}"


def drive_event_id(key_hex):
    return f"drive{key_hex}"


def closed_event_id(day):
    return f"closed{day:%Y%m%d}"


def private(kind, link):
    return {"private": {KIND_PROPERTY: kind, LINK_PROPERTY: link}}


def timed(moment):
    return {"dateTime": timezone.localtime(moment).isoformat(), "timeZone": TIME_ZONE}


def clock(moment):
    return timezone.localtime(moment).strftime("%-I:%M %p")


def money(amount):
    return f"${amount:,.2f}"


# Job events -----------------------------------------------------------------


def total_text(appointment):
    total = appointment.total_before_tax
    try:
        from billing.tax import tax_line_for_appointment

        tax = tax_line_for_appointment(appointment)
    except Exception:  # noqa: BLE001 - a missing rate must not stop the sync
        tax = None
    if tax is None:
        return f"{money(total)} before tax"
    return f"{money(total + tax.sales_tax)} with tax"


def job_event(appointment):
    """The job event: the services and vehicle in the title, the address as
    the location for one-tap directions, and the customer's phone, the
    services, the total and the payment method in the notes. Customers are
    never guests (decision 0006)."""
    lines = [line for line in appointment.lines.all() if line.kind in LISTED_KINDS]
    main = [line.description for line in lines if line.kind in SERVICE_KINDS] or ["Job"]
    vehicle = str(appointment.vehicle) if appointment.vehicle else "No vehicle recorded"
    customer = appointment.customer
    notes = [
        f"Customer: {customer}" + (f", {customer.mobile_display}" if customer.mobile else ", no mobile number"),
        "Services: " + (", ".join(line.description for line in lines) or "none listed"),
        f"Total: {total_text(appointment)}",
        "Payment: " + (appointment.get_preferred_payment_method_display() or "not chosen"),
    ]
    if appointment.time_on_site_minutes is None:
        notes.append("Time on site not recorded; shown as an hour.")
    if appointment.status == Appointment.Status.COMPLETED:
        notes.append("Completed.")
    notes.append("Booked in the Dixie Detail control app. Change it there: edits made here are put back.")
    start = appointment.scheduled_start
    end = appointment.ends_at or start + UNKNOWN_LENGTH
    return {
        "summary": f"{', '.join(main)} · {vehicle}",
        "location": str(appointment.service_address) if appointment.service_address else "",
        "description": "\n".join(notes),
        "start": timed(start),
        "end": timed(end),
        "status": "confirmed",
        "transparency": "opaque",
        "extendedProperties": private("job", job_link(appointment)),
    }


def drive_event(appointment, buffer_minutes):
    """The "Drive to job" block, from the leave time (the drive time plus the
    buffer before arrival) to the arrival time, with a notification when it
    starts. None when the drive is not known."""
    if appointment.drive_minutes is None or appointment.service_address is None:
        return None
    arrival = appointment.scheduled_start
    leave = arrival - datetime.timedelta(minutes=appointment.drive_minutes + buffer_minutes)
    drive = f"{appointment.drive_minutes}-minute drive" + (" (estimated)" if appointment.drive_estimated else "")
    return {
        "summary": "Drive to job",
        "location": str(appointment.service_address),
        "description": f"Leave by {clock(leave)}: {drive} plus {buffer_minutes} minutes. Arrive at {clock(arrival)} for {appointment.customer}.",
        "start": timed(leave),
        "end": timed(arrival),
        "status": "confirmed",
        "transparency": "opaque",
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 0}]},
        "extendedProperties": private("drive", job_link(appointment)),
    }


def appointment_events(appointment, buffer_minutes):
    """{event ID: (kind, body)} for one appointment; empty when it is not
    on the calendar."""
    if appointment is None or appointment.status not in ON_THE_CALENDAR:
        return {}
    key = appointment.calendar_key.hex
    found = {job_event_id(key): ("job", job_event(appointment))}
    drive = drive_event(appointment, buffer_minutes)
    if drive is not None:
        found[drive_event_id(key)] = ("drive", drive)
    return found


# Closed days --------------------------------------------------------------


def closed_event(exception):
    day = exception.date
    return {
        "summary": "Closed",
        "description": exception.reason or "Closed in the Dixie Detail control app.",
        "start": {"date": day.isoformat()},
        "end": {"date": (day + datetime.timedelta(days=1)).isoformat()},
        "status": "confirmed",
        "transparency": "opaque",
        "extendedProperties": private("closed", closed_link(day)),
    }


# One link, or everything ------------------------------------------------------


def appointments_with_details():
    return Appointment.objects.select_related("customer", "vehicle", "service_address").prefetch_related("lines")


def for_link(link):
    """{event ID: (kind, body)} the link should have on the calendar now."""
    kind, _, value = link.partition(":")
    if kind == "job":
        appointment = appointments_with_details().filter(calendar_key=uuid.UUID(hex=value)).first()
        return appointment_events(appointment, SchedulingSettings.get().leave_buffer_minutes)
    if kind == "closed":
        day = datetime.date.fromisoformat(value)
        exception = DateException.objects.filter(date=day, kind=DateException.Kind.CLOSED).first()
        return {closed_event_id(day): ("closed", closed_event(exception))} if exception else {}
    return {}


def everything(first_day):
    """{event ID: (kind, link, body)} for every appointment and closed date
    from first_day on: what the Jobs calendar should hold from then."""
    buffer_minutes = SchedulingSettings.get().leave_buffer_minutes
    found = {}
    appointments = appointments_with_details().filter(
        scheduled_start__gte=local_midnight(first_day), status__in=ON_THE_CALENDAR
    ).order_by("scheduled_start")
    for appointment in appointments:
        link = job_link(appointment)
        for event_id, (kind, body) in appointment_events(appointment, buffer_minutes).items():
            found[event_id] = (kind, link, body)
    for exception in DateException.objects.filter(date__gte=first_day, kind=DateException.Kind.CLOSED).order_by("date"):
        found[closed_event_id(exception.date)] = ("closed", closed_link(exception.date), closed_event(exception))
    return found


# Comparing ------------------------------------------------------------------


def moment_of(edge):
    """An event's start or end as comparable text: the date of an all-day
    event, or the instant in UTC."""
    edge = edge or {}
    if "date" in edge:
        return edge["date"]
    if "dateTime" in edge:
        value = datetime.datetime.fromisoformat(edge["dateTime"].replace("Z", "+00:00"))
        return value.astimezone(datetime.timezone.utc).isoformat()
    return ""


COMPARED = {
    "summary": "title",
    "location": "location",
    "description": "notes",
    "start": "time",
    "end": "time",
}


def comparable(event):
    return {
        "summary": event.get("summary", ""),
        "location": event.get("location", ""),
        "description": event.get("description", ""),
        "start": moment_of(event.get("start")),
        "end": moment_of(event.get("end")),
    }


def fingerprint(event):
    """A hash of what the owner sees of an event."""
    return hashlib.sha256(json.dumps(comparable(event), sort_keys=True).encode()).hexdigest()


def differences(google_event, body):
    """The parts the owner changed in Google, in plain words, such as ["time", "title"]."""
    have, want = comparable(google_event), comparable(body)
    names = []
    for field_name, label in COMPARED.items():
        if have[field_name] != want[field_name] and label not in names:
            names.append(label)
    return names


def is_ours(event):
    return KIND_PROPERTY in ((event.get("extendedProperties") or {}).get("private") or {})


def link_of(event):
    return ((event.get("extendedProperties") or {}).get("private") or {}).get(LINK_PROPERTY, "")
