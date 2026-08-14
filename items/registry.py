"""Look a piece of gear up by the name a character sheet writes it under.

A PC's JSON names its gear the way the book does - "Broadsword", "Gambeson
Armor", "Minor Healing Potion" - and something has to turn that into the thing
itself. That's this: the same job adversaries/registry.py does for stat blocks,
and for the same reason, so a character file never has to know where its gear is
defined.

## Two kinds of thing in here

**Weapons and armor are data**, read from the JSON catalogues in this package
(see catalogue.py). What they do beyond their printed numbers is named features,
implemented in features/.

**Consumables are callables**, registered by a decorator on the function itself.
A potion's whole existence is the effect it has when drunk - there is no record
to speak of - so writing one means writing the function and naming it. They are
deliberately kept few, which is why they carry no catalogue of their own.

## Misses

`find_weapon` raises. Gear that doesn't resolve means a PC who can't attack at
all, which is worth failing loudly over, and the suggestion tells the author what
to copy onto the sheet.

`find_armor` returns None instead. A sheet carries Armor Score and thresholds
already resolved, so an armor nobody has catalogued costs a fight nothing - and
requiring every homebrew breastplate to be written up before a sheet will load
would be a real burden for no gain. It is never silent, though: a PC whose armor
isn't catalogued reports the armor's own name as unimplemented in the coverage
block, so the gap is visible rather than assumed away.

Discovery is lazy and cached - the first lookup reads every catalogue and imports
every module in this package, so the consumable decorators have run. A catalogue
that won't load is kept in `load_errors()` rather than dropped, the same contract
encounters/ and adversaries/ keep.
"""

import importlib
import pkgutil
from difflib import get_close_matches
from pathlib import Path
from typing import Callable

from content.names import canonical
from items.catalogue import Armor, Weapon, read_catalogue

_DEFINITIONS_DIR = Path(__file__).resolve().parent

# Modules that hold machinery rather than consumable definitions. Importing them
# would be harmless, but skipping them makes the intent obvious and avoids
# importing this module from inside itself.
_NON_DEFINITION_MODULES = frozenset({"registry", "catalogue", "weapons"})

_weapons: dict[str, Weapon] = {}
_armor: dict[str, Armor] = {}
_consumables: dict[str, Callable] = {}
_consumable_names: dict[str, str] = {}
_failures: dict[str, str] = {}
_discovered = False


# --- Consumables -------------------------------------------------------------


def consumable(name: str):
    """Register a consumable's effect under the name character sheets use for it."""

    def register(function: Callable) -> Callable:
        key = canonical(name)
        existing = _consumables.get(key)
        if existing is not None and existing is not function:
            raise ValueError(
                f"Two different consumables are both registered as {name!r}. Names "
                "have to be unique - a character sheet has nothing else to go on."
            )
        _consumables[key] = function
        _consumable_names[key] = name
        return function

    return register


# --- Discovery ---------------------------------------------------------------


def _discover() -> None:
    """Read every catalogue and import every definition module in this package."""
    global _discovered
    if _discovered:
        return

    _weapons.clear()
    _armor.clear()
    _failures.clear()

    claimed_weapons: dict[str, str] = {}
    claimed_armor: dict[str, str] = {}

    for path in sorted(_DEFINITIONS_DIR.glob("*.json")):
        try:
            weapons, armor = read_catalogue(path)
        except Exception as error:  # a bad file is one bad catalogue, not a crash
            _failures[path.name] = f"{type(error).__name__}: {error}"
            continue

        for found, table, claimed, kind in (
            (weapons, _weapons, claimed_weapons, "weapons"),
            (armor, _armor, claimed_armor, "armor"),
        ):
            for item in found:
                key = canonical(item.name)
                claimed_by = claimed.get(key)
                if claimed_by is not None:
                    raise ValueError(
                        f"Two {kind} are both named {item.name!r} ({claimed_by} "
                        f"and {path.name}). Names have to be unique - a character "
                        "sheet has nothing else to go on."
                    )
                table[key] = item
                claimed[key] = path.name

    package = importlib.import_module(__package__)
    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name not in _NON_DEFINITION_MODULES:
            importlib.import_module(f"{__package__}.{module_info.name}")

    _discovered = True


def refresh() -> None:
    """Force the next lookup to re-read and re-import. For tests, mostly."""
    global _discovered
    _discovered = False


def load_errors() -> dict[str, str]:
    """Catalogues in this package that didn't load, by filename, with the reason."""
    _discover()
    return dict(_failures)


# --- Lookup ------------------------------------------------------------------


def find_weapon(name: str) -> Weapon:
    """The weapon record published under `name`, whatever case the sheet wrote it in.

    Raises on a miss: a PC whose weapon doesn't resolve can't attack, and that is
    worth failing loudly over rather than fighting without one.
    """
    _discover()
    try:
        return _weapons[canonical(name)]
    except KeyError:
        raise KeyError(f"No weapon named {name!r} is catalogued.{_hint(name, _weapons)}") from None


def find_armor(name: str) -> Armor | None:
    """The armor record published under `name`, or None if nobody has catalogued it.

    None rather than an error - see this module's docstring. The caller is
    expected to surface the miss, not to swallow it.
    """
    _discover()
    return _armor.get(canonical(name))


def find_consumable(name: str) -> Callable:
    """The effect callable for the consumable published under `name`."""
    _discover()
    try:
        return _consumables[canonical(name)]
    except KeyError:
        described = ", ".join(
            _consumable_names[key]
            for key in get_close_matches(canonical(name), _consumable_names, n=3)
        )
        hint = f" Did you mean: {described}?" if described else ""
        raise KeyError(f"No consumable named {name!r} is implemented.{hint}") from None


def _hint(name: str, table: dict) -> str:
    """Near misses, shown in the spelling that needs copying onto the sheet."""
    suggestions = get_close_matches(canonical(name), table, n=3)
    described = ", ".join(table[key].name for key in suggestions)
    return f" Did you mean: {described}?" if described else ""


def all_weapons() -> dict[str, Weapon]:
    """Every catalogued weapon, keyed by the name it was published under."""
    _discover()
    return {weapon.name: weapon for weapon in _weapons.values()}


def all_armor() -> dict[str, Armor]:
    """Every catalogued armor, keyed by the name it was published under."""
    _discover()
    return {armor.name: armor for armor in _armor.values()}


def all_consumables() -> dict[str, Callable]:
    """Every consumable, keyed by the name it was registered under."""
    _discover()
    return {_consumable_names[key]: function for key, function in _consumables.items()}
