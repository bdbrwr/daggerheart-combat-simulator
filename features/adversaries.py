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

from combat.results import AttackResult
from content.aoe import Range, targets_in_area
from content.conditions import VULNERABLE, Condition, when_they_act
from content.names import ADVERSARY, qualified
from content.registry import (
    Fight,
    action,
    activation_limit,
    attack_area,
    damage_bonus,
    direct_damage,
    feature_parameter,
    insignificant_combat_effect,
    no_combat_effect,
    on_damaged,
    on_hit,
    severity_increase,
    spotlight_cost,
)
from dice.common import AdvantageState
from dice.damage import DiceGroup, roll_damage
from dice.duality import roll_duality

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
        "Weak Structure: the physical-damage restriction - damage types aren't "
        "tracked anywhere, so this worsens magic damage too, which makes the "
        "Construct slightly more fragile here than on the page",
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


def _reaction_roll(pc, trait: str, difficulty: int):
    """One PC's Reaction Roll against `difficulty`, using `trait`.

    Not a wrapper around the roller - `roll_duality` is called here, at the site
    that needs it, and this only works out the modifier. A PC whose sheet doesn't
    carry the trait rolls at +0 rather than failing to roll, since every sheet
    carries all six and a missing one is a malformed sheet rather than a rule.
    """
    return roll_duality(
        modifier=pc.traits.get(trait, 0),
        difficulty=difficulty,
    )


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

    USAGE POLICY - awaiting a ruling. Used whenever the Stress can be paid and
    it reaches anybody. That is the placeholder default rather than a judgement:
    the feature names no other condition, and a threshold like "only when it
    catches two" would be a knob nobody has set.

    Vulnerable ends "when they next act", which the fight loop announces after
    the PC's spotlight resolves - so a PC caught by this is still Vulnerable for
    any attack that lands before their turn comes round.
    """
    caught = targets_in_area(Range.VERY_CLOSE, fight.conscious_party)
    if not caught:
        return None
    if not adversary.can_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} bursts out of the ground (Earth Eruption)")

    for pc in caught:
        roll = _reaction_roll(pc, "agility", adversary.difficulty)
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

    USAGE POLICY - awaiting a ruling. Free to use, so it's taken whenever it
    reaches anybody. That is the placeholder default; the feature costs nothing
    and names no condition.
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
        "Bite: the Restrain, and the Strength Roll to break out of it. Being "
        "Restrained only stops a combatant moving, which has no representation "
        "here - real at a table, absent in the simulation",
    ],
)
def bite(adversary, target, fight: Fight):
    """Mark a Stress to bite one target for 3d4+10.

    SRD: "Mark a Stress to make an attack against a target within Melee range. On
    a success, deal 3d4+10 physical damage and the target is Restrained until
    they break free with a successful Strength Roll."

    3d4+10 averages 17.5 against the Bear's standard 1d8+3 at 7.5 - it is the
    Bear's whole threat, and worth a Stress every time it can pay. So the only
    reason to decline is not being able to.

    Only two Stress on the stat block, so this fires twice a fight and then the
    Bear is a 1d8+3 attacker for the rest of it. That shape is the point of the
    stat block and it's why the Stress is claimed rather than assumed.
    """
    if not adversary.can_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} lunges with a bite")
    return adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=3, sides=4)],
        damage_modifier=10,
    )


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

    The Ogre's printed range is Very Close, so that's the band swept. Worth
    knowing when reading the Ogre's numbers: the area rule puts Very Close at a
    third of the field, so against a party of four this reaches one PC and the
    sweep buys nothing that turn. That's the area rule doing its job - it exists
    so "all targets within range" can't mean "everyone, always" - but it does
    mean the Ogre's Fear cost bites hardest in exactly the small fights where the
    sweep is worth least. The band fractions are knobs, in SIMULATION-RULES.md.
    """
    return Range.VERY_CLOSE


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

    USAGE POLICY - awaiting a ruling. Used whenever the Stress can be paid, which
    is the placeholder default; the card names no other condition.
    """
    caught = targets_in_area(Range.FAR, fight.conscious_party)
    if not caught or not adversary.can_spend_stress(1):
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
        "positions exist to draw one. The Construct's own Melee band stands in",
    ],
)
def trample(adversary, target, fight: Fight):
    """Mark a Stress to attack everyone in the way for 1d8.

    SRD: "Mark a Stress to make an attack against all targets in the Construct's
    path when they move. Targets the Construct succeeds against take 1d8 physical
    damage."

    USAGE POLICY - awaiting a ruling. Used whenever the Stress can be paid and
    it reaches anybody. Melee reaches two under the area rule, so in practice
    this is "hit two people for 1d8 instead of one for 1d20" - which may well
    want a condition on it, but that is a call to make rather than assume.
    """
    caught = targets_in_area(Range.MELEE, fight.conscious_party)
    if not caught or not adversary.can_spend_stress(1):
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

    Always taken when it can be paid. +10 on a 1d20 attack is enormous: it moves
    a typical hit from around 10 to around 20, which for a tier 1 PC is the
    difference between Major and Severe, and the free extra spotlight is on top.
    Four Stress means four of them, and then the Construct is done.

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

    USAGE POLICY - awaiting a ruling. Free, so it's used whenever it reaches
    anybody. That is the placeholder default; the feature costs nothing.
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
        "Grab and Drag: the Restrain, which only stops a combatant moving and so "
        "has no representation here",
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

    USAGE POLICY - awaiting a ruling. Used whenever the GM can afford the Fear,
    which is the placeholder default rather than a judgement: the feature's own
    text puts no other condition on it. Its damage is lower than the Defender's
    standard attack, but that is a fact about damage only and not a reason to
    hold it back - what makes it worth using at a table is the Restrain, and the
    fact that this simulator doesn't model Restrained is a gap of ours rather
    than evidence about the game.
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
    fight.note(f"{adversary.name} drags {target.name} in (GM spends a Fear)")
    return result

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
