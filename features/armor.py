"""Armor features.

Registered under the armor feature's own name, namespaced - `armor:Reinforced`.
See features/weapons.py for why the namespace exists.

## Unlike weapon features, these are scoped to the wearer

A weapon's feature belongs to the weapon and only reaches attacks made with it.
An armor's feature belongs to whoever is wearing it and reaches everything that
happens to them - Fortified changes what any hit costs, Painful charges for any
slot marked, Reinforced moves the thresholds every hit is measured against. So
armor feature names go into a PC's `named_features` and dispatch finds them the
same way it finds a domain card's.

## Only the numbers are already on the sheet

A sheet carries Armor Score and damage thresholds already resolved, so an armor
whose whole feature is a number - Flexible's +1 Evasion, Heavy's -1 - has nothing
left to do here and is declared at the bottom of this module. The features that
*aren't* just a number are the reason armor is modelled at all, and they're the
bulk of the SRD's list: Fortified, Resilient, Shifting, Impenetrable, Painful,
Hopeful, Burning and the rest are real mechanics that no sheet can carry.

Only what the current sheets equip is implemented. Everything else in the SRD
armor table is deliberately absent rather than declared, so it reports as
*unimplemented* the moment somebody equips it - which is the honest answer.
"""

from content.names import ARMOR, qualified
from content.registry import Holder, no_combat_effect, severity_response

# Reinforced's bump, kept as a constant so the interpretation below has a name.
REINFORCED_THRESHOLD_BONUS = 2


def _severity(amount: int, major: int, severe: int) -> int:
    """The HP `amount` marks against these thresholds, before anything softens it.

    Duplicated from PlayerCharacter.severity_of rather than called through it,
    because the whole point here is to ask the question against thresholds the
    character doesn't have.
    """
    if amount >= severe:
        return 3
    if amount >= major:
        return 2
    return 1


@severity_response(qualified(ARMOR, "Reinforced"))
def reinforced(
    wearer: Holder, amount: int, hp_to_mark: int, fight=None, damage_type=None
) -> int:
    """*Reinforced*: when you mark your last Armor Slot, increase your damage
    thresholds by +2 until you clear at least 1 Armor Slot.

    `damage_type` is ignored: raised thresholds are raised against everything,
    and the feature names no type.

    Expressed as a severity response rather than as a change to the character's
    thresholds, because thresholds are read once when damage lands and this is
    conditional on state that changes mid-fight. The effect is the same: work out
    what the hit would have marked against the raised thresholds, and take the
    difference off. It's worth at most 1 HP, since +2 can only move a hit across
    one threshold.

    SIMULATION RULE - interpretation. This applies to the hit that marked the
    last slot, not only to later ones. The SRD says the thresholds go up "when
    you mark your last Armor Slot", and by the time damage responses are
    consulted that slot has already been marked - so the wearer is in the state
    the feature describes. Reading it the other way would need the damage
    pipeline to remember what armor looked like before the hit, for a difference
    of one HP on one hit per fight.
    """
    if hp_to_mark <= 0:
        return hp_to_mark
    if wearer.armor_marked < wearer.armor_max:
        return hp_to_mark

    reduction = _severity(amount, wearer.major_threshold, wearer.severe_threshold) - (
        _severity(
            amount,
            wearer.major_threshold + REINFORCED_THRESHOLD_BONUS,
            wearer.severe_threshold + REINFORCED_THRESHOLD_BONUS,
        )
    )
    return max(hp_to_mark - reduction, 0)


# --- Already resolved on the character sheet ---------------------------------
#
# The user's ruling, the same one features/subclasses.py records: if a feature
# modifies a value the sheet carries, the sheet's number already includes it.
# Declared so they still reach the coverage report as assessed rather than
# looking like work nobody has done.

no_combat_effect(
    qualified(ARMOR, "Flexible"),
    "+1 to Evasion. A character sheet carries its Evasion already resolved, so "
    "this is in that number - applying it again would count it twice.",
)


# --- Flavour-only homebrew ---------------------------------------------------
#
# One shared name that any homebrew item can point at, rather than a declaration
# per item. Homebrew gear whose feature is pure flavour is common and each entry
# would otherwise need its own no_combat_effect line saying the same thing - so
# a piece of gear tags itself `"features": ["Homebrew Flavour Only"]` and is
# assessed immediately.
#
# This is the user's ruling on what has no combat effect, not the assistant's.
# It covers *flavour*: homebrew gear with a real mechanical feature gets its own
# named feature and its own implementation, like any SRD one. What this exists
# to prevent is flavour-only gear sitting silently unimplemented, where a
# judgement already made looks like work nobody has done.

no_combat_effect(
    qualified(ARMOR, "Homebrew Flavour Only"),
    "Homebrew armor whose feature is flavour rather than mechanics. Its Armor "
    "Score and damage thresholds are already resolved onto the character sheet, "
    "so there is nothing left for it to do in a fight. Shared by any homebrew "
    "armor that needs it - gear with a real mechanical feature names that "
    "feature instead.",
)
