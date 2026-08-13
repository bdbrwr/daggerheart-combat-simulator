"""Deliberately thin.

adversaries/adversary.py imports AttackResult from combat.results, and
importing any submodule runs this file first - so anything re-exported here
gets pulled in while `adversaries` is still half-built. Only modules that
depend on neither adversaries nor characters can live here; combat.report,
combat.state, combat.policy and combat.fight all do, so they're imported from
their own modules:

    from combat.fight import run_fight
"""

from .common import FightOutcome, Side
from .results import AttackResult

__all__ = ["AttackResult", "FightOutcome", "Side"]
