# Current rules

This document covers only the rules that hold today. Rationale lives in `decisions/`; progress lives in `progress.md`.

Code development started 2026-09-05. The following are constraints the implementation must satisfy.

## Scope

This library covers democratic economic planning and participatory economic planning. The library is called `demplan`, under the MIT license.

The mechanism layer accepts only coordination procedures within this field. **It does not implement market mechanisms**: `Economy` carries no market-clearing-specific fields such as a market-clearing residual. The comparison benchmark across mechanisms is a centralized optimal reference solution, not a market baseline.
The reference solution takes the researcher's declared objective as a parameter: `reference_solution(economy, objective) -> Plan`. The objective goes into the run manifest. The library ships several objectives as options and sets no default.
The objective's contract: `weights(economy)` gives weights on final consumption, and `allocate(economy, aggregate)` gives the allocation of the aggregate to consumer units. An objective interpreted as a minimization must carry both `final_demand_lower_bound` and `minimize_kind`; carrying only one is an error. The final-demand lower bound cannot be negative. This well-formedness check on the declaration is not an invariant, so the rule that "non-negativity is an optional constraint" does not apply to it.

**The foundation layer is theory-neutral.** Anything that carries an economic-theory assumption — invariants, metrics, behavioral equations — is always an optional tool, never a mandatory prerequisite. Before adding anything to the fixed layer, ask "which school of thought would disagree with this." If you can answer that question, it cannot be fixed.

v1 has no money or debt stock fields, and no interaction topology between agents. Both are deferred past v1, but agents have had stable identifiers since Stage 0 so this can be hooked in later.

**`Economy` is a closed economy: there is no place for imports or exports.** This is an assumption, not a neutral omission — related implementations' open-economy models carry `use_import`, `prices_import`, `prices_export`, and an export residual. World prices are exogenous terms of trade, not an internally cleared price, so adding them would not violate "no market mechanisms." Until it is added, the reference solution's declared assumption list must list this one.

v1 covers producing units on the order of 10³ to 10⁴, with Leontief and Cobb-Douglas technology variants.

## Division of responsibility

The library guarantees the infrastructure half: the data model, invariant checks, metric definitions, deterministic seed distribution, and provenance records. The researcher supplies the coordination procedure; whether the implementation is correct and whether the conclusions hold is the researcher's own responsibility.

**The extension mechanism for coordination procedures is an interface, not a list the library maintains.** Any implementation that satisfies the interface gets all of the above capabilities, without merging into this library's code. The library makes no promise to understand the researcher's implementation, and no promise to judge whether two implementations are equivalent.

**Comparison is the researcher's job, not the library's.** The library does not prescribe which quantity a comparison uses as its benchmark; the researcher declares it when comparing, and the declaration goes into the run manifest. Comparability rests on four things: **the same initial economy plus the same evolution rule**, the same recording discipline, a declared comparison benchmark, and output raw enough that anyone can recompute any metric after the fact.

In multi-period rollout, only the initial economy is shared — the trajectories afterward diverge, and that divergence is itself one of the things being compared. But when the two runs use different evolution rules, the comparison is between "coordination mechanism plus evolution rule" combinations, not pure mechanisms, and the manifest must make that visible.

**Overreach means hardcoding, not providing.** For computational steps that carry theory — proposal behavior, constraints, metrics — the library provides tools, but does not weld them into the core or set them as the default path.

## Core abstractions

v1's public surface is two data types, two functions, and a toolbox:

| Name | Responsibility |
|---|---|
| `Economy` | Data model: the state of a given period. Commodities, producing units, consumer units, technology, endowments, time |
| `Plan` | One period's plan: physical layer plus extension layer |
| `solve(economy, seed) -> Plan` | The coordination procedure interface. An object implementing it is called a `Procedure` |
| `advance(economy, plan, seed) -> Economy` | The evolution rule; appears only in multi-period runs |
| Tools | `iterate`, proposal behavior, invariant residuals, metrics, reference solution, seed derivation, self-test tools |

`Participant` (produces a proposal given a signal) has no interface position in v1; it appears only at v2's council granularity. Metrics are a collection of functions, not an object.

**The abstraction has exactly one test**: the mechanisms below run on the same `Economy`, and their outputs can state differences in the same vocabulary — a quantity undefined on one side stays absent, and absent must be distinguishable from zero. **The library does not score or rank**, see [decisions/comparison-and-presentation.md](decisions/comparison-and-presentation.md).

| Use case | Granularity | Status |
|---|---|---|
| Parecon's iterative price adjustment | Sector | Working, `prefabs/hahnel` |
| Cockshott's direct labor-time calculation | Sector | Envisioned |
| Kantorovich-style linear programming | Sector | Working, `reference_solution`, but **requires Leontief** |
| OLIN-EP's nonlinear input-output `(I − F(x))x = d` | Unit (factories and citizens) | Doesn't fit: `technology_kind`'s enum has no entry for it |
| I-EPOS's discrete candidate-plan selection | Council | v2. A proposal isn't a continuous vector; the `Participant` interface needs to accommodate "choose from a finite candidate set" |

The last two rows have public code and published results, see [research/related-implementations.md](research/related-implementations.md). Two of the first three rows are already working, but **the two cannot be compared today**: dep1ex's 30,000 units are all Cobb-Douglas, the reference solution requires Leontief, so it must pass through `linearize`, and linearization silently swaps decreasing returns to scale for constant returns.

## Data model

`Economy` consists of three columnar tables, each with fixed columns plus an `extra` named-array bag. The fixed columns hold only what every school of thought agrees exists; behavioral parameters go into `extra`, whose keys the library conventionalizes and prefabs interpret. **`Economy` carries no prices.** Valuation quantities live only in `Plan`'s extension layer and in the coordination procedure's own `State`.

**Commodities**: a single table, each row tagged with a kind. dep1ex currently has five kinds — private consumption goods, public goods, intermediate goods, natural resources, and labor. **This set is currently closed**; `validate` rejects any other value. Opening it up has to happen together with making the kind attribute declarable, and **emissions are not blocked by the kind set** — emissions are joint products, blocked by "one output per unit"; money stock, per the deferred list, is an added field, not an added kind. Both are decided to happen, see [decisions/data-model.md](decisions/data-model.md) 2026-09-05.

| Column | Type | Meaning |
|---|---|---|
| `commodity_id` | int64 | Stable identifier, equal to the row index |
| `commodity_kind` | int8 | Kind: 0 private consumption good, 1 public good, 2 intermediate good, 3 natural resource, 4 labor. Extensible |
| `endowment` | f64 | Quantity available this period without production. Zero for produced goods |

**Producing units**: columnar arrays, plus a unit-to-sector grouping map. Variable-length inputs are stored as a flat array plus offsets, not padded into a rectangle. In v1, each unit has exactly one output commodity.

| Column | Type | Meaning |
|---|---|---|
| `unit_id` | int64 | Stable identifier, equal to the row index |
| `unit_group` | int64 | Unit-to-sector grouping map; values are arbitrary group labels the library does not range-check. In dep1ex it equals the output commodity |
| `output_commodity` | int64 | The output commodity |
| `technology_kind` | int8 | 0 Leontief, 1 Cobb-Douglas. Extensible |
| `technology_scale` | f64 | Scale coefficient. dep1ex's `a` |
| `input_offsets` | int64[n_units + 1] | Unit i's inputs are the flat array's `[offsets[i], offsets[i+1])` |
| `input_commodity` | int64[n_inputs] | Input commodities |
| `input_coefficient` | f64[n_inputs] | Under Leontief, the input coefficient; under Cobb-Douglas, the exponent |

**Consumer units**: `consumer_id` (int64, stable identifier), `consumer_group` (int64).

**`extra` conventional keys** (whether they're present is decided by the loader and the prefab; the library doesn't require them):

| Table | Key | Shape | Meaning |
|---|---|---|---|
| Consumer unit | `entitlement` | f64[n_consumers] | Consumption entitlement, an exogenous flow. dep1ex's `income` |
| Consumer unit | `utility_exponent` | f64[n_consumers, k] | Cobb-Douglas utility exponents. Column j's commodity is given by `utility_exponent_commodity` |
| Consumer unit | `utility_exponent_commodity` | int64[k] | The column-to-commodity map for the row above |
| Producing unit | `effort_c`, `effort_s`, `effort_k` | f64[n_units] | dep1ex's worker-council closed-form parameters `c`, `s`, `du`. `c` is also the effort exponent in the production function |

Each array in `extra` has a first dimension equal to that table's row count. **Column-map keys are the exception**: their shape is `[k]`, where k is the column count of another 2-D `extra` array. The only column-map key currently registered is `utility_exponent_commodity`. A utility-exponent column can point to a commodity of any kind, not just private consumption goods and public goods.

`period` (int64) records which period this is.

**`Economy` is the state of a given period, not a fixed problem statement.** In multi-period runs, the evolution rule updates it. Holding it constant would weld the theoretical assumption "fixed technology, fixed input ratios" into the data model.

**`Plan` has two layers:**

```
Physical layer (theory-neutral, every mechanism has it)
├── Production side: output f64[n_units], input_use f64[n_inputs] (aligned with Economy's flat input array)
└── Consumption side: consumption f64[n_consumers, k] plus consumption_commodity int64[k]
            (private goods: "who gets how much"; the column-to-commodity map follows the same
            pattern as Economy's utility_exponent),
            provision f64[n_commodities] (public goods: "how much is produced and shared in total";
            zero for other commodities)

Extension layer (mechanism-specific)
├── valuation: a named-array bag. Predefined keys indicative_price / labor_value / shadow_price
│   (f64[n_commodities], NaN for commodities the mechanism leaves undefined) and income (f64[n_consumers]).
│   Other keys are free
└── extra: a named-array bag for mechanism-specific physical quantities. The first dimension is one
    of n_units, n_consumers, or n_commodities.
    prefab hahnel writes effort (f64[n_units], the effort factor in the production function)
    and consumer_demand (f64[n_commodities], the contribution of consumer councils' stated plans to
    demand for each commodity: for private goods, the sum across councils; for public goods, the
    shared quantity counted once for society as a whole; for other commodities, the undivided total;
    zero for a commodity nobody stated demand for)
```

Each of these two keys has an exported constant (`EFFORT`, `CONSUMER_DEMAND`); the test is "vocabulary needed to read any plan." The `extra` keys on `Economy`'s three tables are mechanism input parameters, not vocabulary for reading a plan, so they stay bare strings.

dep1ex's production function is `Q = a · e^c · Π x_j^{b_j}`, where `e` is the effort a unit chooses each round and `c` is `effort_c`. `technology_kind = 1` describes only the input side; reconstructing the full relationship requires `Plan.extra["effort"]`.

Input use must be stored in the physical layer; it cannot be dropped as a derived quantity — when the technology allows substitution, the input mix is a decision the mechanism made, not a computed result. Endowment use (how much of each natural resource or labor was used) is an aggregation of input use by commodity, derived by an accessor, and not stored separately.

**Three physical-layer fields can be absent**: passing `None` for `consumption`, `consumption_commodity`, or `provision` declares "this mechanism has no such quantity." `output` and `input_use` are required — every mechanism that plans production has both, and **passing `None` for them is an error at construction time**, not deferred to `validate`. Fields have no default value, so an omission is still a missing-argument error; absence can only be something the researcher wrote explicitly. `consumption` and `consumption_commodity` describe the same quantity and go in and out together. `Plan.absent_fields` reads back the declaration. An accessor that needs a field the plan lacks raises `PlanFieldAbsent` — **it does not return zero**, because a zero would enter a balance equation as a quantity the other side never held, and the two sides would no longer close.

Divergence monitoring covers only the physical fields a plan actually carries: a mechanism that reports only `output` and `input_use` gets a `diverged=False` that says only those two stayed finite. In determinism comparisons, both sides absent counts as consistent; one side absent and the other present is reported as `<field> (absent from one run)`, not as a numeric difference.

**`valuation`'s length has two tiers by key**: conventional keys follow their registered row count (`indicative_price`, `labor_value`, and `shadow_price` are one per commodity; `income` is one per consumer unit); other keys' first dimension is one of `n_units`, `n_consumers`, or `n_commodities`. The dtype must be `float64`, and it's **rejected rather than converted** — converting would erase the signal that "the mechanism computed this quantity in a different type."

**`Plan` has two subclasses**: `StatedPlan`'s `consumption` is the stated plan, `AllocatedPlan`'s is the allocated plan. A subclass only adds an identity — no added fields, no narrowed contract. `require_comparable(a, b)` refuses to subtract when the two sides are different subclasses. The prefab `hahnel` produces `StatedPlan`; the reference solution produces `AllocatedPlan`.

## Multiple periods

The researcher chooses between static and rolling:

```
run_periods(economy, procedure, periods, seed, advance=None, next_procedure=None, check_period=True)
```

Not passing an evolution rule means static (the same economy is solved `periods` times); passing one means rolling (`Economy` is updated each period). Anyone not doing multi-period work never sees this concept.

**The evolution rule `advance(economy, plan, seed) -> Economy` belongs to the researcher.** It holds capital accumulation, technological progress, resource depletion, population change — each one a theoretical claim. The library provides a few common implementations as tools. It is called only between two periods, `periods − 1` times in total. The library assigns the seed it receives, so a random evolution rule is reproducible; the rule must not keep random state between two calls.

**The next period's coordination procedure is built by the function slot `next_procedure(previous_plan) -> Procedure`.** Whatever the previous period passes to the next one (for example the warm-start prices) the mechanism puts into the plan and reads back itself. Without it, every period reuses the same coordination procedure. The coordination procedure interface `solve(economy, seed)` does not change.

**Seed layout**: `split_seed(seed, 2 · periods)` gives `w₀ …`. Period i (counting from 0) uses `w₂ᵢ` for the coordination procedure, and the evolution rule that produces the economy of period i+1 uses `w₂ᵢ₊₁`. The last position is reserved. This layout is part of the determinism contract.

**Output** keeps every period's economy, the `RunResult`, the coordination procedure's seed and the evolution rule's seed.

**Soft check on the period number**: when the `period` returned by the evolution rule is not the previous one plus one, a `PeriodWarning` is issued. It does not raise and does not correct the value; `check_period=False` turns it off.

It's structurally the same as `iterate`: the value isn't running the loop for the researcher, but letting the library see that this is a trajectory — which is what makes cross-period provenance, multi-period output structure, and cross-period residuals possible.

## Replaceable and fixed

`Economy` is extensible, not replaceable. Once it becomes pluggable, results across studies stop being comparable.

The following two are fixed, not exposed as plugins:

- `Economy`'s data model
- Determinism and seeding

Everything else is optional or pluggable: `Procedure`, `Participant` behavior cores, economy generators and data loaders, invariant and constraint families, all metrics, output backends, visualization.

## The coordination procedure interface

The interface has exactly one layer:

```
solve(economy, seed) -> Plan
```

Iterative price adjustment, direct labor-time calculation, and the linear-programming reference solution all implement it.

The library also provides an **opt-in** loop tool, `iterate(init, step, converged, max_rounds)`. Using it gives the library round counts, an upper-bound guard, and divergence detection; not using it leaves only the final result. The optional `plan_of` parameter says "how to view this round's state as a plan"; the library uses it to produce a round-by-round trajectory with a definition shared across mechanisms, for diagnostics. With `keep_trajectory=False`, `plan_of` is used only to detect divergence, and the trajectory isn't kept. Round-count definition: `rounds` is the number of times `step` is called up to convergence; the convergence test runs after each `step` call, not after `init`. A state containing a non-finite value does not count as converged.

`State` is unconstrained — an arbitrary object of the researcher's choosing. The library never looks inside it.

## Invariants: an optional toolbox

The four invariants are **optional constraints**, not hard gates. The researcher enables them as needed; adding them one at a time makes the experiment progressively stricter.

- **Material balance**: no commodity's use exceeds its output plus its endowment
- **Budget identity**: each participant's spending matches their income
- **Non-negativity**: quantities and prices are not negative
- **Price homogeneity of degree zero**: scaling all prices by the same factor leaves the physical solution unchanged

Each of the four carries a theoretical assumption of its own (in order: closed within the period with no inventory, a hard budget constraint, every output is a good rather than a bad, and monetary neutrality), so none can be set as a prerequisite. The reasoning for each is in [decisions/invariants-and-metrics.md](decisions/invariants-and-metrics.md).

**Theoretical commitments belong to the prefab.** Which invariants to enable when reproducing a given paper is declared by that paper's prefab; the library sets no global default.

**Residuals are always computed, and their names stay neutral.** Material balance, budget, and non-negativity can all be computed from a single run's output, and the library computes their residuals and writes them into the output whether or not they were set as constraints — except where the mechanism leaves them undefined (direct labor-time calculation has no prices, so the budget residual is N/A for it, not 0, and the output must be able to show that difference). The budget residual needs prices and income: prices come from `valuation`'s price-type keys, income comes from `valuation["income"]`, falling back to consumer units' `extra["entitlement"]` when it's absent. The naming is always "budget residual," never "budget-identity violation": the same number is a defect to one researcher and the object of study itself to someone running a credit-creation experiment. The library gives the number, not the verdict.

**Price homogeneity of degree zero is a property test, not a residual.** It's a property of the coordination procedure, and a single run's output doesn't contain it. The `check_homogeneity` tool rescales the initial valuation, reruns, and compares the physical layer; it's usable only for coordination procedures that expose their initial valuation as a parameter.

**Cross-period residuals** are likewise always computed and neutrally named: the cumulative resource use (against the initial endowment) and the change in the number of consumer units, which can be computed from fixed fields, are computed by default in multi-period runs and written to the output, and can be turned off. Non-negative capital stock and a stock equal to the prior period's stock plus net flow have no corresponding fields in the data model; they are marked N/A with the reason. Which of them constrain a given model is declared by its evolution rule or prefab. The output includes a coverage table.

Their character differs from the single-period batch, and the document calls this out separately: **a single-period invariant violation is visible to the researcher on the spot** (this period's plan is infeasible), **but a cross-period violation is not** — when the evolution rule computes something wrong, every subsequent period's coordination procedure computes a fully self-consistent answer to a wrong problem, every check passes, the charts look fine, and the error grows with the number of periods, silently the whole way.

The toolbox will keep growing. SFC accounting identities (stocks as accumulated flows, transaction-flow matrix rows and columns summing to zero) are the next planned addition; their behavioral-equation part does not enter the foundation layer.

## Determinism

The library's half guarantees bit-for-bit reproducibility: data loading, `Evaluator`, scan scheduling, and seed distribution all produce bit-for-bit identical results for the same scenario file and the same seed. Parallel reductions use deterministic chunking and don't depend on thread count or scheduling order.

`seed` is an integer from 0 to 2⁶⁴−1. `split_seed(seed, n)` derives n child seeds using SplitMix64; `rng(seed)` returns numpy's `default_rng(seed)`.

A researcher-supplied coordination procedure is arbitrary Python, and the library cannot guarantee its determinism. The library hands it the seed (`solve(economy, seed)`) and provides `check_determinism(procedure, economy, seed, n)` for self-testing — it runs several times, compares the output, and reports where they differ if they don't match. This is a tool, not a gate. **It compares three categories: physical columns, `valuation`, and `extra`**; entries from the latter two carry a `valuation.<key>` or `extra.<key>` prefix. The order is physical columns, then `valuation`, then `extra`, with keys within each bag sorted by name. A physical column absent on one side and present on the other is reported as `<column> (absent from one run)`, not as a numeric difference. There's no runtime enforcement: Python has no real sandbox, and a randomized coordination procedure is legitimate research. What's guaranteed is "reproducible given a seed," not "no randomness allowed."

## Run configuration document

`run_configuration(procedure, economy, seed, loader=None, plan=None)` produces a **loadable** configuration document: it comes out at the end of a run, and feeding it back in gives the same configuration. This is **a separate document** from the run manifest — the configuration document holds configuration, the manifest holds provenance, and the configuration document's hash goes into the manifest. Keeping them separate lets a load tell clearly which half is input; otherwise, feeding it back in would treat the previous run's result as input.

**It is not welded into `run`.** `run`'s signature and `RunResult` stay unchanged; computing an economy's content hash costs something (0.064 seconds for dep1ex01's 53 MB), and a parameter sweep of thousands of runs shouldn't pay that cost every time. The researcher calls it explicitly.

The format is JSON (UTF-8, sorted keys, indent 2, `allow_nan=False`). There are eight top-level keys: `configuration_version`, `library_version`, `core_version`, `seed`, `economy`, `procedure`, `loader`, `plan_fields_absent`.

**The economy is content-hashed** byte-for-byte with no precision loss, under the algorithm identifier `sha256-columns-v2`: each column is converted to C order and normalized to little-endian, then `column-name\ndtype\nshape\n` is prepended to the bytes fed into sha256; the three `extra` bags' keys, with their prefix, count as columns too; the overall digest is the sha256 of the per-column digests concatenated after sorting by column name. **A scalar column's shape line reads `1`** (a 0-D array is promoted to 1-D), and integer scalars are normalized to int64 first. **Only numeric dtypes can be hashed**: object, structured, and text dtypes are all rejected, with the offending column named — their bytes are either memory addresses or a width the second language can't reproduce. **Any change to any step requires bumping the algorithm identifier.** **Per-column digests are stored alongside the overall digest**; `compare_economy_digests` compares two of them and returns an `EconomyDigestReport` naming which columns differ — this is what makes cross-platform floating-point last-bit differences diagnosable. Comparison is refused when the two digests' `algorithm` differ. **The library doesn't verify this automatically**; comparison is a tool the researcher calls explicitly.

**Implementations shipped with the library are content-hashed; the researcher's own are not**: for library-shipped ones, the module's source file gets a sha256; for the researcher's, only their declared provenance is recorded, and it's `null` if none is given. **Both sides record parameters** — a parameter is data, not code, and the library can introspect the researcher's data classes the same way it introspects its own. numpy scalars are recorded by value.

Versioning rules: a missing key in a document falls back to its default (an old document must still work with a new library); an unknown key is an error that distinguishes its two causes (the library is older than the document, or the key has been retired — the latter is checked against a registry of retired keys); a `configuration_version` newer than the library is an outright error. **A newly added key's default must preserve the old behavior** — if that's not possible, the key can't be added silently.

**Three things this document does not promise, which the researcher should know:**

- `plan_fields_absent` records the field names the researcher declared, and **the library does not check whether they're actual fields on `Plan`**. This is a direct consequence of duck typing without importing `Plan`: misspell a field name by one character and it goes into the document unchanged — nothing turns red.
- `source_digest` hashes the **entire module source file**, so it's **just as sensitive to comment-level changes**. When two documents' `source_digest` differ, that could mean the behavior changed, or it could mean someone edited a docstring.
- Parameters of type `Enum`, `datetime`, `complex`, or `set` **fall back to an "undeclared" form; their values do not enter the document**. JSON-native scalars and containers (including numpy scalars) are recorded by value; `np.ndarray` is not recorded, because its size is unbounded.

## Execution and storage

The entire economy stays resident in memory as columnar f64 arrays. A single iteration round never touches disk: reads happen only at the start of a run, writes only at the end.

v1's Rust layer holds only four things: storage and schema validation for `Economy` and `Plan`, the data loader, residual computation, and Parquet output. Proposal behavior, `iterate`, prefabs, and the reference solution live in Python. On the Python side, `Economy` and `Plan` are immutable data classes with numpy-array fields. Errors returned from Rust are converted at the binding layer into Python exceptions that inherit from `ValueError`.

## Output contract

The Rust side produces only long-format (tidy) Arrow/Parquet, with a versioned schema. Plotting happens in the Python layer.

Output has three tiers:

| Tier | Default | Purpose |
|---|---|---|
| Full configuration, one per period (output, input use, consumption, endowment use, valuation) | Always produced | Comparability |
| Process summary (round count, whether it converged, wall-clock time) | Always produced | The mechanism-efficiency comparison axis |
| Round-by-round trajectory | Only when `plan_of` is given | Reproduction and diagnostics |

**Acceptance test: can any metric be reconstructed from the output.** Storing only a summary doesn't pass.

Every run produces a run manifest recording the seed, the scenario file hash, the enabled constraint set, the declared comparison benchmark, and the provenance of the coordination procedure **and the evolution rule** — the two are treated equally, because a difference in the evolution rule can send the trajectory just as far off course, and no check will catch it.

When provenance is undeclared, **the output carries an objective statement of fact** ("this run's coordination procedure and evolution rule declared no provenance") — it doesn't block anyone or pass judgment; the reader decides for themselves whether it's reproducible. The highest tier of transparency is being folded into a prefab, at which point a reproducer gets it with `pip install` and never has to go find the author's repository. **Library-shipped** coordination procedures and prefabs are content-hashed, with the name resolving to a specific hash, so that the library's own implementation upgrades never silently change old scenarios' behavior; **researcher-supplied** ones record only their declared provenance (name, version, git commit, DOI — all optional); the library doesn't introspect their code, and an undeclared one is left blank and marked as such.

## Assembly-time validation

Every plugin declares what fields and capabilities it needs and what it provides. The whole assembly graph is validated before a run starts. Crossing the language boundary between Rust and Python loses the type system's protection, so this schema validation layer is required.
