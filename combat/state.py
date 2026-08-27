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
from content.conditions import UNSEEN, VULNERABLE, Condition
from content.names import canonical
from content.registry import refuses_condition

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

    # Extra spotlights that cost the GM **nothing** - no Fear, and not counted
    # against the turn's cap. Kept apart from `granted` rather than merged with a
    # flag, because the loop has to ask two different questions of them: whether
    # this adversary may act again, and whether acting is free. Cleared with
    # `granted` at the start of each GM turn.
    #
    # `free_granted` is what content handed out; `free_used` is how much of it the
    # loop has spent. Two counters rather than one that decrements, so
    # `_next_adversary` can still see the whole allowance when it works out who
    # is eligible.
    free_granted: dict[int, int] = field(default_factory=dict)
    free_used: dict[int, int] = field(default_factory=dict)

    # Whoever is acting on a free spotlight *right now*, or None. Set by the GM
    # turn around the activation it is resolving, so content can ask whether this
    # particular attack is happening on a spotlight somebody else paid for. The
    # Young Dryad's `Voice of the Forest` needs it: the allies it rallies deal
    # half damage "while spotlighted this way", and nothing else can tell that
    # activation apart from the ally's own.
    acting_free: Adversary | None = None

    # Whoever is taking a spotlight *right now*, free or paid, or None. Set by
    # the GM turn around every activation, so it is None for the whole of a PC's
    # spotlight and between activations.
    #
    # It exists because damage arrives at a PC with no idea who threw it -
    # `take_damage` carries an amount and a type and nothing else - and content
    # that responds to being hit sometimes has to know. Arcana's Counterspell
    # rolls against the attacker's own Difficulty, and there is no other way to
    # reach it: threading an attacker through `take_damage` would change that
    # signature on both sides of the table and in every stand-in that implements
    # the Target protocol.
    #
    # None is an answer, not a gap. Damage arriving while nothing is spotlighted
    # is the party's own - On Fire burning whoever is carrying it - and content
    # asking about an adversary should decline rather than guess at one.
    spotlighted: Adversary | None = None

    # Spotlights content has *used up* on somebody other than whoever is acting,
    # during the current GM turn. The mirror of `granted`, cleared with it. A
    # Minion's Group Attack spotlights the whole swarm in one activation, and the
    # rest of the swarm must not then act again in the same turn.
    consumed: dict[int, int] = field(default_factory=dict)

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
    def defeated_adversaries(self) -> list[Adversary]:
        """Adversaries that have fallen but are still on the field.

        The bodies. Nothing in the loop reads this - a defeated adversary is out
        of `living_adversaries` and that is all the loop needs - but content can
        ask, and one does: the Patchwork Zombie Hulk's `Another for the Pile`
        eats a corpse to clear an HP and a Stress, and the user's ruling is that
        a defeated adversary is what a corpse means here.

        An adversary taken off the field by `remove` rather than defeated - the
        Green Ooze splitting - leaves no body, which is right: it did not die.
        """
        return [adversary for adversary in self.adversaries if adversary.is_defeated]

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

    def grant_activation(self, holder, free: bool = False) -> None:
        """Let `holder` be spotlighted once more this GM turn.

        The Construct's Overload ("the Construct can then take the spotlight
        again") grants one mid-turn, which a feature registered on
        `activation_limit` can't express - that answers before the turn starts.

        By default the extra spotlight is bounded by the turn's own cap and
        charged the usual Fear, on the same reasoning as Relentless: the cap is
        what holds a simulated fight to something a GM would run, so nothing
        reaches around it.

        **`free=True` reaches around both**, and is the user's ruling on the Young
        Dryad's `Voice of the Forest`: that feature's 1d4 spotlights cost the GM
        no Fear and do not count against party size + 1. The machinery is generic
        so anything else can be flipped to it later with one keyword, but as a
        *ruling* it is scoped to that one feature - Rally Guards, Move as a Unit,
        Tactician and Overload were all ruled the other way and are unchanged.
        See SIMULATION-RULES.md.
        """
        table = self.free_granted if free else self.granted
        table[id(holder)] = table.get(id(holder), 0) + 1

    def granted_activations(self, holder) -> int:
        return self.granted.get(id(holder), 0)

    def free_activations(self, holder) -> int:
        """How many free spotlights `holder` was handed this GM turn, spent or not."""
        return self.free_granted.get(id(holder), 0)

    def has_free_activation(self, holder) -> bool:
        """Whether `holder` still has a free spotlight left to take."""
        return self.free_used.get(id(holder), 0) < self.free_activations(holder)

    def take_free_activation(self, holder) -> bool:
        """Spend one of `holder`'s free spotlights; return whether there was one.

        The GM takes a free spotlight before a paid one whenever both are
        available, which is what anybody would do - the paid one is still there
        afterwards if the turn has room for it.
        """
        if not self.has_free_activation(holder):
            return False
        self.free_used[id(holder)] = self.free_used.get(id(holder), 0) + 1
        return True

    def acting_freely(self, combatant) -> bool:
        """Whether `combatant` is taking a free spotlight at this very moment.

        False everywhere except inside the activation itself, which is what makes
        it the right question for content scoped to "while spotlighted this way".
        Asked rather than inferred from `free_used`, which would still read as
        spent for the rest of the GM turn.
        """
        return self.acting_free is combatant

    def consume_activation(self, holder) -> None:
        """Use up one of `holder`'s spotlights without them choosing to act.

        The mirror of `grant_activation`, and the piece that lets one feature
        move several combatants. The SRD's Group Attack "spotlights all Giant
        Rats within Close range" and resolves them as one shared attack: that is
        a single activation as far as the GM turn's budget goes, but every Rat
        in it has now been spotlighted and must not come round again this turn.

        Deliberately separate from the loop's own tally of who has acted. That
        tally is about who the loop *chose*; this is about spotlights content
        spent on its own account, and keeping them apart means the loop never has
        to know which feature did it.
        """
        self.consumed[id(holder)] = self.consumed.get(id(holder), 0) + 1

    def consumed_activations(self, holder) -> int:
        return self.consumed.get(id(holder), 0)

    def summon(self, adversary: Adversary) -> None:
        """Add an adversary to the fight already under way.

        The Jagged Knife Lieutenant's *More Where That Came From* is the first
        thing that does this, and it is a bigger change than it looks: until now
        the field an encounter spawned was the field the fight ended with, and
        several places assume only that it can shrink.

        What follows from adding one here rather than anywhere else: it is a
        living adversary immediately, so it can be targeted and can be
        spotlighted this same GM turn (the loop re-reads `living_adversaries`
        each time it picks). It has no activations spent, so it goes before
        anything that has already acted. And it counts toward victory - the
        party has to clear it like anything else.

        The caller passes a **spawned** combatant, not a catalogue definition, so
        summoning twice never shares one HP track.
        """
        self.adversaries.append(adversary)

    def summon_ally(self, combatant: PlayerCharacter) -> None:
        """Add a temporary combatant to the **party** already under way.

        The party-side mirror of `summon`, and the Book of Exota's *Create
        Construct* is the first thing that needs it: the user's ruling is that
        the construct "becomes a temporary party member with 1 HP" - so it can be
        swung at, it draws attacks away from the PCs, and it falls apart to any
        damage that reaches it, which is what the card says happens.

        **Rebinds `party` rather than appending to it**, and that is the whole
        trick. `combat/fight.py` holds the list the encounter spawned and hands
        that same list to the `FightResult`, so an append would put the construct
        into every per-member statistic the report prints - unmarked HP, near
        death, Hope - as though it were one of the party. Rebinding means the
        fight sees it and the report does not.

        Two consequences that follow from it being a party member, both real and
        both intended by the ruling. It counts toward `party_is_down`, so a fight
        is not lost while the construct still stands; and
        `max_activations_per_gm_turn` is party size + 1, so summoning one also
        buys the GM an extra activation each turn. See SIMULATION-RULES.md.
        """
        self.party = [*self.party, combatant]

    def remove(self, adversary: Adversary) -> None:
        """Take an adversary out of the fight **without** defeating it.

        The mirror of `summon`, and the Green Ooze's *Split* is why it exists:
        the Ooze becomes two Tiny Green Oozes, so it leaves the field at a moment
        when the party is worse off than before, not better.

        Marking its HP would have done the same job to the loop - everything asks
        `is_defeated` - and told a lie to the reader. A play-by-play saying "the
        Green Ooze is defeated" as the field doubles reads as a win, and any
        future statistic counting adversaries defeated would have counted it.

        Nothing else changes. The removed adversary is not in `living_adversaries`
        so it can't be targeted or spotlighted, and it no longer counts toward
        victory - which is right, since it isn't there. Stale entries it leaves in
        the targeting memory and the token tables are harmless: both are keyed by
        `id()` and nothing looks up a combatant that isn't on the field.

        Its **conditions are not** harmless, which is why they are released here -
        see `release_conditions_from`. A hold whose only printed way out is
        something happening to this adversary can never end once it has left.
        """
        self.release_conditions_from(adversary)
        self.adversaries = [
            standing for standing in self.adversaries if standing is not adversary
        ]

    # --- Conditions ----------------------------------------------------------

    def apply_condition(self, holder, condition: Condition) -> None:
        """Put `condition` on `holder`, replacing any of the same name.

        Replacing rather than stacking: nothing in the SRD makes being Vulnerable
        twice worse than once, and a re-application refreshes how long it lasts,
        which is what the later of two overlapping effects should do.

        **Content the holder carries can refuse it outright** - the Valor card
        Bold Presence shrugs one off per rest - so this is the moment "when you
        would gain a condition" happens, and the only place it can be asked.
        Asked generically; nothing here knows what any such content is.

        A refresh is *not* gaining a condition, so a holder who already carries
        one of that name is never offered the refusal. Otherwise a once-per-rest
        dodge would be spent on a Vulnerable the PC already had.
        """
        if not self.has_condition(holder, condition.name) and refuses_condition(
            holder, condition, self
        ):
            self.note(f"{holder.name} shrugs off {condition.name}")
            return
        self.conditions[(id(holder), condition.name)] = condition

    def has_condition(self, holder, name: str) -> bool:
        return (id(holder), name) in self.conditions

    def condition_on(self, holder, name: str) -> Condition | None:
        """The condition record itself, for content that needs more than its name.

        `has_condition` answers the usual question. This one exists because a
        condition knows **who applied it**, and some content asks: the Jagged
        Knife Kneebreaker's `I've Got 'Em` doubles damage against creatures
        *it* has Restrained, not against anyone who happens to be held.
        """
        return self.conditions.get((id(holder), name))

    def clear_condition(self, holder, name: str) -> None:
        self.conditions.pop((id(holder), name), None)

    def release_conditions_from(self, source) -> list[str]:
        """End the conditions `source` applied that **only `source`** could end.

        Called whenever an adversary leaves the fight, by either route: defeated,
        or removed outright by something like the Green Ooze's *Split*.

        The discriminator is a condition with a `source` and **no `end` of its
        own**. Such a condition is written to be lifted by something happening to
        whoever applied it - Envelop ends when the Ooze takes Severe damage, Grab
        and Drag when the Defender does - and once that adversary is off the
        field it can never take any damage again. Without this the condition
        would sit on the PC for the rest of the fight with no way out, which is
        harsher than anything the SRD prints.

        **A condition that carries its own `end` is left alone**, and that is the
        important half. The Minor Chaos Elemental's Sickening Flux makes a PC
        Vulnerable "until their next rest or they clear a HP" - it names its own
        exit, so killing the Elemental must not cure it. Same for the holds that
        offer an escape roll: a PC Restrained by a dead Bear can still roll out,
        and nothing is stranded.

        Returns the names lifted, so a caller can report them.
        """
        released: list[str] = []
        for holder in [*self.party, *self.adversaries]:
            for (holder_id, name), condition in list(self.conditions.items()):
                if holder_id != id(holder):
                    continue
                if condition.source is not source or condition.end is not None:
                    continue
                self.clear_condition(holder, name)
                self.note(
                    f"{holder.name} is no longer {name} - {source.name} is gone"
                )
                released.append(name)
        return released

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

    def apply_condition_effects(self, holder, moment: str) -> None:
        """Let every condition on `holder` do whatever it does at `moment`.

        The twin of `expire_conditions`, and announced the same way: the loop
        says what is happening and each condition decides whether that is its
        cue. Most have no `effect` at all, because their effect is already asked
        for somewhere else - Vulnerable is read where Advantage is worked out.

        The Giant Scorpion's Poison is the case this exists for: "roll a d6
        before you make an action roll; on 4 or lower, mark a Stress" is a cost
        nothing else in the simulator was already asking about.
        """
        for (holder_id, _), condition in list(self.conditions.items()):
            if holder_id != id(holder) or condition.effect is None:
                continue
            condition.effect(holder, self, moment)

    def disadvantaged_on(self, holder, trait: str) -> bool:
        """Whether a condition on `holder` hobbles rolls made with `trait`.

        The counterpart to `is_vulnerable`, for conditions that reach a roll
        rather than the rolls made against one. The Archer Guard's Hobbling Shot
        is the first: "disadvantage on Agility Rolls until they clear at least
        1 HP".

        Matched canonically, like every other name in the project - a condition
        written with "Agility" and a sheet keyed "agility" are the same trait,
        and a lookup that missed on capitalisation would leave the condition
        sitting on the PC doing nothing at all.
        """
        wanted = canonical(trait)
        return any(
            holder_id == id(holder)
            and any(canonical(hobbled) == wanted for hobbled in condition.disadvantage_on)
            for (holder_id, _), condition in self.conditions.items()
        )

    def is_hidden(self, combatant) -> bool:
        """Whether rolls against `combatant` have Disadvantage right now.

        The exact mirror of `is_vulnerable`, and the reason both live here rather
        than on the combatants: a PC doesn't know which fight it is in, and an
        adversary knows nothing about conditions at all.

        Nothing is Hidden by the rules the way a PC with every Stress marked is
        Vulnerable, so this is only ever content having applied it.

        **Two condition names, one effect.** The SRD prints Hidden and Invisible
        separately and they come to the same thing here - Grace's *Invisibility*
        says "attack rolls against them are made with disadvantage", which is
        precisely what Hidden was ruled to be worth. They stay two names so a
        report says which card fired, and `content/conditions.py`'s `UNSEEN`
        holds the list, so this reader never grows a branch.
        """
        return any(self.has_condition(combatant, name) for name in UNSEEN)

    def cannot_act(self, combatant) -> bool:
        """Whether a condition currently stops `combatant` acting at all.

        Read off `Condition.prevents_action` rather than by name, so nothing here
        or in the loop knows that Stunned is what answers - and a second such
        condition would need no change.

        The activation is still spent when this is true, and the Fear it cost is
        still gone. That is deliberate and it is the whole weight of the thing:
        the GM turn charges before an adversary is asked what it does, exactly as
        it does for the Green Ooze's `Slow`.
        """
        return any(
            holder_id == id(combatant) and condition.prevents_action
            for (holder_id, _), condition in self.conditions.items()
        )

    def searchable_condition(self, combatant):
        """The condition on `combatant` that somebody could spend a roll to end.

        Returns the `Condition` carrying a `found_by`, or None. Asked by the turn
        policy when it decides whether a PC spends their action roll hunting for
        something rather than swinging at it; nothing here knows that Hidden is
        the only such condition today.
        """
        for (holder_id, _), condition in self.conditions.items():
            if holder_id == id(combatant) and condition.found_by is not None:
                return condition
        return None

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
