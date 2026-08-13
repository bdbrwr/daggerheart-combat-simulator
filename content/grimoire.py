"""Cards that hold several abilities under one name.

A Grimoire is one domain card carrying three separate spells. A character sheet
names the *book* - "Book of Ava" - so that's what a lookup has to be keyed on,
but the spells inside it are separate things that fire at different points: one
makes an action roll, another costs a Hope and no roll at all.

This maps the two together. Each ability is written as its own function, exactly
like a standalone card, and the Grimoire registers one dispatcher per hook kind
under the book's name. Asking the registry what "Book of Ava" does as an action
walks its action spells in order and takes the first that wants the roll.

    AVA = Grimoire("Book of Ava")

    @AVA.action("Power Push")
    def power_push(caster, target, fight): ...

    @AVA.free("Tava's Armor")
    def tavas_armor(caster, fight): ...

Two consequences worth knowing:

  * A Grimoire spends **one** slot of the spotlight budget per spotlight, not
    one per spell, because the budget counts the card. Casting Tava's Armor uses
    the book's free slot; a second free spell from the same book has to wait.
  * Because abilities keep their own identity, moving a book between loadout and
    vault moves all of its spells together - which is how the card works at a
    table, and what makes a vault swap expressible later.
"""

import random
from typing import Callable, Iterable

from content.registry import action, free

__all__ = ["FeatureSet", "Grimoire"]


class Grimoire:
    """One card, several named abilities, reached through the card's name."""

    def __init__(self, card: str):
        self.card = card
        self._actions: list[tuple[str, Callable]] = []
        self._free: list[tuple[str, Callable]] = []
        self._gaps: list[str] = []
        self._action_registered = False
        self._free_registered = False

    def action(self, ability: str, unmodelled: Iterable[str] = ()):
        """Register one of this book's spells as an action roll."""

        def register(function: Callable) -> Callable:
            self._actions.append((ability, function))
            self._gaps.extend(f"{ability}: {gap}" for gap in unmodelled)
            self._register_action()
            return function

        return register

    def free(self, ability: str, unmodelled: Iterable[str] = ()):
        """Register one of this book's spells as needing no roll."""

        def register(function: Callable) -> Callable:
            self._free.append((ability, function))
            self._gaps.extend(f"{ability}: {gap}" for gap in unmodelled)
            self._register_free()
            return function

        return register

    def note_gap(self, ability: str, gap: str) -> None:
        """Record a spell of this book that isn't modelled at all.

        Not `no_combat_effect`: that's for content which could not change a
        fight even fully implemented. A spell we simply don't run is a gap on
        the book, and shows up as one in the coverage report.
        """
        self._gaps.append(f"{ability}: {gap}")
        self._refresh_gaps()

    # --- Registration ---------------------------------------------------------
    #
    # One dispatcher per hook kind, registered the first time a spell of that
    # kind is added. Re-registering the same function on later spells would trip
    # the registry's name check, so each is claimed once and the closure picks
    # up new spells as they're appended.

    def _register_action(self) -> None:
        if self._action_registered:
            self._refresh_gaps()
            return
        self._action_registered = True

        @action(self.card, unmodelled=self._gaps)
        def cast(caster, target, fight):
            # Shuffled for the same reason a loadout is: the order spells were
            # written into a book carries no meaning, so it mustn't decide
            # which one gets cast.
            spells = [spell for _, spell in self._actions]
            random.shuffle(spells)
            for spell in spells:
                result = spell(caster, target, fight)
                if result is not None:
                    return result
            return None

        cast.__name__ = f"cast_{self.card.lower().replace(' ', '_')}"

    def _register_free(self) -> None:
        if self._free_registered:
            self._refresh_gaps()
            return
        self._free_registered = True

        @free(self.card, unmodelled=self._gaps)
        def invoke(caster, fight):
            spells = [spell for _, spell in self._free]
            random.shuffle(spells)
            return any(spell(caster, fight) for spell in spells)

        invoke.__name__ = f"invoke_{self.card.lower().replace(' ', '_')}"

    def _refresh_gaps(self) -> None:
        """Keep the registry's assessment in step as later spells declare gaps."""
        from content.registry import Status, _assess

        if self._action_registered or self._free_registered:
            _assess(self.card, Status.MODELLED, __name__, unmodelled=tuple(self._gaps))


# A class or a community is the same shape as a Grimoire: one name on a
# character sheet, several separate features underneath it. The alias just reads
# better at those sites than talking about a book of spells.
FeatureSet = Grimoire
