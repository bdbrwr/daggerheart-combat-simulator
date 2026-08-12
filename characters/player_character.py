"""Player character state - loaded from characters/*.json, then mutated over the course of a simulated fight.

Unlike the roll-result dataclasses in dice/, PlayerCharacter is NOT frozen:HP, Stress, Hope, and Armor Slots all change turn to turn during combat, and an instance of this class is where that state lives for the length of a fight. The values loaded from JSON are just the starting point.

Death/downfall (unconsciousness, death moves) is deliberately not modeled here yet - marking the last HP slot triggers SRD rules this module doesn't implement, so don't infer death from hp_marked == hp_max until that's beenlooked up and built on purpose.
"""

import json
from dataclasses import dataclass
from pathlib import Path


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

    hp_marked: int = 0
    stress_marked: int = 0
    hope_marked: int = 0
    armor_marked: int = 0

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
            traits=data["traits"],
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
        self.stress_marked = min(self.stress_marked + amount, self.stress_max)

    def clear_stress(self, amount: int) -> None:
        self.stress_marked = max(self.stress_marked - amount, 0)

    def mark_armor_slot(self, amount: int) -> None:
        self.armor_marked = min(self.armor_marked + amount, self.armor_max)

    def clear_armor_slot(self, amount: int) -> None:
        self.armor_marked = max(self.armor_marked - amount, 0)

    def gain_hope(self, amount: int) -> None:
        self.hope_marked = min(self.hope_marked + amount, self.hope_max)

    def spend_hope(self, amount: int) -> None:
        self.hope_marked = max(self.hope_marked - amount, 0)

    def take_damage(self, amount: int) -> int:
        """Mark HP per the SRD's Damage Thresholds rule; return the HP marked.

        <=0 damage: mark nothing. Below Major threshold: mark 1. At/above
        Major: mark 2. At/above Severe: mark 3.

        Massive Damage (an SRD-optional rule: 2x Severe marks 4 instead of 3)
        is NOT implemented here. Marking an Armor Slot to reduce severity is
        a choice made by the caller before this runs, not handled here -
        this function only does the threshold math.
        """
        if amount <= 0:
            hp_to_mark = 0
        elif amount >= self.severe_threshold:
            hp_to_mark = 3
        elif amount >= self.major_threshold:
            hp_to_mark = 2
        else:
            hp_to_mark = 1
        self.mark_hp(hp_to_mark)
        return hp_to_mark
