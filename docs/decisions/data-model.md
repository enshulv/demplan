# Data model

## 2026-09-28

### WIOD loader: one economy per year, with an observed plan

**Decision** (five recommendations the maintainer accepted on 2026-09-28):

1. **Which tables**: the world input-output tables (WIOT, 2000–2014) of the WIOD 2016 release are required; each year loads into one `Economy` with `period` set to the year. The socio-economic accounts (SEA) are optional and used only when the caller passes the file.
2. **The unit of labour is the caller's choice**: the loader has a `labor=` argument (compensation in money, or hours worked from the SEA). Both are data; choosing one is a theoretical choice, so the library does not make it for the researcher.
3. **Final demand**: each of the five final-demand categories of each economy (households, non-profit institutions, government, gross fixed capital formation, changes in inventories) is one consumer unit, 44 × 5 in all, with the economy and the category recorded in `consumer_extra`. The loader also returns an **observed plan**: the year's recorded intermediate use and final demand, so researchers can compare a mechanism's plan with what happened.
4. **Rows that are not commodities** (taxes less subsidies, value added and the other rows below the intermediate block) are not commodities; they are kept as they are in `unit_extra`. Changes in inventories are a consumer unit under point 3 and may be negative.
5. **No emissions for now**: the JRC environmental accounts are added as an optional extension once their source has been checked.

The file format and whether the code sits on the Rust or the Python side are decided after inspecting the real files, under the existing principles (performance architecture: loaders live in the Rust core).
The rows marked ⚠ in the field mapping ([research/wiod-field-mapping.md](../research/wiod-field-mapping.md)) are checked against the real files before implementation.

**Why**: The maintainer decided the WIOD loader is done before publication, so researchers who want real input-output tables can start work.
After the kinds were opened, two of the four gaps in the field mapping are no longer gaps: two-level grouping (the economy goes into `extra`) and "one commodity is both a private and a public good" (the consumption side is split into `consumption` and `shared_use`). The remaining negative entries are handled by the signed definition of the residuals, and valuation in money is explained in the documentation.

**Rejected alternatives**:
- Fix labour to compensation, or to hours — makes a theoretical choice for the researcher
- Put government consumption into `shared_use` — in the observed data government consumption is use recorded by industry; whether it is non-rival is an interpretation, not data
- Make the value-added rows commodities — they are not produced or used, and putting them into the material balance would create a false balance

---

## 2026-09-27

### "How much endowment is used" depends on the caller declaring which commodities count as resources

**Decision**: `Plan.endowment_use` no longer decides by commodity kind. Instead, the caller states which commodities
count as resources, for example `endowment_use(economy, resources=...)`; the Hahnel module provides translation
functions such as `hahnel.natural_resources` and `hahnel.labor`. The cross-period residual "cumulative resource use
against the initial endowment" is built on it. Without a declaration, the result is N/A and states which declaration
is missing.

**Why**: Decided by the maintainer. Once commodity kinds are removed, the library cannot tell which commodities are
resources. Deciding by "endowment greater than 0" gives unchanged results on dep1ex, but it overcounts a commodity
that has an opening stock and is also produced in the same period. Suppose 200 tons of grain are left from last year
(endowment 200), 800 tons are produced this year, and 900 tons are used. Counting everything with endowment greater
than 0 gives 900, more than the stock. How much of the 900 tons comes from the stock is itself an accounting
convention (use old stock first, or new output first). Multi-period runs that roll leftover output into the next
period's endowment, and WIOD's changes in inventories, both produce such commodities. A declaration makes no
accounting assumption on the researcher's behalf. A default of N/A is in tension with "residuals are computed by
default so researchers see the gaps," but the N/A states which declaration is missing, so the gap stays visible.

**Alternatives rejected**:

- Count every commodity with endowment greater than 0 — overcounts commodities that have a stock and are also
  produced, with no error
- Take the smaller of use and endowment — chooses the "use stock first" accounting convention for the researcher
- Drop "endowment used" and compare cumulative use with cumulative endowment per commodity — for commodities that are
  being produced, this comparison has no meaning

**Supersedes**: Partially supersedes the algorithm in 2026-09-05, "Single-output units; endowment use is a derived
quantity," that aggregates endowment use by kind. "Endowment use is not stored in `Plan` and is derived from input
use" is unchanged.

---

### The core technology interface is "can these inputs produce this set of outputs," plus an assembly helper

**Decision**: The core technology interface asks only one question: can this producing unit's set of inputs produce
this set of outputs (the answer says how far off it is). It does not assume that inputs and the output mix can be
treated separately. The library also provides an assembly helper that combines two simple pieces into a complete
implementation: an input-side production function (given the inputs, what activity level they support; one formula)
and an output-side rule (given this activity level, how much of each output comes out; for example, the fixed
proportions the library provides). Simple cases use the assembly helper and write only one formula. Researchers
studying complex joint production implement the core interface directly.

**Why**: Decided by the maintainer: the solution must be theory-neutral, but it must not raise the bar for the typical
researcher. "First the inputs determine an activity level, then the activity level determines the output mix" is a
theoretical assumption (separability). It holds for an oil refinery. It does not hold for sheep farming, where the
feed itself affects the ratio of wool to mutton. The core interface does not make this assumption. A researcher
working on a complex problem would have to build the model themselves without this library too, so leaving the core
interface for them to write is not a problem. A typical researcher uses the assembly helper, and writes the same code
as with a production function alone.

**Alternatives rejected**: Chain the two interfaces as the only way to connect them — easy to write, but it welds the
separability assumption into the interface.

**Supersedes**: Partially supersedes the same day's "The technology-form interface asks one question: the production
function": the production function moves from being the core interface to being the input-side piece of the assembly
helper. "The bar for researchers implementing a new form must be low" and "use it to check whether a plan is
technically feasible" are unchanged.

---

### Joint products: the data model records a quantity per output, output proportions come from a pluggable implementation, and the library provides fixed proportions but does not attach them by default

**Decision**: A producing unit's outputs become a flat array plus offsets, the same as its inputs: each unit lists its
output commodities, and the plan's `output` records one quantity for each (unit, output) pair. The data model neither
records nor assumes proportions between outputs. The relationship between outputs comes from a pluggable
implementation, which researchers can write themselves. The library provides one implementation, "fixed proportions"
(each unit of activity yields each output in its declared proportion), but **does not attach it by default**; whoever
wants it attaches it. Each dep1ex unit has only one output, so results are the same as now.

**Why**: Decided by the maintainer: the output proportions of joint production must not be fixed to one theory, and
the library must still connect to WIOD quickly. "Fixed output proportions" is an assumption within joint-production
theory (input-output analysis, Sraffa, and von Neumann use it; whether the product mix can be adjusted is itself
disputed). A data shape that records a quantity per output can hold fixed proportions; the reverse is not true. The
fixed-proportions implementation lets WIOD and environmental-account data of the "emission factor" type (each sector's
emissions proportional to its output) plug in directly, so researchers don't each write their own version with their
own standard.

**Alternatives rejected**:

- The data model records "activity level + fixed proportions" — easiest to implement, but writes fixed proportions
  into the fixed layer
- Record a quantity per output but provide no implementation — everyone writes their own for WIOD, with no common
  standard
- Attach fixed proportions by default — this makes it the library's default theory

**How to apply**: How the "output relationship" interface fits with and attaches to the technology interface just
decided (the production function) is taken up in the same round of questions.

---

### The technology-form interface asks one question: the production function

(The core interface's role is partially superseded by the same day's "The core technology interface is 'can these
inputs produce this set of outputs,' plus an assembly helper.")

**Decision**: The technology-form interface requires an answer to only one question: given a producing unit's inputs,
how much can it produce (the production function). A researcher implements a new technology form by writing a class
with a label and this one method; the form's own parameters go in `unit_extra`. With this, the library can check
whether a plan is technically feasible: for each unit, whether its planned inputs can produce its planned output.

**Why**: Decided by the maintainer. Every technology form can answer with a production function; it just means writing
out the formula, so the bar for researchers implementing a new form is as low as it gets. Checked one by one, nothing
in the library currently asks this question of an arbitrary technology: the reference solution reads Leontief
coefficients directly, the linearization tool only divides a plan's input use by its output without looking at the
technology form, and Hahnel uses its own hard-coded Cobb-Douglas with an effort factor. "Is this technically feasible"
is a check the library cannot do now, and it matters in practice: of the 30000 units in a Hahnel plan, only 34 satisfy
the Cobb-Douglas relation without the effort factor. With the effort factor they all match, and only Hahnel's
implementation knows the effort factor.

**Alternatives rejected**:

- Add "the least-cost input mix" — lets price-coordination mechanisms be written independent of technology, but many
  forms have no closed-form solution, so researchers would have to write numerical optimization; a high bar, and slow
  to compute
- Add "a linear approximation" — the linearization tool can already read fixed proportions from a plan without looking
  at the technology form, so most of the functionality overlaps

---

### `technology_kind` becomes a text label, and researchers can add technology forms

**Decision**: `technology_kind` stays a fixed column of the producing-unit table, but changes from a closed integer
enum to a text label, such as `"leontief"` or `"cobb_douglas"`; researchers can use names of their own. Validation no
longer rejects labels the library does not know. The library's tools handle only the forms they know, and raise an
error with the reason when they meet an unknown one. The library provides a technology-form interface; a researcher
who implements it can use their own technology form instead of the two the library presets. The content of the
interface is decided separately.

**Why**: Decided by the maintainer: technology functions matter a great deal in economic research and are themselves
much disputed, so presetting only two is clearly not enough. A text label carries its own meaning and costs
researchers little to use.

Unlike `commodity_kind`, this column cannot be removed: what the numbers in `input_coefficient` mean depends on it.
The same set of numbers is a fixed proportion when read as Leontief and an exponent when read as Cobb-Douglas. The
column currently accepts only two values (`economy.py:44-48`; validation at `economy.py:263` and on the Rust side), so
OLIN-EP's nonlinear input-output model in the spec's use-case table does not fit, and neither does CES.

**Alternatives rejected**:

- Keep integer codes and open up the values — when two researchers each use the same code for different forms, the
  exported data does not show it
- Remove the column, and move the technology form into `unit_extra` together with `input_coefficient` and
  `technology_scale` — the fixed layer keeps only the input structure, and someone who receives an economy cannot tell
  what the technology is without reading the bag; the largest change

**How to apply**: The Rust side and the numpy side change from an int8 column to a string column, and the
canonicalization for the economy digest changes accordingly.

Guarding against typos: the library exports constants for the forms it knows (such as `LEONTIEF = "leontief"`). Code
uses the constant, so a typo makes Python report on the spot that the name does not exist; the data still stores text.
A researcher's own form carries its label in its interface implementation, so it does not need to be typed again
elsewhere. For text typed by hand with a typo, a tool that meets an unknown label raises an error that lists the known
labels and names the closest one.

---

### `provision` becomes "the quantity in shared, non-rival use" and records how much is used

**Decision**: `Plan.provision` stays an optional fixed field, with a new definition: the quantity, per commodity, that
belongs to no single consumer unit and is used in common (non-rival use: one party's use does not reduce what is
available to another). It holds the **quantity used**, not the quantity produced. Total use on the consumption side =
the sum of the rows of `consumption` + `provision`, and the material-balance residual is computed from this without
reading any kind or attribute. The Hahnel prefab now fills in the stated level of the shared commodities (the sum of
the councils' stated quantities divided by the number of councils, the same as the original program's `csvgen.clj`
lines 699-703, which is the segment it currently writes into `extra["consumer_demand"]`) instead of the supply. The
reference solution already fills in use, and is unchanged.

**Why**: Decided by the maintainer: use a theory-neutral concept. Don't call it a "public good"; only say that it is
in shared, non-rival use. Rivalry is a physical property: when one party eats a loaf of bread the other has one fewer,
while one party's use of a park does not prevent another's. Shared use cannot be recorded in the per-consumer-unit
table and then summed; otherwise 100 councils that each want a 50-mu park would be counted as 5000 mu.

After commodity kinds are removed, the spec's original definition ("how much of a public good is produced in total,
shared") no longer refers to anything. Meanwhile Hahnel filled in output and the reference solution filled in use: the
same name with different meanings, and with Hahnel's version the material balance on these commodities is structurally
always 0. With both unified as quantity used, one formula holds for both, and the library does not need to read any
mechanism's private keys.

**Alternatives rejected**:

- Remove `provision` and add a neutral "consumption-side total" fixed field — the total and the per-consumer-unit
  table are two copies of the data; the library does not know which commodities are shared, so it cannot check that
  they agree
- Remove `provision` and record shared use in the per-consumer-unit table too, with the caller declaring which
  commodities are shared — when `run` calls the residual function by default it has no declaration, so the material
  balance for plans with shared commodities could only be N/A by default
- Keep "how much was produced" — same name as the reference solution's field with a different meaning, and the
  material balance would have to read Hahnel's private keys

**Known limitation**: A commodity has only one shared quantity, meaning everyone shares the same amount. Regional
sharing (each country has its own government services) and tiered sharing still cannot be expressed. This is a gap
found by the 2026-09-05 design review, and this entry does not solve it.

**Supersedes**: Partially supersedes the 2026-08-30 and 2026-09-05 definitions of `provision` ("how much of a public
good is produced in total, shared"). The parts saying it can be absent and is recorded separately from `consumption`
are unchanged.

---

### Remove the fixed columns `commodity_kind`, `unit_group`, and `consumer_group`

**Decision**: `Economy` drops three fixed columns: the commodity table's `commodity_kind`, the producing-unit table's
`unit_group`, and the consumer-unit table's `consumer_group`. Loaders and prefabs that need such labels put them in
the corresponding `extra` bag, under key names of their choosing. For example, the dep1ex loader writes
`commodity_extra["hahnel_kind"]`, and a WIOD loader can write `unit_extra["industry"]` and `unit_extra["region"]`. The
Rust side's `Economy`, validation, the dep1ex loader, the PyO3 bindings, and the economy digest change accordingly.

**Why**: Decided by the maintainer: a fixed column the library never reads is dead code and only adds redundancy. Once
the library defines no attribute vocabulary, `commodity_kind` has no reader in the library; only the Hahnel module
reads it. `unit_group` and `consumer_group` never had readers (in `python/` and `crates/` they are referenced only by
their definitions, validation, loader writes, and binding exports). A fixed column must be filled for every economy,
so a researcher who needs no classification has to fill in a meaningless value, and the words "kind" and "group" in
the names make readers think the library has a classification scheme. With the columns removed, the two levels of
grouping WIOD needs (industry × economy) can be expressed with two `extra` keys, no longer limited to one level.
`consumer_group` is in the same situation as `unit_group` and is removed for the same reason.

**Alternatives rejected**: Keep them as free-form labels (as 2026-09-05 did for `unit_group`: the library neither
validates nor interprets them) — still required, still implies a classification, and still has no reader.

**Supersedes**: Partially supersedes 2026-09-05, "`unit_group` is an arbitrary grouping label; the library does not
validate its range": the part of that entry that keeps `unit_group` as a fixed column is replaced by this one. Its
reasons for refusing to pin `unit_group` to a dense index and for not deciding ahead of time for Stage 3 carry over
into this entry.

---

### Built-in models provide only small, descriptively named translation functions, with no bundling and no one-call comparison

**Decision**: Each built-in model's package (such as `demplan.prefabs.hahnel`) provides small functions that translate
its own labels into sets of commodities, with names that state their meaning, for example `hahnel.labor(economy)` and
`hahnel.public(economy)`. Researchers use them to pass arguments to the general tools. Which reference solution to
compare against is still written out by the researcher. The library provides no way to bundle declarations and expand
them with `**`, and no one-call comparison function.

**Why**: Decided by the maintainer: the literal name is the meaning, and it reads clearly. The deeper things are
wrapped, the more Python technique a call requires, and the library cannot assume much Python skill from social
scientists. A one-call comparison would also have to choose the objective for the researcher, which conflicts with
"the comparison benchmark is declared by the researcher."

**Alternatives rejected**:

- Bundled declarations (`reference_solution(economy, MinimizeLabor(targets), **hahnel.declarations(economy))`) — the
  call site doesn't show what is passed, and `**` expansion is an obstacle for readers not fluent in Python
- One-call comparison (`hahnel.compare_with_reference(economy, result)`) — chooses the objective for the researcher;
  once the objective is made a required argument, it reduces to bundling plus one call

**How to apply**: Researcher-facing interfaces should read like a sentence: parameter and function names state their
meaning, and callers are not required to know techniques such as `**`, decorators, or protocol classes. Every new
built-in model provides translation functions in the same way.

---

### The library defines no commodity-attribute vocabulary; declarations a tool needs are passed by the caller at call time

**Decision**: `Economy` carries no commodity attributes named by the library, and the library registers no
conventional attribute keys. When a library tool needs to know a split such as "which commodities count as labor" or
"which are shared," the caller passes it as an argument at call time. Each loader's and prefab's own labels go in
`commodity_extra`; the key names and meanings belong to them, and the library does not read them.

**Why**: Decided by the maintainer. From the researcher's point of view, the two approaches, "the library registers
conventional keys and tools read them automatically" and "define nothing," were compared step by step:

- Checked one by one: once nothing is defined, the only declarations the caller must supply are two or three
  parameters of the reference solution (the split between private allocation and shared use, which commodities the
  labor-minimizing objective sums, and which commodities may carry consumption weights). The Hahnel prefab reads its
  own labels. Stage 2's three residuals need no attributes, and `endowment_use` can decide from the fixed column
  `endowment` instead (an inference, to be checked before implementation)
- Comparability relies on the run configuration document recording the coordination procedure's parameters; a
  reproducer's importer reads them as is. It does not rely on the economy carrying its own declarations
- The risks of conventional keys: when the key name is right but the meaning differs (for example, a loader records
  "labor" as wage amounts), tools use it anyway with no warning; reading the code does not show which declarations a
  tool used; and the registered key names are themselves a small vocabulary

**Alternatives rejected**:

- Fixed attribute columns (the library defines a few columns that every economy must fill) — welds a classification
  into the fixed layer, which is exactly what this work is removing
- Conventional keys (the library registers key names, and tools read them automatically when present) — see the three
  risks above; it would also be the first time library-level code reads a key from `Economy`'s `extra`

**How to apply**: The run configuration document must be able to record these parameters in full (whether array-valued
parameters are written out in full is to be checked during implementation). For the built-in models, see the entry
"Built-in models provide only small, descriptively named translation functions."

---

### Commodity kinds, technology kinds, and joint products are opened up together; the five kind tags move into the Hahnel package

**Decision**: Three theory-laden restrictions in the fixed layer are lifted in the same work package: the closed enum
of commodity kinds, the closed enum of technology kinds, and "a producing unit has only one output." dep1ex's five
commodity kind tags (private consumption goods, public goods, intermediate goods, natural resources, labor) are no
longer public constants of the library; they move into the dep1ex loader and `demplan.prefabs.hahnel`. Order: this
work package comes first, and Stage 2's residual tools come after it.

**Why**: Decided by the maintainer: infrastructure must not presuppose a theory, and not every researcher accepts
Hahnel's model. The five-kind enum comes from Hahnel's model and dep1ex's data shape; keeping it at the library's top
level implies that the world consists of these five kinds. The three restrictions are the same kind of problem, so
they are handled together, and the WIOD loader and Stage 2 face the final shape without being changed twice. Stage 2
comes after because the non-negativity residual needs to know which commodities are bads and the cross-period
residuals need to know which count as endowment; with kinds opened up first, Stage 2's tools read the declared content
from the start.

**Alternatives rejected**:

- Open up only commodity kinds, and leave technology kinds and joint products as they are — Stage 2 and WIOD would
  first be written for "one output per unit," then changed again when joint products arrive
- Keep `CommodityKind` in the library's public interface as "the dep1ex convention" — the library's top level would
  keep implying one worldview
- Do Stage 2 first — the residuals would first be written for the five kinds, then reworked when kinds are opened up

**How to apply**: Where attributes attach, whether the library defines an attribute vocabulary, and what `provision`
means are taken up in the same design round; once decided, they are recorded further in this file. This entry
schedules the 2026-09-05 entries "Commodity kinds open up, but only together with declarable kind properties" and
"Joint products move up in delivery order"; it does not change their content.

---

> "Coordination procedure" corresponds to the code identifier `Procedure`; "evolution rule" corresponds to `advance`. Code is always in English.

## 2026-08-30

### Commodities share one table with a kind tag, not separate tables per kind

**Decision**: All commodities live in one table, each row tagged with a kind. dep1ex currently has five kinds:
private consumption goods, public goods, intermediate goods, natural resources, and labor. Natural resources and
labor are in the same table too; they have prices and take part in price adjustment just like the others.

**Why**: Adding a new kind is then just one more tag value, not a structural change. This project's v1 already needs
an emissions extension, and a money-stock extension is coming later — both will add entries to this same table.

Splitting into five tables would be type-safer, but `research/bench/repro.py:137`'s
`np.where(cat == 0, ..., np.where(cat == 1, ...))` shows that real computations routinely need to treat all kinds
uniformly; separate tables would turn this into a five-way branch every time.

**Alternatives rejected**: see [rejected/data-model.md](rejected/data-model.md)

---

### `Plan` splits into a physical layer and an extension layer; the extension layer keeps a free-form bag

**Decision**: The core of `Plan` is the **physical allocation**, theory-neutral and present for every mechanism:

```
Plan (period t)
├── Production side: each producing unit → output (by commodity), input use (by commodity)
├── Consumption side: private goods "who gets how much", public goods "how much is produced in total, shared"
└── Endowment use: how much natural resource is used, how much labor
```

Valuation quantities form the **extension layer**: the library predefines a few common ones (indicative price,
labor value, shadow price), plus a free-form bag where researchers can put valuation kinds the library did not
anticipate.

**Why**: `Plan`'s field set is itself a theoretical commitment — hard-coding it as "quantities plus prices" amounts
to claiming that every plan must include prices, but plans under the labor-time school have no prices at all.

The split's placement has an independent check: running the four invariants against it, the two theory-neutral ones
(material balance, non-negativity) can be computed from the physical layer alone, while the two theory-laden ones
(budget identity, zero-degree homogeneity of prices) need the extension layer. **This is not a coincidence — a
physical allocation is a fact every school agrees on, and prices are exactly where they disagree.**

This makes the "compute it if you can; N/A is not zero" rule hold automatically in the data structure: under a
labor-time mechanism, `Plan` simply has no price slot, so price-related checks are automatically N/A.

The free-form bag exists because a closed enumeration would force researchers to wait for a library release just to
add one more valuation kind, which runs into [coordination-procedures.md](coordination-procedures.md)'s rule that
"the extension mechanism is an interface, not a list the library maintains."

**How to apply**: Input use must be stored in `Plan`, not dropped as a derivable quantity. Under Leontief it truly is
derivable (output times a fixed coefficient), but once technology allows substitution (Cobb-Douglas), **the same
output can come from different input mixes, and which mix was chosen is a decision made by the mechanism**. So
`Technology` has been an extensible type from day one, designed with substitutability in mind.

---

### `Economy` is mutable across periods

**Decision**: `Economy` is **the state of one period**, not a fixed problem statement. Across multiple periods it is
updated by the evolution rule:

```
Economy₀ ──solve──> Plan₀ ──┐
                            ├──evolution rule──> Economy₁ ──solve──> Plan₁ ──> ...
                            ┘
```

**Why**: Making `Economy` permanently fixed would weld a theoretical assumption into the data model —
**fixed technology, fixed input ratios**. Once you want to study technological change, resource depletion, or
population change, that assumption breaks down, and long-run sustainability is one of the main battlegrounds in
debates about democratic economic planning.

A theoretical presupposition baked into the data model is more hidden than one baked into a check, because no check
will ever flag its presence.

This doesn't conflict with [phasing-and-granularity.md](phasing-and-granularity.md)'s "the time dimension goes into
the data model from the start," but that decision is about a **single multi-period solve** (cross-period
optimization, solving all T periods' plans at once, with `Economy` fixed), while this one is about **rolling
multi-period** use. Both are valid; `Economy` accommodates both at once: it can carry known data for T periods
(future endowments, population forecasts) and also be advanced to the next period. Static or rolling is the
researcher's choice; see [evolution-rule.md](evolution-rule.md).

**Alternatives rejected**: see [rejected/data-model.md](rejected/data-model.md)

**How to apply**: v1 uses dep1ex, a single period, so the evolution rule is never exercised in practice. But the
interface has to be designed now around "`Economy` is one period's state" — if it were written as an immutable
problem statement, adding the evolution rule later would mean changing every coordination procedure's signature,
which is a rewrite.

---

### Variable-length inputs are stored as a flat array plus an offset table

**Decision**: Each producing unit has a different number of input commodities (in dep1ex, anywhere from a handful
to more than a dozen). These are stored as one flat array plus a table of "where each unit's inputs start," rather
than padded into a rectangular matrix.

**Why**: Padding into a rectangle (what `research/bench/repro.py` currently does) wastes a lot of memory when the
number of inputs per unit is uneven. Flat-plus-offset is compact and contiguous, matching
[performance-architecture.md](performance-architecture.md)'s "columnar `f64` arrays, whole economy resident in
memory."

This is an internal implementation detail with no externally visible consequence; it doesn't change any behavior a
researcher can observe.

---

## 2026-09-05

### Prices do not go into `Economy`

**Decision**: `Economy` has no price column. Valuation quantities live in exactly two places: `Plan`'s extension
layer, and the coordination procedure's own `State`. Warm-start starting prices are held by the coordination
procedure itself, as one of its parameters or as part of its `State`.

**Why**: `Economy` is the fixed layer, and the fixed layer is theory-neutral. Prices are a valuation quantity; under
the school that computes labor time directly, `Economy` has no price column at all. The 2026-08-30 decision
"commodities share one table with a kind tag" said "they have prices and take part in price adjustment just like the
others" — that sentence describes how dep1ex data gets *used* under parecon, not a field of `Economy`. Leaving that
sentence in the spec would have put a price column into the fixed layer as early as Stage 0.

**Partially narrows**: this narrows the sentence "they have prices and take part in price adjustment just like the
others" in the 2026-08-30 decision "commodities share one table with a kind tag, not separate tables per kind." The
one-table-with-a-kind-tag structure itself is unchanged.

**How to apply**: Checks that need prices (budget residual) read them from `Plan.valuation`; coordination procedures
that need prices initialize their own.

---

### `Economy` splits into a fixed core and named extension columns, mirroring `Plan`

**Decision**: `Economy` is made of three columnar tables: commodities, producing units, consumer units. Each table
has a set of fixed columns plus a named-array `extra` bag.

Fixed columns hold only what every school agrees exists: identifiers, groupings, commodity kind, endowment, output
commodity, and technology type with its parameters (input commodities, input coefficients, scale coefficient).

Behavioral parameters — in dep1ex, a producing unit's `c`, `s`, `du`, and a consumer unit's utility exponents and
consumption entitlement — go into `extra`, with key names fixed by library documentation and interpreted by prefabs.

**Endowment is a column in the commodity table**: how much is available this period without any production. It is
0 for output goods; for dep1ex, natural resources and labor are each 1000.

**Why**: A production function's shape can be made an extensible type, but every behavioral parameter is a claim
made by one particular school (the shape of effort disutility, Cobb-Douglas utility, exogenous consumption
entitlements). Putting them in fixed columns would violate theory-neutrality; not putting them in `Economy` at all
would leave the dep1ex loader nowhere to place them, and the evolution rule would have no way to update them. Named
extension columns are the same pattern as `Plan`'s extension-layer free-form bag.

**Alternatives rejected**:

- A dedicated table per kind of behavioral parameter — every new paper reproduced would add another table, running
  into [coordination-procedures.md](coordination-procedures.md)'s "the extension mechanism is an interface, not a
  list the library maintains"

**How to apply**: Key-name conventions go into `spec.md`. Every key the loader writes into `extra` must be
documented there, with its source and meaning.

---

### `Plan`'s extension layer predefines an `income` slot

**Decision**: `Plan.valuation`'s predefined keys gain `income` (per consumer unit). The budget residual can be
computed whenever `valuation` has both a price key and `income`; when `income` is absent, it falls back to
`Economy` consumer-unit `extra`'s `entitlement`; if neither is present, the residual is N/A.

(The fallback sentence is partially superseded: the budget residual now needs prices, income, and all spending
supplied by the mechanism, and no longer falls back to `entitlement`. See
[invariants-and-metrics.md](invariants-and-metrics.md) 2026-09-27.)

**Why**: The budget residual needs each participant's income. The physical layer doesn't have it, and none of the
three previously predefined extension-layer valuation kinds have it either. Without adding this slot, the budget
residual would be N/A for every mechanism.

---

### Single-output units; endowment use is a derived quantity

**Decision**: In v1, each producing unit has exactly one output commodity. Endowment use is not stored in `Plan`; it
is obtained by aggregating input use by commodity.

**Why**: Both dep1ex and input-output tables (with a diagonal make matrix) are single-output. Multiple outputs can
later be added by adding a flat `output` array, without changing the identity of the existing columns. Endowment use
is a deterministic aggregate of input use; storing it twice would let the two copies drift.

**Partially narrows**: this changes "endowment use" in `spec.md`'s physical layer from a stored item to a derived
one. The rest of the 2026-08-30 decision "`Plan` splits into a physical layer and an extension layer" is unchanged.

---

### `Plan` gains an `extra` bag; dep1ex's technology is Cobb-Douglas with an effort factor

**Decision**: `Plan` gains `extra: Mapping[str, ndarray]`, the same pattern as the `extra` on `Economy`'s three
tables: named arrays whose first dimension is one of `n_units`, `n_consumers`, or `n_commodities`. The prefab
`hahnel_2020_slides` writes two conventional keys: `effort` (`f64[n_units]`) and `consumer_demand`
(`f64[n_commodities]`, the consumer councils' stated demand's contribution to demand for each commodity). The second
key was originally named `public_demand` and recorded only public goods; it was generalized on 2026-09-05 (see
below).

**Why**: A comprehensive adversarial review (2026-09-05) independently traced the upstream Clojure code and found
that dep1ex's production function is `Q = a · e^c · Π x_j^{b_j}`, where `e` is an effort level each unit chooses
every round and `c` (`effort_c`) is its exponent in the production function — not merely a behavioral parameter. All
eight closed-form solutions upstream return effort, and the loader was previously discarding it. Without recording
effort, `Plan` cannot be used to reconstruct "what technological relationship do output and input satisfy" as a
metric — on dep1ex01's converged plan, only 34 of 30,000 units satisfy the declared Cobb-Douglas relationship, with
a median deviation of 8.6%.

Public goods have the same problem: `provision` is supply, and there is nowhere to put consumers' stated demand for
public goods; material balance for public goods is then always 0.

Both quantities are mechanism-specific physical quantities, not valuation quantities, so `valuation` is the wrong
place for them; putting them in fixed columns would weld dep1ex's model into the physical layer. Hence a bag shaped
like `Economy.extra`.

**Partially narrows**: this narrows this document's 2026-09-05 decision "`Economy` splits into a fixed core and
named extension columns" where it described `effort_c` as a "behavioral parameter." `effort_c` is also a technology
parameter; `effort_s` and `effort_k` remain behavioral parameters. For dep1ex, `technology_kind = 1` means "the
input side is Cobb-Douglas"; the full production function also has an effort factor, and the documentation must say
so.

**How to apply**: `tools.cobb_douglas` produces an input bundle without the effort factor, which differs from the
prefab's input mix; the tool's documentation states this.

---

### The dep1ex loader derives `n_goods` only from input codes, and checks that segment codes stay in bounds

**Decision**: `n_goods` is the maximum value across the three input-code segments, and does not fold in `:product`.
`:product` and the input codes must each fall within `[1, segment size]` for their own segment; out-of-range codes
raise a `LoadError`.

**Why**: `:product` numbers private goods under `:industry 0` and public goods under `:industry 2`; it does not share
a numbering space with intermediate goods, natural resources, or labor. Folding it into the maximum would
conjure up phantom commodities — with an endowment but no demand — whenever there are more kinds of private or
public goods than of the other kinds, and no price-adjustment mechanism would ever converge. dep1ex01 through 05
each have 100 of every kind, so the bug was invisible; a hand-built fixture from adversarial review (4 private
goods, input codes up to 3) reproduced 3 phantom commodities and 250 rounds without convergence. Out-of-range codes
would silently rewrite a commodity's kind.

The rule was wrong in the specification (stated as "all `:product` values plus the maximum code appearing across
the three segments"). The implementation followed it literally and raised the concern in its own report, but the
specification was not corrected. The differential test's fixture then copied the same rule from the implementation,
so nothing ever caught the error.

**How to apply**: A differential test's expected values must come from an independent reference
(`repro.py:223`), not be derived from the implementation itself.

---

### The utility-exponent column can point at a commodity of any kind; the split criterion is "is it a private good"

**Decision**: The commodity that `utility_exponent_commodity` points at can have any of the five `commodity_kind`
values. `hahnel_2020_slides` splits consumption demand into two groups based on whether the column's commodity is a
private good: the private-good group becomes `Plan.consumption`; everything else (public goods, and commodities
that are neither private nor public) is folded into commodity demand under its own pricing rule.

**Why**: The private-good group has to be handed to `Plan.consumption` unchanged, so it must be its own contiguous
array. Everything else is only ever used once, in an aggregate, and is thrown away — splitting it further would
buy nothing.

A private/public binary split would silently drop the third kind of column — that demand changes the price path and
the number of rounds to converge, yet nothing would ever report an error.

**Alternatives rejected**:

- A private/public binary split — see above, the third kind of column gets silently dropped
- Reject the third kind of column outright — it's not a malformed declaration. The computed demand and price path
  are both correct; it's simply not recorded in the plan. Rejecting it would mean the library deciding, on the
  researcher's behalf, that "households do not directly consume natural resources" — and relabeling natural
  resources as a private good would also drop their production use from `Plan.endowment_use`'s endowment
  accounting. The library gives numbers, not verdicts; see [invariants-and-metrics.md](invariants-and-metrics.md)

**How to apply**: Code that reads `commodity_kind` is written against all five kinds, not against a
private/public binary. The third kind of column's demand is recorded by `consumer_demand`; see the next entry.

---

### `public_demand` generalizes to `consumer_demand`, covering all three kinds of columns

**Decision**: The conventional key `public_demand` in `Plan.extra` becomes `consumer_demand`, `f64[n_commodities]`,
recording the consumer councils' stated demand's contribution to demand for each commodity: for private goods, the
sum across councils (equal to `total_consumption`); for public goods, the shared amount counted once for society as
a whole; for the remaining commodities, the un-divided total; commodities nobody claimed demand for are 0. The old
key equals `np.where(public_commodity, consumer_demand, 0.0)`, so it is derivable and is not kept alongside the new
one.

**Supersedes**: the fact, in the 2026-08-30 decision "`Plan` gains an `extra` bag," that the key written was
`public_demand`; the rest of that decision still holds.

**Why**: When the utility-exponent column points at a commodity that is neither private nor public, that demand
still counts toward commodity demand, participates in imbalance, and changes the number of rounds to converge — and
then is nowhere to be found in the plan. Recomputing material balance from that plan produces a different economy.
This is exactly the problem `public_demand` was added to `extra` to solve in the first place; at the time, only
public goods were considered.

Generalizing rather than adding a parallel key, because all three kinds of columns record the same thing: this
round's consumption-side demand entering material balance. Two separate keys would suggest they are two different
kinds of quantity.

While here, this also fixes a missing term in the README's material-balance example: it used to read
`total_input_use + total_consumption + public_demand`, which is missing a term whenever the third kind of column is
present; it now reads `total_input_use + consumer_demand`, two terms.

**Alternatives rejected**:

- Add a separate key for just the third kind of column — `extra` stays asymmetric, and readers have to stitch three
  keys together to get consumption-side demand
- Keep `public_demand` alongside the new key — redundant, and the two would inevitably drift apart

**How to apply**: `Plan.validate` still does not enforce which keys `extra` has; that is unchanged. Generalizing an
already-registered conventional key costs nothing while there are no external users, and costs a lot once there
are — catch a wrongly scoped conventional key early.

---

### Two conventional keys in `Plan.extra` get exported constants; `Economy.extra`'s keys do not

**Decision**: `Plan.extra`'s `effort` and `consumer_demand` each get an exported constant (`EFFORT`,
`CONSUMER_DEMAND`), added to `__all__`. The keys in the `extra` bags of `Economy`'s three tables (`entitlement`,
`utility_exponent`, `utility_exponent_commodity`, `effort_c/s/k`) stay as bare strings. The criterion is: **export a
constant only for vocabulary that is required to read a plan.**

**Why**: Comparability comes from raw output, not from reading each other's code
([coordination-procedures.md](coordination-procedures.md)). Two researchers comparing their runs must use the exact
same string to mean the same thing; if one of them typos a key as `efort`, the two runs can never be matched up
after the fact, and nothing would flag the mistake at the time. `Plan`'s documentation already states that without
these two keys, a plan's production function and material balance cannot be reconstructed — they are required
reading for anyone reading a plan, not a private concern of one mechanism.

`Economy.extra`'s keys don't meet this bar: they are inputs to the mechanism, and someone reading a plan doesn't
need them.

**Alternatives rejected**:

- Export nothing from either bag — `valuation` already exports four constants, so this would be inconsistent, and
  a typo'd key would still go unnoticed by anything
- Export both bags — this would suggest the library validates these keys, when the spec explicitly says "their
  presence is up to the loader and the prefab; the library does not require them." `Economy.extra`'s keys have no
  matching reader that would benefit
- Base it on "does library code read it today" — right now no library code reads any `extra` key (the residual
  toolbox isn't written yet), so this criterion returns an empty list, while the problem already exists today

**How to apply**: When adding a new conventional key in the future, ask: **can someone who doesn't know this key
still read the plan?** If not, export a constant for it.

---

### `unit_group` is an arbitrary grouping label; the library does not validate its range

(The fixed column itself is partially superseded: on 2026-09-27 `unit_group` was removed, and grouping moved to
`unit_extra`.)

**Decision**: `unit_group`'s value is defined as an arbitrary grouping label; it is not required to fall within
`[0, n_groups)`, and `validate` does not check it. The spec's field table states this.

**Why**: No code in the library aggregates by `unit_group`; defining a range for it would have no consumer and would
be an empty promise. There is also no `n_groups` field — one would either have to be added, or inferred as
`max + 1`, which would make range-checking trivially true.

More importantly, [research/wiod-field-mapping.md](../research/wiod-field-mapping.md) already found that
`unit_group` has only one level, and cannot express both "grouped by industry" and "grouped by economy" at once.
Pinning it down as a dense index now would amount to deciding that question for Stage 3 ahead of time.

**Alternatives rejected**: Require it to fall within `[0, n_groups)` — see above: no consumer, and it conflicts with
a candidate design for Stage 3.

---

### `Plan`'s fixed fields become optional per field, starting with `consumption` and `provision`

**Decision**: `Plan`'s fixed fields become individually optional — at the granularity of a **single field**, not a
group of fields. This round covers only `consumption` (together with `consumption_commodity`) and `provision`;
`output` and `input_use` are untouched. The pairing constraint gets its own guard: `consumption` and
`consumption_commodity` must be present together or absent together; having only one is an error.

**Absence must be a researcher's declaration**, not an accident. What belongs in a plan is part of how the
researcher builds it, and it's their responsibility — an absence that doesn't match the declaration is an error.
But **declaring it must be cheap** — this must not make writing a mechanism harder.

**Partially supersedes**: the "all fixed fields are required" part of the 2026-08-30 decision "`Plan` splits into a
physical layer and an extension layer." The split into layers and the free-form bag are unchanged.

**Why**: The fixed layer had things with theoretical commitments baked in, and theory-neutrality in the base layer
is a hard constraint ([invariants-and-metrics.md](invariants-and-metrics.md)). A 2026-09-05 adversarial design review
found, one by one:

- `consumption` is "private goods allocated per consumer unit," which commits to exclusive consumption and to "an
  identifiable consumer unit existing." An input-output-style mechanism that only balances totals has no such
  quantity
- `provision` is one scalar per public good — that is, a Samuelsonian pure public good, equal for all of society. It
  cannot express regional or tiered supply
- `output` and `input_use` are close to neutral — any mechanism that plans production has them, so they are outside
  this round's scope

Per-field rather than per-group, because field granularity is more flexible, while group boundaries drawn wrong have
to be redrawn later; the pairing constraint is handled with an explicit guard, which is more direct than folding it
into a grouping scheme.

**Alternatives rejected**:

- Optional by layer (field group) — the group boundaries would have to be fixed first, and neutral fields like
  `output`/`input_use` would be forced into a group anyway
- Not distinguishing "declared absent" from "left out by mistake" — leaving it out becomes silent, exactly the
  failure mode this library keeps trying to prevent
- Accessors return zero when a field is absent — the library would then have one quantity dropped for some
  mechanisms and fully counted for others, and the two sides wouldn't reconcile. This is exactly the shape of
  `endowment_use`'s existing defect

**How to apply**: When an accessor's required field is absent, it must **raise an exception that clearly names what
is missing and how to supply it**. The user is a researcher, not an engineer, and shouldn't have to trace the cause
by reading a stack trace; a generic exception is only a fallback.

---

### Stated plan and allocated plan: one field plus subclass specialization

**Decision**: `consumption` stays one field, with the **broadest** meaning — "the consumption-side quantity."
Specialization is expressed with subclasses, following the Liskov substitution principle:

```
Plan                    broadest meaning, doesn't state which kind
 ├─ StatedPlan(Plan)     consumption is the consumer councils' stated demand
 └─ AllocatedPlan(Plan)  consumption is the solved allocation
```

A subclass narrows none of the parent's contract; it only adds a declaration. Without a tag, the default is the
broadest reading. Comparing differences is dispatched on type: two sides of the same kind may be subtracted; sides
of different kinds are rejected, with an explanation.

**Why**: These two quantities are already living in the same field today, and nothing catches it. A 2026-09-05
experiment found: the prefab's `consumption` is the demand matrix computed by `_demand`, while the reference
solution's is the LP solution's allocation after `allocate`; `validate` passes on both. On dep1ex01's converged
plan, every private good is over-produced by between 3.04% and 3.35% — that plan is not a feasible allocation.

The consequence is that comparability silently breaks: a researcher computing "unmet demand = stated − delivered"
would get a structural 0 for the reference solution and around 3% for the prefab, and that difference comes from the
two fields meaning different things, not from economics.

Keeping one field rather than splitting into two, because **no mechanism today produces both quantities** — the
prefab only ever has a stated demand, the reference solution only ever has an allocation. Splitting the field would
create a slot with no user today.

The concept of "proposal versus stated demand" was already identified as something the data model must not lose:
[phasing-and-granularity.md](phasing-and-granularity.md), when establishing "ground truth is the set of producing
units, not a matrix," says exactly this — "a row in a matrix has no concept of a 'proposal,' and a council is a
decision-making body." This decision brings that principle down to `Plan`.

**Alternatives rejected**:

- Split into two fields — creates a slot with no user today, and the name `consumption` would have to be either
  retired or redefined
- Put the semantics in a string tag inside a bag — cheap to serialize, but the semantics become runtime data, and a
  typo in the tag has to be caught by convention alone
- Attach the semantics to the layer declaration — the same layer can't then have two fields with different
  semantics

---

### Commodity kinds open up, but only together with declarable kind properties

**Decision**: `CommodityKind`'s whitelist validation opens up (in both `economy.py` and the Rust side), **but not on
its own** — at the same time, kind properties move from hard-coded to declarable: whether a kind is consumable,
whether it counts as an endowment, which layer(s) it participates in.

**Why**: Opening the whitelist on its own buys little. The evidence:

- **Emissions are not blocked by the enum being closed — they're blocked by "one output per unit."**
  `output_commodity` is a single value per unit; the natural model for emissions is a joint product. Every
  workaround is unclean: negative input coefficients are undefined in the Leontief and Cobb-Douglas tools; giving
  every unit a paired "emissions unit" would double the unit count and scramble the meaning of `unit_group`
- **Neither is a money stock.** `progress.md`'s deferred-work list says "add a **field**, don't change what a row
  represents," while the spec used it as an example of "adding a kind" — the two already contradicted each other;
  see the next entry for the fix
- The one real thing this buys: a researcher can attach a private tag the library doesn't recognize, without
  forking

Meanwhile `objectives.py`'s `_require_consumable_support` rejects any unrecognized kind outright. **An open enum with
hard-coded properties is a label with no meaning**: a researcher can attach it, but none of the library's tools will
recognize it once attached. So opening the enum has to come paired with declarable properties.

**Alternatives rejected**:

- Open the whitelist alone — see above, half-open
- Keep it closed and make README and spec honestly say "extensible" is not accurate — adopted briefly on
  2026-09-05, then rejected after re-evaluating against "not bound by the phasing schedule": honest, but closes off
  this path for extension

**How to apply**: The four places that dispatch on kind (`objectives.py`'s consumability check and
`_split_equally`, `plan.py`'s `_ENDOWED_KINDS`, `reference.py`'s consumable mask) all need to switch to reading a
declared property instead of a hard-coded tuple. Wherever this can't be done, **raise an error, never silently
zero out** — silently zeroing out would give every new kind a defect shaped like "a quantity that affects the
outcome without being recorded."

---

### Producing units may have multiple outputs (joint products)

**Decision**: `Economy`'s unit table drops the "exactly one output commodity per unit" restriction, and supports
joint products.

**Why**: This is the key to the emissions experiment, and emissions are an explicitly stated use case in the
charter. Steel and CO₂ are produced simultaneously by the same unit; this structure cannot be expressed today, and
it has nothing to do with whether commodity kinds are open. Fixed capital and Sraffa-style joint production hit the
same wall.

**Alternatives rejected**: Model emissions as a negative input coefficient — the library's two technology tools have
no defined behavior for negative coefficients; give every producing unit a paired "emissions unit" — doubles the
unit count and scrambles the meaning of `unit_group`.

**How to apply**: `output_commodity` and the related `bincount` aggregations (`Plan.total_output`, the prefab's
`_aggregate`, the reference solution's constraint matrix) all assume one output per unit; each one needs
re-examining. This change reaches deeper than the `Plan`-layering work, and it gets its own work package.

---

### Joint products move up in delivery order, evaluated in the same round as the `Plan` layering work

**Decision**: Joint products are no longer scheduled last. They join the same round of scheduling evaluation as
`Plan` layering and opening up kind properties; the actual order among them is set by build dependencies, not by
"the deeper the change, the later it goes."

**Why**: A 2026-09-05 survey of three comparable implementations found that `pablovegan/Economic-Planning` has a
`pollutants_constraint`, treating an ecological ceiling as an ordinary constraint run on real supply-and-use tables
for Spain and Sweden. Before this, "emissions are blocked by 'one output per unit'" was only backed by this
project's own reasoning; now there is a second, independent implementation as evidence, and Szczepanczyk (2023)
lists "environmental impact" among its seven directions for future work.

The original reason for scheduling it last was "this change reaches deeper than `Plan` layering." **Depth of change
is a cost to build, not a priority.** Schedule by need, not by cutting it out of the phase plan; see
[scope-and-purpose.md](scope-and-purpose.md) 2026-09-05.

**Alternatives rejected**: Keep it scheduled last — emissions are an explicitly stated use case in the charter;
scheduling an explicitly stated use case behind every optional improvement would put the delivery order at odds with
the charter.

**How to apply**: This only changes **order**, not the content or the rejected alternatives of the
[previous entry](#producing-units-may-have-multiple-outputs-joint-products); the two stand side by side. When
scheduling, count "the reference solution's constraint matrix needs rewriting" as part of the cost — it is the most
expensive of the three `bincount` aggregations.

**Related**: [research/related-implementations.md](../research/related-implementations.md)

---

### `Plan.valuation` doesn't validate dtype or length; folded into the `Plan`-layering work package

**Decision**: Arrays in `Plan.valuation` are validated for neither dtype nor length — this is a confirmed defect.
**It will not be patched at the coordination-procedure layer**; it is folded into the `Plan`-layering work package
instead.

**Why**: Found while fixing B2 on 2026-09-05, via an escape-probe test; three symptoms share one root cause —

- A price rule returns `int64`, so the archived `indicative_price` is `[893, 937, 704]`, when the honest value is
  `[899.5, 943.8, 711.3]`
- A price rule returns `float32`, silently losing precision
- A price rule returns a constant array one element too long — for an economy with 15 commodities, 16 entries get
  archived, and nothing reports it

**This is the same class of defect as B2**: the archived numbers don't match the numbers actually used, and nothing
says so. The difference is that B2's root cause was at the coordination-procedure layer, while this one's root cause
is in `Plan`.

Patching it only at the `PriceRule` call site would block just one caller; `valuation` is the shared entry point
every mechanism uses to write valuation quantities, and any one mechanism returning the wrong dtype would silently
get archived — the check belongs at that entry point.

**How to apply**: Do this together with the `Plan`-layering work. Check two things — every `valuation` array is
`f64`, and its length equals `n_commodities`. ⚠ **Reject, don't convert**: silently converting `int64` to `f64`
would erase the signal that "the rule computed the wrong type," swapping one silent failure for another.

**One incidental ruling**: `prefabs/hahnel_2020_slides._owned_copy` is an unconditional
`np.array(array, copy=True)` with no `isinstance` guard, which is why a rule returning a Python list works today
(it used to raise `TypeError` on the next round's indexing). **Keep this as is** — it lets "the library owns
`next_price`" hold unconditionally, and the slack it leaves is exactly what the check above will eventually take
back.

**Related**: [coordination-procedures.md](coordination-procedures.md) 2026-09-05, "arrays handed to researcher code
are copies the library owns"

---

## 2026-09-06

### `Plan` declares absence with `None`; a missing required field still errors at construction

**Decision**: Turns the 2026-09-05 decision "`Plan`'s fixed fields become optional per field" into a buildable
specification.

**Why**: That decision set three principles — "optional per field, absence must be declared, declaring it must be
cheap" — but didn't specify what represents absence, what an accessor raises, or where the run configuration
document reads the declaration from. All three are shapes that had to be pinned down in advance; leaving them open
would mean whoever implements it decides on the spot, which is exactly the kind of gap this project's process is
meant to prevent.

**`None` is the declaration of absence.** Fields **have no default value**, so leaving one out is still caught
directly by Python's "missing required argument" error, while explicitly writing `consumption=None` is the
researcher saying "my mechanism has no such quantity." Declaring it therefore costs one word.

**Alternatives rejected**: Add a separate `absent=("consumption",)` parameter — the same fact would have to be
written twice (setting the field to `None`, then naming it again), and any mismatch between the two would need its
own rule to resolve.

**Pairing guard**: `consumption` and `consumption_commodity` must both be `None` or both be arrays; supplying only
one is an error.

**The accessor raises a dedicated exception**, `PlanFieldAbsent` (a subclass of `SchemaError`). The message has
three parts: which field is missing, why this accessor needs it, and — "if your mechanism genuinely has no such
quantity, this accessor does not apply to you." **It never returns zero** — the library would then have one
quantity dropped for some mechanisms and fully counted for others, and the two sides wouldn't reconcile.

**`Plan.absent_fields -> tuple[str, ...]`**, returning absent field names in field-declaration order. This is the
sole entry point the run configuration document uses to read "which layers were declared"; its signature is fixed.

**`valuation` validation**: every array must be `f64` and its length must equal `n_commodities`, **rejected, not
converted** — silently converting `int64` to `f64` swaps one silent failure for another. This fulfills the "how to
apply" of the same day's decision "`Plan.valuation` doesn't validate dtype or length."

**Subclasses**: `StatedPlan` and `AllocatedPlan` add only an identity, no fields, and narrow no contract. Paired
with a `require_comparable(a, b)`: passes when both sides are the same kind, or either side is the base `Plan`;
rejects — with an explanation of what differs — when one side is `StatedPlan` and the other is `AllocatedPlan`.
**The difference-presentation component itself is out of scope for this round** — `decisions/comparison-and-presentation.md`
only set the principle, not the concrete list; building it now would mean pre-selecting from that list.

**How to apply**: These are buildable shapes, not a new charter item. Where they conflict with entries above, the
entries above take precedence.

---

### `valuation` validates length per key: conventional keys use their registered row count, others pick one of three

**Decision**: Overturns half of the same-day decision "every array in `valuation` must have length `n_commodities`."
New rule:

| Key | Length |
|---|---|
| `indicative_price`, `labor_value`, `shadow_price` | `== n_commodities` |
| `income` | `== n_consumers` |
| Any other key | first dimension is one of `n_units`, `n_consumers`, `n_commodities` |

The `float64` requirement is unchanged. The error message must distinguish the two cases: for a conventional key,
"this key is registered as one-per-X"; for any other key, "the first dimension must be one of the three."

**Why**: Half of the earlier rule was wrong; implementation pushed back on it. When it was written, only
`indicative_price` and `shadow_price` were visible, both one-per-commodity, and "one per commodity" got generalized
into a blanket rule for all of `valuation`. But `income` is **one per consumer unit**, established by the 2026-08-30
decision "`Plan`'s extension layer predefines an `income` slot," and both `README.md` and `spec.md` already state
`f64[n_consumers]`. A blanket rule would break that slot on any economy where `n_consumers != n_commodities`.

The new rule is **stricter** than the blanket one: for a key the library recognizes as conventional, it checks the
exact length it knows that key means; for a key it doesn't recognize, it has no known meaning for the row count, so
it can only check one of three — the same pattern, and the same reasoning, as `Plan.extra`'s
`_require_extra_rows`.

**Partially supersedes**: overturns the sentence about `valuation`'s **length** in the same-day decision
["`Plan` declares absence with `None`"](#plan-declares-absence-with-none-a-missing-required-field-still-errors-at-construction).
"Reject, don't convert" and the `float64` requirement are both unchanged.

**How to apply**: Whenever a new conventional key is added to `valuation`, **register what it is one-per at the same
time**, or it falls into the looser three-way check by default.

⚠ When this decision was written, the checklist omitted `labor_value`; implementation registered it as
`n_commodities` by the general rule and pushed back — backed by `README.md` and the constant's own documentation
(embodied labor time per commodity). **The registration table is the single source of truth**; it must not be
scattered across several pieces of prose. This decision's table has now been completed.

---

### Four implementation details of the `Plan` layering settled

**Decision**: Four questions that came up during implementation, settled one by one.

1. **`absent_fields` is a property**, not a method. The run configuration document already consumes it as a
   property on both sides; they are already aligned.
2. **`absent_fields` lists `consumption_commodity`** too, taken literally — it returns every optional field that is
   `None`. It is a list of **fields**, not of "layers."
3. **`require_comparable` raises `ValueError`**, not `SchemaError`. `SchemaError`'s documentation says it means "a
   structural violation," and comparability is not a structural problem; `SchemaError` is a subclass of
   `ValueError`, so `except ValueError` catches both.
4. **`valuation`'s dtype check runs in `__post_init__`; its length check runs in `validate`.** `run()` does not call
   `validate`; if both checks lived only in `validate`, then "a price rule returns `int64`, and the archived value
   is the truncated one" — the very symptom that motivated this decision — would still go unflagged on the prefab's
   default path. dtype needs no economy to check; length needs `n_commodities`, so only the length half has to stay
   in `validate`.

**Why**: None of these four were specified, and each one has more than one reasonable way to do it. Writing them
down now means not having to ask again.

**Also fixed while here**: `iterate.py`'s `_physical_arrays` and `checks.py`'s `_differing_fields` used to read all
five physical fields unconditionally, and would crash on `None` whenever one was absent — **making "fields can be
absent" unusable end to end**. Both were fixed together: the divergence criterion now looks only at physical
quantities that actually exist (`iterate`'s documentation states this narrowing of coverage), and the determinism
comparison treats both sides being absent as equal, one side absent and the other present as different — and
reports it as "one side is absent," not as a numeric difference.

**How to apply**: Before adding any code that "reads every physical field," ask first what it does when it hits
`None`.

---

### `output` and `input_use` must be arrays at construction time

**Decision**: When `Plan`'s two required physical fields are passed `None`, this is now an error **at construction
time**, not deferred to `validate`. The error message names which field it was, names both required fields, and
names the three that may be declared absent.

**Why**: Once "fields can be absent" was built into `Plan` this round, the absence mechanism got applied to fields
that aren't allowed to be absent. `Plan(output=None, input_use=None, ...)` would construct successfully
(construction doesn't check required fields, and `run()` never calls `validate`), so `iterate`'s monitor would read
no arrays at all — `all([])` is `True`, so it would **report `diverged=False`**. Before this change, the same call
raised `TypeError`.

**Turning a loud crash into a silent affirmative verdict** is exactly the class of failure this library keeps trying
to prevent. `checks._physical_verdict` has the same shape. Found by adversarial code review on 2026-09-06.

**Order**: this check runs before the pairing guard — a plan missing its required fields should say so, rather than
being told about the pair it is also missing.

**How to apply**: Whenever adding any "can be absent" mechanism to the fixed layer, **also ask about the fields that
must not be allowed to be absent**. Optionality is opened per field, not per type.

---

### `check_determinism` compares three groups: physical columns, `valuation`, and `extra`

**Decision**: `differing_fields` now also compares `Plan.extra`, with entries prefixed `extra.<key>` (the same shape
as `valuation.<key>`). The report order is physical columns → `valuation` → `extra`, sorted by key name within each
bag. The documentation for `check_determinism` and `DeterminismReport` now states which three groups are compared,
and in what order.

**Why**: Until now, `extra` was never compared at all, while `DeterminismReport.identical`'s documentation made the
unqualified claim "repeated runs agreed." `check_determinism` is the library's only executable check for
determinism-with-a-fixed-seed — one of the **two things `spec.md`'s "the following two things are fixed" explicitly
fixes** — and the one prefab that exists writes exactly `effort` and `consumer_demand` into `extra`, which the spec
explicitly says are required to reconstruct a plan's production function and material balance.
**A mechanism whose effort drifts every round would still be certified reproducible by this tool.**

⚠ **Mutation testing is blind to this one**: no code reads `extra` at all, so corrupting it wouldn't turn any test
red — it isn't even eligible to appear in a mutation table. Both times this was caught, it was by asking "what does
this code claim, and what mechanism makes that claim true" — the 2026-09-05 adversarial design review logged it as
T1, and the 2026-09-06 adversarial code review independently hit the same issue again.

**How to apply**: Whenever adding any new container to `Plan`, **also ask whether `check_determinism` compares it**.
A gap in coverage looks like "certified reproducible," which is exactly the direction no test will ever turn red
for.
