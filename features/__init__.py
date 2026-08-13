"""Ancestries, communities, classes and subclasses - everything a sheet names
that isn't a domain card or a piece of gear.

Empty for now. Modules land here as `ancestries.py`, `communities.py`,
`classes.py`, `subclasses.py`, registering into content/registry.py exactly the
way domain_cards/ does - the same hook decorators, the same `no_combat_effect`
declaration for the many that can't change a fight.

The package exists already so content/registry.py's discovery list is honest and
so the first feature has somewhere obvious to go.
"""
