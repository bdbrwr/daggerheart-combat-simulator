"""Domain-card tests that belong to no single domain.

Every other `test_domain_cards_<domain>.py` file holds the cards of one domain,
mirroring `domain_cards/`. Four things do not fit that split and live here
instead:

* **The registry lookups.** What is being checked is that a module plus a
  decorator is the whole of adding a card, and that a name in no hook table comes
  back None rather than raising. The cards named are examples, not the subject.
* **The shared Stress rule.** `will_spend_stress` is one rule for every PC Stress
  cost - freely, except the last slot, which waits until 2 or fewer HP are
  unmarked. Every card costing a Stress asks it rather than deciding for itself,
  so it is pinned once here rather than in whichever domain happened to need it.
* **The rolled trait travelling with the roll.** `roll_duality` records the trait
  it was made with and `roll_bonus` carries it to content. Sage-Touched is the
  card that could not be written without it, but the machinery is the dice's.
* **The loadout gate every *X*-Touched card declares as a gap** - a ruling that
  spans nine cards in nine domains.
"""

import random

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.state import FightState
from content import Status, assess, find_guard, find_severity_response
from content.spellcast import spellcast
from dice.damage import DiceGroup
from dice.duality import roll_duality
from domain_cards.arcana import ARCANA_TOUCHED
from domain_cards.blade import BLADE_TOUCHED, get_back_up
from domain_cards.bone import BONE_TOUCHED
from domain_cards.valor import i_am_your_shield
from items.registry import find_weapon
from items.weapons import attack_with

GET_BACK_UP = "Get Back Up"
I_AM_YOUR_SHIELD = "I Am Your Shield"


def _make_character(**overrides) -> PlayerCharacter:
    """A level 1 sheet, the one the oldest cards were measured against."""
    defaults = dict(
        name="Test PC",
        level=1,
        # Names nothing has implemented, on purpose. A class or subclass with
        # damage responses of its own (Stalwart's Iron Will marks a second Armor
        # Slot; Unstoppable softens every hit) would stack with whatever is being
        # measured. Invented names keep each case about one thing.
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Human",
        community="Wanderborne",
        traits={"agility": 0, "strength": 2, "finesse": 0, "instinct": 1, "presence": 1, "knowledge": -1},
        evasion=9,
        proficiency=1,
        major_threshold=6,
        severe_threshold=12,
        hp_max=7,
        stress_max=6,
        hope_max=6,
        armor_max=0,  # off unless a test is about armor
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


def _make_caster(**overrides) -> PlayerCharacter:
    """A level 7 sheet with a Spellcast trait, for the cases that make rolls."""
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


# --- The registry ------------------------------------------------------------


def test_cards_are_discovered_without_being_registered_by_hand():
    """Writing the module and decorating the function is the whole of adding one."""
    assert find_severity_response(GET_BACK_UP) is get_back_up
    assert find_guard(I_AM_YOUR_SHIELD) is i_am_your_shield


def test_a_card_that_registered_no_such_hook_is_skipped_rather_than_an_error():
    """A lookup asks one hook table, and most content isn't in it.

    Whirlwind is implemented and is not a guard; a name nobody has written is in
    no table at all. Both have to come back None rather than raising, because a
    sheet is allowed to carry either.
    """
    assert find_severity_response("A Card Nobody Has Written") is None
    assert find_guard("Whirlwind") is None


def test_a_pc_carrying_an_unimplemented_card_still_takes_damage_normally():
    character = _make_character(
        domain_cards_loadout=["A Card Nobody Has Written", "Whirlwind"]
    )

    assert character.take_damage(12) == 3


# --- The shared Stress rule --------------------------------------------------
#
# `will_spend_stress` is one rule for every PC Stress cost: freely, except the
# last slot, which waits until 2 or fewer HP are unmarked. Every card asks it
# rather than deciding for itself, so it is pinned here once.


def test_a_pc_spends_stress_freely_while_a_slot_remains():
    character = _make_character(stress_max=3)

    assert character.will_spend_stress(1) is True
    character.mark_stress(1)
    assert character.will_spend_stress(1) is True


def test_a_pc_holds_their_last_stress_slot_while_healthy():
    character = _make_character(stress_max=3, hp_max=7)
    character.mark_stress(2)

    assert character.can_spend_stress(1) is True  # able
    assert character.will_spend_stress(1) is False  # unwilling


def test_a_pc_releases_their_last_stress_slot_when_near_death():
    character = _make_character(stress_max=3, hp_max=7)
    character.mark_stress(2)
    character.mark_hp(5)  # 2 unmarked

    assert character.is_near_death is True
    assert character.will_spend_stress(1) is True


def test_a_cost_bigger_than_the_pool_is_refused_outright():
    character = _make_character(stress_max=2)

    assert character.will_spend_stress(3) is False


def test_a_multi_slot_cost_is_measured_at_the_last_slot_it_would_mark():
    """Two slots free and a cost of two lands on the last one, so the rule bites."""
    character = _make_character(stress_max=3, hp_max=7)
    character.mark_stress(1)

    assert character.will_spend_stress(2) is False
    character.mark_hp(5)
    assert character.will_spend_stress(2) is True


def test_spending_stress_is_not_itself_gated_on_wanting_to():
    """`spend_stress` is the payment; whether to pay is the caller's decision."""
    character = _make_character(stress_max=2, hp_max=7)
    character.mark_stress(1)

    assert character.will_spend_stress(1) is False
    assert character.spend_stress(1) is True
    assert character.stress_marked == 2


# --- The trait travelling with the roll --------------------------------------


def test_a_duality_roll_records_the_trait_it_was_made_with():
    random.seed(1)
    assert roll_duality(trait="instinct").trait == "instinct"


def test_a_roll_with_no_trait_named_records_none():
    """A hand-built result has no character behind it, which is a real answer."""
    random.seed(1)
    assert roll_duality().trait == ""


def test_a_spellcast_roll_carries_the_trait_it_rolled():
    caster = _make_caster()
    target = _make_adversary()
    fight = _state([caster], [target])

    assert spellcast(caster, target, fight).trait == "knowledge"


def test_a_named_trait_reaches_the_roll_rather_than_the_spellcast_trait():
    """Grace's Troublemaker rolls Presence; the roll should say so."""
    caster = _make_caster()
    target = _make_adversary()
    fight = _state([caster], [target])

    assert spellcast(caster, target, fight, trait="presence").trait == "presence"


def test_a_weapon_swing_carries_the_weapons_own_trait():
    attacker = _make_caster()
    target = _make_adversary()
    fight = _state([attacker], [target])
    weapon = find_weapon(attacker.primary_weapon)

    result = attack_with(attacker, weapon, target, fight=fight)

    assert result.attack_roll.trait == weapon.trait


# --- The ruling every X-Touched card inherits --------------------------------


def test_every_touched_card_declares_the_loadout_gate_as_a_gap():
    """The user's ruling: carrying the card is proof of the loadout."""
    for card in (ARCANA_TOUCHED, BLADE_TOUCHED, BONE_TOUCHED):
        assert "loadout" in " ".join(assess(card).unmodelled)


# --- The whole of levels 1 and 2 ---------------------------------------------


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
