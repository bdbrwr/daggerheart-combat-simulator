import random

from dice import roll_d20, AdvantageState


def test_one_die_when_no_advantage():
    result = roll_d20(advantage_state=AdvantageState.NONE)
    assert len(result.die_results) == 1


def test_two_dice_when_advantage():
    result = roll_d20(advantage_state=AdvantageState.ADVANTAGE)
    assert len(result.die_results) == 2


def test_two_dice_when_disadvantage():
    result = roll_d20(advantage_state=AdvantageState.DISADVANTAGE)
    assert len(result.die_results) == 2


def test_all_dice_within_bounds():
    for _ in range(50):
        for state in (AdvantageState.NONE, AdvantageState.ADVANTAGE, AdvantageState.DISADVANTAGE):
            result = roll_d20(advantage_state=state)
            assert all(1 <= d <= 20 for d in result.die_results)


def test_modifier_and_evasion_pass_through_unchanged():
    result = roll_d20(modifier=4, evasion=15)
    assert result.modifier == 4
    assert result.evasion == 15


def test_reproducible_under_a_fixed_seed():
    random.seed(77)
    first = roll_d20(advantage_state=AdvantageState.ADVANTAGE)
    random.seed(77)
    second = roll_d20(advantage_state=AdvantageState.ADVANTAGE)
    assert first == second
