"""Tests for the last four level 6 cards - Sage, Splendor and Valor.

Four cards run and two are declarations, and the cases here split the same way.
The declarations are checked through `assess`, because *out of combat* is the one
state that is easy to get wrong in the direction that loses information: filing
Conjured Steeds or Forager as having no combat effect would look identical from
the outside and would quietly drop both off the sequenced-encounter list.

Determinism comes from the same two tricks the other domain-card files use -
a target with a Difficulty of 0 so no case turns on whether a roll landed, and a
patched `content.spellcast.roll_duality` where a case needs a particular outcome.
Zone of Protection adds a third: its membership is a `random.random()` draw
against `chance_within`, so cases patch that draw rather than seeding around it.

The readings these pin down are the ones the modules document as choices:

* Inevitable's advantage die reaches a **Spellcast Roll** as well as a weapon
  swing, which is the whole reason `action_roll_advantage` exists rather than the
  card registering on `attack_advantage`.
* Rise Up fires on **any** damage that marks HP, which is the user's ruling that
  everything marking damage in a combat simulator is an attack.
* Restoration never lifts a condition the **party** put on somebody, so it cannot
  work against its own side.
* Zone of Protection's die climbs only on a hit it actually soaked, and the zone
  ends after the one it reduces by 6.
"""

import random
from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.state import FightState
from content import (
    Status,
    apply_on_damaged,
    apply_on_roll,
    assess,
    granted_action_roll_advantage,
    party_damage_reduction,
    use_free_abilities,
)
from content.conditions import RESTRAINED, SHELTERED, Condition
from content.spellcast import spellcast
from dice.common import AdvantageState
from dice.damage import DiceGroup
from dice.duality import DualityRollResult
from domain_cards.splendor import (
    RESTORATION,
    RESTORATION_TOKENS,
    ZONE_DIE,
    ZONE_OF_PROTECTION,
    zone_of_protection,
)
from domain_cards.valor import INEVITABLE, INEVITABLE_OWED, RISE_UP
from items.registry import find_weapon
from items.weapons import attack_with

CONJURED_STEEDS = "Conjured Steeds"
FORAGER = "Forager"


def _make_character(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=6,
        # Names nothing has implemented, so a class or subclass feature never
        # lands in the same total as the card being measured.
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 0,
            "strength": 2,
            "finesse": 0,
            "instinct": 1,
            "presence": 1,
            "knowledge": 3,
        },
        evasion=11,
        proficiency=2,
        spellcast_trait="knowledge",
        major_threshold=9,
        severe_threshold=18,
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
        difficulty=0,  # every roll lands
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


def _roll(hope: int, fear: int, difficulty: int | None = None) -> DualityRollResult:
    return DualityRollResult(
        hope_die_result=hope,
        fear_die_result=fear,
        modifier=0,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=difficulty,
    )


# --- The two declarations ------------------------------------------------------


def test_the_sage_cards_are_out_of_combat_rather_than_dismissed():
    """The state matters: a dismissal would drop both off the sequenced list."""
    assert assess(CONJURED_STEEDS).status is Status.OUT_OF_COMBAT
    assert assess(FORAGER).status is Status.OUT_OF_COMBAT


def test_the_declarations_say_why():
    """An assessment with no reason is indistinguishable from a shrug."""
    assert assess(CONJURED_STEEDS).reason
    assert assess(FORAGER).reason


# --- Inevitable ----------------------------------------------------------------


def test_a_failed_action_roll_owes_the_next_one_an_advantage_die():
    character = _make_character(domain_cards_loadout=[INEVITABLE])
    fight = _state([character], [])

    apply_on_roll(character, _roll(3, 4, difficulty=15), fight)

    assert fight.token_count(character, INEVITABLE_OWED) == 1


def test_a_successful_action_roll_owes_nothing():
    character = _make_character(domain_cards_loadout=[INEVITABLE])
    fight = _state([character], [])

    apply_on_roll(character, _roll(11, 10, difficulty=15), fight)

    assert fight.token_count(character, INEVITABLE_OWED) == 0


def test_a_roll_with_no_difficulty_is_not_a_failure():
    """`is_success` is None there, which must not read as False."""
    character = _make_character(domain_cards_loadout=[INEVITABLE])
    fight = _state([character], [])

    apply_on_roll(character, _roll(3, 4), fight)

    assert fight.token_count(character, INEVITABLE_OWED) == 0


def test_the_advantage_die_is_spent_on_being_asked():
    character = _make_character(domain_cards_loadout=[INEVITABLE])
    fight = _state([character], [])
    fight.set_token(character, INEVITABLE_OWED, 1)

    granted = granted_action_roll_advantage(character, None, fight)

    assert granted is AdvantageState.ADVANTAGE
    assert fight.token_count(character, INEVITABLE_OWED) == 0


def test_nothing_is_granted_when_nothing_is_owed():
    character = _make_character(domain_cards_loadout=[INEVITABLE])
    fight = _state([character], [])

    assert granted_action_roll_advantage(character, None, fight) is AdvantageState.NONE


def test_the_advantage_die_reaches_a_weapon_swing():
    """The hook is folded into `attack_with` beside the attack-only one."""
    random.seed(3)
    character = _make_character(domain_cards_loadout=[INEVITABLE])
    target = _make_adversary()
    fight = _state([character], [target])
    fight.set_token(character, INEVITABLE_OWED, 1)

    result = attack_with(
        character, find_weapon("Broadsword"), target, fight=fight
    )

    assert result.attack_roll.advantage_state is AdvantageState.ADVANTAGE
    assert fight.token_count(character, INEVITABLE_OWED) == 0


def test_the_advantage_die_reaches_a_spellcast_roll():
    """The whole reason for a hook of its own - `attack_advantage` never gets here."""
    random.seed(3)
    character = _make_character(domain_cards_loadout=[INEVITABLE])
    target = _make_adversary()
    fight = _state([character], [target])
    fight.set_token(character, INEVITABLE_OWED, 1)

    roll = spellcast(character, target, fight)

    assert roll.advantage_state is AdvantageState.ADVANTAGE
    assert fight.token_count(character, INEVITABLE_OWED) == 0


def test_a_pc_without_the_card_rolls_flat():
    random.seed(3)
    character = _make_character(domain_cards_loadout=[])
    target = _make_adversary()
    fight = _state([character], [target])

    assert spellcast(character, target, fight).advantage_state is AdvantageState.NONE


# --- Rise Up -------------------------------------------------------------------


def test_rise_up_clears_a_stress_off_a_wound():
    character = _make_character(domain_cards_loadout=[RISE_UP])
    character.mark_stress(3)
    fight = _state([character], [])

    apply_on_damaged(character, 12, 2, fight)

    assert character.stress_marked == 2


def test_rise_up_ignores_a_hit_that_marked_no_hp():
    """An Armor Slot swallowing a hit whole is not a wound the card sees."""
    character = _make_character(domain_cards_loadout=[RISE_UP])
    character.mark_stress(3)
    fight = _state([character], [])

    apply_on_damaged(character, 12, 0, fight)

    assert character.stress_marked == 3


def test_rise_up_fires_on_damage_from_anything_at_all():
    """The user's ruling: everything that marks damage here is an attack.

    Nothing is spotlighted, so this wound has no attacker attached - a burn, an
    area spell, the party's own. The card fires anyway, and that is the reading
    rather than an oversight.
    """
    character = _make_character(domain_cards_loadout=[RISE_UP])
    character.mark_stress(1)
    fight = _state([character], [])
    assert fight.spotlighted is None

    apply_on_damaged(character, 5, 1, fight)

    assert character.stress_marked == 0


def test_rise_up_declares_its_threshold_clause_as_a_gap():
    """A sheet carries thresholds resolved, so running the bonus would double it."""
    assert assess(RISE_UP).is_partial is True
    assert "Severe threshold" in " ".join(assess(RISE_UP).unmodelled)


# --- Restoration ---------------------------------------------------------------


def test_restoration_stocks_its_spellcast_trait_in_tokens():
    caster = _make_character(domain_cards_loadout=[RESTORATION])
    hurt = _make_character(name="Hurt", domain_cards_loadout=[])
    hurt.mark_hp(6)  # 2 unmarked of 8
    fight = _state([caster, hurt], [], rest=Rest.LONG)

    use_free_abilities(caster, fight, limit=1)

    # Three to start (the caster's Knowledge), one spent on the touch.
    assert fight.token_count(caster, RESTORATION_TOKENS) == 2
    assert hurt.hp_marked == 4


def test_restoration_is_empty_without_a_long_rest():
    caster = _make_character(domain_cards_loadout=[RESTORATION])
    hurt = _make_character(name="Hurt", domain_cards_loadout=[])
    hurt.mark_hp(6)
    fight = _state([caster, hurt], [], rest=Rest.SHORT)

    use_free_abilities(caster, fight, limit=1)

    assert fight.token_count(caster, RESTORATION_TOKENS) == 0
    assert hurt.hp_marked == 6


def test_restoration_leaves_a_lightly_wounded_party_alone():
    """The trigger is 2 or fewer unmarked, not any mark at all."""
    caster = _make_character(domain_cards_loadout=[RESTORATION])
    dented = _make_character(name="Dented", domain_cards_loadout=[])
    dented.mark_hp(2)  # 6 unmarked of 8
    fight = _state([caster, dented], [], rest=Rest.LONG)

    use_free_abilities(caster, fight, limit=1)

    assert dented.hp_marked == 2
    assert fight.token_count(caster, RESTORATION_TOKENS) == 3


def test_restoration_takes_stress_when_that_is_the_track_in_trouble():
    caster = _make_character(domain_cards_loadout=[RESTORATION])
    strained = _make_character(name="Strained", domain_cards_loadout=[])
    strained.mark_stress(5)  # 1 unmarked of 6
    fight = _state([caster, strained], [], rest=Rest.LONG)

    use_free_abilities(caster, fight, limit=1)

    assert strained.stress_marked == 3


def test_a_token_lifts_a_condition_an_adversary_applied():
    caster = _make_character(domain_cards_loadout=[RESTORATION])
    held = _make_character(name="Held", domain_cards_loadout=[])
    fight = _state([caster, held], [], rest=Rest.LONG)
    fight.apply_condition(held, Condition(name=RESTRAINED, source=_make_adversary()))

    use_free_abilities(caster, fight, limit=1)

    assert fight.has_condition(held, RESTRAINED) is False
    assert fight.token_count(caster, RESTORATION_TOKENS) == 2


def test_a_token_never_lifts_a_condition_the_party_put_there():
    """Wild Fortress shelters two PCs on purpose; clearing that would be a bug."""
    caster = _make_character(domain_cards_loadout=[RESTORATION])
    sheltered = _make_character(name="Sheltered", domain_cards_loadout=[])
    fight = _state([caster, sheltered], [], rest=Rest.LONG)
    fight.apply_condition(sheltered, Condition(name=SHELTERED, source=caster))

    use_free_abilities(caster, fight, limit=1)

    assert fight.has_condition(sheltered, SHELTERED) is True
    assert fight.token_count(caster, RESTORATION_TOKENS) == 3


def test_restoration_needs_a_spellcast_trait():
    """It is a Spell, and the size of its pool is a number the PC doesn't have."""
    caster = _make_character(domain_cards_loadout=[RESTORATION], spellcast_trait="")
    hurt = _make_character(name="Hurt", domain_cards_loadout=[])
    hurt.mark_hp(6)
    fight = _state([caster, hurt], [], rest=Rest.LONG)

    use_free_abilities(caster, fight, limit=1)

    assert hurt.hp_marked == 6


# --- Zone of Protection ---------------------------------------------------------


def _cast_the_zone(caster, target, fight):
    """Raise the zone on a roll that certainly beats the printed 16."""
    with patch("content.spellcast.roll_duality", return_value=_roll(12, 11, 16)):
        return zone_of_protection(caster, target, fight)


def test_raising_the_zone_puts_the_die_at_one():
    caster = _make_character(domain_cards_loadout=[ZONE_OF_PROTECTION])
    target = _make_adversary()
    fight = _state([caster], [target], rest=Rest.LONG)

    result = _cast_the_zone(caster, target, fight)

    assert result is not None
    assert fight.token_count(caster, ZONE_DIE) == 1


def test_a_failed_cast_keeps_the_per_long_rest_use():
    """"Once per long rest **on a success**" - the page says so outright."""
    caster = _make_character(domain_cards_loadout=[ZONE_OF_PROTECTION])
    target = _make_adversary()
    fight = _state([caster], [target], rest=Rest.LONG)

    with patch("content.spellcast.roll_duality", return_value=_roll(2, 3, 16)):
        zone_of_protection(caster, target, fight)

    assert fight.token_count(caster, ZONE_DIE) == 0
    assert fight.can_use_once_per_rest(caster, ZONE_OF_PROTECTION, long=True) is True


def test_the_zone_declines_while_one_already_stands():
    caster = _make_character(domain_cards_loadout=[ZONE_OF_PROTECTION])
    target = _make_adversary()
    fight = _state([caster], [target], rest=Rest.LONG)
    fight.set_token(caster, ZONE_DIE, 3)

    assert _cast_the_zone(caster, target, fight) is None


def test_the_zone_soaks_the_dies_value_and_then_grows():
    caster = _make_character(domain_cards_loadout=[ZONE_OF_PROTECTION])
    allies = [_make_character(name=f"Ally {n}") for n in range(3)]
    fight = _state([caster, *allies], [], rest=Rest.LONG)
    fight.set_token(caster, ZONE_DIE, 3)

    with patch("random.random", return_value=0.0):  # certainly inside the band
        taken = party_damage_reduction(allies[0], 10, fight)

    assert taken == 3
    assert fight.token_count(caster, ZONE_DIE) == 4


def test_a_pc_outside_the_zone_is_not_covered_and_the_die_does_not_move():
    caster = _make_character(domain_cards_loadout=[ZONE_OF_PROTECTION])
    allies = [_make_character(name=f"Ally {n}") for n in range(3)]
    fight = _state([caster, *allies], [], rest=Rest.LONG)
    fight.set_token(caster, ZONE_DIE, 3)

    with patch("random.random", return_value=0.99):  # certainly outside
        taken = party_damage_reduction(allies[0], 10, fight)

    assert taken == 0
    assert fight.token_count(caster, ZONE_DIE) == 3


def test_the_zone_fades_after_the_hit_it_reduces_by_six():
    caster = _make_character(domain_cards_loadout=[ZONE_OF_PROTECTION])
    allies = [_make_character(name=f"Ally {n}") for n in range(3)]
    fight = _state([caster, *allies], [], rest=Rest.LONG)
    fight.set_token(caster, ZONE_DIE, 6)

    with patch("random.random", return_value=0.0):
        taken = party_damage_reduction(allies[0], 20, fight)

    assert taken == 6
    assert fight.token_count(caster, ZONE_DIE) == 0


def test_the_zone_reduces_before_the_thresholds_are_read():
    """Which is what makes the die worth more than its face."""
    caster = _make_character(domain_cards_loadout=[ZONE_OF_PROTECTION])
    allies = [_make_character(name=f"Ally {n}") for n in range(3)]
    fight = _state([caster, *allies], [], rest=Rest.LONG)
    fight.set_token(caster, ZONE_DIE, 4)

    with patch("random.random", return_value=0.0):
        # 12 is over the ally's Major threshold of 9 and would mark 2 HP; the
        # zone takes it to 8, which marks 1.
        marked = allies[0].take_damage(12, fight)

    assert marked == 1
