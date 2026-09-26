# Comparison with similar implementations

Three public implementations that compute economic plans, surveyed 2026-09-05. They are not
upstream for this library — this library does not take code from them, and the licenses
would not permit it (see the end of this document). The survey serves two purposes:
confirming that this library's niche is not already occupied, and using them as real-world
test cases for the criterion that "the same `Economy` must hold several mechanisms."

Cloned at `upstream/socialist_planning/`, `upstream/EPOS/`, and
`upstream/Economic-Planning/`; like `pequod-plus`, each carries its own `.git` and is not
tracked by this repository.

## The three subjects

| | OLIN-EP | I-EPOS | Economic-Planning |
|---|---|---|---|
| Repository | `ssamot/socialist_planning` | `epournaras/EPOS` | `pablovegan/Economic-Planning` |
| Paper | Samothrakis (2020), arXiv:2005.01539 | Nardelli et al. (2025) | None; cites Hagberg and Zacharia |
| Form | One-off experiment script | Java framework | Python package, with documentation and CI |
| Language | Python | Java 8 + Maven | Python + cvxpy |
| License | GPL-3.0 | GPL-2.0-or-later | GPL-3.0 |
| Last commit | 2021-01-10 | 2026-05-22 | 2025-07-07 |
| Granularity | Unit (factories and citizens) | Council | Sector |
| Problem solved | Root-finding | Combinatorial selection | Linear programming |

**None of them is shared infrastructure.** OLIN-EP's README states that it only demonstrates
feasibility and does not benchmark against anything; I-EPOS's domain is general
combinatorial optimization for self-managed sharing economies, with economic planning as one
application; Economic-Planning is a single-mechanism solver package. The niche this library
aims for, comparable to Concordia and AgentSociety, remains open.

Each of the three teams wrote its own data model; none of their economies runs on another's
solver. This is the duplication that this library's point 7 sets out to eliminate.

### OLIN-EP: nonlinear input-output

Formulates the allocation as `(I − F(x))x = d`. `F(x)` is **a function of the output
level**, i.e., input coefficients vary with scale; the solution method is fixed-point
iteration plus nonlinear least squares. The paper's scale timings measure the linear problem
`(I − A)x = d`: 50,000 intermediate goods, 5,000 final goods, and 200 consumption profiles,
solved in under 20 seconds on an i7-8700K.

The quality of a plan is judged by its worst-performing consumption profile (in the original
text: "the plan is as good as its worst performance"). This is a maximin objective, which
fits into this library's `reference_solution(economy, objective)` at the `objective` slot.

### I-EPOS: decentralized selection among discrete plans

Each agent holds **a finite set of candidate plans** and selects one; the global cost is
evaluated on the aggregate signal; agents coordinate over a tree topology. The plan file
format is `cost:values`, one candidate per line.

The only dataset in the repository is `gaussian`, i.e., randomly generated vectors — **it
carries no economic data of any kind**. Nardelli et al. (2025) propose a variation
of I-EPOS as the technical basis of decentralized planning for communizing, and describe their
approach as closer to Ostrom's commons than to central planning such as Cockshott and Cottrell
(1993); the paper does not mention parecon. For this library it is one more mechanism alongside
parecon and labour-time planning; that grouping is this library's, not the paper's.

### Economic-Planning: constrained linear programming

A multi-period linear program written in `cvxpy`, with objective `minimize Σ c_t · x_t`;
`cost_hours` sums labor hours and import prices. Constraints include material balance,
import-export balance, a cap on cross-period labor reallocation
(`labor_realloc_constraint`), and an ecological cap (`pollutants_constraint`). Multiple
periods use a rolling horizon. The data comes from Spain's INE and Swedish supply-use
tables.

Its `Economy` is a pydantic data class; every field is **a list of one matrix per period**,
and `periods` equals `len(supply)`.

## Consequences for this library

### 1. Opening up the enum now has its first external empirical need

`Economy.technology_kind` currently only recognizes 0 (Leontief) and 1 (Cobb-Douglas).
OLIN-EP's `F(x)` is neither. A published mechanism, with code, does not fit into this
library's fixed layer.

The decision that "kind attributes should be declarable and the enum should be opened up"
was previously supported only by reasoning from the design adversarial review; it now has an
instance. See [decisions/data-model.md](../decisions/data-model.md), 2026-09-05.

### 2. Joint products now have a second piece of evidence

Economic-Planning carries a `pollutants_constraint`. Emissions are not blocked by the set of
commodity kinds; they are blocked by "one output per unit" — a point that, until now, rested
only on this project's own reasoning. Now there is an implementation, running on real
supply-use tables, that treats an ecological cap as a routine constraint.

### 3. A closed economy is a fifth unlisted assumption

Economic-Planning's `Economy` has `use_import`, `prices_import`, `prices_export`; its
`PlannedEconomy` has `export_deficit`. This library's `Economy` has no place for imports or
exports at all.

World prices are exogenous terms of trade, not an internal clearing price, so adding them
would not violate "no market mechanisms are implemented." The real issue is: the design
adversarial review's finding V1 pointed out that the reference solution claims "Nothing else
is imposed" while actually welding in four assumptions. **A closed economy is a fifth,
beyond those four**, and none of the four mentions it.

### 4. The criterion's test cases grow from three to five

`spec.md`'s original criterion was that parecon's iterative price adjustment, Cockshott's
direct labor-time calculation, and Kantorovich-style linear programming all run on the same
`Economy`. All three were hypothetical, imagined by this project itself.

OLIN-EP and Economic-Planning have code and real data, making them stronger test cases than
the hypothetical ones. I-EPOS is a test case for v2's council granularity: its agents
**select one from a finite candidate set**, so v2's `Participant` interface cannot assume
that proposals are continuous vectors.

### 5. Overlap with the future directions listed in upstream's 2023 paper

Szczepanczyk (2023) lists seven future directions at its end; "other production functions"
matches OLIN-EP's `F(x)`, and "environmental impact" matches `pollutants_constraint`. Three
independent parties have converged on the same set of gaps.

## Measured: the first cross-mechanism comparison on dep1ex01

The question is not "which one runs faster," but "for the same basket of final consumption,
how much labor does each path spend." Script: `.cache/tmp/xmech_probe2.py`, not checked into
the repository.

Economy: 500 commodities (100 in each of five kinds), 30,000 producing units, 30,000
consumer units, 164,742 input entries. **All 30,000 units are Cobb-Douglas**; not one is
Leontief.

| | Wall clock | Result |
|---|---|---|
| Loading | 0.78 s | — |
| A: iterative price adjustment (`hahnel_2020_slides`, 5% threshold) | 1.18 s | Converges in 14 rounds, spending 96,415.5 labor |
| Linearization | 0.01 s | — |
| B: reference solution (`minimize_labor`, with the lower bound set to the consumption basket delivered by A) | 4.02 s | Optimal labor 53,347.6 |

**A / B = 1.81.**

### Why this number cannot be cited as-is

Three things undermine it, and **the library currently states none of them**:

1. **The reference solution cannot run on the original economy.** `reference_solution`
   requires Leontief technology, while dep1ex is 100% Cobb-Douglas. Making the comparison
   requires `linearize` first; there is no alternative path.
2. **Linearization replaces decreasing returns to scale with constant returns, silently.**
   Measured on dep1ex01, each unit's total elasticity (the sum of input exponents plus
   `effort_c`) falls between 0.8136 and 0.9400, with a median of 0.8750 — **zero of the
   30,000 units reach 1**. After linearization, the LP faces a technology with constant
   returns to scale, so it overstates the gains from scaling up. **1.81 is an upper bound on
   the true gap, not an estimate.** This is the concrete consequence of finding J1 in the
   design adversarial review: it is not an abstract purity issue, it blocks the first real
   cross-mechanism comparison.
3. **Linearization is anchored to A's own plan.** B is therefore "how much more can be
   saved on the technology A chose," not "the centralized optimum." A different anchor point
   gives a different number.

**All three of these need to be stated in the reference solution's result.** Right now,
`ReferenceResult` has only three fields — `plan`, `objective_value`, `status` — and states
none of the above. This corresponds to the still-open item from the design adversarial
review: add a non-optional `assumptions` field to `ReferenceResult`, **read back from how the
solve was actually constructed** rather than hardcoded.

### The computational-efficiency side carries no information

At the dep1ex scale, both paths run in sub-second to low-single-digit seconds. The
difference is within one order of magnitude, and the two sides are not even solving the
same class of problem (root-finding / combinatorial selection / linear programming).
OLIN-EP's linear problem `(I − A)x = d` at 50,000 × 5,000, solved in 20 seconds, is a worthwhile scale target to cite, and it also
supports point 11, "the entire economy resident in memory."

**Computational efficiency only becomes an issue above 10⁵ commodities; economic
efficiency, at any scale, is the question this library actually exists to answer.**

## License boundary

All three repositories are GPL-licensed; this library is MIT-licensed. See
[decisions/license.md](../decisions/license.md).

- **No code from any of the three may be copied into this repository**, including
  rewritten fragments.
- **Reimplementing from the papers is permitted**: mathematical formulations and
  algorithmic ideas are not covered by copyright.
- **Data-format interoperability is permitted**: reading I-EPOS's `cost:values` or reading
  supply-use tables involves no code copying.
- Clones are kept under `upstream/` for reading and for running comparisons, the same
  treatment as `pequod-plus`.

I-EPOS's source file headers state "either version 2 of the License, or (at your option)
any later version," i.e., GPL-2.0-or-later, which is compatible with GPL-3.0. This does not
change any of the above.
