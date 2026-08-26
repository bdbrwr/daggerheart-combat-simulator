"""What was true of the action roll currently being made.

At the moment there is exactly one such fact, and it exists because
`Adaptability` triggers on failing "a roll that utilized one of your
Experiences": something has to remember whether the roll being re-made was one of
those.

It's recorded as a per-fight token on the roller rather than threaded through
every attack signature, because a parameter on shared machinery that exists for
one named feature is the coupling the content registry is here to prevent -
`items/weapons.py` gaining a `used_experience` flag would be the same mistake as
its old `attack_bonus=1`.

The token is generic: it says an Experience was utilised, not which feature
cares. Whoever pays for an Experience sets it - `combat/policy.py` spending the
Hope, School of Knowledge's *Adept* marking the Stress instead - and the policy
clears it at the start of each spotlight's roll.

Rolling itself is not here. Every action roll is still made by
`dice/duality.py`'s `roll_duality`, called at the site that knows what to roll,
which then offers the result to `content/registry.py`'s `remake_action_roll`.
There is no second way to roll dice in this codebase and there should never be
one.

**One kind of roll does have a shared site**: `content/spellcast.py` is the whole
of what a Spellcast Roll is made of, because every domain module was carrying its
own copy of it. That is still `roll_duality` called from the site that knows what
to roll - there is now one such site for spells instead of six.
"""

__all__ = [
    "EXPERIENCE_HOPE_FLOOR",
    "EXPERIENCE_UTILISED",
    "clear_experience_utilised",
    "experience_was_utilised",
    "note_experience_utilised",
]

# The token name. Not a feature name - several things in the SRD key off having
# used an Experience, and this says only that one was.
EXPERIENCE_UTILISED = "Experience Utilised"

# How much banked Hope counts as **plenty** - the point past which a PC will
# spend one on something that only improves a roll.
#
# SIMULATION RULE - policy, ruled. It started life in `combat/policy.py` as the
# floor for spending Hope on an Experience, set high enough that doing so never
# starves the cards that want Hope. The user's ruling on **Help an Ally** was
# that helping reads the same number - "one constant read in two places rather
# than two that could drift" - and helping is a move `content/` has to be able to
# make, which is why the constant lives here rather than in the turn policy.
#
# It keeps the name of its first user. Both readers are asking one question, and
# renaming it would only make the second look like a different rule.
EXPERIENCE_HOPE_FLOOR = 5


def note_experience_utilised(roller, fight=None) -> None:
    """Record that the roll now being made utilises one of `roller`'s Experiences."""
    if fight is not None:
        fight.set_token(roller, EXPERIENCE_UTILISED, 1)


def clear_experience_utilised(roller, fight=None) -> None:
    """Forget any Experience from a previous roll, before a new one is made."""
    if fight is not None:
        fight.set_token(roller, EXPERIENCE_UTILISED, 0)


def experience_was_utilised(roller, fight=None) -> bool:
    """Whether the roll just made utilised one of `roller`'s Experiences."""
    if fight is None:
        return False
    return bool(fight.token_count(roller, EXPERIENCE_UTILISED))
