import random

from dice import roll_damage, DiceGroup


def test_die_count_matches_the_group():
    result = roll_damage([DiceGroup(count=3, sides=6)])
    assert len(result.die_results[0]) == 3


def test_each_group_rolled_independently():
    result = roll_damage([DiceGroup(2, 8), DiceGroup(1, 4)])
    assert len(result.die_results) == 2
    assert len(result.die_results[0]) == 2
    assert len(result.die_results[1]) == 1


def test_zero_count_group_rolls_nothing():
    result = roll_damage([DiceGroup(0, 6)])
    assert result.die_results == [[]]


def test_all_dice_within_bounds_for_their_own_group():
    for _ in range(50):
        result = roll_damage([DiceGroup(2, 8), DiceGroup(3, 4)])
        low_group, high_group = result.die_results
        assert all(1 <= d <= 8 for d in low_group)
        assert all(1 <= d <= 4 for d in high_group)


def test_modifier_and_is_critical_pass_through_unchanged():
    result = roll_damage([DiceGroup(1, 6)], modifier=4, is_critical=True)
    assert result.modifier == 4
    assert result.is_critical is True


def test_reproducible_under_a_fixed_seed():
    random.seed(42)
    first = roll_damage([DiceGroup(2, 8), DiceGroup(1, 4)], modifier=3)
    random.seed(42)
    second = roll_damage([DiceGroup(2, 8), DiceGroup(1, 4)], modifier=3)
    assert first == second
