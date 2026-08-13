"""Tests for the three-state content registry and the coverage report.

The point of all of this is one distinction: content assessed as having no
combat effect must never look like content nobody has written yet. So most of
these check that the two stay apart, in the registry and in the printed block.

Declarations are made against throwaway names rather than real cards, so these
don't break every time a card is implemented. The real content is checked only
where the test is about the real content.
"""

import pytest

from characters.player_character import PlayerCharacter
from content.registry import (
    Status,
    assess,
    assess_all,
    guard,
    no_combat_effect,
    severity_response,
)
from simulation.coverage import format_coverage


def _make_character(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=1,
        character_class="Guardian",
        subclass="Stalwart",
        ancestry="Human",
        community="Wanderborne",
        traits={"agility": 0, "strength": 2, "finesse": 0, "instinct": 1, "presence": 1, "knowledge": -1},
        evasion=9,
        proficiency=1,
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
    defaults.update(overrides)
    return PlayerCharacter(**defaults)


# --- The three states --------------------------------------------------------


def test_anything_nobody_declared_is_unimplemented():
    assessment = assess("A Card Nobody Has Written")

    assert assessment.status is Status.UNIMPLEMENTED
    assert assessment.is_complete is False


def test_an_implemented_card_is_modelled():
    assert assess("Get Back Up").status is Status.MODELLED


def test_a_dismissed_card_is_not_the_same_as_a_missing_one():
    """The whole reason this module exists."""
    dismissed = assess("Bare Bones")
    missing = assess("Rune Ward")

    assert dismissed.status is Status.NO_COMBAT_EFFECT
    assert missing.status is Status.UNIMPLEMENTED
    assert dismissed.reason  # says why
    assert not missing.reason


def test_a_dismissal_records_where_it_was_declared():
    assert assess("Bare Bones").source == "domain_cards.valor"


def test_declared_gaps_make_a_card_partly_modelled():
    shield = assess("I Am Your Shield")

    assert shield.status is Status.MODELLED
    assert shield.is_partial is True
    assert shield.is_complete is False
    assert any("Armor Slots" in gap for gap in shield.unmodelled)


def test_a_card_with_no_gaps_is_complete():
    assert assess("Get Back Up").is_complete is True


def test_assess_all_keeps_the_order_it_was_given():
    names = ["Get Back Up", "Nothing At All", "Bare Bones"]

    assert [a.name for a in assess_all(names)] == names


# --- Declaring ---------------------------------------------------------------


def test_the_same_name_cannot_be_both_modelled_and_dismissed():
    @severity_response("Contradictory Card")
    def _card(character, amount, hp_to_mark):
        return hp_to_mark

    with pytest.raises(ValueError, match="can only"):
        no_combat_effect("Contradictory Card", "it cannot be both")


def test_two_hooks_on_one_name_merge_their_gaps():
    """Content can do more than one thing; that isn't a name collision."""

    @severity_response("Two Hook Card", unmodelled=["softening gap"])
    def _softens(character, amount, hp_to_mark):
        return hp_to_mark

    @guard("Two Hook Card", unmodelled=["guarding gap"])
    def _guards_too(shielder, ally):
        return False

    assert assess("Two Hook Card").unmodelled == ("softening gap", "guarding gap")


def test_two_different_functions_cannot_claim_one_name():
    @severity_response("Contested Card")
    def _first(character, amount, hp_to_mark):
        return hp_to_mark

    with pytest.raises(ValueError, match="Names have to be unique"):

        @severity_response("Contested Card")
        def _second(character, amount, hp_to_mark):
            return hp_to_mark


# --- The report --------------------------------------------------------------


# Counts are pinned against made-up ancestries and classes rather than real
# ones. A real name's state changes the moment somebody implements it, and a
# test that has to be re-counted every time content lands is a test that will
# eventually just be edited until it passes.
NOWHERE = dict(
    ancestry="Unwritten Ancestry",
    community="Wildborne",  # really ruled out, and permanently so
    character_class="Unwritten Class",
    subclass="Unwritten Subclass",
)


def test_the_block_counts_each_state_for_each_character():
    party = [_make_character(name="Kael", domain_cards_loadout=["Get Back Up"], **NOWHERE)]

    block = format_coverage(party)

    assert "Kael" in block
    assert "1 modelled" in block  # Get Back Up
    assert "1 no effect" in block  # Wildborne, ruled out
    assert "3 unimplemented" in block  # the three invented names


def test_the_block_names_what_is_unimplemented():
    party = [_make_character(name="Kael", domain_cards_loadout=[], **NOWHERE)]

    block = format_coverage(party)

    assert "unimplemented" in block
    assert "Unwritten Class" in block
    assert "Unwritten Subclass" in block


def test_the_block_spells_out_a_partial_implementation():
    party = [_make_character(name="Kael", domain_cards_loadout=["I Am Your Shield"])]

    block = format_coverage(party)

    assert "gap" in block
    assert "I Am Your Shield" in block


def test_the_block_warns_that_unimplemented_is_not_harmless():
    party = [_make_character(name="Kael")]

    assert "work not done" in format_coverage(party)


def test_a_fully_covered_party_carries_no_warning():
    """Nothing named at all means nothing missing."""
    bare = _make_character(
        name="Nobody", ancestry="Bare Bones", community="Bare Bones",
        character_class="Bare Bones", subclass="Bare Bones", domain_cards_loadout=[],
    )

    block = format_coverage([bare])

    assert "work not done" not in block
    assert "4 no effect" in block


def test_the_block_repeats_what_a_sheet_asked_to_ignore():
    """Per-character exclusions sit next to the registry's verdicts."""
    party = [
        _make_character(
            name="Kael",
            not_modelled={"Wyrmscale Halfplate": "Homebrew; thresholds already resolved."},
        )
    ]

    block = format_coverage(party)

    assert "sheet says" in block
    assert "Wyrmscale Halfplate" in block


def test_a_party_of_nobody_is_not_an_error():
    assert "no party" in format_coverage([])


def test_every_named_feature_on_a_sheet_is_assessed():
    character = _make_character(domain_cards_loadout=["Get Back Up", "I Am Your Shield"])

    assert character.named_features == [
        "Human",
        "Wanderborne",
        "Guardian",
        "Stalwart",
        "Get Back Up",
        "I Am Your Shield",
    ]
