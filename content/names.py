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


def canonical(name: str) -> str:
    """The form a name is stored and looked up under."""
    return " ".join(name.split()).casefold()
