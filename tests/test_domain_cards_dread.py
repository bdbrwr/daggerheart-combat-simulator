"""Tests for the Dread domain cards.

The domain's own shape is what most of these are about: **three of its first seven
cards pay out on a roll with Fear**, which nothing else in the project does, so
several cases exist only to pin which die or which condition a Hope roll and a
Fear roll each produce. Determinism comes from patching
`content.spellcast.roll_duality` with a roll whose Hope and Fear dice are chosen to
force the outcome, rather than from seeding.

Two pieces of existing machinery are used in ways they had not been, and those are
the cases worth reading first:

* **`ally_damage_reduction` carrying a third party's effect.** Blighting Strike
  halves an adversary's next successful attack. The halving belongs to neither
  combatant in that attack, so it reaches the hit through the party-wide reduction
  hook and finds the attacker through `fight.spotlighted` - which is why those
  cases set `spotlighted` by hand.
* **`force_reroll` rewriting rather than re-rolling.** Umbral Veil spends tokens
  *after* an attack roll is made, so it returns a copy of the resolved roll with a
  smaller modifier. The cases assert on the returned roll's total, not on a remake.

The rulings pinned down here are the ones the module documents as choices: the
failure cost paid in Hope before Stress, Umbral Veil raised at the first spotlight
with no Fear floor, Siphon Essence held until the caster has 2 Hit Points marked,
and Shared Trauma firing only to lift somebody out of near death.

From level 4 up, three more: Chains of Affliction reading its own per-GM-turn
tally of damage dealt rather than any printed number, Spectral Mist lifting per
person on that PC's next action roll, and Dread-Touched stopping at a Stress
ceiling instead of at the shared last-slot rule. Two cards deal damage with no
attack roll at all - Summon Horror and Darkfire - so their cases assert on what
`roll_damage` was asked for rather than on a roll that never happens.

`EVERY_DREAD_CARD` at the bottom is the whole domain, and the three cases over it
are the ones that would catch a card registered from the wrong module, a card
silently missing, or the registry failing to discover the module at all.
"""

from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.state import FightState
from combat.results import AttackResult
from content import (
    Status,
    ally_soften_damage,
    apply_ally_on_damaged,
    apply_ally_on_hit,
    apply_ally_on_spotlight,
    apply_on_hit,
    apply_on_roll,
    assess,
    dealt_damage_scaling,
    fear_is_converted,
    force_adversary_reroll,
    party_damage_reduction,
    soften_damage,
    total_extra_damage,
    total_roll_bonus,
)
from content.conditions import (
    BEFORE_AN_ACTION_ROLL,
    CHAINED,
    FEAR_FUELED,
    INCORPOREAL,
    ON_A_GM_TURN,
    RESTRAINED,
    VULNERABLE,
)
from content.damage_types import DamageType
from dice.common import AdvantageState
from dice.d20 import D20RollResult
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from domain_cards.dread import (
    AVATAR_OF_TERROR,
    BLIGHTED,
    BLIGHTING_FEAR_DIE,
    BLIGHTING_HOPE_DIE,
    BLIGHTING_STRIKE,
    CHAINS_OF_AFFLICTION,
    DAMNATION,
    DARKFIRE,
    DARKFIRE_DIFFICULTY,
    DARK_ARMY,
    DARK_ARMY_DIFFICULTY,
    DARK_ARMY_TOKENS,
    DIRE_STRIKE,
    DREAD_TOUCHED,
    DREAD_TOUCHED_STRESS_CEILING,
    ELDRITCH_FLESH,
    ELDRITCH_FLESH_HOPE,
    FIENDS,
    HIDEOUS_RETRIBUTION,
    INVOKE_TORMENT,
    JUMP_SCARE,
    SAVOR_THE_ANGUISH,
    SHARED_TRAUMA,
    SIPHON_ESSENCE,
    SIPHON_ESSENCE_HP_MARKED,
    SPECTRAL_MIST,
    SPECTRAL_MIST_HOPE,
    SUMMON_HORROR,
    SUMMON_HORROR_DIFFICULTY,
    TERRIFY,
    UMBRAL_VEIL,
    VEIL_TOKENS,
    VOICE_OF_DREAD,
    WALL_OF_HUNGER,
    WALL_OF_HUNGER_DIFFICULTY,
    WALL_OF_HUNGER_STRESS,
    avatar_of_terror,
    blighting_strike,
    chains_of_affliction,
    damnation,
    dark_army,
    darkfire,
    dire_strike,
    hideous_retribution,
    jump_scare,
    shared_trauma,
    siphon_essence,
    spectral_mist,
    summon_horror,
    terrify,
    umbral_veil,
    voice_of_dread,
    wall_of_hunger,
)


def _make_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Test PC",
        level=3,
        # Names nothing has implemented, on purpose: a class or subclass with
        # damage responses of its own would sit in the middle of what is measured.
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 1,
            "strength": 0,
            "finesse": 1,
            "instinct": 1,
            "presence": 1,
            "knowledge": 2,
        },
        evasion=11,
        proficiency=2,
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
        armor_item="",
        domain_cards_loadout=[],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
    )
    defaults.update(overrides)
    return PlayerCharacter(**defaults)


def _make_adversary(**overrides) -> Adversary:
    """Thresholds a hit can actually cross, so marked HP is a number a case reads."""
    defaults = dict(
        name="Dummy",
        tier=1,
        difficulty=0,  # every roll lands unless a case says otherwise
        major_threshold=5,
        severe_threshold=10,
        hp_max=50,
        stress_max=3,
        attack_modifier=0,
        damage_dice=[DiceGroup(count=1, sides=4)],
        damage_modifier=0,
    )
    defaults.update(overrides)
    return Adversary(**defaults)


def _state(party, adversaries, **overrides) -> FightState:
    return FightState(
        encounter_name="Test",
        party=list(party),
        adversaries=list(adversaries),
        **overrides,
    )


def _rested_state(party, adversaries, **overrides) -> FightState:
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


WITH_HOPE = _roll(9, 6, 5)  # total 15, succeeds, Hope wins
WITH_FEAR = _roll(6, 9, 5)  # total 15, succeeds, Fear wins
A_MISS = _roll(2, 3, 20)  # total 5, fails


def _casting(roll: DualityRollResult):
    return patch("content.spellcast.roll_duality", return_value=roll)


def _damage(total: int) -> DamageRollResult:
    return DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=8)], die_results=[[total]], modifier=0
    )


def _attack(die: int, modifier: int, evasion: int) -> D20RollResult:
    return D20RollResult(
        die_results=[die],
        modifier=modifier,
        advantage_state=AdvantageState.NONE,
        evasion=evasion,
    )


# --- Blighting Strike --------------------------------------------------------


def _striking(**overrides):
    caster = _make_pc(domain_cards_loadout=[BLIGHTING_STRIKE], **overrides)
    target = _make_adversary()
    return caster, target, _rested_state([caster], [target])


def _die_rolled(mock) -> int:
    """The size of the die the card asked `roll_damage` for."""
    return mock.call_args.kwargs["dice_groups"][0].sides


def test_a_roll_with_hope_rolls_the_smaller_die():
    caster, target, fight = _striking()

    with (
        _casting(WITH_HOPE),
        patch("domain_cards.dread.roll_damage", return_value=_damage(6)) as rolled,
    ):
        blighting_strike(caster, target, fight)

    assert _die_rolled(rolled) == BLIGHTING_HOPE_DIE


def test_a_roll_with_fear_rolls_the_bigger_die():
    """The card's whole oddity: the outcome that hands the GM a Fear hits harder."""
    caster, target, fight = _striking()

    with (
        _casting(WITH_FEAR),
        patch("domain_cards.dread.roll_damage", return_value=_damage(6)) as rolled,
    ):
        blighting_strike(caster, target, fight)

    assert _die_rolled(rolled) == BLIGHTING_FEAR_DIE


def test_a_landed_strike_blights_the_target():
    caster, target, fight = _striking()

    with (
        _casting(WITH_HOPE),
        patch("domain_cards.dread.roll_damage", return_value=_damage(6)),
    ):
        blighting_strike(caster, target, fight)

    assert fight.token_count(target, BLIGHTED) == 1


def test_a_target_the_strike_finished_is_not_blighted():
    """A debuff on a creature that is off the field is worth nothing."""
    caster, target, fight = _striking()
    target.hp_marked = target.hp_max - 1

    with (
        _casting(WITH_HOPE),
        patch("domain_cards.dread.roll_damage", return_value=_damage(40)),
    ):
        blighting_strike(caster, target, fight)

    assert target.is_defeated is True
    assert fight.token_count(target, BLIGHTED) == 0


def test_a_failed_strike_spends_a_hope():
    caster, target, fight = _striking()

    with _casting(A_MISS):
        result = blighting_strike(caster, target, fight)

    assert result.damage_roll is None
    assert caster.hope_marked == 5
    assert caster.stress_marked == 0


def test_a_failed_strike_with_no_hope_marks_a_stress():
    """Forced, not spent - so the last-slot rule does not hold it back."""
    caster, target, fight = _striking(hope_marked=0, stress_marked=5)

    with _casting(A_MISS):
        blighting_strike(caster, target, fight)

    assert caster.stress_marked == 6


def test_the_blight_halves_the_next_hit():
    caster, target, fight = _striking()
    fight.set_token(target, BLIGHTED, 1)
    fight.spotlighted = target

    # 9 halves to 4 - what survives is amount // 2, rounding down.
    assert party_damage_reduction(caster, 9, fight) == 5


def test_the_blight_is_spent_on_one_hit():
    caster, target, fight = _striking()
    fight.set_token(target, BLIGHTED, 1)
    fight.spotlighted = target

    party_damage_reduction(caster, 9, fight)

    assert fight.token_count(target, BLIGHTED) == 0
    assert party_damage_reduction(caster, 9, fight) == 0


def test_an_unblighted_adversary_swings_in_full():
    caster, target, fight = _striking()
    fight.spotlighted = target

    assert party_damage_reduction(caster, 9, fight) == 0


def test_damage_with_nobody_spotlighted_is_never_halved():
    """That damage is the party's own, and has no attacker to have been blighted."""
    caster, target, fight = _striking()
    fight.set_token(target, BLIGHTED, 1)

    assert fight.spotlighted is None
    assert party_damage_reduction(caster, 9, fight) == 0


# --- Umbral Veil -------------------------------------------------------------


def _veiling(fear: int = 5, **overrides):
    holder = _make_pc(domain_cards_loadout=[UMBRAL_VEIL], **overrides)
    target = _make_adversary()
    return holder, target, _rested_state([holder], [target], fear=fear)


def test_the_veil_is_worth_the_fear_in_the_pool():
    holder, _, fight = _veiling(fear=5)

    assert umbral_veil(holder, fight) is True
    assert fight.token_count(holder, VEIL_TOKENS) == 5
    assert holder.stress_marked == 1


def test_the_veil_declines_on_an_empty_pool():
    """Zero tokens would buy nothing at all - the standing zero-benefit rule."""
    holder, _, fight = _veiling(fear=0)

    assert umbral_veil(holder, fight) is False
    assert holder.stress_marked == 0


def test_the_veil_is_raised_once():
    holder, _, fight = _veiling()

    assert umbral_veil(holder, fight) is True
    assert umbral_veil(holder, fight) is False
    assert holder.stress_marked == 1


def test_the_veil_spends_the_fewest_tokens_that_make_a_miss():
    holder, adversary, fight = _veiling(fear=5)
    umbral_veil(holder, fight)

    # 14 against an Evasion of 11 is three over, so four tokens take it under.
    hit = _attack(die=12, modifier=2, evasion=11)
    replaced = force_adversary_reroll(adversary, holder, hit, lambda: hit, fight)

    assert replaced.is_success is False
    assert fight.token_count(holder, VEIL_TOKENS) == 1


def test_an_attack_that_already_missed_spends_nothing():
    holder, adversary, fight = _veiling()
    umbral_veil(holder, fight)

    missed = _attack(die=3, modifier=0, evasion=11)
    assert force_adversary_reroll(adversary, holder, missed, lambda: missed, fight) is missed
    assert fight.token_count(holder, VEIL_TOKENS) == 5


def test_a_hit_no_pool_could_reach_keeps_its_tokens():
    holder, adversary, fight = _veiling(fear=2)
    umbral_veil(holder, fight)

    far_over = _attack(die=19, modifier=0, evasion=11)
    force_adversary_reroll(adversary, holder, far_over, lambda: far_over, fight)

    assert fight.token_count(holder, VEIL_TOKENS) == 2


def test_a_critical_cannot_be_shaved_off():
    """A natural 20 succeeds regardless of Evasion, so no number of tokens helps."""
    holder, adversary, fight = _veiling(fear=12)
    umbral_veil(holder, fight)

    crit = _attack(die=20, modifier=0, evasion=11)
    force_adversary_reroll(adversary, holder, crit, lambda: crit, fight)

    assert fight.token_count(holder, VEIL_TOKENS) == 12


def test_the_veil_does_not_answer_an_attack_on_somebody_else():
    holder = _make_pc(name="Veiled", domain_cards_loadout=[UMBRAL_VEIL])
    ally = _make_pc(name="Ally")
    adversary = _make_adversary()
    fight = _rested_state([holder, ally], [adversary], fear=5)
    umbral_veil(holder, fight)

    hit = _attack(die=12, modifier=2, evasion=11)
    force_adversary_reroll(adversary, ally, hit, lambda: hit, fight)

    assert fight.token_count(holder, VEIL_TOKENS) == 5


# --- Voice of Dread ----------------------------------------------------------


def test_the_voice_forces_a_stress_and_restrains():
    caster = _make_pc(domain_cards_loadout=[VOICE_OF_DREAD])
    target = _make_adversary()
    fight = _rested_state([caster], [target], fear=3)

    with _casting(WITH_HOPE):
        result = voice_of_dread(caster, target, fight)

    assert result.damage_roll is None
    assert target.stress_marked == 1
    assert fight.has_condition(target, RESTRAINED) is True


def test_the_gm_pays_a_fear_to_shake_the_voice_off():
    caster = _make_pc(domain_cards_loadout=[VOICE_OF_DREAD])
    target = _make_adversary()
    fight = _rested_state([caster], [target], fear=3)

    with _casting(WITH_HOPE):
        voice_of_dread(caster, target, fight)

    assert fight.expire_conditions(target, ON_A_GM_TURN) == [RESTRAINED]
    assert fight.fear == 2


def test_the_voice_still_costs_a_stress_against_something_already_held():
    """Where the standing don't-re-apply rule would decline, this one does not."""
    caster = _make_pc(domain_cards_loadout=[VOICE_OF_DREAD])
    target = _make_adversary()
    fight = _rested_state([caster], [target], fear=3)

    with _casting(WITH_HOPE):
        voice_of_dread(caster, target, fight)
        voice_of_dread(caster, target, fight)

    assert target.stress_marked == 2


def test_a_failed_voice_costs_the_adversary_nothing():
    caster = _make_pc(domain_cards_loadout=[VOICE_OF_DREAD])
    target = _make_adversary(difficulty=20)
    fight = _rested_state([caster], [target], fear=3)

    with _casting(A_MISS):
        voice_of_dread(caster, target, fight)

    assert target.stress_marked == 0
    assert fight.has_condition(target, RESTRAINED) is False


# --- Hideous Retribution -----------------------------------------------------


def _retributing(**overrides):
    """Four PCs, because the Close band reaches nobody over a party of two."""
    holder = _make_pc(name="Dread", domain_cards_loadout=[HIDEOUS_RETRIBUTION], **overrides)
    allies = [_make_pc(name=f"Ally {index}") for index in range(3)]
    attacker = _make_adversary(difficulty=10)
    return holder, allies, attacker, _rested_state([holder, *allies], [attacker])


def _in_range():
    """The band reaching whoever the card is asking about, rather than a spread roll.

    Patches the draw the *card* makes, so it cannot be nested with
    `_the_whole_field` below - both end up patching `random.random` itself.
    """
    return patch("domain_cards.dread.random.random", return_value=0.0)


def _the_whole_field():
    """Every band at full reach. Far falls one short on a **low** draw, so 0.99."""
    return patch("content.aoe.random.random", return_value=0.99)


def test_the_reaction_hurts_the_adversary_that_hurt_an_ally():
    holder, allies, attacker, fight = _retributing()
    fight.spotlighted = attacker

    with (
        _in_range(),
        patch("domain_cards.dread.roll_duality", return_value=_roll(9, 6, 10)),
        patch("domain_cards.dread.roll_damage", return_value=_damage(6)),
    ):
        apply_ally_on_damaged(allies[0], 6, 1, fight)

    assert holder.stress_marked == 1
    assert attacker.hp_marked == 2  # 6 crosses the Major threshold of 5


def test_a_failed_reaction_costs_no_stress():
    holder, allies, attacker, fight = _retributing()
    fight.spotlighted = attacker

    with (
        _in_range(),
        patch("domain_cards.dread.roll_duality", return_value=_roll(2, 3, 10)),
        patch("domain_cards.dread.roll_damage") as rolled,
    ):
        apply_ally_on_damaged(allies[0], 6, 1, fight)

    assert holder.stress_marked == 0
    rolled.assert_not_called()


def test_the_holders_own_wound_is_not_an_allys():
    holder, allies, attacker, fight = _retributing()
    fight.spotlighted = attacker

    with (
        _in_range(),
        patch("domain_cards.dread.roll_duality", return_value=_roll(9, 6, 10)),
    ):
        apply_ally_on_damaged(holder, 6, 1, fight)

    assert holder.stress_marked == 0


def test_damage_with_nobody_spotlighted_is_not_answered():
    """It is the party's own, so there is no target to punish."""
    holder, allies, attacker, fight = _retributing()

    with (
        _in_range(),
        patch("domain_cards.dread.roll_duality", return_value=_roll(9, 6, 10)),
    ):
        apply_ally_on_damaged(allies[0], 6, 1, fight)

    assert holder.stress_marked == 0


# --- Siphon Essence ----------------------------------------------------------


def _siphoning(hp_marked: int, **overrides):
    caster = _make_pc(domain_cards_loadout=[SIPHON_ESSENCE], **overrides)
    caster.hp_marked = hp_marked
    target = _make_adversary()
    return caster, target, _rested_state([caster], [target])


def test_the_siphon_declines_on_a_healthy_caster():
    caster, target, fight = _siphoning(SIPHON_ESSENCE_HP_MARKED - 1)

    assert siphon_essence(caster, target, fight) is None
    assert fight.can_use_once_per_rest(caster, SIPHON_ESSENCE, long=True) is True


def test_the_siphon_clears_what_the_target_marked():
    caster, target, fight = _siphoning(4)

    with (
        _casting(WITH_HOPE),
        patch("domain_cards.dread.roll_damage", return_value=_damage(11)),
    ):
        result = siphon_essence(caster, target, fight)

    # 11 is over the Severe threshold of 10, so three Hit Points each way.
    assert result.hp_marked == 3
    assert target.hp_marked == 3
    assert caster.hp_marked == 1


def test_a_roll_with_fear_buys_an_extra_die():
    caster, target, fight = _siphoning(4)

    with (
        _casting(WITH_FEAR),
        patch("domain_cards.dread.roll_damage", return_value=_damage(6)) as rolled,
    ):
        siphon_essence(caster, target, fight)

    assert rolled.call_args.kwargs["dice_groups"][0].count == caster.proficiency + 1


def test_a_failed_siphon_keeps_the_per_rest_use():
    caster, target, fight = _siphoning(4)

    with _casting(A_MISS):
        siphon_essence(caster, target, fight)

    assert fight.can_use_once_per_rest(caster, SIPHON_ESSENCE, long=True) is True
    assert caster.hp_marked == 4


def test_the_siphon_is_once_per_long_rest():
    caster, target, fight = _siphoning(4)

    with (
        _casting(WITH_HOPE),
        patch("domain_cards.dread.roll_damage", return_value=_damage(11)),
    ):
        assert siphon_essence(caster, target, fight) is not None
        caster.hp_marked = 4
        assert siphon_essence(caster, target, fight) is None


# --- Shared Trauma -----------------------------------------------------------


def _sharing(receiver_marked: int, giver_marked: int = 0):
    holder = _make_pc(name="Dread", domain_cards_loadout=[SHARED_TRAUMA])
    ally = _make_pc(name="Ally")
    holder.hp_marked = receiver_marked
    ally.hp_marked = giver_marked
    return holder, ally, _rested_state([holder, ally], [])


def test_the_fewest_points_that_lift_somebody_clear_are_moved():
    # 7 of 8 marked is 1 unmarked; clear of near death is 3, so two points move.
    holder, ally, fight = _sharing(receiver_marked=7)

    assert shared_trauma(holder, fight) is True
    assert holder.hp_marked == 5
    assert ally.hp_marked == 2


def test_nothing_moves_while_everybody_is_healthy():
    holder, ally, fight = _sharing(receiver_marked=2)

    assert shared_trauma(holder, fight) is False
    assert holder.hp_marked == 2
    assert ally.hp_marked == 0


def test_nobody_is_pushed_into_near_death_to_save_somebody():
    """The giver has to stay clear of the band afterwards, or there is no giver."""
    holder, ally, fight = _sharing(receiver_marked=7, giver_marked=5)

    assert shared_trauma(holder, fight) is False
    assert holder.hp_marked == 7
    assert ally.hp_marked == 5


def test_the_transfer_is_once_per_rest():
    holder, ally, fight = _sharing(receiver_marked=7)

    assert shared_trauma(holder, fight) is True
    holder.hp_marked = 7
    ally.hp_marked = 0
    assert shared_trauma(holder, fight) is False


# --- Terrify -----------------------------------------------------------------


def _terrifying():
    caster = _make_pc(domain_cards_loadout=[TERRIFY])
    target = _make_adversary()
    return caster, target, _rested_state([caster], [target], fear=3)


def test_terrify_forces_a_die_of_stress():
    caster, target, fight = _terrifying()

    with (
        _casting(WITH_HOPE),
        patch("domain_cards.dread.random.randint", return_value=3),
    ):
        terrify(caster, target, fight)

    assert target.stress_marked == 3


def test_a_roll_with_hope_leaves_them_unvulnerable():
    caster, target, fight = _terrifying()

    with (
        _casting(WITH_HOPE),
        patch("domain_cards.dread.random.randint", return_value=2),
    ):
        terrify(caster, target, fight)

    assert fight.has_condition(target, VULNERABLE) is False


def test_a_roll_with_fear_also_makes_them_vulnerable():
    caster, target, fight = _terrifying()

    with (
        _casting(WITH_FEAR),
        patch("domain_cards.dread.random.randint", return_value=2),
    ):
        terrify(caster, target, fight)

    assert fight.has_condition(target, VULNERABLE) is True
    assert fight.expire_conditions(target, ON_A_GM_TURN) == [VULNERABLE]
    assert fight.fear == 2


def test_a_full_stress_track_overflows_into_a_hit_point():
    """The SRD's overflow rule applies on both sides - one HP, not one per Stress."""
    caster, target, fight = _terrifying()
    target.stress_marked = target.stress_max

    with (
        _casting(WITH_HOPE),
        patch("domain_cards.dread.random.randint", return_value=4),
    ):
        terrify(caster, target, fight)

    assert target.stress_marked == target.stress_max
    assert target.hp_marked == 1


# --- Chains of Affliction ----------------------------------------------------


def _chaining(**overrides):
    holder = _make_pc(domain_cards_loadout=[CHAINS_OF_AFFLICTION], **overrides)
    heavy = _make_adversary(name="Heavy")
    light = _make_adversary(name="Light")
    return holder, heavy, light, _rested_state([holder], [heavy, light])


def _dealt(fight, attacker, amount: int, holder) -> None:
    """One adversary hitting somebody, so the card's own tally sees it."""
    fight.spotlighted = attacker
    apply_ally_on_damaged(holder, amount, 1, fight)
    fight.spotlighted = None


def test_the_chain_declines_before_anything_has_attacked():
    """Nothing has hit yet, so there is no 'last GM turn' to read."""
    holder, heavy, light, fight = _chaining()

    assert chains_of_affliction(holder, fight) is False
    assert holder.stress_marked == 0


def test_the_chain_goes_on_whatever_hit_hardest():
    holder, heavy, light, fight = _chaining()
    _dealt(fight, light, 3, holder)
    _dealt(fight, heavy, 9, holder)

    assert chains_of_affliction(holder, fight) is True
    assert fight.has_condition(heavy, CHAINED) is True
    assert fight.has_condition(light, CHAINED) is False
    assert holder.stress_marked == 2


def test_an_adversary_that_attacked_an_earlier_turn_is_not_a_candidate():
    """Only the most recent turn counts, however hard the earlier one hit."""
    holder, heavy, light, fight = _chaining()
    _dealt(fight, heavy, 9, holder)
    fight.gm_turns = 1
    _dealt(fight, light, 3, holder)

    chains_of_affliction(holder, fight)

    assert fight.has_condition(light, CHAINED) is True
    assert fight.has_condition(heavy, CHAINED) is False


def test_only_one_creature_is_chained_at_a_time():
    holder, heavy, light, fight = _chaining()
    _dealt(fight, heavy, 9, holder)

    assert chains_of_affliction(holder, fight) is True
    assert chains_of_affliction(holder, fight) is False
    assert holder.stress_marked == 2


def test_a_chained_creatures_blow_costs_one_less_hit_point():
    holder, heavy, light, fight = _chaining()
    _dealt(fight, heavy, 9, holder)
    chains_of_affliction(holder, fight)
    fight.spotlighted = heavy

    assert ally_soften_damage(holder, 12, 2, fight) == 1


def test_an_unchained_creatures_blow_is_untouched():
    holder, heavy, light, fight = _chaining()
    _dealt(fight, heavy, 9, holder)
    chains_of_affliction(holder, fight)
    fight.spotlighted = light

    assert ally_soften_damage(holder, 12, 2, fight) == 2


def test_a_blow_already_marking_nothing_is_not_reduced_further():
    holder, heavy, light, fight = _chaining()
    _dealt(fight, heavy, 9, holder)
    chains_of_affliction(holder, fight)
    fight.spotlighted = heavy

    assert ally_soften_damage(holder, 4, 0, fight) == 0


# --- Summon Horror -----------------------------------------------------------


def _summoning(**overrides):
    holder = _make_pc(domain_cards_loadout=[SUMMON_HORROR], **overrides)
    target = _make_adversary()
    return holder, target, _rested_state([holder], [target])


def _saving(die: int):
    """The adversary's Reaction Roll, which is a flat d20 against a Difficulty."""
    return patch(
        "domain_cards.dread.roll_d20",
        return_value=_attack(die=die, modifier=0, evasion=SUMMON_HORROR_DIFFICULTY),
    )


def test_the_horror_deals_damage_with_no_roll_at_all():
    holder, target, fight = _summoning()

    with (
        patch("domain_cards.dread.roll_damage", return_value=_damage(6)) as rolled,
        _saving(die=18),
    ):
        assert summon_horror(holder, fight) is True

    assert target.hp_marked == 2  # 6 crosses the Major threshold of 5
    assert holder.stress_marked == 1
    # Dice equal to the Spellcast trait, not the Proficiency.
    assert rolled.call_args.kwargs["dice_groups"][0].count == holder.traits["knowledge"]


def test_a_failed_reaction_roll_forces_stress_equal_to_the_hit():
    holder, target, fight = _summoning()

    with (
        patch("domain_cards.dread.roll_damage", return_value=_damage(6)),
        _saving(die=2),
    ):
        summon_horror(holder, fight)

    assert target.stress_marked == 2  # equal to the Hit Points marked


def test_a_successful_reaction_roll_forces_none():
    holder, target, fight = _summoning()

    with (
        patch("domain_cards.dread.roll_damage", return_value=_damage(6)),
        _saving(die=18),
    ):
        summon_horror(holder, fight)

    assert target.stress_marked == 0


def test_the_horror_is_summoned_once_a_fight():
    holder, target, fight = _summoning()

    with (
        patch("domain_cards.dread.roll_damage", return_value=_damage(6)),
        _saving(die=18),
    ):
        assert summon_horror(holder, fight) is True
        assert summon_horror(holder, fight) is False

    assert holder.stress_marked == 1


def test_the_horror_declines_over_an_empty_field():
    holder = _make_pc(domain_cards_loadout=[SUMMON_HORROR])
    fight = _rested_state([holder], [])

    assert summon_horror(holder, fight) is False


# --- Dire Strike -------------------------------------------------------------


def _a_landed_hit(hp_marked: int = 1) -> AttackResult:
    return AttackResult(
        attack_roll=WITH_HOPE, damage_roll=_damage(6), hp_marked=hp_marked
    )


def test_a_hope_takes_a_fear_off_the_gm():
    holder = _make_pc(domain_cards_loadout=[DIRE_STRIKE])
    target = _make_adversary()
    fight = _rested_state([holder], [target], fear=4)

    apply_on_hit(holder, target, _a_landed_hit(), fight)

    assert holder.hope_marked == 5
    assert fight.fear == 3


def test_nothing_is_spent_on_an_empty_fear_pool():
    holder = _make_pc(domain_cards_loadout=[DIRE_STRIKE])
    target = _make_adversary()
    fight = _rested_state([holder], [target], fear=0)

    apply_on_hit(holder, target, _a_landed_hit(), fight)

    assert holder.hope_marked == 6


def test_a_hit_that_marked_no_hit_points_drains_nothing():
    holder = _make_pc(domain_cards_loadout=[DIRE_STRIKE])
    target = _make_adversary()
    fight = _rested_state([holder], [target], fear=4)

    apply_on_hit(holder, target, _a_landed_hit(hp_marked=0), fight)

    assert holder.hope_marked == 6
    assert fight.fear == 4


# --- Spectral Mist -----------------------------------------------------------


def _misting(**overrides):
    """Four PCs, because the Close band reaches nobody over a smaller party."""
    holder = _make_pc(name="Dread", domain_cards_loadout=[SPECTRAL_MIST], **overrides)
    allies = [_make_pc(name=f"Ally {index}") for index in range(3)]
    return holder, allies, _rested_state([holder, *allies], [])


def test_the_mist_costs_two_hope_and_turns_physical_damage_aside():
    holder, allies, fight = _misting()

    with _in_range():
        assert spectral_mist(holder, fight) is True

    assert holder.hope_marked == 6 - SPECTRAL_MIST_HOPE
    assert fight.has_condition(allies[0], INCORPOREAL) is True
    assert party_damage_reduction(allies[0], 9, fight, DamageType.PHYSICAL) == 9


def test_magic_still_finds_them():
    holder, allies, fight = _misting()

    with _in_range():
        spectral_mist(holder, fight)

    assert party_damage_reduction(allies[0], 9, fight, DamageType.MAGIC) == 0


def test_the_mist_lifts_on_that_pcs_next_action_roll():
    holder, allies, fight = _misting()

    with _in_range():
        spectral_mist(holder, fight)

    assert fight.expire_conditions(allies[0], BEFORE_AN_ACTION_ROLL) == [INCORPOREAL]
    assert party_damage_reduction(allies[0], 9, fight, DamageType.PHYSICAL) == 0
    # And an ally who has not yet rolled still has theirs.
    assert fight.has_condition(allies[1], INCORPOREAL) is True


def test_the_mist_declines_without_the_two_hope():
    holder, allies, fight = _misting(hope_marked=1)

    with _in_range():
        assert spectral_mist(holder, fight) is False

    assert fight.has_condition(holder, INCORPOREAL) is False


# --- Darkfire ----------------------------------------------------------------


def _burning(**overrides):
    """Four adversaries, where the Close band reaches exactly three."""
    holder = _make_pc(domain_cards_loadout=[DARKFIRE], **overrides)
    field = [_make_adversary(name=f"Dummy {index}") for index in range(4)]
    return holder, field, _rested_state([holder], field)


def _burnt(die: int):
    return patch(
        "domain_cards.dread.roll_d20",
        return_value=_attack(die=die, modifier=0, evasion=DARKFIRE_DIFFICULTY),
    )


def test_darkfire_spends_one_hope_per_target_the_band_reaches():
    holder, field, fight = _burning()

    with (
        patch("domain_cards.dread.roll_damage", return_value=_damage(11)),
        _burnt(die=2),
    ):
        assert darkfire(holder, fight) is True

    # Six Hope held, three targets reachable, so three Hope go in.
    assert holder.hope_marked == 3
    assert sum(1 for a in field if a.hp_marked) == 3


def test_a_target_that_saves_takes_half():
    holder, field, fight = _burning()

    with (
        patch("domain_cards.dread.roll_damage", return_value=_damage(11)),
        _burnt(die=18),
    ):
        darkfire(holder, fight)

    # 11 halves to 5, which is the Major threshold: 2 HP rather than 3.
    burnt = [a for a in field if a.hp_marked]
    assert all(a.hp_marked == 2 for a in burnt)


def test_darkfire_is_cast_once_a_fight():
    holder, field, fight = _burning()

    with (
        patch("domain_cards.dread.roll_damage", return_value=_damage(11)),
        _burnt(die=2),
    ):
        assert darkfire(holder, fight) is True
        assert darkfire(holder, fight) is False


def test_darkfire_declines_with_no_hope_left():
    holder, field, fight = _burning(hope_marked=0)

    assert darkfire(holder, fight) is False


# --- Jump Scare --------------------------------------------------------------


def _scaring(**overrides):
    holder = _make_pc(domain_cards_loadout=[JUMP_SCARE], **overrides)
    target = _make_adversary()
    return holder, target, _rested_state([holder], [target])


def test_the_scare_costs_a_stress_and_leaves_them_vulnerable():
    holder, target, fight = _scaring()

    apply_on_hit(holder, target, _a_landed_hit(), fight)

    assert holder.stress_marked == 1
    assert fight.has_condition(target, VULNERABLE) is True


def test_the_vulnerable_lasts_until_they_mark_a_hit_point():
    holder, target, fight = _scaring()
    apply_on_hit(holder, target, _a_landed_hit(), fight)

    # Nothing has hit them since, so it holds - and costs the GM no Fear.
    assert fight.expire_conditions(target, ON_A_GM_TURN) == []

    target.mark_hp(1)

    assert fight.expire_conditions(target, ON_A_GM_TURN) == [VULNERABLE]


def test_the_scare_declines_against_something_already_vulnerable():
    holder, target, fight = _scaring()
    apply_on_hit(holder, target, _a_landed_hit(), fight)

    apply_on_hit(holder, target, _a_landed_hit(), fight)

    assert holder.stress_marked == 1


def test_the_scare_declines_against_a_target_the_hit_finished():
    holder, target, fight = _scaring()
    target.hp_marked = target.hp_max

    apply_on_hit(holder, target, _a_landed_hit(), fight)

    assert holder.stress_marked == 0


# --- Dread-Touched -----------------------------------------------------------


def _touched(**overrides):
    holder = _make_pc(domain_cards_loadout=[DREAD_TOUCHED], **overrides)
    target = _make_adversary()
    return holder, target, _rested_state([holder], [target], fear=5)


def test_two_stress_denies_the_gm_their_fear():
    holder, _, fight = _touched()

    assert fear_is_converted(holder, fight) is True
    assert holder.stress_marked == 2


def test_the_denial_stops_at_the_ceiling():
    """Codex-Touched's rule: the ceiling replaces the willingness rule."""
    holder, _, fight = _touched(stress_marked=DREAD_TOUCHED_STRESS_CEILING)

    assert fear_is_converted(holder, fight) is False
    assert holder.stress_marked == DREAD_TOUCHED_STRESS_CEILING


def test_the_per_rest_bonus_is_the_whole_pool():
    holder, target, fight = _touched()

    assert total_roll_bonus(holder, target, fight) == 5


def test_the_bonus_is_taken_once_a_rest():
    holder, target, fight = _touched()

    assert total_roll_bonus(holder, target, fight) == 5
    assert total_roll_bonus(holder, target, fight) == 0


def test_an_empty_pool_neither_pays_nor_claims_the_use():
    holder, target, fight = _touched()
    fight.fear = 0

    assert total_roll_bonus(holder, target, fight) == 0

    fight.fear = 4
    assert total_roll_bonus(holder, target, fight) == 4


# --- Dark Army ---------------------------------------------------------------


def _fielding(adversaries: int = 3, **overrides):
    """Three adversaries, since the Very Close band reaches nobody below that."""
    holder = _make_pc(domain_cards_loadout=[DARK_ARMY], **overrides)
    field = [_make_adversary(name=f"Dummy {index}") for index in range(adversaries)]
    return holder, field, _rested_state([holder], field)


def test_a_successful_cast_places_eight_fiends():
    holder, field, fight = _fielding()

    with _casting(_roll(12, 11, DARK_ARMY_DIFFICULTY)):
        assert dark_army(holder, field[0], fight) is not None

    assert fight.token_count(holder, FIENDS) == DARK_ARMY_TOKENS


def test_a_fiend_spends_itself_on_a_damage_roll():
    holder, field, fight = _fielding()
    fight.set_token(holder, FIENDS, DARK_ARMY_TOKENS)

    with _in_range():
        groups = total_extra_damage(holder, field[0], WITH_HOPE, fight)

    assert len(groups) == 1
    assert groups[0].sides == 8
    assert fight.token_count(holder, FIENDS) == DARK_ARMY_TOKENS - 1


def test_a_fiend_spends_itself_taking_a_blow():
    holder, field, fight = _fielding()
    fight.set_token(holder, FIENDS, DARK_ARMY_TOKENS)

    with patch("domain_cards.dread.random.randint", return_value=5):
        assert party_damage_reduction(holder, 12, fight) == 5

    assert fight.token_count(holder, FIENDS) == DARK_ARMY_TOKENS - 1


def test_an_empty_pool_of_fiends_does_nothing():
    holder, field, fight = _fielding()

    with _in_range():
        assert total_extra_damage(holder, field[0], WITH_HOPE, fight) == []
    assert party_damage_reduction(holder, 12, fight) == 0


# --- Eldritch Flesh ----------------------------------------------------------


def _fleshed(**overrides):
    holder = _make_pc(domain_cards_loadout=[ELDRITCH_FLESH], **overrides)
    return holder, _rested_state([holder], [])


def test_marked_stress_raises_the_thresholds():
    """Major 10 becomes 13 at three Stress, so 12 drops out of the Major band."""
    holder, fight = _fleshed(stress_marked=3)

    assert soften_damage(holder, 12, 2, fight) == 1


def test_an_unstressed_caster_gets_nothing():
    holder, fight = _fleshed()

    assert soften_damage(holder, 12, 2, fight) == 2


def test_the_bonus_never_makes_a_hit_worse():
    """A hit already softened below the raised band is left where it is."""
    holder, fight = _fleshed(stress_marked=3)

    assert soften_damage(holder, 25, 1, fight) == 1


def test_a_roll_with_fear_buys_an_armor_slot_back():
    holder, fight = _fleshed(armor_max=2)
    holder.armor_marked = 1

    apply_on_roll(holder, WITH_FEAR, fight)

    assert holder.armor_marked == 0
    assert holder.hope_marked == 6 - ELDRITCH_FLESH_HOPE


def test_a_roll_with_hope_mends_nothing():
    holder, fight = _fleshed(armor_max=2)
    holder.armor_marked = 1

    apply_on_roll(holder, WITH_HOPE, fight)

    assert holder.armor_marked == 1
    assert holder.hope_marked == 6


def test_nothing_is_spent_with_no_slot_marked():
    holder, fight = _fleshed(armor_max=2)

    apply_on_roll(holder, WITH_FEAR, fight)

    assert holder.hope_marked == 6


# --- Damnation ---------------------------------------------------------------


def _damning(**overrides):
    caster = _make_pc(domain_cards_loadout=[DAMNATION], **overrides)
    target = _make_adversary(name="Damned")
    other = _make_adversary(name="Witness")
    return caster, target, other, _rested_state([caster], [target, other])


def test_damnation_rolls_a_die_per_stress_the_rule_allows():
    caster, target, other, fight = _damning()

    with (
        _casting(WITH_HOPE),
        patch("domain_cards.dread.roll_damage", return_value=_damage(30)) as rolled,
    ):
        damnation(caster, target, fight)

    # Six slots, and the shared rule holds the last one back while healthy.
    assert caster.stress_marked == 5
    assert rolled.call_args.kwargs["dice_groups"][0].count == 5
    assert rolled.call_args.kwargs["dice_groups"][0].sides == 20


def test_a_kill_costs_the_rest_of_the_field_a_stress():
    caster, target, other, fight = _damning()
    target.hp_marked = target.hp_max - 1

    with (
        _the_whole_field(),
        _casting(WITH_HOPE),
        patch("domain_cards.dread.roll_damage", return_value=_damage(30)),
    ):
        damnation(caster, target, fight)

    assert target.is_defeated is True
    assert other.stress_marked == 1


def test_a_target_left_standing_costs_the_field_nothing():
    caster, target, other, fight = _damning()

    with (
        _the_whole_field(),
        _casting(WITH_HOPE),
        patch("domain_cards.dread.roll_damage", return_value=_damage(6)),
    ):
        damnation(caster, target, fight)

    assert other.stress_marked == 0


def test_damnation_declines_with_no_stress_to_spend():
    caster, target, other, fight = _damning(stress_marked=5)
    caster.hp_marked = 0  # healthy, so the last slot is held back

    assert damnation(caster, target, fight) is None


# --- Savor the Anguish -------------------------------------------------------


def _savouring(**overrides):
    holder = _make_pc(domain_cards_loadout=[SAVOR_THE_ANGUISH], **overrides)
    ally = _make_pc(name="Ally")
    target = _make_adversary()
    return holder, ally, target, _rested_state([holder, ally], [target])


def _hit_for(total: int) -> AttackResult:
    return AttackResult(
        attack_roll=WITH_HOPE, damage_roll=_damage(total), hp_marked=1
    )


def test_severe_damage_on_an_adversary_clears_a_stress():
    holder, ally, target, fight = _savouring(stress_marked=2)

    # 10 is the adversary's Severe threshold.
    apply_ally_on_hit(ally, target, _hit_for(10), fight)

    assert holder.stress_marked == 1


def test_a_lesser_wound_is_not_savoured():
    holder, ally, target, fight = _savouring(stress_marked=2)

    apply_ally_on_hit(ally, target, _hit_for(9), fight)

    assert holder.stress_marked == 2


def test_nothing_is_savoured_with_no_stress_marked():
    holder, ally, target, fight = _savouring()

    apply_ally_on_hit(ally, target, _hit_for(30), fight)

    assert holder.stress_marked == 0


# --- Avatar of Terror --------------------------------------------------------


def _avatar(adversaries: int = 3, **overrides):
    """Three adversaries, since the Very Close band reaches nobody below that.

    `chance_within(VERY_CLOSE, 1)` and `(VERY_CLOSE, 2)` are both exactly 0.0 - a
    third of a field of one or two, unfloored, rounds to nothing - so a smaller
    field makes the Hope clause untestable rather than merely unlikely.
    """
    holder = _make_pc(domain_cards_loadout=[AVATAR_OF_TERROR], **overrides)
    field = [_make_adversary(name=f"Dummy {index}") for index in range(adversaries)]
    return holder, field[0], _rested_state([holder], field, fear=4)


def test_the_avatar_is_taken_at_once_whatever_the_hope():
    """Ruled apart from Force of Nature: no Hope floor, taken at the start."""
    holder, _, fight = _avatar(hope_marked=1)

    assert avatar_of_terror(holder, fight) is True
    assert fight.has_condition(holder, FEAR_FUELED) is True
    assert holder.stress_marked == 1


def test_the_form_rolls_a_die_for_every_fear_in_the_pool():
    holder, target, fight = _avatar()
    avatar_of_terror(holder, fight)

    groups = total_extra_damage(holder, target, WITH_HOPE, fight)

    assert len(groups) == 1
    assert groups[0].count == 4  # the Fear in the pool
    assert groups[0].sides == 6


def test_the_pool_is_read_afresh_on_every_damage_roll():
    holder, target, fight = _avatar()
    avatar_of_terror(holder, fight)
    fight.fear = 9

    assert total_extra_damage(holder, target, WITH_HOPE, fight)[0].count == 9


def test_an_empty_pool_adds_nothing():
    holder, target, fight = _avatar()
    avatar_of_terror(holder, fight)
    fight.fear = 0

    assert total_extra_damage(holder, target, WITH_HOPE, fight) == []


def test_a_bought_spotlight_feeds_the_form_a_hope():
    holder, target, fight = _avatar(hope_marked=2)
    avatar_of_terror(holder, fight)

    with _in_range():
        apply_ally_on_spotlight(target, fight, True)

    assert holder.hope_marked == 3


def test_a_spotlight_the_gm_did_not_pay_for_feeds_nothing():
    """A GM turn's first activation is free, and a granted one was already bought."""
    holder, target, fight = _avatar(hope_marked=2)
    avatar_of_terror(holder, fight)

    with _in_range():
        apply_ally_on_spotlight(target, fight, False)

    assert holder.hope_marked == 2


def test_an_untransformed_dread_feeds_on_nothing():
    holder, target, fight = _avatar(hope_marked=2)

    with _in_range():
        apply_ally_on_spotlight(target, fight, True)

    assert holder.hope_marked == 2


def test_the_upkeep_drops_the_form_when_the_hope_runs_out():
    holder, target, fight = _avatar(hope_marked=1)
    avatar_of_terror(holder, fight)

    fight.apply_condition_effects(holder, BEFORE_AN_ACTION_ROLL)
    assert holder.hope_marked == 0
    assert fight.has_condition(holder, FEAR_FUELED) is True

    fight.apply_condition_effects(holder, BEFORE_AN_ACTION_ROLL)
    assert fight.has_condition(holder, FEAR_FUELED) is False


# --- Invoke Torment ----------------------------------------------------------


def _tormenting(**overrides):
    holder = _make_pc(domain_cards_loadout=[INVOKE_TORMENT], **overrides)
    target = _make_adversary()
    return holder, target, _rested_state([holder], [target])


def test_a_stressed_out_target_takes_double():
    holder, target, fight = _tormenting()
    target.stress_marked = target.stress_max

    assert dealt_damage_scaling(holder, target, fight) == 2


def test_a_target_with_stress_left_takes_normal_damage():
    holder, target, fight = _tormenting()
    target.stress_marked = target.stress_max - 1

    assert dealt_damage_scaling(holder, target, fight) == 1


def test_finishing_a_stressed_out_target_pays_a_hope():
    holder, target, fight = _tormenting(hope_marked=3)
    target.stress_marked = target.stress_max
    target.hp_marked = target.hp_max

    apply_on_hit(holder, target, _a_landed_hit(), fight)

    assert holder.hope_marked == 4


def test_finishing_one_with_stress_left_pays_nothing():
    holder, target, fight = _tormenting(hope_marked=3)
    target.hp_marked = target.hp_max

    apply_on_hit(holder, target, _a_landed_hit(), fight)

    assert holder.hope_marked == 3


# --- Wall of Hunger ----------------------------------------------------------


def _walling(adversaries: int = 4, **overrides):
    """Four adversaries, where the Close band reaches exactly three."""
    caster = _make_pc(domain_cards_loadout=[WALL_OF_HUNGER], **overrides)
    field = [_make_adversary(name=f"Dummy {index}") for index in range(adversaries)]
    return caster, field, _rested_state([caster], field)


def test_the_wall_forces_stress_on_everything_the_band_catches():
    caster, field, fight = _walling()

    with _casting(_roll(12, 11, WALL_OF_HUNGER_DIFFICULTY)):
        assert wall_of_hunger(caster, field[0], fight) is not None

    caught = [a for a in field if a.stress_marked]
    assert len(caught) == 3
    assert all(a.stress_marked == WALL_OF_HUNGER_STRESS for a in caught)
    assert caster.hope_marked == 5


def test_the_wall_declines_below_two_in_the_band():
    """One adversary is all the Close band reaches over a field of two."""
    caster, field, fight = _walling(adversaries=2)

    assert wall_of_hunger(caster, field[0], fight) is None
    assert caster.hope_marked == 6


def test_a_failed_cast_keeps_the_hope():
    caster, field, fight = _walling()

    with _casting(_roll(2, 3, WALL_OF_HUNGER_DIFFICULTY)):
        result = wall_of_hunger(caster, field[0], fight)

    assert result is not None and not result.attack_roll.is_success
    assert caster.hope_marked == 6
    assert all(a.stress_marked == 0 for a in field)


def test_the_wall_declines_without_a_hope():
    caster, field, fight = _walling(hope_marked=0)

    assert wall_of_hunger(caster, field[0], fight) is None


def test_a_full_stress_track_takes_a_hit_point_from_the_wall():
    caster, field, fight = _walling()
    for adversary in field:
        adversary.stress_marked = adversary.stress_max

    with _casting(_roll(12, 11, WALL_OF_HUNGER_DIFFICULTY)):
        wall_of_hunger(caster, field[0], fight)

    assert sum(a.hp_marked for a in field) == 3


# --- Registered --------------------------------------------------------------


EVERY_DREAD_CARD = (
    # Level 1
    BLIGHTING_STRIKE,
    UMBRAL_VEIL,
    VOICE_OF_DREAD,
    # Levels 2-3
    HIDEOUS_RETRIBUTION,
    SIPHON_ESSENCE,
    SHARED_TRAUMA,
    TERRIFY,
    # Levels 4-6
    CHAINS_OF_AFFLICTION,
    SUMMON_HORROR,
    DIRE_STRIKE,
    SPECTRAL_MIST,
    DARKFIRE,
    JUMP_SCARE,
    # Levels 7-10
    DREAD_TOUCHED,
    WALL_OF_HUNGER,
    DARK_ARMY,
    ELDRITCH_FLESH,
    DAMNATION,
    SAVOR_THE_ANGUISH,
    AVATAR_OF_TERROR,
    INVOKE_TORMENT,
)


def test_every_card_in_the_domain_is_modelled():
    """Also the check that the registry discovers a newly added domain module."""
    for card in EVERY_DREAD_CARD:
        assert assess(card).status is Status.MODELLED


def test_the_domain_is_the_twenty_one_the_srd_prints():
    """Three at level 1 and two at every level from 2 to 10, like every domain."""
    assert len(set(EVERY_DREAD_CARD)) == 21


def test_every_card_is_registered_in_this_module():
    """A card registered from somewhere else would be a name collision, not a port."""
    for card in EVERY_DREAD_CARD:
        assert assess(card).source == "domain_cards.dread"


def test_the_partial_implementations_declare_their_gaps():
    assert assess(TERRIFY).is_partial is True
    assert "flee" in " ".join(assess(TERRIFY).unmodelled)
