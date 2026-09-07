"""Tests for the Midnight domain cards.

The one worth the most care is Shadowbind, whose whole value is the Fear the GM
has to spend undoing it - Restrained does nothing by itself here, so the Fear
count is what the cases assert on.

Two pieces of shared machinery are what several of these are really about:

* **`fear_conversion`**, Midnight-Touched's, is the first thing that stops the GM
  gaining a Fear.
* **`on_damaged` carries the damage type.** Spellcharge's trigger names the type
  and its payload names the HP finally marked, and nothing else has both.

The readings pinned down here are the ones the module documents as choices:
Vanishing Dodge reading the *printed* damage type off the attacking stat block,
and Spellcharge capping its pool at the Spellcast trait and emptying the whole of
it into the next attack that lands.

Determinism comes from constructing rolls with fixed dice, from a target with a
Difficulty of 0 so no case turns on whether an attack landed, and from patching
`content.spellcast.roll_duality` where a case needs a cast to come out a
particular way.
"""

from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.fight import _apply_duality_outcome
from combat.rest import Rest
from combat.results import AttackResult
from combat.state import FightState
from content import (
    Status,
    apply_attack_missed,
    apply_on_damaged,
    apply_on_effect_landed,
    assess,
    total_extra_damage,
    use_free_abilities,
)
from content.conditions import (
    HIDDEN,
    HORRIFIED,
    ON_A_GM_TURN,
    RESTRAINED,
    VULNERABLE,
    Condition,
)
from content.damage_types import (
    DamageType,
    damage_type_named,
    includes,
    types_in,
)
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from domain_cards.midnight import (
    MIDNIGHT_TOUCHED,
    NIGHT_TERROR,
    SPELLCHARGE,
    SPELLCHARGE_DIE,
    SPELLCHARGE_TOKENS,
    TOLL_TOKENS,
    TOLLED,
    TWILIGHT_TOLL,
    TWILIGHT_TOLL_DIE,
    VANISHING_DODGE,
    _casts_with_magic,
    midnight_spirit,
    night_terror,
    rain_of_blades,
    shadowbind,
    twilight_toll,
    twilight_toll_collects,
    twilight_toll_falls,
)
from items.registry import find_weapon
from items.weapons import attack_with

RAIN_OF_BLADES = "Rain of Blades"
MIDNIGHT_SPIRIT = "Midnight Spirit"
SHADOWBIND = "Shadowbind"


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


def _make_printed_adversary(**overrides) -> Adversary:
    """A stat block with a printed damage type, which Vanishing Dodge reads."""
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


@contextmanager
def _bunched():
    """Every band at its best reach, so a case is about the card not the spread."""
    with patch("content.aoe.random.random", return_value=0.0):
        yield


# --- Rain of Blades ----------------------------------------------------------


def test_rain_of_blades_catches_everything_the_band_reaches():
    caster = _make_level_2_pc(domain_cards_loadout=[RAIN_OF_BLADES])
    mob = [_make_adversary(name=f"A{n}") for n in range(9)]
    state = _state([caster], mob)

    with _bunched():
        result = rain_of_blades(caster, mob[0], state)

    assert result.damage_roll.dice_groups[0] == DiceGroup(count=2, sides=8)
    assert len([a for a in mob if a.hp_marked > 0]) > 1
    assert caster.hope_marked == 5


def test_rain_of_blades_declines_against_a_single_target():
    caster = _make_level_2_pc(domain_cards_loadout=[RAIN_OF_BLADES])
    adversary = _make_adversary()
    state = _state([caster], [adversary])

    assert rain_of_blades(caster, adversary, state) is None
    assert caster.hope_marked == 6


def test_rain_of_blades_needs_a_hope():
    caster = _make_level_2_pc(domain_cards_loadout=[RAIN_OF_BLADES], hope_marked=0)
    mob = [_make_adversary(name=f"A{n}") for n in range(9)]
    state = _state([caster], mob)

    with _bunched():
        assert rain_of_blades(caster, mob[0], state) is None


def test_a_vulnerable_target_takes_more_than_the_others():
    """The rider is per target, so two adversaries in one sweep can differ.

    Both damage rolls are pinned to the same fixed five, so a Vulnerable target
    takes ten and everyone else takes five - and the thresholds are set between
    the two, which is the only way the difference shows up as marked HP.
    """
    caster = _make_level_2_pc(domain_cards_loadout=[RAIN_OF_BLADES])
    mob = [
        _make_adversary(name=f"A{n}", major_threshold=8, severe_threshold=1000)
        for n in range(9)
    ]
    state = _state([caster], mob)
    state.apply_condition(mob[1], Condition(name=VULNERABLE))

    fixed = DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=8)], die_results=[[5]], modifier=0
    )
    with _bunched(), patch("domain_cards.midnight.roll_damage", return_value=fixed):
        rain_of_blades(caster, mob[0], state)

    assert mob[0].hp_marked == 1  # 5, below the Major threshold
    assert mob[1].hp_marked == 2  # 5 + the Vulnerable rider's 5, which clears it


# --- Midnight Spirit ---------------------------------------------------------


def test_the_spirit_deals_spellcast_trait_dice():
    caster = _make_level_2_pc(domain_cards_loadout=[MIDNIGHT_SPIRIT])  # presence 3
    adversary = _make_adversary()
    state = _state([caster], [adversary])

    result = midnight_spirit(caster, adversary, state)

    assert result.damage_roll.dice_groups[0] == DiceGroup(count=3, sides=6)
    assert caster.hope_marked == 5


def test_the_spirit_costs_its_hope_even_on_a_miss():
    """The Hope pays for the summoning, which happens whether the spirit lands."""
    caster = _make_level_2_pc(domain_cards_loadout=[MIDNIGHT_SPIRIT])
    adversary = _make_adversary(difficulty=99)
    state = _state([caster], [adversary])

    missed = _roll(10, 4, difficulty=99)
    with patch("content.spellcast.roll_duality", return_value=missed):
        result = midnight_spirit(caster, adversary, state)

    assert result.damage_roll is None
    assert caster.hope_marked == 5
    assert adversary.hp_marked == 0


def test_no_spirit_without_a_hope():
    caster = _make_level_2_pc(domain_cards_loadout=[MIDNIGHT_SPIRIT], hope_marked=0)
    adversary = _make_adversary()
    state = _state([caster], [adversary])

    assert midnight_spirit(caster, adversary, state) is None


def test_a_spellcast_trait_of_zero_summons_nothing():
    caster = _make_level_2_pc(
        domain_cards_loadout=[MIDNIGHT_SPIRIT],
        traits={
            "agility": 0,
            "strength": 0,
            "finesse": 0,
            "instinct": 0,
            "presence": 0,
            "knowledge": 0,
        },
    )
    adversary = _make_adversary()
    state = _state([caster], [adversary])

    assert midnight_spirit(caster, adversary, state) is None
    assert caster.hope_marked == 6


# --- Shadowbind --------------------------------------------------------------


def test_shadowbind_restrains_what_it_beats():
    caster = _make_level_2_pc(domain_cards_loadout=[SHADOWBIND])
    mob = [_make_adversary(name=f"A{n}") for n in range(9)]
    state = _state([caster], mob)

    with _bunched():
        shadowbind(caster, mob[0], state)

    assert any(state.has_condition(a, RESTRAINED) for a in mob)


def test_binding_costs_the_gm_a_fear_per_adversary():
    """The card's whole value here, since Restrained does nothing by itself."""
    caster = _make_level_2_pc(domain_cards_loadout=[SHADOWBIND])
    mob = [_make_adversary(name=f"A{n}") for n in range(9)]
    state = _state([caster], mob, fear=6)

    with _bunched():
        shadowbind(caster, mob[0], state)

    bound = [a for a in mob if state.has_condition(a, RESTRAINED)]
    for adversary in bound:
        state.expire_conditions(adversary, ON_A_GM_TURN)

    assert state.fear == 6 - len(bound)


def test_shadowbind_declines_when_everything_in_reach_is_already_bound():
    caster = _make_level_2_pc(domain_cards_loadout=[SHADOWBIND])
    adversary = _make_adversary()
    state = _state([caster], [adversary])

    with _bunched():
        shadowbind(caster, adversary, state)

    with _bunched():
        assert shadowbind(caster, adversary, state) is None


def test_shadowbind_deals_no_damage():
    caster = _make_level_2_pc(domain_cards_loadout=[SHADOWBIND])
    mob = [_make_adversary(name=f"A{n}") for n in range(9)]
    state = _state([caster], mob)

    with _bunched():
        result = shadowbind(caster, mob[0], state)

    assert result.damage_roll is None
    assert all(a.hp_marked == 0 for a in mob)


# --- Midnight-Touched --------------------------------------------------------


def test_the_gm_gains_no_fear_and_the_pc_gains_a_hope():
    holder = _make_level_7_pc(domain_cards_loadout=[MIDNIGHT_TOUCHED], hope_marked=0)
    fight = _state([holder], [], rest=Rest.LONG)

    _apply_duality_outcome(holder, _roll(3, 9, difficulty=20), fight)

    assert fight.fear == 0
    assert holder.hope_marked == 1


def test_the_fear_lands_normally_when_the_pc_has_hope():
    holder = _make_level_7_pc(domain_cards_loadout=[MIDNIGHT_TOUCHED], hope_marked=2)
    fight = _state([holder], [], rest=Rest.LONG)

    _apply_duality_outcome(holder, _roll(3, 9, difficulty=20), fight)

    assert fight.fear == 1


def test_the_fear_conversion_is_once_per_rest():
    holder = _make_level_7_pc(domain_cards_loadout=[MIDNIGHT_TOUCHED], hope_marked=0)
    fight = _state([holder], [], rest=Rest.LONG)

    _apply_duality_outcome(holder, _roll(3, 9, difficulty=20), fight)
    holder.spend_hope(1)  # back to 0 Hope
    _apply_duality_outcome(holder, _roll(3, 9, difficulty=20), fight)

    assert fight.fear == 1


def _swing(loadout, roll, **overrides):
    """Swing a Broadsword on a fixed roll; return the flat damage modifier and the PC.

    The modifier is read off the `roll_damage` call rather than off the damage,
    since what the card adds is a number and any total can come from any dice.
    """
    holder = _make_level_7_pc(domain_cards_loadout=loadout, **overrides)
    target = _make_printed_adversary()
    fight = _state([holder], [target])

    with patch("items.weapons.roll_damage", return_value=Mock(total=5)) as rolled:
        with patch("items.weapons.roll_duality", return_value=roll):
            attack_with(holder, find_weapon("Broadsword"), target, fight=fight)

    return rolled.call_args.kwargs["modifier"], holder


LANDED = _roll(11, 9, difficulty=0)


def test_the_fear_die_is_added_to_a_landed_swing():
    """Whatever the weapon's own modifier is, plus the Fear Die showing 9."""
    with_card, _ = _swing([MIDNIGHT_TOUCHED], LANDED)
    without, _ = _swing([], LANDED)

    assert with_card == without + LANDED.fear_die_result


def test_the_fear_die_costs_a_stress():
    _, holder = _swing([MIDNIGHT_TOUCHED], LANDED)

    assert holder.stress_marked == 1


def test_the_fear_die_is_held_back_at_the_last_stress_slot():
    """The shared rule, like every other PC Stress cost."""
    with_card, holder = _swing(
        [MIDNIGHT_TOUCHED], LANDED, stress_max=2, stress_marked=1
    )
    without, _ = _swing([], LANDED)

    assert with_card == without
    assert holder.stress_marked == 1


# --- Vanishing Dodge ---------------------------------------------------------


def test_a_failed_physical_attack_buys_shadow():
    holder = _make_level_7_pc(domain_cards_loadout=[VANISHING_DODGE])
    attacker = _make_printed_adversary()
    fight = _state([holder], [attacker])

    apply_attack_missed(holder, attacker, _roll(2, 3), fight)

    assert fight.has_condition(holder, HIDDEN) is True
    assert holder.hope_marked == 5


def test_a_magic_attacker_is_not_dodged():
    """"An attack ... that would deal physical damage" - read off the stat block."""
    holder = _make_level_7_pc(domain_cards_loadout=[VANISHING_DODGE])
    attacker = _make_printed_adversary(damage_type="magic")
    fight = _state([holder], [attacker])

    apply_attack_missed(holder, attacker, _roll(2, 3), fight)

    assert fight.has_condition(holder, HIDDEN) is False
    assert holder.hope_marked == 6


def test_the_dodge_is_not_bought_twice_over():
    holder = _make_level_7_pc(domain_cards_loadout=[VANISHING_DODGE])
    attacker = _make_printed_adversary()
    fight = _state([holder], [attacker])

    apply_attack_missed(holder, attacker, _roll(2, 3), fight)
    apply_attack_missed(holder, attacker, _roll(2, 3), fight)

    assert holder.hope_marked == 5


def test_no_hope_means_no_dodge():
    holder = _make_level_7_pc(domain_cards_loadout=[VANISHING_DODGE], hope_marked=0)
    attacker = _make_printed_adversary()
    fight = _state([holder], [attacker])

    apply_attack_missed(holder, attacker, _roll(2, 3), fight)

    assert fight.has_condition(holder, HIDDEN) is False


# --- A printed damage type has to be parsed before it is read ----------------


def test_a_printed_damage_type_is_read_as_a_type_and_not_as_letters():
    """`Adversary.damage_type` is the string a catalogue entry wrote.

    Handing it straight to `types_in` gives a set of *characters*, which no
    `DamageType` is a member of - so a check written that way silently answers
    False for every adversary in the catalogue. Hush's `_casts_with_magic` had
    exactly that bug and stopped nobody acting; this pins both readings.
    """
    printed = _make_printed_adversary(damage_type="magic").type_of_damage()

    assert isinstance(printed, str)
    assert DamageType.MAGIC not in types_in(printed)  # the bug
    assert includes(damage_type_named(printed), DamageType.MAGIC)  # the fix


def test_hush_stops_an_adversary_whose_printed_attack_is_magic():
    assert _casts_with_magic(_make_printed_adversary(damage_type="magic")) is True
    assert _casts_with_magic(_make_printed_adversary(damage_type="physical")) is False


def test_a_dual_typed_attacker_counts_as_physical_for_the_dodge():
    """The Spellblade's "phy/mag" satisfies a physical restriction - the standing rule."""
    holder = _make_level_7_pc(domain_cards_loadout=[VANISHING_DODGE])
    attacker = _make_printed_adversary(damage_type="phy/mag")
    fight = _state([holder], [attacker])

    apply_attack_missed(holder, attacker, _roll(2, 3), fight)

    assert fight.has_condition(holder, HIDDEN) is True


# --- Spellcharge -------------------------------------------------------------


def _charged(**overrides):
    holder = _make_level_8_pc(domain_cards_loadout=[SPELLCHARGE], **overrides)
    target = _make_adversary()
    return holder, target, _rested_state([holder], [target])


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


# --- Night Terror ------------------------------------------------------------


def _terrifying(adversaries: int, fear: int = 6, **overrides):
    holder = _make_level_8_pc(level=9, domain_cards_loadout=[NIGHT_TERROR], **overrides)
    field = [_make_adversary(name=f"Dummy {index}") for index in range(adversaries)]
    return holder, field, _rested_state([holder], field, fear=fear)


def test_night_terror_horrifies_what_it_reaches_and_leaves_them_vulnerable():
    holder, field, fight = _terrifying(6)

    with _bunched(), patch("domain_cards.midnight.roll_d20") as rolled:
        rolled.return_value.is_success = False
        assert night_terror(holder, fight) is True

    horrified = [a for a in field if fight.has_condition(a, HORRIFIED)]
    assert horrified
    assert all(fight.is_vulnerable(a) for a in horrified)


def test_the_fear_it_steals_becomes_the_damage_it_deals():
    holder, field, fight = _terrifying(6, fear=6)

    with _bunched(), patch("domain_cards.midnight.roll_d20") as rolled:
        rolled.return_value.is_success = False
        night_terror(holder, fight)

    horrified = [a for a in field if fight.has_condition(a, HORRIFIED)]
    assert fight.fear == 6 - len(horrified)
    assert all(a.hp_marked > 0 for a in horrified)


def test_an_empty_fear_pool_still_horrifies_and_deals_nothing():
    """The card read literally: the dice are what the stolen Fear buys."""
    holder, field, fight = _terrifying(6, fear=0)

    with _bunched(), patch("domain_cards.midnight.roll_d20") as rolled:
        rolled.return_value.is_success = False
        night_terror(holder, fight)

    horrified = [a for a in field if fight.has_condition(a, HORRIFIED)]
    assert horrified
    assert all(a.hp_marked == 0 for a in field)


def test_a_target_that_holds_its_nerve_is_untouched():
    holder, field, fight = _terrifying(6)

    with _bunched(), patch("domain_cards.midnight.roll_d20") as rolled:
        rolled.return_value.is_success = True
        night_terror(holder, fight)

    assert not any(fight.has_condition(a, HORRIFIED) for a in field)
    assert all(a.hp_marked == 0 for a in field)
    assert fight.fear == 6


def test_night_terror_is_once_per_long_rest():
    holder, field, fight = _terrifying(6)

    with _bunched(), patch("domain_cards.midnight.roll_d20") as rolled:
        rolled.return_value.is_success = False
        assert night_terror(holder, fight) is True
        assert night_terror(holder, fight) is False


def test_the_gm_pays_a_fear_to_calm_one_down():
    """"Temporarily" on an adversary is the standing until-the-GM-pays reading."""
    holder, field, fight = _terrifying(6)

    with _bunched(), patch("domain_cards.midnight.roll_d20") as rolled:
        rolled.return_value.is_success = False
        night_terror(holder, fight)

    horrified = [a for a in field if fight.has_condition(a, HORRIFIED)][0]
    fight.fear = 2
    ended = fight.expire_conditions(horrified, ON_A_GM_TURN)

    assert HORRIFIED in ended
    assert fight.fear == 1


# --- Twilight Toll -----------------------------------------------------------


def _tolling(*hit_points: int, **overrides):
    holder = _make_level_8_pc(
        level=9, domain_cards_loadout=[TWILIGHT_TOLL], **overrides
    )
    field = [
        _make_adversary(name=f"Dummy {index}", hp_max=points)
        for index, points in enumerate(hit_points)
    ]
    return holder, field, _rested_state([holder], field)


def _landed_effect() -> AttackResult:
    """An action roll that succeeded and rolled no damage."""
    return AttackResult(attack_roll=_roll(9, 4, difficulty=5), damage_roll=None)


def test_the_toll_goes_on_the_toughest_adversary():
    holder, field, fight = _tolling(6, 12)

    assert twilight_toll(holder, fight) is True
    assert fight.token_count(holder, TOLLED) == id(field[1])


def test_the_toll_declines_while_one_already_stands():
    holder, field, fight = _tolling(6, 12)

    assert twilight_toll(holder, fight) is True
    assert twilight_toll(holder, fight) is False


def test_the_toll_is_re_chosen_once_its_creature_is_gone():
    """And re-choosing clears what the dead one's toll had banked."""
    holder, field, fight = _tolling(6, 12)
    twilight_toll(holder, fight)
    fight.set_token(holder, TOLL_TOKENS, 3)
    field[1].mark_hp(field[1].hp_max)

    assert twilight_toll(holder, fight) is True
    assert fight.token_count(holder, TOLLED) == id(field[0])
    assert fight.token_count(holder, TOLL_TOKENS) == 0


def test_a_damageless_success_against_the_tolled_creature_rings_it():
    holder, field, fight = _tolling(12)
    twilight_toll(holder, fight)

    twilight_toll_collects(holder, field[0], _landed_effect(), fight)

    assert fight.token_count(holder, TOLL_TOKENS) == 1


def test_the_same_success_against_anybody_else_rings_nothing():
    holder, field, fight = _tolling(6, 12)
    twilight_toll(holder, fight)  # goes on field[1]

    twilight_toll_collects(holder, field[0], _landed_effect(), fight)

    assert fight.token_count(holder, TOLL_TOKENS) == 0


def test_the_toll_reaches_the_hook_through_dispatch():
    """Nothing in combat/policy.py knows this card; it asks the hook."""
    holder, field, fight = _tolling(12)
    twilight_toll(holder, fight)

    apply_on_effect_landed(holder, field[0], _landed_effect(), fight)

    assert fight.token_count(holder, TOLL_TOKENS) == 1


def test_the_whole_pool_falls_on_the_next_damage():
    holder, field, fight = _tolling(12)
    twilight_toll(holder, fight)
    fight.set_token(holder, TOLL_TOKENS, 3)

    groups = twilight_toll_falls(holder, field[0], _roll(9, 4, 5), fight)

    assert groups == [DiceGroup(count=3, sides=TWILIGHT_TOLL_DIE, discardable=False)]
    assert fight.token_count(holder, TOLL_TOKENS) == 0


def test_the_toll_never_falls_on_anybody_else():
    holder, field, fight = _tolling(6, 12)
    twilight_toll(holder, fight)  # goes on field[1]
    fight.set_token(holder, TOLL_TOKENS, 3)

    assert twilight_toll_falls(holder, field[0], _roll(9, 4, 5), fight) == []
    assert fight.token_count(holder, TOLL_TOKENS) == 3


def test_an_unrung_toll_adds_no_dice():
    holder, field, fight = _tolling(12)
    twilight_toll(holder, fight)

    assert twilight_toll_falls(holder, field[0], _roll(9, 4, 5), fight) == []


def test_the_toll_is_offered_as_a_free_ability():
    holder, field, fight = _tolling(12)

    assert use_free_abilities(holder, fight, limit=1) == [TWILIGHT_TOLL]


# --- Assessed and dismissed --------------------------------------------------


@pytest.mark.parametrize("card", ["Pick and Pull", "Uncanny Disguise"])
def test_the_two_social_cards_are_declared_rather_than_absent(card):
    assessment = assess(card)

    assert assessment.status is Status.NO_COMBAT_EFFECT
    assert assessment.reason


def test_the_level_eight_pair_are_assessed():
    assert assess(SPELLCHARGE).status is Status.MODELLED
    assert assess("Shadowhunter").status is Status.NO_COMBAT_EFFECT


def test_the_level_nine_pair_are_modelled():
    for card in (NIGHT_TERROR, TWILIGHT_TOLL):
        assert assess(card).status is Status.MODELLED
