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

  1. Heal, if hurt and carrying something that heals.
  2. Use a Hope feature, if affordable and worth it.
  3. Use a class feature, if worth it.
  4. Help an ally, or spend Hope on an Experience, if Hope is plentiful.
  5. Attack.

Only (1), (4)'s Experience half, and (5) exist yet - the Guardian's features
and domain cards aren't implemented, so their steps are marked and skipped
rather than faked. Each entry carries its own "does this make sense now?"
test; the ordering here is the only global policy.
"""

from adversaries.adversary import Adversary
from characters.player_character import PlayerCharacter
from combat.results import AttackResult
from combat.state import FightState
from dice.common import AdvantageState
from items.registry import find_consumable, find_weapon

# A PC drinks at this much HP left or less. Two is the point where the next
# solid hit is plausibly the last one.
LOW_HP_REMAINING = 2

# Spending Hope on an Experience is the cheapest use of a big Hope pool, but
# Hope is also what the unimplemented features want, so the floor is set high
# enough that spending it never starves them once they exist.
EXPERIENCE_HOPE_FLOOR = 5

# Consumables that clear HP, by the name a character sheet writes them under.
# Explicit rather than inferred: the registry maps a name to a callable, but
# nothing about that callable says whether it heals.
HEALING_CONSUMABLES = frozenset({"Minor Healing Potion"})


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


def take_pc_turn(pc: PlayerCharacter, state: FightState) -> AttackResult | None:
    """Run one PC's turn: free actions first, then the roll that ends it.

    Returns the attack that closed the turn, or None if there was nothing left
    to attack (which only happens if the fight is already over).
    """
    _use_free_actions(pc, state)

    target = choose_pc_target(state)
    if target is None:
        return None
    return _attack(pc, target, state)


def _use_free_actions(pc: PlayerCharacter, state: FightState) -> None:
    """Everything a PC does before committing to a roll.

    None of these pass the spotlight, so a PC can stack as many as apply.
    """
    if _should_heal(pc):
        _heal(pc, state)

    # Step 2 (Hope feature) and step 3 (class feature) go here once the
    # Guardian's features exist. They're free actions or Stress-costed ones,
    # not rolls, so they belong on this side of the turn.


def _should_heal(pc: PlayerCharacter) -> bool:
    return pc.hp_remaining <= LOW_HP_REMAINING and _find_healing_item(pc) is not None


def _find_healing_item(pc: PlayerCharacter) -> dict | None:
    """The first healing consumable the PC still has one of, if any."""
    for entry in pc.consumables:
        if entry["name"] in HEALING_CONSUMABLES and entry.get("quantity", 0) > 0:
            return entry
    return None


def _heal(pc: PlayerCharacter, state: FightState) -> None:
    entry = _find_healing_item(pc)
    if entry is None:
        return
    entry["quantity"] -= 1
    cleared = find_consumable(entry["name"])(pc)
    state.note(f"{pc.name} drinks a {entry['name']}, clearing {cleared} HP")


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
    state.note(f"{pc.name} spends a Hope on an Experience (+{bonus})")
    return bonus


def _attack(pc: PlayerCharacter, target: Adversary, state: FightState) -> AttackResult:
    """The roll that ends a PC's turn, with its aftermath applied."""
    attack = find_weapon(pc.primary_weapon)
    result = attack(pc, target, AdvantageState.NONE, _experience_bonus(pc, state))

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
    SRD's condition. Adversary Fear features aren't implemented, so an
    activation is always a standard attack for now.
    """
    target = choose_adversary_target(adversary, state)
    if target is None:
        return None

    advantage = (
        AdvantageState.ADVANTAGE if target.is_vulnerable else AdvantageState.NONE
    )
    result = adversary.attack(target, advantage)

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
