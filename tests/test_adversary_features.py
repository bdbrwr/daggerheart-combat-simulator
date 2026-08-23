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
from content.damage_types import DamageType
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
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityOutcome, DualityRollResult
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
        # Every real stat block prints one, and an untyped attack now means a
        # type restriction can never fire - so the default here mirrors the
        # catalogue rather than leaving test damage in a state no page has.
        damage_type="physical",
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
    assert (
        weak_structure(
            construct, amount=9, hp_to_mark=2, damage_type=DamageType.PHYSICAL
        )
        == 3
    )


def test_weak_structure_adds_nothing_to_a_hit_that_marked_nothing():
    """"When the Construct marks HP" - a hit softened away marked none."""
    construct = _adversary("Construct", features=["Weak Structure"])
    assert (
        weak_structure(
            construct, amount=9, hp_to_mark=0, damage_type=DamageType.PHYSICAL
        )
        == 0
    )


def test_weak_structure_leaves_magic_damage_alone():
    """"From physical damage" - the restriction the page prints."""
    construct = _adversary("Construct", features=["Weak Structure"])
    assert (
        weak_structure(construct, amount=9, hp_to_mark=2, damage_type=DamageType.MAGIC)
        == 2
    )


def test_weak_structure_leaves_untyped_damage_alone():
    """Untyped damage matches no restriction, so a gap costs nothing extra."""
    construct = _adversary("Construct", features=["Weak Structure"])
    assert weak_structure(construct, amount=9, hp_to_mark=2) == 2


def test_weak_structure_reaches_the_construct_through_dispatch():
    construct = _adversary("Construct", features=["Weak Structure"])
    assert (
        harden_damage(
            construct, amount=9, hp_to_mark=1, damage_type=DamageType.PHYSICAL
        )
        == 2
    )


def test_an_adversary_without_it_takes_the_hit_unchanged():
    assert (
        harden_damage(_adversary(), amount=9, hp_to_mark=1, damage_type=DamageType.PHYSICAL)
        == 1
    )


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
# it.
#
# `targets_reached` draws one `random.random()` and walks `reach_outcomes` in
# order, and Melee lists its bunched case first - so a draw of zero is bunched
# and a draw near one is scattered. These used to patch `randint`, which the band
# rules stopped using when they moved to a single draw, and so pinned nothing.


def _bunched():
    return patch("content.aoe.random.random", lambda: 0.0)


def _scattered():
    return patch("content.aoe.random.random", lambda: 0.999)


def _wolf(**overrides) -> Adversary:
    """The printed Dire Wolf: 4 HP, 3 Stress, a 1d6+2 standard attack.

    Pack Tactics carries its parameter here exactly as `srd.json` does. It became
    parameterised in batch 8, when the Sylvan Soldier turned up with the same
    feature name, different dice and no Fear clause - so the two terms are the
    Wolf's printed text, and a bare `Pack Tactics` now correctly does nothing.
    """
    defaults = dict(
        features=["Pack Tactics (1d6+5, Fear)", "Hobbling Strike"],
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
        dice, modifier = pack_tactics(wolves[0], fight.party[0], None, fight)

    assert dice == [DiceGroup(count=1, sides=6)]
    assert modifier == 5
    assert fight.fear == 1


def test_a_scattered_pair_of_wolves_gets_nothing():
    """Two wolves converge on one PC about half the time, not always."""
    from features.adversaries import pack_tactics

    wolves = [_wolf(), _wolf()]
    fight = _fight(adversaries=wolves, fear=0)

    with _scattered():
        assert pack_tactics(wolves[0], fight.party[0], None, fight) is None
    assert fight.fear == 0


def test_a_big_enough_pack_always_converges():
    """At six the Melee band reaches 3 or 2, and either clears the bar of 2."""
    from features.adversaries import pack_tactics

    wolves = [_wolf() for _ in range(6)]
    fight = _fight(adversaries=wolves, fear=0)

    for spread in (_bunched, _scattered):
        with spread():
            assert pack_tactics(wolves[0], fight.party[0], None, fight) is not None


def test_a_lone_wolf_gets_nothing_from_pack_tactics():
    from features.adversaries import pack_tactics

    wolf = _wolf()
    fight = _fight(adversaries=[wolf], fear=0)

    for spread in (_bunched, _scattered):
        with spread():
            assert pack_tactics(wolf, fight.party[0], None, fight) is None
    assert fight.fear == 0


def test_pack_tactics_does_not_count_a_bear_as_a_packmate():
    from features.adversaries import pack_tactics

    wolf, bear = _wolf(), _adversary("Bear")
    fight = _fight(adversaries=[wolf, bear], fear=0)

    with _bunched():
        assert pack_tactics(wolf, fight.party[0], None, fight) is None


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

    assert horde(_mosquitoes(), None, None, _fight()) is None


def test_a_horde_thinned_to_half_deals_its_parameter_instead():
    from features.adversaries import horde

    swarm = _mosquitoes()
    swarm.mark_hp(3)  # half of 6

    dice, modifier = horde(swarm, None, None, _fight())

    assert dice == [DiceGroup(count=1, sides=4)]
    assert modifier == 1


def test_a_horde_without_a_parameter_guesses_nothing():
    from features.adversaries import horde

    swarm = _mosquitoes(features=["Horde"])
    swarm.mark_hp(6)

    assert horde(swarm, None, None, _fight()) is None


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

    armor_shredding_shards(snake, attacker, find_weapon("Broadsword"), 7, 1, fight)

    assert attacker.armor_marked == 1


def test_shards_do_not_reach_someone_attacking_from_further_off():
    from features.adversaries import armor_shredding_shards

    snake = _snake()
    fight = _fight(adversaries=[snake])
    attacker = fight.party[0]

    armor_shredding_shards(snake, attacker, find_weapon("Shortbow"), 7, 1, fight)

    assert attacker.armor_marked == 0
    assert attacker.hp_marked == 0


def test_shards_cost_an_hp_when_there_is_no_armor_left():
    from features.adversaries import armor_shredding_shards

    snake = _snake()
    fight = _fight(party=_party(armor_max=0), adversaries=[snake])
    attacker = fight.party[0]

    armor_shredding_shards(snake, attacker, find_weapon("Broadsword"), 7, 1, fight)

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


# --- Fall Back ---------------------------------------------------------------
#
# The Harrier's counter goes through `attack_with`, since the trigger is a PC
# swinging at it - so these patch both rollers: the PC's duality roll in
# items/weapons.py and the Harrier's d20 in adversaries/adversary.py.


def _harrier(**overrides) -> Adversary:
    """The printed Harrier: 3 HP, 3 Stress, a 1d6+2 javelin at Close."""
    defaults = dict(
        features=["Maintain Distance", "Fall Back"],
        hp_max=3,
        stress_max=3,
        difficulty=12,
        attack_modifier=1,
        damage_dice=[DiceGroup(count=1, sides=6)],
        damage_modifier=2,
        range="Close",
    )
    defaults.update(overrides)
    return _adversary("Harrier", **defaults)


def test_fall_back_counters_a_melee_attacker_for_a_stress():
    from items.weapons import attack_with

    harrier = _harrier()
    fight = _fight(party=_party(armor_max=0), adversaries=[harrier])
    attacker = fight.party[0]

    with patch(
        "items.weapons.roll_duality", return_value=_duality(succeeds=True)
    ), patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        attack_with(
            attacker, find_weapon("Broadsword"), harrier, fight=fight
        )

    assert harrier.stress_marked == 1
    assert attacker.hp_marked >= 1


def test_the_attack_fall_back_interrupts_still_happens():
    """The ruling: a Reaction that gives ground doesn't veto the swing."""
    from items.weapons import attack_with

    harrier = _harrier()
    fight = _fight(party=_party(armor_max=0), adversaries=[harrier])

    with patch(
        "items.weapons.roll_duality", return_value=_duality(succeeds=True)
    ), patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = attack_with(
            fight.party[0], find_weapon("Broadsword"), harrier, fight=fight
        )

    assert result.damage_roll is not None
    assert harrier.hp_marked >= 1


def test_fall_back_ignores_an_attacker_who_never_closed():
    """Read off the weapon: a Shortbow reaches Far, so nobody moved into Melee."""
    from items.weapons import attack_with

    harrier = _harrier()
    fight = _fight(party=_party(armor_max=0), adversaries=[harrier])

    with patch(
        "items.weapons.roll_duality", return_value=_duality(succeeds=True)
    ), patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        attack_with(fight.party[0], find_weapon("Shortbow"), harrier, fight=fight)

    assert harrier.stress_marked == 0
    assert not any(pc.hp_marked for pc in fight.party)


def test_fall_back_is_not_gated_on_how_hurt_the_harrier_is():
    """A Reaction, so the Stress-desperation rule deliberately doesn't apply."""
    from features.adversaries import fall_back

    harrier = _harrier()
    harrier.spend_stress(2)  # one slot left, and 3 unmarked HP against a threshold of 2
    fight = _fight(party=_party(armor_max=0), adversaries=[harrier])

    assert harrier.will_spend_stress(1) is False, "an Action could not spend this slot"

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        fall_back(harrier, fight.party[0], find_weapon("Broadsword"), fight)

    assert harrier.stress_marked == 3


def test_fall_back_declines_when_the_stress_is_gone():
    from features.adversaries import fall_back

    harrier = _harrier(stress_max=1)
    harrier.spend_stress(1)
    fight = _fight(party=_party(armor_max=0), adversaries=[harrier])

    fall_back(harrier, fight.party[0], find_weapon("Broadsword"), fight)

    assert not any(pc.hp_marked for pc in fight.party)


def test_maintain_distance_is_declared_as_having_no_combat_effect():
    assert assess("adversary:Maintain Distance").status is Status.NO_COMBAT_EFFECT
    assert assess("adversary:Maintain Distance").reason


# --- Hobbling Shot, and a condition that hobbles a trait ----------------------


def _archer(**overrides) -> Adversary:
    """The printed Archer Guard: 3 HP, 2 Stress, a 1d8+3 longbow at Far."""
    defaults = dict(
        features=["Hobbling Shot"],
        hp_max=3,
        stress_max=2,
        difficulty=10,
        attack_modifier=1,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=3,
        range="Far",
    )
    defaults.update(overrides)
    return _adversary("Archer Guard", **defaults)


def test_hobbling_shot_costs_a_stress_and_hobbles_whoever_it_wounds():
    from features.adversaries import HOBBLED, hobbling_shot

    archer = _archer()
    fight = _fight(party=_party(armor_max=0), adversaries=[archer])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        hobbling_shot(archer, target, fight)

    assert archer.stress_marked == 1
    assert fight.has_condition(target, HOBBLED)
    assert fight.disadvantaged_on(target, "agility") is True
    assert fight.disadvantaged_on(target, "strength") is False


def test_a_healthy_archer_still_takes_the_shot():
    """3 HP against two Stress: the desperation rule never holds this back."""
    from features.adversaries import hobbling_shot

    archer = _archer()
    fight = _fight(party=_party(armor_max=0), adversaries=[archer])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        assert hobbling_shot(archer, fight.party[0], fight) is not None


def test_hobbling_shot_pays_nothing_on_a_miss():
    from features.adversaries import HOBBLED, hobbling_shot

    archer = _archer()
    fight = _fight(adversaries=[archer])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(1)):
        hobbling_shot(archer, fight.party[0], fight)

    assert archer.stress_marked == 0
    assert not fight.has_condition(fight.party[0], HOBBLED)


def test_a_hit_that_marked_no_hp_hobbles_nobody():
    """"If the target marks HP from this attack" - armor can swallow it whole."""
    from features.adversaries import HOBBLED, hobbling_shot

    archer = _archer()
    # Thresholds out of reach, so 1d12+3 lands in the lowest band and marks 1 HP
    # - which the free Armor Slot then takes back down to none.
    fight = _fight(
        party=_party(armor_max=2, major_threshold=100, severe_threshold=200),
        adversaries=[archer],
    )
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        hobbling_shot(archer, target, fight)

    assert target.hp_marked == 0
    assert archer.stress_marked == 1, "the Stress is still paid for the hit"
    assert not fight.has_condition(target, HOBBLED)


def test_the_hobble_lifts_only_once_an_hp_is_cleared():
    from features.adversaries import HOBBLED, hobbling_shot

    archer = _archer()
    fight = _fight(party=_party(armor_max=0), adversaries=[archer])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        hobbling_shot(archer, target, fight)

    fight.expire_conditions(target, WHEN_THEY_ACT)
    fight.expire_conditions(target, ON_A_GM_TURN)
    assert fight.has_condition(target, HOBBLED)

    target.clear_hp(1)
    assert fight.expire_conditions(target, WHEN_THEY_ACT) == [HOBBLED]


def test_a_hobbled_pc_rolls_an_agility_weapon_at_disadvantage():
    """The condition has to reach the roll, or it is a record of nothing."""
    from features.adversaries import HOBBLED
    from items.weapons import attack_with

    fight = _fight()
    attacker = fight.party[0]
    fight.apply_condition(
        attacker, Condition(name=HOBBLED, disadvantage_on=("agility",))
    )

    with patch(
        "items.weapons.roll_duality", return_value=_duality(succeeds=True)
    ) as rolled:
        attack_with(
            attacker, find_weapon("Shortbow"), fight.adversaries[0], fight=fight
        )

    assert rolled.call_args.kwargs["advantage_state"] is AdvantageState.DISADVANTAGE


def test_advantage_and_a_hobble_cancel_each_other_out():
    from features.adversaries import HOBBLED
    from items.weapons import attack_with

    fight = _fight()
    attacker = fight.party[0]
    fight.apply_condition(
        attacker, Condition(name=HOBBLED, disadvantage_on=("agility",))
    )

    with patch(
        "items.weapons.roll_duality", return_value=_duality(succeeds=True)
    ) as rolled:
        attack_with(
            attacker,
            find_weapon("Shortbow"),
            fight.adversaries[0],
            AdvantageState.ADVANTAGE,
            fight=fight,
        )

    assert rolled.call_args.kwargs["advantage_state"] is AdvantageState.NONE


def test_an_unhobbled_pc_rolls_as_normal():
    from items.weapons import attack_with

    fight = _fight()

    with patch(
        "items.weapons.roll_duality", return_value=_duality(succeeds=True)
    ) as rolled:
        attack_with(
            fight.party[0], find_weapon("Shortbow"), fight.adversaries[0], fight=fight
        )

    assert rolled.call_args.kwargs["advantage_state"] is AdvantageState.NONE


# --- Detain ------------------------------------------------------------------


def _bladed_guard(**overrides) -> Adversary:
    """A Bladed Guard whose printed attack is unmistakable.

    1d4+10 rather than the page's 1d6+1, deliberately: the point of these tests
    is that Detain rolls the *standard* damage, and a number no feature's own
    dice could produce is what shows it.
    """
    defaults = dict(
        features=["Shield Wall", "Detain"],
        hp_max=5,
        stress_max=2,
        difficulty=12,
        attack_modifier=1,
        damage_dice=[DiceGroup(count=1, sides=4)],
        damage_modifier=10,
    )
    defaults.update(overrides)
    return _adversary("Bladed Guard", **defaults)


def test_detain_deals_the_adversarys_standard_damage():
    from features.adversaries import detain

    guard = _bladed_guard()
    fight = _fight(party=_party(armor_max=0), adversaries=[guard])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = detain(guard, fight.party[0], fight)

    assert result.damage_roll.total >= 11
    assert guard.stress_marked == 1


def test_detain_keeps_its_stress_on_a_miss():
    from features.adversaries import detain

    guard = _bladed_guard()
    fight = _fight(adversaries=[guard])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(1)):
        detain(guard, fight.party[0], fight)

    assert guard.stress_marked == 0


def test_shield_wall_is_declared_as_having_no_combat_effect():
    assert assess("adversary:Shield Wall").status is Status.NO_COMBAT_EFFECT
    assert assess("adversary:Shield Wall").reason


# --- Rally Guards ------------------------------------------------------------


def _head_guard(**overrides) -> Adversary:
    """The printed Head Guard: 7 HP, 3 Stress, a 1d10+4 mace."""
    defaults = dict(
        features=["Rally Guards", "On My Signal (5)", "Momentum"],
        hp_max=7,
        stress_max=3,
        difficulty=15,
        attack_modifier=4,
        damage_dice=[DiceGroup(count=1, sides=10)],
        damage_modifier=4,
    )
    defaults.update(overrides)
    return _adversary("Head Guard", **defaults)


def test_rally_guards_spends_two_fear_and_hands_out_spotlights():
    from features.adversaries import rally_guards

    head, allies = _head_guard(), [_archer() for _ in range(3)]
    fight = _fight(adversaries=[head, *allies], fear=3)

    result = rally_guards(head, fight.party[0], fight)

    assert fight.fear == 1
    assert result.made_an_attack is False
    assert fight.granted_activations(head) == 1
    assert sum(fight.granted_activations(ally) for ally in allies) >= 1


def test_rally_guards_declines_without_the_fear():
    from features.adversaries import rally_guards

    head = _head_guard()
    fight = _fight(adversaries=[head, _archer()], fear=1)

    assert rally_guards(head, fight.party[0], fight) is None
    assert fight.fear == 1


# --- On My Signal ------------------------------------------------------------
#
# The countdown ticks from the party's rolls, so these drive it through the
# dispatch rather than calling the feature's halves in sequence. Far reaches
# everyone unless the spread roll falls short (1 in 4), so it is pinned rather
# than sampled wherever the count matters.


def _all_in_range():
    """Pin the spread roll so Far reaches the whole field.

    Far lists its one-in-four "falls short" case *first* in `reach_outcomes`, so
    a draw near one selects the other branch and everybody is in range. It used
    to patch `randint`, which the band rules stopped using when they moved to a
    single `random.random()` draw - so this pinned nothing and the volley's size
    was a real random draw.

    Worth knowing what it does beyond the band: `content.aoe.random` *is* the
    `random` module, so pinning `random.random` pins that call everywhere - which
    is why the volley's own roller is patched alongside it, and patched where the
    feature calls it (`features.adversaries.roll_d20`) rather than where an
    ordinary adversary attack does.
    """
    return patch("content.aoe.random.random", lambda: 0.999)


def _archers_that_deal(flat: int, count: int) -> list[Adversary]:
    """Archer Guards whose damage is a flat number, so a total can be asserted."""
    return [
        _archer(damage_dice=[], damage_modifier=flat, attack_modifier=0)
        for _ in range(count)
    ]


def test_the_countdown_arms_once_on_the_first_spotlight():
    from features.adversaries import (
        ON_MY_SIGNAL_COUNTDOWN,
        on_my_signal_arms,
    )

    head = _head_guard()
    fight = _fight(adversaries=[head])

    on_my_signal_arms(head, fight)
    assert fight.token_count(head, ON_MY_SIGNAL_COUNTDOWN) == 5

    fight.set_token(head, ON_MY_SIGNAL_COUNTDOWN, 2)
    on_my_signal_arms(head, fight)
    assert fight.token_count(head, ON_MY_SIGNAL_COUNTDOWN) == 2, "it does not re-arm"


def test_a_head_guard_without_a_number_arms_nothing():
    from features.adversaries import ON_MY_SIGNAL_COUNTDOWN, on_my_signal_arms

    head = _head_guard(features=["On My Signal"])
    fight = _fight(adversaries=[head])

    on_my_signal_arms(head, fight)

    assert fight.token_count(head, ON_MY_SIGNAL_COUNTDOWN) == 0


def test_the_countdown_ticks_on_a_pc_attack_roll_and_fires_at_zero():
    from content.registry import apply_on_party_attack_roll
    from features.adversaries import on_my_signal_arms

    head = _head_guard()
    archers = _archers_that_deal(flat=5, count=2)
    # Thresholds set so a combined volley crosses a band two separate hits
    # could not: 5 apiece marks 1 HP each, while 10 at once is Severe.
    fight = _fight(
        party=_party(armor_max=0, major_threshold=6, severe_threshold=10),
        adversaries=[head, *archers],
    )
    target = fight.party[0]
    fight.last_pc_to_attack = target

    on_my_signal_arms(head, fight)
    roll = _duality(succeeds=True)

    with _all_in_range(), patch(
        "features.adversaries.roll_d20", return_value=_d20(19)
    ):
        for _ in range(4):
            apply_on_party_attack_roll(target, roll, fight)
        assert target.hp_marked == 0, "four ticks is not five"

        apply_on_party_attack_roll(target, roll, fight)

    assert target.hp_marked == 3, "two hits of 5, combined into one Severe 10"


def test_the_countdown_fires_only_once():
    from content.registry import apply_on_party_attack_roll
    from features.adversaries import on_my_signal_arms

    head = _head_guard()
    archers = _archers_that_deal(flat=5, count=2)
    fight = _fight(
        party=_party(armor_max=0, major_threshold=6, severe_threshold=10),
        adversaries=[head, *archers],
    )
    target = fight.party[0]
    fight.last_pc_to_attack = target

    on_my_signal_arms(head, fight)
    roll = _duality(succeeds=True)

    with _all_in_range(), patch(
        "features.adversaries.roll_d20", return_value=_d20(19)
    ):
        for _ in range(8):
            apply_on_party_attack_roll(target, roll, fight)

    assert target.hp_marked == 3, "the whistle is spent, not re-armed"


def test_the_signal_does_nothing_with_no_archers_to_answer_it():
    from content.registry import apply_on_party_attack_roll
    from features.adversaries import on_my_signal_arms

    head = _head_guard()
    fight = _fight(party=_party(armor_max=0), adversaries=[head])
    fight.last_pc_to_attack = fight.party[0]

    on_my_signal_arms(head, fight)
    roll = _duality(succeeds=True)

    # Nothing to patch: with no archers on the field the signal never rolls.
    for _ in range(5):
        apply_on_party_attack_roll(fight.party[0], roll, fight)

    assert not any(pc.hp_marked for pc in fight.party)


def test_a_volley_that_misses_entirely_costs_nothing():
    from content.registry import apply_on_party_attack_roll
    from features.adversaries import on_my_signal_arms

    head = _head_guard()
    archers = _archers_that_deal(flat=5, count=2)
    fight = _fight(party=_party(armor_max=0), adversaries=[head, *archers])
    target = fight.party[0]
    fight.last_pc_to_attack = target

    on_my_signal_arms(head, fight)
    roll = _duality(succeeds=True)

    with _all_in_range(), patch(
        "features.adversaries.roll_d20", return_value=_d20(1)
    ):
        for _ in range(5):
            apply_on_party_attack_roll(target, roll, fight)

    assert target.hp_marked == 0


# --- Curse -------------------------------------------------------------------


def _hexer(**overrides) -> Adversary:
    """The printed Jagged Knife Hexer: 4 HP, 4 Stress, a 1d6+2 staff at Far."""
    defaults = dict(
        features=["Curse", "Chaotic Flux"],
        hp_max=4,
        stress_max=4,
        difficulty=13,
        attack_modifier=2,
        damage_dice=[DiceGroup(count=1, sides=6)],
        damage_modifier=2,
        range="Far",
    )
    defaults.update(overrides)
    return _adversary("Jagged Knife Hexer", **defaults)


def _rolled_with(hope: int, fear: int) -> DualityRollResult:
    return DualityRollResult(
        hope_die_result=hope,
        fear_die_result=fear,
        modifier=2,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=10,
    )


def test_curse_applies_the_condition_without_attacking():
    from features.adversaries import CURSED, curse

    hexer = _hexer()
    fight = _fight(adversaries=[hexer])
    target = fight.party[0]

    result = curse(hexer, target, fight)

    assert fight.has_condition(target, CURSED)
    assert result.made_an_attack is False
    assert hexer.stress_marked == 0, "applying it costs nothing"


def test_curse_declines_against_an_already_cursed_target():
    from features.adversaries import curse

    hexer = _hexer()
    fight = _fight(adversaries=[hexer])
    target = fight.party[0]

    curse(hexer, target, fight)

    assert curse(hexer, target, fight) is None


def test_a_curse_lasts_the_rest_of_the_fight():
    """Ruled: a temporary condition on a PC runs to their next rest."""
    from features.adversaries import CURSED, curse

    hexer = _hexer()
    fight = _fight(adversaries=[hexer])
    target = fight.party[0]

    curse(hexer, target, fight)
    fight.expire_conditions(target, WHEN_THEY_ACT)
    fight.expire_conditions(target, ON_A_GM_TURN)

    assert fight.has_condition(target, CURSED)


def test_a_cursed_roll_with_hope_becomes_one_with_fear():
    from content.registry import converted_party_roll
    from dice.duality import DualityOutcome
    from features.adversaries import curse

    hexer = _hexer()
    fight = _fight(adversaries=[hexer])
    target = fight.party[0]
    curse(hexer, target, fight)

    rolled = _rolled_with(hope=9, fear=3)
    converted = converted_party_roll(target, rolled, fight)

    assert rolled.outcome is DualityOutcome.HOPE
    assert converted.outcome is DualityOutcome.FEAR
    assert converted.total == rolled.total, "the swap must not move the total"
    assert converted.is_success == rolled.is_success
    assert hexer.stress_marked == 1


def test_a_roll_already_with_fear_is_left_alone():
    from content.registry import converted_party_roll
    from features.adversaries import curse

    hexer = _hexer()
    fight = _fight(adversaries=[hexer])
    target = fight.party[0]
    curse(hexer, target, fight)

    rolled = _rolled_with(hope=3, fear=9)

    assert converted_party_roll(target, rolled, fight) is rolled
    assert hexer.stress_marked == 0


def test_an_uncursed_pcs_roll_is_left_alone():
    from content.registry import converted_party_roll

    hexer = _hexer()
    fight = _fight(adversaries=[hexer])

    rolled = _rolled_with(hope=9, fear=3)

    assert converted_party_roll(fight.party[0], rolled, fight) is rolled
    assert hexer.stress_marked == 0


def test_a_hexer_out_of_stress_cannot_convert():
    from content.registry import converted_party_roll
    from features.adversaries import curse

    hexer = _hexer(stress_max=1)
    fight = _fight(adversaries=[hexer])
    target = fight.party[0]
    curse(hexer, target, fight)
    hexer.spend_stress(1)

    rolled = _rolled_with(hope=9, fear=3)

    assert converted_party_roll(target, rolled, fight) is rolled


def test_the_conversion_is_not_gated_on_how_hurt_the_hexer_is():
    """A Reaction, so the Stress-desperation rule deliberately doesn't apply."""
    from content.registry import converted_party_roll
    from dice.duality import DualityOutcome
    from features.adversaries import curse

    hexer = _hexer()
    hexer.spend_stress(3)  # one slot left, and 4 unmarked HP against a threshold of 2
    fight = _fight(adversaries=[hexer])
    target = fight.party[0]
    curse(hexer, target, fight)

    assert hexer.will_spend_stress(1) is False, "an Action could not spend this slot"

    converted = converted_party_roll(target, _rolled_with(hope=9, fear=3), fight)
    assert converted.outcome is DualityOutcome.FEAR
    assert hexer.stress_marked == 4


# --- Chaotic Flux ------------------------------------------------------------


def test_chaotic_flux_costs_a_stress_and_lands_on_whoever_it_reaches():
    from features.adversaries import chaotic_flux

    hexer = _hexer()
    fight = _fight(party=_party(armor_max=0), adversaries=[hexer])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = chaotic_flux(hexer, fight.party[0], fight)

    assert hexer.stress_marked == 1
    # 2d6+3, so at least 5 - it brought dice of its own rather than the staff's.
    assert result.damage_roll.total >= 5
    assert any(pc.hp_marked for pc in fight.party)


def test_chaotic_flux_reaches_at_most_three():
    from features.adversaries import CHAOTIC_FLUX_TARGETS, chaotic_flux

    hexer = _hexer()
    fight = _fight(party=_party(size=12, armor_max=0), adversaries=[hexer])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        chaotic_flux(hexer, fight.party[0], fight)

    hurt = sum(1 for pc in fight.party if pc.hp_marked)
    assert 1 <= hurt <= CHAOTIC_FLUX_TARGETS


def test_chaotic_flux_declines_without_the_stress():
    from features.adversaries import chaotic_flux

    hexer = _hexer(stress_max=0)
    fight = _fight(adversaries=[hexer])

    assert chaotic_flux(hexer, fight.party[0], fight) is None


# --- Hold Them Down, and a Restrain that is recorded -------------------------
#
# Restrained still does nothing on its own. What these check is that it is
# written down, with its source, so that content keying on it can ask - and that
# both printed ways out of a hold work.


def _kneebreaker(**overrides) -> Adversary:
    """The printed Kneebreaker: 7 HP, 4 Stress, a 1d4+6 club."""
    defaults = dict(
        features=["I've Got 'Em", "Hold Them Down"],
        hp_max=7,
        stress_max=4,
        difficulty=12,
        major_threshold=7,
        severe_threshold=14,
        attack_modifier=-3,
        damage_dice=[DiceGroup(count=1, sides=4)],
        damage_modifier=6,
    )
    defaults.update(overrides)
    return _adversary("Jagged Knife Kneebreaker", **defaults)


def test_hold_them_down_deals_no_damage_and_applies_both_conditions():
    from content.conditions import RESTRAINED
    from features.adversaries import hold_them_down

    kneebreaker = _kneebreaker()
    fight = _fight(party=_party(armor_max=0), adversaries=[kneebreaker])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = hold_them_down(kneebreaker, target, fight)

    assert result.damage_roll.total == 0, "the target takes no damage"
    assert target.hp_marked == 0
    assert fight.has_condition(target, RESTRAINED)
    assert fight.has_condition(target, VULNERABLE)


def test_hold_them_down_leaves_nothing_on_a_miss():
    from content.conditions import RESTRAINED
    from features.adversaries import hold_them_down

    kneebreaker = _kneebreaker()
    fight = _fight(adversaries=[kneebreaker])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(1)):
        hold_them_down(kneebreaker, fight.party[0], fight)

    assert not fight.has_condition(fight.party[0], RESTRAINED)


def test_a_successful_strength_roll_breaks_both_conditions_at_once():
    from content.conditions import RESTRAINED
    from features.adversaries import hold_them_down

    kneebreaker = _kneebreaker()
    fight = _fight(party=_party(armor_max=0), adversaries=[kneebreaker])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        hold_them_down(kneebreaker, target, fight)

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=False)
    ):
        assert fight.expire_conditions(target, WHEN_THEY_ACT) == []
        assert fight.has_condition(target, RESTRAINED)

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ):
        assert fight.expire_conditions(target, WHEN_THEY_ACT) == [RESTRAINED]

    assert not fight.has_condition(target, VULNERABLE), "both conditions lift together"


def test_major_damage_to_the_kneebreaker_frees_everyone_it_holds():
    from content.conditions import RESTRAINED
    from features.adversaries import hold_them_down, hold_them_down_releases

    kneebreaker = _kneebreaker()
    fight = _fight(party=_party(armor_max=0), adversaries=[kneebreaker])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        hold_them_down(kneebreaker, target, fight)

    hold_them_down_releases(kneebreaker, amount=6, hp_marked=1, fight=fight)
    assert fight.has_condition(target, RESTRAINED), "6 is below the Major threshold"

    hold_them_down_releases(kneebreaker, amount=7, hp_marked=2, fight=fight)
    assert not fight.has_condition(target, RESTRAINED)
    assert not fight.has_condition(target, VULNERABLE)


def test_a_kneebreaker_only_frees_the_creatures_it_is_holding_itself():
    from content.conditions import RESTRAINED
    from features.adversaries import hold_them_down_releases

    kneebreaker, other = _kneebreaker(), _kneebreaker()
    fight = _fight(adversaries=[kneebreaker, other])
    held_by_other = fight.party[0]
    fight.apply_condition(
        held_by_other, Condition(name=RESTRAINED, source=other)
    )

    hold_them_down_releases(kneebreaker, amount=14, hp_marked=3, fight=fight)

    assert fight.has_condition(held_by_other, RESTRAINED)


# --- I've Got 'Em ------------------------------------------------------------


def test_ive_got_em_doubles_an_allys_damage_against_a_creature_it_holds():
    from content.conditions import RESTRAINED
    from features.adversaries import ive_got_em

    kneebreaker, ally = _kneebreaker(), _adversary("Bear")
    fight = _fight(adversaries=[kneebreaker, ally])
    target = fight.party[0]
    fight.apply_condition(target, Condition(name=RESTRAINED, source=kneebreaker))

    assert ive_got_em(kneebreaker, target, ally, fight) == 2


def test_ive_got_em_does_not_double_the_kneebreakers_own_attacks():
    """"By other adversaries" - the Kneebreaker holds them for everyone else."""
    from content.conditions import RESTRAINED
    from features.adversaries import ive_got_em

    kneebreaker = _kneebreaker()
    fight = _fight(adversaries=[kneebreaker])
    target = fight.party[0]
    fight.apply_condition(target, Condition(name=RESTRAINED, source=kneebreaker))

    assert ive_got_em(kneebreaker, target, kneebreaker, fight) is None


def test_ive_got_em_ignores_a_creature_somebody_else_is_holding():
    from content.conditions import RESTRAINED
    from features.adversaries import ive_got_em

    kneebreaker, other = _kneebreaker(), _adversary("Deeproot Defender")
    fight = _fight(adversaries=[kneebreaker, other])
    target = fight.party[0]
    fight.apply_condition(target, Condition(name=RESTRAINED, source=other))

    assert ive_got_em(kneebreaker, target, other, fight) is None


def test_ive_got_em_ignores_a_creature_who_is_not_held():
    from features.adversaries import ive_got_em

    kneebreaker, ally = _kneebreaker(), _adversary("Bear")
    fight = _fight(adversaries=[kneebreaker, ally])

    assert ive_got_em(kneebreaker, fight.party[0], ally, fight) is None


def test_the_doubling_reaches_an_allys_attack_through_dispatch():
    """The point of the hook: the attacker knows nothing about the Kneebreaker."""
    from content.conditions import RESTRAINED
    from features.adversaries import ive_got_em  # noqa: F401 - registers the hook

    kneebreaker = _kneebreaker()
    ally = _adversary(
        "Bear", damage_dice=[], damage_modifier=5, features=[]
    )
    # Thresholds set so 5 marks 1 HP and the doubled 10 marks 2.
    fight = _fight(
        party=_party(armor_max=0, major_threshold=6, severe_threshold=20),
        adversaries=[kneebreaker, ally],
    )
    target = fight.party[0]
    fight.apply_condition(target, Condition(name=RESTRAINED, source=kneebreaker))

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        ally.attack(target, fight=fight)

    assert target.hp_marked == 2, "5 doubled to 10, which is Major"


def test_an_unheld_target_takes_the_damage_as_rolled():
    kneebreaker = _kneebreaker()
    ally = _adversary("Bear", damage_dice=[], damage_modifier=5, features=[])
    fight = _fight(
        party=_party(armor_max=0, major_threshold=6, severe_threshold=20),
        adversaries=[kneebreaker, ally],
    )

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        ally.attack(fight.party[0], fight=fight)

    assert fight.party[0].hp_marked == 1


# --- The Lieutenant ----------------------------------------------------------


def _lieutenant(**overrides) -> Adversary:
    """The printed Lieutenant: 6 HP, 3 Stress, a 1d8+3 javelin at Close."""
    defaults = dict(
        features=["Tactician", "More Where That Came From", "Coup de Grace", "Momentum"],
        hp_max=6,
        stress_max=3,
        difficulty=13,
        major_threshold=7,
        severe_threshold=14,
        attack_modifier=2,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=3,
        range="Close",
    )
    defaults.update(overrides)
    return _adversary("Jagged Knife Lieutenant", **defaults)


def test_tactician_spends_a_stress_to_hand_out_two_spotlights():
    from features.adversaries import tactician

    lieutenant = _lieutenant()
    allies = [_adversary(f"Thug {index}") for index in range(4)]
    fight = _fight(adversaries=[lieutenant, *allies])

    tactician(lieutenant, fight)

    assert lieutenant.stress_marked == 1
    granted = sum(fight.granted_activations(ally) for ally in allies)
    assert 1 <= granted <= 2


def test_tactician_does_not_spend_the_lieutenants_own_action():
    """Ruled: it fires on being spotlighted and the Lieutenant still attacks.

    Which is a fact about *which hook* it registers on, so that is what this
    checks - an Action would be one of the options competing for the spotlight,
    and this must not be.
    """
    from content import action_options
    from features.adversaries import tactician

    assert tactician not in action_options(_lieutenant())


def test_tactician_declines_with_nobody_to_direct():
    from features.adversaries import tactician

    lieutenant = _lieutenant()
    fight = _fight(adversaries=[lieutenant])

    tactician(lieutenant, fight)

    assert lieutenant.stress_marked == 0


def test_more_where_that_came_from_adds_three_lackeys_to_the_fight():
    from features.adversaries import (
        SUMMONED_COUNT,
        SUMMONED_MINION,
        more_where_that_came_from,
    )

    lieutenant = _lieutenant()
    fight = _fight(adversaries=[lieutenant])

    result = more_where_that_came_from(lieutenant, fight.party[0], fight)

    assert result.made_an_attack is False
    summoned = [a for a in fight.living_adversaries if a.name == SUMMONED_MINION]
    assert len(summoned) == SUMMONED_COUNT
    assert all(minion.hp_marked == 0 for minion in summoned)


def test_each_summon_has_its_own_hp_track():
    """Spawned, not shared - marking one must not defeat the rest."""
    from features.adversaries import SUMMONED_MINION, more_where_that_came_from

    lieutenant = _lieutenant()
    fight = _fight(adversaries=[lieutenant])
    more_where_that_came_from(lieutenant, fight.party[0], fight)

    summoned = [a for a in fight.adversaries if a.name == SUMMONED_MINION]
    summoned[0].mark_hp(1)

    assert summoned[0].is_defeated
    assert not any(minion.is_defeated for minion in summoned[1:])


def test_a_summoned_minion_can_be_targeted_and_counts_toward_victory():
    from features.adversaries import more_where_that_came_from

    lieutenant = _lieutenant()
    fight = _fight(adversaries=[lieutenant])
    lieutenant.mark_hp(lieutenant.hp_max)

    assert fight.adversaries_are_cleared

    more_where_that_came_from(lieutenant, fight.party[0], fight)

    assert not fight.adversaries_are_cleared


def test_coup_de_grace_needs_a_vulnerable_target():
    from features.adversaries import coup_de_grace

    lieutenant = _lieutenant()
    fight = _fight(adversaries=[lieutenant], fear=2)

    assert coup_de_grace(lieutenant, fight.party[0], fight) is None
    assert fight.fear == 2


def test_coup_de_grace_spends_the_fear_and_hits_for_a_great_deal():
    from features.adversaries import coup_de_grace

    lieutenant = _lieutenant()
    fight = _fight(party=_party(armor_max=0), adversaries=[lieutenant], fear=2)
    target = fight.party[0]
    fight.apply_condition(target, Condition(name=VULNERABLE))

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = coup_de_grace(lieutenant, target, fight)

    assert fight.fear == 1
    # 2d6+12, so at least 14 - far above the printed 1d8+3.
    assert result.damage_roll.total >= 14
    assert target.stress_marked == 1


def test_coup_de_grace_pays_the_fear_even_on_a_miss():
    """"Spend a Fear to make an attack" - the Fear buys the attempt."""
    from features.adversaries import coup_de_grace

    lieutenant = _lieutenant()
    fight = _fight(adversaries=[lieutenant], fear=2)
    target = fight.party[0]
    fight.apply_condition(target, Condition(name=VULNERABLE))

    with patch("adversaries.adversary.roll_d20", return_value=_d20(1)):
        coup_de_grace(lieutenant, target, fight)

    assert fight.fear == 1
    assert target.stress_marked == 0


# --- The Shadow --------------------------------------------------------------


def _shadow(**overrides) -> Adversary:
    """The printed Shadow: 3 HP, 3 Stress, a 1d4+4 dagger."""
    defaults = dict(
        features=["Backstab", "Cloaked"],
        hp_max=3,
        stress_max=3,
        difficulty=12,
        major_threshold=4,
        severe_threshold=8,
        attack_modifier=1,
        damage_dice=[DiceGroup(count=1, sides=4)],
        damage_modifier=4,
    )
    defaults.update(overrides)
    return _adversary("Jagged Knife Shadow", **defaults)


def _d20_with(die: int, advantage: AdvantageState) -> D20RollResult:
    return D20RollResult(
        die_results=[die],
        modifier=0,
        advantage_state=advantage,
        evasion=10,
    )


def test_backstab_swaps_the_damage_when_the_attack_had_advantage():
    from features.adversaries import backstab

    shadow = _shadow()
    dice, modifier = backstab(
        shadow, None, _d20_with(19, AdvantageState.ADVANTAGE), _fight()
    )

    assert dice == [DiceGroup(count=1, sides=6)]
    assert modifier == 6


def test_backstab_leaves_an_ordinary_attack_alone():
    from features.adversaries import backstab

    shadow = _shadow()

    assert backstab(shadow, None, _d20_with(19, AdvantageState.NONE), _fight()) is None
    assert backstab(shadow, None, None, _fight()) is None


def test_cloaked_grants_advantage_to_exactly_one_attack():
    from features.adversaries import CLOAKED_TOKEN, cloaked, cloaked_grants_advantage

    shadow = _shadow()
    fight = _fight(adversaries=[shadow])
    target = fight.party[0]

    assert cloaked(shadow, target, fight).made_an_attack is False
    assert fight.token_count(shadow, CLOAKED_TOKEN) == 1

    assert cloaked_grants_advantage(shadow, target, fight) is AdvantageState.ADVANTAGE
    assert cloaked_grants_advantage(shadow, target, fight) is None, "spent on the attack"


def test_cloaking_twice_over_buys_nothing():
    from features.adversaries import cloaked

    shadow = _shadow()
    fight = _fight(adversaries=[shadow])

    cloaked(shadow, fight.party[0], fight)

    assert cloaked(shadow, fight.party[0], fight) is None


def test_the_shared_advantage_rule_folds_both_sources():
    from combat.policy import adversary_attack_advantage
    from features.adversaries import cloaked

    shadow = _shadow()
    fight = _fight(adversaries=[shadow])
    target = fight.party[0]

    assert adversary_attack_advantage(shadow, target, fight) is AdvantageState.NONE

    cloaked(shadow, target, fight)
    assert adversary_attack_advantage(shadow, target, fight) is AdvantageState.ADVANTAGE

    # And a Vulnerable target grants it without any cloak at all.
    fight.apply_condition(target, Condition(name=VULNERABLE))
    assert adversary_attack_advantage(shadow, target, fight) is AdvantageState.ADVANTAGE


# --- The Minor Chaos Elemental -----------------------------------------------


def _elemental(**overrides) -> Adversary:
    """The printed Minor Chaos Elemental: 7 HP, 3 Stress, a 1d12+6 blast."""
    defaults = dict(
        features=[
            "Arcane Form",
            "Sickening Flux",
            "Remake Reality",
            "Magical Reflection",
            "Momentum",
        ],
        hp_max=7,
        stress_max=3,
        difficulty=14,
        major_threshold=7,
        severe_threshold=14,
        attack_modifier=3,
        damage_dice=[DiceGroup(count=1, sides=12)],
        damage_modifier=6,
        # Magic, unlike the fixture default - the Warp Blast is one of the two
        # tier 1 attacks that is, and Magical Reflection reads it for the type
        # its rebound deals.
        damage_type="magic",
        range="Close",
    )
    defaults.update(overrides)
    return _adversary("Minor Chaos Elemental", **defaults)


def test_an_adversary_spends_its_own_hp_but_never_its_last():
    elemental = _elemental(hp_max=7)

    assert elemental.will_spend_hp(1) is True

    elemental.mark_hp(6)  # one unmarked HP left
    assert elemental.will_spend_hp(1) is False


def test_sickening_flux_costs_an_hp_and_leaves_the_party_vulnerable():
    from features.adversaries import sickening_flux

    elemental = _elemental()
    fight = _fight(party=_party(armor_max=0), adversaries=[elemental])

    result = sickening_flux(elemental, fight.party[0], fight)

    assert elemental.hp_marked == 1
    assert result.made_an_attack is False
    caught = [pc for pc in fight.party if fight.has_condition(pc, VULNERABLE)]
    assert caught
    assert all(pc.stress_marked == 1 for pc in caught)


def test_sickening_flux_declines_on_the_elementals_last_hp():
    from features.adversaries import sickening_flux

    elemental = _elemental()
    elemental.mark_hp(6)
    fight = _fight(adversaries=[elemental])

    assert sickening_flux(elemental, fight.party[0], fight) is None
    assert elemental.hp_marked == 6


def test_the_flux_vulnerable_outlasts_acting_and_the_gm_turn():
    from features.adversaries import sickening_flux

    elemental = _elemental()
    fight = _fight(party=_party(armor_max=0), adversaries=[elemental])
    sickening_flux(elemental, fight.party[0], fight)

    caught = [pc for pc in fight.party if fight.has_condition(pc, VULNERABLE)][0]
    fight.expire_conditions(caught, WHEN_THEY_ACT)
    fight.expire_conditions(caught, ON_A_GM_TURN)

    assert fight.has_condition(caught, VULNERABLE)


def test_remake_reality_spends_a_fear_for_direct_damage():
    from features.adversaries import remake_reality

    elemental = _elemental()
    fight = _fight(party=_party(armor_max=2), adversaries=[elemental], fear=1)

    result = remake_reality(elemental, fight.party[0], fight)

    assert fight.fear == 0
    assert result.made_an_attack is False
    hurt = [pc for pc in fight.party if pc.hp_marked]
    assert hurt and all(pc.armor_marked == 0 for pc in hurt), "direct marks no slot"


def test_remake_reality_declines_without_the_fear():
    from features.adversaries import remake_reality

    elemental = _elemental()
    fight = _fight(adversaries=[elemental], fear=0)

    assert remake_reality(elemental, fight.party[0], fight) is None


def test_magical_reflection_costs_a_close_attacker_half_of_what_they_dealt():
    from features.adversaries import magical_reflection

    elemental = _elemental()
    fight = _fight(party=_party(armor_max=0), adversaries=[elemental])
    attacker = fight.party[0]

    magical_reflection(elemental, attacker, find_weapon("Broadsword"), 9, 1, fight)

    assert attacker.hp_marked >= 1


def test_magical_reflection_does_not_reach_an_archer():
    from features.adversaries import magical_reflection

    elemental = _elemental()
    fight = _fight(party=_party(armor_max=0), adversaries=[elemental])
    attacker = fight.party[0]

    magical_reflection(elemental, attacker, find_weapon("Shortbow"), 9, 1, fight)

    assert attacker.hp_marked == 0


def test_magical_reflection_halves_downward_and_ignores_a_scratch():
    from features.adversaries import magical_reflection

    elemental = _elemental()
    # Thresholds chosen so the reflected 4 marks 1 HP and nothing else would.
    fight = _fight(
        party=_party(armor_max=0, major_threshold=5, severe_threshold=20),
        adversaries=[elemental],
    )
    attacker = fight.party[0]

    magical_reflection(elemental, attacker, find_weapon("Broadsword"), 9, 1, fight)
    assert attacker.hp_marked == 1, "half of 9 is 4, which is below Major"

    magical_reflection(elemental, attacker, find_weapon("Broadsword"), 1, 1, fight)
    assert attacker.hp_marked == 1, "half of 1 rounds down to nothing"


def test_arcane_form_is_modelled():
    """It was the last unimplemented feature on any ported stat block.

    Left as a real gap for as long as nothing read damage types - never
    dismissed, because the catalogues recorded the types all along and a
    dismissal would have claimed the effect had nothing here to touch.
    """
    assert assess("adversary:Arcane Form").status is Status.MODELLED


def test_arcane_form_halves_magic_and_leaves_steel_alone():
    """The whole point of the stat block: the answer to it is a weapon choice."""
    elemental = _elemental()

    assert elemental.take_damage(13, damage_type=DamageType.MAGIC) == 1
    assert _elemental().take_damage(13, damage_type=DamageType.PHYSICAL) == 2


# --- Batch 5: the Minor Fire Elemental ---------------------------------------
#
# Scorched Earth and Hellfire share `_flames`, so the three outcomes of the
# Reaction Roll are pinned once here and Hellfire's own cases only check what is
# different about it.


def _fire_elemental(**overrides) -> Adversary:
    """The printed Minor Fire Elemental: 9 HP, 3 Stress, a 1d10+4 blast at Far."""
    defaults = dict(
        features=[
            "Relentless (2)",
            "Scorched Earth",
            "Explosion",
            "Consume Kindling",
            "Momentum",
        ],
        hp_max=9,
        stress_max=3,
        difficulty=13,
        major_threshold=7,
        severe_threshold=15,
        attack_modifier=3,
        damage_dice=[DiceGroup(count=1, sides=10)],
        damage_modifier=4,
        damage_type="magic",
        range="Far",
    )
    defaults.update(overrides)
    return _adversary("Minor Fire Elemental", **defaults)


def _fixed_damage(total: int):
    """Pin the shared damage roll `_flames` makes, so a save's half is exact."""
    return patch(
        "features.adversaries.roll_damage",
        return_value=DamageRollResult(
            dice_groups=[DiceGroup(count=1, sides=total)],
            die_results=[[total]],
            modifier=0,
        ),
    )


def _burnable(**overrides):
    """A party whose thresholds make 10, 5 and 0 damage read as 2, 1 and 0 HP."""
    return _party(armor_max=0, major_threshold=6, severe_threshold=20, **overrides)


def test_scorched_earth_burns_whoever_fails_the_reaction_roll():
    from features.adversaries import scorched_earth

    elemental = _fire_elemental()
    fight = _fight(party=_burnable(), adversaries=[elemental])

    with _fixed_damage(10), patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=False)
    ):
        scorched_earth(elemental, fight.party[0], fight)

    assert elemental.stress_marked == 1
    hurt = [pc for pc in fight.party if pc.hp_marked]
    assert hurt and all(pc.hp_marked == 2 for pc in hurt), "10 is Major here"


def test_a_successful_reaction_roll_buys_half_rather_than_nothing():
    """The new shape: every earlier save was a clean escape."""
    from features.adversaries import scorched_earth

    elemental = _fire_elemental()
    fight = _fight(party=_burnable(), adversaries=[elemental])

    with _fixed_damage(10), patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ):
        scorched_earth(elemental, fight.party[0], fight)

    hurt = [pc for pc in fight.party if pc.hp_marked]
    assert hurt and all(pc.hp_marked == 1 for pc in hurt), "half of 10 is below Major"


def test_a_critical_reaction_roll_still_takes_nothing_at_all():
    """"Half" and "nothing" come apart here, so the critical needs its own branch."""
    from features.adversaries import scorched_earth

    elemental = _fire_elemental()
    fight = _fight(party=_burnable(), adversaries=[elemental])

    with _fixed_damage(10), patch(
        "features.adversaries.roll_duality",
        return_value=_duality(succeeds=True, critical=True),
    ):
        scorched_earth(elemental, fight.party[0], fight)

    assert not any(pc.hp_marked for pc in fight.party)


def test_an_adversary_makes_its_reaction_roll_on_a_flat_d20():
    """No traits to add, so the bare die against the Difficulty."""
    from features.adversaries import _reaction_roll

    other = _adversary("Bystander")
    fight = _fight(adversaries=[other])

    with patch("features.adversaries.roll_d20", return_value=_d20(19)) as rolled:
        roll = _reaction_roll(other, "agility", 13, fight)

    assert rolled.call_args.kwargs["modifier"] == 0
    assert roll.is_success


def test_a_pc_still_makes_theirs_on_duality_dice():
    from features.adversaries import _reaction_roll

    fight = _fight()

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ) as rolled:
        _reaction_roll(fight.party[0], "agility", 13, fight)

    assert rolled.call_args.kwargs["modifier"] == 1, "the PC's Agility"


def _wounded_bystander() -> Adversary:
    """An ally the Very Close band is certain to catch.

    Very Close reaches `n // 3` held to two, so on a small field it catches
    exactly one - and `targets_in_area` takes the **most wounded first**. Marking
    an HP is therefore how a test puts a chosen combatant inside the area without
    pinning the spread roll or building a nine-body field.
    """
    bystander = _adversary(
        "Bystander", hp_max=9, major_threshold=6, severe_threshold=20
    )
    bystander.mark_hp(1)
    return bystander


def test_scorched_earth_catches_the_elementals_own_allies():
    """"All creatures" - and they roll a d20 to save, like anybody else."""
    from features.adversaries import scorched_earth

    elemental = _fire_elemental()
    bystander = _wounded_bystander()
    fight = _fight(party=_party(size=1, armor_max=0), adversaries=[elemental, bystander])

    with _fixed_damage(10), patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=False)
    ), patch("features.adversaries.roll_d20", return_value=_d20(1, evasion=99)):
        scorched_earth(elemental, fight.party[0], fight)

    assert bystander.hp_marked > 1, "an ally that failed its save burns too"
    assert elemental.hp_marked == 0, "but the Elemental does not burn itself"


def test_an_ally_that_saves_against_scorched_earth_takes_half():
    from features.adversaries import scorched_earth

    elemental = _fire_elemental()
    bystander = _wounded_bystander()
    fight = _fight(party=_party(size=1, armor_max=0), adversaries=[elemental, bystander])

    with _fixed_damage(10), patch("features.adversaries.roll_d20", return_value=_d20(15)):
        scorched_earth(elemental, fight.party[0], fight)

    # Half of 10 is 5, below the bystander's Major of 6, so one more HP.
    assert bystander.hp_marked == 2


def test_hellfire_reaches_only_the_party():
    """"All targets", where Scorched Earth says creatures - the noun is the rule."""
    from features.adversaries import hellfire

    demon = _demon()
    bystander = _adversary("Bystander", hp_max=9, major_threshold=6, severe_threshold=20)
    fight = _fight(party=_burnable(), adversaries=[demon, bystander], fear=1)

    with _fixed_damage(10), patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=False)
    ), patch("features.adversaries.roll_d20", return_value=_d20(1, evasion=99)):
        hellfire(demon, fight.party[0], fight)

    assert bystander.hp_marked == 0
    assert any(pc.hp_marked for pc in fight.party)


def test_earth_eruption_can_knock_over_the_burrowers_allies():
    """The same word, and now a real opening for the party."""
    from features.adversaries import earth_eruption

    burrower = _adversary("Acid Burrower", features=["Earth Eruption"], hp_max=8)
    bystander = _wounded_bystander()
    fight = _fight(party=_party(size=1), adversaries=[burrower, bystander])

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=False)
    ), patch("features.adversaries.roll_d20", return_value=_d20(1, evasion=99)):
        earth_eruption(burrower, fight.party[0], fight)

    assert fight.is_vulnerable(bystander)
    assert not fight.is_vulnerable(burrower), "it does not knock itself over"


def test_an_ally_that_makes_its_save_keeps_its_feet():
    from features.adversaries import earth_eruption

    burrower = _adversary("Acid Burrower", features=["Earth Eruption"], hp_max=8)
    bystander = _wounded_bystander()
    fight = _fight(party=_party(size=1), adversaries=[burrower, bystander])

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ), patch("features.adversaries.roll_d20", return_value=_d20(20)):
        earth_eruption(burrower, fight.party[0], fight)

    assert not fight.is_vulnerable(bystander)


def test_scorched_earth_declines_without_the_stress():
    from features.adversaries import scorched_earth

    elemental = _fire_elemental(stress_max=0)
    fight = _fight(adversaries=[elemental])

    assert scorched_earth(elemental, fight.party[0], fight) is None


def test_explosion_spends_a_fear_and_sweeps_close_range():
    from features.adversaries import explosion

    elemental = _fire_elemental()
    fight = _fight(party=_party(armor_max=0), adversaries=[elemental], fear=1)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = explosion(elemental, fight.party[0], fight)

    assert fight.fear == 0
    assert result.damage_roll is not None
    assert any(pc.hp_marked for pc in fight.party)


def test_explosion_declines_without_the_fear():
    from features.adversaries import explosion

    elemental = _fire_elemental()
    fight = _fight(adversaries=[elemental], fear=0)

    assert explosion(elemental, fight.party[0], fight) is None


def test_consume_kindling_clears_hp_first():
    from features.adversaries import consume_kindling

    elemental = _fire_elemental()
    elemental.mark_hp(2)
    elemental.mark_stress(1)
    fight = _fight(adversaries=[elemental])

    consume_kindling(elemental, fight)

    assert elemental.hp_marked == 1
    assert elemental.stress_marked == 1, "Stress waits until the HP track is clean"


def test_consume_kindling_falls_through_to_stress():
    from features.adversaries import consume_kindling

    elemental = _fire_elemental()
    elemental.mark_stress(2)
    fight = _fight(adversaries=[elemental])

    consume_kindling(elemental, fight)

    assert elemental.stress_marked == 1


def test_consume_kindling_spends_nothing_on_an_unhurt_elemental():
    """A use is never wasted, so an untouched Elemental banks all three."""
    from features.adversaries import CONSUME_KINDLING_USES, consume_kindling

    elemental = _fire_elemental()
    fight = _fight(adversaries=[elemental])

    for _ in range(CONSUME_KINDLING_USES + 2):
        consume_kindling(elemental, fight)

    elemental.mark_hp(1)
    consume_kindling(elemental, fight)

    assert elemental.hp_marked == 0, "the uses were still there when it was hurt"


def test_consume_kindling_runs_out_after_three():
    from features.adversaries import CONSUME_KINDLING_USES, consume_kindling

    elemental = _fire_elemental()
    elemental.mark_hp(5)
    fight = _fight(adversaries=[elemental])

    for _ in range(CONSUME_KINDLING_USES + 3):
        consume_kindling(elemental, fight)

    assert elemental.hp_marked == 5 - CONSUME_KINDLING_USES


# --- Batch 5: the Minor Demon -------------------------------------------------


def _demon(**overrides) -> Adversary:
    """The printed Minor Demon: 8 HP, 4 Stress, 1d8+6 claws at Melee."""
    defaults = dict(
        features=["Relentless (2)", "All Must Fall", "Hellfire", "Reaper", "Momentum"],
        hp_max=8,
        stress_max=4,
        difficulty=14,
        major_threshold=8,
        severe_threshold=15,
        attack_modifier=3,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=6,
    )
    defaults.update(overrides)
    return _adversary("Minor Demon", **defaults)


def _in_range():
    """Pin the Close band so the PC is beside the Demon."""
    return patch("features.adversaries.random.random", lambda: 0.0)


def _out_of_range():
    return patch("features.adversaries.random.random", lambda: 0.99)


def _failed_with_fear() -> DualityRollResult:
    """All Must Fall's exact trigger, which `_duality` can't build.

    That helper rolls Hope 5 against Fear 4, so its failures are failures *with
    Hope* - and this feature fires on neither a success nor a failure with Hope.
    """
    return DualityRollResult(
        hope_die_result=2,
        fear_die_result=6,
        modifier=0,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=100,
    )


def test_the_trigger_helper_really_is_a_failure_with_fear():
    """Guards the three cases below, which all pass vacuously if this is wrong."""
    roll = _failed_with_fear()

    assert not roll.is_success
    assert roll.outcome is DualityOutcome.FEAR


def test_all_must_fall_costs_a_hope_on_a_failure_with_fear():
    from features.adversaries import all_must_fall

    demon = _demon()
    fight = _fight(adversaries=[demon])
    roller = fight.party[0]
    roller.gain_hope(3)

    with _in_range():
        all_must_fall(demon, roller, _failed_with_fear(), fight)

    assert roller.hope_marked == 2


def test_all_must_fall_leaves_a_successful_roll_alone():
    from features.adversaries import all_must_fall

    demon = _demon()
    fight = _fight(adversaries=[demon])
    roller = fight.party[0]
    roller.gain_hope(3)

    with _in_range():
        all_must_fall(demon, roller, _duality(succeeds=True), fight)

    assert roller.hope_marked == 3


def test_all_must_fall_does_not_reach_a_pc_out_of_range():
    from features.adversaries import all_must_fall

    demon = _demon()
    fight = _fight(adversaries=[demon])
    roller = fight.party[0]
    roller.gain_hope(3)

    with _out_of_range():
        all_must_fall(demon, roller, _failed_with_fear(), fight)

    assert roller.hope_marked == 3


def test_all_must_fall_takes_nothing_from_a_pc_with_no_hope():
    from features.adversaries import all_must_fall

    demon = _demon()
    fight = _fight(adversaries=[demon])
    roller = fight.party[0]

    with _in_range():
        all_must_fall(demon, roller, _failed_with_fear(), fight)

    assert roller.hope_marked == 0


def test_hellfire_spends_a_fear_and_reaches_the_whole_field():
    from features.adversaries import hellfire

    demon = _demon()
    fight = _fight(party=_burnable(), adversaries=[demon], fear=1)

    with _fixed_damage(10), patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=False)
    ):
        hellfire(demon, fight.party[0], fight)

    assert fight.fear == 0
    # Far reaches everyone or all but one, and every one of them failed.
    assert sum(1 for pc in fight.party if pc.hp_marked) >= len(fight.party) - 1


def test_reaper_adds_the_demons_own_marked_hp():
    from features.adversaries import reaper

    demon = _demon()
    demon.mark_hp(5)
    fight = _fight(adversaries=[demon])

    assert reaper(demon, fight.party[0], fight) == 5
    assert demon.stress_marked == 1


def test_reaper_keeps_its_stress_while_the_demon_is_unhurt():
    """The ruled general qualifier: a Reaction buying nothing is not taken."""
    from features.adversaries import reaper

    demon = _demon()
    fight = _fight(adversaries=[demon])

    assert reaper(demon, fight.party[0], fight) == 0
    assert demon.stress_marked == 0


def test_reaper_declines_when_the_stress_is_gone():
    from features.adversaries import reaper

    demon = _demon(stress_max=0)
    demon.mark_hp(5)
    fight = _fight(adversaries=[demon])

    assert reaper(demon, fight.party[0], fight) == 0


# --- Batch 5: the Minor Treant ------------------------------------------------


def test_the_minor_treant_needed_no_new_code():
    """Both features were written generically in batch 2, like the Lackey's."""
    assert assess("adversary:Minion (5)").status is Status.MODELLED
    assert assess("adversary:Group Attack").status is Status.MODELLED


def test_the_treants_minion_number_is_read_off_its_own_stat_block():
    treant = _adversary("Minor Treant", features=["Minion (5)", "Group Attack"])

    assert feature_parameter(treant, "adversary:Minion") == "5"


# --- Batch 5: the Oozes -------------------------------------------------------


def _green_ooze(**overrides) -> Adversary:
    """The printed Green Ooze: 5 HP, 2 Stress, 1d6+1 at Melee, Difficulty 8."""
    defaults = dict(
        features=["Slow", "Acidic Form", "Envelop", "Split (Tiny Green Ooze)"],
        hp_max=5,
        stress_max=2,
        difficulty=8,
        major_threshold=5,
        severe_threshold=10,
        attack_modifier=1,
        damage_dice=[DiceGroup(count=1, sides=6)],
        damage_modifier=1,
        damage_type="magic",
    )
    defaults.update(overrides)
    return _adversary("Green Ooze", **defaults)


def test_slow_spends_the_first_spotlight_and_acts_on_the_second():
    from content.registry import skips_spotlight

    ooze = _green_ooze()
    fight = _fight(adversaries=[ooze])

    assert skips_spotlight(ooze, fight) is True, "the first spotlight is always lost"
    assert skips_spotlight(ooze, fight) is False
    assert skips_spotlight(ooze, fight) is True, "and it alternates from there"


def test_a_slow_adversary_takes_no_action_on_the_spotlight_it_loses():
    """Through the loop, since the whole point is that the activation is spent."""
    from combat.policy import take_adversary_turn

    ooze = _green_ooze()
    fight = _fight(party=_party(armor_max=0), adversaries=[ooze])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        assert take_adversary_turn(ooze, fight) is None
        assert not any(pc.hp_marked for pc in fight.party)

        assert take_adversary_turn(ooze, fight) is not None


def test_an_adversary_without_slow_acts_every_time():
    from content.registry import skips_spotlight

    fight = _fight()

    assert skips_spotlight(_adversary(), fight) is False


def test_acidic_form_burns_an_armor_slot():
    from features.adversaries import acidic_form

    ooze = _green_ooze()
    fight = _fight(party=_party(armor_max=2), adversaries=[ooze])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = ooze.attack(target, fight=fight)
    marked_by_the_hit = target.armor_marked

    acidic_form(ooze, target, result, fight)

    assert target.armor_marked == marked_by_the_hit + 1


def test_acidic_form_costs_an_hp_when_there_is_no_armor_left():
    from features.adversaries import acidic_form

    ooze = _green_ooze()
    fight = _fight(party=_party(armor_max=0), adversaries=[ooze])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = ooze.attack(target, fight=fight)
    before = target.hp_marked

    acidic_form(ooze, target, result, fight)

    assert target.hp_marked == before + 1


def test_acidic_form_does_nothing_on_a_miss():
    from features.adversaries import acidic_form

    ooze = _green_ooze()
    fight = _fight(party=_party(armor_max=2), adversaries=[ooze])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(1)):
        result = ooze.attack(target, fight=fight)

    acidic_form(ooze, target, result, fight)

    assert target.armor_marked == 0


def test_envelop_costs_two_stress_and_then_one_per_action_roll():
    from features.adversaries import ENVELOP_STRESS, ENVELOPED, envelop

    ooze = _green_ooze()
    fight = _fight(party=_party(armor_max=0), adversaries=[ooze])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        envelop(ooze, target, fight)

    assert target.stress_marked == ENVELOP_STRESS
    assert fight.has_condition(target, ENVELOPED)

    fight.apply_condition_effects(target, BEFORE_AN_ACTION_ROLL)
    assert target.stress_marked == ENVELOP_STRESS + 1


def test_being_enveloped_costs_nothing_at_a_moment_it_does_not_name():
    from features.adversaries import ENVELOP_STRESS, envelop

    ooze = _green_ooze()
    fight = _fight(party=_party(armor_max=0), adversaries=[ooze])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        envelop(ooze, target, fight)

    fight.apply_condition_effects(target, ON_A_GM_TURN)

    assert target.stress_marked == ENVELOP_STRESS


def test_severe_damage_to_the_ooze_frees_whoever_it_swallowed():
    from features.adversaries import ENVELOPED, envelop, envelop_releases

    ooze = _green_ooze()
    fight = _fight(party=_party(armor_max=0), adversaries=[ooze])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        envelop(ooze, target, fight)

    envelop_releases(ooze, ooze.severe_threshold - 1, 1, fight)
    assert fight.has_condition(target, ENVELOPED), "a lesser hit does not free them"

    envelop_releases(ooze, ooze.severe_threshold, 3, fight)
    assert not fight.has_condition(target, ENVELOPED)


def test_envelop_deals_the_oozes_standard_damage():
    """No dice of its own, so a standard-damage swap would reach it."""
    from features.adversaries import envelop

    ooze = _green_ooze(damage_dice=[DiceGroup(count=1, sides=4)], damage_modifier=10)
    fight = _fight(party=_party(armor_max=0), adversaries=[ooze])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = envelop(ooze, fight.party[0], fight)

    assert result.damage_roll.total >= 11


def test_split_replaces_the_ooze_with_two_tiny_ones():
    from features.adversaries import SPLIT_COUNT, split

    ooze = _green_ooze()
    ooze.mark_hp(3)
    fight = _fight(adversaries=[ooze], fear=1)

    split(ooze, 4, 1, fight)

    assert fight.fear == 0
    # Identity, not equality: two spawned Tiny Green Oozes are equal dataclasses,
    # so `in` would be answering a different question from the one asked.
    assert all(a is not ooze for a in fight.adversaries), "it left the field"
    assert not ooze.is_defeated, "and it was not defeated doing so"

    tinies = [a for a in fight.living_adversaries if a.name == "Tiny Green Ooze"]
    assert len(tinies) == SPLIT_COUNT
    assert all(tiny.hp_marked == 0 and tiny.stress_marked == 0 for tiny in tinies)
    assert all(fight.granted_activations(tiny) == 1 for tiny in tinies)


def test_split_becomes_whatever_its_parameter_names():
    """One feature, two products - which is why it is parameterised at all."""
    from features.adversaries import split

    red = _adversary(
        "Red Ooze",
        features=["Creeping Fire", "Ignite", "Split (Tiny Red Ooze)"],
        hp_max=5,
        major_threshold=6,
        severe_threshold=11,
        damage_type="magic",
    )
    red.mark_hp(3)
    fight = _fight(adversaries=[red], fear=1)

    split(red, 4, 1, fight)

    assert [a.name for a in fight.living_adversaries] == ["Tiny Red Ooze"] * 2


def test_split_without_a_parameter_becomes_nothing():
    """The number - here the name - is the whole of what it turns into."""
    from features.adversaries import split

    ooze = _green_ooze(features=["Split"])
    ooze.mark_hp(3)
    fight = _fight(adversaries=[ooze], fear=1)

    split(ooze, 4, 1, fight)

    assert any(a is ooze for a in fight.adversaries)
    assert fight.fear == 1


def test_splitting_frees_whoever_the_ooze_had_swallowed():
    """Otherwise the hold could never end: its only way out is Severe damage to
    an Ooze that is no longer on the field."""
    from features.adversaries import ENVELOPED, envelop, split

    ooze = _green_ooze()
    fight = _fight(party=_party(armor_max=0), adversaries=[ooze], fear=1)
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        envelop(ooze, target, fight)
    assert fight.has_condition(target, ENVELOPED)

    ooze.mark_hp(3)
    split(ooze, 4, 1, fight)

    assert not fight.has_condition(target, ENVELOPED)


def test_killing_the_ooze_frees_whoever_it_had_swallowed():
    """The case Split's own release didn't cover, and the common one.

    Envelop's only printed way out is the Ooze taking Severe damage, but its
    thresholds are 5/10 on a 5 HP track - so two Major hits kill it and Severe
    never lands. Without a release the PC would keep marking a Stress on every
    action roll for the rest of the fight, held by something that isn't there.
    """
    from features.adversaries import ENVELOPED, envelop

    ooze = _green_ooze()
    fight = _fight(party=_party(armor_max=0), adversaries=[ooze])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        envelop(ooze, target, fight)
    assert fight.has_condition(target, ENVELOPED)

    ooze.mark_hp(3)
    assert fight.has_condition(target, ENVELOPED), "still standing, still holding"

    # A Major hit, which marks the last 2 HP. Severe is 10, so the blow that
    # kills it is nowhere near the one the page says would free the target.
    ooze.take_damage(5, fight)

    assert ooze.is_defeated
    assert not fight.has_condition(target, ENVELOPED)

    before = target.stress_marked
    fight.apply_condition_effects(target, BEFORE_AN_ACTION_ROLL)
    assert target.stress_marked == before, "and it stops costing them Stress"


def test_a_condition_with_its_own_ender_survives_its_source_dying():
    """The other half, and the reason this isn't just 'clear everything'.

    Sickening Flux makes a PC Vulnerable "until their next rest or they clear a
    HP". That names its own exit, so killing the Elemental must not cure it.
    """
    from features.adversaries import sickening_flux

    elemental = _elemental()
    fight = _fight(party=_party(armor_max=0), adversaries=[elemental])
    sickening_flux(elemental, fight.party[0], fight)

    caught = [pc for pc in fight.party if fight.has_condition(pc, VULNERABLE)][0]

    elemental.mark_hp(elemental.hp_unmarked - 1)
    elemental.take_damage(1, fight)

    assert elemental.is_defeated
    assert fight.has_condition(caught, VULNERABLE)


def test_split_holds_until_three_hp_are_marked():
    from features.adversaries import split

    ooze = _green_ooze()
    ooze.mark_hp(2)
    fight = _fight(adversaries=[ooze], fear=2)

    split(ooze, 4, 1, fight)

    assert any(a is ooze for a in fight.adversaries)
    assert fight.fear == 2


def test_split_declines_without_the_fear():
    from features.adversaries import split

    ooze = _green_ooze()
    ooze.mark_hp(3)
    fight = _fight(adversaries=[ooze], fear=0)

    split(ooze, 4, 1, fight)

    assert any(a is ooze for a in fight.adversaries)


def test_a_defeated_ooze_does_not_split():
    """A Fear must not undo a kill."""
    from features.adversaries import split

    ooze = _green_ooze()
    ooze.mark_hp(ooze.hp_max)
    fight = _fight(adversaries=[ooze], fear=2)

    split(ooze, 12, 3, fight)

    assert fight.fear == 2
    assert fight.adversaries_are_cleared


def test_a_removed_adversary_is_gone_without_being_defeated():
    """`remove` is the mirror of `summon`, and the distinction is the point."""
    ooze = _green_ooze()
    other = _adversary("Bystander")
    fight = _fight(adversaries=[ooze, other])

    fight.remove(ooze)

    assert fight.living_adversaries == [other]
    assert not ooze.is_defeated


def test_the_tiny_ooze_carries_acidic_form_from_the_same_registration():
    tiny = _adversary("Tiny Green Ooze", features=["Acidic Form"])

    assert assess(tiny.named_features[0]).status is Status.MODELLED


# --- Batch 6: the Red Oozes ---------------------------------------------------


def _red_ooze(**overrides) -> Adversary:
    """The printed Red Ooze: 5 HP, 3 Stress, 1d8+3 at Melee."""
    defaults = dict(
        features=["Creeping Fire", "Ignite", "Split (Tiny Red Ooze)"],
        hp_max=5,
        stress_max=3,
        difficulty=10,
        major_threshold=6,
        severe_threshold=11,
        attack_modifier=1,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=3,
        damage_type="magic",
    )
    defaults.update(overrides)
    return _adversary("Red Ooze", **defaults)


def test_creeping_fire_is_declared_as_having_no_combat_effect():
    assert assess("adversary:Creeping Fire").status is Status.NO_COMBAT_EFFECT
    assert assess("adversary:Creeping Fire").reason


def test_ignite_sets_the_target_alight():
    from features.adversaries import IGNITED, ignite

    ooze = _red_ooze()
    fight = _fight(party=_party(armor_max=0), adversaries=[ooze])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        ignite(ooze, target, fight)

    assert fight.has_condition(target, IGNITED)


def test_being_ignited_costs_damage_on_every_action_roll():
    """The first condition whose per-roll cost is damage rather than Stress."""
    from features.adversaries import IGNITED, ignite

    ooze = _red_ooze()
    fight = _fight(party=_party(armor_max=0), adversaries=[ooze])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        ignite(ooze, target, fight)

    before = target.hp_marked
    fight.apply_condition_effects(target, BEFORE_AN_ACTION_ROLL)

    assert target.hp_marked > before
    assert fight.has_condition(target, IGNITED), "and it keeps burning"


def test_a_successful_finesse_roll_puts_the_fire_out():
    from features.adversaries import IGNITED, ignite

    ooze = _red_ooze()
    fight = _fight(party=_party(armor_max=0), adversaries=[ooze])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        ignite(ooze, target, fight)

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=False)
    ):
        assert fight.expire_conditions(target, WHEN_THEY_ACT) == []

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ):
        assert fight.expire_conditions(target, WHEN_THEY_ACT) == [IGNITED]


def test_the_fire_outlives_the_ooze_that_lit_it():
    """Ignited carries its own ender, so it is not a hold and does not lift."""
    from features.adversaries import IGNITED, ignite

    ooze = _red_ooze()
    fight = _fight(party=_party(armor_max=0), adversaries=[ooze])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        ignite(ooze, target, fight)

    ooze.mark_hp(ooze.hp_unmarked - 1)
    ooze.take_damage(1, fight)

    assert ooze.is_defeated
    assert fight.has_condition(target, IGNITED)


def test_ignite_is_not_used_on_a_target_already_burning():
    """Rule 3: its point is the condition, and 1d8 is less than the staff."""
    from features.adversaries import ignite

    ooze = _red_ooze()
    fight = _fight(party=_party(armor_max=0), adversaries=[ooze])
    target = fight.party[0]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        ignite(ooze, target, fight)
        assert ignite(ooze, target, fight) is None


def test_burning_scorches_a_melee_attacker():
    from features.adversaries import burning

    tiny = _adversary("Tiny Red Ooze", features=["Burning"], hp_max=2, damage_type="magic")
    fight = _fight(party=_party(armor_max=2), adversaries=[tiny])
    attacker = fight.party[0]

    burning(tiny, attacker, find_weapon("Broadsword"), 7, 1, fight)

    assert attacker.hp_marked >= 1
    assert attacker.armor_marked == 0, "direct damage marks no Armor Slot"


def test_burning_does_not_reach_an_archer():
    from features.adversaries import burning

    tiny = _adversary("Tiny Red Ooze", features=["Burning"], hp_max=2, damage_type="magic")
    fight = _fight(party=_party(armor_max=0), adversaries=[tiny])
    attacker = fight.party[0]

    burning(tiny, attacker, find_weapon("Shortbow"), 7, 1, fight)

    assert attacker.hp_marked == 0


def test_burning_needs_damage_to_have_been_dealt():
    from features.adversaries import burning

    tiny = _adversary("Tiny Red Ooze", features=["Burning"], hp_max=2, damage_type="magic")
    fight = _fight(party=_party(armor_max=0), adversaries=[tiny])
    attacker = fight.party[0]

    burning(tiny, attacker, find_weapon("Broadsword"), 0, 0, fight)

    assert attacker.hp_marked == 0


# --- Batch 6: the pirates -----------------------------------------------------


def _captain(**overrides) -> Adversary:
    """The printed Pirate Captain: 7 HP, 5 Stress, a 1d12+2 cutlass."""
    defaults = dict(
        features=["Swashbuckler", "Reinforcements", "No Quarter", "Momentum"],
        hp_max=7,
        stress_max=5,
        difficulty=14,
        major_threshold=7,
        severe_threshold=14,
        attack_modifier=4,
        damage_dice=[DiceGroup(count=1, sides=12)],
        damage_modifier=2,
    )
    defaults.update(overrides)
    return _adversary("Pirate Captain", **defaults)


def _tough(**overrides) -> Adversary:
    """The printed Pirate Tough: 5 HP, 3 Stress, 2d6 fists with no flat bonus."""
    defaults = dict(
        features=["Swashbuckler", "Clear the Decks"],
        hp_max=5,
        stress_max=3,
        difficulty=13,
        major_threshold=8,
        severe_threshold=15,
        attack_modifier=1,
        damage_dice=[DiceGroup(count=2, sides=6)],
        damage_modifier=0,
    )
    defaults.update(overrides)
    return _adversary("Pirate Tough", **defaults)


def test_swashbuckler_costs_a_glancing_melee_attacker_a_stress():
    from features.adversaries import swashbuckler

    captain = _captain()
    fight = _fight(adversaries=[captain])
    attacker = fight.party[0]

    swashbuckler(captain, attacker, find_weapon("Broadsword"), 6, 2, fight)

    assert attacker.stress_marked == 1


def test_swashbuckler_says_nothing_about_a_solid_hit():
    """"2 or fewer HP" - a hit that really hurt is not what it punishes."""
    from features.adversaries import swashbuckler

    captain = _captain()
    fight = _fight(adversaries=[captain])
    attacker = fight.party[0]

    swashbuckler(captain, attacker, find_weapon("Broadsword"), 20, 3, fight)

    assert attacker.stress_marked == 0


def test_swashbuckler_does_not_reach_an_archer():
    from features.adversaries import swashbuckler

    captain = _captain()
    fight = _fight(adversaries=[captain])
    attacker = fight.party[0]

    swashbuckler(captain, attacker, find_weapon("Shortbow"), 6, 1, fight)

    assert attacker.stress_marked == 0


def test_swashbuckler_reaches_every_pirate_from_one_registration():
    from features.adversaries import swashbuckler

    for pirate in (_captain(), _tough()):
        fight = _fight(adversaries=[pirate])
        attacker = fight.party[0]

        swashbuckler(pirate, attacker, find_weapon("Broadsword"), 6, 1, fight)

        assert attacker.stress_marked == 1


def test_swashbuckler_reaches_the_captain_through_dispatch():
    """The signature change is only worth anything if the call site passes it."""
    from content.registry import apply_on_attacked

    captain = _captain()
    fight = _fight(adversaries=[captain])
    attacker = fight.party[0]

    apply_on_attacked(captain, attacker, find_weapon("Broadsword"), 6, 1, fight)

    assert attacker.stress_marked == 1


def test_reinforcements_summons_a_raiders_horde_once():
    from features.adversaries import REINFORCEMENTS_SUMMON, reinforcements

    captain = _captain()
    captain.mark_hp(3)  # inside the Stress-desperation line
    fight = _fight(adversaries=[captain])

    result = reinforcements(captain, fight.party[0], fight)

    assert result.made_an_attack is False
    assert captain.stress_marked == 1
    raiders = [a for a in fight.living_adversaries if a.name == REINFORCEMENTS_SUMMON]
    assert len(raiders) == 1

    assert reinforcements(captain, fight.party[0], fight) is None, "once per scene"
    assert captain.stress_marked == 1


def test_no_quarter_needs_a_crew_around_the_target():
    """At three pirates the Melee band reaches two, which is not enough."""
    from features.adversaries import no_quarter

    crew = [_captain(), _tough(), _tough()]
    fight = _fight(adversaries=crew, fear=2)

    with _bunched():
        assert no_quarter(crew[0], fight.party[0], fight) is None
    assert fight.fear == 2


def test_no_quarter_lands_once_the_crew_is_big_enough():
    from features.adversaries import no_quarter

    crew = [_captain()] + [_tough() for _ in range(5)]
    fight = _fight(party=_party(armor_max=0), adversaries=crew, fear=2)
    target = fight.party[0]

    with _bunched(), patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=False)
    ):
        result = no_quarter(crew[0], target, fight)

    assert fight.fear == 1
    assert result.made_an_attack is False
    assert target.stress_marked >= 2, "1d4+1 is at least 2"


def test_holding_your_nerve_against_no_quarter_costs_one_stress():
    from features.adversaries import no_quarter

    crew = [_captain()] + [_tough() for _ in range(5)]
    fight = _fight(party=_party(armor_max=0), adversaries=crew, fear=2)
    target = fight.party[0]

    with _bunched(), patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ):
        no_quarter(crew[0], target, fight)

    assert target.stress_marked == 1


def test_a_critical_shrugs_no_quarter_off_entirely():
    from features.adversaries import no_quarter

    crew = [_captain()] + [_tough() for _ in range(5)]
    fight = _fight(party=_party(armor_max=0), adversaries=crew, fear=2)
    target = fight.party[0]

    with _bunched(), patch(
        "features.adversaries.roll_duality",
        return_value=_duality(succeeds=True, critical=True),
    ):
        no_quarter(crew[0], target, fight)

    assert target.stress_marked == 0


def test_no_quarter_counts_anything_with_pirate_in_its_name():
    """"Pirates" is a kind rather than a stat block, unlike On My Signal's."""
    from features.adversaries import no_quarter

    crew = [_captain()] + [_tough() for _ in range(5)]
    landlubbers = [_adversary(f"Bandit {index}") for index in range(6)]
    fight = _fight(adversaries=[*crew, *landlubbers], fear=2)

    with _bunched(), patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ):
        assert no_quarter(crew[0], fight.party[0], fight) is not None

    # The same field with nobody piratical in it reaches nothing.
    alone = _fight(adversaries=[_captain(), *landlubbers], fear=2)
    with _bunched():
        assert no_quarter(alone.adversaries[0], alone.party[0], alone) is None


def test_no_quarter_declines_without_the_fear():
    from features.adversaries import no_quarter

    crew = [_captain()] + [_tough() for _ in range(5)]
    fight = _fight(adversaries=crew, fear=0)

    with _bunched():
        assert no_quarter(crew[0], fight.party[0], fight) is None


def test_clear_the_decks_costs_a_stress_on_a_landed_hit():
    from features.adversaries import clear_the_decks

    tough = _tough()
    fight = _fight(party=_party(armor_max=0), adversaries=[tough])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = clear_the_decks(tough, fight.party[0], fight)

    assert tough.stress_marked == 1
    # 3d4, so at least 3 and never the 2d6 the stat block prints.
    assert result.damage_roll.total >= 3


def test_clear_the_decks_keeps_its_stress_on_a_miss():
    from features.adversaries import clear_the_decks

    tough = _tough()
    fight = _fight(adversaries=[tough])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(1)):
        clear_the_decks(tough, fight.party[0], fight)

    assert tough.stress_marked == 0


def test_the_pirate_raiders_needed_no_new_code():
    """Horde (X) was generic from batch 2, and Swashbuckler is shared."""
    assert assess("adversary:Horde (1d4+1)").status is Status.MODELLED
    assert assess("adversary:Swashbuckler").status is Status.MODELLED


def test_a_mixed_threshold_reads_major_and_leaves_severe_out_of_reach():
    """The Tiny Green Ooze prints '4/None', the catalogue's first mixed pair."""
    from adversaries.registry import find_adversary

    tiny = find_adversary("Tiny Green Ooze").spawn()

    assert tiny.major_threshold == 4
    assert tiny.severe_threshold == NO_THRESHOLD
    assert tiny.take_damage(4) == 2, "Major, and that is the most anything can mark"
    assert tiny.is_defeated


# --- Batch 7: the skeletons ---------------------------------------------------
#
# Two of the five stat blocks needed no code at all, so the tests for those
# assert coverage status rather than behaviour - the same shape the Minor Treant
# and the Jagged Knife Lackey already use.
#
# Opportunist goes through the area rule, so it pins the spread roll with
# `_bunched()` above. The pinning is documentation rather than necessity here:
# Very Close is proportional (`n // 3`, capped at 2), so at the field sizes used
# below both draws give the same reach, and the same is true of Close over a
# party of four (Terrifying's band, which reaches 3 either way). That is
# deliberate - a test whose result depended on which way the band rolled would
# belong in validation/, not here.


def _skeleton_archer(**overrides) -> Adversary:
    """The printed Skeleton Archer: 3 HP, 2 Stress, a Far 1d8+1 shortbow.

    Named in full because `_archer` is already the **Archer Guard** further up
    this file, and a second definition of that name would silently replace it
    for every test in the module - which is exactly what happened when this was
    first written, and took out the On My Signal countdown tests.
    """
    defaults = dict(
        features=["Opportunist", "Deadly Shot"],
        hp_max=3,
        stress_max=2,
        difficulty=9,
        major_threshold=4,
        severe_threshold=7,
        attack_modifier=2,
        range="Far",
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=1,
    )
    defaults.update(overrides)
    return _adversary("Skeleton Archer", **defaults)


def _skeleton_knight(**overrides) -> Adversary:
    """The printed Skeleton Knight: 5 HP, 2 Stress, a 1d10+2 rusty greatsword.

    Named in full for the reason `_skeleton_archer` is - helpers here share one
    module namespace, and a bare `_knight` would collide with the first other
    knight the catalogue gains.
    """
    defaults = dict(
        features=["Terrifying", "Cut to the Bone", "Dig Two Graves"],
        hp_max=5,
        stress_max=2,
        difficulty=13,
        major_threshold=7,
        severe_threshold=13,
        attack_modifier=2,
        damage_dice=[DiceGroup(count=1, sides=10)],
        damage_modifier=2,
    )
    defaults.update(overrides)
    return _adversary("Skeleton Knight", **defaults)


def _skeleton_warrior(**overrides) -> Adversary:
    """The printed Skeleton Warrior: 3 HP, 2 Stress, a 1d6+2 sword.

    Named in full, as the other two in this batch are.
    """
    defaults = dict(
        features=["Only Bones", "Won't Stay Dead"],
        hp_max=3,
        stress_max=2,
        difficulty=10,
        major_threshold=4,
        severe_threshold=8,
        attack_modifier=0,
        damage_dice=[DiceGroup(count=1, sides=6)],
        damage_modifier=2,
    )
    defaults.update(overrides)
    return _adversary("Skeleton Warrior", **defaults)


def test_the_sellsword_and_the_dredge_needed_no_new_code():
    """Minion (X) and Group Attack were both generic from batch 2."""
    assert assess("adversary:Minion (4)").status is Status.MODELLED
    assert assess("adversary:Group Attack").status is Status.MODELLED


def test_the_sellswords_flat_damage_and_absent_thresholds_load():
    """A Minion with no dice at all, like the Giant Rat and the Minor Treant."""
    from adversaries.registry import find_adversary

    sellsword = find_adversary("Sellsword").spawn()

    assert sellsword.damage_dice == []
    assert sellsword.damage_modifier == 3
    assert sellsword.major_threshold == NO_THRESHOLD
    assert sellsword.take_damage(1) == 1 and sellsword.is_defeated


# --- Opportunist --------------------------------------------------------------


def test_opportunist_doubles_the_archers_damage_on_a_crowded_field():
    from features.adversaries import opportunist

    archer = _skeleton_archer()
    crowd = [archer] + [_adversary(f"Skeleton Dredge {n}", hp_max=1) for n in range(5)]
    fight = _fight(adversaries=crowd)

    with _bunched():
        assert opportunist(archer, fight.party[0], archer, fight) == 2


def test_opportunist_gets_nothing_from_a_small_field():
    """Very Close reaches n // 3, so two adversaries are not a crowd."""
    from features.adversaries import opportunist

    archer = _skeleton_archer()
    fight = _fight(adversaries=[archer, _adversary("Skeleton Dredge", hp_max=1)])

    with _bunched():
        assert opportunist(archer, fight.party[0], archer, fight) is None


def test_opportunist_does_not_double_what_anybody_else_deals():
    """The mirror of I've Got 'Em: this one belongs to the attacker."""
    from features.adversaries import opportunist

    archer = _skeleton_archer()
    crowd = [archer] + [_adversary(f"Skeleton Dredge {n}", hp_max=1) for n in range(5)]
    fight = _fight(adversaries=crowd)

    with _bunched():
        assert opportunist(archer, fight.party[0], crowd[1], fight) is None


def test_opportunist_reaches_the_archer_through_dispatch():
    from content.registry import incoming_damage_multiplier

    archer = _skeleton_archer()
    crowd = [archer] + [_adversary(f"Skeleton Dredge {n}", hp_max=1) for n in range(5)]
    fight = _fight(adversaries=crowd)

    with _bunched():
        assert incoming_damage_multiplier(fight.party[0], archer, fight) == 2


def test_opportunist_doubles_before_the_targets_thresholds():
    """Where the effect really lives - the same place I've Got 'Em's does.

    Flat damage and no dice, so the total is fixed and the only thing the
    assertion can be reading is the doubling.
    """
    archer = _skeleton_archer(damage_dice=[], damage_modifier=5)
    crowd = [archer] + [_adversary(f"Skeleton Dredge {n}", hp_max=1) for n in range(5)]
    # Thresholds set so 5 marks 1 HP and the doubled 10 marks 2.
    fight = _fight(
        party=_party(armor_max=0, major_threshold=6, severe_threshold=20),
        adversaries=crowd,
    )

    with _bunched(), patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        archer.attack(fight.party[0], fight=fight)

    assert fight.party[0].hp_marked == 2, "5 doubled to 10, which is Major"


def test_a_lone_archer_deals_what_it_rolled():
    archer = _skeleton_archer(damage_dice=[], damage_modifier=5)
    fight = _fight(
        party=_party(armor_max=0, major_threshold=6, severe_threshold=20),
        adversaries=[archer],
    )

    with _bunched(), patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        archer.attack(fight.party[0], fight=fight)

    assert fight.party[0].hp_marked == 1


# --- Deadly Shot --------------------------------------------------------------


def test_deadly_shot_declines_against_a_target_who_is_not_vulnerable():
    """A printed requirement rather than a policy of ours, like Coup de Grace."""
    from features.adversaries import deadly_shot

    archer = _skeleton_archer()
    fight = _fight(adversaries=[archer])

    assert deadly_shot(archer, fight.party[0], fight) is None
    assert archer.stress_marked == 0


def test_deadly_shot_lands_on_a_vulnerable_target_for_a_stress():
    from features.adversaries import deadly_shot

    archer = _skeleton_archer()
    fight = _fight(party=_party(armor_max=0), adversaries=[archer])
    target = fight.party[0]
    fight.apply_condition(target, Condition(name=VULNERABLE))

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = deadly_shot(archer, target, fight)

    assert archer.stress_marked == 1
    assert result.damage_roll.total >= 11, "3d4+8, never the 1d8+1 it prints"


def test_deadly_shot_keeps_its_stress_on_a_miss():
    from features.adversaries import deadly_shot

    archer = _skeleton_archer()
    fight = _fight(adversaries=[archer])
    target = fight.party[0]
    fight.apply_condition(target, Condition(name=VULNERABLE))

    with patch("adversaries.adversary.roll_d20", return_value=_d20(1)):
        deadly_shot(archer, target, fight)

    assert archer.stress_marked == 0


# --- Terrifying ---------------------------------------------------------------


def test_terrifying_takes_a_hope_from_the_front_line():
    from features.adversaries import terrifying

    knight = _skeleton_knight()
    party = _party()
    for pc in party:
        pc.gain_hope(2)
    fight = _fight(party=party, adversaries=[knight], fear=0)

    terrifying(knight, party[0], None, fight)

    # Close reaches 3 of 4, so one PC keeps both of theirs.
    assert sum(pc.hope_marked for pc in party) == 5


def test_terrifying_hands_the_gm_one_fear_not_one_per_pc():
    """The Patchwork Zombie Hulk has to print 'for each' to get the other reading."""
    from features.adversaries import terrifying

    knight = _skeleton_knight()
    party = _party()
    for pc in party:
        pc.gain_hope(2)
    fight = _fight(party=party, adversaries=[knight], fear=0)

    terrifying(knight, party[0], None, fight)

    assert fight.fear == 1


def test_terrifying_takes_nothing_from_a_pc_with_no_hope_banked():
    from features.adversaries import terrifying

    knight = _skeleton_knight()
    party = _party()
    fight = _fight(party=party, adversaries=[knight], fear=0)

    terrifying(knight, party[0], None, fight)

    assert all(pc.hope_marked == 0 for pc in party)
    assert fight.fear == 1, "the Fear rides on the attack, not on the Hope"


# --- Cut to the Bone ----------------------------------------------------------


def test_cut_to_the_bone_costs_a_stress_and_forces_one():
    from features.adversaries import cut_to_the_bone

    knight = _skeleton_knight()
    fight = _fight(party=_party(armor_max=0), adversaries=[knight])

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        result = cut_to_the_bone(knight, fight.party[0], fight)

    assert knight.stress_marked == 1
    assert result.damage_roll.total >= 3, "1d8+2, not the 1d10+2 it prints"
    assert sum(pc.stress_marked for pc in fight.party) >= 1


def test_cut_to_the_bone_holds_its_last_stress_until_the_knight_is_nearly_down():
    """Two Stress against 5 HP: the second slot opens at 2 unmarked HP."""
    from features.adversaries import cut_to_the_bone

    knight = _skeleton_knight(stress_marked=1)
    fight = _fight(adversaries=[knight])

    assert cut_to_the_bone(knight, fight.party[0], fight) is None

    knight.mark_hp(3)  # 2 unmarked HP, so the last slot is on the table
    with patch("adversaries.adversary.roll_d20", return_value=_d20(1)):
        assert cut_to_the_bone(knight, fight.party[0], fight) is not None


# --- Dig Two Graves -----------------------------------------------------------


def test_dig_two_graves_says_nothing_while_the_knight_stands():
    from features.adversaries import dig_two_graves

    knight = _skeleton_knight()
    fight = _fight(adversaries=[knight])
    knight.mark_hp(4)

    dig_two_graves(knight, amount=9, hp_marked=2, fight=fight)

    assert all(pc.hp_marked == 0 for pc in fight.party)


def test_dig_two_graves_swings_at_whoever_killed_the_skeleton_knight():
    """The ruling this batch: the priority is modelled, not declared a gap."""
    from features.adversaries import dig_two_graves

    knight = _skeleton_knight(features=["Dig Two Graves"])
    party = _party(armor_max=0)
    for pc in party:
        pc.gain_hope(4)
    fight = _fight(party=party, adversaries=[knight])
    knight.mark_hp(knight.hp_max)

    fight.last_attacker_of[id(knight)] = party[2]

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        dig_two_graves(knight, amount=9, hp_marked=1, fight=fight)

    assert party[2].hope_marked < 4, "1d4 Hope off the creature that killed it"
    assert party[2].hp_marked > 0
    assert all(pc.hope_marked == 4 for pc in party if pc is not party[2])


def test_dig_two_graves_takes_no_hope_on_a_miss():
    from features.adversaries import dig_two_graves

    knight = _skeleton_knight(features=["Dig Two Graves"])
    party = _party()
    for pc in party:
        pc.gain_hope(4)
    fight = _fight(party=party, adversaries=[knight])
    knight.mark_hp(knight.hp_max)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(1)):
        dig_two_graves(knight, amount=9, hp_marked=1, fight=fight)

    assert all(pc.hope_marked == 4 for pc in party)


def test_the_dying_blow_carries_the_knights_own_terrifying():
    """A Reaction's attack is outside the loop, so the riders are asked here."""
    from features.adversaries import dig_two_graves

    knight = _skeleton_knight()
    party = _party(armor_max=0)
    fight = _fight(party=party, adversaries=[knight], fear=0)
    knight.mark_hp(knight.hp_max)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        dig_two_graves(knight, amount=9, hp_marked=1, fight=fight)

    assert fight.fear == 1


def test_a_pc_who_kills_a_knight_takes_the_parting_swing():
    """End to end, and the reason the targeting memory had to move earlier."""
    from combat.policy import take_pc_turn

    knight = _skeleton_knight(features=["Dig Two Graves"])
    party = _party(armor_max=0)
    for pc in party:
        pc.gain_hope(4)
    fight = _fight(party=party, adversaries=[knight])
    knight.mark_hp(knight.hp_max - 1)

    # Somebody else hit it last time round; the memory must not still say so.
    fight.last_attacker_of[id(knight)] = party[3]

    with patch(
        "items.weapons.roll_duality", return_value=_duality(succeeds=True)
    ), patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        take_pc_turn(party[0], fight)

    assert knight.is_defeated
    assert party[0].hope_marked < 4, "the killer, not whoever swung last time"
    assert party[3].hope_marked == 4


# --- Only Bones ---------------------------------------------------------------


def test_only_bones_halves_physical_damage():
    from features.adversaries import only_bones

    assert only_bones(_skeleton_warrior(), DamageType.PHYSICAL) == 0.5


def test_only_bones_leaves_magic_alone():
    from features.adversaries import only_bones

    assert only_bones(_skeleton_warrior(), DamageType.MAGIC) is None


def test_only_bones_leaves_untyped_damage_alone():
    """A resistance applies to a type that was stated."""
    from features.adversaries import only_bones

    assert only_bones(_skeleton_warrior(), None) is None


def test_only_bones_reaches_the_warrior_through_dispatch():
    from content.registry import resistance_to

    assert resistance_to(_skeleton_warrior(), DamageType.PHYSICAL) == 0.5
    assert resistance_to(_skeleton_warrior(), DamageType.MAGIC) == 1.0


def test_only_bones_halves_before_the_warriors_thresholds():
    """Where the whole effect lives: 9 physical marks 1 HP fewer than 9 magic."""
    from adversaries.registry import find_adversary

    physical = find_adversary("Skeleton Warrior").spawn()
    magical = find_adversary("Skeleton Warrior").spawn()

    assert physical.take_damage(9, damage_type=DamageType.PHYSICAL) == 2
    assert magical.take_damage(9, damage_type=DamageType.MAGIC) == 3


# --- Won't Stay Dead ----------------------------------------------------------


def test_a_defeated_warrior_with_company_is_still_a_spotlight_candidate():
    from content.registry import spotlights_while_defeated

    warrior = _skeleton_warrior()
    fight = _fight(adversaries=[warrior, _adversary("Skeleton Dredge", hp_max=1)])
    warrior.mark_hp(warrior.hp_max)

    assert spotlights_while_defeated(warrior, fight) is True


def test_a_defeated_warrior_standing_alone_asks_for_nothing():
    """"If there are other adversaries on the battlefield" - there are none."""
    from content.registry import spotlights_while_defeated

    warrior = _skeleton_warrior()
    fight = _fight(adversaries=[warrior])
    warrior.mark_hp(warrior.hp_max)

    assert spotlights_while_defeated(warrior, fight) is False


def test_an_ordinary_adversary_stays_off_the_list_once_it_is_down():
    from content.registry import spotlights_while_defeated

    thing = _adversary()
    fight = _fight(adversaries=[thing, _adversary("Other")])
    thing.mark_hp(thing.hp_max)

    assert spotlights_while_defeated(thing, fight) is False


def test_the_gm_turn_offers_a_defeated_warrior_a_spotlight():
    """The one new call site, in `_next_adversary`."""
    from combat.fight import _next_adversary

    warrior = _skeleton_warrior()
    fight = _fight(adversaries=[warrior, _adversary("Skeleton Dredge", hp_max=1)])
    warrior.mark_hp(warrior.hp_max)

    # Everything else has already gone, so the Warrior is the only candidate.
    picked = _next_adversary(fight, {id(fight.adversaries[1]): 1})

    assert picked is warrior


def test_a_six_re_forms_the_warrior_with_no_marked_hp():
    from features.adversaries import wont_stay_dead

    warrior = _skeleton_warrior()
    fight = _fight(adversaries=[warrior, _adversary("Skeleton Dredge", hp_max=1)])
    warrior.mark_hp(warrior.hp_max)
    warrior.mark_stress(2)

    with patch("features.adversaries.random.randint", return_value=6):
        wont_stay_dead(warrior, fight)

    assert warrior.hp_marked == 0
    assert warrior.is_defeated is False
    assert warrior.stress_marked == 2, "the page clears HP and only HP"


def test_anything_below_a_six_leaves_the_warrior_down():
    from features.adversaries import wont_stay_dead

    warrior = _skeleton_warrior()
    fight = _fight(adversaries=[warrior, _adversary("Skeleton Dredge", hp_max=1)])
    warrior.mark_hp(warrior.hp_max)

    with patch("features.adversaries.random.randint", return_value=5):
        wont_stay_dead(warrior, fight)

    assert warrior.is_defeated


def test_a_warrior_alone_does_not_re_form_however_the_die_falls():
    from features.adversaries import wont_stay_dead

    warrior = _skeleton_warrior()
    fight = _fight(adversaries=[warrior])
    warrior.mark_hp(warrior.hp_max)

    with patch("features.adversaries.random.randint", return_value=6):
        wont_stay_dead(warrior, fight)

    assert warrior.is_defeated


def test_a_warrior_that_failed_to_re_form_spends_the_spotlight_on_nothing():
    from features.adversaries import wont_stay_dead_skips

    warrior = _skeleton_warrior()
    warrior.mark_hp(warrior.hp_max)

    assert wont_stay_dead_skips(warrior, _fight(adversaries=[warrior])) is True


def test_a_warrior_that_came_back_acts_on_the_same_activation():
    """The stricter reading - that re-forming spends the spotlight - was declined."""
    from features.adversaries import wont_stay_dead_skips

    warrior = _skeleton_warrior()

    assert wont_stay_dead_skips(warrior, _fight(adversaries=[warrior])) is False


def test_a_living_warrior_is_never_skipped():
    from content.registry import skips_spotlight

    warrior = _skeleton_warrior()

    assert skips_spotlight(warrior, _fight(adversaries=[warrior])) is False


# --- Batch 8: the Spellblade, the swarms and the brambles ---------------------
#
# Helpers are named in full, per the batch 7 lesson: one module namespace holds
# every helper in this file, and `_swarm` would be ambiguous between two of the
# three stat blocks in this batch alone.


def _spellblade(**overrides) -> Adversary:
    """The printed Spellblade: 6 HP, 3 Stress, a 1d8+4 longsword that is both types."""
    defaults = dict(
        features=["Arcane Steel", "Suppressing Blast", "Move as a Unit", "Momentum"],
        hp_max=6,
        stress_max=3,
        difficulty=14,
        major_threshold=8,
        severe_threshold=14,
        attack_modifier=3,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=4,
        damage_type="magic/physical",
    )
    defaults.update(overrides)
    return _adversary("Spellblade", **defaults)


def _rat_swarm(**overrides) -> Adversary:
    """The printed Swarm of Rats: 6 HP, 2 Stress, ATK -3."""
    defaults = dict(
        features=["Horde (1d4+1)", "In Your Face"],
        hp_max=6,
        stress_max=2,
        difficulty=10,
        major_threshold=6,
        severe_threshold=10,
        attack_modifier=-3,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=2,
    )
    defaults.update(overrides)
    return _adversary("Swarm of Rats", **defaults)


def _sylvan_soldier(**overrides) -> Adversary:
    """The printed Sylvan Soldier: 4 HP, 2 Stress, a 1d8+1 scythe."""
    defaults = dict(
        features=["Pack Tactics (1d8+5)", "Forest Control", "Blend In"],
        hp_max=4,
        stress_max=2,
        difficulty=11,
        major_threshold=6,
        severe_threshold=11,
        attack_modifier=0,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=1,
    )
    defaults.update(overrides)
    return _adversary("Sylvan Soldier", **defaults)


def _bramble_swarm(**overrides) -> Adversary:
    """The printed Tangle Bramble Swarm: 6 HP, 3 Stress, 1d6+3 thorns."""
    defaults = dict(
        features=["Horde (1d4+2)", "Crush", "Encumber"],
        hp_max=6,
        stress_max=3,
        difficulty=12,
        major_threshold=6,
        severe_threshold=11,
        attack_modifier=0,
        damage_dice=[DiceGroup(count=1, sides=6)],
        damage_modifier=3,
    )
    defaults.update(overrides)
    return _adversary("Tangle Bramble Swarm", **defaults)


def _tangle_bramble(**overrides) -> Adversary:
    """The printed Tangle Bramble: a 1 HP Minion dealing a flat 2."""
    defaults = dict(
        features=["Minion (4)", "Group Attack", "Drain and Multiply"],
        hp_max=1,
        stress_max=1,
        difficulty=11,
        major_threshold=NO_THRESHOLD,
        severe_threshold=NO_THRESHOLD,
        attack_modifier=-1,
        damage_dice=[],
        damage_modifier=2,
    )
    defaults.update(overrides)
    return _adversary("Tangle Bramble", **defaults)


# --- Damage that is both types, and Arcane Steel ------------------------------


def test_a_page_printing_both_types_reads_as_the_pair():
    from content.damage_types import BOTH, damage_type_named

    assert damage_type_named("phy/mag") is BOTH
    assert damage_type_named("magic/physical") is BOTH


def test_a_hit_that_is_both_counts_as_each_of_them():
    from content.damage_types import BOTH, includes

    assert includes(BOTH, DamageType.PHYSICAL) is True
    assert includes(BOTH, DamageType.MAGIC) is True


def test_a_single_type_still_counts_as_only_itself():
    from content.damage_types import includes

    assert includes(DamageType.PHYSICAL, DamageType.PHYSICAL) is True
    assert includes(DamageType.PHYSICAL, DamageType.MAGIC) is False


def test_untyped_damage_counts_as_nothing():
    from content.damage_types import includes

    assert includes(None, DamageType.PHYSICAL) is False
    assert includes(None, DamageType.MAGIC) is False


def test_arcane_steel_makes_the_standard_attack_both_types():
    from content.damage_types import BOTH
    from features.adversaries import arcane_steel

    assert arcane_steel(_spellblade()) is BOTH


def test_arcane_steel_reaches_the_standard_attack_but_not_a_feature_that_types_itself():
    from content.damage_types import BOTH

    spellblade = _spellblade()

    assert spellblade.type_of_damage() is BOTH
    assert spellblade.type_of_damage(DamageType.MAGIC) is DamageType.MAGIC


def test_either_resistance_halves_a_hit_that_is_both():
    """The ruling: resisted if either is, not only if both are."""
    from content.damage_types import BOTH
    from content.registry import resistance_to

    physical = _skeleton_warrior()  # Only Bones - resistant to physical
    magical = _adversary("Minor Chaos Elemental", features=["Arcane Form"])

    assert resistance_to(physical, BOTH) == 0.5
    assert resistance_to(magical, BOTH) == 0.5


def test_a_physical_only_restriction_fires_on_a_hit_that_is_both():
    from content.damage_types import BOTH
    from features.adversaries import weak_structure

    construct = _adversary("Construct", features=["Weak Structure"])

    assert weak_structure(construct, amount=9, hp_to_mark=2, damage_type=BOTH) == 3


def test_the_spellblades_catalogue_entry_carries_the_pair():
    from adversaries.registry import find_adversary
    from content.damage_types import BOTH

    spellblade = find_adversary("Spellblade").spawn()

    assert spellblade.type_of_damage() is BOTH


# --- Suppressing Blast --------------------------------------------------------


def test_suppressing_blast_costs_a_stress_and_pays_a_fear_per_wound():
    from features.adversaries import suppressing_blast

    spellblade = _spellblade()
    fight = _fight(party=_party(armor_max=0), adversaries=[spellblade], fear=0)

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=False)
    ):
        result = suppressing_blast(spellblade, fight.party[0], fight)

    assert spellblade.stress_marked == 1
    assert result.made_an_attack is False
    # Far reaches 3 or 4 of a party of four, and 1d8+2 marks HP on every one of
    # them against a Major threshold of 6 with no armor.
    wounded = sum(1 for pc in fight.party if pc.hp_marked)
    assert wounded >= 3
    assert fight.fear == wounded


def test_a_successful_save_against_suppressing_blast_takes_nothing():
    """No "half damage" clause on this one, unlike Scorched Earth and Hellfire."""
    from features.adversaries import suppressing_blast

    spellblade = _spellblade()
    fight = _fight(party=_party(armor_max=0), adversaries=[spellblade], fear=0)

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ):
        suppressing_blast(spellblade, fight.party[0], fight)

    assert all(pc.hp_marked == 0 for pc in fight.party)
    assert fight.fear == 0, "the Fear is per target who marked HP"


def test_suppressing_blast_is_on_the_table_from_full_health():
    """Three Stress slots free open at 10 or fewer unmarked HP, and it has 6."""
    from features.adversaries import suppressing_blast

    spellblade = _spellblade()
    fight = _fight(adversaries=[spellblade])

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ):
        assert suppressing_blast(spellblade, fight.party[0], fight) is not None
    assert spellblade.stress_marked == 1


def test_suppressing_blast_stops_once_the_stress_runs_out():
    from features.adversaries import suppressing_blast

    spellblade = _spellblade(stress_marked=3)
    fight = _fight(adversaries=[spellblade])

    assert suppressing_blast(spellblade, fight.party[0], fight) is None


# --- Move as a Unit -----------------------------------------------------------


def test_move_as_a_unit_spends_two_fear_and_rallies_allies():
    from features.adversaries import move_as_a_unit

    spellblade = _spellblade()
    allies = [_adversary(f"Guard {index}") for index in range(4)]
    fight = _fight(adversaries=[spellblade, *allies], fear=3)

    result = move_as_a_unit(spellblade, fight.party[0], fight)

    assert fight.fear == 1
    assert result.made_an_attack is False
    assert sum(fight.granted_activations(ally) for ally in allies) >= 1


def test_move_as_a_unit_does_not_spotlight_the_spellblade_itself():
    """Rally Guards names the Head Guard as well; this one names allies only."""
    from features.adversaries import move_as_a_unit

    spellblade = _spellblade()
    fight = _fight(adversaries=[spellblade, _adversary("Guard")], fear=3)

    move_as_a_unit(spellblade, fight.party[0], fight)

    assert fight.granted_activations(spellblade) == 0


def test_move_as_a_unit_declines_without_the_fear():
    from features.adversaries import move_as_a_unit

    spellblade = _spellblade()
    fight = _fight(adversaries=[spellblade], fear=1)

    assert move_as_a_unit(spellblade, fight.party[0], fight) is None


# --- In Your Face -------------------------------------------------------------


def test_in_your_face_hobbles_a_melee_swing_at_anybody_else():
    from features.adversaries import in_your_face

    swarm, other = _rat_swarm(), _adversary("Bandit")
    fight = _fight(adversaries=[swarm, other])

    hobbled = in_your_face(
        swarm, fight.party[0], other, find_weapon("Broadsword"), fight
    )

    assert hobbled is True


def test_in_your_face_does_not_stop_anybody_hitting_the_swarm():
    from features.adversaries import in_your_face

    swarm = _rat_swarm()
    fight = _fight(adversaries=[swarm])

    hobbled = in_your_face(
        swarm, fight.party[0], swarm, find_weapon("Broadsword"), fight
    )

    assert hobbled is False


def test_in_your_face_leaves_an_archer_alone():
    from features.adversaries import in_your_face

    swarm, other = _rat_swarm(), _adversary("Bandit")
    fight = _fight(adversaries=[swarm, other])

    hobbled = in_your_face(swarm, fight.party[0], other, find_weapon("Shortbow"), fight)

    assert hobbled is False


def test_in_your_face_reaches_a_weapon_swing_through_dispatch():
    """The hook is only worth anything if the attack actually consults it."""
    from items.weapons import attack_with

    swarm, other = _rat_swarm(), _adversary("Bandit")
    fight = _fight(adversaries=[swarm, other])

    with patch(
        "items.weapons.roll_duality", return_value=_duality(succeeds=True)
    ) as rolled:
        attack_with(fight.party[0], find_weapon("Broadsword"), other, fight=fight)

    assert rolled.call_args.kwargs["advantage_state"] is AdvantageState.DISADVANTAGE


# --- Pack Tactics, now parameterised ------------------------------------------


def test_the_sylvan_soldiers_pack_tactics_deals_its_own_dice_and_no_fear():
    from features.adversaries import pack_tactics

    soldiers = [_sylvan_soldier(), _sylvan_soldier()]
    fight = _fight(adversaries=soldiers, fear=0)

    with _bunched():
        dice, modifier = pack_tactics(soldiers[0], fight.party[0], None, fight)

    assert dice == [DiceGroup(count=1, sides=8)]
    assert modifier == 5
    assert fight.fear == 0, "only the Dire Wolf's printed text pays a Fear"


def test_the_dire_wolfs_pack_tactics_still_pays_its_fear():
    from features.adversaries import pack_tactics

    wolves = [_wolf(), _wolf()]
    fight = _fight(adversaries=wolves, fear=0)

    with _bunched():
        dice, modifier = pack_tactics(wolves[0], fight.party[0], None, fight)

    assert dice == [DiceGroup(count=1, sides=6)]
    assert modifier == 5
    assert fight.fear == 1


def test_pack_tactics_without_a_parameter_declines_rather_than_guessing():
    from features.adversaries import pack_tactics

    pack = [_wolf(features=["Pack Tactics"]), _wolf(features=["Pack Tactics"])]
    fight = _fight(adversaries=pack)

    with _bunched():
        assert pack_tactics(pack[0], fight.party[0], None, fight) is None


def test_the_catalogues_dire_wolf_carries_both_terms():
    from adversaries.registry import find_adversary
    from content.registry import feature_parameter

    wolf = find_adversary("Dire Wolf").spawn()

    assert feature_parameter(wolf, "adversary:Pack Tactics") == "1d6+5, Fear"


# --- Forest Control -----------------------------------------------------------


def test_forest_control_drops_a_tree_on_one_creature():
    from features.adversaries import forest_control

    soldier = _sylvan_soldier()
    fight = _fight(party=_party(armor_max=0), adversaries=[soldier], fear=2)

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=False)
    ):
        result = forest_control(soldier, fight.party[0], fight)

    assert fight.fear == 1
    assert result.made_an_attack is False
    assert fight.party[0].hp_marked > 0
    assert all(pc.hp_marked == 0 for pc in fight.party[1:]), "a creature, singular"


def test_a_successful_agility_roll_dodges_the_tree():
    from features.adversaries import forest_control

    soldier = _sylvan_soldier()
    fight = _fight(party=_party(armor_max=0), adversaries=[soldier], fear=2)

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ):
        forest_control(soldier, fight.party[0], fight)

    assert fight.party[0].hp_marked == 0


def test_forest_control_declines_without_the_fear():
    from features.adversaries import forest_control

    soldier = _sylvan_soldier()
    fight = _fight(adversaries=[soldier], fear=0)

    assert forest_control(soldier, fight.party[0], fight) is None


# --- Blend In, and Hidden -----------------------------------------------------


def test_blend_in_marks_a_stress_and_hides_the_soldier():
    from content.conditions import HIDDEN
    from features.adversaries import blend_in

    soldier = _sylvan_soldier()
    fight = _fight(adversaries=[soldier])
    landed = AttackResult(
        attack_roll=_d20(19),
        damage_roll=DamageRollResult(
            dice_groups=[DiceGroup(count=1, sides=8)],
            die_results=[[4]],
            modifier=1,
        ),
    )

    blend_in(soldier, fight.party[0], landed, fight)

    assert soldier.stress_marked == 1
    assert fight.is_hidden(soldier) is True
    assert fight.condition_on(soldier, HIDDEN).found_by == ("instinct", 14)


def test_blend_in_does_nothing_on_a_miss():
    from features.adversaries import blend_in

    soldier = _sylvan_soldier()
    fight = _fight(adversaries=[soldier])
    missed = AttackResult(attack_roll=_d20(1), damage_roll=None)

    blend_in(soldier, fight.party[0], missed, fight)

    assert soldier.stress_marked == 0
    assert fight.is_hidden(soldier) is False


def test_the_soldier_breaks_cover_when_it_next_acts():
    from content.conditions import HIDDEN, Condition
    from features.adversaries import blend_in_reveals

    soldier = _sylvan_soldier()
    fight = _fight(adversaries=[soldier])
    fight.apply_condition(soldier, Condition(name=HIDDEN, source=soldier))

    blend_in_reveals(soldier, fight)

    assert fight.is_hidden(soldier) is False


def test_a_swing_at_something_hidden_is_made_at_disadvantage():
    from content.conditions import HIDDEN, Condition
    from items.weapons import attack_with

    soldier = _sylvan_soldier()
    fight = _fight(adversaries=[soldier])
    fight.apply_condition(soldier, Condition(name=HIDDEN, source=soldier))

    with patch(
        "items.weapons.roll_duality", return_value=_duality(succeeds=True)
    ) as rolled:
        attack_with(fight.party[0], find_weapon("Broadsword"), soldier, fight=fight)

    assert rolled.call_args.kwargs["advantage_state"] is AdvantageState.DISADVANTAGE


def test_cloaked_now_hides_the_shadow_for_real():
    """Batch 4 declared the Hidden itself a gap; the ruling on Hidden closed it."""
    from features.adversaries import cloaked

    shadow = _adversary("Jagged Knife Shadow", features=["Cloaked"])
    fight = _fight(adversaries=[shadow])

    cloaked(shadow, fight.party[0], fight)

    assert fight.is_hidden(shadow) is True


def test_striking_from_hiding_ends_the_cloak_and_the_hiding_together():
    from features.adversaries import cloaked, cloaked_grants_advantage

    shadow = _adversary("Jagged Knife Shadow", features=["Cloaked"])
    fight = _fight(adversaries=[shadow])
    cloaked(shadow, fight.party[0], fight)

    assert cloaked_grants_advantage(shadow, fight.party[0], fight) is (
        AdvantageState.ADVANTAGE
    )
    assert fight.is_hidden(shadow) is False


def test_a_cloaked_shadow_cannot_be_hunted():
    """The page prints no roll to find one, so the condition offers none."""
    from features.adversaries import cloaked

    shadow = _adversary("Jagged Knife Shadow", features=["Cloaked"])
    fight = _fight(adversaries=[shadow])
    cloaked(shadow, fight.party[0], fight)

    assert fight.searchable_condition(shadow) is None


# --- Spending an action roll to find something hidden -------------------------


def test_a_pc_spends_their_action_roll_looking_and_finds_the_soldier():
    from combat.policy import _search_for_hidden
    from content.conditions import HIDDEN, Condition

    soldier = _sylvan_soldier()
    fight = _fight(adversaries=[soldier])
    fight.apply_condition(
        soldier, Condition(name=HIDDEN, source=soldier, found_by=("instinct", 14))
    )

    with patch("combat.policy.roll_duality", return_value=_duality(succeeds=True)):
        result = _search_for_hidden(fight.party[0], fight)

    assert result is not None and result.made_an_attack is True
    assert result.damage_roll is None
    assert fight.is_hidden(soldier) is False


def test_a_failed_search_spends_the_one_attempt_and_leaves_them_hidden():
    from combat.policy import _search_for_hidden
    from content.conditions import HIDDEN, Condition

    soldier = _sylvan_soldier()
    fight = _fight(adversaries=[soldier])
    fight.apply_condition(
        soldier, Condition(name=HIDDEN, source=soldier, found_by=("instinct", 14))
    )

    with patch("combat.policy.roll_duality", return_value=_duality(succeeds=False)):
        assert _search_for_hidden(fight.party[0], fight) is not None
        # One attempt per hiding: nobody else gets to try.
        assert _search_for_hidden(fight.party[1], fight) is None

    assert fight.is_hidden(soldier) is True


def test_nobody_searches_when_nothing_is_hidden():
    from combat.policy import _search_for_hidden

    fight = _fight(adversaries=[_sylvan_soldier()])

    assert _search_for_hidden(fight.party[0], fight) is None


def test_hiding_again_earns_a_fresh_search():
    from combat.policy import _search_for_hidden
    from content.conditions import HIDDEN, Condition

    soldier = _sylvan_soldier()
    fight = _fight(adversaries=[soldier])
    hidden = Condition(name=HIDDEN, source=soldier, found_by=("instinct", 14))

    fight.apply_condition(soldier, hidden)
    with patch("combat.policy.roll_duality", return_value=_duality(succeeds=False)):
        _search_for_hidden(fight.party[0], fight)
        assert _search_for_hidden(fight.party[0], fight) is None

        # The Soldier strikes and vanishes again - a fresh condition, a fresh try.
        fight.apply_condition(soldier, hidden)
        assert _search_for_hidden(fight.party[0], fight) is not None


# --- Encumber, and the bramble tokens -----------------------------------------


def _landed_hit(hp_marked: int = 1) -> AttackResult:
    """A hit that definitely landed, for a rider that only reads the result."""
    return AttackResult(
        attack_roll=_d20(19),
        damage_roll=DamageRollResult(
            dice_groups=[DiceGroup(count=1, sides=6)],
            die_results=[[4]],
            modifier=3,
        ),
        hp_marked=hp_marked,
    )


def test_encumber_leaves_a_bramble_token_and_restrains():
    from content.conditions import RESTRAINED
    from features.adversaries import BRAMBLE_TOKEN, encumber

    swarm = _bramble_swarm()
    fight = _fight(adversaries=[swarm])
    target = fight.party[0]

    encumber(swarm, target, _landed_hit(), fight)

    assert fight.token_count(target, BRAMBLE_TOKEN) == 1
    assert fight.has_condition(target, RESTRAINED)
    assert fight.is_vulnerable(target) is False


def test_a_third_bramble_token_makes_the_target_vulnerable():
    from features.adversaries import BRAMBLE_TOKEN, encumber

    swarm = _bramble_swarm()
    fight = _fight(adversaries=[swarm])
    target = fight.party[0]

    for _ in range(3):
        encumber(swarm, target, _landed_hit(), fight)

    assert fight.token_count(target, BRAMBLE_TOKEN) == 3
    assert fight.is_vulnerable(target) is True


def test_tearing_free_of_the_brambles_spawns_a_minion_for_each_token():
    from features.adversaries import BRAMBLE_TOKEN, TANGLE_BRAMBLE, encumber

    swarm = _bramble_swarm()
    fight = _fight(adversaries=[swarm])
    target = fight.party[0]
    for _ in range(2):
        encumber(swarm, target, _landed_hit(), fight)

    with patch(
        "features.adversaries.roll_duality", return_value=_duality(succeeds=True)
    ):
        fight.expire_conditions(target, WHEN_THEY_ACT)

    assert fight.token_count(target, BRAMBLE_TOKEN) == 0
    spawned = [a for a in fight.living_adversaries if a.name == TANGLE_BRAMBLE]
    assert len(spawned) == 2


def test_major_damage_to_the_swarm_clears_the_brambles_without_spawning_anything():
    """The asymmetry is printed: only the Finesse Roll lets the Minions loose."""
    from features.adversaries import (
        BRAMBLE_TOKEN,
        TANGLE_BRAMBLE,
        encumber,
        encumber_releases,
    )

    swarm = _bramble_swarm()
    fight = _fight(adversaries=[swarm])
    target = fight.party[0]
    for _ in range(2):
        encumber(swarm, target, _landed_hit(), fight)

    encumber_releases(swarm, amount=swarm.major_threshold, hp_marked=2, fight=fight)

    assert fight.token_count(target, BRAMBLE_TOKEN) == 0
    assert not [a for a in fight.living_adversaries if a.name == TANGLE_BRAMBLE]


# --- Crush --------------------------------------------------------------------


def test_crush_needs_three_bramble_tokens():
    from features.adversaries import crush, encumber

    swarm = _bramble_swarm()
    fight = _fight(adversaries=[swarm])
    encumber(swarm, fight.party[0], _landed_hit(), fight)

    assert crush(swarm, fight.party[0], fight) is None
    assert swarm.stress_marked == 0


def test_crush_deals_direct_damage_to_whoever_is_most_wrapped_up():
    from features.adversaries import crush, encumber

    swarm = _bramble_swarm()
    fight = _fight(party=_party(armor_max=2), adversaries=[swarm])
    wrapped = fight.party[1]
    for _ in range(3):
        encumber(swarm, wrapped, _landed_hit(), fight)

    result = crush(swarm, fight.party[0], fight)

    assert result is not None and result.made_an_attack is False
    assert swarm.stress_marked == 1
    assert wrapped.hp_marked > 0
    assert wrapped.armor_marked == 0, "direct damage marks no Armor Slot"


# --- Drain and Multiply -------------------------------------------------------


def test_brambles_knot_into_a_horde_with_the_hp_of_however_many_merged():
    """Four on the field, and the Close band gathers three of them."""
    from features.adversaries import TANGLE_BRAMBLE_SWARM, drain_and_multiply

    brambles = [_tangle_bramble() for _ in range(4)]
    fight = _fight(adversaries=brambles)

    with _bunched():
        drain_and_multiply(brambles[0], fight.party[0], _landed_hit(), fight)

    swarms = [a for a in fight.living_adversaries if a.name == TANGLE_BRAMBLE_SWARM]
    assert len(swarms) == 1
    assert swarms[0].hp_max == 3, "the count of Minions merged, not the printed 6"
    left = [a for a in fight.living_adversaries if a.name == "Tangle Bramble"]
    assert len(left) == 1, "the one the band didn't reach is still standing"


def test_two_brambles_are_not_enough_to_merge():
    from features.adversaries import TANGLE_BRAMBLE_SWARM, drain_and_multiply

    brambles = [_tangle_bramble() for _ in range(2)]
    fight = _fight(adversaries=brambles)

    with _bunched():
        drain_and_multiply(brambles[0], fight.party[0], _landed_hit(), fight)

    assert not [a for a in fight.living_adversaries if a.name == TANGLE_BRAMBLE_SWARM]


def test_three_on_the_field_is_still_not_enough_once_the_band_has_its_say():
    """Close reaches min(n*3//4, n-1), which is 2 at three Minions - so four is
    the floor for this feature, the same shape No Quarter has at six pirates."""
    from features.adversaries import TANGLE_BRAMBLE_SWARM, drain_and_multiply

    brambles = [_tangle_bramble() for _ in range(3)]
    fight = _fight(adversaries=brambles)

    with _bunched():
        drain_and_multiply(brambles[0], fight.party[0], _landed_hit(), fight)

    assert not [a for a in fight.living_adversaries if a.name == TANGLE_BRAMBLE_SWARM]


def test_a_hit_that_marked_no_hp_multiplies_nothing():
    """"Causes a target to mark HP" - armor can swallow it whole."""
    from features.adversaries import TANGLE_BRAMBLE_SWARM, drain_and_multiply

    brambles = [_tangle_bramble() for _ in range(4)]
    fight = _fight(adversaries=brambles)

    with _bunched():
        drain_and_multiply(
            brambles[0], fight.party[0], _landed_hit(hp_marked=0), fight
        )

    assert not [a for a in fight.living_adversaries if a.name == TANGLE_BRAMBLE_SWARM]


def test_the_tangle_brambles_flat_damage_loads():
    from adversaries.registry import find_adversary

    bramble = find_adversary("Tangle Bramble").spawn()

    assert bramble.damage_dice == []
    assert bramble.damage_modifier == 2
    assert bramble.major_threshold == NO_THRESHOLD
