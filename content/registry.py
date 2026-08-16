"""Every named thing a character sheet carries, and what the simulator does with it.

A sheet names a lot of content: domain cards, an ancestry, a community, a class,
a subclass. Some of it changes a fight, some of it can't, and some of it simply
hasn't been written yet. This module is where all three are declared, so that
the third is never mistaken for the second.

## The three states

Before this existed, an unimplemented card and a card we'd judged irrelevant
both looked the same from the outside - a lookup returning nothing. That is a
bad failure for a tool whose whole claim is being more trustworthy than the
official Battle Points math, because it hides how much of a character the
simulator is actually running.

  * MODELLED          - code runs it. Registered with a hook decorator.
  * NO_COMBAT_EFFECT  - assessed and dismissed: its effect has **no
                        representation in this simulation**. Declared with
                        `no_combat_effect(name, reason)`.
  * INSIGNIFICANT_COMBAT_EFFECT
                      - assessed and dismissed: its effect *is* represented here,
                        but is so small it is very unlikely to change an outcome
                        across a high-N run. The reason says by how much.
                        Declared with `insignificant_combat_effect(name, reason)`.
  * UNIMPLEMENTED     - not declared at all. Work not done, and it should be
                        visible in output rather than silently absent.

The middle two both run no code; what differs is the judgement recorded, and the
two claims are genuinely different. The first says the simulator has nothing for
this effect to touch - a knockback moves a combatant, and no position is
tracked. Note the scope: that is a statement about *this simulation*, not about
the game, and a knockback really does change a fight at a table. The second says
the effect lands squarely on something modelled and then measures it - +1
expected damage, which threshold bands absorb far more often than not.

So "it's small" settles neither. The first needs the effect to fall entirely
outside what is modelled; the second needs a number. Neither is ever the
assistant's call - dismissing content is a judgement about the game, and it
belongs to the user.

A fourth state also means a measured decision never has to be parked in
UNIMPLEMENTED for want of anywhere better, which would misreport it as work
nobody has done.

A MODELLED thing can still be *partly* modelled. Hooks take an `unmodelled`
list for the parts deliberately left out - "Restrained, because no movement is
tracked" - so a partial implementation says so in the same place it's
registered, and the gaps reach the coverage report instead of dying in a
docstring.

## One card, one place

Content is defined in the packages listed in `_DEFINITION_PACKAGES`, one module
per grouping, and a piece of content's effect *and* its "should this fire?"
decision both live with it. The rest of the codebase only ever calls the
dispatch functions at the bottom of this file - one per hook point. Nothing
outside these packages may grow a branch that knows a name.

Discovery is lazy and cached: the first lookup imports every module in every
definition package so their decorators and declarations have run.
"""

import importlib
import inspect
import pkgutil
import random
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, NamedTuple, Protocol

from content.names import base_name, canonical, parameter

# Packages holding content definitions. Adding a content type is adding a line
# here plus the package; nothing else in the codebase changes.
_DEFINITION_PACKAGES = ("domain_cards", "features")


class Status(Enum):
    """How much of a named piece of content the simulator runs."""

    MODELLED = "modelled"
    NO_COMBAT_EFFECT = "no combat effect"
    INSIGNIFICANT_COMBAT_EFFECT = "insignificant combat effect"
    UNIMPLEMENTED = "unimplemented"

    @property
    def is_dismissed(self) -> bool:
        """Assessed and knowingly not run. Nothing about the fight changes."""
        return self in (
            Status.NO_COMBAT_EFFECT,
            Status.INSIGNIFICANT_COMBAT_EFFECT,
        )


@dataclass(frozen=True)
class Assessment:
    """What the simulator does with one named thing off a character sheet."""

    name: str
    status: Status
    source: str = ""
    reason: str = ""
    unmodelled: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        """Modelled with nothing knowingly left out."""
        return self.status is Status.MODELLED and not self.unmodelled

    @property
    def is_partial(self) -> bool:
        """Modelled, but with declared gaps."""
        return self.status is Status.MODELLED and bool(self.unmodelled)


class Holder(Protocol):
    """The slice of a PC that content touches.

    A Protocol rather than importing PlayerCharacter: characters/ imports this
    package, and the import can't run both ways.
    """

    name: str
    proficiency: int
    major_threshold: int
    severe_threshold: int
    hp_marked: int
    hp_unmarked: int
    is_near_death: bool
    stress_marked: int
    stress_max: int
    hope_marked: int
    armor_marked: int
    armor_max: int
    armor_unmarked: int
    traits: dict[str, int]
    spellcast_trait: str
    experiences: list[dict]

    # Everything the sheet names - domain cards, ancestry, community, class,
    # subclass. Dispatch scans all of it, not just the loadout: a community
    # feature reaches into a fight exactly the way a card does, and nothing
    # about the hooks cares which kind of content registered them.
    named_features: list[str]

    level: int

    def spend_stress(self, amount: int = 1) -> bool: ...
    def can_spend_stress(self, amount: int = 1) -> bool: ...
    def clear_stress(self, amount: int) -> None: ...
    def gain_hope(self, amount: int) -> None: ...
    def can_spend_hope(self, amount: int = 1) -> bool: ...
    def spend_hope(self, amount: int) -> None: ...
    def clear_hp(self, amount: int) -> None: ...
    def mark_armor_slot(self, amount: int) -> None: ...
    def clear_armor_slot(self, amount: int) -> None: ...


class Interception(NamedTuple):
    """A PC stepping in front of another, and the content that let them."""

    shielder: Holder
    card: str


class DamagePool(NamedTuple):
    """The dice an attack is about to roll, before anything rolls them.

    Passed to `damage_pool` content so a weapon feature can change the shape of
    the roll rather than only its total - which is the one thing none of the
    other hooks can express. `extra_damage` can add dice but never take one
    away, and Massive and Powerful do both at once: roll an extra die, then
    discard the lowest of the pool.
    """

    dice_groups: list
    drop_lowest: int = 0
    modifier: int = 0


class Fight(Protocol):
    """The slice of a fight in progress that content is allowed to touch.

    Content needs to see the other side, and some of it drains the GM's Fear
    (see SIMULATION-RULES.md on temporary conditions). Declared as a Protocol so
    this package never imports combat/.
    """

    fear: int

    def note(self, message: str) -> None: ...
    def gain_fear(self, amount: int = 1) -> int: ...
    def grant_activation(self, holder) -> None: ...
    def consume_activation(self, holder) -> None: ...
    def apply_condition(self, holder, condition) -> None: ...
    def has_condition(self, holder, name: str) -> bool: ...
    def clear_condition(self, holder, name: str) -> None: ...
    def is_vulnerable(self, combatant) -> bool: ...
    def token_count(self, holder, name: str) -> int: ...
    def add_token(self, holder, name: str, cap: int) -> bool: ...
    def set_token(self, holder, name: str, value: int) -> None: ...
    def spend_tokens(self, holder, name: str, amount: int) -> int: ...
    def spend_fear(self, amount: int = 1) -> bool: ...
    def can_use_once_per_rest(self, holder, ability: str, long: bool = False) -> bool: ...
    def use_once_per_rest(self, holder, ability: str, long: bool = False) -> bool: ...

    @property
    def living_adversaries(self) -> list: ...

    @property
    def conscious_party(self) -> list: ...


_assessments: dict[str, Assessment] = {}

# Hook tables - one per point where content can reach into a fight. There is no
# "turn action" here on purpose: Daggerheart has no turns, only the spotlight,
# and what moves the spotlight is the outcome of a roll. So content is filed by
# its relationship to rolls and to damage.
#
#   _actions           make the action roll themselves; the outcome can pass the
#                      spotlight, so at most one resolves per spotlight
#   _free_abilities    require no roll, so they can never pass the spotlight
#   _damage_bonuses    add to the damage of a roll already happening
#   _on_hits           fire after an attack has landed
#   _severity_responses / _guards
#                      fire when damage arrives, not when the holder acts
#   _rerolls / _force_rerolls
#                      fire on a roll that has already resolved, and may replace
#                      it. Both are scanned party-wide, not holder-wide
_actions: dict[str, Callable] = {}
_hope_dice: dict[str, Callable] = {}
_roll_bonuses: dict[str, Callable] = {}
_on_rolls: dict[str, Callable] = {}
_rerolls: dict[str, Callable] = {}
_force_rerolls: dict[str, Callable] = {}
_free_abilities: dict[str, Callable] = {}
_damage_bonuses: dict[str, Callable] = {}
_extra_damage: dict[str, Callable] = {}
_on_hits: dict[str, Callable] = {}
_severity_responses: dict[str, Callable] = {}
_severity_increases: dict[str, Callable] = {}
_guards: dict[str, Callable] = {}
_immunities: dict[str, Callable] = {}
_damage_pools: dict[str, Callable] = {}
_activation_limits: dict[str, Callable] = {}
_direct_damage: dict[str, Callable] = {}
_spotlight_costs: dict[str, Callable] = {}
_attack_areas: dict[str, Callable] = {}
_on_damaged: dict[str, Callable] = {}
_difficulty_bonuses: dict[str, Callable] = {}
_standard_damage: dict[str, Callable] = {}
_on_attacked: dict[str, Callable] = {}
_on_spotlight: dict[str, Callable] = {}

_discovered = False
_discovering = False


# --- Declaring ---------------------------------------------------------------


def severity_response(name: str, unmodelled: Iterable[str] = ()):
    """Register content that changes the HP an incoming hit marks.

    Signature: `(holder, amount, hp_to_mark, fight) -> int` - the HP the hit
    should now mark. `amount` is the raw damage, so content can key on the
    number rolled rather than on what other reductions have left.

    `fight` may be None: damage can be resolved outside a fight (in a test, say),
    and content that needs per-fight state has to cope with not having it rather
    than assume it's there.
    """

    def register(function: Callable) -> Callable:
        _claim(_severity_responses, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def severity_increase(name: str, unmodelled: Iterable[str] = ()):
    """Register content that makes an incoming hit mark *more* HP.

    Signature and arguments are `severity_response`'s exactly - `(holder, amount,
    hp_to_mark, fight) -> int` - and this is its opposite number: that hook is
    for content that softens a hit, this one for content that worsens it. The
    Construct's `Weak Structure` ("when the Construct marks HP from physical
    damage, they must mark an additional HP") is the first, and the shape recurs
    often enough across the SRD's adversaries to be worth its own hook rather
    than a sign flip inside the softening one.

    Two hooks rather than one because the *order* matters and has to be fixed
    somewhere: softening runs first and hardening second, so a hit that armor and
    a domain card absorbed entirely has marked no HP, and content triggering "when
    you mark HP" correctly doesn't fire. Content here is responsible for checking
    `hp_to_mark` itself before adding to it.

    For symmetry `severity_response` would read better as `severity_decrease`.
    It isn't renamed only because five content modules register against the
    current name; that's the state of things rather than a decision anyone made.
    """

    def register(function: Callable) -> Callable:
        _claim(_severity_increases, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def immunity(name: str, unmodelled: Iterable[str] = ()):
    """Register content that makes its holder immune to a condition.

    Signature: `(holder, condition, fight) -> bool`. The condition is passed by
    name (see `content/conditions.py`) so that one piece of content can answer
    for several - Unstoppable turns off both Restrained and Vulnerable - without
    the caller learning anything about which content is involved.
    """

    def register(function: Callable) -> Callable:
        _claim(_immunities, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def guard(name: str, unmodelled: Iterable[str] = ()):
    """Register content that lets its holder take a hit aimed at an ally."""

    def register(function: Callable) -> Callable:
        _claim(_guards, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def action(name: str, unmodelled: Iterable[str] = ()):
    """Register content that makes an action roll of its own.

    Signature: `(holder, target, fight) -> AttackResult | None`. Returning None
    declines - the content had its chance and passed, so the PC falls through to
    the next option and ultimately to their weapon. Whether the content is a
    better use of the roll than a weapon attack is its own decision to make.
    """

    def register(function: Callable) -> Callable:
        _claim(_actions, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def free(name: str, unmodelled: Iterable[str] = ()):
    """Register content that takes effect without any roll.

    Signature: `(holder, fight) -> bool` - whether it fired. It can never pass
    the spotlight, but it does spend from the budget in SIMULATION-RULES.md, so
    returning True has a cost even though no dice were involved.
    """

    def register(function: Callable) -> Callable:
        _claim(_free_abilities, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def damage_bonus(name: str, unmodelled: Iterable[str] = ()):
    """Register content that adds to the damage of an attack already happening.

    Signature: `(holder, target, fight) -> int`. Applied before thresholds, so
    it can change how many HP a hit marks rather than only the number printed.
    """

    def register(function: Callable) -> Callable:
        _claim(_damage_bonuses, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def extra_damage(name: str, unmodelled: Iterable[str] = ()):
    """Register content that adds dice to a damage roll that is about to happen.

    Signature: `(holder, target, roll, fight) -> list[DiceGroup]` - the extra
    dice, or an empty list to decline.

    This is the hook for "on a success with Fear, deal an extra 1d10", and it
    exists because neither neighbour can express that. `damage_bonus` is
    consulted before the attack is rolled, so it can't know how the roll came
    out; `on_hit` fires after the damage has already been applied, so anything
    it adds arrives as a second, separate hit and is measured against the
    target's thresholds all over again - which can mark an HP the rules never
    intended.

    Firing here instead means the extra dice are part of the same damage roll,
    so they're counted once, before thresholds, exactly as a bigger weapon die
    would be. Flat bonuses that don't depend on the roll belong on
    `damage_bonus`; this is for dice conditional on the outcome.

    `fight` may be None, as with `severity_response`.
    """

    def register(function: Callable) -> Callable:
        _claim(_extra_damage, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def damage_pool(name: str, unmodelled: Iterable[str] = ()):
    """Register content that reshapes the dice an attack is about to roll.

    Signature: `(holder, weapon, pool, fight) -> DamagePool` - the pool as it
    should now be, or the pool it was given to decline.

    This is the hook for Massive and Powerful: "roll an additional damage die
    and discard the lowest result". `extra_damage` can add dice but has no way
    to take one back off, and `damage_bonus` only moves the total, so neither
    can say it. Fires after the attack has landed and before the damage is
    rolled, so everything it changes is measured against the target's
    thresholds exactly once.

    Weapon features are the expected caller, which is why `weapon` is in the
    signature - a feature belongs to the thing that has it, and needs to see
    the die it is adding one of.
    """

    def register(function: Callable) -> Callable:
        _claim(_damage_pools, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def activation_limit(name: str, unmodelled: Iterable[str] = ()):
    """Register content that lets its holder take more than one spotlight a turn.

    Signature: `(holder, fight) -> int | None` - how many times this combatant
    may be spotlighted in a single GM turn, or None to decline. The SRD's
    `Relentless (X)` is the reason it exists, and so far the only user.

    This is a *limit*, not a grant: it says how many activations are permitted,
    and the GM still has to be able to afford each one past the first. Nothing
    here charges Fear - `combat/fight.py` already does that for every extra
    activation, and Relentless says to spend Fear as usual.
    """

    def register(function: Callable) -> Callable:
        _claim(_activation_limits, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def spotlight_cost(name: str, unmodelled: Iterable[str] = ()):
    """Register content that makes its holder cost extra Fear to spotlight.

    Signature: `(holder, fight) -> int` - Fear on top of what the GM turn already
    charges. The Cave Ogre's `Ramp Up` ("you must spend a Fear to spotlight the
    Ogre") is the reason: it charges even for the turn's first activation, which
    is otherwise free.
    """

    def register(function: Callable) -> Callable:
        _claim(_spotlight_costs, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def attack_area(name: str, unmodelled: Iterable[str] = ()):
    """Register content that turns its holder's standard attack into an area one.

    Signature: `(holder, fight) -> Range | None` - the band the standard attack
    now sweeps, or None to decline. Ramp Up's "while spotlighted, they can make
    their standard attack against all targets within range" is the case, and it's
    a passive rather than an action: it changes what the ordinary attack *is*, so
    it can't be one option among several or it would only apply half the time.
    """

    def register(function: Callable) -> Callable:
        _claim(_attack_areas, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def on_attacked(name: str, unmodelled: Iterable[str] = ()):
    """Register content on a *target* that responds to being successfully attacked.

    Signature: `(holder, attacker, weapon, fight) -> None`. The mirror of
    `on_hit`, which belongs to whoever swung: this belongs to whoever was hit,
    and it fires on a successful attack whether or not any HP was marked. The
    Glass Snake's `Armor-Shredding Shards` ("after a successful attack against
    the Snake within Melee range, the attacker must mark an Armor Slot") is the
    reason it exists, and the attacker's *weapon* is in the signature because
    that clause is the only handle the simulator has on range.

    Distinct from `on_damaged`, which fires on damage arriving and can't see who
    dealt it - "the attacker must mark an Armor Slot" needs the attacker.
    """

    def register(function: Callable) -> Callable:
        _claim(_on_attacked, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def on_spotlight(name: str, unmodelled: Iterable[str] = ()):
    """Register content that fires whenever its holder takes the spotlight.

    Signature: `(holder, fight) -> None`. Not an action and not a choice: it runs
    before the holder picks what to do, and it can't decline the spotlight or
    take it. The Glass Snake's Spitter Die - "when the Snake is in the spotlight,
    roll this die" - is the case, and it keeps rolling every spotlight for the
    rest of the fight however the Snake spends them.

    Deliberately not an `action`: an action is one of the things a spotlight can
    be spent on, and exactly one of them resolves. This is something that happens
    *to* the spotlight, so it neither competes with the standard attack nor
    consumes it.
    """

    def register(function: Callable) -> Callable:
        _claim(_on_spotlight, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def standard_damage(name: str, unmodelled: Iterable[str] = ()):
    """Register content that replaces the dice its holder's *standard* attack rolls.

    Signature: `(holder, target, fight) -> tuple[list[DiceGroup], int] | None` -
    the dice and flat modifier to roll instead of the printed ones, or None to
    decline. The SRD writes this shape often: the Giant Mosquitoes' `Horde (X)`
    ("their standard attack deals 1d4+1 instead") and the Dire Wolf's `Pack
    Tactics` ("deal 1d6+5 instead of their standard damage") are the first two,
    and one hook serves both.

    **Only the printed attack.** A feature that hits with dice of its own - the
    Bear's Bite at 3d4+10 - passes them explicitly and is never asked, which is
    right: "instead of their standard damage" says nothing about a different
    attack the same adversary might make.

    Asked from inside the damage roll, so by the time it runs the attack has
    already landed. That matters for content whose trigger is a *successful*
    standard attack - Pack Tactics hands the GM a Fear, and asking before the
    roll would pay out on a miss.
    """

    def register(function: Callable) -> Callable:
        _claim(_standard_damage, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def difficulty_bonus(name: str, unmodelled: Iterable[str] = ()):
    """Register content that raises its holder's Difficulty.

    Signature: `(holder) -> int` - the bonus. **Resolved once, at spawn time**,
    and added into `Adversary.difficulty`; it is never consulted during a fight,
    which is why this is the one hook with no `fight` in its signature.

    That is deliberate. Difficulty is read in four places that have no fight to
    dispatch with - `items/weapons.py`, `content/aoe.py`'s `area_difficulty` and
    `targets_beaten`, and `features/classes.py`'s Hold Them Off - and threading a
    fight through all of them to move a number by 2 would be a great deal of
    machinery for a constant. Resolving it into the stat block means every reader
    is already correct without knowing this hook exists, which is the same
    arrangement character sheets use for their own resolved values.

    The cost is that a bonus the SRD qualifies - Flying is "*while* flying" -
    can't switch off mid-fight. The qualifier moves to the author instead: the
    number is written on the stat block, so an adversary airborne half the time
    is written with half the bonus. Over a high-N run those come to the same
    place, and the knob is in the JSON where it can be tuned per adversary.
    """

    def register(function: Callable) -> Callable:
        _claim(_difficulty_bonuses, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def on_damaged(name: str, unmodelled: Iterable[str] = ()):
    """Register content that fires when its holder has just taken damage.

    Signature: `(holder, amount, hp_marked, fight) -> None`. Distinct from
    `severity_response` and `severity_increase`, which are asked *while* a hit is
    being worked out and return the HP it should cost. This fires afterwards,
    when the marking is done, for content that reacts rather than adjusts - the
    Acid Burrower spraying blood on a Severe hit, the Construct exploding on its
    last HP.

    Both the raw `amount` and the `hp_marked` it came to are passed, because the
    SRD triggers on both kinds: "takes Severe damage" is about the number rolled,
    "marks 2 or more HP" is about what it cost.
    """

    def register(function: Callable) -> Callable:
        _claim(_on_damaged, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def direct_damage(name: str, unmodelled: Iterable[str] = ()):
    """Register content whose holder's attacks can't be softened by an Armor Slot.

    Signature: `(holder, fight) -> bool`. The SRD's direct damage, which the Cave
    Ogre's `Bone Breaker` grants for every attack it makes. A predicate rather
    than a flag on the stat block, because content is where the answer belongs
    and because a feature may well want to say "only on a critical" one day.
    """

    def register(function: Callable) -> Callable:
        _claim(_direct_damage, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def on_hit(name: str, unmodelled: Iterable[str] = ()):
    """Register content that fires after an attack has landed.

    Signature: `(holder, target, result, fight) -> None`. For content that
    extends a successful attack rather than being an attack of its own.
    """

    def register(function: Callable) -> Callable:
        _claim(_on_hits, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def hope_die(name: str, unmodelled: Iterable[str] = ()):
    """Register content that changes the size of the Hope Die.

    Signature: `(holder, fight) -> int | None` - the die to roll instead of a
    d12, or None to decline. `roll_duality` already takes a `hope_die` size, so
    nothing in dice/ needs to change for this.

    Unlike the other hooks, being asked *is* the commitment: the roll follows
    immediately, so content that spends a per-rest use here has genuinely spent
    it. Content that wants to be choosier should decline before claiming.
    """

    def register(function: Callable) -> Callable:
        _claim(_hope_dice, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def roll_bonus(name: str, unmodelled: Iterable[str] = ()):
    """Register content that adds to an action roll before it's made.

    Signature: `(holder, target, fight) -> int`. Like `hope_die`, being asked is
    the commitment - the roll follows immediately - so content that spends a
    resource here has genuinely spent it.
    """

    def register(function: Callable) -> Callable:
        _claim(_roll_bonuses, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def on_roll(name: str, unmodelled: Iterable[str] = ()):
    """Register content that responds to how an action roll came out.

    Signature: `(holder, roll, fight) -> None`. Fires after the roll resolves,
    for content keyed on rolling with Fear, failing, or critting.
    """

    def register(function: Callable) -> Callable:
        _claim(_on_rolls, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def reroll(name: str, unmodelled: Iterable[str] = ()):
    """Register content that can re-make a PC's action roll after it resolves.

    Signature: `(holder, roller, roll, remake, fight) -> DualityRollResult | None`
    - the replacement roll, or None to decline. `remake()` produces a fresh roll
    on the same terms as the original; content calls it rather than building one,
    so nothing here has to know the modifier, difficulty or Hope Die that went
    into the roll it is replacing.

    `holder` owns the content and `roller` made the roll, and they are not always
    the same PC: the Faerie's Luckbender can rescue an ally's roll, while the
    Human's Adaptability is strictly about your own. Content that only ever
    applies to itself checks `holder is roller`.

    Like `hope_die` and `roll_bonus`, being asked is close to the commitment -
    the replacement is taken as soon as it's offered - so content that spends
    Hope, Stress or a per-rest use here has genuinely spent it. Decline first,
    pay second.
    """

    def register(function: Callable) -> Callable:
        _claim(_rerolls, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def force_reroll(name: str, unmodelled: Iterable[str] = ()):
    """Register content that forces an *adversary* to re-make a roll.

    Signature:
    `(holder, attacker, target, roll, remake, fight) -> D20RollResult | None`,
    with the same `remake()` contract as `reroll`. The mirror image of that hook:
    there the party is re-rolling its own dice, here it is reaching across the
    table. The Wizard's Not This Time is the reason it exists.

    Scanned across the whole conscious party, since the PC who owns the content
    is not the one being attacked - the Wizard spends the Hope whoever the
    adversary swung at. `target` is that PC, and is in the signature because how
    badly hurt they are is exactly what makes an ordinary hit worth stopping.
    """

    def register(function: Callable) -> Callable:
        _claim(_force_rerolls, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def no_combat_effect(name: str, reason: str) -> None:
    """Declare that `name` exists and has no effect on the *simulated* fight.

    Called at module level in whichever content module the thing belongs to:

        no_combat_effect("Nature's Tongue", "Speaking with animals - never
                         changes a fight's outcome.")

    The point is the difference between this and silence. Silence means nobody
    has looked at it yet; this means someone did, and here's why it was left
    out. Both end up in the coverage report, labelled differently.

    Use this when the content's effect has **nothing to touch here** - the whole
    of it lands outside what the simulator represents. A knockback is the
    standard case: it moves a combatant, no position is tracked, and so it can
    change nothing. Say both halves in the reason, because such a feature is
    usually not inert at a table - this is a statement about the simulation.

    If the effect *is* represented and is merely small, that's
    `insignificant_combat_effect` - a different claim, recorded separately.
    """
    _assess(name, Status.NO_COMBAT_EFFECT, _calling_module(), reason=reason)


def insignificant_combat_effect(name: str, reason: str) -> None:
    """Declare that `name` reaches the simulation, but by too little to matter.

    The difference from `no_combat_effect` is the judgement being recorded, not
    the behaviour - both run no code. `no_combat_effect` says the effect has no
    representation here at all. This says it lands on something the simulator
    models fully, somebody worked out how much it is worth, and the answer was
    too small to change an outcome across a high-N run:

        insignificant_combat_effect(
            "adversary:From Above",
            "Swaps 1d8+1 for 1d10+1, about +1 expected damage. Damage becomes HP
             through threshold bands, so a point rarely changes what a hit marks.",
        )

    Record the size of the effect in the reason, because that is the whole
    content of the claim. "Probably small" is not an assessment.

    This exists so that a measured decision never has to be parked in
    `UNIMPLEMENTED`, which reads as work nobody has done. Like every dismissal it
    is the user's call to make, not the assistant's.
    """
    _assess(name, Status.INSIGNIFICANT_COMBAT_EFFECT, _calling_module(), reason=reason)


def _calling_module() -> str:
    """The module that called into here, for provenance in the coverage report."""
    frame = inspect.currentframe()
    caller = frame.f_back.f_back if frame and frame.f_back else None
    return caller.f_globals.get("__name__", "") if caller else ""


def _registered(table: dict[str, Callable], name: str):
    """The content registered for `name`, allowing for a parameter in the name.

    A stat block writes the name as the SRD prints it - `Relentless (3)` - while
    the content registers under its base name, `Relentless`, because the number
    is an argument rather than part of what the feature is. This is the one place
    that knows the two can differ, so every hook table gets the behaviour without
    each dispatch function repeating it.

    An exact match always wins, so content whose real name ends in brackets can
    still claim it and is never shadowed by a base-name registration.
    """
    found = table.get(canonical(name))
    if found is not None:
        return found
    base = base_name(name)
    return table.get(canonical(base)) if base != name else None


def feature_parameter(holder, name: str) -> str | None:
    """The argument `holder`'s stat block wrote for the feature registered as `name`.

    The other half of parameterised names. Dispatch finds a feature by its base
    name and calls it with the ordinary signature; the feature then asks this
    what X was for *this* holder - the Acid Burrower's Relentless is a 3 and the
    Construct's is a 2, and only the holder can say which.

    Deliberately not threaded through dispatch. Every hook signature would have
    grown a parameter that almost no content uses, and reading it here keeps a
    feature's own argument inside the feature, which is where "one card, one
    place" puts it.

    Returns None when the holder doesn't carry the feature at all, or carries it
    without a parameter - both of which the caller has to have an answer for.
    """
    for written in holder.named_features:
        if canonical(base_name(written)) == canonical(name):
            return parameter(written)
    return None


def _claim(table: dict[str, Callable], name: str, function: Callable) -> None:
    """Take a name in `table`, refusing to let two pieces of content share one.

    Claimed under the canonical form, so two registrations differing only in
    capitalisation are correctly treated as the same name and collide.
    """
    existing = table.get(canonical(name))
    if existing is not None and existing is not function:
        raise ValueError(
            f"Two different pieces of content are both registered as {name!r}. "
            "Names have to be unique - a character sheet has nothing else to go on."
        )
    table[canonical(name)] = function


def _assess(
    name: str,
    status: Status,
    source: str,
    reason: str = "",
    unmodelled: tuple[str, ...] = (),
) -> None:
    """Record what we do with `name`, merging a second hook on the same name.

    One piece of content can register for more than one hook - something that
    both softens damage and guards an ally - so two MODELLED declarations merge
    their gaps rather than colliding. Declaring the same name both modelled and
    without combat effect is a contradiction and raises.
    """
    existing = _assessments.get(canonical(name))
    if existing is not None and existing.status is not status:
        raise ValueError(
            f"{name!r} is declared both {existing.status.value!r} (in "
            f"{existing.source}) and {status.value!r} (in {source}). It can only "
            "be one."
        )

    if existing is not None:
        unmodelled = tuple(dict.fromkeys(existing.unmodelled + unmodelled))
        reason = reason or existing.reason
        source = existing.source

    # Keyed canonically, but the Assessment keeps the spelling it was declared
    # with - that's what a reader of the coverage report should see.
    _assessments[canonical(name)] = Assessment(
        name=name,
        status=status,
        source=source,
        reason=reason,
        unmodelled=unmodelled,
    )


# --- Discovery ---------------------------------------------------------------


def _discover() -> None:
    """Import every content module so its decorators and declarations have run.

    A separate in-progress flag guards against a content module importing this
    one back and re-entering, while `_discovered` is only set once every import
    has actually succeeded. Those have to be two different flags: marking
    discovery done up front means a content module that fails to import leaves
    the registry silently half-populated, and every piece of content filed after
    the broken one looks merely unimplemented. One syntax error then reads as a
    dozen unrelated failures.
    """
    global _discovered, _discovering
    if _discovered or _discovering:
        return

    _discovering = True
    try:
        for package_name in _DEFINITION_PACKAGES:
            package = importlib.import_module(package_name)
            for module_info in pkgutil.iter_modules(package.__path__):
                importlib.import_module(f"{package_name}.{module_info.name}")
        _discovered = True
    finally:
        _discovering = False


def refresh() -> None:
    """Force the next lookup to re-import. For tests, mostly."""
    global _discovered
    _discovered = False


# --- Assessing ---------------------------------------------------------------


def assess(name: str) -> Assessment:
    """What the simulator does with `name` - UNIMPLEMENTED if nobody has said.

    Matched regardless of capitalisation, so a sheet writing "i am your shield"
    finds the card. An unimplemented result carries the name *as the sheet wrote
    it*, since that's the string somebody has to go and look for.
    """
    _discover()
    return _registered(_assessments, name) or Assessment(
        name=name, status=Status.UNIMPLEMENTED
    )


def assess_all(names: Iterable[str]) -> list[Assessment]:
    """`assess` over a sheet's worth of names, in the order given."""
    return [assess(name) for name in names]


def all_assessments() -> dict[str, Assessment]:
    """Everything declared anywhere - a copy, so callers can't corrupt the cache.

    Keyed by the name each piece of content was declared with, not the canonical
    form, so this reads as a catalogue rather than as internal bookkeeping.
    """
    _discover()
    return {assessment.name: assessment for assessment in _assessments.values()}


# --- Lookup ------------------------------------------------------------------


def find_severity_response(name: str) -> Callable | None:
    """The damage-response for `name`, or None if it isn't modelled.

    None rather than an error, unlike items/registry.py: a sheet is allowed to
    name content nobody has written yet, and a PC carrying it still has to be
    able to walk into a fight. Gear is different - a weapon that doesn't resolve
    means a PC who can't attack at all, which is worth failing loudly over.
    """
    _discover()
    return _registered(_severity_responses, name)


def find_guard(name: str) -> Callable | None:
    """The guard behaviour for `name`, or None if it isn't modelled."""
    _discover()
    return _registered(_guards, name)


# --- Dispatch ----------------------------------------------------------------
#
# The only functions the rest of the codebase calls. One per hook point. Their
# number stays constant as content is added; only the definition packages grow.


def action_options(holder: Holder) -> list[Callable]:
    """Every roll-making ability the loadout offers, in a random order.

    A loadout is an unordered list - the order someone typed their cards in -
    so it must never decide which abilities a PC can use. Shuffling and taking
    the first that accepts is a uniform choice among the willing ones, without
    every ability needing a separate "would you act?" predicate.

    That trick only works because **declining is side-effect free**: an ability
    asked whether it wants the roll must not spend Hope, mark Stress or claim a
    per-rest use unless it commits. Every ability here has to honour that.

    The caller adds the PC's weapon attack to this list before choosing. The
    weapon is one of the options, not a fallback - see SIMULATION-RULES.md.
    """
    _discover()
    options = [
        found
        for name in holder.named_features
        if (found := _registered(_actions, name)) is not None
    ]
    random.shuffle(options)
    return options


def take_action(holder: Holder, target, fight: Fight):
    """Let one randomly chosen willing ability take this spotlight's roll.

    Returns its result, or None if nothing volunteered. Callers that also offer
    a weapon should use `action_options` directly, so the weapon is shuffled in
    among the rest rather than only being reached when everything declines.
    """
    for act in action_options(holder):
        result = act(holder, target, fight)
        if result is not None:
            return result
    return None


def use_free_abilities(holder: Holder, fight: Fight, limit: int) -> list[str]:
    """Fire up to `limit` no-roll abilities, returning the names that went off.

    The limit is the spotlight budget from SIMULATION-RULES.md, standing in for
    a player who doesn't hog the spotlight. Without it a PC would use every free
    ability they could afford, every single spotlight.

    Candidates are shuffled for the same reason as `action_options`: which
    abilities get used must not depend on the order a loadout was written in.
    """
    _discover()
    # The sheet's own spelling is carried along for the report; only the lookup
    # is canonical.
    candidates = [
        (name, found)
        for name in holder.named_features
        if (found := _registered(_free_abilities, name)) is not None
    ]
    random.shuffle(candidates)

    used: list[str] = []
    for name, ability in candidates:
        if len(used) >= limit:
            break
        if ability(holder, fight):
            used.append(name)
    return used


DEFAULT_HOPE_DIE = 12


def hope_die_for(holder: Holder, fight: Fight) -> int:
    """The Hope Die this holder rolls right now - a d12 unless something swaps it.

    Consulted once, immediately before an action roll is made. The first piece
    of content that offers a die wins; candidates are shuffled so that which one
    doesn't depend on the order a sheet was written in.
    """
    _discover()
    candidates = [
        found
        for name in holder.named_features
        if (found := _registered(_hope_dice, name)) is not None
    ]
    random.shuffle(candidates)

    for swap in candidates:
        sides = swap(holder, fight)
        if sides:
            return sides
    return DEFAULT_HOPE_DIE


def total_roll_bonus(holder: Holder, target, fight: Fight, names=None) -> int:
    """Everything that adds to this action roll, summed.

    Consulted at the moment the roll is made, by whichever option was chosen -
    so a card that declined never spends anything toward a roll it isn't making.

    `names` narrows the scope, and exists for gear. Content a *holder* carries -
    a domain card, a class feature, an armor feature - applies to everything
    they do, which is what the default does by scanning `named_features`. A
    *weapon's* feature does not: a Broadsword's Reliable is "+1 to attack rolls"
    with the Broadsword, and summing it holder-wide would quietly add it to a
    Wizard's spell attacks too. So an attack passes the weapon's own feature
    names here, and calls this twice - once holder-wide, once for the weapon.
    """
    _discover()
    total = 0
    for name in holder.named_features if names is None else names:
        contribute = _registered(_roll_bonuses, name)
        if contribute is not None:
            total += contribute(holder, target, fight)
    return total


def adjust_damage_pool(holder: Holder, weapon, pool: DamagePool, fight=None, names=None):
    """Let content reshape the dice an attack is about to roll.

    Each piece of content sees what the previous one left, so two adjustments
    compose. `names` scopes the lookup the same way `total_roll_bonus` does, and
    for gear it is the caller's job to pass the weapon's own feature names -
    Massive belongs to the Greatsword, not to the Guardian holding it.
    """
    _discover()
    for name in holder.named_features if names is None else names:
        adjust = _registered(_damage_pools, name)
        if adjust is not None:
            pool = adjust(holder, weapon, pool, fight)
    return pool


def apply_on_roll(holder: Holder, roll, fight: Fight) -> None:
    """Let content respond to how an action roll came out."""
    _discover()
    for name in holder.named_features:
        respond = _registered(_on_rolls, name)
        if respond is not None:
            respond(holder, roll, fight)


def _party_offers(fight: Fight, table: dict[str, Callable]) -> list[tuple[Holder, Callable]]:
    """Every (PC, content) pair in `table` the standing party can offer, shuffled.

    Both reroll hooks are party-wide rather than holder-wide, so neither the
    order an encounter listed the party in nor the order a sheet was typed in may
    decide who answers. Flattening both and shuffling once is a uniform choice
    across every offer on the table.

    **The shuffle only happens when there is a choice to make.** With no offers
    or exactly one, the order can't matter, and drawing from the global RNG
    anyway would shift the dice for every roll in every fight - including fights
    where nothing in the party can reroll anything. Two seeded runs that differ
    only in a loadout would then diverge for no reason connected to the loadout,
    which is exactly what a fixed seed exists to rule out.
    """
    if fight is None:
        return []

    offers: list[tuple[Holder, Callable]] = [
        (holder, found)
        for holder in fight.conscious_party
        for name in holder.named_features
        if (found := _registered(table, name)) is not None
    ]
    if len(offers) > 1:
        random.shuffle(offers)
    return offers


def remake_action_roll(roller: Holder, roll, remake: Callable, fight: Fight = None):
    """Give the party a chance to replace an action roll that has just resolved.

    Returns the roll to carry on with - the replacement if anything offered one,
    otherwise the roll it was given, so a caller can always use the result
    unconditionally.

    **At most one reroll applies.** The first offer wins and the rest are never
    asked, which stops a party stacking Luckbender on top of Adaptability to buy
    three attempts at one roll. Nothing in the SRD forbids that outright, but a
    chain of rerolls off a single trigger is not what any of these features
    describes, and letting it happen would quietly make a failed roll cheap.

    Called immediately after the roll is made and before anything reads it, so a
    replacement is indistinguishable from having rolled that way first. Content
    that rolls its own attack should reach this through
    `content/rolls.py`'s `make_action_roll` rather than calling `roll_duality`
    directly - the same contract that already applies to `total_roll_bonus`.
    """
    _discover()
    for holder, offer in _party_offers(fight, _rerolls):
        replacement = offer(holder, roller, roll, remake, fight)
        if replacement is not None:
            return replacement
    return roll


def force_adversary_reroll(
    attacker, target, roll, remake: Callable, fight: Fight = None
):
    """Give the party a chance to make an adversary re-make the roll it just made.

    The mirror of `remake_action_roll`, and the same contract: the roll to carry
    on with is returned either way, and the first PC willing to pay for it is the
    only one asked.

    `target` is the PC being swung at, who is generally not the PC being asked -
    content here reaches across the table on somebody else's behalf, so it needs
    to see whose behalf that is.

    `fight` may be None - an adversary's attack can be resolved outside a fight,
    in a test - in which case there is no party to ask and the roll stands.
    """
    _discover()
    for holder, offer in _party_offers(fight, _force_rerolls):
        replacement = offer(holder, attacker, target, roll, remake, fight)
        if replacement is not None:
            return replacement
    return roll


def total_damage_bonus(holder: Holder, target, fight: Fight) -> int:
    """Everything in the loadout that adds to this attack's damage, summed."""
    _discover()
    total = 0
    for name in holder.named_features:
        contribute = _registered(_damage_bonuses, name)
        if contribute is not None:
            total += contribute(holder, target, fight)
    return total


def total_extra_damage(holder: Holder, target, roll, fight=None) -> list:
    """Every extra damage die this holder's content adds to the roll just made.

    Consulted between the attack roll and the damage roll, with the attack roll
    in hand so content can key on how it came out. Returns dice groups to fold
    into the same `roll_damage` call, so they land before thresholds.

    Anything that rolls its own attack damage is expected to call this, the same
    way it already calls `total_roll_bonus` for the attack itself. That's the
    contract for content that rolls damage rather than swinging a weapon.
    """
    _discover()
    groups: list = []
    for name in holder.named_features:
        contribute = _registered(_extra_damage, name)
        if contribute is not None:
            groups.extend(contribute(holder, target, roll, fight))
    return groups


# One spotlight per combatant per GM turn, unless content says otherwise.
DEFAULT_ACTIVATIONS = 1


def activations_allowed(holder, fight=None) -> int:
    """How many times `holder` may be spotlighted in one GM turn.

    One, unless something they carry raises it. Where two pieces of content both
    answer, the highest wins - a limit is a permission, and the more permissive
    one is what a GM would be working from.

    Called by the GM turn once per candidate. Nothing here knows about
    Relentless; the loop only asks how many activations this adversary is good
    for and then has to afford them.
    """
    _discover()
    allowed = DEFAULT_ACTIVATIONS
    for name in holder.named_features:
        limit = _registered(_activation_limits, name)
        if limit is not None:
            allowed = max(allowed, limit(holder, fight) or DEFAULT_ACTIVATIONS)
    return allowed


def apply_on_hit(holder: Holder, target, result, fight: Fight) -> None:
    """Let every on-hit ability in the loadout respond to a landed attack."""
    _discover()
    for name in holder.named_features:
        respond = _registered(_on_hits, name)
        if respond is not None:
            respond(holder, target, result, fight)


def soften_damage(character: Holder, amount: int, hp_to_mark: int, fight=None) -> int:
    """Let every damage-response this character carries soften a hit.

    Called once by PlayerCharacter.take_damage. Each response sees what the
    previous one left, so two reductions stack.

    Scans everything the sheet names rather than only the domain-card loadout: a
    class feature softens a hit exactly the way a card does (Unstoppable reduces
    the severity of every hit while it's running), and nothing about this hook
    cares which kind of content registered it.
    """
    _discover()
    for name in character.named_features:
        respond = _registered(_severity_responses, name)
        if respond is not None:
            hp_to_mark = respond(character, amount, hp_to_mark, fight)
    return hp_to_mark


def extra_spotlight_cost(holder, fight=None) -> int:
    """Fear this combatant costs to spotlight, on top of the turn's own charge."""
    _discover()
    total = 0
    for name in holder.named_features:
        charge = _registered(_spotlight_costs, name)
        if charge is not None:
            total += charge(holder, fight)
    return total


def standard_attack_area(holder, fight=None):
    """The band this combatant's standard attack sweeps, or None for one target.

    First answer wins; nothing in the SRD gives one adversary two of these, and
    combining bands would be inventing a rule.
    """
    _discover()
    for name in holder.named_features:
        area = _registered(_attack_areas, name)
        if area is not None:
            band = area(holder, fight)
            if band is not None:
                return band
    return None


def apply_on_damaged(holder, amount: int, hp_marked: int, fight=None) -> None:
    """Let content react to `holder` having just taken a hit.

    Called by both sides' `take_damage` once the marking is settled, so a feature
    keyed on "marks their last HP" sees the holder already down.
    """
    _discover()
    for name in holder.named_features:
        respond = _registered(_on_damaged, name)
        if respond is not None:
            respond(holder, amount, hp_marked, fight)


def apply_on_attacked(holder, attacker, weapon, fight=None) -> None:
    """Let content the *target* carries respond to a successful attack on them."""
    _discover()
    for name in holder.named_features:
        respond = _registered(_on_attacked, name)
        if respond is not None:
            respond(holder, attacker, weapon, fight)


def apply_on_spotlight(holder, fight=None) -> None:
    """Let content fire on its holder taking the spotlight, before they act."""
    _discover()
    for name in holder.named_features:
        respond = _registered(_on_spotlight, name)
        if respond is not None:
            respond(holder, fight)


def standard_attack_damage(holder, target, fight=None):
    """The dice this combatant's standard attack should roll instead, if any.

    Returns `(dice_groups, modifier)` or None. First answer wins: nothing in the
    SRD gives one adversary two of these, and combining two replacements would be
    inventing a rule rather than following one.
    """
    _discover()
    for name in holder.named_features:
        swap = _registered(_standard_damage, name)
        if swap is not None:
            replacement = swap(holder, target, fight)
            if replacement is not None:
                return replacement
    return None


def total_difficulty_bonus(holder) -> int:
    """Everything this stat block carries that raises its Difficulty, summed.

    Called once, by `Adversary.spawn`, and never during a fight - see
    `difficulty_bonus` for why the bonus is resolved into the number rather than
    asked for on every roll. No `fight` argument for the same reason: there is no
    fight yet when this runs.
    """
    _discover()
    total = 0
    for name in holder.named_features:
        contribute = _registered(_difficulty_bonuses, name)
        if contribute is not None:
            total += contribute(holder)
    return total


def deals_direct_damage(holder, fight=None) -> bool:
    """Whether this combatant's attacks bypass the target's Armor Slot right now.

    False unless something they carry says otherwise. One call site, in the
    adversary's standard attack; PC weapons don't ask because no PC content deals
    direct damage yet.
    """
    _discover()
    for name in holder.named_features:
        grants = _registered(_direct_damage, name)
        if grants is not None and grants(holder, fight):
            return True
    return False


def harden_damage(character, amount: int, hp_to_mark: int, fight=None) -> int:
    """Let everything this combatant carries make an incoming hit cost more.

    The mirror of `soften_damage`, and called immediately after it by whoever is
    taking the damage - both sides of the table, since an adversary's Weak
    Structure and a PC's armor are the same shape of thing pointed in opposite
    directions.

    Running second is what makes "when you mark HP" honest: by the time this is
    asked, the softening has had its say, so a hit fully absorbed by armor and a
    domain card is sitting at zero and content that only fires on a real mark can
    see that.
    """
    _discover()
    for name in character.named_features:
        respond = _registered(_severity_increases, name)
        if respond is not None:
            hp_to_mark = respond(character, amount, hp_to_mark, fight)
    return hp_to_mark


def is_immune_to(holder: Holder, condition: str, fight=None) -> bool:
    """Whether anything this holder carries turns `condition` off right now.

    One call site per condition the simulator tracks. Content answers for itself;
    nothing here knows which feature grants what.
    """
    _discover()
    for name in holder.named_features:
        grants = _registered(_immunities, name)
        if grants is not None and grants(holder, condition, fight):
            return True
    return False


def find_shielder(target: Holder, party: list) -> Interception | None:
    """An ally who steps in front of `target`, or None if nobody does.

    Called once by the turn policy, before an adversary's attack is rolled. The
    first willing ally goes: a party with two Guardians both shielding the same
    PC is not worth the code it would take to arbitrate.

    Whether stepping in is worthwhile is the content's business, not this
    function's - it says no by returning False.
    """
    _discover()
    for ally in party:
        if ally is target:
            continue
        for name in ally.named_features:
            steps_in = _registered(_guards, name)
            if steps_in is not None and steps_in(ally, target):
                return Interception(shielder=ally, card=name)
    return None
