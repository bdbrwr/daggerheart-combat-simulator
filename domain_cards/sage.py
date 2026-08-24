"""Sage domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json.
"""

import random

from combat.results import AttackResult
from content.aoe import (
    Range,
    area_difficulty,
    chance_within,
    targets_beaten,
    targets_in_area,
)
from content.damage_types import DamageType
from content.grimoire import Grimoire
from content.registry import (
    Fight,
    Holder,
    action,
    extra_damage,
    free,
    hope_die_for,
    no_combat_effect,
    remake_action_roll,
    severity_response,
    total_extra_damage,
    total_roll_bonus,
)
from dice.damage import DiceGroup, roll_damage
from dice.duality import roll_duality


def _spellcast(caster: Holder, target, fight: Fight, difficulty: int | None = None):
    """A Spellcast Roll, or None if this caster can't make one.

    Rolled against `target`'s Difficulty unless one is given - an area spell is
    rolled against the whole area at once and passes `area_difficulty` instead.

    A sheet that names no `spellcast_trait` declines to cast rather than
    guessing a trait, so unusable content shows up as content that never fires
    rather than as content that quietly fires with the wrong number.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None

    # Both worked out outside the closure: asking for a roll bonus or a Hope Die
    # is the commitment, and a reroll re-makes the dice rather than the decisions
    # that fed them.
    modifier = caster.traits[trait] + total_roll_bonus(caster, target, fight)
    against = target.difficulty if difficulty is None else difficulty
    hope_die = hope_die_for(caster, fight)

    def roll():
        return roll_duality(modifier=modifier, difficulty=against, hope_die=hope_die)

    # Offered to the reroll hook, so content that can re-make a resolved roll
    # reaches a spell as readily as it reaches a weapon swing.
    return remake_action_roll(caster, roll(), roll, fight)


# --- Vicious Entangle --------------------------------------------------------


@action(
    "Vicious Entangle",
    unmodelled=[
        "the Restrained condition itself - conditions aren't tracked, so per "
        "SIMULATION-RULES.md this drains a Fear from the GM instead",
        "'within Far range' and 'within Very Close range of your target' - no "
        "positions are tracked, so the second target is any other adversary",
    ],
)
def vicious_entangle(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Vicious Entangle (Sage, level 1).

    SRD: Spellcast Roll against a target within Far range. On a success, roots
    and vines deal 1d8+1 physical damage and temporarily Restrain the target.
    Additionally on a success, spend a Hope to temporarily Restrain another
    adversary within Very Close range of your target.

    The damage is a flat 1d8+1 - the card doesn't say "using your Proficiency",
    so it doesn't scale with it, which is what makes this a level 1 card that
    stops being the Ranger's best roll fairly quickly.

    Restraining isn't modelled, so both Restrains cost the GM a Fear apiece
    under the temporary-condition rule. That makes the Hope worth spending for
    the second one: it converts a Hope into a Fear off the GM's pool, which is
    the closest the simulator can get to what the card actually buys.

    Never declines. Unlike Slumber, this deals damage whatever the GM's pool
    looks like, so there's no state in which casting it is a wasted spotlight.
    """
    attack_roll = _spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=1, sides=8)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=1,
        is_critical=attack_roll.is_critical,
    )
    marked = target.take_damage(damage_roll.total, damage_type=DamageType.PHYSICAL)
    fight.spend_fear(1)
    fight.note(
        f"{caster.name} entangles {target.name} for {damage_roll.total} "
        "(Restrained: the GM loses a Fear)"
    )

    _entangle_a_second(caster, target, fight)
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


def _entangle_a_second(caster: Holder, target, fight: Fight) -> None:
    """Spend a Hope to Restrain another adversary, if that buys anything.

    SIMULATION RULE - policy. The Hope is only spent when there's somebody else
    to Restrain *and* the GM has a Fear for it to take. At 0 Fear the condition
    is free to the GM (see SIMULATION-RULES.md), so the Hope would buy nothing
    at all - and Hope has other uses.
    """
    others = [adversary for adversary in fight.living_adversaries if adversary is not target]
    if not others or fight.fear < 1:
        return
    if not caster.can_spend_hope(1):
        return

    caster.spend_hope(1)
    fight.spend_fear(1)
    fight.note(
        f"{caster.name} spends a Hope to entangle {others[0].name} too "
        "(the GM loses another Fear)"
    )


# --- Conjure Swarm -----------------------------------------------------------
#
# One card, two swarms that fire at different points: the beetles need no roll
# and then sit waiting for damage to arrive, while the fire flies are an attack.
# That's the Grimoire shape, so it uses the Grimoire - with the beetles' actual
# effect registered as a damage response under the card's name, since a swarm
# that softens a hit isn't something the free-ability hook can express.

SWARM = Grimoire("Conjure Swarm")

BEETLES = "Tekaira Armored Beetles"

# The beetles are kept up after they've absorbed a hit only while Hope is
# plentiful; below this the Hope is worth more elsewhere.
BEETLES_HOPE_FLOOR = 3

# Fire Flies is a Hope for one attack, so it wants to be catching several
# adversaries. Below this it's a worse weapon swing that also costs a Hope.
FIRE_FLIES_WORTH_IT = 2

FIRE_FLIES_DICE = 2
FIRE_FLIES_DIE = 8
FIRE_FLIES_MODIFIER = 3


@SWARM.free(BEETLES)
def tekaira_armored_beetles(caster: Holder, fight: Fight) -> bool:
    """Conjure Swarm, first half. Mark a Stress to encircle yourself in beetles.

    SRD: when you next take damage, reduce the severity by one threshold. You
    can spend a Hope to keep the beetles conjured after taking damage.

    Conjuring is all that happens here - the reduction itself arrives with the
    damage, which is why the other half of this card is a damage response.

    SIMULATION RULE - policy, ruled. Conjured whenever they aren't already up and
    the shared last-slot rule allows the Stress
    (`PlayerCharacter.will_spend_stress`). This card used to refuse the last slot
    outright; the user's general rule releases it once the caster is at 2 or
    fewer unmarked HP, which is the one point where a threshold off the next hit
    is worth going Vulnerable for.
    """
    if fight.token_count(caster, BEETLES):
        return False
    if not fight.living_adversaries:
        return False
    if not caster.will_spend_stress(1):
        return False
    caster.spend_stress(1)

    fight.add_token(caster, BEETLES, cap=1)
    fight.note(f"{caster.name} conjures armored beetles")
    return True


@severity_response("Conjure Swarm")
def beetles_take_the_hit(
    caster: Holder, amount: int, hp_to_mark: int, fight=None, damage_type=None
) -> int:
    """Conjure Swarm, the beetles' payoff: one threshold off the next hit.

    A threshold is worth one HP here, floored at zero - the same arithmetic
    every severity reduction uses.

    `damage_type` is ignored: the card says "when you next take damage" without
    naming a type, so the beetles answer for either kind.

    SIMULATION RULE - policy. The Hope to keep the beetles up afterwards is
    spent only while Hope is plentiful. They're worth exactly one threshold on
    one hit, so a Hope for a second use is a fair price when Hope is spare and a
    poor one when it's the last of it.
    """
    if fight is None or not fight.token_count(caster, BEETLES):
        return hp_to_mark
    if hp_to_mark <= 0:
        return hp_to_mark  # nothing left to soften; don't spend the swarm on it

    if caster.hope_marked >= BEETLES_HOPE_FLOOR and caster.can_spend_hope(1):
        caster.spend_hope(1)
        fight.note(f"{caster.name} spends a Hope to keep the beetles up")
    else:
        fight.spend_tokens(caster, BEETLES, 1)

    return max(hp_to_mark - 1, 0)


@SWARM.action(
    "Fire Flies",
    unmodelled=[
        "'all adversaries within Close range' - no positions are tracked, so "
        "the area rule in SIMULATION-RULES.md decides how many are caught",
    ],
)
def fire_flies(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Conjure Swarm, second half. Spellcast against everything within Close range.

    SRD: make a Spellcast Roll against all adversaries within Close range. Spend
    a Hope to deal 2d8+3 magic damage to targets you succeeded against.

    The roll is made **against the whole area at once**, not against one target
    and then reused - which is the difference between this and Whirlwind. One
    roll and one damage roll, each adversary in the area checked against its own
    Difficulty, and the damage dealt to every one the roll beat. The Hope pays
    for the damage rather than for the roll, so it's spent once the roll is
    known to have landed on somebody.

    SIMULATION RULE - policy. Declines unless it would reach two or more
    adversaries, and declining means the card isn't among the options the PC
    chooses from at all - not that it's cast without the Hope. Against a single
    adversary it would be a Hope spent to do less than the Ranger's bow.
    """
    if not caster.can_spend_hope(1):
        return None

    area = targets_in_area(Range.CLOSE, fight.living_adversaries)
    if len(area) < FIRE_FLIES_WORTH_IT:
        return None

    attack_roll = _spellcast(caster, target, fight, difficulty=area_difficulty(area))
    if attack_roll is None:
        return None

    caught = targets_beaten(attack_roll, area)
    if not caught:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    caster.spend_hope(1)
    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=FIRE_FLIES_DICE, sides=FIRE_FLIES_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=FIRE_FLIES_MODIFIER,
        is_critical=attack_roll.is_critical,
    )

    # Summed across everything caught: the on-hit hooks that read this ask
    # whether the damage roll marked HP, and it did if any target marked one.
    marked = sum(
        adversary.take_damage(damage_roll.total, damage_type=DamageType.MAGIC)
        for adversary in caught
    )
    fight.note(
        f"{caster.name} looses fire flies, catching {len(caught)} "
        f"for {damage_roll.total} each"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


# --- Natural Familiar --------------------------------------------------------

NATURAL_FAMILIAR = "Natural Familiar"

# The familiar itself, once it's out. A token rather than a combatant: nothing
# can target it, so it has no state of its own worth tracking.
FAMILIAR = "Natural Familiar summoned"

FAMILIAR_DIE = 6


@free(
    NATURAL_FAMILIAR,
    unmodelled=[
        "The extra Hope for a familiar that flies - flight has no "
        "representation here",
        "Commanding it with a Spellcast Roll, and marking a Stress to see "
        "through its eyes - both produce information rather than an effect",
        "'or the familiar is targeted by an attack' - nothing ever targets it, "
        "the same gap the Beastbound companion declares, so once summoned it "
        "stays for the whole fight",
    ],
)
def natural_familiar(caster: Holder, fight: Fight) -> bool:
    """Natural Familiar (Sage, level 2). Spend a Hope to summon it.

    SRD: spend a Hope to summon a small nature spirit or forest critter to your
    side until your next rest, you cast Natural Familiar again, or the familiar
    is targeted by an attack. When you deal damage to an adversary within Melee
    range of your familiar, you add a d6 to your damage roll.

    Summoning is all that happens here; the d6 arrives with the damage, which is
    why the other half of this card is an `extra_damage` rider.

    Fires whenever the Hope can be paid and it isn't already out, which is the
    standing default. The one thing it won't do is summon into an empty field -
    a familiar with nothing to stand next to buys nothing at all.
    """
    if fight.token_count(caster, FAMILIAR):
        return False
    if not fight.living_adversaries:
        return False
    if not caster.can_spend_hope(1):
        return False

    caster.spend_hope(1)
    fight.add_token(caster, FAMILIAR, cap=1)
    fight.note(f"{caster.name} summons a familiar")
    return True


@extra_damage(NATURAL_FAMILIAR)
def familiar_flanks(attacker: Holder, target, roll, fight: Fight = None) -> list:
    """Natural Familiar's d6, when the familiar happens to be next to the target.

    SIMULATION RULE - policy, ruled. "Within Melee range of your familiar" is
    positioning, and none is tracked, so **the area rule answers it**: the odds
    that this particular adversary is within the familiar's Melee band, via
    `chance_within` - the same function that decides whether the Faerie's
    Luckbender can reach an ally.

    Rolled per attack rather than settled once, because where the familiar is
    standing is exactly the thing that changes between one swing and the next.
    Reading it as "always adjacent" was offered and declined; so was pinning the
    familiar to the party's focus target.

    What that comes to: against a single adversary the familiar is always beside
    it, and the odds fall away as the field grows - `n // 3`-ish for a Melee
    band, so the d6 is a reliable bonus in a duel and an occasional one in a
    brawl.

    `discardable=False`, like every other die a feature adds to somebody else's
    roll: a Massive or Powerful weapon discards the lowest of the dice *it*
    rolled, and this is not one of them.
    """
    if fight is None or not fight.token_count(attacker, FAMILIAR):
        return []

    living = fight.living_adversaries
    if not living:
        return []
    if random.random() >= chance_within(Range.MELEE, len(living)):
        return []

    return [DiceGroup(count=1, sides=FAMILIAR_DIE, discardable=False)]


# Dismissals are the user's call, not the assistant's.
no_combat_effect(
    "Gifted Tracker",
    "Spend Hope while tracking to ask the GM about a creature's passage, and "
    "gain +1 Evasion against creatures tracked that way. The questions produce "
    "information about the past. The Evasion bonus is real and would be "
    "represented - but it applies only against creatures the party actually "
    "tracked, and nothing here records that they did, so the trigger has no "
    "representation. Modelling it as always on, or as a flag on the encounter, "
    "were both offered and declined.",
)
no_combat_effect(
    "Nature's Tongue",
    "Speaking with plants and animals can't change a fight. Its second clause - "
    "spend a Hope for +2 to a Spellcast Roll while in a natural environment - is "
    "a blanket bonus rather than a specific one, and the simulator already "
    "spends Hope on an Experience it assumes always applies, so that bonus is "
    "in the numbers already. Worth revisiting if Experiences are ever modelled "
    "as applying only sometimes.",
)
