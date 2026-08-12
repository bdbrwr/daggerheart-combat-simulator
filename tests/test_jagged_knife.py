"""The stat blocks as printed - these should only ever change if the book does.

Per-encounter tuning happens in encounters/, so a failure here means either a
transcription error or that someone edited the definition where they meant to
add an override.
"""

from adversaries.srd import JAGGED_KNIFE_BANDIT, JAGGED_KNIFE_SNIPER
from dice.damage import DiceGroup


def test_jagged_knife_bandit_stats():
    assert JAGGED_KNIFE_BANDIT.name == "Jagged Knife Bandit"
    assert JAGGED_KNIFE_BANDIT.tier == 1
    assert JAGGED_KNIFE_BANDIT.difficulty == 12
    assert JAGGED_KNIFE_BANDIT.major_threshold == 8
    assert JAGGED_KNIFE_BANDIT.severe_threshold == 14
    assert JAGGED_KNIFE_BANDIT.hp_max == 5
    assert JAGGED_KNIFE_BANDIT.stress_max == 3
    assert JAGGED_KNIFE_BANDIT.attack_modifier == 1
    assert JAGGED_KNIFE_BANDIT.damage_dice == [DiceGroup(count=1, sides=8)]
    assert JAGGED_KNIFE_BANDIT.damage_modifier == 1


def test_jagged_knife_sniper_stats():
    assert JAGGED_KNIFE_SNIPER.name == "Jagged Knife Sniper"
    assert JAGGED_KNIFE_SNIPER.tier == 1
    assert JAGGED_KNIFE_SNIPER.difficulty == 13
    assert JAGGED_KNIFE_SNIPER.major_threshold == 4
    assert JAGGED_KNIFE_SNIPER.severe_threshold == 7
    assert JAGGED_KNIFE_SNIPER.hp_max == 3
    assert JAGGED_KNIFE_SNIPER.stress_max == 2
    assert JAGGED_KNIFE_SNIPER.attack_modifier == -1
    assert JAGGED_KNIFE_SNIPER.damage_dice == [DiceGroup(count=1, sides=10)]
    assert JAGGED_KNIFE_SNIPER.damage_modifier == 2


def test_definitions_start_unmarked():
    for definition in (JAGGED_KNIFE_BANDIT, JAGGED_KNIFE_SNIPER):
        assert definition.hp_marked == 0
        assert definition.stress_marked == 0
