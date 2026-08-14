"""Condition names, as the dispatch in content/registry.py passes them around.

Only Vulnerable is tracked (see SIMULATION-RULES.md section 3) - the rest of
Daggerheart's conditions have no representation, so content that turns one off
has nothing to turn off. They are named here anyway, because a piece of content
answering "am I immune to Restrained?" with a straight False is a different
thing from one that was never asked, and the constant is what lets it say so.

These are rules vocabulary, not content names: passing a condition by name is
what keeps `is_immune_to` from having to know which feature grants what.
"""

VULNERABLE = "Vulnerable"
RESTRAINED = "Restrained"
