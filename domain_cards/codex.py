"""Codex domain cards.

Every Codex card at levels 1-2 is a Grimoire - a single card holding three
spells - so they're built with content/grimoire.py: each spell is its own
function, and the book registers a dispatcher under the name a character sheet
writes.

Card text is paraphrased in each docstring rather than quoted in full. The
verbatim text is in .reference/abilities.json, and was checked against the
printed page (SRD pp. 124-125) for all five books.

A Codex book is mostly utility, and that is a fact about the domain rather than
a gap: of the fifteen spells in the five books, six change a fight. The rest are
declared `no_combat_effect` at the bottom under their own names *and* noted as
gaps on their book, so a reader of the coverage report sees both which book is
partly implemented and which spell inside it was dismissed.
"""

import random

from combat.results import AttackResult
from content.aoe import Range, area_difficulty, targets_beaten, targets_in_area
from content.damage_types import DamageType
from content.grimoire import Grimoire
from content.registry import (
    Fight,
    Holder,
    ally_on_hit,
    hope_die_for,
    no_combat_effect,
    remake_action_roll,
    total_extra_damage,
    total_roll_bonus,
)
from dice.damage import DiceGroup, roll_damage
from dice.duality import roll_duality

# The GM's pool has to be worth draining before spending a spotlight's roll on a
# condition that deals no damage. Below this, damage is the better use.
FEAR_WORTH_DRAINING = 3

# Arcane Barrage spends Hope down to this floor. Hope is the currency for
# Experiences and several other cards, so a caster who empties it into one
# barrage is trading away every later option.
BARRAGE_HOPE_FLOOR = 2


def _spellcast(
    caster: Holder, target, fight: Fight, bonus: int = 0, difficulty: int | None = None
):
    """A Spellcast Roll against a target's Difficulty, or None if we can't make one.

    Rolled against `target`'s Difficulty unless one is given - an area spell is
    rolled against the whole area at once and passes `area_difficulty` instead,
    exactly as the Sage module's twin of this helper does.

    A sheet that names no `spellcast_trait` declines to cast rather than
    guessing a trait, which shows up as content that never fires rather than as
    content that quietly fires wrong.

    Asks for the Hope Die rather than assuming a d12, so anything that swaps it
    applies to spells as much as to weapon swings - and offers the result to
    `remake_action_roll` for the same reason, so a Luckbender or an Adaptability
    reaches a spell as readily as it reaches a swing.
    """
    trait = getattr(caster, "spellcast_trait", "")
    if not trait or trait not in caster.traits:
        return None

    # Asked only once the cast is going ahead, so a spell that declines above
    # never spends a token or a per-rest use toward a roll it isn't making - and
    # asked outside the closure, so a reroll re-makes the dice without charging
    # for the bonuses a second time.
    modifier = caster.traits[trait] + bonus + total_roll_bonus(caster, target, fight)
    against = target.difficulty if difficulty is None else difficulty
    hope_die = hope_die_for(caster, fight)

    def roll():
        return roll_duality(modifier=modifier, difficulty=against, hope_die=hope_die)

    return remake_action_roll(caster, roll(), roll, fight)


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
    attack_roll = _spellcast(caster, target, fight)
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
    attack_roll = _spellcast(caster, target, fight)
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

    attack_roll = _spellcast(caster, target, fight)
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

    attack_roll = _spellcast(caster, target, fight, difficulty=area_difficulty(area))
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
