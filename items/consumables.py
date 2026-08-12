"""Consumable items.

Each consumable is a callable, not a data record, for the same reason as items/weapons.py: using one is a mutation of the PC that used it, so that's what the code does directly rather than describing the item for something else to interpret later.
"""

from characters.player_character import PlayerCharacter
from dice.damage import DiceGroup, roll_damage


def minor_healing_potion(character: PlayerCharacter) -> int:
    """Minor Health Potion: clear 1d4 HP. Returns the amount cleared."""
    roll = roll_damage(dice_groups=[DiceGroup(count=1, sides=4)])
    amount = roll.total
    character.clear_hp(amount)
    return amount
