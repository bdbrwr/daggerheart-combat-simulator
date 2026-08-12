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

    @property
    def hit(self) -> bool:
        return bool(self.attack_roll.is_success)
