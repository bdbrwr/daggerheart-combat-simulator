"""Tests for the party's weapons and the discarded-die feature under them.

Separate from tests/test_weapons.py, which covers the Broadsword and the shared
attack shape. This file is about what was added for the Immareth party:
Shortbow, Greatsword and Greatstaff, and the Massive/Powerful feature they
brought with them.

The discard arithmetic is checked by building DamageRollResult directly with
fixed dice, so there's nothing to seed. The attacks themselves are checked for
properties true of every call - which trait was read, how many dice were rolled
- rather than for a total, since a total needs dice.
"""

import random

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from items.registry import find_weapon
from items.weapons import attack_with


def _make_character(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=2,
        character_class="Guardian",
        subclass="Stalwart",
        ancestry="Human",
        community="Wanderborne",
        traits={"agility": 1, "strength": 3, "finesse": -1, "instinct": 1, "presence": 1, "knowledge": 0},
        evasion=8,
        proficiency=2,
        major_threshold=11,
        severe_threshold=22,
        hp_max=7,
        stress_max=7,
        hope_max=6,
        armor_max=4,
        primary_weapon="Greatsword",
        secondary_weapon=None,
        armor_item="Irontree Breastplate Armor",
        domain_cards_loadout=[],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
    )
    defaults.update(overrides)
    return PlayerCharacter(**defaults)


def _make_adversary(**overrides) -> Adversary:
    defaults = dict(
        name="Target Dummy",
        tier=1,
        difficulty=0,  # every attack lands, so damage always resolves
        major_threshold=100,
        severe_threshold=200,
        hp_max=500,
        stress_max=3,
        attack_modifier=0,
        damage_dice=[],
        damage_modifier=0,
    )
    defaults.update(overrides)
    return Adversary(**defaults)


# --- Discarding the lowest die -----------------------------------------------


def _result(dice: list[int], sides: int = 10, **overrides) -> DamageRollResult:
    defaults = dict(
        dice_groups=[DiceGroup(count=len(dice), sides=sides)],
        die_results=[dice],
        modifier=0,
    )
    defaults.update(overrides)
    return DamageRollResult(**defaults)


def test_nothing_is_discarded_by_default():
    assert _result([1, 2, 3]).rolled_total == 6
    assert _result([1, 2, 3]).dropped == []


def test_the_lowest_die_is_discarded():
    rolled = _result([7, 2, 5], drop_lowest=1)

    assert rolled.dropped == [2]
    assert rolled.rolled_total == 12


def test_only_one_copy_of_a_repeated_low_roll_is_discarded():
    rolled = _result([3, 3, 9], drop_lowest=1)

    assert rolled.dropped == [3]
    assert rolled.rolled_total == 12


def test_discarding_reaches_across_dice_groups():
    """'The lowest result' is the lowest of the whole roll, not per group."""
    rolled = DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=10), DiceGroup(count=1, sides=4)],
        die_results=[[8], [1]],
        modifier=0,
        drop_lowest=1,
    )

    assert rolled.dropped == [1]
    assert rolled.rolled_total == 8


def test_the_modifier_survives_a_discard():
    assert _result([6, 2], modifier=3, drop_lowest=1).total == 9


def test_a_discarded_die_is_not_paid_for_in_the_critical_bonus():
    """Three d10s with one discarded crits for two dice, not three."""
    rolled = _result([4, 4, 4], sides=10, is_critical=True, drop_lowest=1)

    assert rolled.critical_bonus == 20
    assert rolled.rolled_total == 8
    assert rolled.total == 28


def test_a_critical_without_a_discard_is_unchanged():
    assert _result([4, 4], sides=10, is_critical=True).critical_bonus == 20


def test_the_repr_says_what_was_thrown_away():
    assert "dropped=[2]" in repr(_result([7, 2], drop_lowest=1))


# --- The weapons themselves --------------------------------------------------


def test_every_weapon_on_the_party_sheets_resolves():
    for name in ("Broadsword", "Shortbow", "Greatsword", "Greatstaff"):
        assert find_weapon(name) is not None


def test_a_weapon_that_discards_rolls_one_extra_die():
    """Greatsword at Proficiency 2 rolls three d10s and keeps the best two."""
    random.seed(4)

    result = attack_with(
        _make_character(proficiency=2), find_weapon("Greatsword"), _make_adversary()
    )

    assert result.damage_roll.dice_groups == [DiceGroup(count=3, sides=10)]
    assert len(result.damage_roll.dropped) == 1


def test_a_weapon_without_the_feature_rolls_proficiency_dice():
    random.seed(4)

    result = attack_with(
        _make_character(proficiency=2), find_weapon("Shortbow"), _make_adversary()
    )

    assert result.damage_roll.dice_groups == [DiceGroup(count=2, sides=6)]
    assert result.damage_roll.dropped == []
    assert result.damage_roll.modifier == 3


def test_the_greatstaff_has_no_flat_modifier():
    random.seed(4)

    result = attack_with(_make_character(), find_weapon("Greatstaff"), _make_adversary())

    assert result.damage_roll.modifier == 0


def test_each_weapon_reads_the_trait_the_srd_gives_it():
    """Knowledge +50 can't fail against Difficulty 40; Strength +3 would."""
    generous = {"agility": 0, "strength": 0, "finesse": 0, "instinct": 0, "presence": 0, "knowledge": 50}
    random.seed(1)

    staff = attack_with(
        _make_character(traits=generous),
        find_weapon("Greatstaff"),
        _make_adversary(difficulty=40),
    )

    assert staff.attack_roll.is_success is True


def test_an_experience_bonus_reaches_the_attack_roll():
    random.seed(9)
    unaided = attack_with(
        _make_character(), find_weapon("Greatsword"), _make_adversary(difficulty=99)
    )

    random.seed(9)
    aided = attack_with(
        _make_character(),
        find_weapon("Greatsword"),
        _make_adversary(difficulty=99),
        AdvantageState.NONE,
        50,
    )

    assert unaided.attack_roll.total + 50 == aided.attack_roll.total
