"""Quiet matching (returning-customers.md, decisions 0034 and 0067).

A website booking or request is matched on its 10-digit mobile number
against every customer's number and every second contact's. A match puts it
on that customer; no match makes a new customer. Nothing here is ever shown
on the website: the public API's answers are built only from the quote, the
address and the booking itself.

When the booking's name, address or vehicle differs from the record, it
still goes on the customer, and a MatchFlag shows the owner both versions
with four ways to resolve it (resolve()). The job always uses the address
and vehicle as booked, so drive time, tax and price are right whatever the
owner decides later.

A request (a quote request, an offline request or a second vehicle the same
day) is matched the same way when it arrives, but any address or vehicle it
brings is held off the record (inactive) and its flags wait in its intake
until it is booked (release()).
"""

import re
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from appointments.models import Appointment, MatchFlag
from vehicles.models import Vehicle

from .models import Address, Consent, Customer, SecondContact

# Common street words written either way, so "123 Main Street" and "123
# Main St" are the same address.
STREET_WORDS = {
    "street": "st", "road": "rd", "drive": "dr", "avenue": "ave", "lane": "ln", "court": "ct", "circle": "cir",
    "boulevard": "blvd", "parkway": "pkwy", "highway": "hwy", "place": "pl", "terrace": "ter", "trail": "trl",
    "north": "n", "south": "s", "east": "e", "west": "w",
    "northeast": "ne", "northwest": "nw", "southeast": "se", "southwest": "sw",
    "apartment": "apt", "suite": "ste", "unit": "unit", "number": "", "#": "",
}


def words(text):
    """Lowercase words, punctuation and extra spaces ignored."""
    return re.sub(r"[^a-z0-9#' ]+", " ", (text or "").lower()).split()


def name_key(text):
    return " ".join(words(text))


def color_key(text):
    """Capital letters and extra spaces ignored, so "dark blue" matches
    "Dark  Blue" (decision 0067)."""
    return " ".join((text or "").lower().split())


def model_key(text):
    """Make or model, letters and digits only: "F-150" is "f150"."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def street_key(text):
    return " ".join(part for part in (STREET_WORDS.get(word, word) for word in words(text)) if part)


@dataclass
class Given:
    """A booking or request as the customer typed it. address is an unsaved
    Address made from the verified place; vehicle holds Vehicle fields."""

    first_name: str
    last_name: str
    mobile: str
    address: Address | None
    vehicle: dict | None
    is_test: bool = False

    @property
    def full_name(self):
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    @property
    def vehicle_text(self):
        return str(Vehicle(**self.vehicle)) if self.vehicle else ""


@dataclass
class Intake:
    """Where matching put a booking or request."""

    customer: Customer
    address: Address | None
    vehicle: Vehicle | None
    matched: bool
    contact: SecondContact | None = None
    flags: list = field(default_factory=list)
    new_address: bool = False
    new_vehicle: bool = False
    given: Given = None
    consent_ids: list = field(default_factory=list)

    def as_json(self):
        """What the review queue needs later, kept on the job or request."""
        given = self.given
        return {
            "matched": self.matched,
            "contact_id": self.contact.pk if self.contact else None,
            "first_name": given.first_name,
            "last_name": given.last_name,
            "mobile": given.mobile,
            "vehicle_text": given.vehicle_text,
            "color": (given.vehicle or {}).get("color", ""),
            "new_address_id": self.address.pk if self.new_address and self.address else None,
            "new_vehicle_id": self.vehicle.pk if self.new_vehicle and self.vehicle else None,
            "consent_ids": list(self.consent_ids),
            "flags": self.flags,
        }


# Finding the customer -------------------------------------------------------


def same_name(first, last, record_first, record_last):
    """The first names agree, and the last names too when the booking gave one."""
    if name_key(first) != name_key(record_first):
        return False
    return not name_key(last) or name_key(last) == name_key(record_last)


def same_contact_name(first, last, contact_name):
    full = name_key(f"{first} {last}")
    contact = name_key(contact_name)
    if full == contact:
        return True
    return not name_key(last) and contact.split()[:1] == [name_key(first)]


def find_match(mobile, is_test=False, first_name="", last_name=""):
    """(customer, second contact or None) for the number, or (None, None).

    A customer's own number comes before a second contact's. When several
    customers share the number, the one whose name the booking gave comes
    first, then the one booked most recently. Test bookings match only test
    customers, and real bookings only real ones.
    """
    if not mobile:
        return None, None
    customers = list(
        Customer.objects.filter(mobile=mobile, is_test=is_test)
        .annotate(last_job=Max("appointments__scheduled_start"))
        .order_by("-last_job", "-created_at", "-pk")
    )
    # Max puts customers without a job first in a descending sort; put them last.
    customers.sort(key=lambda customer: customer.last_job is None)
    if customers:
        named = [customer for customer in customers if same_name(first_name, last_name, customer.first_name, customer.last_name)]
        return (named or customers)[0], None
    contacts = list(
        SecondContact.objects.filter(phone=mobile, customer__is_test=is_test).select_related("customer").order_by("-customer__created_at", "-pk")
    )
    if contacts:
        named = [contact for contact in contacts if same_contact_name(first_name, last_name, contact.name)]
        contact = (named or contacts)[0]
        return contact.customer, contact
    return None, None


# Addresses --------------------------------------------------------------------


def same_address(address, other):
    if address.google_place_id and address.google_place_id == other.google_place_id:
        return True
    return (
        street_key(address.line1) == street_key(other.line1)
        and street_key(address.line2) == street_key(other.line2)
        and (address.zip_code or "")[:5] == (other.zip_code or "")[:5]
    )


def find_address(customer, booked):
    for address in customer.addresses.filter(active=True).order_by("pk"):
        if same_address(address, booked):
            return address
    return None


def fill_verification(address, booked):
    """An unverified record address the booking's verified place matched
    takes the place's location and tax, so the job's drive time and tax are
    right. Its parts are not changed."""
    if address.verified and address.point is not None:
        return address
    for name in ("county", "latitude", "longitude", "google_place_id", "verification", "verified_at", "tax_jurisdiction",
                 "tax_needs_check", "tax_note"):
        setattr(address, name, getattr(booked, name))
    address._verified_now = True
    address._change_reason = "Verified from a website booking at the same address"
    address.save()
    return address


# Vehicles ---------------------------------------------------------------------


def same_vehicle(vehicle, given):
    """Same make and model, and the same year when both have one."""
    if vehicle.vehicle_model_id and given.get("vehicle_model") is not None:
        same_model = vehicle.vehicle_model_id == given["vehicle_model"].pk
    else:
        same_model = bool(model_key(given.get("make")) and model_key(given.get("model"))) and (
            model_key(vehicle.make) == model_key(given.get("make")) and model_key(vehicle.model) == model_key(given.get("model"))
        )
    if not same_model:
        return False
    year = given.get("year")
    return not vehicle.year or not year or vehicle.year == year


def vehicle_matches(customer, given):
    return [vehicle for vehicle in customer.vehicles.filter(active=True).order_by("pk") if same_vehicle(vehicle, given)]


def pick_by_color(vehicles, color):
    """The one vehicle whose recorded color is the booking's, or None."""
    wanted = color_key(color)
    if not wanted:
        return None
    found = [vehicle for vehicle in vehicles if color_key(vehicle.color) == wanted]
    return found[0] if len(found) == 1 else None


# Taking a booking in ------------------------------------------------------------


def new_records(customer, given, active=True):
    address = vehicle = None
    if given.address is not None:
        address = clone_address(given.address, customer, active)
    if given.vehicle is not None:
        vehicle = Vehicle.objects.create(customer=customer, active=active, **given.vehicle)
    return address, vehicle


def clone_address(address, customer, active=True):
    copy = Address(customer=customer, active=active)
    for name in (*Address.PARTS, "county", "latitude", "longitude", "google_place_id", "verification", "verified_at",
                 "tax_jurisdiction", "tax_needs_check", "tax_note", "approved_out_of_area"):
        setattr(copy, name, getattr(address, name))
    copy._verified_now = True
    copy.save()
    return copy


def lines(items):
    return "\n".join(str(item) for item in items)


@transaction.atomic
def take_in(given, source="Website", hold=False):
    """Match a booking or request and put it on a customer. Returns an
    Intake with the customer, the address and vehicle the job uses, and
    the flags to raise, as dicts, once the job exists (raise_flags()).

    With hold, a new address or vehicle is kept off the record (inactive)
    until the request is booked.
    """
    customer, contact = find_match(given.mobile, given.is_test, given.first_name, given.last_name)
    if customer is None:
        customer = Customer.objects.create(
            first_name=given.first_name, last_name=given.last_name, mobile=given.mobile, source=source, is_test=given.is_test,
        )
        address, vehicle = new_records(customer, given)
        return Intake(customer, address, vehicle, matched=False, new_address=address is not None,
                      new_vehicle=vehicle is not None, given=given)

    intake = Intake(customer, None, None, matched=True, contact=contact, given=given)
    # The customer's own name, or any of their second contacts' names.
    named = same_name(given.first_name, given.last_name, customer.first_name, customer.last_name) or any(
        same_contact_name(given.first_name, given.last_name, other.name) for other in customer.second_contacts.all()
    )
    if not named:
        record = str(customer) + (f" (second contact: {contact.name})" if contact else "")
        intake.flags.append({"field": MatchFlag.Field.NAME, "booked_value": given.full_name, "record_value": record})

    if given.address is not None:
        existing = find_address(customer, given.address)
        if existing is not None:
            intake.address = fill_verification(existing, given.address)
        else:
            others = list(customer.addresses.filter(active=True).order_by("pk"))
            intake.address = clone_address(given.address, customer, active=not hold)
            intake.new_address = True
            if others:
                intake.flags.append({
                    "field": MatchFlag.Field.ADDRESS, "booked_value": str(intake.address), "record_value": lines(others),
                    "booked_address_id": intake.address.pk, "record_choices": [address.pk for address in others],
                })

    if given.vehicle is not None:
        same = vehicle_matches(customer, given.vehicle)
        chosen = same[0] if len(same) == 1 else pick_by_color(same, given.vehicle.get("color"))
        if chosen is not None:
            intake.vehicle = chosen
        else:
            others = same or list(customer.vehicles.filter(active=True).order_by("pk"))
            intake.vehicle = Vehicle.objects.create(customer=customer, active=not hold, **given.vehicle)
            intake.new_vehicle = True
            if others:
                intake.flags.append({
                    "field": MatchFlag.Field.VEHICLE, "booked_value": str(intake.vehicle), "record_value": lines(others),
                    "booked_vehicle_id": intake.vehicle.pk, "record_choices": [vehicle.pk for vehicle in others],
                    "identical_vehicles": len(same) > 1,
                })
    return intake


def raise_flags(appointment, intake_json):
    """Create the review flags a booking's intake holds, on its job."""
    made = []
    for draft in (intake_json or {}).get("flags", []):
        made.append(MatchFlag.objects.create(
            appointment=appointment,
            customer=appointment.customer,
            field=draft["field"],
            booked_value=draft["booked_value"],
            record_value=draft.get("record_value", ""),
            booked_address_id=draft.get("booked_address_id"),
            booked_vehicle_id=draft.get("booked_vehicle_id"),
            record_choices=draft.get("record_choices", []),
            identical_vehicles=draft.get("identical_vehicles", False),
        ))
    return made


@transaction.atomic
def release(appointment, intake_json):
    """A request has been booked as this job: put the address and vehicle it
    brought on the record, keep its intake on the job, and raise its flags."""
    intake_json = intake_json or {}
    for model, key in ((Address, "new_address_id"), (Vehicle, "new_vehicle_id")):
        if intake_json.get(key):
            model.objects.filter(pk=intake_json[key], customer=appointment.customer).update(active=True)
    appointment.intake = intake_json
    appointment.save(update_fields=["intake"])
    return raise_flags(appointment, intake_json)


# Resolving a flag -------------------------------------------------------------


class ResolveError(ValueError):
    """The flag can't be resolved as asked."""


def choices_of(flag):
    """The record's addresses or vehicles the flag lists, still on file."""
    model = Address if flag.field == MatchFlag.Field.ADDRESS else Vehicle
    found = {item.pk: item for item in model.objects.filter(pk__in=flag.record_choices or [], customer=flag.customer)}
    return [found[pk] for pk in flag.record_choices or [] if pk in found]


def actions_for(flag):
    """[(resolution, label, needs a pick)] the flag offers."""
    if flag.field == MatchFlag.Field.VEHICLE and flag.identical_vehicles:
        return [
            (MatchFlag.Resolution.UPDATE_RECORD, "It was this vehicle; record the color", True),
            (MatchFlag.Resolution.KEEP_RECORD, "It was this vehicle; keep the record as it is", True),
            (MatchFlag.Resolution.ADD_ALONGSIDE, "Add it as another vehicle", False),
            (MatchFlag.Resolution.MOVE_TO_NEW_CUSTOMER, "Move the booking to a new customer", False),
        ]
    labels = {
        MatchFlag.Field.NAME: ("Change the name on the record", "Keep the record's name", "Add as a second contact"),
        MatchFlag.Field.ADDRESS: ("Use the new address instead", "Keep the record's address", "Add it as another address"),
        MatchFlag.Field.VEHICLE: ("It replaces this vehicle", "Keep the record's vehicles", "Add it as another vehicle"),
    }[flag.field]
    pick = flag.field == MatchFlag.Field.VEHICLE and len(flag.record_choices or []) > 1
    return [
        (MatchFlag.Resolution.UPDATE_RECORD, labels[0], pick),
        (MatchFlag.Resolution.KEEP_RECORD, labels[1], False),
        (MatchFlag.Resolution.ADD_ALONGSIDE, labels[2], False),
        (MatchFlag.Resolution.MOVE_TO_NEW_CUSTOMER, "Move the booking to a new customer", False),
    ]


def close(flag, resolution, user, note):
    flag.resolution = resolution
    flag.resolution_note = note[:300]
    flag.resolved_at = timezone.now()
    flag.resolved_by = user
    flag.save(update_fields=["resolution", "resolution_note", "resolved_at", "resolved_by", "booked_address", "booked_vehicle"])


def picked(flag, choice):
    choices = choices_of(flag)
    if len(choices) == 1 and not flag.identical_vehicles and choice in (None, ""):
        return choices[0]
    for item in choices:
        if str(item.pk) == str(choice):
            return item
    raise ResolveError("Pick which of the record's vehicles it was.")


def booking_name(appointment):
    reference = appointment.reference or f"job {appointment.pk}"
    return f"website booking {reference}"


def vehicle_in_use(vehicle, but=None):
    jobs = vehicle.appointments.all()
    if but is not None:
        jobs = jobs.exclude(pk=but.pk)
    return jobs.exists() or vehicle.recurringseries_set.exists()


@transaction.atomic
def resolve(flag, resolution, user, choice=None):
    """Resolve a flag with one of the four actions. Every choice is logged on
    the flag, with who and when, and every record change in its history."""
    if not flag.is_open:
        raise ResolveError("This difference has already been resolved.")
    if resolution == MatchFlag.Resolution.MOVE_TO_NEW_CUSTOMER:
        return move_to_new_customer(flag.appointment, user)
    if resolution not in MatchFlag.Resolution.values:
        raise ResolveError("Choose what to do.")
    appointment = flag.appointment
    handler = {MatchFlag.Field.NAME: resolve_name, MatchFlag.Field.ADDRESS: resolve_address, MatchFlag.Field.VEHICLE: resolve_vehicle}[flag.field]
    note = handler(flag, resolution, choice, appointment)
    close(flag, resolution, user, note)
    return flag


def resolve_name(flag, resolution, choice, appointment):
    customer = flag.customer
    intake = appointment.intake or {}
    first, last = intake.get("first_name", ""), intake.get("last_name", "")
    if resolution == MatchFlag.Resolution.UPDATE_RECORD:
        customer.first_name, customer.last_name = first or customer.first_name, last
        customer._change_reason = f"Name changed from the {booking_name(appointment)}"
        customer.save()
        return f"Changed the name to {customer}"
    if resolution == MatchFlag.Resolution.ADD_ALONGSIDE:
        contact = SecondContact(customer=customer, name=flag.booked_value, phone=intake.get("mobile") or customer.mobile,
                                notes=f"Added from the {booking_name(appointment)}.")
        contact._change_reason = f"Added from the {booking_name(appointment)}"
        contact.save()
        return f"Added {contact.name} as a second contact"
    return "Kept the record's name"


def resolve_address(flag, resolution, choice, appointment):
    booked = flag.booked_address
    if booked is None:
        raise ResolveError("The booked address is no longer on file.")
    if resolution == MatchFlag.Resolution.UPDATE_RECORD:
        replaced = [address for address in choices_of(flag) if address.active and address.pk != booked.pk]
        for address in replaced:
            address.active = False
            address._change_reason = f"Replaced by the address on the {booking_name(appointment)}"
            address.save()
        set_active(booked, True, f"The address on the {booking_name(appointment)}")
        return f"Used {booked} instead of {lines(replaced) or 'the old address'}".replace("\n", "; ")
    if resolution == MatchFlag.Resolution.KEEP_RECORD:
        set_active(booked, False, f"Kept off the record after the {booking_name(appointment)}; the job still uses it")
        return f"Kept the record's address; {booked} stays on this job only"
    set_active(booked, True, f"Added from the {booking_name(appointment)}")
    return f"Added {booked} as another address"


def set_active(item, active, reason):
    if item.active != active:
        item.active = active
        item._change_reason = reason
        item.save()


def resolve_vehicle(flag, resolution, choice, appointment):
    booked = flag.booked_vehicle
    intake = appointment.intake or {}
    if flag.identical_vehicles and resolution in (MatchFlag.Resolution.UPDATE_RECORD, MatchFlag.Resolution.KEEP_RECORD):
        it = picked(flag, choice)
        color = (intake.get("color") or "").strip()
        note = f"Picked {it}"
        if resolution == MatchFlag.Resolution.UPDATE_RECORD and color and color_key(color) != color_key(it.color):
            it.color = color
            it._change_reason = f"Color from the {booking_name(appointment)}"
            it.save()
            note = f"Picked {it}, recording the color"
        appointment.vehicle = it
        appointment._change_reason = f"Vehicle picked from the review queue: {it}"
        appointment.save()
        if booked is not None and booked.pk != it.pk and not vehicle_in_use(booked):
            flag.booked_vehicle = None
            booked.delete()
        return note
    if booked is None:
        raise ResolveError("The booked vehicle is no longer on file.")
    if resolution == MatchFlag.Resolution.UPDATE_RECORD:
        old = picked(flag, choice)
        set_active(old, False, f"Replaced by the vehicle on the {booking_name(appointment)}")
        set_active(booked, True, f"The vehicle on the {booking_name(appointment)}")
        return f"{booked} replaces {old}"
    if resolution == MatchFlag.Resolution.KEEP_RECORD:
        set_active(booked, False, f"Kept off the record after the {booking_name(appointment)}; the job still uses it")
        return f"Kept the record's vehicles; {booked} stays on this job only"
    set_active(booked, True, f"Added from the {booking_name(appointment)}")
    return f"Added {booked} as another vehicle"


@transaction.atomic
def move_to_new_customer(appointment, user):
    """Someone else shares the number: the booking goes to a new customer
    with the name it gave, taking the address, vehicle and consent answers
    it brought, or copies of the record's when it matched them. Every open
    flag on the job is closed with this choice."""
    intake = appointment.intake or {}
    old = appointment.customer
    new = Customer.objects.create(
        first_name=intake.get("first_name") or old.first_name, last_name=intake.get("last_name", ""),
        mobile=intake.get("mobile") or old.mobile, source="Website", is_test=old.is_test,
    )
    reason = f"Moved from {old} after the {booking_name(appointment)}"
    address = appointment.service_address
    if address is not None:
        if address.pk == intake.get("new_address_id") and not address.appointments.exclude(pk=appointment.pk).exists():
            address.customer, address.active = new, True
            address._change_reason = reason
            address.save()
        else:
            address = clone_address(address, new)
    vehicle = appointment.vehicle
    if vehicle is not None:
        if vehicle.pk == intake.get("new_vehicle_id") and not vehicle_in_use(vehicle, but=appointment):
            vehicle.customer, vehicle.active = new, True
            vehicle._change_reason = reason
            vehicle.save()
        else:
            vehicle = Vehicle.objects.create(
                customer=new, vehicle_model=vehicle.vehicle_model, year=vehicle.year, make=vehicle.make, model=vehicle.model,
                color=(intake.get("color") or "").strip(), vehicle_class=vehicle.vehicle_class, size_variant=vehicle.size_variant,
            )
    Consent.objects.filter(pk__in=intake.get("consent_ids") or [], customer=old).update(customer=new)
    appointment.customer, appointment.service_address, appointment.vehicle = new, address, vehicle
    appointment._change_reason = reason
    appointment.save()
    from publicapi.models import QuoteRequest, SecondVehicleRequest, TimeRequest

    QuoteRequest.objects.filter(appointment=appointment).update(customer=new)
    TimeRequest.objects.filter(appointment=appointment).update(customer=new)
    SecondVehicleRequest.objects.filter(appointment=appointment).update(customer=new)
    note = f"Moved the booking to a new customer, {new}"
    for flag in appointment.match_flags.filter(resolution=""):
        close(flag, MatchFlag.Resolution.MOVE_TO_NEW_CUSTOMER, user, note)
    return new
