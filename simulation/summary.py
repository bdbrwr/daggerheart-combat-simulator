"""What a run of N fights adds up to.

A fight is compressed to `FightRecord` - the scalars a comparison actually
uses - as soon as it finishes, so a 10,000-fight run doesn't sit on 10,000
parties and their gear. The records are kept raw and every statistic is
derived from them on demand, the same way the roll results in dice/ derive
their totals: nothing here stores a number that could have been computed.

Keeping the raw records rather than only the aggregates means a question we
haven't thought of yet ("what did the fights we lost in two rounds look
like?") stays answerable from a summary that's already in hand.
"""

from dataclasses import dataclass
from statistics import fmean

from combat.common import FightOutcome
from combat.report import FightResult

# A PC this close to going down counts the fight as a near thing, however it
# ended. Two HP is roughly one solid hit from unconsciousness for a tier 1 PC.
NEAR_DEATH_HP_UNMARKED = 2


@dataclass(frozen=True)
class FightRecord:
    """One finished fight, flattened to the numbers a run compares."""

    outcome: FightOutcome
    party_size: int
    pc_actions: int
    adversary_activations: int
    gm_turns: int
    party_hp_unmarked: int
    lowest_hp_unmarked: int
    unconscious_pcs: int
    surviving_adversaries: int
    fear_gained: int
    fear_spent: int
    fear_remaining: int
    scars_gained: int

    @classmethod
    def of(cls, result: FightResult) -> "FightRecord":
        return cls(
            outcome=result.outcome,
            party_size=result.party_size,
            pc_actions=result.pc_actions,
            adversary_activations=result.adversary_activations,
            gm_turns=result.gm_turns,
            party_hp_unmarked=result.party_hp_unmarked,
            lowest_hp_unmarked=result.lowest_hp_unmarked,
            unconscious_pcs=result.unconscious_pcs,
            surviving_adversaries=result.surviving_adversaries,
            fear_gained=result.fear_gained,
            fear_spent=result.fear_spent,
            fear_remaining=result.fear_remaining,
            scars_gained=result.scars_gained,
        )

    @property
    def pc_rounds(self) -> float:
        if not self.party_size:
            return 0.0
        return self.pc_actions / self.party_size

    @property
    def gm_rounds(self) -> float:
        if not self.party_size:
            return 0.0
        return self.adversary_activations / self.party_size

    @property
    def resolved(self) -> bool:
        return self.outcome is not FightOutcome.UNRESOLVED

    @property
    def won(self) -> bool:
        return self.outcome is FightOutcome.PARTY_VICTORY

    @property
    def pcs_standing(self) -> int:
        """PCs still conscious when the fight ended."""
        return self.party_size - self.unconscious_pcs

    @property
    def near_death(self) -> bool:
        """Whether anyone finished on the edge - or over it.

        Measured on unmarked HP, so this is true of every defeat by
        definition: a party is beaten when nobody is left standing, and an
        unconscious PC has every HP marked.
        """
        return self.lowest_hp_unmarked <= NEAR_DEATH_HP_UNMARKED


@dataclass(frozen=True)
class Distribution:
    """The shape of one measurement across a run.

    Percentiles are nearest-rank, not interpolated: with fight lengths that
    come in whole actions, a p90 of "7" is a length that actually occurred,
    which reads better than an interpolated 6.8 that never did.
    """

    values: tuple[float, ...]

    @classmethod
    def of(cls, values) -> "Distribution":
        return cls(values=tuple(sorted(values)))

    @property
    def count(self) -> int:
        return len(self.values)

    @property
    def mean(self) -> float:
        return fmean(self.values) if self.values else 0.0

    @property
    def median(self) -> float:
        return self.percentile(0.5)

    @property
    def minimum(self) -> float:
        return self.values[0] if self.values else 0.0

    @property
    def maximum(self) -> float:
        return self.values[-1] if self.values else 0.0

    def percentile(self, fraction: float) -> float:
        if not self.values:
            return 0.0
        index = min(int(fraction * self.count), self.count - 1)
        return self.values[index]

    def summarize(self) -> str:
        """One line: mean, median, the tails, and the full range."""
        if not self.values:
            return "no data"
        return (
            f"mean {self.mean:>5.1f}   median {self.median:>5.1f}   "
            f"p10 {self.percentile(0.1):>5.1f}   p90 {self.percentile(0.9):>5.1f}   "
            f"range {self.minimum:g}-{self.maximum:g}"
        )


@dataclass(frozen=True)
class SimulationSummary:
    """Every fight in a run, plus the setup needed to read them.

    Statistics are properties rather than stored fields, so slicing the
    records a different way never means the summary disagrees with itself.
    """

    encounter_name: str
    party: list[str]
    opposition: list[str]
    seed: int | None
    records: list[FightRecord]

    # The encounter file's own account of why it's set up this way. Carried here
    # so the reasoning behind a knob and the numbers it produced are printed
    # together rather than living in a file nobody opens.
    notes: str = ""

    # This run's variation name on its own ("Sniper toughened"), where
    # `encounter_name` is the full title ("Roadside Ambush - Sniper toughened").
    # A comparison table of one experiment's variations wants the short form:
    # every row repeating the experiment name is noise, and the table is only
    # 28 characters wide.
    variation: str = ""

    @property
    def runs(self) -> int:
        return len(self.records)

    @property
    def resolved(self) -> list[FightRecord]:
        """Fights that actually finished.

        Unresolved fights hit the action cap, so their length is the cap
        rather than a fight length. Averaging them in would quietly drag every
        distribution toward it, so they're counted separately and left out.
        """
        return [record for record in self.records if record.resolved]

    @property
    def victories(self) -> list[FightRecord]:
        return [record for record in self.records if record.won]

    @property
    def defeats(self) -> list[FightRecord]:
        return [
            record
            for record in self.records
            if record.outcome is FightOutcome.PARTY_DEFEAT
        ]

    @property
    def unresolved(self) -> list[FightRecord]:
        return [record for record in self.records if not record.resolved]

    @property
    def win_rate(self) -> float:
        return len(self.victories) / self.runs if self.runs else 0.0

    @property
    def defeat_rate(self) -> float:
        return len(self.defeats) / self.runs if self.runs else 0.0

    @property
    def unresolved_rate(self) -> float:
        return len(self.unresolved) / self.runs if self.runs else 0.0

    @property
    def near_death_rate(self) -> float:
        """How often a fight was won with someone on the edge.

        Deliberately scoped to victories: in a defeat everyone is down by
        definition, so counting those would just restate the loss rate. This
        is the number that separates a comfortable win from a scare.
        """
        victories = self.victories
        if not victories:
            return 0.0
        return sum(1 for record in victories if record.near_death) / len(victories)

    def distribution(self, attribute: str, records=None) -> Distribution:
        """The distribution of one record attribute, over resolved fights by default."""
        source = self.resolved if records is None else records
        return Distribution.of(getattr(record, attribute) for record in source)
