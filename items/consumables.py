"""Consumable items.

Each consumable is a callable, not a data record. Weapons and armor became
records because a weapon has printed stats that a fight reads; a potion has none
- its whole existence is what it does when drunk, so that's what the code is.

Consumables are deliberately kept few, which is why they have no catalogue of
their own and are registered by a decorator instead.
"""

from typing import Protocol

from dice.damage import DiceGroup, roll_damage
from items.registry import consumable


class Drinker(Protocol):
    """The slice of a PC a consumable touches.

    A Protocol rather than importing PlayerCharacter: characters/ resolves its
    gear through items/, so importing back the other way would make the two
    packages a cycle - `characters` would be half-initialised at the moment this
    module asked it for a name.
    """

    def clear_hp(self, amount: int) -> None: ...
    def clear_stress(self, amount: int) -> None: ...


@consumable("Minor Healing Potion")
def minor_healing_potion(character: Drinker) -> int:
    """Minor Health Potion: clear 1d4 HP. Returns the amount cleared."""
    roll = roll_damage(dice_groups=[DiceGroup(count=1, sides=4)])
    amount = roll.total
    character.clear_hp(amount)
    return amount


@consumable("Minor Stamina Potion")
def minor_stamina_potion(character: Drinker) -> int:
    """Minor Stamina Potion: clear 1d4 Stress. Returns the amount cleared.

    The other half of the pair a PC starts with, and it matters more here than
    it looks. Stress is what several cards are paid for - Get Back Up, I Am Your
    Shield, the beetles - and marking the last of it makes a PC Vulnerable, so
    every roll against them has Advantage. Clearing Stress mid-fight buys both
    of those back.
    """
    roll = roll_damage(dice_groups=[DiceGroup(count=1, sides=4)])
    amount = roll.total
    character.clear_stress(amount)
    return amount
