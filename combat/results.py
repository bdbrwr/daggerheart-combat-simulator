"""Outcomes of a resolved action, shared by both sides of a fight.

A PC attacking an adversary and an adversary attacking a PC produce the same
shape of outcome - an attack roll, plus a damage roll if it landed - even
though the two roll against different numbers with different dice (duality vs
d20). One result type for both keeps a simulation loop from having to care
which side of the table an attack came from.
"""

from dataclasses import dataclass

from dice.d20 import D20RollResult
from dice.damage import DamageRollResult
from dice.duality import DualityRollResult


@dataclass(frozen=True)
class AttackResult:
    """Outcome of one attack: the attack roll, and the damage roll if it hit."""

    attack_roll: DualityRollResult | D20RollResult
    damage_roll: DamageRollResult | None

    # How many HP the hit actually marked, once thresholds, an Armor Slot and
    # any damage response had their say. Not derivable from `damage_roll`: only
    # the target knows its own thresholds. Content that fires on a landed attack
    # needs the distinction - Unstoppable grows only on a hit that marked 1 or
    # more HP, which is not the same as a hit that dealt damage.
    hp_marked: int = 0

    @property
    def hit(self) -> bool:
        return bool(self.attack_roll.is_success)
