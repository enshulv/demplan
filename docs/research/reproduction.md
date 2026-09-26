# Reproduction record: participatory planning iteration counts

A reproduction of Hahnel and Szczepanczyk's participatory planning simulation. Scripts are
in `research/bench/`.

## Data source

The original experiment data is at <https://www.szcz.org/depexperiments/>:

- `dep1ex01.clj.gz` through `dep1ex40.clj.gz`, 54 MB each, 2020-11-27. These correspond to
  the forty experiments described in the paper
- `ppex001.clj.gz` through `ppex005.clj.gz`, 79 MB each, 2025-07-04

`dep1ex01` decompresses to 160,896,411 bytes. A full-text scan confirms it contains only two
top-level definitions: `ccs` and `wcs`.

**These files contain only inputs, no results.** The published iteration counts cannot be
read from the files; they can only be reproduced by rerunning the simulation.

The parsed results match the paper's description item by item:

| Item | Paper | Measured from data |
|---|---|---|
| Number of councils | 30,000 + 30,000 | 30,000 + 30,000 |
| Number of commodities | 100 | 100 private goods + 100 public goods |
| Input cap | maximum of eight | Distribution 3 to 8, none exceeding it |
| Initial income | Not stated | 5000 |

**Endowment parameter**: the supply quantities of nature and labor are not in the data
files; the paper's body text gives 1000. This reproduction confirms that value by working
backward from the data; see below.

## Results

Reimplemented from the paper's pseudocode and upstream's ClojureScript path in `util.cljc`,
at a 5% threshold:

| Endowment | Cold-start rounds | Warm-start rounds |
|---|---|---|
| 10³ | 155 | 8 |
| 10⁴ | 54 | 7 |
| 10⁵ | 97 | 255 (did not converge) |

Warm start follows the paper's augmented reset: perturb the exponents, reset the round
counter, **prices are not reset** (upstream's `augmented-reset` in `util.cljc` confirms that
prices are not reset).

## Conclusions

### 6.5 is the warm-start figure; the authors reported it that way in 2020

The 2020 conference slides list the two start types separately (page 7; download location
in [literature/README.md](literature/README.md)):

> - To 5% threshold **from arbitrary price vector**: avg. **11.85** iterations.
> - To 3% threshold from arbitrary price vector: avg. 19.2 iterations.
> - To 5% threshold **from previous experiment's price vector**, accounting for technology
>   changes and consumer preferences' changes: avg. **6.5** iterations.

So "6.5" explicitly refers to replanning from the previous period's prices, not planning an
economy from an arbitrary initial value.

**This distinction disappeared in later citations.** The 2023 JIE paper states "across two
years of the lifespan... we see an average of 6.5 iterations," keeping only the 6.5 figure;
the project page likewise mentions only that one number. Readers are left with
"participatory planning takes only six or seven rounds," while the original report gives
11.85 rounds from an arbitrary starting point, and 19.2 rounds at the 3% threshold.

### Comparing the four pieces of evidence

| Source | Cold start (arbitrary initial value) | Warm start (carrying over previous period's prices) |
|---|---|---|
| 2020 slides (40 experiments, 5% threshold) | **11.85** | **6.5** |
| 2023 JIE paper | Not stated | 6.5 |
| Upstream's own records for the new code (`notes.txt`, six runs) | 41 to 96 | 1, 5, 6, 11, 12, 1; mean 6.0 |
| This independent reimplementation (dep1ex01) | 54 to 155 | 7, 8 |

**The warm-start column agrees across all four sources**: 6.5, 6.0, 7, 8. This can be
considered reproduced.

**The cold-start column does not agree**: the authors reported 11.85 in 2020, while the
authors' own new code reports 41 to 96, and this reimplementation reports 54 to 155. Both
later implementations run an order of magnitude higher than the original report, and are
close to each other.

### Source of the gap: the price-update rule, not the endowment

The cold-start gap has been located. **The endowment is exactly the 1000 stated in the
paper**; the price-update rule is where the readings diverge.

The 2020 slides and the 2023 paper give **two different formulas**:

| Source | Rule |
|---|---|
| 2020 slides, page 5 | `w = v(1.05 − 0.5ᵛ)`, with `v = 0.25` when `v > 0.25`. No recursion |
| 2023 paper pseudocode | The adjustment is `1.05 − 0.5ᵛ`, **multiplied by the previous round's delta**, then min, absolute value, floored at 0.001 |

The 2023 version replaces the leading `v ×` factor from the 2020 version with "multiplied by
the previous round's delta." Upstream's current code (`pequod-plus`) implements the 2023
version.

Comparing three readings on the same data (dep1ex01) and the same endowment (1000):

| Rule | Cold start, 5% |
|---|---|
| 2023 paper pseudocode | **Does not converge**; after 250 rounds the worst imbalance is still 30.2% |
| 2020 formula, `v` capped at 0.25 before use | **14 rounds** |
| 2020 formula, `w` capped at 0.25 after computing | **Does not converge**; after 250 rounds the worst imbalance is 148.9% |

### Reproduction results using the 2020 rule

Using the rule "`v` capped at 0.25 before use," endowment 1000, running dep1ex01 through
dep1ex05:

| Experiment | Cold 5% | Cold 3% | Warm 5% (three seeds) |
|---|---|---|---|
| dep1ex01 | 14 | 23 | 4, 4, 4 |
| dep1ex02 | 13 | 23 | 4, 4, 4 |
| dep1ex03 | 13 | 22 | 4, 4, 4 |
| dep1ex04 | 14 | 23 | 4, 4, 4 |
| dep1ex05 | 13 | 23 | 4, 4, 4 |
| **Mean** | **13.40** | **22.80** | **4.00** |
| **2020 report (40 experiments)** | **11.85** | **19.2** | **6.5** |

Both cold-start thresholds fall within 13% to 19% of the reported values, and the ratio
between the two also agrees — 3%/5% = 1.70 here, versus 19.2/11.85 = 1.62 in the report.

### The endowment is indeed 1000

Holding the 2020 rule fixed, sweeping the endowment:

| S | 250 | 500 | 700 | **1000** | 1400 | 2000 | 4000 |
|---|---|---|---|---|---|---|---|
| Cold 5% | 41 | 30 | 14 | **14** | 31 | 37 | 49 |
| Cold 3% | 56 | 45 | 28 | **23** | 46 | 53 | 64 |

The minimum falls between 700 and 1000, consistent with the 1000 stated in the paper.

A further corroboration: at an initial price of 700, the mean first-round demand for labor
and nature is about 463, so an endowment of 1000 corresponds to roughly 74% initial surplus
— a plausible order of magnitude, not an arbitrary figure.

### Remaining discrepancies

- **Cold start: 13.40 vs. 11.85**, 13% higher. This run covers only 5 of the 40 experiments,
  while the report averages over 40; also, this is a reimplementation, not upstream's code
- **Warm start: 4.00 vs. 6.5**, 38% lower. The three random seeds produce identical results,
  giving zero variance, which is not expected — it suggests this reimplementation's
  augmented-reset perturbation may be smaller than upstream's. The slides state that warm
  start is accompanied by a 2.446% rise in GDP, an independently checkable figure that has
  not yet been verified

## Performance

At the same scale (30,000 WC × 30,000 CC × 100 commodities):

| Implementation | Per round | 100 rounds | Resident memory |
|---|---|---|---|
| numpy, single-threaded | 99.1 ms | 9.91 s | 54.8 MB |
| Upstream's SQLite implementation | ~144 s | ~4 hours | Data on disk |

Upstream's wall-clock time for one complete experiment is 160 to 253 minutes (eleven records
in `docs/notes.txt`). Note that its `user` time is more than double its `real` time even
though the code is single-threaded — the extra CPU time is JVM garbage collection.

Another repository, `pe_ifb_compute`, studies computational requirements specifically; its
load function calls `con.commit()` inside the insert loop. Measured comparison (20,000
rows):

| Path | Time | Rate |
|---|---|---|
| Commit per row (original code) | 40.49 s | 494 rows/s |
| Commit moved outside the loop | 0.041 s | 493,764 rows/s |

## Caveats

- Only 5 of the 40 experiments were run
- This reimplementation is not upstream's code; it was rewritten from the descriptions in
  the paper and slides. It uses a derived compact closed-form solution that is mathematically
  equivalent to upstream's expanded form, but has not been checked bit-for-bit
- The warm-start augmented-reset perturbation used self-chosen seeds; the three seeds produce
  identical results, giving zero variance. This is not expected; the perturbation magnitude
  may be smaller than upstream's
- The six runs recorded in upstream's `notes.txt` use the ppex series (300 to 3000 councils),
  not the published dep1ex series. Strictly speaking, upstream's new code has never been run
  against the published data

## This line of work ends here

The conclusions are sufficient to support this library's design decisions; this research
effort ended on 2026-08-28. See [decisions/research-scope.md](../decisions/research-scope.md)
for the decision record.

Not done but doable (to be picked up again if a paper is written in the future):

1. Run all 40 experiments to establish a firm mean
2. Calibrate the augmented-reset perturbation magnitude against the slides' "warm start
   accompanied by a 2.446% rise in GDP"
3. Contact the authors. **This has been decided against**; see the decision record for the
   reasoning

## 2026-09-05 addendum: the public-good pricing rule leaves no trace in the plan

The reproduction work concluded on 2026-08-28; this finding was made during v1
implementation and is appended here.

The model defines a pricing rule for public goods: a consumer council facing a public good
bids at the listed price divided by the number of councils; the quantity it reports is then
divided again by the number of councils when aggregating, so the good is counted once for
society as a whole. **These two halves cancel exactly.**

The reason is the combination of Cobb-Douglas utility and the "spend the full entitlement"
assumption: expenditure shares are independent of price, so dividing the price by n
multiplies the stated plan by exactly n, and dividing again by n during aggregation returns
it to where it started.

Measured on dep1ex01 (30,000 consumer councils): relabeling public goods as intermediate
goods, which removes both halves at once, still gives 14 rounds; the maximum relative
deviation in output, input use, consumption, per-commodity demand, and indicative prices is
2.3e-14, which is floating-point noise.

**This is a property of the published model, not something introduced when porting it into
this library.** Upstream's ClojureScript implements both halves: `consume` in
`upstream/pequod-plus/src/cljc/pequod_plus/util.cljc` bids at
`(/ public-good-price num-of-ccs)` on the public-good branch, and the same file's aggregation
divides the summed public-good demand by `num-of-ccs` again. This library's numpy reference
implementation, `research/bench/repro.py`, has both halves as well.

**Consequence**: the 13 to 14 rounds this library reproduces **do not exercise this rule**.
Removing the rule entirely leaves the iteration count and every number in the plan
unchanged. Making it have an observable effect would require replacing Cobb-Douglas utility,
or having councils not spend their full entitlement.

The one place it is observable in this library is the per-column stated plan, pinned by
`TestStatedDemandSplit` in `tests/test_hahnel_2020_slides.py`.
