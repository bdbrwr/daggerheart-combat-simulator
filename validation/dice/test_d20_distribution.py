import random
import pytest

from dice import roll_d20, AdvantageState

N = 200_000


@pytest.fixture(autouse=True)
def seeded_random():
    random.seed(42)


def test_baseline_crit_rate_and_average():
    results = [roll_d20() for _ in range(N)]
    crit_pct = sum(r.is_critical for r in results) / N * 100
    avg_total = sum(r.total for r in results) / N
    assert crit_pct == pytest.approx(5.0, abs=0.2)
    assert avg_total == pytest.approx(10.5, abs=0.1)


def test_advantage_crit_rate_and_average():
    results = [roll_d20(advantage_state=AdvantageState.ADVANTAGE) for _ in range(N)]
    crit_pct = sum(r.is_critical for r in results) / N * 100
    avg_total = sum(r.total for r in results) / N
    assert crit_pct == pytest.approx(9.75, abs=0.3)
    assert avg_total == pytest.approx(13.825, abs=0.1)


def test_disadvantage_crit_rate_and_average():
    results = [roll_d20(advantage_state=AdvantageState.DISADVANTAGE) for _ in range(N)]
    crit_pct = sum(r.is_critical for r in results) / N * 100
    avg_total = sum(r.total for r in results) / N
    assert crit_pct == pytest.approx(0.25, abs=0.1)
    assert avg_total == pytest.approx(7.175, abs=0.1)
