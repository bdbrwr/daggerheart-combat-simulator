"""Dice roll resolution for Daggerheart combat.

Two independent roll types, sharing only the AdvantageState enum:
- Duality rolls (dice/duality.py) - PCs, 2d12 Hope vs. Fear, additive adv/disadv.
- D20 rolls (dice/d20.py) - adversaries/environments, classic take-higher/lower adv/disadv.
"""

from .common import AdvantageState
from .duality import DualityRollResult, DualityOutcome, roll_duality
from .d20 import D20RollResult, roll_d20

__all__ = ["AdvantageState", "DualityRollResult", "DualityOutcome", "roll_duality", "D20RollResult", "roll_d20"]
