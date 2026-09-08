"""Tests for the Splendor domain cards.

Splendor is the domain that gives things away, and the cases split by who is
paying and who is protected. Restoration stocks a pool off a long rest and spends
it on whoever is worst off; Zone of Protection and Shield Aura both stand over
somebody else and wear out doing it; Splendor-Touched is the one that answers only
for its own holder.

One piece of shared machinery is what several of these are really about:

* **`ally_severity_response`**, the party-wide twin of `severity_response`, which
  is the only way one PC's card can move the threshold bands of another PC's hit.
  It carries `marked_armor` because Shield Aura's trigger is exactly that.

The readings pinned down here are the ones the modules document as choices:
Restoration never lifting a condition the **party** put on somebody, so it cannot
work against its own side; Zone of Protection's die climbing only on a hit it
actually soaked and the zone ending after the one it reduces by 6; Splendor-Touched
preferring Hope and marking Stress only to stay standing; Shield Aura answering
only a hit that marked an Armor Slot; and Stunning Sunlight emptying the Hope pool
one target at a time.

Level 10 puts two restorations here that nothing else in the project does.
Invigoration hands a **spent per-rest use** back, so its cases are about
`FightState.refresh_once_per_rest` and the Hope floor that prices it; Resurrection
puts an unconscious PC back on their feet, which is the one exception to the
standing policy that an unconscious PC takes no further part - so its cases pin
both the revival and what it does *not* undo.

Determinism comes from a target with a Difficulty of 0 so no case turns on whether
a roll landed, from patching `content.spellcast.roll_duality` where a card casts
against a printed Difficulty, and from patching the `random.random()` draw that
decides who a band reaches rather than seeding around it.
"""

from unittest.mock import patch

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.rest import Rest
from combat.results import AttackResult
from combat.state import FightState
from content import (
    Status,
    ally_soften_damage,
    apply_on_hit,
    apply_on_targeted,
    assess,
    party_damage_reduction,
    soften_damage,
    take_action,
    use_free_abilities,
)
from content.conditions import RESTRAINED, SHELTERED, STUNNED, Condition
from content.damage_types import DamageType
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from domain_cards.splendor import (
    AURA_STANDING,
    HEALING_STRIKE,
    INVIGORATION,
    INVIGORATION_HOPE_FLOOR,
    RESURRECTION,
    RESURRECTION_DIFFICULTY,
    RESURRECTION_VAULTED,
    invigoration,
    resurrection,
    OVERWHELMING_AURA,
    OVERWHELMING_AURA_DIFFICULTY,
    OVERWHELMING_AURA_HOPE,
    SALVATION_BEAM,
    SALVATION_BEAM_DIFFICULTY,
    overwhelming_aura,
    overwhelming_aura_costs,
    salvation_beam,
    RESTORATION,
    RESTORATION_TOKENS,
    SHIELD_AURA,
    SHIELD_AURA_WORN,
    SPLENDOR_TOUCHED,
    STUNNING_SUNLIGHT,
    ZONE_DIE,
    ZONE_OF_PROTECTION,
    zone_of_protection,
)


def _make_level_6_pc(**overrides) -> PlayerCharacter:
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
        armor_max=0,
        primary_weapon="Broadsword",
        secondary_weapon=None,
        # No armor, deliberately: half of these cases go through `soften_damage`,
        # and an armor feature registered on the same hook would sit in the middle
        # of what is being measured.
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


def _field(count: int) -> list[Adversary]:
    return [_make_adversary(name=f"Dummy {index}") for index in range(count)]


def _succeeding(difficulty: int):
    """Patch the shared cast so a printed-Difficulty spell definitely lands."""
    return patch(
        "content.spellcast.roll_duality",
        return_value=_roll(hope=12, fear=11, difficulty=difficulty),
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


# --- Restoration -------------------------------------------------------------


def test_restoration_stocks_its_spellcast_trait_in_tokens():
    caster = _make_level_6_pc(domain_cards_loadout=[RESTORATION])
    hurt = _make_level_6_pc(name="Hurt", domain_cards_loadout=[])
    hurt.mark_hp(6)  # 2 unmarked of 8
    fight = _state([caster, hurt], [], rest=Rest.LONG)

    use_free_abilities(caster, fight, limit=1)

    # Three to start (the caster's Knowledge), one spent on the touch.
    assert fight.token_count(caster, RESTORATION_TOKENS) == 2
    assert hurt.hp_marked == 4


def test_restoration_is_empty_without_a_long_rest():
    caster = _make_level_6_pc(domain_cards_loadout=[RESTORATION])
    hurt = _make_level_6_pc(name="Hurt", domain_cards_loadout=[])
    hurt.mark_hp(6)
    fight = _state([caster, hurt], [], rest=Rest.SHORT)

    use_free_abilities(caster, fight, limit=1)

    assert fight.token_count(caster, RESTORATION_TOKENS) == 0
    assert hurt.hp_marked == 6


def test_restoration_leaves_a_lightly_wounded_party_alone():
    """The trigger is 2 or fewer unmarked, not any mark at all."""
    caster = _make_level_6_pc(domain_cards_loadout=[RESTORATION])
    dented = _make_level_6_pc(name="Dented", domain_cards_loadout=[])
    dented.mark_hp(2)  # 6 unmarked of 8
    fight = _state([caster, dented], [], rest=Rest.LONG)

    use_free_abilities(caster, fight, limit=1)

    assert dented.hp_marked == 2
    assert fight.token_count(caster, RESTORATION_TOKENS) == 3


def test_restoration_takes_stress_when_that_is_the_track_in_trouble():
    caster = _make_level_6_pc(domain_cards_loadout=[RESTORATION])
    strained = _make_level_6_pc(name="Strained", domain_cards_loadout=[])
    strained.mark_stress(5)  # 1 unmarked of 6
    fight = _state([caster, strained], [], rest=Rest.LONG)

    use_free_abilities(caster, fight, limit=1)

    assert strained.stress_marked == 3


def test_a_token_lifts_a_condition_an_adversary_applied():
    caster = _make_level_6_pc(domain_cards_loadout=[RESTORATION])
    held = _make_level_6_pc(name="Held", domain_cards_loadout=[])
    fight = _state([caster, held], [], rest=Rest.LONG)
    fight.apply_condition(held, Condition(name=RESTRAINED, source=_make_adversary()))

    use_free_abilities(caster, fight, limit=1)

    assert fight.has_condition(held, RESTRAINED) is False
    assert fight.token_count(caster, RESTORATION_TOKENS) == 2


def test_a_token_never_lifts_a_condition_the_party_put_there():
    """Wild Fortress shelters two PCs on purpose; clearing that would be a bug."""
    caster = _make_level_6_pc(domain_cards_loadout=[RESTORATION])
    sheltered = _make_level_6_pc(name="Sheltered", domain_cards_loadout=[])
    fight = _state([caster, sheltered], [], rest=Rest.LONG)
    fight.apply_condition(sheltered, Condition(name=SHELTERED, source=caster))

    use_free_abilities(caster, fight, limit=1)

    assert fight.has_condition(sheltered, SHELTERED) is True
    assert fight.token_count(caster, RESTORATION_TOKENS) == 3


def test_restoration_needs_a_spellcast_trait():
    """It is a Spell, and the size of its pool is a number the PC doesn't have."""
    caster = _make_level_6_pc(domain_cards_loadout=[RESTORATION], spellcast_trait="")
    hurt = _make_level_6_pc(name="Hurt", domain_cards_loadout=[])
    hurt.mark_hp(6)
    fight = _state([caster, hurt], [], rest=Rest.LONG)

    use_free_abilities(caster, fight, limit=1)

    assert hurt.hp_marked == 6


# --- Zone of Protection ------------------------------------------------------


def _cast_the_zone(caster, target, fight):
    """Raise the zone on a roll that certainly beats the printed 16."""
    with patch("content.spellcast.roll_duality", return_value=_roll(12, 11, 16)):
        return zone_of_protection(caster, target, fight)


def test_raising_the_zone_puts_the_die_at_one():
    caster = _make_level_6_pc(domain_cards_loadout=[ZONE_OF_PROTECTION])
    target = _make_adversary()
    fight = _state([caster], [target], rest=Rest.LONG)

    result = _cast_the_zone(caster, target, fight)

    assert result is not None
    assert fight.token_count(caster, ZONE_DIE) == 1


def test_a_failed_cast_keeps_the_per_long_rest_use():
    """"Once per long rest **on a success**" - the page says so outright."""
    caster = _make_level_6_pc(domain_cards_loadout=[ZONE_OF_PROTECTION])
    target = _make_adversary()
    fight = _state([caster], [target], rest=Rest.LONG)

    with patch("content.spellcast.roll_duality", return_value=_roll(2, 3, 16)):
        zone_of_protection(caster, target, fight)

    assert fight.token_count(caster, ZONE_DIE) == 0
    assert fight.can_use_once_per_rest(caster, ZONE_OF_PROTECTION, long=True) is True


def test_the_zone_declines_while_one_already_stands():
    caster = _make_level_6_pc(domain_cards_loadout=[ZONE_OF_PROTECTION])
    target = _make_adversary()
    fight = _state([caster], [target], rest=Rest.LONG)
    fight.set_token(caster, ZONE_DIE, 3)

    assert _cast_the_zone(caster, target, fight) is None


def test_the_zone_soaks_the_dies_value_and_then_grows():
    caster = _make_level_6_pc(domain_cards_loadout=[ZONE_OF_PROTECTION])
    allies = [_make_level_6_pc(name=f"Ally {n}") for n in range(3)]
    fight = _state([caster, *allies], [], rest=Rest.LONG)
    fight.set_token(caster, ZONE_DIE, 3)

    with patch("random.random", return_value=0.0):  # certainly inside the band
        taken = party_damage_reduction(allies[0], 10, fight)

    assert taken == 3
    assert fight.token_count(caster, ZONE_DIE) == 4


def test_a_pc_outside_the_zone_is_not_covered_and_the_die_does_not_move():
    caster = _make_level_6_pc(domain_cards_loadout=[ZONE_OF_PROTECTION])
    allies = [_make_level_6_pc(name=f"Ally {n}") for n in range(3)]
    fight = _state([caster, *allies], [], rest=Rest.LONG)
    fight.set_token(caster, ZONE_DIE, 3)

    with patch("random.random", return_value=0.99):  # certainly outside
        taken = party_damage_reduction(allies[0], 10, fight)

    assert taken == 0
    assert fight.token_count(caster, ZONE_DIE) == 3


def test_the_zone_fades_after_the_hit_it_reduces_by_six():
    caster = _make_level_6_pc(domain_cards_loadout=[ZONE_OF_PROTECTION])
    allies = [_make_level_6_pc(name=f"Ally {n}") for n in range(3)]
    fight = _state([caster, *allies], [], rest=Rest.LONG)
    fight.set_token(caster, ZONE_DIE, 6)

    with patch("random.random", return_value=0.0):
        taken = party_damage_reduction(allies[0], 20, fight)

    assert taken == 6
    assert fight.token_count(caster, ZONE_DIE) == 0


def test_the_zone_reduces_before_the_thresholds_are_read():
    """Which is what makes the die worth more than its face."""
    caster = _make_level_6_pc(domain_cards_loadout=[ZONE_OF_PROTECTION])
    allies = [_make_level_6_pc(name=f"Ally {n}") for n in range(3)]
    fight = _state([caster, *allies], [], rest=Rest.LONG)
    fight.set_token(caster, ZONE_DIE, 4)

    with patch("random.random", return_value=0.0):
        # 12 is over the ally's Major threshold of 9 and would mark 2 HP; the
        # zone takes it to 8, which marks 1.
        marked = allies[0].take_damage(12, fight)

    assert marked == 1


# --- Healing Strike ----------------------------------------------------------


def test_a_landed_blow_clears_an_ally_hit_point_for_two_hope():
    attacker = _make_level_7_pc(name="Striker", domain_cards_loadout=[HEALING_STRIKE])
    hurt = _make_level_7_pc(name="Hurt", hp_max=8)
    spare = _make_level_7_pc(name="Spare")
    other = _make_level_7_pc(name="Other")
    hurt.hp_marked = 6  # two unmarked, so at the floor
    target = _make_adversary()
    fight = _rested_state([attacker, hurt, spare, other], [target])

    with patch("domain_cards.splendor.random.random", return_value=0.0):
        apply_on_hit(attacker, target, _landed_hit(), fight)

    assert hurt.hp_marked == 5
    assert attacker.hope_marked == 4


def test_the_heal_declines_for_an_ally_who_is_merely_dented():
    attacker = _make_level_7_pc(name="Striker", domain_cards_loadout=[HEALING_STRIKE])
    dented = _make_level_7_pc(name="Dented", hp_max=8)
    spare = _make_level_7_pc(name="Spare")
    other = _make_level_7_pc(name="Other")
    dented.hp_marked = 1
    target = _make_adversary()
    fight = _rested_state([attacker, dented, spare, other], [target])

    with patch("domain_cards.splendor.random.random", return_value=0.0):
        apply_on_hit(attacker, target, _landed_hit(), fight)

    assert dented.hp_marked == 1
    assert attacker.hope_marked == 6


def test_the_heal_declines_without_the_two_hope():
    attacker = _make_level_7_pc(
        name="Striker", domain_cards_loadout=[HEALING_STRIKE], hope_marked=1
    )
    hurt = _make_level_7_pc(name="Hurt", hp_max=8)
    spare = _make_level_7_pc(name="Spare")
    other = _make_level_7_pc(name="Other")
    hurt.hp_marked = 6
    target = _make_adversary()
    fight = _rested_state([attacker, hurt, spare, other], [target])

    with patch("domain_cards.splendor.random.random", return_value=0.0):
        apply_on_hit(attacker, target, _landed_hit(), fight)

    assert hurt.hp_marked == 6
    assert attacker.hope_marked == 1


# --- Splendor-Touched --------------------------------------------------------


def test_the_wound_is_paid_for_in_hope_while_near_death():
    holder = _make_level_7_pc(domain_cards_loadout=[SPLENDOR_TOUCHED])
    fight = _rested_state([holder], [])
    holder.hp_marked = 6  # two unmarked

    assert soften_damage(holder, 25, 2, fight) == 0
    assert holder.hope_marked == 4
    assert holder.stress_marked == 0


def test_nothing_is_converted_while_the_holder_is_healthy():
    holder = _make_level_7_pc(domain_cards_loadout=[SPLENDOR_TOUCHED])
    fight = _rested_state([holder], [])

    assert soften_damage(holder, 25, 3, fight) == 3
    assert holder.hope_marked == 6
    assert fight.can_use_once_per_rest(holder, SPLENDOR_TOUCHED, long=True) is True


def test_stress_is_marked_only_when_it_keeps_the_holder_standing():
    """No Hope left, and the hit would take the last two HP."""
    holder = _make_level_7_pc(domain_cards_loadout=[SPLENDOR_TOUCHED], hope_marked=0)
    fight = _rested_state([holder], [])
    holder.hp_marked = 6  # two unmarked, and the hit costs two

    assert soften_damage(holder, 25, 2, fight) == 0
    assert holder.stress_marked == 2


def test_a_survivable_wound_is_taken_rather_than_stressed_for():
    holder = _make_level_7_pc(domain_cards_loadout=[SPLENDOR_TOUCHED], hope_marked=0)
    fight = _rested_state([holder], [])
    holder.hp_marked = 6  # two unmarked, and the hit costs only one

    assert soften_damage(holder, 12, 1, fight) == 1
    assert holder.stress_marked == 0
    assert fight.can_use_once_per_rest(holder, SPLENDOR_TOUCHED, long=True) is True


def test_the_conversion_is_once_per_long_rest():
    holder = _make_level_7_pc(domain_cards_loadout=[SPLENDOR_TOUCHED])
    fight = _rested_state([holder], [])
    holder.hp_marked = 6

    assert soften_damage(holder, 25, 2, fight) == 0
    assert soften_damage(holder, 25, 2, fight) == 2


# --- Shield Aura -------------------------------------------------------------


def _auraed(**overrides):
    caster = _make_level_8_pc(name="Seraph", domain_cards_loadout=[SHIELD_AURA])
    frail = _make_level_8_pc(name="Frail", hp_marked=5, **overrides)
    sturdy = _make_level_8_pc(name="Sturdy")
    return caster, frail, sturdy, _rested_state(
        [caster, frail, sturdy], [_make_adversary()]
    )


def test_shield_aura_goes_on_the_frailest_ally():
    caster, frail, sturdy, fight = _auraed()

    assert use_free_abilities(caster, fight, 1) == [SHIELD_AURA]
    assert fight.token_count(frail, SHIELD_AURA_WORN) == 1
    assert fight.token_count(sturdy, SHIELD_AURA_WORN) == 0
    assert fight.token_count(caster, SHIELD_AURA_WORN) == 0
    assert caster.stress_marked == 1


def test_shield_aura_holds_on_one_creature_at_a_time():
    caster, _, _, fight = _auraed()

    assert use_free_abilities(caster, fight, 1) == [SHIELD_AURA]
    assert use_free_abilities(caster, fight, 1) == []


def test_the_aura_drops_a_hit_a_further_threshold():
    caster, frail, _, fight = _auraed()
    use_free_abilities(caster, fight, 1)

    marked = ally_soften_damage(frail, 25, 2, fight, DamageType.PHYSICAL, True)

    assert marked == 1
    assert fight.token_count(frail, SHIELD_AURA_WORN) == 1


def test_the_aura_answers_nothing_where_no_armor_slot_was_marked():
    """Direct damage, or a PC with no slots free - the card's trigger, literally."""
    caster, frail, _, fight = _auraed()
    use_free_abilities(caster, fight, 1)

    assert ally_soften_damage(frail, 25, 2, fight, DamageType.PHYSICAL, False) == 2


def test_the_aura_fades_when_it_takes_a_hit_to_nothing():
    caster, frail, _, fight = _auraed()
    use_free_abilities(caster, fight, 1)

    assert ally_soften_damage(frail, 12, 1, fight, DamageType.PHYSICAL, True) == 0
    assert fight.token_count(frail, SHIELD_AURA_WORN) == 0


def test_a_hit_already_marking_nothing_neither_ends_nor_charges_the_aura():
    caster, frail, _, fight = _auraed()
    use_free_abilities(caster, fight, 1)

    assert ally_soften_damage(frail, 12, 0, fight, DamageType.PHYSICAL, True) == 0
    assert fight.token_count(frail, SHIELD_AURA_WORN) == 1


def test_the_aura_answers_only_for_whoever_wears_it():
    caster, _, sturdy, fight = _auraed()
    use_free_abilities(caster, fight, 1)

    assert ally_soften_damage(sturdy, 25, 2, fight, DamageType.PHYSICAL, True) == 2


# --- Stunning Sunlight -------------------------------------------------------


def _sunlit(adversaries: int, **overrides):
    caster = _make_level_8_pc(domain_cards_loadout=[STUNNING_SUNLIGHT], **overrides)
    field = _field(adversaries)
    return caster, field, _rested_state([caster], field)


def test_stunning_sunlight_burns_one_target_per_hope():
    caster, field, fight = _sunlit(6, hope_marked=2)

    assert take_action(caster, field[0], fight) is not None

    assert caster.hope_marked == 0
    assert sum(1 for a in field if a.hp_marked > 0) == 2


def test_stunning_sunlight_is_capped_by_the_targets_it_beat():
    """Hope is never spent on a target the roll never reached."""
    caster, field, fight = _sunlit(1)

    take_action(caster, field[0], fight)

    assert caster.hope_marked == 5


def test_stunning_sunlight_declines_with_no_hope():
    caster, field, fight = _sunlit(4, hope_marked=0)

    assert take_action(caster, field[0], fight) is None


def test_a_target_that_fails_its_reaction_roll_is_stunned():
    caster, field, fight = _sunlit(6, hope_marked=2)

    with patch("domain_cards.splendor.roll_d20") as rolled:
        rolled.return_value.is_success = False
        take_action(caster, field[0], fight)

    assert sum(1 for a in field if fight.has_condition(a, STUNNED)) == 2


def test_a_target_that_saves_takes_damage_and_is_not_stunned():
    caster, field, fight = _sunlit(6, hope_marked=2)

    with patch("domain_cards.splendor.roll_d20") as rolled:
        rolled.return_value.is_success = True
        take_action(caster, field[0], fight)

    assert not any(fight.has_condition(a, STUNNED) for a in field)
    assert sum(1 for a in field if a.hp_marked > 0) == 2


# --- Overwhelming Aura -------------------------------------------------------


def _auraing(**overrides):
    caster = _make_level_8_pc(
        level=9, domain_cards_loadout=[OVERWHELMING_AURA], **overrides
    )
    adversary = _make_adversary()
    return caster, adversary, _rested_state([caster], [adversary])


def test_the_aura_goes_up_for_two_hope():
    caster, adversary, fight = _auraing()

    with _succeeding(OVERWHELMING_AURA_DIFFICULTY):
        assert overwhelming_aura(caster, adversary, fight) is not None

    assert fight.token_count(caster, AURA_STANDING) == 1
    assert caster.hope_marked == 6 - OVERWHELMING_AURA_HOPE


def test_an_adversary_pays_a_stress_for_aiming_at_the_caster():
    caster, adversary, fight = _auraing()
    fight.set_token(caster, AURA_STANDING, 1)

    overwhelming_aura_costs(caster, adversary, _roll(9, 4, 5), fight)

    assert adversary.stress_marked == 1


def test_the_stress_is_owed_on_a_miss_as_much_as_on_a_hit():
    """The trigger is being aimed at, which is why the hook fires either way."""
    caster, adversary, fight = _auraing()
    fight.set_token(caster, AURA_STANDING, 1)

    apply_on_targeted(caster, adversary, _roll(2, 3, 20), fight)

    assert adversary.stress_marked == 1


def test_no_aura_costs_an_adversary_nothing():
    caster, adversary, fight = _auraing()

    apply_on_targeted(caster, adversary, _roll(9, 4, 5), fight)

    assert adversary.stress_marked == 0


def test_the_aura_declines_while_one_already_stands():
    caster, adversary, fight = _auraing()
    fight.set_token(caster, AURA_STANDING, 1)

    with _succeeding(OVERWHELMING_AURA_DIFFICULTY):
        assert overwhelming_aura(caster, adversary, fight) is None


def test_the_aura_declines_without_the_two_hope():
    caster, adversary, fight = _auraing(hope_marked=1)

    with _succeeding(OVERWHELMING_AURA_DIFFICULTY):
        assert overwhelming_aura(caster, adversary, fight) is None


def test_a_failed_cast_raises_nothing_and_keeps_the_hope():
    caster, adversary, fight = _auraing()

    with patch(
        "content.spellcast.roll_duality",
        return_value=_roll(2, 3, OVERWHELMING_AURA_DIFFICULTY),
    ):
        result = overwhelming_aura(caster, adversary, fight)

    assert result is not None and not result.attack_roll.is_success
    assert fight.token_count(caster, AURA_STANDING) == 0
    assert caster.hope_marked == 6


def test_the_presence_clause_is_declared_as_a_gap():
    """`gain_trait_bonus` grants to every trait at once, so one trait needs more."""
    assert assess(OVERWHELMING_AURA).is_partial is True
    assert "Presence" in " ".join(assess(OVERWHELMING_AURA).unmodelled)


# --- Salvation Beam ----------------------------------------------------------


def _beaming(*marked: int, **overrides):
    """A caster and one ally per entry, each with that many Hit Points marked."""
    caster = _make_level_8_pc(
        level=9, name="Seraph", domain_cards_loadout=[SALVATION_BEAM], **overrides
    )
    allies = []
    for index, hurt in enumerate(marked):
        ally = _make_level_8_pc(level=9, name=f"Ally {index}")
        ally.mark_hp(hurt)
        allies.append(ally)
    target = _make_adversary()
    return caster, allies, _rested_state([caster, *allies], [target]), target


def test_the_beam_spends_stress_and_clears_hit_points():
    caster, allies, fight, target = _beaming(4, 4)

    with _succeeding(SALVATION_BEAM_DIFFICULTY):
        assert salvation_beam(caster, target, fight) is not None

    # Five of six Stress marked, one held back by the shared last-slot rule.
    assert caster.stress_marked == 5
    assert sum(ally.hp_marked for ally in allies) == 8 - 5


def test_each_point_goes_to_whoever_is_worst_off():
    caster, allies, fight, target = _beaming(3, 1, stress_marked=4)

    with _succeeding(SALVATION_BEAM_DIFFICULTY):
        salvation_beam(caster, target, fight)

    # One point to spend, and it goes to the ally with three marked.
    assert allies[0].hp_marked == 2
    assert allies[1].hp_marked == 1


def test_the_beam_stops_once_there_is_nothing_left_to_clear():
    caster, allies, fight, target = _beaming(1)

    with _succeeding(SALVATION_BEAM_DIFFICULTY):
        salvation_beam(caster, target, fight)

    assert allies[0].hp_marked == 0
    assert caster.stress_marked == 1


def test_the_beam_declines_for_a_party_with_nothing_marked():
    caster, allies, fight, target = _beaming(0)

    assert salvation_beam(caster, target, fight) is None
    assert caster.stress_marked == 0


def test_the_beam_declines_when_no_stress_can_be_paid():
    caster, allies, fight, target = _beaming(4, stress_marked=5)

    assert salvation_beam(caster, target, fight) is None


def test_the_caster_is_not_one_of_the_beams_targets():
    """"A line of **allies**" - Rune Ward's and Life Ward's reading of the word."""
    caster, allies, fight, target = _beaming(4)
    caster.mark_hp(6)

    with _succeeding(SALVATION_BEAM_DIFFICULTY):
        salvation_beam(caster, target, fight)

    assert caster.hp_marked == 6


# --- Invigoration ------------------------------------------------------------

# Any per-rest ability at all: the card looks for a *spent use*, and never asks
# what it was.
A_SPENT_CARD = "Towering Stalk"


def _invigorating(**overrides):
    caster = _make_level_8_pc(
        level=10, name="Seraph", domain_cards_loadout=[INVIGORATION], **overrides
    )
    ally = _make_level_8_pc(level=10, name="Ally")
    return caster, ally, _rested_state([caster, ally], [])


def test_a_six_hands_a_spent_use_back():
    caster, ally, fight = _invigorating()
    fight.use_once_per_rest(ally, A_SPENT_CARD)

    with patch("domain_cards.splendor.random.randint", return_value=6):
        assert invigoration(caster, fight) is True

    assert fight.can_use_once_per_rest(ally, A_SPENT_CARD) is True


def test_nothing_comes_back_without_a_six_and_the_hope_is_gone():
    caster, ally, fight = _invigorating()
    fight.use_once_per_rest(ally, A_SPENT_CARD)

    with patch("domain_cards.splendor.random.randint", return_value=1):
        assert invigoration(caster, fight) is True

    assert fight.can_use_once_per_rest(ally, A_SPENT_CARD) is False
    assert caster.hope_marked == INVIGORATION_HOPE_FLOOR


def test_the_pool_is_drawn_to_the_floor_and_one_die_is_rolled_per_hope():
    caster, ally, fight = _invigorating()
    fight.use_once_per_rest(ally, A_SPENT_CARD)

    with patch("domain_cards.splendor.random.randint", return_value=6) as rolled:
        invigoration(caster, fight)

    assert caster.hope_marked == INVIGORATION_HOPE_FLOOR
    assert rolled.call_count == 6 - INVIGORATION_HOPE_FLOOR


def test_the_casters_own_spent_use_is_reachable():
    """'You **or** an ally' - unlike most of this domain, it can pay itself."""
    caster, ally, fight = _invigorating()
    fight.use_once_per_rest(caster, A_SPENT_CARD)

    with patch("domain_cards.splendor.random.randint", return_value=6):
        invigoration(caster, fight)

    assert fight.can_use_once_per_rest(caster, A_SPENT_CARD) is True


def test_it_declines_while_nobody_has_spent_anything():
    caster, ally, fight = _invigorating()

    assert invigoration(caster, fight) is False
    assert caster.hope_marked == 6


def test_it_declines_at_the_hope_floor():
    caster, ally, fight = _invigorating(hope_marked=INVIGORATION_HOPE_FLOOR)
    fight.use_once_per_rest(ally, A_SPENT_CARD)

    assert invigoration(caster, fight) is False
    assert caster.hope_marked == INVIGORATION_HOPE_FLOOR


# --- Resurrection ------------------------------------------------------------


def _resurrecting(**overrides):
    caster = _make_level_8_pc(
        level=10, name="Seraph", domain_cards_loadout=[RESURRECTION], **overrides
    )
    fallen = _make_level_8_pc(level=10, name="Fallen")
    target = _make_adversary()
    return caster, fallen, target, _rested_state([caster, fallen], [target])


def _down(pc):
    """A PC who has taken a death move, with everything a death move leaves."""
    pc.hp_marked = pc.hp_max
    pc.stress_marked = pc.stress_max
    pc.unconscious = True
    return pc


def test_a_successful_cast_puts_a_fallen_pc_back_on_their_feet():
    """The one exception to 'an unconscious PC takes no further part' - ruled."""
    caster, fallen, target, fight = _resurrecting()
    _down(fallen)

    with (
        _succeeding(RESURRECTION_DIFFICULTY),
        patch("domain_cards.splendor.random.randint", return_value=6),
    ):
        result = resurrection(caster, target, fight)

    assert result is not None and result.attack_roll.is_success
    assert fallen.is_conscious is True
    assert fallen.hp_marked == 0
    assert fallen.stress_marked == 0
    assert fight.conscious_party == [caster, fallen]


def test_a_six_leaves_the_card_in_hand():
    caster, fallen, target, fight = _resurrecting()
    _down(fallen)

    with (
        _succeeding(RESURRECTION_DIFFICULTY),
        patch("domain_cards.splendor.random.randint", return_value=6),
    ):
        resurrection(caster, target, fight)

    assert fight.token_count(caster, RESURRECTION_VAULTED) == 0


def test_anything_lower_spends_the_card_for_good():
    caster, fallen, target, fight = _resurrecting()
    _down(fallen)

    with (
        _succeeding(RESURRECTION_DIFFICULTY),
        patch("domain_cards.splendor.random.randint", return_value=5),
    ):
        resurrection(caster, target, fight)

    assert fight.token_count(caster, RESURRECTION_VAULTED) == 1

    # Vaulted, so a second casualty gets nothing.
    _down(fallen)
    assert resurrection(caster, target, fight) is None


def test_a_failed_cast_vaults_it_too_and_raises_nobody():
    """'You can't cast Resurrection again for a week' - which is this fight."""
    caster, fallen, target, fight = _resurrecting()
    _down(fallen)

    with patch(
        "content.spellcast.roll_duality",
        return_value=_roll(2, 3, RESURRECTION_DIFFICULTY),
    ):
        result = resurrection(caster, target, fight)

    assert result is not None and not result.attack_roll.is_success
    assert fallen.is_conscious is False
    assert fight.token_count(caster, RESURRECTION_VAULTED) == 1


def test_it_declines_while_the_whole_party_is_standing():
    caster, fallen, target, fight = _resurrecting()

    assert resurrection(caster, target, fight) is None


def test_the_scar_the_death_move_took_is_not_undone():
    caster, fallen, target, fight = _resurrecting()
    _down(fallen)
    fallen.scars = 1

    with (
        _succeeding(RESURRECTION_DIFFICULTY),
        patch("domain_cards.splendor.random.randint", return_value=6),
    ):
        resurrection(caster, target, fight)

    assert fallen.scars == 1


# --- Assessed ----------------------------------------------------------------


def test_the_later_cards_are_modelled():
    for card in (
        RESTORATION,
        ZONE_OF_PROTECTION,
        HEALING_STRIKE,
        SPLENDOR_TOUCHED,
        SHIELD_AURA,
        STUNNING_SUNLIGHT,
        OVERWHELMING_AURA,
        SALVATION_BEAM,
        INVIGORATION,
        RESURRECTION,
    ):
        assert assess(card).status is Status.MODELLED
