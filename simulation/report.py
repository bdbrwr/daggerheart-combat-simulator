"""Turn a run into something readable at a glance.

Written for the question actually being asked - "is this encounter the fight I
wanted?" - so the headline is the win rate, and everything under it is there to
explain the shape of that number rather than to be comprehensive. A 60% win
rate reached in three rounds without anyone dropping is a different encounter
from a 60% reached in nine with a PC on their last HP, and the report has to
show the difference.

Plain text on purpose: it goes in a terminal next to the numbers being tuned,
and a run whose output needs a viewer is a run nobody looks at.
"""

import textwrap

from simulation.summary import NEAR_DEATH_HP_UNMARKED, SimulationSummary

WIDTH = 78

# COST TO THE PARTY is laid out as two columns, victories against defeats, so
# the two halves of an encounter can be read against each other rather than one
# at a time. Widths chosen to keep the whole table inside WIDTH.
LABEL_WIDTH = 22
COLUMN_WIDTH = 26

# The comparison table: one row per encounter, one column per headline number.
NAME_WIDTH = 28
FIGURE_WIDTH = 12


def format_report(summary: SimulationSummary) -> str:
    """The whole run as one printable block."""
    return "\n".join(
        [
            *_heading(summary),
            "",
            *_outcomes(summary),
            "",
            *_length(summary),
            "",
            *_cost(summary),
            "",
            *_fear(summary),
            *_warnings(summary),
        ]
    )


def _heading(summary: SimulationSummary) -> list[str]:
    """The encounter, and - if its file says - why it's set up this way.

    The notes are printed rather than left in the file because a tuning decision
    is only worth anything next to the numbers it produced. An encounter with
    nothing to say prints nothing.
    """
    seed = f"seed {summary.seed}" if summary.seed is not None else "unseeded"
    lines = [
        "=" * WIDTH,
        f"{summary.encounter_name} - {summary.runs:,} fights ({seed})",
        "=" * WIDTH,
        f"  Party        {', '.join(summary.party) or '(nobody)'}",
        f"  Opposition   {'; '.join(summary.opposition) or '(nothing)'}",
    ]

    if summary.notes:
        lines.append("")
        lines += [f"  {line}" for line in textwrap.wrap(summary.notes, WIDTH - 2)]
    return lines


def _outcomes(summary: SimulationSummary) -> list[str]:
    lines = ["OUTCOMES"]
    for label, records, rate in (
        ("Party victory", summary.victories, summary.win_rate),
        ("Party defeat", summary.defeats, summary.defeat_rate),
        ("Unresolved", summary.unresolved, summary.unresolved_rate),
    ):
        lines.append(f"  {label:<16}{len(records):>8,}   {rate:>6.1%}")
    return lines


def _length(summary: SimulationSummary) -> list[str]:
    """Both round metrics, plus the split that tends to matter most.

    Wins and losses are separated because a party that loses, loses fast, and
    a combined average of the two describes no fight anyone had.
    """
    lines = [
        "FIGHT LENGTH  (resolved fights only)",
        f"  PC rounds      {summary.distribution('pc_rounds').summarize()}",
        f"  GM rounds      {summary.distribution('gm_rounds').summarize()}",
    ]

    victories, defeats = summary.victories, summary.defeats
    if victories:
        won = summary.distribution("pc_rounds", victories)
        lines.append(f"  won in         mean {won.mean:>5.1f} PC rounds   median {won.median:>5.1f}")
    if defeats:
        lost = summary.distribution("pc_rounds", defeats)
        lines.append(f"  lost in        mean {lost.mean:>5.1f} PC rounds   median {lost.median:>5.1f}")
    return lines


def _cost(summary: SimulationSummary) -> list[str]:
    """What the fight cost, won or lost - the half of balance a win rate can't show.

    Both columns are shown even though several rows are definitional on one
    side: in a defeat every PC is unconscious, so their unmarked HP is zero and
    every defeat is a near death. Those rows say so in words rather than being
    dropped, because a column that silently disappears is harder to read than
    one that explains itself - and the rows that aren't definitional (scars, and
    how many adversaries were still standing when the party fell) are exactly
    the ones that say how close a loss was.
    """
    victories, defeats = summary.victories, summary.defeats

    return [
        "COST TO THE PARTY",
        _row("", "victories", "defeats"),
        _row(
            "Fights",
            _share(len(victories), summary.runs),
            _share(len(defeats), summary.runs),
        ),
        _row(
            "Unmarked HP, lowest",
            _spread(summary.distribution("lowest_hp_unmarked", victories)),
            _spread(summary.distribution("lowest_hp_unmarked", defeats)),
        ),
        _row(
            "Unmarked HP, party",
            _spread(summary.distribution("party_hp_unmarked", victories)),
            _spread(summary.distribution("party_hp_unmarked", defeats)),
        ),
        _row(
            "PCs still standing",
            _spread(summary.distribution("pcs_standing", victories)),
            "none, by definition" if defeats else "-",
        ),
        _row(
            "Near death",
            f"{summary.near_death_rate:.1%}" if victories else "-",
            "100%, by definition" if defeats else "-",
        ),
        _row(
            "Adversaries left",
            "none, by definition" if victories else "-",
            _spread(summary.distribution("surviving_adversaries", defeats)),
        ),
        _row("Scars", _total_scars(victories), _total_scars(defeats)),
        f"  (near death = a PC finished on {NEAR_DEATH_HP_UNMARKED} unmarked HP or less)",
    ]


def _row(label: str, victories_cell: str, defeats_cell: str) -> str:
    return f"  {label:<{LABEL_WIDTH}}{victories_cell:<{COLUMN_WIDTH}}{defeats_cell}".rstrip()


def _share(count: int, total: int) -> str:
    if not total:
        return "-"
    return f"{count:,} ({count / total:.1%})"


def _spread(distribution) -> str:
    """A distribution at table width - mean and median only, tails left to the sections above."""
    if not distribution.count:
        return "-"
    return f"mean {distribution.mean:>4.1f}  median {distribution.median:>4.1f}"


def _total_scars(records) -> str:
    if not records:
        return "-"
    return f"{sum(record.scars_gained for record in records):,}"


def _fear(summary: SimulationSummary) -> list[str]:
    """Whether the GM's economy is doing anything.

    Fear spent near zero means extra activations never got bought, which makes
    the encounter easier than the rules allow and is usually a sign the fight
    ends before the pool fills.
    """
    return [
        "FEAR",
        f"  Generated      {summary.distribution('fear_gained').summarize()}",
        f"  Spent          {summary.distribution('fear_spent').summarize()}",
        f"  Left over      {summary.distribution('fear_remaining').summarize()}",
    ]


def format_comparison(summaries: list[SimulationSummary], title: str = "") -> str:
    """Several runs side by side - the table tuning actually gets read off.

    One row per encounter, one column per headline number, so a variation can
    be judged against the thing it varies from without scrolling between two
    full reports. The full reports are still printed above it; this is the
    summary of the summaries.

    Worth knowing when reading it: a single `--seed` seeds every encounter in
    the command, so each variation is fought against the same sequence of dice.
    That's deliberate - it means a difference between two rows is a difference
    between the stat blocks rather than luck, which is what makes a small run
    worth looking at at all.
    """
    if not summaries:
        return ""

    counts = {summary.runs for summary in summaries}
    how_many = f"{counts.pop():,} fights each" if len(counts) == 1 else "varying run counts"
    seeds = {summary.seed for summary in summaries}
    described = f"seed {seeds.pop()}" if len(seeds) == 1 and None not in seeds else "unseeded"

    described_as = f"COMPARISON: {title}" if title else "COMPARISON"
    lines = [
        "=" * WIDTH,
        f"{described_as} - {len(summaries)} variations, {how_many} ({described})",
        "=" * WIDTH,
        _comparison_row("variation", "win rate", "PC rounds", "near death", "unmarked HP"),
    ]

    for summary in summaries:
        victories = summary.victories
        lines.append(
            _comparison_row(
                # The short name: every row repeating the experiment would cost
                # most of a column that's only 28 characters wide.
                summary.variation or summary.encounter_name,
                f"{summary.win_rate:.1%}",
                f"{summary.distribution('pc_rounds').mean:.1f}",
                f"{summary.near_death_rate:.1%}" if victories else "-",
                f"{summary.distribution('lowest_hp_unmarked', victories).mean:.1f}"
                if victories
                else "-",
            )
        )

    lines += [
        "",
        "  Win rate is of every fight run. Near death and unmarked HP are of the",
        "  victories only - a defeat leaves every PC on zero by definition.",
    ]

    stalled = [summary for summary in summaries if summary.unresolved]
    if stalled:
        names = ", ".join(summary.encounter_name for summary in stalled)
        lines += ["", f"  ! Fights hit the action cap in: {names}. See the reports above."]

    return "\n".join(lines)


def _comparison_row(name: str, *figures: str) -> str:
    shortened = name if len(name) < NAME_WIDTH else name[: NAME_WIDTH - 2] + "…"
    cells = "".join(f"{figure:>{FIGURE_WIDTH}}" for figure in figures)
    return f"  {shortened:<{NAME_WIDTH}}{cells}".rstrip()


def _warnings(summary: SimulationSummary) -> list[str]:
    if not summary.unresolved:
        return []
    return [
        "",
        "!" * WIDTH,
        f"  {len(summary.unresolved):,} fights hit the action cap without finishing and are",
        "  excluded from every distribution above. That usually means one side",
        "  can't meaningfully hurt the other - check the stat blocks.",
        "!" * WIDTH,
    ]
