"""Look an experiment up by name, wherever in this package it's defined.

The command line names an experiment the way its file does - "Roadside Ambush" -
so how these files are organised stays a decision we can revisit without touching
the CLI. Adding one means writing a JSON file in this package and nothing else.

## Why JSON rather than Python

An encounter file is data: a name, some counts, some overridden numbers. Nothing
in it runs. Authoring them as Python modules meant every one was *imported* on
every run, so a single broken tuning experiment took down `--list` and every
other encounter with it - and that gets worse the more variations there are,
which for a tool whose workflow is "define a variation, run it, keep the one you
like" is the wrong direction. Data files fail one at a time.

## A broken file is never silent

Isolation must not become silence, which is the failure this project cares most
about. A file that won't load is kept in `load_errors()` rather than dropped:
`--list` prints them, and asking for an experiment that isn't there reports them
alongside the near-miss suggestions. A run that vanished because somebody left a
trailing comma should say so.
"""

from difflib import get_close_matches
from pathlib import Path

from content.names import canonical
from encounters.encounter import Experiment

_DEFINITIONS_DIR = Path(__file__).resolve().parent

_catalogue: dict[str, Experiment] | None = None
_failures: dict[str, str] = {}


def _discover() -> dict[str, Experiment]:
    """Read every encounter file in this package, keeping the failures.

    Raises ValueError if two files claim the same name - a run named on the
    command line has nothing else to go on, and silently picking one would mean
    reporting numbers for a fight nobody asked for. Names differing only in
    capitalisation are the same name for this purpose.
    """
    found: dict[str, Experiment] = {}
    claimed: dict[str, str] = {}
    _failures.clear()

    for path in sorted(_DEFINITIONS_DIR.glob("*.json")):
        try:
            experiment = Experiment.from_json(path)
        except Exception as error:  # a bad file is one bad experiment, not a crash
            _failures[path.name] = f"{type(error).__name__}: {error}"
            continue

        claimed_by = claimed.get(canonical(experiment.name))
        if claimed_by is not None:
            raise ValueError(
                f"Two encounter files are both named {experiment.name!r} "
                f"({claimed_by} and {path.name}). Names have to be unique across "
                "this package - a run named on the command line has nothing else "
                "to go on."
            )

        found[experiment.name] = experiment
        claimed[canonical(experiment.name)] = path.name

    return found


def _load() -> dict[str, Experiment]:
    global _catalogue
    if _catalogue is None:
        _catalogue = _discover()
    return _catalogue


def refresh() -> None:
    """Drop the cache so the next lookup re-reads the files. For tests, mostly."""
    global _catalogue
    _catalogue = None


def load_errors() -> dict[str, str]:
    """Files in this package that didn't load, by filename, with the reason."""
    _load()
    return dict(_failures)


def find_experiment(name: str) -> Experiment:
    """The experiment defined under `name`, with every variation it holds.

    Returns the shared definition, which is safe to hand straight to a run - an
    Encounter is a recipe, and `spawn()` is what produces the combatants a fight
    actually marks HP on.

    Matched regardless of capitalisation, so `"roadside ambush"` typed at the
    command line finds "Roadside Ambush".
    """
    catalogue = _load()
    wanted = canonical(name)
    for defined, experiment in catalogue.items():
        if canonical(defined) == wanted:
            return experiment

    suggestions = get_close_matches(name, catalogue, n=3)
    hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
    if _failures:
        broken = ", ".join(sorted(_failures))
        hint += f" (These files didn't load, and may be the one you wanted: {broken}.)"
    raise KeyError(f"No experiment named {name!r} is defined in this package.{hint}")


def all_experiments() -> dict[str, Experiment]:
    """Every defined experiment by name - a copy, so callers can't corrupt the cache."""
    return dict(_load())
