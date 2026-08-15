"""Encounter setup - which adversaries, how many, against which PCs.

## One file, one experiment

An encounter file defines an **Experiment**: a named question, and the
**variations** run side by side to answer it. Variations that belong together
live in one file because that's what makes them a comparison rather than two
unrelated runs, and because the difference between them should be exactly the
knob being moved:

    {
      "name": "Roadside Ambush",
      "notes": "Four adversaries against one tier 1 PC. What does softening buy?",

      "party": ["example_character.json"],
      "starting_fear": 0,
      "starting_spotlight": "pcs",
      "rest": "long",

      "variations": [
        { "name": "As printed",
          "groups": [{ "adversary": "Jagged Knife Bandit", "count": 3 }] },

        { "name": "One fewer bandit",
          "notes": "The obvious first thing to try.",
          "groups": [{ "adversary": "Jagged Knife Bandit", "count": 2 }] }
      ]
    }

Everything outside `variations` is the shared baseline. A variation may override
any of it - `party`, `rest`, `starting_fear`, `starting_spotlight` - so "the same
fight, but walked into with no rest" is a variation rather than a second file.

Each variation becomes an `Encounter`: one runnable fight, which is what
`combat/fight.py` and `simulation/runner.py` take. A Group names an adversary
definition, how many of it show up, and any stat overrides for this encounter's
copies. Overrides live here rather than in the adversary definition so the
definition keeps matching its printed stat block, and so the same adversary can
appear at different settings in different variations.

`spawn()` hands back fresh, independent PCs and adversaries at starting state, so
one variation can be run any number of times without a previous fight's marked HP
leaking into the next.

## Strict on purpose

An unknown key, an unknown adversary, an override naming a stat an Adversary
doesn't have, an unparseable spotlight or rest, or a missing character sheet all
raise, naming the file. A typo that silently defaulted would quietly simulate a
different fight from the one written down, which is the failure this project can
least afford.

`notes` is the one thing JSON costs that a Python definition gave away free: a
docstring explaining *why* a knob was moved. The experiment's notes and the
variation's are carried into the run's report, so the reasoning sits next to the
numbers it produced.

## Sequences

A variation's payload is `groups` - one fight. It is deliberately *a* key rather
than the only one, because a variation will later be able to carry `fights`: a
chain of fights run back to back, with the PCs' and the GM's resources carried
forward, and sequence variations that differ in whether a rest is allowed between
them. Nothing implements that yet, and a file asking for it is told so plainly
rather than being met with "unknown key".
"""

import json
from dataclasses import dataclass, field, fields
from pathlib import Path

from adversaries.adversary import Adversary
from adversaries.catalogue import parse_dice
from adversaries.registry import find_adversary
from characters.player_character import PlayerCharacter
from combat.common import Side
from combat.rest import Rest
from content.names import canonical

CHARACTERS_DIR = Path(__file__).resolve().parent.parent / "characters"

# Settings a variation may inherit from its experiment, or state for itself.
_SHARED_KEYS = frozenset({"party", "starting_fear", "starting_spotlight", "rest"})

_EXPERIMENT_KEYS = _SHARED_KEYS | {"name", "notes", "variations"}
_VARIATION_KEYS = _SHARED_KEYS | {"name", "notes", "groups", "fights"}
_GROUP_KEYS = frozenset({"adversary", "count", "overrides"})

# Every stat a Group may override, taken from the dataclass rather than listed
# here - so adding a stat to Adversary makes it tunable with nothing to update.
_ADVERSARY_STATS = frozenset(stat.name for stat in fields(Adversary))


def _reject_unknown_keys(data: dict, allowed: frozenset[str], what: str, source: str) -> None:
    """Refuse a key nobody reads, so a typo can't quietly become a default."""
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(
            f"{source}: {what} has unknown key(s) {', '.join(repr(key) for key in unknown)}. "
            f"Allowed: {', '.join(sorted(allowed))}."
        )


def _parse_enum(enum_class, value, field_name: str, source: str):
    """An enum member from the string a JSON file wrote, whatever its case."""
    for member in enum_class:
        if canonical(member.value) == canonical(str(value)):
            return member
    allowed = ", ".join(repr(member.value) for member in enum_class)
    raise ValueError(
        f"{source}: {field_name} is {value!r}, which is not one of {allowed}."
    )


def _character_path(entry: str, source: str) -> Path:
    """A party entry as a path - a bare filename means `characters/`."""
    path = Path(entry)
    resolved = path if path.is_absolute() else CHARACTERS_DIR / path
    if not resolved.exists():
        raise ValueError(f"{source}: no character sheet at {resolved}.")
    return resolved


class Group:
    """`count` copies of one adversary definition, with optional stat overrides.

    The adversary is named the way the book names it - `Group("Jagged Knife
    Bandit", count=3)` - and looked up in the registry, so an encounter never
    has to know which module the definition sits in. Passing the Adversary
    object itself works too, where a static reference is worth more than the
    decoupling.

    Not a dataclass: overrides are taken as loose keyword arguments so a group
    reads like the stat block it's tweaking, rather than nesting them in a dict.
    """

    def __init__(self, adversary: Adversary | str, count: int = 1, **overrides):
        # Resolved now rather than at spawn, so a misspelled name fails while the
        # file is being read instead of mid-simulation.
        self.adversary = find_adversary(adversary) if isinstance(adversary, str) else adversary
        self.count = count
        self.overrides = overrides

    @classmethod
    def from_data(cls, data: dict, source: str) -> "Group":
        """One group out of an encounter file, validated eagerly.

        Overrides are checked against the stats an Adversary actually has, so a
        misspelled knob fails while the file is being read rather than at spawn
        time - by which point a run is already under way.

        `damage_dice` is the one override that isn't a bare number, so it goes
        through the catalogue's own `parse_dice`: an encounter writes `"2d6"` or
        `"2d6+1d4"` exactly the way a stat block does. Parsing here rather than
        in `__init__` keeps the JSON path and the Python one honest - a Group
        built in code passes `DiceGroup`s directly, the same way it passes an
        Adversary object instead of a name.
        """
        _reject_unknown_keys(data, _GROUP_KEYS, "a group", source)
        if "adversary" not in data:
            raise ValueError(f"{source}: a group is missing 'adversary'.")

        overrides = dict(data.get("overrides", {}))
        unknown = sorted(set(overrides) - _ADVERSARY_STATS)
        if unknown:
            raise ValueError(
                f"{source}: {data['adversary']!r} is overridden on "
                f"{', '.join(repr(stat) for stat in unknown)}, which an adversary "
                "doesn't have."
            )

        if "damage_dice" in overrides:
            overrides["damage_dice"] = parse_dice(
                overrides["damage_dice"], source, data["adversary"]
            )

        try:
            return cls(data["adversary"], count=data.get("count", 1), **overrides)
        except KeyError as error:
            raise KeyError(f"{source}: {error.args[0]}") from None

    def __repr__(self) -> str:
        parts = [self.adversary.name, f"count={self.count}"]
        parts += [f"{stat}={value!r}" for stat, value in self.overrides.items()]
        return "Group(" + ", ".join(parts) + ")"

    def spawn(self) -> list[Adversary]:
        """`count` independent copies at starting state, overrides applied.

        Raises TypeError if an override names a stat Adversary doesn't have,
        so a typo fails loudly instead of quietly simulating the wrong fight.
        """
        return [self.adversary.spawn(**self.overrides) for _ in range(self.count)]


@dataclass
class Encounter:
    """One variation: a party, an opposition, and the state they meet in.

    This is the runnable unit - what a fight and a Monte Carlo run take. It's
    usually one of several in an experiment, but nothing here needs to know that.

    `starting_fear` and `starting_spotlight` are part of the setup rather than
    the loop's business: a fight picked up mid-scene starts with the GM's pool
    already filled, and an ambush starts with the GM acting. Both change how a
    fight goes enough to be worth sweeping, so they sit here with the rest of
    the tuning.
    """

    name: str
    party: list[Path]
    groups: list[Group]
    starting_fear: int = 0
    starting_spotlight: Side = Side.PCS

    # What the party got before this fight. Rest.NONE is an encounter picked up
    # straight after another one, with nothing refreshed - which is the setup
    # for asking how a party degrades across an adventuring day rather than only
    # how it handles one fresh fight. See combat/rest.py.
    rest: Rest = Rest.LONG

    # Why this variation is set up the way it is, including whatever the
    # experiment as a whole had to say. Printed with the run's report.
    notes: str = ""

    # The experiment this variation belongs to, for titling a report. Empty for
    # an Encounter built directly in Python.
    experiment: str = ""

    @property
    def title(self) -> str:
        """How this run is named in a report - experiment and variation."""
        return f"{self.experiment} - {self.name}" if self.experiment else self.name

    def spawn_party(self) -> list[PlayerCharacter]:
        """Load each PC fresh from its JSON, at whatever state that file describes."""
        return [PlayerCharacter.from_json(path) for path in self.party]

    def spawn_adversaries(self) -> list[Adversary]:
        """Every group's copies, flattened into the order they were listed."""
        return [adversary for group in self.groups for adversary in group.spawn()]

    def spawn(self) -> tuple[list[PlayerCharacter], list[Adversary]]:
        """Both sides at starting state - one simulated fight's worth of combatants."""
        return self.spawn_party(), self.spawn_adversaries()

    @property
    def adversary_count(self) -> int:
        return sum(group.count for group in self.groups)


@dataclass
class Experiment:
    """One encounter file: a named question and the variations that answer it.

    The unit the command line addresses. Running it runs every variation against
    the same dice and prints a comparison table underneath, which is the whole
    tuning workflow in one command.
    """

    name: str
    variations: list[Encounter]
    notes: str = ""
    source: str = field(default="", compare=False)

    @classmethod
    def from_json(cls, path: str | Path) -> "Experiment":
        """Read an encounter file, failing loudly on anything odd."""
        path = Path(path)
        source = path.name
        data = json.loads(path.read_text())

        _reject_unknown_keys(data, _EXPERIMENT_KEYS, "an encounter file", source)
        for required in ("name", "variations"):
            if required not in data:
                raise ValueError(f"{source}: missing required key {required!r}.")
        if not data["variations"]:
            raise ValueError(f"{source}: 'variations' is empty; nothing to run.")

        shared = {key: data[key] for key in _SHARED_KEYS if key in data}
        notes = data.get("notes", "")

        variations = [
            _variation(entry, shared, notes, data["name"], source)
            for entry in data["variations"]
        ]

        claimed: dict[str, str] = {}
        for variation in variations:
            if canonical(variation.name) in claimed:
                raise ValueError(
                    f"{source}: two variations are both named {variation.name!r}. "
                    "Names have to be unique within a file - a comparison table "
                    "has nothing else to tell its rows apart."
                )
            claimed[canonical(variation.name)] = variation.name

        return cls(name=data["name"], variations=variations, notes=notes, source=source)


def _variation(
    data: dict, shared: dict, shared_notes: str, experiment: str, source: str
) -> Encounter:
    """One variation, with anything it didn't state inherited from the file."""
    _reject_unknown_keys(data, _VARIATION_KEYS, "a variation", source)

    if "fights" in data:
        raise ValueError(
            f"{source}: {data.get('name', 'a variation')!r} asks for 'fights'. "
            "Chained fights aren't implemented yet - a variation carries a single "
            "'groups' for now."
        )
    for required in ("name", "groups"):
        if required not in data:
            raise ValueError(f"{source}: a variation is missing {required!r}.")

    settings = {**shared, **{key: data[key] for key in _SHARED_KEYS if key in data}}
    if "party" not in settings:
        raise ValueError(
            f"{source}: {data['name']!r} has no party, and the file states none."
        )

    return Encounter(
        name=data["name"],
        experiment=experiment,
        party=[_character_path(entry, source) for entry in settings["party"]],
        groups=[Group.from_data(group, source) for group in data["groups"]],
        starting_fear=settings.get("starting_fear", 0),
        starting_spotlight=_parse_enum(
            Side,
            settings.get("starting_spotlight", Side.PCS.value),
            "starting_spotlight",
            source,
        ),
        rest=_parse_enum(Rest, settings.get("rest", Rest.LONG.value), "rest", source),
        notes=" ".join(part for part in (shared_notes, data.get("notes", "")) if part),
    )
