"""Splendor domain cards.

Card text is paraphrased in each docstring rather than quoted in full. The
verbatim text is in .reference/abilities.json.
"""

from combat.results import AttackResult
from content.registry import Fight, Holder, action, hope_die_for
from dice.duality import roll_duality

HEALING_HANDS_DIFFICULTY = 13

# Only worth a spotlight's roll once an ally is genuinely in trouble. Healing
# somebody at full HP spends the party's tempo on nothing.
HURT_ENOUGH_TO_HEAL = 2


@action(
    "Healing Hands",
    unmodelled=[
        "'within Melee range' - no positions are tracked, so any ally can be "
        "reached",
        "clearing Stress instead of HP - HP is always chosen, since a downed "
        "PC is what actually ends a fight",
    ],
)
def healing_hands(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Healing Hands (Splendor, level 2). Spellcast Roll (13) against an ally other
    than yourself; on a success mark a Stress to clear 2 HP on them, on a failure
    mark a Stress to clear 1. The same target can't be healed again until your
    next long rest.

    `target` is the adversary the turn policy picked, and is ignored - this
    spell aims at an ally instead. It declines unless somebody is hurt enough to
    be worth a spotlight, which is what stops a healer standing in the back
    topping people up instead of fighting.

    The per-long-rest limit is per *target*, so the once-per-rest key carries
    the ally's name with it.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None
    if not caster.can_spend_stress(1):
        return None

    patient = _who_needs_it(caster, fight)
    if patient is None:
        return None
    if not fight.use_once_per_rest(caster, f"Healing Hands:{patient.name}", long=True):
        return None

    roll = roll_duality(
        modifier=caster.traits[trait],
        difficulty=HEALING_HANDS_DIFFICULTY,
        hope_die=hope_die_for(caster, fight),
    )
    caster.spend_stress(1)
    cleared = 2 if roll.is_success else 1
    patient.clear_hp(cleared)
    fight.note(f"{caster.name} heals {patient.name} for {cleared} HP")

    # No damage was dealt, but a roll was made - and it's the roll, not the
    # damage, that decides whether the spotlight moves.
    return AttackResult(attack_roll=roll, damage_roll=None)


def _who_needs_it(caster: Holder, fight: Fight):
    """The worst-off conscious ally, if anyone is hurt enough to be worth it."""
    allies = [
        pc
        for pc in fight.conscious_party
        if pc is not caster and pc.hp_remaining <= HURT_ENOUGH_TO_HEAL
    ]
    if not allies:
        return None
    return min(allies, key=lambda pc: pc.hp_remaining)
