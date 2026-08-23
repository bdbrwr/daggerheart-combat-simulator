"""The two damage types, and what resistance and immunity do to a hit.

Daggerheart types every point of damage, and the SRD is unusually precise about
what that buys a target:

  * "There are two damage types: **physical damage (phy)** and **magic damage
    (mag)**."
  * "If a target has **resistance** to a damage type, they reduce incoming damage
    of that type by half **before comparing it to their Hit Point Thresholds**."
  * "If a target has **immunity** to a damage type, they ignore incoming damage
    of that type."
  * "The effects of multiple resistances to the same damage type **do not
    stack**."

Two of those decide the whole shape of this module. Halving happens *before*
thresholds, so resistance changes how many HP a hit marks rather than only the
number printed - the same place `I've Got 'Em`'s doubling already applies. And
resistances don't stack, so several answers are folded by taking the **strongest
single** one rather than by multiplying: two resistances are still a half, and a
resistance beside an immunity is nothing at all.

## A hit can be both types at once

The SRD prints the Spellblade's attack as `1d8+4 phy/mag` and its Arcane Steel as
"considered both physical and magic". So a hit's type is not always one of the
two: `BOTH` is the pair, and the ruling is that such a hit is **resisted if the
target resists either**, and satisfies a restriction naming either. Content asks
`includes(damage_type, DamageType.PHYSICAL)` rather than comparing with `is`,
which is the one change the pair forced on everything that reads a type.

## Untyped damage is not an error, and it matches nothing

Damage should always have a type, and after the typing sweep everything in this
simulator states one bar the Beastbound companion, whose sheet leaves the choice
to the player and which nobody has ruled on.

Where a type is nevertheless missing, the rule is that **it matches nothing**. It
is resolved unreduced rather than raising, and it satisfies no type restriction
either - a physical-only feature declines on it exactly as a magic resistance
does. So a gap in the authoring can only ever *fail* to apply an effect, never
wrongly apply one, and it shows up as nothing happening rather than as the wrong
thing happening.

What *does* raise is a type somebody wrote down and spelled wrong, because that
is the one case where the failure would be invisible: it would quietly resolve as
untyped, and a resistance that silently never fires looks identical to a
resistance nobody implemented. See `damage_type_named`.
"""

from enum import Enum

from content.names import canonical


class DamageType(Enum):
    """The SRD's two damage types, spelled as the book spells them."""

    PHYSICAL = "physical"
    MAGIC = "magic"


# A hit that is **both** types at once, which the SRD prints as "1d8+4 phy/mag"
# on the Spellblade and describes as "considered both physical and magic".
#
# RULED: **a hit that is both is resisted if the target resists *either*.** It
# genuinely counts as both for everything, so the Skeleton Warrior's physical
# resistance halves a Spellblade's swing exactly as a magic resistance would, and
# a physical-only restriction like the Construct's Weak Structure fires on it too.
# The other reading - resisted only by something resistant to both - was offered
# and declined.
#
# Represented as a frozenset rather than a third enum member on purpose. Every
# restriction in the codebase used to ask `damage_type is DamageType.PHYSICAL`,
# and a third member would have answered False to all of them - precisely the
# checks the ruling says should pass. A set makes "does this hit count as
# physical?" a membership question instead, which is what the ruling actually
# says, so the five sites that asked it now call `includes` and there is one
# answer rather than a special case per feature.
BOTH = frozenset({DamageType.PHYSICAL, DamageType.MAGIC})

# What a stat block prints beside its damage - "Warp Blast: Close, 1d12+6 mag".
# Accepted so a catalogue entry can be typed the way the page reads, rather than
# the author translating as they go.
_ABBREVIATIONS = {
    "phy": DamageType.PHYSICAL,
    "mag": DamageType.MAGIC,
}

# The dual type, spelled the several ways a page or an author might write it.
_PAIRED = frozenset({"phy/mag", "mag/phy", "physical/magic", "magic/physical"})

# What each of the three answers does to a damage total. Named rather than left
# as bare numbers because "0.5" at a call site says nothing about which SRD rule
# put it there.
UNREDUCED = 1.0
RESISTED = 0.5
IMMUNE = 0.0


def damage_type_named(name) -> "DamageType | frozenset | None":
    """The type a printed damage type names, matched canonically.

    Returns None for nothing at all - an empty string or None - which is how
    untyped damage travels; see the module docstring for why that isn't an error.

    Returns **`BOTH`** for a page that prints the pair ("phy/mag"), and passes an
    already-resolved `DamageType` or a set of them straight through, so a feature
    that hands a type in directly and a catalogue entry that spells one out reach
    the same place.

    Raises on anything else. A type somebody wrote and misspelled is exactly the
    failure the canonical matching everywhere else exists to prevent: it would
    quietly resolve as untyped, and a resistance that silently never fires looks
    identical to a resistance nobody implemented.
    """
    if name is None:
        return None
    if isinstance(name, DamageType):
        return name
    if isinstance(name, (frozenset, set)):
        return frozenset(name) or None

    written = str(name).strip()
    if not written:
        return None

    if canonical(written) in {canonical(pair) for pair in _PAIRED}:
        return BOTH

    for damage_type in DamageType:
        if canonical(damage_type.value) == canonical(written):
            return damage_type
    abbreviated = _ABBREVIATIONS.get(canonical(written))
    if abbreviated is not None:
        return abbreviated

    raise ValueError(
        f"{name!r} is not a damage type. Expected "
        + " or ".join(f"{kind.value!r}" for kind in DamageType)
        + " (the book's 'phy' and 'mag' are accepted too, and 'phy/mag' for a hit "
        "that is both)."
    )


def types_in(damage_type) -> frozenset:
    """Every `DamageType` a hit counts as, as a set.

    One place to normalise the three shapes a hit's type can arrive in - a single
    `DamageType`, the `BOTH` pair, or None for untyped - so nothing else has to
    care which it was handed. Untyped comes back empty, which is what makes it
    match nothing without any caller special-casing it.
    """
    if damage_type is None:
        return frozenset()
    if isinstance(damage_type, DamageType):
        return frozenset({damage_type})
    return frozenset(damage_type)


def includes(damage_type, kind: DamageType) -> bool:
    """Whether a hit of this type counts as `kind`.

    The replacement for `damage_type is DamageType.PHYSICAL` at every site that
    used to ask it, and the reason the dual type is a set: the Spellblade's swing
    is physical *and* magic, so a physical-only restriction must fire on it and a
    magic resistance must reduce it.

    Untyped damage counts as nothing, which is the standing rule - a hit nobody
    typed can only ever fail to satisfy a restriction, never wrongly satisfy one.
    """
    return kind in types_in(damage_type)


def strongest(factors) -> float:
    """The one factor that applies, out of everything that answered.

    The **smallest**, because resistances don't stack: two of them are still a
    half, and an immunity beside a resistance is an immunity. Multiplying would
    have made a second resistance quarter the damage, which the SRD rules out in
    so many words.

    Nothing answering is `UNREDUCED`, so a caller can use the result without
    checking whether anything did.
    """
    return min(factors, default=UNREDUCED)


def reduced(amount: int, factor: float) -> int:
    """`amount` after a resistance or immunity, rounded down.

    Rounding down follows the rest of the codebase's halvings - Whirlwind's half
    damage to additional targets, Magical Reflection's rebound - and the SRD
    never rounds a damage reduction up.
    """
    if factor >= UNREDUCED:
        return amount
    return int(amount * factor)
