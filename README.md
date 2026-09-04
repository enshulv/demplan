# cyberstride

Shared research infrastructure for democratic economic planning.

Write a coordination procedure, run it on a published economy, and get output raw enough that
anyone can recompute any metric from it afterwards. The library covers democratic and
participatory planning; the benchmark it offers against a mechanism is a centrally computed
optimum under an objective function you declare, not a market.

MIT licensed.

## Install

There is no release on PyPI yet. Building from source needs a Rust toolchain, because the
data model, the loaders and the output writer are Rust behind a Python extension module.

```sh
pip install maturin
maturin develop --release
```

`maturin develop` without `--release` builds faster and runs slower; use the release build
when you are timing anything.

## Ten lines

`HahnelSlides2020` is the iterative price procedure of the 2020 Hahnel-Szczepanczyk-Weisdorf
simulation experiments, set up to reproduce their published round counts. The dep1ex archives
it reads are at <https://www.szcz.org/depexperiments/>.

```python
import numpy as np
from cyberstride import load_dep1ex, run
from cyberstride.prefabs import HahnelSlides2020

economy = load_dep1ex("dep1ex01.clj.gz")
result = run(HahnelSlides2020(), economy, seed=0)

supply = result.plan.total_output(economy) + economy.endowment
demand = (result.plan.total_input_use(economy)
          + result.plan.total_consumption(economy)
          + result.plan.provision)
gap = np.abs(2 * (supply - demand)) / np.where(supply + demand > 0, supply + demand, 1.0)

print(result.summary.rounds, result.summary.converged, gap.max())
```

Nothing in that last calculation is privileged. `Plan` stores the full configuration, so any
measure of feasibility, cost or fairness you want to argue about is a few lines away from the
same output.

## Write your own coordination method

A coordination method is any object with one method:

```python
def solve(self, economy: Economy, seed: int) -> Plan: ...
```

That is the whole interface. Implementing it is enough to get the data model, the loaders,
the timing and round accounting, the determinism self-test and the output format; your code
does not have to be merged into this library to get any of it.

If your method drives a fixed point, running the loop through `iterate` lets the library count
rounds, apply a cap and watch for divergence, none of which it can see from outside:

```python
import numpy as np
from cyberstride import iterate


class ProportionalRule:
    """Move every price by a fixed fraction of its relative imbalance."""

    def __init__(self, gain=0.2, threshold_pct=5.0, max_rounds=200):
        self.gain = gain
        self.threshold_pct = threshold_pct
        self.max_rounds = max_rounds

    def solve(self, economy, seed):
        def step(price):
            plan = self.propose(economy, price)
            supply = plan.total_output(economy) + economy.endowment
            demand = plan.total_input_use(economy) + plan.total_consumption(economy)
            scale = np.where(supply + demand > 0, supply + demand, 1.0)
            return price * (1 + self.gain * (demand - supply) / scale)

        def settled(price):
            return self.worst_gap(economy, price) * 100 < self.threshold_pct

        start = np.full(economy.n_commodities, 700.0)
        return self.propose(economy, iterate(lambda: start, step, settled, self.max_rounds).state)
```

`propose` and `worst_gap` are yours: they are where your assumptions about how councils behave
live. `cyberstride.tools` holds the closed forms of the two technologies the data model knows
about, and `python/cyberstride/prefabs/hahnel_2020_slides.py` is a complete worked procedure.

Round counting is worth one sentence of care, because published counts depend on it. `rounds`
is the number of times `step` was called, and convergence is tested after each `step` and never
after the starting state.

`seed` is a 64-bit integer. `split_seed(seed, n)` derives sub-seeds from it and `rng(seed)`
returns a numpy generator, so a whole run is reproducible from that one number.
`check_determinism(procedure, economy, seed, n)` runs your method several times and compares
the plans bit for bit. It is a tool, not a gate: a randomised procedure is legitimate research,
and the promise being checked is reproducibility given a seed, not the absence of randomness.

## `Economy`

One period of an economy, held as three column tables plus `period` and named `extra` bags.
`Economy` is immutable; evolve it with `dataclasses.replace`, which revalidates the result.

There are no prices here. Valuations belong to whatever mechanism computed them, so they live
on `Plan`.

**Commodities.** One table, with a class marker per row. A new class is a new marker value,
not a new column.

| column | type | meaning |
|---|---|---|
| `commodity_id` | int64 | stable identifier, equal to the row number |
| `commodity_kind` | int8 | 0 private good, 1 public good, 2 intermediate, 3 natural resource, 4 labour |
| `endowment` | f64 | quantity available this period without producing it; 0 for produced goods |

**Producing units.** Variable-length input lists are stored flat with offsets rather than
padded into a rectangle. Unit `i` owns `input_commodity[input_offsets[i]:input_offsets[i+1]]`
and the matching slice of `input_coefficient`; `economy.inputs_of(i)` returns that window. In
v1 each unit produces exactly one commodity.

| column | type | meaning |
|---|---|---|
| `unit_id` | int64 | stable identifier, equal to the row number |
| `unit_group` | int64 | which sector the unit belongs to |
| `output_commodity` | int64 | what it produces |
| `technology_kind` | int8 | 0 Leontief, 1 Cobb-Douglas |
| `technology_scale` | f64 | scale coefficient |
| `input_offsets` | int64[n_units + 1] | bounds of each unit's window into the flat input arrays |
| `input_commodity` | int64[n_inputs] | which commodity each input is |
| `input_coefficient` | f64[n_inputs] | an input coefficient under Leontief, an exponent under Cobb-Douglas |

**Consumer units.** `consumer_id` (int64, equal to the row number) and `consumer_group`
(int64).

**`extra` bags.** `commodity_extra`, `unit_extra` and `consumer_extra` hold named arrays whose
leading dimension is their table's row count. Nothing requires a particular key to be present;
these names are conventions that loaders write and prefabs read.

| table | key | shape | meaning |
|---|---|---|---|
| consumer | `entitlement` | f64[n_consumers] | consumption entitlement, an exogenous flow |
| consumer | `utility_exponent` | f64[n_consumers, k] | Cobb-Douglas utility exponents |
| consumer | `utility_exponent_commodity` | int64[k] | which commodity each of those columns is |
| unit | `effort_c`, `effort_s`, `effort_k` | f64[n_units] | behavioural parameters of the dep1ex worker-council closed form |

## `Plan`

One period's plan, in two layers.

**Physical layer.** Present whatever the mechanism believes about economics.

| field | type | meaning |
|---|---|---|
| `output` | f64[n_units] | what each producing unit makes |
| `input_use` | f64[n_inputs] | what it uses, aligned with `Economy`'s flat input arrays |
| `consumption` | f64[n_consumers, k] | who gets how much of each private good |
| `consumption_commodity` | int64[k] | which commodity each consumption column is |
| `provision` | f64[n_commodities] | shared quantity of each public good; 0 for every other commodity |

Input use is stored rather than derived. Where a technology allows substitution, the input mix
is a decision the mechanism made, and recomputing it afterwards would replace that decision
with the recomputing tool's own theory. Endowment use is different: it is a plain aggregation
of input use, so `plan.endowment_use(economy)` derives it.

**Extension layer.** `valuation` is a named-array bag, because a mechanism that computes
labour times has no prices and one that iterates on prices has no labour times. Predefined
keys are `indicative_price`, `labor_value` and `shadow_price` (f64[n_commodities], with NaN
for commodities the mechanism leaves undefined) and `income` (f64[n_consumers]). Any other key
is yours.

Aggregates over commodities are accessors, not stored columns: `total_output`,
`total_input_use`, `total_consumption` and `endowment_use`, each taking the economy the plan
was made for.

## What this library is answerable for

The infrastructure half: the data model, the optional invariant checks, the definitions of the
measures, deterministic seed distribution, and the provenance record of a run.

The coordination method is yours. Whether your implementation is correct and whether your
conclusions follow are yours too. The library does not read your code, does not judge whether
two procedures are equivalent, and does not pick the quantity a comparison rests on; you
declare that, and the declaration goes in the run manifest.
