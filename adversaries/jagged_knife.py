"""The Jagged Knife gang's adversaries - both Tier 1, both from the SRD.

Each is a single Adversary literal: the stat block as numbers, nothing else.
Names match the SRD's exactly so an encounter listing them can be checked
against the printed stat block without guesswork.

Attacks run through Adversary.attack(), so nothing here needs an attack
function of its own. Passive features that aren't part of a standard attack
roll (Climber, From Above, Unseen Strike) aren't modeled - they depend on
position/Hidden state this scaffolding doesn't track yet. Picked deliberately
as adversaries whose features have little expected impact on simulated
outcomes; noted here for debugging, not implemented.
"""

from adversaries.adversary import Adversary
from dice.damage import DiceGroup

# Tier 1 Standard. Daggers: melee, 1d8+1 physical.
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
