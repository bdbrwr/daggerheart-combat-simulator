from unittest.mock import patch

from characters.player_character import PlayerCharacter
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from items.weapons import broadsword_attack


class FakeTarget:
    """A minimal stand-in for the Target protocol - no Adversary class exists yet."""

    def __init__(self, difficulty: int = 10):
        self.difficulty = difficulty
        self.damage_taken: list[int] = []

    def take_damage(self, amount: int) -> int:
        self.damage_taken.append(amount)
        return amount


def _make_attacker(agility: int = 2, proficiency: int = 1) -> PlayerCharacter:
    return PlayerCharacter(
        name="Test PC",
        level=1,
        character_class="Guardian",
        subclass="Stalwart",
        ancestry="Human",
        community="Wanderborne",
        traits={"agility": agility, "strength": 0, "finesse": 0, "instinct": 0, "presence": 0, "knowledge": 0},
        evasion=9,
        proficiency=proficiency,
        major_threshold=6,
        severe_threshold=12,
        hp_max=7,
        stress_max=6,
        hope_max=6,
        armor_max=3,
        primary_weapon="Broadsword",
        secondary_weapon=None,
        armor_item="Gambeson Armor",
        domain_cards_loadout=[],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
    )


def _duality_result(*, hope: int, fear: int, modifier: int, difficulty: int) -> DualityRollResult:
    return DualityRollResult(
        hope_die_result=hope,
        fear_die_result=fear,
        modifier=modifier,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=difficulty,
    )


def test_broadsword_attack_hit_rolls_and_applies_damage():
    attacker = _make_attacker()
    target = FakeTarget(difficulty=10)
    hit_roll = _duality_result(hope=10, fear=5, modifier=5, difficulty=10)  # total 20, not a crit
    damage_roll = DamageRollResult(dice_groups=[DiceGroup(count=1, sides=8)], die_results=[[7]], modifier=0)

    with (
        patch("items.weapons.roll_duality", return_value=hit_roll) as mock_roll_duality,
        patch("items.weapons.roll_damage", return_value=damage_roll),
    ):
        result = broadsword_attack(attacker, target)

    assert result.hit is True
    assert result.damage_roll is damage_roll
    assert target.damage_taken == [7]
    # Reliable: +1 to attack rolls, on top of the Agility trait
    assert mock_roll_duality.call_args.kwargs["modifier"] == attacker.traits["agility"] + 1


def test_broadsword_attack_miss_deals_no_damage():
    attacker = _make_attacker()
    target = FakeTarget(difficulty=20)
    miss_roll = _duality_result(hope=2, fear=1, modifier=0, difficulty=20)  # total 3, well below difficulty

    with (
        patch("items.weapons.roll_duality", return_value=miss_roll),
        patch("items.weapons.roll_damage") as mock_roll_damage,
    ):
        result = broadsword_attack(attacker, target)

    assert result.hit is False
    assert result.damage_roll is None
    assert target.damage_taken == []
    mock_roll_damage.assert_not_called()
