"""Codex domain cards.

Every Codex card through level 4 is a Grimoire - one card holding two or three
spells - so they're built with content/grimoire.py: each spell is its own
function, and the book registers a dispatcher under the name a character sheet
writes. **Level 5 is where that stops**: the SRD prints plain Spells from there
on, so those cards are declared directly rather than inside a book.

Card text is paraphrased in each docstring rather than quoted in full. The
verbatim text is in .reference/abilities.json, and was checked against the
printed page (SRD pp. 124-125) for all nine books.

Level 7 splits the way level 6 did, one card each way. **Codex-Touched** is the
only *X*-Touched card in the project whose bonus has a price - a Stress buys the
caster's whole Proficiency on a cast - and the **Book of Homet** is the second
book after Vagras with nothing implemented at all, both of its spells being
passage.

Level 6 is where the domain stops attacking and starts rearranging the fight.
**Sigil of Retribution** is the first party card anywhere that pays the *GM* -
a Fear, up front - and the first that banks somebody else's wounds as damage.
**Banish** takes an adversary off the field entirely and prints a way back, which
is what gave `FightState` a `removed` list to hold it in.

A Codex book is mostly utility, and that is a fact about the domain rather than
a gap: of the twenty-five spells in the nine books, thirteen change a fight. The
rest are declared `no_combat_effect` at the bottom under their own names *and*
noted as gaps on their book, so a reader of the coverage report sees both which
book is partly implemented and which spell inside it was dismissed.

Level 4 is where a Codex book stops being a spell list and starts being other
machinery. The **Book of Grynn** carries the first party-wide negation that isn't
a counterspell, and the **Book of Exota** carries *Create Construct*, which is
the first thing in the simulator to add a combatant to the **party** mid-fight.

Level 3 brings the two most dangerous spells in the domain, and neither is a
plain attack. **Rune Circle** is the first thing in the simulator that deals
damage with no roll at all - a Stress buys 2d12+4 to everything in Melee, and
nothing can miss. **Fireball** is the first *party* spell that can hurt the
party: "all creatures within Very Close range" is read the way the adversary
features already read it, so an ally standing next to the target saves against
it too.

Level 8 is the domain's third whole card to reach no fight, and the **Book of
Vyola** is worth reading the dismissal of: one of its spells is information, and
the other - *Shared Clarity*, which pools two PCs' Stress tracks - is real,
representable and ruled to make no difference across a high-N run. **Safe Haven**
is filed as out of combat rather than dismissed, because the downtime move it
grants is one of the larger things a party can buy.
"""

import random

from combat.results import AttackResult
from content.aoe import (
    Range,
    area_difficulty,
    chance_within,
    targets_beaten,
    targets_in_area,
)
from content.conditions import RESTRAINED, Condition, when_the_gm_pays
from content.damage_types import DamageType, types_in
from content.grimoire import Grimoire
from content.registry import (
    Fight,
    Holder,
    action,
    ally_damage_reduction,
    ally_on_damaged,
    ally_on_hit,
    ally_on_roll,
    extra_damage,
    free,
    hope_die_for,
    no_combat_effect,
    out_of_combat_ability,
    spellcast_bonus,
    total_extra_damage,
)
from content.spellcast import spellcast
from dice.d20 import roll_d20
from dice.damage import DiceGroup, roll_damage
from dice.duality import DualityOutcome, roll_duality

# The GM's pool has to be worth draining before spending a spotlight's roll on a
# condition that deals no damage. Below this, damage is the better use.
FEAR_WORTH_DRAINING = 3

# Arcane Barrage spends Hope down to this floor. Hope is the currency for
# Experiences and several other cards, so a caster who empties it into one
# barrage is trading away every later option.
BARRAGE_HOPE_FLOOR = 2


# --- Book of Ava -------------------------------------------------------------

AVA = Grimoire("Book of Ava")


@AVA.action(
    "Power Push",
    unmodelled=[
        "the knockback to Far range - no positions are tracked",
        "'within Melee range' - with no range modelled, this is always "
        "available, which is generous for a caster who would rarely be in melee",
    ],
)
def power_push(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Power Push (Book of Ava). Spellcast against a target in Melee range; on a
    success they're knocked back to Far and take d10+2 magic damage using
    Proficiency.
    """
    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=caster.proficiency, sides=10)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=2,
        is_critical=attack_roll.is_critical,
    )
    marked = target.take_damage(damage_roll.total, fight, damage_type=DamageType.MAGIC)
    fight.note(f"{caster.name} casts Power Push at {target.name}")
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


@AVA.action(
    "Ice Spike",
    unmodelled=[
        "range - at a table this is the Far option and Power Push the Melee "
        "one, and that is what decides between them. Here the choice is random",
    ],
)
def ice_spike(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Ice Spike (Book of Ava). Spellcast against the target's Difficulty when used
    as a weapon; on a success, d6 physical damage using Proficiency.

    Implemented rather than dismissed. It deals less than Power Push, but that
    is not a reason to leave it out: at a table this is the Far option and Power
    Push is the Melee one, and range is what decides between them. Since no
    positions are modelled, the two are chosen between at random - which is at
    least honest about not knowing, where always taking the bigger die would
    quietly assume the caster is always in melee.
    """
    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=caster.proficiency, sides=6)]
        + total_extra_damage(caster, target, attack_roll, fight),
        is_critical=attack_roll.is_critical,
    )
    # Physical, unusually for a Codex spell - the card says so, and it is the one
    # place a magic-resistant adversary would notice the difference between the
    # Book of Ava's two attack spells.
    marked = target.take_damage(damage_roll.total, fight, damage_type=DamageType.PHYSICAL)
    fight.note(f"{caster.name} strikes {target.name} with an Ice Spike")
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


@AVA.free(
    "Tava's Armor",
    unmodelled=[
        "recasting to move the ward onto somebody else - it's warded once per "
        "fight and stays there",
    ],
)
def tavas_armor(caster: Holder, fight: Fight) -> bool:
    """Tava's Armor (Book of Ava). Spend a Hope to give a target +1 Armor Score
    until their next rest.

    Armor Score is the number of Armor Slots, so this raises `armor_max` by one.
    Only worth a Hope once somebody has actually run out of slots - an unused
    slot is worth nothing, and the Hope has other buyers.
    """
    exhausted = [pc for pc in fight.conscious_party if pc.armor_marked >= pc.armor_max]
    if not exhausted or not caster.can_spend_hope(1):
        return False

    # Claimed last, so a cast that was never going to happen doesn't burn the
    # ward for the rest of the fight.
    if not fight.use_once_per_rest(caster, "Tava's Armor"):
        return False

    warded = exhausted[0]
    caster.spend_hope(1)
    warded.armor_max += 1
    fight.note(f"{caster.name} wards {warded.name} with Tava's Armor (+1 Armor Score)")
    return True


# --- Book of Illiat ----------------------------------------------------------

ILLIAT = Grimoire("Book of Illiat")


@ILLIAT.action(
    "Slumber",
    unmodelled=[
        "the Asleep condition itself - conditions aren't tracked, so this "
        "drains a Fear from the GM instead (see SIMULATION-RULES.md)",
    ],
)
def slumber(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Slumber (Book of Illiat). Spellcast against a target within Very Close; on a
    success they're Asleep until damaged or the GM spends a Fear to clear it.

    The condition isn't tracked, so per the simulation rule a temporary
    condition costs the GM a Fear - which is close to what this spell actually
    costs them, since clearing it is exactly what the card says a Fear buys.

    Only cast when the GM's pool is worth draining. This spell deals no damage,
    so below that it's a spotlight spent on nothing.
    """
    if fight.fear < FEAR_WORTH_DRAINING:
        return None

    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if attack_roll.is_success:
        fight.spend_fear(1)
        fight.note(f"{caster.name} puts {target.name} to sleep (the GM loses a Fear)")
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


@ILLIAT.free("Arcane Barrage")
def arcane_barrage(caster: Holder, fight: Fight) -> bool:
    """Arcane Barrage (Book of Illiat). Once per rest, spend any number of Hope and
    roll that many d6s of magic damage against one target.

    No action roll, so it can never pass the spotlight - damage for Hope, with
    nothing risked. That makes it strong, and the Hope is what pays for it.

    Spends down to a floor rather than emptying the pool, because Hope is also
    what Experiences and other cards want.
    """
    spend = caster.hope_marked - BARRAGE_HOPE_FLOOR
    if spend <= 0:
        return False

    targets = fight.living_adversaries
    if not targets:
        return False
    if not fight.use_once_per_rest(caster, "Arcane Barrage"):
        return False

    caster.spend_hope(spend)
    damage = roll_damage(dice_groups=[DiceGroup(count=spend, sides=6)])
    target = max(targets, key=lambda adversary: adversary.hp_marked)
    target.take_damage(damage.total, fight, damage_type=DamageType.MAGIC)
    fight.note(
        f"{caster.name} spends {spend} Hope on an Arcane Barrage, "
        f"hitting {target.name} for {damage.total}"
    )
    return True


ILLIAT.note_gap("Telepathy", "no combat effect - a line of communication")
no_combat_effect(
    "Telepathy",
    "Opens mental communication. Nothing about a fight's outcome changes.",
)


# --- Book of Tyfar -----------------------------------------------------------

TYFAR = Grimoire("Book of Tyfar")

# "Against up to three adversaries within Melee range" - the card's own cap,
# which sits on top of whatever the Melee band reaches.
WILD_FLAME_TARGETS = 3
WILD_FLAME_DICE = 2
WILD_FLAME_DIE = 6


@TYFAR.action(
    "Wild Flame",
    unmodelled=[
        "'within Melee range' - no positions are tracked, so the area rule in "
        "SIMULATION-RULES.md decides how many are caught, and nothing stops a "
        "Wizard casting it from the back line where the card puts them in reach",
    ],
)
def wild_flame(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Wild Flame (Book of Tyfar).

    SRD: make a Spellcast Roll against up to three adversaries within Melee
    range. Targets you succeed against take 2d6 magic damage and must mark a
    Stress as flames erupt from your hand.

    The roll is made **against the whole area at once** and each adversary is
    then checked against its own Difficulty - the Fire Flies shape rather than
    the Whirlwind one. Two caps apply and the smaller wins: the Melee band
    reaches 3 on a large field and 2 or 1 on a small one, and the card itself
    stops at three however many are standing there.

    **Never declines**, unlike Fire Flies. That card spends a Hope, so casting it
    at one target is a real cost for less than a bow; this one costs nothing but
    the roll it was going to make anyway, so there is no state in which casting
    is worse than not casting.

    The forced Stress is the half worth watching. It is the first PC card that
    marks an *adversary's* Stress, and an adversary's Stress is what pays for its
    Action features and what its desperation rule measures - so this reaches
    across the table into a resource the GM side has been spending freely.
    """
    area = targets_in_area(Range.MELEE, fight.living_adversaries)[:WILD_FLAME_TARGETS]
    if not area:
        return None

    attack_roll = spellcast(caster, target, fight, difficulty=area_difficulty(area))
    if attack_roll is None:
        return None

    caught = targets_beaten(attack_roll, area)
    if not caught:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=WILD_FLAME_DICE, sides=WILD_FLAME_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        is_critical=attack_roll.is_critical,
    )

    marked = 0
    for adversary in caught:
        marked += adversary.take_damage(
            damage_roll.total, fight, damage_type=DamageType.MAGIC
        )
        # Not a voluntary cost, so it is marked rather than spent - and an
        # adversary with a full Stress track simply loses nothing, since the
        # SRD's overflow-into-HP rule is a PC rule.
        adversary.mark_stress(1)

    fight.note(
        f"{caster.name} looses wild flame, catching {len(caught)} "
        f"for {damage_roll.total} each and a Stress apiece"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


TYFAR.note_gap("Magic Hand", "no combat effect - a conjured hand")
TYFAR.note_gap("Mysterious Mist", "no combat effect - fog over a place")

no_combat_effect(
    "Magic Hand",
    "Conjures a hand with the caster's own size and strength within Far range. "
    "It carries and manipulates; it makes no attack and the card gives it no "
    "damage. Nothing in a fight for it to touch.",
)
no_combat_effect(
    "Mysterious Mist",
    "A thick fog in a stationary area within Very Close range, heavily obscuring "
    "everything in it. The fog is terrain: it sits in a place, and no positions "
    "are tracked, so nobody is ever inside or outside it. Very much a real "
    "effect at a table - reading it as the Hidden condition on one side or the "
    "other was considered and declined, since which side is in the fog is "
    "exactly the positional fact that isn't modelled.",
)


# --- Book of Sitil -----------------------------------------------------------

SITIL = Grimoire("Book of Sitil")

PARALLELA = "Parallela"
PARALLELA_HOPE = 2

# The second target has to exist for the spell to buy anything at all.
PARALLELA_ADVERSARIES = 2


@SITIL.free(
    PARALLELA,
    unmodelled=[
        "'or an ally within Close range' - no positions are tracked, so any "
        "conscious ally can be reached",
        "The second target's damage type is read off the attacker's weapon, so "
        "an ally whose attack was a spell splashes as though it were a swing - "
        "the same simplification Whirlwind makes for the same reason",
    ],
)
def parallela(caster: Holder, fight: Fight) -> bool:
    """Parallela (Book of Sitil). Spend 2 Hope to double an ally's next attack.

    SRD: spend 2 Hope to cast this spell on yourself or an ally within Close
    range. The next time the target makes an attack, they can hit an additional
    target within range that their attack roll would succeed against. You can
    only hold this spell on one creature at a time.

    SIMULATION RULE - policy, ruled. Cast on **another party member**, never on
    the caster: the user's reasoning is that optimal play puts it on somebody
    else and then still spends the caster's own action roll. Which ally is random
    among the conscious ones, the standing default - picking "the best attacker"
    would mean scoring the party, which this project does not do.

    Declines while it would buy nothing, and neither check is an invented
    threshold: with one adversary standing there is no additional target for the
    rider to find, and with the spell already hanging on somebody the card says
    outright it can't be cast again.

    The rider itself is `parallela_doubles` - it has to fire on the *ally's*
    attack, which no holder-scoped hook can express.
    """
    if not caster.can_spend_hope(PARALLELA_HOPE):
        return False
    if len(fight.living_adversaries) < PARALLELA_ADVERSARIES:
        return False

    party = fight.conscious_party
    if any(fight.token_count(pc, PARALLELA) for pc in party):
        return False

    allies = [pc for pc in party if pc is not caster]
    if not allies:
        return False

    ally = random.choice(allies)
    caster.spend_hope(PARALLELA_HOPE)
    fight.add_token(ally, PARALLELA, cap=1)
    fight.note(f"{caster.name} casts Parallela on {ally.name}")
    return True


@ally_on_hit("Book of Sitil")
def parallela_doubles(
    holder: Holder, attacker, target, result, fight: Fight
) -> None:
    """Parallela's payoff: the same blow lands on a second adversary.

    Fires on the attack of whoever is carrying the spell, which is why it is
    registered party-wide rather than on the caster. `holder` is the Wizard whose
    book this is and `attacker` is the ally who just hit - they are never the
    same PC, since the spell is only ever cast on somebody else.

    Full damage, not half. Whirlwind says explicitly that its additional targets
    take half; this card says nothing of the kind, so nothing is halved - the
    same reading Hold Them Off already gets.

    SIMULATION RULE - rules interpretation. "The next time the target makes an
    attack" is read as the next attack that **lands**, so a miss doesn't burn the
    spell. Slightly generous, and it is what registering on a landed hit gives
    for free; the alternative would spend 2 Hope on a roll that hit nobody.

    Which second target, where the roll beat several, is random - the order
    `living_adversaries` happens to be in carries no meaning.
    """
    if not fight.token_count(attacker, PARALLELA):
        return

    # Spent whether or not a second target is found: this attack is "the next
    # time the target makes an attack", and the spell resolves on it.
    fight.spend_tokens(attacker, PARALLELA, 1)

    others = [
        adversary for adversary in fight.living_adversaries if adversary is not target
    ]
    reached = targets_beaten(result.attack_roll, others)
    if not reached:
        return

    second = random.choice(reached)
    damage_type = getattr(attacker, "weapon_damage_type", None)
    second.take_damage(result.damage_roll.total, fight, damage_type=damage_type)
    fight.note(
        f"Parallela carries {attacker.name}'s attack into {second.name} "
        f"for {result.damage_roll.total}"
    )


SITIL.note_gap("Adjust Appearance", "no combat effect - a disguise")
SITIL.note_gap("Illusion", "no combat effect - a visual decoy")

no_combat_effect(
    "Adjust Appearance",
    "Shifts the caster's appearance and clothing to avoid recognition. Nothing "
    "about a fight already under way changes.",
)
no_combat_effect(
    "Illusion",
    "A visual illusion no larger than the caster, which holds up to scrutiny "
    "only until an observer is within Melee range. A decoy works by being "
    "somewhere the caster is not, and no positions are tracked - so there is "
    "nowhere for it to stand and nobody to be drawn to it.",
)


# --- Book of Vagras ----------------------------------------------------------
#
# The one card in the batch with nothing implemented. All three of its spells are
# utility, so the *book* is declared rather than built - a Grimoire with no spell
# registered would report the card as unimplemented, which is exactly the wrong
# answer for something that has been read and assessed.

no_combat_effect(
    "Book of Vagras",
    "All three spells are utility. Runic Lock seals an object; Arcane Door opens "
    "a portal to a point within Far range; Reveal uncovers anything magically "
    "hidden within Close range. Reveal was the one worth arguing about - the "
    "simulator models Hidden, and the Jagged Knife Shadow's Cloaked prints no "
    "way to be found - and it was ruled to find objects rather than creatures, "
    "so Cloaked stays un-findable.",
)
no_combat_effect(
    "Runic Lock",
    "Locks an object that can close. There are no objects in a simulated fight.",
)
no_combat_effect(
    "Arcane Door",
    "A portal from where the caster is to a point within Far range, castable "
    "only with no adversary in Melee. Its whole effect is moving somebody "
    "somewhere else, and no positions are tracked - the standing answer for "
    "repositioning content. At a table it is an escape, which is a real thing to "
    "take away from a fight.",
)
no_combat_effect(
    "Reveal",
    "Reveals anything magically hidden within Close range. Ruled to be about "
    "objects - hidden doors, caches, glyphs - rather than about creatures using "
    "the Hidden condition. Reading it the other way was offered and declined: it "
    "would have made a no-cost Spellcast Roll the party's answer to the Shadow's "
    "Cloaked, which the SRD deliberately prints with no way to be found.",
)


# --- Book of Korvax ----------------------------------------------------------

KORVAX = Grimoire("Book of Korvax")

RUNE_CIRCLE_DICE = 2
RUNE_CIRCLE_DIE = 12
RUNE_CIRCLE_MODIFIER = 4


@KORVAX.free(
    "Rune Circle",
    unmodelled=[
        "'or who enter Melee range' - the circle is a lasting hazard on the "
        "ground and nothing tracks anybody walking into it. Ruled to a single "
        "burst on the reasoning that a GM who can see the circle keeps their "
        "adversaries out of it, so the recurring half would rarely be collected "
        "at a table either",
        "The knockback to Very Close - no positions are tracked",
        "'within Melee range' - the area rule in SIMULATION-RULES.md decides how "
        "many adversaries the circle catches, and nothing stops a Wizard drawing "
        "one where the card puts them in reach",
    ],
)
def rune_circle(caster: Holder, fight: Fight) -> bool:
    """Rune Circle (Book of Korvax). Mark a Stress; everything in Melee burns.

    SRD: "Mark a Stress to create a temporary magical circle on the ground where
    you stand. All adversaries within Melee range, or who enter Melee range, take
    2d12+4 magic damage and are knocked back to Very Close range."

    **No roll of any kind**, which is what makes it a free ability rather than an
    action: it costs the caster a Stress and nothing else, so it does not spend
    the spotlight's one action roll and a Wizard can draw the circle *and*
    attack. There is no attack roll to miss with either - the damage simply
    lands, against the target's thresholds like any other.

    SIMULATION RULE - policy. Nothing to rule on beyond the standing default: the
    circle is drawn whenever the Stress can be paid and there is somebody in the
    band to catch. `will_spend_stress` is the shared last-slot rule, as every PC
    Stress cost is.

    Magic damage, per the card. Each adversary takes the same roll and each is
    measured against its own thresholds, which is how every area effect here
    resolves.
    """
    if fight is None or not caster.will_spend_stress(1):
        return False

    caught = targets_in_area(Range.MELEE, fight.living_adversaries)
    if not caught:
        return False

    caster.spend_stress(1)
    damage = roll_damage(
        dice_groups=[DiceGroup(count=RUNE_CIRCLE_DICE, sides=RUNE_CIRCLE_DIE)],
        modifier=RUNE_CIRCLE_MODIFIER,
    )
    for adversary in caught:
        adversary.take_damage(damage.total, fight, damage_type=DamageType.MAGIC)
    fight.note(
        f"{caster.name} marks a Stress for a rune circle, catching {len(caught)} "
        f"for {damage.total} each"
    )
    return True


KORVAX.note_gap("Levitation", "no combat effect - lifting and repositioning")
KORVAX.note_gap("Recant", "no combat effect - erasing a conversation")

no_combat_effect(
    "Levitation",
    "Temporarily lifts a target the caster can see into the air and moves them "
    "within Close range of where they were. Its whole effect is where somebody "
    "is standing, and no positions are tracked - the standing answer for "
    "repositioning content. It changes a great deal at a table, where being off "
    "the ground and out of reach is most of the point.",
)
no_combat_effect(
    "Recant",
    "A Hope forces a Reaction Roll (15); on a failure the target forgets the "
    "last minute of the conversation. Conversations are not represented, and "
    "neither is memory - the target's stat block is unchanged either way, and an "
    "adversary in an encounter is already hostile and already swinging.",
)


# --- Book of Norai -----------------------------------------------------------

NORAI = Grimoire("Book of Norai")

FIREBALL_DIE = 20
FIREBALL_MODIFIER = 5
FIREBALL_DIFFICULTY = 13


@NORAI.action(
    "Mystic Tether",
    unmodelled=[
        "'within Far range' - no positions are tracked, so this always reaches",
        "'If you target a flying creature, this spell grounds them' - nothing "
        "here represents a creature being airborne, so there is no altitude to "
        "take away. `Flying (X)` is resolved into a stat block's Difficulty at "
        "spawn and is not a state anything can end",
    ],
)
def mystic_tether(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Mystic Tether (Book of Norai).

    SRD: make a Spellcast Roll against a target within Far range. On a success
    they're temporarily Restrained and must mark a Stress. If you target a flying
    creature, this spell grounds and temporarily Restrains them.

    Two effects and only one of them bites here. Restrained is **recorded and
    does nothing by itself** - being held stops a combatant moving, and no
    movement is modelled - so under the standing rule for a condition the party
    puts on an adversary its whole cost to the GM is the Fear they must spend to
    clear it. The forced Stress is the half that lands directly: an adversary's
    Stress is what pays for its Action features and what its desperation rule
    reads.

    Never declines. It costs nothing but the roll the caster was making anyway,
    so there is no state in which casting it is worse than not - the Wild Flame
    reading rather than the Fire Flies one.

    Skips a target already Restrained, per the standing rule that a feature whose
    point is a condition is not used on somebody who already has it. The Stress
    goes with it: the card's two effects are one clause.
    """
    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    if not target.is_defeated and not fight.has_condition(target, RESTRAINED):
        fight.apply_condition(
            target,
            Condition(name=RESTRAINED, end=when_the_gm_pays, source=caster),
        )
        target.mark_stress(1)
        fight.note(f"{caster.name} tethers {target.name}, who marks a Stress")

    return AttackResult(attack_roll=attack_roll, damage_roll=None)


@NORAI.action(
    "Fireball",
    unmodelled=[
        "'within Very Far range' - no positions are tracked, so this always "
        "reaches its first target",
        "'all creatures within Very Close range of them' - who is standing near "
        "the target is answered by the area rule, rolled per combatant",
    ],
)
def fireball(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Fireball (Book of Norai).

    SRD: make a Spellcast Roll against a target within Very Far range. On a
    success, hurl a sphere of fire that explodes on impact. The target and all
    creatures within Very Close range of them must make a Reaction Roll (13).
    Targets who fail take d20+5 magic damage using your Proficiency. Targets who
    succeed take half damage.

    SIMULATION RULE - rules interpretation, ruled. **"All creatures" includes the
    party.** The SRD alternates "creatures" and "targets" deliberately, and the
    adversary features already read the distinction that way - the Fire
    Elemental's Scorched Earth catches its own allies where the Demon's Hellfire
    does not. This is the first time the rule cuts against the party, and it is
    the same rule: a PC the area rule places within Very Close of the target
    rolls to save alongside the adversaries.

    So the spell is genuinely dangerous to drop on something a Guardian is in
    melee with, which is what the page says it should be.

    **The save is a Reaction Roll**, so it generates no Hope and no Fear and
    moves no spotlight. An adversary rolls a flat d20 with no modifier, having no
    traits; a PC rolls Duality Dice plus a trait, and since the card names none
    they roll their **best** - the ruling being that the GM names the trait at the
    table and a player argues for the one they are good at. A **critical takes
    nothing at all**, which is the standing reading of a critical on a save.

    Never declines: the damage happens on a success whatever the field looks
    like, and the caster is never themselves in the blast (the area is measured
    around the target).
    """
    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=caster.proficiency, sides=FIREBALL_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=FIREBALL_MODIFIER,
        is_critical=attack_roll.is_critical,
    )

    caught = [target] + _splashed(caster, target, fight)
    marked = 0
    for creature in caught:
        marked += _fireball_lands_on(creature, damage_roll.total, fight)

    fight.note(
        f"{caster.name}'s fireball bursts on {target.name}, catching "
        f"{len(caught)} for up to {damage_roll.total}"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


def _splashed(caster: Holder, target, fight: Fight) -> list:
    """Everyone other than the target the blast reaches, both sides of the table.

    The area rule stands in for "within Very Close range of them", rolled per
    combatant with `chance_within` rather than swept with `targets_in_area`,
    because the question is about proximity to *the target* rather than to the
    caster - the same shape Natural Familiar's d6 asks.

    The caster is excluded. They threw it from Very Far, which is the one piece
    of positioning the card is explicit enough about to honour.
    """
    others = [
        creature
        for creature in [*fight.living_adversaries, *fight.conscious_party]
        if creature is not target and creature is not caster
    ]
    if not others:
        return []

    odds = chance_within(Range.VERY_CLOSE, len(others))
    return [creature for creature in others if random.random() < odds]


def _fireball_lands_on(creature, damage: int, fight: Fight) -> int:
    """One creature's save against the blast; returns the HP it marked.

    A flat d20 for an adversary, which carries no traits, and Duality Dice plus
    the best trait for a PC. `roll_d20` and `roll_duality` are called directly
    rather than through a helper of their own: there is exactly one way to roll
    each in this codebase and this is a second site that needs them.

    The best trait is picked **by name** rather than by value, so the roll can
    record which trait it was made on alongside the modifier it contributed. Two
    traits tied at the top give the same number either way, so which of them the
    roll is labelled with changes nothing about the save.
    """
    traits = getattr(creature, "traits", None)
    if traits:
        best = max(traits, key=lambda name: traits[name])
        save = roll_duality(
            modifier=traits[best], difficulty=FIREBALL_DIFFICULTY, trait=best
        )
    else:
        save = roll_d20(evasion=FIREBALL_DIFFICULTY)

    if save.is_critical:
        fight.note(f"{creature.name} is clear of the blast entirely")
        return 0

    taken = damage if not save.is_success else damage // 2
    marked = creature.take_damage(taken, fight, damage_type=DamageType.MAGIC)
    if save.is_success:
        fight.note(f"{creature.name} shields against the blast, taking {taken}")
    return marked


# --- Book of Grynn -----------------------------------------------------------

GRYNN = Grimoire("Book of Grynn")

ARCANE_DEFLECTION = "Arcane Deflection"

WALL_OF_FLAME_DICE = 4
WALL_OF_FLAME_DIE = 10
WALL_OF_FLAME_MODIFIER = 3
WALL_OF_FLAME_DIFFICULTY = 15


@ally_damage_reduction(
    "Book of Grynn",
    unmodelled=[
        "'the damage of an attack' is read as **any** incoming damage, since "
        "this hook is asked wherever a PC takes some. On Fire burning its holder "
        "would be negated the same way a sword would, which is generous - but "
        "narrowing it would need an attacker, and damage arrives without one",
    ],
)
def arcane_deflection(
    caster: Holder, target, amount: int, fight: Fight, damage_type=None
) -> int:
    """Arcane Deflection (Book of Grynn). Returns the damage this hit should lose.

    SRD: "Once per long rest, spend a Hope to negate the damage of an attack
    targeting you or an ally within Very Close range."

    **Negated outright, not softened.** The whole amount is returned, so the hit
    resolves to nothing - and because `take_damage` floors at zero before the
    thresholds are read, no Armor Slot is spent on an attack that never landed.
    The same shape as Blade's Scramble, and the same reason no other hook can say
    it: an Armor Slot and `severity_response` both work in threshold bands.

    **Once per *long* rest**, which is the user's ruling and is not the same as
    the once-per-rest that most cards carry. A short rest does not give it back,
    so a party pushed through several encounters between long rests has this once
    and no more - which is what will matter when encounters run in sequence.

    **"You or an ally within Very Close range"** is a question about where
    somebody is standing, so the standing answer applies: the caster is always in
    range of themselves, and an ally is reached on the area rule's odds. Asked
    only after everything cheaper has agreed, so the positional roll is not made
    on hits the spell was never going to touch.

    SIMULATION RULE - policy, ruled. Spent on the first hit that would mark **2
    or more HP**, or on any hit against a PC already at 2 or fewer unmarked HP.
    The same rule Counterspell follows, and it reads only what a player can see
    when they decide: the damage the GM announced, against that PC's printed
    thresholds.
    """
    if fight is None:
        return 0

    if amount < target.major_threshold and not target.is_near_death:
        return 0
    if not caster.can_spend_hope(1):
        return 0
    if not fight.can_use_once_per_rest(caster, ARCANE_DEFLECTION, long=True):
        return 0

    if target is not caster:
        allies = [pc for pc in fight.conscious_party if pc is not caster]
        if not allies or random.random() >= chance_within(Range.VERY_CLOSE, len(allies)):
            return 0

    fight.use_once_per_rest(caster, ARCANE_DEFLECTION, long=True)
    caster.spend_hope(1)
    fight.note(
        f"{caster.name} deflects the attack on {target.name}, negating {amount}"
    )
    return amount


@GRYNN.action(
    "Wall of Flame",
    unmodelled=[
        "'All creatures in its path must choose a side to be on' - the choice is "
        "positional and no positions are tracked, so nobody chooses. What is "
        "modelled is the burning",
        "The wall **lasting**. It is a temporary hazard between two points and "
        "the damage is collected by anything that later passes through it; here "
        "it burns once, as it goes up. Ruled the same way Rune Circle's recurring "
        "half was, and for the same reason - a GM who can see a wall of fire "
        "keeps their adversaries off it",
        "'between two points within Far range' - the area rule in "
        "SIMULATION-RULES.md decides how much of the field the wall crosses",
    ],
)
def wall_of_flame(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Wall of Flame (Book of Grynn).

    SRD: "Make a Spellcast Roll (15). On a success, create a temporary wall of
    magical flame between two points within Far range. All creatures in its path
    must choose a side to be on, and anything that subsequently passes through the
    wall takes 4d10+3 magic damage."

    SIMULATION RULE - rules interpretation, ruled. **The wall's reach is the area
    rule's Far band**, which is the user's ruling on how a wall drawn across the
    field is answered here. Far is everything on the field a quarter of the time
    short by one, so a wall of flame is the widest thing the party can cast and
    still not reliably everything.

    Rolled against the printed Difficulty of 15 rather than against any target's,
    which is what the card prints - so this is one of the few Spellcast Rolls in
    the simulator whose number to beat has nothing to do with what it is aimed at.

    Never declines. It costs nothing but the roll the caster was making anyway.

    Everything caught takes the same 4d10+3 and is measured against its own
    thresholds, which is how every area effect here resolves.
    """
    attack_roll = spellcast(
        caster, target, fight, difficulty=WALL_OF_FLAME_DIFFICULTY
    )
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    caught = targets_in_area(Range.FAR, fight.living_adversaries)
    if not caught:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=WALL_OF_FLAME_DICE, sides=WALL_OF_FLAME_DIE)]
        + total_extra_damage(caster, target, attack_roll, fight),
        modifier=WALL_OF_FLAME_MODIFIER,
        is_critical=attack_roll.is_critical,
    )

    marked = 0
    for adversary in caught:
        marked += adversary.take_damage(
            damage_roll.total, fight, damage_type=DamageType.MAGIC
        )

    fight.note(
        f"{caster.name} raises a wall of flame across {len(caught)} "
        f"for {damage_roll.total} each"
    )
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


GRYNN.note_gap("Time Lock", "no combat effect - freezing an object in place")

no_combat_effect(
    "Time Lock",
    "Stops an object in time and space where it is until the caster's next rest, "
    "with a Spellcast Roll to hold it there if a creature tries to move it. There "
    "are no objects in a simulated fight, and the spell says outright that it "
    "targets one - so there is nothing here for it to hold.",
)


# --- Book of Exota -----------------------------------------------------------

EXOTA = Grimoire("Book of Exota")

REPUDIATE = "Repudiate"

CREATE_CONSTRUCT = "Create Construct"
CONSTRUCT_HOPE = 1

# The construct's own action, registered under a name **only the construct
# carries**. It is not a card anybody's sheet names, which is exactly why it can
# have one: dispatch finds an ability by the names its holder lists, and the
# construct is spawned with this one in its loadout.
ANIMATED_CONSTRUCT = "Animated Construct"

CONSTRUCT_DICE = 2
CONSTRUCT_DIE = 10
CONSTRUCT_MODIFIER = 3

# "They fall apart when they take any amount of damage", read as the user ruled
# it: one HP and thresholds nothing can reach, so every hit that lands is Minor,
# marks the single HP, and takes the construct off the field.
CONSTRUCT_HP = 1
CONSTRUCT_THRESHOLD = 999

# Placed on the construct itself, so "you can only maintain one construct at a
# time" is answered by looking at the party rather than by remembering on the
# caster - a construct that has fallen apart is no longer conscious and no longer
# found, which is what lets the next one be built.
CONSTRUCT_MARK = "Animated construct"


@ally_damage_reduction(
    "Book of Exota",
    unmodelled=[
        "'a magical effect taking place' in general - nothing marks an adversary "
        "feature as magical, so the only magical effect the simulator can "
        "recognise is an attack that deals **magic damage**. The same gap "
        "Arcana's Counterspell declares, and for the same reason",
    ],
)
def repudiate(
    caster: Holder, target, amount: int, fight: Fight, damage_type=None
) -> int:
    """Repudiate (Book of Exota). Returns the damage this hit should lose.

    SRD: "You can interrupt a magical effect taking place. Make a reaction roll
    using your Spellcast trait. Once per rest on a success, the effect stops and
    any consequences are avoided."

    **Counterspell's card, in a book.** Everything the Arcana card settled applies
    here unchanged: a magical effect is an incoming attack that deals magic
    damage, the reaction roll is Duality Dice on the caster's Spellcast trait
    against the **attacking adversary's** own Difficulty, and "any consequences
    are avoided" means the whole amount, returned before the thresholds so no
    Armor Slot is spent either. Who is attacking comes from `fight.spotlighted`;
    a `None` there means the magic is the party's own and this declines.

    Two differences from Counterspell, both printed on the page. This one does
    **not** vault itself, so there is nothing to buy back - and its limit is
    "once per rest **on a success**", so a failed interruption costs nothing and
    the caster may try again. The per-rest use is claimed after the roll for
    exactly that reason.

    SIMULATION RULE - policy. The same rule Counterspell was ruled to, extended
    to the card that does the same thing: attempted on the first magic hit that
    would mark **2 or more HP**, or on any magic hit against a PC already at 2 or
    fewer unmarked HP. Read off the damage announced and the target's printed
    thresholds, and nothing else.

    **Party-wide, not just the caster**, like Counterspell: the card says "a
    magical effect taking place", not one aimed at you.
    """
    if fight is None or DamageType.MAGIC not in types_in(damage_type):
        return 0

    attacker = fight.spotlighted
    if attacker is None:
        return 0

    if amount < target.major_threshold and not target.is_near_death:
        return 0

    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return 0
    if not fight.can_use_once_per_rest(caster, REPUDIATE):
        return 0

    # A Reaction Roll, so it is not offered to the reroll hook and generates
    # neither Hope nor Fear - see SIMULATION-RULES.md.
    reaction = roll_duality(
        modifier=caster.traits[trait],
        difficulty=attacker.difficulty,
        hope_die=hope_die_for(caster, fight),
        trait=trait,
    )
    if not reaction.is_success:
        fight.note(f"{caster.name}'s repudiation fails ({reaction})")
        return 0

    fight.use_once_per_rest(caster, REPUDIATE)
    fight.note(
        f"{caster.name} repudiates {attacker.name}, sparing {target.name} "
        f"{amount} magic damage"
    )
    return amount


@EXOTA.free(
    CREATE_CONSTRUCT,
    unmodelled=[
        "'a group of objects around you' - nothing represents the scenery, so "
        "there is always something to animate",
        "'Make a Spellcast Roll to command them to take action' - the roll is "
        "made by the construct on its own spotlight rather than by the caster on "
        "theirs, which follows from it being a party member. The consequence is "
        "that commanding it costs the caster nothing after the Hope",
        "'they share your Evasion and traits' is read as a **copy** taken when "
        "the construct is built. A caster whose Evasion changes mid-fight - "
        "Ferocity - does not change the construct's",
    ],
)
def create_construct(caster: Holder, fight: Fight) -> bool:
    """Create Construct (Book of Exota). A Hope animates something that fights.

    SRD: "Spend a Hope to choose a group of objects around you and create an
    animated construct from them that obeys basic commands. Make a Spellcast Roll
    to command them to take action. When necessary, they share your Evasion and
    traits and their attacks deal 2d10+3 physical damage. You can only maintain
    one construct at a time, and they fall apart when they take any amount of
    damage."

    SIMULATION RULE - policy, ruled. **The construct joins the party.** The
    user's ruling is that it becomes a temporary party member with 1 HP and
    thresholds nothing can reach, so it takes its own spotlights, adversaries can
    swing at it, and any hit that lands takes it off the field. One Hope builds
    it and it fights for as long as it lasts; commanding it costs nothing more.

    Two things follow from that and are worth reading numbers with in mind: a
    fight is not lost while the construct is still standing, and a GM turn is
    party size + 1 activations, so summoning one also hands the GM an extra
    activation each turn. See `FightState.summon_ally` and SIMULATION-RULES.md.

    Declines without a Spellcast trait to give it. The construct rolls the
    caster's traits, and one that could never make its Spellcast Roll would be a
    Hope spent on something that stands there.

    "Only one construct at a time" is read off the party rather than remembered
    on the caster, so a construct that has fallen apart is not one that is still
    being maintained.
    """
    if fight is None:
        return False

    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return False
    if not caster.can_spend_hope(CONSTRUCT_HOPE):
        return False
    if any(fight.token_count(pc, CONSTRUCT_MARK) for pc in fight.conscious_party):
        return False

    caster.spend_hope(CONSTRUCT_HOPE)
    construct = _construct_for(caster)
    fight.set_token(construct, CONSTRUCT_MARK, 1)
    fight.summon_ally(construct)
    fight.note(f"{caster.name} spends a Hope and animates {construct.name}")
    return True


def _construct_for(caster: Holder):
    """The construct as a combatant, built from the caster it belongs to.

    A `PlayerCharacter` because that is what the party is a list of, and because
    everything the fight loop does to a party member - spotlighting it, targeting
    it, marking its HP - is written against that class. Imported here rather than
    at module scope for the reason `domain_cards/` imports anything from outside
    itself: this is the one card that needs it.

    Every number on it is either copied from the caster (Evasion, traits, the
    Spellcast trait it rolls) or is the ruling (`CONSTRUCT_HP`,
    `CONSTRUCT_THRESHOLD`). It carries no ancestry, community, class or subclass:
    a construct has none, and leaving them blank means dispatch finds nothing
    under them rather than finding somebody else's features.

    One Stress slot rather than none, and it is not a resource anything spends. A
    combatant with a Stress track of zero has every slot marked by definition,
    which would make it Vulnerable by the SRD's own rule and hand every attack
    against it Advantage - an artefact of the arithmetic rather than anything the
    card says.

    Level zero, so the death move that fires when its single HP is marked can
    never leave a scar: `avoid_death` scars on a d12 at or below the PC's level.
    """
    from characters.player_character import PlayerCharacter

    return PlayerCharacter(
        name=f"{caster.name}'s construct",
        level=0,
        character_class="",
        subclass="",
        ancestry="",
        community="",
        traits=dict(caster.traits),
        evasion=getattr(caster, "evasion", 0),
        proficiency=caster.proficiency,
        major_threshold=CONSTRUCT_THRESHOLD,
        severe_threshold=CONSTRUCT_THRESHOLD,
        hp_max=CONSTRUCT_HP,
        stress_max=1,
        hope_max=0,
        armor_max=0,
        primary_weapon="",
        secondary_weapon=None,
        armor_item="",
        domain_cards_loadout=[ANIMATED_CONSTRUCT],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
        spellcast_trait=getattr(caster, "spellcast_trait", ""),
    )


@action(
    ANIMATED_CONSTRUCT,
    unmodelled=[
        "The construct is **not** reported. `combat/fight.py` hands the report "
        "the party the encounter spawned, and `summon_ally` rebinds rather than "
        "appends, so nothing the construct did shows up in the per-member "
        "figures - which is deliberate: a 1 HP combatant in the near-death rate "
        "would say something untrue about the party",
    ],
)
def construct_strike(construct: Holder, target, fight: Fight):
    """What the animated construct does with a spotlight.

    A Spellcast Roll on the traits it copied from its caster, and 2d10+3 physical
    on a success - the card's own numbers. Physical rather than magic: the card
    says so, and it is the one place a magic-resistant adversary would find the
    construct easier to deal with than the Wizard who built it.

    Never declines. The construct carries nothing else and has no weapon, so this
    is the whole of what its spotlight can resolve into.
    """
    attack_roll = spellcast(construct, target, fight)
    if attack_roll is None:
        return None

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=CONSTRUCT_DICE, sides=CONSTRUCT_DIE)],
        modifier=CONSTRUCT_MODIFIER,
        is_critical=attack_roll.is_critical,
    )
    marked = target.take_damage(
        damage_roll.total, fight, damage_type=DamageType.PHYSICAL
    )
    fight.note(f"{construct.name} strikes {target.name} for {damage_roll.total}")
    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )


# --- Sigil of Retribution ------------------------------------------------------

SIGIL_OF_RETRIBUTION = "Sigil of Retribution"

SIGIL_DIE = 8

# Placed on the *adversary* wearing the sigil, so "this effect ends when the marked
# adversary is defeated" is answered by looking at the field rather than by
# remembering anything on the caster - a defeated adversary is not in
# `living_adversaries`, so nothing finds the mark and the spell may be cast again.
SIGIL_MARK = "Sigil of retribution"

# The dice waiting on the card, held on the caster - it is their card.
SIGIL_DICE = "Sigil dice"


@free(
    SIGIL_OF_RETRIBUTION,
    unmodelled=[
        "'within Close range' - no positions are tracked, so the sigil always "
        "reaches whoever the party is focusing",
        "'or you cast Sigil of Retribution again' - the spell is only cast while "
        "no sigil stands, so nothing ever moves one. Re-casting to shift the mark "
        "onto a fresher target is a judgement about the fight that nobody has "
        "ruled on, and the card's other ender covers the case that matters: the "
        "marked adversary dying frees it",
    ],
)
def sigil_of_retribution(caster: Holder, fight: Fight) -> bool:
    """Sigil of Retribution (Codex, level 6). Mark one adversary and bank its blows.

    SRD: "Mark an adversary within Close range with a sigil of retribution. The GM
    gains a Fear. When the marked adversary deals damage to you or your allies,
    place a d8 on this card. You can hold a number of d8s equal to your level. When
    you successfully attack the marked adversary, roll the dice on this card and
    add the total to your damage roll, then clear the dice. This effect ends when
    the marked adversary is defeated or you cast Sigil of Retribution again."

    **No roll**, so it is a free ability: the caster marks somebody *and* takes
    their action roll in the same spotlight. What it costs is not the caster's at
    all - **the GM gains a Fear** - which makes this the first party card anywhere
    that pays the other side of the table outright. A Fear is an extra activation
    the GM would not otherwise have had.

    SIMULATION RULE - policy, ruled. **No trigger of its own.** It is offered like
    any other free ability, shuffled among them and bounded by the spotlight
    budget, and it fires whenever no sigil is standing. Holding it back until the
    party had taken damage - proof that the marked adversary would ever charge it -
    was proposed and declined: the user's ruling is that content with nothing
    special about it joins the random selection rather than getting a bespoke
    trigger.

    The mark goes on the party's focus target, which is the adversary with the most
    HP marked - `combat/policy.py`'s rule, **restated** here rather than called,
    since that module imports this package and the dependency cannot run the other
    way. The same arrangement Chokehold already uses.

    Declines while a sigil stands. One card, one sigil.
    """
    if fight is None:
        return False

    living = fight.living_adversaries
    if not living:
        return False
    if any(fight.token_count(adversary, SIGIL_MARK) for adversary in living):
        return False

    marked = max(living, key=lambda adversary: adversary.hp_marked)
    fight.set_token(marked, SIGIL_MARK, 1)
    # A fresh sigil starts empty. The dice belong to the previous one, whose
    # adversary is dead - "this effect ends" takes them with it.
    fight.set_token(caster, SIGIL_DICE, 0)
    fight.gain_fear(1)
    fight.note(
        f"{caster.name} marks {marked.name} with a sigil of retribution "
        f"(the GM gains a Fear)"
    )
    return True


@ally_on_damaged(SIGIL_OF_RETRIBUTION)
def sigil_charges(
    caster: Holder, target, amount: int, hp_marked: int, fight: Fight
) -> None:
    """A d8 goes on the card every time the marked adversary hurts the party.

    Registered on the same name as the free ability above, which is how one card
    reaches several hooks. **Party-wide**, because the card says "damage to you or
    your allies" - a sigil that only charged off the caster's own wounds would be a
    different and much smaller card, which is the whole reason `ally_on_damaged`
    exists.

    Who dealt the damage comes from `fight.spotlighted`, since damage reaches a PC
    with no attacker attached. `None` there means the hit was the party's own - On
    Fire burning its holder - and charges nothing, which is right: the sigil is
    retribution against one adversary.

    Keyed on **damage dealt**, not HP marked, exactly as the card says: "when the
    marked adversary deals damage". So a hit an Armor Slot swallowed whole still
    puts a die on the card.

    Capped at the caster's level, which is what the page prints. Over the cap the
    blow simply banks nothing.
    """
    if fight is None or amount <= 0:
        return

    attacker = fight.spotlighted
    if attacker is None or not fight.token_count(attacker, SIGIL_MARK):
        return

    held = fight.token_count(caster, SIGIL_DICE)
    if held >= caster.level:
        return

    fight.set_token(caster, SIGIL_DICE, held + 1)
    fight.note(f"{caster.name}'s sigil answers for {target.name} ({held + 1}d8)")


@extra_damage(SIGIL_OF_RETRIBUTION)
def sigil_repays(caster: Holder, target, roll, fight: Fight = None) -> list:
    """The dice on the card, thrown into the damage of a hit on the marked adversary.

    Asked from inside the damage roll, so the dice join it and cross the target's
    thresholds once - which is the whole reason `extra_damage` exists rather than
    dealing a second hit afterwards. It also means a **missed** attack neither
    spends the dice nor throws them, since the hook is only reached on a hit.

    `discardable=False`, like every die a feature adds to somebody else's roll: a
    Massive or Powerful weapon discards the lowest of the dice *it* rolled, and
    these are not among them.
    """
    if fight is None or not fight.token_count(target, SIGIL_MARK):
        return []

    held = fight.token_count(caster, SIGIL_DICE)
    if not held:
        return []

    fight.set_token(caster, SIGIL_DICE, 0)
    fight.note(f"{caster.name}'s sigil discharges {held}d8 into {target.name}")
    return [DiceGroup(count=held, sides=SIGIL_DIE, discardable=False)]


# --- Banish --------------------------------------------------------------------

BANISH = "Banish"

BANISH_DIE = 20

# The Difficulty the banished adversary rolls against to come back, held on the
# caster as a plain number, and the `id()` of whoever is out there. Both are
# `set_token` values rather than counts - the Ranger's Focus arrangement, which is
# what that method exists for.
BANISHED_WHO = "Banished adversary"
BANISHED_DIFFICULTY = "Banishment difficulty"


@action(
    BANISH,
    unmodelled=[
        "'within Close range' - no positions are tracked, so the spell always "
        "reaches whoever the party is focusing",
        "A banished adversary is off the field, so **the party can win a fight "
        "while one is still banished**. That follows from the standing reading "
        "that a removed adversary is not there rather than from anything about "
        "this card, and it is the one place the spell is worth more here than at "
        "a table, where the GM would still have it in hand",
        "The banished adversary's own return roll is not made on any schedule of "
        "its own - only a PC rolling with Fear buys it one, which is what the page "
        "prints. A fight in which the party never rolls with Fear again never "
        "sees it back",
    ],
)
def banish(caster: Holder, target, fight: Fight) -> AttackResult | None:
    """Banish (Codex, level 6). Take one adversary off the board entirely.

    SRD: "Make a Spellcast Roll against a target within Close range. On a success,
    roll a number of d20s equal to your Spellcast trait. The target must make a
    reaction roll with a Difficulty equal to your highest result. On a success, the
    target must mark a Stress but isn't banished. Once per rest on a failure, they
    are banished from this realm. When the PCs roll with Fear, the Difficulty gains
    a -1 penalty and the target makes another reaction roll. On a success, they
    return from banishment."

    **Two gates, not one.** Beating the target's Difficulty only earns the spell a
    second contest: a pool of d20s equal to the caster's Spellcast trait, best
    result taken, against a flat d20 the adversary rolls with no modifier. So a
    high Spellcast trait buys more attempts at a high number rather than a bonus,
    which is a different shape from every other spell in the domain.

    SIMULATION RULE - rules interpretation, ruled. **Banishment is `remove`, not
    defeat** - the Green Ooze's *Split* shape. The adversary leaves the field with
    its HP and Stress untouched, is not reported as a kill, and comes back the same
    object it left as. `FightState.removed` is what holds it in the meantime, and
    the caster remembers which one by `id()`, the way Ranger's Focus remembers its
    mark.

    The **-1 is cumulative**: each PC roll with Fear lowers the Difficulty by
    another point and buys another attempt, so a banishment gets easier the longer
    it lasts and the worse the party's luck runs. Reading it as a flat -1 applied
    once was the alternative; the page's "gains a -1 penalty" alongside a repeated
    roll reads as accumulating.

    SIMULATION RULE - rules interpretation. The per-rest limit gates **the
    banishment, not the spell**. "Once per rest on a failure, they are banished" is
    the Repudiate and Troublemaker phrasing - the limit sits on the payoff - so the
    spell may be cast again after it has been used, and a failed reaction roll with
    the use already spent simply does nothing. The Stress is the *success* clause
    and is not owed on a failure.

    SIMULATION RULE - policy. Nothing to rule on: no Hope, no Stress, and the
    per-rest use is claimed only when the banishment actually happens, so casting
    costs nothing but the roll the caster was making anyway. The Preservation Blast
    reading - it never declines.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None

    dice = caster.traits[trait]
    if dice <= 0:
        return None

    attack_roll = spellcast(caster, target, fight)
    if attack_roll is None:
        return None
    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    difficulty = max(random.randint(1, BANISH_DIE) for _ in range(dice))

    # A flat d20 with no modifier, since adversaries have no traits to roll. The
    # Difficulty is passed as `evasion` on purpose; see `dice/d20.py`.
    if roll_d20(evasion=difficulty).is_success:
        target.mark_stress(1)
        fight.note(
            f"{caster.name} reaches for {target.name} at {difficulty}, and they "
            f"hold on - a Stress marked"
        )
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    if not fight.use_once_per_rest(caster, BANISH):
        fight.note(f"{caster.name} has no banishment left to give {target.name}")
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    fight.set_token(caster, BANISHED_WHO, id(target))
    fight.set_token(caster, BANISHED_DIFFICULTY, difficulty)
    fight.remove(target)
    fight.note(f"{caster.name} banishes {target.name} from this realm")
    return AttackResult(attack_roll=attack_roll, damage_roll=None)


@ally_on_roll(BANISH)
def banish_weakens(caster: Holder, roller, roll, fight: Fight) -> None:
    """Every roll the party makes with Fear loosens the banishment by a point.

    Registered on the same name as the spell, which is how one card reaches two
    hooks. **Party-wide**, because the card says "when the PCs roll with Fear" -
    any of them, not only the caster - which is exactly what `ally_on_roll` is for.

    A critical is neither Hope nor Fear (the two dice matched, so neither won), so
    it does not loosen anything. `DualityOutcome` is asked rather than the dice
    compared, which keeps that right for free.

    The adversary is found in `fight.removed_adversaries` by the `id()` recorded
    when the spell landed. It cannot have been recycled onto something else: the
    removed list is holding the object alive.
    """
    if fight is None or roll is None:
        return
    if getattr(roll, "outcome", None) is not DualityOutcome.FEAR:
        return

    banished_id = fight.token_count(caster, BANISHED_WHO)
    if not banished_id:
        return

    banished = next(
        (gone for gone in fight.removed_adversaries if id(gone) == banished_id), None
    )
    if banished is None:
        fight.set_token(caster, BANISHED_WHO, 0)
        return

    difficulty = fight.token_count(caster, BANISHED_DIFFICULTY) - 1
    fight.set_token(caster, BANISHED_DIFFICULTY, difficulty)

    if not roll_d20(evasion=difficulty).is_success:
        fight.note(f"{banished.name} claws at the veil and fails ({difficulty})")
        return

    fight.set_token(caster, BANISHED_WHO, 0)
    fight.summon(banished)
    fight.note(f"{banished.name} returns from banishment")


# --- Level 5: assessed and dismissed ------------------------------------------
#
# Codex stops printing Grimoires at level 5 and prints plain Spells instead, so
# these two are cards in their own right rather than entries inside a book -
# which is why they are declared here rather than beside one.

no_combat_effect(
    "Manifest Wall",
    "A Spellcast Roll (15), then once per rest a Hope raises a temporary magical "
    "wall between two points within Far range at any angle; creatures and objects "
    "in its path are shunted to a side of the caster's choice, and it stands until "
    "the next rest. Terrain and a shunt, and no positions are tracked - the "
    "standing answer for content whose whole effect is where somebody is standing. "
    "Deliberately **not** the Wall of Flame case: that one was ruled to the area "
    "rule's Far band because anything passing through it takes 4d10+3, and there "
    "was damage to place. This wall deals nothing, so there is nothing to place.",
)

no_combat_effect(
    "Teleport",
    "Once per long rest, a Spellcast Roll (16) puts the caster and any number of "
    "willing targets within Close range at a place they have been before, with the "
    "roll modified by how well they know it and a scattered arrival on a failure. "
    "Travel - the Blink Out case at a much longer range, and no positions are "
    "tracked. Worth knowing that modelling it would make a party *worse*: the cast "
    "spends a whole action roll to buy nothing here, where at a table it is how a "
    "party leaves a fight it cannot win.",
)


# --- Codex-Touched ---------------------------------------------------------------

CODEX_TOUCHED = "Codex-Touched"

# SIMULATION RULE - policy, ruled. The card sets no limit at all, and the standing
# default for a Stress-priced rider is the shared last-slot rule. The user ruled
# **against** that here and set a ceiling instead: the Stress is not marked once
# this many slots are already marked. A rider asked on *every* cast would otherwise
# run a caster's whole track through one card in three or four spotlights.
CODEX_TOUCHED_STRESS_CEILING = 3


@spellcast_bonus(
    CODEX_TOUCHED,
    unmodelled=[
        "'When 4 or more of the domain cards in your loadout are from the Codex "
        "domain' - the loadout is not counted. The user's ruling is that carrying "
        "the card is taken as proof the condition is met, since a player who takes "
        "it has built for it. Recorded as a simulation rule rather than checked",
        "'Once per rest, replace this card with any card from your vault without "
        "paying its Recall Cost' - nothing models a loadout changing mid-fight. "
        "Counterspell is the one card that reaches the vault at all and does so "
        "for itself alone, by the user's ruling; a general swap would need a "
        "loadout that can be rewritten and a rule for what to swap in",
        "Two Spellcast Rolls the hook is not asked at - Splendor's Healing Hands "
        "and Grace's Invisibility roll `roll_duality` by hand rather than through "
        "the shared shape, for the reason recorded at the end of "
        "domain_cards/PORTED.md",
    ],
)
def codex_touched(caster: Holder, target, fight: Fight = None) -> int:
    """Codex-Touched (Codex, level 7), the clause that bites.

    SRD: "When 4 or more of the domain cards in your loadout are from the Codex
    domain, gain the following benefits: you can mark a Stress to add your
    Proficiency to a Spellcast Roll; once per rest, replace this card with any card
    from your vault without paying its Recall Cost."

    **Being asked is the commitment**, which is this hook's contract - the roll
    follows immediately - so the Stress is marked here rather than needing anything
    afterwards to confirm the cast happened.

    SIMULATION RULE - policy, ruled. Marked while **fewer than
    `CODEX_TOUCHED_STRESS_CEILING` slots are already marked**, rather than by the
    shared last-slot rule every other Stress cost asks. The user ruled this one
    specially and the reason is the trigger: this is asked on *every* Spellcast
    Roll, so the standing rule would spend the caster's whole track on it within a
    few spotlights and leave nothing for the cards that also want Stress. The
    ceiling caps it at three casts between clears.

    `can_spend_stress` rather than `will_spend_stress`, deliberately: the ceiling
    replaces the willingness rule rather than sitting on top of it, and the check
    that remains is only that a slot exists at all.
    """
    if fight is None or caster.stress_marked >= CODEX_TOUCHED_STRESS_CEILING:
        return 0
    if not caster.can_spend_stress(1):
        return 0

    caster.spend_stress(1)
    fight.note(
        f"{caster.name} marks a Stress; the cast carries their full Proficiency "
        f"(+{caster.proficiency})"
    )
    return caster.proficiency


# --- Book of Homet ---------------------------------------------------------------
#
# The second book in the domain with nothing implemented, after Vagras, and
# declared the same way: both of its spells are passage, so the *book* is declared
# under its own name as well. A Grimoire with no spell registered would report the
# card as unimplemented, which is the wrong answer for something read and assessed.

no_combat_effect(
    "Book of Homet",
    "Both spells are passage. Pass Through is a Spellcast Roll (13) that carries "
    "the party through a wall or door within Close range, ending once everyone is "
    "on the other side; Plane Gate is a Spellcast Roll (14) opening a gateway to "
    "another dimension or plane the caster has been to, lasting until the next "
    "rest. Neither touches anybody's numbers, grants a roll in a fight or makes an "
    "attack - the standing answer for content whose whole effect is where somebody "
    "is standing, which the domain has already given Arcane Door and Teleport.",
)
no_combat_effect(
    "Pass Through",
    "A Spellcast Roll (13) moves the party through a wall or door within Close "
    "range. There are no walls in a simulated fight and no positions are tracked, "
    "so there is nothing to pass through and nowhere to arrive. At a table it is "
    "how a party gets somewhere the fight was not.",
)
no_combat_effect(
    "Plane Gate",
    "A Spellcast Roll (14) opens a gateway to a location on another plane the "
    "caster has visited, lasting until their next rest. Travel, at the longest "
    "range the domain prints - the Teleport case, and dismissed for the same "
    "reason: an encounter is one place, and leaving it is not something the "
    "simulator represents.",
)


# --- Book of Vyola ---------------------------------------------------------------
#
# The third book in the domain with nothing implemented, after Vagras and Homet,
# and declared the same way: the *book* carries its own declaration alongside its
# two spells, because a Grimoire with no spell registered would report the card as
# unimplemented - the wrong answer for something read and assessed.
#
# Worth recording that its two spells are dismissed for **different** reasons, and
# that the second was a real decision rather than an obvious one.

no_combat_effect(
    "Book of Vyola",
    "Neither spell reaches a fight. Memory Delve buys information about a target's "
    "past; Shared Clarity pairs two willing creatures so either can take a Stress "
    "the other would mark, which is a real and fully represented effect that the "
    "user ruled makes no difference across a high-N run. Declared under the book's "
    "own name as well as per spell, so the card never reads as work nobody has "
    "done.",
)
no_combat_effect(
    "Memory Delve",
    "A Spellcast Roll against a target within Far range; on a success the caster "
    "peers into their mind and the GM describes any memories pertaining to a "
    "question asked. Information about a target's past, which is the Telepathy, "
    "Recant and Divination case - nothing about a fight's outcome turns on what an "
    "adversary remembers, and the spell makes no attack and moves no number.",
)
no_combat_effect(
    "Shared Clarity",
    "Once per long rest, a Hope pairs two willing creatures until their next rest; "
    "when one of them would mark Stress, the pair choose between them who marks "
    "it. Stress is tracked closely here, so the dismissal is not about the "
    "resource being invisible: it is that the effect is **symmetrical**, and so "
    "has nothing in an outcome to touch. The pair mark the same total Stress "
    "either way, and all the card decides is which of the two tracks fills first. "
    "That is the user's ruling, in their words - it does nothing across a high-N "
    "run. Worth naming what was declined "
    "alongside it, since the machinery was costed: `PlayerCharacter.spend_stress` "
    "is called from dozens of places with no fight in hand, so the partner cannot "
    "be found from there, and both ways of fixing that - an optional `fight` "
    "threaded through the Stress path, and a required one - were offered and "
    "declined.",
)


# --- Safe Haven ------------------------------------------------------------------

out_of_combat_ability(
    "Safe Haven",
    "A few minutes of calm and 2 Hope summon a large interdimensional home behind "
    "a door within Close range, which only creatures of the caster's choice can "
    "enter and whose entrance can be made invisible; taking a rest inside it grants "
    "an additional downtime move. **Not a dismissal.** The extra downtime move is "
    "real, fully representable and one of the larger things a party can buy - a "
    "long rest move clears every marked HP or every Stress - which is precisely why "
    "this is not filed as having no combat effect. What it is not is a combat move: "
    "'a few minutes of calm to focus' is a condition a fight never meets, so the "
    "card belongs to the sequenced-encounter machinery that does not exist yet. "
    "Mending Touch's and Recovery's state, and the shelter half is the Blink Out "
    "case sitting underneath it - no positions are tracked, so leaving a fight is "
    "not something the simulator represents either.",
)
