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

Level 5 brings **Wild Fortress**, the first card anywhere that takes PCs *out* of
the fight - two of them shelter inside a dome that soaks what would have hit them
and costs them their spotlights. It is also the first thing with a damage track
that is not a combatant, and the reason `combat/fight.py` now skips a PC who
cannot act instead of spotlighting them.

**Level 6 is the first level of this domain that reaches no fight at all**, and
neither of its cards is dismissed: *Conjured Steeds* and *Forager* are both filed
*out of combat*, which is the state for an effect that is real and representable
and simply happens between fights. Sage is the first domain to have two cards in
that state at one level.

Level 8 turns the domain outward. **Forest Sprites** gives every one of its
benefits to somebody else, twice over, and needed two party-wide hooks that had no
twin before - a flat bonus on an ally's roll, and a second Armor Slot for an
ally's hit. **Rejuvenation Barrier** is the first party-wide *resistance*, and it
is expressed as a reduction rather than a real one, since resistance is
holder-scoped and this barrier belongs to whoever cast it.
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
from content.conditions import RESTRAINED, SHELTERED, Condition, when_the_gm_pays
from content.damage_types import DamageType, types_in
from content.grimoire import Grimoire
from content.registry import (
    Fight,
    Holder,
    action,
    ally_damage_reduction,
    ally_extra_armor_slot,
    ally_roll_bonus,
    extra_damage,
    free,
    no_combat_effect,
    out_of_combat_ability,
    roll_bonus,
    severity_response,
    spellcast_bonus,
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


# --- Thorn Skin ---------------------------------------------------------------

THORN_SKIN = "Thorn Skin"

THORN_DIE = 6

# Tokens still on the card, set to the caster's Spellcast trait when the thorns
# sprout and spent a few at a time against incoming hits.
THORN_TOKENS = "Thorn Skin tokens"


@free(
    THORN_SKIN,
    unmodelled=[
        "'When you take a rest, clear all unspent tokens' - nothing carries "
        "between fights, so a caster is spawned fresh from their sheet and the "
        "tokens go with the fight either way",
    ],
)
def thorn_skin(caster: Holder, fight: Fight) -> bool:
    """Thorn Skin (Sage, level 5). Sprout thorns, once per rest.

    SRD: "Once per rest, spend a Hope to sprout thorns all over your body. When
    you do, place a number of tokens equal to your Spellcast trait on this card."

    **No roll**, so it is a free ability: the Hope and the per-rest use are the
    whole cost and the caster still gets their action roll.

    SIMULATION RULE - policy. Sprouted whenever the Hope can be paid, which is the
    standing default with no threshold of its own. The tokens last the fight and
    clear at the next rest whether or not they were spent, so there is no state in
    which sprouting later is worth more than sprouting now - the same reasoning
    Deadly Focus and Scramble take of a once-per-rest that costs nothing to hold.

    A caster whose Spellcast trait is zero or less places no tokens and declines
    rather than spending a Hope on an empty card, the reading Unleash Chaos takes
    of any count drawn from a trait.
    """
    if fight is None or not caster.can_spend_hope(1):
        return False

    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return False

    tokens = caster.traits[trait]
    if tokens <= 0:
        return False
    if fight.token_count(caster, THORN_TOKENS):
        return False
    if not fight.use_once_per_rest(caster, THORN_SKIN):
        return False

    caster.spend_hope(1)
    fight.set_token(caster, THORN_TOKENS, tokens)
    fight.note(f"{caster.name} sprouts thorns, placing {tokens} tokens")
    return True


@ally_damage_reduction(
    THORN_SKIN,
    unmodelled=[
        "The thorns are the caster's own, so this is scoped back to its holder "
        "with a `holder is target` check - the same arrangement Scramble uses, "
        "since there is no holder-scoped twin of this hook and one card is not a "
        "reason to build one",
    ],
)
def thorn_skin_reduces(
    caster: Holder, target, amount: int, fight: Fight, damage_type=None
) -> int:
    """Thorn Skin's reduction. Returns the damage this hit should lose.

    SRD: "When you take damage, you can spend any number of tokens to roll that
    number of d6s. Add the results together and reduce the incoming damage by that
    amount. If you're within Melee range of the attacker, deal that amount of
    damage back to them."

    **Reduces the damage number, not the severity**, which is why it registers
    here rather than on `severity_response`: that hook returns the HP a hit marks
    and cannot subtract nine from a total. Rune Ward's argument exactly, with a
    pool instead of one die.

    SIMULATION RULE - policy, ruled. **The fewest tokens that could carry the hit
    below a threshold it is currently at or above.** Each token is worth at most 6,
    so the card asks whether `n` tokens *could* drop the damage past the Severe
    line, the Major line, or 1 - that last being the hit disappearing entirely -
    and spends the smallest `n` for which the answer is yes. Nothing is spent on a
    hit no number of tokens could improve, and no more is spent than the hit could
    need. Spending the whole pool on the first hit worth reducing was offered and
    declined.

    Like Rune Ward, it reads only what a player can see when they decide: the
    damage announced and their own printed thresholds. It does **not** read the
    d6s, which nobody has rolled - so a hit seven points above Severe is worth two
    tokens even though a pair of 3s would not have saved it.

    "If you're within Melee range of the attacker" is answered off the attacker's
    **printed band**, the way Redirect answers the same clause - `Adversary.range`
    is a number on the stat block rather than a position. So the thorns bite back
    at whatever came into reach and never at an archer.
    """
    if fight is None or caster is not target:
        return 0

    tokens = fight.token_count(caster, THORN_TOKENS)
    if tokens <= 0:
        return 0

    spending = _thorns_worth_spending(target, amount, tokens)
    if spending <= 0:
        return 0

    fight.spend_tokens(caster, THORN_TOKENS, spending)
    rolled = roll_damage(dice_groups=[DiceGroup(count=spending, sides=THORN_DIE)])
    fight.note(
        f"{caster.name}'s thorns absorb {rolled.total} ({spending} token(s) spent)"
    )

    attacker = fight.spotlighted
    if attacker is not None and attacker.attack_band is Range.MELEE:
        attacker.take_damage(rolled.total, fight, damage_type=DamageType.PHYSICAL)
        fight.note(f"The thorns tear {attacker.name} for {rolled.total}")

    return rolled.total


def _thorns_worth_spending(target, amount: int, tokens: int) -> int:
    """How many tokens could carry this hit below a line it is currently above.

    Each token is one d6, so `n` of them can take off at most `n * THORN_DIE`.
    The lines are the ones that change what the hit costs in HP: the Severe
    threshold, the Major threshold, and 1.

    Returns the smallest such `n`, or 0 when the pool could not move the hit
    across any line - arithmetic on numbers already printed on the sheet and on
    the damage the GM just announced, and on nothing else.
    """
    lines = (target.severe_threshold, target.major_threshold, 1)
    for spending in range(1, tokens + 1):
        if any(
            line <= amount and amount - spending * THORN_DIE < line for line in lines
        ):
            return spending
    return 0


# --- Wild Fortress -------------------------------------------------------------

WILD_FORTRESS = "Wild Fortress"

WILD_FORTRESS_DIFFICULTY = 13
WILD_FORTRESS_HOPE = 2

# The dome's own printed numbers: thresholds 15/30, and it comes apart once it has
# marked 3 Hit Points.
DOME_MAJOR = 15
DOME_SEVERE = 30
DOME_HP = 3

# How much of the dome is gone, held on the caster.
DOME_MARKED = "Wild Fortress HP marked"


@action(
    WILD_FORTRESS,
    unmodelled=[
        "'a creature can't be targeted by attacks' - focus fire still picks a "
        "sheltered PC as readily as anybody, so what is modelled is the dome "
        "taking the hit rather than the attack never being aimed. The two come to "
        "the same thing for damage and not for anything that keys on being "
        "attacked",
        "The dome as a thing with a position, which is most of what it is at a "
        "table - who is inside it is decided when it goes up and nobody walks in "
        "or out",
        "A caster who goes down some *other* way - Stress that wouldn't fit - "
        "stops being scanned for the absorption, so the dome quietly stops "
        "soaking while the ally inside is still held. The fight still resolves, "
        "since that ally then takes damage normally; what is lost is the dome "
        "coming apart at the right moment",
    ],
)
def wild_fortress(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Wild Fortress (Sage, level 5). A dome two PCs shelter inside.

    SRD: "Make a Spellcast Roll (13). On a success, spend 2 Hope to grow a natural
    barricade in the shape of a dome that you and one ally can take cover within.
    While inside the dome, a creature can't be targeted by attacks and can't make
    attacks. Attacks made against the dome automatically succeed. The dome has the
    following damage thresholds and lasts until it marks 3 Hit Points.
    Thresholds: 15/30."

    **Both halves are modelled, and the second is the price.** Everything aimed at
    an occupant lands on the dome instead, marking the dome's own HP against its
    own thresholds; and both occupants lose their spotlights for as long as it
    stands. It is the first card anywhere that takes a PC out of the fight, which
    is why `combat/fight.py` now skips a PC who cannot act instead of spotlighting
    them.

    SIMULATION RULE - policy, ruled. Raised when the caster or the frailest ally
    is **near death**. Giving up two PCs' attacks only pays for itself to keep
    somebody standing, which is Life Ward's trigger applied to a card that costs a
    great deal more than Hope. The ally sheltered is the frailest conscious one -
    Rune Ward's rule for who a protection goes to.

    Declines while a dome already stands, and without an ally to shelter with,
    since the card is explicit that it holds two.
    """
    if fight is None or not caster.can_spend_hope(WILD_FORTRESS_HOPE):
        return None
    if fight.has_condition(caster, SHELTERED):
        return None

    allies = [pc for pc in fight.conscious_party if pc is not caster]
    if not allies:
        return None

    sheltered = min(allies, key=lambda pc: pc.hp_unmarked)
    if not caster.is_near_death and not sheltered.is_near_death:
        return None

    attack_roll = spellcast(
        caster, target, fight, difficulty=WILD_FORTRESS_DIFFICULTY
    )
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    caster.spend_hope(WILD_FORTRESS_HOPE)
    fight.set_token(caster, DOME_MARKED, 0)
    for occupant in (caster, sheltered):
        fight.apply_condition(
            occupant,
            Condition(name=SHELTERED, source=caster, prevents_action=True),
        )
    fight.note(
        f"{caster.name} grows a dome over themselves and {sheltered.name}, "
        f"who take no part until it falls"
    )
    # No damage of its own, so nothing the party carries fires off this as a
    # landed hit - the same shape every condition-only card here returns.
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


@ally_damage_reduction(WILD_FORTRESS)
def wild_fortress_absorbs(
    caster: Holder, target, amount: int, fight: Fight, damage_type=None
) -> int:
    """The dome taking a hit meant for whoever is inside it.

    Returns the whole amount, so the hit resolves to nothing against the PC -
    `take_damage` floors at zero before the thresholds, which also means no Armor
    Slot is spent. That is Scramble's shape, and it is what "can't be targeted by
    attacks" comes to once the attack has been aimed anyway.

    **The dome marks its own HP against its own thresholds**, 15/30, which is the
    one place in the simulator where something other than a combatant has a
    threshold band. "Attacks made against the dome automatically succeed", so
    there is no roll to make - the damage simply arrives.

    Once three are marked the dome comes apart and both occupants are released in
    the same moment, which is the only way the condition ever ends: it carries no
    `end` of its own, so nothing offers it at an announced moment.
    """
    if fight is None:
        return 0

    shelter = fight.condition_on(target, SHELTERED)
    if shelter is None or shelter.source is not caster:
        return 0

    marked = 3 if amount >= DOME_SEVERE else 2 if amount >= DOME_MAJOR else 1
    standing = fight.token_count(caster, DOME_MARKED) + marked
    fight.set_token(caster, DOME_MARKED, standing)
    fight.note(
        f"{caster.name}'s dome takes {amount} for {target.name} "
        f"({min(standing, DOME_HP)}/{DOME_HP} HP marked)"
    )

    if standing >= DOME_HP:
        _dome_falls(caster, fight)
    return amount


def _dome_falls(caster: Holder, fight: Fight) -> None:
    """Release everybody the dome was holding, and clear its tally.

    The condition is cleared here rather than through an `end` predicate because
    what ends it is something happening to the *dome*, which is not a combatant
    and is never offered an announced moment.
    """
    fight.set_token(caster, DOME_MARKED, 0)
    for pc in fight.conscious_party:
        shelter = fight.condition_on(pc, SHELTERED)
        if shelter is not None and shelter.source is caster:
            fight.clear_condition(pc, SHELTERED)
            fight.note(f"The dome falls, and {pc.name} is back in the fight")


# --- Sage-Touched ----------------------------------------------------------------

SAGE_TOUCHED = "Sage-Touched"

SAGE_TOUCHED_SPELLCAST = 2

# "Double your Agility or Instinct" - the two traits the card names, and the only
# ones the doubling reaches.
SAGE_TOUCHED_TRAITS = ("agility", "instinct")

# The gap every *X*-Touched card carries. Written out here rather than imported
# from another domain's module, since one card must never import another's - the
# same duplication Blade, Bone, Midnight and Grace already carry.
TOUCHED_LOADOUT_GAP = (
    "'When 4 or more of the domain cards in your loadout are from the Sage "
    "domain' - the loadout is not counted. The user's ruling is that carrying the "
    "card is taken as proof the condition is met, since a player who takes it has "
    "built for it. Recorded as a simulation rule rather than checked"
)


@spellcast_bonus(SAGE_TOUCHED, unmodelled=[TOUCHED_LOADOUT_GAP])
def sage_touched(caster: Holder, target, fight: Fight = None) -> int:
    """Sage-Touched (Sage, level 7), first clause.

    SRD: "When 4 or more of the domain cards in your loadout are from the Sage
    domain, gain the following benefits: while you're in a natural environment,
    you gain a +2 bonus to your Spellcast Rolls; once per rest, you can double
    your Agility or Instinct when making a roll that uses that trait. You must
    choose to do this before you roll."

    SIMULATION RULE - interpretation, ruled. **Every fight counts as a natural
    environment**, so the bonus is simply on. Nothing here represents terrain -
    where a fight happens is not a fact the simulator holds - and the user's
    ruling was to run the clause rather than declare it a gap. Declaring it, and
    authoring a natural-environment flag on the encounter, were both offered and
    declined. So this errs generous: a Sage fighting in a cellar gets the +2 here
    and would not at a table.

    **Spellcast Rolls and nothing else**, which is why this is on
    `spellcast_bonus` rather than `roll_bonus` - that one is asked from the weapon
    swing too, and a Sage who picks up a Broadsword should not be swinging it at
    +2. Arcana-Touched's argument, with a bigger number.
    """
    return SAGE_TOUCHED_SPELLCAST


@roll_bonus(
    SAGE_TOUCHED,
    unmodelled=[
        "Two action rolls the hook is not asked at - Splendor's Healing Hands and "
        "Grace's Invisibility both roll `roll_duality` by hand rather than through "
        "the shared Spellcast shape, so a Sage carrying either would keep the "
        "doubling for their next roll instead of spending it there. Valor's "
        "Inevitable declares the same two",
        "A **Reaction Roll** that uses Agility or Instinct is never offered it, "
        "which is correct - the SRD's action rolls and reaction rolls are "
        "different things and the card names the first",
    ],
)
def sage_touched_doubles(
    holder: Holder, target, fight: Fight = None, trait: str = ""
) -> int:
    """Sage-Touched's second clause - the trait, counted twice.

    The roll already adds the trait once, so doubling it is a bonus of exactly the
    trait again. **This is the card the trait had to be threaded through the roll
    for**: `roll_bonus` used to be told who was rolling and what at, and never
    which of the six traits was going into the total - so "a roll that uses that
    trait" could not be asked at all.

    "You must choose to do this before you roll" is this hook's own contract
    rather than something that needed arranging: it is asked once, immediately
    before the dice, and **being asked is the commitment**, so the per-rest use is
    claimed here and a reroll re-makes the dice without charging again.

    SIMULATION RULE - policy. The standing rule for a free once-per-rest, which
    Deadly Focus and Premonition already follow: it fires on the **first** action
    roll that uses either trait. Holding it for a better roll would mostly mean
    not using it, and nothing about the roll being made says whether a bigger one
    is coming.

    Declines at a trait of zero or less rather than claiming the use for nothing -
    the standing rule that a benefit computing to zero is not paid for, read off a
    number printed on the character sheet.
    """
    if fight is None or trait not in SAGE_TOUCHED_TRAITS:
        return 0

    doubled = holder.traits.get(trait, 0)
    if doubled <= 0:
        return 0
    if not fight.use_once_per_rest(holder, SAGE_TOUCHED):
        return 0

    fight.note(f"{holder.name} draws on the wild, doubling their {trait} (+{doubled})")
    return doubled


# --- Wild Surge ------------------------------------------------------------------

WILD_SURGE = "Wild Surge"

# The die sitting on the card, held as a token carrying its current face. It goes
# down showing 1 and climbs by one every roll it pays out on.
WILD_SURGE_DIE = "Wild Surge die"
WILD_SURGE_MAX = 6


@free(WILD_SURGE)
def wild_surge(holder: Holder, fight: Fight) -> bool:
    """Wild Surge (Sage, level 7). A Stress buys a die that grows on every roll.

    SRD: "Once per long rest, mark a Stress to channel the natural world around
    you and enhance yourself. Describe how your appearance changes, then place a
    d6 on this card with the 1 value facing up. While the Wild Surge Die is
    active, you add its value to every action roll you make. After you add its
    value to a roll, increase the Wild Surge Die's value by one. When the die's
    value would exceed 6 or you take a rest, this form drops and you must mark an
    additional Stress."

    **No roll**, so it is a free ability: the Stress is the whole cost and the
    caster still takes their action roll in the same spotlight - which means the
    surge can pay out on the very roll it was raised for.

    SIMULATION RULE - policy, ruled. **Raised at the first spotlight the Stress
    allows.** The die is worth +1 through +6 across six action rolls, twenty-one
    points in total, and every spotlight spent unsurged is one of those rolls
    thrown away - so there is no moment worth waiting for. `will_spend_stress` is
    the shared last-slot rule, as every PC Stress cost is.

    Once per **long** rest, so a party pushed through a second encounter without
    one walks in with it already spent.
    """
    if fight is None or fight.token_count(holder, WILD_SURGE_DIE):
        return False
    if not holder.will_spend_stress(1):
        return False
    if not fight.use_once_per_rest(holder, WILD_SURGE, long=True):
        return False

    holder.spend_stress(1)
    fight.set_token(holder, WILD_SURGE_DIE, 1)
    fight.note(f"{holder.name} surges with the wild, and the die goes down at 1")
    return True


@roll_bonus(
    WILD_SURGE,
    unmodelled=[
        "'every action roll you make' reaches the three shared roll sites and not "
        "the two cards that roll `roll_duality` by hand - Splendor's Healing Hands "
        "and Grace's Invisibility. A Sage carrying either would neither get the "
        "bonus there nor tick the die, which is the same gap Sage-Touched and "
        "Inevitable declare",
        "A Reaction Roll neither takes the bonus nor advances the die. That is the "
        "reading rather than an omission - the card says *action roll*, and the "
        "SRD keeps the two apart",
    ],
)
def wild_surge_climbs(
    holder: Holder, target, fight: Fight = None, trait: str = ""
) -> int:
    """The Wild Surge Die's value, added and then advanced.

    The order is the card's: the roll gets the value the die is *currently*
    showing, and the die goes up afterwards. So the sixth roll it pays out on gets
    +6 and is the last - the seventh would need a 7, which is what "would exceed
    6" names, and the form drops there.

    The Stress the form costs on the way out is **forced**, not spent, so a PC
    with no free slot marks an HP for it and can be dropped by their own surge
    ending. That is what the page says, and it is the whole risk the card carries.

    `trait` is unused: the die adds to any action roll, and the card names none.

    Being asked is the commitment, the contract every pre-roll hook keeps - which
    here means the die advances on the roll it was asked for even if a reroll
    later replaces the dice.
    """
    if fight is None:
        return 0

    value = fight.token_count(holder, WILD_SURGE_DIE)
    if value <= 0:
        return 0

    if value + 1 > WILD_SURGE_MAX:
        fight.set_token(holder, WILD_SURGE_DIE, 0)
        holder.mark_stress(1)
        fight.note(
            f"{holder.name}'s wild surge burns out at +{value}, costing them a Stress"
        )
    else:
        fight.set_token(holder, WILD_SURGE_DIE, value + 1)
    return value


# --- Forest Sprites --------------------------------------------------------------

FOREST_SPRITES = "Forest Sprites"

FOREST_SPRITES_DIFFICULTY = 13

# How many sprites are still standing, held on the caster. Each grants exactly one
# benefit and then vanishes, so this is a pool of charges rather than a flag.
SPRITES_STANDING = "Forest Sprites standing"

FOREST_SPRITES_ATTACK_BONUS = 3

# Hope is what several other cards and every Experience is bought with, so the
# spell empties the pool down to this rather than through it. Ruled - Arcane
# Barrage's floor, read here for the second time rather than a new number.
FOREST_SPRITES_HOPE_FLOOR = 2


@action(
    FOREST_SPRITES,
    unmodelled=[
        "'who appear at points you choose within Far range' and 'within Melee "
        "range of a sprite' - no positions are tracked, so where a sprite stands "
        "is not a choice the caster makes and being beside one is not a fact the "
        "simulator holds. A standing sprite pays out to whoever next triggers it, "
        "which is more generous than the page: at a table a badly placed sprite "
        "helps nobody",
        "'or taking any damage' - a sprite can only be spent by granting a "
        "benefit here. Nothing targets one, since a sprite is not a combatant, so "
        "the second way they vanish never happens",
    ],
)
def forest_sprites(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Forest Sprites (Sage, level 8). A Hope apiece for a field of one-shot helpers.

    SRD: "Make a Spellcast Roll (13). On a success, spend any number of Hope to
    create an equal number of small forest sprites who appear at points you choose
    within Far range, providing the following benefits: your allies gain a +3 bonus
    to attack rolls against adversaries within Melee range of a sprite; an ally who
    marks an Armor Slot while within Melee range of a sprite can mark an additional
    Armor Slot. A sprite vanishes after granting a benefit or taking any damage."

    **Every benefit this card grants goes to somebody else** - "your allies", both
    times - which is why it needed two party-wide hooks that had no twin before:
    `ally_roll_bonus` for the +3 and `ally_extra_armor_slot` for the slot. Battle
    Cry needed the third one of that shape, and between them the party side can now
    reach an ally's roll and an ally's armor.

    A flat Difficulty of 13, printed on the card: the sprites are conjured rather
    than aimed at anybody. The roll still goes through `content/spellcast.py`, so
    it is a real action roll and its Hope or Fear moves the spotlight.

    SIMULATION RULE - policy, ruled. **Hope is spent down to a floor of 2**, which
    is Arcane Barrage's rule: the pool is what every Experience and several other
    cards are bought with, and this spell would otherwise swallow all of it.
    Spending every Hope, a fixed three, and casting only above 5 were all offered
    and declined.

    Declines while sprites are still standing, so the caster does not spend a
    second cast topping up a field they already have.
    """
    if fight is None:
        return None
    if fight.token_count(caster, SPRITES_STANDING):
        return None

    spare = caster.hope_marked - FOREST_SPRITES_HOPE_FLOOR
    if spare <= 0:
        return None

    attack_roll = spellcast(
        caster, target, fight, difficulty=FOREST_SPRITES_DIFFICULTY
    )
    if attack_roll is None:
        return None
    if not attack_roll.is_success:
        fight.note(f"{caster.name} calls, and nothing answers ({attack_roll})")
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    caster.spend_hope(spare)
    fight.set_token(caster, SPRITES_STANDING, spare)
    fight.note(f"{caster.name} spends {spare} Hope; {spare} forest sprites appear")
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


@ally_roll_bonus(FOREST_SPRITES)
def forest_sprites_guide(
    holder: Holder, attacker, target, fight: Fight = None, trait: str = ""
) -> int:
    """The +3 a sprite hands one ally's swing, and the sprite spent doing it.

    Registered on the same name as the action above - the arrangement one card uses
    to reach several hooks. `attacker is not holder` is the card's own word: *your
    allies*, so the Druid who conjured them swings unaided.

    Being asked is the commitment, which is this hook's contract and exactly what
    the card needs: "a sprite vanishes after granting a benefit", so the charge is
    spent here rather than waiting to be told the roll happened.
    """
    if fight is None or attacker is holder:
        return 0
    if not fight.spend_tokens(holder, SPRITES_STANDING, 1):
        return 0

    fight.note(f"A sprite guides {attacker.name}'s blow (+{FOREST_SPRITES_ATTACK_BONUS})")
    return FOREST_SPRITES_ATTACK_BONUS


@ally_extra_armor_slot(FOREST_SPRITES)
def forest_sprites_shield(
    holder: Holder,
    target,
    amount: int,
    hp_to_mark: int,
    fight: Fight = None,
    damage_type=None,
) -> int:
    """The second Armor Slot a sprite buys an ally, and the sprite spent on it.

    Being asked means a free slot has already gone in - the hook's contract, and
    the card's trigger read literally ("an ally who marks an Armor Slot").

    SIMULATION RULE - policy. The Brace rule: the sprite is spent only where the
    extra slot would actually save an HP, since the free slot has already taken a
    band off and a second one on a hit already marking nothing buys nothing. That
    is the standing zero-benefit rule, read off the announced damage and the
    target's printed thresholds.

    Scoped to allies, like the +3 above, because the card says so both times.
    """
    if fight is None or target is holder or hp_to_mark <= 0:
        return 0
    if not fight.spend_tokens(holder, SPRITES_STANDING, 1):
        return 0

    fight.note(f"A sprite takes the blow with {target.name}, buying a second slot")
    return 1


# --- Rejuvenation Barrier --------------------------------------------------------

REJUVENATION_BARRIER = "Rejuvenation Barrier"

REJUVENATION_DIFFICULTY = 15
REJUVENATION_DIE = 4

# Set on the caster while the barrier stands. It follows them and has no printed
# ender, so it lasts the fight.
BARRIER_STANDING = "Rejuvenation Barrier standing"


@action(
    REJUVENATION_BARRIER,
    unmodelled=[
        "'from **outside** the barrier' - the resistance is printed to apply only "
        "to damage crossing it, and nothing records where an attack came from. So "
        "every physical hit is halved, which errs generous",
        "'when you move, the barrier follows you' - no positions are tracked, so "
        "the barrier is never anywhere in particular and never has to keep up",
    ],
)
def rejuvenation_barrier(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Rejuvenation Barrier (Sage, level 8). A dome that heals once and then holds.

    SRD: "Make a Spellcast Roll (15). Once per rest on a success, create a
    temporary barrier of protective energy around you at Very Close range. You and
    all allies within the barrier when this spell is cast clear 1d4 Hit Points.
    While the barrier is up, you and all allies within have resistance to physical
    damage from outside the barrier. When you move, the barrier follows you."

    **Two halves with very different shapes.** The clear happens once, to whoever
    is inside at the moment of casting; the resistance runs for the rest of the
    fight and is asked per hit. Who is inside is the standing positional answer -
    `chance_within` over the party, rolled at each question, which is Zone of
    Protection's ruling of the same shape.

    SIMULATION RULE - policy, ruled. **Cast as early as the option shuffle
    allows**, which is Zone of Protection's rule for the same reason: the
    resistance is the larger half and runs until the fight ends, so a spotlight
    spent uncast throws part of it away. Waiting for somebody with HP marked, and
    for the Healing Field floor of two, were both offered and declined - the cost
    is that the 1d4 is sometimes rolled on a party at full health, where `clear_hp`
    clamps it to nothing.

    The 1d4 is rolled **per person**, the way Rousing Strike's is: the card gives
    each creature inside a clear of its own rather than one shared number.

    Once per rest on a **success**, which the card prints - so a failed cast costs
    the spotlight and leaves the card available.
    """
    if fight is None or fight.token_count(caster, BARRIER_STANDING):
        return None
    if not fight.can_use_once_per_rest(caster, REJUVENATION_BARRIER):
        return None

    attack_roll = spellcast(
        caster, target, fight, difficulty=REJUVENATION_DIFFICULTY
    )
    if attack_roll is None:
        return None
    if not attack_roll.is_success:
        fight.note(f"{caster.name}'s barrier fails to form ({attack_roll})")
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    fight.use_once_per_rest(caster, REJUVENATION_BARRIER)
    fight.set_token(caster, BARRIER_STANDING, 1)

    inside = [caster] + [
        pc
        for pc in fight.conscious_party
        if pc is not caster
        and random.random() < chance_within(Range.VERY_CLOSE, len(fight.conscious_party) - 1)
    ]
    for pc in inside:
        cleared = random.randint(1, REJUVENATION_DIE)
        pc.clear_hp(cleared)
    fight.note(
        f"{caster.name} raises a rejuvenation barrier over {len(inside)} of the party"
    )
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


@ally_damage_reduction(
    REJUVENATION_BARRIER,
    unmodelled=[
        "The halving is expressed as a **reduction** rather than as a true "
        "resistance, because `damage_resistance` is holder-scoped and this barrier "
        "belongs to somebody else. Two consequences, both declared rather than "
        "hidden: it sums with other reductions instead of following the SRD's "
        "'strongest single resistance' rule, and it lands after any real resistance "
        "the target carries rather than being reconciled with it",
    ],
)
def rejuvenation_barrier_holds(
    holder: Holder, target, amount: int, fight: Fight, damage_type=None
) -> int:
    """Half of a physical hit, taken off anybody standing inside the barrier.

    Registered on the same name as the action above. Physical only, as the card
    says; magic passes straight through.

    Returned as the **difference** rather than the half, so what survives is
    `amount // 2` - the same figure `reduced` produces for a real resistance, since
    both round the surviving half down.

    Membership is rolled per hit, which is Zone of Protection's ruling: the barrier
    is a place rather than a list of occupants, so the same PC can be inside it for
    one blow and outside for the next. The caster is inside always - it is centred
    on them.
    """
    if fight is None or not fight.token_count(holder, BARRIER_STANDING):
        return 0
    if DamageType.PHYSICAL not in types_in(damage_type):
        return 0

    if target is not holder:
        others = len(fight.conscious_party) - 1
        if random.random() >= chance_within(Range.VERY_CLOSE, others):
            return 0

    sheltered = amount - amount // 2
    fight.note(f"{target.name} is inside the barrier, and it takes {sheltered}")
    return sheltered


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

out_of_combat_ability(
    "Conjured Steeds",
    "Spend any number of Hope to conjure that many steeds the party rides until "
    "their next long rest or the steeds take any damage. Two of its three clauses "
    "are travel - double land speed, and moving within Far range without a roll - "
    "and the third is a real combat trade the simulator could express outright: a "
    "rider takes -2 on attack rolls and gains +2 on damage rolls. So this is not a "
    "dismissal, and filing it as one would have been false in both directions. "
    "What is true of it is *when* it is cast: conjuring mounts is something a "
    "party does on the road, and the ridden state is what they would carry into "
    "the fight at the far end of it. The user ruled it into this state on that "
    "reading, so it joins the sequenced-encounter list rather than being written "
    "as something cast mid-fight.",
)

out_of_combat_ability(
    "Forager",
    "'As an additional downtime move you can choose, roll a d6 to see what you "
    "forage' - the card names its own moment, and it is between fights. What it "
    "produces is not: the six results are a food that clears 2 Stress, a relic "
    "worth 2 Hope, an arcane rune worth +2 to a Spellcast Roll, a healing vial "
    "that clears 2 Hit Points, a luck charm that rerolls any die, and a free "
    "choice among them, and the party can carry five at a time. Every one of "
    "those would change a fight it was spent in. The user's ruling is that when "
    "sequenced encounters land, this is modelled as the downtime move it is - "
    "each forage handing the party a consumable carrying one of those abilities - "
    "so the card is on the to-do list rather than dismissed.",
)
