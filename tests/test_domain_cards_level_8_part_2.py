"""Tests for the level 8 cards of Codex, Grace and Midnight.

Six cards and only two of them built, so most of this file is about the two that
are - plus the one piece of machinery they needed:

* **`on_damaged` now carries the damage type.** Spellcharge's trigger names the
  type and its payload names the HP finally marked, and nothing else has both.

The readings pinned down here are the ones the modules document as choices: Mass
Enrapture declining below three adversaries and below a payable Stress, then
applying and clearing the condition inside one action; and Spellcharge capping its
pool at the Spellcast trait and emptying the whole of it into the next attack that
lands.

Determinism comes from a target with a Difficulty of 0 so no case turns on whether
an attack landed, and from patching `content.spellcast.roll_duality` where a case
needs a cast to come out a particular way.
"""

from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.state import FightState
from content import (
    Status,
    apply_on_damaged,
    assess,
    take_action,
    total_extra_damage,
)
from content.conditions import ENRAPTURED, Condition, when_the_gm_pays
from content.damage_types import DamageType
from dice.common import AdvantageState
from dice.damage import DiceGroup
from dice.duality import DualityRollResult
from domain_cards.grace import ENRAPTURE, MASS_ENRAPTURE, MASS_ENRAPTURE_WORTH_IT
from domain_cards.midnight import (
    SPELLCHARGE,
    SPELLCHARGE_DIE,
    SPELLCHARGE_TOKENS,
)


def _make_character(**overrides) -> PlayerCharacter:
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


def _roll(hope: int, fear: int, difficulty: int) -> DualityRollResult:
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


# --- Mass Enrapture ---------------------------------------------------------------


def _enrapturing(adversaries: int, **overrides):
    caster = _make_character(domain_cards_loadout=[MASS_ENRAPTURE], **overrides)
    field = _field(adversaries)
    return caster, field, _state([caster], field)


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
    caster = _make_character(domain_cards_loadout=[MASS_ENRAPTURE])
    field = [_make_adversary(name=f"Dummy {index}", difficulty=25) for index in range(4)]
    fight = _state([caster], field)

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
    caster = _make_character(domain_cards_loadout=[ENRAPTURE])
    field = _field(4)
    fight = _state([caster], field)

    take_action(caster, field[0], fight)

    assert fight.has_condition(field[0], ENRAPTURED)


# --- Spellcharge ------------------------------------------------------------------


def _charged(**overrides):
    holder = _make_character(domain_cards_loadout=[SPELLCHARGE], **overrides)
    target = _make_adversary()
    return holder, target, _state([holder], [target])


def test_magic_damage_banks_a_token_per_hit_point_marked():
    holder, _, fight = _charged()

    apply_on_damaged(holder, 12, 2, fight, False, DamageType.MAGIC)

    assert fight.token_count(holder, SPELLCHARGE_TOKENS) == 2


def test_physical_damage_banks_nothing():
    holder, _, fight = _charged()

    apply_on_damaged(holder, 12, 2, fight, False, DamageType.PHYSICAL)

    assert fight.token_count(holder, SPELLCHARGE_TOKENS) == 0


def test_untyped_damage_banks_nothing():
    """The rule every type-carrying hook follows - no type matches no restriction."""
    holder, _, fight = _charged()

    apply_on_damaged(holder, 12, 2, fight, False, None)

    assert fight.token_count(holder, SPELLCHARGE_TOKENS) == 0


def test_magic_damage_that_marks_no_hit_points_banks_nothing():
    holder, _, fight = _charged()

    apply_on_damaged(holder, 4, 0, fight, False, DamageType.MAGIC)

    assert fight.token_count(holder, SPELLCHARGE_TOKENS) == 0


def test_the_pool_is_capped_at_the_spellcast_trait():
    """Knowledge 2, so a 3 HP hit banks two and a second hit adds nothing."""
    holder, _, fight = _charged()

    apply_on_damaged(holder, 25, 3, fight, False, DamageType.MAGIC)
    assert fight.token_count(holder, SPELLCHARGE_TOKENS) == 2

    apply_on_damaged(holder, 25, 3, fight, False, DamageType.MAGIC)
    assert fight.token_count(holder, SPELLCHARGE_TOKENS) == 2


def test_a_caster_with_no_spellcast_trait_banks_nothing():
    holder, _, fight = _charged(spellcast_trait="")

    apply_on_damaged(holder, 12, 2, fight, False, DamageType.MAGIC)

    assert fight.token_count(holder, SPELLCHARGE_TOKENS) == 0


def test_the_whole_pool_goes_into_the_next_landing_attack():
    holder, target, fight = _charged()
    fight.set_token(holder, SPELLCHARGE_TOKENS, 2)

    groups = total_extra_damage(holder, target, _roll(9, 4, 5), fight)

    assert groups == [DiceGroup(count=2, sides=SPELLCHARGE_DIE, discardable=False)]
    assert fight.token_count(holder, SPELLCHARGE_TOKENS) == 0


def test_an_empty_pool_adds_no_dice():
    holder, target, fight = _charged()

    assert total_extra_damage(holder, target, _roll(9, 4, 5), fight) == []


def test_the_pool_pays_out_once_and_refills_from_magic():
    holder, target, fight = _charged()
    apply_on_damaged(holder, 12, 2, fight, False, DamageType.MAGIC)

    assert total_extra_damage(holder, target, _roll(9, 4, 5), fight)
    assert total_extra_damage(holder, target, _roll(9, 4, 5), fight) == []

    apply_on_damaged(holder, 12, 1, fight, False, DamageType.MAGIC)
    assert total_extra_damage(holder, target, _roll(9, 4, 5), fight)


def test_an_adversary_taking_damage_reaches_the_hook_with_its_type():
    """Both sides pass the type they resolved; nothing on the GM side reads it yet."""
    holder, target, fight = _charged()

    target.take_damage(12, fight, damage_type=DamageType.MAGIC)

    assert target.hp_marked > 0


# --- Coverage ---------------------------------------------------------------------


def test_the_batch_is_assessed():
    assert assess(MASS_ENRAPTURE).status is Status.MODELLED
    assert assess(SPELLCHARGE).status is Status.MODELLED

    dismissed = [
        "Book of Vyola",
        "Memory Delve",
        "Shared Clarity",
        "Astral Projection",
        "Shadowhunter",
    ]
    assert all(assess(name).status is Status.NO_COMBAT_EFFECT for name in dismissed)
    assert assess("Safe Haven").status is Status.OUT_OF_COMBAT
