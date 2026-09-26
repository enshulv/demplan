# Adversarial Review: Work Package 1 (Stage 0 plus Stage 1) — 2026-09-05

**Method**: an adversarial review conducted by a reviewer with no context on this session, working from a presumption of guilt,
reviewing tests before code, with mutation testing mandatory. This document is an excerpt of the report (the blocking and
non-blocking sections plus instrumentation notes); the complete list of attempted attacks is not included here.
Disposition: five blocking and nine non-blocking findings were sent on for fixes; see `progress.md`.

Commit reviewed: 909903a. The mutation tables and reports are archived in
[mutation-tables-2026-09-05/](mutation-tables-2026-09-05/) (`line1-*`); the replay results after the fix are in
`line1-replay-after-fix.json`: all five surviving mutants were killed. Baseline: cargo 54 passed; pytest 286 passed in full.
69 mutants (47 Python, 22 Rust), with both batches carrying negative and positive controls.

## blocking[]

### B1. The dep1ex loader folds `:product` numbers into `n_goods`, conjuring commodities with an endowment out of nowhere; no price-update mechanism ever converges as a result

`crates/cyberstride-core/src/dep1ex.rs:852-865` (`largest_commodity_number`) takes the maximum of `units.product` and
`units.input_number` together. `:product` numbers private goods for `:industry 0` and public goods for `:industry 2`; these do
not share a numbering space with intermediate goods, natural resources, or labor. The reference implementation,
`research/bench/repro.py:223`, uses only the input segment: `n_goods = int(wc["coef"].max()) + 1`.

Trigger: any archive where `max(:product) > max(input number)`. In dep1ex01–05, each of the five kinds has 100 commodities,
so the bug does not show up there.
Consequence: the extra phantom natural-resource and labor commodities carry an `endowment` but no input or consumption index at
all; the imbalance sits permanently at 200%, prices adjust downward every round, but demand is always 0.

Actual run (`probe_b3.py`, `probe_b4.py`, n_priv=4, n_pub=2, input numbers only going up to 3): the correct layout has 15
commodities, the loader produces 18, with numbers 13 and 17 being phantoms; it fails to converge in 250 rounds.

No test caught this, because the `reference` fixture in `tests/test_core_load_dep1ex.py:63` copies the implementation's own
rule (`n_goods = int(max(wc["coef"][wc["mask"]].max(), wc["product"].max())) + 1`), while `tests/reference/dep1ex_numpy.py:83` uses
the reference rule. The fixture in `crates/cyberstride-core/tests/load_dep1ex.rs:8-11` has `max(:product)=2 < 3`, which cannot
distinguish the two rules. Mutant `rs-ngoods-input-numbers-only` (swap in the reference rule) survived; every test stayed green.

### B2. `Economy` claims a Cobb-Douglas technology that is not dep1ex's real technology: the actual production function includes an effort factor, and `Plan` has nowhere to put it

Upstream's `solution-3` and `solution-4` in `upstream/pequod-plus/src/clj/pequod_plus/csvgen.clj` return `effort` in addition
to `output` and `x_j` (all eight archives return it). Transcribing upstream's effort expression and measuring it gives
`max |lnQ − ln(a · effort^c · Π x^b)| = 8.9e-16` (`probe_e.py`). In other words, dep1ex's production function is
**`Q = a · e^c · Π x_j^{b_j}`**, where `c` is effort's exponent in the production function.

Consequence (`probe_d.py`, a converged dep1ex01 plan): `output / (technology_scale · Π x^input_coefficient)` has a minimum of
1.0015, a median of 1.0863, and a maximum of 1.3363; only 34 out of 30,000 units fall within 1% of the declared Cobb-Douglas
relationship. `tools.cobb_douglas.cost_minimizing_inputs_flat`, run on the same `Economy`, computes an input mix different from
the prefab's, and nothing warns the researcher of this. Every unit in the dep1ex archives carries `:effort 0.5`, which the loader
discards.

### B3. `run(HahnelSlides2020(), …)` can report `converged=True` when the plan is entirely `NaN`

`hahnel_2020_slides.py:122` uses `np.nanmax(imbalance)`; when supply or demand hits `inf`, `_relative_imbalance` produces
`inf/inf = NaN`, which is then treated as perfect balance. `iterate`'s divergence detection only switches on when `plan_of` is
given, and the prefab defaults to `record_trajectory=False`.

Trigger: the closed-form solution's denominator `D = effort_c − effort_k + effort_k·Σb` is slightly negative. In a synthetic
economy where unit 0's `effort_c` is set to `k − k·B − 1e-5` (`probe_g3.py`): `converged=True, rounds=2`, `plan.output` is all
`NaN`, and `Plan.validate` raises `SchemaError`. With `record_trajectory=True`, it instead gives `converged=False, rounds=1`.
The reference `endowment.run` reports the same false convergence on the same economy (invisible to a numerical diff). On
dep1ex01–05, `|D|` never drops below 0.382, so this defect is not live on the published data.

### B4. Public-good material balance cannot be reconstructed from `Plan`; the README's example is permanently 0 for public goods

`hahnel_2020_slides.py:121` defines `provision` as the supply of a public good, so the gap in the README's "ten lines"
example is permanently 0 for public goods. Actual run (`probe_f.py`, dep1ex01): the README gap on public goods is at most 0.0,
while the mechanism's own measured public-good imbalance has a max of 0.0348 and a mean of 0.0329, with 100 out of 100 exceeding
1%. `Plan` has no field recording how much of each public good consumers wanted. This collides with the spec requirement that any
metric be reconstructible from the output.

### B5. Segmented commodity numbering never checks that it stays within its own segment's bounds; going out of bounds silently spills into the neighboring segment

`dep1ex.rs:767` (`base + product − 1`) and `:775` (`segment_base + value − 1`) never check that a number stays within the
length of its own segment. Actual run (`probe_j.py`, n_priv=n_pub=2, n_goods=3): a private unit whose `:product` number overruns
the private segment ends up producing a good tagged as public; an intermediate-good input numbered 0 lands on a public good.
`commodity_kind` is the basis on which `endowment_use`, material balance, and public-good pricing all dispatch. No test covers
this.

## non_blocking[]

| # | Location | Description |
|---|---|---|
| N1 | `economy.py:88-91` | `_freeze_array` rewrites the caller's array in place; after constructing an `Economy`, the buffer still in the caller's hands becomes read-only |
| N2 | `economy.py:8-11` | Read-only is just a numpy flag; `arr.flags.writeable = True` can flip it back. The docstring should state how strong this guarantee actually is |
| N3 | `economy.rs:510-547` | Rust's `validate` is weaker than Python's: it does not check `extra` F64 values for finiteness, and does not check column-mapping keys for dtype, range, or column count |
| N4 | `test_hahnel_2020_slides.py:110-119` | `test_the_reported_price_is_the_one_the_proposals_used` only asserts that two vectors are unequal, which cannot falsify its own name |
| N5 | `test_procedure.py:157-162` | `test_the_recorder_is_cleared_after_run` cannot be falsified: deleting `_recorder.reset(token)` at `procedure.py:61` survives |
| N6 | `hahnel_2020_slides.py:90` | `effort_s` is permanently 1.0 in dep1ex01 and in the synthetic economies, so the `c·log(s)` term is never exercised; a sign-flip mutant survives |
| N7 | `hahnel_2020_slides.py:231-233` | `record_trajectory=True` returns `trajectory[-1]`; changing it to `[0]` survives |
| N8 | `hahnel_2020_slides.py:104` | Changing `consumption_commodity` to just take the first k columns survives: in both fixtures, the private-good columns happen to come first |
| N9 | `hahnel_2020_slides.py:176-182` | The guard in `_require_cobb_douglas` has no test; neutralizing it survives |
| N10 | `dep1ex.rs:170`, `cyberstride-py/src/lib.rs:55-60` | The mapping from `LoadError::Schema` to `_core.SchemaError` is never exercised by a test (measurement confirms it works) |
| N11 | `test_hahnel_2020_slides.py:190-199` | `test_not_slower_than_the_reference` compares timing ratios from a single run; it sits behind neither the `slow` marker nor a release gate |
| N12 | `test_hahnel_2020_slides.py:32,228` | The multiset literals themselves have no discriminating power; each group relies on the accompanying `cold5_ours == cold5_reference` |
| N13 | `tests/load_dep1ex.rs:8-11` | The comment claims the fixture can discriminate between the two `n_goods` rules; it cannot (see B1) |
| N14 | `pyproject.toml:25`, `tests/conftest.py:24` | The `slow` marker is registered twice, with different descriptions |
| N15 | `economy.py:316-323` | The `base is None` and `base.ndim != 2` branches of `_validate_column_mapping` have no test case |
| N16 | `research/bench/bench_v1.py:52` | The `worst_imbalance_pct` field does not exist; that column is permanently `NaN` |
| N17 | `README.md:72-93` | Running the second example as written raises `AttributeError` (incomplete by design, but it reads like a complete, copyable class) |

## Instrumentation notes

Python mutation batches need `PYTHONDONTWRITEBYTECODE=1`, with `__pycache__` cleared beforehand: a `.pyc` is validated by
`(mtime, size)`, and if the byte-for-byte restore lands within the same second, the stale mutated bytecode keeps getting used
instead. The first round of this review produced two false kills for exactly this reason. `cd-share-not-normalised` is an
equivalent mutant (`log(B)` cancels between the two terms; measured across 2000 random inputs, the largest difference is
1.4e-14), not a real gap.
