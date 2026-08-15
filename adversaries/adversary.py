"""Adversary stats and state - the GM-side equivalent of characters/player_character.py.

An Adversary is a plain bag of numbers plus one generic `attack()`. Every stat
that affects how dangerous a fight is - Difficulty, thresholds, HP, Stress,
attack modifier, damage dice, damage modifier - is a field, so tuning an
adversary never means editing code. That's the whole point: this simulator
exists to push those numbers around until an encounter lands on the balance
profile we want, so they have to be reachable as values a run can vary.

Individual adversaries are **authored as JSON**, one file per publication (see
srd.json), and read by catalogue.py - a stat block is data, and this is the side
of the table homebrew is written for. What a stat block *does* beyond a standard
attack is its named features, which are code in features/adversaries.py, exactly
the way a character sheet names domain cards that live in domain_cards/.

Per-encounter tweaks belong in encounters/, not in the catalogue: `spawn()`
copies a definition and applies overrides so the definition itself is never
mutated by a simulated fight.

Adversaries don't have Hope, Armor Slots, or Evasion (PC-only concepts) - the
number PC attacks roll against is Difficulty instead (per the SRD: "attacks
rolled against adversaries use the target's Difficulty instead of Evasion").

Defeat is simply `is_defeated` - all HP marked, and the fight loop drops them.
Adversaries get none of the PC death-move machinery; that asymmetry is in the
rules, not a shortcut.
"""

from dataclasses import dataclass, field, replace
from typing import Protocol

from combat.results import AttackResult
from content.names import ADVERSARY, qualified
from content.registry import force_adversary_reroll
from dice.common import AdvantageState
from dice.d20 import roll_d20
from dice.damage import DiceGroup, roll_damage


class Target(Protocol):
    """Anything an adversary's attack can target - a PC, for now."""

    evasion: int

    def take_damage(self, amount: int, fight=None) -> int: ...


@dataclass
class Adversary:
    """An adversary's stats plus whatever HP/Stress have been marked so far.

    Used both as a reusable definition (a stat block, at starting state) and as
    a single combatant in a fight - `spawn()` turns the former into the latter.
    """

    name: str
    tier: int
    difficulty: int
    major_threshold: int
    severe_threshold: int
    hp_max: int
    stress_max: int
    attack_modifier: int
    damage_dice: list[DiceGroup] = field(default_factory=list)
    damage_modifier: int = 0

    # What this stat block does beyond a standard attack, by name. Implemented
    # in features/adversaries.py, reached through the same dispatch a PC's
    # domain cards use, and reported in the coverage block either way - so a
    # feature nobody has written is visible rather than silently absent.
    features: list[str] = field(default_factory=list)

    # Which book this stat block was printed in, or where a homebrew one came
    # from. Never read by the fight loop; it's how a reader tells an as-printed
    # adversary from one of ours.
    publication: str = ""

    hp_marked: int = 0
    stress_marked: int = 0

    @property
    def named_features(self) -> list[str]:
        """This stat block's features, namespaced so dispatch can find them.

        The same input the coverage report takes for a PC. Qualified because a
        catalogue's feature names are not unique across kinds - see
        content/names.py - and because "adversary:Relentless" is what a reader
        of the coverage block needs to see to know which Relentless is missing.
        """
        return [qualified(ADVERSARY, name) for name in self.features]

    @property
    def is_defeated(self) -> bool:
        """True once every HP is marked - adversaries just leave the fight.

        No death move, no unconscious state: the SRD's death rules are a PC
        thing, and for balance purposes an adversary that's out is out.
        """
        return self.hp_marked >= self.hp_max

    def spawn(self, **overrides) -> "Adversary":
        """An independent copy at starting state, with any stat overrides applied.

        One definition can back several combatants in the same fight, so each
        one needs its own HP/Stress to mark and its own damage_dice list.
        Overrides are how an encounter tunes a stat block without touching the
        definition - `JAGGED_KNIFE_BANDIT.spawn(hp_max=7, damage_modifier=3)`.
        """
        changes = {
            "damage_dice": list(self.damage_dice),
            "features": list(self.features),
            "hp_marked": 0,
            "stress_marked": 0,
        }
        changes.update(overrides)
        return replace(self, **changes)

    def attack(
        self,
        target: Target,
        advantage_state: AdvantageState = AdvantageState.NONE,
        fight=None,
    ) -> AttackResult:
        """Standard attack: d20 + attack_modifier against the target's Evasion.

        On a hit, rolls this adversary's damage dice plus its flat modifier and
        applies the total to the target. Adversaries whose attack does something
        a plain roll can't express need their own function alongside their
        definition; nothing does yet.

        `fight` is handed to the target rather than used here: a PC's damage
        responses can depend on state that only lives for the length of a fight
        (Unstoppable's die), and the target has no other way to reach it. It
        stays optional so a damage calculation can still be tested on its own.

        The one thing `fight` *is* used for here is reaching the party: content
        that can force this adversary to re-make its roll belongs to a PC, not to
        the PC being swung at, so the dispatch is asked party-wide. Nothing in
        this module knows which content that is.
        """

        def swing():
            return roll_d20(
                modifier=self.attack_modifier,
                evasion=target.evasion,
                advantage_state=advantage_state,
            )

        # Asked before anything reads the roll, so a forced reroll is
        # indistinguishable from the adversary having rolled that way first.
        attack_roll = force_adversary_reroll(self, swing(), swing, fight)

        if not attack_roll.is_success:
            return AttackResult(attack_roll=attack_roll, damage_roll=None)

        damage_roll = roll_damage(
            dice_groups=self.damage_dice,
            modifier=self.damage_modifier,
            is_critical=attack_roll.is_critical,
        )
        marked = target.take_damage(damage_roll.total, fight)
        return AttackResult(
            attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
        )

    def mark_hp(self, amount: int) -> None:
        self.hp_marked = min(self.hp_marked + amount, self.hp_max)

    def clear_hp(self, amount: int) -> None:
        self.hp_marked = max(self.hp_marked - amount, 0)

    def mark_stress(self, amount: int) -> None:
        self.stress_marked = min(self.stress_marked + amount, self.stress_max)

    def clear_stress(self, amount: int) -> None:
        self.stress_marked = max(self.stress_marked - amount, 0)

    def take_damage(self, amount: int, fight=None) -> int:
        """Mark HP per the SRD's Damage Thresholds rule; return the HP marked.

        Same rule, and same threshold-to-HP-marked math, as
        PlayerCharacter.take_damage - dice/damage.py's own docstring notes
        damage resolution is shared by PCs and adversaries alike. Duplicated
        here rather than factored into a shared base class for now; revisit
        if a third caller needs the same logic.

        `fight` is accepted and ignored, so that both sides satisfy the same
        Target protocol. Adversaries carry no content, so nothing on this side
        has a damage response to consult.
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
