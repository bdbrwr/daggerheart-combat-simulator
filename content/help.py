"""Help an Ally - the party move where one PC's Hope improves another's roll.

Not content. Nothing on a character sheet grants this: every PC can do it, the
same way every PC can swing a weapon, so it lives beside the dispatch rather than
in `domain_cards/` or `features/`. What content *can* do is add to a help that is
already happening, which is the `help_bonus` hook in `content/registry.py`.

## Why it lives in content/ and not in combat/policy.py

The turn policy is where a PC's *own* choices are made, and helping is not one of
them - it is a reaction to somebody else's roll, and it costs the helper nothing
but the Hope. So it has to be reachable from every place an action roll is made,
and several of those are domain cards. `combat/` may import `content/` and not
the other way round, which settles where it goes.

## The SRD, and what it already found here

    "Spend a Hope to give an ally an advantage die on their roll. Multiple
    players can spend Hope to help the same acting player, but that player only
    adds the highest result to their final total."

`dice/duality.py` has modelled this since it was written - `roll_duality` takes
`help_dice`, rolls each, and adds only the best, and it deliberately does **not**
cancel against Disadvantage the way the acting player's own advantage die does.
What was missing was anybody calling it: no simulated PC had ever helped anyone.
So this module is the move, not the mechanic.
"""

import random
from typing import NamedTuple

from .registry import Fight, Holder, total_help_bonus
from .rolls import EXPERIENCE_HOPE_FLOOR

__all__ = ["HELP_DIE", "Help", "NO_HELP", "help_with_roll"]

# The die an ally rolls when they help. The SRD's advantage die, which is a d6
# everywhere it appears.
HELP_DIE = 6


class Help(NamedTuple):
    """What an ally's help contributes to the roll about to be made.

    Two parts rather than one, because they reach `roll_duality` differently:
    the dice are a pool of their own that resolves to its best single result,
    and the bonus is a flat add folded into the roll's modifier.
    """

    dice: list[int]
    bonus: int


NO_HELP = Help(dice=[], bonus=0)


def help_with_roll(roller: Holder, fight: Fight = None) -> Help:
    """Let one ally spend a Hope to help `roller`, and say what it bought.

    Called once, immediately before an action roll is made, from every site that
    makes one - so **being asked is the commitment**, the same contract
    `hope_die_for` and `total_roll_bonus` keep. The Hope is spent here, and a
    reroll re-makes the dice without asking again.

    Returns `NO_HELP` when there is no fight to read a party out of, which is the
    case in a test that resolves an attack on its own.

    SIMULATION RULE - policy, ruled. Two decisions, both the user's:

    * **An ally helps once their Hope is plentiful** - `EXPERIENCE_HOPE_FLOOR`
      or more banked. That is the same number the Experience spend reads, and
      deliberately the same constant rather than a second one: the question is
      the same one both times, which is whether this PC has Hope to spare for
      something that only improves a roll.
    * **Exactly one ally helps.** Only the single best help die counts, so a
      second helper spends a whole Hope for the chance of beating one d6 - and
      that is a fact about the rule, readable off the page, rather than a
      statistic anybody has to work out. The ally with the **most** banked Hope
      is the one who pays, so the cost lands where it is least missed.

    Ties on Hope are broken at random rather than by party order, for the reason
    `_next_pc` picks at random: the order an encounter listed the party in
    carries no meaning and must never decide an outcome.
    """
    if fight is None:
        return NO_HELP

    willing = [
        ally
        for ally in fight.conscious_party
        if ally is not roller and ally.hope_marked >= EXPERIENCE_HOPE_FLOOR
    ]
    if not willing:
        return NO_HELP

    most = max(ally.hope_marked for ally in willing)
    candidates = [ally for ally in willing if ally.hope_marked == most]
    # Drawn from the global RNG only when there is genuinely a choice, exactly as
    # `_party_offers` skips its shuffle: a party with one obvious helper must not
    # shift the dice for every roll of every fight.
    helper = candidates[0] if len(candidates) == 1 else random.choice(candidates)

    helper.spend_hope(1)
    fight.note(f"{helper.name} spends a Hope to help {roller.name}")

    # Content the *helper* carries that adds to the roll they are helping with -
    # the Bone card Tactician lends one of its own Experiences. Asked after the
    # Hope is spent, so it only ever fires on help that is really happening.
    # Nothing here knows what any of it is.
    return Help(dice=[HELP_DIE], bonus=total_help_bonus(helper, roller, fight))
