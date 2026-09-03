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

Level 4 brings **Glyph of Nightfall**, which is Sage's Corrosive Projectile with
the opposite duration - and that difference is the whole of what it costs to
write. A permanent reduction is simply a smaller number on the stat block; a
temporary one has to be given back, so the card carries a condition whose only
job is to time it.

Level 5's **Hush** brings *Silenced*, the first condition whose effect is settled
per holder when it lands - it stops an adversary whose printed attack is magic and
leaves everybody else merely conditioned. It is also the first party-applied
condition anywhere that can lift **without the GM paying a Fear**, since the card
prints an ender that reaches the caster rather than the holder.

Level 6 reaches no fight at all: Dark Whispers is a conversation and four
questions for the GM, Mass Disguise is minutes of silence and Presence Rolls.
Midnight joins Grace's level 4 as a domain whose whole level is declared rather
than built - and, like that one, it is worth recording so it does not read as an
omission.

Level 7 puts the domain back in the fight twice over. **Midnight-Touched** is the
first card anywhere that stops the GM gaining a Fear, and the first to read the
Fear Die's own result as damage - which is what gave `damage_pool` the attack roll.
**Vanishing Dodge** is the third card on the missed-attack trigger after Redirect
and Rapid Riposte, and the first to answer a miss with something other than damage.

Level 8 splits the same way level 6 did, but only halfway. **Spellcharge** turns
magic damage taken into damage dealt, and is the first card anywhere that needed
`on_damaged` to know what **type** the hit was. **Shadowhunter** is dismissed on
its trigger - low light and darkness, which the simulator holds no fact about -
and it is worth reading that dismissal carefully, since the effect it turns off is
one of the largest in the domain.
"""

from combat.results import AttackResult
from content.aoe import Range, area_difficulty, targets_beaten, targets_in_area
from content.conditions import (
    HIDDEN,
    RESTRAINED,
    SILENCED,
    VULNERABLE,
    WHEN_THEY_ACT,
    Condition,
    when_the_gm_pays,
    when_they_attack,
)
from content.damage_types import DamageType, damage_type_named, includes, types_in
from content.registry import (
    DamagePool,
    Fight,
    Holder,
    action,
    ally_extra_damage,
    attack_advantage,
    attack_missed,
    damage_pool,
    extra_damage,
    fear_conversion,
    free,
    no_combat_effect,
    on_damaged,
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


# --- Glyph of Nightfall ------------------------------------------------------

GLYPH_OF_NIGHTFALL = "Glyph of Nightfall"

# The card gives the state no name of its own - it just says "temporarily" - so
# one is taken here. The condition carries no effect: what it does is already
# written into the stat block's Difficulty, and this record exists purely to say
# how long that lasts and to hand the points back when it ends.
GLYPHED = "Glyphed"

# How many points this particular glyph took off, kept so exactly that much is
# restored. A number rather than a count, which is what `set_token` is for.
GLYPH_REDUCTION = "Glyph of Nightfall reduction"

# The lowest a Difficulty may be driven. `domain_cards/sage.py` carries its own
# constant of the same name for Corrosive Projectile, deliberately duplicated
# rather than shared: one card must never import another card's module.
MINIMUM_DIFFICULTY = 1


@action(
    GLYPH_OF_NIGHTFALL,
    unmodelled=[
        "'within Very Close range' - no positions are tracked, so the glyph "
        "always reaches whoever the party is focusing",
    ],
)
def glyph_of_nightfall(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Glyph of Nightfall (Midnight, level 4).

    SRD: "Make a Spellcast Roll against a target within Very Close range. On a
    success, spend a Hope to conjure a dark glyph upon their body that exposes
    their weak points, temporarily reducing the target's Difficulty by a value
    equal to your Knowledge (minimum 1)."

    **Corrosive Projectile's effect with the opposite duration**, and the
    difference is the whole of what is interesting about it. That card says
    *permanently*, so it writes the new number into the spawned stat block and
    nothing has to remember anything. This one says *temporarily*, which for a
    condition the party puts on an adversary is the standing reading: it lifts
    when the GM spends a Fear on their turn. So the points have to be given back,
    and `_glyph_fades` is what does it.

    The Difficulty is still moved by writing to the stat block rather than by
    being consulted per roll, for the reason `difficulty_bonus` gives: Difficulty
    is read in four places that have no fight to dispatch with. The condition is
    the timer, not the effect.

    **"Minimum 1" is on the reduction, not on the result** - it is the Knowledge
    value that floors at one, which matters for a caster with a Knowledge of 0 or
    less. A separate floor stops the Difficulty itself being driven below
    `MINIMUM_DIFFICULTY`, and the card declines when there is nothing left to
    take.

    SIMULATION RULE - policy. The Hope is what conjures the glyph rather than an
    upgrade to it - "on a success, **spend a Hope** to conjure" puts the whole
    effect inside the payment - so a caster with none declines before rolling
    rather than rolling and then failing to pay. That is the Bolt Beacon reading.
    Skips a target already glyphed, per the standing rule that a feature whose
    point is a condition is not used on somebody who has it; the consequence here
    is that the reduction does not stack, where Corrosive Projectile's does.

    Deals no damage at all, which makes it the second Midnight card whose whole
    output is what it does to the other side's numbers.
    """
    if fight is None or not caster.can_spend_hope(1):
        return None
    if fight.has_condition(target, GLYPHED):
        return None

    reduction = min(
        max(caster.traits.get("knowledge", 0), 1),
        target.difficulty - MINIMUM_DIFFICULTY,
    )
    if reduction <= 0:
        return None

    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    caster.spend_hope(1)

    # Applied *before* the Difficulty moves, and then checked. The condition is
    # what gives the points back, so anything that refused it would otherwise
    # leave the reduction permanent - which is the one outcome the card does not
    # allow. `apply_condition` narrates a refusal itself.
    fight.apply_condition(
        target, Condition(name=GLYPHED, end=_glyph_fades, source=caster)
    )
    if not fight.has_condition(target, GLYPHED):
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    target.difficulty -= reduction
    fight.set_token(target, GLYPH_REDUCTION, reduction)
    fight.note(
        f"{caster.name} marks {target.name} with a glyph of nightfall "
        f"(Difficulty {target.difficulty + reduction} to {target.difficulty})"
    )
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


def _glyph_fades(holder, fight: Fight, moment: str) -> bool:
    """The GM pays a Fear to scrub the glyph off, and the Difficulty comes back.

    Wraps the standing `when_the_gm_pays` rather than replacing it, exactly as
    `_chokehold_breaks` does, so the duration is the one every condition the party
    applies gets. What this adds is restoring the stat block: the reduction was
    written into `difficulty`, and only the number recorded when it landed can put
    it back - a glyph that took 2 must not hand back 3 because the caster's
    Knowledge changed, and two sources moving the same Difficulty must each undo
    their own.
    """
    if not when_the_gm_pays(holder, fight, moment):
        return False

    given_back = fight.token_count(holder, GLYPH_REDUCTION)
    fight.set_token(holder, GLYPH_REDUCTION, 0)
    holder.difficulty += given_back
    return True


# --- Hush --------------------------------------------------------------------

HUSH = "Hush"


@action(
    HUSH,
    unmodelled=[
        "'within Close range' for the target, and 'everything within Very Close "
        "range of them' for the area - no positions are tracked, so the area rule "
        "in SIMULATION-RULES.md decides how many the silence reaches, measured "
        "over the adversaries other than the target",
        "The silence **following the target as they move**, which is what makes "
        "this an area that travels rather than one that is placed. Nothing moves "
        "here, so who is caught is settled once when the spell lands",
        "'they can't make noise' - noise has no representation. Only the spell "
        "half of Silenced reaches a fight",
        "'or you cast Hush again' as an ender - the standing don't-re-apply rule "
        "already stops a second cast while a silence is standing, so the clause "
        "is unreachable rather than unimplemented",
    ],
)
def hush(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Hush (Midnight, level 5). Silence a target and everything around them.

    SRD: make a Spellcast Roll against a target within Close range. On a success,
    spend a Hope to conjure suppressive magic around the target that encompasses
    everything within Very Close range of them and follows them as they move. The
    target and anything within the area is *Silenced* until the GM spends a Fear
    on their turn to clear this condition, you cast Hush again, or you take Major
    damage. While *Silenced*, they can't make noise and can't cast spells.

    SIMULATION RULE - rules interpretation, ruled. **"Can't cast spells" is
    answered by the Counterspell rule**: magic damage is the only magic this
    simulator recognises, since nothing marks a feature as magical and damage is
    the one thing that carries a type. So the silence is asked, per target and at
    the moment it lands, whether that adversary's **printed attack deals magic
    damage**. If it does, the condition stops them acting, exactly as Stunned
    does - the activation and the Fear that bought it are both spent on nothing.
    If it doesn't, they are Silenced and inert, exactly as Restrained is, and the
    GM still has to pay a Fear each to clear it.

    Reading it as stopping *any* Action feature was offered and declined, as was
    leaving the condition inert for everybody.

    The Hope is what conjures the suppression, so a caster with none declines
    before rolling rather than spending the spotlight and failing to pay - the
    Bolt Beacon and Glyph of Nightfall reading. It is spent only on a success, as
    the card orders it.

    The third ender - the caster taking Major damage - **is** modelled, in
    `hush_breaks` below. That makes this the first party condition anywhere that
    the GM can end without paying for it.
    """
    if fight is None or not caster.can_spend_hope(1):
        return None
    if fight.has_condition(target, SILENCED):
        return None

    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    caster.spend_hope(1)

    others = [
        adversary for adversary in fight.living_adversaries if adversary is not target
    ]
    caught = [target] + targets_in_area(Range.VERY_CLOSE, others)
    for adversary in caught:
        fight.apply_condition(
            adversary,
            Condition(
                name=SILENCED,
                end=when_the_gm_pays,
                source=caster,
                prevents_action=_casts_with_magic(adversary),
            ),
        )

    stopped = sum(1 for adversary in caught if _casts_with_magic(adversary))
    fight.note(
        f"{caster.name} hushes {len(caught)}, {stopped} of whom cannot act at all"
    )
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


def _casts_with_magic(adversary) -> bool:
    """Whether this adversary's printed attack is the kind of magic a silence stops.

    Read off the stat block's own damage type, which is the only handle the
    simulator has on whether anything is magical - the same reading Counterspell
    is built on. Decided once, when the condition lands, rather than asked again
    later: a stat block's printed type does not change mid-fight, and freezing it
    onto `Condition.prevents_action` is what lets the fight loop stay generic.

    The gap it leaves is an adversary whose *standard attack* is physical but
    whose Action feature deals magic damage. It is Silenced and inert, where the
    page would stop the feature.

    **The printed type is parsed before it is read.** `Adversary.damage_type` is
    the string a catalogue entry wrote - "magic", or "magic/physical" for a hit
    that is both - and `types_in` takes a resolved `DamageType`. Handing it the
    raw string put it through `frozenset("magic")`, a set of five *characters*,
    which no `DamageType` is ever a member of - so this silently answered False
    for every adversary in the catalogue and Hush stopped nobody acting. Fixed by
    parsing first, which is what `damage_type_named` is for.
    """
    return includes(
        damage_type_named(adversary.type_of_damage()), DamageType.MAGIC
    )


@on_damaged(HUSH)
def hush_breaks(
    holder: Holder,
    amount: int,
    hp_marked: int,
    fight: Fight,
    marked_armor: bool = False,
    damage_type=None,
) -> None:
    """Major damage to the caster tears the suppression apart.

    The card's third ender, and the only one in the project that lets a condition
    the party applied lift **without the GM paying for it**. Read on the damage
    *amount* against the caster's printed Major threshold, which is the standing
    reading of "takes Major damage" - the same one Get Back Up takes of "Severe".

    Only silences this caster raised are cleared. `release_conditions_from` would
    have taken everything they had applied, which would drop a Chokehold or a
    glyph off the same PC being hit, so the condition's `source` is checked one at
    a time instead.
    """
    if fight is None or amount < holder.major_threshold:
        return

    for adversary in fight.living_adversaries:
        silence = fight.condition_on(adversary, SILENCED)
        if silence is not None and silence.source is holder:
            fight.clear_condition(adversary, SILENCED)
            fight.note(f"{holder.name} reels, and {adversary.name} is no longer Silenced")


# --- Midnight-Touched ------------------------------------------------------------

MIDNIGHT_TOUCHED = "Midnight-Touched"

TOUCHED_LOADOUT_GAP = (
    "'When 4 or more of the domain cards in your loadout are from the Midnight "
    "domain' - the loadout is not counted. The user's ruling is that carrying the "
    "card is taken as proof the condition is met, since a player who takes it has "
    "built for it. Recorded as a simulation rule rather than checked"
)


@fear_conversion(MIDNIGHT_TOUCHED, unmodelled=[TOUCHED_LOADOUT_GAP])
def midnight_touched(holder: Holder, fight: Fight = None) -> bool:
    """Midnight-Touched (Midnight, level 7), first clause.

    SRD: "When 4 or more of the domain cards in your loadout are from the Midnight
    domain, gain the following benefits: once per rest, when you have 0 Hope and
    the GM would gain a Fear, you can gain a Hope instead; when you make a
    successful attack, you can mark a Stress to add the result of your Fear Die to
    your damage roll."

    **The card prints its own trigger exactly**, so there is no policy to rule: it
    fires at 0 Hope, on a roll that was about to hand the GM a Fear, and it has one
    use per rest. Nothing here weighs whether a better moment is coming, because 0
    Hope is already the worst one.

    Being asked is the commitment - the Fear is a line away from landing - so the
    per-rest use is claimed here and the Hope banked before returning True.

    Worth reading its numbers knowing it moves **two** resources at once: the GM's
    pool loses what is close to an extra activation, and the PC comes off the floor
    of a currency several of their cards need. Every other party card that touches
    the Fear pool pays *into* it or drains it by clearing a condition.
    """
    if fight is None or holder.hope_marked > 0:
        return False
    if not fight.use_once_per_rest(holder, MIDNIGHT_TOUCHED):
        return False

    holder.gain_hope(1)
    fight.note(
        f"{holder.name} turns the GM's Fear aside and takes a Hope from it instead"
    )
    return True


@damage_pool(
    MIDNIGHT_TOUCHED,
    unmodelled=[
        TOUCHED_LOADOUT_GAP,
        "Damage rolled by anything other than a weapon swing. "
        "`adjust_damage_pool` is asked from `items/weapons.py` and from the two "
        "cards that deal weapon damage without swinging, and content rolling "
        "Proficiency dice of its own never consults it - so a Midnight caster's "
        "spells carry no Fear Die. The same gap Voice of Reason and Never "
        "Upstaged declare",
    ],
)
def midnight_touched_bites(
    holder: Holder, weapon, pool: DamagePool, fight: Fight = None, roll=None
) -> DamagePool:
    """Midnight-Touched's second clause - the Fear Die, read again as damage.

    **On `damage_pool` rather than either damage hook next door**, which is Never
    Upstaged's argument with one thing added. "When you make a **successful**
    attack" rules out `damage_bonus`, asked before the dice are thrown; "the result
    of your Fear Die" is a flat number rather than dice, which rules out
    `extra_damage`. What is new is that the number is only knowable *from the roll*,
    and this hook could not see one until this card - which is why `damage_pool`
    now carries the attack roll.

    `roll` is None where the damage is not coming from an attack at all (Rapid
    Riposte, Glancing Blow), and the card declines there: no attack, no Fear Die.

    SIMULATION RULE - policy. The standing default for a Stress cost, which is what
    Reckless, Versatile Fighter and Rage Up all get: marked on every landed swing
    the shared last-slot rule allows. Worth knowing the size before reading the
    numbers - a Fear Die is a d12, so this averages +6.5 on a hit and is the
    largest per-Stress damage bonus in the project.

    Being asked is the commitment: the damage roll follows immediately, so the
    Stress is marked here.
    """
    if fight is None or roll is None:
        return pool

    fear = getattr(roll, "fear_die_result", None)
    if not fear or not holder.will_spend_stress(1):
        return pool

    holder.spend_stress(1)
    fight.note(f"{holder.name} marks a Stress; the Fear Die bites for +{fear}")
    return pool._replace(modifier=pool.modifier + fear)


# --- Vanishing Dodge -------------------------------------------------------------

VANISHING_DODGE = "Vanishing Dodge"


@attack_missed(
    VANISHING_DODGE,
    unmodelled=[
        "'teleporting to a point within Close range of the attacker' - pure "
        "repositioning, and no positions are tracked. What is modelled is the "
        "Hidden it comes wrapped in",
        "An adversary's **area** attack. Only the PC the attack was aimed at is "
        "announced as having been missed, so a swept attack that failed against "
        "several is dodged by at most one of them. Redirect and Rapid Riposte "
        "declare the same gap for the same reason",
    ],
)
def vanishing_dodge(holder: Holder, attacker, roll, fight: Fight = None) -> None:
    """Vanishing Dodge (Midnight, level 7). A miss buys a Hope's worth of shadow.

    SRD: "When an attack made against you that would deal physical damage fails,
    you can spend a Hope to envelop yourself in shadow, becoming *Hidden* and
    teleporting to a point within Close range of the attacker. You remain Hidden
    until the next time you make an action roll."

    **The third card on this trigger**, after Redirect and Rapid Riposte, and the
    first that answers a miss with something other than damage. All three read what
    they need off the attacker's stat block rather than off any position: those two
    read the printed range band, and this one reads the printed **damage type**,
    since "would deal physical damage" is a fact about the attack that never
    landed.

    "Until the next time you make an action roll" is the `WHEN_THEY_ATTACK` moment,
    and this is the card that moment is **literally** right for - Cloaking Blast,
    which it was built for, means "until you attack" and settles for this as an
    approximation. Here the page and the loop say the same thing.

    SIMULATION RULE - policy. The standing default for a rider costing a single
    Hope: spent whenever the trigger fires and the PC is not already Hidden.
    Holding it for a better miss would mean holding it for a miss that looks no
    different, since nothing about the failed attack tells the PC what comes next.
    """
    if fight is None or not holder.can_spend_hope(1):
        return
    if fight.is_hidden(holder):
        return
    # Parsed before it is read - `Adversary.damage_type` is the string a catalogue
    # entry wrote, and `includes` wants a resolved type. See `_casts_with_magic`,
    # which had this wrong.
    if not includes(damage_type_named(attacker.type_of_damage()), DamageType.PHYSICAL):
        return

    holder.spend_hope(1)
    fight.apply_condition(
        holder, Condition(name=HIDDEN, end=when_they_attack, source=holder)
    )
    fight.note(f"{holder.name} slips into shadow as the blow goes wide")


# --- Spellcharge -----------------------------------------------------------------

SPELLCHARGE = "Spellcharge"

# The pool, held on the caster. A count rather than a flag, and capped at the
# caster's Spellcast trait, which is what the card prints.
SPELLCHARGE_TOKENS = "Spellcharge tokens"

SPELLCHARGE_DIE = 6


@on_damaged(
    SPELLCHARGE,
    unmodelled=[
        "Magic damage that marks **no** HP banks nothing, which is the card read "
        "literally - 'tokens equal to the number of Hit Points you marked'. So a "
        "magic hit an Armor Slot swallowed whole charges the card with nothing, "
        "the same way Never Upstaged banks nothing off one",
    ],
)
def spellcharge(
    holder: Holder,
    amount: int,
    hp_marked: int,
    fight: Fight = None,
    marked_armor: bool = False,
    damage_type=None,
) -> None:
    """Spellcharge (Midnight, level 8), first half - the pool magic damage fills.

    SRD: "When you take magic damage, place tokens equal to the number of Hit
    Points you marked on this card. You can store a number of tokens equal to your
    Spellcast trait. When you make a successful attack against a target, you can
    spend any number of tokens to add a **d6** for each token spent to your damage
    roll."

    **The first registrant that needed `on_damaged` to carry the damage type**,
    and the reason it does. The trigger names the type and the payload names the
    HP finally marked, and this is the only hook that has both: `severity_response`
    sees the type while the figure is still being settled, and this one saw the
    settled figure and no type. Reading the type off the spotlighted adversary's
    printed attack instead would be wrong for any feature that states its own -
    the inference `marked_armor` was added to avoid.

    Capped at the caster's Spellcast trait, as the card says. A PC with no
    Spellcast trait, or one of zero or less, stores nothing and the card is inert -
    the same reading Unleash Chaos and Preservation Blast take of a card whose size
    is drawn from a trait.

    No policy to rule on for this half: the card states its own trigger and the
    tokens cost nothing to bank.
    """
    if fight is None or hp_marked <= 0:
        return
    if DamageType.MAGIC not in types_in(damage_type):
        return

    trait = getattr(holder, "spellcast_trait", "")
    if not trait or trait not in holder.traits:
        return
    capacity = holder.traits[trait]
    if capacity <= 0:
        return

    stored = min(fight.token_count(holder, SPELLCHARGE_TOKENS) + hp_marked, capacity)
    fight.set_token(holder, SPELLCHARGE_TOKENS, stored)
    fight.note(f"{holder.name}'s spellcharge holds {stored}")


@extra_damage(SPELLCHARGE)
def spellcharge_discharges(
    holder: Holder, target, roll, fight: Fight = None
) -> list:
    """Spellcharge's second half - the pool spent on a landed attack.

    Registered on the same name as the collector above, which is how one card
    reaches two hooks - Ferocity's, Boost's and Signature Move's arrangement.

    SIMULATION RULE - policy, ruled. **Every token on every landing attack**, which
    is Unleash Chaos's rule for the same "spend any number" wording. So the pool
    empties as soon as there is an attack to spend it on and refills the next time
    magic lands; nothing is left banked when a fight ends. Holding until the pool
    was full, and spending the fewest that could cross a threshold band, were both
    offered and declined.

    Asked from inside the damage roll of an attack that has already succeeded, so
    "when you make a successful attack" comes for free and the dice cross the
    target's thresholds exactly once. It is holder-scoped and asked wherever a PC's
    content rolls damage, so unlike a weapon-only rider this also reaches a
    Grimoire spell's damage - which is what "a successful attack" says.

    `discardable=False`, like every die a feature adds to somebody else's roll.
    """
    if fight is None:
        return []

    tokens = fight.spend_tokens(
        holder, SPELLCHARGE_TOKENS, fight.token_count(holder, SPELLCHARGE_TOKENS)
    )
    if not tokens:
        return []

    fight.note(f"{holder.name} discharges {tokens}d6 into the blow")
    return [DiceGroup(count=tokens, sides=SPELLCHARGE_DIE, discardable=False)]


# --- Assessed and dismissed --------------------------------------------------

no_combat_effect(
    "Shadowhunter",
    "While shrouded in low light or darkness, +1 to Evasion and attack rolls made "
    "with advantage. **Dismissed on its trigger, not on the size of its effect** - "
    "which is the Gifted Tracker reading, and worth being plain about because the "
    "effect is one of the largest in the domain. Advantage on every attack roll "
    "would be enormous; what has no representation here is *when* it applies. "
    "Nothing records how a fight is lit, exactly as nothing records what the party "
    "tracked, and the simulator holds no fact about where an encounter happens. "
    "Reading it as always on - the ruling Sage-Touched's natural-environment "
    "clause got - was offered and declined, as was gating it on the holder being "
    "Hidden. If an encounter ever grows a 'this fight is in darkness' field, this "
    "is the card waiting for it.",
)
no_combat_effect(
    "Stealth Expertise",
    "A Stress turns a roll with Fear into a roll with Hope while attempting to "
    "move unnoticed through a dangerous area, for the holder or for an ally "
    "within Close range doing the same. The *effect* is one of the largest a card "
    "could have - a roll's Hope or Fear decides who gains what and whether the "
    "party keeps the spotlight - but the **trigger** has no representation here: "
    "the simulator makes attack rolls, Spellcast Rolls and Reaction Rolls, and "
    "never rolls to move unnoticed through anywhere. Dismissed on the trigger, "
    "the way Gifted Tracker was, and not on the size of the effect.",
)
no_combat_effect(
    "Phantom Retreat",
    "A Hope activates the spell where the caster is standing, and another Hope at "
    "any time before their next rest makes them disappear and reappear on that "
    "spot; the spell then ends. Its whole effect is where somebody is standing, "
    "and no positions are tracked - the Blink Out case with a delay attached. "
    "Worth knowing that modelling it would make a party *worse*, since the two "
    "Hope would buy nothing here, and that at a table this is one of the strongest "
    "escapes in the domain: it is how a Rogue walks into a fight they intend to "
    "leave.",
)
no_combat_effect(
    "Dark Whispers",
    "Speak into the mind of anyone you have made physical contact with, and once "
    "the channel is open they can speak back; a Spellcast Roll additionally buys "
    "one answer from the GM - where they are, what they are doing, what they are "
    "afraid of, what they cherish most. Communication and information about people "
    "nobody is fighting, which is the Floating Eye and Through Your Eyes case: the "
    "spell makes no attack, grants no roll and moves no number. The four questions "
    "are worth naming because two of them sound tactical, and neither is: nothing "
    "in a simulated fight turns on an adversary's fears or attachments, and where "
    "they are is the one thing the area rule stands in for precisely because no "
    "positions are tracked.",
)
no_combat_effect(
    "Mass Disguise",
    "A few minutes of silence and a Stress redress every willing creature within "
    "Close range, their new forms sharing a general body structure and size; a "
    "disguised creature has advantage on Presence Rolls to avoid scrutiny, and a "
    "Countdown (8) the GM ticks ends it. Both halves are outside a fight - the "
    "minutes of focus cannot be found during one, and the advantage lands on "
    "Presence Rolls to avoid scrutiny, which the simulator never makes. The Uncanny "
    "Disguise ruling, applied to the same spell at party scale, and for the same "
    "reason: adversaries in an encounter are already hostile and already swinging. "
    "Deliberately **not** the out-of-combat state, which is for an effect that is "
    "real and merely mistimed - this one would still buy nothing once encounters "
    "are sequenced.",
)
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
