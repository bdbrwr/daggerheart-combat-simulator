"""Content that re-makes a roll after it has already resolved.

Three features share one piece of machinery: the Wizard's Not This Time reaches
across the table to an adversary's d20, while the Faerie's Luckbender and the
Human's Adaptability re-make a PC's own Duality Dice.

Every roll here is built by hand and every `remake` is a stub returning a fixed
result, so nothing depends on the dice. The one genuinely random decision -
whether an ally is within Close range - is patched.
"""

from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.state import FightState
from content.registry import force_adversary_reroll, remake_action_roll
from content.rolls import note_experience_utilised
from dice.common import AdvantageState
from dice.d20 import D20RollResult
from dice.duality import DualityRollResult
from features.ancestries import LUCKBENDER, adaptability, luckbender
from features.classes import not_this_time

REROLLED_TOTAL = 23


def _make_pc(name: str, **overrides) -> PlayerCharacter:
    defaults = dict(
        name=name,
        level=2,
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 1, "strength": 1, "finesse": 1,
            "instinct": 1, "presence": 0, "knowledge": 1,
        },
        evasion=10,
        proficiency=1,
        major_threshold=6,
        severe_threshold=12,
        hp_max=6,
        stress_max=6,
        hope_max=6,
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


def _make_adversary(name: str = "Bandit") -> Adversary:
    return Adversary(
        name=name,
        tier=1,
        difficulty=11,
        major_threshold=5,
        severe_threshold=10,
        hp_max=8,
        stress_max=3,
        attack_modifier=1,
    )


def _fight(party: list[PlayerCharacter], adversaries=None, **overrides) -> FightState:
    return FightState(
        encounter_name="Test",
        party=party,
        adversaries=adversaries if adversaries is not None else [_make_adversary()],
        **overrides,
    )


def _duality(*, hope: int, fear: int, modifier: int = 0, difficulty: int = 11):
    return DualityRollResult(
        hope_die_result=hope,
        fear_die_result=fear,
        modifier=modifier,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=difficulty,
    )


def _failed() -> DualityRollResult:
    """A roll of 3 against Difficulty 11 - a failure, and not a critical."""
    return _duality(hope=2, fear=1)


def _succeeded() -> DualityRollResult:
    return _duality(hope=9, fear=8)


def _d20(die: int, evasion: int = 10) -> D20RollResult:
    return D20RollResult(
        die_results=[die],
        modifier=1,
        advantage_state=AdvantageState.NONE,
        evasion=evasion,
    )


def _remake_duality():
    """A stub reroll, distinguishable from anything built above by its total."""
    return _duality(hope=12, fear=11)


def _remake_d20():
    return _d20(2)


# --- Not This Time -----------------------------------------------------------
#
# Two triggers, so every test here has to say which PC is being swung at as well
# as what the d20 did. `_unhurt` isolates the critical, `_bleeding` the other.


def _unhurt(name: str = "Artorias") -> PlayerCharacter:
    """A target with every HP unmarked - nowhere near death."""
    return _make_pc(name)


def _bleeding(name: str = "Artorias") -> PlayerCharacter:
    """A target on 2 unmarked HP of 6, which is `NEAR_DEATH_HP_UNMARKED`."""
    return _make_pc(name, hp_marked=4)


def test_a_critical_is_rerolled_for_three_hope():
    wizard = _make_pc("Wizard", hope_marked=3)
    adversary = _make_adversary()
    fight = _fight([wizard], [adversary])

    replacement = not_this_time(
        wizard, adversary, _unhurt(), _d20(20), _remake_d20, fight
    )

    assert replacement is not None
    assert replacement.die_result == 2
    assert wizard.hope_marked == 0


def test_an_ordinary_hit_on_an_unhurt_pc_is_left_alone():
    """The card allows it; the policy holds the Hope for the two rolls worth it."""
    wizard = _make_pc("Wizard", hope_marked=6)
    fight = _fight([wizard])

    assert (
        not_this_time(
            wizard, _make_adversary(), _unhurt(), _d20(18), _remake_d20, fight
        )
        is None
    )
    assert wizard.hope_marked == 6


def test_an_ordinary_hit_on_a_near_death_pc_is_rerolled():
    """Not a critical, but the damage is measured against a PC leaving the fight."""
    wizard = _make_pc("Wizard", hope_marked=3)
    fight = _fight([wizard])

    replacement = not_this_time(
        wizard, _make_adversary(), _bleeding(), _d20(18), _remake_d20, fight
    )

    assert replacement is not None
    assert replacement.die_result == 2
    assert wizard.hope_marked == 0


def test_a_miss_is_never_rerolled():
    """Even on a near-death PC: a reroll can only give the GM a second try."""
    wizard = _make_pc("Wizard", hope_marked=6)
    fight = _fight([wizard])

    assert (
        not_this_time(
            wizard, _make_adversary(), _bleeding(), _d20(1), _remake_d20, fight
        )
        is None
    )
    assert wizard.hope_marked == 6


def test_a_critical_costs_nothing_without_the_full_three_hope():
    wizard = _make_pc("Wizard", hope_marked=2)
    fight = _fight([wizard])

    assert (
        not_this_time(
            wizard, _make_adversary(), _unhurt(), _d20(20), _remake_d20, fight
        )
        is None
    )
    assert wizard.hope_marked == 2


def test_an_adversarys_critical_reaches_the_wizard_through_dispatch():
    """The Wizard isn't the one being attacked, so the scan has to be party-wide."""
    wizard = _make_pc("Wizard", character_class="Wizard", hope_marked=3)
    fighter = _make_pc("Fighter")
    fight = _fight([fighter, wizard])

    replacement = force_adversary_reroll(
        _make_adversary(), fighter, _d20(20), _remake_d20, fight
    )

    assert replacement.die_result == 2
    assert wizard.hope_marked == 0


def test_an_adversary_roll_stands_when_there_is_no_fight_to_ask():
    """Damage can be resolved outside a fight, and then there's no party."""
    original = _d20(20)

    assert (
        force_adversary_reroll(_make_adversary(), _unhurt(), original, _remake_d20)
        is original
    )


# --- Luckbender --------------------------------------------------------------


def _faerie(**overrides) -> PlayerCharacter:
    """A Faerie at the Hope floor, unless a test says otherwise."""
    overrides.setdefault("hope_marked", 6)
    return _make_pc("Aeloria", ancestry="Faerie", **overrides)


def test_a_faerie_rerolls_her_own_failed_roll_for_three_hope():
    faerie = _faerie()
    fight = _fight([faerie])

    replacement = luckbender(faerie, faerie, _failed(), _remake_duality, fight)

    assert replacement is not None
    assert replacement.total == REROLLED_TOTAL
    assert faerie.hope_marked == 3


def test_a_successful_roll_is_not_rerolled():
    faerie = _faerie()
    fight = _fight([faerie])

    assert luckbender(faerie, faerie, _succeeded(), _remake_duality, fight) is None
    assert faerie.hope_marked == 6


def test_luckbender_holds_below_its_hope_floor():
    """Affordable at 3 Hope, but held until 6 so a class Hope feature survives it."""
    faerie = _faerie(hope_marked=5)
    fight = _fight([faerie])

    assert luckbender(faerie, faerie, _failed(), _remake_duality, fight) is None
    assert faerie.hope_marked == 5


def test_luckbender_is_once_per_long_rest():
    faerie = _faerie(hope_marked=6)
    fight = _fight([faerie])

    assert luckbender(faerie, faerie, _failed(), _remake_duality, fight) is not None
    faerie.gain_hope(6)
    assert luckbender(faerie, faerie, _failed(), _remake_duality, fight) is None


def test_luckbender_is_already_spent_in_a_no_rest_encounter():
    faerie = _faerie()
    fight = _fight([faerie], rest=Rest.NONE)

    assert luckbender(faerie, faerie, _failed(), _remake_duality, fight) is None
    assert faerie.hope_marked == 6


def _party_around(faerie: PlayerCharacter, ally: PlayerCharacter) -> list:
    """A four-PC party, which is the size the range question is meaningful at.

    The field Close is measured over is **the rest of the party**, so with only
    one other PC the band's own "never all of them" rule leaves nothing for it to
    reach and the odds collapse. Four PCs put three allies on the field, where
    Close reaches two - the 2/3 these cases are pinned either side of.
    """
    return [faerie, ally, _make_pc("Bran"), _make_pc("Cass")]


def test_an_allys_roll_is_rescued_when_they_are_within_close_range():
    faerie = _faerie()
    ally = _make_pc("Artorias")
    fight = _fight(_party_around(faerie, ally))

    with patch("features.ancestries.random.random", return_value=0.0):
        replacement = luckbender(faerie, ally, _failed(), _remake_duality, fight)

    assert replacement is not None
    assert faerie.hope_marked == 3


def test_an_ally_out_of_close_range_is_not_rescued():
    """Close reaches two of three allies, so 0.99 falls outside it."""
    faerie = _faerie()
    ally = _make_pc("Artorias")
    fight = _fight(_party_around(faerie, ally))

    with patch("features.ancestries.random.random", return_value=0.99):
        assert luckbender(faerie, ally, _failed(), _remake_duality, fight) is None

    # Declining has to be free: neither the Hope nor the per-rest use is spent.
    assert faerie.hope_marked == 6
    assert fight.can_use_once_per_rest(faerie, LUCKBENDER, long=True)


def test_a_faerie_needs_no_range_check_for_her_own_roll():
    """"Within Close range" qualifies the ally in the card text, not you."""
    faerie = _faerie()
    fight = _fight([faerie])

    with patch("features.ancestries.random.random", return_value=0.99):
        assert luckbender(faerie, faerie, _failed(), _remake_duality, fight) is not None


# --- Adaptability ------------------------------------------------------------


def _human(**overrides) -> PlayerCharacter:
    return _make_pc(
        "Artorias",
        ancestry="Human",
        experiences=[{"name": "No one left behind", "modifier": 2}],
        **overrides,
    )


def test_a_failed_experience_roll_is_rerolled_for_a_stress():
    human = _human()
    fight = _fight([human])
    note_experience_utilised(human, fight)

    replacement = adaptability(human, human, _failed(), _remake_duality, fight)

    assert replacement is not None
    assert replacement.total == REROLLED_TOTAL
    assert human.stress_marked == 1


def test_a_roll_without_an_experience_is_not_rerolled():
    human = _human()
    fight = _fight([human])

    assert adaptability(human, human, _failed(), _remake_duality, fight) is None
    assert human.stress_marked == 0


def test_an_experience_from_a_previous_roll_does_not_carry_over():
    human = _human()
    fight = _fight([human])
    note_experience_utilised(human, fight)

    assert adaptability(human, human, _failed(), _remake_duality, fight) is not None

    from content.rolls import clear_experience_utilised

    clear_experience_utilised(human, fight)
    assert adaptability(human, human, _failed(), _remake_duality, fight) is None


def test_adaptability_does_not_reach_an_allys_roll():
    """"When *you* fail" - this is the half Luckbender does differently."""
    human = _human()
    ally = _make_pc("Aeloria")
    fight = _fight([human, ally])
    note_experience_utilised(human, fight)

    assert adaptability(human, ally, _failed(), _remake_duality, fight) is None
    assert human.stress_marked == 0


def test_adaptability_keeps_the_last_stress_slots_back():
    human = _human(stress_marked=5)
    fight = _fight([human])
    note_experience_utilised(human, fight)

    assert adaptability(human, human, _failed(), _remake_duality, fight) is None
    assert human.stress_marked == 5


def test_adaptability_still_fires_at_the_ceiling_itself():
    human = _human(stress_marked=4)
    fight = _fight([human])
    note_experience_utilised(human, fight)

    assert adaptability(human, human, _failed(), _remake_duality, fight) is not None
    assert human.stress_marked == 5


# --- The dispatch itself -----------------------------------------------------


def test_an_untouched_roll_comes_back_unchanged():
    """Callers use the return value unconditionally, so it can't be None."""
    pc = _make_pc("Nobody")
    fight = _fight([pc])
    original = _failed()

    assert remake_action_roll(pc, original, _remake_duality, fight) is original


def test_only_one_reroll_applies_to_a_single_roll():
    """Both are willing; stacking them would buy three attempts at one roll."""
    faerie = _faerie()
    human = _human()
    fight = _fight([faerie, human])
    note_experience_utilised(human, fight)

    with patch("features.ancestries.random.random", return_value=0.0):
        replacement = remake_action_roll(human, _failed(), _remake_duality, fight)

    assert replacement is not None
    # Whichever answered first, exactly one of them paid - the shuffle means the
    # test can't say which, only that the other was never asked.
    paid = (faerie.hope_marked == 3) + (human.stress_marked == 1)
    assert paid == 1
