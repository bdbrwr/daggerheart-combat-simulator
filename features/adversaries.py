"""Adversary features.

Registered under the feature's own name, namespaced - `adversary:Climber`. See
features/weapons.py for why the namespace exists. A stat block in
`adversaries/*.json` names its features and they resolve here, exactly the way a
character sheet names its domain cards.

Both halves of the file matter. The implementations at the top are reached
through the same dispatch a PC's domain cards use - an adversary satisfies the
`Holder` shape well enough for `named_features` to be scanned, so no hook needed
an adversary-specific twin. The declarations at the bottom are features assessed
and knowingly not run.

## Why the dismissals below are dismissals rather than gaps

None of them runs any code, and none is `unimplemented`, because
`unimplemented` means work nobody has done - and these were assessed. Two of
them are dismissed as **insignificant** rather than as having no effect at all,
which is the distinction that state exists for. Damage is something the simulator
represents completely, so there is no question of the effect having nothing to
touch - both really do swap in a bigger damage die. What settles them is the
*size* of the swap, which is why each reason states a number.

Contrast `Climber` and `Overwhelming Force`, which are the other kind: their
whole effect is where a combatant stands or ends up, and no position is tracked
at all. There is nothing to measure, so there is no number in their reasons.

The reason it settles it is the shape of Daggerheart's damage rules. Damage
becomes marked HP through **threshold bands**, not linearly - a hit marks 1, 2 or
3 HP depending on which side of the Major and Severe thresholds it lands. A point
or two of expected damage moves a roll within a band far more often than across
one, so an expected-damage bump this small is very nearly invisible in the only
number that reaches the fight.
"""

import random
from dataclasses import replace

from adversaries.catalogue import parse_dice
from adversaries.registry import find_adversary
from combat.results import AttackResult
from content.aoe import Range, chance_within, targets_in_area, targets_reached
from content.conditions import (
    BEFORE_AN_ACTION_ROLL,
    POISONED,
    RESTRAINED,
    VULNERABLE,
    Condition,
    until_they_clear_hp,
    when_they_act,
)
from content.damage_types import RESISTED, DamageType
from content.names import ADVERSARY, canonical, qualified
from content.registry import (
    Fight,
    action,
    activation_limit,
    apply_on_hit,
    attack_advantage,
    attack_area,
    before_attacked,
    convert_party_roll,
    damage_bonus,
    damage_multiplier,
    damage_resistance,
    deals_direct_damage,
    difficulty_bonus,
    direct_damage,
    feature_parameter,
    force_adversary_reroll,
    insignificant_combat_effect,
    no_combat_effect,
    on_attacked,
    on_damaged,
    on_hit,
    on_party_attack_roll,
    on_spotlight,
    severity_increase,
    skip_spotlight,
    spotlight_cost,
    standard_damage,
)
from dice.common import AdvantageState
from dice.d20 import roll_d20
from dice.damage import DiceGroup, roll_damage
from dice.duality import DualityOutcome, roll_duality


def _damage_spec(written: str) -> tuple[list[DiceGroup], int]:
    """A printed damage expression like `1d4+1` as dice plus a flat modifier.

    A catalogue entry keeps the two in separate keys, so an encounter can tune
    them independently. A *feature's* parameter can't: it is the book's own text,
    and the book writes `Horde (1d4+1)`. This splits the flat terms off and hands
    the rest to the catalogue's `parse_dice`, which stays the one place that
    knows what a die looks like.

    Raises the same way `parse_dice` does, so a stat block with an unreadable
    parameter fails where it is written rather than rolling something else.
    """
    dice_terms: list[str] = []
    modifier = 0
    for term in str(written).split("+"):
        term = term.strip()
        if not term:
            continue
        if term.isdigit():
            modifier += int(term)
        else:
            dice_terms.append(term)
    return parse_dice(dice_terms, "a feature's parameter", written), modifier

# SIMULATION RULE - policy. A feature whose point is applying a condition is not
# used against a target that already has it: re-applying changes nothing, and
# whether somebody is already Poisoned or Cursed is plainly visible at a table.
# The check lives in each such feature rather than in shared machinery, because
# *which* features those are is a reading of the printed text - the feature knows
# it about itself.
#
# There used to be a `CONDITION_ATTACK_EV_MARGIN` here, gating that check on the
# feature being worse than the standard attack by 2 or more expected damage. It
# is gone, on the user's ruling: nothing at a table computes the expected value
# of two damage pools and compares them, so a policy may not turn on it. That is
# the same principle that keeps the Faerie's Wings unmodelled, applied to the
# GM's side. See SIMULATION-RULES.md.

# --- Parameterised features --------------------------------------------------
#
# The SRD prints some of these with the number baked into the name -
# `Relentless (3)`, `Relentless (2)`. That is one feature with an argument, so it
# registers once under its base name and reads X off whichever stat block is
# carrying it. See content/names.py for the matching, and `feature_parameter`
# for the reading.

RELENTLESS = qualified(ADVERSARY, "Relentless")


@activation_limit(RELENTLESS)
def relentless(adversary, fight: Fight) -> int | None:
    """This adversary can be spotlighted up to X times per GM turn.

    SRD: "The Burrower can be spotlighted up to three times per GM turn. Spend
    Fear as usual to spotlight them."

    Only the limit lives here. The Fear is charged by the GM turn, which already
    pays for every activation past the first - that's what "as usual" means, and
    duplicating it here would charge twice.

    A stat block naming Relentless without a number gets nothing rather than a
    guess: the number is the whole of the feature, and inventing one would
    quietly make an adversary more dangerous than the page says.
    """
    written = feature_parameter(adversary, RELENTLESS)
    if written is None:
        return None
    try:
        return int(written)
    except ValueError:
        return None


FLYING = qualified(ADVERSARY, "Flying")


@difficulty_bonus(FLYING)
def flying(adversary) -> int:
    """+X to this adversary's Difficulty.

    SRD: "While flying, the Mosquitoes have a +2 bonus to their Difficulty."

    Parameterised as `Flying (X)` although the SRD prints the name bare, for two
    reasons. The bonus is not the same number on every flier the book prints, and
    - more usefully - the parameter is where the "while flying" qualifier goes.
    Nothing here tracks whether an adversary is currently airborne, so rather
    than invent a per-round check, the *average* uplift is authored: a creature
    in the air the whole fight is written `Flying (2)`, and one up half the time
    would be written `Flying (1)`. Across a high-N run those land in the same
    place, and the knob sits in the JSON where an author can reach it.

    The bonus is resolved into `Adversary.difficulty` at spawn time, so every
    roll made against this adversary already accounts for it without any of the
    four places that read Difficulty knowing this feature exists. See
    `content/registry.py`'s `difficulty_bonus` and `Adversary.spawn`.

    A stat block writing `Flying` with no number gets nothing rather than a
    guess, exactly as Relentless does - the number is the whole of the feature.
    """
    written = feature_parameter(adversary, FLYING)
    if written is None:
        return 0
    try:
        return int(written)
    except ValueError:
        return 0


MOMENTUM = qualified(ADVERSARY, "Momentum")


@on_hit(MOMENTUM)
def momentum(adversary, target, result, fight: Fight) -> None:
    """When this adversary makes a successful attack against a PC, gain a Fear.

    SRD: "When the Bear makes a successful attack against a PC, you gain a Fear."

    Dispatch only reaches an on-hit rider once the attack has landed, so the
    success is already established by the time this runs.

    Worth knowing what this does to the economy: Fear buys extra activations, so
    an adversary with Momentum partly pays for its own next turn. It's the first
    thing in the simulator that hands the GM Fear from anywhere other than a PC
    rolling with Fear.
    """
    gained = fight.gain_fear(1)
    if gained:
        fight.note(f"{adversary.name} presses the advantage (Momentum: GM gains a Fear)")


WEAK_STRUCTURE = qualified(ADVERSARY, "Weak Structure")


@severity_increase(WEAK_STRUCTURE)
def weak_structure(
    adversary, amount: int, hp_to_mark: int, fight=None, damage_type=None
) -> int:
    """When this adversary marks HP from physical damage, they mark another.

    SRD: "When the Construct marks HP from physical damage, they must mark an
    additional HP."

    **Physical only**, which used to be a declared gap and is now enforced: the
    type reaches this hook as an argument. Untyped damage does not qualify - a
    restriction matches only a type that was actually stated - so the Construct
    is never worsened by a hit nobody typed.

    Keyed on HP actually being marked, not on damage being dealt - a hit that
    softened away to nothing didn't mark anything, so there is nothing to add to.
    Running after `soften_damage` is what makes that check meaningful; see
    `severity_increase`.

    On a 9 HP track this is worth a lot: it turns a Major hit into 3 HP and a
    Severe into 4, so the Construct dies to roughly two thirds of the hits its
    HP suggests. That is the trade the stat block is making for its 1d20 attack.
    Now that the restriction bites, a party carrying magic damage is the answer
    to it - which is the choice the printed page was offering all along.
    """
    if damage_type is not DamageType.PHYSICAL:
        return hp_to_mark
    if hp_to_mark <= 0:
        return hp_to_mark
    return hp_to_mark + 1


# --- Reaction rolls ----------------------------------------------------------
#
# A Reaction Roll is Duality Dice plus a trait, and that is all it is: the
# Hope/Fear outcome is **not** read. Nobody gains a Hope, the GM gains no Fear,
# and the spotlight doesn't move - it isn't an action roll, and only an action
# roll does any of that. So a feature calls `roll_duality` directly and looks at
# `is_success` and `is_critical`, and nothing else.
#
# A critical ignores the effect entirely - not just the part a success avoids.
# Where a failure is "15 damage and Vulnerable" and a success is "5 damage", a
# critical is "nothing at all".
#
# SIMULATION RULE - policy. Where the SRD prints no Difficulty for a reaction
# roll, the adversary's own Difficulty is used. It is the number already on the
# stat block and it scales with tier, which makes it the least invented option
# available - but it is invented, and it is a knob.


def _reaction_roll(combatant, trait: str, difficulty: int, fight=None):
    """One combatant's Reaction Roll against `difficulty`, using `trait`.

    **Both sides of the table make these, on different dice.** A PC rolls Duality
    Dice plus the named trait, as they do for everything. An adversary rolls a
    **flat d20 with no modifier**: stat blocks carry no traits, so there is
    nothing to add and `trait` is only which roll the page called for.

    Which one is chosen by whether the combatant has traits at all, rather than
    by asking what kind of thing it is - the same duck-typing the damage hooks
    already rely on, and it keeps this from importing either class.

    Not a wrapper around a roller: `roll_duality` and `roll_d20` are each called
    here, at the site that needs them, and this only works out the modifier and
    the state to roll in. A PC whose sheet doesn't carry the trait rolls at +0
    rather than failing to roll, since every sheet carries all six and a missing
    one is a malformed sheet rather than a rule.

    A condition that hobbles the trait applies here as much as it does to an
    attack - "disadvantage on Agility Rolls" covers the Agility Reaction Roll a
    PC makes to keep their feet - which is why `fight` is in the signature. It
    reaches only the duality branch, because a hobble names a trait and an
    adversary has none. `fight` stays optional so a roll can be made without one.

    Both result types answer `is_success` and `is_critical`, which is all any
    caller reads - so a feature never has to know which side rolled.

    The number this d20 is checked against is a **Difficulty**, and it is passed
    into `roll_d20`'s `evasion` parameter. That is deliberate and ruled: the
    parameter is named for the use it has almost everywhere - an attack against a
    PC's Evasion - rather than renamed to something generic for the sake of this
    one caller. It is a number to beat either way, and the alternative traded a
    clear name at dozens of call sites for a vague one.
    """
    traits = getattr(combatant, "traits", None)
    if traits is None:
        return roll_d20(modifier=0, evasion=difficulty)

    disadvantaged = fight is not None and fight.disadvantaged_on(combatant, trait)
    return roll_duality(
        modifier=traits.get(trait, 0),
        difficulty=difficulty,
        advantage_state=(
            AdvantageState.DISADVANTAGE if disadvantaged else AdvantageState.NONE
        ),
    )


# --- Breaking free -----------------------------------------------------------
#
# Several of the SRD's conditions end on a roll the held creature makes, and the
# ruling is that those are **modelled** rather than declared as gaps: the PC tries
# the check at each moment the loop announces, exactly as the Giant Scorpion's
# Poison already offers its Knowledge Roll. What stays unmodelled is only the
# *cost* of trying - a PC spending their spotlight on it - since the attempt is
# folded into the announced moments instead of taking a turn.


def _breaks_free(
    traits: tuple[str, ...], difficulty: int, also_clear: tuple[str, ...] = ()
):
    """A condition that lifts when its holder succeeds on a Reaction Roll.

    `traits` is every trait the printed text offers as a way out, and the PC
    rolls the **best** of them - the SRD lets the player choose, and a player
    chooses the one they are good at. A single-trait escape passes a 1-tuple.

    `also_clear` names conditions that lift with this one, for a feature that
    applies two at once and frees both together ("break free, clearing both
    conditions"). They are cleared here rather than each carrying its own
    predicate, because two predicates would roll separately and could desync -
    a creature half-freed from one hold is not a state the SRD has.
    """

    def ended(holder, fight, moment: str) -> bool:
        # The best of the traits offered, since the player would choose. An
        # adversary has none and rolls a flat d20, so any of them names the same
        # roll and the first will do.
        carried = getattr(holder, "traits", {})
        trait = max(traits, key=lambda name: carried.get(name, 0))
        if not _reaction_roll(holder, trait, difficulty, fight).is_success:
            return False
        for name in also_clear:
            fight.clear_condition(holder, name)
        return True

    return ended


def _release_held(adversary, fight, *names: str) -> None:
    """Free everyone this adversary is holding, of every condition in `names`.

    The other way out of a hold: the SRD frees a creature automatically when the
    thing holding them is hurt badly enough. Only conditions this adversary
    applied are cleared, which is what `Condition.source` is for.
    """
    for pc in fight.conscious_party:
        for name in names:
            held = fight.condition_on(pc, name)
            if held is not None and held.source is adversary:
                fight.clear_condition(pc, name)


# --- Clauses the SRD prints on more than one stat block -----------------------
#
# Both of these are printed verbatim across several features, so the mechanic
# lives here once and each feature keeps whatever it does *around* it. This is
# not the same as sharing content: no feature's decision to fire is in here, only
# the arithmetic the page repeats word for word.


def _burn_an_armor_slot(pc, fight) -> bool:
    """Cost `pc` an Armor Slot with none of its benefit; an HP if they have none.

    "The target must mark an Armor Slot without receiving its benefits (they can
    still use armor to reduce the damage). If they can't mark an Armor Slot, they
    must mark an additional HP." The Acid Burrower's *Spit Acid* and both Oozes'
    *Acidic Form* print it identically.

    Returns whether a slot was actually marked, which is what a caller with
    something to add on the failing branch needs to know - Spit Acid hands the GM
    a Fear there and Acidic Form doesn't. The HP is forced, so it goes through
    the death check and can be the mark that drops a PC.
    """
    if pc.armor_unmarked > 0:
        pc.mark_armor_slot(1)
        return True
    pc.mark_hp_and_check_death(1)
    return False


# RULED. **Both sides make Reaction Rolls** - see `_reaction_roll` for the dice.
# So a feature that calls for one reaches whoever the printed text says it
# reaches, allies included, and they get a real chance to save.
#
# **Read the printed noun, because the SRD alternates it deliberately.** "All
# *creatures*" includes the acting adversary's own side; "all *targets*" is the
# party only. Scorched Earth says creatures and Hellfire, two stat blocks later,
# says targets - both in the same batch, which is what makes the distinction hard
# to put down to loose wording. Each feature therefore builds its own field and
# hands it here; nothing about that decision lives in this helper.


def _flames(adversary, fight, caught: list, dice, modifier: int, damage_type):
    """An area that damages whoever fails an Agility Reaction Roll, halved on a pass.

    The shape both *Scorched Earth* and *Hellfire* print: no attack roll, and a
    save for **half** rather than for nothing. Every other reaction-roll feature
    so far has offered a clean escape, which is why this is worth saying once
    here rather than twice in the features.

    **One damage roll shared by everyone caught**, the way Remake Reality and
    Rampaging Fury already do it - the page describes one patch of fire, not a
    roll per target. Half rounds down, following every other halving in the
    codebase.

    **A critical takes nothing at all**, and needs its own branch here. The
    standing rule is that a critical ignores the whole effect rather than only
    the part a success avoids - and where a success normally buys a clean escape
    that costs nothing to express, here it buys half, so "half" and "nothing"
    have come apart for the first time.

    Returns the `AttackResult` the caller should hand back: the spotlight was
    spent, but nothing rolled to hit anybody.
    """
    damage = roll_damage(dice_groups=dice, modifier=modifier)
    for creature in caught:
        roll = _reaction_roll(creature, "agility", adversary.difficulty, fight)
        if roll.is_critical:
            dealt = 0
        elif roll.is_success:
            dealt = damage.total // 2
        else:
            dealt = damage.total
        if dealt <= 0:
            fight.note(f"{creature.name} is untouched by the flames ({roll})")
            continue
        creature.take_damage(dealt, fight, damage_type=damage_type)
        shielded = "shields themselves for" if roll.is_success else "is caught for"
        fight.note(f"{creature.name} {shielded} {dealt}")
    return AttackResult(attack_roll=None, damage_roll=None)


# --- Acid Burrower -----------------------------------------------------------

EARTH_ERUPTION = qualified(ADVERSARY, "Earth Eruption")


@action(
    EARTH_ERUPTION,
    unmodelled=[
        "Earth Eruption: being knocked over, which is where a combatant ends up "
        "and so has nothing to change here. Only the Vulnerable it causes is "
        "modelled",
    ],
)
def earth_eruption(adversary, target, fight: Fight):
    """Mark a Stress: everyone Very Close makes an Agility Reaction Roll or is Vulnerable.

    SRD: "Mark a Stress to have the Burrower burst out of the ground. All
    creatures within Very Close range must succeed on an Agility Reaction Roll or
    be knocked over, making them Vulnerable until they next act."

    Returns None to decline, the same contract a PC's action content follows, so
    the Burrower falls through to its standard attack when this isn't worth it.
    Declining has to be free, so the Stress is claimed last.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table (`Adversary.will_spend_stress`); among
    the options that pass, the choice is random. Nothing else conditions it - no
    threshold on how many PCs it catches.

    **"All creatures" means the Burrower's own side too**, which is the same
    reading Acid Bath already takes of the same word - and now that adversaries
    make Reaction Rolls, they get a flat d20 to keep their feet like anybody
    else. A knocked-over adversary is Vulnerable, so every roll against it has
    Advantage: this feature can hand the party a real opening. The Burrower
    itself is excluded.

    Vulnerable ends "when they next act", which the fight loop announces after
    the PC's spotlight resolves - so a PC caught by this is still Vulnerable for
    any attack that lands before their turn comes round.
    """
    caught = targets_in_area(
        Range.VERY_CLOSE,
        list(fight.conscious_party)
        + [other for other in fight.living_adversaries if other is not adversary],
    )
    if not caught:
        return None
    if not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} bursts out of the ground (Earth Eruption)")

    for creature in caught:
        roll = _reaction_roll(creature, "agility", adversary.difficulty, fight)
        if roll.is_success:
            fight.note(f"{creature.name} keeps their feet ({roll})")
            continue
        fight.apply_condition(creature, Condition(name=VULNERABLE, end=when_they_act))
        fight.note(f"{creature.name} is knocked over, and is Vulnerable until they act")

    # Fired, so the spotlight is spent - but nothing rolled to hit anybody, which
    # is what an attack roll of None says. Returning None here would mean
    # "declined", and the Burrower would get a standard attack on top.
    return AttackResult(attack_roll=None, damage_roll=None)


SPIT_ACID = qualified(ADVERSARY, "Spit Acid")


@action(SPIT_ACID)
def spit_acid(adversary, target, fight: Fight):
    """Attack everyone within Close range for 2d6, and burn an Armor Slot.

    SRD: "Make an attack against all targets in front of the Burrower within
    Close range. Targets the Burrower succeeds against take 2d6 physical damage
    and must mark an Armor Slot without receiving its benefits (they can still
    use armor to reduce the damage). If they can't mark an Armor Slot, they must
    mark an additional HP and you gain a Fear."

    The parenthesis settles the order: the hit resolves normally first, free slot
    and all, and the burned slot comes afterwards - so a PC with one slot left
    spends it on the damage and then has none for the acid.

    USAGE POLICY - ruled. Nothing to pay, so nothing to gate: it joins the
    shuffled pool of options alongside the standard attack whenever it reaches
    anybody, and the choice among them is random. That is the standing default
    for any feature with no policy of its own - the same rule the party already
    plays by.
    """
    caught = targets_in_area(Range.CLOSE, fight.conscious_party)
    if not caught:
        return None

    result, struck = adversary.area_attack(
        caught,
        fight=fight,
        damage_dice=[DiceGroup(count=2, sides=6)],
        damage_modifier=0,
        damage_type=DamageType.PHYSICAL,
    )
    for pc in struck:
        if _burn_an_armor_slot(pc, fight):
            fight.note(f"{pc.name}'s armor is eaten away (Spit Acid: an Armor Slot)")
            continue
        # The Fear is Spit Acid's own, not part of the shared clause - the Oozes'
        # Acidic Form prints the same armor burn without it.
        fight.note(f"{pc.name} has no armor left to lose, and marks an HP")
        fight.gain_fear(1)
    return result


ACID_BATH = qualified(ADVERSARY, "Acid Bath")


@on_damaged(
    ACID_BATH,
    unmodelled=[
        "Acid Bath: the blood left on the ground, which deals 1d6 to anyone "
        "moving through it. Movement isn't modelled, so nothing ever moves "
        "through anything",
    ],
)
def acid_bath(adversary, amount: int, hp_marked: int, fight=None) -> None:
    """When this adversary takes Severe damage, everyone Close takes 1d10.

    SRD: "When the Burrower takes Severe damage, all creatures within Close range
    are bathed in their acidic blood, taking 1d10 physical damage."

    Keyed on the *damage* reaching the Severe threshold rather than on the HP it
    marked, which is what "takes Severe damage" says - the same reading Get Back
    Up already uses on the PC side, so a hit softened after the fact still counts.

    "All creatures" means allies too, and other adversaries are included for that
    reason. It's a real cost of the feature and leaving them out would flatter it.
    No attack roll is involved: the blood doesn't miss.

    That splash re-enters `take_damage`, which fires `on_damaged` again - so two
    Burrowers within Close range of each other could in principle set each other
    off. They can't: the splash is 1d10 and the trigger is a Severe threshold of
    15, so it can never re-trigger itself. Worth knowing before writing a feature
    whose reaction can reach its own trigger.
    """
    if fight is None or amount < adversary.severe_threshold:
        return

    splashed = targets_in_area(
        Range.CLOSE,
        list(fight.conscious_party)
        + [other for other in fight.living_adversaries if other is not adversary],
    )
    if not splashed:
        return

    fight.note(f"{adversary.name} sprays acidic blood (Acid Bath)")
    for caught in splashed:
        damage = roll_damage(dice_groups=[DiceGroup(count=1, sides=10)], modifier=0)
        caught.take_damage(damage.total, fight, damage_type=DamageType.PHYSICAL)
        fight.note(f"{caught.name} is bathed in it for {damage.total}")


# --- Bear --------------------------------------------------------------------

BITE = qualified(ADVERSARY, "Bite")


@action(
    BITE,
    unmodelled=[
        "Bite: what being Restrained stops - moving - which has no representation "
        "here. The condition is recorded, and the Strength Roll to break out of "
        "it is rolled, so content that keys on being held can see it",
    ],
)
def bite(adversary, target, fight: Fight):
    """Mark a Stress to bite one target for 3d4+10.

    SRD: "Mark a Stress to make an attack against a target within Melee range. On
    a success, deal 3d4+10 physical damage and the target is Restrained until
    they break free with a successful Strength Roll."

    3d4+10 averages 17.5 against the Bear's standard 1d8+3 at 7.5 - it is the
    Bear's whole threat.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table (`Adversary.will_spend_stress`). The
    Bear is the sharpest case of that rule anywhere in the catalogue: 7 HP
    against only two Stress means its first Bite has to wait until it is down to
    5 unmarked HP, and its second until 2. A Bear at full health is a 1d8+3
    attacker, and it becomes the thing on the page as the party wears it down.
    """
    if not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} lunges with a bite")
    result = adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=3, sides=4)],
        damage_modifier=10,
        damage_type=DamageType.PHYSICAL,
    )
    if result.damage_roll is None:
        return result

    # Recorded rather than merely declared: being held does nothing on its own
    # here, but content elsewhere asks whether a creature is held and by whom.
    fight.apply_condition(
        target,
        Condition(
            name=RESTRAINED,
            end=_breaks_free(("strength",), adversary.difficulty),
            source=adversary,
        ),
    )
    fight.note(f"{target.name} is caught in the Bear's jaws")
    return result


# --- Cave Ogre ---------------------------------------------------------------

BONE_BREAKER = qualified(ADVERSARY, "Bone Breaker")


@direct_damage(BONE_BREAKER)
def bone_breaker(adversary, fight=None) -> bool:
    """This adversary's attacks deal direct damage.

    SRD: "The Ogre's attacks deal direct damage." Direct damage can't be reduced
    by marking an Armor Slot; thresholds still decide how many HP it costs.

    Unconditional, which is why there is nothing to decide here. It is worth more
    than it looks against this party: the armor policy marks a free slot against
    every hit, so turning that off is close to a whole extra HP on every landed
    Ogre attack - and the Ogre is already swinging 1d10+2.
    """
    return True


RAMP_UP = qualified(ADVERSARY, "Ramp Up")


@spotlight_cost(RAMP_UP)
def ramp_up_costs_fear(adversary, fight=None) -> int:
    """Spotlighting this adversary costs a Fear, even the turn's free one.

    SRD: "You must spend a Fear to spotlight the Ogre."

    Half of Ramp Up; the other half is below. A passive, so there is nothing
    optional about it: the charge is made by the GM turn at the moment the Ogre
    is spotlighted, before it has chosen what to do, and an empty pool means the
    Ogre doesn't act at all.

    Charging at spotlight time is what makes the cost unavoidable. Whatever the
    Ogre then does - its standard attack, or Hail of Boulders for a Stress on top
    - the Fear has already been paid, so no action of its own can duck it.
    """
    return 1


@attack_area(RAMP_UP)
def ramp_up_sweeps(adversary, fight=None):
    """While spotlighted, the standard attack hits everyone in range.

    SRD: "While spotlighted, they can make their standard attack against all
    targets within range."

    **"Within range" is read off the stat block**, not named here. The Ogre's
    printed range is Very Close, and this feature would be equally correct on a
    Melee or a Far adversary - which is the whole reason `Adversary.range` is a
    field. Naming a band here would have baked one adversary's number into
    content shared by all of them.

    Worth knowing when reading the Ogre's numbers: the area rule holds Very Close
    to two, so against a party of four this reaches one PC and the sweep buys
    nothing that turn. That's the area rule doing its job - it exists so "all
    targets within range" can't mean "everyone, always" - but it does mean the
    Ogre's Fear cost bites hardest in exactly the small fights where the sweep is
    worth least. The band fractions are knobs, in SIMULATION-RULES.md.
    """
    return adversary.attack_band


HAIL_OF_BOULDERS = qualified(ADVERSARY, "Hail of Boulders")


@action(HAIL_OF_BOULDERS)
def hail_of_boulders(adversary, target, fight: Fight):
    """Mark a Stress to throw rocks at everyone within Far range for 1d10+2.

    SRD: "Mark a Stress to pick up heavy objects and throw them at all targets in
    front of the Ogre within Far range. Make an attack against these targets.
    Targets the Ogre succeeds against take 1d10+2 physical damage. If they succeed
    against more than one target, you gain a Fear."

    Far reaches the whole field, which is what makes this the Ogre's real area
    threat where its own Very Close sweep isn't.

    The Ogre's Ramp Up Fear has already been paid to spotlight it by the time
    this is offered, so this costs the GM a Fear *and* the Ogre a Stress - the
    charge happens at spotlight time precisely so no action can duck it.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table (`Adversary.will_spend_stress`). The
    Ogre has 8 HP against three Stress, so its first hail is available from the
    opening spotlight and the rest arrive as it is worn down.
    """
    caught = targets_in_area(Range.FAR, fight.conscious_party)
    if not caught or not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} hurls a hail of boulders")
    result, struck = adversary.area_attack(
        caught,
        fight=fight,
        damage_dice=[DiceGroup(count=1, sides=10)],
        damage_modifier=2,
        damage_type=DamageType.PHYSICAL,
    )
    if len(struck) > 1:
        fight.gain_fear(1)
        fight.note("The boulders scatter the party (GM gains a Fear)")
    return result


RAMPAGING_FURY = qualified(ADVERSARY, "Rampaging Fury")


@on_damaged(
    RAMPAGING_FURY,
    unmodelled=[
        "Rampaging Fury: 'all targets in their path' is a line drawn by moving "
        "the Ogre, and no positions exist to draw one through. The Close band "
        "stands in for it",
    ],
)
def rampaging_fury(adversary, amount: int, hp_marked: int, fight=None) -> None:
    """When this adversary marks 2 or more HP, rampage for 2d6+3 direct damage.

    SRD: "When the Ogre marks 2 or more HP, they can rampage. Move the Ogre to a
    point within Close range and deal 2d6+3 direct physical damage to all targets
    in their path."

    Keyed on HP *marked*, not on the damage rolled - the trigger names the cost,
    not the number, which is the opposite of Acid Bath and the reason `on_damaged`
    is handed both.

    No attack roll and no saving throw: the Ogre moves and everyone in the way is
    hit. Direct, so no Armor Slot softens it, which against a party that always
    marks one is worth about an HP a head on top of an average of 10.
    """
    if fight is None or hp_marked < 2:
        return

    trampled = targets_in_area(Range.CLOSE, fight.conscious_party)
    if not trampled:
        return

    fight.note(f"{adversary.name} rampages (Rampaging Fury)")
    damage = roll_damage(dice_groups=[DiceGroup(count=2, sides=6)], modifier=3)
    for pc in trampled:
        pc.take_damage(damage.total, fight, direct=True, damage_type=DamageType.PHYSICAL)
        fight.note(f"{pc.name} is caught in the path for {damage.total}")


# --- Construct ---------------------------------------------------------------

TRAMPLE = qualified(ADVERSARY, "Trample")


@action(
    TRAMPLE,
    unmodelled=[
        "Trample: 'in the Construct's path when they move' is a line, and no "
        "positions exist to draw one. The adversary's own printed range stands in",
    ],
)
def trample(adversary, target, fight: Fight):
    """Mark a Stress to attack everyone in the way for 1d8.

    SRD: "Mark a Stress to make an attack against all targets in the Construct's
    path when they move. Targets the Construct succeeds against take 1d8 physical
    damage."

    The SRD prints no band for it - the path is drawn by moving - so the
    adversary's **own printed range** stands in, read off the stat block rather
    than named here. The Construct's is Melee.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table (`Adversary.will_spend_stress`), and
    among the options that pass the choice is random. Melee reaches one or two
    under the area rule, so in practice this is "hit two people for 1d8 instead
    of one for 1d20" - and there is deliberately no target-count threshold on top.
    """
    caught = targets_in_area(adversary.attack_band, fight.conscious_party)
    if not caught or not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} tramples forward")
    result, _ = adversary.area_attack(
        caught,
        fight=fight,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=0,
        damage_type=DamageType.PHYSICAL,
    )
    return result


OVERLOAD = qualified(ADVERSARY, "Overload")


@damage_bonus(OVERLOAD)
def overload(adversary, target, fight: Fight) -> int:
    """Mark a Stress for +10 damage, and take the spotlight again.

    SRD: "Before rolling damage for the Construct's attack, you can mark a Stress
    to gain a +10 bonus to the damage roll. The Construct can then take the
    spotlight again."

    Asked from inside the damage roll, which is where "before rolling damage"
    puts it - and by then the attack has already landed, so the Stress is never
    spent on a miss.

    USAGE POLICY - ruled. A **Reaction**, so it fires whenever its trigger
    happens and the Stress can be paid, and the Stress-desperation rule that
    gates Action features deliberately does not apply - see
    `Adversary.will_spend_stress` for why the two are different decisions.

    Worth knowing what that means here, because Overload is the largest thing
    the ruling reaches. +10 on a 1d20 attack is enormous: it moves a typical hit
    from around 10 to around 20, which for a tier 1 PC is the difference between
    Major and Severe, and the free extra spotlight is on top. Four Stress means
    the Construct's first four landed attacks all carry it, from full health,
    and then it is done. The extra activations still cost Fear and still sit
    inside the GM turn's cap, which is the only thing holding it back.

    The extra activation is granted rather than taken: it still counts against
    the GM turn's cap and still costs the usual Fear, like every other way of
    acting twice.
    """
    if fight is None or not adversary.can_spend_stress(1):
        return 0

    adversary.spend_stress(1)
    fight.grant_activation(adversary)
    fight.note(f"{adversary.name} overloads (+10 damage, and it acts again)")
    return 10


DEATH_QUAKE = qualified(ADVERSARY, "Death Quake")


@on_damaged(DEATH_QUAKE)
def death_quake(adversary, amount: int, hp_marked: int, fight=None) -> None:
    """When this adversary marks their last HP, explode for 1d12+2 at Very Close.

    SRD: "When the Construct marks their last HP, the magic powering them ruptures
    in an explosion of force. Make an attack with advantage against all targets
    within Very Close range. Targets the Construct succeeds against take 1d12+2
    magic damage."

    Fires from `on_damaged`, which runs after the marking is settled - so
    `is_defeated` is already true here, and the Construct is exploding as it dies
    rather than needing to survive to do it.

    **Magic**, stated explicitly, and the clearest case in the catalogue for why
    a feature may override its stat block's type: the Construct's Fist Slam is
    physical, and letting the blast inherit that would have a party's magic
    resistances silently fail against the one attack the page calls magic.

    Worth knowing for encounter tuning: this makes killing the Construct cost
    something, so a party that focuses it down takes the blast at exactly the
    moment they thought the fight was won.
    """
    if fight is None or not adversary.is_defeated:
        return

    caught = targets_in_area(Range.VERY_CLOSE, fight.conscious_party)
    if not caught:
        return

    fight.note(f"{adversary.name} ruptures (Death Quake)")
    _, struck = adversary.area_attack(
        caught,
        AdvantageState.ADVANTAGE,
        fight,
        damage_dice=[DiceGroup(count=1, sides=12)],
        damage_modifier=2,
        damage_type=DamageType.MAGIC,
    )
    for pc in struck:
        fight.note(f"{pc.name} is caught in the blast")


# --- Deeproot Defender -------------------------------------------------------

GROUND_SLAM = qualified(ADVERSARY, "Ground Slam")


@action(
    GROUND_SLAM,
    unmodelled=[
        "Ground Slam: the knockback to Far range itself, which is where a "
        "combatant ends up and has nothing to change here. The Stress it forces "
        "is modelled",
    ],
)
def ground_slam(adversary, target, fight: Fight):
    """Slam the ground: everyone Very Close is knocked back and marks a Stress.

    SRD: "Slam the ground, knocking all targets within Very Close range back to
    Far range. Each target knocked back this way must mark a Stress."

    No attack roll, no Stress cost to the Defender, and no damage - what it does
    here is drain the party's Stress, which is worth more than it looks: a PC
    with every Stress marked is Vulnerable, and one with none spare can't pay for
    their own cards.

    The Stress is *forced*, so a PC who can't fit it marks an HP instead, per the
    SRD's rule on being made to mark Stress you don't have.

    USAGE POLICY - ruled. Nothing to pay, so nothing to gate: it joins the
    shuffled pool of options alongside the standard attack whenever it reaches
    anybody, and the choice among them is random - the standing default for a
    feature with no policy of its own.
    """
    caught = targets_in_area(Range.VERY_CLOSE, fight.conscious_party)
    if not caught:
        return None

    fight.note(f"{adversary.name} slams the ground")
    for pc in caught:
        pc.mark_stress(1)
        fight.note(f"{pc.name} is knocked back, and marks a Stress")
    return AttackResult(attack_roll=None, damage_roll=None)


GRAB_AND_DRAG = qualified(ADVERSARY, "Grab and Drag")
GRAB_AND_DRAG_FEAR = 1


@action(
    GRAB_AND_DRAG,
    unmodelled=[
        "Grab and Drag: what being Restrained stops - moving - which has no "
        "representation here. The condition is recorded so content that keys on "
        "being held can see it",
        "Grab and Drag: being pulled into Melee range, which is positioning",
    ],
)
def grab_and_drag(adversary, target, fight: Fight):
    """Attack for 1d6+2, spending a Fear on a hit, and Restrain the target.

    SRD: "Make an attack against a target within Close range. On a success, spend
    a Fear to pull them into Melee range, deal 1d6+2 physical damage, and Restrain
    them until the Defender takes Severe damage."

    The Fear is spent on a success, so the attack is rolled first and only a
    landed one is paid for - which is what the card's "on a success" says.

    USAGE POLICY - ruled. Used whenever the GM can afford the Fear, and among
    the options that pass the choice is random. Nothing holds it back for dealing
    less than the Defender's standard attack (1d6+2 at 5.5 against 1d8+3 at 7.5):
    a feature is only ever "strictly worse" with respect to damage, and damage is
    not the whole of why a GM reaches for something.

    It carries no already-has-the-condition check either, unlike Venomous
    Stinger. What it applies is Restrained, which has no effect of its own here,
    so declining to re-apply it would be holding back an attack over a condition
    that does nothing - the hold's own gap, declared above, rather than a
    judgement about the feature.
    """
    if fight.fear < GRAB_AND_DRAG_FEAR:
        return None

    result = adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=1, sides=6)],
        damage_modifier=2,
        damage_type=DamageType.PHYSICAL,
    )
    if result.damage_roll is None:
        return result

    fight.spend_fear(GRAB_AND_DRAG_FEAR)
    fight.apply_condition(target, Condition(name=RESTRAINED, source=adversary))
    fight.note(f"{adversary.name} drags {target.name} in (GM spends a Fear)")
    return result


@on_damaged(GRAB_AND_DRAG)
def grab_and_drag_releases(adversary, amount: int, hp_marked: int, fight=None) -> None:
    """Severe damage to this adversary frees whoever it was holding.

    SRD: "Restrain them until the Defender takes Severe damage" - the printed way
    out, and the only one, since this hold offers no roll to break free. Keyed on
    the damage rolled rather than the HP it cost, the same reading Acid Bath uses.
    """
    if fight is None or amount < adversary.severe_threshold:
        return

    _release_held(adversary, fight, RESTRAINED)
    fight.note(f"{adversary.name}'s vines go slack")

# --- Dire Wolf ---------------------------------------------------------------

PACK_TACTICS = qualified(ADVERSARY, "Pack Tactics")

# How many of the pack have to be on the target for the feature to fire: the
# attacker and one more, which is what "another Dire Wolf within Melee range of
# the target" says.
PACK_TACTICS_WOLVES = 2


@standard_damage(PACK_TACTICS)
def pack_tactics(adversary, target, roll=None, fight=None):
    """A successful standard attack deals 1d6+5 instead, and hands the GM a Fear.

    SRD: "If the Wolf makes a successful standard attack and another Dire Wolf is
    within Melee range of the target, deal 1d6+5 physical damage instead of their
    standard damage and you gain a Fear."

    Asked from inside the damage roll, so the success is already established -
    which is what lets the Fear be paid out here rather than needing a second
    registration on `on_hit`, where nothing distinguishes a standard attack from
    a Hobbling Strike.

    SIMULATION RULE - policy. "Another Dire Wolf within Melee range of the
    target" is positioning, and none is tracked, so the **area rule answers it**:
    of the wolves alive, `targets_reached(MELEE, ...)` says how many are on this
    target, and the feature needs `PACK_TACTICS_WOLVES` of them - the attacker
    and one more. The band's reach is rolled, so a pair of wolves converge about
    half the time and a pack of six always does. That is the point of routing it
    through the area rule rather than through "is another wolf alive?": the
    latter would fire on every attack while any packmate stood anywhere, which
    is far more than the page promises.

    Worth knowing for tuning: 1d6+5 averages 8.5 against the Wolf's printed
    1d6+2 at 5.5, and the Fear rides on top of every one that lands. Like the
    Bear's Momentum, a pack of these partly pays for its own extra activations -
    and unlike Momentum it needs no Stress and has no cap, so how often the band
    lets it through is the whole of what holds it back.
    """
    if fight is None:
        return None

    pack = [
        other
        for other in fight.living_adversaries
        if canonical(other.name) == canonical(adversary.name)
    ]
    # The attacker counts: the question is how many wolves are on this target,
    # and it is one of them.
    if len(pack) < PACK_TACTICS_WOLVES:
        return None
    if targets_reached(Range.MELEE, len(pack)) < PACK_TACTICS_WOLVES:
        return None

    fight.gain_fear(1)
    fight.note(f"{adversary.name} closes in as a pack (Pack Tactics: GM gains a Fear)")
    return [DiceGroup(count=1, sides=6)], 5


HOBBLING_STRIKE = qualified(ADVERSARY, "Hobbling Strike")


@action(HOBBLING_STRIKE)
def hobbling_strike(adversary, target, fight: Fight):
    """Mark a Stress: 3d4+10 direct, and Vulnerable until they clear an HP.

    SRD: "Mark a Stress to make an attack against a target within Melee range. On
    a success, deal 3d4+10 direct physical damage and make them Vulnerable until
    they clear at least 1 HP."

    Direct is stated on the attack rather than granted by a passive - the Wolf
    carries no Bone Breaker - which is what `Adversary.attack`'s `direct`
    argument is for. Against a party that marks a free Armor Slot against
    everything, that is worth close to a whole extra HP on top of an average
    of 17.5.

    The Vulnerable is the more dangerous half across a whole fight. It hands
    *every* roll against that PC Advantage, and unlike the SRD's usual "until
    they next act" it doesn't wear off on its own: somebody has to spend a turn
    healing before it lifts. See `until_they_clear_hp`.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table. The Wolf has 4 HP against three Stress,
    so the first is available from the opening spotlight.
    """
    if not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} snaps at {target.name}'s legs (Hobbling Strike)")
    result = adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=3, sides=4)],
        damage_modifier=10,
        direct=True,
        damage_type=DamageType.PHYSICAL,
    )
    if result.damage_roll is None:
        return result

    # Measured after the hit has landed, so the HP this attack just marked is
    # part of what has to be cleared.
    fight.apply_condition(
        target,
        Condition(name=VULNERABLE, end=until_they_clear_hp(target.hp_marked)),
    )
    fight.note(f"{target.name} is hobbled, and is Vulnerable until they clear an HP")
    return result


# --- Giant Mosquitoes --------------------------------------------------------

HORDE = qualified(ADVERSARY, "Horde")


@standard_damage(HORDE)
def horde(adversary, target, roll=None, fight=None):
    """Once half this adversary's HP is marked, the standard attack deals X.

    SRD: "When the Mosquitoes have marked half or more of their HP, their
    standard attack deals 1d4+1 physical damage instead."

    Parameterised, so `Horde (1d4+1)` is one feature reading its own damage off
    the stat block - and the parameter is a whole damage expression rather than a
    number, which is why `_damage_spec` exists. The SRD prints the swarm's
    thinning-out this way on every Horde, with different dice each time.

    Note which direction this runs: it makes the adversary *weaker* as it is
    worn down, where most of the SRD's damage swaps make one stronger. That is
    the Horde's whole shape - a mass of small things that stops being a mass.

    A stat block writing `Horde` with no parameter gets nothing rather than a
    guess, exactly as Relentless and Flying do.
    """
    written = feature_parameter(adversary, HORDE)
    if written is None:
        return None
    # "Half or more of their HP", so a 6 HP swarm switches at 3 marked.
    if adversary.hp_marked * 2 < adversary.hp_max:
        return None
    return _damage_spec(written)


BLOODSUCKER = qualified(ADVERSARY, "Bloodsucker")


@on_hit(BLOODSUCKER)
def bloodsucker(adversary, target, result, fight: Fight) -> None:
    """When an attack makes the target mark HP, mark a Stress to force one more.

    SRD: "When the Mosquitoes' attack causes a target to mark HP, you can mark a
    Stress to force the target to mark an additional HP."

    Keyed on HP actually marked rather than on damage dealt, which is what the
    trigger says: a hit an Armor Slot swallowed entirely caused nobody to mark
    anything, so there is nothing to add to. `AttackResult.hp_marked` carries
    that figure back from wherever the damage was resolved.

    The extra HP is forced rather than rolled, so it goes through the death check
    directly and can be the mark that drops a PC.

    USAGE POLICY - ruled. A Reaction, so it fires on every trigger it can pay
    for; the Stress-desperation rule that gates Actions deliberately doesn't
    apply. Three Stress means the first three hits that hurt somebody each cost
    an extra HP.
    """
    if result is None or result.hp_marked <= 0:
        return
    if not adversary.can_spend_stress(1):
        return

    adversary.spend_stress(1)
    target.mark_hp_and_check_death(1)
    fight.note(f"{adversary.name} drains {target.name} (Bloodsucker: an extra HP)")


# --- Giant Rat ---------------------------------------------------------------

MINION = qualified(ADVERSARY, "Minion")


@on_damaged(
    MINION,
    unmodelled=[
        "Minion (X): 'a Minion within range the attack would succeed against' - "
        "no range is tracked, so every other living Minion of the same stat block "
        "is eligible. The success half needs no check: they share a Difficulty, "
        "so an attack that beat one would beat all of them",
        "Minion (X): the SRD counts damage a *PC* deals, and nothing records who "
        "dealt it - so a splash from another adversary would spread the same way",
    ],
)
def minion(adversary, amount: int, hp_marked: int, fight=None) -> None:
    """For every X damage dealt to this Minion, another of them goes down too.

    SRD: "The Rat is defeated when they take any damage. For every 3 damage a PC
    deals to the Rat, defeat an additional Minion within range the attack would
    succeed against."

    Only the overkill needs code. **"Defeated when they take any damage" already
    falls out of the stat block**: a Minion prints no thresholds, the catalogue
    stores that as `NO_THRESHOLD`, so every hit lands in the lowest band and
    marks 1 HP off a 1 HP track. Nothing here has to say it, and saying it again
    would be a second expression of the same rule.

    The additional Minions are taken down with `mark_hp` rather than
    `take_damage`, deliberately: `take_damage` fires this hook again, so one big
    hit would cascade through the swarm and each defeated Minion would spread the
    full damage onward. The SRD divides the damage once.

    Parameterised, so `Minion (3)` and a `Minion (5)` elsewhere are one feature.
    """
    if fight is None or amount <= 0:
        return

    written = feature_parameter(adversary, MINION)
    if written is None:
        return
    try:
        per = int(written)
    except ValueError:
        return
    if per <= 0:
        return

    extra = amount // per
    if extra <= 0:
        return

    swarm = [
        other
        for other in fight.living_adversaries
        if other is not adversary and canonical(other.name) == canonical(adversary.name)
    ]
    for other in swarm[:extra]:
        other.mark_hp(other.hp_max)
        fight.note(f"{other.name} is cut down in the same blow (Minion {per})")


GROUP_ATTACK = qualified(ADVERSARY, "Group Attack")
GROUP_ATTACK_FEAR = 1

# SIMULATION RULE - policy. How many of the swarm have to be in range before the
# GM spends the Fear. Below this the feature buys nothing a plain standard attack
# from one Minion wouldn't: it is one shared roll for the combined damage of
# everyone it sweeps, so at one Minion it *is* that Minion's standard attack, and
# at two it doubles it. Written as a constant, and generalised to every Minion
# rather than to the Giant Rat, because the shape recurs across the SRD's Minions.
GROUP_ATTACK_WORTH_IT = 2


@action(
    GROUP_ATTACK,
    unmodelled=[
        "Group Attack: the Minions moving into Melee range of the target, which "
        "is positioning and has no representation here. Which of them are within "
        "Close range of the target is stood in for by the area rule",
    ],
)
def group_attack(adversary, target, fight: Fight):
    """Spend a Fear: the whole swarm makes one shared attack for combined damage.

    SRD: "Spend a Fear to choose a target and spotlight all Giant Rats within
    Close range of them. Those Minions move into Melee range of the target and
    make one shared attack roll. On a success, they deal 1 physical damage each.
    Combine this damage."

    Written for Minions in general rather than for the Giant Rat. Nothing here
    names a stat block: the swarm is "every living adversary sharing this one's
    name", which is what "all Giant Rats" means when the Giant Rat is the one
    holding the feature, and the damage is built from the holder's own printed
    attack so a Minion with dice combines correctly too.

    **One activation, however many it sweeps** - the feature is a single shared
    roll, so it costs a single spotlight. But every Minion in the swarm *has*
    been spotlighted, so each one's activation is consumed and none of them comes
    round again this GM turn. That is the whole reason `consume_activation`
    exists; see `combat/state.py`.

    USAGE POLICY - ruled. Used when it reaches `GROUP_ATTACK_WORTH_IT` or more of
    the swarm, since below that it is one Minion's ordinary attack for a Fear.
    """
    if fight.fear < GROUP_ATTACK_FEAR:
        return None

    kin = [
        other
        for other in fight.living_adversaries
        if canonical(other.name) == canonical(adversary.name)
    ]
    # How many of the swarm are within Close range of the target. The area rule
    # is the simulator's only answer to a range band, and it applies here even
    # though what is being counted is the GM's own side rather than a field of
    # targets - the question ("how much of this group does Close cover?") is the
    # same one.
    swarm = kin[: targets_reached(Range.CLOSE, len(kin))]
    if len(swarm) < GROUP_ATTACK_WORTH_IT:
        return None

    fight.spend_fear(GROUP_ATTACK_FEAR)
    fight.note(
        f"{len(swarm)} {adversary.name}s swarm {target.name} "
        f"(Group Attack: GM spends a Fear)"
    )

    # Each Minion deals its own printed damage and the total is combined, so the
    # shared roll is the stat block's attack multiplied by the swarm. The Giant
    # Rat has no dice at all - a flat 1 - which is why this has to scale both the
    # dice and the modifier rather than assuming either.
    combined = [
        DiceGroup(count=group.count * len(swarm), sides=group.sides)
        for group in adversary.damage_dice
    ]
    result = adversary.attack(
        target,
        fight=fight,
        damage_dice=combined,
        damage_modifier=adversary.damage_modifier * len(swarm),
    )

    # The holder's own activation is the loop's to charge; the rest of the swarm
    # has been spotlighted by this feature and is done for the turn.
    for minion in swarm:
        if minion is not adversary:
            fight.consume_activation(minion)
    return result


# --- Giant Scorpion ----------------------------------------------------------

DOUBLE_STRIKE = qualified(ADVERSARY, "Double Strike")

# The SRD names two targets outright, so this is the feature's own number rather
# than a knob - but how many are actually in Melee is still the area rule's
# answer, and at that band it reaches one or two.
DOUBLE_STRIKE_TARGETS = 2


@action(DOUBLE_STRIKE)
def double_strike(adversary, target, fight: Fight):
    """Mark a Stress to make the standard attack against two Melee targets.

    SRD: "Mark a Stress to make a standard attack against two targets within
    Melee range."

    The *printed* attack, not a different one, so no dice are passed and the stat
    block's own 1d12+2 is rolled - which also means a standard-attack swap would
    reach it, if the Scorpion had one.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table, and there is deliberately **no** check
    that two targets are available first. So against a lone PC this spends a
    Stress to do exactly what the standard attack would have done, which is the
    ruled behaviour rather than an oversight.
    """
    caught = targets_in_area(Range.MELEE, fight.conscious_party)[:DOUBLE_STRIKE_TARGETS]
    if not caught or not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} strikes with both pincers (Double Strike)")
    result, _ = adversary.area_attack(caught, fight=fight)
    return result


VENOMOUS_STINGER = qualified(ADVERSARY, "Venomous Stinger")
VENOMOUS_STINGER_FEAR = 1

# The Scorpion's poison, as printed: shaken off on a Knowledge Roll at 16, and
# costing a Stress on a d6 of 4 or lower before each action roll.
SCORPION_POISON_DIFFICULTY = 16
SCORPION_POISON_DIE = 6
SCORPION_POISON_BITES_AT = 4


def _scorpion_poison_ends(holder, fight, moment: str) -> bool:
    """A Knowledge Reaction Roll at 16 shakes the Scorpion's poison off.

    The SRD's other way out - "until their next rest" - never arrives inside one
    fight, so the roll is the only route here. Offered at each moment the loop
    announces rather than once a round, which is the granularity the condition
    machinery has everywhere.
    """
    return _reaction_roll(
        holder, "knowledge", SCORPION_POISON_DIFFICULTY, fight
    ).is_success


def _scorpion_poison_bites(holder, fight, moment: str) -> None:
    """Before an action roll, a d6 of 4 or lower costs the poisoned PC a Stress.

    The first real use of `Condition.effect`, and the reason poison is modelled
    as a *family* rather than one condition: the name is shared, but this effect
    and this ender belong to the Scorpion specifically.

    A plain d6 drawn straight from `random`, the way `content/aoe.py` draws its
    spread roll - this is not an attack, a damage roll or a duality roll, so
    none of `dice/` has a shape for it.
    """
    if moment != BEFORE_AN_ACTION_ROLL:
        return
    if random.randint(1, SCORPION_POISON_DIE) > SCORPION_POISON_BITES_AT:
        return
    holder.mark_stress(1)
    fight.note(f"{holder.name} is wracked by poison, and marks a Stress")


@action(VENOMOUS_STINGER)
def venomous_stinger(adversary, target, fight: Fight):
    """Attack for 1d4+4 and Poison the target, spending a Fear on a hit.

    SRD: "Make an attack against a target within Very Close range. On a success,
    spend a Fear to deal 1d4+4 physical damage and Poison them until their next
    rest or they succeed on a Knowledge Roll (16). While Poisoned, the target
    must roll a d6 before they make an action roll. On a result of 4 or lower,
    they must mark a Stress."

    The Fear is spent on a success, so the attack is rolled first and only a
    landed one is paid for.

    USAGE POLICY - ruled. The sting's point is the Poison, so it is held back
    against a target who is already Poisoned - there it would buy nothing at all,
    and whether somebody is poisoned is visible to everyone at the table.
    Otherwise it joins the shuffled pool of options like anything else.

    What it is *not* gated on is a comparison of expected damage. 1d4+4 averages
    6.5 against the Scorpion's printed 1d12+2 at 8.5, and that used to be the
    test for whether this counted as a condition attack at all; the ruling is
    that no combatant computes such a thing, so no policy may turn on it.
    """
    if fight.fear < VENOMOUS_STINGER_FEAR:
        return None
    if fight.has_condition(target, POISONED):
        return None

    result = adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=1, sides=4)],
        damage_modifier=4,
        damage_type=DamageType.PHYSICAL,
    )
    if result.damage_roll is None:
        return result

    fight.spend_fear(VENOMOUS_STINGER_FEAR)
    fight.apply_condition(
        target,
        Condition(
            name=POISONED,
            end=_scorpion_poison_ends,
            effect=_scorpion_poison_bites,
        ),
    )
    fight.note(f"{adversary.name} poisons {target.name} (GM spends a Fear)")
    return result


# --- Glass Snake -------------------------------------------------------------

ARMOR_SHREDDING_SHARDS = qualified(ADVERSARY, "Armor-Shredding Shards")


@on_attacked(
    ARMOR_SHREDDING_SHARDS,
    unmodelled=[
        "Armor-Shredding Shards: only a weapon attack reaches this. Content that "
        "rolls an attack of its own - a Grimoire spell, the Beastbound companion "
        "- has no weapon and so no range to read, and never triggers it",
    ],
)
def armor_shredding_shards(
    adversary, attacker, weapon, damage=0, hp_marked=0, fight=None
) -> None:
    """A successful Melee attack on this adversary costs the attacker an Armor Slot.

    SRD: "After a successful attack against the Snake within Melee range, the
    attacker must mark an Armor Slot. If they can't mark an Armor Slot, they must
    mark an HP."

    SIMULATION RULE - policy. No positions are tracked, so "within Melee range"
    is read off the **attacker's weapon**: everyone is assumed to have attacked
    from the greatest range their weapon allows, so a Melee-only weapon triggers
    this and anything reaching further does not. That makes the feature a real
    tax on the front line and free for archers, which is the shape it has at a
    table - and it means a party's answer to the Snake is a weapon choice.

    Note this fires on a successful attack rather than on a wound: a hit the
    Snake shrugged off entirely still leaves glass in whoever threw it.
    """
    if fight is None or canonical(weapon.range) != canonical(Range.MELEE.value):
        return

    if attacker.armor_unmarked > 0:
        attacker.mark_armor_slot(1)
        fight.note(
            f"{attacker.name} tears their armor on the shards "
            f"(Armor-Shredding Shards: an Armor Slot)"
        )
        return

    attacker.mark_hp_and_check_death(1)
    fight.note(f"{attacker.name} has no armor left to shred, and marks an HP")


SPITTER = qualified(ADVERSARY, "Spitter")
SPITTER_FEAR = 1
SPITTER_DIE_TOKEN = "Spitter Die"

# The die itself, as printed: a d6 rolled at each of the Snake's spotlights,
# spitting on a 5 or higher for 1d4 against an Agility Reaction Roll.
SPITTER_DIE = 6
SPITTER_SPITS_AT = 5


@action(SPITTER)
def spitter(adversary, target, fight: Fight):
    """Spend a Fear to introduce the Spitter Die, and act again this turn.

    SRD: "Spend a Fear to introduce a d6 Spitter Die. When the Snake is in the
    spotlight, roll this die. On a result of 5 or higher, all targets in front of
    the Snake within Far range must succeed on an Agility Reaction Roll or take
    1d4 physical damage. The Snake can take the spotlight a second time this GM
    turn."

    Two halves, and this is the one that costs something. The die's own rolling
    is `spitter_die_rolls` below, on the spotlight hook - so it keeps going for
    the rest of the fight however the Snake spends its spotlights, which is what
    makes buying it early worth so much more than buying it late.

    **The extra spotlight is granted once, on the turn the die is introduced** -
    not every turn the die is active, and not for rolling a 5. Spending the Fear
    buys the die *and* one extra activation that turn; afterwards the die keeps
    rolling and buys nothing. That makes it the Overload shape (`grant_activation`)
    rather than the Relentless one, and it stays inside the GM turn's cap with
    the extra activation still costing the usual Fear.

    USAGE POLICY - ruled. Bought at the first spotlight the Fear allows, since it
    is worth strictly more the earlier it lands. Once introduced there is nothing
    left to buy, so this declines for the rest of the fight.
    """
    if fight.token_count(adversary, SPITTER_DIE_TOKEN):
        return None
    if fight.fear < SPITTER_FEAR:
        return None

    fight.spend_fear(SPITTER_FEAR)
    fight.set_token(adversary, SPITTER_DIE_TOKEN, 1)
    fight.grant_activation(adversary)
    fight.note(
        f"{adversary.name} rears back, glass shards rattling "
        f"(Spitter: GM spends a Fear, and it acts again)"
    )
    # Fired, so the spotlight is spent - but nothing was rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


@on_spotlight(
    SPITTER,
    unmodelled=[
        "Spitter: 'all targets in front of the Snake' is a facing, and none is "
        "tracked. The Far band stands in for it",
    ],
)
def spitter_die_rolls(adversary, fight=None) -> None:
    """Roll the Spitter Die at each of this adversary's spotlights.

    The passive half of Spitter, registered against the same name so the feature
    stays one piece of content in one place. It does nothing until the action
    above has bought the die, and everything afterwards.

    Rolls at *every* spotlight the Snake takes, including the extra one the
    purchase granted - so the turn it is bought, the die rolls once, on that
    granted second activation.
    """
    if fight is None or not fight.token_count(adversary, SPITTER_DIE_TOKEN):
        return
    if random.randint(1, SPITTER_DIE) < SPITTER_SPITS_AT:
        return

    caught = targets_in_area(Range.FAR, fight.conscious_party)
    if not caught:
        return

    fight.note(f"{adversary.name} spits a spray of glass (Spitter Die)")
    for pc in caught:
        roll = _reaction_roll(pc, "agility", adversary.difficulty, fight)
        if roll.is_success:
            fight.note(f"{pc.name} ducks the spray ({roll})")
            continue
        damage = roll_damage(dice_groups=[DiceGroup(count=1, sides=4)], modifier=0)
        pc.take_damage(damage.total, fight, damage_type=DamageType.PHYSICAL)
        fight.note(f"{pc.name} is cut by the spray for {damage.total}")


SPINNING_SERPENT = qualified(ADVERSARY, "Spinning Serpent")


@action(SPINNING_SERPENT)
def spinning_serpent(adversary, target, fight: Fight):
    """Mark a Stress to attack everyone within Very Close for 1d6+1.

    SRD: "Mark a Stress to make an attack against all targets within Very Close
    range. Targets the Snake succeeds against take 1d6+1 physical damage."

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table, with deliberately no threshold on how
    many PCs it reaches. Worth knowing what that costs against the area rule:
    Very Close is held to two, and against a party of four it reaches one - so
    this is often 1d6+1 to a single PC where the standard attack would have been
    1d8+2 to the same one.
    """
    caught = targets_in_area(Range.VERY_CLOSE, fight.conscious_party)
    if not caught or not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} whips into a spin (Spinning Serpent)")
    result, _ = adversary.area_attack(
        caught,
        fight=fight,
        damage_dice=[DiceGroup(count=1, sides=6)],
        damage_modifier=1,
        damage_type=DamageType.PHYSICAL,
    )
    return result


# --- Harrier -----------------------------------------------------------------

FALL_BACK = qualified(ADVERSARY, "Fall Back")


@before_attacked(
    FALL_BACK,
    unmodelled=[
        "Fall Back: the Harrier moving anywhere within Close range, which is "
        "where a combatant ends up and has nothing to change here. The "
        "counterattack it comes with is modelled",
        "Fall Back: a PC the counterattack knocks unconscious still completes "
        "the attack they had already started - a spotlight under way can't be "
        "unwound",
    ],
)
def fall_back(adversary, attacker, weapon, fight=None) -> None:
    """Mark a Stress to counterattack whoever closes to Melee, for 1d10+2.

    SRD: "When a creature moves into Melee range to make an attack, you can mark
    a Stress before the attack roll to move anywhere within Close range and make
    an attack against that creature. On a success, deal 1d10+2 physical damage."

    SIMULATION RULE - policy. Two readings had to be settled and both are the
    user's ruling. **The incoming attack still happens**: the SRD never says it
    is cancelled, and a PC can move within Close range as part of their own
    action, so one whose target backed off would simply follow. And "moves into
    Melee range to make an attack" is read off the **attacker's weapon**, the
    same handle on range Armor-Shredding Shards already uses - a Melee weapon
    triggers this and anything reaching further does not.

    USAGE POLICY - ruled. A Reaction, so it fires on every trigger it can pay
    for and the Stress-desperation rule that gates Actions deliberately does not
    apply. Three Stress against 3 HP means the Harrier's first three melee
    attackers each eat a 1d10+2 counter, from full health - which is a lot more
    damage than its printed 1d6+2 javelin, and the reason this stat block is
    dangerous to a front line rather than to an archer.
    """
    if fight is None or canonical(weapon.range) != canonical(Range.MELEE.value):
        return
    if not adversary.can_spend_stress(1):
        return

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} gives ground and throws (Fall Back)")
    result = adversary.attack(
        attacker,
        fight=fight,
        damage_dice=[DiceGroup(count=1, sides=10)],
        damage_modifier=2,
        damage_type=DamageType.PHYSICAL,
    )
    if result.damage_roll is None:
        fight.note(f"{adversary.name} misses {attacker.name} ({result.attack_roll})")
        return

    fight.note(f"{adversary.name} catches {attacker.name} for {result.damage_roll.total}")
    # A Reaction's attack is made outside the spotlight loop, so the loop isn't
    # there to hand out the riders a landed attack triggers. Asked here instead,
    # generically - an adversary carrying Momentum should gain its Fear off this
    # attack exactly as off any other.
    apply_on_hit(adversary, attacker, result, fight)


# --- Archer Guard ------------------------------------------------------------

HOBBLING_SHOT = qualified(ADVERSARY, "Hobbling Shot")

# The SRD prints this effect without naming it as a condition, so the name is
# ours; what matters is the trait it hobbles and how it ends.
HOBBLED = "Hobbled"


@action(
    HOBBLING_SHOT,
    unmodelled=[
        "Hobbling Shot: the disadvantage reaches a PC's weapon attacks and their "
        "Reaction Rolls, which is where a trait is named. Content that rolls an "
        "attack of its own - a Grimoire spell - doesn't consult it, so a "
        "spellcaster whose trait is Agility escapes the hobble",
    ],
)
def hobbling_shot(adversary, target, fight: Fight):
    """Attack at Far for 1d12+3, and hobble whoever it wounds.

    SRD: "Make an attack against a target within Far range. On a success, mark a
    Stress to deal 1d12+3 physical damage. If the target marks HP from this
    attack, they have disadvantage on Agility Rolls until they clear at least
    1 HP."

    The Stress is paid on a success, so the attack is rolled first and only a
    landed one is paid for - the shape Grab and Drag already uses for its Fear.

    The hobble is keyed on HP actually marked rather than on damage dealt, which
    is what the trigger says: a hit an Armor Slot swallowed whole wounded nobody.
    Like the Dire Wolf's Vulnerable it doesn't wear off on its own - somebody has
    to heal before it lifts - and it is measured against the mark this attack
    just made. See `until_they_clear_hp`.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table. Worth knowing that the rule never
    actually holds it back here: 3 HP against two Stress puts the Archer inside
    the line from full health, so this is simply what an Archer Guard does.
    1d12+3 averages 9.5 against its printed 1d8+3 at 7.5.
    """
    if not adversary.will_spend_stress(1):
        return None

    result = adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=1, sides=12)],
        damage_modifier=3,
        damage_type=DamageType.PHYSICAL,
    )
    if result.damage_roll is None:
        return result

    adversary.spend_stress(1)
    if result.hp_marked <= 0:
        return result

    # Measured after the hit has landed, so the HP this attack just marked is
    # part of what has to be cleared.
    fight.apply_condition(
        target,
        Condition(
            name=HOBBLED,
            end=until_they_clear_hp(target.hp_marked),
            disadvantage_on=("agility",),
        ),
    )
    fight.note(
        f"{target.name} is hobbled, and has disadvantage on Agility Rolls "
        f"until they clear an HP"
    )
    return result


# --- Bladed Guard ------------------------------------------------------------

DETAIN = qualified(ADVERSARY, "Detain")


@action(
    DETAIN,
    unmodelled=[
        "Detain: what being Restrained stops - moving - which has no "
        "representation here. The condition is recorded and the roll to break "
        "free is rolled, so content that keys on being held can see it",
        "Detain: breaking free with a successful *attack*, one of the three "
        "routes the SRD offers. The two rolls are modelled and are the ones a "
        "PC would reach for",
    ],
)
def detain(adversary, target, fight: Fight):
    """Attack for the printed damage, then mark a Stress to Restrain the target.

    SRD: "Make an attack against a target within Very Close range. On a success,
    mark a Stress to Restrain the target until they break free with a successful
    attack, Finesse Roll, or Strength Roll."

    SIMULATION RULE - interpretation, ruled. The feature prints no damage, and
    the ruling is that an attack feature deals **whatever damage it states, and
    otherwise the adversary's standard damage** - so this is an ordinary
    Longsword swing with a Stress spent on top. The corroboration is on the page
    two entries later: the Jagged Knife Kneebreaker's Hold Them Down has to say
    "the target takes no damage", which is only worth printing if damage is what
    happens by default.

    Passing no dice is also what keeps that true mechanically: `dice is None` is
    the discriminator for "the printed attack", so a standard-damage swap would
    reach this exactly as it reaches an ordinary swing.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table, and among the options that pass the
    choice is random. Be clear about what that means here: being Restrained has
    no effect of its own in this simulation, so a Detain that lands is the
    Guard's own attack for the price of a Stress - unless something else on the
    field keys on the hold, which is exactly what the Kneebreaker's `I've Got 'Em`
    does. The condition is recorded for that reason; what stays unrepresented is
    the movement it stops, declared above.
    """
    if not adversary.will_spend_stress(1):
        return None

    result = adversary.attack(target, fight=fight)
    if result.damage_roll is None:
        return result

    adversary.spend_stress(1)
    fight.apply_condition(
        target,
        Condition(
            name=RESTRAINED,
            # "A successful attack, Finesse Roll, or Strength Roll" - three ways
            # out, and the PC rolls whichever of the two traits they are better
            # at. The attack route isn't modelled and is declared above.
            end=_breaks_free(("finesse", "strength"), adversary.difficulty),
            source=adversary,
        ),
    )
    fight.note(f"{adversary.name} detains {target.name}")
    return result


# --- Head Guard --------------------------------------------------------------

RALLY_GUARDS = qualified(ADVERSARY, "Rally Guards")
RALLY_GUARDS_FEAR = 2

# "Up to 2d4 allies", as printed. Rolled with `random` directly, the way the
# Spitter Die and the Scorpion's poison die are: this is neither an attack, a
# damage roll nor a duality roll, so nothing in dice/ has a shape for it.
RALLY_GUARDS_DICE = 2
RALLY_GUARDS_DIE = 4


@action(RALLY_GUARDS)
def rally_guards(adversary, target, fight: Fight):
    """Spend 2 Fear to spotlight this adversary and up to 2d4 allies within Far.

    SRD: "Spend 2 Fear to spotlight the Head Guard and up to 2d4 allies within
    Far range."

    Every spotlight it hands out is a `grant_activation`, which means the same
    thing here as it does for the Construct's Overload: the extra activations sit
    inside the GM turn's cap and each still costs the loop its usual Fear. So the
    2 Fear buys the *permission* for a whole line of guards to act again, not the
    activations themselves - and on a big field the cap, rather than the pool, is
    usually what limits it.

    Who is within Far range goes through the area rule, the way Group Attack
    counts its swarm: the question ("how much of this group does the band
    cover?") is the same one whichever side of the table is being counted. Which
    allies get picked is random among those in range, because the order an
    encounter listed its adversaries in carries no meaning.

    USAGE POLICY - ruled. Used whenever the GM can afford the 2 Fear, and among
    the options that pass the choice is random - the standing default for a
    feature with no policy of its own. Deliberately **no** target-count
    threshold, unlike a Minion's Group Attack: the proposal to hold it back below
    two allies was put and declined, so a Head Guard alone will spend 2 Fear on
    an extra activation the GM could have had for 1. That is the ruled behaviour
    rather than an oversight, and `GROUP_ATTACK_WORTH_IT` is where the opposite
    shape lives if it is ever wanted here.
    """
    if fight.fear < RALLY_GUARDS_FEAR:
        return None

    allies = [other for other in fight.living_adversaries if other is not adversary]
    within = targets_reached(Range.FAR, len(allies)) if allies else 0
    wanted = sum(
        random.randint(1, RALLY_GUARDS_DIE) for _ in range(RALLY_GUARDS_DICE)
    )
    rallied = random.sample(allies, min(within, wanted)) if within else []

    fight.spend_fear(RALLY_GUARDS_FEAR)
    fight.grant_activation(adversary)
    for ally in rallied:
        fight.grant_activation(ally)

    fight.note(
        f"{adversary.name} bellows an order, rallying {len(rallied)} "
        f"{'ally' if len(rallied) == 1 else 'allies'} (Rally Guards: GM spends "
        f"{RALLY_GUARDS_FEAR} Fear)"
    )
    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


ON_MY_SIGNAL = qualified(ADVERSARY, "On My Signal")

# The countdown, and the fact that it has been started. Two tokens rather than
# one, because a countdown standing at zero and a countdown that was never armed
# are both a count of nothing, and only one of them should still be ticking.
ON_MY_SIGNAL_COUNTDOWN = "On My Signal countdown"
ON_MY_SIGNAL_ARMED = "On My Signal armed"

# The one place in the catalogue where a feature names another stat block. The
# SRD writes it that way - "all Archer Guards within Far range" - so the name is
# the book's, matched canonically like every other.
ARCHER_GUARD = "Archer Guard"


@on_spotlight(ON_MY_SIGNAL)
def on_my_signal_arms(adversary, fight=None) -> None:
    """Start the countdown the first time this adversary is spotlighted.

    SRD: "Countdown (5). When the Head Guard is in the spotlight for the first
    time, activate the countdown."

    Half of the feature; the ticking is below. Parameterised as `On My Signal (X)`
    for the reason `Relentless (X)` and `Flying (X)` are - the number is an
    argument, not part of what the feature is - and a stat block writing it
    without one arms nothing rather than guessing at a starting value.
    """
    if fight is None or fight.token_count(adversary, ON_MY_SIGNAL_ARMED):
        return

    written = feature_parameter(adversary, ON_MY_SIGNAL)
    if written is None:
        return
    try:
        start = int(written)
    except ValueError:
        return
    if start <= 0:
        return

    fight.set_token(adversary, ON_MY_SIGNAL_ARMED, 1)
    fight.set_token(adversary, ON_MY_SIGNAL_COUNTDOWN, start)
    fight.note(f"{adversary.name} raises a whistle (On My Signal: countdown {start})")


@on_party_attack_roll(
    ON_MY_SIGNAL,
    unmodelled=[
        "On My Signal: 'the nearest target within their range' is positioning. "
        "The standing targeting rule stands in for it, and every Archer Guard "
        "fires at the same PC - which is what makes 'combine their damage' mean "
        "anything",
    ],
)
def on_my_signal_ticks(adversary, roller, roll, fight=None) -> None:
    """Tick the countdown on each PC attack roll; on zero, the archers fire.

    SRD: "It ticks down when a PC makes an attack roll. When it triggers, all
    Archer Guards within Far range make a standard attack with advantage against
    the nearest target within their range. If any attacks succeed on the same
    target, combine their damage."

    It triggers **once**. The SRD only re-arms a countdown that says it loops,
    and this one doesn't, so the tokens are left at zero afterwards and the
    Head Guard's whistle is spent.

    Each archer rolls its own attack - that is what "all Archer Guards make a
    standard attack" says - and the successes are then combined into a single
    damage roll rather than several. The distinction matters a great deal in
    Daggerheart: three separate hits of 7 mark 3 HP off a tier 1 PC, while one
    combined 21 is Severe and marks 3 off a much sturdier one. Combining is the
    printed rule and it is the whole reason this feature is frightening.

    The forced-reroll dispatch is offered for every one of those attacks, as it
    would be for any other, so the party's Not This Time still reaches them.
    """
    if fight is None or not fight.token_count(adversary, ON_MY_SIGNAL_COUNTDOWN):
        return

    fight.spend_tokens(adversary, ON_MY_SIGNAL_COUNTDOWN, 1)
    left = fight.token_count(adversary, ON_MY_SIGNAL_COUNTDOWN)
    if left > 0:
        fight.note(f"{adversary.name}'s signal draws closer (countdown {left})")
        return

    archers = [
        other
        for other in fight.living_adversaries
        if canonical(other.name) == canonical(ARCHER_GUARD)
    ]
    firing = archers[: targets_reached(Range.FAR, len(archers))] if archers else []
    if not firing:
        fight.note(f"{adversary.name} gives the signal, and nobody is there to take it")
        return

    # The standing targeting rule, asked on the Head Guard's behalf - it is the
    # one calling the shot, and every archer fires at the same PC. Imported here
    # rather than at module level: combat/ reaches content/, which discovers this
    # package, so the two only meet at call time.
    from combat.policy import choose_adversary_target

    target = choose_adversary_target(adversary, fight)
    if target is None:
        return

    fight.note(
        f"{adversary.name} gives the signal, and {len(firing)} "
        f"{ARCHER_GUARD}{'s' if len(firing) > 1 else ''} fire on {target.name}"
    )

    hits = 0
    critical = False
    for archer in firing:

        def swing(shooter=archer):
            return roll_d20(
                modifier=shooter.attack_modifier,
                evasion=target.evasion,
                advantage_state=AdvantageState.ADVANTAGE,
            )

        shot = force_adversary_reroll(archer, target, swing(), swing, fight)
        if shot.is_success:
            hits += 1
            critical = critical or shot.is_critical

    if not hits:
        fight.note(f"{target.name} is missed by every arrow")
        return

    # Combined, so the volley is measured against the target's thresholds once.
    # Every Archer Guard shares a stat block, so multiplying one archer's printed
    # attack by the number that hit is exactly the sum of their damage - the same
    # arithmetic Group Attack uses to combine a swarm.
    shooter = firing[0]
    damage = roll_damage(
        dice_groups=[
            DiceGroup(count=group.count * hits, sides=group.sides)
            for group in shooter.damage_dice
        ],
        modifier=shooter.damage_modifier * hits,
        is_critical=critical,
    )
    # The archers' own standard attack, so it deals the archers' printed type -
    # read off the shooter rather than off the Head Guard whose whistle called
    # it, and asked through `type_of_damage` so the fallback is spelled once.
    target.take_damage(
        damage.total,
        fight,
        direct=deals_direct_damage(shooter, fight),
        damage_type=shooter.type_of_damage(),
    )
    fight.note(
        f"{hits} of the volley lands on {target.name} for {damage.total} combined"
    )


# --- Jagged Knife Hexer ------------------------------------------------------

CURSE = qualified(ADVERSARY, "Curse")
CURSED = "Cursed"


@action(CURSE)
def curse(adversary, target, fight: Fight):
    """Curse a target within Far range, for the rest of the fight.

    SRD: "Choose a target within Far range and temporarily Curse them. While the
    target is Cursed, you can mark a Stress when that target rolls with Hope to
    make the roll be with Fear instead."

    Applying it is this half and costs nothing; the Stress is spent later, per
    roll, in `curse_turns_hope_to_fear` below.

    SIMULATION RULE - interpretation, ruled. The SRD clears a *temporary*
    condition when its holder "makes a move against it" - for a PC, spending
    their spotlight on a successful action roll. Nothing here models a PC
    spending a turn that way, so the ruling is that a condition an adversary
    applies to a PC lasts **until their next rest** unless the feature says
    otherwise, which inside one fight means it never lifts: an `end` of None.
    The GM-side default is the other way round and unchanged - a condition the
    party puts on an adversary ends when the GM pays a Fear.

    USAGE POLICY - ruled. Nothing to pay, so nothing to gate: it joins the
    shuffled pool of options whenever there is somebody left to curse. The one
    check is that the target isn't Cursed already, since re-applying it would
    spend a whole spotlight to change nothing.
    """
    if fight.has_condition(target, CURSED):
        return None

    fight.apply_condition(target, Condition(name=CURSED))
    fight.note(f"{adversary.name} lays a curse on {target.name}")
    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


@convert_party_roll(CURSE)
def curse_turns_hope_to_fear(adversary, roller, roll, fight=None):
    """Mark a Stress to make a Cursed PC's roll with Hope be with Fear instead.

    The passive half of Curse, registered against the same name so the feature
    stays one piece of content in one place.

    **Done by swapping the two duality dice**, which is worth understanding
    because `DualityRollResult` is frozen and derives everything from the dice it
    was rolled with. Exchanging the Hope and Fear results leaves the total
    untouched (it is their sum), leaves success and criticality exactly as they
    fell, and flips the only thing this feature is entitled to flip: which of the
    two came up higher. Nothing has to be overridden and no stored field
    duplicates a derived one.

    USAGE POLICY - ruled. A Reaction, so it fires on every trigger it can pay
    for. The Hexer's four Stress are therefore four converted rolls, and each one
    is worth more than a Hope: the party loses the Hope, the GM gains a Fear, and
    the spotlight passes to the GM instead of staying with the party. Two of the
    three are things the Hexer's own attacks could never buy.
    """
    if fight is None or roll.outcome is not DualityOutcome.HOPE:
        return None
    if not fight.has_condition(roller, CURSED):
        return None
    if not adversary.can_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(
        f"{roller.name}'s hope curdles under the curse ({adversary.name} marks a Stress)"
    )
    return replace(
        roll,
        hope_die_result=roll.fear_die_result,
        fear_die_result=roll.hope_die_result,
    )


CHAOTIC_FLUX = qualified(ADVERSARY, "Chaotic Flux")

# "Up to three targets", as printed - the feature's own number rather than a
# knob. How many are actually within Very Close is still the area rule's answer,
# and at that band it reaches one or two.
CHAOTIC_FLUX_TARGETS = 3


@action(CHAOTIC_FLUX)
def chaotic_flux(adversary, target, fight: Fight):
    """Mark a Stress to attack up to three targets within Very Close for 2d6+3.

    SRD: "Make an attack against up to three targets within Very Close range.
    Mark a Stress to deal 2d6+3 magic damage to targets the Hexer succeeded
    against."

    2d6+3 averages 10 against the Hexer's printed 1d6+2 at 6.5, and it can land
    on more than one PC - which makes this, not the staff, what a Hexer's Stress
    is for once its curse is out.

    Typed magic explicitly, though the Hexer's staff is magic too and the
    fallback would have reached the same answer - stating it means the feature
    stays correct if the stat block is ever retuned.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table, with deliberately no threshold on how
    many PCs it reaches. Four Stress against 4 HP means the Hexer is inside the
    line from full health and can keep this up until the Stress runs out.
    """
    caught = targets_in_area(Range.VERY_CLOSE, fight.conscious_party)[
        :CHAOTIC_FLUX_TARGETS
    ]
    if not caught or not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} looses a wave of chaotic magic (Chaotic Flux)")
    result, _ = adversary.area_attack(
        caught,
        fight=fight,
        damage_dice=[DiceGroup(count=2, sides=6)],
        damage_modifier=3,
        damage_type=DamageType.MAGIC,
    )
    return result


# --- Jagged Knife Kneebreaker ------------------------------------------------

IVE_GOT_EM = qualified(ADVERSARY, "I've Got 'Em")
HOLD_THEM_DOWN = qualified(ADVERSARY, "Hold Them Down")

# "Take double damage", as printed.
IVE_GOT_EM_MULTIPLIER = 2


@damage_multiplier(IVE_GOT_EM)
def ive_got_em(adversary, target, attacker, fight=None) -> int | None:
    """Creatures this adversary has Restrained take double damage from its allies.

    SRD: "Creatures Restrained by the Kneebreaker take double damage from attacks
    by other adversaries."

    The feature this simulator's Restrained ruling was reopened for. Being
    Restrained still does nothing on its own - no movement is modelled - but the
    condition is now *recorded* when a feature applies one, precisely so content
    like this can ask. "By the Kneebreaker" is read strictly, through
    `Condition.source`: a creature some other adversary is holding is not one
    this Kneebreaker has.

    "By other adversaries" is read strictly too, so the Kneebreaker's own attacks
    are unaffected - which is the whole shape of the stat block. It holds
    somebody down and everything else in the fight hits twice as hard, so a
    Kneebreaker is worth far more beside a Lieutenant than it is alone.

    Doubling lands **before** the target's thresholds, which is where the effect
    really lives: 8 damage against a threshold of 11 marks 1 HP, and 16 marks 2.
    """
    if fight is None or attacker is adversary:
        return None

    held = fight.condition_on(target, RESTRAINED)
    if held is None or held.source is not adversary:
        return None

    # Worth a line of its own in the play-by-play: the loop reports the damage
    # *rolled*, and what lands is twice that, so a reader would otherwise see a
    # hit mark more HP than the printed number explains.
    fight.note(
        f"{target.name} is held fast, and takes double damage "
        f"(I've Got 'Em: {adversary.name})"
    )
    return IVE_GOT_EM_MULTIPLIER


@action(
    HOLD_THEM_DOWN,
    unmodelled=[
        "Hold Them Down: what being Restrained stops - moving - which has no "
        "representation here. The condition is recorded so other content can "
        "key on it, and the Vulnerable it applies alongside is modelled in full",
    ],
)
def hold_them_down(adversary, target, fight: Fight):
    """Pin a target: no damage, but Restrained and Vulnerable until they break out.

    SRD: "Make an attack against a target within Melee range. On a success, the
    target takes no damage but is Restrained and Vulnerable. The target can break
    free, clearing both conditions, with a successful Strength Roll or is freed
    automatically if the Kneebreaker takes Major or greater damage."

    The one attack in the catalogue that deals nothing on purpose - and the
    clause that proves the rule for every other feature, since a page only has to
    say "takes no damage" where damage is what would otherwise happen.

    What it buys is Vulnerable, which is large: every roll against that PC has
    Advantage until they get out, and with a Kneebreaker on the field their
    allies are also hitting them twice as hard (`I've Got 'Em`).

    Both ways out are modelled. The Strength Roll is offered at each moment the
    loop announces, and frees the target of both conditions at once; the
    Kneebreaker taking Major damage frees everyone it holds, which is
    `hold_them_down_releases` below.

    USAGE POLICY - ruled. Nothing to pay, so nothing to gate: it joins the
    shuffled pool of options, the standing default.
    """
    result = adversary.attack(
        target, fight=fight, damage_dice=[], damage_modifier=0
    )
    if result.damage_roll is None:
        return result

    escape = _breaks_free(("strength",), adversary.difficulty, also_clear=(VULNERABLE,))
    fight.apply_condition(
        target, Condition(name=RESTRAINED, end=escape, source=adversary)
    )
    fight.apply_condition(target, Condition(name=VULNERABLE, source=adversary))
    fight.note(
        f"{adversary.name} pins {target.name} down - Restrained and Vulnerable "
        f"until they break free"
    )
    return result


@on_damaged(HOLD_THEM_DOWN)
def hold_them_down_releases(adversary, amount: int, hp_marked: int, fight=None) -> None:
    """Major damage to this adversary frees everyone it was holding.

    Keyed on the damage *rolled* reaching the Major threshold, which is what
    "takes Major or greater damage" says - the same reading Acid Bath uses for
    Severe, and deliberately not the HP it cost.
    """
    if fight is None or amount < adversary.major_threshold:
        return

    _release_held(adversary, fight, RESTRAINED, VULNERABLE)
    fight.note(f"{adversary.name} loses its grip")


# --- Jagged Knife Lieutenant -------------------------------------------------

TACTICIAN = qualified(ADVERSARY, "Tactician")

# "Two allies within Close range", as printed.
TACTICIAN_ALLIES = 2


@on_spotlight(TACTICIAN)
def tactician(adversary, fight=None) -> None:
    """Mark a Stress when spotlighted to also spotlight two allies within Close.

    SRD: "When you spotlight the Lieutenant, mark a Stress to also spotlight two
    allies within Close range."

    **It does not cost the Lieutenant its action**, which is the ruling that
    decides which hook this is. The trigger is being spotlighted rather than
    something done with the spotlight, so it fires on arrival and the Lieutenant
    still attacks afterwards - the SRD files it as an Action, but the word
    "also" is doing the work.

    Which allies are within Close goes through the area rule, and which of them
    get picked is random among those in range, for the reason every unordered
    list in this project is shuffled.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table. 6 HP against three Stress puts the
    Lieutenant inside the line from full health, so in practice it rallies until
    the Stress runs out.
    """
    if fight is None or not adversary.will_spend_stress(1):
        return

    allies = [other for other in fight.living_adversaries if other is not adversary]
    within = targets_reached(Range.CLOSE, len(allies)) if allies else 0
    rallied = random.sample(allies, min(within, TACTICIAN_ALLIES)) if within else []
    if not rallied:
        return

    adversary.spend_stress(1)
    for ally in rallied:
        fight.grant_activation(ally)
    fight.note(
        f"{adversary.name} directs {len(rallied)} "
        f"{'ally' if len(rallied) == 1 else 'allies'} (Tactician)"
    )


MORE_WHERE_THAT_CAME_FROM = qualified(ADVERSARY, "More Where That Came From")

# The summons, as printed: three Jagged Knife Lackeys, by name.
SUMMONED_MINION = "Jagged Knife Lackey"
SUMMONED_COUNT = 3


@action(
    MORE_WHERE_THAT_CAME_FROM,
    unmodelled=[
        "More Where That Came From: the Lackeys appearing at Far range, which is "
        "positioning. They join the fight and are targetable immediately",
    ],
)
def more_where_that_came_from(adversary, target, fight: Fight):
    """Summon three Jagged Knife Lackeys into the fight.

    SRD: "Summon three Jagged Knife Lackeys, who appear at Far range."

    The first feature that adds adversaries to a fight already under way; see
    `combat/state.py`'s `summon` for what that means for the loop. Each is
    spawned from the catalogue, so the summons have their own HP tracks and the
    catalogue definition is never mutated. A Lackey is a 1 HP Minion with a flat
    2 damage attack, and three of them within Close range of each other can make
    a Group Attack, so what this really buys is a shared attack the Lieutenant
    didn't have to roll.

    Declines rather than raising if the Lackey isn't in the catalogue at all: an
    encounter can be run against a cut-down catalogue, and a feature that
    couldn't find its summons should pass the spotlight to something that works.

    USAGE POLICY - ruled. Nothing to pay, so nothing to gate: it is one of the
    options and the shuffle picks it about as often as anything else. **No cap,
    deliberately** - the proposal to bound it (once per fight, or only below N
    live Lackeys) was put and declined, on the grounds that Minions die to any
    damage and a summoned field clears about as fast as it arrives. So the
    Lieutenant can keep whistling up reinforcements for as long as the fight
    lasts, which is what the page describes. `MAX_PC_ACTIONS` is the only
    backstop, and it is scaffolding rather than a rule about this feature.
    """
    try:
        definition = find_adversary(SUMMONED_MINION)
    except KeyError:
        return None

    for _ in range(SUMMONED_COUNT):
        fight.summon(definition.spawn())
    fight.note(
        f"{adversary.name} whistles up {SUMMONED_COUNT} {SUMMONED_MINION}s "
        f"(More Where That Came From)"
    )
    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


COUP_DE_GRACE = qualified(ADVERSARY, "Coup de Grace")
COUP_DE_GRACE_FEAR = 1


@action(COUP_DE_GRACE)
def coup_de_grace(adversary, target, fight: Fight):
    """Spend a Fear to hit a Vulnerable target for 2d6+12, and cost them a Stress.

    SRD: "Spend a Fear to make an attack against a Vulnerable target within Close
    range. On a success, deal 2d6+12 physical damage and the target must mark a
    Stress."

    2d6+12 averages 19 against the Lieutenant's printed 1d8+3 at 7.5, so this is
    the single largest tier 1 attack in the catalogue - and it is gated on the
    target already being Vulnerable, which is a printed requirement rather than a
    policy of ours. The Fear is spent to *make* the attack, so a miss still costs
    it.

    Worth reading beside the rest of the gang. Nothing in the Lieutenant's own
    kit makes anybody Vulnerable, but a Jagged Knife band is not played alone:
    the Kneebreaker's Hold Them Down applies exactly this condition, and a PC who
    has marked their last Stress is Vulnerable anyway. This is the payoff card of
    a kit rather than a feature that stands by itself.

    The attack is rolled through the shared advantage rule rather than flat,
    since a Vulnerable target hands every roll against them Advantage - which,
    this feature being what it is, is always true when it fires.

    USAGE POLICY - ruled. Used whenever the Fear can be paid and the target
    qualifies, and among the options that pass the choice is random.
    """
    from combat.policy import adversary_attack_advantage

    if fight.fear < COUP_DE_GRACE_FEAR:
        return None
    if not fight.is_vulnerable(target):
        return None

    fight.spend_fear(COUP_DE_GRACE_FEAR)
    fight.note(f"{adversary.name} goes for the kill (Coup de Grace: GM spends a Fear)")
    result = adversary.attack(
        target,
        adversary_attack_advantage(adversary, target, fight),
        fight,
        damage_dice=[DiceGroup(count=2, sides=6)],
        damage_modifier=12,
        damage_type=DamageType.PHYSICAL,
    )
    if result.damage_roll is None:
        return result

    target.mark_stress(1)
    return result


# --- Jagged Knife Shadow -----------------------------------------------------

BACKSTAB = qualified(ADVERSARY, "Backstab")


@standard_damage(BACKSTAB)
def backstab(adversary, target, roll=None, fight=None):
    """A standard attack made with Advantage deals 1d6+6 instead.

    SRD: "When the Shadow succeeds on a standard attack that has advantage, they
    deal 1d6+6 physical damage instead of their standard damage."

    Reads the Advantage off **the roll that was actually made**, which is why
    `standard_damage` is handed one. Working it out again here would ask the
    advantage rule a second time and consume Cloaked's token twice - and it would
    be a second expression of a rule that already lives in
    `combat/policy.py`'s `adversary_attack_advantage`.

    Two sources reach it today: the target being Vulnerable, and the Shadow's own
    Cloaked. 1d6+6 averages 9.5 against the printed 1d4+4 at 6.5, so the pair is
    worth about +3 on every attack the Shadow sets up.
    """
    if roll is None or roll.advantage_state is not AdvantageState.ADVANTAGE:
        return None
    return [DiceGroup(count=1, sides=6)], 6


CLOAKED = qualified(ADVERSARY, "Cloaked")
CLOAKED_TOKEN = "Cloaked"


@action(
    CLOAKED,
    unmodelled=[
        "Cloaked: being Hidden itself, which the SRD also uses to stop a "
        "combatant being targeted. Nothing here tracks Hidden as a condition, so "
        "only the Advantage on the next attack is modelled",
    ],
)
def cloaked(adversary, target, fight: Fight):
    """Vanish: the next attack this adversary makes has Advantage.

    SRD: "Become Hidden until after the Shadow's next attack. Attacks made while
    Hidden from this feature have advantage."

    Spends the whole spotlight and rolls nothing, which is the trade: a turn of
    no damage buys Advantage, and with Backstab it also buys 1d6+6 instead of
    1d4+4 on the attack that follows. Declines while already cloaked, since there
    is nothing to buy twice.

    USAGE POLICY - ruled. Nothing to pay, so it is simply one of the options and
    the shuffle picks among them - which means a Shadow will sometimes spend a
    spotlight cloaking when striking would have been better, and sometimes set
    up a 1d6+6 it would otherwise never have rolled. That is the random-among-
    viable default doing its job rather than a threshold nobody chose.
    """
    if fight.token_count(adversary, CLOAKED_TOKEN):
        return None

    fight.set_token(adversary, CLOAKED_TOKEN, 1)
    fight.note(f"{adversary.name} melts into the shadows (Cloaked)")
    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


@attack_advantage(CLOAKED)
def cloaked_grants_advantage(adversary, target, fight=None):
    """The cloak pays out on the next attack, and is spent doing it.

    Being asked *is* the attack being made - the advantage rule is consulted once,
    immediately before the roll - so the token is cleared here rather than
    needing something afterwards to notice the attack happened. That is what
    "until after the Shadow's next attack" comes to.
    """
    if fight is None or not fight.token_count(adversary, CLOAKED_TOKEN):
        return None

    fight.set_token(adversary, CLOAKED_TOKEN, 0)
    fight.note(f"{adversary.name} strikes from hiding")
    return AdvantageState.ADVANTAGE


# --- Minor Chaos Elemental ---------------------------------------------------

ARCANE_FORM = qualified(ADVERSARY, "Arcane Form")


@damage_resistance(ARCANE_FORM)
def arcane_form(adversary, damage_type, fight=None) -> float | None:
    """This adversary is resistant to magic damage.

    SRD: "The Elemental is resistant to magic damage."

    The first resistance in the catalogue, and the whole reason
    `content/damage_types.py` exists. Halving lands **before** the Elemental's
    thresholds of 7 and 14, which is what the SRD requires and where the effect
    really lives: a 13-point spell goes from marking 2 HP to marking 1, and a
    16-point one from 3 to 2. Against a 7 HP track that is close to doubling how
    long the Elemental survives a caster.

    Declines on anything that isn't magic, which includes untyped damage - a
    resistance applies to a type that was stated, so a feature nobody has typed
    can only ever fail to be resisted rather than be resisted wrongly.

    Worth reading beside the stat block's other half: the Elemental's own Warp
    Blast is magic, and Magical Reflection sends half a melee attacker's damage
    back as magic too. So a party's answer to this adversary is genuinely a
    weapon choice - the front line's steel gets through in full, and the
    spellcasters do not.
    """
    if damage_type is not DamageType.MAGIC:
        return None
    return RESISTED


SICKENING_FLUX = qualified(ADVERSARY, "Sickening Flux")


@action(SICKENING_FLUX)
def sickening_flux(adversary, target, fight: Fight):
    """Mark an HP: everyone Close marks a Stress and is Vulnerable until healed.

    SRD: "Mark a HP to force all targets within Close range to mark a Stress and
    become Vulnerable until their next rest or they clear a HP."

    The first feature in the catalogue whose cost is the adversary's **own HP**,
    which needed a rule of its own - see `Adversary.will_spend_hp`. The short of
    it: spent freely from full health, never the last one.

    The effect is the largest in this batch. Vulnerable hands every roll against
    those PCs Advantage, and "until their next rest or they clear a HP" means it
    does not wear off on its own - a PC who was unhurt when it landed cannot
    clear an HP they never marked, so for them it lasts the fight. The forced
    Stress is measured first, deliberately: a PC with no free slot marks an HP
    instead, and that HP is then part of what they would have to clear.

    USAGE POLICY - ruled. Available whenever it isn't the Elemental's last HP,
    which in practice means from the opening spotlight.
    """
    caught = targets_in_area(Range.CLOSE, fight.conscious_party)
    if not caught or not adversary.will_spend_hp(1):
        return None

    adversary.mark_hp(1)
    fight.note(f"{adversary.name} warps the air around it (Sickening Flux: marks an HP)")
    for pc in caught:
        pc.mark_stress(1)
        fight.apply_condition(
            pc,
            Condition(
                name=VULNERABLE,
                end=until_they_clear_hp(pc.hp_marked),
                source=adversary,
            ),
        )
        fight.note(f"{pc.name} sickens, marking a Stress, and is Vulnerable")
    # Fired, so the spotlight is spent - but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


REMAKE_REALITY = qualified(ADVERSARY, "Remake Reality")
REMAKE_REALITY_FEAR = 1


@action(
    REMAKE_REALITY,
    unmodelled=[
        "Remake Reality: the area becoming a different biome, which is terrain. "
        "Nothing here represents where a fight happens, so only the damage is "
        "modelled",
    ],
)
def remake_reality(adversary, target, fight: Fight):
    """Spend a Fear: 2d6+3 direct damage to everyone within Very Close.

    SRD: "Spend a Fear to transform the area within Very Close range into a
    different biome. All targets within this area take 2d6+3 direct magic
    damage."

    No attack roll and no reaction roll: the ground changes underneath them.
    Direct, so the party's free Armor Slot doesn't soften it, which against this
    party is worth close to a whole extra HP a head on top of an average of 10.

    One damage roll shared by everyone caught, the way Rampaging Fury does it -
    the SRD describes a single transformation rather than a roll per target.

    USAGE POLICY - ruled. Used whenever the GM can afford the Fear, and among the
    options that pass the choice is random.
    """
    caught = targets_in_area(Range.VERY_CLOSE, fight.conscious_party)
    if not caught or fight.fear < REMAKE_REALITY_FEAR:
        return None

    fight.spend_fear(REMAKE_REALITY_FEAR)
    fight.note(f"{adversary.name} remakes the ground itself (GM spends a Fear)")
    damage = roll_damage(dice_groups=[DiceGroup(count=2, sides=6)], modifier=3)
    for pc in caught:
        pc.take_damage(damage.total, fight, direct=True, damage_type=DamageType.MAGIC)
        fight.note(f"{pc.name} is caught in the change for {damage.total}")
    return AttackResult(attack_roll=None, damage_roll=None)


MAGICAL_REFLECTION = qualified(ADVERSARY, "Magical Reflection")

# "Within Close range" - the bands at or inside it. Read off the attacker's
# weapon, so anything reaching further (Far, Very Far) doesn't trigger it.
WITHIN_CLOSE = (Range.MELEE, Range.VERY_CLOSE, Range.CLOSE)


@on_attacked(
    MAGICAL_REFLECTION,
    unmodelled=[
        "Magical Reflection: only a weapon attack reaches this, as with "
        "Armor-Shredding Shards. Content that rolls an attack of its own has no "
        "weapon and so no range to read, and never triggers it",
    ],
)
def magical_reflection(
    adversary, attacker, weapon, damage=0, hp_marked=0, fight=None
) -> None:
    """An attack from Close range or nearer costs the attacker half what they dealt.

    SRD: "When the Elemental takes damage from an attack within Close range, deal
    an amount of damage to the attacker equal to half the damage they dealt."

    SIMULATION RULE - policy. "Within Close range" is read off the **attacker's
    weapon**, the same handle Armor-Shredding Shards uses: everyone is assumed to
    have attacked from the greatest range their weapon allows, so a Melee, Very
    Close or Close weapon triggers this and a Far one does not. The Elemental is
    therefore a tax on the front line and free for archers.

    Half, rounded down, and measured on the damage **rolled** rather than the HP
    it cost - "the damage they dealt" is the number, and a hit the Elemental
    shrugged off still came in at that size. The reflection is ordinary damage
    going the other way, so the PC's own armor and damage responses get their say.

    SIMULATION RULE - interpretation, ruled. The page prints no damage type for
    the rebound. The ruling is the standing one for any adversary feature that
    states none: it deals the type of the adversary's own standard attack, which
    for the Elemental is magic. So this is not the attacker's blow returning in
    kind - a Greatsword's rebound is magic too - it is the Elemental's own
    magic, and a PC resistant to magic halves it.

    The trigger is a landed attack, so a miss reflects nothing.
    """
    if fight is None or damage <= 0:
        return
    if not any(canonical(weapon.range) == canonical(band.value) for band in WITHIN_CLOSE):
        return

    reflected = damage // 2
    if reflected <= 0:
        return

    attacker.take_damage(reflected, fight, damage_type=adversary.type_of_damage())
    fight.note(
        f"{attacker.name}'s blow rebounds off {adversary.name} for {reflected} "
        f"(Magical Reflection)"
    )


# --- Minor Fire Elemental ----------------------------------------------------

SCORCHED_EARTH = qualified(ADVERSARY, "Scorched Earth")


@action(
    SCORCHED_EARTH,
    unmodelled=[
        "Scorched Earth: choosing the point. The page lets the GM place the "
        "Very Close area anywhere within Far range, which is positioning - so "
        "the area is measured around the Elemental instead, and a GM who would "
        "have placed it on the tightest cluster gets no credit for it",
    ],
)
def scorched_earth(adversary, target, fight: Fight):
    """Mark a Stress: the ground within Very Close bursts into flames for 2d8.

    SRD: "Mark a Stress to choose a point within Far range. The ground within
    Very Close range of that point immediately bursts into flames. All creatures
    within this area must make an Agility Reaction Roll. Targets who fail take
    2d8 magic damage from the flames. Targets who succeed take half damage."

    **The band is the area's own size, not the range it can be placed at.** Very
    Close is what burns; Far is only how far away the Elemental can start the
    fire, and no positions are tracked for that to mean anything.

    **"All creatures" means the Elemental's own side too**, and they roll to save
    exactly as a PC does - a flat d20, since an adversary has no traits. The
    printed noun is doing real work here: Hellfire two stat blocks later says
    "all targets" and reaches only the party. It is a genuine cost of the
    feature, and it is why a Fire Elemental is awkward to field beside anything
    fragile. The Elemental itself is excluded, the way Acid Bath excludes the
    Burrower.

    The first feature where a successful Reaction Roll buys *half* damage rather
    than escaping the effect - see `_flames`, which both this and Hellfire use.
    A critical still ignores it entirely, per the standing rule on reaction rolls.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table, with no threshold on how many it
    reaches - and deliberately none on how many of them are allies either. 9 HP
    against three Stress puts the Elemental inside the line from full health, so
    in practice this is simply what it does until the Stress runs out - and
    Consume Kindling can buy some of it back.
    """
    caught = targets_in_area(
        Range.VERY_CLOSE,
        list(fight.conscious_party)
        + [other for other in fight.living_adversaries if other is not adversary],
    )
    if not caught or not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} sets the ground alight (Scorched Earth)")
    return _flames(
        adversary,
        fight,
        caught,
        [DiceGroup(count=2, sides=8)],
        0,
        DamageType.MAGIC,
    )


EXPLOSION = qualified(ADVERSARY, "Explosion")
EXPLOSION_FEAR = 1


@action(
    EXPLOSION,
    unmodelled=[
        "Explosion: the knockback to Far range, which is where a combatant ends "
        "up and has nothing to change here. The damage is modelled",
    ],
)
def explosion(adversary, target, fight: Fight):
    """Spend a Fear to erupt, attacking everyone within Close for 1d8.

    SRD: "Spend a Fear to erupt in a fiery explosion. Make an attack against all
    targets within Close range. Targets the Elemental succeeds against take 1d8
    magic damage and are knocked back to Far range."

    An ordinary area attack - one roll against everyone, unlike Scorched Earth's
    save-for-half - so the two halves of this stat block ask the party for
    different things: Evasion here, an Agility Reaction Roll there.

    USAGE POLICY - ruled. Used whenever the GM can afford the Fear, and among the
    options that pass the choice is random. 1d8 averages 4.5 against the
    Elemental's printed 1d10+4 at 9.5, so this is much the weaker attack against
    a single PC and only pays when Close reaches two or more - and there is
    deliberately no threshold saying so.
    """
    caught = targets_in_area(Range.CLOSE, fight.conscious_party)
    if not caught or fight.fear < EXPLOSION_FEAR:
        return None

    fight.spend_fear(EXPLOSION_FEAR)
    fight.note(f"{adversary.name} erupts (Explosion: GM spends a Fear)")
    result, _ = adversary.area_attack(
        caught,
        fight=fight,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=0,
        damage_type=DamageType.MAGIC,
    )
    return result


CONSUME_KINDLING = qualified(ADVERSARY, "Consume Kindling")
CONSUME_KINDLING_TOKEN = "Consume Kindling"

# "Three times per scene", as printed - the feature's own number rather than a
# knob, and a scene is one fight here.
CONSUME_KINDLING_USES = 3


@on_spotlight(CONSUME_KINDLING)
def consume_kindling(adversary, fight=None) -> None:
    """Three times a fight, clear an HP - or a Stress once the HP track is clean.

    SRD: "Three times per scene, when the Elemental moves onto objects that are
    highly flammable, consume them to clear a HP or a Stress."

    SIMULATION RULE - policy, ruled. The printed trigger is moving onto flammable
    scenery, and neither movement nor terrain has any representation here. Rather
    than dismiss the feature - it is worth up to 3 HP on a 9 HP Solo, which is
    far too large to wave through - the ruling is that **the kindling is always
    to hand**: the Elemental consumes some on each of its spotlights until its
    three uses are gone. That makes it effectively a 12 HP adversary, and the
    availability is the invented part rather than the effect.

    **HP first, then Stress**, also ruled. HP is what keeps it on the field, so
    it takes that whenever any is marked; a use is only spent on Stress once
    there is no HP to clear, where it buys another Scorched Earth instead. A use
    is never spent on nothing, so an unhurt Elemental at full Stress banks them.

    Fired on the spotlight rather than as an Action, because the page makes it a
    Reaction to moving and the Elemental moves when it acts - so this costs it
    nothing and does not compete with Scorched Earth or Explosion.
    """
    if fight is None:
        return
    if fight.token_count(adversary, CONSUME_KINDLING_TOKEN) >= CONSUME_KINDLING_USES:
        return

    if adversary.hp_marked > 0:
        adversary.clear_hp(1)
        cleared = "an HP"
    elif adversary.stress_marked > 0:
        adversary.clear_stress(1)
        cleared = "a Stress"
    else:
        return  # nothing to clear, so nothing is spent

    fight.add_token(adversary, CONSUME_KINDLING_TOKEN, cap=CONSUME_KINDLING_USES)
    left = CONSUME_KINDLING_USES - fight.token_count(adversary, CONSUME_KINDLING_TOKEN)
    fight.note(
        f"{adversary.name} consumes kindling, clearing {cleared} "
        f"({left} left this scene)"
    )


# --- Minor Demon -------------------------------------------------------------

ALL_MUST_FALL = qualified(ADVERSARY, "All Must Fall")


@on_party_attack_roll(ALL_MUST_FALL)
def all_must_fall(adversary, roller, roll, fight=None) -> None:
    """A PC who fails with Fear near this adversary loses a Hope.

    SRD: "When a PC rolls a failure with Fear while within Close range of the
    Demon, they lose a Hope."

    A critical is never "with Fear" and a success is not a failure, so the band
    this fires in is narrow - roughly one roll in four - but it costs the GM
    nothing at all, which makes it the only free Hope drain in the catalogue.

    SIMULATION RULE - policy. "Within Close range of the Demon" is positioning,
    so the **area rule answers it**, measured over the conscious party: that is
    the field the band has to reach, exactly as Luckbender measures its ally
    check over the rest of the party rather than over the adversaries. Against
    four PCs Close covers three of them, so a given failure lands in range three
    times in four.

    The Hope is taken through `spend_hope`, so it is counted as spent in the
    report. Strictly a PC losing a Hope to a curse has not *spent* it, but the
    alternative is a fifth Hope figure nobody asked for, and the four the report
    prints would stop reconciling if it simply vanished.
    """
    if fight is None or roll.is_success:
        return
    if roll.outcome is not DualityOutcome.FEAR:
        return
    if not roller.can_spend_hope(1):
        return
    if random.random() >= chance_within(Range.CLOSE, len(fight.conscious_party)):
        return

    roller.spend_hope(1)
    fight.note(f"{roller.name}'s hope fails them near {adversary.name} (All Must Fall)")


HELLFIRE = qualified(ADVERSARY, "Hellfire")
HELLFIRE_FEAR = 1


@action(HELLFIRE)
def hellfire(adversary, target, fight: Fight):
    """Spend a Fear: 1d20+3 to everyone within Far, halved by an Agility save.

    SRD: "Spend a Fear to rain down hellfire within Far range. All targets within
    the area must make an Agility Reaction Roll. Targets who fail take 1d20+3
    magic damage. Targets who succeed take half damage."

    Far reaches the whole field, so unlike Scorched Earth this has no band
    holding it back - and 1d20+3 averages 13.5, which is Severe for most tier 1
    PCs. It is the largest area effect in tier 1 by a distance, and the save only
    halves it.

    **"All targets", not "all creatures"** - so this reaches the party alone, and
    the Demon's allies stand in the fire untouched. Scorched Earth two stat blocks
    earlier says creatures and does catch them. The two landing in the same batch
    is what makes the distinction hard to put down to loose wording, and it is
    worth knowing which way round they are: the Demon is safe to field beside
    anything, the Fire Elemental is not.

    Magic damage from a stat block whose printed Claws are physical, so the type
    is stated here rather than inherited.

    USAGE POLICY - ruled. Used whenever the GM can afford the Fear, and among the
    options that pass the choice is random.
    """
    caught = targets_in_area(Range.FAR, fight.conscious_party)
    if not caught or fight.fear < HELLFIRE_FEAR:
        return None

    fight.spend_fear(HELLFIRE_FEAR)
    fight.note(f"{adversary.name} rains down hellfire (GM spends a Fear)")
    return _flames(
        adversary,
        fight,
        caught,
        [DiceGroup(count=1, sides=20)],
        3,
        DamageType.MAGIC,
    )


REAPER = qualified(ADVERSARY, "Reaper")


@damage_bonus(REAPER)
def reaper(adversary, target, fight: Fight) -> int:
    """Mark a Stress for damage equal to this adversary's own marked HP.

    SRD: "Before rolling damage for the Demon's attack, you can mark a Stress to
    gain a bonus to the damage roll equal to the Demon's current number of marked
    HP."

    Asked from inside the damage roll, which is where "before rolling damage"
    puts it - and by then the attack has landed, so the Stress is never spent on
    a miss. The same hook and the same window as the Construct's Overload.

    The stat block reads backwards from a Horde: the Demon gets *more* dangerous
    as the party wears it down. At 7 of 8 HP marked its Claws swing 1d8+13.

    USAGE POLICY - ruled. A **Reaction**, so it fires whenever its trigger
    happens and the Stress can be paid - with one general qualifier the user
    ruled alongside it: **a Reaction whose benefit computes to zero is not
    taken.** An undamaged Demon would otherwise burn a Stress for +0, and all
    four would be gone before the feature was worth anything. That is not an
    expected-damage comparison - the bonus is a number both sides of the table
    can read off the stat block - so the rule against those does not reach it.
    """
    if fight is None:
        return 0

    bonus = adversary.hp_marked
    if bonus <= 0:
        return 0
    if not adversary.can_spend_stress(1):
        return 0

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} reaps its own wounds (Reaper: +{bonus} damage)")
    return bonus


# --- Green Ooze --------------------------------------------------------------

SLOW = qualified(ADVERSARY, "Slow")
SLOW_TOKEN = "Slow"


@skip_spotlight(SLOW)
def slow(adversary, fight=None) -> bool:
    """This adversary spends every other spotlight preparing, and cannot act.

    SRD: "When you spotlight the Ooze and they don't have a token on their stat
    block, they can't act yet. Place a token on their stat block and describe
    what they're preparing to do. When you spotlight the Ooze and they have a
    token on their stat block, clear the token and they can act."

    So the *first* spotlight is always the wasted one, and it alternates from
    there. That is a large tax and the reason the Green Ooze's other numbers
    look generous: it acts half as often as anything else on the field, and the
    activation it loses still cost the GM whatever the turn charged for it.

    Being asked is the commitment - the hook is consulted exactly once per
    activation - so the token is flipped here rather than needing something
    afterwards to notice the spotlight happened. The same contract Cloaked keeps
    with the advantage rule.
    """
    if fight is None:
        return False

    if fight.token_count(adversary, SLOW_TOKEN):
        fight.set_token(adversary, SLOW_TOKEN, 0)
        return False

    fight.set_token(adversary, SLOW_TOKEN, 1)
    fight.note(f"{adversary.name} gathers itself, and cannot act yet (Slow)")
    return True


ACIDIC_FORM = qualified(ADVERSARY, "Acidic Form")


@on_hit(ACIDIC_FORM)
def acidic_form(adversary, target, result, fight: Fight) -> None:
    """A successful attack costs the target an Armor Slot, or an HP if they have none.

    SRD: "When the Ooze makes a successful attack, the target must mark an Armor
    Slot without receiving its benefits (they can still use armor to reduce the
    damage). If they can't mark an Armor Slot, they must mark an additional HP."

    The parenthesis settles the order, exactly as it does for Spit Acid: the hit
    resolves normally first, free slot and all, and the burned slot comes
    afterwards - so a PC down to one slot spends it on the damage and then has
    none left for the acid. Firing on `on_hit` is what makes that true, since
    the damage has already been applied by then.

    Keyed on the attack succeeding rather than on HP being marked, which is what
    the trigger says - a hit the armor swallowed entirely still burns a slot.

    Carried by both Oozes, so it is registered once and reached by whichever is
    swinging. Against a party of two- and three-slot armor, a pair of Tiny Green
    Oozes strips the front line bare in a couple of exchanges, and everything
    after that is HP.
    """
    if result is None or result.damage_roll is None:
        return

    if _burn_an_armor_slot(target, fight):
        fight.note(f"{target.name}'s armor sizzles (Acidic Form: an Armor Slot)")
        return
    fight.note(f"{target.name} has no armor left to burn, and marks an HP")


ENVELOP = qualified(ADVERSARY, "Envelop")
ENVELOPED = "Enveloped"

# "The target must mark 2 Stress", as printed.
ENVELOP_STRESS = 2


def _envelop_costs_a_stress(holder, fight, moment: str) -> None:
    """Being enveloped costs a Stress on every action roll the holder makes.

    The Scorpion Poison's shape - `Condition.effect` on `BEFORE_AN_ACTION_ROLL` -
    with no die to roll: the SRD charges this one unconditionally.
    """
    if moment != BEFORE_AN_ACTION_ROLL:
        return
    holder.mark_stress(1)
    fight.note(f"{holder.name} struggles inside the ooze, and marks a Stress")


@action(
    ENVELOP,
    unmodelled=[
        "Envelop: being inside the Ooze as a position - there is nothing here "
        "for that to change. The Stress it costs, both up front and per action "
        "roll, is modelled in full, and so is being freed",
    ],
)
def envelop(adversary, target, fight: Fight):
    """A standard attack that swallows the target: 2 Stress, and more on every roll.

    SRD: "Make a standard attack against a target within Melee range. On a
    success, the Ooze envelops them and the target must mark 2 Stress. The target
    must mark an additional Stress when they make an action roll. If the Ooze
    takes Severe damage, the target is freed."

    The *printed* attack, so no dice are passed and the stat block's own 1d6+1 is
    rolled - and Acidic Form burns a slot on top of it, since this is a
    successful attack like any other.

    What it really costs is the Stress. Two up front plus one per action roll
    empties a six-slot track in four turns, and a PC with every Stress marked is
    Vulnerable for the rest of the fight. The forced Stress falls through to HP
    when it won't fit, per the SRD.

    **No already-enveloped check**, unlike Venomous Stinger. Rule 3 covers a
    feature whose *point* is the condition, and this one deals the Ooze's full
    damage and 2 more Stress whether or not the hold is already on - so declining
    would hold back a real attack over nothing.

    USAGE POLICY - ruled. Nothing to pay, so nothing to gate: it joins the
    shuffled pool alongside the standard attack, the standing default.
    """
    result = adversary.attack(target, fight=fight)
    if result.damage_roll is None:
        return result

    target.mark_stress(ENVELOP_STRESS)
    fight.apply_condition(
        target,
        Condition(name=ENVELOPED, effect=_envelop_costs_a_stress, source=adversary),
    )
    fight.note(
        f"{adversary.name} engulfs {target.name}, who marks {ENVELOP_STRESS} Stress"
    )
    return result


@on_damaged(ENVELOP)
def envelop_releases(adversary, amount: int, hp_marked: int, fight=None) -> None:
    """Severe damage to this adversary frees whoever it has swallowed.

    "If the Ooze takes Severe damage, the target is freed" - the printed way out,
    and the only one on the page, since this hold offers no roll to break free.
    Keyed on the damage rolled rather than the HP it cost, the reading Acid Bath
    established.

    There is a second, unprinted way out, and it is not this feature's business:
    the Ooze **leaving the fight** at all, whether killed or Split. A hold that
    only the holder can lift has to end when the holder is gone, or it would
    outlast the thing that caused it - and the Ooze's own 5/10 thresholds on a
    5 HP track mean two Major hits kill it without a Severe one ever landing, so
    that is the common case rather than the corner one. Handled generically by
    `FightState.release_conditions_from`.
    """
    if fight is None or amount < adversary.severe_threshold:
        return

    _release_held(adversary, fight, ENVELOPED)
    fight.note(f"{adversary.name} loses its grip, and the ooze sloughs away")


SPLIT = qualified(ADVERSARY, "Split")
SPLIT_FEAR = 1

# "When the Ooze has 3 or more HP marked", and "two" of them, as printed.
SPLIT_AT_HP_MARKED = 3
SPLIT_COUNT = 2


@on_damaged(SPLIT)
def split(adversary, amount: int, hp_marked: int, fight=None) -> None:
    """At 3 marked HP, spend a Fear to become two fresh copies of something smaller.

    SRD: "When the Ooze has 3 or more HP marked, you can spend a Fear to split
    them into two Tiny Green Oozes (with no marked HP or Stress). Immediately
    spotlight both of them."

    **Parameterised with what it becomes** - `Split (Tiny Green Ooze)`,
    `Split (Tiny Red Ooze)` - although the SRD prints the name bare on both, for
    the reason `Flying (X)` is parameterised: it is one rule whose argument
    differs per stat block, and hard-coding either would make the other silently
    turn into the wrong creature. A stat block writing `Split` with no parameter
    splits into nothing rather than guessing.

    Keyed on the Ooze's *state* rather than on the hit, which is what "has 3 or
    more HP marked" says - so it can fire on any wound once the track is deep
    enough, not only on the one that got there.

    **The Ooze leaves without being defeated**, through `FightState.remove` - the
    mirror of the `summon` the Lieutenant already uses. Marking its HP would have
    looked the same to the loop and told the reader a lie: the party is worse off
    at this moment, not better.

    Worth reading as arithmetic. A Green Ooze at 3 of 5 marked has 2 HP left; it
    becomes 4 HP spread over two bodies that are *harder to hit* (Difficulty 14
    against its own 8), both carrying Acidic Form, and both act immediately. The
    Fear is cheap for that. What the party loses by splitting it is the Envelop
    and the Slow - the Tinies have neither, so they act every turn.

    A defeated Ooze does not split: "when the Ooze has 3 or more HP marked" is
    about one still standing, and a stat block that split as it died would let a
    Fear undo the kill.

    USAGE POLICY - ruled. Used whenever the GM can afford the Fear, the standing
    default for a feature with no policy of its own.
    """
    if fight is None or adversary.is_defeated:
        return
    if adversary.hp_marked < SPLIT_AT_HP_MARKED:
        return
    if fight.fear < SPLIT_FEAR:
        return

    becomes = feature_parameter(adversary, SPLIT)
    if becomes is None:
        return

    try:
        definition = find_adversary(becomes)
    except KeyError:
        # An encounter can be run against a cut-down catalogue; a feature that
        # can't find what it becomes leaves the Ooze standing rather than
        # removing it and putting nothing back.
        return

    fight.spend_fear(SPLIT_FEAR)
    # Whatever it had swallowed comes loose with it - `remove` releases the holds
    # of anything leaving the field, so nothing about that is Split's business.
    fight.remove(adversary)
    for _ in range(SPLIT_COUNT):
        spawned = definition.spawn()
        fight.summon(spawned)
        fight.grant_activation(spawned)

    fight.note(
        f"{adversary.name} splits into {SPLIT_COUNT} {becomes}s, which act at "
        f"once (GM spends a Fear)"
    )


# --- Red Ooze ----------------------------------------------------------------

IGNITE = qualified(ADVERSARY, "Ignite")
IGNITED = "Ignited"

# "Extinguished with a successful Finesse Roll (14)" - the Difficulty is printed
# here, unlike the reaction rolls that fall back on the adversary's own.
IGNITE_ESCAPE_DIFFICULTY = 14


def _ignited_burns(holder, fight, moment: str) -> None:
    """Being on fire costs 1d4 magic damage on every action roll.

    The Scorpion Poison's shape - `Condition.effect` at `BEFORE_AN_ACTION_ROLL` -
    but the first one whose cost is **damage** rather than Stress, and there is
    no die to check first: the SRD charges this one every time.
    """
    if moment != BEFORE_AN_ACTION_ROLL:
        return
    burn = roll_damage(dice_groups=[DiceGroup(count=1, sides=4)], modifier=0)
    holder.take_damage(burn.total, fight, damage_type=DamageType.MAGIC)
    fight.note(f"{holder.name} is burning, and takes {burn.total}")


@action(IGNITE)
def ignite(adversary, target, fight: Fight):
    """Attack for 1d8 and set the target alight until they put themselves out.

    SRD: "Make an attack against a target within Very Close range. On a success,
    the target takes 1d8 magic damage and is Ignited until they're extinguished
    with a successful Finesse Roll (14). While Ignited, the target takes 1d4
    magic damage when they make an action roll."

    The fire is the point of it: 1d8 averages 4.5 against the Red Ooze's printed
    1d8+3 at 7.5, so as a hit this is strictly the worse option and what it buys
    is a burn that keeps costing until somebody rolls it off.

    **Ignited carries its own ender**, which matters beyond the escape roll: a
    condition that can end on its own terms survives its source leaving the
    fight, so killing the Ooze does not put the fire out. That is the right
    answer here and the wrong one for a hold - see
    `FightState.release_conditions_from`.

    The Difficulty is printed (14) rather than falling back on the Ooze's own,
    which is the first time a printed escape roll has stated one.

    USAGE POLICY - ruled. Rule 3, the one place it applies: the point of the
    attack is the condition, so it is not used against a target who is already
    Ignited - there it would trade the Ooze's better standard attack for nothing.
    """
    if fight.has_condition(target, IGNITED):
        return None

    result = adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=0,
        damage_type=DamageType.MAGIC,
    )
    if result.damage_roll is None:
        return result

    fight.apply_condition(
        target,
        Condition(
            name=IGNITED,
            end=_breaks_free(("finesse",), IGNITE_ESCAPE_DIFFICULTY),
            effect=_ignited_burns,
        ),
    )
    fight.note(f"{target.name} catches fire (Ignited until a Finesse Roll puts it out)")
    return result


# --- Tiny Red Ooze -------------------------------------------------------------

BURNING = qualified(ADVERSARY, "Burning")


@on_attacked(
    BURNING,
    unmodelled=[
        "Burning: only a weapon attack reaches this, as with Armor-Shredding "
        "Shards. Content that rolls an attack of its own - a Grimoire spell, the "
        "Beastbound companion - has no weapon and so no range to read, and never "
        "triggers it",
    ],
)
def burning(adversary, attacker, weapon, damage=0, hp_marked=0, fight=None) -> None:
    """Hurting this adversary in Melee costs the attacker 1d6 direct damage.

    SRD: "When a creature within Melee range deals damage to the Ooze, they take
    1d6 direct magic damage."

    Keyed on damage being **dealt** rather than on a successful attack, so a hit
    the Ooze shrugged off entirely still burns - the number rolled is what the
    trigger names. Read off the attacker's weapon for range, the same handle
    Armor-Shredding Shards and Magical Reflection use.

    Direct, so no Armor Slot softens it. On a 2 HP stat block that is the whole
    point: killing a Tiny Red Ooze in melee costs something, and the party's
    answer to a field of them is to shoot.
    """
    if fight is None or damage <= 0:
        return
    if canonical(weapon.range) != canonical(Range.MELEE.value):
        return

    burn = roll_damage(dice_groups=[DiceGroup(count=1, sides=6)], modifier=0)
    attacker.take_damage(burn.total, fight, direct=True, damage_type=DamageType.MAGIC)
    fight.note(
        f"{attacker.name} is scorched striking {adversary.name} for {burn.total} "
        f"(Burning)"
    )


# --- The pirates ---------------------------------------------------------------

SWASHBUCKLER = qualified(ADVERSARY, "Swashbuckler")

# "2 or fewer HP", as printed.
SWASHBUCKLER_MAX_HP = 2


@on_attacked(
    SWASHBUCKLER,
    unmodelled=[
        "Swashbuckler: only a weapon attack reaches this, as with "
        "Armor-Shredding Shards - content that rolls an attack of its own has no "
        "weapon and so no range to read",
    ],
)
def swashbuckler(adversary, attacker, weapon, damage=0, hp_marked=0, fight=None) -> None:
    """A Melee hit that barely hurts this adversary costs the attacker a Stress.

    SRD: "When the Captain marks 2 or fewer HP from an attack within Melee range,
    the attacker must mark a Stress."

    **It is the pirate who marks the HP**, not the PC - that is how the SRD writes
    adversary features throughout, and reading it the other way round would turn
    a defensive quirk into a second attack. So this fires on a hit that landed
    and cost the pirate little: chip damage gets a sneer and a bruise back.

    The `1 <=` half of the range never actually bites, and it is there for
    honesty rather than for safety: adversaries have no Armor Slots, so a landed
    hit always marks at least one HP against a threshold band. A PC is the
    asymmetric case - the free slot means they routinely mark none - which is why
    content on the party side has to check for zero and this doesn't.

    Carried by all three pirate stat blocks, so it registers once and reaches
    whichever was hit. The Stress is forced, so a PC with none free marks an HP.

    Worth knowing what it does to focus fire: the party's own policy is to hit
    the most wounded adversary, and a Horde of Pirate Raiders on 4 HP with
    thresholds of 5/11 marks 1 HP off most tier 1 hits. So a melee party pays a
    Stress for very nearly every swing they take at this crew.
    """
    if fight is None or canonical(weapon.range) != canonical(Range.MELEE.value):
        return
    if not 1 <= hp_marked <= SWASHBUCKLER_MAX_HP:
        return

    attacker.mark_stress(1)
    fight.note(
        f"{attacker.name}'s blow glances off {adversary.name}, and costs them a "
        f"Stress (Swashbuckler)"
    )


REINFORCEMENTS = qualified(ADVERSARY, "Reinforcements")
REINFORCEMENTS_TOKEN = "Reinforcements"

# "A Pirate Raiders Horde", by name - a Horde is one stat block standing for a
# group, so this summons a single adversary rather than several.
REINFORCEMENTS_SUMMON = "Pirate Raiders"


@action(
    REINFORCEMENTS,
    unmodelled=[
        "Reinforcements: the Raiders appearing at Far range, which is "
        "positioning. They join the fight and are targetable immediately",
    ],
)
def reinforcements(adversary, target, fight: Fight):
    """Once a fight, mark a Stress to whistle up a Horde of Pirate Raiders.

    SRD: "Once per scene, mark a Stress to summon a Pirate Raiders Horde, which
    appears at Far range."

    A scene is one fight here, and the limit is held with a token rather than
    with the per-rest machinery: a once-per-*scene* ability is available in every
    fight whatever rest preceded it, where `use_once_per_rest` would correctly
    refuse it in a no-rest encounter. That distinction is why Spitter and Consume
    Kindling use tokens too.

    Unlike the Lieutenant's uncapped summoning this brings one adversary rather
    than three, and only ever once - but a Raiders Horde is a 4 HP stat block
    with a real attack rather than a 1 HP Minion, so it is much the bigger
    addition.

    Declines rather than raising if the Raiders aren't in the catalogue at all,
    the same way More Where That Came From does.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table. The Captain's 7 HP against five Stress
    puts it inside the line from full health, so in practice the Raiders arrive
    early - which is what a Leader with a whistle should do.
    """
    if fight.token_count(adversary, REINFORCEMENTS_TOKEN):
        return None
    if not adversary.will_spend_stress(1):
        return None

    try:
        definition = find_adversary(REINFORCEMENTS_SUMMON)
    except KeyError:
        return None

    adversary.spend_stress(1)
    fight.set_token(adversary, REINFORCEMENTS_TOKEN, 1)
    fight.summon(definition.spawn())
    fight.note(
        f"{adversary.name} calls up a {REINFORCEMENTS_SUMMON} Horde (Reinforcements)"
    )
    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


NO_QUARTER = qualified(ADVERSARY, "No Quarter")
NO_QUARTER_FEAR = 1

# "Three or more Pirates within Melee range of them", as printed.
NO_QUARTER_PIRATES = 3

# What counts as a Pirate: any stat block with the word in its name, matched
# canonically. The SRD writes the requirement as a *kind* rather than naming
# stat blocks, unlike On My Signal's "all Archer Guards" - so this is the one
# feature that matches on part of a name instead of the whole of one.
PIRATE = canonical("Pirate")

# The Captain's threats, as printed: 1d4+1 Stress on a failure.
NO_QUARTER_STRESS_DIE = 4
NO_QUARTER_STRESS_BONUS = 1


@action(NO_QUARTER)
def no_quarter(adversary, target, fight: Fight):
    """Spend a Fear: the crew closes in, and the target marks 1d4+1 Stress.

    SRD: "Spend a Fear to choose a target who has three or more Pirates within
    Melee range of them. The Captain leads the Pirates in hurling threats and
    promises of a watery grave. The target must make a Presence Reaction Roll. On
    a failure, the target marks 1d4+1 Stress. On a success, they must mark a
    Stress."

    No damage at all - the whole feature is Stress, which on a six-slot track is
    up to five at once and leaves a PC Vulnerable for the rest of the fight. The
    first Presence Reaction Roll in the catalogue, and a critical escapes it
    entirely per the standing rule.

    SIMULATION RULE - policy. "Three or more Pirates within Melee range of them"
    is positioning, so the **area rule answers it exactly as Pack Tactics does**:
    of the pirates alive, `targets_reached(MELEE, ...)` says how many are on the
    target, and the feature needs `NO_QUARTER_PIRATES` of them.

    Be clear about what that costs, because it is more than it is for Pack
    Tactics. The Melee band reaches at most 3, and only on a field of
    `MANY_ADVERSARIES` or more with the clustered roll - so **No Quarter cannot
    fire below six pirates, and fires about half the time above it**. That
    follows from the printed 3 meeting the band rather than from any threshold
    of ours; lowering it to 2 was offered and declined, so this is the ruled
    behaviour rather than an oversight.

    USAGE POLICY - ruled. Used whenever the GM can afford the Fear and the crew
    is close enough, and among the options that pass the choice is random.
    """
    if fight.fear < NO_QUARTER_FEAR:
        return None

    crew = [
        other for other in fight.living_adversaries if PIRATE in canonical(other.name)
    ]
    # The Captain counts: the question is how many pirates are on this target,
    # and it is one of them.
    if len(crew) < NO_QUARTER_PIRATES:
        return None
    if targets_reached(Range.MELEE, len(crew)) < NO_QUARTER_PIRATES:
        return None

    fight.spend_fear(NO_QUARTER_FEAR)
    fight.note(
        f"{adversary.name} promises {target.name} a watery grave (No Quarter: "
        f"GM spends a Fear)"
    )

    roll = _reaction_roll(target, "presence", adversary.difficulty, fight)
    if roll.is_critical:
        fight.note(f"{target.name} laughs it off ({roll})")
    elif roll.is_success:
        target.mark_stress(1)
        fight.note(f"{target.name} holds their nerve, and marks a Stress ({roll})")
    else:
        cost = random.randint(1, NO_QUARTER_STRESS_DIE) + NO_QUARTER_STRESS_BONUS
        target.mark_stress(cost)
        fight.note(f"{target.name} is shaken, and marks {cost} Stress ({roll})")

    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


CLEAR_THE_DECKS = qualified(ADVERSARY, "Clear the Decks")


@action(
    CLEAR_THE_DECKS,
    unmodelled=[
        "Clear the Decks: moving into Melee range and knocking the target back "
        "to Close, both of which are where combatants end up and have nothing to "
        "change here. The damage is modelled",
    ],
)
def clear_the_decks(adversary, target, fight: Fight):
    """Mark a Stress on a landed hit to deal 3d4 instead.

    SRD: "Make an attack against a target within Very Close range. On a success,
    mark a Stress to move into Melee range of the target, dealing 3d4 physical
    damage and knocking the target back to Close range."

    3d4 averages 7.5 against the Tough's printed 2d6 at 7 - so unlike most Stress
    Actions this is barely an upgrade on the damage, and what the page is really
    selling is the repositioning, which has nothing to change here. That makes it
    one of the weakest Stress Actions in the catalogue as modelled, and the
    declared gap above is most of why.

    The Stress is paid on a success, so the attack is rolled first and a miss
    costs nothing - the shape Hobbling Shot uses.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table. 5 HP against three Stress puts the
    Tough inside the line from full health.
    """
    if not adversary.will_spend_stress(1):
        return None

    result = adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=3, sides=4)],
        damage_modifier=0,
        damage_type=DamageType.PHYSICAL,
    )
    if result.damage_roll is None:
        return result

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} clears the decks, barrelling into {target.name}")
    return result


no_combat_effect(
    qualified(ADVERSARY, "Creeping Fire"),
    "The Red Ooze can only move within Very Close range, and lights any "
    "flammable object it touches on fire. Both halves are movement and terrain, "
    "and neither has any representation here - unlike Consume Kindling there is "
    "no mechanical benefit attached that could be modelled in the trigger's "
    "place. Note the first half is a *restriction* on the Ooze rather than a "
    "threat, so leaving it out if anything flatters the Ooze less than modelling "
    "it would: its printed attack is already Melee, so the cap would change "
    "nothing even if positions were tracked.",
)

no_combat_effect(
    qualified(ADVERSARY, "Maintain Distance"),
    "After making a standard attack, the Harrier can move anywhere within Far "
    "range. The whole of the effect is where the Harrier ends up, and no "
    "position is tracked for it to change. At a table it is most of what makes a "
    "Harrier a Harrier - it kites, and a melee party spends turns closing the "
    "gap again - and none of that has any representation here.",
)

no_combat_effect(
    qualified(ADVERSARY, "Shield Wall"),
    "A creature trying to move within Very Close range of the Guard must succeed "
    "on an Agility Roll, at a Difficulty that rises with the number of Bladed "
    "Guards in the line. Both halves are about movement: nothing here moves, so "
    "the roll is never called for and the line of guards never forms. At a table "
    "this can cost a PC their action outright, which is a real effect with no "
    "representation in the simulation rather than a small one.",
)

no_combat_effect(
    qualified(ADVERSARY, "Overwhelming Force"),
    "Targets who mark HP from the Bear's standard attack are knocked back to "
    "Very Close range. The whole of the effect is where a combatant ends up, and "
    "no position is tracked for it to change - so there is nothing here for it "
    "to touch. It is a real effect at a table, where being pushed out of Melee "
    "costs a turn to close again; this records that the simulation has no "
    "representation of that, not that the feature is inert in the game.",
)

no_combat_effect(
    qualified(ADVERSARY, "Climber"),
    "Traversing terrain that would slow something else down. It changes where "
    "an adversary can get to in the fiction, never what happens once a fight "
    "starts - and no positioning is modelled for it to interact with anyway.",
)

insignificant_combat_effect(
    qualified(ADVERSARY, "From Above"),
    "1d10+1 instead of the standard 1d8+1 when attacking from above, about +1 "
    "expected damage (6.5 against 5.5). Against "
    "thresholds of 8 and 14 that almost never moves a hit into a higher "
    "threshold band, so it would change the HP marked in only a small "
    "fraction of hits. Position isn't tracked either, so it could not fire "
    "reliably even if it were worth modelling.",
)

insignificant_combat_effect(
    qualified(ADVERSARY, "Unseen Strike"),
    "1d10+4 instead of the standard 1d10+2 while Hidden, +2 expected damage "
    "(9.5 against 7.5). Larger than From Above's bump but "
    "the same reasoning applies: damage reaches HP through threshold bands, so "
    "most of it is absorbed within a band. Hidden isn't a tracked condition "
    "either.",
)
