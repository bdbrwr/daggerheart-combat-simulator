"""Valor domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json.

Cards from this domain that can't affect a fight are declared at the bottom, so
"assessed and dismissed" never looks like "nobody has got to it yet".
"""

from content.registry import Fight, Holder, damage_bonus, guard, no_combat_effect


@damage_bonus(
    "Body Basher",
    unmodelled=[
        "The Melee-only restriction - weapon range bands aren't recorded "
        "anywhere, so this applies to any weapon the holder is carrying",
    ],
)
def body_basher(attacker: Holder, target, fight: Fight) -> int:
    """Body Basher (Valor, level 2).

    SRD: on a successful attack using a weapon with a Melee range, gain a bonus
    to your damage roll equal to your Strength.

    Applied before the target's thresholds are consulted, so it can change how
    many HP the hit marks rather than only the number printed - which is the
    whole reason it's a damage bonus hook rather than something bolted on after.

    The Melee restriction isn't enforced, and that's declared above. It happens
    to be correct for the only holder so far (a Greatsword is Melee), but it
    would quietly overstate a Body Basher on a bow.
    """
    return max(attacker.traits["strength"], 0)


@guard(
    "I Am Your Shield",
    unmodelled=[
        "Marking any number of Armor Slots against the redirected hit - "
        "take_damage marks at most one slot per hit",
        "'Within Very Close range' - no positioning is tracked, so every "
        "conscious PC is assumed able to reach the ally",
    ],
)
def i_am_your_shield(shielder: Holder, ally: Holder) -> bool:
    """I Am Your Shield (Valor, level 1). Returns whether `shielder` steps in.

    SRD: when an ally within Very Close range would take damage, you can mark a
    Stress to stand in the way and make yourself the target of the attack
    instead. When you take damage from this attack, you can mark any number of
    Armor Slots.

    SIMULATION RULE - rules interpretation. Applied by swapping the attack's
    target before it's rolled, so the attack resolves against the shielder's
    Evasion. That's what the effect clause says - "make yourself the target of
    the attack instead" - though the trigger clause ("when an ally would take
    damage") can be read as firing after a hit is known, in which case the
    ally's Evasion would decide it and the shielder would simply eat the damage.
    Worth revisiting; it changes how often stepping in is a good idea.

    The parts left out are declared on the decorator above rather than only
    here, so they reach the coverage report.
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


no_combat_effect(
    "Bare Bones",
    "Sets Armor Score and thresholds when wearing no armor. A sheet already "
    "carries its resolved thresholds and armor slots, so this changes nothing "
    "at simulation time.",
)
