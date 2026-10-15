"""Model fields shared by every app: money and rates as exact decimals
(decision 0047) and phone numbers as 10 digits (decision 0049)."""

import re

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

NON_DIGITS = re.compile(r"\D")


def normalize_phone(value):
    """Return a US phone number as its 10 digits, or "" when it is empty.

    Formatting is ignored and a leading country code 1 is dropped. Anything
    that is not then 10 digits raises ValidationError.
    """
    if value is None or not str(value).strip():
        return ""
    digits = NON_DIGITS.sub("", str(value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValidationError(
            "Enter a 10-digit US phone number, such as (423) 555-0142.", code="invalid_phone"
        )
    return digits


def format_phone(digits):
    """Show 10 stored digits as (423) 555-0142."""
    if not digits:
        return ""
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


class PhoneField(models.CharField):
    """A US phone number, always stored as 10 digits or "" (decision 0049).

    Values are normalized when assigned through a form, when saved and when
    used in a lookup, so filter(mobile="(423) 555-0142") finds 4235550142.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_length", 10)
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        return normalize_phone(super().to_python(value))

    def get_prep_value(self, value):
        return normalize_phone(super().get_prep_value(value))

    def pre_save(self, model_instance, add):
        value = normalize_phone(getattr(model_instance, self.attname))
        setattr(model_instance, self.attname, value)
        return value


def phone_check(field_name, name):
    """Database check that a phone column holds 10 digits or nothing."""
    return models.CheckConstraint(
        condition=Q(**{field_name: ""}) | Q(**{f"{field_name}__regex": r"^[0-9]{10}$"}),
        name=name,
    )


class MoneyField(models.DecimalField):
    """An amount in dollars and cents, stored as numeric (decision 0047)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 10)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(*args, **kwargs)


class PercentField(models.DecimalField):
    """A percentage such as 9.75 or 80, stored as numeric (decision 0047)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 6)
        kwargs.setdefault("decimal_places", 3)
        super().__init__(*args, **kwargs)


class HoursField(models.DecimalField):
    """A job length in hours, such as 6.5."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 5)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(*args, **kwargs)
