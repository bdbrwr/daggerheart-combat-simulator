"""Splendor domain cards.

Card text is paraphrased in each docstring rather than quoted in full. The
verbatim text is in .reference/abilities.json, checked against the printed page
(SRD p. 132).
"""

from combat.results import AttackResult
from content.conditions import VULNERABLE, Condition, when_the_gm_pays
from content.damage_types import DamageType
from content.registry import (
    Fight,
    Holder,
    action,
    hope_die_for,
    no_combat_effect,
    out_of_combat_ability,
    remake_action_roll,
    reroll,
    total_extra_damage,
    total_roll_bonus,
)
from dice.damage import DiceGroup, roll_damage
from dice.duality import roll_duality

HEALING_HANDS_DIFFICULTY = 13

BOLT_BEACON_DIE = 8
BOLT_BEACON_MODIFIER = 2

REASSURANCE = "Reassurance"

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

    roll = roll_duality(
        modifier=caster.traits[trait],
        difficulty=HEALING_HANDS_DIFFICULTY,
        hope_die=hope_die_for(caster, fight),
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


def _spellcast(caster: Holder, target, fight: Fight):
    """A Spellcast Roll against a target's Difficulty, or None if we can't make one.

    The third copy of this helper - `domain_cards/codex.py` and
    `domain_cards/sage.py` each have one, and they have already drifted apart
    once. Worth pulling into one shared place; kept per-module for now because
    that is the convention the other two set.

    A sheet that names no `spellcast_trait` declines rather than guessing, so
    unusable content shows up as content that never fires rather than as content
    that quietly fires with the wrong number.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None

    # Worked out outside the closure: asking content for a roll bonus is the
    # commitment, so a reroll re-makes the dice and not the decisions behind them.
    modifier = caster.traits[trait] + total_roll_bonus(caster, target, fight)
    hope_die = hope_die_for(caster, fight)

    def roll():
        return roll_duality(
            modifier=modifier, difficulty=target.difficulty, hope_die=hope_die
        )

    return remake_action_roll(caster, roll(), roll, fight)


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

    attack_roll = _spellcast(caster, target, fight)
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


out_of_combat_ability(
    "Mending Touch",
    "Spend 2 Hope to clear a Hit Point or a Stress on somebody, and once per "
    "long rest 2 of either. Real healing, fully representable - but the card "
    "gates it on taking 'a few minutes to focus on the target', which is not "
    "something that happens while a fight is on. It belongs to the party's time "
    "between encounters, and runs when sequenced encounters do.",
)

no_combat_effect(
    "Final Words",
    "Infuses a corpse with a moment of life to answer questions. It produces "
    "information about the past, and nothing about a fight's outcome turns on "
    "what a body has to say.",
)
