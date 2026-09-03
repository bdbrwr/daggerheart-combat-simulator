"""Tests for the level 8 cards of Sage, Splendor and Valor - the batch that
closes level 8.

Six cards, all modelled, and four pieces of machinery that are most of what these
are really about:

* **`ally_roll_bonus`** and **`ally_extra_armor_slot`**, the party-wide twins of
  two hooks that had only ever been holder-scoped. Forest Sprites gives both of
  its benefits to somebody else and could not be written without them.
* **`ally_severity_response`**, the party-wide twin of `severity_response`, which
  is the only way one PC's card can move the threshold bands of another PC's hit.
  It carries `marked_armor` because Shield Aura's trigger is exactly that.
* **`PlayerCharacter.gain_trait_bonus`**, which is how Full Surge's "+2 to all of
  your character traits" reaches everything that reads a trait.

The readings pinned down here are the ones the modules document as choices:
Forest Sprites spending Hope down to a floor of 2 and burning one sprite per
benefit, Shield Aura answering only a hit that marked an Armor Slot and fading
when it takes one to nothing, Stunning Sunlight emptying the Hope pool one target
at a time, and Ground Pound declining below two.

Determinism comes from a target with a Difficulty of 0 so no case turns on
whether an attack landed, from patching `content.spellcast.roll_duality` where a
cast is made against a printed Difficulty, and from patching the module-level
`random` where a card rolls dice of its own.
"""

from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.state import FightState
from content import (
    Status,
    ally_extra_armor_slots,
    ally_soften_damage,
    assess,
    party_damage_reduction,
    take_action,
    total_ally_roll_bonus,
    use_free_abilities,
)
from content.conditions import STUNNED
from content.damage_types import DamageType
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from domain_cards.sage import (
    BARRIER_STANDING,
    FOREST_SPRITES,
    FOREST_SPRITES_ATTACK_BONUS,
    FOREST_SPRITES_HOPE_FLOOR,
    REJUVENATION_BARRIER,
    SPRITES_STANDING,
)
from domain_cards.splendor import (
    SHIELD_AURA,
    SHIELD_AURA_WORN,
    STUNNING_SUNLIGHT,
)
from domain_cards.valor import (
    FULL_SURGE,
    FULL_SURGE_BONUS,
    FULL_SURGE_STRESS,
    GROUND_POUND,
    GROUND_POUND_WORTH_IT,
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
    return [_make_adversary(name=f"Dummy {index}") for index in range(count)]


def _succeeding(difficulty: int):
    """Patch the shared cast so a printed-Difficulty spell definitely lands."""
    return patch(
        "content.spellcast.roll_duality",
        return_value=_roll(hope=12, fear=11, difficulty=difficulty),
    )


# --- Forest Sprites ---------------------------------------------------------------


def _conjuring(**overrides):
    caster = _make_character(
        name="Druid", domain_cards_loadout=[FOREST_SPRITES], **overrides
    )
    ally = _make_character(name="Ally")
    target = _make_adversary()
    return caster, ally, target, _state([caster, ally], [target])


def test_forest_sprites_spends_hope_down_to_the_floor():
    caster, _, target, fight = _conjuring()

    with _succeeding(13):
        assert take_action(caster, target, fight) is not None

    assert caster.hope_marked == FOREST_SPRITES_HOPE_FLOOR
    assert fight.token_count(caster, SPRITES_STANDING) == 6 - FOREST_SPRITES_HOPE_FLOOR


def test_forest_sprites_declines_at_the_floor():
    caster, _, target, fight = _conjuring(hope_marked=FOREST_SPRITES_HOPE_FLOOR)

    with _succeeding(13):
        assert take_action(caster, target, fight) is None


def test_forest_sprites_declines_while_sprites_still_stand():
    caster, _, target, fight = _conjuring()
    fight.set_token(caster, SPRITES_STANDING, 1)

    with _succeeding(13):
        assert take_action(caster, target, fight) is None


def test_a_failed_conjuring_spends_no_hope():
    caster, _, target, fight = _conjuring()

    with patch(
        "content.spellcast.roll_duality",
        return_value=_roll(hope=1, fear=2, difficulty=13),
    ):
        result = take_action(caster, target, fight)

    assert result is not None and not result.attack_roll.is_success
    assert caster.hope_marked == 6
    assert fight.token_count(caster, SPRITES_STANDING) == 0


def test_a_sprite_guides_an_allys_swing_and_vanishes():
    caster, ally, target, fight = _conjuring()
    fight.set_token(caster, SPRITES_STANDING, 2)

    bonus = total_ally_roll_bonus(ally, target, fight, "agility")

    assert bonus == FOREST_SPRITES_ATTACK_BONUS
    assert fight.token_count(caster, SPRITES_STANDING) == 1


def test_a_sprite_never_guides_the_druid_who_conjured_it():
    """'Your allies' - both benefits are scoped away from the caster."""
    caster, _, target, fight = _conjuring()
    fight.set_token(caster, SPRITES_STANDING, 2)

    assert total_ally_roll_bonus(caster, target, fight, "agility") == 0
    assert fight.token_count(caster, SPRITES_STANDING) == 2


def test_no_sprites_left_adds_nothing():
    caster, ally, target, fight = _conjuring()

    assert total_ally_roll_bonus(ally, target, fight, "agility") == 0


def test_a_sprite_buys_an_ally_a_second_armor_slot():
    caster, ally, _, fight = _conjuring()
    fight.set_token(caster, SPRITES_STANDING, 1)

    slots = ally_extra_armor_slots(ally, 12, 1, fight, DamageType.PHYSICAL)

    assert slots == 1
    assert fight.token_count(caster, SPRITES_STANDING) == 0


def test_a_sprite_is_not_spent_where_the_slot_would_save_nothing():
    """Brace's rule - the free slot already took the hit to nothing."""
    caster, ally, _, fight = _conjuring()
    fight.set_token(caster, SPRITES_STANDING, 1)

    assert ally_extra_armor_slots(ally, 12, 0, fight, DamageType.PHYSICAL) == 0
    assert fight.token_count(caster, SPRITES_STANDING) == 1


def test_a_sprite_does_not_shield_the_druid_who_conjured_it():
    caster, _, _, fight = _conjuring()
    fight.set_token(caster, SPRITES_STANDING, 1)

    assert ally_extra_armor_slots(caster, 12, 1, fight, DamageType.PHYSICAL) == 0


# --- Rejuvenation Barrier ---------------------------------------------------------


def _barrier(**overrides):
    caster = _make_character(
        name="Druid", domain_cards_loadout=[REJUVENATION_BARRIER], **overrides
    )
    target = _make_adversary()
    return caster, target, _state([caster], [target])


def test_the_barrier_goes_up_and_clears_hit_points():
    caster, target, fight = _barrier(hp_marked=4)

    with _succeeding(15):
        assert take_action(caster, target, fight) is not None

    assert fight.token_count(caster, BARRIER_STANDING)
    assert caster.hp_marked < 4


def test_the_barrier_is_once_per_rest_on_a_success():
    caster, target, fight = _barrier()

    with patch(
        "content.spellcast.roll_duality",
        return_value=_roll(hope=1, fear=2, difficulty=15),
    ):
        take_action(caster, target, fight)

    assert fight.can_use_once_per_rest(caster, REJUVENATION_BARRIER)
    assert fight.token_count(caster, BARRIER_STANDING) == 0


def test_the_barrier_halves_physical_damage_for_the_caster():
    caster, _, fight = _barrier()
    fight.set_token(caster, BARRIER_STANDING, 1)

    lost = party_damage_reduction(caster, 15, fight, DamageType.PHYSICAL)

    assert 15 - lost == 15 // 2


def test_the_barrier_does_nothing_against_magic():
    caster, _, fight = _barrier()
    fight.set_token(caster, BARRIER_STANDING, 1)

    assert party_damage_reduction(caster, 15, fight, DamageType.MAGIC) == 0


def test_no_barrier_reduces_nothing():
    caster, _, fight = _barrier()

    assert party_damage_reduction(caster, 15, fight, DamageType.PHYSICAL) == 0


# --- Shield Aura ------------------------------------------------------------------


def _auraed(**overrides):
    caster = _make_character(name="Seraph", domain_cards_loadout=[SHIELD_AURA])
    frail = _make_character(name="Frail", hp_marked=5, **overrides)
    sturdy = _make_character(name="Sturdy")
    return caster, frail, sturdy, _state([caster, frail, sturdy], [_make_adversary()])


def test_shield_aura_goes_on_the_frailest_ally():
    caster, frail, sturdy, fight = _auraed()

    assert use_free_abilities(caster, fight, 1) == [SHIELD_AURA]
    assert fight.token_count(frail, SHIELD_AURA_WORN) == 1
    assert fight.token_count(sturdy, SHIELD_AURA_WORN) == 0
    assert fight.token_count(caster, SHIELD_AURA_WORN) == 0
    assert caster.stress_marked == 1


def test_shield_aura_holds_on_one_creature_at_a_time():
    caster, _, _, fight = _auraed()

    assert use_free_abilities(caster, fight, 1) == [SHIELD_AURA]
    assert use_free_abilities(caster, fight, 1) == []


def test_the_aura_drops_a_hit_a_further_threshold():
    caster, frail, _, fight = _auraed()
    use_free_abilities(caster, fight, 1)

    marked = ally_soften_damage(frail, 25, 2, fight, DamageType.PHYSICAL, True)

    assert marked == 1
    assert fight.token_count(frail, SHIELD_AURA_WORN) == 1


def test_the_aura_answers_nothing_where_no_armor_slot_was_marked():
    """Direct damage, or a PC with no slots free - the card's trigger, literally."""
    caster, frail, _, fight = _auraed()
    use_free_abilities(caster, fight, 1)

    assert ally_soften_damage(frail, 25, 2, fight, DamageType.PHYSICAL, False) == 2


def test_the_aura_fades_when_it_takes_a_hit_to_nothing():
    caster, frail, _, fight = _auraed()
    use_free_abilities(caster, fight, 1)

    assert ally_soften_damage(frail, 12, 1, fight, DamageType.PHYSICAL, True) == 0
    assert fight.token_count(frail, SHIELD_AURA_WORN) == 0


def test_a_hit_already_marking_nothing_neither_ends_nor_charges_the_aura():
    caster, frail, _, fight = _auraed()
    use_free_abilities(caster, fight, 1)

    assert ally_soften_damage(frail, 12, 0, fight, DamageType.PHYSICAL, True) == 0
    assert fight.token_count(frail, SHIELD_AURA_WORN) == 1


def test_the_aura_answers_only_for_whoever_wears_it():
    caster, _, sturdy, fight = _auraed()
    use_free_abilities(caster, fight, 1)

    assert ally_soften_damage(sturdy, 25, 2, fight, DamageType.PHYSICAL, True) == 2


# --- Stunning Sunlight ------------------------------------------------------------


def _sunlit(adversaries: int, **overrides):
    caster = _make_character(domain_cards_loadout=[STUNNING_SUNLIGHT], **overrides)
    field = _field(adversaries)
    return caster, field, _state([caster], field)


def test_stunning_sunlight_burns_one_target_per_hope():
    caster, field, fight = _sunlit(6, hope_marked=2)

    assert take_action(caster, field[0], fight) is not None

    assert caster.hope_marked == 0
    assert sum(1 for a in field if a.hp_marked > 0) == 2


def test_stunning_sunlight_is_capped_by_the_targets_it_beat():
    """Hope is never spent on a target the roll never reached."""
    caster, field, fight = _sunlit(1)

    take_action(caster, field[0], fight)

    assert caster.hope_marked == 5


def test_stunning_sunlight_declines_with_no_hope():
    caster, field, fight = _sunlit(4, hope_marked=0)

    assert take_action(caster, field[0], fight) is None


def test_a_target_that_fails_its_reaction_roll_is_stunned():
    caster, field, fight = _sunlit(6, hope_marked=2)

    with patch("domain_cards.splendor.roll_d20") as rolled:
        rolled.return_value.is_success = False
        take_action(caster, field[0], fight)

    assert sum(1 for a in field if fight.has_condition(a, STUNNED)) == 2


def test_a_target_that_saves_takes_damage_and_is_not_stunned():
    caster, field, fight = _sunlit(6, hope_marked=2)

    with patch("domain_cards.splendor.roll_d20") as rolled:
        rolled.return_value.is_success = True
        take_action(caster, field[0], fight)

    assert not any(fight.has_condition(a, STUNNED) for a in field)
    assert sum(1 for a in field if a.hp_marked > 0) == 2


# --- Full Surge -------------------------------------------------------------------


def test_full_surge_raises_every_trait():
    pc = _make_character(domain_cards_loadout=[FULL_SURGE])
    fight = _state([pc], [_make_adversary()])
    before = dict(pc.traits)

    assert use_free_abilities(pc, fight, 1) == [FULL_SURGE]

    assert all(pc.traits[t] == before[t] + FULL_SURGE_BONUS for t in before)
    assert pc.stress_marked == FULL_SURGE_STRESS


def test_full_surge_records_what_it_granted():
    """The record is what keeps the sheet's authored numbers recoverable."""
    pc = _make_character(domain_cards_loadout=[FULL_SURGE])
    fight = _state([pc], [_make_adversary()])

    use_free_abilities(pc, fight, 1)

    assert set(pc.trait_bonuses) == set(pc.traits)
    assert all(bonus == FULL_SURGE_BONUS for bonus in pc.trait_bonuses.values())


def test_full_surge_declines_when_the_three_stress_cannot_be_paid():
    pc = _make_character(domain_cards_loadout=[FULL_SURGE], stress_marked=4)
    fight = _state([pc], [_make_adversary()])

    assert use_free_abilities(pc, fight, 1) == []
    assert pc.trait_bonuses == {}


def test_full_surge_is_once_per_long_rest():
    pc = _make_character(domain_cards_loadout=[FULL_SURGE])
    fight = _state([pc], [_make_adversary()])

    assert use_free_abilities(pc, fight, 1) == [FULL_SURGE]
    assert use_free_abilities(pc, fight, 1) == []


def test_a_surged_trait_reaches_a_roll():
    """`traits` is the effective mapping, so every reader picks the bonus up."""
    pc = _make_character(domain_cards_loadout=[FULL_SURGE])
    fight = _state([pc], [_make_adversary()])

    use_free_abilities(pc, fight, 1)

    assert pc.traits["strength"] == 2 + FULL_SURGE_BONUS


# --- Ground Pound -----------------------------------------------------------------


def _pounding(adversaries: int, thresholds: int = 100, **overrides):
    """A field of `adversaries`. **Six or more** for the band to reach two.

    Very Close reaches a third of the field held to a cap of two, so a field of
    four reaches exactly one and every cast would decline for the wrong reason.
    """
    pc = _make_character(domain_cards_loadout=[GROUND_POUND], **overrides)
    field = [
        _make_adversary(
            name=f"Dummy {index}",
            major_threshold=thresholds,
            severe_threshold=thresholds * 10,
        )
        for index in range(adversaries)
    ]
    return pc, field, _state([pc], field)


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


# --- Coverage ---------------------------------------------------------------------


def test_the_batch_is_assessed():
    modelled = [
        FOREST_SPRITES,
        REJUVENATION_BARRIER,
        SHIELD_AURA,
        STUNNING_SUNLIGHT,
        FULL_SURGE,
        GROUND_POUND,
    ]
    assert all(assess(name).status is Status.MODELLED for name in modelled)
