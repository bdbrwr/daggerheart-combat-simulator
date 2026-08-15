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
    """The adversaries in an area that a PC's roll actually beat.

    Each is checked against its own Difficulty, which is what "targets you
    succeeded against" means when one roll faces several. A critical beats all
    of them, since a critical succeeds regardless of Difficulty.
    """
    return [
        target
        for target in targets
        if roll.is_critical or roll.total >= target.difficulty
    ]


def targets_hit(roll, targets: list) -> list:
    """The PCs in an area that an adversary's roll actually hit.

    The mirror of `targets_beaten`, and separate from it for the reason
    `dice/d20.py` gives for naming its field `evasion` rather than `difficulty`:
    a roll against a PC is measured against Evasion, and the two are different
    numbers on different sheets. One function taking whichever attribute happened
    to exist would be the kind of cleverness that hides a mismatch.
    """
    return [
        target for target in targets if roll.is_critical or roll.total >= target.evasion
    ]


# The share of the field each band covers, as a probability. These are the same
# numbers `targets_reached` below works in - keep the two in step by hand. They
# are not derived from it, and the reason is the floor: `targets_reached` never
# returns zero, because an area effect that caught nobody would be a rounding
# artefact rather than a decision. As a *count* that floor is right. As a
# *probability* it is badly wrong - against a single adversary it would say any
# given ally is certainly within Close range.
_BAND_SHARE = {
    Range.FAR: 1.0,
    Range.CLOSE: 3 / 4,
    Range.VERY_CLOSE: 1 / 3,
}


def chance_within(band: Range, adversaries: int) -> float:
    """The odds that one particular other combatant is within `band`.

    The area rule already answers "how much of the field does this band cover?".
    This reuses the same shares as a *probability* for a single named combatant:
    if an area effect at Close range reaches three quarters of the field, then
    any one combatant is within Close range about three quarters of the time.

    SIMULATION RULE - policy. It exists for content whose condition is that one
    specific other person is in range rather than that an area is swept: the
    Faerie's Luckbender can rescue "a willing ally within Close range", and with
    no positions tracked the simulator has to put a number on that.

    Melee is the odd one out. Its rule is a flat count - 2 adversaries, or 3 in a
    crowd - rather than a share of the field, so there is no fraction to read off
    and it is worked out from the field size instead, capped at certainty.

    Returns 0.0 on an empty field: there is nothing to measure against, and
    content should decline rather than treat that as certainty.
    """
    if adversaries <= 0:
        return 0.0
    if band in _BAND_SHARE:
        return _BAND_SHARE[band]
    return min(targets_reached(Range.MELEE, adversaries) / adversaries, 1.0)


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
