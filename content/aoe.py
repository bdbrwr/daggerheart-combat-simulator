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


def reach_outcomes(band: Range, combatants: int) -> list[tuple[float, int]]:
    """Every reach `band` can produce over a field this size, with its odds.

    **One definition of the band rules, read two ways.** `targets_reached` draws
    from it and `chance_within` takes its expectation, so the count and the
    probability can never disagree about what a band means. They used to be two
    sets of numbers - a rolled count here and three hand-written shares beside
    it - and they drifted apart the moment the spread rolls were added.

    Each outcome is already floored at 1 and capped at the field size, so no
    caller has to re-apply either. The floor is why an area effect never catches
    nobody: a sweep that fizzled entirely would be a rounding artefact rather
    than a decision.
    """
    if combatants <= 0:
        return [(1.0, 0)]

    def clamped(reached: int) -> int:
        return min(max(reached, 1), combatants)

    if band is Range.FAR:
        # Everyone, but one short a quarter of the time. Far used to mean
        # "the whole field, always", which made every Far ability worth its
        # ceiling on every cast.
        short = 1 / FAR_FALLS_SHORT_ONE_IN
        return [(short, clamped(combatants - 1)), (1 - short, clamped(combatants))]

    if band is Range.CLOSE:
        # Three quarters and never all of them, and held to CLOSE_CAP half the
        # time - so the band's advantage over Very Close only really shows on a
        # big field, and even there not every time.
        base = min(combatants * 3 // 4, combatants - 1)
        held = 1 / CLOSE_HELD_TO_ITS_CAP_ONE_IN
        return [(held, clamped(min(base, CLOSE_CAP))), (1 - held, clamped(base))]

    if band is Range.VERY_CLOSE:
        # A third, held to VERY_CLOSE_CAP unless the field is unusually spread
        # out - which is the one-in-ten case, not the common one.
        base = combatants // 3
        spread = 1 / VERY_CLOSE_SPREADS_ONE_IN
        return [
            (spread, clamped(base)),
            (1 - spread, clamped(min(base, VERY_CLOSE_CAP))),
        ]

    # Melee: 3 on a crowded field and 2 otherwise, less one unless they're
    # bunched. So Melee below MANY_ADVERSARIES is 1 or 2 rather than a flat 2.
    best = 3 if combatants >= MANY_ADVERSARIES else 2
    clustered = 1 / MELEE_CLUSTERS_ONE_IN
    return [(clustered, clamped(best)), (1 - clustered, clamped(best - 1))]


def chance_within(band: Range, others: int) -> float:
    """The odds that one particular other combatant is within `band`.

    SIMULATION RULE - policy. It exists for content whose condition is that one
    specific other person is in range rather than that an area is swept: the
    Faerie's Luckbender can rescue "a willing ally within Close range", and with
    no positions tracked the simulator has to put a number on that.

    **Derived from the area rule rather than written beside it.** If a band
    reaches `r` of a field of `n`, then any one member of that field is within
    it `r / n` of the time. The reach is rolled, so the *expectation* is what's
    divided - asking `targets_reached` would hand back one sample of a random
    variable and call it a likelihood, which would make the same question answer
    differently each time it was asked.

    `others` is the field the question is asked about, and it is not always the
    adversaries: "is my ally close by?" is measured over the rest of the party,
    since that is who the band has to reach. Returns 0.0 on an empty field -
    there is nothing to measure against, and content should decline rather than
    treat that as certainty.
    """
    if others <= 0:
        return 0.0
    expected = sum(
        probability * reached for probability, reached in reach_outcomes(band, others)
    )
    return min(expected / others, 1.0)


def targets_reached(band: Range, adversaries: int) -> int:
    """How many of `adversaries` an area effect at `band` catches.

    **Rolled, not fixed.** Each band has a base reach from the field size and
    then a spread roll that can take it down - so calling this twice with the
    same field can give two answers, on purpose. A fight is seeded, so a run is
    still reproducible; what isn't reproducible is one ability always finding
    the field arranged the way it likes.

    Never more than there are, and never fewer than one; `reach_outcomes` holds
    both the band rules and those bounds.
    """
    if adversaries <= 0:
        return 0

    outcomes = reach_outcomes(band, adversaries)
    draw = random.random()
    cumulative = 0.0
    for probability, reached in outcomes:
        cumulative += probability
        if draw < cumulative:
            return reached
    # Only reachable on floating-point remainder, where the last outcome is the
    # one the draw fell inside.
    return outcomes[-1][1]
