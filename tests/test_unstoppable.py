"""The Guardian's Unstoppable, driven directly rather than through a fight.

Every hook is called by hand with fixed state, so nothing here depends on dice.
What's under test is the state machine: when it turns on, what it does while
it's running, and the two ways it ends.
"""

from types import SimpleNamespace

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.state import FightState
from content.conditions import RESTRAINED, VULNERABLE
from content.damage_types import DamageType
from features.classes import (
    UNSTOPPABLE,
    unstoppable,
    unstoppable_adds_damage,
    unstoppable_grows,
    unstoppable_immunities,
    unstoppable_reduces_severity,
)

# Unstoppable and Iron Will are both physical-only on the page, so nearly every
# case here has to state a type. Aliased so the assertions stay readable.
PHYSICAL = DamageType.PHYSICAL


def _guardian(level: int = 1, hp_marked: int = 1) -> PlayerCharacter:
    return PlayerCharacter(
        name="Test Guardian",
        level=level,
        character_class="Guardian",
        subclass="Stalwart",
        ancestry="Human",
        community="Wanderborne",
        traits={
            "agility": 0, "strength": 2, "finesse": 0,
            "instinct": 0, "presence": 0, "knowledge": 0,
        },
        evasion=9,
        proficiency=1,
        major_threshold=6,
        severe_threshold=12,
        hp_max=7,
        stress_max=6,
        hope_max=6,
        armor_max=3,
        primary_weapon="Greatsword",
        secondary_weapon=None,
        armor_item="Gambeson Armor",
        domain_cards_loadout=[],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
        hp_marked=hp_marked,
    )


def _fight(guardian: PlayerCharacter, adversaries: int = 1) -> FightState:
    stat_block = Adversary(
        name="Test Adversary",
        tier=1,
        difficulty=11,
        major_threshold=5,
        severe_threshold=10,
        hp_max=5,
        stress_max=3,
        attack_modifier=1,
    )
    return FightState(
        encounter_name="Test",
        party=[guardian],
        adversaries=[stat_block.spawn() for _ in range(adversaries)],
        rest=Rest.LONG,
    )


def _a_hit_marking(hp: int):
    """The slice of an AttackResult the on-hit hook actually reads."""
    return SimpleNamespace(hp_marked=hp)


def test_becomes_unstoppable_with_the_die_showing_one():
    guardian = _guardian()
    fight = _fight(guardian)

    assert unstoppable(guardian, fight) is True
    assert fight.token_count(guardian, UNSTOPPABLE) == 1


def test_declines_before_the_guardian_has_been_hit():
    guardian = _guardian(hp_marked=0)
    fight = _fight(guardian)

    assert unstoppable(guardian, fight) is False
    assert fight.token_count(guardian, UNSTOPPABLE) == 0


def test_declining_does_not_spend_the_once_per_long_rest_use():
    """Declining has to be side-effect free, or the shuffle would eat the use."""
    guardian = _guardian(hp_marked=0)
    fight = _fight(guardian)

    unstoppable(guardian, fight)

    assert fight.can_use_once_per_rest(guardian, UNSTOPPABLE, long=True) is True


def test_cannot_be_used_twice_in_one_fight():
    guardian = _guardian()
    fight = _fight(guardian)

    assert unstoppable(guardian, fight) is True
    fight.spend_tokens(guardian, UNSTOPPABLE, fight.token_count(guardian, UNSTOPPABLE))

    assert unstoppable(guardian, fight) is False


def test_is_not_available_without_a_long_rest():
    guardian = _guardian()
    fight = _fight(guardian)
    fight.rest = Rest.NONE

    assert unstoppable(guardian, fight) is False


def test_severity_drops_by_one_threshold_while_running():
    guardian = _guardian()
    fight = _fight(guardian)
    unstoppable(guardian, fight)

    assert unstoppable_reduces_severity(guardian, 20, 3, fight, PHYSICAL) == 2
    assert unstoppable_reduces_severity(guardian, 8, 2, fight, PHYSICAL) == 1


def test_severity_floors_at_zero():
    """Minor to None - a hit that would have marked one HP marks nothing."""
    guardian = _guardian()
    fight = _fight(guardian)
    unstoppable(guardian, fight)

    assert unstoppable_reduces_severity(guardian, 3, 1, fight, PHYSICAL) == 0
    assert unstoppable_reduces_severity(guardian, 3, 0, fight, PHYSICAL) == 0


def test_magic_damage_is_untouched_even_while_running():
    """"When you take physical damage" - the restriction the page prints."""
    guardian = _guardian()
    fight = _fight(guardian)
    unstoppable(guardian, fight)

    assert unstoppable_reduces_severity(guardian, 20, 3, fight, DamageType.MAGIC) == 3


def test_untyped_damage_is_untouched_even_while_running():
    """Untyped matches no restriction, so an unauthored type can only cost less."""
    guardian = _guardian()
    fight = _fight(guardian)
    unstoppable(guardian, fight)

    assert unstoppable_reduces_severity(guardian, 20, 3, fight) == 3


def test_severity_is_untouched_when_not_unstoppable():
    guardian = _guardian()
    fight = _fight(guardian)

    assert unstoppable_reduces_severity(guardian, 20, 3, fight, PHYSICAL) == 3


def test_severity_is_untouched_without_a_fight_to_read_state_from():
    """Damage can resolve outside a fight; the feature declines rather than raising."""
    guardian = _guardian()

    assert unstoppable_reduces_severity(guardian, 20, 3, None, PHYSICAL) == 3


def test_damage_bonus_is_the_current_die_value():
    guardian = _guardian()
    fight = _fight(guardian)
    unstoppable(guardian, fight)

    assert unstoppable_adds_damage(guardian, None, fight) == 1

    unstoppable_grows(guardian, None, _a_hit_marking(2), fight)

    assert unstoppable_adds_damage(guardian, None, fight) == 2


def test_no_damage_bonus_when_not_unstoppable():
    guardian = _guardian()
    fight = _fight(guardian)

    assert unstoppable_adds_damage(guardian, None, fight) == 0


def test_the_die_only_grows_on_a_hit_that_marked_hp():
    guardian = _guardian()
    fight = _fight(guardian)
    unstoppable(guardian, fight)

    unstoppable_grows(guardian, None, _a_hit_marking(0), fight)

    assert fight.token_count(guardian, UNSTOPPABLE) == 1


def test_the_die_falls_off_when_it_would_pass_its_maximum():
    """A level 1 die is a d4: 1, 2, 3, 4, then out."""
    guardian = _guardian()
    fight = _fight(guardian)
    unstoppable(guardian, fight)

    for expected in (2, 3, 4):
        unstoppable_grows(guardian, None, _a_hit_marking(1), fight)
        assert fight.token_count(guardian, UNSTOPPABLE) == expected

    unstoppable_grows(guardian, None, _a_hit_marking(1), fight)

    assert fight.token_count(guardian, UNSTOPPABLE) == 0
    assert unstoppable_adds_damage(guardian, None, fight) == 0


def test_the_die_is_a_d6_from_level_five():
    guardian = _guardian(level=5)
    fight = _fight(guardian)
    unstoppable(guardian, fight)

    for _ in range(5):
        unstoppable_grows(guardian, None, _a_hit_marking(1), fight)

    assert fight.token_count(guardian, UNSTOPPABLE) == 6


def test_unstoppable_turns_off_vulnerable_and_restrained():
    guardian = _guardian()
    fight = _fight(guardian)
    unstoppable(guardian, fight)

    assert unstoppable_immunities(guardian, VULNERABLE, fight) is True
    assert unstoppable_immunities(guardian, RESTRAINED, fight) is True
    assert unstoppable_immunities(guardian, "Hidden", fight) is False


def test_no_immunity_when_not_unstoppable():
    guardian = _guardian()
    fight = _fight(guardian)

    assert unstoppable_immunities(guardian, VULNERABLE, fight) is False
