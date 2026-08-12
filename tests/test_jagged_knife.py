from unittest.mock import patch

from adversaries.jagged_knife import (
    jagged_knife_bandit_attack,
    jagged_knife_sniper_attack,
    make_jagged_knife_bandit,
    make_jagged_knife_sniper,
)
from dice.common import AdvantageState
from dice.d20 import D20RollResult
from dice.damage import DamageRollResult, DiceGroup


class FakeTarget:
    """A minimal stand-in for the adversaries.adversary.Target protocol."""

    def __init__(self, evasion: int = 10):
        self.evasion = evasion
        self.damage_taken: list[int] = []

    def take_damage(self, amount: int) -> int:
        self.damage_taken.append(amount)
        return amount


def _d20_result(*, die: int, modifier: int, evasion: int) -> D20RollResult:
    return D20RollResult(
        die_results=[die],
        modifier=modifier,
        advantage_state=AdvantageState.NONE,
        evasion=evasion,
    )


def test_make_jagged_knife_bandit_stats():
    bandit = make_jagged_knife_bandit()
    assert bandit.name == "Jagged Knife Bandit"
    assert bandit.tier == 1
    assert bandit.difficulty == 12
    assert bandit.major_threshold == 8
    assert bandit.severe_threshold == 14
    assert bandit.hp_max == 5
    assert bandit.stress_max == 3
    assert bandit.attack_modifier == 1


def test_make_jagged_knife_sniper_stats():
    sniper = make_jagged_knife_sniper()
    assert sniper.name == "Jagged Knife Sniper"
    assert sniper.tier == 1
    assert sniper.difficulty == 13
    assert sniper.major_threshold == 4
    assert sniper.severe_threshold == 7
    assert sniper.hp_max == 3
    assert sniper.stress_max == 2
    assert sniper.attack_modifier == -1


def test_bandit_attack_hit_rolls_and_applies_damage():
    bandit = make_jagged_knife_bandit()
    target = FakeTarget(evasion=10)
    hit_roll = _d20_result(die=15, modifier=1, evasion=10)  # total 16, not a crit
    damage_roll = DamageRollResult(dice_groups=[DiceGroup(count=1, sides=8)], die_results=[[5]], modifier=1)

    with (
        patch("adversaries.jagged_knife.roll_d20", return_value=hit_roll) as mock_roll_d20,
        patch("adversaries.jagged_knife.roll_damage", return_value=damage_roll),
    ):
        result = jagged_knife_bandit_attack(bandit, target)

    assert result.hit is True
    assert result.damage_roll is damage_roll
    assert target.damage_taken == [6]  # 5 rolled + 1 flat modifier
    assert mock_roll_d20.call_args.kwargs["modifier"] == bandit.attack_modifier
    assert mock_roll_d20.call_args.kwargs["evasion"] == target.evasion


def test_bandit_attack_miss_deals_no_damage():
    bandit = make_jagged_knife_bandit()
    target = FakeTarget(evasion=18)
    miss_roll = _d20_result(die=5, modifier=1, evasion=18)  # total 6, well below evasion

    with (
        patch("adversaries.jagged_knife.roll_d20", return_value=miss_roll),
        patch("adversaries.jagged_knife.roll_damage") as mock_roll_damage,
    ):
        result = jagged_knife_bandit_attack(bandit, target)

    assert result.hit is False
    assert result.damage_roll is None
    assert target.damage_taken == []
    mock_roll_damage.assert_not_called()


def test_sniper_attack_hit_rolls_and_applies_damage():
    sniper = make_jagged_knife_sniper()
    target = FakeTarget(evasion=10)
    hit_roll = _d20_result(die=18, modifier=-1, evasion=10)  # total 17, not a crit
    damage_roll = DamageRollResult(dice_groups=[DiceGroup(count=1, sides=10)], die_results=[[6]], modifier=2)

    with (
        patch("adversaries.jagged_knife.roll_d20", return_value=hit_roll) as mock_roll_d20,
        patch("adversaries.jagged_knife.roll_damage", return_value=damage_roll),
    ):
        result = jagged_knife_sniper_attack(sniper, target)

    assert result.hit is True
    assert target.damage_taken == [8]  # 6 rolled + 2 flat modifier
    assert mock_roll_d20.call_args.kwargs["modifier"] == sniper.attack_modifier
