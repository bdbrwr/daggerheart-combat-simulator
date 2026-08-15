"""Temporary conditions, and the moments at which they end.

Daggerheart's conditions are states a combatant is in for a while, and the "for a
while" is as much a part of the rule as the effect - `Vulnerable until they next
act` and `Vulnerable until the scene ends` are very different things attached to
the same word. So a condition here is a small record carrying both.

## What is actually modelled

**Vulnerable only.** It hands every roll against its holder Advantage, which is
a real and large effect, so content that applies it has something to apply.

**Restrained is ruled to have no combat effect here.** Being Restrained stops a
combatant moving and does nothing else, and no movement is modelled - so a
feature that Restrains is implemented for whatever *else* it does, with the
Restrain declared as a gap where it's registered. That is the user's ruling, and
it is about this simulation rather than about the game: at a table, being held in
place matters a great deal.

The rest of the SRD's conditions - Hidden, On Fire, Stunned - have no
representation at all and no content applies one yet.

## Why `end` is a callable

Because the answer isn't always about time. A condition may end when its holder
next acts, or when the GM pays to shake it off, and a future one may end on a
successful roll to break free. A predicate asked at each opportunity covers all
of those without this module learning what any particular condition is.

Conditions live on the `FightState` for the length of one fight, keyed by holder
and name, the same way per-fight tokens do.
"""

from dataclasses import dataclass
from typing import Callable

VULNERABLE = "Vulnerable"
RESTRAINED = "Restrained"

# The moments a condition is offered a chance to end. The fight loop announces
# these; a condition's `end` decides whether this one is its cue.
WHEN_THEY_ACT = "when they act"
ON_A_GM_TURN = "on a GM turn"


@dataclass(frozen=True)
class Condition:
    """One temporary condition sitting on one combatant.

    `end` is asked at every moment the loop announces and returns whether the
    condition is over. None means it lasts the rest of the fight, which is what
    "until the scene ends" comes to here.

    `effect` is for a condition whose effect isn't already asked for somewhere
    else. Nothing sets it yet: the only modelled condition is Vulnerable, and the
    one place that cares - whether an attack has Advantage - asks
    `FightState.is_vulnerable` directly. It is here because the shape was asked
    for, and it is worth knowing it is unused rather than discovering it half
    wired in.
    """

    name: str
    end: Callable[..., bool] | None = None
    effect: Callable | None = None


def when_they_act(holder, fight, moment: str) -> bool:
    """Ends the next time the conditioned combatant takes the spotlight.

    The SRD's "until they next act". The loop announces the moment *after* the
    turn resolves, so a combatant is still conditioned for the action that shakes
    it off - which is the point of being knocked over.
    """
    return moment == WHEN_THEY_ACT


def when_the_gm_pays(holder, fight, moment: str) -> bool:
    """Ends when the GM spends a Fear on their turn to clear it.

    The default for a condition the *party* puts on an adversary, and the
    simulator's long-standing stand-in for conditions it doesn't model in full:
    several of these are written to end exactly this way (Slumber says so
    outright), so draining the pool is close to what the condition costs the GM
    side, and it lands in a currency already tracked carefully.

    A GM who can't afford it doesn't clear it, which is the honest consequence -
    and the reason the old version of this rule, which charged the Fear at the
    moment the condition landed, understated conditions applied while the pool
    was empty.
    """
    if moment != ON_A_GM_TURN:
        return False
    return fight.spend_fear(1)
