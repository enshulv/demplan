# Rejected: Invariants and Metrics

## 2026-08-28

### The library mandates a fixed set of core metrics

**Rejected.**

**Proposal**: `Evaluator` fixes five core metrics — feasibility violation, rounds to convergence, labor cost,
emissions against a cap, welfare under a given social welfare function — and does not expose them as plugins, to keep results comparable across studies.

**Why it was considered**: the reasoning in `extension-boundary.md:11` — once the data model and the metrics are pluggable,
two results stop being comparable, and the goal of reducing duplicated work across the field fails on the spot.

**Why rejected**: all five carry a theoretical commitment. "Welfare under a given social welfare function" first requires committing to an SWF form,
which is the most contested point in normative economics; "labor cost" presupposes that labor is the relevant cost measure,
while the linear-programming school wants the objective function's value instead; "emissions against a cap" presupposes that ecological constraints take the form of a cap rather than a tax or a stock constraint.

More fundamentally: **comparison is not the library's job, it is the researcher's.** Comparison requires both sides to share a standard,
and choosing that standard is a research judgment. If the library picks it for them, it decides which angle the research conclusion holds from.

Comparability has another path that does not require fixed metrics — see [invariants-and-metrics.md](../invariants-and-metrics.md),
the point on "comparability rests on raw output."

**Revival condition**: none. This conflicts directly with the theory-neutrality constraint.

---

### Require `State` to implement a method that returns recordable quantities

**Rejected.**

**Proposal**: the `State` used by `iterate` must implement `record() -> dict[str, float]`; the library calls it every round,
guaranteeing that every iterative method produces a trajectory.

**Why it was considered**: to guarantee a non-empty trajectory. Otherwise, if the researcher does not provide one, no convergence curve can be drawn.

**Why rejected**: forcing this buys "non-empty," not "comparable" — each researcher picks their own key names, one reports `max_excess`,
another `rmse_price`, and the two curves cannot be overlaid on the same chart.

**Only the library can compute a comparable trajectory**, so the correct approach is the optional `plan_of=`:
the researcher supplies "how to read the current state as a plan," and the library measures it with its own consistent, stackable definition.

There is also an asymmetry on the cost side: **an optional parameter can be added later; a mandatory interface cannot be removed later.**
Adding an optional `plan_of=` today changes none of the existing calls; making `record()` mandatory today and then removing that requirement
tomorrow would break every published method at once. So "not mandatory now" is reversible, and "mandatory now" is not.

**Revival condition**: if it is observed that nearly all methods pass `plan_of`, and the lack of a trajectory causes real problems.
At that point there would be evidence to support it, rather than a prediction.

---

### Enforce determinism at the runtime level

**Rejected.**

**Proposal**: sandbox away `random`, the clock, and file access from the researcher's code, guaranteeing determinism at the runtime level.

**Why it was considered**: `spec.md` promises "bit-identical output given the same seed," and a researcher's arbitrary Python code cannot
deliver that on its own.

**Why rejected**: two reasons, either one sufficient on its own. Python has no real sandbox, so this cannot be done.
And a randomized coordination procedure is legitimate research — what must be guaranteed is "reproducible given a seed," not "no randomness allowed."

**Revival condition**: none.

---

### Compute a content hash for coordination procedures supplied by researchers

**Rejected.**

**Proposal**: per the original wording in [reproducibility.md](../reproducibility.md), record a content hash for every coordination
procedure, including researcher-authored ones, extracting source with something like `inspect.getsource` and hashing it.

**Why it was considered**: the upstream case — two price-update rules with the same name, one converging in 14 rounds and one not
converging in 250, went unnoticed for six years. A content hash guards against exactly this.

**Why rejected**: for a researcher's own code, a hash computed by the library is a **worse version control system**.
Their method lives in a repository, where a single git commit covers the whole repository, with history, authorship, and timestamps —
that is far stronger than a function body the library extracts on its own. And if they never publish the code at all, a hash does not help
either — a hexadecimal string with nothing to compare it against is dead information.

There is also a string of technically unhashable cases: lambdas, C extensions, and interactively defined functions have no retrievable
source; bytecode differs across Python versions; hashing a closure means hashing the entire environment.
When the source cannot be retrieved, the only option is to record "unhashable," and **a fake provenance record is worse than no
provenance record.**

Responsibility is clear here too: whether "the run used the same code" is a question for the researcher's own version control, not
this library.

**This rejection covers only half of the proposal.** Content hashing is still mandatory for the coordination procedures and prefabs
**the library ships itself** — that guards against the library drifting on its own: six months from now, `hahnel_2020_slides` gets
reimplemented, and an old scenario silently runs the new algorithm — same name, same parameters, a different result. That is exactly
the upstream failure mode, self-inflicted.

**Revival condition**: none. The library's own half was already retained, see [reproducibility.md](../reproducibility.md).
