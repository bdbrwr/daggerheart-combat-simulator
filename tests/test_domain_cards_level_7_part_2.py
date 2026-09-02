"""Tests for the level 7 cards of Codex, Grace and Midnight.

Four cards run and two are declarations. The batch's machinery is what most of
these are really about, and all three pieces reach places nothing had touched:

* **`stress_instead_of_hp`** changes which track an adversary's wound lands on,
  which means `Adversary.take_damage` now has a step between the severity hooks
  and the marking. The cases check that the HP reported onward is the *reduced*
  figure, since content keyed on "marks 2 or more HP" reads it.
* **`armor_instead_of_stress`** reaches `PlayerCharacter.spend_stress` itself, so
  it changes what **every** Stress cost in the project does for one PC. The cases
  pin the scope: only where the standing last-slot rule refuses.
* **`fear_conversion`** is the first thing that stops the GM gaining a Fear.

Determinism comes from constructing rolls with fixed dice and from a target with
a Difficulty of 0, so no case turns on whether an attack landed.
"""

from unittest.mock import Mock, patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.fight import _apply_duality_outcome
from combat.rest import Rest
from combat.state import FightState
from content import (
    apply_attack_missed,
    assess,
    marked_as_stress_instead,
    marks_armor_instead_of_stress,
    total_spellcast_bonus,
)
from content.conditions import HIDDEN
from dice.common import AdvantageState
from dice.damage import DiceGroup
from dice.duality import DualityRollResult
from domain_cards.codex import CODEX_TOUCHED, CODEX_TOUCHED_STRESS_CEILING
from domain_cards.grace import GRACE_TOUCHED
from domain_cards.midnight import MIDNIGHT_TOUCHED, VANISHING_DODGE

BOOK_OF_HOMET = "Book of Homet"
ENDLESS_CHARISMA = "Endless Charisma"


def _make_character(**overrides) -> PlayerCharacter:
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


def test_the_dismissed_pair_are_declared_with_reasons():
    for name in (BOOK_OF_HOMET, ENDLESS_CHARISMA):
        assert assess(name).status.value == "no combat effect"
        assert assess(name).reason


def test_the_book_is_declared_as_well_as_its_spells():
    """A Grimoire with no spell registered would report as unimplemented."""
    for name in (BOOK_OF_HOMET, "Pass Through", "Plane Gate"):
        assert assess(name).status.value == "no combat effect"


# --- Codex-Touched -------------------------------------------------------------


def test_the_stress_buys_the_casters_whole_proficiency():
    caster = _make_character(domain_cards_loadout=[CODEX_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    assert total_spellcast_bonus(caster, target, fight) == 3
    assert caster.stress_marked == 1


def test_the_ceiling_stops_it_rather_than_the_last_slot_rule():
    """Three marked of six - the shared rule would still allow this one."""
    caster = _make_character(domain_cards_loadout=[CODEX_TOUCHED])
    caster.mark_stress(CODEX_TOUCHED_STRESS_CEILING)
    target = _make_adversary()
    fight = _state([caster], [target])

    assert caster.will_spend_stress(1) is True  # the standing rule says yes
    assert total_spellcast_bonus(caster, target, fight) == 0  # the ceiling says no
    assert caster.stress_marked == CODEX_TOUCHED_STRESS_CEILING


def test_three_casts_are_bought_and_then_no_more():
    caster = _make_character(domain_cards_loadout=[CODEX_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    bought = [total_spellcast_bonus(caster, target, fight) for _ in range(5)]

    assert bought == [3, 3, 3, 0, 0]


# --- Grace-Touched: the Armor Slot ---------------------------------------------


def test_the_permission_is_registered():
    holder = _make_character(domain_cards_loadout=[GRACE_TOUCHED])

    assert marks_armor_instead_of_stress(holder, 1) is True
    assert marks_armor_instead_of_stress(_make_character(), 1) is False


def test_armor_is_not_touched_while_stress_is_comfortable():
    """The scope of the ruling: it unlocks a refusal, it doesn't replace Stress."""
    holder = _make_character(domain_cards_loadout=[GRACE_TOUCHED], armor_max=3)

    assert holder.spend_stress(1) is True
    assert holder.stress_marked == 1
    assert holder.armor_marked == 0


def test_armor_pays_for_the_last_stress_slot():
    holder = _make_character(domain_cards_loadout=[GRACE_TOUCHED], armor_max=3)
    holder.mark_stress(5)  # one slot left, and the PC is not near death

    assert holder.will_spend_stress(1) is True
    assert holder.spend_stress(1) is True
    assert holder.stress_marked == 5  # the Stress was not marked
    assert holder.armor_marked == 1


def test_armor_pays_when_the_stress_track_is_full():
    holder = _make_character(domain_cards_loadout=[GRACE_TOUCHED], armor_max=3)
    holder.mark_stress(6)

    assert holder.spend_stress(1) is True
    assert holder.armor_marked == 1


def test_without_armor_the_standing_rule_stands():
    holder = _make_character(domain_cards_loadout=[GRACE_TOUCHED], armor_max=0)
    holder.mark_stress(5)

    assert holder.will_spend_stress(1) is False


def test_a_pc_without_the_card_is_unchanged():
    holder = _make_character(armor_max=3)
    holder.mark_stress(5)

    assert holder.will_spend_stress(1) is False
    assert holder.armor_marked == 0


# --- Grace-Touched: the wound taken as Stress ----------------------------------


def test_a_wound_lands_on_stress_instead():
    caster = _make_character(domain_cards_loadout=[GRACE_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    marked = target.take_damage(12, fight)  # over Major, so 2 HP

    assert marked == 0
    assert target.hp_marked == 0
    assert target.stress_marked == 2


def test_the_hp_reported_onward_is_the_reduced_figure():
    """Content keyed on "marks 2 or more HP" has to see what actually landed."""
    caster = _make_character(domain_cards_loadout=[GRACE_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    assert target.take_damage(5, fight) == 0


def test_an_adversary_near_death_takes_the_hp():
    caster = _make_character(domain_cards_loadout=[GRACE_TOUCHED])
    target = _make_adversary()
    target.mark_hp(10)  # 2 unmarked of 12
    fight = _state([caster], [target])

    target.take_damage(5, fight)

    assert target.hp_marked == 11
    assert target.stress_marked == 0


def test_a_full_stress_track_sends_the_wound_back_to_hp():
    caster = _make_character(domain_cards_loadout=[GRACE_TOUCHED])
    target = _make_adversary()
    target.mark_stress(3)
    fight = _state([caster], [target])

    target.take_damage(5, fight)

    assert target.hp_marked == 1


def test_a_wound_bigger_than_the_track_is_split():
    caster = _make_character(domain_cards_loadout=[GRACE_TOUCHED])
    target = _make_adversary(stress_max=1)
    fight = _state([caster], [target])

    marked = target.take_damage(25, fight)  # Severe, so 3 HP

    assert target.stress_marked == 1
    assert target.hp_marked == 2
    assert marked == 2


def test_nothing_converts_without_the_card():
    target = _make_adversary()
    fight = _state([_make_character()], [target])

    assert marked_as_stress_instead(target, 2, fight) == 0


# --- Midnight-Touched ----------------------------------------------------------


def test_the_gm_gains_no_fear_and_the_pc_gains_a_hope():
    holder = _make_character(domain_cards_loadout=[MIDNIGHT_TOUCHED], hope_marked=0)
    fight = _state([holder], [], rest=Rest.LONG)

    _apply_duality_outcome(holder, _roll(3, 9, difficulty=20), fight)

    assert fight.fear == 0
    assert holder.hope_marked == 1


def test_the_fear_lands_normally_when_the_pc_has_hope():
    holder = _make_character(domain_cards_loadout=[MIDNIGHT_TOUCHED], hope_marked=2)
    fight = _state([holder], [], rest=Rest.LONG)

    _apply_duality_outcome(holder, _roll(3, 9, difficulty=20), fight)

    assert fight.fear == 1


def test_the_fear_conversion_is_once_per_rest():
    holder = _make_character(domain_cards_loadout=[MIDNIGHT_TOUCHED], hope_marked=0)
    fight = _state([holder], [], rest=Rest.LONG)

    _apply_duality_outcome(holder, _roll(3, 9, difficulty=20), fight)
    holder.spend_hope(1)  # back to 0 Hope
    _apply_duality_outcome(holder, _roll(3, 9, difficulty=20), fight)

    assert fight.fear == 1


def _swing(loadout, roll, **overrides):
    """Swing a Broadsword on a fixed roll; return the flat damage modifier and the PC.

    The modifier is read off the `roll_damage` call rather than off the damage,
    since what the card adds is a number and any total can come from any dice.
    """
    holder = _make_character(domain_cards_loadout=loadout, **overrides)
    target = _make_adversary()
    fight = _state([holder], [target])

    from items.registry import find_weapon
    from items.weapons import attack_with

    with patch("items.weapons.roll_damage", return_value=Mock(total=5)) as rolled:
        with patch("items.weapons.roll_duality", return_value=roll):
            attack_with(holder, find_weapon("Broadsword"), target, fight=fight)

    return rolled.call_args.kwargs["modifier"], holder


LANDED = _roll(11, 9, difficulty=0)


def test_the_fear_die_is_added_to_a_landed_swing():
    """Whatever the weapon's own modifier is, plus the Fear Die showing 9."""
    with_card, _ = _swing([MIDNIGHT_TOUCHED], LANDED)
    without, _ = _swing([], LANDED)

    assert with_card == without + LANDED.fear_die_result


def test_the_fear_die_costs_a_stress():
    _, holder = _swing([MIDNIGHT_TOUCHED], LANDED)

    assert holder.stress_marked == 1


def test_the_fear_die_is_held_back_at_the_last_stress_slot():
    """The shared rule, like every other PC Stress cost."""
    with_card, holder = _swing(
        [MIDNIGHT_TOUCHED], LANDED, stress_max=2, stress_marked=1
    )
    without, _ = _swing([], LANDED)

    assert with_card == without
    assert holder.stress_marked == 1


# --- Vanishing Dodge -----------------------------------------------------------


def test_a_failed_physical_attack_buys_shadow():
    holder = _make_character(domain_cards_loadout=[VANISHING_DODGE])
    attacker = _make_adversary()
    fight = _state([holder], [attacker])

    apply_attack_missed(holder, attacker, _roll(2, 3), fight)

    assert fight.has_condition(holder, HIDDEN) is True
    assert holder.hope_marked == 5


def test_a_magic_attacker_is_not_dodged():
    """"An attack ... that would deal physical damage" - read off the stat block."""
    holder = _make_character(domain_cards_loadout=[VANISHING_DODGE])
    attacker = _make_adversary(damage_type="magic")
    fight = _state([holder], [attacker])

    apply_attack_missed(holder, attacker, _roll(2, 3), fight)

    assert fight.has_condition(holder, HIDDEN) is False
    assert holder.hope_marked == 6


def test_the_dodge_is_not_bought_twice_over():
    holder = _make_character(domain_cards_loadout=[VANISHING_DODGE])
    attacker = _make_adversary()
    fight = _state([holder], [attacker])

    apply_attack_missed(holder, attacker, _roll(2, 3), fight)
    apply_attack_missed(holder, attacker, _roll(2, 3), fight)

    assert holder.hope_marked == 5


def test_no_hope_means_no_dodge():
    holder = _make_character(domain_cards_loadout=[VANISHING_DODGE], hope_marked=0)
    attacker = _make_adversary()
    fight = _state([holder], [attacker])

    apply_attack_missed(holder, attacker, _roll(2, 3), fight)

    assert fight.has_condition(holder, HIDDEN) is False


# --- A printed damage type has to be parsed before it is read -------------------


def test_a_printed_damage_type_is_read_as_a_type_and_not_as_letters():
    """`Adversary.damage_type` is the string a catalogue entry wrote.

    Handing it straight to `types_in` gives a set of *characters*, which no
    `DamageType` is a member of - so a check written that way silently answers
    False for every adversary in the catalogue. Hush's `_casts_with_magic` had
    exactly that bug and stopped nobody acting; this pins both readings.
    """
    from content.damage_types import DamageType, damage_type_named, includes, types_in

    printed = _make_adversary(damage_type="magic").type_of_damage()

    assert isinstance(printed, str)
    assert DamageType.MAGIC not in types_in(printed)  # the bug
    assert includes(damage_type_named(printed), DamageType.MAGIC)  # the fix


def test_hush_stops_an_adversary_whose_printed_attack_is_magic():
    from domain_cards.midnight import _casts_with_magic

    assert _casts_with_magic(_make_adversary(damage_type="magic")) is True
    assert _casts_with_magic(_make_adversary(damage_type="physical")) is False


def test_a_dual_typed_attacker_counts_as_physical_for_the_dodge():
    """The Spellblade's "phy/mag" satisfies a physical restriction - the standing rule."""
    holder = _make_character(domain_cards_loadout=[VANISHING_DODGE])
    attacker = _make_adversary(damage_type="phy/mag")
    fight = _state([holder], [attacker])

    apply_attack_missed(holder, attacker, _roll(2, 3), fight)

    assert fight.has_condition(holder, HIDDEN) is True
