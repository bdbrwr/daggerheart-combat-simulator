"""Damage types, resistance and immunity - the machinery and its first users.

Deterministic throughout: every case either builds a value and reads a derived
one back, or pushes a chosen number of damage into a combatant and reads the HP
it marked. Nothing here rolls a die.

Three claims are what this file exists to pin down, and each is a reading that
could plausibly have gone the other way:

* **Halving happens before thresholds.** That is what the SRD says outright, and
  it is why resistance changes how many HP a hit marks rather than only the
  figure printed. `test_a_resistance_changes_the_hp_marked_not_just_the_number`
  is the case that would fail if the order were ever flipped.
* **Resistances do not stack.** Several answers fold by taking the strongest
  single one. Multiplying would quarter a hit against two resistances.
* **Untyped damage matches nothing.** It is never resisted, and it satisfies no
  type restriction either - so a feature nobody has typed can only ever fail to
  trigger something, never trigger the wrong thing. This is the half most worth
  a test, because the failure it guards against is silent.
"""

import pytest

from adversaries.adversary import Adversary
from adversaries.catalogue import parse_damage_type
from characters.player_character import PlayerCharacter
from content.damage_types import (
    IMMUNE,
    RESISTED,
    UNREDUCED,
    DamageType,
    damage_type_named,
    reduced,
    strongest,
)
from content.registry import harden_damage, resistance_to, soften_damage
from dice.damage import DiceGroup
from features.adversaries import arcane_form
from features.subclasses import iron_will
from items.registry import find_weapon

PHYSICAL = DamageType.PHYSICAL
MAGIC = DamageType.MAGIC


def _elemental(**overrides) -> Adversary:
    """The Minor Chaos Elemental's numbers, since it is the only resistant one.

    Thresholds of 7 and 14 against a 7 HP track are what make the halving
    visible: a 13-point spell lands in a different band once it is halved.
    """
    defaults = dict(
        name="Minor Chaos Elemental",
        tier=1,
        difficulty=14,
        major_threshold=7,
        severe_threshold=14,
        hp_max=7,
        stress_max=3,
        attack_modifier=3,
        damage_dice=[DiceGroup(count=1, sides=12)],
        damage_modifier=6,
        damage_type="magic",
        range="Close",
        features=["Arcane Form"],
    )
    defaults.update(overrides)
    return Adversary(**defaults)


def _stalwart(**overrides) -> PlayerCharacter:
    """A Guardian carrying Iron Will and nothing else that answers damage.

    The class is deliberately left unwritten: registering the real "Guardian"
    would bring Unstoppable's own severity response into the same dispatch, and
    these cases are about one feature at a time.
    """
    defaults = dict(
        name="Test Stalwart",
        level=1,
        character_class="Unwritten Class",
        subclass="Stalwart",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 0, "strength": 2, "finesse": 0,
            "instinct": 0, "presence": 0, "knowledge": 0,
        },
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


# --- Naming a type -----------------------------------------------------------


def test_both_types_are_matched_by_the_name_the_book_prints():
    assert damage_type_named("physical") is PHYSICAL
    assert damage_type_named("magic") is MAGIC


def test_the_books_own_abbreviations_are_accepted():
    """A catalogue entry should read the way the stat block reads."""
    assert damage_type_named("phy") is PHYSICAL
    assert damage_type_named("mag") is MAGIC


def test_matching_folds_case_and_whitespace():
    assert damage_type_named("  Magic ") is MAGIC
    assert damage_type_named("PHY") is PHYSICAL


def test_a_type_that_is_already_a_type_passes_straight_through():
    assert damage_type_named(MAGIC) is MAGIC


def test_nothing_at_all_is_untyped_rather_than_an_error():
    """How untyped damage travels: a missing type can only fail to apply one."""
    assert damage_type_named(None) is None
    assert damage_type_named("") is None
    assert damage_type_named("   ") is None


def test_a_misspelled_type_raises_rather_than_resolving_as_untyped():
    """The one case that must be loud: a resistance that silently never fires
    is indistinguishable from a resistance nobody implemented."""
    with pytest.raises(ValueError):
        damage_type_named("magical")


def test_the_catalogue_normalises_an_abbreviation_to_the_full_spelling():
    assert parse_damage_type("mag", "srd.json", "Thing") == "magic"


def test_the_catalogue_reads_an_omitted_type_as_untyped():
    assert parse_damage_type(None, "srd.json", "Thing") == ""


def test_the_catalogue_names_the_file_and_the_entry_when_a_type_is_wrong():
    with pytest.raises(ValueError, match="Thing"):
        parse_damage_type("fire", "srd.json", "Thing")


# --- Folding several answers -------------------------------------------------


def test_nothing_answering_leaves_the_hit_unreduced():
    assert strongest([]) == UNREDUCED


def test_two_resistances_are_still_one_resistance():
    """The SRD in so many words: resistances to the same type do not stack.

    Multiplying would make the second one worth a quarter of the hit.
    """
    assert strongest([RESISTED, RESISTED]) == RESISTED


def test_an_immunity_beside_a_resistance_is_an_immunity():
    assert strongest([RESISTED, IMMUNE]) == IMMUNE


def test_a_reduction_rounds_down():
    assert reduced(13, RESISTED) == 6


def test_an_immunity_takes_the_whole_hit():
    assert reduced(13, IMMUNE) == 0


def test_an_unreduced_hit_is_left_exactly_as_it_came():
    assert reduced(13, UNREDUCED) == 13


# --- Arcane Form -------------------------------------------------------------


def test_arcane_form_halves_magic_damage():
    assert arcane_form(_elemental(), MAGIC) == RESISTED


def test_arcane_form_declines_on_physical_damage():
    assert arcane_form(_elemental(), PHYSICAL) is None


def test_arcane_form_declines_on_untyped_damage():
    """A resistance applies to a type that was stated, and none was."""
    assert arcane_form(_elemental(), None) is None


def test_the_dispatch_finds_the_resistance_by_the_name_on_the_stat_block():
    assert resistance_to(_elemental(), MAGIC) == RESISTED


def test_an_adversary_without_it_takes_everything_in_full():
    assert resistance_to(_elemental(features=[]), MAGIC) == UNREDUCED


def test_untyped_damage_is_never_reduced():
    assert resistance_to(_elemental(), None) == UNREDUCED


# --- Where the halving lands -------------------------------------------------


def test_a_resistance_changes_the_hp_marked_not_just_the_number():
    """The whole point of halving before thresholds.

    Thirteen magic damage against thresholds of 7 and 14 is Major and marks 2
    HP. Halved to 6 it falls below Major and marks 1. If the halving were
    applied after the bands were read, both would mark 2 and the feature would
    be worth nothing at all.
    """
    resistant = _elemental()
    unresistant = _elemental(features=[])

    assert resistant.take_damage(13, damage_type=MAGIC) == 1
    assert unresistant.take_damage(13, damage_type=MAGIC) == 2


def test_the_same_hit_dealt_as_physical_is_not_softened():
    assert _elemental().take_damage(13, damage_type=PHYSICAL) == 2


def test_an_untyped_hit_of_the_same_size_is_not_softened_either():
    assert _elemental().take_damage(13) == 2


# --- Which type a feature's damage carries -----------------------------------


def test_a_feature_that_states_no_type_deals_the_stat_blocks_own():
    """The ruling: an adversary's untyped feature damage falls back to its
    standard attack's type."""
    assert _elemental().type_of_damage() == "magic"


def test_a_feature_that_states_a_type_overrides_the_stat_block():
    """Death Quake is the case - a magic blast from a physical Construct."""
    assert _elemental().type_of_damage(PHYSICAL) is PHYSICAL


def test_a_weapon_types_the_damage_it_deals():
    """The PC side needed no authoring: the catalogue already carries it."""
    assert damage_type_named(find_weapon("Broadsword").damage_type) is PHYSICAL
    assert damage_type_named(find_weapon("Greatstaff").damage_type) is MAGIC


# --- Type restrictions on the severity hooks ---------------------------------


def test_iron_will_spends_a_slot_against_physical_damage():
    guardian = _stalwart()

    assert iron_will(guardian, 8, 2, None, PHYSICAL) == 1
    assert guardian.armor_marked == 1


def test_iron_will_keeps_the_slot_against_magic_damage():
    """"When you take physical damage" - the restriction the page prints."""
    guardian = _stalwart()

    assert iron_will(guardian, 8, 2, None, MAGIC) == 2
    assert guardian.armor_marked == 0


def test_iron_will_keeps_the_slot_against_untyped_damage():
    guardian = _stalwart()

    assert iron_will(guardian, 8, 2, None) == 2
    assert guardian.armor_marked == 0


def test_the_softening_dispatch_carries_the_type_to_the_feature():
    """The signature change is only worth anything if dispatch passes it on."""
    assert soften_damage(_stalwart(), 8, 2, None, PHYSICAL) == 1
    assert soften_damage(_stalwart(), 8, 2, None, MAGIC) == 2


def test_the_hardening_dispatch_carries_the_type_too():
    construct = Adversary(
        name="Construct",
        tier=1,
        difficulty=13,
        major_threshold=7,
        severe_threshold=15,
        hp_max=9,
        stress_max=4,
        attack_modifier=4,
        damage_type="physical",
        features=["Weak Structure"],
    )

    assert harden_damage(construct, 9, 1, None, PHYSICAL) == 2
    assert harden_damage(construct, 9, 1, None, MAGIC) == 1
    assert harden_damage(construct, 9, 1, None) == 1


def test_a_stalwart_taking_a_magic_hit_marks_the_full_severity():
    """End to end, through take_damage.

    Twelve damage is Severe against these thresholds and marks 3 HP. The free
    Armor Slot takes one off whatever the type - that is simulation policy and
    carries no type of its own - which leaves 2. Iron Will's *second* slot is
    physical-only, so it takes another off a sword and nothing off a spell.
    """
    physical = _stalwart()
    magic = _stalwart()

    assert physical.take_damage(12, damage_type=PHYSICAL) == 1
    assert physical.armor_marked == 2  # the free slot, and Iron Will's

    assert magic.take_damage(12, damage_type=MAGIC) == 2
    assert magic.armor_marked == 1  # the free slot only
