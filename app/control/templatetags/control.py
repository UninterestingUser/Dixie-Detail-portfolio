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


@register.filter
def percent(value):
    """9.750 as "9.75", 7.000 as "7", for a tax rate."""
    if value is None:
        return ""
    text = f"{value:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


@register.filter
def notice_given(delta):
    """How much notice a cancellation gave, from the time between it and
    the job's start: "3 days, 4 hours' notice", "5 hours' notice"."""
    if delta is None:
        return ""
    if delta.total_seconds() <= 0:
        return "Canceled after the start time"
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "Less than an hour's notice"
    days, hours = divmod(hours, 24)
    parts = [f"{days} day{'' if days == 1 else 's'}"] if days else []
    if hours:
        parts.append(f"{hours} hour{'' if hours == 1 else 's'}")
    text = ", ".join(parts)
    return text + ("' notice" if text.endswith("s") else "'s notice")


@register.filter
def pretty_json(value):
    """A stored JSON value, indented for reading."""
    import json

    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True)
