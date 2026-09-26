# Adversarial Code Review: Work Package Wrap-up, Four Items — 2026-09-05

Reviewed range: `git diff c7af99c cc43149` (convention key constants, `RunSummary.diverged`, moving the objective-declaration
check to a different layer, `PriceRule` read-only inputs). Conducted separately from the design adversarial review; this review
covers only the code layer. Instrument calibration was clean (the negative control survived, the positive controls were killed):
of 24 mutants, 21 were killed and 3 survived (including 1 negative control). The mutation table is in
`.cache/mutation/red-loose-ends-*.json`, which is not checked into the repository.

⚠ **None of the three blocking defects were found by mutation testing.** They were found by asking "what property does this code
claim, and what mechanism makes that property hold." Mutation testing is blind to a property that no test has ever exercised.

## blocking[]

| # | Defect | Verification |
|---|---|---|
| B1 | A `NaN` lower bound slips past two checks: `_require_non_negative` tests `values < 0` (`NaN < 0` is `False`), and `_require_consumable_support` tests `!= 0` (`NaN` passes and sits on a private good). HiGHS treats a `NaN` bound as no bound at all, so the plan produces nothing, the lower bound goes unmet, and `status="optimal"` anyway. The root cause is that `MinimizeLabor` has **three** checks, and the change that relocated them moved only two, omitting exactly the finiteness one | Not independently reproduced; the mechanism matches the code |
| B2 | **The read-only input guard does not close the path it is documented as closing.** Two escape routes: the rule reuses its output buffer (the library stores the return value by reference as next round's price, while the rule still holds a writable base), and writing directly to `.base` | Confirmed by reproduction |
| B3 | When a coordination procedure calls `iterate` without passing `plan_of`, `diverged` reads `False`, conflating that with "did not diverge." The `RunSummary` documentation says both being false means "rounds exhausted." The real fix belongs in `iterate.py`: "the library never saw a plan" is a third state, parallel to "the library never saw the loop," and should be `None` | Confirmed by reproduction |

The measurement for B2 (synthetic economy, none of the three raise an exception):

```
honest : 25 rounds  price[:3] = [899.507, 943.756, 711.264]
reuse  : 25 rounds  price[:3] = [902.048, 945.724, 711.811]
.base  :  1 round   price[:3] = [700.0,   700.0,   700.0]
```

Root cause: passing a read-only view only protects the memory **the library itself owns**, and the library never owned
`next_price` in the first place. The correct fix is to take ownership and then freeze the array itself (`.base` is `None`),
rather than freezing a view onto someone else's array.

## non_blocking[] (selected)

1. The rule that "the reference solution must not depend on the objective's own checks" only lands on the minimization branch —
   a hand-written **maximization** objective's `weights` skips the checks entirely. Putting weight on labor gives
   `objective_value=20.0`, `output=[0,0]`. **Same issue as V3 in the design adversarial review; the two reviews hit it
   independently.**
2. `minimize_kind` only checks that a value is present, not what it is: `minimize_kind=99` gives `status=optimal`,
   `objective_value=0.0`, while the plan actually spends 12 units of labor.
3. Nothing asserts which attribute the error label points to (mutant M16 survived).
4. No test pins down that the three views are views onto the live array rather than a copy — a future change to pass a copy
   instead would silently reverse the decision (M21 survived).
5. Freezing `surplus` is confirmed by measurement to be an equivalent mutant; it introduces no other issue.
6. `diverged` has never been asserted against a real mechanism; all coverage rests on a hand-built `DivergingProcedure`.
7. `test_the_economy_extra_keys_are_not_exported` guards three names that never existed in the first place.
8. The 16 mutants claimed for the implementation have **no reproducible artifacts on disk** — asked to verify they could be
   replayed, they could not.

## Not breached (selected)

`np.asarray`, `arg[:]`, `reshape`, `+=`, and `np.add(out=)` all raise `ValueError`; only `.base` escapes. Writing after
`arg.copy()` leaves no contamination path. The three `__all__` tests do not overlap and each one bites. The `None` semantics for
`diverged` are pinned down for nested `run`, two `iterate` calls within one `solve`, and never calling `iterate`. A lower bound
with the wrong length, all zeros, `+inf`, or `minimize_kind` given as a string — all of these raise an error rather than fail
silently.
