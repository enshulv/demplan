# Comparison and presentation

> "Preset comparison items" refers to the set the library ships with, computable across every mechanism; "difference presentation" refers to laying these quantities side by side across two runs.

## 2026-09-05

### The library doesn't score; it only presents differences. What gets compared is set by presets plus researcher configuration

**Decision**: The library doesn't score plans, and doesn't rank them. It does four things:

1. Compute and present a set of **preset comparison items** — quantities that necessarily exist across every model and every theory
2. Let researchers **configure** these presets
3. Provide an **extension point** for researchers to add their own comparison items
4. **Leave a value blank** wherever one side has no definition for it, with blank kept distinguishable from zero

**The library doesn't accept requests to "implement a non-preset item for me."** If a researcher wants a quantity that isn't in the presets, that's their own work to do, including modifying the competing mechanism's implementation so it produces that quantity too. An item gets promoted into the library only once demand for it is strong enough.

**Why**: This isn't a new direction — it's aligning a leftover phrase in [spec.md](../spec.md) with the rest of the project. The spec originally said the three mechanisms are "**scored by the same set of metric functions**," while the same spec also says "the library supplies numbers, not verdicts," and [invariants-and-metrics.md](invariants-and-metrics.md) says "no fixed core metrics; the comparison benchmark is declared by the researcher." **"Scoring" implies the library holds a yardstick; the other two statements say plainly that it doesn't.**

The shape "presets plus leaving undefined values blank" was already set — see spec.md's "residuals are always computed, named neutrally": material balance, budget, and non-negativity are all always computed and written to output whether or not they're set as constraints, except where the mechanism has no definition for them, with "N/A, not 0, and the output must distinguish them" stated explicitly. This entry generalizes that from residuals to the whole comparison surface, and adds two things: configurability, and an extension point.

**Alternatives rejected**:

- The library defines a fixed set of core metrics and ranks by them — a verdict is theory too, conflicting with the two statements in invariants-and-metrics.md
- Only guarantee tidy output formatting, leaving all differencing to the researcher — this gives the library no way to actually deliver on "present differences faithfully and without bias," and nothing would stop a researcher from subtracting an allocated plan from a stated plan

**How to apply**: Before adding any candidate comparison item, ask first: **does it necessarily exist across every mechanism?** If not, it isn't a preset — it goes through the extension point.

---

### "Efficiency" has no fixed definition

**Decision**: The library reports wall-clock time (`RunSummary.wall_seconds`), round count (`rounds`, `None` for methods that don't iterate), and the three states converged/diverged/undetermined, as-is — it does **not** define "efficiency." The definition is declared by the researcher at comparison time.

**Why**: Wall-clock time measures the implementation, not the mechanism. Measured on 2026-09-05: the same code with and without divergence detection differs by 8% to 14%, and machine load alone differs by 45%. Treating that as efficiency would read implementation differences as mechanism differences. Round count isn't universal either — a non-iterative method has no round count.

Neither quantity is one that "necessarily exists across every model," so neither qualifies as a preset efficiency definition. This is consistent with "no fixed core metrics" in [invariants-and-metrics.md](invariants-and-metrics.md).

---

### Difference presentation is a thin component, not a plain file format

**Decision**: The library provides a component that takes two runs and produces a diff. It only handles presets, blanks, configuration, and the extension point — it isn't a general-purpose comparison engine, and it doesn't render a verdict.

**Why**: Computing presets, leaving them blank, configuring them, and extending them can't be done just by "writing tidy output and letting the researcher diff it themselves." And the commitment to being "faithful and unbiased" requires the library to be able to **refuse** a comparison that shouldn't be made — when both sides are non-blank but aren't the same kind of quantity (a stated plan versus an allocated plan), subtracting element-wise still returns a number, and that number is itself a biased presentation.

**How to apply**: When the component finds the two sides don't share the same semantic identity, it **refuses to subtract and states why** — it doesn't hand back a number.
