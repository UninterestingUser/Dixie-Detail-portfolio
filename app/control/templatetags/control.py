from decimal import Decimal

from django import template
from django.utils import timezone

from core.fields import format_phone
from core.scheduling import format_minutes

register = template.Library()


@register.filter
def money(value):
    """$1,234.50, or -$5.00 for a negative amount."""
    if value is None or value == "":
        return ""
    amount = Decimal(value)
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


@register.filter
def phone(value):
    """10 stored digits as (423) 555-0142."""
    return format_phone(value)


@register.filter
def duration(minutes):
    """90 as "1.5 hours", 30 as "30 minutes"."""
    if minutes is None or minutes == "":
        return ""
    return format_minutes(int(minutes))


@register.filter
def local_time(moment):
    """8:00 AM, in Eastern time."""
    if not moment:
        return ""
    return timezone.localtime(moment).strftime("%-I:%M %p")


@register.filter
def get_item(mapping, key):
    return mapping.get(key) if mapping else None
