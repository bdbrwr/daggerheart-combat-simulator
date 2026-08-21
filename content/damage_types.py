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

## Untyped damage is not an error

Every attack in the game has a type, and every stat block and weapon states one.
But a damage figure that reaches a target without one - a test, or a feature
nobody has typed yet - is resolved **unreduced** rather than raising. A missing
type can only ever fail to apply a resistance, which is today's behaviour and
visibly wrong in the direction of "nothing happened"; a raise mid-fight would be
worse. What *does* raise is a type somebody wrote down and spelled wrong: see
`damage_type_named`.
"""

from enum import Enum

from content.names import canonical


class DamageType(Enum):
    """The SRD's two damage types, spelled as the book spells them."""

    PHYSICAL = "physical"
    MAGIC = "magic"


# What a stat block prints beside its damage - "Warp Blast: Close, 1d12+6 mag".
# Accepted so a catalogue entry can be typed the way the page reads, rather than
# the author translating as they go.
_ABBREVIATIONS = {
    "phy": DamageType.PHYSICAL,
    "mag": DamageType.MAGIC,
}

# What each of the three answers does to a damage total. Named rather than left
# as bare numbers because "0.5" at a call site says nothing about which SRD rule
# put it there.
UNREDUCED = 1.0
RESISTED = 0.5
IMMUNE = 0.0


def damage_type_named(name) -> DamageType | None:
    """The `DamageType` a printed type names, matched canonically.

    Returns None for nothing at all - an empty string or None - which is how
    untyped damage travels; see the module docstring for why that isn't an error.

    Raises on anything else. A type somebody wrote and misspelled is exactly the
    failure the canonical matching everywhere else exists to prevent: it would
    quietly resolve as untyped, and a resistance that silently never fires looks
    identical to a resistance nobody implemented.
    """
    if name is None:
        return None
    if isinstance(name, DamageType):
        return name

    written = str(name).strip()
    if not written:
        return None

    for damage_type in DamageType:
        if canonical(damage_type.value) == canonical(written):
            return damage_type
    abbreviated = _ABBREVIATIONS.get(canonical(written))
    if abbreviated is not None:
        return abbreviated

    raise ValueError(
        f"{name!r} is not a damage type. Expected "
        + " or ".join(f"{kind.value!r}" for kind in DamageType)
        + " (the book's 'phy' and 'mag' are accepted too)."
    )


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
