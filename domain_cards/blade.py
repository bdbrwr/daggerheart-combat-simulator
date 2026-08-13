"""Blade domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json.
"""

from domain_cards.registry import Holder, severity_response


@severity_response("Get Back Up")
def get_back_up(character: Holder, amount: int, hp_to_mark: int) -> int:
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


def _worth_a_stress(character: Holder, hp_to_mark: int) -> bool:
    """Whether to pay a Stress to drop this hit by one HP.

    SIMULATION RULE - policy. The SRD makes this a player's choice; a simulator
    has to automate it. Always pay if the hit would otherwise put the PC down:
    unconsciousness ends their fight outright, where being Vulnerable only makes
    the rest of it harder. Otherwise only while a spare slot remains, because
    marking the last Stress hands every adversary Advantage on every roll
    against them - a cost that outlives the single HP it just saved.
    """
    if hp_to_mark >= character.hp_remaining:
        return True
    return character.stress_marked + 1 < character.stress_max
