# Incremental Adversarial Review: Fixes and Stage 1.5 — 2026-09-05

Reviewed range: `git diff 909903a 904837c`. The mutation tables and reports are archived in
[mutation-tables-2026-09-05/](mutation-tables-2026-09-05/) (`delta-*`). Baseline: cargo 62 passed; pytest 436 passed. 78 mutants
(55 Python, 17 Rust, 4 criterion-isolation controls), with both batches carrying negative and positive controls; of 6 survivors,
3 were judged equivalent mutants after producing artifacts, and 3 are real gaps (B3, B4, B5).

## blocking[]

| # | Defect | Evidence | Disposition |
|---|---|---|---|
| B1 | `MinimizeLabor` accepts negative `targets`; the reference solution reports a physically impossible optimum with `status="optimal"` | A three-commodity economy with `targets [6,-3,0]` reports the labor minimum as 6 instead of 12; commodity 1 has zero output yet 3 units are consumed | Fixed. |
| B2 | A hand-written objective that declares only `final_demand_lower_bound` and omits `minimize_kind` is silently treated as a maximization, and the lower bound is dropped | `status optimal, objective_value -0.0, output [0. 0.]` | Same fix. |
| B3 | The guard in `CouncilModel._require_keys` has no test; neutralizing the whole check still leaves all 436 tests green (mutant `pf-required-keys-off` survived) | With the guard: `ValueError: … needs unit_extra keys effort_s`. Without it: `KeyError` | Same fix. |
| B4 | Nothing tests the unit number reported when an input segment goes out of bounds: both test cases put the bad value in unit 0 (mutant `rs-input-unit-attribution` survived) | The `:product` branch has three mutants on the same attribute killed; this is a degenerate fixture specific to the input branch | Same fix. |
| B5 | `tests/test_readme_examples.py` cuts once on the heading and then searches the rest of the document for a code block, so if that section has none it silently grabs the next section's block (mutant `readme-ten-lines-block-defenced` survived) | Changing the `## Ten lines` fence to `text` still leaves the test green, because it picks up the `def solve(...)` block instead | Same fix. |
| B6 | README says the reference solution "is not built yet," while the same commit already exports it | `__init__.py` exports seven names, and all 630 lines of `test_reference.py` are green | Fixed. |
| B7 | The README's Windows activation line has an embedded BEL control character (rendered as an escape) | Byte offset 1115 is `0x07` | Fixed. |

## non_blocking[] (selected)

1. `consumable` means two different things in `objectives.py` and `reference.py`; the `reference.py` module docstring's claim
   of "one variable per consumable commodity" is false under the former's meaning.
2. A price rule that writes `price` in place contaminates the recorded `indicative_price`; the `PriceRule` protocol does not
   say "must not modify its input." Fix: pass a read-only view.
3. The sentence in `CouncilModel.converged` about `NaN` describes an unreachable precondition (`_relative_imbalance` can never
   produce `NaN`); `np.max` and `np.nanmax` are equivalent mutants of each other here.
4. `MinimizeLabor({0: 6.0})` raises `TypeError`; the mapping branch is dead code. Its sibling class supports a mapping and
   this one does not.
5. `MaximizeWeightedConsumption(np.zeros(n))` returns `objective_value == -0.0`.
6. Across the whole suite, only dep1ex01 had ever exercised the Rust loader; the review added a load smoke test for all five
   archives, and all five passed.
7. `iterate`'s divergence monitoring does not cover `Plan.extra`.
8. The discriminating power of the "scaling up by 1% must violate the constraint" criterion has a lower bound somewhere
   between 0.1% and 1%; the comment does not state this limit.
9. `__init__.py`'s `__all__` is no longer in ASCII order.

## Not breached (selected)

- The effort formula: algebraically simplifying upstream's `solution-3` residual expression matches, term for term, the
  closed form in `solution-4`, which never references it; the input demand `x_j = b_j·λ·Q/p_j` matches upstream's `x1`,
  term for term, across a seventeen-term expansion.
- `public_demand`: recomputing it independently from just `entitlement`, `utility_exponent`, and `indicative_price` matches
  the value recorded in the plan with a maximum absolute difference of 0.0.
- The reference solution's self-looping unit matches a hand computation term for term against the actual run; a negative
  `endowment` reports `ReferenceInfeasible`; `shadow = -marginals` gives non-negative, correct values on both of two
  oppositely-signed hand-computed duals (verified only against scipy 1.18.1).
- Feeding the output of `linearize` into a prefab is rejected by a guard, with the message naming `technology_kind`.
