"""Subclass features, and the extra-damage hook School of War needed.

Face Your Fear is the first content keyed on *how* an attack roll came out, so
these pin both halves: that the feature reads the outcome correctly, and that
what it returns joins the attack's own damage roll rather than arriving as a
second hit.

Rolls are built by hand or patched - nothing here depends on the dice.
"""

from unittest.mock import patch

from characters.player_character import PlayerCharacter
from content import total_extra_damage
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityOutcome, DualityRollResult
from features.subclasses import FACE_YOUR_FEAR_DIE, face_your_fear
from items.weapons import greatstaff_attack


class FakeTarget:
    """Minimal stand-in for the items.weapons.Target protocol."""

    def __init__(self, difficulty: int = 10):
        self.difficulty = difficulty
        self.damage_taken: list[int] = []

    def take_damage(self, amount: int, fight=None) -> int:
        self.damage_taken.append(amount)
        return amount


def _make_wizard(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test Wizard",
        level=1,
        character_class="Wizard",
        subclass="School of War",
        # Invented, so an ancestry or community feature can't join the roll and
        # change what these tests are measuring.
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 0, "strength": 0, "finesse": 0,
            "instinct": 0, "presence": 0, "knowledge": 2,
        },
        evasion=10,
        proficiency=1,
        major_threshold=5,
        severe_threshold=11,
        hp_max=6,
        stress_max=6,
        hope_max=6,
        armor_max=3,
        primary_weapon="Greatstaff",
        secondary_weapon=None,
        armor_item="Gambeson Armor",
        domain_cards_loadout=[],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
    )
    defaults.update(overrides)
    return PlayerCharacter(**defaults)


def _roll(*, hope: int, fear: int, modifier: int = 5, difficulty: int = 10) -> DualityRollResult:
    return DualityRollResult(
        hope_die_result=hope,
        fear_die_result=fear,
        modifier=modifier,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=difficulty,
    )


SUCCESS_WITH_FEAR = _roll(hope=3, fear=9)
SUCCESS_WITH_HOPE = _roll(hope=9, fear=3)
CRITICAL = _roll(hope=7, fear=7)
FAILURE_WITH_FEAR = _roll(hope=1, fear=2, modifier=0, difficulty=20)


# --- The feature -------------------------------------------------------------


def test_a_success_with_fear_adds_the_die():
    wizard = _make_wizard()

    assert SUCCESS_WITH_FEAR.outcome is DualityOutcome.FEAR
    assert face_your_fear(wizard, None, SUCCESS_WITH_FEAR) == [
        DiceGroup(count=1, sides=FACE_YOUR_FEAR_DIE, discardable=False)
    ]


def test_a_success_with_hope_adds_nothing():
    assert face_your_fear(_make_wizard(), None, SUCCESS_WITH_HOPE) == []


def test_a_critical_is_not_a_success_with_fear():
    """The dice matched, so the outcome is its own thing - not Fear."""
    assert CRITICAL.outcome is DualityOutcome.CRIT
    assert face_your_fear(_make_wizard(), None, CRITICAL) == []


def test_a_failed_attack_adds_nothing_however_it_rolled():
    assert FAILURE_WITH_FEAR.outcome is DualityOutcome.FEAR
    assert face_your_fear(_make_wizard(), None, FAILURE_WITH_FEAR) == []


# --- The dispatch ------------------------------------------------------------


def test_the_dispatch_finds_the_feature_by_the_name_on_the_sheet():
    wizard = _make_wizard()

    assert total_extra_damage(wizard, None, SUCCESS_WITH_FEAR) == [
        DiceGroup(count=1, sides=FACE_YOUR_FEAR_DIE, discardable=False)
    ]


def test_a_character_without_the_subclass_gets_no_extra_dice():
    other = _make_wizard(subclass="Unwritten Subclass")

    assert total_extra_damage(other, None, SUCCESS_WITH_FEAR) == []


# --- The call site -----------------------------------------------------------


def test_the_extra_die_joins_the_weapons_own_damage_roll():
    """One roll, not two: the die is in the pool the weapon asks for.

    That's the whole reason this hook exists rather than using on_hit - dice
    added afterwards would be a second hit, measured against the target's
    thresholds all over again.
    """
    wizard = _make_wizard(proficiency=1)
    target = FakeTarget(difficulty=10)
    damage_roll = DamageRollResult(
        dice_groups=[DiceGroup(count=2, sides=6)], die_results=[[3, 4]], modifier=0
    )

    with (
        patch("items.weapons.roll_duality", return_value=SUCCESS_WITH_FEAR),
        patch("items.weapons.roll_damage", return_value=damage_roll) as mock_roll_damage,
    ):
        greatstaff_attack(wizard, target)

    kwargs = mock_roll_damage.call_args.kwargs
    # Greatstaff is Powerful, so the weapon's own pool is Proficiency + 1 d6s,
    # and Face Your Fear's d10 sits alongside it in the same roll - marked out
    # of the discard's reach, since Powerful throws away one of the weapon's own
    # dice rather than one the Wizard's subclass added.
    assert kwargs["dice_groups"] == [
        DiceGroup(count=2, sides=6),
        DiceGroup(count=1, sides=FACE_YOUR_FEAR_DIE, discardable=False),
    ]
    assert kwargs["drop_lowest"] == 1


def test_no_extra_die_reaches_the_damage_roll_on_a_success_with_hope():
    wizard = _make_wizard(proficiency=1)
    target = FakeTarget(difficulty=10)
    damage_roll = DamageRollResult(
        dice_groups=[DiceGroup(count=2, sides=6)], die_results=[[3, 4]], modifier=0
    )

    with (
        patch("items.weapons.roll_duality", return_value=SUCCESS_WITH_HOPE),
        patch("items.weapons.roll_damage", return_value=damage_roll) as mock_roll_damage,
    ):
        greatstaff_attack(wizard, target)

    assert mock_roll_damage.call_args.kwargs["dice_groups"] == [DiceGroup(count=2, sides=6)]
