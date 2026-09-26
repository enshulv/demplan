# Extension boundary

## 2026-08-28

### The mechanism layer is pluggable; the data model and invariants are fixed

(⚠ The fixed items were narrowed to two on 2026-08-30; see "Fixed items narrowed from four to two" at the end of this document. The rest of this entry still holds.)

**Decision**: `Procedure`, participant behavioral cores, economy generators and data loaders, constraint families, additional metrics, output backends, and visualization are all implemented as extensions. Four items are fixed and not exposed as extensions: the `Economy` data model, conservation-law and invariant checks, a set of core metrics, and determinism and seeding.

**Why**: This library carries a burden that a general-purpose harness project doesn't have — comparability across studies. Once the data model is pluggable, two results stop being comparable, and the goal of reducing fragmentation across studies fails right there.

The mechanism layer, on the other hand, has to be pluggable, because in economics, an extension boundary is roughly a theoretical-commitment boundary. Swapping a utility function isn't like swapping a logging component — it's a theoretical stance. Making these choices explicit turns the extension registry into a map of the theoretical landscape. The upstream implementation's problems are exactly these assumptions (fixed income, exogenous labor supply, single period), all buried in code where a reader can't see them.

**Alternatives rejected**:

- "Everything is a plugin" (deepseek-harness's philosophy) — reasonable as internal discipline, harmful as a public commitment to the target users. See the next entry

**How to apply**: To decide whether a slot should be an extension point, ask this — would a social-science researcher who doesn't write code want to swap it? If yes, it must be swappable from a scenario file, with a default. If no, but another school of mechanism thought would want to swap it, it's a third-tier extension, documented for implementers. If neither, it's core, and making it an extension only adds assembly overhead.

---

### The external surface follows three tiers of progressive disclosure

**Decision**:

1. Scenario files (TOML), zero code
2. A prefab plus parameter overrides, ten lines of Python
3. Implementing `Procedure` or a behavioral core from scratch

The first tier must be able to run an entire paper's worth of experiments on its own.

**Why**: Being pluggable isn't itself hard to understand — social-science researchers call `library()` in R every day. What discourages them is the configuration space — when everything is pluggable, nothing has a default, and the user faces dozens of slots with no way to tell which wrong value silently turns the result into garbage.

Concordia's answer is `prefabs`: fully composed internally, shipped externally as pre-assembled recipes.

**How to apply**: Each prefab corresponds to reproducing one piece of literature, named like `hahnel_2021` or `cockshott_cottrell`. A user starts from "I want to reproduce this paper," not from a blank assembly bench. Give opinionated defaults, not dozens of equally weighted options.

---

### The extension system carries assembly-time validation and a run manifest

**Decision**: Every extension declares what it needs and what it provides, and the whole assembly graph is validated before a run starts. Every run produces a run manifest recording the resolved extension graph, versions, and content hashes.

**Why**: Without these two things, being pluggable makes fragmentation worse instead of curing it.

Assembly-time validation: a long-running experiment shouldn't crash halfway through because "this `Procedure` needs a capital stock and your `Economy` doesn't have one." Rust's type system catches some of this, but that protection stops once the extension boundary crosses into Python.

Run manifest: without it, two researchers quietly swap in a different requirement core, and their results stop being comparable. A paper cites the manifest hash.

---

### The interface is functional; the implementation can mutate in place

**Decision**: `Procedure`'s signature takes the shape `fn step(state: State) -> State`, and the implementation mutates in place internally through an exclusive borrow.

**Why**: Pure functions give three things for free — replayability, snapshotting, and time-travel debugging. Property tests are also much easier to write against pure functions. The upstream implementation's TODO list says "add time-travelling," but its state lives behind a mutable reference, so it can't.

But pure doesn't mean copying the entire world every step. Using persistent data structures at 10⁷ entities would erase the entire performance advantage. Rust's ownership model is exactly what lets the signature be functional while the implementation stays in place.

---

### Fixed items narrowed from four to two

**Decision**: The items not exposed as extensions are now two: the `Economy` data model, and determinism and seeding.

Of the original four, "conservation-law and invariant checks" and "a set of core metrics" move out of the fixed layer, becoming optional tools and researcher-declared quantities respectively.

**Why**: Both carry theoretical commitments, conflicting with "theory-neutrality is a hard constraint on the base layer" established in [invariants-and-metrics.md](invariants-and-metrics.md). The presuppositions carried by the four invariants and the five metrics are listed one by one in that document.

This entry only changes the list of fixed items. The rest of the entry above — the mechanism layer must be pluggable, an extension boundary is roughly a theoretical-commitment boundary, and the criterion for deciding whether a slot should be an extension point — all still holds, and "an extension boundary is roughly a theoretical-commitment boundary" is exactly what this narrowing rests on.

**Partially narrowed**: This entry narrows the list of fixed items in "the mechanism layer is pluggable; the data model and invariants are fixed" from 2026-08-28.

**How to apply**: Comparability no longer depends on fixed metrics. It depends instead on "the same `Economy` plus recording discipline plus a declared comparison benchmark plus output raw enough to recompute after the fact."
