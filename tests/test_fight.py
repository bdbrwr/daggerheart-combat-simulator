"""Deterministic tests for the spotlight loop.

Nothing here averages anything. The fights that are run end up decided by
construction - an adversary that can't be hit, a party that can't be missed -
so the assertions hold on every run rather than most of them. Whether the
crit rate or the win rate looks right is validation/'s job.
"""

from pathlib import Path

import pytest

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.common import FightOutcome, Side
from combat.fight import run_fight
from combat.policy import choose_adversary_target, choose_pc_target
from combat.report import FightResult
from combat.state import MAX_FEAR, FightState
from dice.damage import DiceGroup
from encounters.encounter import Encounter, Group

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


def _make_adversary(**overrides) -> Adversary:
    defaults = dict(
        name="Test Adversary",
        tier=1,
        difficulty=12,
        major_threshold=8,
        severe_threshold=14,
        hp_max=5,
        stress_max=3,
        attack_modifier=1,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=1,
    )
    defaults.update(overrides)
    return Adversary(**defaults)


def _make_state(party=None, adversaries=None, **overrides) -> FightState:
    return FightState(
        encounter_name="Test Fight",
        party=party if party is not None else [_make_character()],
        adversaries=adversaries if adversaries is not None else [_make_adversary()],
        **overrides,
    )


# --- Fear pool ---------------------------------------------------------------


def test_fear_stops_at_the_cap():
    state = _make_state(fear=MAX_FEAR - 1)
    assert state.gain_fear(1) == 1
    assert state.gain_fear(1) == 0
    assert state.fear == MAX_FEAR


def test_fear_can_only_be_spent_if_it_is_there():
    state = _make_state(fear=1)
    assert state.spend_fear(1) is True
    assert state.spend_fear(1) is False
    assert state.fear == 0
    assert state.fear_spent == 1


def test_activation_cap_is_party_size_plus_one():
    state = _make_state(party=[_make_character(), _make_character()])
    assert state.max_activations_per_gm_turn == 3


# --- Targeting ---------------------------------------------------------------


def test_adversary_hits_back_at_whoever_hit_it():
    attacker, bystander = _make_character(name="Attacker"), _make_character(name="Bystander")
    adversary = _make_adversary()
    state = _make_state(party=[bystander, attacker], adversaries=[adversary])
    state.last_attacker_of[id(adversary)] = attacker

    assert choose_adversary_target(adversary, state) is attacker


def test_adversary_falls_back_to_the_last_pc_to_attack_anything():
    recent, other = _make_character(name="Recent"), _make_character(name="Other")
    adversary = _make_adversary()
    state = _make_state(party=[other, recent], adversaries=[adversary])
    state.last_pc_to_attack = recent

    assert choose_adversary_target(adversary, state) is recent


def test_an_unconscious_pc_is_never_targeted():
    downed, standing = _make_character(name="Downed"), _make_character(name="Standing")
    downed.unconscious = True
    adversary = _make_adversary()
    state = _make_state(party=[downed, standing], adversaries=[adversary])
    state.last_attacker_of[id(adversary)] = downed
    state.last_pc_to_attack = downed

    assert choose_adversary_target(adversary, state) is standing


def test_no_target_when_the_whole_party_is_down():
    downed = _make_character()
    downed.unconscious = True
    state = _make_state(party=[downed])

    assert choose_adversary_target(state.adversaries[0], state) is None


def test_the_party_focuses_the_most_wounded_adversary():
    fresh, wounded = _make_adversary(name="Fresh"), _make_adversary(name="Wounded")
    wounded.mark_hp(3)
    state = _make_state(adversaries=[fresh, wounded])

    assert choose_pc_target(state) is wounded


def test_defeated_adversaries_are_not_targeted():
    defeated, alive = _make_adversary(name="Defeated"), _make_adversary(name="Alive")
    defeated.mark_hp(defeated.hp_max)
    state = _make_state(adversaries=[defeated, alive])

    assert choose_pc_target(state) is alive


# --- Fight outcomes ----------------------------------------------------------


def _one_on_one(adversary_overrides: dict | None = None, **encounter_overrides) -> Encounter:
    return Encounter(
        name="Test Fight",
        party=[EXAMPLE_CHARACTER_PATH],
        groups=[Group("Jagged Knife Bandit", count=1, **(adversary_overrides or {}))],
        **encounter_overrides,
    )


# Rigging a fight takes a little care, because both crit rules cut through the
# obvious levers: a duality critical succeeds whatever the Difficulty, and a
# natural 20 hits whatever the Evasion. So a side is made harmless by taking
# away its damage, and unkillable by giving it more HP than the action cap
# could ever chew through - not by setting a number nobody can roll against.
HARMLESS = {"damage_dice": [], "damage_modifier": 0}
UNKILLABLE = {"hp_max": 1000}
FRAGILE = {"difficulty": 0, "hp_max": 1}


def test_party_wins_against_a_fragile_adversary():
    """Difficulty 0, 1 HP: the first PC swing lands and finishes it."""
    result = run_fight(_one_on_one({**FRAGILE, **HARMLESS}))

    assert result.outcome is FightOutcome.PARTY_VICTORY
    assert result.party_won is True
    assert result.surviving_adversaries == 0
    assert result.surviving_pcs == 1
    assert result.pc_actions == 1


def test_party_loses_to_an_adversary_that_never_misses_and_cannot_be_killed():
    result = run_fight(
        _one_on_one(
            {
                **UNKILLABLE,
                "difficulty": 100,
                "attack_modifier": 100,
                "damage_dice": [DiceGroup(count=1, sides=1)],
                "damage_modifier": 100,
            }
        )
    )

    assert result.outcome is FightOutcome.PARTY_DEFEAT
    assert result.surviving_pcs == 0
    assert result.unconscious_pcs == 1


def test_a_fight_neither_side_can_finish_is_reported_not_hung():
    """Neither side can land a finishing blow, so the loop gives up and says so."""
    result = run_fight(_one_on_one({**UNKILLABLE, **HARMLESS, "difficulty": 100}))

    assert result.outcome is FightOutcome.UNRESOLVED
    assert result.surviving_pcs == 1
    assert result.surviving_adversaries == 1


def test_a_lone_adversary_acts_once_per_gm_turn():
    """With nothing else to spotlight there's nothing for Fear to buy."""
    result = run_fight(_one_on_one({**UNKILLABLE, **HARMLESS, "difficulty": 100}))

    assert result.adversary_activations == result.gm_turns
    # Every GM turn is handed over by a PC action, so it can't outnumber them.
    assert result.gm_turns <= result.pc_actions


def test_the_gm_buys_extra_activations_with_fear_up_to_the_cap():
    """Three adversaries, one PC: the GM can spotlight two per turn, not three."""
    encounter = Encounter(
        name="Outnumbered",
        party=[EXAMPLE_CHARACTER_PATH],
        groups=[
            Group("Jagged Knife Bandit", count=3, **{**UNKILLABLE, **HARMLESS, "difficulty": 100})
        ],
        starting_fear=5,
        starting_spotlight=Side.GM,
    )
    result = run_fight(encounter)

    assert result.fear_spent >= 1  # the opening turn bought a second activation
    assert result.adversary_activations <= 2 * result.gm_turns  # party size + 1


def test_the_gm_can_start_with_fear_and_the_spotlight():
    encounter = _one_on_one({**FRAGILE, **HARMLESS}, starting_fear=5, starting_spotlight=Side.GM)
    result = run_fight(encounter)

    # The GM opened, so an adversary acted before any PC did.
    assert result.gm_turns >= 1
    assert result.outcome is FightOutcome.PARTY_VICTORY


def test_the_same_seed_replays_the_same_fight():
    import random

    encounter = Encounter(
        name="Roadside", party=[EXAMPLE_CHARACTER_PATH], groups=[Group("Jagged Knife Bandit", count=2)]
    )

    random.seed(11)
    first = run_fight(encounter)
    random.seed(11)
    second = run_fight(encounter)

    assert first.outcome is second.outcome
    assert first.pc_actions == second.pc_actions
    assert first.adversary_activations == second.adversary_activations
    assert first.fear_gained == second.fear_gained


def test_a_fresh_fight_does_not_inherit_the_last_one():
    import random

    encounter = _one_on_one({**FRAGILE, **HARMLESS})

    random.seed(3)
    first = run_fight(encounter)
    random.seed(3)
    second = run_fight(encounter)

    assert first.party[0] is not second.party[0]
    assert first.adversaries[0] is not second.adversaries[0]
    assert first.pc_actions == second.pc_actions


def test_logging_is_off_unless_asked_for():
    encounter = _one_on_one({**FRAGILE, **HARMLESS})

    assert run_fight(encounter).log == []
    assert run_fight(encounter, logging=True).log != []


# --- Report ------------------------------------------------------------------


def _make_result(**overrides) -> FightResult:
    defaults = dict(
        encounter_name="Test Fight",
        outcome=FightOutcome.PARTY_VICTORY,
        party=[_make_character(), _make_character()],
        adversaries=[_make_adversary()],
        pc_actions=8,
        adversary_activations=6,
        gm_turns=4,
        fear_gained=5,
        fear_spent=2,
        fear_remaining=3,
        unconscious_pcs=0,
        scars_gained=0,
    )
    defaults.update(overrides)
    return FightResult(**defaults)


def test_round_metrics_are_per_party_member():
    result = _make_result(pc_actions=8, adversary_activations=6)

    assert result.party_size == 2
    assert result.pc_rounds == 4.0
    assert result.gm_rounds == 3.0


def test_round_metrics_survive_an_empty_party():
    """A party of nobody is a broken encounter, not a divide-by-zero."""
    result = _make_result(party=[])

    assert result.pc_rounds == 0.0
    assert result.gm_rounds == 0.0


def test_party_hp_unmarked_totals_the_party():
    hurt = _make_character(hp_max=7)
    hurt.mark_hp(4)
    result = _make_result(party=[hurt, _make_character(hp_max=7)])

    assert result.party_hp_unmarked == 10


# --- Item registry -----------------------------------------------------------


def test_gear_is_found_by_the_name_a_character_sheet_uses():
    from items.registry import find_consumable, find_weapon

    assert find_weapon("Broadsword").__name__ == "broadsword_attack"
    assert find_consumable("Minor Healing Potion").__name__ == "minor_healing_potion"


def test_an_unimplemented_item_fails_loudly_with_a_suggestion():
    from items.registry import find_weapon

    with pytest.raises(KeyError, match="Broadsword"):
        find_weapon("Broadswrod")
