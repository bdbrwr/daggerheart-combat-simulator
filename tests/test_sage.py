"""Sage domain cards.

Both implemented cards make or respond to rolls, so the dice are patched and
what's under test is the decision-making around them: when a card fires, what it
costs, and what it drains from the GM.

Restraining isn't tracked, so Vicious Entangle's Restrains are Fear off the GM's
pool per SIMULATION-RULES.md - which makes the Fear count the thing to assert on.
"""

from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.state import FightState
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from domain_cards.sage import (
    BEETLES,
    beetles_take_the_hit,
    fire_flies,
    tekaira_armored_beetles,
    vicious_entangle,
)


def _make_ranger(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Luma",
        level=2,
        character_class="Ranger",
        subclass="Beastbound",
        # Invented, so nothing else can join the roll or soften the damage.
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 2, "strength": 0, "finesse": 1,
            "instinct": 1, "presence": 0, "knowledge": 0,
        },
        evasion=11,
        proficiency=1,
        major_threshold=6,
        severe_threshold=12,
        hp_max=6,
        stress_max=6,
        hope_max=6,
        armor_max=0,  # off unless a test is about armor
        primary_weapon="Shortbow",
        secondary_weapon=None,
        armor_item="Gambeson Armor",
        domain_cards_loadout=["Vicious Entangle", "Conjure Swarm"],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
        spellcast_trait="agility",
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
        hp_max=5,
        stress_max=3,
        attack_modifier=1,
    )


def _fight(ranger: PlayerCharacter, adversaries: list[Adversary], fear: int = 3) -> FightState:
    return FightState(
        encounter_name="Test",
        party=[ranger],
        adversaries=adversaries,
        fear=fear,
    )


def _roll(*, hope: int, fear: int, modifier: int, difficulty: int) -> DualityRollResult:
    return DualityRollResult(
        hope_die_result=hope,
        fear_die_result=fear,
        modifier=modifier,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=difficulty,
    )


HIT = _roll(hope=9, fear=6, modifier=2, difficulty=11)  # total 17
MISS = _roll(hope=2, fear=1, modifier=2, difficulty=11)  # total 5


def _damage(total: int) -> DamageRollResult:
    return DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=8)], die_results=[[total - 1]], modifier=1
    )


# --- Vicious Entangle --------------------------------------------------------


def test_entangle_deals_damage_and_drains_a_fear_for_the_restrain():
    ranger = _make_ranger(hope_marked=0)
    adversary = _make_adversary()
    fight = _fight(ranger, [adversary], fear=3)

    with (
        patch("domain_cards.sage.roll_duality", return_value=HIT),
        patch("domain_cards.sage.roll_damage", return_value=_damage(6)),
    ):
        result = vicious_entangle(ranger, adversary, fight)

    assert result.hit is True
    assert adversary.hp_marked == 2  # 6 is at the Major threshold of 5
    assert fight.fear == 2


def test_a_missed_entangle_costs_the_gm_nothing():
    ranger = _make_ranger()
    adversary = _make_adversary()
    fight = _fight(ranger, [adversary], fear=3)

    with (
        patch("domain_cards.sage.roll_duality", return_value=MISS),
        patch("domain_cards.sage.roll_damage") as mock_roll_damage,
    ):
        result = vicious_entangle(ranger, adversary, fight)

    assert result.hit is False
    assert result.damage_roll is None
    assert fight.fear == 3
    mock_roll_damage.assert_not_called()


def test_a_hope_buys_a_second_restrain_and_a_second_fear():
    ranger = _make_ranger(hope_marked=2)
    first, second = _make_adversary("First"), _make_adversary("Second")
    fight = _fight(ranger, [first, second], fear=3)

    with (
        patch("domain_cards.sage.roll_duality", return_value=HIT),
        patch("domain_cards.sage.roll_damage", return_value=_damage(6)),
    ):
        vicious_entangle(ranger, first, fight)

    assert ranger.hope_marked == 1
    assert fight.fear == 1  # one Fear per Restrain


def test_no_hope_is_spent_with_nobody_else_to_restrain():
    ranger = _make_ranger(hope_marked=2)
    adversary = _make_adversary()
    fight = _fight(ranger, [adversary], fear=3)

    with (
        patch("domain_cards.sage.roll_duality", return_value=HIT),
        patch("domain_cards.sage.roll_damage", return_value=_damage(6)),
    ):
        vicious_entangle(ranger, adversary, fight)

    assert ranger.hope_marked == 2


def test_no_hope_is_spent_when_the_gm_has_no_fear_left_to_take():
    """At 0 Fear a temporary condition is free to the GM, so the Hope buys nothing."""
    ranger = _make_ranger(hope_marked=2)
    first, second = _make_adversary("First"), _make_adversary("Second")
    fight = _fight(ranger, [first, second], fear=0)

    with (
        patch("domain_cards.sage.roll_duality", return_value=HIT),
        patch("domain_cards.sage.roll_damage", return_value=_damage(6)),
    ):
        vicious_entangle(ranger, first, fight)

    assert ranger.hope_marked == 2
    assert fight.fear == 0


def test_a_caster_with_no_spellcast_trait_declines():
    """Declining is how unusable content shows up, rather than a wrong guess."""
    ranger = _make_ranger(spellcast_trait="")
    adversary = _make_adversary()
    fight = _fight(ranger, [adversary])

    assert vicious_entangle(ranger, adversary, fight) is None


# --- Conjure Swarm: the beetles ----------------------------------------------


def test_the_beetles_cost_a_stress_to_conjure():
    ranger = _make_ranger()
    fight = _fight(ranger, [_make_adversary()])

    assert tekaira_armored_beetles(ranger, fight) is True
    assert ranger.stress_marked == 1
    assert fight.token_count(ranger, BEETLES) == 1


def test_the_beetles_are_not_conjured_twice():
    ranger = _make_ranger()
    fight = _fight(ranger, [_make_adversary()])
    tekaira_armored_beetles(ranger, fight)

    assert tekaira_armored_beetles(ranger, fight) is False
    assert ranger.stress_marked == 1


def test_the_beetles_keep_the_last_stress_slot_free():
    ranger = _make_ranger(stress_max=2)
    ranger.mark_stress(1)
    fight = _fight(ranger, [_make_adversary()])

    assert tekaira_armored_beetles(ranger, fight) is False
    assert ranger.stress_marked == 1


def test_the_beetles_take_one_threshold_off_the_next_hit():
    ranger = _make_ranger(hope_marked=0)
    fight = _fight(ranger, [_make_adversary()])
    tekaira_armored_beetles(ranger, fight)

    assert beetles_take_the_hit(ranger, 12, 3, fight) == 2


def test_the_beetles_are_spent_unless_a_hope_keeps_them_up():
    ranger = _make_ranger(hope_marked=0)
    fight = _fight(ranger, [_make_adversary()])
    tekaira_armored_beetles(ranger, fight)

    beetles_take_the_hit(ranger, 12, 3, fight)

    assert fight.token_count(ranger, BEETLES) == 0
    assert beetles_take_the_hit(ranger, 12, 3, fight) == 3  # gone


def test_a_hope_keeps_the_beetles_up_for_the_next_hit():
    ranger = _make_ranger(hope_marked=4)
    fight = _fight(ranger, [_make_adversary()])
    tekaira_armored_beetles(ranger, fight)

    assert beetles_take_the_hit(ranger, 12, 3, fight) == 2
    assert ranger.hope_marked == 3
    assert fight.token_count(ranger, BEETLES) == 1


def test_the_beetles_are_not_spent_on_a_hit_armor_already_absorbed():
    ranger = _make_ranger(hope_marked=0)
    fight = _fight(ranger, [_make_adversary()])
    tekaira_armored_beetles(ranger, fight)

    assert beetles_take_the_hit(ranger, 4, 0, fight) == 0
    assert fight.token_count(ranger, BEETLES) == 1


def test_the_beetles_do_nothing_without_a_fight_to_read_state_from():
    assert beetles_take_the_hit(_make_ranger(), 12, 3, None) == 3


# --- Conjure Swarm: the fire flies -------------------------------------------


def test_fire_flies_declines_against_a_single_adversary():
    """A Hope for less than a bow shot; the card wants a crowd."""
    ranger = _make_ranger(hope_marked=3)
    adversary = _make_adversary()
    fight = _fight(ranger, [adversary])

    assert fire_flies(ranger, adversary, fight) is None
    assert ranger.hope_marked == 3


def test_fire_flies_declines_without_a_hope_to_spend():
    ranger = _make_ranger(hope_marked=0)
    crowd = [_make_adversary(f"Bandit {n}") for n in range(3)]
    fight = _fight(ranger, crowd)

    assert fire_flies(ranger, crowd[0], fight) is None


def test_fire_flies_hits_everything_it_reaches_and_costs_one_hope():
    """One roll and one damage roll, applied to each adversary it beat."""
    ranger = _make_ranger(hope_marked=3)
    crowd = [_make_adversary(f"Bandit {n}") for n in range(3)]
    fight = _fight(ranger, crowd)
    damage = DamageRollResult(
        dice_groups=[DiceGroup(count=2, sides=8)], die_results=[[4, 4]], modifier=3
    )

    with (
        patch("domain_cards.sage.roll_duality", return_value=HIT),
        patch("domain_cards.sage.roll_damage", return_value=damage) as mock_roll_damage,
    ):
        result = fire_flies(ranger, crowd[0], fight)

    assert ranger.hope_marked == 2
    assert mock_roll_damage.call_count == 1
    # Close range reaches 2 of 3, and 11 damage is Severe against a 10 threshold.
    assert sum(1 for adversary in crowd if adversary.hp_marked) == 2
    assert result.hp_marked == 6


def test_fire_flies_is_rolled_against_the_area_and_resolved_per_target():
    """The roll faces the whole area, not the one adversary the policy picked.

    This is the difference from Whirlwind, which rolls against a single target
    and reuses that roll: here every adversary in the area is checked against
    its own Difficulty, and the roll counts as a success if it beat any of them.
    """
    ranger = _make_ranger(hope_marked=3)
    easy = _make_adversary("Easy", difficulty=11)
    hard = _make_adversary("Hard", difficulty=20)
    spare = _make_adversary("Spare", difficulty=11)
    fight = _fight(ranger, [easy, hard, spare])
    damage = DamageRollResult(
        dice_groups=[DiceGroup(count=2, sides=8)], die_results=[[4, 4]], modifier=3
    )

    with (
        patch("domain_cards.sage.roll_duality", return_value=HIT) as mock_roll_duality,
        patch("domain_cards.sage.roll_damage", return_value=damage),
    ):
        result = fire_flies(ranger, hard, fight)

    # Rolled against the lowest Difficulty in the area, not the picked target's.
    assert mock_roll_duality.call_args.kwargs["difficulty"] == 11
    assert easy.hp_marked == 3  # 11 damage is Severe against a 10 threshold
    assert hard.hp_marked == 0  # a total of 17 didn't beat its Difficulty of 20
    assert result.hit is True


def test_natures_tongue_is_assessed_rather_than_left_missing():
    """The ruling is the user's; what matters here is that it's recorded."""
    from content import Status, assess

    assessment = assess("Nature's Tongue")

    assert assessment.status is Status.NO_COMBAT_EFFECT
    assert assessment.reason


def test_fire_flies_spends_no_hope_when_the_roll_beat_nobody():
    ranger = _make_ranger(hope_marked=3)
    crowd = [_make_adversary(f"Bandit {n}", difficulty=20) for n in range(3)]
    fight = _fight(ranger, crowd)

    with (
        patch("domain_cards.sage.roll_duality", return_value=MISS),
        patch("domain_cards.sage.roll_damage") as mock_roll_damage,
    ):
        result = fire_flies(ranger, crowd[0], fight)

    assert result.damage_roll is None
    assert ranger.hope_marked == 3
    mock_roll_damage.assert_not_called()
