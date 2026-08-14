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

from content import soften_damage


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

    # Set by a death move rather than loaded from JSON: a character sheet
    # describes a PC walking into a fight, not one already down in it.
    unconscious: bool = False
    scars: int = 0

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
            self._mark_hp_with_death_check(1)

    def clear_stress(self, amount: int) -> None:
        self.stress_marked = max(self.stress_marked - amount, 0)

    def can_spend_stress(self, amount: int = 1) -> bool:
        """Whether a move costing `amount` Stress is available at all.

        Per the SRD a character can't use a move that requires marking Stress
        if all of their Stress is marked. Unlike forced Stress, this never
        converts to HP - the move is simply off the table.
        """
        return self.stress_marked + amount <= self.stress_max

    def spend_stress(self, amount: int = 1) -> bool:
        """Pay a voluntary Stress cost; return whether it went through."""
        if not self.can_spend_stress(amount):
            return False
        self.stress_marked += amount
        return True

    def mark_armor_slot(self, amount: int) -> None:
        self.armor_marked = min(self.armor_marked + amount, self.armor_max)

    def clear_armor_slot(self, amount: int) -> None:
        self.armor_marked = max(self.armor_marked - amount, 0)

    def gain_hope(self, amount: int) -> None:
        self.hope_marked = min(self.hope_marked + amount, self.hope_max)

    def can_spend_hope(self, amount: int = 1) -> bool:
        """Whether there's enough Hope banked to pay `amount`.

        Separate from spend_hope, which clamps rather than refusing - content
        that costs Hope has to check first, the same way spend_stress refuses a
        cost it can't cover.
        """
        return self.hope_marked >= amount

    def spend_hope(self, amount: int) -> None:
        self.hope_marked = max(self.hope_marked - amount, 0)

    @property
    def named_features(self) -> list[str]:
        """Everything this sheet names that game content could implement.

        The input to the coverage report: each of these is either modelled,
        assessed as having no combat effect, or unimplemented, and a reader of a
        win rate deserves to know which.

        Ancestry, community, class and subclass go in as single names, which is
        coarse - a class is really a bundle of features - but it's honest, since
        an undeclared class name reports as unimplemented until someone splits
        it up and declares the parts.
        """
        return [
            self.ancestry,
            self.community,
            self.character_class,
            self.subclass,
            *self.domain_cards_loadout,
        ]

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

        Massive Damage (an SRD-optional rule: 2x Severe marks 4 instead of 3)
        and damage-type resistance are NOT implemented.
        """
        if amount >= self.severe_threshold:
            return 3
        if amount >= self.major_threshold:
            return 2
        return 1

    def take_damage(self, amount: int, fight=None) -> int:
        """Mark HP per the SRD's Damage Thresholds rule; return the HP marked.

        <=0 damage: mark nothing, and no slot is spent on a hit that wasn't
        going to land anyway. Otherwise the severity is worked out from the
        thresholds, then softened twice over: a free Armor Slot is always
        marked to drop it by one, and any damage-response domain card in the
        loadout gets its say. Both floor at zero.

        Armor goes first so a card is never asked to spend a resource on a hit
        the free slot already absorbed.

        `fight` is passed straight through to the damage responses, which is the
        only way content whose effect lasts a single fight (Unstoppable) can
        tell whether it's currently running. It's optional: damage resolves the
        same way without one, with such content simply declining.

        Marking the last HP triggers Avoid Death.
        """
        if amount <= 0:
            return 0

        hp_to_mark = self.severity_of(amount)

        if self.should_mark_armor_slot():
            self.mark_armor_slot(1)
            hp_to_mark = max(hp_to_mark - 1, 0)

        hp_to_mark = soften_damage(self, amount, hp_to_mark, fight)

        self._mark_hp_with_death_check(hp_to_mark)
        return hp_to_mark

    def _mark_hp_with_death_check(self, amount: int) -> None:
        """Mark HP and take the death move if that was the last of it."""
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
        if random.randint(1, 12) > self.level:
            return False
        self.scars += 1
        self.hope_max = max(self.hope_max - 1, 0)
        self.hope_marked = min(self.hope_marked, self.hope_max)
        return True
