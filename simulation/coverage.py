"""How much of a fight the simulator actually runs.

A win rate is only worth reading if you know what produced it. If half of a
character isn't implemented, the party in the simulation is weaker than the
party at the table, and the encounter looks harder than it is - so this block
belongs next to the numbers, not in a file somebody has to go and find.

The same is true of the other side, and more sharply. An adversary whose Fear
feature isn't written is a *weaker* adversary, so an unimplemented stat block
makes an encounter look easier rather than harder. Both sides are printed for
that reason: the two errors point in opposite directions, and a reader who can
only see one has no idea which way a number is wrong.

Four states per named thing, from content/registry.py:

  * modelled          - code runs it (possibly with declared gaps)
  * no effect         - assessed and dismissed: it cannot change a fight
  * insignificant     - assessed and dismissed: it could, by too little to model
  * unimplemented     - nobody has looked at it yet

The distinction the report exists to make is between the dismissals and the last
one. A dismissal costs the results nothing, because somebody looked and said so.
"Unimplemented" costs them something nobody has measured, which is why it is the
only state that prints a warning.

The two dismissals are kept apart because they are different claims - "this
cannot matter" versus "this matters by about a point of damage" - and a reader
deciding how far to trust a win rate should be able to see which was made.

## How much of it prints

Three levels, chosen on the command line:

  * NONE    - `--no-coverage`. No block at all.
  * SUMMARY - the default. The three states that mean something *isn't* running:
              no effect, insignificant, unimplemented. Modelled content is left
              out, and so are the gaps declared on it.
  * FULL    - `--full-coverage`. Everything, modelled counts and declared gaps
              included.

Both dismissals print one line per name with the opening sentence of the reason
recorded against it. A dismissal's whole content is its reasoning - "this cannot
matter" and "this matters by about a point of damage" are claims somebody should
be able to check and disagree with - so a bare count would be asking the reader
to take it on trust. Unimplemented stays a plain list of names, because there is
nothing to say about it yet: that's what unimplemented means.

SUMMARY is the default because the block is read to answer one question - what
is missing from this fight? - and the modelled half answers the opposite one. In
a real party the declared gaps alone run to twenty-odd lines, which buries the
handful of entries a reader actually has to act on. They are recorded where the
content is registered and printed in full on request; nothing is lost, it just
isn't in the way.
"""

from enum import Enum

from content.registry import Status, assess_all

WIDTH = 78

# The narrowest the combatant-name column gets. It widens to fit the longest name
# actually in the block - "Jagged Knife Bandit" is 19 characters and a fixed 18
# left it touching the counts with no gap at all. Names come from stat blocks and
# character sheets, so nothing here can assume a bound on them.
NAME_WIDTH = 18
NAME_GUTTER = 2

LABEL_WIDTH = 16
INDENT = " " * 6


class CoverageDetail(Enum):
    """How much of the coverage block to print."""

    NONE = "none"
    SUMMARY = "summary"
    FULL = "full"


def format_coverage(party, adversaries=(), detail: CoverageDetail = CoverageDetail.SUMMARY) -> str:
    """The coverage block for one fight, as printed under a report.

    `adversaries` is optional so a caller with only a party - a test, or any
    report that predates the GM side existing - still gets the block it had.

    Returns an empty string at NONE, so a caller can print whatever comes back
    without asking which level it requested.
    """
    if detail is CoverageDetail.NONE:
        return ""
    if not party and not adversaries:
        return "COVERAGE\n  (nobody in the fight)"

    # `assessed_features`, not `named_features`: coverage asks how much of a
    # character the simulator runs, which includes their weapon's features even
    # though those are scoped to the weapon rather than dispatched holder-wide.
    assessed = [
        (pc.name, assess_all(pc.assessed_features), pc.not_modelled) for pc in party
    ]
    opposition = _distinct(adversaries)

    heading = (
        "COVERAGE  (how much of each combatant the simulator runs)"
        if detail is CoverageDetail.FULL
        else "COVERAGE  (what isn't running; --full-coverage for the rest)"
    )
    lines = [heading]

    # One column width for the whole block, so the party's counts and the
    # opposition's line up with each other rather than each side being tidy on
    # its own.
    width = _name_column([name for name, _, _ in assessed] + [name for name, _ in opposition])

    if party:
        lines.append("  party")
        for name, assessments, excluded in assessed:
            lines.extend(_for_combatant(name, assessments, excluded, detail, width))
    else:
        lines.append("  party            (nobody)")

    if opposition:
        lines.append("  opposition")
        for name, assessments in opposition:
            lines.extend(_for_combatant(name, assessments, {}, detail, width))

    everything = [a for _, a, _ in assessed] + [a for _, a in opposition]
    if any(_with_status(a, Status.UNIMPLEMENTED) for a in everything):
        lines += [
            "",
            "  Unimplemented is not the same as no effect: it's work not done. On the",
            "  party's side every entry makes them weaker here than at a table; on the",
            "  opposition's it makes the encounter easier. The two don't cancel out.",
        ]
    return "\n".join(lines)


def _distinct(adversaries) -> list:
    """One row per stat block, not per body on the field.

    Three Jagged Knife Bandits are three copies of one definition, and printing
    the same missing feature three times would say nothing the first line
    didn't. Keyed by name, which is what the registry keys on too.
    """
    seen: dict[str, list] = {}
    for adversary in adversaries:
        if adversary.name not in seen:
            seen[adversary.name] = assess_all(adversary.named_features)
    return list(seen.items())


def _name_column(names) -> int:
    """How wide the name column has to be for every name to keep its gutter."""
    longest = max((len(name) for name in names), default=0)
    return max(NAME_WIDTH, longest + NAME_GUTTER)


def _for_combatant(name, assessments, excluded, detail, width) -> list[str]:
    """One combatant's tally, then the detail worth naming."""
    modelled = _with_status(assessments, Status.MODELLED)
    dismissed = _with_status(assessments, Status.NO_COMBAT_EFFECT)
    minor = _with_status(assessments, Status.INSIGNIFICANT_COMBAT_EFFECT)
    missing = _with_status(assessments, Status.UNIMPLEMENTED)

    # The modelled count is the one figure that says what *is* running, so it
    # only appears at FULL. The other three are the point of the summary.
    counted = f"{len(modelled)} modelled  " if detail is CoverageDetail.FULL else ""
    lines = [
        f"    {name:<{width}}{counted}"
        f"{len(dismissed)} no effect  {len(minor)} insignificant  "
        f"{len(missing)} unimplemented"
    ]

    if missing:
        lines.append(_detail("unimplemented", ", ".join(a.name for a in missing)))

    # Both dismissals are named *and* carry why, one line each. A count on its
    # own asks the reader to take it on trust, which is the opposite of what this
    # block is for: the whole claim of a dismissal is the reasoning behind it, so
    # a reader has to be able to see it and go and argue with it. Unimplemented
    # is the one state with nothing to say - nobody has looked at it yet - so it
    # stays a plain list of names.
    for assessment in dismissed:
        lines.append(_detail("no effect", _described(assessment)))
    for assessment in minor:
        lines.append(_detail("insignificant", _described(assessment)))

    # Gaps hang off content that *is* modelled - a partial implementation saying
    # what it left out. They belong with the modelled half, so they print at FULL
    # only. Content with nothing left out declares no gaps and has never printed
    # a line here.
    if detail is CoverageDetail.FULL:
        for assessment in modelled:
            for gap in assessment.unmodelled:
                lines.append(_detail("gap", f"{assessment.name}: {gap}"))

    # Per-character exclusions declared on the sheet itself - homebrew gear,
    # mostly. Shown alongside the registry's verdicts so a reader sees
    # everything left out of this character in one place.
    for excluded_name, reason in excluded.items():
        lines.append(_detail("sheet says", f"{excluded_name}: {reason}"))

    return lines


def _with_status(assessments, status: Status) -> list:
    return [assessment for assessment in assessments if assessment.status is status]


def _described(assessment) -> str:
    """A dismissed name with a one-line note on why it was dismissed."""
    summary = _summarise(assessment.reason)
    return f"{assessment.name} - {summary}" if summary else assessment.name


def _summarise(reason: str) -> str:
    """The opening sentence of a recorded reason.

    Reasons are written to be argued with, so several run to a paragraph -
    Wings' is six lines on why spending Stress blind is worth nothing. Printing
    all of it for every dismissed name would bury the report it sits under, and
    printing none of it leaves a bare count nobody can check.

    The first sentence is the compromise, and it's a fair one because the
    convention in the content modules is to lead with what the thing does and
    follow with the argument. The full text stays where it was declared, which is
    where somebody disagreeing with a dismissal needs to go anyway.
    """
    collapsed = " ".join(reason.split())
    if not collapsed:
        return ""
    opening, ended, _ = collapsed.partition(". ")
    return opening + "." if ended else opening


def _detail(label: str, text: str) -> str:
    """A wrapped detail line, hanging-indented under the combatant it belongs to."""
    prefix = f"{INDENT}{label:<{LABEL_WIDTH}}"
    hang = INDENT + " " * LABEL_WIDTH
    room = max(WIDTH - len(prefix), 20)

    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > room and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    lines.append(current)

    return "\n".join(
        (prefix if index == 0 else hang) + line for index, line in enumerate(lines)
    )
