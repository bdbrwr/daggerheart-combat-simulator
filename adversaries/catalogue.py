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
from content.aoe import band_named
from content.damage_types import damage_type_named
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
    # Required rather than defaulted, even though no positioning is tracked and
    # an ordinary attack never reads it. A feature that turns the standard attack
    # into an area one sweeps *this* band, so an omitted range would quietly
    # decide how many combatants such a feature reaches - the exact class of
    # silent difference the rest of this list exists to prevent.
    "range",
)

_FILE_KEYS = frozenset({"publication", "notes", "adversaries"})

# "2d6", or "d8" for a single die. Sizes and counts only - a flat modifier is
# `damage_modifier`, so that an encounter can tune the two independently.
_DIE = re.compile(r"^(\d*)d(\d+)$", re.IGNORECASE)

# What the book's `Thresholds: None` becomes.
#
# Some stat blocks print no thresholds at all - Minions, and small things like
# the Tiny Green Ooze on 2 HP. Every case found so far is an adversary with less
# HP than the threshold would ever become relevant for: a Minion is defeated by
# any damage, so there is no second or third HP for a Major hit to mark.
#
# A threshold set out of reach expresses that exactly, and every hit lands in the
# lowest band, which is the right answer. Zero would be catastrophically wrong -
# it would put every hit at or above Severe and mark 3 HP off a 1 HP track.
NO_THRESHOLD = 9999

_UNPRINTED_THRESHOLD = frozenset({"none", ""})
_THRESHOLDS = ("major_threshold", "severe_threshold")


def parse_threshold(value, source: str, entry: str) -> int:
    """One damage threshold, reading the book's `None` as out of reach.

    JSON `null` and the string `"None"` are both accepted, since the reference
    data spells it one way and a hand-typed entry may well spell it the other.
    """
    if value is None or (
        isinstance(value, str) and value.strip().casefold() in _UNPRINTED_THRESHOLD
    ):
        return NO_THRESHOLD

    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{source}: {entry!r} has a threshold of {value!r}, which is neither a "
            "number nor 'None'. The book prints 'None' for adversaries with too "
            "few HP for the threshold to matter; anything else has to be a number."
        ) from None


def parse_range(value, source: str, entry: str) -> str:
    """The printed range band of a standard attack, validated and normalised.

    Stored back as the band's canonical spelling, so a file writing "very close"
    ends up carrying "Very Close" and a report prints the book's own wording
    whatever the entry was typed as.
    """
    try:
        return band_named(value).value
    except ValueError as error:
        raise ValueError(
            f"{source}: {entry!r} has a range of {value!r}. {error} It is the band "
            "printed beside the standard attack - 'Claws: Very Close, 1d12+2'."
        ) from None


def parse_damage_type(value, source: str, entry: str) -> str:
    """The printed type of a standard attack, validated and normalised.

    Stored back as the type's canonical spelling, so an entry typed the way the
    page abbreviates it - "1d12+6 **mag**" - ends up carrying "magic" and a
    report prints one vocabulary rather than two.

    Unlike `range`, an omitted type is allowed and comes back as "". A stat block
    with no type simply never has anyone's resistance applied to its attack,
    which is the behaviour every fight had before types existed. A type that is
    *stated and unrecognised* raises, because that is the case where a resistance
    would silently never fire - indistinguishable from one nobody implemented.
    """
    try:
        matched = damage_type_named(value)
    except ValueError as error:
        raise ValueError(
            f"{source}: {entry!r} has a damage type of {value!r}. {error} It is "
            "what the stat block prints beside the standard attack's dice - "
            "'Warp Blast: Close, 1d12+6 mag'."
        ) from None
    return matched.value if matched is not None else ""


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
    for threshold in _THRESHOLDS:
        stats[threshold] = parse_threshold(data[threshold], source, entry)
    stats["range"] = parse_range(data["range"], source, entry)
    stats["damage_type"] = parse_damage_type(data.get("damage_type"), source, entry)
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
