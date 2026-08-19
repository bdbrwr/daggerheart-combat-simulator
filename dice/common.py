"""Shared tri-state Advantage/Disadvantage indicator.

Any number of sources granting Advantage or Disadvantage collapses to the
same effect - it does not stack. Duality rolls (PCs, see dice/duality.py)
and D20 rolls (adversaries/environments, see dice/d20.py) both use this
enum, but resolve it completely differently - do not assume shared
resolution logic just because they share the type.
"""

from enum import Enum

class AdvantageState(Enum):
    """ADVANTAGE, NONE, or DISADVANTAGE - a tri-state, not a stacking count."""

    DISADVANTAGE = -1
    NONE = 0
    ADVANTAGE = 1


def combined(*states: AdvantageState) -> AdvantageState:
    """Several sources of Advantage/Disadvantage collapsed into one state.

    Per the SRD the two cancel: "if you have both advantage and disadvantage,
    they cancel each other out". Neither side stacks, so three sources of
    Advantage and one of Disadvantage still come to plain Advantage rather than
    to anything bigger.

    Summing the signed values and clamping expresses exactly that, and it means a
    caller with a state in hand can fold another in without knowing what the
    first one was. The first caller is a weapon attack, which now has two
    sources to reconcile: the state its holder was handed, and any condition
    sitting on them that hobbles the trait they're rolling.
    """
    total = sum(state.value for state in states)
    return AdvantageState(max(-1, min(1, total)))
