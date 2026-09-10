"""Dread domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json, checked against the printed page -
SRD 2.0's *Domain Card Reference* appendix, pp. 213-214.

**Dread is new in SRD 2.0**, the tenth domain and the first added since this
project began. It is reachable by the Warlock and the Witch, both also new, so a
party built from the current book can carry these where it could not carry
anything from a domain we had not written. Every other domain here was ported by
*level*; this one is ported by domain, across every level at once, because the
whole of it arrived together.

Two things run through the domain and neither had a shape here before:

* **The GM's Fear pool is a resource the party reads.** *Umbral Veil* is sized by
  it outright - the veil is worth however much Fear the GM is holding when it goes
  up. Midnight's *Night Terror* is the only earlier card that looks at the pool at
  all, and it looks at it once; here it is a recurring theme, and *Dread-Touched*
  and *Avatar of Terror* at the higher levels do the same thing.
* **Damage the party makes somebody else's attack worse at dealing.** *Blighting
  Strike* halves an adversary's next successful attack, which nothing in the
  project could express: every damage hook either belongs to whoever is swinging
  or to whoever is being hit, and this belongs to a third party who marked the
  swinger a spotlight ago.

Levels 1-3: *Blighting Strike*, *Umbral Veil* and *Voice of Dread* at level 1;
*Hideous Retribution* and *Siphon Essence* at level 2; *Shared Trauma* and
*Terrify* at level 3.

**Blighting Strike is the first card anywhere that rolls a bigger die on a roll
with Fear** - d10+1 against the d6+1 a roll with Hope gets - so the outcome that
hands the GM a Fear is also the one that hits harder. Nothing else in the project
is shaped that way round.

Levels 4-6: *Chains of Affliction* and *Summon Horror* at level 4; *Dire Strike*
and *Spectral Mist* at level 5; *Darkfire* and *Jump Scare* at level 6.

Three things about that middle stretch are worth knowing before reading any of it:

* **Two of the six deal damage without an attack roll.** *Summon Horror* and
  *Darkfire* both print a cost and a damage line and never say "Make a Spellcast
  Roll", which the user ruled is exactly what it looks like - so both are **free
  abilities** that deal their damage and leave the caster's own action roll intact.
  Only Disintegration Wave and Night Terror did anything like it before.
* **Both scale on the Spellcast trait rather than Proficiency.** "Using your
  Spellcast trait" is the substitution "using your Proficiency" makes everywhere
  else, ruled by the user, so the number of dice is the caster's Spellcast trait -
  and a trait of 0 or less leaves the card inert, the standing reading of content
  whose size is a printed number.
* **Chains of Affliction is the first thing that makes an adversary's attacks
  worth less.** Every earlier condition either changes how rolls against its holder
  go, stops them acting, or is recorded and inert.

Levels 7-10 close the domain: *Dread-Touched* and *Wall of Hunger* at level 7;
*Dark Army* and *Eldritch Flesh* at level 8; *Damnation* and *Savor the Anguish*
at level 9; *Avatar of Terror* and *Invoke Torment* at level 10.

Four more firsts, and the domain's own logic finally closes at the top:

* **Eldritch Flesh is the first threshold bonus that moves during a fight**, rising
  with the caster's own marked Stress where every other threshold number is carried
  resolved on the sheet.
* **Dark Army is the first pool spent on two different things** - eight tokens that
  are both a damage bonus and a ward, drawn down by whichever happens first.
* **Dread-Touched's per-rest clause is the largest roll bonus anywhere**: the GM's
  whole Fear pool, up to +12 on a single action roll.
* **Invoke Torment is what the rest of the domain is for.** Dread forces Stress on
  five separate cards, and this is what a filled track finally buys - every blow
  landing twice as hard, multiplied before the thresholds are read.
"""

import random
from dataclasses import replace

from characters.player_character import NEAR_DEATH_HP_UNMARKED
from combat.results import AttackResult
from content.aoe import Range, chance_within, targets_in_area
from content.conditions import (
    BEFORE_AN_ACTION_ROLL,
    CHAINED,
    FEAR_FUELED,
    INCORPOREAL,
    RESTRAINED,
    VULNERABLE,
    Condition,
    when_the_gm_pays,
)
from content.damage_types import DamageType, types_in
from content.registry import (
    Fight,
    Holder,
    action,
    ally_damage_reduction,
    ally_on_damaged,
    ally_on_hit,
    ally_on_spotlight,
    ally_severity_response,
    damage_scaling,
    extra_damage,
    fear_conversion,
    force_reroll,
    free,
    on_hit,
    on_roll,
    roll_bonus,
    severity_response,
    total_extra_damage,
)
from content.spellcast import spellcast
from dice.d20 import roll_d20
from dice.damage import DiceGroup, roll_damage
from dice.duality import DualityOutcome, roll_duality

# --- Blighting Strike ------------------------------------------------------------

BLIGHTING_STRIKE = "Blighting Strike"

# "On a roll with Hope, deal d6+1... On a roll with Fear, deal d10+1" - the two
# dice the card prints, both rolled at the caster's Proficiency.
BLIGHTING_HOPE_DIE = 6
BLIGHTING_FEAR_DIE = 10
BLIGHTING_MODIFIER = 1

# Set on the adversary the strike landed on. Their next successful attack deals
# half damage, and the token is spent by the hit that takes the reduction.
BLIGHTED = "Blighting Strike blight"


def _pay_for_the_miss(caster: Holder, fight: Fight) -> None:
    """The price of a failed strike - "you must spend a Hope or mark a Stress".

    SIMULATION RULE - policy, ruled. **Always the Hope**, and a Stress only at
    zero Hope. The user's ruling, and it is a general rule for any card printing a
    choice of costs rather than a Blighting Strike threshold: the Stress track is
    the scarcer resource here, since it gates Reckless, Rage Up and every other
    Stress cost, and the shared last-slot rule already keeps a slot in reserve.

    The Stress is **forced** rather than spent - the card says *must* - so it goes
    through `mark_stress` and can overflow into a Hit Point, exactly as the Stress
    a burnt-out Wild Surge costs does. A caster with no Hope and a full Stress
    track can be dropped by their own failed spell.
    """
    if caster.can_spend_hope(1):
        caster.spend_hope(1)
        fight.note(f"{caster.name}'s strike goes wide, and costs them a Hope")
        return

    caster.mark_stress(1)
    fight.note(f"{caster.name}'s strike goes wide with no Hope left to pay for it")


@action(
    BLIGHTING_STRIKE,
    unmodelled=[
        "'within Far range' - no positions are tracked, so this always reaches",
    ],
)
def blighting_strike(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Blighting Strike (Dread, level 1). The spell that prefers rolling badly.

    SRD: "Make a Spellcast Roll against a target within Far range. On a success:
    on a roll with Hope, deal d6+1 magic damage using your Proficiency; on a roll
    with Fear, deal d10+1 magic damage using your Proficiency. The target's next
    successful attack deals half damage. On a failure, you must spend a Hope or
    mark a Stress."

    **The first card anywhere whose damage is larger on a roll with Fear.** Every
    other conditional die in the project pays out on Hope; this one pays out on the
    outcome that hands the GM a Fear, so the roll a caster would rather have is not
    the roll that hits hardest.

    SIMULATION RULE - rules interpretation. **A critical takes the Hope die.** A
    critical is neither a roll with Hope nor a roll with Fear - the dice tie - and
    the project's standing reading is that a critical is not a success with Hope.
    The card names only the two outcomes, so the conservative line is the smaller
    die, and the critical is already paid for: `roll_damage` maximises the dice for
    it either way.

    The **blight** is laid whether or not the damage defeated anything, except on a
    target the hit finished - a permanent debuff on a creature that is off the field
    is worth nothing, the skip Forceful Push and Corrosive Projectile both make.

    Never declines. The failure clause costs something, but a spell that declines
    costs a whole spotlight, which is strictly worse.
    """
    if fight is None:
        return None

    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        _pay_for_the_miss(caster, fight)
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    sides = (
        BLIGHTING_FEAR_DIE
        if attack_roll.outcome is DualityOutcome.FEAR
        else BLIGHTING_HOPE_DIE
    )
    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=caster.proficiency, sides=sides)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=BLIGHTING_MODIFIER,
        is_critical=attack_roll.is_critical,
    )
    marked = target.take_damage(damage_roll.total, fight, damage_type=DamageType.MAGIC)

    if not target.is_defeated:
        fight.set_token(target, BLIGHTED, 1)
    fight.note(
        f"{caster.name} blights {target.name} for {damage_roll.total} "
        f"(d{sides} on a roll with {attack_roll.outcome.value})"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


@ally_damage_reduction(
    BLIGHTING_STRIKE,
    unmodelled=[
        "'the target's next successful **attack**' is read as the next damage the "
        "blighted adversary deals, which is not quite the same thing: a feature "
        "that deals damage without an attack roll spends the blight too. The "
        "narrower reading would need the attack itself announced to party content, "
        "which nothing does",
        "A swept attack marks one PC's damage and spends the blight there, so the "
        "rest of an area attack lands in full - the gap Redirect and Rapid Riposte "
        "already declare about a sweep announcing only one target",
    ],
)
def blighting_strike_halves(
    holder: Holder, target, amount: int, fight: Fight, damage_type=None
) -> int:
    """Half of a blighted adversary's next hit, taken off whoever it landed on.

    Registered on the same name as the action above - the arrangement one card uses
    to reach two hooks.

    **This is why the card needed a party-wide hook rather than a holder-scoped
    one.** The blight belongs to neither combatant in the attack: the caster laid
    it a spotlight ago and may not be the one being hit. `ally_damage_reduction` is
    the only hook asked about a hit on *anybody* with the whole party's content in
    scope, and `fight.spotlighted` is how it learns which adversary is swinging -
    the same route Counterspell takes to reach an attacker's Difficulty.

    Returned as the **difference** rather than the half, so what survives is
    `amount // 2` - damage halves round down, the same figure a real resistance
    produces.

    Scoped to the conscious party by `_party_offers`, so a caster who has gone down
    stops maintaining the blight. That falls out of the hook rather than being a
    rule anybody wrote, and it is the sensible reading of a spell.
    """
    if fight is None:
        return 0

    attacker = fight.spotlighted
    if attacker is None or not fight.token_count(attacker, BLIGHTED):
        return 0

    # Spent on being collected, so one strike halves one hit.
    fight.set_token(attacker, BLIGHTED, 0)
    blunted = amount - amount // 2
    fight.note(f"The blight on {attacker.name} takes {blunted} off the blow")
    return blunted


# --- Umbral Veil -----------------------------------------------------------------

UMBRAL_VEIL = "Umbral Veil"

# The tokens sitting on the card, each worth -1 on one attack roll made against the
# holder. Placed equal to the Fear in the GM's pool at the moment the veil goes up.
VEIL_TOKENS = "Umbral Veil tokens"


@free(
    UMBRAL_VEIL,
    unmodelled=[
        "'At the end of the scene, clear all unspent tokens' - tokens live on the "
        "`FightState` and a fight is a scene, so they are cleared by the fight "
        "ending rather than by anything here",
    ],
)
def umbral_veil(holder: Holder, fight: Fight) -> bool:
    """Umbral Veil (Dread, level 1). A Stress buys as much shadow as the GM has Fear.

    SRD: "Once per rest, you can mark a Stress to encase yourself in shadowy energy.
    When you do, place a number of tokens on this card equal to the number of Fear
    in the GM's pool. After an attack roll is made against you, you can spend any
    number of tokens to give the result a -1 penalty per token spent. At the end of
    the scene, clear all unspent tokens."

    **The first card whose size is set by the GM's pool.** Everything else the party
    carries is sized by its own sheet - a Proficiency, a trait, a number of cards -
    and this one is sized by how well the GM has been doing.

    **No roll**, so it is a free ability: the veil goes up *and* the holder takes
    their action roll in the same spotlight.

    SIMULATION RULE - policy, ruled. **Raised at the first spotlight the Stress
    allows**, which is Wild Surge's rule, and here the reasoning is the user's and
    specific to this card: Fear accumulates *before* a fight and is spent down
    during it, so the pool is generally fullest at the opening and a veil raised
    later is worth less, not more. A Fear floor was offered and declined for exactly
    that reason.

    One consequence worth knowing when reading numbers: the veil's size is
    effectively the encounter's **`starting_fear`**, since that is what the pool
    holds at the first spotlight. It is the first card in the project whose worth is
    set by a knob on the encounter rather than by anything on a character sheet.

    Once per **short** rest, as printed, so a party that takes any rest gets it back.
    """
    if fight is None or fight.token_count(holder, VEIL_TOKENS):
        return False
    if not fight.fear:
        return False
    if not holder.will_spend_stress(1):
        return False
    if not fight.use_once_per_rest(holder, UMBRAL_VEIL):
        return False

    holder.spend_stress(1)
    fight.set_token(holder, VEIL_TOKENS, fight.fear)
    fight.note(
        f"{holder.name} draws the shadows in, and {fight.fear} of them hold"
    )
    return True


@force_reroll(
    UMBRAL_VEIL,
    unmodelled=[
        "A **critical** cannot be shaved off - a natural 20 succeeds regardless of "
        "Evasion, so no number of tokens changes it and none are spent trying",
    ],
)
def umbral_veil_darkens(
    holder: Holder, attacker, target, roll, remake, fight: Fight = None
):
    """The tokens spent turning one attack on the holder into a miss.

    Registered on the same name as the free ability above.

    **Spent after the roll**, which the card says outright, and that is what puts it
    on the forced-reroll hook rather than on `evasion_bonus`: that one is asked
    before the dice and could only ever be a standing bonus. This is Fane of the
    Wilds' shape pointed at the other side of the table - it rewrites a resolved
    roll rather than throwing fresh dice, so `remake` is deliberately unused.

    **This is not the imperfect-information case.** The card's own text is "after an
    attack roll is made", so the holder is meant to see the result before deciding,
    which is exactly what a player at the table sees.

    SIMULATION RULE - policy. **The fewest tokens that turn a hit into a miss, and
    none on an attack that already missed** - Fane of the Wilds' rule for a pool
    spent against a known number, read here for the second time rather than a new
    one. A hit no number of tokens could reach buys nothing and keeps them.

    Scoped with `target is holder`: the card says *against you*.
    """
    if fight is None or target is not holder:
        return None

    held = fight.token_count(holder, VEIL_TOKENS)
    if not held or roll.evasion is None:
        return None
    if roll.is_critical or not roll.is_success:
        return None

    # One more than the margin, so the total lands below Evasion rather than on it.
    spent = roll.total - roll.evasion + 1
    if spent <= 0 or spent > held:
        return None

    fight.set_token(holder, VEIL_TOKENS, held - spent)
    fight.note(
        f"{holder.name}'s veil swallows the blow ({spent} token"
        f"{'s' if spent != 1 else ''} spent, {held - spent} left)"
    )
    return replace(roll, modifier=roll.modifier - spent)


# --- Voice of Dread --------------------------------------------------------------

VOICE_OF_DREAD = "Voice of Dread"


@action(
    VOICE_OF_DREAD,
    unmodelled=[
        "'a creature you can see' - nothing records line of sight, so this always "
        "reaches",
        "Being Restrained itself, which is ruled to have no effect of its own here "
        "because no movement is modelled - so what the Restrain comes to is the "
        "Fear the GM must spend to clear it, exactly as Shadowbind's does",
    ],
)
def voice_of_dread(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Voice of Dread (Dread, level 1). Words that cost a Stress and a Fear.

    SRD: "You can magically speak to a creature you can see, tormenting them with
    your words. Make a Spellcast Roll against them. On a success, they must mark a
    Stress and are frozen with terror, making them temporarily *Restrained*."

    Recall Cost 0 and no cost to cast - the cheapest thing in the domain, and what
    it buys is two drains on the GM at once: a Stress off the adversary's own track,
    and the Fear it takes to shake the Restrain off.

    Worth knowing what filling an adversary's Stress track buys, since half of this
    card is exactly that: an adversary with no free Stress cannot pay for its Action
    features, and a forced Stress that will not fit marks a Hit Point instead.

    The Stress is **forced** rather than spent, so an adversary whose track is
    already full marks a Hit Point instead - the SRD's overflow rule applies on both
    sides of the table. So this card keeps biting after an adversary is stressed
    out, where a feature that *spends* Stress would simply stop working.

    Never declines, and in particular **does not decline against a target already
    Restrained**: the standing don't-re-apply rule is about not paying twice for one
    condition, and here the Stress lands either way, so there is always something to
    buy.
    """
    if fight is None:
        return None

    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    target.mark_stress(1)
    if not target.is_defeated and not fight.has_condition(target, RESTRAINED):
        fight.apply_condition(
            target, Condition(name=RESTRAINED, end=when_the_gm_pays, source=caster)
        )
    fight.note(f"{caster.name}'s voice freezes {target.name} where they stand")

    # No damage of its own, so nothing that reads a landed hit fires off this.
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


# --- Hideous Retribution ---------------------------------------------------------

HIDEOUS_RETRIBUTION = "Hideous Retribution"

HIDEOUS_RETRIBUTION_DIE = 6


@ally_on_damaged(
    HIDEOUS_RETRIBUTION,
    unmodelled=[
        "'from a target you can see' - nothing records line of sight. What is "
        "checked instead is that an adversary is spotlighted, since damage arriving "
        "with nobody spotlighted is the party's own and has no target to punish",
        "The reaction roll is not offered `total_roll_bonus`, which is asked at the "
        "three action-roll sites. That is the reading rather than a gap: the SRD "
        "keeps action rolls and reaction rolls apart, and Sage-Touched and Wild "
        "Surge both declare the same thing from the other side",
    ],
)
def hideous_retribution(
    holder: Holder, target, amount: int, hp_marked: int, fight: Fight = None
) -> None:
    """Hideous Retribution (Dread, level 2). Answering a blow struck at somebody else.

    SRD: "When an ally within Close range takes damage from a target you can see,
    you can make a reaction roll against the target using your Spellcast trait. On a
    success, mark a Stress to deal d6 magic damage using your Proficiency."

    A **Reaction Roll**, which the project models as Duality Dice plus a trait with
    the Hope/Fear outcome unread - so this neither hands the GM a Fear nor pays the
    caster a Hope, however the dice fall, and it does not move the spotlight. The
    Difficulty is the attacker's own, which is what "against the target" names.

    "An ally" is scoped away from the holder: a Dread caster taking a hit themselves
    does not answer it with this. Whether the ally is within Close range is the
    standing positional answer - `chance_within` over the rest of the party, rolled
    at each blow, since where everyone is standing is exactly what changes between
    one attack and the next.

    SIMULATION RULE - policy. Nothing new to rule. It is a Reaction, so the standing
    rule applies - it fires whenever the trigger happens and the cost can be paid,
    and the desperation rule that gates Actions deliberately does not apply. The
    zero-benefit exception cannot bite here, since the damage is dice rather than a
    number that could compute to nothing.

    The Stress is **checked before the roll and paid after** it, so a reaction the
    caster could not have afforded is never rolled and a failed one costs nothing.
    """
    if fight is None or target is holder:
        return

    attacker = fight.spotlighted
    if attacker is None or attacker.is_defeated:
        return

    others = len(fight.conscious_party) - 1
    if others <= 0 or random.random() >= chance_within(Range.CLOSE, others):
        return

    trait = getattr(holder, "spellcast_trait", "")
    if not trait or trait not in holder.traits:
        return
    if not holder.will_spend_stress(1):
        return

    reaction = roll_duality(
        modifier=holder.traits[trait], difficulty=attacker.difficulty, trait=trait
    )
    if not reaction.is_success:
        fight.note(f"{holder.name} rounds on {attacker.name} and finds nothing")
        return

    holder.spend_stress(1)
    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=holder.proficiency, sides=HIDEOUS_RETRIBUTION_DIE)]
        + total_extra_damage(holder, attacker, reaction, fight),
        is_critical=reaction.is_critical,
    )
    attacker.take_damage(damage_roll.total, fight, damage_type=DamageType.MAGIC)
    fight.note(
        f"{holder.name} answers for {target.name}, hurting {attacker.name} "
        f"for {damage_roll.total}"
    )


# --- Siphon Essence --------------------------------------------------------------

SIPHON_ESSENCE = "Siphon Essence"

SIPHON_DIE = 12
SIPHON_MODIFIER = 4

# SIMULATION RULE - policy, ruled. Held until the caster is carrying at least this
# many marked Hit Points, so the clear half of the spell is not thrown away. The
# user's number.
SIPHON_ESSENCE_HP_MARKED = 2


@action(
    SIPHON_ESSENCE,
    unmodelled=[
        "'within Very Close range' - no positions are tracked, so this always "
        "reaches",
    ],
)
def siphon_essence(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Siphon Essence (Dread, level 2). Take the damage dealt and keep it.

    SRD: "Make a Spellcast Roll against a target within Very Close range. Once per
    long rest on a success, the target takes d12+4 magic damage using your
    Proficiency. On a success with Fear, you gain a +1 bonus to your Proficiency for
    this attack. You clear a number of Hit Points equal to the number of Hit Points
    the target marked from this attack."

    **The first card that turns damage dealt straight into Hit Points cleared**, and
    it is a one-for-one conversion rather than a fraction: a hit that marks three of
    an adversary's Hit Points clears three of the caster's own. So its worth is the
    target's *thresholds* as much as the caster's Proficiency - the same number of
    points of damage buys more against something fragile.

    The +1 Proficiency on a success with Fear is the domain's second card of that
    shape after Blighting Strike, and it lands on the **dice count** rather than on
    the total, so it is worth a whole extra d12.

    SIMULATION RULE - policy, ruled. **Held until the caster has 2 or more Hit
    Points marked.** The user's ruling and the user's number. Rejuvenation Barrier's
    cast-early rule was offered and declined here, and the difference is what the
    two spells waste: the Barrier's 1d4 is one part of a spell that also raises a
    resistance for the whole fight, while this is once per **long** rest and its
    clear is half of what it does. The cost of the ruling is that a caster nothing
    ever hits never casts it.

    Once per long rest **on a success**, which the card prints - so a failed cast
    costs the spotlight and leaves the spell available.
    """
    if fight is None:
        return None
    if caster.hp_marked < SIPHON_ESSENCE_HP_MARKED:
        return None
    if not fight.can_use_once_per_rest(caster, SIPHON_ESSENCE, long=True):
        return None

    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        fight.note(f"{caster.name} reaches for {target.name}'s essence and misses")
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    fight.use_once_per_rest(caster, SIPHON_ESSENCE, long=True)

    proficiency = caster.proficiency + (
        1 if attack_roll.outcome is DualityOutcome.FEAR else 0
    )
    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=proficiency, sides=SIPHON_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=SIPHON_MODIFIER,
        is_critical=attack_roll.is_critical,
    )
    marked = target.take_damage(damage_roll.total, fight, damage_type=DamageType.MAGIC)
    caster.clear_hp(marked)
    fight.note(
        f"{caster.name} siphons {target.name} for {damage_roll.total}, "
        f"taking back {marked} Hit Point{'s' if marked != 1 else ''}"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


# --- Shared Trauma ---------------------------------------------------------------

SHARED_TRAUMA = "Shared Trauma"


@free(
    SHARED_TRAUMA,
    unmodelled=[
        "'within Melee range' of each other - no positions are tracked, so any two "
        "conscious PCs can be paired",
        "'a willing creature' is read as a PC. Nothing else in a fight would "
        "consent, and an unconscious one cannot",
    ],
)
def shared_trauma(holder: Holder, fight: Fight) -> bool:
    """Shared Trauma (Dread, level 3). Move the wound rather than heal it.

    SRD: "You can transfer suffering from one creature to another. Once per rest,
    mark any number of Hit Points on a willing creature within Melee range to clear
    an equal number of Hit Points on another willing creature within Melee range."

    **Net zero across the party**, which is what makes it unlike every other card
    here that touches Hit Points: nothing is healed, it is only moved. So it is
    worth using in exactly one situation - when the points are worth more off one
    PC than they cost on another - and worth nothing at all otherwise.

    **No roll**, so it is a free ability: the transfer happens *and* the holder
    takes their action roll in the same spotlight. It is also the first card that
    reaches two other PCs without the holder needing to be either of them.

    SIMULATION RULE - policy, ruled. **Only to lift somebody out of near death.**
    The card fires when a PC is at `NEAR_DEATH_HP_UNMARKED` or fewer unmarked Hit
    Points, moves the fewest points that lift them clear of that band, and takes
    them only from a PC who is still clear of it afterwards. Equalising the two and
    moving as much as the giver can spare were both offered and declined. It is a
    "never make it worse" rule and is meant to generalise to any later card that
    moves Hit Points between PCs rather than being this card's threshold.

    The giver is chosen at **random among those who can afford it**, per the
    standing random-among-viable rule - picking the healthiest would be scoring the
    party, which this project rules out.

    The transfer goes through `mark_hp_and_check_death` rather than the raw
    `mark_hp`, as every route to a marked Hit Point must. The policy above already
    guarantees the giver survives it, so nothing is ever offered a death move here -
    but the rule is that no caller gets to decide that for itself.
    """
    if fight is None:
        return False
    if not fight.can_use_once_per_rest(holder, SHARED_TRAUMA):
        return False

    standing = fight.conscious_party
    failing = [pc for pc in standing if pc.is_near_death]
    if not failing:
        return False

    receiver = min(failing, key=lambda pc: pc.hp_unmarked)
    needed = NEAR_DEATH_HP_UNMARKED + 1 - receiver.hp_unmarked
    if needed <= 0 or needed > receiver.hp_marked:
        return False

    givers = [
        pc
        for pc in standing
        if pc is not receiver and pc.hp_unmarked - needed > NEAR_DEATH_HP_UNMARKED
    ]
    if not givers:
        return False

    # Only drawn from when there is a choice to make - the same reason
    # `_party_offers` skips its shuffle, since a draw nobody needed would shift
    # every later roll in the fight.
    giver = random.choice(givers) if len(givers) > 1 else givers[0]

    fight.use_once_per_rest(holder, SHARED_TRAUMA)
    giver.mark_hp_and_check_death(needed, fight)
    receiver.clear_hp(needed)
    fight.note(
        f"{holder.name} moves {needed} Hit Point{'s' if needed != 1 else ''} "
        f"from {receiver.name} onto {giver.name}"
    )
    return True


# --- Terrify ---------------------------------------------------------------------

TERRIFY = "Terrify"

TERRIFY_STRESS_DIE = 4


@action(
    TERRIFY,
    unmodelled=[
        "'you can make the target flee one range away from you' - pure "
        "repositioning, and no positions are tracked. Death Grip's pull declares "
        "the same gap, and errs the same way: at a table the flee is a real choice, "
        "so this card comes out somewhat better here than it plays",
        "'within Close range' - no positions are tracked, so this always reaches",
    ],
)
def terrify(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Terrify (Dread, level 3). A die of Stress, and Vulnerable if it goes badly.

    SRD: "Make a Spellcast Roll against a target within Close range. On a success,
    the target marks 1d4 Stress, and you can make the target flee one range away
    from you (such as Very Close to Close or Close to Far). On a success with Fear,
    the target also becomes temporarily *Vulnerable*."

    **The largest forced Stress in the project** - up to four at once, where Death
    Grip's constrict forces two and Voice of Dread forces one. Against a tier 1
    adversary with a track of three, a good roll empties it outright, and a forced
    Stress that will not fit marks a Hit Point instead.

    The Vulnerable rides on a **success with Fear**, the domain's third clause of
    that shape after Blighting Strike and Siphon Essence: the outcome the caster
    would rather not have is the one that pays extra. Temporary, so the GM spends a
    Fear to clear it, which is the standing price for a condition the party applies.

    Never declines. It costs nothing but the roll the caster was making anyway,
    which is the Preservation Blast side of the split.
    """
    if fight is None:
        return None

    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    forced = random.randint(1, TERRIFY_STRESS_DIE)
    target.mark_stress(forced)

    if (
        attack_roll.outcome is DualityOutcome.FEAR
        and not target.is_defeated
        and not fight.has_condition(target, VULNERABLE)
    ):
        fight.apply_condition(
            target, Condition(name=VULNERABLE, end=when_the_gm_pays, source=caster)
        )
    fight.note(
        f"{caster.name} terrifies {target.name}, forcing {forced} Stress"
    )

    # No damage of its own, so nothing that reads a landed hit fires off this.
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


def _spellcast_dice(caster: Holder) -> int:
    """How many dice a spell "using your Spellcast trait" rolls.

    SIMULATION RULE - rules interpretation, ruled. **The trait substitutes for
    Proficiency.** Every card ported before this domain says "using your
    Proficiency" and rolls that many dice; SRD 2.0's Dread cards say "using your
    Spellcast trait", and the user ruled it the same substitution with a different
    stat - which is also how Splendor's *Restoration* already reads "equal to your
    Spellcast trait". Rolling Proficiency dice anyway, and rolling one die with the
    trait added to the total, were both offered and declined.

    Zero or less leaves the card inert rather than rolling no dice at all, which is
    the standing reading of content whose size is a printed number - Sage-Touched's
    doubling and Unyielding Armor's Proficiency dice both decline the same way.
    """
    return caster.traits.get(getattr(caster, "spellcast_trait", ""), 0)


# --- Chains of Affliction --------------------------------------------------------

CHAINS_OF_AFFLICTION = "Chains of Affliction"

CHAINS_STRESS = 2

# What an adversary dealt during the GM turn its tally belongs to, and which turn
# that was. The turn is stored as `gm_turns + 1` so an unset token reads as "has
# never attacked" rather than as the opening turn - and so the card never has to
# know whether the loop ticks its counter at the start of a GM turn or the end.
CHAINS_DEALT = "Chains of Affliction damage dealt"
CHAINS_TALLIED = "Chains of Affliction tallied on turn"


@ally_on_damaged(
    CHAINS_OF_AFFLICTION,
    unmodelled=[
        "The tally only accrues while the card's holder is conscious, since "
        "`_party_offers` scans the standing party. A Dread caster who goes down "
        "and is brought back has forgotten what hit whom",
    ],
)
def chains_of_affliction_watches(
    holder: Holder, target, amount: int, hp_marked: int, fight: Fight = None
) -> None:
    """Keep a per-GM-turn tally of what each adversary is dealing.

    Not an effect of the card at all - it is the bookkeeping the *targeting* rule
    needs, and it lives here rather than on `FightState` because nothing else in the
    project wants it. That is the one-card-one-place rule read the strict way: a
    card that needs a fact nobody records should record it for itself before it asks
    shared machinery to grow a field.

    Keyed on `fight.spotlighted`, the same route Blighting Strike and Hideous
    Retribution take to find out who is swinging.
    """
    if fight is None or amount <= 0:
        return

    attacker = fight.spotlighted
    if attacker is None:
        return

    turn = fight.gm_turns + 1
    if fight.token_count(attacker, CHAINS_TALLIED) != turn:
        fight.set_token(attacker, CHAINS_TALLIED, turn)
        fight.set_token(attacker, CHAINS_DEALT, 0)
    fight.set_token(
        attacker, CHAINS_DEALT, fight.token_count(attacker, CHAINS_DEALT) + amount
    )


def _worst_of_the_last_turn(fight: Fight) -> list:
    """The adversaries that attacked most recently, hardest-hitting first.

    "Most recently" is read off the tally rather than off the turn counter, so the
    answer is the same whether the card is used during a GM turn or after one.
    """
    living = fight.living_adversaries
    latest = max((fight.token_count(a, CHAINS_TALLIED) for a in living), default=0)
    if not latest:
        return []

    attacked = [a for a in living if fight.token_count(a, CHAINS_TALLIED) == latest]
    hardest = max(fight.token_count(a, CHAINS_DEALT) for a in attacked)
    return [a for a in attacked if fight.token_count(a, CHAINS_DEALT) == hardest]


@free(
    CHAINS_OF_AFFLICTION,
    unmodelled=[
        "'within Close range' - no positions are tracked, so the chain reaches "
        "whichever adversary the targeting rule picks",
    ],
)
def chains_of_affliction(holder: Holder, fight: Fight) -> bool:
    """Chains of Affliction (Dread, level 4). Make one adversary's blows land softer.

    SRD: "Mark 2 Stress to temporarily *Chain* a target within Close range. When a
    *Chained* creature deals damage, the target of their attack marks one fewer Hit
    Point than they would. You can't have more than one creature *Chained* at a
    time."

    **The first thing in the project that makes an adversary's attacks worth less.**
    Every condition before it changes how rolls against its holder go, stops them
    acting, or is recorded and inert - none of them reached what the holder's own
    blows cost. It takes a Hit Point off the mark rather than damage off the roll,
    so it is worth the same against a big hit and a small one.

    **No roll**, so it is a free ability: the chain goes on *and* the holder takes
    their action roll in the same spotlight.

    SIMULATION RULE - policy, ruled. **The first spotlight the shared last-slot rule
    allows the 2 Stress, on the adversary that attacked during the last GM turn and
    dealt the most damage doing it.** The user's rule, and it is deliberately not
    the standing "goes on the toughest" rule that Eternal Enervation and Twilight
    Toll follow: what this card reduces is damage dealt, so it goes on whatever is
    actually dealing it. Placing it on the biggest printed attack, and holding it
    until the party is hurt, were both offered and declined.

    Two consequences follow and both are real. The card **cannot be used before the
    first GM turn**, since nothing has attacked yet - so "first spotlight allowed"
    means the first one after the party has been hit. And the damage it reads is
    what was actually dealt rather than what is printed, which is a fact the party
    watched happen rather than a statistic anybody computes.

    Declines while a chain already stands, which the card prints outright.
    """
    if fight is None:
        return False
    if any(fight.has_condition(a, CHAINED) for a in fight.living_adversaries):
        return False

    candidates = _worst_of_the_last_turn(fight)
    if not candidates:
        return False
    if not holder.will_spend_stress(CHAINS_STRESS):
        return False

    # Ties drawn rather than taken in spawn order, and only drawn from when there
    # is a choice - the reason `_party_offers` skips its own shuffle.
    target = random.choice(candidates) if len(candidates) > 1 else candidates[0]

    holder.spend_stress(CHAINS_STRESS)
    fight.apply_condition(
        target, Condition(name=CHAINED, end=when_the_gm_pays, source=holder)
    )
    fight.note(f"{holder.name} binds {target.name} in chains of affliction")
    return True


@ally_severity_response(CHAINS_OF_AFFLICTION)
def chains_of_affliction_binds(
    holder: Holder,
    target,
    amount: int,
    hp_to_mark: int,
    fight: Fight = None,
    damage_type=None,
    marked_armor: bool = False,
) -> int:
    """The Hit Point a chained creature's blow no longer costs.

    Registered on the same name as the free ability above.

    On the **party-wide** severity hook rather than the holder-scoped one for
    Blighting Strike's reason: the chain belongs to the caster, and the PC being hit
    is somebody else. It reduces `hp_to_mark` rather than the damage, because that
    is what the card says - "marks one fewer Hit Point than they would" - so an
    Armor Slot has already had its say by the time this is asked.

    Never below zero, and skipped on a hit already marking nothing, which is the
    standing zero-benefit rule rather than a threshold.
    """
    if fight is None or hp_to_mark <= 0:
        return hp_to_mark

    attacker = fight.spotlighted
    if attacker is None or not fight.has_condition(attacker, CHAINED):
        return hp_to_mark

    fight.note(f"The chains drag at {attacker.name}, and the blow costs one less")
    return hp_to_mark - 1


# --- Summon Horror ---------------------------------------------------------------

SUMMON_HORROR = "Summon Horror"

SUMMON_HORROR_DIE = 8
SUMMON_HORROR_MODIFIER = 1

# The Reaction Roll the horror forces, printed on the card.
SUMMON_HORROR_DIFFICULTY = 12

# "Once per scene", and a fight is a scene - so a token rather than a per-rest use.
HORROR_SUMMONED = "Summon Horror summoned"


@free(
    SUMMON_HORROR,
    unmodelled=[
        "No attack roll is made, so nothing keyed on one is offered - "
        "`total_extra_damage` and the party's reroll content both want a roll to "
        "read, and there is none. A rider that would have joined an ordinary "
        "spell's damage does not join this",
        "'summon an otherworldly creature' - the horror is never a combatant. It "
        "deals its damage and dissipates in the same breath, so nothing can target "
        "it and it takes no spotlight",
    ],
)
def summon_horror(holder: Holder, fight: Fight) -> bool:
    """Summon Horror (Dread, level 4). A Stress for damage that cannot miss.

    SRD: "Once per scene, mark a Stress to summon an otherworldly creature that
    deals d8+1 magic damage using your Spellcast trait. If the target marks any Hit
    Points from this attack, they must succeed on a Reaction Roll (12) to steel
    themselves against the horror or mark an equal number of Stress. After making
    the attack, the creature dissipates."

    SIMULATION RULE - rules interpretation, ruled. **There is no attack roll.** The
    card never says "Make a Spellcast Roll", and every card that wants one says so;
    the user ruled it reads exactly as printed. So this is a **free ability** - the
    damage lands, and the caster still takes their own action roll in the same
    spotlight. Reading the phrase "using your Spellcast trait" as implying a cast,
    and having the summoned creature roll its own attack, were both offered and
    declined.

    That makes it the third thing in the project to deal damage with no roll behind
    it, after Disintegration Wave and Night Terror, and the first where the damage
    is an ordinary damage roll against ordinary thresholds.

    "Once per scene" is a **token** rather than a per-rest use: a fight is a scene,
    and a per-rest use would wrongly survive into the next encounter unspent.

    SIMULATION RULE - policy. Aimed at the party's focus target - the adversary with
    the most Hit Points marked - which is Chokehold's rule and the same one
    `combat/policy.py` uses, restated here because `content/` cannot import it.
    Declines against an empty field and while the Stress cannot be paid.

    The Stress the horror forces is **equal to the Hit Points it marked**, so it is
    worth most against something whose thresholds it comfortably crosses.
    """
    if fight is None or fight.token_count(holder, HORROR_SUMMONED):
        return False

    dice = _spellcast_dice(holder)
    if dice <= 0:
        return False

    living = fight.living_adversaries
    if not living:
        return False
    if not holder.will_spend_stress(1):
        return False

    holder.spend_stress(1)
    fight.set_token(holder, HORROR_SUMMONED, 1)

    target = max(living, key=lambda adversary: adversary.hp_marked)
    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=dice, sides=SUMMON_HORROR_DIE)],
        modifier=SUMMON_HORROR_MODIFIER,
    )
    marked = target.take_damage(damage_roll.total, fight, damage_type=DamageType.MAGIC)
    fight.note(
        f"{holder.name} summons a horror, and it tears {damage_roll.total} "
        f"out of {target.name}"
    )

    if marked and not target.is_defeated:
        # An adversary's Reaction Roll is a flat d20 against a Difficulty - they
        # have no traits - and a critical takes nothing at all.
        save = roll_d20(evasion=SUMMON_HORROR_DIFFICULTY)
        if not (save.is_success or save.is_critical):
            target.mark_stress(marked)
            fight.note(f"{target.name} fails to steel themselves ({marked} Stress)")
    return True


# --- Dire Strike -----------------------------------------------------------------

DIRE_STRIKE = "Dire Strike"


@on_hit(DIRE_STRIKE)
def dire_strike(attacker: Holder, target, result, fight: Fight) -> None:
    """Dire Strike (Dread, level 5). A Hope off the party for a Fear off the GM.

    SRD: "When a target marks any number of Hit Points from an attack you make, you
    can spend a Hope to drain power from them. The GM loses a Fear."

    **The only card in the project that takes Fear off the GM as its whole effect.**
    Night Terror removes Fear too, but converts it into damage on the way out; this
    is a straight trade of one currency for the other, and the exchange rate is
    fixed at one for one.

    SIMULATION RULE - policy. The standing default for a rider costing a single
    Hope, and there is nothing to choose between: one landed hit looks like any
    other, so holding it back would be inventing foresight. Vanishing Dodge's
    reading.

    Declines on an **empty pool**, per the standing zero-benefit rule - at 0 Fear
    the Hope would buy nothing, which is the same check Vicious Entangle makes
    before paying for a second Restrain.

    Fires on Hit Points marked rather than on damage dealt, which is the card's own
    wording, so a hit an Armor Slot took to nothing buys nothing.
    """
    if fight is None or not fight.fear:
        return
    if not result.hp_marked:
        return
    if not attacker.can_spend_hope(1):
        return

    attacker.spend_hope(1)
    fight.spend_fear(1)
    fight.note(f"{attacker.name} drains the dread out of {target.name} (1 Fear)")


# --- Spectral Mist ---------------------------------------------------------------

SPECTRAL_MIST = "Spectral Mist"

SPECTRAL_MIST_HOPE = 2


def _until_their_next_action_roll(holder, fight, moment: str) -> bool:
    """Corporeal again the moment its holder rolls.

    The card says "after they pass through a solid object **or make an action
    roll**", and `BEFORE_AN_ACTION_ROLL` is the only moment announced per action
    roll. Before or after that roll is a distinction with nothing between it here:
    an action roll is not physical damage, so nothing the mist protects against can
    happen in the gap.
    """
    return moment == BEFORE_AN_ACTION_ROLL


@free(
    SPECTRAL_MIST,
    unmodelled=[
        "'they can move through solid objects' and the other half of the ender, "
        "'after they pass through a solid object' - terrain and movement, neither "
        "of which has any representation. So the only way out is the action roll, "
        "which errs **generous**: at a table a PC could lose the mist by moving",
    ],
)
def spectral_mist(holder: Holder, fight: Fight) -> bool:
    """Spectral Mist (Dread, level 5). Two Hope, and physical damage stops mattering.

    SRD: "Spend 2 Hope to conjure an eerie mist that turns you and allies of your
    choice within Close range momentarily incorporeal. While a creature is
    incorporeal, they can move through solid objects and are immune to physical
    damage. They become corporeal again after they pass through a solid object or
    make an action roll. Otherwise, this effect lasts until the end of the scene."

    **Immunity rather than resistance**, which is why it goes through the hook that
    can return the whole amount - `damage_resistance` halves. That puts it with the
    Book of Yarrow's *Magic Immunity* and *Specter of the Dark*, and it is the only
    one of the three that covers somebody other than its caster.

    SIMULATION RULE - policy, ruled. **It lasts until each covered PC's own next
    action roll.** The consequence the user accepted when ruling it is worth being
    plain about: conjuring is a free ability, so the caster makes their action roll
    in the very same spotlight and is corporeal again immediately - **this card
    protects the caster's allies and not the caster**. Skipping the casting
    spotlight for them, and running the mist to the end of the scene with the ender
    declared a gap, were both offered and declined.

    Who is covered is the standing positional answer - `chance_within` over the rest
    of the party, drawn once as the mist goes up rather than per hit, because the
    card names the creatures at the moment it is cast rather than describing a place
    they can wander out of. That is the opposite of Rejuvenation Barrier's ruling,
    and for the reason the two cards differ: a barrier is somewhere to stand, and
    this is a list of names.

    Declines while the caster is already incorporeal - re-conjuring would buy
    nothing they do not have.
    """
    if fight is None or fight.has_condition(holder, INCORPOREAL):
        return False
    if not holder.can_spend_hope(SPECTRAL_MIST_HOPE):
        return False

    standing = fight.conscious_party
    others = len(standing) - 1
    covered = [holder] + [
        pc
        for pc in standing
        if pc is not holder and random.random() < chance_within(Range.CLOSE, others)
    ]

    holder.spend_hope(SPECTRAL_MIST_HOPE)
    for pc in covered:
        fight.apply_condition(
            pc,
            Condition(
                name=INCORPOREAL,
                end=_until_their_next_action_roll,
                source=holder,
            ),
        )
    fight.note(
        f"{holder.name} conjures a spectral mist over {len(covered)} of the party"
    )
    return True


@ally_damage_reduction(SPECTRAL_MIST)
def spectral_mist_passes_through(
    holder: Holder, target, amount: int, fight: Fight, damage_type=None
) -> int:
    """Physical damage passing straight through whoever the mist still covers.

    Registered on the same name as the free ability above. Returns the **whole**
    amount, so the hit resolves to nothing - `take_damage` floors at zero before the
    thresholds, which also means no Armor Slot is spent on it. Magic passes through
    the mist rather than the other way round, as the card says.

    Read off the condition rather than off a list of who was covered, so a PC whose
    mist has already lifted is correctly unprotected.
    """
    if fight is None or not fight.has_condition(target, INCORPOREAL):
        return 0
    if DamageType.PHYSICAL not in types_in(damage_type):
        return 0

    fight.note(f"The blow passes straight through {target.name}")
    return amount


# --- Darkfire --------------------------------------------------------------------

DARKFIRE = "Darkfire"

DARKFIRE_DIE = 8
DARKFIRE_MODIFIER = 6

# The Reaction Roll the fire forces, printed on the card.
DARKFIRE_DIFFICULTY = 15

DARKFIRE_CAST = "Darkfire cast"


@free(
    DARKFIRE,
    unmodelled=[
        "No attack roll is made, so nothing keyed on one is offered - the gap "
        "Summon Horror declares beside it",
        "'within Close range' - no positions are tracked, so the area rule in "
        "SIMULATION-RULES.md decides how much of the field the fire can reach",
    ],
)
def darkfire(holder: Holder, fight: Fight) -> bool:
    """Darkfire (Dread, level 6). A Hope apiece, and the field catches light.

    SRD: "Once per scene, spend any number of Hope to target an equal number of
    adversaries within Close range. Each target makes a Reaction Roll (15). Targets
    who fail take d8+6 magic damage using your Spellcast trait as they are engulfed
    in dark fire. Targets who succeed take half damage."

    **No attack roll**, ruled the same way Summon Horror's absence was, so this is a
    free ability that empties the Hope pool into the field and leaves the caster's
    own action roll intact.

    SIMULATION RULE - policy, ruled. **The whole pool, capped by the targets the
    Close band reaches.** Stunning Sunlight's rule, and its reasoning transfers
    exactly: nothing this spell reaches escapes damage, since a target who succeeds
    on the Reaction Roll still takes half, so a Hope is never spent for no result.
    Arcane Barrage's floor of 2 and a fixed number of targets were both offered and
    declined.

    One damage roll **rolled once and reused** across every target, which is the
    standing reading for a spell that hits several at once, and halving on a
    successful save rounds **down** - the standing rule for halving damage.
    """
    if fight is None or fight.token_count(holder, DARKFIRE_CAST):
        return False

    dice = _spellcast_dice(holder)
    if dice <= 0:
        return False

    area = targets_in_area(Range.CLOSE, fight.living_adversaries)
    if not area:
        return False

    hope = min(holder.hope_marked, len(area))
    if hope <= 0:
        return False

    holder.spend_hope(hope)
    fight.set_token(holder, DARKFIRE_CAST, 1)

    caught = area[:hope]
    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=dice, sides=DARKFIRE_DIE)],
        modifier=DARKFIRE_MODIFIER,
    )
    for adversary in caught:
        save = roll_d20(evasion=DARKFIRE_DIFFICULTY)
        dealt = (
            damage_roll.total // 2
            if save.is_success or save.is_critical
            else damage_roll.total
        )
        adversary.take_damage(dealt, fight, damage_type=DamageType.MAGIC)

    fight.note(
        f"{holder.name} spends {hope} Hope, and dark fire engulfs {len(caught)} "
        f"for {damage_roll.total}"
    )
    return True


# --- Jump Scare ------------------------------------------------------------------

JUMP_SCARE = "Jump Scare"


def _until_they_mark_hp(already: int):
    """Vulnerable until its holder marks a Hit Point, whatever marks it.

    A closure over the Hit Points the creature was carrying when the condition
    landed, because "until they mark 1 or more Hit Points" is a fact about the
    holder rather than about a moment. Asked at every announced moment, so it lifts
    at the first one after they have taken anything.
    """

    def ended(holder, fight, moment: str) -> bool:
        return holder.hp_marked > already

    return ended


@on_hit(
    JUMP_SCARE,
    unmodelled=[
        "'when you deal **magic** damage' - `on_hit` is told a landed attack and "
        "its damage roll, and **not** what type it was, so this fires on any "
        "landed attack that dealt damage. It errs generous, and it is the one gap "
        "in this batch that shared machinery could close: `on_damaged` already "
        "carries a `damage_type` for Spellcharge, and `on_hit` does not",
        "'teleport within Melee range with them' - pure repositioning, and no "
        "positions are tracked. What is modelled is the Vulnerable it arrives with",
    ],
)
def jump_scare(attacker: Holder, target, result, fight: Fight) -> None:
    """Jump Scare (Dread, level 6). Arrive in their face, and they never recover.

    SRD: "When you deal magic damage to a target, you can mark a Stress to teleport
    within Melee range with them. When you do, they are *Vulnerable* until they mark
    1 or more Hit Points."

    **The most unusual ender in the project.** Every other condition the party
    applies to an adversary lifts when the GM pays a Fear; this one lifts when the
    adversary *takes a wound* - so it costs the GM nothing at all and instead ends
    itself on the party doing the very thing the Vulnerable was helping them do. In
    practice it lasts from the hit that applied it until the next one that marks a
    Hit Point, which against something with high thresholds can be several rolls.

    SIMULATION RULE - policy. The standing default for a Stress-priced rider, the
    same one Reckless, Versatile Fighter, Rage Up and Midnight-Touched get: marked
    whenever the shared last-slot rule allows. Declines against a target already
    Vulnerable, per the standing don't-re-apply rule, and against one the hit just
    finished - a condition on a creature that is off the field is worth nothing.
    """
    if fight is None or target.is_defeated:
        return
    if fight.has_condition(target, VULNERABLE):
        return
    if not attacker.will_spend_stress(1):
        return

    attacker.spend_stress(1)
    fight.apply_condition(
        target,
        Condition(
            name=VULNERABLE,
            end=_until_they_mark_hp(target.hp_marked),
            source=attacker,
        ),
    )
    fight.note(f"{attacker.name} appears in {target.name}'s face, and they freeze")


# --- Dread-Touched ---------------------------------------------------------------

DREAD_TOUCHED = "Dread-Touched"

DREAD_TOUCHED_STRESS = 2

# SIMULATION RULE - policy, ruled. Codex-Touched's ceiling, read here rather than a
# second number that could drift. Below this many Stress already marked the denial
# is paid for; at or above it the card stops, so one rider cannot run a caster's
# whole track. Like Codex-Touched, this **replaces** `will_spend_stress` rather
# than sitting on top of it.
DREAD_TOUCHED_STRESS_CEILING = 3

# The gap every *X*-Touched card carries. Written out here rather than imported
# from another domain's module, since one card must never import another's.
TOUCHED_LOADOUT_GAP = (
    "'When 4 or more of the domain cards in your loadout are from the Dread "
    "domain' - the loadout is not counted. The user's ruling is that carrying the "
    "card is taken as proof the condition is met, since a player who takes it has "
    "built for it. Recorded as a simulation rule rather than checked"
)


@fear_conversion(DREAD_TOUCHED, unmodelled=[TOUCHED_LOADOUT_GAP])
def dread_touched(roller: Holder, fight: Fight = None) -> bool:
    """Dread-Touched (Dread, level 7), first clause. Two Stress buys the GM nothing.

    SRD: "When 4 or more of the domain cards in your loadout are from the Dread
    domain, gain the following benefits: when you succeed with Fear, you can mark 2
    Stress to prevent the GM from gaining a Fear. Once per rest when making an
    action roll, you can gain a bonus to the roll equal to the number of Fear in the
    GM's pool."

    The second *X*-Touched card on `fear_conversion`, after Midnight's, and the
    more expensive of the two - 2 Stress against Midnight-Touched's one.

    SIMULATION RULE - policy, ruled. **A Stress ceiling, exactly as Codex-Touched
    has**, and the user chose it for the same reason: this is asked on *every*
    success with Fear, so the standing last-slot rule would run a caster's whole
    track through one card in a few spotlights and leave nothing for the domain's
    other Stress costs - and Dread charges Stress on five other cards. Firing
    whenever the shared rule allows, and a ceiling on the GM's Fear pool instead,
    were both offered and declined.

    So this asks `can_spend_stress` rather than `will_spend_stress`: the ceiling
    replaces the willingness rule, which is Codex-Touched's arrangement and the only
    other place in the project that does it.
    """
    if fight is None:
        return False
    if roller.stress_marked >= DREAD_TOUCHED_STRESS_CEILING:
        return False
    if not roller.can_spend_stress(DREAD_TOUCHED_STRESS):
        return False

    roller.spend_stress(DREAD_TOUCHED_STRESS)
    fight.note(f"{roller.name} swallows the dread, and the GM gains nothing")
    return True


@roll_bonus(
    DREAD_TOUCHED,
    unmodelled=[
        TOUCHED_LOADOUT_GAP,
        "Two action rolls the hook is not asked at - Splendor's Healing Hands and "
        "Grace's Invisibility both roll `roll_duality` by hand rather than through "
        "the shared Spellcast shape. Sage-Touched and Inevitable declare the same "
        "two",
    ],
)
def dread_touched_draws_on_the_pool(
    holder: Holder, target, fight: Fight = None, trait: str = ""
) -> int:
    """Dread-Touched's second clause - the GM's whole Fear pool, once per rest.

    **The largest single roll bonus in the project**, and the only one whose size is
    the GM's own resources: at the 12-Fear cap it is +12 on one action roll, where
    the next largest anybody carries is Forest Sprites' +3.

    SIMULATION RULE - policy. The standing rule for a free once-per-rest that Deadly
    Focus, Premonition and Sage-Touched's doubling already follow: it fires on the
    **first** action roll where it would be worth anything. Holding it for a bigger
    pool would mostly mean not using it, and nothing about the roll being made says
    whether a better moment is coming.

    Umbral Veil's ruling points the same way for a second reason specific to this
    domain: Fear accumulates before a fight and is spent down during it, so the pool
    is generally fullest at the opening and waiting is as likely to shrink the bonus
    as to grow it.

    Declines on an **empty pool** rather than claiming the use for +0, the standing
    zero-benefit rule. `trait` is unused: the card names none.

    Being asked is the commitment, this hook's contract - so the use is claimed here
    and a reroll re-makes the dice without charging again.
    """
    if fight is None or not fight.fear:
        return 0
    if not fight.use_once_per_rest(holder, DREAD_TOUCHED):
        return 0

    fight.note(f"{holder.name} draws on the GM's dread (+{fight.fear})")
    return fight.fear


# --- Dark Army -------------------------------------------------------------------

DARK_ARMY = "Dark Army"

DARK_ARMY_DIFFICULTY = 14
DARK_ARMY_TOKENS = 8
DARK_ARMY_DIE = 8

FIENDS = "Dark Army fiends"

# SIMULATION RULE - policy, ruled. "Spend **any number** of tokens" twice over, for
# two different things, and the user's rule is to spend as each occasion arises
# rather than budgeting between them - one token per trigger, first come, first
# served. Named so changing it is a one-line edit.
DARK_ARMY_PER_TRIGGER = 1


@action(DARK_ARMY)
def dark_army(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Dark Army (Dread, level 8). Eight fiends, spent a favour at a time.

    SRD: "Make a Spellcast Roll (14). Once per long rest on a success, you can
    summon dark fiends that surround and move with you. Place 8 tokens on this card.
    When you deal damage to a target within Very Close range, you can spend any
    number of tokens to add 1d8 for each token spent to your damage roll.
    Additionally, when you take damage, you can spend any number of tokens to reduce
    the damage by 1d8 for each token spent. Each time you spend a token, a fiend acts
    on your behalf, then disappears. When you take a rest, clear all unspent tokens."

    **The first pool in the project spent on two different things.** Every other
    token pool has one use - Thorn Skin reduces, Unleash Chaos and Spellcharge add,
    Fane of the Wilds buys a roll back - and this one is both a damage bonus and a
    ward drawing on the same eight charges.

    SIMULATION RULE - policy, ruled. **Spend as it happens**, one token per trigger,
    with no budget kept back for the other use. The user's rule, chosen over
    reserving for defence first (Thorn Skin's fewest-that-cross-a-band rule),
    emptying the pool into the first damage roll (Spellcharge's answer), and
    splitting it down the middle. Its consequence is worth knowing: which half of
    the card gets the tokens is decided by what happens first rather than by what
    they are worth, so a caster nothing attacks spends them all on damage and one
    under pressure spends them all warding.

    A flat Difficulty of 14, printed on the card - the fiends are summoned rather
    than aimed at anybody. Once per long rest **on a success**, so a failed cast
    costs the spotlight and leaves the card available.
    """
    if fight is None or fight.token_count(caster, FIENDS):
        return None
    if not fight.can_use_once_per_rest(caster, DARK_ARMY, long=True):
        return None

    attack_roll = spellcast(caster, target, fight, difficulty=DARK_ARMY_DIFFICULTY)
    if attack_roll is None:
        return None
    if not attack_roll.is_success:
        fight.note(f"{caster.name} calls, and nothing crawls out ({attack_roll})")
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    fight.use_once_per_rest(caster, DARK_ARMY, long=True)
    fight.set_token(caster, FIENDS, DARK_ARMY_TOKENS)
    fight.note(f"{caster.name} is surrounded by {DARK_ARMY_TOKENS} dark fiends")
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


@extra_damage(
    DARK_ARMY,
    unmodelled=[
        "'within Very Close range' - no positions are tracked, so the area rule "
        "answers whether this particular target is close enough, rolled per attack "
        "the way Natural Familiar's is",
    ],
)
def dark_army_strikes(attacker: Holder, target, roll, fight: Fight = None) -> list:
    """A fiend spending itself on one of its summoner's damage rolls.

    Registered on the same name as the action above. `discardable=False`, like every
    other die a feature adds to somebody else's roll: a Massive or Powerful weapon
    discards the lowest of the dice *it* rolled, and this is not one of them.

    Being asked is the commitment, which is this hook's contract - so the fiend is
    spent here rather than waiting to be told the damage landed.
    """
    if fight is None:
        return []

    living = fight.living_adversaries
    if not living or random.random() >= chance_within(Range.VERY_CLOSE, len(living)):
        return []
    if not fight.spend_tokens(attacker, FIENDS, DARK_ARMY_PER_TRIGGER):
        return []

    fight.note(f"A fiend throws itself at {target.name}")
    return [
        DiceGroup(count=DARK_ARMY_PER_TRIGGER, sides=DARK_ARMY_DIE, discardable=False)
    ]


@ally_damage_reduction(DARK_ARMY)
def dark_army_shields(
    holder: Holder, target, amount: int, fight: Fight, damage_type=None
) -> int:
    """A fiend spending itself taking a blow meant for its summoner.

    Registered on `ally_damage_reduction` and then scoped straight back to its own
    holder, which is the arrangement Magic Immunity and Specter of the Dark already
    use: it is the one hook asked with the raw damage in hand, before the
    thresholds, and the severity hooks work on Hit Points instead.

    The die is rolled rather than fixed, so the reduction is 1-8 and the card cannot
    promise what a token is worth.
    """
    if fight is None or target is not holder:
        return 0
    if not fight.spend_tokens(holder, FIENDS, DARK_ARMY_PER_TRIGGER):
        return 0

    absorbed = random.randint(1, DARK_ARMY_DIE)
    fight.note(f"A fiend takes {absorbed} of the blow for {holder.name}")
    return absorbed


# --- Eldritch Flesh --------------------------------------------------------------

ELDRITCH_FLESH = "Eldritch Flesh"

ELDRITCH_FLESH_HOPE = 2


@severity_response(ELDRITCH_FLESH)
def eldritch_flesh(
    holder: Holder, amount: int, hp_to_mark: int, fight: Fight = None, damage_type=None
) -> int:
    """Eldritch Flesh (Dread, level 8), first clause. Thresholds that rise as you fray.

    SRD: "Gain a +1 bonus to your damage thresholds for each Stress you have marked.
    Additionally, when you roll with Fear, you can spend 2 Hope to clear an Armor
    Slot."

    **The first threshold bonus in the project that moves during a fight.** Every
    other one is a number a character sheet carries already resolved - the standing
    rule - and Blade's *Frenzy* is the only card with a threshold clause at all,
    which it can express as a constant because its +8 is fixed. This one is the
    caster's marked Stress, so it changes with every cost they pay.

    Expressed as a **severity response** rather than by writing the thresholds: the
    hook is handed the damage and what it currently marks, so the band can simply be
    re-read against raised numbers. Taking the smaller of the two answers means the
    card can only ever help, and it composes safely with an Armor Slot that has
    already had its say.

    No policy to rule on: it costs nothing, has no limit and states its own trigger.
    It is inert at no Stress marked, which is the card doing what it says rather
    than a threshold of ours.
    """
    if hp_to_mark <= 0 or holder.stress_marked <= 0:
        return hp_to_mark

    bonus = holder.stress_marked
    major = holder.major_threshold + bonus
    severe = holder.severe_threshold + bonus
    hardened = 3 if amount >= severe else 2 if amount >= major else 1

    if hardened >= hp_to_mark:
        return hp_to_mark
    if fight is not None:
        fight.note(f"{holder.name}'s flesh crawls, and the blow costs one less")
    return hardened


@on_roll(ELDRITCH_FLESH)
def eldritch_flesh_mends(holder: Holder, roll, fight: Fight) -> None:
    """Eldritch Flesh's second clause - an Armor Slot bought back with a roll's Fear.

    Registered on the same name as the severity response above.

    SIMULATION RULE - policy, ruled. **Fires on the trigger whenever there is
    enough Hope and a marked Armor Slot to clear** - the user's ruling, and
    deliberately *not* the gate Life Ward and Healing Strike got for the same 2
    Hope. What separates them is what the Hope buys: those two spend it on
    somebody else's Hit Points, where an Armor Slot is the resource this PC is
    about to need on the next hit, and the card offers it only on a roll that
    already went badly. So there is no moment worth holding it for.

    The two conditions are the whole policy. A slot must actually be marked, which
    is the standing zero-benefit rule rather than a threshold, and the Hope must be
    there to pay.
    """
    if fight is None or holder.armor_marked <= 0:
        return
    if roll.outcome is not DualityOutcome.FEAR:
        return
    if not holder.can_spend_hope(ELDRITCH_FLESH_HOPE):
        return

    holder.spend_hope(ELDRITCH_FLESH_HOPE)
    holder.clear_armor_slot(1)
    fight.note(f"{holder.name}'s armor knits itself back together")


# --- Damnation -------------------------------------------------------------------

DAMNATION = "Damnation"

DAMNATION_DIE = 20


@action(
    DAMNATION,
    unmodelled=[
        "'within Far range' of the caster and of the target - no positions are "
        "tracked, so the spell always reaches and the area rule decides how much of "
        "the field the target's death carries to",
    ],
)
def damnation(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Damnation (Dread, level 9). A d20 a Stress, and the field feels it die.

    SRD: "Make a Spellcast Roll against a target within Far range. On a success,
    mark any number of Stress to roll an equal number of d20s, dealing magic damage
    equal to the total result. If this attack defeats the target, all adversaries
    within Far range of the target must mark a Stress."

    **A whole d20 per Stress with no flat modifier at all**, which is the largest
    per-Stress damage in the project - Falling Sky's shards are 1d20+2 apiece but
    spread across an area, and this puts every die into one creature.

    SIMULATION RULE - policy. Falling Sky's rule, which is the standing answer for a
    Stress-priced "any number": `will_spend_stress` asked once per die, so a full
    track empties to one spare slot on a single cast and stops. Nothing new to rule.

    Declines before rolling when no Stress can be paid at all, per the standing
    zero-benefit rule - the spell does nothing without at least one die.

    The Stress its kill forces on the rest of the field is the second half, and it
    is **forced** rather than spent, so an adversary with a full track marks a Hit
    Point instead.
    """
    if fight is None:
        return None
    if not caster.will_spend_stress(1):
        return None

    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None
    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    dice = 0
    while caster.will_spend_stress(1):
        caster.spend_stress(1)
        dice += 1

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=dice, sides=DAMNATION_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        is_critical=attack_roll.is_critical,
    )
    marked = target.take_damage(damage_roll.total, fight, damage_type=DamageType.MAGIC)
    fight.note(
        f"{caster.name} damns {target.name} with {dice} d20s for {damage_roll.total}"
    )

    if target.is_defeated:
        witnesses = [
            adversary
            for adversary in targets_in_area(Range.FAR, fight.living_adversaries)
            if adversary is not target
        ]
        for adversary in witnesses:
            adversary.mark_stress(1, fight)
        if witnesses:
            fight.note(f"{len(witnesses)} of the field feel {target.name} go")

    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


# --- Savor the Anguish -----------------------------------------------------------

SAVOR_THE_ANGUISH = "Savor the Anguish"


@ally_on_hit(
    SAVOR_THE_ANGUISH,
    unmodelled=[
        "'within Close range' - no positions are tracked, so any adversary the "
        "party wounds severely is close enough",
        "Severe damage from anything other than a **party attack** never reaches "
        "this: `ally_on_hit` is asked where a landed attack rolled damage, so an "
        "adversary hurt by its own side, or by a card that marks Hit Points without "
        "dealing damage, is not savoured",
    ],
)
def savor_the_anguish(
    holder: Holder, attacker, target, result, fight: Fight = None
) -> None:
    """Savor the Anguish (Dread, level 9). Somebody else's pain, taken as rest.

    SRD: "When an adversary within Close range takes Severe damage, you can clear a
    Stress."

    Costs nothing, has no limit, and takes no roll - the only wholly free card in
    the domain, and one of very few anywhere. On the **party-wide** hit hook rather
    than the holder's own, because the card says "an adversary takes Severe damage"
    without naming who dealt it, so an ally's blow feeds it exactly as the holder's
    does.

    Severe is read off the damage **amount** against the target's printed Severe
    threshold, which is Get Back Up's and Shrug It Off's reading of the same word -
    so a hit that armor or a resistance softened below the line does not count, and
    the number both sides of the table can see is what decides it.

    No policy to rule on. It is skipped when there is no Stress to clear, which is
    the difference between clearing something and clearing nothing rather than a
    threshold.
    """
    if fight is None or holder.stress_marked <= 0:
        return
    if result.damage_roll is None:
        return
    if result.damage_roll.total < target.severe_threshold:
        return

    holder.clear_stress(1)
    fight.note(f"{holder.name} savours {target.name}'s anguish, and breathes easier")


# --- Avatar of Terror ------------------------------------------------------------

AVATAR_OF_TERROR = "Avatar of Terror"

AVATAR_DIE = 6


def _the_terror_holds(holder, fight, moment: str) -> None:
    """The Hope owed before each action roll, and the reversion when it isn't there.

    Force of Nature's upkeep exactly, and deliberately a second copy rather than an
    import: one card must never import another's module, so the two domains carry
    the same eight lines. If a third card ever needs it, it belongs in
    `content/` instead.
    """
    if moment != BEFORE_AN_ACTION_ROLL:
        return

    if holder.can_spend_hope(1):
        holder.spend_hope(1)
        return

    fight.clear_condition(holder, FEAR_FUELED)
    fight.note(f"{holder.name} runs out of Hope, and the terror drains away")


@free(
    AVATAR_OF_TERROR,
    unmodelled=[
        "The state has no printed keyword - the card describes a transformation and "
        "lists its benefits - so `FEAR_FUELED` is the simulator's own label. See "
        "`content/conditions.py`",
    ],
)
def avatar_of_terror(holder: Holder, fight: Fight) -> bool:
    """Avatar of Terror (Dread, level 10). Become the thing the GM's Fear is for.

    SRD: "Mark a Stress to transform into a creature fueled by fear. While in this
    form, you gain a 1d6 bonus to your damage rolls for each Fear in the GM's pool.
    Additionally, you gain a Hope when the GM spends a Fear to spotlight an
    adversary within Very Close range. Before you make an action roll, you must
    spend a Hope. If you can't, you revert to your normal form."

    **Force of Nature's shape with the GM's pool wired into the damage.** Both cost
    a Stress to enter and a Hope before every action roll; where Sage's form adds a
    flat +10, this one adds *1d6 per Fear the GM is holding*, re-read on every
    damage roll - so it is the only thing in the project whose damage moves during a
    fight because of something the other side of the table did.

    SIMULATION RULE - policy, ruled. **Taken at the start of the battle** - the
    first spotlight the Stress allows, with no Hope floor. The user's ruling, and it
    parts company with Force of Nature deliberately: that card was given a floor
    because an empty pool would revert it on the next roll, and here the same
    reasoning that settled Umbral Veil applies instead - the GM's Fear is fullest at
    the opening, and the form is worth most while it is. Reading Force of Nature's
    floor across, and gating on the size of the Fear pool, were both offered and
    declined.

    **No roll**, so it is a free ability: the form is taken *and* an action roll
    made in the same spotlight - and that roll is charged for, since the upkeep is
    announced before every one.
    """
    if fight is None or fight.has_condition(holder, FEAR_FUELED):
        return False
    if not holder.will_spend_stress(1):
        return False

    holder.spend_stress(1)
    fight.apply_condition(
        holder,
        Condition(name=FEAR_FUELED, effect=_the_terror_holds, source=holder),
    )
    fight.note(f"{holder.name} becomes an avatar of terror")
    return True


@extra_damage(AVATAR_OF_TERROR)
def avatar_of_terror_feeds(
    attacker: Holder, target, roll, fight: Fight = None
) -> list:
    """A d6 for every Fear the GM is holding, read at the moment damage is rolled.

    Registered on the same name as the free ability above. On `extra_damage` rather
    than `damage_bonus` because the card says *1d6 bonus*, which is dice rather than
    a number - so it lands in the same `roll_damage` call and crosses the target's
    thresholds once.

    Read **per damage roll**, not fixed when the form was taken: the pool moves, and
    the card says "for each Fear in the GM's pool" in the present tense. An empty
    pool adds nothing, which is the card read literally rather than a decline.
    """
    if fight is None or not fight.has_condition(attacker, FEAR_FUELED):
        return []
    if not fight.fear:
        return []

    return [DiceGroup(count=fight.fear, sides=AVATAR_DIE, discardable=False)]


@ally_on_spotlight(
    AVATAR_OF_TERROR,
    unmodelled=[
        "'within Very Close range' - no positions are tracked, so the area rule "
        "answers whether this particular adversary is close enough, drawn per "
        "spotlight the way Natural Familiar's is",
    ],
)
def avatar_of_terror_feeds_on_fear(
    holder: Holder, adversary, fight: Fight = None, paid: bool = False
) -> None:
    """The Hope the form takes back each time the GM buys a spotlight nearby.

    Registered on the same name as the free ability above, and **this is the clause
    the hook was built for**: "you gain a Hope when the GM spends a Fear to
    spotlight an adversary within Very Close range" is a fact about the GM's
    economy rather than about anything the adversary then does, and nothing on the
    party's side of the table could be asked about it.

    `paid` is what makes it correct rather than approximately correct. A GM turn's
    **first** activation costs no Fear, and a spotlight handed out by content - the
    Young Dryad's Voice of the Forest - was bought by that feature rather than by
    the turn's budget. Neither is the GM spending a Fear, and both would have paid
    out if this had keyed on "an adversary is up" instead.

    So the form partly funds its own upkeep: a Hope in, a Hope owed before each
    action roll. Worth watching when these are run, since it is the only thing in
    the project where the two sides' economies are wired directly together.
    """
    if fight is None or not paid:
        return
    if not fight.has_condition(holder, FEAR_FUELED):
        return

    living = fight.living_adversaries
    if not living or random.random() >= chance_within(Range.VERY_CLOSE, len(living)):
        return

    holder.gain_hope(1)
    fight.note(f"{holder.name} feeds on the Fear spent to move {adversary.name}")


# --- Invoke Torment --------------------------------------------------------------

INVOKE_TORMENT = "Invoke Torment"

INVOKE_TORMENT_MULTIPLIER = 2


@damage_scaling(INVOKE_TORMENT)
def invoke_torment(attacker: Holder, target, fight: Fight = None) -> float:
    """Invoke Torment (Dread, level 10), first clause. Double damage to the spent.

    SRD: "You deal double damage to targets that have all their Stress marked.
    Additionally, when an adversary within Close range is defeated with all its
    Stress marked, you gain a Hope."

    **The domain's payoff for everything else it does.** Dread forces Stress on five
    separate cards - Voice of Dread, Terrify, Summon Horror, Damnation and Wall of
    Hunger - and this is what a filled track is finally worth: every one of the
    caster's blows lands twice as hard.

    On `damage_scaling`, which multiplies the roll before the target's thresholds
    are read, so doubling can move a hit up a band rather than only up a number.

    Read off the target's own track at the moment damage is rolled, so an adversary
    that clears a Stress stops being worth double immediately. No policy to rule on:
    the card costs nothing, has no limit and states its own trigger exactly.
    """
    if target.stress_marked < target.stress_max:
        return 1
    return INVOKE_TORMENT_MULTIPLIER


@on_hit(
    INVOKE_TORMENT,
    unmodelled=[
        "'within Close range' - no positions are tracked, so any adversary the "
        "holder finishes counts",
        "An adversary defeated by something other than the holder's own landed "
        "attack pays nothing - `on_hit` is holder-scoped, and the card says only "
        "'when an adversary is defeated', which would include an ally's kill",
    ],
)
def invoke_torment_savours(
    attacker: Holder, target, result, fight: Fight
) -> None:
    """Invoke Torment's second clause - a Hope for finishing something hollowed out.

    Registered on the same name as the damage scaling above. Pays only when the
    target was defeated **with its whole Stress track marked**, which is the card
    read literally and is the same state the doubling keys on - so the two clauses
    reward the same work.
    """
    if fight is None or not target.is_defeated:
        return
    if target.stress_marked < target.stress_max:
        return

    attacker.gain_hope(1)
    fight.note(f"{attacker.name} savours the end of {target.name} (+1 Hope)")


# --- Wall of Hunger --------------------------------------------------------------

WALL_OF_HUNGER = "Wall of Hunger"

WALL_OF_HUNGER_DIFFICULTY = 10
WALL_OF_HUNGER_STRESS = 2

# SIMULATION RULE - policy, ruled. The Fire Flies and Rain of Blades floor: a cast
# that costs a Hope beyond the roll waits for a second target.
WALL_OF_HUNGER_WORTH_IT = 2


@action(
    WALL_OF_HUNGER,
    unmodelled=[
        "'that passes through it' - the second half of the trigger is movement, "
        "and none is tracked. Only creatures caught as the wall appears mark the "
        "Stress, so a wall left standing does nothing at all here",
        "'The wall lasts until you mark a Hit Point or cast this spell again' - "
        "with the standing wall inert, its duration has nothing to govern, so "
        "neither ender is modelled and the spell can simply be cast again",
        "'between two points within Far range' - the wall's own reach is not what "
        "decides who it catches; the area rule is, at the band the user ruled",
    ],
)
def wall_of_hunger(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Wall of Hunger (Dread, level 7). A Hope, and the front rank chokes on it.

    SRD: "Make a Spellcast Roll (10). On a success, you can spend a Hope to create a
    visible wall of writhing necrotic energy between two points within Far range.
    The wall lasts until you mark a Hit Point or cast this spell again. A creature
    inside the wall when it appears or that passes through it must mark 2 Stress."

    SIMULATION RULE - rules interpretation, ruled. **The wall catches through the
    area rule**, at the **Close** band with a floor of two. The user's ruling, and
    it is worth recording what it settles: a wall is a piece of terrain, and terrain
    has no representation here - the reading that dismissed Codex's *Manifest Wall*
    and Sage's *Plant Dominion*. The user ruled instead that a wall conjured **into**
    a fight catches whoever the band reaches, which is the same answer Hold the Line
    got for its movement trigger. Dismissing this card was offered and declined.

    So what runs is a Stress sweep for a Hope: everything the Close band reaches
    marks 2 Stress as the wall appears. The standing wall is inert, which is
    declared above, and it errs **against** the card - at a table the thing keeps
    working after the round it went up.

    A flat Difficulty of 10, printed on the card and the lowest anything asks for -
    the wall is conjured rather than aimed at anybody.

    The Stress is **forced** rather than spent, so an adversary with a full track
    marks a Hit Point instead.

    The band is drawn **before** the roll and reused, so the floor and the sweep see
    the same field - asking twice would let the card decline against one arrangement
    and resolve against another.
    """
    if fight is None:
        return None
    if not caster.can_spend_hope(1):
        return None

    caught = targets_in_area(Range.CLOSE, fight.living_adversaries)
    if len(caught) < WALL_OF_HUNGER_WORTH_IT:
        return None

    attack_roll = spellcast(
        caster, target, fight, difficulty=WALL_OF_HUNGER_DIFFICULTY
    )
    if attack_roll is None:
        return None
    if not attack_roll.is_success:
        fight.note(f"{caster.name}'s wall fails to rise ({attack_roll})")
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    caster.spend_hope(1)
    for adversary in caught:
        adversary.mark_stress(WALL_OF_HUNGER_STRESS, fight)
    fight.note(
        f"{caster.name} raises a wall of hunger, and {len(caught)} choke on it "
        f"({WALL_OF_HUNGER_STRESS} Stress each)"
    )

    # No damage of its own, so nothing that reads a landed hit fires off this.
    return AttackResult(attack_roll=attack_roll, damage_roll=None)
