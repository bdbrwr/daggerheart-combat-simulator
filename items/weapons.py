"""Swinging a weapon - the one attack shape every weapon shares.

A weapon used to be a callable per weapon, with its stats baked into the
arguments it passed. It isn't any more: a weapon's numbers are a record in a JSON
catalogue (see catalogue.py) and everything it does beyond those numbers is a
named feature in features/weapons.py. What's left here is the shape itself, which
is the same for all of them - roll the weapon's trait against the target's
Difficulty, and on a hit roll Proficiency dice of the weapon's size.

That change is what makes the 61st weapon free. Under the old arrangement,
Reliable was `attack_bonus=1` and Massive was `discards_lowest=True` - parameters
on shared machinery that existed because of two specific named features, which is
exactly the coupling the content registry exists to prevent. Now this module
knows no weapon and no feature by name; it calls dispatch, twice, and the
features answer for themselves.

## Why a weapon's features are scoped and a holder's are not

Content a character *carries* applies to everything they do, so dispatch scans
`named_features` and this module needn't think about it. A weapon's feature is
different: Reliable is "+1 to attack rolls" **with that weapon**, and letting it
sum holder-wide would silently add it to a Grimoire spell. So the weapon's own
feature names are passed explicitly, and every attack consults both scopes.

Range is recorded on the record and otherwise unused - nothing in the simulator
tracks distance. See SIMULATION-RULES.md.
"""

from typing import Protocol

from combat.results import AttackResult
from content import (
    DamagePool,
    adjust_damage_pool,
    remake_action_roll,
    total_extra_damage,
    total_roll_bonus,
)
from content.registry import apply_before_attacked, apply_on_attacked
from dice.common import AdvantageState, combined
from dice.damage import DiceGroup, roll_damage
from dice.duality import roll_duality
from items.catalogue import Weapon


class Attacker(Protocol):
    """The slice of a PC a weapon touches.

    A Protocol rather than importing PlayerCharacter: characters/ resolves its
    gear through items/, and the import can't run both ways.
    """

    traits: dict[str, int]
    proficiency: int
    named_features: list[str]


class Target(Protocol):
    """Anything a PC's weapon can attack - an adversary."""

    difficulty: int

    # Scanned for content that punishes being hit, which belongs to whoever was
    # attacked rather than to whoever swung.
    named_features: list[str]

    def take_damage(self, amount: int, fight=None) -> int: ...


def attack_with(
    attacker: Attacker,
    weapon: Weapon,
    target: Target,
    advantage_state: AdvantageState = AdvantageState.NONE,
    bonus: int = 0,
    damage_bonus: int = 0,
    hope_die: int = 12,
    fight=None,
) -> AttackResult:
    """Attack `target` with `weapon`, rolling and applying damage on a hit.

    `bonus` is a flat add to the attack roll from outside the weapon - an
    Experience the PC spent Hope on, mostly - and `damage_bonus` is the same idea
    for damage. Both are parameters rather than something worked out here,
    because whether an Experience or a domain card applies is a decision made by
    the acting character, not by the sword.

    `damage_bonus` is added before the target's thresholds are consulted, so it
    can change how many HP a hit marks and not just the number printed. So is
    everything the two dispatch calls below contribute, for the same reason.
    """
    # Content the *target* carries that interrupts an attack before it is rolled -
    # the Harrier's Fall Back, which counterattacks the moment somebody closes to
    # Melee. Fired first, because "before the attack roll" is the trigger, and it
    # cannot stop what follows: the swing happens either way. Nothing here knows
    # what any of it is.
    apply_before_attacked(target, attacker, weapon, fight)

    # A condition can hobble the trait this weapon rolls - the Archer Guard's
    # Hobbling Shot leaves its target with disadvantage on Agility Rolls. Folded
    # in rather than overwriting, so a PC attacking with Advantage and hobbled at
    # once ends up where the SRD puts them: the two cancel.
    if fight is not None and fight.disadvantaged_on(attacker, weapon.trait):
        advantage_state = combined(advantage_state, AdvantageState.DISADVANTAGE)

    # Worked out once, before the roll, and *outside* the closure below: asking
    # content for a roll bonus is the commitment, so several of them spend Hope
    # or mark Stress on being asked. A reroll re-makes the dice, not the
    # decisions that fed them - evaluating this twice would charge for it twice.
    modifier = (
        # Indexed, not `.get(..., 0)`: the catalogue already validated the
        # trait against the six real ones and sheets lowercase their trait
        # keys, so a miss here is a broken sheet and should say so rather
        # than quietly rolling a flat zero.
        attacker.traits[weapon.trait]
        + bonus
        + total_roll_bonus(attacker, target, fight, names=weapon.named_features)
    )

    def roll():
        return roll_duality(
            modifier=modifier,
            difficulty=target.difficulty,
            advantage_state=advantage_state,
            hope_die=hope_die,
        )

    # Content that can re-make a resolved roll gets its say before anything
    # reads the result, so a reroll is indistinguishable from having rolled that
    # way first. It re-makes the roll through the same closure, on identical
    # terms.
    attack_roll = remake_action_roll(attacker, roll(), roll, fight)

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    # The weapon's own pool first, reshaped by its own features - this is where
    # Massive and Powerful roll their extra die and discard the lowest, and the
    # discard is theirs alone, reaching only the dice the weapon rolled.
    pool = adjust_damage_pool(
        attacker,
        weapon,
        DamagePool(
            dice_groups=[DiceGroup(count=attacker.proficiency, sides=weapon.damage_die)],
            drop_lowest=0,
            modifier=weapon.damage_modifier,
        ),
        fight,
        names=weapon.named_features,
    )

    # Then content the *character* carries that adds dice conditional on how the
    # attack came out. These join the same roll so they're counted once against
    # the target's thresholds - and they sit outside the weapon's discard, since
    # a Greatstaff's Powerful has no business throwing away a Wizard's die.
    dice_groups = list(pool.dice_groups)
    dice_groups += total_extra_damage(attacker, target, attack_roll, fight)

    damage_roll = roll_damage(
        dice_groups=dice_groups,
        modifier=pool.modifier + damage_bonus,
        is_critical=attack_roll.is_critical,
        drop_lowest=pool.drop_lowest,
    )
    marked = target.take_damage(damage_roll.total)

    # Content the *target* carries that punishes being hit - the Glass Snake's
    # shards of glass. Asked after the damage lands, because the trigger is a
    # successful attack rather than a wound, and handed the weapon because how
    # far away the attacker was standing is the only thing such content has to
    # read range off. Nothing here knows what any of it is.
    apply_on_attacked(target, attacker, weapon, damage_roll.total, fight)

    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )
