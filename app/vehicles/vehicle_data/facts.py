"""One source's facts about one model year, gathered across the source's
rows: a set of values for each listed fact and a range for each measured one."""

from collections import defaultdict

LISTED = ("epa_size_classes", "drives", "body_styles", "source_vehicle_types", "cab_styles", "seat_rows")
MEASURED = (
    "passenger_volume", "luggage_volume", "gvwr", "curb_weight", "length", "width", "height", "wheelbase",
)
# Every VehicleModelYear field an import writes, in the order compared.
FACT_FIELDS = LISTED + tuple(f"{name}_{end}" for name in MEASURED for end in ("min", "max")) + ("source_ids",)
BODY_STYLES = ("two-door", "four-door", "hatchback", "unknown")
CAB_STYLES = ("regular", "extended", "crew")
ORDER = {"body_styles": BODY_STYLES, "cab_styles": CAB_STYLES}


class Facts:
    def __init__(self, id_fields=None):
        # With id_fields, each source id is a tuple stored as a dict with
        # those keys, such as vPIC's {"make_id": 460, "model_id": 1801}.
        self.id_fields = id_fields
        self.listed = defaultdict(set)
        self.ranges = {}
        self.ids = set()

    def add(self, name, value):
        if value not in (None, ""):
            self.listed[name].add(value)

    def measure(self, name, value):
        if value is None:
            return
        low, high = self.ranges.get(name, (value, value))
        self.ranges[name] = (min(low, value), max(high, value))

    def merge(self, other):
        for name, values in other.listed.items():
            self.listed[name] |= values
        for name, (low, high) in other.ranges.items():
            self.measure(name, low)
            self.measure(name, high)
        self.ids |= other.ids

    def values(self):
        """The VehicleModelYear fields, every one of FACT_FIELDS."""
        values = {}
        for name in LISTED:
            found = self.listed.get(name, ())
            values[name] = sorted(found, key=ORDER[name].index) if name in ORDER else sorted(found)
        for name in MEASURED:
            values[f"{name}_min"], values[f"{name}_max"] = self.ranges.get(name, (None, None))
        ids = sorted(self.ids)
        values["source_ids"] = [dict(zip(self.id_fields, found)) for found in ids] if self.id_fields else ids
        return values
