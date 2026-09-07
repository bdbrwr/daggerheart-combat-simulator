"""Tests for the Sage domain cards.

Most of these make or respond to rolls, so the dice are patched and what's under
test is the decision-making around them: when a card fires, what it costs, and
what it drains from the GM.

**The Spellcast Roll is patched through `content.spellcast`**, not through the
Sage module. Every domain module used to carry its own `_spellcast` helper and so
its own `roll_duality` import; they now share `content/spellcast.py`, which is
where the call lives. Patching `domain_cards.sage.roll_duality` raises, which is
the good failure - Splendor kept a `roll_duality` import for Healing Hands, so the
same mistake there patches a name nothing calls and the test fails on an
assertion instead.

Restraining isn't tracked, so Vicious Entangle's Restrains are Fear off the GM's
pool per SIMULATION-RULES.md - which makes the Fear count the thing to assert on.

Two pieces of shared machinery are what the later cards are mostly about:

* **The rolled trait** travels with a duality roll and through `roll_bonus`, which
  is the only way Sage-Touched's "double your Agility or Instinct on a roll that
  uses that trait" can be asked at all. The machinery itself is pinned in
  `test_domain_cards.py`; what is here is the card reading it.
* **`ally_roll_bonus`** and **`ally_extra_armor_slot`**, the party-wide twins of
  two hooks that had only ever been holder-scoped. Forest Sprites gives both of
  its benefits to somebody else and could not be written without them.

The readings pinned down here are the ones the module documents as choices:
Sage-Touched's +2 running in every fight because terrain is not modelled, Wild
Surge climbing 1 through 6 and then charging a forced Stress on the way out, and
Forest Sprites spending Hope down to a floor of 2 and burning one sprite per
benefit.
"""

from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.state import FightState
from content import (
    Status,
    ally_extra_armor_slots,
    assess,
    party_damage_reduction,
    take_action,
    total_ally_roll_bonus,
    total_roll_bonus,
    total_spellcast_bonus,
    use_free_abilities,
)
from content.damage_types import DamageType
from content.spellcast import spellcast
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from domain_cards.sage import (
    BARRIER_STANDING,
    BEETLES,
    FOREST_SPRITES,
    FOREST_SPRITES_ATTACK_BONUS,
    FOREST_SPRITES_HOPE_FLOOR,
    REJUVENATION_BARRIER,
    SAGE_TOUCHED,
    SPRITES_STANDING,
    WILD_SURGE,
    WILD_SURGE_DIE,
    WILD_SURGE_MAX,
    beetles_take_the_hit,
    fire_flies,
    tekaira_armored_beetles,
    vicious_entangle,
)

CONJURED_STEEDS = "Conjured Steeds"
FORAGER = "Forager"


def _make_ranger(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Luma",
        level=2,
        character_class="Ranger",
        subclass="Beastbound",
        # Invented, so nothing else can join the roll or soften the damage.
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 2, "strength": 0, "finesse": 1,
            "instinct": 1, "presence": 0, "knowledge": 0,
        },
        evasion=11,
        proficiency=1,
        major_threshold=6,
        severe_threshold=12,
        hp_max=6,
        stress_max=6,
        hope_max=6,
        armor_max=0,  # off unless a test is about armor
        primary_weapon="Shortbow",
        secondary_weapon=None,
        armor_item="Gambeson Armor",
        domain_cards_loadout=["Vicious Entangle", "Conjure Swarm"],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
        spellcast_trait="agility",
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
        # No armor, deliberately: an armor feature registered on a damage hook
        # would sit in the middle of what is being measured.
        armor_item="",
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
            "agility": 1,
            "strength": 2,
            "finesse": 1,
            "instinct": 1,
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
        armor_item="",
        domain_cards_loadout=[],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
    )
    defaults.update(overrides)
    return PlayerCharacter(**defaults)


def _make_bandit(name: str = "Bandit", difficulty: int = 11) -> Adversary:
    """The level 1-2 cards' target, with a Difficulty a roll can actually miss."""
    return Adversary(
        name=name,
        tier=1,
        difficulty=difficulty,
        major_threshold=5,
        severe_threshold=10,
        hp_max=5,
        stress_max=3,
        attack_modifier=1,
    )


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


def _fight(ranger: PlayerCharacter, adversaries: list[Adversary], fear: int = 3) -> FightState:
    return FightState(
        encounter_name="Test",
        party=[ranger],
        adversaries=adversaries,
        fear=fear,
    )


def _rested_state(party, adversaries, **overrides) -> FightState:
    """A fight the party walked into off a long rest, for the per-rest cards."""
    overrides.setdefault("rest", Rest.LONG)
    return FightState(
        encounter_name="Test", party=party, adversaries=adversaries, **overrides
    )


def _roll(*, hope: int, fear: int, modifier: int, difficulty: int) -> DualityRollResult:
    return DualityRollResult(
        hope_die_result=hope,
        fear_die_result=fear,
        modifier=modifier,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=difficulty,
    )


HIT = _roll(hope=9, fear=6, modifier=2, difficulty=11)  # total 17
MISS = _roll(hope=2, fear=1, modifier=2, difficulty=11)  # total 5


def _damage(total: int) -> DamageRollResult:
    return DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=8)], die_results=[[total - 1]], modifier=1
    )


def _succeeding(difficulty: int):
    """Patch the shared cast so a printed-Difficulty spell definitely lands."""
    return patch(
        "content.spellcast.roll_duality",
        return_value=_roll(hope=12, fear=11, modifier=0, difficulty=difficulty),
    )


# --- Vicious Entangle --------------------------------------------------------


def test_entangle_deals_damage_and_drains_a_fear_for_the_restrain():
    ranger = _make_ranger(hope_marked=0)
    adversary = _make_bandit()
    fight = _fight(ranger, [adversary], fear=3)

    with (
        patch("content.spellcast.roll_duality", return_value=HIT),
        patch("domain_cards.sage.roll_damage", return_value=_damage(6)),
    ):
        result = vicious_entangle(ranger, adversary, fight)

    assert result.hit is True
    assert adversary.hp_marked == 2  # 6 is at the Major threshold of 5
    assert fight.fear == 2


def test_a_missed_entangle_costs_the_gm_nothing():
    ranger = _make_ranger()
    adversary = _make_bandit()
    fight = _fight(ranger, [adversary], fear=3)

    with (
        patch("content.spellcast.roll_duality", return_value=MISS),
        patch("domain_cards.sage.roll_damage") as mock_roll_damage,
    ):
        result = vicious_entangle(ranger, adversary, fight)

    assert result.hit is False
    assert result.damage_roll is None
    assert fight.fear == 3
    mock_roll_damage.assert_not_called()


def test_a_hope_buys_a_second_restrain_and_a_second_fear():
    ranger = _make_ranger(hope_marked=2)
    first, second = _make_bandit("First"), _make_bandit("Second")
    fight = _fight(ranger, [first, second], fear=3)

    with (
        patch("content.spellcast.roll_duality", return_value=HIT),
        patch("domain_cards.sage.roll_damage", return_value=_damage(6)),
    ):
        vicious_entangle(ranger, first, fight)

    assert ranger.hope_marked == 1
    assert fight.fear == 1  # one Fear per Restrain


def test_no_hope_is_spent_with_nobody_else_to_restrain():
    ranger = _make_ranger(hope_marked=2)
    adversary = _make_bandit()
    fight = _fight(ranger, [adversary], fear=3)

    with (
        patch("content.spellcast.roll_duality", return_value=HIT),
        patch("domain_cards.sage.roll_damage", return_value=_damage(6)),
    ):
        vicious_entangle(ranger, adversary, fight)

    assert ranger.hope_marked == 2


def test_no_hope_is_spent_when_the_gm_has_no_fear_left_to_take():
    """At 0 Fear a temporary condition is free to the GM, so the Hope buys nothing."""
    ranger = _make_ranger(hope_marked=2)
    first, second = _make_bandit("First"), _make_bandit("Second")
    fight = _fight(ranger, [first, second], fear=0)

    with (
        patch("content.spellcast.roll_duality", return_value=HIT),
        patch("domain_cards.sage.roll_damage", return_value=_damage(6)),
    ):
        vicious_entangle(ranger, first, fight)

    assert ranger.hope_marked == 2
    assert fight.fear == 0


def test_a_caster_with_no_spellcast_trait_declines():
    """Declining is how unusable content shows up, rather than a wrong guess."""
    ranger = _make_ranger(spellcast_trait="")
    adversary = _make_bandit()
    fight = _fight(ranger, [adversary])

    assert vicious_entangle(ranger, adversary, fight) is None


# --- Conjure Swarm: the beetles ----------------------------------------------


def test_the_beetles_cost_a_stress_to_conjure():
    ranger = _make_ranger()
    fight = _fight(ranger, [_make_bandit()])

    assert tekaira_armored_beetles(ranger, fight) is True
    assert ranger.stress_marked == 1
    assert fight.token_count(ranger, BEETLES) == 1


def test_the_beetles_are_not_conjured_twice():
    ranger = _make_ranger()
    fight = _fight(ranger, [_make_bandit()])
    tekaira_armored_beetles(ranger, fight)

    assert tekaira_armored_beetles(ranger, fight) is False
    assert ranger.stress_marked == 1


def test_the_beetles_keep_the_last_stress_slot_free():
    ranger = _make_ranger(stress_max=2)
    ranger.mark_stress(1)
    fight = _fight(ranger, [_make_bandit()])

    assert tekaira_armored_beetles(ranger, fight) is False
    assert ranger.stress_marked == 1


def test_the_beetles_take_one_threshold_off_the_next_hit():
    ranger = _make_ranger(hope_marked=0)
    fight = _fight(ranger, [_make_bandit()])
    tekaira_armored_beetles(ranger, fight)

    assert beetles_take_the_hit(ranger, 12, 3, fight) == 2


def test_the_beetles_are_spent_unless_a_hope_keeps_them_up():
    ranger = _make_ranger(hope_marked=0)
    fight = _fight(ranger, [_make_bandit()])
    tekaira_armored_beetles(ranger, fight)

    beetles_take_the_hit(ranger, 12, 3, fight)

    assert fight.token_count(ranger, BEETLES) == 0
    assert beetles_take_the_hit(ranger, 12, 3, fight) == 3  # gone


def test_a_hope_keeps_the_beetles_up_for_the_next_hit():
    ranger = _make_ranger(hope_marked=4)
    fight = _fight(ranger, [_make_bandit()])
    tekaira_armored_beetles(ranger, fight)

    assert beetles_take_the_hit(ranger, 12, 3, fight) == 2
    assert ranger.hope_marked == 3
    assert fight.token_count(ranger, BEETLES) == 1


def test_the_beetles_are_not_spent_on_a_hit_armor_already_absorbed():
    ranger = _make_ranger(hope_marked=0)
    fight = _fight(ranger, [_make_bandit()])
    tekaira_armored_beetles(ranger, fight)

    assert beetles_take_the_hit(ranger, 4, 0, fight) == 0
    assert fight.token_count(ranger, BEETLES) == 1


def test_the_beetles_do_nothing_without_a_fight_to_read_state_from():
    assert beetles_take_the_hit(_make_ranger(), 12, 3, None) == 3


# --- Conjure Swarm: the fire flies -------------------------------------------


def test_fire_flies_declines_against_a_single_adversary():
    """A Hope for less than a bow shot; the card wants a crowd."""
    ranger = _make_ranger(hope_marked=3)
    adversary = _make_bandit()
    fight = _fight(ranger, [adversary])

    assert fire_flies(ranger, adversary, fight) is None
    assert ranger.hope_marked == 3


def test_fire_flies_declines_without_a_hope_to_spend():
    ranger = _make_ranger(hope_marked=0)
    crowd = [_make_bandit(f"Bandit {n}") for n in range(3)]
    fight = _fight(ranger, crowd)

    assert fire_flies(ranger, crowd[0], fight) is None


def test_fire_flies_hits_everything_it_reaches_and_costs_one_hope():
    """One roll and one damage roll, applied to each adversary it beat."""
    ranger = _make_ranger(hope_marked=3)
    crowd = [_make_bandit(f"Bandit {n}") for n in range(3)]
    fight = _fight(ranger, crowd)
    damage = DamageRollResult(
        dice_groups=[DiceGroup(count=2, sides=8)], die_results=[[4, 4]], modifier=3
    )

    with (
        patch("content.spellcast.roll_duality", return_value=HIT),
        patch("domain_cards.sage.roll_damage", return_value=damage) as mock_roll_damage,
    ):
        result = fire_flies(ranger, crowd[0], fight)

    assert ranger.hope_marked == 2
    assert mock_roll_damage.call_count == 1
    # Close range reaches 2 of 3, and 11 damage is Severe against a 10 threshold.
    assert sum(1 for adversary in crowd if adversary.hp_marked) == 2
    assert result.hp_marked == 6


def test_fire_flies_is_rolled_against_the_area_and_resolved_per_target():
    """The roll faces the whole area, not the one adversary the policy picked.

    This is the difference from Whirlwind, which rolls against a single target
    and reuses that roll: here every adversary in the area is checked against
    its own Difficulty, and the roll counts as a success if it beat any of them.
    """
    ranger = _make_ranger(hope_marked=3)
    easy = _make_bandit("Easy", difficulty=11)
    hard = _make_bandit("Hard", difficulty=20)
    spare = _make_bandit("Spare", difficulty=11)
    fight = _fight(ranger, [easy, hard, spare])
    damage = DamageRollResult(
        dice_groups=[DiceGroup(count=2, sides=8)], die_results=[[4, 4]], modifier=3
    )

    with (
        patch("content.spellcast.roll_duality", return_value=HIT) as mock_roll_duality,
        patch("domain_cards.sage.roll_damage", return_value=damage),
    ):
        result = fire_flies(ranger, hard, fight)

    # Rolled against the lowest Difficulty in the area, not the picked target's.
    assert mock_roll_duality.call_args.kwargs["difficulty"] == 11
    assert easy.hp_marked == 3  # 11 damage is Severe against a 10 threshold
    assert hard.hp_marked == 0  # a total of 17 didn't beat its Difficulty of 20
    assert result.hit is True


def test_fire_flies_spends_no_hope_when_the_roll_beat_nobody():
    ranger = _make_ranger(hope_marked=3)
    crowd = [_make_bandit(f"Bandit {n}", difficulty=20) for n in range(3)]
    fight = _fight(ranger, crowd)

    with (
        patch("content.spellcast.roll_duality", return_value=MISS),
        patch("domain_cards.sage.roll_damage") as mock_roll_damage,
    ):
        result = fire_flies(ranger, crowd[0], fight)

    assert result.damage_roll is None
    assert ranger.hope_marked == 3
    mock_roll_damage.assert_not_called()


# --- Sage-Touched ------------------------------------------------------------


def test_the_spellcast_bonus_is_simply_on():
    """Ruled: every fight counts as a natural environment."""
    caster = _make_level_7_pc(domain_cards_loadout=[SAGE_TOUCHED])
    target = _make_adversary()
    fight = _rested_state([caster], [target])

    assert total_spellcast_bonus(caster, target, fight) == 2


def test_the_spellcast_bonus_does_not_reach_a_weapon_swing():
    caster = _make_level_7_pc(domain_cards_loadout=[SAGE_TOUCHED])
    target = _make_adversary()
    fight = _rested_state([caster], [target])

    assert total_roll_bonus(caster, target, fight, trait="strength") == 0


def test_the_doubling_fires_on_a_roll_that_uses_the_trait():
    holder = _make_level_7_pc(domain_cards_loadout=[SAGE_TOUCHED])
    target = _make_adversary()
    fight = _rested_state([holder], [target])

    # Agility 3, doubled - so the roll gets the trait a second time.
    assert total_roll_bonus(holder, target, fight, trait="agility") == 3


def test_the_doubling_declines_on_a_trait_the_card_does_not_name():
    holder = _make_level_7_pc(domain_cards_loadout=[SAGE_TOUCHED])
    target = _make_adversary()
    fight = _rested_state([holder], [target])

    assert total_roll_bonus(holder, target, fight, trait="finesse") == 0
    # And the use is still there for an Agility roll afterwards.
    assert total_roll_bonus(holder, target, fight, trait="agility") == 3


def test_the_doubling_declines_at_a_trait_of_zero():
    """Instinct is 0 on the test sheet - the standing zero-benefit rule."""
    holder = _make_level_7_pc(domain_cards_loadout=[SAGE_TOUCHED])
    target = _make_adversary()
    fight = _rested_state([holder], [target])

    assert total_roll_bonus(holder, target, fight, trait="instinct") == 0
    assert fight.can_use_once_per_rest(holder, SAGE_TOUCHED) is True


def test_the_doubling_is_once_per_rest():
    holder = _make_level_7_pc(domain_cards_loadout=[SAGE_TOUCHED])
    target = _make_adversary()
    fight = _rested_state([holder], [target])

    assert total_roll_bonus(holder, target, fight, trait="agility") == 3
    assert total_roll_bonus(holder, target, fight, trait="agility") == 0


def test_the_doubling_lands_in_a_spellcast_roll_made_on_that_trait():
    """A Sage whose Spellcast trait is Instinct or Agility gets both clauses."""
    caster = _make_level_7_pc(
        domain_cards_loadout=[SAGE_TOUCHED], spellcast_trait="agility"
    )
    target = _make_adversary()
    fight = _rested_state([caster], [target])

    roll = spellcast(caster, target, fight)

    # Agility 3, the card's +2 to Spellcast Rolls, and Agility doubled again.
    assert roll.modifier == 8
    assert roll.trait == "agility"


# --- Wild Surge --------------------------------------------------------------


def test_the_surge_costs_a_stress_and_places_the_die_at_one():
    holder = _make_level_7_pc(domain_cards_loadout=[WILD_SURGE])
    fight = _rested_state([holder], [])

    assert use_free_abilities(holder, fight, limit=1) == [WILD_SURGE]
    assert holder.stress_marked == 1
    assert fight.token_count(holder, WILD_SURGE_DIE) == 1


def test_the_surge_is_not_raised_twice():
    holder = _make_level_7_pc(domain_cards_loadout=[WILD_SURGE])
    fight = _rested_state([holder], [])

    use_free_abilities(holder, fight, limit=1)
    assert use_free_abilities(holder, fight, limit=1) == []


def test_the_die_adds_its_value_and_then_climbs():
    holder = _make_level_7_pc(domain_cards_loadout=[WILD_SURGE])
    target = _make_adversary()
    fight = _rested_state([holder], [target])
    fight.set_token(holder, WILD_SURGE_DIE, 1)

    assert total_roll_bonus(holder, target, fight, trait="agility") == 1
    assert fight.token_count(holder, WILD_SURGE_DIE) == 2
    assert total_roll_bonus(holder, target, fight, trait="agility") == 2
    assert fight.token_count(holder, WILD_SURGE_DIE) == 3


def test_the_form_drops_after_the_die_pays_out_at_six():
    holder = _make_level_7_pc(domain_cards_loadout=[WILD_SURGE])
    target = _make_adversary()
    fight = _rested_state([holder], [target])
    fight.set_token(holder, WILD_SURGE_DIE, WILD_SURGE_MAX)

    # The sixth payout still gets its +6; the seventh would need a 7.
    assert total_roll_bonus(holder, target, fight, trait="agility") == WILD_SURGE_MAX
    assert fight.token_count(holder, WILD_SURGE_DIE) == 0
    assert holder.stress_marked == 1
    assert total_roll_bonus(holder, target, fight, trait="agility") == 0


def test_the_stress_the_form_costs_is_forced_and_can_reach_hp():
    """A full Stress track means the surge ending marks an HP instead."""
    holder = _make_level_7_pc(domain_cards_loadout=[WILD_SURGE], stress_max=1)
    target = _make_adversary()
    fight = _rested_state([holder], [target])
    holder.stress_marked = 1
    fight.set_token(holder, WILD_SURGE_DIE, WILD_SURGE_MAX)

    total_roll_bonus(holder, target, fight, trait="agility")

    assert holder.hp_marked == 1


# --- Forest Sprites ----------------------------------------------------------


def _conjuring(**overrides):
    caster = _make_level_8_pc(
        name="Druid", domain_cards_loadout=[FOREST_SPRITES], **overrides
    )
    ally = _make_level_8_pc(name="Ally")
    target = _make_adversary()
    return caster, ally, target, _rested_state([caster, ally], [target])


def test_forest_sprites_spends_hope_down_to_the_floor():
    caster, _, target, fight = _conjuring()

    with _succeeding(13):
        assert take_action(caster, target, fight) is not None

    assert caster.hope_marked == FOREST_SPRITES_HOPE_FLOOR
    assert fight.token_count(caster, SPRITES_STANDING) == 6 - FOREST_SPRITES_HOPE_FLOOR


def test_forest_sprites_declines_at_the_floor():
    caster, _, target, fight = _conjuring(hope_marked=FOREST_SPRITES_HOPE_FLOOR)

    with _succeeding(13):
        assert take_action(caster, target, fight) is None


def test_forest_sprites_declines_while_sprites_still_stand():
    caster, _, target, fight = _conjuring()
    fight.set_token(caster, SPRITES_STANDING, 1)

    with _succeeding(13):
        assert take_action(caster, target, fight) is None


def test_a_failed_conjuring_spends_no_hope():
    caster, _, target, fight = _conjuring()

    with patch(
        "content.spellcast.roll_duality",
        return_value=_roll(hope=1, fear=2, modifier=0, difficulty=13),
    ):
        result = take_action(caster, target, fight)

    assert result is not None and not result.attack_roll.is_success
    assert caster.hope_marked == 6
    assert fight.token_count(caster, SPRITES_STANDING) == 0


def test_a_sprite_guides_an_allys_swing_and_vanishes():
    caster, ally, target, fight = _conjuring()
    fight.set_token(caster, SPRITES_STANDING, 2)

    bonus = total_ally_roll_bonus(ally, target, fight, "agility")

    assert bonus == FOREST_SPRITES_ATTACK_BONUS
    assert fight.token_count(caster, SPRITES_STANDING) == 1


def test_a_sprite_never_guides_the_druid_who_conjured_it():
    """'Your allies' - both benefits are scoped away from the caster."""
    caster, _, target, fight = _conjuring()
    fight.set_token(caster, SPRITES_STANDING, 2)

    assert total_ally_roll_bonus(caster, target, fight, "agility") == 0
    assert fight.token_count(caster, SPRITES_STANDING) == 2


def test_no_sprites_left_adds_nothing():
    caster, ally, target, fight = _conjuring()

    assert total_ally_roll_bonus(ally, target, fight, "agility") == 0


def test_a_sprite_buys_an_ally_a_second_armor_slot():
    caster, ally, _, fight = _conjuring()
    fight.set_token(caster, SPRITES_STANDING, 1)

    slots = ally_extra_armor_slots(ally, 12, 1, fight, DamageType.PHYSICAL)

    assert slots == 1
    assert fight.token_count(caster, SPRITES_STANDING) == 0


def test_a_sprite_is_not_spent_where_the_slot_would_save_nothing():
    """Brace's rule - the free slot already took the hit to nothing."""
    caster, ally, _, fight = _conjuring()
    fight.set_token(caster, SPRITES_STANDING, 1)

    assert ally_extra_armor_slots(ally, 12, 0, fight, DamageType.PHYSICAL) == 0
    assert fight.token_count(caster, SPRITES_STANDING) == 1


def test_a_sprite_does_not_shield_the_druid_who_conjured_it():
    caster, _, _, fight = _conjuring()
    fight.set_token(caster, SPRITES_STANDING, 1)

    assert ally_extra_armor_slots(caster, 12, 1, fight, DamageType.PHYSICAL) == 0


# --- Rejuvenation Barrier ----------------------------------------------------


def _barrier(**overrides):
    caster = _make_level_8_pc(
        name="Druid", domain_cards_loadout=[REJUVENATION_BARRIER], **overrides
    )
    target = _make_adversary()
    return caster, target, _rested_state([caster], [target])


def test_the_barrier_goes_up_and_clears_hit_points():
    caster, target, fight = _barrier(hp_marked=4)

    with _succeeding(15):
        assert take_action(caster, target, fight) is not None

    assert fight.token_count(caster, BARRIER_STANDING)
    assert caster.hp_marked < 4


def test_the_barrier_is_once_per_rest_on_a_success():
    caster, target, fight = _barrier()

    with patch(
        "content.spellcast.roll_duality",
        return_value=_roll(hope=1, fear=2, modifier=0, difficulty=15),
    ):
        take_action(caster, target, fight)

    assert fight.can_use_once_per_rest(caster, REJUVENATION_BARRIER)
    assert fight.token_count(caster, BARRIER_STANDING) == 0


def test_the_barrier_halves_physical_damage_for_the_caster():
    caster, _, fight = _barrier()
    fight.set_token(caster, BARRIER_STANDING, 1)

    lost = party_damage_reduction(caster, 15, fight, DamageType.PHYSICAL)

    assert 15 - lost == 15 // 2


def test_the_barrier_does_nothing_against_magic():
    caster, _, fight = _barrier()
    fight.set_token(caster, BARRIER_STANDING, 1)

    assert party_damage_reduction(caster, 15, fight, DamageType.MAGIC) == 0


def test_no_barrier_reduces_nothing():
    caster, _, fight = _barrier()

    assert party_damage_reduction(caster, 15, fight, DamageType.PHYSICAL) == 0


# --- Assessed rather than built ----------------------------------------------


def test_natures_tongue_is_assessed_rather_than_left_missing():
    """The ruling is the user's; what matters here is that it's recorded."""
    assessment = assess("Nature's Tongue")

    assert assessment.status is Status.NO_COMBAT_EFFECT
    assert assessment.reason


def test_the_level_six_cards_are_out_of_combat_rather_than_dismissed():
    """The state matters: a dismissal would drop both off the sequenced list."""
    assert assess(CONJURED_STEEDS).status is Status.OUT_OF_COMBAT
    assert assess(FORAGER).status is Status.OUT_OF_COMBAT


def test_the_out_of_combat_declarations_say_why():
    """An assessment with no reason is indistinguishable from a shrug."""
    assert assess(CONJURED_STEEDS).reason
    assert assess(FORAGER).reason


def test_the_later_cards_are_modelled():
    for card in (SAGE_TOUCHED, WILD_SURGE, FOREST_SPRITES, REJUVENATION_BARRIER):
        assert assess(card).status is Status.MODELLED
