from adversaries.adversary import Adversary


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
    )
    defaults.update(overrides)
    return Adversary(**defaults)


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
