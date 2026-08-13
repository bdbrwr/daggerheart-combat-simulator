"""How much of a party the simulator actually runs.

A win rate is only worth reading if you know what produced it. If half of a
character isn't implemented, the party in the simulation is weaker than the
party at the table, and the encounter looks harder than it is - so this block
belongs next to the numbers, not in a file somebody has to go and find.

Three states per named thing, from content/registry.py:

  * modelled          - code runs it (possibly with declared gaps)
  * no combat effect  - assessed and dismissed, with a reason
  * unimplemented     - nobody has looked at it yet

The distinction the report exists to make is between the last two. "No combat
effect" costs the results nothing. "Unimplemented" costs them something nobody
has measured.
"""

from content.registry import Status, assess_all

WIDTH = 78
NAME_WIDTH = 20
LABEL_WIDTH = 16
INDENT = " " * 6


def format_coverage(party) -> str:
    """The coverage block for one party, as printed under a report."""
    if not party:
        return "COVERAGE\n  (no party)"

    assessed = [(pc, assess_all(pc.named_features)) for pc in party]

    lines = ["COVERAGE  (how much of each character the simulator runs)"]
    for pc, assessments in assessed:
        lines.extend(_for_character(pc, assessments))

    if any(_with_status(a, Status.UNIMPLEMENTED) for _, a in assessed):
        lines += [
            "",
            "  Unimplemented is not the same as no effect: it's work not done, and",
            "  every entry makes the party weaker here than it would be at a table.",
        ]
    return "\n".join(lines)


def _for_character(pc, assessments) -> list[str]:
    """One PC's tally, then the detail worth naming."""
    modelled = _with_status(assessments, Status.MODELLED)
    dismissed = _with_status(assessments, Status.NO_COMBAT_EFFECT)
    missing = _with_status(assessments, Status.UNIMPLEMENTED)

    lines = [
        f"  {pc.name:<{NAME_WIDTH}}{len(modelled)} modelled   "
        f"{len(dismissed)} no effect   {len(missing)} unimplemented"
    ]

    if missing:
        lines.append(_detail("unimplemented", ", ".join(a.name for a in missing)))

    for assessment in modelled:
        for gap in assessment.unmodelled:
            lines.append(_detail("gap", f"{assessment.name}: {gap}"))

    # Per-character exclusions declared on the sheet itself - homebrew gear,
    # mostly. Shown alongside the registry's verdicts so a reader sees
    # everything left out of this character in one place.
    for name, reason in pc.not_modelled.items():
        lines.append(_detail("sheet says", f"{name}: {reason}"))

    return lines


def _with_status(assessments, status: Status) -> list:
    return [assessment for assessment in assessments if assessment.status is status]


def _detail(label: str, text: str) -> str:
    """A wrapped detail line, hanging-indented under the character it belongs to."""
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
