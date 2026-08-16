"""The SRD adversary features, one by one.

Every feature is called directly rather than through a fight, so each test says
what one rule does and nothing else. Where a feature rolls dice, the roller is
patched at the module that calls it - the same way the weapon tests patch
`items.weapons.roll_duality` - so nothing here depends on a seed.

Two things are worth knowing before adding to this file:

* An adversary's features reach dispatch **qualified** (`adversary:Relentless`),
  and a stat block writes them bare. `_adversary(features=[...])` takes the bare
  form, exactly as `srd.json` does.
* Several features are parameterised - the stat block writes `Relentless (3)`
  and the content registers as `Relentless`. Tests that care about the number
  build the stat block with the printed name.
"""

from unittest.mock import patch

import pytest

from adversaries.adversary import Adversary
from adversaries.catalogue import NO_THRESHOLD
from characters.player_character import PlayerCharacter
from combat.results import AttackResult
from combat.state import FightState
from content.aoe import Range
from content.conditions import (
    BEFORE_AN_ACTION_ROLL,
    ON_A_GM_TURN,
    POISONED,
    VULNERABLE,
    WHEN_THEY_ACT,
    Condition,
    when_the_gm_pays,
    when_they_act,
)
from items.registry import find_weapon
from content.names import base_name, parameter
from content.registry import (
    Status,
    activations_allowed,
    assess,
    deals_direct_damage,
    extra_spotlight_cost,
    feature_parameter,
    harden_damage,
    standard_attack_area,
)
from dice.common import AdvantageState
from dice.d20 import D20RollResult
from dice.damage import DiceGroup
from dice.duality import DualityRollResult
from features.adversaries import (
    acid_bath,
    bite,
    bone_breaker,
    death_quake,
    earth_eruption,
    grab_and_drag,
    ground_slam,
    hail_of_boulders,
    momentum,
    ramp_up_costs_fear,
    ramp_up_sweeps,
    rampaging_fury,
    relentless,
    spit_acid,
    trample,
    weak_structure,
)


def _make_pc(name: str, **overrides) -> PlayerCharacter:
    defaults = dict(
        name=name,
        level=2,
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 1, "strength": 1, "finesse": 1,
            "instinct": 1, "presence": 0, "knowledge": 1,
        },
        evasion=10,
        proficiency=1,
        major_threshold=6,
        severe_threshold=12,
        hp_max=6,
        stress_max=6,
        hope_max=6,
        armor_max=2,
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


def _party(size: int = 4, **overrides) -> list[PlayerCharacter]:
    return [_make_pc(f"PC{index}", **overrides) for index in range(size)]


def _adversary(name: str = "Thing", features=(), **overrides) -> Adversary:
    defaults = dict(
        name=name,
        tier=1,
        difficulty=13,
        major_threshold=8,
        severe_threshold=15,
        hp_max=8,
        stress_max=3,
        attack_modifier=2,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=2,
        features=list(features),
    )
    defaults.update(overrides)
    return Adversary(**defaults)


def _fight(party=None, adversaries=None, **overrides) -> FightState:
    return FightState(
        encounter_name="Test",
        party=_party() if party is None else party,
        adversaries=[_adversary()] if adversaries is None else adversaries,
        **overrides,
    )


def _d20(die: int, evasion: int = 10, modifier: int = 0) -> D20RollResult:
    return D20RollResult(
        die_results=[die],
        modifier=modifier,
        advantage_state=AdvantageState.NONE,
        evasion=evasion,
    )


def _duality(*, succeeds: bool, critical: bool = False) -> DualityRollResult:
    """A reaction roll that lands exactly where the test wants it."""
    hope, fear = (5, 5) if critical else (5, 4)
    return DualityRollResult(
        hope_die_result=hope,
        fear_die_result=fear,
        modifier=0,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=1 if succeeds else 100,
    )


# --- Parameterised names -----------------------------------------------------


def test_a_printed_number_is_split_off_the_feature_name():
    assert base_name("Relentless (3)") == "Relentless"
    assert parameter("Relentless (3)") == "3"


def test_a_name_without_a_parameter_is_left_alone():
    assert base_name("Bone Breaker") == "Bone Breaker"
    assert parameter("Bone Breaker") is None


def test_a_namespace_prefix_survives_the_split():
    """Only a trailing bracket is stripped, so the qualifier can't be eaten."""
    assert base_name("adversary:Relentless (3)") == "adversary:Relentless"


def test_a_parameterised_feature_is_found_by_its_base_name():
    """The whole point: the stat block's spelling reaches the registration."""
    assert assess("adversary:Relentless (3)").status is Status.MODELLED


def test_a_holder_reports_the_number_its_own_stat_block_wrote():
    burrower = _adversary(features=["Relentless (3)"])
    construct = _adversary(features=["Relentless (2)"])

    assert feature_parameter(burrower, "adversary:Relentless") == "3"
    assert feature_parameter(construct, "adversary:Relentless") == "2"


def test_a_holder_without_the_feature_reports_nothing():
    assert feature_parameter(_adversary(), "adversary:Relentless") is None


# --- Relentless --------------------------------------------------------------


def test_relentless_allows_as_many_activations_as_its_number():
    burrower = _adversary(features=["Relentless (3)"])
    assert relentless(burrower, _fight()) == 3


def test_relentless_without_a_number_declines_rather_than_guessing():
    """The number is the whole feature; inventing one would invent a stat."""
    assert relentless(_adversary(features=["Relentless"]), _fight()) is None


def test_an_adversary_with_no_features_gets_one_activation():
    assert activations_allowed(_adversary(), _fight()) == 1


def test_relentless_raises_the_activation_allowance():
    burrower = _adversary(features=["Relentless (3)"])
    assert activations_allowed(burrower, _fight()) == 3


# --- Momentum ----------------------------------------------------------------


def test_momentum_hands_the_gm_a_fear():
    bear = _adversary("Bear", features=["Momentum"])
    fight = _fight(fear=0)

    momentum(bear, _make_pc("Target"), None, fight)

    assert fight.fear == 1


def test_momentum_adds_nothing_once_the_fear_pool_is_full():
    bear = _adversary("Bear", features=["Momentum"])
    fight = _fight(fear=12)

    momentum(bear, _make_pc("Target"), None, fight)

    assert fight.fear == 12


# --- Overwhelming Force ------------------------------------------------------


def test_overwhelming_force_is_declared_as_having_no_combat_effect():
    """A knockback moves a combatant, and no position is tracked to move."""
    assert assess("adversary:Overwhelming Force").status is Status.NO_COMBAT_EFFECT


def test_a_dismissal_carries_its_reason():
    assert assess("adversary:Overwhelming Force").reason


# --- Weak Structure ----------------------------------------------------------


def test_weak_structure_adds_an_hp_to_a_hit_that_marked_one():
    construct = _adversary("Construct", features=["Weak Structure"])
    assert weak_structure(construct, amount=9, hp_to_mark=2) == 3


def test_weak_structure_adds_nothing_to_a_hit_that_marked_nothing():
    """"When the Construct marks HP" - a hit softened away marked none."""
    construct = _adversary("Construct", features=["Weak Structure"])
    assert weak_structure(construct, amount=9, hp_to_mark=0) == 0


def test_weak_structure_reaches_the_construct_through_dispatch():
    construct = _adversary("Construct", features=["Weak Structure"])
    assert harden_damage(construct, amount=9, hp_to_mark=1) == 2


def test_an_adversary_without_it_takes_the_hit_unchanged():
    assert harden_damage(_adversary(), amount=9, hp_to_mark=1) == 1


# --- Bone Breaker and direct damage -----------------------------------------


def test_bone_breaker_makes_this_adversarys_attacks_direct():
    ogre = _adversary("Cave Ogre", features=["Bone Breaker"])
    assert deals_direct_damage(ogre, _fight()) is True


def test_an_adversary_without_it_deals_ordinary_damage():
    assert deals_direct_damage(_adversary(), _fight()) is False


def test_direct_damage_marks_no_armor_slot():
    pc = _make_pc("Target", armor_max=2)
    pc.take_damage(7, direct=True)

    assert pc.armor_marked == 0
    assert pc.hp_marked == 2  # Major, with no slot to soften it


def test_ordinary_damage_still_marks_one():
    pc = _make_pc("Target", armor_max=2)
    pc.take_damage(7)

    assert pc.armor_marked == 1
    assert pc.hp_marked == 1


def test_direct_damage_is_still_measured_against_thresholds():
    """Only the Armor Slot is skipped - severity works exactly as before."""
    pc = _make_pc("Target", armor_max=0)
    assert pc.take_damage(13, direct=True) == 3  # at or above Severe


# --- Conditions --------------------------------------------------------------


def test_a_condition_is_absent_until_it_is_applied():
    fight = _fight()
    assert not fight.has_condition(fight.party[0], VULNERABLE)


def test_a_condition_ends_at_the_moment_it_names():
    fight = _fight()
    pc = fight.party[0]
    fight.apply_condition(pc, Condition(name=VULNERABLE, end=when_they_act))

    assert fight.expire_conditions(pc, ON_A_GM_TURN) == []
    assert fight.has_condition(pc, VULNERABLE)

    assert fight.expire_conditions(pc, WHEN_THEY_ACT) == [VULNERABLE]
    assert not fight.has_condition(pc, VULNERABLE)


def test_a_condition_with_no_end_lasts_the_rest_of_the_fight():
    fight = _fight()
    pc = fight.party[0]
    fight.apply_condition(pc, Condition(name=VULNERABLE))

    fight.expire_conditions(pc, WHEN_THEY_ACT)
    fight.expire_conditions(pc, ON_A_GM_TURN)

    assert fight.has_condition(pc, VULNERABLE)


def test_the_gm_pays_a_fear_to_shake_a_condition_off():
    fight = _fight(fear=1)
    adversary = fight.adversaries[0]
    fight.apply_condition(adversary, Condition(name=VULNERABLE, end=when_the_gm_pays))

    assert fight.expire_conditions(adversary, ON_A_GM_TURN) == [VULNERABLE]
    assert fight.fear == 0


def test_a_gm_who_cannot_pay_does_not_shake_it_off():
    """The honest consequence, and the reason the charge moved to clear-time."""
    fight = _fight(fear=0)
    adversary = fight.adversaries[0]
    fight.apply_condition(adversary, Condition(name=VULNERABLE, end=when_the_gm_pays))

    assert fight.expire_conditions(adversary, ON_A_GM_TURN) == []
    assert fight.has_condition(adversary, VULNERABLE)


def test_vulnerable_is_answered_from_either_source():
    fight = _fight()
    stressed, conditioned = fight.party[0], fight.party[1]
    stressed.stress_marked = stressed.stress_max
    fight.apply_condition(conditioned, Condition(name=VULNERABLE))

    assert fight.is_vulnerable(stressed)
    assert fight.is_vulnerable(conditioned)
    assert not fight.is_vulnerable(fight.party[2])


def test_an_adversary_is_never_vulnerable_of_its_own_accord():
    adversary = _adversary()
    adversary.stress_marked = adversary.stress_max
    assert adversary.is_vulnerable is False


# --- Adversary Stress --------------------------------------------------------


def test_an_adversary_can_pay_a_stress_it_has():
    adversary = _adversary(stress_max=2)
    assert adversary.spend_stress(1) is True
    assert adversary.stress_marked == 1


def test_an_adversary_cannot_pay_a_stress_it_does_not_have():
    """A feature whose Stress can't be paid is simply off the table."""
    adversary = _adversary(stress_max=1)
    adversary.spend_stress(1)

    assert adversary.can_spend_stress(1) is False
    assert adversary.spend_stress(1) is False
    assert adversary.stress_marked == 1


# --- The Stress-desperation rule ---------------------------------------------
#
# `hp_unmarked <= X**2 + 1`, with X the Stress slots still free: 10 at three
# slots, 5 at two, 2 at one. Actions consult it; Reactions deliberately don't.


def test_the_desperation_thresholds_are_the_squares_plus_one():
    """The whole rule, read off one adversary at each slot count."""
    adversary = _adversary(hp_max=20, stress_max=3)

    adversary.hp_marked = 20 - 10
    assert adversary.will_spend_stress(1) is True
    adversary.hp_marked = 20 - 11
    assert adversary.will_spend_stress(1) is False

    adversary.spend_stress(1)
    adversary.hp_marked = 20 - 5
    assert adversary.will_spend_stress(1) is True
    adversary.hp_marked = 20 - 6
    assert adversary.will_spend_stress(1) is False

    adversary.spend_stress(1)
    adversary.hp_marked = 20 - 2
    assert adversary.will_spend_stress(1) is True
    adversary.hp_marked = 20 - 3
    assert adversary.will_spend_stress(1) is False


def test_the_last_slot_opens_on_the_partys_own_near_death_line():
    """The +1 exists to put both sides of the table on the same number."""
    from characters.player_character import NEAR_DEATH_HP_UNMARKED

    adversary = _adversary(hp_max=8, stress_max=1)
    adversary.hp_marked = 8 - NEAR_DEATH_HP_UNMARKED

    assert adversary.will_spend_stress(1) is True


def test_a_cost_of_several_slots_is_measured_at_the_last_one():
    """Two slots at once has to clear the threshold the second one faces."""
    # 6 unmarked HP. One slot is measured at X=3 (threshold 10) and passes;
    # two are measured at X=2 (threshold 5) and don't.
    adversary = _adversary(hp_max=20, stress_max=3)
    adversary.hp_marked = 20 - 6

    assert adversary.will_spend_stress(1) is True
    assert adversary.will_spend_stress(2) is False


def test_an_adversary_that_cannot_afford_the_stress_never_spends_it():
    """However desperate: the slots still have to exist."""
    adversary = _adversary(hp_max=8, stress_max=1)
    adversary.hp_marked = 7
    adversary.spend_stress(1)

    assert adversary.will_spend_stress(1) is False


# --- Earth Eruption ----------------------------------------------------------


def test_earth_eruption_costs_a_stress_and_makes_no_attack():
    burrower = _adversary("Acid Burrower", features=["Earth Eruption"])
    fight = _fight()

    result = earth_eruption(burrower, fight.party[0], fight)

    assert burrower.stress_marked == 1
    assert result is not None, "firing must not read as declining"
    assert result.made_an_attack is False


def test_earth_eruption_declines_when_it_cannot_pay():
    burrower = _adversary("Acid Burrower", features=["Earth Eruption"], stress_max=0)
    fight = _fight()

    assert earth_eruption(burrower, fight.party[0], fight) is None
    assert burrower.stress_marked == 0


def test_a_pc_who_fails_the_reaction_roll_is_made_vulnerable():
    burrower = _adversary("Acid Burrower", features=["Earth Eruption"])
    fight = _fight()

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=False)
    ):
        earth_eruption(burrower, fight.party[0], fight)

    caught = [pc for pc in fight.party if fight.has_condition(pc, VULNERABLE)]
    assert caught, "somebody in the area should have been knocked over"


def test_a_pc_who_makes_the_reaction_roll_keeps_their_feet():
    burrower = _adversary("Acid Burrower", features=["Earth Eruption"])
    fight = _fight()

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ):
        earth_eruption(burrower, fight.party[0], fight)

    assert not any(fight.has_condition(pc, VULNERABLE) for pc in fight.party)


# --- Spit Acid ---------------------------------------------------------------


def test_spit_acid_burns_an_armor_slot_on_everyone_it_hits():
    burrower = _adversary("Acid Burrower", features=["Spit Acid"])
    fight = _fight()

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        spit_acid(burrower, fight.party[0], fight)

    # Close reaches three of four; each takes the hit (one slot) and the acid
    # (a second), so anyone caught has both slots gone.
    burned = [pc for pc in fight.party if pc.armor_marked == 2]
    assert len(burned) == 3


def test_spit_acid_costs_an_hp_and_a_fear_when_there_is_no_armor_left():
    burrower = _adversary("Acid Burrower", features=["Spit Acid"])
    fight = _fight(party=_party(size=1, armor_max=0), fear=0)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        spit_acid(burrower, fight.party[0], fight)

    assert fight.party[0].hp_marked >= 1
    assert fight.fear == 1


# --- Acid Bath ---------------------------------------------------------------


# The splash is 1d10, which against a PC with Armor Slots can be softened to
# nothing - so these use an unarmored party. Otherwise "did anyone get hurt?"
# would depend on the die, which is exactly what tests/ must not do.


def test_acid_bath_fires_on_severe_damage():
    burrower = _adversary("Acid Burrower", features=["Acid Bath"], severe_threshold=15)
    fight = _fight(party=_party(armor_max=0), adversaries=[burrower])

    acid_bath(burrower, amount=15, hp_marked=3, fight=fight)

    assert any(pc.hp_marked for pc in fight.party)


def test_acid_bath_does_not_fire_below_the_severe_threshold():
    burrower = _adversary("Acid Burrower", features=["Acid Bath"], severe_threshold=15)
    fight = _fight(party=_party(armor_max=0), adversaries=[burrower])

    acid_bath(burrower, amount=14, hp_marked=2, fight=fight)

    assert not any(pc.hp_marked for pc in fight.party)


def test_acid_bath_reads_the_damage_rolled_not_the_hp_it_cost():
    """"Takes Severe damage" is about the number, so armor can't dodge it."""
    burrower = _adversary("Acid Burrower", features=["Acid Bath"], severe_threshold=15)
    fight = _fight(party=_party(armor_max=0), adversaries=[burrower])

    acid_bath(burrower, amount=20, hp_marked=0, fight=fight)

    assert any(pc.hp_marked for pc in fight.party)


# --- Bite --------------------------------------------------------------------


def _bear(**overrides) -> Adversary:
    """The printed Bear: 7 HP against only two Stress.

    Built to the page here because that ratio is the whole point of these
    tests - it is the one stat block the desperation rule keeps quiet at full
    health, and the generic `_adversary` defaults would hide that.
    """
    defaults = dict(features=["Bite"], hp_max=7, stress_max=2)
    defaults.update(overrides)
    return _adversary("Bear", **defaults)


def test_bite_costs_a_stress():
    bear = _bear()
    bear.mark_hp(2)  # 5 unmarked, which is the two-slot threshold
    fight = _fight()

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        bite(bear, fight.party[0], fight)

    assert bear.stress_marked == 1


def test_a_healthy_bear_does_not_bite():
    """7 HP against two Stress: the desperation rule's sharpest case.

    Not a statement that Bite is weak - it is the Bear's whole threat. It is
    that the GM holds a two-slot track back until the Bear is in trouble.
    """
    bear = _bear()
    fight = _fight()

    assert bite(bear, fight.party[0], fight) is None
    assert bear.stress_marked == 0


def test_bite_declines_when_the_bear_is_out_of_stress():
    bear = _bear(stress_max=1)
    bear.mark_hp(6)  # desperate enough; simply has nothing left to spend
    bear.spend_stress(1)
    fight = _fight()

    assert bite(bear, fight.party[0], fight) is None


# --- Ramp Up -----------------------------------------------------------------


def test_ramp_up_charges_a_fear_to_spotlight():
    ogre = _adversary("Cave Ogre", features=["Ramp Up"])
    assert extra_spotlight_cost(ogre, _fight()) == 1


def test_an_ordinary_adversary_costs_nothing_extra_to_spotlight():
    assert extra_spotlight_cost(_adversary(), _fight()) == 0


def test_ramp_up_sweeps_the_ogres_own_range():
    ogre = _adversary("Cave Ogre", features=["Ramp Up"], range="Very Close")
    assert ramp_up_sweeps(ogre) is Range.VERY_CLOSE
    assert standard_attack_area(ogre, _fight()) is Range.VERY_CLOSE


def test_ramp_up_sweeps_whatever_band_the_stat_block_prints():
    """The point of the field: one feature, correct on every adversary.

    Before `range` existed the Ogre's Very Close was written into the feature,
    so the same feature on a Melee adversary would have swept the wrong band.
    """
    reacher = _adversary("Something Long-Armed", features=["Ramp Up"], range="Far")
    assert standard_attack_area(reacher, _fight()) is Range.FAR


def test_a_range_is_read_however_it_was_typed():
    assert _adversary(range="very close").attack_band is Range.VERY_CLOSE


def test_a_range_nobody_recognises_raises_rather_than_defaulting():
    """A silent default here would quietly change how far an area sweep reaches."""
    with pytest.raises(ValueError):
        _adversary(range="Adjacent").attack_band


def test_an_ordinary_adversary_attacks_one_target():
    assert standard_attack_area(_adversary(), _fight()) is None


def test_ramp_up_charges_whatever_the_ogre_then_does():
    """The Fear is paid to spotlight, so no action of its own can duck it."""
    ogre = _adversary("Cave Ogre", features=["Ramp Up", "Hail of Boulders"])
    assert ramp_up_costs_fear(ogre) == 1


# --- Hail of Boulders --------------------------------------------------------


def test_hail_of_boulders_costs_a_stress():
    ogre = _adversary("Cave Ogre", features=["Hail of Boulders"])
    fight = _fight()

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        hail_of_boulders(ogre, fight.party[0], fight)

    assert ogre.stress_marked == 1


def test_hail_of_boulders_declines_without_the_stress():
    ogre = _adversary("Cave Ogre", features=["Hail of Boulders"], stress_max=0)
    assert hail_of_boulders(ogre, _make_pc("Target"), _fight()) is None


def test_hail_of_boulders_hands_the_gm_a_fear_for_catching_two():
    ogre = _adversary("Cave Ogre", features=["Hail of Boulders"])
    fight = _fight(fear=0)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        hail_of_boulders(ogre, fight.party[0], fight)

    assert fight.fear == 1


# --- Rampaging Fury ----------------------------------------------------------


def test_rampaging_fury_fires_when_two_hp_are_marked():
    ogre = _adversary("Cave Ogre", features=["Rampaging Fury"])
    fight = _fight(adversaries=[ogre])

    rampaging_fury(ogre, amount=9, hp_marked=2, fight=fight)

    assert any(pc.hp_marked for pc in fight.party)


def test_rampaging_fury_does_not_fire_on_a_single_hp():
    ogre = _adversary("Cave Ogre", features=["Rampaging Fury"])
    fight = _fight(adversaries=[ogre])

    rampaging_fury(ogre, amount=9, hp_marked=1, fight=fight)

    assert not any(pc.hp_marked for pc in fight.party)


def test_rampaging_fury_is_direct_so_no_armor_is_marked():
    ogre = _adversary("Cave Ogre", features=["Rampaging Fury"])
    fight = _fight(adversaries=[ogre])

    rampaging_fury(ogre, amount=9, hp_marked=2, fight=fight)

    hurt = [pc for pc in fight.party if pc.hp_marked]
    assert hurt and all(pc.armor_marked == 0 for pc in hurt)


# --- Trample -----------------------------------------------------------------


def test_trample_costs_a_stress():
    construct = _adversary("Construct", features=["Trample"])
    fight = _fight()

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        trample(construct, fight.party[0], fight)

    assert construct.stress_marked == 1


def test_trample_declines_without_the_stress():
    construct = _adversary("Construct", features=["Trample"], stress_max=0)
    assert trample(construct, _make_pc("Target"), _fight()) is None


# --- Overload ----------------------------------------------------------------


def test_overload_buys_ten_damage_for_a_stress():
    from features.adversaries import overload

    construct = _adversary("Construct", features=["Overload"])
    fight = _fight()

    assert overload(construct, fight.party[0], fight) == 10
    assert construct.stress_marked == 1


def test_overload_grants_another_spotlight():
    from features.adversaries import overload

    construct = _adversary("Construct", features=["Overload"])
    fight = _fight()

    overload(construct, fight.party[0], fight)

    assert fight.granted_activations(construct) == 1


def test_overload_adds_nothing_without_the_stress():
    from features.adversaries import overload

    construct = _adversary("Construct", features=["Overload"], stress_max=0)
    fight = _fight()

    assert overload(construct, fight.party[0], fight) == 0
    assert fight.granted_activations(construct) == 0


# --- Death Quake -------------------------------------------------------------


def test_death_quake_fires_when_the_construct_is_down():
    # Unarmored, so 1d12+2 can't be softened to nothing and the assertion
    # doesn't depend on the die.
    construct = _adversary("Construct", features=["Death Quake"], hp_max=1)
    fight = _fight(party=_party(armor_max=0), adversaries=[construct])
    construct.mark_hp(1)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        death_quake(construct, amount=9, hp_marked=1, fight=fight)

    assert any(pc.hp_marked for pc in fight.party)


def test_death_quake_does_not_fire_while_the_construct_stands():
    construct = _adversary("Construct", features=["Death Quake"], hp_max=9)
    fight = _fight(party=_party(armor_max=0), adversaries=[construct])
    construct.mark_hp(2)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        death_quake(construct, amount=9, hp_marked=2, fight=fight)

    assert not any(pc.hp_marked for pc in fight.party)


# --- Ground Slam -------------------------------------------------------------


def test_ground_slam_marks_a_stress_on_everyone_it_reaches():
    defender = _adversary("Deeproot Defender", features=["Ground Slam"])
    fight = _fight()

    result = ground_slam(defender, fight.party[0], fight)

    assert sum(pc.stress_marked for pc in fight.party) >= 1
    assert result.made_an_attack is False


def test_ground_slam_costs_the_defender_nothing():
    defender = _adversary("Deeproot Defender", features=["Ground Slam"])
    fight = _fight()

    ground_slam(defender, fight.party[0], fight)

    assert defender.stress_marked == 0


def test_forced_stress_that_will_not_fit_costs_an_hp_instead():
    """The SRD's rule on being made to mark Stress you haven't got."""
    defender = _adversary("Deeproot Defender", features=["Ground Slam"])
    fight = _fight(party=_party(size=1, stress_max=1))
    fight.party[0].mark_stress(1)

    ground_slam(defender, fight.party[0], fight)

    assert fight.party[0].hp_marked == 1


# --- Grab and Drag -----------------------------------------------------------


def test_grab_and_drag_spends_a_fear_on_a_hit():
    defender = _adversary("Deeproot Defender", features=["Grab and Drag"])
    fight = _fight(fear=2)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = grab_and_drag(defender, fight.party[0], fight)

    assert result.damage_roll is not None
    assert fight.fear == 1


def test_grab_and_drag_keeps_the_fear_on_a_miss():
    defender = _adversary("Deeproot Defender", features=["Grab and Drag"])
    fight = _fight(fear=2)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(1)):
        result = grab_and_drag(defender, fight.party[0], fight)

    assert result.damage_roll is None
    assert fight.fear == 2


def test_grab_and_drag_declines_when_the_gm_has_no_fear():
    defender = _adversary("Deeproot Defender", features=["Grab and Drag"])
    fight = _fight(fear=0)

    assert grab_and_drag(defender, fight.party[0], fight) is None


# --- Pack Tactics ------------------------------------------------------------
#
# Whether the pack converges on one target is the Melee band's answer, and that
# band is rolled - two wolves come together about half the time. So the spread
# roll is pinned here rather than sampled, the same way tests/test_hooks.py pins
# it: a roll of the top of the range means bunched, the bottom means scattered.


def _bunched():
    return patch("content.aoe.random.randint", lambda low, high: high)


def _scattered():
    return patch("content.aoe.random.randint", lambda low, high: low)


def _wolf(**overrides) -> Adversary:
    """The printed Dire Wolf: 4 HP, 3 Stress, a 1d6+2 standard attack."""
    defaults = dict(
        features=["Pack Tactics", "Hobbling Strike"],
        hp_max=4,
        stress_max=3,
        difficulty=12,
        attack_modifier=2,
        damage_dice=[DiceGroup(count=1, sides=6)],
        damage_modifier=2,
    )
    defaults.update(overrides)
    return _adversary("Dire Wolf", **defaults)


def test_pack_tactics_swaps_the_standard_damage_and_pays_a_fear():
    from features.adversaries import pack_tactics

    wolves = [_wolf(), _wolf()]
    fight = _fight(adversaries=wolves, fear=0)

    with _bunched():
        dice, modifier = pack_tactics(wolves[0], fight.party[0], fight)

    assert dice == [DiceGroup(count=1, sides=6)]
    assert modifier == 5
    assert fight.fear == 1


def test_a_scattered_pair_of_wolves_gets_nothing():
    """Two wolves converge on one PC about half the time, not always."""
    from features.adversaries import pack_tactics

    wolves = [_wolf(), _wolf()]
    fight = _fight(adversaries=wolves, fear=0)

    with _scattered():
        assert pack_tactics(wolves[0], fight.party[0], fight) is None
    assert fight.fear == 0


def test_a_big_enough_pack_always_converges():
    """At six the Melee band reaches 3 or 2, and either clears the bar of 2."""
    from features.adversaries import pack_tactics

    wolves = [_wolf() for _ in range(6)]
    fight = _fight(adversaries=wolves, fear=0)

    for spread in (_bunched, _scattered):
        with spread():
            assert pack_tactics(wolves[0], fight.party[0], fight) is not None


def test_a_lone_wolf_gets_nothing_from_pack_tactics():
    from features.adversaries import pack_tactics

    wolf = _wolf()
    fight = _fight(adversaries=[wolf], fear=0)

    for spread in (_bunched, _scattered):
        with spread():
            assert pack_tactics(wolf, fight.party[0], fight) is None
    assert fight.fear == 0


def test_pack_tactics_does_not_count_a_bear_as_a_packmate():
    from features.adversaries import pack_tactics

    wolf, bear = _wolf(), _adversary("Bear")
    fight = _fight(adversaries=[wolf, bear], fear=0)

    with _bunched():
        assert pack_tactics(wolf, fight.party[0], fight) is None


def test_the_swap_reaches_the_standard_attack_through_dispatch():
    """The point of the hook: nothing passes these dice in, the feature does."""
    wolves = [_wolf(), _wolf()]
    fight = _fight(party=_party(armor_max=0), adversaries=wolves, fear=0)

    with _bunched(), patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = wolves[0].attack(fight.party[0], fight=fight)

    # 1d6+5 is at least 6; the printed 1d6+2 could never reach it.
    assert result.damage_roll.total >= 6


def test_a_feature_with_its_own_dice_is_not_swapped():
    """"Instead of their standard damage" says nothing about a Hobbling Strike.

    Bunched, so the swap would certainly have fired had it been asked - which is
    what makes the untouched damage and the unpaid Fear mean something.
    """
    wolves = [_wolf(), _wolf()]
    fight = _fight(party=_party(armor_max=0), adversaries=wolves, fear=0)

    with _bunched(), patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = wolves[0].attack(
            fight.party[0],
            fight=fight,
            damage_dice=[DiceGroup(count=1, sides=4)],
            damage_modifier=0,
        )

    # 1d4+0 can never reach 1d6+5's floor of 6.
    assert result.damage_roll.total <= 4
    assert fight.fear == 0, "the swap never ran, so no Fear was paid"


# --- Hobbling Strike ---------------------------------------------------------


def test_hobbling_strike_is_direct_and_leaves_the_target_vulnerable():
    from features.adversaries import hobbling_strike

    wolf = _wolf()
    fight = _fight(party=_party(armor_max=2), adversaries=[wolf])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        hobbling_strike(wolf, target, fight)

    assert target.armor_marked == 0, "direct damage marks no Armor Slot"
    assert fight.has_condition(target, VULNERABLE)
    assert wolf.stress_marked == 1


def test_hobbling_strike_vulnerable_outlasts_acting_and_the_gm_turn():
    """"Until they clear at least 1 HP" - neither of the usual moments ends it."""
    from features.adversaries import hobbling_strike

    wolf = _wolf()
    fight = _fight(party=_party(armor_max=0), adversaries=[wolf])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        hobbling_strike(wolf, target, fight)

    fight.expire_conditions(target, WHEN_THEY_ACT)
    fight.expire_conditions(target, ON_A_GM_TURN)
    assert fight.has_condition(target, VULNERABLE)

    target.clear_hp(1)
    assert fight.expire_conditions(target, WHEN_THEY_ACT) == [VULNERABLE]


def test_hobbling_strike_leaves_nothing_on_a_miss():
    from features.adversaries import hobbling_strike

    wolf = _wolf()
    fight = _fight(adversaries=[wolf])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(1)):
        hobbling_strike(wolf, fight.party[0], fight)

    assert not fight.has_condition(fight.party[0], VULNERABLE)


# --- Horde -------------------------------------------------------------------


def _mosquitoes(**overrides) -> Adversary:
    defaults = dict(
        features=["Horde (1d4+1)", "Flying (2)", "Bloodsucker"],
        hp_max=6,
        stress_max=3,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=3,
    )
    defaults.update(overrides)
    return _adversary("Giant Mosquitoes", **defaults)


def test_a_horde_at_full_strength_uses_its_printed_attack():
    from features.adversaries import horde

    assert horde(_mosquitoes(), None, _fight()) is None


def test_a_horde_thinned_to_half_deals_its_parameter_instead():
    from features.adversaries import horde

    swarm = _mosquitoes()
    swarm.mark_hp(3)  # half of 6

    dice, modifier = horde(swarm, None, _fight())

    assert dice == [DiceGroup(count=1, sides=4)]
    assert modifier == 1


def test_a_horde_without_a_parameter_guesses_nothing():
    from features.adversaries import horde

    swarm = _mosquitoes(features=["Horde"])
    swarm.mark_hp(6)

    assert horde(swarm, None, _fight()) is None


# --- Flying ------------------------------------------------------------------


def test_flying_is_resolved_into_difficulty_at_spawn():
    definition = _mosquitoes(difficulty=10)
    assert definition.difficulty == 10
    assert definition.spawn().difficulty == 12


def test_flying_lands_on_top_of_an_encounters_override():
    definition = _mosquitoes(difficulty=10)
    assert definition.spawn(difficulty=15).difficulty == 17


def test_an_adversary_that_does_not_fly_spawns_unchanged():
    assert _adversary(difficulty=13).spawn().difficulty == 13


# --- Bloodsucker -------------------------------------------------------------


def test_bloodsucker_forces_an_extra_hp_for_a_stress():
    from features.adversaries import bloodsucker

    swarm = _mosquitoes()
    fight = _fight(party=_party(armor_max=0), adversaries=[swarm])
    target = fight.party[0]
    target.mark_hp(1)

    bloodsucker(swarm, target, AttackResult(None, None, hp_marked=1), fight)

    assert target.hp_marked == 2
    assert swarm.stress_marked == 1


def test_bloodsucker_does_not_fire_on_a_hit_that_marked_nothing():
    from features.adversaries import bloodsucker

    swarm = _mosquitoes()
    fight = _fight(adversaries=[swarm])

    bloodsucker(swarm, fight.party[0], AttackResult(None, None, hp_marked=0), fight)

    assert swarm.stress_marked == 0


def test_bloodsucker_is_not_gated_on_how_hurt_the_swarm_is():
    """A Reaction, so the Stress-desperation rule deliberately doesn't apply."""
    from features.adversaries import bloodsucker

    swarm = _mosquitoes()
    swarm.spend_stress(2)  # one slot left, and 6 unmarked HP against a threshold of 2
    fight = _fight(party=_party(armor_max=0), adversaries=[swarm])

    assert swarm.will_spend_stress(1) is False, "an Action could not spend this slot"
    bloodsucker(swarm, fight.party[0], AttackResult(None, None, hp_marked=1), fight)
    assert swarm.stress_marked == 3


# --- Minion ------------------------------------------------------------------


def test_minion_overkill_takes_down_one_more_per_x_damage():
    from features.adversaries import minion

    rats = [_rat() for _ in range(4)]
    fight = _fight(adversaries=rats)

    minion(rats[0], amount=7, hp_marked=1, fight=fight)

    # 7 // 3 = 2 additional Rats.
    assert sum(1 for rat in rats if rat.is_defeated) == 2


def test_minion_overkill_does_not_cascade():
    """Taken down with mark_hp, so no defeated Minion spreads the damage onward."""
    from features.adversaries import minion

    rats = [_rat() for _ in range(8)]
    fight = _fight(adversaries=rats)

    minion(rats[0], amount=6, hp_marked=1, fight=fight)

    assert sum(1 for rat in rats if rat.is_defeated) == 2


def test_a_small_hit_takes_down_nobody_extra():
    from features.adversaries import minion

    rats = [_rat() for _ in range(4)]
    fight = _fight(adversaries=rats)

    minion(rats[0], amount=2, hp_marked=1, fight=fight)

    assert not any(rat.is_defeated for rat in rats)


def test_a_minion_is_defeated_by_any_damage_without_the_feature_saying_so():
    """It falls out of NO_THRESHOLD and a 1 HP track, not out of this code."""
    rat = _rat()
    rat.take_damage(1)
    assert rat.is_defeated


# --- Double Strike -----------------------------------------------------------


def _scorpion(**overrides) -> Adversary:
    defaults = dict(
        features=["Double Strike", "Venomous Stinger", "Momentum"],
        hp_max=6,
        stress_max=3,
        difficulty=13,
        attack_modifier=1,
        damage_dice=[DiceGroup(count=1, sides=12)],
        damage_modifier=2,
    )
    defaults.update(overrides)
    return _adversary("Giant Scorpion", **defaults)


def test_double_strike_costs_a_stress_and_uses_the_printed_attack():
    from features.adversaries import double_strike

    scorpion = _scorpion()
    fight = _fight(party=_party(armor_max=0), adversaries=[scorpion])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = double_strike(scorpion, fight.party[0], fight)

    assert scorpion.stress_marked == 1
    # 1d12+2, so at least 3 - it did not bring dice of its own.
    assert result.damage_roll.total >= 3


def test_double_strike_reaches_at_most_two():
    from features.adversaries import double_strike

    scorpion = _scorpion()
    fight = _fight(party=_party(size=4, armor_max=0), adversaries=[scorpion])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        double_strike(scorpion, fight.party[0], fight)

    assert sum(1 for pc in fight.party if pc.hp_marked) <= 2


# --- Venomous Stinger and Poison ---------------------------------------------


def test_venomous_stinger_poisons_and_spends_a_fear_on_a_hit():
    from features.adversaries import venomous_stinger

    scorpion = _scorpion()
    fight = _fight(party=_party(armor_max=0), adversaries=[scorpion], fear=2)
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        venomous_stinger(scorpion, target, fight)

    assert fight.has_condition(target, POISONED)
    assert fight.fear == 1


def test_venomous_stinger_keeps_the_fear_on_a_miss():
    from features.adversaries import venomous_stinger

    scorpion = _scorpion()
    fight = _fight(adversaries=[scorpion], fear=2)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(1)):
        venomous_stinger(scorpion, fight.party[0], fight)

    assert fight.fear == 2
    assert not fight.has_condition(fight.party[0], POISONED)


def test_venomous_stinger_declines_against_an_already_poisoned_target():
    """The condition-attack rule: it's worse on damage, so it buys only the Poison."""
    from features.adversaries import venomous_stinger

    scorpion = _scorpion()
    fight = _fight(adversaries=[scorpion], fear=2)
    target = fight.party[0]
    fight.apply_condition(target, Condition(name=POISONED))

    assert venomous_stinger(scorpion, target, fight) is None


def test_poison_costs_a_stress_before_an_action_roll_on_a_low_die():
    from features.adversaries import venomous_stinger

    scorpion = _scorpion()
    fight = _fight(party=_party(armor_max=0), adversaries=[scorpion], fear=2)
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        venomous_stinger(scorpion, target, fight)

    with patch("features.adversaries.random.randint", return_value=1):
        fight.apply_condition_effects(target, BEFORE_AN_ACTION_ROLL)
    assert target.stress_marked == 1

    with patch("features.adversaries.random.randint", return_value=6):
        fight.apply_condition_effects(target, BEFORE_AN_ACTION_ROLL)
    assert target.stress_marked == 1, "a 6 is above the threshold"


def test_poison_does_nothing_at_a_moment_it_does_not_name():
    from features.adversaries import venomous_stinger

    scorpion = _scorpion()
    fight = _fight(party=_party(armor_max=0), adversaries=[scorpion], fear=2)
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        venomous_stinger(scorpion, target, fight)

    with patch("features.adversaries.random.randint", return_value=1):
        fight.apply_condition_effects(target, ON_A_GM_TURN)

    assert target.stress_marked == 0


def test_poison_lifts_on_a_successful_knowledge_roll():
    from features.adversaries import venomous_stinger

    scorpion = _scorpion()
    fight = _fight(party=_party(armor_max=0), adversaries=[scorpion], fear=2)
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        venomous_stinger(scorpion, target, fight)

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=False)
    ):
        assert fight.expire_conditions(target, ON_A_GM_TURN) == []

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ):
        assert fight.expire_conditions(target, ON_A_GM_TURN) == [POISONED]


# --- Glass Snake -------------------------------------------------------------


def _snake(**overrides) -> Adversary:
    defaults = dict(
        features=["Armor-Shredding Shards", "Spinning Serpent", "Spitter"],
        hp_max=5,
        stress_max=3,
        difficulty=14,
        attack_modifier=2,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=2,
    )
    defaults.update(overrides)
    return _adversary("Glass Snake", **defaults)


def test_shards_cost_a_melee_attacker_an_armor_slot():
    from features.adversaries import armor_shredding_shards

    snake = _snake()
    fight = _fight(adversaries=[snake])
    attacker = fight.party[0]

    armor_shredding_shards(snake, attacker, find_weapon("Broadsword"), fight)

    assert attacker.armor_marked == 1


def test_shards_do_not_reach_someone_attacking_from_further_off():
    from features.adversaries import armor_shredding_shards

    snake = _snake()
    fight = _fight(adversaries=[snake])
    attacker = fight.party[0]

    armor_shredding_shards(snake, attacker, find_weapon("Shortbow"), fight)

    assert attacker.armor_marked == 0
    assert attacker.hp_marked == 0


def test_shards_cost_an_hp_when_there_is_no_armor_left():
    from features.adversaries import armor_shredding_shards

    snake = _snake()
    fight = _fight(party=_party(armor_max=0), adversaries=[snake])
    attacker = fight.party[0]

    armor_shredding_shards(snake, attacker, find_weapon("Broadsword"), fight)

    assert attacker.hp_marked == 1


def test_spinning_serpent_costs_a_stress():
    from features.adversaries import spinning_serpent

    snake = _snake()
    snake.mark_hp(1)  # 4 unmarked, inside the three-slot threshold
    fight = _fight(party=_party(armor_max=0), adversaries=[snake])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        spinning_serpent(snake, fight.party[0], fight)

    assert snake.stress_marked == 1


def test_spitter_buys_the_die_and_an_extra_spotlight_once():
    from features.adversaries import SPITTER_DIE_TOKEN, spitter

    snake = _snake()
    fight = _fight(adversaries=[snake], fear=2)

    assert spitter(snake, fight.party[0], fight) is not None
    assert fight.token_count(snake, SPITTER_DIE_TOKEN) == 1
    assert fight.granted_activations(snake) == 1
    assert fight.fear == 1

    # Bought already, so there is nothing left to buy.
    assert spitter(snake, fight.party[0], fight) is None
    assert fight.granted_activations(snake) == 1


def test_the_spitter_die_does_nothing_until_it_is_bought():
    from features.adversaries import spitter_die_rolls

    snake = _snake()
    fight = _fight(party=_party(armor_max=0), adversaries=[snake])

    with patch("features.adversaries.random.randint", return_value=6):
        spitter_die_rolls(snake, fight)

    assert not any(pc.hp_marked for pc in fight.party)


def test_the_spitter_die_sprays_on_a_five_or_higher():
    from features.adversaries import spitter, spitter_die_rolls

    snake = _snake()
    fight = _fight(party=_party(armor_max=0), adversaries=[snake], fear=2)
    spitter(snake, fight.party[0], fight)

    with patch("features.adversaries.random.randint", return_value=5), patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=False)
    ):
        spitter_die_rolls(snake, fight)

    assert any(pc.hp_marked for pc in fight.party)


def test_the_spitter_die_holds_its_fire_below_five():
    from features.adversaries import spitter, spitter_die_rolls

    snake = _snake()
    fight = _fight(party=_party(armor_max=0), adversaries=[snake], fear=2)
    spitter(snake, fight.party[0], fight)

    with patch("features.adversaries.random.randint", return_value=4):
        spitter_die_rolls(snake, fight)

    assert not any(pc.hp_marked for pc in fight.party)


def test_a_pc_who_makes_the_reaction_roll_dodges_the_spray():
    from features.adversaries import spitter, spitter_die_rolls

    snake = _snake()
    fight = _fight(party=_party(armor_max=0), adversaries=[snake], fear=2)
    spitter(snake, fight.party[0], fight)

    with patch("features.adversaries.random.randint", return_value=6), patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ):
        spitter_die_rolls(snake, fight)

    assert not any(pc.hp_marked for pc in fight.party)


# --- Group Attack ------------------------------------------------------------
#
# Field sizes here are chosen so the area rule's spread roll can't bite: at three
# adversaries Close reaches 2 and at four it reaches 3, and CLOSE_CAP is 3, so
# the cap is a no-op at both. A test in tests/ may not depend on how a die fell.


def _rat(**overrides) -> Adversary:
    """The printed Giant Rat: a Minion whose attack is a flat 1, with no dice."""
    defaults = dict(
        features=["Minion (3)", "Group Attack"],
        hp_max=1,
        stress_max=1,
        difficulty=10,
        attack_modifier=-4,
        damage_dice=[],
        damage_modifier=1,
        # The book prints `Thresholds: None`, which is the half of Minion (X)
        # that needs no code - so the fixture has to carry it for that to be
        # what these tests are actually showing.
        major_threshold=NO_THRESHOLD,
        severe_threshold=NO_THRESHOLD,
    )
    defaults.update(overrides)
    return _adversary("Giant Rat", **defaults)


def test_group_attack_combines_the_damage_of_everyone_it_sweeps():
    """Four Rats, three of them in range, a flat 1 each - so a shared hit for 3."""
    from features.adversaries import group_attack

    rats = [_rat() for _ in range(4)]
    fight = _fight(party=_party(armor_max=0), adversaries=rats, fear=2)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = group_attack(rats[0], fight.party[0], fight)

    assert result.damage_roll.total == 3
    assert fight.fear == 1


def test_group_attack_spotlights_the_swarm_without_charging_for_them():
    """One activation, but every Minion in it is done for the turn."""
    from features.adversaries import group_attack

    rats = [_rat() for _ in range(4)]
    fight = _fight(party=_party(armor_max=0), adversaries=rats, fear=2)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        group_attack(rats[0], fight.party[0], fight)

    # The holder's own activation belongs to the loop, so it isn't consumed here.
    assert fight.consumed_activations(rats[0]) == 0
    assert fight.consumed_activations(rats[1]) == 1
    assert fight.consumed_activations(rats[2]) == 1
    # The fourth was out of range and is untouched.
    assert fight.consumed_activations(rats[3]) == 0


def test_group_attack_declines_when_it_reaches_too_few():
    """At two Rats, Close reaches one - which is just that Rat's own attack."""
    from features.adversaries import group_attack

    rats = [_rat() for _ in range(2)]
    fight = _fight(adversaries=rats, fear=2)

    assert group_attack(rats[0], fight.party[0], fight) is None
    assert fight.fear == 2


def test_group_attack_declines_without_the_fear():
    from features.adversaries import group_attack

    rats = [_rat() for _ in range(4)]
    fight = _fight(adversaries=rats, fear=0)

    assert group_attack(rats[0], fight.party[0], fight) is None


def test_group_attack_only_sweeps_minions_of_the_same_stat_block():
    """"All Giant Rats" is the swarm, not everything on the GM's side."""
    from features.adversaries import group_attack

    rats = [_rat() for _ in range(3)]
    bear = _adversary("Bear", features=["Bite"])
    fight = _fight(party=_party(armor_max=0), adversaries=[*rats, bear], fear=2)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = group_attack(rats[0], fight.party[0], fight)

    # Three Rats, so Close reaches two of them: a flat 1 each.
    assert result.damage_roll.total == 2
    assert fight.consumed_activations(bear) == 0


def test_grab_and_drag_is_not_policied_into_never_firing():
    """It deals less than the standard attack, which is a fact about damage only.

    The Restrain that justifies it at a table has no representation here, and
    that is a gap of ours rather than a reason for a GM never to use it.
    """
    defender = _adversary("Deeproot Defender", features=["Grab and Drag"])
    fight = _fight(fear=1)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        assert grab_and_drag(defender, fight.party[0], fight) is not None
