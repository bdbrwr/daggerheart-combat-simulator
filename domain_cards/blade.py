"""Blade domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json.
"""

from content.aoe import Range, targets_reached
from content.registry import Fight, Holder, on_hit, severity_response


@severity_response("Get Back Up")
def get_back_up(character: Holder, amount: int, hp_to_mark: int, fight=None) -> int:
    """Get Back Up (Blade, level 1). Returns the HP the hit should now mark.

    SRD: when you take Severe damage, you can mark a Stress to reduce the
    severity by one threshold.

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
    """
    if amount < character.severe_threshold:
        return hp_to_mark
    if hp_to_mark <= 0:
        return hp_to_mark  # armor already took it to nothing; don't buy nothing
    if not _worth_a_stress(character, hp_to_mark):
        return hp_to_mark
    if not character.spend_stress(1):
        return hp_to_mark
    return hp_to_mark - 1


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

    splash = result.damage_roll.total // 2
    for adversary in others[:reach]:
        adversary.take_damage(splash)
        fight.note(f"Whirlwind catches {adversary.name} for {splash}")


def _worth_a_stress(character: Holder, hp_to_mark: int) -> bool:
    """Whether to pay a Stress to drop this hit by one HP.

    SIMULATION RULE - policy. The SRD makes this a player's choice; a simulator
    has to automate it. Always pay if the hit would otherwise put the PC down:
    unconsciousness ends their fight outright, where being Vulnerable only makes
    the rest of it harder. Otherwise only while a spare slot remains, because
    marking the last Stress hands every adversary Advantage on every roll
    against them - a cost that outlives the single HP it just saved.
    """
    if hp_to_mark >= character.hp_unmarked:
        return True
    return character.stress_marked + 1 < character.stress_max
