"""Encounter setup - which adversaries, how many, against which PCs.

An Encounter is the closest thing to the simulation itself, so it's also where
tuning happens. A Group names an adversary definition, how many of it show up,
and any stat overrides to apply to this encounter's copies:

    Group(JAGGED_KNIFE_SNIPER, count=2, hp_max=5, damage_modifier=4)

The overrides go here rather than in the adversary definition so the definition
keeps matching its printed stat block, and so the same adversary can appear at
different settings in different encounters. Sweeping a knob across runs is a
loop over encounters built this way.

`spawn()` hands back fresh, independent PCs and adversaries at starting state,
so one Encounter definition can be run any number of times without a previous
fight's marked HP leaking into the next.
"""

from dataclasses import dataclass
from pathlib import Path

from adversaries.adversary import Adversary
from adversaries.registry import find_adversary
from characters.player_character import PlayerCharacter
from combat.common import Side
from combat.rest import Rest

CHARACTERS_DIR = Path(__file__).resolve().parent.parent / "characters"


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
        # Resolved now rather than at spawn, so a misspelled name fails when the
        # encounter module is imported instead of mid-simulation.
        self.adversary = find_adversary(adversary) if isinstance(adversary, str) else adversary
        self.count = count
        self.overrides = overrides

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
    """One side's adversaries against a party, ready to be run repeatedly.

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
