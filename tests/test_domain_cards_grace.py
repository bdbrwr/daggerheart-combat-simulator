"""Tests for the Grace domain cards.

The one worth the most care is Enrapture, whose real effect isn't the one the
card appears to describe: it moves an adversary's attacks onto the caster. It is
checked through the targeting rule that reads it rather than by inspecting a
condition record.

Two pieces of shared machinery are what the level 7 cases are really about, and
both belong to Grace-Touched:

* **`armor_instead_of_stress`** reaches `PlayerCharacter.spend_stress` itself, so
  it changes what **every** Stress cost in the project does for one PC. The cases
  pin the scope: only where the standing last-slot rule refuses.
* **`stress_instead_of_hp`** changes which track an adversary's wound lands on,
  which means `Adversary.take_damage` has a step between the severity hooks and
  the marking. The cases check that the HP reported onward is the *reduced*
  figure, since content keyed on "marks 2 or more HP" reads it.

The reading pinned down for Mass Enrapture is the module's: it declines below
three adversaries and below a payable Stress, then applies and clears the
condition inside one action - so what runs is an area attack on Stress tracks.

Determinism comes from a target with a Difficulty of 0 so no case turns on
whether a cast landed, and from patching `content.spellcast.roll_duality` where a
case needs one to come out a particular way.
"""

from unittest.mock import patch

import pytest

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.policy import choose_adversary_target
from combat.rest import Rest
from combat.state import FightState
from content import (
    Status,
    assess,
    marked_as_stress_instead,
    marks_armor_instead_of_stress,
    take_action,
)
from content.conditions import ENRAPTURED, ON_A_GM_TURN, Condition, when_the_gm_pays
from dice.common import AdvantageState
from dice.damage import DiceGroup
from dice.duality import DualityRollResult
from domain_cards.grace import (
    ENRAPTURE,
    GRACE_TOUCHED,
    MASS_ENRAPTURE,
    MASS_ENRAPTURE_WORTH_IT,
    enrapture,
    troublemaker,
)

TROUBLEMAKER = "Troublemaker"
ENDLESS_CHARISMA = "Endless Charisma"


def _make_level_2_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Bard",
        level=2,
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 0,
            "strength": 0,
            "finesse": 1,
            "instinct": 1,
            "presence": 3,
            "knowledge": 2,
        },
        evasion=11,
        proficiency=2,
        spellcast_trait="presence",
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
            "agility": 1,
            "strength": 1,
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
    """A dummy nothing can wound, for cases that are not about where a hit lands."""
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


def _make_woundable_adversary(**overrides) -> Adversary:
    """Real thresholds and a small HP track, for the cases that measure a wound."""
    defaults = dict(
        name="Dummy",
        tier=1,
        difficulty=0,
        major_threshold=10,
        severe_threshold=20,
        hp_max=12,
        stress_max=3,
        attack_modifier=0,
        damage_dice=[DiceGroup(count=1, sides=4)],
        damage_modifier=0,
        damage_type="physical",
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


def _field(count: int) -> list[Adversary]:
    """A field of distinct adversaries - identity matters, tokens are keyed by id."""
    return [_make_adversary(name=f"Dummy {index}") for index in range(count)]


# --- Enrapture ---------------------------------------------------------------


def test_enrapture_fixes_the_adversarys_attacks_on_the_caster():
    """Checked through the targeting rule, which is the only thing that reads it."""
    caster = _make_level_2_pc(name="Bard", domain_cards_loadout=[ENRAPTURE])
    ally = _make_level_2_pc(name="Guardian", domain_cards_loadout=[])
    adversary = _make_adversary()
    state = _state([caster, ally], [adversary], rest=Rest.LONG)
    # Without the spell the adversary would swing at whoever hit it last.
    state.last_attacker_of[id(adversary)] = ally

    enrapture(caster, adversary, state)

    assert state.has_condition(adversary, ENRAPTURED) is True
    assert choose_adversary_target(adversary, state) is caster


def test_an_adversary_nobody_enraptured_is_targeted_normally():
    caster = _make_level_2_pc(name="Bard", domain_cards_loadout=[ENRAPTURE])
    ally = _make_level_2_pc(name="Guardian", domain_cards_loadout=[])
    adversary = _make_adversary()
    state = _state([caster, ally], [adversary])
    state.last_attacker_of[id(adversary)] = ally

    assert choose_adversary_target(adversary, state) is ally


def test_the_gm_pays_a_fear_to_break_the_spell():
    caster = _make_level_2_pc(domain_cards_loadout=[ENRAPTURE])
    adversary = _make_adversary()
    state = _state([caster], [adversary], fear=2, rest=Rest.LONG)

    enrapture(caster, adversary, state)
    ended = state.expire_conditions(adversary, ON_A_GM_TURN)

    assert ENRAPTURED in ended
    assert state.fear == 1


def test_enrapture_costs_a_stress_to_cost_them_one():
    caster = _make_level_2_pc(domain_cards_loadout=[ENRAPTURE])
    adversary = _make_adversary()
    state = _state([caster], [adversary], rest=Rest.LONG)

    enrapture(caster, adversary, state)

    assert caster.stress_marked == 1
    assert adversary.stress_marked == 1


def test_the_forced_stress_is_once_per_rest():
    caster = _make_level_2_pc(domain_cards_loadout=[ENRAPTURE])
    first, second = _make_adversary(name="A"), _make_adversary(name="B")
    state = _state([caster], [first, second], rest=Rest.LONG)

    enrapture(caster, first, state)
    enrapture(caster, second, state)

    assert caster.stress_marked == 1
    assert second.stress_marked == 0


def test_enrapture_declines_against_a_target_already_enraptured():
    caster = _make_level_2_pc(domain_cards_loadout=[ENRAPTURE])
    adversary = _make_adversary()
    state = _state([caster], [adversary], rest=Rest.LONG)

    enrapture(caster, adversary, state)

    assert enrapture(caster, adversary, state) is None


def test_an_unconscious_caster_compels_nobody():
    """The override only reaches a PC who can still be attacked."""
    caster = _make_level_2_pc(name="Bard", domain_cards_loadout=[ENRAPTURE])
    ally = _make_level_2_pc(name="Guardian", domain_cards_loadout=[])
    adversary = _make_adversary()
    state = _state([caster, ally], [adversary], rest=Rest.LONG)

    enrapture(caster, adversary, state)
    caster.unconscious = True

    assert choose_adversary_target(adversary, state) is ally


# --- Troublemaker ------------------------------------------------------------


def test_troublemaker_forces_stress_without_dealing_damage():
    caster = _make_level_2_pc(domain_cards_loadout=[TROUBLEMAKER])
    adversary = _make_adversary()
    state = _state([caster], [adversary], rest=Rest.LONG)

    result = troublemaker(caster, adversary, state)

    assert result.damage_roll is None
    assert result.made_an_attack is True
    assert adversary.stress_marked > 0


def test_troublemaker_is_once_per_rest():
    caster = _make_level_2_pc(domain_cards_loadout=[TROUBLEMAKER])
    adversary = _make_adversary()
    state = _state([caster], [adversary], rest=Rest.LONG)

    troublemaker(caster, adversary, state)

    assert troublemaker(caster, adversary, state) is None


def test_troublemaker_is_unavailable_without_a_rest():
    caster = _make_level_2_pc(domain_cards_loadout=[TROUBLEMAKER])
    adversary = _make_adversary()
    state = _state([caster], [adversary], rest=Rest.NONE)

    assert troublemaker(caster, adversary, state) is None


def test_troublemaker_needs_no_spellcast_trait():
    """It rolls Presence, so a PC who casts nothing can still provoke."""
    caster = _make_level_2_pc(spellcast_trait="", domain_cards_loadout=[TROUBLEMAKER])
    adversary = _make_adversary()
    state = _state([caster], [adversary], rest=Rest.LONG)

    assert troublemaker(caster, adversary, state) is not None


# --- Grace-Touched: the Armor Slot -------------------------------------------


def test_the_permission_is_registered():
    holder = _make_level_7_pc(domain_cards_loadout=[GRACE_TOUCHED])

    assert marks_armor_instead_of_stress(holder, 1) is True
    assert marks_armor_instead_of_stress(_make_level_7_pc(), 1) is False


def test_armor_is_not_touched_while_stress_is_comfortable():
    """The scope of the ruling: it unlocks a refusal, it doesn't replace Stress."""
    holder = _make_level_7_pc(domain_cards_loadout=[GRACE_TOUCHED], armor_max=3)

    assert holder.spend_stress(1) is True
    assert holder.stress_marked == 1
    assert holder.armor_marked == 0


def test_armor_pays_for_the_last_stress_slot():
    holder = _make_level_7_pc(domain_cards_loadout=[GRACE_TOUCHED], armor_max=3)
    holder.mark_stress(5)  # one slot left, and the PC is not near death

    assert holder.will_spend_stress(1) is True
    assert holder.spend_stress(1) is True
    assert holder.stress_marked == 5  # the Stress was not marked
    assert holder.armor_marked == 1


def test_armor_pays_when_the_stress_track_is_full():
    holder = _make_level_7_pc(domain_cards_loadout=[GRACE_TOUCHED], armor_max=3)
    holder.mark_stress(6)

    assert holder.spend_stress(1) is True
    assert holder.armor_marked == 1


def test_without_armor_the_standing_rule_stands():
    holder = _make_level_7_pc(domain_cards_loadout=[GRACE_TOUCHED], armor_max=0)
    holder.mark_stress(5)

    assert holder.will_spend_stress(1) is False


def test_a_pc_without_the_card_is_unchanged():
    holder = _make_level_7_pc(armor_max=3)
    holder.mark_stress(5)

    assert holder.will_spend_stress(1) is False
    assert holder.armor_marked == 0


# --- Grace-Touched: the wound taken as Stress --------------------------------


def test_a_wound_lands_on_stress_instead():
    caster = _make_level_7_pc(domain_cards_loadout=[GRACE_TOUCHED])
    target = _make_woundable_adversary()
    fight = _state([caster], [target])

    marked = target.take_damage(12, fight)  # over Major, so 2 HP

    assert marked == 0
    assert target.hp_marked == 0
    assert target.stress_marked == 2


def test_the_hp_reported_onward_is_the_reduced_figure():
    """Content keyed on "marks 2 or more HP" has to see what actually landed."""
    caster = _make_level_7_pc(domain_cards_loadout=[GRACE_TOUCHED])
    target = _make_woundable_adversary()
    fight = _state([caster], [target])

    assert target.take_damage(5, fight) == 0


def test_an_adversary_near_death_takes_the_hp():
    caster = _make_level_7_pc(domain_cards_loadout=[GRACE_TOUCHED])
    target = _make_woundable_adversary()
    target.mark_hp(10)  # 2 unmarked of 12
    fight = _state([caster], [target])

    target.take_damage(5, fight)

    assert target.hp_marked == 11
    assert target.stress_marked == 0


def test_a_full_stress_track_sends_the_wound_back_to_hp():
    caster = _make_level_7_pc(domain_cards_loadout=[GRACE_TOUCHED])
    target = _make_woundable_adversary()
    target.mark_stress(3)
    fight = _state([caster], [target])

    target.take_damage(5, fight)

    assert target.hp_marked == 1


def test_a_wound_bigger_than_the_track_is_split():
    caster = _make_level_7_pc(domain_cards_loadout=[GRACE_TOUCHED])
    target = _make_woundable_adversary(stress_max=1)
    fight = _state([caster], [target])

    marked = target.take_damage(25, fight)  # Severe, so 3 HP

    assert target.stress_marked == 1
    assert target.hp_marked == 2
    assert marked == 2


def test_nothing_converts_without_the_card():
    target = _make_woundable_adversary()
    fight = _state([_make_level_7_pc()], [target])

    assert marked_as_stress_instead(target, 2, fight) == 0


# --- Mass Enrapture ----------------------------------------------------------


def _enrapturing(adversaries: int, **overrides):
    caster = _make_level_8_pc(domain_cards_loadout=[MASS_ENRAPTURE], **overrides)
    field = _field(adversaries)
    return caster, field, _rested_state([caster], field)


def test_mass_enrapture_forces_a_stress_on_everything_it_caught():
    """How many the Far band reaches is rolled, so the floor is what is asserted."""
    caster, field, fight = _enrapturing(4)

    result = take_action(caster, field[0], fight)

    assert result is not None
    assert caster.stress_marked == 1
    caught = sum(adversary.stress_marked for adversary in field)
    assert caught >= MASS_ENRAPTURE_WORTH_IT
    assert all(adversary.stress_marked <= 1 for adversary in field)


def test_mass_enrapture_ends_its_own_condition_at_once():
    """The ruling is that the spell is cast to be ended, so nothing stays held."""
    caster, field, fight = _enrapturing(4)

    take_action(caster, field[0], fight)

    assert not any(fight.has_condition(a, ENRAPTURED) for a in field)


def test_mass_enrapture_declines_below_three_adversaries():
    caster, field, fight = _enrapturing(MASS_ENRAPTURE_WORTH_IT - 1)

    assert take_action(caster, field[0], fight) is None
    assert caster.stress_marked == 0


def test_mass_enrapture_declines_when_the_stress_cannot_be_paid():
    """The last-slot rule, checked before the roll so declining costs nothing."""
    caster, field, fight = _enrapturing(4, stress_marked=5)

    assert take_action(caster, field[0], fight) is None
    assert caster.stress_marked == 5


def test_mass_enrapture_skips_an_adversary_already_enraptured():
    """Without this, a mass cast would clear a compulsion Enrapture had bought.

    Six on the field so the sweep clears its floor even after one is removed and
    even when the Far band falls short - neither of which is under this case's
    control.
    """
    caster, field, fight = _enrapturing(6)
    fight.apply_condition(
        field[0],
        Condition(name=ENRAPTURED, end=when_the_gm_pays, source=caster),
    )

    take_action(caster, field[0], fight)

    assert fight.has_condition(field[0], ENRAPTURED)
    assert field[0].stress_marked == 0
    assert caster.stress_marked == 1


def test_mass_enrapture_declines_once_too_few_are_left_unenraptured():
    """Four on the field, two already held - the sweep is short of its floor."""
    caster, field, fight = _enrapturing(4)

    for adversary in field[:2]:
        fight.apply_condition(
            adversary,
            Condition(name=ENRAPTURED, end=when_the_gm_pays, source=caster),
        )

    assert take_action(caster, field[0], fight) is None


def test_a_cast_that_reaches_nobody_spends_no_stress():
    """The field has to be hard for a cast to genuinely catch nobody.

    An area spell is one roll re-checked against **each target's own Difficulty**,
    so the roll's own `is_success` - measured against `area_difficulty` - is not
    what decides who is caught. Against the Difficulty 0 dummies the rest of this
    file uses, every roll beats everybody however it is patched.
    """
    caster = _make_level_8_pc(domain_cards_loadout=[MASS_ENRAPTURE])
    field = [_make_adversary(name=f"Dummy {index}", difficulty=25) for index in range(4)]
    fight = _rested_state([caster], field)

    with patch(
        "content.spellcast.roll_duality",
        return_value=_roll(hope=1, fear=2, difficulty=25),
    ):
        result = take_action(caster, field[0], fight)

    assert result is not None and not result.attack_roll.is_success
    assert caster.stress_marked == 0
    assert all(adversary.stress_marked == 0 for adversary in field)


def test_enrapture_and_mass_enrapture_are_separate_cards():
    """Both register on ENRAPTURED; only the level 1 card leaves it standing."""
    caster = _make_level_8_pc(domain_cards_loadout=[ENRAPTURE])
    field = _field(4)
    fight = _rested_state([caster], field)

    take_action(caster, field[0], fight)

    assert fight.has_condition(field[0], ENRAPTURED)


# --- Assessed rather than built ----------------------------------------------


def test_inspirational_words_waits_for_sequenced_encounters():
    assert assess("Inspirational Words").status is Status.OUT_OF_COMBAT


@pytest.mark.parametrize("card", ["Deft Deceiver", "Tell No Lies"])
def test_the_two_social_cards_are_declared_rather_than_absent(card):
    assessment = assess(card)

    assert assessment.status is Status.NO_COMBAT_EFFECT
    assert assessment.reason


def test_endless_charisma_is_declared_with_a_reason():
    assert assess(ENDLESS_CHARISMA).status.value == "no combat effect"
    assert assess(ENDLESS_CHARISMA).reason


def test_the_level_eight_pair_are_assessed():
    assert assess(MASS_ENRAPTURE).status is Status.MODELLED
    assert assess("Astral Projection").status is Status.NO_COMBAT_EFFECT


@pytest.mark.parametrize("card", ["Copycat", "Master of the Craft"])
def test_the_whole_of_level_nine_is_declared_rather_than_absent(card):
    """Grace is the fourth domain with a level that reaches no fight at all.

    Both are dismissals rather than gaps, and for reasons the domain hasn't used
    before - Master of the Craft moves numbers the sheet carries resolved, and
    Copycat's printed price is a card *level* nothing in the project records.
    """
    assessment = assess(card)

    assert assessment.status is Status.NO_COMBAT_EFFECT
    assert assessment.reason
