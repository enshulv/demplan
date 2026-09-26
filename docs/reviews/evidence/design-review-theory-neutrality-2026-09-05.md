# Design Adversarial Review: Theory Neutrality — 2026-09-05

Reviewed the public surface of `cc43149`. The criterion comes from `decisions/scope-and-purpose.md`, 2026-09-05:
theory-neutral does not mean "carries no theory," it means making theory an optional tool and stating plainly, to the
researcher, the stance it implies. Findings fall into four categories: smuggled-in, non-optional, opaque, and misrepresented.
**Read-only review; no files were changed.**

The review was conducted independently, with no context carried over from the code adversarial review, which was done
separately. Every citation and measurement below was independently checked; how each one was checked is noted.

## Misrepresented[] (claims made that were not enforced, or enforced without consequence; the most serious category)

| # | Finding | Verification |
|---|---|---|
| V1 | The `reference.py` module docstring says "**Nothing else is imposed**," while in fact it hardcodes four things: non-negativity (`bounds` is `(0.0, None)` throughout), free disposal (constraints use inequalities), no inventory within the period (constraints have no stock term), and constant returns to scale with no capacity cap (variables have no upper bound). The first three are exactly the theoretical commitments that `invariants-and-metrics.md` names as things that "must not be set as a premise." | Checked against the citation and `bounds()` |
| V2 | `Objective.weights` invites researchers to "returns zeros and carries its own attributes instead," but `reference_solution` only recognizes the pair `final_demand_lower_bound` + `minimize_kind`. **Zero plus arbitrary attributes is silently waved through**: a hand-written objective gets `status=optimal`, `value=-0.0`, and all-zero output | Confirmed by reproduction |
| V3 | `_require_consumable_support` is called by `MaximizeWeightedConsumption.weights` itself; the reference-solution layer never re-checks a maximization objective's `weights`. A hand-written objective that puts weight on labor gets `objective_value=300`, entirely from a quantity that does not exist in the plan | Not independently reproduced; same mechanism as V2 |
| V4 | The README says "the check is the reason a plan built for one economy cannot be quietly aggregated against another," while `_require_conformable` only compares shape and dtype. Two economies of the same shape with their output commodities swapped each accept the other's plan; `validate` passes both | Checked against the citation and the implementation |

## Smuggled-in[] (a school's assumptions riding along in the base layer or an unavoidable path, undisclosed)

| # | Finding |
|---|---|
| J1 | `linearize` silently swaps a Cobb-Douglas technology's decreasing returns to scale for constant returns to scale (the coefficient is taken as `input_use/output`, with `technology_scale` set to 1). The path the README spells out explicitly is "CD economy → `linearize` → reference solution," so the benchmark is systematically higher than what the original technology could actually reach, and higher still the further the operating point sits from the anchor. The documentation states the anchor-point commitment; returns to scale go unmentioned |
| J2 | `linearize` folds the effort chosen by the worker council into the input coefficients: the higher the effort, the better the linearized technology looks. `Plan.extra["effort"]` is discarded, and the returned `Economy` no longer remembers where it was anchored. Cross-mechanism comparison silently breaks down here |
| J3 | `Plan.endowment_use` welds in the assumption that "endowment = natural resources and labor." The documentation states, as if it were a fact, "Other commodities are zero: they are produced within the period" — an assertion the schema does not enforce. When a researcher uses the `endowment` column to hold cross-period inventory (the only place the library leaves for it), the supply side counts it in full while the use side drops it by kind, and the two sides no longer balance |

## Non-optional[]

| # | Finding | Verification |
|---|---|---|
| B1 | `CommodityKind` and `TechnologyKind` are closed enums (an allow-list on both the Python and Rust sides), while the README says "A new class is a new marker value, not a new column," and the spec says "extensible." The two future extensions the library itself names — emissions and money stocks — cannot get in today. Separately, "one commodity, one kind" forces a dual-purpose commodity (electricity as both an intermediate good and a consumer good) to pick one or the other | Checked against the citation and both sides' validation |

## Opaque[] (the commitment is real, but not written where the researcher can read it)

| # | Finding | Verification |
|---|---|---|
| T1 | ✅ **Fixed (2026-09-06).** `check_determinism` does not compare `Plan.extra`, while the README says it "compares the plans bit for bit." A method whose `consumer_demand` differs every run gets reported as `identical=True` | Checked against the citation and `checks.py`; **the code adversarial review hit this again independently on 2026-09-06**, with neither review aware of the other; see `decisions/data-model.md`, same date |
| T2 | The reference solution's plan has an empty `extra`, so the README's own material-balance formula raises `KeyError: 'consumer_demand'` when run against the library's own benchmark. The two plan producers inside the library follow two different conventions for recording demand-side data | |
| T3 | `commodity_id` / `unit_id` are called stable identifiers, but are in fact forced to equal the row number. An evolution rule that adds or removes any row renumbers every row after it | |
| T4 | Equal division is a distributive claim: `MaximizeWeightedConsumption` states it, while `MinimizeLabor` routes through the same `_split_equally` without a word about it. And `n_consumers` counts consumer councils, not people, while the prefab's public-good rule treats it as a headcount | |
| T5 | `MinimizeLabor` sums all labor commodities 1:1 — that is, it treats every kind of labor as fully commensurable by the hour — which is the single most famous open question within labor value theory itself | |
| T6 | `load_dep1ex`'s `endowment=1000.0` determines the constraint level for the whole economy (at 500 versus 1000, the rounds to 3% convergence are 45 versus 23); the function's docstring states this, but the README's ten-line example does not | |
| T7 | `provision` is a single scalar per public good — a Samuelsonian pure public good; regionally or tiered supply cannot be expressed in the physical layer. `total_consumption` covers only private goods, so using it for a per-capita measure will systematically miss public goods | |
| T8 | The provenance of `initial_price = 700.0` (the body of the paper) is not stated in the docstring, while `threshold_pct`'s is | |
| T9 | `ReferenceProcedure` unconditionally claims "The linear program is deterministic," while that determinism is actually provided by HiGHS through SciPy's call into it, and holding across versions and builds is not something this library controls | |
| T10 | `valuation`'s three price-like keys sit side by side and read like interchangeable notions of "value," but their units and normalization differ: the indicative price is only defined up to an overall scaling, the LP dual is "objective value per unit of commodity," and labor value is time | |

## Unavoidable but disclosed[] (positive findings, selected)

`input_use` being stored rather than derived, `linearize`'s anchor-point commitment and its handling of idle units, the
warning that `cost_minimizing_inputs` can disagree with the prefab, `iterate`'s definition of a round, the three states of
`converged`/`diverged`, `check_determinism` being a tool rather than a gate, **the convergence criterion being left entirely to
the researcher (the cleanest instance of theory-neutrality in the whole codebase)**, divergence being defined precisely as
non-finite values and nothing more, `PriceRule`'s read-only inputs, `CouncilModel`'s list of commitments, the prefix-chain
property of `split_seed`, and a unit having exactly one output (already disclosed as a v1 scope limitation).

## not_done[] (what the next pass should look at first)

1. The `checks` residual toolbox is not implemented yet, but the spec has already fixed its wording: "income is taken from
   `valuation["income"]`, falling back to `entitlement` when absent" — this step makes "the consumer faces a budget constraint,
   and the entitlement is income" the default, and it will become a genuine smuggled-in assumption once implemented.
2. `advance` / multi-period runs and the run manifest are not implemented yet; T3 (row number as identifier) and J3 (nowhere
   to put inventory) will be amplified there.
3. `tests/` and `research/bench/` were not reviewed (out of scope for this pass); no real dep1ex data was run — every
   measurement here was on a small hand-built economy, so the conclusions are all structural.
