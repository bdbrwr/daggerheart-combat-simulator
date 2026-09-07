"""Tests for the Codex domain cards that are not Grimoires.

Codex is mostly books, and the books have a file of their own
(`test_grimoires.py`) because one card carries three spells and the spells are
what a fight sees. What is left here is the domain's one non-book card,
Codex-Touched, plus the declarations - which matter more in this domain than in
any other, since **a Grimoire with no spell registered would report the card as
unimplemented**. Declaring the book as well as its spells is what keeps a
deliberate dismissal from looking like work nobody has done.

Determinism comes from a target with a Difficulty of 0, so no case turns on
whether a cast landed.
"""

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.state import FightState
from content import Status, assess, total_spellcast_bonus
from dice.damage import DiceGroup
from domain_cards.codex import CODEX_TOUCHED, CODEX_TOUCHED_STRESS_CEILING

BOOK_OF_HOMET = "Book of Homet"
BOOK_OF_VYOLA = "Book of Vyola"
SAFE_HAVEN = "Safe Haven"


def _make_level_7_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=7,
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 2,
            "strength": 1,
            "finesse": 3,
            "instinct": 0,
            "presence": 1,
            "knowledge": 2,
        },
        evasion=12,
        proficiency=3,
        spellcast_trait="knowledge",
        major_threshold=10,
        severe_threshold=20,
        hp_max=8,
        stress_max=6,
        hope_max=6,
        hope_marked=6,
        armor_max=0,  # off unless a case is about armor
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


def _make_adversary(**overrides) -> Adversary:
    defaults = dict(
        name="Dummy",
        tier=1,
        difficulty=0,
        major_threshold=10,
        severe_threshold=20,
        hp_max=12,
        stress_max=3,
        attack_modifier=0,
        damage_dice=[DiceGroup(count=1, sides=4)],
        damage_modifier=0,
        damage_type="physical",
    )
    defaults.update(overrides)
    return Adversary(**defaults)


def _state(party, adversaries, **overrides) -> FightState:
    return FightState(
        encounter_name="Test", party=party, adversaries=adversaries, **overrides
    )


# --- Codex-Touched -----------------------------------------------------------


def test_the_stress_buys_the_casters_whole_proficiency():
    caster = _make_level_7_pc(domain_cards_loadout=[CODEX_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    assert total_spellcast_bonus(caster, target, fight) == 3
    assert caster.stress_marked == 1


def test_the_ceiling_stops_it_rather_than_the_last_slot_rule():
    """Three marked of six - the shared rule would still allow this one."""
    caster = _make_level_7_pc(domain_cards_loadout=[CODEX_TOUCHED])
    caster.mark_stress(CODEX_TOUCHED_STRESS_CEILING)
    target = _make_adversary()
    fight = _state([caster], [target])

    assert caster.will_spend_stress(1) is True  # the standing rule says yes
    assert total_spellcast_bonus(caster, target, fight) == 0  # the ceiling says no
    assert caster.stress_marked == CODEX_TOUCHED_STRESS_CEILING


def test_three_casts_are_bought_and_then_no_more():
    caster = _make_level_7_pc(domain_cards_loadout=[CODEX_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    bought = [total_spellcast_bonus(caster, target, fight) for _ in range(5)]

    assert bought == [3, 3, 3, 0, 0]


# --- The books that reach no fight -------------------------------------------


def test_the_book_of_homet_is_declared_with_a_reason():
    assert assess(BOOK_OF_HOMET).status.value == "no combat effect"
    assert assess(BOOK_OF_HOMET).reason


def test_the_book_is_declared_as_well_as_its_spells():
    """A Grimoire with no spell registered would report as unimplemented."""
    for name in (BOOK_OF_HOMET, "Pass Through", "Plane Gate"):
        assert assess(name).status.value == "no combat effect"


def test_the_book_of_vyola_is_declared_as_well_as_its_spells():
    for name in (BOOK_OF_VYOLA, "Memory Delve", "Shared Clarity"):
        assert assess(name).status is Status.NO_COMBAT_EFFECT


def test_safe_haven_waits_for_sequenced_encounters():
    """Not a dismissal: it is the to-do list for sequenced encounters."""
    assert assess(SAFE_HAVEN).status is Status.OUT_OF_COMBAT
