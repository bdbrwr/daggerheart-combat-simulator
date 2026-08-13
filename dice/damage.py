"""Damage roll resolution - weapon and spell damage, PCs and adversaries alike.

A damage formula on a card is written as "XdY+Z" (roll X dice of Y sides, add flat modifier Z), or as several dice groups added together, e.g. "XdY + AdB + Z". Some formulas omit the dice count and derive it from a character trait instead - "dY+Z using your Proficiency" (weapons) or "dY+Z using your Spellcast trait" (spells/domain cards). Per the SRD, Proficiency/Spellcast-trait dice counts multiply the number of dice rolled but never touch the flat modifier, and a Spellcast trait of +0 or lower rolls no dice at all.

This module deliberately does not implement Proficiency or Spellcast traits, expecting these to be parsed at the calling function before being passed to this module.

On a critical success you make the damage roll as usual and then add the maximum possible result of the damage dice to the total (the total isn't doubled, and the modifier isn't touched either).
"""

from dataclasses import dataclass
import random


@dataclass(frozen=True)
class DiceGroup:
    """One group of like-sized dice within a damage formula - the "2d8" in "2d8 + 1d4 + 3".

    A count of 0 is valid and rolls no dice for that group - e.g. a Spellcast trait of +0 or lower per the SRD.
    """

    count: int
    sides: int


@dataclass(frozen=True)
class DamageRollResult:
    """Immutable result of a damage roll across one or more DiceGroups.

    All derived values (rolled_total, critical_bonus, total) are computed via properties from the raw dice fields - never add a stored field that duplicates one of these.
    """

    dice_groups: list[DiceGroup]
    die_results: list[list[int]]  # one inner list per dice_groups entry, same order
    modifier: int
    is_critical: bool = False
    drop_lowest: int = 0

    @property
    def dropped(self) -> list[int]:
        """The individual dice discarded by drop_lowest, lowest first.

        Weapon features like Massive and Powerful read "roll an additional
        damage die and discard the lowest result" - the caller rolls the extra
        die by raising the group's count, and this takes the lowest back off.
        Dropping is across the whole roll rather than per group, which is what
        "the lowest result" means when a formula has more than one group.
        """
        if self.drop_lowest <= 0:
            return []
        every_die = sorted(die for group in self.die_results for die in group)
        return every_die[: self.drop_lowest]

    @property
    def rolled_total(self) -> int:
        """Sum of every rolled die that counts, before modifier or critical bonus."""
        rolled = sum(sum(group_results) for group_results in self.die_results)
        return rolled - sum(self.dropped)

    @property
    def critical_bonus(self) -> int:
        """Max possible value of the damage dice, added on a critical hit.

        A Crit adds the maximum possible result of the damage dice on top of the normal roll. 0 when is_critical is False.

        Discarded dice don't contribute: the bonus is the maximum of the dice
        that actually counted, so a dropped die isn't paid for twice. The SRD
        doesn't spell out how a crit and a discard interact - see
        SIMULATION-RULES.md.
        """
        if not self.is_critical:
            return 0
        every_side = sorted(
            group.sides for group in self.dice_groups for _ in range(group.count)
        )
        return sum(every_side[self.drop_lowest :])

    @property
    def total(self) -> int:
        """rolled_total + modifier + critical_bonus."""
        return self.rolled_total + self.modifier + self.critical_bonus

    def __repr__(self) -> str:
        groups = " + ".join(
            f"{group.count}d{group.sides}={results}"
            for group, results in zip(self.dice_groups, self.die_results)
        )
        parts = [groups if groups else "(no dice)"]
        if self.dropped:
            parts.append(f"dropped={self.dropped}")
        if self.modifier:
            parts.append(f"mod={self.modifier:+d}")
        if self.is_critical:
            parts.append(f"CRIT(+{self.critical_bonus})")
        parts.append(f"total={self.total}")
        return "DamageRoll(" + ", ".join(parts) + ")"


def roll_damage(
    dice_groups: list[DiceGroup],
    modifier: int = 0,
    is_critical: bool = False,
    drop_lowest: int = 0,
) -> DamageRollResult:
    """Roll one or more dice groups and resolve modifier/critical damage.

    Args:
        dice_groups: The dice pools to roll, e.g. [DiceGroup(2, 8), DiceGroup(1, 4)] for "2d8 + 1d4". A group with count=0 rolls no dice for that group (e.g. a Spellcast trait of +0 or lower) but is still kept in the result for record-keeping.        modifier: Flat modifier added to the total, unaffected by dice counts.
        is_critical: Whether the preceding attack roll was a critical success - if True, the maximum possible dice result is added on top of the normal roll.
        drop_lowest: How many of the lowest individual dice to discard, for weapon features like Massive and Powerful. The caller is responsible for rolling the extra die (by raising a group's count); this only takes the lowest back off. Every die rolled stays in the result for record-keeping.
    Returns:
        A DamageRollResult with every raw die roll recorded.
    """
    die_results = [
        [random.randint(1, group.sides) for _ in range(group.count)]
        for group in dice_groups
    ]

    return DamageRollResult(
        dice_groups=dice_groups,
        die_results=die_results,
        modifier=modifier,
        is_critical=is_critical,
        drop_lowest=drop_lowest,
    )
