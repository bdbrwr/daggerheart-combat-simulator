"""Splendor domain cards.

Card text is paraphrased in each docstring rather than quoted in full. The
verbatim text is in .reference/abilities.json, checked against the printed page
(SRD p. 132).

Splendor is the restoring domain, and at level 3 both cards give something back:
one off a landed attack, one off having nothing left to give. Voice of Reason is
the first card anywhere that turns **on** when its holder is out of Stress, which
is also the moment they become Vulnerable.

Level 4 takes that as far as it goes. **Life Ward** is the first thing anywhere
that reaches a **death move** - three Hope buys an ally one that never happens -
and it is worth reading its numbers knowing what it costs: three Hope is most of
a pool, and the ward does nothing at all until the moment it does everything.

Level 5's **Smite** is the first content anywhere that scales a PC's *own* damage.
The GM side has multiplied damage since the Kneebreaker; the party had no way to,
because every damage hook here adds to a roll or reshapes it rather than scaling
the finished number. Doubling has to reach the dice, the modifier and the critical
bonus at once, which is what put a `multiplier` on `DamageRollResult`.
"""

import random
from dataclasses import replace

from combat.results import AttackResult
from content.aoe import Range, targets_in_area
from content.conditions import VULNERABLE, Condition, when_the_gm_pays
from content.damage_types import DamageType
from content.help import help_with_roll
from content.registry import (
    DamagePool,
    Fight,
    Holder,
    action,
    damage_pool,
    damage_scaling,
    damage_typing,
    death_move_ward,
    free,
    hope_die_for,
    no_combat_effect,
    on_hit,
    out_of_combat_ability,
    reroll,
    total_extra_damage,
)
from content.spellcast import spellcast
from dice.damage import DiceGroup, roll_damage
from dice.duality import DualityOutcome, roll_duality

HEALING_HANDS_DIFFICULTY = 13

BOLT_BEACON_DIE = 8
BOLT_BEACON_MODIFIER = 2

REASSURANCE = "Reassurance"

SECOND_WIND = "Second Wind"
VOICE_OF_REASON = "Voice of Reason"

# Second Wind clears exactly this much Stress, and the clearing-in-full rule
# means it takes the Hit Point instead when that many aren't marked.
SECOND_WIND_STRESS = 3

# Only worth a spotlight's roll once an ally is genuinely in trouble. Healing
# somebody at full HP spends the party's tempo on nothing.
HURT_ENOUGH_TO_HEAL = 2


@action(
    "Healing Hands",
    unmodelled=[
        "'within Melee range' - no positions are tracked, so any ally can be "
        "reached",
        "clearing Stress instead of HP - HP is always chosen, since a downed "
        "PC is what actually ends a fight",
    ],
)
def healing_hands(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Healing Hands (Splendor, level 2). Spellcast Roll (13) against an ally other
    than yourself; on a success mark a Stress to clear 2 HP on them, on a failure
    mark a Stress to clear 1. The same target can't be healed again until your
    next long rest.

    `target` is the adversary the turn policy picked, and is ignored - this
    spell aims at an ally instead. It declines unless somebody is hurt enough to
    be worth a spotlight, which is what stops a healer standing in the back
    topping people up instead of fighting.

    The per-long-rest limit is per *target*, so the once-per-rest key carries
    the ally's name with it.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None
    if not caster.can_spend_stress(1):
        return None

    patient = _who_needs_it(caster, fight)
    if patient is None:
        return None
    if not fight.use_once_per_rest(caster, f"Healing Hands:{patient.name}", long=True):
        return None

    # Asked only once every decline above has passed, so an ally never pays a
    # Hope toward a heal that isn't happening.
    helped = help_with_roll(caster, fight)
    roll = roll_duality(
        modifier=caster.traits[trait] + helped.bonus,
        difficulty=HEALING_HANDS_DIFFICULTY,
        hope_die=hope_die_for(caster, fight),
        help_dice=helped.dice,
    )
    caster.spend_stress(1)
    cleared = 2 if roll.is_success else 1
    patient.clear_hp(cleared)
    fight.note(f"{caster.name} heals {patient.name} for {cleared} HP")

    # No damage was dealt, but a roll was made - and it's the roll, not the
    # damage, that decides whether the spotlight moves.
    return AttackResult(attack_roll=roll, damage_roll=None)


def _who_needs_it(caster: Holder, fight: Fight):
    """The worst-off conscious ally, if anyone is hurt enough to be worth it."""
    allies = [
        pc
        for pc in fight.conscious_party
        if pc is not caster and pc.hp_unmarked <= HURT_ENOUGH_TO_HEAL
    ]
    if not allies:
        return None
    return min(allies, key=lambda pc: pc.hp_unmarked)


@action(
    "Bolt Beacon",
    unmodelled=[
        "'within Far range' - no positions are tracked, so this always reaches",
        "The target glowing brightly - light has no representation here beyond "
        "the Vulnerable the same clause applies",
    ],
)
def bolt_beacon(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Bolt Beacon (Splendor, level 1).

    SRD: make a Spellcast Roll against a target within Far range. On a success,
    spend a Hope to send a bolt of shimmering light toward them, dealing d8+2
    magic damage using your Proficiency. The target becomes temporarily
    Vulnerable and glows brightly until this condition is cleared.

    **The Hope is the delivery, not an upgrade.** The card's damage clause is
    inside "spend a Hope to send a bolt", so with no Hope banked there is no bolt
    - which is why this declines before rolling rather than rolling and then
    failing to pay. Contrast Forceful Push, where the attack happens either way
    and the Hope only buys the condition.

    The Vulnerable isn't optional for the same reason: the card states it as part
    of what the bolt does, so nothing here weighs whether to apply it. It is
    skipped only against a target the hit just defeated, which is off the field.

    "Temporarily", on an adversary, is the standing reading - it lasts until the
    GM spends a Fear on it.
    """
    if not caster.can_spend_hope(1):
        return None

    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    caster.spend_hope(1)
    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=caster.proficiency, sides=BOLT_BEACON_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=BOLT_BEACON_MODIFIER,
        is_critical=attack_roll.is_critical,
    )
    marked = target.take_damage(
        damage_roll.total, fight, damage_type=DamageType.MAGIC
    )

    if not target.is_defeated:
        fight.apply_condition(
            target, Condition(name=VULNERABLE, end=when_the_gm_pays, source=caster)
        )
    fight.note(
        f"{caster.name} lights {target.name} up for {damage_roll.total} "
        "(Vulnerable)"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


@reroll(REASSURANCE)
def reassurance(holder: Holder, roller, roll, remake, fight: Fight):
    """Reassurance (Splendor, level 1). Returns the replacement roll, or None.

    SRD: once per rest, after an ally attempts an action roll but before the
    consequences take place, you can offer assistance or words of support. When
    you do, your ally can reroll their dice.

    **An ally's roll only.** The card says "an ally", where the Faerie's
    Luckbender says "yours or a willing ally's" - so this checks `holder is
    roller` and declines on its own holder's rolls.

    SIMULATION RULE - policy, ruled. Spent on any **failed** roll by an ally.
    That is Luckbender's trigger without its Hope floor, because this costs
    nothing at all: there is no resource to weigh, only the single per-rest use,
    and rerolling a success buys nothing measurable.

    A roll made with no Difficulty has no failure to rescue, so `is_success is
    False` rather than a falsy check - None would otherwise read as a failure.

    Being asked is close to the commitment for this hook, so the per-rest use is
    claimed only once every other check has passed.
    """
    if fight is None or holder is roller:
        return None
    if roll.is_success is not False:
        return None
    if not fight.use_once_per_rest(holder, REASSURANCE):
        return None

    fight.note(f"{holder.name} steadies {roller.name}, who tries again")
    return remake()


# --- Second Wind -------------------------------------------------------------


@on_hit(
    SECOND_WIND,
    unmodelled=[
        "'an ally within Close range' - no positions are tracked, so the area "
        "rule in SIMULATION-RULES.md decides who is close enough to catch the "
        "second half",
        "A success on an action roll that isn't an attack - the on-hit hook only "
        "sees an attack that landed, and the card says 'succeed on an attack'",
    ],
)
def second_wind(attacker: Holder, target, result, fight: Fight) -> None:
    """Second Wind (Splendor, level 3).

    SRD: "Once per rest, when you succeed on an attack against an adversary, you
    can clear 3 Stress or a Hit Point. On a success with Hope, you also clear 3
    Stress or a Hit Point on an ally within Close range of you."

    SIMULATION RULE - policy, ruled. **3 Stress whenever 3 are marked, otherwise
    the Hit Point.** The Stress is the bigger clear and the number the card is
    priced around, and taking it only at 3 is the standing clearing-in-full rule:
    a feature that clears a named quantity is used when it can clear all of it.

    A PC with neither 3 Stress nor a marked HP gains nothing, so the per-rest use
    is checked first and claimed only once somebody will actually be restored.

    The second half rides `DualityOutcome.HOPE` specifically. A **critical is not
    "with Hope"** - it is its own outcome with the two dice matched, which is the
    reading Face Your Fear and Forceful Push's momentum die already take.

    Which ally is random among those in range who would gain something, which is
    the standing rule for a choice with none of its own. Picking the worst-off
    would be scoring the party.
    """
    if fight is None or result.attack_roll is None:
        return
    if not result.attack_roll.is_success:
        return
    if not fight.can_use_once_per_rest(attacker, SECOND_WIND):
        return

    reached = []
    if getattr(result.attack_roll, "outcome", None) is DualityOutcome.HOPE:
        allies = [pc for pc in fight.conscious_party if pc is not attacker]
        reached = [
            ally for ally in targets_in_area(Range.CLOSE, allies) if _restorable(ally)
        ]

    if not _restorable(attacker) and not reached:
        return

    fight.use_once_per_rest(attacker, SECOND_WIND)
    if _restorable(attacker):
        _second_wind_restores(attacker, fight)
    if reached:
        _second_wind_restores(random.choice(reached), fight)


def _restorable(pc: Holder) -> bool:
    """Whether Second Wind would actually clear anything on this PC."""
    return pc.stress_marked >= SECOND_WIND_STRESS or pc.hp_marked > 0


def _second_wind_restores(pc: Holder, fight: Fight) -> None:
    """Clear the 3 Stress if they are all there, otherwise a Hit Point."""
    if pc.stress_marked >= SECOND_WIND_STRESS:
        pc.clear_stress(SECOND_WIND_STRESS)
        fight.note(f"{pc.name} catches their second wind, clearing "
                   f"{SECOND_WIND_STRESS} Stress")
    else:
        pc.clear_hp(1)
        fight.note(f"{pc.name} catches their second wind, clearing an HP")


# --- Voice of Reason ---------------------------------------------------------


@damage_pool(
    VOICE_OF_REASON,
    unmodelled=[
        "'Advantage on action rolls to de-escalate violent situations or "
        "convince someone to follow your lead' - the simulator makes attack "
        "rolls, Spellcast Rolls and Reaction Rolls and never rolls to talk "
        "anybody down, so there is no roll for the advantage to land on",
        "Damage rolled by anything other than a weapon. Several cards roll "
        "Proficiency dice of their own - Bolt Beacon's d8+2, Corrosive "
        "Projectile's d6+4 - and none of them consults the damage-pool hook, so "
        "the bonus reaches weapon swings only",
    ],
)
def voice_of_reason(
    holder: Holder, weapon, pool: DamagePool, fight: Fight = None
) -> DamagePool:
    """Voice of Reason (Splendor, level 3), second clause.

    SRD: "You're emboldened in moments of duress. When all of your Stress slots
    are marked, you gain a +1 bonus to your Proficiency for damage rolls."

    Proficiency is the *count* of damage dice a weapon rolls, so +1 Proficiency
    is one more of the weapon's own dice - which is why this reshapes the pool
    rather than adding a die through `extra_damage`. The extra die is
    **discardable**, unlike a die a feature lends to somebody else's roll: it is
    one of the weapon's dice in every sense the SRD uses, so a Massive or
    Powerful discard is entitled to throw it away.

    No policy to rule on. The card has no cost and no limit and states its own
    trigger exactly - every Stress slot marked - so it is on whenever that is
    true and off whenever it isn't.

    Worth noting what the trigger coincides with rather than what it is worth: a
    PC with every Stress marked is **Vulnerable** by the rules, so every roll
    against them has Advantage at the same moment this turns on. The two are
    worth reading together when the numbers come in.
    """
    if holder.stress_marked < holder.stress_max:
        return pool
    if not pool.dice_groups:
        return pool

    groups = list(pool.dice_groups)
    groups[0] = replace(groups[0], count=groups[0].count + 1)
    if fight is not None:
        fight.note(f"{holder.name} is emboldened; +1 Proficiency on the damage")
    return pool._replace(dice_groups=groups)


# --- Life Ward ---------------------------------------------------------------

LIFE_WARD = "Life Ward"

LIFE_WARD_HOPE = 3

# Set on whoever is wearing the sigil. A token on the *target* rather than on the
# caster, because the dispatch that reads it is asked about whoever is about to
# go down - the same arrangement Rune Ward uses for the same reason.
SIGILLED = "Life Ward sigil"


@free(
    LIFE_WARD,
    unmodelled=[
        "'an ally within Close range' - no positions are tracked, so any "
        "conscious ally can be marked",
        "Moving the sigil. The card ends the ward when you cast Life Ward on "
        "another target, so re-casting is how it moves; here it is placed once "
        "and stays until it is spent",
        "HP marked by anything other than **damage** doesn't reach the ward. "
        "`mark_hp_and_check_death` is handed a fight by `take_damage` and by "
        "nothing else, so a PC whose last HP is marked by Stress that wouldn't "
        "fit, or by a feature saying 'mark an additional HP' outright, makes "
        "their death move with the sigil still on them",
    ],
)
def life_ward(caster: Holder, fight: Fight) -> bool:
    """Life Ward (Splendor, level 4). Three Hope buys somebody one death move.

    SRD: "Spend 3 Hope and choose an ally within Close range. They are marked
    with a glowing sigil of protection. When this ally would make a death move,
    they clear a Hit Point instead. This effect ends when it saves the target
    from a death move, you cast Life Ward on another target, or you take a long
    rest."

    **No roll**, so it is a free ability: 3 Hope and nothing else, and the caster
    can raise the ward *and* take their action roll in the same spotlight.

    SIMULATION RULE - policy, ruled. Two decisions:

    * The sigil goes on the **frailest ally** - whoever has the least unmarked HP
      - and never on the caster, since the card says "an ally". Rune Ward's holder
      rule exactly.
    * It is cast **only once that ally is near death**, at
      `NEAR_DEATH_HP_UNMARKED` unmarked HP or fewer. Casting as soon as the Hope
      allowed was offered and declined: three Hope is most of a pool and the ward
      does nothing at all until a death move is actually coming, so the party
      holds it until one plausibly is.

    Read together, the two halves say the same thing twice on purpose: the ward
    goes to the ally who is about to need it, and it goes up at the moment they
    start needing it. A caster whose *own* HP is low doesn't trigger it - the
    sigil cannot go on them, so nothing would be bought.

    Declines while a sigil already stands, since the card holds on one creature at
    a time and re-casting is how the page moves it rather than a second ward.
    """
    if fight is None or not caster.can_spend_hope(LIFE_WARD_HOPE):
        return False

    party = fight.conscious_party
    if any(fight.token_count(pc, SIGILLED) for pc in party):
        return False

    allies = [pc for pc in party if pc is not caster]
    if not allies:
        return False

    warded = min(allies, key=lambda pc: pc.hp_unmarked)
    if not warded.is_near_death:
        return False

    caster.spend_hope(LIFE_WARD_HOPE)
    fight.set_token(warded, SIGILLED, 1)
    fight.note(f"{caster.name} marks {warded.name} with a sigil of protection")
    return True


@death_move_ward(LIFE_WARD)
def life_ward_saves(caster: Holder, target, fight: Fight) -> bool:
    """The sigil spends itself, and the death move never happens.

    "They clear a Hit Point instead" - so the HP that was just marked comes back
    off and the PC stays up with one unmarked. Nothing else of the death move
    happens: no unconsciousness, no scar roll, and no entry in the `death_moves`
    tally, because being asked here is *before* the move rather than instead of
    part of it.

    Party-wide, since the sigil is worn by somebody other than the caster - the
    same reason Rune Ward is on the party-wide hook. The token says who is
    wearing it, so every other PC's copy of this card correctly declines.

    "This effect ends when it saves the target from a death move" is the token
    being cleared here: one death move, once, and the 3 Hope is gone with it.
    """
    if fight is None or not fight.token_count(target, SIGILLED):
        return False

    fight.set_token(target, SIGILLED, 0)
    target.clear_hp(1)
    fight.note(
        f"{target.name}'s sigil flares and takes the blow - they stay standing"
    )
    return True


# --- Smite ---------------------------------------------------------------------

SMITE = "Smite"

SMITE_HOPE = 3

# The Hope a PC has to be holding before three of it goes on a charge. Luckbender's
# floor, read here for the reason it is read there: a card this expensive must not
# starve the class features that also want Hope.
SMITE_HOPE_FLOOR = 6

# Set on the caster while the smite is charged and waiting for a weapon to land.
SMITE_CHARGED = "Smite charged"

# Set for the moment between the two hooks this card registers on. The doubling is
# asked before the damage is rolled and the retyping after it, so the second one
# cannot read the charge - it has already been spent - and needs its own mark to
# know that this particular hit is the smite.
SMITE_STRUCK = "Smite striking"


@free(SMITE)
def smite(caster: Holder, fight: Fight) -> bool:
    """Smite (Splendor, level 5). Charge the blow, once per rest.

    SRD: "Once per rest, spend 3 Hope to charge your powerful smite. When you next
    successfully attack with a weapon, double the result of your damage roll. This
    attack deals magic damage regardless of the weapon's damage type."

    **No roll**, so charging is a free ability and the caster still swings in the
    same spotlight - which means the charge can be spent on the very attack it was
    bought for.

    SIMULATION RULE - policy, ruled. Charged at **6 Hope or above**, which is
    Luckbender's floor read in a third place. The charge itself never expires
    inside a fight, so there is no moment worth waiting for; what the floor buys is
    that three Hope does not disappear out of a pool the party's other cards are
    drawing on. Charging as soon as the 3 Hope could be paid was offered and
    declined.

    Declines while a charge is already standing - the card holds one.
    """
    if fight is None or fight.token_count(caster, SMITE_CHARGED):
        return False
    if caster.hope_marked < SMITE_HOPE_FLOOR:
        return False
    if not caster.can_spend_hope(SMITE_HOPE):
        return False
    if not fight.use_once_per_rest(caster, SMITE):
        return False

    caster.spend_hope(SMITE_HOPE)
    fight.set_token(caster, SMITE_CHARGED, 1)
    fight.note(f"{caster.name} charges a smite")
    return True


@damage_scaling(
    SMITE,
    unmodelled=[
        "'when you next successfully attack **with a weapon**' reaches a weapon "
        "swing only. A card that rolls its own damage - a Grimoire spell, Bolt "
        "Beacon - is not a weapon attack and correctly never spends the charge, "
        "but it also means a Splendor caster who mostly casts may never use it",
    ],
)
def smite_doubles(holder: Holder, target, fight: Fight = None) -> float | None:
    """The doubling itself, and the moment the charge is spent.

    Asked once, immediately before the weapon's damage is rolled and only after
    the attack has landed - which is exactly "when you next successfully attack
    with a weapon". So the charge is never burned on a miss.

    Returns a factor rather than dice, because doubling has to reach the weapon's
    dice, its flat modifier *and* the critical bonus at once. `roll_damage` takes
    it as `multiplier` and `DamageRollResult.total` floors the product, so every
    later reader - the play-by-play, Whirlwind's splash, the target's on-attacked
    content - sees the number that actually landed.
    """
    if fight is None or not fight.token_count(holder, SMITE_CHARGED):
        return None

    fight.set_token(holder, SMITE_CHARGED, 0)
    fight.set_token(holder, SMITE_STRUCK, 1)
    fight.note(f"{holder.name}'s smite lands, doubling the blow")
    return 2.0


@damage_typing(SMITE)
def smite_is_magic(holder: Holder, target, fight: Fight = None):
    """"Regardless of the weapon's damage type" - the smite is magic.

    Registered on the same name as the doubling above, which is how one card
    reaches two hooks. Asked at the moment the damage is handed to the target,
    which is *after* `smite_doubles` has already cleared the charge - so this
    reads its own token instead, set alongside it.

    Worth knowing what it is worth: the type decides whose resistance applies, so
    a smite gets through an adversary resistant to physical damage and is halved by
    one resistant to magic. The card names it as an upside and it is not always
    one.
    """
    if fight is None or not fight.token_count(holder, SMITE_STRUCK):
        return None

    fight.set_token(holder, SMITE_STRUCK, 0)
    return DamageType.MAGIC


out_of_combat_ability(
    "Mending Touch",
    "Spend 2 Hope to clear a Hit Point or a Stress on somebody, and once per "
    "long rest 2 of either. Real healing, fully representable - but the card "
    "gates it on taking 'a few minutes to focus on the target', which is not "
    "something that happens while a fight is on. It belongs to the party's time "
    "between encounters, and runs when sequenced encounters do.",
)

no_combat_effect(
    "Divination",
    "Once per long rest, 3 Hope asks the forces beyond one yes-or-no question "
    "about an event, person, place or situation in the near future. The answer is "
    "GM narrative: it touches nobody's numbers, grants no roll and makes no "
    "attack, which is the Floating Eye case - information about things nobody is "
    "swinging at. Worth being plain that the dismissal is about *this* "
    "simulation: at a table, knowing the answer to one yes-or-no question can "
    "decide whether a fight happens at all.",
)

no_combat_effect(
    "Shape Material",
    "A Hope shapes a section of natural material the caster is touching - stone, "
    "ice, wood - into a rudimentary tool or a door, no larger than themselves. "
    "Craft, and the simulator has no objects to shape: nothing in a fight is made "
    "of anything, no tool is carried that wasn't authored on the sheet, and a door "
    "is somewhere to go, which is position. It touches nobody's numbers, grants no "
    "roll and makes no attack.",
)

no_combat_effect(
    "Final Words",
    "Infuses a corpse with a moment of life to answer questions. It produces "
    "information about the past, and nothing about a fight's outcome turns on "
    "what a body has to say.",
)
