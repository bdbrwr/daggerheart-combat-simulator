import pytest

from adversaries.adversary import Adversary
from adversaries.registry import (
    all_adversaries,
    find_adversary,
    load_errors,
    refresh,
)


def test_find_adversary_returns_the_shared_definition():
    """The same object every time, so a Group can spawn copies off it."""
    assert find_adversary("Jagged Knife Bandit") is find_adversary("jagged knife bandit")


def test_find_adversary_works_without_knowing_the_module():
    """The point of the registry - no import path anywhere in this test."""
    found = find_adversary("Jagged Knife Sniper")
    assert found.name == "Jagged Knife Sniper"
    assert found.difficulty == 13


def test_find_adversary_raises_on_an_unknown_name():
    with pytest.raises(KeyError):
        find_adversary("Definitely Not An Adversary")


def test_find_adversary_suggests_close_matches():
    with pytest.raises(KeyError) as raised:
        find_adversary("Jagged Knife Bandits")
    assert "Jagged Knife Bandit" in str(raised.value)


def test_all_adversaries_includes_every_defined_adversary():
    catalogue = all_adversaries()
    assert "Jagged Knife Bandit" in catalogue
    assert "Jagged Knife Sniper" in catalogue
    assert all(isinstance(value, Adversary) for value in catalogue.values())


def test_all_adversaries_returns_a_copy():
    all_adversaries().clear()
    assert "Jagged Knife Bandit" in all_adversaries()


def test_a_stat_block_is_read_off_the_catalogue():
    """The numbers come from srd.json, not from a Python literal."""
    bandit = find_adversary("Jagged Knife Bandit")

    assert bandit.hp_max == 5
    assert bandit.stress_max == 3
    assert bandit.damage_modifier == 1
    assert [(g.count, g.sides) for g in bandit.damage_dice] == [(1, 8)]
    assert bandit.publication == "Daggerheart SRD"


def test_a_stat_blocks_features_are_namespaced_for_the_registry():
    """Feature names are qualified, so an adversary's Heavy can't collide with a
    weapon's - and so the coverage block says which one is missing."""
    bandit = find_adversary("Jagged Knife Bandit")

    assert bandit.features == ["Climber", "From Above"]
    assert bandit.named_features == ["adversary:Climber", "adversary:From Above"]


def test_refresh_rebuilds_the_catalogue():
    """Re-read from disk, so the stats match even though the object is new."""
    before = find_adversary("Jagged Knife Bandit")
    refresh()
    after = find_adversary("Jagged Knife Bandit")

    assert after is not before  # genuinely re-read, not handed back from cache
    assert after == before


def test_the_catalogues_all_load():
    """Isolation mustn't become silence - a stat block that vanished says why."""
    assert load_errors() == {}
