"""Arcana domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json, checked against the printed page
(SRD p. 119), where the Domain Card Reference appendix begins.

Cards from this domain that can't affect a fight are declared at the bottom.

Level 6's **Telekinesis** is the first card anywhere that prints two rolls inside
one action - see its docstring for why the second is rolled plainly rather than
through `content/spellcast.py`.

Level 7 is where every domain prints an *X*-Touched card, gated on holding four
or more of that domain's cards. **Arcana-Touched** is the first, and the user's
ruling is that carrying the card is taken as proof of the loadout - see
SIMULATION-RULES.md. **Cloaking Blast** is the first party content anywhere that
reaches the GM's *targeting* rule: its Cloaked condition says its holder cannot
be aimed at, which is a stronger thing than Hidden and needed
`Condition.untargetable` to say at all.
"""

import random
from dataclasses import replace

from combat.results import AttackResult
from content.aoe import Range, area_difficulty, targets_beaten, targets_in_area
from content.conditions import (
    CLOAKED,
    ON_FIRE,
    WHEN_THEY_ACT,
    Condition,
    when_the_gm_pays,
    when_they_attack,
)
from content.damage_types import DamageType, types_in
from content.registry import (
    Fight,
    Holder,
    action,
    ally_damage_reduction,
    hope_die_for,
    move_rescind,
    no_combat_effect,
    on_roll,
    reroll,
    spellcast_bonus,
    total_extra_damage,
)
from content.spellcast import spellcast
from dice.d20 import roll_d20
from dice.damage import DiceGroup, roll_damage
from dice.duality import DualityOutcome, roll_duality

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
        trait=trait,
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


# --- Chain Lightning ---------------------------------------------------------

CHAIN_LIGHTNING = "Chain Lightning"

CHAIN_LIGHTNING_STRESS = 2
CHAIN_LIGHTNING_DICE = 2
CHAIN_LIGHTNING_DIE = 8
CHAIN_LIGHTNING_MODIFIER = 4

# The card costs a resource beyond the roll, so it waits for a second target -
# the Rain of Blades side of the split rather than the Preservation Blast side,
# where a spell that costs nothing but the roll never declines.
CHAIN_LIGHTNING_MINIMUM_TARGETS = 2


@action(
    CHAIN_LIGHTNING,
    unmodelled=[
        "'all targets within Close range' - no positions are tracked, so the "
        "area rule in SIMULATION-RULES.md decides how many the first burst "
        "catches",
        "'within Close range of previous targets who took damage' - nothing "
        "records who is standing near whom, so each further wave is a fresh "
        "Close draw over the adversaries the lightning has not reached yet. The "
        "shape of the chain at a table - two adversaries beside each other "
        "carrying it into a third across the room - has no representation here",
    ],
)
def chain_lightning(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Chain Lightning (Arcana, level 5).

    SRD: "Mark 2 Stress to make a Spellcast Roll, unleashing lightning on all
    targets within Close range. Targets you succeed against must make a reaction
    roll with a Difficulty equal to the result of your Spellcast Roll. Targets who
    fail take 2d8+4 magic damage. Additional adversaries not already targeted by
    Chain Lightning and within Close range of previous targets who took damage
    must also make the reaction roll. Targets who fail take 2d8+4 magic damage.
    This chain continues until there are no more adversaries within range."

    One Spellcast Roll against the whole area, each adversary checked against its
    own Difficulty - the Wild Flame shape. What is new is the second gate: beating
    an adversary's Difficulty only earns it a **reaction roll**, and the lightning
    lands on the ones that fail it. An adversary's reaction roll is a flat d20 with
    no modifier, since adversaries have no traits, and the Difficulty is the total
    the Spellcast Roll came to - so a big roll both catches more of the area and is
    harder to shrug off.

    SIMULATION RULE - rules interpretation, ruled. **The chain is a fresh Close
    draw per wave.** Whoever the lightning damaged carries it onward, and who is
    near them is the positional question the area rule answers everywhere else, so
    each wave draws `targets_in_area(Range.CLOSE, ...)` again from the adversaries
    it has not reached. Waves continue while the previous one actually dealt
    damage, which is what "until there are no more adversaries within range" comes
    to on a field with no positions in it. Reading it as "everything still alive"
    was offered and declined.

    **The damage is rolled once and reused**, the reading `Adversary.area_attack`
    already takes of one roll landing on several targets - so every adversary the
    chain catches, in every wave, takes the same 2d8+4.

    SIMULATION RULE - policy, ruled. Declines below `CHAIN_LIGHTNING_MINIMUM_TARGETS`
    in the initial band. The 2 Stress is what separates this from Preservation
    Blast, which never declines because it costs nothing the caster wasn't
    spending anyway.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None

    area = targets_in_area(Range.CLOSE, fight.living_adversaries)
    if len(area) < CHAIN_LIGHTNING_MINIMUM_TARGETS:
        return None
    if not caster.will_spend_stress(CHAIN_LIGHTNING_STRESS):
        return None

    # The Stress buys the roll, so it is marked once the cast is definitely going
    # ahead and never on a decline.
    caster.spend_stress(CHAIN_LIGHTNING_STRESS)
    attack_roll = spellcast(caster, target, fight, difficulty=area_difficulty(area))
    if attack_roll is None:
        return None

    beaten = targets_beaten(attack_roll, area)
    if not beaten:
        fight.note(f"{caster.name}'s lightning finds nobody ({attack_roll})")
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=CHAIN_LIGHTNING_DICE, sides=CHAIN_LIGHTNING_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=CHAIN_LIGHTNING_MODIFIER,
        is_critical=attack_roll.is_critical,
    )

    # Held by identity: `Adversary` is a plain dataclass, so two spawned copies of
    # one stat block compare equal and a membership test on the objects would drop
    # the second of a pair from the chain.
    reached = {id(adversary) for adversary in area}
    struck = _shocked(beaten, attack_roll.total, damage_roll.total, fight)
    marked = sum(hit for _, hit in struck)
    fight.note(
        f"{caster.name} looses chain lightning, catching {len(struck)} "
        f"for {damage_roll.total} each"
    )

    while struck:
        onward = [
            adversary
            for adversary in fight.living_adversaries
            if id(adversary) not in reached
        ]
        if not onward:
            break
        wave = targets_in_area(Range.CLOSE, onward)
        reached.update(id(adversary) for adversary in wave)
        struck = _shocked(wave, attack_roll.total, damage_roll.total, fight)
        marked += sum(hit for _, hit in struck)
        if struck:
            fight.note(f"The lightning arcs onward into {len(struck)} more")

    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


def _shocked(targets: list, difficulty: int, damage: int, fight: Fight) -> list:
    """Which of `targets` fail the reaction roll, and what the lightning cost them.

    A flat d20 against `difficulty` per adversary - no modifier, since adversaries
    have no traits to roll and the SRD's reaction rolls for them are exactly that.
    The Difficulty is passed as `evasion` on purpose; see `dice/d20.py`, which
    keeps that name for the number a d20 has to beat whatever it is called on the
    other side of the table.

    Returns pairs rather than bare adversaries because the caller needs the HP the
    chain marked in total, and asking each target again afterwards would not say.
    """
    caught = []
    for adversary in targets:
        if roll_d20(evasion=difficulty).is_success:
            fight.note(f"{adversary.name} shrugs off the lightning")
            continue
        caught.append(
            (adversary, adversary.take_damage(damage, fight, damage_type=DamageType.MAGIC))
        )
    return caught


# --- Premonition -------------------------------------------------------------

PREMONITION = "Premonition"


@move_rescind(
    PREMONITION,
    unmodelled=[
        "'immediately after the GM conveys the consequences of a roll you made' "
        "reaches a **failed** move only. A success with Fear has consequences "
        "conveyed too, and its damage has already landed - the simulator cannot "
        "un-deal it, so that half of the trigger is out of reach",
        "'like they never happened' does not refund what the rescinded move "
        "spent. Stress marked and Hope paid for the first attempt are gone; only "
        "the move itself is taken back. Refunding was offered and would mean "
        "every option reporting what it cost, which nothing does",
        "Rolls made outside the spotlight's one move - a Reaction Roll, a "
        "Counterspell - are not offered to this hook, so a vision cannot rescue "
        "one of those",
    ],
)
def premonition(holder: Holder, roll, fight: Fight) -> bool:
    """Premonition (Arcana, level 5). Whether the move that just failed is taken back.

    SRD: "You can channel arcane energy to have visions of the future. Once per
    long rest, immediately after the GM conveys the consequences of a roll you
    made, you can rescind the move and consequences like they never happened and
    make another move instead."

    SIMULATION RULE - rules interpretation, ruled. **A move, not a roll.** The
    simulator already had a hook that re-throws the dice of a roll that resolved -
    Luckbender and Adaptability both use it - and registering here instead is the
    difference between "cast that again" and "do something else". Rescinding sends
    the PC back through the whole spotlight, options shuffled afresh, so a Wizard
    whose Cinder Grasp missed may swing their staff the second time.

    **The consequences that can be taken back are a failure's.** The move's Hope
    or Fear outcome is spent by the loop after the move returns, so a rescinded
    failure costs the party nothing - no Fear handed over, no spotlight passed.
    That is the whole of what the card buys here, and it is a large thing: a roll
    with Fear is how the GM's turn arrives.

    No policy of its own to rule on. The card has one trigger, one use per long
    rest, and no cost, so it fires on the first move of the fight that fails -
    holding it back would mostly mean not using it, which is the Deadly Focus
    reading of a free once-per-rest.
    """
    if fight is None or roll is None or roll.is_success:
        return False
    if not fight.use_once_per_rest(holder, PREMONITION, long=True):
        return False

    fight.note(f"{holder.name} foresaw this, and the move is unmade ({roll})")
    return True


# --- Telekinesis -------------------------------------------------------------

TELEKINESIS = "Telekinesis"

TELEKINESIS_DIE = 12
TELEKINESIS_MODIFIER = 4

# The card needs somebody to pick up *and* somebody to throw them at. On a field
# of one there is no second target, and the lift alone buys only a change of
# position - which nothing here represents.
TELEKINESIS_MINIMUM_TARGETS = 2


@action(
    TELEKINESIS,
    unmodelled=[
        "'move them anywhere within Far range of their original position' - the "
        "whole of what the first roll buys on its own is where the lifted "
        "adversary ends up, and no positions are tracked. Only the throw reaches "
        "the fight, which is why the card declines when there is nobody to throw "
        "them at",
        "'against a target within Far range', twice - no positions are tracked, "
        "so both the lift and the throw always reach",
        "The additional Spellcast Roll is rolled on the caster's Spellcast trait "
        "alone. Content bonuses, an ally's Help and a swapped Hope Die are all "
        "hooks whose contract is that **being asked is the commitment**, and "
        "asking them a second time inside one action would charge for them twice "
        "- so the throw gets none of them",
        "The throw's roll produces neither Hope nor Fear and is not offered to "
        "the party's reroll content. A spotlight resolves into one action with "
        "one duality outcome and the loop spends the lift's; the throw is a roll "
        "made inside that action, the way a Reaction Roll is",
    ],
)
def telekinesis(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Telekinesis (Arcana, level 6). Pick one adversary up and throw it at another.

    SRD: "Make a Spellcast Roll against a target within Far range. On a success,
    you can use your mind to move them anywhere within Far range of their original
    position. You can throw the lifted target as an attack against the second
    target by making an additional Spellcast Roll. On a success, deal d12+4
    physical damage to the second target using your Proficiency. This spell then
    ends."

    Two rolls in one action, and they are made against **different** adversaries:
    the first against whoever is being lifted, the second against whoever they are
    thrown at. Only the second takes damage - the lifted adversary is the
    projectile and the card gives it nothing.

    "Using your Proficiency" counts the dice, as it does everywhere else, so a
    Proficiency 3 caster throws 3d12+4. Physical damage, which is what the page
    says: a Wizard hitting somebody with a Wizard is not magic.

    SIMULATION RULE - policy, ruled. Two decisions:

    * **The throw goes at the party's focus** - `target`, whoever the party's own
      targeting rule already picked - so the damage lands where every other card
      puts it.
    * **The adversary lifted is the one with the lowest printed Difficulty**,
      chosen at random among ties. The first roll is made against *its* Difficulty
      and nothing else about it matters, so grabbing the easiest thing to grab is
      the choice a table makes. That reads a number printed on a stat block, not
      a statistic anybody has to work out.

    Declines below `TELEKINESIS_MINIMUM_TARGETS` living adversaries. The card
    costs no Stress and no Hope, so this is not the Rain of Blades gate - it is
    that the spell has no second half to resolve, and the first half is
    positioning.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None
    if caster.proficiency <= 0:
        return None

    living = fight.living_adversaries
    if len(living) < TELEKINESIS_MINIMUM_TARGETS:
        return None

    others = [adversary for adversary in living if adversary is not target]
    if not others:
        return None

    # Ties broken by a draw rather than by list order: which of two equally easy
    # adversaries gets picked up must not be decided by the order a catalogue
    # happened to list them in.
    easiest = min(adversary.difficulty for adversary in others)
    lifted = random.choice(
        [adversary for adversary in others if adversary.difficulty == easiest]
    )

    grab = spellcast(caster, lifted, fight)
    if grab is None:
        return None
    if not grab.is_success:
        fight.note(f"{caster.name} reaches for {lifted.name} and can't lift them")
        return AttackResult(attack_roll=grab, damage_roll=None)

    # The additional Spellcast Roll. Rolled here rather than through
    # `content/spellcast.py` on purpose - see the declared gaps: that helper asks
    # three commitment hooks, and this is the second roll of one action.
    throw = roll_duality(
        modifier=caster.traits[trait], difficulty=target.difficulty, trait=trait
    )
    if not throw.is_success:
        fight.note(
            f"{caster.name} hurls {lifted.name} at {target.name} and misses ({throw})"
        )
        return AttackResult(attack_roll=grab, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=caster.proficiency, sides=TELEKINESIS_DIE)]
        # Asked with the **throw**, since that is the roll that landed - content
        # keying on how an attack came out is asking about the one that hit.
        + total_extra_damage(caster, target, throw, fight),
        modifier=TELEKINESIS_MODIFIER,
        is_critical=throw.is_critical,
    )
    marked = target.take_damage(
        damage_roll.total, fight, damage_type=DamageType.PHYSICAL
    )
    fight.note(
        f"{caster.name} throws {lifted.name} into {target.name} "
        f"for {damage_roll.total}"
    )
    return AttackResult(
        attack_roll=grab, damage_roll=damage_roll, hp_marked=marked
    )


# --- Arcana-Touched --------------------------------------------------------------

ARCANA_TOUCHED = "Arcana-Touched"

ARCANA_TOUCHED_SPELLCAST = 1

# The gap every *X*-Touched card carries, written once here and repeated on the
# other two in this batch. See SIMULATION-RULES.md for the ruling.
TOUCHED_LOADOUT_GAP = (
    "'When 4 or more of the domain cards in your loadout are from this domain' - "
    "the loadout is not counted. The user's ruling is that carrying the card is "
    "taken as proof the condition is met, since a player who takes it has built "
    "for it. Recorded as a simulation rule rather than checked, and it errs "
    "generous: a sheet naming the card in a mixed loadout runs it anyway"
)


@spellcast_bonus(ARCANA_TOUCHED, unmodelled=[TOUCHED_LOADOUT_GAP])
def arcana_touched(caster: Holder, target, fight: Fight = None) -> int:
    """Arcana-Touched (Arcana, level 7), first clause.

    SRD: "When 4 or more of the domain cards in your loadout are from the Arcana
    domain, gain the following benefits: +1 bonus to your Spellcast Rolls; once
    per rest, you can switch the results of your Hope and Fear Dice."

    **Spellcast Rolls and nothing else**, which is why this is on a hook of its
    own rather than on `roll_bonus`: that one is asked from the weapon swing too,
    and an Arcana caster who picks up a Broadsword should not be swinging it at
    +1. See `spellcast_bonus`.

    No policy - it costs nothing, has no limit and is simply on.
    """
    return ARCANA_TOUCHED_SPELLCAST


@reroll(
    ARCANA_TOUCHED,
    unmodelled=[
        TOUCHED_LOADOUT_GAP,
        "The **die sizes** are not swapped with the results, only the results "
        "themselves, which is what the card says. It can only matter alongside "
        "Bone's Signature Move, the one thing that makes the two dice different "
        "sizes - and there the swap is still safe, since a roll with Fear has the "
        "smaller number on the Hope Die",
    ],
)
def arcana_touched_switches(
    holder: Holder, roller: Holder, roll, remake, fight: Fight = None
):
    """Arcana-Touched's second clause - the Hope and Fear Dice traded over.

    SRD: "Once per rest, you can switch the results of your Hope and Fear Dice."

    **The total does not move**, since it is the two dice added together, so
    whether the roll succeeded is untouched. What changes is the *outcome*: a roll
    with Fear becomes a roll with Hope. That is worth more than it looks - it
    decides whether the PC banks a Hope or the GM banks a Fear, and whether the
    party keeps the spotlight at all.

    Registered on the `reroll` hook because that is the one place a resolved roll
    can be replaced, and `remake` is deliberately unused: this is Support Tank's
    shape, rewriting fields of the roll that was made rather than throwing fresh
    dice. Scoped to its own holder with `holder is roller` - the card says *your*
    dice.

    SIMULATION RULE - policy, ruled. Spent on a **successful** roll with Fear.
    That is where the switch buys the most: the party keeps the spotlight *and*
    the Hope goes to the PC instead of the Fear going to the GM. Spending it on
    any roll with Fear was offered and declined - on a failure the spotlight
    passes regardless, so the switch is worth one Hope and one Fear rather than a
    whole extra action for the party.
    """
    if fight is None or holder is not roller or roll is None:
        return None
    if not roll.is_success or roll.outcome is not DualityOutcome.FEAR:
        return None
    if not fight.use_once_per_rest(holder, ARCANA_TOUCHED):
        return None

    switched = replace(
        roll,
        hope_die_result=roll.fear_die_result,
        fear_die_result=roll.hope_die_result,
    )
    fight.note(
        f"{holder.name} switches their dice; the roll comes up with Hope ({switched})"
    )
    return switched


# --- Cloaking Blast --------------------------------------------------------------

CLOAKING_BLAST = "Cloaking Blast"

# Set while a cast is in flight, so the on-roll hook can tell a Spellcast Roll
# from a weapon swing - which is the only thing it needs and the only thing it
# cannot otherwise see. Cleared by that hook whichever way the roll came out.
CASTING = "Cloaking Blast cast in flight"


@spellcast_bonus(CLOAKING_BLAST)
def cloaking_blast_watches(caster: Holder, target, fight: Fight = None) -> int:
    """Marks that a Spellcast Roll is being made, and adds nothing to it.

    A bonus hook used as a *notice*, which is worth being plain about: this is
    asked from `content/spellcast.py` and nowhere else, so being asked is exactly
    the fact the card's trigger needs - "when you make a successful Spellcast Roll
    to cast a different spell". `on_roll` fires for every action roll a PC makes
    and could not tell a cast from a swing.

    Returns 0 always. The card grants no bonus; it only needs to know.

    "A **different** spell" comes for free: Cloaking Blast is a rider rather than
    a spell of its own, so it never casts anything and the roll being watched is
    always somebody else's spell.
    """
    if fight is not None:
        fight.set_token(caster, CASTING, 1)
    return 0


@on_roll(
    CLOAKING_BLAST,
    unmodelled=[
        "'You remain unseen if you are stationary when an adversary moves to "
        "where they would normally see you', and 'when you move into or within "
        "an adversary's line of sight' - both halves are position and line of "
        "sight, neither of which is tracked. What is modelled is the user's "
        "ruling on what being Cloaked is worth: the holder cannot be targeted "
        "until they attack",
        "A cloak on the **whole party** at once would leave an adversary with "
        "nobody to swing at; `combat/policy.py` hands back the full list rather "
        "than nothing, so the last cloak in such a party protects nobody. No card "
        "can reach that state today",
        "A move taken back by Premonition never reaches this hook, so the token "
        "the cast left behind survives into the second attempt - a rescinded cast "
        "followed by a weapon swing would cloak off the swing",
        "'When you ... make an attack, you are no longer Cloaked' is read as any "
        "spotlight that resolved into an **action roll**, because that is all the "
        "loop can see - `AttackResult.made_an_attack` means 'this action rolled'. "
        "So a spotlight spent on Healing Hands or Zone of Protection breaks the "
        "cloak as well as one spent swinging. It errs the conservative way: the "
        "cloak ends sooner than the page would have it, never later",
    ],
)
def cloaking_blast(holder: Holder, roll, fight: Fight) -> None:
    """Cloaking Blast (Arcana, level 7). A Hope buys a spell-caster one turn unseen.

    SRD: "When you make a successful Spellcast Roll to cast a different spell, you
    can spend a Hope to become *Cloaked*. While Cloaked, you remain unseen if you
    are stationary when an adversary moves to where they would normally see you.
    When you move into or within an adversary's line of sight or make an attack,
    you are no longer Cloaked."

    SIMULATION RULE - rules interpretation, ruled. **Cloaked means the holder
    cannot be targeted**, until their next attack. The printed text is line of
    sight and standing still, neither of which has any representation here, so the
    user ruled the effect rather than the fiction - and ruled it **stronger than
    Hidden**, which the simulator already models as Disadvantage on rolls against
    its holder. It is the first thing on the party's side to reach the GM's
    targeting rule, through `Condition.untargetable`.

    SIMULATION RULE - policy. The Hope is spent whenever there is one to spend and
    no cloak already stands, which is the standing default for a rider with a
    single-Hope cost - Forceful Push's rule. No threshold of its own: one Hope for
    a GM turn out of reach is not the shape of price Life Ward's gate exists for,
    and there is no later cast worth saving it for.

    The cloak is applied **after** the moment that would break it is announced -
    see `combat/fight.py` - so a cloak raised off an attack spell survives that
    spell and breaks on the caster's next action roll. What counts as "an attack"
    there is the loop's approximation rather than the card's word; the gap above
    says so.
    """
    if fight is None or not fight.token_count(holder, CASTING):
        return

    # Cleared whichever way the roll went, so a failed cast cannot leave a mark
    # that a later weapon swing would read as a cast of its own.
    fight.set_token(holder, CASTING, 0)

    if roll is None or not roll.is_success:
        return
    if fight.has_condition(holder, CLOAKED) or not holder.can_spend_hope(1):
        return

    holder.spend_hope(1)
    fight.apply_condition(
        holder,
        Condition(
            name=CLOAKED,
            end=when_they_attack,
            source=holder,
            untargetable=True,
        ),
    )
    fight.note(f"{holder.name} spends a Hope and vanishes behind their own spell")


# --- Assessed and dismissed --------------------------------------------------

no_combat_effect(
    "Rift Walker",
    "A Spellcast Roll (15) plants an arcane marking where the caster stands; the "
    "next successful cast opens a rift back to it, and the rift stays open until "
    "it is closed or another spell is cast. Its whole effect is safe passage to a "
    "spot on the ground, and no positions are tracked - the standing answer for "
    "content whose effect is where somebody is standing, the same one Blink Out, "
    "Flight and Teleport already have. At a table it is an escape route prepared "
    "in advance, which is most of what an Arcana caster spends level 6 on.",
)
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
