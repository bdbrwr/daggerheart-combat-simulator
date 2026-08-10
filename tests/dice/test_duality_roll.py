import random

from dice import roll_duality, AdvantageState


def test_dice_within_default_bounds():
    for _ in range(50):
        result = roll_duality()
        assert 1 <= result.hope_die_result <= 12
        assert 1 <= result.fear_die_result <= 12


def test_custom_die_sizes_are_respected():
    for _ in range(50):
        result = roll_duality(hope_die=20, fear_die=4)
        assert 1 <= result.hope_die_result <= 20
        assert 1 <= result.fear_die_result <= 4


def test_advantage_die_absent_when_state_is_none():
    result = roll_duality(advantage_state=AdvantageState.NONE)
    assert result.advantage_die_result is None


def test_advantage_die_present_and_in_range_when_advantage():
    for _ in range(50):
        result = roll_duality(advantage_state=AdvantageState.ADVANTAGE)
        assert result.advantage_die_result is not None
        assert 1 <= result.advantage_die_result <= 6


def test_advantage_die_present_and_in_range_when_disadvantage():
    for _ in range(50):
        result = roll_duality(advantage_state=AdvantageState.DISADVANTAGE)
        assert result.advantage_die_result is not None
        assert 1 <= result.advantage_die_result <= 6


def test_no_help_dice_by_default():
    result = roll_duality()
    assert result.help_dice_results is None


def test_help_dice_count_matches_input():
    result = roll_duality(help_dice=[6, 6, 4])
    assert len(result.help_dice_results) == 3


def test_help_dice_respect_each_die_size():
    for _ in range(50):
        result = roll_duality(help_dice=[6, 20])
        low, high = result.help_dice_results
        assert 1 <= low <= 6
        assert 1 <= high <= 20


def test_modifier_and_difficulty_pass_through_unchanged():
    result = roll_duality(modifier=3, difficulty=15)
    assert result.modifier == 3
    assert result.difficulty == 15


def test_reproducible_under_a_fixed_seed():
    random.seed(123)
    first = roll_duality(help_dice=[6], advantage_state=AdvantageState.ADVANTAGE)
    random.seed(123)
    second = roll_duality(help_dice=[6], advantage_state=AdvantageState.ADVANTAGE)
    assert first == second
