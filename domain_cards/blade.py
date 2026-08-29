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
"""

import random

from content.aoe import Range, targets_reached
from content.registry import (
    Fight,
    Holder,
    ally_damage_reduction,
    attack_advantage,
    damage_die_maximum,
    damage_die_reroll,
    extra_damage,
    no_combat_effect,
    on_hit,
    out_of_combat_ability,
    severity_response,
)
from dice.common import AdvantageState
from dice.damage import DiceGroup
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

out_of_combat_ability(
    "A Soldier's Bond",
    "Once per long rest, complimenting someone gives you and them 3 Hope each. "
    "Not a dismissal: 6 Hope across two PCs is a large effect and Hope is fully "
    "tracked here. What the card isn't is a combat move - players don't stop "
    "mid-fight to pay someone a compliment, they do it between encounters. So it "
    "belongs to the sequenced-encounter machinery, which doesn't exist yet, and "
    "is recorded here as work with a home rather than as work nobody has done.",
)
