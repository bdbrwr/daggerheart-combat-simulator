"""Whether the party walked into this fight rested, and what that refreshes.

A great deal of Daggerheart content is limited to once per short rest, once per
long rest, or once per session. The obvious shortcut in a single-fight simulator
is to treat "once per rest" as "once per fight" - every fight starts fresh. That
would quietly make a party stronger than it is, because the interesting question
is how they hold up across an adventuring day, not how they handle one fight
with everything available.

So rest state is encounter setup, sitting alongside `starting_fear` and
`starting_spotlight`: it describes the condition the party walks in with. Running
several encounters in sequence with no rest between them is the point.

SIMULATION RULE - simplification. NONE is conservative: with no state carried
between encounters, the simulator can't know which per-rest abilities a party
already spent, so it assumes all of them. That makes a no-rest encounter harder
than it might really be. Tracking real carry-over needs a campaign-level runner
that doesn't exist yet.
"""

from enum import Enum


class Rest(Enum):
    """What the party got before this fight."""

    LONG = "long"
    SHORT = "short"
    NONE = "none"

    @property
    def refreshes_short(self) -> bool:
        """Whether once-per-short-rest abilities are available."""
        return self is not Rest.NONE

    @property
    def refreshes_long(self) -> bool:
        """Whether once-per-long-rest abilities are available.

        A short rest doesn't refresh them, which is the whole distinction.
        """
        return self is Rest.LONG
