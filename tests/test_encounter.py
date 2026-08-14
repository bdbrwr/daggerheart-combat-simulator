"""Group and Encounter as classes, built directly rather than read from a file.

Reading an encounter file - inheritance, overrides, and the ways a bad file
fails - is tests/test_encounters.py. These are about the objects a file produces,
so they construct them in Python, which is also how a sweep or a test would.

Stat blocks are looked up rather than imported: a definition lives in
adversaries/srd.json, so there is no module-level literal to reach for. The
lookups are made inside each test rather than once at import, because the
registry's cache can be dropped by `refresh()` in another file - holding an
object across that would make these pass or fail on test *order*.
"""

import pytest

from adversaries.registry import find_adversary
from encounters.encounter import CHARACTERS_DIR, Encounter, Group
from encounters.registry import find_experiment

BANDIT = "Jagged Knife Bandit"
SNIPER = "Jagged Knife Sniper"


def _encounter(**overrides) -> Encounter:
    """Three Bandits and a Sniper against the example PC."""
    defaults = dict(
        name="Test",
        party=[CHARACTERS_DIR / "example_character.json"],
        groups=[
            Group(find_adversary(BANDIT), count=3),
            Group(find_adversary(SNIPER), count=1),
        ],
    )
    defaults.update(overrides)
    return Encounter(**defaults)


def test_group_spawns_requested_count():
    group = Group(find_adversary(BANDIT), count=3)
    spawned = group.spawn()
    assert len(spawned) == 3
    assert all(adversary.name == BANDIT for adversary in spawned)


def test_group_accepts_an_adversary_by_name():
    group = Group(BANDIT, count=2)
    assert group.adversary is find_adversary(BANDIT)
    assert len(group.spawn()) == 2


def test_group_rejects_an_unknown_name_at_construction():
    with pytest.raises(KeyError):
        Group("Jagged Knife Trebuchet", count=1)


def test_group_spawns_independent_copies():
    first, second = Group(find_adversary(BANDIT), count=2).spawn()
    first.mark_hp(2)
    assert second.hp_marked == 0
    assert find_adversary(BANDIT).hp_marked == 0


def test_group_overrides_apply_to_every_copy():
    spawned = Group(SNIPER, count=2, hp_max=5, damage_modifier=4).spawn()
    assert [adversary.hp_max for adversary in spawned] == [5, 5]
    assert [adversary.damage_modifier for adversary in spawned] == [4, 4]


def test_group_overrides_leave_the_definition_alone():
    Group(SNIPER, count=1, hp_max=5).spawn()
    assert find_adversary(SNIPER).hp_max == 3


def test_group_rejects_an_unknown_stat():
    with pytest.raises(TypeError):
        Group(find_adversary(BANDIT), count=1, hp_maximum=9).spawn()


def test_a_spawned_copy_does_not_share_its_feature_list():
    """Features are a list, so a copy has to get its own - an adversary that
    gained one mid-fight must not write it back onto the definition."""
    spawned = Group(find_adversary(BANDIT), count=1).spawn()[0]
    spawned.features.append("Invented Mid-Fight")

    assert find_adversary(BANDIT).features == ["Climber", "From Above"]


def test_encounter_spawns_every_group_in_order():
    encounter = Encounter(
        name="Test",
        party=[],
        groups=[
            Group(find_adversary(BANDIT), count=2),
            Group(find_adversary(SNIPER), count=1),
        ],
    )
    names = [adversary.name for adversary in encounter.spawn_adversaries()]
    assert names == [BANDIT, BANDIT, SNIPER]


def test_encounter_adversary_count():
    assert _encounter().adversary_count == 4


def test_encounter_loads_the_party_from_json():
    party = _encounter().spawn_party()

    assert len(party) == 1
    assert party[0].name


def test_encounter_spawn_returns_both_sides():
    party, adversaries = _encounter().spawn()

    assert len(party) == 1
    assert len(adversaries) == 4


def test_encounter_party_paths_exist():
    for path in _encounter().party:
        assert path.is_file()
    assert CHARACTERS_DIR.is_dir()


def test_an_encounter_built_in_python_is_titled_by_its_own_name():
    """No experiment behind it, so there's nothing to prefix."""
    assert _encounter().title == "Test"


def test_the_shipped_example_tunes_a_stat_block_without_touching_the_definition():
    """The whole reason overrides live in the encounter file and not in adversaries/."""
    experiment = find_experiment("Roadside Ambush")
    toughened = next(
        variation
        for variation in experiment.variations
        if "toughened" in variation.name.lower()
    )

    sniper = next(
        adversary
        for adversary in toughened.spawn_adversaries()
        if adversary.name == SNIPER
    )

    assert sniper.hp_max == 5
    assert sniper.damage_modifier == 4
    assert find_adversary(SNIPER).hp_max == 3
    assert find_adversary(SNIPER).damage_modifier == 2
