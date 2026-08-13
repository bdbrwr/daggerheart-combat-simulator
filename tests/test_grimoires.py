"""Tests for the Grimoire mapping, rest state, and Aeloria's cards.

A Grimoire is one card holding several spells, so most of these are about the
mapping: a sheet names the book, and the book's spells are reached through it.
The rest-state tests matter because three of these abilities are once per rest,
and whether they're available is encounter setup rather than an assumption.
"""

import random

import pytest

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.policy import take_pc_turn
from combat.rest import Rest
from combat.state import FightState
from content import assess, take_action, use_free_abilities
from dice.damage import DiceGroup

WIZARD_LOADOUT = ["Book of Ava", "Book of Illiat", "Healing Hands"]


def _make_caster(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Aeloria",
        level=2,
        character_class="Wizard",
        subclass="School of Knowledge",
        ancestry="Fairy",
        community="Seaborne",
        traits={"agility": 0, "strength": 0, "finesse": 0, "instinct": 1, "presence": 1, "knowledge": 3},
        evasion=11,
        proficiency=2,
        spellcast_trait="knowledge",
        major_threshold=9,
        severe_threshold=18,
        hp_max=7,
        stress_max=6,
        hope_max=6,
        hope_marked=6,
        armor_max=4,
        primary_weapon="Greatstaff",
        secondary_weapon=None,
        armor_item="Devouring Robes",
        domain_cards_loadout=list(WIZARD_LOADOUT),
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
        difficulty=0,  # every spell lands
        major_threshold=100,
        severe_threshold=200,
        hp_max=500,
        stress_max=3,
        attack_modifier=0,
        damage_dice=[DiceGroup(count=1, sides=4)],
        damage_modifier=0,
    )
    defaults.update(overrides)
    return Adversary(**defaults)


def _state(party, adversaries, **overrides) -> FightState:
    return FightState(
        encounter_name="Test", party=party, adversaries=adversaries, **overrides
    )


# --- The mapping -------------------------------------------------------------


def test_a_book_is_reached_by_the_name_the_sheet_writes():
    """The sheet says "Book of Ava", never "Power Push"."""
    assert assess("Book of Ava").status.value == "modelled"
    assert assess("Book of Illiat").status.value == "modelled"


def test_a_books_spells_are_declared_against_the_book():
    gaps = " ".join(assess("Book of Ava").unmodelled)

    assert "Power Push" in gaps
    assert "Ice Spike" in gaps
    assert "Tava's Armor" in gaps


def test_a_spell_that_is_never_run_is_a_gap_not_a_dismissal():
    """Telepathy can't matter; Ice Spike can, and only loses to a simplification."""
    assert "Telepathy" in " ".join(assess("Book of Illiat").unmodelled)
    assert assess("Book of Ava").is_partial is True


def test_casting_a_book_reaches_one_of_its_spells():
    random.seed(2)
    caster = _make_caster(domain_cards_loadout=["Book of Ava"])
    target = _make_adversary()

    result = take_action(caster, target, _state([caster], [target]))

    assert result is not None
    assert target.hp_marked > 0  # Power Push or Ice Spike landed


def test_both_of_a_books_damage_spells_get_cast():
    """Which one is random - the order they were written in means nothing."""
    random.seed(11)
    seen = set()

    for _ in range(60):
        caster = _make_caster(domain_cards_loadout=["Book of Ava"])
        target = _make_adversary()
        result = take_action(caster, target, _state([caster], [target]))
        group = result.damage_roll.dice_groups[0]
        seen.add((group.count, group.sides))

    assert (2, 10) in seen  # Power Push
    assert (2, 6) in seen  # Ice Spike


def test_the_weapon_competes_with_a_card_that_always_accepts():
    """Power Push never declines, and must not make the Greatstaff unreachable."""
    random.seed(11)
    seen = set()

    for _ in range(60):
        caster = _make_caster(domain_cards_loadout=["Book of Ava"])
        target = _make_adversary()
        result = take_pc_turn(caster, _state([caster], [target]))
        if result is not None and result.damage_roll is not None:
            group = result.damage_roll.dice_groups[0]
            seen.add((group.count, group.sides))

    assert (3, 6) in seen  # the Greatstaff, rolling Proficiency + 1 and dropping one
    assert (2, 10) in seen  # Power Push


def test_a_caster_with_no_spellcast_trait_declines_rather_than_guessing():
    random.seed(2)
    caster = _make_caster(spellcast_trait="", domain_cards_loadout=["Book of Ava"])
    target = _make_adversary()

    assert take_action(caster, target, _state([caster], [target])) is None
    assert target.hp_marked == 0


# --- Rest state --------------------------------------------------------------


def test_a_rested_party_has_its_once_per_rest_abilities():
    caster = _make_caster()
    state = _state([caster], [], rest=Rest.LONG)

    assert state.can_use_once_per_rest(caster, "Arcane Barrage") is True


def test_a_party_that_did_not_rest_has_none_of_them():
    caster = _make_caster()
    state = _state([caster], [], rest=Rest.NONE)

    assert state.can_use_once_per_rest(caster, "Arcane Barrage") is False


def test_a_short_rest_does_not_refresh_a_long_rest_ability():
    caster = _make_caster()
    state = _state([caster], [], rest=Rest.SHORT)

    assert state.can_use_once_per_rest(caster, "Something", long=False) is True
    assert state.can_use_once_per_rest(caster, "Something", long=True) is False


def test_an_ability_can_only_be_spent_once():
    caster = _make_caster()
    state = _state([caster], [], rest=Rest.LONG)

    assert state.use_once_per_rest(caster, "Arcane Barrage") is True
    assert state.use_once_per_rest(caster, "Arcane Barrage") is False


def test_two_pcs_spend_their_own_uses():
    first, second = _make_caster(name="One"), _make_caster(name="Two")
    state = _state([first, second], [], rest=Rest.LONG)

    state.use_once_per_rest(first, "Arcane Barrage")

    assert state.can_use_once_per_rest(second, "Arcane Barrage") is True


# --- Arcane Barrage ----------------------------------------------------------


def test_arcane_barrage_deals_damage_without_any_roll():
    """No action roll means it can never pass the spotlight - that's the point."""
    random.seed(5)
    caster = _make_caster(domain_cards_loadout=["Book of Illiat"], hope_marked=6)
    target = _make_adversary()
    state = _state([caster], [target], rest=Rest.LONG)

    assert use_free_abilities(caster, state, limit=1) == ["Book of Illiat"]
    assert target.hp_marked > 0
    assert caster.hope_marked == 2  # spent down to the floor


def test_arcane_barrage_holds_its_hope_at_the_floor():
    caster = _make_caster(domain_cards_loadout=["Book of Illiat"], hope_marked=2)
    target = _make_adversary()
    state = _state([caster], [target], rest=Rest.LONG)

    assert use_free_abilities(caster, state, limit=1) == []
    assert target.hp_marked == 0


def test_arcane_barrage_is_unavailable_without_a_rest():
    caster = _make_caster(domain_cards_loadout=["Book of Illiat"], hope_marked=6)
    target = _make_adversary()
    state = _state([caster], [target], rest=Rest.NONE)

    assert use_free_abilities(caster, state, limit=1) == []
    assert caster.hope_marked == 6


# --- Slumber -----------------------------------------------------------------


def test_slumber_waits_until_the_gm_has_fear_worth_draining():
    random.seed(2)
    caster = _make_caster(domain_cards_loadout=["Book of Illiat"])
    target = _make_adversary()

    assert take_action(caster, target, _state([caster], [target], fear=0)) is None


def test_slumber_drains_a_fear_when_it_lands():
    random.seed(2)
    caster = _make_caster(domain_cards_loadout=["Book of Illiat"])
    target = _make_adversary()
    state = _state([caster], [target], fear=5)

    result = take_action(caster, target, state)

    assert result is not None
    assert result.damage_roll is None  # it deals no damage
    assert state.fear == 4


# --- Tava's Armor ------------------------------------------------------------


def test_tavas_armor_waits_until_somebody_has_run_out_of_slots():
    caster = _make_caster(domain_cards_loadout=["Book of Ava"])
    state = _state([caster], [], rest=Rest.LONG)

    assert use_free_abilities(caster, state, limit=1) == []
    assert caster.hope_marked == 6


def test_tavas_armor_wards_a_pc_with_nothing_left():
    caster = _make_caster(domain_cards_loadout=["Book of Ava"])
    caster.armor_marked = caster.armor_max
    state = _state([caster], [], rest=Rest.LONG)

    assert use_free_abilities(caster, state, limit=1) == ["Book of Ava"]
    assert caster.armor_max == 5
    assert caster.hope_marked == 5


def test_a_declined_ward_is_still_available_later():
    """Declining mustn't burn the once-per-fight use."""
    caster = _make_caster(domain_cards_loadout=["Book of Ava"])
    state = _state([caster], [], rest=Rest.LONG)

    use_free_abilities(caster, state, limit=1)  # declines: nobody is out of slots
    caster.armor_marked = caster.armor_max

    assert use_free_abilities(caster, state, limit=1) == ["Book of Ava"]


# --- Healing Hands -----------------------------------------------------------


def test_healing_hands_ignores_a_party_that_is_fine():
    random.seed(2)
    caster = _make_caster(domain_cards_loadout=["Healing Hands"])
    ally = _make_caster(name="Artorias")
    target = _make_adversary()

    assert take_action(caster, target, _state([caster, ally], [target])) is None


def test_healing_hands_clears_hp_on_the_worst_off_ally():
    random.seed(2)
    caster = _make_caster(domain_cards_loadout=["Healing Hands"])
    ally = _make_caster(name="Artorias", hp_max=7)
    ally.mark_hp(6)  # one unmarked HP left
    target = _make_adversary()
    state = _state([caster, ally], [target], rest=Rest.LONG)

    result = take_action(caster, target, state)

    assert result is not None
    assert ally.hp_marked < 6
    assert caster.stress_marked == 1


def test_healing_hands_will_not_heal_the_same_ally_twice():
    random.seed(2)
    caster = _make_caster(domain_cards_loadout=["Healing Hands"])
    ally = _make_caster(name="Artorias", hp_max=7)
    ally.mark_hp(6)
    target = _make_adversary()
    state = _state([caster, ally], [target], rest=Rest.LONG)

    take_action(caster, target, state)
    ally.mark_hp(6)

    assert take_action(caster, target, state) is None


def test_healing_hands_never_targets_the_caster():
    random.seed(2)
    caster = _make_caster(domain_cards_loadout=["Healing Hands"])
    caster.mark_hp(6)
    target = _make_adversary()

    assert take_action(caster, target, _state([caster], [target])) is None
