"""Look a domain card up by the name a character sheet writes, and run it.

Same job as adversaries/registry.py and items/registry.py, for the third kind of
game content: a sheet names its loadout ("I Am Your Shield", "Get Back Up") and
this is what turns those names into behaviour.

## One card, one module

There are roughly 210 domain cards. The hard rule that shape follows from:
**implementing a card means writing code in exactly one place.** A card's effect
and the decision about whether it fires both live with the card, in its domain's
module. Nothing outside this package may grow a branch, a loop, or a special
case that knows a card by name - if adding the 211th card would mean editing
combat/policy.py, the design is wrong.

What the rest of the codebase gets instead is the dispatch functions at the
bottom of this file: one call per hook point, which iterate a PC's loadout and
hand off. `PlayerCharacter.take_damage` calls `soften_damage`; the fight's turn
policy calls `find_shielder`. Neither knows a card exists.

New hook types (a card that changes an attack roll, a card that is a turn
action) get a new dispatch function here and a single call site out there. The
call sites stay constant in number as cards are added; only this package grows.

## Why a top-level package

Not `characters/domain_cards/`, because characters/player_character.py calls
`soften_damage`, and discovery importing its own parent package would be a
cycle. Sitting alongside items/ and adversaries/ also matches the flat layout.

Discovery is lazy and cached - the first lookup imports every module in this
package so their decorators have run.
"""

import importlib
import pkgutil
from typing import Callable, NamedTuple, Protocol

# Modules that hold machinery rather than card definitions.
_NON_DEFINITION_MODULES = frozenset({"registry"})

# Cards that change how much a hit costs the PC taking it.
_severity_responses: dict[str, Callable] = {}

# Cards that let one PC take a hit aimed at another.
_guards: dict[str, Callable] = {}

_discovered = False


class Holder(Protocol):
    """The slice of a PC that domain cards touch.

    A Protocol rather than importing PlayerCharacter: characters/ imports this
    package, and the import can't run both ways.
    """

    name: str
    severe_threshold: int
    hp_remaining: int
    stress_marked: int
    stress_max: int
    domain_cards_loadout: list[str]

    def spend_stress(self, amount: int = 1) -> bool: ...


class Interception(NamedTuple):
    """A PC stepping in front of another, and the card that let them."""

    shielder: Holder
    card: str


# --- Registration ------------------------------------------------------------


def severity_response(name: str):
    """Register a card that changes the HP an incoming hit marks."""

    def register(function: Callable) -> Callable:
        _claim(_severity_responses, name, function)
        return function

    return register


def guard(name: str):
    """Register a card that lets its holder take a hit aimed at an ally."""

    def register(function: Callable) -> Callable:
        _claim(_guards, name, function)
        return function

    return register


def _claim(table: dict[str, Callable], name: str, function: Callable) -> None:
    """Take a name in `table`, refusing to let two cards share one."""
    existing = table.get(name)
    if existing is not None and existing is not function:
        raise ValueError(
            f"Two different domain cards are both registered as {name!r}. Names "
            "have to be unique - a character sheet has nothing else to go on."
        )
    table[name] = function


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


# --- Lookup ------------------------------------------------------------------


def find_severity_response(name: str) -> Callable | None:
    """The damage-response for `name`, or None if that card isn't implemented.

    None rather than an error, unlike items/registry.py: a loadout is allowed to
    name cards nobody has written yet, and a PC carrying one still has to be
    able to walk into a fight. Gear is different - a weapon that doesn't resolve
    means a PC who can't attack at all, which is worth failing loudly over.
    """
    _discover()
    return _severity_responses.get(name)


def find_guard(name: str) -> Callable | None:
    """The guard behaviour for `name`, or None if that card isn't implemented."""
    _discover()
    return _guards.get(name)


def all_severity_responses() -> dict[str, Callable]:
    _discover()
    return dict(_severity_responses)


def all_guards() -> dict[str, Callable]:
    _discover()
    return dict(_guards)


# --- Dispatch ----------------------------------------------------------------
#
# The only functions the rest of the codebase calls. One per hook point.


def soften_damage(character: Holder, amount: int, hp_to_mark: int) -> int:
    """Let every damage-response card in `character`'s loadout soften a hit.

    Called once by PlayerCharacter.take_damage. Cards are applied in loadout
    order and each sees what the previous one left, so two reductions stack.
    """
    _discover()
    for name in character.domain_cards_loadout:
        respond = _severity_responses.get(name)
        if respond is not None:
            hp_to_mark = respond(character, amount, hp_to_mark)
    return hp_to_mark


def find_shielder(target: Holder, party: list) -> Interception | None:
    """An ally who steps in front of `target`, or None if nobody does.

    Called once by the turn policy, before an adversary's attack is rolled. The
    first willing ally goes: a party with two Guardians both shielding the same
    PC is not a situation worth the code it would take to arbitrate.

    Deciding whether stepping in is worthwhile is the card's business, not this
    function's - a card says no by returning False.
    """
    _discover()
    for ally in party:
        if ally is target:
            continue
        for name in ally.domain_cards_loadout:
            steps_in = _guards.get(name)
            if steps_in is not None and steps_in(ally, target):
                return Interception(shielder=ally, card=name)
    return None
