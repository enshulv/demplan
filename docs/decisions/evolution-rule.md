# Evolution rule

> "Evolution rule" corresponds to `advance` in the code: what the economy becomes after this period's plan executes.
> **It is not called an "iteration rule"** — in this project, "iteration" already refers specifically to the rounds inside a single `solve` call (convergence round count, cold start, warm start). Mixing the two would make "the evolution rule is wrong" and "the iteration round count doesn't converge" read as the same kind of problem.

## 2026-08-30

### The evolution rule belongs to the researcher, and is a tool parameter, not a core abstraction

**Decision**: `advance(economy, plan) -> Economy` is supplied by the researcher, and carries capital accumulation, technological progress, resource depletion, and population change. It's a parameter to the multi-period driver tool, **not the fifth row of the core-abstraction table**:

```
run_periods(economy, procedure, advance=..., T=5)
```

Anyone not doing multi-period work never sees this concept at all.

**Why**: It belongs to the researcher because it carries theory — how investment turns into capacity (Harrod-Domar? endogenous growth?), how technology progresses (a learning curve? R&D spending?) — every version of this is a school's own claim. It's handled the same way as proposal behavior: the library provides tools, and doesn't hard-code one.

It isn't listed as a core abstraction because it's structurally the same as `iterate`. `iterate`'s value isn't running the loop for the researcher (they could write the same `for` loop themselves) — it's **letting the library see that this is a single iteration**, which is what makes round counts and trajectories exist at all. The evolution rule works the same way: a researcher can write their own multi-period loop outside the library, but then the library sees T unrelated runs, not the fact that they belong to one trajectory — and cross-period provenance, multi-period output structure, and cross-period invariants all stop existing.

**How to apply**: Static versus rolling is the researcher's choice — not passing an evolution rule means static, passing one means rolling. The library supports both, the same kind of optionality as "no `plan_of` means only round counts."

---

### Errors in the evolution rule are more dangerous than errors in the coordination procedure; cross-period invariants offset that risk

**Decision**: The toolbox gains a set of cross-period invariants: cumulative resource use not exceeding the initial stock, non-negative capital stock, population conservation, and a stock equaling last period's stock plus this period's net flow. Like the single-period ones, these are **off by default**, enabled as needed.

**Why**: When the coordination procedure computes something wrong, this period's plan is wrong, and a single-period invariant may catch it. When the evolution rule computes something wrong, what's wrong is **next period's problem statement**, and next period's coordination procedure will solve that wrong problem into a perfectly self-consistent answer — every invariant passes, the plan is fully feasible, and the chart looks fine.

Concretely: if a capital-accumulation formula drops a depreciation-rate factor, period 2's capacity runs 5% high, and period 2's plan is entirely feasible, violating not a single invariant; period 3 runs 10% high, period 5 runs 30% high. **The error grows with each period, silently the whole way.** This is the worst version of the failure mode recorded in [performance-architecture.md](performance-architecture.md), because every period repairs itself into a state that looks correct.

Cross-period invariants are exactly the probe for this class of error: a missing depreciation factor violates the identity "stock equals last period's stock plus investment minus depreciation." And **cross-period invariants only exist when the library can see the whole trajectory** — if the researcher writes the loop themselves outside the library, and the library checks each period independently, nobody is watching the cross-period constraint. The danger comes from crossing periods, so the offsetting tool only exists from a cross-period vantage point too.

Off by default matches the single-period behavior (`invariants-and-metrics.md`'s theory-neutrality principle applies to the cross-period set too: "how capital depreciates" is theory as well).

**How to apply**: Documentation needs to call out the cross-period set's property specifically — a single-period invariant violation is visible to the researcher on the spot; a cross-period violation isn't.

---

### The comparability anchor is the initial economy plus the same evolution rule

**Decision**: Under multi-period rolling, the statement of comparability changes from "the same `Economy`" to **"the same initial economy, plus the same evolution rule."** When the two sides use different evolution rules, the comparison is between "mechanism plus evolution rule" combinations, not pure mechanisms — and that has to be visible in the manifest.

**Why**: Under multi-period rolling, only `Economy₀` is shared; after that, the paths diverge — two mechanisms lead to different accumulation paths, and `Economy₁` is already different between them. That divergence is itself one of the things being compared ("your mechanism yields higher capacity after five periods"), so it isn't a defect.

But left unstated, a reader will attribute all the difference to the coordination mechanism. Reproduction is worse: a person reproducing the work doesn't know which evolution rule the original author used, and the trajectory they rebuild will come out completely different — **while both trajectories look correct**, every period feasible, every invariant passing. They'll conclude the difference is in the mechanism implementation, when it's entirely in the evolution rule.

**How to apply**: In the manifest, the evolution rule's provenance gets **the same treatment** as the coordination procedure's; the documentation calls this out separately.

**Partially narrowed**: This entry narrows the statement of the comparability anchor in [invariants-and-metrics.md](invariants-and-metrics.md) 2026-08-28, "comparability rests on raw output." The rest of that entry — output must be raw enough to recompute any metric after the fact — is unchanged.
