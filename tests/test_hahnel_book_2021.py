"""The Hahnel (2021) prefab: the program's price rule and the procedure built on it.

The rule is the one ``msszczep/pequod-cljs`` ran to produce the book's tables,
``src/clj/pequod_cljs/csvgen.clj`` at commit ``71e44d3``. Three sources check it here, none of
them the prefab's own code:

* the rule written out by hand, one commodity at a time, in the unit tests below;
* ``research/bench/endowment.py`` in mode ``cljs_lagged``, an independent numpy
  reimplementation over a different data layout, for round counts and prices;
* the program's own per-round output, when ``DEMPLAN_UPSTREAM_DIR`` names a directory holding
  it; see ``tests/reference/pequod_cljs.py``. Those files are not in the repository.
"""

from __future__ import annotations

import dataclasses
import gc
import math
import time
from decimal import ROUND_DOWN, Decimal

import numpy as np
import pytest

from demplan import INDICATIVE_PRICE, StatedPlan, check_determinism, run
from demplan.prefabs.hahnel import (
    NEXT_INDICATIVE_PRICE,
    PRICE_RULE_STATE,
    Book2021Rule,
    HahnelBook2021,
    WarmStart,
    book_2021_rule,
    real_gdp_growth,
)
from reference import synthetic
from reference.dep1ex_numpy import (
    Dep1exLayout,
    economy_from_repro,
    parse_dep1ex,
    reference_first_round,
    reference_run,
    unified_price,
)
from reference.paths import dep1ex_available, dep1ex_path
from reference.pequod_cljs import read_first_year, read_years, upstream_csv

TIMING_ALLOWANCE = 1.3

SYNTHETIC_LAYOUT = Dep1exLayout(
    n_priv=synthetic.N_PER_CLASS, n_pub=synthetic.N_PER_CLASS, n_goods=synthetic.N_PER_CLASS
)

PUBLISHED_EXPERIMENTS = (1, 2, 3, 4, 5)

ROUNDS_AT_5_PERCENT = {1: 12, 2: 12, 3: 12, 4: 12, 5: 12}
"""Cold start at 700, endowment 1000, threshold 5 percent, dep1ex01 to 05.

Hahnel (2021), ch. 9, Table 9.1 prints 12 for each of the five experiments.
"""

ROUNDS_AT_3_PERCENT = {1: 19, 2: 20, 3: 19, 4: 19, 5: 19}
"""The same runs at the 3 percent threshold.

These are the program's own output: pequod-cljs at ``71e44d3`` ran on dep1ex61 to 65, which are
dep1ex01 to 05, and reached 3 percent after 19, 20, 19, 19 and 19 rounds. Hahnel (2021), ch. 9,
Table 9.2 prints 19, 19, 20, 19, 19, which is the same five numbers with experiments 2 and 3
transposed in print.
"""

WORST_IMBALANCE_RTOL = 1e-12
"""How closely the prefab's worst imbalance per round has to follow the program's.

The program prints every number at full double precision. Summing thirty thousand councils in
another order and taking ``exp`` and ``log`` in another library moves the last digits, so a
bit-for-bit match is out of reach for any reimplementation. Measured on dep1ex01 to 05 over
every first-year round, the worst imbalance agrees to 2.4e-13 relative.
"""

PRICE_RTOL = 1e-13
"""Measured agreement of the price after every first-year round: 5.3e-15 relative."""

MULTIPLIER_ATOL = 1e-12
"""Measured agreement of the carried multiplier (``pdlist``) after every round: 4.1e-14."""

TABLE_9_4_GDP = {1: "2.6", 2: "2.549", 3: "2.528", 4: "2.271", 5: "2.32"}
"""Real GDP growth in percent from year one to year two, dep1ex01 to 05.

Hahnel (2021), ch. 9, Table 9.4, p. 183, as printed. Measured against the program's own output
for these runs (2.60078..., 2.54957..., 2.52815..., 2.27138..., 2.32095...), each printed value is
the growth truncated to three decimals, not rounded, with trailing zeros dropped.
"""


def program_step(imbalance: float, multiplier: float) -> float:
    """``get-deltas`` of csvgen.clj for one commodity, in plain floats.

    ``max(0.001, min(base, |base * multiplier|))`` with ``base = 1.05 - 0.5**imbalance``.
    Written out here from the rule's statement rather than taken from the prefab.
    """
    base = 1.05 - 0.5**imbalance
    return max(0.001, min(base, abs(base * multiplier)))


def read_only(values) -> np.ndarray:
    array = np.array(values, dtype=np.float64)
    array.flags.writeable = False
    return array


class Recorder:
    """``book_2021_rule``, keeping a copy of what every round handed it and got back."""

    def __init__(self):
        self.worst = []
        self.handed_price = []
        self.handed_state = []
        self.next_price = []
        self.next_state = []

    def initial_state(self, n_commodities):
        return book_2021_rule.initial_state(n_commodities)

    def __call__(self, price, surplus, imbalance, state):
        next_price, next_state = book_2021_rule(price, surplus, imbalance, state)
        self.worst.append(float(np.max(imbalance)))
        self.handed_price.append(np.array(price, copy=True))
        self.handed_state.append(np.array(state, copy=True))
        self.next_price.append(np.array(next_price, copy=True))
        self.next_state.append(np.array(next_state, copy=True))
        return next_price, next_state


class TestTheRuleOnItsOwn:
    """One step of the rule, checked against numbers worked out from its statement."""

    PRICE = (700.0, 700.0, 700.0, 700.0, 700.0, 700.0)
    SURPLUS = (5.0, -5.0, 1.0, -2.0, 0.0, 3.0)
    IMBALANCE = (1.0, 0.1, 0.002, 0.5, 0.0, 0.3)
    STATE = (0.25, 0.25, 0.002, 3.0, 0.25, -0.5)

    def step(self):
        return book_2021_rule(
            read_only(self.PRICE),
            read_only(self.SURPLUS),
            read_only(self.IMBALANCE),
            read_only(self.STATE),
        )

    def test_a_worked_round(self):
        """Six commodities, one per case of the rule.

        0: surplus, imbalance 1 taken uncapped in the exponent, step ``0.55 * 0.25``;
        1: shortage, the multiplier is the state handed in, not this round's imbalance;
        2: a step below 0.001 is raised to 0.001;
        3: a multiplier above 1 leaves the step at ``base``;
        4: balance keeps the price;
        5: a negative multiplier counts by its size.
        """
        next_price, _ = self.step()
        np.testing.assert_allclose(
            next_price,
            [603.75, 720.4692264810587, 699.3, 940.0252531694166, 700.0, 616.7883387246825],
            rtol=1e-13,
            atol=0,
        )

    def test_the_next_state_is_this_rounds_imbalance_capped_at_a_quarter(self):
        _, next_state = self.step()
        np.testing.assert_array_equal(next_state, [0.25, 0.1, 0.002, 0.25, 0.0, 0.25])

    def test_each_price_follows_the_step_written_out_by_hand(self):
        next_price, _ = self.step()
        for at, (price, surplus, imbalance, state) in enumerate(
            zip(self.PRICE, self.SURPLUS, self.IMBALANCE, self.STATE)
        ):
            step = program_step(imbalance, state)
            expected = price * (1 - step) if surplus > 0 else price * (1 + step) if surplus < 0 else price
            assert math.isclose(next_price[at], expected, rel_tol=1e-15), at

    def test_the_exponent_takes_the_imbalance_uncapped(self):
        """With the exponent capped at 0.25 the first commodity would fall to 663.41."""
        next_price, _ = self.step()
        assert not math.isclose(next_price[0], 663.4068726694001, rel_tol=1e-6)

    def test_the_multiplier_is_the_state_not_the_current_imbalance(self):
        """The same round with the state set to this round's capped imbalance steps less."""
        lagged, _ = self.step()
        current, _ = book_2021_rule(
            read_only(self.PRICE),
            read_only(self.SURPLUS),
            read_only(self.IMBALANCE),
            read_only(np.minimum(self.IMBALANCE, 0.25)),
        )
        assert lagged[1] != current[1]
        assert math.isclose(current[1], 700.0 * (1 + program_step(0.1, 0.1)), rel_tol=1e-15)

    def test_the_results_are_float64_arrays_of_the_commodity_count(self):
        next_price, next_state = self.step()
        for array in (next_price, next_state):
            assert isinstance(array, np.ndarray)
            assert array.dtype == np.float64
            assert array.shape == (len(self.PRICE),)

    def test_the_initial_state_is_a_quarter_everywhere(self):
        """csvgen.clj starts every commodity's ``pdlist`` entry at 0.25."""
        state = book_2021_rule.initial_state(7)
        assert isinstance(state, np.ndarray)
        assert state.dtype == np.float64
        np.testing.assert_array_equal(state, np.full(7, 0.25))

    def test_the_initial_state_is_a_fresh_array_every_time(self):
        first = book_2021_rule.initial_state(3)
        second = book_2021_rule.initial_state(3)
        assert not np.shares_memory(first, second)

    def test_the_rule_is_a_frozen_dataclass_without_fields(self):
        assert dataclasses.is_dataclass(Book2021Rule)
        assert dataclasses.fields(Book2021Rule) == ()
        assert isinstance(book_2021_rule, Book2021Rule)
        with pytest.raises(dataclasses.FrozenInstanceError):
            book_2021_rule.anything = 1


class TestTheProcedure:
    def test_the_fields_in_order_with_their_defaults(self):
        assert [(field.name, field.default) for field in dataclasses.fields(HahnelBook2021)] == [
            ("threshold_pct", 5.0),
            ("max_rounds", 250),
            ("initial_price", 700.0),
            ("initial_rule_state", None),
            ("record_trajectory", False),
            ("price_rule", None),
        ]

    def test_it_is_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            HahnelBook2021().threshold_pct = 3.0

    def test_the_default_rule_is_the_programs(self, synthetic_economy):
        default = run(HahnelBook2021(), synthetic_economy, seed=0)
        named = run(HahnelBook2021(price_rule=book_2021_rule), synthetic_economy, seed=0)
        assert default.summary.rounds == named.summary.rounds
        for key in (INDICATIVE_PRICE, NEXT_INDICATIVE_PRICE):
            np.testing.assert_array_equal(default.plan.valuation[key], named.plan.valuation[key])
        np.testing.assert_array_equal(
            default.plan.extra[PRICE_RULE_STATE], named.plan.extra[PRICE_RULE_STATE]
        )

    def test_the_default_run_starts_from_the_rules_initial_state(self, synthetic_economy):
        rule = Recorder()
        run(HahnelBook2021(price_rule=rule, max_rounds=1), synthetic_economy, seed=0)
        np.testing.assert_array_equal(
            rule.handed_state[0], np.full(synthetic_economy.n_commodities, 0.25)
        )

    def test_the_seed_does_not_change_the_result(self, synthetic_economy):
        first = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        second = run(HahnelBook2021(), synthetic_economy, seed=2**63).plan
        np.testing.assert_array_equal(first.output, second.output)
        np.testing.assert_array_equal(
            first.valuation[NEXT_INDICATIVE_PRICE], second.valuation[NEXT_INDICATIVE_PRICE]
        )

    def test_the_same_procedure_solved_again_is_bit_identical(self, synthetic_economy):
        report = check_determinism(HahnelBook2021(), synthetic_economy, 0, n=3)
        assert report.identical is True
        assert report.differing_fields == []


class TestInitialPrice:
    """A scalar is a flat cold start; a vector of one price per commodity is a warm start."""

    def warm_price(self, economy):
        return 500.0 + 25.0 * np.arange(economy.n_commodities, dtype=np.float64)

    def test_a_vector_is_the_price_of_the_first_round(self, synthetic_economy):
        price = self.warm_price(synthetic_economy)
        result = run(
            HahnelBook2021(initial_price=price, record_trajectory=True, max_rounds=2),
            synthetic_economy,
            seed=0,
        )
        np.testing.assert_array_equal(
            result.summary.trajectory[0].valuation[INDICATIVE_PRICE], price
        )

    def test_a_scalar_is_the_same_run_as_its_flat_vector(self, synthetic_economy):
        flat = np.full(synthetic_economy.n_commodities, 640.0)
        scalar = run(HahnelBook2021(initial_price=640.0), synthetic_economy, seed=0)
        vector = run(HahnelBook2021(initial_price=flat), synthetic_economy, seed=0)
        assert scalar.summary.rounds == vector.summary.rounds
        for key in (INDICATIVE_PRICE, NEXT_INDICATIVE_PRICE):
            np.testing.assert_array_equal(scalar.plan.valuation[key], vector.plan.valuation[key])
        np.testing.assert_array_equal(scalar.plan.output, vector.plan.output)

    def test_a_warm_start_changes_the_run(self, synthetic_economy):
        cold = run(HahnelBook2021(max_rounds=1), synthetic_economy, seed=0).plan
        warm = run(
            HahnelBook2021(initial_price=self.warm_price(synthetic_economy), max_rounds=1),
            synthetic_economy,
            seed=0,
        ).plan
        assert not np.array_equal(cold.output, warm.output)

    def test_the_vector_is_copied_rather_than_held(self, synthetic_economy):
        price = self.warm_price(synthetic_economy)
        kept = price.copy()
        result = run(
            HahnelBook2021(initial_price=price, record_trajectory=True, max_rounds=2),
            synthetic_economy,
            seed=0,
        )
        price[:] = 1.0
        np.testing.assert_array_equal(
            result.summary.trajectory[0].valuation[INDICATIVE_PRICE], kept
        )

    @pytest.mark.parametrize(
        "problem, make",
        [
            ("too short", lambda n: np.full(n - 1, 700.0)),
            ("too long", lambda n: np.full(n + 1, 700.0)),
            ("two-dimensional", lambda n: np.full((n, 1), 700.0)),
            ("NaN", lambda n: np.where(np.arange(n) == 2, np.nan, 700.0)),
            ("infinite", lambda n: np.where(np.arange(n) == 2, np.inf, 700.0)),
            ("zero", lambda n: np.where(np.arange(n) == 2, 0.0, 700.0)),
            ("negative", lambda n: np.where(np.arange(n) == 2, -700.0, 700.0)),
            ("not float64", lambda n: np.full(n, 700, dtype=np.int64)),
        ],
    )
    def test_an_invalid_vector_is_refused(self, synthetic_economy, problem, make):
        price = make(synthetic_economy.n_commodities)
        with pytest.raises(ValueError, match="initial_price"):
            run(HahnelBook2021(initial_price=price), synthetic_economy, seed=0)

    @pytest.mark.parametrize("price", [0.0, -700.0, float("nan"), float("inf")])
    def test_an_invalid_scalar_is_refused(self, synthetic_economy, price):
        with pytest.raises(ValueError, match="initial_price"):
            run(HahnelBook2021(initial_price=price), synthetic_economy, seed=0)


class TestInitialRuleState:
    def test_the_supplied_state_is_what_round_one_hands_the_rule(self, synthetic_economy):
        state = np.linspace(0.01, 0.3, synthetic_economy.n_commodities)
        rule = Recorder()
        run(
            HahnelBook2021(price_rule=rule, initial_rule_state=state, max_rounds=2),
            synthetic_economy,
            seed=0,
        )
        np.testing.assert_array_equal(rule.handed_state[0], state)

    def test_the_supplied_state_moves_the_first_step(self, synthetic_economy):
        """Round one's step is taken with the supplied multiplier, worked out by hand."""
        n = synthetic_economy.n_commodities
        state = np.full(n, 0.1)
        rule = Recorder()
        result = run(
            HahnelBook2021(price_rule=rule, initial_rule_state=state, max_rounds=1),
            synthetic_economy,
            seed=0,
        )
        seen = Recorder()
        run(HahnelBook2021(price_rule=seen, max_rounds=1), synthetic_economy, seed=0)
        np.testing.assert_array_equal(rule.worst, seen.worst)

        plan = result.plan
        price = np.asarray(plan.valuation[INDICATIVE_PRICE])
        surplus = (
            plan.total_output(synthetic_economy)
            + np.asarray(synthetic_economy.endowment)
            - plan.total_input_use(synthetic_economy)
            - np.asarray(plan.extra["consumer_demand"])
        )
        total = (
            plan.total_output(synthetic_economy)
            + np.asarray(synthetic_economy.endowment)
            + plan.total_input_use(synthetic_economy)
            + np.asarray(plan.extra["consumer_demand"])
        )
        imbalance = np.abs(2 * surplus) / total
        expected = [
            p * (1 - program_step(v, 0.1)) if s > 0 else p * (1 + program_step(v, 0.1))
            for p, s, v in zip(price, surplus, imbalance)
        ]
        np.testing.assert_allclose(
            plan.valuation[NEXT_INDICATIVE_PRICE], expected, rtol=1e-12, atol=0
        )
        assert not np.allclose(
            plan.valuation[NEXT_INDICATIVE_PRICE], seen.next_price[0], rtol=1e-6, atol=0
        )

    def test_a_supplied_state_is_not_asked_of_the_rule(self, synthetic_economy):
        class Counting(Recorder):
            calls = 0

            def initial_state(self, n_commodities):
                Counting.calls += 1
                return super().initial_state(n_commodities)

        state = np.full(synthetic_economy.n_commodities, 0.2)
        run(
            HahnelBook2021(price_rule=Counting(), initial_rule_state=state, max_rounds=3),
            synthetic_economy,
            seed=0,
        )
        assert Counting.calls == 0

    @pytest.mark.parametrize(
        "problem, make",
        [
            ("wrong length", lambda n: np.full(n + 1, 0.25)),
            ("zero-dimensional", lambda n: np.array(0.25)),
            ("NaN", lambda n: np.where(np.arange(n) == 1, np.nan, 0.25)),
            ("infinite", lambda n: np.where(np.arange(n) == 1, -np.inf, 0.25)),
            ("not float64", lambda n: np.full(n, 1, dtype=np.int64)),
            ("float32", lambda n: np.full(n, 0.25, dtype=np.float32)),
            ("a list", lambda n: [0.25] * n),
        ],
    )
    def test_an_invalid_state_is_refused(self, synthetic_economy, problem, make):
        state = make(synthetic_economy.n_commodities)
        with pytest.raises(ValueError, match="state"):
            run(HahnelBook2021(initial_rule_state=state), synthetic_economy, seed=0)


@pytest.fixture
def synthetic_reference(synthetic_reference_inputs):
    """``endowment.run`` in mode ``cljs_lagged`` on the synthetic economy, at 5 and at 3."""
    wc, cc, _, endowment = synthetic_reference_inputs
    return {
        threshold: reference_run(
            wc, cc, SYNTHETIC_LAYOUT, threshold=threshold, endowment_per_commodity=endowment
        )
        for threshold in (5.0, 3.0)
    }


class TestSyntheticAgainstTheReference:
    @pytest.mark.parametrize("threshold", [5.0, 3.0])
    def test_the_round_count(self, synthetic_economy, synthetic_reference, threshold):
        expected_rounds, _, _ = synthetic_reference[threshold]
        result = run(HahnelBook2021(threshold_pct=threshold), synthetic_economy, seed=0)
        assert result.summary.converged is True
        assert result.summary.rounds == expected_rounds

    @pytest.mark.parametrize("threshold", [5.0, 3.0])
    def test_the_final_prices(self, synthetic_economy, synthetic_reference, threshold):
        _, expected_prices, _ = synthetic_reference[threshold]
        result = run(HahnelBook2021(threshold_pct=threshold), synthetic_economy, seed=0)
        np.testing.assert_allclose(
            result.plan.valuation[INDICATIVE_PRICE],
            unified_price(expected_prices, SYNTHETIC_LAYOUT),
            rtol=1e-9,
            atol=0,
        )


@pytest.mark.slow
@pytest.mark.skipif(not dep1ex_available(1), reason="dep1ex01 archive not available")
class TestDep1ex01:
    def test_round_count_matches_the_reference(self, dep1ex01_parsed, dep1ex01_economy):
        wc, cc, layout = dep1ex01_parsed
        expected_rounds, _, _ = reference_run(wc, cc, layout)
        result = run(HahnelBook2021(), dep1ex01_economy, seed=0)
        assert result.summary.converged is True
        assert result.summary.rounds == expected_rounds

    def test_final_prices_match_the_reference(self, dep1ex01_parsed, dep1ex01_economy):
        wc, cc, layout = dep1ex01_parsed
        _, expected_prices, _ = reference_run(wc, cc, layout)
        result = run(HahnelBook2021(), dep1ex01_economy, seed=0)
        np.testing.assert_allclose(
            result.plan.valuation[INDICATIVE_PRICE],
            unified_price(expected_prices, layout),
            rtol=1e-9,
            atol=0,
        )

    def test_first_round_proposals_match_the_reference(self, dep1ex01_parsed, dep1ex01_economy):
        wc, cc, layout = dep1ex01_parsed
        expected_output, expected_input_use = reference_first_round(wc, cc, layout)
        first = run(
            HahnelBook2021(max_rounds=1, record_trajectory=True), dep1ex01_economy, seed=0
        ).plan
        np.testing.assert_allclose(first.output, expected_output, rtol=1e-12, atol=0)
        np.testing.assert_allclose(first.input_use, expected_input_use, rtol=1e-12, atol=0)

    def test_not_slower_than_the_reference(self, dep1ex01_parsed, dep1ex01_economy):
        wc, cc, layout = dep1ex01_parsed
        started = time.perf_counter()
        reference_run(wc, cc, layout)
        reference_seconds = time.perf_counter() - started
        result = run(HahnelBook2021(), dep1ex01_economy, seed=0)
        assert result.summary.wall_seconds <= TIMING_ALLOWANCE * reference_seconds, (
            f"prefab {result.summary.wall_seconds:.2f}s "
            f"vs reference {reference_seconds:.2f}s"
        )

    def test_determinism_report(self, dep1ex01_economy):
        report = check_determinism(HahnelBook2021(), dep1ex01_economy, 0, n=2)
        assert report.identical is True
        assert report.differing_fields == []


@pytest.fixture(scope="module", params=PUBLISHED_EXPERIMENTS, ids=lambda i: f"dep1ex0{i}")
def experiment(request):
    """``(index, layout, wc, cc, economy)`` for one of dep1ex01 to 05, parsed once."""
    index = request.param
    if not dep1ex_available(index):
        pytest.skip(f"dep1ex0{index} archive not available")
    wc, cc, layout = parse_dep1ex(dep1ex_path(index))
    yield index, layout, wc, cc, economy_from_repro(wc, cc, layout)
    gc.collect()


@pytest.fixture(scope="module")
def run_at_3_percent(experiment):
    """The prefab at the 3 percent threshold, with every round's rule inputs and outputs."""
    _, _, _, _, economy = experiment
    rule = Recorder()
    result = run(HahnelBook2021(threshold_pct=3.0, price_rule=rule), economy, seed=0)
    return result, rule


@pytest.mark.slow
class TestPublishedExperiments:
    def test_rounds_at_5_percent(self, experiment):
        index, layout, wc, cc, economy = experiment
        result = run(HahnelBook2021(), economy, seed=0)
        reference_rounds, _, _ = reference_run(wc, cc, layout, threshold=5.0)
        assert result.summary.converged is True
        assert result.summary.rounds == reference_rounds
        assert result.summary.rounds == ROUNDS_AT_5_PERCENT[index]

    def test_rounds_at_3_percent(self, experiment, run_at_3_percent):
        index, _, _, _, _ = experiment
        result, _ = run_at_3_percent
        assert result.summary.converged is True
        assert result.summary.rounds == ROUNDS_AT_3_PERCENT[index]


@pytest.fixture(scope="module")
def program_rounds(experiment):
    """The program's first-year rounds on this experiment, or a skip."""
    index, layout, _, _, _ = experiment
    path = upstream_csv(index)
    if path is None:
        pytest.skip(f"pequod-cljs output dep1ex6{index}.csv not available")
    return read_first_year(path, layout)


@pytest.mark.slow
class TestAgainstTheProgramsOwnOutput:
    """The prefab against what pequod-cljs printed, round by round.

    The program ran each experiment to the 3 percent threshold, so its first year has one row
    per round of the prefab's 3 percent run.
    """

    def test_every_rounds_worst_imbalance(self, program_rounds, run_at_3_percent):
        result, rule = run_at_3_percent
        assert len(program_rounds) == result.summary.rounds == len(rule.worst)
        printed = np.array([row.threshold_report.max() for row in program_rounds])
        np.testing.assert_allclose(
            100.0 * np.array(rule.worst), printed, rtol=WORST_IMBALANCE_RTOL, atol=0
        )

    def test_every_rounds_next_price_and_multiplier(self, program_rounds, run_at_3_percent):
        result, rule = run_at_3_percent
        assert len(program_rounds) == len(rule.next_price)
        for number, (row, price, state) in enumerate(
            zip(program_rounds, rule.next_price, rule.next_state), start=1
        ):
            np.testing.assert_allclose(
                price, row.price_after, rtol=PRICE_RTOL, atol=0, err_msg=f"round {number}"
            )
            np.testing.assert_allclose(
                state, row.pdlist, rtol=0, atol=MULTIPLIER_ATOL, err_msg=f"round {number}"
            )

    def test_the_final_plan_files_the_last_rounds_rule_output(self, run_at_3_percent):
        result, rule = run_at_3_percent
        np.testing.assert_array_equal(
            result.plan.valuation[NEXT_INDICATIVE_PRICE], rule.next_price[-1]
        )
        np.testing.assert_array_equal(result.plan.extra[PRICE_RULE_STATE], rule.next_state[-1])

    def test_the_rule_repeats_each_update_from_the_programs_own_inputs(
        self, experiment, program_rounds
    ):
        """Each round fed the program's balance, price and multiplier, one round at a time.

        The first round starts from the prefab's cold-start price and the rule's own initial
        state; every later round from the price and multiplier the program printed for the
        round before. The multiplier comes out exactly, the price to the last place.
        """
        _, layout, _, _, _ = experiment
        n = layout.n_commodities
        price = np.full(n, HahnelBook2021().initial_price)
        state = book_2021_rule.initial_state(n)
        for number, row in enumerate(program_rounds, start=1):
            imbalance = np.abs(2 * row.surplus) / (row.supply + row.demand)
            next_price, next_state = book_2021_rule(
                read_only(price), read_only(row.surplus), read_only(imbalance), read_only(state)
            )
            np.testing.assert_array_equal(next_state, row.pdlist, err_msg=f"round {number}")
            np.testing.assert_allclose(
                next_price, row.price_after, rtol=1e-15, atol=0, err_msg=f"round {number}"
            )
            price, state = row.price_after, row.pdlist

    def test_the_rule_repeats_each_step_the_program_printed(self, experiment, program_rounds):
        """The step, read off a unit price so that no other factor is in the product."""
        _, layout, _, _, _ = experiment
        n = layout.n_commodities
        state = book_2021_rule.initial_state(n)
        for number, row in enumerate(program_rounds, start=1):
            imbalance = np.abs(2 * row.surplus) / (row.supply + row.demand)
            moved = row.surplus != 0
            next_price, _ = book_2021_rule(
                read_only(np.ones(n)), read_only(row.surplus), read_only(imbalance), read_only(state)
            )
            assert moved.sum() > 0
            np.testing.assert_allclose(
                np.abs(next_price - 1.0)[moved],
                row.step[moved],
                rtol=1e-12,
                atol=0,
                err_msg=f"round {number}",
            )
            state = row.pdlist


@pytest.fixture(scope="module")
def program_years(experiment):
    """Both years the program ran on this experiment, or a skip."""
    index, layout, _, _, _ = experiment
    path = upstream_csv(index)
    if path is None:
        pytest.skip(f"pequod-cljs output dep1ex6{index}.csv not available")
    years = read_years(path, layout)
    assert len(years) == 2
    return years


def year_end_plan(economy, year) -> StatedPlan:
    """The program's last round of ``year`` as a plan: each unit's output, the final price and
    ``pdlist``. Nothing else of the round is read by what these tests call."""
    last = year.rounds[-1]
    return StatedPlan(
        output=year.last_unit_output,
        input_use=np.zeros(economy.n_inputs),
        consumption=None,
        consumption_commodity=None,
        shared_use=None,
        valuation={NEXT_INDICATIVE_PRICE: last.price_after},
        extra={PRICE_RULE_STATE: last.pdlist},
    )


@pytest.mark.slow
class TestAgainstTheProgramsSecondYear:
    """Year two of the program: a warm start from year one's end, and the book's GDP growth.

    Between the years the program perturbed the exponents with random draws that are not
    recoverable, so year two is not rerun here; its printed balance is taken as given.
    """

    def test_year_twos_first_round_repeats_the_programs_update_from_year_ones_end(
        self, experiment, program_years
    ):
        """``WarmStart`` on year one's last round, then one update on year two's first balance.

        The rule gets year two's first-round balance as the program printed it, and the price
        and multiplier the warm-started procedure starts from.
        """
        _, _, _, _, economy = experiment
        first_year, second_year = program_years
        procedure = WarmStart()(year_end_plan(economy, first_year))
        rule = book_2021_rule if procedure.price_rule is None else procedure.price_rule
        opening = second_year.rounds[0]
        imbalance = np.abs(2 * opening.surplus) / (opening.supply + opening.demand)

        next_price, next_state = rule(
            read_only(procedure.initial_price),
            read_only(opening.surplus),
            read_only(imbalance),
            read_only(procedure.initial_rule_state),
        )

        np.testing.assert_array_equal(next_state, opening.pdlist)
        np.testing.assert_allclose(next_price, opening.price_after, rtol=1e-15, atol=0)

    def test_year_twos_first_step_is_the_one_the_program_printed(
        self, experiment, program_years
    ):
        """The step, read off a unit price so that no other factor is in the product."""
        _, layout, _, _, economy = experiment
        first_year, second_year = program_years
        procedure = WarmStart()(year_end_plan(economy, first_year))
        rule = book_2021_rule if procedure.price_rule is None else procedure.price_rule
        opening = second_year.rounds[0]
        imbalance = np.abs(2 * opening.surplus) / (opening.supply + opening.demand)
        moved = opening.surplus != 0

        next_price, _ = rule(
            read_only(np.ones(layout.n_commodities)),
            read_only(opening.surplus),
            read_only(imbalance),
            read_only(procedure.initial_rule_state),
        )

        assert moved.sum() > 0
        np.testing.assert_allclose(
            np.abs(next_price - 1.0)[moved], opening.step[moved], rtol=1e-12, atol=0
        )

    def test_real_gdp_growth_of_the_programs_two_years_is_table_9_4(
        self, experiment, program_years
    ):
        index, _, _, _, economy = experiment
        first_year, second_year = program_years
        growth = real_gdp_growth(
            economy,
            year_end_plan(economy, first_year),
            economy,
            year_end_plan(economy, second_year),
        )
        truncated = Decimal(repr(growth)).quantize(Decimal("0.001"), rounding=ROUND_DOWN)
        assert truncated == Decimal(TABLE_9_4_GDP[index]), f"growth {growth!r}"
