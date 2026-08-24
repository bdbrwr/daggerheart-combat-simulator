"""Tests for the Bone domain cards.

Two of the five run. Ferocity is the first content that changes a PC's Evasion
mid-fight, so several of these are about the number an adversary actually rolls
against rather than about the card in isolation - which is where a bonus that
only exists between two moments has to be checked.

Strategic Approach is a token pool with a trigger keyed per adversary, so its
cases are about which attacks get the die and which don't.
"""

import random

import pytest

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.results import AttackResult
from combat.state import FightState
from content import Status, assess, total_evasion_bonus
from dice.damage import DamageRollResult, DiceGroup
from domain_cards.bone import (
    FEROCITY_BONUS,
    STRATEGIC_OPENED,
    STRATEGIC_TOKENS,
    ferocity,
    ferocity_evades,
    strategic_approach,
)

FEROCITY = "Ferocity"
STRATEGIC_APPROACH = "Strategic Approach"


def _make_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Luma",
        level=2,
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 1,
            "strength": 0,
            "finesse": 2,
            "instinct": 1,
            "presence": 0,
            "knowledge": 2,
        },
        evasion=11,
        proficiency=2,
        major_threshold=9,
        severe_threshold=18,
        hp_max=7,
        stress_max=6,
        hope_max=6,
        hope_marked=6,
        armor_max=0,
        primary_weapon="Shortbow",
        secondary_weapon=None,
        armor_item="Gambeson Armor",
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
        difficulty=0,
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


def _state(party, adversaries, **overrides) -> FightState:
    return FightState(
        encounter_name="Test", party=party, adversaries=adversaries, **overrides
    )


def _hit(hp_marked: int) -> AttackResult:
    """A landed attack that cost the target `hp_marked` HP."""
    return AttackResult(
        attack_roll=None,
        damage_roll=DamageRollResult(
            dice_groups=[DiceGroup(count=1, sides=6)],
            die_results=[[5]],
            modifier=0,
        ),
        hp_marked=hp_marked,
    )


# --- Ferocity ----------------------------------------------------------------


def test_ferocity_buys_evasion_equal_to_the_hp_the_hit_marked():
    pc = _make_pc(domain_cards_loadout=[FEROCITY])
    adversary = _make_adversary()
    state = _state([pc], [adversary])

    ferocity(pc, adversary, _hit(3), state)

    assert pc.hope_marked == 4
    assert state.token_count(pc, FEROCITY_BONUS) == 3


def test_a_hit_that_marked_nothing_buys_nothing():
    pc = _make_pc(domain_cards_loadout=[FEROCITY])
    adversary = _make_adversary()
    state = _state([pc], [adversary])

    ferocity(pc, adversary, _hit(0), state)

    assert pc.hope_marked == 6
    assert state.token_count(pc, FEROCITY_BONUS) == 0


def test_ferocity_needs_two_hope():
    pc = _make_pc(domain_cards_loadout=[FEROCITY], hope_marked=1)
    adversary = _make_adversary()
    state = _state([pc], [adversary])

    ferocity(pc, adversary, _hit(2), state)

    assert pc.hope_marked == 1
    assert state.token_count(pc, FEROCITY_BONUS) == 0


def test_the_bonus_reaches_the_number_an_adversary_rolls_against():
    pc = _make_pc(domain_cards_loadout=[FEROCITY])
    adversary = _make_adversary()
    state = _state([pc], [adversary])
    state.set_token(pc, FEROCITY_BONUS, 2)

    assert total_evasion_bonus(pc, adversary, state) == 2


def test_the_bonus_is_gone_after_the_attack_it_was_bought_for():
    """"Until after the next attack made against you" - one attack, not a fight."""
    pc = _make_pc(domain_cards_loadout=[FEROCITY])
    adversary = _make_adversary()
    state = _state([pc], [adversary])
    state.set_token(pc, FEROCITY_BONUS, 2)

    first = ferocity_evades(pc, adversary, state)
    second = ferocity_evades(pc, adversary, state)

    assert (first, second) == (2, 0)


def test_a_pc_without_the_card_has_a_plain_evasion():
    pc = _make_pc(domain_cards_loadout=[])
    adversary = _make_adversary()
    state = _state([pc], [adversary])

    assert total_evasion_bonus(pc, adversary, state) == 0


def test_the_bonus_is_asked_for_once_per_attack_not_once_per_roll():
    """An adversary's attack reads Evasion outside its reroll closure.

    Rolled rather than constructed, because what this is checking is that
    `Adversary.attack` consults the hook exactly once - a second consultation
    would clear the token mid-attack and quietly halve the card's value.
    """
    random.seed(5)
    pc = _make_pc(domain_cards_loadout=[FEROCITY])
    adversary = _make_adversary()
    state = _state([pc], [adversary])
    state.set_token(pc, FEROCITY_BONUS, 3)

    adversary.attack(pc, fight=state)

    assert state.token_count(pc, FEROCITY_BONUS) == 0


# --- Strategic Approach ------------------------------------------------------


def test_the_opening_blow_on_an_adversary_gets_a_d8():
    pc = _make_pc(domain_cards_loadout=[STRATEGIC_APPROACH])
    adversary = _make_adversary()
    state = _state([pc], [adversary], rest=Rest.LONG)

    dice = strategic_approach(pc, adversary, None, state)

    assert [(group.count, group.sides) for group in dice] == [(1, 8)]
    assert dice[0].discardable is False


def test_the_second_blow_on_the_same_adversary_gets_nothing():
    pc = _make_pc(domain_cards_loadout=[STRATEGIC_APPROACH])
    adversary = _make_adversary()
    state = _state([pc], [adversary], rest=Rest.LONG)

    strategic_approach(pc, adversary, None, state)

    assert strategic_approach(pc, adversary, None, state) == []


def test_a_fresh_adversary_gets_its_own_opening_blow():
    """The trigger is per adversary, not per fight."""
    pc = _make_pc(domain_cards_loadout=[STRATEGIC_APPROACH])
    first, second = _make_adversary(name="A"), _make_adversary(name="B")
    state = _state([pc], [first, second], rest=Rest.LONG)

    strategic_approach(pc, first, None, state)

    assert strategic_approach(pc, second, None, state) != []


def test_the_card_holds_tokens_equal_to_knowledge():
    pc = _make_pc(domain_cards_loadout=[STRATEGIC_APPROACH])  # knowledge 2
    mob = [_make_adversary(name=f"A{n}") for n in range(4)]
    state = _state([pc], mob, rest=Rest.LONG)

    spent = [strategic_approach(pc, adversary, None, state) for adversary in mob]

    assert [bool(dice) for dice in spent] == [True, True, False, False]
    assert state.token_count(pc, STRATEGIC_TOKENS) == 0


def test_a_knowledge_of_zero_still_places_one_token():
    pc = _make_pc(
        domain_cards_loadout=[STRATEGIC_APPROACH],
        traits={
            "agility": 0,
            "strength": 0,
            "finesse": 0,
            "instinct": 0,
            "presence": 0,
            "knowledge": 0,
        },
    )
    adversary = _make_adversary()
    state = _state([pc], [adversary], rest=Rest.LONG)

    assert strategic_approach(pc, adversary, None, state) != []


def test_a_party_that_did_not_long_rest_walks_in_with_an_empty_card():
    pc = _make_pc(domain_cards_loadout=[STRATEGIC_APPROACH])
    adversary = _make_adversary()
    state = _state([pc], [adversary], rest=Rest.NONE)

    assert strategic_approach(pc, adversary, None, state) == []


def test_a_short_rest_does_not_place_tokens_either():
    """"After a long rest" - the card says which rest, so a short one won't do."""
    pc = _make_pc(domain_cards_loadout=[STRATEGIC_APPROACH])
    adversary = _make_adversary()
    state = _state([pc], [adversary], rest=Rest.SHORT)

    assert strategic_approach(pc, adversary, None, state) == []


def test_opening_on_one_adversary_does_not_mark_another_as_opened():
    pc = _make_pc(domain_cards_loadout=[STRATEGIC_APPROACH])
    first, second = _make_adversary(name="A"), _make_adversary(name="B")
    state = _state([pc], [first, second], rest=Rest.LONG)

    strategic_approach(pc, first, None, state)

    assert state.token_count(pc, f"{STRATEGIC_OPENED}:{id(second)}") == 0


# --- Assessed and dismissed --------------------------------------------------


def test_untouchable_is_already_in_the_sheets_evasion():
    assert assess("Untouchable").status is Status.NO_COMBAT_EFFECT


@pytest.mark.parametrize("card", ["Deft Maneuvers", "I See It Coming"])
def test_the_two_measured_dismissals_say_how_much_they_are_worth(card):
    """An insignificant ruling's whole claim is the size, so it has to state one."""
    assessment = assess(card)

    assert assessment.status is Status.INSIGNIFICANT_COMBAT_EFFECT
    assert assessment.reason
