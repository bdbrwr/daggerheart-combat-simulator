"""Tests for looking an encounter up by name.

Same shape as the adversary and item registries, and checked the same way:
that discovery finds a definition nobody registered by hand, and that a
misspelled name fails with a suggestion rather than a bare miss.
"""

import pytest

from encounters import registry
from encounters.encounter import Encounter
from encounters.roadside_ambush import ROADSIDE_AMBUSH


def test_a_defined_encounter_is_found_by_its_own_name():
    assert registry.find_encounter("Roadside Ambush") is ROADSIDE_AMBUSH


def test_discovery_needs_no_hand_written_registration():
    """roadside_ambush.py registers nothing - defining the literal is enough."""
    catalogue = registry.all_encounters()

    assert "Roadside Ambush" in catalogue
    assert all(isinstance(found, Encounter) for found in catalogue.values())


def test_a_near_miss_is_told_what_it_probably_meant():
    with pytest.raises(KeyError) as raised:
        registry.find_encounter("Roadside Ambash")

    assert "Did you mean" in str(raised.value)
    assert "Roadside Ambush" in str(raised.value)


def test_a_name_like_nothing_defined_still_fails_cleanly():
    with pytest.raises(KeyError) as raised:
        registry.find_encounter("Tea With The Duke")

    assert "Tea With The Duke" in str(raised.value)


def test_the_catalogue_handed_out_is_a_copy():
    """Corrupting the returned dict mustn't empty the cache behind it."""
    registry.all_encounters().clear()

    assert "Roadside Ambush" in registry.all_encounters()


def test_a_refreshed_registry_finds_the_same_definitions_again():
    registry.refresh()

    assert registry.find_encounter("Roadside Ambush") is ROADSIDE_AMBUSH
