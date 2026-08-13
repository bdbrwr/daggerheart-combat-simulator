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

from simulation.cli import DEFAULT_SAVE_DIR, build_parser, main
from simulation.runner import DEFAULT_RUNS

ENCOUNTER = "Roadside Ambush"
VARIATION = "Roadside Ambush (Softened)"


# --- Arguments ---------------------------------------------------------------


def test_the_defaults_are_a_full_unseeded_statistical_run():
    arguments = build_parser().parse_args([ENCOUNTER])

    assert arguments.encounters == [ENCOUNTER]
    assert arguments.runs == DEFAULT_RUNS
    assert arguments.seed is None
    assert arguments.play_by_play is False
    assert arguments.list is False
    assert arguments.all is False
    assert arguments.save is False
    assert arguments.save_dir is None


def test_the_short_flags_mean_what_the_long_ones_mean():
    short = build_parser().parse_args([ENCOUNTER, "-n", "5", "-s", "3", "-p"])
    spelled_out = build_parser().parse_args(
        [ENCOUNTER, "--runs", "5", "--seed", "3", "--play-by-play"]
    )

    assert short == spelled_out


def test_several_encounters_are_taken_as_several():
    arguments = build_parser().parse_args([ENCOUNTER, VARIATION])

    assert arguments.encounters == [ENCOUNTER, VARIATION]


def test_saving_to_a_directory_does_not_swallow_the_encounter_name():
    """--save-dir takes a value; --save is a flag, so this ordering stays unambiguous."""
    arguments = build_parser().parse_args(["--save", ENCOUNTER])

    assert arguments.encounters == [ENCOUNTER]
    assert arguments.save is True


# --- Listing -----------------------------------------------------------------


def test_listing_names_each_encounter_its_party_and_its_tuning(capsys):
    assert main(["--list"]) == 0

    listed = capsys.readouterr().out
    assert ENCOUNTER in listed
    assert VARIATION in listed
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


def test_a_run_reports_how_much_of_the_party_is_modelled(capsys):
    """Coverage isn't behind a flag - it's context the win rate needs."""
    main([ENCOUNTER, "--runs", "3", "--seed", "1"])

    printed = capsys.readouterr().out
    assert "COVERAGE" in printed
    assert "Kael Ashgrove" in printed
    assert "unimplemented" in printed


def test_one_encounter_alone_gets_no_comparison_table(capsys):
    main([ENCOUNTER, "--runs", "3", "--seed", "1"])

    assert "COMPARISON" not in capsys.readouterr().out


def test_several_encounters_are_reported_then_compared(capsys):
    assert main([ENCOUNTER, VARIATION, "--runs", "3", "--seed", "1"]) == 0

    printed = capsys.readouterr().out
    assert printed.count("OUTCOMES") == 2  # a full report for each
    assert "COMPARISON" in printed
    assert VARIATION in printed


def test_all_runs_every_defined_encounter(capsys):
    assert main(["--all", "--runs", "3", "--seed", "1"]) == 0

    printed = capsys.readouterr().out
    assert ENCOUNTER in printed
    assert VARIATION in printed


def test_naming_encounters_and_asking_for_all_is_refused():
    with pytest.raises(SystemExit) as raised:
        main(["--all", ENCOUNTER])

    assert raised.value.code == 2


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


# --- Saving ------------------------------------------------------------------


def test_saving_writes_exactly_what_was_printed(capsys, tmp_path):
    assert main([ENCOUNTER, "--runs", "3", "--seed", "1", "--save-dir", str(tmp_path)]) == 0

    printed = capsys.readouterr().out
    saved = list(tmp_path.glob("*.txt"))
    assert len(saved) == 1
    # The report, minus the trailing "Saved to ..." line the file can't contain.
    assert saved[0].read_text(encoding="utf-8").strip() in printed
    assert "OUTCOMES" in saved[0].read_text(encoding="utf-8")


def test_a_saved_file_is_named_for_the_encounter(tmp_path):
    main([ENCOUNTER, "--runs", "2", "--seed", "1", "--save-dir", str(tmp_path)])

    assert "roadside-ambush" in list(tmp_path.glob("*.txt"))[0].name


def test_saving_several_encounters_says_so_in_the_filename(tmp_path):
    main([ENCOUNTER, VARIATION, "--runs", "2", "--seed", "1", "--save-dir", str(tmp_path)])

    assert "and-1-more" in list(tmp_path.glob("*.txt"))[0].name


def test_a_missing_save_directory_is_created(tmp_path):
    destination = tmp_path / "not" / "yet" / "there"

    main([ENCOUNTER, "--runs", "2", "--seed", "1", "--save-dir", str(destination)])

    assert list(destination.glob("*.txt"))


def test_the_default_save_directory_is_the_gitignored_one():
    assert DEFAULT_SAVE_DIR == "runs"


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
