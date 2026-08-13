"""A worked example of an encounter definition - three Bandits and a Sniper.

Adversaries are named as the book names them and resolved by the registry, so
this file has no idea which module their stat blocks live in.

The Sniper is deliberately shown with overrides applied: as printed it has
Thresholds 4/7 and HP 3, which makes it fold to almost any hit. Bumping its HP
and damage is the kind of tuning this module exists for, and keeping it here
means the definition in adversaries/srd.py still matches the book.

Also a worked example of a *variation*. Running the two side by side -

    python -m simulation "Roadside Ambush" "Roadside Ambush (Softened)" --seed 7

- is the workflow the whole tool is for: same party, same dice, one knob moved,
and a comparison table saying what the knob did. Variations live here as their
own literals rather than being assembled on the command line, so a run from
last week can be repeated exactly and the numbers that produced a decision are
still readable next to the decision.
"""

from encounters.encounter import CHARACTERS_DIR, Encounter, Group

PARTY = [CHARACTERS_DIR / "example_character.json"]

ROADSIDE_AMBUSH = Encounter(
    name="Roadside Ambush",
    party=PARTY,
    groups=[
        Group("Jagged Knife Bandit", count=3),
        Group("Jagged Knife Sniper", count=1, hp_max=5, damage_modifier=4),
    ],
)

# The same ambush with the pressure taken off: one fewer Bandit, and the Sniper
# left exactly as the book prints it. Four adversaries against a single tier 1
# PC is a losing fight by a wide margin, so this is the obvious first thing to
# try - and having both defined makes "how much did that actually help?" a
# question with a number rather than an opinion.
ROADSIDE_AMBUSH_SOFTENED = Encounter(
    name="Roadside Ambush (Softened)",
    party=PARTY,
    groups=[
        Group("Jagged Knife Bandit", count=2),
        Group("Jagged Knife Sniper", count=1),
    ],
)
