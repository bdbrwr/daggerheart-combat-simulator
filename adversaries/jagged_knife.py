"""The Jagged Knife gang's adversaries - both Tier 1.

Each adversary is a `make_*()` factory for its starting stats plus an
`*_attack()` callable for its standard attack, following the same shape as
items/weapons.py: the callable reads the adversary's own modifier and weapon
dice, rolls the attack, and on a hit rolls and applies damage directly.

Passive features that aren't part of a standard attack roll (Climber, From
Above, Unseen Strike) aren't modeled - they depend on position/Hidden state
this scaffolding doesn't track yet. Picked deliberately as adversaries whose
features have little expected impact on simulated outcomes; noted here for
debugging, not implemented.
"""

from dataclasses import dataclass

from adversaries.adversary import Adversary, Target
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup, roll_damage
from dice.d20 import D20RollResult, roll_d20


@dataclass(frozen=True)
class AttackResult:
    """Outcome of one adversary attack: the attack roll, and the damage roll if it hit."""

    attack_roll: D20RollResult
    damage_roll: DamageRollResult | None

    @property
    def hit(self) -> bool:
        return bool(self.attack_roll.is_success)


def make_jagged_knife_bandit() -> Adversary:
    """Tier 1 Standard. Difficulty 12, Thresholds 8/14, HP 5, Stress 3.

    Climber (Passive): easy terrain traversal, not combat-relevant.
    From Above (Passive): 1d10+1 instead of standard damage when attacking
    from above - not modeled (no position tracking yet).
    """
    return Adversary(
        name="Jagged Knife Bandit",
        tier=1,
        difficulty=12,
        major_threshold=8,
        severe_threshold=14,
        hp_max=5,
        stress_max=3,
        attack_modifier=1,
    )


def jagged_knife_bandit_attack(
    adversary: Adversary,
    target: Target,
    advantage_state: AdvantageState = AdvantageState.NONE,
) -> AttackResult:
    """Daggers: melee, 1d8+1 physical."""
    attack_roll = roll_d20(
        modifier=adversary.attack_modifier,
        evasion=target.evasion,
        advantage_state=advantage_state,
    )

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=1, sides=8)],
        modifier=1,
        is_critical=attack_roll.is_critical,
    )
    target.take_damage(damage_roll.total)
    return AttackResult(attack_roll=attack_roll, damage_roll=damage_roll)


def make_jagged_knife_sniper() -> Adversary:
    """Tier 1 Ranged. Difficulty 13, Thresholds 4/7, HP 3, Stress 2.

    Unseen Strike (Passive): 1d10+4 instead of standard damage when the
    Sniper is Hidden - not modeled (no Hidden state tracked yet).
    """
    return Adversary(
        name="Jagged Knife Sniper",
        tier=1,
        difficulty=13,
        major_threshold=4,
        severe_threshold=7,
        hp_max=3,
        stress_max=2,
        attack_modifier=-1,
    )


def jagged_knife_sniper_attack(
    adversary: Adversary,
    target: Target,
    advantage_state: AdvantageState = AdvantageState.NONE,
) -> AttackResult:
    """Shortbow: far range, 1d10+2 physical."""
    attack_roll = roll_d20(
        modifier=adversary.attack_modifier,
        evasion=target.evasion,
        advantage_state=advantage_state,
    )

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=1, sides=10)],
        modifier=2,
        is_critical=attack_roll.is_critical,
    )
    target.take_damage(damage_roll.total)
    return AttackResult(attack_roll=attack_roll, damage_roll=damage_roll)
