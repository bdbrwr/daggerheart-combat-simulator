"""Weapon features.

Registered under the weapon feature's own name, namespaced - `weapon:Reliable`,
not `Reliable`. The SRD gives a Warhammer the feature "Heavy" and Chainmail Armor
the feature "Heavy", and they are two different pieces of content that happen to
share a word; in a flat namespace the second would collide with the first. Nobody
types the prefix: items/*.json says `"features": ["Reliable"]` and the catalogue
qualifies it. See content/names.py.

## These are scoped to the weapon, not to the character

Every other module in this package registers content a *character* carries, which
applies to everything they do. A weapon's feature doesn't: Reliable is "+1 to
attack rolls" **with that weapon**, and a Wizard's spell attack must not pick it
up because their party's Guardian happens to be holding a Broadsword. So
items/weapons.py passes the weapon's own feature names to dispatch rather than
letting it scan `named_features`, and these fire only for attacks made with the
weapon that has them.

## Features the sheet has already applied

Same rule as everywhere else: a weapon feature whose whole effect is a number the
character sheet states - Massive's -1 to Evasion - is already in that number by
the time a sheet is written, so it isn't applied again here. It's noted in the
docstring rather than declared as a gap, because it isn't a gap: the effect is
in the simulation, just carried by the sheet instead of by this code.
"""

from content.names import WEAPON, qualified
from content.registry import DamagePool, Fight, Holder, damage_pool, roll_bonus
from dice.damage import DiceGroup

RELIABLE_BONUS = 1


@roll_bonus(qualified(WEAPON, "Reliable"))
def reliable(attacker: Holder, target, fight: Fight) -> int:
    """*Reliable*: +1 to attack rolls.

    Scoped to the weapon, so this reaches attacks made with it and nothing else.
    """
    return RELIABLE_BONUS


def _extra_die_discarding_the_lowest(
    attacker: Holder, weapon, pool: DamagePool, fight=None, roll=None
) -> DamagePool:
    """Roll one more of the weapon's own dice, then throw the lowest away.

    Shared because *Massive* and *Powerful* say exactly the same thing about
    damage; they differ only in that Massive also costs a point of Evasion, which
    the character sheet already carries.

    The extra die is added to the weapon's own pool and the discard is recorded
    on the roll, so `dice/damage.py` takes the lowest back off. Both halves stay
    inside the weapon's dice: `DiceGroup.discardable` is what keeps a Greatstaff
    from throwing away a die that School of War's Face Your Fear contributed.
    Only the first discardable group grows, since a weapon rolls one pool - if a
    future feature adds a second, it shouldn't silently get a free die too.
    """
    groups, grown = [], False
    for group in pool.dice_groups:
        if group.discardable and not grown:
            groups.append(
                DiceGroup(
                    count=group.count + 1,
                    sides=group.sides,
                    discardable=group.discardable,
                )
            )
            grown = True
        else:
            groups.append(group)

    if not grown:  # nothing of the weapon's own to add to, so nothing to discard
        return pool

    return pool._replace(dice_groups=groups, drop_lowest=pool.drop_lowest + 1)


@damage_pool(qualified(WEAPON, "Massive"))
def massive(
    attacker: Holder, weapon, pool: DamagePool, fight=None, roll=None
) -> DamagePool:
    """*Massive*: -1 to Evasion; on a successful attack, roll an additional
    damage die and discard the lowest result.

    The Evasion penalty is not applied here - a character sheet stores Evasion
    already resolved, so subtracting it again would charge the PC twice.
    """
    return _extra_die_discarding_the_lowest(attacker, weapon, pool, fight)


@damage_pool(qualified(WEAPON, "Powerful"))
def powerful(
    attacker: Holder, weapon, pool: DamagePool, fight=None, roll=None
) -> DamagePool:
    """*Powerful*: on a successful attack, roll an additional damage die and
    discard the lowest result.

    Massive without the Evasion cost.
    """
    return _extra_die_discarding_the_lowest(attacker, weapon, pool, fight)
