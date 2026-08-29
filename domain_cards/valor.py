"""Valor domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json, checked against the printed page
(SRD p. 134) - which also settled the level 1-2 cards below, ported before the
printed-page check became part of the process.

Cards from this domain that can't affect a fight are declared at the bottom, so
"assessed and dismissed" never looks like "nobody has got to it yet".

Valor is the one domain with no Spellcast Roll anywhere in its first three
levels: everything here rides a weapon swing, an incoming hit, or somebody
else's roll. That is why it needed no change when Help an Ally landed - Forceful
Push attacks through `items/weapons.py`, which asks for help on the party's
behalf.

**Level 4 does not break that**, which is worth saying because it looks like it
does: *Goad Them On* rolls its own action, but it is a **Presence** Roll rather
than a Spellcast one, and it reaches the shared helper the way Grace's
Troublemaker does - by naming the trait. Valor still casts nothing.

The two level 4 cards are both firsts of a different kind. *Goad Them On* is the
first party content to hobble an **adversary's** attack roll, and *Support Tank*
is the first content anywhere that re-rolls a **single die** of a duality roll
rather than the whole thing.

Level 5 keeps the domain's shape: **Rousing Strike** rides a critical weapon
attack and lifts the whole party off it, and **Armorer** is filed *out of combat*
- its Armor Score bonus is already in the sheet, and what remains is a downtime
move that restores an Armor Slot on every ally.
"""

import random
from dataclasses import replace

from combat.results import AttackResult
from content.aoe import Range, chance_within, targets_in_area
from content.conditions import (
    TAUNTED,
    VULNERABLE,
    Condition,
    when_the_gm_pays,
    when_they_act,
)
from content.registry import (
    Fight,
    Holder,
    action,
    adversary_attack_disadvantage,
    adversary_target_override,
    ally_on_roll,
    condition_refusal,
    damage_bonus,
    extra_damage,
    guard,
    hope_die_for,
    no_combat_effect,
    on_hit,
    out_of_combat_ability,
    reroll,
    total_damage_bonus,
    total_roll_bonus,
)
from content.spellcast import spellcast
from dice.common import AdvantageState
from dice.damage import DiceGroup
from dice.duality import DualityOutcome

FORCEFUL_PUSH = "Forceful Push"

CRITICAL_INSPIRATION = "Critical Inspiration"

LEAN_ON_ME = "Lean on Me"

# Lean on Me clears exactly this much on each of the two PCs, and the
# clearing-in-full rule means it only fires when both have that much marked.
LEAN_ON_ME_STRESS = 2

# Marks the swing Forceful Push is making, so the card's own conditional die
# joins *that* damage roll and not an ordinary attack the same PC makes later.
# The `extra_damage` hook is holder-scoped and fires on every attack its holder
# rolls, which is right for a passive and wrong for one card's own follow-up.
PUSHING = "Forceful Push in flight"

FORCEFUL_PUSH_DIE = 6

BOLD_PRESENCE = "Bold Presence"


@damage_bonus(
    "Body Basher",
    unmodelled=[
        "The Melee-only restriction - weapon range bands aren't recorded "
        "anywhere, so this applies to any weapon the holder is carrying",
    ],
)
def body_basher(attacker: Holder, target, fight: Fight) -> int:
    """Body Basher (Valor, level 2).

    SRD: on a successful attack using a weapon with a Melee range, gain a bonus
    to your damage roll equal to your Strength.

    Applied before the target's thresholds are consulted, so it can change how
    many HP the hit marks rather than only the number printed - which is the
    whole reason it's a damage bonus hook rather than something bolted on after.

    The Melee restriction isn't enforced, and that's declared above. It happens
    to be correct for the only holder so far (a Greatsword is Melee), but it
    would quietly overstate a Body Basher on a bow.
    """
    return max(attacker.traits["strength"], 0)


@guard(
    "I Am Your Shield",
    unmodelled=[
        "Marking any number of Armor Slots against the redirected hit - "
        "take_damage marks at most one slot per hit",
        "'Within Very Close range' - no positioning is tracked, so every "
        "conscious PC is assumed able to reach the ally",
    ],
)
def i_am_your_shield(shielder: Holder, ally: Holder) -> bool:
    """I Am Your Shield (Valor, level 1). Returns whether `shielder` steps in.

    SRD: when an ally within Very Close range would take damage, you can mark a
    Stress to stand in the way and make yourself the target of the attack
    instead. When you take damage from this attack, you can mark any number of
    Armor Slots.

    SIMULATION RULE - rules interpretation. Applied by swapping the attack's
    target before it's rolled, so the attack resolves against the shielder's
    Evasion. That's what the effect clause says - "make yourself the target of
    the attack instead" - though the trigger clause ("when an ally would take
    damage") can be read as firing after a hit is known, in which case the
    ally's Evasion would decide it and the shielder would simply eat the damage.
    Worth revisiting; it changes how often stepping in is a good idea.

    The parts left out are declared on the decorator above rather than only
    here, so they reach the coverage report.
    """
    if not _worth_shielding(shielder, ally):
        return False
    return shielder.spend_stress(1)


def _worth_shielding(shielder: Holder, ally: Holder) -> bool:
    """Whether stepping in front of `ally` is the better trade.

    SIMULATION RULE - policy. The SRD makes this a player's choice. Step in only
    when the ally is closer to going down than the shielder is: the point of the
    card is moving a hit onto whoever can afford it, and a shielder who would
    drop from the hit themselves gains the party nothing by taking it.
    """
    if ally.hp_unmarked >= shielder.hp_unmarked:
        return False
    return shielder.hp_unmarked > 1


@action(
    FORCEFUL_PUSH,
    unmodelled=[
        "The knockback to Close range - no positions are tracked, so being "
        "shoved back changes nothing here",
        "'against a target within Melee range' - with no range modelled this is "
        "always available, which is generous for a PC who isn't in melee",
    ],
)
def forceful_push(attacker: Holder, target, fight: Fight) -> AttackResult | None:
    """Forceful Push (Valor, level 1).

    SRD: make an attack with your primary weapon against a target within Melee
    range. On a success, you deal damage and knock them back to Close range. On a
    success with Hope, add a d6 to your damage roll. Additionally, you can spend
    a Hope to make them temporarily Vulnerable.

    The attack goes through `attack_with`, the same shared shape an ordinary
    swing uses, so the weapon's own features, the party's reroll content and
    anything granting Advantage all reach it exactly as they would any other
    attack. What this card adds is the conditional d6 and the Vulnerable.

    The d6 is registered separately on `extra_damage` so it joins the weapon's
    own damage roll and is measured against the target's thresholds once -
    dealing it afterwards would be a second hit through the bands. See
    `forceful_push_momentum`.

    Never declines. It is a weapon attack with an upside attached, so there is no
    state in which making it is a wasted roll - which means it is simply one more
    option in the spotlight's shuffle alongside the plain swing.
    """
    from items.registry import find_weapon
    from items.weapons import attack_with

    carrying = getattr(attacker, "primary_weapon", "")
    if not carrying:
        return None

    # Set around the swing and cleared afterwards, so the extra die can tell this
    # attack from every other one this PC makes. In a `finally` because an
    # exception mid-attack would otherwise leave the token set for the fight.
    fight.set_token(attacker, PUSHING, 1)
    try:
        result = attack_with(
            attacker,
            find_weapon(carrying),
            target,
            AdvantageState.NONE,
            total_roll_bonus(attacker, target, fight),
            total_damage_bonus(attacker, target, fight),
            hope_die_for(attacker, fight),
            fight,
        )
    finally:
        fight.set_token(attacker, PUSHING, 0)

    if result.damage_roll is None:
        return result

    fight.note(f"{attacker.name} shoves {target.name} back")
    _press_them(attacker, target, fight)
    return result


@extra_damage(FORCEFUL_PUSH)
def forceful_push_momentum(
    attacker: Holder, target, roll, fight: Fight = None
) -> list[DiceGroup]:
    """Forceful Push's extra d6 on a success with Hope.

    Only offered to the swing the card itself is making - `PUSHING` says which
    one that is. Without it this would add a d6 to every attack the holder ever
    made with Hope, which is a much bigger card than the one printed.

    A critical is deliberately **not** treated as "with Hope". It is its own
    outcome with the two dice matched, which is the reading School of War's Face
    Your Fear already applies to "with Fear" - and a crit is already paying out
    the maximum of every damage die.

    `discardable=False`, like Face Your Fear's die: a Massive or Powerful weapon
    discards the lowest of the dice *it* rolled, and this is not one of them.
    """
    if fight is None or not fight.token_count(attacker, PUSHING):
        return []
    if roll is None or not roll.is_success:
        return []
    if getattr(roll, "outcome", None) is not DualityOutcome.HOPE:
        return []
    return [DiceGroup(count=1, sides=FORCEFUL_PUSH_DIE, discardable=False)]


def _press_them(attacker: Holder, target, fight: Fight) -> None:
    """Spend a Hope to leave the target Vulnerable, if that buys anything.

    SIMULATION RULE - policy, ruled. The Hope is spent on **every successful
    hit** while there is one to spend. Unlike Vicious Entangle's second Restrain,
    which converts a Hope into a Fear off the GM's pool and buys nothing at 0
    Fear, Vulnerable is modelled outright - every roll against the target has
    Advantage until the GM pays to clear it - so the Hope always buys a real
    effect whatever the pool looks like.

    Two states where it would buy nothing are skipped, and neither is a threshold
    of the kind that needs its own ruling: a target already Vulnerable gains
    nothing from being made Vulnerable again, and a target the hit just defeated
    is off the field. Both are facts the party can see rather than statistics
    anyone has to work out.

    "Temporarily" is the party putting a condition on an adversary, which ends
    when the GM spends a Fear on it - `when_the_gm_pays`, the standing reading in
    SIMULATION-RULES.md.
    """
    if target.is_defeated or fight.is_vulnerable(target):
        return
    if not attacker.can_spend_hope(1):
        return

    attacker.spend_hope(1)
    fight.apply_condition(
        target, Condition(name=VULNERABLE, end=when_the_gm_pays, source=attacker)
    )
    fight.note(f"{attacker.name} spends a Hope to leave {target.name} Vulnerable")


@condition_refusal(
    BOLD_PRESENCE,
    unmodelled=[
        "Spending a Hope to add Strength to a Presence Roll - ruled an "
        "insignificant effect. The only Presence Rolls this simulator makes are "
        "the Reaction Rolls an adversary forces, of which one source exists in "
        "the whole ported catalogue (the Patchwork Zombie Hulk's Tormented "
        "Screams), and the clause is taken as a roleplay option for a Strength "
        "character rather than something a fight turns on",
        "A PC going Vulnerable by the rules, on marking their last Stress - that "
        "is a standing state rather than a condition anything applies, so it "
        "never passes through the moment this hook is asked at, and the dodge "
        "cannot stop it",
        "Holding the dodge back for a worse condition later - it is spent on the "
        "first one that would land",
    ],
)
def bold_presence(holder: Holder, condition, fight: Fight) -> bool:
    """Bold Presence (Valor, level 2), second clause. Returns whether it fires.

    SRD: "Once per rest when you would gain a condition, you can describe how
    your bold presence aids you in the situation and avoid gaining the
    condition."

    Once per *short* rest, so `long=False` - a short rest gives it back.

    Fires on the first condition that would land, which is the standing default
    for content with no policy of its own: it costs nothing to use and there is
    no way for a PC to know a worse condition is coming. Being asked is already
    the commitment - the hook is only consulted when a condition really would
    land, and never on a refresh of one already held - so claiming the per-rest
    use here is safe.

    Refusing is total: the condition is never recorded, so nothing downstream
    ever sees it. That is what makes this a `condition_refusal` rather than an
    `immunity`, which suppresses a condition that is still sitting there.
    """
    if fight is None:
        return False
    return fight.use_once_per_rest(holder, BOLD_PRESENCE)


# --- Critical Inspiration ----------------------------------------------------


@on_hit(
    CRITICAL_INSPIRATION,
    unmodelled=[
        "'all allies within Very Close range' - no positions are tracked, so "
        "the area rule in SIMULATION-RULES.md decides how many are reached. "
        "Worth knowing what that comes to over a *party* rather than a field of "
        "adversaries: Very Close reaches `n // 3` held to two, so in a four-PC "
        "party one ally hears it",
        "A critical on an action roll that isn't an attack - the on-hit hook "
        "only sees an attack that landed, so a critical Troublemaker or "
        "Shadowbind doesn't inspire anybody",
    ],
)
def critical_inspiration(attacker: Holder, target, result, fight: Fight) -> None:
    """Critical Inspiration (Valor, level 3).

    SRD: "Once per rest, when you critically succeed on an attack, all allies
    within Very Close range can clear a Stress or gain a Hope."

    SIMULATION RULE - policy, ruled. Each ally **clears a Stress if any is
    marked, and otherwise gains a Hope**. That is the ruling Strange Patterns
    already got for the same choice, and for the same reason: Stress is the
    scarcer resource here, since running out of it hands every adversary
    Advantage for the rest of the fight, while a Hope handed to somebody with
    nothing to clear is never wasted.

    Nothing here weighs the two - each ally answers for themselves off what they
    are carrying, which is a fact visible at the table rather than a comparison
    anybody works out.

    The per-rest use is **checked before the reach is rolled and claimed after**,
    so a critical that reaches nobody costs nothing. It is also not claimed when
    every ally reached would gain nothing at all - no Stress marked and Hope
    already at its cap - since spending the one use of the fight on that would be
    spending it on nothing.
    """
    if fight is None or result.attack_roll is None:
        return
    if not getattr(result.attack_roll, "is_critical", False):
        return
    if not fight.can_use_once_per_rest(attacker, CRITICAL_INSPIRATION):
        return

    allies = [pc for pc in fight.conscious_party if pc is not attacker]
    reached = [ally for ally in targets_in_area(Range.VERY_CLOSE, allies) if _liftable(ally)]
    if not reached:
        return

    fight.use_once_per_rest(attacker, CRITICAL_INSPIRATION)
    for ally in reached:
        if ally.stress_marked:
            ally.clear_stress(1)
            fight.note(f"{attacker.name}'s critical clears a Stress on {ally.name}")
        else:
            ally.gain_hope(1)
            fight.note(f"{attacker.name}'s critical hands {ally.name} a Hope")


def _liftable(ally: Holder) -> bool:
    """Whether this ally would actually gain something from being inspired.

    A PC with no Stress marked and their Hope already at the cap gains nothing
    from either half of the choice. Reads only what is on their own sheet.
    """
    return bool(ally.stress_marked) or ally.hope_marked < ally.hope_max


# --- Lean on Me --------------------------------------------------------------


@ally_on_roll(
    LEAN_ON_ME,
    unmodelled=[
        "The consoling itself - 'when you console or inspire an ally' is "
        "fiction, and taken as always available. Nothing in the simulator "
        "represents a PC choosing to speak to somebody",
    ],
)
def lean_on_me(holder: Holder, roller: Holder, roll, fight: Fight) -> None:
    """Lean on Me (Valor, level 3).

    SRD: "Once per long rest, when you console or inspire an ally who failed an
    action roll, you can both clear 2 Stress."

    An **ally's** roll, never the holder's own - which is why this is registered
    on the party-wide hook and checks `holder is not roller`. Registered
    holder-scoped it would have fired only on the consoler's own failures, which
    is precisely the roll the card is not about.

    SIMULATION RULE - policy. The standing clearing-in-full rule applies: a
    feature whose effect is clearing named quantities is used only when it can
    clear **every one of them**. So both PCs need 2 Stress marked, and a card
    with one use per long rest is never spent to clear one Stress off a pair who
    have barely any.

    `is_success is not False` rather than `not is_success`, because a roll made
    with no Difficulty answers None - that is not a failure, and Reassurance
    reads its trigger the same way.
    """
    if fight is None or holder is roller:
        return
    if roll is None or roll.is_success is not False:
        return
    if holder.stress_marked < LEAN_ON_ME_STRESS:
        return
    if roller.stress_marked < LEAN_ON_ME_STRESS:
        return
    if not fight.use_once_per_rest(holder, LEAN_ON_ME, long=True):
        return

    holder.clear_stress(LEAN_ON_ME_STRESS)
    roller.clear_stress(LEAN_ON_ME_STRESS)
    fight.note(
        f"{holder.name} steadies {roller.name}; both clear {LEAN_ON_ME_STRESS} Stress"
    )


# --- Goad Them On ------------------------------------------------------------

GOAD_THEM_ON = "Goad Them On"

# A Presence Roll, not a Spellcast Roll - the second card in the project to roll
# a named trait through the shared helper, after Grace's Troublemaker.
GOAD_TRAIT = "presence"


@action(
    GOAD_THEM_ON,
    unmodelled=[
        "'a target within Close range' - no positions are tracked, so the goad "
        "always reaches whoever the party is focusing",
    ],
)
def goad_them_on(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Goad Them On (Valor, level 4). Make it come for you, badly.

    SRD: "Describe how you taunt a target within Close range, then make a
    Presence Roll against them. On a success, the target must mark a Stress, and
    the next time the GM spotlights them, they must target you with an attack,
    which they make with disadvantage."

    Three effects on one roll, and all three are modelled. The Stress is the half
    that lands immediately - an adversary's Stress is what pays for its Action
    features and what its desperation rule reads. The compulsion is *Taunted*,
    which the simulator already has from the other side of the table: the
    Weaponmaster's Goading Strike puts it on a PC, and this is the same condition
    put on an adversary. The Disadvantage is the third, and it needed the one new
    hook this card cost.

    **The duration is exactly one activation.** "The next time the GM spotlights
    them" is `WHEN_THEY_ACT`, which the loop announces *after* an adversary has
    acted - so the goad holds through their next spotlight and lifts behind it.
    That is the plainest reading of the printed text and needed no ruling, which
    is unusual for a condition here: most arrive with a name and nothing else.

    A **Presence Roll**, so it goes through the shared helper with the trait
    named, exactly as Grace's Troublemaker does. Rolled against the target's own
    Difficulty, which is the standing rule wherever the SRD prints a roll against
    a creature and no number to beat.

    Never declines except against a target already goaded, per the standing rule
    that a feature whose point is a condition is not used on somebody who has it.
    It costs nothing but the roll the caster was making anyway.

    **Worth reading the numbers of carefully.** Like Grace's Enrapture, this is a
    card whose point is *being attacked*: it takes an attack off whoever the GM
    would have chosen and puts it on the taunter. Unlike Enrapture it hands back
    a Disadvantage on that attack, and unlike Enrapture it ends on its own rather
    than costing the GM a Fear.
    """
    if fight is None or fight.has_condition(target, TAUNTED):
        return None

    attack_roll = spellcast(caster, target, fight, trait=GOAD_TRAIT)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    # Forced rather than spent, so an adversary with a full Stress track simply
    # loses nothing - the SRD's overflow-into-HP rule is a PC rule.
    target.mark_stress(1)
    fight.apply_condition(
        target, Condition(name=TAUNTED, end=when_they_act, source=caster)
    )
    fight.note(f"{caster.name} goads {target.name}, who marks a Stress")
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


@adversary_target_override(GOAD_THEM_ON)
def goad_them_on_compels(holder: Holder, adversary, fight: Fight):
    """A goaded adversary swings at whoever goaded it.

    Read off the condition's **source** rather than off its presence, so a
    Weaponmaster that also carries a Taunt cannot pick this up, and so two Valor
    PCs each goading something send it at the right one.

    The exact mirror of the Weaponmaster's `goading_strike_compels`, which is the
    same condition read by the party's targeting rule instead of the GM's.
    """
    if fight is None:
        return None
    goad = fight.condition_on(adversary, TAUNTED)
    if goad is None or goad.source is not holder:
        return None
    return holder


@adversary_attack_disadvantage(GOAD_THEM_ON)
def goad_them_on_hobbles(holder: Holder, attacker, target, fight: Fight) -> bool:
    """The goaded attack is made at Disadvantage.

    Scoped to the attack the goad actually compelled - this adversary, swinging
    at this holder - rather than to every swing a goaded adversary makes. The card
    attaches the Disadvantage to the compulsion ("they must target you with an
    attack, **which** they make with disadvantage"), so an attack that ended up
    aimed elsewhere is not the one being described.

    Folded into the roll with `combined`, so a goaded adversary swinging at a
    Vulnerable taunter comes out even rather than hobbled outright.
    """
    if fight is None or target is not holder:
        return False
    goad = fight.condition_on(attacker, TAUNTED)
    return goad is not None and goad.source is holder


# --- Support Tank ------------------------------------------------------------

SUPPORT_TANK = "Support Tank"

SUPPORT_TANK_HOPE = 2

# The same floor Luckbender uses, and for the same shape of card: a Hope-priced
# reroll of an ally's failed roll with no per-rest limit. Duplicated rather than
# shared, because one card must never import another's module.
SUPPORT_TANK_HOPE_FLOOR = 6


@reroll(
    SUPPORT_TANK,
    unmodelled=[
        "'an ally within Close range' is answered by the area rule rather than "
        "by position, rolled per offer - so a Valor PC in a big party reaches "
        "their ally most of the time and not always",
        "**Which** die the ally would rather rethrow. The card lets them choose "
        "between the Hope and the Fear Die; this always throws the one showing "
        "the lower result, which is the die with the most room to improve. Where "
        "the two dice are different sizes - a Hope Die swapped to a d20 - the "
        "lower *result* is not necessarily the better rethrow, and no comparison "
        "of the two is made",
    ],
)
def support_tank(holder: Holder, roller: Holder, roll, remake, fight: Fight = None):
    """Support Tank (Valor, level 4). Two Hope rethrows **one** of an ally's dice.

    SRD: "When an ally within Close range fails a roll, you can spend 2 Hope to
    allow them to reroll either their Hope or Fear Die."

    **The first content anywhere that re-rolls a single die of a duality roll.**
    Every other registrant on this hook re-makes the whole thing - Luckbender and
    Adaptability both say "reroll your Duality Dice", and the simulator's reading
    of that is recorded in SIMULATION-RULES.md. This card is explicit that it is
    one die, so `remake` is deliberately unused and the replacement is built by
    changing one field of the resolved roll. That is what put the die *sizes* on
    `DualityRollResult`: the Hope Die is not always a d12.

    The consequence worth knowing is that it re-rolls **less** than the others
    and can therefore do more: the untouched die keeps its value, so a roll
    already carrying a good Fear die keeps it, and a rethrow that comes up equal
    to the other die is a **critical**.

    SIMULATION RULE - policy, ruled. Fires on an ally's **failed** roll, at
    `SUPPORT_TANK_HOPE_FLOOR` Hope or above - Luckbender's floor, for the same
    shape of card, so one number is read in two places rather than two that could
    drift. Rerolling a success buys nothing measurable, and without a floor a
    Valor PC would empty their Hope into other people's rolls.

    SIMULATION RULE - policy. The die thrown again is the one **showing the lower
    result**, which is what anybody at a table does and is arithmetic on two
    numbers already face-up - not a comparison of anything nobody computes. A
    failed roll can never be a tie, since equal dice are a critical and a critical
    always succeeds.
    """
    if fight is None or holder is roller:
        return None
    if roll is None or roll.is_success is not False:
        return None
    if holder.hope_marked < SUPPORT_TANK_HOPE_FLOOR:
        return None
    if not holder.can_spend_hope(SUPPORT_TANK_HOPE):
        return None

    allies = [pc for pc in fight.conscious_party if pc is not holder]
    if not allies or random.random() >= chance_within(Range.CLOSE, len(allies)):
        return None

    holder.spend_hope(SUPPORT_TANK_HOPE)

    if roll.hope_die_result <= roll.fear_die_result:
        thrown, which = (
            replace(roll, hope_die_result=random.randint(1, roll.hope_die_sides)),
            "Hope",
        )
    else:
        thrown, which = (
            replace(roll, fear_die_result=random.randint(1, roll.fear_die_sides)),
            "Fear",
        )

    fight.note(
        f"{holder.name} spends {SUPPORT_TANK_HOPE} Hope; {roller.name} rethrows "
        f"their {which} Die ({thrown})"
    )
    return thrown


# --- Rousing Strike ------------------------------------------------------------

ROUSING_STRIKE = "Rousing Strike"

# "Clear a Hit Point or 1d4 Stress" - the Stress option's die.
ROUSING_STRIKE_DIE = 4


@on_hit(
    ROUSING_STRIKE,
    unmodelled=[
        "'all allies who can see or hear you' - no positions are tracked, so "
        "every conscious PC is reached. Unlike Critical Inspiration, which prints "
        "a Very Close band, this card names a sense rather than a range, and "
        "nothing here represents line of sight either way",
        "A critical that deals **no damage** never reaches this hook, the same "
        "gap Champion's Edge declares - `on_hit` is asked where a landed attack "
        "has rolled damage",
    ],
)
def rousing_strike(attacker: Holder, target, result, fight: Fight) -> None:
    """Rousing Strike (Valor, level 5). A critical lifts the whole party.

    SRD: "Once per rest, when you critically succeed on an attack, you and all
    allies who can see or hear you can clear a Hit Point or 1d4 Stress."

    SIMULATION RULE - policy. **Each PC takes the Hit Point if they have one
    marked, and otherwise rolls the 1d4 Stress.** That is the Healing Hands
    ruling - HP is taken over Stress because a downed PC is what ends a fight -
    and each ally answers off their own sheet, exactly as Critical Inspiration's
    allies do. The 1d4 is rolled per PC rather than once and shared, since the
    card gives each of them the choice.

    The per-rest use is **not** spent when nobody would gain from it: a party at
    full HP and no Stress marked keeps the card for later, which is the same
    guard Critical Inspiration and Second Wind carry.
    """
    if fight is None or result.attack_roll is None:
        return
    if not result.attack_roll.is_critical:
        return

    lifted = [
        pc
        for pc in fight.conscious_party
        if pc.hp_marked > 0 or pc.stress_marked > 0
    ]
    if not lifted:
        return
    if not fight.use_once_per_rest(attacker, ROUSING_STRIKE):
        return

    for pc in lifted:
        if pc.hp_marked > 0:
            pc.clear_hp(1)
            fight.note(f"{pc.name} is roused, clearing a Hit Point")
        else:
            cleared = random.randint(1, ROUSING_STRIKE_DIE)
            pc.clear_stress(cleared)
            fight.note(f"{pc.name} is roused, clearing {cleared} Stress")


out_of_combat_ability(
    "Armorer",
    "Two clauses in two states, and the card can only be in one. The +1 Armor "
    "Score is a value a character sheet carries **already resolved**, exactly as "
    "it carries Evasion and thresholds, so running it here would count the bonus "
    "twice - the same reason Bare Bones and Bone's Untouchable are declared. What "
    "is left is real and fully representable: during a rest, repairing your own "
    "armor as a downtime move clears an Armor Slot on **every ally** too. That is "
    "a party-wide restore of the resource this simulator spends on almost every "
    "incoming hit, and it happens between fights rather than during one - so it "
    "belongs to the sequenced-encounter machinery with A Soldier's Bond, Mending "
    "Touch, Inspirational Words and Soothing Speech, and is filed here rather than "
    "dismissed. The user ruled it into this state for exactly that reason.",
)

no_combat_effect(
    "Bare Bones",
    "Sets Armor Score and thresholds when wearing no armor. A sheet already "
    "carries its resolved thresholds and armor slots, so this changes nothing "
    "at simulation time.",
)
