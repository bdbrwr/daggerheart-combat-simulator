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
