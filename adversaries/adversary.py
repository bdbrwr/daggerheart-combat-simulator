"""Adversary stats and state - the GM-side equivalent of characters/player_character.py.

An Adversary is a plain bag of numbers plus one generic `attack()`. Every stat
that affects how dangerous a fight is - Difficulty, thresholds, HP, Stress,
attack modifier, damage dice, damage modifier - is a field, so tuning an
adversary never means editing code. That's the whole point: this simulator
exists to push those numbers around until an encounter lands on the balance
profile we want, so they have to be reachable as values a run can vary.

Individual adversaries are **authored as JSON**, one file per publication (see
srd.json), and read by catalogue.py - a stat block is data, and this is the side
of the table homebrew is written for. What a stat block *does* beyond a standard
attack is its named features, which are code in features/adversaries.py, exactly
the way a character sheet names domain cards that live in domain_cards/.

Per-encounter tweaks belong in encounters/, not in the catalogue: `spawn()`
copies a definition and applies overrides so the definition itself is never
mutated by a simulated fight.

Adversaries don't have Hope, Armor Slots, or Evasion (PC-only concepts) - the
number PC attacks roll against is Difficulty instead (per the SRD: "attacks
rolled against adversaries use the target's Difficulty instead of Evasion").

Defeat is simply `is_defeated` - all HP marked, and the fight loop drops them.
Adversaries get none of the PC death-move machinery; that asymmetry is in the
rules, not a shortcut.
"""

from dataclasses import dataclass, field, replace
from typing import Protocol

from combat.results import AttackResult
from content.names import ADVERSARY, qualified
from content.aoe import Range, band_named, targets_hit
from content.damage_types import damage_type_named, reduced
from content.registry import (
    apply_on_damaged,
    deals_direct_damage,
    force_adversary_reroll,
    harden_damage,
    incoming_damage_multiplier,
    resistance_to,
    soften_damage,
    standard_attack_damage,
    standard_attack_damage_type,
    total_damage_bonus,
    total_difficulty_bonus,
    total_evasion_bonus,
)
from dice.common import AdvantageState
from dice.d20 import roll_d20
from dice.damage import DiceGroup, roll_damage


class Target(Protocol):
    """Anything an adversary's attack can target - a PC, for now."""

    evasion: int

    # Scanned for content that raises the target's own Evasion against this
    # attack - the Bone card Ferocity. Evasion used to be read straight off the
    # sheet and could not change mid-fight.
    named_features: list[str]

    # Read by nothing here, but handed to the party's forced-reroll content: how
    # close the target is to going down is what decides whether stopping an
    # ordinary hit is worth paying for.
    is_near_death: bool

    def take_damage(
        self, amount: int, fight=None, direct: bool = False, damage_type=None
    ) -> int: ...


@dataclass
class Adversary:
    """An adversary's stats plus whatever HP/Stress have been marked so far.

    Used both as a reusable definition (a stat block, at starting state) and as
    a single combatant in a fight - `spawn()` turns the former into the latter.
    """

    name: str
    tier: int
    difficulty: int
    major_threshold: int
    severe_threshold: int
    hp_max: int
    stress_max: int
    attack_modifier: int
    damage_dice: list[DiceGroup] = field(default_factory=list)
    damage_modifier: int = 0

    # The type the stat block prints beside its standard attack - "Warp Blast:
    # Close, 1d12+6 mag". Either of the SRD's two, spelled as the book spells it
    # or with the book's own abbreviation; `content/damage_types.py` matches both.
    #
    # Optional rather than required, which is the one place this differs from
    # `range`. An omitted range would quietly decide how many combatants an area
    # feature reaches - a silent difference in the numbers. An omitted type can
    # only ever fail to apply somebody's resistance, so it leaves the fight
    # exactly as it was before types existed. Every entry states one anyway; the
    # default is a floor, not a licence.
    damage_type: str = ""

    # The range band the stat block prints beside its standard attack - "Claws:
    # Very Close, 1d12+2".
    #
    # No positioning is tracked, so this never decides whether an ordinary attack
    # connects. It matters when a feature turns the standard attack into an area
    # one: the SRD's Ramp Up is "their standard attack against all targets within
    # range", and *within range* is this. Before it was a field, such a feature
    # had to name a band itself, which meant the Cave Ogre's Very Close was
    # written into the feature - so the same feature on a Melee adversary would
    # have swept the wrong band, and every future one would need its own hand-
    # entered copy of a number already printed on the page.
    #
    # Kept as the printed string, the way `items/catalogue.py` keeps a weapon's,
    # so a catalogue entry and an encounter override are the same vocabulary.
    # `attack_band` is the parsed form.
    range: str = "Melee"

    # What this stat block does beyond a standard attack, by name. Implemented
    # in features/adversaries.py, reached through the same dispatch a PC's
    # domain cards use, and reported in the coverage block either way - so a
    # feature nobody has written is visible rather than silently absent.
    features: list[str] = field(default_factory=list)

    # The role the SRD prints beside the tier - "Solo", "Bruiser", "Minion".
    #
    # Carried as data and **never honoured by the fight loop**, because the SRD
    # gives a type no rules of its own: "An adversary's type represents the role
    # they play in a conflict", followed by one descriptive line each ("Bruisers:
    # tough; deliver powerful attacks"). Everything mechanical that sounds like a
    # type is printed as a named *feature* instead - Minion (X), Horde (X),
    # Relentless (X), Slow, Arcane Form, Armored Carapace are all in the SRD's
    # list of example passives, which is where they reach a fight from.
    #
    # It's here because it's on the printed page and a catalogue entry is meant
    # to be checkable against it, and because it's what a reader filters on -
    # Social adversaries are deliberately not ported, and without this the reason
    # would live nowhere.
    type: str = ""

    # Which book this stat block was printed in, or where a homebrew one came
    # from. Never read by the fight loop; it's how a reader tells an as-printed
    # adversary from one of ours.
    publication: str = ""

    hp_marked: int = 0
    stress_marked: int = 0

    @property
    def named_features(self) -> list[str]:
        """This stat block's features, namespaced so dispatch can find them.

        The same input the coverage report takes for a PC. Qualified because a
        catalogue's feature names are not unique across kinds - see
        content/names.py - and because "adversary:Relentless" is what a reader
        of the coverage block needs to see to know which Relentless is missing.
        """
        return [qualified(ADVERSARY, name) for name in self.features]

    @property
    def is_defeated(self) -> bool:
        """True once every HP is marked - adversaries just leave the fight.

        No death move, no unconscious state: the SRD's death rules are a PC
        thing, and for balance purposes an adversary that's out is out.
        """
        return self.hp_marked >= self.hp_max

    @property
    def attack_band(self) -> "Range":
        """This adversary's printed range, as the band the area rule works in.

        Content that sweeps "within range" reads this rather than naming a band,
        so one feature is correct on every stat block that carries it. Raises on
        an unrecognised band, which the catalogue has already rejected at load -
        the check is here too because an `Adversary` built directly in code
        never went through it.
        """
        return band_named(self.range)

    @property
    def hp_unmarked(self) -> int:
        """HP not yet marked - the party side's vocabulary, on the GM side too.

        Damage *marks* HP in Daggerheart, so both sides of the table answer the
        question the same way and nothing anywhere says "HP left".
        """
        return max(self.hp_max - self.hp_marked, 0)

    @property
    def stress_unmarked(self) -> int:
        """Stress slots still free - what a feature's cost has to fit into."""
        return max(self.stress_max - self.stress_marked, 0)

    def spawn(self, **overrides) -> "Adversary":
        """An independent copy at starting state, with any stat overrides applied.

        One definition can back several combatants in the same fight, so each
        one needs its own HP/Stress to mark and its own damage_dice list.
        Overrides are how an encounter tunes a stat block without touching the
        definition - `JAGGED_KNIFE_BANDIT.spawn(hp_max=7, damage_modifier=3)`.

        **Difficulty-modifying features are resolved here**, into the number,
        rather than being consulted on every roll made against this adversary -
        the SRD's `Flying (X)` is the case, and `content/registry.py`'s
        `difficulty_bonus` says why. The bonus lands on top of whatever the
        encounter overrode, so tuning the printed Difficulty and carrying the
        feature are independent.

        The consequence to know: this is a **definition-to-combatant** step and
        spawning a combatant again would apply the bonus a second time. Nothing
        does, and nothing should - `spawn` is called on a catalogue entry.
        """
        changes = {
            "damage_dice": list(self.damage_dice),
            "features": list(self.features),
            "hp_marked": 0,
            "stress_marked": 0,
        }
        changes.update(overrides)
        spawned = replace(self, **changes)
        spawned.difficulty += total_difficulty_bonus(spawned)
        return spawned

    def _damage_for(self, dice, modifier, attack_roll, target, fight):
        """Roll this attack's damage, letting content add to it first.

        `dice`/`modifier` default to the stat block's, so a feature that hits
        with something other than the printed attack - the Bear's Bite at
        3d4+10 - passes its own rather than reimplementing the roll.

        **That default is also the discriminator** for content that replaces the
        standard attack's dice: `dice is None` means "the printed attack", which
        is exactly what `Horde (X)` and `Pack Tactics` say they change. A feature
        that brought its own dice is never asked, since "instead of their standard
        damage" says nothing about a different attack.

        `total_damage_bonus` is asked here, which is "before rolling damage" and
        after the hit is known, exactly where the Construct's Overload wants to
        be offered its Stress. The standard-attack swap sits in the same window
        for the same reason: Pack Tactics pays out a Fear on a *successful*
        standard attack, and asking before the roll would pay for a miss.
        """
        if dice is None:
            swapped = standard_attack_damage(self, target, attack_roll, fight)
            if swapped is not None:
                dice, modifier = swapped

        bonus = total_damage_bonus(self, target, fight) if fight is not None else 0
        return roll_damage(
            dice_groups=self.damage_dice if dice is None else dice,
            modifier=(self.damage_modifier if modifier is None else modifier) + bonus,
            is_critical=attack_roll is not None and attack_roll.is_critical,
        )

    def type_of_damage(self, stated=None):
        """The type this attack deals, defaulting to the stat block's own.

        The same arrangement `damage_dice` and `direct` already use, and it says
        the same rule the SRD writes for damage: a feature that states its own
        type on the page passes it - the Construct's Death Quake is magic
        whatever the Construct's fists are - and one that says nothing deals the
        printed attack's type.

        Public, and the one place that rule lives. `attack` and `area_attack`
        call it for their callers, but a feature that rolls damage without going
        through either - a reflection, a splash, a countdown volley - has to ask
        it directly rather than reading `damage_type` off the stat block itself,
        so the fallback can never be spelled two different ways.

        **Content can override the printed attack's type**, which is what the
        Spellblade's `Arcane Steel` does ("considered both physical and magic").
        Asked only when nothing was stated, so it reaches the standard attack and
        never a feature that brought its own type - the same discriminator
        `standard_damage` uses for dice.
        """
        if stated is not None:
            return stated
        overridden = standard_attack_damage_type(self)
        return self.damage_type if overridden is None else overridden

    def _dealt(self, damage_roll, target, fight) -> int:
        """The damage this roll actually delivers, after anything multiplies it.

        Separate from the roll because the roll is what was *thrown* and this is
        what *lands*: the Jagged Knife Kneebreaker's `I've Got 'Em` doubles what
        its allies deal to a creature it has Restrained, and that doubling has to
        happen before the target's thresholds see the number - doubling after
        would double the HP marked instead, which is a far larger effect.

        Asked of the field rather than of either combatant, since the content
        doing it belongs to neither. See `content/registry.py`'s
        `damage_multiplier`.

        **Floored once, at the end.** A multiplier can be a fraction - the Young
        Dryad's `Voice of the Forest` halves what its rallied allies deal - and
        rounding after everything has multiplied is what keeps a halving and a
        doubling on the same attack from depending on which was applied first.
        Half rounds down, following every other halving in the codebase.
        """
        multiplier = incoming_damage_multiplier(target, self, fight)
        return int(damage_roll.total * multiplier)

    def area_attack(
        self,
        targets: list,
        advantage_state: AdvantageState = AdvantageState.NONE,
        fight=None,
        damage_dice=None,
        damage_modifier=None,
        direct: bool | None = None,
        damage_type=None,
    ) -> tuple[AttackResult, list]:
        """One attack roll measured against every target's Evasion.

        The shape the SRD's area features take: "make an attack against all
        targets in front of them within Close range. Targets the Ogre succeeds
        against take 1d10+2." One roll, one damage roll, applied to everyone it
        beat - the same reading `Hold Them Off` already uses for reusing a roll.

        Returns the result and the targets actually struck, since callers need
        the count: several features hand the GM a Fear for beating more than one.

        The party is offered a forced reroll here exactly as it is for a
        single-target attack, and for the same reason - the roll hasn't been read
        yet, so replacing it is indistinguishable from having rolled that way. The
        PC handed to the dispatch is whoever in the area is closest to going down,
        since content deciding whether the roll is worth stopping is asking about
        the worst it could do.
        """
        if not targets:
            return AttackResult(attack_roll=None, damage_roll=None), []

        def swing():
            return roll_d20(
                modifier=self.attack_modifier,
                # The area rule reads a success as beating *somebody*, so the
                # roll is checked against the easiest target and each one
                # re-checked below.
                evasion=min(target.evasion for target in targets),
                advantage_state=advantage_state,
            )

        attack_roll = force_adversary_reroll(
            self,
            min(targets, key=lambda target: target.hp_unmarked),
            swing(),
            swing,
            fight,
        )

        struck = targets_hit(attack_roll, targets)
        if not struck:
            return AttackResult(attack_roll=attack_roll, damage_roll=None), []

        damage_roll = self._damage_for(
            damage_dice, damage_modifier, attack_roll, struck[0], fight
        )
        # Unstated means "whatever this adversary's features say", so Bone
        # Breaker reaches a swept attack the same way it reaches a single one.
        if direct is None:
            direct = deals_direct_damage(self, fight)

        marked = 0
        for target in struck:
            # Asked per target: a multiplier keyed on a condition applies to
            # whoever carries it, not to everyone the sweep caught.
            marked += target.take_damage(
                self._dealt(damage_roll, target, fight),
                fight,
                direct=direct,
                damage_type=self.type_of_damage(damage_type),
            )

        return (
            AttackResult(
                attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
            ),
            struck,
        )

    def attack(
        self,
        target: Target,
        advantage_state: AdvantageState = AdvantageState.NONE,
        fight=None,
        damage_dice=None,
        damage_modifier=None,
        direct: bool | None = None,
        damage_type=None,
    ) -> AttackResult:
        """Standard attack: d20 + attack_modifier against the target's Evasion.

        On a hit, rolls this adversary's damage dice plus its flat modifier and
        applies the total to the target. Adversaries whose attack does something
        a plain roll can't express need their own function alongside their
        definition; nothing does yet.

        `fight` is handed to the target rather than used here: a PC's damage
        responses can depend on state that only lives for the length of a fight
        (Unstoppable's die), and the target has no other way to reach it. It
        stays optional so a damage calculation can still be tested on its own.

        The one thing `fight` *is* used for here is reaching the party: content
        that can force this adversary to re-make its roll belongs to a PC, not to
        the PC being swung at, so the dispatch is asked party-wide. Nothing in
        this module knows which content that is.
        """

        # Worked out once, and *outside* the closure below, for the reason
        # `items/weapons.py` computes its roll modifier outside its own: asking
        # content for an Evasion bonus is the commitment, and the Bone card
        # Ferocity's bonus lasts only "until after the next attack made against
        # you". Asking again inside a forced reroll would spend it twice on one
        # attack. Nothing here knows what content answers.
        evasion = target.evasion + total_evasion_bonus(target, self, fight)

        def swing():
            return roll_d20(
                modifier=self.attack_modifier,
                evasion=evasion,
                advantage_state=advantage_state,
            )

        # Asked before anything reads the roll, so a forced reroll is
        # indistinguishable from the adversary having rolled that way first.
        attack_roll = force_adversary_reroll(self, target, swing(), swing, fight)

        if not attack_roll.is_success:
            return AttackResult(attack_roll=attack_roll, damage_roll=None)

        damage_roll = self._damage_for(
            damage_dice, damage_modifier, attack_roll, target, fight
        )
        # Whether this attack is direct - no Armor Slot may be marked against it -
        # is a question for the attacker's features, asked generically. Nothing
        # here knows that the Cave Ogre's Bone Breaker is what answers it.
        #
        # Stated explicitly by a feature whose *own* attack is direct without any
        # passive granting it, which is the Dire Wolf's Hobbling Strike. Unstated
        # still means "whatever this adversary's features say", so the two don't
        # interfere - the same arrangement `area_attack` already uses.
        if direct is None:
            direct = deals_direct_damage(self, fight)
        marked = target.take_damage(
            self._dealt(damage_roll, target, fight),
            fight,
            direct=direct,
            damage_type=self.type_of_damage(damage_type),
        )
        return AttackResult(
            attack_roll=attack_roll, damage_roll=damage_roll, hp_marked=marked
        )

    def mark_hp(self, amount: int) -> None:
        self.hp_marked = min(self.hp_marked + amount, self.hp_max)

    def clear_hp(self, amount: int) -> None:
        self.hp_marked = max(self.hp_marked - amount, 0)

    def mark_stress(self, amount: int) -> None:
        self.stress_marked = min(self.stress_marked + amount, self.stress_max)

    def clear_stress(self, amount: int) -> None:
        self.stress_marked = max(self.stress_marked - amount, 0)

    def can_spend_stress(self, amount: int = 1) -> bool:
        """Whether this adversary can pay a feature's Stress cost.

        The SRD is explicit about where it comes from: "If a feature requires the
        GM to spend Stress to activate it, the Stress must come from the adversary
        whose feature is being activated." So this is per-adversary, not a pool.

        Same shape as a PC's voluntary Stress cost, and the same rule - a feature
        whose Stress can't be paid simply isn't available. Unlike a PC there is no
        fallback to marking HP, because that rule is about being *forced* to mark
        Stress, which nothing does to an adversary here.
        """
        return self.stress_marked + amount <= self.stress_max

    def will_spend_stress(self, amount: int = 1) -> bool:
        """Whether this adversary is hurt enough to pay an **Action**'s Stress cost.

        SIMULATION RULE - policy. `can_spend_stress` answers whether the slots
        exist; this answers whether the GM would spend them, and the two are
        deliberately separate questions. An adversary hoards its last Stress
        while it is healthy and empties the track as it gets closer to going
        down, so a stat block's Stress reads as how much desperation it has in
        it rather than as a budget spent the moment a fight starts.

        The rule, with X the Stress slots still free before this cost is paid:

            hp_unmarked <= X ** 2 + 1

        So with three slots free an adversary spends at 10 or fewer unmarked HP,
        with two at 5 or fewer, and its last slot only at 2 or fewer - the same
        line `NEAR_DEATH_HP_UNMARKED` draws on the party side, which is where
        the +1 comes from. A cost of more than one slot is measured at the last
        slot it would mark, since that is the one that has to be affordable.

        In practice almost every ported tier 1 adversary clears the first
        threshold immediately (three free slots against 9 HP or fewer) and then
        has to be wounded for the rest, which is the intended shape. The Bear is
        the exception worth knowing: 7 HP against only two Stress means it can't
        Bite until it is down to 5 unmarked HP.

        **Reactions do not consult this.** A reaction fires when its trigger
        happens or not at all, so gating it on how hurt the adversary is would
        mean discarding the trigger rather than choosing a moment - which is a
        different decision from the one this rule is about. Reaction features
        call `can_spend_stress` directly.
        """
        if not self.can_spend_stress(amount):
            return False
        slots_left_after = self.stress_unmarked - amount
        return self.hp_unmarked <= (slots_left_after + 1) ** 2 + 1

    def will_spend_hp(self, amount: int = 1) -> bool:
        """Whether this adversary would pay a feature's cost in its **own HP**.

        SIMULATION RULE - policy. The Minor Chaos Elemental's Sickening Flux is
        the first feature in the catalogue that costs HP rather than Stress or
        Fear, and the Stress-desperation rule doesn't reach it.

        The ruling is that HP is spent on the same reading as Stress, with one
        guard: **never the last HP**. Worth being plain about what that comes to,
        because the two halves are not equally load-bearing. The desperation test
        asks whether `hp_unmarked` has fallen to `X**2 + 1` with X the slots left
        after paying - and when the pool being spent *is* the HP track, that
        reduces to `hp_unmarked <= hp_unmarked**2 + 1`, which is true of every
        adversary alive. So the rule that actually bites is the guard: an
        adversary will spend HP freely, from full health, and stops one short of
        killing itself.

        That is deliberate rather than a degenerate case. Such a feature is a
        trade the stat block offers - the Elemental buys the whole party going
        Vulnerable with a slice of its own life - and a GM would take it early,
        when there is still a fight left to win with it.
        """
        return self.hp_unmarked - amount >= 1

    def spend_stress(self, amount: int = 1) -> bool:
        """Pay a feature's Stress cost; return whether it went through."""
        if not self.can_spend_stress(amount):
            return False
        self.stress_marked += amount
        return True

    @property
    def is_vulnerable(self) -> bool:
        """Adversaries are never Vulnerable of their own accord.

        A PC becomes Vulnerable by marking their last Stress; nothing in the SRD
        does that to an adversary, so the only route here is content applying the
        condition, which `FightState.is_vulnerable` asks about separately. This
        exists so both sides answer the same question rather than the caller
        having to know which kind of combatant it is holding.
        """
        return False

    def take_damage(
        self, amount: int, fight=None, direct: bool = False, damage_type=None
    ) -> int:
        """Mark HP per the SRD's Damage Thresholds rule; return the HP marked.

        Same rule, and same threshold-to-HP-marked math, as
        PlayerCharacter.take_damage - dice/damage.py's own docstring notes
        damage resolution is shared by PCs and adversaries alike. Duplicated
        here rather than factored into a shared base class for now; revisit
        if a third caller needs the same logic.

        The two damage-response hooks are consulted in the same order the PC
        side uses them: softening first, then hardening, so content that fires
        "when this adversary marks HP" is measured against what the hit finally
        cost. Adversaries mark no Armor Slots - they have none - so there is no
        equivalent of the PC's free slot before either.

        `fight` is passed through to both, the way a PC's is, for content whose
        effect only exists for the length of a fight.

        `direct` is accepted and ignored: direct damage means no Armor Slot may
        be marked against it, and adversaries have no Armor Slots to begin with.
        It's in the signature so both sides satisfy one Target protocol.

        `damage_type` is consulted first and works exactly as it does for a PC -
        halved for a resistance, gone for an immunity, and before the thresholds
        either way. This is the side that currently has content for it: the Minor
        Chaos Elemental's `Arcane Form` is resistant to magic damage, so what a
        party's spellcasters are carrying starts to matter.
        """
        # Resolved once and carried, exactly as `PlayerCharacter.take_damage`
        # does: the type answers the resistance and is then handed to the two
        # damage-response hooks, where the Construct's physical-only Weak
        # Structure reads it.
        kind = damage_type_named(damage_type)

        amount = reduced(amount, resistance_to(self, kind, fight))
        if amount <= 0:
            hp_to_mark = 0
        elif amount >= self.severe_threshold:
            hp_to_mark = 3
        elif amount >= self.major_threshold:
            hp_to_mark = 2
        else:
            hp_to_mark = 1

        hp_to_mark = soften_damage(self, amount, hp_to_mark, fight, kind)
        hp_to_mark = harden_damage(self, amount, hp_to_mark, fight, kind)

        self.mark_hp(hp_to_mark)

        # Fired last, with the marking settled, so content keyed on "marks their
        # last HP" sees an adversary that is already down - which is what the
        # Construct's Death Quake needs to be true.
        apply_on_damaged(self, amount, hp_to_mark, fight)

        # An adversary that has just died takes its holds with it. A condition
        # whose only printed way out is something happening to *this* adversary -
        # the Green Ooze's Envelop ends when the Ooze takes Severe damage - can
        # never end once it is off the field, and the Ooze's own thresholds mean
        # two Major hits kill it without a Severe one ever landing. Asked
        # generically; nothing here knows which conditions those are, or that any
        # exist. See `FightState.release_conditions_from` for what is spared.
        if fight is not None and self.is_defeated:
            fight.release_conditions_from(self)
        return hp_to_mark
