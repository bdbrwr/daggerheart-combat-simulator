"""Midnight domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json, checked against the printed page
(SRD p. 128).

The last domain ported at levels 1-2, and the one that leans hardest on rules
settled earlier: Rain of Blades takes the area shape Fire Flies established,
Midnight Spirit counts its dice off the Spellcast trait the way the Beastbound
companion does, and Shadowbind's whole effect turns out to be the Fear the GM
must spend to undo it.

Level 3 adds the two cards that mark somebody rather than hurting them.
**Chokehold** is the first party content that pays out on *anybody's* attack
rather than its holder's, and **Veil of Night** is the first thing that makes a
PC Hidden - a condition the simulator has modelled since Cloaked, on a side of
the table nothing had ever applied it to.
"""

from combat.results import AttackResult
from content.aoe import Range, area_difficulty, targets_beaten, targets_in_area
from content.conditions import (
    HIDDEN,
    RESTRAINED,
    VULNERABLE,
    WHEN_THEY_ACT,
    Condition,
    when_the_gm_pays,
)
from content.damage_types import DamageType
from content.registry import (
    Fight,
    Holder,
    action,
    ally_extra_damage,
    attack_advantage,
    free,
    no_combat_effect,
    total_extra_damage,
)
from content.spellcast import spellcast
from dice.common import AdvantageState
from dice.damage import DiceGroup, roll_damage

CHOKEHOLD = "Chokehold"

# Marks the adversary this card has hold of, so the extra dice ride attacks on
# *that* creature rather than on anything the party happens to find Vulnerable.
CHOKED = "Chokehold held"

CHOKEHOLD_DICE = 2
CHOKEHOLD_DIE = 6

VEIL_OF_NIGHT = "Veil of Night"

VEIL_DIFFICULTY = 13

# Set on the caster while the veil stands. Also what tells the ender to let the
# casting itself pass - see `_veil_lifts`.
VEILED = "Veil of Night standing"

# --- Rain of Blades ----------------------------------------------------------

RAIN_OF_BLADES = "Rain of Blades"

RAIN_OF_BLADES_DIE = 8
RAIN_OF_BLADES_MODIFIER = 2

# The extra die a Vulnerable target takes, rolled per target rather than once.
VULNERABLE_DIE = 8

# A Hope for one roll wants to be catching several. Below this it is a worse
# weapon swing that also costs a Hope - the same line Fire Flies draws.
RAIN_OF_BLADES_WORTH_IT = 2


@action(
    RAIN_OF_BLADES,
    unmodelled=[
        "'all targets within Very Close range' - no positions are tracked, so "
        "the area rule in SIMULATION-RULES.md decides how many are caught",
    ],
)
def rain_of_blades(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Rain of Blades (Midnight, level 1).

    SRD: spend a Hope to make a Spellcast Roll and conjure throwing blades that
    strike out at all targets within Very Close range. Targets you succeed
    against take d8+2 magic damage using your Proficiency. If a target you hit is
    Vulnerable, they take an extra 1d8 damage.

    The Fire Flies shape: one roll made against the whole area at once, each
    adversary then checked against its own Difficulty, and the damage dealt to
    every one the roll beat.

    SIMULATION RULE - policy, ruled. Declines unless it would reach two or more
    adversaries, exactly as Fire Flies does and for the same reason - a Hope
    spent to hit one target is a worse weapon swing. Very Close reaches `n // 3`
    held to two, so on a small field this card often waits.

    **The Vulnerable rider is rolled per target**, not once for the sweep. It has
    to be: the card asks about each target's own condition, and a shared roll
    would either hand the extra die to adversaries who don't qualify or deny it
    to ones who do. Each target's total still meets its thresholds exactly once.
    """
    if not caster.can_spend_hope(1):
        return None

    area = targets_in_area(Range.VERY_CLOSE, fight.living_adversaries)
    if len(area) < RAIN_OF_BLADES_WORTH_IT:
        return None

    attack_roll = spellcast(caster, target, fight, difficulty=area_difficulty(area))
    if attack_roll is None:
        return None

    caster.spend_hope(1)

    caught = targets_beaten(attack_roll, area)
    if not caught:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=caster.proficiency, sides=RAIN_OF_BLADES_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=RAIN_OF_BLADES_MODIFIER,
        is_critical=attack_roll.is_critical,
    )

    marked = 0
    for adversary in caught:
        dealt = damage_roll.total
        if fight.is_vulnerable(adversary):
            extra = roll_damage(dice_groups=[DiceGroup(count=1, sides=VULNERABLE_DIE)])
            dealt += extra.total
        marked += adversary.take_damage(dealt, fight, damage_type=DamageType.MAGIC)

    fight.note(
        f"{caster.name} looses a rain of blades, catching {len(caught)} "
        f"for {damage_roll.total} each"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


# --- Midnight Spirit ---------------------------------------------------------

MIDNIGHT_SPIRIT = "Midnight Spirit"

SPIRIT_DIE = 6


@action(
    MIDNIGHT_SPIRIT,
    unmodelled=[
        "The spirit's other half - moving and carrying things until your next "
        "rest. Only the attack is a fight",
        "'You can only have one spirit at a time' - the spirit dissipates the "
        "moment it attacks, which is the only thing it does here, so the limit "
        "never binds",
        "'within Very Far range' - no positions are tracked",
    ],
)
def midnight_spirit(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Midnight Spirit (Midnight, level 2).

    SRD: spend a Hope to summon a humanoid-sized spirit. You can send it to
    attack an adversary: make a Spellcast Roll against a target within Very Far
    range, and on a success the spirit moves into Melee with them, deals a number
    of d6s equal to your Spellcast trait in magic damage, then dissipates.

    Summoning and attacking are one action here, because the spirit does nothing
    else the simulator can see and the attack consumes it either way. The Hope is
    spent on the summoning, so it goes whether or not the roll lands - which is
    what the card says, and what makes this a real cost rather than a rider.

    Dice counted off the **Spellcast trait**, so this scales with the stat the
    caster already leans on rather than with Proficiency. A trait of zero or less
    rolls nothing, per the SRD's rule for trait-counted dice, and the card
    declines rather than spending a Hope on no dice at all.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None

    dice = caster.traits[trait]
    if dice <= 0:
        return None
    if not caster.can_spend_hope(1):
        return None

    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    caster.spend_hope(1)

    if not attack_roll.is_success:
        fight.note(f"{caster.name}'s spirit misses {target.name} and dissipates")
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=dice, sides=SPIRIT_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        is_critical=attack_roll.is_critical,
    )
    marked = target.take_damage(damage_roll.total, fight, damage_type=DamageType.MAGIC)
    fight.note(
        f"{caster.name}'s spirit strikes {target.name} for {damage_roll.total}"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


# --- Shadowbind --------------------------------------------------------------

SHADOWBIND = "Shadowbind"


@action(
    SHADOWBIND,
    unmodelled=[
        "'all adversaries within Very Close range' - no positions are tracked, "
        "so the area rule decides how many are caught",
        "Being Restrained itself, which is ruled to have no effect of its own "
        "here because no movement is modelled. So the whole value of this card "
        "is the Fear the GM must spend to clear it - one per adversary bound",
    ],
)
def shadowbind(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Shadowbind (Midnight, level 2).

    SRD: make a Spellcast Roll against all adversaries within Very Close range.
    Targets you succeed against are temporarily Restrained as their shadow binds
    them in place.

    **Worth being plain about what this comes to.** Restrained stops a combatant
    moving and no movement is modelled, so the condition does nothing by itself -
    that is a ruling made long before this card. What a condition the party puts
    on an adversary *does* cost is a Fear, spent on the GM's turn to shake it
    off. So Shadowbind is a Fear-burner: bind three adversaries and the GM pays
    three Fear, or leaves them bound and pays nothing because being bound costs
    them nothing. That is a real effect on the pool the GM buys activations with,
    and it is not the control spell the page describes.

    Costs nothing but the roll, so it never declines except when there is nobody
    left to bind - every adversary in reach already being Restrained is the one
    state where casting buys nothing at all.
    """
    area = [
        adversary
        for adversary in targets_in_area(Range.VERY_CLOSE, fight.living_adversaries)
        if not fight.has_condition(adversary, RESTRAINED)
    ]
    if not area:
        return None

    attack_roll = spellcast(caster, target, fight, difficulty=area_difficulty(area))
    if attack_roll is None:
        return None

    bound = targets_beaten(attack_roll, area)
    for adversary in bound:
        fight.apply_condition(
            adversary,
            Condition(name=RESTRAINED, end=when_the_gm_pays, source=caster),
        )
    if bound:
        fight.note(
            f"{caster.name} binds {len(bound)} adversaries with their own shadows"
        )
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


# --- Chokehold ---------------------------------------------------------------


@free(
    CHOKEHOLD,
    unmodelled=[
        "'when you position yourself behind a creature who's about your size' - "
        "neither positioning nor creature size is represented, so the hold is "
        "always available. Both are real restrictions at a table: half of what "
        "makes this card a choice is that the thing has to be reachable and "
        "roughly person-shaped",
        "Damage rolled by anything other than a weapon - a card that rolls its "
        "own dice doesn't consult the party-wide extra-damage hook, so the 2d6 "
        "rides weapon swings only",
    ],
)
def chokehold(holder: Holder, fight: Fight) -> bool:
    """Chokehold (Midnight, level 3). Mark a Stress to take hold of somebody.

    SRD: "When you position yourself behind a creature who's about your size, you
    can mark a Stress to pull them into a chokehold, making them temporarily
    Vulnerable. When a creature attacks a target who is Vulnerable in this way,
    they deal an extra 2d6 damage."

    **No roll**, which is what makes it a free ability: it costs a Stress and
    nothing else, so it doesn't spend the spotlight's action roll and the PC can
    choke somebody *and* attack them in the same spotlight.

    SIMULATION RULE - policy, ruled. The hold goes on **the party's focus
    target** - the adversary with the most HP marked, which is the rule
    `choose_pc_target` follows - so the 2d6 lands where the party is already
    swinging. That does mean this module restates the focus rule rather than
    calling it; `combat/policy.py` imports `content/`, so the dependency cannot
    run the other way.

    Skips a target already Vulnerable, per the standing rule that a feature whose
    point is a condition is not used on somebody who has it. Note what that costs
    here and why it is still right: the 2d6 rider is tied to being Vulnerable
    *in this way*, so a target Vulnerable from something else gets no dice - but
    re-applying a condition somebody already has is exactly the thing the rule
    forbids, and the alternative would be Chokehold overwriting a Bolt Beacon's
    Vulnerable to claim the same slot.

    "Temporarily" is the party putting a condition on an adversary, so it lifts
    when the GM spends a Fear - and the extra dice go with it, since the token is
    cleared alongside.
    """
    if fight is None or not holder.will_spend_stress(1):
        return False

    living = fight.living_adversaries
    if not living:
        return False

    candidates = [
        adversary
        for adversary in living
        if not fight.is_vulnerable(adversary) and not fight.token_count(adversary, CHOKED)
    ]
    if not candidates:
        return False

    target = max(candidates, key=lambda adversary: adversary.hp_marked)

    holder.spend_stress(1)
    fight.set_token(target, CHOKED, 1)
    fight.apply_condition(
        target, Condition(name=VULNERABLE, end=_chokehold_breaks, source=holder)
    )
    fight.note(f"{holder.name} drags {target.name} into a chokehold")
    return True


def _chokehold_breaks(holder, fight: Fight, moment: str) -> bool:
    """The GM pays a Fear to break the hold, and the extra dice stop with it.

    Wraps the standing `when_the_gm_pays` rather than replacing it, so the
    duration is the same one every other condition the party applies gets. What
    this adds is clearing the token, so nothing keeps paying out 2d6 against a
    creature that is no longer held.
    """
    if not when_the_gm_pays(holder, fight, moment):
        return False
    fight.set_token(holder, CHOKED, 0)
    return True


@ally_extra_damage(CHOKEHOLD)
def chokehold_bites(
    holder: Holder, attacker, target, roll, fight: Fight = None
) -> list[DiceGroup]:
    """Chokehold's 2d6 for whoever swings at the creature being held.

    The card says "when **a creature** attacks a target who is Vulnerable in this
    way", not "when you attack" - so this is registered party-wide and pays out
    on any PC's swing, not only the choker's. Registered holder-scoped it would
    have been a card that helps nobody but its owner, which is a different and
    much smaller card.

    Keyed on the token rather than on the condition, because "Vulnerable **in
    this way**" is narrower than being Vulnerable: a target a Bolt Beacon lit up
    is Vulnerable and is not in a chokehold.

    `discardable=False`, like every die a feature lends to somebody else's roll -
    a Massive or Powerful weapon discards the lowest of the dice *it* rolled, and
    these are not among them.

    The dice are not spent or consumed: the hold pays out on every attack for as
    long as it lasts, which is what makes the GM's Fear worth spending on it.
    """
    if fight is None or not fight.token_count(target, CHOKED):
        return []
    return [DiceGroup(count=CHOKEHOLD_DICE, sides=CHOKEHOLD_DIE, discardable=False)]


# --- Veil of Night -----------------------------------------------------------


@action(
    VEIL_OF_NIGHT,
    unmodelled=[
        "'between two points within Far range' and 'adversaries on the other "
        "side of the veil' - no positions are tracked, so the curtain has no "
        "geometry and every adversary is treated as being on the far side of it",
        "Being Hidden stopping a combatant being targeted at all - only the "
        "Disadvantage is modelled, so focus fire still picks the caster as "
        "readily as anybody. The same gap Cloaked declares",
    ],
)
def veil_of_night(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Veil of Night (Midnight, level 3).

    SRD: make a Spellcast Roll (13). On a success, create a temporary curtain of
    darkness between two points within Far range. Only you can see through this
    darkness. You're considered Hidden to adversaries on the other side of the
    veil, and you have advantage on attacks you make through the darkness. The
    veil remains until you cast another spell.

    Both halves are modelled: Hidden gives every roll against the caster
    Disadvantage, and the Advantage rides their next attack through
    `attack_advantage`.

    SIMULATION RULE - rules interpretation, ruled. **The veil holds until the
    caster's next action resolves** - the `WHEN_THEY_ACT` moment the loop already
    announces, skipping the casting itself. What that comes to is one GM turn
    spent Hidden and then one attack made with Advantage, which is what the card
    buys before a caster would realistically cast anything else.

    The ruling was made when "until you cast another spell" could not be detected
    at all: each domain module carried its own `_spellcast` helper and there was
    no one place a cast passed through. **There is now** - `content/spellcast.py`
    - so the literal reading has become implementable, and the difference is that
    a veiled PC swinging a weapon would keep the darkness where they currently
    lose it. Left as ruled rather than quietly changed; worth revisiting if the
    numbers make the card look weak.

    Declines while a veil is already standing: re-casting would buy nothing, and
    at a table casting Veil of Night again is what *ends* the first one.

    Costs the caster their whole action roll and nothing else - no Hope, no
    Stress. The price is the spotlight.
    """
    if fight.token_count(caster, VEILED):
        return None

    attack_roll = spellcast(caster, target, fight, difficulty=VEIL_DIFFICULTY)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    # Two, not one: the ender reads this to tell the casting itself from the
    # caster's *next* action, and a plain flag could not say which.
    fight.set_token(caster, VEILED, 2)
    fight.apply_condition(
        caster, Condition(name=HIDDEN, end=_veil_lifts, source=caster)
    )
    fight.note(f"{caster.name} draws a curtain of darkness and is lost in it")
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


def _veil_lifts(holder, fight: Fight, moment: str) -> bool:
    """Ends at the caster's next action - not the one that cast it.

    The loop announces `WHEN_THEY_ACT` immediately after the spotlight that
    created the veil, so a plain `when_they_act` would end it before the GM ever
    got a turn. The token counts down instead: the casting spends the first, the
    caster's next action spends the last, and expiry happens *after* that action
    resolves - so the attack the veil was drawn for is made with Advantage and
    the darkness lifts behind it.
    """
    if moment != WHEN_THEY_ACT:
        return False
    fight.spend_tokens(holder, VEILED, 1)
    return fight.token_count(holder, VEILED) <= 0


@attack_advantage(VEIL_OF_NIGHT)
def veil_hides_the_blade(attacker: Holder, target, fight: Fight):
    """Advantage on an attack made through the darkness.

    Only while the veil stands, which is the token. Folded together with
    everything else by `combined`, so a veiled PC swinging at something Hidden
    comes out even rather than keeping the Advantage outright.

    Being asked is the commitment for this hook, and that is fine here because
    the veil is not consumed by being used - it is spent by the *action*, which
    the condition's ender counts separately.
    """
    if fight is None or not fight.token_count(attacker, VEILED):
        return None
    return AdvantageState.ADVANTAGE


# --- Assessed and dismissed --------------------------------------------------

no_combat_effect(
    "Pick and Pull",
    "Advantage on action rolls to pick nonmagical locks, disarm nonmagical "
    "traps, or steal items from a target. Locks, traps and inventories are all "
    "outside a simulated fight, so there is no roll here for the advantage to "
    "land on.",
)
no_combat_effect(
    "Uncanny Disguise",
    "A Stress and a few minutes' preparation to wear another humanoid's face, "
    "with advantage on Presence Rolls to avoid scrutiny while the tokens last. "
    "Both halves are outside a fight: the preparation cannot happen during one, "
    "and being disguised would change nothing once blades are out - adversaries "
    "in an encounter are already hostile and already swinging. Distinct from "
    "Mending Touch, which is deferred rather than dismissed because its effect "
    "*would* matter if it could be used.",
)
