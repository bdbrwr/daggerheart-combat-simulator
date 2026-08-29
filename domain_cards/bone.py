"""Bone domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json, checked against the printed page
(SRD pp. 122-123).

Bone is the Evasion domain, and three of its five level 1-2 cards are about not
being hit. That turned out to be the interesting thing: Evasion is a number a
character sheet carries already resolved, and until *Ferocity* nothing could
change it once a fight had started.

Level 3 adds the two cards that reach *other* people's rolls and other people's
armor: Tactician is the first content anywhere that belongs to a PC helping
somebody else, and Brace is the first that spends more than the one free Armor
Slot the damage rule already marks.

Level 5's **Signature Move** is the first content anywhere to swap the party's
Hope Die - the `hope_die` hook has existed since the Faerie and no domain card
had ever registered on it.
"""

import random

from combat.results import AttackResult
from content.aoe import Range, chance_within, targets_in_area
from content.registry import (
    Fight,
    Holder,
    action,
    attack_missed,
    evasion_bonus,
    extra_armor_slot,
    extra_damage,
    help_bonus,
    hope_die,
    hope_die_for,
    insignificant_combat_effect,
    no_combat_effect,
    on_hit,
    on_roll,
    total_damage_bonus,
    total_roll_bonus,
)
from content.rolls import EXPERIENCE_HOPE_FLOOR
from dice.common import AdvantageState
from dice.damage import DiceGroup, roll_damage
from items.registry import find_weapon
from items.weapons import attack_with

BRACE = "Brace"
TACTICIAN = "Tactician"

# --- Ferocity ----------------------------------------------------------------

FEROCITY = "Ferocity"
FEROCITY_HOPE = 2

# The bonus waiting to be spent on the next attack, as a number rather than a
# count - `set_token` exists for exactly this.
FEROCITY_BONUS = "Ferocity bonus"


@on_hit(FEROCITY)
def ferocity(attacker: Holder, target, result, fight: Fight) -> None:
    """Ferocity (Bone, level 2). Buy Evasion with the damage you just did.

    SRD: when you cause an adversary to mark 1 or more Hit Points, you can spend
    2 Hope to increase your Evasion by the number of Hit Points they marked. This
    bonus lasts until after the next attack made against you.

    SIMULATION RULE - policy, ruled. Spent **whenever the 2 Hope can be paid**,
    which is the standing default. Worth being clear that this is not the
    imperfect-information case the Faerie's Wings is: the choice is made when
    your own hit lands, before any attack comes back, so nothing here reads a
    roll a player couldn't see. It does mean the common case is 2 Hope for +1
    Evasion against one attack.

    Keyed on HP **marked**, not damage dealt - `result.hp_marked` is what the hit
    finally cost after thresholds, an Armor Slot and any resistance, which is
    what the card asks for.
    """
    if result.hp_marked < 1:
        return
    if not attacker.can_spend_hope(FEROCITY_HOPE):
        return

    attacker.spend_hope(FEROCITY_HOPE)
    fight.set_token(attacker, FEROCITY_BONUS, result.hp_marked)
    fight.note(
        f"{attacker.name} spends 2 Hope on Ferocity (+{result.hp_marked} Evasion)"
    )


@evasion_bonus(
    FEROCITY,
    unmodelled=[
        "An adversary's **area** attack doesn't consult the bonus - that "
        "resolves one roll against the lowest Evasion on the field and then "
        "re-checks each target, and a per-target bonus can't reach into that. "
        "So Ferocity protects against single-target attacks only",
    ],
)
def ferocity_evades(holder: Holder, attacker, fight: Fight) -> int:
    """The bonus Ferocity bought, spent on the attack now being rolled.

    "Until after the next attack made against you" - so it applies to this attack
    and is gone afterwards, which is why the token is cleared here rather than
    waiting for something to notice the attack happened. Being asked is the
    commitment; see `evasion_bonus`.
    """
    if fight is None:
        return 0

    bonus = fight.token_count(holder, FEROCITY_BONUS)
    if not bonus:
        return 0

    fight.set_token(holder, FEROCITY_BONUS, 0)
    return bonus


# --- Strategic Approach ------------------------------------------------------

STRATEGIC_APPROACH = "Strategic Approach"

STRATEGIC_TOKENS = "Strategic Approach tokens"
STRATEGIC_PRIMED = "Strategic Approach primed"

# Marks an adversary this PC has already opened on. Keyed per adversary, since
# the card's trigger is the first attack against *each* of them.
STRATEGIC_OPENED = "Strategic Approach opened"

STRATEGIC_DIE = 8


@extra_damage(
    STRATEGIC_APPROACH,
    unmodelled=[
        "The other two options the card offers - making the attack with "
        "Advantage, and clearing a Stress on an ally within Melee range of the "
        "adversary. Ruled: the token always buys the d8, since it is the one "
        "option always available and needs no judgement",
        "'the first time you move within Close range of an adversary' - no "
        "positions are tracked, so the trigger is read as the first attack "
        "against each adversary",
    ],
)
def strategic_approach(attacker: Holder, target, roll, fight: Fight = None) -> list:
    """Strategic Approach (Bone, level 2). A d8 on your opening blow.

    SRD: after a long rest, place tokens equal to your Knowledge on this card
    (minimum 1). The first time you move within Close range of an adversary and
    make an attack against them, spend one token to make the attack with
    advantage, clear a Stress on an ally within Melee range of the adversary, or
    add a d8 to your damage roll.

    SIMULATION RULE - policy, ruled. **The token always buys the d8.** It is the
    only one of the three that is always available - Advantage has to be decided
    before the roll this hook is asked after, and clearing an ally's Stress needs
    an ally with Stress marked - and it needs no judgement about which is worth
    more.

    SIMULATION RULE - rules interpretation. Asked from inside the damage roll, so
    a **missed** attack neither spends a token nor counts as having opened on
    that adversary. "The first time you make an attack against them" reads either
    way; this one keeps the token for a blow that lands, which is the same
    reading Parallela already gets.

    `discardable=False`, like every die a feature adds to somebody else's roll: a
    Massive or Powerful weapon discards the lowest of the dice *it* rolled, and
    this is not one of them.
    """
    if fight is None:
        return []

    _prime(attacker, fight)

    opened = f"{STRATEGIC_OPENED}:{id(target)}"
    if fight.token_count(attacker, opened):
        return []
    if not fight.spend_tokens(attacker, STRATEGIC_TOKENS, 1):
        return []

    fight.set_token(attacker, opened, 1)
    fight.note(f"{attacker.name} opens on {target.name} with Strategic Approach")
    return [DiceGroup(count=1, sides=STRATEGIC_DIE, discardable=False)]


def _prime(attacker: Holder, fight: Fight) -> None:
    """Place the card's tokens the first time it is looked at in this fight.

    "After a long rest, place a number of tokens equal to your Knowledge on this
    card (minimum 1)" - so a party that did **not** long rest walks in with the
    card empty. That follows the standing rule for a no-rest encounter: nothing
    carries between fights yet, so every per-rest resource is assumed already
    spent.

    The rest is asked through `can_use_once_per_rest`, which answers
    "did this party take a long rest?" without anything being spent - the key is
    never claimed. Indirect, but the alternative is putting `rest` on the `Fight`
    protocol for one card.

    Two tokens rather than one, because a count of zero has to mean "spent" and
    not "never placed".
    """
    if fight.token_count(attacker, STRATEGIC_PRIMED):
        return
    fight.set_token(attacker, STRATEGIC_PRIMED, 1)

    if not fight.can_use_once_per_rest(attacker, STRATEGIC_APPROACH, long=True):
        return
    fight.set_token(attacker, STRATEGIC_TOKENS, max(attacker.traits["knowledge"], 1))


# --- Brace -------------------------------------------------------------------


@extra_armor_slot(BRACE)
def brace(
    holder: Holder, amount: int, hp_to_mark: int, fight: Fight = None, damage_type=None
) -> int:
    """Brace (Bone, level 3). Returns how many further Armor Slots to mark.

    SRD: "When you mark an Armor Slot to reduce incoming damage, you can mark a
    Stress to mark an additional Armor Slot."

    Being asked at all means the first slot has already gone in - that is the
    contract of the hook, and it is the card's trigger read literally. So this
    never fires against direct damage, and never against a hit that arrived at a
    PC with no slots left.

    SIMULATION RULE - policy, ruled. The Stress is paid **only when the extra
    slot would actually save an HP**, which is `hp_to_mark > 0`: the free slot
    has already taken a band off, and if that left the hit marking nothing then
    a second slot buys nothing either. That is the Rune Ward reading, and it
    reads only what a player can see when they decide - the damage the GM
    announced, and their own printed thresholds.

    The `will_spend_stress` check is the shared last-slot rule, as every PC
    Stress cost is: freely while a spare slot remains, and the last only once the
    PC is at 2 or fewer unmarked HP.

    `amount` and `damage_type` are unused - the card names neither a threshold
    nor a type, so it answers for any hit that got past the first slot. They are
    in the signature because the hook is generic and other content could key on
    either.
    """
    if hp_to_mark <= 0:
        return 0
    if not holder.will_spend_stress(1):
        return 0

    holder.spend_stress(1)
    if fight is not None:
        fight.note(f"{holder.name} braces, marking a Stress for a second Armor Slot")
    return 1


# --- Tactician ---------------------------------------------------------------


@help_bonus(
    TACTICIAN,
    unmodelled=[
        "'When making a Tag Team Roll, you can roll a d20 as your Hope Die' - "
        "Tag Team Rolls are not modelled. They cost 3 Hope, are limited to one "
        "per player per session, and resolve *two* PCs' actions off one chosen "
        "roll, which the spotlight loop has no shape for - a spotlight resolves "
        "into exactly one action. A known gap rather than a dismissal",
    ],
)
def tactician(helper: Holder, roller: Holder, fight: Fight = None) -> int:
    """Tactician (Bone, level 3). Returns what the helper's Experience adds.

    SRD: "When you Help an Ally, they can spend a Hope to add one of your
    Experiences to their roll alongside your advantage die. When making a Tag
    Team Roll, you can roll a d20 as your Hope Die."

    The first clause only. Note whose Hope pays: the **roller's**, not the
    helper's - the helper has already spent theirs on the advantage die by the
    time this is asked, and the card charges the ally receiving the Experience.

    Which Experience is the helper's best, on the same assumption
    `combat/policy.py` makes when a PC buys their own: which Experience applies
    to a given moment is a fiction call a simulator cannot make, so one always
    does. That assumption is optimistic in both places, and the Hope floor below
    is set high partly because of it.

    SIMULATION RULE - policy. The roller pays only while their Hope is
    plentiful - `EXPERIENCE_HOPE_FLOOR`, the same number that decides whether an
    ally helps at all and whether a PC buys their own Experience. Extending the
    user's Help an Ally ruling to the third Hope this move can cost, on their own
    reasoning for it: one constant read everywhere rather than several that could
    drift. Worth overruling if a Tactician should lend more freely than that.

    Returns 0 rather than declining loudly when the helper has no Experiences at
    all, which is a legal sheet.
    """
    if not helper.experiences:
        return 0
    if roller.hope_marked < EXPERIENCE_HOPE_FLOOR or not roller.can_spend_hope(1):
        return 0

    bonus = max(experience["modifier"] for experience in helper.experiences)
    if bonus <= 0:
        return 0

    roller.spend_hope(1)
    if fight is not None:
        fight.note(
            f"{roller.name} spends a Hope on {helper.name}'s Experience (+{bonus})"
        )
    return bonus


# --- Boost -------------------------------------------------------------------

BOOST = "Boost"

BOOST_DIE = 10

# Set for the length of the one attack the card buys, so the d10 joins that
# damage roll and no other. A token rather than a flag on the holder because
# everything content remembers about a fight lives on the fight.
BOOST_AERIAL = "Boost aerial attack"


@action(
    BOOST,
    unmodelled=[
        "'end your move within Melee range of the target' - the card lands the "
        "holder in melee, which at a table is most of what it costs. No positions "
        "are tracked, so nothing here changes about where they are afterwards",
        "'against a target within Far range' - no positions are tracked, so the "
        "boost always reaches whoever the party is focusing",
    ],
)
def boost(holder: Holder, target, fight: Fight) -> AttackResult | None:
    """Boost (Bone, level 4). Mark a Stress, vault off an ally, come down hard.

    SRD: "Mark a Stress to boost off a willing ally within Close range, fling
    yourself into the air, and perform an aerial attack against a target within
    Far range. You have advantage on the attack, add a d10 to the damage roll,
    and end your move within Melee range of the target."

    A weapon swing with two things bolted on, so it *is* the weapon swing -
    `attack_with`, with Advantage passed in and a d10 riding along. Everything a
    normal swing consults still applies, which is the point of routing it through
    the shared attack shape rather than rolling something of its own.

    **The ally is answered by the area rule.** "A willing ally within Close
    range" is a question about where somebody is standing, and the standing
    answer for those is `chance_within` over the rest of the party rather than
    "is there another PC at all". So a Bone character in a party of four finds
    somebody to vault off most of the time and not every time, and alone they
    never do.

    SIMULATION RULE - policy. Nothing to rule on beyond the standing default:
    taken whenever the Stress can be paid, by the shared last-slot rule that
    every PC Stress cost uses. The card asks for no judgement - Advantage and an
    extra d10 are better than a plain swing on any roll - so what limits it is
    the Stress track and nothing else.

    The Experience is deliberately not bought here. `combat/policy.py` spends that
    Hope inside the weapon option only, so a card taking the roll instead never
    charges for one; this card is no different.
    """
    if fight is None:
        return None

    carried = getattr(holder, "primary_weapon", "")
    if not carried:
        return None

    allies = [pc for pc in fight.conscious_party if pc is not holder]
    if not allies:
        return None
    if random.random() >= chance_within(Range.CLOSE, len(allies)):
        return None

    if not holder.will_spend_stress(1):
        return None
    holder.spend_stress(1)
    fight.note(f"{holder.name} boosts off an ally and comes down on {target.name}")

    fight.set_token(holder, BOOST_AERIAL, 1)
    try:
        return attack_with(
            holder,
            find_weapon(carried),
            target,
            AdvantageState.ADVANTAGE,
            total_roll_bonus(holder, target, fight),
            total_damage_bonus(holder, target, fight),
            hope_die_for(holder, fight),
            fight,
        )
    finally:
        # Cleared whether the attack hit, missed or raised: the d10 belongs to
        # this one swing, and a miss must not leave it waiting for the next.
        fight.set_token(holder, BOOST_AERIAL, 0)


@extra_damage(BOOST)
def boost_from_above(holder: Holder, target, roll, fight: Fight = None) -> list:
    """The d10 the aerial attack adds, and only on that attack.

    Registered on the same name as the action above, which is how one card
    reaches two hooks - the arrangement Ferocity already uses for its on-hit and
    its Evasion halves. `boost` sets the token immediately before calling
    `attack_with`, and `attack_with` asks this from inside the damage roll, so
    the die joins that roll and crosses the target's thresholds once.

    `discardable=False`, like every die a feature adds to somebody else's roll.
    """
    if fight is None or not fight.token_count(holder, BOOST_AERIAL):
        return []
    return [DiceGroup(count=1, sides=BOOST_DIE, discardable=False)]


# --- Redirect ----------------------------------------------------------------

REDIRECT = "Redirect"

REDIRECT_DIE = 6
REDIRECT_FACE = 6


@attack_missed(
    REDIRECT,
    unmodelled=[
        "An adversary's **area** attack. Only the PC the attack was aimed at is "
        "announced as having been missed, so a swept attack that failed against "
        "several can be redirected by at most one of them",
    ],
)
def redirect(holder: Holder, attacker, roll, fight: Fight = None) -> None:
    """Redirect (Bone, level 4). Send a failed attack into somebody else.

    SRD: "When an attack made against you from beyond Melee range fails, roll a
    number of d6s equal to your Proficiency. If any roll a 6, you can mark a
    Stress to redirect the attack to damage an adversary within Very Close range
    instead."

    **"From beyond Melee range" is read off the attacker's printed band**, which
    is a number on the stat block rather than a position - `Adversary.range` is
    "Claws: Melee" or "Warp Blast: Close", and the card is asking which. So this
    answers a positional clause without any positions, and a Melee adversary is
    correctly never redirected.

    SIMULATION RULE - rules interpretation. The attacker is **excluded** from the
    adversaries the attack can be turned onto. The card's own setup is that the
    attack came from beyond Melee range while the new victim is within Very
    Close, and the alternative reading - a shot bouncing straight back at whoever
    fired it - would make the card better against exactly the adversaries it is
    written to punish. Which of the rest is the most wounded one, following the
    party's focus-fire rule.

    The redirected attack deals the attacker's **printed** damage, typed as the
    stat block types it. There is no roll to make: the attack already resolved,
    and what this card changes is who it lands on rather than whether it lands.

    SIMULATION RULE - policy. A Reaction, so the standing rule applies - it fires
    whenever its trigger happens and the cost can be paid, with no desperation
    gate. The Stress is the shared last-slot rule, as every PC Stress cost is.

    The d6s are rolled **after** the cheap checks rather than before, which the
    card's own order does not require and which changes nothing: a 6 that nobody
    could pay for and no adversary could receive buys the same nothing either
    way.
    """
    if fight is None or holder.proficiency <= 0:
        return
    if attacker.attack_band is Range.MELEE:
        return
    if not holder.will_spend_stress(1):
        return

    others = [
        adversary for adversary in fight.living_adversaries if adversary is not attacker
    ]
    nearby = targets_in_area(Range.VERY_CLOSE, others)
    if not nearby:
        return

    rolled = [random.randint(1, REDIRECT_DIE) for _ in range(holder.proficiency)]
    if REDIRECT_FACE not in rolled:
        return

    holder.spend_stress(1)
    victim = nearby[0]
    damage = roll_damage(
        dice_groups=attacker.damage_dice, modifier=attacker.damage_modifier
    )
    victim.take_damage(
        damage.total, fight, damage_type=attacker.type_of_damage()
    )
    fight.note(
        f"{holder.name} redirects {attacker.name}'s attack into {victim.name} "
        f"for {damage.total}"
    )


# --- Signature Move ----------------------------------------------------------

SIGNATURE_MOVE = "Signature Move"

# The die that replaces the d12 Hope Die. Also what identifies the roll
# afterwards - see `signature_move_clears`.
SIGNATURE_MOVE_DIE = 20


@hope_die(
    SIGNATURE_MOVE,
    unmodelled=[
        "'as part of an action you're taking' - `hope_die_for` is asked wherever "
        "Duality Dice are rolled, and a PC's **Reaction Rolls** (Counterspell, "
        "Repudiate) are among those sites. Nothing there distinguishes an action "
        "roll from a reaction, so a Reaction Roll can claim the per-rest use. The "
        "d20 still helps that roll; what is lost is the Stress, since the clear "
        "below only ever fires on the spotlight's action roll",
        "Naming and describing the move is fiction with no mechanic attached, so "
        "nothing here records what the move is",
    ],
)
def signature_move(holder: Holder, fight: Fight) -> int | None:
    """Signature Move (Bone, level 5). A d20 in place of the Hope Die.

    SRD: "Name and describe your signature combat move. Once per rest, when you
    perform this signature move as part of an action you're taking, you can roll a
    **d20** as your Hope Die. On a success, clear a Stress."

    A d20 against a d12 Fear Die does two things at once, and the second is the
    larger: the roll's total goes up by four on average, and the roll comes up
    with **Hope** far more often than with Fear - which is what decides whether
    the party keeps the spotlight. This is the first content anywhere to swap the
    Hope Die on the party's side.

    SIMULATION RULE - policy, ruled. **Spent on the first action roll made while
    a Stress is marked.** Taking the first roll of the fight outright was offered
    and declined: the card pays out a Stress clear on a success, and a party at
    full Stress would throw that half away. Waiting for a mark is the same
    reasoning Critical Inspiration and Healing Field already follow, and it costs
    the d20 on the opening rolls of a fight, which is deliberate.

    Being asked is the commitment - `hope_die_for` consults this immediately
    before the roll - so the per-rest use is claimed here rather than afterwards.
    """
    if fight is None or holder.stress_marked <= 0:
        return None
    if not fight.use_once_per_rest(holder, SIGNATURE_MOVE):
        return None

    fight.note(f"{holder.name} performs their signature move, rolling a d20 for Hope")
    return SIGNATURE_MOVE_DIE


@on_roll(SIGNATURE_MOVE)
def signature_move_clears(holder: Holder, roll, fight: Fight) -> None:
    """The Stress a successful signature move clears.

    Registered on the same name as the die swap above, which is how one card
    reaches two hooks - the arrangement Ferocity and Boost already use.

    **Which roll this was is read off the roll itself**, through the Hope Die's
    size, rather than through a token the swap left behind. `DualityRollResult`
    records what each die was rolled on (added for Support Tank), and nothing else
    in the project swaps to a d20, so the size identifies the roll exactly. A
    token would have been wrong here: `hope_die_for` is asked at roll sites this
    hook never hears about, so one set on a Reaction Roll would sit there and pay
    out on the next action roll instead.
    """
    if fight is None or roll is None:
        return
    if roll.hope_die_sides != SIGNATURE_MOVE_DIE or not roll.is_success:
        return
    if holder.stress_marked <= 0:
        return

    holder.clear_stress(1)
    fight.note(f"{holder.name}'s signature move lands, clearing a Stress")


# --- Assessed and dismissed --------------------------------------------------

no_combat_effect(
    "Know Thy Enemy",
    "An Instinct Roll against a creature being observed; on a success, a Hope "
    "buys one set of information about them - unmarked HP and Stress, Difficulty "
    "and thresholds, tactics and damage dice, or features and Experiences - and a "
    "Stress additionally removes a Fear from the GM's pool. Dismissed on its "
    "**trigger**, the way Gifted Tracker and Stealth Expertise are: 'when "
    "observing a creature' is not a move the simulator ever makes, and every "
    "number the card would reveal is already read by the party's own policies, so "
    "the information half changes nothing here. Worth recording that the Fear "
    "clause is real and fully representable - a Fear removed is an extra "
    "activation the GM never gets - and that modelling it alone, as a partial "
    "implementation with the information declared a gap, was proposed and "
    "declined. The card is filed whole rather than split.",
)

no_combat_effect(
    "Untouchable",
    "A bonus to Evasion equal to half the holder's Agility. A character sheet "
    "carries Evasion already resolved, exactly as it carries thresholds and "
    "Armor Score, so the bonus is in the number before a fight starts and "
    "applying it here would count it twice. The same reason the Human's High "
    "Stamina and Valor's Bare Bones are declared rather than run.",
)

insignificant_combat_effect(
    "Deft Maneuvers",
    "Once per rest, mark a Stress to sprint anywhere within Far range, and +1 to "
    "the attack roll if that movement ends in Melee and you swing. The sprint "
    "has no representation - no positions are tracked - but the +1 does, which "
    "is why this is measured rather than dismissed outright. It is worth **one "
    "point on a single attack roll, once per rest**: about five percentage "
    "points on one roll in a fight, bought with a Stress that several other "
    "cards want.",
)

insignificant_combat_effect(
    "I See It Coming",
    "Mark a Stress for +1d4 Evasion against one incoming attack from beyond "
    "Melee range - an average of +2.5 on one roll, repeatable while Stress "
    "lasts. Ruled the same way as the Faerie's Wings, and for the same reason "
    "rather than for the size: the holder chooses **before knowing what the "
    "attack roll needed to beat**, so any implementation would spend the Stress "
    "on precisely the attacks worth spending it on and would simulate a better "
    "party than the one at the table. See SIMULATION-RULES.md on imperfect "
    "information. Note this is the bigger of the two - Wings is a flat +2 and "
    "happens once - so if that ruling is ever revisited, this is the card that "
    "moves the numbers most.",
)
