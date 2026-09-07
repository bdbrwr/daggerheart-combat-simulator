"""Tests for the Blade domain cards.

The oldest is a damage response, which makes it easy to test honestly: damage of
a chosen size goes in, and the HP it marks comes out. No dice are involved in
those except the death move, which the cases here stay clear of unless they're
testing it. The later ones reach a roll, and stay deterministic by constructing
the result they need or by giving the target a Difficulty of 0 or 1 so that
whether the attack landed is never what a case turns on.

One piece of shared machinery is what several of these are really about:

* **`attack_failed`** belongs to the attacker, where `attack_missed` belongs to
  whoever was swung at. The two are one word apart and must not be confused;
  Glancing Blow is the card on the first of them.
* **`Condition.denies_armor`**, read through `FightState.armor_is_denied` at the
  one point `take_damage` would mark a free slot. A field rather than a hook,
  which is what `prevents_action` and `untargetable` already are. Frenzy is what
  needed it.

The rules readings these pin down are the ones the card module documents as
choices rather than as SRD text - that Get Back Up triggers on the damage amount
and so stacks with an Armor Slot, that Not Good Enough rerolls each die once and
before any discard, that Glancing Blow's half Proficiency rounds **up**, that
Battle Cry gives everything away and keeps none of it, and that Frenzy waits for
the armor to be gone. If any of those change, these are the tests that should
fail.
"""

import random
from unittest.mock import Mock, patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.state import FightState
from content import (
    Status,
    ally_granted_attack_advantage,
    apply_ally_on_roll,
    apply_attack_failed,
    assess,
    granted_attack_advantage,
    reroll_damage_dice,
    soften_damage,
    total_damage_bonus,
    total_roll_bonus,
    use_free_abilities,
)
from content.conditions import FRENZIED, Condition
from content.damage_types import DamageType
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from domain_cards.blade import (
    BATTLE_CRY,
    BATTLE_CRY_RALLIED,
    BLADE_TOUCHED,
    FRENZY,
    FRENZY_DAMAGE,
    GLANCING_BLOW,
    get_back_up,
    not_good_enough,
    reckless,
)
from items.registry import find_weapon
from items.weapons import attack_with

GET_BACK_UP = "Get Back Up"
NOT_GOOD_ENOUGH = "Not Good Enough"
RECKLESS = "Reckless"

# The default sheet names a real ancestry and community, which carry content of
# their own. That's fine for the damage-response cases, which measure HP; it
# isn't for a case counting Hope or Stress to the point, since a rider that
# spends either would land in the same total. These blank both out for the same
# reason the defaults blank out the class and subclass.
NOTHING_ELSE = dict(ancestry="Unwritten Ancestry", community="Unwritten Community")


def _make_level_1_pc(**overrides) -> PlayerCharacter:
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
        armor_max=0,  # off unless a case is about armor
        primary_weapon="Broadsword",
        secondary_weapon=None,
        # No armor item, deliberately: several cases here go through
        # `soften_damage`, and an armor feature registered on the same hook would
        # sit in the middle of what is being measured.
        armor_item="",
        domain_cards_loadout=[],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
    )
    defaults.update(overrides)
    return PlayerCharacter(**defaults)


def _make_target(**overrides) -> Adversary:
    """The level 1-2 cards' target.

    Trivial on purpose: those cases are about what a card does on a hit, not
    about whether the attack landed.
    """
    defaults = dict(
        name="Test Adversary",
        tier=1,
        difficulty=1,
        major_threshold=100,
        severe_threshold=200,
        hp_max=50,
        stress_max=3,
        attack_modifier=0,
        damage_dice=[DiceGroup(count=1, sides=4)],
        damage_modifier=0,
    )
    defaults.update(overrides)
    return Adversary(**defaults)


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
        encounter_name="Test", party=list(party), adversaries=list(adversaries), **overrides
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


# --- Get Back Up -------------------------------------------------------------


def test_get_back_up_turns_a_severe_hit_into_a_major_one():
    character = _make_level_1_pc(domain_cards_loadout=[GET_BACK_UP])

    assert character.take_damage(12) == 2
    assert character.stress_marked == 1


def test_without_the_card_a_severe_hit_costs_the_full_three():
    character = _make_level_1_pc(domain_cards_loadout=[])

    assert character.take_damage(12) == 3
    assert character.stress_marked == 0


def test_get_back_up_ignores_anything_short_of_severe():
    character = _make_level_1_pc(domain_cards_loadout=[GET_BACK_UP])

    assert character.take_damage(6) == 2  # Major, not Severe
    assert character.stress_marked == 0


def test_get_back_up_stacks_with_an_armor_slot():
    """The chosen reading: the hit is Severe by its size, whatever armor did."""
    character = _make_level_1_pc(domain_cards_loadout=[GET_BACK_UP], armor_max=3)

    assert character.take_damage(12) == 1  # 3, less one for armor, less one for the card
    assert character.armor_marked == 1
    assert character.stress_marked == 1


def test_get_back_up_cannot_fire_when_stress_is_full():
    """A move costing Stress is unavailable, not paid for in HP."""
    character = _make_level_1_pc(domain_cards_loadout=[GET_BACK_UP], stress_max=2)
    character.mark_stress(2)

    assert character.take_damage(12) == 3
    assert character.hp_marked == 3


def test_get_back_up_refuses_a_cost_it_cannot_pay_even_when_it_wants_to():
    """Called directly: the policy wants the reduction, but Stress is full.

    Going through take_damage here would mark the last HP and roll a death
    move, which this isn't about.
    """
    character = _make_level_1_pc(domain_cards_loadout=[GET_BACK_UP], stress_max=1, hp_max=3)
    character.mark_stress(1)

    assert get_back_up(character, 12, 3) == 3
    assert character.hp_marked == 0


def test_get_back_up_buys_nothing_when_the_hit_is_already_down_to_zero():
    """Called directly - armor alone can't reach 0 from Severe, so this guards a branch."""
    character = _make_level_1_pc(domain_cards_loadout=[GET_BACK_UP])

    assert get_back_up(character, 12, 0) == 0
    assert character.stress_marked == 0


def test_get_back_up_keeps_its_last_stress_when_the_hit_is_survivable():
    """Marking the last Stress means Advantage on every roll against you."""
    character = _make_level_1_pc(domain_cards_loadout=[GET_BACK_UP], stress_max=2, hp_max=7)
    character.mark_stress(1)

    assert character.take_damage(12) == 3
    assert character.stress_marked == 1
    assert character.is_vulnerable is False


def test_get_back_up_holds_its_last_stress_even_against_a_hit_that_drops_them():
    """The behaviour the shared Stress rule changed, pinned deliberately.

    This card used to pay whenever the hit would put the PC down. It now asks
    `will_spend_stress` like every other Stress cost, which releases the last
    slot only at 2 or fewer unmarked HP - and 3 unmarked HP against a 3 HP hit
    is exactly the case that falls outside it.
    """
    character = _make_level_1_pc(domain_cards_loadout=[GET_BACK_UP], stress_max=2, hp_max=3)
    character.mark_stress(1)

    assert character.take_damage(12) == 3
    assert character.stress_marked == 1
    assert character.is_conscious is False


def test_get_back_up_spends_its_last_stress_once_the_pc_is_near_death():
    """At 2 or fewer unmarked HP the last slot is released, per the shared rule.

    Armor is on so the reduction has somewhere to land: 3 HP, less one for the
    free slot, less one for the card, leaves the PC standing on their last HP.
    """
    character = _make_level_1_pc(
        domain_cards_loadout=[GET_BACK_UP], stress_max=2, hp_max=6, armor_max=1
    )
    character.mark_stress(1)
    character.mark_hp(4)  # 2 unmarked - near death

    assert character.take_damage(12) == 1
    assert character.stress_marked == 2
    assert character.is_vulnerable is True
    assert character.is_conscious is True


# --- Not Good Enough ---------------------------------------------------------


def _damage_roll(die_results, sides=6, **overrides) -> DamageRollResult:
    """A damage roll with dice already showing what a case needs them to show."""
    defaults = dict(
        dice_groups=[DiceGroup(count=len(die_results), sides=sides)],
        die_results=[list(die_results)],
        modifier=0,
    )
    defaults.update(overrides)
    return DamageRollResult(**defaults)


def test_not_good_enough_rerolls_ones_and_twos_and_leaves_the_rest():
    character = _make_level_1_pc(domain_cards_loadout=[NOT_GOOD_ENOUGH])
    roll = _damage_roll([1, 2, 3, 6])

    with patch("content.registry.random.randint", return_value=5):
        rerolled = reroll_damage_dice(character, roll, None)

    assert rerolled.die_results == [[5, 5, 3, 6]]


def test_a_reroll_replaces_the_roll_rather_than_mutating_it():
    """Roll results are frozen dataclasses; the original has to survive intact."""
    character = _make_level_1_pc(domain_cards_loadout=[NOT_GOOD_ENOUGH])
    roll = _damage_roll([1, 6])

    with patch("content.registry.random.randint", return_value=4):
        rerolled = reroll_damage_dice(character, roll, None)

    assert roll.die_results == [[1, 6]]
    assert rerolled.die_results == [[4, 6]]
    assert rerolled.total == 10


def test_a_die_is_offered_one_reroll_and_not_a_second():
    """A rerolled 2 that comes up a 1 stays a 1 - reroll, not reroll-until-happy."""
    character = _make_level_1_pc(domain_cards_loadout=[NOT_GOOD_ENOUGH])
    roll = _damage_roll([2])

    with patch("content.registry.random.randint", return_value=1) as thrown:
        rerolled = reroll_damage_dice(character, roll, None)

    assert rerolled.die_results == [[1]]
    assert thrown.call_count == 1


def test_a_roll_with_nothing_to_reroll_comes_back_unchanged():
    character = _make_level_1_pc(domain_cards_loadout=[NOT_GOOD_ENOUGH])
    roll = _damage_roll([3, 4, 5])

    assert reroll_damage_dice(character, roll, None) is roll


def test_a_pc_without_the_card_keeps_every_die():
    character = _make_level_1_pc(domain_cards_loadout=[])
    roll = _damage_roll([1, 1, 1])

    assert reroll_damage_dice(character, roll, None) is roll


def test_the_card_answers_for_itself_whatever_die_it_is_asked_about():
    character = _make_level_1_pc()

    assert not_good_enough(character, 12, 2, None) is True
    assert not_good_enough(character, 4, 3, None) is False


def test_a_reroll_happens_before_a_massive_discard_takes_the_lowest():
    """The discard is derived from the results, so it sees the new values."""
    character = _make_level_1_pc(domain_cards_loadout=[NOT_GOOD_ENOUGH])
    roll = _damage_roll([1, 4, 6], drop_lowest=1)

    with patch("content.registry.random.randint", return_value=5):
        rerolled = reroll_damage_dice(character, roll, None)

    assert rerolled.dropped == [4]  # not the 1, which is now a 5
    assert rerolled.rolled_total == 11


# --- Reckless ----------------------------------------------------------------


def test_reckless_marks_a_stress_for_advantage():
    character = _make_level_1_pc(domain_cards_loadout=[RECKLESS], stress_max=3)
    adversary = _make_target()
    fight = _state([character], [adversary])

    assert reckless(character, adversary, fight) is AdvantageState.ADVANTAGE
    assert character.stress_marked == 1


def test_reckless_declines_on_the_last_slot_while_the_pc_is_healthy():
    character = _make_level_1_pc(domain_cards_loadout=[RECKLESS], stress_max=2, hp_max=7)
    character.mark_stress(1)
    adversary = _make_target()
    fight = _state([character], [adversary])

    assert reckless(character, adversary, fight) is None
    assert character.stress_marked == 1


def test_reckless_reaches_a_weapon_swing_through_dispatch():
    """Nothing in items/weapons.py knows this card; it asks the hook."""
    character = _make_level_1_pc(domain_cards_loadout=[RECKLESS], stress_max=3)
    adversary = _make_target()
    fight = _state([character], [adversary])

    assert granted_attack_advantage(character, adversary, fight) is AdvantageState.ADVANTAGE
    assert character.stress_marked == 1


def test_a_reckless_pc_rolls_their_swing_with_advantage():
    character = _make_level_1_pc(
        domain_cards_loadout=[RECKLESS], stress_max=3, **NOTHING_ELSE
    )
    adversary = _make_target()
    fight = _state([character], [adversary])

    random.seed(11)
    result = attack_with(character, find_weapon("Broadsword"), adversary, fight=fight)

    assert result.attack_roll.advantage_state is AdvantageState.ADVANTAGE
    assert character.stress_marked == 1


# --- Blade-Touched -----------------------------------------------------------


def test_blade_touched_adds_two_to_an_attack_roll():
    holder = _make_level_7_pc(domain_cards_loadout=[BLADE_TOUCHED])
    target = _make_adversary()
    fight = _state([holder], [target])

    assert total_roll_bonus(holder, target, fight) == 2


def test_blade_touched_declares_its_threshold_clause_as_a_gap():
    assert assess(BLADE_TOUCHED).is_partial is True
    assert "Severe damage threshold" in " ".join(assess(BLADE_TOUCHED).unmodelled)


# --- Glancing Blow -----------------------------------------------------------


def test_a_failed_swing_still_lands_something():
    random.seed(1)
    holder = _make_level_7_pc(domain_cards_loadout=[GLANCING_BLOW])
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
    holder = _make_level_7_pc(domain_cards_loadout=[GLANCING_BLOW], proficiency=proficiency)
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
    holder = _make_level_7_pc(domain_cards_loadout=[GLANCING_BLOW], stress_max=2)
    holder.mark_stress(1)
    target = _make_adversary()
    fight = _state([holder], [target])

    apply_attack_failed(holder, target, _roll(2, 3, difficulty=20), fight)

    assert holder.stress_marked == 1
    assert target.hp_marked == 0


def test_a_pc_without_the_card_does_nothing_on_a_miss():
    holder = _make_level_7_pc(domain_cards_loadout=[])
    target = _make_adversary()
    fight = _state([holder], [target])

    apply_attack_failed(holder, target, _roll(2, 3, difficulty=20), fight)

    assert target.hp_marked == 0


# --- Battle Cry --------------------------------------------------------------


def _crying_party():
    crier = _make_level_8_pc(
        name="Crier", domain_cards_loadout=[BATTLE_CRY], stress_marked=2, hope_marked=1
    )
    ally = _make_level_8_pc(name="Ally", stress_marked=2, hope_marked=1)
    fight = _rested_state([crier, ally], [_make_adversary()])
    return crier, ally, fight


def test_battle_cry_pays_the_allies_and_not_the_crier():
    crier, ally, fight = _crying_party()

    assert use_free_abilities(crier, fight, 1) == [BATTLE_CRY]
    assert (ally.stress_marked, ally.hope_marked) == (1, 2)
    assert (crier.stress_marked, crier.hope_marked) == (2, 1)


def test_battle_cry_declines_for_a_pc_with_no_allies():
    """Every effect is scoped to allies, so with none the use would buy nothing."""
    crier = _make_level_8_pc(domain_cards_loadout=[BATTLE_CRY])
    fight = _rested_state([crier], [_make_adversary()])

    assert use_free_abilities(crier, fight, 1) == []
    assert fight.can_use_once_per_rest(crier, BATTLE_CRY, long=True)


def test_battle_cry_is_once_per_long_rest():
    crier, _, fight = _crying_party()

    assert use_free_abilities(crier, fight, 1) == [BATTLE_CRY]
    assert use_free_abilities(crier, fight, 1) == []


def test_a_rallied_ally_swings_with_advantage():
    crier, ally, fight = _crying_party()
    use_free_abilities(crier, fight, 1)

    state = ally_granted_attack_advantage(ally, fight.adversaries[0], fight)

    assert state is AdvantageState.ADVANTAGE


def test_the_crier_gains_no_advantage_of_their_own():
    crier, _, fight = _crying_party()
    use_free_abilities(crier, fight, 1)

    state = ally_granted_attack_advantage(crier, fight.adversaries[0], fight)

    assert state is AdvantageState.NONE


def test_a_failure_with_fear_ends_the_rally():
    crier, ally, fight = _crying_party()
    use_free_abilities(crier, fight, 1)

    apply_ally_on_roll(ally, _roll(hope=3, fear=9, difficulty=20), fight)

    assert not fight.token_count(crier, BATTLE_CRY_RALLIED)


def test_a_success_with_fear_leaves_the_rally_standing():
    crier, ally, fight = _crying_party()
    use_free_abilities(crier, fight, 1)

    apply_ally_on_roll(ally, _roll(hope=3, fear=9, difficulty=5), fight)

    assert fight.token_count(crier, BATTLE_CRY_RALLIED)


def test_the_criers_own_failure_with_fear_ends_their_rally():
    """'until **you** or an ally rolls a failure with Fear' - the crier counts."""
    crier, _, fight = _crying_party()
    use_free_abilities(crier, fight, 1)

    apply_ally_on_roll(crier, _roll(hope=3, fear=9, difficulty=20), fight)

    assert not fight.token_count(crier, BATTLE_CRY_RALLIED)


# --- Frenzy ------------------------------------------------------------------


def test_frenzy_waits_while_an_armor_slot_is_still_free():
    pc = _make_level_8_pc(domain_cards_loadout=[FRENZY], armor_max=3, armor_marked=2)
    fight = _rested_state([pc], [_make_adversary()])

    assert use_free_abilities(pc, fight, 1) == []
    assert not fight.has_condition(pc, FRENZIED)


def test_frenzy_starts_once_every_armor_slot_is_marked():
    pc = _make_level_8_pc(domain_cards_loadout=[FRENZY], armor_max=3, armor_marked=3)
    fight = _rested_state([pc], [_make_adversary()])

    assert use_free_abilities(pc, fight, 1) == [FRENZY]
    assert fight.has_condition(pc, FRENZIED)


def test_a_pc_with_no_armor_at_all_frenzies_immediately():
    pc = _make_level_8_pc(domain_cards_loadout=[FRENZY], armor_max=0)
    fight = _rested_state([pc], [_make_adversary()])

    assert use_free_abilities(pc, fight, 1) == [FRENZY]


def test_frenzy_adds_ten_to_the_damage_roll():
    pc = _make_level_8_pc(domain_cards_loadout=[FRENZY], armor_max=0)
    target = _make_adversary()
    fight = _rested_state([pc], [target])

    assert total_damage_bonus(pc, target, fight) == 0
    use_free_abilities(pc, fight, 1)
    assert total_damage_bonus(pc, target, fight) == FRENZY_DAMAGE


def test_a_frenzied_pc_marks_no_armor_slot():
    """The condition's `denies_armor`, read at the one point a slot would go in."""
    pc = _make_level_8_pc(armor_max=3)
    fight = _rested_state([pc], [_make_adversary()])
    fight.apply_condition(pc, Condition(name=FRENZIED, denies_armor=True))

    marked = pc.take_damage(12, fight, damage_type=DamageType.PHYSICAL)

    assert pc.armor_marked == 0
    assert marked == 2  # Major, with nothing to soften it


def test_a_pc_who_is_not_frenzied_still_marks_their_armor():
    pc = _make_level_8_pc(armor_max=3)
    fight = _rested_state([pc], [_make_adversary()])

    marked = pc.take_damage(12, fight, damage_type=DamageType.PHYSICAL)

    assert pc.armor_marked == 1
    assert marked == 1


def test_frenzy_takes_a_band_off_a_hit_inside_the_severe_window():
    """A 20 clears the printed Severe threshold; 28 is the first that still does."""
    pc = _make_level_8_pc(domain_cards_loadout=[FRENZY], armor_max=0)
    fight = _rested_state([pc], [_make_adversary()])
    use_free_abilities(pc, fight, 1)

    assert soften_damage(pc, 20, 3, fight, DamageType.PHYSICAL) == 2
    assert soften_damage(pc, 27, 3, fight, DamageType.PHYSICAL) == 2


def test_frenzy_leaves_a_hit_above_the_window_severe():
    pc = _make_level_8_pc(domain_cards_loadout=[FRENZY], armor_max=0)
    fight = _rested_state([pc], [_make_adversary()])
    use_free_abilities(pc, fight, 1)

    assert soften_damage(pc, 28, 3, fight, DamageType.PHYSICAL) == 3


def test_frenzy_leaves_a_hit_below_the_severe_threshold_alone():
    pc = _make_level_8_pc(domain_cards_loadout=[FRENZY], armor_max=0)
    fight = _rested_state([pc], [_make_adversary()])
    use_free_abilities(pc, fight, 1)

    assert soften_damage(pc, 12, 2, fight, DamageType.PHYSICAL) == 2


def test_frenzy_does_nothing_before_it_is_entered():
    pc = _make_level_8_pc(domain_cards_loadout=[FRENZY], armor_max=3, armor_marked=1)
    fight = _rested_state([pc], [_make_adversary()])

    assert soften_damage(pc, 20, 3, fight, DamageType.PHYSICAL) == 3
    assert total_damage_bonus(pc, _make_adversary(), fight) == 0


# --- Assessed ----------------------------------------------------------------


def test_the_level_eight_pair_are_modelled():
    for card in (BATTLE_CRY, FRENZY):
        assert assess(card).status is Status.MODELLED
