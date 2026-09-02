"""The one shape a Spellcast Roll takes.

Every domain module used to carry its own `_spellcast` helper - six copies of the
same twelve lines, which had drifted three ways by the time level 3 landed: four
took a `difficulty` for area spells, Grace's took a `trait` because Troublemaker
rolls Presence, and Codex's took a flat `bonus` **that no card ever passed**.
Adding **Help an Ally** meant editing all six, which was the point at which the
duplication stopped being tolerable.

The dead `bonus` is worth noting as the thing duplication does: it survived in
one copy for as long as nobody had to look at all six side by side. It is gone
here rather than carried forward, since a parameter nothing uses is machinery
kept on speculation. A card printing a flat bonus to its own roll can add one
back in a line.

This is that helper, once. It is not new machinery: nothing here does anything
the copies didn't, and the rolling is still `dice/duality.py`'s `roll_duality`
called from the site that knows what to roll - there is one such site now instead
of six.

## What a Spellcast Roll is made of

Duality Dice plus the caster's Spellcast trait, against the target's Difficulty,
and then five things that all have to happen **outside** the roll's closure:

  * anything content adds to the roll (`total_roll_bonus`),
  * an ally spending a Hope to help (`content/help.py`),
  * the size of the Hope Die (`hope_die_for`),
  * Advantage on the roll (`granted_action_roll_advantage`),
  * and the party's chance to re-make the result (`remake_action_roll`).

The first four share one contract: **being asked is the commitment.** Several
registrants spend Hope, mark Stress or claim a per-rest use simply by being
consulted, so they are evaluated once and the closure reuses the answers. A
reroll re-makes the *dice*, never the decisions that fed them - asking twice
would charge twice.

## Why it lives in content/ rather than domain_cards/

Because `domain_cards/` is content, and one card must never import another's
module. A helper shared by six cards belongs beside the dispatch they all already
call. `features/` will want it too the first time a subclass casts something.

## A note for tests

`roll_duality` is imported here, so this is the module to patch when a case needs
a Spellcast Roll to come out a particular way - `content.spellcast.roll_duality`,
not the domain module. Patching the domain module used to work and now reaches
nothing, since the domain modules no longer call it. Most cases avoid the
question entirely by giving the target a Difficulty of 0 or 1.
"""

from dice.duality import roll_duality

from .help import help_with_roll
from .registry import (
    Fight,
    Holder,
    granted_action_roll_advantage,
    hope_die_for,
    remake_action_roll,
    total_roll_bonus,
)

__all__ = ["spellcast"]


def spellcast(
    caster: Holder,
    target,
    fight: Fight = None,
    *,
    trait: str = "",
    difficulty: int | None = None,
):
    """A Spellcast Roll against `target`, or None if this caster can't make one.

    `trait` names which of the caster's traits to roll, defaulting to their
    Spellcast trait. Grace's *Troublemaker* passes `"presence"`, being a Presence
    Roll rather than a spell - which is also why a PC with no Spellcast trait at
    all can still use that card.

    `difficulty` overrides the target's own, for a spell rolled **against a whole
    area at once**: such a spell has no single Difficulty, so the caller passes
    `content/aoe.py`'s `area_difficulty` and each target is re-checked afterwards.
    See SIMULATION-RULES.md on how an area roll's own success is decided.

    Returns None rather than rolling when the caster names no trait to roll, or
    names one their sheet doesn't carry. That way unusable content shows up as
    content that never fires rather than as content that quietly fires with the
    wrong number - and the caller treats None as "this spell declines", so the
    spotlight falls through to whatever else the PC could do.

    Everything is worked out **before** the closure and reused by it. See the
    module docstring: asking content for a bonus, a Hope Die or an ally's help is
    the commitment, and a reroll must not charge for any of them twice.

    Keyword-only after `fight`, deliberately. The six helpers this replaces
    disagreed about what their fourth positional argument meant, so a positional
    call is exactly the mistake worth failing loudly on.
    """
    rolling = trait or getattr(caster, "spellcast_trait", "")
    if not rolling or rolling not in caster.traits:
        return None

    helped = help_with_roll(caster, fight)
    modifier = (
        caster.traits[rolling] + total_roll_bonus(caster, target, fight) + helped.bonus
    )
    against = target.difficulty if difficulty is None else difficulty
    hope_die = hope_die_for(caster, fight)
    # Content that hands *any* action roll Advantage - the Valor card Inevitable.
    # Not `attack_advantage`, which only a standard attack consults, so a card
    # registered there would reach a weapon swing and never a cast. Resolved out
    # here with everything else for the reason the module docstring gives: being
    # asked is the commitment, and a reroll must not spend a one-shot grant twice.
    advantage_state = granted_action_roll_advantage(caster, target, fight)

    def roll():
        return roll_duality(
            modifier=modifier,
            difficulty=against,
            advantage_state=advantage_state,
            hope_die=hope_die,
            help_dice=helped.dice,
        )

    # Offered to the party's reroll content before anything reads the result, so
    # a replacement is indistinguishable from having rolled that way first.
    return remake_action_roll(caster, roll(), roll, fight)
