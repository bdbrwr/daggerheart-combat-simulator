"""The end state of a fight, per party member.

Party-wide totals answer questions about the party. These cover the other half:
what each individual character walked out with, which is what says whether an
encounter is evenly hard or reliably brutal to one person - and which is the
state a sequence of encounters would have to carry forward.

Everything here is built by hand or rigged so the outcome is certain. The one
piece of randomness, the scar roll inside a death move, is never asserted on.
"""

import random

from combat.common import FightOutcome
from combat.report import CombatantState, FightResult
from characters.player_character import PlayerCharacter
from simulation.report import format_comparison, format_report
from simulation.summary import FightRecord, SimulationSummary


def _make_pc(name: str = "Kael", **overrides) -> PlayerCharacter:
    defaults = dict(
        name=name,
        level=1,
        character_class="Unwritten Class",
        subclass="Unwritten Subclass",
        ancestry="Unwritten Ancestry",
        community="Unwritten Community",
        traits={
            "agility": 0, "strength": 1, "finesse": 0,
            "instinct": 0, "presence": 0, "knowledge": 0,
        },
        evasion=10,
        proficiency=1,
        major_threshold=6,
        severe_threshold=12,
        hp_max=6,
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
    defaults.update(overrides)
    return PlayerCharacter(**defaults)


def _state(**overrides) -> CombatantState:
    defaults = dict(
        name="Kael",
        conscious=True,
        hp_unmarked=4,
        hp_max=6,
        stress_unmarked=5,
        stress_max=6,
        armor_unmarked=2,
        armor_max=3,
        hope_marked=2,
        scars=0,
        death_moves=0,
    )
    defaults.update(overrides)
    return CombatantState(**defaults)


def _record(states, **overrides) -> FightRecord:
    defaults = dict(
        outcome=FightOutcome.PARTY_VICTORY,
        party_size=len(states),
        pc_actions=4,
        adversary_activations=3,
        gm_turns=3,
        party_hp_unmarked=sum(state.hp_unmarked for state in states),
        lowest_hp_unmarked=min((s.hp_unmarked for s in states), default=0),
        unconscious_pcs=sum(1 for state in states if not state.conscious),
        surviving_adversaries=0,
        fear_gained=2,
        fear_spent=1,
        fear_remaining=1,
        scars_gained=sum(state.scars for state in states),
        party_state=tuple(states),
        death_moves=sum(state.death_moves for state in states),
    )
    defaults.update(overrides)
    return FightRecord(**defaults)


def _summary(records, variation: str = "") -> SimulationSummary:
    return SimulationSummary(
        encounter_name="Rigged",
        party=["Kael"],
        opposition=["Jagged Knife Bandit x1"],
        seed=1,
        records=records,
        variation=variation,
    )


# --- What a PC can say about itself ------------------------------------------


def test_unmarked_is_the_inverse_of_marked_on_every_track():
    pc = _make_pc(hp_marked=2, stress_marked=1, armor_marked=3)

    assert pc.hp_unmarked == 4
    assert pc.stress_unmarked == 5
    assert pc.armor_unmarked == 0


def test_a_fresh_pc_has_made_no_death_moves():
    assert _make_pc().death_moves == 0


def test_going_down_counts_a_death_move():
    random.seed(1)
    pc = _make_pc(hp_max=1, armor_max=0)

    pc.take_damage(20)

    assert pc.death_moves == 1
    assert pc.is_conscious is False


def test_a_death_move_is_counted_whether_or_not_it_scars():
    """A scar is the roll after the move going badly, so the two differ."""
    random.seed(1)
    pc = _make_pc(hp_max=1, armor_max=0, level=1)

    pc.take_damage(20)

    assert pc.death_moves == 1
    assert pc.scars <= pc.death_moves


# --- The snapshot ------------------------------------------------------------


def test_a_snapshot_carries_the_pcs_condition():
    pc = _make_pc(name="Aeloria", hp_marked=2, stress_marked=4, armor_marked=1)

    captured = CombatantState.of(pc)

    assert captured.name == "Aeloria"
    assert captured.conscious is True
    assert captured.hp_unmarked == 4
    assert captured.stress_unmarked == 2
    assert captured.armor_unmarked == 2


def test_a_snapshot_does_not_move_when_the_pc_does():
    """Frozen, and free of any reference back - a run keeps 10,000 of these."""
    pc = _make_pc()
    captured = CombatantState.of(pc)

    pc.mark_hp(3)

    assert captured.hp_unmarked == 6


def test_a_result_reports_one_state_per_pc_in_order():
    party = [_make_pc(name="Aeloria"), _make_pc(name="Artorias")]
    result = FightResult(
        encounter_name="Rigged",
        outcome=FightOutcome.PARTY_VICTORY,
        party=party,
        adversaries=[],
        pc_actions=1,
        adversary_activations=1,
        gm_turns=1,
        fear_gained=0,
        fear_spent=0,
        fear_remaining=0,
        unconscious_pcs=0,
        scars_gained=0,
    )

    assert [state.name for state in result.party_state] == ["Aeloria", "Artorias"]


def test_a_results_death_moves_are_the_partys_between_them():
    party = [_make_pc(name="Aeloria", death_moves=1), _make_pc(name="Luma", death_moves=1)]
    result = FightResult(
        encounter_name="Rigged",
        outcome=FightOutcome.PARTY_DEFEAT,
        party=party,
        adversaries=[],
        pc_actions=1,
        adversary_activations=1,
        gm_turns=1,
        fear_gained=0,
        fear_spent=0,
        fear_remaining=0,
        unconscious_pcs=2,
        scars_gained=0,
    )

    assert result.death_moves == 2


# --- Reading a run one member at a time --------------------------------------


def test_the_members_are_named_in_the_order_they_were_fielded():
    records = [_record([_state(name="Aeloria"), _state(name="Luma")])]

    assert _summary(records).member_names == ["Aeloria", "Luma"]


def test_one_members_figures_are_not_the_other_members():
    records = [
        _record([_state(name="Aeloria", hp_unmarked=1), _state(name="Luma", hp_unmarked=5)]),
        _record([_state(name="Aeloria", hp_unmarked=3), _state(name="Luma", hp_unmarked=5)]),
    ]
    summary = _summary(records)

    assert summary.member_distribution(0, "hp_unmarked").mean == 2.0
    assert summary.member_distribution(0, "hp_unmarked").minimum == 1
    assert summary.member_distribution(1, "hp_unmarked").mean == 5.0


def test_going_down_is_counted_per_member():
    """The point of the whole table: an encounter aimed at one character."""
    records = [
        _record([_state(name="Aeloria", conscious=False), _state(name="Luma")]),
        _record([_state(name="Aeloria", conscious=False), _state(name="Luma")]),
        _record([_state(name="Aeloria"), _state(name="Luma")]),
    ]
    summary = _summary(records)

    assert summary.times_unconscious(0) == 2
    assert summary.times_unconscious(1) == 0
    assert summary.unconscious_rate(0) == 2 / 3
    assert summary.unconscious_rate(1) == 0.0


def test_a_record_with_no_member_state_is_skipped_not_counted_as_zero():
    """A hand-built record isn't a member on nothing left - it's a member unrecorded."""
    records = [_record([_state(hp_unmarked=4)]), FightRecord(
        outcome=FightOutcome.PARTY_VICTORY,
        party_size=1,
        pc_actions=1,
        adversary_activations=1,
        gm_turns=1,
        party_hp_unmarked=0,
        lowest_hp_unmarked=0,
        unconscious_pcs=0,
        surviving_adversaries=0,
        fear_gained=0,
        fear_spent=0,
        fear_remaining=0,
        scars_gained=0,
    )]
    summary = _summary(records)

    assert summary.member_distribution(0, "hp_unmarked").count == 1
    assert summary.member_distribution(0, "hp_unmarked").mean == 4.0


def test_a_run_that_recorded_nothing_per_member_names_nobody():
    summary = _summary([])

    assert summary.member_names == []
    assert summary.unconscious_rate(0) == 0.0


# --- How it reads ------------------------------------------------------------


def _two_members(variation: str = "") -> SimulationSummary:
    return _summary(
        [
            _record(
                [
                    _state(name="Aeloria", conscious=False, hp_unmarked=0),
                    _state(name="Luma", hp_unmarked=5),
                ]
            ),
            _record([_state(name="Aeloria", hp_unmarked=2), _state(name="Luma", hp_unmarked=6)]),
        ],
        variation=variation,
    )


def test_the_report_carries_a_row_for_each_member():
    printed = format_report(_two_members())

    assert "PER PARTY MEMBER" in printed
    assert "Aeloria" in printed
    assert "Luma" in printed


def test_the_report_says_how_often_each_member_went_down():
    printed = format_report(_two_members())
    row = next(line for line in printed.splitlines() if "Aeloria" in line)

    assert "50.0%" in row  # one of the two resolved fights
    assert " 1" in row  # and the count alongside it


def test_a_rare_down_survives_a_rate_that_rounds_to_nothing():
    """The reason the count is there at all.

    One PC on the floor in five thousand fights is 0.02%, which prints as 0.0%.
    "Never happens" and "happens once in five thousand" are different findings,
    and the second is exactly the rare disaster a tuning pass wants to see.
    """
    records = [_record([_state(name="Aeloria")]) for _ in range(4999)]
    records.append(_record([_state(name="Aeloria", conscious=False, hp_unmarked=0)]))
    summary = _summary(records)

    row = next(
        line for line in format_report(summary).splitlines() if "Aeloria" in line
    )

    assert summary.times_unconscious(0) == 1
    assert "0.0%" in row
    assert "1" in row.split("0.0%")[1]  # the count, after the rate that hid it


def test_the_report_counts_death_moves_separately_from_scars():
    """Scars undercount how often a fight went wrong - not every drop scars."""
    summary = _summary(
        [_record([_state(conscious=False, hp_unmarked=0, death_moves=1, scars=0)])]
    )

    printed = format_report(summary)

    assert "Death moves" in printed
    assert "Scars" in printed


def test_a_report_without_member_state_says_so_rather_than_breaking():
    bare = FightRecord(
        outcome=FightOutcome.PARTY_VICTORY,
        party_size=1,
        pc_actions=1,
        adversary_activations=1,
        gm_turns=1,
        party_hp_unmarked=4,
        lowest_hp_unmarked=4,
        unconscious_pcs=0,
        surviving_adversaries=0,
        fear_gained=0,
        fear_spent=0,
        fear_remaining=0,
        scars_gained=0,
    )

    printed = format_report(_summary([bare]))

    assert "no per-member state" in printed


def test_the_comparison_breaks_the_members_out_by_variation():
    printed = format_comparison(
        [_two_members("As printed"), _two_members("One fewer bandit")]
    )

    assert "PER PARTY MEMBER" in printed
    assert "As printed" in printed
    assert "One fewer bandit" in printed
    # Each variation lists every member underneath it.
    assert printed.count("Aeloria") == 2
    assert printed.count("Luma") == 2
