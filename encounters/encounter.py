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
from characters.player_character import PlayerCharacter

CHARACTERS_DIR = Path(__file__).resolve().parent.parent / "characters"


class Group:
    """`count` copies of one adversary definition, with optional stat overrides.

    Not a dataclass: overrides are taken as loose keyword arguments so a group
    reads like the stat block it's tweaking - `Group(SOME_ADVERSARY, count=2,
    hp_max=5)` - rather than nesting them in a dict literal.
    """

    def __init__(self, adversary: Adversary, count: int = 1, **overrides):
        self.adversary = adversary
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
    """One side's adversaries against a party, ready to be run repeatedly."""

    name: str
    party: list[Path]
    groups: list[Group]

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
