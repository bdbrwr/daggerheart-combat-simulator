"""Community features.

Registered under the name a character sheet writes in its `community` field, so
"Orderborne" is the key even though the feature itself is called Dedicated.
Content dispatch scans everything a sheet names, not just the domain-card
loadout, which is what lets a community reach into a fight at all.

Card and feature text is paraphrased in each docstring rather than quoted in
full; the verbatim wording is on the SRD site.
"""

from content.registry import (
    Fight,
    Holder,
    hope_die,
    no_combat_effect,
    on_roll,
    roll_bonus,
)
from dice.duality import DualityOutcome

ORDERBORNE_HOPE_DIE = 20


@hope_die(
    "Orderborne",
    unmodelled=[
        "the three sayings themselves - which principle is being embodied is "
        "a fiction call, so the feature is taken as always applicable",
    ],
)
def dedicated(holder: Holder, fight: Fight) -> int | None:
    """Orderborne's *Dedicated*: once per rest, roll a d20 as your Hope Die.

    Not a flat bonus. Swapping d12 for d20 on the Hope side raises the total,
    and - because the Hope die is what decides Hope vs Fear - it also makes a
    roll with Hope far more likely, which keeps the spotlight with the party.
    It cuts the critical rate as a side effect, since a Crit is the two dice
    matching and a d20 matches a d12 less often.

    SIMULATION RULE - policy. Whether a principle applies to the current action
    is a fiction call a simulator can't make, so this assumes one always does
    and spends the use on the first action roll of the fight. That's the
    optimistic reading, and it makes the feature worth slightly more here than
    at a table where the GM might not buy the justification.
    """
    if not fight.use_once_per_rest(holder, "Dedicated"):
        return None
    fight.note(f"{holder.name} is Dedicated - rolling a d20 as their Hope Die")
    return ORDERBORNE_HOPE_DIE


KNOW_THE_TIDE = "Know the Tide"


@on_roll("Seaborne")
def know_the_tide_gain(holder: Holder, roll, fight: Fight) -> None:
    """Seaborne's *Know the Tide*, first half: a token for every roll with Fear.

    Held up to the PC's level. A run of bad luck is what stocks it, which makes
    it a quiet counterweight to the spotlight swinging to the GM.
    """
    if roll.outcome is not DualityOutcome.FEAR:
        return
    if fight.add_token(holder, KNOW_THE_TIDE, cap=holder.level):
        fight.note(f"{holder.name} reads the tide (token {fight.token_count(holder, KNOW_THE_TIDE)})")


@roll_bonus("Seaborne")
def know_the_tide_spend(holder: Holder, target, fight: Fight) -> int:
    """Seaborne's *Know the Tide*, second half: spend any number of tokens for +1 each.

    SIMULATION RULE - policy. Spends everything held. The rules let a player
    hold tokens back for a roll that matters more, but a simulator has no way to
    know which roll that is, and tokens are worth nothing at the end of a fight -
    so hoarding them would only ever lose value. A knob if it turns out to
    matter.
    """
    spent = fight.spend_tokens(holder, KNOW_THE_TIDE, fight.token_count(holder, KNOW_THE_TIDE))
    if spent:
        fight.note(f"{holder.name} spends {spent} tide token(s) for +{spent}")
    return spent


# Dismissals below are the user's calls, not the assistant's - whether a piece
# of content can affect a fight is a judgement about the game, and it's theirs
# to make. Seaborne is why that matters: it reads like pure flavour and turns
# out to place tokens that buy a bonus to attack rolls.
no_combat_effect("Wildborne", "Ruled as having no effect on the combat simulation.")
no_combat_effect("Wanderborne", "Ruled as having no effect on the combat simulation.")
