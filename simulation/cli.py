"""The command line - how a run actually gets started.

Everything under this module already worked; what was missing was a way to ask
it a question without opening a REPL. That's all this is: name an encounter,
say how many times to fight it, and get simulation/report.py's block of text.

Three things you can ask for, because they're the three questions that come up
while tuning a stat block:

    python -m simulation --list
    python -m simulation "Roadside Ambush" --runs 10000 --seed 7
    python -m simulation "Roadside Ambush" --play-by-play --seed 7

The last one is the important one. A win rate that looks wrong is unreadable on
its own - it says a number is off but not which rule produced it - so the same
encounter can be run once with the fight loop narrating itself, and the seed
makes that single fight reproducible. Tuning tends to go: run ten thousand,
notice something odd, run one and read it.

Encounters are named, not built here. A fight worth running is worth committing
as a definition in encounters/, where its overrides sit next to the stat block
they tune and a run from last week can be repeated exactly.
"""

import argparse
import random

from combat.fight import run_fight
from encounters.registry import all_encounters, find_encounter
from simulation.report import format_report
from simulation.runner import DEFAULT_RUNS, describe_group, run_simulation

USAGE_EXAMPLES = """\
examples:
  python -m simulation --list
  python -m simulation "Roadside Ambush"
  python -m simulation "Roadside Ambush" --runs 1000 --seed 7
  python -m simulation "Roadside Ambush" --play-by-play --seed 7
"""


def build_parser() -> argparse.ArgumentParser:
    """The argument parser, built separately so tests can exercise it directly."""
    parser = argparse.ArgumentParser(
        prog="python -m simulation",
        description="Fight an encounter N times and report how it went.",
        epilog=USAGE_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "encounter",
        nargs="?",
        help='the encounter to run, named as its definition names it (e.g. "Roadside Ambush")',
    )
    parser.add_argument(
        "-n",
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        metavar="N",
        help=f"how many fights to simulate (default: {DEFAULT_RUNS:,})",
    )
    parser.add_argument(
        "-s",
        "--seed",
        type=int,
        default=None,
        metavar="SEED",
        help="seed the run so it can be repeated exactly (default: unseeded)",
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
        help="run a single fight and narrate it, instead of a statistical run (ignores --runs)",
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

    if arguments.encounter is None:
        parser.print_help()
        return 2

    if arguments.runs < 1:
        parser.error("--runs has to be at least 1")

    try:
        encounter = find_encounter(arguments.encounter)
    except KeyError as error:
        # The registry's message already carries the suggestions; KeyError
        # stringifies with quotes around it, so unwrap to the message itself.
        parser.exit(2, f"{error.args[0]}\n")

    if arguments.play_by_play:
        print(_narrate(encounter, arguments.seed))
    else:
        print(format_report(run_simulation(encounter, runs=arguments.runs, seed=arguments.seed)))
    return 0


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
