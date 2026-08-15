"""What a combatant chooses to do - the simulator's stand-in for a table.

Separated from the loop because this is the part that will keep changing.
The spotlight rules are fixed; which ability a Guardian reaches for at 3 Hope
is not, and every domain card added is another decision to make here.

The shape of a PC's turn comes straight from the spotlight rules: only a roll
can pass the spotlight to the GM, so a PC may take any number of actions that
don't require a roll and then finishes with exactly one that does. That's why
`take_pc_turn` is written as "resolve the free actions, then commit to a roll"
rather than "pick an action".

Priority order for a PC, most preferred first:

  1. Drink a consumable, if hurt or nearly out of Stress and carrying one.
  2. Use a Hope feature, if affordable and worth it.
  3. Use a class feature, if worth it.
  4. Help an ally, or spend Hope on an Experience, if Hope is plentiful.
  5. Attack.

Steps (2) and (3) aren't a list of features here: anything that needs no roll -
a Hope feature, a class feature, a domain card - is reached through the single
`use_free_abilities` call, and decides for itself whether it's worth using.
Helping an ally, the other half of (4), still doesn't exist. Each entry carries
its own "does this make sense now?" test; the ordering here is the only global
policy.

Note that domain cards are NOT absent from a fight just because they're absent
from that list. The two implemented so far are damage responses rather than turn
actions - nothing chooses to use them, they fire when damage arrives - so they
hook in where damage is resolved instead. Every card lives in domain_cards/, and
this module reaches them through exactly one generic call (`_shield`); no card is
named here, and none ever should be. Cards that really are turn actions will join
the priority order above through a dispatch call of their own.
"""

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.results import AttackResult
from combat.state import FightState
import random

from content import (
    action_options,
    apply_on_hit,
    find_shielder,
    hope_die_for,
    is_immune_to,
    total_damage_bonus,
    total_roll_bonus,
    use_free_abilities,
)
from content.conditions import VULNERABLE
from content.names import canonical
from content.rolls import clear_experience_utilised, note_experience_utilised
from dice.common import AdvantageState
from items.registry import find_consumable, find_weapon
from items.weapons import attack_with

# A PC drinks at this much unmarked HP or less. Two is the point where the next
# solid hit is plausibly the last one.
LOW_HP_UNMARKED = 2

# Spending Hope on an Experience is the cheapest use of a big Hope pool, but
# Hope is also what the unimplemented features want, so the floor is set high
# enough that spending it never starves them once they exist.
EXPERIENCE_HOPE_FLOOR = 5

# Consumables the policy knows how to want, by what they clear, and by the name
# a character sheet writes them under - held canonically, so a sheet's
# capitalisation can't stop a PC drinking. Explicit rather than inferred: the
# registry maps a name to a callable, but nothing about that callable says what
# it does.
HEALING_CONSUMABLES = frozenset({canonical("Minor Healing Potion")})
STAMINA_CONSUMABLES = frozenset({canonical("Minor Stamina Potion")})

# A PC drinks a stamina potion at this many free Stress slots or fewer. Marking
# the last Stress makes them Vulnerable - Advantage on every roll against them -
# and a PC with no spare slot also can't pay for the cards that cost one, so the
# potion buys back both at once.
LOW_STRESS_SLOTS = 1

# The spotlight budget - see SIMULATION-RULES.md. Consumables sit outside it,
# and riders and damage responses don't spend from it either, since neither is
# an action the PC chose to take.
FREE_BUDGET_BEFORE_A_ROLL = 1
FREE_BUDGET_ALONE = 2


def choose_pc_target(state: FightState) -> Adversary | None:
    """Which adversary the party attacks: the one closest to going down.

    Focus fire. It's what a party actually does, and it's the choice that
    matters most for balance - every adversary removed early is a whole
    activation the GM never gets - so modelling anything softer would flatter
    the encounter. Ties go to the one listed first, which keeps a fight
    reproducible under a fixed seed.
    """
    living = state.living_adversaries
    if not living:
        return None
    return max(living, key=lambda adversary: adversary.hp_marked)


def choose_adversary_target(
    adversary: Adversary, state: FightState
) -> PlayerCharacter | None:
    """Which PC an adversary swings at, following the fiction.

    Whoever hit this adversary last, failing that whoever last hit anything on
    the GM's side, failing that anyone. An adversary hitting back at the PC
    who just cut it is the ordinary way a fight reads at the table, and it
    keeps attention on whoever is actually engaging.

    Unconscious PCs are skipped at every step: per the SRD they can't be
    targeted at all.
    """
    standing = state.conscious_party
    if not standing:
        return None

    remembered = state.last_attacker_of.get(id(adversary))
    if remembered is not None and remembered.is_conscious:
        return remembered

    if state.last_pc_to_attack is not None and state.last_pc_to_attack.is_conscious:
        return state.last_pc_to_attack

    return standing[0]


def _shield(target: PlayerCharacter, state: FightState) -> PlayerCharacter:
    """Let a domain card move this attack onto a different PC.

    Whether any card does, which one, and whether it's a good idea are all
    decided inside domain_cards/ - this asks once and reports the answer. It
    stays this size however many cards get written; see
    domain_cards/registry.py for why that's the rule.
    """
    interception = find_shielder(target, state.conscious_party)
    if interception is None:
        return target

    state.note(
        f"{interception.shielder.name} steps in front of {target.name} "
        f"({interception.card})"
    )
    return interception.shielder


def take_pc_turn(pc: PlayerCharacter, state: FightState) -> AttackResult | None:
    """Hold the spotlight: everything that needs no roll, then the roll itself.

    Returns the roll that closed it, or None if there was nothing left to
    attack (which only happens if the fight is already over).
    """
    target = choose_pc_target(state)
    _use_free_actions(pc, state, roll_to_follow=target is not None)

    if target is None:
        return None
    return _make_the_roll(pc, target, state)


def _use_free_actions(
    pc: PlayerCharacter, state: FightState, roll_to_follow: bool
) -> None:
    """Everything a PC does that needs no roll, capped by the spotlight budget.

    Nothing here can pass the spotlight - only a roll does that - so without a
    cap a PC would fire every free ability they could afford, every spotlight.
    The budget standing in for a player who doesn't hog the spotlight is in
    SIMULATION-RULES.md: consumables are free, then either two no-roll actions,
    or one alongside the roll that ends the spotlight.
    """
    # Consumables are outside the budget, so wanting both doesn't cost an action.
    if _should_heal(pc):
        _drink(pc, state, HEALING_CONSUMABLES, "HP")
    if _should_clear_stress(pc):
        _drink(pc, state, STAMINA_CONSUMABLES, "Stress")

    budget = FREE_BUDGET_BEFORE_A_ROLL if roll_to_follow else FREE_BUDGET_ALONE
    for name in use_free_abilities(pc, state, budget):
        state.note(f"{pc.name} uses {name}")


def _should_heal(pc: PlayerCharacter) -> bool:
    return pc.hp_unmarked <= LOW_HP_UNMARKED and bool(
        _find_item(pc, HEALING_CONSUMABLES)
    )


def _should_clear_stress(pc: PlayerCharacter) -> bool:
    """Whether to drink something that clears Stress.

    SIMULATION RULE - policy. Held until the PC is nearly out of Stress rather
    than drunk on the first mark, because Stress is only worth clearing once
    there's a cost to being out of it - going Vulnerable, or being unable to pay
    for a card. Drinking early would waste a 1d4 on slots that weren't scarce.
    """
    free_slots = pc.stress_max - pc.stress_marked
    return free_slots <= LOW_STRESS_SLOTS and bool(_find_item(pc, STAMINA_CONSUMABLES))


def _find_item(pc: PlayerCharacter, names: frozenset[str]) -> dict | None:
    """The first consumable of any of `names` the PC still has one of, if any."""
    for entry in pc.consumables:
        if canonical(entry["name"]) in names and entry.get("quantity", 0) > 0:
            return entry
    return None


def _drink(
    pc: PlayerCharacter, state: FightState, names: frozenset[str], clears: str
) -> None:
    """Use one consumable from `names`. `clears` is only for the play-by-play."""
    entry = _find_item(pc, names)
    if entry is None:
        return
    entry["quantity"] -= 1
    cleared = find_consumable(entry["name"])(pc)
    state.note(f"{pc.name} drinks a {entry['name']}, clearing {cleared} {clears}")


def _experience_bonus(pc: PlayerCharacter, state: FightState) -> int:
    """Spend 1 Hope on the PC's best Experience, if Hope is plentiful.

    Returns the bonus to add to the attack roll, or 0 if none was spent. Which
    Experience applies is a fiction call a simulator can't make, so this
    assumes one always does - an optimistic assumption, and the reason the Hope
    floor is set high rather than spending down to the last point.
    """
    if pc.hope_marked < EXPERIENCE_HOPE_FLOOR or not pc.experiences:
        return 0
    bonus = max(experience["modifier"] for experience in pc.experiences)
    pc.spend_hope(1)
    # Recorded generically, for content that triggers on a roll having utilised
    # an Experience. Nothing here knows which content that is.
    note_experience_utilised(pc, state)
    state.note(f"{pc.name} spends a Hope on an Experience (+{bonus})")
    return bonus


def _make_the_roll(
    pc: PlayerCharacter, target: Adversary, state: FightState
) -> AttackResult:
    """The one roll that can pass the spotlight, with its aftermath applied.

    A weapon attack is not privileged here - it's the fallback. Content that
    makes an action roll of its own gets first refusal, and declines by
    returning None. Nothing in this function knows what any of that content is.
    """
    # A new roll, so whatever the last one utilised is forgotten. Set before the
    # options are offered because it's the option that chooses to pay for an
    # Experience, and only the one that takes the roll ever does.
    clear_experience_utilised(pc, state)

    def swing_the_weapon(attacker, at, fight):
        """The weapon as one option among the rest. It never declines.

        The Experience is only paid for here, once the weapon is definitely
        taking the roll - content that makes its own roll doesn't receive the
        bonus, so spending the Hope before choosing would burn it for nothing.

        The weapon is a record now rather than a callable, so the shared attack
        shape takes it as an argument. What the weapon *does* beyond its numbers
        is its own features, which items/weapons.py dispatches scoped to the
        weapon - nothing here knows any of them.
        """
        return attack_with(
            attacker,
            find_weapon(attacker.primary_weapon),
            at,
            AdvantageState.NONE,
            _experience_bonus(attacker, fight) + total_roll_bonus(attacker, at, fight),
            total_damage_bonus(attacker, at, fight),
            hope_die_for(attacker, fight),
            fight,
        )

    # The weapon is shuffled in among the cards rather than being a fallback:
    # a loadout is unordered, and swinging is a real choice, not a last resort.
    options = action_options(pc) + [swing_the_weapon]
    random.shuffle(options)

    result = None
    for option in options:
        result = option(pc, target, state)
        if result is not None:
            break

    if result.damage_roll is not None:
        apply_on_hit(pc, target, result, state)

    state.last_attacker_of[id(target)] = pc
    state.last_pc_to_attack = pc

    if result.damage_roll is None:
        state.note(f"{pc.name} misses {target.name} ({result.attack_roll})")
    else:
        state.note(
            f"{pc.name} hits {target.name} for {result.damage_roll.total} "
            f"({target.hp_marked}/{target.hp_max} HP marked)"
        )
        if target.is_defeated:
            state.note(f"{target.name} is defeated")
    return result


def take_adversary_turn(adversary: Adversary, state: FightState) -> AttackResult | None:
    """Spotlight one adversary: pick a PC and swing at them.

    A Vulnerable PC (all Stress marked) is attacked with Advantage, per the
    SRD's condition - unless something the PC carries turns the condition off,
    which is asked generically rather than by name. Adversary Fear features
    aren't implemented, so an activation is always a standard attack for now.

    The fight is handed to the attack so it reaches the target's damage
    responses: whether one applies can depend on state that only exists for the
    length of this fight.
    """
    target = choose_adversary_target(adversary, state)
    if target is None:
        return None

    target = _shield(target, state)

    vulnerable = target.is_vulnerable and not is_immune_to(target, VULNERABLE, state)
    advantage = AdvantageState.ADVANTAGE if vulnerable else AdvantageState.NONE
    result = adversary.attack(target, advantage, state)

    if result.damage_roll is None:
        state.note(f"{adversary.name} misses {target.name} ({result.attack_roll})")
    else:
        state.note(
            f"{adversary.name} hits {target.name} for {result.damage_roll.total} "
            f"({target.hp_marked}/{target.hp_max} HP marked)"
        )
        if not target.is_conscious:
            state.note(f"{target.name} avoids death and drops unconscious")
    return result
