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
  4. Spend Hope on an Experience, if Hope is plentiful.
  5. Look for something that has gone to ground, if anything has and nobody has
     looked yet - see `_search_for_hidden`. This is the one step that takes the
     action roll *ahead* of the shuffle rather than being one option among it.
  6. Attack.

Steps (2) and (3) aren't a list of features here: anything that needs no roll -
a Hope feature, a class feature, a domain card - is reached through the single
`use_free_abilities` call, and decides for itself whether it's worth using. Each
entry carries its own "does this make sense now?" test; the ordering here is the
only global policy.

**Help an Ally is deliberately not on that list.** It used to be, as the other
half of (4), and it was wrong there: helping is a reaction to somebody *else's*
roll, not something a PC spends their own spotlight on. It lives in
`content/help.py` and is asked at every site that makes an action roll - which
includes several domain cards, and is why it sits in `content/` rather than
here.

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
from dataclasses import replace

from content import (
    action_options,
    adversary_attack_is_hobbled,
    apply_ally_on_hit,
    apply_attack_missed,
    apply_on_hit,
    apply_on_spotlight,
    attacks_on_are_aided,
    find_shielder,
    forced_adversary_target,
    forced_party_target,
    granted_attack_advantage,
    hope_die_for,
    is_immune_to,
    remake_action_roll,
    skips_spotlight,
    standard_attack_area,
    total_damage_bonus,
    total_roll_bonus,
    use_free_abilities,
)
from content.aoe import targets_in_area
from content.conditions import BEFORE_AN_ACTION_ROLL, VULNERABLE
from content.help import help_with_roll
from content.names import canonical
from content.rolls import (
    EXPERIENCE_HOPE_FLOOR,
    clear_experience_utilised,
    note_experience_utilised,
)
from dice.common import AdvantageState, combined
from dice.duality import roll_duality
from items.registry import find_consumable, find_weapon
from items.weapons import attack_with

# A PC drinks at this much unmarked HP or less. Two is the point where the next
# solid hit is plausibly the last one.
LOW_HP_UNMARKED = 2

# `EXPERIENCE_HOPE_FLOOR` now lives in `content/rolls.py` and is imported above.
# It moved because **Help an Ally** reads the same number and is made from
# `content/`, which may not import `combat/`. The rule it states is unchanged:
# spending Hope on an Experience is the cheapest use of a big Hope pool, so the
# floor is set high enough that doing it never starves the cards that want Hope.

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


def choose_pc_target(
    state: FightState, pc: PlayerCharacter | None = None
) -> Adversary | None:
    """Which adversary the party attacks: the one closest to going down.

    Focus fire. It's what a party actually does, and it's the choice that
    matters most for balance - every adversary removed early is a whole
    activation the GM never gets - so modelling anything softer would flatter
    the encounter. Ties go to the one listed first, which keeps a fight
    reproducible under a fixed seed.

    **Unless something on the GM's side has taken the choice away.** The
    Weaponmaster's Goading Strike fixes a Taunted PC's target to the
    Weaponmaster, which is asked here through one generic dispatch - nothing in
    this function knows what a Taunt is, or that any such content exists. `pc` is
    optional only because callers that ask "who is the party focusing?" in
    general, rather than on one PC's behalf, have nobody to be compelled.
    """
    living = state.living_adversaries
    if not living:
        return None

    if pc is not None:
        forced = forced_party_target(pc, state)
        if forced is not None:
            return forced

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

    **Unless something the party did has taken the choice away.** Grace's
    Enrapture fixes an Enraptured adversary's attention on whoever cast it,
    which is asked here through one generic dispatch - the mirror of the
    Weaponmaster's Taunt reaching `choose_pc_target`. Nothing in this function
    knows what an Enrapture is, or that any such content exists.
    """
    standing = state.conscious_party
    if not standing:
        return None

    compelled = forced_adversary_target(adversary, state)
    if compelled is not None and compelled.is_conscious:
        return compelled

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
    target = choose_pc_target(state, pc)
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


def _search_for_hidden(pc: PlayerCharacter, state: FightState) -> AttackResult | None:
    """Spend this PC's action roll hunting something that has gone to ground.

    SIMULATION RULE - policy, ruled. A condition may print a roll somebody *else*
    can make to end it - the Sylvan Soldier's Blend In lifts when "a PC succeeds
    on an Instinct Roll (14) to find them" - and the ruling is that the party
    spends **one action roll** on it. Not one per PC and not one per spotlight:
    the attempt is made once, and if it fails the party lives with the
    Disadvantage until the condition runs out on its own terms.

    That "once" is enforced by taking the `found_by` off the condition after the
    attempt rather than by a token, which means a *fresh* application brings a
    fresh attempt - a Soldier who hides again is hunted again. `Condition` is
    frozen, so the spent condition is replaced with a copy that offers no roll.

    Taken **before** the shuffled options rather than among them, deliberately.
    Everything else a PC could do that spotlight is chosen at random among the
    viable, which is the standing default; this one is a decision the user made,
    so it happens rather than coming up about half the time.

    It is a real action roll - Duality Dice plus the trait, offered to the
    party's reroll content, and its Hope or Fear outcome spent by the loop
    exactly as a missed attack's would be. So the search costs the party the
    spotlight when it comes up with Fear, which is most of what makes it a cost.

    What it does *not* get is an Experience or a damage roll: there is nothing to
    hit. Returns None when there is nobody to look for, so the caller falls
    through to the ordinary options.
    """
    for adversary in state.living_adversaries:
        condition = state.searchable_condition(adversary)
        if condition is None:
            continue

        trait, difficulty = condition.found_by
        # An ally can spend a Hope to help with this the same as with any other
        # action roll - the search is a real one, which is the whole reason it
        # costs the party the spotlight when it comes up with Fear.
        help_offered = help_with_roll(pc, state)

        def roll():
            return roll_duality(
                modifier=pc.traits.get(trait, 0) + help_offered.bonus,
                difficulty=difficulty,
                advantage_state=(
                    AdvantageState.DISADVANTAGE
                    if state.disadvantaged_on(pc, trait)
                    else AdvantageState.NONE
                ),
                hope_die=hope_die_for(pc, state),
                help_dice=help_offered.dice,
            )

        made = remake_action_roll(pc, roll(), roll, state)
        if made.is_success:
            state.clear_condition(adversary, condition.name)
            state.note(
                f"{pc.name} finds {adversary.name}, who is no longer "
                f"{condition.name} ({made})"
            )
        else:
            # Spent either way: the attempt is what the ruling allows one of.
            state.apply_condition(adversary, replace(condition, found_by=None))
            state.note(f"{pc.name} searches for {adversary.name} in vain ({made})")
        return AttackResult(attack_roll=made, damage_roll=None)
    return None


def _make_the_roll(
    pc: PlayerCharacter, target: Adversary, state: FightState
) -> AttackResult | None:
    """The one roll that can pass the spotlight, with its aftermath applied.

    A weapon attack is not privileged here - it's the fallback. Content that
    makes an action roll of its own gets first refusal, and declines by
    returning None. Nothing in this function knows what any of that content is.
    """
    # A new roll, so whatever the last one utilised is forgotten. Set before the
    # options are offered because it's the option that chooses to pay for an
    # Experience, and only the one that takes the roll ever does.
    clear_experience_utilised(pc, state)

    # Conditions that charge their holder for making an action roll get paid
    # first - the Giant Scorpion's Poison is "roll a d6 before you make an action
    # roll". Announced generically; nothing here knows which conditions those
    # are, or that any exist.
    state.apply_condition_effects(pc, BEFORE_AN_ACTION_ROLL)

    # Something on the field may have gone to ground, and the ruling is that the
    # party spends one action roll looking for it. Asked before the options are
    # offered rather than shuffled in among them, because this is a decision
    # rather than the random-among-viable default. See `_search_for_hidden`.
    searching = _search_for_hidden(pc, state)
    if searching is not None:
        return searching

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
    #
    # A combatant carrying no weapon simply isn't offered one. Every sheet in
    # characters/ names a primary weapon, so this changes nothing for a PC; what
    # it makes possible is a party member who is not one, which the Book of
    # Exota's construct is. Without the guard `find_weapon("")` would raise about
    # half the time, on the spotlights where the shuffle happened to reach the
    # swing first.
    options = action_options(pc)
    if pc.primary_weapon:
        options = options + [swing_the_weapon]
    random.shuffle(options)

    # Recorded *before* the attack resolves rather than after it. Nothing that
    # reads this memory outside an attack can tell the difference - an adversary
    # choosing who to swing at does so on the GM's turn, long after either write
    # would have happened - but content firing from *inside* the attack can:
    # until this moved, a feature triggered by the blow that landed still saw
    # whoever hit that adversary the time before. The Skeleton Knight's
    # `Dig Two Graves` swings at "the creature who killed them" and is the first
    # thing to ask. Written whether or not the attack hits, exactly as before.
    state.last_attacker_of[id(target)] = pc
    state.last_pc_to_attack = pc

    result = None
    for option in options:
        result = option(pc, target, state)
        if result is not None:
            break

    if result is None:
        # Only reachable for a combatant carrying no weapon whose every option
        # declined - the swing never declines, so a PC can never get here. None
        # is what the caller already understands as "this spotlight resolved into
        # nothing", and the combatant is marked as having acted either way, so
        # the pass moves on rather than coming back to them.
        return None

    if result.damage_roll is not None:
        apply_on_hit(pc, target, result, state)
        # And content another PC put *on* this one, which the holder-scoped call
        # above can't reach - the Book of Sitil's Parallela hangs on an ally and
        # resolves when they land a hit. Asked party-wide; nothing here knows
        # what any of it is, or that any of it exists.
        apply_ally_on_hit(pc, target, result, state)

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


def adversary_attack_advantage(
    adversary: Adversary, target: PlayerCharacter, state: FightState
) -> AdvantageState:
    """The state an adversary's attack on `target` is rolled in.

    Five sources, folded together rather than any one winning outright. A
    Vulnerable PC hands every roll against them Advantage per the SRD - unless
    something they carry turns the condition off, which is asked generically
    rather than by name. Being Hidden is its mirror. On top of those, content the
    *attacker* carries can grant its own (the Jagged Knife Shadow's Cloaked), and
    so can content belonging to a **third** adversary that has the target
    surrounded (the Shambling Zombie's Too Many to Handle) - which is the exact
    counterpart of the hobble `items/weapons.py` folds in on the party's side.

    The fifth is the **party** hobbling this attack, which is the mirror of that
    same counterpart pointed back across the table: Valor's *Goad Them On* makes a
    goaded adversary swing at the taunter with disadvantage. Asked generically;
    nothing here knows what any of it is.

    One function because two callers have to agree. The standard attack rolls in
    whatever this returns, and a feature that needs to know whether the attack
    *had* Advantage reads it off the roll rather than working it out again -
    asking twice would consume Cloaked's token twice.
    """
    vulnerable = state.is_vulnerable(target) and not is_immune_to(
        target, VULNERABLE, state
    )
    return combined(
        AdvantageState.ADVANTAGE if vulnerable else AdvantageState.NONE,
        # Content a third adversary carries, keyed on where the target is
        # standing rather than on who is swinging. Asked generically.
        AdvantageState.ADVANTAGE
        if attacks_on_are_aided(target, state)
        else AdvantageState.NONE,
        # Hidden is Vulnerable's mirror and folds in the same way. Nothing makes
        # a PC Hidden today, so this never fires - it is here because both sides
        # should answer the question the same way, and the party side of it (in
        # items/weapons.py) very much does fire.
        AdvantageState.DISADVANTAGE if state.is_hidden(target) else AdvantageState.NONE,
        granted_attack_advantage(adversary, target, state),
        # And party content hobbling this adversary's swing - Goad Them On.
        AdvantageState.DISADVANTAGE
        if adversary_attack_is_hobbled(adversary, target, state)
        else AdvantageState.NONE,
    )


def take_adversary_turn(adversary: Adversary, state: FightState) -> AttackResult | None:
    """Spotlight one adversary: pick a PC and swing at them.

    A Vulnerable PC (all Stress marked) is attacked with Advantage, per the
    SRD's condition - unless something the PC carries turns the condition off,
    which is asked generically rather than by name.

    An activation resolves into exactly one of the adversary's Action features
    or its standard attack, picked at random among those willing - which is the
    standing policy for anything with no rule of its own. What makes a feature
    willing is its own business: several consult the Stress-desperation rule
    (`Adversary.will_spend_stress`) and decline while the adversary is healthy.

    The fight is handed to the attack so it reaches the target's damage
    responses: whether one applies can depend on state that only exists for the
    length of this fight.
    """
    # Content that fires on the spotlight arriving rather than on anything the
    # adversary chooses - the Glass Snake's Spitter Die rolls itself every time
    # the Snake is up. Asked first, so it happens whatever the adversary then
    # does, and it neither competes for the action nor consumes it.
    apply_on_spotlight(adversary, state)

    # Content that spends the activation on nothing at all - the Green Ooze's
    # Slow, which prepares on one spotlight and acts on the next. Asked after the
    # riders above, because the SRD's trigger for those is being *in* the
    # spotlight and the Ooze is: it simply can't act once it is there. The Fear
    # the activation cost has already been charged by the GM turn, which is the
    # whole weight of the feature.
    if skips_spotlight(adversary, state):
        return None

    # And a condition that stops them acting at all - Stunned, which Grace's
    # Hypnotic Shimmer applies. Asked after the spotlight riders above for the
    # same reason `skips_spotlight` is: the trigger for those is being *in* the
    # spotlight, and a Stunned adversary is. It simply can't do anything once it
    # is there, and the Fear the activation cost has already been charged.
    #
    # Read generically off `Condition.prevents_action`; nothing here knows the
    # condition's name, or that any such condition exists.
    if state.cannot_act(adversary):
        state.note(f"{adversary.name} cannot act, and the spotlight is spent")
        return None

    target = choose_adversary_target(adversary, state)
    if target is None:
        return None

    target = _shield(target, state)

    def standard_attack(attacker, at, fight):
        """The stat block's printed attack - what an adversary does by default.

        Whether it rolls with Advantage is `adversary_attack_advantage`'s answer,
        which folds the target being Vulnerable together with anything the
        attacker carries that grants it.

        Never declines, exactly like the PC's weapon swing, so a spotlight always
        resolves into something.
        """
        advantage = adversary_attack_advantage(attacker, at, fight)

        # A passive can turn the printed attack into an area one - the Cave
        # Ogre's Ramp Up. Asked here rather than being an action option, because
        # it changes what the standard attack *is* rather than replacing it.
        band = standard_attack_area(attacker, fight)
        if band is not None:
            caught = targets_in_area(band, fight.conscious_party)
            result, struck = attacker.area_attack(caught, advantage, fight)
            for hit in struck:
                fight.note(f"{attacker.name} catches {hit.name} in its swing")
            return result

        return attacker.attack(at, advantage, fight)

    # An SRD "Action" feature is what the adversary does *instead of* its
    # standard attack, so the two are offered together and exactly one resolves -
    # the same shape as a PC choosing between a domain card and their weapon, and
    # shuffled for the same reason: the order a stat block lists its features in
    # carries no meaning and must not decide which one gets used.
    options = action_options(adversary) + [standard_attack]
    random.shuffle(options)

    result = None
    for option in options:
        result = option(adversary, target, state)
        if result is not None:
            break

    # The GM side gets its on-hit riders the same way the party does, through the
    # one dispatch call - the Bear's Momentum hands the GM a Fear off a landed
    # attack. Nothing here knows which feature that is, and an adversary carrying
    # none is unaffected.
    if result.damage_roll is not None:
        apply_on_hit(adversary, target, result, state)

    # And the other half of that: content the *target* carries that responds to
    # an attack failing - the Bone card Redirect, which sends it into an
    # adversary instead. The one moment in an incoming attack nothing announced
    # until now; `before_attacked` and `on_attacked` cover the other two, and
    # both of those are asked from `items/weapons.py`, which only ever sees the
    # party swinging. Nothing here knows what any of it is.
    if result.made_an_attack and result.damage_roll is None:
        apply_attack_missed(target, adversary, result.attack_roll, state)

    if not result.made_an_attack:
        pass  # the feature narrated itself; there is no roll to report
    elif result.damage_roll is None:
        state.note(f"{adversary.name} misses {target.name} ({result.attack_roll})")
    else:
        state.note(
            f"{adversary.name} hits {target.name} for {result.damage_roll.total} "
            f"({target.hp_marked}/{target.hp_max} HP marked)"
        )
        if not target.is_conscious:
            state.note(f"{target.name} avoids death and drops unconscious")
    return result
