---
name: demplan-usage
description: How to use the demplan library for research. Use when a user wants to run, reproduce or compare democratic planning mechanisms with demplan; load an economy or write a coordination procedure; compare a plan with the reference solution; make a run reproducible; or report results obtained with demplan.
---

# Using demplan

demplan is shared research infrastructure for democratic economic planning. A researcher loads
an economy, runs a coordination procedure on it, and gets the whole plan back as arrays. The
library covers democratic and participatory planning only; it has no market mechanism, and the
benchmark it offers is a centrally computed optimum under an objective the researcher declares.

This skill is for helping a researcher use the library. For changing the library itself, use
`demplan-development`.

## Before you write any code

- **Do not guess the API.** The public names are in `demplan.__all__`; every public function has a
  docstring that states its contract. `docs/spec.md` is the authoritative description of the data
  model and the rules. The README's code blocks are executed by the test suite, so they are known
  to work; start from them.
- **Ask what the researcher wants to find out**, not only what code to write. Most tasks are one
  of: reproduce a published result, change one part of a published procedure, write a new
  mechanism, compare mechanisms, or run a parameter sweep. The sections below follow that order.
- **The library takes no side in economic theory.** Anything theory-laden (a price rule, an
  objective that counts only labour, a linearised technology) is a choice the researcher makes and
  should state. Say so when you use such a tool on their behalf.

## Install

Until a release is on PyPI, install from source. This needs Python 3.10 or newer and a Rust
toolchain (<https://rustup.rs>):

```sh
git clone https://github.com/enshulv/demplan && cd demplan
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install maturin numpy scipy
maturin develop --release
```

Published economies are downloaded separately, for example
`curl -sSL -o dep1ex01.clj.gz https://www.szcz.org/depexperiments/dep1ex01.clj.gz` (56 MB).

## Reproduce a published result

```python
from demplan import load_dep1ex, run
from demplan.prefabs import HahnelBook2021
from demplan.prefabs.hahnel import stateless

economy = load_dep1ex("dep1ex01.clj.gz")        # endowment defaults to 1000, the paper's value
result = run(HahnelBook2021(), economy, seed=0)
print(result.summary.rounds, result.summary.converged, result.summary.diverged)
```

- `HahnelSlides2020(threshold_pct=3.0)` runs at the 3% threshold.
- The endowment of natural resources and labour is a parameter of `load_dep1ex` because it
  matters: the round count changes with it.
- ⚠ **Known issue.** The prefab caps the price-update rule's `v` in both places it appears;
  Hahnel (2021, p. 181) caps it only where it first appears. Until this is corrected, the prefab's
  round counts are one to four rounds higher than the book's per-experiment tables. Tell the
  researcher this before they cite a reproduction number. Details:
  `docs/research/reproduction.md`, addendum of 2026-09-26.

## Change one part of a published procedure

`HahnelSlides2020(price_rule=f)` swaps the price-update rule and keeps the rest. `f` receives the
price, the surplus and the relative imbalance, as read-only arrays, and returns a new price array:

```python
import numpy as np

def proportional(price, surplus, imbalance):
    return price * (1 - 0.2 * np.sign(surplus) * imbalance)

result = run(HahnelBook2021(price_rule=stateless(proportional)), economy, seed=0)
```

Return a new array each round; do not write into the arguments.
`demplan.prefabs.hahnel_2020_slides.slides_2020_rule` is the prefab's own rule in the same shape.
`CouncilModel` in the same module is the councils' side of the procedure, with `initial_state`,
`step`, `converged` and `plan_of`, for a researcher who wants a different loop around the same
councils.

## Write a new coordination procedure

A coordination procedure is any object with `solve(self, economy, seed) -> Plan`. Nothing has to
be subclassed or registered.

**`Economy`** is one period, as column tables: commodities (`commodity_kind`: private good, public
good, intermediate, natural resource, labour), producing units (technology, and inputs stored flat:
unit `i` owns `input_commodity[input_offsets[i]:input_offsets[i+1]]`, see `economy.inputs_of(i)`),
and consumer units. It has no prices. It is immutable; build the next period with
`dataclasses.replace`, which validates again. Identifiers currently equal row numbers.

**`Plan`** has a physical layer and an extension layer:

| Field | Shape | Notes |
|---|---|---|
| `output` | `f64[n_units]` | required |
| `input_use` | `f64[n_inputs]` | required, aligned with the flat input arrays |
| `consumption` | `f64[n_consumers, k]` | pass `None` if the mechanism has no per-consumer consumption |
| `consumption_commodity` | `int64[k]` | which commodity each consumption column is; `None` with the above |
| `provision` | `f64[n_commodities]` | shared quantity of each public good; `None` if not modelled |
| `valuation` | name → `f64` array | prices, labour values, shadow prices; keys and lengths are checked |
| `extra` | name → array | any other physical quantity, one row per unit, consumer or commodity |

Arrays must already have the right dtype: the library refuses rather than converts. An accessor
over a field declared absent raises `PlanFieldAbsent` instead of returning zero.
`StatedPlan` and `AllocatedPlan` distinguish what councils asked for from what an allocation gave.

If the procedure iterates to a fixed point, drive it with
`iterate(init, step, converged, max_rounds, plan_of=...)`. The library then counts rounds, applies
the cap and stops on non-finite values. Rounds are calls to `step`; convergence is never tested on
the starting state. State this definition whenever a round count is reported.

`demplan.tools` has the closed forms of Leontief and Cobb-Douglas technology.

## Compare with the reference solution

```python
from demplan import MinimizeLabor, reference_solution
from demplan.tools.linearize import linearize

plan = result.plan
floor = plan.total_consumption(economy) + plan.provision   # private goods consumed + public goods provided
best = reference_solution(linearize(economy, plan), MinimizeLabor(floor))
```

- The reference solution is a linear program and needs Leontief technology. `linearize` fixes the
  input ratios a plan chose; it turns decreasing returns to scale into constant returns and anchors
  the benchmark on the plan being compared. **A gap computed this way is an upper bound, not an
  estimate.** Say so in any report.
- `MinimizeLabor` counts only labour as a cost; `MaximizeWeightedConsumption` weights final
  consumption. Both carry theoretical commitments, which their docstrings state.
- `plan.extra["consumer_demand"]` is what consumer councils asked for, with public goods already
  divided by the number of councils; it is not the same as the floor above.

## Make a run reproducible

- One integer seed drives everything: `split_seed(seed, n)` for sub-seeds, `rng(seed)` for a numpy
  generator.
- `check_determinism(procedure, economy, seed, n=3)` compares repeated runs byte for byte,
  including `valuation` and `extra`.
- `run_configuration(procedure, economy, seed, plan=plan).to_json("run.json")` records the economy
  as a content hash with per-column digests, the procedure and its parameters, and the library
  version. `compare_economy_digests(recorded, current)` names the columns that differ.

## Reporting results

- Report the threshold, the round-count definition, the seed, the library version and the run
  configuration file.
- Do not claim more than the library supports: the current limitations are listed in the README.
- **Any statement about published work** (a paper's number, a page, a quotation, what another
  implementation does) must be checked against the original. If you do not have the original, ask
  the researcher for it; if it cannot be provided, leave the statement out. The procedure is in
  `demplan-development`, section "Citation check".

## Where to look

| Question | Source |
|---|---|
| Exact data model and rules | `docs/spec.md` |
| Why a rule is what it is | `docs/decisions/` |
| Reproduction details and numbers | `docs/research/reproduction.md` |
| Longer guides | the wiki: For Researchers, Quality Assurance |
