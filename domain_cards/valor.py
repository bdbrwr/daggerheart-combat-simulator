"""Valor domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json.
"""

from domain_cards.registry import Holder, guard


@guard("I Am Your Shield")
def i_am_your_shield(shielder: Holder, ally: Holder) -> bool:
    """I Am Your Shield (Valor, level 1). Returns whether `shielder` steps in.

    SRD: when an ally within Very Close range would take damage, you can mark a
    Stress to stand in the way and make yourself the target of the attack
    instead. When you take damage from this attack, you can mark any number of
    Armor Slots.

    SIMULATION RULE - rules interpretation. Applied by swapping the attack's
    target before it's rolled, so the attack resolves against the shielder's
    Evasion. That's what the effect clause says - "make yourself the target of
    the attack instead" - though the trigger clause ("would take damage") can be
    read as firing after a hit is known, in which case the ally's Evasion would
    decide it and the shielder would simply eat the damage. Worth revisiting; it
    changes how often stepping in is a good idea.

    SIMULATION RULE - not implemented. The second sentence's "mark any number of
    Armor Slots" is ignored: PlayerCharacter.take_damage marks at most one slot
    per hit, and multi-slot marking is a change to the damage rules rather than
    to this card.

    SIMULATION RULE - simplification. Range isn't modelled anywhere in the
    simulator, so "within Very Close range" is taken as always true - every
    conscious PC is assumed able to reach the ally.
    """
    if not _worth_shielding(shielder, ally):
        return False
    return shielder.spend_stress(1)


def _worth_shielding(shielder: Holder, ally: Holder) -> bool:
    """Whether stepping in front of `ally` is the better trade.

    SIMULATION RULE - policy. The SRD makes this a player's choice. Step in only
    when the ally is closer to going down than the shielder is: the point of the
    card is moving a hit onto whoever can afford it, and a shielder who would
    drop from the hit themselves gains the party nothing by taking it.
    """
    if ally.hp_remaining >= shielder.hp_remaining:
        return False
    return shielder.hp_remaining > 1
