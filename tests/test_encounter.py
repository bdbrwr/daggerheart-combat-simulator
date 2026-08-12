import pytest

from adversaries.srd import JAGGED_KNIFE_BANDIT, JAGGED_KNIFE_SNIPER
from encounters.encounter import CHARACTERS_DIR, Encounter, Group
from encounters.roadside_ambush import ROADSIDE_AMBUSH


def test_group_spawns_requested_count():
    group = Group(JAGGED_KNIFE_BANDIT, count=3)
    spawned = group.spawn()
    assert len(spawned) == 3
    assert all(adversary.name == "Jagged Knife Bandit" for adversary in spawned)


def test_group_accepts_an_adversary_by_name():
    group = Group("Jagged Knife Bandit", count=2)
    assert group.adversary is JAGGED_KNIFE_BANDIT
    assert len(group.spawn()) == 2


def test_group_rejects_an_unknown_name_at_construction():
    with pytest.raises(KeyError):
        Group("Jagged Knife Trebuchet", count=1)


def test_group_spawns_independent_copies():
    first, second = Group(JAGGED_KNIFE_BANDIT, count=2).spawn()
    first.mark_hp(2)
    assert second.hp_marked == 0
    assert JAGGED_KNIFE_BANDIT.hp_marked == 0


def test_group_overrides_apply_to_every_copy():
    spawned = Group("Jagged Knife Sniper", count=2, hp_max=5, damage_modifier=4).spawn()
    assert [adversary.hp_max for adversary in spawned] == [5, 5]
    assert [adversary.damage_modifier for adversary in spawned] == [4, 4]


def test_group_overrides_leave_the_definition_alone():
    Group("Jagged Knife Sniper", count=1, hp_max=5).spawn()
    assert JAGGED_KNIFE_SNIPER.hp_max == 3


def test_group_rejects_an_unknown_stat():
    with pytest.raises(TypeError):
        Group(JAGGED_KNIFE_BANDIT, count=1, hp_maximum=9).spawn()


def test_encounter_spawns_every_group_in_order():
    encounter = Encounter(
        name="Test",
        party=[],
        groups=[Group(JAGGED_KNIFE_BANDIT, count=2), Group(JAGGED_KNIFE_SNIPER, count=1)],
    )
    names = [adversary.name for adversary in encounter.spawn_adversaries()]
    assert names == ["Jagged Knife Bandit", "Jagged Knife Bandit", "Jagged Knife Sniper"]


def test_encounter_adversary_count():
    assert ROADSIDE_AMBUSH.adversary_count == 4


def test_encounter_loads_the_party_from_json():
    party = ROADSIDE_AMBUSH.spawn_party()
    assert len(party) == 1
    assert party[0].name


def test_encounter_spawn_returns_both_sides():
    party, adversaries = ROADSIDE_AMBUSH.spawn()
    assert len(party) == 1
    assert len(adversaries) == 4


def test_encounter_party_paths_exist():
    for path in ROADSIDE_AMBUSH.party:
        assert path.is_file()
    assert CHARACTERS_DIR.is_dir()


def test_roadside_ambush_sniper_is_tuned_not_as_printed():
    _, adversaries = ROADSIDE_AMBUSH.spawn()
    sniper = next(a for a in adversaries if a.name == "Jagged Knife Sniper")
    assert sniper.hp_max == 5
    assert sniper.damage_modifier == 4
    assert JAGGED_KNIFE_SNIPER.hp_max == 3
    assert JAGGED_KNIFE_SNIPER.damage_modifier == 2
