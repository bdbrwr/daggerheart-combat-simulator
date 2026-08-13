"""How many adversaries an area effect actually catches.

Nothing in this simulator tracks position, so an ability that hits "all targets
within X range" would hit everything, every time - far more generous than a
table, where the GM places adversaries and the spread of a fight is what makes
an area effect good or wasted. Instead the range band caps how many can be
caught. The rule, the numbers and the reasoning are in SIMULATION-RULES.md;
this is the arithmetic.

The cap is the **total** number of adversaries caught, uniformly. An ability
that extends an attack that already hit someone counts that adversary among
them, which is why Whirlwind reaches nobody new until a fight has six
adversaries in it. That's the intended consequence of a uniform rule.
"""

from enum import Enum

# How many adversaries count as "a lot" for a Melee area effect, which reaches
# 2 below this and 3 at or above it. A knob, not a rule.
MANY_ADVERSARIES = 6


class Range(Enum):
    """The SRD's range bands, as far as an area effect cares about them."""

    MELEE = "Melee"
    VERY_CLOSE = "Very Close"
    CLOSE = "Close"
    FAR = "Far"


def targets_reached(band: Range, adversaries: int) -> int:
    """How many of `adversaries` an area effect at `band` catches.

    Never more than there are, and never fewer than one - an area effect that
    caught nobody at all would be a rounding artefact rather than a decision.
    """
    if adversaries <= 0:
        return 0

    if band is Range.FAR:
        reached = adversaries
    elif band is Range.CLOSE:
        # Three quarters, and never all of them.
        reached = min(adversaries * 3 // 4, adversaries - 1)
    elif band is Range.VERY_CLOSE:
        reached = adversaries // 3
    else:
        reached = 3 if adversaries >= MANY_ADVERSARIES else 2

    return min(max(reached, 1), adversaries)
