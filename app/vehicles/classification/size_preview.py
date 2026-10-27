"""The report classify_vehicles --scheme size --dry-run prints: what the
size-based classes of data/size-classes.yaml would give (decision 0082),
worked out in memory by classification.sizes. Customers appear only as
vehicle ids with year, make and model, never by name.
"""

from collections import Counter, defaultdict

from vehicles.models import ModelApproval, ModelOverride, ModelYearClassification, Vehicle, VehicleModel
from vehicles.size_report import customer_counts, ladder, size_ranges, steps, year_facts
from vehicles.vehicle_data.names import name_key, words

from .engine import Method, class_label, size_label, years_text
from .rules import FACTS
from .seed import models_named
from .sizes import median, tenth

UNCLASSIFIED = "unclassified"
SOURCES = ("measured", "inherited", "no box volume", "EPA-class fallback", UNCLASSIFIED)
CABS = ("regular", "extended", "crew")


def class_name(result):
    return result.vehicle_class.name if result is not None and result.vehicle_class is not None else UNCLASSIFIED


def source_of(model_year, result):
    """Where a model year's class comes from, for the counts."""
    if result.vehicle_class is None:
        return UNCLASSIFIED
    if result.method == Method.EPA_FALLBACK:
        return "EPA-class fallback"
    if model_year.box_volume is None:
        return "no box volume"
    return model_year.box_volume.source


def spans(entries):
    """[(year, label)] -> "2015-2019 Medium; 2020 Large", joining consecutive years."""
    joined = []
    for year, label in sorted(entries):
        if joined and joined[-1][2] == label and joined[-1][1] == year - 1:
            joined[-1][1] = year
        else:
            joined.append([year, year, label])
    return "; ".join(f"{years_text(first, last)} {label}" for first, last, label in joined)


def vehicle_name(vehicle):
    """A customer's vehicle as the report shows it: id, year, make and model only."""
    name = " ".join(str(part) for part in (vehicle.year, vehicle.make, vehicle.model) if part)
    return f"vehicle {vehicle.pk}: {name or 'no year, make or model'}"


def customers_note(count):
    return f"  * {count} customer vehicle{'s' if count != 1 else ''}" if count else ""


class Preview:
    def __init__(self, scheme, out):
        self.scheme = scheme
        self.write = lambda line="": out.write(line + "\n")
        self.by_model = defaultdict(list)
        self.models = {}
        for (model_id, year), (model_year, result) in scheme.results.items():
            self.by_model[model_id].append((year, model_year, result))
            self.models[model_id] = model_year.vehicle_model
        for found in self.by_model.values():
            found.sort(key=lambda entry: entry[0])
        self.vehicles, _, _, _ = customer_counts()
        self.stored = {
            (row.vehicle_model_id, row.year): row.vehicle_class.name if row.vehicle_class_id else "in queue"
            for row in ModelYearClassification.objects.select_related("vehicle_class")
        }

    def new_classes(self, model_id, first=None, last=None):
        entries = [
            (year, class_name(result))
            for year, _, result in self.by_model.get(model_id, [])
            if (first is None or year >= first) and (last is None or year <= last)
        ]
        return spans(entries) if entries else "no model years in the catalog"

    def model_label(self, vehicle_model):
        return f"{vehicle_model.make} {vehicle_model.model}"

    def range_volume(self, size_range):
        """The median of the range's model years' box volumes, as the rules saw them."""
        values = [
            self.scheme.results[(size_range.vehicle_model.pk, facts.year)][0].box_volume.value
            for facts in size_range.years
            if self.scheme.results[(size_range.vehicle_model.pk, facts.year)][0].box_volume is not None
        ]
        return tenth(median(values))

    def ranges(self, label, keep):
        """[SizeRange] over the model years keep(model_year, result) accepts,
        grouped as the vehicle size report groups them, with label(key) as
        each year's class, and customer vehicle counts."""
        ranges = []
        for model_id, entries in self.by_model.items():
            years = [year_facts(model_year, label((model_id, year))) for year, model_year, result in entries if keep(model_year, result)]
            for found in size_ranges(self.models[model_id], years):
                found.vehicles = sum(self.vehicles.get((model_id, facts.year), 0) for facts in found.years)
                ranges.append(found)
        return ranges

    # The sections, in order.

    def run(self):
        self.write("DRY RUN (size-based classes, data/size-classes.yaml): nothing was changed.")
        self.write("Model overrides, review queue decisions and approvals are not carried into the size-based classes.")
        self.write("Lines: " + ", ".join(f"{line['above']} from {line['at']} cu ft" for line in self.scheme.lines) + f"; below {self.scheme.lines[0]['at']}: {self.scheme.lines[0]['below']}")
        self.counts()
        self.fallback()
        self.near_lines()
        self.mixed()
        self.overrides_and_approvals()
        self.customer_vehicles()
        self.old_light_pickups()
        self.pickups()

    def counts(self):
        results = self.scheme.results.values()
        by_class = defaultdict(Counter)
        for model_year, result in results:
            by_class[class_name(result)][source_of(model_year, result)] += 1
        order = {name: index for index, name in enumerate(entry["name"] for entry in self.scheme.data["classes"])}
        self.write(f"\nModel years by new class and source of the class ({len(self.scheme.results):,} model years)")
        self.write("  class: total (measured / inherited / no box volume / EPA-class fallback)")
        for name in sorted(by_class, key=lambda name: (order.get(name, len(order)), name)):
            counts = by_class[name]
            if name == UNCLASSIFIED:
                continue
            parts = " / ".join(f"{counts.get(source, 0):,}" for source in SOURCES[:-1])
            self.write(f"  {name}: {sum(counts.values()):,} ({parts})")
        self.write(f"  unclassified, waiting in the review queue: {sum(by_class[UNCLASSIFIED].values()):,}")
        asks = sum(1 for _, result in results if result.ask_size)
        self.write(f"  the booking form asks the size: {asks:,}")

    def fallback(self):
        used = Counter()
        from .sizes import main_epa_class

        for model_year, result in self.scheme.results.values():
            if result.method == Method.EPA_FALLBACK:
                used[main_epa_class(model_year)] += 1
        self.write("\nEPA size class fallback: where most measured model years of each EPA size class land")
        self.write("  (used for a model with no measurements in any year)")
        for epa in sorted(self.scheme.fallback_counts):
            counts = self.scheme.fallback_counts[epa]
            detail = ", ".join(f"{name} {count:,}" for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])))
            self.write(f"  {epa}: {self.scheme.fallback_table[epa]} ({detail}); used for {used.get(epa, 0):,} model years")

    def size_lines(self):
        size_classes = self.scheme.size_classes
        keep = lambda model_year, result: class_name(result) in size_classes and result.method != Method.EPA_FALLBACK  # noqa: E731
        label = lambda key: class_name(self.scheme.results[key][1])  # noqa: E731
        return ladder(self.ranges(label, keep), self.scheme.data["newest_from"])

    def near_lines(self):
        near = self.scheme.data["near_line"]
        found = []
        for size_range in self.size_lines():
            volume = self.range_volume(size_range)
            for line in self.scheme.lines:
                distance = volume - line["at"]
                if abs(distance) <= near:
                    found.append((line["at"], volume, size_range, line, distance))
        self.write(f"\nNear a line: models within {near} cu ft of a line ({len(found):,})")
        self.write(f"  (each model's newest size range from {self.scheme.data['newest_from']} on, plus any range a customer owns)")
        for at, volume, size_range, line, distance in sorted(found, key=lambda item: (item[0], item[1], item[2].name)):
            side = "over" if distance >= 0 else "under"
            self.write(
                f"  {size_range.name}: {volume} cu ft, {abs(distance)} {side} the {at} line ({line['below']} | {line['above']});"
                f" gets {size_range.vehicle_class}{customers_note(size_range.vehicles)}"
            )

    def mixed(self):
        found = []
        for model_id, entries in self.by_model.items():
            classified = [(year, class_name(result)) for year, _, result in entries if result.vehicle_class is not None]
            if len({name for _, name in classified}) > 1:
                found.append(f"{self.model_label(self.models[model_id])}: {spans(classified)}")
        self.write(f"\nModels whose class changes between model years ({len(found):,})")
        for line in sorted(found):
            self.write(f"  {line}")

    def overrides_and_approvals(self):
        overrides = ModelOverride.objects.select_related("vehicle_model", "vehicle_class").order_by("vehicle_model__make", "vehicle_model__model", "year_from")
        self.write(f"\nModel overrides, not carried forward ({overrides.count():,}), with what the new rules give instead")
        for override in overrides:
            years = f" {override.year_from or ''}-{override.year_to or ''}" if override.year_from or override.year_to else ""
            note = f" ({override.note})" if override.note else ""
            self.write(
                f"  {self.model_label(override.vehicle_model)}{years}: {override.vehicle_class}{note}"
                f" -> {self.new_classes(override.vehicle_model_id, override.year_from, override.year_to)}"
            )
        approvals = ModelApproval.objects.filter(cleared_at=None).select_related("vehicle_model", "vehicle_class").order_by(
            "vehicle_model__make", "vehicle_model__model", "year_from"
        )
        self.write(f"\nApprovals, not carried forward ({approvals.count():,}), with what the new rules give instead")
        for approval in approvals:
            self.write(
                f"  {self.model_label(approval.vehicle_model)} {years_text(approval.year_from, approval.year_to)}:"
                f" approved as {class_label(approval.vehicle_class, approval.size)}"
                f" -> {self.new_classes(approval.vehicle_model_id, approval.year_from, approval.year_to)}"
            )

    def proposed_for_unlinked(self, vehicle):
        """(proposed class, reason) for a vehicle not linked to the catalog."""
        if vehicle.vehicle_class is None:
            return UNCLASSIFIED, "not linked and no recorded class: needs a year, make and model"
        data = self.scheme.data
        proposed = data["unlinked_vehicles"].get(vehicle.vehicle_class.name)
        if proposed is None:
            return UNCLASSIFIED, "not linked, and its recorded class has no proposed class: for review"
        if vehicle.vehicle_class.name == "Fullsize SUVs & Minivans" and is_minivan(vehicle.model, data["minivan_models"]):
            return data["minivan_class"], "not linked; a minivan, proposed from its recorded class: for review"
        return proposed, "not linked; proposed from its recorded class: for review"

    def new_for(self, vehicle):
        """(new class, reason) for one customer's vehicle."""
        if vehicle.vehicle_model_id is None:
            return self.proposed_for_unlinked(vehicle)
        if vehicle.year is None:
            names = {class_name(result) for _, _, result in self.by_model.get(vehicle.vehicle_model_id, [])}
            if len(names) == 1 and UNCLASSIFIED not in names:
                return next(iter(names)), "no year; every model year of its model is in this class"
            return "year needed", "no year; its model's years span " + ", ".join(sorted(names) or ["no model years"])
        found = self.scheme.results.get((vehicle.vehicle_model_id, vehicle.year))
        if found is None:
            return UNCLASSIFIED, f"the catalog has no {vehicle.year} for its model"
        _, result = found
        if result.vehicle_class is None:
            return UNCLASSIFIED, result.because
        return class_label(result.vehicle_class, size_label(result.size_variant, result.ask_size, result.vehicle_class)), result.because

    def customer_vehicles(self):
        vehicles = list(Vehicle.objects.select_related("vehicle_class", "size_variant").order_by("pk"))
        lines, moves = [], Counter()
        for vehicle in vehicles:
            recorded = class_label(vehicle.vehicle_class, vehicle.size_variant.label if vehicle.size_variant else "") if vehicle.vehicle_class else "no class"
            new, reason = self.new_for(vehicle)
            moves[(str(vehicle.vehicle_class) if vehicle.vehicle_class else "no class", new.split(" (")[0])] += 1
            lines.append(f"  {vehicle_name(vehicle)} | {recorded} -> {new} | {reason}")
        self.write(f"\nCustomer vehicles ({len(vehicles):,}): recorded class -> new class")
        for (old, new), count in sorted(moves.items()):
            self.write(f"  {old} -> {new}: {count:,}")
        self.write("\nCustomer vehicles one by one: recorded class -> new class | reason")
        for line in lines:
            self.write(line)

    def old_light_pickups(self):
        old = next((entry["renamed_from"] for entry in self.scheme.data["classes"] if entry.get("renamed_from")), None)
        pickups = self.scheme.pickup_classes
        years = defaultdict(list)
        for (model_id, year), name in self.stored.items():
            if name == old:
                years[model_id].append(year)
        found = []
        for model_id, model_years in years.items():
            entries = [(year, class_name(self.scheme.results[(model_id, year)][1])) for year in model_years if (model_id, year) in self.scheme.results]
            if any(name not in pickups for _, name in entries):
                found.append(f"{self.model_label(VehicleModel.objects.get(pk=model_id))}: {spans(entries)}")
        self.write(f"\nModels now in {old} that the new rules do not treat as pickups ({len(found):,})")
        for line in sorted(found):
            self.write(f"  {line}")

    def pickups(self):
        pickups = self.scheme.pickup_classes
        keep = lambda model_year, result: class_name(result) in pickups  # noqa: E731
        label = lambda key: self.stored.get(key, "no class")  # noqa: E731
        lines = sorted(
            ladder(self.ranges(label, keep), self.scheme.data["newest_from"]),
            key=lambda found: (self.range_volume(found), found.name),
        )
        self.write(f"\nPickup ladder, for placing a pickup size line later; the pickup rules are unchanged ({len(lines):,} lines)")
        self.write("  box volume, length, model and years, cab styles, EPA size class, GVWR range, current class")
        for found in lines:
            self.write(
                f"  {self.range_volume(found):>6} cu ft  {found.measure('length'):>6} in  {found.name}  cabs: {self.cabs(found)}"
                f"  EPA: {found.epa_main or 'none'}  GVWR: {self.gvwr(found)}  now {found.vehicle_class}{customers_note(found.vehicles)}"
            )
        for title, key, unit in (
            ("Largest steps in box volume", self.range_volume, "cu ft"),
            ("Largest steps in length", lambda found: found.measure("length"), "in"),
        ):
            self.write(f"\n{title} on the pickup ladder:")
            for step, lower, upper in steps(lines, key):
                self.write(f"  +{step} {unit}: {lower.name} ({key(lower)} {unit}) | {upper.name} ({key(upper)} {unit})")
        self.write("\nPickup check: models that must be pickups")
        for entry in self.scheme.data["pickup_checks"]:
            found = models_named(entry["make"], entry["model"])
            if not found:
                self.write(f"  {entry['make']} {entry['model']}: not in the catalog")
            for vehicle_model in found:
                entries = [(year, class_name(result)) for year, _, result in self.by_model.get(vehicle_model.pk, [])]
                verdict = "pickup in every model year" if entries and all(name in pickups for _, name in entries) else "NOT A PICKUP IN EVERY MODEL YEAR"
                self.write(f"  {self.model_label(vehicle_model)}: {verdict}: {spans(entries) or 'no model years'}")

    def cabs(self, size_range):
        found = set()
        for facts in size_range.years:
            found |= self.scheme.results[(size_range.vehicle_model.pk, facts.year)][0].values("cab_style")
        return ", ".join(cab for cab in CABS if cab in found) or "unknown"

    def gvwr(self, size_range):
        lows, highs = [], []
        for facts in size_range.years:
            model_year = self.scheme.results[(size_range.vehicle_model.pk, facts.year)][0]
            for row in model_year.measured(FACTS["gvwr"]).values():
                lows.append(row.gvwr_min)
                highs.append(row.gvwr_max)
        return f"{min(lows):,}-{max(highs):,} lb" if lows else "none"


def is_minivan(model, names):
    """Whether a model name is or begins with one of the minivan names, in whole words."""
    found = words(model or "")
    starts = {"".join(found[:count]) for count in range(1, len(found) + 1)}
    return any(name_key(name) in starts for name in names)


def write_report(scheme, out):
    Preview(scheme, out).run()
