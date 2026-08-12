"""Weapon attacks.

Each weapon is a callable, not a data record: reads the attacker's trait and Proficiency, rolls the attack against the target's Difficulty, and - on a hit - rolls and applies damage. The only reason a weapon's stats exist in this codebase is to run them in a simulated fight, so they're written as the code that does that rather than as a description of it that something else wouldhave to interpret.

Docstrings describe what a weapon *should* do (a paraphrase, not the SRDtext verbatim) so a mismatch between the two is easy to spot while debugging.
"""

from typing import Protocol

from characters.player_character import PlayerCharacter
from combat.results import AttackResult
from dice.common import AdvantageState
from dice.damage import DiceGroup, roll_damage
from dice.duality import roll_duality


class Target(Protocol):
    """Anything a PC's weapon can attack - an adversary."""

    difficulty: int

    def take_damage(self, amount: int) -> int: ...


def broadsword_attack(
    attacker: PlayerCharacter,
    target: Target,
    advantage_state: AdvantageState = AdvantageState.NONE,
) -> AttackResult:
    """Broadsword: Agility, melee, one-handed, d8 physical.
    Reliable: +1 to attack rolls.
    """
    attack_roll = roll_duality(
        modifier=attacker.traits["agility"] + 1,  # +1 from Reliable
        difficulty=target.difficulty,
        advantage_state=advantage_state,
    )

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=attacker.proficiency, sides=8)],
        is_critical=attack_roll.is_critical,
    )
    target.take_damage(damage_roll.total)
    return AttackResult(attack_roll=attack_roll, damage_roll=damage_roll)
