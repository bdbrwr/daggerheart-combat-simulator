"""Tests for the content registry's states and the coverage report.

The point of all of this is one distinction: content assessed as having no
combat effect must never look like content nobody has written yet. So most of
these check that the two stay apart, in the registry and in the printed block.

Declarations are made against throwaway names rather than real cards, so these
don't break every time a card is implemented. The real content is checked only
where the test is about the real content - and **an example of *unimplemented*
must always be a made-up name**, since any real one stops being an example the
moment somebody ports it.
"""

import pytest

from adversaries.registry import find_adversary
from characters.player_character import PlayerCharacter
from content.registry import (
    Status,
    assess,
    assess_all,
    guard,
    no_combat_effect,
    severity_response,
)
from simulation.coverage import CoverageDetail, format_coverage


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


# --- The states --------------------------------------------------------------


def test_anything_nobody_declared_is_unimplemented():
    assessment = assess("A Card Nobody Has Written")

    assert assessment.status is Status.UNIMPLEMENTED
    assert assessment.is_complete is False


def test_an_implemented_card_is_modelled():
    assert assess("Get Back Up").status is Status.MODELLED


def test_a_dismissed_card_is_not_the_same_as_a_missing_one():
    """The whole reason this module exists.

    The missing half is a throwaway name, per this module's own rule: it used to
    be Rune Ward, and broke the day Rune Ward was implemented. A real card can
    only ever illustrate "unimplemented" until somebody implements it.
    """
    dismissed = assess("Bare Bones")
    missing = assess("A Card Nobody Has Written")

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
    def _card(character, amount, hp_to_mark, fight=None):
        return hp_to_mark

    with pytest.raises(ValueError, match="can only"):
        no_combat_effect("Contradictory Card", "it cannot be both")


def test_two_hooks_on_one_name_merge_their_gaps():
    """Content can do more than one thing; that isn't a name collision."""

    @severity_response("Two Hook Card", unmodelled=["softening gap"])
    def _softens(character, amount, hp_to_mark, fight=None):
        return hp_to_mark

    @guard("Two Hook Card", unmodelled=["guarding gap"])
    def _guards_too(shielder, ally):
        return False

    assert assess("Two Hook Card").unmodelled == ("softening gap", "guarding gap")


def test_two_different_functions_cannot_claim_one_name():
    @severity_response("Contested Card")
    def _first(character, amount, hp_to_mark, fight=None):
        return hp_to_mark

    with pytest.raises(ValueError, match="Names have to be unique"):

        @severity_response("Contested Card")
        def _second(character, amount, hp_to_mark, fight=None):
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
    """Counts include equipped gear: the default sheet carries a Broadsword
    (Reliable, modelled) and Gambeson Armor (Flexible, ruled sheet-resolved)."""
    party = [_make_character(name="Kael", domain_cards_loadout=["Get Back Up"], **NOWHERE)]

    block = format_coverage(party, detail=CoverageDetail.FULL)

    assert "Kael" in block
    assert "2 modelled" in block  # Get Back Up, weapon:Reliable
    assert "2 no effect" in block  # Wildborne, armor:Flexible
    assert "3 unimplemented" in block  # the three invented names


def test_the_block_names_what_is_unimplemented():
    party = [_make_character(name="Kael", domain_cards_loadout=[], **NOWHERE)]

    block = format_coverage(party)

    assert "unimplemented" in block
    assert "Unwritten Class" in block
    assert "Unwritten Subclass" in block


def test_the_block_spells_out_a_partial_implementation():
    party = [_make_character(name="Kael", domain_cards_loadout=["I Am Your Shield"])]

    block = format_coverage(party, detail=CoverageDetail.FULL)

    assert "gap" in block
    assert "I Am Your Shield" in block


# --- How much of it prints ---------------------------------------------------


def _detailed(detail: CoverageDetail) -> str:
    party = [_make_character(name="Kael", domain_cards_loadout=["I Am Your Shield"], **NOWHERE)]
    return format_coverage(party, detail=detail)


def _tally_rows(block: str, name: str) -> list[str]:
    """Every tally line for `name` - never the detail lines underneath one.

    Matched on the counts themselves rather than on the name appearing in a
    line, because a reason is free to mention anything: `adversary:From Above`
    opens its reason with "Jagged Knife Bandit:", so counting the name across
    the whole block finds the row *and* the prose under it.
    """
    return [
        line
        for line in block.splitlines()
        if line.strip().startswith(name) and "unimplemented" in line
    ]


def _counts_for(block: str, name: str) -> str:
    """The one tally line for `name`.

    Assertions about which *counts* appear have to be made against this rather
    than the whole block, since the detail lines carry prose reasons and a
    reason is free to contain any word a count is named after.
    """
    return _tally_rows(block, name)[0]


def test_nothing_is_printed_at_all_when_coverage_is_turned_off():
    """Empty rather than a stub heading, so the caller can print what it gets."""
    assert _detailed(CoverageDetail.NONE) == ""


def test_the_default_leaves_out_the_modelled_half():
    """The block answers "what isn't running?"; modelled content answers the opposite."""
    block = _detailed(CoverageDetail.SUMMARY)

    assert "modelled" not in _counts_for(block, "Kael")
    assert "I Am Your Shield" not in block  # modelled, so neither it nor its gaps


def test_the_default_still_carries_every_state_that_means_something_is_missing():
    block = _detailed(CoverageDetail.SUMMARY)

    assert "no effect" in block
    assert "insignificant" in block
    assert "unimplemented" in block
    assert "Unwritten Class" in block  # named, not just counted


def test_the_full_block_adds_the_modelled_count_and_the_declared_gaps():
    block = _detailed(CoverageDetail.FULL)

    assert "modelled" in _counts_for(block, "Kael")
    assert "gap" in block
    assert "I Am Your Shield" in block


def test_a_gap_line_only_appears_for_content_that_declared_one():
    """A fully modelled feature has no gaps, so it prints no gap line even at FULL."""
    party = [_make_character(name="Kael", domain_cards_loadout=["Get Back Up"], **NOWHERE)]

    block = format_coverage(party, detail=CoverageDetail.FULL)

    assert "2 modelled" in block  # Get Back Up and weapon:Reliable, neither partial
    assert "gap" not in block


# --- Naming what was dismissed, and why --------------------------------------


def test_a_dismissal_is_named_and_carries_its_reason():
    """A count alone asks the reader to take the judgement on trust."""
    party = [_make_character(name="Kael", domain_cards_loadout=[], **NOWHERE)]

    block = format_coverage(party)

    assert "no effect" in block
    assert "Wildborne" in block  # named, not just counted
    assert "Ruled as having no effect" in block  # and why


def test_both_dismissals_are_named_not_only_the_insignificant_one():
    """They were reported differently once: insignificant named, no effect counted."""
    block = format_coverage(
        [_make_character(name="Kael", domain_cards_loadout=[], **NOWHERE)],
        [find_adversary("Jagged Knife Bandit")],
    )

    assert "armor:Flexible" in block  # a no-effect dismissal
    assert "adversary:From Above" in block  # an insignificant one


def test_only_the_opening_sentence_of_a_reason_is_printed():
    """Reasons run to a paragraph; the block would be unreadable carrying all of it."""
    party = [_make_character(name="Kael", domain_cards_loadout=[], **NOWHERE)]

    block = format_coverage(party)

    assert "+1 to Evasion." in block  # armor:Flexible's opening sentence
    assert "count it twice" not in block  # the rest of its argument


def test_an_unimplemented_name_carries_no_note():
    """There is nothing to say about it - that's what unimplemented means."""
    party = [_make_character(name="Kael", domain_cards_loadout=[], **NOWHERE)]

    block = format_coverage(party)
    unimplemented = next(
        line for line in block.splitlines() if "unimplemented   " in line
    )

    assert "Unwritten Class" in unimplemented
    assert " - " not in unimplemented


# --- Laying it out -----------------------------------------------------------


def test_a_long_name_keeps_a_gap_before_its_counts():
    """"Jagged Knife Bandit" is 19 characters and used to run into the tally."""
    block = format_coverage([], [find_adversary("Jagged Knife Bandit")])
    row = _counts_for(block, "Jagged Knife Bandit")

    assert "Jagged Knife Bandit " in row
    assert "Bandit0" not in row and "Bandit1" not in row


def _counts_start(line: str) -> int:
    """Where the tally begins - the first digit, none of these names having one."""
    return next(index for index, char in enumerate(line) if char.isdigit())


def test_both_sides_share_one_name_column():
    """Party and opposition line up with each other, not each within itself."""
    block = format_coverage(
        [_make_character(name="Kael", **NOWHERE)],
        [find_adversary("Jagged Knife Bandit")],
    )

    assert _counts_start(_counts_for(block, "Kael")) == _counts_start(
        _counts_for(block, "Jagged Knife Bandit")
    )


def test_the_block_warns_that_unimplemented_is_not_harmless():
    """Named against the invented sheet, so implementing real content can't silence it."""
    party = [_make_character(name="Kael", **NOWHERE)]

    assert "work not done" in format_coverage(party)


def test_a_fully_covered_party_carries_no_warning():
    """Nothing named at all means nothing missing."""
    bare = _make_character(
        name="Nobody", ancestry="Bare Bones", community="Bare Bones",
        character_class="Bare Bones", subclass="Bare Bones", domain_cards_loadout=[],
    )

    block = format_coverage([bare])

    assert "work not done" not in block
    # The four invented names, plus Gambeson Armor's Flexible.
    assert "5 no effect" in block


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


def test_a_fight_with_nobody_in_it_is_not_an_error():
    assert "nobody in the fight" in format_coverage([])


# --- The other side ----------------------------------------------------------
#
# An unimplemented domain card makes the party weaker than it is at a table, so
# the encounter reads as harder. An unimplemented adversary feature makes the
# opposition weaker, so it reads as easier. The two errors point in opposite
# directions and a reader who can only see one can't tell which way a number is
# wrong - which is why both sides are printed.


def test_the_block_covers_the_opposition_too():
    bandit = find_adversary("Jagged Knife Bandit")

    block = format_coverage([_make_character(name="Kael")], [bandit])

    assert "opposition" in block
    assert "Jagged Knife Bandit" in block


def test_a_dismissal_that_is_too_small_to_model_is_not_the_same_as_one_that_cannot_matter():
    """The fourth state. Both run no code; the claim recorded differs.

    Climber cannot reach a fight at all. From Above genuinely swaps in a bigger
    damage die and was measured as too small to bother with. Reporting them
    identically would hide which of those two things was decided.
    """
    climber = assess("adversary:Climber")
    from_above = assess("adversary:From Above")

    assert climber.status is Status.NO_COMBAT_EFFECT
    assert from_above.status is Status.INSIGNIFICANT_COMBAT_EFFECT
    assert climber.status is not from_above.status
    assert from_above.reason  # says how big the effect actually is


def test_both_kinds_of_dismissal_count_as_assessed():
    assert Status.NO_COMBAT_EFFECT.is_dismissed is True
    assert Status.INSIGNIFICANT_COMBAT_EFFECT.is_dismissed is True
    assert Status.UNIMPLEMENTED.is_dismissed is False
    assert Status.MODELLED.is_dismissed is False


def test_the_block_names_what_was_dismissed_as_insignificant():
    """A dismissal is only worth anything if a reader can go and check it."""
    block = format_coverage([], [find_adversary("Jagged Knife Bandit")])

    assert "insignificant" in block
    assert "adversary:From Above" in block


def test_an_assessed_adversary_raises_no_unimplemented_warning():
    """All three Jagged Knife passives are decided, so nothing is outstanding."""
    block = format_coverage([], [find_adversary("Jagged Knife Bandit")])

    assert "work not done" not in block


def test_copies_of_one_stat_block_are_reported_once():
    """Three bandits are three copies of one definition, not three findings."""
    bandit = find_adversary("Jagged Knife Bandit")

    block = format_coverage([], [bandit.spawn(), bandit.spawn(), bandit.spawn()])

    assert len(_tally_rows(block, "Jagged Knife Bandit")) == 1


def test_an_opposition_only_fight_still_reports():
    block = format_coverage([], [find_adversary("Jagged Knife Sniper")])

    assert "Jagged Knife Sniper" in block
    assert "(nobody)" in block


def test_a_party_only_fight_is_unchanged():
    """Callers that never had an opposition to pass still get their block."""
    assert "Kael" in format_coverage([_make_character(name="Kael")])


def test_named_features_are_what_applies_to_the_character():
    """Dispatch scans this: content the PC carries, which now includes their
    armor's features, because those apply to anything that happens to them."""
    character = _make_character(domain_cards_loadout=["Get Back Up", "I Am Your Shield"])

    assert character.named_features == [
        "Human",
        "Wanderborne",
        "Guardian",
        "Stalwart",
        "Get Back Up",
        "I Am Your Shield",
        "armor:Flexible",
    ]


def test_a_weapons_features_are_assessed_but_not_dispatched_holder_wide():
    """The distinction the two properties exist for. Reliable is the
    Broadsword's, so it must not join everything its holder does - but it is
    still part of how much of this character the simulator runs."""
    character = _make_character(domain_cards_loadout=[])

    assert "weapon:Reliable" not in character.named_features
    assert "weapon:Reliable" in character.assessed_features
    assert "armor:Flexible" in character.assessed_features


def test_an_uncatalogued_armor_reports_under_its_own_name():
    """Never silently absent: unknown gear shows as unimplemented rather than
    contributing nothing quietly."""
    character = _make_character(armor_item="Wyrmscale Halfplate")

    assert "Wyrmscale Halfplate" in character.named_features
    assert "Wyrmscale Halfplate" in format_coverage([character])
