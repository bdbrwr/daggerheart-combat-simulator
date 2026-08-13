"""Deterministic tests for the Monte Carlo layer.

The statistics are checked against hand-built records, where the right answer
is arithmetic rather than an expectation. The few tests that actually run
fights use encounters rigged so the outcome is certain - a 1 HP adversary that
deals no damage can only lose - so "win rate is exactly 1.0" is a fact about
the code, not a tolerance. Whether a *fair* fight comes out at a believable
rate is validation/'s problem.
"""

from pathlib import Path

from combat.common import FightOutcome
from encounters.encounter import Encounter, Group
from simulation.report import format_report
from simulation.runner import describe_group, run_simulation
from simulation.summary import (
    NEAR_DEATH_HP_REMAINING,
    Distribution,
    FightRecord,
    SimulationSummary,
)

EXAMPLE_CHARACTER_PATH = Path(__file__).parent.parent / "characters" / "example_character.json"

# Rigged so the outcome can't vary: crits bypass Difficulty and natural 20s
# bypass Evasion, so a side is made safe by removing its damage and unkillable
# by giving it more HP than the action cap can chew through.
HARMLESS = {"damage_dice": [], "damage_modifier": 0}
DOOMED = {"difficulty": 0, "hp_max": 1, **HARMLESS}
DEADLY = {"hp_max": 1000, "difficulty": 100, "attack_modifier": 100, "damage_modifier": 100}
STALEMATE = {"hp_max": 1000, "difficulty": 100, **HARMLESS}


def _encounter(adversary_overrides: dict, name: str = "Rigged") -> Encounter:
    return Encounter(
        name=name,
        party=[EXAMPLE_CHARACTER_PATH],
        groups=[Group("Jagged Knife Bandit", count=1, **adversary_overrides)],
    )


def _make_record(**overrides) -> FightRecord:
    defaults = dict(
        outcome=FightOutcome.PARTY_VICTORY,
        party_size=1,
        pc_actions=4,
        adversary_activations=3,
        gm_turns=3,
        party_hp_remaining=5,
        lowest_hp_remaining=5,
        unconscious_pcs=0,
        surviving_adversaries=0,
        fear_gained=2,
        fear_spent=1,
        fear_remaining=1,
        scars_gained=0,
    )
    defaults.update(overrides)
    return FightRecord(**defaults)


def _make_summary(records: list[FightRecord]) -> SimulationSummary:
    return SimulationSummary(
        encounter_name="Rigged",
        party=["Test PC"],
        opposition=["Jagged Knife Bandit x1"],
        seed=1,
        records=records,
    )


# --- Distribution ------------------------------------------------------------


def test_distribution_of_nothing_is_empty_not_an_error():
    empty = Distribution.of([])

    assert empty.count == 0
    assert empty.mean == 0.0
    assert empty.median == 0.0
    assert empty.summarize() == "no data"


def test_distribution_statistics_are_nearest_rank():
    """1..10, so every answer is a value that actually occurred."""
    spread = Distribution.of([10, 3, 5, 1, 8, 2, 9, 4, 7, 6])

    assert spread.count == 10
    assert spread.mean == 5.5
    assert spread.minimum == 1
    assert spread.maximum == 10
    assert spread.median == 6
    assert spread.percentile(0.1) == 2
    assert spread.percentile(0.9) == 10


def test_distribution_of_one_value_is_that_value():
    single = Distribution.of([3])

    assert single.mean == 3
    assert single.median == 3
    assert single.percentile(0.9) == 3


# --- Records -----------------------------------------------------------------


def test_rounds_are_actions_per_party_member():
    record = _make_record(party_size=2, pc_actions=9, adversary_activations=6)

    assert record.pc_rounds == 4.5
    assert record.gm_rounds == 3.0


def test_near_death_is_measured_on_whoever_came_closest():
    assert _make_record(lowest_hp_remaining=NEAR_DEATH_HP_REMAINING).near_death is True
    assert _make_record(lowest_hp_remaining=NEAR_DEATH_HP_REMAINING + 1).near_death is False
    assert _make_record(lowest_hp_remaining=0).near_death is True


def test_an_unresolved_fight_is_neither_won_nor_resolved():
    record = _make_record(outcome=FightOutcome.UNRESOLVED)

    assert record.resolved is False
    assert record.won is False


# --- Summary -----------------------------------------------------------------


def test_rates_are_shares_of_every_fight_run():
    summary = _make_summary(
        [
            _make_record(outcome=FightOutcome.PARTY_VICTORY),
            _make_record(outcome=FightOutcome.PARTY_DEFEAT),
            _make_record(outcome=FightOutcome.PARTY_DEFEAT),
            _make_record(outcome=FightOutcome.UNRESOLVED),
        ]
    )

    assert summary.runs == 4
    assert summary.win_rate == 0.25
    assert summary.defeat_rate == 0.5
    assert summary.unresolved_rate == 0.25


def test_unresolved_fights_are_left_out_of_distributions():
    """The cap isn't a fight length, so it mustn't drag the average toward it."""
    summary = _make_summary(
        [
            _make_record(pc_actions=4),
            _make_record(pc_actions=6),
            _make_record(outcome=FightOutcome.UNRESOLVED, pc_actions=500),
        ]
    )

    assert summary.distribution("pc_rounds").count == 2
    assert summary.distribution("pc_rounds").mean == 5.0


def test_near_death_rate_is_scoped_to_wins():
    """Everyone is down in a defeat, so counting those would restate the loss rate."""
    summary = _make_summary(
        [
            _make_record(outcome=FightOutcome.PARTY_VICTORY, lowest_hp_remaining=1),
            _make_record(outcome=FightOutcome.PARTY_VICTORY, lowest_hp_remaining=6),
            _make_record(outcome=FightOutcome.PARTY_DEFEAT, lowest_hp_remaining=0),
        ]
    )

    assert summary.near_death_rate == 0.5


def test_a_run_with_no_wins_reports_zero_rather_than_dividing_by_them():
    summary = _make_summary([_make_record(outcome=FightOutcome.PARTY_DEFEAT)])

    assert summary.near_death_rate == 0.0
    assert summary.win_rate == 0.0


def test_an_empty_run_has_no_rates():
    summary = _make_summary([])

    assert summary.runs == 0
    assert summary.win_rate == 0.0
    assert summary.distribution("pc_rounds").count == 0


# --- Running -----------------------------------------------------------------


def test_a_hopeless_adversary_loses_every_single_fight():
    summary = run_simulation(_encounter(DOOMED), runs=25, seed=1)

    assert summary.runs == 25
    assert summary.win_rate == 1.0
    assert summary.near_death_rate == 0.0  # it never lands a hit


def test_an_overwhelming_adversary_wins_every_single_fight():
    summary = run_simulation(_encounter(DEADLY), runs=25, seed=1)

    assert summary.win_rate == 0.0
    assert summary.defeat_rate == 1.0


def test_unresolvable_fights_are_counted_and_flagged():
    summary = run_simulation(_encounter(STALEMATE), runs=3, seed=1)

    assert summary.unresolved_rate == 1.0
    assert summary.distribution("pc_rounds").count == 0
    assert "hit the action cap" in format_report(summary)


def test_the_same_seed_reruns_the_same_experiment():
    encounter = Encounter(
        name="Fair Fight",
        party=[EXAMPLE_CHARACTER_PATH],
        groups=[Group("Jagged Knife Bandit", count=2)],
    )

    first = run_simulation(encounter, runs=30, seed=5)
    second = run_simulation(encounter, runs=30, seed=5)

    assert first.records == second.records


def test_different_seeds_are_different_experiments():
    encounter = Encounter(
        name="Fair Fight",
        party=[EXAMPLE_CHARACTER_PATH],
        groups=[Group("Jagged Knife Bandit", count=2)],
    )

    assert run_simulation(encounter, runs=30, seed=5).records != run_simulation(
        encounter, runs=30, seed=6
    ).records


def test_a_run_records_what_it_was_a_run_of():
    summary = run_simulation(_encounter(DOOMED, name="Named Fight"), runs=2, seed=1)

    assert summary.encounter_name == "Named Fight"
    assert summary.party == ["Kael Ashgrove"]
    assert summary.seed == 1


def test_tuning_is_named_in_the_opposition_line():
    """A run against an overridden stat block must not look like the printed one."""
    plain = Group("Jagged Knife Bandit", count=3)
    tuned = Group("Jagged Knife Sniper", count=1, hp_max=5)

    assert describe_group(plain) == "Jagged Knife Bandit x3"
    assert "hp_max=5" in describe_group(tuned)


# --- Report ------------------------------------------------------------------


def test_the_report_covers_every_section():
    summary = run_simulation(_encounter(DOOMED), runs=5, seed=1)
    report = format_report(summary)

    for heading in ("OUTCOMES", "FIGHT LENGTH", "COST TO THE PARTY", "FEAR"):
        assert heading in report
    assert "Rigged" in report
    assert "Kael Ashgrove" in report


def test_the_report_survives_a_run_the_party_never_won():
    report = format_report(run_simulation(_encounter(DEADLY), runs=5, seed=1))

    assert "no wins to measure" in report


def test_a_clean_run_carries_no_warning():
    report = format_report(run_simulation(_encounter(DOOMED), runs=5, seed=1))

    assert "hit the action cap" not in report
