import pytest

from dice import D20RollResult, AdvantageState


def make_result(**overrides) -> D20RollResult:
    defaults = dict(
        die_results=[10],
        modifier=0,
        advantage_state=AdvantageState.NONE,
        evasion=None,
    )
    defaults.update(overrides)
    return D20RollResult(**defaults)


# --- die_result resolution -------------------------------------------------

def test_die_result_is_the_single_roll_when_no_advantage():
    result = make_result(die_results=[14], advantage_state=AdvantageState.NONE)
    assert result.die_result == 14


def test_die_result_is_higher_roll_with_advantage():
    result = make_result(die_results=[6, 17], advantage_state=AdvantageState.ADVANTAGE)
    assert result.die_result == 17


def test_die_result_is_lower_roll_with_disadvantage():
    result = make_result(die_results=[6, 17], advantage_state=AdvantageState.DISADVANTAGE)
    assert result.die_result == 6


# --- is_critical -------------------------------------------------------

def test_natural_20_is_critical_no_advantage():
    result = make_result(die_results=[20], advantage_state=AdvantageState.NONE)
    assert result.is_critical is True


def test_advantage_crits_if_either_roll_is_20():
    result = make_result(die_results=[3, 20], advantage_state=AdvantageState.ADVANTAGE)
    assert result.is_critical is True


def test_disadvantage_only_crits_if_both_rolls_are_20():
    not_crit = make_result(die_results=[3, 20], advantage_state=AdvantageState.DISADVANTAGE)
    is_crit = make_result(die_results=[20, 20], advantage_state=AdvantageState.DISADVANTAGE)
    assert not_crit.is_critical is False
    assert is_crit.is_critical is True


def test_natural_1_is_not_critical():
    # No fumble mechanic assumed - a natural 1 is just a very low roll.
    result = make_result(die_results=[1])
    assert result.is_critical is False


# --- total -----------------------------------------------------------------

def test_total_adds_modifier_to_resolved_die():
    result = make_result(die_results=[6, 17], modifier=-3, advantage_state=AdvantageState.ADVANTAGE)
    assert result.total == 14 #also verifies negative modifier


# --- is_success ------------------------------------------------------------

def test_is_success_none_without_an_evasion():
    result = make_result(evasion=None)
    assert result.is_success is None


def test_is_success_true_when_total_meets_evasion():
    result = make_result(die_results=[14], modifier=2, evasion=16)
    assert result.total == 16
    assert result.is_success is True


def test_is_success_false_when_total_below_evasion():
    result = make_result(die_results=[5], modifier=0, evasion=16)
    assert result.is_success is False


def test_critical_always_succeeds_regardless_of_evasion():
    result = make_result(die_results=[20], evasion=999)
    assert result.is_success is True


# --- immutability ------------------------------------------------------------

def test_result_is_immutable():
    result = make_result()
    with pytest.raises(AttributeError):
        result.modifier = 99  # type: ignore[misc]
