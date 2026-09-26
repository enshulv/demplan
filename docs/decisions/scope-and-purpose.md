# Scope and purpose

## 2026-08-28

### This library is shared academic infrastructure for democratic economic planning

**Decision**: This library is shared academic infrastructure for democratic and participatory economic planning, built from three parts:

1. Comparison infrastructure across mechanisms
2. Computational optimization infrastructure
3. A low-barrier wrapper for social-science researchers

Comparison is one component of this infrastructure, not its identity.

**Why**: The earlier framing set up a choice between a "neutral comparison platform" and a "parecon reference implementation." That framing itself drew the boundary in the wrong place.

"Neutral platform" draws the boundary around the type of coordination mechanism, so it only stays consistent if it also takes in markets. "parecon reference implementation" draws the boundary around a single school of thought, so other approaches in the same field can't get in. The boundary should sit on the **field**: democratic economic planning. This field holds several mutually incompatible approaches — participatory planning's iterative price adjustment, Cockshott's direct labor-time calculation, Kantorovich-style linear programming — and they need a shared data model and a shared set of metrics to talk to each other. Providing that is exactly the job of shared infrastructure.

The wrapper gets its own part because the target users are social-science researchers. [technology-choices.md](technology-choices.md) already set Python as the primary user interface on this basis; this entry raises it to the charter level: lowering the barrier to use is a delivery goal, not an implementation detail.

**How to apply**: To decide whether a feature belongs in the library, ask "does it serve the implementation, comparison, or usability of democratic planning mechanisms," not "is it neutral."

---

### The comparison boundary stops at democratic planning mechanisms

**Decision**: What `Evaluator` compares is limited to democratic planning mechanisms against each other, with the centralized optimal solution as the reference. The library does not implement market mechanisms. `Economy` carries no market-specific fields such as monetary income/expenditure or market-clearing residuals.

**Why**: The sole purpose of a market baseline is to answer the question "compared to what." Under the shared-infrastructure framing, that question already has two answers: compared to other mechanisms in the same field, and compared to the reference solution.

The reference solution is a harder benchmark than a market baseline — it is an upper bound computable on the same `Economy`. A market baseline instead requires committing to a whole set of behavioral assumptions (who is a price-taker, how clearing is defined, how expectations form), and that set of assumptions becomes the point of contention itself, shifting review from "is your mechanism good" to "is your market model fair."

At the field level, the consequence is fixed: `Economy` reserves no structure for markets, so field-level design work can start immediately.

**Alternatives rejected**: see [rejected/scope-and-purpose.md](rejected/scope-and-purpose.md)

**How to apply**: The core-abstraction test in [spec.md](../spec.md) (three mechanisms run on the same `Economy`) is unaffected — all three are democratic planning mechanisms. When a new mechanism comes up, judge first whether it belongs to this field. If it doesn't, it stays out of v1, and no field gets added for it.

---

### The library's responsibility boundary: it answers for the process, the researcher answers for the results

**Decision**: The library guarantees the reliability of the infrastructure — the data model, the invariant checks, the metric definitions, deterministic seeding, and provenance records. Which coordination procedure a researcher uses, and what conclusions they draw, are the researcher's own responsibility.

**Why**: The coordination procedure is the researcher's research content (see [coordination-procedures.md](coordination-procedures.md)). Since the library doesn't choose the mechanism for the researcher, it can't vouch for their conclusions either.

The analogy is a road: the paving crew answers for how smooth the road is; the driver answers for how fast they drive.

This needs to go in the public-facing documentation, because users need to know what the library does and doesn't guarantee for them. A blurred responsibility boundary has a concrete consequence in an academic setting: people will mistake "the library ran it" for "the library endorses it."

**How to apply**: Every sentence in the documentation that describes a guarantee should be able to answer "is this the library's half or the researcher's half."

---

### v1 value-proposition ranking

**Decision**: Ranked by "how much duplicated work it removes × how many people it helps," the library's value to researchers, in order, is:

1. **Data onboarding** — turning a real input-output table into a computable economy is weeks of specialized work that every researcher redoes, and it has nothing to do with the mechanism
2. **Invariant checking** — researchers don't write this themselves, because they'd need to already know a failure mode exists before it occurs to them
3. **Common-basis metrics** — the vehicle for comparability
4. **Provenance and output** — what lets others reproduce the work
5. **Parameter sweeps** — researchers can write a `for` loop themselves; lowest value

**Why**: This ranking overturns the earlier implicit assumption that the mechanism layer was the main battleground. The mechanism is the part researchers were always going to write themselves, so the library contributes least there; the data layer is pure duplicated work, contributing the most, and yet it's the easiest to overlook.

**Where this doesn't apply, stated plainly**: when a researcher just wants to try a mechanism once on a toy economy, doesn't care about comparing it to others, and doesn't intend to let anyone reproduce it, hand-rolled numpy is faster, and this library is a burden. This library wins when three things hold at once — real data, comparison against others, and reproducibility by others.

**How to apply**: v1's implementation order follows this ranking. See [progress.md](../progress.md).

---

### Monetary stocks and interaction topology are deferred past v1, but the identifier hook goes in now

**Decision**: `Economy` does not get monetary or debt-stock fields within v1, nor does it get an interaction topology among agents (network or spatial). Both are deferred past v1. **But Stage 0 must give every agent a stable identifier.**

**Why**: Both are things the library will eventually need — monetary stocks support credit-creation and deficit-financing experiments, and stock-flow-consistent accounting identities (see [invariants-and-metrics.md](invariants-and-metrics.md)); interaction topology supports ABM-based planning simulations, because ABM agents act on each other, not only in response to a central signal.

Deferring is safe, checked against the criteria set in [phasing-and-granularity.md](phasing-and-granularity.md): both are **added fields** or an **added structure indexed by agent identifier**; no existing scenario or method needs to change. Contrast this with the example that would actually be a rewrite — treating the A-matrix as ground truth in v1 is a rewrite because it changes what a row's identity is, not because it adds a field.

**The stable identifier is the one hook that must go in now**: without it, stocks have nothing to attach to later, and neither does a network edge. The cost is close to zero.

**One misreading to guard against**: the 2026-08-28 entry above, "The comparison boundary stops at democratic planning mechanisms," rules out "market-specific fields such as monetary income/expenditure or market-clearing residuals" because the library doesn't build a market baseline. **Monetary stocks are not covered by that exclusion** — they are a monetary arrangement internal to a planned economy (the Soviet Union's dual cash/non-cash currency, participatory planning's consumption credit, Cockshott's labor certificates), not a market-clearing mechanism. When it's time to add them, don't use that earlier decision as grounds for refusal.

---

## 2026-09-05

### Theory-neutral means transparent, not empty

**Decision**: The constraint "the base layer presupposes no economic theory" is implemented by **turning theory into an optional tool handed to the researcher, and stating whatever theory that tool carries in a place the researcher will actually read** — docstrings, READMEs, prefab class documentation — not only in `docs/decisions/`. The library must not smuggle a theory into a result, nor claim a commitment it doesn't actually impose. **Transparency ranks above brevity, performance, and interface elegance.**

**Why**: "Carrying no theory" isn't achievable. `Plan`'s field split, a prefab's closed-form solution, the reference solution's objective — every one of these carries a commitment. What's achievable is making the commitment visible. A researcher writing a paper from the library's output has to be able to say what assumptions the result depends on; a hidden assumption leaves the paper's conclusions unverifiable by reviewers or by anyone coming after.

This rule covers failure in both directions, and both were hit once on 2026-09-05:

- **Under-reporting**: when a utility index pointed at a third commodity kind, that demand changed the price path but never entered the plan record. Fixed by `consumer_demand`; see [data-model.md](data-model.md)
- **Over-claiming**: `CouncilModel`'s class documentation claimed that "public goods are priced per capita, and the stated plan is counted only once" as a substantive commitment. Testing showed the two halves cancel exactly, with no effect on any number the plan reports. The class documentation now states that it has no effect, and what would need to change to give it one; see [research/reproduction.md](../research/reproduction.md)

The second failure is worse: under-reporting withholds information; over-claiming supplies wrong information — the researcher would believe they had taken a position they hadn't.

**Alternatives rejected**:

- Reject inputs that would produce unrecorded consequences — that would mean the library ruling on whether the researcher's modeling choice is valid; see [data-model.md](data-model.md) 2026-09-05, alternatives rejected for "the utility-index column may point at any commodity kind"
- Document it only in `docs/` — researchers read docstrings and READMEs, not the decision log. The decision log answers "why was this decided," not "how is this disclosed to users"

**How to apply**: Before adding any prefab, objective, or optional tool, ask two questions — **what theory does it bring into the result? Is that stated somewhere the researcher will actually read?** Both need a satisfying answer before the work counts as done.

---

### Design decisions follow need, not the phase schedule

**Decision**: Phasing (v1/v2, Stage 0 through 6) is no longer a hard constraint on design. Whether a design belongs in the library is judged on its own costs and benefits, not vetoed with "that's v2's job" or "that's Stage 4's job." Phasing still orders **construction sequence**; it no longer decides **design scope**.

**Why**: The maintainer decided this explicitly on 2026-09-05. Two things were directly affected that day:

- Opening up commodity kinds had been judged as "roughly Stage 3's worth of work" and recommended against; lifting that restriction and re-evaluating produced a different conclusion — "opening it up on its own doesn't pay off; it has to be done together with kind attributes" — **the conclusion changed, and the reason it changed was technical, not a phasing question**
- Making `Plan`'s layering optional touches the data model shared with v2's council granularity. Phasing would have deferred it; need says do it now — Stage 2 is untouched, which is the cheapest window there is

**How to apply**: Before using phasing as grounds for refusal, work out the technical costs and benefits first. If they still don't add up, that's a technical conclusion. Refusing without doing that work, on the grounds that "it's the next phase's problem," doesn't hold.

**What this doesn't overturn**: the v1/v2 division of labor and "shared data model, not shared execution engine" in [phasing-and-granularity.md](phasing-and-granularity.md) still hold — that entry describes a difference in the two phases' objects and execution architecture, not a gate on design scope.

---

### The library's purpose is to help the field of democratic economic planning develop smoothly

**Decision**: The purpose of this library is to give democratic economic planning a reliable technical foundation, so the field develops more smoothly.

**Scope says what the library is; purpose says why it exists.** When both are within bounds but point to different priorities, purpose wins.

Purpose implies two criteria:

- **Success**: duplicated work across the field goes down. **Someone forking this library and doing it better counts as success, not failure.**
- **Failure**: this library becomes the sixth mutually incompatible implementation — one more data model in the field, with no less duplication than before.

**Why**: The maintainer decided this explicitly on 2026-09-05. Scope alone wasn't enough: it draws the boundary (what belongs in the library) but doesn't set priorities (which of two in-bounds things to do first). That round of work on 2026-09-05 hit four trade-offs that only purpose could settle, and purpose hadn't been written down at all, so each one had to be re-derived from scratch:

1. **The license rationale gets promoted.** [license.md](license.md) recorded the reason as "minimize friction to academic adoption" — that's instrumental. Under this purpose, MIT is part of the charter: a project whose purpose is to advance the field can't use its license to restrict how the field uses its output
2. **Interoperability goes from "nice to have" to a criterion in its own right.** See "Two corrections to the schedule" below
3. **The low-barrier wrapper needs an actual phase.** Same as above
4. **The rationale for prioritizing technical-representation work (opening up enums, joint products, an assumptions list) changed.** It isn't design fastidiousness — it's a barrier keeping the field out: an outside researcher's first-day problem isn't `Plan`'s layering, it's "my economy isn't Leontief, and your reference solution can't run it"

**Alternatives rejected**:

- Record only scope, not purpose — this round showed that isn't enough; all four trade-offs needed purpose to settle
- Write the purpose as "build the best library for this field" — that turns the criterion into "how much are we used," which gives the opposite answer to "duplication across the field goes down" on the question of forking

**Two corrections to the schedule** (these change the plan, not any recorded decision):

- **Interoperability goes from none to something.** As of 2026-09-05, `io.py` has exactly one function, `load_dep1ex`. It can't read any existing implementation's data, and it can't export anything any existing implementation can read. Stage 4's "long-format Parquet" is this library's own format, not interoperability. **As of today, this library's net effect on the field is one more data model** — exactly the state the failure criterion above describes
- **The low-barrier wrapper needs a phase.** The [three parts from 2026-08-28](#this-library-is-shared-academic-infrastructure-for-democratic-economic-planning) list it as the third part and say explicitly that "lowering the barrier to use is a delivery goal, not an implementation detail," but none of Stage 0 through 6 is it, and it's absent from the five-item v1 value-proposition ranking too. The charter has a pillar standing where the plan has no slot for it

⚠ The second point above **does not modify** the content of the 2026-08-28 value-proposition ranking — that is a historical fact. What it records is that the ranking missed the wrapper at the time; the fix is tracked in [progress.md](../progress.md).

**How to apply**: When deciding which of two things to do first, ask "**which one lets the next person in the field start working sooner**," not "which makes the library more complete." If the answer is the same either way, pick either; if it differs, the former wins.

**Related**: the size of the field, measured on GitHub on 2026-09-26: eight related public repositories (`pequod2`, `pequod-clj`, `pequod-cljs`, `pequod-plus`, `pe_ifb_compute`, `socialist_planning`, `EPOS`, `Economic-Planning`) have 70 stars combined, against Concordia's 1735 and Mesa's 3857. The repositories are listed in [research/README.md](../research/README.md) and [research/related-implementations.md](../research/related-implementations.md). (Corrected 2026-09-26 after a citation check: this said "research/related-implementations.md sized the field — six public repositories, about 60 stars combined, against Concordia's 1,669 and Mesa's 3,826"; the cited document contains none of these numbers, so they are replaced with values measured on GitHub on 2026-09-26.)
