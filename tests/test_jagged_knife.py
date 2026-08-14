"""The stat blocks as printed - these should only ever change if the book does.

Per-encounter tuning happens in encounters/, so a failure here means either a
transcription error in adversaries/srd.json or that someone edited the definition
where they meant to add an override.

Looked up rather than imported: a stat block is a catalogue entry now, not a
module-level literal. The lookup happens inside each test because another file's
`refresh()` can drop the registry's cache, and holding an object across that
would make these pass or fail on test order.
"""

from adversaries.registry import find_adversary
from dice.damage import DiceGroup


def test_jagged_knife_bandit_stats():
    bandit = find_adversary("Jagged Knife Bandit")

    assert bandit.name == "Jagged Knife Bandit"
    assert bandit.tier == 1
    assert bandit.difficulty == 12
    assert bandit.major_threshold == 8
    assert bandit.severe_threshold == 14
    assert bandit.hp_max == 5
    assert bandit.stress_max == 3
    assert bandit.attack_modifier == 1
    assert bandit.damage_dice == [DiceGroup(count=1, sides=8)]
    assert bandit.damage_modifier == 1


def test_jagged_knife_sniper_stats():
    sniper = find_adversary("Jagged Knife Sniper")

    assert sniper.name == "Jagged Knife Sniper"
    assert sniper.tier == 1
    assert sniper.difficulty == 13
    assert sniper.major_threshold == 4
    assert sniper.severe_threshold == 7
    assert sniper.hp_max == 3
    assert sniper.stress_max == 2
    assert sniper.attack_modifier == -1
    assert sniper.damage_dice == [DiceGroup(count=1, sides=10)]
    assert sniper.damage_modifier == 2


def test_the_printed_passives_are_named_rather_than_left_in_a_comment():
    """These aren't modelled, and naming them is what makes that visible.

    Before the catalogue existed they sat in a Python comment, which meant a
    reader of a win rate had no way to know they were missing. Named here, they
    report as *unimplemented* in the coverage block under every run.
    """
    assert find_adversary("Jagged Knife Bandit").features == ["Climber", "From Above"]
    assert find_adversary("Jagged Knife Sniper").features == ["Unseen Strike"]


def test_definitions_carry_their_publication():
    for name in ("Jagged Knife Bandit", "Jagged Knife Sniper"):
        assert find_adversary(name).publication == "Daggerheart SRD"


def test_definitions_start_unmarked():
    for name in ("Jagged Knife Bandit", "Jagged Knife Sniper"):
        definition = find_adversary(name)
        assert definition.hp_marked == 0
        assert definition.stress_marked == 0
