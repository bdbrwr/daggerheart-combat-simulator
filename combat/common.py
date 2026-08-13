"""Vocabulary shared across the fight loop and the things that configure it.

Kept separate from combat/results.py for the same reason dice/common.py exists:
encounters need to name a starting spotlight without importing the loop, and
the loop needs to name an outcome without importing encounters.
"""

from enum import Enum


class Side(Enum):
    """Who currently holds the spotlight.

    Daggerheart has no turn order - the spotlight is the whole of it. It
    starts with the PCs unless an encounter says otherwise, and swings to the
    GM the moment a PC fails a roll or rolls with Fear.
    """

    PCS = "pcs"
    GM = "gm"


class FightOutcome(Enum):
    """How a simulated fight ended.

    UNRESOLVED means the loop hit its action cap with both sides still
    standing - a fight nobody can finish (PCs who can't beat a Difficulty,
    adversaries who can't beat an Evasion). It's a bug signal or a genuinely
    broken matchup, not a draw to average into the results.
    """

    PARTY_VICTORY = "party_victory"
    PARTY_DEFEAT = "party_defeat"
    UNRESOLVED = "unresolved"
