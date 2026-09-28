# Checks of the published implementations

The scripts in this directory check each entry of the wiki page
[Limitations of Existing Implementations](https://github.com/enshulv/demplan/wiki/Limitations-of-Existing-Implementations)
against upstream's own artefacts: the output files the authors committed to
[`msszczep/pequod-cljs`](https://github.com/msszczep/pequod-cljs), their programs built in Docker
from their own `project.clj`, and their functions called directly. demplan appears only where a
statement is about demplan, such as "demplan's trajectory matches the program's output".

- **Pinned inputs.** Every upstream file is listed in `manifest.tsv` with its repository, commit,
  path, sha256 and size. `fetch.py` downloads what is missing and stops on any file whose hash
  differs. Docker base images are pinned by digest.
- **Controls.** Every check also runs a comparison that should agree and one that should not, and
  prints the numbers of both sides with the file, commit, row or round they come from.
- **No upstream code in this repository.** `pequod-cljs` has no licence and `pequod-plus` is
  GPL-3.0, so no line of either is stored here. Where a check runs an upstream program with a
  change, the change is an edit set in `docker/<program>/edits/*.json`: repository, commit, file,
  and for each edited line its number, the sha256 of the line as committed, and either a
  whole-line replacement or the replacement of one text that must occur exactly once on the line.
  `_source_edits.py` checks every line hash before it changes anything, and each run prints the
  resulting diff against the commit.

Step-by-step guides for running each script and reading its output, written for readers who
have not used the command line much, are on the wiki: start at
[Reproducing the limitations: setup](https://github.com/enshulv/demplan/wiki/Reproducing-Limitations-Setup).
This file is the reference.

## Requirements

Python 3.11 or later with numpy. `check_rules.py` also needs demplan; `check_effort.py` and
`docker/pequod-plus/verify_closed_forms.py` need scipy; the two `docker/` scripts need Docker and
network access to Docker Hub, GitHub, Clojars and Maven Central on their first run. Every script
takes `--cache DIR` (default `research/data/upstream/`) and `--data-dir DIR` (the dep1ex archives,
default `$DEMPLAN_DATA_DIR` or `research/data/`), and `--help` lists the rest.

## Scripts

Times were taken on a Windows laptop with 12 threads, after the downloads.

| Script | Wiki entries | Command | Time | Downloads |
|---|---|---|---|---|
| `fetch.py` | all | `python research/upstream/fetch.py` | 4 s when present | 4.0 GB: 40 archives, 50 output CSVs, 20 LFS pointers, `csvgen.clj`, `bin/dep_data_process.py` |
| `check_outputs.py` | 1, 2 | `python research/upstream/check_outputs.py` | 9 s | 1.8 GB of output CSVs |
| `check_inputs.py` | 3 | `python research/upstream/check_inputs.py` | 2 min | 2.2 GB of archives |
| `check_rules.py` | 1, 3 | `python research/upstream/check_rules.py [--experiments 1-40]` | 55 s for 1–5, 6.6 min for 1–40 | one 36 MB output CSV per experiment |
| `check_effort.py` | 7 | `python research/upstream/check_effort.py [--experiments 1] [--round last]` | 70 s per experiment | as `check_rules.py` |
| `check_history.py` | 8, 9 | `python research/upstream/check_history.py [--no-fetch]` | 7 min after cloning | clones of both repositories, about 1 GB |
| `docker/pequod-plus/run_all.py` | 4, 5, 6, 7 | `python research/upstream/docker/pequod-plus/run_all.py` | 3.7 min with the images built | four images, 928 MB |
| `docker/pequod-cljs/run.py` | 1, 9 | `python research/upstream/docker/pequod-cljs/run.py` | 18–19 min | image of 2.4 GB; peak container memory up to 4.5 GiB |

## What each script does

**`check_outputs.py`** reads the 40 output files `dep1ex61.csv` to `dep1ex100.csv` of
`pequod-cljs` (commit `df6dc57`). It recomputes every recorded price step from the same row's
supply and demand under the program's rule, the rule as printed in the book (p. 181) and the rule
as printed in the paper (p. 7), and checks the recorded stored imbalance, price, surplus and
imbalance columns. It then sets Tables 9.1, 9.2, 9.4 and 9.5 of the book, as printed in
`book_tables.csv`, against the same files, with `dep1ex51.csv` to `dep1ex60.csv` as the control.
It does not use demplan.

**`check_inputs.py`** renames the first line of each public archive `dep1exNN` and compares its
sha256 and size with every LFS pointer `dep1exMM.clj` of `pequod-cljs`.

**`check_rules.py`** runs demplan's councils (`demplan.prefabs.hahnel`) once per price rule: the
program's, the book's, the paper's, and each printed rule with the program's floor of 0.001. For
each it reads the first round below 5% and below 3%, sets them against Tables 9.1 and 9.2 and the
program's output, and compares every round's worst imbalance with the output file of the same
experiment and, as a control, of the next one. The program's stopping rounds are confirmed with
`HahnelBook2021`. For each experiment it prints the first round below 5% and 3% of each printed
rule next to the same rule with the floor, and the summary counts the experiments where the floor
changes one.

**`check_effort.py`** solves every worker council of an archive at the prices its proposal was
made at (the previous row's prices, 700 in round 1, as `csvgen.clj` lines 884–889 show) with a
numerical maximiser, and compares the output and effort `pequod-cljs` recorded for it, grouped by
the number of inputs. The prices after the round's update are the control that should not match.
It also lists every line of `csvgen.clj` that mentions effort.

**`check_history.py`** clones `pequod-plus` and `pequod-cljs` without their LFS objects and prints,
for each statement of entries 8 and 9, the git or text command that bears on it and its raw
output; where a statement can be compared mechanically, both sides are printed with an `equal`
column. The search of the full history of `pequod-cljs` for timings states its patterns and prints
every line they match, with `time lein run` as a control that has to match. It also searches the
full message of every commit of both repositories with the same patterns, and checks that every
commit the page cites is among those searched.

**`docker/pequod-plus/run_all.py`** builds `pequod-plus` at `44a6d08` (the commit the wiki
cites), at `44a6d08` with `edits/solution-5-x1-log-p3.json` applied, at `44d8c15` (the head of
branch `db` on 2026-09-28) and at `10da5d2` (the code of the author's timed runs). In each it runs
probes that load the program's namespaces and call its functions:

| Probe | What it calls |
|---|---|
| `probe/src/probe/demand_by_commodity.clj` | `update-surpluses-prices` (the in-memory step) on two goods per category and two consumer councils, and one round of `iterate-plan-improved` (the SQLite step) on a 100-goods economy; prints supply and demand per commodity next to the per-commodity and category-wide sums |
| `probe/src/probe/category_multiplier.clj` | `calculate-price-deltas`, `get-delta` and `force-to-one` for pairs of commodities, then which multiplier each applied step was computed from on both per-round paths |
| `probe/src/probe/closed_forms.clj` | `csvgen/process-wc` (or `util/proposal` where `csvgen` does not load) on 31,409 worker councils: every council of dep1ex01 at the last year-one prices of `dep1ex61.csv`, samples at uniform prices, and draws in the ranges of the program's generator |

`verify_closed_forms.py` checks each returned solution against the first-order conditions and a
scipy maximiser, without `pequod-plus` code (`make_closed_form_cases.py` writes the cases).

The source lines `run_all.py` prints for each commit are listed in
`docker/pequod-plus/lines/<commit>.json`: file, line number, the sha256 of the line as committed,
and, for lines too long to print whole, a range of columns. `_source_lines.py` checks every listed
line against its hash before printing any, and stops naming the commit, file and line of every
mismatch. The edited image prints its base commit's listing, checked on the base image, after
confirming that its file equals the base file with the edit set applied.

**`docker/pequod-cljs/run.py`** builds `pequod-cljs` at `71e44d3` (OpenJDK 11.0.16, Leiningen
2.9.8), puts in the public `dep1ex01` renamed to `dep1ex61` after checking it against the LFS
pointer, and runs `lein run -m pequod-cljs.csvgen ex61` as `bin/bigger_csv.sh` does: 12 rounds as
committed, then 3 rounds each with `edits/rule-book-p181.json` and `edits/rule-paper-p7.json`. It
compares every column with the committed `dep1ex61.csv`, recomputes the steps under each rule, and
prints the time and memory of each run. The tree at `71e44d3` lacks the other data namespaces
`csvgen.clj` requires; each is replaced by a stub file defining `ccs` and `wcs` as nil, and
`csvgen.clj` itself runs unchanged (its git blob id is printed before each run). Only year one is
run: year two perturbs the exponents with an unseeded `rand-nth`.

## Tests

`tests/upstream/` holds the tests of these scripts. They run offline, without Docker, as part of
`pytest` from the repository root. A few read `csvgen.clj` or an output CSV from the cache and skip
when it is absent.
