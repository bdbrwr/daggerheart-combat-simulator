"""A worked example of an encounter definition - three Bandits and a Sniper.

Adversaries are named as the book names them and resolved by the registry, so
this file has no idea which module their stat blocks live in.

The Sniper is deliberately shown with overrides applied: as printed it has
Thresholds 4/7 and HP 3, which makes it fold to almost any hit. Bumping its HP
and damage is the kind of tuning this module exists for, and keeping it here
means the definition in adversaries/srd.py still matches the book.
"""

from encounters.encounter import CHARACTERS_DIR, Encounter, Group

ROADSIDE_AMBUSH = Encounter(
    name="Roadside Ambush",
    party=[CHARACTERS_DIR / "example_character.json"],
    groups=[
        Group("Jagged Knife Bandit", count=3),
        Group("Jagged Knife Sniper", count=1, hp_max=5, damage_modifier=4),
    ],
)
