"""Reading a stat block whose thresholds the book prints as `None`.

Minions, and small things like the Tiny Green Ooze on 2 HP, have no damage
thresholds at all - they have fewer HP than a threshold could ever become
relevant for. `NO_THRESHOLD` puts them out of reach, so every hit lands in the
lowest band.

The failure this guards against is the obvious wrong answer: a threshold of zero
would put *every* hit at or above Severe and mark 3 HP off a 1 HP track.
"""

import pytest

from adversaries.catalogue import NO_THRESHOLD, adversary_from_data, parse_threshold

MINION = {
    "name": "Giant Rat",
    "tier": 1,
    "type": "Minion",
    "difficulty": 10,
    "major_threshold": None,
    "severe_threshold": None,
    "hp_max": 1,
    "stress_max": 1,
    "attack_modifier": -4,
    "damage_dice": "",
    "damage_modifier": 1,
}


def _entry(**overrides) -> dict:
    return {**MINION, **overrides}


def test_a_null_threshold_is_read_as_out_of_reach():
    assert parse_threshold(None, "srd.json", "Giant Rat") == NO_THRESHOLD


def test_the_string_none_is_read_the_same_way():
    """The reference data spells it one way and a typed entry may spell it the other."""
    assert parse_threshold("None", "srd.json", "Giant Rat") == NO_THRESHOLD
    assert parse_threshold("none", "srd.json", "Giant Rat") == NO_THRESHOLD


def test_an_ordinary_threshold_is_just_a_number():
    assert parse_threshold(8, "srd.json", "Bandit") == 8


def test_a_threshold_that_is_neither_raises_and_names_the_entry():
    with pytest.raises(ValueError, match="Giant Rat"):
        parse_threshold("shallow", "srd.json", "Giant Rat")


def test_a_minion_takes_the_lowest_band_from_any_hit():
    """The whole point: no hit is ever Major or Severe against them."""
    rat = adversary_from_data(_entry(), "SRD", "srd.json")

    assert rat.take_damage(1) == 1
    assert rat.hp_marked == 1


def test_even_an_enormous_hit_marks_one_hp():
    rat = adversary_from_data(_entry(), "SRD", "srd.json")
    assert rat.take_damage(500) == 1


def test_a_minion_is_defeated_by_that_one_hp():
    rat = adversary_from_data(_entry(), "SRD", "srd.json")
    rat.take_damage(1)
    assert rat.is_defeated


def test_an_attack_with_no_dice_at_all_loads():
    """The Giant Rat deals a flat 1 - the whole attack is its modifier."""
    rat = adversary_from_data(_entry(), "SRD", "srd.json")

    assert rat.damage_dice == []
    assert rat.damage_modifier == 1


def test_the_type_is_carried_but_never_read_by_a_fight():
    rat = adversary_from_data(_entry(), "SRD", "srd.json")
    assert rat.type == "Minion"
