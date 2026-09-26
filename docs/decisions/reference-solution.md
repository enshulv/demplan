# Reference solution

> "Reference solution" corresponds to `reference_solution` and `ReferenceProcedure` in the code; "objective" corresponds to `Objective`.
> The definition itself (parameterized by the objective) is in [invariants-and-metrics.md](invariants-and-metrics.md) 2026-09-05. This document records implementation-layer decisions.

## 2026-09-05

### The objective fixes both the weights and the allocation; both are theoretical commitments

**Decision**: The `Objective` protocol has two methods: `weights(economy)` gives the weights on final consumption, and `allocate(economy, aggregate)` splits the aggregate final consumption computed by the linear program across consumer units and public goods. The library ships two objectives: `MaximizeWeightedConsumption` (equal split) and `MinimizeLabor` (minimize total labor given a final-consumption lower bound, also equal split). Both document, in their docstrings, exactly what they each commit to.

**Why**: `Plan`'s consumption side is "who gets how much"; the linear program can only compute the aggregate total. How that total gets split is a theory of allocation, a commitment just like the weights are, so it belongs in the objective object rather than being hardwired into the solver.

**Alternatives rejected**:

- Have the solver assign the aggregate to a single representative consumer unit — this would require a special case in `Plan`'s shape, and it hides the allocation theory inside the implementation.
- Allow `targets` to fall on intermediate goods or on labor — those quantities have no place on `Plan`'s consumption side, and material balance can't be recovered from the plan. This now errors instead.

---

### Shadow prices come from the dual variables, unclamped

**Decision**: `valuation["shadow_price"]` takes the dual variable of the commodity constraint, zeroing out only noise below 1e-12 — no `max(x, 0)` clamp. The final-consumption lower bound is implemented as a variable bound, not added to the constraint matrix.

**Why**: Clamping would turn "shadow prices are non-negative" into a test that's true by construction — a sign error would still pass green. Putting the lower bound into the constraint matrix would add extra components to the dual vector that don't correspond to any commodity, breaking the "one commodity, one shadow price" correspondence.

---

### `linearize` is a tool carrying theoretical commitments; idle units get all-zero coefficients

**Decision**: `linearize(economy, plan)` converts each producing unit's technology to Leontief, with coefficients taken as `input_use / output`. A unit with zero output gets all-zero coefficients; the docstring notes that in the reference solution this amounts to "something from nothing," and the linear program becomes unbounded if weighted. Negative outputs and coefficients that overflow are rejected.

**Why**: Treating the input ratios a mechanism happened to choose as a fixed technology is a commitment, not a neutral transformation. There are two ways to handle idle units (all-zero or drop them); all-zero was chosen because it doesn't change the unit table's row identity — dropping them is left to the caller's responsibility. On dep1ex, the minimum output is 0.1067, so this doesn't trigger.

---

### The well-formedness of a declared objective is checked by the library, independent of the optional invariants

**Decision**: `MinimizeLabor` rejects a negative final-consumption lower bound; an objective that carries only `final_demand_lower_bound` or only `minimize_kind`, but not both, makes `reference_solution` error rather than silently treating it as a maximization. These two checks are about the well-formedness of a **declaration**, not a plan invariant, so they are not subject to the "non-negativity is an optional constraint" restriction.

**Why**: The second round of adversarial review found that a negative lower bound makes that commodity's final consumption negative, using its own lower bound to cover its own input, and the minimum labor value gets reported as 6 instead of 12 while `status` still reads `optimal`; a half-declared, self-written objective gets treated as a maximization with all-zero weights, returning an all-zero solution with `status` `optimal`. The reference solution is the scoring baseline for the entire library — if it's silently wrong, nothing catches it.

**How to apply**: The contract for identifying a minimization objective by its attributes is already written into the spec. The case of a researcher-written objective was patched on 2026-09-05, see the next entry.

---

### scipy is a runtime dependency

**Decision**: `scipy` moves from a dev dependency to `[project] dependencies`.

**Why**: The reference solution is a public feature of the library, not test infrastructure.

---

### The abstract criterion's first test

**Decision**: Use the dep1ex case in `tests/test_reference.py` as the first test of the spec's abstract criterion: the parecon plan and the reference solution both run on the same linearized `Economy`, scored through the same set of derived accessors. Numbers from this local run, 2026-09-05: weighted final consumption 1.525e8 vs. 2.158e8, total labor used 9.64e4 vs. 1.00e5, reference solution 4.43 seconds.

**Why**: The criterion requires three mechanisms to run on the same `Economy`. This run only has two, and the parecon plan runs on a Cobb-Douglas economy while the reference solution runs on its linearization — **not the same `Economy`**, only the same set of units, commodities, and consumer units. The criterion is only partially tested; a full test awaits the Cockshott labor-time mechanism (Stage 5).

---

## 2026-09-05

### The objective's declaration checks live at the reference-solution layer, independent of any specific objective class

**Decision**: As soon as `reference_solution` reads an objective as a minimization by its attributes, it applies two checks to its `final_demand_lower_bound`: non-negativity, and that it falls only on consumable commodities. `MinimizeLabor`'s own two checks stay in place — an early failure point is closer to where the researcher made the mistake — but the reference-solution layer no longer depends on them.

**Covers**: The "to be added next round" item left open in the How to apply of the 2026-09-05 decision "The well-formedness of a declared objective is checked by the library"; that decision itself is unchanged.

**Why**: `reference_solution` identifies an objective by its attributes (`final_demand_lower_bound` plus `minimize_kind`); a researcher writing his own object with the same attributes takes the same solve path, and neither check applies to it. Tested on a three-commodity economy:

- Negative lower bound, `targets [6, -3, 0]`: the minimum labor value gets reported as 6 instead of 12, commodity 1 is produced at 0 but consumed at 3, and `status` still reads `"optimal"`.
- Lower bound falling on an intermediate good, `targets [6, 3, 0]`: 6 extra units of labor produce 6 extra units of an intermediate good, while the plan's own `final_use` records 0 for it — the quantity being optimized doesn't exist in the plan's own output.

The reference solution is the scoring baseline for the entire library — if it's silently wrong, nothing catches it.

**How to apply**: Wherever an interface "identifies by attributes," the check must live at the layer doing the identification, not inside the library's own bundled implementation — the bundled implementation is only one of the objects satisfying that attribute set.
