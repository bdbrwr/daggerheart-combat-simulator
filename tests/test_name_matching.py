"""Names on a character sheet are matched regardless of capitalisation.

A sheet is typed by a person, and "I am your shield" is what people write. Before
this, that missed: the card reported as *unimplemented* and silently never fired,
which is the one failure this project can least afford - it looks identical to a
card nobody has written, and the win rate quietly belongs to a weaker party.

So both registries key on a canonical form. These pin that, and pin the limits of
it: punctuation and spelling are still matched exactly, because a wrong match
would be worse than a miss.
"""

import pytest

from characters.player_character import PlayerCharacter
from content import Status, assess, find_guard, find_severity_response, find_shielder
from content.names import canonical
from items.registry import all_weapons, find_consumable, find_weapon


def _make_character(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=2,
        # Invented, so only the loadout under test can fire.
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 0, "strength": 2, "finesse": 0,
            "instinct": 1, "presence": 1, "knowledge": 0,
        },
        evasion=9,
        proficiency=2,
        major_threshold=6,
        severe_threshold=12,
        hp_max=7,
        stress_max=6,
        hope_max=6,
        armor_max=0,
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


# --- The canonical form ------------------------------------------------------


def test_case_and_surrounding_whitespace_are_ignored():
    assert canonical("I Am Your Shield") == canonical("i am your shield")
    assert canonical("  Whirlwind ") == canonical("Whirlwind")
    assert canonical("Book  of Ava") == canonical("Book of Ava")


def test_punctuation_and_spelling_are_still_matched_exactly():
    """A miss is visible in the coverage report; a wrong match isn't."""
    assert canonical("Natures Tongue") != canonical("Nature's Tongue")
    assert canonical("Whirlwinds") != canonical("Whirlwind")


# --- Content -----------------------------------------------------------------


def test_a_card_is_found_however_the_sheet_capitalised_it():
    assert find_guard("i am your shield") is find_guard("I Am Your Shield")
    assert find_severity_response("GET BACK UP") is find_severity_response("Get Back Up")


def test_a_miscapitalised_card_is_assessed_as_modelled_not_missing():
    """The bug this exists to stop: implemented content reported as a gap."""
    assert assess("i am your shield").status is Status.MODELLED
    assert assess("conjure swarm").status is Status.MODELLED


def test_an_assessment_keeps_the_spelling_it_was_declared_with():
    assert assess("i am your shield").name == "I Am Your Shield"


def test_an_unimplemented_name_is_reported_as_the_sheet_wrote_it():
    """Nothing to correct it to, so the report shows what to go and look for.

    A made-up name rather than a real card. This used to say "Rune WARD" and
    broke the day Rune Ward was implemented - a real card illustrates
    *unimplemented* only until somebody gets to it.
    """
    unknown = assess("No Such CARD")

    assert unknown.status is Status.UNIMPLEMENTED
    assert unknown.name == "No Such CARD"


def test_dispatch_reaches_a_card_the_sheet_miscapitalised():
    """End to end: the loadout string is what a real sheet had in it."""
    shielder = _make_character(name="Kael", domain_cards_loadout=["i am your shield"])
    hurt = _make_character(name="Ally", hp_max=7)
    hurt.mark_hp(5)

    interception = find_shielder(hurt, [shielder, hurt])

    assert interception is not None
    assert interception.shielder is shielder
    assert shielder.stress_marked == 1


# --- Items -------------------------------------------------------------------


def test_gear_is_found_however_the_sheet_capitalised_it():
    assert find_weapon("greatsword") is find_weapon("Greatsword")
    assert find_consumable("MINOR HEALING POTION") is find_consumable("Minor Healing Potion")


def test_the_catalogue_keeps_the_names_items_were_registered_under():
    assert "Broadsword" in all_weapons()


def test_an_unknown_item_still_fails_loudly_and_suggests_the_real_spelling():
    """Gear that doesn't resolve means a PC who can't attack - worth raising over."""
    with pytest.raises(KeyError, match="Greatsword"):
        find_weapon("greatswrod")


# --- Stat blocks and encounters ----------------------------------------------


def test_an_adversary_is_found_however_an_encounter_capitalised_it():
    from adversaries.registry import find_adversary

    assert find_adversary("jagged knife bandit") is find_adversary("Jagged Knife Bandit")


def test_an_experiment_is_found_however_it_was_typed_at_the_command_line():
    from encounters.registry import all_experiments, find_experiment

    defined = next(iter(all_experiments()), None)
    assert defined is not None, "no experiments are defined to look up"
    assert find_experiment(defined.upper()) is find_experiment(defined)


# --- Traits ------------------------------------------------------------------


def test_trait_keys_are_lowercased_when_a_sheet_is_loaded(tmp_path):
    """A capitalised trait key would make every Spellcast Roll decline in silence."""
    import json

    sheet = {
        "name": "Test", "level": 2, "class": "Wizard", "subclass": "School of War",
        "ancestry": "Faerie", "community": "Seaborne", "spellcast_trait": "Knowledge",
        "traits": {"Agility": 0, "Strength": 0, "Finesse": 0,
                   "Instinct": 1, "Presence": 1, "Knowledge": 3},
        "evasion": 11, "proficiency": 2,
        "thresholds": {"major": 9, "severe": 18},
        "hp": {"max": 7, "marked": 0},
        "stress": {"max": 6, "marked": 0},
        "hope": {"max": 6, "marked": 0},
        "armor": {"max": 4, "marked": 0},
        "equipment": {"primary_weapon": "Greatstaff", "secondary_weapon": None,
                      "armor": "Devouring Robes"},
        "domain_cards": {"loadout": [], "vault": []},
        "experiences": [], "consumables": [],
    }
    written = tmp_path / "capitalised.json"
    written.write_text(json.dumps(sheet))

    loaded = PlayerCharacter.from_json(written)

    assert loaded.spellcast_trait in loaded.traits
    assert loaded.traits["knowledge"] == 3
