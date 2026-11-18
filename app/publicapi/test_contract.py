"""The public API's answers match data/public-api-shapes.yaml, the contract
the website's fake API (site/tests/fake/api.mjs) is checked against too
(site/tests/unit/contract.test.mjs), so the fake the browser tests run on
can't drift from the real API. The fake once added a `place` field to its
quotes that the real API never sent, and the booking flow came to rely on
it: every browser test passed while the real location step never unlocked.

Shapes, in the file:
- "string", "number", "boolean", "null", or a union such as "string|null";
- a one-item list, for a list whose every item has that shape;
- a mapping, for an object with exactly those keys. A key ending in "?"
  may be left out, and "$or_null: true" lets the whole object be null;
- a mapping of "$items" (the item shape) and "$or_null: true", for a list
  that may be null.

This test works the shape out from the real answers below and requires it
to equal the file's. After a deliberate change to an answer, run
tools/run-tests.sh -s publicapi/test_contract.py: a mismatch prints the
shapes as they are now. Put them in the file, and update the fake to match.
"""

import yaml
from django.conf import settings
from django.test import SimpleTestCase

from vehicles.models import VehicleClass

from .testing import BASE, CLEVELAND, GOOD_TOKEN, KNOXVILLE, ApiTestCase, jpeg
from .test_quote_requests import upload_file

SHAPES_FILE = settings.DATA_DIR / "public-api-shapes.yaml"
NUMBER = "number"


def shape_of(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return NUMBER
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        item = None
        for element in value:
            item = shape_of(element) if item is None else merge(item, shape_of(element))
        return [item if item is not None else "any"]
    if isinstance(value, dict):
        return {key: shape_of(element) for key, element in value.items()}
    raise TypeError(f"Not JSON: {value!r}")


def _nullable_list(shape):
    """A list shape's item shape and whether it may be null, or None."""
    if isinstance(shape, list):
        return shape[0], False
    if isinstance(shape, dict) and "$items" in shape:
        return shape["$items"], True
    return None


def _split(shape):
    """An object shape's keys as {name: (shape, optional)}, and its $or_null."""
    keys = {}
    for key, element in shape.items():
        if key == "$or_null":
            continue
        keys[key.rstrip("?")] = (element, key.endswith("?"))
    return keys, bool(shape.get("$or_null"))


def _join(keys, or_null):
    shape = {(name + "?" if optional else name): element for name, (element, optional) in sorted(keys.items())}
    if or_null:
        shape["$or_null"] = True
    return shape


def merge(a, b):
    """One shape covering both a and b."""
    if a == b:
        return a
    if a == "any":
        return b
    if b == "any":
        return a
    la, lb = _nullable_list(a), _nullable_list(b)
    if la and (lb or b == "null"):
        item = merge(la[0], lb[0]) if lb else la[0]
        return {"$items": item, "$or_null": True} if la[1] or b == "null" or lb[1] else [item]
    if lb and a == "null":
        return merge(b, a)
    if isinstance(a, dict) and b == "null":
        keys, _ = _split(a)
        return _join(keys, True)
    if a == "null" and isinstance(b, dict):
        return merge(b, a)
    if isinstance(a, dict) and isinstance(b, dict):
        (ka, na), (kb, nb) = _split(a), _split(b)
        keys = {}
        for name in ka.keys() | kb.keys():
            if name in ka and name in kb:
                keys[name] = (merge(ka[name][0], kb[name][0]), ka[name][1] or kb[name][1])
            else:
                keys[name] = ((ka.get(name) or kb.get(name))[0], True)
        return _join(keys, na or nb)
    if isinstance(a, str) and isinstance(b, str):
        return "|".join(sorted(set(a.split("|")) | set(b.split("|"))))
    raise ValueError(f"Can't describe {a!r} and {b!r} as one shape")


def normalize(shape):
    """A shape as read from the file, in the form merge() makes."""
    if isinstance(shape, dict) and "$items" in shape:
        return {"$items": normalize(shape["$items"]), "$or_null": True}
    if isinstance(shape, dict):
        keys, or_null = _split(shape)
        return _join({name: (normalize(element), optional) for name, (element, optional) in keys.items()}, or_null)
    if isinstance(shape, list):
        return [normalize(shape[0])]
    return "|".join(sorted(shape.split("|")))


class ContractTests(ApiTestCase):
    def answers(self):
        """Real answers, by the name the shapes file uses, covering each
        kind of answer the website reads."""
        client = self.client
        found = {}
        # One class with its photo card picture and the rest without, as on
        # the server until every picture is set.
        VehicleClass.objects.filter(pk=self.small.pk).update(photo="/images/vehicle-classes/vehicle-class-small.webp")

        def keep(name, response, status):
            self.assertEqual(response.status_code, status, response.content)
            found.setdefault(name, []).append(response.json())

        keep("services", client.get_api("services"), 200)
        keep("booking-options", client.get_api("booking-options"), 200)
        keep("price-table", client.get_api("price-table"), 200)
        keep("vehicles/years", client.get_api("vehicles/years"), 200)
        keep("vehicles/makes", client.get_api("vehicles/makes", {"year": 2019}), 200)
        keep("vehicles/models", client.get_api("vehicles/models", {"year": 2019, "make": "Toyota"}), 200)
        keep("vehicles/models", client.get_api("vehicles/models", {"year": 2020, "make": "Honda"}), 200)
        for params in (
            {"year": 2019, "make": "Toyota", "model": "RAV4"},
            {"year": 2019, "make": "Toyota", "model": "Highlander"},
            {"year": 2019, "make": "Toyota", "model": "Highlander", "size": 3},
            {"year": 2020, "make": "Honda", "model": "Gold Wing", "type": "motorcycle"},
            {"year": 2021, "make": "Ford", "model": "Transit 250"},
            {"year": 1969, "make": "Chevrolet", "model": "Camaro"},
        ):
            keep("vehicles/lookup", client.get_api("vehicles/lookup", params), 200)
        keep("vehicles/photo-cards", client.get_api("vehicles/photo-cards"), 200)

        place = client.post_json("addresses", {"place_id": CLEVELAND, "session_token": "session-token-1"})
        keep("addresses", place, 201)
        token = place.json()["place"]
        keep("error", client.post_json("addresses", {"place_id": KNOXVILLE}), 422)

        rav4 = {"year": 2019, "make": "Toyota", "model": "RAV4"}
        keep("quotes", client.post_json("quotes", {"vehicle": rav4, "service": self.full_detail.pk, "condition": 1, "add_ons": [self.seats.pk]}), 201)
        keep("quotes", client.post_json("quotes", {"vehicle": {"photo_card": self.small.pk}, "service": self.exterior.pk, "size": 2}), 201)
        gold_wing = {"year": 2020, "make": "Honda", "model": "Gold Wing", "type": "motorcycle"}
        keep("quotes", client.post_json("quotes", {"vehicle": gold_wing, "service": self.motorcycle_detail.pk}), 201)
        with_place = client.post_json("quotes", {"vehicle": rav4, "service": self.full_detail.pk, "condition": 2, "add_ons": [self.seats.pk], "place": token})
        keep("quotes", with_place, 201)
        quote = with_place.json()
        keep("error", client.post_json("quotes", {"vehicle": rav4}), 400)

        keep("open-times", client.get_api("open-times", {"quote": quote["number"], "days": 31}), 200)
        start = self.first_open(quote)
        keep("bookings", client.post_json("bookings", self.booking_body(quote, start)), 201)

        session = client.post_json("quote-requests/uploads", {"turnstile": GOOD_TOKEN})
        keep("quote-requests/uploads", session, 201)
        session_id = session.json()["session"]
        photo = client.post(f"{BASE}quote-requests/uploads/{session_id}/photos", {"photo": upload_file(jpeg())})
        keep("quote-requests/uploads/photos", photo, 201)
        request = {
            "vehicle": {"year": 2021, "make": "Ford", "model": "Transit 250"}, "service": "not_sure",
            "description": "Work van.", "place": token, "first_name": "Morgan", "mobile": "423-555-0160",
            "consents": {"version": "2026-10-13", "appointment": True, "follow_up": False}, "turnstile": GOOD_TOKEN,
        }
        keep("quote-requests", client.post_json("quote-requests", {**request, "session": session_id, "photos": [photo.json()["photo"]]}), 201)
        keep("error", client.post_json("quote-requests", {**request, "turnstile": "refused"}), 403)
        return found

    def test_the_real_answers_have_the_contracts_shapes(self):
        shapes = {}
        for name, answers in self.answers().items():
            shape = None
            for answer in answers:
                shape = shape_of(answer) if shape is None else merge(shape, shape_of(answer))
            shapes[name] = shape
        written = yaml.safe_load(SHAPES_FILE.read_text())["answers"] or {}
        if {name: normalize(shape) for name, shape in written.items()} != shapes:
            # The shapes as they are now, to paste over the file's after a
            # deliberate change (then update the fake to match).
            print(yaml.safe_dump({"answers": shapes}, sort_keys=True, width=200))
        self.assertEqual(sorted(written), sorted(shapes), "The endpoints in public-api-shapes.yaml")
        for name, shape in shapes.items():
            with self.subTest(name):
                self.assertEqual(normalize(written[name]), shape)


class ShapeTests(SimpleTestCase):
    def test_merge_makes_keys_optional_and_objects_nullable(self):
        self.assertEqual(merge(shape_of({"a": 1, "b": "x"}), shape_of({"a": 2})), {"a": "number", "b?": "string"})
        self.assertEqual(merge(shape_of({"a": 1}), "null"), {"a": "number", "$or_null": True})
        self.assertEqual(merge("string", "null"), "null|string")
        self.assertEqual(shape_of([1, None]), ["null|number"])
        self.assertEqual(shape_of([]), ["any"])
