"""Strict checks on every input: known fields only, the right type, sane
lengths. A failure names the field and nothing else (http.bad_request)."""

import datetime
import re

from django.core.exceptions import ValidationError
from django.utils import timezone

from core.fields import normalize_phone

from .http import bad_request

# Letters, digits, spaces and the punctuation names, addresses and models use.
PLAIN_TEXT = re.compile(r"^[^\x00-\x1f\x7f<>]*$")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
NUMBER = re.compile(r"^[A-Z0-9]{6,12}$")


def only(data, required=(), optional=(), field="body"):
    """Refuse a dict with a missing required field or an unknown one."""
    if not isinstance(data, dict):
        raise bad_request(field)
    allowed = set(required) | set(optional)
    for name in data:
        if name not in allowed:
            raise bad_request(name if field == "body" else f"{field}.{name}")
    for name in required:
        if name not in data:
            raise bad_request(name if field == "body" else f"{field}.{name}")
    return data


def text(value, field, max_length, required=True, multiline=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise bad_request(field)
    value = value.strip()
    if required and not value:
        raise bad_request(field)
    if len(value) > max_length:
        raise bad_request(field)
    checked = value.replace("\n", " ").replace("\r", " ").replace("\t", " ") if multiline else value
    if not PLAIN_TEXT.match(checked):
        raise bad_request(field)
    return value


def integer(value, field, low, high, required=True):
    if value is None and not required:
        return None
    if isinstance(value, str) and value.strip().isdigit() and len(value.strip()) <= 9:
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise bad_request(field)
    return value


def boolean(value, field):
    if not isinstance(value, bool):
        raise bad_request(field)
    return value


def token(value, field):
    if not isinstance(value, str) or not TOKEN.match(value):
        raise bad_request(field)
    return value


def number(value, field):
    if not isinstance(value, str) or not NUMBER.match(value.strip().upper()):
        raise bad_request(field)
    return value.strip().upper()


def id_list(value, field, max_items=10):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > max_items:
        raise bad_request(field)
    found = [integer(item, field, 1, 2**31 - 1) for item in value]
    if len(set(found)) != len(found):
        raise bad_request(field)
    return found


def phone(value, field="mobile"):
    if not isinstance(value, str) or len(value) > 30:
        raise bad_request(field, "Enter a 10-digit mobile number, such as (423) 555-0142.")
    try:
        digits = normalize_phone(value)
    except ValidationError as error:
        raise bad_request(field, "Enter a 10-digit mobile number, such as (423) 555-0142.") from error
    if not digits:
        raise bad_request(field, "Enter a 10-digit mobile number, such as (423) 555-0142.")
    return digits


def moment(value, field):
    """An ISO 8601 date and time with its offset, such as
    2026-12-08T08:00:00-05:00, as an aware datetime."""
    if not isinstance(value, str) or len(value) > 40:
        raise bad_request(field)
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except ValueError as error:
        raise bad_request(field) from error
    if timezone.is_naive(parsed):
        raise bad_request(field)
    return parsed


def date(value, field):
    if not isinstance(value, str) or len(value) != 10:
        raise bad_request(field)
    try:
        return datetime.date.fromisoformat(value)
    except ValueError as error:
        raise bad_request(field) from error
