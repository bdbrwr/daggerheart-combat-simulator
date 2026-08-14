"""Weapon attacks.

Each weapon is a callable, not a data record: reads the attacker's trait and Proficiency, rolls the attack against the target's Difficulty, and - on a hit - rolls and applies damage. The only reason a weapon's stats exist in this codebase is to run them in a simulated fight, so they're written as the code that does that rather than as a description of it that something else wouldhave to interpret.

Docstrings describe what a weapon *should* do (a paraphrase, not the SRDtext verbatim) so a mismatch between the two is easy to spot while debugging.

Every weapon shares the same shape - roll against Difficulty, roll Proficiency dice on a hit - so that shape lives in `_attack_with` and each weapon is the line that describes itself. A weapon whose attack does something that shape can't express writes its own function instead; none does yet.

Weapon features that only change a number already resolved on the character sheet are NOT applied here. Greatsword's Massive says "-1 to Evasion", and a sheet stores its Evasion already worked out, so applying it again would charge the PC twice. Features that change the roll itself (Reliable's +1 to attack, Massive and Powerful's discarded die) are applied.

Range is recorded in the docstrings and otherwise unused - nothing in the simulator tracks distance. See SIMULATION-RULES.md.
"""

from typing import Protocol

from characters.player_character import PlayerCharacter
from combat.results import AttackResult
from content import total_extra_damage
from dice.common import AdvantageState
from dice.damage import DiceGroup, roll_damage
from dice.duality import roll_duality
from items.registry import weapon


class Target(Protocol):
    """Anything a PC's weapon can attack - an adversary."""

    difficulty: int

    def take_damage(self, amount: int, fight=None) -> int: ...


def _attack_with(
    attacker: PlayerCharacter,
    target: Target,
    advantage_state: AdvantageState,
    bonus: int,
    damage_bonus: int = 0,
    hope_die: int = 12,
    fight=None,
    *,
    trait: str,
    sides: int,
    modifier: int = 0,
    attack_bonus: int = 0,
    discards_lowest: bool = False,
) -> AttackResult:
    """The shape every weapon attack shares.

    `bonus` is a flat add to the attack roll from outside the weapon - an
    Experience the PC spent Hope on, mostly. `damage_bonus` is the same idea for
    damage, and is where content like Body Basher lands. Both are parameters
    rather than something the weapon works out for itself, because whether an
    Experience or a domain card applies is a decision made by the acting
    character, not by the sword.

    `damage_bonus` is added before the target's thresholds are consulted, so it
    can change how many HP a hit marks and not just the number printed.

    `discards_lowest` covers Massive and Powerful: an extra damage die is
    rolled and the lowest of the pool is thrown away.

    `fight` is only passed along to the extra-damage dispatch below, which is
    the one thing here that can't be worked out before the attack is rolled.
    """
    attack_roll = roll_duality(
        modifier=attacker.traits[trait] + attack_bonus + bonus,
        difficulty=target.difficulty,
        advantage_state=advantage_state,
        hope_die=hope_die,
    )

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    # Content that adds dice conditional on how the attack came out joins the
    # same roll, so its dice are counted before the target's thresholds rather
    # than arriving as a second hit. One call; no weapon knows what it adds.
    count = attacker.proficiency + (1 if discards_lowest else 0)
    dice_groups = [DiceGroup(count=count, sides=sides)]
    dice_groups += total_extra_damage(attacker, target, attack_roll, fight)

    damage_roll = roll_damage(
        dice_groups=dice_groups,
        modifier=modifier + damage_bonus,
        is_critical=attack_roll.is_critical,
        drop_lowest=1 if discards_lowest else 0,
    )
    marked = target.take_damage(damage_roll.total)
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


@weapon("Broadsword")
def broadsword_attack(
    attacker: PlayerCharacter,
    target: Target,
    advantage_state: AdvantageState = AdvantageState.NONE,
    bonus: int = 0,
    damage_bonus: int = 0,
    hope_die: int = 12,
    fight=None,
) -> AttackResult:
    """Broadsword: Agility, melee, one-handed, d8 physical.
    Reliable: +1 to attack rolls.
    """
    return _attack_with(
        attacker, target, advantage_state, bonus, damage_bonus, hope_die, fight,
        trait="agility", sides=8, attack_bonus=1,
    )


@weapon("Shortbow")
def shortbow_attack(
    attacker: PlayerCharacter,
    target: Target,
    advantage_state: AdvantageState = AdvantageState.NONE,
    bonus: int = 0,
    damage_bonus: int = 0,
    hope_die: int = 12,
    fight=None,
) -> AttackResult:
    """Shortbow: Agility, far, two-handed, d6+3 physical. No feature."""
    return _attack_with(
        attacker, target, advantage_state, bonus, damage_bonus, hope_die, fight,
        trait="agility", sides=6, modifier=3,
    )


@weapon("Greatsword")
def greatsword_attack(
    attacker: PlayerCharacter,
    target: Target,
    advantage_state: AdvantageState = AdvantageState.NONE,
    bonus: int = 0,
    damage_bonus: int = 0,
    hope_die: int = 12,
    fight=None,
) -> AttackResult:
    """Greatsword: Strength, melee, two-handed, d10+3 physical.
    Massive: -1 to Evasion; on a hit, roll an extra damage die and discard the lowest.

    The Evasion penalty is deliberately not applied - a character sheet stores
    Evasion already resolved, so subtracting it here would charge it twice.
    """
    return _attack_with(
        attacker, target, advantage_state, bonus, damage_bonus, hope_die, fight,
        trait="strength", sides=10, modifier=3, discards_lowest=True,
    )


@weapon("Greatstaff")
def greatstaff_attack(
    attacker: PlayerCharacter,
    target: Target,
    advantage_state: AdvantageState = AdvantageState.NONE,
    bonus: int = 0,
    damage_bonus: int = 0,
    hope_die: int = 12,
    fight=None,
) -> AttackResult:
    """Greatstaff: Knowledge, very far, two-handed, d6 magic.
    Powerful: on a hit, roll an extra damage die and discard the lowest.
    """
    return _attack_with(
        attacker, target, advantage_state, bonus, damage_bonus, hope_die, fight,
        trait="knowledge", sides=6, discards_lowest=True,
    )
