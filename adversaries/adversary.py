"""Adversary state - the GM-side equivalent of characters/player_character.py.

Like PlayerCharacter, an Adversary is mutable: HP and Stress get marked over
the course of a simulated fight. Adversaries don't have Hope, Armor Slots, or
Evasion (PC-only concepts) - the number PC attacks roll against is Difficulty
instead (per the SRD: "attacks rolled against adversaries use the target's
Difficulty instead of Evasion").

Defeat (what happens when an adversary marks its last HP) is deliberately not
modeled here yet, the same way PlayerCharacter doesn't infer death from
hp_marked == hp_max - that hasn't been looked up and built on purpose.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass
class Adversary:
    """An adversary's stats plus whatever HP/Stress have been marked so far."""

    name: str
    tier: int
    difficulty: int
    major_threshold: int
    severe_threshold: int
    hp_max: int
    stress_max: int
    attack_modifier: int

    hp_marked: int = 0
    stress_marked: int = 0

    def mark_hp(self, amount: int) -> None:
        self.hp_marked = min(self.hp_marked + amount, self.hp_max)

    def clear_hp(self, amount: int) -> None:
        self.hp_marked = max(self.hp_marked - amount, 0)

    def mark_stress(self, amount: int) -> None:
        self.stress_marked = min(self.stress_marked + amount, self.stress_max)

    def clear_stress(self, amount: int) -> None:
        self.stress_marked = max(self.stress_marked - amount, 0)

    def take_damage(self, amount: int) -> int:
        """Mark HP per the SRD's Damage Thresholds rule; return the HP marked.

        Same rule, and same threshold-to-HP-marked math, as
        PlayerCharacter.take_damage - dice/damage.py's own docstring notes
        damage resolution is shared by PCs and adversaries alike. Duplicated
        here rather than factored into a shared base class for now; revisit
        if a third caller needs the same logic.
        """
        if amount <= 0:
            hp_to_mark = 0
        elif amount >= self.severe_threshold:
            hp_to_mark = 3
        elif amount >= self.major_threshold:
            hp_to_mark = 2
        else:
            hp_to_mark = 1
        self.mark_hp(hp_to_mark)
        return hp_to_mark


class Target(Protocol):
    """Anything an adversary's attack can target - a PC, for now."""

    evasion: int

    def take_damage(self, amount: int) -> int: ...
