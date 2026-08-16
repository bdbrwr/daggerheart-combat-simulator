"""Swinging a weapon, and the weapon features that change what a swing rolls.

A weapon is a record now rather than a callable, so these go through the one
shared shape - `attack_with` - with the record looked up by the name a character
sheet would write. Both dice are patched in every case, so nothing here depends
on the RNG: the question is always which pool the weapon asked for, never what
it rolled.

The features are the point of most of it. Reliable, Massive and Powerful are
content registered in features/weapons.py, dispatched scoped to the weapon, so
the cases below double as proof that scoping works - a weapon without the feature
must not pick it up from a party member who has one.
"""

from unittest.mock import patch

from characters.player_character import PlayerCharacter
from dice.common import AdvantageState
from dice.damage import DamageRollResult, DiceGroup
from dice.duality import DualityRollResult
from items.registry import find_weapon
from items.weapons import attack_with


class FakeTarget:
    """A minimal stand-in for the items.weapons.Target protocol.

    Adversary satisfies that protocol too, but a fake keeps these tests to one
    moving part - the weapon - and records what damage it was handed.
    """

    def __init__(self, difficulty: int = 10, features: list[str] | None = None):
        self.difficulty = difficulty
        self.damage_taken: list[int] = []
        # Scanned for content that punishes being hit - the Glass Snake's
        # Armor-Shredding Shards. Empty by default so these stay about the
        # weapon; a test that wants such a feature passes it.
        self.named_features = features or []

    def take_damage(self, amount: int, fight=None) -> int:
        self.damage_taken.append(amount)
        return amount


def _make_attacker(agility: int = 2, proficiency: int = 1) -> PlayerCharacter:
    return PlayerCharacter(
        name="Test PC",
        level=1,
        # Names nothing implements, so no class or subclass feature joins the
        # roll and the arithmetic below stays about the weapon.
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={"agility": agility, "strength": 0, "finesse": 0, "instinct": 0, "presence": 0, "knowledge": 0},
        evasion=9,
        proficiency=proficiency,
        major_threshold=6,
        severe_threshold=12,
        hp_max=7,
        stress_max=6,
        hope_max=6,
        armor_max=3,
        primary_weapon="Broadsword",
        secondary_weapon=None,
        armor_item="Gambeson Armor",
        domain_cards_loadout=[],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
    )


def _duality_result(*, hope: int, fear: int, modifier: int, difficulty: int) -> DualityRollResult:
    return DualityRollResult(
        hope_die_result=hope,
        fear_die_result=fear,
        modifier=modifier,
        advantage_state=AdvantageState.NONE,
        advantage_die_result=None,
        help_dice_results=None,
        difficulty=difficulty,
    )


# --- The record ---------------------------------------------------------------


def test_a_weapon_is_read_off_the_catalogue():
    """The numbers come from items/srd.json, not from a Python literal."""
    broadsword = find_weapon("Broadsword")

    assert broadsword.trait == "agility"
    assert broadsword.damage_die == 8
    assert broadsword.damage_modifier == 0
    assert broadsword.features == ("Reliable",)
    assert broadsword.named_features == ["weapon:Reliable"]


# --- Data entry can't break a lookup ------------------------------------------
#
# Catalogues and sheets are typed by hand, and a lookup that missed on
# capitalisation wouldn't fail loudly - the feature would report as
# unimplemented and silently never fire, which looks exactly like work nobody
# has done. So every one of these entry points folds case and whitespace.


def test_a_weapon_is_found_however_the_sheet_capitalised_it():
    assert find_weapon("greatsword") is find_weapon("Greatsword")
    assert find_weapon("  GREATSWORD  ") is find_weapon("Greatsword")


def test_armor_is_found_however_the_sheet_capitalised_it():
    from items.registry import find_armor

    assert find_armor("gambeson armor") is find_armor("Gambeson Armor")
    assert find_armor("  IronTree   Breastplate Armor ") is find_armor(
        "IronTree Breastplate Armor"
    )


def test_a_catalogues_feature_name_survives_sloppy_spacing():
    """The qualified name has to fold the same way an unqualified one does.

    A feature written "  massive " in a catalogue must reach the same registry
    entry as "Massive", or the weapon would silently lose its feature.
    """
    from content.names import WEAPON, canonical, qualified

    assert canonical(qualified(WEAPON, "  massive ")) == canonical(
        qualified(WEAPON, "Massive")
    )
    assert canonical(qualified(WEAPON, "From  Above")) == canonical(
        qualified(WEAPON, "From Above")
    )


def test_a_namespace_cannot_fold_into_another_kind():
    """Punctuation isn't folded, so armor:Heavy and weapon:Heavy stay apart."""
    from content.names import ARMOR, WEAPON, canonical, qualified

    assert canonical(qualified(ARMOR, "Heavy")) != canonical(qualified(WEAPON, "Heavy"))


# --- Swinging -----------------------------------------------------------------


def test_attack_hit_rolls_and_applies_damage():
    attacker = _make_attacker()
    target = FakeTarget(difficulty=10)
    hit_roll = _duality_result(hope=10, fear=5, modifier=5, difficulty=10)  # total 20, not a crit
    damage_roll = DamageRollResult(dice_groups=[DiceGroup(count=1, sides=8)], die_results=[[7]], modifier=0)

    with (
        patch("items.weapons.roll_duality", return_value=hit_roll) as mock_roll_duality,
        patch("items.weapons.roll_damage", return_value=damage_roll),
    ):
        result = attack_with(attacker, find_weapon("Broadsword"), target)

    assert result.hit is True
    assert result.damage_roll is damage_roll
    assert target.damage_taken == [7]
    # Reliable: +1 to attack rolls, on top of the Agility trait
    assert mock_roll_duality.call_args.kwargs["modifier"] == attacker.traits["agility"] + 1


def test_a_weapon_rolls_the_trait_its_record_names():
    """The Greatsword is Strength, not the Agility the Broadsword rolls."""
    attacker = _make_attacker(agility=2)
    attacker.traits["strength"] = 4
    target = FakeTarget(difficulty=10)
    hit_roll = _duality_result(hope=10, fear=5, modifier=4, difficulty=10)

    with (
        patch("items.weapons.roll_duality", return_value=hit_roll) as mock_roll_duality,
        patch("items.weapons.roll_damage"),
    ):
        attack_with(attacker, find_weapon("Greatsword"), target)

    assert mock_roll_duality.call_args.kwargs["modifier"] == 4  # Strength, no Reliable


def _damage_pool_asked_for(weapon_name: str, attacker, hope: int = 10, fear: int = 5):
    """Run an attack on a hit and hand back the kwargs it passed to roll_damage."""
    target = FakeTarget(difficulty=10)
    hit_roll = _duality_result(hope=hope, fear=fear, modifier=0, difficulty=10)
    damage_roll = DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=8)], die_results=[[5]], modifier=0
    )

    with (
        patch("items.weapons.roll_duality", return_value=hit_roll),
        patch("items.weapons.roll_damage", return_value=damage_roll) as mock_roll_damage,
    ):
        attack_with(attacker, find_weapon(weapon_name), target)

    return mock_roll_damage.call_args.kwargs


# --- Massive and Powerful -----------------------------------------------------


def test_massive_rolls_one_more_die_than_proficiency_and_discards_the_lowest():
    """Greatsword's Massive at Proficiency 2: three d10s, keep the best two.

    The extra die is rolled by raising the pool, and dice/damage.py takes the
    lowest back off - so the count has to be Proficiency + 1, not Proficiency.
    """
    kwargs = _damage_pool_asked_for("Greatsword", _make_attacker(proficiency=2))

    assert kwargs["dice_groups"] == [DiceGroup(count=3, sides=10)]
    assert kwargs["drop_lowest"] == 1
    assert kwargs["modifier"] == 3


def test_massive_scales_the_extra_die_with_proficiency():
    """The +1 is on top of Proficiency at every level, not a fixed pool size."""
    for proficiency in (1, 3, 5):
        kwargs = _damage_pool_asked_for(
            "Greatsword", _make_attacker(proficiency=proficiency)
        )
        assert kwargs["dice_groups"] == [DiceGroup(count=proficiency + 1, sides=10)]
        assert kwargs["drop_lowest"] == 1


def test_powerful_rolls_one_more_die_than_proficiency():
    """Greatstaff's Powerful is the same rule on a d6 with no flat modifier."""
    kwargs = _damage_pool_asked_for("Greatstaff", _make_attacker(proficiency=2))

    assert kwargs["dice_groups"] == [DiceGroup(count=3, sides=6)]
    assert kwargs["drop_lowest"] == 1
    assert kwargs["modifier"] == 0


def test_a_weapon_without_the_feature_rolls_exactly_proficiency_dice():
    """The control: no Massive or Powerful means no extra die and no discard."""
    kwargs = _damage_pool_asked_for("Broadsword", _make_attacker(proficiency=2))

    assert kwargs["dice_groups"] == [DiceGroup(count=2, sides=8)]
    assert kwargs["drop_lowest"] == 0


def test_a_weapons_feature_does_not_leak_onto_another_weapon():
    """The reason weapon features are dispatched scoped to the weapon.

    The same PC swings a Greatsword and then a Shortbow. Massive belongs to the
    Greatsword; if it were summed holder-wide the Shortbow would inherit it.
    """
    attacker = _make_attacker(proficiency=2)
    attacker.traits["strength"] = 2

    massive = _damage_pool_asked_for("Greatsword", attacker)
    plain = _damage_pool_asked_for("Shortbow", attacker)

    assert massive["drop_lowest"] == 1
    assert plain["drop_lowest"] == 0
    assert plain["dice_groups"] == [DiceGroup(count=2, sides=6)]


def test_reliable_does_not_leak_onto_another_weapon():
    """Same scoping question for a roll bonus rather than a damage pool."""
    attacker = _make_attacker(agility=2)
    target = FakeTarget(difficulty=10)
    hit_roll = _duality_result(hope=10, fear=5, modifier=2, difficulty=10)

    with (
        patch("items.weapons.roll_duality", return_value=hit_roll) as mock_roll_duality,
        patch("items.weapons.roll_damage"),
    ):
        attack_with(attacker, find_weapon("Shortbow"), target)

    # Agility alone: the Shortbow has no Reliable, and the Broadsword's isn't
    # the attacker's to carry.
    assert mock_roll_duality.call_args.kwargs["modifier"] == 2


# --- The rest of the shape ----------------------------------------------------


def test_a_hit_reports_the_hp_it_marked():
    """Content that fires on a landed attack keys on HP marked, not damage dealt."""
    attacker = _make_attacker()
    target = FakeTarget(difficulty=10)
    hit_roll = _duality_result(hope=10, fear=5, modifier=5, difficulty=10)
    damage_roll = DamageRollResult(
        dice_groups=[DiceGroup(count=1, sides=8)], die_results=[[7]], modifier=0
    )

    with (
        patch("items.weapons.roll_duality", return_value=hit_roll),
        patch("items.weapons.roll_damage", return_value=damage_roll),
    ):
        result = attack_with(attacker, find_weapon("Broadsword"), target)

    # FakeTarget.take_damage hands back the damage it was given.
    assert result.hp_marked == 7


def test_attack_miss_deals_no_damage():
    attacker = _make_attacker()
    target = FakeTarget(difficulty=20)
    miss_roll = _duality_result(hope=2, fear=1, modifier=0, difficulty=20)  # total 3, well below

    with (
        patch("items.weapons.roll_duality", return_value=miss_roll),
        patch("items.weapons.roll_damage") as mock_roll_damage,
    ):
        result = attack_with(attacker, find_weapon("Broadsword"), target)

    assert result.hit is False
    assert result.damage_roll is None
    assert target.damage_taken == []
    mock_roll_damage.assert_not_called()
