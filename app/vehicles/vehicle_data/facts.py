"""One source's facts about one model year, gathered across the source's
rows: a set of values for each listed fact and a range for each measured
one, with how the rows spread across them, so a rule can go by what most of
a model year's rows say."""

from collections import Counter, defaultdict

LISTED = ("epa_size_classes", "drives", "body_styles", "source_vehicle_types", "cab_styles", "seat_rows")
MEASURED = (
    "passenger_volume", "luggage_volume", "gvwr", "curb_weight", "length", "width", "height", "wheelbase",
)
# Every VehicleModelYear field an import writes, in the order compared.
FACT_FIELDS = (
    LISTED + tuple(f"{name}_{end}" for name in MEASURED for end in ("min", "max")) + ("source_ids", "distribution")
)
BODY_STYLES = ("two-door", "four-door", "hatchback", "unknown")
CAB_STYLES = ("regular", "extended", "crew")
ORDER = {"body_styles": BODY_STYLES, "cab_styles": CAB_STYLES}


def ordered(name, values):
    return sorted(values, key=ORDER[name].index) if name in ORDER else sorted(values)


def number(value):
    """A measured value as JSON stores it: whole numbers as int, tenths as float."""
    return int(value) if value == int(value) else float(value)


class Facts:
    def __init__(self, id_fields=None):
        # With id_fields, each source id is a tuple stored as a dict with
        # those keys, such as vPIC's {"make_id": 460, "model_id": 1801}.
        self.id_fields = id_fields
        self.listed = defaultdict(set)
        self.counts = defaultdict(Counter)
        self.ranges = {}
        self.measures = defaultdict(list)
        self.ids = set()

    def add(self, name, value):
        if value not in (None, ""):
            self.listed[name].add(value)
            self.counts[name][value] += 1

    def measure(self, name, value):
        if value is None:
            return
        low, high = self.ranges.get(name, (value, value))
        self.ranges[name] = (min(low, value), max(high, value))
        self.measures[name].append(number(value))

    def merge(self, other):
        for name, values in other.listed.items():
            self.listed[name] |= values
            self.counts[name].update(other.counts[name])
        for name, (low, high) in other.ranges.items():
            current_low, current_high = self.ranges.get(name, (low, high))
            self.ranges[name] = (min(current_low, low), max(current_high, high))
            self.measures[name].extend(other.measures[name])
        self.ids |= other.ids

    def values(self):
        """The VehicleModelYear fields, every one of FACT_FIELDS."""
        values = {}
        for name in LISTED:
            values[name] = ordered(name, self.listed.get(name, ()))
        for name in MEASURED:
            values[f"{name}_min"], values[f"{name}_max"] = self.ranges.get(name, (None, None))
        ids = sorted(self.ids)
        values["source_ids"] = [dict(zip(self.id_fields, found)) for found in ids] if self.id_fields else ids
        values["distribution"] = distribution(
            {name: dict(self.counts[name]) for name in LISTED if self.counts.get(name)},
            {name: self.measures[name] for name in MEASURED if self.measures.get(name)},
        )
        return values


def distribution(counts, measures):
    """{fact: {value: rows}} for listed facts and {fact: [each row's value]}
    for measured ones, in a stable order."""
    found = {name: {str(value): counts[name][value] for value in ordered(name, counts[name])} for name in counts}
    found.update({name: sorted(measures[name]) for name in measures})
    return found


def merge_rows(keep, drop):
    """Fold one model-year record into another of the same source, as when two
    catalog models turn out to be one vehicle."""
    for name in LISTED:
        setattr(keep, name, ordered(name, set(getattr(keep, name)) | set(getattr(drop, name))))
    for name in MEASURED:
        lows = [value for value in (getattr(keep, f"{name}_min"), getattr(drop, f"{name}_min")) if value is not None]
        highs = [value for value in (getattr(keep, f"{name}_max"), getattr(drop, f"{name}_max")) if value is not None]
        setattr(keep, f"{name}_min", min(lows) if lows else None)
        setattr(keep, f"{name}_max", max(highs) if highs else None)
    seen, ids = set(), []
    for found in [*keep.source_ids, *drop.source_ids]:
        key = tuple(sorted(found.items())) if isinstance(found, dict) else found
        if key not in seen:
            seen.add(key)
            ids.append(found)
    keep.source_ids = ids
    counts, measures = {}, {}
    for spread in (keep.distribution or {}, drop.distribution or {}):
        for name, values in spread.items():
            if isinstance(values, dict):
                counts.setdefault(name, Counter()).update(values)
            else:
                measures.setdefault(name, []).extend(values)
    keep.distribution = distribution(counts, measures)
    keep.first_seen = min(keep.first_seen, drop.first_seen)
    keep.last_seen = max(keep.last_seen, drop.last_seen)
