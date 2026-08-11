from dataclasses import dataclass
import random

from .common import AdvantageState


@dataclass(frozen=True)
class D20RollResult:
    die_results: list[int]  # one roll normally; two if advantage/disadvantage
    modifier: int
    advantage_state: AdvantageState
    evasion: int | None = None  # typically the target's Evasion

    @property
    def die_result(self) -> int:
        if self.advantage_state is AdvantageState.ADVANTAGE:
            return max(self.die_results)
        if self.advantage_state is AdvantageState.DISADVANTAGE:
            return min(self.die_results)
        return self.die_results[0]

    @property
    def total(self) -> int:
        return self.die_result + self.modifier

    @property
    def is_critical(self) -> bool:
        return self.die_result == 20

    @property
    def is_success(self) -> bool | None:
        if self.evasion is None:
            return None
        if self.is_critical:
            return True
        return self.total >= self.evasion

    def __repr__(self) -> str:
        parts = [f"d20={self.die_results}"]
        if self.advantage_state is not AdvantageState.NONE:
            parts.append(f"{self.advantage_state.name.lower()}->picked={self.die_result}")
        if self.modifier:
            parts.append(f"mod={self.modifier:+d}")
        parts.append(f"total={self.total}")
        if self.is_critical:
            parts.append("CRIT")
        if self.evasion is not None:
            parts.append("SUCCESS" if self.is_success else "FAIL")
        return "D20Roll(" + ", ".join(parts) + ")"


def roll_d20(
    modifier: int = 0,
    evasion: int | None = None,
    advantage_state: AdvantageState = AdvantageState.NONE,
) -> D20RollResult:
    if advantage_state is AdvantageState.NONE:
        die_results = [random.randint(1, 20)]
    else:
        die_results = [random.randint(1, 20), random.randint(1, 20)]

    return D20RollResult(
        die_results=die_results,
        modifier=modifier,
        advantage_state=advantage_state,
        evasion=evasion,
    )
