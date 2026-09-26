# Reproducibility

## 2026-08-28

### Scenarios must pin down the coordination procedure's implementation itself, not just its name and parameters

(⚠ Scope narrowed on 2026-08-28 to implementations bundled with the library; see "Content hashing applies only to implementations bundled with the library" below. The core insight — that a name and version number are not enough to pin down an implementation — still holds.)

**Decision**: When a scenario file references a `Procedure`, it records its content hash, not just its name and version number. The hash in the run manifest must resolve back to the specific implementation. A `prefab`'s name carries its provenance and year; different algorithm versions from the same research each get their own name.

**Why**: This isn't derived from principle — it's sized from the upstream case, see [research/reproduction.md](../research/reproduction.md).

Upstream's published results could not be reproduced by third parties for a long time. After investigation, the cause was **not** any of the usual suspects:

| Common suspect | Actual situation |
|---|---|
| Parameters undisclosed | The endowment of 1000 is written directly in the paper's body text |
| Data undisclosed | Forty input economies had been public for six years |
| Random seed | The data is a fixed file; no seed needed |
| Implementation bug | A few existed, but none large enough to cause an order-of-magnitude difference |

The real cause was that **the algorithm drifted between two publications**, and neither natural-language description was precise enough to distinguish the two versions: the 2020 conference report gave a one-line formula, `w = v(1.05 − 0.5ᵛ)`; the 2023 paper described a different rule in prose. Tested side by side, the former converges in 14 rounds, the latter fails to converge after 250. Both materials were cited as "the same algorithm."

**Natural language is not a specification.** A paragraph of prose describing a price-update rule will be implemented differently by two competent implementers, with different convergence behavior. And these two materials are exactly what the authors published so that others could reimplement the work.

**Alternatives rejected**:

- Recording only the `Procedure`'s name and semantic version — version numbers are maintained by humans, and humans forget. Upstream's two versions were never given different names or version numbers; both materials call it "the price adjustment rule."

**How to apply**:

1. Whenever the documentation describes an algorithm, attach an executable reference implementation, and keep the description and the implementation in sync. When they diverge, the implementation is authoritative.
2. A `prefab` isn't named `hahnel_participatory_planning`; it's named `hahnel_2020_slides` and `hahnel_2023_paper` — these are two algorithms, not two descriptions of one algorithm.
3. When reproducing a result from the literature, record "which material, which version" as part of the scenario.

---

### Each coordination procedure gets a set of convergence regression benchmarks

(⚠ Scope narrowed on 2026-08-28; see "Round-count benchmarks apply only to library-bundled methods and methods using `iterate`" below. The reasoning and failure mode are unchanged.)

**Decision**: Every `Procedure` ships with a fixed input and an expected range of iteration rounds, checked in CI. A run outside that range fails the check.

**Why**: Upstream's rule drifted from the 2020 version to the 2023 version with nothing catching it. In 2026 the author himself submitted two fixes related to the price-update rule, titled "Fix oscillating behavior" and "Fix extremely slow convergence" — he was hand-tuning parameters while the problem was in the rule itself. A test asserting "dep1ex01 cold start should converge in 10 to 20 rounds" would have caught it immediately.

This kind of benchmark complements the differential tests in [performance-architecture.md](performance-architecture.md): differential tests guarantee the computation is correct; convergence benchmarks guarantee the iteration actually converges. The latter is a failure mode specific to this domain — every equation correct, every invariant passing, but the iteration never converges, while the output still looks like a plausible economy.

---

### Content hashing applies only to implementations bundled with the library

**Decision**: The library computes content hashes for the coordination methods and prefabs it ships itself; a scenario's reference by name resolves to a specific hash. For coordination methods a researcher writes themselves, the library **does not** compute a hash — it only records the provenance he **declares**: name, version, git commit, DOI, all optional. If none is available, the field is left blank with an explicit "undeclared" marker.

**Why**: For a researcher's code, a hash computed by the library is a worse version-control system than the researcher's own — see [rejected/invariants-and-metrics.md](rejected/invariants-and-metrics.md).

But the library's own half must still be kept, because the failure mode this original decision guards against would recur within the library itself: six months later, `hahnel_2020_slides`'s implementation changes, and an old scenario silently runs the new algorithm — same name, same parameters, different result. That is exactly a homemade version of the upstream case.

**Partially narrowed**: This narrows the scope of the 2026-08-28 decision "Scenarios must pin down the coordination procedure's implementation itself." That decision's core insight — a name and version number are not enough to pin down an implementation — still fully holds; it's only that for implementations a researcher supplies, the responsibility for pinning them down shifts to his own version control.

---

### Round-count benchmarks apply only to library-bundled methods and methods using `iterate`

**Decision**: The CI assertion on the round-count range applies to coordination methods bundled with the library, and to methods where the researcher calls `iterate`. For methods where the researcher writes his own loop, the library cannot count the rounds, so this benchmark doesn't apply.

**Why**: The interface is a single layer plus a voluntary tool (see [coordination-procedures.md](coordination-procedures.md)); when the loop lives on the researcher's side, the library can't see the round count.

**Partially narrowed**: This narrows the scope of the 2026-08-28 decision "Each coordination procedure gets a set of convergence regression benchmarks." That decision's reasoning — that "every equation correct, every invariant passing, yet the iteration never converges" is a failure mode specific to this domain — is unchanged.

---

### Determinism: declare the boundary and provide a self-test tool, don't enforce it at runtime

**Decision**: The library guarantees its own half is bit-for-bit reproducible — data loading, metric computation, scan scheduling, seed distribution. The researcher's half is his responsibility; the library hands him the seed (`solve(economy, seed)`), and provides `check_determinism(procedure, economy, seed, n)` for self-testing: run it several times, compare the outputs, and report where they differ if they do. This is a tool, not a gate.

**Why**: "Determinism" doesn't mean "no randomness allowed." A randomized coordination method is legitimate research; what needs to be preserved is reproducibility given a fixed seed.

Runtime enforcement is neither possible nor desirable — see [rejected/invariants-and-metrics.md](rejected/invariants-and-metrics.md). Declaring the boundary without providing a tool means the researcher only finds out when someone else fails to reproduce his results — by which point the paper is already published.

**How to apply**: This falls under the broader direction of "make every kind of optional check available." Future testing tools should follow the same shape — provided, optional, explicitly declared.

---

## 2026-08-30

### Transparency has three tiers; the prefab tier is the highest

**Decision**: The key to comparability is letting a reproducer rebuild the same setup with the same tools, verbatim. Transparency splits into three tiers, and the library's way of working is to push people upward:

| Tier | Form | What the reproducer must do |
|---|---|---|
| Low | Provenance undeclared | Can't. The manifest truthfully flags this fact |
| Medium | Git commit or DOI declared | Go find that repository, set up the environment themselves, match versions themselves |
| **High** | Adopted as a prefab | `pip install` and it's there; one citation and it runs |

When provenance is undeclared, the output carries an objective factual marker — "the coordination method and evolution rule used in this run have undeclared provenance." It doesn't block anyone or pass judgment, it just records the fact; readers judge reproducibility for themselves. This follows the same pattern as "residuals are always computed, naming is neutral" in [invariants-and-metrics.md](invariants-and-metrics.md).

**Why**: Transparency doesn't mean the library introspects a researcher's code — that was already rejected, see [rejected/invariants-and-metrics.md](rejected/invariants-and-metrics.md). What transparency needs is for the manifest's provenance record to be enough for someone to find and rebuild the work; the two aren't in conflict.

Only the highest tier truly delivers "built with the same tools, verbatim": the reproducer never has to go find the author's repository. And **the working pattern where "as soon as a researcher publishes code, it gets adopted, cleaned up, reproduced, and packaged into something usable"** is, in essence, exactly the mechanism that pushes people from the middle tier to the highest one — it isn't just a way to attract users, it's how transparency actually gets implemented.

**How to apply**: The undeclared-provenance marker has to appear in the output itself, not buried deep in the manifest — otherwise readers won't notice that the field is empty.

---

## 2026-09-05

### The seed is a 64-bit unsigned integer; derivation uses SplitMix64

**Decision**: `solve(economy, seed)`'s `seed` is an integer from 0 to 2⁶⁴−1. `split_seed(seed, n)` generates n sub-seeds using SplitMix64. `rng(seed)` returns `numpy.random.default_rng(seed)`.

**Why**: SplitMix64 has a public specification and is bit-for-bit reproducible across languages, so scan scheduling on the Rust side derives the same sub-seeds as computed on the Python side.

---

## 2026-09-05

### The run configuration document is an input, not just a record; it's separate from the run manifest

**Decision**: The library produces a **run configuration document**: it's emitted at the end of a run, and feeding it back to the library on a later run reproduces the same setup. It is **separate** from the run manifest — the configuration document holds settings (loadable), the manifest holds provenance (read-only); the configuration document's hash goes into the manifest.

**Why**: Existing decisions all describe the manifest in the recording direction only — write it down for people to look at and check afterward. **Only the loadable half relieves the reconfiguration burden**: the reproducer doesn't have to manually check and reconfigure each field one by one.

The value here goes beyond reproducibility. **The reconfiguration burden is the main cost of making anything optional** — removing it makes every future "should this be optional" judgment cheaper. So this document carries real weight; it isn't a side feature.

The split into two documents exists because one document needs to distinguish "which fields are settings" from "which fields are results from this run" — otherwise feeding it back would treat last run's results as this run's input.

**What this document can and cannot promise**: the part the library owns can be restored automatically (the declared layer, the content hash of library-bundled procedures, parameters, seed, the loader and its parameters, library version); code the researcher owns follows the rule in "Content hashing applies only to implementations bundled with the library" in this document — it isn't hashed, only his declared provenance is recorded, left blank with an explicit **"undeclared"** marker if unavailable.

**Alternatives rejected**: Merge settings and provenance into one document — when loading, it becomes unclear which half is input, and the boundary blurs.

---

### The run configuration document's versioning rule: missing keys use defaults, unknown keys error, removed keys error explicitly

**Decision**:

| Case | Behavior |
|---|---|
| Document has the key, library recognizes it | Use it |
| Document is missing the key, library has it | **Use the default, don't error** (an old document must still run against a newer library) |
| Document has the key, library doesn't recognize it | **Error**, and the two causes must be distinguished |

For the third row, the error message for the two causes **must differ**: library older than the document (document came from a newer version) → "this document requires a newer library"; library newer than the document and the key **has been removed** → "this setting no longer exists in this version," stating clearly when and why it was removed. The latter requires the library to keep a **registry of retired keys** (key name, version removed, reason) — without it, removal degrades into a generic error.

**One more constraint**: **the default value for any newly added key must preserve the old behavior.** Otherwise, an old document fed into a newer library won't error, but it will run a different setup than before — same name, same parameters, different result, exactly the shape this family of decisions guards against. **A new feature that can't preserve old behavior via its default must not be added silently** — it goes through an explicit version change instead.

**Why**: Once the document is loadable, "silently ignoring a new key" turns from impossible into easy — running a new configuration under old semantics.

---

### `Economy` gets a content hash, byte-exact, plus per-column hashes stored alongside

**Decision**: The library computes a content hash for `Economy` and writes it into the run configuration document, **byte-exact, no precision reduction**. Besides the overall hash, it **also stores per-column hashes**; a mismatch error must state which column differs. The hash algorithm carries a version tag (so an old document can still be interpreted correctly).

**Why**: When economies don't match, the reproducer is holding **the same code with different numbers**, and nothing anywhere shows the difference. This is exactly the shape of the case at the top of this document: upstream's published results were long unreproducible even though parameters and data were both public — the failure was that "what you got and what was used originally weren't the same thing, and no one noticed."

It covers three categories that "loader name + parameters" can't cover: a hand-built economy, a researcher's own loader, **and a loader drifting on its own** (same parameters, different loader version). This repository already has a precedent for the last category: `research/bench/repro.py`'s `parse` silently truncates input records whose lengths don't match, while the Rust loader raises an error on the same input.

Byte-exact was chosen for research usability — reducing precision would swallow real small differences, and this library's convergence criteria are thresholds of 3% to 5%, where a last-digit difference can genuinely change the round count (crossing the threshold). The cost is that cross-platform floating-point last-digit differences get flagged as "not the same economy" — **the per-column hash exists precisely to make that alarm diagnosable**: it reports "column `input_coefficient` differs, the rest match," letting the researcher tell at a glance whether it's a loader difference or an actual data change.

Measured cost: the dep1ex01 economy is 53.3 MB; sha256 takes 0.064 seconds, negligible against the 1.2 seconds for one solve.

**This does not apply to code.** The reasoning in "Content hashing applies only to implementations bundled with the library" — "for a researcher's code, a hash computed by the library is a worse version-control system" — holds for code (which has git); it does not hold for an in-memory array, which has no version control at all.

**How to apply**: A matching hash only proves the arrays are bit-for-bit identical — it does not prove the same library version, numpy, platform, or solver. What a field in the document claims must exactly match what it actually checks.

**Alternatives rejected**: Hash after reducing precision — swallows differences that can change the round count; record only provenance and parameters, no hash — catches neither a hand-built economy nor loader drift.

---

## 2026-09-06

### The run configuration document's concrete shape: JSON, a standalone function, per-column hashes

**Decision**: This turns the 2026-09-05 decision "The run configuration document is an input" into a buildable spec. Everything below is newly decided here.

**Format**: JSON, UTF-8, `sort_keys=True`, indent 2.
**Excluded**: TOML — requires an extra dependency on the write side; YAML — requires a dependency, and implicit type coercion reads `no` as a boolean.

**The API is a standalone function, not welded into `run`**:

```
run_configuration(procedure, economy, seed, loader=None, plan=None) -> RunConfiguration
RunConfiguration.to_json(path) / RunConfiguration.from_json(path)
```

`run()`'s signature and `RunResult` are unchanged. **Why**: `run`'s job is to run. The configuration document has to hash the economy's contents (53.3 MB, 0.064 seconds for dep1ex01), and welding that into `run` means every run pays that cost, while a parameter scan runs it thousands of times. The researcher calls it explicitly; whether to pay is his call.

**Top-level keys**: `configuration_version` (int), `library_version`, `seed`, `economy`, `procedure`, `loader`, `plan_fields_absent`.

`plan_fields_absent` comes from `plan.absent_fields`; if `plan` isn't given, it's `null`, the same "undeclared" form as the loader block. **This function only duck-types `plan`** — it doesn't import `Plan`; the configuration document records what the researcher declared, not a validation of his plan.

**Economy hash block**: `{"algorithm": "sha256-columns-v1", "digest": hex, "columns": {column name: hex}}`. The normalization is pinned as follows; changing any step requires bumping `algorithm`'s version number:

- Each column is first passed through `np.ascontiguousarray`, then normalized to little-endian (`astype(dtype.newbyteorder("<"), copy=False)`), then the **column header** is appended to `tobytes()` and fed to sha256. ⚠ **The column header's byte-level encoding is pinned by item 2 of "Six implementation details finalized" below** — the line here originally specified a different separator, which is now void; that item pins the correct one.
- The `extra` bag's keys are included as columns too, with the column name prefixed `commodity_extra.`, `unit_extra.`, `consumer_extra.`
- The overall `digest` is the sha256 of the hex digests of all columns, sorted by column name and concatenated

**Normalizing to little-endian instead of rejecting big-endian platforms**: the cost is one copy, in exchange for cross-platform comparability.

**Coordination method block**: for a library-bundled method (`type(procedure).__module__` starting with `cyberstride.`), record `{"kind": "library", "module", "qualname", "source_digest", "parameters"}`, where `source_digest` is the sha256 of **the bytes of the source file defining that module** — not the class's source code, because module-level constants (such as `PRICE_STEP_CEILING`) also determine behavior. A researcher's method is recorded as `{"kind": "researcher", "declared_origin": null}` — **the key is always present, and the value `null` is the explicit form of "undeclared"**, not the key being omitted.

**Parameters**: if the coordination method is a dataclass, record its fields; if not, `"parameters": null`. ⚠ **How each field's value is recorded is superseded by the two 2026-09-06 revisions below**, each of which carves off a piece of this line — this line is no longer the complete rule. The complete rule is in "How parameter values are recorded (the single source)."

**The loader block is supplied explicitly by the researcher**; if not given, it's `null`. **Why**: `Economy` is a fixed layer; giving it a provenance field would push provenance data into the fixed layer. The economy's identity is pinned by the content hash; the loader block is only a convenience.

**Implementation of the versioning rule**: the retired-key registry is a module-level `RETIRED_KEYS: dict[str, RetiredKey]`, where `RetiredKey` carries `removed_in` and `reason`. It's empty in v1, but the mechanism must exist and be tested.

**How "new keys' defaults must preserve old behavior" becomes a test**: a test dumps all current default values to JSON and compares them against a checked-in baseline. Changing a default turns the test red, forcing an explicit decision.

**How to apply**: These are the buildable shapes, not a new charter. Where they conflict with the decisions above, the decisions above take precedence.

---

---

### A researcher's coordination method also records parameters; six implementation details for the run configuration document finalized

**Decision**: **The researcher's block also carries `parameters`**, following exactly the same rules as the library-bundled block (dataclass fields recorded; JSON scalars recorded directly; non-scalars use the library/researcher two-way split; non-dataclasses record `null`). The `declared_origin` field and "no content hash for a researcher's code" both remain unchanged.

**Why**: Pinning the researcher's block to exactly the two keys `{"kind", "declared_origin"}` mistakenly extended "don't hash a researcher's code" into "don't record his parameters either." The reasoning for that rule — "for a researcher's code, a hash computed by the library is a worse version-control system" — **holds for code, but not for parameters**: parameters are data, not code, and the library can introspect a researcher's dataclass exactly as well as it can its own.

The consequence landed squarely on this library's target users. **A coordination method the researcher writes himself is the most common case**, and if his parameters can't be recorded, then "run it, get the document, feed it back, get the same setup" doesn't hold for him — and per [scope-and-purpose.md](scope-and-purpose.md) 2026-09-05, helping the next person in the field get started faster is the tiebreaker for priority.

**Partial supersession**: This overturns the **exhaustiveness** of the same-day decision "[The run configuration document's concrete shape](#the-run-configuration-documents-concrete-shape-json-a-standalone-function-per-column-hashes)"'s line "a researcher's method is recorded as `{"kind": "researcher", "declared_origin": null}`." The rules that a researcher's code isn't hashed, and that only declared provenance is recorded, are unchanged.

**Six more details finalized**:

1. **There are 8 top-level keys**; `core_version` sits alongside `library_version`. The original list omitted it.
2. **The column header's byte encoding is pinned**: `f"{name}\n{dtype.str}\n{shape joined by commas}\n"` encoded as UTF-8, then appended to `tobytes()`. **Without pinning this, the Rust side can't compute the same `sha256-columns-v1`**, and cross-language reproducibility is exactly this hash's purpose. The spec itself says "changing any step requires bumping the version number," and the separator is one of those steps that must be pinned. ⚠ **The scalar column's shape line is written as `1`, not an empty string.** `np.ascontiguousarray` promotes a 0-dimensional array to one dimension, so `period`'s shape is `(1,)`. A second-language implementation working from the prose alone would naturally write an empty shape and compute a different digest — **exactly the kind of divergence this algorithm identifier is meant to prevent**.
3. **`loader` accepts a JSON-serializable `Mapping`**, not the loader function itself.
4. **The per-column digest needs a comparison entry point.** "A mismatch error must state which column differs," as written, had no code to execute it — the digest was written into the document but nothing in the library compared it. The error message **must list the differing column names**; saying only "mismatch" doesn't fulfill this rule.
5. **`configuration_version` newer than the library must error**, not be silently accepted just because the key sets happen to match. The original three-row versioning rule only covered keys, not the version number itself.
6. **`allow_nan=False`.** `NaN` and `Infinity` are not standard JSON; another language can't read them back, and cross-language readability is the reason JSON was chosen. A non-finite value among the parameters must error, and the message must state which parameter.

**One accepted cost**: `plan_fields_absent` records the field names the researcher declared, and **the library does not check that they are actually fields on `Plan`** — a direct consequence of "duck-type only, don't import `Plan`." A misspelled field name will go into the document unchanged with nothing turning red. This is an accepted cost, not a defect, but it must be stated where the researcher can read it.

**How to apply**: Before adding any new key to the run configuration document, ask two questions — **does its default preserve old behavior? Will a cross-language implementation compute the same bytes from this prose?**

---

### numpy scalars are recorded by value; digest comparison returns a report, not an exception

**Decision**: Two revisions, two finalizations.

**1. When a parameter is a numpy scalar, call `.item()` to convert it to a Python scalar before recording it.** The original rule — "JSON scalars recorded directly, everything else follows the library/researcher two-way split" — never said which side a numpy scalar falls on, and the consequence is that **the run configuration document silently loses data**: `np.float64` happens to be a subclass of `float`, so it gets recorded, while `np.int64`, `np.float32`, and `np.bool_` are not subclasses of their corresponding built-in types, so `max_rounds=np.int64(250)` gets recorded as "parameter undeclared" — **the value is simply lost, and the researcher never notices**.

That `np.float64` happens to work is an accident, not a design. After conversion, all four types follow the same path. A value that becomes non-finite after conversion must still fail the "parameters must be finite" check — it can't be routed around it.

**2. `compare_economy_digests` returns a report, doesn't raise.** The library's existing shape for self-test tools is `check_determinism` → `DeterminismReport`, and [spec.md](../spec.md)'s division of responsibility says **the library is responsible for the process, the researcher is responsible for the result** — invariants and metrics are an optional toolbox, not a hard gate. Comparing two digests is a judgment call, and that judgment is handed back to the researcher.

⚠ "A mismatch error must state which column differs" governs **the content of the message** (it must name the differing columns), not whether this mechanism raises. That half of the rule is unchanged.

**Exception**: when the two digests' `algorithm` values differ, it **still raises**. Digests computed under different normalizations, whether they happen to match or not, mean nothing — that isn't a result that can be handed to the researcher to judge.

**3. The library doesn't automatically verify the economy's digest.** `from_json` has no economy in hand; `run_configuration`'s digest was computed from the economy it was given — neither call site has a second party to compare against. Comparing requires an entry point that holds both at once, and that is exactly the comparison function itself. The researcher calls it explicitly.

**4. Loading an old document does not upgrade its version number.** A document with `configuration_version: 0` is written back still as `0`. The library doesn't rewrite facts in the researcher's own document on his behalf.

**Why**: The first two of these were pushback found during implementation, both pointing at the same class of mistake — **the decision was made looking only at the case in front of it, without checking back against a shape the library had already established**. The first treated "what counts as a JSON scalar" as self-evident; the second lifted the word "error" straight from the decision text, when that sentence was actually about message content.

**How to apply**: Before adding a new self-test tool, look at what shape `check_determinism` already has — **a tool returns a report; only a gate raises** — and in this library's toolbox, gates are the exception, not the norm.

---

### Digest algorithm bumped to v2: reject dtypes the hash can't represent faithfully, normalize `period` and line endings

**Decision**: Five items; the first four change behavior, and the algorithm identifier moves from `sha256-columns-v1` to **`sha256-columns-v2`**.

1. **The column digest rejects any dtype outside the simple set.** If `dtype.kind` isn't in `biufc`, or `dtype.fields` is non-empty, it errors and states which column and which dtype.
2. **`period` is normalized to int64 before the digest is computed.**
3. **Before hashing, `source_digest` normalizes CRLF and lone CR to LF.**
4. **JSON-native containers are recorded recursively by value**: `list` / `tuple` → array, `dict` (keys must be `str`) → object, elements recurse through the same parameter rule. `np.ndarray` still falls to the undeclared form (unbounded size).
5. **The column digest's preimage needs a test hand-transcribed from the spec text**; the expected value must not be copied from the implementation.

**Why**: All from the second round of adversarial review; all four are cases of "a claimed property that doesn't actually hold."

- **The preimage had no test executing it** (item 5). Changing the column header separator, the field order, UTF-8 to UTF-16, the shape-join character, or **swapping the column digest's sha256 for sha3_256** — five mutants, **all of them survived the full suite of 834 tests**, while `algorithm` still said `v1`. The reason: that whole suite consists of inequality assertions (A ≠ B), which are insensitive to format; the one test that actually computed the preimage was a **golden-master stand-in**, with its expected value taken from the implementation's own output. `algorithm` is this document's entire promise of cross-language reproducibility, **and it could now be lying**. By contrast, the two mutants at the overall-digest layer were killed within 0.7 seconds — it's the column-digest layer that has no net, not the module as a whole.
- **Object dtype hashes a memory address** (item 1). `tobytes()` gives the bytes of a `PyObject*` pointer, so two economies identical value-for-value get different digests, while the module's docstring claims "identical digests prove the arrays are bit-for-bit identical." Structured dtypes share this family of problem: `dtype.str` is lossy — `[("alpha","<f8"),("beta","<f8")]` and `[("gamma","<f8"),("delta","<f8")]` are both `|V16`, and different field names produce the same column digest. **The rejection sits at the digest layer, not in `Economy`** — limiting which dtypes `Economy` may hold is a data-model decision and belongs in its own entry; the digest's job is simply refusing to hash something it can't hash faithfully.
- **`period`'s Python type leaks into the column header** (item 2). `period=np.int32(0)` and `period=0` pass the same `validate` and are the same economy in the same period, yet their digests differ. The cross-language half is harder still: the Rust side has no way to know whether to write `<i4` or `<i8` in the column header.
- **`source_digest` changes with the checked-out line ending** (item 3). This repository has `core.autocrlf=true`; the working tree is CRLF while the blob is LF, so two researchers checking out the same tag get two different digests. ⚠ This item is not filling a gap — it's **preserving a property that doesn't hold across platforms**: a mutant that added this normalization was killed, because a test independently hashes the raw bytes. A line ending is not behavior.
- **A container parameter silently loses its value** (item 4). `(0.1, 0.9)` gets recorded as "parameter undeclared," indistinguishable from "the researcher passed in a callable." The implementation followed the spec as written, **but the spec's own criterion doesn't hold here**: the same-day decision "numpy scalars are recorded by value" already established that silently losing data is unacceptable, and `np.int64` and a two-element float tuple are no different on that count.

**Why bump the version number**: the spec itself says "changing any step requires bumping the version number." With zero users and zero published documents right now, the cost of changing it is zero; not changing it would let the `v1` identifier **lie a second time**.

**Partial supersession**: This changes the algorithm identifier and the column digest's scope in "[The run configuration document's concrete shape](#the-run-configuration-documents-concrete-shape-json-a-standalone-function-per-column-hashes)," and changes the scope of item 1 in "[numpy scalars are recorded by value](#numpy-scalars-are-recorded-by-value-digest-comparison-returns-a-report-not-an-exception)" (generalizing from scalars to JSON-native containers). The rest of both decisions is unchanged.

**Known gaps not covered**: `Enum`, `datetime`, `complex`, and `set` parameters still fall to the undeclared form — JSON has no corresponding form, and converting them requires choosing a representation, which is a separate decision.

**How to apply**: **The digest's preimage is a cross-language contract, and it must have a test hand-transcribed from the spec text.** An inequality assertion (A ≠ B after changing A) proves nothing about format; a test whose expected value comes from the implementation is a golden-master stand-in. Before adding any step to this preimage, ask "would a second-language implementation compute the same bytes from this prose?"

---

### How parameter values are recorded (the single source)

**Decision**: A parameter's value in the run configuration document is recorded per the table below. **This table is the single, complete rule** — the statements previously scattered across three decisions each covered only part of it; this table is authoritative.

| Value | How it's recorded |
|---|---|
| `bool` / `int` / `float` / `str` / `None` | Recorded directly by value |
| numpy scalar (`np.generic`) | `.item()` to a Python scalar first, then recorded per the row above |
| `list` / `tuple` | JSON array, elements recurse through this table |
| `Mapping` with all-`str` keys | JSON object, values recurse through this table |
| `np.ndarray` | **Undeclared form** (unbounded size) |
| Everything else (callables, `Enum`, `datetime`, `complex`, `set`, mappings with non-`str` keys) | **Undeclared form** |

"Undeclared form" refers to the block `{"kind": ..., "declared_origin": ..., "parameters": ...}`, with library-owned vs. researcher-owned determined by the value itself or its type.

Non-finite values (`NaN`, `Infinity`) error at any level, with the message giving the **full path with indices and keys** (for example `parameters.weights[1]`, `parameters.thresholds['price']`).

**Why**: This rule was cut twice — the 2026-09-06 decision "numpy scalars are recorded by value" added the second row, and the same-day "Digest algorithm bumped to v2" item 4 added the third and fourth rows — while **the original line, "JSON scalars recorded directly, everything else follows the two-way split," was never rewritten**. Anyone implementing from that original line alone would reproduce the same bug. One rule scattered across three places is no rule at all.

**Known cost, to be stated where the researcher can read it**: `Enum`, `datetime`, `complex`, and `set` fall to the undeclared form and their values are lost — JSON has no corresponding form, and converting them would mean choosing a representation on the researcher's behalf. A `namedtuple` is recorded as a JSON array, **losing its field names**, because it is a `tuple`. A self-referential container raises `RecursionError` instead of `ConfigurationError`; no realistic parameter takes this shape.

**Alternatives rejected**: Cap container size — any cap would be arbitrary, and the truly unbounded category (arrays) is already excluded.

---

### The column digest rejects text dtypes, stricter than the argument requires

**Decision**: `'U'` and `'S'` (text) columns are rejected along with object and structured dtypes, even though their `tobytes()` is faithful.

**Why**: numpy's `<U8` is stored in memory as UCS-4 — eight code points take 32 bytes. A second-language implementation working from the spec text has no way to guess this width, and would compute a different digest — **exactly the kind of divergence this algorithm identifier exists to prevent**. Faithfully hashing bytes that a second language can't reproduce is worse than rejecting them: it produces a digest that looks usable but isn't.

**How to apply**: If text columns are supported in the future, pin their encoding and width in the spec first, then lift this restriction.
