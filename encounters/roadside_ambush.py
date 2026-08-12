"""A worked example of an encounter definition - three Bandits and a Sniper.

The Sniper is deliberately shown with overrides applied: as printed it has
Thresholds 4/7 and HP 3, which makes it fold to almost any hit. Bumping its HP
and damage is the kind of tuning this module exists for, and keeping it here
means adversaries/jagged_knife.py still matches the book.
"""

from adversaries.jagged_knife import JAGGED_KNIFE_BANDIT, JAGGED_KNIFE_SNIPER
from encounters.encounter import CHARACTERS_DIR, Encounter, Group

ROADSIDE_AMBUSH = Encounter(
    name="Roadside Ambush",
    party=[CHARACTERS_DIR / "example_character.json"],
    groups=[
        Group(JAGGED_KNIFE_BANDIT, count=3),
        Group(JAGGED_KNIFE_SNIPER, count=1, hp_max=5, damage_modifier=4),
    ],
)
