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
from content.aoe import Range, targets_in_area, targets_reached
from content.conditions import (
    BEFORE_AN_ACTION_ROLL,
    POISONED,
    RESTRAINED,
    VULNERABLE,
    Condition,
    until_they_clear_hp,
    when_they_act,
)
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

# SIMULATION RULE - policy. How much worse than the standard attack a feature's
# damage has to be before "it's really for the condition" is the honest reading
# of it. An attack feature past this margin whose point is applying a condition
# is held back against a target that already has that condition; below it, the
# feature is just another attack and the random-among-viable default applies.
#
# A knob, and a thinly-evidenced one: it is set from the only two features that
# currently qualify - Venomous Stinger (1d4+4 at 6.5 against the Scorpion's
# 1d12+2 at 8.5) and Grab and Drag (1d6+2 at 5.5 against 1d8+3 at 7.5) - which
# both sit at exactly 2.0, so the margin separates nothing yet. Twelve of the
# SRD's ~129 adversaries are ported; this wants revisiting, and a validation
# check over the whole catalogue, once there are enough features to test it
# against. See SIMULATION-RULES.md.
CONDITION_ATTACK_EV_MARGIN = 2

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


@severity_increase(
    WEAK_STRUCTURE,
    unmodelled=[
        "Weak Structure: the physical-damage restriction - damage types are "
        "recorded on the catalogues but nothing reads them yet, so this worsens "
        "magic damage too and makes the Construct slightly more fragile here "
        "than on the page",
    ],
)
def weak_structure(adversary, amount: int, hp_to_mark: int, fight=None) -> int:
    """When this adversary marks HP, they mark an additional one.

    SRD: "When the Construct marks HP from physical damage, they must mark an
    additional HP."

    Keyed on HP actually being marked, not on damage being dealt - a hit that
    softened away to nothing didn't mark anything, so there is nothing to add to.
    Running after `soften_damage` is what makes that check meaningful; see
    `severity_increase`.

    On a 9 HP track this is worth a lot: it turns a Major hit into 3 HP and a
    Severe into 4, so the Construct dies to roughly two thirds of the hits its
    HP suggests. That is the trade the stat block is making for its 1d20 attack.
    """
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


def _reaction_roll(pc, trait: str, difficulty: int, fight=None):
    """One PC's Reaction Roll against `difficulty`, using `trait`.

    Not a wrapper around the roller - `roll_duality` is called here, at the site
    that needs it, and this only works out the modifier and the state to roll in.
    A PC whose sheet doesn't carry the trait rolls at +0 rather than failing to
    roll, since every sheet carries all six and a missing one is a malformed
    sheet rather than a rule.

    A condition that hobbles this trait applies here as much as it does to an
    attack - "disadvantage on Agility Rolls" covers the Agility Reaction Roll a
    PC makes to keep their feet - which is why `fight` is in the signature. It
    stays optional so a reaction roll can still be made without one.
    """
    disadvantaged = fight is not None and fight.disadvantaged_on(pc, trait)
    return roll_duality(
        modifier=pc.traits.get(trait, 0),
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
        trait = max(traits, key=lambda name: holder.traits.get(name, 0))
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

    Vulnerable ends "when they next act", which the fight loop announces after
    the PC's spotlight resolves - so a PC caught by this is still Vulnerable for
    any attack that lands before their turn comes round.
    """
    caught = targets_in_area(Range.VERY_CLOSE, fight.conscious_party)
    if not caught:
        return None
    if not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} bursts out of the ground (Earth Eruption)")

    for pc in caught:
        roll = _reaction_roll(pc, "agility", adversary.difficulty, fight)
        if roll.is_success:
            fight.note(f"{pc.name} keeps their feet ({roll})")
            continue
        fight.apply_condition(pc, Condition(name=VULNERABLE, end=when_they_act))
        fight.note(f"{pc.name} is knocked over, and is Vulnerable until they act")

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
        caught, fight=fight, damage_dice=[DiceGroup(count=2, sides=6)], damage_modifier=0
    )
    for pc in struck:
        if pc.armor_unmarked > 0:
            pc.mark_armor_slot(1)
            fight.note(f"{pc.name}'s armor is eaten away (Spit Acid: an Armor Slot)")
            continue
        pc.mark_hp_and_check_death(1)
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
        caught.take_damage(damage.total, fight)
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
        pc.take_damage(damage.total, fight, direct=True)
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
        caught, fight=fight, damage_dice=[DiceGroup(count=1, sides=8)], damage_modifier=0
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
    the options that pass the choice is random.

    This is the one batch 1 feature the condition-attack rule reaches and then
    can't act on. That rule holds back an attack that is worse than the standard
    one by 2 or more expected damage and exists mainly to apply a condition,
    unless the target is free of that condition - and Grab and Drag qualifies on
    the numbers exactly (1d6+2 at 5.5 against the Defender's 1d8+3 at 7.5). But
    the condition it applies is Restrained, which has no representation here, so
    "does the target already have it?" has no answer to read and the rule
    collapses to no condition at all. That is our gap rather than a judgement
    about the feature - declared above, where it is registered.
    """
    if fight.fear < GRAB_AND_DRAG_FEAR:
        return None

    result = adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=1, sides=6)],
        damage_modifier=2,
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

    USAGE POLICY - ruled, and this is the first feature the condition-attack rule
    actually acts on. 1d4+4 averages 6.5 against the Scorpion's printed 1d12+2 at
    8.5 - exactly the `CONDITION_ATTACK_EV_MARGIN` of 2 - and what the trade buys
    is the Poison. So it is held back against a target already Poisoned, where it
    would be strictly worse than simply stinging them again.
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
def armor_shredding_shards(adversary, attacker, weapon, damage=0, fight=None) -> None:
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
        pc.take_damage(damage.total, fight)
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
    target.take_damage(damage.total, fight, direct=deals_direct_damage(shooter, fight))
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

    Damage types are recorded on the catalogues but not yet read by anything, so
    the magic damage resolves like any other; that gap is already declared on the
    Construct's Weak Structure, and it is what `Arcane Form` is waiting on.

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
        pc.take_damage(damage.total, fight, direct=True)
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
def magical_reflection(adversary, attacker, weapon, damage=0, fight=None) -> None:
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

    The trigger is a landed attack, so a miss reflects nothing.
    """
    if fight is None or damage <= 0:
        return
    if not any(canonical(weapon.range) == canonical(band.value) for band in WITHIN_CLOSE):
        return

    reflected = damage // 2
    if reflected <= 0:
        return

    attacker.take_damage(reflected, fight)
    fight.note(
        f"{attacker.name}'s blow rebounds off {adversary.name} for {reflected} "
        f"(Magical Reflection)"
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
