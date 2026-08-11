import pytest

from dice import DamageRollResult, DiceGroup


def make_result(**overrides) -> DamageRollResult:
    defaults = dict(
        dice_groups=[DiceGroup(count=2, sides=8)],
        die_results=[[5, 3]],
        modifier=0,
        is_critical=False,
    )
    defaults.update(overrides)
    return DamageRollResult(**defaults)


# --- rolled_total ------------------------------------------------------

def test_rolled_total_sums_a_single_group():
    result = make_result(dice_groups=[DiceGroup(2, 8)], die_results=[[5, 3]])
    assert result.rolled_total == 8


def test_rolled_total_sums_across_multiple_groups():
    result = make_result(
        dice_groups=[DiceGroup(2, 8), DiceGroup(1, 4)],
        die_results=[[5, 3], [2]],
    )
    assert result.rolled_total == 10


def test_rolled_total_zero_for_an_empty_group():
    result = make_result(dice_groups=[DiceGroup(0, 8)], die_results=[[]])
    assert result.rolled_total == 0


# --- critical_bonus ------------------------------------------------------

def test_critical_bonus_zero_when_not_critical():
    result = make_result(is_critical=False)
    assert result.critical_bonus == 0


def test_critical_bonus_is_max_possible_dice_value_not_a_doubled_total():
    # SRD: crit adds max possible dice result on top, it does not double the total.
    result = make_result(
        dice_groups=[DiceGroup(2, 8)], die_results=[[1, 1]], is_critical=True
    )
    assert result.critical_bonus == 16  # 2 * 8, regardless of what was actually rolled


def test_critical_bonus_sums_max_across_multiple_groups():
    result = make_result(
        dice_groups=[DiceGroup(2, 8), DiceGroup(1, 4)],
        die_results=[[1, 1], [1]],
        is_critical=True,
    )
    assert result.critical_bonus == 20  # (2*8) + (1*4)


# --- total -----------------------------------------------------------------

def test_total_adds_modifier_to_rolled_total():
    result = make_result(dice_groups=[DiceGroup(2, 8)], die_results=[[5, 3]], modifier=3)
    assert result.total == 11


def test_total_combines_rolled_modifier_and_critical_bonus():
    result = make_result(
        dice_groups=[DiceGroup(2, 8)], die_results=[[5, 3]], modifier=3, is_critical=True
    )
    # rolled(8) + mod(3) + crit_bonus(16) = 27
    assert result.total == 27


def test_critical_does_not_double_the_modifier():
    with_crit = make_result(modifier=10, is_critical=True)
    without_crit = make_result(modifier=10, is_critical=False)
    assert with_crit.total - without_crit.total == with_crit.critical_bonus


# --- immutability ------------------------------------------------------------

def test_result_is_immutable():
    result = make_result()
    with pytest.raises(AttributeError):
        result.modifier = 99  # type: ignore[misc]
