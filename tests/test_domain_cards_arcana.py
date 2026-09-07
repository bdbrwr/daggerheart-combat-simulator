"""Tests for the Arcana domain cards.

Seven cards run across levels 1 to 8, and each reaches the fight by a different
route: Rune Ward is a damage reduction asked of the whole party, Unleash Chaos is
an action with a token pool, Cinder Grasp leaves a condition behind that goes on
costing the target after the spell has resolved, and the level 7 and 8 pair
answer incoming attacks rather than making them.

Two pieces of shared machinery are what several of these are really about:

* **`spellcast_bonus`** reaches a Spellcast Roll and *not* a weapon swing, which
  is the whole reason it exists rather than Arcana-Touched using `roll_bonus`.
* **`Condition.untargetable`** reaches the GM's targeting rule, so a cloaked PC is
  not chosen - and the whole party being cloaked falls back rather than leaving an
  adversary with nobody to hit.

The readings pinned down here are the ones the module documents as choices:
Arcana-Touched switching only a *successful* roll with Fear, the cloak surviving
the spotlight that raised it and breaking on the next roll, Arcane Reflection
emptying the Hope pool on Counterspell's trigger and dealing the damage back, and
Confusing Aura buying two extra layers a Stress at a time and losing one per
attack it turns away.

The dice are pinned wherever a case is about a decision rather than a roll -
`randint` for the Ward Die, a Difficulty of 0 for a spell that has to land, and a
patched `content.spellcast.roll_duality` where a card casts against a printed
Difficulty.
"""

import random
from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.fight import _take_pc_spotlight
from combat.policy import choose_adversary_target
from combat.rest import Rest
from combat.state import FightState
from content import (
    Status,
    apply_on_roll,
    assess,
    party_damage_reduction,
    remake_action_roll,
    total_roll_bonus,
    total_spellcast_bonus,
)
from content.conditions import (
    CLOAKED,
    ON_A_GM_TURN,
    ON_FIRE,
    WHEN_THEY_ACT,
    WHEN_THEY_ATTACK,
    Condition,
    when_they_attack,
)
from content.damage_types import DamageType
from content.spellcast import spellcast
from dice.common import AdvantageState
from dice.damage import DiceGroup
from dice.duality import DualityRollResult
from domain_cards.arcana import (
    ARCANA_TOUCHED,
    ARCANE_REFLECTION,
    CASTING,
    CHAOS_PRIMED,
    CHAOS_TOKENS,
    CLOAKING_BLAST,
    CONFUSING_AURA,
    CONFUSING_AURA_LAYERS,
    WARD_SPENT,
    cinder_grasp,
    confusing_aura,
    rune_ward,
    unleash_chaos,
)

RUNE_WARD = "Rune Ward"
UNLEASH_CHAOS = "Unleash Chaos"
CINDER_GRASP = "Cinder Grasp"


def _make_level_2_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Aeloria",
        level=2,
        # Invented, so nothing else on the sheet reaches into these numbers.
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 0,
            "strength": 0,
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
        hp_max=7,
        stress_max=6,
        hope_max=6,
        hope_marked=6,
        armor_max=0,  # off unless a case is about armor
        primary_weapon="Greatstaff",
        secondary_weapon=None,
        armor_item="Gambeson Armor",
        domain_cards_loadout=[],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
    )
    defaults.update(overrides)
    return PlayerCharacter(**defaults)


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


def _make_level_8_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=8,
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 3,
            "strength": 1,
            "finesse": 2,
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
        # No armor item, deliberately: several cases here go through
        # `party_damage_reduction`, and an armor feature registered on a hook in
        # the same path would sit in the middle of what is being measured.
        armor_item="",
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


# --- Rune Ward ---------------------------------------------------------------


def test_the_ward_takes_its_die_off_a_hit_that_could_drop_a_band():
    caster = _make_level_2_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_level_2_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([caster, ally], [])

    with patch("domain_cards.arcana.random.randint", return_value=5):
        taken = rune_ward(caster, ally, 10, state)

    assert taken == 5
    assert ally.hope_marked == 5  # the *holder* pays


def test_the_ward_ignores_a_hit_it_could_not_move():
    """30 damage is nowhere near a threshold an 8 could carry it under."""
    caster = _make_level_2_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_level_2_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([caster, ally], [])

    assert rune_ward(caster, ally, 30, state) == 0
    assert ally.hope_marked == 6


def test_the_ward_fires_on_a_hit_it_could_take_away_entirely():
    """Under 8 damage, any Ward Die big enough leaves nothing to mark."""
    caster = _make_level_2_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_level_2_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([caster, ally], [])

    with patch("domain_cards.arcana.random.randint", return_value=7):
        assert rune_ward(caster, ally, 6, state) == 7


def test_a_ward_die_of_eight_reduces_this_hit_and_then_burns_out():
    caster = _make_level_2_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_level_2_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([caster, ally], [])

    with patch("domain_cards.arcana.random.randint", return_value=8):
        first = rune_ward(caster, ally, 10, state)
    second = rune_ward(caster, ally, 10, state)

    assert first == 8
    assert second == 0
    assert state.token_count(caster, WARD_SPENT) == 1


def test_the_ward_protects_its_holder_and_nobody_else():
    caster = _make_level_2_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_level_2_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([caster, ally], [])

    with patch("domain_cards.arcana.random.randint", return_value=5):
        assert rune_ward(caster, caster, 10, state) == 0
    assert caster.hope_marked == 6


def test_a_caster_with_no_ally_keeps_the_trinket_in_their_pocket():
    """Ruled: it goes to somebody else, so a lone PC can never use it."""
    caster = _make_level_2_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    state = _state([caster], [])

    assert rune_ward(caster, caster, 10, state) == 0
    assert caster.hope_marked == 6


def test_the_ward_needs_a_hope_from_whoever_holds_it():
    caster = _make_level_2_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_level_2_pc(name="Guardian", domain_cards_loadout=[], hope_marked=0)
    state = _state([caster, ally], [])

    assert rune_ward(caster, ally, 10, state) == 0


def test_the_reduction_lands_before_the_thresholds():
    """The whole point of the hook: 10 is Major, and 10 less 5 is not."""
    caster = _make_level_2_pc(name="Wizard", domain_cards_loadout=[RUNE_WARD])
    ally = _make_level_2_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([caster, ally], [])

    with patch("domain_cards.arcana.random.randint", return_value=5):
        marked = ally.take_damage(10, state)

    assert marked == 1  # Major (2 HP) without the ward


def test_a_party_without_the_card_takes_the_hit_in_full():
    ally = _make_level_2_pc(name="Guardian", domain_cards_loadout=[])
    state = _state([ally], [])

    assert ally.take_damage(10, state) == 2


# --- Unleash Chaos -----------------------------------------------------------


def test_the_card_opens_full_and_spends_everything():
    random.seed(3)
    caster = _make_level_2_pc(domain_cards_loadout=[UNLEASH_CHAOS])
    target = _make_adversary()
    state = _state([caster], [target])

    result = unleash_chaos(caster, target, state)

    # Tokens equal to the Spellcast trait, which is knowledge 3.
    assert result.damage_roll.dice_groups[0] == DiceGroup(count=3, sides=10)
    assert state.token_count(caster, CHAOS_TOKENS) == 0
    assert caster.stress_marked == 0


def test_a_second_cast_marks_a_stress_to_refill():
    random.seed(3)
    caster = _make_level_2_pc(domain_cards_loadout=[UNLEASH_CHAOS])
    target = _make_adversary()
    state = _state([caster], [target])

    unleash_chaos(caster, target, state)
    result = unleash_chaos(caster, target, state)

    assert result.damage_roll.dice_groups[0] == DiceGroup(count=3, sides=10)
    assert caster.stress_marked == 1


def test_an_empty_card_declines_when_the_stress_rule_says_no():
    caster = _make_level_2_pc(domain_cards_loadout=[UNLEASH_CHAOS], stress_max=2)
    caster.mark_stress(1)  # last slot, and the PC is healthy
    target = _make_adversary()
    state = _state([caster], [target])
    state.set_token(caster, CHAOS_PRIMED, 1)
    state.set_token(caster, CHAOS_TOKENS, 0)

    assert unleash_chaos(caster, target, state) is None
    assert caster.stress_marked == 1


def test_a_caster_with_no_spellcast_trait_declines():
    caster = _make_level_2_pc(spellcast_trait="", domain_cards_loadout=[UNLEASH_CHAOS])
    target = _make_adversary()
    state = _state([caster], [target])

    assert unleash_chaos(caster, target, state) is None


def test_a_spellcast_trait_of_zero_has_no_tokens_to_place():
    caster = _make_level_2_pc(
        domain_cards_loadout=[UNLEASH_CHAOS],
        traits={
            "agility": 0,
            "strength": 0,
            "finesse": 0,
            "instinct": 0,
            "presence": 0,
            "knowledge": 0,
        },
    )
    target = _make_adversary()
    state = _state([caster], [target])

    assert unleash_chaos(caster, target, state) is None


# --- Cinder Grasp and On Fire ------------------------------------------------


def test_cinder_grasp_burns_the_target_and_leaves_it_alight():
    random.seed(3)
    caster = _make_level_2_pc(domain_cards_loadout=[CINDER_GRASP])
    target = _make_adversary()
    state = _state([caster], [target])

    result = cinder_grasp(caster, target, state)

    assert result.damage_roll.dice_groups[0] == DiceGroup(count=1, sides=20)
    assert target.hp_marked > 0
    assert state.has_condition(target, ON_FIRE) is True


def test_on_fire_costs_its_holder_every_time_they_act():
    random.seed(3)
    caster = _make_level_2_pc(domain_cards_loadout=[CINDER_GRASP])
    target = _make_adversary()
    state = _state([caster], [target])

    cinder_grasp(caster, target, state)
    before = target.hp_marked
    state.apply_condition_effects(target, WHEN_THEY_ACT)

    assert target.hp_marked > before


def test_a_creature_that_is_not_acting_does_not_burn():
    random.seed(3)
    caster = _make_level_2_pc(domain_cards_loadout=[CINDER_GRASP])
    target = _make_adversary()
    state = _state([caster], [target])

    cinder_grasp(caster, target, state)
    before = target.hp_marked
    state.apply_condition_effects(target, ON_A_GM_TURN)

    assert target.hp_marked == before


def test_the_gm_can_pay_a_fear_to_put_the_fire_out():
    random.seed(3)
    caster = _make_level_2_pc(domain_cards_loadout=[CINDER_GRASP])
    target = _make_adversary()
    state = _state([caster], [target], fear=3)

    cinder_grasp(caster, target, state)
    ended = state.expire_conditions(target, ON_A_GM_TURN)

    assert ON_FIRE in ended
    assert state.fear == 2


def test_a_gm_with_no_fear_watches_it_burn():
    random.seed(3)
    caster = _make_level_2_pc(domain_cards_loadout=[CINDER_GRASP])
    target = _make_adversary()
    state = _state([caster], [target], fear=0)

    cinder_grasp(caster, target, state)

    assert state.expire_conditions(target, ON_A_GM_TURN) == []
    assert state.has_condition(target, ON_FIRE) is True


# --- Arcana-Touched ----------------------------------------------------------


def test_the_spellcast_bonus_reaches_a_cast():
    caster = _make_level_7_pc(domain_cards_loadout=[ARCANA_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    assert total_spellcast_bonus(caster, target, fight) == 1


def test_the_spellcast_bonus_does_not_reach_a_weapon_swing():
    """The whole reason for a hook of its own rather than `roll_bonus`."""
    caster = _make_level_7_pc(domain_cards_loadout=[ARCANA_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    assert total_roll_bonus(caster, target, fight) == 0


def test_the_bonus_lands_in_the_spellcast_roll():
    caster = _make_level_7_pc(domain_cards_loadout=[ARCANA_TOUCHED])
    target = _make_adversary()
    fight = _state([caster], [target])

    roll = spellcast(caster, target, fight)

    # Knowledge 2, plus the card's 1.
    assert roll.modifier == 3


def test_the_dice_switch_on_a_successful_roll_with_fear():
    holder = _make_level_7_pc(domain_cards_loadout=[ARCANA_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    switched = remake_action_roll(holder, _roll(4, 11, difficulty=12), lambda: None, fight)

    assert switched.hope_die_result == 11
    assert switched.fear_die_result == 4
    # The total is untouched - only which die won has changed.
    assert switched.total == 15
    assert switched.is_success is True


def test_the_switch_is_declined_on_a_failure():
    """Ruled: a failure passes the spotlight regardless, so the use is kept."""
    holder = _make_level_7_pc(domain_cards_loadout=[ARCANA_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    roll = _roll(3, 5, difficulty=20)
    assert remake_action_roll(holder, roll, lambda: None, fight) is roll
    assert fight.can_use_once_per_rest(holder, ARCANA_TOUCHED) is True


def test_the_switch_is_declined_on_a_roll_that_already_came_up_with_hope():
    holder = _make_level_7_pc(domain_cards_loadout=[ARCANA_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    roll = _roll(11, 4, difficulty=12)
    assert remake_action_roll(holder, roll, lambda: None, fight) is roll


def test_the_switch_is_once_per_rest():
    holder = _make_level_7_pc(domain_cards_loadout=[ARCANA_TOUCHED])
    fight = _state([holder], [], rest=Rest.LONG)

    remake_action_roll(holder, _roll(4, 11, difficulty=12), lambda: None, fight)
    second = _roll(4, 11, difficulty=12)

    assert remake_action_roll(holder, second, lambda: None, fight) is second


# --- Cloaking Blast ----------------------------------------------------------


def test_a_successful_cast_cloaks_the_caster_for_a_hope():
    caster = _make_level_7_pc(domain_cards_loadout=[CLOAKING_BLAST])
    target = _make_adversary()
    fight = _state([caster], [target])

    spellcast(caster, target, fight)  # sets the "a cast is in flight" token
    apply_on_roll(caster, _roll(9, 4, difficulty=5), fight)

    assert fight.has_condition(caster, CLOAKED) is True
    assert caster.hope_marked == 5


def test_a_weapon_swing_never_cloaks():
    """`on_roll` fires for every action roll; only a cast leaves the token."""
    caster = _make_level_7_pc(domain_cards_loadout=[CLOAKING_BLAST])
    fight = _state([caster], [])

    apply_on_roll(caster, _roll(9, 4, difficulty=5), fight)

    assert fight.has_condition(caster, CLOAKED) is False
    assert caster.hope_marked == 6


def test_a_failed_cast_clears_the_token_without_cloaking():
    caster = _make_level_7_pc(domain_cards_loadout=[CLOAKING_BLAST])
    target = _make_adversary()
    fight = _state([caster], [target])

    spellcast(caster, target, fight)
    apply_on_roll(caster, _roll(2, 3, difficulty=20), fight)

    assert fight.has_condition(caster, CLOAKED) is False
    assert fight.token_count(caster, CASTING) == 0


def test_a_cloaked_pc_is_not_chosen_as_a_target():
    hidden = _make_level_7_pc(name="Hidden")
    plain = _make_level_7_pc(name="Plain")
    adversary = _make_adversary()
    fight = _state([hidden, plain], [adversary])
    fight.last_pc_to_attack = hidden
    fight.apply_condition(
        hidden, Condition(name=CLOAKED, source=hidden, untargetable=True)
    )

    assert choose_adversary_target(adversary, fight) is plain


def test_a_wholly_cloaked_party_is_still_targetable():
    """A cloak protects an individual, not the party - see `_targetable`."""
    alone = _make_level_7_pc(name="Alone")
    adversary = _make_adversary()
    fight = _state([alone], [adversary])
    fight.apply_condition(
        alone, Condition(name=CLOAKED, source=alone, untargetable=True)
    )

    assert choose_adversary_target(adversary, fight) is alone


def test_the_cloak_survives_the_spotlight_that_raised_it():
    """The ordering that makes the card work at all.

    The moment that breaks a cloak is announced before the roll's outcome is
    spent, and the cloak is applied by that outcome - so a cast that was itself an
    attack does not break the cloak it just raised.

    Carrying no primary weapon leaves Bolt Beacon as the only option the shuffle
    can reach, which is what makes the spotlight certainly a cast rather than a
    swing. `_take_pc_spotlight` is the loop function that announces the moment.
    """
    random.seed(5)
    caster = _make_level_7_pc(
        domain_cards_loadout=[CLOAKING_BLAST, "Bolt Beacon"], primary_weapon=""
    )
    target = _make_adversary()
    fight = _state([caster], [target])

    _take_pc_spotlight(fight)

    assert fight.has_condition(caster, CLOAKED) is True


def test_the_cloak_breaks_on_the_next_action_roll():
    """Through the card's real ender, not a stand-in for it."""
    caster = _make_level_7_pc(domain_cards_loadout=[CLOAKING_BLAST])
    fight = _state([caster], [])
    fight.apply_condition(
        caster,
        Condition(
            name=CLOAKED,
            end=when_they_attack,
            source=caster,
            untargetable=True,
        ),
    )

    # A spotlight that resolved into no roll leaves it alone...
    fight.expire_conditions(caster, WHEN_THEY_ACT)
    assert fight.has_condition(caster, CLOAKED) is True

    # ...and one that made a roll ends it.
    fight.expire_conditions(caster, WHEN_THEY_ATTACK)
    assert fight.has_condition(caster, CLOAKED) is False


def test_the_cloak_is_not_re_bought_while_one_stands():
    caster = _make_level_7_pc(domain_cards_loadout=[CLOAKING_BLAST])
    target = _make_adversary()
    fight = _state([caster], [target])

    spellcast(caster, target, fight)
    apply_on_roll(caster, _roll(9, 4, difficulty=5), fight)
    spellcast(caster, target, fight)
    apply_on_roll(caster, _roll(9, 4, difficulty=5), fight)

    assert caster.hope_marked == 5  # one Hope, not two


# --- Arcane Reflection -------------------------------------------------------


def _reflecting(**overrides):
    """A PC carrying Arcane Reflection, an adversary, and the spotlight on it."""
    pc = _make_level_8_pc(domain_cards_loadout=[ARCANE_REFLECTION], **overrides)
    adversary = _make_adversary()
    fight = _rested_state([pc], [adversary])
    fight.spotlighted = adversary
    return pc, adversary, fight


def test_arcane_reflection_negates_the_hit_and_deals_it_back_on_a_six():
    pc, adversary, fight = _reflecting()

    with patch("domain_cards.arcana.random.randint", return_value=6):
        lost = party_damage_reduction(pc, 12, fight, DamageType.MAGIC)

    assert lost == 12
    assert adversary.hp_marked > 0


def test_arcane_reflection_spends_every_banked_hope():
    pc, _, fight = _reflecting(hope_marked=4)

    with patch("domain_cards.arcana.random.randint", return_value=6) as rolled:
        party_damage_reduction(pc, 12, fight, DamageType.MAGIC)

    assert pc.hope_marked == 0
    assert rolled.call_count == 4


def test_arcane_reflection_spends_the_hope_even_when_no_six_comes_up():
    """The dice are what the Hope buys; the card says nothing about a refund."""
    pc, adversary, fight = _reflecting()

    with patch("domain_cards.arcana.random.randint", return_value=1):
        lost = party_damage_reduction(pc, 12, fight, DamageType.MAGIC)

    assert lost == 0
    assert pc.hope_marked == 0
    assert adversary.hp_marked == 0


def test_arcane_reflection_ignores_physical_damage():
    pc, _, fight = _reflecting()

    with patch("domain_cards.arcana.random.randint", return_value=6):
        assert party_damage_reduction(pc, 12, fight, DamageType.PHYSICAL) == 0
    assert pc.hope_marked == 6


def test_arcane_reflection_declines_a_hit_below_the_major_threshold():
    pc, _, fight = _reflecting()

    with patch("domain_cards.arcana.random.randint", return_value=6):
        assert party_damage_reduction(pc, 9, fight, DamageType.MAGIC) == 0


def test_arcane_reflection_answers_a_small_hit_while_near_death():
    pc, _, fight = _reflecting(hp_marked=7)

    with patch("domain_cards.arcana.random.randint", return_value=6):
        assert party_damage_reduction(pc, 3, fight, DamageType.MAGIC) == 3


def test_arcane_reflection_declines_with_no_hope_banked():
    pc, _, fight = _reflecting(hope_marked=0)

    assert party_damage_reduction(pc, 12, fight, DamageType.MAGIC) == 0


def test_arcane_reflection_declines_when_nothing_is_spotlighted():
    """Magic damage with no adversary acting is the party's own - On Fire."""
    pc, _, fight = _reflecting()
    fight.spotlighted = None

    assert party_damage_reduction(pc, 12, fight, DamageType.MAGIC) == 0
    assert pc.hope_marked == 6


def test_arcane_reflection_does_not_answer_for_an_ally():
    """'When **you** would take magic damage' - scoped to its own holder."""
    caster = _make_level_8_pc(domain_cards_loadout=[ARCANE_REFLECTION])
    ally = _make_level_8_pc(name="Ally")
    adversary = _make_adversary()
    fight = _rested_state([caster, ally], [adversary])
    fight.spotlighted = adversary

    with patch("domain_cards.arcana.random.randint", return_value=6):
        assert party_damage_reduction(ally, 12, fight, DamageType.MAGIC) == 0
    assert caster.hope_marked == 6


# --- Confusing Aura ----------------------------------------------------------


def _cast_aura(pc, fight, target, hope=10, fear=5):
    """Cast the aura through a fixed Spellcast Roll. 15 beats the printed 14."""
    with patch(
        "content.spellcast.roll_duality",
        return_value=_roll(hope=hope, fear=fear, difficulty=14),
    ):
        return confusing_aura(pc, target, fight)


def test_confusing_aura_raises_three_layers_when_the_stress_allows_two():
    pc = _make_level_8_pc(domain_cards_loadout=[CONFUSING_AURA])
    target = _make_adversary()
    fight = _rested_state([pc], [target])

    assert _cast_aura(pc, fight, target) is not None
    assert fight.token_count(pc, CONFUSING_AURA_LAYERS) == 3
    assert pc.stress_marked == 2


def test_confusing_aura_buys_one_extra_layer_when_the_last_slot_is_held_back():
    """The shared last-slot rule, asked per layer - Rage Up's shape."""
    pc = _make_level_8_pc(domain_cards_loadout=[CONFUSING_AURA], stress_marked=4)
    target = _make_adversary()
    fight = _rested_state([pc], [target])

    _cast_aura(pc, fight, target)

    assert fight.token_count(pc, CONFUSING_AURA_LAYERS) == 2
    assert pc.stress_marked == 5


def test_a_failed_cast_leaves_the_per_rest_use_available():
    """'Once per long rest **on a success**' gates the payoff, not the attempt."""
    pc = _make_level_8_pc(domain_cards_loadout=[CONFUSING_AURA])
    target = _make_adversary()
    fight = _rested_state([pc], [target])

    result = _cast_aura(pc, fight, target, hope=4, fear=3)  # 7 against 14

    assert result is not None and not result.attack_roll.is_success
    assert fight.token_count(pc, CONFUSING_AURA_LAYERS) == 0
    assert fight.can_use_once_per_rest(pc, CONFUSING_AURA, long=True)


def test_confusing_aura_declines_while_an_aura_already_stands():
    pc = _make_level_8_pc(domain_cards_loadout=[CONFUSING_AURA])
    target = _make_adversary()
    fight = _rested_state([pc], [target])
    fight.set_token(pc, CONFUSING_AURA_LAYERS, 1)

    assert _cast_aura(pc, fight, target) is None


def test_a_layer_tears_away_and_the_attack_finds_nothing():
    pc = _make_level_8_pc(domain_cards_loadout=[CONFUSING_AURA])
    fight = _rested_state([pc], [_make_adversary()])
    fight.set_token(pc, CONFUSING_AURA_LAYERS, 2)

    with patch("domain_cards.arcana.random.randint", return_value=5):
        lost = party_damage_reduction(pc, 14, fight, DamageType.PHYSICAL)

    assert lost == 14
    assert fight.token_count(pc, CONFUSING_AURA_LAYERS) == 1


def test_all_low_dice_end_the_spell_and_the_damage_lands():
    pc = _make_level_8_pc(domain_cards_loadout=[CONFUSING_AURA])
    fight = _rested_state([pc], [_make_adversary()])
    fight.set_token(pc, CONFUSING_AURA_LAYERS, 3)

    with patch("domain_cards.arcana.random.randint", return_value=4):
        lost = party_damage_reduction(pc, 14, fight, DamageType.PHYSICAL)

    assert lost == 0
    assert fight.token_count(pc, CONFUSING_AURA_LAYERS) == 0


def test_an_aura_worn_to_nothing_answers_no_further_hits():
    pc = _make_level_8_pc(domain_cards_loadout=[CONFUSING_AURA])
    fight = _rested_state([pc], [_make_adversary()])
    fight.set_token(pc, CONFUSING_AURA_LAYERS, 1)

    with patch("domain_cards.arcana.random.randint", return_value=6):
        assert party_damage_reduction(pc, 14, fight, DamageType.PHYSICAL) == 14
        assert party_damage_reduction(pc, 14, fight, DamageType.PHYSICAL) == 0


# --- Assessed and dismissed --------------------------------------------------


def test_the_two_utility_spells_are_declared_rather_than_absent():
    assert assess("Wall Walk").status.value == "no combat effect"
    assert assess("Floating Eye").status.value == "no combat effect"


def test_the_level_eight_pair_are_modelled():
    for card in (ARCANE_REFLECTION, CONFUSING_AURA):
        assert assess(card).status is Status.MODELLED
