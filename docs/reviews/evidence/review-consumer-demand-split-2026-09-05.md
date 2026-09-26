# Adversarial Review: Splitting Consumer Demand and `consumer_demand` — 2026-09-05

Reviewed range: `git diff 60e03bd d9e75e7` (`747dd5f` splits consumer demand, `d9e75e7` generalizes the convention keys).
The mutation tables and reports sit outside [mutation-tables-2026-09-05/](mutation-tables-2026-09-05/), in the not-checked-in
`.cache/mutation/` (`consumer-demand-plan.json`, `consumer-demand-plan-2.json`, `c23-escalate-plan.json`, and their matching
reports). Baseline: 474 passed, 1 skipped. 33 mutants (including 4 controls), 29 real mutants, 28 killed, 1 survived.

## blocking[]

| # | Defect | Evidence | Disposition |
|---|---|---|---|
| B1 | No test guards the pairing between `consumption_commodity` and the column order of the consumption block. Sorting the labels without sorting the blocks leaves all 474 tests (including real runs of dep1ex01–05) green | Mutant `C23-consumption-commodity-sorted`; confirmed to survive by an independent replay. The root cause is that the private-good labels in all four available inputs happen to already be in ascending order, so `np.sort` is a no-op everywhere | Fixed |

The root cause of B1 is a degenerate fixture, not a weakly written assertion. The only assertion that pins down the label
content is `assert_array_equal(columns, commodities_of_kind(PRIVATE_GOOD))`, and that function's docstring says "in ascending
order" — this assertion asks "do the labels equal the ascending list," not "do the labels still track the block," and
structurally it cannot distinguish between the two. `build_permuted_economy` claims to defeat "picking private goods by
position," but its internal `argsort` sorts the columns back into ascending commodity-number order, quietly restoring the very
assumption it was meant to break on the private-good side.

The control experiment is clean: mutants of the same shape aimed at `other_commodity` are killed 7 times over (the economy
with a third commodity class perturbs the number order of the other block), while the ones aimed at `consumption_commodity` slip
through.

## non_blocking[]

1. **The `3e-14` bound was read off an incomplete measurement.** `effort` is also a quantity the plan reports: at the 5% level
   it measures 4.34e-14, and at the 3% level 5.24e-14, both over the stated bound; `input_use` at the 3% level also exceeds it,
   at 3.01e-14. The five quantities that were enumerated happen to be exactly the five the original evidence script measured.
   Fixed: all seven arrays and both thresholds are now remeasured, the bound is set to 1e-13, and a note states plainly that
   "this is what these specific runs measured, not a bound proven against the model."
2. One test docstring says "what the plan used to report on its own," a leftover from the `public_demand` era. Rewritten to
   state the actual reason.
3. Nothing in the repository can verify per-household `entitlement` (the allowances in the three synthetic economies and in
   dep1ex01–05 are all single-valued), so `entitlement[:, None]` versus `mean()` is an equivalent mutant, not a false pass. But
   this change turns it from one place into two, and each block could independently use the wrong denominator with nothing to
   catch it. Added an economy with per-household allowances that differ from each other, and mutants on both branches now turn
   red.
4. All coverage of the public-good pricing rule rests on the four tests in `TestStatedDemandSplit` that call the private
   method `_demand` directly. This review confirmed by measurement that the docstring's claim, "looking column by column is the
   only place this is observable," holds — meaning those tests carry real weight rather than just painting a target. The
   fragility is now noted in the test class's documentation.

## Not breached (selected)

- Upstream's `consume` in `util.cljc` prices at `(/ public-good-price num-of-ccs)`, aggregates in two places and then divides
  once more; the reference implementation `research/bench/endowment.py` divides on both sides the same way — the docstring's
  claim holds.
- The same commodity pointed to by multiple columns, an empty private-good column, an empty remaining column,
  `n_consumers = 1`, and swapping the third commodity class for a natural resource or labor — all of these run through cleanly
  and match an independent recomputation.
- `np.shares_memory` is not always true: reverting `plan_of` to `.copy()` is killed by all three tests.
- Shared memory carries no aliasing hazard: `Plan` marks its physical-layer arrays `writeable=False`.
- The worry that "a missing key turns red but a miscalculated value would not" does not hold: mutants that revert only the
  generalization while keeping the key and the public-good term are killed by 4 tests.
- Bit-for-bit equality in the material balance is not a coincidence: the implementation sums with `bincount` twice, the test
  once, and the accumulation order for a given commodity is consistent between them.
