"""Everything one fight in progress needs to know about itself.

Split out from the loop so decision-making (combat/policy.py) can read the
same state the loop writes without the two importing each other.

Holds the Fear pool, the running counters the report is built from, and the
small amount of memory targeting needs - who hit whom last.
"""

from dataclasses import dataclass, field

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.common import Side

# Per the SRD the GM can hold up to 12 Fear at once. Fear generated past the
# cap is simply lost, which matters for balance: a party that rolls badly for
# a long stretch doesn't bank an unlimited GM turn later on.
MAX_FEAR = 12


@dataclass
class FightState:
    """One fight, mid-flight: both sides, the Fear pool, and the tally so far."""

    encounter_name: str
    party: list[PlayerCharacter]
    adversaries: list[Adversary]

    spotlight: Side = Side.PCS
    fear: int = 0

    pc_actions: int = 0
    adversary_activations: int = 0
    gm_turns: int = 0
    fear_gained: int = 0
    fear_spent: int = 0

    # PCs who have already acted in the current pass. The spotlight stays with
    # the party on a success with Hope, so something has to stop one lucky PC
    # acting forever: everyone goes once before anyone goes twice. Tracked by
    # id() because PlayerCharacter is a mutable dataclass and so unhashable.
    acted_this_pass: set[int] = field(default_factory=set)

    # Targeting memory: an adversary hits back at whoever hit it, so it needs
    # to remember who that was. Keyed by id() for the same reason.
    last_attacker_of: dict[int, PlayerCharacter] = field(default_factory=dict)
    last_pc_to_attack: PlayerCharacter | None = None

    logging: bool = False
    log: list[str] = field(default_factory=list)

    @property
    def conscious_party(self) -> list[PlayerCharacter]:
        """PCs who can still act and still be targeted."""
        return [pc for pc in self.party if pc.is_conscious]

    @property
    def living_adversaries(self) -> list[Adversary]:
        return [adversary for adversary in self.adversaries if not adversary.is_defeated]

    @property
    def party_is_down(self) -> bool:
        return not self.conscious_party

    @property
    def adversaries_are_cleared(self) -> bool:
        return not self.living_adversaries

    @property
    def max_activations_per_gm_turn(self) -> int:
        """How many adversaries the GM may spotlight in one turn.

        Party size + 1. The SRD lets the GM spend Fear to spotlight as many
        adversaries as they can afford; that's fine at a table where a GM is
        reading the room, but a simulator with a greedy Fear policy would just
        empty the pool into the first turn. Capping it keeps a GM turn to
        roughly "everyone gets answered, plus a bit of pressure". A knob worth
        sweeping later.
        """
        return len(self.party) + 1

    def gain_fear(self, amount: int = 1) -> int:
        """Add Fear up to the cap; return how much was actually gained."""
        gained = min(amount, MAX_FEAR - self.fear)
        if gained <= 0:
            return 0
        self.fear += gained
        self.fear_gained += gained
        return gained

    def spend_fear(self, amount: int = 1) -> bool:
        """Spend Fear if there's enough; return whether it went through."""
        if self.fear < amount:
            return False
        self.fear -= amount
        self.fear_spent += amount
        return True

    def note(self, message: str) -> None:
        """Record a line of play-by-play, if this run asked for one."""
        if self.logging:
            self.log.append(message)
