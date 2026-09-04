"""The 2020 slides prefab, measured against the numpy reference in ``research/bench``.

Every expected number here is produced by running ``endowment.py``, which is an independent
implementation of the same price rule over a different data layout. The two published
constants that appear literally are the 2020 slides' own figures for the five dep1ex
experiments; they enter through the reference run, not through the prefab.
"""

from __future__ import annotations

import gc
import statistics
import time

import numpy as np
import pytest

from cyberstride import INDICATIVE_PRICE, CommodityKind, check_determinism, run
from cyberstride.prefabs import HahnelSlides2020
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

DEP1EX_COUNT = 5
COLD_5_PERCENT_ROUNDS = [13, 13, 13, 14, 14]
COLD_3_PERCENT_MEAN = 22.8
TIMING_ALLOWANCE = 1.3

SYNTHETIC_LAYOUT = Dep1exLayout(
    n_priv=synthetic.N_PER_CLASS, n_pub=synthetic.N_PER_CLASS, n_goods=synthetic.N_PER_CLASS
)


@pytest.fixture
def synthetic_reference_rounds(synthetic_reference_inputs):
    """``endowment.run`` on the synthetic economy: ``(rounds, prices, worst_percent)``."""
    wc, cc, _, endowment = synthetic_reference_inputs
    return reference_run(wc, cc, SYNTHETIC_LAYOUT, threshold=5.0, endowment_per_commodity=endowment)


class TestSyntheticEconomy:
    def test_it_converges(self, synthetic_economy):
        result = run(HahnelSlides2020(), synthetic_economy, seed=0)
        assert result.summary.converged is True
        assert result.summary.rounds is not None
        assert result.summary.rounds < HahnelSlides2020().max_rounds

    def test_round_count_matches_the_reference(self, synthetic_economy, synthetic_reference_rounds):
        expected_rounds, _, _ = synthetic_reference_rounds
        result = run(HahnelSlides2020(), synthetic_economy, seed=0)
        assert result.summary.rounds == expected_rounds

    def test_final_prices_match_the_reference(self, synthetic_economy, synthetic_reference_rounds):
        _, expected_prices, _ = synthetic_reference_rounds
        result = run(HahnelSlides2020(), synthetic_economy, seed=0)
        np.testing.assert_allclose(
            result.plan.valuation[INDICATIVE_PRICE],
            unified_price(expected_prices, SYNTHETIC_LAYOUT),
            rtol=1e-9,
            atol=0,
        )

    def test_the_plan_satisfies_the_schema(self, synthetic_economy):
        result = run(HahnelSlides2020(), synthetic_economy, seed=0)
        result.plan.validate(synthetic_economy)

    def test_material_balance_at_the_reported_threshold(self, synthetic_economy):
        """Public goods sit at zero here by construction; the reference run covers them."""
        procedure = HahnelSlides2020()
        plan = run(procedure, synthetic_economy, seed=0).plan
        supply = plan.total_output(synthetic_economy) + np.asarray(synthetic_economy.endowment)
        demand = (
            plan.total_input_use(synthetic_economy)
            + plan.total_consumption(synthetic_economy)
            + np.asarray(plan.provision)
        )
        total = supply + demand
        imbalance = np.where(total > 0, np.abs(2 * (supply - demand)) / np.where(total > 0, total, 1.0), 0.0)
        assert imbalance.max() * 100 < procedure.threshold_pct

    def test_consumption_columns_are_the_private_goods(self, synthetic_economy):
        plan = run(HahnelSlides2020(), synthetic_economy, seed=0).plan
        kinds = np.asarray(synthetic_economy.commodity_kind)
        columns = np.asarray(plan.consumption_commodity)
        assert np.all(kinds[columns] == CommodityKind.PRIVATE_GOOD)
        np.testing.assert_array_equal(
            columns, synthetic_economy.commodities_of_kind(CommodityKind.PRIVATE_GOOD)
        )
        assert plan.consumption.shape == (synthetic_economy.n_consumers, columns.shape[0])
        assert np.all(plan.consumption > 0.0)

    def test_provision_is_confined_to_public_goods(self, synthetic_economy):
        plan = run(HahnelSlides2020(), synthetic_economy, seed=0).plan
        kinds = np.asarray(synthetic_economy.commodity_kind)
        public = kinds == CommodityKind.PUBLIC_GOOD
        provision = np.asarray(plan.provision)
        assert np.all(provision[public] > 0.0)
        assert provision[~public].sum() == 0.0
        np.testing.assert_allclose(
            provision[public], plan.total_output(synthetic_economy)[public]
        )

    def test_the_reported_price_is_the_one_the_proposals_used(self, synthetic_economy):
        """The published round count is reached at the price of that round, before adjustment."""
        procedure = HahnelSlides2020(record_trajectory=True)
        result = run(procedure, synthetic_economy, seed=0)
        one_round_less = HahnelSlides2020(max_rounds=result.summary.rounds - 1)
        earlier = run(one_round_less, synthetic_economy, seed=0)
        assert earlier.summary.converged is False
        assert not np.allclose(
            earlier.plan.valuation[INDICATIVE_PRICE], result.plan.valuation[INDICATIVE_PRICE]
        )

    def test_trajectory_is_off_by_default(self, synthetic_economy):
        result = run(HahnelSlides2020(), synthetic_economy, seed=0)
        assert result.summary.trajectory is None

    def test_trajectory_has_one_plan_per_round(self, synthetic_economy):
        result = run(HahnelSlides2020(record_trajectory=True), synthetic_economy, seed=0)
        assert result.summary.trajectory is not None
        assert len(result.summary.trajectory) == result.summary.rounds
        for plan in result.summary.trajectory:
            plan.validate(synthetic_economy)

    def test_the_first_trajectory_entry_is_priced_at_the_initial_price(self, synthetic_economy):
        procedure = HahnelSlides2020(record_trajectory=True, initial_price=640.0)
        result = run(procedure, synthetic_economy, seed=0)
        np.testing.assert_array_equal(
            result.summary.trajectory[0].valuation[INDICATIVE_PRICE],
            np.full(synthetic_economy.n_commodities, 640.0),
        )

    def test_a_round_cap_stops_the_loop(self, synthetic_economy):
        result = run(HahnelSlides2020(max_rounds=3), synthetic_economy, seed=0)
        assert result.summary.rounds == 3
        assert result.summary.converged is False

    def test_a_tighter_threshold_needs_more_rounds(self, synthetic_economy):
        loose = run(HahnelSlides2020(threshold_pct=5.0), synthetic_economy, seed=0)
        tight = run(HahnelSlides2020(threshold_pct=3.0), synthetic_economy, seed=0)
        assert tight.summary.rounds > loose.summary.rounds

    def test_the_seed_does_not_change_the_result(self, synthetic_economy):
        first = run(HahnelSlides2020(), synthetic_economy, seed=0).plan
        second = run(HahnelSlides2020(), synthetic_economy, seed=2**63).plan
        np.testing.assert_array_equal(first.output, second.output)

    def test_determinism_report(self, synthetic_economy):
        report = check_determinism(HahnelSlides2020(), synthetic_economy, 0, n=3)
        assert report.identical is True
        assert report.differing_fields == []


@pytest.mark.skipif(not dep1ex_available(1), reason="dep1ex01 archive not available")
class TestDep1ex01:
    def test_round_count_matches_the_reference(self, dep1ex01_parsed, dep1ex01_economy):
        wc, cc, layout = dep1ex01_parsed
        expected_rounds, _, _ = reference_run(wc, cc, layout)
        result = run(HahnelSlides2020(), dep1ex01_economy, seed=0)
        assert result.summary.converged is True
        assert result.summary.rounds == expected_rounds

    def test_final_prices_match_the_reference(self, dep1ex01_parsed, dep1ex01_economy):
        wc, cc, layout = dep1ex01_parsed
        _, expected_prices, _ = reference_run(wc, cc, layout)
        result = run(HahnelSlides2020(), dep1ex01_economy, seed=0)
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
            HahnelSlides2020(max_rounds=1, record_trajectory=True), dep1ex01_economy, seed=0
        ).plan
        np.testing.assert_allclose(first.output, expected_output, rtol=1e-12, atol=0)
        np.testing.assert_allclose(first.input_use, expected_input_use, rtol=1e-12, atol=0)

    def test_not_slower_than_the_reference(self, dep1ex01_parsed, dep1ex01_economy):
        wc, cc, layout = dep1ex01_parsed
        started = time.perf_counter()
        reference_run(wc, cc, layout)
        reference_seconds = time.perf_counter() - started
        result = run(HahnelSlides2020(), dep1ex01_economy, seed=0)
        assert result.summary.wall_seconds <= TIMING_ALLOWANCE * reference_seconds, (
            f"prefab {result.summary.wall_seconds:.2f}s "
            f"vs reference {reference_seconds:.2f}s"
        )

    def test_determinism_report(self, dep1ex01_economy):
        report = check_determinism(HahnelSlides2020(), dep1ex01_economy, 0, n=2)
        assert report.identical is True
        assert report.differing_fields == []


@pytest.mark.slow
@pytest.mark.skipif(
    not all(dep1ex_available(i) for i in range(1, DEP1EX_COUNT + 1)),
    reason="the full dep1ex set is not available",
)
class TestPublishedExperiments:
    def test_all_five_experiments(self):
        cold5_ours, cold5_reference, cold3_ours = [], [], []
        for index in range(1, DEP1EX_COUNT + 1):
            wc, cc, layout = parse_dep1ex(dep1ex_path(index))
            economy = economy_from_repro(wc, cc, layout)
            reference5, _, _ = reference_run(wc, cc, layout, threshold=5.0)
            cold5_reference.append(reference5)
            cold5_ours.append(run(HahnelSlides2020(), economy, seed=0).summary.rounds)
            cold3_ours.append(
                run(HahnelSlides2020(threshold_pct=3.0), economy, seed=0).summary.rounds
            )
            del wc, cc, economy
            gc.collect()

        assert cold5_ours == cold5_reference
        assert sorted(cold5_ours) == COLD_5_PERCENT_ROUNDS
        assert abs(statistics.fmean(cold3_ours) - COLD_3_PERCENT_MEAN) < 0.05
