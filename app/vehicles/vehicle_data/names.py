"""The names customers know, from data/vehicle-names.yaml: make spellings,
EPA base models split into nameplates, the other spellings of one vehicle,
and the trim words a customer's model name may carry. Used by the import,
the third-row list and link_vehicles, so every part of the system calls a
vehicle the same thing.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache

import yaml
from django.conf import settings


def name_key(text):
    """A make or model name as it is matched across sources: capitals and
    digits only, so the EPA's "F150" and vPIC's "F-150" are one model."""
    return re.sub(r"[^A-Z0-9]", "", (text or "").upper())


def words(name):
    """A name as words of capitals and digits: "CR-V EX/L" -> ["CRV", "EX", "L"]."""
    return [word for word in (name_key(part) for part in re.split(r"[\s/()]+", name or "")) if word]


def contains(haystack, phrase):
    """Whether the words of phrase appear together, in order, in haystack."""
    haystack, phrase = list(haystack), list(phrase)
    size = len(phrase)
    return size > 0 and any(haystack[start:start + size] == phrase for start in range(len(haystack) - size + 1))


@dataclass(frozen=True)
class Nameplate:
    name: str
    when: tuple  # phrases, each as words()


@dataclass
class Names:
    make_aliases: dict = field(default_factory=dict)  # make key -> catalog make key
    aliases: dict = field(default_factory=dict)  # (make key, model key) -> the name shown
    nameplates: dict = field(default_factory=dict)  # (make key, base model key) -> [Nameplate]
    trim_words: frozenset = frozenset()  # each a word as words() gives it

    @classmethod
    def from_data(cls, data):
        names = cls()
        for other, make in (data.get("make_aliases") or {}).items():
            names.make_aliases[name_key(other)] = name_key(make)
        for entry in data.get("aliases") or []:
            make = names.make_key(entry["make"])
            for spelling in [entry["name"], *entry.get("also", [])]:
                names.aliases[(make, name_key(str(spelling)))] = entry["name"]
        for entry in data.get("nameplates") or []:
            key = (names.make_key(entry["make"]), name_key(entry["base_model"]))
            names.nameplates[key] = [
                Nameplate(split["name"], tuple(tuple(words(phrase)) for phrase in split["when"]))
                for split in entry["split"]
            ]
        names.trim_words = frozenset(word for phrase in data.get("trim_words") or [] for word in words(str(phrase)))
        return names

    def make_key(self, make):
        key = name_key(make)
        return self.make_aliases.get(key, key)

    def model(self, make, model):
        """The name customers know for this make and model name."""
        return self.aliases.get((self.make_key(make), name_key(model)), model)

    def model_key(self, make, model):
        return name_key(self.model(make, model))

    def nameplate(self, make, base_model, epa_model):
        """The nameplate an EPA row belongs to: the first split of its base
        model whose phrase its model name contains, or the base model."""
        found = words(epa_model)
        for plate in self.nameplates.get((self.make_key(make), name_key(base_model)), ()):
            if any(contains(found, phrase) for phrase in plate.when):
                return plate.name
        return base_model

    def nameplate_words(self, make, model):
        """Every word the nameplates split from this model use, such as
        {"SPORT", "XL"} for the Santa Fe, which a trim word never drops."""
        found = set()
        for plate in self.nameplates.get((self.make_key(make), self.model_key(make, model)), ()):
            found.update(words(plate.name))
            for phrase in plate.when:
                found.update(phrase)
        return found


@lru_cache(maxsize=4)
def _load(path, modified):
    return Names.from_data(yaml.safe_load(path.read_text()) or {})


def load_names(data_dir=None):
    """The names in data/vehicle-names.yaml, reread when the file changes."""
    path = (data_dir or settings.DATA_DIR) / "vehicle-names.yaml"
    return _load(path, path.stat().st_mtime_ns)
