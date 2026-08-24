"""Grace domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json, checked against the printed page
(SRD p. 126).

Grace is the talking domain, and at levels 1-2 most of it is talking: three of
the five cards resolve rolls the simulator never makes. What is left are the two
that reach across the table - one fixing an adversary's attention, one making it
mark Stress for being provoked.
"""

from combat.results import AttackResult
from content.conditions import ENRAPTURED, Condition, when_the_gm_pays
from content.registry import (
    Fight,
    Holder,
    action,
    adversary_target_override,
    hope_die_for,
    no_combat_effect,
    out_of_combat_ability,
    remake_action_roll,
    total_roll_bonus,
)
from dice.damage import DiceGroup, roll_damage
from dice.duality import roll_duality

# --- Enrapture ---------------------------------------------------------------

ENRAPTURE = "Enrapture"


@action(
    ENRAPTURE,
    unmodelled=[
        "'within Close range' - no positions are tracked, so any adversary can "
        "be enraptured",
        "The fiction of the condition - a narrowed field of view and sound "
        "drowned out. What is modelled is what it comes to: the target's "
        "attention, and so its attacks, are fixed on the caster",
    ],
)
def enrapture(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Enrapture (Grace, level 1).

    SRD: make a Spellcast Roll against a target within Close range. On a success
    they become temporarily Enraptured - their attention fixed on you, narrowing
    their field of view and drowning out any sound but your voice. Once per rest
    on a success, you can mark a Stress to force the Enraptured target to mark a
    Stress as well.

    SIMULATION RULE - policy, ruled. **Enraptured fixes the target's target**:
    an enraptured adversary swings at the caster until the GM spends a Fear to
    shake it off. That is the mirror of the ruling already made for the
    Weaponmaster's Taunt, pointed the other way across the table, and it is what
    "their attention is fixed on you" comes to in a fight.

    So this is a card that *buys danger* for its caster in exchange for taking it
    off somebody else - which makes it the first party content whose whole point
    is being attacked.

    Declines against a target that is already enraptured, whoever did it:
    re-applying a condition somebody already has buys nothing, which is the
    standing rule. Deals no damage, so a cast is a spotlight spent on the
    condition alone.
    """
    if fight.has_condition(target, ENRAPTURED):
        return None

    attack_roll = _spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    fight.apply_condition(
        target,
        Condition(name=ENRAPTURED, end=when_the_gm_pays, source=caster),
    )
    fight.note(f"{caster.name} enraptures {target.name}")

    _hold_their_gaze(caster, target, fight)
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


def _hold_their_gaze(caster: Holder, target, fight: Fight) -> None:
    """The once-per-rest Stress the card can force on an enraptured target.

    Paid for with the caster's own Stress, so it goes through the shared
    last-slot rule like every other PC Stress cost. Claimed only once both the
    Stress and the per-rest use are certain, since a spell that declined here
    would otherwise burn the use for nothing.
    """
    if not caster.will_spend_stress(1):
        return
    if not fight.use_once_per_rest(caster, ENRAPTURE):
        return

    caster.spend_stress(1)
    target.mark_stress(1)
    fight.note(f"{caster.name} holds {target.name}'s gaze, costing them a Stress")


@adversary_target_override(ENRAPTURE)
def enrapture_compels(holder: Holder, adversary, fight: Fight):
    """Whoever enraptured this adversary is who it swings at.

    Reads the condition's `source` rather than assuming the holder, because two
    Bards in one party would each be asked about every adversary and only one of
    them cast it. Nothing is returned for an adversary this holder didn't
    enrapture, so the GM's own targeting rule applies as usual.
    """
    condition = fight.condition_on(adversary, ENRAPTURED)
    if condition is None or condition.source is not holder:
        return None
    return holder


# --- Troublemaker ------------------------------------------------------------

TROUBLEMAKER = "Troublemaker"

TROUBLEMAKER_DIE = 4


@action(
    TROUBLEMAKER,
    unmodelled=[
        "'within Far range' - no positions are tracked, so any adversary can "
        "be provoked",
    ],
)
def troublemaker(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Troublemaker (Grace, level 2).

    SRD: when you taunt or provoke a target within Far range, make a Presence
    Roll against them. Once per rest on a success, roll a number of d4s equal to
    your Proficiency. The target must mark Stress equal to the highest result
    rolled.

    A **Presence** Roll, not a Spellcast Roll - the one action card in the port
    that rolls a named trait rather than the caster's spellcasting one, so a PC
    with no Spellcast trait at all can still use it.

    The **highest** of the d4s, not their sum. At Proficiency 2 that averages a
    little over 3 Stress; at Proficiency 1 it is a flat d4. Against a stat block
    with three Stress slots that is most of the track in one roll, which is what
    makes a card with no damage on it worth a spotlight.

    Fires whenever the per-rest use is there, which is the standing default -
    the card names no condition beyond that. The use is **checked** before the
    roll and **claimed after it**, so declining costs nothing and a failed
    provocation still spends the card: "once per rest on a success" gates the
    payoff, not the attempt.
    """
    trait = "presence"
    if trait not in caster.traits:
        return None
    if not fight.can_use_once_per_rest(caster, TROUBLEMAKER):
        return None

    attack_roll = _spellcast(caster, target, fight, trait=trait)
    if attack_roll is None:
        return None

    fight.use_once_per_rest(caster, TROUBLEMAKER)

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    rolled = roll_damage(
        dice_groups=[DiceGroup(count=max(caster.proficiency, 1), sides=TROUBLEMAKER_DIE)]
    )
    worst = max(rolled.die_results[0])
    target.mark_stress(worst)
    fight.note(f"{caster.name} provokes {target.name} into marking {worst} Stress")
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


# --- Shared ------------------------------------------------------------------


def _spellcast(caster: Holder, target, fight: Fight, trait: str = ""):
    """An action roll against a target's Difficulty, or None if we can't make one.

    `trait` names which of the caster's traits to roll, defaulting to their
    Spellcast trait - Troublemaker rolls Presence instead, which is why this copy
    of the helper takes the argument and the other modules' don't.

    A sheet that names no trait to roll declines rather than guessing, so
    unusable content shows up as content that never fires rather than as content
    that quietly fires with the wrong number.
    """
    rolling = trait or getattr(caster, "spellcast_trait", "")
    if not rolling or rolling not in caster.traits:
        return None

    modifier = caster.traits[rolling] + total_roll_bonus(caster, target, fight)
    hope_die = hope_die_for(caster, fight)

    def roll():
        return roll_duality(
            modifier=modifier, difficulty=target.difficulty, hope_die=hope_die
        )

    return remake_action_roll(caster, roll(), roll, fight)


# --- Assessed rather than built ----------------------------------------------

out_of_combat_ability(
    "Inspirational Words",
    "Tokens equal to the holder's Presence, each spent when speaking with an "
    "ally to clear a Stress, clear a Hit Point, or hand them a Hope. All three "
    "are fully represented and a pool that size is real support - which is why "
    "this is not a dismissal. What it is not is a combat move: the party uses it "
    "in the quiet between encounters, so it runs when sequenced encounters do.",
)

no_combat_effect(
    "Deft Deceiver",
    "A Hope buys advantage on a roll to deceive or trick someone into believing "
    "a lie. The simulator makes attack rolls, Spellcast Rolls and Reaction "
    "Rolls; it never rolls to deceive anybody, so there is no roll for the "
    "advantage to land on.",
)
no_combat_effect(
    "Tell No Lies",
    "On a success the target can't lie to the caster while they stay within "
    "Close range, and marks a Stress only if they refuse to answer a question. "
    "Both halves are about a conversation - and the Stress is contingent on one, "
    "so it cannot be salvaged as the modelled part. Nothing in a fight turns on "
    "whether an adversary is telling the truth.",
)
