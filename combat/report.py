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
class CombatantState:
    """One PC's condition at the moment a fight ended.

    The party-wide totals a report used to carry - unconscious PCs, scars, the
    party's unmarked HP - answer questions about *the party*. They can't answer
    "which of these three is the one the encounter keeps knocking over?", which
    is a different and often more useful question when tuning: an encounter that
    is fine on average can still be reliably brutal to one character.

    Frozen and free of any reference back to the PlayerCharacter it was taken
    from, so a run of 10,000 fights can keep every one of these without keeping
    10,000 parties and their gear alive.

    It is also the shape a **sequence** of encounters needs. Running fights back
    to back means carrying each PC's marked tracks into the next one, and this is
    that state, written down. Nothing restores from it yet - the carry-forward is
    still unbuilt - but the recording half no longer is.
    """

    name: str
    conscious: bool
    hp_unmarked: int
    hp_max: int
    stress_unmarked: int
    stress_max: int
    armor_unmarked: int
    armor_max: int
    hope_marked: int
    scars: int
    death_moves: int

    # Where this PC's Hope went, rather than only what was left of it. Hope is
    # the one track that both fills and empties during a fight, so the end state
    # on its own says nothing: two Hope left over is a PC who never spent any
    # and a PC who earned eight and burned them both. Defaulted so a record
    # built by hand in a test can still state an end state without accounting
    # for the whole fight.
    hope_at_start: int = 0
    hope_gained: int = 0
    hope_spent: int = 0

    @classmethod
    def of(cls, pc) -> "CombatantState":
        """A snapshot of `pc` exactly as they are now."""
        return cls(
            name=pc.name,
            conscious=pc.is_conscious,
            hp_unmarked=pc.hp_unmarked,
            hp_max=pc.hp_max,
            stress_unmarked=pc.stress_unmarked,
            stress_max=pc.stress_max,
            armor_unmarked=pc.armor_unmarked,
            armor_max=pc.armor_max,
            hope_marked=pc.hope_marked,
            scars=pc.scars,
            death_moves=pc.death_moves,
            hope_at_start=pc.hope_at_start,
            hope_gained=pc.hope_gained,
            hope_spent=pc.hope_spent,
        )


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
    def party_state(self) -> tuple[CombatantState, ...]:
        """Each PC's end state, in the order the party was fielded.

        Derived rather than stored, so it can't drift from the party it
        describes. The simulation layer copies it into its own record, which is
        where it has to survive the party being dropped.
        """
        return tuple(CombatantState.of(pc) for pc in self.party)

    @property
    def death_moves(self) -> int:
        """How many death moves the party made between them.

        Distinct from `scars_gained`, which counts only the ones that left a
        mark. With Avoid Death the only move implemented and nobody ever revived,
        this currently equals the number of PCs who ended unconscious - but it is
        counted where it happens rather than inferred, so it stays right when a
        second death move or a revival arrives.
        """
        return sum(pc.death_moves for pc in self.party)

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
    def party_hp_unmarked(self) -> int:
        """Unmarked HP across the whole party - the near-death signal, in aggregate."""
        return sum(pc.hp_unmarked for pc in self.party)

    @property
    def lowest_hp_unmarked(self) -> int:
        """Unmarked HP on whoever came closest to going down.

        The honest near-death signal: a party total hides one PC on their last
        HP behind three who are untouched.
        """
        if not self.party:
            return 0
        return min(pc.hp_unmarked for pc in self.party)

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
