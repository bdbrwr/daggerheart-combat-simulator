"""Tests for the two implemented domain cards.

Both are damage responses, which makes them easy to test honestly: damage of a
chosen size goes in, and the HP it marks comes out. No dice are involved in any
of this except the death move, which the cases here stay clear of unless
they're testing it.

The rules readings these pin down are the ones the card modules document as
choices rather than as SRD text - that Get Back Up triggers on the damage amount
and so stacks with an Armor Slot, and that I Am Your Shield swaps the target
before the attack is rolled. If either reading changes, these are the tests that
should fail.

Cards are tested through the dispatch functions the rest of the codebase calls,
plus one case through combat/policy.py to prove that call site is wired up.
"""

from characters.player_character import PlayerCharacter
from combat.policy import _shield
from combat.state import FightState
from content import find_guard, find_severity_response, find_shielder
from domain_cards.blade import get_back_up
from domain_cards.valor import i_am_your_shield

GET_BACK_UP = "Get Back Up"
I_AM_YOUR_SHIELD = "I Am Your Shield"


def _make_character(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=1,
        # Names nothing has implemented, on purpose. A class or subclass with
        # damage responses of its own (Stalwart's Iron Will marks a second Armor
        # Slot; Unstoppable softens every hit) would stack with the card these
        # tests are measuring, and the card's own arithmetic would stop being
        # what came out. Invented names keep each case about one card.
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
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
        armor_max=0,  # off unless a test is about armor
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


# --- Registry ----------------------------------------------------------------


def test_cards_are_discovered_without_being_registered_by_hand():
    """Writing the module and decorating the function is the whole of adding one."""
    assert find_severity_response(GET_BACK_UP) is get_back_up
    assert find_guard(I_AM_YOUR_SHIELD) is i_am_your_shield


def test_an_unimplemented_card_is_skipped_rather_than_an_error():
    """A loadout may name cards nobody has written yet."""
    assert find_severity_response("Rune Ward") is None
    assert find_guard("Whirlwind") is None


def test_a_pc_carrying_an_unimplemented_card_still_takes_damage_normally():
    character = _make_character(domain_cards_loadout=["Not Good Enough", "Whirlwind"])

    assert character.take_damage(12) == 3


# --- Get Back Up -------------------------------------------------------------


def test_get_back_up_turns_a_severe_hit_into_a_major_one():
    character = _make_character(domain_cards_loadout=[GET_BACK_UP])

    assert character.take_damage(12) == 2
    assert character.stress_marked == 1


def test_without_the_card_a_severe_hit_costs_the_full_three():
    character = _make_character(domain_cards_loadout=[])

    assert character.take_damage(12) == 3
    assert character.stress_marked == 0


def test_get_back_up_ignores_anything_short_of_severe():
    character = _make_character(domain_cards_loadout=[GET_BACK_UP])

    assert character.take_damage(6) == 2  # Major, not Severe
    assert character.stress_marked == 0


def test_get_back_up_stacks_with_an_armor_slot():
    """The chosen reading: the hit is Severe by its size, whatever armor did."""
    character = _make_character(domain_cards_loadout=[GET_BACK_UP], armor_max=3)

    assert character.take_damage(12) == 1  # 3, less one for armor, less one for the card
    assert character.armor_marked == 1
    assert character.stress_marked == 1


def test_get_back_up_cannot_fire_when_stress_is_full():
    """A move costing Stress is unavailable, not paid for in HP."""
    character = _make_character(domain_cards_loadout=[GET_BACK_UP], stress_max=2)
    character.mark_stress(2)

    assert character.take_damage(12) == 3
    assert character.hp_marked == 3


def test_get_back_up_refuses_a_cost_it_cannot_pay_even_when_it_wants_to():
    """Called directly: the policy wants the reduction, but Stress is full.

    Going through take_damage here would mark the last HP and roll a death
    move, which this isn't about.
    """
    character = _make_character(domain_cards_loadout=[GET_BACK_UP], stress_max=1, hp_max=3)
    character.mark_stress(1)

    assert get_back_up(character, 12, 3) == 3
    assert character.hp_marked == 0


def test_get_back_up_buys_nothing_when_the_hit_is_already_down_to_zero():
    """Called directly - armor alone can't reach 0 from Severe, so this guards a branch."""
    character = _make_character(domain_cards_loadout=[GET_BACK_UP])

    assert get_back_up(character, 12, 0) == 0
    assert character.stress_marked == 0


def test_get_back_up_keeps_its_last_stress_when_the_hit_is_survivable():
    """Marking the last Stress means Advantage on every roll against you."""
    character = _make_character(domain_cards_loadout=[GET_BACK_UP], stress_max=2, hp_max=7)
    character.mark_stress(1)

    assert character.take_damage(12) == 3
    assert character.stress_marked == 1
    assert character.is_vulnerable is False


def test_get_back_up_spends_its_last_stress_to_stay_conscious():
    """Going Vulnerable beats going down - the fight continues either way."""
    character = _make_character(domain_cards_loadout=[GET_BACK_UP], stress_max=2, hp_max=3)
    character.mark_stress(1)

    assert character.take_damage(12) == 2
    assert character.is_vulnerable is True
    assert character.is_conscious is True


# --- I Am Your Shield --------------------------------------------------------


def test_an_ally_steps_in_front_of_the_pc_who_is_closer_to_going_down():
    shielder = _make_character(name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD])
    hurt = _make_character(name="Ally", hp_max=7)
    hurt.mark_hp(5)  # 2 unmarked HP left

    interception = find_shielder(hurt, [shielder, hurt])

    assert interception is not None
    assert interception.shielder is shielder
    assert interception.card == I_AM_YOUR_SHIELD
    assert shielder.stress_marked == 1


def test_nobody_steps_in_for_a_pc_who_is_no_worse_off():
    shielder = _make_character(name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD])
    unhurt = _make_character(name="Ally")

    assert find_shielder(unhurt, [shielder, unhurt]) is None
    assert shielder.stress_marked == 0


def test_a_shielder_on_their_last_hp_does_not_step_in():
    """Moving the hit onto someone who also drops gains the party nothing."""
    shielder = _make_character(name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD], hp_max=7)
    shielder.mark_hp(6)
    hurt = _make_character(name="Ally", hp_max=7)
    hurt.mark_hp(6)

    assert find_shielder(hurt, [shielder, hurt]) is None


def test_a_shielder_with_no_stress_left_cannot_step_in():
    shielder = _make_character(
        name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD], stress_max=1
    )
    shielder.mark_stress(1)
    hurt = _make_character(name="Ally", hp_max=7)
    hurt.mark_hp(5)

    assert find_shielder(hurt, [shielder, hurt]) is None


def test_a_solo_pc_is_never_shielded_by_themselves():
    """The card needs an ally, so with a party of one it can never fire."""
    alone = _make_character(name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD], hp_max=7)
    alone.mark_hp(6)

    assert find_shielder(alone, [alone]) is None
    assert alone.stress_marked == 0


def test_the_card_reports_whether_it_stepped_in():
    """The card's own contract, independent of how the registry calls it."""
    shielder = _make_character(hp_max=7)
    hurt = _make_character(hp_max=7)
    hurt.mark_hp(5)

    assert i_am_your_shield(shielder, hurt) is True
    assert i_am_your_shield(shielder, shielder) is False


# --- The call site -----------------------------------------------------------


def test_the_turn_policy_moves_the_attack_onto_the_shielder():
    """combat/policy.py knows no card by name; it asks and takes the answer."""
    shielder = _make_character(name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD])
    hurt = _make_character(name="Ally", hp_max=7)
    hurt.mark_hp(5)
    state = FightState(encounter_name="Test", party=[shielder, hurt], adversaries=[])

    assert _shield(hurt, state) is shielder


def test_an_unconscious_ally_never_steps_in():
    """The policy filters to conscious PCs before the cards are asked at all."""
    shielder = _make_character(name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD])
    shielder.unconscious = True
    hurt = _make_character(name="Ally", hp_max=7)
    hurt.mark_hp(5)
    state = FightState(encounter_name="Test", party=[shielder, hurt], adversaries=[])

    assert _shield(hurt, state) is hurt
