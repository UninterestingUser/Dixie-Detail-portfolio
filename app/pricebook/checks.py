"""The price book check (decision 0083), run by load_pricebook on
data/price-matrix.csv, by apply_size_classes on the draft it publishes, and
by the tests. It refuses a price book where:

- a maintenance plan is not its percentage of Full Detail for the same class
  and size (Monthly 50% and Quarterly 80%, from data/pricing-rules.yaml), or
  its service hours are not Full Detail's, or Full Detail has a price with
  no maintenance plan price beside it;
- a class and size the rules can give has no base price: Full Detail, or for
  a class with a service of its own (Motorcycles) that service. Every size
  variant data/vehicle-classes.yaml lists for an online class counts, and so
  does every class and size the classified catalog gives, when one is passed
  in (classification.sizes.produced). A class booked by quote needs none.

A cell is a dict like a row of data/price-matrix.csv: service,
vehicle_class, size_variant (a value or None), hours and price.
"""

from collections import defaultdict

from vehicles.classification.seed import read_data

from .models import DerivedPriceRule, Price
from .pricing import base_price, to_cents

MAINTENANCE_PERCENT_KEYS = {
    "Quarterly Maintenance": "quarterly_percent_of_full_detail",
    "Monthly Maintenance": "monthly_percent_of_full_detail",
}
QUOTE = "ask for a quote"
SHOWN = 5


def cell_name(cell):
    size = f" size {cell['size_variant']}" if cell["size_variant"] is not None else ""
    return f"{cell['service']} / {cell['vehicle_class']}{size}"


def version_cells(version):
    """The cells of a pricebook version, its maintenance plans worked out from
    their rules, each class by its name in data/vehicle-classes.yaml (a class
    apply_size_classes has yet to rename by its new name)."""
    from vehicles.classification.switch import renames

    named = renames()
    cells = [
        {
            "service": price.service.name,
            "vehicle_class": named.get(price.vehicle_class.name, price.vehicle_class.name),
            "size_variant": price.size_variant.value if price.size_variant else None,
            "hours": price.one_person_service_hours,
            "price": price.price,
        }
        for price in Price.objects.filter(version=version).select_related("service", "vehicle_class", "size_variant")
    ]
    for rule in DerivedPriceRule.objects.filter(version=version).select_related("service", "base_service"):
        for price in Price.objects.filter(version=version, service=rule.base_service).select_related("vehicle_class", "size_variant"):
            found = base_price(version, rule.service, price.vehicle_class, price.size_variant)
            cells.append(
                {
                    "service": rule.service.name,
                    "vehicle_class": named.get(price.vehicle_class.name, price.vehicle_class.name),
                    "size_variant": price.size_variant.value if price.size_variant else None,
                    "hours": found.one_person_service_hours,
                    "price": found.price,
                }
            )
    return cells


def own_services(data_dir=None):
    """{class name: service name} for a class with a service of its own, such as Motorcycles."""
    found = {}
    for entry in read_data("services.yaml", data_dir)["services"]:
        for name in entry.get("offered_for") or []:
            found[name] = entry["name"]
    return found


def check(cells, produced=None, data_dir=None):
    """What is wrong with a price book, as a list of sentences; empty when it passes."""
    rules = read_data("pricing-rules.yaml", data_dir)["maintenance_plans"]
    classes = read_data("vehicle-classes.yaml", data_dir)["classes"]
    base_service = rules["base_service"]
    own = own_services(data_dir)
    by_cell = {(cell["service"], cell["vehicle_class"], cell["size_variant"]): cell for cell in cells}
    problems = []

    # The maintenance plans follow Full Detail.
    for service, key in MAINTENANCE_PERCENT_KEYS.items():
        percent = rules[key]
        for cell in cells:
            if cell["service"] == base_service and (service, cell["vehicle_class"], cell["size_variant"]) not in by_cell:
                problems.append(f"{cell_name({**cell, 'service': service})} is missing: {base_service} has a price there.")
            if cell["service"] != service:
                continue
            base = by_cell.get((base_service, cell["vehicle_class"], cell["size_variant"]))
            if base is None:
                problems.append(f"{cell_name(cell)} has no {base_service} price to follow.")
                continue
            expected = to_cents(base["price"] * percent / 100)
            if cell["price"] != expected:
                problems.append(f"{cell_name(cell)} is ${cell['price']}; {percent}% of {base_service} is ${expected}.")
            if cell["hours"] != base["hours"]:
                problems.append(f"{cell_name(cell)} is {cell['hours']:g} hours; {base_service} is {base['hours']:g}.")

    # Every class and size the rules can give has a base price.
    needed = defaultdict(list)
    quoted = {entry["name"] for entry in classes if entry.get("booking") == QUOTE}
    for entry in classes:
        if entry["name"] in quoted:
            continue
        sizes = [int(value) for value in (entry.get("size_variants") or {})] or [None]
        for size in sizes:
            needed[(entry["name"], size)].append("data/vehicle-classes.yaml")
    for key, names in (produced or {}).items():
        if key[0] not in quoted:
            needed[key].extend(names)
    priced = {(cell["service"], cell["vehicle_class"], cell["size_variant"]) for cell in cells}
    for (class_name, size), sources in sorted(needed.items(), key=lambda item: (item[0][0], item[0][1] or 0)):
        service = own.get(class_name, base_service)
        if (service, class_name, size) in priced:
            continue
        if size is None and any(found[:2] == (service, class_name) for found in priced):
            continue
        rows = f" size {size}" if size is not None else ""
        shown = ", ".join(sources[:SHOWN]) + (f" and {len(sources) - SHOWN:,} more" if len(sources) > SHOWN else "")
        problems.append(f"{class_name}{rows} has no {service} price, but the rules can give it: {shown}.")
    return problems
