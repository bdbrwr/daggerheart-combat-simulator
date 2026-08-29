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

**On Fire**, which burns whoever carries it each time they act. Modelled because
the card applying it prints the whole rule itself - Arcana's *Cinder Grasp* says
"when a creature acts while On Fire, they must take an extra 2d6 magic damage if
they are still On Fire at the end of their action" - so unlike the conditions
that arrive with only a name, this one came with its own mechanic and nothing had
to be invented. The burn rides `Condition.effect` at `WHEN_THEY_ACT`.

**Stunned**, which stops its holder acting at all, and **Invisible**, which is
Hidden's effect under the SRD's own second name for it. Both arrived with Grace's
level 3 cards, and both were modelled for On Fire's reason: the card applying
each one prints what it does. *Hypnotic Shimmer* spells out "they can't use
reactions and can't take any other actions", and *Invisibility* spells out
"attack rolls against them are made with disadvantage".

With those two in, **every condition the SRD names now has a representation
here.** What is still declared as a gap is one clause of Stunned - "can't use
reactions" - since an adversary's Reaction features fire from a dozen dispatch
points rather than from the spotlight.

**Silenced**, from Midnight's *Hush*, is the first condition whose effect is
decided **per holder, at the moment it lands**. "They can't cast spells" has
exactly one handle here - magic damage, the only magic this simulator recognises -
so the card asks each target whether its printed attack is magic and sets
`prevents_action` accordingly. A Silenced magic adversary loses its activation
like a Stunned one; a Silenced physical adversary is recorded and inert like a
Restrained one. That is why `prevents_action` is a field on the record rather than
a property of the name.

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

# **Taunted**, which fixes its holder's target to whoever taunted them. Ruled by
# the user rather than read off the page: the Weaponmaster's Goading Strike gives
# two different durations for the same clause ("until their next successful
# attack" and "the next time the Taunted target attacks"), and pinning the target
# is what the feature does at a table. Read in `combat/policy.py`, through the
# generic `forced_party_target` dispatch - nothing there knows this name.
TAUNTED = "Taunted"

# **Enraptured**, Taunted's mirror across the table: an Enraptured adversary
# swings at whoever enraptured them. Ruled by the user on exactly that reading -
# the printed text is fiction ("their attention is fixed on you, narrowing their
# field of view and drowning out any sound but your voice"), and fixing the
# target is what it comes to in a fight. Read in `combat/policy.py` through the
# generic `forced_adversary_target` dispatch; nothing there knows this name.
ENRAPTURED = "Enraptured"

# **On Fire**, the first condition whose own damage the SRD spells out on the
# card that applies it. Its holder burns each time they act, which is why it is
# the first real user of `Condition.effect` on the *acting* moment rather than
# before an action roll. How much it burns for belongs to whoever lit the fire,
# not here - Cinder Grasp's is 2d6 magic, and a future card's may not be.
ON_FIRE = "On Fire"

# **Invisible**, which the SRD prints as its own condition and which comes to
# exactly what Hidden comes to here: "attack rolls against them are made with
# disadvantage", which is Grace's *Invisibility* spelling out on its own card the
# thing Hidden had to be ruled. Kept as a separate name rather than folded into
# HIDDEN so a report says which one a combatant is under - a card called
# Invisibility announcing "Hidden" reads as the wrong card having fired.
INVISIBLE = "Invisible"

# The conditions that make rolls against their holder Disadvantaged. Two names,
# one effect, and the list lives here so `FightState.is_hidden` stays a single
# generic reader rather than growing a branch per condition name.
UNSEEN = (HIDDEN, INVISIBLE)

# **Stunned**, which stops its holder acting at all. The last of the SRD's named
# conditions to have no representation here, and it is modelled for exactly the
# reason On Fire is: the card that applies it prints the whole rule. Grace's
# *Hypnotic Shimmer* says "while Stunned, they can't use reactions and can't take
# any other actions until they clear this condition", so nothing had to be
# invented.
#
# Read through `Condition.prevents_action` rather than by name, so the fight loop
# never learns this word - and so a future condition that also stops somebody
# acting needs no new branch.
STUNNED = "Stunned"

# **Silenced**, from Midnight's *Hush*: "while Silenced, they can't make noise and
# can't cast spells". The noise has no representation, and casting spells has
# exactly one - the Counterspell ruling, that **magic damage is the only magic
# this simulator recognises**. So the silence is worth something against an
# adversary whose printed attack deals magic damage and nothing against one whose
# doesn't, and *which* it is has to be decided per holder.
#
# That decision is made by whoever applies it, when it lands, and carried on
# `Condition.prevents_action` - the same field Stunned uses, and the reason it is
# a field rather than a property of the name. A Silenced physical adversary is
# recorded and inert, exactly as Restrained is, so other content can still key on
# it and the coverage report still says the card fired.
SILENCED = "Silenced"

# **Sheltered**, from Sage's *Wild Fortress*: a creature inside the dome "can't be
# targeted by attacks and can't make attacks". The second half is
# `prevents_action`, which makes this the first condition ever applied to a **PC**
# that stops them acting - and the reason `combat/fight.py` now skips a PC who
# cannot act rather than spotlighting them. The first half is the dome soaking
# what would have hit them, which is the card's own damage-reduction hook rather
# than anything this name carries.
SHELTERED = "Sheltered"

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

    # Whether this condition stops its holder acting at all. Data rather than a
    # callable, for `disadvantage_on`'s reason: it isn't something that *happens*
    # at an announced moment but a standing fact about whether a spotlight can be
    # spent, read where that is decided (`combat/policy.py`). Stunned is the
    # first and only user.
    #
    # The activation is still spent and the Fear it cost is still gone - the GM
    # turn charges before an adversary is asked what it does, which is the same
    # weight the Green Ooze's `Slow` carries.
    prevents_action: bool = False


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
