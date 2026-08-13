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
    character = _make_character(stress_max=6, hp_max=7)
    character.mark_stress(10)
    assert character.stress_marked == 6


# --- Stress: forced vs voluntary ---------------------------------------------
#
# The SRD splits these two apart and the simulator has to as well. Forced
# Stress ("must mark 1 or more Stress but can't") overflows into a single HP;
# a voluntary cost ("mark a Stress" on a card) is simply unavailable when
# Stress is full and must never touch HP.


def test_forced_stress_that_does_not_fit_marks_one_hp():
    character = _make_character(stress_max=2, hp_max=7)
    character.mark_stress(2)

    character.mark_stress(1)

    assert character.stress_marked == 2
    assert character.hp_marked == 1


def test_the_overflow_is_one_hp_however_much_stress_did_not_fit():
    character = _make_character(stress_max=2, hp_max=7)

    character.mark_stress(9)

    assert character.stress_marked == 2
    assert character.hp_marked == 1


def test_forced_stress_overflowing_onto_the_last_hp_still_drops_the_pc():
    character = _make_character(stress_max=1, hp_max=1, level=0)
    character.mark_stress(1)

    character.mark_stress(1)

    assert character.hp_marked == 1
    assert character.unconscious is True


def test_stress_that_fits_never_touches_hp():
    character = _make_character(stress_max=6, hp_max=7)

    character.mark_stress(6)

    assert character.stress_marked == 6
    assert character.hp_marked == 0


def test_a_voluntary_stress_cost_is_refused_rather_than_paid_in_hp():
    character = _make_character(stress_max=2, hp_max=7)
    character.mark_stress(2)

    assert character.can_spend_stress(1) is False
    assert character.spend_stress(1) is False
    assert character.hp_marked == 0  # the move is off the table, not paid for


def test_a_voluntary_stress_cost_is_paid_when_there_is_room():
    character = _make_character(stress_max=2, hp_max=7)

    assert character.spend_stress(1) is True
    assert character.stress_marked == 1


def test_a_voluntary_cost_bigger_than_the_free_slots_is_all_or_nothing():
    character = _make_character(stress_max=2, hp_max=7)
    character.mark_stress(1)

    assert character.spend_stress(2) is False
    assert character.stress_marked == 1


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


# The threshold tests pin armor_max=0 so they measure the threshold math only.
# With armor available a PC spends a slot to soften anything Major or worse,
# which is what the armor tests further down cover.


def test_take_damage_marks_nothing_below_zero_or_zero():
    character = _make_character(major_threshold=6, severe_threshold=12, armor_max=0)
    assert character.take_damage(0) == 0
    assert character.take_damage(-5) == 0
    assert character.hp_marked == 0


def test_take_damage_below_major_marks_one():
    character = _make_character(major_threshold=6, severe_threshold=12, armor_max=0)
    assert character.take_damage(5) == 1
    assert character.hp_marked == 1


def test_take_damage_at_major_marks_two():
    character = _make_character(major_threshold=6, severe_threshold=12, armor_max=0)
    assert character.take_damage(6) == 2
    assert character.hp_marked == 2


def test_take_damage_at_severe_marks_three():
    character = _make_character(major_threshold=6, severe_threshold=12, armor_max=0)
    assert character.take_damage(12) == 3
    assert character.hp_marked == 3


def test_take_damage_well_above_severe_still_marks_three():
    character = _make_character(major_threshold=6, severe_threshold=12, armor_max=0)
    assert character.take_damage(100) == 3
    assert character.hp_marked == 3


def test_armor_slot_is_spent_to_soften_a_major_hit():
    character = _make_character(major_threshold=6, severe_threshold=12, armor_max=3)
    assert character.take_damage(6) == 1
    assert character.armor_marked == 1


def test_armor_slot_takes_a_minor_hit_down_to_nothing():
    """A free slot is always spent, so a 1 HP hit costs the slot and no HP."""
    character = _make_character(major_threshold=6, severe_threshold=12, armor_max=3)
    assert character.take_damage(5) == 0
    assert character.hp_marked == 0
    assert character.armor_marked == 1


def test_no_armor_slot_is_spent_on_damage_that_never_landed():
    character = _make_character(major_threshold=6, severe_threshold=12, armor_max=3)
    assert character.take_damage(0) == 0
    assert character.armor_marked == 0


def test_armor_slot_is_not_spent_once_they_are_all_marked():
    character = _make_character(major_threshold=6, severe_threshold=12, armor_max=1)
    character.armor_marked = 1
    assert character.take_damage(12) == 3
    assert character.armor_marked == 1


def test_marking_the_last_hp_drops_the_pc_unconscious():
    character = _make_character(hp_max=3, major_threshold=6, severe_threshold=12, armor_max=0)
    character.take_damage(12)
    assert character.hp_marked == 3
    assert character.unconscious is True
    assert character.is_conscious is False


def test_a_pc_who_is_still_up_stays_conscious():
    character = _make_character(hp_max=7, major_threshold=6, severe_threshold=12, armor_max=0)
    character.take_damage(12)
    assert character.is_conscious is True


def test_avoid_death_scars_when_the_hope_die_is_at_or_under_level():
    """The scar roll is a d12 against level, so the two ends of it are certain.

    A level 12 PC can't roll above their level and always scars; a level 0 one
    never can. No seeding needed - the outcome is fixed by construction.
    """
    scarring = _make_character(level=12, hope_max=6)
    assert scarring.avoid_death() is True
    assert scarring.scars == 1
    assert scarring.hope_max == 5
    assert scarring.unconscious is True

    unscarred = _make_character(level=0, hope_max=6)
    assert unscarred.avoid_death() is False
    assert unscarred.scars == 0
    assert unscarred.hope_max == 6
    assert unscarred.unconscious is True


def test_vulnerable_once_the_last_stress_is_marked():
    character = _make_character(stress_max=2)
    assert character.is_vulnerable is False
    character.mark_stress(2)
    assert character.is_vulnerable is True
