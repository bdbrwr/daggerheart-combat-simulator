"""Player character state - loaded from characters/*.json, then mutated over the course of a simulated fight.

Unlike the roll-result dataclasses in dice/, PlayerCharacter is NOT frozen:HP, Stress, Hope, and Armor Slots all change turn to turn during combat, and an instance of this class is where that state lives for the length of a fight. The values loaded from JSON are just the starting point.

Marking the last HP slot now triggers a death move. Simulated PCs always take
Avoid Death - it's the safest choice and the only one that leaves a fight
recoverable - so `take_damage` applies it automatically rather than asking a
policy which move to make. Blaze of Glory and Risk It All are not modeled.

An unconscious PC can't act and can't be targeted, and per the SRD only comes
back when an ally clears one of their marked HP. Nothing in the simulator
heals a downed PC yet, so in practice going unconscious removes a PC for the
rest of the fight; `clear_hp` deliberately does NOT wake them, because the
decision to spend a turn reviving someone isn't modeled and inferring it from
a stray heal would quietly change fight outcomes.
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path

from content import (
    apply_on_damaged,
    harden_damage,
    party_damage_reduction,
    resistance_to,
    soften_damage,
)
from content.damage_types import damage_type_named, reduced
from items.registry import find_armor, find_weapon

# How little unmarked HP counts as being on the edge.
#
# It started as a reporting threshold - `simulation/summary.py` reads it for the
# near-death rate - and it is now also a trigger content keys on, since the
# Wizard's Not This Time steps in for a PC who is one hit from the floor. Both
# are asking the same question, so both read the same number rather than each
# picking one: two HP is roughly one solid hit from unconsciousness for a tier 1
# PC. It lives here because it is a fact about a PC's HP, and because content in
# features/ can reach a character but not the simulation layer.
NEAR_DEATH_HP_UNMARKED = 2


@dataclass
class PlayerCharacter:
    """A PC's starting stats plus whatever HP/Stress/Hope/Armor Slots have
    been marked so far in the current simulated fight."""

    name: str
    level: int
    character_class: str
    subclass: str
    ancestry: str
    community: str

    traits: dict[str, int]
    evasion: int
    proficiency: int

    major_threshold: int
    severe_threshold: int

    hp_max: int
    stress_max: int
    hope_max: int
    armor_max: int

    primary_weapon: str
    secondary_weapon: str | None
    armor_item: str

    domain_cards_loadout: list[str]
    domain_cards_vault: list[str]
    experiences: list[dict]
    consumables: list[dict]

    # Organisational only - which campaign this PC belongs to. Never read by
    # the fight loop; useful for telling four sheets apart in a report.
    campaign: str = ""

    # Which trait this PC's Spellcast Rolls use, as a key into `traits`. It
    # comes from the subclass, but can be reflavoured to a different trait, so
    # it's genuinely per-character rather than derivable - which is why it sits
    # on the sheet as an already-resolved value, the way thresholds and Evasion
    # do. Blank means this PC makes no Spellcast Rolls: content that needs one
    # declines rather than guessing a trait.
    spellcast_trait: str = ""

    # Things on this sheet the simulator knowingly ignores, by the name the
    # sheet writes them under: {"Wyrmscale Halfplate": "Homebrew. Armor Score
    # and thresholds are already resolved into the numbers above."}
    #
    # This is for the *per-character* case - homebrew gear, mostly - where the
    # thing exists on one sheet and nowhere else. Content shared across
    # characters (domain cards, ancestries, communities) is declared in its own
    # module via content/registry.py instead of being repeated in every sheet
    # that carries it. Both end up in the coverage report.
    not_modelled: dict[str, str] = field(default_factory=dict)

    hp_marked: int = 0
    stress_marked: int = 0
    hope_marked: int = 0
    armor_marked: int = 0

    # What this PC's Hope did over a fight, rather than only what was left of it
    # at the end. Counted as it actually lands, the way the Fear pool counts
    # itself: Hope offered past the cap never arrives and is not counted gained,
    # and a cost bigger than the bank spends only what was there.
    hope_gained: int = 0
    hope_spent: int = 0

    # Set by a death move rather than loaded from JSON: a character sheet
    # describes a PC walking into a fight, not one already down in it.
    unconscious: bool = False
    scars: int = 0

    # How many times this PC has made a death move. Counted separately from
    # `scars` because a death move is the event and a scar is one possible
    # outcome of it - a PC can go down without scarring, and reporting only
    # scars would undercount how often the fight went badly wrong.
    death_moves: int = 0

    # The Hope banked when this PC walked into the fight. Never passed in - it's
    # read off `hope_marked` at construction, which is exactly what a sheet's
    # starting state is - but recorded rather than derived from the counters
    # above, because a scar crosses out a filled Hope slot and that loss is
    # neither a gain nor a spend.
    hope_at_start: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self.hope_at_start = self.hope_marked

    @classmethod
    def from_json(cls, path: str | Path) -> "PlayerCharacter":
        """Build a PlayerCharacter at its starting state from a characters/*.json file."""
        data = json.loads(Path(path).read_text())
        return cls(
            name=data["name"],
            level=data["level"],
            character_class=data["class"],
            subclass=data["subclass"],
            ancestry=data["ancestry"],
            community=data["community"],
            # Trait keys are lowercased for the same reason spellcast_trait is:
            # a sheet writing "Agility" would otherwise miss every lookup, and
            # content that can't find its trait declines silently rather than
            # failing.
            traits={trait.strip().lower(): value for trait, value in data["traits"].items()},
            evasion=data["evasion"],
            proficiency=data["proficiency"],
            major_threshold=data["thresholds"]["major"],
            severe_threshold=data["thresholds"]["severe"],
            hp_max=data["hp"]["max"],
            stress_max=data["stress"]["max"],
            hope_max=data["hope"]["max"],
            armor_max=data["armor"]["max"],
            primary_weapon=data["equipment"]["primary_weapon"],
            secondary_weapon=data["equipment"]["secondary_weapon"],
            armor_item=data["equipment"]["armor"],
            domain_cards_loadout=data["domain_cards"]["loadout"],
            domain_cards_vault=data["domain_cards"]["vault"],
            experiences=data["experiences"],
            consumables=data["consumables"],
            # Optional, so older sheets without them still load.
            campaign=data.get("campaign", ""),
            # Lowercased to match the `traits` keys: sheets write "Agility",
            # traits are keyed "agility", and a mismatch would silently make
            # every Spellcast Roll decline rather than fail loudly.
            spellcast_trait=data.get("spellcast_trait", "").strip().lower(),
            not_modelled=data.get("not_modelled", {}),
            hp_marked=data["hp"]["marked"],
            stress_marked=data["stress"]["marked"],
            hope_marked=data["hope"]["marked"],
            armor_marked=data["armor"]["marked"],
        )

    def mark_hp(self, amount: int) -> None:
        self.hp_marked = min(self.hp_marked + amount, self.hp_max)

    def clear_hp(self, amount: int) -> None:
        self.hp_marked = max(self.hp_marked - amount, 0)

    def mark_stress(self, amount: int) -> None:
        """Mark Stress this PC is being *forced* to take.

        Per the SRD: "When a character must mark 1 or more Stress but can't,
        they mark 1 HP instead." One HP for the whole unmarkable requirement,
        not one per Stress that wouldn't fit - and that HP can be the last one,
        so it goes through the same death check damage does.

        For a *voluntary* cost - a domain card that says "mark a Stress" - use
        spend_stress() instead. The SRD treats the two differently: a move
        requiring Stress simply can't be used when Stress is full, and must
        never fall through to HP.
        """
        free = self.stress_max - self.stress_marked
        self.stress_marked = min(self.stress_marked + amount, self.stress_max)
        if amount > free:
            self.mark_hp_and_check_death(1)

    def clear_stress(self, amount: int) -> None:
        self.stress_marked = max(self.stress_marked - amount, 0)

    def can_spend_stress(self, amount: int = 1) -> bool:
        """Whether a move costing `amount` Stress is available at all.

        Per the SRD a character can't use a move that requires marking Stress
        if all of their Stress is marked. Unlike forced Stress, this never
        converts to HP - the move is simply off the table.
        """
        return self.stress_marked + amount <= self.stress_max

    def will_spend_stress(self, amount: int = 1) -> bool:
        """Whether this PC would *choose* to pay a Stress cost, not just whether
        they can.

        SIMULATION RULE - policy, ruled by the user. `can_spend_stress` answers
        whether the slots exist; this answers whether a player would spend them:

            freely, **except the last slot**, which is only marked once the PC
            is at 2 or fewer unmarked HP.

        Marking the last Stress is a cliff rather than an empty resource. It
        makes the PC Vulnerable - Advantage on every roll against them, per the
        SRD - and it also shuts off every other card that costs a Stress, which
        for a loadout built around them is most of what the character does. So it
        is held back until the PC is close enough to the floor that the immediate
        problem outweighs both.

        `is_near_death` is the same line the near-death rate is reported at and
        the same one `Adversary.will_spend_stress` draws for an adversary's last
        slot, so both sides of the table hold their last Stress until the same
        point. One number, read in one place, rather than three that could drift.

        A cost of several slots is measured at the last one it would mark, since
        that is the one that has to be worth paying.

        Content asks the *holder*, never re-deriving this: the two sides answer
        differently (an adversary follows a desperation curve) and the caller
        should not have to know which kind of combatant it is holding.
        """
        if not self.can_spend_stress(amount):
            return False
        if self.stress_marked + amount < self.stress_max:
            return True
        return self.is_near_death

    def spend_stress(self, amount: int = 1) -> bool:
        """Pay a voluntary Stress cost; return whether it went through.

        Deliberately *not* gated on `will_spend_stress`: this is the payment, and
        whether the PC wants to make it is the caller's decision. Content that
        should hold the last slot back asks first.
        """
        if not self.can_spend_stress(amount):
            return False
        self.stress_marked += amount
        return True

    def mark_armor_slot(self, amount: int) -> None:
        self.armor_marked = min(self.armor_marked + amount, self.armor_max)

    def clear_armor_slot(self, amount: int) -> None:
        self.armor_marked = max(self.armor_marked - amount, 0)

    def gain_hope(self, amount: int) -> None:
        """Bank Hope up to the cap; Hope offered past it is simply lost.

        Only what actually lands is counted as gained, which is how the Fear
        pool counts itself too - so the four figures a report shows (start,
        gained, spent, what's left) reconcile.
        """
        gained = min(amount, self.hope_max - self.hope_marked)
        if gained <= 0:
            return
        self.hope_marked += gained
        self.hope_gained += gained

    def can_spend_hope(self, amount: int = 1) -> bool:
        """Whether there's enough Hope banked to pay `amount`.

        Separate from spend_hope, which clamps rather than refusing - content
        that costs Hope has to check first, the same way spend_stress refuses a
        cost it can't cover.
        """
        return self.hope_marked >= amount

    def spend_hope(self, amount: int) -> None:
        """Pay a Hope cost, clamped at nothing; only what was there is spent."""
        spent = min(amount, self.hope_marked)
        self.hope_marked -= spent
        self.hope_spent += spent

    @property
    def armor_features(self) -> list[str]:
        """The features of the armor this PC is wearing, namespaced.

        Scoped to the wearer, so these belong in `named_features` and dispatch
        finds them exactly the way it finds a domain card's - Fortified changes
        what any hit costs, Painful charges for any slot marked. Contrast
        `weapon_features`, which are scoped to the weapon instead.

        An armor nobody has catalogued reports under its own name rather than
        being skipped, so it shows up as *unimplemented* instead of silently
        contributing nothing. A sheet carries its Armor Score and thresholds
        already resolved, so an uncatalogued armor costs a fight nothing - but
        "costs nothing" and "nobody has looked at it" are exactly the two things
        this project refuses to let look alike.
        """
        armor = find_armor(self.armor_item) if self.armor_item else None
        if armor is None:
            return [self.armor_item] if self.armor_item else []
        return armor.named_features

    @property
    def weapon_features(self) -> list[str]:
        """The features of the weapon this PC carries, namespaced.

        Deliberately *not* part of `named_features`. A weapon's feature applies
        to attacks made with that weapon, not to everything its holder does, so
        letting dispatch scan it holder-wide would quietly add a Broadsword's
        Reliable to a Grimoire spell. items/weapons.py passes these to dispatch
        itself, scoped to the swing being made.

        They still reach the coverage report through `assessed_features`,
        because a weapon feature nobody has written is a real gap and has to be
        visible.
        """
        return find_weapon(self.primary_weapon).named_features if self.primary_weapon else []

    @property
    def weapon_damage_type(self) -> str:
        """The damage type of the weapon this PC swings, or "" if they carry none.

        Here for the same reason `weapon_features` is: content that **reuses an
        attack the weapon already made** has to type what it deals, and the
        weapon is what typed the original. Whirlwind's splash and Hold Them Off's
        two extra targets are both that shape - the same damage roll landing on
        somebody else, so the same type.

        Content that rolls damage of its own says so itself and never reads this;
        a Grimoire spell is magic whatever the caster is holding.
        """
        return find_weapon(self.primary_weapon).damage_type if self.primary_weapon else ""

    @property
    def named_features(self) -> list[str]:
        """Everything this PC carries that applies to whatever they do.

        The list dispatch scans. Ancestry, community, class and subclass go in as
        single names, which is coarse - a class is really a bundle of features -
        but it's honest, since an undeclared class name reports as unimplemented
        until someone splits it up and declares the parts.
        """
        return [
            self.ancestry,
            self.community,
            self.character_class,
            self.subclass,
            *self.domain_cards_loadout,
            *self.armor_features,
        ]

    @property
    def assessed_features(self) -> list[str]:
        """Everything about this PC the coverage report should account for.

        A superset of `named_features`, because coverage and dispatch are asking
        different questions. Dispatch asks "what applies to this character?" -
        which a weapon's feature does not, since it belongs to the weapon.
        Coverage asks "how much of this character does the simulator run?", and a
        weapon feature nobody has implemented is missing from the fight whether
        or not it is holder-scoped.
        """
        return [*self.named_features, *self.weapon_features]

    @property
    def is_conscious(self) -> bool:
        """False once a death move has put this PC down.

        Unconscious PCs neither act nor can be targeted, so both the spotlight
        and adversary targeting filter on this.
        """
        return not self.unconscious

    @property
    def is_vulnerable(self) -> bool:
        """True once the last Stress is marked - all rolls against them have Advantage."""
        return self.stress_marked >= self.stress_max

    @property
    def hp_unmarked(self) -> int:
        """HP not yet marked - the exact inverse of `hp_marked`.

        Named for the SRD's own vocabulary: damage *marks* HP, so "unmarked" is
        the unambiguous term and "remaining" was ours. Both directions are kept
        because content asks in both - "have I been hit at all?" reads off
        `hp_marked`, "would this drop me?" off this one.
        """
        return self.hp_max - self.hp_marked

    @property
    def is_near_death(self) -> bool:
        """One solid hit from the floor - `NEAR_DEATH_HP_UNMARKED` unmarked or less.

        Content asks this to decide whether a PC is worth spending something
        expensive on. It is true of an unconscious PC too, who has every HP
        marked, but nothing consults it about one: an unconscious PC can't be
        targeted, so no attack is ever aimed at them to answer for.
        """
        return self.hp_unmarked <= NEAR_DEATH_HP_UNMARKED

    @property
    def stress_unmarked(self) -> int:
        """Stress slots still free - the inverse of `stress_marked`.

        Same vocabulary as HP, and for the same reason: the game marks a track,
        so "unmarked" is the unambiguous word for what's left. Reaching zero is
        what makes a PC Vulnerable, which is why it's worth reporting.
        """
        return self.stress_max - self.stress_marked

    @property
    def armor_unmarked(self) -> int:
        """Armor Slots still free - the inverse of `armor_marked`."""
        return self.armor_max - self.armor_marked

    def should_mark_armor_slot(self) -> bool:
        """Whether to spend an Armor Slot against incoming damage.

        Marking armor is reactive - it happens as damage lands, never as a
        turn's action - so the decision lives here rather than in a PC's
        action policy.

        The rule is unconditional: if a slot is free, mark it and mark one
        less HP. That includes a hit that would only have marked a single HP,
        which then costs the PC nothing but the slot.
        """
        return self.armor_marked < self.armor_max

    def severity_of(self, amount: int) -> int:
        """The HP `amount` marks on its own, before armor or any card softens it.

        Below Major threshold: 1. At/above Major: 2. At/above Severe: 3.

        `amount` is expected to have been through any resistance already -
        `take_damage` halves before it gets here, which is what the SRD's "before
        comparing it to their Hit Point Thresholds" requires.

        Massive Damage (an SRD-optional rule: 2x Severe marks 4 instead of 3) is
        NOT implemented.
        """
        if amount >= self.severe_threshold:
            return 3
        if amount >= self.major_threshold:
            return 2
        return 1

    def take_damage(
        self, amount: int, fight=None, direct: bool = False, damage_type=None
    ) -> int:
        """Mark HP per the SRD's Damage Thresholds rule; return the HP marked.

        <=0 damage: mark nothing, and no slot is spent on a hit that wasn't
        going to land anyway. Otherwise the severity is worked out from the
        thresholds, then softened twice over: a free Armor Slot is always
        marked to drop it by one, and any damage-response domain card in the
        loadout gets its say. Both floor at zero.

        `damage_type` is the SRD's physical or magic, and it is the **first**
        thing consulted: a resistance halves the number and an immunity zeroes it
        *before* the thresholds see it, which is what the SRD says outright and
        what makes resistance change how many HP a hit marks rather than only the
        figure rolled. Armor comes after, in the SRD's own order. Damage arriving
        with no type is never reduced - see `content/damage_types.py`.

        Armor goes first so a card is never asked to spend a resource on a hit
        the free slot already absorbed. Content that *worsens* a hit is asked
        last, through `harden_damage`, so that "when you mark HP" is measured
        against what the hit finally costs rather than what it started at.
        Nothing on the PC side registers there yet; the call is here so both
        sides of the table run the same pipeline.

        `fight` is passed straight through to the damage responses, which is the
        only way content whose effect lasts a single fight (Unstoppable) can
        tell whether it's currently running. It's optional: damage resolves the
        same way without one, with such content simply declining.

        `direct` is the SRD's direct damage: **no Armor Slot may be marked
        against it**, so it costs HP and nothing else. Thresholds still decide how
        many, and damage responses still get their say - only the free slot is
        skipped. Against this party that is worth roughly a whole HP on every
        such hit, since the policy marks a slot against everything otherwise.

        Marking the last HP triggers Avoid Death.
        """
        # Resolved once, and then carried: the type decides the resistance here
        # and is handed to the two damage-response hooks below, several of whose
        # registrants are restricted to one type on the page (Iron Will,
        # Unstoppable). Parsing it twice would be two chances to disagree.
        kind = damage_type_named(damage_type)

        amount = reduced(amount, resistance_to(self, kind, fight))

        # Party content that subtracts from the number itself - Arcana's Rune
        # Ward takes 1d8 off. After the resistance, which the SRD fixes as the
        # first thing to happen, and before the thresholds, which is what lets a
        # ward drop a hit a whole band or take it away entirely. Asked
        # generically; nothing here knows what a ward is.
        amount = max(amount - party_damage_reduction(self, amount, fight, kind), 0)

        if amount <= 0:
            return 0

        hp_to_mark = self.severity_of(amount)

        if not direct and self.should_mark_armor_slot():
            self.mark_armor_slot(1)
            hp_to_mark = max(hp_to_mark - 1, 0)

        hp_to_mark = soften_damage(self, amount, hp_to_mark, fight, kind)
        hp_to_mark = harden_damage(self, amount, hp_to_mark, fight, kind)

        self.mark_hp_and_check_death(hp_to_mark)
        apply_on_damaged(self, amount, hp_to_mark, fight)
        return hp_to_mark

    def mark_hp_and_check_death(self, amount: int) -> None:
        """Mark HP and take the death move if that was the last of it.

        Public because HP gets marked by things that aren't damage: Stress that
        won't fit, and features that say "mark an additional HP" outright, like
        the Acid Burrower's Spit Acid. All of them have to be able to be the last
        HP, so none of them may use the raw `mark_hp`.
        """
        self.mark_hp(amount)
        if self.hp_marked >= self.hp_max and not self.unconscious:
            self.avoid_death()

    def avoid_death(self) -> bool:
        """Take the Avoid Death death move; return whether it left a scar.

        Drops the PC unconscious, then rolls the Hope Die (a d12): on a result
        at or below the PC's level they gain a scar, which permanently crosses
        out a Hope slot. Scars barely bite inside a single fight - a level 1 PC
        scars one time in twelve - but they're counted and reported, since how
        often a party walks away marked is part of what an encounter costs.
        """
        self.unconscious = True
        self.death_moves += 1
        if random.randint(1, 12) > self.level:
            return False
        self.scars += 1
        self.hope_max = max(self.hope_max - 1, 0)
        # A scar crosses out a Hope slot, and a banked Hope sitting in it goes
        # with it. That is neither gained nor spent, so it isn't counted as
        # either - which is the one case where a Hope report's four figures
        # don't add up, and the report says so.
        self.hope_marked = min(self.hope_marked, self.hope_max)
        return True
