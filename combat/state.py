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
from combat.rest import Rest
from content.conditions import VULNERABLE, Condition

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

    # What the party got before this fight, and what they've burned since.
    # Keyed by (id(holder), ability name) because PlayerCharacter is unhashable.
    rest: Rest = Rest.LONG
    spent_per_rest: set[tuple[int, str]] = field(default_factory=set)

    # Tokens content places on itself during a fight - Know the Tide's, and the
    # several domain cards built the same way. Generic rather than per-feature,
    # keyed by (id(holder), name) like the per-rest uses above.
    tokens: dict[tuple[int, str], int] = field(default_factory=dict)

    # Temporary conditions on either side, keyed the same way. Separate from
    # tokens because a condition is a record rather than a count - it carries the
    # predicate that says when it's over.
    conditions: dict[tuple[int, str], Condition] = field(default_factory=dict)

    # Extra spotlights content handed out during the current GM turn, by id().
    # Cleared at the start of each one - "take the spotlight again" means this
    # turn, not a credit carried forward.
    granted: dict[int, int] = field(default_factory=dict)

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
        """How many activations the GM gets in one turn.

        Activations, not distinct adversaries: `Relentless (X)` lets one
        adversary take several, and they all count against this.

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

    def can_use_once_per_rest(self, holder, ability: str, long: bool = False) -> bool:
        """Whether `holder` still has their per-rest use of `ability`.

        `long` marks an ability limited to once per *long* rest - a short rest
        doesn't give it back. Content asks this rather than assuming a fresh
        slate, because an encounter can be set up as following straight on from
        another with no rest at all.
        """
        refreshed = self.rest.refreshes_long if long else self.rest.refreshes_short
        if not refreshed:
            return False
        return (id(holder), ability) not in self.spent_per_rest

    def use_once_per_rest(self, holder, ability: str, long: bool = False) -> bool:
        """Spend `holder`'s per-rest use of `ability`; return whether it was there."""
        if not self.can_use_once_per_rest(holder, ability, long):
            return False
        self.spent_per_rest.add((id(holder), ability))
        return True

    def grant_activation(self, holder) -> None:
        """Let `holder` be spotlighted once more this GM turn.

        The Construct's Overload ("the Construct can then take the spotlight
        again") grants one mid-turn, which a feature registered on
        `activation_limit` can't express - that answers before the turn starts.

        Still bounded by the turn's own cap and still charged the usual Fear, on
        the same reasoning as Relentless: the cap is what holds a simulated fight
        to something a GM would run, so nothing reaches around it.
        """
        self.granted[id(holder)] = self.granted.get(id(holder), 0) + 1

    def granted_activations(self, holder) -> int:
        return self.granted.get(id(holder), 0)

    # --- Conditions ----------------------------------------------------------

    def apply_condition(self, holder, condition: Condition) -> None:
        """Put `condition` on `holder`, replacing any of the same name.

        Replacing rather than stacking: nothing in the SRD makes being Vulnerable
        twice worse than once, and a re-application refreshes how long it lasts,
        which is what the later of two overlapping effects should do.
        """
        self.conditions[(id(holder), condition.name)] = condition

    def has_condition(self, holder, name: str) -> bool:
        return (id(holder), name) in self.conditions

    def clear_condition(self, holder, name: str) -> None:
        self.conditions.pop((id(holder), name), None)

    def expire_conditions(self, holder, moment: str) -> list[str]:
        """Offer every condition on `holder` the chance to end; return those that did.

        The loop announces a moment - a combatant acting, a GM turn coming round -
        and each condition decides for itself whether that is its cue. Nothing
        here knows what any condition is or how long it should last.

        A condition with no `end` never ends, which is how "until the scene ends"
        is expressed.
        """
        ended = []
        for (holder_id, name), condition in list(self.conditions.items()):
            if holder_id != id(holder) or condition.end is None:
                continue
            if condition.end(holder, self, moment):
                self.clear_condition(holder, name)
                ended.append(name)
        return ended

    def is_vulnerable(self, combatant) -> bool:
        """Whether rolls against `combatant` have Advantage right now.

        Two sources, and the caller shouldn't have to know there are two: a PC
        with every Stress marked is Vulnerable by the rules, and anybody can be
        made Vulnerable by content. Asking here keeps `PlayerCharacter` from
        needing to see the fight it's in.

        Immunity is *not* checked here - that's a separate question with its own
        dispatch, and the one caller that cares asks both.
        """
        return combatant.is_vulnerable or self.has_condition(combatant, VULNERABLE)

    def token_count(self, holder, name: str) -> int:
        """How many `name` tokens `holder` is currently holding."""
        return self.tokens.get((id(holder), name), 0)

    def add_token(self, holder, name: str, cap: int) -> bool:
        """Place one token, up to `cap`. Returns whether there was room for it."""
        if self.token_count(holder, name) >= cap:
            return False
        self.tokens[(id(holder), name)] = self.token_count(holder, name) + 1
        return True

    def set_token(self, holder, name: str, value: int) -> None:
        """Set a token to an exact value, rather than counting up to a cap.

        Some content doesn't hold a *count* of anything - it remembers a single
        number for the length of a fight. Strange Patterns remembers which face
        the Wizard is watching for; Ranger's Focus remembers which adversary is
        marked, as the `id()` of that adversary. Both are one value that gets
        overwritten rather than incremented, which `add_token` can't express.
        """
        self.tokens[(id(holder), name)] = value

    def spend_tokens(self, holder, name: str, amount: int) -> int:
        """Spend up to `amount` tokens; return how many were actually spent."""
        spent = min(amount, self.token_count(holder, name))
        if spent > 0:
            self.tokens[(id(holder), name)] = self.token_count(holder, name) - spent
        return spent

    def note(self, message: str) -> None:
        """Record a line of play-by-play, if this run asked for one."""
        if self.logging:
            self.log.append(message)
