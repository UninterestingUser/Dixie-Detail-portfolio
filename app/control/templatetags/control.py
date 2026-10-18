from decimal import Decimal

from django import template

from core.fields import format_phone

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
