"""Reading encounter files, and looking an experiment up by name.

An encounter file is an experiment: one question, and the variations run side by
side to answer it. So these split three ways - that a file in the package is
found without anybody registering it, that variations inherit what the file says
and override what they state themselves, and that anything wrong in a file fails
loudly naming the file rather than defaulting quietly and simulating a fight
nobody wrote down.
"""

import json

import pytest

from combat.common import Side
from combat.rest import Rest
from encounters import registry
from encounters.encounter import CHARACTERS_DIR, Encounter, Experiment

VALID = {
    "name": "Test Fight",
    "party": ["example_character.json"],
    "variations": [
        {"name": "As printed", "groups": [{"adversary": "Jagged Knife Bandit", "count": 2}]}
    ],
}


def _write(path, **changes) -> str:
    """A valid encounter file with `changes` applied. Returns its path."""
    path.write_text(json.dumps({**VALID, **changes}))
    return path


def _one_variation(path, **changes) -> Encounter:
    """Read a file whose single variation has `changes` applied."""
    variation = {**VALID["variations"][0], **changes}
    return Experiment.from_json(_write(path, variations=[variation])).variations[0]


# --- Looking one up ----------------------------------------------------------


def test_an_experiment_is_found_by_its_own_name():
    found = registry.find_experiment("Roadside Ambush")

    assert isinstance(found, Experiment)
    assert found.name == "Roadside Ambush"
    assert len(found.variations) > 1  # it exists to be a comparison


def test_discovery_needs_no_hand_written_registration():
    """example_encounter.json registers nothing - the file being there is enough."""
    catalogue = registry.all_experiments()

    assert "Roadside Ambush" in catalogue
    assert all(isinstance(found, Experiment) for found in catalogue.values())


def test_a_near_miss_is_told_what_it_probably_meant():
    with pytest.raises(KeyError) as raised:
        registry.find_experiment("Roadside Ambash")

    assert "Did you mean" in str(raised.value)
    assert "Roadside Ambush" in str(raised.value)


def test_a_name_like_nothing_defined_still_fails_cleanly():
    with pytest.raises(KeyError) as raised:
        registry.find_experiment("Tea With The Duke")

    assert "Tea With The Duke" in str(raised.value)


def test_the_catalogue_handed_out_is_a_copy():
    """Corrupting the returned dict mustn't empty the cache behind it."""
    registry.all_experiments().clear()

    assert "Roadside Ambush" in registry.all_experiments()


def test_a_refreshed_registry_finds_the_same_definitions_again():
    registry.refresh()

    assert registry.find_experiment("Roadside Ambush").name == "Roadside Ambush"


# --- What a variation inherits -----------------------------------------------


def test_a_variation_inherits_the_files_party_and_settings(tmp_path):
    variation = _one_variation(tmp_path / "fight.json")

    assert variation.party == [CHARACTERS_DIR / "example_character.json"]
    assert variation.starting_fear == 0
    assert variation.starting_spotlight is Side.PCS
    assert variation.rest is Rest.LONG


def test_a_variation_overrides_what_it_states_itself(tmp_path):
    """"The same fight, walked into cold" is a variation, not a second file."""
    variation = _one_variation(
        tmp_path / "fight.json",
        starting_fear=3,
        starting_spotlight="gm",
        rest="none",
    )

    assert variation.starting_fear == 3
    assert variation.starting_spotlight is Side.GM
    assert variation.rest is Rest.NONE


def test_a_variation_is_titled_by_its_experiment_and_its_own_name(tmp_path):
    variation = _one_variation(tmp_path / "fight.json")

    assert variation.name == "As printed"
    assert variation.experiment == "Test Fight"
    assert variation.title == "Test Fight - As printed"


def test_the_files_notes_reach_every_variation(tmp_path):
    """Reasoning is printed with the numbers, so each report carries all of it."""
    experiment = Experiment.from_json(
        _write(
            tmp_path / "fight.json",
            notes="Why this question.",
            variations=[{**VALID["variations"][0], "notes": "Why this knob."}],
        )
    )

    assert experiment.notes == "Why this question."
    assert experiment.variations[0].notes == "Why this question. Why this knob."


def test_overrides_reach_the_spawned_adversaries(tmp_path):
    variation = _one_variation(
        tmp_path / "fight.json",
        groups=[
            {
                "adversary": "Jagged Knife Sniper",
                "count": 1,
                "overrides": {"hp_max": 5, "damage_modifier": 4},
            }
        ],
    )

    spawned = variation.spawn_adversaries()

    assert len(spawned) == 1
    assert spawned[0].hp_max == 5
    assert spawned[0].damage_modifier == 4


# --- Failing loudly ----------------------------------------------------------


def test_an_unknown_key_is_refused_rather_than_ignored(tmp_path):
    """A typo that quietly defaulted would simulate a different fight."""
    with pytest.raises(ValueError, match="startng_fear"):
        Experiment.from_json(_write(tmp_path / "fight.json", startng_fear=5))


def test_an_unknown_key_on_a_variation_is_refused_too(tmp_path):
    with pytest.raises(ValueError, match="groop"):
        Experiment.from_json(
            _write(tmp_path / "fight.json", variations=[{"name": "Odd", "groop": []}])
        )


def test_a_file_with_no_variations_has_nothing_to_run(tmp_path):
    with pytest.raises(ValueError, match="nothing to run"):
        Experiment.from_json(_write(tmp_path / "fight.json", variations=[]))


def test_two_variations_cannot_share_a_name(tmp_path):
    """A comparison table has nothing else to tell its rows apart."""
    twice = [VALID["variations"][0], {**VALID["variations"][0], "name": "as printed"}]

    with pytest.raises(ValueError, match="unique"):
        Experiment.from_json(_write(tmp_path / "fight.json", variations=twice))


def test_a_variation_with_no_party_anywhere_is_refused(tmp_path):
    data = {key: value for key, value in VALID.items() if key != "party"}
    (tmp_path / "fight.json").write_text(json.dumps(data))

    with pytest.raises(ValueError, match="no party"):
        Experiment.from_json(tmp_path / "fight.json")


def test_an_unknown_adversary_names_the_file_it_was_written_in(tmp_path):
    with pytest.raises(KeyError, match="fight.json"):
        _one_variation(tmp_path / "fight.json", groups=[{"adversary": "Jagged Knife Bandi"}])


def test_an_override_of_a_stat_adversaries_do_not_have_is_refused(tmp_path):
    """Caught while reading, not at spawn - by then a run is already going."""
    with pytest.raises(ValueError, match="evasion"):
        _one_variation(
            tmp_path / "fight.json",
            groups=[{"adversary": "Jagged Knife Bandit", "overrides": {"evasion": 12}}],
        )


def test_an_unparseable_rest_says_what_was_expected(tmp_path):
    with pytest.raises(ValueError, match="'long'"):
        Experiment.from_json(_write(tmp_path / "fight.json", rest="overnight"))


def test_a_missing_character_sheet_is_caught_while_reading(tmp_path):
    with pytest.raises(ValueError, match="no character sheet"):
        Experiment.from_json(_write(tmp_path / "fight.json", party=["nobody.json"]))


def test_a_chained_sequence_says_it_is_not_built_yet(tmp_path):
    """Better than "unknown key" for something that's coming."""
    with pytest.raises(ValueError, match="aren't implemented yet"):
        Experiment.from_json(
            _write(
                tmp_path / "fight.json",
                variations=[{"name": "Two waves", "fights": [{}, {}]}],
            )
        )


# --- One bad file doesn't take down the rest ---------------------------------


def test_a_broken_file_is_recorded_rather_than_crashing_the_others(tmp_path, monkeypatch):
    _write(tmp_path / "good.json")
    (tmp_path / "broken.json").write_text("{ this is not json")
    monkeypatch.setattr(registry, "_DEFINITIONS_DIR", tmp_path)
    registry.refresh()

    try:
        assert "Test Fight" in registry.all_experiments()
        assert "broken.json" in registry.load_errors()
    finally:
        registry.refresh()


def test_a_lookup_that_misses_mentions_the_files_that_would_not_load(tmp_path, monkeypatch):
    """Isolation mustn't become silence - a vanished run has to say why."""
    (tmp_path / "broken.json").write_text("{ this is not json")
    monkeypatch.setattr(registry, "_DEFINITIONS_DIR", tmp_path)
    registry.refresh()

    try:
        with pytest.raises(KeyError, match="broken.json"):
            registry.find_experiment("Anything At All")
    finally:
        registry.refresh()


def test_two_files_claiming_one_name_is_an_error(tmp_path, monkeypatch):
    _write(tmp_path / "first.json")
    _write(tmp_path / "second.json", name="test fight")  # same name, different case
    monkeypatch.setattr(registry, "_DEFINITIONS_DIR", tmp_path)
    registry.refresh()

    try:
        with pytest.raises(ValueError, match="unique"):
            registry.all_experiments()
    finally:
        registry.refresh()
