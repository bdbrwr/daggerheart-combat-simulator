"""Blade domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json.

Cards assessed as belonging outside a fight are declared at the bottom, so that
"used between encounters" never looks like "nobody has got to it yet" - and, just
as importantly, never looks like a dismissal either.
"""

from content.aoe import Range, targets_reached
from content.registry import (
    Fight,
    Holder,
    attack_advantage,
    damage_die_reroll,
    on_hit,
    out_of_combat_ability,
    severity_response,
)
from dice.common import AdvantageState

# Not Good Enough rerolls any die showing this or less.
NOT_GOOD_ENOUGH_CEILING = 2


@severity_response("Get Back Up")
def get_back_up(
    character: Holder, amount: int, hp_to_mark: int, fight=None, damage_type=None
) -> int:
    """Get Back Up (Blade, level 1). Returns the HP the hit should now mark.

    SRD: when you take Severe damage, you can mark a Stress to reduce the
    severity by one threshold.

    `damage_type` is ignored: the card names no type, so it answers for both.

    SIMULATION RULE - rules interpretation. This triggers on the damage *amount*
    clearing the Severe threshold rather than on the HP the hit would end up
    marking. That matters when an Armor Slot has already softened it: under this
    reading the hit is still Severe damage - a property of the number rolled -
    so the card still applies and the two reductions stack, taking a Severe hit
    from 3 HP down to 1. The SRD doesn't say either way. Reading it the other
    way (armor first, so the card only fires if the hit is still severe
    afterwards) would make the pair order-dependent for no stated reason.

    The Stress is a voluntary cost, so it goes through spend_stress: per the SRD
    a move requiring Stress simply can't be used when Stress is full, and must
    never fall through to marking HP the way forced Stress does.

    SIMULATION RULE - policy, ruled. Whether the Stress is worth paying is the
    shared last-slot rule (`PlayerCharacter.will_spend_stress`), not a policy of
    this card's own. It used to have one - "always pay if the hit would otherwise
    put the PC down, otherwise only while a spare slot remains" - and the user
    replaced it with the general rule so that every card costing Stress answers
    the same way. The one case that changed: a PC on their last Stress slot with
    3 unmarked HP taking a hit that would mark all 3 now goes down rather than
    paying, because the last slot is held until 2 or fewer are unmarked.
    """
    if amount < character.severe_threshold:
        return hp_to_mark
    if hp_to_mark <= 0:
        return hp_to_mark  # armor already took it to nothing; don't buy nothing
    if not character.will_spend_stress(1):
        return hp_to_mark
    character.spend_stress(1)
    return hp_to_mark - 1


@damage_die_reroll(
    "Not Good Enough",
    unmodelled=[
        "Damage rolled by anything other than a weapon - a card or a subclass "
        "feature that rolls its own dice doesn't consult the reroll hook, so "
        "this reaches weapon swings only",
    ],
)
def not_good_enough(attacker: Holder, sides: int, result: int, fight: Fight) -> bool:
    """Not Good Enough (Blade, level 1). Whether this die gets thrown again.

    SRD: "When you roll your damage dice, you can reroll any 1s or 2s."

    No cost and no limit, so there is no policy to rule on: a reroll of a 1 or a
    2 can only move the total up or leave it where it was, and the simulator
    plays PC content at optimal play. It fires on every damage roll the card can
    reach.

    Each die is offered one fresh throw - see `damage_die_reroll`. A rerolled 2
    that comes up a 1 stays a 1; the card says reroll, not reroll until happy.

    `sides` is unused here, and is in the signature because a rule about dice
    could well be about their size: "reroll any 1s" reads differently on a d4
    than on a d12, and content that wants to care can.
    """
    return result <= NOT_GOOD_ENOUGH_CEILING


@attack_advantage(
    "Reckless",
    unmodelled=[
        "Attacks that aren't a weapon swing - a Grimoire spell or any card that "
        "rolls its own attack passes its own advantage state and never consults "
        "this hook, so Reckless can't be spent on one",
    ],
)
def reckless(attacker: Holder, target, fight: Fight) -> AdvantageState | None:
    """Reckless (Blade, level 2). Advantage on this attack for a Stress.

    SRD: "Mark a Stress to gain advantage on an attack."

    SIMULATION RULE - policy, ruled. Paid whenever the shared last-slot rule
    allows it (`PlayerCharacter.will_spend_stress`): freely while a spare slot
    remains, and the last slot only once the PC is at 2 or fewer unmarked HP.
    That is the general rule for every PC Stress cost rather than anything
    specific to this card.

    So in practice a Reckless PC swings with Advantage from the first spotlight
    and keeps doing it until one slot is left, which is a fast way to spend a
    Stress track - and exactly what the card is for.

    Being asked is the commitment: `items/weapons.py` consults this once,
    immediately before the swing, so the Stress buys a roll that definitely
    happens. A reroll re-makes that roll without asking again.
    """
    if not attacker.will_spend_stress(1):
        return None

    attacker.spend_stress(1)
    if fight is not None:
        fight.note(f"{attacker.name} marks a Stress to attack recklessly")
    return AdvantageState.ADVANTAGE


@on_hit(
    "Whirlwind",
    unmodelled=[
        "'Within Very Close range' - no positions are tracked, so the area "
        "rule in SIMULATION-RULES.md decides how many adversaries are caught",
    ],
)
def whirlwind(attacker: Holder, target, result, fight: Fight) -> None:
    """Whirlwind (Blade, level 1).

    SRD: "When you make a successful attack against a target within Very Close
    range, you can spend a Hope to use the attack against all other targets
    within Very Close range. All additional adversaries you succeed against with
    this ability take half damage."

    SIMULATION RULE - rules interpretation. Once the attack against the primary
    target has succeeded, every additional adversary caught is **hit
    automatically** and takes half damage; the roll is not re-checked against
    each one's Difficulty. "All additional adversaries you succeed against" can
    be read as a per-target check, and was implemented that way at first - but
    the trigger is a single successful attack being *used* against the others,
    and this is the reading the table plays. Half damage rounds down.

    The Hope is only spent when there is somebody else to hit. At Very Close the
    area rule reaches a third of the field in total - held to two unless the
    field is unusually spread out - and the original target is one of them, so
    in a fight with fewer than six adversaries this correctly does nothing and
    costs nothing.

    That reach is **rolled per cast**, not a fixed function of the field: the
    same six adversaries can be bunched or strung out, so how far one Whirlwind
    carries is not how far the next one does. See `content/aoe.py`.
    """
    others = [
        adversary
        for adversary in fight.living_adversaries
        if adversary is not target
    ]
    reach = targets_reached(Range.VERY_CLOSE, len(fight.living_adversaries)) - 1
    if reach <= 0 or not others:
        return

    if not attacker.can_spend_hope(1):
        return
    attacker.spend_hope(1)

    # The same attack landing on somebody else, so the same type: the card adds
    # no damage of its own, it re-uses the swing's. See
    # `PlayerCharacter.weapon_damage_type`.
    splash = result.damage_roll.total // 2
    damage_type = getattr(attacker, "weapon_damage_type", None)
    for adversary in others[:reach]:
        adversary.take_damage(splash, fight, damage_type=damage_type)
        fight.note(f"Whirlwind catches {adversary.name} for {splash}")


out_of_combat_ability(
    "A Soldier's Bond",
    "Once per long rest, complimenting someone gives you and them 3 Hope each. "
    "Not a dismissal: 6 Hope across two PCs is a large effect and Hope is fully "
    "tracked here. What the card isn't is a combat move - players don't stop "
    "mid-fight to pay someone a compliment, they do it between encounters. So it "
    "belongs to the sequenced-encounter machinery, which doesn't exist yet, and "
    "is recorded here as work with a home rather than as work nobody has done.",
)
