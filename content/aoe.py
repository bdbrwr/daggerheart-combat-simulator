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


def targets_in_area(band: Range, adversaries: list) -> list:
    """Which adversaries an area effect at `band` catches, most wounded first.

    Most wounded first is the focus-fire policy applied to an area, and it also
    keeps the choice off the order an encounter happened to spawn its
    adversaries in - order that carries no meaning must never decide an outcome.
    """
    reach = targets_reached(band, len(adversaries))
    return sorted(adversaries, key=lambda adversary: adversary.hp_marked, reverse=True)[
        :reach
    ]


def area_difficulty(targets: list) -> int:
    """The Difficulty a roll made against a whole area is measured against.

    An attack "against all adversaries within Close range" is one roll resolved
    separately against each target, so it has no single Difficulty of its own -
    and yet the spotlight rules need to know whether the roll *succeeded*. The
    lowest Difficulty in the area answers that: you either beat somebody or you
    beat nobody. See SIMULATION-RULES.md.
    """
    return min((target.difficulty for target in targets), default=0)


def targets_beaten(roll, targets: list) -> list:
    """The targets in an area that the roll actually beat.

    Each is checked against its own Difficulty, which is what "targets you
    succeeded against" means when one roll faces several. A critical beats all
    of them, since a critical succeeds regardless of Difficulty.
    """
    return [
        target
        for target in targets
        if roll.is_critical or roll.total >= target.difficulty
    ]


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
