"""Tests for the Grimoire mapping, rest state, and the Codex books.

A Grimoire is one card holding several spells, so most of these are about the
mapping: a sheet names the book, and the book's spells are reached through it.
The rest-state tests matter because three of these abilities are once per rest,
and whether they're available is encounter setup rather than an assumption.

The later books add two shapes the earlier two didn't have: a spell rolled
against a whole area at once (Wild Flame), and a spell one PC hangs on another
that resolves when *they* attack (Parallela). The second is the reason
`ally_on_hit` exists, so the cases here reach it through dispatch rather than
calling the rider directly wherever they can.
"""

import random
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.policy import take_pc_turn
from combat.rest import Rest
from combat.results import AttackResult
from combat.state import FightState
from content import (
    apply_ally_on_hit,
    assess,
    remake_action_roll,
    take_action,
    use_free_abilities,
)
from content.conditions import VULNERABLE
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from domain_cards.codex import PARALLELA, parallela, parallela_doubles, wild_flame
from domain_cards.sage import FAMILIAR, familiar_flanks
from domain_cards.splendor import bolt_beacon

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


# --- Book of Tyfar: Wild Flame -----------------------------------------------


@contextmanager
def _bunched():
    """Every band at its best reach, so a case is about the card and not the roll.

    The area rule draws one `random.random()` per call and walks the outcomes in
    order, so 0.0 always takes the first - the clustered one.
    """
    with patch("content.aoe.random.random", return_value=0.0):
        yield


def test_wild_flame_catches_several_and_marks_a_stress_on_each():
    random.seed(4)
    caster = _make_caster(domain_cards_loadout=["Book of Tyfar"])
    mob = [_make_adversary(name=f"Zombie {n}") for n in range(6)]
    state = _state([caster], mob)

    with _bunched():
        result = wild_flame(caster, mob[0], state)

    caught = [adversary for adversary in mob if adversary.hp_marked > 0]
    assert len(caught) > 1
    assert all(adversary.stress_marked == 1 for adversary in caught)
    assert result.damage_roll.dice_groups[0] == DiceGroup(count=2, sides=6)


def test_wild_flame_never_reaches_more_than_three():
    """The card's own cap, on top of whatever the Melee band would allow."""
    random.seed(4)
    caster = _make_caster(domain_cards_loadout=["Book of Tyfar"])
    mob = [_make_adversary(name=f"Zombie {n}") for n in range(12)]
    state = _state([caster], mob)

    with _bunched():
        wild_flame(caster, mob[0], state)

    assert len([a for a in mob if a.hp_marked > 0]) <= 3


def test_wild_flame_declines_with_nothing_left_to_burn():
    caster = _make_caster(domain_cards_loadout=["Book of Tyfar"])
    state = _state([caster], [])

    assert wild_flame(caster, None, state) is None


def test_wild_flame_takes_the_roll_when_the_book_is_cast():
    """Tyfar has one action spell, so casting the book always reaches it."""
    random.seed(4)
    caster = _make_caster(domain_cards_loadout=["Book of Tyfar"])
    mob = [_make_adversary(name="A"), _make_adversary(name="B")]
    state = _state([caster], mob)

    with _bunched():
        result = take_action(caster, mob[0], state)

    assert result is not None
    assert result.damage_roll.dice_groups[0] == DiceGroup(count=2, sides=6)


def test_tyfars_two_utility_spells_are_declared_against_the_book():
    gaps = " ".join(assess("Book of Tyfar").unmodelled)

    assert "Magic Hand" in gaps
    assert "Mysterious Mist" in gaps
    assert assess("Magic Hand").status.value == "no combat effect"


# --- Book of Sitil: Parallela ------------------------------------------------


def _damage_of(total: int) -> DamageRollResult:
    return DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=12)],
        die_results=[[total]],
        modifier=0,
    )


def _landed(damage: int = 6) -> AttackResult:
    """An attack that hit, rolling a fixed 14 for the second target to be checked against.

    Constructed rather than rolled: what the rider does with a landed attack is
    the point, and which adversaries a 14 reaches is then a property of their own
    Difficulties rather than of the dice.
    """
    return AttackResult(
        attack_roll=DualityRollResult(
            hope_die_result=10,
            fear_die_result=4,
            modifier=0,
            advantage_state=AdvantageState.NONE,
            advantage_die_result=None,
            help_dice_results=None,
            difficulty=0,
        ),
        damage_roll=_damage_of(damage),
        hp_marked=1,
    )


def test_parallela_hangs_on_an_ally_and_costs_two_hope():
    caster = _make_caster(domain_cards_loadout=["Book of Sitil"], hope_marked=6)
    ally = _make_caster(name="Artorias", domain_cards_loadout=[])
    mob = [_make_adversary(name="A"), _make_adversary(name="B")]
    state = _state([caster, ally], mob)

    assert parallela(caster, state) is True
    assert caster.hope_marked == 4
    assert state.token_count(ally, PARALLELA) == 1


def test_parallela_is_never_cast_on_the_caster():
    """Ruled: it goes on somebody else, so a lone PC can't use it at all."""
    caster = _make_caster(domain_cards_loadout=["Book of Sitil"], hope_marked=6)
    mob = [_make_adversary(name="A"), _make_adversary(name="B")]
    state = _state([caster], mob)

    assert parallela(caster, state) is False
    assert caster.hope_marked == 6


def test_parallela_declines_against_a_single_adversary():
    """With nothing else standing there is no additional target to find."""
    caster = _make_caster(domain_cards_loadout=["Book of Sitil"], hope_marked=6)
    ally = _make_caster(name="Artorias", domain_cards_loadout=[])
    state = _state([caster, ally], [_make_adversary()])

    assert parallela(caster, state) is False
    assert caster.hope_marked == 6


def test_parallela_is_not_recast_while_it_is_already_held():
    caster = _make_caster(domain_cards_loadout=["Book of Sitil"], hope_marked=6)
    ally = _make_caster(name="Artorias", domain_cards_loadout=[])
    mob = [_make_adversary(name="A"), _make_adversary(name="B")]
    state = _state([caster, ally], mob)

    parallela(caster, state)

    assert parallela(caster, state) is False
    assert caster.hope_marked == 4


def test_parallela_cannot_be_cast_without_the_hope():
    caster = _make_caster(domain_cards_loadout=["Book of Sitil"], hope_marked=1)
    ally = _make_caster(name="Artorias", domain_cards_loadout=[])
    mob = [_make_adversary(name="A"), _make_adversary(name="B")]
    state = _state([caster, ally], mob)

    assert parallela(caster, state) is False


def test_the_rider_carries_the_attack_into_a_second_adversary():
    caster = _make_caster(domain_cards_loadout=["Book of Sitil"])
    ally = _make_caster(name="Artorias", domain_cards_loadout=[])
    struck, second = _make_adversary(name="A"), _make_adversary(name="B")
    state = _state([caster, ally], [struck, second])
    state.add_token(ally, PARALLELA, cap=1)

    parallela_doubles(caster, ally, struck, _landed(damage=6), state)

    assert second.hp_marked > 0  # the full damage roll, not half of it
    assert state.token_count(ally, PARALLELA) == 0


def test_the_rider_reaches_an_allys_attack_through_dispatch():
    """Nothing in combat/policy.py knows this card; it asks the party-wide hook."""
    caster = _make_caster(domain_cards_loadout=["Book of Sitil"])
    ally = _make_caster(name="Artorias", domain_cards_loadout=[])
    struck, second = _make_adversary(name="A"), _make_adversary(name="B")
    state = _state([caster, ally], [struck, second])
    state.add_token(ally, PARALLELA, cap=1)

    apply_ally_on_hit(ally, struck, _landed(damage=6), state)

    assert second.hp_marked > 0


def test_an_attack_by_somebody_without_the_spell_carries_nowhere():
    caster = _make_caster(domain_cards_loadout=["Book of Sitil"])
    ally = _make_caster(name="Artorias", domain_cards_loadout=[])
    struck, second = _make_adversary(name="A"), _make_adversary(name="B")
    state = _state([caster, ally], [struck, second])

    apply_ally_on_hit(ally, struck, _landed(damage=6), state)

    assert second.hp_marked == 0


def test_the_spell_is_spent_even_when_no_second_target_was_beaten():
    """It resolves on the attack, whether or not the roll reached anybody else."""
    caster = _make_caster(domain_cards_loadout=["Book of Sitil"])
    ally = _make_caster(name="Artorias", domain_cards_loadout=[])
    struck = _make_adversary(name="A")
    untouchable = _make_adversary(name="B", difficulty=99)
    state = _state([caster, ally], [struck, untouchable])
    state.add_token(ally, PARALLELA, cap=1)

    parallela_doubles(caster, ally, struck, _landed(damage=6), state)

    assert untouchable.hp_marked == 0
    assert state.token_count(ally, PARALLELA) == 0


def test_the_spell_only_fires_once():
    caster = _make_caster(domain_cards_loadout=["Book of Sitil"])
    ally = _make_caster(name="Artorias", domain_cards_loadout=[])
    struck, second = _make_adversary(name="A"), _make_adversary(name="B")
    state = _state([caster, ally], [struck, second])
    state.add_token(ally, PARALLELA, cap=1)

    parallela_doubles(caster, ally, struck, _landed(damage=6), state)
    marked = second.hp_marked
    parallela_doubles(caster, ally, struck, _landed(damage=6), state)

    assert second.hp_marked == marked


# --- Book of Vagras ----------------------------------------------------------


def test_a_book_with_nothing_to_run_is_dismissed_rather_than_missing():
    """A Grimoire that registered no spell would report the card unimplemented."""
    assessment = assess("Book of Vagras")

    assert assessment.status.value == "no combat effect"
    assert assessment.reason


def test_reveal_was_ruled_not_to_find_hidden_creatures():
    assert assess("Reveal").status.value == "no combat effect"
    assert "Cloaked" in assess("Reveal").reason


# --- Bolt Beacon -------------------------------------------------------------


def _roll_that(succeeds: bool) -> DualityRollResult:
    """A duality roll with a settled outcome, so a case isn't about the dice."""
    return DualityRollResult(
        hope_die_result=10,
        fear_die_result=4,
        modifier=0,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=0 if succeeds else 99,
    )


def test_bolt_beacon_burns_a_hope_and_leaves_the_target_vulnerable():
    random.seed(6)
    caster = _make_caster(domain_cards_loadout=["Bolt Beacon"], hope_marked=6)
    target = _make_adversary()
    state = _state([caster], [target])

    result = bolt_beacon(caster, target, state)

    assert result.damage_roll.dice_groups[0] == DiceGroup(count=2, sides=8)
    assert target.hp_marked > 0
    assert caster.hope_marked == 5
    assert state.has_condition(target, VULNERABLE) is True


def test_bolt_beacon_is_not_cast_at_all_without_a_hope():
    """The Hope is what sends the bolt, so with none there is nothing to cast."""
    caster = _make_caster(domain_cards_loadout=["Bolt Beacon"], hope_marked=0)
    target = _make_adversary()
    state = _state([caster], [target])

    assert bolt_beacon(caster, target, state) is None
    assert target.hp_marked == 0


def test_a_missed_bolt_beacon_keeps_its_hope():
    caster = _make_caster(domain_cards_loadout=["Bolt Beacon"], hope_marked=6)
    target = _make_adversary()
    state = _state([caster], [target])

    with patch("domain_cards.splendor.roll_duality", return_value=_roll_that(False)):
        result = bolt_beacon(caster, target, state)

    assert result.damage_roll is None
    assert caster.hope_marked == 6
    assert state.has_condition(target, VULNERABLE) is False


# --- Reassurance -------------------------------------------------------------


def test_reassurance_rerolls_an_allys_failure():
    holder = _make_caster(name="Seraph", domain_cards_loadout=["Reassurance"])
    ally = _make_caster(name="Artorias", domain_cards_loadout=[])
    state = _state([holder, ally], [], rest=Rest.LONG)
    replacement = _roll_that(True)

    made = remake_action_roll(ally, _roll_that(False), lambda: replacement, state)

    assert made is replacement
    assert state.can_use_once_per_rest(holder, "Reassurance") is False


def test_reassurance_leaves_a_successful_roll_alone():
    holder = _make_caster(name="Seraph", domain_cards_loadout=["Reassurance"])
    ally = _make_caster(name="Artorias", domain_cards_loadout=[])
    state = _state([holder, ally], [], rest=Rest.LONG)
    succeeded = _roll_that(True)

    assert remake_action_roll(ally, succeeded, lambda: _roll_that(True), state) is succeeded
    assert state.can_use_once_per_rest(holder, "Reassurance") is True


def test_reassurance_is_for_an_ally_and_not_for_yourself():
    """The card says "an ally", where Luckbender says "yours or an ally's"."""
    holder = _make_caster(name="Seraph", domain_cards_loadout=["Reassurance"])
    state = _state([holder], [], rest=Rest.LONG)
    failed = _roll_that(False)

    assert remake_action_roll(holder, failed, lambda: _roll_that(True), state) is failed
    assert state.can_use_once_per_rest(holder, "Reassurance") is True


def test_reassurance_is_spent_after_one_use():
    holder = _make_caster(name="Seraph", domain_cards_loadout=["Reassurance"])
    ally = _make_caster(name="Artorias", domain_cards_loadout=[])
    state = _state([holder, ally], [], rest=Rest.LONG)

    remake_action_roll(ally, _roll_that(False), lambda: _roll_that(True), state)
    second = _roll_that(False)

    assert remake_action_roll(ally, second, lambda: _roll_that(True), state) is second


# --- Natural Familiar --------------------------------------------------------


def test_the_familiar_costs_a_hope_to_summon():
    caster = _make_caster(domain_cards_loadout=["Natural Familiar"], hope_marked=6)
    state = _state([caster], [_make_adversary()])

    assert use_free_abilities(caster, state, limit=1) == ["Natural Familiar"]
    assert caster.hope_marked == 5
    assert state.token_count(caster, FAMILIAR) == 1


def test_a_second_familiar_is_not_summoned():
    caster = _make_caster(domain_cards_loadout=["Natural Familiar"], hope_marked=6)
    state = _state([caster], [_make_adversary()])

    use_free_abilities(caster, state, limit=1)

    assert use_free_abilities(caster, state, limit=1) == []
    assert caster.hope_marked == 5


def test_nothing_is_summoned_into_an_empty_field():
    caster = _make_caster(domain_cards_loadout=["Natural Familiar"], hope_marked=6)
    state = _state([caster], [])

    assert use_free_abilities(caster, state, limit=1) == []
    assert caster.hope_marked == 6


def test_the_familiars_die_rides_an_attack_it_is_standing_beside():
    caster = _make_caster(domain_cards_loadout=["Natural Familiar"])
    target = _make_adversary()
    state = _state([caster], [target])
    state.add_token(caster, FAMILIAR, cap=1)

    # Against a single adversary the familiar is always beside it, so any draw
    # under 1.0 is in range.
    with patch("domain_cards.sage.random.random", return_value=0.0):
        dice = familiar_flanks(caster, target, None, state)

    assert [(group.count, group.sides) for group in dice] == [(1, 6)]
    assert dice[0].discardable is False


def test_the_familiars_die_stays_home_when_the_field_is_spread_out():
    caster = _make_caster(domain_cards_loadout=["Natural Familiar"])
    mob = [_make_adversary(name=f"A{n}") for n in range(12)]
    state = _state([caster], mob)
    state.add_token(caster, FAMILIAR, cap=1)

    with patch("domain_cards.sage.random.random", return_value=0.999):
        assert familiar_flanks(caster, mob[0], None, state) == []


def test_no_familiar_means_no_die():
    caster = _make_caster(domain_cards_loadout=["Natural Familiar"])
    target = _make_adversary()
    state = _state([caster], [target])

    with patch("domain_cards.sage.random.random", return_value=0.0):
        assert familiar_flanks(caster, target, None, state) == []


# --- Assessed rather than built ----------------------------------------------


def test_gifted_tracker_was_dismissed_on_its_trigger_not_its_size():
    assessment = assess("Gifted Tracker")

    assert assessment.status.value == "no combat effect"
    assert "tracked" in assessment.reason


def test_mending_touch_waits_for_sequenced_encounters():
    assert assess("Mending Touch").status.value == "out of combat"


def test_final_words_cannot_change_a_fight():
    assert assess("Final Words").status.value == "no combat effect"
