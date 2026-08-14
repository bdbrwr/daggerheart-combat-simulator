"""Look an encounter up by name, wherever in this package it's defined.

The command line names an encounter the way its definition does - "Roadside
Ambush" - rather than importing it from whichever module it happens to sit in.
Same job, and same reasoning, as adversaries/registry.py: adding an encounter
means writing the literal and nothing else, and how these files are organised
(one per adventure, one per tuning experiment) stays a decision we can revisit
without touching the CLI.

Discovery is lazy and cached - the first lookup imports every module in this
package and collects each Encounter it finds. Modules are imported for their
side effect of defining encounters, so a module that defines none is fine.
"""

import importlib
import pkgutil
from difflib import get_close_matches

from content.names import canonical
from encounters.encounter import Encounter

# Modules that hold machinery rather than encounter definitions. Importing them
# would be harmless (they define no Encounter literals), but skipping them makes
# the intent obvious and avoids importing this module from inside itself.
_NON_DEFINITION_MODULES = frozenset({"encounter", "registry"})

_catalogue: dict[str, Encounter] | None = None


def _discover() -> dict[str, Encounter]:
    """Import every definition module and collect its encounters by name.

    Raises ValueError if two different encounters claim the same name - a run
    named on the command line has nothing else to go on, and silently picking
    one would mean reporting numbers for a fight nobody asked for.
    """
    package = importlib.import_module(__package__)
    found: dict[str, Encounter] = {}
    # Keyed canonically for the uniqueness check only - two encounters differing
    # just in capitalisation are the same name to anyone typing one.
    claimed: dict[str, Encounter] = {}

    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name in _NON_DEFINITION_MODULES:
            continue
        module = importlib.import_module(f"{__package__}.{module_info.name}")

        for value in vars(module).values():
            if not isinstance(value, Encounter):
                continue
            existing = claimed.get(canonical(value.name))
            if existing is None:
                found[value.name] = value
                claimed[canonical(value.name)] = value
            elif existing is not value:
                raise ValueError(
                    f"Two different encounters are both named {value.name!r}. "
                    "Names have to be unique across this package - a run named "
                    "on the command line has nothing else to go on."
                )

    return found


def _load() -> dict[str, Encounter]:
    global _catalogue
    if _catalogue is None:
        _catalogue = _discover()
    return _catalogue


def refresh() -> None:
    """Drop the cache so the next lookup re-imports. For tests, mostly."""
    global _catalogue
    _catalogue = None


def find_encounter(name: str) -> Encounter:
    """The encounter defined under `name`.

    Returns the shared definition, which is safe to hand straight to a run -
    an Encounter is a recipe, and `spawn()` is what produces the combatants a
    fight actually marks HP on.

    Matched regardless of capitalisation, so `"roadside ambush"` typed at the
    command line finds "Roadside Ambush".
    """
    catalogue = _load()
    wanted = canonical(name)
    for defined, encounter in catalogue.items():
        if canonical(defined) == wanted:
            return encounter

    try:
        return catalogue[name]
    except KeyError:
        suggestions = get_close_matches(name, catalogue, n=3)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        raise KeyError(
            f"No encounter named {name!r} is defined in this package.{hint}"
        ) from None


def all_encounters() -> dict[str, Encounter]:
    """Every defined encounter by name - a copy, so callers can't corrupt the cache."""
    return dict(_load())
