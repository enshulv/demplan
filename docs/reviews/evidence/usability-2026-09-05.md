# Usability Evaluation — 2026-09-05 (Work Package 1, commit 909903a)

**Method**: an agent with no prior context on this project, given only the installed package, `README.md`, and the dep1ex01
dataset, role-played a social-science researcher. Reading `docs/`, `research/`, `crates/`, and `tests/` was off limits. The task:
get started from the README, reproduce a published experiment, write two of their own price-update rules, and compute labor use
and private consumption from the resulting plan.

**Conclusion**: **6/10** (8 for exploration, 4 for publishing a paper). The core functionality and speed are already there; what
is missing is writing output to disk and a public seam for swapping in a price-update rule.

## Results

| Coordination procedure | Rounds | Converged | Worst imbalance | Seconds |
|---|---|---|---|---|
| `HahnelSlides2020()` (built in) | 14 | yes | 0.0478 | 3.50 |
| Proportional rule, gain=0.5 (the gain suggested to the researcher) | 250 (cap) | no | 1.02 | 44.7 |
| Proportional rule, gain=0.2 | 11 | yes | 0.0393 | 1.17 |
| Proportional rule, gain=0.1 | 22 | yes | 0.0452 | 2.72 |
| Adaptive-gain rule | 23 | yes | 0.0377 | 2.38 |

The researcher's substantive finding: the 2020 rule's effective gain, `w/v = 1.05 − 0.5^v`, tops out at 0.21;
a fixed gain of 0.2 converges three rounds faster than the published rule on this economy; the stability boundary sits between 0.2
and 0.3. A sweep over six gains ran in two minutes, versus a week for the upstream implementation. `check_determinism` returned
`identical` for both hand-written methods.

Compared with upstream: one experiment set, 4 hours versus 3.5 seconds; ten variants, 40 hours versus 2 minutes 6 seconds.

## Friction (by severity)

| # | Where | What happened | Severity | Disposition |
|---|---|---|---|---|
| F1 | README | Three places promise a run manifest and an output writer that do not exist in the code. Two labs cannot exchange run results today | Blocking (for publishing a paper) | README rewritten to state the facts accurately; the writer and manifest are Stage 4, listed as the first item for next steps |
| F2 | prefab | Swapping the price-update rule while leaving the rest unchanged requires importing three private names, `_Model`, `_State`, and `_relative_imbalance` | Slows things down, and is a correctness hazard | To fix: expose the council model and a `price_rule` parameter |
| F3 | README | The "ten lines" section and the "write your own" section define demand inconsistently; the latter omits `provision` | Slows things down, silently wrong answer | Fixed |
| F4 | `Plan` | A `Plan` with the wrong shape can be constructed; `total_consumption` silently returns the wrong vector | A blocking-level trap for the researcher | To fix: accessor checks lengths and names the offending field |
| F5 | README | "Optional invariant checks" is in fact just a single determinism self-check | Slows things down | README updated; the residual toolbox is Stage 2 |
| F6 | README installation | Does not say to create a virtual environment first, the minimum Python version, how to install Rust, or how long the build takes | A real first-time user would give up here | Fixed |
| F7 | README | The example uses a bare filename with no download command | Cosmetic | Fixed |
| F8 | `tools` | Only answers "given output, how much input," not "given prices, how much output does the council propose"; the dep1ex closed-form solution is hidden inside a private class | Slows things down, ate up the entire third step | Fixed alongside F2 |

Two more items belong in `not_done`: `iterate` only detects divergence when given `plan_of`, which keeps every round's `Plan` in
memory; the researcher gave up on divergence detection because of this, and gain=0.5 ran the full 250 rounds. The README has no
example of hand-building a small `Economy`, leaving no way in for the 15 required fields.

## The three most helpful things

1. The speed is honest speed: 1.1 seconds to load, 3.5 seconds for a full run, and `run()` carries its own `wall_seconds`.
2. The built-in method reproduces the published 14 rounds on the very first run, exactly as written in the README, with zero
   configuration.
3. The docstrings say the sentences that decide success or failure: `iterate`'s definition of a round, and the prefab's two
   paragraphs on "clamp the imbalance before computing the step size."

## What the next evaluation should check

Whether F1, F2, and F4 are closed; whether a genuine first-time install goes through cleanly (this environment came
pre-installed, so the installation section was not exercised).
