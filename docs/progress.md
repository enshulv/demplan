# Progress

## Design

| Item | Status | Notes |
|---|---|---|
| Core abstraction split | ✅ | Four layers: `Economy` / `Participant` / `Procedure` / `Evaluator`, see spec.md |
| Language stack | ✅ | Rust core + Python as the first-class interface + TS/wasm frontend |
| Phasing and granularity | ✅ | v1 at sector granularity, v2 at council granularity; shared data model, not a shared execution engine |
| Extension boundary | ✅ | The mechanism layer is pluggable; the data model and invariants are fixed. Three tiers of progressive disclosure to the outside |
| Performance architecture | ✅ | The whole economy stays resident in memory, columnar f64, no disk access within a round |
| Scope and purpose | ✅ | Shared research infrastructure for democratic economic planning: comparison + computational optimization + a low-barrier wrapper |
| Comparison boundary | ✅ | Compares only among democratic planning mechanisms, with the reference solution as the benchmark. No market baseline; `Economy` carries no market-**clearing**-specific fields. Money stock isn't excluded by this — it's only deferred, see [decisions/scope-and-purpose.md](decisions/scope-and-purpose.md) |
| Project name | ✅ | Renamed `demplan` (democratic planning) on 2026-09-26. The former name `cyberstride` was taken from Project Cybersyn's statistical early-warning component; see [decisions/naming.md](decisions/naming.md) |
| `Economy` field-level design | ✅ | Nailed down to column names 2026-09-05, see [spec.md](spec.md#data-model) |
| Pre-implementation spec revision | ✅ | 2026-09-05: moved price out of `Economy`, changed homogeneity to a property test, added an `income` slot, defined the reference solution, scoped the Rust surface |
| Scenario file format | ⏸ | Deferred to Stage 4, when it becomes clear what the manifest needs to hold |

## Research

| Item | Status | Notes |
|---|---|---|
| Upstream code review | ✅ | See [research/upstream-code-issues.md](research/upstream-code-issues.md) |
| Measured performance comparison | ✅ | 99 ms per round with numpy versus roughly 4 hours per experiment upstream |
| Literature archive | ✅ | The 2023 JIE paper and the 2020 conference slides. The repository records only provenance and download URLs; the source texts are not distributed with the repository, see [research/literature/README.md](research/literature/README.md) |
| Obtaining published data | ✅ | Downloaded 5 of 40 groups (dep1ex01 through 05), enough to work with |
| Reverse-engineering the endowment parameter | ✅ | It's exactly the 1000 the paper states in its text. The sensitivity curve bottoms out between 700 and 1000 |
| Locating the price-update rule | ✅ | The 2020 slides' formula reproduces; the 2023 paper's pseudocode does not converge. The current code uses the latter |
| Reproducing cold-start round counts | ✅ | Mean over 5 groups: 5% threshold 13.40 (paper reports 11.85), 3% threshold 22.80 (paper reports 19.2) |
| Reproducing warm-start round counts | 🟡 | This run: 4.00, paper reports 6.5. Variance across three seeds is zero, so the perturbation magnitude may be too small. **Not pursuing further** |
| Running the remaining 35 groups | ❌ | Low marginal benefit, see [decisions/research-scope.md](decisions/research-scope.md) |
| Reconciling the GDP growth figure | ❌ | Doesn't affect any design decision, see [decisions/research-scope.md](decisions/research-scope.md) |
| Contacting the upstream authors | ❌ | See [decisions/research-scope.md](decisions/research-scope.md) |
| Cross-validating against pequod-cljs | ❌ | Poor cost-to-benefit ratio, see [decisions/rejected/research-methods.md](decisions/rejected/research-methods.md) |

**This line closed on 2026-08-28.** The scripts and data under `research/` are kept as a ready-made regression target for v1.

## v1 implementation

| Item | Status | Notes |
|---|---|---|
| Stage 0 | ✅ | Five blocking issues found by adversarial review are fixed and reverified (phantom commodities, segment out-of-bounds, false convergence via NaN, the effort factor, public-good demand). Rust: `Economy`, `validate`, the dep1ex loader (0.70 seconds versus 4.46 seconds for numpy); Python: `Economy`, `Plan`, `iterate`, `run`, `split_seed`, `check_determinism`, technical tools |
| Stage 1.5 | ✅ | Incremental adversarial review found seven blocking issues, now fixed (negative lower bound, a partially declared objective, two coverage gaps, an incorrect test location in the README, two other README issues). Linear-programming reference solution, two objectives, `linearize`; the reference solution takes 4.43 seconds on dep1ex01. The abstraction test is partially exercised, see [decisions/reference-solution.md](decisions/reference-solution.md) |
| Stage 1 | ✅ | Same work package as Stage 0, went through one round of adversarial review and one round of fixes. Prefab `hahnel_2020_slides` reproduces the reference round counts exactly on dep1ex01 through 05 (14, 13, 13, 14, 13), 3% mean 22.80; the Rust loader and the numpy adapter agree bit for bit |
| Consumer demand split | ✅ | 2026-09-05: `plan_of` no longer copies the consumption block; the default configuration is 13% faster, and divergence-detection overhead drops from 31-38% to 8-14%. Bit-for-bit unchanged on dep1ex01 through 05. See [decisions/performance-architecture.md](decisions/performance-architecture.md) |
| The third-kind recording gap | ✅ | 2026-09-05: `public_demand` generalized to `consumer_demand`, recording all three kinds of columns. Bit-for-bit identical to the old key on public goods; round counts unchanged. See [decisions/data-model.md](decisions/data-model.md) |
| Adversarial review (consumer demand split) | ✅ | 2026-09-05: one blocking issue (no coverage of the pairing between `consumption_commodity` and the consumption block's column order) fixed, with a replay confirming the kill; all four non-blocking issues handled. 29 real mutants, 28 killed. See [reviews/evidence/review-consumer-demand-split-2026-09-05.md](reviews/evidence/review-consumer-demand-split-2026-09-05.md) |
| Adversarial review, code and design tracks | 🟡 | 2026-09-05: the code review's three blocking issues are **fixed and reverified** (see the row below); the design review's four categories, eighteen issues in total, are **unaddressed**. Reports are in [reviews/evidence/](reviews/evidence/) |
| Fixes for the code review's three blocking issues | ✅ | 2026-09-05: B1 the `NaN` lower bound, B2 two escapes of read-only input arguments (changed to library-owned copies), B3 a third `diverged` state, plus W1 (a maximization weight not checked) and W2 (`minimize_kind` value not validated), both found by both reviews. 553 passed (516 + 37 new), all 18 mutants killed, 4 spot-replayed during the primary check confirming the same kill, golden output bit-for-bit unchanged. See [decisions/coordination-procedures.md](decisions/coordination-procedures.md) |
| Optional `Plan` layering and the configuration document | ✅ | 2026-09-06: implemented as two parallel work packages. 834 passed (baseline 553 + 281 new), golden output bit-for-bit unchanged on both. **Joint products are now evaluated in the same period**, no longer scheduled last. See [decisions/data-model.md](decisions/data-model.md) |
| ├ Optional `Plan` fields | ✅ | 2026-09-06: passing `None` for the three physical fields declares absence; accessors raise `PlanFieldAbsent` instead of returning zero. `valuation` is validated by key tier, rejected rather than converted. `StatedPlan` / `AllocatedPlan` separate the stated plan from the allocated plan. Also fixed absence-related crashes in `iterate` and `checks` |
| ├ Run configuration document | ✅ | 2026-09-06: `run_configuration` is independent of `run`; `sha256-columns-v1` per-column content hashing, plus `compare_economy_digests` returning a report; versioning rules and a retired-key registry; both researcher-supplied and library-shipped sides record parameters |
| └ Seam between the two work packages | ✅ | 2026-09-06: `tests/test_integration_configuration_seam.py`, 14 tests. Covers what neither work package saw on its own — feeding a real `Plan` into `run_configuration`, container conventions (in-memory tuple vs. JSON list), and a real prefab's parameters and `source_digest` |
| Spec gaps found during implementation | ✅ | 2026-09-06: implementation found 12 issues with the specification, and **for 5 of them the specification was wrong** (a one-size-fits-all rule for `valuation`, `labor_value` missing from the registry, the researcher-supplied block not recording parameters, numpy scalars losing their value, and comparison that should return a report instead of raising). All resolutions are recorded, see [decisions/reproducibility.md](decisions/reproducibility.md) and [decisions/data-model.md](decisions/data-model.md) 2026-09-06 |
| Adversarial review (two work packages in parallel) | ✅ | 2026-09-06: one work package for `Plan` layering, one for the configuration document and the seam, each reviewed as its own tree. Nine blocking issues and twenty-six non-blocking issues in total. **None of the nine blocking issues were caught by the implementation's mutation tests** — all of them came from asking, again and again, what a piece of code claimed and what mechanism actually backed that claim. Reports are in [reviews/evidence/](reviews/evidence/) |
| Fixes for adversarial review's blocking issues (two work packages in parallel) | ✅ | 2026-09-06: **965 passed** (baseline 553 + 412). All seventeen mutants that survived adversarial review are now killed, golden output bit-for-bit unchanged. The primary check manually replayed R14 (swapping the column digest for sha3_256) and confirmed it now kills 9 |
| Digest algorithm bumped to v2 | ✅ | 2026-09-06: before this, nothing exercised the preimage bytes of `sha256-columns-v1` — five mutants (changing the separator, the field order, the encoding, the hash function) all passed while `algorithm` kept claiming v1. There is now a test that hand-assembles the preimage from the spec text; its failure message says directly, "either you broke it, or you owe it a version bump" |
| Four wrap-up items for the work package | ✅ | 2026-09-05: exported constants for `Plan.extra`'s two keys, `RunSummary.diverged`, moving the objective-declaration check to the reference-solution layer, and read-only input arguments for `PriceRule`. 516 passed, bit-for-bit unchanged |
| Survey of related implementations | ✅ | 2026-09-05: cloned `socialist_planning`, `EPOS`, and `Economic-Planning` into `upstream/`; formalization and license boundaries are in [research/related-implementations.md](research/related-implementations.md). Three consequences: opening up the enum now has external empirical demand behind it, joint products moved earlier in the schedule, and closed-economy is a fifth, previously unlisted assumption |
| First cross-mechanism comparison on dep1ex | 🟡 | 2026-09-05: iterative price adjustment spends 96,415 labor over 14 rounds; the reference solution's optimum is 53,348; A/B = 1.81. **This number cannot be cited directly** — the reference solution can't run Cobb-Douglas, so it has to pass through `linearize`, and linearization silently swaps the 0.875 scale elasticity for 1, so 1.81 is an upper bound. It holds only once `ReferenceResult` carries an assumption list |
| Interop gap | 🟡 | Logged 2026-09-05: `io.py` has only `load_dep1ex`; it can't read any existing implementation's data, and can't export anything another tool can read. By [decisions/scope-and-purpose.md](decisions/scope-and-purpose.md)'s failure test, this is a state of "one more data model, with no less duplicated work." |
| Rename to `demplan` | ✅ | 2026-09-26: package, crates, extension module and environment variables renamed. The collected test ids are identical before and after, 965 passed / cargo 63 passed, and the dep1ex01–05 fingerprints are bit-identical. See [decisions/naming.md](decisions/naming.md) |
| Preparing publication | 🟡 | 2026-09-26: README rewritten (purpose, reproduction comparison, limitations, references), `CONTRIBUTING.md`, pull request template, `CITATION.cff`, four wiki pages; documentation moved to English in public with the Chinese originals kept privately. To do: citation check, new repository, push, Zenodo DOI. See [decisions/publication.md](decisions/publication.md) |
| Low-barrier-wrapper gap | 🟡 | Logged 2026-09-05: one of the charter's three parts, absent from both Stage 0-6 and v1's value-priority ordering |

The order follows [decisions/scope-and-purpose.md](decisions/scope-and-purpose.md)'s value ranking: how much duplicated work is eliminated times how many people it reaches.

| Stage | Content | Acceptance |
|---|---|---|
| 0 | Implement `Economy` and `Plan` | Shape already decided (see [decisions/data-model.md](decisions/data-model.md)); implement as specified |
| 1 | End-to-end run on dep1ex: `Economy` + prefab `hahnel_2020_slides` + minimal accounting | dep1ex01 through 05 cold start, 5% threshold, 13, 13, 13, 14, 14 rounds respectively, matching `confirm.py` group by group |
| 1.5 | Minimal linear-programming reference solution (Leontief, scipy) | First test of the abstraction: the reference solution and the prefab run on the same `Economy` |
| 2 | Invariant toolbox and metric tools. **Do the WIOD field mapping first**, listing only what `Economy` is missing | Three residuals, the homogeneity property test, the cross-period batch, property-test coverage |
| 3 | Connect a real input-output table (EXIOBASE or WIOD), with labor and emissions extensions | One command from raw data to a runnable `Economy` |
| 4 | Run manifest and output contract | Long-format Parquet, every number traceable |
| 5 | Second and third coordination procedures (Cockshott labor time, linear-programming reference solution) | spec.md's abstraction test holds. Use cases have grown from three to five; the last two (OLIN-EP, I-EPOS) have public code |
| 6 | Parameter sweeps | Scenario-level parallelism |
| Unscheduled | **Interop**: read external implementations' data formats, export `Plan` into a form others can verify | At least one external format can load into `Economy`, at least one export can be read back by an external tool |
| Unscheduled | **Low-barrier wrapper** (the charter's third part) | A researcher who doesn't write Python can run an experiment to completion |

The last two rows were added 2026-09-05, see [decisions/scope-and-purpose.md](decisions/scope-and-purpose.md), "this library's purpose is to help the field of democratic economic planning develop smoothly." The order follows "which one gets the next person in the field working faster," not the row numbers.

**Next work package: the WIOD loader** (decided by the maintainer on 2026-09-26, ahead of the Stage 2 invariant toolbox). Reason: walking through the library as a researcher, the largest barrier is that dep1ex is the only data source, so a researcher who wants a real input-output table cannot start at all. The installation barrier is removed by the prebuilt wheels of v0.1.0; only a loader removes the data barrier. The starting point is the list of gaps in [research/wiod-field-mapping.md](research/wiod-field-mapping.md).

Stage 1 chose dep1ex over toy data or going straight to EXIOBASE because it satisfies four conditions at once:
it's real, published data; it's small and already parsed (`research/bench/repro.py`); **it has a known correct answer**;
and its field shapes are complete (intermediate goods, natural resources, labor, and private and public consumption — five price kinds, see `repro.py:118`).
It's the cheapest use case for testing `Economy`'s field design, at a point where changing fields is still cheap.

Technical constraint: v1's `Technology` implements **Leontief and Cobb-Douglas variants** —
dep1ex uses the latter, see [decisions/phasing-and-granularity.md](decisions/phasing-and-granularity.md) 2026-08-30.
v1 has no operator layer; the researcher implements the coordination procedure in arbitrary Python, see [decisions/coordination-procedures.md](decisions/coordination-procedures.md).

Stage 1's Cobb-Douglas closed-form solution needs differential testing per [decisions/performance-architecture.md](decisions/performance-architecture.md);
the reference implementation is at `research/bench/repro.py:149-152` — this is the batch of expressions where upstream's
transcription error (`log(p3)` copied as `log(p2)`) lives.

⚠ **The price-update rule's reference implementation is a different file**: `research/bench/endowment.py`'s
`delta_slides_capv` (the 2020 slides version), driven by `confirm.py`.
What `repro.py` inlines is the 2023 paper version, which doesn't converge in 250 rounds; implementing from it won't produce 13 to 14 rounds.

## Design freedoms still to converge

**⚠ Tier A reopened 2026-09-05.** Design adversarial review found theoretical commitments in the fixed layer, and
combined with the rule "design proceeds as needed, not dictated by the stage table," three items reopened:
`Plan`'s shape, whether commodity kinds are open or closed, and the one-output-per-unit restriction on units.
New directions are already decided, see [decisions/data-model.md](decisions/data-model.md) 2026-09-05.

Three things decided 2026-08-28 stand unchanged: the interface, how strictly invariants are enforced, and determinism
and hashing. Two things decided 2026-08-30 stand unchanged: `Economy` being mutable across periods, and where the
evolution rule belongs.

Tier B decided 2026-09-05: starting with WIOD (Stage 3), v1 shipping only the `hahnel_2020_slides` prefab for now,
error presentation (Rust `Result`, Python exceptions), seed derivation (SplitMix64), and not shipping an
evolution-rule implementation yet. Still deferred: the scenario file format (to be decided at Stage 4).

Tier C decided 2026-09-05: repository layout and package name, see [decisions/technology-choices.md](decisions/technology-choices.md).
Still open: the shape of CI, and `CITATION.cff`.

## Deferred past v1

| Item | Why it's safe |
|---|---|
| Money and debt stock fields | Adds fields, doesn't change row identity. Needed for credit-creation experiments and SFC accounting identities |
| Interaction topology between agents (network or spatial) | An independent structure indexed by agent identifier. Needed for ABM-based planning simulations |
| Operator layer (structured representation of coordination procedures) | A convenience layer built on top of the interface; existing procedures keep running unchanged. See [decisions/rejected/coordination-procedures.md](decisions/rejected/coordination-procedures.md) |
| Frontend and HTTP contract layer | Not discussed this round |

The only prerequisite hook for the first two items is **stable identifiers**, already listed under Stage 0.
