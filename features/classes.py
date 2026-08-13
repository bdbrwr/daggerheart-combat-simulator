"""Class features and Hope features.

Registered under the name a character sheet writes in its `class` field, because
that's what a lookup has to be keyed on - a sheet says "Guardian", not "Frontline
Tank". A class carries several features under that one name, which is the same
shape a Grimoire has, so it uses the same helper.

Feature text is paraphrased in each docstring rather than quoted in full; the
verbatim wording is on the SRD site.

Nothing here is dismissed as having no combat effect. That's a judgement about
the game and it's the user's to make, so anything not ruled on and not
implemented stays `unimplemented` and says so in the coverage report.
"""

from content.grimoire import FeatureSet
from content.registry import Fight, Holder

# Every Hope feature in the game costs 3 Hope.
HOPE_FEATURE_COST = 3

GUARDIAN = FeatureSet("Guardian")


@GUARDIAN.free("Frontline Tank")
def frontline_tank(guardian: Holder, fight: Fight) -> bool:
    """Guardian's Hope feature. Spend 3 Hope to clear 2 Armor Slots.

    Worth it once at least two slots are marked - clearing one slot for three
    Hope is a poor trade, and Armor Slots are only worth anything while there's
    damage still to come.

    SIMULATION RULE - policy. Waits for two marked slots rather than spending on
    the first. The rules let a Guardian burn it whenever they like; a knob.
    """
    if not guardian.can_spend_hope(HOPE_FEATURE_COST):
        return False
    if guardian.armor_marked < 2:
        return False

    guardian.spend_hope(HOPE_FEATURE_COST)
    guardian.clear_armor_slot(2)
    fight.note(f"{guardian.name} shrugs it off (Frontline Tank: 2 Armor Slots cleared)")
    return True
