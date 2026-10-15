"""Payment methods (payments.md). Kept apart from the models so any app can
import them without importing billing's models."""

from django.db import models


class PaymentMethod(models.TextChoices):
    CARD = "card", "Credit or debit card"
    CASH_APP_PAY = "cash_app_pay", "Cash App Pay"
    CASH_APP_DIRECT = "cash_app_direct", "Cash App to the owner's $cashtag"
    VENMO = "venmo", "Venmo"
    PAYPAL = "paypal", "PayPal"
    CASH = "cash", "Cash"
    BITCOIN = "bitcoin", "Bitcoin"
    CHECK = "check", "Check"
    TRADE = "trade", "Trade (goods instead of money)"
    GIFT_CARD = "gift_card", "Gift card"


# Accepted by the owner case by case and never offered on the website
# (decision 0053).
OWNER_ONLY_METHODS = frozenset({PaymentMethod.CHECK, PaymentMethod.TRADE})

# A gift card is recorded by the owner as a prepayment, not chosen at booking.
NOT_CHOSEN_AT_BOOKING = frozenset({PaymentMethod.GIFT_CARD})


def website_methods():
    """The methods a customer can pick as their preferred method online."""
    return [
        method
        for method in PaymentMethod
        if method not in OWNER_ONLY_METHODS and method not in NOT_CHOSEN_AT_BOOKING
    ]
