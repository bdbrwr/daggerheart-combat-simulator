"""Tests for the Grace and Midnight domain cards - the last two ported.

Five of the ten run. The two worth the most care are the ones whose real effect
isn't the one the card appears to describe: Enrapture, which moves an adversary's
attacks onto the caster, and Shadowbind, whose whole value is the Fear the GM has
to spend undoing it. Both are checked through the machinery that reads them
rather than by inspecting a condition record.
"""

from contextlib import contextmanager
from unittest.mock import patch

import pytest

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.policy import choose_adversary_target
from combat.rest import Rest
from combat.state import FightState
from content import Status, assess
from content.conditions import (
    ENRAPTURED,
    ON_A_GM_TURN,
    RESTRAINED,
    VULNERABLE,
    Condition,
)
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from domain_cards.grace import enrapture, troublemaker
from domain_cards.midnight import midnight_spirit, rain_of_blades, shadowbind

ENRAPTURE = "Enrapture"
TROUBLEMAKER = "Troublemaker"
RAIN_OF_BLADES = "Rain of Blades"
MIDNIGHT_SPIRIT = "Midnight Spirit"
SHADOWBIND = "Shadowbind"


def _make_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Bard",
        level=2,
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 0,
            "strength": 0,
            "finesse": 1,
            "instinct": 1,
            "presence": 3,
            "knowledge": 2,
        },
        evasion=11,
        proficiency=2,
        spellcast_trait="presence",
        major_threshold=9,
        severe_threshold=18,
        hp_max=7,
        stress_max=6,
        hope_max=6,
        hope_marked=6,
        armor_max=0,
        primary_weapon="Shortbow",
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


@contextmanager
def _bunched():
    """Every band at its best reach, so a case is about the card not the spread."""
    with patch("content.aoe.random.random", return_value=0.0):
        yield


# --- Enrapture ---------------------------------------------------------------


def test_enrapture_fixes_the_adversarys_attacks_on_the_caster():
    """Checked through the targeting rule, which is the only thing that reads it."""
    caster = _make_pc(name="Bard", domain_cards_loadout=[ENRAPTURE])
    ally = _make_pc(name="Guardian", domain_cards_loadout=[])
    adversary = _make_adversary()
    state = _state([caster, ally], [adversary], rest=Rest.LONG)
    # Without the spell the adversary would swing at whoever hit it last.
    state.last_attacker_of[id(adversary)] = ally

    enrapture(caster, adversary, state)

    assert state.has_condition(adversary, ENRAPTURED) is True
    assert choose_adversary_target(adversary, state) is caster


def test_an_adversary_nobody_enraptured_is_targeted_normally():
    caster = _make_pc(name="Bard", domain_cards_loadout=[ENRAPTURE])
    ally = _make_pc(name="Guardian", domain_cards_loadout=[])
    adversary = _make_adversary()
    state = _state([caster, ally], [adversary])
    state.last_attacker_of[id(adversary)] = ally

    assert choose_adversary_target(adversary, state) is ally


def test_the_gm_pays_a_fear_to_break_the_spell():
    caster = _make_pc(domain_cards_loadout=[ENRAPTURE])
    adversary = _make_adversary()
    state = _state([caster], [adversary], fear=2, rest=Rest.LONG)

    enrapture(caster, adversary, state)
    ended = state.expire_conditions(adversary, ON_A_GM_TURN)

    assert ENRAPTURED in ended
    assert state.fear == 1


def test_enrapture_costs_a_stress_to_cost_them_one():
    caster = _make_pc(domain_cards_loadout=[ENRAPTURE])
    adversary = _make_adversary()
    state = _state([caster], [adversary], rest=Rest.LONG)

    enrapture(caster, adversary, state)

    assert caster.stress_marked == 1
    assert adversary.stress_marked == 1


def test_the_forced_stress_is_once_per_rest():
    caster = _make_pc(domain_cards_loadout=[ENRAPTURE])
    first, second = _make_adversary(name="A"), _make_adversary(name="B")
    state = _state([caster], [first, second], rest=Rest.LONG)

    enrapture(caster, first, state)
    enrapture(caster, second, state)

    assert caster.stress_marked == 1
    assert second.stress_marked == 0


def test_enrapture_declines_against_a_target_already_enraptured():
    caster = _make_pc(domain_cards_loadout=[ENRAPTURE])
    adversary = _make_adversary()
    state = _state([caster], [adversary], rest=Rest.LONG)

    enrapture(caster, adversary, state)

    assert enrapture(caster, adversary, state) is None


def test_an_unconscious_caster_compels_nobody():
    """The override only reaches a PC who can still be attacked."""
    caster = _make_pc(name="Bard", domain_cards_loadout=[ENRAPTURE])
    ally = _make_pc(name="Guardian", domain_cards_loadout=[])
    adversary = _make_adversary()
    state = _state([caster, ally], [adversary], rest=Rest.LONG)

    enrapture(caster, adversary, state)
    caster.unconscious = True

    assert choose_adversary_target(adversary, state) is ally


# --- Troublemaker ------------------------------------------------------------


def test_troublemaker_forces_stress_without_dealing_damage():
    caster = _make_pc(domain_cards_loadout=[TROUBLEMAKER])
    adversary = _make_adversary()
    state = _state([caster], [adversary], rest=Rest.LONG)

    result = troublemaker(caster, adversary, state)

    assert result.damage_roll is None
    assert result.made_an_attack is True
    assert adversary.stress_marked > 0


def test_troublemaker_is_once_per_rest():
    caster = _make_pc(domain_cards_loadout=[TROUBLEMAKER])
    adversary = _make_adversary()
    state = _state([caster], [adversary], rest=Rest.LONG)

    troublemaker(caster, adversary, state)

    assert troublemaker(caster, adversary, state) is None


def test_troublemaker_is_unavailable_without_a_rest():
    caster = _make_pc(domain_cards_loadout=[TROUBLEMAKER])
    adversary = _make_adversary()
    state = _state([caster], [adversary], rest=Rest.NONE)

    assert troublemaker(caster, adversary, state) is None


def test_troublemaker_needs_no_spellcast_trait():
    """It rolls Presence, so a PC who casts nothing can still provoke."""
    caster = _make_pc(spellcast_trait="", domain_cards_loadout=[TROUBLEMAKER])
    adversary = _make_adversary()
    state = _state([caster], [adversary], rest=Rest.LONG)

    assert troublemaker(caster, adversary, state) is not None


# --- Rain of Blades ----------------------------------------------------------


def test_rain_of_blades_catches_everything_the_band_reaches():
    caster = _make_pc(domain_cards_loadout=[RAIN_OF_BLADES])
    mob = [_make_adversary(name=f"A{n}") for n in range(9)]
    state = _state([caster], mob)

    with _bunched():
        result = rain_of_blades(caster, mob[0], state)

    assert result.damage_roll.dice_groups[0] == DiceGroup(count=2, sides=8)
    assert len([a for a in mob if a.hp_marked > 0]) > 1
    assert caster.hope_marked == 5


def test_rain_of_blades_declines_against_a_single_target():
    caster = _make_pc(domain_cards_loadout=[RAIN_OF_BLADES])
    adversary = _make_adversary()
    state = _state([caster], [adversary])

    assert rain_of_blades(caster, adversary, state) is None
    assert caster.hope_marked == 6


def test_rain_of_blades_needs_a_hope():
    caster = _make_pc(domain_cards_loadout=[RAIN_OF_BLADES], hope_marked=0)
    mob = [_make_adversary(name=f"A{n}") for n in range(9)]
    state = _state([caster], mob)

    with _bunched():
        assert rain_of_blades(caster, mob[0], state) is None


def test_a_vulnerable_target_takes_more_than_the_others():
    """The rider is per target, so two adversaries in one sweep can differ.

    Both damage rolls are pinned to the same fixed five, so a Vulnerable target
    takes ten and everyone else takes five - and the thresholds are set between
    the two, which is the only way the difference shows up as marked HP.
    """
    caster = _make_pc(domain_cards_loadout=[RAIN_OF_BLADES])
    mob = [
        _make_adversary(name=f"A{n}", major_threshold=8, severe_threshold=1000)
        for n in range(9)
    ]
    state = _state([caster], mob)
    state.apply_condition(mob[1], Condition(name=VULNERABLE))

    fixed = DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=8)], die_results=[[5]], modifier=0
    )
    with _bunched(), patch("domain_cards.midnight.roll_damage", return_value=fixed):
        rain_of_blades(caster, mob[0], state)

    assert mob[0].hp_marked == 1  # 5, below the Major threshold
    assert mob[1].hp_marked == 2  # 5 + the Vulnerable rider's 5, which clears it


# --- Midnight Spirit ---------------------------------------------------------


def test_the_spirit_deals_spellcast_trait_dice():
    caster = _make_pc(domain_cards_loadout=[MIDNIGHT_SPIRIT])  # presence 3
    adversary = _make_adversary()
    state = _state([caster], [adversary])

    result = midnight_spirit(caster, adversary, state)

    assert result.damage_roll.dice_groups[0] == DiceGroup(count=3, sides=6)
    assert caster.hope_marked == 5


def test_the_spirit_costs_its_hope_even_on_a_miss():
    """The Hope pays for the summoning, which happens whether the spirit lands."""
    caster = _make_pc(domain_cards_loadout=[MIDNIGHT_SPIRIT])
    adversary = _make_adversary(difficulty=99)
    state = _state([caster], [adversary])

    missed = DualityRollResult(
        hope_die_result=10,
        fear_die_result=4,
        modifier=0,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=99,
    )
    with patch("domain_cards.midnight.roll_duality", return_value=missed):
        result = midnight_spirit(caster, adversary, state)

    assert result.damage_roll is None
    assert caster.hope_marked == 5
    assert adversary.hp_marked == 0


def test_no_spirit_without_a_hope():
    caster = _make_pc(domain_cards_loadout=[MIDNIGHT_SPIRIT], hope_marked=0)
    adversary = _make_adversary()
    state = _state([caster], [adversary])

    assert midnight_spirit(caster, adversary, state) is None


def test_a_spellcast_trait_of_zero_summons_nothing():
    caster = _make_pc(
        domain_cards_loadout=[MIDNIGHT_SPIRIT],
        traits={
            "agility": 0,
            "strength": 0,
            "finesse": 0,
            "instinct": 0,
            "presence": 0,
            "knowledge": 0,
        },
    )
    adversary = _make_adversary()
    state = _state([caster], [adversary])

    assert midnight_spirit(caster, adversary, state) is None
    assert caster.hope_marked == 6


# --- Shadowbind --------------------------------------------------------------


def test_shadowbind_restrains_what_it_beats():
    caster = _make_pc(domain_cards_loadout=[SHADOWBIND])
    mob = [_make_adversary(name=f"A{n}") for n in range(9)]
    state = _state([caster], mob)

    with _bunched():
        shadowbind(caster, mob[0], state)

    assert any(state.has_condition(a, RESTRAINED) for a in mob)


def test_binding_costs_the_gm_a_fear_per_adversary():
    """The card's whole value here, since Restrained does nothing by itself."""
    caster = _make_pc(domain_cards_loadout=[SHADOWBIND])
    mob = [_make_adversary(name=f"A{n}") for n in range(9)]
    state = _state([caster], mob, fear=6)

    with _bunched():
        shadowbind(caster, mob[0], state)

    bound = [a for a in mob if state.has_condition(a, RESTRAINED)]
    for adversary in bound:
        state.expire_conditions(adversary, ON_A_GM_TURN)

    assert state.fear == 6 - len(bound)


def test_shadowbind_declines_when_everything_in_reach_is_already_bound():
    caster = _make_pc(domain_cards_loadout=[SHADOWBIND])
    adversary = _make_adversary()
    state = _state([caster], [adversary])

    with _bunched():
        shadowbind(caster, adversary, state)

    with _bunched():
        assert shadowbind(caster, adversary, state) is None


def test_shadowbind_deals_no_damage():
    caster = _make_pc(domain_cards_loadout=[SHADOWBIND])
    mob = [_make_adversary(name=f"A{n}") for n in range(9)]
    state = _state([caster], mob)

    with _bunched():
        result = shadowbind(caster, mob[0], state)

    assert result.damage_roll is None
    assert all(a.hp_marked == 0 for a in mob)


# --- Assessed rather than built ----------------------------------------------


def test_inspirational_words_waits_for_sequenced_encounters():
    assert assess("Inspirational Words").status is Status.OUT_OF_COMBAT


@pytest.mark.parametrize(
    "card", ["Deft Deceiver", "Tell No Lies", "Pick and Pull", "Uncanny Disguise"]
)
def test_the_four_social_cards_are_declared_rather_than_absent(card):
    assessment = assess(card)

    assert assessment.status is Status.NO_COMBAT_EFFECT
    assert assessment.reason


def test_every_level_one_and_two_card_is_accounted_for():
    """The point of the whole port: nothing in the slice is still a gap.

    Named explicitly rather than read from the reference file, so this fails if
    a card is quietly dropped as well as if one is never written.
    """
    slice_of_the_book = [
        "Rune Ward", "Unleash Chaos", "Wall Walk", "Cinder Grasp", "Floating Eye",
        "Get Back Up", "Not Good Enough", "Whirlwind", "A Soldier's Bond", "Reckless",
        "Deft Maneuvers", "I See It Coming", "Untouchable", "Ferocity",
        "Strategic Approach",
        "Book of Ava", "Book of Illiat", "Book of Tyfar", "Book of Sitil",
        "Book of Vagras",
        "Deft Deceiver", "Enrapture", "Inspirational Words", "Tell No Lies",
        "Troublemaker",
        "Pick and Pull", "Rain of Blades", "Uncanny Disguise", "Midnight Spirit",
        "Shadowbind",
        "Gifted Tracker", "Nature's Tongue", "Vicious Entangle", "Conjure Swarm",
        "Natural Familiar",
        "Bolt Beacon", "Mending Touch", "Reassurance", "Final Words", "Healing Hands",
        "Bare Bones", "Forceful Push", "I Am Your Shield", "Body Basher",
        "Bold Presence",
    ]

    missing = [
        card
        for card in slice_of_the_book
        if assess(card).status is Status.UNIMPLEMENTED
    ]

    assert missing == []
    assert len(slice_of_the_book) == 45
