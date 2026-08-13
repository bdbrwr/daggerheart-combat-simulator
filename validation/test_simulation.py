"""Statistical checks on the Monte Carlo layer itself.

Everything here samples fights and checks an aggregate against a tolerance, so
it belongs out of `tests/` for the reasons validation/README.md gives.

These don't assert that any particular encounter is balanced - that's a design
question with no correct answer, and it's the thing the tool exists to let a
person judge. What they check is that the machinery producing those numbers is
sound: that a win rate is a stable property of an encounter rather than an
artefact of the seed, that the sample size does what sample size is supposed
to do, and that a fight the party wins costs them less than one they lose.
"""

from pathlib import Path

from encounters.encounter import Encounter, Group
from simulation.runner import run_simulation

EXAMPLE_CHARACTER_PATH = Path(__file__).parent.parent / "characters" / "example_character.json"

RUNS = 20_000


def _fair_fight(count: int = 1) -> Encounter:
    """One tier 1 PC against `count` Jagged Knife Bandits, as printed."""
    return Encounter(
        name=f"Bandits x{count}",
        party=[EXAMPLE_CHARACTER_PATH],
        groups=[Group("Jagged Knife Bandit", count=count)],
    )


def test_win_rate_is_a_property_of_the_encounter_not_the_seed():
    """Two independent runs of the same fight should agree closely.

    This is the assumption every balance decision rests on: that a win rate
    read off one run would have been the same had the run been seeded
    differently. If this drifts, no amount of tuning means anything.
    """
    first = run_simulation(_fair_fight(), runs=RUNS, seed=101)
    second = run_simulation(_fair_fight(), runs=RUNS, seed=202)

    assert abs(first.win_rate - second.win_rate) < 0.02


def test_a_bigger_sample_settles_down():
    """A small run scatters around the large-run answer; a large one doesn't."""
    reference = run_simulation(_fair_fight(), runs=RUNS, seed=7).win_rate

    small = [run_simulation(_fair_fight(), runs=100, seed=seed).win_rate for seed in range(8)]
    large = [run_simulation(_fair_fight(), runs=4_000, seed=seed).win_rate for seed in range(8)]

    small_spread = max(abs(rate - reference) for rate in small)
    large_spread = max(abs(rate - reference) for rate in large)

    assert large_spread < small_spread


def test_more_adversaries_make_a_fight_harder():
    """Monotonicity - the cheapest sanity check there is on a combat loop.

    If adding bandits didn't lower the win rate, something in the spotlight or
    activation rules would be dropping adversary turns on the floor.
    """
    alone = run_simulation(_fair_fight(1), runs=RUNS, seed=11).win_rate
    outnumbered = run_simulation(_fair_fight(3), runs=RUNS, seed=11).win_rate

    assert outnumbered < alone


def test_fear_is_only_spent_when_there_is_something_to_spend_it_on():
    """The GM's pool should engage exactly when a second adversary exists.

    Against a lone adversary there's nothing to buy - the free activation is
    the only one available - so Fear accumulates untouched. Add more and the
    GM starts paying for extra activations every turn. Fear spending stuck at
    zero in a crowded fight would mean the activation rules never fire.
    """
    alone = run_simulation(_fair_fight(1), runs=RUNS, seed=23)
    crowd = run_simulation(_fair_fight(3), runs=RUNS, seed=23)

    assert alone.distribution("fear_spent").maximum == 0
    assert crowd.distribution("fear_spent").mean > 0


def test_both_outcomes_occur_in_a_matchup_that_should_be_close():
    """A fight neither side always wins is the only kind worth tuning."""
    summary = run_simulation(_fair_fight(2), runs=RUNS, seed=13)

    assert summary.victories and summary.defeats


def test_no_fight_between_plausible_combatants_goes_unresolved():
    """The action cap should only ever catch genuinely broken matchups."""
    summary = run_simulation(_fair_fight(2), runs=RUNS, seed=17)

    assert summary.unresolved_rate == 0.0
