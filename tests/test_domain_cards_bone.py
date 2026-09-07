"""Tests for the Bone domain cards.

Bone is the Evasion domain, and Ferocity is the first content that changes a PC's
Evasion mid-fight - so several of these are about the number an adversary actually
rolls against rather than about the card in isolation, which is where a bonus that
only exists between two moments has to be checked.

Strategic Approach is a token pool with a trigger keyed per adversary, so its
cases are about which attacks get the die and which don't. Breaking Blow is the
same shape moved onto the *target*: the charge belongs to the creature and the
dice go to whoever hits it next, which is what separates it from a rider on its
own holder's attack.

The reading pinned down here that the module documents as a choice is
Bone-Touched negating a hit outright rather than softening it.
"""

import random
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.results import AttackResult
from combat.state import FightState
from content import (
    Status,
    apply_on_hit,
    assess,
    party_damage_reduction,
    soften_damage,
    total_ally_extra_damage,
    total_damage_bonus,
    total_evasion_bonus,
)
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from domain_cards.bone import (
    BONE_TOUCHED,
    BREAKING_BLOW,
    BREAKING_BLOW_CHARGE,
    CRUEL_PRECISION,
    FEROCITY_BONUS,
    DEATHRUN,
    DEATHRUN_HOPE,
    ON_THE_BRINK,
    SPLINTERING_STRIKE,
    SWIFT_STEP,
    STRATEGIC_OPENED,
    STRATEGIC_TOKENS,
    _finishing_share,
    _splintered,
    deathrun,
    ferocity,
    ferocity_evades,
    on_the_brink,
    splintering_strike,
    strategic_approach,
    swift_step,
)

FEROCITY = "Ferocity"
STRATEGIC_APPROACH = "Strategic Approach"


def _make_level_2_pc(**overrides) -> PlayerCharacter:
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


def _make_level_7_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=7,
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 2,
            "strength": 1,
            "finesse": 3,
            "instinct": 0,
            "presence": 1,
            "knowledge": 2,
        },
        evasion=12,
        proficiency=3,
        spellcast_trait="knowledge",
        major_threshold=10,
        severe_threshold=20,
        hp_max=8,
        stress_max=6,
        hope_max=6,
        hope_marked=6,
        armor_max=0,  # off unless a case is about armor
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


def _make_level_8_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=8,
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 3,
            "strength": 1,
            "finesse": 2,
            "instinct": 0,
            "presence": 1,
            "knowledge": 2,
        },
        evasion=12,
        proficiency=3,
        spellcast_trait="knowledge",
        major_threshold=10,
        severe_threshold=20,
        hp_max=8,
        stress_max=6,
        hope_max=6,
        hope_marked=6,
        armor_max=0,
        primary_weapon="Broadsword",
        secondary_weapon=None,
        armor_item="",
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


def _rested_state(party, adversaries, **overrides) -> FightState:
    """A fight the party walked into off a long rest, for the per-rest cards."""
    overrides.setdefault("rest", Rest.LONG)
    return _state(party, adversaries, **overrides)


def _roll(hope: int, fear: int, difficulty: int | None = None) -> DualityRollResult:
    return DualityRollResult(
        hope_die_result=hope,
        fear_die_result=fear,
        modifier=0,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=difficulty,
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


def _landed_hit() -> AttackResult:
    """An attack that hit for something, for the on-hit riders to read."""
    return AttackResult(
        attack_roll=_roll(hope=9, fear=4, difficulty=5),
        damage_roll=DamageRollResult(
            dice_groups=[DiceGroup(count=1, sides=4)],
            die_results=[[4]],
            modifier=0,
        ),
        hp_marked=1,
    )


# --- Ferocity ----------------------------------------------------------------


def test_ferocity_buys_evasion_equal_to_the_hp_the_hit_marked():
    pc = _make_level_2_pc(domain_cards_loadout=[FEROCITY])
    adversary = _make_adversary()
    state = _state([pc], [adversary])

    ferocity(pc, adversary, _hit(3), state)

    assert pc.hope_marked == 4
    assert state.token_count(pc, FEROCITY_BONUS) == 3


def test_a_hit_that_marked_nothing_buys_nothing():
    pc = _make_level_2_pc(domain_cards_loadout=[FEROCITY])
    adversary = _make_adversary()
    state = _state([pc], [adversary])

    ferocity(pc, adversary, _hit(0), state)

    assert pc.hope_marked == 6
    assert state.token_count(pc, FEROCITY_BONUS) == 0


def test_ferocity_needs_two_hope():
    pc = _make_level_2_pc(domain_cards_loadout=[FEROCITY], hope_marked=1)
    adversary = _make_adversary()
    state = _state([pc], [adversary])

    ferocity(pc, adversary, _hit(2), state)

    assert pc.hope_marked == 1
    assert state.token_count(pc, FEROCITY_BONUS) == 0


def test_the_bonus_reaches_the_number_an_adversary_rolls_against():
    pc = _make_level_2_pc(domain_cards_loadout=[FEROCITY])
    adversary = _make_adversary()
    state = _state([pc], [adversary])
    state.set_token(pc, FEROCITY_BONUS, 2)

    assert total_evasion_bonus(pc, adversary, state) == 2


def test_the_bonus_is_gone_after_the_attack_it_was_bought_for():
    """"Until after the next attack made against you" - one attack, not a fight."""
    pc = _make_level_2_pc(domain_cards_loadout=[FEROCITY])
    adversary = _make_adversary()
    state = _state([pc], [adversary])
    state.set_token(pc, FEROCITY_BONUS, 2)

    first = ferocity_evades(pc, adversary, state)
    second = ferocity_evades(pc, adversary, state)

    assert (first, second) == (2, 0)


def test_a_pc_without_the_card_has_a_plain_evasion():
    pc = _make_level_2_pc(domain_cards_loadout=[])
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
    pc = _make_level_2_pc(domain_cards_loadout=[FEROCITY])
    adversary = _make_adversary()
    state = _state([pc], [adversary])
    state.set_token(pc, FEROCITY_BONUS, 3)

    adversary.attack(pc, fight=state)

    assert state.token_count(pc, FEROCITY_BONUS) == 0


# --- Strategic Approach ------------------------------------------------------


def test_the_opening_blow_on_an_adversary_gets_a_d8():
    pc = _make_level_2_pc(domain_cards_loadout=[STRATEGIC_APPROACH])
    adversary = _make_adversary()
    state = _state([pc], [adversary], rest=Rest.LONG)

    dice = strategic_approach(pc, adversary, None, state)

    assert [(group.count, group.sides) for group in dice] == [(1, 8)]
    assert dice[0].discardable is False


def test_the_second_blow_on_the_same_adversary_gets_nothing():
    pc = _make_level_2_pc(domain_cards_loadout=[STRATEGIC_APPROACH])
    adversary = _make_adversary()
    state = _state([pc], [adversary], rest=Rest.LONG)

    strategic_approach(pc, adversary, None, state)

    assert strategic_approach(pc, adversary, None, state) == []


def test_a_fresh_adversary_gets_its_own_opening_blow():
    """The trigger is per adversary, not per fight."""
    pc = _make_level_2_pc(domain_cards_loadout=[STRATEGIC_APPROACH])
    first, second = _make_adversary(name="A"), _make_adversary(name="B")
    state = _state([pc], [first, second], rest=Rest.LONG)

    strategic_approach(pc, first, None, state)

    assert strategic_approach(pc, second, None, state) != []


def test_the_card_holds_tokens_equal_to_knowledge():
    pc = _make_level_2_pc(domain_cards_loadout=[STRATEGIC_APPROACH])  # knowledge 2
    mob = [_make_adversary(name=f"A{n}") for n in range(4)]
    state = _state([pc], mob, rest=Rest.LONG)

    spent = [strategic_approach(pc, adversary, None, state) for adversary in mob]

    assert [bool(dice) for dice in spent] == [True, True, False, False]
    assert state.token_count(pc, STRATEGIC_TOKENS) == 0


def test_a_knowledge_of_zero_still_places_one_token():
    pc = _make_level_2_pc(
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
    pc = _make_level_2_pc(domain_cards_loadout=[STRATEGIC_APPROACH])
    adversary = _make_adversary()
    state = _state([pc], [adversary], rest=Rest.NONE)

    assert strategic_approach(pc, adversary, None, state) == []


def test_a_short_rest_does_not_place_tokens_either():
    """"After a long rest" - the card says which rest, so a short one won't do."""
    pc = _make_level_2_pc(domain_cards_loadout=[STRATEGIC_APPROACH])
    adversary = _make_adversary()
    state = _state([pc], [adversary], rest=Rest.SHORT)

    assert strategic_approach(pc, adversary, None, state) == []


def test_opening_on_one_adversary_does_not_mark_another_as_opened():
    pc = _make_level_2_pc(domain_cards_loadout=[STRATEGIC_APPROACH])
    first, second = _make_adversary(name="A"), _make_adversary(name="B")
    state = _state([pc], [first, second], rest=Rest.LONG)

    strategic_approach(pc, first, None, state)

    assert state.token_count(pc, f"{STRATEGIC_OPENED}:{id(second)}") == 0


# --- Bone-Touched ------------------------------------------------------------


def test_three_hope_makes_a_solid_hit_fail():
    holder = _make_level_7_pc(domain_cards_loadout=[BONE_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    # 12 is over the holder's Major threshold of 10, so the hit qualifies.
    taken = party_damage_reduction(holder, 12, fight)

    assert taken == 12
    assert holder.hope_marked == 3


def test_the_negation_leaves_no_armor_slot_spent():
    """The whole amount is returned, so `take_damage` floors before thresholds."""
    holder = _make_level_7_pc(domain_cards_loadout=[BONE_TOUCHED], armor_max=3)
    fight = _state([holder], [], rest=Rest.LONG)

    assert holder.take_damage(12, fight) == 0
    assert holder.armor_marked == 0


def test_a_glancing_hit_is_not_worth_three_hope():
    holder = _make_level_7_pc(domain_cards_loadout=[BONE_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    assert party_damage_reduction(holder, 4, fight) == 0
    assert holder.hope_marked == 6


def test_any_hit_on_a_near_death_holder_is_worth_it():
    holder = _make_level_7_pc(domain_cards_loadout=[BONE_TOUCHED])
    holder.mark_hp(6)  # 2 unmarked of 8
    fight = _state([holder], [], rest=Rest.LONG)

    assert party_damage_reduction(holder, 4, fight) == 4


def test_bone_touched_never_reaches_an_ally():
    """The card says "an attack that succeeded against **you**"."""
    holder = _make_level_7_pc(name="Holder", domain_cards_loadout=[BONE_TOUCHED])
    ally = _make_level_7_pc(name="Ally")
    fight = _state([holder, ally], [], rest=Rest.LONG)

    assert party_damage_reduction(ally, 12, fight) == 0


def test_bone_touched_is_once_per_rest():
    holder = _make_level_7_pc(domain_cards_loadout=[BONE_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    party_damage_reduction(holder, 12, fight)

    assert party_damage_reduction(holder, 12, fight) == 0


# --- Cruel Precision ---------------------------------------------------------


def test_cruel_precision_takes_the_better_trait():
    """Finesse 3 against Agility 2, and the player picks."""
    holder = _make_level_7_pc(domain_cards_loadout=[CRUEL_PRECISION])
    target = _make_adversary()
    fight = _state([holder], [target])

    assert total_damage_bonus(holder, target, fight) == 3


def test_cruel_precision_never_makes_a_weapon_worse():
    holder = _make_level_7_pc(
        domain_cards_loadout=[CRUEL_PRECISION],
        traits={
            "agility": -1,
            "strength": 0,
            "finesse": -2,
            "instinct": 0,
            "presence": 0,
            "knowledge": 0,
        },
    )
    target = _make_adversary()
    fight = _state([holder], [target])

    assert total_damage_bonus(holder, target, fight) == 0


# --- Breaking Blow -----------------------------------------------------------


def test_breaking_blow_marks_a_stress_and_leaves_the_target_charged():
    pc = _make_level_8_pc(domain_cards_loadout=[BREAKING_BLOW])
    target = _make_adversary()
    fight = _rested_state([pc], [target])

    apply_on_hit(pc, target, _landed_hit(), fight)

    assert pc.stress_marked == 1
    assert fight.token_count(target, BREAKING_BLOW_CHARGE) == 1


def test_breaking_blow_declines_against_a_target_already_charged():
    pc = _make_level_8_pc(domain_cards_loadout=[BREAKING_BLOW])
    target = _make_adversary()
    fight = _rested_state([pc], [target])
    fight.set_token(target, BREAKING_BLOW_CHARGE, 1)

    apply_on_hit(pc, target, _landed_hit(), fight)

    assert pc.stress_marked == 0


def test_breaking_blow_declines_against_a_target_the_hit_just_defeated():
    pc = _make_level_8_pc(domain_cards_loadout=[BREAKING_BLOW])
    target = _make_adversary(hp_max=1)
    target.hp_marked = 1
    fight = _rested_state([pc], [target])

    apply_on_hit(pc, target, _landed_hit(), fight)

    assert pc.stress_marked == 0


def test_any_pcs_next_attack_collects_the_two_d12():
    """The charge is the Bone character's; the dice go to whoever hits next."""
    bone = _make_level_8_pc(name="Bone", domain_cards_loadout=[BREAKING_BLOW])
    ally = _make_level_8_pc(name="Ally")
    target = _make_adversary()
    fight = _rested_state([bone, ally], [target])
    fight.set_token(target, BREAKING_BLOW_CHARGE, 1)

    groups = total_ally_extra_damage(ally, target, _landed_hit().attack_roll, fight)

    assert groups == [DiceGroup(count=2, sides=12, discardable=False)]
    assert fight.token_count(target, BREAKING_BLOW_CHARGE) == 0


def test_the_charge_pays_out_once():
    bone = _make_level_8_pc(domain_cards_loadout=[BREAKING_BLOW])
    target = _make_adversary()
    fight = _rested_state([bone], [target])
    fight.set_token(target, BREAKING_BLOW_CHARGE, 1)
    roll = _landed_hit().attack_roll

    assert total_ally_extra_damage(bone, target, roll, fight)
    assert total_ally_extra_damage(bone, target, roll, fight) == []


def test_an_uncharged_target_adds_no_dice():
    bone = _make_level_8_pc(domain_cards_loadout=[BREAKING_BLOW])
    target = _make_adversary()
    fight = _rested_state([bone], [target])

    assert total_ally_extra_damage(bone, target, _landed_hit().attack_roll, fight) == []


def test_a_charge_belongs_to_the_creature_rather_than_to_the_attack():
    """Two adversaries, one charged: the other collects nothing."""
    bone = _make_level_8_pc(domain_cards_loadout=[BREAKING_BLOW])
    charged = _make_adversary(name="Charged")
    other = _make_adversary(name="Other")
    fight = _rested_state([bone], [charged, other])
    fight.set_token(charged, BREAKING_BLOW_CHARGE, 1)
    roll = _landed_hit().attack_roll

    assert total_ally_extra_damage(bone, other, roll, fight) == []
    assert total_ally_extra_damage(bone, charged, roll, fight)


# --- On the Brink ------------------------------------------------------------


@contextmanager
def _bunched():
    """Every band at its best reach, so a case is about the card not the spread."""
    with patch("content.aoe.random.random", return_value=0.0):
        yield


def _on_the_brink(**overrides):
    """A Bone character carrying the card, at 2 unmarked HP of 8."""
    holder = _make_level_8_pc(
        level=9, domain_cards_loadout=[ON_THE_BRINK], **overrides
    )
    holder.mark_hp(6)
    return holder, _rested_state([holder], [_make_adversary()])


def test_minor_damage_marks_nothing_while_near_death():
    holder, fight = _on_the_brink()

    assert holder.is_near_death is True
    assert soften_damage(holder, 5, 1, fight) == 0


def test_a_major_hit_is_untouched():
    """The card answers Minor damage and nothing else."""
    holder, fight = _on_the_brink()

    assert soften_damage(holder, 12, 2, fight) == 2


def test_a_healthy_holder_takes_minor_damage_normally():
    holder = _make_level_8_pc(level=9, domain_cards_loadout=[ON_THE_BRINK])
    fight = _rested_state([holder], [_make_adversary()])

    assert holder.is_near_death is False
    assert soften_damage(holder, 5, 1, fight) == 1


def test_the_trigger_is_read_off_the_damage_and_not_the_hp_it_would_mark():
    """A Major hit an Armor Slot softened to one HP is still not Minor damage."""
    holder, fight = _on_the_brink()

    assert soften_damage(holder, 12, 1, fight) == 1


def test_a_hit_armor_already_took_to_nothing_is_left_alone():
    holder, fight = _on_the_brink()

    assert soften_damage(holder, 5, 0, fight) == 0


def test_the_card_reaches_the_real_damage_pipeline():
    holder, fight = _on_the_brink()

    assert holder.take_damage(5, fight) == 0
    assert holder.hp_marked == 6


def test_a_holder_without_the_card_marks_the_hit_point():
    holder = _make_level_8_pc(level=9)
    holder.mark_hp(6)
    fight = _rested_state([holder], [_make_adversary()])

    assert holder.take_damage(5, fight) == 1


def test_the_card_answers_for_itself_whatever_it_is_asked():
    """The card's own contract, independent of how the registry calls it."""
    holder, fight = _on_the_brink()

    assert on_the_brink(holder, 5, 1, fight) == 0
    assert on_the_brink(holder, 12, 2, fight) == 2


# --- Splintering Strike: how the pool is shared out ---------------------------
#
# `_splintered` is a pure function of a pool and the targets an attack beat, so
# the allocation ruling is pinned here directly rather than through a cast whose
# damage would have to be patched twice over.


@pytest.mark.parametrize(
    "unmarked, expected",
    [(1, 1), (2, "major"), (3, "severe"), (4, None), (5, None)],
)
def test_what_it_costs_to_finish_a_target(unmarked, expected):
    """The bands cap a single share at 3 HP, so four unmarked cannot be finished."""
    adversary = _make_adversary(hp_max=unmarked, major_threshold=10, severe_threshold=20)

    wanted = {"major": 10, "severe": 20}.get(expected, expected)

    assert _finishing_share(adversary) == wanted


def test_a_defeated_target_needs_no_share():
    adversary = _make_adversary(hp_max=1)
    adversary.hp_marked = 1

    assert _finishing_share(adversary) is None


def test_the_pool_finishes_what_it_can_and_wastes_the_rest():
    """Both are on their last Hit Point, so a point each is the whole answer."""
    first, second = _make_adversary(name="A", hp_max=1), _make_adversary(
        name="B", hp_max=1
    )

    shared = dict(
        (adversary.name, share) for adversary, share in _splintered(40, [first, second])
    )

    assert shared == {"A": 1, "B": 1}


def test_a_target_nothing_could_finish_takes_the_whole_pool():
    alone = _make_adversary(name="A", hp_max=5)

    assert _splintered(40, [alone]) == [(alone, 40)]


def test_the_remainder_goes_to_the_toughest_left_standing():
    """B is finished for a point; A's finishing share is out of reach, so it
    takes everything left rather than the pool being spent on a corpse."""
    tough = _make_adversary(name="A", hp_max=2, major_threshold=10)
    frail = _make_adversary(name="B", hp_max=1)

    shared = dict(
        (adversary.name, share) for adversary, share in _splintered(5, [tough, frail])
    )

    assert shared == {"B": 1, "A": 4}


# --- Splintering Strike: the card ---------------------------------------------


def _splintering(*hit_points: int, **overrides):
    holder = _make_level_8_pc(
        level=9, domain_cards_loadout=[SPLINTERING_STRIKE], **overrides
    )
    field = [
        _make_adversary(name=f"Dummy {index}", hp_max=points)
        for index, points in enumerate(hit_points)
    ]
    return holder, field, _rested_state([holder], field)


def test_the_strike_spends_a_hope_and_finishes_what_it_beat():
    holder, field, fight = _splintering(1, 1)

    with _bunched():
        result = splintering_strike(holder, field[0], fight)

    assert result is not None
    assert holder.hope_marked == 5
    assert all(adversary.is_defeated for adversary in field)


def test_the_strike_is_once_per_long_rest_on_a_success():
    holder, field, fight = _splintering(1, 1)

    with _bunched():
        assert splintering_strike(holder, field[0], fight) is not None
        assert fight.can_use_once_per_rest(holder, SPLINTERING_STRIKE, long=True) is False
        assert splintering_strike(holder, field[0], fight) is None


def test_the_strike_declines_without_a_hope():
    holder, field, fight = _splintering(1, 1, hope_marked=0)

    with _bunched():
        assert splintering_strike(holder, field[0], fight) is None
    assert all(adversary.hp_marked == 0 for adversary in field)


def test_a_roll_that_beats_nobody_keeps_the_per_rest_use():
    """"Once per long rest, **on a success**" gates the payoff, not the attempt."""
    holder, field, fight = _splintering(1)
    field[0].difficulty = 40

    with _bunched(), patch(
        "content.spellcast.roll_duality", return_value=_roll(2, 3, difficulty=40)
    ):
        result = splintering_strike(holder, field[0], fight)

    assert result is not None and not result.attack_roll.is_success
    assert field[0].hp_marked == 0
    assert holder.hope_marked == 5  # the Hope buys the attempt
    assert fight.can_use_once_per_rest(holder, SPLINTERING_STRIKE, long=True) is True


# --- Deathrun ----------------------------------------------------------------


def _running(*hit_points: int, **overrides):
    holder = _make_level_8_pc(level=10, domain_cards_loadout=[DEATHRUN], **overrides)
    field = [
        _make_adversary(
            name=f"Dummy {index}",
            hp_max=points,
            major_threshold=10,
            severe_threshold=20,
        )
        for index, points in enumerate(hit_points)
    ]
    return holder, field, _rested_state([holder], field)


def _a_fixed_pool():
    """26 across four dice - so the bundles are 26 and then 24, 18 and 12."""
    return patch(
        "domain_cards.bone.roll_damage",
        return_value=DamageRollResult(
            dice_groups=[DiceGroup(count=4, sides=8)],
            die_results=[[8, 8, 8, 2]],
            modifier=0,
        ),
    )


def test_the_run_spends_three_hope_and_deals_down_the_line():
    holder, field, fight = _running(3, 1)

    with _bunched(), _a_fixed_pool():
        result = deathrun(holder, field[0], fight)

    assert result is not None
    assert holder.hope_marked == 6 - DEATHRUN_HOPE
    assert all(adversary.is_defeated for adversary in field)


def test_the_first_bundle_goes_where_it_finishes_the_most():
    """26 marks 3 Hit Points, so it is spent on the target that needs all three."""
    holder, field, fight = _running(1, 3)

    with _bunched(), _a_fixed_pool():
        deathrun(holder, field[0], fight)

    assert field[1].hp_marked == 3
    assert field[0].is_defeated is True


def test_no_adversary_is_dealt_to_twice():
    """"You can't target the same adversary more than once per attack."

    Both are far too big to finish, so nothing about the order hides a second
    helping: one bundle each is three marked Hit Points each.
    """
    holder, field, fight = _running(50, 50)

    with _bunched(), _a_fixed_pool():
        deathrun(holder, field[0], fight)

    assert [adversary.hp_marked for adversary in field] == [3, 3]


def test_the_run_declines_without_the_three_hope():
    holder, field, fight = _running(3, 1, hope_marked=2)

    with _bunched():
        assert deathrun(holder, field[0], fight) is None


# --- Swift Step --------------------------------------------------------------


def _stepping(**overrides):
    holder = _make_level_8_pc(level=10, domain_cards_loadout=[SWIFT_STEP], **overrides)
    attacker = _make_adversary()
    return holder, attacker, _rested_state([holder], [attacker])


def test_a_failed_attack_clears_a_stress():
    holder, attacker, fight = _stepping(stress_marked=2)

    swift_step(holder, attacker, _roll(2, 3, 20), fight)

    assert holder.stress_marked == 1


def test_it_hands_over_a_hope_when_there_is_no_stress_to_clear():
    """The card prints the fallback the general rule already states."""
    holder, attacker, fight = _stepping(hope_marked=2)

    swift_step(holder, attacker, _roll(2, 3, 20), fight)

    assert holder.hope_marked == 3
    assert holder.stress_marked == 0


def test_it_reaches_the_missed_attack_trigger_through_dispatch():
    from content import apply_attack_missed

    holder, attacker, fight = _stepping(stress_marked=2)

    apply_attack_missed(holder, attacker, _roll(2, 3, 20), fight)

    assert holder.stress_marked == 1


# --- Assessed and dismissed --------------------------------------------------


def test_untouchable_is_already_in_the_sheets_evasion():
    assert assess("Untouchable").status is Status.NO_COMBAT_EFFECT


@pytest.mark.parametrize("card", ["Deft Maneuvers", "I See It Coming"])
def test_the_two_measured_dismissals_say_how_much_they_are_worth(card):
    """An insignificant ruling's whole claim is the size, so it has to state one."""
    assessment = assess(card)

    assert assessment.status is Status.INSIGNIFICANT_COMBAT_EFFECT
    assert assessment.reason


def test_breaking_blow_is_modelled_and_wrangle_is_dismissed():
    assert assess(BREAKING_BLOW).status is Status.MODELLED
    assert assess("Wrangle").status is Status.NO_COMBAT_EFFECT


def test_the_level_nine_pair_are_modelled():
    for card in (ON_THE_BRINK, SPLINTERING_STRIKE):
        assert assess(card).status is Status.MODELLED


def test_the_level_ten_pair_are_modelled():
    for card in (DEATHRUN, SWIFT_STEP):
        assert assess(card).status is Status.MODELLED
