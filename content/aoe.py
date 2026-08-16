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

import random
from enum import Enum

from content.names import canonical

# How many adversaries count as "a lot" for a Melee area effect, which reaches
# 3 at or above this and 2 below it - before the spread roll below takes one off.
# A knob, not a rule.
MANY_ADVERSARIES = 6

# Each band's reach is rolled rather than fixed, because a table's spread isn't
# fixed either: the same four adversaries are sometimes bunched and sometimes
# strung out, and a band that always delivered its best case would price every
# area ability off its best case. Written as one-in-N divisors, the form the
# rule was stated in, so the code and SIMULATION-RULES.md read the same way.
FAR_FALLS_SHORT_ONE_IN = 4  # Far misses one adversary
CLOSE_HELD_TO_ITS_CAP_ONE_IN = 2  # Close is held to CLOSE_CAP
VERY_CLOSE_SPREADS_ONE_IN = 10  # Very Close is *not* held to VERY_CLOSE_CAP
MELEE_CLUSTERS_ONE_IN = 2  # Melee gets its higher count rather than one fewer

CLOSE_CAP = 3
VERY_CLOSE_CAP = 2


class Range(Enum):
    """The SRD's range bands, as far as an area effect cares about them."""

    MELEE = "Melee"
    VERY_CLOSE = "Very Close"
    CLOSE = "Close"
    FAR = "Far"


def band_named(name: str) -> Range:
    """The `Range` a printed band names, matched canonically.

    Catalogues are typed by hand and write a band the way the book prints it, so
    "very close" has to find `VERY_CLOSE` - the same canonical matching every
    other registry in the project uses, and for the same reason: a lookup that
    missed on capitalisation would not fail loudly.

    Raises on anything that isn't one of the four. A band nobody recognises would
    otherwise have to become a default, and the default would silently change how
    many combatants an area effect reaches.
    """
    for band in Range:
        if canonical(band.value) == canonical(str(name)):
            return band
    raise ValueError(
        f"{name!r} is not a range band. Expected one of "
        + ", ".join(repr(band.value) for band in Range)
        + "."
    )


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
#
# KNOWN OUT OF STEP, awaiting a ruling. The spread rolls above cut the expected
# reach of every band, and these three numbers have deliberately not been moved
# with them, because they answer a different question for different content -
# "is one named ally close by?" (Luckbender) rather than "how much of the field
# does this sweep?". Re-deriving them from the new expected reach would make Far
# n-dependent (1 - 0.25/n) rather than certain, and would change how often
# Luckbender can rescue an ally, which is a balance decision rather than a
# tidy-up. Recorded here so the gap is visible rather than silent.
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

    Melee is the odd one out. Its rule is a count rather than a share of the
    field, so there is no fraction to read off and it is worked out from the
    field size instead, capped at certainty.

    That count is now **rolled**, so its *expected* value is used rather than
    `targets_reached` itself: asking the roller would hand back one sample of a
    random variable and call it a likelihood, which would make the same question
    answer differently each time it was asked. The expectation is the higher
    count less a half, since the spread roll is an even one.

    Returns 0.0 on an empty field: there is nothing to measure against, and
    content should decline rather than treat that as certainty.
    """
    if adversaries <= 0:
        return 0.0
    if band in _BAND_SHARE:
        return _BAND_SHARE[band]
    best = 3 if adversaries >= MANY_ADVERSARIES else 2
    return min((best - 0.5) / adversaries, 1.0)


def targets_reached(band: Range, adversaries: int) -> int:
    """How many of `adversaries` an area effect at `band` catches.

    **Rolled, not fixed.** Each band has a base reach from the field size and
    then a spread roll that can take it down - so calling this twice with the
    same field can give two answers, on purpose. A fight is seeded, so a run is
    still reproducible; what isn't reproducible is one ability always finding
    the field arranged the way it likes.

    Never more than there are, and never fewer than one - an area effect that
    caught nobody at all would be a rounding artefact rather than a decision.
    """
    if adversaries <= 0:
        return 0

    if band is Range.FAR:
        # Everyone, but one short a quarter of the time. Far used to mean
        # "the whole field, always", which made every Far ability worth its
        # ceiling on every cast.
        short = random.randint(1, FAR_FALLS_SHORT_ONE_IN) == FAR_FALLS_SHORT_ONE_IN
        reached = adversaries - 1 if short else adversaries
    elif band is Range.CLOSE:
        # Three quarters and never all of them, and held to CLOSE_CAP half the
        # time - so the band's advantage over Very Close only really shows on a
        # big field, and even there not every time.
        reached = min(adversaries * 3 // 4, adversaries - 1)
        capped = (
            random.randint(1, CLOSE_HELD_TO_ITS_CAP_ONE_IN)
            == CLOSE_HELD_TO_ITS_CAP_ONE_IN
        )
        if capped:
            reached = min(reached, CLOSE_CAP)
    elif band is Range.VERY_CLOSE:
        # A third, held to VERY_CLOSE_CAP unless the field is unusually spread
        # out - which is the one-in-ten case, not the common one.
        reached = adversaries // 3
        spread = (
            random.randint(1, VERY_CLOSE_SPREADS_ONE_IN) == VERY_CLOSE_SPREADS_ONE_IN
        )
        if not spread:
            reached = min(reached, VERY_CLOSE_CAP)
    else:
        # 3 on a crowded field and 2 otherwise, less one unless they're bunched.
        # So Melee below MANY_ADVERSARIES is now 1 or 2 rather than a flat 2.
        clustered = (
            random.randint(1, MELEE_CLUSTERS_ONE_IN) == MELEE_CLUSTERS_ONE_IN
        )
        best = 3 if adversaries >= MANY_ADVERSARIES else 2
        reached = best if clustered else best - 1

    return min(max(reached, 1), adversaries)
