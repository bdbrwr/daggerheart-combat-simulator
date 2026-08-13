"""Run one encounter N times.

The loop itself is three lines - the work this module actually does is make a
run reproducible and record what it was a run *of*, so a summary read a week
later still says which stat blocks produced it.

Seeding follows the project's existing convention: `random.seed()` on the
global module rather than an injected generator, matching dice/. One seed at
the top of a run fixes every fight in it, so `seed=7, runs=10_000` is a single
reproducible experiment, not 10,000 unrelated ones.
"""

import random

from simulation.summary import FightRecord, SimulationSummary
from combat.fight import run_fight

DEFAULT_RUNS = 10_000


def run_simulation(encounter, runs: int = DEFAULT_RUNS, seed: int | None = None) -> SimulationSummary:
    """Fight `encounter` `runs` times and hand back everything that happened.

    Each fight spawns both sides fresh, so nothing carries between them.
    Logging stays off - a play-by-play of 10,000 fights is worth nothing and
    costs a great deal of string building. Use `run_fight(encounter,
    logging=True)` when a single fight needs explaining.
    """
    if seed is not None:
        random.seed(seed)

    records = [FightRecord.of(run_fight(encounter)) for _ in range(runs)]

    return SimulationSummary(
        encounter_name=encounter.name,
        party=[pc.name for pc in encounter.spawn_party()],
        opposition=[describe_group(group) for group in encounter.groups],
        seed=seed,
        records=records,
    )


def describe_group(group) -> str:
    """A group as a reader needs it: the stat block, the count, and any tuning.

    The overrides matter more than anything else on the line - a run against a
    Sniper with hp_max=5 is a different experiment from one against the
    printed stat block, and a summary that hid that would be misleading.
    """
    described = f"{group.adversary.name} x{group.count}"
    if group.overrides:
        tuning = ", ".join(f"{stat}={value!r}" for stat, value in group.overrides.items())
        described += f" ({tuning})"
    return described
