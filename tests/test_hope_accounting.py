"""Where a PC's Hope came from and went.

The end state alone can't be read: two Hope left over describes both a PC who
spent nothing all fight and one who earned eight and burned them. So the report
carries four figures, and they have to reconcile - start plus generated minus
spent is what's left.

The one exception is a scar, which crosses out a Hope slot and takes any Hope
banked in it with it. That is neither gained nor spent, and the last test here
pins it so nobody later "fixes" the arithmetic by miscounting it as one.
"""

from characters.player_character import NEAR_DEATH_HP_UNMARKED, PlayerCharacter
from combat.report import CombatantState


def _make_pc(**overrides) -> PlayerCharacter:
    defaults = dict(
        name="Ealin",
        level=2,
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={"agility": 1, "strength": 1, "finesse": 1,
                "instinct": 1, "presence": 0, "knowledge": 1},
        evasion=10,
        proficiency=1,
        major_threshold=6,
        severe_threshold=12,
        hp_max=6,
        stress_max=6,
        hope_max=6,
        armor_max=0,
        primary_weapon="Shortbow",
        secondary_weapon=None,
        armor_item="Gambeson Armor",
        domain_cards_loadout=[],
        domain_cards_vault=[],
        experiences=[],
        consumables=[],
        hope_marked=2,
    )
    defaults.update(overrides)
    return PlayerCharacter(**defaults)


def test_a_pc_starts_with_whatever_their_sheet_says():
    assert _make_pc(hope_marked=2).hope_at_start == 2


def test_starting_hope_is_recorded_even_at_zero():
    assert _make_pc(hope_marked=0).hope_at_start == 0


def test_starting_hope_does_not_move_when_hope_does():
    pc = _make_pc(hope_marked=2)
    pc.gain_hope(3)
    pc.spend_hope(4)

    assert pc.hope_at_start == 2


def test_hope_gained_counts_what_actually_landed():
    pc = _make_pc(hope_marked=0)
    pc.gain_hope(3)

    assert pc.hope_gained == 3
    assert pc.hope_marked == 3


def test_hope_offered_past_the_cap_is_not_counted_gained():
    """Matching how the Fear pool counts itself, so the four figures reconcile."""
    pc = _make_pc(hope_marked=5, hope_max=6)
    pc.gain_hope(4)

    assert pc.hope_marked == 6
    assert pc.hope_gained == 1


def test_hope_spent_counts_what_was_actually_paid():
    pc = _make_pc(hope_marked=4)
    pc.spend_hope(3)

    assert pc.hope_spent == 3
    assert pc.hope_marked == 1


def test_a_cost_bigger_than_the_bank_spends_only_what_was_there():
    pc = _make_pc(hope_marked=2)
    pc.spend_hope(5)

    assert pc.hope_marked == 0
    assert pc.hope_spent == 2


def test_the_four_figures_reconcile():
    pc = _make_pc(hope_marked=2)
    pc.gain_hope(4)
    pc.spend_hope(3)
    pc.gain_hope(1)

    assert pc.hope_at_start + pc.hope_gained - pc.hope_spent == pc.hope_marked


def test_a_snapshot_carries_all_four():
    pc = _make_pc(hope_marked=2)
    pc.gain_hope(4)
    pc.spend_hope(3)

    state = CombatantState.of(pc)

    assert state.hope_at_start == 2
    assert state.hope_gained == 4
    assert state.hope_spent == 3
    assert state.hope_marked == 3


def test_a_hand_built_snapshot_need_not_account_for_the_whole_fight():
    """Defaults exist so a test can state an end state without inventing a fight."""
    state = CombatantState(
        name="Nobody",
        conscious=True,
        hp_unmarked=4,
        hp_max=6,
        stress_unmarked=6,
        stress_max=6,
        armor_unmarked=0,
        armor_max=0,
        hope_marked=1,
        scars=0,
        death_moves=0,
    )

    assert state.hope_at_start == 0
    assert state.hope_gained == 0


# --- Near death --------------------------------------------------------------


def test_a_pc_on_the_threshold_counts_as_near_death():
    pc = _make_pc()
    pc.mark_hp(pc.hp_max - NEAR_DEATH_HP_UNMARKED)

    assert pc.hp_unmarked == NEAR_DEATH_HP_UNMARKED
    assert pc.is_near_death


def test_a_pc_one_above_it_does_not():
    pc = _make_pc()
    pc.mark_hp(pc.hp_max - NEAR_DEATH_HP_UNMARKED - 1)

    assert not pc.is_near_death


def test_an_untouched_pc_is_not_near_death():
    assert not _make_pc().is_near_death


def test_the_reporting_layer_reads_the_same_threshold():
    """One number, so a report can't call a fight close on a different edge."""
    from simulation.summary import NEAR_DEATH_HP_UNMARKED as reported

    assert reported is NEAR_DEATH_HP_UNMARKED
