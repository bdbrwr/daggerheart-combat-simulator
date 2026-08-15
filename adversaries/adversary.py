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
from content.aoe import targets_hit
from content.registry import (
    apply_on_damaged,
    deals_direct_damage,
    force_adversary_reroll,
    harden_damage,
    soften_damage,
    total_damage_bonus,
)
from dice.common import AdvantageState
from dice.d20 import roll_d20
from dice.damage import DiceGroup, roll_damage


class Target(Protocol):
    """Anything an adversary's attack can target - a PC, for now."""

    evasion: int

    # Read by nothing here, but handed to the party's forced-reroll content: how
    # close the target is to going down is what decides whether stopping an
    # ordinary hit is worth paying for.
    is_near_death: bool

    def take_damage(self, amount: int, fight=None, direct: bool = False) -> int: ...


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

    def spawn(self, **overrides) -> "Adversary":
        """An independent copy at starting state, with any stat overrides applied.

        One definition can back several combatants in the same fight, so each
        one needs its own HP/Stress to mark and its own damage_dice list.
        Overrides are how an encounter tunes a stat block without touching the
        definition - `JAGGED_KNIFE_BANDIT.spawn(hp_max=7, damage_modifier=3)`.
        """
        changes = {
            "damage_dice": list(self.damage_dice),
            "features": list(self.features),
            "hp_marked": 0,
            "stress_marked": 0,
        }
        changes.update(overrides)
        return replace(self, **changes)

    def _damage_for(self, dice, modifier, is_critical, target, fight):
        """Roll this attack's damage, letting content add to it first.

        `dice`/`modifier` default to the stat block's, so a feature that hits
        with something other than the printed attack - the Bear's Bite at
        3d4+10 - passes its own rather than reimplementing the roll.

        `total_damage_bonus` is asked here, which is "before rolling damage" and
        after the hit is known, exactly where the Construct's Overload wants to
        be offered its Stress.
        """
        bonus = total_damage_bonus(self, target, fight) if fight is not None else 0
        return roll_damage(
            dice_groups=self.damage_dice if dice is None else dice,
            modifier=(self.damage_modifier if modifier is None else modifier) + bonus,
            is_critical=is_critical,
        )

    def area_attack(
        self,
        targets: list,
        advantage_state: AdvantageState = AdvantageState.NONE,
        fight=None,
        damage_dice=None,
        damage_modifier=None,
        direct: bool | None = None,
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
            damage_dice, damage_modifier, attack_roll.is_critical, struck[0], fight
        )
        # Unstated means "whatever this adversary's features say", so Bone
        # Breaker reaches a swept attack the same way it reaches a single one.
        if direct is None:
            direct = deals_direct_damage(self, fight)

        marked = 0
        for target in struck:
            marked += target.take_damage(damage_roll.total, fight, direct=direct)

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

        def swing():
            return roll_d20(
                modifier=self.attack_modifier,
                evasion=target.evasion,
                advantage_state=advantage_state,
            )

        # Asked before anything reads the roll, so a forced reroll is
        # indistinguishable from the adversary having rolled that way first.
        attack_roll = force_adversary_reroll(self, target, swing(), swing, fight)

        if not attack_roll.is_success:
            return AttackResult(attack_roll=attack_roll, damage_roll=None)

        damage_roll = self._damage_for(
            damage_dice, damage_modifier, attack_roll.is_critical, target, fight
        )
        # Whether this attack is direct - no Armor Slot may be marked against it -
        # is a question for the attacker's features, asked generically. Nothing
        # here knows that the Cave Ogre's Bone Breaker is what answers it.
        marked = target.take_damage(
            damage_roll.total, fight, direct=deals_direct_damage(self, fight)
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

    def take_damage(self, amount: int, fight=None, direct: bool = False) -> int:
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
        """
        if amount <= 0:
            hp_to_mark = 0
        elif amount >= self.severe_threshold:
            hp_to_mark = 3
        elif amount >= self.major_threshold:
            hp_to_mark = 2
        else:
            hp_to_mark = 1

        hp_to_mark = soften_damage(self, amount, hp_to_mark, fight)
        hp_to_mark = harden_damage(self, amount, hp_to_mark, fight)

        self.mark_hp(hp_to_mark)

        # Fired last, with the marking settled, so content keyed on "marks their
        # last HP" sees an adversary that is already down - which is what the
        # Construct's Death Quake needs to be true.
        apply_on_damaged(self, amount, hp_to_mark, fight)
        return hp_to_mark
