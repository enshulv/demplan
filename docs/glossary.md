# Glossary

This glossary defines terms specific to this project. Where a term conflicts with a general style guide, this document takes precedence.

## 1. Project-specific terms

**Code always uses English identifiers** (see [decisions/repository-conventions.md](decisions/repository-conventions.md)). The table below gives the term as used in prose; the parenthetical, where one exists, is the identifier used in code.

| Term | Definition |
|---|---|
| coordination procedure (`Procedure`) | The method that, given all proposals, produces a new signal or a final plan. Upstream's price-update rule `w = v(1.05 − 0.5ᵛ)` is one implementation of it. Supplied by the researcher, see [decisions/coordination-procedures.md](decisions/coordination-procedures.md) |
| cold start | A planning process where every indicative price starts from the same initial value. Called Year One in the upstream literature |
| warm start | Replanning that carries over the previous period's converged prices and perturbs only the exponents. Called Year Two in the upstream literature |
| indicative price | A social-cost estimate published by the Iteration Facilitation Board in participatory planning; not a market price |
| Iteration Facilitation Board | IFB, the procedure that publishes and adjusts indicative prices |
| endowment | The exogenous supply of natural resources and labor. Upstream's data files don't include this parameter, but the paper's text gives a value (1000), confirmed by reverse-engineering, see [research/reproduction.md](research/reproduction.md) |
| participant | The economic agent that submits proposals. In v1, sectors; in v2, worker councils and consumer councils |
| mechanism layer | The pluggable part: coordination procedures, behavior cores, generators, constraint families, metrics. Opposite the fixed data model and invariants |
| reference solution | The centralized optimal solution computed by an optimization solver given the researcher's declared objective, used as the scoring benchmark for decentralized procedures. The objective goes into the manifest, see [decisions/invariants-and-metrics.md](decisions/invariants-and-metrics.md) 2026-09-05 |
| objective (`Objective`) | A parameter of the reference solution: it gives both the weights on final consumption and the rule allocating the aggregate to consumer units. Both are theoretical commitments, see [decisions/reference-solution.md](decisions/reference-solution.md) |
| linearization (`linearize`) | Treats the input ratios a plan chose as a fixed technology, yielding a Leontief economy. A tool that carries a theoretical commitment |
| producing unit (`unit`) | The agent in `Economy` that produces a commodity. dep1ex's worker councils, an input-output table's sectors |
| consumer unit (`consumer`) | The agent in `Economy` that receives private goods. dep1ex's consumer councils |
| extra bag (`extra`) | The named-array bag each of `Economy`'s three tables carries, holding theory-laden data such as behavioral parameters. Key names are conventionalized by the library and interpreted by prefabs. Same pattern as `Plan`'s `valuation` |
| prefab | A configuration (coordination procedure, parameters, enabled constraint set) preassembled to match a paper. Named with its source and year, e.g. `hahnel_2020_slides`. **Theoretical commitments belong to the prefab, not the library** |
| invariant toolbox | A collection of optional constraints. The researcher enables them as needed; adding them one at a time makes the experiment progressively stricter. Not a hard gate |
| residual | The degree to which a constraint is violated; the library always computes it and writes it into the output. **Call it a "residual," not a "violation"** — the same number is the object of study for someone running a credit-creation experiment, not a defect |
| comparison benchmark | The quantity the researcher declares when making a comparison. The library doesn't prescribe it; the declaration goes into the run manifest |
| SFC | Stock-flow consistent. The accounting part enters the toolbox as an optional conservation law; the behavioral equations belong to the researcher |
| iteration | **Refers specifically to rounds within a single `solve` call** (convergence round count, cold start, warm start). Advancing across periods is not called iteration — it's called evolution |
| evolution rule (`advance`) | What the economy becomes after this period's plan is carried out: capital accumulation, technological progress, resource depletion, population change. Belongs to the researcher; it's a parameter of the multi-period driver tool, not a core abstraction. **Not called an "iteration rule,"** to avoid colliding with the term above |
| physical layer / extension layer | `Plan`'s two layers. The physical layer is the allocation (output, input use, consumption, endowment use), theory-neutral; the extension layer is valuation quantities (prices, labor values, shadow prices), mechanism-specific |
| entitlement (`entitlement`) | dep1ex's `income`. An exogenously given **flow**, not an accumulable money stock. v1 has no money stock; don't conflate the two |
| Cybersyn | Chile's 1971-73 economic control project (Spanish original name Proyecto Synco), the only attempt at democratic economic planning ever to reach production operation. It comprised four components: CHECO, Cyberstride, Cybernet, and Opsroom |
| Cyberstride | Cybersyn's statistical forecasting and early-warning component. The library's former name came from it; the library was renamed `demplan` on 2026-09-26, see [decisions/naming.md](decisions/naming.md) |
| CHECO | CHilean ECOnomy, Cybersyn's economic simulation component. Functionally analogous to this library, but not the source of its name |

Inclusion criterion: these terms either already appear repeatedly in the design documents, or have no consistent usage in public sources.

## 2. Cases where this project overrides the base word list

| Term | Ruling | Reason |
|---|---|---|
| cold start / warm start | Keep | Standard terms in numerical optimization (cold start / warm start), referring to whether a previous solution is reused as the starting point. Not an invented metaphor |
| endowment | Keep | Standard economics term (endowment) |
| shadow price | Keep | Standard linear-programming term (shadow price) |

## 3. Candidates for promotion

None currently.
