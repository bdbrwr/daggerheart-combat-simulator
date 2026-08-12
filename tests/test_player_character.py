from pathlib import Path

from characters.player_character import PlayerCharacter

EXAMPLE_CHARACTER_PATH = Path(__file__).parent.parent / "characters" / "example_character.json"


def _make_character(**overrides) -> PlayerCharacter:
    defaults = dict(
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
    )
    defaults.update(overrides)
    return PlayerCharacter(**defaults)


def test_from_json_loads_example_character():
    character = PlayerCharacter.from_json(EXAMPLE_CHARACTER_PATH)

    assert character.name == "Kael Ashgrove"
    assert character.character_class == "Guardian"
    assert character.evasion == 9
    assert character.proficiency == 1
    assert character.major_threshold == 6
    assert character.severe_threshold == 12
    assert character.hp_max == 7
    assert character.hope_marked == 2
    assert character.primary_weapon == "Broadsword"
    assert character.secondary_weapon is None
    assert character.armor_item == "Gambeson Armor"
    assert character.domain_cards_loadout == ["I Am Your Shield", "Get Back Up"]
    assert character.domain_cards_vault == []


def test_mark_hp_clamps_to_max():
    character = _make_character(hp_max=7)
    character.mark_hp(10)
    assert character.hp_marked == 7


def test_clear_hp_clamps_to_zero():
    character = _make_character(hp_max=7)
    character.hp_marked = 3
    character.clear_hp(10)
    assert character.hp_marked == 0


def test_mark_stress_clamps_to_max():
    character = _make_character(stress_max=6)
    character.mark_stress(10)
    assert character.stress_marked == 6


def test_mark_armor_slot_clamps_to_max():
    character = _make_character(armor_max=3)
    character.mark_armor_slot(10)
    assert character.armor_marked == 3


def test_gain_hope_clamps_to_max():
    character = _make_character(hope_max=6)
    character.gain_hope(10)
    assert character.hope_marked == 6


def test_spend_hope_clamps_to_zero():
    character = _make_character(hope_max=6)
    character.hope_marked = 2
    character.spend_hope(10)
    assert character.hope_marked == 0


def test_take_damage_marks_nothing_below_zero_or_zero():
    character = _make_character(major_threshold=6, severe_threshold=12)
    assert character.take_damage(0) == 0
    assert character.take_damage(-5) == 0
    assert character.hp_marked == 0


def test_take_damage_below_major_marks_one():
    character = _make_character(major_threshold=6, severe_threshold=12)
    assert character.take_damage(5) == 1
    assert character.hp_marked == 1


def test_take_damage_at_major_marks_two():
    character = _make_character(major_threshold=6, severe_threshold=12)
    assert character.take_damage(6) == 2
    assert character.hp_marked == 2


def test_take_damage_at_severe_marks_three():
    character = _make_character(major_threshold=6, severe_threshold=12)
    assert character.take_damage(12) == 3
    assert character.hp_marked == 3


def test_take_damage_well_above_severe_still_marks_three():
    character = _make_character(major_threshold=6, severe_threshold=12)
    assert character.take_damage(100) == 3
    assert character.hp_marked == 3
