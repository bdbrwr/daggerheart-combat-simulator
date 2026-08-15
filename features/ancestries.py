"""Ancestry features.

Registered under the name a character sheet writes in its `ancestry` field, so
"Faerie" is the key even though the features themselves are called Luckbender and
Wings. An ancestry carries two features under that one name, which is the same
shape a class has.

Feature text is paraphrased in each docstring rather than quoted in full; the
verbatim wording is in `.reference/ancestries.json`.

## Features the sheet has already applied

A feature whose whole effect is a number the character sheet states has already
been worked into that number by the time a sheet is written, so running it again
here would count it twice. The Human's *High Stamina* is one of those. It's
declared under its own name at the bottom rather than left silent.

## Imperfect information is not modelled

The party is otherwise simulated playing well - a PC spends an Experience when it
helps, takes the lenient reading of a trigger. The Faerie's *Wings* is the
exception the user ruled on, and the reasoning generalises: the simulator can see
an adversary's attack roll and the target's Evasion, and a player cannot. Any
implementation would therefore spend the Stress on exactly the attacks worth
spending it on, which doesn't simulate the party more accurately - it simulates a
better party than the one at the table. Declining to model it is the honest
answer, and the coverage report carries the reasoning.

Dismissals here are the user's calls, not the assistant's. Anything not ruled on
stays `unimplemented`, which is the honest state and shows as such in coverage.
"""

import random

from content.aoe import Range, chance_within
from content.registry import (
    Fight,
    Holder,
    insignificant_combat_effect,
    no_combat_effect,
    reroll,
)
from content.rolls import experience_was_utilised

# --- Faerie ------------------------------------------------------------------

LUCKBENDER = "Luckbender"
LUCKBENDER_COST = 3

# Luckbender is only reached for at this much Hope or more. Its cost is the same
# 3 Hope every class's Hope feature charges, and those are generally the bigger
# swing in a fight - Frontline Tank clearing two Armor Slots, Hold Them Off
# reusing a roll on two more adversaries. Holding at 6 means the Hope feature is
# still affordable after Luckbender has been paid for, so this never starves it.
LUCKBENDER_HOPE_FLOOR = 6

FAERIE_GAPS = [
    "Wings, ruled as an insignificant combat effect and declared as such under "
    "its own name - a player can't know what a roll needs to beat, so there is "
    "no honest policy for when to mark the Stress",
    "Luckbender: 'once per session' is gated as once per long rest, the longest "
    "period the simulator tracks. Within a single fight the two are the same "
    "thing; across an adventuring day with rests in it, this is more generous "
    "than the card",
    "Luckbender: only the Duality Dice are meant to be rerolled, but the "
    "replacement re-makes the whole roll, so an Advantage or Help die is rolled "
    "again too",
]


@reroll("Faerie", unmodelled=FAERIE_GAPS)
def luckbender(faerie: Holder, roller: Holder, roll, remake, fight: Fight):
    """The Faerie's *Luckbender*.

    SRD: once per session, after you or a willing ally within Close range makes
    an action roll, you can spend 3 Hope to reroll the Duality Dice.

    Rescuing an ally is the interesting half, and it's why the reroll hook is
    scanned across the whole party rather than only the PC who rolled: the Faerie
    spends her own Hope on somebody else's dice.

    SIMULATION RULE - policy. Three conditions, all of them knobs:

      * Only a **failed** roll is rerolled. The card doesn't say so - it triggers
        on any action roll - but spending 3 Hope to improve a roll that already
        succeeded buys nothing the simulator can measure.
      * Only at `LUCKBENDER_HOPE_FLOOR` Hope or above, so this never spends the
        Hope a class feature was saving for. Those are generally worth more to a
        fight than one reroll.
      * For an **ally's** roll, whether they are within Close range is decided by
        the odds in `content/aoe.py` - no positions are tracked, so the area
        rule's Close fraction stands in as a probability. The Faerie's own roll
        needs no such check: "within Close range" qualifies the ally in the card
        text, not you.

    Declining is side-effect free, as the reroll contract requires: the Hope and
    the per-rest use are both claimed only once the reroll is definitely
    happening, and the range check comes before either.
    """
    if roll.is_success:
        return None
    if faerie.hope_marked < LUCKBENDER_HOPE_FLOOR:
        return None
    if not faerie.can_spend_hope(LUCKBENDER_COST):
        return None
    if not fight.can_use_once_per_rest(faerie, LUCKBENDER, long=True):
        return None

    if roller is not faerie:
        in_range = chance_within(Range.CLOSE, len(fight.living_adversaries))
        if random.random() >= in_range:
            return None

    # Claimed last - everything above could still have declined.
    if not fight.use_once_per_rest(faerie, LUCKBENDER, long=True):
        return None

    faerie.spend_hope(LUCKBENDER_COST)
    replacement = remake()
    fight.note(
        f"{faerie.name} bends {roller.name}'s luck "
        f"(Luckbender: {roll.total} rerolled to {replacement.total})"
    )
    return replacement


insignificant_combat_effect(
    "Wings",
    "Mark a Stress after an adversary attacks you to gain +2 Evasion against "
    "that attack. Used with perfect knowledge it would turn roughly one "
    "attack in ten into a miss, which is real - but a player never learns what "
    "the roll needed to beat, so at the table the Stress is spent blind. Spent "
    "blind on every attack it is close to worthless and plausibly negative: a "
    "Stress per incoming swing empties a 6-slot track in six hits, and an empty "
    "track makes the PC Vulnerable, which hands every adversary Advantage on "
    "every roll for the rest of the fight. Modelling it would mean choosing the "
    "attacks worth paying for, which is information the party doesn't have.",
)


# --- Human -------------------------------------------------------------------

ADAPTABILITY = "Adaptability"

# Adaptability is only used while this many Stress or fewer are marked. Marking
# the last Stress makes a PC Vulnerable - Advantage on every roll against them
# for the rest of the fight - so the last slots are worth more than a reroll.
ADAPTABILITY_MAX_STRESS_MARKED = 4

HUMAN_GAPS = [
    "High Stamina, ruled as having no combat effect because the sheet's Stress "
    "maximum already includes it, and declared as such under its own name",
    "Adaptability: only the Duality Dice are meant to be rerolled, but the "
    "replacement re-makes the whole roll, so an Advantage or Help die is rolled "
    "again too",
]


@reroll("Human", unmodelled=HUMAN_GAPS)
def adaptability(human: Holder, roller: Holder, roll, remake, fight: Fight):
    """The Human's *Adaptability*.

    SRD: when you fail a roll that utilized one of your Experiences, you can mark
    a Stress to reroll.

    Strictly about your own roll - "when *you* fail" - so this declines for an
    ally, which is what separates it from Luckbender above.

    Whether the roll utilised an Experience is remembered per fight rather than
    threaded through every attack signature; see `content/rolls.py` for why. Both
    ways of paying for an Experience count, the Hope in `combat/policy.py` and
    the Stress in School of Knowledge's *Adept*.

    SIMULATION RULE - policy. The only departure from the card as written is a
    ceiling on how much Stress a PC will spend this way: it fires while
    `ADAPTABILITY_MAX_STRESS_MARKED` or fewer are marked, keeping the last slots
    back. Marking the last Stress makes a PC Vulnerable for the rest of the
    fight, which costs far more than one rerolled attack is worth.

    The Stress is a voluntary cost, so it goes through `spend_stress`: per the
    SRD a move requiring Stress simply can't be used when Stress is full, and
    must never fall through to marking HP the way forced Stress does.
    """
    if roller is not human:
        return None
    if roll.is_success:
        return None
    if not experience_was_utilised(human, fight):
        return None
    if human.stress_marked > ADAPTABILITY_MAX_STRESS_MARKED:
        return None

    # Claimed last, and the one call that can still refuse - a full Stress track
    # takes the move off the table entirely.
    if not human.spend_stress(1):
        return None

    replacement = remake()
    fight.note(
        f"{human.name} adapts (Adaptability: {roll.total} rerolled to "
        f"{replacement.total})"
    )
    return replacement


no_combat_effect(
    "High Stamina",
    "An additional Stress slot at character creation. A character sheet "
    "states its Stress maximum outright, so the extra slot is already in that "
    "number - applying it again at simulation time would count it twice.",
)


# --- Ruled out ---------------------------------------------------------------

no_combat_effect("Fungril", "Ruled as having no effect on the combat simulation.")
