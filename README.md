# cyberstride

Shared research infrastructure for democratic economic planning.

Write a coordination procedure, run it on a published economy, and get the full plan back as
plain arrays, raw enough that any metric can be recomputed from it afterwards. The library
covers democratic and participatory planning; the benchmark it offers against a mechanism is a
centrally computed optimum under an objective function you declare, not a market.

MIT licensed. Status: early. What exists today is the data model, the dep1ex loader, one
published procedure, the loop and seed tools, and the determinism self-test. Also present: the linear-programming reference
optimum for Leontief economies, with a `linearize` tool for economies whose technology is
Cobb-Douglas. Not yet built: the on-disk output format and run manifest, and the invariant
residual toolbox. Those are the next two pieces, in that order.

## Install

There is no release on PyPI yet. Building from source needs a Rust toolchain
(<https://rustup.rs>), because the data model and the loaders are Rust behind a Python
extension module. Python 3.10 or newer; the only runtime dependency is numpy.

```sh
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install maturin numpy
maturin develop --release        # first build takes about a minute
```

`maturin develop` without `--release` builds faster and runs slower; use the release build
when you are timing anything.

The dep1ex archives are 56 MB each, gzipped:

```sh
curl -sSL -o dep1ex01.clj.gz https://www.szcz.org/depexperiments/dep1ex01.clj.gz
```

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
plan = result.plan

supply = plan.total_output(economy) + economy.endowment
demand = plan.total_input_use(economy) + plan.extra["consumer_demand"]
gap = np.abs(2 * (supply - demand)) / np.where(supply + demand > 0, supply + demand, 1.0)

print(result.summary.rounds, result.summary.converged, gap.max())
```

`result.summary` also carries `diverged`. A run that stops because a plan went non-finite is a
different fact from one that spends its round cap while still converging: the first says
something about the mechanism, the second about the budget it was given. Both are `None` when
the procedure never called `iterate`, because then the library saw no loop to judge.

`plan.provision` is the supply side of a public good, the quantity produced and shared, and it
is already inside `total_output`. The demand side is `plan.extra["consumer_demand"]`: what the
consumer councils asked for, one entry per commodity, private goods included. It is the whole
consumption side of the balance, which is why `total_consumption` is not added to it.

Nothing in that last calculation is privileged. `Plan` stores the full configuration, so any
measure of feasibility, cost or fairness you want to argue about is a few lines away from the
same output.

## Write your own coordination method

A coordination method is any object with one method:

```python
def solve(self, economy: Economy, seed: int) -> Plan: ...
```

That is the whole interface. Implementing it is enough to get the data model, the loaders,
the timing and round accounting and the determinism self-test; your code does not have to be
merged into this library to get any of it.

If the change you want is to the price rule alone, `HahnelSlides2020` takes one. A price rule
is a function of the price the proposals were made at, the surplus at that price and the
relative imbalance, returning the next price. Everything else, the councils and the
aggregation, stays as the 2020 slides describe it:

```python
import numpy as np
from cyberstride import run
from cyberstride.prefabs import HahnelSlides2020


def proportional_rule(price, surplus, imbalance):
    """Move every price by a fifth of its relative imbalance."""
    return price * (1 - 0.2 * np.sign(surplus) * imbalance)


result = run(HahnelSlides2020(price_rule=proportional_rule), economy, seed=0)
print(result.summary.rounds, result.summary.converged)
```

Return a new array each round. The three arguments arrive as read-only views, which stops a
direct write; writing through `arg.base`, or returning a buffer you keep and write again next
round, still reaches the price the plan records and the imbalance the loop tests convergence
on, and neither raises. Closing that needs the board to own those arrays, which it does not
yet.

`cyberstride.prefabs.hahnel_2020_slides.slides_2020_rule` is the published rule in the same
shape, so you can compare against it or wrap it.

To change more than the rule, write `solve` yourself. `CouncilModel` in that same module is
the councils' side of the slides procedure on its own, with `initial_state`, `step`,
`converged` and `plan_of` in exactly the shape `iterate` takes, so a procedure that wants a
different loop can drive it directly; using it commits you to the theory its docstring
states. `cyberstride.tools` holds the closed forms of the two technologies the data model
knows about.

If your method drives a fixed point, running the loop through `iterate` lets the library count
rounds, apply a cap and watch for divergence, none of which it can see from outside. Pass
`plan_of` to say how a state reads as a plan; `keep_trajectory=False` keeps the divergence
check without holding one plan per round.

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

**Building one by hand.** Seven commodities, three producing units and two consumer units,
with Leontief technology. Integer columns are int64 and the kind markers int8; `Economy`
checks that, and the check is the reason a plan built for one economy cannot be quietly
aggregated against another.

```python
import numpy as np
from cyberstride import CommodityKind, Economy, TechnologyKind

kinds = [CommodityKind.PRIVATE_GOOD, CommodityKind.PRIVATE_GOOD, CommodityKind.PUBLIC_GOOD,
         CommodityKind.INTERMEDIATE, CommodityKind.INTERMEDIATE,
         CommodityKind.NATURAL_RESOURCE, CommodityKind.LABOR]

economy = Economy(
    period=0,
    commodity_id=np.arange(7, dtype=np.int64),
    commodity_kind=np.array(kinds, dtype=np.int8),
    endowment=np.array([0.0, 0.0, 0.0, 0.0, 0.0, 100.0, 200.0]),
    unit_id=np.arange(3, dtype=np.int64),
    unit_group=np.array([0, 0, 1], dtype=np.int64),
    output_commodity=np.array([0, 1, 2], dtype=np.int64),           # two private, one public
    technology_kind=np.full(3, TechnologyKind.LEONTIEF, dtype=np.int8),
    technology_scale=np.ones(3),
    input_offsets=np.array([0, 3, 5, 8], dtype=np.int64),           # unit i owns [o[i], o[i+1])
    input_commodity=np.array([3, 5, 6, 4, 6, 3, 4, 6], dtype=np.int64),
    input_coefficient=np.array([0.4, 0.2, 0.5, 0.3, 0.6, 0.1, 0.2, 0.4]),
    consumer_id=np.arange(2, dtype=np.int64),
    consumer_group=np.array([0, 1], dtype=np.int64),
    consumer_extra={"entitlement": np.array([1000.0, 1500.0]),
                    "utility_exponent": np.array([[0.5, 0.3, 0.2], [0.4, 0.4, 0.2]]),
                    "utility_exponent_commodity": np.arange(3, dtype=np.int64)},
)
economy.validate()
```

Construction validates already; the last line is there to say so. Nothing in this economy
produces commodities 3 and 4, so a scenario you would draw conclusions from needs units for
them; the schema does not require it.

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

`extra` is a second named-array bag, for physical quantities the fixed fields have no column
for. Each array is one row per producing unit, per consumer unit or per commodity. Two keys
are conventions the dep1ex prefab writes, and both are exported as constants, `EFFORT` and
`CONSUMER_DEMAND`, because reading a plan back needs them: without them the production
function and the material balance cannot be rebuilt from what the plan carries. The `extra`
keys of `Economy` are the mechanism's own input parameters and stay plain strings.

| key | shape | meaning |
|---|---|---|
| `effort` | f64[n_units] | effort each unit chose, when the production function has an effort factor |
| `consumer_demand` | f64[n_commodities] | what the consumer councils asked for per commodity, as the mechanism balanced it against supply: for a private good the whole total, the same one `consumption` holds; for a public good the total already divided by the number of consumer councils; for a commodity that is neither, the whole total; 0 where no council asked for it |

Aggregates over commodities are accessors, not stored columns: `total_output`,
`total_input_use`, `total_consumption` and `endowment_use`, each taking the economy the plan
was made for.

## What this library is answerable for

The infrastructure half: the data model, the loaders, deterministic seed distribution, the
determinism self-test, and, once built, the invariant residuals and the provenance record of
a run.

The coordination method is yours. Whether your implementation is correct and whether your
conclusions follow are yours too. The library does not read your code, does not judge whether
two procedures are equivalent, and does not pick the quantity a comparison rests on; you
declare that, and once the run manifest exists the declaration goes there.
