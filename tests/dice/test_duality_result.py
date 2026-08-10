import pytest

from dice import DualityRollResult, DualityOutcome, AdvantageState


def make_result(**overrides) -> DualityRollResult:
    defaults = dict(
        hope_die_result=5,
        fear_die_result=3,
        modifier=0,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=[],
        difficulty=None,
    )
    defaults.update(overrides)
    return DualityRollResult(**defaults)


# --- outcome -----------------------------------------------------------

def test_hope_die_greater_gives_hope_outcome():
    result = make_result(hope_die_result=8, fear_die_result=3)
    assert result.outcome is DualityOutcome.HOPE


def test_fear_die_greater_gives_fear_outcome():
    result = make_result(hope_die_result=3, fear_die_result=8)
    assert result.outcome is DualityOutcome.FEAR


def test_equal_dice_gives_critical_outcome():
    result = make_result(hope_die_result=7, fear_die_result=7)
    assert result.outcome is DualityOutcome.CRIT


def test_is_critical_true_only_when_dice_equal():
    assert make_result(hope_die_result=6, fear_die_result=6).is_critical is True
    assert make_result(hope_die_result=6, fear_die_result=5).is_critical is False


# --- advantage_total -----------------------------------------------------

def test_advantage_total_zero_when_state_is_none():
    result = make_result(advantage_state=AdvantageState.NONE, advantage_die_result=None)
    assert result.advantage_total == 0


def test_advantage_total_adds_die_when_advantage():
    result = make_result(advantage_state=AdvantageState.ADVANTAGE, advantage_die_result=5)
    assert result.advantage_total == 5


def test_advantage_total_subtracts_die_when_disadvantage():
    result = make_result(advantage_state=AdvantageState.DISADVANTAGE, advantage_die_result=5)
    assert result.advantage_total == -5


# --- help_total ----------------------------------------------------------

def test_help_total_zero_when_no_helpers():
    result = make_result(help_dice_results=[])
    assert result.help_total == 0


def test_help_total_uses_best_die_not_sum():
    result = make_result(help_dice_results=[2, 6, 4])
    assert result.help_total == 6  # NOT 12 - only the best helper counts


# --- total -----------------------------------------------------------------

def test_total_combines_all_components():
    result = make_result(
        hope_die_result=5, fear_die_result=3, modifier=2,
        advantage_state=AdvantageState.ADVANTAGE, advantage_die_result=4,
        help_dice_results=[1, 5, 2],
    )
    # 5 + 3 + 2 (mod) + 4 (advantage) + 5 (best of the help dice) = 19
    assert result.total == 19


# --- is_success ------------------------------------------------------------

def test_is_success_is_none_without_a_difficulty():
    result = make_result(difficulty=None)
    assert result.is_success is None


def test_is_success_true_when_total_meets_difficulty():
    result = make_result(hope_die_result=8, fear_die_result=5, difficulty=13)
    assert result.total == 13
    assert result.is_success is True


def test_is_success_false_when_total_below_difficulty():
    result = make_result(hope_die_result=2, fear_die_result=1, difficulty=13)
    assert result.is_success is False


def test_critical_always_succeeds_regardless_of_difficulty():
    result = make_result(hope_die_result=6, fear_die_result=6, difficulty=999)
    assert result.is_success is True


# --- immutability ------------------------------------------------------------

def test_result_is_immutable():
    result = make_result()
    with pytest.raises(AttributeError):
        result.modifier = 99  # type: ignore[misc]
