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


# The list a customer picks from on the website: one entry per method, in
# the order of payment_methods_accepted in data/business.yaml. Cash App is
# one choice there; the two ways it reaches the owner (Cash App Pay in the
# Stripe link, or straight to the $cashtag) are for recording a payment
# only, and a website choice of Cash App is saved as Cash App Pay, the
# route the payment link offers. Each entry: the name in business.yaml,
# then the website's value, its label and the method saved.
WEBSITE_CHOICES = {
    "cash": ("cash", "Cash", PaymentMethod.CASH),
    "card": ("card", "Card", PaymentMethod.CARD),
    "Venmo": ("venmo", "Venmo", PaymentMethod.VENMO),
    "PayPal": ("paypal", "PayPal", PaymentMethod.PAYPAL),
    "Cash App": ("cash_app", "Cash App", PaymentMethod.CASH_APP_PAY),
    "Bitcoin": ("bitcoin", "Bitcoin", PaymentMethod.BITCOIN),
}

# Values an older copy of the booking page may still send, such as a request
# kept while the server was offline: saved as themselves.
EARLIER_WEBSITE_VALUES = {
    PaymentMethod.CASH_APP_PAY.value: PaymentMethod.CASH_APP_PAY,
    PaymentMethod.CASH_APP_DIRECT.value: PaymentMethod.CASH_APP_DIRECT,
}


class WebsiteMethod:
    def __init__(self, value, label, saved):
        self.value, self.label, self.saved = value, label, saved


def website_methods():
    """The methods a customer can pick as their preferred method online, in
    the order of payment_methods_accepted in data/business.yaml. A name
    there without an entry in WEBSITE_CHOICES is an error, so a new method
    is never left off the website by accident."""
    import yaml
    from django.conf import settings

    names = yaml.safe_load((settings.DATA_DIR / "business.yaml").read_text())["payment_methods_accepted"]
    methods = []
    for name in names:
        if name not in WEBSITE_CHOICES:
            raise ValueError(f"No website choice for the payment method {name!r} (billing/methods.py).")
        methods.append(WebsiteMethod(*WEBSITE_CHOICES[name]))
    return methods


def saved_method(value):
    """The method to save for a website value, or None when the website
    doesn't offer it (an owner-only method, a gift card, or anything else)."""
    for method in website_methods():
        if method.value == value:
            return method.saved
    return EARLIER_WEBSITE_VALUES.get(value)


def website_label(saved):
    """The customer's word for a saved method: "Cash App" for either route."""
    for method in website_methods():
        if method.saved == saved:
            return method.label
    if saved == PaymentMethod.CASH_APP_DIRECT:
        return WEBSITE_CHOICES["Cash App"][1]
    return PaymentMethod(saved).label
