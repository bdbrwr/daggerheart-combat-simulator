"""Class features and Hope features.

Registered under the name a character sheet writes in its `class` field, because
that's what a lookup has to be keyed on - a sheet says "Guardian", not "Frontline
Tank". A class carries several features under that one name, which is the same
shape a Grimoire has, so it uses the same helper.

Feature text is paraphrased in each docstring rather than quoted in full; the
verbatim wording is on the SRD site.

Nothing here is dismissed as having no combat effect. That's a judgement about
the game and it's the user's to make, so anything not ruled on and not
implemented stays `unimplemented` and says so in the coverage report.
"""

import random

from content.conditions import RESTRAINED, VULNERABLE
from content.grimoire import FeatureSet
from content.registry import (
    Fight,
    Holder,
    damage_bonus,
    immunity,
    no_combat_effect,
    on_hit,
    on_roll,
    severity_response,
)

# Every Hope feature in the game costs 3 Hope.
HOPE_FEATURE_COST = 3

GUARDIAN = FeatureSet("Guardian")


@GUARDIAN.free("Frontline Tank")
def frontline_tank(guardian: Holder, fight: Fight) -> bool:
    """Guardian's Hope feature. Spend 3 Hope to clear 2 Armor Slots.

    Worth it once at least two slots are marked - clearing one slot for three
    Hope is a poor trade, and Armor Slots are only worth anything while there's
    damage still to come.

    SIMULATION RULE - policy. Waits for two marked slots rather than spending on
    the first. The rules let a Guardian burn it whenever they like; a knob.
    """
    if not guardian.can_spend_hope(HOPE_FEATURE_COST):
        return False
    if guardian.armor_marked < 2:
        return False

    guardian.spend_hope(HOPE_FEATURE_COST)
    guardian.clear_armor_slot(2)
    fight.note(f"{guardian.name} shrugs it off (Frontline Tank: 2 Armor Slots cleared)")
    return True


# --- Unstoppable -------------------------------------------------------------
#
# The Guardian's once-per-long-rest class feature, and the first content whose
# effect is a *state* the holder is in rather than a single moment: it changes
# damage taken, damage dealt, and what conditions can land, all at once, and for
# as long as it lasts. That's why it registers on four hooks under the one name
# a sheet writes - "Guardian" - rather than being a single function.
#
# The die's current value is the whole of its state, so it's kept where per-fight
# state belongs: a token on the FightState, keyed by holder and name. Nothing has
# to clean it up when the fight ends, which is exactly what "or when the scene
# ends, remove the die" asks for.

UNSTOPPABLE = "Unstoppable"

# The die is a d4 until level 5, then a d6. Its *value* starts at 1 and climbs;
# the size is only ever the point at which it falls off.
UNSTOPPABLE_D6_FROM_LEVEL = 5
UNSTOPPABLE_DIE_SMALL = 4
UNSTOPPABLE_DIE_LARGE = 6

# How much punishment the Guardian takes before turning it on. See the policy
# note on `unstoppable` - this is a knob, not a rule.
UNSTOPPABLE_HP_MARKED_BEFORE_USE = 1


def _unstoppable_die_size(guardian: Holder) -> int:
    """The maximum value this Guardian's Unstoppable Die can hold."""
    if guardian.level >= UNSTOPPABLE_D6_FROM_LEVEL:
        return UNSTOPPABLE_DIE_LARGE
    return UNSTOPPABLE_DIE_SMALL


def _unstoppable_value(guardian: Holder, fight: Fight | None) -> int:
    """The die's current value, or 0 when it isn't on the sheet at all.

    0 doubles as "not Unstoppable", which is sound because the die is placed
    showing 1 - a value of zero is never a state the feature can be in.
    """
    if fight is None:
        return 0
    return fight.token_count(guardian, UNSTOPPABLE)


@GUARDIAN.free(UNSTOPPABLE)
def unstoppable(guardian: Holder, fight: Fight) -> bool:
    """Guardian's class feature. Once per long rest, become Unstoppable.

    SRD: place the Unstoppable Die with 1 facing up (a d4, or a d6 from level
    5). While Unstoppable you reduce the severity of physical damage by one
    threshold, add the die's current value to your damage rolls, and can't be
    Restrained or Vulnerable. After a damage roll of yours marks 1 or more HP,
    the die goes up by one; when it would pass its maximum, or when the scene
    ends, it comes off and you drop out.

    No roll is involved, so it's a free ability: it can't pass the spotlight,
    but it does spend from the spotlight budget.

    SIMULATION RULE - policy. Turned on once the Guardian has actually been hit
    (1 HP marked) rather than on the first spotlight of the fight. The rules let
    a player flip it whenever they like, and the trade is real: going early gets
    the damage bonus for longer, while going late means the damage reduction is
    still running when the fight is at its most dangerous. Waiting for a mark
    also stops it being spent on a fight the party was never going to lose.
    """
    if _unstoppable_value(guardian, fight):
        return False
    if guardian.hp_marked < UNSTOPPABLE_HP_MARKED_BEFORE_USE:
        return False
    if not fight.living_adversaries:
        return False

    # Claimed last: an ability asked whether it wants to fire must not spend a
    # per-rest use unless it commits (see SIMULATION-RULES.md).
    if not fight.use_once_per_rest(guardian, UNSTOPPABLE, long=True):
        return False

    fight.add_token(guardian, UNSTOPPABLE, cap=_unstoppable_die_size(guardian))
    fight.note(f"{guardian.name} becomes Unstoppable (die at 1)")
    return True


@severity_response(
    "Guardian",
    unmodelled=[
        "Unstoppable: the physical-damage restriction - damage types aren't "
        "tracked anywhere, so this softens magic damage too",
    ],
)
def unstoppable_reduces_severity(
    guardian: Holder, amount: int, hp_to_mark: int, fight=None
) -> int:
    """One threshold less severe: Severe to Major, Major to Minor, Minor to None.

    Each threshold is worth exactly one HP, so a step down the ladder is one HP
    fewer marked, floored at zero - which is what "Minor to None" means.

    Unlike Get Back Up this costs nothing and isn't a choice, so there's no
    policy here: while the die is on the sheet, it always applies.
    """
    if not _unstoppable_value(guardian, fight):
        return hp_to_mark
    return max(hp_to_mark - 1, 0)


@damage_bonus("Guardian")
def unstoppable_adds_damage(guardian: Holder, target, fight: Fight) -> int:
    """Add the die's current value to the damage roll.

    Applied before the target's thresholds are consulted, like every damage
    bonus, so a growing die can tip a hit into marking another HP rather than
    only raising the number printed.
    """
    return _unstoppable_value(guardian, fight)


@on_hit("Guardian")
def unstoppable_grows(guardian: Holder, target, result, fight: Fight) -> None:
    """Tick the die up after a damage roll that marked 1 or more HP.

    The SRD's trigger is HP *marked*, not damage dealt: a hit the target's armor
    swallowed entirely doesn't advance it. That distinction is why an attack
    reports `hp_marked` alongside its damage roll.

    Rolling past the maximum is what ends it - so a Guardian who keeps landing
    hits drops out of Unstoppable sooner, which is the feature's own clock.
    """
    if not _unstoppable_value(guardian, fight):
        return
    if not result.hp_marked:
        return

    if fight.add_token(guardian, UNSTOPPABLE, cap=_unstoppable_die_size(guardian)):
        fight.note(
            f"{guardian.name}'s Unstoppable Die rises to "
            f"{fight.token_count(guardian, UNSTOPPABLE)}"
        )
        return

    fight.spend_tokens(guardian, UNSTOPPABLE, _unstoppable_value(guardian, fight))
    fight.note(f"{guardian.name} is no longer Unstoppable (the die ran out)")


@immunity(
    "Guardian",
    unmodelled=[
        "Unstoppable: immunity to Restrained, which is real but inert - no "
        "condition except Vulnerable is tracked at all",
    ],
)
def unstoppable_immunities(guardian: Holder, condition: str, fight: Fight) -> bool:
    """While Unstoppable, the Guardian can't be Restrained or Vulnerable.

    Vulnerable is the one that bites: it hands every adversary Advantage on
    every roll against the PC, and a Guardian at full Stress is exactly the PC
    they want it against. Restrained is answered honestly here even though
    nothing tracks it, so this doesn't quietly become wrong if it ever is.
    """
    if condition not in (VULNERABLE, RESTRAINED):
        return False
    return bool(_unstoppable_value(guardian, fight))


# --- Ranger ------------------------------------------------------------------
#
# Both of the Ranger's features extend an attack that has already landed, so
# they're two halves of one on-hit rider - a hook table takes one function per
# name, and "Ranger" is the one name a sheet writes.

RANGERS_FOCUS = "Ranger's Focus"
RANGERS_FOCUS_COST = 1
HOLD_THEM_OFF_TARGETS = 2

RANGER_GAPS = [
    "Ranger's Focus: ending the Focus to reroll the Duality Dice after a failed "
    "attack - a roll that has resolved can't be re-made here",
    "Ranger's Focus: knowing precisely what direction the Focus is in, which is "
    "positioning and isn't tracked",
    "Ranger's Focus: nothing in the simulator consumes an adversary's Stress "
    "yet, so the Stress this forces is marked and then does nothing. The Hope "
    "is a real cost against a benefit that can't show up in the numbers",
    "Hold Them Off: 'with a weapon' isn't enforced - an on-hit rider can't see "
    "which option produced the attack, so the companion's attack triggers it too",
    "Hold Them Off: 'within range of the attack' - no positions are tracked, so "
    "any two other adversaries can be reached",
]


@on_hit("Ranger", unmodelled=RANGER_GAPS)
def ranger_riders(ranger: Holder, target, result, fight: Fight) -> None:
    """Everything the Ranger adds to an attack that just landed.

    Hold Them Off goes first: it spends the roll that has just happened, and
    whether the Ranger then marks a Focus shouldn't depend on it.
    """
    if result.damage_roll is None:
        return
    _hold_them_off(ranger, target, result, fight)
    _rangers_focus(ranger, target, result, fight)


def _hold_them_off(ranger: Holder, target, result, fight: Fight) -> None:
    """The Ranger's Hope feature. Spend 3 Hope to reuse this roll on two more.

    SRD: spend 3 Hope when you succeed on an attack with a weapon to use that
    same roll against two additional adversaries within range of the attack.

    This is the *reuse a roll* shape, not the roll-against-an-area shape: the
    attack was made against one adversary and the same total is now measured
    against two more Difficulties. The card names its own cap of two, so the
    area rule doesn't apply - that rule exists to stop "everyone in range"
    meaning everyone, and this was never that.

    SIMULATION RULE - interpretation. The same damage roll is applied in full to
    each. Whirlwind says explicitly that additional targets take half damage;
    this card says nothing, so nothing is halved.

    SIMULATION RULE - policy. Three Hope is a lot, so it's only spent when there
    are two others to hit and the roll would actually beat at least one of them.
    A player knows roughly how tough an adversary is by the time they've hit it.
    """
    others = [
        adversary for adversary in fight.living_adversaries if adversary is not target
    ]
    if len(others) < HOLD_THEM_OFF_TARGETS:
        return
    if not ranger.can_spend_hope(HOPE_FEATURE_COST):
        return

    # Most wounded first, the same focus fire that picks a single target - the
    # order the encounter spawned its adversaries in must not decide this.
    reached = sorted(others, key=lambda adversary: adversary.hp_marked, reverse=True)[
        :HOLD_THEM_OFF_TARGETS
    ]
    beaten = [
        adversary
        for adversary in reached
        if result.attack_roll.is_critical
        or result.attack_roll.total >= adversary.difficulty
    ]
    if not beaten:
        return

    ranger.spend_hope(HOPE_FEATURE_COST)
    for adversary in beaten:
        adversary.take_damage(result.damage_roll.total)
        fight.note(
            f"{ranger.name} holds them off, catching {adversary.name} "
            f"for {result.damage_roll.total}"
        )


def _rangers_focus(ranger: Holder, target, result, fight: Fight) -> None:
    """The Ranger's class feature. A Hope marks a target; damage then costs them Stress.

    SRD: spend a Hope and make an attack against a target. On a success, deal
    normal damage and temporarily make the target your Focus. Until the feature
    ends or you Focus a different creature, when you deal damage to them they
    must mark a Stress, you know what direction they're in, and a failed attack
    against them can end the Focus to reroll your Duality Dice.

    The Focus is remembered as the `id()` of the adversary, in one token on the
    Ranger. That makes "is this my Focus?" exact and makes Focusing somebody
    else end the old one for free, which is what the card says happens.

    SIMULATION RULE - interpretation. The Hope is spent on an attack that has
    *landed*, rather than declared before the roll as the card reads. That's
    slightly generous - a missed Focus attempt costs the Ranger nothing here -
    but the alternative is deciding to spend before knowing whether the attack
    is even the one that ends the spotlight.
    """
    if fight.token_count(ranger, RANGERS_FOCUS) == id(target):
        target.mark_stress(1)
        fight.note(f"{target.name} is Focused, and marks a Stress")
        return

    if not ranger.can_spend_hope(RANGERS_FOCUS_COST):
        return

    ranger.spend_hope(RANGERS_FOCUS_COST)
    fight.set_token(ranger, RANGERS_FOCUS, id(target))
    fight.note(f"{ranger.name} makes {target.name} their Focus")


# --- Wizard ------------------------------------------------------------------

STRANGE_PATTERNS = "Strange Patterns"

# A Duality Die is a d12, so the number the Wizard watches for is 1-12. Zero is
# never a face, which is what lets an unset token mean "not chosen yet".
DUALITY_DIE_FACES = 12

WIZARD_GAPS = [
    "Not This Time (the Wizard's Hope feature): spend 3 Hope to force an "
    "adversary within Far range to reroll an attack or damage roll - nothing "
    "can force a reroll yet",
    "Prestidigitation, ruled as having no combat effect and declared as such "
    "under its own name",
    "Strange Patterns: changing the number on a long rest. It's drawn fresh for "
    "each fight instead, which comes to the same thing across a run of them",
]


@on_roll("Wizard", unmodelled=WIZARD_GAPS)
def strange_patterns(wizard: Holder, roll, fight: Fight) -> None:
    """Wizard class feature. Watch for one number on either Duality Die.

    SRD: choose a number between 1 and 12. When you roll that number on a
    Duality Die, gain a Hope or clear a Stress.

    Either die counts - the card says "a Duality Die", not the Hope Die - which
    makes this worth about a sixth of every roll.

    SIMULATION RULE - interpretation. A roll showing the number on *both* dice
    fires once, not twice. The card is written as a trigger on the roll rather
    than on each die, and a doubles roll is already a critical.

    SIMULATION RULE - policy. Clears a Stress when any is marked, otherwise
    gains a Hope. Stress is the scarcer resource and running out of it hands
    every adversary Advantage; Hope, by contrast, is spent on things the PC
    chooses to do. A knob.
    """
    watched = _watched_number(wizard, fight)
    dice = (getattr(roll, "hope_die_result", None), getattr(roll, "fear_die_result", None))
    if watched not in dice:
        return

    if wizard.stress_marked:
        wizard.clear_stress(1)
        fight.note(f"{wizard.name} sees the pattern in a {watched}, and clears a Stress")
    else:
        wizard.gain_hope(1)
        fight.note(f"{wizard.name} sees the pattern in a {watched}, and gains a Hope")


def _watched_number(wizard: Holder, fight: Fight) -> int:
    """The number this Wizard is watching for, drawn at random the first time.

    The choice is the player's and carries no information a simulator could use,
    so it's randomised rather than written on the character sheet - every number
    is as good as every other, and drawing it per fight keeps the sheet clean.
    """
    watched = fight.token_count(wizard, STRANGE_PATTERNS)
    if watched:
        return watched

    watched = random.randint(1, DUALITY_DIE_FACES)
    fight.set_token(wizard, STRANGE_PATTERNS, watched)
    fight.note(f"{wizard.name} is watching for {watched}s")
    return watched


# Dismissals are the user's call, not the assistant's. This one is theirs.

no_combat_effect(
    "Prestidigitation",
    "Harmless subtle magic - a spark, a scent, a moved trinket. Ruled as having "
    "no effect on the combat simulation.",
)
