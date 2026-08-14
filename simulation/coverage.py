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
"""

from content.registry import Status, assess_all

WIDTH = 78
NAME_WIDTH = 18
LABEL_WIDTH = 16
INDENT = " " * 6


def format_coverage(party, adversaries=()) -> str:
    """The coverage block for one fight, as printed under a report.

    `adversaries` is optional so a caller with only a party - a test, or any
    report that predates the GM side existing - still gets the block it had.
    """
    if not party and not adversaries:
        return "COVERAGE\n  (nobody in the fight)"

    # `assessed_features`, not `named_features`: coverage asks how much of a
    # character the simulator runs, which includes their weapon's features even
    # though those are scoped to the weapon rather than dispatched holder-wide.
    assessed = [
        (pc.name, assess_all(pc.assessed_features), pc.not_modelled) for pc in party
    ]
    opposition = _distinct(adversaries)

    lines = ["COVERAGE  (how much of each combatant the simulator runs)"]

    if party:
        lines.append("  party")
        for name, assessments, excluded in assessed:
            lines.extend(_for_combatant(name, assessments, excluded))
    else:
        lines.append("  party            (nobody)")

    if opposition:
        lines.append("  opposition")
        for name, assessments in opposition:
            lines.extend(_for_combatant(name, assessments, {}))

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


def _for_combatant(name, assessments, excluded) -> list[str]:
    """One combatant's tally, then the detail worth naming."""
    modelled = _with_status(assessments, Status.MODELLED)
    dismissed = _with_status(assessments, Status.NO_COMBAT_EFFECT)
    minor = _with_status(assessments, Status.INSIGNIFICANT_COMBAT_EFFECT)
    missing = _with_status(assessments, Status.UNIMPLEMENTED)

    lines = [
        f"    {name:<{NAME_WIDTH}}{len(modelled)} modelled  "
        f"{len(dismissed)} no effect  {len(minor)} insignificant  "
        f"{len(missing)} unimplemented"
    ]

    if missing:
        lines.append(_detail("unimplemented", ", ".join(a.name for a in missing)))

    # Named as well as counted: a dismissal is only worth anything if a reader
    # can see what was dismissed and go and check the reasoning.
    if minor:
        lines.append(_detail("insignificant", ", ".join(a.name for a in minor)))

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
