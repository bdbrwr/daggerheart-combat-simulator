"""Valor domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json.

Cards from this domain that can't affect a fight are declared at the bottom, so
"assessed and dismissed" never looks like "nobody has got to it yet".
"""

from combat.results import AttackResult
from content.conditions import VULNERABLE, Condition, when_the_gm_pays
from content.registry import (
    Fight,
    Holder,
    action,
    condition_refusal,
    damage_bonus,
    extra_damage,
    guard,
    hope_die_for,
    no_combat_effect,
    total_damage_bonus,
    total_roll_bonus,
)
from dice.common import AdvantageState
from dice.damage import DiceGroup
from dice.duality import DualityOutcome

FORCEFUL_PUSH = "Forceful Push"

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


no_combat_effect(
    "Bare Bones",
    "Sets Armor Score and thresholds when wearing no armor. A sheet already "
    "carries its resolved thresholds and armor slots, so this changes nothing "
    "at simulation time.",
)
