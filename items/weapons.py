"""Swinging a weapon - the one attack shape every weapon shares.

A weapon used to be a callable per weapon, with its stats baked into the
arguments it passed. It isn't any more: a weapon's numbers are a record in a JSON
catalogue (see catalogue.py) and everything it does beyond those numbers is a
named feature in features/weapons.py. What's left here is the shape itself, which
is the same for all of them - roll the weapon's trait against the target's
Difficulty, and on a hit roll Proficiency dice of the weapon's size.

That change is what makes the 61st weapon free. Under the old arrangement,
Reliable was `attack_bonus=1` and Massive was `discards_lowest=True` - parameters
on shared machinery that existed because of two specific named features, which is
exactly the coupling the content registry exists to prevent. Now this module
knows no weapon and no feature by name; it calls dispatch, twice, and the
features answer for themselves.

## Why a weapon's features are scoped and a holder's are not

Content a character *carries* applies to everything they do, so dispatch scans
`named_features` and this module needn't think about it. A weapon's feature is
different: Reliable is "+1 to attack rolls" **with that weapon**, and letting it
sum holder-wide would silently add it to a Grimoire spell. So the weapon's own
feature names are passed explicitly, and every attack consults both scopes.

Range is recorded on the record and otherwise unused - nothing in the simulator
tracks distance. See SIMULATION-RULES.md.
"""

from typing import Protocol

from combat.results import AttackResult
from content import (
    DamagePool,
    adjust_damage_pool,
    dealt_damage_scaling,
    dealt_damage_type,
    remake_action_roll,
    total_ally_extra_damage,
    total_extra_damage,
    total_roll_bonus,
)
from content.help import help_with_roll
from content.registry import (
    apply_before_attacked,
    apply_on_attacked,
    granted_action_roll_advantage,
    granted_attack_advantage,
    maximise_damage_dice,
    party_attack_is_hobbled,
    reroll_damage_dice,
)
from dice.common import AdvantageState, combined
from dice.damage import DiceGroup, roll_damage
from dice.duality import roll_duality
from items.catalogue import Weapon


class Attacker(Protocol):
    """The slice of a PC a weapon touches.

    A Protocol rather than importing PlayerCharacter: characters/ resolves its
    gear through items/, and the import can't run both ways.
    """

    traits: dict[str, int]
    proficiency: int
    named_features: list[str]


class Target(Protocol):
    """Anything a PC's weapon can attack - an adversary."""

    difficulty: int

    # Scanned for content that punishes being hit, which belongs to whoever was
    # attacked rather than to whoever swung.
    named_features: list[str]

    # Read by nothing here, but a target can carry conditions that change the
    # roll made against it - being Hidden gives it Disadvantage.
    name: str

    def take_damage(
        self, amount: int, fight=None, direct: bool = False, damage_type=None
    ) -> int: ...


def attack_with(
    attacker: Attacker,
    weapon: Weapon,
    target: Target,
    advantage_state: AdvantageState = AdvantageState.NONE,
    bonus: int = 0,
    damage_bonus: int = 0,
    hope_die: int = 12,
    fight=None,
) -> AttackResult:
    """Attack `target` with `weapon`, rolling and applying damage on a hit.

    `bonus` is a flat add to the attack roll from outside the weapon - an
    Experience the PC spent Hope on, mostly - and `damage_bonus` is the same idea
    for damage. Both are parameters rather than something worked out here,
    because whether an Experience or a domain card applies is a decision made by
    the acting character, not by the sword.

    `damage_bonus` is added before the target's thresholds are consulted, so it
    can change how many HP a hit marks and not just the number printed. So is
    everything the two dispatch calls below contribute, for the same reason.
    """
    # Content the *target* carries that interrupts an attack before it is rolled -
    # the Harrier's Fall Back, which counterattacks the moment somebody closes to
    # Melee. Fired first, because "before the attack roll" is the trigger, and it
    # cannot stop what follows: the swing happens either way. Nothing here knows
    # what any of it is.
    apply_before_attacked(target, attacker, weapon, fight)

    # Content the *attacker* carries that grants Advantage on the swing they're
    # making - the Blade card Reckless, which marks a Stress for it. The GM side
    # has asked this of its own standard attack since Cloaked was written; a PC's
    # standard attack is this function, so it asks here. Folded rather than
    # overwriting, so a Reckless PC swinging at something Hidden comes out even.
    #
    # Being asked is the commitment, which is why it is asked once per swing and
    # not per reroll: content here spends its Stress on being consulted.
    advantage_state = combined(
        advantage_state, granted_attack_advantage(attacker, target, fight)
    )

    # And content that grants Advantage on *any* action roll rather than on a
    # standard attack - the Valor card Inevitable, which hands the next roll
    # after a failure an advantage die. A separate hook because a swing is only
    # one of the shapes an action roll takes; see `action_roll_advantage`. Asked
    # here for the same reason its neighbour is, and folded rather than
    # overwriting, so two sources land where the SRD puts them.
    advantage_state = combined(
        advantage_state, granted_action_roll_advantage(attacker, target, fight)
    )

    # A condition can hobble the trait this weapon rolls - the Archer Guard's
    # Hobbling Shot leaves its target with disadvantage on Agility Rolls. Folded
    # in rather than overwriting, so a PC attacking with Advantage and hobbled at
    # once ends up where the SRD puts them: the two cancel.
    if fight is not None and fight.disadvantaged_on(attacker, weapon.trait):
        advantage_state = combined(advantage_state, AdvantageState.DISADVANTAGE)

    # And a condition on the *target* can hobble the roll too: every roll against
    # a Hidden combatant has Disadvantage. The mirror of the Vulnerable check the
    # GM side already makes in `combat/policy.py`, and folded in the same way, so
    # a PC with Advantage swinging at something Hidden comes out even.
    if fight is not None and fight.is_hidden(target):
        advantage_state = combined(advantage_state, AdvantageState.DISADVANTAGE)

    # And content belonging to a *third* adversary can hobble it, keyed on which
    # target was chosen - the Swarm of Rats' In Your Face. Asked generically;
    # nothing here knows what any of it is.
    if party_attack_is_hobbled(attacker, target, weapon, fight):
        advantage_state = combined(advantage_state, AdvantageState.DISADVANTAGE)

    # Worked out once, before the roll, and *outside* the closure below: asking
    # content for a roll bonus is the commitment, so several of them spend Hope
    # or mark Stress on being asked. A reroll re-makes the dice, not the
    # decisions that fed them - evaluating this twice would charge for it twice.
    # An ally spending a Hope to help, which is a party move rather than anything
    # the attacker carries - see `content/help.py`. Asked here, outside the
    # closure, for the reason the modifier is worked out here: being asked is the
    # commitment, and the helper's Hope is spent on being consulted.
    help_offered = help_with_roll(attacker, fight)

    modifier = (
        # Indexed, not `.get(..., 0)`: the catalogue already validated the
        # trait against the six real ones and sheets lowercase their trait
        # keys, so a miss here is a broken sheet and should say so rather
        # than quietly rolling a flat zero.
        attacker.traits[weapon.trait]
        + bonus
        + total_roll_bonus(attacker, target, fight, names=weapon.named_features)
        # Content the *helper* carries - the Bone card Tactician lends one of its
        # own Experiences. A flat add, so it folds in here rather than into the
        # help pool, which resolves to its single best die.
        + help_offered.bonus
    )

    def roll():
        return roll_duality(
            modifier=modifier,
            difficulty=target.difficulty,
            advantage_state=advantage_state,
            hope_die=hope_die,
            help_dice=help_offered.dice,
        )

    # Content that can re-make a resolved roll gets its say before anything
    # reads the result, so a reroll is indistinguishable from having rolled that
    # way first. It re-makes the roll through the same closure, on identical
    # terms.
    attack_roll = remake_action_roll(attacker, roll(), roll, fight)

    if not attack_roll.is_success:
        return AttackResult(attack_roll=attack_roll, damage_roll=None)

    # Content the *character* carries that changes the shape of the pool before
    # the weapon's own features see it - Splendor's Voice of Reason adds a
    # Proficiency die while all its holder's Stress is marked. Asked holder-wide,
    # the same way `total_roll_bonus` is asked twice: once for the holder and
    # once for the weapon.
    #
    # Before the weapon's own features rather than after, because a Proficiency
    # bonus really is one more of the *weapon's* dice - so a Massive discard
    # should see the bumped pool and take the lowest of all of them.
    pool = adjust_damage_pool(
        attacker,
        weapon,
        DamagePool(
            dice_groups=[DiceGroup(count=attacker.proficiency, sides=weapon.damage_die)],
            drop_lowest=0,
            modifier=weapon.damage_modifier,
        ),
        fight,
    )

    # Then the weapon's own features - this is where Massive and Powerful roll
    # their extra die and discard the lowest, and the discard is theirs alone,
    # reaching only the dice the weapon rolled.
    pool = adjust_damage_pool(
        attacker, weapon, pool, fight, names=weapon.named_features
    )

    # Then content the *character* carries that adds dice conditional on how the
    # attack came out. These join the same roll so they're counted once against
    # the target's thresholds - and they sit outside the weapon's discard, since
    # a Greatstaff's Powerful has no business throwing away a Wizard's die.
    dice_groups = list(pool.dice_groups)
    dice_groups += total_extra_damage(attacker, target, attack_roll, fight)

    # And dice another PC's content hangs on the *target* rather than on whoever
    # is swinging - Midnight's Chokehold pays out for anyone who attacks the
    # creature it has hold of. Joins the same roll, so it crosses the target's
    # thresholds once, exactly as the holder-scoped dice above do.
    dice_groups += total_ally_extra_damage(attacker, target, attack_roll, fight)

    damage_roll = roll_damage(
        dice_groups=dice_groups,
        modifier=pool.modifier + damage_bonus,
        is_critical=attack_roll.is_critical,
        drop_lowest=pool.drop_lowest,
        # Content the attacker carries that scales the whole roll - Splendor's
        # Smite, which doubles it. Passed into the roll rather than applied to the
        # total afterwards, so everything that later reads `damage_roll.total` -
        # the report, Whirlwind's splash, the target's on-attacked content - sees
        # the number that actually landed. Asked generically; nothing here knows
        # what any of it is.
        multiplier=dealt_damage_scaling(attacker, target, fight),
    )

    # Content that re-throws individual dice of the roll just made - the Blade
    # card Not Good Enough, which rerolls any 1s or 2s. Asked after the dice are
    # read and before anything else looks at the total, so a reroll is
    # indistinguishable from having rolled that way, exactly as a remade attack
    # roll is. The discard, if the weapon has one, takes the lowest of whatever
    # this leaves - `dropped` is derived from the results rather than stored.
    damage_roll = reroll_damage_dice(attacker, damage_roll, fight)

    # And content that buys the top face of one die outright - the Blade card
    # Versatile Fighter, which marks a Stress for it. After the reroll rather
    # than before, so a die Not Good Enough has already rescued is judged on what
    # it now shows and the Stress goes to whatever is still worst.
    damage_roll = maximise_damage_dice(attacker, damage_roll, fight)

    # Typed off the weapon, which is where the SRD prints it - a Broadsword deals
    # physical damage and a Greatstaff magic - so a target's resistance is
    # answered by what the PC chose to carry rather than by anything decided here.
    #
    # `fight` is passed for the reason every other call site passes it: it is how
    # the target's own damage responses reach state that only lives for the
    # length of a fight. It was missing here, which left every hook downstream of
    # a PC weapon hit - the resistance, the two severity hooks - seeing None.
    # ...unless content the attacker carries retypes the swing, which Smite does:
    # "this attack deals magic damage regardless of the weapon's damage type".
    # Asked generically, and the weapon's own type is what comes back when nothing
    # answers.
    marked = target.take_damage(
        damage_roll.total,
        fight,
        damage_type=dealt_damage_type(attacker, target, weapon.damage_type, fight),
    )

    # Content the *target* carries that punishes being hit - the Glass Snake's
    # shards of glass. Asked after the damage lands, because the trigger is a
    # successful attack rather than a wound, and handed the weapon because how
    # far away the attacker was standing is the only thing such content has to
    # read range off. Nothing here knows what any of it is.
    #
    # Both figures the hit produced go through: the damage rolled, and the HP it
    # finally cost. The SRD keys such features on either - see `on_attacked`.
    apply_on_attacked(target, attacker, weapon, damage_roll.total, marked, fight)

    return AttackResult(
        attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
    )
