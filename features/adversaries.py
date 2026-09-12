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
from content.aoe import (
    Range,
    band_named,
    chance_within,
    targets_in_area,
    targets_reached,
)
from content.conditions import (
    BEFORE_AN_ACTION_ROLL,
    COVERED_IN_SPIDERS,
    ENCHANTED,
    ENVENOMATED,
    EXHAUSTED,
    HIDDEN,
    PINNED,
    POISONED,
    RESTRAINED,
    SHAKY,
    SLOWED,
    TAUNTED,
    TRAPPED,
    VULNERABLE,
    WEAPON_STUCK,
    WHEN_THEY_ACT,
    Condition,
    until_they_clear_hp,
    until_they_take_damage,
    when_they_act,
)
from content.damage_types import BOTH, RESISTED, DamageType, includes
from content.names import ADVERSARY, canonical, qualified
from content.registry import (
    Fight,
    action,
    activation_limit,
    adversary_on_damaged,
    adversary_on_spotlight,
    ally_damage_bonus,
    apply_on_hit,
    attack_advantage,
    attack_advantage_against,
    attack_area,
    attack_failed,
    attack_missed,
    attack_roll_bonus,
    before_attacked,
    condition_refusal,
    convert_party_roll,
    critical_refusal,
    damage_bonus,
    damage_multiplier,
    damage_resistance,
    deals_direct_damage,
    difficulty_bonus,
    direct_damage,
    feature_parameter,
    force_adversary_reroll,
    insignificant_combat_effect,
    live_difficulty_bonus,
    no_combat_effect,
    on_ally_defeated,
    on_attacked,
    on_damaged,
    on_hit,
    on_party_attack_roll,
    on_party_spotlight,
    on_spotlight,
    on_stress_marked,
    out_of_combat_ability,
    party_attack_disadvantage,
    reaction_roll_bonus,
    party_target_override,
    severity_increase,
    severity_response,
    skip_spotlight,
    spotlight_cost,
    spotlight_while_defeated,
    standard_damage,
    standard_damage_type,
    stress_refusal,
    total_attack_roll_bonus,
    total_reaction_roll_bonus,
)
from dice.common import AdvantageState, combined
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
    # A minus is normalised into a signed term before splitting, because the SRD
    # writes one: the Will-o'-the-Wisps are `Horde (1d4-1)`, and without this the
    # whole string would reach `parse_dice` as a single unreadable die.
    for term in str(written).replace("-", "+-").split("+"):
        term = term.strip()
        if not term:
            continue
        if term.lstrip("-").isdigit():
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
    if not includes(damage_type, DamageType.PHYSICAL):
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
        # An adversary has no traits to add, but content can still move the roll -
        # the Rabble Mawb's *Come Back Worse* sharpens **all** its rolls, not only
        # its attacks. Asked here because this is the one place a d20 Reaction Roll
        # is thrown; see `reaction_roll_bonus`.
        return roll_d20(
            modifier=total_reaction_roll_bonus(combatant, fight), evasion=difficulty
        )

    disadvantaged = fight is not None and fight.disadvantaged_on(combatant, trait)
    return roll_duality(
        modifier=traits.get(trait, 0),
        difficulty=difficulty,
        advantage_state=(
            AdvantageState.DISADVANTAGE if disadvantaged else AdvantageState.NONE
        ),
        trait=trait,
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
def acid_bath(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False, damage_type=None
) -> None:
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
def rampaging_fury(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False, damage_type=None
) -> None:
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
def death_quake(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False, damage_type=None
) -> None:
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
def grab_and_drag_releases(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False, damage_type=None
) -> None:
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

# The word a stat block adds to the parameter when its printed text pays the GM a
# Fear - `Pack Tactics (1d6+5, Fear)`. See the docstring for why the parameter
# carries two things rather than one.
PACK_TACTICS_FEAR = "Fear"


@standard_damage(PACK_TACTICS)
def pack_tactics(adversary, target, roll=None, fight=None):
    """A successful standard attack deals X instead, and may hand the GM a Fear.

    SRD, Dire Wolf: "If the Wolf makes a successful standard attack and another
    Dire Wolf is within Melee range of the target, deal 1d6+5 physical damage
    instead of their standard damage **and you gain a Fear**."

    SRD, Sylvan Soldier: "If the Soldier makes a standard attack and another
    Sylvan Soldier is within Melee range of the target, deal **1d8+5** physical
    damage instead of their standard damage." No Fear.

    **Parameterised on both halves that differ**, which is why the argument is
    two terms rather than one: `Pack Tactics (1d6+5, Fear)` on the Dire Wolf and
    `Pack Tactics (1d8+5)` on the Sylvan Soldier. The alternative - dropping the
    Fear so a single number would do - was offered and declined, on the grounds
    that it would quietly change a stat block that is already ported rather than
    changing how one is authored. So the printed difference lives in the JSON,
    where a reader can check it against the page, exactly as `Horde (X)` and
    `Split (X)` already do.

    A stat block writing `Pack Tactics` bare gets nothing rather than a guess,
    the way Relentless and Flying do - and the same is true of the Fear, which
    has to be asked for by name.

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

    Worth knowing for tuning: the Wolf's 1d6+5 averages 8.5 against its printed
    1d6+2 at 5.5, and the Fear rides on top of every one that lands. Like the
    Bear's Momentum, a pack of Wolves partly pays for its own extra activations -
    and unlike Momentum it needs no Stress and has no cap, so how often the band
    lets it through is the whole of what holds it back. A pack of Sylvan Soldiers
    buys the damage and none of that.
    """
    if fight is None:
        return None

    written = feature_parameter(adversary, PACK_TACTICS)
    if written is None:
        return None
    terms = [term.strip() for term in str(written).split(",") if term.strip()]
    if not terms:
        return None
    pays_fear = any(canonical(term) == canonical(PACK_TACTICS_FEAR) for term in terms[1:])
    dice, modifier = _damage_spec(terms[0])

    pack = [
        other
        for other in fight.living_adversaries
        if canonical(other.name) == canonical(adversary.name)
    ]
    # The attacker counts: the question is how many of the pack are on this
    # target, and it is one of them.
    if len(pack) < PACK_TACTICS_WOLVES:
        return None
    if targets_reached(Range.MELEE, len(pack)) < PACK_TACTICS_WOLVES:
        return None

    if pays_fear:
        fight.gain_fear(1)
        fight.note(
            f"{adversary.name} closes in as a pack (Pack Tactics: GM gains a Fear)"
        )
    else:
        fight.note(f"{adversary.name} closes in as a pack (Pack Tactics)")
    return dice, modifier


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
def minion(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False, damage_type=None
) -> None:
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
def hold_them_down_releases(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False, damage_type=None
) -> None:
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
        "Cloaked: the SRD also uses Hidden to stop a combatant being targeted at "
        "all. What is modelled is the Disadvantage every roll against a hidden "
        "combatant takes, plus this feature's own Advantage - targeting itself "
        "still ignores it",
    ],
)
def cloaked(adversary, target, fight: Fight):
    """Vanish: rolls against this adversary are hobbled, and its next attack isn't.

    SRD: "Become Hidden until after the Shadow's next attack. Attacks made while
    Hidden from this feature have advantage."

    **Both halves are now modelled.** The Advantage was always here; the Hidden
    itself used to be a declared gap, because nothing tracked the condition. It
    does now - every roll against a hidden combatant has Disadvantage - so the
    condition is applied for real and the gap is gone. That makes the Shadow
    meaningfully harder to hit for the turn it spends cloaking, which is a change
    to a stat block that was already ported: it follows from the ruling on
    Hidden rather than from any decision about the Shadow.

    **No `found_by`**, unlike the Sylvan Soldier's Blend In. The page offers no
    roll to find a cloaked Shadow, so the party cannot spend an action hunting
    for one - it simply ends when the Shadow strikes.

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
    fight.apply_condition(adversary, Condition(name=HIDDEN, source=adversary))
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

    The Hidden condition ends in the same breath, since the page ends both with
    the same clause. Cleared here rather than by anything watching the attack,
    for the same reason the token is.
    """
    if fight is None or not fight.token_count(adversary, CLOAKED_TOKEN):
        return None

    fight.set_token(adversary, CLOAKED_TOKEN, 0)
    fight.clear_condition(adversary, HIDDEN)
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
    if not includes(damage_type, DamageType.MAGIC):
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
def envelop_releases(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False, damage_type=None
) -> None:
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
def split(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False, damage_type=None
) -> None:
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


# --- Skeleton Archer ---------------------------------------------------------

OPPORTUNIST = qualified(ADVERSARY, "Opportunist")

# "Two or more adversaries within Very Close range of a creature", as printed,
# and "double" for the damage.
OPPORTUNIST_ADVERSARIES = 2
OPPORTUNIST_MULTIPLIER = 2


@damage_multiplier(OPPORTUNIST)
def opportunist(adversary, target, attacker, fight=None) -> int | None:
    """Double this adversary's damage to a creature two or more of its side crowd.

    SRD: "When two or more adversaries are within Very Close range of a creature,
    all damage the Archer deals to that creature is doubled."

    Registered on the same hook as the Kneebreaker's `I've Got 'Em`, and the two
    are near mirror images: that one belongs to a **third party** and doubles
    what *other* adversaries deal, while this one belongs to the attacker and
    doubles only its own. So the check here is `attacker is adversary`, exactly
    where I've Got 'Em checks `attacker is not adversary`.

    **All damage the Archer deals**, not only its standard attack - so Deadly
    Shot's 3d4+8 is doubled too, which is the largest single number a tier 1
    stat block can produce. Doubling lands before the target's thresholds, the
    same place I've Got 'Em's does.

    SIMULATION RULE - policy. "Two or more adversaries within Very Close range of
    a creature" is positioning, so the **area rule answers it** the way it
    answers Pack Tactics and No Quarter: of the adversaries alive,
    `targets_reached(VERY_CLOSE, ...)` says how many are on this target.

    RULED. **The Archer counts itself**, the same reading No Quarter takes when
    it counts the Captain among its three Pirates - the page names a number of
    adversaries rather than "other adversaries", where Pack Tactics is explicit
    about "*another* Dire Wolf".

    Worth knowing before reading numbers, because the consequence is large. Very
    Close reaches `n // 3` capped at 2, so **this cannot fire below six
    adversaries** - the No Quarter situation again, and arriving the same way,
    from a printed 2 meeting the band rather than from any threshold of ours. A
    Skeleton Archer in a small skirmish is a plain 1d8+1 shooter; one standing
    behind a crowd of Dredges is something else entirely, which is what the
    Dredge's own feeble stat block is for.
    """
    if fight is None or attacker is not adversary:
        return None

    crowd = fight.living_adversaries
    if len(crowd) < OPPORTUNIST_ADVERSARIES:
        return None
    if targets_reached(Range.VERY_CLOSE, len(crowd)) < OPPORTUNIST_ADVERSARIES:
        return None

    # Worth a line of its own for the same reason I've Got 'Em's is: the loop
    # reports the damage *rolled*, and what lands is twice that.
    fight.note(
        f"{target.name} is surrounded, and takes double damage "
        f"(Opportunist: {adversary.name})"
    )
    return OPPORTUNIST_MULTIPLIER


DEADLY_SHOT = qualified(ADVERSARY, "Deadly Shot")


@action(DEADLY_SHOT)
def deadly_shot(adversary, target, fight: Fight):
    """Mark a Stress to shoot a Vulnerable target at Far range for 3d4+8.

    SRD: "Make an attack against a Vulnerable target within Far range. On a
    success, mark a Stress to deal 3d4+8 physical damage."

    3d4+8 averages 15.5 against the Archer's printed 1d8+1 at 5.5, so this is
    most of what a Skeleton Archer is worth - and it is gated on the target
    already being Vulnerable, which is a **printed requirement** rather than a
    policy of ours. Coup de Grace is the same shape and the same reading.

    Nothing in the Archer's own kit makes anybody Vulnerable, so like Coup de
    Grace this is the payoff card of a kit rather than a feature that stands by
    itself: a PC who has marked their last Stress qualifies, and so does one the
    Minor Chaos Elemental's Sickening Flux or a Kneebreaker's hold has caught.

    Rolled through the shared advantage rule rather than flat, since a Vulnerable
    target hands every roll against them Advantage - which, this feature being
    what it is, is always true when it fires.

    The Stress is paid on a success, so the attack is rolled first and a miss
    costs nothing - the shape Hobbling Shot uses.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table. 3 HP against two Stress puts the Archer
    inside the line from full health, so the rule never actually holds this back
    and the printed Vulnerable requirement is the whole of the gate.
    """
    from combat.policy import adversary_attack_advantage

    if not fight.is_vulnerable(target):
        return None
    if not adversary.will_spend_stress(1):
        return None

    result = adversary.attack(
        target,
        adversary_attack_advantage(adversary, target, fight),
        fight,
        damage_dice=[DiceGroup(count=3, sides=4)],
        damage_modifier=8,
        damage_type=DamageType.PHYSICAL,
    )
    if result.damage_roll is None:
        return result

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} looses a deadly shot at {target.name}")
    return result


# --- Skeleton Knight ---------------------------------------------------------

TERRIFYING = qualified(ADVERSARY, "Terrifying")


@on_hit(TERRIFYING)
def terrifying(adversary, target, result, fight: Fight) -> None:
    """A landed attack costs every PC in Close range a Hope, and hands the GM a Fear.

    SRD: "When the Knight makes a successful attack, all PCs within Close range
    lose a Hope and you gain a Fear."

    Dispatch only reaches an on-hit rider once the attack has landed, so the
    success is already established - and it reaches *every* attack the Knight
    makes, its standard swing and Cut to the Bone alike, which is what "a
    successful attack" says.

    **One Fear, not one per PC.** The corroboration is two entries further down
    the same page: the Patchwork Zombie Hulk's *Tormented Screams* has to write
    "you gain a Fear **for each**" to get the other reading, which is only worth
    printing if a bare "you gain a Fear" means one.

    "All PCs within Close range" is an area rather than one named person, so
    `targets_in_area` answers it - the shape Ground Slam and Death Quake use -
    where the Minor Demon's *All Must Fall* asks `chance_within` because its
    trigger is one particular PC's roll.

    The Hope is taken through `spend_hope`, which clamps, so a PC with none
    simply loses nothing. It is counted as *spent* in the report for the reason
    All Must Fall gives: a PC losing a Hope to fear has not strictly spent it,
    but the alternative is a fifth Hope figure nobody asked for and four that
    stop reconciling.

    This is the second free Hope drain in the catalogue and much the more
    reliable one - All Must Fall needs the party to roll a failure with Fear,
    where this needs only the Knight to connect - and it pays the GM a Fear on
    top, which is Momentum's effect without Momentum's name.

    **This is the bare, default variant.** SRD 2.0 prints a second feature under
    this same name on the Darkweave Queen, and the two are told apart by the
    parameter - see `terrifying_on_a_miss`. A stat block writing `Terrifying`
    gets this one; anything writing a parameter is asking for another, so this
    declines rather than running on top of it.
    """
    if feature_parameter(adversary, TERRIFYING) is not None:
        return

    caught = targets_in_area(Range.CLOSE, fight.conscious_party)
    if not caught:
        return

    for pc in caught:
        if not pc.can_spend_hope(1):
            continue
        pc.spend_hope(1)
        fight.note(f"{pc.name} loses a Hope to the Knight's advance (Terrifying)")

    gained = fight.gain_fear(1)
    if gained:
        fight.note(f"{adversary.name} is terrifying (GM gains a Fear)")


CUT_TO_THE_BONE = qualified(ADVERSARY, "Cut to the Bone")


@action(CUT_TO_THE_BONE)
def cut_to_the_bone(adversary, target, fight: Fight):
    """Mark a Stress to sweep everyone Very Close for 1d8+2 and a Stress each.

    SRD: "Mark a Stress to make an attack against all targets within Very Close
    range. Targets the Knight succeeds against take 1d8+2 physical damage and
    must mark a Stress."

    1d8+2 averages 6.5 against the Knight's printed 1d10+2 at 7.5, so as damage
    this is a small step down and what it buys is reach plus the forced Stress -
    which is worth more than it looks, since a PC with every Stress marked is
    Vulnerable for the rest of the fight and can't pay for their own cards. The
    Stress is forced, so a PC with no free slot marks an HP instead.

    Worth knowing what the area rule costs it: Very Close is held to two, so
    against a party of four this reaches one PC and the sweep buys nothing - the
    same tax Spinning Serpent pays, and the reason a lone Knight is really just a
    greatsword.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table, with deliberately no threshold on how
    many PCs it reaches. 5 HP against two Stress puts the Knight inside the line
    from full health, so both its Stress go early and then it is a plain
    attacker.
    """
    caught = targets_in_area(Range.VERY_CLOSE, fight.conscious_party)
    if not caught or not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} sweeps the rusty greatsword (Cut to the Bone)")
    result, struck = adversary.area_attack(
        caught,
        fight=fight,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=2,
        damage_type=DamageType.PHYSICAL,
    )
    for pc in struck:
        pc.mark_stress(1)
        fight.note(f"{pc.name} is cut to the bone, and marks a Stress")
    return result


DIG_TWO_GRAVES = qualified(ADVERSARY, "Dig Two Graves")

# "Loses 1d4 Hope", as printed. Rolled with `random` directly, the way the
# Spitter Die and No Quarter's Stress are - this is neither an attack, a damage
# roll nor a duality roll, so nothing in dice/ has a shape for it.
DIG_TWO_GRAVES_HOPE_DIE = 4


@on_damaged(
    DIG_TWO_GRAVES,
    unmodelled=[
        "Dig Two Graves: a PC the dying blow knocks unconscious still completes "
        "the attack they had already started - the swing resolves inside their "
        "own, and a spotlight under way can't be unwound. The same gap Fall Back "
        "declares",
    ],
)
def dig_two_graves(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False, damage_type=None
) -> None:
    """When this adversary is defeated, it swings once more for 1d4+8 and 1d4 Hope.

    SRD: "When the Knight is defeated, they make an attack against a target
    within Very Close range (prioritizing the creature who killed them). On a
    success, the target takes 1d4+8 physical damage and loses 1d4 Hope."

    Fires from `on_damaged`, which runs after the marking is settled - so
    `is_defeated` is already true here and the Knight is swinging as it dies,
    the same window the Construct's Death Quake explodes in. Firing from there
    rather than from `on_attacked` is what makes it reach **however the Knight
    died**: a spell that rolled its own attack, an area effect, or another
    adversary's splash all get the parting swing, where the attack-side hook only
    sees a PC's weapon.

    RULED. **"Prioritizing the creature who killed them" is modelled**, not
    declared as a gap - and it needed one thing moving to be true. The standing
    targeting rule already answers "whoever hit this adversary last", but the
    memory behind it was written *after* an attack resolved, so at this moment it
    still named whoever hit the Knight the time before. `combat/policy.py` now
    records it before the attack instead, which nothing outside an attack can
    tell apart, and this feature simply asks the standing rule.

    1d4+8 averages 10.5 against the Knight's printed 1d10+2 at 7.5, so killing
    this stat block costs something - and the Hope hurts more than the damage
    does, since 1d4 off a six-Hope track is most of what a PC has banked for
    their class feature. Note the Knight's own *Terrifying* fires off this attack
    too, through the generic on-hit dispatch, so the parting swing also drains
    the whole front line and pays the GM a Fear.

    USAGE POLICY - ruled. A Reaction: it fires whenever its trigger happens, and
    it costs nothing at all, so there is nothing to gate.
    """
    if fight is None or not adversary.is_defeated:
        return

    # The standing targeting rule, which now names the killer - see above.
    # Imported here rather than at module level: combat/ reaches content/, which
    # discovers this package, so the two only meet at call time.
    from combat.policy import choose_adversary_target

    target = choose_adversary_target(adversary, fight)
    if target is None:
        return

    fight.note(f"{adversary.name} swings as it falls (Dig Two Graves)")
    result = adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=1, sides=4)],
        damage_modifier=8,
        damage_type=DamageType.PHYSICAL,
    )
    if result.damage_roll is None:
        fight.note(f"{adversary.name} misses {target.name} ({result.attack_roll})")
        return

    # `spend_hope` clamps, so a PC with less than the roll simply loses what they
    # had. Counted as spent for the reason Terrifying and All Must Fall are.
    lost = random.randint(1, DIG_TWO_GRAVES_HOPE_DIE)
    target.spend_hope(lost)
    fight.note(f"{target.name} loses {lost} Hope to the Knight's dying blow")

    # A Reaction's attack is made outside the spotlight loop, so the loop isn't
    # there to hand out the riders a landed attack triggers - the Harrier's Fall
    # Back has the same problem and the same answer. Asked generically; it is
    # what carries the Knight's own Terrifying onto this swing.
    apply_on_hit(adversary, target, result, fight)


# --- Skeleton Warrior --------------------------------------------------------

ONLY_BONES = qualified(ADVERSARY, "Only Bones")


@damage_resistance(ONLY_BONES)
def only_bones(adversary, damage_type, fight=None) -> float | None:
    """This adversary is resistant to physical damage.

    SRD: "The Warrior is resistant to physical damage."

    The mirror of the Minor Chaos Elemental's `Arcane Form`, registered on the
    same hook and pointed at the other type. Arcane Form is answered by drawing
    steel; this one is answered by magic damage.

    Halving lands **before** the Warrior's thresholds of 4 and 8, which is what
    the effect is made of: 9 physical marks 2 HP where 9 magic marks 3, and it
    takes 16 physical to reach Severe.

    One bound worth having, because it is arithmetic rather than a guess: the
    thresholds are one HP apart per band, so **halving can save at most 1 HP on
    any single hit**, against a 3 HP track. That is the ceiling on what this
    feature can do per swing, whatever the damage rolled.

    **How much that is worth is a question for a run, not for this docstring.**
    The arithmetic above is one hit; what it does to a fight depends on what the
    party is carrying and how often thresholds are near a boundary, which is
    exactly the sort of thing this simulator exists to measure rather than to be
    told. Early observation from the user is that it matters *less* than the
    per-hit arithmetic suggests.

    Declines on anything that isn't physical, which includes untyped damage - a
    resistance applies to a type that was stated.
    """
    if not includes(damage_type, DamageType.PHYSICAL):
        return None
    return RESISTED


WONT_STAY_DEAD = qualified(ADVERSARY, "Won't Stay Dead")

# The die and the face that brings it back, as printed.
WONT_STAY_DEAD_DIE = 6
WONT_STAY_DEAD_REFORMS_AT = 6


@spotlight_while_defeated(WONT_STAY_DEAD)
def wont_stay_dead_waits(adversary, fight=None) -> bool:
    """A defeated Warrior can still be spotlighted, while it has company.

    The permission half of the feature, and the reason `spotlight_while_defeated`
    exists at all: the GM has to be able to spend a spotlight on a pile of bones
    before the d6 below can be rolled.

    The printed condition - "if there are other adversaries on the battlefield" -
    is checked here as well as at the roll, so the GM never pays for a spotlight
    that cannot possibly do anything. The Warrior itself is defeated and so is
    not among `living_adversaries`, which means a *lone* Warrior asks for
    nothing: the fight is already over by the time the loop would ask.
    """
    return fight is not None and bool(fight.living_adversaries)


@on_spotlight(WONT_STAY_DEAD)
def wont_stay_dead(adversary, fight=None) -> None:
    """Roll a d6 on being spotlighted while defeated; on a 6, re-form.

    SRD: "When the Warrior is defeated, you can spotlight them and roll a d6. On
    a result of 6, if there are other adversaries on the battlefield, the Warrior
    re-forms with no marked HP."

    RULED. **"You can spotlight them" is an activation, charged as usual.** The
    roll is not free and does not happen at the moment of death: it waits for a
    GM turn with a spotlight to spare, costs the usual Fear for every activation
    past the turn's first, and counts against the party size + 1 cap like
    everything else. So a Warrior cut down on a PC's spotlight lies there until
    the GM comes round, and a GM with an empty Fear pool and a busy field may
    never get the roll at all. What was *not* ruled is the stricter reading: a
    Warrior that comes back has **not** spent its spotlight doing so, and acts on
    the same activation.

    **No marked HP, and the Stress stays.** The page says HP and only HP, so a
    Warrior that has already spent its Stress comes back with it still spent.

    Uncapped, because the page prints no limit: each defeat is a fresh 1-in-6.
    That cannot stall a fight - the roll needs another adversary standing, so the
    last thing on the field never comes back and `adversaries_are_cleared` still
    ends things.

    Rolled with `random` directly, the way the Spitter Die is: this is neither an
    attack, a damage roll nor a duality roll, so nothing in dice/ has a shape
    for it.
    """
    if fight is None or not adversary.is_defeated:
        return
    if not fight.living_adversaries:
        return

    rolled = random.randint(1, WONT_STAY_DEAD_DIE)
    if rolled < WONT_STAY_DEAD_REFORMS_AT:
        fight.note(f"{adversary.name}'s bones rattle and lie still ({rolled})")
        return

    adversary.clear_hp(adversary.hp_marked)
    fight.note(
        f"{adversary.name} re-forms with no marked HP (Won't Stay Dead: {rolled})"
    )


@skip_spotlight(WONT_STAY_DEAD)
def wont_stay_dead_skips(adversary, fight=None) -> bool:
    """A Warrior that failed to re-form spends the activation on nothing.

    The third registration, and the one that keeps a pile of bones from swinging
    a sword. `on_spotlight` above has already had its say by the time this is
    asked - that ordering is fixed in `combat/policy.py` - so a Warrior that
    rolled a 6 is no longer defeated here and carries on to act, while one that
    didn't stops. A Warrior that was never defeated answers False and this costs
    it nothing.
    """
    return adversary.is_defeated


# --- Spellblade ---------------------------------------------------------------

ARCANE_STEEL = qualified(ADVERSARY, "Arcane Steel")


@standard_damage_type(ARCANE_STEEL)
def arcane_steel(adversary):
    """This adversary's standard attack is both physical and magic at once.

    SRD: "Damage dealt by the Spellblade's standard attack is considered both
    physical and magic." The page prints the same thing beside the attack itself
    - `1d8+4 phy/mag`.

    RULED. **A hit that is both is resisted if the target resists *either*.** So
    the Skeleton Warrior's `Only Bones` halves a Spellblade's swing exactly as the
    Minor Chaos Elemental's `Arcane Form` would, and a physical-only restriction
    like the Construct's `Weak Structure` fires on it too. The other reading -
    resisted only by something resistant to both, which would have made this an
    upgrade rather than a liability against a resistant target - was offered and
    declined.

    Only the **standard** attack, which is what the page says and what
    `Adversary.type_of_damage` enforces: a feature that states its own type is
    never asked. The Spellblade's own Suppressing Blast is printed as magic and
    stays magic.
    """
    return BOTH


SUPPRESSING_BLAST = qualified(ADVERSARY, "Suppressing Blast")


@action(SUPPRESSING_BLAST)
def suppressing_blast(adversary, target, fight: Fight):
    """Mark a Stress: everyone at Far saves or takes 1d8+2, and each wound pays a Fear.

    SRD: "Mark a Stress and target a group within Far range. All targets must
    succeed on an Agility Reaction Roll or take 1d8+2 magic damage. You gain a
    Fear for each target who marked HP from this attack."

    **A clean escape, not a save for half** - unlike Scorched Earth and Hellfire,
    which print "targets who succeed take half damage" and share `_flames`. This
    one says nothing of the kind, so a successful roll takes nothing and the
    feature is not written through that helper.

    **"All targets", not "all creatures"**, so it reaches the party alone and the
    Spellblade's own line stands in it untouched - the distinction the SRD
    alternates deliberately, and the same one that separates Hellfire from
    Scorched Earth.

    The Fear is paid **per target who marked HP**, not per target caught, so a
    hit an Armor Slot swallowed whole earns the GM nothing. That is a different
    trigger from Hail of Boulders' "if they succeed against more than one target",
    and it is the one place in the catalogue where a single Action can pay the GM
    several Fear at once.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table, with no threshold on how many it
    reaches. 6 HP against three Stress puts the Spellblade inside the line from
    full health - three slots free open at 10 or fewer unmarked HP - so in
    practice this is simply what it does until the Stress runs out.
    """
    caught = targets_in_area(Range.FAR, fight.conscious_party)
    if not caught or not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} looses a suppressing blast")

    # One roll shared by everyone caught, the way `_flames` does it - the page
    # describes a single blast rather than a roll per target.
    damage = roll_damage(dice_groups=[DiceGroup(count=1, sides=8)], modifier=2)
    wounded = 0
    for pc in caught:
        roll = _reaction_roll(pc, "agility", adversary.difficulty, fight)
        if roll.is_success:
            fight.note(f"{pc.name} dives clear of the blast ({roll})")
            continue
        marked = pc.take_damage(damage.total, fight, damage_type=DamageType.MAGIC)
        fight.note(f"{pc.name} is caught for {damage.total}")
        if marked > 0:
            wounded += 1

    for _ in range(wounded):
        fight.gain_fear(1)
    if wounded:
        fight.note(
            f"The blast draws blood from {wounded} of them (GM gains {wounded} Fear)"
        )
    return AttackResult(attack_roll=None, damage_roll=None)


MOVE_AS_A_UNIT = qualified(ADVERSARY, "Move as a Unit")
MOVE_AS_A_UNIT_FEAR = 2

# "Up to five allies", as printed.
MOVE_AS_A_UNIT_ALLIES = 5


@action(MOVE_AS_A_UNIT)
def move_as_a_unit(adversary, target, fight: Fight):
    """Spend 2 Fear to spotlight up to five allies within Far range.

    SRD: "Spend 2 Fear to spotlight up to five allies within Far range."

    The Head Guard's Rally Guards with a fixed number instead of a rolled one,
    and one real difference: Rally Guards spotlights the Head Guard **as well**
    ("spotlight the Head Guard and up to 2d4 allies"), where this names allies
    only. So the Spellblade spends its own spotlight rallying and does not act.

    Every spotlight it hands out is a `grant_activation`, which means what it
    means everywhere else: the extra activations sit inside the GM turn's cap and
    each still costs the loop its usual Fear. On a big field the cap rather than
    the pool is usually what limits it.

    Who is within Far goes through the area rule, and which allies get picked is
    random among those in range, for the reason every unordered list in this
    project is shuffled.

    USAGE POLICY - ruled. Used whenever the GM can afford the 2 Fear, and among
    the options that pass the choice is random - the standing default. No
    target-count threshold, the same ruling Rally Guards got: a Spellblade alone
    will spend 2 Fear on nothing rather than being held back by a knob nobody
    chose.
    """
    if fight.fear < MOVE_AS_A_UNIT_FEAR:
        return None

    allies = [other for other in fight.living_adversaries if other is not adversary]
    within = targets_reached(Range.FAR, len(allies)) if allies else 0
    rallied = (
        random.sample(allies, min(within, MOVE_AS_A_UNIT_ALLIES)) if within else []
    )

    fight.spend_fear(MOVE_AS_A_UNIT_FEAR)
    for ally in rallied:
        fight.grant_activation(ally)

    fight.note(
        f"{adversary.name} moves the line as one, rallying {len(rallied)} "
        f"{'ally' if len(rallied) == 1 else 'allies'} (Move as a Unit: GM spends "
        f"{MOVE_AS_A_UNIT_FEAR} Fear)"
    )
    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


# --- Swarm of Rats -------------------------------------------------------------

IN_YOUR_FACE = qualified(ADVERSARY, "In Your Face")


@party_attack_disadvantage(
    IN_YOUR_FACE,
    unmodelled=[
        "In Your Face: only a weapon attack reaches this, as with "
        "Armor-Shredding Shards. Content that rolls an attack of its own - a "
        "Grimoire spell, the Beastbound companion - has no weapon and so no "
        "range to read, and swings at anything unhobbled",
    ],
)
def in_your_face(adversary, attacker, target, weapon, fight=None) -> bool:
    """A creature in this adversary's face swings at anything else at Disadvantage.

    SRD: "All targets within Melee range have disadvantage on attacks against
    targets other than the Swarm."

    The first feature in the catalogue that hobbles a PC's roll depending on
    **who they chose to attack**, which is why `party_attack_disadvantage` exists:
    the trait hobble already in `Condition.disadvantage_on` cannot express it,
    since the trait is the same whichever adversary is being swung at.

    SIMULATION RULE - policy. "Within Melee range" is read off the **attacker's
    weapon**, the handle Armor-Shredding Shards, Fall Back, Magical Reflection and
    Burning all already use: a PC swinging a Melee weapon is in the rats' faces
    and one shooting from Far is not. That makes the Swarm a tax on the front line
    and free for archers, which is the shape it has at a table.

    Declines when the Swarm *is* the target, which is the whole of the feature -
    it does not stop anybody hitting the rats, it makes hitting anything else
    harder. A party's answer is to kill the Swarm first, which is what a swarm in
    your face is for.
    """
    if fight is None or target is adversary:
        return False
    return canonical(weapon.range) == canonical(Range.MELEE.value)


# --- Sylvan Soldier ------------------------------------------------------------

FOREST_CONTROL = qualified(ADVERSARY, "Forest Control")
FOREST_CONTROL_FEAR = 1

# "An Agility Reaction Roll (15)" - printed, unlike most, so it doesn't fall back
# on the Soldier's own Difficulty of 11.
FOREST_CONTROL_DIFFICULTY = 15


@action(
    FOREST_CONTROL,
    unmodelled=[
        "Forest Control: pulling the tree down *within Close range* is where the "
        "Soldier can reach, which is positioning. Who it lands on is the standing "
        "targeting rule's answer",
    ],
)
def forest_control(adversary, target, fight: Fight):
    """Spend a Fear to drop a tree on one creature for 1d10, saved on a 15.

    SRD: "Spend a Fear to pull down a tree within Close range. A creature hit by
    the tree must succeed on an Agility Reaction Roll (15) or take 1d10 physical
    damage."

    RULED. **One creature, not an area.** The SRD writes "a creature", singular,
    and it is careful everywhere else to write "all targets" or "all creatures"
    when it means an area - Suppressing Blast does so on the very same page. The
    alternative, everyone the Close band reaches, was offered and declined.

    No attack roll: the tree either catches them or it doesn't, and the Agility
    Reaction Roll is the only thing between the target and 1d10. The Difficulty is
    **printed** (15) rather than falling back on the Soldier's own 11, which makes
    this one of the few reaction rolls in the catalogue that states its own - and
    a hard one, four above what the stat block would otherwise ask.

    USAGE POLICY - ruled. Used whenever the GM can afford the Fear, and among the
    options that pass the choice is random - the standing default.
    """
    if fight.fear < FOREST_CONTROL_FEAR:
        return None

    fight.spend_fear(FOREST_CONTROL_FEAR)
    fight.note(f"{adversary.name} pulls down a tree (Forest Control: GM spends a Fear)")

    roll = _reaction_roll(target, "agility", FOREST_CONTROL_DIFFICULTY, fight)
    if roll.is_success:
        fight.note(f"{target.name} rolls clear of the falling tree ({roll})")
    else:
        damage = roll_damage(dice_groups=[DiceGroup(count=1, sides=10)], modifier=0)
        target.take_damage(damage.total, fight, damage_type=DamageType.PHYSICAL)
        fight.note(f"{target.name} is crushed for {damage.total} ({roll})")

    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


BLEND_IN = qualified(ADVERSARY, "Blend In")

# "A PC succeeds on an Instinct Roll (14) to find them", as printed.
BLEND_IN_FOUND_BY = ("instinct", 14)


@on_hit(BLEND_IN)
def blend_in(adversary, target, result, fight: Fight) -> None:
    """Mark a Stress on a landed attack to vanish until this adversary strikes again.

    SRD: "When the Soldier makes a successful attack, you can mark a Stress to
    become Hidden until the Soldier's next attack or a PC succeeds on an Instinct
    Roll (14) to find them."

    **Hidden is modelled**, on the user's ruling: every roll against a hidden
    combatant has Disadvantage. That is what this feature buys, and it is the
    reason the condition exists at all - the page says only "become Hidden", so
    what being Hidden is worth had to be decided rather than read.

    Two ways out, both printed and both modelled. The Soldier's next attack ends
    it, which `blend_in_reveals` below does on its next spotlight; and a PC can
    spend an action roll on an Instinct Roll (14), which the condition carries as
    its `found_by` and `combat/policy.py` acts on. **One such attempt per
    hiding**, ruled - the party does not throw spotlight after spotlight at it.

    USAGE POLICY - ruled. A Reaction, so it fires on every trigger it can pay for
    and the Stress-desperation rule that gates Actions deliberately does not
    apply. Two Stress against 4 HP means the Soldier's first two landed attacks
    each buy a turn of cover, from full health.
    """
    if result is None or result.damage_roll is None:
        return
    if not adversary.can_spend_stress(1):
        return

    adversary.spend_stress(1)
    fight.apply_condition(
        adversary,
        Condition(name=HIDDEN, source=adversary, found_by=BLEND_IN_FOUND_BY),
    )
    fight.note(f"{adversary.name} melts into the undergrowth (Blend In)")


@on_spotlight(BLEND_IN)
def blend_in_reveals(adversary, fight=None) -> None:
    """Coming out to attack ends the hiding.

    "Until the Soldier's next attack" - and the Soldier attacks on its spotlight,
    so the condition is lifted as the spotlight arrives. The difference between
    that and lifting it on the attack itself is invisible: being Hidden only
    changes rolls made *against* this adversary, and those happen on the party's
    spotlights, not on its own.

    Registered against the same name as the half above, so Blend In stays one
    piece of content in one place.
    """
    if fight is None:
        return
    if fight.has_condition(adversary, HIDDEN):
        fight.clear_condition(adversary, HIDDEN)
        fight.note(f"{adversary.name} breaks cover")


# --- The Tangle Brambles -------------------------------------------------------

ENCUMBER = qualified(ADVERSARY, "Encumber")
CRUSH = qualified(ADVERSARY, "Crush")
DRAIN_AND_MULTIPLY = qualified(ADVERSARY, "Drain and Multiply")

# The bramble tokens themselves, and the two counts the page keys on.
BRAMBLE_TOKEN = "Bramble token"
BRAMBLE_TOKENS_VULNERABLE = 3

# "A Finesse Roll (12 + the number of bramble tokens)", as printed.
BRAMBLE_ESCAPE_BASE = 12

# What the Minions that spring loose are, and what the Swarm is, by name.
TANGLE_BRAMBLE = "Tangle Bramble"
TANGLE_BRAMBLE_SWARM = "Tangle Bramble Swarm"

# "Three or more Tangle Bramble Minions within Close range", as printed.
DRAIN_AND_MULTIPLY_MINIONS = 3


def _bramble_escape(adversary):
    """The Finesse Roll that shakes every bramble token off, and what it spawns.

    SRD: "All bramble tokens can be removed by succeeding on a Finesse Roll (12 +
    the number of bramble tokens) ... If bramble tokens are removed from a target
    using a Finesse Roll, a number of Tangle Bramble Minions spawn within Melee
    range equal to the number of tokens removed."

    The Difficulty **rises with the count**, which is the only escape roll in the
    catalogue whose number moves - so the longer a PC is held the harder it gets
    to get out, and the more Minions they let loose when they do. Built as a
    closure over the Swarm rather than a plain predicate for that reason: it has
    to read the holder's own token count at the moment it is asked.
    """

    def ended(holder, fight, moment: str) -> bool:
        tokens = fight.token_count(holder, BRAMBLE_TOKEN)
        if tokens <= 0:
            return True

        roll = _reaction_roll(
            holder, "finesse", BRAMBLE_ESCAPE_BASE + tokens, fight
        )
        if not roll.is_success:
            return False

        fight.set_token(holder, BRAMBLE_TOKEN, 0)
        fight.clear_condition(holder, VULNERABLE)
        fight.note(f"{holder.name} tears free of the brambles ({roll})")

        # The tokens don't vanish - they get up and walk. Declines quietly if the
        # Minion isn't in the catalogue, the way every other summon does.
        try:
            definition = find_adversary(TANGLE_BRAMBLE)
        except KeyError:
            return True
        for _ in range(tokens):
            fight.summon(definition.spawn())
        fight.note(f"{tokens} {TANGLE_BRAMBLE}s spring loose where they fell")
        return True

    return ended


def _bramble_up(adversary, target, fight) -> None:
    """Add a bramble token to `target`, and apply what the count now buys."""
    tokens = fight.token_count(target, BRAMBLE_TOKEN) + 1
    fight.set_token(target, BRAMBLE_TOKEN, tokens)

    # "If a target has any bramble tokens, they are Restrained" - recorded rather
    # than merely declared, so content that keys on being held can see it, and
    # carrying its own way out so it survives the Swarm leaving the field.
    fight.apply_condition(
        target,
        Condition(name=RESTRAINED, end=_bramble_escape(adversary), source=adversary),
    )
    if tokens >= BRAMBLE_TOKENS_VULNERABLE:
        fight.apply_condition(target, Condition(name=VULNERABLE, source=adversary))
        fight.note(
            f"{target.name} is wrapped in {tokens} brambles - Restrained and Vulnerable"
        )
        return
    fight.note(f"{target.name} is tangled in {tokens} brambles, and is Restrained")


@on_hit(
    ENCUMBER,
    unmodelled=[
        "Encumber: what being Restrained stops - moving - which has no "
        "representation here. The tokens, the Vulnerable at three of them, the "
        "Finesse Roll out and the Minions it spawns are all modelled",
    ],
)
def encumber(adversary, target, result, fight: Fight) -> None:
    """A landed attack leaves a bramble token; three of them make the target Vulnerable.

    SRD: "When the Swarm succeeds on an attack, give the target a bramble token.
    If a target has any bramble tokens, they are Restrained. If a target has 3 or
    more bramble tokens, they are also Vulnerable. All bramble tokens can be
    removed by succeeding on a Finesse Roll (12 + the number of bramble tokens)
    or dealing Major or greater damage to the Swarm. If bramble tokens are removed
    from a target using a Finesse Roll, a number of Tangle Bramble Minions spawn
    within Melee range equal to the number of tokens removed."

    A **Reaction** on the page despite reading like a choice, so it fires on every
    landed attack and costs nothing - there is nothing here to gate.

    The tokens are the point, and they compound: each one raises the Finesse
    Difficulty to escape, the third makes the target Vulnerable (every roll
    against them at Advantage), and every token shaken off becomes a Tangle
    Bramble Minion standing next to them. So a PC who waits gets harder to free
    and lets more loose when they finally are.

    **Two ways out, and they are not equivalent.** The Finesse Roll spawns the
    Minions; Major damage to the Swarm simply clears the tokens
    (`encumber_releases` below). That asymmetry is printed, and it is the whole
    tactical shape of the stat block - hitting the brambles is cleaner than
    struggling out of them.
    """
    if result is None or result.damage_roll is None:
        return
    _bramble_up(adversary, target, fight)


@on_damaged(ENCUMBER)
def encumber_releases(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False, damage_type=None
) -> None:
    """Major damage to this adversary shakes every bramble token loose.

    "Or dealing Major or greater damage to the Swarm" - the other printed way
    out, keyed on the damage rolled rather than the HP it cost, the reading Acid
    Bath established.

    **No Minions spawn on this route.** The page attaches that only to the
    Finesse Roll, which is what makes cutting the Swarm the better answer.
    """
    if fight is None or amount < adversary.major_threshold:
        return

    freed = False
    for pc in fight.conscious_party:
        if not fight.token_count(pc, BRAMBLE_TOKEN):
            continue
        fight.set_token(pc, BRAMBLE_TOKEN, 0)
        held = fight.condition_on(pc, RESTRAINED)
        if held is not None and held.source is adversary:
            fight.clear_condition(pc, RESTRAINED)
        fight.clear_condition(pc, VULNERABLE)
        freed = True

    if freed:
        fight.note(f"The blow scatters {adversary.name}'s brambles, freeing the party")


@action(CRUSH)
def crush(adversary, target, fight: Fight):
    """Mark a Stress: 2d6+8 direct damage to somebody wrapped in three brambles.

    SRD: "Mark a Stress to deal 2d6+8 direct physical damage to a target with 3 or
    more bramble tokens."

    No attack roll at all - the brambles are already holding them - and **direct**,
    so no Armor Slot softens it. 2d6+8 averages 15 against the Swarm's printed
    1d6+3 at 6.5, and it is gated on a printed requirement rather than a policy of
    ours, the same shape as Coup de Grace and Deadly Shot.

    Chooses whoever is most wrapped up rather than the standing target, since the
    requirement is the whole point of the feature and the loop's target may not
    qualify at all.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table, plus the printed three-token gate. The
    Stress rule never actually holds this back - 6 HP against three Stress is
    inside the line from full health - so the **tokens** are the whole of the
    gate, and the Swarm has to have landed three attacks on somebody first.
    """
    if not adversary.will_spend_stress(1):
        return None

    wrapped = [
        pc
        for pc in fight.conscious_party
        if fight.token_count(pc, BRAMBLE_TOKEN) >= BRAMBLE_TOKENS_VULNERABLE
    ]
    if not wrapped:
        return None
    caught = max(wrapped, key=lambda pc: fight.token_count(pc, BRAMBLE_TOKEN))

    adversary.spend_stress(1)
    damage = roll_damage(dice_groups=[DiceGroup(count=2, sides=6)], modifier=8)
    caught.take_damage(
        damage.total, fight, direct=True, damage_type=DamageType.PHYSICAL
    )
    fight.note(
        f"{adversary.name} crushes {caught.name} in the brambles for {damage.total}"
    )
    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


@on_hit(
    DRAIN_AND_MULTIPLY,
    unmodelled=[
        "Drain and Multiply: 'within Close range' for the Minions being gathered "
        "up is positioning. The area rule stands in for it, as it does for Pack "
        "Tactics and No Quarter",
    ],
)
def drain_and_multiply(adversary, target, result, fight: Fight) -> None:
    """Three or more of these Minions can merge into a Horde when one draws blood.

    SRD: "When an attack from the Bramble causes a target to mark HP and there are
    three or more Tangle Bramble Minions within Close range, you can combine the
    Minions into a Tangle Bramble Swarm Horde. The Horde's HP is equal to the
    number of Minions combined."

    The first feature in the catalogue that turns adversaries into a *different*
    adversary, and the mirror of the Green Ooze's Split: that one is a single
    stat block becoming two smaller ones, this is several becoming one larger.
    Both go through `remove` and `summon` together, so the Minions leave without
    being defeated - marking their HP would tell the reader the party had won
    something at the moment they are worse off.

    **The Horde's HP is the count, not the stat block's printed 6.** That is what
    the page says, and it is the whole risk the feature carries for the GM: three
    Minions make a 3 HP Horde, which is frailer than the printed one. Spawned with
    an override, the way an encounter tunes a stat block.

    Keyed on HP actually marked rather than on the attack landing, which is what
    "causes a target to mark HP" says - a hit an Armor Slot swallowed whole
    changes nothing.

    Worth knowing what the area rule costs it, because the printed 3 and the band
    disagree: Close reaches `min(n * 3 // 4, n - 1)`, which is 2 at three Minions
    and only reaches 3 at **four**. So the feature cannot fire below four
    Brambles on the field - the same shape No Quarter has at six pirates, and
    arriving the same way, from a printed number meeting a proportional band.

    USAGE POLICY - ruled. A Reaction costing nothing, so it fires whenever its
    trigger happens and the area rule allows it. Nothing holds it back for the
    Horde being frailer than the Minions were: that is a comparison of what a
    combatant is worth, which is not something a policy here may turn on.
    """
    if result is None or result.hp_marked <= 0:
        return

    kin = [
        other
        for other in fight.living_adversaries
        if canonical(other.name) == canonical(adversary.name)
    ]
    if len(kin) < DRAIN_AND_MULTIPLY_MINIONS:
        return
    gathered = kin[: targets_reached(Range.CLOSE, len(kin))]
    if len(gathered) < DRAIN_AND_MULTIPLY_MINIONS:
        return

    try:
        definition = find_adversary(TANGLE_BRAMBLE_SWARM)
    except KeyError:
        # An encounter can be run against a cut-down catalogue; a feature that
        # can't find what it becomes leaves the Minions standing.
        return

    for minion in gathered:
        fight.remove(minion)
    fight.summon(definition.spawn(hp_max=len(gathered)))
    fight.note(
        f"{len(gathered)} {TANGLE_BRAMBLE}s knot together into a "
        f"{TANGLE_BRAMBLE_SWARM} with {len(gathered)} HP (Drain and Multiply)"
    )


# --- Weaponmaster --------------------------------------------------------------

GOADING_STRIKE = qualified(ADVERSARY, "Goading Strike")


@action(GOADING_STRIKE)
def goading_strike(adversary, target, fight: Fight):
    """The printed attack, plus a Stress to pin the target's attention.

    SRD: "Make a standard attack against a target. On a success, mark a Stress to
    Taunt the target until their next successful attack. The next time the
    Taunted target attacks, they have disadvantage against targets other than the
    Weaponmaster."

    RULED. **A Taunt fixes the target's target.** The printed text gives two
    different durations for one clause - "until their next successful attack" and
    "the next time the Taunted target attacks" - and rather than pick between
    them, the user ruled the effect itself: a Taunted PC swings at the
    Weaponmaster. That is what the feature does at a table, it makes the stated
    duration do work, and it needs no reading of which sentence wins.

    So this is the first GM-side content that reaches the *party's* targeting
    rule, through `party_target_override`. What the PC then does to the
    Weaponmaster is still entirely theirs - the compulsion is the target and
    nothing else.

    The *printed* attack, so no dice are passed and the Claymore's own 1d12+2 is
    rolled - which is what "a standard attack" says, and what lets a
    standard-damage swap reach it if the Weaponmaster ever had one. Rolled
    through the shared advantage rule rather than flat, the way Coup de Grace and
    Deadly Shot are, so a Vulnerable target hands it Advantage like any other
    attack.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table. 6 HP against three Stress means the
    first goad is available from full health, the second waits until 5 unmarked
    HP and the last until 2. It declines against a target it has *already* Taunted,
    on Rule 3 - the Taunt is the whole of what this buys over the standard
    attack, and re-applying it would change nothing while costing a Stress. The
    loop then falls through to the standard attack, which deals exactly the same
    damage.
    """
    from combat.policy import adversary_attack_advantage

    taunt = fight.condition_on(target, TAUNTED)
    if taunt is not None and taunt.source is adversary:
        return None
    if not adversary.will_spend_stress(1):
        return None

    result = adversary.attack(
        target, adversary_attack_advantage(adversary, target, fight), fight
    )
    if result.damage_roll is None:
        return result

    adversary.spend_stress(1)
    fight.apply_condition(target, Condition(name=TAUNTED, source=adversary))
    fight.note(
        f"{adversary.name} goads {target.name}, who can look at nothing else "
        f"(Taunted)"
    )
    return result


@party_target_override(GOADING_STRIKE)
def goading_strike_compels(adversary, attacker, fight=None):
    """A PC this adversary has Taunted attacks it and nothing else.

    Scanned across the *living* adversaries, so a dead Weaponmaster compels
    nobody - and the condition itself is swept up by
    `FightState.release_conditions_from` when it leaves the field, since it
    carries a source and no `end` of its own.
    """
    if fight is None:
        return None
    taunt = fight.condition_on(attacker, TAUNTED)
    if taunt is None or taunt.source is not adversary:
        return None
    return adversary


@on_party_attack_roll(GOADING_STRIKE)
def goading_strike_releases(adversary, roller, roll, fight=None) -> None:
    """The Taunt lifts on the target's next successful attack.

    The printed duration, and the reason this is the hook rather than a
    `Condition.end`: the loop announces moments (a combatant acting, a GM turn),
    and none of them is "an attack roll succeeded". This one watches the roll
    itself, which is exactly what the page names.

    Registered against the same name as the two halves above, so Goading Strike
    stays one piece of content in one place.
    """
    if fight is None or not roll.is_success:
        return

    taunt = fight.condition_on(roller, TAUNTED)
    if taunt is None or taunt.source is not adversary:
        return

    fight.clear_condition(roller, TAUNTED)
    fight.note(f"{roller.name} lands a blow and shakes off the taunt")


ADRENALINE_BURST = qualified(ADVERSARY, "Adrenaline Burst")
ADRENALINE_BURST_FEAR = 1
ADRENALINE_BURST_TOKEN = "Adrenaline Burst"

# "Clear 2 HP and 2 Stress", as printed.
ADRENALINE_BURST_HP = 2
ADRENALINE_BURST_STRESS = 2


@action(ADRENALINE_BURST)
def adrenaline_burst(adversary, target, fight: Fight):
    """Once a fight, spend a Fear to clear 2 HP and 2 Stress.

    SRD: "Once per scene, spend a Fear to clear 2 HP and 2 Stress."

    A scene is one fight here, and the limit is held with a token rather than
    with the per-rest machinery, for the reason Reinforcements gives: a
    once-per-*scene* ability is available in every fight whatever rest preceded
    it, where `use_once_per_rest` would correctly refuse it in a no-rest
    encounter.

    USAGE POLICY - ruled, and general. **A feature that clears fixed quantities
    is used only when it can clear all of them.** So this waits until 2 HP *and*
    2 Stress are actually marked; below that the Fear and the scene's single use
    would buy less than the page promises. The rule is stated once here and in
    SIMULATION-RULES.md rather than per feature - the Patchwork Zombie Hulk's
    `Another for the Pile` is the second case in this batch alone.

    Note it is deliberately *not* the Consume Kindling rule, which is a different
    shape: that one clears "a HP **or** a Stress", so it takes whichever is
    there. This one names both, so it waits for both.

    A Weaponmaster reaches the bar somewhere in the middle of a fight - three
    Stress, two of which its own Goading Strikes spend - and buying back 2 HP of
    6 is most of a second wind.
    """
    if fight.token_count(adversary, ADRENALINE_BURST_TOKEN):
        return None
    if adversary.hp_marked < ADRENALINE_BURST_HP:
        return None
    if adversary.stress_marked < ADRENALINE_BURST_STRESS:
        return None
    if fight.fear < ADRENALINE_BURST_FEAR:
        return None

    fight.spend_fear(ADRENALINE_BURST_FEAR)
    fight.set_token(adversary, ADRENALINE_BURST_TOKEN, 1)
    adversary.clear_hp(ADRENALINE_BURST_HP)
    adversary.clear_stress(ADRENALINE_BURST_STRESS)
    fight.note(
        f"{adversary.name} finds a second wind (Adrenaline Burst: clears "
        f"{ADRENALINE_BURST_HP} HP and {ADRENALINE_BURST_STRESS} Stress, GM "
        f"spends a Fear)"
    )
    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


# --- Young Dryad ---------------------------------------------------------------

VOICE_OF_THE_FOREST = qualified(ADVERSARY, "Voice of the Forest")

# "Spotlight 1d4 allies", as printed. Rolled with `random` directly, the way
# Rally Guards' 2d4 and the Spitter Die are - this is neither an attack, a damage
# roll nor a duality roll, so nothing in dice/ has a shape for it.
VOICE_OF_THE_FOREST_DIE = 4
VOICE_OF_THE_FOREST_TOKEN = "Voice of the Forest"

# "Their attacks deal half damage", as printed.
VOICE_OF_THE_FOREST_HALVED = 0.5


@action(
    VOICE_OF_THE_FOREST,
    unmodelled=[
        "Voice of the Forest: 'within range of a target they can attack without "
        "moving' is positioning, and it constrains the *allies* rather than the "
        "Dryad - so unlike Rally Guards and Move as a Unit there is no printed "
        "band to run through the area rule. Every living ally is eligible and "
        "the 1d4 is the whole cap",
    ],
)
def voice_of_the_forest(adversary, target, fight: Fight):
    """Mark a Stress to hand 1d4 allies a free spotlight, at half damage.

    SRD: "Mark a Stress to spotlight 1d4 allies within range of a target they can
    attack without moving. On a success, their attacks deal half damage."

    The second sentence reads oddly on its own - there is no roll here for "a
    success" to be about - and the SRD prints the clean version of the same
    clause on three later stat blocks: "attacks they make while spotlighted this
    way deal half damage" (the Knight of the Realm, the Mortal Hunter, the
    Secret-Keeper). So the halving is what the rally costs, paid by the allies.

    RULED. **These activations are free**: they cost the GM no Fear and do not
    count against the turn's cap of party size + 1. That is a deliberate
    departure from what Rally Guards, Move as a Unit, Tactician and Overload were
    ruled to do, and it is scoped to this feature alone - the machinery in
    `FightState.grant_activation` is generic so anything else can be moved to it
    later, but nothing already ported has been. See SIMULATION-RULES.md.

    Which allies get picked is random among those alive, for the reason every
    unordered list in this project is shuffled. Nobody's own spotlight is handed
    out here: the Dryad spends its whole activation rallying and does not attack,
    the way Move as a Unit does and unlike Rally Guards.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table, and among the options that pass the
    choice is random. Deliberately **no** target-count threshold, the same ruling
    Rally Guards and Move as a Unit got: a Dryad standing alone will spend a
    Stress on nothing rather than be held back by a knob nobody chose.

    Worth knowing where that line falls, because it is the Bear's shape rather
    than the usual one: 6 HP against only **two** Stress means the first rally
    waits until the Dryad is at 5 or fewer unmarked HP, and the second until 2.
    So a Dryad at full health is a 1d8+5 attacker and nothing else, and the
    forest answers once the party has hurt it.
    """
    if not adversary.will_spend_stress(1):
        return None

    allies = [other for other in fight.living_adversaries if other is not adversary]
    wanted = random.randint(1, VOICE_OF_THE_FOREST_DIE)
    rallied = random.sample(allies, min(len(allies), wanted)) if allies else []

    adversary.spend_stress(1)
    for ally in rallied:
        fight.grant_activation(ally, free=True)
        # Stamped with the turn it was granted on, so a free spotlight some other
        # feature hands the same ally later in the fight isn't quietly halved too.
        # Offset by one so an ally who was never rallied - whose token reads 0,
        # the same as never having been set - can't match turn zero.
        fight.set_token(ally, VOICE_OF_THE_FOREST_TOKEN, fight.gm_turns + 1)

    fight.note(
        f"{adversary.name} calls the forest to arms, rallying {len(rallied)} "
        f"{'ally' if len(rallied) == 1 else 'allies'} for free (Voice of the "
        f"Forest: their attacks deal half damage)"
    )
    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


@damage_multiplier(VOICE_OF_THE_FOREST)
def voice_of_the_forest_halves(adversary, target, attacker, fight=None) -> float | None:
    """An ally acting on this adversary's free spotlight deals half damage.

    The other half of the rally, registered against the same name so the feature
    stays one piece of content in one place - and on the same hook as the Jagged
    Knife Kneebreaker's `I've Got 'Em`, pointed the other way. That one doubles
    what a third party deals; this one halves it, which is the same question
    ("how much of this roll actually lands?") with the number moving the other
    direction. `content/registry.py`'s `damage_multiplier` says why a fraction is
    allowed there, and `Adversary._dealt` floors the product once at the end.

    **Scoped to the granted activation**, which is what "while spotlighted this
    way" means and what `FightState.acting_freely` exists to answer. Asking that
    rather than spending the token on the first damage roll is what keeps an area
    attack honest: one sweep is one attack, and every target it catches should be
    halved, not only the first.

    Halving lands **before** the target's thresholds, the same place I've Got
    'Em's doubling does - and that is where the effect really lives, since damage
    reaches HP through bands.
    """
    if fight is None or attacker is adversary:
        return None
    if not fight.acting_freely(attacker):
        return None
    if fight.token_count(attacker, VOICE_OF_THE_FOREST_TOKEN) != fight.gm_turns + 1:
        return None

    fight.note(
        f"{attacker.name} strikes on the Dryad's call, and deals half damage "
        f"(Voice of the Forest: {adversary.name})"
    )
    return VOICE_OF_THE_FOREST_HALVED


THORNY_CAGE = qualified(ADVERSARY, "Thorny Cage")
THORNY_CAGE_FEAR = 1


def _thorny_cage_breaks(adversary):
    """The way out of the cage, in the two steps the user ruled.

    The caged PC tries the printed Strength Roll first. If that fails, **another
    PC marks a Stress and pulls the cage apart** - which is where the page's
    "when a creature makes an action roll against the cage, they must mark a
    Stress" lands: the creature acting against the cage is an ally, and the
    Stress is what it costs them.

    So the cage holds for at most one of its victim's spotlights, and costs the
    party either nothing (a made roll) or one Stress. Who pays is random among
    the allies who can, since the order an encounter listed the party in carries
    no meaning.

    A closure over the Dryad rather than a plain predicate, because the escape
    Difficulty is the Dryad's own - the page prints none, which is the standing
    fallback for a reaction roll.
    """

    def ended(holder, fight, moment: str) -> bool:
        roll = _reaction_roll(holder, "strength", adversary.difficulty, fight)
        if roll.is_success:
            fight.note(f"{holder.name} forces the cage apart ({roll})")
            return True

        helpers = [
            pc
            for pc in fight.conscious_party
            if pc is not holder and pc.can_spend_stress(1)
        ]
        if not helpers:
            fight.note(
                f"{holder.name} is caught fast, and nobody is free to pry the "
                f"cage open ({roll})"
            )
            return False

        helper = helpers[0] if len(helpers) == 1 else random.choice(helpers)
        helper.spend_stress(1)
        fight.note(
            f"{helper.name} tears {holder.name}'s cage open, and marks a Stress"
        )
        return True

    return ended


@action(
    THORNY_CAGE,
    unmodelled=[
        "Thorny Cage: what being Restrained stops - moving - which has no "
        "representation here. The condition is recorded so content that keys on "
        "being held can see it, and both ways out are modelled in full",
    ],
)
def thorny_cage(adversary, target, fight: Fight):
    """Spend a Fear to cage one target, until they or an ally break it open.

    SRD: "Spend a Fear to form a cage around a target within Very Close range and
    Restrain them until they're freed with a successful Strength Roll. When a
    creature makes an action roll against the cage, they must mark a Stress."

    No attack roll: the cage simply closes. The Difficulty of the Strength Roll
    is not printed, so it falls back on the Dryad's own 11 - the standing rule
    for a reaction roll with no stated number.

    USAGE POLICY - ruled. Used whenever the GM can afford the Fear, and among the
    options that pass the choice is random. The one check is Rule 3: it declines
    against somebody this Dryad has already caged, since the cage is the whole of
    the feature - there is no damage attached - and a second one would spend a
    Fear and a spotlight to change nothing. That is the Curse's shape rather than
    Grab and Drag's, which deals real damage around its hold and so has no such
    check.
    """
    if fight.fear < THORNY_CAGE_FEAR:
        return None

    held = fight.condition_on(target, RESTRAINED)
    if held is not None and held.source is adversary:
        return None

    fight.spend_fear(THORNY_CAGE_FEAR)
    fight.apply_condition(
        target,
        Condition(
            name=RESTRAINED, end=_thorny_cage_breaks(adversary), source=adversary
        ),
    )
    fight.note(
        f"{adversary.name} closes a cage of thorns around {target.name} "
        f"(Thorny Cage: GM spends a Fear)"
    )
    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


# --- Brawny Zombie -------------------------------------------------------------

REND_ASUNDER = qualified(ADVERSARY, "Rend Asunder")


@action(REND_ASUNDER)
def rend_asunder(adversary, target, fight: Fight):
    """The printed attack with Advantage, direct, against somebody it is holding.

    SRD: "Make a standard attack with advantage against a target the Zombie has
    Restrained. On a success, the attack deals direct damage."

    Gated on a **printed** requirement rather than a policy of ours, the same
    shape Coup de Grace, Deadly Shot and Crush have - and read strictly through
    `Condition.source`, so a creature some other adversary is holding does not
    qualify. Nothing but this Zombie's own *Rip and Tear* puts anybody in that
    state, so the two halves of the stat block are a sequence: hold first, then
    tear.

    Chooses whoever it is actually holding rather than the standing target, since
    the requirement is the whole point of the feature and the loop's target
    usually will not qualify. The standing target wins when it does, and
    otherwise the choice is random among those held.

    The *printed* attack, so no dice are passed and the Slam's own 1d12+3 is
    rolled - which also means the Zombie's own Rip and Tear reaches it, since
    that fires on any attack that rolls the standard damage.

    The Advantage is **folded** with the shared advantage rule rather than
    replacing it, so a target who is also Vulnerable does not come out with less
    than they would have - Advantage doesn't stack, and combining is how every
    other source in the codebase is handled.

    Direct, so no Armor Slot softens it. Against a party that marks a free slot
    against everything that is worth close to a whole extra HP on top of an
    average of 9.5.

    USAGE POLICY - ruled. Nothing to pay, so nothing to gate beyond the printed
    requirement: it joins the shuffled pool of options whenever the Zombie has
    somebody held, the standing default.
    """
    from combat.policy import adversary_attack_advantage

    held = [
        pc
        for pc in fight.conscious_party
        if (caged := fight.condition_on(pc, RESTRAINED)) is not None
        and caged.source is adversary
    ]
    if not held:
        return None

    # Identity, not equality: both combatant classes are plain dataclasses, so
    # `in` would compare field by field and could match the wrong body.
    if any(pc is target for pc in held):
        caught = target
    elif len(held) == 1:
        caught = held[0]
    else:
        caught = random.choice(held)

    fight.note(f"{adversary.name} rends {caught.name} asunder")
    return adversary.attack(
        caught,
        combined(
            AdvantageState.ADVANTAGE,
            adversary_attack_advantage(adversary, caught, fight),
        ),
        fight,
        direct=True,
    )


RIP_AND_TEAR = qualified(ADVERSARY, "Rip and Tear")

# "Force them to mark 2 Stress", as printed.
RIP_AND_TEAR_STRESS = 2


@standard_damage(
    RIP_AND_TEAR,
    unmodelled=[
        "Rip and Tear: what being Restrained stops - moving - which has no "
        "representation here. The condition is recorded so the Zombie's own Rend "
        "Asunder can key on it, and the forced Stress is modelled in full",
    ],
)
def rip_and_tear(adversary, target, roll=None, fight=None):
    """Mark a Stress on a landed standard attack to hold the target and cost them 2.

    SRD: "When the Zombie makes a successful standard attack, you can mark a
    Stress to temporarily Restrain the target and force them to mark 2 Stress."

    **Registered on `standard_damage` although it swaps no dice**, and that is
    the point rather than a workaround: this hook is asked once, from inside the
    damage roll, for exactly the attacks that roll the stat block's *printed*
    damage - which is what the SRD means by "a standard attack". `on_hit` would
    have been the wrong trigger, since it fires for every attack a feature rolls
    with dice of its own. Declining the swap by returning None leaves the printed
    1d12+3 exactly as it was.

    One consequence worth knowing: the forced Stress lands a moment *before* the
    damage does, since the hook runs while the damage is still being rolled. A PC
    with no free slot therefore marks the Stress as an HP first and takes the
    Slam second, where at a table the order would be the other way round. It can
    change which mark drops somebody, and no other ordering was available without
    a hook whose only user would be this feature.

    "Temporarily Restrain" with no printed way out, so it lasts the rest of the
    fight - the standing rule for a condition an adversary puts on a PC. It
    carries a source and no `end`, which means killing the Zombie frees them,
    through `FightState.release_conditions_from`.

    USAGE POLICY - ruled. A Reaction, so it fires on every trigger it can pay for
    and the Stress-desperation rule that gates Actions deliberately does not
    apply. Four Stress against 7 HP means the Zombie's first four landed attacks
    each cost the target 2 Stress, from full health. No already-held check: the
    2 Stress lands whether or not the hold is already on, so declining would give
    up something real - the Envelop reading rather than the Ignite one.
    """
    if fight is None or not adversary.can_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.apply_condition(target, Condition(name=RESTRAINED, source=adversary))
    target.mark_stress(RIP_AND_TEAR_STRESS)
    fight.note(
        f"{adversary.name} rips into {target.name}, who is Restrained and marks "
        f"{RIP_AND_TEAR_STRESS} Stress (Rip and Tear)"
    )
    # The printed damage is unchanged; this feature only ever rides along.
    return None


# --- Patchwork Zombie Hulk -----------------------------------------------------

DESTRUCTIBLE = qualified(ADVERSARY, "Destructible")


@severity_increase(DESTRUCTIBLE)
def destructible(
    adversary, amount: int, hp_to_mark: int, fight=None, damage_type=None
) -> int:
    """A Major or greater hit on this adversary marks an additional HP.

    SRD: "When the Zombie takes Major or greater damage, they mark an additional
    HP."

    The Construct's `Weak Structure` on the other hook of the same pair, and
    keyed differently on purpose: that one triggers on HP being *marked* and is
    restricted to physical damage, where this one reads the **damage rolled**
    against the Major threshold and takes any type at all. Both are what their
    pages say.

    Reading the number rather than the mark is the same choice Acid Bath and
    Hold Them Down make for "takes Severe damage" and "takes Major or greater
    damage" - the trigger names the size of the hit, not what it cost.

    On a 10 HP track with thresholds of 8 and 15 this turns every Major hit into
    3 HP and every Severe into 4. The zero check below never actually bites - a
    hit at or above the Major threshold has already marked at least 2 - and is
    there for the same honesty `Swashbuckler`'s lower bound is.
    """
    if amount < adversary.major_threshold:
        return hp_to_mark
    if hp_to_mark <= 0:
        return hp_to_mark
    return hp_to_mark + 1


FLAILING_LIMBS = qualified(ADVERSARY, "Flailing Limbs")


@attack_area(FLAILING_LIMBS)
def flailing_limbs(adversary, fight=None):
    """The standard attack sweeps everyone within Very Close range.

    SRD: "When the Zombie makes a standard attack, they can attack all targets
    within Very Close range."

    **The band is named on the page**, unlike the Cave Ogre's Ramp Up, which says
    only "within range" and therefore reads its holder's printed range off the
    stat block. Here the SRD writes Very Close outright, so that is what is
    returned - it happens to match the Hulk's own printed range, and would stay
    correct if it didn't.

    A passive rather than an action, so the sweep is not one option among
    several: it changes what the ordinary attack *is*. The page's "they can" is
    read as always taken, because sweeping is weakly better than not - one attack
    roll and one damage roll either way, applied to everyone it beats rather than
    to one - so there is never a moment where declining buys anything.

    Worth knowing what the area rule costs it: Very Close is held to two, so
    against a party of four this reaches one or two, and the 1d20 lands on each
    of them.
    """
    return Range.VERY_CLOSE


ANOTHER_FOR_THE_PILE = qualified(ADVERSARY, "Another for the Pile")
ANOTHER_FOR_THE_PILE_TOKEN = "Absorbed"

# "Clearing a HP and a Stress", as printed.
ANOTHER_FOR_THE_PILE_HP = 1
ANOTHER_FOR_THE_PILE_STRESS = 1


@action(ANOTHER_FOR_THE_PILE)
def another_for_the_pile(adversary, target, fight: Fight):
    """Absorb a body off the field to clear an HP and a Stress.

    SRD: "When the Zombie is within Very Close range of a corpse, they can
    incorporate it into themselves, clearing a HP and a Stress."

    RULED. **A corpse is an adversary that has been defeated in this fight**, and
    each one can be absorbed only once. Nothing else in the simulator represents
    a body, and the alternative - the Consume Kindling ruling, where the fiction
    is simply assumed available - was declined here: unlike scattered kindling
    there is a real piece of field state to point at, and using it gives the Hulk
    a shape that depends on the encounter. A Hulk fielded alone never eats; one
    standing behind a screen of Rotted Zombies feeds all fight.

    "Within Very Close range" is positioning, and the area rule answers it
    trivially: the band's reach is floored at one, so a corpse anywhere on the
    field is always within reach of it. Nothing is gated on the count.

    An adversary taken off the field *without* being defeated - a Green Ooze that
    Split - leaves no body, which is right: it did not die. See
    `FightState.defeated_adversaries`.

    USAGE POLICY - ruled, and the same general rule Adrenaline Burst records: a
    feature that clears fixed quantities is used only when it can clear all of
    them. So this waits for an HP *and* a Stress to be marked. There is no
    per-scene limit, because the page prints none - what bounds it is the supply
    of bodies.
    """
    if adversary.hp_marked < ANOTHER_FOR_THE_PILE_HP:
        return None
    if adversary.stress_marked < ANOTHER_FOR_THE_PILE_STRESS:
        return None

    corpses = [
        corpse
        for corpse in fight.defeated_adversaries
        if not fight.token_count(corpse, ANOTHER_FOR_THE_PILE_TOKEN)
    ]
    if not corpses:
        return None

    # Which body gets eaten is random among those left, for the reason every
    # unordered list in this project is: the order an encounter spawned its
    # adversaries in carries no meaning.
    eaten = corpses[0] if len(corpses) == 1 else random.choice(corpses)
    fight.set_token(eaten, ANOTHER_FOR_THE_PILE_TOKEN, 1)

    adversary.clear_hp(ANOTHER_FOR_THE_PILE_HP)
    adversary.clear_stress(ANOTHER_FOR_THE_PILE_STRESS)
    fight.note(
        f"{adversary.name} folds {eaten.name} into itself (Another for the Pile: "
        f"clears an HP and a Stress)"
    )
    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


TORMENTED_SCREAMS = qualified(ADVERSARY, "Tormented Screams")

# "A Presence Reaction Roll (13)" - printed, so it doesn't fall back on the
# Hulk's own Difficulty of 13. (They happen to agree; the number is still read
# from the feature, since a retuned stat block must not move it.)
TORMENTED_SCREAMS_DIFFICULTY = 13


@action(TORMENTED_SCREAMS)
def tormented_screams(adversary, target, fight: Fight):
    """Mark a Stress: everyone at Far saves against losing a Hope, and each costs a Fear.

    SRD: "Mark a Stress to cause all PCs within Far range to make a Presence
    Reaction Roll (13). Targets who fail lose a Hope and you gain a Fear for
    each. Targets who succeed must mark a Stress."

    **Both outcomes cost something**, which is unusual - every other reaction roll
    in the catalogue either buys a clean escape or halves the damage. Only a
    critical gets away with nothing, per the standing rule that a critical
    ignores the effect entirely.

    "You gain a Fear **for each**" is the phrase that settled the Skeleton
    Knight's `Terrifying` at a single Fear two entries earlier on the same page:
    a bare "you gain a Fear" means one, and this is what the other reading looks
    like when the SRD wants it. So the two features differ in code, and this one
    can pay the GM several Fear at once - the second such feature in the
    catalogue after the Spellblade's Suppressing Blast.

    The Fear is paid per PC who *failed*, whether or not they had a Hope to lose;
    the trigger names the failure, not the loss. `spend_hope` clamps, so a PC
    with none simply loses nothing - and it is counted as spent in the report for
    the reason All Must Fall and Terrifying give.

    Far reaches the whole field, so unlike the Hulk's own Very Close sweep there
    is no band holding this back.

    USAGE POLICY - ruled. An Action costing Stress, so the Stress-desperation
    rule decides when it is on the table. 10 HP against three Stress is the
    deepest HP track in tier 1, and three free slots open at 10 or fewer unmarked
    HP - so the Hulk is exactly on the line at full health and screams from the
    opening spotlight.
    """
    caught = targets_in_area(Range.FAR, fight.conscious_party)
    if not caught or not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} screams with a dozen stolen voices")

    for pc in caught:
        roll = _reaction_roll(pc, "presence", TORMENTED_SCREAMS_DIFFICULTY, fight)
        if roll.is_critical:
            fight.note(f"{pc.name} shuts the screaming out entirely ({roll})")
            continue
        if roll.is_success:
            pc.mark_stress(1)
            fight.note(f"{pc.name} holds their nerve, and marks a Stress ({roll})")
            continue

        if pc.can_spend_hope(1):
            pc.spend_hope(1)
        fight.gain_fear(1)
        fight.note(
            f"{pc.name} is unmanned by the screaming, losing a Hope ({roll}; GM "
            f"gains a Fear)"
        )

    # The spotlight is spent, but nothing rolled to hit anybody.
    return AttackResult(attack_roll=None, damage_roll=None)


# --- Shambling Zombie ----------------------------------------------------------

TOO_MANY_TO_HANDLE = qualified(ADVERSARY, "Too Many to Handle")

# "At least one other Zombie", so two counting the one holding the feature - the
# reading Opportunist and No Quarter already take of a printed count.
TOO_MANY_TO_HANDLE_ZOMBIES = 2

# What counts as a Zombie: any stat block with the word in its name, matched
# canonically. RULED, on the No Quarter precedent - the SRD writes the
# requirement as a *kind* ("at least one other Zombie") rather than naming a stat
# block the way Pack Tactics names "another Sylvan Soldier", and the book prints
# five Zombies in tier 1 alone.
ZOMBIE = canonical("Zombie")


@attack_advantage_against(TOO_MANY_TO_HANDLE)
def too_many_to_handle(adversary, target, fight=None) -> bool:
    """A creature this adversary crowds is attacked at Advantage by everyone.

    SRD: "When the Zombie is within Melee range of a creature and at least one
    other Zombie is within Close range, all attacks against that creature have
    advantage."

    The first feature in the catalogue that hands Advantage to attacks made by
    somebody *else*, which is why `attack_advantage_against` exists: the holder-
    scoped `attack_advantage` can only speak for the combatant carrying it, and a
    surrounding feature is precisely not that. It is the exact mirror of the
    Swarm of Rats' `In Your Face`, pointed across the table in the other
    direction.

    SIMULATION RULE - policy. Both halves are positioning, so the **area rule
    answers both**, the way it answers Pack Tactics, No Quarter and Opportunist.
    Whether this Zombie is in Melee of the creature is `targets_in_area(MELEE,
    party)`, which reaches one or two of a party of four and takes the most
    wounded first; whether another Zombie is within Close is
    `targets_reached(CLOSE, ...)` over the mob, needing
    `TOO_MANY_TO_HANDLE_ZOMBIES` of them counting this one.

    Both are rolled afresh per attack, which is what the band rules are for -
    the same field is sometimes bunched and sometimes strung out, and a feature
    that always found it arranged the way it liked would be priced off its best
    case.

    Worth knowing before reading numbers, because the printed 1 and the band
    disagree. Close reaches `min(n * 3 // 4, n - 1)`, which over **two** Zombies
    is 1 whichever way the spread roll falls - so **this cannot fire below three
    Zombies on the field**, and above that it always does. That is the same shape
    No Quarter has at six pirates and Drain and Multiply at four Brambles, and it
    arrives the same way: a printed count meeting a proportional band, not a
    threshold of ours.
    """
    if fight is None:
        return False
    # Identity, not equality - see `rend_asunder` for why `in` is unsafe here.
    engaged = targets_in_area(Range.MELEE, fight.conscious_party)
    if not any(pc is target for pc in engaged):
        return False

    mob = [
        other for other in fight.living_adversaries if ZOMBIE in canonical(other.name)
    ]
    # This Zombie counts: the question is how many of the mob are on this
    # creature, and it is one of them.
    if len(mob) < TOO_MANY_TO_HANDLE_ZOMBIES:
        return False
    return targets_reached(Range.CLOSE, len(mob)) >= TOO_MANY_TO_HANDLE_ZOMBIES


HORRIFYING = qualified(ADVERSARY, "Horrifying")


@on_hit(HORRIFYING)
def horrifying(adversary, target, result, fight: Fight) -> None:
    """A hit from this adversary that wounds also costs the target a Stress.

    SRD: "Targets who mark HP from the Zombie's attacks must also mark a Stress."

    Keyed on HP actually marked rather than on the attack landing, which is what
    the trigger says: a hit an Armor Slot swallowed whole wounded nobody, so
    there is nothing to be horrified by. `AttackResult.hp_marked` carries that
    figure back from wherever the damage was resolved - the same reading
    Bloodsucker and Drain and Multiply use.

    "The Zombie's attacks", plural and unqualified, so this reaches every attack
    it makes rather than only the standard one.

    The Stress is forced, so a PC with no free slot marks an HP instead. On a
    1 Stress stat block that costs the Zombie nothing at all, which is what makes
    a mob of them expensive: a party's Stress track is what pays for their cards,
    and a PC with none spare is Vulnerable for the rest of the fight.
    """
    if result is None or result.hp_marked <= 0:
        return

    target.mark_stress(1)
    fight.note(f"{target.name} recoils from {adversary.name}, and marks a Stress")


# --- Zombie Pack ---------------------------------------------------------------

OVERWHELM = qualified(ADVERSARY, "Overwhelm")


@on_attacked(
    OVERWHELM,
    unmodelled=[
        "Overwhelm: only a weapon attack reaches this, as with Armor-Shredding "
        "Shards. Content that rolls an attack of its own - a Grimoire spell, the "
        "Beastbound companion - has no weapon and so no range to read, and is "
        "never counterattacked",
    ],
)
def overwhelm(adversary, attacker, weapon, damage=0, hp_marked=0, fight=None) -> None:
    """A Melee hit that wounds this adversary buys the attacker a swing back.

    SRD: "When the Zombies mark HP from an attack within Melee range, you can
    mark a Stress to make a standard attack against the attacker."

    **It is the Zombies who mark the HP**, not the PC - the SRD writes adversary
    features from the stat block's own side throughout, and reading it the other
    way round would turn a wounded-beast reflex into a second attack on a hit
    that never landed. So this fires on a hit that got through, which on a 6 HP
    Horde with thresholds of 6 and 12 is very nearly every hit.

    SIMULATION RULE - policy. "Within Melee range" is read off the **attacker's
    weapon**, the handle Armor-Shredding Shards, Fall Back, Magical Reflection,
    Burning and In Your Face all already use: a PC swinging a Melee weapon is
    close enough to be grabbed and one shooting from Far is not. The Pack is
    therefore a tax on the front line and free for archers.

    The counterattack is the *printed* attack, so the Pack's own `Horde (1d4+2)`
    reaches it and a worn-down Pack swings back for less.

    USAGE POLICY - ruled. A Reaction, so it fires on every trigger it can pay for
    and the Stress-desperation rule that gates Actions deliberately does not
    apply. Three Stress means the first three melee hits that hurt it each earn a
    1d10+2 back, from full health.
    """
    if fight is None or hp_marked <= 0:
        return
    if canonical(weapon.range) != canonical(Range.MELEE.value):
        return
    if not adversary.can_spend_stress(1):
        return

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} surges over {attacker.name} (Overwhelm)")
    result = adversary.attack(attacker, fight=fight)
    if result.damage_roll is None:
        fight.note(f"{adversary.name} misses {attacker.name} ({result.attack_roll})")
        return

    fight.note(
        f"{adversary.name} drags {attacker.name} down for {result.damage_roll.total}"
    )
    # A Reaction's attack is made outside the spotlight loop, so the loop isn't
    # there to hand out the riders a landed attack triggers - the Harrier's Fall
    # Back and the Skeleton Knight's Dig Two Graves have the same problem and the
    # same answer. Asked generically.
    apply_on_hit(adversary, attacker, result, fight)


# --- Ahuizotl (SRD 2.0) ------------------------------------------------------

AQUATIC_ATTACKER = qualified(ADVERSARY, "Aquatic Attacker")

AQUATIC_ATTACKER_DIE = 6


@attack_advantage(
    AQUATIC_ATTACKER,
    unmodelled=[
        "The Advantage reaches the **standard attack only**. `attack_advantage` is "
        "asked once per activation in `combat/policy.py`, and an Action feature "
        "that rolls its own attack passes no advantage - so the Ahuizotl's own "
        "Tail Swat swings without it. The extra die below has no such limit, "
        "because `damage_bonus` is asked wherever this adversary rolls damage",
    ],
)
def aquatic_attacker(adversary, target, fight=None):
    """Advantage on every standard attack, because it is always in the water.

    SRD: "When the Ahuizotl attacks from the water, it has advantage on the attack
    and deals an extra 1d6 damage."

    SIMULATION RULE - policy, ruled. **The water is always to hand.** Nothing here
    records where a fight is happening, and the user ruled this the way Consume
    Kindling was ruled rather than declaring it a gap: the creature drowns victims
    in rivers and carries Swimming +2, so a GM placing one puts it in water, and
    the *availability* is the invented part rather than the effect. Declaring the
    clause, and authoring an aquatic flag on the encounter, were both offered and
    declined.

    Worth being plain about the size, since it is larger than Consume Kindling's:
    this is Advantage plus a die on **every** attack from the opening spotlight,
    not a resource that runs out.
    """
    return AdvantageState.ADVANTAGE


@damage_bonus(AQUATIC_ATTACKER)
def aquatic_attacker_bites_deeper(adversary, target, fight=None) -> int:
    """The extra 1d6, rolled and added before the target's thresholds.

    Registered on the same name as the Advantage above - one feature reaching two
    hooks. The die is **rolled here and returned as a flat number**, which is the
    only shape the GM side has for extra dice: `total_damage_bonus` sums integers,
    and `total_extra_damage` is never asked from `Adversary._damage_for`. What
    matters for the fight is unchanged - the die lands before the thresholds are
    read - and what is lost is that a play-by-play line reports the total rather
    than the dice. Midnight-Touched's Fear Die takes the same shape on the party's
    side.
    """
    return random.randint(1, AQUATIC_ATTACKER_DIE)


TAIL_SWAT = qualified(ADVERSARY, "Tail Swat")

TAIL_SWAT_DICE = 1
TAIL_SWAT_DIE = 8
TAIL_SWAT_MODIFIER = 2


@action(TAIL_SWAT)
def tail_swat(adversary, target, fight: Fight):
    """Mark a Stress: an attack within Very Close for 1d8+2.

    SRD: "Mark a Stress to make an attack against a target within Very Close
    range. On a success, deal 1d8+2 physical damage."

    Bigger than the Ahuizotl's printed Bite (1d6+2) and reaching a band further,
    which is what the Stress buys.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule decides when it is on the table. The Ahuizotl has 4 HP
    against three Stress, so the first is available from the opening spotlight.
    """
    if not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} lashes out with its tail (Tail Swat)")
    return adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=TAIL_SWAT_DICE, sides=TAIL_SWAT_DIE)],
        damage_modifier=TAIL_SWAT_MODIFIER,
        damage_type=DamageType.PHYSICAL,
    )


DRAG_AND_BAG = qualified(ADVERSARY, "Drag and Bag")

DRAG_AND_BAG_FEAR = 1


@action(
    DRAG_AND_BAG,
    unmodelled=[
        "'grab a target within Close range' and 'pull the target into Melee "
        "range' - both are repositioning, and no positions are tracked. What is "
        "modelled is the Restrain and the Advantage it buys",
    ],
)
def drag_and_bag(adversary, target, fight: Fight):
    """Spend a Fear to Restrain a target, and swing at them with Advantage after.

    SRD: "Spend a Fear to have the Ahuizotl grab a target within Close range with
    its tail, pull the target into Melee range, and temporarily *Restrain* them.
    The Ahuizotl has advantage on attacks against targets *Restrained* in this
    way."

    **This is the feature the Grab and Drag ruling exists for.** Restrained does
    nothing by itself here, so an earlier version of this project would have
    policied a card like this into never firing - and the standing rule is that a
    feature must never be policied dead because of a system the simulator leaves
    out. It is not dead in any case: the Advantage clause is real, and it is what
    the Fear actually buys.

    "Temporarily" on a **PC** lasts until their next rest, which is the whole
    fight - the standing reading, and the opposite of what a condition the party
    puts on an adversary gets. So the Restrain carries no ender.

    No attack roll: the card grabs rather than strikes, so this resolves into an
    activation with no roll behind it, the shape Spitter already has.

    USAGE POLICY - ruled. The standing default for a Fear cost: spent whenever the
    pool allows. Declines against a target this Ahuizotl already has hold of, per
    the standing don't-re-apply rule - a second grab would buy nothing.
    """
    if fight.fear < DRAG_AND_BAG_FEAR:
        return None

    held = fight.condition_on(target, RESTRAINED)
    if held is not None and held.source is adversary:
        return None
    if not fight.spend_fear(DRAG_AND_BAG_FEAR):
        return None

    fight.apply_condition(target, Condition(name=RESTRAINED, source=adversary))
    fight.note(
        f"{adversary.name} drags {target.name} down by the tail "
        f"(Drag and Bag: GM spends a Fear)"
    )
    return AttackResult(attack_roll=None, damage_roll=None)


@attack_advantage(DRAG_AND_BAG)
def drag_and_bag_holds_them(adversary, target, fight=None):
    """Advantage against whoever this Ahuizotl is holding.

    Registered on the same name as the action above. Scoped by the condition's
    **source**, so an Ahuizotl gets nothing from somebody else's hold - which also
    keeps two of them from sharing one grab.
    """
    if fight is None:
        return None

    held = fight.condition_on(target, RESTRAINED)
    if held is None or held.source is not adversary:
        return None
    return AdvantageState.ADVANTAGE


# --- Atotoll (SRD 2.0) -------------------------------------------------------

WIND_LORD = qualified(ADVERSARY, "Wind Lord")


@party_attack_disadvantage(WIND_LORD)
def wind_lord(adversary, attacker, target, weapon, fight=None) -> bool:
    """Attacks against this adversary are Disadvantaged, because it is airborne.

    SRD: "While the Atotoll is flying, attacks against it are made with
    disadvantage."

    SIMULATION RULE - policy, ruled. **The "while flying" qualifier belongs to the
    author**, which is the ruling `Flying (X)` already carries: nothing tracks
    whether a creature is currently in the air, so a stat block that carries this
    feature is one that spends the fight airborne, and a grounded variant simply
    drops it from its `features` list. Ruling it always-on as a *rule*, and
    declaring it a gap, were both offered and declined.

    Where it differs from `Flying (X)`: that one is a number and can be authored as
    an **average** uplift, so a creature airborne half the time is written
    `Flying (1)`. Disadvantage is a tri-state and cannot be averaged, so this is on
    or off per entry and nothing in between.

    `target is adversary` is load-bearing. Party-attack content is scanned across
    every living adversary, so without it one Atotoll on the field would hobble
    every attack the party made at anything.
    """
    return target is adversary


ARCHERS_BANE = qualified(ADVERSARY, "Archer's Bane")

ARCHERS_BANE_FEAR = 1

# "Beyond Close range" read off the attacker's weapon, the handle
# Armor-Shredding Shards, Fall Back and Overwhelm all already use.
BEYOND_CLOSE = (Range.FAR, Range.VERY_FAR)


@on_attacked(
    ARCHERS_BANE,
    unmodelled=[
        "Only a **weapon** attack reaches this. Content that rolls an attack of "
        "its own - a Grimoire spell, the Beastbound companion - has no weapon and "
        "so no range to read, and never triggers it. The gap Armor-Shredding "
        "Shards declares",
        "'would deal damage' is read as **did** deal damage: `on_attacked` is "
        "asked after the hit resolves, so the reflection answers a blow that "
        "landed rather than heading one off. What is lost is that the Atotoll "
        "still takes the damage it reflects",
    ],
)
def archers_bane(adversary, attacker, weapon, damage=0, hp_marked=0, fight=None) -> None:
    """Spend a Fear to throw a distant attacker's own damage back at them.

    SRD: "When a creature beyond Close range would deal damage to the Atotoll with
    a weapon attack, you can spend a Fear to make an attack roll against them. On a
    success, whirling winds reflect the attack and deal the attacker's damage back
    to them."

    **The first feature anywhere that deals somebody else's damage roll back.**
    Everything else that answers an attack rolls its own dice; this one carries the
    number that was just dealt, so a Wizard's big cast comes back exactly as big.

    "Beyond Close range" is read off the **attacker's weapon**, which is the
    standing handle for a range clause on this side of the table: everyone is
    assumed to have attacked from the greatest range their weapon allows, so a bow
    triggers it and a sword does not. That makes the Atotoll a specific answer to
    ranged parties, which is the shape it has on the page.

    The reflection is typed as the weapon's own, so a magic weapon's damage comes
    back magic and anything resisting it resists the reflection too.

    USAGE POLICY - ruled. A Reaction, so the standing rule applies - it fires on
    every trigger the Fear can pay for, and the Stress-desperation rule that gates
    Actions deliberately does not. Skipped on a hit that dealt nothing, per the
    standing zero-benefit rule: there would be no damage to send back.
    """
    if fight is None or damage <= 0:
        return
    if band_named(weapon.range) not in BEYOND_CLOSE:
        return
    if fight.fear < ARCHERS_BANE_FEAR:
        return
    if not fight.spend_fear(ARCHERS_BANE_FEAR):
        return

    roll = roll_d20(modifier=adversary.attack_modifier, evasion=attacker.evasion)
    if not roll.is_success:
        fight.note(
            f"{adversary.name}'s winds scatter around {attacker.name} ({roll})"
        )
        return

    attacker.take_damage(
        damage, fight, damage_type=getattr(weapon, "damage_type", None)
    )
    fight.note(
        f"{adversary.name} turns {attacker.name}'s own shot back on them "
        f"for {damage} (Archer's Bane: GM spends a Fear)"
    )


# --- Bugboar (SRD 2.0) -------------------------------------------------------

SURPRISE = qualified(ADVERSARY, "Surprise!")

SURPRISE_DIE = 8

# How many standard attacks this adversary has made, so "its first attack in a
# scene" can be answered. Counted rather than flagged because both halves of the
# feature have to agree on which attack is the first, and they are asked at two
# different moments of the same swing.
SURPRISE_ATTACKS = "Surprise! attacks made"


def _still_untouched(adversary) -> bool:
    """Whether nothing has marked this adversary's HP or Stress yet."""
    return adversary.hp_marked == 0 and adversary.stress_marked == 0


@attack_advantage(
    SURPRISE,
    unmodelled=[
        "Only standard attacks are counted, since `attack_advantage` is asked once "
        "per activation from `combat/policy.py` and an Action rolling its own "
        "attack is never offered it. The Bugboar has no attacking Action, so "
        "nothing is lost on this stat block",
    ],
)
def surprise(adversary, target, fight=None):
    """Advantage on this adversary's first attack, while it is still untouched.

    SRD: "If the Bugboar makes its first attack in a scene before it's marked HP or
    Stress, it has advantage on the attack and deals an extra 1d8 damage."

    The counter is incremented **here** rather than in the damage half, because
    this hook is asked once per attack whether it hits or misses - so a first
    attack that goes wide still spends the surprise, which is what "its first
    attack" says. Reading it off the damage hook instead would have handed the
    ambush to the second swing whenever the first one missed.

    No policy to rule on: it costs nothing, has no limit, and states its own
    trigger exactly.
    """
    if fight is None:
        return None

    made = fight.token_count(adversary, SURPRISE_ATTACKS) + 1
    fight.set_token(adversary, SURPRISE_ATTACKS, made)

    if made != 1 or not _still_untouched(adversary):
        return None
    fight.note(f"{adversary.name} comes out of nowhere (Surprise!)")
    return AdvantageState.ADVANTAGE


@damage_bonus(SURPRISE)
def surprise_hits_harder(adversary, target, fight=None) -> int:
    """The extra 1d8 on that same first attack.

    Registered on the same name as the Advantage above and reading the same
    counter, which is already at 1 by the time this is asked - `attack_advantage`
    runs before the roll and this runs after the hit is known, both within one
    swing.
    """
    if fight is None:
        return 0
    if fight.token_count(adversary, SURPRISE_ATTACKS) != 1:
        return 0
    if not _still_untouched(adversary):
        return 0
    return random.randint(1, SURPRISE_DIE)


BRUTAL = qualified(ADVERSARY, "Brutal")

BRUTAL_DIE = 6


@damage_bonus(BRUTAL)
def brutal(adversary, target, fight=None) -> int:
    """Mark a Stress on a landed attack for an extra 1d6.

    SRD: "When the Bugboar makes a successful standard attack, mark a Stress to
    deal an extra 1d6 damage."

    Asked after the hit is known and before the damage is rolled, which is exactly
    the window the trigger describes - so the Stress is never spent on a miss.

    USAGE POLICY - ruled. A Reaction, so it fires on every trigger it can pay for
    and consults `can_spend_stress` rather than the Stress-desperation rule that
    gates Actions. Three Stress on a 5 HP Bruiser means the first three landed
    attacks each carry the extra die, from full health.
    """
    if fight is None or not adversary.can_spend_stress(1):
        return 0

    adversary.spend_stress(1)
    rolled = random.randint(1, BRUTAL_DIE)
    fight.note(f"{adversary.name} puts its weight behind it (Brutal: +{rolled})")
    return rolled


WARHEART = qualified(ADVERSARY, "Warheart")

WARHEART_FEAR = 1


@condition_refusal(WARHEART)
def warheart(adversary, condition, fight=None) -> bool:
    """Spend a Fear to shrug off a condition as it lands.

    SRD: "When a condition would be imposed on the Bugboar, you can spend a Fear to
    negate it."

    **Bold Presence's mirror across the table**, and the first GM-side registrant
    on `condition_refusal`. It is asked from `FightState.apply_condition`, which is
    the one moment "when a condition would be imposed" happens - and only for a
    condition the Bugboar does not already carry, since a refresh is not gaining
    one.

    Worth knowing what it is worth here: the party's conditions on an adversary are
    mostly Vulnerable and Restrained, and Vulnerable is the one that matters, so
    this is largely a Fear spent to keep the party from handing themselves
    Advantage.

    USAGE POLICY - ruled. A Reaction, so the standing rule applies: spent on every
    condition the Fear can pay for, with no threshold. Holding it for a worse
    condition would be inventing foresight, which is the same reasoning Bold
    Presence's own ruling gives.
    """
    if fight is None or fight.fear < WARHEART_FEAR:
        return False
    if not fight.spend_fear(WARHEART_FEAR):
        return False

    fight.note(
        f"{adversary.name} shrugs off {condition.name} "
        f"(Warheart: GM spends a Fear)"
    )
    return True


# --- Common Ruffian (SRD 2.0) ------------------------------------------------

SURVIVAL_INSTINCT = qualified(ADVERSARY, "Survival Instinct")

SURVIVAL_INSTINCT_DIE = 6
SURVIVAL_INSTINCT_FLEES_AT = 4

# Rolled once, the first time the Ruffian is half down. The trigger is a threshold
# being crossed rather than a state being held, so without this it would re-roll on
# every wound after the first.
SURVIVAL_ROLLED = "Survival Instinct rolled"


@on_damaged(SURVIVAL_INSTINCT)
def survival_instinct(
    adversary, amount, hp_marked, fight=None, marked_armor=False, damage_type=None
) -> None:
    """At half HP, a d6: the Ruffian runs, or the GM banks a Fear.

    SRD: "When the Ruffian marks half their HP, roll a d6. On a result of 4 or
    higher, the Ruffian flees the scene. Otherwise, you gain a Fear."

    SIMULATION RULE - rules interpretation, ruled. **Fleeing is modelled as being
    defeated** - its HP is marked out and it leaves the fight by the ordinary
    route. `FightState.remove` exists for exactly this shape (the Green Ooze's
    Split takes an adversary off the field without defeating it) and was offered;
    the user ruled the simpler way. The cost is recorded rather than hidden: **a
    Ruffian that runs is reported as a kill the party did not make**, and any
    future statistic counting adversaries defeated will count it.

    Rolled **once**, on the wound that first takes it to half - the trigger is a
    line being crossed, not a state, so without the token every later hit would
    roll again.

    No policy to rule on. It costs nothing, has no limit, and both outcomes are the
    page's own. Note which way the odds run: a d6 at 4 or higher is even money, and
    the half that does not flee hands the GM a Fear - so the feature is good for
    the GM either way, which is unusual for something that reads as cowardice.
    """
    if fight is None or hp_marked <= 0:
        return
    if adversary.hp_marked * 2 < adversary.hp_max:
        return
    if fight.token_count(adversary, SURVIVAL_ROLLED):
        return

    fight.set_token(adversary, SURVIVAL_ROLLED, 1)
    if random.randint(1, SURVIVAL_INSTINCT_DIE) >= SURVIVAL_INSTINCT_FLEES_AT:
        adversary.mark_hp(adversary.hp_max)
        fight.note(f"{adversary.name} breaks and runs (Survival Instinct)")
        return

    fight.gain_fear(1)
    fight.note(
        f"{adversary.name} holds their ground (Survival Instinct: GM gains a Fear)"
    )


# --- The Darkweaves (SRD 2.0) ------------------------------------------------
#
# Four stat blocks that arrive as one encounter: a Queen who summons the others,
# Crawlers that swarm, a Spinner that webs, and Swarmlings that get everywhere.
# Four of their features needed no code at all - Minion (3), Group Attack,
# Relentless (3) and Horde (1d4) were all already generic - and what is new is
# mostly **conditions with a printed way out**, which is the shape this family has.


def _escapes_on(trait: str, difficulty: int, also_clear: tuple = ()):
    """A condition that lifts when its holder makes the printed Reaction Roll.

    The standing rule for a condition the page gives an escape from: it is a
    Reaction Roll the affected PC attempts at each announced moment, rather than a
    declared gap. `WHEN_THEY_ACT` is the moment, so a held PC gets one attempt each
    time the spotlight reaches them.

    `also_clear` exists because three of these features apply **two** conditions
    lifted by **one** roll - "Vulnerable and Restrained until they succeed on a
    Strength Roll (10)". Each condition carries its own `end`, so giving both the
    roll would make the PC roll twice for one escape. Instead the Restrain carries
    it and clears the Vulnerable alongside itself. The consequence, declared rather
    than hidden: something that lifted the Restrain by another route would leave
    the Vulnerable behind, and nothing does that today.
    """

    def ends(holder, fight, moment: str) -> bool:
        if fight is None or moment != WHEN_THEY_ACT:
            return False

        roll = _reaction_roll(holder, trait, difficulty, fight)
        if not roll.is_success:
            return False

        for name in also_clear:
            fight.clear_condition(holder, name)
        return True

    return ends


def _web_them(adversary, target, fight: Fight, difficulty: int, feature: str) -> None:
    """Vulnerable *and* Restrained, lifted together by one Strength Roll.

    Shared by the Spinner's *Wrap in Shadow-Silk* and the Queen's *Darkfang
    Envenomation*, which print the same pair at two different Difficulties. Both
    are sourced to the adversary that applied them, so two Darkweaves cannot share
    one web.
    """
    fight.apply_condition(target, Condition(name=VULNERABLE, source=adversary))
    fight.apply_condition(
        target,
        Condition(
            name=RESTRAINED,
            end=_escapes_on("strength", difficulty, also_clear=(VULNERABLE,)),
            source=adversary,
        ),
    )
    fight.note(
        f"{target.name} is wrapped in shadow-silk by {adversary.name} ({feature})"
    )


SKIN_CRAWLING = qualified(ADVERSARY, "Skin-Crawling")

SKIN_CRAWLING_FEAR = 1

# SIMULATION RULE - policy, ruled. Group Attack's floor read here rather than a
# second number that could drift: a Fear spent to put one Stress on one PC is
# thin, and the Crawler's own Group Attack is competing for the same Fear.
SKIN_CRAWLING_WORTH_IT = 2


@action(
    SKIN_CRAWLING,
    unmodelled=[
        "'all PCs within Melee range of the Crawler' - no positions are tracked, "
        "so the area rule decides how much of the party a single Crawler is on top "
        "of",
    ],
)
def skin_crawling(adversary, target, fight: Fight):
    """Spend a Fear: everybody the Melee band reaches marks a Stress.

    SRD: "Spend a Fear to force all PCs within Melee range of the Crawler to mark a
    Stress."

    No attack roll - the Fear buys the effect outright, which is Rune Circle's
    shape on the other side of the table. The Stress is **forced**, so a PC with a
    full track marks a Hit Point instead.

    USAGE POLICY - ruled. Declines below `SKIN_CRAWLING_WORTH_IT` PCs in the band,
    which is Group Attack's floor: below that a Fear buys a single Stress, and this
    Crawler's other Action wants the same Fear.
    """
    if fight.fear < SKIN_CRAWLING_FEAR:
        return None

    caught = targets_in_area(Range.MELEE, fight.conscious_party)
    if len(caught) < SKIN_CRAWLING_WORTH_IT:
        return None
    if not fight.spend_fear(SKIN_CRAWLING_FEAR):
        return None

    for pc in caught:
        pc.mark_stress(1)
    fight.note(
        f"{adversary.name} swarms over {len(caught)} of the party "
        f"(Skin-Crawling: GM spends a Fear)"
    )
    return AttackResult(attack_roll=None, damage_roll=None)


DARKWEAVE_VENOM = qualified(ADVERSARY, "Darkweave Venom")

DARKWEAVE_VENOM_ESCAPE = 9


def _exhaustion_bites(holder, fight, moment: str) -> None:
    """The Stress *Exhausted* charges before each of its holder's action rolls."""
    if moment != BEFORE_AN_ACTION_ROLL:
        return

    holder.mark_stress(1)
    fight.note(f"{holder.name} drags themselves through it (Exhausted: a Stress)")


@on_hit(DARKWEAVE_VENOM)
def darkweave_venom(adversary, target, result, fight: Fight) -> None:
    """Mark a Stress on a landed bite to leave the target *Exhausted*.

    SRD: "When the Crawler makes a successful attack, you can mark a Stress to
    *Exhaust* the target until they succeed on a Strength Roll (9). While
    *Exhausted*, the target must mark a Stress each time they make an action roll."

    **The most expensive condition the party can be under.** The Giant Scorpion's
    Poison rolls a d6 first and charges on a 4 or lower; this simply charges, every
    action roll, until the PC rolls their way out - so it is a tax on doing
    anything at all.

    A Minion with a single Stress slot pays for it, which is the whole cost: a
    Crawler that venoms somebody has spent itself and cannot do it again.

    USAGE POLICY - ruled. A Reaction, so it fires on every trigger it can pay for
    and asks `can_spend_stress` rather than the desperation rule that gates
    Actions. Declines against a target already Exhausted, per the standing
    don't-re-apply rule.
    """
    if fight is None or result.damage_roll is None:
        return
    if fight.has_condition(target, EXHAUSTED):
        return
    if not adversary.can_spend_stress(1):
        return

    adversary.spend_stress(1)
    fight.apply_condition(
        target,
        Condition(
            name=EXHAUSTED,
            end=_escapes_on("strength", DARKWEAVE_VENOM_ESCAPE),
            effect=_exhaustion_bites,
            source=adversary,
        ),
    )
    fight.note(f"{target.name} is Exhausted by darkweave venom")


# SRD 2.0 prints **two different features called Terrifying**: the Skeleton
# Knight's fires on the Knight's own successful attack, and the Darkweave Queen's
# on a PC's failed attack roll. Dispatch matches on the base name, so without
# something to tell them apart each stat block would run both rules.
#
# SIMULATION RULE - ruled. **The variant is named in the parameter**, which is
# `Flying (X)`'s arrangement: the bare `Terrifying` is the Skeleton Knight's, and
# the Queen's entry writes `Terrifying (Miss)`. Each half checks the parameter and
# declines when it is not theirs, so one name serves both and a homebrew stat block
# picks whichever it wants by writing it. Scoping the registration to a stat block
# name was offered and declined - it would have kept the catalogue verbatim to the
# page, but left homebrew unable to ask for the Queen's version at all.
TERRIFYING_ON_A_MISS = "Miss"


@attack_missed(TERRIFYING)
def terrifying_on_a_miss(adversary, attacker, roll, fight: Fight = None) -> None:
    """Every attack that comes up short against this adversary banks the GM a Fear.

    SRD: "When a PC fails an attack roll against the Queen, you gain a Fear."

    Registered against the same base name as the Skeleton Knight's *Terrifying* and
    told apart by the parameter - see the note above. A stat block writing the bare
    name gets the Knight's rule and this declines.

    **This is `attack_missed`'s second call site.** The hook has always meant "the
    target's own content answers an attack that failed against them", and until now
    only the GM turn announced it - so it could only ever hear about an adversary
    missing a PC. `items/weapons.py` now announces it too, which costs no new hook
    and makes the two sides symmetric, exactly as `on_hit` already fires from both.

    Note what it does to the fight rather than to the roll: a high Difficulty
    already makes the Queen hard to hit, and this makes every miss *pay* the GM -
    so the party's bad luck buys extra activations for a Solo that is Relentless (3).

    No policy to rule on: it costs nothing, has no limit and states its own trigger.
    """
    if fight is None:
        return

    written = feature_parameter(adversary, TERRIFYING)
    if written is None or canonical(written) != canonical(TERRIFYING_ON_A_MISS):
        return

    fight.gain_fear(1)
    fight.note(f"{attacker.name}'s nerve fails them ({adversary.name}: Terrifying)")


DEN_MOTHER = qualified(ADVERSARY, "Den Mother")

DEN_MOTHER_FEAR = 2
DEN_MOTHER_SUMMONS = 2

# "Darkweave adversaries (other than Darkweave Queens)" - the brood, by name.
DEN_MOTHER_BROOD = (
    "Darkweave Crawler",
    "Darkweave Spinner",
    "Darkweave Swarmlings",
)

DEN_MOTHER_CALLED = "Den Mother called"


@action(
    DEN_MOTHER,
    unmodelled=[
        "'who appear within Close range' - no positions are tracked, so they simply "
        "arrive",
    ],
)
def den_mother(adversary, target, fight: Fight):
    """Once per scene, 2 Fear buys two more Darkweaves who act immediately.

    SRD: "Once per scene, spend 2 Fear to summon up to two Darkweave adversaries
    (other than Darkweave Queens), who appear within Close range and immediately
    take the spotlight."

    SIMULATION RULE - policy, ruled. **Two drawn at random from the brood, and
    their spotlights are free.** Random among viable is the standing rule - picking
    the scariest would be scoring the field on the party's behalf - and the free
    activations are *Voice of the Forest*'s shape: the 2 Fear has already bought
    them, so charging again for the spotlight would charge twice for one feature.
    Free means outside both the Fear cost and the party-size+1 cap. Making them
    cost as usual, and always summoning Crawlers, were both offered and declined.

    Worth watching when this is run: the Queen is **Relentless (3)** as well, so a
    turn where she calls the brood can run to six activations against a party of
    four, and two of them are free.

    Once per **scene**, which is a fight - so a token rather than a per-rest use,
    since a per-rest use would wrongly survive into the next encounter unspent.
    """
    if fight.token_count(adversary, DEN_MOTHER_CALLED):
        return None
    if fight.fear < DEN_MOTHER_FEAR:
        return None

    brood = [found for name in DEN_MOTHER_BROOD if (found := find_adversary(name))]
    if not brood:
        return None
    if not fight.spend_fear(DEN_MOTHER_FEAR):
        return None

    fight.set_token(adversary, DEN_MOTHER_CALLED, 1)
    called = []
    for _ in range(DEN_MOTHER_SUMMONS):
        spawned = random.choice(brood).spawn()
        fight.summon(spawned)
        fight.grant_activation(spawned, free=True)
        called.append(spawned.name)

    fight.note(
        f"{adversary.name} calls her brood: {', '.join(called)} "
        f"(Den Mother: GM spends {DEN_MOTHER_FEAR} Fear)"
    )
    return AttackResult(attack_roll=None, damage_roll=None)


QUICKER_THAN_SHE_LOOKS = qualified(ADVERSARY, "Quicker Than She Looks")

QUICKER_THAN_SHE_LOOKS_FEAR = 1


@action(
    QUICKER_THAN_SHE_LOOKS,
    unmodelled=[
        "'move up to Far range' - repositioning, and no positions are tracked. What "
        "is modelled is the attack the move sets up, which is the half the Fear is "
        "really spent on",
    ],
)
def quicker_than_she_looks(adversary, target, fight: Fight):
    """Spend a Fear for a standard attack with Advantage.

    SRD: "Spend a Fear to move up to Far range and make a standard attack with
    advantage."

    The Queen's printed attack is 1d12+4 at +3, so Advantage on it is a large
    thing to buy for one Fear - and unlike most Actions it costs her nothing of her
    own.

    USAGE POLICY - ruled. The standing default for a Fear cost: spent whenever the
    pool allows. There is no state where swinging with Advantage is worse than
    swinging without, so no threshold applies.
    """
    if fight.fear < QUICKER_THAN_SHE_LOOKS_FEAR:
        return None
    if not fight.spend_fear(QUICKER_THAN_SHE_LOOKS_FEAR):
        return None

    fight.note(
        f"{adversary.name} is on {target.name} before they see her "
        f"(Quicker Than She Looks: GM spends a Fear)"
    )
    return adversary.attack(target, AdvantageState.ADVANTAGE, fight)


DARKFANG_ENVENOMATION = qualified(ADVERSARY, "Darkfang Envenomation")

DARKFANG_FEAR = 1
DARKFANG_ESCAPE = 12


@on_hit(
    DARKFANG_ENVENOMATION,
    unmodelled=[
        "'or take a rest' - the second way out. A rest happens between fights and "
        "the condition does not outlive one, so the escape roll is the only ender "
        "that ever bites",
    ],
)
def darkfang_envenomation(adversary, target, result, fight: Fight) -> None:
    """Spend a Fear on a landed bite: Vulnerable and Restrained at once.

    SRD: "When the Queen succeeds on a standard attack, you can spend a Fear to
    make the target *Vulnerable* and *Restrained* until they succeed on a Strength
    Roll (12) or take a rest."

    The hardest escape roll in tier 1 - a flat Strength Roll against 12 - and what
    it holds back is the Vulnerable, since Restrained does nothing by itself here.
    Both lift together on one roll; see `_escapes_on`.

    USAGE POLICY - ruled. A Reaction, so the standing rule applies: spent on every
    landed standard attack the Fear can pay for. Declines against a target already
    held, per the standing don't-re-apply rule - a second web would refresh nothing
    and cost a Fear.
    """
    if fight is None or result.damage_roll is None:
        return
    if fight.has_condition(target, RESTRAINED):
        return
    if fight.fear < DARKFANG_FEAR or not fight.spend_fear(DARKFANG_FEAR):
        return

    _web_them(adversary, target, fight, DARKFANG_ESCAPE, "Darkfang Envenomation")


WRAP_IN_SHADOW_SILK = qualified(ADVERSARY, "Wrap in Shadow-Silk")

WRAP_IN_SHADOW_SILK_ESCAPE = 10


@action(WRAP_IN_SHADOW_SILK)
def wrap_in_shadow_silk(adversary, target, fight: Fight):
    """Mark a Stress: an attack that webs whoever it lands on.

    SRD: "Mark a Stress to make an attack against a target within Melee range. On a
    success, the target is *Vulnerable* and *Restrained* until they succeed on a
    Strength Roll (10)."

    The Queen's Darkfang Envenomation at a lower Difficulty and a lower price - a
    Stress rather than a Fear - which is the Spinner's whole role in the family.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule decides when it is on the table. Declines against a
    target already held, per the standing don't-re-apply rule, so the Stress is
    never spent re-webbing somebody.
    """
    if fight.has_condition(target, RESTRAINED):
        return None
    if not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} spins a snare at {target.name} (Wrap in Shadow-Silk)")
    result = adversary.attack(target, fight=fight)
    if result.damage_roll is None:
        return result

    _web_them(adversary, target, fight, WRAP_IN_SHADOW_SILK_ESCAPE, "Wrap in Shadow-Silk")
    return result


SHADOW_FANG = qualified(ADVERSARY, "Shadow Fang")

SHADOW_FANG_FEAR = 1
SHADOW_FANG_ESCAPE = 10


@on_hit(
    SHADOW_FANG,
    unmodelled=[
        "'against a target within Melee range' - no positions are tracked. The "
        "Spinner's printed attack is Melee, so every standard attack it lands "
        "qualifies and nothing is lost on this stat block",
    ],
)
def shadow_fang(adversary, target, result, fight: Fight) -> None:
    """Spend a Fear on a landed bite to leave the target *Shaky*.

    SRD: "When the Spinner makes a successful attack against a target within Melee
    range, you can spend a Fear to make the target *Shaky* until they succeed on an
    Instinct Roll (10). While *Shaky*, the target has disadvantage on attack rolls."

    **Vulnerable's mirror, pointed the other way.** Every condition the GM has
    applied so far changes how rolls against its holder go; this one changes the
    holder's own swings, which is a shape the party side had (Hidden) and the GM
    side did not.

    USAGE POLICY - ruled. A Reaction, so it fires on every trigger the Fear can pay
    for. Declines against a target already Shaky, per the standing don't-re-apply
    rule.
    """
    if fight is None or result.damage_roll is None:
        return
    if fight.has_condition(target, SHAKY):
        return
    if fight.fear < SHADOW_FANG_FEAR or not fight.spend_fear(SHADOW_FANG_FEAR):
        return

    fight.apply_condition(
        target,
        Condition(
            name=SHAKY,
            end=_escapes_on("instinct", SHADOW_FANG_ESCAPE),
            source=adversary,
        ),
    )
    fight.note(f"{target.name}'s hands won't steady ({adversary.name}: Shadow Fang)")


@party_attack_disadvantage(SHADOW_FANG)
def shadow_fang_shakes_them(adversary, attacker, target, weapon, fight=None) -> bool:
    """The Disadvantage *Shaky* puts on its holder's attacks.

    Registered on the same name as the reaction above. The condition carries no
    machinery of its own - it is the record that the state is on - and this reads
    it, which is Dread's *Chains of Affliction* arrangement.

    Scoped by the condition's **source**, so a second Spinner gets no credit for
    the first one's bite. Note it hobbles the PC's attack at **anything**, not only
    at the Spinner, which is what the card says.
    """
    if fight is None:
        return False

    shaky = fight.condition_on(attacker, SHAKY)
    return shaky is not None and shaky.source is adversary


GET_EM_OFF = qualified(ADVERSARY, "Get 'em Off, Get 'em Off!")

COVERED_IN_SPIDERS_DIE = 6
COVERED_IN_SPIDERS_FEEDS_AT = 4


def _spiders_crawl(holder, fight, moment: str) -> None:
    """The d6 *Covered in Spiders* rolls before each of its holder's action rolls."""
    if moment != BEFORE_AN_ACTION_ROLL:
        return
    if random.randint(1, COVERED_IN_SPIDERS_DIE) < COVERED_IN_SPIDERS_FEEDS_AT:
        return

    fight.gain_fear(1)
    fight.note(f"{holder.name} claws at the spiders (Covered in Spiders: a Fear)")


@on_hit(GET_EM_OFF)
def get_em_off(adversary, target, result, fight: Fight) -> None:
    """Mark a Stress on a wound to leave the target Covered in Spiders.

    SRD: "When an attack from the Swarmlings causes a target to mark HP, you can
    mark a Stress to make the target temporarily *Covered in Spiders*. While
    *Covered in Spiders*, the target must roll a d6 when they make an action roll.
    On a result of 4 or higher, they must mark a Stress or you gain a Fear."

    SIMULATION RULE - policy, ruled. **The GM always takes the Fear.** The card
    offers a choice and says nothing about making it; the user ruled it to the Fear
    outright rather than reading it as the PC's call. So the condition never touches
    the PC's Stress track and instead feeds the GM's pool - which makes it the
    first condition anywhere whose payload is Fear, and worth roughly half a Fear
    per action roll for the rest of the fight. Marking the Stress while the shared
    last-slot rule allowed it, and always marking the Stress, were both offered and
    declined.

    Keyed on **HP actually marked** rather than on damage dealt, which is what the
    trigger says - a hit an Armor Slot swallowed caused nobody to mark anything.
    Bloodsucker reads its own trigger the same way.

    "Temporarily" on a PC is the whole fight, the standing reading, so this carries
    no ender at all.

    USAGE POLICY - ruled. A Reaction, so it fires on every trigger it can pay for.
    Declines against a target already covered, per the standing don't-re-apply rule.
    """
    if fight is None or not result.hp_marked:
        return
    if fight.has_condition(target, COVERED_IN_SPIDERS):
        return
    if not adversary.can_spend_stress(1):
        return

    adversary.spend_stress(1)
    fight.apply_condition(
        target,
        Condition(
            name=COVERED_IN_SPIDERS,
            effect=_spiders_crawl,
            source=adversary,
        ),
    )
    fight.note(f"{target.name} is covered in spiders ({adversary.name})")


# --- The Redcaps (SRD 2.0) ---------------------------------------------------
#
# Five fey murderers who work as a pack: Biters underfoot, Skinners in numbers, a
# Butcher and a Breaker doing the work, and a Candlemaker whose lantern makes all
# of them hit harder. The Candlemaker is the reason `ally_damage_bonus` exists -
# it is the first thing in the catalogue whose effect lands on somebody else's
# damage roll.

BACKBREAKER = qualified(ADVERSARY, "Backbreaker")

BACKBREAKER_DICE = 3
BACKBREAKER_DIE = 4
BACKBREAKER_MODIFIER = 10


@action(BACKBREAKER)
def backbreaker(adversary, target, fight: Fight):
    """Mark a Stress: 3d4+10, and a Restrain that only healing lifts.

    SRD: "Mark a Stress to make an attack against a target within Melee range. On
    a success, deal 3d4+10 physical damage. A target who marks HP from this attack
    is *Restrained* until they clear a HP."

    The Dire Wolf's *Hobbling Strike* pointed at Restrained instead of Vulnerable,
    and with the same ender - `until_they_clear_hp`, measured **after** the hit so
    the HP this attack just marked is part of what has to be cleared. Unlike the
    SRD's usual "until they next act" it does not wear off on its own.

    Keyed on Hit Points actually marked rather than on the attack landing, which
    is what the trigger says: a hit an Armor Slot swallowed entirely leaves nobody
    to hold.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule decides when it is on the table.
    """
    if not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} swings low at {target.name} (Backbreaker)")
    result = adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=BACKBREAKER_DICE, sides=BACKBREAKER_DIE)],
        damage_modifier=BACKBREAKER_MODIFIER,
        damage_type=DamageType.PHYSICAL,
    )
    if not result.hp_marked:
        return result

    fight.apply_condition(
        target,
        Condition(
            name=RESTRAINED,
            end=until_they_clear_hp(target.hp_marked),
            source=adversary,
        ),
    )
    fight.note(f"{target.name} goes down hard, and stays down until they heal")
    return result


KNEECAPPER = qualified(ADVERSARY, "Kneecapper")

KNEECAPPER_FEAR = 1


@on_hit(KNEECAPPER)
def kneecapper(adversary, target, result, fight: Fight) -> None:
    """Spend a Fear on a landed standard attack to leave the target Vulnerable.

    SRD: "When the Breaker makes a successful standard attack, you can spend a
    Fear to make the target temporarily *Vulnerable*."

    "Temporarily" on a **PC** lasts until their next rest, which is the whole
    fight - the standing reading, and the opposite of what a condition the party
    puts on an adversary gets. So it carries no ender and the Fear buys the rest of
    the fight.

    USAGE POLICY - ruled. A Reaction, so the standing rule applies: spent on every
    landed attack the Fear can pay for. Declines against a target already
    Vulnerable, per the standing don't-re-apply rule.
    """
    if fight is None or result.damage_roll is None:
        return
    if fight.has_condition(target, VULNERABLE):
        return
    if fight.fear < KNEECAPPER_FEAR or not fight.spend_fear(KNEECAPPER_FEAR):
        return

    fight.apply_condition(target, Condition(name=VULNERABLE, source=adversary))
    fight.note(
        f"{adversary.name} takes {target.name}'s knee out "
        f"(Kneecapper: GM spends a Fear)"
    )


CHOP_HAPPY = qualified(ADVERSARY, "Chop Happy")

# "Up to three targets" - the card's own ceiling on what the band delivers.
CHOP_HAPPY_TARGETS = 3


@action(
    CHOP_HAPPY,
    unmodelled=[
        "'up to three targets' names no range, so the Butcher's own printed band "
        "answers it - Melee, which is what its Meat Cleaver reaches. The area rule "
        "then decides how many of the party are in it",
    ],
)
def chop_happy(adversary, target, fight: Fight):
    """Mark a Stress: one shared swing at up to three, and a Fear for each it wounds.

    SRD: "Mark a Stress to make a standard attack against up to three targets. For
    each target who marks HP, you gain a Fear."

    SIMULATION RULE - policy, ruled. **The Melee band, capped at three.** The card
    names no range of its own, and the user ruled it to the Butcher's printed one -
    its standard attack is Melee, and this is a standard attack. So the area rule
    answers how many of the party are close enough and the card's own ceiling
    trims it, which is Ramp Up's and Hail of Boulders' shape.

    One roll against everyone caught, each checked against their own Evasion - the
    standard area-attack shape on this side of the table.

    **The Fear is per target wounded**, not per target hit, which is the card's own
    wording: a swing an Armor Slot swallowed pays nothing. Against a bunched party
    that is up to three Fear from one Stress, which is the largest Fear return any
    tier 1 Action offers.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule decides when it is on the table. Declines when the band
    reaches nobody.
    """
    if not adversary.will_spend_stress(1):
        return None

    caught = targets_in_area(Range.MELEE, fight.conscious_party)[:CHOP_HAPPY_TARGETS]
    if not caught:
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} wades in, cleaver swinging (Chop Happy)")

    # Read before the swing, because the Fear is owed for Hit Points **this
    # attack** marked - a PC who walked in already wounded is not proof of
    # anything. `area_attack` returns one combined total rather than a figure per
    # target, so the comparison has to be made here.
    before = {id(pc): pc.hp_marked for pc in caught}
    result, struck = adversary.area_attack(caught, fight=fight)

    gained = 0
    for pc in struck:
        if pc.hp_marked > before[id(pc)]:
            gained += fight.gain_fear(1)
    if gained:
        fight.note(f"{adversary.name} draws blood ({gained} Fear)")
    return result


KNIFE_THROWER = qualified(ADVERSARY, "Knife Thrower")


@action(KNIFE_THROWER)
def knife_thrower(adversary, target, fight: Fight):
    """Mark a Stress for a standard attack at Far, with Advantage while Hidden.

    SRD: "Mark a Stress to make a standard attack against a target within Far
    range. If the Butcher is *Hidden*, they make the attack with advantage."

    What it buys is **reach**: the Butcher's printed attack is Melee, and no
    positions are tracked, so the range half changes nothing here - which is worth
    saying plainly rather than pretending the Stress bought something.

    The Advantage half is real and is read off the condition. Nothing on this stat
    block makes the Butcher Hidden, so it fires only when something else does -
    which in a Redcap pack is the Candlemaker's *Hand of Glory* lighting the
    Butcher's own hiding place, or a future feature.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule decides when it is on the table.
    """
    if not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    advantage = (
        AdvantageState.ADVANTAGE
        if fight is not None and fight.is_hidden(adversary)
        else AdvantageState.NONE
    )
    fight.note(f"{adversary.name} sends a knife at {target.name} (Knife Thrower)")
    return adversary.attack(target, advantage, fight)


HAND_OF_GLORY = qualified(ADVERSARY, "Hand of Glory")

HAND_OF_GLORY_TOKENS = 5

# The candles still burning, held on the stat block. While any remain the
# Candlemaker is Hidden and its pack hits harder.
GLORY_TOKENS = "Hand of Glory candles"

# Set once the five have been placed, so a Candlemaker whose candles have all gone
# out is not handed five more the next time anything looks. A count of zero has to
# mean "spent" rather than "never placed".
GLORY_PLACED = "Hand of Glory placed"


def _glory_lit(adversary, fight: Fight) -> int:
    """How many candles are burning, placing them the first time it is asked.

    "When the Candlemaker appears" is the start of the fight, and there is no
    moment announced for an adversary arriving - so the tokens are placed lazily
    the first time anything looks, which is Strategic Approach's arrangement on the
    party's side. A second token records that they have been placed, so a
    Candlemaker whose candles have all gone out is not handed five more.
    """
    if fight is None:
        return 0
    if not fight.token_count(adversary, GLORY_PLACED):
        fight.set_token(adversary, GLORY_PLACED, 1)
        fight.set_token(adversary, GLORY_TOKENS, HAND_OF_GLORY_TOKENS)
    return fight.token_count(adversary, GLORY_TOKENS)


@on_damaged(HAND_OF_GLORY)
def hand_of_glory(
    adversary, amount, hp_marked, fight=None, marked_armor=False, damage_type=None
) -> None:
    """A candle gutters out for every Hit Point the Candlemaker marks.

    SRD: "When the Candlemaker appears, place 5 tokens on this stat block. Remove a
    token whenever the Candlemaker marks a HP. While this stat block has 1 or more
    tokens on it, the Candlemaker is *Hidden*."

    **Five candles against six Hit Points**, so in practice the Candlemaker is
    Hidden for nearly the whole of its life and stops being so on the blow that
    very nearly finishes it. Hidden is modelled outright here - every roll against
    a hidden combatant has Disadvantage - which makes this the largest defensive
    passive in tier 1.

    One token per Hit Point marked rather than per wound: a hit that marks three
    puts out three candles, which is what "whenever the Candlemaker marks a HP"
    says read literally.

    The *Hidden* itself is applied here rather than carried as a standing state,
    because the condition is what `FightState.is_hidden` reads and the tokens are
    what decide it.
    """
    if fight is None or hp_marked <= 0:
        return

    lit = max(_glory_lit(adversary, fight) - hp_marked, 0)
    fight.set_token(adversary, GLORY_TOKENS, lit)

    if lit:
        fight.note(f"{adversary.name}'s hand of glory gutters ({lit} candles left)")
        return

    fight.clear_condition(adversary, HIDDEN)
    fight.note(f"{adversary.name}'s last candle goes out, and the shadows drop")


@on_spotlight(HAND_OF_GLORY)
def hand_of_glory_lights(adversary, fight=None) -> None:
    """Keep the Candlemaker Hidden for as long as a candle burns.

    Registered on the same name as the damage response above. Asked at every one of
    this adversary's spotlights, which is also the first moment anything looks at
    the stat block - so this is where the five candles get placed.
    """
    if fight is None:
        return
    if not _glory_lit(adversary, fight):
        return
    if fight.has_condition(adversary, HIDDEN):
        return

    fight.apply_condition(adversary, Condition(name=HIDDEN, source=adversary))
    fight.note(f"{adversary.name} keeps to the candlelight ({HIDDEN})")


TORCHBEARER = qualified(ADVERSARY, "Torchbearer")

TORCHBEARER_BONUS = 1

# Matched canonically on part of a name, the way ZOMBIE already is - the card says
# "each **Redcap** adversary", which is a kind rather than a stat block.
REDCAP = canonical("Redcap")


@ally_damage_bonus(TORCHBEARER)
def torchbearer(adversary, attacker, target, fight=None) -> int:
    """The +1 the Candlemaker's light puts on every nearby Redcap's damage.

    SRD: "The light of the Candlemaker's Hand of Glory inspires bloodlust in their
    allies. While this stat block has 1 or more tokens on it, each Redcap adversary
    within Close range gains a +1 bonus to their damage rolls."

    **The first thing in the catalogue whose effect lands on another adversary's
    damage roll**, and the reason `ally_damage_bonus` exists - `damage_bonus` is
    holder-scoped and could only ever reach the Candlemaker's own swings. The
    party's side has had the same shape since Breaking Blow.

    SIMULATION RULE - policy, ruled. **"Within Close range" is the area rule**, the
    standing answer for a range clause, asked per damage roll through
    `chance_within` - so whether a given Redcap is standing in the light is
    re-rolled each time it swings, exactly as Natural Familiar's d6 is. The field it
    is measured over is the rest of the GM's side rather than the party, since that
    is who the band has to reach.

    "Each **Redcap** adversary" is matched on part of a name, the third feature in
    the catalogue to do so after *Too Many to Handle*'s Zombies and *No Quarter*'s
    Pirates - and it correctly excludes the Candlemaker itself, since the card says
    *their allies*.

    Gone the moment the last candle does, which ties the pack's damage to how badly
    the Candlemaker is doing.
    """
    if fight is None or attacker is adversary:
        return 0
    if REDCAP not in canonical(attacker.name):
        return 0
    if not _glory_lit(adversary, fight):
        return 0

    others = len(fight.living_adversaries) - 1
    if others <= 0 or random.random() >= chance_within(Range.CLOSE, others):
        return 0

    fight.note(f"{attacker.name} swings in the candlelight (+{TORCHBEARER_BONUS})")
    return TORCHBEARER_BONUS


DANCE_IN_THE_FLAMES = qualified(ADVERSARY, "Dance in the Flames")

DANCE_DICE = 2
DANCE_DIE = 10


@action(
    DANCE_IN_THE_FLAMES,
    unmodelled=[
        "'a group of PCs within Far range' - no positions are tracked, so the area "
        "rule decides how much of the party the fireball catches",
    ],
)
def dance_in_the_flames(adversary, target, fight: Fight):
    """Spend a candle to drop 2d10 on the Far band, halved by an Agility save.

    SRD: "Spend a token from the Hand of Glory. The Candlemaker conjures a ball of
    fire on a group of PCs within Far range. Each target must make an Agility
    Reaction Roll. Targets who fail take 2d10 magic damage. Targets who succeed
    take half damage."

    **Its cost is the Candlemaker's own defence**, which is the interesting part of
    the stat block: every cast is a candle, and the candles are what keep it Hidden
    and what buff the pack. So the Leader chooses between hurting the party now and
    staying hard to hit - and the choice is real, because it has only five.

    One damage roll rolled once and reused across everybody caught, the standing
    area reading, and halving on a successful save rounds **down**.

    USAGE POLICY - ruled. The standing default: cast whenever a candle can be
    spent and the band reaches somebody. No threshold - the fire is the largest
    thing this stat block does, and the tokens are limited rather than renewable,
    so there is no state where holding one back is clearly better.
    """
    if fight is None:
        return None

    lit = _glory_lit(adversary, fight)
    if not lit:
        return None

    caught = targets_in_area(Range.FAR, fight.conscious_party)
    if not caught:
        return None

    fight.set_token(adversary, GLORY_TOKENS, lit - 1)
    if lit - 1 <= 0:
        fight.clear_condition(adversary, HIDDEN)

    damage = roll_damage(
        dice_groups=[DiceGroup(count=DANCE_DICE, sides=DANCE_DIE)], modifier=0
    )
    fight.note(
        f"{adversary.name} throws a candle, and it blooms into fire "
        f"(Dance in the Flames: {lit - 1} candles left)"
    )
    for pc in caught:
        roll = _reaction_roll(pc, "agility", adversary.difficulty, fight)
        dealt = damage.total // 2 if roll.is_success else damage.total
        pc.take_damage(dealt, fight, damage_type=DamageType.MAGIC)
        fight.note(f"{pc.name} takes {dealt} from the flames")

    return AttackResult(attack_roll=None, damage_roll=damage)


SHALLOW_CUTS = qualified(ADVERSARY, "Shallow Cuts")

SHALLOW_CUTS_EACH = 1


@convert_party_roll(
    SHALLOW_CUTS,
    unmodelled=[
        "This rides the roll-**conversion** hook as a pure notice rather than "
        "converting anything, because that hook is the only GM-side one asked on "
        "*every* PC roll rather than on attack rolls alone. It always returns "
        "None, so nothing it does can rewrite a roll. Fane of the Wilds uses a "
        "bonus hook the same way",
    ],
)
def shallow_cuts(adversary, roller, roll, fight=None):
    """Every failed roll costs a PC a point per Skinner underfoot.

    SRD: "When a PC fails a roll, they take 1 physical damage for each Skinner
    within Melee range of them. Combine this damage."

    **Any failed roll, not just an attack**, which is what the page says - a missed
    swing, a failed Spellcast, a Reaction Roll that came up short. That is why this
    sits on the conversion hook: it is asked at the point a roll's outcome is spent,
    for every roll a PC makes, where `on_party_attack_roll` would only ever hear
    about attacks.

    SIMULATION RULE - policy, ruled. **How many Skinners are on that PC is the area
    rule**, asked at the moment the roll fails - `targets_reached` over the swarm at
    the Melee band, the same question *Group Attack* asks of its own kin. So a lone
    Skinner is worth a point and a full pack several, and it is re-rolled each time
    rather than fixed.

    Combined into **one** amount before it is dealt, which the card says outright -
    so it crosses the PC's thresholds once rather than arriving as separate points.

    Registered once for the swarm: the first Skinner asked answers for all of them,
    and the rest return nothing, so a pack of four does not deal four times over.
    """
    if fight is None or roll.is_success:
        return None

    kin = [
        other
        for other in fight.living_adversaries
        if canonical(other.name) == canonical(adversary.name)
    ]
    # Only the first of the swarm answers - `_gm_offers` asks every one of them,
    # and the count below already speaks for the whole pack.
    if not kin or kin[0] is not adversary:
        return None

    underfoot = targets_reached(Range.MELEE, len(kin))
    if underfoot <= 0:
        return None

    dealt = underfoot * SHALLOW_CUTS_EACH
    roller.take_damage(dealt, fight, damage_type=DamageType.PHYSICAL)
    fight.note(
        f"{roller.name} stumbles, and {underfoot} {adversary.name}s open them up "
        f"for {dealt} (Shallow Cuts)"
    )
    return None


# --- Five beasts and a shapeshifter (SRD 2.0) ---------------------------------
#
# Elk, Falcon, Grimmling Warband, Harpy and Kelpie: nothing that fights as a pack,
# and the batch where two of them introduce something the catalogue had never had -
# **an adversary leaving a fight without being defeated.** The Elk bolts when it is
# hurt and the Warband breaks when its Leader falls, and both go through
# `FightState.remove`, which the Green Ooze's *Split* built and nothing has used to
# take something off the field for good.
#
# Worth being plain about what that means for a result: a fled adversary is not a
# defeated one, but the fight still ends when the field is empty, because
# `_check_finished` reads `living_adversaries` and a removed adversary is not in
# it. So the party can win without landing a killing blow.


ELK_HEADBUTT = qualified(ADVERSARY, "Headbutt")

HEADBUTT_DICE = 1
HEADBUTT_DIE = 12
HEADBUTT_MODIFIER = 2

# Who the Elk last lowered its antlers at, stored as a token. Tokens are counts, so
# the *identity* is kept by storing `id(target)` as the value - which is a stable
# integer for as long as the PC is alive, and never 0, so an unset token reads
# correctly as "nobody yet".
HEADBUTT_LAST_TARGET = "Headbutt last target"


@attack_failed(ELK_HEADBUTT)
def headbutt_remembers_a_miss(adversary, target, roll, fight=None) -> None:
    """Record who the Elk swung at even when it missed.

    Without this the last target would only ever be written down on a landed hit -
    this feature's other registration is asked from inside the damage roll, which a
    miss never reaches - so an Elk that missed a PC and then hit the same PC would
    count as having switched targets and charge again. The two registrations
    together mean every swing updates the memory, which is what "moves before making
    a standard attack" needs: the Elk moved whether or not it connected.
    """
    if fight is None:
        return
    fight.set_token(adversary, HEADBUTT_LAST_TARGET, id(target))


@standard_damage(ELK_HEADBUTT)
def headbutt(adversary, target, roll=None, fight=None):
    """A charging standard attack deals 1d12+2 instead of the printed damage.

    SRD: "When the Elk moves from Close range or farther before making a standard
    attack, it deals 1d12+2 physical damage instead of their standard damage."

    SIMULATION RULE - policy, ruled. No movement is tracked, so the trigger is read
    as **the Elk swinging at somebody other than whoever it last swung at** - a new
    target is the one visible sign that it crossed the field to reach them. The
    user ruled it; "always" and "never" were both offered and declined, and so was
    the narrower "first attack of the fight only".

    **The opening attack counts as a charge.** With no previous target recorded the
    Elk closed from wherever it was standing, which the user ruled explicitly. So a
    lone Elk against a party of four Headbutts on its first swing and then whenever
    random targeting moves it on - and against a single PC it Headbutts once and
    never again, which is the shape the reading is meant to have.

    1d12+2 averages 8.5 against the printed 1d8+1 at 5.5.
    """
    if fight is None:
        return None

    # Read before it is overwritten: the comparison is against the *previous*
    # swing, and this one becomes the previous swing for the next.
    last = fight.token_count(adversary, HEADBUTT_LAST_TARGET)
    fight.set_token(adversary, HEADBUTT_LAST_TARGET, id(target))
    if last == id(target):
        return None

    fight.note(f"{adversary.name} lowers its antlers and charges {target.name}")
    return [DiceGroup(count=HEADBUTT_DICE, sides=HEADBUTT_DIE)], HEADBUTT_MODIFIER


BOLT = qualified(ADVERSARY, "Bolt")

BOLT_DIFFICULTY = 10


def _bolts(adversary, fight) -> None:
    """The Reaction Roll that decides whether a spooked animal stays in the fight.

    Shared by this feature's two registrations rather than written twice, since the
    printed text gives one rule with two triggers.

    An adversary rolls a **flat d20** with no modifier, so the trait named here is
    only which roll the page called for; the SRD prints none for this one at all.

    A defeated Elk does not flee - there is nothing left to run, and removing it
    would take a body off the field that the party has already earned.
    """
    if fight is None or adversary.is_defeated:
        return

    roll = _reaction_roll(adversary, "instinct", BOLT_DIFFICULTY, fight)
    if roll.is_success:
        fight.note(f"{adversary.name} shies but holds its ground ({roll})")
        return

    fight.note(f"{adversary.name} bolts and is gone ({roll})")
    fight.remove(adversary)


@on_damaged(BOLT)
def bolt_when_wounded(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False,
    damage_type=None,
) -> None:
    """Half of *Bolt*: the Elk flees a wound unless it makes a Reaction Roll (10).

    SRD: "When the Elk marks a HP or Stress, it must succeed on a Reaction Roll
    (10) or flee the scene."

    Keyed on Hit Points actually marked rather than on damage arriving, which is
    what the trigger says. Adversaries mark no Armor Slots, so on this side of the
    table any landed hit marks at least one and the distinction rarely bites - but
    a hit softened away to nothing really did make the Elk mark nothing.

    **The first feature in the catalogue that takes an adversary off the field
    without defeating it.** `FightState.remove` is the Green Ooze's machinery
    pointed at a different end: Split removes an Ooze and puts two back, and this
    removes an Elk and puts nothing back.

    USAGE POLICY - none to make. It is not a choice: the page says *must*.
    """
    if fight is None or hp_marked <= 0:
        return
    _bolts(adversary, fight)


@on_stress_marked(BOLT)
def bolt_when_stressed(adversary, amount: int, fight=None) -> None:
    """The other half of *Bolt*, and the reason `on_stress_marked` exists.

    "Marks a HP **or Stress**" - and nothing announced the second. `on_damaged`
    above hears about the Hit Points and could never hear about the Stress, since
    the two arrive by completely different routes: one through the damage
    pipeline, the other from party content forcing a mark (Death Grip, Hush's
    Stun, a wall of hunger).

    Registered on the same name as the damage response above, which is the Redcap
    Candlemaker's *Hand of Glory* arrangement - one printed feature, two moments.

    Forced Stress only, never Stress the Elk spends: it has no feature to spend it
    on, and the hook draws that line for everything that follows.
    """
    _bolts(adversary, fight)


NIMBLE_FLYER = qualified(ADVERSARY, "Nimble Flyer")


@difficulty_bonus(NIMBLE_FLYER)
def nimble_flyer(adversary) -> int:
    """+X to this adversary's Difficulty, because it fights on the wing.

    SRD: "While flying, the Falcon gains a +3 bonus to its Difficulty."

    **Word for word the Giant Mosquitoes' `Flying`, under a different printed
    name**, so it is parameterised the same way and resolved the same way - into
    `Adversary.difficulty` at spawn time, where none of the four readers of
    Difficulty has to know it exists. See `flying` above for the whole of the
    reasoning; the only thing that differs is which word the book chose.

    It is registered under its own name rather than authored as `Flying (3)`
    because a catalogue entry is meant to be checkable against the printed page,
    and a reader looking for *Nimble Flyer* should find it. Homebrew can reach
    either name, which is what the parameterised-name convention is for.

    The Falcon is written `Nimble Flyer (3)` - the full printed bonus, on the same
    reading the Mosquitoes got: a bird of prey is airborne for the whole of a
    fight, so the average uplift and the printed number are the same. A grounded
    variant would be authored with a smaller one.
    """
    written = feature_parameter(adversary, NIMBLE_FLYER)
    if written is None:
        return 0
    try:
        return int(written)
    except ValueError:
        return 0


DIVE_BOMB = qualified(ADVERSARY, "Dive Bomb")

DIVE_BOMB_BONUS = 2


@action(DIVE_BOMB)
def dive_bomb(adversary, target, fight: Fight):
    """Mark a Stress for a standard attack at +2 to both rolls.

    SRD: "Mark a Stress to make a standard attack against a target from above. The
    Falcon gains a +2 bonus to the attack and damage rolls."

    **The first feature to move an adversary's attack roll rather than its
    damage**, which is why `Adversary.attack` grew an `attack_modifier` override -
    dice, flat damage, directness and damage type could all already be stated by a
    feature, and how well it swings could not.

    "From above" is the Falcon being airborne, which *Nimble Flyer* already says it
    is for the whole fight - so the qualifier is always satisfied and costs nothing
    to check, the same handling the Ahuizotl's `Aquatic Attacker` got.

    The printed dice are passed explicitly rather than left to default. That is not
    cosmetic: `_damage_for` treats unstated dice as its cue to ask content whether
    the standard attack's dice should be swapped, and an answer would arrive
    carrying its own flat modifier and quietly discard this +2. The Falcon has no
    such feature today, and stating the dice means it never could.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule decides when it is on the table: three slots against 3
    HP puts the Falcon inside the line from full health.
    """
    if not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} folds its wings and stoops on {target.name}")
    return adversary.attack(
        target,
        fight=fight,
        attack_modifier=adversary.attack_modifier + DIVE_BOMB_BONUS,
        damage_dice=list(adversary.damage_dice),
        damage_modifier=adversary.damage_modifier + DIVE_BOMB_BONUS,
    )


COWARDLY = qualified(ADVERSARY, "Cowardly")

COWARDLY_DIE = 6
COWARDLY_FLEES_ON = 2

# The printed type the SRD's own feature text names - "an allied **Leader**".
LEADER = "Leader"


def _loses_nerve(adversary, fight, because: str) -> None:
    """The d6 the Warband rolls to see whether it stays in the fight.

    Shared by this feature's two registrations, as `_bolts` is by the Elk's: one
    printed rule with two triggers.
    """
    if fight is None or adversary.is_defeated:
        return

    roll = random.randint(1, COWARDLY_DIE)
    if roll > COWARDLY_FLEES_ON:
        fight.note(f"{adversary.name} wavers but holds ({because}, d6: {roll})")
        return

    fight.note(f"{adversary.name} breaks and scatters ({because}, d6: {roll})")
    fight.remove(adversary)


@on_stress_marked(COWARDLY)
def cowardly_at_the_last_stress(adversary, amount: int, fight=None) -> None:
    """Half of *Cowardly*: the Warband may scatter when its Stress track fills.

    SRD: "When the Warband marks its last Stress or an allied Leader is defeated,
    roll a d6. On a result of 2 or lower, the Warband flees the scene."

    **Its last Stress specifically**, so this is asked after the marking has
    settled and checks that nothing is left - a Warband forced to mark one of two
    is not at its last. A forced mark that overflows the track has still filled it,
    and correctly triggers.

    A third of the time it goes, which over a Horde with 2 Stress is a real chance
    the party clears a stat block by pressure rather than damage.
    """
    if fight is None or adversary.stress_unmarked > 0:
        return
    _loses_nerve(adversary, fight, "its last Stress")


@on_ally_defeated(COWARDLY)
def cowardly_when_a_leader_falls(adversary, defeated, fight=None) -> None:
    """The other half of *Cowardly*, and the reason `on_ally_defeated` exists.

    Nothing announced an adversary being defeated: the fight loop notices only that
    `living_adversaries` has got shorter, and `on_damaged` belongs to whoever took
    the hit rather than to whoever watched.

    **The first feature anywhere to read an adversary's printed `type`.** The
    standing note is that type carries no mechanics and the fight loop never reads
    it - which is still true, and is about the *loop*. The SRD's own feature text
    names a type here ("an allied **Leader**"), so content reading it is the page
    being followed rather than the rule being bent. Matched canonically, like every
    other name in the project.

    No range clause on the page, so none is applied: a Warband anywhere on the
    field sees its Leader go down. That is the printed text rather than a reading -
    contrast *Torchbearer*, which says "within Close range" and gets the area rule.
    """
    if fight is None or canonical(getattr(defeated, "type", "")) != canonical(LEADER):
        return
    _loses_nerve(adversary, fight, f"{defeated.name} falls")


TOXIC_AURA = qualified(ADVERSARY, "Toxic Aura")

# Matched on part of a name, the way REDCAP and ZOMBIE are - the page says "all
# non-Harpies", which is a kind rather than a stat block.
HARPY = canonical("Harpy")


@adversary_on_spotlight(TOXIC_AURA)
def toxic_aura(adversary, spotlighted, fight=None, paid: bool = False) -> None:
    """Everything standing in the stench is Vulnerable, re-drawn as the field moves.

    SRD: "The Harpy emits a foul stench that renders all non-Harpies *Vulnerable*
    while within Very Close range."

    SIMULATION RULE - policy, ruled. A standing aura rather than a triggered
    effect, and **who is inside it is re-drawn at every adversary spotlight** - the
    user's ruling, chosen over drawing it once at the start of the fight and over
    reading it only off whoever the Harpy attacks. That is why this rides
    `adversary_on_spotlight` rather than `on_spotlight`: the aura is a fact about
    where people are standing, which changes as the whole field takes its turns and
    not only when the Harpy acts.

    **"All non-Harpies" includes the Harpy's own side**, on the standing
    printed-noun ruling - the SRD alternates "creatures" and "targets" deliberately,
    and this says neither, it says everyone who is not a Harpy. So a Harpy fighting
    alongside anything else makes its allies Vulnerable too, which is a real cost
    for fielding one.

    How many are caught is `targets_reached` at the Very Close band over that whole
    field. Worth knowing the arithmetic before reading any numbers: Very Close takes
    a third, floored at one and capped at two, so a party of four with no other
    adversaries has **exactly one** of its members Vulnerable at any moment, and it
    takes six non-Harpies on the field before a second is caught.

    The previous draw is lifted before the new one is taken, which is what makes it
    an aura people walk in and out of rather than a condition that accumulates.
    Only conditions **this** Harpy applied are lifted - a Vulnerable somebody else
    put on a PC is not the Harpy's to clear, which is what `Condition.source` is
    for - and a creature already Vulnerable from elsewhere is left alone rather
    than having its own ender overwritten.

    One Harpy answers for the flock, the arrangement *Shallow Cuts* uses: the band
    is measured over everyone who is not a Harpy, so a second stench would
    re-draw the same question and double nothing.
    """
    if fight is None:
        return

    flock = [
        other for other in fight.living_adversaries if HARPY in canonical(other.name)
    ]
    if not flock or flock[0] is not adversary:
        return

    outsiders = list(fight.conscious_party) + [
        other
        for other in fight.living_adversaries
        if HARPY not in canonical(other.name)
    ]
    if not outsiders:
        return

    for creature in outsiders:
        held = fight.condition_on(creature, VULNERABLE)
        if held is not None and held.source is adversary:
            fight.clear_condition(creature, VULNERABLE)

    caught = random.sample(
        outsiders, min(targets_reached(Range.VERY_CLOSE, len(outsiders)), len(outsiders))
    )
    for creature in caught:
        if fight.is_vulnerable(creature):
            continue
        fight.apply_condition(
            creature, Condition(name=VULNERABLE, source=adversary)
        )
    if caught:
        fight.note(
            f"{adversary.name}'s stench turns the air, and "
            f"{len(caught)} gag on it ({VULNERABLE})"
        )


SWOOPING_ATTACK = qualified(ADVERSARY, "Swooping Attack")

SWOOPING_DICE = 3
SWOOPING_DIE = 6


@action(
    SWOOPING_ATTACK,
    unmodelled=[
        "The Harpy's flight path - it moves in a straight line to a point within "
        "Far range - has no representation, so the attack simply reaches whoever "
        "the GM's targeting rule picked. The page names one target either way",
    ],
)
def swooping_attack(adversary, target, fight: Fight):
    """Mark a Stress to dive the length of the field for 3d6.

    SRD: "Mark a Stress to have the Harpy move in a straight line to a point within
    Far range and make an attack against a target in the Harpy's path. On a
    success, the Harpy deals 3d6 physical damage."

    **A target in the path, singular**, so this is one attack against one PC rather
    than an area effect - the SRD writes its area features as "all targets within",
    and this is not one of them. The line itself is movement and reaches nothing
    here.

    3d6 averages 10.5 against the printed 1d8+1 at 5.5, with a tighter spread than
    a single big die - which against threshold bands is a different thing from the
    same average on 1d12+4.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule decides when it is on the table.
    """
    if not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} stoops the length of the field at {target.name}")
    return adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=SWOOPING_DICE, sides=SWOOPING_DIE)],
        damage_modifier=0,
        damage_type=DamageType.PHYSICAL,
    )


SHAPESHIFTER = qualified(ADVERSARY, "Shapeshifter")

# Which PC finds the Kelpie's current form alluring, kept as `id(pc)` for the
# reason HEADBUTT_LAST_TARGET is - a token is a count, and an identity stored as
# one is a stable integer that is never 0.
SHAPESHIFTER_FORM = "Shapeshifter form"


@action(SHAPESHIFTER)
def shapeshifter(adversary, target, fight: Fight):
    """Mark a Stress to wear the shape one PC finds hardest to strike.

    SRD: "Mark a Stress to change the Kelpie's physical form into any creature or
    object smaller than a wagon. A creature has disadvantage on rolls against the
    Kelpie while the Kelpie is in a form the creature finds pleasing or alluring."

    SIMULATION RULE - policy, ruled. **One PC, for the rest of the fight.** A form
    is tailored to one creature's desire, and *Heart's Desire* is what tells the
    Kelpie whose - so the Kelpie always finds a form that works on somebody, and
    never on everybody. Applying it to the whole party, and ending it on the next
    hit the Kelpie takes, were both offered and declined.

    Which PC is chosen at random, per the standing rule for a choice nothing in the
    printed text decides. Nothing here reads who is most dangerous: that is a
    statistic nobody at a table computes.

    Not taken again while a form is already worn - re-shaping would spend a Stress
    to move the Disadvantage from one PC to another for no gain, which is the
    standing don't-re-apply rule reaching a feature that carries a token rather
    than a condition.

    No roll of its own, so it hands back a rollless `AttackResult` the way the
    flame features do: the spotlight was spent and nothing was thrown.

    USAGE POLICY - ruled. An Action costing Stress. Note what the Kelpie's stat
    block does to the desperation rule - five Stress against 3 HP means it clears
    the line from full health and can afford to shift early.
    """
    if fight is None or not adversary.will_spend_stress(1):
        return None
    if fight.token_count(adversary, SHAPESHIFTER_FORM):
        return None

    charmed = list(fight.conscious_party)
    if not charmed:
        return None

    adversary.spend_stress(1)
    chosen = random.choice(charmed)
    fight.set_token(adversary, SHAPESHIFTER_FORM, id(chosen))
    fight.note(
        f"{adversary.name} takes a shape {chosen.name} cannot bring themselves "
        f"to strike cleanly"
    )
    return AttackResult(attack_roll=None, damage_roll=None)


@party_attack_disadvantage(SHAPESHIFTER)
def shapeshifter_beguiles(adversary, attacker, target, weapon, fight=None) -> bool:
    """The Disadvantage the Kelpie's borrowed shape puts on one PC's swings.

    Registered on the same name as the action above - one printed feature, one
    moment that sets the state and one that reads it, the *Hand of Glory*
    arrangement.

    Scoped to attacks **against the Kelpie itself**, which is what the page says:
    the form is what the attacker cannot bear to hit, so it does nothing to that
    PC's swings at anything else. Contrast the Darkweave Spinner's *Shadow Fang*,
    registered on the same hook, which hobbles its victim's attacks generally.

    The page says "disadvantage on **rolls** against the Kelpie" and this hobbles
    attack rolls - which is not a narrowing, because an attack roll is the only
    kind of roll anybody makes *against* an adversary here. A PC's other action
    rolls are made against a card's own Difficulty rather than against a
    combatant, so there is nothing else for the clause to reach.
    """
    if fight is None or target is not adversary:
        return False
    return fight.token_count(adversary, SHAPESHIFTER_FORM) == id(attacker)


ENCHANT = qualified(ADVERSARY, "Enchant")

ENCHANT_FEAR = 1


@action(ENCHANT)
def enchant(adversary, target, fight: Fight):
    """Spend a Fear to talk a PC out of the fight until somebody hits them.

    SRD: "Spend a Fear to have the Kelpie beguile a PC within Close range. The PC
    must succeed on an Instinct Reaction Roll or become *Enchanted* until they take
    damage. While *Enchanted*, the PC perceives the Kelpie as a trusted friend or
    ally and will do what the Kelpie says unless it contradicts the PC's most
    deeply held morals."

    SIMULATION RULE - policy, ruled. **An Enchanted PC loses their spotlight
    entirely**, carried on `Condition.prevents_action` - the user's ruling, chosen
    over letting them act but never at the Kelpie, and over turning them on an ally.
    So this is the first thing on the GM's side of the table that can stop a PC
    acting at all, and the party's only way out is to wound their own charmed
    friend.

    The condition is applied with no printed Difficulty, so the Kelpie's own
    Difficulty is used - the standing rule where the SRD names a Reaction Roll and
    no number.

    "Within Close range" goes through the area rule, asked of the party, which is
    the standing answer for a range clause naming one specific creature.

    **The Fear is spent before the roll**, because the page spends it to *have the
    Kelpie beguile* rather than on the result - a successful save costs the GM the
    Fear all the same.

    USAGE POLICY - ruled. Free among the affordable options, gated by the standing
    don't-re-apply rule: a PC who is already Enchanted is not worth a second Fear,
    since the condition has no stacking half.
    """
    if fight is None or fight.has_condition(target, ENCHANTED):
        return None

    party = len(fight.conscious_party)
    if party <= 0 or random.random() >= chance_within(Range.CLOSE, party):
        return None
    if not fight.spend_fear(ENCHANT_FEAR):
        return None

    roll = _reaction_roll(target, "instinct", adversary.difficulty, fight)
    if roll.is_success:
        fight.note(f"{target.name} shakes off the Kelpie's voice ({roll})")
        return AttackResult(attack_roll=None, damage_roll=None)

    fight.apply_condition(
        target,
        Condition(
            name=ENCHANTED,
            end=until_they_take_damage(target.hp_marked, target.armor_marked),
            source=adversary,
            prevents_action=True,
        ),
    )
    fight.note(
        f"{target.name} takes the Kelpie for a friend and stops fighting "
        f"({ENCHANTED}, until they are hurt)"
    )
    return AttackResult(attack_roll=None, damage_roll=None)


insignificant_combat_effect(
    qualified(ADVERSARY, "Captivating"),
    "A PC must mark a Stress to move out of the Kelpie's Melee range. Word for "
    "word the Redcap Biters' Ankle Weights, and ruled into the same state by the "
    "user, so the same number applies: **one Stress per disengagement, and a "
    "simulated fight contains zero disengagements**, for an expected cost of 0.0 "
    "Stress across a high-N run. The state is the one it is because Stress is a "
    "resource represented completely here - the effect has something to touch - "
    "and only its trigger never arrives. It would become real the moment "
    "positions were tracked.",
)


no_combat_effect(
    qualified(ADVERSARY, "Heart's Desire"),
    "After the Kelpie has watched a creature for at least a hundred heartbeats, "
    "it knows the physical form that creature would find most pleasing. The "
    "effect is **knowledge**, and knowledge has no representation here: nothing "
    "in the simulator holds information that a combatant could act on or lack. "
    "What it is *for* is Shapeshifter, which is modelled and which carries the "
    "whole mechanical half - the ruling that the Kelpie always finds a form "
    "somebody finds alluring is exactly this passive being assumed true. So "
    "dismissing it loses nothing, and modelling it would mean writing a second "
    "copy of Shapeshifter's own effect.",
)


# --- Masque Muerte, Mechanorb, Mountain Troll, Octopus, Panther (SRD 2.0) -----
#
# The batch that brought three pieces of shared machinery: **Pools** (tokens
# belonging to no combatant), **Evolutions** (a stat block that changes mid-fight)
# and a passive that moves an adversary's own attack roll.


MASQUE_LIBRE = qualified(ADVERSARY, "Libre")


@condition_refusal(MASQUE_LIBRE)
def libre(adversary, condition, fight: Fight = None) -> bool:
    """This adversary simply cannot be Restrained.

    SRD: "The Masque Muerte can't be *Restrained*."

    The Bugboar's *Warheart* pointed at one condition rather than all of them, and
    it is worth naming what it is worth here: Restrained is recorded-but-inert, so
    refusing it buys nothing directly. What it does buy is immunity to the things
    that *read* the record - the Jagged Knife Kneebreaker's *I've Got 'Em* doubles
    its allies' damage against a creature it has Restrained, and a wrestler who
    cannot be held never gives that up.

    Asked only when a condition would actually land, so nothing is spent checking.
    """
    return canonical(condition.name) == canonical(RESTRAINED)


HEEL_TURN = qualified(ADVERSARY, "Heel Turn")


@action(HEEL_TURN)
def heel_turn(adversary, target, fight: Fight):
    """Mark a Stress: a Close attack that costs a Stress and leaves them Vulnerable.

    SRD: "Mark a Stress to make an attack against a PC within Close range. On a
    success, the target marks a Stress and is temporarily *Vulnerable* as the
    Masque Muerte assaults them with a string of insulting taunts."

    The feature states no damage of its own, so the attack deals the Masque
    Muerte's standard 1d12+2 magic - the standing default.

    "Temporarily" on a PC is the whole fight, the standing reading, so the
    Vulnerable carries no ender. The Stress is forced rather than spent, so a full
    track overflows into a Hit Point on the PC's side exactly as it does on the
    GM's.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule gates it; and held back against a target already
    Vulnerable, per the standing don't-re-apply rule, since the taunt is what the
    Stress is being spent on.
    """
    if fight is None or not adversary.will_spend_stress(1):
        return None
    if fight.is_vulnerable(target):
        return None

    party = len(fight.conscious_party)
    if party <= 0 or random.random() >= chance_within(Range.CLOSE, party):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} works the crowd against {target.name} (Heel Turn)")
    result = adversary.attack(target, fight=fight)
    if not result.made_an_attack or not result.attack_roll.is_success:
        return result

    target.mark_stress(1)
    fight.apply_condition(
        target, Condition(name=VULNERABLE, source=adversary)
    )
    fight.note(f"{target.name} loses their composure ({VULNERABLE})")
    return result


SPECTRAL_SUPLEX = qualified(ADVERSARY, "Spectral Suplex")

SUPLEX_DICE = 1
SUPLEX_DIE = 10
SUPLEX_MODIFIER = 6
SUPLEX_FEAR = 1


@action(SPECTRAL_SUPLEX)
def spectral_suplex(adversary, target, fight: Fight):
    """Spend a Fear to slam a held PC for 1d10+6 magic, with no roll to miss with.

    SRD: "Spend a Fear to have the Masque Muerte suplex a *Restrained* PC, dealing
    1d10+6 magic damage to them."

    **No attack roll at all** - the page makes it a consequence of already being
    held rather than a swing, so there is nothing for Evasion or a forced reroll
    to turn away. That is the second thing in the catalogue that cannot miss,
    after Codex's Rune Circle on the party's side, and it is what being Restrained
    by this stat block costs.

    Only a *Restrained* target, which in practice means one this Masque Muerte has
    *Pinned* with *Tag Team* - Restrained arrives from a handful of other places
    (the Kneebreaker, the Bear, an Octopus) and any of them would do. Declines when
    nobody is held, so the Fear is never spent on nothing.

    USAGE POLICY - ruled. Free among the affordable options, per the standing
    random-among-viable rule, with the printed requirement doing the gating.
    """
    if fight is None or not fight.has_condition(target, RESTRAINED):
        return None
    if not fight.spend_fear(SUPLEX_FEAR):
        return None

    damage = roll_damage(
        dice_groups=[DiceGroup(count=SUPLEX_DICE, sides=SUPLEX_DIE)],
        modifier=SUPLEX_MODIFIER,
    )
    target.take_damage(damage.total, fight, damage_type=DamageType.MAGIC)
    fight.note(
        f"{adversary.name} hauls {target.name} off the ground for "
        f"{damage.total} (Spectral Suplex)"
    )
    return AttackResult(attack_roll=None, damage_roll=damage)


UNMASKING_DEATH = qualified(ADVERSARY, "Unmasking Death")

UNMASKING_FEAR = 1


@action(UNMASKING_DEATH)
def unmasking_death(adversary, target, fight: Fight):
    """Spend a Fear: everyone Close sees the face under the mask and marks a Stress.

    SRD: "Spend a Fear to have the Masque Muerte momentarily remove their mask,
    revealing their horrifying face underneath. Each PC within Close range must
    succeed on a Presence Reaction Roll or mark a Stress."

    "Each **PC**", not each creature, so the printed noun keeps this off the Masque
    Muerte's own side - the distinction *Scorched Earth* and *Hellfire* already
    turn on.

    No Difficulty is printed, so the Masque Muerte's own is used, per the standing
    rule for a Reaction Roll the SRD names without a number.

    A critical takes nothing, as every Reaction Roll here does; there is no half
    measure to take, since the cost is a single Stress.

    USAGE POLICY - ruled. Free among the affordable options. It declines when the
    band reaches nobody, so the Fear is never spent on an empty room.
    """
    if fight is None:
        return None

    party = fight.conscious_party
    caught = party[: targets_reached(Range.CLOSE, len(party))] if party else []
    if not caught:
        return None
    if not fight.spend_fear(UNMASKING_FEAR):
        return None

    fight.note(f"{adversary.name} lifts the mask, and {len(caught)} look at what is under it")
    for pc in caught:
        roll = _reaction_roll(pc, "presence", adversary.difficulty, fight)
        if roll.is_success:
            fight.note(f"{pc.name} holds their nerve ({roll})")
            continue
        pc.mark_stress(1)
        fight.note(f"{pc.name} recoils, marking a Stress ({roll})")
    return AttackResult(attack_roll=None, damage_roll=None)


TAG_TEAM = qualified(ADVERSARY, "Tag Team")

TAG_TEAM_FEAR = 1
PIN_DICE = 1
PIN_DIE = 12


@on_hit(TAG_TEAM)
def tag_team(adversary, target, result, fight: Fight) -> None:
    """Spend a Fear on a landed hit to Pin the target until they wrestle free.

    SRD: "When the Masque Muerte deals damage to a PC, you can spend a Fear to
    have a spectral wrestler appear and *Pin* the target until they escape with a
    successful Strength Roll. While *Pinned*, the target is *Restrained* and takes
    an extra 1d12 magic damage from the Masque Muerte's attacks."

    *Pinned* is **its own condition**, which is the user's ruling and the standing
    call for a state the page names and refers back to. A *Restrained* record goes
    on beside it so other content can still see the hold - the Kneebreaker's *I've
    Got 'Em* keys on exactly that - and the Restrain carries the escape roll,
    clearing the Pin with it, so a PC never rolls twice for one struggle.

    No Difficulty is printed for the Strength Roll, so the Masque Muerte's own is
    used, per the standing rule.

    USAGE POLICY - ruled. A Reaction, so it fires on every trigger it can pay for,
    and declines against a target already Pinned per the standing don't-re-apply
    rule - a second Pin would replace the first rather than stack.
    """
    if fight is None or not result.made_an_attack:
        return
    if fight.has_condition(target, PINNED):
        return
    if not fight.spend_fear(TAG_TEAM_FEAR):
        return

    fight.apply_condition(
        target,
        Condition(
            name=RESTRAINED,
            end=_breaks_free(("strength",), adversary.difficulty, also_clear=(PINNED,)),
            source=adversary,
        ),
    )
    fight.apply_condition(target, Condition(name=PINNED, source=adversary))
    fight.note(f"a spectral wrestler drops on {target.name} ({PINNED})")


@damage_bonus(TAG_TEAM)
def tag_team_grinds_them_down(adversary, target, fight=None) -> int:
    """The extra 1d12 a Pinned target takes from this adversary's attacks.

    Registered on the same name as the Reaction above - one printed feature, one
    moment that applies the hold and one that reads it, the *Hand of Glory*
    arrangement.

    Scoped to a Pin **this** Masque Muerte put on, through `Condition.source`, so
    two of them in one fight each collect only on their own. That is the same
    strictness the Kneebreaker's *I've Got 'Em* reads its own Restrain with.

    **On `damage_bonus` rather than `extra_damage`**, which is the hook a card
    adding dice would normally take - and which never fires here. `extra_damage`
    is asked from `items/weapons.py` alone, so it only ever hears about a PC's
    swing; the GM side's damage goes through `Adversary._damage_for`, which asks
    `damage_bonus` and its ally-scoped twin and nothing else. So the d12 is thrown
    here and handed over as a number.

    Nothing is lost by that. `_damage_for` folds the bonus into the modifier
    **before** `roll_damage`, so the extra still lands inside the attack's single
    damage roll and crosses the target's thresholds exactly once - which is the
    whole property `extra_damage` exists to protect. What it costs is only that a
    play-by-play line reading the roll shows the d12 inside the total rather than
    as its own group, which is declared here rather than worked around.

    Asked before the attack is rolled, so it cannot key on how the swing came out -
    and it has no need to, since being Pinned is a standing fact about the target.
    """
    if fight is None:
        return 0
    held = fight.condition_on(target, PINNED)
    if held is None or held.source is not adversary:
        return 0
    return roll_damage(
        dice_groups=[DiceGroup(count=PIN_DICE, sides=PIN_DIE)], modifier=0
    ).total


HIVE_MIND = qualified(ADVERSARY, "Hive Mind")

HIVE_MIND_EACH = 1


@live_difficulty_bonus(HIVE_MIND)
def hive_mind(adversary, attacker, fight=None) -> int:
    """+1 Difficulty for every other one of these standing within Close range.

    SRD: "The Mechanorb gains a +1 bonus to their Difficulty for each other
    Mechanorb within Close range."

    **Not `difficulty_bonus`**, which is resolved into the stat block once at
    spawn and could not say this: the count falls as the swarm is cleared, so a
    bonus frozen at the encounter's opening field would leave the last Mechanorb
    standing as hard to hit as six of them were. See `live_difficulty_bonus`.

    SIMULATION RULE - policy. "Within Close range" is the area rule, the standing
    answer for a range clause, asked per swing so where the swarm is standing is
    re-rolled rather than fixed. Close reaches `min(n * 3 // 4, n - 1)` of the
    others, so a pair of orbs is worth +1 to each other and a field of six is
    worth +3.

    Matched on the stat block's own name, so a Mechanorb counts other Mechanorbs
    and nothing else - "each other **Mechanorb**" names its own kind rather than a
    kind of adversary, which is where this differs from *No Quarter*'s Pirates.
    """
    if fight is None:
        return 0

    swarm = [
        other
        for other in fight.living_adversaries
        if canonical(other.name) == canonical(adversary.name) and other is not adversary
    ]
    if not swarm:
        return 0
    return HIVE_MIND_EACH * targets_reached(Range.CLOSE, len(swarm))


ADAPTIVE_TACTICS = qualified(ADVERSARY, "Adaptive Tactics")


def _mechanorb_pool(adversary) -> str:
    """The name of the pool this stat block's swarm shares.

    Keyed on the **stat block's own name** rather than on the feature, so every
    Mechanorb shares one pool and a homebrew stat block carrying *Adaptive Tactics*
    gets its own rather than feeding somebody else's. The page calls it "the
    Mechanorb Pool", which is that reading.
    """
    return f"{canonical(adversary.name)} Pool"


@attack_failed(ADAPTIVE_TACTICS)
def adaptive_tactics_learns(adversary, target, roll, fight=None) -> None:
    """A missed needle teaches the swarm something: one token into the pool.

    SRD: "*Pool.* When the Mechanorb fails an attack roll, add a token to the
    Mechanorb Pool. All Mechanorbs in the scene gain a bonus to attack rolls equal
    to the number of tokens in the Mechanorb Pool. Clear all tokens when any
    Mechanorb takes Severe damage or is defeated."

    **The first Pool in the project.** SRD 2.0 p. 94 defines one as tokens "shared
    by multiple adversaries" that the GM collects "in a separate location" rather
    than on a stat block, and every token here was keyed to a single holder. So
    `FightState` grew `pool_count` / `add_to_pool` / `clear_pool`, keyed by name
    alone - which is what lets the bonus outlive the orb that earned it.

    **The first GM-side registrant on `attack_failed`.** The hook has always meant
    "the attacker's own content answers their swing coming up short", and it was
    announced only from `items/weapons.py`, so it could only ever hear about a PC
    missing. `Adversary.attack` announces it too now - one new call site, no new
    hook, exactly as `attack_missed` was opened to the party's side.

    No cap on the pool, which is the page read literally. A swarm that keeps
    missing keeps getting better at it until something clears them.
    """
    if fight is None:
        return
    size = fight.add_to_pool(_mechanorb_pool(adversary), 1)
    fight.note(f"{adversary.name} adjusts (Adaptive Tactics: pool at {size})")


@attack_roll_bonus(ADAPTIVE_TACTICS)
def adaptive_tactics_aims(adversary, target, fight=None) -> int:
    """Every one of the swarm swings at +1 per token in the shared pool."""
    if fight is None:
        return 0
    return fight.pool_count(_mechanorb_pool(adversary))


@on_damaged(ADAPTIVE_TACTICS)
def adaptive_tactics_resets(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False,
    damage_type=None,
) -> None:
    """A Severe hit on any of them, or a defeat, empties the pool.

    Read off the **damage** against this adversary's own Severe threshold rather
    than off the Hit Points it marked, which is how every other "takes Severe
    damage" trigger in the catalogue reads it - the Green Ooze's *Envelop* release
    and Blade's *Get Back Up* both measure the amount.

    Registered on the same name as the two above; one printed feature, three
    moments.
    """
    if fight is None:
        return
    if amount < adversary.severe_threshold and not adversary.is_defeated:
        return
    if not fight.pool_count(_mechanorb_pool(adversary)):
        return

    fight.clear_pool(_mechanorb_pool(adversary))
    fight.note(f"{adversary.name} is knocked out of formation (Adaptive Tactics cleared)")


STOLEN_ARMOR = qualified(ADVERSARY, "Stolen Armor")

ENRAGED_MOUNTAIN_TROLL = "Enraged Mountain Troll"

STOLEN_ARMOR_COUNTDOWN = "Stolen Armor countdown"
STOLEN_ARMOR_PLACED = "Stolen Armor placed"


def _armor_left(adversary, fight) -> int:
    """How many hits the stolen armor still turns, placing it the first time asked.

    "When combat begins" is a moment nothing announces, so the countdown is placed
    lazily the first time anything looks - the Redcap Candlemaker's *Hand of Glory*
    arrangement, and for the same reason. A second token records that it has been
    placed, so a Troll whose armor is gone is not handed a fresh set.

    The value is the number of PCs standing when it is placed, which is the first
    hit the Troll takes - so in practice the whole party.
    """
    if fight is None:
        return 0
    if not fight.token_count(adversary, STOLEN_ARMOR_PLACED):
        fight.set_token(adversary, STOLEN_ARMOR_PLACED, 1)
        fight.set_token(
            adversary, STOLEN_ARMOR_COUNTDOWN, len(fight.conscious_party)
        )
    return fight.token_count(adversary, STOLEN_ARMOR_COUNTDOWN)


@severity_response(STOLEN_ARMOR)
def stolen_armor(
    adversary, amount: int, hp_to_mark: int, fight=None, damage_type=None
) -> int:
    """Purloined plate turns one band off every hit, until it is beaten off.

    SRD: "*Countdown.* When combat begins, activate a countdown with a value equal
    to the number of PCs. When the Troll takes damage, reduce the severity by one
    threshold, then tick down the countdown. When it triggers, the Troll evolves."

    SIMULATION RULE - policy, ruled. Damage becomes 1, 2 or 3 Hit Points through
    the threshold bands, so "reduce the severity by one threshold" is one Hit Point
    fewer - and a hit that was only ever going to mark **1 marks nothing at all**.
    The user ruled that rather than flooring it at one: a band below the lowest band
    is no wound. It is bounded either way, since every hit ticks the countdown
    whatever its size.

    So the armor is worth *party size* hits, and the party chooses nothing about
    how big they are: four small hits strip it as fast as four Severe ones. What a
    table does about that is exactly the sort of thing worth watching in a run.

    The evolution is triggered from here rather than from a separate hook, because
    this is the one moment the page ties it to - taking damage.
    """
    if fight is None:
        return hp_to_mark

    left = _armor_left(adversary, fight)
    if left <= 0:
        return hp_to_mark

    softened = max(hp_to_mark - 1, 0)
    fight.spend_tokens(adversary, STOLEN_ARMOR_COUNTDOWN, 1)
    left = fight.token_count(adversary, STOLEN_ARMOR_COUNTDOWN)
    fight.note(
        f"{adversary.name}'s stolen armor turns the blow "
        f"({hp_to_mark} HP to {softened}; {left} left)"
    )

    if left <= 0:
        _enrage(adversary, fight)
    return softened


def _enrage(adversary, fight) -> None:
    """Swap the Troll's stat block for its Evolution, in place.

    SRD, *Enraged Mountain Troll*: "The Troll loses their 'Stolen Armor' and 'Flail
    Swipe' features, then gains a +1 bonus to their Difficulty. Additionally, they
    gain the 'Double Swipe' feature and replace 'Skull Flail' with the following
    standard attack: Claw Swipe | Very Close | 1d10+3 phy."

    **The first Evolution in the project**, and it is the same combatant throughout
    - the user's ruling. `Adversary.evolve` rewrites what the stat block *is* and
    leaves what this fight has done to it alone, so the Hit Points and Stress the
    party has already spent still count and every condition and token keyed to the
    Troll survives the change.

    The evolved form is an ordinary catalogue entry rather than numbers written
    here, so both halves of the page stay checkable against it - the same reason
    `Adversary` carries no per-adversary Python at all.
    """
    evolved = find_adversary(ENRAGED_MOUNTAIN_TROLL)
    if evolved is None:
        return
    adversary.evolve(evolved.spawn())
    fight.note(f"the armor falls away, and {adversary.name} rises")


FLAIL_SWIPE = qualified(ADVERSARY, "Flail Swipe")

FLAIL_SWIPE_DICE = 2
FLAIL_SWIPE_DIE = 8
FLAIL_SWIPE_MODIFIER = 2


@action(
    FLAIL_SWIPE,
    unmodelled=[
        "'In front of the Troll' is a facing, and none is tracked - so the band "
        "reaches whoever the area rule puts inside it rather than whoever is "
        "standing the right way",
    ],
)
def flail_swipe(adversary, target, fight: Fight):
    """Mark a Stress to sweep everyone Very Close for 2d8+2.

    SRD: "Mark a Stress to make an attack against all targets in front of the Troll
    within Very Close range. Targets the Troll succeeds against take 2d8+2 physical
    damage."

    The Cave Ogre's *Hail of Boulders* shape: one attack roll measured against each
    target's Evasion, which is what "targets the Troll succeeds against" says. Very
    Close takes a third of the party, floored at one and capped at two.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule decides when it is on the table - three slots against 8
    HP puts the Troll inside the line from full health.
    """
    if fight is None or not adversary.will_spend_stress(1):
        return None

    caught = targets_in_area(Range.VERY_CLOSE, fight.conscious_party)
    if not caught:
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} sweeps the flail through {len(caught)}")
    result, _ = adversary.area_attack(
        caught,
        fight=fight,
        damage_dice=[DiceGroup(count=FLAIL_SWIPE_DICE, sides=FLAIL_SWIPE_DIE)],
        damage_modifier=FLAIL_SWIPE_MODIFIER,
        damage_type=DamageType.PHYSICAL,
    )
    return result


DOUBLE_SWIPE = qualified(ADVERSARY, "Double Swipe")

DOUBLE_SWIPE_FEAR = 1
DOUBLE_SWIPE_ATTACKS = 2


@action(DOUBLE_SWIPE)
def double_swipe(adversary, target, fight: Fight):
    """Spend a Fear for two claw swipes, combined into one wound if both land.

    SRD: "Spend a Fear to move up to Close range and make two standard attacks
    against a target within Melee range. If both attacks succeed, combine the
    damage, and the target loses a Hope."

    **Combining matters more than the second attack does.** Two hits of 7 each mark
    1 Hit Point apiece off a tier 1 PC; one combined 14 crosses a Severe threshold
    and marks 3. That is the Head Guard's *On My Signal* arithmetic, and this
    builds the combined roll the same way - the attacks share a stat block, so
    multiplying the printed dice by the number that landed **is** the sum of them.

    The Hope is taken only when both land, which is what the page gates it on, and
    only where there is one to take - the standing zero-benefit rule.

    The move to Close range is repositioning and reaches nothing here.

    USAGE POLICY - ruled. Free among the affordable options, per the standing
    random-among-viable rule.
    """
    if fight is None or not fight.spend_fear(DOUBLE_SWIPE_FEAR):
        return None

    def swing():
        return roll_d20(
            modifier=adversary.attack_modifier,
            evasion=target.evasion,
        )

    hits = 0
    critical = False
    for _ in range(DOUBLE_SWIPE_ATTACKS):
        blow = force_adversary_reroll(adversary, target, swing(), swing, fight)
        if blow.is_success:
            hits += 1
            critical = critical or blow.is_critical

    if not hits:
        fight.note(f"{adversary.name} swipes twice at {target.name} and connects with neither")
        return AttackResult(attack_roll=None, damage_roll=None)

    damage = roll_damage(
        dice_groups=[
            DiceGroup(count=group.count * hits, sides=group.sides)
            for group in adversary.damage_dice
        ],
        modifier=adversary.damage_modifier * hits,
        is_critical=critical,
    )
    marked = target.take_damage(
        damage.total,
        fight,
        direct=deals_direct_damage(adversary, fight),
        damage_type=adversary.type_of_damage(),
    )
    fight.note(
        f"{hits} of the double swipe lands on {target.name} for {damage.total}"
    )

    if hits == DOUBLE_SWIPE_ATTACKS and target.can_spend_hope(1):
        target.spend_hope(1)
        fight.note(f"{target.name} is rattled and loses a Hope")
    return AttackResult(attack_roll=None, damage_roll=damage, hp_marked=marked)


GRAPPLE = qualified(ADVERSARY, "Grapple")


@action(GRAPPLE)
def grapple(adversary, target, fight: Fight):
    """An attack that leaves the target held and Vulnerable until they break out.

    SRD: "Make an attack roll against a target within Close range. On a success,
    the target becomes *Restrained* and *Vulnerable* until they escape with a
    successful Strength Roll."

    The feature states no damage of its own, so the attack deals the Octopus's
    standard 1d6 - the standing default.

    **Two conditions, one escape roll.** The Restrain carries the roll and clears
    the Vulnerable with it, which is `_breaks_free`'s `also_clear` and the same
    arrangement the Darkweaves needed: a creature half-freed from one hold is not a
    state the SRD has. No Difficulty is printed, so the Octopus's own is used.

    The Vulnerable is what this is actually worth - Restrained is recorded and
    inert here - and an Octopus has 2 Hit Points, so it rarely gets to do it twice.

    USAGE POLICY - ruled. Free among the affordable options, held back against a
    target already Restrained by this Octopus per the standing don't-re-apply rule.
    """
    if fight is None:
        return None
    held = fight.condition_on(target, RESTRAINED)
    if held is not None and held.source is adversary:
        return None

    party = len(fight.conscious_party)
    if party <= 0 or random.random() >= chance_within(Range.CLOSE, party):
        return None

    fight.note(f"{adversary.name} wraps its arms around {target.name} (Grapple)")
    result = adversary.attack(target, fight=fight)
    if not result.made_an_attack or not result.attack_roll.is_success:
        return result

    fight.apply_condition(
        target,
        Condition(
            name=RESTRAINED,
            end=_breaks_free(("strength",), adversary.difficulty, also_clear=(VULNERABLE,)),
            source=adversary,
        ),
    )
    fight.apply_condition(target, Condition(name=VULNERABLE, source=adversary))
    fight.note(f"{target.name} is wrapped up ({RESTRAINED}, {VULNERABLE})")
    return result


SQUIRT_INK = qualified(ADVERSARY, "Squirt Ink")


@action(
    SQUIRT_INK,
    unmodelled=[
        "The underwater half - 'a cloud of darkness that fills an area within "
        "Very Close range and blocks line of sight' - has no representation at "
        "all, since nothing tracks where a fight happens or what anybody can see",
    ],
)
def squirt_ink(adversary, target, fight: Fight):
    """Mark a Stress to ink the ground; whoever is standing in it may go over.

    SRD: "Mark a Stress to have the Octopus squirt ink. On land, the ink covers the
    ground within Very Close range. Each creature who moves through that area must
    succeed on an Agility Reaction Roll or slip and fall, becoming *Vulnerable*
    until they exit the area."

    SIMULATION RULE - policy, ruled. "Each creature who **moves through**" is
    movement, and none is tracked. The user ruled it to the area rule instead:
    whoever the Very Close band reaches when the ink goes down makes the Agility
    Reaction Roll, and those who fail are Vulnerable. Dismissing the feature
    outright, and re-rolling it at every announced moment the way the Harpy's
    *Toxic Aura* is re-drawn, were both offered and declined.

    "Until they exit the area" has nowhere to be measured, so the Vulnerable takes
    the standing reading for a condition on a PC and lasts the fight.

    **"Each creature" includes the Octopus's own side**, per the standing
    printed-noun rule - the SRD alternates "creatures" and "targets" deliberately,
    and this says creatures. The Octopus itself is spared: it squirted the ink
    rather than walking into it.

    No Difficulty is printed, so the Octopus's own is used.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule gates it. With 2 Hit Points against 3 Stress the
    Octopus is inside that line from full health.
    """
    if fight is None or not adversary.will_spend_stress(1):
        return None

    creatures = list(fight.conscious_party) + [
        other for other in fight.living_adversaries if other is not adversary
    ]
    caught = creatures[: targets_reached(Range.VERY_CLOSE, len(creatures))]
    if not caught:
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} blacks out the ground under {len(caught)}")
    for creature in caught:
        if fight.is_vulnerable(creature):
            continue
        roll = _reaction_roll(creature, "agility", adversary.difficulty, fight)
        if roll.is_success:
            fight.note(f"{creature.name} keeps their footing ({roll})")
            continue
        fight.apply_condition(creature, Condition(name=VULNERABLE, source=adversary))
        fight.note(f"{creature.name} goes down in the ink ({VULNERABLE})")
    return AttackResult(attack_roll=None, damage_roll=None)


SHADOW_STALKER = qualified(ADVERSARY, "Shadow Stalker")

SHADOW_STALKER_BONUS = 2
SHADOW_STALKER_STALKED = "Shadow Stalker opened"


def _stalk(adversary, fight) -> None:
    """Put the Panther in cover once, at the start of the fight.

    "Combat begins" is a moment nothing announces, so the cloak is raised lazily
    the first time anything looks - the *Hand of Glory* arrangement - and a token
    records that it has happened so the Panther never slips back into cover later.

    Two things look: the Panther taking a spotlight, and somebody swinging at it.
    Between them they cover both ways a fight can open, which is why this is
    registered on two hooks rather than one - the party holds the spotlight first
    by default, so waiting for the Panther's own activation would let the opening
    attacks come in against an uncloaked cat.
    """
    if fight is None or fight.token_count(adversary, SHADOW_STALKER_STALKED):
        return
    fight.set_token(adversary, SHADOW_STALKER_STALKED, 1)
    fight.apply_condition(
        adversary,
        Condition(name=HIDDEN, end=when_they_act, source=adversary),
    )
    fight.note(f"{adversary.name} is already in the shadows ({HIDDEN})")


@on_spotlight(SHADOW_STALKER)
def shadow_stalker_opens(adversary, fight=None) -> None:
    """Raise the cloak when the Panther takes its first spotlight."""
    _stalk(adversary, fight)


@before_attacked(SHADOW_STALKER)
def shadow_stalker_was_already_there(adversary, attacker, weapon, fight=None) -> None:
    """And raise it when somebody swings first, which is the commoner case."""
    _stalk(adversary, fight)


@attack_roll_bonus(SHADOW_STALKER)
def shadow_stalker(adversary, target, fight=None) -> int:
    """+2 to this adversary's attack rolls while it is Hidden.

    SRD: "While *Hidden*, the Panther gains a +2 bonus to its attack rolls."

    SIMULATION RULE - policy, ruled. Nothing in the Panther's own stat block hides
    it, so the bonus would never once have fired - the shape that left the Redcap
    Butcher's *Knife Thrower* Advantage mostly dead. The user ruled that **the
    Panther opens the fight Hidden and the cloak breaks when it acts**: an ambush
    predator strikes from cover once. Leaving the bonus dead, and re-arming the
    cloak on any spotlight it does not attack on, were both offered and declined.

    So this is worth +2 on the opening swing and nothing afterwards, unless
    something else hides the Panther - and being Hidden is worth more than the
    bonus while it lasts, since every roll against a hidden combatant is
    Disadvantaged.

    **The first registrant on `attack_roll_bonus`**, which exists because nothing
    could move an adversary's ordinary attack roll: `attack_advantage` grants
    Advantage rather than a number, and the `attack_modifier` override belongs to a
    feature stating what its own attack swings at.
    """
    if fight is None or not fight.has_condition(adversary, HIDDEN):
        return 0
    return SHADOW_STALKER_BONUS


POUNCING_STRIKE = qualified(ADVERSARY, "Pouncing Strike")

POUNCE_DICE = 1
POUNCE_DIE = 12
POUNCE_MODIFIER = 2


@action(POUNCING_STRIKE)
def pouncing_strike(adversary, target, fight: Fight):
    """Mark a Stress to cross the field and land on somebody for 1d12+2.

    SRD: "Mark a Stress to have the Panther leap into Melee range of a target
    within Far range and make an attack against them. On a success, deal 1d12+2
    physical damage."

    The leap is movement and reaches nothing here; what the Stress buys is the
    bigger damage, 1d12+2 against the printed 1d8+1.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule decides when it is on the table - three slots against 4
    HP puts the Panther inside the line from full health.
    """
    if not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} breaks cover and lands on {target.name}")
    return adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=POUNCE_DICE, sides=POUNCE_DIE)],
        damage_modifier=POUNCE_MODIFIER,
        damage_type=DamageType.PHYSICAL,
    )


# --- Phantom, Poltergeist, Rabble Mawb, Rugaru, Gillbeast (SRD 2.0) ----------
#
# Two of these come back from the dead, which the catalogue had only ever seen the
# Skeleton Warrior do - and both are armed at the moment of defeat, which
# `on_damaged` already announces because it fires after the marking is settled.
# That is the Construct's *Death Quake* and the Skeleton Knight's *Dig Two Graves*
# arrangement; no new hook was needed for it.


INCORPOREAL = qualified(ADVERSARY, "Incorporeal")


@damage_resistance(
    INCORPOREAL,
    unmodelled=[
        "Moving through solid objects is movement and terrain, and neither has "
        "any representation here",
    ],
)
def incorporeal(adversary, damage_type, fight=None) -> float | None:
    """This adversary is resistant to physical damage, being barely there.

    SRD: "The Phantom has resistance to physical damage and can move through solid
    objects."

    **The Skeleton Warrior's `Only Bones` under a third printed name**, and
    registered separately rather than shared, which is the project's standing
    arrangement: one card, one place, and a reader looking up *Incorporeal* should
    find it. The rule itself is identical and the hook does the work.

    Halving lands before the Phantom's thresholds, and its Severe is printed
    `None` - so on a 2 HP stat block with a Major of 5 what this really buys is
    turning a 5-to-9 physical hit from 2 marked Hit Points into 1, which on a 2 HP
    track is the difference between dying to one blow and dying to two.

    Declines on anything that isn't physical, untyped damage included - a
    resistance applies to a type that was stated.
    """
    if not includes(damage_type, DamageType.PHYSICAL):
        return None
    return RESISTED


SPECTER = qualified(ADVERSARY, "Specter")


@damage_resistance(
    SPECTER,
    unmodelled=[
        "'Mark a Stress to move up to Close range through solid objects' is "
        "movement, and none is tracked - so the Poltergeist's Stress is never "
        "spent on it",
    ],
)
def specter(adversary, damage_type, fight=None) -> float | None:
    """This adversary is resistant to physical damage, being made of nothing.

    SRD: "The Poltergeist has resistance to physical damage. Mark a Stress to move
    up to Close range through solid objects."

    The third registration of the same rule, after the Skeleton Warrior's *Only
    Bones* and the Phantom's *Incorporeal* - separate for the reason each of those
    is, since the SRD gives one mechanic three names and a coverage block should
    say which one a stat block is carrying.

    With *Possessor* and *Ghost Storm* both dismissed on their triggers, this is
    the whole of what the Poltergeist has beyond its printed attack.
    """
    if not includes(damage_type, DamageType.PHYSICAL):
        return None
    return RESISTED


FEAR_AURA = qualified(ADVERSARY, "Fear Aura")

FEAR_AURA_DIFFICULTY = 10


@on_party_spotlight(FEAR_AURA)
def fear_aura(adversary, pc, fight=None) -> None:
    """Standing near this thing costs a Stress unless you can look at it.

    SRD: "A PC who takes the spotlight within Very Close range of the Phantom must
    succeed on a Presence Reaction Roll (10) or mark a Stress."

    **The reason `on_party_spotlight` exists.** The trigger is the spotlight
    arriving rather than a roll being made, and nothing on the GM's side of the
    table announced that. Registering on `convert_party_roll` and returning None -
    which fires about once per spotlight, and is the trick *Shallow Cuts* uses -
    was offered and declined by the user: a hook is meant to name a moment
    somebody at a table would recognise.

    SIMULATION RULE - policy. "Within Very Close range" is the area rule, asked per
    spotlight so who is standing near the Phantom is re-rolled rather than fixed -
    `chance_within` over the party, the handle Natural Familiar's d6 already uses.

    Difficulty 10 is printed, so nothing is invented here. A critical takes
    nothing, as every Reaction Roll does.

    Worth knowing before the Phantom is run: it has 2 Hit Points and 1 Stress, so
    nearly everything it is worth is this passive and the physical resistance -
    the Phantom is a tax on standing still rather than a thing that fights.
    """
    if fight is None:
        return

    party = len(fight.conscious_party)
    if party <= 0 or random.random() >= chance_within(Range.VERY_CLOSE, party):
        return

    roll = _reaction_roll(pc, "presence", FEAR_AURA_DIFFICULTY, fight)
    if roll.is_success:
        return
    pc.mark_stress(1)
    fight.note(f"{pc.name} feels the cold off {adversary.name} and marks a Stress ({roll})")


LINGERING_HAUNT = qualified(ADVERSARY, "Lingering Haunt")

LINGERING_HAUNT_FEAR = 1
LINGERING_HAUNT_DIE = 6
LINGERING_HAUNT_COUNTDOWN = "Lingering Haunt countdown"
LINGERING_HAUNT_SPENT = "Lingering Haunt spent"


@on_damaged(LINGERING_HAUNT)
def lingering_haunt_arms(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False,
    damage_type=None,
) -> None:
    """Spend a Fear as the Phantom goes down, and start the clock on its return.

    SRD: "*Countdown (1d6).* When the Phantom is defeated, you can spend a Fear to
    activate the countdown. It ticks down when a PC rolls with Fear. When it
    triggers, clear the Phantom's HP and immediately spotlight them."

    Fired from `on_damaged`, which runs after the marking has settled - so
    `is_defeated` is already true and the Phantom is arming this as it dies. That
    is the Construct's *Death Quake* arrangement and the Skeleton Knight's *Dig
    Two Graves*, and it is why no hook had to be added for "when this adversary is
    defeated".

    Armed **once**: a second token records that the Fear has been spent, so a body
    hit again does not buy a second haunting.

    USAGE POLICY - ruled. A Reaction, so it fires on the trigger whenever the Fear
    can be paid.
    """
    if fight is None or not adversary.is_defeated:
        return
    if fight.token_count(adversary, LINGERING_HAUNT_SPENT):
        return
    if not fight.spend_fear(LINGERING_HAUNT_FEAR):
        return

    fight.set_token(adversary, LINGERING_HAUNT_SPENT, 1)
    ticks = random.randint(1, LINGERING_HAUNT_DIE)
    fight.set_token(adversary, LINGERING_HAUNT_COUNTDOWN, ticks)
    fight.note(f"{adversary.name} dissipates, but not for good (countdown {ticks})")


@spotlight_while_defeated(LINGERING_HAUNT)
def lingering_haunt_lingers(adversary, fight=None) -> bool:
    """A Phantom with a countdown running is still on the field.

    The Skeleton Warrior's *Won't Stay Dead* hook, and it does two jobs here. It
    keeps the body a spotlight candidate, and - because `_gm_offers` scans the
    living **plus** whatever declares this - it is also what keeps the Phantom
    reachable by the dispatch that ticks its countdown. Without it the haunting
    would arm as the Phantom died and then never be asked about again.

    True only while the countdown is actually running, so a Phantom nobody paid a
    Fear for stays down.
    """
    if fight is None:
        return False
    return bool(fight.token_count(adversary, LINGERING_HAUNT_COUNTDOWN))


@on_party_attack_roll(LINGERING_HAUNT)
def lingering_haunt_ticks(adversary, roller, roll, fight=None) -> None:
    """Every roll with Fear brings the Phantom back a step; at zero it re-forms.

    SRD: "It ticks down when a PC rolls with Fear. When it triggers, clear the
    Phantom's HP and immediately spotlight them."

    Asked on **every PC action roll**, not only attacks: the loop guards this
    dispatch on `AttackResult.made_an_attack`, which means "this action rolled"
    rather than "this action was an attack" - the same discriminator Cloaking Blast
    reads. So a Spellcast that came up with Fear ticks the countdown exactly as a
    swing does.

    "Immediately spotlight them" is taken literally: the Phantom takes its turn on
    the spot, in the middle of the PC's spotlight, rather than waiting for the next
    GM turn. `take_adversary_turn` is imported at call time for the reason *On My
    Signal* imports its targeting rule that way - `combat/` reaches `content/`,
    which discovers this package, so the two can only meet inside a call.

    That spotlight costs the GM nothing further: the Fear was paid when the
    countdown was armed, which is what the page charges for the whole feature.
    """
    if fight is None or not fight.token_count(adversary, LINGERING_HAUNT_COUNTDOWN):
        return
    if roll.outcome is not DualityOutcome.FEAR:
        return

    fight.spend_tokens(adversary, LINGERING_HAUNT_COUNTDOWN, 1)
    left = fight.token_count(adversary, LINGERING_HAUNT_COUNTDOWN)
    if left > 0:
        fight.note(f"the air goes cold again ({adversary.name}: countdown {left})")
        return

    adversary.clear_hp(adversary.hp_max)
    fight.note(f"{adversary.name} re-forms out of the cold, and is on you")

    from combat.policy import take_adversary_turn

    take_adversary_turn(adversary, fight)


COME_BACK_WORSE = qualified(ADVERSARY, "Come Back Worse")

COME_BACK_WORSE_FEAR = 1
COME_BACK_TIMES = "Come Back Worse uses"


@on_damaged(COME_BACK_WORSE)
def come_back_worse(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False,
    damage_type=None,
) -> None:
    """Spend a Fear to stand the Mawb back up, angrier each time.

    SRD: "When the Rabble Mawb is defeated, you can **spend a Fear** to bring it
    back to life, clearing all HP and Stress. The Rabble Mawb gains a bonus to all
    rolls equal to the number of times this feature has been used by this Rabble
    Mawb."

    Fired from `on_damaged` with `is_defeated` already true - the *Death Quake*
    arrangement. Clearing the HP puts it back into `living_adversaries` on its own,
    since that list is derived rather than stored, so nothing has to re-add it.

    USAGE POLICY - ruled. **Uncapped**, which is the page read literally: the Fear
    pool is the only limit, and every revival is a Fear the GM did not spend on an
    activation. Capping it at one, and at a tunable constant, were both offered and
    declined - the same reasoning that left the Jagged Knife Lieutenant's *More
    Where That Came From* unbounded. A Reaction, so it fires whenever the Fear can
    be paid.

    Worth watching when this is run: a Rabble Mawb is the first thing in the
    catalogue that can make a fight longer without limit, and `MAX_PC_ACTIONS` is
    the only backstop.
    """
    if fight is None or not adversary.is_defeated:
        return
    if not fight.spend_fear(COME_BACK_WORSE_FEAR):
        return

    used = fight.token_count(adversary, COME_BACK_TIMES) + 1
    fight.set_token(adversary, COME_BACK_TIMES, used)
    adversary.clear_hp(adversary.hp_max)
    adversary.clear_stress(adversary.stress_max)
    fight.note(f"{adversary.name} boils back up, worse than before (+{used})")


@attack_roll_bonus(COME_BACK_WORSE)
def come_back_worse_sharpens(adversary, target, fight=None) -> int:
    """+1 to this adversary's attack rolls for every time it has been killed.

    Half of "a bonus to **all** rolls"; the other half is the Reaction Roll
    registration below. An adversary makes exactly those two kinds of roll, so
    between them the page is covered.
    """
    if fight is None:
        return 0
    return fight.token_count(adversary, COME_BACK_TIMES)


@reaction_roll_bonus(COME_BACK_WORSE)
def come_back_worse_steadies(adversary, fight=None) -> int:
    """And the same bonus on its Reaction Rolls, which is the rest of "all rolls".

    Registered on the same name as its sibling above - one printed clause, two
    kinds of roll - and the reason `reaction_roll_bonus` exists at all: nothing
    reached the flat d20 an adversary throws to save.
    """
    if fight is None:
        return 0
    return fight.token_count(adversary, COME_BACK_TIMES)


CHILD_OF_NIGHT = qualified(ADVERSARY, "Child of Night")


@difficulty_bonus(CHILD_OF_NIGHT)
def child_of_night(adversary) -> int:
    """+X to this adversary's Difficulty, because it is fighting under a moon.

    SRD: "While in moonlight, the Rugaru gains a +2 bonus to their Difficulty."

    SIMULATION RULE - policy, ruled. `Flying (X)`'s treatment of a qualifier
    nothing represents: **the parameter is where "while in moonlight" goes**, so
    the catalogue writes `Child of Night (2)` for a Rugaru hunting at night and a
    smaller number - or no feature at all - for one dragged into daylight. Reading
    it as simply always on (the *Sage-Touched* ruling) and dismissing it outright
    were both offered and declined.

    Resolved into `Adversary.difficulty` at spawn, so the four places that read
    Difficulty never learn this exists. A stat block writing the name bare gets
    nothing rather than a guess, exactly as Relentless and Flying do.
    """
    written = feature_parameter(adversary, CHILD_OF_NIGHT)
    if written is None:
        return 0
    try:
        return int(written)
    except ValueError:
        return 0


BLOODTHIRSTY = qualified(ADVERSARY, "Bloodthirsty")

BLOODTHIRSTY_TOKENS = "Bloodthirsty tokens"

# Raised by a feature around an attack of its own, so content counting the
# **standard** attack can tell the two apart. `on_hit` fires for whatever an
# adversary swung with and carries nothing that says which it was; the SRD keys
# several features on the standard attack specifically, so the discrimination is
# done by whoever knows - the feature bringing its own dice.
NOT_THE_STANDARD_ATTACK = "not the standard attack"


@on_hit(BLOODTHIRSTY)
def bloodthirsty(adversary, target, result, fight: Fight) -> None:
    """Every wound its jaws open makes the next bite land easier.

    Counted off the **standard attack** only, which is what the page says. `on_hit`
    fires for whatever the adversary swung with and cannot tell one from another,
    so the discrimination is done from the other end: the Rugaru's only other
    attack is *Flesh Ripper*, and that feature raises a flag around its own swing
    which this reads and skips. A stat block carrying Bloodthirsty and no such
    feature needs nothing.
    """
    if fight is None or not result.hp_marked:
        return
    if fight.token_count(adversary, NOT_THE_STANDARD_ATTACK):
        return
    tokens = fight.token_count(adversary, BLOODTHIRSTY_TOKENS) + 1
    fight.set_token(adversary, BLOODTHIRSTY_TOKENS, tokens)
    fight.note(f"{adversary.name} tastes blood (Bloodthirsty: {tokens})")


@attack_roll_bonus(BLOODTHIRSTY)
def bloodthirsty_sharpens(adversary, target, fight=None) -> int:
    """+1 to attack rolls for every token on the stat block.

    SRD: "When a PC marks HP from the Rugaru's standard attack, add a token to this
    stat block. The Rugaru gains a bonus to attack rolls equal to the number of
    tokens on this stat block. Clear all tokens when the Rugaru takes Severe
    damage."

    Tokens on the stat block rather than in a Pool, which is the page: this one is
    the Rugaru's own, where the Mechanorb's is shared. It is a **runaway** - each
    wound makes the next easier to land - and the only thing that stops it is the
    party landing a Severe hit, which is what the third clause is for.
    """
    if fight is None:
        return 0
    return fight.token_count(adversary, BLOODTHIRSTY_TOKENS)


@on_damaged(BLOODTHIRSTY)
def bloodthirsty_is_broken(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False,
    damage_type=None,
) -> None:
    """A Severe hit knocks the taste out of its mouth.

    Read off the **damage** against the Rugaru's own Severe threshold rather than
    off the Hit Points marked, the way every other "takes Severe damage" trigger in
    the catalogue reads it.
    """
    if fight is None or amount < adversary.severe_threshold:
        return
    if not fight.token_count(adversary, BLOODTHIRSTY_TOKENS):
        return
    fight.set_token(adversary, BLOODTHIRSTY_TOKENS, 0)
    fight.note(f"{adversary.name} is hurt badly enough to lose the scent")


HOWL_AT_THE_MOON = qualified(ADVERSARY, "Howl at the Moon")

HOWL_DIFFICULTY = 15


@action(HOWL_AT_THE_MOON)
def howl_at_the_moon(adversary, target, fight: Fight):
    """Mark a Stress: everyone within Far loses a Hope, and the GM banks each one.

    SRD: "Mark a Stress to force each PC within Far range to make a Presence
    Reaction Roll (15). Targets who fail lose a Hope. Gain a Fear for each Hope
    lost. If a PC has no Hope, they must mark a Stress and become *Vulnerable*
    until they roll with Hope."

    **A Hope taken off the party and a Fear handed to the GM at once**, which is
    the most direct economy attack in tier 1 - the Hexer's Curse does it one roll
    at a time and this does it to the whole party for one Stress. Difficulty 15 is
    printed and is high for tier 1.

    The branch on having no Hope is the page read literally, and it makes the
    feature *worse* against a party that has already been drained: a PC with
    nothing to lose marks a Stress and goes Vulnerable instead.

    Far reaches everyone but one a quarter of the time, so this is close to a
    party-wide effect every time it is used.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule decides when it is on the table.
    """
    if fight is None or not adversary.will_spend_stress(1):
        return None

    party = fight.conscious_party
    caught = party[: targets_reached(Range.FAR, len(party))] if party else []
    if not caught:
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} throws its head back and howls")
    for pc in caught:
        roll = _reaction_roll(pc, "presence", HOWL_DIFFICULTY, fight)
        if roll.is_success:
            fight.note(f"{pc.name} holds against the howl ({roll})")
            continue
        if pc.can_spend_hope(1):
            pc.spend_hope(1)
            fight.gain_fear(1)
            fight.note(f"{pc.name} loses a Hope to the howl, and the GM banks it")
            continue
        pc.mark_stress(1)
        fight.apply_condition(pc, Condition(name=VULNERABLE, source=adversary))
        fight.note(f"{pc.name} has no Hope left and breaks ({VULNERABLE})")
    return AttackResult(attack_roll=None, damage_roll=None)


@on_party_attack_roll(HOWL_AT_THE_MOON)
def howl_at_the_moon_lifts(adversary, roller, roll, fight=None) -> None:
    """The Vulnerable this feature applies ends on its victim's next roll with Hope.

    A condition's own `end` predicate is asked at announced moments and is never
    shown a roll, so the ender lives here instead - the one place GM-side content
    is told how a PC's roll came out. Only a Vulnerable **this** Rugaru applied is
    lifted, read off `Condition.source`, so a Vulnerable from anywhere else is left
    where it is.

    Asked on every PC **action roll** rather than on attacks alone: the loop guards
    this dispatch on `made_an_attack`, which means "this action rolled". So any roll
    that comes up with Hope lifts it, which is the page.
    """
    if fight is None:
        return
    if roll.outcome not in (DualityOutcome.HOPE, DualityOutcome.CRIT):
        return
    held = fight.condition_on(roller, VULNERABLE)
    if held is None or held.source is not adversary:
        return
    fight.clear_condition(roller, VULNERABLE)
    fight.note(f"{roller.name} finds their nerve again")


FLESH_RIPPER = qualified(ADVERSARY, "Flesh Ripper")

FLESH_RIPPER_DICE = 1
FLESH_RIPPER_DIE = 12
FLESH_RIPPER_MODIFIER = 2


@action(FLESH_RIPPER)
def flesh_ripper(adversary, target, fight: Fight):
    """Mark a Stress for 1d12+2 that no Armor Slot can soften.

    SRD: "Mark a Stress to make an attack against a target within Melee range. On a
    success, deal 1d12+2 **direct** physical damage."

    Direct is stated on the attack rather than granted by a passive, which is what
    `Adversary.attack`'s `direct` argument is for - the Dire Wolf's *Hobbling
    Strike* shape. Against a party that marks a free Armor Slot against everything,
    that is worth close to a whole extra Hit Point on top of the dice.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule gates it - four slots against 8 HP puts the Rugaru
    inside the line from full health.
    """
    if not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} tears into {target.name}")

    # Raised around the swing so *Bloodthirsty* can tell this from the standard
    # attack it is actually counting - see there. Cleared in a `finally` so a
    # feature that raises cannot leave the flag standing.
    fight.set_token(adversary, NOT_THE_STANDARD_ATTACK, 1)
    try:
        return adversary.attack(
            target,
            fight=fight,
            damage_dice=[DiceGroup(count=FLESH_RIPPER_DICE, sides=FLESH_RIPPER_DIE)],
            damage_modifier=FLESH_RIPPER_MODIFIER,
            direct=True,
            damage_type=DamageType.PHYSICAL,
        )
    finally:
        fight.set_token(adversary, NOT_THE_STANDARD_ATTACK, 0)


KA_CHOMP = qualified(ADVERSARY, "Ka-Chomp")

KA_CHOMP_DICE = 1
KA_CHOMP_DIE = 12


@action(KA_CHOMP)
def ka_chomp(adversary, target, fight: Fight):
    """Mark a Stress: 1d12, and a wasted Armor Slot on top of it.

    SRD: "Mark a Stress to attack a target within Melee range. On a success, the
    target takes 1d12 physical damage and must mark an Armor Slot without gaining
    its benefit (they can still use armor to reduce the damage)."

    The burned slot is the clause the Acid Burrower's *Spit Acid* and both Oozes'
    *Acidic Form* print word for word, so it goes through the shared helper: a slot
    if there is one, and an additional Hit Point if there is not. That second half
    is what makes this dangerous against a PC who has already spent their armor.

    USAGE POLICY - ruled. An Action costing Stress. Two slots against 4 HP means
    the Gillbeast is inside the desperation line from full health.
    """
    if not adversary.will_spend_stress(1):
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} lunges at {target.name} (Ka-Chomp)")
    result = adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=KA_CHOMP_DICE, sides=KA_CHOMP_DIE)],
        damage_modifier=0,
        damage_type=DamageType.PHYSICAL,
    )
    if not result.made_an_attack or not result.attack_roll.is_success:
        return result

    _burn_an_armor_slot(target, fight)
    return result


FEEDING_FRENZY = qualified(ADVERSARY, "Feeding Frenzy")

FEEDING_FRENZY_FEAR = 1

# Raised while a frenzy is resolving, so the school's own bites cannot start
# another one. A **pool** rather than a token because the guard belongs to the
# feature rather than to any one fish: whichever Gillbeast answered, none of them
# may re-enter. See the docstring for why this is a guard rather than a rule.
FRENZY_UNDERWAY = "Feeding Frenzy underway"


@adversary_on_damaged(FEEDING_FRENZY)
def feeding_frenzy(adversary, target, amount: int, hp_marked: int, fight=None) -> None:
    """Blood in the water: every Gillbeast nearby piles onto whoever is bleeding.

    SRD: "When a creature marks HP, you can **spend a Fear** to spotlight all
    Sawtoothed Gillbeasts within Very Close range of them. Those Gillbeasts move
    into Melee range of the creature and each make a standard attack against them.
    If any attacks succeed, combine their damage."

    SIMULATION RULE - policy, ruled. **"A creature" includes the GM's own side**,
    the standing printed-noun rule, so a school of Gillbeasts turns on a wounded
    ally exactly as it turns on a wounded PC. Reading it as the party only, and as
    anything-but-another-Gillbeast, were both offered and declined. A Gillbeast
    fielded beside anything else is a liability to it, which is a real cost for
    whoever builds the encounter.

    **The reason `adversary_on_damaged` exists.** `on_damaged` is holder-scoped on
    whoever took the wound, so nothing let one adversary hear about another being
    hurt - the gap `on_ally_defeated` closed for defeat, one step earlier.

    The successes are **combined into one damage roll**, which is the Head Guard's
    *On My Signal* arithmetic and the whole reason the feature is frightening:
    three separate hits of 6 mark 3 Hit Points, one combined 18 is Severe.

    Every Gillbeast swept has been spotlighted, so each spends an activation - the
    Group Attack rule - and the school does not come round again this GM turn.

    One of them answers for the school, the *Shallow Cuts* arrangement, so a Fear
    buys one frenzy rather than one per fish.

    USAGE POLICY - ruled. A Reaction, so it fires whenever the Fear can be paid,
    and it declines when the wounded creature is the only Gillbeast in range - the
    standing zero-benefit rule.

    **One frenzy per wound**, which is a guard rather than a printed limit: the
    school's own bites make their victim mark HP, and that is this feature's
    trigger, so an unguarded version would feed on itself until the Fear pool was
    empty. The page describes one reaction to one wound.
    """
    if fight is None or hp_marked <= 0:
        return
    # A frenzy's own bites make their victim mark HP, which is this very trigger -
    # so without a guard the school would feed on itself until the Fear ran out.
    # Held back rather than allowed: the page describes one reaction to one wound,
    # and a GM does not pay a second Fear for the blood the first one drew.
    if fight.pool_count(FRENZY_UNDERWAY):
        return

    school = [
        other
        for other in fight.living_adversaries
        if canonical(other.name) == canonical(adversary.name) and other is not target
    ]
    if not school or school[0] is not adversary:
        return

    biting = school[: targets_reached(Range.VERY_CLOSE, len(school))]
    if not biting:
        return
    if not fight.spend_fear(FEEDING_FRENZY_FEAR):
        return

    fight.note(f"{len(biting)} {adversary.name}s turn on {target.name}")

    # A PC is swung at against Evasion and an adversary against its Difficulty -
    # the same split `Adversary.attack` and `area_attack` keep, and the reason
    # this feature needs it at all is that its target can be either. Worked out
    # once, outside the closure, like every other pre-roll decision.
    beat = getattr(target, "evasion", None)
    if beat is None:
        beat = target.difficulty

    hits = 0
    critical = False
    fight.add_to_pool(FRENZY_UNDERWAY, 1)
    try:
        for fish in biting:
            fight.consume_activation(fish)

            def swing(biter=fish):
                return roll_d20(
                    modifier=biter.attack_modifier + total_attack_roll_bonus(
                        biter, target, fight
                    ),
                    evasion=beat,
                )

            bite = force_adversary_reroll(fish, target, swing(), swing, fight)
            if bite.is_success:
                hits += 1
                critical = critical or bite.is_critical

        if not hits:
            fight.note(f"{target.name} thrashes clear of every one of them")
            return

        biter = biting[0]
        damage = roll_damage(
            dice_groups=[
                DiceGroup(count=group.count * hits, sides=group.sides)
                for group in biter.damage_dice
            ],
            modifier=biter.damage_modifier * hits,
            is_critical=critical,
        )
        target.take_damage(
            damage.total,
            fight,
            direct=deals_direct_damage(biter, fight),
            damage_type=biter.type_of_damage(),
        )
        fight.note(
            f"{hits} of the school land on {target.name} for {damage.total} combined"
        )
    finally:
        fight.clear_pool(FRENZY_UNDERWAY)


SCALY = qualified(ADVERSARY, "Scaly")

SCALY_DIE = 6
SCALY_SAVES_ON = 6


@severity_response(SCALY)
def scaly(adversary, amount: int, hp_to_mark: int, fight=None, damage_type=None) -> int:
    """A one-in-six chance the scales turn a wound into a Stress instead.

    SRD: "When the Gillbeast would mark any number of HP, roll a d6. On a result of
    6, you can mark a Stress instead."

    "Any number of HP" is the whole marking, so a Severe hit that would have cost
    three Hit Points costs one Stress - which is what makes a one-in-six worth
    having on a 4 HP stat block.

    USAGE POLICY - ruled. A Reaction, so it fires whenever the Stress can be paid;
    the desperation rule deliberately does not gate it. With the track full the
    scales simply do not help, since the Stress is a cost rather than something
    forced.
    """
    if fight is None or hp_to_mark <= 0:
        return hp_to_mark
    if not adversary.can_spend_stress(1):
        return hp_to_mark
    if random.randint(1, SCALY_DIE) != SCALY_SAVES_ON:
        return hp_to_mark

    adversary.spend_stress(1)
    fight.note(f"{adversary.name}'s scales turn the blow ({hp_to_mark} HP to a Stress)")
    return 0


# --- The last of tier 1 (SRD 2.0) --------------------------------------------
#
# Soul-Shattered Mage, Spellbound Armor, Viper, Waxwork Creation and the
# Will-o'-the-Wisps. Yufo is the fourth Social and is skipped by rule.


BROKEN_MAGIC = qualified(ADVERSARY, "Broken Magic")

BROKEN_MAGIC_DIE = 6
DIMENSION_RIFT_DICE = 2
DIMENSION_RIFT_DIE = 6
DISCORDANT_DICE = 2
DISCORDANT_DIE = 8
DISCORDANT_TARGETS = 3


@action(BROKEN_MAGIC)
def broken_magic(adversary, target, fight: Fight):
    """Mark a Stress and roll a d6 for which of three broken spells comes out.

    SRD: "Mark a Stress to roll a d6. The Mage uses the corresponding move:
    1-2 *Dimension Rift* ... 3-4 *Time Dilation* ... 5-6 *Discordant Visions*."

    A printed random table, so there is no policy to write for **which** move -
    the die decides, which is the rare case where the SRD has already made the
    choice this module usually has to be told.

    USAGE POLICY - ruled. An Action costing Stress, so the standing
    Stress-desperation rule decides when it is on the table. Five slots against 6
    HP puts the Mage inside that line from full health.
    """
    if fight is None or not adversary.will_spend_stress(1):
        return None

    party = fight.conscious_party
    if not party:
        return None

    adversary.spend_stress(1)
    rolled = random.randint(1, BROKEN_MAGIC_DIE)

    if rolled <= 2:
        damage = roll_damage(
            dice_groups=[DiceGroup(count=DIMENSION_RIFT_DICE, sides=DIMENSION_RIFT_DIE)],
            modifier=0,
        )
        target.take_damage(
            damage.total, fight, direct=True, damage_type=DamageType.MAGIC
        )
        fight.note(
            f"{adversary.name} tears {target.name} apart and back together "
            f"for {damage.total} direct (Dimension Rift)"
        )
        return AttackResult(attack_roll=None, damage_roll=damage)

    if rolled <= 4:
        caught = party[: targets_reached(Range.FAR, len(party))]
        for pc in caught:
            if fight.has_condition(pc, SLOWED):
                continue
            fight.apply_condition(pc, Condition(name=SLOWED, source=adversary))
        fight.note(f"{adversary.name} stretches time around {len(caught)} (Slowed)")
        return AttackResult(attack_roll=None, damage_roll=None)

    caught = party[: min(targets_reached(Range.CLOSE, len(party)), DISCORDANT_TARGETS)]
    if not caught:
        return AttackResult(attack_roll=None, damage_roll=None)
    fight.note(f"{adversary.name} shows {len(caught)} something they cannot unsee")
    result, _ = adversary.area_attack(
        caught,
        fight=fight,
        damage_dice=[DiceGroup(count=DISCORDANT_DICE, sides=DISCORDANT_DIE)],
        damage_modifier=0,
        direct=True,
        damage_type=DamageType.MAGIC,
    )
    return result


@on_party_attack_roll(BROKEN_MAGIC)
def broken_magic_time_resumes(adversary, roller, roll, fight=None) -> None:
    """*Slowed* lasts "until they roll with Hope", which no `end` predicate can see.

    The Rugaru's *Howl at the Moon* ender, registered the same way and for the same
    reason: a condition's `end` is asked at announced moments and is never shown a
    roll, so the one place GM-side content is told how a PC's roll came out is
    here. Only a *Slowed* this Mage applied is lifted, read off `Condition.source`.
    """
    if fight is None:
        return
    if roll.outcome not in (DualityOutcome.HOPE, DualityOutcome.CRIT):
        return
    held = fight.condition_on(roller, SLOWED)
    if held is None or held.source is not adversary:
        return
    fight.clear_condition(roller, SLOWED)
    fight.note(f"time snaps back for {roller.name}")


FEEL_MY_PAIN = qualified(ADVERSARY, "Feel My Pain")

FEEL_MY_PAIN_DIE = 6


@on_damaged(FEEL_MY_PAIN)
def feel_my_pain(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False,
    damage_type=None,
) -> None:
    """Every wound the Mage takes is shared out, and its Stress is the multiplier.

    SRD: "When the Mage marks HP, roll a number of d6s equal to the number of
    Stress the Mage has marked. The Mage deals direct magic damage equal to the
    total result to all PCs within Very Close range."

    **The Mage's own Stress is the weapon**, which inverts the usual reading of a
    Stress track: *Broken Magic* spends Stress to act and every spent slot makes
    this Reaction bigger, so a Mage that has been casting hard hurts far more to
    kill. At five marked that is 5d6 direct, shared by everyone standing close.

    Direct, so no Armor Slot softens it, and one roll dealt to everyone caught -
    the page describes one burst, not a roll per PC.

    Keyed on Hit Points actually marked, which is what the trigger says. Zero
    marked Stress means zero dice, which the standing zero-benefit rule would stop
    anyway; the Reaction costs nothing, so there is nothing else to gate.
    """
    if fight is None or hp_marked <= 0 or not adversary.stress_marked:
        return

    party = fight.conscious_party
    caught = party[: targets_reached(Range.VERY_CLOSE, len(party))] if party else []
    if not caught:
        return

    damage = roll_damage(
        dice_groups=[DiceGroup(count=adversary.stress_marked, sides=FEEL_MY_PAIN_DIE)],
        modifier=0,
    )
    fight.note(
        f"{adversary.name} shares the pain with {len(caught)} for {damage.total}"
    )
    for pc in caught:
        pc.take_damage(damage.total, fight, direct=True, damage_type=DamageType.MAGIC)


TIRELESS = qualified(ADVERSARY, "Tireless")


@stress_refusal(TIRELESS)
def tireless(adversary, amount: int, fight=None) -> bool:
    """This adversary ignores Stress outright - it cannot be worn down.

    SRD: "The Armor can't be forced to mark Stress. When an effect would cause it
    to mark Stress, the Armor ignores that part of the effect."

    **The reason `stress_refusal` exists.** The Armor prints `Stress: None`, so its
    track is zero-length - and a zero-length track is not a refusal, it is a track
    that is always full, which the SRD's overflow rule turns into a Hit Point for
    every Stress anybody forces on it. That is the opposite of what the page says,
    and no existing hook could say "ignore it": `condition_refusal` next door
    refuses a condition, not a cost.

    Worth knowing what it is worth: every party feature that forces Stress onto an
    adversary - Death Grip, Hypnotic Shimmer, a wall of hunger - does nothing at
    all to this stat block.
    """
    return True


CLATTER_AND_RECOMBOBULATE = qualified(ADVERSARY, "Clatter & Recombobulate")

CLATTER_FEAR = 1
CLATTER_CLEARS = 2


@on_damaged(CLATTER_AND_RECOMBOBULATE)
def clatter_and_recombobulate(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False,
    damage_type=None,
) -> None:
    """Once a scene, spend a Fear to put the Armor back together and act at once.

    SRD: "Once per scene when the Armor is defeated, you can spend a Fear to
    reactivate it. Clear 2 HP and immediately spotlight it."

    Fired from `on_damaged` with `is_defeated` already true - the Construct's
    *Death Quake* arrangement, and the same shape the Rabble Mawb's *Come Back
    Worse* takes. Where that one is uncapped, this prints "once per scene" and gets
    it, through the per-rest machinery scoped to this fight.

    It clears **2** Hit Points rather than all of them, so the Armor comes back at
    a third of its track and the party has done real work - which is what separates
    it from the Mawb, whose revival is total.

    "Immediately spotlight it" is taken literally: the Armor takes its turn on the
    spot rather than waiting for the next GM turn, the reading *Lingering Haunt*
    already got. The Fear paid here is what buys that spotlight.
    """
    if fight is None or not adversary.is_defeated:
        return
    if not fight.can_use_once_per_rest(adversary, CLATTER_AND_RECOMBOBULATE):
        return
    if not fight.spend_fear(CLATTER_FEAR):
        return

    fight.use_once_per_rest(adversary, CLATTER_AND_RECOMBOBULATE)
    adversary.clear_hp(CLATTER_CLEARS)
    fight.note(f"{adversary.name} clatters back together and comes on again")

    from combat.policy import take_adversary_turn

    take_adversary_turn(adversary, fight)


VENOMOUS = qualified(ADVERSARY, "Venomous")


def _envenomation(holder, fight, moment: str) -> None:
    """A Stress before every action roll, for as long as the venom is in them."""
    if moment != BEFORE_AN_ACTION_ROLL:
        return
    holder.mark_stress(1)
    fight.note(f"{holder.name} works against the venom (Envenomated: a Stress)")


@on_hit(VENOMOUS)
def venomous(adversary, target, result, fight: Fight) -> None:
    """A landed bite leaves the target paying a Stress for every roll they make.

    SRD: "When the Viper makes a successful standard attack, the target becomes
    temporarily *Envenomated*. While *Envenomated*, the target must mark a Stress
    whenever they make an action roll."

    Mechanically the Darkweave Crawler's *Exhausted*, and kept as its own condition
    name so a report says which creature did it. Unlike Exhausted it prints **no
    way out**, so "temporarily" takes the standing reading and it lasts the fight -
    which on a Minion with a 1-damage bite is most of what a Viper is for.

    USAGE POLICY - ruled. A Passive with no cost, gated only by the standing
    don't-re-apply rule: a target already Envenomated gains nothing from a second
    dose, since the condition neither stacks nor refreshes an ender it does not
    have.
    """
    if fight is None or not result.made_an_attack:
        return
    if fight.has_condition(target, ENVENOMATED):
        return

    fight.apply_condition(
        target,
        Condition(name=ENVENOMATED, effect=_envenomation, source=adversary),
    )
    fight.note(f"{target.name} is bitten ({ENVENOMATED})")


NO_VITAL_ORGANS = qualified(ADVERSARY, "No Vital Organs")


@critical_refusal(NO_VITAL_ORGANS)
def no_vital_organs(adversary, attacker, fight=None) -> bool:
    """A critical against this adversary finds nothing worth hitting twice.

    SRD: "The Creation doesn't take extra damage from attacks that critically
    succeed against it."

    **The bonus goes, the critical stays.** A critical still succeeds regardless of
    Difficulty, which is most of what a natural 20 buys; what this denies is the
    maximum-damage-dice bonus riding on top. See `critical_refusal` for why no
    softening hook could express that - all three receive a number with the bonus
    already baked in.

    On a 10 HP Solo with thresholds of 8 and 15 that is a real defence: a critical
    is exactly the roll most likely to push a party's damage across the Severe
    line, and against the Creation it no longer does so for free.
    """
    return True


WAX_BALL = qualified(ADVERSARY, "Wax Ball")

WAX_BALL_DICE = 1
WAX_BALL_DIE = 12
WAX_BALL_MODIFIER = 2
WAX_BALL_DIFFICULTY = 15


@action(WAX_BALL)
def wax_ball(adversary, target, fight: Fight):
    """Mark a Stress to throw a ball of wax that sticks whoever it hits.

    SRD: "Mark a Stress to have the Creation throw a ball of wax at a target within
    Far range. Make an attack against the target. On a success, the target takes
    1d12+2 physical damage and becomes *Restrained* until they succeed on a
    Strength Roll (15)."

    The escape roll is printed with its own Difficulty, so nothing is invented -
    and it is a hard one, which is what the Restrain is priced on.

    USAGE POLICY - ruled. An Action costing Stress, gated by the standing
    Stress-desperation rule, and held back against a target this Creation has
    already Restrained per the standing don't-re-apply rule.
    """
    if fight is None or not adversary.will_spend_stress(1):
        return None
    held = fight.condition_on(target, RESTRAINED)
    if held is not None and held.source is adversary:
        return None

    adversary.spend_stress(1)
    fight.note(f"{adversary.name} lobs a ball of wax at {target.name}")
    result = adversary.attack(
        target,
        fight=fight,
        damage_dice=[DiceGroup(count=WAX_BALL_DICE, sides=WAX_BALL_DIE)],
        damage_modifier=WAX_BALL_MODIFIER,
        damage_type=DamageType.PHYSICAL,
    )
    if not result.made_an_attack or not result.attack_roll.is_success:
        return result

    fight.apply_condition(
        target,
        Condition(
            name=RESTRAINED,
            end=_breaks_free(("strength",), WAX_BALL_DIFFICULTY),
            source=adversary,
        ),
    )
    fight.note(f"{target.name} is stuck fast ({RESTRAINED})")
    return result


SPLUTCH = qualified(ADVERSARY, "Splutch!")

SPLUTCH_DIE = 6
SPLUTCH_STICKS_ON = 5
SPLUTCH_DIFFICULTY = 15


@on_attacked(SPLUTCH)
def splutch(adversary, attacker, weapon, damage, hp_marked, fight=None) -> None:
    """A weapon swung into the wax has a fair chance of staying there.

    SRD: "When a PC within Melee range of the Creation makes a weapon attack
    against it, roll a d6. On a 5 or higher, the attacker's weapon gets stuck in
    the Creation and can be removed only with a successful Strength Roll (15)."

    SIMULATION RULE - policy, ruled. A stuck weapon means the PC **cannot make
    weapon attacks** until they pull it free, and keeps everything else they could
    do - their domain cards, their spells. Losing the whole spotlight
    (`prevents_action`, the *Enchanted* treatment) and swinging at Disadvantage
    were both offered and declined. It is the first condition anywhere to take a
    PC's weapon rather than their turn, which is what `prevents_weapon_attack` is.

    "Within Melee range" is read off the attacker's weapon, the standing handle -
    so a bow is never stuck in the wax and an archer is untouched by this entirely.

    A one-in-three chance on every melee swing, with a Strength Roll (15) out at
    each announced moment. Fires whether or not the attack hurt the Creation, which
    is what the trigger says - the swing is what gets stuck.
    """
    if fight is None or weapon is None:
        return
    if band_named(weapon.range) is not Range.MELEE:
        return
    if fight.has_condition(attacker, WEAPON_STUCK):
        return
    if random.randint(1, SPLUTCH_DIE) < SPLUTCH_STICKS_ON:
        return

    fight.apply_condition(
        attacker,
        Condition(
            name=WEAPON_STUCK,
            end=_breaks_free(("strength",), SPLUTCH_DIFFICULTY),
            source=adversary,
            prevents_weapon_attack=True,
        ),
    )
    fight.note(f"{attacker.name}'s weapon sticks fast in {adversary.name}")


SMOTHERING_GRAPPLE = qualified(ADVERSARY, "Smothering Grapple")

SMOTHERING_FEAR = 1


@on_hit(SMOTHERING_GRAPPLE)
def smothering_grapple(adversary, target, result, fight: Fight) -> None:
    """Spend a Fear on a landed standard attack to pull somebody inside the wax.

    SRD: "When the Creation makes a successful standard attack against a target
    within Melee range, you can spend a Fear to *Trap* the target inside the
    Creation's wax body. While *Trapped*, the target is *Restrained* and must mark
    a Stress and move with the Creation each time it's spotlighted. A *Trapped*
    creature is freed when the Creation takes Major or greater damage."

    *Trapped* is its own condition, the standing call for a state the page names -
    and here the name does real work, because the upkeep is charged on the
    **Creation's** spotlights rather than its holder's, which no `Condition.effect`
    can express. The Creation's own `on_spotlight` below does it.

    A Restrained record goes on beside it so other content can still see the hold.
    Neither carries an `end`, because the printed way out is something happening to
    the Creation rather than to the victim - which `release_conditions_from`
    already answers for a source-tagged condition with no ender of its own, and
    which the damage response below answers for a Major hit.

    USAGE POLICY - ruled. A Reaction, so it fires whenever the Fear can be paid,
    and it declines against a target already Trapped per the don't-re-apply rule.
    """
    if fight is None or not result.made_an_attack:
        return
    if fight.has_condition(target, TRAPPED):
        return
    if not fight.spend_fear(SMOTHERING_FEAR):
        return

    fight.apply_condition(target, Condition(name=TRAPPED, source=adversary))
    fight.apply_condition(target, Condition(name=RESTRAINED, source=adversary))
    fight.note(f"{adversary.name} folds {target.name} into its body ({TRAPPED})")


@on_spotlight(SMOTHERING_GRAPPLE)
def smothering_grapple_smothers(adversary, fight=None) -> None:
    """Everyone inside the wax pays a Stress each time the Creation is spotlighted.

    Charged here rather than from the condition, because a condition's effect fires
    at **its holder's** announced moments and the page charges this on the
    Creation's. Registered on the same name as the Reaction above, which is the
    *Hand of Glory* arrangement.

    The Stress is forced, so a full track overflows into a Hit Point - which is how
    being smothered eventually kills somebody.
    """
    if fight is None:
        return
    for pc in fight.conscious_party:
        held = fight.condition_on(pc, TRAPPED)
        if held is None or held.source is not adversary:
            continue
        pc.mark_stress(1)
        fight.note(f"{pc.name} is crushed deeper into the wax (a Stress)")


@on_damaged(SMOTHERING_GRAPPLE)
def smothering_grapple_releases(
    adversary, amount: int, hp_marked: int, fight=None, marked_armor: bool = False,
    damage_type=None,
) -> None:
    """A Major hit on the Creation breaks it open and frees whoever is inside.

    Read off the **damage** against the Creation's own Major threshold rather than
    off the Hit Points marked, the way every other threshold trigger in the
    catalogue reads it. Frees the Restrain with the Trap, so nobody is left half
    held.
    """
    if fight is None or amount < adversary.major_threshold:
        return
    for pc in fight.conscious_party:
        held = fight.condition_on(pc, TRAPPED)
        if held is None or held.source is not adversary:
            continue
        fight.clear_condition(pc, TRAPPED)
        _release_held(adversary, fight, RESTRAINED)
        fight.note(f"the wax splits and {pc.name} is free")


KALEIDOSCOPIC = qualified(ADVERSARY, "Kaleidoscopic")

WISPS = canonical("Will-o'-the-Wisps")


@adversary_on_spotlight(KALEIDOSCOPIC)
def kaleidoscopic(adversary, spotlighted, fight=None, paid: bool = False) -> None:
    """Anybody watching the lights is Vulnerable, re-drawn as the field moves.

    SRD: "All targets within Very Close range of the Will-o'-the-Wisps are
    *Vulnerable*."

    The Harpy's *Toxic Aura* exactly, and it takes that ruling: a standing aura
    whose membership is **re-drawn at every adversary spotlight**, with the previous
    draw lifted first so it is something people walk out of rather than something
    that accumulates.

    One difference from the Harpy, and it is the printed noun: this says "all
    **targets**", not "all creatures", so it is the party only and the Wisps' own
    side is untouched. *Scorched Earth* and *Hellfire* are the pair that made that
    distinction worth reading carefully.

    Only conditions this swarm applied are lifted, and a PC already Vulnerable from
    elsewhere is left alone rather than having their own ender overwritten.
    """
    if fight is None:
        return

    swarm = [
        other for other in fight.living_adversaries if WISPS in canonical(other.name)
    ]
    if not swarm or swarm[0] is not adversary:
        return

    party = fight.conscious_party
    if not party:
        return

    for pc in party:
        held = fight.condition_on(pc, VULNERABLE)
        if held is not None and held.source is adversary:
            fight.clear_condition(pc, VULNERABLE)

    caught = random.sample(party, min(targets_reached(Range.VERY_CLOSE, len(party)), len(party)))
    for pc in caught:
        if fight.is_vulnerable(pc):
            continue
        fight.apply_condition(pc, Condition(name=VULNERABLE, source=adversary))
    if caught:
        fight.note(
            f"{len(caught)} cannot look away from {adversary.name} ({VULNERABLE})"
        )


FASCINATING = qualified(ADVERSARY, "Fascinating")

FASCINATING_FEAR = 1
FASCINATING_DIFFICULTY = 13


@action(FASCINATING)
def fascinating(adversary, target, fight: Fight):
    """Spend a Fear: everyone within Far reads the afterimages, or pays for it.

    SRD: "Spend a Fear to have the Will-o'-the-Wisps trace looping light trails
    through the air, leaving afterimages that beg to be deciphered. Each PC within
    Far range must succeed on an Instinct Reaction Roll (13) or mark a Stress and
    move up to Close range toward the Will-o'-the-Wisps."

    Difficulty 13 is printed. The movement half is the lure working - the PCs drift
    toward the lights - and has nothing here to touch; what the Fear buys is the
    Stress, across nearly the whole party, since Far reaches everyone but one a
    quarter of the time.

    USAGE POLICY - ruled. Free among the affordable options, per the standing
    random-among-viable rule. It declines when the band reaches nobody, so the Fear
    is never spent on an empty room.
    """
    if fight is None:
        return None

    party = fight.conscious_party
    caught = party[: targets_reached(Range.FAR, len(party))] if party else []
    if not caught:
        return None
    if not fight.spend_fear(FASCINATING_FEAR):
        return None

    fight.note(f"{adversary.name} trace patterns that {len(caught)} cannot put down")
    for pc in caught:
        roll = _reaction_roll(pc, "instinct", FASCINATING_DIFFICULTY, fight)
        if roll.is_success:
            fight.note(f"{pc.name} looks away in time ({roll})")
            continue
        pc.mark_stress(1)
        fight.note(f"{pc.name} drifts toward the lights, marking a Stress ({roll})")
    return AttackResult(attack_roll=None, damage_roll=None)


no_combat_effect(
    qualified(ADVERSARY, "Possessor"),
    "The Poltergeist marks a Stress to inhabit a nonmagical object entirely within "
    "Close range, and the next time it would take damage the object is destroyed "
    "instead and the Poltergeist expelled. **Dismissed on the trigger rather than "
    "on the clause**, which is the user's ruling and the standing shape: the "
    "object is scenery, nothing here represents objects at all, and the negated "
    "hit is a consequence of the object existing rather than something that "
    "happens on its own. The Minor Fire Elemental's *Consume Kindling* was ruled "
    "the other way - its flammable scenery is assumed always to hand - and this "
    "was put alongside it and declined: one loose object big enough to hide inside "
    "and durable enough to soak a blow is a stronger claim than kindling. Worth "
    "knowing what is lost: a Stress for a wholly negated hit, re-castable, on a "
    "2 HP stat block.",
)


no_combat_effect(
    qualified(ADVERSARY, "Ghost Storm"),
    "The Poltergeist spends a Fear to pull all unequipped nonmagical objects "
    "within Very Close range into a vortex, dealing 1d12+2 physical to targets who "
    "fail an Agility Reaction Roll and half to those who succeed. Dismissed on the "
    "same reading as *Possessor* above and by the same ruling: the loose objects "
    "are the trigger, nothing here represents them, and a vortex with nothing to "
    "fill it does nothing. The damage itself is plainly representable - that is "
    "the point of dismissing on the **trigger** rather than salvaging the clause "
    "that would run. It leaves the Poltergeist with *Specter* alone.",
)


insignificant_combat_effect(
    qualified(ADVERSARY, "Ankle Weights"),
    "A PC must mark a Stress to move out of the Redcap Biters' Melee range. The "
    "size, which is what this state has to state: **one Stress per disengagement, "
    "and a simulated fight contains zero disengagements** - nothing here moves, so "
    "the toll is never charged and the expected cost across a high-N run is 0.0 "
    "Stress. Ruled into this state by the user rather than into *no combat "
    "effect*; the distinction being drawn is that Stress is a resource the "
    "simulator represents completely, so the effect has something to touch even "
    "though its trigger never arrives. Worth knowing that it leaves the Biters "
    "with only their Horde passive, and that it would become real the moment "
    "positions were tracked.",
)


out_of_combat_ability(
    qualified(ADVERSARY, "Stone of Omens"),
    "Inside the Atotoll is a stone that foretells fortune, and a PC who searches "
    "its remains makes a fate roll: an even result hands the party Hope to "
    "distribute, an odd one hands the GM Fear. **Not a dismissal.** Hope and Fear "
    "are the two currencies this whole simulator is built around, so the effect is "
    "as representable as anything gets - what puts it in this state is *when*: "
    "searching a corpse is something a party does after the fighting stops, and "
    "the payout would be carried into the next encounter rather than spent in this "
    "one. The user ruled it here on that reading, so it joins the "
    "sequenced-encounter list with A Soldier's Bond and Armorer rather than being "
    "written as something that fires mid-fight. Modelling it as firing "
    "automatically when the Atotoll is defeated was offered and declined - the "
    "page requires a PC to spend the effort.",
)


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
    "most of it is absorbed within a band. Hidden is now a tracked condition, "
    "which the earlier version of this reason leaned on - but nothing on the "
    "Jagged Knife Sniper's stat block makes it Hidden, so the trigger still "
    "never arrives. The ruling itself is unchanged.",
)
