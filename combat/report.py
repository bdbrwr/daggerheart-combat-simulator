"""What one simulated fight hands back.

Deliberately wider than "who won". The point of running 10,000 of these is to
compare distributions, and which numbers turn out to matter isn't settled yet -
so the loop records everything cheap to record and leaves picking the headline
metric until there's output to look at.

On counting fight length: Daggerheart has no rounds, so there is no round to
count. What the loop can count honestly is how many actions the PCs took and
how many times an adversary was spotlighted; dividing each by the party size
gives two round-ish numbers on a scale a GM would recognise. They're reported
side by side rather than reconciled into one, because they measure different
things - `pc_rounds` is how long the fight felt to the players, `gm_rounds` is
how much the adversaries actually got to do, and a gap between them is itself
a balance signal (a party chaining successes with Hope keeps the second number
down).

Kept out of combat/results.py to avoid an import cycle: adversaries/adversary.py
imports AttackResult from there, so that module can't import an Adversary back.
"""

from dataclasses import dataclass, field

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.common import FightOutcome


@dataclass(frozen=True)
class FightResult:
    """The full record of one simulated fight, including both sides' end state."""

    encounter_name: str
    outcome: FightOutcome

    party: list[PlayerCharacter]
    adversaries: list[Adversary]

    pc_actions: int
    adversary_activations: int
    gm_turns: int

    fear_gained: int
    fear_spent: int
    fear_remaining: int

    unconscious_pcs: int
    scars_gained: int

    log: list[str] = field(default_factory=list)

    @property
    def party_size(self) -> int:
        return len(self.party)

    @property
    def party_won(self) -> bool:
        return self.outcome is FightOutcome.PARTY_VICTORY

    @property
    def pc_rounds(self) -> float:
        """PC actions per party member - the fight's length as the players felt it."""
        if not self.party_size:
            return 0.0
        return self.pc_actions / self.party_size

    @property
    def gm_rounds(self) -> float:
        """Adversary activations per party member - how much the GM side got to do."""
        if not self.party_size:
            return 0.0
        return self.adversary_activations / self.party_size

    @property
    def surviving_pcs(self) -> int:
        return sum(1 for pc in self.party if pc.is_conscious)

    @property
    def surviving_adversaries(self) -> int:
        return sum(1 for adversary in self.adversaries if not adversary.is_defeated)

    @property
    def party_hp_remaining(self) -> int:
        """HP left across the whole party - the near-death signal, in aggregate."""
        return sum(pc.hp_remaining for pc in self.party)

    @property
    def lowest_hp_remaining(self) -> int:
        """HP left on whoever came closest to going down.

        The honest near-death signal: a party total hides one PC on their last
        HP behind three who are untouched.
        """
        if not self.party:
            return 0
        return min(pc.hp_remaining for pc in self.party)

    def __repr__(self) -> str:
        parts = [
            self.encounter_name,
            self.outcome.value,
            f"pc_rounds={self.pc_rounds:.1f}",
            f"gm_rounds={self.gm_rounds:.1f}",
            f"pcs_up={self.surviving_pcs}/{self.party_size}",
            f"adversaries_up={self.surviving_adversaries}/{len(self.adversaries)}",
            f"fear={self.fear_remaining}",
        ]
        if self.scars_gained:
            parts.append(f"scars={self.scars_gained}")
        return "FightResult(" + ", ".join(parts) + ")"
