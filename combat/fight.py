"""The combat loop - one simulated fight, start to finish.

Daggerheart has no initiative and no turn order. What it has is the spotlight,
and this loop is mostly the rules for moving it:

  * The party starts with it, unless the encounter says otherwise.
  * A PC takes any number of actions that need no roll, then one that does.
  * It swings to the GM when that roll fails, or comes up with Fear. A roll
    with Fear also hands the GM a Fear.
  * A roll with Hope hands the PC a Hope; a critical also clears a Stress.
  * On a success with Hope the party keeps the spotlight and someone else
    goes, so a hot party can leave the GM waiting - which is the point.
  * A GM turn spotlights one adversary for free and buys further activations
    at 1 Fear each, no adversary twice in the same turn, up to a cap of party
    size + 1. Then the spotlight goes back.

Nothing here decides *what* a combatant does with its turn - that's
combat/policy.py. This module only decides who is acting and when the fight
is over.
"""

import random

from combat.common import FightOutcome, Side
from combat.policy import take_adversary_turn, take_pc_turn
from combat.report import FightResult
from combat.state import FightState
from content import activations_allowed, apply_on_roll, extra_spotlight_cost
from content.conditions import ON_A_GM_TURN, WHEN_THEY_ACT
from dice.duality import DualityOutcome

# Safety net for a matchup that can't resolve - PCs who can't beat a
# Difficulty, adversaries who can't beat an Evasion. Such a fight would
# otherwise loop forever; capping it turns a hang into a reported
# FightOutcome.UNRESOLVED that a Monte Carlo run can count and exclude.
MAX_PC_ACTIONS = 500


def run_fight(encounter, logging: bool = False) -> FightResult:
    """Simulate one fight and report how it went.

    Spawns both sides fresh from the encounter, so the same Encounter object
    can be run any number of times without a previous fight leaking in.

    Set `logging` for a play-by-play in the result's `log` - useful when a
    single fight looks wrong, and off by default because 10,000 of them
    shouldn't be building strings.
    """
    party, adversaries = encounter.spawn()
    state = FightState(
        encounter_name=encounter.name,
        party=party,
        adversaries=adversaries,
        spotlight=encounter.starting_spotlight,
        fear=encounter.starting_fear,
        rest=encounter.rest,
        logging=logging,
    )
    state.note(
        f"{encounter.name}: {len(party)} PC(s) vs {len(adversaries)} adversaries, "
        f"GM starts with {state.fear} Fear, {state.spotlight.value} hold the spotlight"
    )

    outcome = _resolve(state)

    state.note(f"Fight ends: {outcome.value}")
    return FightResult(
        encounter_name=encounter.name,
        outcome=outcome,
        party=party,
        adversaries=adversaries,
        pc_actions=state.pc_actions,
        adversary_activations=state.adversary_activations,
        gm_turns=state.gm_turns,
        fear_gained=state.fear_gained,
        fear_spent=state.fear_spent,
        fear_remaining=state.fear,
        unconscious_pcs=sum(1 for pc in party if not pc.is_conscious),
        scars_gained=sum(pc.scars for pc in party),
        log=state.log,
    )


def _resolve(state: FightState) -> FightOutcome:
    """Pass the spotlight back and forth until one side is out."""
    while True:
        finished = _check_finished(state)
        if finished is not None:
            return finished

        if state.pc_actions >= MAX_PC_ACTIONS:
            return FightOutcome.UNRESOLVED

        if state.spotlight is Side.PCS:
            _take_pc_spotlight(state)
        else:
            _take_gm_turn(state)


def _check_finished(state: FightState) -> FightOutcome | None:
    """Victory when every adversary is down, defeat when every PC is.

    Defeat is "everyone unconscious", not "everyone dead" - simulated PCs
    always take Avoid Death, so a party is beaten when nobody is left standing.

    Later: it would be worth spotting the point where the rest of a fight is a
    formality - every adversary that could still threaten the party is down,
    and the remaining rounds only add turns to the count. A GM would narrate
    that ending rather than roll it out, and since one of the questions this
    tool is meant to answer is whether an encounter drags, counting those
    turns as though they were real fighting would bias the length metrics.
    """
    if state.adversaries_are_cleared:
        return FightOutcome.PARTY_VICTORY
    if state.party_is_down:
        return FightOutcome.PARTY_DEFEAT
    return None


def _take_pc_spotlight(state: FightState) -> None:
    """One PC acts, then the spotlight either stays with the party or moves."""
    pc = _next_pc(state)
    if pc is None:
        return

    state.acted_this_pass.add(id(pc))
    result = take_pc_turn(pc, state)

    # "Until they next act" ends *after* the acting, so a PC knocked over is
    # still Vulnerable for the action that gets them back up - which is the whole
    # point of having been knocked over.
    for ended in state.expire_conditions(pc, WHEN_THEY_ACT):
        state.note(f"{pc.name} is no longer {ended}")

    if result is None:  # nothing left to attack; the loop will call it
        return

    state.pc_actions += 1
    _apply_duality_outcome(pc, result.attack_roll, state)

    # The spotlight swings on a failure or on Fear. A success with Hope - and a
    # critical, which is a success and never "with Fear" - keeps it.
    passes = not result.attack_roll.is_success or (
        result.attack_roll.outcome is DualityOutcome.FEAR
    )
    if passes:
        state.spotlight = Side.GM


def _next_pc(state: FightState):
    """Whoever's turn it is: a random PC who hasn't gone yet this pass.

    Random rather than fixed order because there's no turn order to model -
    with the spotlight staying on a hot party, a fixed order would quietly
    hand the first-listed PC more actions than the rest. Everyone goes once
    before anyone goes twice; when the party has all acted the pass resets and
    they keep going.
    """
    standing = state.conscious_party
    if not standing:
        return None

    waiting = [pc for pc in standing if id(pc) not in state.acted_this_pass]
    if not waiting:
        state.acted_this_pass.clear()
        waiting = standing

    return random.choice(waiting)


def _apply_duality_outcome(pc, roll, state: FightState) -> None:
    """Hand out the Hope or Fear the roll generated.

    Both Hope outcomes give the PC a Hope whether the roll succeeded or not,
    and both Fear outcomes give the GM a Fear on the same terms. A critical
    additionally clears a Stress.
    """
    # Content keyed on how the roll came out - a token for rolling with Fear,
    # and anything else built that way - gets its say before the Hope and Fear
    # are handed out.
    apply_on_roll(pc, roll, state)

    if roll.outcome is DualityOutcome.CRIT:
        pc.gain_hope(1)
        pc.clear_stress(1)
    elif roll.outcome is DualityOutcome.HOPE:
        pc.gain_hope(1)
    else:
        gained = state.gain_fear(1)
        if not gained:
            state.note("Fear is already at its cap; the roll with Fear adds nothing")


def _take_gm_turn(state: FightState) -> None:
    """The GM spotlights adversaries, then hands the spotlight back.

    One activation is free; each one after costs a Fear. The turn stops at party
    size + 1 activations even if there's Fear to burn.

    An adversary acts once per GM turn unless something they carry says
    otherwise - the SRD's `Relentless (X)` allows X. That's asked generically
    through `activations_allowed`; nothing here knows the feature exists, and
    Relentless says to "spend Fear as usual", which the loop already does for
    every activation past the first.

    Fear left over is not spent on anything else yet - adversary Fear features
    aren't implemented, and that's where the rest of the pool would go.
    """
    state.gm_turns += 1
    state.granted.clear()
    state.consumed.clear()

    # A condition the party put on an adversary gets its chance to end here,
    # which for most of them means the GM paying a Fear to shake it off. Done
    # before anything is spotlighted, so an adversary freed this turn can act.
    for adversary in state.living_adversaries:
        for ended in state.expire_conditions(adversary, ON_A_GM_TURN):
            state.note(f"{adversary.name} is no longer {ended}")

    taken: dict[int, int] = {}

    while sum(taken.values()) < state.max_activations_per_gm_turn:
        adversary = _next_adversary(state, taken)
        if adversary is None:
            break

        # One activation a turn is free; every one after costs a Fear. Some
        # adversaries cost extra on top, even for the free one - the Cave Ogre's
        # Ramp Up. Asked generically; nothing here knows the feature.
        owed = (0 if not taken else 1) + extra_spotlight_cost(adversary, state)
        if owed and not state.spend_fear(owed):
            break  # can't afford this one, so not the next one either

        taken[id(adversary)] = taken.get(id(adversary), 0) + 1
        state.adversary_activations += 1
        take_adversary_turn(adversary, state)

        if state.party_is_down:
            break

    state.spotlight = Side.PCS


def _next_adversary(state: FightState, taken: dict[int, int]):
    """Which adversary the GM spotlights next, or None if nobody is left.

    Everyone who can still act goes before anyone goes again, so a Relentless
    adversary takes its extra spotlights after the rest of the field rather than
    swallowing the whole turn up front. That matches how the extra activation
    reads at a table: it's the dangerous thing coming back round, not the only
    thing that ever moves.

    Ties are broken at random rather than by list position. The order an
    encounter happens to spawn its adversaries in carries no meaning and must
    never decide an outcome - the same rule `_next_pc` follows.

    An adversary's spotlights can be used up by something other than this loop
    choosing it: a Minion's Group Attack sweeps its whole swarm into one shared
    attack, and each Minion in it has been spotlighted. Those are counted here
    through `consumed_activations`, so a swept Minion doesn't come round again -
    and, since they also count toward "who has gone least", the rest of the field
    gets its turn before anything acts twice.
    """

    def spent(adversary) -> int:
        return taken.get(id(adversary), 0) + state.consumed_activations(adversary)

    available = [
        adversary
        for adversary in state.living_adversaries
        if spent(adversary)
        < activations_allowed(adversary, state) + state.granted_activations(adversary)
    ]
    if not available:
        return None

    fewest = min(spent(adversary) for adversary in available)
    return random.choice([a for a in available if spent(a) == fewest])
