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

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.state import FightState
from content.aoe import Range
from content.conditions import (
    ON_A_GM_TURN,
    VULNERABLE,
    WHEN_THEY_ACT,
    Condition,
    when_the_gm_pays,
    when_they_act,
)
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


def test_bite_costs_a_stress():
    bear = _adversary("Bear", features=["Bite"], stress_max=2)
    fight = _fight()

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        bite(bear, fight.party[0], fight)

    assert bear.stress_marked == 1


def test_bite_declines_when_the_bear_is_out_of_stress():
    bear = _adversary("Bear", features=["Bite"], stress_max=1)
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
    ogre = _adversary("Cave Ogre", features=["Ramp Up"])
    assert ramp_up_sweeps(ogre) is Range.VERY_CLOSE
    assert standard_attack_area(ogre, _fight()) is Range.VERY_CLOSE


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


def test_grab_and_drag_is_not_policied_into_never_firing():
    """It deals less than the standard attack, which is a fact about damage only.

    The Restrain that justifies it at a table has no representation here, and
    that is a gap of ours rather than a reason for a GM never to use it.
    """
    defender = _adversary("Deeproot Defender", features=["Grab and Drag"])
    fight = _fight(fear=1)

    with patch("adversaries.adversary.roll_d20", return_value=_d20(19)):
        assert grab_and_drag(defender, fight.party[0], fight) is not None
