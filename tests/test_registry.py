import pytest

from adversaries.adversary import Adversary
from adversaries.registry import all_adversaries, find_adversary, refresh
from adversaries.srd import JAGGED_KNIFE_BANDIT


def test_find_adversary_returns_the_definition_itself():
    assert find_adversary("Jagged Knife Bandit") is JAGGED_KNIFE_BANDIT


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


def test_a_re_export_does_not_produce_a_duplicate_entry():
    """The same definition seen in two modules collapses to one entry."""
    catalogue = all_adversaries()
    names = [name for name in catalogue if name == "Jagged Knife Bandit"]
    assert len(names) == 1


def test_refresh_rebuilds_the_catalogue():
    before = find_adversary("Jagged Knife Bandit")
    refresh()
    assert find_adversary("Jagged Knife Bandit") is before
