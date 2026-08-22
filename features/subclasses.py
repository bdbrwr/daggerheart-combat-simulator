"""Subclass features.

Registered under the name a character sheet writes in its `subclass` field, so
"Stalwart" is the key even though the features themselves are called Unwavering
and Iron Will. Same registry, same hooks, same three states as everything else.

Feature text is paraphrased in each docstring rather than quoted in full; the
verbatim wording is in `.reference/subclasses.json`.

## Only foundation features are here

A subclass gives its features in three tiers: **foundation** from level 1,
**specialization** from level 5, and **mastery** from level 8. Only the
foundation tier is implemented, because that's the tier the current party
actually has. The others are declared as gaps rather than left silent, so a
level 5 party would show them as missing instead of quietly running without
them.

## Features the sheet has already applied

A feature whose whole effect is a number the character sheet states - damage
thresholds, Evasion, the count of HP or Stress slots, the size of the loadout -
has already been worked into that number by the time a sheet is written. Running
it again here would count it twice. Those are declared `no_combat_effect` at the
bottom of this module, under their own names, so the assessment is recorded
rather than the feature just being absent.

That is the user's ruling, not the assistant's: whether a piece of content can
affect a fight is a judgement about the game and it's theirs to make. Anything
not ruled on and not implemented stays `unimplemented`.
"""

from combat.results import AttackResult
from content.damage_types import DamageType
from content.registry import (
    Fight,
    Holder,
    action,
    apply_on_roll,
    extra_damage,
    hope_die_for,
    no_combat_effect,
    remake_action_roll,
    roll_bonus,
    severity_response,
    total_damage_bonus,
    total_extra_damage,
    total_roll_bonus,
)
from content.rolls import note_experience_utilised
from dice.common import AdvantageState
from dice.damage import DiceGroup, roll_damage
from dice.duality import DualityOutcome, roll_duality

# --- Stalwart (Guardian) -----------------------------------------------------

STALWART_GAPS = [
    "Unrelenting and Partners-in-Arms (specialization, level 5) and Undaunted "
    "and Loyal Protector (mastery, level 8)",
]

# An extra Armor Slot is worth spending on a hit this big or bigger. Below it,
# the slot is worth more later than the single HP is now.
IRON_WILL_WORTH_A_SLOT = 2


@severity_response("Stalwart", unmodelled=STALWART_GAPS)
def iron_will(
    guardian: Holder, amount: int, hp_to_mark: int, fight=None, damage_type=None
) -> int:
    """Stalwart's *Iron Will*. Returns the HP the hit should now mark.

    SRD: when you take physical damage, you can mark an additional Armor Slot to
    reduce the severity.

    "Additional" is the important word: `take_damage` already marks one slot
    against every hit as a matter of simulation policy, and this is a second one
    on top of that. Each slot is worth one threshold, which is one HP.

    **Physical damage only**, as printed, checked first so the slot is never
    even considered against a spell. Untyped damage doesn't qualify: a
    restriction matches only a type that was stated, so the Guardian keeps the
    slot rather than spending it on a hit nobody typed.

    SIMULATION RULE - policy. Slots are the party's durability and there are
    only a few, so this doesn't spend one to save a single HP. It pays when the
    hit would otherwise put the Guardian down, and otherwise only when the hit
    is still marking 2 or more HP after the free slot.
    """
    if damage_type is not DamageType.PHYSICAL:
        return hp_to_mark
    if hp_to_mark <= 0:
        return hp_to_mark
    if guardian.armor_marked >= guardian.armor_max:
        return hp_to_mark

    drops_them = hp_to_mark >= guardian.hp_unmarked
    if not drops_them and hp_to_mark < IRON_WILL_WORTH_A_SLOT:
        return hp_to_mark

    guardian.mark_armor_slot(1)
    return hp_to_mark - 1


# --- School of Knowledge (Wizard) --------------------------------------------

SCHOOL_OF_KNOWLEDGE_GAPS = [
    "Adept: which Experience applies is a fiction call, so the best one is "
    "assumed to apply - the same assumption combat/policy.py already makes",
    "Brilliant and Honed Expertise (mastery, level 8) and Accomplished and "
    "Perfect Recall (specialization, level 5)",
]


@roll_bonus("School of Knowledge", unmodelled=SCHOOL_OF_KNOWLEDGE_GAPS)
def adept(wizard: Holder, target, fight: Fight) -> int:
    """School of Knowledge's *Adept*.

    SRD: when you Utilize an Experience, you can mark a Stress instead of
    spending a Hope. If you do, double your Experience modifier for that roll.

    SIMULATION RULE - policy. The two ways of paying for an Experience are split
    by the Hope floor rather than weighed against each other: `combat/policy.py`
    already spends Hope on an Experience whenever the PC is above the floor, so
    this fires only *below* it, where that path declines. The result is a Wizard
    who uses an Experience on every roll - Hope while they have plenty, Stress
    once they don't - which is the point of the feature, but it does mean the
    doubled modifier is never chosen while Hope is plentiful even though a
    player might.

    Stress is only marked while a spare slot remains: marking the last one hands
    every adversary Advantage on every roll, which outlives the one roll this
    buys. Being asked is the commitment for this hook - the roll follows
    immediately - so the Stress is marked here rather than offered.
    """
    from combat.policy import EXPERIENCE_HOPE_FLOOR

    if not wizard.experiences:
        return 0
    if wizard.hope_marked >= EXPERIENCE_HOPE_FLOOR:
        return 0  # policy is about to pay for it with Hope instead
    if wizard.stress_marked + 1 >= wizard.stress_max:
        return 0
    if not wizard.spend_stress(1):
        return 0

    bonus = max(experience["modifier"] for experience in wizard.experiences) * 2
    # Recorded for content that triggers on having utilised an Experience -
    # paying with Stress is still utilising one, so this route has to say so as
    # much as the Hope route in combat/policy.py does.
    note_experience_utilised(wizard, fight)
    fight.note(f"{wizard.name} marks a Stress to double an Experience (+{bonus})")
    return bonus


# --- Beastbound (Ranger) -----------------------------------------------------
#
# The companion is a second creature, but it never needs a spotlight of its own:
# per the Ranger Companion sheet (SRD p.18) you command it with a Spellcast Roll,
# and that roll *is* the attack. So this is an action the Ranger takes, which is
# why nothing in combat/fight.py changes to support it.

# The companion's damage die at level 1. "Vicious" steps it up (d6 to d8), which
# is a level-up option and so isn't taken here.
COMPANION_DAMAGE_DIE = 6

BEASTBOUND_GAPS = [
    "Companion: its damage is 'physical or magic as the player chose', and no "
    "choice has been ruled - so the companion's bite goes out untyped and no "
    "resistance is ever applied to it. Awaiting a ruling; everything else that "
    "deals damage now states a type",
    "Companion: the companion is never attacked, so its Stress, and dropping "
    "out of the scene when its last Stress is marked, are not modelled. "
    "Nothing targets it because no positioning is tracked - which means this "
    "understates nothing about the party's damage but ignores the companion's "
    "own risk entirely",
    "Companion: the two Companion Experiences (+2 each, bought with a Hope) - "
    "which one applies is a fiction call, and no Hope is spent on them here",
    "Companion: every level-up option (Intelligent, Vicious, Resilient, "
    "Armored, Bonded and the rest) - the companion is run at its level 1 sheet",
    "Companion: the follow-up swing after a success with Hope doesn't spend a "
    "Hope on an Experience, where an ordinary weapon attack would",
    "Expert Training and Battle-Bonded (specialization, level 5) and Advanced "
    "Training and Loyal Friend (mastery, level 8)",
]


@action("Beastbound", unmodelled=BEASTBOUND_GAPS)
def companion(ranger: Holder, target, fight: Fight) -> AttackResult | None:
    """Beastbound's *Companion*, commanded to attack.

    SRD (Ranger Companion sheet): make a Spellcast Roll to command your
    companion to take action. Their damage roll uses *your* Proficiency and
    *their* damage die - a d6 at level 1, Melee range, physical or magic as the
    player chose.

    A sheet that names no `spellcast_trait` declines rather than guessing a
    trait, the same way the Grimoire spells do - content that never fires is a
    visible gap, where content that quietly fires with the wrong trait isn't.

    Note what this is worth: Proficiency d6 with no flat modifier, from a PC who
    also has a weapon. It's rarely the bigger number, and it isn't meant to be -
    the point is that commanding the companion is one of the things a Beastbound
    Ranger can spend their roll on, and the simulator picks at random among the
    options a PC can actually use rather than scoring them.

    SIMULATION RULE - policy. The companion sheet also says: "On a success with
    Hope, if your next action builds on their success, you gain advantage on the
    roll." Whether the next action builds on it is a fiction call, so here it
    always does, and the Ranger takes it **immediately** as a weapon swing with
    Advantage rather than waiting for a later spotlight. See `_press_the_advantage`.
    """
    trait = getattr(ranger, "spellcast_trait", "")
    if not trait or trait not in ranger.traits:
        return None

    # Asked only once the command is going ahead, so nothing is spent toward a
    # roll that isn't being made - and outside the closure, so a reroll doesn't
    # charge for the bonuses twice.
    modifier = ranger.traits[trait] + total_roll_bonus(ranger, target, fight)
    hope_die = hope_die_for(ranger, fight)

    def roll():
        return roll_duality(
            modifier=modifier, difficulty=target.difficulty, hope_die=hope_die
        )

    # Offered to the reroll hook so it reaches the companion's Spellcast Roll too.
    attack_roll = remake_action_roll(ranger, roll(), roll, fight)

    if not attack_roll.is_success:
        fight.note(f"{ranger.name}'s companion misses {target.name}")
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    # "On a success, their damage roll uses your Proficiency and their damage
    # die" - the count is the Ranger's, the die is the companion's.
    damage_roll = roll_damage(
        dice_groups=[DiceGroup(count=ranger.proficiency, sides=COMPANION_DAMAGE_DIE)]
        + total_extra_damage(ranger, target, attack_roll, fight),
        is_critical=attack_roll.is_critical,
    )
    # Untyped, and the only damage left in the simulator that is - the companion
    # sheet says "physical or magic as the player chose" and no choice has been
    # ruled. Declared in BEASTBOUND_GAPS. `fight` is passed either way, so the
    # target's own damage responses can see it.
    marked = target.take_damage(damage_roll.total, fight)
    fight.note(
        f"{ranger.name}'s companion mauls {target.name} for {damage_roll.total}"
    )
    commanded = AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )

    if attack_roll.outcome is not DualityOutcome.HOPE:
        return commanded
    return _press_the_advantage(ranger, target, fight, commanded)


def _press_the_advantage(
    ranger: Holder, target, fight: Fight, commanded: AttackResult
) -> AttackResult:
    """The Ranger's own swing, with Advantage, straight after the companion's hit.

    SIMULATION RULE - policy, and a compression of two spotlights into one. The
    companion sheet grants advantage on your *next* action roll if it builds on
    the companion's success; a success with Hope also keeps the spotlight with
    the party. At a table that usually reads as the Ranger following up
    themselves, but the loop hands the next spotlight to a random PC who hasn't
    acted, so waiting would mean the advantage usually went to nobody. Taking it
    immediately is the chosen simplification. It does mean a Beastbound Ranger
    makes two action rolls in one spotlight, which no other PC can do.

    A critical is deliberately not treated as "with Hope" - it's its own
    outcome, the same reading `face_your_fear` above applies to "with Fear".

    The companion's roll generated Hope that the spotlight loop will never see,
    because only the returned roll reaches it - so it's paid out here. There is
    no matching Fear case to worry about: this is only reached on Hope.
    """
    from items.registry import find_weapon
    from items.weapons import attack_with

    apply_on_roll(ranger, commanded.attack_roll, fight)
    ranger.gain_hope(1)

    if not getattr(ranger, "primary_weapon", ""):
        return commanded

    fight.note(f"{ranger.name} presses the companion's advantage")
    return attack_with(
        ranger,
        find_weapon(ranger.primary_weapon),
        target,
        AdvantageState.ADVANTAGE,
        total_roll_bonus(ranger, target, fight),
        total_damage_bonus(ranger, target, fight),
        hope_die_for(ranger, fight),
        fight,
    )


# --- School of War (Wizard) --------------------------------------------------

# Face Your Fear deals an extra 1d10 at the foundation tier. The specialization
# raises it to 2d10 and the mastery to 3d10, neither of which is implemented -
# hence a constant rather than a bare 1, so the level gate has somewhere to go.
FACE_YOUR_FEAR_DICE = 1
FACE_YOUR_FEAR_DIE = 10

SCHOOL_OF_WAR_GAPS = [
    "Face Your Fear: the extra die is magic where the weapon it rides on may "
    "not be. Damage types are tracked now, but this die joins the weapon's own "
    "damage roll so that it is measured against thresholds once - and one roll "
    "carries one type, which is the weapon's. Against a magic-resistant target "
    "the 1d10 is therefore unresisted where the SRD would halve it",
    "Thrive in Chaos and Have No Fear (mastery, level 8) and Conjure Shield "
    "and Fueled by Fear (specialization, level 5)",
]


@extra_damage("School of War", unmodelled=SCHOOL_OF_WAR_GAPS)
def face_your_fear(wizard: Holder, target, roll, fight=None) -> list[DiceGroup]:
    """School of War's *Face Your Fear*.

    SRD: when you succeed with Fear on an attack roll, you deal an extra 1d10
    magic damage.

    A Fear die that beat the Hope die *and* still cleared the Difficulty is a
    narrow band - roughly one attack in four - so this is a spike rather than a
    steady bonus, and it pays out precisely on the rolls that hand the spotlight
    to the GM. That's the feature working as written: the Wizard's consolation
    for a roll that costs the party tempo.

    A critical is not "with Fear" - it's its own outcome and the two dice
    matched - so it doesn't qualify, and asking for the outcome rather than
    comparing the dice keeps that right for free.

    Returns dice rather than a number so they join the attack's own damage roll,
    where they're counted once against the target's thresholds.

    Marked `discardable=False`: a Massive or Powerful weapon throws away the
    lowest of the dice *it* rolled, and this isn't one of them. So the die is
    rolled alongside the weapon's pool and added to the same total, but the
    discard can't reach it.
    """
    if not roll.is_success:
        return []
    if getattr(roll, "outcome", None) is not DualityOutcome.FEAR:
        return []
    return [
        DiceGroup(
            count=FACE_YOUR_FEAR_DICE, sides=FACE_YOUR_FEAR_DIE, discardable=False
        )
    ]


# --- Already resolved on the character sheet ---------------------------------
#
# The user's ruling: if a feature modifies a value the sheet carries, the sheet's
# number already includes it. Declared here so both still reach the coverage
# report as assessed rather than looking like work nobody has done.

no_combat_effect(
    "Unwavering",
    "Stalwart's permanent +1 to damage thresholds. A character sheet carries "
    "its thresholds already resolved, so this is in those numbers - applying it "
    "again at simulation time would count it twice.",
)

no_combat_effect(
    "Battlemage",
    "School of War's additional Hit Point slot. A sheet states its HP maximum "
    "outright, so the extra slot is already in that number.",
)

no_combat_effect(
    "Prepared",
    "School of Knowledge's additional domain card. The sheet's loadout is "
    "written out in full and already includes it, so there is nothing left for "
    "this to add.",
)
