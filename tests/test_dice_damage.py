"""Damage roll resolution, with no dice actually rolled.

Every case here builds a DamageRollResult from fixed die results, so what's
under test is the arithmetic - dropping, the critical bonus, and the total -
rather than the random number generator. Rolling is covered where it belongs, in
the weapon tests, by asserting on the dice pool a weapon asks for.
"""

from dice.damage import DamageRollResult, DiceGroup


def test_drop_lowest_discards_the_smallest_die_of_the_whole_roll():
    """"The lowest result" is across the roll, not within one dice group."""
    result = DamageRollResult(
        dice_groups=[DiceGroup(count=2, sides=8), DiceGroup(count=1, sides=4)],
        die_results=[[7, 5], [2]],
        modifier=0,
        drop_lowest=1,
    )

    assert result.dropped == [2]
    assert result.rolled_total == 12
    assert result.total == 12


def test_dropped_die_still_counts_when_it_is_not_the_lowest():
    result = DamageRollResult(
        dice_groups=[DiceGroup(count=3, sides=10)],
        die_results=[[9, 1, 6]],
        modifier=3,
        drop_lowest=1,
    )

    assert result.dropped == [1]
    assert result.rolled_total == 15
    assert result.total == 18


def test_drop_lowest_zero_keeps_every_die():
    result = DamageRollResult(
        dice_groups=[DiceGroup(count=2, sides=10)],
        die_results=[[4, 1]],
        modifier=0,
    )

    assert result.dropped == []
    assert result.rolled_total == 5


def test_a_die_a_feature_added_is_never_the_one_discarded():
    """Massive and Powerful discard one of the *weapon's* dice.

    Here the d10 rolled a 1 and is the lowest die in the roll, but it isn't the
    weapon's, so the discard takes the lowest d6 instead and the d10 still
    counts toward the total.
    """
    result = DamageRollResult(
        dice_groups=[
            DiceGroup(count=2, sides=6),
            DiceGroup(count=1, sides=10, discardable=False),
        ],
        die_results=[[5, 4], [1]],
        modifier=0,
        drop_lowest=1,
    )

    assert result.dropped == [4]
    assert result.rolled_total == 6


def test_a_protected_die_counts_in_full_toward_the_critical_bonus():
    """Nothing is taken off a die the discard couldn't have reached."""
    result = DamageRollResult(
        dice_groups=[
            DiceGroup(count=2, sides=6),
            DiceGroup(count=1, sides=10, discardable=False),
        ],
        die_results=[[5, 4], [1]],
        modifier=0,
        is_critical=True,
        drop_lowest=1,
    )

    assert result.critical_bonus == 16  # one kept d6, plus the whole d10


def test_critical_bonus_excludes_the_discarded_die():
    """A crit adds the maximum of the dice that were *kept*.

    Three d10s with the lowest discarded is a kept pool of two, so the bonus is
    20 rather than 30 - see the interpretation in SIMULATION-RULES.md.
    """
    result = DamageRollResult(
        dice_groups=[DiceGroup(count=3, sides=10)],
        die_results=[[9, 1, 6]],
        modifier=3,
        is_critical=True,
        drop_lowest=1,
    )

    assert result.critical_bonus == 20
    assert result.total == 15 + 3 + 20


def test_critical_bonus_drops_the_smallest_die_size_across_groups():
    """With mixed dice the discard is assumed to come off the smallest die."""
    result = DamageRollResult(
        dice_groups=[DiceGroup(count=2, sides=10), DiceGroup(count=1, sides=4)],
        die_results=[[3, 3], [4]],
        modifier=0,
        is_critical=True,
        drop_lowest=1,
    )

    assert result.critical_bonus == 20


def test_a_group_of_no_dice_rolls_nothing_but_is_still_recorded():
    result = DamageRollResult(
        dice_groups=[DiceGroup(count=0, sides=6)],
        die_results=[[]],
        modifier=2,
    )

    assert result.rolled_total == 0
    assert result.total == 2
