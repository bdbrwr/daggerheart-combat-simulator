"""Tests for the hook kinds, the spotlight budget, and the area-effect rule.

There are no turns here to test - only the spotlight, and the one roll that can
pass it. So these check the shape of a spotlight: consumables outside the
budget, a capped number of no-roll abilities, and exactly one roll, with riders
and damage responses free of the count.

The `action` and `free` hooks are exercised against throwaway content declared
here, so these don't break every time a real card is written. The `damage_bonus`
and `on_hit` hooks are exercised against the real Body Basher and Whirlwind.
"""

import random

import pytest

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.policy import FREE_BUDGET_ALONE, FREE_BUDGET_BEFORE_A_ROLL, take_pc_turn
from combat.state import FightState
from content import action, free, take_action, use_free_abilities
from content.aoe import MANY_ADVERSARIES, Range, chance_within, targets_reached
from dice.damage import DiceGroup

FIRED: list[str] = []


def _make_character(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=2,
        character_class="Guardian",
        subclass="Stalwart",
        ancestry="Human",
        community="Orderborne",
        traits={"agility": 1, "strength": 3, "finesse": -1, "instinct": 1, "presence": 1, "knowledge": 0},
        evasion=8,
        proficiency=2,
        major_threshold=11,
        severe_threshold=22,
        hp_max=7,
        stress_max=7,
        hope_max=6,
        hope_marked=6,
        armor_max=4,
        primary_weapon="Greatsword",
        secondary_weapon=None,
        armor_item="Irontree Breastplate Armor",
        domain_cards_loadout=[],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
    )
    defaults.update(overrides)
    return PlayerCharacter(**defaults)


def _make_adversary(**overrides) -> Adversary:
    defaults = dict(
        name="Dummy",
        tier=1,
        difficulty=0,  # every attack lands
        major_threshold=100,
        severe_threshold=200,
        hp_max=500,
        stress_max=3,
        attack_modifier=0,
        damage_dice=[DiceGroup(count=1, sides=4)],
        damage_modifier=0,
    )
    defaults.update(overrides)
    return Adversary(**defaults)


def _state(party, adversaries) -> FightState:
    return FightState(encounter_name="Test", party=party, adversaries=adversaries)


@pytest.fixture(autouse=True)
def _clear_fired():
    FIRED.clear()


# --- Throwaway content, to exercise the hooks without real cards -------------


@free("Test Free A")
def _free_a(holder, fight) -> bool:
    FIRED.append("A")
    return True


@free("Test Free B")
def _free_b(holder, fight) -> bool:
    FIRED.append("B")
    return True


@free("Test Free Declines")
def _free_declines(holder, fight) -> bool:
    FIRED.append("declined")
    return False


@action("Test Action")
def _test_action(holder, target, fight):
    FIRED.append("action")
    return "an-attack-result"


@action("Test Action Two")
def _test_action_two(holder, target, fight):
    FIRED.append("action-two")
    return "the-other-result"


@action("Test Action Declines")
def _test_action_declines(holder, target, fight):
    FIRED.append("action-declined")
    return None


# --- The action hook ---------------------------------------------------------


def test_the_first_action_that_wants_the_roll_gets_it():
    pc = _make_character(domain_cards_loadout=["Test Action"])

    assert take_action(pc, _make_adversary(), _state([pc], [])) == "an-attack-result"


def test_content_that_declines_falls_through():
    pc = _make_character(domain_cards_loadout=["Test Action Declines"])

    assert take_action(pc, _make_adversary(), _state([pc], [])) is None
    assert FIRED == ["action-declined"]


def test_loadout_order_does_not_decide_between_two_willing_actions():
    """A loadout is unordered data, so it must never pick the ability.

    Both orderings are asked the same question many times; a first-wins
    implementation would answer one of them identically every single time.
    """
    random.seed(1)
    written_one_way = {
        take_action(
            _make_character(domain_cards_loadout=["Test Action", "Test Action Two"]),
            _make_adversary(),
            _state([], []),
        )
        for _ in range(40)
    }
    written_the_other = {
        take_action(
            _make_character(domain_cards_loadout=["Test Action Two", "Test Action"]),
            _make_adversary(),
            _state([], []),
        )
        for _ in range(40)
    }

    assert written_one_way == {"an-attack-result", "the-other-result"}
    assert written_the_other == written_one_way


def test_an_ability_that_declines_still_lets_another_act():
    pc = _make_character(domain_cards_loadout=["Test Action Declines", "Test Action"])

    assert take_action(pc, _make_adversary(), _state([pc], [])) == "an-attack-result"


def test_a_loadout_with_no_actions_wants_the_weapon():
    pc = _make_character(domain_cards_loadout=["Get Back Up"])

    assert take_action(pc, _make_adversary(), _state([pc], [])) is None


# --- The free hook and the budget --------------------------------------------


def test_free_abilities_stop_at_the_limit():
    pc = _make_character(domain_cards_loadout=["Test Free A", "Test Free B"])

    used = use_free_abilities(pc, _state([pc], []), limit=1)

    assert len(used) == 1
    assert len(FIRED) == 1


def test_which_free_ability_fires_is_not_decided_by_loadout_order():
    random.seed(2)
    pc = _make_character(domain_cards_loadout=["Test Free A", "Test Free B"])

    fired = {
        use_free_abilities(pc, _state([pc], []), limit=1)[0] for _ in range(40)
    }

    assert fired == {"Test Free A", "Test Free B"}


def test_an_ability_that_declines_does_not_spend_from_the_budget():
    pc = _make_character(domain_cards_loadout=["Test Free Declines", "Test Free A"])

    used = use_free_abilities(pc, _state([pc], []), limit=1)

    assert used == ["Test Free A"]  # the decliner never counted


def test_a_limit_of_zero_fires_nothing():
    pc = _make_character(domain_cards_loadout=["Test Free A"])

    assert use_free_abilities(pc, _state([pc], []), limit=0) == []
    assert FIRED == []


def test_the_budget_is_smaller_when_a_roll_will_follow():
    """Two no-roll actions, or one plus the roll that ends the spotlight."""
    assert FREE_BUDGET_BEFORE_A_ROLL == 1
    assert FREE_BUDGET_ALONE == 2


def test_a_spotlight_with_a_roll_allows_one_free_ability():
    random.seed(3)
    pc = _make_character(domain_cards_loadout=["Test Free A", "Test Free B"])
    state = _state([pc], [_make_adversary()])

    take_pc_turn(pc, state)

    assert len(FIRED) == 1


def test_a_spotlight_with_nothing_to_attack_allows_two():
    """No target means no roll, so the wider half of the budget applies."""
    random.seed(3)
    pc = _make_character(domain_cards_loadout=["Test Free A", "Test Free B"])

    assert take_pc_turn(pc, _state([pc], [])) is None
    assert sorted(FIRED) == ["A", "B"]


# --- Riders ------------------------------------------------------------------


def test_body_basher_adds_strength_to_the_damage_roll():
    random.seed(3)
    plain = _make_character()
    without = take_pc_turn(plain, _state([plain], [_make_adversary()]))

    random.seed(3)
    basher = _make_character(domain_cards_loadout=["Body Basher"])
    with_bonus = take_pc_turn(basher, _state([basher], [_make_adversary()]))

    assert with_bonus.damage_roll.total - without.damage_roll.total == 3


def test_whirlwind_reaches_nobody_in_a_small_fight():
    """Very Close catches n // 3 in total, and the original target is one."""
    random.seed(3)
    pc = _make_character(domain_cards_loadout=["Whirlwind"], hope_marked=6)
    others = [_make_adversary(name=f"Other {i}") for i in range(3)]
    state = _state([pc], [_make_adversary(name="Focus"), *others])

    take_pc_turn(pc, state)

    assert all(other.hp_marked == 0 for other in others)
    assert pc.hope_marked == 6  # no Hope spent on nobody


def test_whirlwind_splashes_once_the_fight_is_crowded():
    random.seed(3)
    pc = _make_character(domain_cards_loadout=["Whirlwind"], hope_marked=6)
    crowd = [_make_adversary(name=f"Other {i}") for i in range(7)]
    state = _state([pc], crowd)

    take_pc_turn(pc, state)

    assert sum(1 for adversary in crowd if adversary.hp_marked) > 1
    assert pc.hope_marked == 5


def test_whirlwind_costs_nothing_without_the_hope_for_it():
    random.seed(3)
    pc = _make_character(domain_cards_loadout=["Whirlwind"], hope_marked=0)
    crowd = [_make_adversary(name=f"Other {i}") for i in range(7)]

    take_pc_turn(pc, _state([pc], crowd))

    assert sum(1 for adversary in crowd if adversary.hp_marked) == 1


# --- The area rule -----------------------------------------------------------


def test_far_reaches_everyone():
    assert targets_reached(Range.FAR, 5) == 5


def test_close_never_reaches_everyone():
    for count in range(2, 12):
        assert targets_reached(Range.CLOSE, count) < count


def test_close_is_three_quarters():
    assert targets_reached(Range.CLOSE, 8) == 6
    assert targets_reached(Range.CLOSE, 4) == 3


def test_very_close_is_a_third():
    assert targets_reached(Range.VERY_CLOSE, 9) == 3
    assert targets_reached(Range.VERY_CLOSE, 4) == 1


def test_melee_reaches_two_until_the_fight_is_crowded():
    assert targets_reached(Range.MELEE, 4) == 2
    assert targets_reached(Range.MELEE, MANY_ADVERSARIES) == 3


# --- The same bands as odds --------------------------------------------------
#
# `chance_within` answers a different question from `targets_reached`: not "how
# many does this band sweep?" but "is this one named person inside it?". Content
# whose condition is a specific ally being in range needs the second, and with no
# positions tracked the band's share of the field stands in for it.


def test_far_always_reaches_a_named_combatant():
    assert chance_within(Range.FAR, 4) == 1.0


def test_close_is_three_quarters_as_odds_too():
    assert chance_within(Range.CLOSE, 4) == 0.75


def test_very_close_is_a_third_as_odds_too():
    assert chance_within(Range.VERY_CLOSE, 9) == pytest.approx(1 / 3)


def test_melee_odds_come_from_the_field_size():
    """Melee's rule is a flat count, so it has no share to read off."""
    assert chance_within(Range.MELEE, 4) == 0.5
    assert chance_within(Range.MELEE, MANY_ADVERSARIES) == pytest.approx(0.5)


def test_a_proportional_band_is_not_certain_just_because_the_field_is_small():
    """The bug this exists to prevent.

    `targets_reached` floors at 1 so an area effect never catches nobody - right
    as a count, badly wrong as a probability. Read off it directly, a single
    adversary made Close and Very Close certainties.

    Melee is excluded because it genuinely saturates: its rule is "2 combatants",
    so with only one on the field reaching them is certain, and that is the rule
    rather than a rounding artefact.
    """
    for band in (Range.CLOSE, Range.VERY_CLOSE):
        for count in range(1, 12):
            assert chance_within(band, count) < 1.0


def test_an_empty_field_is_not_certainty_either():
    for band in Range:
        assert chance_within(band, 0) == 0.0


def test_the_odds_are_a_probability_at_every_band():
    for band in Range:
        for count in range(1, 12):
            assert 0.0 <= chance_within(band, count) <= 1.0


def test_an_area_effect_always_reaches_at_least_one():
    for band in Range:
        assert targets_reached(band, 1) == 1
        assert targets_reached(band, 2) >= 1


def test_nobody_to_hit_reaches_nobody():
    assert targets_reached(Range.FAR, 0) == 0
