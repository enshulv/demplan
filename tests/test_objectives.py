"""Objectives: the weights a reference solution maximises and how it hands out the result.

An objective is where a theoretical commitment enters the reference solution, so the tests
here check the commitment as much as the arithmetic: that an equal split really is equal, that
the split conserves the aggregate it was given, and that a weight on a commodity nobody can
consume is refused rather than silently dropped.

The expected numbers are written out by hand from the definition of an equal split. Nothing
here calls the linear program.
"""

from __future__ import annotations

import numpy as np
import pytest

from cyberstride import CommodityKind, Economy, Plan
from cyberstride.objectives import MaximizeWeightedConsumption, MinimizeLabor, Objective

TOLERANCE = 1e-12

# Commodity layout shared by every economy in this file.
PRIVATE_A, PRIVATE_B, PUBLIC_A, INTERMEDIATE, NATURAL, LABOR = range(6)
N_COMMODITIES = 6
N_CONSUMERS = 4


def build_economy(n_consumers: int = N_CONSUMERS) -> Economy:
    """Six commodities, one producing unit, ``n_consumers`` consumer units.

    The unit exists only so the economy is well formed; no test here produces anything.
    """
    kind = np.array(
        [
            CommodityKind.PRIVATE_GOOD,
            CommodityKind.PRIVATE_GOOD,
            CommodityKind.PUBLIC_GOOD,
            CommodityKind.INTERMEDIATE,
            CommodityKind.NATURAL_RESOURCE,
            CommodityKind.LABOR,
        ],
        dtype=np.int8,
    )
    return Economy(
        period=0,
        commodity_id=np.arange(N_COMMODITIES, dtype=np.int64),
        commodity_kind=kind,
        endowment=np.array([0.0, 0.0, 0.0, 0.0, 10.0, 10.0]),
        unit_id=np.arange(1, dtype=np.int64),
        unit_group=np.zeros(1, dtype=np.int64),
        output_commodity=np.array([PRIVATE_A], dtype=np.int64),
        technology_kind=np.zeros(1, dtype=np.int8),
        technology_scale=np.ones(1, dtype=np.float64),
        input_offsets=np.array([0, 1], dtype=np.int64),
        input_commodity=np.array([LABOR], dtype=np.int64),
        input_coefficient=np.array([1.0]),
        consumer_id=np.arange(n_consumers, dtype=np.int64),
        consumer_group=np.zeros(n_consumers, dtype=np.int64),
    )


def aggregate_of(**quantities: float) -> np.ndarray:
    """Final-consumption vector with the named commodities set and the rest zero."""
    values = np.zeros(N_COMMODITIES, dtype=np.float64)
    for name, quantity in quantities.items():
        values[globals()[name.upper()]] = quantity
    return values


class TestProtocolConformance:
    def test_both_built_in_objectives_satisfy_the_protocol(self):
        weights = np.zeros(N_COMMODITIES)
        weights[PRIVATE_A] = 1.0
        assert isinstance(MaximizeWeightedConsumption(weights), Objective)
        assert isinstance(MinimizeLabor(np.zeros(N_COMMODITIES)), Objective)

    def test_names_are_the_documented_ones(self):
        assert MaximizeWeightedConsumption(np.zeros(N_COMMODITIES)).name == (
            "maximize_weighted_consumption"
        )
        assert MinimizeLabor(np.zeros(N_COMMODITIES)).name == "minimize_labor"


class TestMaximizeWeightedConsumptionWeights:
    def test_an_array_comes_back_unchanged(self):
        economy = build_economy()
        given = np.zeros(N_COMMODITIES)
        given[PRIVATE_A] = 2.5
        given[PUBLIC_A] = 0.5
        np.testing.assert_allclose(
            MaximizeWeightedConsumption(given).weights(economy), given, atol=TOLERANCE
        )

    def test_a_mapping_is_scattered_over_the_commodity_range(self):
        economy = build_economy()
        objective = MaximizeWeightedConsumption({PRIVATE_B: 3.0, PUBLIC_A: 1.0})
        expected = np.zeros(N_COMMODITIES)
        expected[PRIVATE_B] = 3.0
        expected[PUBLIC_A] = 1.0
        np.testing.assert_allclose(objective.weights(economy), expected, atol=TOLERANCE)

    def test_the_result_is_a_float64_vector_over_all_commodities(self):
        economy = build_economy()
        weights = MaximizeWeightedConsumption({PRIVATE_A: 1.0}).weights(economy)
        assert weights.shape == (N_COMMODITIES,)
        assert weights.dtype == np.float64

    def test_a_weight_on_an_intermediate_good_is_refused(self):
        economy = build_economy()
        given = np.zeros(N_COMMODITIES)
        given[INTERMEDIATE] = 1.0
        with pytest.raises(ValueError, match="intermediate|consum"):
            MaximizeWeightedConsumption(given).weights(economy)

    def test_a_weight_on_labor_is_refused(self):
        economy = build_economy()
        given = np.zeros(N_COMMODITIES)
        given[LABOR] = 1.0
        with pytest.raises(ValueError):
            MaximizeWeightedConsumption(given).weights(economy)

    def test_a_weight_vector_of_the_wrong_length_is_refused(self):
        economy = build_economy()
        with pytest.raises(ValueError, match="length|shape|commodit"):
            MaximizeWeightedConsumption(np.ones(N_COMMODITIES + 1)).weights(economy)

    def test_a_mapping_key_outside_the_commodity_range_is_refused(self):
        economy = build_economy()
        with pytest.raises(ValueError):
            MaximizeWeightedConsumption({N_COMMODITIES: 1.0}).weights(economy).weights(economy)

    def test_a_non_finite_weight_is_refused(self):
        with pytest.raises(ValueError):
            MaximizeWeightedConsumption(np.array([np.nan, 0.0, 0.0, 0.0, 0.0, 0.0]))

    def test_an_unknown_split_is_refused(self):
        with pytest.raises(ValueError, match="split"):
            MaximizeWeightedConsumption(np.zeros(N_COMMODITIES), split="proportional")


class TestMaximizeWeightedConsumptionAllocate:
    def objective(self):
        return MaximizeWeightedConsumption({PRIVATE_A: 1.0, PRIVATE_B: 2.0, PUBLIC_A: 3.0})

    def test_private_goods_are_split_equally(self):
        economy = build_economy()
        aggregate = aggregate_of(private_a=8.0, private_b=12.0, public_a=5.0)
        consumption, columns, _ = self.objective().allocate(economy, aggregate)
        np.testing.assert_array_equal(columns, [PRIVATE_A, PRIVATE_B])
        np.testing.assert_allclose(
            consumption, np.tile([[2.0, 3.0]], (N_CONSUMERS, 1)), atol=TOLERANCE
        )

    def test_public_goods_go_to_provision_and_nothing_else_does(self):
        economy = build_economy()
        aggregate = aggregate_of(private_a=8.0, public_a=5.0)
        _, _, provision = self.objective().allocate(economy, aggregate)
        expected = np.zeros(N_COMMODITIES)
        expected[PUBLIC_A] = 5.0
        np.testing.assert_allclose(provision, expected, atol=TOLERANCE)

    def test_the_split_conserves_the_aggregate(self):
        economy = build_economy()
        aggregate = aggregate_of(private_a=7.0, private_b=13.0, public_a=5.0)
        consumption, columns, provision = self.objective().allocate(economy, aggregate)
        handed_out = np.zeros(N_COMMODITIES)
        np.add.at(handed_out, columns, consumption.sum(axis=0))
        np.testing.assert_allclose(handed_out + provision, aggregate, atol=1e-9)

    def test_every_consumer_unit_gets_the_same_row(self):
        economy = build_economy()
        consumption, _, _ = self.objective().allocate(
            economy, aggregate_of(private_a=1.0, private_b=3.0)
        )
        assert consumption.shape == (N_CONSUMERS, 2)
        for row in range(1, N_CONSUMERS):
            np.testing.assert_allclose(consumption[row], consumption[0], atol=TOLERANCE)

    def test_the_columns_are_every_private_good_in_ascending_order(self):
        economy = build_economy()
        _, columns, _ = self.objective().allocate(economy, np.zeros(N_COMMODITIES))
        np.testing.assert_array_equal(columns, [PRIVATE_A, PRIVATE_B])
        assert columns.dtype == np.int64

    def test_a_single_consumer_unit_gets_the_whole_aggregate(self):
        economy = build_economy(n_consumers=1)
        consumption, _, _ = self.objective().allocate(economy, aggregate_of(private_a=8.0))
        np.testing.assert_allclose(consumption, [[8.0, 0.0]], atol=TOLERANCE)

    def test_the_result_fits_a_plan_of_the_same_economy(self):
        economy = build_economy()
        consumption, columns, provision = self.objective().allocate(
            economy, aggregate_of(private_a=8.0, public_a=2.0)
        )
        plan = Plan(
            output=np.zeros(economy.n_units),
            input_use=np.zeros(economy.n_inputs),
            consumption=consumption,
            consumption_commodity=columns,
            provision=provision,
        )
        plan.validate(economy)

    def test_splitting_among_zero_consumer_units_is_refused(self):
        economy = build_economy(n_consumers=0)
        with pytest.raises(ValueError, match="consumer"):
            self.objective().allocate(economy, aggregate_of(private_a=8.0))


class TestMinimizeLabor:
    def test_it_exposes_the_attributes_the_reference_solution_reads(self):
        targets = np.zeros(N_COMMODITIES)
        targets[PRIVATE_A] = 4.0
        objective = MinimizeLabor(targets)
        np.testing.assert_allclose(objective.final_demand_lower_bound, targets, atol=TOLERANCE)
        assert objective.minimize_kind == CommodityKind.LABOR

    def test_the_lower_bound_is_a_float64_vector(self):
        objective = MinimizeLabor(np.zeros(N_COMMODITIES))
        assert objective.final_demand_lower_bound.dtype == np.float64
        assert objective.final_demand_lower_bound.ndim == 1

    def test_weights_are_zero_because_the_objective_is_not_a_weighted_sum(self):
        economy = build_economy()
        targets = np.zeros(N_COMMODITIES)
        targets[PRIVATE_A] = 4.0
        weights = MinimizeLabor(targets).weights(economy)
        assert weights.shape == (N_COMMODITIES,)
        np.testing.assert_array_equal(weights, np.zeros(N_COMMODITIES))

    def test_a_target_on_an_intermediate_good_is_refused(self):
        economy = build_economy()
        targets = np.zeros(N_COMMODITIES)
        targets[INTERMEDIATE] = 1.0
        with pytest.raises(ValueError, match="intermediate|consum"):
            MinimizeLabor(targets).weights(economy)

    def test_a_target_vector_of_the_wrong_length_is_refused(self):
        economy = build_economy()
        with pytest.raises(ValueError, match="length|shape|commodit"):
            MinimizeLabor(np.zeros(N_COMMODITIES + 2)).weights(economy)

    def test_it_splits_private_goods_equally_like_the_other_objective(self):
        economy = build_economy()
        targets = np.zeros(N_COMMODITIES)
        targets[PRIVATE_B] = 1.0
        consumption, columns, provision = MinimizeLabor(targets).allocate(
            economy, aggregate_of(private_b=12.0, public_a=3.0)
        )
        np.testing.assert_array_equal(columns, [PRIVATE_A, PRIVATE_B])
        np.testing.assert_allclose(
            consumption, np.tile([[0.0, 3.0]], (N_CONSUMERS, 1)), atol=TOLERANCE
        )
        expected_provision = np.zeros(N_COMMODITIES)
        expected_provision[PUBLIC_A] = 3.0
        np.testing.assert_allclose(provision, expected_provision, atol=TOLERANCE)
