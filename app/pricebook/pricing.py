"""The pricing engine: the only place a price is worked out (decision 0059).

price_job() takes a service, vehicle class, size variant, condition level,
add-ons, promotions and crew size, and returns the priced lines, the total
before tax and the service time, as docs/reference/pricing.md describes:

1. Base price, looked up by service, vehicle class and size variant. A
   maintenance plan is a percentage of Full Detail (a derived price rule).
2. Condition adjustment, for services it applies to: the level's percentage
   of the base price, rounded to the whole dollar, and the same percentage of
   the base service hours, unrounded (decision 0065).
3. Add-ons, at their own price and hours; the condition level never changes them.
4. Promotions, each on the lines it applies to, never below zero.

Sales tax is added in Phase 3; until then it is zero. issue_quote() stores
the result as a quote, the price of record a booking copies.

How a vehicle class is priced is its price basis. Only the fixed price list
is built; another basis, such as per foot of length, is a new class in
PRICE_BASES and a new VehicleClass.PriceBasis choice, with nothing else changed
(decision 0060).
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from core.scheduling import round_to_nearest, time_on_site
from vehicles.models import VehicleClass

from .models import (
    ConditionLevel,
    DerivedPriceRule,
    Price,
    PricebookVersion,
    PricedLine,
    PricingRules,
    Quote,
    QuoteLine,
    Service,
)

CENT = Decimal("0.01")
DOLLAR = Decimal("1")
ZERO = Decimal("0.00")


class PricingError(ValueError):
    """The job cannot be priced as asked."""


class NotPriced(PricingError):
    """The combination is not in the pricebook, so it does not exist."""


def to_cents(amount):
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def format_percent(percent):
    """10.000 as "10", 12.5 as "12.5"."""
    text = f"{percent:f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def format_hours(hours):
    """6.50 as "6.5", 4.00 as "4"."""
    text = f"{Decimal(hours).quantize(CENT):f}"
    return text.rstrip("0").rstrip(".")


@dataclass(frozen=True)
class BasePrice:
    price: Decimal
    one_person_service_hours: Decimal
    # The size variant the price is for: None when the service ignores size.
    size_variant: object


class PriceListBasis:
    """The fixed price list: one price per service, vehicle class and size
    variant, from the price matrix."""

    def base_price(self, version, service, vehicle_class, size_variant):
        prices = Price.objects.filter(version=version, service=service, vehicle_class=vehicle_class)
        # A service that ignores size, such as Exterior Only, has one price
        # per class with no size variant.
        price = (size_variant and prices.filter(size_variant=size_variant).first()) or prices.filter(
            size_variant__isnull=True
        ).first()
        if price is None:
            size = f", size {size_variant.value}" if size_variant else ""
            raise NotPriced(f"{service} is not priced for {vehicle_class}{size}.")
        return BasePrice(price.price, price.one_person_service_hours, price.size_variant)


PRICE_BASES = {
    VehicleClass.PriceBasis.PRICE_LIST: PriceListBasis(),
}


def base_price(version, service, vehicle_class, size_variant=None):
    """The base price and one-person service hours of one service, before the
    condition adjustment. A derived service takes a percentage of its base
    service's price, rounded to the cent, and the same service hours."""
    basis = PRICE_BASES[vehicle_class.price_basis]
    rule = DerivedPriceRule.objects.filter(version=version, service=service).select_related("base_service").first()
    if rule is None:
        return basis.base_price(version, service, vehicle_class, size_variant)
    base = basis.base_price(version, rule.base_service, vehicle_class, size_variant)
    return BasePrice(to_cents(base.price * rule.percent / 100), base.one_person_service_hours, base.size_variant)


@dataclass
class LineDraft:
    """A priced line not yet stored, with the fields of PricedLine."""

    kind: str
    description: str
    amount: Decimal
    one_person_service_hours: Decimal = None
    vehicle_class_name: str = ""
    size_variant_value: int = None
    size_variant_label: str = ""
    condition_level: int = None
    service: object = None
    promotion: object = None
    pricebook_version: object = None
    vehicle_class: object = None
    size_variant: object = None


@dataclass
class PricedJob:
    version: PricebookVersion
    service: Service
    vehicle_class: VehicleClass
    size_variant: object
    condition_level: int
    add_ons: list
    promotions: list
    crew_size: int
    lines: list = field(default_factory=list)
    total_before_tax: Decimal = ZERO
    one_person_service_hours: Decimal = Decimal("0")
    # Service time for the crew, rounded to the nearest 15 minutes.
    service_minutes: int = 0
    full_day_time_on_site_hours: Decimal = None

    @property
    def time_on_site(self):
        """Setup + service time + breakdown for this crew."""
        return time_on_site(self.service_minutes, self.crew_size)

    @property
    def one_person_time_on_site(self):
        return time_on_site(round_to_nearest(self.one_person_service_hours * 60, 1), 1)

    @property
    def full_day(self):
        """Flagged for a second person: one-person time on site at or above the threshold."""
        return self.one_person_time_on_site.total_minutes >= self.full_day_time_on_site_hours * 60


def _service_line(version, service, vehicle_class, base, kind, condition_level=None):
    return LineDraft(
        kind=kind,
        description=service.name,
        amount=base.price,
        one_person_service_hours=base.one_person_service_hours,
        vehicle_class_name=vehicle_class.name,
        size_variant_value=base.size_variant.value if base.size_variant else None,
        size_variant_label=base.size_variant.label if base.size_variant else "",
        condition_level=condition_level,
        service=service,
        pricebook_version=version,
        vehicle_class=vehicle_class,
        size_variant=base.size_variant,
    )


def promotion_valid_on(promotion, on):
    return not (promotion.starts_on and on < promotion.starts_on) and not (
        promotion.ends_on and on > promotion.ends_on
    )


def price_job(
    service,
    vehicle_class,
    size_variant=None,
    condition_level=None,
    add_ons=(),
    promotions=(),
    crew_size=None,
    version=None,
    on=None,
    check_promotion_dates=True,
):
    """Price one job. version defaults to the published version in effect on
    the date `on` (today by default). Raises PricingError, or NotPriced for a
    combination missing from the pricebook."""
    on = on or timezone.localdate()
    version = version or PricebookVersion.current(on)
    if version is None:
        raise PricingError("No published pricebook version is in effect.")
    add_ons, promotions = list(add_ons), list(promotions)

    if service.kind not in (Service.Kind.MAIN, Service.Kind.MAINTENANCE_PLAN) or not service.on_price_list:
        raise PricingError(f"{service} is not a service on the price list.")
    if not vehicle_class.active:
        raise PricingError(f"{vehicle_class} is retired and cannot be priced.")
    if size_variant is not None:
        if size_variant.vehicle_class_id != vehicle_class.pk:
            raise PricingError(f"{size_variant} does not belong to {vehicle_class}.")
        if not size_variant.active:
            raise PricingError(f"{size_variant} is retired and cannot be priced.")
    for add_on in add_ons:
        if add_on.kind != Service.Kind.ADD_ON or not add_on.on_price_list:
            raise PricingError(f"{add_on} is not an add-on on the price list.")
    if len({add_on.pk for add_on in add_ons}) != len(add_ons):
        raise PricingError("An add-on is listed twice.")
    if len({promotion.pk for promotion in promotions}) != len(promotions):
        raise PricingError("A promotion is listed twice.")
    crew_size = crew_size or service.default_crew_size
    if crew_size not in (1, 2):
        raise PricingError("A crew is one or two people.")
    rules = PricingRules.objects.filter(version=version).first()
    if rules is None:
        raise PricingError(f"Pricebook version {version.number} has no pricing rules.")

    job = PricedJob(
        version=version,
        service=service,
        vehicle_class=vehicle_class,
        size_variant=size_variant,
        condition_level=condition_level,
        add_ons=add_ons,
        promotions=promotions,
        crew_size=crew_size,
        full_day_time_on_site_hours=rules.full_day_time_on_site_hours,
    )

    # 1. Base price.
    base = base_price(version, service, vehicle_class, size_variant)
    level = None
    if service.condition_applies:
        if condition_level is None:
            raise PricingError(f"{service} needs a condition level.")
        level = ConditionLevel.objects.filter(version=version, level=condition_level).first()
        if level is None:
            raise PricingError(f"Condition level {condition_level} is not in pricebook version {version.number}.")
    job.lines.append(
        _service_line(version, service, vehicle_class, base, PricedLine.Kind.SERVICE, level and level.level)
    )

    # 2. Condition adjustment: the level's percentage of the main service's
    # base price, rounded to the whole dollar, and of its base service hours,
    # unrounded (decision 0065). Add-ons, maintenance plans, setup and
    # breakdown are never adjusted. A level that adds nothing has no line.
    if level is not None and level.adjustment_percent:
        adjustment = (base.price * level.adjustment_percent / 100).quantize(DOLLAR, rounding=ROUND_HALF_UP)
        job.lines.append(
            LineDraft(
                kind=PricedLine.Kind.CONDITION,
                description=f"Condition level {level.level} (+{format_percent(level.adjustment_percent)}%)",
                amount=to_cents(adjustment),
                one_person_service_hours=base.one_person_service_hours * level.adjustment_percent / 100,
                condition_level=level.level,
                service=service,
                pricebook_version=version,
                vehicle_class_name=vehicle_class.name,
                vehicle_class=vehicle_class,
            )
        )

    # 3. Add-ons, at their own price for the class and size variant.
    for add_on in add_ons:
        job.lines.append(
            _service_line(
                version,
                add_on,
                vehicle_class,
                base_price(version, add_on, vehicle_class, size_variant),
                PricedLine.Kind.ADD_ON,
            )
        )

    # 4. Promotions, each on the lines for the services it applies to, after
    # any earlier promotion, so the total never goes below zero.
    total = sum((line.amount for line in job.lines), ZERO)
    for promotion in promotions:
        if not promotion.active:
            raise PricingError(f"{promotion} is not active.")
        if check_promotion_dates and not promotion_valid_on(promotion, on):
            raise PricingError(f"{promotion} is not valid on {on}.")
        eligible_ids = set(promotion.services.values_list("pk", flat=True))
        eligible = sum(
            (line.amount for line in job.lines if line.amount > 0 and (not eligible_ids or line.service.pk in eligible_ids)),
            ZERO,
        )
        if not eligible:
            raise PricingError(f"{promotion} does not apply to these services.")
        discount = to_cents(promotion.discount_on(min(eligible, total)))
        job.lines.append(
            LineDraft(
                kind=PricedLine.Kind.PROMOTION,
                description=promotion.name,
                amount=-discount,
                promotion=promotion,
                pricebook_version=version,
            )
        )
        total -= discount

    job.total_before_tax = total
    job.one_person_service_hours = sum(
        (line.one_person_service_hours for line in job.lines if line.one_person_service_hours is not None),
        Decimal("0"),
    )
    factor = rules.two_person_time_factor if crew_size == 2 else Decimal("1")
    job.service_minutes = round_to_nearest(
        job.one_person_service_hours * 60 * factor, rules.service_time_rounding_minutes
    )
    return job


@transaction.atomic
def issue_quote(service, vehicle_class, **inputs):
    """Price a job and store it as a quote, the price of record (decision 0059).
    Only a published version can be quoted. Sales tax is zero until Phase 3."""
    job = price_job(service, vehicle_class, **inputs)
    if not job.version.is_published:
        raise PricingError("Quotes are priced from a published pricebook version.")
    stay = job.time_on_site
    quote = Quote.objects.create(
        pricebook_version=job.version,
        service=job.service,
        vehicle_class=job.vehicle_class,
        size_variant=job.size_variant,
        condition_level=job.condition_level,
        crew_size=job.crew_size,
        total_before_tax=job.total_before_tax,
        tax_rate=Decimal("0"),
        sales_tax=ZERO,
        total=job.total_before_tax,
        one_person_service_hours=job.one_person_service_hours,
        service_minutes=stay.service_minutes,
        setup_minutes=stay.setup_minutes,
        breakdown_minutes=stay.breakdown_minutes,
        time_on_site_minutes=stay.total_minutes,
        full_day=job.full_day,
    )
    quote.add_ons.set(job.add_ons)
    quote.promotions.set(job.promotions)
    for position, line in enumerate(job.lines):
        QuoteLine.objects.create(quote=quote, position=position, **vars(line))
    return quote
