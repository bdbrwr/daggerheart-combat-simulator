from dataclasses import dataclass, field
from enum import Enum
import random

from .common import AdvantageState

class Outcome(Enum):
    HOPE = "hope"
    FEAR = "fear"
    CRIT = "crit"

@dataclass(frozen=True)
class DualityRollResult:
    hope_die_result: int
    fear_die_result: int
    modifier: int
    advantage_state: AdvantageState
    advantage_die_result: int | None
    help_dice_results: list[int] | None
    difficulty: int | None = None

    @property
    def outcome(self) -> Outcome:
        if self.hope_die_result == self.fear_die_result:
            return Outcome.CRIT
        return Outcome.HOPE if self.hope_die_result > self.fear_die_result else Outcome.FEAR

    @property
    def advantage_total(self) -> int:
        if self.advantage_state is AdvantageState.NONE or self.advantage_die_result is None:
            return 0
        return self.advantage_state.value * self.advantage_die_result

    @property
    def help_total(self) -> int:
        if self.help_dice_results is None or len(self.help_dice_results) == 0:
            return 0
        return max(self.help_dice_results)

    @property
    def total (self) -> int:
        return (
            self.hope_die_result + self.fear_die_result + self.modifier + self.advantage_total + self.help_total
        )

    @property
    def is_critical(self) -> bool:
        return self.outcome == Outcome.CRIT

    @property
    def is_success(self) -> bool | None:
        if self.difficulty is None:
            return None
        if self.is_critical:
            return True
        return self.total >= self.difficulty

    def __repr__(self) -> str:
        parts = [f"Hope={self.hope_die_result}", f"Fear={self.fear_die_result}"]
        if self.modifier:
            parts.append(f"mod={self.modifier:+d}")
        if self.advantage_state is not AdvantageState.NONE:
            sign = "+" if self.advantage_state is AdvantageState.ADVANTAGE else "-"
            parts.append(f"{self.advantage_state.name.lower()}({sign}{self.advantage_die_result})")
        if self.help_dice_results:
            parts.append(f"help={self.help_total}")
        parts.append(f"total={self.total}")
        parts.append(self.outcome.value)
        if self.difficulty is not None:
            parts.append("SUCCESS" if self.is_success else "FAIL")
        return "DualityRoll(" + ", ".join(parts) + ")"


def roll_duality(
    modifier:int = 0,
    difficulty: int | None = None,
    advantage_state: AdvantageState = AdvantageState.NONE,
    help_dice: list[int] | None = None,
    hope_die = 12,
    fear_die = 12
) -> DualityRollResult:

    hope_die_result = random.randint(1,hope_die)
    fear_die_result = random.randint(1,fear_die)

    advantage_die_result = None
    if advantage_state is not AdvantageState.NONE:
        advantage_die_result = random.randint(1,6) # As fo the 01-09-2026 SRD there is nothing that modifies the player's own advantage die, just the ones helping

    help_dice_results = None
    if help_dice:
        help_dice_results = [random.randint(1,die) for die in help_dice]

    return DualityRollResult(
        hope_die_result=hope_die_result,
        fear_die_result=fear_die_result,
        modifier=modifier,
        advantage_state=advantage_state,
        advantage_die_result=advantage_die_result,
        help_dice_results=help_dice_results,
        difficulty=difficulty
    )
