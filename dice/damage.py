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

    `discardable` says whether a Massive/Powerful discard is allowed to throw one
    of these dice away. It's False for dice a *feature* adds to somebody else's
    roll - School of War's Face Your Fear, say - because those aren't dice rolled
    for the weapon, and the weapon's feature is what the discard belongs to. They
    still join the same roll and the same total, so the damage is checked against
    the target's thresholds once.
    """

    count: int
    sides: int
    discardable: bool = True


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
    def _discardable_dice(self) -> list[int]:
        """Every die the discard is allowed to touch, lowest first."""
        return sorted(
            die
            for group, results in zip(self.dice_groups, self.die_results)
            if group.discardable
            for die in results
        )

    @property
    def dropped(self) -> list[int]:
        """The individual dice discarded by drop_lowest, lowest first.

        Weapon features like Massive and Powerful read "roll an additional
        damage die and discard the lowest result" - the caller rolls the extra
        die by raising the group's count, and this takes the lowest back off.

        Dropping is across the whole roll rather than per group, which is what
        "the lowest result" means when a *formula* has more than one group - but
        only across the groups the weapon itself rolled. Dice another feature
        added are marked `discardable=False` and are out of reach, since the
        feature doing the discarding is the weapon's.
        """
        if self.drop_lowest <= 0:
            return []
        return self._discardable_dice[: self.drop_lowest]

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

        Dice a feature added are counted in full, for the same reason they can't
        be discarded: the discard never reaches them, so nothing is taken off.
        """
        if not self.is_critical:
            return 0

        discardable = sorted(
            group.sides
            for group in self.dice_groups
            if group.discardable
            for _ in range(group.count)
        )
        protected = sum(
            group.sides * group.count
            for group in self.dice_groups
            if not group.discardable
        )
        return sum(discardable[self.drop_lowest :]) + protected

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
        drop_lowest: How many of the lowest individual dice to discard, for weapon features like Massive and Powerful. The caller is responsible for rolling the extra die (by raising a group's count); this only takes the lowest back off, and only from groups marked `discardable`. Every die rolled stays in the result for record-keeping.
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
