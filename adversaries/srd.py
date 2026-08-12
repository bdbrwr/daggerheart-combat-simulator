"""Adversaries as printed in the Daggerheart SRD.

One module per publication: this file is the SRD, homebrew.py is ours, and a
purchased adventure or supplement gets its own module named after it. What a
stat block was published in is the one thing about it that never changes, so
it's what the filing goes on.

Definitions here match the book exactly and are sorted by name. Per-encounter
tuning belongs in encounters/, never here - an encounter overrides a copy, so
these stay checkable against the printed page.

Nothing imports from this module by path. The registry collects every
Adversary defined in this package and keys it by name, so encounters ask for
"Jagged Knife Bandit" and don't care which module it lives in.

Features that aren't part of a standard attack roll aren't modeled - noted per
adversary for debugging, not implemented.
"""

from adversaries.adversary import Adversary
from dice.damage import DiceGroup

# Tier 1 Standard. Daggers: melee, 1d8+1 physical.
# Climber (Passive): easy terrain traversal, not combat-relevant.
# From Above (Passive): 1d10+1 instead of standard damage when attacking from
# above - not modeled (no position tracking yet).
JAGGED_KNIFE_BANDIT = Adversary(
    name="Jagged Knife Bandit",
    tier=1,
    difficulty=12,
    major_threshold=8,
    severe_threshold=14,
    hp_max=5,
    stress_max=3,
    attack_modifier=1,
    damage_dice=[DiceGroup(count=1, sides=8)],
    damage_modifier=1,
)

# Tier 1 Ranged. Shortbow: far range, 1d10+2 physical.
# Unseen Strike (Passive): 1d10+4 instead of standard damage while Hidden -
# not modeled (no Hidden state tracked yet).
JAGGED_KNIFE_SNIPER = Adversary(
    name="Jagged Knife Sniper",
    tier=1,
    difficulty=13,
    major_threshold=4,
    severe_threshold=7,
    hp_max=3,
    stress_max=2,
    attack_modifier=-1,
    damage_dice=[DiceGroup(count=1, sides=10)],
    damage_modifier=2,
)
