"""Duality dice (2d12, Hope vs. Fear) resolution - PC rolls only.

Hope > Fear -> Hope; Fear > Hope -> Fear; equal -> Critical (auto-successregardless of difficulty, gain 1 Hope, clear 1 Stress per the SRD - those Hope/Stress side effects are the caller's responsibility, not modeled here).

Advantage/Disadvantage is resolved additively here: roll a d6 and add it (Advantage) or subtract it (Disadvantage) from the total.

Help (also additive, but a separate mechanic) is a die pool from a helping ally, rolled independently of Advantage/Disadvantage and does NOT cancelagainst Disadvantage - only the single best help die counts.
"""

from dataclasses import dataclass, field
from enum import Enum
import random

from .common import AdvantageState

class DualityOutcome(Enum):
    """Which die won the duality roll: HOPE, FEAR, or a tied CRIT."""

    HOPE = "hope"
    FEAR = "fear"
    CRIT = "crit"

@dataclass(frozen=True)
class DualityRollResult:
    """Immutable result of a single duality (2d12) roll.

    All derived values (outcome, total, is_success, ...) are computed viaproperties from the raw dice fields - never add a stored field that duplicates one of these.
    """

    hope_die_result: int
    fear_die_result: int
    modifier: int
    advantage_state: AdvantageState
    advantage_die_result: int | None
    help_dice_results: list[int] | None
    difficulty: int | None = None

    # The sizes the two dice were rolled at. Raw inputs, not derived values - the
    # class records "every raw die roll", and until now it recorded the results
    # without recording what they were rolled on.
    #
    # They are here because content can re-roll **one** die of a resolved roll:
    # the Valor card Support Tank lets an ally reroll either their Hope or their
    # Fear Die, which means building a replacement result with one field changed,
    # and that needs the size of the die being thrown again. The Hope Die is not
    # always a d12 - `hope_die_for` swaps it - so it cannot be assumed.
    #
    # Defaulted, so every existing construction of this class (tests build them
    # directly with fixed values) keeps working unchanged.
    hope_die_sides: int = 12
    fear_die_sides: int = 12

    # Which of the character's traits was rolled - "agility", "presence", the
    # Spellcast trait a caster rolls with. A raw input like the die sizes above,
    # not a derived value, and recorded for the same reason: the class records
    # every part of what was thrown, and until now it recorded the modifier
    # without recording where the modifier came from.
    #
    # **Duality rolls only.** A d20 roll has no trait to name - adversaries carry
    # none - so `D20RollResult` deliberately has no twin of this field.
    #
    # Empty where there is no trait to name, which is a real answer rather than a
    # gap - a test building a result by hand has no character behind it at all.
    #
    # Defaulted, so nothing that builds one of these has to change.
    trait: str = ""

    @property
    def outcome(self) -> DualityOutcome:
        """HOPE, FEAR, or CRIT depending on which die is higher (or tied)."""
        if self.hope_die_result == self.fear_die_result:
            return DualityOutcome.CRIT
        return DualityOutcome.HOPE if self.hope_die_result > self.fear_die_result else DualityOutcome.FEAR

    @property
    def advantage_total(self) -> int:
        """Signed Advantage/Disadvantage d6 contribution, or 0 if AdvantageState.NONE."""
        if self.advantage_state is AdvantageState.NONE or self.advantage_die_result is None:
            return 0
        return self.advantage_state.value * self.advantage_die_result

    @property
    def help_total(self) -> int:
        """Best single help die, or 0 if no one helped.

        Help dice are NOT summed - only the single best result counts, even
        if multiple allies helped.
        """
        if self.help_dice_results is None or len(self.help_dice_results) == 0:
            return 0
        return max(self.help_dice_results)

    @property
    def total (self) -> int:
        """Hope + Fear + modifier + Advantage/Disadvantage swing + best help die."""
        return (
            self.hope_die_result + self.fear_die_result + self.modifier + self.advantage_total + self.help_total
        )

    @property
    def is_critical(self) -> bool:
        """True when the Hope and Fear dice are equal (Critical Success)."""
        return self.outcome == DualityOutcome.CRIT

    @property
    def is_success(self) -> bool | None:
        """True/False against difficulty, or None if no difficulty was given.

        A Critical always succeeds regardless of difficulty.
        """
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
    fear_die = 12,
    trait: str = "",
) -> DualityRollResult:
    """Roll Hope + Fear duality dice and resolve Advantage/Disadvantage/Help.

    Args:
        modifier: Flat modifier added to the total.
        difficulty: Target number to beat; if None, `is_success` is None.
        advantage_state: ADVANTAGE/DISADVANTAGE additionally rolls a d6 andadds/subtracts it from the total; NONE rolls nothing extra.
        help_dice: Die sizes of any allies helping (e.g. [6, 8] for a d6 anda d8 helper); only the single best result is applied.
        hope_die: Die size for the Hope die (default d12).
        fear_die: Die size for the Fear die (default d12).
        trait: Which character trait is being rolled - "agility", "presence",
            whatever a caster's Spellcast trait is. It changes nothing about the
            dice; it is recorded on the result so that a roll says which kind of
            roll it was. Every site that rolls a trait names it, and the ones
            that have none to name (a hand-built result in a test) leave it
            empty. There is no d20 equivalent: adversaries carry no traits.

    Returns:
        A DualityRollResult with every raw die roll recorded.
    """

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
        difficulty=difficulty,
        hope_die_sides=hope_die,
        fear_die_sides=fear_die,
        trait=trait,
    )
