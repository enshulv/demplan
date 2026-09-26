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

**Partially superseded**: The signature now takes a `seed`; see 2026-09-26, "Shape of the multi-period interface."

---

### Errors in the evolution rule are more dangerous than errors in the coordination procedure; cross-period invariants offset that risk

**Decision**: The toolbox gains a set of cross-period invariants: cumulative resource use not exceeding the initial stock, non-negative capital stock, population conservation, and a stock equaling last period's stock plus this period's net flow. Like the single-period ones, these are **off by default**, enabled as needed.

**Why**: When the coordination procedure computes something wrong, this period's plan is wrong, and a single-period invariant may catch it. When the evolution rule computes something wrong, what's wrong is **next period's problem statement**, and next period's coordination procedure will solve that wrong problem into a perfectly self-consistent answer — every invariant passes, the plan is fully feasible, and the chart looks fine.

Concretely: if a capital-accumulation formula drops a depreciation-rate factor, period 2's capacity runs 5% high, and period 2's plan is entirely feasible, violating not a single invariant; period 3 runs 10% high, period 5 runs 30% high. **The error grows with each period, silently the whole way.** This is the worst version of the failure mode recorded in [performance-architecture.md](performance-architecture.md), because every period repairs itself into a state that looks correct.

Cross-period invariants are exactly the probe for this class of error: a missing depreciation factor violates the identity "stock equals last period's stock plus investment minus depreciation." And **cross-period invariants only exist when the library can see the whole trajectory** — if the researcher writes the loop themselves outside the library, and the library checks each period independently, nobody is watching the cross-period constraint. The danger comes from crossing periods, so the offsetting tool only exists from a cross-period vantage point too.

Off by default matches the single-period behavior (`invariants-and-metrics.md`'s theory-neutrality principle applies to the cross-period set too: "how capital depreciates" is theory as well).

**How to apply**: Documentation needs to call out the cross-period set's property specifically — a single-period invariant violation is visible to the researcher on the spot; a cross-period violation isn't.

**Partially narrowed**: "Off by default" becomes "residuals computed by default, no constraints by default"; see 2026-09-26, "Cross-period residuals are computed by default."

---

### The comparability anchor is the initial economy plus the same evolution rule

**Decision**: Under multi-period rolling, the statement of comparability changes from "the same `Economy`" to **"the same initial economy, plus the same evolution rule."** When the two sides use different evolution rules, the comparison is between "mechanism plus evolution rule" combinations, not pure mechanisms — and that has to be visible in the manifest.

**Why**: Under multi-period rolling, only `Economy₀` is shared; after that, the paths diverge — two mechanisms lead to different accumulation paths, and `Economy₁` is already different between them. That divergence is itself one of the things being compared ("your mechanism yields higher capacity after five periods"), so it isn't a defect.

But left unstated, a reader will attribute all the difference to the coordination mechanism. Reproduction is worse: a person reproducing the work doesn't know which evolution rule the original author used, and the trajectory they rebuild will come out completely different — **while both trajectories look correct**, every period feasible, every invariant passing. They'll conclude the difference is in the mechanism implementation, when it's entirely in the evolution rule.

**How to apply**: In the manifest, the evolution rule's provenance gets **the same treatment** as the coordination procedure's; the documentation calls this out separately.

**Partially narrowed**: This entry narrows the statement of the comparability anchor in [invariants-and-metrics.md](invariants-and-metrics.md) 2026-08-28, "comparability rests on raw output." The rest of that entry — output must be raw enough to recompute any metric after the fact — is unchanged.

## 2026-09-26

### Shape of the multi-period interface: the evolution rule receives a seed, and a function slot builds the next period's coordination procedure

**Decision**: The signatures of the multi-period tool are

```
run_periods(economy, procedure, periods, seed, advance=None, next_procedure=None, check_period=True)
advance(economy, plan, seed) -> Economy
next_procedure(previous_plan) -> Procedure
```

- The evolution rule **gets one more parameter, `seed`**, assigned by the library
- Information from the previous period reaches the next period's coordination procedure through the function slot `next_procedure`: at the start of each period, it builds a new coordination procedure from the previous period's plan. Without it, every period reuses the same coordination procedure, which means a cold start every period; this is the default that contains no theory
- The evolution rule is called only between two periods, `periods − 1` times in total; nothing is advanced after the last period
- The output keeps every period's economy, plan and summary
- The coordination procedure interface `solve(economy, seed)` does not change at all

**Why**:

- **Seed**: an evolution rule can be random (the warm start in Hahnel 2021 randomly perturbs the production and utility exponents). If the evolution rule object holds its own random numbers, running the same object a second time continues the previous sequence, the same input gives a different trajectory, and the library cannot see it. With the library assigning seeds, one master seed determines the whole trajectory. The seed serves reproduction among researchers who use this library, not reproduction of research that predates it — the random numbers of that research can no longer be recovered
- **Function slot**: the maintainer's principle is that the library defines only the slot's interface; how the plugged-in code is written is the researcher's responsibility, and the researcher publishes its source. Of the four channels it costs the least: it does not touch the principle that the interface has only one layer, it does not touch the data model (prices do not go into `Economy`), a new object each period rules out state leaking across periods by construction, and static multi-period runs are a special case of it
- **Keep every economy**: the arrays of `Economy` are read-only views, and `dataclasses.replace` shares unchanged columns with the previous period, so each extra period kept only takes memory for the changed columns (about 50 MB for Hahnel's two-year experiment). Without them, computing a metric that depends on the economy afterward means rerunning the whole trajectory

**Alternatives rejected**:
- Write the previous period's prices into the `extra` of `Economy` and have the coordination procedure read them from the economy — the data model would carry the state of price-based mechanisms, at the edge of the theory-neutrality principle; it also has the evolution rule write the coordination procedure's starting point, which mixes two responsibilities
- `solve(economy, seed, previous=None)` — directly overturns the principle that the interface has only one layer; every researcher's coordination procedure would have to handle the new parameter
- The coordination procedure object carries cross-period memory — reusing the object leaks state, and the same input gives different results
- The evolution rule carries its own random number generator — same reason as above
- Keep only a hash of each period's economy by default — saves memory, but computing metrics afterward means rerunning, and every researcher pays that time cost again and again

**How to apply**: A mechanism that needs to pass information across periods provides its own `next_procedure` function in its prefab, puts the quantities to pass into the plan (`valuation` or `extra`), and has the function read them from the plan. The library does not know, and does not need to know, what is passed.

**Partially supersedes**: In 2026-08-30, "The evolution rule belongs to the researcher, and is a tool parameter, not a core abstraction," the signature `advance(economy, plan)` now takes a `seed`, and the parameter list of `run_periods` is completed. The rest of that entry (it belongs to the researcher, it is a tool parameter, the researcher chooses static or rolling) is unchanged.

---

### Multi-period seed layout: one prefix-stable sequence, even and odd positions for the coordination procedure and the evolution rule

**Decision**: `split_seed(seed, 2T)` gives `w₀ … w₂T₋₁`. The coordination procedure of period i (counting from 0) uses `w₂ᵢ`, and the evolution rule that produces the economy of period i+1 uses `w₂ᵢ₊₁`. The last position is reserved and unused. Period 1 also uses a derived seed, not the master seed directly.

**Why**: The derivation method already exists in the library (SplitMix64); only the layout needs deciding, and once a layout is released it cannot change — changing it would make everyone's published multi-period results impossible to rerun. This layout guarantees three things at once: the same master seed gives the same trajectory; going from T periods to more leaves the first T periods unchanged (`split_seed` is prefix-stable); and when a researcher swaps a deterministic evolution rule for a random one, the seeds the coordination procedure receives do not change (the evolution rule's position is occupied every period).

**Alternatives rejected**:
- The coordination procedure of period 1 uses the master seed directly — this would make a single-period run and period 1 of a multi-period run give the same result, but the rule would no longer be uniform across periods. The maintainer accepted "all derived seeds" from the list of defaults

---

### Soft check on the period number

**Decision**: When the economy returned by the evolution rule has a `period` that is not the previous one plus one, a `PeriodWarning` is issued. It does not raise and does not correct the value; `check_period=False` turns it off. Static multi-period runs are not checked.

**Why**: A researcher writing an evolution rule cares about how the technology changes and can easily forget to increment the period; if they forget, the periods cannot be told apart in the output, and nothing reports it. Raising an error would block legitimate experiments such as "go back one period and start again," and having the library correct the value would make the decision for the researcher. The period is only a number and carries no theory, so the library only warns.

**Alternatives rejected**:
- The library sets the period itself — blocks special experiments
- The library validates and raises — same as above; special experiments would need an extra switch to turn it off
- Leave it entirely to the researcher, the library does nothing — nobody warns when it is forgotten

---

### Cross-period residuals are computed by default; the evolution rule declares which ones are constraints

**Decision**: The cross-period set continues the single-period practice of "always compute residuals, name them neutrally":

- The two that can be computed from fixed fields — cumulative resource use against the initial endowment, and the change in the number of consumer units — are **computed by default and written to the output** in multi-period runs, with no judgment of right or wrong, and can be turned off
- The two that cannot be computed — non-negative capital stock, and a stock equal to the prior period's stock plus net flow — are marked N/A with the reason (the data model has neither concept)
- Which of them constrain a given model is declared by its evolution rule or prefab; the library sets no global default
- The output includes a coverage table that states, for each one, "computed / N/A and why / declared a constraint"

This is done in Stage 2 (invariant toolbox) together with the single-period residuals, not in the multi-period interface work.

**Why**: The maintainer proposed deciding automatically which checks apply based on what the researcher implemented. The structure can decide whether a residual **can be computed**, but not whether it **should hold**: the same `endowment` field is a yearly flow in Hahnel's model (1000 each year; using it up does not affect next year), and a depletable stock in a model that studies non-renewable resources. Deciding violations automatically from the structure would choose a theory for the researcher, which conflicts with the theory-neutrality principle; computing the number without a verdict avoids this. It goes into Stage 2 because the single-period residuals are not implemented yet, and the cross-period set reuses their computation and output format.

**Alternatives rejected**:
- Turn them on as constraints automatically from the structure — Hahnel's second year would always be reported as a violation, though his model is not wrong
- Do it now together with the multi-period interface — the single-period residuals are not implemented yet, so the order would be reversed; Hahnel uses none of them, so there is no real use case to validate it

**Partially narrowed**: In 2026-08-30, "Errors in the evolution rule are more dangerous than errors in the coordination procedure; cross-period invariants offset that risk," the statement "off by default" is narrowed to "residuals computed by default, no constraints by default." The reasoning of that entry and its use as a probe are unchanged.
