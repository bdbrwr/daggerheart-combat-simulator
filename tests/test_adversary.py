from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import NEAR_DEATH_HP_UNMARKED
from dice.common import AdvantageState
from dice.d20 import D20RollResult
from dice.damage import DamageRollResult, DiceGroup


def _make_adversary(**overrides) -> Adversary:
    defaults = dict(
        name="Test Adversary",
        tier=1,
        difficulty=12,
        major_threshold=8,
        severe_threshold=14,
        hp_max=5,
        stress_max=3,
        attack_modifier=1,
        damage_dice=[DiceGroup(count=1, sides=8)],
        damage_modifier=1,
    )
    defaults.update(overrides)
    return Adversary(**defaults)


class FakeTarget:
    """A minimal stand-in for the adversaries.adversary.Target protocol."""

    def __init__(self, evasion: int = 10, hp_unmarked: int = 6, carrying=None):
        self.evasion = evasion
        self.hp_unmarked = hp_unmarked
        self.damage_taken: list[int] = []
        self.direct_damage_taken: list[int] = []
        self.types_taken: list = []

        # Part of the protocol so content that raises the target's own Evasion
        # can be looked for - an attack now asks what the target is carrying
        # before it settles the number to roll against. Empty by default, since
        # these cases are about the adversary's side of the swing.
        self.named_features: list[str] = list(carrying or [])

    @property
    def is_near_death(self) -> bool:
        """Part of the protocol so the party's forced-reroll content can ask."""
        return self.hp_unmarked <= NEAR_DEATH_HP_UNMARKED

    def take_damage(
        self, amount: int, fight=None, direct: bool = False, damage_type=None
    ) -> int:
        """`fight` is part of the protocol so a PC's damage responses can reach
        per-fight state; a fake has none, and records only the damage.

        `direct` says no Armor Slot may be marked against the hit. A fake has no
        armor either, so it changes nothing here - it's recorded separately so a
        test can still assert that an attack came through as direct.

        `damage_type` is the same shape: a fake has no resistances for it to
        answer, and it is recorded rather than dropped so a test can assert what
        type an attack came through as. It is **not** optional decoration -
        `Adversary.attack` types every hit off the stat block, so a stand-in
        without it raises on any attack that lands.
        """
        self.damage_taken.append(amount)
        if direct:
            self.direct_damage_taken.append(amount)
        self.types_taken.append(damage_type)
        return amount


def _d20_result(*, die: int, modifier: int, evasion: int) -> D20RollResult:
    return D20RollResult(
        die_results=[die],
        modifier=modifier,
        advantage_state=AdvantageState.NONE,
        evasion=evasion,
    )


def test_a_feature_can_make_the_standard_attack_direct():
    """Bone Breaker reaches the attack without `attack` knowing its name.

    Also the reason FakeTarget records direct hits separately: without this,
    `direct` would be accepted and dropped, and a broken dispatch would look
    exactly like a working one.
    """
    ogre = _make_adversary(features=["Bone Breaker"])
    target = FakeTarget(evasion=10)
    damage_roll = DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=8)], die_results=[[5]], modifier=1
    )

    with (
        patch("adversaries.adversary.roll_d20",
              return_value=_d20_result(die=15, modifier=1, evasion=10)),
        patch("adversaries.adversary.roll_damage", return_value=damage_roll),
    ):
        ogre.attack(target)

    assert target.direct_damage_taken == [6]


def test_an_ordinary_attack_is_not_direct():
    adversary = _make_adversary()
    target = FakeTarget(evasion=10)
    damage_roll = DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=8)], die_results=[[5]], modifier=1
    )

    with (
        patch("adversaries.adversary.roll_d20",
              return_value=_d20_result(die=15, modifier=1, evasion=10)),
        patch("adversaries.adversary.roll_damage", return_value=damage_roll),
    ):
        adversary.attack(target)

    assert target.damage_taken == [6]
    assert target.direct_damage_taken == []


def test_mark_hp_clamps_to_max():
    adversary = _make_adversary(hp_max=5)
    adversary.mark_hp(10)
    assert adversary.hp_marked == 5


def test_clear_hp_clamps_to_zero():
    adversary = _make_adversary(hp_max=5)
    adversary.hp_marked = 2
    adversary.clear_hp(10)
    assert adversary.hp_marked == 0


def test_mark_stress_clamps_to_max():
    adversary = _make_adversary(stress_max=3)
    adversary.mark_stress(10)
    assert adversary.stress_marked == 3


def test_clear_stress_clamps_to_zero():
    adversary = _make_adversary(stress_max=3)
    adversary.stress_marked = 1
    adversary.clear_stress(10)
    assert adversary.stress_marked == 0


def test_take_damage_marks_nothing_below_zero_or_zero():
    adversary = _make_adversary(major_threshold=8, severe_threshold=14)
    assert adversary.take_damage(0) == 0
    assert adversary.take_damage(-5) == 0
    assert adversary.hp_marked == 0


def test_take_damage_below_major_marks_one():
    adversary = _make_adversary(major_threshold=8, severe_threshold=14)
    assert adversary.take_damage(7) == 1
    assert adversary.hp_marked == 1


def test_take_damage_at_major_marks_two():
    adversary = _make_adversary(major_threshold=8, severe_threshold=14)
    assert adversary.take_damage(8) == 2
    assert adversary.hp_marked == 2


def test_take_damage_at_severe_marks_three():
    adversary = _make_adversary(major_threshold=8, severe_threshold=14)
    assert adversary.take_damage(14) == 3
    assert adversary.hp_marked == 3


def test_take_damage_well_above_severe_still_marks_three():
    adversary = _make_adversary(major_threshold=8, severe_threshold=14)
    assert adversary.take_damage(100) == 3
    assert adversary.hp_marked == 3


def test_spawn_copies_stats():
    definition = _make_adversary(hp_max=5, attack_modifier=1)
    spawned = definition.spawn()
    assert spawned.name == definition.name
    assert spawned.hp_max == 5
    assert spawned.attack_modifier == 1


def test_spawn_applies_overrides_without_touching_the_definition():
    definition = _make_adversary(hp_max=5, damage_modifier=1)
    spawned = definition.spawn(hp_max=9, damage_modifier=4)
    assert spawned.hp_max == 9
    assert spawned.damage_modifier == 4
    assert definition.hp_max == 5
    assert definition.damage_modifier == 1


def test_spawn_gives_each_copy_its_own_marked_state():
    definition = _make_adversary(hp_max=5)
    first, second = definition.spawn(), definition.spawn()
    first.mark_hp(3)
    assert first.hp_marked == 3
    assert second.hp_marked == 0
    assert definition.hp_marked == 0


def test_spawn_resets_marked_state_from_a_used_copy():
    used = _make_adversary(hp_max=5)
    used.mark_hp(4)
    used.mark_stress(2)
    fresh = used.spawn()
    assert fresh.hp_marked == 0
    assert fresh.stress_marked == 0


def test_spawn_does_not_share_the_damage_dice_list():
    definition = _make_adversary()
    spawned = definition.spawn()
    spawned.damage_dice.append(DiceGroup(count=1, sides=6))
    assert len(definition.damage_dice) == 1


def test_attack_hit_rolls_and_applies_damage():
    adversary = _make_adversary(attack_modifier=1, damage_modifier=1)
    target = FakeTarget(evasion=10)
    hit_roll = _d20_result(die=15, modifier=1, evasion=10)  # total 16, not a crit
    damage_roll = DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=8)], die_results=[[5]], modifier=1
    )

    with (
        patch("adversaries.adversary.roll_d20", return_value=hit_roll) as mock_roll_d20,
        patch("adversaries.adversary.roll_damage", return_value=damage_roll) as mock_roll_damage,
    ):
        result = adversary.attack(target)

    assert result.hit is True
    assert result.damage_roll is damage_roll
    assert target.damage_taken == [6]  # 5 rolled + 1 flat modifier
    assert mock_roll_d20.call_args.kwargs["modifier"] == adversary.attack_modifier
    assert mock_roll_d20.call_args.kwargs["evasion"] == target.evasion
    assert mock_roll_damage.call_args.kwargs["dice_groups"] == adversary.damage_dice
    assert mock_roll_damage.call_args.kwargs["modifier"] == adversary.damage_modifier


def test_attack_miss_deals_no_damage():
    adversary = _make_adversary()
    target = FakeTarget(evasion=18)
    miss_roll = _d20_result(die=5, modifier=1, evasion=18)  # total 6, well below evasion

    with (
        patch("adversaries.adversary.roll_d20", return_value=miss_roll),
        patch("adversaries.adversary.roll_damage") as mock_roll_damage,
    ):
        result = adversary.attack(target)

    assert result.hit is False
    assert result.damage_roll is None
    assert target.damage_taken == []
    mock_roll_damage.assert_not_called()


def test_attack_passes_critical_through_to_the_damage_roll():
    adversary = _make_adversary()
    target = FakeTarget(evasion=10)
    crit_roll = _d20_result(die=20, modifier=1, evasion=10)

    with (
        patch("adversaries.adversary.roll_d20", return_value=crit_roll),
        patch("adversaries.adversary.roll_damage") as mock_roll_damage,
    ):
        adversary.attack(target)

    assert mock_roll_damage.call_args.kwargs["is_critical"] is True


def test_attack_uses_tuned_stats_from_spawn():
    tuned = _make_adversary(attack_modifier=1).spawn(attack_modifier=7, damage_modifier=4)
    target = FakeTarget(evasion=10)
    hit_roll = _d20_result(die=15, modifier=7, evasion=10)

    with (
        patch("adversaries.adversary.roll_d20", return_value=hit_roll) as mock_roll_d20,
        patch("adversaries.adversary.roll_damage") as mock_roll_damage,
    ):
        tuned.attack(target)

    assert mock_roll_d20.call_args.kwargs["modifier"] == 7
    assert mock_roll_damage.call_args.kwargs["modifier"] == 4
