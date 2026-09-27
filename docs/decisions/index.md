# Decisions index

| Date | Category | Summary | Link |
|---|---|---|---|
| 2026-08-28 | Scope and purpose | The library is shared research infrastructure for democratic economic planning | [scope-and-purpose.md](scope-and-purpose.md) |
| 2026-08-28 | Scope and purpose | Comparisons stay within democratic planning mechanisms; no market baseline | [scope-and-purpose.md](scope-and-purpose.md) |
| 2026-08-28 | Naming | The project is named cyberstride (provisional, may change before release) | [naming.md](naming.md) |
| 2026-08-28 | Repository conventions | Code is always in English; Chinese is used only in docs | [repository-conventions.md](repository-conventions.md) |
| 2026-08-28 | Scope and purpose | The library is responsible for process; researchers are responsible for results | [scope-and-purpose.md](scope-and-purpose.md) |
| 2026-08-28 | Scope and purpose | v1 value-proposition order: data ingestion first, the mechanism layer last | [scope-and-purpose.md](scope-and-purpose.md) |
| 2026-08-28 | Coordination procedures | Coordination procedures are supplied by researchers; the core cedes control | [coordination-procedures.md](coordination-procedures.md) |
| 2026-08-28 | Coordination procedures | The extension mechanism is an interface, not a set of operators | [coordination-procedures.md](coordination-procedures.md) |
| 2026-08-28 | Coordination procedures | Comparability comes from a shared data model and scorer, not from reading each other's code | [coordination-procedures.md](coordination-procedures.md) |
| 2026-08-28 | License | Adopt MIT | [license.md](license.md) |
| 2026-08-28 | Invariants and metrics | Theory-neutrality is a hard constraint on the base layer | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-08-28 | Invariants and metrics | All four invariants become optional tools | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-08-28 | Invariants and metrics | Theoretical commitments belong to prefabs, not the library | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-08-28 | Invariants and metrics | Residuals are always computed when computable, N/A otherwise, and named neutrally | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-08-28 | Invariants and metrics | No fixed core metrics; comparison benchmarks are declared by the researcher | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-08-28 | Invariants and metrics | Comparability relies on raw output; output splits into three tiers | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-08-28 | Invariants and metrics | SFC splits apart: accounting identities go into the toolbox, behavioral equations belong to the researcher | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-08-28 | Coordination procedures | The interface has only one layer; `iterate` is an opt-in tool | [coordination-procedures.md](coordination-procedures.md) |
| 2026-08-28 | Coordination procedures | Proposal behavior belongs to the researcher; the library provides tools but doesn't hard-code it | [coordination-procedures.md](coordination-procedures.md) |
| 2026-08-28 | Reproducibility | Content hashes are computed only for implementations bundled with the library (partially narrowed) | [reproducibility.md](reproducibility.md) |
| 2026-08-28 | Reproducibility | Convergence-round benchmarks hold only for bundled methods and those using `iterate` (partially narrowed) | [reproducibility.md](reproducibility.md) |
| 2026-08-28 | Reproducibility | Determinism: declare the boundary and provide a self-check tool, not runtime enforcement | [reproducibility.md](reproducibility.md) |
| 2026-08-28 | Extension boundary | The fixed set narrows from four items to two | [extension-boundary.md](extension-boundary.md) |
| 2026-08-28 | Scope and purpose | Money stocks and interaction topology are deferred, but identifier hooks are kept now | [scope-and-purpose.md](scope-and-purpose.md) |
| 2026-08-28 | Technology choices | Rust for the core, with Python bindings as the primary user interface | [technology-choices.md](technology-choices.md) |
| 2026-08-28 | Technology choices | The research platform comes first; academic-output packaging stays in the outer layer | [technology-choices.md](technology-choices.md) |
| 2026-08-28 | Phasing and granularity | v1 is sector-grained, v2 is council-grained; they share a data model but not an execution engine | [phasing-and-granularity.md](phasing-and-granularity.md) |
| 2026-08-28 | Phasing and granularity | v1's ground truth is a set of producing units, not a matrix | [phasing-and-granularity.md](phasing-and-granularity.md) |
| 2026-08-28 | Phasing and granularity | `Technology` is an extensible type from day one; v1 implements only Leontief | [phasing-and-granularity.md](phasing-and-granularity.md) |
| 2026-08-28 | Phasing and granularity | The time dimension goes into the data model from the start | [phasing-and-granularity.md](phasing-and-granularity.md) |
| 2026-08-28 | Extension boundary | The mechanism layer is pluggable; the data model and invariants are fixed | [extension-boundary.md](extension-boundary.md) |
| 2026-08-28 | Extension boundary | The public surface follows three tiers of progressive disclosure | [extension-boundary.md](extension-boundary.md) |
| 2026-08-28 | Extension boundary | The plugin system carries its own assembly-time validation and a run manifest | [extension-boundary.md](extension-boundary.md) |
| 2026-08-28 | Extension boundary | The interface is functional; implementations may mutate in place | [extension-boundary.md](extension-boundary.md) |
| 2026-08-28 | Performance architecture | The whole economy stays resident in memory; one iteration round never touches disk | [performance-architecture.md](performance-architecture.md) |
| 2026-08-28 | Performance architecture | v1's performance goal is throughput across many runs, not the speed of a single run | [performance-architecture.md](performance-architecture.md) |
| 2026-08-28 | Performance architecture | Every optimized kernel keeps a reference implementation and is differentially tested against it | [performance-architecture.md](performance-architecture.md) |
| 2026-08-28 | Reproducibility | A scenario must pin down the coordination procedure's implementation itself, not just its name and parameters | [reproducibility.md](reproducibility.md) |
| 2026-08-28 | Reproducibility | Every coordination procedure gets a set of convergence regression benchmarks | [reproducibility.md](reproducibility.md) |
| 2026-08-28 | Research scope | Close out the exploratory research into the upstream implementation; do not contact the author | [research-scope.md](research-scope.md) |
| 2026-08-30 | Data model | Commodities share one table with a kind tag, not separate tables per kind | [data-model.md](data-model.md) |
| 2026-08-30 | Data model | `Plan` splits into a physical layer and an extension layer; the extension layer keeps a free-form bag | [data-model.md](data-model.md) |
| 2026-08-30 | Data model | `Economy` is mutable across periods | [data-model.md](data-model.md) |
| 2026-08-30 | Data model | Variable-length inputs use a flat array plus an offset table | [data-model.md](data-model.md) |
| 2026-08-30 | Evolution rule | The evolution rule belongs to the researcher; it's a tool parameter, not a core abstraction | [evolution-rule.md](evolution-rule.md) |
| 2026-08-30 | Evolution rule | Cross-period invariants guard against silently accumulating errors; off by default | [evolution-rule.md](evolution-rule.md) |
| 2026-08-30 | Evolution rule | The comparability anchor is the initial economy plus the same evolution rule (partially narrowed) | [evolution-rule.md](evolution-rule.md) |
| 2026-08-30 | Phasing and granularity | v1 implements two technology variants, Leontief and Cobb-Douglas (partially narrowed) | [phasing-and-granularity.md](phasing-and-granularity.md) |
| 2026-08-30 | Phasing and granularity | v1's scale description is corrected to on the order of 10³ to 10⁴ producing units (partially narrowed) | [phasing-and-granularity.md](phasing-and-granularity.md) |
| 2026-08-30 | Reproducibility | Transparency splits into three tiers; prefab is the top tier | [reproducibility.md](reproducibility.md) |
| 2026-09-05 | Data model | Prices do not go into `Economy` (partially narrowed) | [data-model.md](data-model.md) |
| 2026-09-05 | Data model | `Economy` splits into a fixed core and named extension columns, mirroring `Plan` | [data-model.md](data-model.md) |
| 2026-09-05 | Data model | `Plan`'s extension layer predefines an `income` slot | [data-model.md](data-model.md) |
| 2026-09-05 | Data model | Single-output units; endowment use is a derived quantity (partially narrowed) | [data-model.md](data-model.md) |
| 2026-09-05 | Invariants and metrics | Zero-degree homogeneity of prices is a property test, not a residual (partially narrowed) | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-09-05 | Invariants and metrics | The reference solution is a tool parameterized by an objective | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-09-05 | Phasing and granularity | Stage order adjusted: the reference solution moves up to Stage 1.5, WIOD field mapping moves earlier | [phasing-and-granularity.md](phasing-and-granularity.md) |
| 2026-09-05 | Phasing and granularity | v1's core abstractions land: two data types, two functions, one toolbox | [phasing-and-granularity.md](phasing-and-granularity.md) |
| 2026-09-05 | Technology choices | v1's Rust surface is deliberately kept small | [technology-choices.md](technology-choices.md) |
| 2026-09-05 | Technology choices | Repository layout and the Python-side data classes | [technology-choices.md](technology-choices.md) |
| 2026-09-05 | Reproducibility | The seed is a 64-bit unsigned integer; derivation uses SplitMix64 | [reproducibility.md](reproducibility.md) |
| 2026-09-05 | Data model | `Plan` gains an `extra` bag; dep1ex's technology is Cobb-Douglas with an effort factor (partially narrowed) | [data-model.md](data-model.md) |
| 2026-09-05 | Data model | The dep1ex loader derives `n_goods` only from input codes, and checks that segment codes stay in bounds | [data-model.md](data-model.md) |
| 2026-09-05 | Reference solution | The objective sets both weights and allocation; both are theoretical commitments | [reference-solution.md](reference-solution.md) |
| 2026-09-05 | Reference solution | Shadow prices come from the dual variables, unclamped | [reference-solution.md](reference-solution.md) |
| 2026-09-05 | Reference solution | `linearize` is a tool that carries a theoretical commitment; idle units get all-zero coefficients | [reference-solution.md](reference-solution.md) |
| 2026-09-05 | Reference solution | The library checks an objective's declared well-formedness, independent of the optional invariants | [reference-solution.md](reference-solution.md) |
| 2026-09-05 | Reference solution | scipy is a runtime dependency | [reference-solution.md](reference-solution.md) |
| 2026-09-05 | Reference solution | A first check of the abstraction criterion (partially checked) | [reference-solution.md](reference-solution.md) |
| 2026-08-28 | Rejected | Implement a market baseline in v1 as a control group | [rejected/scope-and-purpose.md](rejected/scope-and-purpose.md) |
| 2026-08-30 | Rejected | Split commodities into separate tables per kind | [rejected/data-model.md](rejected/data-model.md) |
| 2026-08-30 | Rejected | Use a closed enum for `Plan`'s valuation layer | [rejected/data-model.md](rejected/data-model.md) |
| 2026-08-30 | Rejected | Keep `Economy` immutable throughout | [rejected/data-model.md](rejected/data-model.md) |
| 2026-08-28 | Rejected | Five groups of rejected name candidates (cybersyn, checo, synco and opsroom, parecon, Greek/Latin word families) | [rejected/naming.md](rejected/naming.md) |
| 2026-08-28 | Rejected | Assemble coordination procedures in v1 from a set of preset operators (deferred, not permanently rejected) | [rejected/coordination-procedures.md](rejected/coordination-procedures.md) |
| 2026-08-28 | Rejected | Use the Coopyleft cooperative license | [rejected/license.md](rejected/license.md) |
| 2026-08-28 | Rejected | Have the library mandate a fixed set of core metrics | [rejected/invariants-and-metrics.md](rejected/invariants-and-metrics.md) |
| 2026-08-28 | Rejected | Require `State` implementations to provide a method returning recordable quantities | [rejected/invariants-and-metrics.md](rejected/invariants-and-metrics.md) |
| 2026-08-28 | Rejected | Enforce determinism at runtime | [rejected/invariants-and-metrics.md](rejected/invariants-and-metrics.md) |
| 2026-08-28 | Rejected | Compute content hashes for coordination procedures supplied by researchers | [rejected/invariants-and-metrics.md](rejected/invariants-and-metrics.md) |
| 2026-08-28 | Rejected | Draw the interface as two layers, forcing a fine-grained interface on iterative mechanisms | [rejected/coordination-procedures.md](rejected/coordination-procedures.md) |
| 2026-08-28 | Rejected | Pure Rust, with no Python interface | [rejected/technology-choices.md](rejected/technology-choices.md) |
| 2026-08-28 | Rejected | Pure Python, with no Rust | [rejected/technology-choices.md](rejected/technology-choices.md) |
| 2026-08-28 | Rejected | Use a database as the computational substrate | [rejected/performance-architecture.md](rejected/performance-architecture.md) |
| 2026-08-28 | Rejected | Install a JVM and Leiningen to run the upstream code as-is | [rejected/research-methods.md](rejected/research-methods.md) |
| 2026-09-05 | Rejected | Switch to GPL, with explicit credit to three comparable implementations' contributions | [rejected/license.md](rejected/license.md) |
| 2026-09-05 | Performance architecture | The cost of divergence detection is eliminated by the prefab, without weakening `iterate`'s check semantics | [performance-architecture.md](performance-architecture.md) |
| 2026-09-05 | Data model | The utility-exponent column can point at a commodity of any kind; the split criterion is "is it a private good" | [data-model.md](data-model.md) |
| 2026-09-05 | Data model | `public_demand` generalizes to `consumer_demand`, covering all three kinds of columns | [data-model.md](data-model.md) |
| 2026-09-05 | Scope and purpose | Theory-neutral means transparent, not blank | [scope-and-purpose.md](scope-and-purpose.md) |
| 2026-09-05 | Data model | Two conventional keys in `Plan.extra` get exported constants; `Economy.extra`'s do not | [data-model.md](data-model.md) |
| 2026-09-05 | Data model | `unit_group` is an arbitrary grouping label; the library does not validate its range | [data-model.md](data-model.md) |
| 2026-09-05 | Coordination procedures | Arrays handed to researcher code are read-only; `RunSummary` distinguishes divergence from running out of rounds | [coordination-procedures.md](coordination-procedures.md) |
| 2026-09-05 | Reference solution | The objective's declared-property check is applied at the reference-solution layer, independent of the concrete objective class | [reference-solution.md](reference-solution.md) |
| 2026-09-05 | Comparison and presentation | The library doesn't score; it only presents differences; preset comparison items plus researcher configuration | [comparison-and-presentation.md](comparison-and-presentation.md) |
| 2026-09-05 | Comparison and presentation | "Efficiency" has no fixed definition; wall-clock time and round counts are presented as-is | [comparison-and-presentation.md](comparison-and-presentation.md) |
| 2026-09-05 | Comparison and presentation | Difference presentation is a thin component, not a pure file format | [comparison-and-presentation.md](comparison-and-presentation.md) |
| 2026-09-05 | Data model | `Plan`'s fixed fields become optional per field, starting with `consumption` and `provision` | [data-model.md](data-model.md) |
| 2026-09-05 | Data model | Stated plan and allocated plan: one field plus subclass specialization | [data-model.md](data-model.md) |
| 2026-09-05 | Data model | Commodity kinds open up, but only together with declarable kind properties | [data-model.md](data-model.md) |
| 2026-09-05 | Data model | Producing units may have multiple outputs (joint products) | [data-model.md](data-model.md) |
| 2026-09-05 | Reproducibility | The run configuration document is an input, kept separate from the run manifest | [reproducibility.md](reproducibility.md) |
| 2026-09-05 | Reproducibility | The run configuration document's versioning rule: a missing key uses its default, an unknown key errors, a removed key errors explicitly | [reproducibility.md](reproducibility.md) |
| 2026-09-05 | Reproducibility | `Economy` gets a byte-for-byte content hash, plus a separately stored per-column hash | [reproducibility.md](reproducibility.md) |
| 2026-09-05 | Scope and purpose | Design follows need, not the phase schedule | [scope-and-purpose.md](scope-and-purpose.md) |
| 2026-09-05 | License | MIT is kept after re-evaluation; three comparable GPL implementations are read but not copied from | [license.md](license.md) |
| 2026-09-05 | Data model | Joint products move up in delivery order, evaluated in the same round as the `Plan` layering work | [data-model.md](data-model.md) |
| 2026-09-05 | Scope and purpose | The purpose is to help the field develop smoothly; success and failure criteria are derived from it, correcting the scheduling of interoperability and the outer wrapper | [scope-and-purpose.md](scope-and-purpose.md) |
| 2026-09-05 | Coordination procedures | Arrays handed to researcher code become library-owned copies; `diverged` gains a third state; three gaps in the reference solution's declared-property checks are closed | [coordination-procedures.md](coordination-procedures.md) |
| 2026-09-05 | Data model | `Plan.valuation` doesn't validate dtype or length; folded into the `Plan`-layering work package | [data-model.md](data-model.md) |
| 2026-09-06 | Reproducibility | The run configuration document's concrete shape: JSON, a standalone function, per-column hashing | [reproducibility.md](reproducibility.md) |
| 2026-09-06 | Data model | `Plan` declares absence with `None`; a missing required field still errors at construction | [data-model.md](data-model.md) |
| 2026-09-06 | Data model | `valuation` validates length per key: conventional keys use their registered row count, others pick one of three | [data-model.md](data-model.md) |
| 2026-09-06 | Data model | Four implementation details of the `Plan` layering settled, along with fixing `iterate` and `checks` crashing on absence | [data-model.md](data-model.md) |
| 2026-09-06 | Reproducibility | Researcher-written coordination procedures also get their parameters recorded; six implementation details of the run configuration document settled | [reproducibility.md](reproducibility.md) |
| 2026-09-06 | Reproducibility | numpy scalars are recorded by value; a summary comparison returns a report instead of raising | [reproducibility.md](reproducibility.md) |
| 2026-09-06 | Reproducibility | The summary algorithm upgrades to v2: rejects dtypes that can't be hashed faithfully, normalizes `period` and line endings | [reproducibility.md](reproducibility.md) |
| 2026-09-06 | Reproducibility | How parameter values are recorded (the single source of truth), merging rules that were scattered across three decisions | [reproducibility.md](reproducibility.md) |
| 2026-09-06 | Reproducibility | Column summaries reject text dtypes, stricter than the argument for them strictly required | [reproducibility.md](reproducibility.md) |
| 2026-09-06 | Data model | `output` and `input_use` must be arrays at construction time | [data-model.md](data-model.md) |
| 2026-09-06 | Data model | `check_determinism` compares three groups: physical columns, `valuation`, and `extra` | [data-model.md](data-model.md) |
| 2026-09-26 | Repository conventions | Upstream literature's original text isn't distributed with the repo; only its source and download URL are recorded | [repository-conventions.md](repository-conventions.md) |
| 2026-09-26 | Naming | The project is renamed demplan, superseding cyberstride | [naming.md](naming.md) |
| 2026-09-26 | Rejected | Other name candidates: neurath, anarres, algedonic, tatonnement, kantorovich, SocietyPlanning, PlanningSociety, eco_demplan, keeping cyberstride | [rejected/naming.md](rejected/naming.md) |
| 2026-09-26 | Repository conventions | Public documents are in English; the Chinese originals are kept in a private repository, paired and checked | [repository-conventions.md](repository-conventions.md) |
| 2026-09-26 | Repository conventions | Public commit messages use English Conventional Commits | [repository-conventions.md](repository-conventions.md) |
| 2026-09-26 | Publication | Publish early; the public repository and a DOI establish the date | [publication.md](publication.md) |
| 2026-09-26 | Publication | The README opens with the purpose and shows the reproduction comparison and the limitations | [publication.md](publication.md) |
| 2026-09-26 | Publication | The wiki has three guides: researchers, contributors, quality assurance | [publication.md](publication.md) |
| 2026-09-26 | Publication | Authorship: Enrique Mark; license: MIT | [publication.md](publication.md) |
| 2026-09-26 | Publication | Every citation needs evidence from the original source | [publication.md](publication.md) |
| 2026-09-26 | Contributing and AI | AI assistance is accepted, but a person is accountable for every change and shows the decision process | [contributing-and-ai.md](contributing-and-ai.md) |
| 2026-09-26 | Quality assurance | Publish the quality assurance practices, and commit to formal proof where it is needed | [quality-assurance.md](quality-assurance.md) |
| 2026-09-26 | Publication | Releases go through GitHub Actions: prebuilt wheels and trusted publishing | [publication.md](publication.md) |
| 2026-09-26 | Contributing and AI | Two manuals for agents, project hooks, repository checks and CI; AI-generated code without decision context is not accepted | [contributing-and-ai.md](contributing-and-ai.md) |
| 2026-09-26 | Evolution rule | Multi-period interface: the evolution rule receives a seed, a function slot builds the next period's coordination procedure, every period's economy is kept | [evolution-rule.md](evolution-rule.md) |
| 2026-09-26 | Evolution rule | Multi-period seed layout: one prefix-stable sequence, even and odd positions for the coordination procedure and the evolution rule | [evolution-rule.md](evolution-rule.md) |
| 2026-09-26 | Evolution rule | Soft check on the period number: warn, do not raise | [evolution-rule.md](evolution-rule.md) |
| 2026-09-26 | Evolution rule | Cross-period residuals computed by default, constraints declared by the evolution rule, done in Stage 2 | [evolution-rule.md](evolution-rule.md) |
| 2026-09-26 | Coordination procedures | The Hahnel prefab follows the program that produced the book's tables, not the book's text | [coordination-procedures.md](coordination-procedures.md) |
| 2026-09-26 | Coordination procedures | The price-update rule slot supports stateful rules, with state passed in and out explicitly | [coordination-procedures.md](coordination-procedures.md) |
| 2026-09-26 | Rejected | Build in the book's literal rule and the `pequod-plus` rule as comparable variants | [rejected/coordination-procedures.md](rejected/coordination-procedures.md) |
| 2026-09-26 | Research scope | Full reproduction against Hahnel (2021), chapter 9; the criterion is trends and mechanism insights | [research-scope.md](research-scope.md) |
| 2026-09-26 | Reproducibility | The multi-period run configuration document extends the single-period one; without multi-period parameters it is byte-for-byte the same as now | [reproducibility.md](reproducibility.md) |
| 2026-09-27 | Invariants and metrics | The budget residual is computed only when prices, income, and all spending are supplied by the mechanism (partially supersedes the `income` fallback) | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-09-27 | Invariants and metrics | Residuals are a separate function, and `run` calls it by default | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-09-27 | Invariants and metrics | Homogeneity and independence from the starting point are two checks; nominal quantities are declared by the researcher (partially supersedes 2026-09-05) | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-09-27 | Data model | Commodity kinds, technology kinds, and joint products are opened up together; the five kind tags move into the Hahnel package; this comes before Stage 2 | [data-model.md](data-model.md) |
| 2026-09-27 | Data model | The library defines no commodity-attribute vocabulary; declarations a tool needs are passed by the caller at call time | [data-model.md](data-model.md) |
| 2026-09-27 | Data model | Built-in models provide only small, descriptively named translation functions, with no bundling and no one-call comparison | [data-model.md](data-model.md) |
| 2026-09-27 | Data model | Remove the fixed columns `commodity_kind`, `unit_group`, and `consumer_group`; labels move to the `extra` bags (partially supersedes 2026-09-05) | [data-model.md](data-model.md) |
| 2026-09-27 | Data model | `provision` becomes "the quantity in shared, non-rival use" and records how much is used | [data-model.md](data-model.md) |
| 2026-09-27 | Data model | `technology_kind` becomes a text label, and researchers can add technology forms | [data-model.md](data-model.md) |
| 2026-09-27 | Data model | The technology-form interface asks one question: the production function | [data-model.md](data-model.md) |
| 2026-09-27 | Data model | Joint products: record a quantity per output; output proportions come from a pluggable implementation; the library provides fixed proportions but does not attach them by default | [data-model.md](data-model.md) |
| 2026-09-27 | Data model | The core technology interface is "can these inputs produce this set of outputs," plus an assembly helper (partially supersedes the same day's production-function entry) | [data-model.md](data-model.md) |
| 2026-09-27 | Data model | "How much endowment is used" depends on the caller declaring which commodities count as resources; without a declaration the cross-period resource residual is N/A | [data-model.md](data-model.md) |
| 2026-09-28 | Invariants and metrics | The indicator tools are "input use on declared commodities" and "field-by-field comparison of two plans" | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-09-28 | Invariants and metrics | "Property-based test coverage" means property tests of the library's own residual tools; no random-economy generator for researchers | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-09-28 | Invariants and metrics | The non-negativity residual takes bads from the caller as `bads=`; prices of bads are not checked for sign | [invariants-and-metrics.md](invariants-and-metrics.md) |
| 2026-09-28 | Data model | WIOD loader: one economy per year, the unit of labour chosen by the caller, each of five final-demand categories a consumer unit, plus an observed plan | [data-model.md](data-model.md) |
| 2026-09-28 | Publication | Go public after opening the kinds, Stage 2 and the WIOD loader (narrows 2026-09-26 "publish early") | [publication.md](publication.md) |
| 2026-09-28 | Publication | The wiki follows documentation-site conventions, with a from-zero tutorial and a full configuration reference | [publication.md](publication.md) |
| 2026-09-28 | Data model | The WIOD loader creates no labour commodity by default; labour data comes from the SEA (partially supersedes point 2 of the same day's WIOD entry) | [data-model.md](data-model.md) |
