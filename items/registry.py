"""Look an item up by the name a character sheet writes it under.

A PC's JSON names its gear the way the book does - "Broadsword", "Minor
Healing Potion" - but the items themselves are callables, so something has to
bridge the two. That's this: the same job adversaries/registry.py does for
stat blocks, and for the same reason - so a character file never has to know
which module its gear is implemented in.

Registration is a decorator on the function itself, which keeps an item
defined in exactly one place: writing a new weapon means writing the function
and naming it, with nothing to add to a table elsewhere.

Discovery is lazy and cached - the first lookup imports every module in this
package so their decorators run.
"""

import importlib
import pkgutil
from difflib import get_close_matches
from typing import Callable

from content.names import canonical

# Modules that hold machinery rather than item definitions.
_NON_DEFINITION_MODULES = frozenset({"registry"})

# Keyed canonically, so a sheet writing "greatsword" still finds the Greatsword.
# The companion dicts remember the spelling each item was registered under, which
# is what a suggestion in an error message should show.
_weapons: dict[str, Callable] = {}
_weapon_names: dict[str, str] = {}
_consumables: dict[str, Callable] = {}
_consumable_names: dict[str, str] = {}
_discovered = False


def weapon(name: str):
    """Register a weapon attack under the name character sheets use for it."""

    def register(function: Callable) -> Callable:
        _claim(_weapons, _weapon_names, name, function, "weapon")
        return function

    return register


def consumable(name: str):
    """Register a consumable's effect under the name character sheets use for it."""

    def register(function: Callable) -> Callable:
        _claim(_consumables, _consumable_names, name, function, "consumable")
        return function

    return register


def _claim(
    table: dict[str, Callable],
    names: dict[str, str],
    name: str,
    function: Callable,
    kind: str,
) -> None:
    """Take a name in `table`, refusing to let two items share one.

    A duplicate name would make a lookup ambiguous, and silently picking one
    would quietly simulate the wrong gear. Claimed canonically, so two items
    differing only in capitalisation collide rather than shadowing each other.
    """
    key = canonical(name)
    existing = table.get(key)
    if existing is not None and existing is not function:
        raise ValueError(
            f"Two different {kind}s are both registered as {name!r}. Names have "
            "to be unique - a character sheet has nothing else to go on."
        )
    table[key] = function
    names[key] = name


def _discover() -> None:
    """Import every module in this package so its decorators have run."""
    global _discovered
    if _discovered:
        return
    package = importlib.import_module(__package__)
    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name in _NON_DEFINITION_MODULES:
            continue
        importlib.import_module(f"{__package__}.{module_info.name}")
    _discovered = True


def refresh() -> None:
    """Force the next lookup to re-import. For tests, mostly."""
    global _discovered
    _discovered = False


def _find(
    table: dict[str, Callable], names: dict[str, str], name: str, kind: str
) -> Callable:
    """The item registered under `name`, whatever case the sheet wrote it in.

    A miss still raises: gear that doesn't resolve means a PC who can't attack,
    which is worth failing loudly over. Suggestions are shown in the spelling
    they were registered with, since that's what needs copying onto the sheet.
    """
    _discover()
    try:
        return table[canonical(name)]
    except KeyError:
        suggestions = get_close_matches(canonical(name), names, n=3)
        described = ", ".join(names[key] for key in suggestions)
        hint = f" Did you mean: {described}?" if suggestions else ""
        raise KeyError(f"No {kind} named {name!r} is implemented.{hint}") from None


def find_weapon(name: str) -> Callable:
    """The attack callable for the weapon published under `name`."""
    return _find(_weapons, _weapon_names, name, "weapon")


def find_consumable(name: str) -> Callable:
    """The effect callable for the consumable published under `name`."""
    return _find(_consumables, _consumable_names, name, "consumable")


def all_weapons() -> dict[str, Callable]:
    """Every weapon, keyed by the name it was registered under."""
    _discover()
    return {_weapon_names[key]: function for key, function in _weapons.items()}


def all_consumables() -> dict[str, Callable]:
    """Every consumable, keyed by the name it was registered under."""
    _discover()
    return {_consumable_names[key]: function for key, function in _consumables.items()}
