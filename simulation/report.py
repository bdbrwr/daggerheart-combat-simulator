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

from simulation.summary import NEAR_DEATH_HP_REMAINING, SimulationSummary

WIDTH = 78


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
    seed = f"seed {summary.seed}" if summary.seed is not None else "unseeded"
    return [
        "=" * WIDTH,
        f"{summary.encounter_name} - {summary.runs:,} fights ({seed})",
        "=" * WIDTH,
        f"  Party        {', '.join(summary.party) or '(nobody)'}",
        f"  Opposition   {'; '.join(summary.opposition) or '(nothing)'}",
    ]


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
    """What winning cost - the half of balance a win rate alone can't show."""
    lines = ["COST TO THE PARTY"]
    victories = summary.victories

    if victories:
        near = sum(1 for record in victories if record.near_death)
        lines.append(
            f"  Near death     {near:,} of {len(victories):,} wins ({summary.near_death_rate:.1%}) "
            f"ended with a PC on {NEAR_DEATH_HP_REMAINING} HP or less"
        )
        lines.append(f"  HP left on a win  {summary.distribution('lowest_hp_remaining', victories).summarize()}")
    else:
        lines.append("  Near death     no wins to measure")

    scars = sum(record.scars_gained for record in summary.records)
    lines.append(f"  Scars          {scars:,} across {summary.runs:,} fights")
    return lines


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
