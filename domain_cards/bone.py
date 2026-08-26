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
"""

from content.registry import (
    Fight,
    Holder,
    evasion_bonus,
    extra_armor_slot,
    extra_damage,
    help_bonus,
    insignificant_combat_effect,
    no_combat_effect,
    on_hit,
)
from content.rolls import EXPERIENCE_HOPE_FLOOR
from dice.damage import DiceGroup

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


# --- Assessed and dismissed --------------------------------------------------

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
