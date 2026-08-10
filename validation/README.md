# validation/
Statistical validation tests - large-N Monte Carlo checks that a probability distribution matches its analytic expectation, within tolerance.

These are deliberately **not** part of `tests/` and are **not** run by a plain `pytest` / `uv run pytest`

## Why these are kept separate from tests/
`tests/` should have no possibility of flaking. Everything in here is different in kind - it samples N random outcomes and checks whether an aggregate statistic falls within a tolerance band. That's a legitimate check (it's often the only practical way to validate that probability math is correct), but it inherits:

- a structurally non-zero false-failure rate, even at a fixed seed,
- slower runtime (N=200,000 samples per test),
- poor failure localization (a failure says "the distribution is off",
  not "this specific branch of logic is wrong").

Mixing the two tiers into one `pytest` run makes the fast, exact, should-never-flake tier slower and occasionally flaky for reasons unrelated to a real bug.

## Running these
``` bash
uv run pytest validation/ -v
```

## Future: CI integration
Intended to be wired into a CI job that's allowed to run longer and isn't gating every commit/PR - e.g. nightly, or on release branches - rather than the fast unit test tier that should run on every push.
