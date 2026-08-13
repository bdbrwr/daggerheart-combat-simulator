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

    One activation is free; each one after costs a Fear. An adversary acts at
    most once per GM turn, and the turn stops at party size + 1 activations
    even if there's Fear to burn.

    Fear left over is not spent on anything else yet - adversary Fear features
    aren't implemented, and that's where the rest of the pool would go.
    """
    state.gm_turns += 1
    activated: set[int] = set()

    while len(activated) < state.max_activations_per_gm_turn:
        available = [a for a in state.living_adversaries if id(a) not in activated]
        if not available:
            break

        if activated and not state.spend_fear(1):
            break  # out of Fear, so out of extra activations

        adversary = available[0]
        activated.add(id(adversary))
        state.adversary_activations += 1
        take_adversary_turn(adversary, state)

        if state.party_is_down:
            break

    state.spotlight = Side.PCS
