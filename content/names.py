"""Matching the name a character sheet writes to the name content registered under.

Sheets are typed by people. "I am your shield" for "I Am Your Shield" is the
kind of difference that happens constantly and means nothing - but a lookup keyed
on the literal string would miss, and a miss here is the worst possible failure
mode for this project: the card reports as *unimplemented* and silently never
fires. Nothing raises, nothing looks wrong, and the win rate quietly belongs to a
party missing a card.

So every registry keys on the canonical form of a name rather than the string as
written, and the name a sheet used is kept for display.

Deliberately conservative. Case and whitespace only:

    "I am your shield"   -> "i am your shield"
    "  Whirlwind "       -> "whirlwind"
    "Book  of Ava"       -> "book of ava"

Apostrophes, hyphens and spelling are left exactly as they are. Collapsing those
too would risk merging two genuinely different names, and a *wrong* match is far
worse than a miss - a miss is at least visible in the coverage report. That means
"Natures Tongue" still won't find "Nature's Tongue", which is the intended
trade: punctuation is a typo worth catching, capitalisation isn't.

`casefold` rather than `lower` so the comparison holds for non-ASCII names too.
"""


import re


def canonical(name: str) -> str:
    """The form a name is stored and looked up under."""
    return " ".join(name.split()).casefold()


# --- Parameterised names -----------------------------------------------------
#
# The SRD prints some adversary features with a number baked into the name:
# `Relentless (3)`, `Minion (3)`, `Horde (1d4+1)`. That is one feature with an
# argument, not three features - the Acid Burrower's `Relentless (3)` and the
# Construct's `Relentless (2)` are the same rule with a different X.
#
# So a stat block writes the name as printed, and the registry looks the content
# up under its **base** name. The argument isn't threaded through dispatch, which
# would mean changing every hook signature for a handful of features. The feature
# reads it off its own holder instead, via `content/registry.py`'s
# `feature_parameter` - which is where a feature's own business belongs.
#
# Deliberately narrow: a *trailing* parenthesised group only, so a name that
# merely contains a bracket somewhere isn't silently truncated.

_PARAMETERISED = re.compile(r"^(?P<base>.+?)\s*\((?P<argument>[^()]+)\)$")


def base_name(name: str) -> str:
    """`name` without its trailing parameter - "Relentless (3)" -> "Relentless".

    Returns the name unchanged when there is no parameter, so a caller can use
    it unconditionally. Any namespace prefix survives, since the pattern only
    ever strips from the end: "adversary:Relentless (3)" -> "adversary:Relentless".
    """
    matched = _PARAMETERISED.match(name.strip())
    return matched.group("base") if matched else name.strip()


def parameter(name: str) -> str | None:
    """The argument in `name`, or None if it has none.

    A string rather than an int, because not every parameter is one: `Horde
    (1d4+1)` carries a damage expression. Parsing it is the feature's job.
    """
    matched = _PARAMETERISED.match(name.strip())
    return matched.group("argument").strip() if matched else None


# --- Namespaces --------------------------------------------------------------
#
# Content named on a *character sheet* - domain cards, ancestries, communities,
# classes, subclasses - shares one flat namespace, because those names really
# are unique across the game. Content named in a *catalogue* is different: the
# SRD gives a Warhammer the feature "Heavy" and Chainmail Armor the feature
# "Heavy", and they are two separate pieces of content that happen to share a
# word. In a flat namespace the second registration would collide with the
# first, and the registry would refuse to load rather than let one shadow the
# other.
#
# So a catalogue's features are registered, dispatched and reported under a
# qualified name. Nobody types the prefix: the JSON author writes "Heavy" and
# the loader qualifies it from the catalogue the entry came from.

WEAPON = "weapon"
ARMOR = "armor"
ADVERSARY = "adversary"

QUALIFIER = ":"


def qualified(kind: str, name: str) -> str:
    """`name` in `kind`'s namespace - `qualified(ARMOR, "Heavy")` is "armor:Heavy".

    The separator is punctuation, which `canonical` deliberately leaves alone,
    so a qualified name can never fold into an unqualified one and two kinds
    can never fold into each other.
    """
    return f"{kind}{QUALIFIER}{name.strip()}"
