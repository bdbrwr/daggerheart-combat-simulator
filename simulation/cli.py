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

What you name is an *encounter file* - one experiment, holding the variations
that answer one question. Naming it runs every variation in it, reports each in
full, and puts a comparison table underneath whose rows are the variations. That
is the tuning workflow in a single command, and it's why variations belong in one
file: they're only worth reading against each other.

Crucially a single `--seed` seeds every run in the command, so each variation is
fought against the same sequence of dice and a difference between two rows is a
difference between the stat blocks rather than luck.

Naming several files runs each experiment and prints its own table; the tables
stay separate, because a row from one question doesn't belong beside a row from
another.

Encounters are named, not built here. A variation worth running is worth
committing to its file in encounters/, where its overrides sit next to the stat
block they tune and a run from last week can be repeated exactly.

`--play-by-play` is the other half of the job: a single seeded fight with the
loop narrating itself. A win rate that looks wrong says a number is off but not
which rule produced it, so tuning tends to go - run ten thousand, notice
something odd, run one and read it.
"""

import argparse
import random
import re
import textwrap
from datetime import datetime
from pathlib import Path

from combat.fight import run_fight
from encounters.registry import all_experiments, find_experiment, load_errors
from simulation.coverage import CoverageDetail, format_coverage
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
  python -m simulation "Roadside Ambush" "Cliffside Chase" --seed 7
  python -m simulation --all --runs 2000 --seed 7 --save
  python -m simulation "Roadside Ambush" --play-by-play --seed 7
  python -m simulation "Roadside Ambush" --full-coverage
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
    # Mutually exclusive: they're three points on one dial, and asking for two
    # at once has no sensible answer.
    coverage = parser.add_mutually_exclusive_group()
    coverage.add_argument(
        "--no-coverage",
        action="store_true",
        help="omit the coverage block entirely",
    )
    coverage.add_argument(
        "--full-coverage",
        action="store_true",
        help="print the whole coverage block, including modelled content and the "
        "gaps declared on it (default: only what isn't running)",
    )
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

    names = _chosen_experiments(parser, arguments)
    if names is None:
        parser.print_help()
        return 2

    if arguments.runs < 1:
        parser.error("--runs has to be at least 1")

    try:
        experiments = [find_experiment(name) for name in names]
    except KeyError as error:
        # The registry's message already carries the suggestions; KeyError
        # stringifies with quotes around it, so unwrap to the message itself.
        parser.exit(2, f"{error.args[0]}\n")

    if arguments.play_by_play:
        output = "\n\n".join(
            _narrate(variation, arguments.seed)
            for experiment in experiments
            for variation in experiment.variations
        )
    else:
        output = _run_and_compare(
            experiments, arguments.runs, arguments.seed, _coverage_detail(arguments)
        )

    print(output)

    if arguments.save or arguments.save_dir is not None:
        directory = arguments.save_dir or DEFAULT_SAVE_DIR
        print(f"\nSaved to {_save(output, directory, names)}")
    return 0


def _chosen_experiments(parser, arguments) -> list[str] | None:
    """The experiment names to run, or None if the command named nothing.

    `--all` and a list of names are refused together rather than merged: one of
    them would have to silently win, and quietly running something other than
    what was typed is the last thing a tool for measuring things should do.
    """
    if arguments.all and arguments.encounters:
        parser.error("name encounters or pass --all, not both")
    if arguments.all:
        return sorted(all_experiments())
    return list(arguments.encounters) or None


def _coverage_detail(arguments) -> CoverageDetail:
    """Which coverage level the flags asked for; argparse already refused both."""
    if arguments.no_coverage:
        return CoverageDetail.NONE
    if arguments.full_coverage:
        return CoverageDetail.FULL
    return CoverageDetail.SUMMARY


def _run_and_compare(
    experiments,
    runs: int,
    seed: int | None,
    coverage: CoverageDetail = CoverageDetail.SUMMARY,
) -> str:
    """Every variation's full report, with its experiment's comparison underneath.

    The comparison belongs to one experiment rather than to the whole command:
    variations of one question are what's worth reading against each other, and
    a table mixing two unrelated experiments would invite exactly the comparison
    the file boundary exists to prevent.

    Coverage follows the reports - it's the context a win rate has to be read
    against, since unimplemented content on the party's side makes an encounter
    look harder than it is and unimplemented content on the opposition's makes it
    look easier. Printed once per distinct pairing of party and opposition rather
    than once per variation, since variations usually share both, but never
    skipped for a variation that changes either.

    How much of it prints is `--no-coverage` / `--full-coverage`; see
    simulation/coverage.py. At NONE the block comes back empty and simply isn't
    appended, so nothing here needs to know which level it asked for.
    """
    blocks = []
    for experiment in experiments:
        summaries = []
        shown = set()

        for variation in experiment.variations:
            summaries.append(run_simulation(variation, runs=runs, seed=seed))
            blocks.append(format_report(summaries[-1]))

            # Keyed on both sides: two variations sharing a party but fielding
            # different stat blocks have different coverage, and the opposition's
            # is the half that says whether an encounter is easier than it reads.
            fielded = (
                tuple(variation.party),
                tuple(group.adversary.name for group in variation.groups),
            )
            if fielded not in shown:
                shown.add(fielded)
                block = format_coverage(
                    variation.spawn_party(), variation.spawn_adversaries(), coverage
                )
                if block:
                    blocks.append(block)

        if len(summaries) > 1:
            blocks.append(format_comparison(summaries, title=experiment.name))

    return "\n\n".join(blocks)


LABEL_INDENT = " " * 17


def _format_catalogue() -> str:
    """Every defined encounter with its party, opposition and notes.

    The party is loaded rather than listed by filename, so the names here match
    the ones a report prints. That does mean a definition pointing at a missing
    character file fails the listing - which is the right time to find out.

    Files that wouldn't load are listed underneath rather than passed over. A
    run that quietly isn't there is the whole reason this section exists.
    """
    catalogue = all_experiments()
    failures = load_errors()
    if not catalogue and not failures:
        return "No encounters are defined in encounters/."

    lines = []
    for name, experiment in sorted(catalogue.items()):
        lines.append(name)
        if experiment.notes:
            lines.append(
                textwrap.fill(
                    experiment.notes,
                    width=78,
                    initial_indent="    notes        ",
                    subsequent_indent=LABEL_INDENT,
                )
            )

        shared_party = experiment.variations[0].party
        lines.append(f"    party        {_named_party(experiment.variations[0])}")
        lines.append("    variations")
        for variation in experiment.variations:
            opposition = "; ".join(describe_group(group) for group in variation.groups)
            lines.append(f"        {variation.name:<24}{opposition or '(nothing)'}")
            # Only worth repeating when this variation swapped the party out.
            if variation.party != shared_party:
                lines.append(f"        {'':<24}party: {_named_party(variation)}")

    if failures:
        lines.append("")
        lines.append("! These files in encounters/ did not load:")
        for filename, reason in sorted(failures.items()):
            lines.append(f"    {filename}")
            lines.append(f"        {reason}")

    return "\n".join(lines)


def _named_party(variation) -> str:
    """The PC names a variation fields, loaded from their sheets."""
    return ", ".join(pc.name for pc in variation.spawn_party()) or "(nobody)"


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
            f"{encounter.title} - one fight ({described})",
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
