# daggerheart-combat-simulator

A Monte Carlo combat simulator for Daggerheart, built to balance adversary stat
blocks against real party compositions.

The official Battle Points math produces encounters that swing between "a sack of
HP to clear" and unexpectedly deadly, and it can't tell you which you've built
until you run it at the table. This runs the fight ten thousand times instead and
reports what actually happens: how often the party wins, how long it takes, and
what it costs them when they do.

It is **not** a rules engine and doesn't try to be. A great deal of it is table
decisions frozen into fixed policies, readings chosen where the SRD is silent,
and rules knowingly skipped. All of those are catalogued in
[SIMULATION-RULES.md](SIMULATION-RULES.md), and every run prints a coverage block
saying how much of each combatant it actually ran — because a win rate produced
by a half-implemented party is misleading without it.

## Requirements

Python 3.14+, managed with [uv](https://docs.astral.sh/uv/). No runtime
dependencies.

```
uv sync
```

## Running it

```
uv run python -m simulation --list
uv run python -m simulation "Roadside Ambush"
uv run python -m simulation "Roadside Ambush" --runs 10000 --seed 7
uv run python -m simulation --all --runs 2000 --seed 7 --save
uv run python -m simulation "Roadside Ambush" --play-by-play --seed 7
```

| Flag | What it does |
|---|---|
| `--list`, `-l` | Every encounter file, its party, its variations — and any file that failed to load, with the reason |
| `--runs N`, `-n` | Fights per variation (default 1,000). 10,000+ for a number you'd act on |
| `--seed N`, `-s` | Repeat a run exactly. **One seed seeds every variation in the command**, so they face the same dice and a difference between rows is a difference between stat blocks rather than luck |
| `--all`, `-a` | Run every encounter file |
| `--play-by-play`, `-p` | One seeded fight, narrated line by line |
| `--no-coverage` | Omit the coverage block |
| `--full-coverage` | Print all of it, including modelled content and its declared gaps |
| `--save` / `--save-dir` | Write exactly what was printed to a timestamped file in `runs/` |

### The tuning loop

1. **Write an encounter file** in `encounters/` — one file is one *question*, and
   the `variations` inside it are the answers you're comparing.
2. **Run it.** Naming one file runs every variation and prints a comparison table
   underneath. That table is the thing you read.
3. **Move one knob**, in a new variation, with a `notes` field saying why. Notes
   are printed with the report, so the reasoning stays next to the numbers.
4. **When a number looks wrong**, `--play-by-play --seed 7` runs a single fight
   with the loop narrating itself. A win rate tells you a number is off; this
   tells you which rule produced it.

Step 4 is worth reaching for earlier than feels necessary. A feature that
silently isn't firing looks exactly like a feature that chose not to.

## Authoring: everything you write is JSON

Content you author is data. Code is only for things that *do* something in a
fight.

| You write | Where | Names, which resolve to |
|---|---|---|
| Character sheets | `characters/*.json` | domain cards, ancestry, community, class, subclass → `domain_cards/`, `features/` |
| Encounters | `encounters/*.json` | adversaries → `adversaries/*.json` |
| Adversary stat blocks | `adversaries/*.json` | features → `features/adversaries.py` |
| Weapons and armor | `items/*.json` | features → `features/weapons.py`, `features/armor.py` |

The pattern is the same everywhere: **a record is JSON, and it names features
that are code.** A character sheet names "I Am Your Shield"; an adversary stat
block names "Relentless"; a Greatsword names "Massive". One file per publication
(`srd.json`, `homebrew.json`, one per purchased adventure), so a broken homebrew
file costs you that file and nothing else.

Copy `encounters/example_encounter.json` to start — its four variations
demonstrate every kind of override.

```json
{
  "name": "Roadside Ambush",
  "notes": "Four adversaries against one tier 1 PC. What does softening buy?",

  "party": ["example_character.json"],
  "starting_fear": 0,
  "starting_spotlight": "pcs",
  "rest": "long",

  "variations": [
    { "name": "As printed",
      "groups": [{ "adversary": "Jagged Knife Bandit", "count": 3 }] },

    { "name": "One fewer bandit",
      "notes": "The obvious first thing to try.",
      "groups": [{ "adversary": "Jagged Knife Bandit", "count": 2 }] },

    { "name": "Toughened sniper",
      "notes": "Same count, more staying power. Tune the block, not the number of bodies.",
      "groups": [
        { "adversary": "Jagged Knife Bandit", "count": 3 },
        { "adversary": "Jagged Knife Sniper", "count": 1,
          "overrides": { "hp_max": 5, "damage_modifier": 4 } }
      ] }
  ]
}
```

Everything outside `variations` is the shared baseline; a variation overrides only
what it states. **Per-encounter tuning belongs in `overrides`**, never in the stat
block — that keeps `adversaries/srd.json` checkable against the printed page, and
lets the same adversary appear at different settings in different variations. The
keys you may override are exactly the keys the catalogue uses, in the same
notation — so `"damage_dice": "2d6"`, `"2d6+1d4"` or `["2d6", "1d4"]`, with any
flat bonus going in `damage_modifier` rather than into the dice string.

### Adding an adversary

```json
{
  "publication": "Immareth homebrew",
  "adversaries": [
    { "name": "Bog Lurker",
      "tier": 1, "difficulty": 13,
      "major_threshold": 7, "severe_threshold": 15,
      "hp_max": 6, "stress_max": 3,
      "attack_modifier": 2,
      "damage_dice": "1d10", "damage_modifier": 2,
      "features": ["Drag Under"] }
  ]
}
```

That's the whole of it — discovery is automatic, there's nothing to register.
`"Drag Under"` isn't implemented, so it will report as **unimplemented** in the
coverage block under every run until somebody writes it in
`features/adversaries.py`. That's intended: the gap is visible instead of silent.

### Loading is strict, on purpose

An unknown key, a misspelled stat, an unknown adversary, a missing character
sheet — all raise, naming the file. A typo that quietly defaulted would simulate a
different fight from the one you wrote down, which is the failure this project can
least afford. A file that won't parse at all is isolated but **never silent**: it's
reported by `--list` and named when a lookup misses it.

Names are matched **case- and whitespace-insensitively** but not otherwise:
`"i am your shield"` finds the card, `"Natures Tongue"` does not find
`"Nature's Tongue"`. A wrong match is worse than a miss, because a miss shows up
in the coverage block.

## Reading the output

- **OUTCOMES** — win / defeat / unresolved. *Unresolved* means the fight hit the
  action cap, which usually means neither side can meaningfully hurt the other.
  Those are excluded from every distribution.
- **FIGHT LENGTH** — in PC rounds and GM rounds, split by win and loss, because a
  party that loses tends to lose fast and a combined average describes no fight
  anyone had.
- **COST TO THE PARTY** — victories and defeats side by side. A 60% win rate
  reached in three rounds with nobody hurt is a different encounter from a 60%
  reached in nine with a PC on their last HP. *Death moves* counts PCs dropping;
  *scars* counts the roll after that going badly, so scars are always fewer.
- **PER PARTY MEMBER** — the same cost, one character at a time: how often each
  ended a fight down (as a rate *and* a count, because at 10,000 runs a rate
  rounds a rare disaster to 0.0%), and the minimum and mean of what they had left
  unmarked on each track. A party averaging four unmarked HP is comfortable if all three sit
  at four and badly aimed if two are untouched and the third is on nothing every
  time — and only this table tells them apart. Repeated under the comparison,
  grouped by variation, so you can see what moving a knob did to each character.
- **FEAR** — whether the GM's economy did anything. Fear spent near zero means
  extra activations never got bought.
- **COVERAGE** — what the simulator *isn't* running, for both sides. Read this
  first. `--full-coverage` adds the modelled half and the gaps declared on it;
  `--no-coverage` drops the block entirely.

Coverage separates four states, and the difference between the dismissals and the
last one is the whole point:

- **modelled** — code runs it (possibly with declared gaps)
- **no effect** — assessed and dismissed: it *cannot* change a fight
- **insignificant** — assessed and dismissed: it could, but by too little to be
  worth modelling, and the recorded reason says by how much
- **unimplemented** — nobody has looked at it yet

Only the last one is a gap. The two dismissals cost the results nothing, because
somebody looked and wrote down what they found.

The default prints the three states that mean something isn't running. Modelled
content is left out, and so are the **gaps** declared on partial implementations
— a modelled feature saying which parts of itself it doesn't do. Those are real,
but in a full party they run to twenty-odd lines and bury the handful of entries
worth acting on, so they wait behind `--full-coverage`. Content that is modelled
with nothing left out declares no gaps and never prints one at any level.

Unimplemented content on the *party's* side makes an encounter look harder than
it is. Unimplemented content on the *opposition's* side makes it look easier. The
two don't cancel out, which is why both are printed.

## Tests

```
uv run pytest                  # fast, deterministic — run this
uv run pytest validation/ -v   # slow statistical checks — not run by default
```

`tests/` is deterministic and example-based: results are either constructed with
fixed values or rigged so the outcome is certain. `validation/` holds Monte Carlo
checks ("is the crit rate really ~8.33%?") which have a structurally non-zero
false-failure rate, and are kept out of the default run on purpose.

## Layout

```
dice/          roll resolution — duality (PC), d20 (adversary), damage
characters/    PlayerCharacter, loaded from JSON sheets
adversaries/   stat blocks as JSON catalogues + the registry that finds them
items/         weapons and armor as JSON catalogues; the shared attack shape;
               consumables (callables — a potion has no stats to record)
content/       the shared registry: hook decorators, the three coverage states,
               discovery, and the dispatch the rest of the codebase calls
domain_cards/  one module per domain (definitions only)
features/      ancestries, communities, classes, subclasses, and gear and
               adversary features — same registry, same hooks
encounters/    JSON. One file is one experiment: a question plus its variations
combat/        one fight: fight.py (spotlight loop), policy.py (decisions),
               state.py (Fear + counters), report.py
simulation/    the Monte Carlo layer: runner, summary, report, coverage, cli
tests/         fast deterministic unit tests
validation/    slow statistical checks, not run by default
```

Contributor conventions — how content must be self-contained, how names are
matched, and the report's vocabulary — are in [CLAUDE.md](CLAUDE.md).
