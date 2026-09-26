# Phasing and granularity

## 2026-08-28

### v1 targets department-level granularity, v2 targets council-level granularity; shared data model, separate execution engines

(⚠ v1's scale description was revised on 2026-08-30 to "10³ to 10⁴ order producing units"; see the end of this document. The phasing itself and "shared data model, not shared execution engine" are unchanged.)

**Decision**: v1 covers departments on the order of 10³ (sparse linear algebra); v2 covers individual councils on the order of 10⁷ (data parallelism). Both phases share the same `Economy` data model, each with its own execution engine.

**Why**: These two scales are different problems, both as mathematical objects and as performance-engineering targets. Solving a sparse 10³×10³ Leontief system takes milliseconds, with limited GPU benefit; a closed-form solve per round for 10⁷ individuals is standard embarrassingly-parallel work, well suited to SIMD and GPU. Building v2's execution architecture early, inside v1, would be wasted effort and a source of coupling.

**How to apply**: Don't do v2's performance groundwork inside v1. GPU work is v2's job.

---

### v1's ground truth is a set of producing units, not a matrix

**Decision**: `Economy` is stored as "a column-wise array of producing units, plus a mapping from unit to department." In v1, there happens to be exactly one unit per department, so the mapping is the identity. The input-output matrix is a derived view, grouped from that array — it isn't the underlying model.

**Why**: If v1 treated the A-matrix, the final-demand vector, and the labor vector as ground truth, v2 wouldn't be an extension — it would be a rewrite. A row in a matrix has no concept of a "proposal," and a council is a decision-making agent.

In v1, this layer of indirection is the identity mapping, which costs almost nothing. Adding it back in later would mean redoing the work.

**Alternatives rejected**:

- Use the matrix directly as ground truth in v1 — v2 would then need to rewrite the data model, at a cost far larger than the indirection layer saves in v1

---

### `Technology` is an extensible type from day one; v1 implements only Leontief

(⚠ The number of v1 variants was revised on 2026-08-30 to two; see "v1 implements two technology variants, Leontief and Cobb-Douglas," below. The extensible-type decision itself is exactly what that later revision rests on.)

**Decision**: The technology representation is defined as an enum or trait. v1 implements only the `Leontief` variant.

**Why**: Department-level technology is Leontief fixed coefficients (linear); council-level technology is substitutable Cobb-Douglas (nonlinear). These are different mathematical objects. If v1 welded "technology equals the A-matrix," v2 would break.

The cost is a dozen or so extra lines in v1; the benefit is avoiding a rewrite later.

---

### The time dimension goes into the data model from the start

**Decision**: `Economy` is designed as T periods, with T=1 as a special case.

**Why**: Single-period and multi-period are a fundamental fork — multi-period requires dated commodities, cross-period constraints, and handling capital stocks and production cycles. Going from multi-period down to single-period is easy; going the other way is a rewrite.

The upstream implementation has no time dimension at all — it's the biggest simplification it makes.

---

## 2026-08-30

### v1 implements two technology variants, Leontief and Cobb-Douglas

**Decision**: `Technology` implements two variants in v1, not one.

**Why**: Stage 1's acceptance target for v1 is reproducing dep1ex's cold start converging in 13 to 14 rounds, and **dep1ex's technology is Cobb-Douglas, not Leontief**.

The evidence is in `research/bench/repro.py:152`: `x = exp(log_b + log_lam − log_p + log_Q)`, which expands to `x_ij = b_ij · λ_i · Q_i / p_j` — **input demand depends on input price**, which is the result of Cobb-Douglas cost minimization. Leontief's input demand is `x_ij = a_ij · Q_i`, independent of price. The same holds on the consumption side: `d_priv = income · exp / (tot_exp · p)` is a fixed-expenditure-share demand from Cobb-Douglas utility. This also explains why the upstream implementation needed Mathematica to solve closed forms — Leontief demand is trivial and doesn't need symbolic solving.

Adding this variant doesn't break any recorded decision: `Technology` was already designed as an extensible type; what the base layer fixes is "technology exists as a concept," not "technology has this one shape." **Putting a second option into a slot designed to be open is exactly how theory-neutrality gets implemented for this field.**

The change lands in three places, across three layers: `Technology::CobbDouglas` as a data-model variant; "given a technology and prices, compute cost-minimizing input demand" as a toolbox function; and "given prices, how much this unit intends to produce" as a closed-form solution that is **proposal behavior, belonging to the researcher** — content of the `hahnel_2020_slides` prefab, carrying that paper's behavioral assumptions.

That closed-form solution is one of the eight expressions the upstream implementation derived in Mathematica, transcribed by hand, with `log(p3)` copied as `log(p2)` in one of them — so it needs to go through differential testing per [performance-architecture.md](performance-architecture.md) when it's brought in.

**The reference implementations come from two different files — don't mix them up**: the Cobb-Douglas closed-form solution and input demand are in `research/bench/repro.py:149-152` (the `num/D` and `x` expressions); the **price-update rule** behind the 13-to-14-round target is `delta_slides_capv` in `research/bench/endowment.py`, driven by `confirm.py` with `MODE = "slides_capv"`.

The price-update rule inlined in `repro.py` is the **2023 paper version** (multiplies by the previous round's increment, floor at 0.001). Per [research/upstream-code-issues.md](../research/upstream-code-issues.md), that version fails to converge after 250 rounds. Implementing the coordination procedure from it would leave Stage 1 unable to hit the target.

**Partially narrowed**: This entry narrows the v1 variant count in this document's 2026-08-28 entry, "`Technology` is an extensible type from day one; v1 implements only Leontief." The rest of that entry — the technology representation is defined as an enum or trait, because the two are different mathematical objects — holds completely; this entry rests on it.

---

### v1's scale description is revised to 10³ to 10⁴ order producing units

**Decision**: v1's covered scale changes from "departments on the order of 10³" to "producing units on the order of 10³ to 10⁴."

**Why**: dep1ex has 30,000 worker councils plus 30,000 consumer councils, beyond what "10³ departments" describes. But it isn't a technical obstacle:

The ground truth set on 2026-08-28 in this document is "a column-wise array of producing units, plus a mapping from unit to department," noting that "in v1, there happens to be exactly one unit per department, so the mapping is the identity." dep1ex's 30,000 councils are just 30,000 producing units, grouped by `industry` — **the grouping mapping isn't the identity here, and the data model was designed for exactly this**.

The execution engine handles it too: [performance-architecture.md](performance-architecture.md) measured 99 milliseconds per round and 54.8 MB resident at this scale — no need for v2's data parallelism.

The reason for keeping that layer of indirection was "so v2 doesn't need a rewrite," and it just paid off inside v1 itself.

**Partially narrowed**: This entry only changes the scale wording in this document's 2026-08-28 entry; the v1-department/v2-council phasing and "shared data model, not shared execution engine" are unchanged.

---

## 2026-09-05

### Stage order adjusted: reference solution moves earlier, data field mapping moves earlier

**Decision**: Insert Stage 1.5 between Stage 1 and Stage 2: a minimal linear-programming reference solution (Leontief technology, `scipy.optimize.linprog`). Before Stage 2 begins, do a WIOD field-mapping pass first — listing only what `Economy` is missing, with no code written.

**Why**: `spec.md`'s core-abstraction test (three mechanisms run on the same `Economy`) is the whole design's bet, and the original plan didn't verify it until Stage 5. The first four stages were entirely on parecon plus dep1ex, which would shape `Economy` into parecon's shape. The linear-programming reference solution is the cheapest of the three mechanisms to build, and it is the comparison benchmark itself.

WIOD brings things dep1ex doesn't have: multiple regions, imports and exports, a non-diagonal make table, inventory changes and subsidies (negative entries), and a value-added row. Knowing what's missing before the residual definitions are locked in is cheaper than finding out after.

---

### v1's core abstraction lands as two data types, two functions, and a toolbox

**Decision**: v1's external surface is `Economy`, `Plan`, `solve`, `advance`, and the toolbox functions. `Participant` has no interface slot in v1 — that arrives at v2's council granularity. `Evaluator` is a collection of metric functions, not an object. `spec.md`'s core-abstraction table is written this way; the four-layer split is kept as v2's target shape.

**Why**: `spec.md` should only state rules that hold now. Writing v2's abstraction as if it's a current rule would send whoever implements Stage 0 off building classes nobody uses yet.
