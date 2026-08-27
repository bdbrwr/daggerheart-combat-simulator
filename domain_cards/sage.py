"""Sage domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json, checked against the printed page
(SRD p. 130).

Corrosive Projectile at level 3 is the first card anywhere that changes an
adversary's **Difficulty** mid-fight. It does it by writing the new number into
the spawned stat block rather than carrying a condition, which is the same place
`Flying (X)` resolves - see its docstring for why.

Level 4 brings the first card that offers a *menu*. **Death Grip** prints three
effects and lets the caster pick one, and one of the three is pure repositioning
- so the ruling is which of them a simulated caster chooses between, and the cost
of that ruling is declared as a gap where the card registers. **Healing Field**
is the first party-wide heal here that is not a domain card's rider.
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
from content.conditions import RESTRAINED, Condition, when_the_gm_pays
from content.damage_types import DamageType
from content.grimoire import Grimoire
from content.registry import (
    Fight,
    Holder,
    action,
    extra_damage,
    free,
    no_combat_effect,
    severity_response,
    total_extra_damage,
)
from content.spellcast import spellcast
from dice.d20 import roll_d20
from dice.damage import DiceGroup, roll_damage

CORROSIVE_PROJECTILE = "Corrosive Projectile"

CORROSIVE_DIE = 6
CORROSIVE_MODIFIER = 4

# The SRD's minimum: "mark 2 or more Stress", worth -1 Difficulty per 2. Ruled to
# the minimum, so one cast buys one point and the rest of the track stays for
# everything else that wants it.
CORRODE_STRESS = 2
CORRODE_DIFFICULTY = 1

# However corroded a stat block gets, there has to be a number left to beat. A
# Difficulty of zero would make every roll against it an automatic success, which
# is not something the SRD ever prints.
MINIMUM_DIFFICULTY = 1

TOWERING_STALK = "Towering Stalk"

TOWERING_STALK_DIE = 8

# The same floor Fire Flies uses, and for the same reason: an area spell aimed at
# one adversary is a worse weapon swing bought with a resource.
TOWERING_STALK_WORTH_IT = 2


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
    attack_roll = spellcast(caster, target, fight)
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

    attack_roll = spellcast(caster, target, fight, difficulty=area_difficulty(area))
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


# --- Corrosive Projectile ----------------------------------------------------


@action(
    CORROSIVE_PROJECTILE,
    unmodelled=[
        "'within Far range' - no positions are tracked, so this always reaches",
        "Stacking beyond one cast is real but arrives one point at a time: each "
        "cast marks the printed minimum of 2 Stress for a single -1, rather "
        "than emptying the track into one projectile",
    ],
)
def corrosive_projectile(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Corrosive Projectile (Sage, level 3).

    SRD: make a Spellcast Roll against a target within Far range. On a success,
    deal d6+4 magic damage using your Proficiency. Additionally, mark 2 or more
    Stress to make them permanently Corroded - a -1 penalty to their Difficulty
    for every 2 Stress spent, and the condition stacks.

    SIMULATION RULE - rules interpretation. **Corroded is written straight into
    the adversary's Difficulty** rather than carried as a `Condition`. The card
    says *permanently*, so there is nothing for an ender to do, and Difficulty is
    read in four places that have no fight to dispatch with - `items/weapons.py`,
    `content/aoe.py`'s `area_difficulty` and `targets_beaten`, and Hold Them Off.
    This is the same place `Flying (X)` resolves and for the same reason: an
    adversary in a fight is a spawned copy, so nothing leaks back into the
    catalogue.

    That also gives stacking for free - a second cast subtracts another point -
    and it means every reader of the number is already correct without knowing
    this card exists.

    SIMULATION RULE - policy, ruled. The **printed minimum of 2 Stress**, for one
    -1. Spending down in pairs while the shared rule allowed it was offered and
    declined: a point of Difficulty is bought per cast and the rest of the track
    stays available for everything else that wants a Stress.

    Never declines. The spell deals its damage whether or not the Stress is
    affordable, so there is no state in which casting it is a wasted spotlight -
    the corrosion is an extra the caster pays for afterwards if they can.
    """
    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=caster.proficiency, sides=CORROSIVE_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=CORROSIVE_MODIFIER,
        is_critical=attack_roll.is_critical,
    )
    marked = target.take_damage(damage_roll.total, fight, damage_type=DamageType.MAGIC)
    fight.note(
        f"{caster.name} hits {target.name} with a corrosive projectile "
        f"for {damage_roll.total}"
    )

    _corrode(caster, target, fight)
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


def _corrode(caster: Holder, target, fight: Fight) -> None:
    """Mark the Stress to take a point off the target's Difficulty, if worth it.

    Skipped against a target the hit just defeated - it is off the field, so a
    permanent penalty on it is permanently worth nothing. That is a state the
    party can see rather than a statistic anyone works out, the same skip
    Forceful Push makes for a target already Vulnerable.

    Also skipped once the Difficulty has nowhere left to fall. Nothing in the SRD
    prints a Difficulty a roll cannot fail against, so `MINIMUM_DIFFICULTY` is a
    floor of ours - and a Stress spent below it would buy nothing.
    """
    if target.is_defeated or target.difficulty <= MINIMUM_DIFFICULTY:
        return
    if not caster.will_spend_stress(CORRODE_STRESS):
        return

    caster.spend_stress(CORRODE_STRESS)
    target.difficulty = max(target.difficulty - CORRODE_DIFFICULTY, MINIMUM_DIFFICULTY)
    fight.note(
        f"{target.name} is Corroded - Difficulty now {target.difficulty}"
    )


# --- Towering Stalk ----------------------------------------------------------


@action(
    TOWERING_STALK,
    unmodelled=[
        "The climbable stalk itself - a thing to climb, up to Far range. "
        "Movement and terrain, neither of which is represented",
        "'within Close range' - no positions are tracked, so the area rule in "
        "SIMULATION-RULES.md decides how many adversaries the stalk catches",
        "Being lifted into the air and dropped - the damage is what is modelled; "
        "where anybody lands is not",
    ],
)
def towering_stalk(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Towering Stalk (Sage, level 3).

    SRD: once per rest, conjure a thick twisting stalk within Close range that
    can be easily climbed, growing up to Far range. Mark a Stress to use this
    spell as an attack: make a Spellcast Roll against an adversary or group of
    adversaries within Close range, lifting targets you succeed against into the
    air and dropping them for d8 physical damage using your Proficiency.

    SIMULATION RULE - rules interpretation, ruled. **The once-per-rest limit
    covers the attack too.** The card prints "once per rest, you can conjure" and
    then, in a separate paragraph, "mark a Stress to use this spell as an
    attack" - and attacking with it *is* conjuring it, so the limit is on the
    spell rather than on the climbing. Read the other way this would be a
    repeatable area attack for a Stress apiece.

    SIMULATION RULE - policy, ruled. Declines below two adversaries in the area,
    the same floor Fire Flies and Rain of Blades use: one use per rest bought
    with a Stress is a real cost, and aimed at a single target it is a worse
    weapon swing.

    The roll is made **against the whole area at once** - one roll, one damage
    roll, each adversary checked against its own Difficulty - which is the Fire
    Flies shape rather than Whirlwind's reuse of a single-target roll.

    Physical damage, not magic. The stalk drops them; nothing burns.

    The per-rest use and the Stress are both **checked before the roll and paid
    after** it, so declining costs neither.
    """
    if not fight.can_use_once_per_rest(caster, TOWERING_STALK):
        return None
    if not caster.will_spend_stress(1):
        return None

    area = targets_in_area(Range.CLOSE, fight.living_adversaries)
    if len(area) < TOWERING_STALK_WORTH_IT:
        return None

    attack_roll = spellcast(caster, target, fight, difficulty=area_difficulty(area))
    if attack_roll is None:
        return None

    fight.use_once_per_rest(caster, TOWERING_STALK)
    caster.spend_stress(1)

    caught = targets_beaten(attack_roll, area)
    if not caught:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=caster.proficiency, sides=TOWERING_STALK_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        is_critical=attack_roll.is_critical,
    )
    # Summed across everything caught, the way Fire Flies sums: the on-hit hooks
    # that read this ask whether the damage roll marked HP, and it did if any
    # target marked one.
    marked = sum(
        adversary.take_damage(damage_roll.total, fight, damage_type=DamageType.PHYSICAL)
        for adversary in caught
    )
    fight.note(
        f"{caster.name}'s stalk erupts, lifting {len(caught)} and dropping them "
        f"for {damage_roll.total} each"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


# --- Death Grip --------------------------------------------------------------

DEATH_GRIP = "Death Grip"

# The Reaction Roll the vines force, printed on the card.
DEATH_GRIP_DIFFICULTY = 13

DEATH_GRIP_DICE = 3
DEATH_GRIP_DIE = 6
DEATH_GRIP_MODIFIER = 2

# "Force them to mark 2 Stress" - the constricting option.
DEATH_GRIP_STRESS = 2

# The card's three options, by what they do here. The pull is not among them -
# see the docstring.
CONSTRICT = "constrict"
VINES = "vines"


@action(
    DEATH_GRIP,
    unmodelled=[
        "The **pull** option - 'you pull the target into Melee range or pull "
        "yourself into Melee range of them'. Pure repositioning, and no positions "
        "are tracked, so it is not one of the options a simulated caster chooses "
        "between. Worth knowing which way that errs: at a table the pull is a "
        "real choice, so this card comes out somewhat better here than it plays",
        "'within Close range' and 'all adversaries between you and the target' - "
        "no positions are tracked, so the area rule in SIMULATION-RULES.md "
        "decides how much of the field the vines cross",
        "Being Restrained itself, which is ruled to have no effect of its own "
        "here because no movement is modelled - so what the Restrain comes to is "
        "the Fear the GM must spend to clear it, exactly as Shadowbind's does",
    ],
)
def death_grip(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Death Grip (Sage, level 4).

    SRD: make a Spellcast Roll against a target within Close range and choose one
    of - pulling the target into Melee range (or yourself into theirs);
    constricting them to force 2 Stress; or vines catching all adversaries
    between you and the target, who must succeed on a Reaction Roll (13) or take
    3d6+2 physical damage. On a success, the chosen effect happens and the target
    is temporarily Restrained.

    SIMULATION RULE - policy, ruled. **The choice is random between the two
    options that bite here**, and the pull is not one of them: its whole effect is
    where somebody is standing, so it is not an option whose cost can be paid in
    the sense the standing random-among-viable rule means. That is Strategic
    Approach's precedent, where the token always buys the d8 because the other two
    options cannot be evaluated. The honest cost of the ruling is stated as a gap
    above - a table would sometimes take the pull, and this caster never does.

    The **vines are only a candidate when they reach somebody**, since a sweep
    that catches nobody is not an option that reaches anybody. So against a lone
    adversary the card always constricts, which is the same shape every area card
    here has.

    SIMULATION RULE - rules interpretation, ruled. **"Between you and the target"
    is the Close band with the target taken out.** The target is at Close range,
    so anything between is inside that band; and the target is not hit by the
    vines - it gets the Restrain instead - so it comes out of the count.

    The save is a **clean escape, not a save for half**: the card says "succeed on
    a Reaction Roll (13) **or** be hit", where Scorched Earth and Hellfire print
    "targets who succeed take half damage" and this one prints nothing of the
    kind. An adversary rolls a flat d20 with no modifier, having no traits, and a
    critical takes nothing at all - both standing readings.

    Never declines. It costs nothing but the roll the caster was making anyway.
    """
    if fight is None:
        return None

    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    # Rolled once and reused: the band's reach is a random draw, so asking twice
    # would give the choice one field and the resolution another.
    between = [
        adversary
        for adversary in targets_in_area(Range.CLOSE, fight.living_adversaries)
        if adversary is not target
    ]

    options = [CONSTRICT] + ([VINES] if between else [])
    # Only drawn from when there is a choice to make - the same reason
    # `_party_offers` skips its shuffle, since a draw nobody needed would shift
    # every later roll in the fight.
    chosen = random.choice(options) if len(options) > 1 else options[0]

    damage_roll = None
    marked = 0
    if chosen == VINES:
        damage_roll = roll_damage(
            dice_groups=[DiceGroup(count=DEATH_GRIP_DICE, sides=DEATH_GRIP_DIE)]
            + total_extra_damage(caster, target, attack_roll, fight),
            modifier=DEATH_GRIP_MODIFIER,
            is_critical=attack_roll.is_critical,
        )
        for adversary in between:
            save = roll_d20(evasion=DEATH_GRIP_DIFFICULTY)
            if save.is_success or save.is_critical:
                continue
            marked += adversary.take_damage(
                damage_roll.total, fight, damage_type=DamageType.PHYSICAL
            )
        fight.note(
            f"{caster.name}'s vines lash out at {len(between)} between them "
            f"and {target.name} for {damage_roll.total}"
        )
    else:
        # Forced rather than spent: an adversary with a full Stress track simply
        # loses nothing, since the SRD's overflow-into-HP rule is a PC rule.
        target.mark_stress(DEATH_GRIP_STRESS)
        fight.note(
            f"{caster.name} constricts {target.name}, forcing "
            f"{DEATH_GRIP_STRESS} Stress"
        )

    if not target.is_defeated and not fight.has_condition(target, RESTRAINED):
        fight.apply_condition(
            target, Condition(name=RESTRAINED, end=when_the_gm_pays, source=caster)
        )

    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


# --- Healing Field -----------------------------------------------------------

HEALING_FIELD = "Healing Field"

HEALING_FIELD_HOPE = 2

# What the 2 Hope upgrades the clear to, and also the number of marked HP
# somebody has to be carrying before it is worth paying for.
HEALING_FIELD_GREATER = 2

# How many people the field has to actually restore before it is worth the one
# use a long rest gives.
HEALING_FIELD_WORTH_IT = 2


@free(
    HEALING_FIELD,
    unmodelled=[
        "'everywhere within Close range of you bursts to life' - no positions are "
        "tracked, so the area rule decides which allies are standing in the "
        "field. The caster is always in it, since it is centred on them",
    ],
)
def healing_field(caster: Holder, fight: Fight) -> bool:
    """Healing Field (Sage, level 4). Once per long rest, the party clears HP.

    SRD: "Once per long rest, you can conjure a field of healing plants around
    you. Everywhere within Close range of you bursts to life with vibrant nature,
    allowing you and all allies in the area to clear a Hit Point. Spend 2 Hope to
    allow you and all allies to clear 2 Hit Points instead."

    **No roll**, which makes it a free ability: it costs a use and possibly some
    Hope, so it never spends the spotlight's action roll and the caster can raise
    the field *and* attack in the same spotlight.

    **Once per *long* rest**, which a short rest does not give back - the printed
    granularity rather than the per-rest limit most cards carry.

    SIMULATION RULE - policy, ruled. Two decisions:

    * The field waits until it would restore **two or more people**. One use a
      long rest is a real cost, and spending it to take a single HP off a single
      PC is the shape of thing that leaves a party wishing they had it later.
    * The 2 Hope is spent only when somebody in the field actually has **2 HP
      marked** to clear. That is the standing clearing-in-full rule: paying for a
      2 HP clear that everybody only takes 1 of is two Hope for one HP.

    Both read only what a player can see - their allies' marked HP and their own
    Hope - and the caster counts as one of the people restored, since the card
    says "you and all allies".

    An unconscious PC is not reached. `clear_hp` deliberately does not wake one,
    and the party the field is measured over is the conscious one, so this is
    consistent with every other heal here rather than a rule of its own.
    """
    if fight is None:
        return False
    if not fight.can_use_once_per_rest(caster, HEALING_FIELD, long=True):
        return False

    # The caster is in their own field by definition, so only the allies are put
    # to the band.
    allies = [pc for pc in fight.conscious_party if pc is not caster]
    reached = [caster] + targets_in_area(Range.CLOSE, allies)

    restored = [pc for pc in reached if pc.hp_marked > 0]
    if len(restored) < HEALING_FIELD_WORTH_IT:
        return False

    greater = caster.can_spend_hope(HEALING_FIELD_HOPE) and any(
        pc.hp_marked >= HEALING_FIELD_GREATER for pc in restored
    )

    fight.use_once_per_rest(caster, HEALING_FIELD, long=True)
    if greater:
        caster.spend_hope(HEALING_FIELD_HOPE)

    cleared = HEALING_FIELD_GREATER if greater else 1
    for pc in restored:
        pc.clear_hp(cleared)
    fight.note(
        f"{caster.name} raises a healing field, clearing {cleared} HP "
        f"on {len(restored)}"
    )
    return True


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
