"""Midnight domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json, checked against the printed page
(SRD p. 128).

The last domain ported, and the one that leans hardest on rules settled earlier:
Rain of Blades takes the area shape Fire Flies established, Midnight Spirit
counts its dice off the Spellcast trait the way the Beastbound companion does,
and Shadowbind's whole effect turns out to be the Fear the GM must spend to undo
it.
"""

from combat.results import AttackResult
from content.aoe import Range, area_difficulty, targets_beaten, targets_in_area
from content.conditions import RESTRAINED, Condition, when_the_gm_pays
from content.damage_types import DamageType
from content.registry import (
    Fight,
    Holder,
    action,
    hope_die_for,
    no_combat_effect,
    remake_action_roll,
    total_extra_damage,
    total_roll_bonus,
)
from dice.damage import DiceGroup, roll_damage
from dice.duality import roll_duality

# --- Rain of Blades ----------------------------------------------------------

RAIN_OF_BLADES = "Rain of Blades"

RAIN_OF_BLADES_DIE = 8
RAIN_OF_BLADES_MODIFIER = 2

# The extra die a Vulnerable target takes, rolled per target rather than once.
VULNERABLE_DIE = 8

# A Hope for one roll wants to be catching several. Below this it is a worse
# weapon swing that also costs a Hope - the same line Fire Flies draws.
RAIN_OF_BLADES_WORTH_IT = 2


@action(
    RAIN_OF_BLADES,
    unmodelled=[
        "'all targets within Very Close range' - no positions are tracked, so "
        "the area rule in SIMULATION-RULES.md decides how many are caught",
    ],
)
def rain_of_blades(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Rain of Blades (Midnight, level 1).

    SRD: spend a Hope to make a Spellcast Roll and conjure throwing blades that
    strike out at all targets within Very Close range. Targets you succeed
    against take d8+2 magic damage using your Proficiency. If a target you hit is
    Vulnerable, they take an extra 1d8 damage.

    The Fire Flies shape: one roll made against the whole area at once, each
    adversary then checked against its own Difficulty, and the damage dealt to
    every one the roll beat.

    SIMULATION RULE - policy, ruled. Declines unless it would reach two or more
    adversaries, exactly as Fire Flies does and for the same reason - a Hope
    spent to hit one target is a worse weapon swing. Very Close reaches `n // 3`
    held to two, so on a small field this card often waits.

    **The Vulnerable rider is rolled per target**, not once for the sweep. It has
    to be: the card asks about each target's own condition, and a shared roll
    would either hand the extra die to adversaries who don't qualify or deny it
    to ones who do. Each target's total still meets its thresholds exactly once.
    """
    if not caster.can_spend_hope(1):
        return None

    area = targets_in_area(Range.VERY_CLOSE, fight.living_adversaries)
    if len(area) < RAIN_OF_BLADES_WORTH_IT:
        return None

    attack_roll = _spellcast(caster, target, fight, difficulty=area_difficulty(area))
    if attack_roll is None:
        return None

    caster.spend_hope(1)

    caught = targets_beaten(attack_roll, area)
    if not caught:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=caster.proficiency, sides=RAIN_OF_BLADES_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=RAIN_OF_BLADES_MODIFIER,
        is_critical=attack_roll.is_critical,
    )

    marked = 0
    for adversary in caught:
        dealt = damage_roll.total
        if fight.is_vulnerable(adversary):
            extra = roll_damage(dice_groups=[DiceGroup(count=1, sides=VULNERABLE_DIE)])
            dealt += extra.total
        marked += adversary.take_damage(dealt, fight, damage_type=DamageType.MAGIC)

    fight.note(
        f"{caster.name} looses a rain of blades, catching {len(caught)} "
        f"for {damage_roll.total} each"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


# --- Midnight Spirit ---------------------------------------------------------

MIDNIGHT_SPIRIT = "Midnight Spirit"

SPIRIT_DIE = 6


@action(
    MIDNIGHT_SPIRIT,
    unmodelled=[
        "The spirit's other half - moving and carrying things until your next "
        "rest. Only the attack is a fight",
        "'You can only have one spirit at a time' - the spirit dissipates the "
        "moment it attacks, which is the only thing it does here, so the limit "
        "never binds",
        "'within Very Far range' - no positions are tracked",
    ],
)
def midnight_spirit(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Midnight Spirit (Midnight, level 2).

    SRD: spend a Hope to summon a humanoid-sized spirit. You can send it to
    attack an adversary: make a Spellcast Roll against a target within Very Far
    range, and on a success the spirit moves into Melee with them, deals a number
    of d6s equal to your Spellcast trait in magic damage, then dissipates.

    Summoning and attacking are one action here, because the spirit does nothing
    else the simulator can see and the attack consumes it either way. The Hope is
    spent on the summoning, so it goes whether or not the roll lands - which is
    what the card says, and what makes this a real cost rather than a rider.

    Dice counted off the **Spellcast trait**, so this scales with the stat the
    caster already leans on rather than with Proficiency. A trait of zero or less
    rolls nothing, per the SRD's rule for trait-counted dice, and the card
    declines rather than spending a Hope on no dice at all.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None

    dice = caster.traits[trait]
    if dice <= 0:
        return None
    if not caster.can_spend_hope(1):
        return None

    attack_roll = _spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    caster.spend_hope(1)

    if not attack_roll.is_success:
        fight.note(f"{caster.name}'s spirit misses {target.name} and dissipates")
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=dice, sides=SPIRIT_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        is_critical=attack_roll.is_critical,
    )
    marked = target.take_damage(damage_roll.total, fight, damage_type=DamageType.MAGIC)
    fight.note(
        f"{caster.name}'s spirit strikes {target.name} for {damage_roll.total}"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


# --- Shadowbind --------------------------------------------------------------

SHADOWBIND = "Shadowbind"


@action(
    SHADOWBIND,
    unmodelled=[
        "'all adversaries within Very Close range' - no positions are tracked, "
        "so the area rule decides how many are caught",
        "Being Restrained itself, which is ruled to have no effect of its own "
        "here because no movement is modelled. So the whole value of this card "
        "is the Fear the GM must spend to clear it - one per adversary bound",
    ],
)
def shadowbind(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Shadowbind (Midnight, level 2).

    SRD: make a Spellcast Roll against all adversaries within Very Close range.
    Targets you succeed against are temporarily Restrained as their shadow binds
    them in place.

    **Worth being plain about what this comes to.** Restrained stops a combatant
    moving and no movement is modelled, so the condition does nothing by itself -
    that is a ruling made long before this card. What a condition the party puts
    on an adversary *does* cost is a Fear, spent on the GM's turn to shake it
    off. So Shadowbind is a Fear-burner: bind three adversaries and the GM pays
    three Fear, or leaves them bound and pays nothing because being bound costs
    them nothing. That is a real effect on the pool the GM buys activations with,
    and it is not the control spell the page describes.

    Costs nothing but the roll, so it never declines except when there is nobody
    left to bind - every adversary in reach already being Restrained is the one
    state where casting buys nothing at all.
    """
    area = [
        adversary
        for adversary in targets_in_area(Range.VERY_CLOSE, fight.living_adversaries)
        if not fight.has_condition(adversary, RESTRAINED)
    ]
    if not area:
        return None

    attack_roll = _spellcast(caster, target, fight, difficulty=area_difficulty(area))
    if attack_roll is None:
        return None

    bound = targets_beaten(attack_roll, area)
    for adversary in bound:
        fight.apply_condition(
            adversary,
            Condition(name=RESTRAINED, end=when_the_gm_pays, source=caster),
        )
    if bound:
        fight.note(
            f"{caster.name} binds {len(bound)} adversaries with their own shadows"
        )
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


# --- Shared ------------------------------------------------------------------


def _spellcast(caster: Holder, target, fight: Fight, difficulty: int | None = None):
    """A Spellcast Roll against a target's Difficulty, or None if we can't make one.

    Rolled against `target`'s Difficulty unless one is given - an area spell
    passes `area_difficulty` instead.

    The sixth copy of this helper across `domain_cards/`, and by now plainly one
    too many: they have drifted (some take a `bonus`, some a `difficulty`, Grace's
    takes a trait). Pulling them into one shared place is a small change and
    would be its own, since it touches six modules.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None

    modifier = caster.traits[trait] + total_roll_bonus(caster, target, fight)
    against = target.difficulty if difficulty is None else difficulty
    hope_die = hope_die_for(caster, fight)

    def roll():
        return roll_duality(modifier=modifier, difficulty=against, hope_die=hope_die)

    return remake_action_roll(caster, roll(), roll, fight)


# --- Assessed and dismissed --------------------------------------------------

no_combat_effect(
    "Pick and Pull",
    "Advantage on action rolls to pick nonmagical locks, disarm nonmagical "
    "traps, or steal items from a target. Locks, traps and inventories are all "
    "outside a simulated fight, so there is no roll here for the advantage to "
    "land on.",
)
no_combat_effect(
    "Uncanny Disguise",
    "A Stress and a few minutes' preparation to wear another humanoid's face, "
    "with advantage on Presence Rolls to avoid scrutiny while the tokens last. "
    "Both halves are outside a fight: the preparation cannot happen during one, "
    "and being disguised would change nothing once blades are out - adversaries "
    "in an encounter are already hostile and already swinging. Distinct from "
    "Mending Touch, which is deferred rather than dismissed because its effect "
    "*would* matter if it could be used.",
)
