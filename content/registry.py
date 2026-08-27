"""Every named thing a character sheet carries, and what the simulator does with it.

A sheet names a lot of content: domain cards, an ancestry, a community, a class,
a subclass. Some of it changes a fight, some of it can't, and some of it simply
hasn't been written yet. This module is where all three are declared, so that
the third is never mistaken for the second.

## The states

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
  * OUT_OF_COMBAT     - assessed, and **not a dismissal**: players don't use it
                        during a fight, they use it between fights. Nothing runs
                        today because encounters aren't sequenced yet; when they
                        are, everything here is the to-do list. Declared with
                        `out_of_combat_ability(name, reason)`.
  * UNIMPLEMENTED     - not declared at all. Work not done, and it should be
                        visible in output rather than silently absent.

The two dismissals both run no code; what differs is the judgement recorded, and
the two claims are genuinely different. The first says the simulator has nothing for
this effect to touch - a knockback moves a combatant, and no position is
tracked. Note the scope: that is a statement about *this simulation*, not about
the game, and a knockback really does change a fight at a table. The second says
the effect lands squarely on something modelled and then measures it - +1
expected damage, which threshold bands absorb far more often than not.

So "it's small" settles neither. The first needs the effect to fall entirely
outside what is modelled; the second needs a number. Neither is ever the
assistant's call - dismissing content is a judgement about the game, and it
belongs to the user.

OUT_OF_COMBAT is not a third dismissal, and reading it as one would lose the
point of it. A Soldier's Bond hands two PCs 3 Hope each: that is neither
unrepresented nor small, so both dismissals would be false. What is true of it is
*when* it happens - between fights, never during one. So it records a decision
with a scheduled home rather than a judgement that nothing is lost.

The extra states also mean a measured decision never has to be parked in
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
from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Iterable, NamedTuple, Protocol

from content.damage_types import UNREDUCED, strongest, types_in
from content.names import base_name, canonical, parameter
from dice.common import AdvantageState, combined

# Packages holding content definitions. Adding a content type is adding a line
# here plus the package; nothing else in the codebase changes.
_DEFINITION_PACKAGES = ("domain_cards", "features")


class Status(Enum):
    """How much of a named piece of content the simulator runs."""

    MODELLED = "modelled"
    NO_COMBAT_EFFECT = "no combat effect"
    INSIGNIFICANT_COMBAT_EFFECT = "insignificant combat effect"
    OUT_OF_COMBAT = "out of combat"
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
    # Both halves of the Hope track, because content has to be able to tell a PC
    # who would gain from a Hope from one already at their cap - Valor's Critical
    # Inspiration hands out Hope and must not spend its one use of the fight on
    # somebody who cannot bank it.
    hope_max: int
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

    # Whether the holder is *willing* to pay, as opposed to able to. Both sides
    # answer it and they answer it differently - a PC by the last-slot rule, an
    # adversary by its desperation curve - which is exactly why content asks the
    # holder rather than working it out.
    def will_spend_stress(self, amount: int = 1) -> bool: ...
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
    gm_turns: int

    # The adversary taking a spotlight at this very moment, or None - which is
    # what it is for the whole of a PC's spotlight, and between activations on a
    # GM turn. Set by the loop around the activation it is resolving, exactly as
    # `acting_free` is.
    #
    # It exists because damage arrives at a PC without saying who threw it:
    # `take_damage` carries an amount and a type and no attacker, and threading
    # one through would change that signature on both sides of the table and in
    # every stand-in. Content that needs to know *what is hitting me* reads this
    # instead - Arcana's Counterspell needs the attacker's Difficulty to roll
    # against. None is a meaningful answer rather than a gap: damage arriving
    # outside a GM activation is the party's own (On Fire burning its holder),
    # and content asking about an adversary should decline on it.
    spotlighted: object | None

    def note(self, message: str) -> None: ...
    def acting_freely(self, combatant) -> bool: ...
    def gain_fear(self, amount: int = 1) -> int: ...
    def grant_activation(self, holder, free: bool = False) -> None: ...
    def consume_activation(self, holder) -> None: ...
    def apply_condition(self, holder, condition) -> None: ...
    def has_condition(self, holder, name: str) -> bool: ...
    def condition_on(self, holder, name: str): ...
    def clear_condition(self, holder, name: str) -> None: ...
    def summon(self, adversary) -> None: ...
    def summon_ally(self, combatant) -> None: ...
    def remove(self, adversary) -> None: ...
    def release_conditions_from(self, source) -> list: ...
    def is_vulnerable(self, combatant) -> bool: ...
    def disadvantaged_on(self, holder, trait: str) -> bool: ...
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
    def defeated_adversaries(self) -> list: ...

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
_standard_damage_types: dict[str, Callable] = {}
_on_attacked: dict[str, Callable] = {}
_before_attacked: dict[str, Callable] = {}
_on_spotlight: dict[str, Callable] = {}
_skip_spotlight: dict[str, Callable] = {}
_spotlight_while_defeated: dict[str, Callable] = {}
_on_party_attack_rolls: dict[str, Callable] = {}
_party_attack_disadvantages: dict[str, Callable] = {}
_party_target_overrides: dict[str, Callable] = {}
_party_roll_conversions: dict[str, Callable] = {}
_attack_advantages: dict[str, Callable] = {}
_attack_advantages_against: dict[str, Callable] = {}
_damage_multipliers: dict[str, Callable] = {}
_damage_resistances: dict[str, Callable] = {}
_damage_die_rerolls: dict[str, Callable] = {}
_condition_refusals: dict[str, Callable] = {}
_ally_on_hits: dict[str, Callable] = {}
_ally_damage_reductions: dict[str, Callable] = {}
_evasion_bonuses: dict[str, Callable] = {}
_adversary_target_overrides: dict[str, Callable] = {}
_help_bonuses: dict[str, Callable] = {}
_damage_die_maximums: dict[str, Callable] = {}
_extra_armor_slots: dict[str, Callable] = {}
_ally_on_rolls: dict[str, Callable] = {}
_ally_extra_damage: dict[str, Callable] = {}
_attack_misses: dict[str, Callable] = {}
_death_move_wards: dict[str, Callable] = {}
_adversary_attack_disadvantages: dict[str, Callable] = {}

_discovered = False
_discovering = False


# --- Declaring ---------------------------------------------------------------


def severity_response(name: str, unmodelled: Iterable[str] = ()):
    """Register content that changes the HP an incoming hit marks.

    Signature: `(holder, amount, hp_to_mark, fight, damage_type) -> int` - the HP
    the hit should now mark. `amount` is the raw damage, so content can key on
    the number rolled rather than on what other reductions have left.

    `damage_type` is a `DamageType` or None, and it is here because the SRD
    restricts several of these to one type: the Stalwart's Iron Will and the
    Guardian's Unstoppable are both "when you take **physical** damage". It is a
    fact about the hit exactly as `amount` and `hp_to_mark` are, so it sits
    beside them rather than being declared on the decorator and filtered inside
    dispatch. Most registrants ignore it.

    **Untyped damage matches no restriction.** A hit that arrives with no type
    satisfies neither "physical only" nor "magic only", which is the same rule
    `resistance_to` follows: missing data can then only ever *fail* to apply an
    effect, never wrongly apply one. Damage should always be typed; where it
    isn't, the gap shows up as nothing happening.

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
    hp_to_mark, fight, damage_type) -> int` - and this is its opposite number:
    that hook is for content that softens a hit, this one for content that
    worsens it. The Construct's `Weak Structure` ("when the Construct marks HP
    from physical damage, they must mark an additional HP") is the first, and the
    shape recurs often enough across the SRD's adversaries to be worth its own
    hook rather than a sign flip inside the softening one. It is also why
    `damage_type` is in the signature; see `severity_response`.

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


def damage_die_reroll(name: str, unmodelled: Iterable[str] = ()):
    """Register content that re-rolls individual dice of a damage roll just made.

    Signature: `(holder, sides, result, fight) -> bool` - whether the die that
    came up `result` on a d`sides` should be rolled again. The Blade card Not
    Good Enough ("when you roll your damage dice, you can reroll any 1s or 2s")
    is the reason it exists.

    **None of the three damage hooks next door can say this.** `damage_bonus`
    moves the total, `extra_damage` adds dice, `damage_pool` reshapes the pool
    before anything is thrown - and all three run *before* the dice are read.
    This one is asked afterwards, per die, which is the only place a rule about
    the number showing on a die can be answered.

    **Each die is offered once.** Content that says yes gets one fresh throw of
    the same size, and the new result is not offered back - "reroll any 1s or 2s"
    is one reroll, not a re-roll-until-happy. A die can therefore come up a 1
    again and stay there.

    The rerolled results replace the originals in the roll, so everything derived
    from them follows: a Massive discard takes the lowest of the *new* values, and
    the critical bonus is untouched because it is computed from the dice sizes.
    See SIMULATION-RULES.md on the ordering.
    """

    def register(function: Callable) -> Callable:
        _claim(_damage_die_rerolls, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def condition_refusal(name: str, unmodelled: Iterable[str] = ()):
    """Register content that can stop a condition landing on its holder at all.

    Signature: `(holder, condition, fight) -> bool` - True to refuse it, so it is
    never recorded. The condition is passed as the `Condition` record rather than
    by name, since content may want to know who applied it. The Valor card Bold
    Presence ("once per rest when you would gain a condition, you can avoid
    gaining the condition") is the reason it exists.

    **Distinct from `immunity` below, which cannot express it.** That hook is a
    *standing* answer, asked wherever a condition's effect is read - the
    Guardian's Unstoppable turns Vulnerable off for as long as it runs, and the
    condition itself is still sitting there when it stops. This one is asked
    once, at the moment the condition would land, and a refusal is permanent for
    that application. Folding the two together would break Unstoppable: a
    condition applied while it ran would never come back afterwards.

    Because it is asked only when a condition would really land, **being asked is
    the commitment** - content here can spend a per-rest use on the spot without
    checking anything else first.

    Not asked when the holder already carries a condition of that name: a refresh
    is not gaining a condition, and charging a per-rest use for one would spend it
    on nothing.
    """

    def register(function: Callable) -> Callable:
        _claim(_condition_refusals, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def damage_die_maximum(name: str, unmodelled: Iterable[str] = ()):
    """Register content that replaces a rolled damage die with its top face.

    Signature: `(holder, sides, result, fight) -> bool` - whether the die that
    came up `result` on a d`sides` should instead be read as `sides`. The Blade
    card Versatile Fighter ("mark a Stress to use the maximum result of one of
    your damage dice instead of rolling it") is the reason it exists.

    **Neighbour to `damage_die_reroll`, and deliberately not the same hook.**
    That one throws the die again and takes whatever comes up, which is a
    *gamble*; this one sets a known value, which is a *purchase*. Content paying
    a Stress needs to know exactly what it bought, and a reroll cannot promise
    that - a rerolled 1 can come up a 1 again, and the reroll hook's docstring
    says so outright.

    **Asked at most once per damage roll, and only while nothing has claimed
    it.** The card maximises *one* die, so dispatch stops at the first die a
    responder accepts. That makes the order dice are offered in load-bearing, and
    `maximise_damage_dice` offers them worst-first - the die furthest from its own
    top face - so content paying for this gets the most the card can give it.
    Reading which die is furthest from its maximum is arithmetic on numbers the
    player is looking at, not a statistic nobody computes.

    Runs **after** `damage_die_reroll`, so a die Not Good Enough has already
    rescued is judged on its new value. Two cards on one sheet then compose the
    way a table would play them: throw the bad dice again, then buy the worst of
    what is left. See SIMULATION-RULES.md on the ordering.
    """

    def register(function: Callable) -> Callable:
        _claim(_damage_die_maximums, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def extra_armor_slot(name: str, unmodelled: Iterable[str] = ()):
    """Register content that marks further Armor Slots against an incoming hit.

    Signature: `(holder, amount, hp_to_mark, fight, damage_type) -> int` - how
    many *additional* slots to mark, or 0 to decline. The Bone card Brace ("when
    you mark an Armor Slot to reduce incoming damage, you can mark a Stress to
    mark an additional Armor Slot") is the reason it exists.

    **Asked only when a slot has actually been marked**, which is the card's
    trigger read literally. So it never fires against direct damage, and never
    against a hit that arrived at a PC with no slots free - in both of those the
    first slot was not marked, and there is nothing for an additional one to be
    additional to.

    `hp_to_mark` is what the hit costs *after* the free slot, so content can see
    what another slot would buy. Zero means the free slot already took the whole
    hit and a second one would buy nothing.

    The caller marks the slots and takes the same number off `hp_to_mark`,
    clamped to what is actually free and floored at nothing - so content asking
    for more slots than the holder has left is not a way to mark negative HP.

    **Not `severity_response`, which cannot say this.** That hook returns the HP
    a hit should mark and has no way to spend an Armor Slot doing it, so a card
    registered there would soften the hit for free and leave the PC's armor
    untouched - which is most of what Brace costs.
    """

    def register(function: Callable) -> Callable:
        _claim(_extra_armor_slots, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def help_bonus(name: str, unmodelled: Iterable[str] = ()):
    """Register content that adds to a roll its holder is *helping* with.

    Signature: `(holder, roller, fight) -> int` - the bonus, or 0 to decline.
    `holder` is the helper, `roller` is the ally taking the action. The Bone card
    Tactician ("when you Help an Ally, they can spend a Hope to add one of your
    Experiences to their roll alongside your advantage die") is the reason.

    Holder-scoped on the **helper**, which is what makes it a hook of its own
    rather than a use of `roll_bonus`. That one is scoped to whoever is rolling,
    and the whole point of this content is that it belongs to somebody else - the
    Experience being lent is the Tactician's, not the roller's.

    Asked once, by `content/help.py`, at the moment a helper has been chosen and
    their Hope spent - so being asked means the help is definitely happening and
    content here may spend the roller's resources on it.
    """

    def register(function: Callable) -> Callable:
        _claim(_help_bonuses, name, function)
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


def ally_extra_damage(name: str, unmodelled: Iterable[str] = ()):
    """Register content that adds dice to *any* party member's damage roll.

    Signature: `(holder, attacker, target, roll, fight) -> list[DiceGroup]` - the
    extra dice, or an empty list to decline. Scanned across the conscious party
    rather than across whoever swung, because `holder` and `attacker` are
    generally different PCs. The Midnight card Chokehold is the reason: "when **a
    creature** attacks a target who is Vulnerable in this way, they deal an extra
    2d6 damage".

    **Distinct from `extra_damage` next door, which is holder-scoped.** That one
    fires only for its own holder's attacks, which is right for Forceful Push's
    momentum die. This is for content that marks a *target* and then pays out on
    whoever hits it, and holder-scoping it would mean a Chokehold only ever
    helped the PC who applied it - which is precisely what the card does not say.
    The same argument that gave Parallela `ally_on_hit`.

    Content is expected to check for itself that this attack is one it has a
    claim on - usually by a token placed on the *target*. Every registrant is
    asked about every party attack.

    Joins the same `roll_damage` call as the attack's own dice, so what it adds
    is measured against the target's thresholds exactly once - the whole reason
    `extra_damage` exists rather than dealing a second hit afterwards.
    """

    def register(function: Callable) -> Callable:
        _claim(_ally_extra_damage, name, function)
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

    Signature: `(holder, attacker, weapon, damage, hp_marked, fight) -> None`. The
    mirror of `on_hit`, which belongs to whoever swung: this belongs to whoever
    was hit, and it fires on a successful attack whether or not any HP was
    marked. The Glass Snake's `Armor-Shredding Shards` ("after a successful
    attack against the Snake within Melee range, the attacker must mark an Armor
    Slot") is the reason it exists, and the attacker's *weapon* is in the
    signature because that clause is the only handle the simulator has on range.

    **Both figures the hit produced are passed**, because the SRD keys features
    on either and this hook is the only one that can also see who swung:

    * `damage` is the total dealt, before the holder's thresholds turned it into
      marked HP. The Minor Chaos Elemental's Magical Reflection needs it - "deal
      damage to the attacker equal to half the damage they dealt".
    * `hp_marked` is what the hit finally cost. The Pirate Captain's
      *Swashbuckler* needs it - "when the Captain marks 2 or fewer HP from an
      attack within Melee range, the attacker must mark a Stress".

    Note the subject of that second one: it is the **Captain** marking HP, not
    the Captain making somebody else mark it. That is how the SRD writes adversary
    features throughout - the stat block's own text is about the stat block.

    Distinct from `on_damaged`, which sees both figures but not who dealt them -
    "the attacker must mark an Armor Slot" needs the attacker. Each hook knew
    half of what these features ask for, which is why this one has grown both.
    """

    def register(function: Callable) -> Callable:
        _claim(_on_attacked, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def before_attacked(name: str, unmodelled: Iterable[str] = ()):
    """Register content on a *target* that fires before an incoming attack is rolled.

    Signature: `(holder, attacker, weapon, fight) -> None`, identical to
    `on_attacked` and belonging to the same combatant - what differs is the
    moment. That hook fires once an attack has succeeded; this one fires before
    the dice are thrown at all, which is where the SRD puts its interrupting
    Reactions: the Harrier's Fall Back is "when a creature moves into Melee
    range to make an attack, you can mark a Stress **before the attack roll**".

    **The attack goes ahead regardless.** The return value is ignored and there
    is no way to say "and it never happens": a Reaction whose fiction is
    stepping out of reach is modelled as the counterattack it comes with, not as
    a veto, because a PC can move within Close range as part of their own action
    and would simply follow. See SIMULATION-RULES.md.

    The attacker's `weapon` is passed for the reason `on_attacked` takes it -
    it is the only handle the simulator has on how far away they were standing.
    """

    def register(function: Callable) -> Callable:
        _claim(_before_attacked, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def death_move_ward(name: str, unmodelled: Iterable[str] = ()):
    """Register party content that can stop a PC's death move happening at all.

    Signature: `(holder, target, fight) -> bool` - True if the death move is
    averted, in which case the PC stays conscious and nothing else happens to
    them here. Scanned across the conscious party, since `holder` and `target`
    are generally different PCs: Splendor's *Life Ward* is cast on somebody else.
    The **first** answer wins - a death move is averted once, not twice.

    **Content that averts it is responsible for what happens instead.** Life Ward
    says the target "clears a Hit Point instead", so the card does the clearing
    before returning True. This hook only decides whether `avoid_death` runs.

    Asked at the moment the last HP is marked and before the death move is taken,
    which makes **being asked the commitment** - a card here has a trigger that
    has genuinely happened, so it may spend its ward on the spot.

    `fight` may be None, and content should decline on it. That is not a
    formality: HP is marked from several places and only some of them carry a
    fight (see `PlayerCharacter.mark_hp_and_check_death`), so a ward that assumed
    one would raise on the paths that don't.
    """

    def register(function: Callable) -> Callable:
        _claim(_death_move_wards, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def adversary_attack_disadvantage(name: str, unmodelled: Iterable[str] = ()):
    """Register party content that hobbles an **adversary's** attack.

    Signature: `(holder, attacker, target, fight) -> bool` - whether this attack
    is made at Disadvantage. Scanned across the conscious party, since the content
    belongs to a PC rather than to either combatant in the attack. The Valor card
    *Goad Them On* is the reason: a goaded adversary must attack the taunter next
    spotlight, "which they make with disadvantage".

    **The mirror of `party_attack_disadvantage`, pointed the other way across the
    table.** That one is GM-side content hobbling a PC's swing; this is party-side
    content hobbling an adversary's. Neither can be written as the other, and
    `attack_advantage` next door can't say it either - that hook is holder-scoped
    on whoever is attacking, and the whole point here is that the content belongs
    to the other side.

    Folded into the roll with `combined`, so it cancels against a Vulnerable
    target's Advantage rather than overriding it - which is what the SRD does with
    two opposed sources.
    """

    def register(function: Callable) -> Callable:
        _claim(_adversary_attack_disadvantages, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def attack_missed(name: str, unmodelled: Iterable[str] = ()):
    """Register content on a *target* that responds to an incoming attack failing.

    Signature: `(holder, attacker, roll, fight) -> None`. Holder-scoped on
    whoever was swung at, because that is how the SRD writes it: the Bone card
    Redirect is "when an attack made against **you** from beyond Melee range
    fails". Nothing is returned - the attack has already missed, and there is
    nothing left to change about it.

    **The third moment in an incoming attack, and the only one that was missing.**
    `before_attacked` fires before the dice, `on_attacked` fires once the attack
    has succeeded, and between them they had no way to say "and if it doesn't".
    A miss is a real trigger in Daggerheart - it is what a Reaction like this one
    is paid for - and until this hook existed it simply went unannounced.

    `roll` is the attack roll that failed, so content can read how it came out.
    `attacker` is the adversary that swung, which is what carries the printed
    range band a card like Redirect has to read.

    Asked once per activation, of the PC the attack was aimed at. An **area**
    attack that catches several PCs announces only that one, which is declared as
    a gap where content registers.
    """

    def register(function: Callable) -> Callable:
        _claim(_attack_misses, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def attack_advantage(name: str, unmodelled: Iterable[str] = ()):
    """Register content that grants its holder Advantage on the attack they're making.

    Signature: `(holder, target, fight) -> AdvantageState | None` - the state this
    content contributes, or None to decline. Everything that answers is folded
    together with `dice/common.py`'s `combined`, so Advantage and Disadvantage
    cancel rather than stack.

    Asked once, immediately before the standard attack is rolled, which makes
    **being asked the commitment** - the same contract `hope_die` and `roll_bonus`
    keep. The Jagged Knife Shadow's Cloaked is why: it grants Advantage "until
    after the Shadow's next attack", so it spends its token when consulted rather
    than needing to be told afterwards that the attack happened.

    Only the *standard* attack consults this - on **both sides of the table**.
    For an adversary that is the stat block's printed attack; for a PC it is the
    weapon swing, which is why `items/weapons.py` folds this in alongside the
    hobbles it already asks about. Content that rolls an attack of its own passes
    whatever state it means to roll in, which is usually none, so a card like
    Reckless reaches a swing and not a Grimoire spell - declared as a gap where
    it registers.
    """

    def register(function: Callable) -> Callable:
        _claim(_attack_advantages, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def damage_multiplier(name: str, unmodelled: Iterable[str] = ()):
    """Register GM-side content that multiplies damage dealt to one of the party.

    Signature: `(holder, target, attacker, fight) -> float | None` - the
    multiplier, or None to decline. Scanned across the living adversaries rather
    than across the attacker or the target, because the content belongs to
    neither: the Jagged Knife Kneebreaker's `I've Got 'Em` says creatures **it**
    has Restrained take double damage from attacks by *other* adversaries, so the
    feature is a third party to every attack it changes.

    **A multiplier may be a fraction.** The Young Dryad's `Voice of the Forest`
    buys extra activations for its allies at the price of their attacks dealing
    half damage, which is this hook pointed the other way - and it is the same
    question ("how much of this roll actually lands?") whichever direction it
    moves the number. `Adversary._dealt` floors the product once at the end, so
    a halving rounds down like every other halving in the codebase.

    Applied to the damage total before the target's thresholds see it, which is
    what "take double damage" means in a game where damage becomes HP through
    bands - doubling afterwards would double the HP instead, which is a much
    larger and quite different effect. A halving lands in the same place and for
    the same reason.

    Multipliers from several sources multiply together. Nothing in the SRD stacks
    two of these yet; multiplying is the reading that doesn't privilege whichever
    adversary happened to be listed first.
    """

    def register(function: Callable) -> Callable:
        _claim(_damage_multipliers, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def damage_resistance(name: str, unmodelled: Iterable[str] = ()):
    """Register content that makes its holder resistant or immune to a damage type.

    Signature: `(holder, damage_type, fight) -> float | None` - the factor
    incoming damage of that type is multiplied by, or None to decline.
    `content/damage_types.py` names the three answers it can give: `UNREDUCED`,
    `RESISTED` (a half) and `IMMUNE` (nothing gets through).

    **One hook for both**, keyed by the type. Immunity and resistance differ only
    in how much of the hit survives - the SRD writes them as one paragraph - so a
    feature granting both would otherwise have to register twice and a caller
    would have to ask two questions and reconcile the answers. Note this is *not*
    `immunity` above, which is about **conditions**: the names are similar and
    the questions are not, so neither is overloaded onto the other.

    Holder-scoped, because a resistance belongs to whoever is being hit rather
    than to the attack. Dispatch scans the target's own features and takes the
    **strongest single** answer, since "the effects of multiple resistances to the
    same damage type do not stack".

    Applied before the target's thresholds, which is what the SRD says outright -
    so a resistance changes how many HP a hit marks, not just the number rolled.
    """

    def register(function: Callable) -> Callable:
        _claim(_damage_resistances, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def party_attack_disadvantage(name: str, unmodelled: Iterable[str] = ()):
    """Register GM-side content that hobbles a PC's attack on *somebody else*.

    Signature: `(holder, attacker, target, weapon, fight) -> bool` - whether this
    attack is made at Disadvantage. Scanned across the living adversaries, since
    the content belongs to a third party: the Swarm of Rats' `In Your Face` says
    everyone in Melee of the Swarm has disadvantage attacking anything *other
    than* the Swarm, so the feature belongs to neither the PC swinging nor the
    adversary being swung at.

    **Distinct from `Condition.disadvantage_on`, which cannot express it.** That
    one hobbles a named *trait*, and the trait is the same whichever adversary is
    being attacked - so it can say "disadvantage on Agility Rolls" and cannot say
    "disadvantage on attacks against anyone but me". This hook takes both the
    attacker and the target for exactly that reason.

    The `weapon` is passed for the reason `on_attacked` takes it: it is the only
    handle the simulator has on how far away the attacker was standing.

    Folded into the roll with `combined`, so a PC who would otherwise have
    Advantage comes out even rather than being hobbled outright.
    """

    def register(function: Callable) -> Callable:
        _claim(_party_attack_disadvantages, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def attack_advantage_against(name: str, unmodelled: Iterable[str] = ()):
    """Register GM-side content that hands Advantage to attacks on one creature.

    Signature: `(holder, target, fight) -> bool` - whether attacks made against
    `target` right now have Advantage. Scanned across the living adversaries,
    since the content belongs to a third party: the Shambling Zombie's `Too Many
    to Handle` says "all attacks against that creature have advantage" when the
    Zombie has it surrounded, so the feature belongs to neither the adversary
    swinging nor the PC being swung at.

    **The mirror of `party_attack_disadvantage`, pointed the other way across the
    table.** That one is GM-side content hobbling a *PC's* roll; this is GM-side
    content aiding a roll *against* a PC. Neither can be written as the other:
    `attack_advantage` next door is holder-scoped and can only speak for the
    combatant carrying it, which is exactly what a surrounding feature is not.

    No `weapon` in the signature, unlike its mirror. That one needs it because
    "within Melee range" has to be read off the attacker's reach; this one asks
    about where the *target* is standing relative to the content's holder, which
    the area rule answers without knowing who is swinging.

    Folded into the roll with `combined`, so it cancels against Disadvantage
    rather than overriding it.
    """

    def register(function: Callable) -> Callable:
        _claim(_attack_advantages_against, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def party_target_override(name: str, unmodelled: Iterable[str] = ()):
    """Register GM-side content that decides who a PC attacks this spotlight.

    Signature: `(holder, attacker, fight) -> object | None` - the adversary the
    PC must swing at, or None to decline. Scanned across the living adversaries,
    and the first answer wins: two adversaries both compelling the same PC is not
    a state the SRD has.

    The Weaponmaster's `Goading Strike` is the reason it exists. A Taunt is
    modelled as the PC's target being **fixed to whoever taunted them**, ruled by
    the user rather than read off the page - the printed text gives two different
    durations for the same clause, and pinning the target is what the feature is
    for at a table.

    Asked once, where the party's own targeting rule is asked, so a compelled PC
    never even considers the focus-fire choice. It reaches only the *target*: what
    the PC then does to it - a weapon swing, a domain card - is still theirs.
    """

    def register(function: Callable) -> Callable:
        _claim(_party_target_overrides, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def on_party_attack_roll(name: str, unmodelled: Iterable[str] = ()):
    """Register GM-side content that watches a PC make an attack roll.

    Signature: `(holder, roller, roll, fight) -> None`. Scanned across the living
    adversaries rather than across the roller's own sheet, because the content
    belongs to the other side of the table - the mirror of `force_reroll`, which
    is party content watching an adversary's roll.

    The Head Guard's countdown is the reason it exists: "it ticks down when a PC
    makes an attack roll". Watching only - anything that needs to *change* the
    roll belongs on `convert_party_roll`, which is asked first.
    """

    def register(function: Callable) -> Callable:
        _claim(_on_party_attack_rolls, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def convert_party_roll(name: str, unmodelled: Iterable[str] = ()):
    """Register GM-side content that rewrites how a PC's action roll came out.

    Signature: `(holder, roller, roll, fight) -> DualityRollResult | None` - the
    roll as it should now read, or None to decline. The first conversion offered
    wins, on the same reasoning `remake_action_roll` gives for stopping at one:
    a chain of rewrites off a single trigger is not what any of this content
    describes.

    The Jagged Knife Hexer's Curse is the case - "mark a Stress when that target
    rolls with Hope to make the roll be with Fear instead" - and it is worth
    seeing what that rewrites, because a duality outcome is not just a token: it
    decides whether the PC gains a Hope or the GM gains a Fear, *and* whether the
    party keeps the spotlight. So one Stress here can cost the party their turn.

    Distinct from `on_party_attack_roll`, which only watches. Kept separate for
    the reason `severity_response` and `on_damaged` are separate: one is asked
    while an outcome is still being settled, the other after it is.
    """

    def register(function: Callable) -> Callable:
        _claim(_party_roll_conversions, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def skip_spotlight(name: str, unmodelled: Iterable[str] = ()):
    """Register content that takes its holder's spotlight away before they act.

    Signature: `(holder, fight) -> bool` - True to spend the activation on
    nothing. The Green Ooze's `Slow` is the reason it exists: "when you spotlight
    the Ooze and they don't have a token, they can't act yet - place a token and
    describe what they're preparing to do."

    Distinct from every other way a spotlight can come to nothing. An `action`
    that declines simply lets the next option try, and the standard attack never
    declines, so a spotlight always resolves into *something*; this is the hook
    for content that says it resolves into nothing at all. And it is not
    `on_spotlight`, which fires on the spotlight arriving and cannot refuse it.

    **Being asked is the commitment**, the same contract `attack_advantage` and
    `hope_die` keep: it is consulted exactly once per activation, so content that
    alternates can flip its own token here rather than needing something
    afterwards to notice the spotlight happened.

    The activation is still spent, and the Fear it cost is still gone - the GM
    turn charges before the adversary is asked what it does. That is the whole
    weight of the feature.
    """

    def register(function: Callable) -> Callable:
        _claim(_skip_spotlight, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def spotlight_while_defeated(name: str, unmodelled: Iterable[str] = ()):
    """Register content that lets its holder be spotlighted after being defeated.

    Signature: `(holder, fight) -> bool` - whether the GM may still spend a
    spotlight on this combatant now that it is down. False, and nothing else in
    the loop changes: a defeated adversary is not in `living_adversaries`, so it
    cannot be targeted, does not count toward victory, and is never picked.

    The Skeleton Warrior's `Won't Stay Dead` is the reason it exists: "when the
    Warrior is defeated, you can spotlight them and roll a d6. On a result of 6,
    if there are other adversaries on the battlefield, the Warrior re-forms with
    no marked HP." The spotlight is what buys the roll, so the feature is
    unreachable unless something can offer a defeated combatant one.

    **Permission only.** It says the GM *may* spotlight them; the turn still
    charges its usual Fear for every activation past the first and the spotlight
    still counts against the party size + 1 cap, exactly as `Relentless (X)`'s
    extra activations do. Nothing here reaches around the budget.

    What happens once the spotlight arrives is the content's own business, and it
    is expected to answer `on_spotlight` (to do the thing) and `skip_spotlight`
    (to spend the activation on nothing when it didn't work). This hook only
    decides who is on the GM's list.
    """

    def register(function: Callable) -> Callable:
        _claim(_spotlight_while_defeated, name, function)
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

    Signature: `(holder, target, roll, fight) -> tuple[list[DiceGroup], int] | None`
    - the dice and flat modifier to roll instead of the printed ones, or None to
    decline. `roll` is the attack roll that has just landed, passed for the same
    reason `extra_damage` takes one: the SRD writes swaps conditional on *how*
    the attack came out, and the Jagged Knife Shadow's Backstab ("when the Shadow
    succeeds on a standard attack that **has advantage**") is the first. Content
    that only cares who is being hit ignores it. The SRD writes this shape often: the Giant Mosquitoes' `Horde (X)`
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


def standard_damage_type(name: str, unmodelled: Iterable[str] = ()):
    """Register content that changes what type its holder's *standard* attack deals.

    Signature: `(holder) -> DamageType | frozenset | None` - the type the printed
    attack now deals, or None to decline. The Spellblade's `Arcane Steel` is the
    reason: "damage dealt by the Spellblade's standard attack is considered both
    physical and magic", which nothing else could say.

    **Only the printed attack**, exactly like `standard_damage` next door: a
    feature that rolls damage of its own states its own type on the page and is
    never asked, so the Construct's Death Quake stays magic out of a physical
    stat block whatever else that stat block carries.

    No `fight` in the signature, for `difficulty_bonus`'s reason turned around:
    this one *does* run during a fight, but the answer is a standing fact about
    the stat block rather than about the moment, and `Adversary.type_of_damage`
    is called from several places that have no fight to pass.
    """

    def register(function: Callable) -> Callable:
        _claim(_standard_damage_types, name, function)
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


def ally_on_hit(name: str, unmodelled: Iterable[str] = ()):
    """Register content that responds to *any* party member's landed attack.

    Signature: `(holder, attacker, target, result, fight) -> None`. Scanned across
    the conscious party rather than across whoever swung, because `holder` and
    `attacker` are generally different PCs - the same arrangement `reroll` and
    `force_reroll` already use for content that reaches somebody else's roll.

    **Distinct from `on_hit` next door, which is holder-scoped.** That one fires
    only for its own holder's attacks, which is right for Whirlwind: a Guardian's
    card has no business firing off a Ranger's bow. This is for content a PC
    *puts on* somebody else - the Book of Sitil's Parallela hangs on an ally and
    resolves the next time **they** attack - and holder-scoping it would mean the
    spell only ever worked when cast on yourself.

    Fires on a landed attack, from the same call site as `apply_on_hit`, so
    content here sees a hit and never a miss.

    Content is expected to check for itself that the attack belongs to it -
    usually by a token placed on the attacker when the spell was cast. Every
    registrant is asked about every party attack.
    """

    def register(function: Callable) -> Callable:
        _claim(_ally_on_hits, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def adversary_target_override(name: str, unmodelled: Iterable[str] = ()):
    """Register party content that decides who an adversary swings at.

    Signature: `(holder, adversary, fight) -> object | None` - the PC the
    adversary must attack, or None to decline. Scanned across the conscious
    party, since the content belongs to the PC who cast it rather than to the
    adversary it is on. The first answer wins.

    **The exact mirror of `party_target_override`**, which is the GM's side of
    the same idea: that hook is a Weaponmaster's Taunt fixing a PC's target, and
    this is Grace's *Enrapture* fixing an adversary's. The two are kept apart
    rather than merged because they are asked in different places, of different
    lists, on behalf of different sides - and because a single hook would let
    party content compel a PC, which nothing should.

    It reaches only the *target*. What the adversary then does to that PC - its
    standard attack, an Action feature - is still the GM's.
    """

    def register(function: Callable) -> Callable:
        _claim(_adversary_target_overrides, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def evasion_bonus(name: str, unmodelled: Iterable[str] = ()):
    """Register content that raises its holder's Evasion against an incoming attack.

    Signature: `(holder, attacker, fight) -> int` - the bonus, or 0 to decline.
    Holder-scoped: Evasion belongs to whoever is being swung at.

    **Evasion was a fixed number until this existed.** A sheet carries it already
    resolved and `Adversary.attack` read it straight off, so nothing could change
    it mid-fight - which is why the Bone card *Ferocity* ("increase your Evasion
    by the number of Hit Points they marked") had nowhere to put its effect.

    **Asked once per attack, outside the roll's closure**, which makes being asked
    the commitment - the same contract `total_roll_bonus` keeps and for the same
    reason. Ferocity's bonus lasts "until after the next attack made against
    you", so it is consumed when consulted; asking again inside a forced reroll
    would spend it twice on one attack.

    One call site, in `Adversary.attack`. An **area attack does not consult it**:
    that resolves one roll against the lowest Evasion present and then re-checks
    each target, so a per-target bonus would have to reach into `content/aoe.py`,
    which has no fight to dispatch with. Declared as a gap where content
    registers.
    """

    def register(function: Callable) -> Callable:
        _claim(_evasion_bonuses, name, function)
        _assess(name, Status.MODELLED, function.__module__, unmodelled=tuple(unmodelled))
        return function

    return register


def ally_damage_reduction(name: str, unmodelled: Iterable[str] = ()):
    """Register party content that subtracts from the raw damage a PC is taking.

    Signature: `(holder, target, amount, fight, damage_type) -> int` - how much to
    take off the number, or 0 to decline. Scanned across the conscious party,
    since `holder` and `target` are generally different PCs: Arcana's *Rune Ward*
    is the Wizard's trinket held by somebody else, and the ally who spends the
    Hope is not the one whose sheet the card is on.

    **The first hook that reaches the damage number itself**, and none of the
    three next to it can say what this says. An Armor Slot and `severity_response`
    both work in *thresholds*, moving how many HP a hit marks; `damage_multiplier`
    scales the number but cannot subtract a flat amount. "Reduce incoming damage
    by 1d8" is arithmetic on the raw total, and it lands **before the thresholds
    are read** - so it can drop a hit a whole band, or below 1 and away entirely.

    Applied after any resistance has halved the hit, which is the order the SRD
    fixes for resistance ("before comparing it to their Hit Point Thresholds")
    and the conventional one for a multiplier followed by a subtraction.

    Every registrant is asked and the reductions sum. Content decides for itself
    whether it has a claim on this particular PC - usually by a token saying who
    is carrying the thing.

    A holder-scoped twin would suit an adversary that reduces its own incoming
    damage (the Fallen Warlord's *Faltering Armor* is written that way). Nothing
    needs one yet, so there isn't one.
    """

    def register(function: Callable) -> Callable:
        _claim(_ally_damage_reductions, name, function)
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


def ally_on_roll(name: str, unmodelled: Iterable[str] = ()):
    """Register content that responds to *any* party member's action roll.

    Signature: `(holder, roller, roll, fight) -> None`. Scanned across the
    conscious party rather than across whoever rolled, because `holder` and
    `roller` are generally different PCs. The Valor card Lean on Me ("when you
    console or inspire an ally who failed an action roll, you can both clear 2
    Stress") is the reason it exists.

    **Distinct from `on_roll` next door, which is holder-scoped.** That one fires
    only for its own holder's rolls, which is right for a card keyed on how *your*
    roll came out. This is for content whose trigger is somebody else's roll, and
    holder-scoping it would mean the card only ever fired on the consoler's own
    failures - which is precisely the roll the card is not about.

    **Not `reroll`, either**, though that hook is also party-wide and also sees
    another PC's roll. It exists to *replace* a roll and its contract is that the
    first offer wins and the rest are never asked; content that only wants to
    watch would have to decline in a way that still had side effects, which is the
    one thing every hook here forbids. Watching and rewriting are kept apart for
    the reason `on_party_attack_roll` and `convert_party_roll` are.

    Fires once per action roll, from the same place `on_roll` does - after any
    GM-side conversion, so every registrant reads the roll the fight actually
    used. Content is expected to check `holder is not roller` itself if it means
    an ally's roll rather than anybody's.
    """

    def register(function: Callable) -> Callable:
        _claim(_ally_on_rolls, name, function)
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


def out_of_combat_ability(name: str, reason: str) -> None:
    """Declare that `name` is used **between** fights rather than during one.

        out_of_combat_ability(
            "A Soldier's Bond",
            "Once per long rest, complimenting an ally gives you both 3 Hope.
             Players don't stop mid-fight to do it; they do it between
             encounters, so it belongs to the sequenced-encounter machinery
             that doesn't exist yet.",
        )

    Not a dismissal. Both dismissals say the fight is unaffected - one because
    the effect has nothing here to touch, the other because it is too small to
    matter. This says neither: the effect is real, fully representable, and would
    change a fight it was used in. It simply isn't used in one.

    Which makes this state a **to-do list**, and the reason it must not be filed
    as no-combat-effect. Encounters run one at a time today; the plan is to run
    them in sequence, sharing a party's state and their rests (see
    `combat/rest.py` and `rest-state-belongs-on-the-encounter`). When that lands,
    everything declared here is what the party does in the gaps.

    Like every assessment it is the user's call, not the assistant's.
    """
    _assess(name, Status.OUT_OF_COMBAT, _calling_module(), reason=reason)


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


def apply_ally_on_roll(roller: Holder, roll, fight: Fight = None) -> None:
    """Let any PC's content respond to `roller`'s action roll. Everyone gets a say.

    The party-wide twin of `apply_on_roll`, and no short-circuit: two PCs each
    carrying something that fires off an ally's failure should both fire, since
    neither is choosing between them.

    Called from the same place its holder-scoped twin is, so both read the roll
    the fight actually used - after any GM-side conversion.
    """
    _discover()
    for holder, respond in _party_offers(fight, _ally_on_rolls):
        respond(holder, roller, roll, fight)


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


def _gm_offers(fight: Fight, table: dict[str, Callable]) -> list[tuple[object, Callable]]:
    """Every (adversary, content) pair in `table` the GM's side can offer, shuffled.

    The mirror of `_party_offers`, for content that reaches across the table in
    the other direction, and shuffled for the same reason: which of two Hexers
    pays the Stress to curse a roll must not be decided by the order an encounter
    happened to list them in.

    The shuffle is skipped when there is nothing to choose between, exactly as
    `_party_offers` skips it - drawing from the global RNG when no choice exists
    would shift the dice for every fight containing an adversary that carries
    none of this content.
    """
    if fight is None:
        return []

    offers: list[tuple[object, Callable]] = [
        (adversary, found)
        for adversary in fight.living_adversaries
        for name in adversary.named_features
        if (found := _registered(table, name)) is not None
    ]
    if len(offers) > 1:
        random.shuffle(offers)
    return offers


def granted_attack_advantage(holder, target, fight=None):
    """Everything this combatant carries that changes the state of their attack.

    Returns an `AdvantageState`, `NONE` when nothing answers. Folded together
    rather than first-answer-wins, so a holder with two sources of Advantage and
    one of Disadvantage lands where the SRD puts them.
    """
    _discover()
    states = []
    for name in holder.named_features:
        grants = _registered(_attack_advantages, name)
        if grants is not None:
            state = grants(holder, target, fight)
            if state is not None:
                states.append(state)
    return combined(*states) if states else AdvantageState.NONE


def incoming_damage_multiplier(target, attacker, fight: Fight = None) -> float:
    """How much the GM's side multiplies this damage by before thresholds.

    One, unless something on the field says otherwise. Asked of the living
    adversaries rather than of either combatant in the attack - see
    `damage_multiplier` for why the content is a third party to it.

    May come back a fraction as well as a whole number, since content can halve
    as well as double. The caller floors once, after everything has multiplied.
    """
    _discover()
    multiplier: float = 1
    for adversary, contribute in _gm_offers(fight, _damage_multipliers):
        answer = contribute(adversary, target, attacker, fight)
        if answer:
            multiplier *= answer
    return multiplier


def resistance_to(target, damage_type=None, fight: Fight = None) -> float:
    """How much of a hit of this type reaches `target`, as a factor.

    `UNREDUCED` unless something the target carries says otherwise; a half for a
    resistance, nothing at all for an immunity. Where several answer, the
    strongest single one applies rather than the product - resistances do not
    stack in Daggerheart.

    **Untyped damage is never reduced**, the same rule the severity hooks follow:
    a hit that arrives with no type matches nothing, so it resolves in full
    rather than raising. See `content/damage_types.py`.

    Asked of the target rather than of the field, unlike
    `incoming_damage_multiplier`: a resistance is something the creature being
    hit has, not something a third party imposes.

    **A hit that is both physical and magic is offered as each in turn**, and the
    strongest answer applies - so resisting either halves a Spellblade's swing,
    which is the ruling `content/damage_types.py` records. Registrants therefore
    never see the pair and can keep asking about one type at a time.
    """
    kinds = types_in(damage_type)
    if not kinds:
        return UNREDUCED

    _discover()
    factors = []
    for name in target.named_features:
        resist = _registered(_damage_resistances, name)
        if resist is None:
            continue
        for kind in kinds:
            answer = resist(target, kind, fight)
            if answer is not None:
                factors.append(answer)
    return strongest(factors)


def party_attack_is_hobbled(attacker, target, weapon, fight: Fight = None) -> bool:
    """Whether anything on the GM's side makes this particular attack Disadvantaged.

    False unless something says otherwise. Asked once, immediately before a PC's
    weapon roll, and everything registered gets asked - there is no short-circuit,
    because Disadvantage doesn't stack and a second answer costs nothing.

    One call site, in `items/weapons.py`. Content that rolls an attack of its own
    doesn't consult it, which is declared as a gap where such content registers.
    """
    _discover()
    for adversary, hobbles in _gm_offers(fight, _party_attack_disadvantages):
        if hobbles(adversary, attacker, target, weapon, fight):
            return True
    return False


def attacks_on_are_aided(target, fight: Fight = None) -> bool:
    """Whether anything on the GM's side hands attacks on `target` Advantage.

    False unless something says otherwise. The mirror of
    `party_attack_is_hobbled`, and asked the same way: everything registered gets
    its say and there is no short-circuit, because Advantage doesn't stack and a
    second answer costs nothing.

    One call site, in `combat/policy.py`'s `adversary_attack_advantage`, where it
    is folded together with the target being Vulnerable and anything the attacker
    itself carries.
    """
    _discover()
    for adversary, aids in _gm_offers(fight, _attack_advantages_against):
        if aids(adversary, target, fight):
            return True
    return False


def forced_party_target(attacker: Holder, fight: Fight = None):
    """The adversary GM-side content compels `attacker` to swing at, if any.

    None unless something answers, in which case the party's own targeting rule
    applies as usual. The first answer wins - see `party_target_override`.

    One call site, in `combat/policy.py`'s `take_pc_turn`, so a compelled PC's
    target is settled before any of the options are offered a roll.
    """
    _discover()
    for adversary, compel in _gm_offers(fight, _party_target_overrides):
        forced = compel(adversary, attacker, fight)
        if forced is not None:
            return forced
    return None


def apply_on_party_attack_roll(roller: Holder, roll, fight: Fight = None) -> None:
    """Let GM-side content respond to a PC's attack roll. Everything gets its say."""
    _discover()
    for adversary, respond in _gm_offers(fight, _on_party_attack_rolls):
        respond(adversary, roller, roll, fight)


def converted_party_roll(roller: Holder, roll, fight: Fight = None):
    """Give the GM's side a chance to rewrite how a PC's roll came out.

    Returns the roll to carry on with - the rewritten one if anything offered a
    rewrite, otherwise the roll it was given, so the caller can use the result
    unconditionally. At most one conversion applies.

    Called once, at the point the outcome is spent, so everything that reads a
    roll's Hope or Fear reads the same answer.
    """
    _discover()
    for adversary, convert in _gm_offers(fight, _party_roll_conversions):
        replacement = convert(adversary, roller, roll, fight)
        if replacement is not None:
            return replacement
    return roll


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
    that rolls its own attack is expected to offer it here, the same contract
    that already applies to `total_roll_bonus` - and for a Spellcast Roll that is
    free, since `content/spellcast.py` does it for every card in every domain.
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


def total_ally_extra_damage(attacker: Holder, target, roll, fight=None) -> list:
    """Every extra die the *party's* content adds to this attack, from anybody.

    The party-wide twin of `total_extra_damage`, and asked from the same place so
    the dice join one roll and cross the target's thresholds once. Everything
    registered gets its say and the answers accumulate - two PCs each marking the
    same target would both pay out, which is what "when a creature attacks a
    target who is Vulnerable in this way" says.

    Empty without a fight, since there is no party to scan.
    """
    _discover()
    groups: list = []
    for holder, contribute in _party_offers(fight, _ally_extra_damage):
        groups.extend(contribute(holder, attacker, target, roll, fight))
    return groups


def reroll_damage_dice(holder, roll, fight=None):
    """Let content re-throw individual dice of a damage roll that has just landed.

    Returns the roll to carry on with - a copy with the new results if anything
    was rerolled, otherwise the roll it was given, so a caller can use the result
    unconditionally. The same contract `remake_action_roll` keeps for the attack
    roll, one step further down.

    Every registrant is asked about every die and the answers are OR-ed, with no
    short-circuit: being asked is what lets content that pays for a reroll know
    it happened, and skipping the second responder once the first said yes would
    leave it out of step. Each die is offered exactly one fresh throw.

    Called wherever a *PC* rolls damage. `roll_damage` itself doesn't ask,
    deliberately: dice/ knows nothing about content, and a `reroll_below=`
    parameter existing because of one card is the coupling this registry is for.
    """
    _discover()
    responders = [
        found
        for name in holder.named_features
        if (found := _registered(_damage_die_rerolls, name)) is not None
    ]
    if not responders:
        return roll

    results = [list(group_results) for group_results in roll.die_results]
    rerolled = False
    for group, group_results in zip(roll.dice_groups, results):
        for index, value in enumerate(group_results):
            # Listed, not generated: every responder is asked about every die.
            answers = [again(holder, group.sides, value, fight) for again in responders]
            if any(answers):
                group_results[index] = random.randint(1, group.sides)
                rerolled = True

    return replace(roll, die_results=results) if rerolled else roll


def maximise_damage_dice(holder, roll, fight=None):
    """Let content buy the top face of **one** die of a damage roll just made.

    Returns the roll to carry on with - a copy with that die read as its maximum
    if anything claimed one, otherwise the roll it was given, so a caller can use
    the result unconditionally. The same contract `reroll_damage_dice` keeps, and
    called immediately after it.

    **Dice are offered worst-first**, by how far each is from its own top face,
    and the first one a responder accepts ends the scan. Versatile Fighter
    maximises one die and does not say which, so offering them in the order they
    were rolled would make a card's value depend on which die of a pool happened
    to come up badly. A d12 showing 3 is offered before a d6 showing 4.

    Ties keep the order the dice were rolled in, which is stable rather than
    arbitrary: two dice equally far from their maximum are worth the same, so
    there is nothing for a shuffle to decide between.
    """
    _discover()
    responders = [
        found
        for name in holder.named_features
        if (found := _registered(_damage_die_maximums, name)) is not None
    ]
    if not responders:
        return roll

    results = [list(group_results) for group_results in roll.die_results]

    # (shortfall, group index, die index), worst first. `sorted` is stable, so
    # equal shortfalls stay in rolled order.
    offers = sorted(
        (
            (group.sides - value, group_index, die_index)
            for group_index, (group, group_results) in enumerate(
                zip(roll.dice_groups, results)
            )
            for die_index, value in enumerate(group_results)
        ),
        key=lambda offer: -offer[0],
    )

    for shortfall, group_index, die_index in offers:
        if shortfall <= 0:
            # Already showing its top face. Nothing to buy, and offering it would
            # let content spend a Stress on no change at all.
            break
        group = roll.dice_groups[group_index]
        value = results[group_index][die_index]
        if any(claim(holder, group.sides, value, fight) for claim in responders):
            results[group_index][die_index] = group.sides
            return replace(roll, die_results=results)
    return roll


def extra_armor_slots(
    holder, amount: int, hp_to_mark: int, fight=None, damage_type=None
) -> int:
    """How many *additional* Armor Slots this holder marks against the hit.

    Zero unless something they carry says otherwise, and the answers sum - two
    cards each buying a slot buy two. The caller is responsible for clamping to
    the slots actually free; content here says what it wants, not what fits.

    Asked only where a free Armor Slot has already been marked, which is the
    trigger the SRD writes for the one registrant. See `extra_armor_slot`.
    """
    _discover()
    total = 0
    for name in holder.named_features:
        contribute = _registered(_extra_armor_slots, name)
        if contribute is not None:
            total += contribute(holder, amount, hp_to_mark, fight, damage_type)
    return total


def total_help_bonus(helper: Holder, roller: Holder, fight: Fight = None) -> int:
    """Everything `helper` carries that adds to the roll they are helping with.

    Zero unless something answers, and the answers sum. Holder-scoped on the
    helper rather than the roller - see `help_bonus` - and asked once, after the
    helper has been chosen and has paid their Hope.
    """
    _discover()
    total = 0
    for name in helper.named_features:
        contribute = _registered(_help_bonuses, name)
        if contribute is not None:
            total += contribute(helper, roller, fight)
    return total


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


def death_move_prevented(target, fight: Fight = None) -> bool:
    """Whether party content stops `target` taking their death move right now.

    False unless something answers, and the first answer wins - see
    `death_move_ward`. Content that averts the death move has already done
    whatever it does instead by the time this returns.

    False without a fight, since there is no party to scan.
    """
    _discover()
    for holder, ward in _party_offers(fight, _death_move_wards):
        if ward(holder, target, fight):
            return True
    return False


def adversary_attack_is_hobbled(attacker, target, fight: Fight = None) -> bool:
    """Whether party content makes this adversary's attack Disadvantaged.

    False unless something says otherwise. The mirror of
    `party_attack_is_hobbled`, and asked the same way: everything registered gets
    its say and there is no short-circuit, because Disadvantage doesn't stack and
    a second answer costs nothing.

    One call site, in `combat/policy.py`'s `adversary_attack_advantage`, where it
    is folded together with the other three sources rather than overriding them.
    """
    _discover()
    for holder, hobbles in _party_offers(fight, _adversary_attack_disadvantages):
        if hobbles(holder, attacker, target, fight):
            return True
    return False


def apply_attack_missed(target, attacker, roll, fight: Fight = None) -> None:
    """Let the target's own content respond to an attack that just failed.

    Holder-scoped on `target`, which is who the SRD writes such a Reaction for -
    see `attack_missed`. Everything registered is asked and nothing
    short-circuits: a miss is not a resource anybody is competing for.
    """
    _discover()
    for name in target.named_features:
        respond = _registered(_attack_misses, name)
        if respond is not None:
            respond(target, attacker, roll, fight)


def apply_on_hit(holder: Holder, target, result, fight: Fight) -> None:
    """Let every on-hit ability in the loadout respond to a landed attack."""
    _discover()
    for name in holder.named_features:
        respond = _registered(_on_hits, name)
        if respond is not None:
            respond(holder, target, result, fight)


def forced_adversary_target(adversary, fight: Fight = None):
    """The PC party content compels `adversary` to swing at, if any.

    None unless something answers, in which case the GM's own targeting rule
    applies as usual. The first answer wins - two PCs both enrapturing the same
    adversary is not a state the SRD has.

    One call site, in `combat/policy.py`'s `choose_adversary_target`.
    """
    _discover()
    for holder, compel in _party_offers(fight, _adversary_target_overrides):
        forced = compel(holder, adversary, fight)
        if forced is not None:
            return forced
    return None


def total_evasion_bonus(target, attacker, fight: Fight = None) -> int:
    """Everything `target` carries that raises their Evasion against this attack.

    Zero unless something answers, and the answers sum. Consulted once per
    attack, before the roll is made - see `evasion_bonus` for why that is the
    commitment rather than a free question.
    """
    _discover()
    total = 0
    for name in target.named_features:
        contribute = _registered(_evasion_bonuses, name)
        if contribute is not None:
            total += contribute(target, attacker, fight)
    return total


def party_damage_reduction(target, amount: int, fight: Fight = None, damage_type=None) -> int:
    """How much party content takes off the damage `target` is about to suffer.

    Zero unless something answers. Every registrant is asked and the answers sum,
    since two wards on one hit each reduce it - nothing in the SRD says otherwise
    and taking only the largest would be inventing a rule.

    Called from `PlayerCharacter.take_damage`, after any resistance and before
    the thresholds are read. Never floored here: the caller clamps the damage,
    because "reduced below zero" and "reduced to zero" are the same hit.
    """
    _discover()
    total = 0
    for holder, reduce in _party_offers(fight, _ally_damage_reductions):
        total += reduce(holder, target, amount, fight, damage_type)
    return total


def apply_ally_on_hit(attacker, target, result, fight: Fight = None) -> None:
    """Let party content respond to a landed attack made by *anyone* in the party.

    The party-wide counterpart of `apply_on_hit`, called from the same place and
    on the same trigger. Everything registered is asked; content decides for
    itself whether this particular attack is one it has a claim on.

    Note the scope is the *conscious* party, so a caster who has gone down stops
    maintaining what they cast. That falls out of `_party_offers` rather than
    being a rule anyone wrote, and it is the sensible reading of a held spell.
    """
    _discover()
    for holder, respond in _party_offers(fight, _ally_on_hits):
        respond(holder, attacker, target, result, fight)


def soften_damage(
    character: Holder, amount: int, hp_to_mark: int, fight=None, damage_type=None
) -> int:
    """Let every damage-response this character carries soften a hit.

    Called once by PlayerCharacter.take_damage. Each response sees what the
    previous one left, so two reductions stack.

    Scans everything the sheet names rather than only the domain-card loadout: a
    class feature softens a hit exactly the way a card does (Unstoppable reduces
    the severity of every hit while it's running), and nothing about this hook
    cares which kind of content registered it.

    `damage_type` is the `DamageType` the hit arrived with, or None, and is
    passed to every response - see `severity_response` for why the type travels
    as an argument rather than as a filter here.
    """
    _discover()
    for name in character.named_features:
        respond = _registered(_severity_responses, name)
        if respond is not None:
            hp_to_mark = respond(character, amount, hp_to_mark, fight, damage_type)
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


def apply_on_attacked(
    holder, attacker, weapon, damage=0, hp_marked=0, fight=None
) -> None:
    """Let content the *target* carries respond to a successful attack on them."""
    _discover()
    for name in holder.named_features:
        respond = _registered(_on_attacked, name)
        if respond is not None:
            respond(holder, attacker, weapon, damage, hp_marked, fight)


def apply_before_attacked(holder, attacker, weapon, fight=None) -> None:
    """Let content the *target* carries interrupt an attack about to be rolled.

    Nothing it does can stop the attack; see `before_attacked` for why.
    """
    _discover()
    for name in holder.named_features:
        respond = _registered(_before_attacked, name)
        if respond is not None:
            respond(holder, attacker, weapon, fight)


def apply_on_spotlight(holder, fight=None) -> None:
    """Let content fire on its holder taking the spotlight, before they act."""
    _discover()
    for name in holder.named_features:
        respond = _registered(_on_spotlight, name)
        if respond is not None:
            respond(holder, fight)


def skips_spotlight(holder, fight=None) -> bool:
    """Whether anything this combatant carries spends their activation on nothing.

    False unless something says otherwise. Everything registered is asked - none
    of them may be skipped once one answers True, because being asked is the
    commitment and content that alternates flips its own state when consulted.
    Short-circuiting would leave a second such feature out of step with the
    turn it thinks it is on.
    """
    _discover()
    skipped = False
    for name in holder.named_features:
        prepares = _registered(_skip_spotlight, name)
        if prepares is not None and prepares(holder, fight):
            skipped = True
    return skipped


def spotlights_while_defeated(holder, fight=None) -> bool:
    """Whether the GM may still spotlight this combatant now that it is down.

    False unless something it carries says otherwise. Asked by the GM turn when
    it builds its list of candidates, and only ever of a defeated combatant - so
    for every adversary in the catalogue but one this is never reached at all.
    """
    _discover()
    for name in holder.named_features:
        allows = _registered(_spotlight_while_defeated, name)
        if allows is not None and allows(holder, fight):
            return True
    return False


def standard_attack_damage(holder, target, roll=None, fight=None):
    """The dice this combatant's standard attack should roll instead, if any.

    Returns `(dice_groups, modifier)` or None. First answer wins: nothing in the
    SRD gives one adversary two of these, and combining two replacements would be
    inventing a rule rather than following one.

    `roll` is the attack roll that landed, for content keyed on how it came out.
    """
    _discover()
    for name in holder.named_features:
        swap = _registered(_standard_damage, name)
        if swap is not None:
            replacement = swap(holder, target, roll, fight)
            if replacement is not None:
                return replacement
    return None


def standard_attack_damage_type(holder):
    """The type this combatant's standard attack deals instead, if anything says.

    None unless content answers; first answer wins, since nothing in the SRD
    gives one stat block two of these and combining two would be inventing a
    rule. One call site, in `Adversary.type_of_damage`.
    """
    _discover()
    for name in holder.named_features:
        override = _registered(_standard_damage_types, name)
        if override is not None:
            stated = override(holder)
            if stated is not None:
                return stated
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


def harden_damage(
    character, amount: int, hp_to_mark: int, fight=None, damage_type=None
) -> int:
    """Let everything this combatant carries make an incoming hit cost more.

    The mirror of `soften_damage`, and called immediately after it by whoever is
    taking the damage - both sides of the table, since an adversary's Weak
    Structure and a PC's armor are the same shape of thing pointed in opposite
    directions.

    Running second is what makes "when you mark HP" honest: by the time this is
    asked, the softening has had its say, so a hit fully absorbed by armor and a
    domain card is sitting at zero and content that only fires on a real mark can
    see that.

    `damage_type` travels the same way it does through `soften_damage`, and for
    the same registrants' sake: the Construct's Weak Structure is physical-only.
    """
    _discover()
    for name in character.named_features:
        respond = _registered(_severity_increases, name)
        if respond is not None:
            hp_to_mark = respond(character, amount, hp_to_mark, fight, damage_type)
    return hp_to_mark


def refuses_condition(holder, condition, fight=None) -> bool:
    """Whether anything `holder` carries stops `condition` landing at all.

    False unless something says otherwise, and the first refusal wins - once a
    condition has been refused there is nothing left for a second piece of content
    to refuse, and asking on would charge two per-rest uses for one dodge.

    One call site, in `FightState.apply_condition`, which is what makes "when you
    would gain a condition" a moment content can be asked about. See
    `condition_refusal` for why this is not `is_immune_to`.
    """
    _discover()
    for name in holder.named_features:
        refuse = _registered(_condition_refusals, name)
        if refuse is not None and refuse(holder, condition, fight):
            return True
    return False


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
