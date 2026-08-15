"""Tests for the command line.

The CLI is deliberately thin, so these check the wiring rather than the numbers:
that a flag reaches the runner, that a mistyped name comes back as a message
instead of a traceback, and that a seeded play-by-play is the same fight twice.
Whether the statistics underneath are right is tests/test_simulation.py's job.

What the command line names is an *experiment* - one encounter file, holding the
variations run side by side. Tests that need more than one experiment point the
registry at a temporary directory rather than shipping extra example files.

The runs here are tiny on purpose - three fights is enough to prove the report
was printed, and the default ten thousand would make the suite slow for nothing.
"""

import json

import pytest

from encounters import registry
from simulation.cli import DEFAULT_SAVE_DIR, build_parser, main
from simulation.runner import DEFAULT_RUNS

ENCOUNTER = "Roadside Ambush"
ANOTHER = "Cliffside Chase"


def _variations_in(name: str) -> int:
    return len(registry.find_experiment(name).variations)


@pytest.fixture
def experiments(tmp_path, monkeypatch):
    """Point the registry at temporary encounter files, and put it back after."""

    def build(names: list[str], variations: int = 1) -> None:
        for name in names:
            path = tmp_path / f"{name.lower().replace(' ', '_')}.json"
            path.write_text(
                json.dumps(
                    {
                        "name": name,
                        "party": ["example_character.json"],
                        "variations": [
                            {
                                "name": f"Variation {number}",
                                "groups": [
                                    {"adversary": "Jagged Knife Bandit", "count": 1}
                                ],
                            }
                            for number in range(1, variations + 1)
                        ],
                    }
                )
            )
        monkeypatch.setattr(registry, "_DEFINITIONS_DIR", tmp_path)
        registry.refresh()

    yield build
    registry.refresh()


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
    assert arguments.no_coverage is False
    assert arguments.full_coverage is False


def test_the_short_flags_mean_what_the_long_ones_mean():
    short = build_parser().parse_args([ENCOUNTER, "-n", "5", "-s", "3", "-p"])
    spelled_out = build_parser().parse_args(
        [ENCOUNTER, "--runs", "5", "--seed", "3", "--play-by-play"]
    )

    assert short == spelled_out


def test_several_encounters_are_taken_as_several():
    arguments = build_parser().parse_args([ENCOUNTER, ANOTHER])

    assert arguments.encounters == [ENCOUNTER, ANOTHER]


def test_saving_to_a_directory_does_not_swallow_the_encounter_name():
    """--save-dir takes a value; --save is a flag, so this ordering stays unambiguous."""
    arguments = build_parser().parse_args(["--save", ENCOUNTER])

    assert arguments.encounters == [ENCOUNTER]
    assert arguments.save is True


# --- Listing -----------------------------------------------------------------


def test_listing_names_each_experiment_its_party_and_its_variations(capsys):
    assert main(["--list"]) == 0

    listed = capsys.readouterr().out
    assert ENCOUNTER in listed
    assert "Kael Ashgrove" in listed
    assert "As printed" in listed  # a variation, by name
    assert "Jagged Knife Bandit x3" in listed
    assert "hp_max=5" in listed  # the Sniper's override must be visible


# --- Running -----------------------------------------------------------------


def test_a_run_prints_a_full_report_for_every_variation(capsys):
    assert main([ENCOUNTER, "--runs", "3", "--seed", "1"]) == 0

    printed = capsys.readouterr().out
    assert printed.count("OUTCOMES") == _variations_in(ENCOUNTER)
    for heading in ("OUTCOMES", "FIGHT LENGTH", "COST TO THE PARTY", "FEAR"):
        assert heading in printed


def test_a_run_compares_the_variations_in_the_file(capsys):
    """One file is one question, so naming it is already a comparison."""
    main([ENCOUNTER, "--runs", "3", "--seed", "1"])

    printed = capsys.readouterr().out
    assert printed.count("COMPARISON") == 1
    assert ENCOUNTER in printed


def test_a_run_reports_what_is_missing_from_the_party(capsys):
    """Coverage is on by default - it's context the win rate needs."""
    main([ENCOUNTER, "--runs", "3", "--seed", "1"])

    printed = capsys.readouterr().out
    assert "COVERAGE" in printed
    assert "Kael Ashgrove" in printed
    assert "unimplemented" in printed


def test_coverage_is_not_repeated_for_every_variation_sharing_a_party(capsys):
    main([ENCOUNTER, "--runs", "3", "--seed", "1"])

    assert capsys.readouterr().out.count("COVERAGE") == 1


def test_no_coverage_drops_the_block_but_keeps_the_report(capsys):
    main([ENCOUNTER, "--runs", "3", "--seed", "1", "--no-coverage"])

    printed = capsys.readouterr().out
    assert "COVERAGE" not in printed
    assert "OUTCOMES" in printed


def test_full_coverage_adds_the_modelled_half_back(capsys):
    main([ENCOUNTER, "--runs", "3", "--seed", "1", "--full-coverage"])
    full = capsys.readouterr().out

    main([ENCOUNTER, "--runs", "3", "--seed", "1"])
    default = capsys.readouterr().out

    assert "modelled" in full
    assert "modelled" not in default
    assert len(full) > len(default)


def test_asking_for_no_coverage_and_all_of_it_is_refused():
    """Three points on one dial; two at once has no sensible answer."""
    with pytest.raises(SystemExit) as raised:
        main([ENCOUNTER, "--no-coverage", "--full-coverage"])

    assert raised.value.code == 2


def test_a_single_variation_gets_no_comparison_table(capsys, experiments):
    """Nothing to compare it against."""
    experiments([ENCOUNTER], variations=1)

    main([ENCOUNTER, "--runs", "3", "--seed", "1"])

    assert "COMPARISON" not in capsys.readouterr().out


def test_each_experiment_gets_its_own_table(capsys, experiments):
    """A row from one question mustn't sit beside a row from another."""
    experiments([ENCOUNTER, ANOTHER], variations=2)

    assert main([ENCOUNTER, ANOTHER, "--runs", "3", "--seed", "1"]) == 0

    printed = capsys.readouterr().out
    assert printed.count("OUTCOMES") == 4  # two experiments, two variations each
    assert printed.count("COMPARISON") == 2
    assert ENCOUNTER in printed
    assert ANOTHER in printed


def test_all_runs_every_defined_experiment(capsys, experiments):
    experiments([ENCOUNTER, ANOTHER], variations=1)

    assert main(["--all", "--runs", "3", "--seed", "1"]) == 0

    printed = capsys.readouterr().out
    assert ENCOUNTER in printed
    assert ANOTHER in printed


def test_naming_encounters_and_asking_for_all_is_refused():
    with pytest.raises(SystemExit) as raised:
        main(["--all", ENCOUNTER])

    assert raised.value.code == 2


def test_a_play_by_play_narrates_one_fight_per_variation(capsys):
    assert main([ENCOUNTER, "--play-by-play", "--seed", "1"]) == 0

    printed = capsys.readouterr().out
    assert printed.count("one fight (seed 1)") == _variations_in(ENCOUNTER)
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


def test_a_saved_file_is_named_for_the_experiment(tmp_path):
    main([ENCOUNTER, "--runs", "2", "--seed", "1", "--save-dir", str(tmp_path)])

    assert "roadside-ambush" in list(tmp_path.glob("*.txt"))[0].name


def test_saving_several_experiments_says_so_in_the_filename(tmp_path, experiments):
    experiments([ENCOUNTER, ANOTHER], variations=1)

    main([ENCOUNTER, ANOTHER, "--runs", "2", "--seed", "1", "--save-dir", str(tmp_path)])

    assert "and-1-more" in list(tmp_path.glob("*.txt"))[0].name


def test_a_missing_save_directory_is_created(tmp_path):
    destination = tmp_path / "not" / "yet" / "there"

    main([ENCOUNTER, "--runs", "2", "--seed", "1", "--save-dir", str(destination)])

    assert list(destination.glob("*.txt"))


def test_the_default_save_directory_is_the_gitignored_one():
    assert DEFAULT_SAVE_DIR == "runs"


# --- Mistakes ----------------------------------------------------------------


def test_a_mistyped_experiment_is_a_message_not_a_traceback(capsys):
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
