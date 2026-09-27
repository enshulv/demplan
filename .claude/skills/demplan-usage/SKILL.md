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
  model and the rules. Start from the README's code blocks: the test suite runs the ones that need
  no downloaded data and compiles every other one.
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
`curl -sSL -o dep1ex01.clj.gz https://www.szcz.org/depexperiments/dep1ex01.clj.gz` (56 MB); in
Windows PowerShell 5.1 type `curl.exe`, since `curl` there is an alias for `Invoke-WebRequest`.
The WIOD files come from a browser, see below.

## Reproduce a published result

```python
from demplan import load_dep1ex, run
from demplan.prefabs import HahnelBook2021
from demplan.prefabs.hahnel import stateless

economy = load_dep1ex("dep1ex01.clj.gz")        # endowment defaults to 1000, the paper's value
result = run(HahnelBook2021(), economy, seed=0)
print(result.summary.rounds, result.summary.converged, result.summary.diverged)
```

- `HahnelBook2021(threshold_pct=3.0)` runs at the 3% threshold.
- The prefab's price rule, `book_2021_rule`, is the rule of the program that produced the tables
  of Hahnel (2021), ch. 9, not the rule as printed on p. 181 of the book: its step multiplier is
  the previous round's imbalance capped at 0.25, and the step has a floor of 0.001. Tell the
  researcher this when they cite a reproduction number. The comparison with the book's tables
  is in the README and in `docs/research/reproduction.md`.
- The book's two-year experiments (warm start, Tables 9.4 and 9.6) run through
  `demplan.run_periods` with `perturb_exponents` as the change between years and `WarmStart` as
  the next procedure. `increasing_returns` builds the economy of Table 9.6, and
  `real_gdp_growth` computes the growth figure both tables report.
  `research/bench/hahnel_book.py` runs all five tables.
- The endowment of natural resources and labour is a parameter of `load_dep1ex` because it
  matters: the round count changes with it.

## Load real input-output data (WIOD)

`load_wiod(path, year, labor=None, sea=None, exchange_rates=None)` reads one year (2000 to 2014) of
the WIOD 2016 release and returns a `WiodTable` with `economy` and `observed`. The researcher
downloads the files in a browser from <https://doi.org/10.34894/PJ2M1C> (the site serves a bot
check to `curl`): `WIOTS_in_EXCEL.zip` (`path`; leave it packed), and for labour
`Socio_Economic_Accounts.xlsx` (`sea=`) and `Exchange_Rates.xlsx` (`exchange_rates=`). The data is
CC BY 4.0; cite Timmer et al. (2015), as the release asks (entry in the README's references).

- **The economy.** One commodity per product (44 economies times 56 industries), one Leontief unit
  per product with positive output, one consumer unit per final-demand column. Every value is
  millions of US dollars at current prices; say so before a result is read in physical terms.
- **Labour is the researcher's choice; ask, do not pick.** `labor=None` (the default) builds no
  labour commodity. `"hours"` reads hours worked by employees from the SEA; `"compensation"` reads
  compensation of employees and needs the exchange rates too. Both leave out the self-employed.
  Units without a figure (the rest of the world always, China under hours) get no labour input,
  and `unit_extra["labor_observed"]` is 0 for them: a labour total or a labour-minimising plan
  treats their output as free. Some units record output and no intermediate purchases (29 in
  2014), so without labour they need no input at all.
- **The observed plan.** `observed` is an `AllocatedPlan` of the year's recorded flows: gross
  output, intermediate use, final demand with its negative entries (inventory draw-downs) kept,
  `shared_use` all 0. Compare a mechanism's plan with it through `compare_plans`. Before running
  `reference_solution` on a year, the researcher has to state what negative final demand means,
  because a floor on final consumption cannot be negative.
- **Two warnings, both `UserWarning` subclasses in `demplan.io`.** `WiodUnproducedInputs`: units
  use products that have no producing unit (the rest of the world's `M73` in every year); those
  uses are not input entries, each unit's total is in `unit_extra["unproduced_input_use"]`, and
  the observed plan's supply minus use on those products equals what the units drew.
  `WiodLaborGap` names the economies whose units have no labour figure. Report both warnings to
  the researcher rather than silencing them.

## Change one part of a published procedure

`HahnelBook2021(price_rule=rule)` swaps the price-update rule and keeps the rest. A rule is called
once a round with the price, the surplus, the relative imbalance and the state the previous round
returned, all read-only copies, and returns `(next_price, next_state)`; `initial_state(n)` gives
round one's state, and the board carries the state between rounds. `stateless(f)` turns a function
of the first three arrays into a rule:

```python
import numpy as np

def proportional(price, surplus, imbalance):
    return price * (1 - 0.2 * np.sign(surplus) * imbalance)

result = run(HahnelBook2021(price_rule=stateless(proportional)), economy, seed=0)
```

`demplan.prefabs.hahnel.book_2021_rule` is the prefab's own rule in the same shape.
`CouncilModel(economy, threshold_pct, price_rule)` in the same package is the councils' side of the
procedure, with `initial_state`, `step`, `converged` and `plan_of`, for a researcher who wants a
different loop around the same councils.

## Write a new coordination procedure

A coordination procedure is any object with `solve(self, economy, seed) -> Plan`. Nothing has to
be subclassed or registered.

**`Economy`** is one period, as column tables: commodities (`endowment`), producing units, and
consumer units. Producing units store their inputs and outputs flat: unit `i` owns
`input_commodity[input_offsets[i]:input_offsets[i+1]]` (see `economy.inputs_of(i)`) and the output
entries `output_offsets[i]` to `output_offsets[i+1]` of `output_commodity` and
`output_coefficient`. A unit with several output entries has joint products. `technology_kind` is a
text label per unit; `LEONTIEF` and `COBB_DOUGLAS` are the two the library reads by itself.
It has no prices and **no classes of commodity**: labels a loader or prefab needs live in the
`extra` bags under keys it owns, and the library never reads them. dep1ex's five classes are in
`commodity_extra["hahnel_kind"]`, and `demplan.prefabs.hahnel` turns them into commodity indices
with `private_goods`, `shared_goods`, `intermediate_goods`, `natural_resources`, `labor`,
`resources` and `bads`. It is immutable; build the next period with `dataclasses.replace`, which
validates again. Identifiers currently equal row numbers.

**Declarations.** Whenever a library tool needs a grouping of commodities (which ones are labour,
resources, used in common, bads), the caller passes it as a one-dimensional int64 array of
commodity indices: `counted=`, `shared=`, `resources=`, `bads=`, `commodities=`. A duplicate or
out-of-range index raises `ValueError`. Pass the prefab's helpers for dep1ex, and say which
declaration you made when you report a number that depends on it.

**`Plan`** has a physical layer and an extension layer:

| Field | Shape | Notes |
|---|---|---|
| `output` | `f64[n_outputs]` | required, one per output entry, aligned with the flat output arrays |
| `input_use` | `f64[n_inputs]` | required, aligned with the flat input arrays |
| `consumption` | `f64[n_consumers, k]` | pass `None` if the mechanism has no per-consumer consumption |
| `consumption_commodity` | `int64[k]` | which commodity each consumption column is; `None` with the above |
| `shared_use` | `f64[n_commodities]` | quantity consumer units use in common (non-rival use), attributed to none of them; a use, not a supply; `None` if not modelled |
| `valuation` | name → `f64` array | prices, labour values, shadow prices, `income` and `expenditure` per consumer unit; keys and lengths are checked |
| `extra` | name → array | any other physical quantity, one row per unit, consumer or commodity |

Arrays must already have the right dtype: the library refuses rather than converts. An accessor
over a field declared absent raises `PlanFieldAbsent` instead of returning zero.
`StatedPlan` and `AllocatedPlan` distinguish what councils asked for from what an allocation gave.

If the procedure iterates to a fixed point, drive it with
`iterate(init, step, converged, max_rounds, plan_of=...)`. The library then counts rounds, applies
the cap and stops on non-finite values. Rounds are calls to `step`; convergence is never tested on
the starting state. State this definition whenever a round count is reported.

`demplan.tools` has the closed forms of Leontief and Cobb-Douglas technology, for units with one
output entry. `plan.endowment_use(economy, resources)` needs the resources declared;
`plan.total_output(economy)` counts every output entry under its own commodity.

## Read what a plan leaves over or short

Every `run` carries a report on its plan in `result.differences`; `plan_differences(economy, plan)`
computes the same report for any plan, including one from a file or someone else's code.

```python
from demplan import INDICATIVE_PRICE, plan_differences
from demplan.prefabs import hahnel

plan = result.plan
report = plan_differences(economy, plan, bads=hahnel.bads(economy), price=INDICATIVE_PRICE)
report.material_balance.difference     # per commodity: output + endowment - input use - consumption - shared_use
report.budget.difference               # per consumer unit: income - expenditure
report.non_negativity.negative_count   # per field and per price key
```

- **Nothing is a verdict.** Differences are signed, and no field says pass or fail. What gap
  matters is the researcher's statement; do not describe a difference as a violation.
- **N/A is `None` with a reason.** Read `why_not_computed` before reporting a number as missing. The
  material balance is N/A when the plan declares `consumption` or `shared_use` absent. The budget
  difference is N/A unless the plan's `valuation` carries the price the caller names with `price=`,
  `income` and `expenditure`; the library never guesses the price key and never falls back to
  `entitlement`. On a Hahnel plan, `price=INDICATIVE_PRICE` is the price the councils' proposals
  were made at.
- `bads=` exempts the listed commodities' prices from the non-negativity check; quantities are
  always checked. `run(..., bads=..., price=...)` passes the declarations on, and
  `differences=False` skips the report.
- Over several periods, `run_periods(..., resources=hahnel.resources(economy))` adds
  `result.differences`, a `PeriodDifferences`: cumulative use of the declared resources against
  the initial endowment, the consumer-unit count per period, and a four-row `coverage` table.
  Capital stock and the stock-flow identity are always listed as not computed, because the data
  model has no stock. `constraints=` records which rows the study treats as constraints; the
  library only echoes it.
- `check_homogeneity(procedure, economy, seed, rescale, factor)` runs twice and compares the plans
  with `compare_plans`. `rescale` states what is nominal: `hahnel.scale_starting_price` tests
  start-independence, `hahnel.scale_nominal_quantities` scales the initial price, the entitlements and the
  workers' `effort_s` together.
  The report has no tolerance.
- `input_use_on(economy, plan, hahnel.labor(economy))` is the labour total of a plan, and
  `compare_plans(a, b)` gives the largest relative difference per physical field. Other
  indicators (welfare, GDP) are theory-laden and belong in the researcher's own code.

## Check a plan against a technology

`technology_margins(economy, plan, technologies)` gives, per output entry, what the unit's
planned inputs can deliver minus what the plan records. Negative means the plan asks for more
than the inputs produce.

```python
from demplan import technology_margins

margins = technology_margins(economy, plan, {hahnel.TECHNOLOGY: hahnel.technology()})
margins.margin, margins.computed, margins.missing
```

- The library reads `LEONTIEF` and `COBB_DOUGLAS` by itself. Any other label, including the dep1ex
  label `hahnel.TECHNOLOGY` (Cobb-Douglas with an effort factor), is read only when a technology is
  passed for it; otherwise its units are left out and counted in `missing`. Do not report a plan as
  technically feasible when `missing` is not empty.
- A researcher's own technology is a class with `label` and `margin(economy, plan, unit)`. For
  the common case, `SeparableTechnology(label, inputs, outputs)` joins an input side (`Leontief`,
  `CobbDouglas`, or a class with `activity`) with an output side (`SingleOutput`, `FixedRatios`,
  or a class with `deliverable`). `FixedRatios` is never attached by default: fixed output ratios
  for joint products are an assumption the researcher states.

## Compare with the reference solution

```python
from demplan import MinimizeLabor, input_use_on, reference_solution
from demplan.prefabs import hahnel
from demplan.tools.linearize import linearize

public = hahnel.shared_goods(economy)
floor = plan.total_consumption(economy)              # private goods, as the councils stated them
floor[public] = plan.total_output(economy)[public]   # public goods: what the plan produces
objective = MinimizeLabor(floor, counted=hahnel.labor(economy), shared=public)
best = reference_solution(linearize(economy, plan), objective)
print(input_use_on(economy, plan, hahnel.labor(economy)), best.objective_value)
```

With `plan` from the reproduction run above (dep1ex01, 5% threshold) this prints 96539.33… and
53493.73…, the labour totals of the README's comparison.

- The reference solution is a linear program and needs Leontief technology with one output entry
  per unit. `linearize` fixes the input ratios a plan chose; it turns decreasing returns to scale
  into constant returns and anchors the benchmark on the plan being compared. **A gap computed this
  way is an upper bound, not an estimate.** Say so in any report.
- `MinimizeLabor(targets, counted, shared=None)` counts only the input use of `counted` as a cost;
  `MaximizeWeightedConsumption(weights, shared=None)` weights final consumption. Both carry
  theoretical commitments, which their docstrings state. `shared` commodities go to the plan's
  `shared_use` whole; every other commodity with a floor or weight is split evenly across consumer
  units.
- `plan.extra["consumer_demand"]` and `plan.shared_use` hold public goods at the councils' stated
  level, divided by the number of councils; that is not the same as the public-good floor above,
  which is the plan's output.

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
- Report every declaration a number depends on (`counted`, `shared`, `resources`, `bads`, `price`)
  and every technology passed to `technology_margins`. The run configuration file does not record
  them yet.
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
