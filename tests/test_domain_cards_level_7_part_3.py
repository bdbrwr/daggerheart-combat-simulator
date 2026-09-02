"""Tests for the level 7 cards of Sage, Splendor and Valor - the batch that
closes level 7.

Six cards, all modelled, and two pieces of machinery that are what most of these
are really about:

* **The rolled trait** now travels with a duality roll and through `roll_bonus`,
  which is the only way Sage-Touched's "double your Agility or Instinct on a roll
  that uses that trait" can be asked at all.
* **`on_damaged` carries whether an Armor Slot was marked**, which is the fact
  Valor-Touched triggers on the *absence* of - and which cannot be recovered
  afterwards, since direct damage leaves slots free and unspent.

The readings pinned down here are the ones the modules document as choices:
Sage-Touched's +2 running in every fight because terrain is not modelled, Wild
Surge climbing 1 through 6 and then charging a forced Stress on the way out,
Splendor-Touched preferring Hope and marking Stress only to stay standing, and
Shrug It Off firing on Severe damage alone and vaulting itself on a low d6.

Determinism comes from constructing rolls with fixed dice, from a target with a
Difficulty of 0 so no case turns on whether an attack landed, and from patching
the module-level `random` where a card rolls one of its own.
"""

import random
from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.results import AttackResult
from combat.state import FightState
from content import (
    apply_on_damaged,
    apply_on_hit,
    assess,
    soften_damage,
    total_roll_bonus,
    total_spellcast_bonus,
    use_free_abilities,
)
from content.spellcast import spellcast
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult, roll_duality
from domain_cards.sage import (
    SAGE_TOUCHED,
    WILD_SURGE,
    WILD_SURGE_DIE,
    WILD_SURGE_MAX,
)
from domain_cards.splendor import HEALING_STRIKE, SPLENDOR_TOUCHED
from domain_cards.valor import (
    SHRUG_IT_OFF,
    SHRUG_IT_OFF_VAULTED,
    VALOR_TOUCHED,
)
from items.registry import find_weapon


def _make_character(**overrides) -> PlayerCharacter:
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
        # No armor, deliberately: half the cases here go through `soften_damage`,
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
    overrides.setdefault("rest", Rest.LONG)
    return FightState(
        encounter_name="Test", party=party, adversaries=adversaries, **overrides
    )


def _landed_hit() -> AttackResult:
    """An attack that hit for something, for the on-hit riders to read."""
    return AttackResult(
        attack_roll=DualityRollResult(
            hope_die_result=9,
            fear_die_result=4,
            modifier=0,
            advantage_state=AdvantageState.NONE,
            advantage_die_result=None,
            help_dice_results=None,
            difficulty=5,
        ),
        damage_roll=DamageRollResult(
            dice_groups=[DiceGroup(count=1, sides=4)],
            die_results=[[4]],
            modifier=0,
        ),
        hp_marked=1,
    )


# --- The trait travelling with the roll -------------------------------------------


def test_a_duality_roll_records_the_trait_it_was_made_with():
    random.seed(1)
    assert roll_duality(trait="instinct").trait == "instinct"


def test_a_roll_with_no_trait_named_records_none():
    """A hand-built result has no character behind it, which is a real answer."""
    random.seed(1)
    assert roll_duality().trait == ""


def test_a_spellcast_roll_carries_the_trait_it_rolled():
    caster = _make_character()
    target = _make_adversary()
    fight = _state([caster], [target])

    assert spellcast(caster, target, fight).trait == "knowledge"


def test_a_named_trait_reaches_the_roll_rather_than_the_spellcast_trait():
    """Grace's Troublemaker rolls Presence; the roll should say so."""
    caster = _make_character()
    target = _make_adversary()
    fight = _state([caster], [target])

    assert spellcast(caster, target, fight, trait="presence").trait == "presence"


def test_a_weapon_swing_carries_the_weapons_own_trait():
    from items.weapons import attack_with

    attacker = _make_character()
    target = _make_adversary()
    fight = _state([attacker], [target])
    weapon = find_weapon(attacker.primary_weapon)

    result = attack_with(attacker, weapon, target, fight=fight)

    assert result.attack_roll.trait == weapon.trait


# --- Sage-Touched -----------------------------------------------------------------


def test_the_spellcast_bonus_is_simply_on():
    """Ruled: every fight counts as a natural environment."""
    caster = _make_character(domain_cards_loadout=[SAGE_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    assert total_spellcast_bonus(caster, target, fight) == 2


def test_the_spellcast_bonus_does_not_reach_a_weapon_swing():
    caster = _make_character(domain_cards_loadout=[SAGE_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    assert total_roll_bonus(caster, target, fight, trait="strength") == 0


def test_the_doubling_fires_on_a_roll_that_uses_the_trait():
    holder = _make_character(domain_cards_loadout=[SAGE_TOUCHED])
    target = _make_adversary()
    fight = _state([holder], [target])

    # Agility 3, doubled - so the roll gets the trait a second time.
    assert total_roll_bonus(holder, target, fight, trait="agility") == 3


def test_the_doubling_declines_on_a_trait_the_card_does_not_name():
    holder = _make_character(domain_cards_loadout=[SAGE_TOUCHED])
    target = _make_adversary()
    fight = _state([holder], [target])

    assert total_roll_bonus(holder, target, fight, trait="finesse") == 0
    # And the use is still there for an Agility roll afterwards.
    assert total_roll_bonus(holder, target, fight, trait="agility") == 3


def test_the_doubling_declines_at_a_trait_of_zero():
    """Instinct is 0 on the test sheet - the standing zero-benefit rule."""
    holder = _make_character(domain_cards_loadout=[SAGE_TOUCHED])
    target = _make_adversary()
    fight = _state([holder], [target])

    assert total_roll_bonus(holder, target, fight, trait="instinct") == 0
    assert fight.can_use_once_per_rest(holder, SAGE_TOUCHED) is True


def test_the_doubling_is_once_per_rest():
    holder = _make_character(domain_cards_loadout=[SAGE_TOUCHED])
    target = _make_adversary()
    fight = _state([holder], [target])

    assert total_roll_bonus(holder, target, fight, trait="agility") == 3
    assert total_roll_bonus(holder, target, fight, trait="agility") == 0


def test_the_doubling_lands_in_a_spellcast_roll_made_on_that_trait():
    """A Sage whose Spellcast trait is Instinct or Agility gets both clauses."""
    caster = _make_character(
        domain_cards_loadout=[SAGE_TOUCHED], spellcast_trait="agility"
    )
    target = _make_adversary()
    fight = _state([caster], [target])

    roll = spellcast(caster, target, fight)

    # Agility 3, the card's +2 to Spellcast Rolls, and Agility doubled again.
    assert roll.modifier == 8
    assert roll.trait == "agility"


# --- Wild Surge -------------------------------------------------------------------


def test_the_surge_costs_a_stress_and_places_the_die_at_one():
    holder = _make_character(domain_cards_loadout=[WILD_SURGE])
    fight = _state([holder], [])

    assert use_free_abilities(holder, fight, limit=1) == [WILD_SURGE]
    assert holder.stress_marked == 1
    assert fight.token_count(holder, WILD_SURGE_DIE) == 1


def test_the_surge_is_not_raised_twice():
    holder = _make_character(domain_cards_loadout=[WILD_SURGE])
    fight = _state([holder], [])

    use_free_abilities(holder, fight, limit=1)
    assert use_free_abilities(holder, fight, limit=1) == []


def test_the_die_adds_its_value_and_then_climbs():
    holder = _make_character(domain_cards_loadout=[WILD_SURGE])
    target = _make_adversary()
    fight = _state([holder], [target])
    fight.set_token(holder, WILD_SURGE_DIE, 1)

    assert total_roll_bonus(holder, target, fight, trait="agility") == 1
    assert fight.token_count(holder, WILD_SURGE_DIE) == 2
    assert total_roll_bonus(holder, target, fight, trait="agility") == 2
    assert fight.token_count(holder, WILD_SURGE_DIE) == 3


def test_the_form_drops_after_the_die_pays_out_at_six():
    holder = _make_character(domain_cards_loadout=[WILD_SURGE])
    target = _make_adversary()
    fight = _state([holder], [target])
    fight.set_token(holder, WILD_SURGE_DIE, WILD_SURGE_MAX)

    # The sixth payout still gets its +6; the seventh would need a 7.
    assert total_roll_bonus(holder, target, fight, trait="agility") == WILD_SURGE_MAX
    assert fight.token_count(holder, WILD_SURGE_DIE) == 0
    assert holder.stress_marked == 1
    assert total_roll_bonus(holder, target, fight, trait="agility") == 0


def test_the_stress_the_form_costs_is_forced_and_can_reach_hp():
    """A full Stress track means the surge ending marks an HP instead."""
    holder = _make_character(domain_cards_loadout=[WILD_SURGE], stress_max=1)
    target = _make_adversary()
    fight = _state([holder], [target])
    holder.stress_marked = 1
    fight.set_token(holder, WILD_SURGE_DIE, WILD_SURGE_MAX)

    total_roll_bonus(holder, target, fight, trait="agility")

    assert holder.hp_marked == 1


# --- Healing Strike ---------------------------------------------------------------


def test_a_landed_blow_clears_an_ally_hit_point_for_two_hope():
    attacker = _make_character(name="Striker", domain_cards_loadout=[HEALING_STRIKE])
    hurt = _make_character(name="Hurt", hp_max=8)
    spare = _make_character(name="Spare")
    other = _make_character(name="Other")
    hurt.hp_marked = 6  # two unmarked, so at the floor
    target = _make_adversary()
    fight = _state([attacker, hurt, spare, other], [target])

    with patch("domain_cards.splendor.random.random", return_value=0.0):
        apply_on_hit(attacker, target, _landed_hit(), fight)

    assert hurt.hp_marked == 5
    assert attacker.hope_marked == 4


def test_the_heal_declines_for_an_ally_who_is_merely_dented():
    attacker = _make_character(name="Striker", domain_cards_loadout=[HEALING_STRIKE])
    dented = _make_character(name="Dented", hp_max=8)
    spare = _make_character(name="Spare")
    other = _make_character(name="Other")
    dented.hp_marked = 1
    target = _make_adversary()
    fight = _state([attacker, dented, spare, other], [target])

    with patch("domain_cards.splendor.random.random", return_value=0.0):
        apply_on_hit(attacker, target, _landed_hit(), fight)

    assert dented.hp_marked == 1
    assert attacker.hope_marked == 6


def test_the_heal_declines_without_the_two_hope():
    attacker = _make_character(
        name="Striker", domain_cards_loadout=[HEALING_STRIKE], hope_marked=1
    )
    hurt = _make_character(name="Hurt", hp_max=8)
    spare = _make_character(name="Spare")
    other = _make_character(name="Other")
    hurt.hp_marked = 6
    target = _make_adversary()
    fight = _state([attacker, hurt, spare, other], [target])

    with patch("domain_cards.splendor.random.random", return_value=0.0):
        apply_on_hit(attacker, target, _landed_hit(), fight)

    assert hurt.hp_marked == 6
    assert attacker.hope_marked == 1


# --- Splendor-Touched -------------------------------------------------------------


def test_the_wound_is_paid_for_in_hope_while_near_death():
    holder = _make_character(domain_cards_loadout=[SPLENDOR_TOUCHED])
    fight = _state([holder], [])
    holder.hp_marked = 6  # two unmarked

    assert soften_damage(holder, 25, 2, fight) == 0
    assert holder.hope_marked == 4
    assert holder.stress_marked == 0


def test_nothing_is_converted_while_the_holder_is_healthy():
    holder = _make_character(domain_cards_loadout=[SPLENDOR_TOUCHED])
    fight = _state([holder], [])

    assert soften_damage(holder, 25, 3, fight) == 3
    assert holder.hope_marked == 6
    assert fight.can_use_once_per_rest(holder, SPLENDOR_TOUCHED, long=True) is True


def test_stress_is_marked_only_when_it_keeps_the_holder_standing():
    """No Hope left, and the hit would take the last two HP."""
    holder = _make_character(domain_cards_loadout=[SPLENDOR_TOUCHED], hope_marked=0)
    fight = _state([holder], [])
    holder.hp_marked = 6  # two unmarked, and the hit costs two

    assert soften_damage(holder, 25, 2, fight) == 0
    assert holder.stress_marked == 2


def test_a_survivable_wound_is_taken_rather_than_stressed_for():
    holder = _make_character(domain_cards_loadout=[SPLENDOR_TOUCHED], hope_marked=0)
    fight = _state([holder], [])
    holder.hp_marked = 6  # two unmarked, and the hit costs only one

    assert soften_damage(holder, 12, 1, fight) == 1
    assert holder.stress_marked == 0
    assert fight.can_use_once_per_rest(holder, SPLENDOR_TOUCHED, long=True) is True


def test_the_conversion_is_once_per_long_rest():
    holder = _make_character(domain_cards_loadout=[SPLENDOR_TOUCHED])
    fight = _state([holder], [])
    holder.hp_marked = 6

    assert soften_damage(holder, 25, 2, fight) == 0
    assert soften_damage(holder, 25, 2, fight) == 2


# --- Shrug It Off -----------------------------------------------------------------


def test_a_severe_hit_is_reduced_by_a_threshold_for_a_stress():
    holder = _make_character(domain_cards_loadout=[SHRUG_IT_OFF])
    fight = _state([holder], [])

    with patch("domain_cards.valor.random.randint", return_value=6):
        assert soften_damage(holder, 25, 3, fight) == 2

    assert holder.stress_marked == 1
    assert fight.token_count(holder, SHRUG_IT_OFF_VAULTED) == 0


def test_a_low_die_vaults_the_card_for_the_rest_of_the_fight():
    holder = _make_character(domain_cards_loadout=[SHRUG_IT_OFF])
    fight = _state([holder], [])

    with patch("domain_cards.valor.random.randint", return_value=3):
        assert soften_damage(holder, 25, 3, fight) == 2
    assert fight.token_count(holder, SHRUG_IT_OFF_VAULTED) == 1

    # Vaulted, so a second Severe hit gets nothing and costs nothing.
    with patch("domain_cards.valor.random.randint", return_value=6):
        assert soften_damage(holder, 25, 3, fight) == 3
    assert holder.stress_marked == 1


def test_a_major_hit_is_not_shrugged_off():
    """Ruled: Severe damage only, read off the amount rather than the HP."""
    holder = _make_character(domain_cards_loadout=[SHRUG_IT_OFF])
    fight = _state([holder], [])

    assert soften_damage(holder, 12, 2, fight) == 2
    assert holder.stress_marked == 0


def test_a_hit_armor_took_to_nothing_buys_nothing():
    holder = _make_character(domain_cards_loadout=[SHRUG_IT_OFF])
    fight = _state([holder], [])

    assert soften_damage(holder, 25, 0, fight) == 0
    assert holder.stress_marked == 0


# --- Valor-Touched ----------------------------------------------------------------


def test_a_wound_that_marked_no_armor_slot_clears_one():
    holder = _make_character(domain_cards_loadout=[VALOR_TOUCHED], armor_max=2)
    fight = _state([holder], [])
    holder.armor_marked = 2

    apply_on_damaged(holder, 12, 2, fight, False)

    assert holder.armor_marked == 1


def test_a_wound_that_did_mark_an_armor_slot_clears_nothing():
    holder = _make_character(domain_cards_loadout=[VALOR_TOUCHED], armor_max=2)
    fight = _state([holder], [])
    holder.armor_marked = 2

    apply_on_damaged(holder, 12, 2, fight, True)

    assert holder.armor_marked == 2


def test_a_hit_that_marked_no_hp_clears_nothing():
    holder = _make_character(domain_cards_loadout=[VALOR_TOUCHED], armor_max=2)
    fight = _state([holder], [])
    holder.armor_marked = 2

    apply_on_damaged(holder, 12, 0, fight, False)

    assert holder.armor_marked == 2


def test_direct_damage_reaches_the_card_through_the_real_pipeline():
    """The edge `armor_unmarked == 0` would have got wrong.

    Slots are free and none is spent, so the card should fire - which is why the
    fact is carried rather than inferred afterwards.
    """
    holder = _make_character(domain_cards_loadout=[VALOR_TOUCHED], armor_max=2)
    fight = _state([holder], [])
    holder.armor_marked = 1

    holder.take_damage(25, fight, direct=True)

    assert holder.hp_marked == 3
    assert holder.armor_marked == 0


def test_an_ordinary_hit_marks_the_slot_and_the_card_stays_quiet():
    holder = _make_character(domain_cards_loadout=[VALOR_TOUCHED], armor_max=2)
    fight = _state([holder], [])
    holder.armor_marked = 1

    holder.take_damage(25, fight)

    # The free slot went in, so the refund correctly does not.
    assert holder.armor_marked == 2
    assert holder.hp_marked == 2


# --- Coverage ---------------------------------------------------------------------


def test_every_card_in_the_batch_is_assessed():
    for card in (
        SAGE_TOUCHED,
        WILD_SURGE,
        HEALING_STRIKE,
        SPLENDOR_TOUCHED,
        SHRUG_IT_OFF,
        VALOR_TOUCHED,
    ):
        assert assess(card).status.value == "modelled"
