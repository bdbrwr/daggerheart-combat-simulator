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
    size + 1. Then the spotlight goes back. Content can hand out an activation
    that is outside both the charge and the cap; see `_take_gm_turn`.

Nothing here decides *what* a combatant does with its turn - that's
combat/policy.py. This module only decides who is acting and when the fight
is over.
"""

import random

from combat.common import FightOutcome, Side
from combat.policy import take_adversary_turn, take_pc_turn
from combat.report import FightResult
from combat.state import FightState
from content import (
    activations_allowed,
    apply_ally_on_roll,
    apply_on_party_attack_roll,
    apply_on_roll,
    converted_party_roll,
    extra_spotlight_cost,
    fear_is_converted,
    spotlights_while_defeated,
)
from content.conditions import ON_A_GM_TURN, WHEN_THEY_ACT, WHEN_THEY_ATTACK
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

    **There is deliberately no third ending.** Spotting the point where the rest
    of a fight is a formality - every adversary that could still threaten the
    party is down, only Minions left standing - was considered and ruled out.
    The same field means different things in different encounters: a few bandit
    Lackeys after their Lieutenant falls really is over, while a plague of rats
    *is* the encounter, and no rule written here can tell those apart. So a fight
    is played to the end, and the extra rounds are counted as what they are.

    That also settles the shape of a feature that adds adversaries mid-fight -
    the Lieutenant's More Where That Came From - which needs no cap of its own.
    Minions die to any damage, so a summoned field clears quickly; `MAX_PC_ACTIONS`
    remains the only backstop, and it is scaffolding rather than a rule.
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
        # Nobody standing can act - every conscious PC is sheltered, stunned or
        # otherwise held. The spotlight goes to the GM rather than being held by a
        # party that can do nothing with it, which is also the only thing stopping
        # `_resolve` spinning: a spotlight that resolves into nothing never
        # increments `pc_actions`, so the safety net would never catch it.
        state.note("Nobody in the party can act; the spotlight passes")
        state.spotlight = Side.GM
        return

    state.acted_this_pass.add(id(pc))
    result = take_pc_turn(pc, state)

    # Conditions that *do* something when their holder acts get their moment
    # first - On Fire burns whoever is carrying it. Before the expiry below,
    # because the SRD's wording is "if they are still On Fire at the end of their
    # action": the burn is part of the action ending, and shaking the condition
    # off comes after.
    state.apply_condition_effects(pc, WHEN_THEY_ACT)

    # A narrower moment than the one below, announced only when the spotlight
    # resolved into a roll at all. Arcana's *Cloaking Blast* ends "when you make
    # an attack", and this is as close as the loop can get: `made_an_attack` is
    # the same discriminator the GM-side watchers below use, and it means "this
    # action rolled" rather than "this action was an attack". A spotlight spent on
    # Healing Hands therefore breaks the cloak too, which is declared as a gap on
    # the card and errs the conservative way.
    #
    # Announced **here**, before the roll's outcome is spent, and that ordering is
    # load-bearing: content whose trigger is the roll having succeeded applies its
    # condition from `apply_on_roll`, which runs afterwards - so a cloak raised off
    # an attack spell is not broken by the very attack that raised it.
    if result is not None and result.made_an_attack:
        for ended in state.expire_conditions(pc, WHEN_THEY_ATTACK):
            state.note(f"{pc.name} is no longer {ended}")

    # "Until they next act" ends *after* the acting, so a PC knocked over is
    # still Vulnerable for the action that gets them back up - which is the whole
    # point of having been knocked over.
    for ended in state.expire_conditions(pc, WHEN_THEY_ACT):
        state.note(f"{pc.name} is no longer {ended}")

    if result is None:  # nothing left to attack; the loop will call it
        return

    state.pc_actions += 1

    # The GM's side gets to rewrite how the roll came out before anything reads
    # it - the Jagged Knife Hexer's Curse turns a roll with Hope into one with
    # Fear. Asked here, once, because this is where a duality outcome is spent:
    # the Hope it hands the PC, the Fear it hands the GM, and whether the party
    # keeps the spotlight all follow from the same answer.
    roll = converted_party_roll(pc, result.attack_roll, state)
    _apply_duality_outcome(pc, roll, state)

    # GM-side content that only watches the party roll - the Head Guard's
    # countdown ticks on every PC attack roll. After the conversion, so both see
    # the same roll, and guarded on there having been an attack at all.
    if result.made_an_attack:
        apply_on_party_attack_roll(pc, roll, state)

    # The spotlight swings on a failure or on Fear. A success with Hope - and a
    # critical, which is a success and never "with Fear" - keeps it.
    passes = not roll.is_success or (roll.outcome is DualityOutcome.FEAR)
    if passes:
        state.spotlight = Side.GM


def _next_pc(state: FightState):
    """Whoever's turn it is: a random PC who hasn't gone yet this pass.

    Random rather than fixed order because there's no turn order to model -
    with the spotlight staying on a hot party, a fixed order would quietly
    hand the first-listed PC more actions than the rest. Everyone goes once
    before anyone goes twice; when the party has all acted the pass resets and
    they keep going.

    **A PC a condition stops from acting is skipped rather than spotlighted.**
    The GM side spends the activation and the Fear that bought it on a Stunned
    adversary, because the GM chose to spotlight it; the party's spotlight isn't
    bought, so it simply goes to somebody who can use it. Read generically off
    `Condition.prevents_action` - Sage's *Wild Fortress* shelters two PCs who
    "can't make attacks", and a Stunned PC would answer the same way if anything
    stunned one.

    Returns None when nobody can act, which the caller turns into the spotlight
    passing to the GM. That matters: without it a party entirely unable to act
    would hold the spotlight forever.
    """
    standing = [pc for pc in state.conscious_party if not state.cannot_act(pc)]
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

    # And content another PC carries that watches *this* one's roll, which the
    # holder-scoped call above can't reach - Valor's Lean on Me consoles an ally
    # who just failed. Asked party-wide; nothing here knows what any of it is.
    apply_ally_on_roll(pc, roll, state)

    if roll.outcome is DualityOutcome.CRIT:
        pc.gain_hope(1)
        pc.clear_stress(1)
    elif roll.outcome is DualityOutcome.HOPE:
        pc.gain_hope(1)
    else:
        # Party content that stops the Fear arriving at all - Midnight's
        # Midnight-Touched turns it into a Hope for a PC who has none. Asked here
        # because this is the one place a PC's roll hands the GM anything, and
        # `apply_on_roll` above is told how the roll came out without being able to
        # change what follows. Content that answers has already done whatever it
        # does instead; nothing here knows what any of it is.
        if fear_is_converted(pc, state):
            return
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

    **Some activations are free**, and those are outside both halves of that
    rule: they cost no Fear and don't count toward the cap. Only the Young
    Dryad's `Voice of the Forest` hands any out today - see
    `FightState.grant_activation` - so for every other fight this loop behaves
    exactly as it did before. `paid` rather than `taken` is what the cap and the
    turn's one free-of-Fear activation are measured against, which is the whole
    of the difference.

    Fear left over is not spent on anything else yet - adversary Fear features
    aren't implemented, and that's where the rest of the pool would go.
    """
    state.gm_turns += 1
    state.granted.clear()
    state.consumed.clear()
    state.free_granted.clear()
    state.free_used.clear()

    # A condition the party put on an adversary gets its chance to end here,
    # which for most of them means the GM paying a Fear to shake it off. Done
    # before anything is spotlighted, so an adversary freed this turn can act.
    for adversary in state.living_adversaries:
        for ended in state.expire_conditions(adversary, ON_A_GM_TURN):
            state.note(f"{adversary.name} is no longer {ended}")

    taken: dict[int, int] = {}
    paid = 0
    out_of_fear = False

    while True:
        # Whether the turn can still take an activation it has to pay for. Once
        # it can't, the loop keeps going for *free* ones only rather than
        # stopping - a rallied ally's spotlight was bought by the feature that
        # granted it, not by this turn's budget.
        room = not out_of_fear and paid < state.max_activations_per_gm_turn
        adversary = _next_adversary(state, taken, paid_allowed=room)
        if adversary is None:
            break

        free = state.take_free_activation(adversary)
        if not free:
            # One paid activation a turn is free of Fear; every one after costs
            # a Fear. Some adversaries cost extra on top, even for the first -
            # the Cave Ogre's Ramp Up. Asked generically; nothing here knows the
            # feature.
            owed = (0 if not paid else 1) + extra_spotlight_cost(adversary, state)
            if owed and not state.spend_fear(owed):
                # Can't afford this one, so not any other paid one either - but
                # a free spotlight elsewhere on the field is still owed.
                out_of_fear = True
                continue
            paid += 1

        taken[id(adversary)] = taken.get(id(adversary), 0) + 1
        state.adversary_activations += 1

        # Content scoped to "while spotlighted this way" - the Young Dryad's
        # Voice of the Forest - has no other way to tell this activation from one
        # the adversary would have had anyway. Cleared in a `finally` so a
        # feature that raises can't leave the field permanently flagged.
        state.acting_free = adversary if free else None
        # And who is up at all, free or paid. Content on the receiving end of an
        # attack has no other way to find out what is hitting it - see
        # `FightState.spotlighted`. Cleared in the same `finally`, so a feature
        # that raises can't leave the field pointing at an adversary that isn't
        # acting.
        state.spotlighted = adversary
        try:
            take_adversary_turn(adversary, state)
        finally:
            state.acting_free = None
            state.spotlighted = None

        # The same moment the party side announces, on the GM's side of the
        # table. Until On Fire existed nothing needed it - every condition an
        # adversary could carry either did nothing by itself or ended on a GM
        # turn - so this is where the asymmetry gets closed rather than a rule of
        # its own. Effects before expiry, for the reason `_take_pc_spotlight`
        # gives.
        state.apply_condition_effects(adversary, WHEN_THEY_ACT)
        for ended in state.expire_conditions(adversary, WHEN_THEY_ACT):
            state.note(f"{adversary.name} is no longer {ended}")

        if state.party_is_down:
            break

    state.spotlight = Side.PCS


def _next_adversary(state: FightState, taken: dict[int, int], paid_allowed: bool = True):
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

    **A defeated adversary can be a candidate**, if something it carries says so.
    The Skeleton Warrior's `Won't Stay Dead` needs a spotlight to roll the d6 that
    brings it back, so being down is not by itself a reason the GM can't spend one
    on it. Asked generically; nothing here knows the feature exists, and for every
    other stat block the answer is False and the list is `living_adversaries`
    exactly as before. Such a spotlight is charged and capped like any other -
    the permission is all the hook grants.

    `paid_allowed` is False once the turn has run out of either cap or Fear, and
    narrows the field to adversaries still holding a **free** spotlight. Those
    were paid for by the feature that granted them, so the turn's budget being
    spent is not a reason to leave one unused.
    """

    def spent(adversary) -> int:
        return taken.get(id(adversary), 0) + state.consumed_activations(adversary)

    def allowance(adversary) -> int:
        return (
            activations_allowed(adversary, state)
            + state.granted_activations(adversary)
            + state.free_activations(adversary)
        )

    standing = state.living_adversaries + [
        adversary
        for adversary in state.adversaries
        if adversary.is_defeated and spotlights_while_defeated(adversary, state)
    ]
    available = [
        adversary
        for adversary in standing
        if spent(adversary) < allowance(adversary)
        and (paid_allowed or state.has_free_activation(adversary))
    ]
    if not available:
        return None

    fewest = min(spent(adversary) for adversary in available)
    return random.choice([a for a in available if spent(a) == fewest])
