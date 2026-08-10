import random
from collections import Counter

import pytest

from dice import roll_duality, DualityOutcome, AdvantageState

N = 200_000


@pytest.fixture(autouse=True)
def seeded_random():
    random.seed(42)


def test_outcome_distribution():
    results = [roll_duality() for _ in range(N)]
    counts = Counter(r.outcome for r in results)

    crit_pct = counts[DualityOutcome.CRIT] / N * 100
    hope_pct = counts[DualityOutcome.HOPE] / N * 100
    fear_pct = counts[DualityOutcome.FEAR] / N * 100

    assert crit_pct == pytest.approx(100 / 12, abs=0.5)
    assert hope_pct == pytest.approx(66 / 144 * 100, abs=0.5)
    assert fear_pct == pytest.approx(66 / 144 * 100, abs=0.5)
    assert crit_pct + hope_pct + fear_pct == pytest.approx(100.0, abs=0.01)


def test_low_difficulty_almost_always_succeeds():
    results = [roll_duality(difficulty=2) for _ in range(N)]
    success_pct = sum(r.is_success for r in results) / N * 100
    assert success_pct == pytest.approx(100.0, abs=0.1)


def test_high_difficulty_only_crits_succeed():
    results = [roll_duality(difficulty=100) for _ in range(N)]
    success_pct = sum(r.is_success for r in results) / N * 100
    assert success_pct == pytest.approx(100 / 12, abs=0.5)


def test_advantage_shifts_average_total_up():
    baseline = [roll_duality().total for _ in range(N)]
    with_adv = [
        roll_duality(advantage_state=AdvantageState.ADVANTAGE).total
        for _ in range(N)
    ]
    assert sum(baseline) / N == pytest.approx(13.0, abs=0.1)
    assert sum(with_adv) / N == pytest.approx(13.0 + 3.5, abs=0.1)


def test_disadvantage_shifts_average_total_down():
    with_dis = [
        roll_duality(advantage_state=AdvantageState.DISADVANTAGE).total
        for _ in range(N)
    ]
    assert sum(with_dis) / N == pytest.approx(13.0 - 3.5, abs=0.1)


def test_help_uses_best_die_not_sum():
    # E[max(3d6)] = 4.9583 analytically (via P(max<=k)=(k/6)^3).
    # If this were sum-based instead, the average would land near 13+10.5.
    results = [roll_duality(help_dice=[6, 6, 6]).total for _ in range(N)]
    assert sum(results) / N == pytest.approx(13.0 + 4.9583, abs=0.1)


def test_help_does_not_cancel_disadvantage():
    results = [
        roll_duality(
            advantage_state=AdvantageState.DISADVANTAGE, help_dice=[6]
        ).total
        for _ in range(N)
    ]
    # -3.5 (disadvantage) + 3.5 (avg of a single d6) nets back to baseline.
    assert sum(results) / N == pytest.approx(13.0, abs=0.1)


def test_custom_die_sizes():
    results = [
        roll_duality(hope_die=20, fear_die=20).total for _ in range(N)
    ]
    assert sum(results) / N == pytest.approx(21.0, abs=0.1)
