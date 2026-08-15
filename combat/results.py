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
    """Outcome of one action: the attack roll if there was one, the damage if it hit.

    `attack_roll` is None for an action that used its combatant's spotlight
    without rolling to hit anybody. The SRD has several - the Acid Burrower's
    Earth Eruption bursts out of the ground and makes every PC nearby roll to
    keep their feet, which is a Reaction Roll from *them* and no attack from it.

    Such an action still has to return something rather than declining, because
    returning None means "I passed, offer the spotlight to something else" and
    would hand the adversary a second action in the same turn.
    """

    attack_roll: DualityRollResult | D20RollResult | None
    damage_roll: DamageRollResult | None

    # How many HP the hit actually marked, once thresholds, an Armor Slot and
    # any damage response had their say. Not derivable from `damage_roll`: only
    # the target knows its own thresholds. Content that fires on a landed attack
    # needs the distinction - Unstoppable grows only on a hit that marked 1 or
    # more HP, which is not the same as a hit that dealt damage.
    hp_marked: int = 0

    @property
    def made_an_attack(self) -> bool:
        """Whether this action rolled to hit at all.

        The question a loop has to ask before reading the roll - and the reason
        it's a property here rather than an `is not None` check at each site is
        that "there was no roll" is a fact about the action, not a null check.
        """
        return self.attack_roll is not None

    @property
    def hit(self) -> bool:
        return self.made_an_attack and bool(self.attack_roll.is_success)
