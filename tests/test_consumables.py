"""Consumables, and the policy that decides when a PC drinks one.

The 1d4 is patched in every case, so what's under test is what the potion does
and when the policy wants it - never what the die rolled.
"""

from unittest.mock import patch

from characters.player_character import PlayerCharacter
from combat.policy import _should_clear_stress, _should_heal, _use_free_actions
from combat.state import FightState
from dice.damage import DamageRollResult, DiceGroup
from items.consumables import minor_healing_potion, minor_stamina_potion


def _make_character(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=2,
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 0, "strength": 2, "finesse": 0,
            "instinct": 1, "presence": 1, "knowledge": 0,
        },
        evasion=9,
        proficiency=2,
        major_threshold=6,
        severe_threshold=12,
        hp_max=7,
        stress_max=6,
        hope_max=6,
        armor_max=0,
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


def _rolled(amount: int) -> DamageRollResult:
    return DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=4)],
        die_results=[[amount]],
        modifier=0,
    )


def _potions(name: str, quantity: int = 1) -> list[dict]:
    return [{"name": name, "quantity": quantity}]


# --- The potions themselves --------------------------------------------------


def test_a_stamina_potion_clears_the_stress_it_rolled():
    pc = _make_character(stress_max=6)
    pc.mark_stress(5)

    with patch("items.consumables.roll_damage", return_value=_rolled(3)):
        cleared = minor_stamina_potion(pc)

    assert cleared == 3
    assert pc.stress_marked == 2


def test_a_stamina_potion_cannot_clear_past_none_marked():
    pc = _make_character()
    pc.mark_stress(1)

    with patch("items.consumables.roll_damage", return_value=_rolled(4)):
        minor_stamina_potion(pc)

    assert pc.stress_marked == 0


def test_a_healing_potion_still_clears_hp_rather_than_stress():
    pc = _make_character()
    pc.mark_hp(3)
    pc.mark_stress(3)

    with patch("items.consumables.roll_damage", return_value=_rolled(2)):
        minor_healing_potion(pc)

    assert pc.hp_marked == 1
    assert pc.stress_marked == 3


# --- When the policy wants one -----------------------------------------------


def test_stress_is_cleared_only_once_the_slots_have_nearly_run_out():
    pc = _make_character(stress_max=6, consumables=_potions("Minor Stamina Potion"))

    assert _should_clear_stress(pc) is False

    pc.mark_stress(5)  # one slot left

    assert _should_clear_stress(pc) is True


def test_a_pc_with_no_stamina_potion_never_wants_one():
    pc = _make_character(stress_max=6, consumables=[])
    pc.mark_stress(6)

    assert _should_clear_stress(pc) is False


def test_an_empty_bottle_is_not_a_potion():
    pc = _make_character(
        stress_max=6, consumables=_potions("Minor Stamina Potion", quantity=0)
    )
    pc.mark_stress(6)

    assert _should_clear_stress(pc) is False


def test_the_sheet_can_capitalise_it_however_it_likes():
    pc = _make_character(stress_max=6, consumables=_potions("minor stamina potion"))
    pc.mark_stress(6)

    assert _should_clear_stress(pc) is True


# --- Through the turn policy -------------------------------------------------


def test_a_stressed_pc_drinks_on_their_spotlight():
    pc = _make_character(stress_max=6, consumables=_potions("Minor Stamina Potion"))
    pc.mark_stress(6)
    state = FightState(encounter_name="Test", party=[pc], adversaries=[], logging=True)

    with patch("items.consumables.roll_damage", return_value=_rolled(2)):
        _use_free_actions(pc, state, roll_to_follow=True)

    assert pc.stress_marked == 4
    assert pc.consumables[0]["quantity"] == 0
    assert any("Minor Stamina Potion" in line for line in state.log)


def test_both_potions_can_be_drunk_in_one_spotlight():
    """Consumables sit outside the spotlight budget, so neither blocks the other."""
    pc = _make_character(
        hp_max=7,
        stress_max=6,
        consumables=_potions("Minor Healing Potion") + _potions("Minor Stamina Potion"),
    )
    pc.mark_hp(6)  # one unmarked HP left
    pc.mark_stress(6)
    state = FightState(encounter_name="Test", party=[pc], adversaries=[])

    with patch("items.consumables.roll_damage", return_value=_rolled(2)):
        _use_free_actions(pc, state, roll_to_follow=True)

    assert pc.hp_marked == 4
    assert pc.stress_marked == 4


def test_a_healthy_pc_drinks_nothing():
    pc = _make_character(
        consumables=_potions("Minor Healing Potion") + _potions("Minor Stamina Potion")
    )
    state = FightState(encounter_name="Test", party=[pc], adversaries=[])

    _use_free_actions(pc, state, roll_to_follow=True)

    assert all(entry["quantity"] == 1 for entry in pc.consumables)
    assert _should_heal(pc) is False
