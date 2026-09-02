"""Tests for the level 7 cards of Arcana, Blade and Bone.

Six cards, all modelled, and the batch's three pieces of machinery are what most
of these are really about:

* **`spellcast_bonus`** reaches a Spellcast Roll and *not* a weapon swing, which
  is the whole reason it exists rather than Arcana-Touched using `roll_bonus`.
* **`attack_failed`** belongs to the attacker, where `attack_missed` belongs to
  whoever was swung at. The two are one word apart and must not be confused.
* **`Condition.untargetable`** reaches the GM's targeting rule, so a cloaked PC is
  not chosen - and the whole party being cloaked falls back rather than leaving an
  adversary with nobody to hit.

The readings pinned down here are the ones the modules document as choices:
Arcana-Touched switching only a *successful* roll with Fear, the cloak surviving
the spotlight that raised it and breaking on the next roll, Glancing Blow's half
Proficiency rounding **up**, and Bone-Touched negating a hit outright rather than
softening it.

Determinism comes from constructing rolls with fixed dice, from a target with a
Difficulty of 0 so no case turns on whether an attack landed, and from patching
`content.spellcast.roll_duality` where a case needs a particular outcome.
"""

import random
from unittest.mock import Mock, patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.fight import _take_pc_spotlight
from combat.policy import choose_adversary_target
from combat.rest import Rest
from combat.state import FightState
from content import (
    apply_attack_failed,
    apply_on_roll,
    assess,
    party_damage_reduction,
    remake_action_roll,
    total_damage_bonus,
    total_roll_bonus,
    total_spellcast_bonus,
)
from content.conditions import (
    CLOAKED,
    WHEN_THEY_ACT,
    WHEN_THEY_ATTACK,
    Condition,
    when_they_attack,
)
from content.spellcast import spellcast
from dice.common import AdvantageState
from dice.damage import DiceGroup
from dice.duality import DualityRollResult
from domain_cards.arcana import ARCANA_TOUCHED, CASTING, CLOAKING_BLAST
from domain_cards.blade import BLADE_TOUCHED, GLANCING_BLOW
from domain_cards.bone import BONE_TOUCHED, CRUEL_PRECISION


def _make_character(**overrides) -> PlayerCharacter:
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


def _make_adversary(**overrides) -> Adversary:
    defaults = dict(
        name="Dummy",
        tier=1,
        difficulty=0,  # every roll lands
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


# --- Arcana-Touched --------------------------------------------------------------


def test_the_spellcast_bonus_reaches_a_cast():
    caster = _make_character(domain_cards_loadout=[ARCANA_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    assert total_spellcast_bonus(caster, target, fight) == 1


def test_the_spellcast_bonus_does_not_reach_a_weapon_swing():
    """The whole reason for a hook of its own rather than `roll_bonus`."""
    caster = _make_character(domain_cards_loadout=[ARCANA_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    assert total_roll_bonus(caster, target, fight) == 0


def test_the_bonus_lands_in_the_spellcast_roll():
    caster = _make_character(domain_cards_loadout=[ARCANA_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    roll = spellcast(caster, target, fight)

    # Knowledge 2, plus the card's 1.
    assert roll.modifier == 3


def test_the_dice_switch_on_a_successful_roll_with_fear():
    holder = _make_character(domain_cards_loadout=[ARCANA_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    switched = remake_action_roll(holder, _roll(4, 11, difficulty=12), lambda: None, fight)

    assert switched.hope_die_result == 11
    assert switched.fear_die_result == 4
    # The total is untouched - only which die won has changed.
    assert switched.total == 15
    assert switched.is_success is True


def test_the_switch_is_declined_on_a_failure():
    """Ruled: a failure passes the spotlight regardless, so the use is kept."""
    holder = _make_character(domain_cards_loadout=[ARCANA_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    roll = _roll(3, 5, difficulty=20)
    assert remake_action_roll(holder, roll, lambda: None, fight) is roll
    assert fight.can_use_once_per_rest(holder, ARCANA_TOUCHED) is True


def test_the_switch_is_declined_on_a_roll_that_already_came_up_with_hope():
    holder = _make_character(domain_cards_loadout=[ARCANA_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    roll = _roll(11, 4, difficulty=12)
    assert remake_action_roll(holder, roll, lambda: None, fight) is roll


def test_the_switch_is_once_per_rest():
    holder = _make_character(domain_cards_loadout=[ARCANA_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    remake_action_roll(holder, _roll(4, 11, difficulty=12), lambda: None, fight)
    second = _roll(4, 11, difficulty=12)

    assert remake_action_roll(holder, second, lambda: None, fight) is second


# --- Cloaking Blast --------------------------------------------------------------


def test_a_successful_cast_cloaks_the_caster_for_a_hope():
    caster = _make_character(domain_cards_loadout=[CLOAKING_BLAST])
    target = _make_adversary()
    fight = _state([caster], [target])

    spellcast(caster, target, fight)  # sets the "a cast is in flight" token
    apply_on_roll(caster, _roll(9, 4, difficulty=5), fight)

    assert fight.has_condition(caster, CLOAKED) is True
    assert caster.hope_marked == 5


def test_a_weapon_swing_never_cloaks():
    """`on_roll` fires for every action roll; only a cast leaves the token."""
    caster = _make_character(domain_cards_loadout=[CLOAKING_BLAST])
    fight = _state([caster], [])

    apply_on_roll(caster, _roll(9, 4, difficulty=5), fight)

    assert fight.has_condition(caster, CLOAKED) is False
    assert caster.hope_marked == 6


def test_a_failed_cast_clears_the_token_without_cloaking():
    caster = _make_character(domain_cards_loadout=[CLOAKING_BLAST])
    target = _make_adversary()
    fight = _state([caster], [target])

    spellcast(caster, target, fight)
    apply_on_roll(caster, _roll(2, 3, difficulty=20), fight)

    assert fight.has_condition(caster, CLOAKED) is False
    assert fight.token_count(caster, CASTING) == 0


def test_a_cloaked_pc_is_not_chosen_as_a_target():
    hidden = _make_character(name="Hidden")
    plain = _make_character(name="Plain")
    adversary = _make_adversary()
    fight = _state([hidden, plain], [adversary])
    fight.last_pc_to_attack = hidden
    fight.apply_condition(
        hidden, Condition(name=CLOAKED, source=hidden, untargetable=True)
    )

    assert choose_adversary_target(adversary, fight) is plain


def test_a_wholly_cloaked_party_is_still_targetable():
    """A cloak protects an individual, not the party - see `_targetable`."""
    alone = _make_character(name="Alone")
    adversary = _make_adversary()
    fight = _state([alone], [adversary])
    fight.apply_condition(
        alone, Condition(name=CLOAKED, source=alone, untargetable=True)
    )

    assert choose_adversary_target(adversary, fight) is alone


def test_the_cloak_survives_the_spotlight_that_raised_it():
    """The ordering that makes the card work at all.

    The moment that breaks a cloak is announced before the roll's outcome is
    spent, and the cloak is applied by that outcome - so a cast that was itself an
    attack does not break the cloak it just raised.

    Carrying no primary weapon leaves Bolt Beacon as the only option the shuffle
    can reach, which is what makes the spotlight certainly a cast rather than a
    swing. `_take_pc_spotlight` is the loop function that announces the moment.
    """
    random.seed(5)
    caster = _make_character(
        domain_cards_loadout=[CLOAKING_BLAST, "Bolt Beacon"], primary_weapon=""
    )
    target = _make_adversary()
    fight = _state([caster], [target])

    _take_pc_spotlight(fight)

    assert fight.has_condition(caster, CLOAKED) is True


def test_the_cloak_breaks_on_the_next_action_roll():
    """Through the card's real ender, not a stand-in for it."""
    caster = _make_character(domain_cards_loadout=[CLOAKING_BLAST])
    fight = _state([caster], [])
    fight.apply_condition(
        caster,
        Condition(
            name=CLOAKED,
            end=when_they_attack,
            source=caster,
            untargetable=True,
        ),
    )

    # A spotlight that resolved into no roll leaves it alone...
    fight.expire_conditions(caster, WHEN_THEY_ACT)
    assert fight.has_condition(caster, CLOAKED) is True

    # ...and one that made a roll ends it.
    fight.expire_conditions(caster, WHEN_THEY_ATTACK)
    assert fight.has_condition(caster, CLOAKED) is False


def test_the_cloak_is_not_re_bought_while_one_stands():
    caster = _make_character(domain_cards_loadout=[CLOAKING_BLAST])
    target = _make_adversary()
    fight = _state([caster], [target])

    spellcast(caster, target, fight)
    apply_on_roll(caster, _roll(9, 4, difficulty=5), fight)
    spellcast(caster, target, fight)
    apply_on_roll(caster, _roll(9, 4, difficulty=5), fight)

    assert caster.hope_marked == 5  # one Hope, not two


# --- Blade-Touched ---------------------------------------------------------------


def test_blade_touched_adds_two_to_an_attack_roll():
    holder = _make_character(domain_cards_loadout=[BLADE_TOUCHED])
    target = _make_adversary()
    fight = _state([holder], [target])

    assert total_roll_bonus(holder, target, fight) == 2


def test_blade_touched_declares_its_threshold_clause_as_a_gap():
    assert assess(BLADE_TOUCHED).is_partial is True
    assert "Severe damage threshold" in " ".join(assess(BLADE_TOUCHED).unmodelled)


def test_every_touched_card_declares_the_loadout_gate_as_a_gap():
    """The user's ruling: carrying the card is proof of the loadout."""
    for card in (ARCANA_TOUCHED, BLADE_TOUCHED, BONE_TOUCHED):
        assert "loadout" in " ".join(assess(card).unmodelled)


# --- Glancing Blow ---------------------------------------------------------------


def test_a_failed_swing_still_lands_something():
    random.seed(1)
    holder = _make_character(domain_cards_loadout=[GLANCING_BLOW])
    holder.mark_stress(1)
    target = _make_adversary()
    fight = _state([holder], [target])

    apply_attack_failed(holder, target, _roll(2, 3, difficulty=20), fight)

    assert target.hp_marked > 0
    assert holder.stress_marked == 2


def _dice_rolled_by_glancing_blow(proficiency: int) -> int:
    """How many damage dice a failed swing throws at this Proficiency.

    Read off the `roll_damage` call rather than off the damage, since the point is
    the count and any number of dice can roll to any total.
    """
    holder = _make_character(domain_cards_loadout=[GLANCING_BLOW], proficiency=proficiency)
    target = _make_adversary()
    fight = _state([holder], [target])

    with patch("domain_cards.blade.roll_damage", return_value=Mock(total=5)) as rolled:
        apply_attack_failed(holder, target, _roll(2, 3, difficulty=20), fight)

    return sum(group.count for group in rolled.call_args.kwargs["dice_groups"])


def test_half_a_proficiency_rounds_up():
    """Proficiency 3 throws two dice, not one - the user's rule."""
    assert _dice_rolled_by_glancing_blow(3) == 2


def test_rounding_up_means_the_card_always_throws_a_die():
    """No floor-at-1 guard is needed, because rounding up already is one."""
    assert _dice_rolled_by_glancing_blow(1) == 1


def test_an_even_proficiency_is_simply_halved():
    assert _dice_rolled_by_glancing_blow(4) == 2


def test_glancing_blow_holds_its_last_stress_slot():
    """The shared last-slot rule, like every other PC Stress cost."""
    holder = _make_character(domain_cards_loadout=[GLANCING_BLOW], stress_max=2)
    holder.mark_stress(1)
    target = _make_adversary()
    fight = _state([holder], [target])

    apply_attack_failed(holder, target, _roll(2, 3, difficulty=20), fight)

    assert holder.stress_marked == 1
    assert target.hp_marked == 0


def test_a_pc_without_the_card_does_nothing_on_a_miss():
    holder = _make_character(domain_cards_loadout=[])
    target = _make_adversary()
    fight = _state([holder], [target])

    apply_attack_failed(holder, target, _roll(2, 3, difficulty=20), fight)

    assert target.hp_marked == 0


# --- Bone-Touched ----------------------------------------------------------------


def test_three_hope_makes_a_solid_hit_fail():
    holder = _make_character(domain_cards_loadout=[BONE_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    # 12 is over the holder's Major threshold of 10, so the hit qualifies.
    taken = party_damage_reduction(holder, 12, fight)

    assert taken == 12
    assert holder.hope_marked == 3


def test_the_negation_leaves_no_armor_slot_spent():
    """The whole amount is returned, so `take_damage` floors before thresholds."""
    holder = _make_character(domain_cards_loadout=[BONE_TOUCHED], armor_max=3)
    fight = _state([holder], [], rest=Rest.LONG)

    assert holder.take_damage(12, fight) == 0
    assert holder.armor_marked == 0


def test_a_glancing_hit_is_not_worth_three_hope():
    holder = _make_character(domain_cards_loadout=[BONE_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    assert party_damage_reduction(holder, 4, fight) == 0
    assert holder.hope_marked == 6


def test_any_hit_on_a_near_death_holder_is_worth_it():
    holder = _make_character(domain_cards_loadout=[BONE_TOUCHED])
    holder.mark_hp(6)  # 2 unmarked of 8
    fight = _state([holder], [], rest=Rest.LONG)

    assert party_damage_reduction(holder, 4, fight) == 4


def test_bone_touched_never_reaches_an_ally():
    """The card says "an attack that succeeded against **you**"."""
    holder = _make_character(name="Holder", domain_cards_loadout=[BONE_TOUCHED])
    ally = _make_character(name="Ally")
    fight = _state([holder, ally], [], rest=Rest.LONG)

    assert party_damage_reduction(ally, 12, fight) == 0


def test_bone_touched_is_once_per_rest():
    holder = _make_character(domain_cards_loadout=[BONE_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    party_damage_reduction(holder, 12, fight)

    assert party_damage_reduction(holder, 12, fight) == 0


# --- Cruel Precision -------------------------------------------------------------


def test_cruel_precision_takes_the_better_trait():
    """Finesse 3 against Agility 2, and the player picks."""
    holder = _make_character(domain_cards_loadout=[CRUEL_PRECISION])
    target = _make_adversary()
    fight = _state([holder], [target])

    assert total_damage_bonus(holder, target, fight) == 3


def test_cruel_precision_never_makes_a_weapon_worse():
    holder = _make_character(
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
