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

(Correction, 2026-09-27: "agrees across all four sources" does not hold. The log has twelve year-two
counts: 1, 12, 11, 1, 5, 6 (lines 9–14), 11, 6 (lines 35–36), 14 (line 52, 12,000 councils) and
13, 13, 13 (line 161). Their mean is about 8.8, or about 8.4 without the 12,000-council run; 6.0 is
the mean of one table only. Those runs used `ppex` data with 300 to 3000 councils, not dep1ex, and
the 7 and 8 of this reimplementation did not use the price-update rule that produced the published
results. The four rows differ in data and rule, so they cannot corroborate each other. The warm
start was later rerun on all 40 experiments the way the book describes it; see the third addendum
of 2026-09-26. Source: upstream `docs/notes.txt` at `44a6d08`.)

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

  (Correction, 2026-09-27: "the timed runs are full-size ppex experiments" has no source. The timed
  commands are all `lein run -m pequod-plus.csvgen ppex00N`, but the `csvgen.clj` of the time
  (`10da5d2`, unchanged since `04b6caf`) requires only `pequod-plus.ppex004` on line 2, and `setup`
  ignores the experiment argument and always loads `ppex004`. That Clojure namespace is in no
  revision of the repository. The author calls ppex004 "6000 councils" on line 31 of the log and
  writes "An iteration with 60,000 councils" on line 74. Which economy each timed run used cannot
  be determined from the repository.)

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

(Correction, 2026-09-27: chapter 9 is book pages 173–194, notes included; the tables and passages
this addendum uses are on pages 178–185, with Table 9.6 on page 185.)

**Per-experiment round counts.** Tables 9.1 and 9.2 list the round count of each of the 40
experiments at the 5% and 3% thresholds (the averages 11.85 and 19.2 come from them). For
experiments 1 to 5: 12, 12, 12, 12, 12 at 5%; 19, 19, 20, 19, 19 at 3%. The book does not say
that dep1ex01 to 05 are experiments 1 to 5; they are matched here by number.

**Where the cap in the price-update rule applies.** Page 181: "for any v > 0.25 we substituted
0.25 for v where it first appears in the price adjustment formula, but not where it appears as an
exponent". That is, `w = min(v, 0.25) · (1.05 − 0.5^v)`. The slides say only "except when
v > 0.25" and page 7 of the paper says "then v = 0.25"; neither says where the cap applies.
**The prefab's `slides_2020_rule` caps v in both places**, which is not what the book specifies.

(Correction, 2026-09-27: "neither says where the cap applies" overstates it for the paper. The
slides, page 5, do say only "except when v > 0.25". Page 7 of the paper says "except when v > 0.25
then v = 0.25", which read literally sets every v in the formula to 0.25, that is, caps both
occurrences: the prefab's reading above. Source: Szczepanczyk (2023), author's version, page 7.)

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

(Correction, 2026-09-27: "the 6.5 of the slides and the paper is this figure rounded" does not hold.
6.575 rounded to one decimal is 6.6. The slides (page 7) and the paper (page 12) give 6.5 without
saying how it was obtained. The mean of the 40 values printed in Table 9.4 is 6.525, which rounds to
6.5, but no source says that 6.5 comes from that table.)

**Consequence**: the 13.40 and 22.80 rounds reported earlier in this document and in the README
come from the prefab's reading of the cap and are not a faithful reproduction of the published
procedure. Correcting the prefab's cap and implementing the book's warm start is the next work
package; see progress.md.

## Second addendum, 2026-09-26: the `pequod-cljs` source that produced the book's results

Note 7 of the book points to `msszczep/pequod-cljs`. Only the code and notes were read, once
(sparse checkout, without the data blobs). Findings:

**dep1ex01–05 on szcz.org are `dep1ex61`–`65` of that repository**, byte-for-byte identical
except for the namespace on the first line (the sha256 matches the LFS pointer). The
repository's own `dep1ex01`–`50` (`0d24482`, 2020-05-14) are a different, smaller data set (10
commodities per category, 3000 consumer councils), not the experiments in the book. That the
book's 40 experiments correspond to 61–100 in the repository is an inference
(`bin/dep_data_process.py:136,141` loops over `range(61, 101)`); only 01–05 were checked.

(Correction, 2026-09-27: lines 136 and 141 do loop over `range(61, 101)`, but they belong to the
"table 6" section and read `dep2ex` files. The sections for tables 1, 2, 4 and 5 (lines 98, 103,
108 and 129, all commented out) loop over `range(51, 101)`. The two lines show only that Table 9.6
uses 61 to 100; they do not establish that the book's 40 experiments are 61 to 100. The addendum of
2026-09-27 establishes it: 1 to 18 by byte comparison, 19 to 40 by an inference from the per-round
trajectories. "Only 01–05 were checked" is out of date as a result. Source:
`bin/dep_data_process.py` at `pequod-cljs` HEAD, `8bd46b5`.)

**The price-update rule that produced the book's results has a one-round lag** (`csvgen.clj`
@`71e44d3`, 2020-06-23, the version that produced the runs in the book):

`w_k = max(0.001, min(v_{k−1}, 0.25) · (1.05 − 0.5^{v_k}))`, with `v_{−1}` taken as 0.25 before round 1.

- The exponent uses this round's imbalance `v_k`, uncapped; the multiplier uses the **previous**
  round's imbalance capped at 0.25 (`update-pdlist` stores `min(v, 0.25)`, `get-deltas`
  multiplies, with a floor of 0.001)
- Page 181 of the book, "cap only where v first appears, not in the exponent", is structurally
  right; it only omits that the v in the multiplier is the previous round's, and it omits the
  0.001 floor
- The pseudocode on page 10 of the 2023 paper states exactly this rule ("multiply by the
  corresponding price adjustment from the previous round, take the smaller, floor 0.001"). This
  library first read "the previous round's price adjustment" as the previous round's step size
  `w_{k−1}`, and `pequod-plus` implements it the same way; the original multiplies by the
  previous round's capped imbalance `min(v_{k−1}, 0.25)`. The earlier conclusion that "the
  page-10 pseudocode does not converge" came from this misreading
  (Correction, 2026-09-27: "states exactly this rule" overstates it. The pseudocode says to multiply by the
  corresponding quantity from the previous round; it has no 0.25 cap and does not say what that quantity is.
  Read as the previous round's capped imbalance, it matches the program. Found by a citation check.)
- The lagged rule has been there since the first continuous rule (`4751280`, 2020-04-27); the
  base 0.5 and the cap 0.25 have not changed since `fbc4766` (2020-05-12)

**Reproduction result**: with this library's `CouncilModel` unchanged and only the lagged rule
swapped in, dep1ex01–05 cold start at the 5% threshold gives 12, 12, 12, 12, 12, the same as
Table 9.1 experiment by experiment. The worst imbalance per round matches the original's output
`dep1ex61.csv`–`65.csv` round by round to the four decimal places shown, and the step sizes per
round differ by about 1e-15 over 500 × 19 values. At the 3% threshold: 19, 20, 19, 19, 19; Table
9.2 of the book has 19, 19, 20, 19, 19, with experiments 2 and 3 swapped, while the original's
output itself is 19, 20, 19, 19, 19. The cause of the swap cannot be found in the repository
(typesetting or transcription in the book). **The one-round gap at 5% is caused by this lag**;
endowment, initial prices, public goods, effort and random perturbation have all been ruled out.

**Convergence criterion and round counts**: symmetric imbalance `100·|2(s−d)|/(s+d)`, computed
over all 500 commodities, measured at this round's proposals; counting starts at 0 and adds one
after the measurement, the same convention as this library. The original runs once until
everything is ≤ 3%; the 5% round count is the first round in that same run where everything is <
5%.

**Warm start** (`augmented-reset` in the same version, lines 194-200; `-main` line 1048):
- The first year runs until **3%**, and the second year starts from the prices at that point,
  specifically the prices **after** the update; the lagged rule's `pdlist` is **not reset** and
  carries into the second year
- The perturbation changes only the worker councils' input, natural-resource and labor exponents
  (`augment-wc`, lines 185-188), **not the effort exponent**; for consumer councils it changes
  the utility exponents of private and public goods. This agrees with the description of the
  augmented reset in the 2023 paper
- The repository has `compute-gdp` (line 867), but `csvgen` does not call it; the GDP in note 15
  of the book was probably computed offline

**Timing**: the `pequod-cljs` repository contains no timing figures at all.

**The mean of Table 9.4 in the book disagrees with the text** (2026-09-26, table extracted with
`pdftotext` and checked cell by cell): the 40 round counts in Table 9.4 sum to 261, a mean of
6.525; the text on page 183 says "on average it took only 6.575 iterations". The mean of the GDP
column is 2.446, which agrees with the text. Table 9.5 has a mean of 3.775 (text: "3.77"), Table
9.6 a mean of 6.275 (agrees with the text), Table 9.1 a mean of 11.85, and Table 9.2 a mean of
19.225 (text: "19.2").

## 2026-09-26, third addendum: 40 experiments × 10 seeds against the book's five tables

Script `research/bench/hahnel_book.py` (`--experiments 1-40 --seeds 10`), prefab `demplan.prefabs.hahnel` (the original
program's lagged rule); year 1 runs to 3 %, year 2 starts from the prices after year 1's last update and from its rule
state. Four processes, 1276 s wall clock; every run converged.

| Table | Book: mean [min, max] | demplan: mean [min, max] | Sample |
|---|---|---|---|
| 9.1 cold start, first round all < 5 % | 11.850 [11, 13] | 11.850 [11, 13] | 40 |
| 9.2 cold start, first round all < 3 % | 19.225 [18, 22] | 19.200 [18, 22] | 40 |
| 9.5 rounds from all < 10 % to all < 5 % | 3.775 [3, 5] | 3.775 [3, 5] | 40 |
| 9.4 warm start, year 2 first round < 5 % | 6.525 [5, 8] (text: 6.575) | 6.287 [5, 8] | 40 × 10 seeds |
| 9.4 real GDP growth % | 2.446 [2.178, 2.659] | 2.477 [2.143, 2.720] | 40 × 10 seeds |
| 9.6 increasing returns, year 2 first round < 5 % | 6.275 [5, 8] | 6.197 [5, 7] | 40 × 10 seeds |
| 9.6 real GDP growth % | 1.860 [1.659, 2.101] | 1.852 [1.577, 2.116] | 40 × 10 seeds |

**Per experiment**: Tables 9.1 and 9.5 agree on all 40 experiments. Table 9.2 agrees on 37; the three that differ are
experiments 2 and 3 (transposed in the book, see above) and experiment 38: book 19, demplan 18. demplan's worst
imbalance is 2.9992 % in round 18 and 3.2701 % in round 17; the independent numpy reference also gives 18, and the
original program's stop rule would also stop at 18. Not investigated further (whether experiment 38 is `dep1ex38` is
part of the unverified numbering).

**Warm-start distribution**: year-2 rounds, book {5: 8, 6: 5, 7: 25, 8: 2}, demplan {5: 126, 6: 39, 7: 229, 8: 6};
Table 9.6, book {5: 14, 6: 2, 7: 23, 8: 1}, demplan {5: 156, 6: 9, 7: 235}. Both have peaks at 5 and 7. The book's
per-experiment random draws cannot be recovered, so only distributions are compared.

**The book's mechanism findings hold in demplan**: a warm start cuts the round count from about 11.85 to about 6.3
(roughly half); tightening the threshold from 5 % to 3 % costs about 7.35 more rounds; real GDP growth under a warm
start is around 2.4 %; with 20 % of worker councils under increasing returns all 400 runs converge, with round counts
and GDP growth of the same order as the book's.


## Addendum, 2026-09-27: experiment numbering, experiment 38 and Table 9.4

Source: the output files `src/clj/pequod_cljs/dep1ex51.csv` to `dep1ex100.csv` in the original
program's repository, `msszczep/pequod-cljs`, commit `df6dc57` (2020-06-23). Each file was read and
summarized into its per-round worst imbalance and colour column; the files themselves are not
committed.

**Experiment numbering holds for all 40**: experiment N of the book ↔ `dep1exNN` on szcz.org ↔
`dep1ex(60+N)` in the original repository.
- 1 to 18: with the namespace on the first line changed, the sha256 of each szcz input file equals
  the LFS pointer of `dep1ex(60+N).clj` in the repository. Each was compared against all 20
  pointers in the repository and matched only 60+N
- 19 to 40: the repository has no pointers for these inputs, so no byte comparison is possible.
  demplan's per-round worst imbalance has the same number of rounds as the original's
  `dep1ex(60+N).csv`, with a largest difference of 1.9e-12 percentage points over every round of
  the 40 experiments (the original prints full double precision), and the columns computed from the original's output agree with row N of the
  book's tables (below). Two randomly generated data sets giving the same trajectory to twelve
  significant digits are taken to be the same data (an inference)
- The book uses only 61 to 100: `dep1ex51.csv` to `dep1ex60.csv` do not line up with any row of
  the book's tables

This answers the open point in the third addendum, whether experiment 38 is `dep1ex38`: it is.

**Experiment 38: Table 9.2 is misprinted.** In the original's `dep1ex98.csv`, round 18 of year one
has a worst imbalance of 2.9991574176% and colour `:blue`, and year one ends on the next line.
demplan also stops at round 18, at 2.9991574175816607%. The book's text on p. 179: "On average,
it took 19.2 iterations … which is 7.35 more iterations than the 11.85". In the original's output
the 40 first rounds with every imbalance below 3% sum to 768, a mean of 19.2, and 19.2 − 11.85 =
7.35, which matches the text. The 40 values printed in Table 9.2 sum to 769, a mean of 19.225 and a
difference of 7.375, which does not. The original's output and Table 9.2 differ in three places:
experiment 2 (original 20, book 19), experiment 3 (original 19, book 20) and experiment 38
(original 18, book 19). Swapping 2 and 3 leaves the sum unchanged, so the extra round is all in
experiment 38.

**Why the mean of Table 9.4 disagrees with the text: experiment 16 is misprinted.** Table 9.4
prints 5 rounds for experiment 16; in the original's `dep1ex76.csv`, the first round of year two
with every imbalance below 5% (the first `:green`) is round 7. With the original's values the 40
round counts of Table 9.4 sum to 263, a mean of 6.575, which is the text on p. 183, "on average
it took only 6.575 iterations"; with the printed values they sum to 261, a mean of 6.525. This
explains the disagreement noted in the second addendum: the text is right and one cell of the
table is misprinted.

**The GDP values of Table 9.4 are truncated to three decimals.** Real GDP growth computed from the
original's output as the book's note 15 describes (p. 193, "What we report are the averages of the
two percentage increases in real GDP using each year as a base year") and as the original's
`bin/dep_data_process.py` reads it, truncated to three decimals, equals the book's value in all
40 experiments; rounded, it equals it in only 25 (for example experiment 2: original 2.549571,
book 2.549). The year-two round counts agree in 39, and the one that does not is experiment 16.
The book's tables were therefore read from this output; the four cells where they differ from it
were introduced in transcription, at a step the repository does not show.

**Agreement with the original's output, experiment by experiment**: Table 9.1 40/40, Table 9.5
40/40, Table 9.4 GDP 40/40 (truncated to three decimals), Table 9.4 round counts 39/40, Table 9.2
37/40. Table 9.6 was not checked: it comes from `dep2ex61` to `dep2ex100.csv`, which are not in
the repository.

**Consequence for the third addendum**: demplan's 40 cold starts are identical to the original's
output experiment by experiment, with no difference in the first rounds below 10%, 5% and 3%.
demplan's 3% mean of 19.200 in the third addendum is the book's text's 19.2; the book's 19.225 and
6.525 are means of the misprinted tables, and its text's 19.2 and 6.575 agree with the original's
output.
