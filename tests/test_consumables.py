from unittest.mock import patch

from characters.player_character import PlayerCharacter
from dice.damage import DamageRollResult, DiceGroup
from items.consumables import minor_healing_potion


def _make_character() -> PlayerCharacter:
    return PlayerCharacter(
        name="Test PC",
        level=1,
        character_class="Guardian",
        subclass="Stalwart",
        ancestry="Human",
        community="Wanderborne",
        traits={"agility": 0, "strength": 2, "finesse": 0, "instinct": 1, "presence": 1, "knowledge": -1},
        evasion=9,
        proficiency=1,
        major_threshold=6,
        severe_threshold=12,
        hp_max=7,
        stress_max=6,
        hope_max=6,
        armor_max=3,
        primary_weapon="Broadsword",
        secondary_weapon=None,
        armor_item="Gambeson Armor",
        domain_cards_loadout=[],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
        hp_marked=5,
    )


def test_minor_healing_potion_clears_the_rolled_amount():
    character = _make_character()
    fixed_roll = DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=4)],
        die_results=[[3]],
        modifier=0,
    )
    with patch("items.consumables.roll_damage", return_value=fixed_roll):
        healed = minor_healing_potion(character)

    assert healed == 3
    assert character.hp_marked == 2


def test_minor_healing_potion_clamps_hp_marked_at_zero():
    character = _make_character()
    character.hp_marked = 1
    fixed_roll = DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=4)],
        die_results=[[4]],
        modifier=0,
    )
    with patch("items.consumables.roll_damage", return_value=fixed_roll):
        healed = minor_healing_potion(character)

    assert healed == 4
    assert character.hp_marked == 0
