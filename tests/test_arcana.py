"""Tests for the Arcana domain cards.

Three of the five run, and each reaches the fight by a different route: Rune Ward
is a damage reduction asked of the whole party, Unleash Chaos is an action with a
token pool, and Cinder Grasp leaves a condition behind that goes on costing the
target after the spell has resolved.

The dice are pinned wherever a case is about a decision rather than a roll -
`randint` for the Ward Die, a Difficulty of 0 for a spell that has to land.
"""

import random
from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.state import FightState
from content import assess
from content.conditions import ON_A_GM_TURN, ON_FIRE, WHEN_THEY_ACT
from dice.damage import DiceGroup
from domain_cards.arcana import (
    CHAOS_PRIMED,
    CHAOS_TOKENS,
    WARD_SPENT,
    cinder_grasp,
    rune_ward,
    unleash_chaos,
)

RUNE_WARD = "Rune Ward"
UNLEASH_CHAOS = "Unleash Chaos"
CINDER_GRASP = "Cinder Grasp"


def _make_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Aeloria",
        level=2,
        # Invented, so nothing else on the sheet reaches into these numbers.
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 0,
            "strength": 0,
            "finesse": 0,
            "instinct": 1,
            "presence": 1,
            "knowledge": 3,
        },
        evasion=11,
        proficiency=2,
        spellcast_trait="knowledge",
        major_threshold=9,
        severe_threshold=18,
        hp_max=7,
        stress_max=6,
        hope_max=6,
        hope_marked=6,
        armor_max=0,  # off unless a case is about armor
        primary_weapon="Greatstaff",
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
        difficulty=0,  # every spell lands
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


# --- Rune Ward ---------------------------------------------------------------


def test_the_ward_takes_its_die_off_a_hit_that_could_drop_a_band():
    caster = _make_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([caster, ally], [])

    with patch("domain_cards.arcana.random.randint", return_value=5):
        taken = rune_ward(caster, ally, 10, state)

    assert taken == 5
    assert ally.hope_marked == 5  # the *holder* pays


def test_the_ward_ignores_a_hit_it_could_not_move():
    """30 damage is nowhere near a threshold an 8 could carry it under."""
    caster = _make_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([caster, ally], [])

    assert rune_ward(caster, ally, 30, state) == 0
    assert ally.hope_marked == 6


def test_the_ward_fires_on_a_hit_it_could_take_away_entirely():
    """Under 8 damage, any Ward Die big enough leaves nothing to mark."""
    caster = _make_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([caster, ally], [])

    with patch("domain_cards.arcana.random.randint", return_value=7):
        assert rune_ward(caster, ally, 6, state) == 7


def test_a_ward_die_of_eight_reduces_this_hit_and_then_burns_out():
    caster = _make_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([caster, ally], [])

    with patch("domain_cards.arcana.random.randint", return_value=8):
        first = rune_ward(caster, ally, 10, state)
    second = rune_ward(caster, ally, 10, state)

    assert first == 8
    assert second == 0
    assert state.token_count(caster, WARD_SPENT) == 1


def test_the_ward_protects_its_holder_and_nobody_else():
    caster = _make_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([caster, ally], [])

    with patch("domain_cards.arcana.random.randint", return_value=5):
        assert rune_ward(caster, caster, 10, state) == 0
    assert caster.hope_marked == 6


def test_a_caster_with_no_ally_keeps_the_trinket_in_their_pocket():
    """Ruled: it goes to somebody else, so a lone PC can never use it."""
    caster = _make_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    state = _state([caster], [])

    assert rune_ward(caster, caster, 10, state) == 0
    assert caster.hope_marked == 6


def test_the_ward_needs_a_hope_from_whoever_holds_it():
    caster = _make_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_pc(name="Guardian", domain_cards_loadout=[], hope_marked=0)
    state = _state([caster, ally], [])

    assert rune_ward(caster, ally, 10, state) == 0


def test_the_reduction_lands_before_the_thresholds():
    """The whole point of the hook: 10 is Major, and 10 less 5 is not."""
    caster = _make_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([caster, ally], [])

    with patch("domain_cards.arcana.random.randint", return_value=5):
        marked = ally.take_damage(10, state)

    assert marked == 1  # Major (2 HP) without the ward


def test_a_party_without_the_card_takes_the_hit_in_full():
    ally = _make_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([ally], [])

    assert ally.take_damage(10, state) == 2


# --- Unleash Chaos -----------------------------------------------------------


def test_the_card_opens_full_and_spends_everything():
    random.seed(3)
    caster = _make_pc(domain_cards_loadout=[UNLEASH_CHAOS])
    target = _make_adversary()
    state = _state([caster], [target])

    result = unleash_chaos(caster, target, state)

    # Tokens equal to the Spellcast trait, which is knowledge 3.
    assert result.damage_roll.dice_groups[0] == DiceGroup(count=3, sides=10)
    assert state.token_count(caster, CHAOS_TOKENS) == 0
    assert caster.stress_marked == 0


def test_a_second_cast_marks_a_stress_to_refill():
    random.seed(3)
    caster = _make_pc(domain_cards_loadout=[UNLEASH_CHAOS])
    target = _make_adversary()
    state = _state([caster], [target])

    unleash_chaos(caster, target, state)
    result = unleash_chaos(caster, target, state)

    assert result.damage_roll.dice_groups[0] == DiceGroup(count=3, sides=10)
    assert caster.stress_marked == 1


def test_an_empty_card_declines_when_the_stress_rule_says_no():
    caster = _make_pc(domain_cards_loadout=[UNLEASH_CHAOS], stress_max=2)
    caster.mark_stress(1)  # last slot, and the PC is healthy
    target = _make_adversary()
    state = _state([caster], [target])
    state.set_token(caster, CHAOS_PRIMED, 1)
    state.set_token(caster, CHAOS_TOKENS, 0)

    assert unleash_chaos(caster, target, state) is None
    assert caster.stress_marked == 1


def test_a_caster_with_no_spellcast_trait_declines():
    caster = _make_pc(spellcast_trait="", domain_cards_loadout=[UNLEASH_CHAOS])
    target = _make_adversary()
    state = _state([caster], [target])

    assert unleash_chaos(caster, target, state) is None


def test_a_spellcast_trait_of_zero_has_no_tokens_to_place():
    caster = _make_pc(
        domain_cards_loadout=[UNLEASH_CHAOS],
        traits={
            "agility": 0,
            "strength": 0,
            "finesse": 0,
            "instinct": 0,
            "presence": 0,
            "knowledge": 0,
        },
    )
    target = _make_adversary()
    state = _state([caster], [target])

    assert unleash_chaos(caster, target, state) is None


# --- Cinder Grasp and On Fire ------------------------------------------------


def test_cinder_grasp_burns_the_target_and_leaves_it_alight():
    random.seed(3)
    caster = _make_pc(domain_cards_loadout=[CINDER_GRASP])
    target = _make_adversary()
    state = _state([caster], [target])

    result = cinder_grasp(caster, target, state)

    assert result.damage_roll.dice_groups[0] == DiceGroup(count=1, sides=20)
    assert target.hp_marked > 0
    assert state.has_condition(target, ON_FIRE) is True


def test_on_fire_costs_its_holder_every_time_they_act():
    random.seed(3)
    caster = _make_pc(domain_cards_loadout=[CINDER_GRASP])
    target = _make_adversary()
    state = _state([caster], [target])

    cinder_grasp(caster, target, state)
    before = target.hp_marked
    state.apply_condition_effects(target, WHEN_THEY_ACT)

    assert target.hp_marked > before


def test_a_creature_that_is_not_acting_does_not_burn():
    random.seed(3)
    caster = _make_pc(domain_cards_loadout=[CINDER_GRASP])
    target = _make_adversary()
    state = _state([caster], [target])

    cinder_grasp(caster, target, state)
    before = target.hp_marked
    state.apply_condition_effects(target, ON_A_GM_TURN)

    assert target.hp_marked == before


def test_the_gm_can_pay_a_fear_to_put_the_fire_out():
    random.seed(3)
    caster = _make_pc(domain_cards_loadout=[CINDER_GRASP])
    target = _make_adversary()
    state = _state([caster], [target], fear=3)

    cinder_grasp(caster, target, state)
    ended = state.expire_conditions(target, ON_A_GM_TURN)

    assert ON_FIRE in ended
    assert state.fear == 2


def test_a_gm_with_no_fear_watches_it_burn():
    random.seed(3)
    caster = _make_pc(domain_cards_loadout=[CINDER_GRASP])
    target = _make_adversary()
    state = _state([caster], [target], fear=0)

    cinder_grasp(caster, target, state)

    assert state.expire_conditions(target, ON_A_GM_TURN) == []
    assert state.has_condition(target, ON_FIRE) is True


# --- Assessed and dismissed --------------------------------------------------


def test_the_two_utility_spells_are_declared_rather_than_absent():
    assert assess("Wall Walk").status.value == "no combat effect"
    assert assess("Floating Eye").status.value == "no combat effect"
