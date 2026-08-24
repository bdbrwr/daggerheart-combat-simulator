"""Tests for the Blade and Valor domain cards.

The two oldest are damage responses, which makes them easy to test honestly:
damage of a chosen size goes in, and the HP it marks comes out. No dice are
involved in those except the death move, which the cases here stay clear of
unless they're testing it. The later ones reach a roll, and stay deterministic by
constructing the result they need or by giving the target a Difficulty of 1 so
that whether the attack landed is never what a case turns on.

The rules readings these pin down are the ones the card modules document as
choices rather than as SRD text - that Get Back Up triggers on the damage amount
and so stacks with an Armor Slot, that I Am Your Shield swaps the target before
the attack is rolled, that Not Good Enough rerolls each die once and before any
discard, and that a critical is not a success with Hope. If any of those change,
these are the tests that should fail.

The shared Stress rule is pinned here too, since every card costing a Stress asks
it rather than deciding for itself.

Cards are tested through the dispatch functions the rest of the codebase calls,
plus a case each through combat/policy.py and items/weapons.py to prove those
call sites are wired up.
"""

import random
from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.policy import _shield
from combat.state import FightState
from content import (
    Status,
    assess,
    find_guard,
    find_severity_response,
    find_shielder,
    granted_attack_advantage,
    reroll_damage_dice,
)
from content.conditions import RESTRAINED, VULNERABLE, Condition
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from domain_cards.blade import get_back_up, not_good_enough, reckless
from domain_cards.valor import (
    bold_presence,
    forceful_push,
    forceful_push_momentum,
    i_am_your_shield,
)
from items.registry import find_weapon
from items.weapons import attack_with

GET_BACK_UP = "Get Back Up"
I_AM_YOUR_SHIELD = "I Am Your Shield"
NOT_GOOD_ENOUGH = "Not Good Enough"
RECKLESS = "Reckless"
FORCEFUL_PUSH = "Forceful Push"
BOLD_PRESENCE = "Bold Presence"
A_SOLDIERS_BOND = "A Soldier's Bond"

# The default sheet names a real ancestry and community, which carry content of
# their own. That's fine for the damage-response cases above, which measure HP;
# it isn't for a case counting Hope or Stress to the point, since a rider that
# spends either would land in the same total. These blank both out for the same
# reason the defaults blank out the class and subclass.
NOTHING_ELSE = dict(ancestry="Unwritten Ancestry", community="Unwritten Community")


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


def test_a_card_that_registered_no_such_hook_is_skipped_rather_than_an_error():
    """A lookup asks one hook table, and most content isn't in it.

    Whirlwind is implemented and is not a guard; a name nobody has written is in
    no table at all. Both have to come back None rather than raising, because a
    sheet is allowed to carry either.
    """
    assert find_severity_response("A Card Nobody Has Written") is None
    assert find_guard("Whirlwind") is None


def test_a_pc_carrying_an_unimplemented_card_still_takes_damage_normally():
    character = _make_character(
        domain_cards_loadout=["A Card Nobody Has Written", "Whirlwind"]
    )

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


def test_get_back_up_holds_its_last_stress_even_against_a_hit_that_drops_them():
    """The behaviour the shared Stress rule changed, pinned deliberately.

    This card used to pay whenever the hit would put the PC down. It now asks
    `will_spend_stress` like every other Stress cost, which releases the last
    slot only at 2 or fewer unmarked HP - and 3 unmarked HP against a 3 HP hit
    is exactly the case that falls outside it.
    """
    character = _make_character(domain_cards_loadout=[GET_BACK_UP], stress_max=2, hp_max=3)
    character.mark_stress(1)

    assert character.take_damage(12) == 3
    assert character.stress_marked == 1
    assert character.is_conscious is False


def test_get_back_up_spends_its_last_stress_once_the_pc_is_near_death():
    """At 2 or fewer unmarked HP the last slot is released, per the shared rule.

    Armor is on so the reduction has somewhere to land: 3 HP, less one for the
    free slot, less one for the card, leaves the PC standing on their last HP.
    """
    character = _make_character(
        domain_cards_loadout=[GET_BACK_UP], stress_max=2, hp_max=6, armor_max=1
    )
    character.mark_stress(1)
    character.mark_hp(4)  # 2 unmarked - near death

    assert character.take_damage(12) == 1
    assert character.stress_marked == 2
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


# --- The shared Stress rule --------------------------------------------------
#
# `will_spend_stress` is one rule for every PC Stress cost: freely, except the
# last slot, which waits until 2 or fewer HP are unmarked. Every card below asks
# it rather than deciding for itself, so it is pinned here once.


def test_a_pc_spends_stress_freely_while_a_slot_remains():
    character = _make_character(stress_max=3)

    assert character.will_spend_stress(1) is True
    character.mark_stress(1)
    assert character.will_spend_stress(1) is True


def test_a_pc_holds_their_last_stress_slot_while_healthy():
    character = _make_character(stress_max=3, hp_max=7)
    character.mark_stress(2)

    assert character.can_spend_stress(1) is True  # able
    assert character.will_spend_stress(1) is False  # unwilling


def test_a_pc_releases_their_last_stress_slot_when_near_death():
    character = _make_character(stress_max=3, hp_max=7)
    character.mark_stress(2)
    character.mark_hp(5)  # 2 unmarked

    assert character.is_near_death is True
    assert character.will_spend_stress(1) is True


def test_a_cost_bigger_than_the_pool_is_refused_outright():
    character = _make_character(stress_max=2)

    assert character.will_spend_stress(3) is False


def test_a_multi_slot_cost_is_measured_at_the_last_slot_it_would_mark():
    """Two slots free and a cost of two lands on the last one, so the rule bites."""
    character = _make_character(stress_max=3, hp_max=7)
    character.mark_stress(1)

    assert character.will_spend_stress(2) is False
    character.mark_hp(5)
    assert character.will_spend_stress(2) is True


def test_spending_stress_is_not_itself_gated_on_wanting_to():
    """`spend_stress` is the payment; whether to pay is the caller's decision."""
    character = _make_character(stress_max=2, hp_max=7)
    character.mark_stress(1)

    assert character.will_spend_stress(1) is False
    assert character.spend_stress(1) is True
    assert character.stress_marked == 2


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
    character = _make_character(domain_cards_loadout=[NOT_GOOD_ENOUGH])
    roll = _damage_roll([1, 2, 3, 6])

    with patch("content.registry.random.randint", return_value=5):
        rerolled = reroll_damage_dice(character, roll, None)

    assert rerolled.die_results == [[5, 5, 3, 6]]


def test_a_reroll_replaces_the_roll_rather_than_mutating_it():
    """Roll results are frozen dataclasses; the original has to survive intact."""
    character = _make_character(domain_cards_loadout=[NOT_GOOD_ENOUGH])
    roll = _damage_roll([1, 6])

    with patch("content.registry.random.randint", return_value=4):
        rerolled = reroll_damage_dice(character, roll, None)

    assert roll.die_results == [[1, 6]]
    assert rerolled.die_results == [[4, 6]]
    assert rerolled.total == 10


def test_a_die_is_offered_one_reroll_and_not_a_second():
    """A rerolled 2 that comes up a 1 stays a 1 - reroll, not reroll-until-happy."""
    character = _make_character(domain_cards_loadout=[NOT_GOOD_ENOUGH])
    roll = _damage_roll([2])

    with patch("content.registry.random.randint", return_value=1) as thrown:
        rerolled = reroll_damage_dice(character, roll, None)

    assert rerolled.die_results == [[1]]
    assert thrown.call_count == 1


def test_a_roll_with_nothing_to_reroll_comes_back_unchanged():
    character = _make_character(domain_cards_loadout=[NOT_GOOD_ENOUGH])
    roll = _damage_roll([3, 4, 5])

    assert reroll_damage_dice(character, roll, None) is roll


def test_a_pc_without_the_card_keeps_every_die():
    character = _make_character(domain_cards_loadout=[])
    roll = _damage_roll([1, 1, 1])

    assert reroll_damage_dice(character, roll, None) is roll


def test_the_card_answers_for_itself_whatever_die_it_is_asked_about():
    character = _make_character()

    assert not_good_enough(character, 12, 2, None) is True
    assert not_good_enough(character, 4, 3, None) is False


def test_a_reroll_happens_before_a_massive_discard_takes_the_lowest():
    """The discard is derived from the results, so it sees the new values."""
    character = _make_character(domain_cards_loadout=[NOT_GOOD_ENOUGH])
    roll = _damage_roll([1, 4, 6], drop_lowest=1)

    with patch("content.registry.random.randint", return_value=5):
        rerolled = reroll_damage_dice(character, roll, None)

    assert rerolled.dropped == [4]  # not the 1, which is now a 5
    assert rerolled.rolled_total == 11


# --- Reckless ----------------------------------------------------------------


def _make_adversary(**overrides) -> Adversary:
    defaults = dict(
        name="Test Adversary",
        tier=1,
        # Trivial on purpose: these cases are about what a card does on a hit,
        # not about whether the attack landed.
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


def _fight(party, adversaries) -> FightState:
    return FightState(
        encounter_name="test", party=list(party), adversaries=list(adversaries)
    )


def test_reckless_marks_a_stress_for_advantage():
    character = _make_character(domain_cards_loadout=[RECKLESS], stress_max=3)
    adversary = _make_adversary()
    fight = _fight([character], [adversary])

    assert reckless(character, adversary, fight) is AdvantageState.ADVANTAGE
    assert character.stress_marked == 1


def test_reckless_declines_on_the_last_slot_while_the_pc_is_healthy():
    character = _make_character(domain_cards_loadout=[RECKLESS], stress_max=2, hp_max=7)
    character.mark_stress(1)
    adversary = _make_adversary()
    fight = _fight([character], [adversary])

    assert reckless(character, adversary, fight) is None
    assert character.stress_marked == 1


def test_reckless_reaches_a_weapon_swing_through_dispatch():
    """Nothing in items/weapons.py knows this card; it asks the hook."""
    character = _make_character(domain_cards_loadout=[RECKLESS], stress_max=3)
    adversary = _make_adversary()
    fight = _fight([character], [adversary])

    assert granted_attack_advantage(character, adversary, fight) is AdvantageState.ADVANTAGE
    assert character.stress_marked == 1


def test_a_reckless_pc_rolls_their_swing_with_advantage():
    character = _make_character(
        domain_cards_loadout=[RECKLESS], stress_max=3, **NOTHING_ELSE
    )
    adversary = _make_adversary()
    fight = _fight([character], [adversary])

    random.seed(11)
    result = attack_with(character, find_weapon("Broadsword"), adversary, fight=fight)

    assert result.attack_roll.advantage_state is AdvantageState.ADVANTAGE
    assert character.stress_marked == 1


# --- Forceful Push -----------------------------------------------------------


def test_forceful_push_hits_and_leaves_the_target_vulnerable():
    character = _make_character(
        domain_cards_loadout=[FORCEFUL_PUSH], hope_max=6, **NOTHING_ELSE
    )
    character.gain_hope(3)
    adversary = _make_adversary()
    fight = _fight([character], [adversary])

    random.seed(3)
    result = forceful_push(character, adversary, fight)

    assert result.damage_roll is not None
    assert fight.has_condition(adversary, VULNERABLE) is True
    assert character.hope_marked == 2


def test_forceful_push_keeps_its_hope_when_the_target_is_already_vulnerable():
    character = _make_character(
        domain_cards_loadout=[FORCEFUL_PUSH], hope_max=6, **NOTHING_ELSE
    )
    character.gain_hope(3)
    adversary = _make_adversary()
    fight = _fight([character], [adversary])
    fight.apply_condition(adversary, Condition(name=VULNERABLE))

    random.seed(3)
    forceful_push(character, adversary, fight)

    assert character.hope_marked == 3


def test_forceful_push_keeps_its_hope_with_none_banked():
    character = _make_character(
        domain_cards_loadout=[FORCEFUL_PUSH], hope_max=6, **NOTHING_ELSE
    )
    adversary = _make_adversary()
    fight = _fight([character], [adversary])

    random.seed(3)
    forceful_push(character, adversary, fight)

    assert fight.has_condition(adversary, VULNERABLE) is False


def test_forceful_push_declines_for_a_pc_carrying_no_weapon():
    character = _make_character(domain_cards_loadout=[FORCEFUL_PUSH], primary_weapon="")
    adversary = _make_adversary()
    fight = _fight([character], [adversary])

    assert forceful_push(character, adversary, fight) is None


def _duality(hope: int, fear: int, difficulty: int = 5) -> DualityRollResult:
    return DualityRollResult(
        hope_die_result=hope,
        fear_die_result=fear,
        modifier=0,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=difficulty,
    )


def test_the_extra_die_rides_a_success_with_hope():
    character = _make_character(domain_cards_loadout=[FORCEFUL_PUSH])
    adversary = _make_adversary()
    fight = _fight([character], [adversary])
    fight.set_token(character, "Forceful Push in flight", 1)

    dice = forceful_push_momentum(character, adversary, _duality(10, 4), fight)

    assert [(group.count, group.sides) for group in dice] == [(1, 6)]
    assert dice[0].discardable is False


def test_the_extra_die_does_not_ride_a_success_with_fear():
    character = _make_character(domain_cards_loadout=[FORCEFUL_PUSH])
    adversary = _make_adversary()
    fight = _fight([character], [adversary])
    fight.set_token(character, "Forceful Push in flight", 1)

    assert forceful_push_momentum(character, adversary, _duality(4, 10), fight) == []


def test_the_extra_die_does_not_ride_a_critical():
    """A crit is its own outcome, not a success with Hope - the standing reading."""
    character = _make_character(domain_cards_loadout=[FORCEFUL_PUSH])
    adversary = _make_adversary()
    fight = _fight([character], [adversary])
    fight.set_token(character, "Forceful Push in flight", 1)

    assert forceful_push_momentum(character, adversary, _duality(7, 7), fight) == []


def test_the_extra_die_never_rides_an_ordinary_swing():
    """Without the token this is any other attack, and the card adds nothing."""
    character = _make_character(domain_cards_loadout=[FORCEFUL_PUSH])
    adversary = _make_adversary()
    fight = _fight([character], [adversary])

    assert forceful_push_momentum(character, adversary, _duality(10, 4), fight) == []


def test_the_token_is_cleared_once_the_push_resolves():
    character = _make_character(domain_cards_loadout=[FORCEFUL_PUSH])
    adversary = _make_adversary()
    fight = _fight([character], [adversary])

    random.seed(3)
    forceful_push(character, adversary, fight)

    assert fight.token_count(character, "Forceful Push in flight") == 0


# --- Bold Presence -----------------------------------------------------------


def test_bold_presence_refuses_the_first_condition_that_would_land():
    character = _make_character(domain_cards_loadout=[BOLD_PRESENCE])
    fight = _fight([character], [])

    fight.apply_condition(character, Condition(name=VULNERABLE))

    assert fight.has_condition(character, VULNERABLE) is False


def test_bold_presence_only_dodges_once_per_rest():
    character = _make_character(domain_cards_loadout=[BOLD_PRESENCE])
    fight = _fight([character], [])

    fight.apply_condition(character, Condition(name=VULNERABLE))
    fight.apply_condition(character, Condition(name=RESTRAINED))

    assert fight.has_condition(character, VULNERABLE) is False
    assert fight.has_condition(character, RESTRAINED) is True


def test_a_refresh_of_a_condition_already_held_is_not_a_dodge():
    """"When you would gain a condition" - a PC who already has it isn't gaining one."""
    character = _make_character(domain_cards_loadout=[BOLD_PRESENCE])
    fight = _fight([character], [])
    fight.conditions[(id(character), RESTRAINED)] = Condition(name=RESTRAINED)

    fight.apply_condition(character, Condition(name=RESTRAINED))

    assert fight.has_condition(character, RESTRAINED) is True
    assert fight.can_use_once_per_rest(character, BOLD_PRESENCE) is True


def test_a_pc_without_the_card_gains_the_condition():
    character = _make_character(domain_cards_loadout=[])
    fight = _fight([character], [])

    fight.apply_condition(character, Condition(name=VULNERABLE))

    assert fight.has_condition(character, VULNERABLE) is True


def test_bold_presence_declines_outside_a_fight():
    """The per-rest use lives on the fight, so there is nothing to spend."""
    character = _make_character(domain_cards_loadout=[BOLD_PRESENCE])

    assert bold_presence(character, Condition(name=VULNERABLE), None) is False


# --- Assessed, but used between fights ---------------------------------------


def test_a_soldiers_bond_is_recorded_as_an_out_of_combat_ability():
    """Not a dismissal: it is the to-do list for sequenced encounters."""
    assessment = assess(A_SOLDIERS_BOND)

    assert assessment.status is Status.OUT_OF_COMBAT
    assert assessment.reason  # a state that records a decision has to say why


def test_out_of_combat_content_is_neither_dismissed_nor_missing():
    assessment = assess(A_SOLDIERS_BOND)

    assert assessment.status.is_dismissed is False
    assert assessment.status is not Status.UNIMPLEMENTED


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
