# demplan

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23010110.svg)](https://doi.org/10.5281/zenodo.23010110)
[![PyPI](https://img.shields.io/pypi/v/demplan)](https://pypi.org/project/demplan/)

Shared research infrastructure for democratic economic planning.

## Where to start

The [wiki](https://github.com/enshulv/demplan/wiki) holds the guides: a tutorial that starts from
an empty computer, one page per planning mechanism, and a reference for every public name. This
README explains why the library exists and what reproducing the published experiments found.

| You are | Start with |
|---|---|
| A researcher who has never used Python and wants to run or compare planning mechanisms | [Tutorial: Before you start](https://github.com/enshulv/demplan/wiki/Tutorial-Before-You-Start), then the tutorial pages in order |
| A researcher who wants a one-page overview | [For Researchers](https://github.com/enshulv/demplan/wiki/For-Researchers) |
| Looking for the exact model and formulas of a planning mechanism | [Mechanisms](https://github.com/enshulv/demplan/wiki/Mechanisms) |
| A researcher with a planning mechanism of your own you want to run on this data | An [issue](https://github.com/enshulv/demplan/issues) with the paper, pseudocode or code that states it; the maintainer adds it to the library. To write it yourself, [Writing your own procedure](https://github.com/enshulv/demplan/wiki/Tutorial-Writing-Your-Own-Procedure) |
| Comparing with the published experiments or their implementations | [Limitations of Existing Implementations](https://github.com/enshulv/demplan/wiki/Limitations-of-Existing-Implementations) |
| Looking up a function, parameter or error message | [Reference index](https://github.com/enshulv/demplan/wiki/Reference-Index) |
| Asking how far to trust the results | [Quality Assurance](https://github.com/enshulv/demplan/wiki/Quality-Assurance) |
| A developer who wants to contribute code, data loaders or documentation | [For Contributors](https://github.com/enshulv/demplan/wiki/For-Contributors) and [CONTRIBUTING.md](CONTRIBUTING.md) |

**Wiki contents**

- **Tutorial:**
  1 [Before you start](https://github.com/enshulv/demplan/wiki/Tutorial-Before-You-Start) ·
  2 [Installing](https://github.com/enshulv/demplan/wiki/Tutorial-Installing) ·
  3 [First run](https://github.com/enshulv/demplan/wiki/Tutorial-First-Run) ·
  4 [Reading a plan](https://github.com/enshulv/demplan/wiki/Tutorial-Reading-A-Plan) ·
  5 [Comparing with the reference solution](https://github.com/enshulv/demplan/wiki/Tutorial-Comparing-With-The-Reference-Solution) ·
  6 [Several periods](https://github.com/enshulv/demplan/wiki/Tutorial-Several-Periods) ·
  7 [Real input-output data](https://github.com/enshulv/demplan/wiki/Tutorial-Real-Input-Output-Data) ·
  8 [Building your own economy](https://github.com/enshulv/demplan/wiki/Tutorial-Building-Your-Own-Economy) ·
  9 [Writing your own procedure](https://github.com/enshulv/demplan/wiki/Tutorial-Writing-Your-Own-Procedure) ·
  10 [Checking your mechanism](https://github.com/enshulv/demplan/wiki/Tutorial-Checking-Your-Mechanism) ·
  11 [Reproducible results](https://github.com/enshulv/demplan/wiki/Tutorial-Reproducible-Results)
- **Mechanisms:**
  [Overview](https://github.com/enshulv/demplan/wiki/Mechanisms) ·
  [Hahnel (2021)](https://github.com/enshulv/demplan/wiki/Mechanism-Hahnel-2021)
- **Reference:**
  [Index](https://github.com/enshulv/demplan/wiki/Reference-Index) ·
  [Economy](https://github.com/enshulv/demplan/wiki/Reference-Economy) ·
  [Plan](https://github.com/enshulv/demplan/wiki/Reference-Plan) ·
  [Running a procedure](https://github.com/enshulv/demplan/wiki/Reference-Running) ·
  [Reference solution](https://github.com/enshulv/demplan/wiki/Reference-Reference-Solution) ·
  [Checks and residuals](https://github.com/enshulv/demplan/wiki/Reference-Checks-And-Residuals) ·
  [Loaders](https://github.com/enshulv/demplan/wiki/Reference-Loaders) ·
  [Hahnel prefab](https://github.com/enshulv/demplan/wiki/Reference-Hahnel) ·
  [Run configuration](https://github.com/enshulv/demplan/wiki/Reference-Run-Configuration) ·
  [Errors](https://github.com/enshulv/demplan/wiki/Reference-Errors)
- **Guides:**
  [For Researchers](https://github.com/enshulv/demplan/wiki/For-Researchers) ·
  [For Contributors](https://github.com/enshulv/demplan/wiki/For-Contributors) ·
  [Quality Assurance](https://github.com/enshulv/demplan/wiki/Quality-Assurance) ·
  [Limitations of Existing Implementations](https://github.com/enshulv/demplan/wiki/Limitations-of-Existing-Implementations) ·
  [AI Development Guide](https://github.com/enshulv/demplan/wiki/AI-Development-Guide) ·
  [Glossary](https://github.com/enshulv/demplan/wiki/Glossary)

## Purpose

Democratic economic planning has no shared research infrastructure, and it needs one.

Neighbouring fields show what that infrastructure buys. Agent-based and generative social
simulation has Mesa [13], Concordia [10] and AgentSociety [11]: libraries where a researcher
starts from a working model in an afternoon, and where two studies built on the same library
can be compared because they share a data model, a loop and an output format. Research on
democratic planning has nothing comparable. It is scattered across one-off implementations,
each with its own data model:

- **The same model keeps being rewritten.** The participatory planning model of Hahnel and
  Szczepanczyk has been implemented at least four times since 2017 (`pequod2` in NetLogo,
  `pequod-clj`, `pequod-cljs`, `pequod-plus`), in three languages, and none of them became a
  library someone else could build on. Other groups, such as
  OLIN-EP [7], I-EPOS [8] and Economic-Planning [9], each define their own data model, so no
  group's economy runs in another group's solver.
- **Published results are hard to reproduce.** Re-running the published participatory planning
  experiments (see [below](#reproducing-the-published-experiments)) showed that the published
  round counts come back only with the price-update rule of the program that produced them. No
  published text states that rule in full: the book's description [3, p. 181] omits that the
  multiplier is the previous round's imbalance and that the step has a floor, and with the rule
  as printed each of the first five experiments reaches the 5% threshold one or two rounds
  early. The author's own run log for the upstream code records 160 to 253 minutes for each of
  eleven complete runs.

None of this is a failing of the researchers involved. It is what happens when economists also
have to be software engineers. Research and infrastructure are different kinds of work, and
they are best divided: researchers ask the questions, and engineers build the tools that let
them answer those questions quickly and soundly. Economists should not have to spend their time
writing loaders, seeding schemes and convergence checks. AI assistance does not remove that
cost. Researchers have limited time to direct it, and code produced that way does not by itself
have the structure that makes results comparable and reproducible across studies.

demplan is an attempt to provide that infrastructure: one data model that several mechanisms
can run on, deterministic seeding, outputs raw enough to recompute any metric, and a benchmark
that every mechanism can be compared with. Success means less duplicated work in the field. If
someone forks it and does better, that also counts as success.

It is developed by an independent developer, with no funding from any organisation and no
commercial purpose, out of a long-standing interest in the field, and it will be maintained for
the long term. If you have the skills and the interest, contributions are very welcome; see
[Contributing](#contributing). Citing and sharing the project helps more people find it.

## What it does

Write a coordination procedure, run it on a published economy, and get the full plan back as
plain arrays, raw enough that any metric can be recomputed from it afterwards. The library
covers democratic and participatory planning; the benchmark it offers against a mechanism is a
centrally computed optimum under an objective function you declare, not a market.

MIT licensed. Status: early. What exists today is the data model, loaders for the dep1ex
archives and the WIOD world input-output tables, one published procedure, the loop and seed tools, the determinism self-test, the run configuration
document, the report of what a plan leaves over or short that every run carries, a check of
plans against technologies, and the linear-programming reference optimum for Leontief economies
with a `linearize` tool for Cobb-Douglas ones. What is missing is listed under
[Limitations](#limitations-and-open-work). How the library is tested and reviewed is described
in the [quality assurance](https://github.com/enshulv/demplan/wiki/Quality-Assurance) page of
the wiki. Issues and comments are welcome.

## Reproducing the published experiments

The reference point is the participatory annual planning experiments of Hahnel, Szczepanczyk
and Weisdorf [2, 3], with the model described in [1, 3] and the pseudocode in [4]. Chapter 9 of
Hahnel (2021) [3] lists the result of each of the 40 experiments in Tables 9.1, 9.2 and 9.4 to
9.6 (pp. 178–185). Their input data, the `dep1ex01` to `dep1ex40` archives, is public [5]; the
round counts are not in the archives and can only be obtained by running them again. The program
that produced the book's tables is `pequod-cljs` [14], named in the book's note 7 to chapter 9.

**All 40 experiments, against the book's tables.** Prefab `demplan.prefabs.hahnel`
(`HahnelBook2021`), endowment 1000, initial price 700. Year one runs to the 3% threshold; year
two starts from year one's last prices and price-rule state, after the book's random change to
the exponents. The book's random draws cannot be recovered, so the two-year rows are over 10
seeds per experiment and are compared as distributions.

| Table in [3] | Book: mean [min, max] | demplan: mean [min, max] | Runs |
|---|---|---|---|
| 9.1 cold start, first round with every imbalance below 5% | 11.850 [11, 13] | 11.850 [11, 13] | 40 |
| 9.2 cold start, first round with every imbalance below 3% | 19.225 [18, 22] (text: 19.2) | 19.200 [18, 22] | 40 |
| 9.5 rounds from every imbalance below 10% to below 5% | 3.775 [3, 5] | 3.775 [3, 5] | 40 |
| 9.4 year two, first round below 5% | 6.525 [5, 8] (text: 6.575) | 6.287 [5, 8] | 400 |
| 9.4 real GDP growth, % | 2.446 [2.178, 2.659] | 2.477 [2.143, 2.720] | 400 |
| 9.6 year two with increasing returns, first round below 5% | 6.275 [5, 8] | 6.197 [5, 7] | 400 |
| 9.6 real GDP growth, % | 1.860 [1.659, 2.101] | 1.852 [1.577, 2.116] | 400 |

The book's means are computed from the 40 printed entries of each table. Every run converged.

Experiment n of the book is `dep1ex{n}` on the public site and `dep1ex{60+n}` in the program's
repository. For experiments 1 to 18 the input files are identical apart from the namespace on
the first line; for all 40, the program's output files `dep1ex61.csv` to `dep1ex100.csv` [14,
commit `df6dc57`] match demplan's runs round by round, and the rows of the book's tables apart
from the four cells below.

demplan and the program's output agree on every experiment in Tables 9.1, 9.2 and 9.5. The
printed tables differ from that output in four cells. In Table 9.2, experiments 2 and 3 are
transposed (printed 19 and 20, output 20 and 19), and experiment 38 is printed as 19 (output 18,
with a worst imbalance of 2.9992% in round 18). In Table 9.4, experiment 16 is printed as 5
(output 7). The book's text follows the output: its 3% mean of 19.2 (p. 179) is the output's
768/40, and its warm-start mean of 6.575 (p. 183) is the output's 263/40, not the printed
table's 6.525. The GDP values of Table 9.4 are the output's,
truncated to three decimals, in all 40 experiments.

As in the book, a warm start roughly halves the round count (11.85 to 6.29 here, 11.85 to 6.575
in the book); tightening the threshold from 5% to 3% costs 7.35 more rounds (the book: "7.35
more iterations", p. 179); and with a fifth of the worker councils under increasing returns
every run converges (the book: "The procedure converged in all 40 experiments", p. 185).

**The price-update rule.** The published round counts come from the rule the program runs, in
`csvgen.clj` at commit `71e44d3`. For each commodity in round k, with v the relative imbalance:

`w_k = max(0.001, min(v_{k−1}, 0.25) · (1.05 − 0.5^{v_k}))`, with `v_{−1} = 0.25`.

The multiplier is the previous round's imbalance, capped at 0.25; the exponent is this round's,
uncapped. The published texts state this rule only in part:

| Source | What it says | dep1ex01–05, cold start, 5% |
|---|---|---|
| Book [3, p. 181] | `w = v(1.05 − 0.5^v)`, with 0.25 substituted "for v where it first appears in the price adjustment formula, but not where it appears as an exponent"; no lag, no floor | 11, 11, 10, 11, 11 |
| 2020 slides [2, p. 5] and 2023 paper [4, p. 7] | the same formula, "except when v > 0.25"; the slides do not say what happens then, and the paper's "then v = 0.25", read literally, caps both occurrences of v. Capping both: | 14, 13, 13, 14, 13 |
| 2023 paper [4, p. 10], pseudocode | multiply the adjustment by "the corresponding price adjustment of the previous round", take the smaller, floor at 0.001. The program shows that the previous-round quantity is the capped imbalance | — |
| The program [14] | the rule above | **12, 12, 12, 12, 12** (Table 9.1: 12, 12, 12, 12, 12) |

With the program's rule, demplan's worst imbalance in every round of all 40 experiments matches
the program's output files to within 1.9e-12 percentage points.

Two findings about the published model itself:

- The public-good pricing rule has no effect on any number in the plan. Under Cobb-Douglas
  utility with councils spending their whole entitlement, dividing the price by the number of
  councils multiplies the stated quantity by the same number, and aggregation divides it back.
  Removing the rule leaves the round count unchanged, and every quantity and price in the plan
  stays within 6e-14 relative of the run that applies it. The round counts above therefore do
  not test that rule.
- None of the runs in the run log of the upstream `pequod-plus` [6] uses the published `dep1ex`
  data: the round counts come from `ppex` experiments with 300 to 3000 councils, and the timed
  runs are `ppex` experiments.

What is not reproduced: the book's year-two round counts experiment by experiment, because its
random draws are not recoverable, and Table 9.6 experiment by experiment, because its output
files are not in the program's repository. Details, scripts and every intermediate number are in
[docs/research/reproduction.md](docs/research/reproduction.md) and
[docs/research/upstream-code-issues.md](docs/research/upstream-code-issues.md). Where the
published texts, tables and implementations disagree is listed with sources on the wiki page
[Limitations of Existing Implementations](https://github.com/enshulv/demplan/wiki/Limitations-of-Existing-Implementations).

**Speed.** The upstream author's log for `pequod-plus` [6], on the code before its SQLite-based
version, reads: "An iteration with 60,000 councils now takes about two minutes, which would mean
a completion time from start to finish of around two hours, as opposed to something like 12
hours" (`docs/notes.txt`, line 74, 2026-01-21). demplan's `HahnelBook2021` on dep1ex01 (30,000
worker councils, 30,000 consumer councils, 500 commodities) takes about 0.06 s per round: 12
rounds to the 5% threshold in 0.76 s, the median of three runs on one machine that was running
other work at the time. The data and the machines differ, so the comparison shows an order of
magnitude, not a ratio.

## A first comparison between two mechanisms, and why it is not citable yet

On dep1ex01, the iterative procedure converges in 12 rounds and uses 96,539.3 units of labour.
The linear-programming reference solution, asked to deliver the same final consumption at
minimum labour, needs 53,493.7. The ratio is 1.80. The two numbers come from this:

```python
from demplan import MinimizeLabor, input_use_on, load_dep1ex, reference_solution, run
from demplan.prefabs import HahnelBook2021, hahnel
from demplan.tools.linearize import linearize

economy = load_dep1ex("dep1ex01.clj.gz")
result = run(HahnelBook2021(), economy, seed=0)
plan = result.plan
labor = hahnel.labor(economy)
public_goods = hahnel.shared_goods(economy)

floor = plan.total_consumption(economy)
floor[public_goods] += plan.total_output(economy)[public_goods]
objective = MinimizeLabor(floor, counted=labor, shared=public_goods)
reference = reference_solution(linearize(economy, plan), objective)

labor_spent = input_use_on(economy, plan, labor)
print(result.summary.rounds, labor_spent, reference.objective_value)
```

"The same final consumption" is a floor on each commodity. For a private good it is the plan's
consumption summed over the consumer councils; for a public good it is what the worker councils
produced of it, `plan.total_output(economy)`, and not `plan.shared_use`, which holds the level
the councils stated: a run that stops at a 5% threshold leaves the two apart. No other
commodity carries a floor. The reference solution runs on the economy linearised at the
iterative plan, totals the input use of the labour commodities, and treats the public goods as
used in common.

That number is an upper bound on the gap, not an estimate of it. The reference solution needs
Leontief technology, dep1ex is entirely Cobb-Douglas, and `linearize` turns decreasing returns
to scale into constant returns, so the optimum it finds is too good. In dep1ex01 a unit's input
exponents plus its effort exponent `effort_c` sum to a median of 0.875, and to less than 1 in
every unit; the input exponents alone sum to a median of 0.80. Linearization is also anchored on the iterative procedure's own
plan. The reference result does not yet report these assumptions; until it does, the ratio
should not be quoted. See
[docs/research/related-implementations.md](docs/research/related-implementations.md).

## Limitations and open work

Honest status, roughly in the order these will be addressed:

- **Two data sources.** The dep1ex archives and the WIOD 2016 release, one year at a time, load.
  EXIOBASE, emission accounts (the WIOD release has none; the environmental accounts published
  for it are not read yet), and the formats of other implementations do not load.
- **No on-disk output format yet.** Plans come back as arrays in memory; the long-format
  Parquet output and the run manifest are not built.
- **The difference reports stop at what one plan and the fixed fields can show.** Material
  balance, the budget and non-negativity are computed for every run, and cumulative resource use
  across periods; technology margins are a separate call (`technology_margins`) rather than part
  of that report. A capital stock, and the identity that carries a stock from one period to the
  next, have no place in the data model, so the cross-period report lists them as not computed.
  The declarations behind a report (`bads`, `price`, `resources`) are not yet recorded in the run
  configuration document, and the reference solution's result carries no report of its own: pass
  its plan to `plan_differences`.
- **The reference solution states less than it assumes.** Leontief only, constant returns after
  `linearize`, closed economy, non-negativity and free disposal are all built in and none of
  them is reported with the result.
- **Identifiers are row numbers.** Removing a row renumbers the rest. Stable identifiers are a
  breaking change and will happen before 1.0.
- **Joint products are in the data model but not yet in every tool.** A producing unit may list
  several outputs; the reference solution, `linearize` and the two technology helpers still
  refuse such units, and a plan has no valid shape yet for an `extra` or `valuation` key holding
  one value per output entry.
- **Your procedure's provenance cannot be declared yet.** The run configuration document records
  a procedure of yours with `declared_origin` null, because `run_configuration` has no argument
  through which to say where it comes from.
- **One published procedure.** Only the procedure of Hahnel (2021) [3] ships as a prefab. Labour-time planning in the tradition of Cockshott and Cottrell [12] and the
  published algorithms of [7, 8, 9] are candidates.
- **Prebuilt packages cover five platforms.** PyPI has wheels for Windows x64, macOS (Apple
  silicon and Intel) and Linux (x86-64 and ARM64, glibc). Elsewhere, such as Windows on ARM or
  Alpine, pip builds from the sdist: maturin fetches a temporary Rust toolchain if none is
  installed, but the build takes minutes and needs a C linker.
- **The design documents are translated.** The records under `docs/` were first written in
  Chinese and translated; wording errors are likely, and reports of them are welcome.

If you work on democratic planning and any of this blocks you, open an issue. Requests from
people with a concrete research question move things up the list.

## Install

Python 3.10 or newer. The runtime dependencies, numpy and scipy, are installed with it.

```sh
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install demplan
```

PyPI has prebuilt wheels for Windows x64, macOS (Apple silicon and Intel) and Linux (x86-64 and
ARM64), so no compiler is needed on these systems. The wiki's
[Installing](https://github.com/enshulv/demplan/wiki/Tutorial-Installing) page walks through each
system step by step.

On other platforms `pip install demplan` builds from the sdist. To change the library itself,
build from a clone; this needs a Rust toolchain (<https://rustup.rs>), because the data model and
the loaders are Rust behind a Python extension module:

```sh
git clone https://github.com/enshulv/demplan
cd demplan
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install maturin numpy scipy
maturin develop --release        # first build takes about a minute
```

`maturin develop` without `--release` builds faster and runs slower; use the release build
when you are timing anything.

The dep1ex archives are 56 MB each, gzipped:

```sh
curl -sSL -o dep1ex01.clj.gz https://www.szcz.org/depexperiments/dep1ex01.clj.gz
```

In Windows PowerShell 5.1, `curl` is an alias for `Invoke-WebRequest` and does not take these
options; type `curl.exe`:

```powershell
curl.exe -sSL -o dep1ex01.clj.gz https://www.szcz.org/depexperiments/dep1ex01.clj.gz
```

The WIOD files are downloaded in a web browser; see [below](#real-input-output-data-wiod).

## Ten lines

`HahnelBook2021` is the iterative price procedure of Hahnel (2021) [3, ch. 9], with the
price-update rule of the program that produced the book's tables; its round counts on all 40
dep1ex archives are compared with the book's tables above. The dep1ex archives it reads are at
<https://www.szcz.org/depexperiments/>.

```python
import numpy as np
from demplan import load_dep1ex, run
from demplan.prefabs import HahnelBook2021

economy = load_dep1ex("dep1ex01.clj.gz")
result = run(HahnelBook2021(), economy, seed=0)
plan = result.plan

supply = plan.total_output(economy) + economy.endowment
demand = plan.total_input_use(economy) + plan.extra["consumer_demand"]
gap = np.abs(2 * (supply - demand)) / np.where(supply + demand > 0, supply + demand, 1.0)

print(result.summary.rounds, result.summary.converged, gap.max())
```

`result.summary` also carries `diverged`. A run that stops because a plan went non-finite is a
different fact from one that spends its round cap while still converging: the first says
something about the mechanism, the second about the budget it was given. `diverged` is `None` in two
cases: the procedure never called `iterate`, so the library saw no loop, or it drove one
without `plan_of`, so the library saw no plan to judge. `rounds` tells those apart.

The demand side here is `plan.extra["consumer_demand"]`: what the consumer councils asked for,
one entry per commodity, private goods included. It is the whole consumption side of the
balance. The same numbers are also filed in the physical layer: `plan.consumption` holds each
council's private goods and `plan.shared_use` the level of each public good used in common,
so `total_consumption` plus `shared_use` adds up to the same demand.

Nothing in that last calculation is privileged. `Plan` stores the full configuration, so any
measure of feasibility, cost or fairness you want to argue about is a few lines away from the
same output.

## What the plan leaves over or short

`run` also reads the plan it returns and reports, per commodity and per consumer unit, what the
plan leaves over or short: `result.differences`. Continuing from the ten lines above:

```python
from demplan import INDICATIVE_PRICE, plan_differences, technology_margins
from demplan.prefabs import hahnel

balance = result.differences.material_balance
print(balance.difference.min(), balance.difference.max())
print(result.differences.budget.why_not_computed)

budget = plan_differences(economy, plan, price=INDICATIVE_PRICE).budget
print(abs(budget.difference).max())

margins = technology_margins(economy, plan, {hahnel.TECHNOLOGY: hahnel.technology()})
print(margins.missing, abs(margins.margin).max())
```

`balance.difference` is supply minus use for every commodity, signed: output plus endowment,
minus input use, consumption and `shared_use`. On dep1ex01 it lies between 14.9 and 45.9, so the
plan leaves some of every commodity unused. The same report carries every term of that sum, so
the ten-line calculation above is one of many you can make from it.

The budget difference is not computed, and the report says why rather than printing a number
(wrapped here):

```text
the budget difference needs a price, income per consumer unit and total expenditure per consumer
unit, all filed by the mechanism in Plan.valuation; this plan has no declared price (pass price=
naming the valuation key the prices are filed under; this plan carries 'expenditure', 'income',
'indicative_price', 'next_indicative_price')
```

The plan carries two price vectors, and which one a budget is reckoned in is yours to say. Named
with `price=`, income minus expenditure is below 3e-12 for every council. A quantity that cannot
be formed is `None` with a reason, never NaN or zero, and the library never borrows another
quantity to fill the gap. `bads=` exempts the prices of the commodities you declare bads from
the non-negativity check, and `differences=False` skips the report.

`technology_margins` checks each producing unit against a technology: what its planned inputs can
deliver minus what the plan records. The library reads the labels `LEONTIEF` and
`COBB_DOUGLAS` by itself. dep1ex units carry the label of the Hahnel production function, which
has an effort factor, so the example passes the prefab's technology in; called without it, the report
lists all 30,000 units under `missing` instead of reading them as plain Cobb-Douglas. With it,
the largest margin is 5.7e-13: the plan's outputs are what its inputs and efforts produce.

`run_periods` does the same for every period and adds cross-period differences: cumulative use of
the resources you declare against the initial endowment, and the change in the number of consumer
units, with a coverage table listing what the data model cannot test. `check_homogeneity` reruns
a procedure on rescaled inputs and reports how far the plan moved, and `compare_plans` and
`input_use_on` are the two indicators the library ships. None of these reports carries a
tolerance or a pass/fail field.

## Real input-output data: WIOD

The World Input-Output Database (WIOD), 2016 release, covers 28 EU countries, 15 other major
countries and a model of the rest of the world, from 2000 to 2014, with 56 industries in each
economy. `load_wiod` reads one year of it into an `Economy`, together with the flows the table
records for that year, laid out as a plan of that economy: the observed plan.

**Getting the files.** Open <https://doi.org/10.34894/PJ2M1C> in a web browser and download
`WIOTS_in_EXCEL.zip` (919 MB), and for labour `Socio_Economic_Accounts.xlsx` and
`Exchange_Rates.xlsx`. The site checks that a visitor is a browser before it serves a file, so a
download started with `curl` receives the check page instead. Leave the zip packed: `load_wiod`
reads the year you ask for straight out of it. The release is licensed under CC BY 4.0. It asks
every user to cite Timmer et al. (2015) [15]; cite the data set as well, as doi:10.34894/PJ2M1C.

With the three files in a folder named `wiod`:

```python
import numpy as np
from demplan import load_wiod, plan_differences

table = load_wiod("wiod/WIOTS_in_EXCEL.zip", 2014, labor="hours",
                  sea="wiod/Socio_Economic_Accounts.xlsx")
economy, observed = table.economy, table.observed
print(economy.n_commodities, economy.n_units, economy.n_consumers)

balance = plan_differences(economy, observed).material_balance
largest = int(np.argmax(balance.difference))
region, industry = economy.commodity_extra["region"], economy.commodity_extra["industry"]
print(region[largest], industry[largest], round(float(balance.difference[largest]), 1))
```

```text
2506 2327 220
ROW M73 6992.5
```

The economy has one commodity per product, 44 economies times 56 industries, 2,464 in all, and
one labour commodity for each of the 42 economies with hours data. Each product with output in
2014 has one Leontief producing unit, whose input coefficients are the table's purchases divided
by its gross output: 2,327 units, since 137 products had no output that year. Each final-demand
column is a consumer unit, five per economy. Every value is millions of US dollars at current
prices, so one unit of a commodity is a million dollars' worth of it.

The load issues two warnings. `WiodUnproducedInputs` says that 2,298 units use products that no
unit produces, the rest of the world's `M73` and Malta's `A02`, for 6,992.50 million US$ in all.
Those uses are not input entries, since a Leontief unit that needed a product nobody makes could
produce nothing; each unit's total is in `unit_extra["unproduced_input_use"]`. The table balances
`M73` through negative final demand, and the observed plan keeps final demand as recorded, so on
the two products supply minus use equals what the units drew from them. Every other commodity of
the observed plan balances to within 1.8e-14 of its supply. `WiodLaborGap` names the units with no hours figure,
China's 47 and the rest of the world's 55; they get no labour input.

**Labour is your choice.** The world input-output table has no labour data. With `labor=None`, the
default, no labour commodity is built and the zip is the only file needed. `labor="hours"` reads
hours worked by employees from the socio-economic accounts, and `labor="compensation"` reads
compensation of employees, converted to US dollars with `exchange_rates=`, the path of
`Exchange_Rates.xlsx`. Neither counts the self-employed, and which one stands for labour input, or
neither, is a theoretical choice the library does not make for you. A unit without a figure gets
no labour input, never a zero or an estimate, and `unit_extra["labor_observed"]` marks it. The rest
of the world has no figure under either measure, and China has no hours. Some units record output
and no intermediate purchases at all (29 in 2014, mostly industry `T`): without labour they need no
input, and with it labour is their only one.

## Write your own coordination method

A coordination method is any object with one method:

```python
def solve(self, economy: Economy, seed: int) -> Plan: ...
```

That is the whole interface. Implementing it is enough to get the data model, the loaders,
the timing and round accounting and the determinism self-test; your code does not have to be
merged into this library to get any of it.

If the change you want is to the price rule alone, `HahnelBook2021` takes one. A price rule is
called once a round with four arrays, one entry per commodity: the price the proposals were made
at, the surplus at that price, the relative imbalance, and the state the previous round
returned. It returns `(next_price, next_state)`, and `initial_state(n_commodities)` gives the
state for round one. The board carries the state from round to round, so one rule object can
serve many runs. `stateless` turns a function of the first three arrays into a rule.
Everything else, the councils and the aggregation, stays as the book describes it:

```python
import numpy as np
from demplan import run
from demplan.prefabs import HahnelBook2021
from demplan.prefabs.hahnel import stateless


def proportional_rule(price, surplus, imbalance):
    """Move every price by a fifth of its relative imbalance."""
    return price * (1 - 0.2 * np.sign(surplus) * imbalance)


result = run(HahnelBook2021(price_rule=stateless(proportional_rule)), economy, seed=0)
print(result.summary.rounds, result.summary.converged)
```

The four arguments are read-only copies the board owns: writing to one raises, and nothing the
rule does to them reaches the plan. The board also copies both return values, so a rule may
keep one output buffer and rewrite it every round.

`demplan.prefabs.hahnel.book_2021_rule` is the program's rule in the same shape, so you can
compare against it or wrap it.

To change more than the rule, write `solve` yourself. `CouncilModel` in
`demplan.prefabs.hahnel` is the councils' side of the procedure on its own. It takes the price
rule as an argument and has `initial_state`, `step`, `converged` and `plan_of` in exactly the
shape `iterate` takes, so a procedure that wants a different loop can drive it directly; using
it commits you to the theory its docstring states. `demplan.tools` holds the closed forms of the two technologies the library
recognises by label.

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

**Commodities.** One table. The library does not classify commodities: whether one is a
private good, a public good, a resource or labour is a statement of some theory, so a loader or
a prefab that needs such a label writes it into `commodity_extra` under a key it owns (the
dep1ex loader writes `commodity_extra["hahnel_kind"]`).

| column | type | meaning |
|---|---|---|
| `commodity_id` | int64 | stable identifier, equal to the row number |
| `endowment` | f64 | quantity available this period without producing it; 0 for produced goods |

**Producing units.** Variable-length input and output lists are stored flat with offsets
rather than padded into a rectangle. Unit `i` owns
`input_commodity[input_offsets[i]:input_offsets[i+1]]` and the matching slice of
`input_coefficient`; `economy.inputs_of(i)` returns that window. Outputs are laid out the same
way, so a unit can make several commodities (joint products); every unit has at least one
output and lists a commodity at most once.

| column | type | meaning |
|---|---|---|
| `unit_id` | int64 | stable identifier, equal to the row number |
| `technology_kind` | text | a label naming the unit's technology, such as `"leontief"` or `"cobb_douglas"` |
| `technology_scale` | f64 | scale coefficient |
| `input_offsets` | int64[n_units + 1] | bounds of each unit's window into the flat input arrays |
| `input_commodity` | int64[n_inputs] | which commodity each input is |
| `input_coefficient` | f64[n_inputs] | a number per input whose meaning the technology sets: an input coefficient under Leontief, an exponent under Cobb-Douglas |
| `output_offsets` | int64[n_units + 1] | bounds of each unit's window into the flat output arrays |
| `output_commodity` | int64[n_outputs] | which commodity each output is |
| `output_coefficient` | f64[n_outputs] | a number per output whose meaning the technology sets; 1.0 for a unit whose activity is measured in its output |

`technology_kind` is open: any non-empty label is accepted, and `LEONTIEF` and `COBB_DOUGLAS`
are exported as constants for the two forms the library's own tools recognise.

**Consumer units.** `consumer_id` (int64, equal to the row number). Groupings such as region or
household type go into `consumer_extra`.

**`extra` bags.** `commodity_extra`, `unit_extra` and `consumer_extra` hold named arrays whose
leading dimension is their table's row count: numeric arrays, or one-dimensional arrays of
non-empty text labels (a list of `str` works too). Nothing requires a particular key to be
present; these names are conventions that loaders write and prefabs read.

| table | key | shape | meaning |
|---|---|---|---|
| consumer | `entitlement` | f64[n_consumers] | consumption entitlement, an exogenous flow |
| consumer | `utility_exponent` | f64[n_consumers, k] | Cobb-Douglas utility exponents |
| consumer | `utility_exponent_commodity` | int64[k] | which commodity each of those columns is |
| commodity | `hahnel_kind` | text[n_commodities] | the dep1ex loader's class label: `private_good`, `public_good`, `intermediate`, `natural_resource` or `labor` |
| unit | `effort_c`, `effort_s`, `effort_k` | f64[n_units] | behavioural parameters of the dep1ex worker-council closed form |

**Building one by hand.** Seven commodities, three producing units and two consumer units,
with Leontief technology. Integer columns are int64; `Economy` checks that, and the check is
the reason a plan built for one economy cannot be quietly aggregated against another. The
labels in `commodity_extra` are this example's own; the library reads none of them.

```python
import numpy as np
from demplan import LEONTIEF, Economy

economy = Economy(
    period=0,
    commodity_id=np.arange(7, dtype=np.int64),
    endowment=np.array([0.0, 0.0, 0.0, 0.0, 0.0, 100.0, 200.0]),
    commodity_extra={"role": ["food", "clothing", "park", "steel", "cement", "land", "labour"]},
    unit_id=np.arange(3, dtype=np.int64),
    technology_kind=[LEONTIEF, LEONTIEF, LEONTIEF],
    technology_scale=np.ones(3),
    input_offsets=np.array([0, 3, 5, 8], dtype=np.int64),           # unit i owns [o[i], o[i+1])
    input_commodity=np.array([3, 5, 6, 4, 6, 3, 4, 6], dtype=np.int64),
    input_coefficient=np.array([0.4, 0.2, 0.5, 0.3, 0.6, 0.1, 0.2, 0.4]),
    output_offsets=np.array([0, 1, 2, 3], dtype=np.int64),          # one output per unit here
    output_commodity=np.array([0, 1, 2], dtype=np.int64),
    output_coefficient=np.ones(3),
    consumer_id=np.arange(2, dtype=np.int64),
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
| `output` | f64[n_outputs] | how much of each output entry each producing unit makes, aligned with `Economy`'s flat output arrays |
| `input_use` | f64[n_inputs] | what it uses, aligned with `Economy`'s flat input arrays |
| `consumption` | f64[n_consumers, k] | how much each consumer unit uses of each commodity it is attributed |
| `consumption_commodity` | int64[k] | which commodity each consumption column is |
| `shared_use` | f64[n_commodities] | quantity used in common and attributed to no single consumer unit (non-rival use); 0 where nothing is shared |

Input use is stored rather than derived. Where a technology allows substitution, the input mix
is a decision the mechanism made, and recomputing it afterwards would replace that decision
with the recomputing tool's own theory. Endowment use is different: it is a plain aggregation
of input use on the commodities you name, so `plan.endowment_use(economy, resources)` derives
it; which commodities count as resources is your statement, not the library's.

**Absent fields.** Not every mechanism has every physical quantity. A mechanism that
balances totals alone has no consumption per consumer unit, and one whose common use is
regional cannot state it as a single society-wide quantity, so `consumption`,
`consumption_commodity` and `shared_use` may be declared absent by passing `None`. `output` and
`input_use` are required: every mechanism that plans production has both. The fields carry no
default, so leaving one out of the call is still a missing argument -- absence is something
you say, never something that happens to you. `plan.absent_fields` reads the declaration back,
and an accessor over an absent field raises `PlanFieldAbsent` rather than answering zero: a
zero would enter one side of a balance as a quantity the other side never carried.

`StatedPlan` and `AllocatedPlan` say which reading `consumption` carries -- what the consumer
councils asked for, or what an allocation handed out. `require_comparable(a, b)` refuses to
subtract one from the other.

**Extension layer.** `valuation` is a named-array bag, because a mechanism that computes
labour times has no prices and one that iterates on prices has no labour times. Predefined
keys are `indicative_price`, `labor_value` and `shadow_price` (f64[n_commodities], with NaN
for commodities the mechanism leaves undefined), and `income` and `expenditure`
(f64[n_consumers]; expenditure is everything the unit spent this period, its part of anything
used in common included). Any other key
is yours, and its leading dimension has to be one of the three row counts. Every array is
float64, refused rather than converted: converting would hide that the mechanism computed the
quantity in another type.

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

## Recording a run so someone else can repeat it

`run_configuration(procedure, economy, seed, loader=None, plan=None)` returns a document you
can write with `to_json` and someone else can load with `from_json`. It is settings, not
provenance: what went in, in a form that goes back in.

```python
from demplan import run_configuration

configuration = run_configuration(procedure, economy, seed=7, plan=plan)
configuration.to_json("run.json")
```

It is a separate call rather than something `run` does for you, because hashing the economy
costs real time on a large one and a parameter sweep should not pay it a thousand times.

The economy goes in as a content hash, byte for byte, with a digest per column beside the
whole. Two runs that disagree on a number nobody can see are the failure this exists for, and
the per-column digests are what make the alarm diagnosable:
`compare_economy_digests(recorded, current)` names the columns that differ rather than saying
only that something does. It returns a report; deciding what a difference means is yours.

The library hashes the source of its own procedures and not yours -- for your code, git is a
better version control than any hash the library could compute. Parameters are recorded for
both: a parameter is data, not code, and the library can read your dataclass as well as its
own.

Three things the document does not promise, so that you do not read more into it than it says.
The `source_digest` covers the whole module file, so it moves when a docstring moves and not
only when behaviour does. Field names in `plan_fields_absent` come from your plan and are
never checked against `Plan`, because the document reads your plan by duck typing rather than
validating it. Parameters that JSON has no form for -- an `Enum`, a `datetime`, a `set` --
are recorded as undeclared rather than converted, since converting would pick a
representation on your behalf.

## What this library is answerable for

The infrastructure half: the data model, the loaders, deterministic seed distribution, the
determinism self-test, the difference reports, and, once built, the provenance record of a run.

The coordination method is yours. Whether your implementation is correct and whether your
conclusions follow are yours too. The library does not read your code, does not judge whether
two procedures are equivalent, and does not pick the quantity a comparison rests on; you
declare that, and once the run manifest exists the declaration goes there.

## Contributing

Bug reports, questions about a result, and requests for a data source or a procedure are all
welcome as issues. For code and documentation changes, read [CONTRIBUTING.md](CONTRIBUTING.md)
first; the [wiki](https://github.com/enshulv/demplan/wiki) has longer guides for researchers
and for developers.

**On AI assistance.** The project does not reject AI-assisted work; the maintainer uses it too.
What it asks for is that a person stays accountable for every change. A pull request that
changes behaviour, a data model field, or a documented rule has to include a decision record
that shows the human decisions: what options were considered, which one was chosen and why,
what was rejected, and what the contributor checked with their own eyes. The format and the
reasons for it are in [CONTRIBUTING.md](CONTRIBUTING.md#ai-assisted-contributions).
AI-generated code submitted without that context is not accepted. AI agents working in this
repository should start from [AGENTS.md](AGENTS.md); the wiki's AI Development Guide explains the
setup.

## How to cite

Every release is archived on Zenodo. Cite the version you used:

> Mark, E. (2026). *demplan: shared research infrastructure for democratic economic planning*
> (Version 0.1.1) [Computer software]. Zenodo. <https://doi.org/10.5281/zenodo.23010111>

The DOI [10.5281/zenodo.23010110](https://doi.org/10.5281/zenodo.23010110) stands for all versions and always resolves to
the latest; the Zenodo page lists the DOI of each version. Metadata is in
[CITATION.cff](CITATION.cff); GitHub shows a "Cite this repository" button for it.
Citations and mentions help other researchers in the field find the library.

If your work depends on the reproduction results above, please also cite the original
experiments [2, 3] and the pseudocode paper [4].

## References

1. Albert, M., and Hahnel, R. (1991). *The Political Economy of Participatory Economics.*
   Princeton University Press.
2. Hahnel, R., Szczepanczyk, M., and Weisdorf, M. (2020). *Computer Simulation Experiments of
   Participatory Annual Planning.* Systems Science Noon Seminar, 4 December 2020. Slides:
   <https://thenextrecession.wordpress.com/wp-content/uploads/2021/01/computersimulationexperimentsofparti_powerpoint.pdf>
3. Hahnel, R. (2021). *Democratic Economic Planning.* Routledge.
4. Szczepanczyk, M. (2023). Pseudocode and algorithms for computer simulations of
   democratically planned economies. *Journal of Information Economics* 1(3), 15, 43–54.
   <https://doi.org/10.58567/jie01030004>. Open access under CC BY 4.0. Page numbers in this
   README refer to the author's version, <http://www.szcz.org/img/jie-paper-2023.pdf>.
5. Szczepanczyk, M. Participatory planning experiment data (`dep1ex01` to `dep1ex40`).
   <https://www.szcz.org/depexperiments/>
6. Szczepanczyk, M. `pequod-plus`: participatory planning procedure prototype (Clojure,
   GPL-3.0). <https://github.com/msszczep/pequod-plus>
7. Samothrakis, S. (2020). Open loop in natura economic planning. arXiv:2005.01539. Code
   (GPL-3.0): <https://github.com/ssamot/socialist_planning>
8. Nardelli, P. H. J., Gória Silva, P. E., Siljak, H., and Narayanan, A. (2025). Cyber-physical
   decentralized planning for communizing. *Competition & Change* 29(1).
   <https://doi.org/10.1177/10245294231213141>. I-EPOS code (GPL-2.0-or-later):
   <https://github.com/epournaras/EPOS>
9. Parellada, P. V. `Economic-Planning`: a Python package for multi-period
   linear-programming planning (GPL-3.0). <https://github.com/pablovegan/Economic-Planning>
10. Vezhnevets, A. S., et al. (2023). Generative agent-based modeling with actions grounded in
    physical, social, or digital space using Concordia. arXiv:2312.03664.
11. Piao, J., et al. (2025). AgentSociety: Large-scale simulation of LLM-driven generative
    agents advances understanding of human behaviors and society. arXiv:2502.08691.
12. Cockshott, W. P., and Cottrell, A. (1993). *Towards a New Socialism.* Spokesman.
13. Kazil, J., Masad, D., and Crooks, A. (2020). Utilizing Python for agent-based modeling: the
    Mesa framework. In *Social, Cultural, and Behavioral Modeling (SBP-BRiMS 2020)*, Lecture
    Notes in Computer Science 12268, Springer.
14. Szczepanczyk, M. `pequod-cljs`: a computerized simulation of a participatory economy
    (Clojure and ClojureScript). <https://github.com/msszczep/pequod-cljs>. The runs behind the
    tables of [3] used `src/clj/pequod_cljs/csvgen.clj` at commit `71e44d3` (2020-06-23).
15. Timmer, M. P., Dietzenbacher, E., Los, B., Stehrer, R., and de Vries, G. J. (2015). An
    illustrated user guide to the World Input–Output Database: the case of global automotive
    production. *Review of International Economics* 23, 575–605. The WIOD 2016 release (CC BY
    4.0) is at <https://doi.org/10.34894/PJ2M1C>.

demplan reads the published papers and data; it contains no code from the implementations
above. Its reference solution calls the HiGHS solver through SciPy.

## License

MIT. See [LICENSE](LICENSE).
