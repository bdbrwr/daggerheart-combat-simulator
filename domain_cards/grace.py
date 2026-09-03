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

Level 4 turns the domain straight back again: **neither** of its cards reaches a
fight. That is worth recording rather than looking like an omission - Grace is
the only domain so far whose whole level contributes nothing, and the two cards
land in *different* states, which is most of why the states exist. Soothing
Speech is a real heal that happens during a rest; Through Your Eyes is scouting.

Level 5 carries **Words of Discord**, the first thing anywhere that makes one side
of the table attack itself. The whisper is the party's whole contribution: the
attack that follows is the adversary's own, rolled against another adversary's
Difficulty and dealing the whisperer's printed damage.

Level 6 turns the domain inward. **Never Upstaged** banks the holder's own wounds
and pays them back five points apiece, and **Share the Burden** is the only card
in the project that turns one resource straight into another - an ally's Stress
becomes the caster's, and each slot moved is a Hope.

Level 7 keeps doing that, in both directions at once. **Grace-Touched** lets an
Armor Slot pay where a Stress would on the party's side, and turns an adversary's
wound into Stress on the GM's - the first card anywhere to reach the *resource a
mark lands on* rather than its size, which is why it needed two hooks nothing else
uses. **Endless Charisma** is dismissed on its trigger, a social roll the
simulator never makes.

Level 8's **Mass Enrapture** is level 1's Enrapture over the whole Far band, and
the ruling on it is the interesting part: the card is cast only when the Stress
that *ends* the spell can be paid, so the compulsion never gets a spotlight and
what the card actually does here is force a Stress on everything it caught.
"""

import random

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
    DamagePool,
    Fight,
    Holder,
    action,
    adversary_target_override,
    armor_instead_of_stress,
    damage_pool,
    free,
    hope_die_for,
    no_combat_effect,
    on_damaged,
    out_of_combat_ability,
    stress_instead_of_hp,
)
from content.spellcast import spellcast
from dice.d20 import roll_d20
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
        trait=trait,
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


# --- Words of Discord --------------------------------------------------------

WORDS_OF_DISCORD = "Words of Discord"

# Printed on the card rather than read off the target, which is unusual - almost
# every other attack in the project is measured against a Difficulty the stat
# block carries.
WORDS_OF_DISCORD_DIFFICULTY = 13

# Set on an adversary once the compelled attack is over. "The target realizes what
# happened", and under the ruling below that is the end of the card for them.
DISCORD_HEARD = "Words of Discord heard"


@action(
    WORDS_OF_DISCORD,
    unmodelled=[
        "'an adversary within Melee range' - no positions are tracked, so any "
        "adversary can be whispered to",
        "The **-5 penalty** for casting this on somebody who has already heard "
        "it. The ruling is that the caster declines once every adversary has, so "
        "a second cast on the same target never happens and the penalty is never "
        "applied. It is printed and reachable, and only the policy puts it out of "
        "reach - which is worth knowing if that policy is ever changed",
    ],
)
def words_of_discord(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Words of Discord (Grace, level 5). Turn an adversary on its own side.

    SRD: "Whisper words of discord to an adversary within Melee range and make a
    Spellcast Roll (13). On a success, the target must mark a Stress and make an
    attack against another adversary instead of against you or your allies. Once
    this attack is over, the target realizes what happened. The next time you cast
    Words of Discord on them, gain a -5 penalty to the Spellcast Roll."

    **The first thing in the simulator that makes one side attack itself.** The
    compelled attack is a real one: the adversary's own attack modifier against
    the victim's **Difficulty**, dealing the whisperer's printed damage, typed as
    its stat block types it. There is no PC damage roll anywhere in this - the
    party's contribution is the whisper.

    SIMULATION RULE - rules interpretation, ruled. **The attack happens
    immediately, inside the cast**, rather than replacing the adversary's next
    activation. The other reading was offered and declined; it would have needed a
    new hook for party content to take over an adversary's spotlight, and the
    existing target-override hook cannot say it, since that returns a PC. The
    consequence follows plainly from the mechanics and is worth stating: the
    whisperer still takes its own spotlight afterwards, so the card buys the party
    an extra attack on the GM's side rather than taking one away from themselves.

    SIMULATION RULE - policy, ruled. **A target who has not heard it before**, and
    the card declines outright once every living adversary has. Casting at -5
    against a Difficulty of 13 was offered as the alternative and declined. Which
    fresh adversary is whispered to, and which other one is attacked, both follow
    the party's focus-fire rule - the most wounded of the candidates, exactly as
    Redirect chooses who a turned attack lands on.

    Costs nothing but the roll, so there is no other state in which casting it is
    worse than not - the Wild Flame reading.
    """
    living = fight.living_adversaries
    if len(living) < 2:
        return None

    fresh = [
        adversary
        for adversary in living
        if not fight.token_count(adversary, DISCORD_HEARD)
    ]
    if not fresh:
        return None

    whispered = max(fresh, key=lambda adversary: adversary.hp_marked)
    attack_roll = spellcast(
        caster, whispered, fight, difficulty=WORDS_OF_DISCORD_DIFFICULTY
    )
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    whispered.mark_stress(1)
    fight.note(
        f"{caster.name} whispers discord to {whispered.name}, who marks a Stress "
        f"and turns on their own"
    )
    _lash_out(whispered, living, fight)
    fight.set_token(whispered, DISCORD_HEARD, 1)

    # No damage roll of the caster's own, so nothing the party carries fires off
    # this as though it were a landed hit. The play-by-play reports it as a miss,
    # which it shares with every other card whose success is not damage.
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


def _lash_out(whispered, living: list, fight: Fight) -> None:
    """The compelled attack, made by the whispered adversary against one of its own.

    Rolled here rather than through `Adversary.attack`, which measures its roll
    against a PC's **Evasion** and would raise on an adversary target. An attack
    against an adversary is measured against Difficulty - the SRD says so outright
    - so the d20 is thrown directly, the same way an adversary's Reaction Roll is.

    The victim is the most wounded of the others, which is the party's own
    focus-fire rule: the discord is the party's doing, so where it lands follows
    what the party is already trying to achieve. The same choice Redirect makes.
    """
    others = [adversary for adversary in living if adversary is not whispered]
    if not others:
        return

    victim = max(others, key=lambda adversary: adversary.hp_marked)
    swing = roll_d20(modifier=whispered.attack_modifier, evasion=victim.difficulty)
    if not swing.is_success:
        fight.note(f"{whispered.name} lashes out at {victim.name} and misses")
        return

    damage = roll_damage(
        dice_groups=whispered.damage_dice,
        modifier=whispered.damage_modifier,
        is_critical=swing.is_critical,
    )
    victim.take_damage(damage.total, fight, damage_type=whispered.type_of_damage())
    fight.note(
        f"{whispered.name} lashes out at {victim.name} for {damage.total} "
        f"({victim.hp_marked}/{victim.hp_max} HP marked)"
    )
    if victim.is_defeated:
        fight.note(f"{victim.name} is defeated")


# --- Never Upstaged ----------------------------------------------------------

NEVER_UPSTAGED = "Never Upstaged"

NEVER_UPSTAGED_TOKENS = "Never Upstaged tokens"

# "Gain a +5 bonus to your damage roll for each token on this card."
NEVER_UPSTAGED_BONUS = 5


@on_damaged(NEVER_UPSTAGED)
def never_upstaged(
    holder: Holder,
    amount: int,
    hp_marked: int,
    fight: Fight,
    marked_armor: bool = False,
    damage_type=None,
) -> None:
    """Never Upstaged (Grace, level 6), first half. Bank the wound as tokens.

    SRD: "When you mark 1 or more Hit Points from an attack, you can mark a Stress
    to place a number of tokens equal to the number of Hit Points you marked on
    this card. On your next successful attack, gain a +5 bonus to your damage roll
    for each token on this card, then clear all tokens."

    Keyed on HP **marked**, not on damage taken - `hp_marked` is what the hit
    finally cost after thresholds, an Armor Slot and any resistance, which is what
    the card asks for. So a hit an Armor Slot swallowed whole banks nothing, and a
    Severe one banks three tokens and fifteen points of retaliation.

    SIMULATION RULE - policy. Nothing to rule on beyond the standing default: the
    Stress is marked whenever the shared last-slot rule allows it. The card asks
    for no judgement - the tokens sit there until an attack lands and nothing
    expires them - so what limits it is the Stress track and nothing else.

    Tokens **accumulate** across several wounds, since the card says to place them
    and only the successful attack clears them. Two Severe hits before the holder
    next connects is six tokens.
    """
    if fight is None or hp_marked < 1:
        return
    if not holder.will_spend_stress(1):
        return

    holder.spend_stress(1)
    fight.set_token(
        holder,
        NEVER_UPSTAGED_TOKENS,
        fight.token_count(holder, NEVER_UPSTAGED_TOKENS) + hp_marked,
    )
    fight.note(
        f"{holder.name} will not be upstaged, banking {hp_marked} "
        f"token{'s' if hp_marked > 1 else ''}"
    )


@damage_pool(
    NEVER_UPSTAGED,
    unmodelled=[
        "Damage rolled by anything other than a weapon swing. `adjust_damage_pool` "
        "is asked from `items/weapons.py` and from Bone's Rapid Riposte, and the "
        "cards that roll Proficiency dice of their own never consult it - so a "
        "Grace character who banks tokens and then casts is holding them still. "
        "The same gap Splendor's Voice of Reason declares",
    ],
)
def never_upstaged_repays(
    holder: Holder, weapon, pool: DamagePool, fight: Fight = None, roll=None
) -> DamagePool:
    """Never Upstaged, second half. Cash every token into the damage that just landed.

    **On `damage_pool` rather than on either damage hook next door**, and the
    reason is the card's own wording. "On your next **successful** attack" rules
    out `damage_bonus`, which is asked before the dice are thrown and would clear
    the tokens on a miss; "+5 for each token" is a flat number rather than dice,
    which rules out `extra_damage`. This hook is the only one asked *after* an
    attack has landed and *before* its damage is rolled, and `DamagePool` carries
    the flat modifier - so the bonus crosses the target's thresholds exactly once,
    which is where five points per token is worth having.

    Being asked is the commitment: the damage roll follows immediately, so the
    tokens are cleared here rather than waiting for something to notice the hit.
    """
    if fight is None:
        return pool

    tokens = fight.token_count(holder, NEVER_UPSTAGED_TOKENS)
    if not tokens:
        return pool

    fight.set_token(holder, NEVER_UPSTAGED_TOKENS, 0)
    bonus = tokens * NEVER_UPSTAGED_BONUS
    fight.note(f"{holder.name} answers in kind, cashing {tokens} for +{bonus} damage")
    return pool._replace(modifier=pool.modifier + bonus)


# --- Grace-Touched ---------------------------------------------------------------

GRACE_TOUCHED = "Grace-Touched"

# An adversary this close to going down is finished rather than worn down: the HP
# is what takes it off the field, and Stress does not. The user's ruling.
GRACE_TOUCHED_FINISH_AT = 2

TOUCHED_LOADOUT_GAP = (
    "'When 4 or more of the domain cards in your loadout are from the Grace "
    "domain' - the loadout is not counted. The user's ruling is that carrying the "
    "card is taken as proof the condition is met, since a player who takes it has "
    "built for it. Recorded as a simulation rule rather than checked"
)


@armor_instead_of_stress(
    GRACE_TOUCHED,
    unmodelled=[
        TOUCHED_LOADOUT_GAP,
        "Stress a PC is **forced** to mark - by Wild Flame, Troublemaker or an "
        "adversary's feature - still overflows into an HP when the track is full, "
        "rather than being paid with an Armor Slot. The substitution reaches "
        "`spend_stress`, which is the voluntary cost, and not `mark_stress`, which "
        "is the SRD's forced one. Whether 'instead of marking a Stress' covers "
        "being made to mark one is genuinely ambiguous on the page, and this is "
        "the narrower reading",
    ],
)
def grace_touched(holder: Holder, amount: int = 1) -> bool:
    """Grace-Touched (Grace, level 7), first clause.

    SRD: "When 4 or more of the domain cards in your loadout are from the Grace
    domain, gain the following benefits: you can mark an Armor Slot instead of
    marking a Stress; when you would force a target to mark a number of Hit Points,
    you can choose instead to force them to mark that number of Stress."

    A standing permission rather than anything that fires, so this returns True and
    lets `PlayerCharacter._pays_with_armor` decide when it is taken. **When** is
    the user's ruling and lives there: only where the shared last-slot rule would
    otherwise refuse the Stress, so armor is spent at the cliff rather than from
    the first spotlight.

    Worth knowing what that comes to across a sheet, since this reaches *every*
    Stress cost the PC has rather than one card: a Grace character with armor free
    keeps using Stress-priced cards past the point every other PC stops, and pays
    for it in the resource that otherwise absorbs a hit per wound.
    """
    return True


@stress_instead_of_hp(
    GRACE_TOUCHED,
    unmodelled=[
        TOUCHED_LOADOUT_GAP,
        "A hit worth more HP than the adversary has Stress slots free is split - "
        "the slots fill and the remainder still marks HP. The card says 'that "
        "number of Stress', which reads as all or nothing; the split follows the "
        "user's ruling to fill Stress and then go back to HP, and never wastes "
        "part of a hit",
    ],
)
def grace_touched_converts(
    caster: Holder, target, hp_to_mark: int, fight: Fight = None
) -> int:
    """Grace-Touched's second clause - a wound taken as Stress instead.

    SIMULATION RULE - rules interpretation, ruled. **"Force a target to mark Hit
    Points" covers damage.** Reading it as only the handful of effects that say
    "mark an HP" outright - of which the project has one, Champion's Edge - was
    proposed and the user corrected it: this is every HP the party causes an
    adversary to mark. What it does not reach is HP an adversary spends *willingly*
    on its own features, which is `will_spend_hp`'s business and nobody forcing
    anything.

    SIMULATION RULE - policy, ruled. Three states, in order:

    * an adversary at `GRACE_TOUCHED_FINISH_AT` or fewer unmarked HP takes the
      **HP**, because that is what ends it and Stress never will;
    * otherwise, while it has Stress slots free, it takes the **Stress**;
    * and once its track is full, back to HP.

    Worth being plain about what the middle case buys here, because the reasoning
    it was ruled on does not fully hold: an adversary's Stress pays for its Action
    features and gates its desperation rule, so filling the track shuts those off -
    but `Adversary.is_vulnerable` is **always False** in this simulator, so
    stressing one out does *not* make it Vulnerable the way it would a PC. The
    ruling stands as made; the Vulnerable half of it simply has nothing to land on
    today.

    Reads only what a player can see: the HP the hit is about to cost, and the
    target's own tracks.
    """
    if fight is None or hp_to_mark <= 0:
        return 0
    if target.hp_unmarked <= GRACE_TOUCHED_FINISH_AT:
        return 0

    taking = min(hp_to_mark, target.stress_unmarked)
    if taking <= 0:
        return 0

    fight.note(
        f"{caster.name} turns {taking} of {target.name}'s wound into Stress"
    )
    return taking


# --- Share the Burden --------------------------------------------------------

SHARE_THE_BURDEN = "Share the Burden"

# How few free Stress slots an ally has to be down to before the caster takes
# their burden on. It mirrors `combat/policy.py`'s `LOW_STRESS_SLOTS`, which is
# the line at which a PC drinks a stamina potion, and it is restated here rather
# than imported for the reason Chokehold restates the focus rule: `combat/policy.py`
# imports `content/`, and the dependency cannot run the other way.
SHARE_THE_BURDEN_ALLY_SLOTS = 1


@free(
    SHARE_THE_BURDEN,
    unmodelled=[
        "'within Melee range' - no positions are tracked, so any conscious ally "
        "can be relieved",
        "The intimate knowledge or emotions that leak across is fiction with no "
        "mechanic attached, so nothing here records what was learned",
    ],
)
def share_the_burden(caster: Holder, fight: Fight) -> bool:
    """Share the Burden (Grace, level 6). Take an ally's Stress, and be paid for it.

    SRD: "Once per rest, take on the Stress from a willing creature within Melee
    range. The target describes what intimate knowledge or emotions telepathically
    leak from their mind in this moment between you. Transfer any number of their
    marked Stress to you, then gain a Hope for each Stress transferred."

    **No roll**, so it is a free ability: the caster relieves somebody *and* takes
    their own action roll in the same spotlight. It is also the only card in the
    project that turns one resource straight into another - every Stress moved is
    a Hope gained - which is worth reading its numbers knowing.

    SIMULATION RULE - policy, ruled. Three decisions, all the user's:

    * **It waits until an ally is on high Stress** - `SHARE_THE_BURDEN_ALLY_SLOTS`
      free slots or fewer, the line at which that PC would already be reaching for
      a stamina potion. Whoever has the most marked, ties drawn at random.
    * **The caster takes as much as the shared Stress rule lets them**, so they
      fill to one spare slot and stop. `will_spend_stress` is asked per slot, the
      same way Rage Up asks it between its two.
    * **And never more than their Hope can hold.** A Stress transferred past the
      Hope cap is a slot spent for nothing, since the Hope it pays out simply does
      not arrive - `gain_hope` counts only what lands. So the transfer stops at
      whichever of the three limits comes first.

    The Stress is marked on the caster with `spend_stress`, not `mark_stress`:
    this is a cost they choose, and a voluntary cost must never fall through to an
    HP when the track is full.
    """
    if fight is None:
        return False
    if not fight.can_use_once_per_rest(caster, SHARE_THE_BURDEN):
        return False

    burdened = _most_burdened(caster, fight)
    if burdened is None:
        return False

    room = caster.hope_max - caster.hope_marked
    if room <= 0:
        return False

    taken = 0
    while (
        taken < burdened.stress_marked
        and taken < room
        and caster.will_spend_stress(1)
    ):
        caster.spend_stress(1)
        taken += 1
    if not taken:
        return False

    burdened.clear_stress(taken)
    caster.gain_hope(taken)
    fight.use_once_per_rest(caster, SHARE_THE_BURDEN)
    fight.note(
        f"{caster.name} shares {burdened.name}'s burden, taking {taken} Stress "
        f"and gaining {taken} Hope"
    )
    return True


def _most_burdened(caster: Holder, fight: Fight):
    """The ally worth relieving, or None if nobody is close enough to the cliff.

    "A willing creature" is read as an ally rather than the caster, since taking
    on your own Stress is not a transfer. Ties are drawn rather than settled by
    party order, which carries no meaning.
    """
    allies = [
        pc
        for pc in fight.conscious_party
        if pc is not caster
        and pc.stress_max - pc.stress_marked <= SHARE_THE_BURDEN_ALLY_SLOTS
        and pc.stress_marked > 0
    ]
    if not allies:
        return None

    worst = max(pc.stress_marked for pc in allies)
    return random.choice([pc for pc in allies if pc.stress_marked == worst])


# --- Mass Enrapture ---------------------------------------------------------------

MASS_ENRAPTURE = "Mass Enrapture"

# How wide the sweep has to be before the spell is cast at all. Ruled: the card
# is taken for its second clause, and forcing a Stress on one or two adversaries
# is not worth a spotlight and a Stress.
MASS_ENRAPTURE_WORTH_IT = 3


@action(
    MASS_ENRAPTURE,
    unmodelled=[
        "'against all targets within Far range' - no positions are tracked, so "
        "the area rule in SIMULATION-RULES.md decides how many the sweep catches",
        "The Enrapture itself never gets to do anything. Under the ruling the "
        "spell is only cast when the Stress that **ends** it can be paid, so the "
        "condition is applied and cleared inside one action and no adversary ever "
        "spends a spotlight compelled by it. The card's lasting half is therefore "
        "unreachable by design rather than unimplemented - `Enrapture` at level 1 "
        "is the card that keeps its condition",
        "An adversary already Enraptured is skipped entirely, per the standing "
        "don't-re-apply rule, so it takes no Stress from this either. That also "
        "keeps the two cards from interfering: without it, a mass cast would clear "
        "a compulsion Enrapture had bought and paid for",
    ],
)
def mass_enrapture(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Mass Enrapture (Grace, level 8). Catch the field's attention, then break it.

    SRD: "Make a Spellcast Roll against all targets within Far range. Targets you
    succeed against become temporarily *Enraptured*. While *Enraptured*, a
    target's attention is fixed on you, narrowing their field of view and drowning
    out any sound but your voice. **Mark a Stress** to force all *Enraptured*
    targets to mark a Stress, ending this spell."

    One roll against the whole area, each adversary checked against its own
    Difficulty - the Wild Flame shape, and the widest band any party card sweeps.

    SIMULATION RULE - policy, ruled. **The cast and the Stress are one move.** The
    user's ruling is that the card is only worth taking for its second clause here,
    so it is cast only when the Far band holds `MASS_ENRAPTURE_WORTH_IT` or more
    *and* the shared last-slot rule allows the Stress - and then the Stress is
    spent immediately, forcing one on everything the roll caught and ending the
    spell. So this resolves as an area attack on the GM's Stress tracks rather than
    as a lasting compulsion, which is what the declared gap above records.

    Both gates are checked **before** the roll and paid after it, so declining
    costs nothing - the arrangement every gated area card here uses.

    Worth knowing what filling an adversary's Stress buys, since it is the whole
    of the card: an adversary with no free Stress cannot pay for its Action
    features. It does **not** make them Vulnerable - `Adversary.is_vulnerable` is
    always False, which SIMULATION-RULES.md records beside Grace-Touched.
    """
    if fight is None:
        return None

    area = [
        adversary
        for adversary in targets_in_area(Range.FAR, fight.living_adversaries)
        if not fight.has_condition(adversary, ENRAPTURED)
    ]
    if len(area) < MASS_ENRAPTURE_WORTH_IT:
        return None
    if not caster.will_spend_stress(1):
        return None

    attack_roll = spellcast(caster, target, fight, difficulty=area_difficulty(area))
    if attack_roll is None:
        return None

    caught = targets_beaten(attack_roll, area)
    if not caught:
        fight.note(f"{caster.name}'s voice reaches nobody ({attack_roll})")
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    for adversary in caught:
        fight.apply_condition(
            adversary,
            Condition(name=ENRAPTURED, end=when_the_gm_pays, source=caster),
        )
    fight.note(f"{caster.name} enraptures {len(caught)} adversaries")

    # The second clause, taken at once - the Stress the cast was gated on. Only
    # the adversaries this spell enraptured are forced and released, so a target
    # held by Enrapture keeps its compulsion.
    caster.spend_stress(1)
    for adversary in caught:
        adversary.mark_stress(1)
        fight.clear_condition(adversary, ENRAPTURED)
    fight.note(
        f"{caster.name} breaks the spell, costing {len(caught)} adversaries a Stress"
    )
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


# --- Assessed rather than built ----------------------------------------------

no_combat_effect(
    "Astral Projection",
    "Once per long rest, a Stress creates a projected copy of the caster that can "
    "appear anywhere they have been before, seeing, hearing and affecting the "
    "world as though they were there, until their next rest or the projection "
    "takes damage. Remote sensing somewhere the party is not fighting, which is "
    "the standing answer Floating Eye and Through Your Eyes already have - and "
    "the projection appearing 'anywhere you've been before' puts it outside the "
    "encounter by construction. At a table it is a scout, an alibi and a "
    "conversation held from another building; here there is nothing for it to "
    "touch.",
)

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
no_combat_effect(
    "Thought Delver",
    "A Hope reads the vague surface thoughts of a target within Far range, and a "
    "Spellcast Roll delves for deeper ones; on a roll with Fear the target may "
    "notice. Its whole output is information about what somebody is thinking, "
    "which is the Floating Eye and Through Your Eyes case - nothing in a fight "
    "turns on it, and the spell makes no attack, grants no roll and moves no "
    "number. Note that even the failure clause is fiction: being noticed reading "
    "somebody's mind has no mechanical consequence printed on the card.",
)
no_combat_effect(
    "Through Your Eyes",
    "See through a creature's eyes and hear through their ears anywhere within "
    "Very Far range, switching back to your own senses freely until the caster "
    "casts another spell. It produces information about places nobody is fighting "
    "in, which is the Floating Eye case exactly - and it makes no attack, grants "
    "no roll and touches nobody's numbers. At a table it is a scouting spell, and "
    "scouting is what happens before blades are out.",
)

no_combat_effect(
    "Endless Charisma",
    "After an action roll to persuade, lie, or garner favor, a Hope rerolls the "
    "Hope or the Fear Die. The reroll itself is fully represented - it is exactly "
    "Support Tank's mechanic, which the project already runs - so this is dismissed "
    "on its **trigger** rather than on the size of its effect, the way Gifted "
    "Tracker, Stealth Expertise and Know Thy Enemy are. The simulator makes attack "
    "rolls, Spellcast Rolls and Reaction Rolls; persuading, lying and currying "
    "favour are not among them, and the Presence Rolls it does make (Troublemaker, "
    "Goad Them On) are taunts rather than any of the three. If a social or "
    "negotiation step is ever added, this is a card waiting for it.",
)

out_of_combat_ability(
    "Soothing Speech",
    "During a rest, comforting another character while using the Tend to Wounds "
    "downtime move clears an additional Hit Point on them, and 2 Hit Points on "
    "the speaker. Not a dismissal: three Hit Points across two PCs is a large "
    "effect, and HP is the resource this simulator is built to measure. What the "
    "card is not is a combat move - it is gated on a downtime move taken during a "
    "rest, which is the one place a fight never is. So it belongs to the "
    "sequenced-encounter machinery that doesn't exist yet, and joins Inspirational "
    "Words above, Mending Touch and A Soldier's Bond on that list.",
)
