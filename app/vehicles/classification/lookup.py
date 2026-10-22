"""classify(): the vehicle class, size and price basis of one vehicle, as
the booking form asks for it by year, make and model.

The answer comes from the model year's saved classification, so a rule
change reaches bookings only once classify_vehicles applies it. A
customer's vehicle with its own override beats it. A year before the
catalog starts, a model not in the catalog, and a model year waiting in the
review queue with no class yet all fall back to the photo cards, one per
active vehicle class.
"""

from dataclasses import dataclass, field

from vehicles.models import ModelYearClassification, VehicleClass, VehicleModel
from vehicles.vehicle_data.names import load_names

from .seed import read_data

Measures = VehicleClass.Measures


class How:
    RULE = "rule"
    MODEL_OVERRIDE = "model override"
    VEHICLE_OVERRIDE = "vehicle override"
    REVIEW_QUEUE = "review queue"
    PHOTO_CARDS = "photo cards"


@dataclass(frozen=True)
class Choice:
    answer: object
    label: str
    size: int  # the size variant's value


@dataclass(frozen=True)
class Question:
    key: str
    text: str
    choices: tuple


QUESTIONS = {
    Measures.DOORS: Question(
        "doors", "Two doors or four doors?", (Choice(2, "Two doors", 1), Choice(4, "Four doors", 2))
    ),
    Measures.CAB_STYLE: Question(
        "cab",
        "Regular cab, or extended or crew cab?",
        (Choice("regular", "Regular cab", 1), Choice("extended or crew", "Extended or crew cab", 2)),
    ),
    Measures.SEAT_ROWS: Question(
        "third_row", "Does it have a third row of seats?", (Choice(True, "Yes", 3), Choice(False, "No", 2))
    ),
}


@dataclass(frozen=True)
class PhotoCard:
    vehicle_class: VehicleClass
    caption: str


@dataclass
class Classification:
    how: str
    vehicle_class: VehicleClass = None
    size_variant: object = None
    # The size question still to ask, or None.
    question: Question = None
    price_basis: str = ""
    vehicle_type: str = ""
    vehicle_model: VehicleModel = None
    rule: object = None
    override: object = None
    # The model year waits in the review queue; a class it had before still applies.
    in_review: bool = False
    review_reasons: list = field(default_factory=list)
    # Filled when the customer picks from the photo cards instead.
    photo_cards: list = field(default_factory=list)

    @property
    def needs_photo_card(self):
        return self.vehicle_class is None


def first_catalog_year():
    return read_data("vehicle-data-import.yaml")["year_from"]


def photo_cards():
    return [
        PhotoCard(vehicle_class, vehicle_class.photo_card or vehicle_class.name)
        for vehicle_class in VehicleClass.objects.filter(active=True)
    ]


def find_model(year, make, model, vehicle_type=None):
    """The catalog model of this make and name whose years hold the year,
    matched by the names in data/vehicle-names.yaml, so "GLE-Class" finds the
    GLE. A car is preferred to a motorcycle of the same name unless
    vehicle_type says. Matching a customer's vehicle to the catalog uses this too."""
    names = load_names()
    make_key = names.make_key(make)
    spellings = {found for found in VehicleModel.objects.values_list("make", flat=True).distinct() if names.make_key(found) == make_key}
    candidates = VehicleModel.objects.filter(make__in=spellings)
    if vehicle_type:
        candidates = candidates.filter(vehicle_type=vehicle_type)
    model_key = names.model_key(make, model)
    found = [
        vehicle_model
        for vehicle_model in candidates
        if names.model_key(vehicle_model.make, vehicle_model.model) == model_key
        and (vehicle_model.year_from or year) <= year <= (vehicle_model.year_to or year)
    ]
    found.sort(key=lambda vehicle_model: (vehicle_model.vehicle_type != VehicleModel.VehicleType.VEHICLE, vehicle_model.pk))
    return found[0] if found else None


def question_for(vehicle_class):
    """The size question for a class, offering only its active size variants."""
    question = QUESTIONS.get(vehicle_class.size_variant_measures)
    if question is None:
        return None
    offered = set(vehicle_class.size_variants.filter(active=True).values_list("value", flat=True))
    choices = tuple(choice for choice in question.choices if choice.size in offered)
    return Question(question.key, question.text, choices) if len(choices) > 1 else None


def answer(result, answers):
    """Settle the size from the customer's answer, if they gave one."""
    question = question_for(result.vehicle_class)
    if question is None:
        offered = list(result.vehicle_class.size_variants.filter(active=True))
        if len(offered) == 1:
            result.size_variant = offered[0]
        return
    given = (answers or {}).get(question.key)
    if given is None:
        result.question = question
        return
    choice = next((choice for choice in question.choices if choice.answer == given), None)
    if choice is None:
        raise ValueError(f"{given!r} is not an answer to {question.text!r}.")
    result.size_variant = result.vehicle_class.size_variants.get(value=choice.size)
    result.question = None


def classify(year, make, model, answers=None, *, vehicle=None, vehicle_type=None):
    """The vehicle class, the size variant or the question still to ask, the
    price basis, the vehicle type, and how the answer was reached.

    answers holds the customer's answer to the size question, by its key:
    {"doors": 4}, {"cab": "regular"} or {"third_row": True}. vehicle is a
    customer's vehicle, whose own override beats everything else.
    """
    if vehicle is not None and vehicle.class_overridden:
        result = Classification(
            How.VEHICLE_OVERRIDE,
            vehicle.vehicle_class,
            vehicle.size_variant,
            price_basis=vehicle.vehicle_class.price_basis,
            vehicle_model=vehicle.vehicle_model,
            vehicle_type=getattr(vehicle.vehicle_model, "vehicle_type", ""),
        )
        if result.size_variant is None:
            answer(result, answers)
        return result

    vehicle_model = None
    if year is not None and year >= first_catalog_year():
        vehicle_model = find_model(year, make, model, vehicle_type)
    if vehicle_model is None:
        return Classification(How.PHOTO_CARDS, photo_cards=photo_cards())

    stored = (
        ModelYearClassification.objects.filter(vehicle_model=vehicle_model, year=year)
        .select_related("vehicle_class", "size_variant", "rule", "override")
        .first()
    )
    if stored is None or stored.vehicle_class is None:
        return Classification(
            How.REVIEW_QUEUE,
            vehicle_model=vehicle_model,
            vehicle_type=vehicle_model.vehicle_type,
            in_review=True,
            review_reasons=stored.review_reasons if stored else ["not classified yet"],
            photo_cards=photo_cards(),
        )
    how = How.MODEL_OVERRIDE if stored.method == ModelYearClassification.Method.OVERRIDE else How.RULE
    result = Classification(
        how,
        stored.vehicle_class,
        stored.size_variant,
        price_basis=stored.vehicle_class.price_basis,
        vehicle_type=vehicle_model.vehicle_type,
        vehicle_model=vehicle_model,
        rule=stored.rule,
        override=stored.override,
        in_review=stored.in_review,
        review_reasons=stored.review_reasons,
    )
    if stored.ask_size:
        answer(result, answers)
    return result
