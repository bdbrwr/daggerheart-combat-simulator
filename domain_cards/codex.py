"""Codex domain cards.

Both of the implemented ones are Grimoires - a single card holding three spells
- so they're built with content/grimoire.py: each spell is its own function, and
the book registers a dispatcher under the name a character sheet writes.

Card text is paraphrased in each docstring rather than quoted in full. The
verbatim text is in .reference/abilities.json.
"""

from combat.results import AttackResult
from content.damage_types import DamageType
from content.grimoire import Grimoire
from content.registry import (
    Fight,
    Holder,
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


def _spellcast(caster: Holder, target, fight: Fight, bonus: int = 0):
    """A Spellcast Roll against a target's Difficulty, or None if we can't make one.

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
    hope_die = hope_die_for(caster, fight)

    def roll():
        return roll_duality(
            modifier=modifier, difficulty=target.difficulty, hope_die=hope_die
        )

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
