# Invariants and metrics

## 2026-08-28

### Theory-neutrality is a hard constraint on the base layer

**Decision**: The base layer must not presuppose any economic theory. Anything that carries a theoretical presupposition — an invariant, a metric, a behavioral equation — becomes an optional tool that researchers call as needed. The library can offer theory-laden tools for different schools to choose from, but it can't make any one of them an unavoidable precondition.

**Why**: This library serves **every school of thought** under the broad heading of democratic economic planning, and it eventually needs to accommodate complex economics and ABM-based planning simulation too. If the base layer is welded to one school's premises, the other schools can't get in, and the "shared academic infrastructure" framing fails on the spot.

[extension-boundary.md](extension-boundary.md), in "The mechanism layer is pluggable; the data model and invariants are fixed", already said "in economics, the extension boundary is roughly the theoretical-commitment boundary." This entry promotes that from an extension-boundary criterion to a hard constraint on the base layer.

**How to apply**: Before adding anything to the fixed layer, ask "which school would disagree with this." If there's an answer, it can't be fixed — it has to be a tool.

---

### All four invariants become optional tools

**Decision**: Material balance, budget identity, non-negativity, and price homogeneity of degree zero are no longer globally enforced. They are optional constraints in a toolbox, and researchers turn them on as needed. The toolbox will grow later.

**Why**: On review, none of the four is neutral.

| Invariant | Theoretical presupposition it carries | When it fails to hold |
|---|---|---|
| Budget identity | Hard budget constraint | Credit creation, deficit financing, transfer payments |
| Price homogeneity of degree zero | Money is neutral; prices are purely a real-side intermediary | Once money or nominal-denominated debt enters; when different producing units' prices don't move by the same proportion, "scale every price by λ" isn't even a symmetry of the system |
| Non-negativity | Every output is a "good" | Waste and emissions — a bad with a negative price is standard practice in environmental economics, and v1's scope explicitly names an emissions extension |
| Material balance | The period is closed, with no cross-period inventory | `Economy` has been multi-period (T periods) from day one; with stocks, this period's consumption can exceed this period's output |

Price homogeneity of degree zero matters most: it is a substantive Ricardian claim, not an arithmetic property.

`spec.md` used to say "the check is enforced globally; a failing result is flagged invalid and withheld rather than output as usual." That was written when the coordination procedure was still under the library's control. Now that the coordination procedure belongs to the researcher, that sentence has three problems: intermediate output during exploration necessarily violates invariants, so refusing to output it across the board would drive the researcher away; "flagged invalid" (transparency) and "withheld" (gatekeeping) were bundled together, and the latter conflicts with the responsibility boundary; and, per the table above, all four carry theoretical commitments.

**Alternatives rejected**: see [rejected/invariants-and-metrics.md](rejected/invariants-and-metrics.md)

**How to apply**: As a researcher adds constraints one at a time, the experiment gets progressively stricter — that is itself a form of controlling for variables.

---

### Theoretical commitment belongs to the prefab, not the library

**Decision**: The library sets no global default constraint set. Which invariants get turned on when reproducing a given piece of literature is declared by the prefab for that literature. A researcher building from scratch chooses for themselves.

**Why**: Turning everything on by default ships one school's theory out of the box; turning everything off by default leaves a new user with no protection at all. The way out is to give theoretical commitment a clear owner — **the paper, not the library**.

[extension-boundary.md](extension-boundary.md), in "The external surface follows three tiers of progressive disclosure", already decided that prefabs are named after the literature they reproduce (`hahnel_2020_slides`). Given that, "Hahnel 2020 assumes the budget identity holds" is that paper's assumption; the library is just relaying it faithfully.

**How to apply**: Every prefab lists, explicitly, which constraint set it enables, with the rationale pointing at the specific place in the literature.

---

### Residuals are always computed when computable, and named neutrally

**Decision**: The library always computes each constraint's residual and writes it to the output, whether or not the researcher has set it as a constraint. Two limits apply: it isn't computed where the mechanism has no definition for it (direct labor-time calculation has no prices, so price homogeneity of degree zero is N/A for it, not 0 — and the output must be able to distinguish N/A from 0); and naming is always neutral — call it "budget residual," not "budget-identity violation."

**Why**: What the library computes is comparable (a shared definition); what researchers report on their own isn't. Always computing the residual guarantees the output always has a comparable number in it.

Neutral naming matters because the same number means something different to different people: a 15% budget residual is a bug to one researcher and **the object of study itself** to someone running a credit-creation experiment. The library supplies numbers, not verdicts — a verdict is theory too.

**How to apply**: Go back through every word in the output and API that describes a constraint's result, and check whether it is smuggling in a judgment.

---

### No fixed core metrics; the comparison benchmark is declared by the researcher

**Decision**: The library does not fix a set of core metrics. Which quantity a comparison uses as its benchmark is declared by the researcher at comparison time, and that declaration goes into the run manifest. The library provides tools for computing various quantities; it doesn't decide which one is central.

**Why**: Comparison isn't something the library does — it's something the researcher does with the library's tools. And comparison presupposes a shared standard between both sides, and that standard can only be chosen by whoever is doing the comparing — comparing by market terms against comparing by labor terms was never going to work in the first place.

The five core metrics originally listed each carried a theory too: "welfare under a given social welfare function" already commits to a social-welfare-function form; "labor cost" presupposes labor is the relevant cost measure, whereas the Kantorovich school wants the objective's value; "emissions against a cap" presupposes ecological constraints take the form of a cap.

**Supersedes**: This entry narrows [extension-boundary.md](extension-boundary.md) 2026-08-28, "the mechanism layer is pluggable; the data model and invariants are fixed," down from four fixed items to two: the `Economy` data model, and determinism and seeding.

**How to apply**: `Evaluator`'s job changes from "produce a comparable metric" to "given a plan and a declared benchmark, compute that quantity."

---

### Comparability rests on raw output, not on agreed-upon metrics in advance

(⚠ The statement of the comparability anchor was narrowed on 2026-08-30 to "the same initial economy plus the same evolution rule"; see [evolution-rule.md](evolution-rule.md). The rest of this entry is unchanged.)

**Decision**: Comparability rests on three things — the same `Economy`, the same recording discipline, and a declared comparison benchmark in the manifest. Plus one hard requirement on output: **output must be raw enough to let anyone recompute any metric after the fact**.

Output has three tiers:

| Output | Default | Purpose |
|---|---|---|
| Full final allocation (each producing unit's output, each input quantity, prices or labor values, per period) | Always produced | Comparability |
| Process summary (round count, converged or not, wall-clock time) | Always produced | The mechanism-efficiency comparison axis |
| Per-round trajectory | Only with `plan_of` supplied | Reproduction and diagnosis; large |

**Why**: Once the comparison benchmark is free to vary, one paper comparing emissions and another comparing labor productivity lose comparability with each other. The way out isn't going back to fixed metrics — it's **keeping the output raw enough that anyone can measure anyone's results with any yardstick afterward**.

This is stronger than fixed metrics: fixed metrics only guarantee everyone uses the same yardstick; being able to recompute after the fact guarantees any yardstick can measure anyone's results.

Comparability needs "final allocation plus a small process summary" — in a comparison like "you took 500 rounds, I took 200, and output came out about the same," the round count is a process quantity and exactly the point. The full per-round trajectory is for reproduction and diagnosis, not for comparability.

**How to apply**: Stage 4's acceptance test is "can any metric be reconstructed from the output." Storing only summaries doesn't pass.

---

### Splitting SFC: the accounting identity goes in the toolbox, the behavioral equations belong to the researcher

**Decision**: The post-Keynesian stock-flow-consistent (SFC) framework is handled in two halves. The accounting-discipline half — every stock is the accumulation of flows, every flow has a source and a destination, transaction-flow matrices sum to zero across rows and columns — becomes an optional conservation law in the invariant toolbox, alongside material balance. Godley-Lavoie's consumption functions and portfolio-choice equations belong to the mechanism layer, to the researcher; they don't go in the base layer.

**Why**: The core of SFC is accounting discipline, not theory — it conserves financial quantities rather than real ones, the same category as material balance.

Money isn't foreign to this field — it's a design variable: parecon has consumption credit, Cockshott's labor certificates are an explicit monetary design (non-circulating labor certificates), and Allende's Chile was a monetary economy. "Where does purchasing power for consumption come from, and where does unspent income go" needs an answer in every democratic planning proposal.

**How to apply**: The criterion is — **anything that can be stated as a conservation law can go in the toolbox; anything that needs a behavioral equation stays with the researcher**. If SFC ever gets imported as "a whole model," it will drag post-Keynesian behavioral assumptions into the base layer, and that is overreach.

This entry needs the data model to support a monetary-stock field, deferred past v1 along with interaction topology; see [scope-and-purpose.md](scope-and-purpose.md).

---

## 2026-09-05

### Price homogeneity of degree zero is a property test, not a residual

**Decision**: "Residuals are always computed" only covers material balance, budget identity, and non-negativity — all three can be computed from a single run's output. Price homogeneity of degree zero becomes a property-test tool, `check_homogeneity`, shaped the same way as `check_determinism`: scale the coordination procedure's initial valuation quantities proportionally, rerun, and compare the physical layer between the two runs. It only works on coordination procedures that expose an "initial valuation quantity" parameter. Implementation is deferred to Stage 2.

**Why**: Homogeneity is a property of the coordination procedure, not a property of a single plan's bookkeeping. A single plan's output has no quantity called a "homogeneity residual"; putting it in the same rule as the other three would get implementation stuck.

**Partially narrowed**: This entry narrows the scope of "residuals are always computed when computable, and named neutrally" from 2026-08-28. That entry's rules for the other three are unchanged.

---

### The reference solution is a tool parameterized by an objective

**Decision**: The reference solution is defined as `reference_solution(economy, objective) -> Plan`. The objective is declared by the researcher and recorded in the run manifest. The library ships several objectives as options; it sets no default.

**Why**: `spec.md` says the comparison benchmark is the centralized optimal reference solution, but "optimal" was never defined against a target. This document's 2026-08-28 entry, "no fixed core metrics," already established that the objective is a theoretical commitment. The two don't conflict — the resolution is to treat the objective as a parameter — but that had never been written down, and whoever implements Stage 5 would otherwise invent one.

**How to apply**: Stage 1.5's minimal reference solution is a linear program under Leontief technology, with the objective chosen from the library's built-in options and recorded in the manifest.
