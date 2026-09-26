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
counter. **Prices are not reset**; the basis is page 5 of the slides, "Repeat experiment
starting with previous experiment's prices" (upstream's `augmented-reset` in `util.cljc`
confirms that prices are not reset). Step 4 of the paper's augmented reset says to repeat the
procedure from step three of the pseudocode, and step three sets the initial prices, so read
literally the paper does reset prices.

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
the project page likewise gives 6.5 as its only average, and adds "it never took more than 8
iterations". Readers are left with
"participatory planning takes only six or seven rounds," while the original report gives
11.85 rounds from an arbitrary starting point, and 19.2 rounds at the 3% threshold.

### Comparing the four pieces of evidence

| Source | Cold start (arbitrary initial value) | Warm start (carrying over previous period's prices) |
|---|---|---|
| 2020 slides (40 experiments, 5% threshold) | **11.85** | **6.5** |
| 2023 JIE paper | Not stated | 6.5 |
| Upstream's own records for the new code (`notes.txt`) | 41 to 96 | The six-run table of 2026-01-03: 1, 12, 11, 1, 5, 6; mean 6.0. The same log also has 11 and 6, 14 for one run with 12,000 councils, and 13 for each of three runs |
| This independent reimplementation (dep1ex01) | 54 to 155 | 7, 8 |

**The warm-start column agrees across all four sources**: 6.5, 6.0 (the mean of one six-run table in the log), 7, 8. This can be
considered reproduced.

**The cold-start column does not agree**: the authors reported 11.85 in 2020, while the
authors' own new code reports 41 to 96, and this reimplementation reports 54 to 155. Both
later implementations run an order of magnitude higher than the original report, and are
close to each other.

### Source of the gap: the price-update rule, not the endowment

The cold-start gap has been located. **The endowment is exactly the 1000 stated in the
paper**; the price-update rule is where the readings diverge.

The 2023 paper writes out both versions:

| Source | Rule |
|---|---|
| 2023 paper, page 7, the formula used in the experiments | `w = v(1.05 − 0.5ᵛ)`, with `v = 0.25` when `v > 0.25`. No recursion |
| 2023 paper, page 10, pseudocode it calls an adaptation | The adjustment is `1.05 − 0.5ᵛ`, **multiplied by the previous round's delta**, then absolute value, min, floored at 0.001 |

Page 5 of the 2020 slides gives the first formula too, but only says "except when v > 0.25"
without saying what happens then; "`v = 0.25`" comes from page 7 of the paper. The pseudocode
replaces the formula's leading `v ×` factor with "multiplied by the previous round's delta."
The published round counts can only be reproduced with the former; upstream's current code
(`pequod-plus`) implements the latter.

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
| Upstream `pequod-plus`, before the SQLite code | About two minutes | — | — |

The upstream row comes from the author's run log (`docs/notes.txt`); this library did not
measure it. The per-round figure is the log's own wording: "An iteration with 60,000 councils
now takes about two minutes" (2026-01-21). The wall-clock time for one complete experiment is
160 to 253 minutes (eleven records in the same log, January to March 2026). All of these runs
predate upstream's SQLite code, which first appears on 2026-04-09. Across the eleven records,
`user` time is 1.4 to 2.2 times `real` time.

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
- The round-count tables in upstream's `notes.txt` come from ppex runs with 300 to 3000
  councils; the timed runs are full-size ppex experiments. The log has no run on dep1ex data.
  Strictly speaking, upstream's new code has never been run against the published data

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

## Addendum, 2026-09-26: Hahnel (2021), chapter 9, and how the prefab differs

Hahnel (2021), *Democratic Economic Planning*, chapter 9 (book pages 178–184), gives details that
neither the slides nor the paper give. The maintainer holds a private copy; it is not distributed
with the repository.

**Per-experiment round counts.** Tables 9.1 and 9.2 list the round count of each of the 40
experiments at the 5% and 3% thresholds (the averages 11.85 and 19.2 come from them). For
experiments 1 to 5: 12, 12, 12, 12, 12 at 5%; 19, 19, 20, 19, 19 at 3%. The book does not say
that dep1ex01 to 05 are experiments 1 to 5; they are matched here by number.

**Where the cap in the price-update rule applies.** Page 181: "for any v > 0.25 we substituted
0.25 for v where it first appears in the price adjustment formula, but not where it appears as an
exponent". That is, `w = min(v, 0.25) · (1.05 − 0.5^v)`. The slides say only "except when
v > 0.25" and page 7 of the paper says "then v = 0.25"; neither says where the cap applies.
**The prefab's `slides_2020_rule` caps v in both places**, which is not what the book specifies.

Measured on dep1ex01 to 05, seed 0:

| | 5% threshold | 3% threshold |
|---|---|---|
| Book, Tables 9.1 and 9.2, experiments 1 to 5 | 12, 12, 12, 12, 12 | 19, 19, 20, 19, 19 |
| demplan prefab (cap in both places) | 14, 13, 13, 14, 13 | 23, 23, 22, 23, 23 |
| The book's reading (cap only where v first appears) | 11, 11, 10, 11, 11 | 19, 19, 19, 19, 19 |

With the book's reading the 3% counts match almost experiment by experiment; at 5% they are one
round short, for a reason not yet investigated (candidates: whether the threshold test is `<` or
`≤`, and where round counting starts).

**Warm start.** Pages 182–183 specify the perturbation: each exponent of every worker council's
production function is increased by one of {0.000, 0.001, 0.002, 0.003, 0.004} chosen at random,
each exponent of every consumer council's well-being function by one of {−0.002, −0.001, 0.000,
+0.001, +0.002}, and planning starts from the previous year's final prices. Table 9.4 gives the
round count and real GDP growth of each of the 40 experiments: 6.575 rounds on average (the 6.5
of the slides and the paper is this figure rounded), GDP growth from 2.178% to 2.659%, 2.446% on
average. The warm-start perturbation used here before was chosen by this project, which is why it
gave 4.00 rounds.

**Consequence**: the 13.40 and 22.80 rounds reported earlier in this document and in the README
come from the prefab's reading of the cap and are not a faithful reproduction of the published
procedure. Correcting the prefab's cap and implementing the book's warm start is the next work
package; see progress.md.
