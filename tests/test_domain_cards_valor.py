"""Tests for the Valor domain cards.

The oldest is a guard - one PC stepping in front of another - which makes it easy
to test honestly: a party goes in and the interception comes out. The later ones
reach a roll, and stay deterministic by constructing the result they need or by
giving the target a Difficulty of 0 or 1 so that whether the attack landed is
never what a case turns on.

One piece of shared machinery is what several of these are really about:

* **`PlayerCharacter.gain_trait_bonus`**, with `trait_bonuses` beside it, is how
  Full Surge's "+2 to all of your character traits" reaches everything that reads
  a trait while leaving the sheet's authored numbers recoverable.
* **`action_roll_advantage`** exists rather than Inevitable registering on
  `attack_advantage`, because the card's die has to reach a **Spellcast Roll** as
  well as a weapon swing.

The rules readings these pin down are the ones the card module documents as
choices rather than as SRD text - that I Am Your Shield swaps the target before
the attack is rolled, that a critical is not a success with Hope, that Rise Up
fires on **any** damage that marks HP, that Shrug It Off fires on Severe damage
alone and vaults itself on a low d6, and that Ground Pound declines below two
targets. If any of those change, these are the tests that should fail.

The level 10 pair are both tested through the **real pipeline** rather than by
calling the card: Unbreakable through `mark_hp_and_check_death`, which is the only
route that offers a ward at all - and which is also how the declared gap is pinned,
since a Stress overflow carries no fight and so reaches nothing - and Unyielding
Armor through `apply_on_damaged`, which is what carries the fact that a slot was
marked.
"""

import random
from contextlib import contextmanager
from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.policy import _shield
from combat.rest import Rest
from combat.results import AttackResult
from combat.state import FightState
from content import (
    Status,
    apply_on_damaged,
    apply_on_roll,
    assess,
    find_shielder,
    granted_action_roll_advantage,
    soften_damage,
    take_action,
    use_free_abilities,
)
from content.conditions import ON_A_GM_TURN, RESTRAINED, VULNERABLE, Condition
from content.spellcast import spellcast
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from domain_cards.valor import (
    FULL_SURGE,
    HOLD_THE_LINE,
    HOLD_THE_LINE_FEAR,
    LEAD_BY_EXAMPLE,
    LEAD_BY_EXAMPLE_MARK,
    LINE_HELD,
    hold_the_line,
    lead_by_example,
    lead_by_example_lifts,
    FULL_SURGE_BONUS,
    FULL_SURGE_STRESS,
    GROUND_POUND,
    GROUND_POUND_WORTH_IT,
    INEVITABLE,
    INEVITABLE_OWED,
    RISE_UP,
    SHRUG_IT_OFF,
    SHRUG_IT_OFF_VAULTED,
    UNBREAKABLE,
    UNBREAKABLE_VAULTED,
    UNYIELDING_ARMOR,
    VALOR_TOUCHED,
    bold_presence,
    forceful_push,
    forceful_push_momentum,
    i_am_your_shield,
)
from items.registry import find_weapon
from items.weapons import attack_with

I_AM_YOUR_SHIELD = "I Am Your Shield"
FORCEFUL_PUSH = "Forceful Push"
BOLD_PRESENCE = "Bold Presence"
A_SOLDIERS_BOND = "A Soldier's Bond"

# The default sheet names a real ancestry and community, which carry content of
# their own. That's fine for the guard cases, which measure HP; it isn't for a
# case counting Hope or Stress to the point, since a rider that spends either
# would land in the same total. These blank both out for the same reason the
# defaults blank out the class and subclass.
NOTHING_ELSE = dict(ancestry="Unwritten Ancestry", community="Unwritten Community")


def _make_level_1_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=1,
        # Names nothing has implemented, on purpose. A class or subclass with
        # damage responses of its own would stack with the card these tests are
        # measuring, and the card's own arithmetic would stop being what came out.
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


def _make_level_6_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=6,
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 0,
            "strength": 2,
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


def _make_level_7_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=7,
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
        # No armor, deliberately: half of these cases go through `soften_damage`,
        # and an armor feature registered on the same hook would sit in the middle
        # of what is being measured.
        armor_item="",
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
            "agility": 1,
            "strength": 2,
            "finesse": 1,
            "instinct": 1,
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


# --- I Am Your Shield --------------------------------------------------------


def test_an_ally_steps_in_front_of_the_pc_who_is_closer_to_going_down():
    shielder = _make_level_1_pc(name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD])
    hurt = _make_level_1_pc(name="Ally", hp_max=7)
    hurt.mark_hp(5)  # 2 unmarked HP left

    interception = find_shielder(hurt, [shielder, hurt])

    assert interception is not None
    assert interception.shielder is shielder
    assert interception.card == I_AM_YOUR_SHIELD
    assert shielder.stress_marked == 1


def test_nobody_steps_in_for_a_pc_who_is_no_worse_off():
    shielder = _make_level_1_pc(name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD])
    unhurt = _make_level_1_pc(name="Ally")

    assert find_shielder(unhurt, [shielder, unhurt]) is None
    assert shielder.stress_marked == 0


def test_a_shielder_on_their_last_hp_does_not_step_in():
    """Moving the hit onto someone who also drops gains the party nothing."""
    shielder = _make_level_1_pc(
        name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD], hp_max=7
    )
    shielder.mark_hp(6)
    hurt = _make_level_1_pc(name="Ally", hp_max=7)
    hurt.mark_hp(6)

    assert find_shielder(hurt, [shielder, hurt]) is None


def test_a_shielder_with_no_stress_left_cannot_step_in():
    shielder = _make_level_1_pc(
        name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD], stress_max=1
    )
    shielder.mark_stress(1)
    hurt = _make_level_1_pc(name="Ally", hp_max=7)
    hurt.mark_hp(5)

    assert find_shielder(hurt, [shielder, hurt]) is None


def test_a_solo_pc_is_never_shielded_by_themselves():
    """The card needs an ally, so with a party of one it can never fire."""
    alone = _make_level_1_pc(
        name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD], hp_max=7
    )
    alone.mark_hp(6)

    assert find_shielder(alone, [alone]) is None
    assert alone.stress_marked == 0


def test_the_card_reports_whether_it_stepped_in():
    """The card's own contract, independent of how the registry calls it."""
    shielder = _make_level_1_pc(hp_max=7)
    hurt = _make_level_1_pc(hp_max=7)
    hurt.mark_hp(5)

    assert i_am_your_shield(shielder, hurt) is True
    assert i_am_your_shield(shielder, shielder) is False


def test_the_turn_policy_moves_the_attack_onto_the_shielder():
    """combat/policy.py knows no card by name; it asks and takes the answer."""
    shielder = _make_level_1_pc(name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD])
    hurt = _make_level_1_pc(name="Ally", hp_max=7)
    hurt.mark_hp(5)
    state = _state([shielder, hurt], [])

    assert _shield(hurt, state) is shielder


def test_an_unconscious_ally_never_steps_in():
    """The policy filters to conscious PCs before the cards are asked at all."""
    shielder = _make_level_1_pc(name="Kael", domain_cards_loadout=[I_AM_YOUR_SHIELD])
    shielder.unconscious = True
    hurt = _make_level_1_pc(name="Ally", hp_max=7)
    hurt.mark_hp(5)
    state = _state([shielder, hurt], [])

    assert _shield(hurt, state) is hurt


# --- Forceful Push -----------------------------------------------------------


def test_forceful_push_hits_and_leaves_the_target_vulnerable():
    character = _make_level_1_pc(
        domain_cards_loadout=[FORCEFUL_PUSH], hope_max=6, **NOTHING_ELSE
    )
    character.gain_hope(3)
    adversary = _make_target()
    fight = _state([character], [adversary])

    random.seed(3)
    result = forceful_push(character, adversary, fight)

    assert result.damage_roll is not None
    assert fight.has_condition(adversary, VULNERABLE) is True
    assert character.hope_marked == 2


def test_forceful_push_keeps_its_hope_when_the_target_is_already_vulnerable():
    character = _make_level_1_pc(
        domain_cards_loadout=[FORCEFUL_PUSH], hope_max=6, **NOTHING_ELSE
    )
    character.gain_hope(3)
    adversary = _make_target()
    fight = _state([character], [adversary])
    fight.apply_condition(adversary, Condition(name=VULNERABLE))

    random.seed(3)
    forceful_push(character, adversary, fight)

    assert character.hope_marked == 3


def test_forceful_push_keeps_its_hope_with_none_banked():
    character = _make_level_1_pc(
        domain_cards_loadout=[FORCEFUL_PUSH], hope_max=6, **NOTHING_ELSE
    )
    adversary = _make_target()
    fight = _state([character], [adversary])

    random.seed(3)
    forceful_push(character, adversary, fight)

    assert fight.has_condition(adversary, VULNERABLE) is False


def test_forceful_push_declines_for_a_pc_carrying_no_weapon():
    character = _make_level_1_pc(domain_cards_loadout=[FORCEFUL_PUSH], primary_weapon="")
    adversary = _make_target()
    fight = _state([character], [adversary])

    assert forceful_push(character, adversary, fight) is None


def test_the_extra_die_rides_a_success_with_hope():
    character = _make_level_1_pc(domain_cards_loadout=[FORCEFUL_PUSH])
    adversary = _make_target()
    fight = _state([character], [adversary])
    fight.set_token(character, "Forceful Push in flight", 1)

    dice = forceful_push_momentum(character, adversary, _roll(10, 4, 5), fight)

    assert [(group.count, group.sides) for group in dice] == [(1, 6)]
    assert dice[0].discardable is False


def test_the_extra_die_does_not_ride_a_success_with_fear():
    character = _make_level_1_pc(domain_cards_loadout=[FORCEFUL_PUSH])
    adversary = _make_target()
    fight = _state([character], [adversary])
    fight.set_token(character, "Forceful Push in flight", 1)

    assert forceful_push_momentum(character, adversary, _roll(4, 10, 5), fight) == []


def test_the_extra_die_does_not_ride_a_critical():
    """A crit is its own outcome, not a success with Hope - the standing reading."""
    character = _make_level_1_pc(domain_cards_loadout=[FORCEFUL_PUSH])
    adversary = _make_target()
    fight = _state([character], [adversary])
    fight.set_token(character, "Forceful Push in flight", 1)

    assert forceful_push_momentum(character, adversary, _roll(7, 7, 5), fight) == []


def test_the_extra_die_never_rides_an_ordinary_swing():
    """Without the token this is any other attack, and the card adds nothing."""
    character = _make_level_1_pc(domain_cards_loadout=[FORCEFUL_PUSH])
    adversary = _make_target()
    fight = _state([character], [adversary])

    assert forceful_push_momentum(character, adversary, _roll(10, 4, 5), fight) == []


def test_the_token_is_cleared_once_the_push_resolves():
    character = _make_level_1_pc(domain_cards_loadout=[FORCEFUL_PUSH])
    adversary = _make_target()
    fight = _state([character], [adversary])

    random.seed(3)
    forceful_push(character, adversary, fight)

    assert fight.token_count(character, "Forceful Push in flight") == 0


# --- Bold Presence -----------------------------------------------------------


def test_bold_presence_refuses_the_first_condition_that_would_land():
    character = _make_level_1_pc(domain_cards_loadout=[BOLD_PRESENCE])
    fight = _state([character], [])

    fight.apply_condition(character, Condition(name=VULNERABLE))

    assert fight.has_condition(character, VULNERABLE) is False


def test_bold_presence_only_dodges_once_per_rest():
    character = _make_level_1_pc(domain_cards_loadout=[BOLD_PRESENCE])
    fight = _state([character], [])

    fight.apply_condition(character, Condition(name=VULNERABLE))
    fight.apply_condition(character, Condition(name=RESTRAINED))

    assert fight.has_condition(character, VULNERABLE) is False
    assert fight.has_condition(character, RESTRAINED) is True


def test_a_refresh_of_a_condition_already_held_is_not_a_dodge():
    """"When you would gain a condition" - a PC who already has it isn't gaining one."""
    character = _make_level_1_pc(domain_cards_loadout=[BOLD_PRESENCE])
    fight = _state([character], [])
    fight.conditions[(id(character), RESTRAINED)] = Condition(name=RESTRAINED)

    fight.apply_condition(character, Condition(name=RESTRAINED))

    assert fight.has_condition(character, RESTRAINED) is True
    assert fight.can_use_once_per_rest(character, BOLD_PRESENCE) is True


def test_a_pc_without_the_card_gains_the_condition():
    character = _make_level_1_pc(domain_cards_loadout=[])
    fight = _state([character], [])

    fight.apply_condition(character, Condition(name=VULNERABLE))

    assert fight.has_condition(character, VULNERABLE) is True


def test_bold_presence_declines_outside_a_fight():
    """The per-rest use lives on the fight, so there is nothing to spend."""
    character = _make_level_1_pc(domain_cards_loadout=[BOLD_PRESENCE])

    assert bold_presence(character, Condition(name=VULNERABLE), None) is False


# --- Inevitable --------------------------------------------------------------


def test_a_failed_action_roll_owes_the_next_one_an_advantage_die():
    character = _make_level_6_pc(domain_cards_loadout=[INEVITABLE])
    fight = _state([character], [])

    apply_on_roll(character, _roll(3, 4, difficulty=15), fight)

    assert fight.token_count(character, INEVITABLE_OWED) == 1


def test_a_successful_action_roll_owes_nothing():
    character = _make_level_6_pc(domain_cards_loadout=[INEVITABLE])
    fight = _state([character], [])

    apply_on_roll(character, _roll(11, 10, difficulty=15), fight)

    assert fight.token_count(character, INEVITABLE_OWED) == 0


def test_a_roll_with_no_difficulty_is_not_a_failure():
    """`is_success` is None there, which must not read as False."""
    character = _make_level_6_pc(domain_cards_loadout=[INEVITABLE])
    fight = _state([character], [])

    apply_on_roll(character, _roll(3, 4), fight)

    assert fight.token_count(character, INEVITABLE_OWED) == 0


def test_the_advantage_die_is_spent_on_being_asked():
    character = _make_level_6_pc(domain_cards_loadout=[INEVITABLE])
    fight = _state([character], [])
    fight.set_token(character, INEVITABLE_OWED, 1)

    granted = granted_action_roll_advantage(character, None, fight)

    assert granted is AdvantageState.ADVANTAGE
    assert fight.token_count(character, INEVITABLE_OWED) == 0


def test_nothing_is_granted_when_nothing_is_owed():
    character = _make_level_6_pc(domain_cards_loadout=[INEVITABLE])
    fight = _state([character], [])

    assert granted_action_roll_advantage(character, None, fight) is AdvantageState.NONE


def test_the_advantage_die_reaches_a_weapon_swing():
    """The hook is folded into `attack_with` beside the attack-only one."""
    random.seed(3)
    character = _make_level_6_pc(domain_cards_loadout=[INEVITABLE])
    target = _make_adversary()
    fight = _state([character], [target])
    fight.set_token(character, INEVITABLE_OWED, 1)

    result = attack_with(character, find_weapon("Broadsword"), target, fight=fight)

    assert result.attack_roll.advantage_state is AdvantageState.ADVANTAGE
    assert fight.token_count(character, INEVITABLE_OWED) == 0


def test_the_advantage_die_reaches_a_spellcast_roll():
    """The whole reason for a hook of its own - `attack_advantage` never gets here."""
    random.seed(3)
    character = _make_level_6_pc(domain_cards_loadout=[INEVITABLE])
    target = _make_adversary()
    fight = _state([character], [target])
    fight.set_token(character, INEVITABLE_OWED, 1)

    roll = spellcast(character, target, fight)

    assert roll.advantage_state is AdvantageState.ADVANTAGE
    assert fight.token_count(character, INEVITABLE_OWED) == 0


def test_a_pc_without_the_card_rolls_flat():
    random.seed(3)
    character = _make_level_6_pc(domain_cards_loadout=[])
    target = _make_adversary()
    fight = _state([character], [target])

    assert spellcast(character, target, fight).advantage_state is AdvantageState.NONE


# --- Rise Up -----------------------------------------------------------------


def test_rise_up_clears_a_stress_off_a_wound():
    character = _make_level_6_pc(domain_cards_loadout=[RISE_UP])
    character.mark_stress(3)
    fight = _state([character], [])

    apply_on_damaged(character, 12, 2, fight)

    assert character.stress_marked == 2


def test_rise_up_ignores_a_hit_that_marked_no_hp():
    """An Armor Slot swallowing a hit whole is not a wound the card sees."""
    character = _make_level_6_pc(domain_cards_loadout=[RISE_UP])
    character.mark_stress(3)
    fight = _state([character], [])

    apply_on_damaged(character, 12, 0, fight)

    assert character.stress_marked == 3


def test_rise_up_fires_on_damage_from_anything_at_all():
    """The user's ruling: everything that marks damage here is an attack.

    Nothing is spotlighted, so this wound has no attacker attached - a burn, an
    area spell, the party's own. The card fires anyway, and that is the reading
    rather than an oversight.
    """
    character = _make_level_6_pc(domain_cards_loadout=[RISE_UP])
    character.mark_stress(1)
    fight = _state([character], [])
    assert fight.spotlighted is None

    apply_on_damaged(character, 5, 1, fight)

    assert character.stress_marked == 0


def test_rise_up_declares_its_threshold_clause_as_a_gap():
    """A sheet carries thresholds resolved, so running the bonus would double it."""
    assert assess(RISE_UP).is_partial is True
    assert "Severe threshold" in " ".join(assess(RISE_UP).unmodelled)


# --- Shrug It Off ------------------------------------------------------------


def test_a_severe_hit_is_reduced_by_a_threshold_for_a_stress():
    holder = _make_level_7_pc(domain_cards_loadout=[SHRUG_IT_OFF])
    fight = _rested_state([holder], [])

    with patch("domain_cards.valor.random.randint", return_value=6):
        assert soften_damage(holder, 25, 3, fight) == 2

    assert holder.stress_marked == 1
    assert fight.token_count(holder, SHRUG_IT_OFF_VAULTED) == 0


def test_a_low_die_vaults_the_card_for_the_rest_of_the_fight():
    holder = _make_level_7_pc(domain_cards_loadout=[SHRUG_IT_OFF])
    fight = _rested_state([holder], [])

    with patch("domain_cards.valor.random.randint", return_value=3):
        assert soften_damage(holder, 25, 3, fight) == 2
    assert fight.token_count(holder, SHRUG_IT_OFF_VAULTED) == 1

    # Vaulted, so a second Severe hit gets nothing and costs nothing.
    with patch("domain_cards.valor.random.randint", return_value=6):
        assert soften_damage(holder, 25, 3, fight) == 3
    assert holder.stress_marked == 1


def test_a_major_hit_is_not_shrugged_off():
    """Ruled: Severe damage only, read off the amount rather than the HP."""
    holder = _make_level_7_pc(domain_cards_loadout=[SHRUG_IT_OFF])
    fight = _rested_state([holder], [])

    assert soften_damage(holder, 12, 2, fight) == 2
    assert holder.stress_marked == 0


def test_a_hit_armor_took_to_nothing_buys_nothing():
    holder = _make_level_7_pc(domain_cards_loadout=[SHRUG_IT_OFF])
    fight = _rested_state([holder], [])

    assert soften_damage(holder, 25, 0, fight) == 0
    assert holder.stress_marked == 0


# --- Valor-Touched -----------------------------------------------------------


def test_a_wound_that_marked_no_armor_slot_clears_one():
    holder = _make_level_7_pc(domain_cards_loadout=[VALOR_TOUCHED], armor_max=2)
    fight = _rested_state([holder], [])
    holder.armor_marked = 2

    apply_on_damaged(holder, 12, 2, fight, False)

    assert holder.armor_marked == 1


def test_a_wound_that_did_mark_an_armor_slot_clears_nothing():
    holder = _make_level_7_pc(domain_cards_loadout=[VALOR_TOUCHED], armor_max=2)
    fight = _rested_state([holder], [])
    holder.armor_marked = 2

    apply_on_damaged(holder, 12, 2, fight, True)

    assert holder.armor_marked == 2


def test_a_hit_that_marked_no_hp_clears_nothing():
    holder = _make_level_7_pc(domain_cards_loadout=[VALOR_TOUCHED], armor_max=2)
    fight = _rested_state([holder], [])
    holder.armor_marked = 2

    apply_on_damaged(holder, 12, 0, fight, False)

    assert holder.armor_marked == 2


def test_direct_damage_reaches_the_card_through_the_real_pipeline():
    """The edge `armor_unmarked == 0` would have got wrong.

    Slots are free and none is spent, so the card should fire - which is why the
    fact is carried rather than inferred afterwards.
    """
    holder = _make_level_7_pc(domain_cards_loadout=[VALOR_TOUCHED], armor_max=2)
    fight = _rested_state([holder], [])
    holder.armor_marked = 1

    holder.take_damage(25, fight, direct=True)

    assert holder.hp_marked == 3
    assert holder.armor_marked == 0


def test_an_ordinary_hit_marks_the_slot_and_the_card_stays_quiet():
    holder = _make_level_7_pc(domain_cards_loadout=[VALOR_TOUCHED], armor_max=2)
    fight = _rested_state([holder], [])
    holder.armor_marked = 1

    holder.take_damage(25, fight)

    # The free slot went in, so the refund correctly does not.
    assert holder.armor_marked == 2
    assert holder.hp_marked == 2


# --- Full Surge --------------------------------------------------------------


def test_full_surge_raises_every_trait():
    pc = _make_level_8_pc(domain_cards_loadout=[FULL_SURGE])
    fight = _rested_state([pc], [_make_adversary()])
    before = dict(pc.traits)

    assert use_free_abilities(pc, fight, 1) == [FULL_SURGE]

    assert all(pc.traits[t] == before[t] + FULL_SURGE_BONUS for t in before)
    assert pc.stress_marked == FULL_SURGE_STRESS


def test_full_surge_records_what_it_granted():
    """The record is what keeps the sheet's authored numbers recoverable."""
    pc = _make_level_8_pc(domain_cards_loadout=[FULL_SURGE])
    fight = _rested_state([pc], [_make_adversary()])

    use_free_abilities(pc, fight, 1)

    assert set(pc.trait_bonuses) == set(pc.traits)
    assert all(bonus == FULL_SURGE_BONUS for bonus in pc.trait_bonuses.values())


def test_full_surge_declines_when_the_three_stress_cannot_be_paid():
    pc = _make_level_8_pc(domain_cards_loadout=[FULL_SURGE], stress_marked=4)
    fight = _rested_state([pc], [_make_adversary()])

    assert use_free_abilities(pc, fight, 1) == []
    assert pc.trait_bonuses == {}


def test_full_surge_is_once_per_long_rest():
    pc = _make_level_8_pc(domain_cards_loadout=[FULL_SURGE])
    fight = _rested_state([pc], [_make_adversary()])

    assert use_free_abilities(pc, fight, 1) == [FULL_SURGE]
    assert use_free_abilities(pc, fight, 1) == []


def test_a_surged_trait_reaches_a_roll():
    """`traits` is the effective mapping, so every reader picks the bonus up."""
    pc = _make_level_8_pc(domain_cards_loadout=[FULL_SURGE])
    fight = _rested_state([pc], [_make_adversary()])

    use_free_abilities(pc, fight, 1)

    assert pc.traits["strength"] == 2 + FULL_SURGE_BONUS


# --- Ground Pound ------------------------------------------------------------


def _pounding(adversaries: int, thresholds: int = 100, **overrides):
    """A field of `adversaries`. **Six or more** for the band to reach two.

    Very Close reaches a third of the field held to a cap of two, so a field of
    four reaches exactly one and every cast would decline for the wrong reason.
    """
    pc = _make_level_8_pc(domain_cards_loadout=[GROUND_POUND], **overrides)
    field = [
        _make_adversary(
            name=f"Dummy {index}",
            major_threshold=thresholds,
            severe_threshold=thresholds * 10,
        )
        for index in range(adversaries)
    ]
    return pc, field, _rested_state([pc], field)


def test_ground_pound_spends_two_hope_and_lands_on_the_band():
    pc, field, fight = _pounding(6)

    result = take_action(pc, field[0], fight)

    assert result is not None
    assert pc.hope_marked == 4
    assert sum(1 for a in field if a.hp_marked > 0) >= GROUND_POUND_WORTH_IT


def test_ground_pound_declines_below_two_targets():
    pc, field, fight = _pounding(1)

    assert take_action(pc, field[0], fight) is None
    assert pc.hope_marked == 6


def test_ground_pound_declines_without_the_hope():
    pc, field, fight = _pounding(6, hope_marked=1)

    assert take_action(pc, field[0], fight) is None


def _pound_with(saved: bool, thresholds: int):
    """One Ground Pound with a fixed 40 damage and every Reaction Roll going one way."""
    pc, field, fight = _pounding(6, thresholds=thresholds)
    fixed = DamageRollResult(
        dice_groups=[DiceGroup(count=4, sides=10)],
        die_results=[[10, 10, 10, 10]],
        modifier=0,
    )
    with patch("domain_cards.valor.roll_damage", return_value=fixed), patch(
        "domain_cards.valor.roll_d20"
    ) as rolled:
        rolled.return_value.is_success = saved
        return take_action(pc, field[0], fight)


def test_a_target_that_saves_takes_half():
    """40 against a Major of 30: the full hit marks 2 HP, half of it marks 1."""
    saved = _pound_with(saved=True, thresholds=30)
    struck = _pound_with(saved=False, thresholds=30)

    assert saved is not None and struck is not None
    assert saved.hp_marked * 2 == struck.hp_marked


# --- Hold the Line -----------------------------------------------------------


@contextmanager
def _bunched():
    """Every band at its best reach, so a case is about the card not the spread."""
    with patch("content.aoe.random.random", return_value=0.0):
        yield


def _holding(adversaries: int, fear: int = 6, **overrides):
    holder = _make_level_8_pc(
        level=9, domain_cards_loadout=[HOLD_THE_LINE], **overrides
    )
    field = [_make_adversary(name=f"Dummy {index}") for index in range(adversaries)]
    return holder, field, _rested_state([holder], field, fear=fear)


def test_the_line_restrains_what_the_band_reaches():
    holder, field, fight = _holding(6)

    with _bunched():
        assert hold_the_line(holder, fight) is True

    assert any(fight.has_condition(a, RESTRAINED) for a in field)
    assert holder.hope_marked == 5


def test_the_gm_pays_two_fear_to_break_one_free():
    """Twice what every other party-applied condition costs to shake off."""
    holder, field, fight = _holding(6, fear=6)

    with _bunched():
        hold_the_line(holder, fight)

    held = [a for a in field if fight.has_condition(a, RESTRAINED)][0]
    ended = fight.expire_conditions(held, ON_A_GM_TURN)

    assert RESTRAINED in ended
    assert fight.fear == 6 - HOLD_THE_LINE_FEAR


def test_a_gm_who_cannot_afford_it_watches_them_stand_there():
    holder, field, fight = _holding(6, fear=1)

    with _bunched():
        hold_the_line(holder, fight)

    held = [a for a in field if fight.has_condition(a, RESTRAINED)][0]

    assert fight.expire_conditions(held, ON_A_GM_TURN) == []
    assert fight.fear == 1


def test_the_stance_is_taken_once():
    holder, field, fight = _holding(6)

    with _bunched():
        assert hold_the_line(holder, fight) is True
        assert hold_the_line(holder, fight) is False
    assert fight.token_count(holder, LINE_HELD) == 1


def test_the_line_declines_without_a_hope():
    holder, field, fight = _holding(6, hope_marked=0)

    with _bunched():
        assert hold_the_line(holder, fight) is False
    assert not any(fight.has_condition(a, RESTRAINED) for a in field)


def test_the_line_declines_when_everything_it_reaches_is_already_held():
    holder, field, fight = _holding(1)
    fight.apply_condition(field[0], Condition(name=RESTRAINED))

    with _bunched():
        assert hold_the_line(holder, fight) is False
    assert holder.hope_marked == 6


# --- Lead by Example ---------------------------------------------------------


def _leading(**overrides):
    holder = _make_level_8_pc(
        level=9, name="Leader", domain_cards_loadout=[LEAD_BY_EXAMPLE], **overrides
    )
    ally = _make_level_8_pc(level=9, name="Ally")
    target = _make_adversary()
    return holder, ally, target, _rested_state([holder, ally], [target])


def _a_hit() -> AttackResult:
    return AttackResult(
        attack_roll=_roll(9, 4, 5),
        damage_roll=DamageRollResult(
            dice_groups=[DiceGroup(count=1, sides=4)],
            die_results=[[4]],
            modifier=0,
        ),
        hp_marked=1,
    )


def test_the_encouragement_costs_a_stress_and_marks_the_adversary():
    holder, ally, target, fight = _leading()

    lead_by_example(holder, target, _a_hit(), fight)

    assert holder.stress_marked == 1
    assert fight.token_count(target, LEAD_BY_EXAMPLE_MARK) == 1


def test_the_next_ally_to_hit_clears_a_stress():
    holder, ally, target, fight = _leading()
    ally.mark_stress(2)
    lead_by_example(holder, target, _a_hit(), fight)

    lead_by_example_lifts(holder, ally, target, _a_hit(), fight)

    assert ally.stress_marked == 1
    assert fight.token_count(target, LEAD_BY_EXAMPLE_MARK) == 0


def test_an_ally_with_nothing_to_clear_gains_a_hope():
    """The general rule set for Gore and Glory, read here for the second time."""
    holder, ally, target, fight = _leading()
    ally.spend_hope(6)
    lead_by_example(holder, target, _a_hit(), fight)

    lead_by_example_lifts(holder, ally, target, _a_hit(), fight)

    assert ally.hope_marked == 1


def test_the_holder_never_collects_their_own_encouragement():
    holder, ally, target, fight = _leading()
    holder.mark_stress(1)
    lead_by_example(holder, target, _a_hit(), fight)

    lead_by_example_lifts(holder, holder, target, _a_hit(), fight)

    assert holder.stress_marked == 2  # the one the card cost, and no clear
    assert fight.token_count(target, LEAD_BY_EXAMPLE_MARK) == 1


def test_the_encouragement_pays_out_once():
    holder, ally, target, fight = _leading()
    ally.mark_stress(2)
    lead_by_example(holder, target, _a_hit(), fight)

    lead_by_example_lifts(holder, ally, target, _a_hit(), fight)
    lead_by_example_lifts(holder, ally, target, _a_hit(), fight)

    assert ally.stress_marked == 1


def test_it_declines_against_a_target_the_hit_just_defeated():
    holder, ally, target, fight = _leading()
    target.hp_marked = target.hp_max

    lead_by_example(holder, target, _a_hit(), fight)

    assert holder.stress_marked == 0


# --- Unbreakable -------------------------------------------------------------


def _unbreaking(**overrides):
    holder = _make_level_8_pc(
        level=10, domain_cards_loadout=[UNBREAKABLE], **overrides
    )
    return holder, _rested_state([holder], [])


def test_the_last_hit_is_answered_with_a_d6_instead_of_a_death_move():
    holder, fight = _unbreaking()
    holder.hp_marked = holder.hp_max - 1

    with patch("domain_cards.valor.random.randint", return_value=4):
        holder.mark_hp_and_check_death(1, fight)

    assert holder.is_conscious is True
    assert holder.death_moves == 0
    assert holder.hp_marked == holder.hp_max - 4


def test_the_card_is_spent_for_good_either_way():
    holder, fight = _unbreaking()
    holder.hp_marked = holder.hp_max - 1

    with patch("domain_cards.valor.random.randint", return_value=6):
        holder.mark_hp_and_check_death(1, fight)
    assert fight.token_count(holder, UNBREAKABLE_VAULTED) == 1

    holder.hp_marked = holder.hp_max - 1
    holder.mark_hp_and_check_death(1, fight)

    assert holder.is_conscious is False
    assert holder.death_moves == 1


def test_it_wards_nobody_but_its_own_holder():
    """Life Ward is the party-wide one; this card says 'you'."""
    holder = _make_level_8_pc(
        level=10, name="Holder", domain_cards_loadout=[UNBREAKABLE]
    )
    ally = _make_level_8_pc(level=10, name="Ally")
    fight = _rested_state([holder, ally], [])
    ally.hp_marked = ally.hp_max - 1

    ally.mark_hp_and_check_death(1, fight)

    assert ally.is_conscious is False
    assert fight.token_count(holder, UNBREAKABLE_VAULTED) == 0


def test_a_stress_overflow_never_reaches_the_ward():
    """`mark_stress` carries no fight, which is the gap the card declares."""
    holder, fight = _unbreaking()
    holder.hp_marked = holder.hp_max - 1
    holder.stress_marked = holder.stress_max

    holder.mark_stress(1)

    assert holder.is_conscious is False


# --- Unyielding Armor --------------------------------------------------------


def _unyielding(**overrides):
    holder = _make_level_8_pc(
        level=10, domain_cards_loadout=[UNYIELDING_ARMOR], armor_max=2, **overrides
    )
    return holder, _rested_state([holder], [])


def test_a_six_puts_the_armor_slot_back():
    holder, fight = _unyielding()
    holder.armor_marked = 1

    with patch("domain_cards.valor.random.randint", side_effect=[1, 1, 6]):
        apply_on_damaged(holder, 12, 1, fight, True)

    assert holder.armor_marked == 0


def test_no_six_leaves_the_slot_spent():
    holder, fight = _unyielding()
    holder.armor_marked = 1

    with patch("domain_cards.valor.random.randint", return_value=1):
        apply_on_damaged(holder, 12, 1, fight, True)

    assert holder.armor_marked == 1


def test_one_die_is_rolled_per_point_of_proficiency():
    holder, fight = _unyielding()
    holder.armor_marked = 1

    with patch("domain_cards.valor.random.randint", return_value=1) as rolled:
        apply_on_damaged(holder, 12, 1, fight, True)

    assert rolled.call_count == holder.proficiency


def test_a_hit_that_marked_no_armor_slot_rolls_nothing():
    """The trigger read literally - 'when you **would mark** an Armor Slot'."""
    holder, fight = _unyielding()
    holder.armor_marked = 1

    with patch("domain_cards.valor.random.randint", return_value=6) as rolled:
        apply_on_damaged(holder, 12, 2, fight, False)

    assert holder.armor_marked == 1
    rolled.assert_not_called()


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


def test_the_later_cards_are_modelled():
    for card in (
        INEVITABLE,
        SHRUG_IT_OFF,
        VALOR_TOUCHED,
        FULL_SURGE,
        GROUND_POUND,
        HOLD_THE_LINE,
        LEAD_BY_EXAMPLE,
        UNBREAKABLE,
        UNYIELDING_ARMOR,
    ):
        assert assess(card).status is Status.MODELLED
