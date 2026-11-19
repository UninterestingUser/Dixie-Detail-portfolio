"""What the website reads before it asks for a quote: the published
pricebook, the year, make and model lists, the classify() lookup and the
photo cards (public-api.md). Everything here is public and the same for
every visitor, so it is cacheable."""

from dataclasses import dataclass

from django.conf import settings

from billing.methods import website_methods
from pricebook.models import ConditionLevel, Price, PricebookVersion, Service
from vehicles.classification.lookup import Choice, Question, classify, first_catalog_year, photo_cards, question_for
from vehicles.models import ModelYearClassification, VehicleClass, VehicleModel
from vehicles.vehicle_data.names import load_names

from . import consent, validate
from .http import ApiError, bad_request

MOTORCYCLE = VehicleModel.VehicleType.MOTORCYCLE
VEHICLE = VehicleModel.VehicleType.VEHICLE


def money(amount):
    return f"{amount:.2f}" if amount is not None else None


def published_version():
    version = PricebookVersion.current()
    if version is None:
        raise ApiError(503, "unavailable", "Prices aren't available just now. Please try again later.")
    return version


def bookable_services():
    return Service.objects.filter(
        customer_bookable=True, on_price_list=True, kind__in=[Service.Kind.MAIN, Service.Kind.ADD_ON]
    )


def class_json(vehicle_class):
    return {
        "id": vehicle_class.pk,
        "name": vehicle_class.name,
        "booked_by_quote": vehicle_class.booking == VehicleClass.Booking.QUOTE,
    }


def size_json(size_variant):
    return {"value": size_variant.value, "label": size_variant.label} if size_variant else None


def pricebook():
    """The published pricebook: services, classes, size variants, condition
    levels, "from" prices, and the add-ons that go with each service
    (decision 0106)."""
    version = published_version()
    classes = list(VehicleClass.objects.offered().prefetch_related("size_variants"))
    services = list(bookable_services().order_by("kind", "name"))
    prices = list(
        Price.objects.filter(version=version, service__in=services, vehicle_class__in=classes)
        .select_related("size_variant")
        .order_by("price")
    )
    takes_level = version.condition_service_ids()
    fits = version.add_on_fit_map()
    add_on_ids = [service.pk for service in sorted(services, key=lambda item: item.name) if service.kind == Service.Kind.ADD_ON]
    by_service, by_class = {}, {}
    for price in prices:
        by_service.setdefault(price.service_id, []).append(price)
        service = next(item for item in services if item.pk == price.service_id)
        if service.kind == Service.Kind.MAIN:
            by_class.setdefault(price.vehicle_class_id, []).append(price.price)
    return {
        "pricebook_version": version.number,
        "effective_date": version.effective_date.isoformat(),
        "classes": [
            {
                **class_json(vehicle_class),
                "photo_card": vehicle_class.photo_card or vehicle_class.name,
                "examples": list(vehicle_class.photo_card_examples or []),
                "sizes": [size_json(size) for size in vehicle_class.size_variants.all() if size.active],
                "from_price": money(min(by_class[vehicle_class.pk])) if vehicle_class.pk in by_class else None,
            }
            for vehicle_class in classes
        ],
        # A level booked by quote has no percentage: the job is quoted by hand
        # (decision 0103).
        "condition_levels": [
            {
                "level": level.level,
                "adds_percent": None if level.booked_by_quote else f"{level.adjustment_percent:f}".rstrip("0").rstrip("."),
                "booked_by_quote": level.booked_by_quote,
                "label": level.label,
                "description": level.description,
            }
            for level in ConditionLevel.objects.filter(version=version).order_by("level")
        ],
        "services": [
            {
                "id": service.pk,
                "name": service.name,
                "kind": "add_on" if service.kind == Service.Kind.ADD_ON else "service",
                "description": service.description,
                "condition_applies": service.pk in takes_level,
                # The add-ons offered with this service; none for an add-on.
                "add_ons": [pk for pk in add_on_ids if pk in fits.get(service.pk, set()) and pk in by_service],
                "from_price": money(by_service[service.pk][0].price) if service.pk in by_service else None,
                "prices": [
                    {"class_id": price.vehicle_class_id, "size": price.size_variant.value if price.size_variant else None, "price": money(price.price)}
                    for price in sorted(by_service.get(service.pk, []), key=lambda price: (price.vehicle_class_id, price.size_variant.value if price.size_variant else 0))
                ],
            }
            for service in services
            if service.pk in by_service
        ],
    }


def price_table():
    """Every job the website can book online, priced by the pricing engine:
    each offered class booked online and its sizes, each bookable service,
    each condition level with a price for a service that takes one, and
    every set of the add-ons that go with the service (decision 0106). The website bakes it in at build time
    for the "request a time" form, which shows these totals while the server
    is offline; the browser only looks a total up, never works one out
    (decision 0059). Combinations the pricebook doesn't price are left out."""
    from itertools import combinations

    from pricebook.pricing import PricingError, price_job

    version = published_version()
    services = list(bookable_services().order_by("name"))
    mains = [service for service in services if service.kind == Service.Kind.MAIN]
    add_ons = [service for service in services if service.kind == Service.Kind.ADD_ON]
    fits = version.add_on_fit_map()
    levels = [level.level for level in ConditionLevel.objects.filter(version=version, booked_by_quote=False).order_by("level")]
    takes_level = version.condition_service_ids()
    jobs = []
    for vehicle_class in VehicleClass.objects.offered().filter(booking=VehicleClass.Booking.ONLINE).prefetch_related("size_variants"):
        sizes = [size for size in vehicle_class.size_variants.all() if size.active] or [None]
        for size in sizes:
            for service in mains:
                offered = [item for item in add_ons if item.pk in fits.get(service.pk, set())]
                add_on_sets = [chosen for count in range(len(offered) + 1) for chosen in combinations(offered, count)]
                for level in (levels if service.pk in takes_level else [None]):
                    for chosen in add_on_sets:
                        try:
                            job = price_job(service, vehicle_class, size_variant=size, condition_level=level,
                                            add_ons=chosen, version=version)
                        except PricingError:
                            continue
                        jobs.append({
                            "class_id": vehicle_class.pk,
                            "size": size.value if size else None,
                            "service": service.pk,
                            "condition": level,
                            "add_ons": sorted(item.pk for item in chosen),
                            "total_before_tax": money(job.total_before_tax),
                            "time_on_site_minutes": job.time_on_site.total_minutes,
                            "full_day": job.full_day,
                        })
    return {"pricebook_version": version.number, "effective_date": version.effective_date.isoformat(), "jobs": jobs}


def booking_options():
    """The fixed parts of the booking form: payment methods, the consent
    wording, how long a quote lasts and the photo limits."""
    return {
        "payment_methods": [{"value": method.value, "label": method.label} for method in website_methods()],
        "consent": consent.current(),
        "quote_lifetime_minutes": settings.QUOTE_LIFETIME_MINUTES,
        "photos": {
            "max_per_request": settings.QUOTE_REQUEST_MAX_PHOTOS,
            "max_megabytes": settings.QUOTE_REQUEST_PHOTO_MAX_MB,
            "types": ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"],
        },
    }


# Year, make and model lists ---------------------------------------------------


def years():
    found = ModelYearClassification.objects.order_by("-year").values_list("year", flat=True).distinct()
    return {"years": list(found), "first_year": first_catalog_year()}


def make_spellings(year):
    """{make key: [spellings]} of the makes with a model in year."""
    names = load_names()
    found = {}
    for make in ModelYearClassification.objects.filter(year=year).values_list("vehicle_model__make", flat=True).distinct():
        found.setdefault(names.make_key(make), []).append(make)
    return found


def shown_make(spellings):
    """The spelling to show: one that is not all capitals, if there is one."""
    return sorted(spellings, key=lambda make: (make.isupper(), make))[0]


def makes(year):
    return {"year": year, "makes": sorted((shown_make(spellings) for spellings in make_spellings(year).values()), key=str.casefold)}


def models(year, make):
    spellings = make_spellings(year).get(load_names().make_key(make))
    if not spellings:
        return {"year": year, "make": make, "models": []}
    rows = ModelYearClassification.objects.filter(year=year, vehicle_model__make__in=spellings).values_list(
        "vehicle_model__model", "vehicle_model__vehicle_type"
    )
    found = sorted(set(rows), key=lambda row: (row[0].casefold(), row[1]))
    return {
        "year": year,
        "make": shown_make(spellings),
        "models": [{"name": name, "type": kind, "motorcycle": kind == MOTORCYCLE} for name, kind in found],
    }


# The lookup ---------------------------------------------------------------------


def question_json(question):
    if question is None:
        return None
    return {"key": question.key, "text": question.text, "choices": [{"answer": choice.size, "label": choice.label} for choice in question.choices]}


def card_question(vehicle_class):
    """The size question for a class picked from the photo cards: the class's
    own question, or, when the class has several sizes and no question
    settles them, one built from the sizes' own labels."""
    question = question_for(vehicle_class)
    if question is not None:
        return question
    offered = list(vehicle_class.size_variants.filter(active=True).order_by("value"))
    if len(offered) > 1:
        return Question("size", "Which fits it best?", tuple(Choice(size.value, size.label[:1].upper() + size.label[1:], size.value) for size in offered))
    return None


def cards_json():
    return [
        {
            "class_id": card.vehicle_class.pk,
            "name": card.name,
            "caption": card.caption,
            "examples": card.examples,
            "photo": card.photo,
            "booked_by_quote": card.quote,
        }
        for card in photo_cards()
    ]


@dataclass
class Vehicle:
    """A vehicle as the website gave it, settled to a class and size, or
    with the question still to ask."""

    vehicle_class: VehicleClass = None
    size_variant: object = None
    question: Question = None
    year: int = None
    make: str = ""
    model: str = ""
    vehicle_type: str = VEHICLE
    vehicle_model: VehicleModel = None
    photo_card: bool = False
    # The lookup sent the customer to the photo cards.
    needs_photo_card: bool = False

    @property
    def booked_by_quote(self):
        return self.vehicle_class is not None and self.vehicle_class.booking == VehicleClass.Booking.QUOTE

    @property
    def motorcycle(self):
        return self.vehicle_type == MOTORCYCLE or (self.vehicle_class is not None and self.vehicle_class.name == "Motorcycles")


def parse_vehicle(value, field="vehicle", free_text_with_card=False):
    """{"year", "make", "model", "type"} or {"photo_card": class id}."""
    if not isinstance(value, dict):
        raise bad_request(field)
    if "photo_card" in value:
        optional = ("year", "make", "model") if free_text_with_card else ()
        validate.only(value, ["photo_card"], optional, field=field)
        return {
            "photo_card": validate.integer(value["photo_card"], f"{field}.photo_card", 1, 2**31 - 1),
            "year": validate.integer(value.get("year"), f"{field}.year", 1900, 2100, required=False),
            "make": validate.text(value.get("make"), f"{field}.make", 60, required=False),
            "model": validate.text(value.get("model"), f"{field}.model", 100, required=False),
        }
    validate.only(value, ["year", "make", "model"], ["type"], field=field)
    kind = value.get("type", VEHICLE)
    if kind not in (VEHICLE, MOTORCYCLE):
        raise bad_request(f"{field}.type")
    return {
        "year": validate.integer(value["year"], f"{field}.year", 1900, 2100),
        "make": validate.text(value["make"], f"{field}.make", 60),
        "model": validate.text(value["model"], f"{field}.model", 100),
        "type": kind,
    }


def resolve(vehicle, size=None):
    """The class and size of a parsed vehicle, with size the customer's
    answer to the size question (a size value), if any."""
    if "photo_card" in vehicle:
        vehicle_class = VehicleClass.objects.offered().filter(pk=vehicle["photo_card"]).first()
        if vehicle_class is None:
            raise bad_request("vehicle.photo_card")
        found = Vehicle(vehicle_class, year=vehicle.get("year"), make=vehicle.get("make") or "", model=vehicle.get("model") or "", photo_card=True)
        question = card_question(vehicle_class)
        if question is None:
            offered = list(vehicle_class.size_variants.filter(active=True))
            found.size_variant = offered[0] if len(offered) == 1 else None
        else:
            found.question = question
        return settle(found, size)
    result = classify(vehicle["year"], vehicle["make"], vehicle["model"], vehicle_type=vehicle["type"])
    found = Vehicle(
        result.vehicle_class, result.size_variant, result.question, vehicle["year"], vehicle["make"], vehicle["model"],
        result.vehicle_type or vehicle["type"], result.vehicle_model,
    )
    if result.vehicle_model is not None:
        found.make, found.model = result.vehicle_model.make, result.vehicle_model.model
    if result.needs_photo_card:
        found.needs_photo_card = True
        return found
    return settle(found, size)


def settle(found, size):
    """Answer the size question with a size value, when it was given."""
    if found.question is None or size is None:
        if size is not None and found.question is None and (found.size_variant is None or found.size_variant.value != size):
            raise bad_request("size")
        return found
    if size not in {choice.size for choice in found.question.choices}:
        raise bad_request("size")
    found.size_variant = found.vehicle_class.size_variants.get(value=size)
    found.question = None
    return found


def lookup_json(found):
    """The lookup's answer: the class and size, the question still to ask,
    or the photo cards; and whether the class is booked by quote."""
    answer = {
        "vehicle": {"year": found.year, "make": found.make, "model": found.model, "motorcycle": found.motorcycle},
        "photo_cards": None,
        "class": None,
        "size": None,
        "question": None,
        "booked_by_quote": False,
        "message": "",
    }
    if found.needs_photo_card:
        answer["photo_cards"] = cards_json()
        answer["message"] = "Pick the picture closest to your vehicle."
        return answer
    answer.update(
        {
            "class": class_json(found.vehicle_class),
            "size": size_json(found.size_variant),
            "question": question_json(found.question),
            "booked_by_quote": found.booked_by_quote,
        }
    )
    if found.booked_by_quote:
        answer["message"] = f"{found.vehicle_class.name} are priced by hand. Ask for a quote and we'll reply with a price."
    else:
        answer["message"] = f"{found.vehicle_class.name} identified."
    return answer


def reviews():
    """The shown reviews, in the order the Reviews screen sets: the name as
    shown, the text, the date, the stars (or null) and the link to the
    Google review (or null). Never a combined rating."""
    from marketing.models import Review

    return {
        "reviews": [
            {
                "name": review.name,
                "text": review.text,
                "date": review.reviewed_on.isoformat(),
                "stars": review.stars,
                "link": review.google_url or None,
            }
            for review in Review.objects.filter(shown=True)
        ]
    }
