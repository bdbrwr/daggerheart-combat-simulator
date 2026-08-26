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

Level 3 changes the shape of the domain, and both cards brought a condition with
them. **Hypnotic Shimmer** applies *Stunned*, which was the last of the SRD's
named conditions with no representation here at all - and like Cinder Grasp's On
Fire, the card prints the whole rule, so nothing had to be invented.
**Invisibility** applies *Invisible*, which the page spells out as the thing
Hidden had to be ruled to be worth.
"""

from combat.results import AttackResult
from content.aoe import Range, area_difficulty, targets_beaten, targets_in_area
from content.conditions import (
    ENRAPTURED,
    INVISIBLE,
    STUNNED,
    WHEN_THEY_ACT,
    Condition,
    when_the_gm_pays,
)
from content.help import help_with_roll
from content.registry import (
    Fight,
    Holder,
    action,
    adversary_target_override,
    hope_die_for,
    no_combat_effect,
    out_of_combat_ability,
)
from content.spellcast import spellcast
from dice.damage import DiceGroup, roll_damage
from dice.duality import roll_duality

HYPNOTIC_SHIMMER = "Hypnotic Shimmer"

# The same floor Fire Flies and Rain of Blades use: a once-per-rest area spell
# aimed at a single adversary is a spotlight spent for less than a weapon swing.
SHIMMER_WORTH_IT = 2

INVISIBILITY = "Invisibility"

# Printed on the card - Invisibility rolls against a flat 10 rather than against
# anybody's Difficulty, since it targets a willing creature.
INVISIBILITY_DIFFICULTY = 10

# Who is currently Invisible, as a token on the caster - the card holds on one
# creature at a time, so a second cast has to find the first gone.
INVISIBILITY_HELD = "Invisibility held"

# How many actions the invisible creature has left, as a token on them.
INVISIBILITY_TOKENS = "Invisibility actions"

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

    attack_roll = spellcast(caster, target, fight)
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

    attack_roll = spellcast(caster, target, fight, trait=trait)
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


# --- Hypnotic Shimmer --------------------------------------------------------


@action(
    HYPNOTIC_SHIMMER,
    unmodelled=[
        "'in front of you within Close range' - no positions are tracked, so "
        "the area rule in SIMULATION-RULES.md decides how many are caught and "
        "nothing distinguishes what is in front of the caster from what is "
        "behind them",
        "Stunned's 'they can't use reactions' - only the acting half is "
        "modelled. An adversary's Reaction features fire from a dozen dispatch "
        "points rather than from the spotlight, so gating them would mean a "
        "check at every one",
    ],
)
def hypnotic_shimmer(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Hypnotic Shimmer (Grace, level 3).

    SRD: make a Spellcast Roll against all adversaries in front of you within
    Close range. Once per rest on a success, create an illusion of flashing
    colors and lights that temporarily Stuns targets you succeed against and
    forces them to mark a Stress. While Stunned, they can't use reactions and
    can't take any other actions until they clear this condition.

    **The card prints what Stunned does**, which is why the condition is modelled
    rather than standing in for something. Stunned was the last of the SRD's
    named conditions with no representation here; every other one had to be ruled
    on because the book gives it a name and nothing else, and this one arrives
    with its own rule exactly as Cinder Grasp's On Fire did.

    A Stunned adversary **loses its spotlight and the Fear that bought it** - the
    activation is spent and nothing happens, which is the Green Ooze's `Slow`
    shape. That is read generically off `Condition.prevents_action`, so nothing
    in the fight loop knows this card or this condition exists.

    "Until they clear this condition" is the standing reading for a condition the
    party puts on an adversary: it lifts when the GM spends a Fear on their turn.
    So the card poses the GM the same question Cinder Grasp does, and it costs
    them either way - a Fear, or an activation.

    The roll is made **against the whole area at once**, each adversary checked
    against its own Difficulty - the Fire Flies shape.

    SIMULATION RULE - policy. Declines below two adversaries in the area, the
    same floor Fire Flies and Rain of Blades use. The per-rest use is checked
    before the roll and claimed after it, so declining costs nothing and a failed
    cast still spends the card - "once per rest on a success" gates the payoff
    rather than the attempt, which is the reading Troublemaker already takes.
    """
    if not fight.can_use_once_per_rest(caster, HYPNOTIC_SHIMMER):
        return None

    area = targets_in_area(Range.CLOSE, fight.living_adversaries)
    if len(area) < SHIMMER_WORTH_IT:
        return None

    attack_roll = spellcast(caster, target, fight, difficulty=area_difficulty(area))
    if attack_roll is None:
        return None

    fight.use_once_per_rest(caster, HYPNOTIC_SHIMMER)

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    dazzled = targets_beaten(attack_roll, area)
    for adversary in dazzled:
        fight.apply_condition(
            adversary,
            Condition(
                name=STUNNED,
                end=when_the_gm_pays,
                source=caster,
                prevents_action=True,
            ),
        )
        adversary.mark_stress(1)

    if dazzled:
        fight.note(
            f"{caster.name}'s shimmer Stuns {len(dazzled)}, each marking a Stress"
        )
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


# --- Invisibility ------------------------------------------------------------


@action(
    INVISIBILITY,
    unmodelled=[
        "'an ally within Melee range' - no positions are tracked, so any "
        "conscious PC can be reached",
        "An Invisible creature not being *seen* - only the mechanical half is "
        "modelled, which is that attack rolls against them have Disadvantage. "
        "Focus fire still picks its target the same way, so being invisible "
        "never takes somebody off the GM's list. The same gap Cloaked declares",
    ],
)
def invisibility(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Invisibility (Grace, level 3).

    SRD: make a Spellcast Roll (10). On a success, mark a Stress and choose
    yourself or an ally within Melee range to become Invisible. An Invisible
    creature can't be seen except through magical means and attack rolls against
    them are made with disadvantage. Place tokens equal to your Spellcast trait
    on this card; the invisible creature spends one when they take an action, and
    the effect ends after the action that spends the last. Only one creature at a
    time.

    **The card spells out what Invisible is worth** - "attack rolls against them
    are made with disadvantage" - which is precisely what Hidden had to be ruled
    to be worth. So the two are one effect under two names here, and
    `content/conditions.py` keeps the list rather than either reader branching.

    SIMULATION RULE - policy, ruled. It goes to the **frailest conscious PC,
    the caster included** - whoever has the least unmarked HP. That is Rune
    Ward's rule minus its never-the-caster clause, which was there because a ward
    is a trinket you hand somebody; this is a spell you can just as well cast on
    yourself, and the card says so.

    Declines while the spell is already held on somebody, since the card can only
    hold it on one creature at a time and re-casting would buy nothing.

    A caster whose Spellcast trait is zero or less places no tokens and so has
    nothing to hold the spell up, and declines rather than casting for nothing -
    the same reading Unleash Chaos takes of a dice count drawn from a trait.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None

    duration = caster.traits[trait]
    if duration <= 0:
        return None
    if not caster.can_spend_stress(1):
        return None
    if fight.token_count(caster, INVISIBILITY_HELD):
        return None

    subject = min(fight.conscious_party, key=lambda pc: pc.hp_unmarked)

    helped = help_with_roll(caster, fight)
    roll = roll_duality(
        modifier=caster.traits[trait] + helped.bonus,
        difficulty=INVISIBILITY_DIFFICULTY,
        hope_die=hope_die_for(caster, fight),
        help_dice=helped.dice,
    )
    if not roll.is_success:
        return AttackResult(attack_roll=roll, damage_roll=None)

    caster.spend_stress(1)
    fight.set_token(caster, INVISIBILITY_HELD, 1)
    # One extra when the caster hid *themselves*, because the loop announces
    # `WHEN_THEY_ACT` for them immediately after this spotlight - the casting is
    # an action they took, and without the spare token a Spellcast trait of 1
    # would end the spell before the GM ever got a turn. Casting it on an ally
    # needs no such allowance: the ally's own next action is the first to spend
    # one.
    spare = 1 if subject is caster else 0
    fight.set_token(subject, INVISIBILITY_TOKENS, duration + spare)
    fight.apply_condition(
        subject,
        Condition(name=INVISIBLE, end=_invisibility_runs_out, source=caster),
    )
    fight.note(
        f"{caster.name} turns {subject.name} Invisible for {duration} action(s)"
    )
    return AttackResult(attack_roll=roll, damage_roll=None)


def _invisibility_runs_out(holder, fight: Fight, moment: str) -> bool:
    """One token per action the invisible creature takes; ends on the last.

    "After the action that spends the last token is resolved, the effect ends" -
    and `WHEN_THEY_ACT` is announced *after* the action resolves, so the action
    that spends the last token is still made unseen. That is the same ordering
    On Fire relies on for "at the end of their action".

    The caster's hold is released here too, so the spell can be cast again.
    """
    if moment != WHEN_THEY_ACT:
        return False

    fight.spend_tokens(holder, INVISIBILITY_TOKENS, 1)
    if fight.token_count(holder, INVISIBILITY_TOKENS) > 0:
        return False

    spell = fight.condition_on(holder, INVISIBLE)
    if spell is not None and spell.source is not None:
        fight.set_token(spell.source, INVISIBILITY_HELD, 0)
    return True


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
