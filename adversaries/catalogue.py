"""Reading adversary stat blocks out of the JSON catalogues in this package.

## Why JSON

A stat block is data: a name, some numbers, and a list of feature names. Nothing
in it runs. Authoring them as Python modules meant the registry *imported* every
one on every lookup, so a single broken homebrew file took down `--list`, every
encounter, and the whole run - and homebrew adversaries are exactly what this
simulator exists to tune, so that file is the one being edited most. Data files
fail one at a time.

It also finishes a pattern the rest of the project already follows. A character
sheet is JSON and *names* the domain cards that are code; an adversary stat block
is the GM-side sheet, so it is JSON and names the features that are code.

## The keys are the stat names an encounter overrides

Every key except `name`, `features` and `notes` is a field on `Adversary`, spelled
exactly the way an encounter's `overrides` block spells it. That is deliberate:
somebody reading `hp_max: 5` in the catalogue and writing `"hp_max": 7` in an
encounter is using one vocabulary, not translating between two.

## Strict, and loud about it

An unknown key, a missing stat, unparseable damage dice or a duplicate name all
raise, naming the file and the entry. A typo that quietly defaulted would mean
simulating a different adversary from the one written down, which is the failure
this project can least afford. One bad *entry* is reported without costing the
rest of the file; only a file that isn't valid JSON at all costs the whole file,
and registry.py keeps that in `load_errors()` rather than dropping it.
"""

import json
import re
from dataclasses import fields
from pathlib import Path

from adversaries.adversary import Adversary
from dice.damage import DiceGroup

# Everything a catalogue entry may say, taken from the dataclass rather than
# listed here - so adding a stat to Adversary makes it authorable with nothing
# to update. `notes` is the one addition: prose that explains an entry and is
# never read by the fight loop.
_STATS = frozenset(stat.name for stat in fields(Adversary))
_ENTRY_KEYS = _STATS | {"notes"}

# State a fight marks, which a definition must never carry: a stat block
# describes an adversary walking into a fight, not one already bloodied in it.
_RUNTIME_ONLY = frozenset({"hp_marked", "stress_marked"})

_AUTHORABLE = _ENTRY_KEYS - _RUNTIME_ONLY

# Stats with no sensible default. Anything omitted here would silently become a
# zero, and a zero Difficulty or an empty HP track is a different fight.
_REQUIRED = (
    "name",
    "tier",
    "difficulty",
    "major_threshold",
    "severe_threshold",
    "hp_max",
    "stress_max",
    "attack_modifier",
)

_FILE_KEYS = frozenset({"publication", "notes", "adversaries"})

# "2d6", or "d8" for a single die. Sizes and counts only - a flat modifier is
# `damage_modifier`, so that an encounter can tune the two independently.
_DIE = re.compile(r"^(\d*)d(\d+)$", re.IGNORECASE)


def parse_dice(spec, source: str, entry: str) -> list[DiceGroup]:
    """Damage dice from `"1d8"`, or `["2d6", "1d4"]`, or nothing at all.

    A string may join several groups with `+` - `"2d6+1d4"` - so a stat block
    that rolls a mixed pool reads the way the book prints it. An empty spec is a
    real answer, not an error: an adversary can deal flat damage, and the fight
    tests rig one that deals none.
    """
    if spec is None or spec == "":
        return []

    terms = spec if isinstance(spec, list) else str(spec).split("+")

    groups = []
    for term in terms:
        matched = _DIE.match(str(term).strip())
        if matched is None:
            raise ValueError(
                f"{source}: {entry!r} has damage dice {term!r}, which isn't a die "
                "size. Expected something like '1d8', '2d6' or '2d6+1d4'; a flat "
                "bonus belongs in 'damage_modifier'."
            )
        count, sides = matched.groups()
        groups.append(DiceGroup(count=int(count) if count else 1, sides=int(sides)))
    return groups


def adversary_from_data(data: dict, publication: str, source: str) -> Adversary:
    """One catalogue entry as an Adversary definition, validated eagerly."""
    if "name" not in data:
        raise ValueError(f"{source}: an adversary entry is missing 'name'.")
    entry = data["name"]

    unknown = sorted(set(data) - _AUTHORABLE)
    if unknown:
        marked = sorted(set(data) & _RUNTIME_ONLY)
        hint = (
            f" ({', '.join(marked)} is state a fight marks, not something a stat "
            "block starts with.)"
            if marked
            else ""
        )
        raise ValueError(
            f"{source}: {entry!r} has unknown key(s) "
            f"{', '.join(repr(key) for key in unknown)}.{hint} "
            f"Allowed: {', '.join(sorted(_AUTHORABLE))}."
        )

    missing = [key for key in _REQUIRED if key not in data]
    if missing:
        raise ValueError(
            f"{source}: {entry!r} is missing {', '.join(repr(key) for key in missing)}. "
            "Every stat that decides how dangerous an adversary is has to be "
            "stated - defaulting one would quietly simulate a different fight."
        )

    features = data.get("features", [])
    if not isinstance(features, list) or any(not isinstance(f, str) for f in features):
        raise ValueError(
            f"{source}: {entry!r} has 'features' that isn't a list of names. "
            'Write them as strings - ["Relentless", "Horde"] - and implement '
            "them in features/adversaries.py."
        )

    stats = {key: data[key] for key in _STATS if key in data}
    stats["damage_dice"] = parse_dice(data.get("damage_dice"), source, entry)
    stats["features"] = list(features)
    # The file says which book it is once, rather than every entry repeating it.
    stats["publication"] = data.get("publication", publication)

    return Adversary(**stats)


def read_catalogue(path: str | Path) -> list[Adversary]:
    """Every adversary defined in one catalogue file.

    Raises if the file itself is malformed. An entry that won't validate raises
    too, naming both the file and the entry - the caller decides whether that
    costs one file or the whole run.
    """
    path = Path(path)
    source = path.name
    data = json.loads(path.read_text())

    if not isinstance(data, dict):
        raise ValueError(
            f"{source}: a catalogue is an object with an 'adversaries' list, not "
            f"a bare {type(data).__name__}."
        )

    unknown = sorted(set(data) - _FILE_KEYS)
    if unknown:
        raise ValueError(
            f"{source}: unknown key(s) {', '.join(repr(key) for key in unknown)}. "
            f"Allowed: {', '.join(sorted(_FILE_KEYS))}."
        )
    if "adversaries" not in data:
        raise ValueError(f"{source}: missing required key 'adversaries'.")

    publication = data.get("publication", "")
    return [
        adversary_from_data(entry, publication, source) for entry in data["adversaries"]
    ]
