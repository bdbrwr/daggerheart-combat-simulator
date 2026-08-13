"""Ancestry features.

Registered under the name a character sheet writes in its `ancestry` field.

Dismissals here are the user's calls, not the assistant's: whether a piece of
content can affect a fight is a judgement about the game, and it's theirs to
make. Anything not ruled on stays `unimplemented`, which is the honest state and
shows as such in the coverage report.
"""

from content.registry import no_combat_effect

no_combat_effect("Fungril", "Ruled as having no effect on the combat simulation.")
