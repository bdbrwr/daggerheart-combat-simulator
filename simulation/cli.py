"""The command line - how a run actually gets started.

Everything under this module already worked; what was missing was a way to ask
it a question without opening a REPL. That's all this is: name one or more
encounters, say how many times to fight each, and get simulation/report.py's
block of text.

    python -m simulation --list
    python -m simulation "Roadside Ambush" --runs 10000 --seed 7
    python -m simulation "Roadside Ambush" "Roadside Ambush (Softened)" --save
    python -m simulation --all --runs 2000 --seed 7
    python -m simulation "Roadside Ambush" --play-by-play --seed 7

Naming more than one encounter is the tuning workflow. Each is run in full and
reported in full, then a comparison table underneath puts the headline numbers
in rows so a variation can be judged against what it varies from. Crucially a
single `--seed` seeds *every* encounter in the command, so each variation is
fought against the same sequence of dice and a difference between two rows is a
difference between the stat blocks rather than luck.

Encounters are named, not built here. A variation worth running is worth
committing as a definition in encounters/, where its overrides sit next to the
stat block they tune and a run from last week can be repeated exactly.

`--play-by-play` is the other half of the job: a single seeded fight with the
loop narrating itself. A win rate that looks wrong says a number is off but not
which rule produced it, so tuning tends to go - run ten thousand, notice
something odd, run one and read it.
"""

import argparse
import random
import re
from datetime import datetime
from pathlib import Path

from combat.fight import run_fight
from encounters.registry import all_encounters, find_encounter
from simulation.coverage import format_coverage
from simulation.report import format_comparison, format_report
from simulation.runner import DEFAULT_RUNS, describe_group, run_simulation

# Saved runs land here by default. Gitignored: these are experiment output, and
# the definition that produced one is already in encounters/ under version
# control, so the file is a record rather than a source of truth.
DEFAULT_SAVE_DIR = "runs"

USAGE_EXAMPLES = """\
examples:
  python -m simulation --list
  python -m simulation "Roadside Ambush"
  python -m simulation "Roadside Ambush" --runs 1000 --seed 7
  python -m simulation "Roadside Ambush" "Roadside Ambush (Softened)" --seed 7
  python -m simulation --all --runs 2000 --seed 7 --save
  python -m simulation "Roadside Ambush" --play-by-play --seed 7
"""


def build_parser() -> argparse.ArgumentParser:
    """The argument parser, built separately so tests can exercise it directly."""
    parser = argparse.ArgumentParser(
        prog="python -m simulation",
        description="Fight one or more encounters N times each and report how they went.",
        epilog=USAGE_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "encounters",
        nargs="*",
        metavar="ENCOUNTER",
        help='encounters to run, named as their definitions name them (e.g. "Roadside Ambush"). '
        "Name several to get a comparison table.",
    )
    parser.add_argument(
        "-n",
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        metavar="N",
        help=f"how many fights to simulate per encounter (default: {DEFAULT_RUNS:,})",
    )
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        default=None,
        metavar="SEED",
        help="seed the run so it can be repeated exactly, and so every encounter in "
        "the command faces the same dice (default: unseeded)",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="run every encounter defined in encounters/",
    )
    parser.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="list the encounters that are defined, and what's in them",
    )
    parser.add_argument(
        "-p",
        "--play-by-play",
        action="store_true",
        help="run a single fight per encounter and narrate it, instead of a "
        "statistical run (ignores --runs)",
    )
    # Two flags rather than one `--save [DIR]`: an optional-value option sitting
    # next to a variadic positional is an argparse trap, where
    # `--save "Roadside Ambush"` quietly reads the encounter as a directory name.
    parser.add_argument(
        "--save",
        action="store_true",
        help=f"also write exactly what was printed to a timestamped file in {DEFAULT_SAVE_DIR}/",
    )
    parser.add_argument(
        "--save-dir",
        default=None,
        metavar="DIR",
        help=f"save to this directory instead of {DEFAULT_SAVE_DIR}/ (implies --save)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one command. Returns the process exit code.

    Errors that are a user's mistake - an unknown encounter, a nonsense run
    count - are reported as a message and a non-zero code rather than a
    traceback, since the name being wrong is the ordinary case and the registry
    already suggests what was probably meant.
    """
    parser = build_parser()
    arguments = parser.parse_args(argv)

    if arguments.list:
        print(_format_catalogue())
        return 0

    names = _chosen_encounters(parser, arguments)
    if names is None:
        parser.print_help()
        return 2

    if arguments.runs < 1:
        parser.error("--runs has to be at least 1")

    try:
        encounters = [find_encounter(name) for name in names]
    except KeyError as error:
        # The registry's message already carries the suggestions; KeyError
        # stringifies with quotes around it, so unwrap to the message itself.
        parser.exit(2, f"{error.args[0]}\n")

    if arguments.play_by_play:
        output = "\n\n".join(_narrate(encounter, arguments.seed) for encounter in encounters)
    else:
        output = _run_and_compare(encounters, arguments.runs, arguments.seed)

    print(output)

    if arguments.save or arguments.save_dir is not None:
        directory = arguments.save_dir or DEFAULT_SAVE_DIR
        print(f"\nSaved to {_save(output, directory, names)}")
    return 0


def _chosen_encounters(parser, arguments) -> list[str] | None:
    """The encounter names to run, or None if the command named nothing.

    `--all` and a list of names are refused together rather than merged: one of
    them would have to silently win, and quietly running something other than
    what was typed is the last thing a tool for measuring things should do.
    """
    if arguments.all and arguments.encounters:
        parser.error("name encounters or pass --all, not both")
    if arguments.all:
        return sorted(all_encounters())
    return list(arguments.encounters) or None


def _run_and_compare(encounters, runs: int, seed: int | None) -> str:
    """Every encounter's full report, with a comparison table when there's more than one.

    Each report is followed by its party's coverage, unconditionally. It's the
    context the win rate above it has to be read against - a party half of whose
    features aren't implemented makes any encounter look harder than it is - so
    it isn't behind a flag.
    """
    summaries, blocks = [], []
    for encounter in encounters:
        summary = run_simulation(encounter, runs=runs, seed=seed)
        summaries.append(summary)
        blocks.append(format_report(summary))
        blocks.append(format_coverage(encounter.spawn_party()))

    if len(summaries) > 1:
        blocks.append(format_comparison(summaries))
    return "\n\n".join(blocks)


def _format_catalogue() -> str:
    """Every defined encounter with its party and opposition.

    The party is loaded rather than listed by filename, so the names here match
    the ones a report prints. That does mean a definition pointing at a missing
    character file fails the listing - which is the right time to find out.
    """
    catalogue = all_encounters()
    if not catalogue:
        return "No encounters are defined in encounters/."

    lines = []
    for name, encounter in sorted(catalogue.items()):
        party = ", ".join(pc.name for pc in encounter.spawn_party()) or "(nobody)"
        opposition = "; ".join(describe_group(group) for group in encounter.groups)
        lines.append(name)
        lines.append(f"    party        {party}")
        lines.append(f"    opposition   {opposition or '(nothing)'}")
    return "\n".join(lines)


def _narrate(encounter, seed: int | None) -> str:
    """One fight, told line by line, with the result underneath.

    Seeded here rather than by the runner because this doesn't go through it -
    it's a single `run_fight`, the same call the Monte Carlo loop makes ten
    thousand times, with the logging its docstring recommends for exactly this.
    """
    if seed is not None:
        random.seed(seed)

    result = run_fight(encounter, logging=True)
    described = f"seed {seed}" if seed is not None else "unseeded"
    return "\n".join(
        [
            f"{encounter.name} - one fight ({described})",
            "-" * 78,
            *result.log,
            "-" * 78,
            repr(result),
        ]
    )


def _save(output: str, directory: str, names: list[str]) -> Path:
    """Write the printed output to a timestamped file and return where it went.

    One file per command rather than one per encounter, so a comparison and the
    reports it summarises stay in the same place - the whole point of saving a
    run is being able to reread the thing that was on screen.
    """
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    described = _slug(names[0]) if names else "run"
    if len(names) > 1:
        described += f"-and-{len(names) - 1}-more"

    destination = folder / f"{stamp}_{described}.txt"
    destination.write_text(output + "\n", encoding="utf-8")
    return destination


def _slug(name: str) -> str:
    """An encounter name as a filename - lowercase, punctuation collapsed to dashes."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "run"
