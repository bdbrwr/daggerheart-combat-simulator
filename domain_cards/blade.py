"""Blade domain cards.

One module per domain, named as the SRD names it, holding every implemented card
from that domain. A card's effect and the decision about whether to use it both
live here - nothing outside this package should ever need editing to add one.

Card text is paraphrased in each docstring rather than quoted in full, so a
mismatch between the code and the rule is easy to spot while debugging. The
verbatim text is in .reference/abilities.json, checked against the printed page
(SRD p. 121) - which also settled the batch 1 cards below, ported before the
printed-page check became part of the process.

Cards assessed as belonging outside a fight are declared at the bottom, so that
"used between encounters" never looks like "nobody has got to it yet" - and, just
as importantly, never looks like a dismissal either.

Level 6 gives Blade the domain's first card that reaches a **death move** on its
own holder - Splendor's Life Ward is cast on somebody else - and, in Rage Up, the
first card anywhere whose cost is paid *before* the roll it pays for.

Level 7's **Glancing Blow** is the first card anywhere that pays out on the
holder's *own* attack failing. Every other card keyed on a miss - Redirect, Rapid
Riposte - answers a miss made against its holder, which is a different hook
pointed the other way across the swing.
"""

import random

from content.aoe import Range, targets_reached
from content.registry import (
    DamagePool,
    Fight,
    Holder,
    adjust_damage_pool,
    ally_damage_reduction,
    attack_advantage,
    attack_failed,
    damage_bonus,
    damage_die_maximum,
    damage_die_reroll,
    dealt_damage_type,
    death_move_ward,
    extra_damage,
    no_combat_effect,
    on_hit,
    out_of_combat_ability,
    roll_bonus,
    severity_response,
)
from dice.common import AdvantageState
from dice.damage import DiceGroup, roll_damage
from items.registry import find_weapon

# Not Good Enough rerolls any die showing this or less.
NOT_GOOD_ENOUGH_CEILING = 2

SCRAMBLE = "Scramble"
VERSATILE_FIGHTER = "Versatile Fighter"
DEADLY_FOCUS = "Deadly Focus"
CHAMPIONS_EDGE = "Champion's Edge"

# "Spend up to 3 Hope... you can't choose the same option more than once", and the
# card prints exactly three options - so this is the printed cap and the length of
# the list at once. Kept as a number so the page and the code read alike.
CHAMPIONS_EDGE_HOPE = 3

# Which adversary the focus is fixed on, held as that adversary's `id()` - the
# same way Ranger's Focus remembers its mark. Zero means the focus is over, which
# a bare "is there a token?" could not tell apart from never having declared one;
# the per-rest use is what stops it being declared twice.
FOCUSED_ON = "Deadly Focus target"


@severity_response("Get Back Up")
def get_back_up(
    character: Holder, amount: int, hp_to_mark: int, fight=None, damage_type=None
) -> int:
    """Get Back Up (Blade, level 1). Returns the HP the hit should now mark.

    SRD: when you take Severe damage, you can mark a Stress to reduce the
    severity by one threshold.

    `damage_type` is ignored: the card names no type, so it answers for both.

    SIMULATION RULE - rules interpretation. This triggers on the damage *amount*
    clearing the Severe threshold rather than on the HP the hit would end up
    marking. That matters when an Armor Slot has already softened it: under this
    reading the hit is still Severe damage - a property of the number rolled -
    so the card still applies and the two reductions stack, taking a Severe hit
    from 3 HP down to 1. The SRD doesn't say either way. Reading it the other
    way (armor first, so the card only fires if the hit is still severe
    afterwards) would make the pair order-dependent for no stated reason.

    The Stress is a voluntary cost, so it goes through spend_stress: per the SRD
    a move requiring Stress simply can't be used when Stress is full, and must
    never fall through to marking HP the way forced Stress does.

    SIMULATION RULE - policy, ruled. Whether the Stress is worth paying is the
    shared last-slot rule (`PlayerCharacter.will_spend_stress`), not a policy of
    this card's own. It used to have one - "always pay if the hit would otherwise
    put the PC down, otherwise only while a spare slot remains" - and the user
    replaced it with the general rule so that every card costing Stress answers
    the same way. The one case that changed: a PC on their last Stress slot with
    3 unmarked HP taking a hit that would mark all 3 now goes down rather than
    paying, because the last slot is held until 2 or fewer are unmarked.
    """
    if amount < character.severe_threshold:
        return hp_to_mark
    if hp_to_mark <= 0:
        return hp_to_mark  # armor already took it to nothing; don't buy nothing
    if not character.will_spend_stress(1):
        return hp_to_mark
    character.spend_stress(1)
    return hp_to_mark - 1


@damage_die_reroll(
    "Not Good Enough",
    unmodelled=[
        "Damage rolled by anything other than a weapon - a card or a subclass "
        "feature that rolls its own dice doesn't consult the reroll hook, so "
        "this reaches weapon swings only",
    ],
)
def not_good_enough(attacker: Holder, sides: int, result: int, fight: Fight) -> bool:
    """Not Good Enough (Blade, level 1). Whether this die gets thrown again.

    SRD: "When you roll your damage dice, you can reroll any 1s or 2s."

    No cost and no limit, so there is no policy to rule on: a reroll of a 1 or a
    2 can only move the total up or leave it where it was, and the simulator
    plays PC content at optimal play. It fires on every damage roll the card can
    reach.

    Each die is offered one fresh throw - see `damage_die_reroll`. A rerolled 2
    that comes up a 1 stays a 1; the card says reroll, not reroll until happy.

    `sides` is unused here, and is in the signature because a rule about dice
    could well be about their size: "reroll any 1s" reads differently on a d4
    than on a d12, and content that wants to care can.
    """
    return result <= NOT_GOOD_ENOUGH_CEILING


@attack_advantage(
    "Reckless",
    unmodelled=[
        "Attacks that aren't a weapon swing - a Grimoire spell or any card that "
        "rolls its own attack passes its own advantage state and never consults "
        "this hook, so Reckless can't be spent on one",
    ],
)
def reckless(attacker: Holder, target, fight: Fight) -> AdvantageState | None:
    """Reckless (Blade, level 2). Advantage on this attack for a Stress.

    SRD: "Mark a Stress to gain advantage on an attack."

    SIMULATION RULE - policy, ruled. Paid whenever the shared last-slot rule
    allows it (`PlayerCharacter.will_spend_stress`): freely while a spare slot
    remains, and the last slot only once the PC is at 2 or fewer unmarked HP.
    That is the general rule for every PC Stress cost rather than anything
    specific to this card.

    So in practice a Reckless PC swings with Advantage from the first spotlight
    and keeps doing it until one slot is left, which is a fast way to spend a
    Stress track - and exactly what the card is for.

    Being asked is the commitment: `items/weapons.py` consults this once,
    immediately before the swing, so the Stress buys a roll that definitely
    happens. A reroll re-makes that roll without asking again.
    """
    if not attacker.will_spend_stress(1):
        return None

    attacker.spend_stress(1)
    if fight is not None:
        fight.note(f"{attacker.name} marks a Stress to attack recklessly")
    return AdvantageState.ADVANTAGE


@on_hit(
    "Whirlwind",
    unmodelled=[
        "'Within Very Close range' - no positions are tracked, so the area "
        "rule in SIMULATION-RULES.md decides how many adversaries are caught",
    ],
)
def whirlwind(attacker: Holder, target, result, fight: Fight) -> None:
    """Whirlwind (Blade, level 1).

    SRD: "When you make a successful attack against a target within Very Close
    range, you can spend a Hope to use the attack against all other targets
    within Very Close range. All additional adversaries you succeed against with
    this ability take half damage."

    SIMULATION RULE - rules interpretation. Once the attack against the primary
    target has succeeded, every additional adversary caught is **hit
    automatically** and takes half damage; the roll is not re-checked against
    each one's Difficulty. "All additional adversaries you succeed against" can
    be read as a per-target check, and was implemented that way at first - but
    the trigger is a single successful attack being *used* against the others,
    and this is the reading the table plays. Half damage rounds down.

    The Hope is only spent when there is somebody else to hit. At Very Close the
    area rule reaches a third of the field in total - held to two unless the
    field is unusually spread out - and the original target is one of them, so
    in a fight with fewer than six adversaries this correctly does nothing and
    costs nothing.

    That reach is **rolled per cast**, not a fixed function of the field: the
    same six adversaries can be bunched or strung out, so how far one Whirlwind
    carries is not how far the next one does. See `content/aoe.py`.
    """
    others = [
        adversary
        for adversary in fight.living_adversaries
        if adversary is not target
    ]
    reach = targets_reached(Range.VERY_CLOSE, len(fight.living_adversaries)) - 1
    if reach <= 0 or not others:
        return

    if not attacker.can_spend_hope(1):
        return
    attacker.spend_hope(1)

    # The same attack landing on somebody else, so the same type: the card adds
    # no damage of its own, it re-uses the swing's. See
    # `PlayerCharacter.weapon_damage_type`.
    splash = result.damage_roll.total // 2
    damage_type = getattr(attacker, "weapon_damage_type", None)
    for adversary in others[:reach]:
        adversary.take_damage(splash, fight, damage_type=damage_type)
        fight.note(f"Whirlwind catches {adversary.name} for {splash}")


@ally_damage_reduction(
    SCRAMBLE,
    unmodelled=[
        "'a creature within Melee range' - the hook that answers this is asked "
        "by `take_damage`, which carries an amount and a type and no attacker, "
        "so there is no reach to read. Every incoming hit counts as one that "
        "could be scrambled away from",
        "'safely move out of Melee range of the enemy' - movement, and no "
        "positions are tracked. What is modelled is the attack being avoided",
    ],
)
def scramble(
    holder: Holder, target, amount: int, fight: Fight, damage_type=None
) -> int:
    """Scramble (Blade, level 3). Returns the damage this hit should lose.

    SRD: "Once per rest, when a creature within Melee range would deal damage to
    you, you can avoid the attack and safely move out of Melee range of the
    enemy."

    **Avoided outright, not softened.** The whole amount is returned, so the hit
    resolves to nothing: `take_damage` floors at zero and returns before the
    thresholds, which also means no Armor Slot is spent on an attack that never
    landed. That is what "avoid the attack" says, and no other hook can say it -
    an Armor Slot and `severity_response` both work in threshold bands, and the
    smallest thing either can do is take one HP off.

    Registered on the party-wide hook and scoped back to its own holder by the
    `holder is target` check, exactly as Splendor's Reassurance checks
    `holder is not roller`. There is no holder-scoped twin of this hook yet, and
    one card is not a reason to build one.

    SIMULATION RULE - policy, ruled. Spent on the **first hit of the fight**,
    whatever it would have cost. Holding it for a bigger hit was offered and
    declined: a once-per-rest dodge kept back for the perfect moment is a
    once-per-rest dodge that often goes unused, and the first hit is the one a
    player at the table can see coming without knowing what follows.
    """
    if fight is None or holder is not target:
        return 0
    if not fight.use_once_per_rest(holder, SCRAMBLE):
        return 0

    fight.note(f"{holder.name} scrambles clear, avoiding the attack entirely")
    return amount


@damage_die_maximum(
    VERSATILE_FIGHTER,
    unmodelled=[
        "'You can use a different character trait for an equipped weapon' - a "
        "weapon's trait is authored on its catalogue record in items/weapons.json "
        "and is already the trait this character swings it with, the same way a "
        "sheet carries its Evasion resolved. Applying the swap here as well "
        "would count it twice",
        "Damage rolled by anything other than a weapon - a card or a subclass "
        "feature that rolls its own dice doesn't consult this hook, the same gap "
        "Not Good Enough declares",
    ],
)
def versatile_fighter(holder: Holder, sides: int, result: int, fight: Fight) -> bool:
    """Versatile Fighter (Blade, level 3). Whether to buy this die's top face.

    SRD: "You can use a different character trait for an equipped weapon, rather
    than the trait the weapon calls for. When you deal damage, you can mark a
    Stress to use the maximum result of one of your damage dice instead of
    rolling it."

    Only the second clause runs; the first is declared above as already resolved
    in the weapon's catalogue entry.

    **Which die this is has already been decided.** `maximise_damage_dice` offers
    the dice worst-first - furthest from its own top face - and stops at the first
    one claimed, so saying yes here always buys the largest gain the roll has to
    give. A die already showing its maximum is never offered, so the Stress can
    never be spent on no change at all.

    SIMULATION RULE - policy, ruled. Paid whenever the shared last-slot rule
    allows it (`PlayerCharacter.will_spend_stress`): freely while a spare slot
    remains, and the last slot only once the PC is at 2 or fewer unmarked HP.
    That is the general rule for every PC Stress cost, and the same one Reckless
    and Unleash Chaos follow - holding out for a die that would cross a threshold
    band was offered and declined.

    So a Versatile Fighter spends Stress on nearly every landed hit until one
    slot is left, which is fast, and is what the card is for.
    """
    if not holder.will_spend_stress(1):
        return False

    holder.spend_stress(1)
    if fight is not None:
        fight.note(
            f"{holder.name} marks a Stress to force a d{sides} from {result} to {sides}"
        )
    return True


@extra_damage(
    DEADLY_FOCUS,
    unmodelled=[
        "'+1 bonus to your Proficiency' reaches the **weapon** only. A card that "
        "rolls its own Proficiency dice - a Grimoire spell, Forceful Push - reads "
        "`holder.proficiency` directly and never sees this, so the bonus does not "
        "scale a spell. Modelling it properly would mean moving the number on the "
        "sheet, which every reader of a resolved value would then be seeing "
        "changed mid-fight",
        "The extra die sits **outside a weapon's own discard**, since it is added "
        "where `extra_damage` is asked rather than where the pool is shaped. So a "
        "Greatsword's Massive takes the lowest of the weapon's dice and not of "
        "this one - a real Proficiency bonus would be inside that discard",
        "'until the battle ends' - a fight ending is not announced to content, so "
        "the focus simply stops mattering. Nothing carries between fights: a PC "
        "is spawned fresh from their sheet each time",
    ],
)
def deadly_focus(holder: Holder, target, roll, fight: Fight = None) -> list:
    """Deadly Focus (Blade, level 4). One more weapon die, for one adversary.

    SRD: "Once per rest, you can apply all your focus toward a target of your
    choice. Until you attack another creature, you defeat the target, or the
    battle ends, gain a +1 bonus to your Proficiency."

    SIMULATION RULE - policy, ruled. **Declared on the first attack of the
    fight**, against whoever the party is already focusing - which is the most
    wounded adversary, since that is the party's targeting rule. Being a
    once-per-rest bonus that costs nothing, holding it back for a better moment
    would mostly mean not using it; and the party focus-fires anyway, so the
    creature it lands on is the one the fight is being spent on.

    "Until you attack another creature" ends it, and it does not come back: the
    per-rest use has been claimed. Defeating the target is the same clause
    arriving by another route - the party's focus moves to whatever is left, so
    the next attack is against another creature and the focus lapses there.

    SIMULATION RULE - rules interpretation. Both the declaration and the ending
    are read off an attack that **lands**, because that is where this hook is
    asked. A swing that missed neither claims the focus nor breaks it - the same
    reading Parallela and Strategic Approach already get, and the generous half
    of it (a miss against somebody else not costing the focus) is the same shape
    as the forgiving half.
    """
    if fight is None:
        return []

    carried = getattr(holder, "primary_weapon", "")
    if not carried:
        return []

    focused = fight.token_count(holder, FOCUSED_ON)
    if not focused:
        # Never declared, or declared and finished - `use_once_per_rest` is what
        # tells those apart, and it refuses the second time.
        if not fight.use_once_per_rest(holder, DEADLY_FOCUS):
            return []
        fight.set_token(holder, FOCUSED_ON, id(target))
        fight.note(f"{holder.name} fixes all their focus on {target.name}")
    elif focused != id(target):
        fight.set_token(holder, FOCUSED_ON, 0)
        fight.note(f"{holder.name} turns on {target.name}, and their focus breaks")
        return []

    # `discardable=False`, like every die a feature adds to somebody else's roll.
    return [DiceGroup(count=1, sides=find_weapon(carried).damage_die, discardable=False)]


@on_hit(
    CHAMPIONS_EDGE,
    unmodelled=[
        "A critical that deals **no damage** never reaches this hook. `on_hit` is "
        "asked where a landed attack has rolled damage, so a card that crits and "
        "applies a condition instead - Midnight's Shadowbind, Sage's Death Grip - "
        "is an attack the Blade critically succeeded on that this cannot see",
    ],
)
def champions_edge(attacker: Holder, target, result, fight: Fight) -> None:
    """Champion's Edge (Blade, level 5). Up to 3 Hope cashed in on a critical.

    SRD: "When you critically succeed on an attack, you can spend up to 3 Hope and
    choose one of the following options for each Hope spent: you clear a Hit
    Point; you clear an Armor Slot; the target must mark an additional Hit Point.
    You can't choose the same option more than once."

    Three printed options and a cap of three Hope, with no repeats - so the cap is
    the option list, and a Blade with the Hope for it buys every option that is
    open to them.

    SIMULATION RULE - policy, ruled. **Every option that would actually do
    something, up to the Hope available.** Clearing a Hit Point with none marked
    and clearing an Armor Slot with none marked both buy nothing, so neither is
    offered - the standing rule that a benefit computing to zero is not paid for,
    and here it is read off the sheet the player is looking at rather than off a
    statistic. Forcing the target to mark an HP is dropped for the same reason
    once the attack has already finished it off.

    Where the Hope is short of the live options, **the shuffle picks among them**,
    which is the standing default for a choice nobody has ruled on. No Hope floor:
    a critical is rare, and holding Hope back for other cards was offered and
    declined.

    The extra HP is marked directly rather than dealt as damage. The card says the
    target marks a Hit Point, not that it takes damage worth one - so no threshold
    is read, no resistance applies, and nothing that responds to being damaged
    fires. A target this finishes off is still reported defeated, since the loop
    checks after the on-hit riders have run.
    """
    if fight is None or result.attack_roll is None:
        return
    if not result.attack_roll.is_critical:
        return

    def clear_a_hit_point() -> str:
        attacker.clear_hp(1)
        return "clears a Hit Point"

    def clear_an_armor_slot() -> str:
        attacker.clear_armor_slot(1)
        return "clears an Armor Slot"

    def press_the_advantage() -> str:
        target.mark_hp(1)
        return f"forces {target.name} to mark another Hit Point"

    options = []
    if attacker.hp_marked > 0:
        options.append(clear_a_hit_point)
    if attacker.armor_marked > 0:
        options.append(clear_an_armor_slot)
    if not target.is_defeated:
        options.append(press_the_advantage)
    if len(options) > 1:
        random.shuffle(options)

    for take in options[:CHAMPIONS_EDGE_HOPE]:
        if not attacker.can_spend_hope(1):
            break
        attacker.spend_hope(1)
        fight.note(f"{attacker.name}'s critical {take()}")


# --- Battle-Hardened ---------------------------------------------------------

BATTLE_HARDENED = "Battle-Hardened"

BATTLE_HARDENED_HOPE = 1


@death_move_ward(
    BATTLE_HARDENED,
    unmodelled=[
        "HP marked by anything other than **damage** doesn't reach this. "
        "`mark_hp_and_check_death` is handed a fight by `take_damage` and by "
        "nothing else, so a Blade whose last HP is marked by Stress that wouldn't "
        "fit makes their death move with the card unspent. Life Ward has the same "
        "gap for the same reason",
    ],
)
def battle_hardened(holder: Holder, target, fight: Fight) -> bool:
    """Battle-Hardened (Blade, level 6). A Hope buys you out of one death move.

    SRD: "Once per long rest when you would make a Death Move, you can spend a
    Hope to clear a Hit Point instead."

    **Life Ward's shape, turned on its owner.** That card is cast on somebody else
    for 3 Hope and waits on a sigil; this one is carried, costs a single Hope, and
    is spent at the moment it is needed - so the first thing this checks is that
    the PC about to go down is its own holder. The hook is scanned party-wide,
    since a ward generally belongs to another PC, and holder-scoping it here is
    what makes the card personal.

    "Clear a Hit Point instead" is the same clause Life Ward prints: the HP just
    marked comes back off and the PC stays up with one unmarked. Nothing else of
    the death move happens - no unconsciousness, no scar roll, and no entry in the
    `death_moves` tally, because this is asked *before* the move rather than as
    part of it.

    SIMULATION RULE - policy. Nothing to rule on. **Being asked is the
    commitment** - the hook is consulted only when a death move is genuinely
    happening - so there is no moment worth holding a once-per-long-rest use back
    for, and one Hope is not the kind of price that needs a floor. The Premonition
    reading of a cheap once-per-rest.

    Once per **long** rest, so a party running a second encounter without one
    walks in with it already spent - the standing rule for every per-rest resource
    here.
    """
    if fight is None or holder is not target:
        return False
    if not holder.can_spend_hope(BATTLE_HARDENED_HOPE):
        return False
    if not fight.use_once_per_rest(holder, BATTLE_HARDENED, long=True):
        return False

    holder.spend_hope(BATTLE_HARDENED_HOPE)
    target.clear_hp(1)
    fight.note(
        f"{target.name} is too battle-hardened to fall, spending a Hope to stay up"
    )
    return True


# --- Rage Up -----------------------------------------------------------------

RAGE_UP = "Rage Up"

# "You can Rage Up twice per attack" - the printed cap, and the number of Stress
# a swing can cost.
RAGE_UP_USES = 2

# "A bonus to your damage roll equal to twice your Strength."
RAGE_UP_MULTIPLIER = 2


@damage_bonus(
    RAGE_UP,
    unmodelled=[
        "Damage rolled by anything other than a weapon swing. `total_damage_bonus` "
        "is asked where a PC swings - `combat/policy.py` and Bone's Boost - and "
        "the cards that roll Proficiency dice of their own never consult it, so a "
        "Blade raging into a domain card's damage gets nothing. The same gap "
        "Splendor's Voice of Reason declares",
    ],
)
def rage_up(holder: Holder, target, fight: Fight = None) -> int:
    """Rage Up (Blade, level 6). Stress for damage, twice over.

    SRD: "Before you make an attack, you can mark a Stress to gain a bonus to your
    damage roll equal to twice your Strength. You can Rage Up twice per attack."

    A flat add rather than dice, so it belongs on `damage_bonus` - and that hook is
    asked **before the attack roll**, which is exactly where the card puts the
    decision. The consequence is worth naming: the Stress is spent whether or not
    the swing lands, because a Blade raging up has committed before they know. That
    is the card read literally, not a simplification.

    Landing before the target's thresholds is most of what it buys: twice a
    Strength of 3 is +6 on the number the bands are read against, which is a
    different thing from +6 printed after them.

    SIMULATION RULE - policy, ruled. **Twice on every attack, whenever the shared
    last-slot rule allows it** - the standing default for a Stress cost, the same
    one Boost, Brace and Redirect follow. `will_spend_stress` is re-asked between
    the two, so a Blade one slot from the cliff rages up once and stops. Capping it
    at one, and gating the second on a spare slot, were both offered and declined.

    Declines at a Strength of zero or less rather than paying Stress for nothing -
    or, at a negative Strength, for a penalty. The same reading Unleash Chaos takes
    of a card whose whole size is drawn from a trait.
    """
    strength = holder.traits.get("strength", 0)
    if strength <= 0:
        return 0

    paid = 0
    while paid < RAGE_UP_USES and holder.will_spend_stress(1):
        holder.spend_stress(1)
        paid += 1
    if not paid:
        return 0

    bonus = paid * RAGE_UP_MULTIPLIER * strength
    if fight is not None:
        fight.note(
            f"{holder.name} rages up {paid} time{'s' if paid > 1 else ''} "
            f"(+{bonus} damage)"
        )
    return bonus


no_combat_effect(
    "Vitality",
    "Two of - one Stress slot, one Hit Point slot, +2 damage thresholds - gained "
    "permanently when the card is chosen, after which it goes into the vault for "
    "good. All three are values a character sheet carries already resolved, so the "
    "choice is in the numbers before a fight starts and applying it here would "
    "count it twice; the same reason At Ease, Battlemage and Fortified Armor are "
    "declared rather than run. The vaulting makes it plainer still: the card does "
    "not even occupy a loadout slot during the fight it is paying for.",
)

no_combat_effect(
    "Fortified Armor",
    "A +2 bonus to damage thresholds while wearing armor. A character sheet "
    "carries its thresholds already resolved, exactly as it carries Evasion and "
    "Armor Score, so the bonus is in the numbers before a fight starts and "
    "applying it here would count it twice. The same reason the Stalwart's "
    "Unwavering and Bone's Untouchable are declared rather than run. The "
    "condition attached to it - *while you are wearing armor* - is not a "
    "qualifier this party ever fails: every sheet in characters/ names an armor.",
)

# --- Blade-Touched ---------------------------------------------------------------

BLADE_TOUCHED = "Blade-Touched"

BLADE_TOUCHED_ATTACK = 2


@roll_bonus(
    BLADE_TOUCHED,
    unmodelled=[
        "'When 4 or more of the domain cards in your loadout are from the Blade "
        "domain' - the loadout is not counted. The user's ruling is that carrying "
        "the card is taken as proof the condition is met, since a player who takes "
        "it has built for it. Recorded as a simulation rule rather than checked",
        "'+4 bonus to your Severe damage threshold' - a character sheet carries "
        "its damage thresholds **already resolved**, so running the bonus here "
        "would count it twice. The same reason Vitality and Fortified Armor are "
        "declared",
        "'+2 bonus to your **attack** rolls' also reaches a Spellcast Roll that "
        "is not an attack, since `total_roll_bonus` is asked from both the swing "
        "and the cast with nothing to tell them apart. Empty in practice: Blade "
        "prints no Spellcast Roll at any level, and a Blade-Touched loadout has "
        "at most one card from anywhere else",
    ],
)
def blade_touched(holder: Holder, target, fight: Fight = None) -> int:
    """Blade-Touched (Blade, level 7), the clause that isn't already on the sheet.

    SRD: "When 4 or more of the domain cards in your loadout are from the Blade
    domain, gain the following benefits: +2 bonus to your attack rolls; +4 bonus
    to your Severe damage threshold."

    No policy - it costs nothing, has no limit and is simply on. **+2 is the
    largest flat attack bonus any ported card grants**, which is a fact about the
    printed number rather than a claim about what it will do to a fight.
    """
    return BLADE_TOUCHED_ATTACK


# --- Glancing Blow ---------------------------------------------------------------

GLANCING_BLOW = "Glancing Blow"


@attack_failed(
    GLANCING_BLOW,
    unmodelled=[
        "A failed **Spellcast** attack. This hook is asked where a weapon swing "
        "resolves, so a card that rolls its own attack and misses does not reach "
        "it - which suits the card, since what it deals is weapon damage",
        "The play-by-play still reports the swing as a miss. The damage is dealt "
        "outside the `AttackResult` the attack returns, so `combat/policy.py` "
        "notes a miss and this card notes its own hit underneath",
        "'one of your active weapons' - a sheet can carry a secondary weapon and "
        "nothing resolves one (SIMULATION-RULES.md, section 3), so the blow is "
        "always struck with the primary. Rapid Riposte reads the same clause the "
        "same way",
    ],
)
def glancing_blow(holder: Holder, target, roll, fight: Fight = None) -> None:
    """Glancing Blow (Blade, level 7). A miss that still costs the target something.

    SRD: "When you fail an attack, you can mark a Stress to deal weapon damage
    using half your Proficiency."

    **Rapid Riposte's damage, off the opposite trigger.** That card answers an
    attack that failed *against you*; this one answers your own. The pool is built
    the way `items/weapons.py` builds a swing's - Proficiency dice of the weapon's
    size, its modifier, then `adjust_damage_pool` asked holder-wide and again for
    the weapon's own features - so a Greatsword's Massive discards its lowest here
    exactly as it would on a hit.

    What is deliberately **not** asked is `total_damage_bonus` and
    `total_extra_damage`: the first is paid "before you make an attack" and has
    already been spent on the swing that missed, and the second keys on how an
    attack roll came out, which here is badly.

    SIMULATION RULE - rules interpretation, ruled. **Half a Proficiency rounds
    up**, so a Proficiency of 3 rolls two dice and a Proficiency of 1 rolls one.
    The user's rule, and it means the card can never come to no dice at all.

    SIMULATION RULE - policy. Nothing to rule beyond the standing default: it
    fires on every failed swing the shared Stress rule allows, which is the same
    answer Reckless, Versatile Fighter and Rage Up get.
    """
    if fight is None or holder.proficiency <= 0:
        return
    carried = getattr(holder, "primary_weapon", "")
    if not carried:
        return
    if not holder.will_spend_stress(1):
        return

    weapon = find_weapon(carried)
    # Rounded up, per the ruling: `-(-n // 2)` is the floor division the language
    # gives, negated twice.
    dice = -(-holder.proficiency // 2)
    pool = adjust_damage_pool(
        holder,
        weapon,
        DamagePool(
            dice_groups=[DiceGroup(count=dice, sides=weapon.damage_die)],
            drop_lowest=0,
            modifier=weapon.damage_modifier,
        ),
        fight,
    )
    pool = adjust_damage_pool(holder, weapon, pool, fight, names=weapon.named_features)

    holder.spend_stress(1)
    damage = roll_damage(
        dice_groups=pool.dice_groups,
        modifier=pool.modifier,
        drop_lowest=pool.drop_lowest,
    )
    target.take_damage(
        damage.total,
        fight,
        damage_type=dealt_damage_type(holder, target, weapon.damage_type, fight),
    )
    fight.note(
        f"{holder.name}'s miss still glances off {target.name} for {damage.total}"
    )


out_of_combat_ability(
    "A Soldier's Bond",
    "Once per long rest, complimenting someone gives you and them 3 Hope each. "
    "Not a dismissal: 6 Hope across two PCs is a large effect and Hope is fully "
    "tracked here. What the card isn't is a combat move - players don't stop "
    "mid-fight to pay someone a compliment, they do it between encounters. So it "
    "belongs to the sequenced-encounter machinery, which doesn't exist yet, and "
    "is recorded here as work with a home rather than as work nobody has done.",
)
