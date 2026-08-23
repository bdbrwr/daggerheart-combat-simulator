"""Temporary conditions, and the moments at which they end.

Daggerheart's conditions are states a combatant is in for a while, and the "for a
while" is as much a part of the rule as the effect - `Vulnerable until they next
act` and `Vulnerable until the scene ends` are very different things attached to
the same word. So a condition here is a small record carrying both.

## What is actually modelled

**Vulnerable**, which hands every roll against its holder Advantage - a real and
large effect, so content that applies it has something to apply.

**A condition that hobbles one trait**, through `disadvantage_on`. The SRD writes
several of these without giving them a keyword - the Archer Guard's Hobbling Shot
leaves its target "with disadvantage on Agility Rolls until they clear at least
1 HP" - so the field is on `Condition` rather than being a named condition of its
own, and whoever applies one names it whatever the page calls it.

**Restrained is recorded, and does nothing by itself.** Being Restrained stops a
combatant moving, and no movement is modelled - so the condition still has no
effect of its own here, exactly as ruled. What changed is that it is now *written
down* when a feature applies one, because other content asks about it: the Jagged
Knife Kneebreaker's `I've Got 'Em` doubles the damage its allies deal to
creatures it has Restrained, and a condition nobody recorded is one nothing can
key on. So a feature that Restrains applies the record, with its own printed way
out, and the movement half stays declared as a gap where it's registered.

**Hidden**, which is Vulnerable's mirror: every roll made *against* a hidden
combatant has Disadvantage. Ruled by the user rather than read off any one
feature, since the two features that apply it both say only "become Hidden". A
condition may also carry `found_by`, the action roll somebody else can spend
their spotlight on to end it - the Sylvan Soldier's Blend In prints one and the
Shadow's Cloaked does not.

The rest of the SRD's conditions - On Fire, Stunned - have no representation at
all and no content applies one yet.

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

# **Hidden**, which is modelled: every roll made *against* a hidden combatant has
# Disadvantage. The exact mirror of Vulnerable, pointed the other way, and ruled
# by the user rather than read off any one feature's text - the Sylvan Soldier's
# Blend In and the Jagged Knife Shadow's Cloaked both say only "become Hidden",
# and this is what being Hidden is worth.
#
# It was previously in the list of conditions with no representation at all,
# which is why Cloaked used to model only the Advantage its own text spelled out
# and declared the Hidden itself as a gap. That gap is closed.
HIDDEN = "Hidden"

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

    `disadvantage_on` names the traits whose rolls this condition hobbles, in the
    lowercase spelling a character sheet writes them - `("agility",)`. Data
    rather than a callable, unlike its two neighbours, because the effect isn't
    something that *happens* at an announced moment: it is a standing fact about
    every roll of that trait, read where the roll is made. `FightState`
    answers for it, the way it already answers for Vulnerable.

    `source` is whoever applied it, when that matters. Most content only asks
    whether a condition is present, but some asks whose it is: the Jagged Knife
    Kneebreaker doubles damage against creatures **it** has Restrained, which is
    a different question from whether the target is held at all. Read through
    `FightState.condition_on` rather than `has_condition`.

    `found_by` is the trait and Difficulty of an action roll **somebody else**
    spends their spotlight on to end this - `("instinct", 14)` for the Sylvan
    Soldier's Blend In, which lifts when "a PC succeeds on an Instinct Roll (14)
    to find them". Data rather than a callable for `disadvantage_on`'s reason:
    what it describes is not something that happens at an announced moment but a
    standing fact about a roll somebody may choose to make, read where that
    choice is made (`combat/policy.py`).

    Distinct from `end`, which the *holder* is offered at each announced moment
    and which costs nobody a turn. This one costs a whole action roll, so a
    condition carrying it is one the other side has to spend something on. A
    condition with no `found_by` simply offers no such roll - the Shadow's
    Cloaked prints none, and correctly cannot be searched out.
    """

    name: str
    end: Callable[..., bool] | None = None
    effect: Callable | None = None
    disadvantage_on: tuple[str, ...] = ()
    source: object | None = None
    found_by: tuple[str, int] | None = None


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
