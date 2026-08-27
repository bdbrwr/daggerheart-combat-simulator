"""Arcana domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json, checked against the printed page
(SRD p. 119), where the Domain Card Reference appendix begins.

Cards from this domain that can't affect a fight are declared at the bottom.
"""

import random

from combat.results import AttackResult
from content.aoe import Range, area_difficulty, targets_beaten, targets_in_area
from content.conditions import ON_FIRE, WHEN_THEY_ACT, Condition, when_the_gm_pays
from content.damage_types import DamageType, types_in
from content.registry import (
    Fight,
    Holder,
    action,
    ally_damage_reduction,
    hope_die_for,
    no_combat_effect,
    total_extra_damage,
)
from content.spellcast import spellcast
from dice.damage import DiceGroup, roll_damage
from dice.duality import roll_duality

# --- Rune Ward ---------------------------------------------------------------

RUNE_WARD = "Rune Ward"

# Who is carrying the trinket, set once per fight. A token on the holder rather
# than on the caster, because the dispatch that reads it is asked about whoever
# is taking the damage.
WARDED = "Rune Ward held"

# Set on the *caster* once the ward has burned out, so a Ward Die of 8 ends it
# for the rest of the fight - "recharged for free on your next rest" means it
# comes back between encounters, not during one.
WARD_SPENT = "Rune Ward spent"

WARD_DIE = 8


@ally_damage_reduction(
    RUNE_WARD,
    unmodelled=[
        "Choosing to move the ward mid-fight - it goes to the ally closest to "
        "going down when the first hit of the fight lands and stays with them. "
        "It is re-given only if that ally drops, which costs nothing: an "
        "unconscious PC can't be targeted, so a ward on one is inert anyway",
        "'held as a ward by you or an ally' - the caster never keeps it, per "
        "the ruling that it goes to somebody else",
        "The Hope is spent by whoever holds the ward, so a caster with an empty "
        "Hope pool still protects an ally who has one - which is what the card "
        "says, and worth naming because every other card here spends its "
        "owner's resources",
    ],
)
def rune_ward(
    caster: Holder, target, amount: int, fight: Fight, damage_type=None
) -> int:
    """Rune Ward (Arcana, level 1). Returns the damage this hit should lose.

    SRD: a personal trinket infused with protective magic, held as a ward by you
    or an ally. The ward's holder can spend a Hope to reduce incoming damage by
    1d8. If the Ward Die result is 8, the ward's power ends after it reduces
    damage this turn; it recharges for free on your next rest.

    **Reduces the damage number, not the severity.** That is what makes this the
    first registrant on `ally_damage_reduction`: an Armor Slot moves the hit down
    a threshold band and a `severity_response` moves the HP it marks, and neither
    can subtract eight from a total. Landing before the thresholds is the whole
    value of it - the same 1d8 that shaves a point off a huge hit can drop a
    borderline one out of Severe, or take a small one away entirely.

    SIMULATION RULE - policy, ruled. Two decisions, both the user's:

    * **The frailest ally holds it**, never the caster - whoever has the least
      unmarked HP at the moment the ward is first asked about. So a Wizard's Hope
      pays for somebody else's defence, which is what the trinket is for.
    * **The Hope is spent only when the 1d8 could actually save an HP**, which is
      `_could_save_an_hp` below. Reading it any other way spends Hope on hits
      that were always going to mark the same number.

    The second decision reads only what a player can see when they make it: the
    damage the GM announced and their own printed thresholds. It does **not**
    read the Ward Die, which nobody has rolled yet - a hit two points above the
    Severe threshold is worth warding even though a 1 wouldn't save it.
    """
    if fight is None or fight.token_count(caster, WARD_SPENT):
        return 0

    holder = _ward_holder(caster, fight)
    if holder is None or holder is not target:
        return 0
    if not _could_save_an_hp(target, amount):
        return 0
    if not holder.can_spend_hope(1):
        return 0

    holder.spend_hope(1)
    rolled = random.randint(1, WARD_DIE)
    if rolled == WARD_DIE:
        # "The ward's power ends after it reduces damage this turn" - so this hit
        # is still reduced, and nothing after it is.
        fight.set_token(caster, WARD_SPENT, 1)
        fight.note(f"{holder.name}'s rune ward burns out as it takes {rolled}")
    else:
        fight.note(f"{holder.name}'s rune ward absorbs {rolled}")
    return rolled


def _ward_holder(caster: Holder, fight: Fight):
    """Whoever is carrying the trinket, choosing them the first time it matters.

    Assigned lazily rather than at the start of the fight because nothing
    announces a fight starting to content - and the answer is the same either
    way in every case that matters, since the ward is first asked about on the
    first hit anybody takes.

    Returns None when the caster has no ally to give it to. A lone PC keeps the
    trinket in their pocket: the ruling is that it goes to somebody else.
    """
    party = fight.conscious_party
    for pc in party:
        if fight.token_count(pc, WARDED):
            return pc

    allies = [pc for pc in party if pc is not caster]
    if not allies:
        return None

    holder = min(allies, key=lambda pc: pc.hp_unmarked)
    fight.set_token(holder, WARDED, 1)
    fight.note(f"{caster.name}'s rune ward is held by {holder.name}")
    return holder


def _could_save_an_hp(target, amount: int) -> bool:
    """Whether some result of the Ward Die would drop this hit a threshold band.

    True when the damage is within `WARD_DIE` of a line it would fall below: the
    Severe threshold, the Major threshold, or 1 - that last one being the hit
    disappearing entirely, which marks no HP at all.

    A hit sitting far above a band cannot be moved out of it by eight points, so
    the Hope would buy nothing measurable and isn't spent.
    """
    return any(
        line <= amount < line + WARD_DIE
        for line in (target.severe_threshold, target.major_threshold, 1)
    )


# --- Unleash Chaos -----------------------------------------------------------

UNLEASH_CHAOS = "Unleash Chaos"

CHAOS_TOKENS = "Unleash Chaos tokens"

# Distinguishes "never filled" from "filled and then emptied", which a bare count
# cannot: both read as zero.
CHAOS_PRIMED = "Unleash Chaos primed"

CHAOS_DIE = 10


@action(
    UNLEASH_CHAOS,
    unmodelled=[
        "'within Far range' - no positions are tracked, so this always reaches",
        "'At the beginning of a session' - the simulator has no sessions, so "
        "the card fills to the Spellcast trait at the start of each fight. "
        "Worth revisiting once encounters run in sequence, where a session "
        "would span several of them and the tokens would carry over",
    ],
)
def unleash_chaos(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Unleash Chaos (Arcana, level 1).

    SRD: at the beginning of a session, place tokens equal to your Spellcast
    trait on this card. Make a Spellcast Roll against a target within Far range
    and spend any number of tokens; on a success, roll that many d10s and deal
    that much magic damage. Mark a Stress to replenish the card, up to your
    Spellcast trait.

    SIMULATION RULE - policy, ruled. **Every token goes on every cast**, and the
    card is refilled with a Stress whenever the shared last-slot rule allows it.
    So it opens at full power, empties, and comes back once the caster can afford
    the Stress - rather than trickling out a die at a time.

    The refill needs no threshold of its own: `will_spend_stress` already decides
    when a PC is willing to mark one, which is the same question here as
    everywhere else.

    A caster whose Spellcast trait is zero or less has no tokens to place and no
    card to cast, which the SRD says outright about dice counts drawn from a
    trait. They decline rather than rolling for nothing.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None

    capacity = caster.traits[trait]
    if capacity <= 0:
        return None

    _prime(caster, fight, capacity)

    tokens = fight.token_count(caster, CHAOS_TOKENS)
    if not tokens:
        # Empty, so the Stress is what buys this cast - and it is only marked
        # once we know the cast is going ahead, since declining has to cost
        # nothing.
        if not caster.will_spend_stress(1):
            return None
        caster.spend_stress(1)
        fight.set_token(caster, CHAOS_TOKENS, capacity)
        tokens = capacity
        fight.note(f"{caster.name} marks a Stress to refill Unleash Chaos")

    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    fight.spend_tokens(caster, CHAOS_TOKENS, tokens)

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=tokens, sides=CHAOS_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        is_critical=attack_roll.is_critical,
    )
    marked = target.take_damage(damage_roll.total, fight, damage_type=DamageType.MAGIC)
    fight.note(
        f"{caster.name} unleashes {tokens}d10 of chaos at {target.name} "
        f"for {damage_roll.total}"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


def _prime(caster: Holder, fight: Fight, capacity: int) -> None:
    """Fill the card the first time it is looked at in this fight.

    Two tokens rather than one, because a count of zero has to mean "spent" and
    not "never filled" - and it is the second of those that needs topping up for
    free rather than for a Stress.
    """
    if fight.token_count(caster, CHAOS_PRIMED):
        return
    fight.set_token(caster, CHAOS_PRIMED, 1)
    fight.set_token(caster, CHAOS_TOKENS, capacity)


# --- Cinder Grasp ------------------------------------------------------------

CINDER_GRASP = "Cinder Grasp"

CINDER_GRASP_DIE = 20
CINDER_GRASP_MODIFIER = 3

BURN_DICE = 2
BURN_DIE = 6


@action(
    CINDER_GRASP,
    unmodelled=[
        "'within Melee range' - no positions are tracked, so nothing stops a "
        "caster reaching for a target they could not touch",
    ],
)
def cinder_grasp(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Cinder Grasp (Arcana, level 2).

    SRD: make a Spellcast Roll against a target within Melee range. On a success
    the target bursts into flames, takes 1d20+3 magic damage, and is temporarily
    lit On Fire. When a creature acts while On Fire, they must take an extra 2d6
    magic damage if they are still On Fire at the end of their action.

    **The card prints its own condition in full**, which is why On Fire is
    modelled rather than standing in for something. Every other condition the
    simulator has had to rule on arrived with a name and no mechanic; this one
    states what being On Fire costs, so nothing had to be invented and the burn
    is simply what the page says.

    "Temporarily", on an adversary, is the standing reading: it lasts until the
    GM spends a Fear on their turn to put it out. Which makes this card a
    question the GM has to answer - burn, or pay - and the answer costs them
    either way.

    Never declines. The spell costs nothing but the roll, so there is no state in
    which casting it is worse than not.

    A flat 1d20+3 rather than Proficiency dice: the card doesn't say "using your
    Proficiency", so it doesn't scale.
    """
    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=1, sides=CINDER_GRASP_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=CINDER_GRASP_MODIFIER,
        is_critical=attack_roll.is_critical,
    )
    marked = target.take_damage(damage_roll.total, fight, damage_type=DamageType.MAGIC)

    if not target.is_defeated:
        fight.apply_condition(
            target,
            Condition(
                name=ON_FIRE,
                end=when_the_gm_pays,
                effect=_burns,
                source=caster,
            ),
        )
    fight.note(
        f"{caster.name} sets {target.name} alight for {damage_roll.total} (On Fire)"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


def _burns(holder, fight: Fight, moment: str) -> None:
    """The 2d6 On Fire costs its holder every time they act.

    Announced by the loop at `WHEN_THEY_ACT`, which fires *after* the action has
    resolved on both sides of the table - so "at the end of their action" is
    where this lands, and a creature the GM puts out on their turn has already
    stopped burning by the time it next acts.

    Magic damage, as the card says, so anything resistant to magic takes half of
    it - and an adversary this drops is defeated by the fire rather than by
    anybody's attack.
    """
    if moment != WHEN_THEY_ACT:
        return

    burn = roll_damage(dice_groups=[DiceGroup(count=BURN_DICE, sides=BURN_DIE)])
    holder.take_damage(burn.total, fight, damage_type=DamageType.MAGIC)
    fight.note(f"{holder.name} burns for {burn.total}")


# --- Counterspell ------------------------------------------------------------

COUNTERSPELL = "Counterspell"

# The card's own Recall Cost, printed on the page. What it costs in Stress to
# pull back out of the vault after it has been used.
COUNTERSPELL_RECALL = 2

# Set on the caster once the card is in the vault, so a second interruption has
# to buy it back first.
COUNTERSPELL_VAULTED = "Counterspell vaulted"


@ally_damage_reduction(
    COUNTERSPELL,
    unmodelled=[
        "'a magical effect taking place' in general - nothing marks an adversary "
        "feature as magical, so the only magical effect the simulator can "
        "recognise is an attack that deals **magic damage**. A Fear-fuelled "
        "ritual with no damage on it is not something this can interrupt",
        "The vault itself, beyond this one card. Domain cards have a Recall Cost "
        "and could in principle be swapped mid-fight; nothing models a loadout "
        "changing, and the ruling is that only Counterspell buys itself back",
    ],
)
def counterspell(
    caster: Holder, target, amount: int, fight: Fight, damage_type=None
) -> int:
    """Counterspell (Arcana, level 3). Returns the damage this hit should lose.

    SRD: "You can interrupt a magical effect taking place by making a reaction
    roll using your Spellcast trait. On a success, the effect stops and any
    consequences are avoided, and this card is placed in your vault."

    SIMULATION RULE - rules interpretation, ruled. **A magical effect is an
    incoming attack that deals magic damage.** That is the only kind of magic the
    simulator represents: damage carries a type, and nothing else does. So the
    card interrupts the hit, and "any consequences are avoided" means the whole
    amount - it returns to nothing before thresholds, so no Armor Slot is spent
    either.

    The reaction roll is a real one: Duality Dice on the caster's Spellcast trait
    against **the attacking adversary's own Difficulty**, which is the standing
    rule wherever the SRD prints a roll and no number to beat (see the Giant
    Scorpion's Poison). Who is attacking comes from `fight.spotlighted`, because
    damage arrives without an attacker attached; if nothing is spotlighted the
    magic is the party's own - On Fire burning its holder - and this declines.

    **Party-wide, not just the caster.** The card says "a magical effect taking
    place", not one aimed at you, and it registers on the hook that scans the
    whole party for exactly that reason.

    SIMULATION RULE - policy, ruled. Two decisions, both the user's:

    * Spent on the first magic hit that would mark **2 or more HP**, or on any
      magic hit against a PC already at 2 or fewer unmarked HP. Reads the damage
      announced against that PC's printed thresholds, and nothing else.
    * **The vault is modelled, for this card alone.** Once used the card is gone,
      and the caster can mark its Recall Cost in Stress to pull it back. That is
      the user's ruling: the Recall Cost is a real cost the party can pay
      mid-fight, and for a card this size it is worth paying.
    """
    if fight is None or DamageType.MAGIC not in types_in(damage_type):
        return 0

    attacker = fight.spotlighted
    if attacker is None:
        return 0

    # "Would mark 2 or more HP" read off the announced damage and the target's
    # printed thresholds, which is what a player can see when they decide. Not
    # off the HP the hit finally costs: the free Armor Slot has not been marked
    # yet when this is asked, and it is the PC's own later choice anyway. The
    # same reading Get Back Up takes of "when you take Severe damage".
    if amount < target.major_threshold and not target.is_near_death:
        return 0

    # Checked before anything is paid for: a caster with no Spellcast trait can
    # never make the reaction roll, and must not burn Stress recalling a card
    # they cannot then use.
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return 0

    if fight.token_count(caster, COUNTERSPELL_VAULTED):
        # Vaulted. The Stress is what pulls it back out, and is only marked once
        # the interruption is definitely being attempted.
        if not caster.will_spend_stress(COUNTERSPELL_RECALL):
            return 0
        caster.spend_stress(COUNTERSPELL_RECALL)
        fight.set_token(caster, COUNTERSPELL_VAULTED, 0)
        fight.note(
            f"{caster.name} marks {COUNTERSPELL_RECALL} Stress to recall Counterspell"
        )

    # A Reaction Roll, so it is not offered to the reroll hook and generates
    # neither Hope nor Fear - see SIMULATION-RULES.md. The card is vaulted on the
    # attempt rather than on the success: "this card is placed in your vault" is
    # what casting it costs, and a failed interruption still cast it.
    reaction = roll_duality(
        modifier=caster.traits[trait],
        difficulty=attacker.difficulty,
        hope_die=hope_die_for(caster, fight),
    )
    fight.set_token(caster, COUNTERSPELL_VAULTED, 1)

    if not reaction.is_success:
        fight.note(f"{caster.name}'s counterspell fails ({reaction})")
        return 0

    fight.note(
        f"{caster.name} counterspells {attacker.name}, sparing {target.name} "
        f"{amount} magic damage"
    )
    return amount


# --- Preservation Blast ------------------------------------------------------

PRESERVATION_BLAST = "Preservation Blast"

PRESERVATION_BLAST_DIE = 8
PRESERVATION_BLAST_MODIFIER = 3


@action(
    PRESERVATION_BLAST,
    unmodelled=[
        "'forced back to Far range' - the knockback is half of what the card is "
        "named for and no positions are tracked, so nothing here moves. At a "
        "table this is what buys a caster their next turn",
        "'within Melee range' - the area rule in SIMULATION-RULES.md decides how "
        "many adversaries the blast catches, and nothing stops a Wizard casting "
        "it from a place the card would put them out of reach of",
    ],
)
def preservation_blast(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Preservation Blast (Arcana, level 4).

    SRD: "Make a Spellcast Roll against all targets within Melee range. Targets
    you succeed against are forced back to Far range and take d8+3 magic damage
    using your Spellcast trait."

    One roll against the whole area, each adversary then checked against its own
    Difficulty - the Wild Flame shape rather than the Whirlwind one, which is
    what "all targets within Melee range" asks for.

    **"Using your Spellcast trait" counts the dice**, exactly as "using your
    Proficiency" does elsewhere: the trait is how many d8s are rolled, not
    something added to the total. So a Wizard with a Spellcast trait of 3 throws
    3d8+3. A caster whose trait is zero or less rolls nothing and declines, the
    same reading Unleash Chaos takes of a dice count drawn from a trait.

    Never declines otherwise. The spell costs nothing but the roll the caster was
    making anyway, so there is no state in which casting it is worse than not -
    the Wild Flame reading, not the Fire Flies one, and no minimum number of
    targets is required for it to be worth casting.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None

    dice = caster.traits[trait]
    if dice <= 0:
        return None

    area = targets_in_area(Range.MELEE, fight.living_adversaries)
    if not area:
        return None

    attack_roll = spellcast(caster, target, fight, difficulty=area_difficulty(area))
    if attack_roll is None:
        return None

    caught = targets_beaten(attack_roll, area)
    if not caught:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=dice, sides=PRESERVATION_BLAST_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=PRESERVATION_BLAST_MODIFIER,
        is_critical=attack_roll.is_critical,
    )

    marked = 0
    for adversary in caught:
        marked += adversary.take_damage(
            damage_roll.total, fight, damage_type=DamageType.MAGIC
        )

    fight.note(
        f"{caster.name} looses a preservation blast, catching {len(caught)} "
        f"for {damage_roll.total} each"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


# --- Assessed and dismissed --------------------------------------------------

no_combat_effect(
    "Blink Out",
    "A Spellcast Roll (12), then a Hope teleports the caster to a point within "
    "Close range - and an additional Hope per willing creature brought along. Its "
    "whole effect is where somebody is standing, and no positions are tracked, "
    "which is the standing answer for repositioning content. Worth knowing that "
    "modelling it would make a party *worse*: the cast spends a whole action roll "
    "and up to several Hope to buy nothing here. At a table it is an escape, and "
    "taking the whole party with you is most of the point.",
)
no_combat_effect(
    "Flight",
    "A Spellcast Roll (15) places tokens equal to the caster's Agility, one "
    "spent per action roll while airborne, and the caster comes down when the "
    "last is spent. Being off the ground has no representation here - no "
    "positions are tracked, and nothing in a simulated fight reads altitude, so "
    "there is no roll the state changes. Worth knowing that modelling it would "
    "make a party *worse*, since the cast spends a whole action roll to buy "
    "nothing, which is a second reason not to run it.",
)
no_combat_effect(
    "Wall Walk",
    "A Hope lets a creature climb walls and ceilings as easily as level ground. "
    "Movement, and no positions are tracked - the standing answer for content "
    "whose whole effect is where somebody is standing. It buys a great deal at a "
    "table, and nothing here.",
)
no_combat_effect(
    "Floating Eye",
    "A Hope conjures a small orb the caster can see through, anywhere within Very "
    "Far range. It produces information about places nobody is fighting in. "
    "Nothing about a fight's outcome turns on it, and the orb makes no attack.",
)
