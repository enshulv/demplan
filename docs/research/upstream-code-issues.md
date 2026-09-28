# Upstream code issues

Results of reviewing `msszczep/pequod-plus` (branch `db`, HEAD `44a6d08`) and
`msszczep/pe_ifb_compute`. Cloned at `upstream/pequod-plus/`.

The review is pinned to `44a6d08`. Upstream's `db` branch has since moved to `44d8c15`
(2026-09-12): it adds `augmented-reset-db` and calls it from `-main`, so the item under
"Engineering state" that says "`augmented-reset-improved` is defined but never called by
`-main`" has been fixed upstream.

References are primarily by function name; line numbers are only locating hints — upstream
is still evolving, and line numbers will go stale.

## Checks that run (2026-09-29)

Most of the sections below were first reached by reading the code. Since 2026-09-29 every entry
of the wiki page "Limitations of Existing Implementations" has a check that can be run again, in
[`research/upstream/`](../../research/upstream/README.md). The rules: whatever can be shown from
upstream's own artefacts (the output files they committed, their program, their functions) is
not shown with demplan; every check runs one control that should agree and one that should not;
upstream files are pinned by commit and checked by sha256; no upstream code enters this
repository (a changed rule or term is an edit stated as line number, sha256 of the line before
the edit, and replacement, applied at run time). The upstream programs are built and run in
Docker with their own `project.clj`.

Step-by-step guides to installing, running and reading each script are on the wiki, starting
from the index at the top of the limitations page.

| Issue | Evidence | Result |
|---|---|---|
| Price-update rule | the step recomputed from the supply and demand recorded in each row of the 40 output CSVs `pequod-cljs` committed (`df6dc57`) | the lagged rule: largest relative error 2.2e-15 over 575,500 cells; the book's p. 181 as printed: 77; the paper's p. 7 as printed: 51 |
| Price-update rule | `csvgen.clj@71e44d3` (the same blob as at `df6dc57`) run unchanged in Docker on dep1ex61 | the first 12 rounds are byte for byte the committed `dep1ex61.csv`; with only lines 718–719 replaced by the book's or the paper's rule the steps differ from round 1, and the worst imbalance in round 2 is 48.515010% (program), 48.058812% (book), 75.419980% (paper) |
| Four cells of the book's tables | the output CSVs against the tables | only Table 9.2 experiments 2, 3 and 38 and Table 9.4 experiment 16 differ; Table 9.2 sums to 768 (printed 769), Table 9.4 to 263 (printed 261); GDP truncated to three decimals equal in 40 of 40 |
| Experiment numbering | 40 × 20 matrix of the renamed inputs' sha256 against the LFS pointers; demplan's per-round trajectories | 1–18 hit exactly 60+N; 19–40 trajectories within 1.9e-12 |
| Demand not separated by commodity | their per-round entry points called in Docker | on the in-memory and the SQLite path, 100 of 100 private and public goods get the category-wide sum; supply and input demand 100 of 100 per commodity. The same at `44a6d08` and `44d8c15`; at `10da5d2`, where `csvgen` does not load, the in-memory path only |
| Category multiplier | as above | at ±20% the category multiplier is 0.0 and the step 0.001 (0.0359 from the commodity's own imbalance); both per-round paths use the category value |
| `solution-5` | 31,409 worker councils of dep1ex01 through their `process-wc`; the optimum solved independently with scipy, and first-order-condition residuals | 3, 4, 6, 7 and 9 inputs agree to 1e-13; all 7,492 five-input councils disagree, x1 off by −33.9% to +39.7%; with only that term changed to `log-p3` all 7,492 agree |

Correction (2026-09-29): entry 5 of the wiki page said that "the step of every commodity in the
category shrinks". The runs show otherwise: a commodity whose own imbalance is below the
category value gets a larger step than its own imbalance would give (with +20% and −5% in one
category, the −5% commodity gets 0.0063 against 0.0042). Source: the category-multiplier section
of `docker/pequod-plus/run_all.py`.

New finding (2026-09-29): the effort of `solution-8` and `solution-10` is wrong. In
`pequod-plus@44a6d08`, `csvgen.clj` lines 436 and 592, the terms `b_i·log k` and `b_i·log s` of
the effort expression have the opposite sign to those of `solution-4` and `solution-6` (lines 179
and 294). Called in Docker, the effort of councils with 8 inputs is −62% to −98.7% off the
optimum, with 10 inputs −66.5% to −89.8%; the deviation equals the ratio the sign flip predicts to
within 6.7e-16; output and inputs are correct. `pequod-cljs@71e44d3` line 622 (`solution-8`) has
the same expression: in the committed `dep1ex61.csv`, the recorded effort of the 1,857 councils
with 8 inputs is 92.3% to 98.7% below the optimum, while the controls with 3 to 7 inputs agree to
1e-13. Effort comes after output and inputs in the `let` of `solution-8`, and supply, input demand
and GDP do not read it, so the book's tables are not affected; only the `wc_<id>_effort` columns
of the CSV are. The closed forms of `pequod-cljs` go up to 8 inputs.

## Correctness

### The published pseudocode does not reproduce the published results

> **Correction (2026-09-27)**: the conclusion of this section comes from a misreading; the
> original text is kept below as history. The pseudocode on page 10 of the paper says to multiply
> by "the corresponding price adjustment of the previous round", and this library read that as
> the previous round's step, which is where "does not converge" came from. The original program
> that produced the published results (`csvgen.clj` of `pequod-cljs` at `71e44d3`) multiplies by
> the previous round's imbalance capped at 0.25. The pseudocode has no 0.25 cap and does not say
> what the previous-round quantity is; read as the previous round's capped imbalance, it agrees
> with the program. Run on dep1ex01 to 05, the program's rule gives 12, 12, 12, 12, 12 at the 5%
> threshold, the same as Table 9.1 of the book. `pequod-plus` multiplies by an imbalance aggregated per category, which differs from
> the original program's rule. See [reproduction.md](reproduction.md), second addendum of
> 2026-09-26.

**This is the highest-impact finding of this review.**

Page 7 of the 2023 paper gives the price-update formula used in the experiments,
`w = v(1.05 − 0.5ᵛ)`, noting that `v = 0.25` when `v > 0.25`, with no recursion. Page 5 of
the 2020 conference slides gives the same formula but only says "except when v > 0.25",
without saying what happens then. Page 10 of the paper gives pseudocode it calls an
adaptation: the leading `v ×` factor becomes "multiplied by the previous round's delta, then
absolute value, min, floored at 0.001." The published round counts can only be reproduced
with the former; the current code's `compute-surpluses-prices` in `util.cljc` implements the
latter.

Measured on the authors' publicly released dep1ex01 data, at the endowment of 1000 stated in
the paper:

| Rule | Cold start, 5% |
|---|---|
| The paper's page-10 pseudocode (current code) | Does not converge; after 250 rounds the worst imbalance is 30.2% |
| The paper's page-7 formula | 14 rounds, the same order of magnitude as the 11.85 reported in the slides |

In other words, **the 2023 paper, published specifically to let others reimplement the model
from pseudocode, has pseudocode that does not converge to the published results.**

This explains two previously unexplained facts:

1. In upstream's own records (`docs/notes.txt`), cold start is 41 to 96 rounds, an order of
   magnitude away from the 2020 report's 11.85
2. Two consecutive commits in August 2026, "Fix oscillating behavior" and "Fix extremely slow
   convergence"; both change only the second argument of `get-delta`, see "History of fixed
   items" at the end

See [reproduction.md](reproduction.md) for details.

### Transcription error in the `solution-5` expression

In `solution-5` in `src/clj/pequod_plus/csvgen.clj`, the `x1` term is written as
`(* b3 k log-p2)`. Based on the pattern in `solution-4` and `solution-6` and on the analytical
solution, this term should be `b3·k·log(p3)`; the entire `b3-k-log-p3` term is missing.

Effect: for worker councils with exactly five inputs, the demand quantity for their first
intermediate input is computed incorrectly.

The paper says it uses Wolfram Mathematica to generate the equations and then Mathematica's
`Solve` to solve them (page 5); the solution for two inputs is printed on page 6 as Clojure
code. The code has eight such expressions, `solution-3` through `solution-10`.

### Demand for private and public goods is not separated by commodity (added 2026-09-26)

`compute-surpluses-prices` in `util.cljc` computes supply and demand for each commodity. The
supply branch and the input-demand branch both filter by `id-to-use`; **the private-good and
public-good demand branches do not** (HEAD lines 159-163 and 182-187, from `4c8d307`,
2025-04-08): they sum the demand of all consumer councils for all 100 private goods and use that
sum as the demand for each private good; public goods are handled the same way and then divided
by the number of councils. The `ccs` passed in are not filtered beforehand (`iterate-plan` and
`update-surpluses-prices` in `csvgen.clj` pass the whole vector for each commodity), and each
council's `:private-goods` is a vector of per-commodity maps with an `:id`
(`ccs_revised.clj:13-22`), so the shape of the data does not prevent the error either.

The SQLite path copies this error: HEAD `csvgen.clj:750-751` is `select sum(demand) from
private_goods`, with no `good_id` condition, although that column is stored and indexed. The
ClojureScript front end calls the same functions.

Effect: the private-good and public-good quantities that any build of `pequod-plus` (CLJ, CLJS,
SQLite) converges to cannot be compared with a correct implementation. The book's results come
from `pequod-cljs` and are not affected.

### Why the code before SQLite took two minutes per round (added 2026-09-26)

The author's log, verbatim (`docs/notes.txt` line 74, `d0536cf`): "An iteration with 60,000
councils now takes about two minutes, which would mean a completion time from start to finish of
around two hours, as opposed to something like 12 hours." Lines 70 and 86 also credit "a newer
and faster computer". The eleven timed runs (2026-01-24 to 03-15, `real` 160–253 minutes) ran
the `util.cljc` of `0d2506d` (2026-01-18); SQLite first appears in `3745bde` (2026-04-09).

Counting operations from the code (**an estimate, not measured on a JVM**), the bulk of one
round is:

| Rank | Step | Operations per round | Estimated time |
|---|---|---|---|
| 1 | The demand branch from the previous section: for each of the 200 private and public goods, all 30,000 × 100 elements go through a lazy `map`, `get-in` and `flatten` | 6.0e8 elements | 60–150 s |
| 2 | `consume`: two linear `filter`s per commodity, plus the sum over all 2G exponents redone per commodity, O(C·G²) | about 2.0e9 | 10–30 s |
| 3 | For each of 301 input goods, `select-keys` and a hash set rebuilt for every worker council | 9e6 + 9e6 | 3–8 s |

The total is about 75–190 seconds, consistent with "about two minutes". The code is
single-threaded; `user` is 1.4–2.2 times `real`, and the extra is presumably GC and JIT threads.

(Correction, 2026-09-27, two points. First, "Lines 70 and 86 also credit 'a newer and faster
computer'": those words are on line 70 only ("admittedly with a newer and faster computer"); line
86 says "the faster computer I'm using". Second, "the code is single-threaded" holds only for the
program's own code: `util.cljc` and `csvgen.clj` at `10da5d2` contain no `pmap`, `future` or other
call that starts a thread, while on line 86 the author writes that the machine "at one point was
using three cores to finish the job". Which JVM threads account for the extra CPU time was not
measured; "GC and JIT" is a guess. Source: upstream `docs/notes.txt` at `44a6d08`, lines 70 and
86.)

The author's "optimization" commits from January to March 2026 changed only the closed-form
solutions `solution-3` to `solution-8` (for example, `solution-8` went from 370 calls to
`Math/log` to 21). That part takes well under one second per round (estimate), so it does not
explain the change from 12 hours to about 4 hours, and the log itself mentions a faster
computer. Aggregating the rank-1 branch once by commodity id fixes the correctness error and
also removes about 99% of the rank-1 cost.

### Public-good demand differs by a factor of N between the two code paths

`consume` in `src/cljc/pequod_plus/util.cljc` (the ClojureScript path) has each consumer
council face `price / num-of-ccs`, then divides by the number of councils again at
aggregation. `consume-process-all-in-db` (the SQLite path) uses the full `price` directly,
and likewise divides by the number of councils at aggregation.

As a result, the SQLite path's public-good demand is 1/N of the ClojureScript path's
(N = 30000). The paper describes the former: "We divide the price by the number of consumer
councils."

### Aggregate price delta uses a signed mean

`calculate-price-deltas` in `util.cljc` computes `mean(surplus) / mean(supply, demand)`.
Positive and negative imbalances within the same commodity kind cancel out, so a hundred
commodities each imbalanced by 20% can still yield a step size close to zero, pushing each
commodity's adjustment down to the 0.001 floor. `mean(|surplus|)` would better match the
stated intent.

### Enabling the pollutant switch causes a division by zero

`create-ccs-in-csv` in `src/clj/pequod_plus/populate.clj` draws both
`negative_utility_from_exposure` and `positive_utility_from_income` from the same list,
`[0.11 … 0.19]`. The pollution-permit formula's exponent is `1/(k−j)`; with k and j drawn
from the same distribution, this can produce a division by zero or a sign flip.

The older `ccs.clj` used `[1.11 … 1.19]`. The current `csvgen.clj` hardcodes
`include-pollutants?` to `false`, so this has not surfaced yet.

## Performance

### No index on `coefficient`, yet aggregate queries filter on it

`compute-surpluses-prices-improved` in `util.cljc` aggregates with
`select sum(quantity) from intermediate_inputs where coefficient = ?`, and likewise for
`nature`, `labor`, and `pollutant_demands`.

But the indexes `datasource.clj` creates on these four tables are on `wc_id`, `nature_id`,
`labor_id`, `pollutant_id`, and `intermediate_input_id`; none is on `coefficient`.
Note that `intermediate_input_id` is "which input slot this is for the council," while
`coefficient` is "which of the hundred commodities this is" — the two are not the same
thing. Each of these four hundred queries is a full table scan every round.

### Pulling the entire dataset into the JVM every round

`proposal-db` in `csvgen.clj` does `select *` on three input tables every round, then
`group-by`s them, constructing hundreds of thousands of boxed maps and keywords.

### `pe_ifb_compute` commits inside the insert loop

`load_data_to_sqlite_db` in `src/core.py` calls `con.commit()` inside the `while` loop. An
SQLite commit triggers an fsync; the measured cost is about a thousandfold, see
[reproduction.md](reproduction.md).

The same function inserts the strings from `split()` directly, so the `quantity` column is
TEXT, and `sum(quantity)` has to coerce each row from string to number.

(Correction, 2026-09-27: the table is created as `CREATE TABLE … (council_id, product_id,
quantity)` with no declared column types, so "the column is TEXT" is imprecise; the inserted values
are strings and are stored as TEXT. Source: `src/core.py`, lines 41 and 47–48, at `d9a5947`.)

## Engineering state

- `test/cljc/core_test.clj` requires `ppc.core`, a namespace that does not exist in the
  repository. Tests cannot run
- `update-surpluses-prices-improved` in `util.cljc` hardcodes the commodity count as 100,
  independent of what is actually in the database
- `augmented-reset-improved` is defined but never called by `-main`, so the `db` branch only
  ever runs the first year
- The file is named `csvgen` and defines `print-csv`, but `-main` only `println`s a vector;
  it produces no CSV
- `compute-surpluses-prices-improved` destructures `pd`, but its SQL only does
  `select price`, so that binding is always nil

## History of fixed items

Evolution of `get-delta`'s second argument ("the previous round's price delta") on the
SQLite path:

| Commit | Value passed | Nature |
|---|---|---|
| Before `3204491` | `price` | Passes the price itself (700), making the delta always hit the 0.25 cap, causing oscillation |
| `3204491` Fix oscillating behavior | `pd` | Each commodity's own delta; step size begins to decay |
| `44a6d08` Fix extremely slow convergence | Category-aggregated value | Consistent with the ClojureScript path |

The corresponding location on the ClojureScript path was unchanged across all three commits.
So `44a6d08` fixed a porting discrepancy, not an algorithmic improvement.
