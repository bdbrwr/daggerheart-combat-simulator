"""Weapons and armor as data, read out of the JSON catalogues in this package.

Same split as everywhere else in the project: the *record* is JSON, and whatever
the item does beyond its printed numbers is a named feature implemented in
features/weapons.py or features/armor.py. A character sheet names its gear the
way the book does, and that name resolves here.

## What is live and what is provenance

A **weapon's** numbers are live. Nothing on a character sheet carries them, so
the trait a swing rolls, the die it rolls, and its flat bonus all come from this
catalogue and are used in every attack.

An **armor's** numbers are not. A sheet stores Armor Score and damage thresholds
already resolved (see the project's standing rule: any feature whose whole effect
is a number the sheet states has already been applied there), so applying them
again from here would charge the PC twice. They are recorded anyway, because
provenance is worth having and because a future check could tell a reader that a
sheet's numbers no longer match the armor it names - but nothing reads them into
a fight. The reason armor is in this catalogue at all is its **features**.

That is also why armor features and weapon features reach a fight by different
routes. See features/armor.py and features/weapons.py.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from content.names import ARMOR, WEAPON, qualified

_FILE_KEYS = frozenset({"publication", "notes", "weapons", "armor"})

_WEAPON_KEYS = frozenset(
    {
        "name", "trait", "damage_die", "damage_modifier", "damage_type",
        "burden", "range", "tier", "features", "notes", "publication",
    }
)
_WEAPON_REQUIRED = ("name", "trait", "damage_die")

_ARMOR_KEYS = frozenset(
    {
        "name", "base_score", "major_threshold", "severe_threshold",
        "tier", "features", "notes", "publication",
    }
)
_ARMOR_REQUIRED = ("name",)

# The traits a weapon may roll, matching the keys characters/player_character.py
# lowercases a sheet's traits to. A weapon naming anything else would find no
# trait and silently roll a flat modifier of zero.
TRAITS = frozenset({"agility", "strength", "finesse", "instinct", "presence", "knowledge"})


@dataclass(frozen=True)
class Weapon:
    """One weapon's printed record. Immutable - a weapon is never marked."""

    name: str
    trait: str
    damage_die: int
    damage_modifier: int = 0
    damage_type: str = "physical"
    burden: str = "One-Handed"
    range: str = "Melee"
    tier: int = 1
    features: tuple[str, ...] = ()
    publication: str = ""

    @property
    def named_features(self) -> list[str]:
        """This weapon's features, namespaced.

        Qualified because a Warhammer's "Heavy" and Chainmail's "Heavy" are two
        different pieces of content sharing a word - see content/names.py.
        """
        return [qualified(WEAPON, name) for name in self.features]


@dataclass(frozen=True)
class Armor:
    """One armor's printed record.

    `base_score` and the thresholds are recorded but never applied - a sheet
    carries them already resolved. Only `features` reaches a fight.
    """

    name: str
    base_score: int = 0
    major_threshold: int = 0
    severe_threshold: int = 0
    tier: int = 1
    features: tuple[str, ...] = ()
    publication: str = ""

    @property
    def named_features(self) -> list[str]:
        return [qualified(ARMOR, name) for name in self.features]


def _reject_unknown_keys(data: dict, allowed: frozenset, what: str, source: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(
            f"{source}: {what} has unknown key(s) "
            f"{', '.join(repr(key) for key in unknown)}. "
            f"Allowed: {', '.join(sorted(allowed))}."
        )


def _require(data: dict, required, what: str, source: str) -> None:
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(
            f"{source}: {what} is missing {', '.join(repr(key) for key in missing)}."
        )


def _features(data: dict, source: str, entry: str) -> tuple[str, ...]:
    features = data.get("features", [])
    if not isinstance(features, list) or any(not isinstance(f, str) for f in features):
        raise ValueError(
            f"{source}: {entry!r} has 'features' that isn't a list of names. "
            "Write them as strings, and declare each one in features/."
        )
    return tuple(features)


def weapon_from_data(data: dict, publication: str, source: str) -> Weapon:
    """One weapon entry, validated eagerly."""
    _require(data, ("name",), "a weapon entry", source)
    entry = data["name"]
    _reject_unknown_keys(data, _WEAPON_KEYS, f"weapon {entry!r}", source)
    _require(data, _WEAPON_REQUIRED, f"weapon {entry!r}", source)

    trait = str(data["trait"]).strip().lower()
    if trait not in TRAITS:
        raise ValueError(
            f"{source}: weapon {entry!r} rolls {data['trait']!r}, which isn't a "
            f"trait. Expected one of: {', '.join(sorted(TRAITS))}."
        )

    return Weapon(
        name=entry,
        trait=trait,
        damage_die=int(data["damage_die"]),
        damage_modifier=int(data.get("damage_modifier", 0)),
        damage_type=str(data.get("damage_type", "physical")).strip().lower(),
        burden=data.get("burden", "One-Handed"),
        range=data.get("range", "Melee"),
        tier=int(data.get("tier", 1)),
        features=_features(data, source, entry),
        publication=data.get("publication", publication),
    )


def armor_from_data(data: dict, publication: str, source: str) -> Armor:
    """One armor entry, validated eagerly."""
    _require(data, ("name",), "an armor entry", source)
    entry = data["name"]
    _reject_unknown_keys(data, _ARMOR_KEYS, f"armor {entry!r}", source)
    _require(data, _ARMOR_REQUIRED, f"armor {entry!r}", source)

    return Armor(
        name=entry,
        base_score=int(data.get("base_score", 0)),
        major_threshold=int(data.get("major_threshold", 0)),
        severe_threshold=int(data.get("severe_threshold", 0)),
        tier=int(data.get("tier", 1)),
        features=_features(data, source, entry),
        publication=data.get("publication", publication),
    )


def read_catalogue(path: str | Path) -> tuple[list[Weapon], list[Armor]]:
    """Every weapon and armor defined in one catalogue file.

    A file may hold either or both - the SRD tables are separate, but a homebrew
    file usually wants one place for a campaign's gear.
    """
    path = Path(path)
    source = path.name
    data = json.loads(path.read_text())

    if not isinstance(data, dict):
        raise ValueError(
            f"{source}: a catalogue is an object with 'weapons' and/or 'armor', "
            f"not a bare {type(data).__name__}."
        )
    _reject_unknown_keys(data, _FILE_KEYS, "a gear catalogue", source)
    if "weapons" not in data and "armor" not in data:
        raise ValueError(
            f"{source}: defines neither 'weapons' nor 'armor', so nothing in it "
            "can be equipped. Remove the file or give it entries."
        )

    publication = data.get("publication", "")
    weapons = [
        weapon_from_data(entry, publication, source) for entry in data.get("weapons", [])
    ]
    armor = [
        armor_from_data(entry, publication, source) for entry in data.get("armor", [])
    ]
    return weapons, armor
