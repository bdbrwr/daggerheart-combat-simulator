"""Class features that ride on a roll or on an attack that landed.

The Guardian's Unstoppable has its own module; this covers the Wizard's Strange
Patterns and the Ranger's two riders. Every roll here is built by hand, and the
one piece of randomness - the number Strange Patterns watches for - is patched,
so nothing depends on the dice.
"""

from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.results import AttackResult
from combat.state import FightState
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from features.classes import (
    RANGERS_FOCUS,
    STRANGE_PATTERNS,
    ranger_riders,
    strange_patterns,
)

WATCHED = 7


def _make_pc(character_class: str, **overrides) -> PlayerCharacter:
    defaults = dict(
        name=f"Test {character_class}",
        level=2,
        character_class=character_class,
        # Invented, so nothing else on the sheet joins in.
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


def _make_adversary(name: str = "Bandit", difficulty: int = 11) -> Adversary:
    return Adversary(
        name=name,
        tier=1,
        difficulty=difficulty,
        major_threshold=5,
        severe_threshold=10,
        hp_max=8,
        stress_max=3,
        attack_modifier=1,
    )


def _fight(pc: PlayerCharacter, adversaries: list[Adversary]) -> FightState:
    return FightState(encounter_name="Test", party=[pc], adversaries=adversaries)


def _roll(*, hope: int, fear: int, modifier: int = 5, difficulty: int = 11) -> DualityRollResult:
    return DualityRollResult(
        hope_die_result=hope,
        fear_die_result=fear,
        modifier=modifier,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=difficulty,
    )


def _landed(total: int = 6, roll: DualityRollResult | None = None) -> AttackResult:
    """An attack that hit, with a damage roll adding up to `total`."""
    return AttackResult(
        attack_roll=roll or _roll(hope=9, fear=6),  # total 20
        damage_roll=DamageRollResult(
            dice_groups=[DiceGroup(count=1, sides=8)],
            die_results=[[total]],
            modifier=0,
        ),
        hp_marked=2,
    )


# --- Strange Patterns --------------------------------------------------------


def _wizard_watching(**overrides):
    """A Wizard and a fight, with the watched number already drawn."""
    wizard = _make_pc("Wizard", **overrides)
    fight = _fight(wizard, [_make_adversary()])
    fight.set_token(wizard, STRANGE_PATTERNS, WATCHED)
    return wizard, fight


def test_the_number_is_drawn_once_and_then_kept():
    wizard = _make_pc("Wizard")
    fight = _fight(wizard, [_make_adversary()])

    with patch("features.classes.random.randint", return_value=WATCHED) as mock_randint:
        strange_patterns(wizard, _roll(hope=1, fear=2), fight)
        strange_patterns(wizard, _roll(hope=1, fear=2), fight)

    assert mock_randint.call_count == 1
    assert fight.token_count(wizard, STRANGE_PATTERNS) == WATCHED


def test_the_number_on_the_hope_die_gains_a_hope():
    wizard, fight = _wizard_watching(hope_marked=0)

    strange_patterns(wizard, _roll(hope=WATCHED, fear=2), fight)

    assert wizard.hope_marked == 1


def test_the_number_on_the_fear_die_counts_too():
    """The card says "a Duality Die", not the Hope Die."""
    wizard, fight = _wizard_watching(hope_marked=0)

    strange_patterns(wizard, _roll(hope=2, fear=WATCHED), fight)

    assert wizard.hope_marked == 1


def test_any_other_number_does_nothing():
    wizard, fight = _wizard_watching(hope_marked=0)

    strange_patterns(wizard, _roll(hope=WATCHED + 1, fear=WATCHED - 1), fight)

    assert wizard.hope_marked == 0


def test_a_marked_stress_is_cleared_in_preference_to_gaining_hope():
    wizard, fight = _wizard_watching(hope_marked=0)
    wizard.mark_stress(2)

    strange_patterns(wizard, _roll(hope=WATCHED, fear=2), fight)

    assert wizard.stress_marked == 1
    assert wizard.hope_marked == 0


def test_both_dice_showing_the_number_fires_once():
    wizard, fight = _wizard_watching(hope_marked=0)

    strange_patterns(wizard, _roll(hope=WATCHED, fear=WATCHED), fight)

    assert wizard.hope_marked == 1


# --- Ranger's Focus ----------------------------------------------------------


def test_a_landed_attack_spends_a_hope_to_mark_a_focus():
    ranger = _make_pc("Ranger", hope_marked=2)
    adversary = _make_adversary()
    fight = _fight(ranger, [adversary])

    ranger_riders(ranger, adversary, _landed(), fight)

    assert ranger.hope_marked == 1
    assert fight.token_count(ranger, RANGERS_FOCUS) == id(adversary)
    assert adversary.stress_marked == 0  # the Focus starts after this attack


def test_damaging_the_focus_forces_it_to_mark_a_stress():
    ranger = _make_pc("Ranger", hope_marked=2)
    adversary = _make_adversary()
    fight = _fight(ranger, [adversary])

    ranger_riders(ranger, adversary, _landed(), fight)
    ranger_riders(ranger, adversary, _landed(), fight)

    assert adversary.stress_marked == 1
    assert ranger.hope_marked == 1  # no second Hope for the same Focus


def test_focusing_somebody_else_ends_the_first_focus():
    ranger = _make_pc("Ranger", hope_marked=4)
    first, second = _make_adversary("First"), _make_adversary("Second")
    fight = _fight(ranger, [first, second])

    ranger_riders(ranger, first, _landed(), fight)
    ranger_riders(ranger, second, _landed(), fight)

    assert fight.token_count(ranger, RANGERS_FOCUS) == id(second)


def test_no_focus_is_marked_without_a_hope_to_spend():
    ranger = _make_pc("Ranger", hope_marked=0)
    adversary = _make_adversary()
    fight = _fight(ranger, [adversary])

    ranger_riders(ranger, adversary, _landed(), fight)

    assert fight.token_count(ranger, RANGERS_FOCUS) == 0


def test_a_missed_attack_carries_no_riders():
    ranger = _make_pc("Ranger", hope_marked=6)
    adversary = _make_adversary()
    fight = _fight(ranger, [adversary])
    missed = AttackResult(attack_roll=_roll(hope=1, fear=2), damage_roll=None)

    ranger_riders(ranger, adversary, missed, fight)

    assert ranger.hope_marked == 6
    assert fight.token_count(ranger, RANGERS_FOCUS) == 0


# --- Hold Them Off -----------------------------------------------------------


def test_three_hope_carries_the_roll_to_two_more_adversaries():
    ranger = _make_pc("Ranger", hope_marked=6)
    target = _make_adversary("Target")
    others = [_make_adversary("Second"), _make_adversary("Third")]
    fight = _fight(ranger, [target, *others])

    ranger_riders(ranger, target, _landed(total=6), fight)

    assert all(adversary.hp_marked == 2 for adversary in others)  # 6 is Major
    # Three Hope for Hold Them Off, then one more to mark the Focus.
    assert ranger.hope_marked == 2


def test_hold_them_off_needs_two_others_to_be_worth_it():
    ranger = _make_pc("Ranger", hope_marked=6)
    target, other = _make_adversary("Target"), _make_adversary("Other")
    fight = _fight(ranger, [target, other])

    ranger_riders(ranger, target, _landed(), fight)

    assert other.hp_marked == 0
    assert ranger.hope_marked == 5  # only the Focus was paid for


def test_no_hope_is_spent_when_the_roll_beats_neither_of_them():
    ranger = _make_pc("Ranger", hope_marked=6)
    target = _make_adversary("Target")
    tough = [
        _make_adversary("Second", difficulty=25),
        _make_adversary("Third", difficulty=25),
    ]
    fight = _fight(ranger, [target, *tough])

    ranger_riders(ranger, target, _landed(), fight)

    assert all(adversary.hp_marked == 0 for adversary in tough)
    assert ranger.hope_marked == 5  # the Focus, and nothing else


def test_hold_them_off_is_not_paid_for_without_the_full_three_hope():
    ranger = _make_pc("Ranger", hope_marked=2)
    target = _make_adversary("Target")
    others = [_make_adversary("Second"), _make_adversary("Third")]
    fight = _fight(ranger, [target, *others])

    ranger_riders(ranger, target, _landed(), fight)

    assert all(adversary.hp_marked == 0 for adversary in others)
    assert ranger.hope_marked == 1  # the Focus only
