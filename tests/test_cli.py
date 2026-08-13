"""Tests for the command line.

The CLI is deliberately thin, so these check the wiring rather than the
numbers: that a flag reaches the runner, that a mistyped encounter name comes
back as a message instead of a traceback, and that a seeded play-by-play is the
same fight twice. Whether the statistics underneath are right is
tests/test_simulation.py's job.

The runs here are tiny on purpose - three fights is enough to prove the report
was printed, and the default ten thousand would make the suite slow for nothing.
"""

import pytest

from simulation.cli import build_parser, main
from simulation.runner import DEFAULT_RUNS

ENCOUNTER = "Roadside Ambush"


# --- Arguments ---------------------------------------------------------------


def test_the_defaults_are_a_full_unseeded_statistical_run():
    arguments = build_parser().parse_args([ENCOUNTER])

    assert arguments.encounter == ENCOUNTER
    assert arguments.runs == DEFAULT_RUNS
    assert arguments.seed is None
    assert arguments.play_by_play is False
    assert arguments.list is False


def test_the_short_flags_mean_what_the_long_ones_mean():
    short = build_parser().parse_args([ENCOUNTER, "-n", "5", "-s", "3", "-p"])
    spelled_out = build_parser().parse_args(
        [ENCOUNTER, "--runs", "5", "--seed", "3", "--play-by-play"]
    )

    assert short == spelled_out


# --- Listing -----------------------------------------------------------------


def test_listing_names_each_encounter_its_party_and_its_tuning(capsys):
    assert main(["--list"]) == 0

    listed = capsys.readouterr().out
    assert ENCOUNTER in listed
    assert "Kael Ashgrove" in listed
    assert "Jagged Knife Bandit x3" in listed
    assert "hp_max=5" in listed  # the Sniper's override must be visible


# --- Running -----------------------------------------------------------------


def test_a_run_prints_the_whole_report(capsys):
    assert main([ENCOUNTER, "--runs", "3", "--seed", "1"]) == 0

    printed = capsys.readouterr().out
    assert ENCOUNTER in printed
    for heading in ("OUTCOMES", "FIGHT LENGTH", "COST TO THE PARTY", "FEAR"):
        assert heading in printed


def test_a_play_by_play_narrates_a_single_fight(capsys):
    assert main([ENCOUNTER, "--play-by-play", "--seed", "1"]) == 0

    printed = capsys.readouterr().out
    assert "one fight (seed 1)" in printed
    assert "Fight ends:" in printed


def test_the_same_seed_narrates_the_very_same_fight(capsys):
    main([ENCOUNTER, "-p", "-s", "4"])
    first = capsys.readouterr().out

    main([ENCOUNTER, "-p", "-s", "4"])

    assert capsys.readouterr().out == first


# --- Mistakes ----------------------------------------------------------------


def test_a_mistyped_encounter_is_a_message_not_a_traceback(capsys):
    with pytest.raises(SystemExit) as raised:
        main(["Roadside Ambash"])

    assert raised.value.code == 2
    reported = capsys.readouterr().err
    assert "Did you mean" in reported
    assert ENCOUNTER in reported


def test_a_run_of_no_fights_is_refused():
    with pytest.raises(SystemExit) as raised:
        main([ENCOUNTER, "--runs", "0"])

    assert raised.value.code == 2


def test_naming_no_encounter_at_all_prints_the_help(capsys):
    assert main([]) == 2

    assert "usage" in capsys.readouterr().out
