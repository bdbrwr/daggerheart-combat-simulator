"""Look an adversary up by name, whichever catalogue in this package defines it.

Encounters name adversaries the way the book does - "Jagged Knife Bandit" -
rather than knowing which file they sit in. That keeps the filing (srd.json,
homebrew.json, one file per purchased adventure) a decision we can revisit
without editing a single encounter, and it means adding an adversary is just
writing the entry: discovery is automatic, there is nothing to register by hand.

## A broken file is never silent

Isolation must not become silence, which is the failure this project cares most
about - it's the same contract encounters/registry.py keeps, for the same reason.
A catalogue that won't load is kept in `load_errors()` rather than dropped:
`--list` prints them, and a lookup that misses reports them alongside the
near-miss suggestions. An adversary that vanished because somebody left a
trailing comma has to say so, because otherwise it looks exactly like an
adversary nobody has written.

Discovery is lazy and cached - the first lookup reads every catalogue in this
package.
"""

from difflib import get_close_matches
from pathlib import Path

from adversaries.adversary import Adversary
from adversaries.catalogue import read_catalogue
from content.names import canonical

_DEFINITIONS_DIR = Path(__file__).resolve().parent

_catalogue: dict[str, Adversary] | None = None
_failures: dict[str, str] = {}


def _discover() -> dict[str, Adversary]:
    """Read every catalogue in this package, keeping the failures.

    Raises ValueError if two entries claim the same name - that would make a
    lookup ambiguous, and silently picking one would quietly simulate the wrong
    fight. Names differing only in capitalisation are the same name here, since
    an encounter naming one is typed by hand.
    """
    found: dict[str, Adversary] = {}
    claimed: dict[str, str] = {}
    _failures.clear()

    for path in sorted(_DEFINITIONS_DIR.glob("*.json")):
        try:
            defined = read_catalogue(path)
        except Exception as error:  # a bad file is one bad catalogue, not a crash
            _failures[path.name] = f"{type(error).__name__}: {error}"
            continue

        for adversary in defined:
            claimed_by = claimed.get(canonical(adversary.name))
            if claimed_by is not None:
                raise ValueError(
                    f"Two adversaries are both named {adversary.name!r} "
                    f"({claimed_by} and {path.name}). Names have to be unique "
                    "across this package - an encounter has nothing else to go "
                    "on. To vary a published stat block, override it in the "
                    "encounter instead of redefining it."
                )
            found[adversary.name] = adversary
            claimed[canonical(adversary.name)] = path.name

    return found


def _load() -> dict[str, Adversary]:
    global _catalogue
    if _catalogue is None:
        _catalogue = _discover()
    return _catalogue


def refresh() -> None:
    """Drop the cache so the next lookup re-reads the files. For tests, mostly."""
    global _catalogue
    _catalogue = None


def load_errors() -> dict[str, str]:
    """Catalogues in this package that didn't load, by filename, with the reason."""
    _load()
    return dict(_failures)


def find_adversary(name: str) -> Adversary:
    """The adversary defined under `name`.

    Returns the shared definition, not a copy - spawn() it (or let a Group do
    that) before anything marks HP on it.

    Matched regardless of capitalisation, the same way a character sheet's names
    are - an encounter is typed by hand too.
    """
    catalogue = _load()
    wanted = canonical(name)
    for defined, adversary in catalogue.items():
        if canonical(defined) == wanted:
            return adversary

    suggestions = get_close_matches(name, catalogue, n=3)
    hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
    if _failures:
        broken = ", ".join(sorted(_failures))
        hint += f" (These files didn't load, and may hold the one you wanted: {broken}.)"
    raise KeyError(f"No adversary named {name!r} is defined in this package.{hint}")


def all_adversaries() -> dict[str, Adversary]:
    """Every defined adversary by name - a copy, so callers can't corrupt the cache."""
    return dict(_load())
