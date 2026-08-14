"""Consumable items.

Each consumable is a callable, not a data record, for the same reason as items/weapons.py: using one is a mutation of the PC that used it, so that's what the code does directly rather than describing the item for something else to interpret later.
"""

from characters.player_character import PlayerCharacter
from dice.damage import DiceGroup, roll_damage
from items.registry import consumable


@consumable("Minor Healing Potion")
def minor_healing_potion(character: PlayerCharacter) -> int:
    """Minor Health Potion: clear 1d4 HP. Returns the amount cleared."""
    roll = roll_damage(dice_groups=[DiceGroup(count=1, sides=4)])
    amount = roll.total
    character.clear_hp(amount)
    return amount


@consumable("Minor Stamina Potion")
def minor_stamina_potion(character: PlayerCharacter) -> int:
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
