"""Tests for the level 8 cards of Arcana, Blade and Bone - the first of level 8.

Six cards, five modelled, and two pieces of machinery they are mostly about:

* **`ally_attack_advantage`**, party content that hands *another PC's* attack
  Advantage. Battle Cry is the only thing that could not be written without it -
  every other advantage hook is scoped to whoever is swinging.
* **`Condition.denies_armor`**, read through `FightState.armor_is_denied` at the
  one point `take_damage` would mark a free slot. A field rather than a hook,
  which is what `prevents_action` and `untargetable` already are.

The readings pinned down here are the ones the modules document as choices:
Arcane Reflection emptying the Hope pool on Counterspell's trigger and dealing
the damage back, Confusing Aura buying two extra layers a Stress at a time and
losing one per attack it turns away, Battle Cry giving everything away and
keeping none of it, Frenzy waiting for the armor to be gone, and Breaking Blow's
2d12 going to whoever hits the marked creature next.

Determinism comes from a target with a Difficulty of 0 so no case turns on
whether an attack landed, from patching `content.spellcast.roll_duality` where a
card makes a cast against a printed Difficulty, and from patching the
module-level `random` where a card rolls dice of its own.
"""

from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.results import AttackResult
from combat.state import FightState
from content import (
    Status,
    ally_granted_attack_advantage,
    apply_ally_on_roll,
    apply_on_hit,
    assess,
    party_damage_reduction,
    soften_damage,
    total_ally_extra_damage,
    total_damage_bonus,
    use_free_abilities,
)
from content.conditions import FRENZIED, Condition
from content.damage_types import DamageType
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from domain_cards.arcana import (
    ARCANE_REFLECTION,
    CONFUSING_AURA,
    CONFUSING_AURA_LAYERS,
    confusing_aura,
)
from domain_cards.blade import (
    BATTLE_CRY,
    BATTLE_CRY_RALLIED,
    FRENZY,
    FRENZY_DAMAGE,
)
from domain_cards.bone import BREAKING_BLOW, BREAKING_BLOW_CHARGE


def _make_character(**overrides) -> PlayerCharacter:
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
        # `soften_damage`, and an armor feature registered on the same hook would
        # sit in the middle of what is being measured.
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
    overrides.setdefault("rest", Rest.LONG)
    return FightState(
        encounter_name="Test", party=party, adversaries=adversaries, **overrides
    )


def _roll(hope: int, fear: int, difficulty: int) -> DualityRollResult:
    """A duality result with fixed dice, for cases that must not turn on luck."""
    return DualityRollResult(
        hope_die_result=hope,
        fear_die_result=fear,
        modifier=0,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=difficulty,
    )


def _landed_hit() -> AttackResult:
    """An attack that hit for something, for the on-hit riders to read."""
    return AttackResult(
        attack_roll=_roll(hope=9, fear=4, difficulty=5),
        damage_roll=DamageRollResult(
            dice_groups=[DiceGroup(count=1, sides=4)],
            die_results=[[4]],
            modifier=0,
        ),
        hp_marked=1,
    )


# --- Arcane Reflection ------------------------------------------------------------


def _reflecting(**overrides):
    """A PC carrying Arcane Reflection, an adversary, and the spotlight on it."""
    pc = _make_character(domain_cards_loadout=[ARCANE_REFLECTION], **overrides)
    adversary = _make_adversary()
    fight = _state([pc], [adversary])
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
    caster = _make_character(domain_cards_loadout=[ARCANE_REFLECTION])
    ally = _make_character(name="Ally")
    adversary = _make_adversary()
    fight = _state([caster, ally], [adversary])
    fight.spotlighted = adversary

    with patch("domain_cards.arcana.random.randint", return_value=6):
        assert party_damage_reduction(ally, 12, fight, DamageType.MAGIC) == 0
    assert caster.hope_marked == 6


# --- Confusing Aura ---------------------------------------------------------------


def _cast_aura(pc, fight, target, hope=10, fear=5):
    """Cast the aura through a fixed Spellcast Roll. 15 beats the printed 14."""
    with patch(
        "content.spellcast.roll_duality",
        return_value=_roll(hope=hope, fear=fear, difficulty=14),
    ):
        return confusing_aura(pc, target, fight)


def test_confusing_aura_raises_three_layers_when_the_stress_allows_two():
    pc = _make_character(domain_cards_loadout=[CONFUSING_AURA])
    target = _make_adversary()
    fight = _state([pc], [target])

    assert _cast_aura(pc, fight, target) is not None
    assert fight.token_count(pc, CONFUSING_AURA_LAYERS) == 3
    assert pc.stress_marked == 2


def test_confusing_aura_buys_one_extra_layer_when_the_last_slot_is_held_back():
    """The shared last-slot rule, asked per layer - Rage Up's shape."""
    pc = _make_character(domain_cards_loadout=[CONFUSING_AURA], stress_marked=4)
    target = _make_adversary()
    fight = _state([pc], [target])

    _cast_aura(pc, fight, target)

    assert fight.token_count(pc, CONFUSING_AURA_LAYERS) == 2
    assert pc.stress_marked == 5


def test_a_failed_cast_leaves_the_per_rest_use_available():
    """'Once per long rest **on a success**' gates the payoff, not the attempt."""
    pc = _make_character(domain_cards_loadout=[CONFUSING_AURA])
    target = _make_adversary()
    fight = _state([pc], [target])

    result = _cast_aura(pc, fight, target, hope=4, fear=3)  # 7 against 14

    assert result is not None and not result.attack_roll.is_success
    assert fight.token_count(pc, CONFUSING_AURA_LAYERS) == 0
    assert fight.can_use_once_per_rest(pc, CONFUSING_AURA, long=True)


def test_confusing_aura_declines_while_an_aura_already_stands():
    pc = _make_character(domain_cards_loadout=[CONFUSING_AURA])
    target = _make_adversary()
    fight = _state([pc], [target])
    fight.set_token(pc, CONFUSING_AURA_LAYERS, 1)

    assert _cast_aura(pc, fight, target) is None


def test_a_layer_tears_away_and_the_attack_finds_nothing():
    pc = _make_character(domain_cards_loadout=[CONFUSING_AURA])
    fight = _state([pc], [_make_adversary()])
    fight.set_token(pc, CONFUSING_AURA_LAYERS, 2)

    with patch("domain_cards.arcana.random.randint", return_value=5):
        lost = party_damage_reduction(pc, 14, fight, DamageType.PHYSICAL)

    assert lost == 14
    assert fight.token_count(pc, CONFUSING_AURA_LAYERS) == 1


def test_all_low_dice_end_the_spell_and_the_damage_lands():
    pc = _make_character(domain_cards_loadout=[CONFUSING_AURA])
    fight = _state([pc], [_make_adversary()])
    fight.set_token(pc, CONFUSING_AURA_LAYERS, 3)

    with patch("domain_cards.arcana.random.randint", return_value=4):
        lost = party_damage_reduction(pc, 14, fight, DamageType.PHYSICAL)

    assert lost == 0
    assert fight.token_count(pc, CONFUSING_AURA_LAYERS) == 0


def test_an_aura_worn_to_nothing_answers_no_further_hits():
    pc = _make_character(domain_cards_loadout=[CONFUSING_AURA])
    fight = _state([pc], [_make_adversary()])
    fight.set_token(pc, CONFUSING_AURA_LAYERS, 1)

    with patch("domain_cards.arcana.random.randint", return_value=6):
        assert party_damage_reduction(pc, 14, fight, DamageType.PHYSICAL) == 14
        assert party_damage_reduction(pc, 14, fight, DamageType.PHYSICAL) == 0


# --- Battle Cry -------------------------------------------------------------------


def _crying_party():
    crier = _make_character(
        name="Crier", domain_cards_loadout=[BATTLE_CRY], stress_marked=2, hope_marked=1
    )
    ally = _make_character(name="Ally", stress_marked=2, hope_marked=1)
    fight = _state([crier, ally], [_make_adversary()])
    return crier, ally, fight


def test_battle_cry_pays_the_allies_and_not_the_crier():
    crier, ally, fight = _crying_party()

    assert use_free_abilities(crier, fight, 1) == [BATTLE_CRY]
    assert (ally.stress_marked, ally.hope_marked) == (1, 2)
    assert (crier.stress_marked, crier.hope_marked) == (2, 1)


def test_battle_cry_declines_for_a_pc_with_no_allies():
    """Every effect is scoped to allies, so with none the use would buy nothing."""
    crier = _make_character(domain_cards_loadout=[BATTLE_CRY])
    fight = _state([crier], [_make_adversary()])

    assert use_free_abilities(crier, fight, 1) == []
    assert fight.can_use_once_per_rest(crier, BATTLE_CRY, long=True)


def test_battle_cry_is_once_per_long_rest():
    crier, _, fight = _crying_party()

    assert use_free_abilities(crier, fight, 1) == [BATTLE_CRY]
    assert use_free_abilities(crier, fight, 1) == []


def test_a_rallied_ally_swings_with_advantage():
    crier, ally, fight = _crying_party()
    use_free_abilities(crier, fight, 1)

    state = ally_granted_attack_advantage(ally, fight.adversaries[0], fight)

    assert state is AdvantageState.ADVANTAGE


def test_the_crier_gains_no_advantage_of_their_own():
    crier, _, fight = _crying_party()
    use_free_abilities(crier, fight, 1)

    state = ally_granted_attack_advantage(crier, fight.adversaries[0], fight)

    assert state is AdvantageState.NONE


def test_a_failure_with_fear_ends_the_rally():
    crier, ally, fight = _crying_party()
    use_free_abilities(crier, fight, 1)

    apply_ally_on_roll(ally, _roll(hope=3, fear=9, difficulty=20), fight)

    assert not fight.token_count(crier, BATTLE_CRY_RALLIED)


def test_a_success_with_fear_leaves_the_rally_standing():
    crier, ally, fight = _crying_party()
    use_free_abilities(crier, fight, 1)

    apply_ally_on_roll(ally, _roll(hope=3, fear=9, difficulty=5), fight)

    assert fight.token_count(crier, BATTLE_CRY_RALLIED)


def test_the_criers_own_failure_with_fear_ends_their_rally():
    """'until **you** or an ally rolls a failure with Fear' - the crier counts."""
    crier, _, fight = _crying_party()
    use_free_abilities(crier, fight, 1)

    apply_ally_on_roll(crier, _roll(hope=3, fear=9, difficulty=20), fight)

    assert not fight.token_count(crier, BATTLE_CRY_RALLIED)


# --- Frenzy -----------------------------------------------------------------------


def test_frenzy_waits_while_an_armor_slot_is_still_free():
    pc = _make_character(domain_cards_loadout=[FRENZY], armor_max=3, armor_marked=2)
    fight = _state([pc], [_make_adversary()])

    assert use_free_abilities(pc, fight, 1) == []
    assert not fight.has_condition(pc, FRENZIED)


def test_frenzy_starts_once_every_armor_slot_is_marked():
    pc = _make_character(domain_cards_loadout=[FRENZY], armor_max=3, armor_marked=3)
    fight = _state([pc], [_make_adversary()])

    assert use_free_abilities(pc, fight, 1) == [FRENZY]
    assert fight.has_condition(pc, FRENZIED)


def test_a_pc_with_no_armor_at_all_frenzies_immediately():
    pc = _make_character(domain_cards_loadout=[FRENZY], armor_max=0)
    fight = _state([pc], [_make_adversary()])

    assert use_free_abilities(pc, fight, 1) == [FRENZY]


def test_frenzy_adds_ten_to_the_damage_roll():
    pc = _make_character(domain_cards_loadout=[FRENZY], armor_max=0)
    target = _make_adversary()
    fight = _state([pc], [target])

    assert total_damage_bonus(pc, target, fight) == 0
    use_free_abilities(pc, fight, 1)
    assert total_damage_bonus(pc, target, fight) == FRENZY_DAMAGE


def test_a_frenzied_pc_marks_no_armor_slot():
    """The condition's `denies_armor`, read at the one point a slot would go in."""
    pc = _make_character(armor_max=3)
    fight = _state([pc], [_make_adversary()])
    fight.apply_condition(pc, Condition(name=FRENZIED, denies_armor=True))

    marked = pc.take_damage(12, fight, damage_type=DamageType.PHYSICAL)

    assert pc.armor_marked == 0
    assert marked == 2  # Major, with nothing to soften it


def test_a_pc_who_is_not_frenzied_still_marks_their_armor():
    pc = _make_character(armor_max=3)
    fight = _state([pc], [_make_adversary()])

    marked = pc.take_damage(12, fight, damage_type=DamageType.PHYSICAL)

    assert pc.armor_marked == 1
    assert marked == 1


def test_frenzy_takes_a_band_off_a_hit_inside_the_severe_window():
    """A 20 clears the printed Severe threshold; 28 is the first that still does."""
    pc = _make_character(domain_cards_loadout=[FRENZY], armor_max=0)
    fight = _state([pc], [_make_adversary()])
    use_free_abilities(pc, fight, 1)

    assert soften_damage(pc, 20, 3, fight, DamageType.PHYSICAL) == 2
    assert soften_damage(pc, 27, 3, fight, DamageType.PHYSICAL) == 2


def test_frenzy_leaves_a_hit_above_the_window_severe():
    pc = _make_character(domain_cards_loadout=[FRENZY], armor_max=0)
    fight = _state([pc], [_make_adversary()])
    use_free_abilities(pc, fight, 1)

    assert soften_damage(pc, 28, 3, fight, DamageType.PHYSICAL) == 3


def test_frenzy_leaves_a_hit_below_the_severe_threshold_alone():
    pc = _make_character(domain_cards_loadout=[FRENZY], armor_max=0)
    fight = _state([pc], [_make_adversary()])
    use_free_abilities(pc, fight, 1)

    assert soften_damage(pc, 12, 2, fight, DamageType.PHYSICAL) == 2


def test_frenzy_does_nothing_before_it_is_entered():
    pc = _make_character(domain_cards_loadout=[FRENZY], armor_max=3, armor_marked=1)
    fight = _state([pc], [_make_adversary()])

    assert soften_damage(pc, 20, 3, fight, DamageType.PHYSICAL) == 3
    assert total_damage_bonus(pc, _make_adversary(), fight) == 0


# --- Breaking Blow ----------------------------------------------------------------


def test_breaking_blow_marks_a_stress_and_leaves_the_target_charged():
    pc = _make_character(domain_cards_loadout=[BREAKING_BLOW])
    target = _make_adversary()
    fight = _state([pc], [target])

    apply_on_hit(pc, target, _landed_hit(), fight)

    assert pc.stress_marked == 1
    assert fight.token_count(target, BREAKING_BLOW_CHARGE) == 1


def test_breaking_blow_declines_against_a_target_already_charged():
    pc = _make_character(domain_cards_loadout=[BREAKING_BLOW])
    target = _make_adversary()
    fight = _state([pc], [target])
    fight.set_token(target, BREAKING_BLOW_CHARGE, 1)

    apply_on_hit(pc, target, _landed_hit(), fight)

    assert pc.stress_marked == 0


def test_breaking_blow_declines_against_a_target_the_hit_just_defeated():
    pc = _make_character(domain_cards_loadout=[BREAKING_BLOW])
    target = _make_adversary(hp_max=1)
    target.hp_marked = 1
    fight = _state([pc], [target])

    apply_on_hit(pc, target, _landed_hit(), fight)

    assert pc.stress_marked == 0


def test_any_pcs_next_attack_collects_the_two_d12():
    """The charge is the Bone character's; the dice go to whoever hits next."""
    bone = _make_character(name="Bone", domain_cards_loadout=[BREAKING_BLOW])
    ally = _make_character(name="Ally")
    target = _make_adversary()
    fight = _state([bone, ally], [target])
    fight.set_token(target, BREAKING_BLOW_CHARGE, 1)

    groups = total_ally_extra_damage(ally, target, _landed_hit().attack_roll, fight)

    assert groups == [DiceGroup(count=2, sides=12, discardable=False)]
    assert fight.token_count(target, BREAKING_BLOW_CHARGE) == 0


def test_the_charge_pays_out_once():
    bone = _make_character(domain_cards_loadout=[BREAKING_BLOW])
    target = _make_adversary()
    fight = _state([bone], [target])
    fight.set_token(target, BREAKING_BLOW_CHARGE, 1)
    roll = _landed_hit().attack_roll

    assert total_ally_extra_damage(bone, target, roll, fight)
    assert total_ally_extra_damage(bone, target, roll, fight) == []


def test_an_uncharged_target_adds_no_dice():
    bone = _make_character(domain_cards_loadout=[BREAKING_BLOW])
    target = _make_adversary()
    fight = _state([bone], [target])

    assert total_ally_extra_damage(bone, target, _landed_hit().attack_roll, fight) == []


def test_a_charge_belongs_to_the_creature_rather_than_to_the_attack():
    """Two adversaries, one charged: the other collects nothing."""
    bone = _make_character(domain_cards_loadout=[BREAKING_BLOW])
    charged = _make_adversary(name="Charged")
    other = _make_adversary(name="Other")
    fight = _state([bone], [charged, other])
    fight.set_token(charged, BREAKING_BLOW_CHARGE, 1)
    roll = _landed_hit().attack_roll

    assert total_ally_extra_damage(bone, other, roll, fight) == []
    assert total_ally_extra_damage(bone, charged, roll, fight)


# --- Coverage ---------------------------------------------------------------------


def test_the_batch_is_assessed():
    modelled = [
        ARCANE_REFLECTION,
        CONFUSING_AURA,
        BATTLE_CRY,
        FRENZY,
        BREAKING_BLOW,
    ]
    assert all(assess(name).status is Status.MODELLED for name in modelled)
    assert assess("Wrangle").status is Status.NO_COMBAT_EFFECT
