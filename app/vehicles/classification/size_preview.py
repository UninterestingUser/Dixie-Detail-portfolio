"""The report apply_size_classes prints (decision 0083): what the
size-based classes give, model year by model year, with the switch itself
(the classes renamed, offered and retired, the records archived, the rules
created), each customer's vehicle, the price book check and the booked
jobs. A dry run prints the same report. Customers and booked jobs appear
only as ids with year, make and model, never by name.
"""

from collections import Counter, defaultdict

from vehicles.models import ModelOverride, VehicleModel
from vehicles.size_report import customer_counts, ladder, size_ranges, steps, year_facts

from .engine import Method, class_label, years_text
from .rules import FACTS
from .seed import models_named, read_data
from .sizes import median, tenth
from .switch import renames, vehicle_name

UNCLASSIFIED = "unclassified"
SOURCES = ("measured", "inherited", "no box volume", "EPA-class fallback", "model override", "smoothed", UNCLASSIFIED)
CABS = ("regular", "extended", "crew")


def class_name(result):
    return result.vehicle_class.name if result is not None and result.vehicle_class is not None else UNCLASSIFIED


def source_of(model_year, result):
    """Where a model year's class comes from, for the counts."""
    if result.vehicle_class is None:
        return UNCLASSIFIED
    if result.method == Method.EPA_FALLBACK:
        return "EPA-class fallback"
    if result.method == Method.OVERRIDE:
        return "model override"
    if result.method == Method.SMOOTHED:
        return "smoothed"
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


def smoothed_runs(results):
    """["Make Model 2019-2020: Medium, smoothed from Large"] for each run of
    smoothed model years, joined by model and years."""
    from .engine import year_spans

    rows = []
    for model_year, result in results.values():
        if result.method == Method.SMOOTHED:
            old = result.reasons[0].rsplit(" gives ", 1)[-1] if result.reasons else "another class"
            rows.append((model_year.vehicle_model, model_year.year, f"{result.vehicle_class}, smoothed from {old}"))
    return [f"{model.make} {model.model} {years_text(first, last)}: {detail}" for model, first, last, detail in year_spans(rows)]


def customers_note(count):
    return f"  * {count} customer vehicle{'s' if count != 1 else ''}" if count else ""


class Preview:
    def __init__(self, outcome, out, dry_run):
        self.outcome = outcome
        self.scheme = outcome.scheme
        self.dry_run = dry_run
        self.write = lambda line="": out.write(line + "\n")
        self.by_model = defaultdict(list)
        self.models = {}
        for (model_id, year), (model_year, result) in self.scheme.results.items():
            self.by_model[model_id].append((year, model_year, result))
            self.models[model_id] = model_year.vehicle_model
        for found in self.by_model.values():
            found.sort(key=lambda entry: entry[0])
        self.vehicles, _, _, _ = customer_counts()
        self.stored = outcome.before.stored

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
        outcome = self.outcome
        if self.dry_run:
            self.write("DRY RUN (apply_size_classes): nothing was changed. Without --dry-run, on the effective date, it applies all of this in one step.")
        else:
            self.write("APPLIED: the size-based classes and the new price book are live.")
        if outcome.problems:
            self.write(f"REFUSED: the draft price book fails the check in {len(outcome.problems):,} place(s); see the price book check below.")
        self.write(f"Price book: draft version {outcome.version.number}, effective {outcome.effective:%Y-%m-%d}.")
        self.write("Lines: " + ", ".join(f"{line['above']} from {line['at']} cu ft" for line in self.scheme.lines) + f"; below {self.scheme.lines[0]['at']}: {self.scheme.lines[0]['below']}")
        line = self.scheme.pickup_line
        self.write(f"Pickup line: {line['above']} from {line['at']} cu ft; below it {line['below']}; a pickup with no box volume keeps its EPA label's class.")
        self.switch()
        self.price_check()
        self.counts()
        self.fallback()
        self.near_lines()
        self.smoothed()
        self.mixed()
        self.overrides_and_approvals()
        self.customer_vehicles()
        self.booked_jobs()
        self.old_light_pickups()
        self.pickups()

    def switch(self):
        outcome = self.outcome
        self.write("\nThe switch")
        for line in outcome.classes:
            self.write(f"  {line}")
        for name, count in outcome.archived.items():
            self.write(f"  {name} archived: {count:,}")
        self.write(f"  launch rules and overrides created from data/size-classes.yaml: {len(outcome.seeded.launch_set):,}")
        for line in outcome.seeded.launch_set:
            self.write(f"    {line}")
        for line in outcome.seeded.unmatched_overrides:
            self.write(f"    Override not applied: {line}")
        for name, count in outcome.counts.items():
            self.write(f"  {name}: {count:,}")

    def price_check(self):
        problems = self.outcome.problems
        self.write(f"\nPrice book check: {'passed' if not problems else f'{len(problems):,} problem(s)'}")
        for problem in problems:
            self.write(f"  {problem}")

    def counts(self):
        results = self.scheme.results.values()
        by_class = defaultdict(Counter)
        for model_year, result in results:
            by_class[class_name(result)][source_of(model_year, result)] += 1
        order = {name: index for index, name in enumerate(entry["name"] for entry in read_data("vehicle-classes.yaml")["classes"])}
        self.write(f"\nModel years by new class and source of the class ({len(self.scheme.results):,} model years)")
        self.write(f"  class: total ({' / '.join(SOURCES[:-1])})")
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

    def pickup_lines(self):
        pickups = self.scheme.pickup_classes
        keep = lambda model_year, result: class_name(result) in pickups  # noqa: E731
        label = lambda key: class_name(self.scheme.results[key][1])  # noqa: E731
        return ladder(self.ranges(label, keep), self.scheme.data["newest_from"])

    def near_lines(self):
        near = self.scheme.data["near_line"]
        found = []
        for size_range, lines in [(found, self.scheme.lines) for found in self.size_lines()] + [
            (found, [self.scheme.pickup_line]) for found in self.pickup_lines()
        ]:
            volume = self.range_volume(size_range)
            if volume is None:
                continue
            for line in lines:
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

    def smoothed(self):
        runs = smoothed_runs(self.scheme.results)
        limit = self.scheme.data["smoothing"]["max_years"]
        self.write(f"\nSmoothed: runs of up to {limit} model years between two runs of one class, given that class ({len(runs):,})")
        for line in runs:
            self.write(f"  {line}")

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
        before = self.outcome.before
        overrides = ModelOverride.objects.select_related("vehicle_model", "vehicle_class").order_by("vehicle_model__make", "vehicle_model__model", "year_from")
        self.write(f"\nModel overrides now ({overrides.count():,}), from data/size-classes.yaml")
        for override in overrides:
            years = f" {override.year_from or ''}-{override.year_to or ''}" if override.year_from or override.year_to else ""
            self.write(f"  {self.model_label(override.vehicle_model)}{years}: {override.vehicle_class}")
        self.write(f"\nModel overrides archived ({len(before.overrides):,}), with what the new rules give instead")
        for override in before.overrides:
            years = f" {override.year_from or ''}-{override.year_to or ''}" if override.year_from or override.year_to else ""
            note = f" ({override.note})" if override.note else ""
            self.write(
                f"  {self.model_label(override.vehicle_model)}{years}: {override.vehicle_class}{note}"
                f" -> {self.new_classes(override.vehicle_model_id, override.year_from, override.year_to)}"
            )
        self.write(f"\nReview queue decisions archived ({len(before.decisions):,}), with what the new rules give instead")
        for decision in sorted(before.decisions, key=lambda found: (found.vehicle_model.make, found.vehicle_model.model, found.year)):
            self.write(
                f"  {decision.year} {self.model_label(decision.vehicle_model)}: {decision.vehicle_class or 'photo cards'}"
                f" -> {self.new_classes(decision.vehicle_model_id, decision.year, decision.year)}"
            )
        self.write(f"\nApprovals archived; the approval list starts over ({len(before.approvals):,})")
        for approval in before.approvals:
            self.write(
                f"  {self.model_label(approval.vehicle_model)} {years_text(approval.year_from, approval.year_to)}:"
                f" approved as {class_label(approval.vehicle_class, approval.size)}"
                f" -> {self.new_classes(approval.vehicle_model_id, approval.year_from, approval.year_to)}"
            )

    def customer_vehicles(self):
        changes = self.outcome.vehicles
        moves = Counter()
        for change in changes:
            moves[(change.before.split(" (")[0], change.after.split(" (")[0])] += 1
        self.write(f"\nCustomer vehicles ({len(changes):,} changed or left for the owner): recorded class -> new class")
        for (old, new), count in sorted(moves.items()):
            self.write(f"  {old} -> {new}: {count:,}")
        confirm = sum(1 for change in changes if change.vehicle.confirm_year and change.kind == "set")
        proposed = sum(1 for change in changes if change.kind == "proposed")
        self.write(f"  no year, given the newest generation's class and flagged to confirm the year: {confirm:,}")
        self.write(f"  left in a retired class, with a proposed class on the differences screen: {proposed:,}")
        self.write("\nCustomer vehicles one by one: recorded class -> new class | reason")
        for change in changes:
            self.write(f"  {vehicle_name(change.vehicle)} | {change.before} -> {change.after} | {change.reason}")

    def booked_jobs(self):
        jobs = [job for job in self.outcome.jobs if not job.check_by_hand]
        by_hand = [job for job in self.outcome.jobs if job.check_by_hand]
        self.write(f"\nBooked jobs to check by hand: booked in a retired class, with no vehicle or a vehicle with no class or size ({len(by_hand):,})")
        self.write("  Not re-priced: each keeps its quoted price. Give the vehicle its class and size, then decide it on the version's booked-job review.")
        for job in by_hand:
            self.write(f"  {job.describe()} | quoted ${job.booked_total} | {'; '.join(job.reasons)}")
        self.write(f"\nBooked jobs from {self.outcome.effective:%Y-%m-%d} on that the new price book prices differently ({len(jobs):,})")
        self.write("  Each keeps its quoted price, the price of record; decide each on the version's booked-job review.")
        for job in jobs:
            new = f"${job.new_total}" if job.new_total is not None else "cannot be priced"
            in_class = f" in {class_label(job.new_class, job.new_size.label if job.new_size else '')}" if job.new_class else ""
            self.write(f"  {job.describe()} | quoted ${job.booked_total} | new book {new}{in_class} | {'; '.join(job.reasons)}")

    def old_light_pickups(self):
        old = next((old for old, new in renames().items() if new == self.scheme.pickup_line["below"]), None)
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
        label = lambda key: class_name(self.scheme.results[key][1])  # noqa: E731
        lines = sorted(
            ladder(self.ranges(label, keep), self.scheme.data["newest_from"]),
            key=lambda found: (self.range_volume(found) or 0, found.name),
        )
        self.write(f"\nPickup ladder, with the {self.scheme.pickup_line['at']} cu ft pickup line ({len(lines):,} lines)")
        self.write("  box volume, length, model and years, cab styles, EPA size class, GVWR range, class before -> class now")
        marked = False
        for found in lines:
            volume = self.range_volume(found)
            if not marked and volume is not None and volume >= self.scheme.pickup_line["at"]:
                self.write(f"  ---- {self.scheme.pickup_line['at']} cu ft: {self.scheme.pickup_line['above']} from here ----")
                marked = True
            self.write(
                f"  {str(volume or 'none'):>6} cu ft  {str(found.measure('length') or 'none'):>6} in  {found.name}  cabs: {self.cabs(found)}"
                f"  EPA: {found.epa_main or 'none'}  GVWR: {self.gvwr(found)}  {self.before_class(found)} -> {found.vehicle_class}{customers_note(found.vehicles)}"
            )
        for title, key, unit in (
            ("Largest steps in box volume", self.range_volume, "cu ft"),
            ("Largest steps in length", lambda found: found.measure("length"), "in"),
        ):
            self.write(f"\n{title} on the pickup ladder:")
            for step, lower, upper in steps([found for found in lines if key(found) is not None], key):
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
        self.vans(pickups)

    def vans(self, pickups):
        from .rules import Outcome, test_condition

        vans = self.scheme.data["vans"]
        found = []
        for model_id, entries in self.by_model.items():
            if entries and test_condition(entries[0][1], "model", vans).outcome == Outcome.HOLDS:
                classes = [(year, class_name(result)) for year, _, result in entries]
                flag = "  A PICKUP IN SOME YEARS" if any(name in pickups for _, name in classes) else ""
                found.append(f"{self.model_label(self.models[model_id])}: {spans(classes)}{flag}")
        self.write(f"\nVan check: the vans of data/size-classes.yaml, never pickups ({len(found):,} models)")
        for line in sorted(found):
            self.write(f"  {line}")

    def before_class(self, size_range):
        names = {self.stored.get((size_range.vehicle_model.pk, facts.year), "no class") for facts in size_range.years}
        return " / ".join(sorted(names))

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


def write_report(outcome, out, dry_run):
    Preview(outcome, out, dry_run).run()
