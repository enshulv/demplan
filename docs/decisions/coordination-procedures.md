# Coordination procedures

> This document uses "coordination procedure" for what the code calls `Procedure`.

## 2026-08-28

### Coordination procedures are supplied by the researcher; the kernel yields control

**Decision**: The coordination procedure isn't hardwired into the library. The researcher supplies his own implementation at the Python layer, and the library's job is to call it. The kernel's main loop is structured so that it can hand off control — it isn't a one-shot "data in, data out."

**Why**: If the library hardwired the mechanism, it wouldn't be infrastructure — it would be a program with a few options. The mechanism is the researcher's own research; deciding it for him would mean doing his research for him.

This is consistent with "the Python interface boundary sits at the coordination-procedure layer" in [technology-choices.md](technology-choices.md): a coordination procedure is called once per round, on the order of 10² calls per run — the cross-language overhead is acceptable there; the `Participant` layer is 10⁷ calls in v2, and can't afford that boundary.

Measured under realistic conditions, this overhead is negligible: each round a coordination procedure touches five price vectors, length 10² to 10³ (see `research/bench/repro.py:118`), tens of kilobytes. 54.8 MB is the whole economy, which the coordination procedure never touches. The cross-language overhead is on the order of 0.1%.

**How to apply**: When designing any extension point, ask first "is this the researcher's research content, or is it repeated work." If it's research content, hand it off; if it's repeated work, take it over.

---

### The extension mechanism is an interface, not a fixed set of operators

**Decision**: The library's extension point is an interface a coordination procedure must satisfy. Any implementation satisfying the interface can use the library's full surrounding capability: the data model, invariant checks, `Evaluator` metrics, the run manifest, parameter scans, deterministic seed distribution. The library doesn't need to absorb it into its own codebase.

**Why**: Compare to scikit-learn. A third-party implementation of `fit` / `predict` / `get_params` / `set_params` can be used directly with `Pipeline`, `GridSearchCV`, `cross_val_score` — the official documentation states explicitly that it doesn't need to be merged into sklearn. mesa is the same: users subclass `mesa.Agent`, and `step()` can contain arbitrary Python. networkx is the same: a graph data structure plus an algorithm library, and new research is just writing your own function that consumes a `Graph`.

The common shape of these three libraries is that **the infrastructure provides surrounding services, the user writes arbitrary code, and they connect through an interface** — the maintainer isn't on the critical path. By contrast, libraries built around "assembling from a set of preset operators" (polars, Keras, PyMC) all have the maintainer as a bottleneck; they accept this because their engine has to see the whole expression to do query optimization or automatic differentiation. This library has no such payoff.

**Alternatives rejected**: See [rejected/coordination-procedures.md](rejected/coordination-procedures.md).

**How to apply**: To decide whether some capability should be an extension point, ask "would not making it one block the researcher." If it would, it must be an interface, not a list the maintainer maintains.

---

### Comparability comes from a shared data model and scorer, not from reading the other implementation's code

**Decision**: Two coordination procedures are comparable when they run on the same `Economy` and are scored by the same `Evaluator` using the same metrics. The library makes no promise that it can understand a researcher's implementation, nor that it can judge whether two implementations are equivalent.

**Why**: This is the correct resolution of the comparability burden raised in [extension-boundary.md](extension-boundary.md). Two third-party estimators in sklearn are comparable not because sklearn can read their source — it can't — but because they consume the same input and are scored by the same metric.

"Being able to read what the other implementation does" is a capability beyond comparability, requiring a structured representation of the method (see the operator-based alternative in the rejected-alternatives record) — it isn't the foundation of comparability. Conflating the two would lead to building operators for the sake of comparability that comparability never needed.

**How to apply**: When describing this library's comparability externally, say "the same economy, the same scorer" — not "you can inspect each other's methods." The latter isn't achievable in v1.

---

### The interface has exactly one layer; `iterate` is a voluntary tool

**Decision**: The coordination procedure's interface is a single method:

```
solve(economy, seed) -> Plan
```

All three mechanisms implement it — iterative price adjustment, direct labor-time computation, and the linear-programming reference solution.

The library separately provides a **voluntary** looping tool, `iterate(init, step, converged, max_rounds)`. If the researcher calls it inside `solve`, the library gets the round count, an upper-bound safeguard, and divergence detection; if he doesn't, all he gets is the final result.

`iterate` also takes an optional `plan_of` parameter: it tells the library how to read the current round's state as a plan, and the library then measures every round using **its own** set of metrics, producing a round-by-round trajectory with the same definition across mechanisms.

`State` is entirely unconstrained — an arbitrary Python object belonging to the researcher, and the library never looks inside it.

**Why**: The point is tool infrastructure, not forcing anyone into a particular style. Provide a convenient tool, and people who find it useful will use it on their own.

Two alternative shapes were rejected: a two-layer interface (a general outer layer plus a mandatory, more detailed inner layer for iterative mechanisms) would let the library get complete round-by-round information, but a researcher's existing scripts would have to be torn apart to fit it; a single layer with no tool at all would leave the convergence-round benchmarks in [reproducibility.md](reproducibility.md) with nothing to hang on. The voluntary-tool path serves both, at the cost that round-count information is only available for methods that used the tool.

`plan_of` buys **diagnostic power, not comparability** — comparability is fully served by the final configuration plus a process summary, see "comparability comes from raw output" in [invariants-and-metrics.md](invariants-and-metrics.md).

**Alternatives rejected**: A mandatory `record()` — see [rejected/invariants-and-metrics.md](rejected/invariants-and-metrics.md).

**How to apply**: Whenever the library wants some piece of information, make it a voluntary tool first. A voluntary parameter can be added later without breaking existing calls; a mandatory interface can't.

---

### Proposal behavior belongs to the researcher; the library provides tools but doesn't hardwire them

**Decision**: The step "given prices, how much each sector proposes to produce and how much input it wants" belongs to the researcher. The library provides tools like `leontief_demand(economy, prices, targets)` that sit there ready to use; if he wants to substitute his own proposal behavior, he simply doesn't call them.

**Why**: Overstepping means **hardwiring**, not **providing**. If the library welded proposal behavior into its kernel, it would be making a theoretical commitment on the researcher's behalf — the eight closed-form demand expressions upstream show that proposal behavior itself is a modeling choice.

Conversely, if the library didn't even provide something as basic as computing Leontief demand, every researcher would rewrite it themselves — exactly the repeated work this library exists to eliminate.

**How to apply**: This is the general form of the "tool principle," applicable to every computational step carrying a theoretical commitment: provide it, don't hardwire it, don't make it the default path.

---

## 2026-09-05

### Arrays handed to researcher code are read-only; `RunSummary` distinguishes divergence from running out of rounds

**Decision**: The three arguments `PriceRule` receives (prices, supply-demand gap, relative imbalance) are all read-only views; writing to them in place raises `ValueError`, and the protocol's documentation states this constraint and where it comes from. `RunSummary` adds `diverged`, symmetric with `converged`; it's `None` when the coordination procedure didn't use `iterate`.

**Why**: Both changes turn a silent error into an error raised on the spot.

The price rule's in-place writes to its arguments had two leak paths, measured on a synthetic economy:

- Writing to `price` — output quantities are bit-for-bit identical to an honest run, but the recorded `indicative_price` is all zero. The plan is archived under a price the proposal never actually used.
- Writing to `imbalance` — **25 rounds becomes 1**, an entirely different plan, while `converged` still reports `True`. The cause: keyword arguments are evaluated in the order they're written, `next_price=` before `worst_imbalance=`, so the modified imbalance is what decides convergence. The round count is exactly what this prefab promises externally.

The consequence of `RunSummary` lacking `diverged`: a researcher going through the high-level `run` has no way to tell "did it diverge, or did it just run out of rounds." These two facts mean opposite things for his conclusion — one is a property of the mechanism itself, the other means the budget was set too low.

**Alternatives rejected**: Pass a copy instead of a read-only view — has a cost, and it hides this class of bug rather than exposing it.

**How to apply**: Any array the library hands to researcher code, and still needs itself afterward, should be handed over as a read-only view.

⚠ **The 2026-09-05 adversarial code review found that this only blocks direct writes; two paths remain open**: writing to `arg.base`, and a rule returning a buffer it keeps and rewrites the following round — because the library stored the returned value by reference as next round's price, that memory's ownership was never in the library's hands. Measured: for a rule that reuses a buffer, the price archived is `[902.05, 945.72, 711.81]`, while the proposal actually used `[899.51, 943.76, 711.26]`; writing to `imbalance.base` turns 25 rounds into 1 while `converged` still reads `True`.

**A read-only view only protects memory the library itself owns**, and this How-to-apply line didn't distinguish "memory the library owns" from "memory the library merely holds a reference to." Fixed; the fix and the new How to apply are in the next entry, [arrays handed to researcher code are the library's own copies](#arrays-handed-to-researcher-code-are-the-librarys-own-copies-diverged-gets-a-third-state).

---

### Arrays handed to researcher code are the library's own copies; `diverged` gets a third state

**Decision**: Three items, all landed on 2026-09-05.

1. **Arrays the library hands to researcher code are the library's own copies, not views.** `PriceRule`'s three arguments go through `_frozen_copy`: copy first, then mark read-only. A copy owns its own memory; its `.base` is `None`, with no hole to exploit. The rule's **return value is also snapshotted** (`_owned_copy`), so a rule can keep an output buffer and rewrite it repeatedly without ever writing onto the library's state.
2. **`iterate`'s `diverged` gets a third state.** It's `None` when `plan_of` isn't given, paralleling "the library didn't see the loop": a loop nobody watched isn't the same as a loop that didn't diverge. `rounds` distinguishes between these two `None`s.
3. **The reference solution's declaration checks gained three more cases**: the lower bound is now checked for finiteness first (`NaN < 0` is false, and `NaN != 0` is true, so both of the old checks let it through); a maximization objective's `weights` now go through both the finiteness and consumability checks; `minimize_kind` must be a valid `CommodityKind`.

**Why**: All three are the same problem in different guises — **code claiming a property it doesn't actually have**. The read-only view was documented as "an in-place write raises," while two escape paths stayed open; `diverged=False` was read as "did not diverge" when it actually meant "wasn't watched"; the declaration checks were documented as "the reference solution doesn't depend on the objective's own checks," while the maximization branch failed every one of them. Per [scope-and-purpose.md](scope-and-purpose.md) 2026-09-05, a false claim is worse than a missing record: a missing record just withholds information, a false claim gives wrong information.

**Maximization weights are not checked for sign.** A negative weight is a self-consistent penalty term; banning it would weld "what a social welfare function is allowed to say" into a layer that's supposed to carry no such commitment. ⚠ Cost to acknowledge: `_require_consumable_support` will block a use case like "weighting a natural resource to run a shadow-price experiment." This restriction rests on the same principle as not checking sign — the base layer is theory-neutral — but points the other way: what blocks it isn't a theoretical stance, it's the program's structure — a weighted commodity turns into a final-consumption variable, and allocating a natural resource to consumer units has no meaning in this data model.

**Partial supersession**: This overturns the **How to apply** of the previous entry, [arrays handed to researcher code are read-only](#arrays-handed-to-researcher-code-are-read-only-runsummary-distinguishes-divergence-from-running-out-of-rounds) (its line "any array the library still needs afterward should be handed over as a read-only view"). That entry's decision, reasoning, and measurements still hold; the two entries coexist.

**Alternatives rejected**: Validate only `PriceRule`'s return value's dtype and length at that one call site — the hole is in `Plan.valuation` (which checks neither dtype nor length), and patching only this one call site blocks only one caller. See [data-model.md](data-model.md) 2026-09-05, "`Plan.valuation` doesn't check dtype or length."

**How to apply**: Any array the library hands to researcher code, and still needs itself afterward, should be handed over by **taking ownership first, then freezing it** — `copy()`, then set `writeable = False`; never freeze a view. Arrays the researcher hands back should likewise be snapshotted, not stored by reference. The test is one question: **whose memory is this**, not "is there a read-only flag on it."
