# Current rules

This document covers only the rules that hold today. Rationale lives in `decisions/`; progress lives in `progress.md`.

Code development started 2026-09-05. The following are constraints the implementation must satisfy.

## Scope

This library covers democratic economic planning and participatory economic planning. The library is called `demplan`, under the MIT license.

The mechanism layer accepts only coordination procedures within this field. **It does not implement market mechanisms**: `Economy` carries no market-clearing-specific fields such as a market-clearing residual. The comparison benchmark across mechanisms is a centralized optimal reference solution, not a market baseline.
The reference solution takes the researcher's declared objective as a parameter: `reference_solution(economy, objective) -> ReferenceResult` (the plan, the objective value and the solver status; `ReferenceProcedure(objective)` is the same thing as a `solve`). The objective goes into the run manifest. The library ships several objectives as options and sets no default.
The objective's contract: `weights(economy)` gives weights on final consumption, and `allocate(economy, aggregate)` hands the aggregate final consumption to the consumption side, returning `(consumption, consumption_commodity, shared_use)`. An objective interpreted as a minimization must carry both `final_demand_lower_bound` and `counted_commodities`; carrying only one is an error. The final-demand lower bound cannot be negative. This well-formedness check on the declaration is not an invariant, so the rule that "non-negativity is an optional constraint" does not apply to it.

The commodity groupings an objective needs are declared by the caller as arguments; the economy carries none of them:

- `MinimizeLabor(targets, counted, shared=None)`: `targets` is the floor on final consumption. `counted` is required: the commodities whose input use the minimization totals, at least one (which commodities are labour is the researcher's statement). It is stored as the attribute `counted_commodities`.
- `MaximizeWeightedConsumption(weights, split="equal", shared=None)`: `weights` is a weight per commodity, either a full vector or a mapping from commodity to weight.
- `shared` lists the commodities the consumer units use in common; `None` means none. `allocate` puts each commodity in `shared` into `shared_use` at its whole aggregate, and splits every other commodity with a non-zero weight (or floor) evenly across consumer units into `consumption`. The consumption columns are those commodities, in ascending index order.
- Which commodities carry weight is the researcher's statement; the library does not check it.

The reference solution requires every unit's `technology_kind` to be `LEONTIEF` and every unit to have exactly one output entry, and reads `output_coefficient` as output per unit of activity (1 after linearization and on dep1ex). A unit with joint products is refused. The reference solution hands over the solver's quantities as they are, without clipping, so negative values of the order of 1e-14 can appear within the solver's tolerance. Before feeding them back into a declaration that refuses negative entries, such as the floor of `MinimizeLabor`, the caller clips them at 0.

**The foundation layer is theory-neutral.** Anything that carries an economic-theory assumption — invariants, metrics, behavioral equations — is always an optional tool, never a mandatory prerequisite. Before adding anything to the fixed layer, ask "which school of thought would disagree with this." If you can answer that question, it cannot be fixed.

v1 has no money or debt stock fields, and no interaction topology between agents. Both are deferred past v1, but agents have had stable identifiers since Stage 0 so this can be hooked in later.

**`Economy` is a closed economy: there is no place for imports or exports.** This is an assumption, not a neutral omission — related implementations' open-economy models carry `use_import`, `prices_import`, `prices_export`, and an export residual. World prices are exogenous terms of trade, not an internally cleared price, so adding them would not violate "no market mechanisms." Until it is added, the reference solution's declared assumption list must list this one.

v1 covers producing units on the order of 10³ to 10⁴. The library ships implementations of two technologies, Leontief and Cobb-Douglas; researchers implement any other against the interface, see "Technology."

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
| Tools | `iterate`, proposal behavior, differences, the technology check, metrics, reference solution, seed derivation, self-test tools |

`Participant` (produces a proposal given a signal) has no interface position in v1; it appears only at v2's council granularity. Metrics are a collection of functions, not an object.

**The abstraction has exactly one test**: the mechanisms below run on the same `Economy`, and their outputs can state differences in the same vocabulary — a quantity undefined on one side stays absent, and absent must be distinguishable from zero. **The library does not score or rank**, see [decisions/comparison-and-presentation.md](decisions/comparison-and-presentation.md).

| Use case | Granularity | Status |
|---|---|---|
| Parecon's iterative price adjustment | Sector | Working, `prefabs/hahnel` |
| Cockshott's direct labor-time calculation | Sector | Envisioned |
| Kantorovich-style linear programming | Sector | Working, `reference_solution`, but **requires Leontief** |
| OLIN-EP's nonlinear input-output `(I − F(x))x = d` | Unit (factories and citizens) | The data model can hold it (`technology_kind` is a text label); the library has no implementation of this technology, and the reference solution cannot read it |
| I-EPOS's discrete candidate-plan selection | Council | v2. A proposal isn't a continuous vector; the `Participant` interface needs to accommodate "choose from a finite candidate set" |

The last two rows have public code and published results, see [research/related-implementations.md](research/related-implementations.md). Two of the first three rows are already working, but **the two cannot be compared today**: dep1ex's 30,000 units are all Cobb-Douglas with an effort factor (label `hahnel_cobb_douglas_effort`), the reference solution requires Leontief, so it must pass through `linearize`, and linearization silently swaps decreasing returns to scale for constant returns.

## Data model

`Economy` consists of three columnar tables, each with fixed columns plus an `extra` named-array bag. The fixed columns hold only what every school of thought agrees exists. **The library does not classify commodities, producing units or consumer units, and keeps no vocabulary of attributes.** Labels and behavioral parameters that a loader or a prefab needs go into `extra`, under keys whose names and meanings belong to the loader or prefab that writes them. The library's tools read no `extra` key of `Economy`; validation checks shapes only. **`Economy` carries no prices.** Valuation quantities live only in `Plan`'s extension layer and in the coordination procedure's own `State`.

When a library tool needs to know which commodities are resources, labour, used in common or bads, the caller declares it as an argument at the call site. These **declaration arguments** (`resources=`, `bads=`, `commodities=`, `counted=`, `shared=`) are all one-dimensional int64 arrays of commodity indices, each index at most once. An index out of range or listed twice raises `ValueError` naming the argument and the first offending index.

**Commodities**: a single table.

| Column | Type | Meaning |
|---|---|---|
| `commodity_id` | int64 | Stable identifier, equal to the row index |
| `endowment` | f64 | Quantity available this period without production. Zero for produced goods |

**Producing units**: columnar arrays. Variable-length inputs and outputs are both stored as a flat array plus offsets, not padded into a rectangle. Every unit has at least one output entry, and a unit lists a commodity at most once among its output entries; a unit with two or more output entries is a unit with joint products. **The data model records no ratio between a unit's outputs and assumes none.**

| Column | Type | Meaning |
|---|---|---|
| `unit_id` | int64 | Stable identifier, equal to the row index |
| `technology_kind` | text | Technology label, any non-empty text. The two labels the library recognises are exported as constants: `LEONTIEF = "leontief"`, `COBB_DOUGLAS = "cobb_douglas"` |
| `technology_scale` | f64 | Scale coefficient. dep1ex's `a` |
| `input_offsets` | int64[n_units + 1] | Unit i's inputs are the flat input arrays' `[input_offsets[i], input_offsets[i+1])` |
| `input_commodity` | int64[n_inputs] | Input commodities |
| `input_coefficient` | f64[n_inputs] | A number per input whose meaning the unit's technology sets: under Leontief the input coefficient, under Cobb-Douglas the exponent |
| `output_offsets` | int64[n_units + 1] | Unit i's output entries are the flat output arrays' `[output_offsets[i], output_offsets[i+1])` |
| `output_commodity` | int64[n_outputs] | The commodity of each output entry |
| `output_coefficient` | f64[n_outputs] | A finite positive number per output entry, whose meaning the unit's technology sets. The library's own technologies read it as output per unit of activity |

Both sets of offsets start at 0, never decrease and end at the entry count; commodity indices are in range; coefficients are finite; every `output_coefficient` is also above 0, and 0 or a negative value is refused, naming the unit and the output entry. `n_inputs` and `n_outputs` are the lengths of the two flat layouts.

**Consumer units**: `consumer_id` (int64, stable identifier, equal to the row index).

**Text columns**: `technology_kind` and any text array in an `extra` bag are one-dimensional numpy arrays of dtype kind `U`, one label per row; an empty label is refused. A list of `str` is accepted in their place and stored as such an array; the Rust loaders hand text columns over in that form. The finiteness check applies to numeric arrays only.

**`extra` bags**: each array's first dimension equals that table's row count, and it may be numeric or text. The library interprets no key. It checks the shape of the registered **column-map keys** only: such a key has shape `[k]`, where k is the column count of another 2-D `extra` array, and holds commodity indices. The only one registered is `consumer_extra["utility_exponent_commodity"]`, for `utility_exponent`.

The dep1ex loader writes the keys below; their meaning belongs to the loader and to the prefab `hahnel` (the keys the WIOD loader writes are under "Loaders"):

| Table | Key | Shape | Meaning |
|---|---|---|---|
| Commodity | `hahnel_kind` | text[n_commodities] | The five class labels of Hahnel's model: `private_good`, `public_good`, `intermediate`, `natural_resource`, `labor`, laid out as five contiguous sections in that order |
| Consumer unit | `entitlement` | f64[n_consumers] | Consumption entitlement, an exogenous flow. dep1ex's `income` |
| Consumer unit | `utility_exponent` | f64[n_consumers, k] | Cobb-Douglas utility exponents. Column j's commodity is given by `utility_exponent_commodity` |
| Consumer unit | `utility_exponent_commodity` | int64[k] | The column-to-commodity map for the row above. A column can point to any commodity |
| Producing unit | `effort_c`, `effort_s`, `effort_k` | f64[n_units] | dep1ex's worker-council closed-form parameters `c`, `s`, `du`. `c` is also the effort exponent in the production function |

The prefab `hahnel` has five helpers that turn `hahnel_kind` into the index arrays the declaration arguments take: `private_goods`, `shared_goods` (the `public_good` class), `intermediate_goods`, `natural_resources`, `labor`; plus `resources` (natural resources and labour together) and `bads` (an empty array: the source model has no commodity with negative value).

`period` (int64) records which period this is.

**`Economy` is the state of a given period, not a fixed problem statement.** In multi-period runs, the evolution rule updates it. Holding it constant would weld the theoretical assumption "fixed technology, fixed input ratios" into the data model.

**`Plan` has two layers:**

```
Physical layer (theory-neutral, every mechanism has it)
├── Production side: output f64[n_outputs] (one quantity per output entry, aligned with Economy's
│           flat output arrays; its length is n_units when every unit has one output entry),
│           input_use f64[n_inputs] (aligned with Economy's flat input arrays)
└── Consumption side: consumption f64[n_consumers, k] plus consumption_commodity int64[k]
            ("who gets how much"; the column-to-commodity map follows the same pattern as
            Economy's utility_exponent),
            shared_use f64[n_commodities] (per commodity, the quantity the consumer units use
            in common and that is attributed to no single one of them)

Extension layer (mechanism-specific)
├── valuation: a named-array bag. Registered keys indicative_price / labor_value / shadow_price
│   (f64[n_commodities], NaN for commodities the mechanism leaves undefined) and
│   income / expenditure (f64[n_consumers]). Other keys are free
└── extra: a named-array bag for mechanism-specific physical quantities. The first dimension is one
    of n_units, n_consumers, or n_commodities.
    prefab hahnel writes effort (f64[n_units], the effort factor in the production function)
    and consumer_demand (f64[n_commodities], the contribution of consumer councils' stated plans to
    demand for each commodity: for public goods, the shared quantity counted once for society as
    a whole; for every other commodity, the sum of what the councils stated; zero for a commodity
    nobody stated demand for)
```

**`shared_use` is a use, not a supply.** Use in common means non-rival use: one party using the commodity does not reduce what another can use. It is zero for a commodity nobody uses in common. It is kept apart from `consumption` because a quantity used in common cannot be written per consumer unit and summed: 100 councils sharing one 50-acre park would sum to 5,000 acres. A commodity has one shared quantity, meaning everybody uses the same one; regional or tiered sharing cannot be stated. The prefab `hahnel` fills it on public goods with the councils' stated level (the sum of stated quantities divided by the number of consumer units, the same number `extra["consumer_demand"]` holds for those commodities), and with zero elsewhere.

**`expenditure`** is each consumer unit's total expenditure this period, in the unit of `income`, including its part of anything used in common. Like `income` it is an optional registered key; a mechanism that wants a budget difference fills it.

The valuation keys and the two conventional `extra` keys are all exported as constants: `INDICATIVE_PRICE`, `LABOR_VALUE`, `SHADOW_PRICE`, `INCOME`, `EXPENDITURE`, `EFFORT`, `CONSUMER_DEMAND`; the test is "vocabulary needed to read any plan." The `extra` keys on `Economy`'s three tables are mechanism input parameters, not vocabulary for reading a plan, so they stay bare strings.

dep1ex's production function is `Q = a · e^c · Π x_j^{b_j}`, where `e` is the effort a unit chooses each round and `c` is `effort_c`. The loader labels every unit `hahnel_cobb_douglas_effort` (`hahnel.TECHNOLOGY`), with one output entry of `output_coefficient = 1`. Reconstructing the full relationship requires `Plan.extra["effort"]`; `hahnel.technology()` is the technology for this label, see "Technology."

Input use must be stored in the physical layer; it cannot be dropped as a derived quantity — when the technology allows substitution, the input mix is a decision the mechanism made, not a computed result.

Aggregates by commodity are derived by accessors and not stored:

- `total_output(economy)`: `output` summed by `output_commodity` over output entries; a unit with joint products contributes to each commodity it lists
- `total_input_use(economy)`: input use summed by commodity
- `total_consumption(economy)`: the consumption columns summed by `consumption_commodity`; zero for commodities with no column
- `endowment_use(economy, resources)`: input use of the commodities in `resources`, zero for every other commodity. Which commodities draw on the endowment is the caller's statement and has no default: a call without `resources` is a `TypeError` from Python itself

**Three physical-layer fields can be absent**: passing `None` for `consumption`, `consumption_commodity`, or `shared_use` declares "this mechanism has no such quantity." `output` and `input_use` are required — every mechanism that plans production has both, and **passing `None` for them is an error at construction time**, not deferred to `validate`. Fields have no default value, so an omission is still a missing-argument error; absence can only be something the researcher wrote explicitly. `consumption` and `consumption_commodity` describe the same quantity and go in and out together. `Plan.absent_fields` reads back the declaration. An accessor that needs a field the plan lacks raises `PlanFieldAbsent` — **it does not return zero**, because a zero would enter a balance equation as a quantity the other side never held, and the two sides would no longer close.

Divergence monitoring covers only the physical fields a plan actually carries: a mechanism that reports only `output` and `input_use` gets a `diverged=False` that says only those two stayed finite. In determinism comparisons, both sides absent counts as consistent; one side absent and the other present is reported as `<field> (absent from one run)`, not as a numeric difference.

**`valuation`'s length has two tiers by key**: registered keys follow their registered row count (`indicative_price`, `labor_value`, and `shadow_price` are one per commodity; `income` and `expenditure` are one per consumer unit); other keys' first dimension is one of `n_units`, `n_consumers`, or `n_commodities`. The dtype must be `float64`, and it's **rejected rather than converted** — converting would erase the signal that "the mechanism computed this quantity in a different type."

**`Plan` has two subclasses**: `StatedPlan`'s `consumption` is the stated plan, `AllocatedPlan`'s is the allocated plan. A subclass only adds an identity — no added fields, no narrowed contract. `require_comparable(a, b)` refuses to subtract when the two sides are different subclasses. The prefab `hahnel` produces `StatedPlan`; the reference solution produces `AllocatedPlan`.

## Technology

`technology_kind` is a label, and the data model does not say what a label means. A **technology** is one reading of a label, and it answers one question: can a producing unit's planned inputs produce the unit's planned outputs, and by how much does each output fall short or exceed.

```
class Technology(Protocol):
    label: str
    def margin(self, economy, plan, unit) -> ndarray: ...
```

`margin` gives one number per output entry of the unit, in storage order: what the unit's planned inputs can deliver of that output minus what the plan records. A negative number means the plan asks for more than the inputs can produce. It receives the whole plan because some technologies read plan fields beyond `input_use` (Hahnel's reads `plan.extra["effort"]`). The interface is per unit, so a researcher writes the formula for one unit in plain Python without vectorizing. It does not assume that inputs and the mix of outputs can be treated separately.

**Assembly**: a separable technology has two halves.

- The input side, `InputSide.activity(economy, plan, unit) -> float`: how much the unit can run on its planned inputs
- The output side, `OutputSide.deliverable(economy, unit, activity) -> ndarray`: how much of each of the unit's output entries that activity delivers
- `SeparableTechnology(label, inputs, outputs)` joins the two; its margin is `outputs.deliverable(economy, unit, inputs.activity(economy, plan, unit))` minus the plan's output entries of the unit

Pieces the library ships:

| Piece | Side | Reading |
|---|---|---|
| `Leontief()` | input | The smallest `input_use / input_coefficient` over the inputs with a positive coefficient; a unit with no positive coefficient has infinite activity |
| `CobbDouglas()` | input | `technology_scale · Π input_use ^ input_coefficient` |
| `SingleOutput()` | output | The unit must have exactly one output entry, otherwise `ValueError` naming the unit; delivers `activity · output_coefficient` |
| `FixedRatios()` | output | Every output entry delivers `activity · output_coefficient`: outputs in fixed ratios |

The library recognises two labels: `LEONTIEF` reads as `SeparableTechnology(LEONTIEF, Leontief(), SingleOutput())`, and `COBB_DOUGLAS` as `SeparableTechnology(COBB_DOUGLAS, CobbDouglas(), SingleOutput())`. **`FixedRatios` is never attached to a label by default**: reading several outputs in fixed ratios is a statement about that unit's technology, so a researcher who wants it builds the technology and passes it in.

**The check tool** `technology_margins(economy, plan, technologies=None) -> TechnologyReport`:

- `technologies` maps labels to technologies; it adds to the two labels the library recognises and may override them
- The report carries `margin` (f64[n_outputs], 0.0 where not computed), `computed` (bool[n_outputs], which entries were computed) and `missing` (label → number of units carrying that label with no implementation). The arrays are read-only
- A unit whose label has no implementation is not computed and is counted, **never read under a guessed technology**
- A plan not shaped for the economy raises `SchemaError`; a technology that returns a number of entries other than the unit's output entries raises `ValueError`; a technology's own refusal (such as `SingleOutput` meeting a unit with joint products) propagates

The prefab `hahnel` provides `hahnel.technology()`, labelled `hahnel.TECHNOLOGY`, whose margin is `a · e^c · Π x^b − output`, with `e` read from `plan.extra["effort"]` and `c` from `unit_extra["effort_c"]`. The library does not read this label on its own; pass it in: `technology_margins(economy, plan, {hahnel.TECHNOLOGY: hahnel.technology()})`.

Every technology is a theoretical claim about production, so this is a tool, and it is not part of `plan_differences`. `tools.linearize.linearize` and the closed forms in `tools.leontief` and `tools.cobb_douglas` take only economies with one output entry per unit and refuse a unit with joint products; `linearize` writes every unit as `LEONTIEF` with `output_coefficient = 1`.

## Loaders

A loader reads published data into an `Economy`. The files are read in the Rust core, which hands back a mapping of columns; the Python side builds the `Economy` from it and validates it. Labels and behavioral parameters a loader writes go into `extra`, under keys whose names and meanings belong to the loader. A wrong argument, a file that cannot be read, or a file that does not have the expected layout raises `ValueError` or a subclass of it; an economy that breaches the data model raises `SchemaError`.

### `load_dep1ex(path, endowment=1000.0) -> Economy`

Reads one dep1ex archive: the input data of the participatory planning experiments of Hahnel, Szczepanczyk and Weisdorf, a gzipped Clojure data file.

- Commodities come in five contiguous sections, in this order: private consumption goods, public goods, intermediate goods, natural resources, labour. Each commodity's section is written in `commodity_extra["hahnel_kind"]`
- One producing unit per worker council, labelled `hahnel_cobb_douglas_effort`, with one output entry of `output_coefficient = 1`; `input_coefficient` holds the Cobb-Douglas exponents and `technology_scale` holds `a`
- One consumer unit per consumer council. Producing units and consumer units keep the order of the archive
- `endowment` applies to every natural resource and every kind of labour, and the other commodities get 0. The archives do not carry this figure; the default 1000 comes from the papers' text
- `period` is 0; the `extra` keys it writes are listed under "Data model"

### `load_wiod(path, year, labor=None, sea=None, exchange_rates=None) -> WiodTable`

Reads one year of the World Input-Output Database (WIOD), 2016 release. `path` is the release zip `WIOTS_in_EXCEL.zip` (from which `WIOT{year}_Nov16_ROW.xlsb` is read in memory, without extracting it) or one such `.xlsb` workbook. `year` must be an integer from 2000 to 2014; anything else, such as `2014.0` or `"2014"`, raises `ValueError`. It returns `WiodTable(economy, observed)`: `economy` is the economy the table describes, and `observed` is the year's recorded flows laid out as a plan of that economy. Equality of `WiodTable` is identity, as on `Economy`.

**The economy.** Values are millions of US dollars at current prices.

- One commodity per product: 44 economies (43 countries and the rest of the world, `ROW`) times 56 industries, 2464 commodities, in the table's row order. `commodity_extra["region"]` and `commodity_extra["industry"]` hold the two codes. Products have zero endowment
- Every product with positive gross output gets one producing unit, labelled `LEONTIEF`, with one output entry; `output_coefficient` and `technology_scale` are 1. Its inputs are the products it uses that have a producing unit, each at intermediate use divided by the unit's gross output. A negative intermediate-use entry raises `ValueError` naming the year, the two products and the value
- A product whose gross output is not above 0 keeps its commodity and gets no producing unit. Its own intermediate inputs must all be 0; otherwise `ValueError` names the product
- One consumer unit per final-demand column, five per economy, 220 in all. `consumer_extra["region"]` holds the economy and `consumer_extra["final_demand"]` the category (`CONS_h`, `CONS_np`, `CONS_g`, `GFCF`, `INVEN`)
- `unit_extra` holds each unit's `region` and `industry`, the rows below the table body (`taxes_less_subsidies`, `cif_fob_adjustment`, `purchases_by_residents_abroad`, `purchases_by_nonresidents`, `value_added`, `international_transport_margins`), and `unproduced_input_use`. The rows below the table body are not commodities and do not enter the material balance
- `period` is the year

**Products used but not produced.** When units use a product whose gross output is not above 0, that use is not an input entry of the unit: nothing produces the product and nothing holds it, and a Leontief unit that needed it could produce nothing. Each unit's total use of such products is in `unit_extra["unproduced_input_use"]` (0 for a unit that uses none; the key is present in every load). Whenever there is such use, the loader issues one `WiodUnproducedInputs` (a `UserWarning` subclass) naming the products, the number of units that use them and the total value, with no minimum amount. Every year of the 2016 release has such use.

**Units whose only input is labour.** Some units have positive gross output and no intermediate use at all (29 in 2014: industry `T` in 28 economies, and India's `O84`). Under `labor=None` they have no input entry, which a Leontief reading takes as production that needs no input. With a labour measure chosen, those with labour data have labour as their only input, and the rest of the world's has still none. The loader does not warn about them.

**Labour.** The world input-output table (WIOT) has no labour data. `labor=` decides whether labour enters the economy and as what, from the release's socio-economic accounts (SEA; `sea=` is the path of `Socio_Economic_Accounts.xlsx`):

| `labor=` | What it reads | Unit | Files needed |
|---|---|---|---|
| `None` (the default) | nothing: no labour commodity | | the WIOT file alone |
| `"compensation"` | compensation of employees (`COMP`), converted from national currency at the year's rate in `exchange_rates=` (`Exchange_Rates.xlsx`, US dollars per unit of national currency) | millions of US dollars | `sea=` and `exchange_rates=` |
| `"hours"` | hours worked by employees (`H_EMPE`) | millions of hours | `sea=` |

Neither measure includes the self-employed. Which one stands for labour input, or neither, is a theoretical choice the library does not make. With a measure chosen, each economy with data gets one labour commodity, after the products, with `commodity_extra["region"]` holding the economy and `industry` holding `labor`. Its endowment is the total labour input of the economy's units that year; each unit uses its economy's labour at its labour figure divided by its gross output. A labour figure on a product without a producing unit is no unit's input and is not part of the endowment. A measure whose files are not given raises `ValueError` naming the missing argument; `sea` and `exchange_rates` are read only when the measure needs them. The exchange-rate workbook codes Romania `ROM`, which the loader reads as the table's `ROU`, the one alias it accepts; a workbook that lists one economy twice raises `ValueError`.

**Labour gaps.** The rest of the world has no data under either measure, China has no hours, and a figure that is not a number is missing too. A unit without a figure gets no labour input, no zero and no estimate; `unit_extra["labor_observed"]` is 0 for it (1 for the other units; the key exists only when a measure is chosen), and the loader issues one `WiodLaborGap` (a `UserWarning` subclass) naming each economy affected and how many units it has. A figure of 0 is data, not a gap.

**The observed plan** `observed` is an `AllocatedPlan`, validated against the economy by the loader:

- `output` is gross output; `input_use` is intermediate use per input entry, and with a labour measure the labour entries are the labour figures
- `consumption` is final demand, one row per consumer unit and one column per product (`consumption_commodity` lists every product and no labour commodity). Negative entries, such as inventory draw-downs, are kept as recorded
- `shared_use` is 0 everywhere: the WIOT files all final use under some final-demand category
- No field is absent; `valuation` and `extra` are empty

On the observed plan the material-balance difference is 0 to within rounding, with one exception: on a product used but not produced, supply minus use equals what the units drew from it. Those uses are not input entries, while the negative final demand that offsets them in the table is kept.

## Multiple periods

The researcher chooses between static and rolling:

```
run_periods(economy, procedure, periods, seed, advance=None, next_procedure=None, check_period=True,
            bads=None, price=None, resources=None, constraints=(), differences=True) -> PeriodsResult
```

Not passing an evolution rule means static (the same economy is solved `periods` times); passing one means rolling (`Economy` is updated each period). Anyone not doing multi-period work never sees this concept.

**The evolution rule `advance(economy, plan, seed) -> Economy` belongs to the researcher.** It holds capital accumulation, technological progress, resource depletion, population change — each one a theoretical claim. The library provides a few common implementations as tools. It is called only between two periods, `periods − 1` times in total. The library assigns the seed it receives, so a random evolution rule is reproducible; the rule must not keep random state between two calls.

**The next period's coordination procedure is built by the function slot `next_procedure(previous_plan) -> Procedure`.** Whatever the previous period passes to the next one (for example the warm-start prices) the mechanism puts into the plan and reads back itself. Without it, every period reuses the same coordination procedure. The coordination procedure interface `solve(economy, seed)` does not change.

**Seed layout**: `split_seed(seed, 2 · periods)` gives `w₀ …`. Period i (counting from 0) uses `w₂ᵢ` for the coordination procedure, and the evolution rule that produces the economy of period i+1 uses `w₂ᵢ₊₁`. The last position is reserved. This layout is part of the determinism contract.

**Output**: `PeriodsResult.periods` keeps every period's economy, the `RunResult`, the coordination procedure's seed and the evolution rule's seed; `PeriodsResult.differences` is the cross-period difference report (see "Invariants"), `None` when `differences=False`. `bads`, `price` and `differences` are passed to every period's `run`; `resources` and `constraints` go to the cross-period differences computed after the last period. The one `differences` switch turns off both the per-period and the cross-period report.

**Soft check on the period number**: when the `period` returned by the evolution rule is not the previous one plus one, a `PeriodWarning` is issued. It does not raise and does not correct the value; `check_period=False` turns it off.

It's structurally the same as `iterate`: the value isn't running the loop for the researcher, but letting the library see that this is a trajectory — which is what makes cross-period provenance, multi-period output structure, and cross-period differences possible.

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

**Differences are always computed, and their names stay neutral.** Material balance, budget, and non-negativity can all be computed from a single run's output, and the library computes their differences and writes them into the output whether or not they were set as constraints — except where the mechanism leaves them undefined (direct labor-time calculation has no prices, so the budget difference is N/A for it, not 0, and the output must be able to show that). The naming is always "budget difference," never "budget-identity violation": the same number is a defect to one researcher and the object of study itself to someone running a credit-creation experiment. The library gives the number, not the verdict. (The decision records call these quantities residuals.)

### Conventions shared by every report

- A report states numbers only: its fields are differences, margins and minimums, with no pass/fail field and no tolerance. A difference is signed; no absolute value is taken
- **N/A is `None`, never NaN and never 0.** Each quantity that can be N/A comes with a `why_not_computed`, which is `None` when the quantity was computed and otherwise names what is missing. The library does not fall back or borrow a quantity from elsewhere. A NaN in a result only ever comes from a NaN or inf in the plan, carried through by floating-point arithmetic
- Which commodities are bads, which draw on the endowment and which valuation key holds the prices are the caller's statements, passed as arguments at the call site (`bads=`, `resources=`, `price=`). The library reads no `extra` key of `Economy` or `Plan`
- Reports are frozen dataclasses; arrays are float64 or int64 and read-only; mappings are read-only; sequences are tuples
- The differences are computed in Python with numpy. Sums by commodity use `np.bincount` in entry order, so the result is bit-for-bit deterministic

### Single-period differences

`plan_differences(economy, plan, bads=None, price=None) -> PlanDifferences` is a standalone function that works on any plan: one from `run`, from the reference solution, read back from a file, or produced by someone else's code. It first checks that the plan is shaped for the economy and lets the `SchemaError` propagate if not (a malformed plan is an error, not an N/A); a `plan` that is not a `Plan` raises `TypeError`.

`run(procedure, economy, seed, bads=None, price=None, differences=True) -> RunResult` calls it after `solve` returns and outside the timed region, and attaches the report as `RunResult.differences`; with `differences=False` the field is `None` and the plan is not read. `wall_seconds` covers `solve` alone. `check_determinism` does not compute differences.

The report, `PlanDifferences(material_balance, budget, non_negativity)`, has three parts.

**Material balance**, `MaterialBalance`, one number per commodity in every field:

- `supply = total_output + endowment`, where `total_output` is `plan.total_output(economy)`, joint products counted under their own commodities
- `use = total_input_use + total_consumption + shared_use`
- `difference = supply − use`
- When the plan declares `consumption` or `shared_use` absent, use by consumer units is unknown, so `use` and `difference` are N/A for the whole vector, and the reason lists the absent fields in declaration order; the components the plan does carry are still filled in

**Budget difference**, `BudgetDifference`, one number per consumer unit: `difference = income − expenditure`.

- It is computed only when all three are in the plan's `valuation`: the price key the caller names with `price=`, `INCOME` and `EXPENDITURE`. The library does not guess which key holds prices and does not fall back to the consumer units' `entitlement`
- When something is missing, the reason lists what is missing in a fixed order: no declared price (listing the valuation keys the plan carries), the declared price key not in the plan, no `income`, no `expenditure`
- `income` and `expenditure` are filled in whenever the plan carries them, even when the difference cannot be formed
- `priced_consumption` is each consumer unit's row of `consumption` valued at the declared price. It is a reconciliation column: `expenditure − priced_consumption` is what the unit spent outside the consumption block. It is `None` when the plan has no consumption block or no price
- A `price=` naming a key registered as one entry per consumer unit (`INCOME`, `EXPENDITURE`) raises `ValueError`, even when the economy has as many consumer units as commodities; so does a `price=` naming an array that does not hold one entry per commodity

**Non-negativity**, `NonNegativity`:

- Quantities checked: `output`, `input_use`, `consumption` and `shared_use`, whichever the plan carries
- Prices checked: every registered per-commodity key the plan carries (`indicative_price`, `labor_value`, `shadow_price`), as entries named `valuation.<key>`, skipping the commodities in `bads`. A bad exempts prices only; a negative quantity on a bad is still counted. `bads=None` means no commodity is a bad
- Each entry has a `minimum` (NaN ignored; `None` when nothing is left to check) and a `negative_count`
- `not_checked` lists every entry that was not checked, with the reason: a field the plan declares absent, a valuation key the library has not registered (it does not know what the key holds), nothing left to check after the exemption, or every value left to check being NaN. The last two reasons are stated apart: an entry of NaN alone is not reported as having no entries

### Cross-period differences

`period_differences(economies, plans, resources=None, constraints=()) -> PeriodDifferences` accepts any trajectory, `plans[t]` being the plan for `economies[t]`, including one from the researcher's own loop. Sequences of unequal length, or empty ones, raise `ValueError`. `run_periods` calls it after the last period.

- **Cumulative resource use**: `resources` declares the commodities whose input use draws on the initial endowment. `initial_endowment` is period 0's endowment of those commodities, row t of `cumulative_use` is `endowment_use` summed over periods 0 to t, and `resource_difference = initial_endowment − cumulative_use`, signed. When no `resources` are declared, or when some period's commodity count differs from period 0's (so the same index no longer names the same commodity), all three are N/A and `why_resources_not_computed` says which
- **Consumer units**: `consumer_units` counts each period's consumer units and `consumer_unit_change` is the change between consecutive periods. Always computed
- **Non-negative capital stock** and **the stock-flow identity** are never computed: the data model has no capital stock and no stock carried from one period to the next. They appear only in the coverage table, with that reason

**The coverage table**, `PeriodDifferences.coverage`, has exactly four rows, in the order `cumulative_resource_use`, `consumer_unit_count`, `capital_stock_non_negativity`, `stock_flow_identity` (the four names are constants in `demplan.differences`). Each row is `Coverage(name, computed, why_not_computed, declared_constraint)`: `declared_constraint` echoes whether the caller named the row in `constraints=`, and an unknown name raises `ValueError` listing the four. Which of them constrain a given model is declared by its evolution rule or prefab; the library echoes the declaration and does not judge the numbers against it.

Their character differs from the single-period batch, and the document calls this out separately: **a single-period invariant violation is visible to the researcher on the spot** (this period's plan is infeasible), **but a cross-period violation is not** — when the evolution rule computes something wrong, every subsequent period's coordination procedure computes a fully self-consistent answer to a wrong problem, every check passes, the charts look fine, and the error grows with the number of periods, silently the whole way.

### Homogeneity and start-independence

**Price homogeneity of degree zero is a property test, not a difference.** It's a property of the coordination procedure, and a single run's output doesn't contain it.

`check_homogeneity(procedure, economy, seed, rescale, factor) -> HomogeneityReport` runs `run(procedure, economy, seed, differences=False)`, runs again with the same seed on the procedure and economy that `rescale(procedure, economy, factor)` returns, and compares the two plans with `compare_plans`. The library does not decide which quantities are nominal; the caller passes in how to scale them. Two uses:

- **Start-independence**: `rescale` changes only the procedure's starting valuations
- **Homogeneity of degree zero**: `rescale` scales every nominal quantity the researcher declares

The prefab `hahnel` ships two: `scale_starting_price` (the initial price alone) and `scale_nominal_quantities` (the initial price, every consumer council's `entitlement` and every worker council's `unit_extra["effort_s"]` together), both for `HahnelBook2021` only.

The report carries `factor`, `rescale` (the function's qualified name), `comparison`, and both runs' round counts and convergence (`None` when the procedure did not use `iterate`). `factor` must be finite, above zero and other than 1, or `ValueError`; a `rescale` that returns anything but a pair raises `TypeError`. It does not judge pass or fail; the researcher sets the tolerance.

### Indicators

The library ships two general functions that carry no theory, in `demplan.indicators`:

- `input_use_on(economy, plan, commodities) -> float`: the plan's input use summed over the listed commodities, equal to `plan.endowment_use(economy, commodities).sum()`. The labour total of a Hahnel plan is `input_use_on(economy, plan, hahnel.labor(economy))`
- `compare_plans(plan, other) -> PlanComparison`: for each of `output`, `input_use`, `consumption` and `shared_use`, the `max_relative_difference` over entries of `|a − b| / max(|a|, |b|)`, counting an entry where both are 0 as 0 and letting NaN through. That number does not depend on the argument order. A field absent from one or both plans, `consumption` compared between a stated and an allocated plan, and `consumption` when the two plans' columns name different commodities go into `not_compared` with the reason; the other fields are still compared. A field both plans carry with different shapes raises `ValueError`

Welfare, GDP, speed of convergence and similar indicators each carry theoretical commitments and stay out of the library.

The toolbox will keep growing. SFC accounting identities (stocks as accumulated flows, transaction-flow matrix rows and columns summing to zero) are the next planned addition; their behavioral-equation part does not enter the foundation layer.

## Determinism

The library's half guarantees bit-for-bit reproducibility: data loading, `Evaluator`, scan scheduling, and seed distribution all produce bit-for-bit identical results for the same scenario file and the same seed. Parallel reductions use deterministic chunking and don't depend on thread count or scheduling order.

`seed` is an integer from 0 to 2⁶⁴−1. `split_seed(seed, n)` derives n child seeds using SplitMix64; `rng(seed)` returns numpy's `default_rng(seed)`.

A researcher-supplied coordination procedure is arbitrary Python, and the library cannot guarantee its determinism. The library hands it the seed (`solve(economy, seed)`) and provides `check_determinism(procedure, economy, seed, n)` for self-testing — it runs several times, compares the output, and reports where they differ if they don't match. This is a tool, not a gate. **It compares three categories: physical columns, `valuation`, and `extra`**; entries from the latter two carry a `valuation.<key>` or `extra.<key>` prefix. The order is physical columns, then `valuation`, then `extra`, with keys within each bag sorted by name. A physical column absent on one side and present on the other is reported as `<column> (absent from one run)`, not as a numeric difference. There's no runtime enforcement: Python has no real sandbox, and a randomized coordination procedure is legitimate research. What's guaranteed is "reproducible given a seed," not "no randomness allowed."

## Run configuration document

`run_configuration(procedure, economy, seed, loader=None, plan=None, *, periods=1, advance=None, next_procedure=None)` produces a **loadable** configuration document: it comes out at the end of a run, and feeding it back in gives the same configuration. This is **a separate document** from the run manifest — the configuration document holds configuration, the manifest holds provenance, and the configuration document's hash goes into the manifest. Keeping them separate lets a load tell clearly which half is input; otherwise, feeding it back in would treat the previous run's result as input.

**It is not welded into `run`.** The economy's content hash is not computed inside `run`: computing it costs something (0.064 seconds for dep1ex01's 53 MB), and a parameter sweep of thousands of runs shouldn't pay that cost every time. The researcher calls it explicitly.

`periods`, `advance` and `next_procedure` are the arguments of the same names given to `run_periods`, and `periods` is refused as `run_periods` refuses it (anything but a Python or numpy integer of at least 1, `bool` included).

The format is JSON (UTF-8, sorted keys, indent 2, `allow_nan=False`). There are eight top-level keys: `configuration_version`, `library_version`, `core_version`, `seed`, `economy`, `procedure`, `loader`, `plan_fields_absent`. A multi-period run (`periods > 1`) writes three more: `periods`, `advance` and `next_procedure`, the last two as origin blocks, `null` when not given. A single-period run writes none of them, so its document has the same bytes as one written by a library without these keys. A single-period configuration that carries an evolution rule or a next-procedure slot is refused on writing and on reading. A multi-period document reproduces the whole trajectory (initial economy, seed, evolution rule, next-procedure slot, number of periods); later periods' starting points are not in the document and are recomputed by rerunning the trajectory.

**The economy is content-hashed** byte-for-byte with no precision loss, under the algorithm identifier `sha256-columns-v3`:

- A numeric column is converted to C order and normalized to little-endian, and `column-name\ndtype\nshape\n` (UTF-8) is prepended to the bytes fed into sha256
- A **text column** (dtype kind `U`) has the same three header lines, with `text` on the dtype line; then, for each label in row order, its UTF-8 byte length as an 8-byte little-endian unsigned integer followed by those bytes. The width numpy stores the labels at is not part of the digest
- Each key of the three `extra` bags counts as a column named `<bag>.<key>`; the overall digest is the sha256 of the per-column digests concatenated after sorting by column name
- The columns come from `Economy`'s current fields and carry the field names, such as `output_offsets` and `output_coefficient`; the library keeps no list of column names
- **A scalar column's shape line reads `1`** (a 0-D array is promoted to 1-D), and integer scalars are normalized to int64 first
- Object and structured dtypes are rejected, with the offending column named: the first's bytes are memory addresses, and the second's dtype string carries no field names, so two different columns would collide
- A numeric column digests under v3 exactly as under v2

**Any change to any step requires bumping the algorithm identifier.** **Per-column digests are stored alongside the overall digest**; `compare_economy_digests` compares two of them and returns an `EconomyDigestReport` naming which columns differ — this is what makes cross-platform floating-point last-bit differences diagnosable. Comparison is refused when the two digests' `algorithm` differ. **The library doesn't verify this automatically**; comparison is a tool the researcher calls explicitly.

**Implementations shipped with the library are content-hashed; the researcher's own are not**: for library-shipped ones, the module's source file gets a sha256; for the researcher's, only their declared provenance is recorded, and it's `null` if none is given. **A known gap**: `run_configuration` has no argument yet through which the researcher can declare provenance, so `declared_origin` in the researcher's block is always `null` for now. **Both sides record parameters** — a parameter is data, not code, and the library can introspect the researcher's data classes the same way it introspects its own. numpy scalars are recorded by value.

Versioning rules: a missing key in a document falls back to its default (an old document must still work with a new library); an unknown key is an error that distinguishes its two causes (the library is older than the document, or the key has been retired — the latter is checked against a registry of retired keys); a `configuration_version` newer than the library is an outright error. **A newly added key's default must preserve the old behavior** — if that's not possible, the key can't be added silently.

**Three things this document does not promise, which the researcher should know:**

- `plan_fields_absent` records the field names the researcher declared, and **the library does not check whether they're actual fields on `Plan`**. This is a direct consequence of duck typing without importing `Plan`: misspell a field name by one character and it goes into the document unchanged — nothing turns red.
- `source_digest` hashes the **entire module source file**, so it's **just as sensitive to comment-level changes**. When two documents' `source_digest` differ, that could mean the behavior changed, or it could mean someone edited a docstring.
- Parameters of type `Enum`, `datetime`, `complex`, or `set` **fall back to an "undeclared" form; their values do not enter the document**. JSON-native scalars and containers (including numpy scalars) are recorded by value; `np.ndarray` is not recorded, because its size is unbounded.

## Execution and storage

The entire economy stays resident in memory as columnar f64 arrays. A single iteration round never touches disk: reads happen only at the start of a run, writes only at the end.

v1's Rust layer holds only three things: storage and schema validation for `Economy` and `Plan`, the data loader, and Parquet output. Proposal behavior, `iterate`, prefabs, the reference solution, the technology check and the differences live in Python. The differences are computed with numpy and take about 1 to 2 % of a run on dep1ex01. On the Python side, `Economy` and `Plan` are immutable data classes with numpy-array fields. Errors returned from Rust are converted at the binding layer into Python exceptions that inherit from `ValueError`.

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
