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

# Poison is a *family* rather than one condition: the SRD prints several, and
# they share a name while differing in both what they do and how they end. The
# Giant Scorpion's ends on a Knowledge Roll at 16 and costs a Stress before an
# action roll; the Druid beastforms' do something else and end another way. So
# the name is shared - a target is Poisoned or not - and each source supplies its
# own `end` and `effect`.
POISONED = "Poisoned"

# The moments a condition is announced at. A condition's `end` decides whether
# one of them is its cue to lift, and its `effect` whether one is its cue to
# fire. The same vocabulary serves both, so a condition that costs something at a
# particular moment and one that ends at a particular moment are written alike.
WHEN_THEY_ACT = "when they act"
ON_A_GM_TURN = "on a GM turn"
BEFORE_AN_ACTION_ROLL = "before an action roll"


@dataclass(frozen=True)
class Condition:
    """One temporary condition sitting on one combatant.

    `end` is asked at every moment the loop announces and returns whether the
    condition is over. None means it lasts the rest of the fight, which is what
    "until the scene ends" comes to here.

    `effect` is for a condition that *does* something at an announced moment,
    rather than one whose effect is already asked for somewhere else. It takes
    the same `(holder, fight, moment)` as `end` and returns nothing, and it
    checks the moment itself for the same reason `end` does.

    Vulnerable doesn't use it - the one place that cares whether an attack has
    Advantage asks `FightState.is_vulnerable` directly. The Giant Scorpion's
    Poison is the first that does: it costs its holder a Stress on a d6 of 4 or
    lower before each action roll, which nothing else in the simulator was
    already asking about.
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


def until_they_clear_hp(marked_when_applied: int):
    """Ends once the conditioned combatant has cleared any of the HP they had.

    The SRD's "until they clear at least 1 HP", which the Dire Wolf's Hobbling
    Strike uses. Unlike the other two enders this is *stateful* - "clear an HP"
    is measured against how much was marked when the condition landed - so it is
    a factory returning the predicate rather than a predicate itself.

    Reading it against the mark at application time rather than against any later
    change means a hit that marks *more* HP doesn't accidentally end it, and a
    heal that undoes any part of the damage does. Checked at whichever moments
    the loop announces, so it can outlast the heal by up to one of them; that is
    a granularity the condition machinery has everywhere, not something specific
    to this ender.
    """

    def ended(holder, fight, moment: str) -> bool:
        return holder.hp_marked < marked_when_applied

    return ended


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
