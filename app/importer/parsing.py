"""Parsers for the formats in the Baserow and Setmore exports
(docs/reference/data-migration.md). Each raises ValueError on a value it
cannot read, so the import can report the row instead of guessing."""

import datetime
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

UTC = datetime.timezone.utc
NON_DIGITS = re.compile(r"\D")
# "First Last - 4235551234"; the phone part may be empty or 11 digits.
LINK = re.compile(r"^(?P<name>.*?)\s+-\s*(?P<phone>[\d+() .-]*)$")
# "Crossovers & Wagons - Full Detail (2 Rows)", "Carpet Extraction (1 Row)", "Headlight Restoration"
SERVICE = re.compile(r"^(?:(?P<vehicle_class>.+?) - )?(?P<service>.+?)(?: \((?P<rows>\d+) Rows?\))?$")
SEATING = re.compile(r"^(?P<rows>\d+) Rows?$")

# Old Baserow service names and what they are now (decision 0036).
SERVICE_NAMES = {
    "Interior Detail": "Interior Only",
    "Exterior Detail": "Exterior Only",
    "Paint Correction 1-Step": "1-Step Paint Correction",
    "Paint Correction 2-Step": "2-Step Paint Correction",
}


def squash(value):
    """Trim and collapse runs of spaces, so "Ford  " and "Ford" match."""
    return " ".join((value or "").split())


def money(value):
    """"$1,234", "1,234.50", "'-$5" or "" (None)."""
    text = (value or "").strip().lstrip("'").strip()
    if not text:
        return None
    negative = text.startswith("-")
    text = text.lstrip("-").strip().lstrip("$").replace(",", "")
    try:
        amount = Decimal(text).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError(f"not an amount of money: {value!r}") from None
    return -amount if negative else amount


def utc_datetime(value):
    """"10/21/2026 03:30 PM", which Baserow writes in UTC, as an aware datetime."""
    try:
        return datetime.datetime.strptime(squash(value), "%m/%d/%Y %I:%M %p").replace(tzinfo=UTC)
    except ValueError:
        raise ValueError(f"not a date and time (MM/DD/YYYY hh:mm AM): {value!r}") from None


def date(value):
    """"10/14/2026" as a date."""
    try:
        return datetime.datetime.strptime(squash(value), "%m/%d/%Y").date()
    except ValueError:
        raise ValueError(f"not a date (MM/DD/YYYY): {value!r}") from None


def minutes(value):
    """"7:30" (h:mm) as 450, or None when empty."""
    text = squash(value)
    if not text:
        return None
    match = re.fullmatch(r"(\d+):([0-5]\d)", text)
    if not match:
        raise ValueError(f"not a time in h:mm: {value!r}")
    return int(match.group(1)) * 60 + int(match.group(2))


def phone(value):
    """The last 10 digits of a phone number, or "" when it has fewer than 10.

    Baserow stores some numbers with a leading 1 and Setmore uses +1
    (corrections file, rules.phone_numbers)."""
    digits = NON_DIGITS.sub("", value or "")
    return digits[-10:] if len(digits) >= 10 else ""


@dataclass(frozen=True)
class Link:
    """A link to a customer, written as "First Last - 4235551234"."""

    name: str
    phone: str

    @classmethod
    def parse(cls, value):
        text = squash(value)
        match = LINK.match(text)
        if not match:
            return cls(text.lower(), "")
        return cls(squash(match.group("name")).lower(), phone(match.group("phone")))


@dataclass(frozen=True)
class ServiceItem:
    vehicle_class: str
    service: str
    rows: int


def services(value):
    """A Service Name cell as its items: the main service first, then add-ons.

    "Fullsize Trucks - Full Detail (2 Rows),Carpet Extraction (2 Rows)" gives
    two items. Old names are mapped to current ones."""
    items = []
    for part in (value or "").split(","):
        part = squash(part)
        if not part:
            continue
        match = SERVICE.match(part)
        name = squash(match.group("service"))
        items.append(
            ServiceItem(
                vehicle_class=squash(match.group("vehicle_class") or ""),
                service=SERVICE_NAMES.get(name, name),
                rows=int(match.group("rows")) if match.group("rows") else None,
            )
        )
    return items


def seating(value):
    """"2 Rows" as 2, or None when empty."""
    text = squash(value)
    if not text:
        return None
    match = SEATING.match(text)
    if not match:
        raise ValueError(f"not a seating value like \"2 Rows\": {value!r}")
    return int(match.group("rows"))


def seating_or_none(value):
    try:
        return seating(value)
    except ValueError:
        return None


def year(value):
    text = squash(value)
    if not text:
        return None
    if not re.fullmatch(r"(19|20)\d\d", text):
        raise ValueError(f"not a year: {value!r}")
    return int(text)


def split_list(value):
    """"Cash,Venmo" or "Name One, Name Two" as a list of trimmed values."""
    return [squash(part) for part in (value or "").split(",") if squash(part)]
