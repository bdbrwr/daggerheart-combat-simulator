"""Tests for community features - the first content that isn't a domain card.

Orderborne matters twice over: it's the proof that dispatch reaches everything a
sheet names rather than only the loadout, and it's the first content gated on
rest state.
"""

from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.state import FightState
from content import apply_on_roll, assess, hope_die_for, total_roll_bonus
from content.registry import DEFAULT_HOPE_DIE
from dice.duality import DualityOutcome
from features.communities import ORDERBORNE_HOPE_DIE


def _make_character(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Artorias",
        level=2,
        character_class="Guardian",
        subclass="Stalwart",
        ancestry="Human",
        community="Orderborne",
        traits={"agility": 1, "strength": 3, "finesse": -1, "instinct": 1, "presence": 1, "knowledge": 0},
        evasion=8,
        proficiency=2,
        spellcast_trait="",
        major_threshold=11,
        severe_threshold=22,
        hp_max=7,
        stress_max=7,
        hope_max=6,
        hope_marked=2,
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


def _state(pc, **overrides) -> FightState:
    return FightState(encounter_name="Test", party=[pc], adversaries=[], **overrides)


def test_a_community_is_found_without_being_in_the_loadout():
    """Dispatch scans everything a sheet names, not just domain cards."""
    assert assess("Orderborne").status.value == "modelled"


def test_the_first_roll_after_a_rest_swaps_in_a_d20():
    pc = _make_character()

    assert hope_die_for(pc, _state(pc, rest=Rest.LONG)) == ORDERBORNE_HOPE_DIE


def test_only_the_first_roll_gets_it():
    pc = _make_character()
    state = _state(pc, rest=Rest.LONG)

    assert hope_die_for(pc, state) == ORDERBORNE_HOPE_DIE
    assert hope_die_for(pc, state) == DEFAULT_HOPE_DIE


def test_any_rest_is_enough():
    """Dedicated is once per rest, so a short rest refreshes it just as well."""
    pc = _make_character()

    assert hope_die_for(pc, _state(pc, rest=Rest.SHORT)) == ORDERBORNE_HOPE_DIE


def test_a_party_that_never_rested_does_not_have_it():
    pc = _make_character()

    assert hope_die_for(pc, _state(pc, rest=Rest.NONE)) == DEFAULT_HOPE_DIE


def test_a_pc_from_another_community_rolls_a_plain_d12():
    pc = _make_character(community="Wanderborne")

    assert hope_die_for(pc, _state(pc, rest=Rest.LONG)) == DEFAULT_HOPE_DIE


def test_the_communities_nobody_looked_up_stay_unimplemented():
    """Dismissing content needs the feature text behind it, not a guess.

    Seaborne is the cautionary case: it reads like flavour and turns out to
    boost attack rolls, so it's implemented rather than dismissed.
    """
    assert assess("Seaborne").status.value == "modelled"


def test_the_communities_ruled_out_are_recorded_as_such():
    """Dismissed by the user's ruling, not left silently absent."""
    for community in ("Wildborne", "Wanderborne"):
        assert assess(community).status.value == "no combat effect"
        assert assess(community).reason


# --- Know the Tide -----------------------------------------------------------


def _seaborne(**overrides) -> PlayerCharacter:
    return _make_character(name="Aeloria", community="Seaborne", **overrides)


class _FearRoll:
    """Only the outcome matters to Know the Tide, so that's all this carries."""

    outcome = DualityOutcome.FEAR


class _HopeRoll:
    outcome = DualityOutcome.HOPE


def test_a_roll_with_fear_places_a_token():
    pc = _seaborne(level=2)
    state = _state(pc)

    apply_on_roll(pc, _FearRoll(), state)

    assert state.token_count(pc, "Know the Tide") == 1


def test_a_roll_with_hope_places_nothing():
    pc = _seaborne(level=2)
    state = _state(pc)

    apply_on_roll(pc, _HopeRoll(), state)

    assert state.token_count(pc, "Know the Tide") == 0


def test_tokens_are_capped_at_the_pcs_level():
    pc = _seaborne(level=2)
    state = _state(pc)

    for _ in range(5):
        apply_on_roll(pc, _FearRoll(), state)

    assert state.token_count(pc, "Know the Tide") == 2


def test_tokens_are_spent_for_one_each():
    pc = _seaborne(level=3)
    state = _state(pc)
    apply_on_roll(pc, _FearRoll(), state)
    apply_on_roll(pc, _FearRoll(), state)

    assert total_roll_bonus(pc, None, state) == 2
    assert state.token_count(pc, "Know the Tide") == 0


def test_holding_nothing_adds_nothing():
    pc = _seaborne()

    assert total_roll_bonus(pc, None, _state(pc)) == 0


def test_another_communitys_pc_never_gains_tokens():
    pc = _make_character(community="Orderborne")
    state = _state(pc)

    apply_on_roll(pc, _FearRoll(), state)

    assert state.token_count(pc, "Know the Tide") == 0
