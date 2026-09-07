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

from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.state import FightState
from content import Status, assess, total_spellcast_bonus
from content.conditions import ON_A_GM_TURN, VULNERABLE, Condition
from content.damage_types import DamageType
from dice.common import AdvantageState
from dice.damage import DiceGroup
from dice.duality import DualityRollResult
from domain_cards.codex import (
    BOOK_OF_RONIN,
    BOOK_OF_YARROW,
    MAGIC_IMMUNE,
    MAGIC_IMMUNITY_HOPE,
    TRANSCENDENT_UNION,
    TRANSCENDENT_UNION_HOPE,
    UNION_STANDING,
    magic_immunity,
    magic_immunity_holds,
    transcendent_union,
    transcendent_union_bears,
    CODEX_TOUCHED,
    CODEX_TOUCHED_STRESS_CEILING,
    DISINTEGRATION_CEILING,
    DISINTEGRATION_DIFFICULTY,
    DISINTEGRATION_WAVE,
    ETERNAL_ENERVATION,
    disintegration_wave,
    eternal_enervation,
)

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


def _rested_state(party, adversaries, **overrides) -> FightState:
    """A fight the party walked into off a long rest, for the per-rest cards."""
    overrides.setdefault("rest", Rest.LONG)
    return _state(party, adversaries, **overrides)


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


def _landing(difficulty: int):
    """Patch the shared cast so a printed-Difficulty spell definitely succeeds."""
    return patch(
        "content.spellcast.roll_duality",
        return_value=_roll(12, 11, difficulty=difficulty),
    )


def _failing(difficulty: int):
    return patch(
        "content.spellcast.roll_duality",
        return_value=_roll(2, 3, difficulty=difficulty),
    )


def _the_whole_field():
    """Pin the Far band open, so a case is about the card and not the spread.

    Far reaches everyone, **or one short a quarter of the time** - and a draw
    below that share is the short case, so this passes 0.99 rather than the 0.0
    the `_bunched` helpers elsewhere use for bands whose best case is the low
    draw. Without it a two-adversary case silently becomes a one-adversary case
    a quarter of the time, and `targets_in_area` drops the *second* of the two,
    since equally wounded adversaries keep their list order.
    """
    return patch("content.aoe.random.random", return_value=0.99)


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


# --- Eternal Enervation (Book of Ronin) ---------------------------------------


def _enervating(*hit_points: int, **overrides):
    caster = _make_level_7_pc(
        level=9, domain_cards_loadout=[BOOK_OF_RONIN], **overrides
    )
    field = [
        _make_adversary(name=f"Dummy {index}", hp_max=points)
        for index, points in enumerate(hit_points)
    ]
    return caster, field, _rested_state([caster], field)


def test_the_enervation_goes_on_the_toughest_adversary():
    """The user's rule for a lasting mark - the opposite of focus fire."""
    caster, field, fight = _enervating(6, 12)

    eternal_enervation(caster, field[0], fight)

    assert fight.has_condition(field[1], VULNERABLE) is True
    assert fight.has_condition(field[0], VULNERABLE) is False


def test_the_enervation_is_permanent():
    """No ender at all, so a GM turn cannot pay it off the way it pays off others."""
    caster, field, fight = _enervating(12)
    fight.fear = 6

    eternal_enervation(caster, field[0], fight)
    ended = fight.expire_conditions(field[0], ON_A_GM_TURN)

    assert ended == []
    assert fight.has_condition(field[0], VULNERABLE) is True
    assert fight.fear == 6  # nothing was spent trying


def test_the_enervation_skips_a_target_already_vulnerable():
    caster, field, fight = _enervating(12, 6)
    fight.apply_condition(field[0], Condition(name=VULNERABLE))

    eternal_enervation(caster, field[0], fight)

    # The tough one is already Vulnerable, so the spell finds the other.
    assert fight.has_condition(field[1], VULNERABLE) is True


def test_a_failed_enervation_keeps_the_per_rest_use():
    """The roll is pinned rather than the target made hard.

    `_failing` builds a result whose own `difficulty` field is what decides
    success, so the number passed here is the one the roll is measured against -
    the dummies this file uses have a Difficulty of 0 and nothing can miss them.
    """
    caster, field, fight = _enervating(12)

    with _failing(20):
        eternal_enervation(caster, field[0], fight)

    assert fight.has_condition(field[0], VULNERABLE) is False
    assert fight.can_use_once_per_rest(caster, ETERNAL_ENERVATION, long=True) is True


def test_the_enervation_is_once_per_long_rest():
    caster, field, fight = _enervating(12, 12)

    assert eternal_enervation(caster, field[0], fight) is not None
    assert eternal_enervation(caster, field[0], fight) is None


# --- Disintegration Wave ------------------------------------------------------


def _disintegrating(*adversaries, **overrides):
    """`adversaries` are (hp_max, difficulty) pairs."""
    caster = _make_level_7_pc(
        level=9, domain_cards_loadout=[DISINTEGRATION_WAVE], **overrides
    )
    field = [
        _make_adversary(name=f"Dummy {index}", hp_max=points, difficulty=difficulty)
        for index, (points, difficulty) in enumerate(adversaries)
    ]
    return caster, field, _rested_state([caster], field)


def test_the_wave_unmakes_one_adversary_per_stress():
    caster, field, fight = _disintegrating((5, 10), (5, 10), (5, 10))

    with _the_whole_field(), _landing(DISINTEGRATION_DIFFICULTY):
        result = disintegration_wave(caster, field[0], fight)

    assert result is not None
    assert all(adversary.is_defeated for adversary in field)
    assert caster.stress_marked == 3


def test_the_wave_stops_where_the_shared_stress_rule_stops():
    """Six eligible, six slots - the last is held back while the caster is healthy."""
    caster, field, fight = _disintegrating(*[(5, 10)] * 6)

    with _the_whole_field(), _landing(DISINTEGRATION_DIFFICULTY):
        disintegration_wave(caster, field[0], fight)

    assert sum(1 for adversary in field if adversary.is_defeated) == 5
    assert caster.stress_marked == 5


def test_the_wave_takes_the_toughest_first():
    """Four of six marked leaves exactly one Stress the shared rule will spend.

    Five marked would leave none: paying the last slot needs the PC at 2 or fewer
    unmarked HP, so the card would decline before rolling rather than killing one.
    """
    caster, field, fight = _disintegrating((4, 10), (12, 10), stress_marked=4)

    with _the_whole_field(), _landing(DISINTEGRATION_DIFFICULTY):
        disintegration_wave(caster, field[0], fight)

    # The one Stress goes on the adversary damage would take longest to remove.
    assert field[1].is_defeated is True
    assert field[0].is_defeated is False
    assert caster.stress_marked == 5


def test_an_adversary_above_the_ceiling_is_not_on_the_list():
    caster, field, fight = _disintegrating(
        (5, DISINTEGRATION_CEILING), (5, DISINTEGRATION_CEILING + 1)
    )

    with _the_whole_field(), _landing(DISINTEGRATION_DIFFICULTY):
        disintegration_wave(caster, field[0], fight)

    assert field[0].is_defeated is True
    assert field[1].is_defeated is False


def test_the_wave_kills_without_dealing_damage():
    """No threshold is read, so thresholds nothing could cross are irrelevant."""
    caster, field, fight = _disintegrating((5, 10))
    field[0].major_threshold = 1000
    field[0].severe_threshold = 2000

    with _landing(DISINTEGRATION_DIFFICULTY):
        disintegration_wave(caster, field[0], fight)

    assert field[0].is_defeated is True


def test_a_failed_cast_keeps_the_per_rest_use_and_the_stress():
    caster, field, fight = _disintegrating((5, 10))

    with _failing(DISINTEGRATION_DIFFICULTY):
        result = disintegration_wave(caster, field[0], fight)

    assert result is not None and not result.attack_roll.is_success
    assert field[0].is_defeated is False
    assert caster.stress_marked == 0
    assert fight.can_use_once_per_rest(caster, DISINTEGRATION_WAVE, long=True) is True


def test_the_wave_declines_when_no_stress_can_be_paid():
    """The standing zero-benefit rule - the use is never spent on nothing."""
    caster, field, fight = _disintegrating((5, 10), stress_marked=5)
    caster.mark_hp(0)  # healthy, so the last slot is held back

    assert disintegration_wave(caster, field[0], fight) is None
    assert fight.can_use_once_per_rest(caster, DISINTEGRATION_WAVE, long=True) is True


# --- Magic Immunity (Book of Yarrow) -----------------------------------------


def _immunising(kind: str = "magic", **overrides):
    caster = _make_level_7_pc(
        level=10, domain_cards_loadout=[BOOK_OF_YARROW], **overrides
    )
    adversary = _make_adversary(damage_type=kind)
    return caster, adversary, _rested_state([caster], [adversary])


def test_immunity_is_bought_against_a_field_that_deals_magic():
    caster, _, fight = _immunising("magic")

    assert magic_immunity(caster, fight) is True
    assert caster.hope_marked == 6 - MAGIC_IMMUNITY_HOPE
    assert fight.token_count(caster, MAGIC_IMMUNE) == 1


def test_immunity_is_declined_against_a_field_that_deals_physical():
    """Five Hope against the wrong field would buy nothing at all."""
    caster, _, fight = _immunising("physical")

    assert magic_immunity(caster, fight) is False
    assert caster.hope_marked == 6


def test_immunity_declines_without_the_five_hope():
    caster, _, fight = _immunising("magic", hope_marked=4)

    assert magic_immunity(caster, fight) is False


def test_the_whole_magic_hit_is_returned():
    """Immunity rather than resistance, so nothing of it lands."""
    caster, _, fight = _immunising("magic")
    magic_immunity(caster, fight)

    assert magic_immunity_holds(caster, caster, 12, fight, DamageType.MAGIC) == 12


def test_physical_damage_still_lands_on_an_immune_caster():
    caster, _, fight = _immunising("magic")
    magic_immunity(caster, fight)

    assert magic_immunity_holds(caster, caster, 12, fight, DamageType.PHYSICAL) == 0


def test_the_immunity_never_answers_for_an_ally():
    caster, _, fight = _immunising("magic")
    ally = _make_level_7_pc(level=10, name="Ally")
    magic_immunity(caster, fight)

    assert magic_immunity_holds(caster, ally, 12, fight, DamageType.MAGIC) == 0


# --- Transcendent Union ------------------------------------------------------


def _uniting(*unmarked: int, **overrides):
    """A caster plus one PC per entry, each already down to that many unmarked HP."""
    caster = _make_level_7_pc(
        level=10, name="Wizard", domain_cards_loadout=[TRANSCENDENT_UNION], **overrides
    )
    party = [caster]
    for index, left in enumerate(unmarked):
        pc = _make_level_7_pc(level=10, name=f"Ally {index}")
        pc.mark_hp(pc.hp_max - left)
        party.append(pc)
    return caster, party, _rested_state(party, [_make_adversary()])


def test_the_union_costs_five_hope_and_holds():
    caster, party, fight = _uniting(8)

    assert transcendent_union(caster, fight) is True
    assert caster.hope_marked == 6 - TRANSCENDENT_UNION_HOPE
    assert fight.token_count(caster, UNION_STANDING) == 1


def test_the_union_declines_for_a_lone_pc():
    """"On two or more willing creatures" - a union of one is nobody to share with."""
    caster, party, fight = _uniting()

    assert transcendent_union(caster, fight) is False


def test_the_union_declines_without_the_five_hope():
    caster, party, fight = _uniting(8, hope_marked=4)

    assert transcendent_union(caster, fight) is False


def test_the_wound_goes_to_whoever_can_best_carry_it():
    caster, party, fight = _uniting(2)
    transcendent_union(caster, fight)
    hurt = party[1]

    assert transcendent_union_bears(caster, hurt, 2, fight) is caster


def test_the_bearer_is_offered_the_same_choice_and_picks_itself():
    """What makes the transfer terminate rather than bouncing back and forth."""
    caster, party, fight = _uniting(2)
    transcendent_union(caster, fight)

    assert transcendent_union_bears(caster, caster, 2, fight) is None


def test_the_union_reaches_the_real_marking_path():
    caster, party, fight = _uniting(2)
    transcendent_union(caster, fight)
    hurt = party[1]

    hurt.mark_hp_and_check_death(2, fight)

    assert hurt.hp_marked == hurt.hp_max - 2  # unchanged
    assert caster.hp_marked == 2


def test_nothing_moves_without_a_union():
    caster, party, fight = _uniting(2)
    hurt = party[1]

    hurt.mark_hp_and_check_death(2, fight)

    assert hurt.hp_marked == hurt.hp_max
    assert caster.hp_marked == 0


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


def test_the_level_nine_pair_are_assessed():
    assert assess(BOOK_OF_RONIN).status is Status.MODELLED
    assert assess(DISINTEGRATION_WAVE).status is Status.MODELLED
    assert assess("Transform").status is Status.NO_COMBAT_EFFECT
    assert assess("Transform").reason


def test_the_level_ten_pair_are_assessed():
    assert assess(BOOK_OF_YARROW).status is Status.MODELLED
    assert assess(TRANSCENDENT_UNION).status is Status.MODELLED
    assert assess("Timejammer").status is Status.NO_COMBAT_EFFECT
    assert assess("Timejammer").reason


def test_the_book_declares_the_spell_it_does_not_run():
    """A partial Grimoire says which of its spells is missing from the fight."""
    assert assess(BOOK_OF_RONIN).is_partial is True
    assert "Transform" in " ".join(assess(BOOK_OF_RONIN).unmodelled)
