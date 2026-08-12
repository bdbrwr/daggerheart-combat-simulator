"""Look an adversary up by name, wherever in this package it's defined.

Encounters name adversaries the way the book does - "Jagged Knife Bandit" -
rather than importing them from whichever module they happen to sit in. That
keeps the filing (srd.py, homebrew.py, one module per purchased adventure) a
decision we can revisit without editing a single encounter, and it means
adding an adversary is just writing the literal: discovery is automatic, there
is nothing to register by hand.

Discovery is lazy and cached - the first lookup imports every module in this
package and collects each Adversary it finds. Modules are imported for their
side effect of defining adversaries, so a module that defines none is fine.
"""

import importlib
import pkgutil
from difflib import get_close_matches

from adversaries.adversary import Adversary

# Modules that hold machinery rather than adversary definitions. Importing them
# would be harmless (they define no Adversary literals), but skipping them makes
# the intent obvious and avoids importing this module from inside itself.
_NON_DEFINITION_MODULES = frozenset({"adversary", "registry"})

_catalogue: dict[str, Adversary] | None = None


def _discover() -> dict[str, Adversary]:
    """Import every definition module and collect its adversaries by name.

    Raises ValueError if two different adversaries claim the same name - that
    would make a lookup ambiguous, and silently picking one would quietly
    simulate the wrong fight. The same object showing up in two modules (a
    re-export) is fine and collapses to one entry.
    """
    package = importlib.import_module(__package__)
    found: dict[str, Adversary] = {}

    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name in _NON_DEFINITION_MODULES:
            continue
        module = importlib.import_module(f"{__package__}.{module_info.name}")

        for value in vars(module).values():
            if not isinstance(value, Adversary):
                continue
            existing = found.get(value.name)
            if existing is None:
                found[value.name] = value
            elif existing is not value:
                raise ValueError(
                    f"Two different adversaries are both named {value.name!r}. "
                    "Names have to be unique across this package - an encounter "
                    "has nothing else to go on. To vary a published stat block, "
                    "override it in the encounter instead of redefining it."
                )

    return found


def _load() -> dict[str, Adversary]:
    global _catalogue
    if _catalogue is None:
        _catalogue = _discover()
    return _catalogue


def refresh() -> None:
    """Drop the cache so the next lookup re-imports. For tests, mostly."""
    global _catalogue
    _catalogue = None


def find_adversary(name: str) -> Adversary:
    """The adversary definition published under `name`.

    Returns the shared definition, not a copy - spawn() it (or let a Group do
    that) before anything marks HP on it.
    """
    catalogue = _load()
    try:
        return catalogue[name]
    except KeyError:
        suggestions = get_close_matches(name, catalogue, n=3)
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        raise KeyError(
            f"No adversary named {name!r} is defined in this package.{hint}"
        ) from None


def all_adversaries() -> dict[str, Adversary]:
    """Every defined adversary by name - a copy, so callers can't corrupt the cache."""
    return dict(_load())
