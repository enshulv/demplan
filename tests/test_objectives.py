"""Objectives: the weights a reference solution maximises and how it hands out the result.

An objective is where a theoretical commitment enters the reference solution, so the tests
here check the commitment as much as the arithmetic: that an equal split really is equal, that
the split conserves the aggregate it was given, and that the commodities used in common and
the commodities a labour count totals are the ones the researcher declared.

The expected numbers are written out by hand from the definition of an equal split. Nothing
here calls the linear program.
"""

from __future__ import annotations

import numpy as np
import pytest

from demplan import LEONTIEF, Economy, Plan
from demplan.objectives import MaximizeWeightedConsumption, MinimizeLabor, Objective

TOLERANCE = 1e-12

# Commodity layout shared by every economy in this file. The names say what each commodity is
# in the examples below; the economy itself carries no class of any commodity.
PRIVATE_A, PRIVATE_B, PUBLIC_A, INTERMEDIATE, NATURAL, LABOR = range(6)
N_COMMODITIES = 6
N_CONSUMERS = 4

LABOR_ONLY = np.array([LABOR], dtype=np.int64)
SHARED = np.array([PUBLIC_A], dtype=np.int64)


def build_economy(n_consumers: int = N_CONSUMERS) -> Economy:
    """Six commodities, one producing unit, ``n_consumers`` consumer units.

    The unit exists only so the economy is well formed; no test here produces anything.
    """
    return Economy(
        period=0,
        commodity_id=np.arange(N_COMMODITIES, dtype=np.int64),
        endowment=np.array([0.0, 0.0, 0.0, 0.0, 10.0, 10.0]),
        unit_id=np.arange(1, dtype=np.int64),
        technology_kind=[LEONTIEF],
        technology_scale=np.ones(1, dtype=np.float64),
        input_offsets=np.array([0, 1], dtype=np.int64),
        input_commodity=np.array([LABOR], dtype=np.int64),
        input_coefficient=np.array([1.0]),
        output_offsets=np.array([0, 1], dtype=np.int64),
        output_commodity=np.array([PRIVATE_A], dtype=np.int64),
        output_coefficient=np.ones(1, dtype=np.float64),
        consumer_id=np.arange(n_consumers, dtype=np.int64),
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
        assert isinstance(MinimizeLabor(np.zeros(N_COMMODITIES), LABOR_ONLY), Objective)

    def test_names_are_the_documented_ones(self):
        assert MaximizeWeightedConsumption(np.zeros(N_COMMODITIES)).name == (
            "maximize_weighted_consumption"
        )
        assert MinimizeLabor(np.zeros(N_COMMODITIES), LABOR_ONLY).name == "minimize_labor"


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

    @pytest.mark.parametrize("commodity", [INTERMEDIATE, NATURAL, LABOR])
    def test_a_weight_on_any_commodity_is_the_researchers_statement(self, commodity):
        """No commodity is excluded from carrying weight: which ones do is declared."""
        economy = build_economy()
        given = np.zeros(N_COMMODITIES)
        given[commodity] = 1.0
        np.testing.assert_array_equal(MaximizeWeightedConsumption(given).weights(economy), given)

    def test_a_weight_vector_of_the_wrong_length_is_refused(self):
        economy = build_economy()
        with pytest.raises(ValueError, match="length|shape|commodit"):
            MaximizeWeightedConsumption(np.ones(N_COMMODITIES + 1)).weights(economy)

    def test_a_mapping_key_outside_the_commodity_range_is_refused(self):
        economy = build_economy()
        with pytest.raises(ValueError):
            MaximizeWeightedConsumption({N_COMMODITIES: 1.0}).weights(economy)

    def test_a_non_finite_weight_is_refused(self):
        with pytest.raises(ValueError):
            MaximizeWeightedConsumption(np.array([np.nan, 0.0, 0.0, 0.0, 0.0, 0.0]))

    def test_an_unknown_split_is_refused(self):
        with pytest.raises(ValueError, match="split"):
            MaximizeWeightedConsumption(np.zeros(N_COMMODITIES), split="proportional")


class TestMaximizeWeightedConsumptionAllocate:
    def objective(self, shared=SHARED):
        return MaximizeWeightedConsumption(
            {PRIVATE_A: 1.0, PRIVATE_B: 2.0, PUBLIC_A: 3.0}, shared=shared
        )

    def test_the_commodities_not_shared_are_split_equally(self):
        economy = build_economy()
        aggregate = aggregate_of(private_a=8.0, private_b=12.0, public_a=5.0)
        consumption, columns, _ = self.objective().allocate(economy, aggregate)
        np.testing.assert_array_equal(columns, [PRIVATE_A, PRIVATE_B])
        np.testing.assert_allclose(
            consumption, np.tile([[2.0, 3.0]], (N_CONSUMERS, 1)), atol=TOLERANCE
        )

    def test_shared_commodities_go_to_shared_use_whole_and_nothing_else_does(self):
        economy = build_economy()
        aggregate = aggregate_of(private_a=8.0, public_a=5.0)
        _, _, shared_use = self.objective().allocate(economy, aggregate)
        expected = np.zeros(N_COMMODITIES)
        expected[PUBLIC_A] = 5.0
        np.testing.assert_array_equal(shared_use, expected)

    def test_without_shared_commodities_every_weighted_commodity_is_split(self):
        """``shared=None`` says no commodity is used in common, the public one included."""
        economy = build_economy()
        aggregate = aggregate_of(private_a=8.0, private_b=12.0, public_a=20.0)
        consumption, columns, shared_use = self.objective(shared=None).allocate(
            economy, aggregate
        )
        np.testing.assert_array_equal(columns, [PRIVATE_A, PRIVATE_B, PUBLIC_A])
        np.testing.assert_allclose(
            consumption, np.tile([[2.0, 3.0, 5.0]], (N_CONSUMERS, 1)), atol=TOLERANCE
        )
        np.testing.assert_array_equal(shared_use, np.zeros(N_COMMODITIES))

    def test_the_split_conserves_the_aggregate(self):
        economy = build_economy()
        aggregate = aggregate_of(private_a=7.0, private_b=13.0, public_a=5.0)
        consumption, columns, shared_use = self.objective().allocate(economy, aggregate)
        handed_out = np.zeros(N_COMMODITIES)
        np.add.at(handed_out, columns, consumption.sum(axis=0))
        np.testing.assert_allclose(handed_out + shared_use, aggregate, atol=1e-9)

    def test_every_consumer_unit_gets_the_same_row(self):
        economy = build_economy()
        consumption, _, _ = self.objective().allocate(
            economy, aggregate_of(private_a=1.0, private_b=3.0)
        )
        assert consumption.shape == (N_CONSUMERS, 2)
        for row in range(1, N_CONSUMERS):
            np.testing.assert_allclose(consumption[row], consumption[0], atol=TOLERANCE)

    def test_the_columns_are_the_weighted_commodities_not_shared_in_ascending_order(self):
        economy = build_economy()
        objective = MaximizeWeightedConsumption(
            {LABOR: 1.0, PRIVATE_B: 2.0, INTERMEDIATE: 0.5, PUBLIC_A: 3.0}, shared=SHARED
        )
        _, columns, _ = objective.allocate(economy, np.zeros(N_COMMODITIES))
        np.testing.assert_array_equal(columns, [PRIVATE_B, INTERMEDIATE, LABOR])
        assert columns.dtype == np.int64

    def test_a_commodity_with_zero_weight_is_not_a_column(self):
        """PRIVATE_A carries weight 0, so no consumer unit is handed a column of it."""
        economy = build_economy()
        objective = MaximizeWeightedConsumption({PRIVATE_A: 0.0, PRIVATE_B: 1.0})
        _, columns, _ = objective.allocate(economy, np.zeros(N_COMMODITIES))
        np.testing.assert_array_equal(columns, [PRIVATE_B])

    def test_a_negative_weight_is_still_a_column(self):
        """A penalty is a non-zero weight, so the commodity it sits on is consumed like any."""
        economy = build_economy()
        objective = MaximizeWeightedConsumption({PRIVATE_A: -1.0, PRIVATE_B: 1.0})
        _, columns, _ = objective.allocate(economy, np.zeros(N_COMMODITIES))
        np.testing.assert_array_equal(columns, [PRIVATE_A, PRIVATE_B])

    def test_a_single_consumer_unit_gets_the_whole_aggregate(self):
        economy = build_economy(n_consumers=1)
        consumption, _, _ = self.objective().allocate(economy, aggregate_of(private_a=8.0))
        np.testing.assert_allclose(consumption, [[8.0, 0.0]], atol=TOLERANCE)

    def test_the_result_fits_a_plan_of_the_same_economy(self):
        economy = build_economy()
        consumption, columns, shared_use = self.objective().allocate(
            economy, aggregate_of(private_a=8.0, public_a=2.0)
        )
        plan = Plan(
            output=np.zeros(economy.n_outputs),
            input_use=np.zeros(economy.n_inputs),
            consumption=consumption,
            consumption_commodity=columns,
            shared_use=shared_use,
        )
        plan.validate(economy)

    def test_splitting_among_zero_consumer_units_is_refused(self):
        economy = build_economy(n_consumers=0)
        with pytest.raises(ValueError, match="consumer"):
            self.objective().allocate(economy, aggregate_of(private_a=8.0))

    def test_zero_consumer_units_can_still_share_what_is_used_in_common(self):
        """Nothing is split when every weighted commodity is shared."""
        economy = build_economy(n_consumers=0)
        objective = MaximizeWeightedConsumption({PUBLIC_A: 1.0}, shared=SHARED)
        consumption, columns, shared_use = objective.allocate(
            economy, aggregate_of(public_a=4.0)
        )
        assert consumption.shape == (0, 0)
        assert columns.shape == (0,)
        assert shared_use[PUBLIC_A] == 4.0


class TestTheSharedDeclaration:
    """``shared`` names commodity indices; a malformed list is refused, never read loosely."""

    def test_the_default_is_none(self):
        objective = MaximizeWeightedConsumption({PRIVATE_A: 1.0})
        economy = build_economy()
        _, columns, shared_use = objective.allocate(economy, aggregate_of(private_a=4.0))
        np.testing.assert_array_equal(columns, [PRIVATE_A])
        np.testing.assert_array_equal(shared_use, np.zeros(N_COMMODITIES))

    @pytest.mark.parametrize("bad", [-1, N_COMMODITIES])
    def test_an_index_outside_the_commodity_range_is_refused(self, bad):
        objective = MaximizeWeightedConsumption(
            {PRIVATE_A: 1.0}, shared=np.array([bad], dtype=np.int64)
        )
        with pytest.raises(ValueError, match="shared"):
            objective.weights(build_economy())

    @pytest.mark.parametrize("bad", [-1, N_COMMODITIES])
    def test_allocate_refuses_it_as_well(self, bad):
        objective = MaximizeWeightedConsumption(
            {PRIVATE_A: 1.0}, shared=np.array([bad], dtype=np.int64)
        )
        with pytest.raises(ValueError, match="shared"):
            objective.allocate(build_economy(), np.zeros(N_COMMODITIES))

    def test_a_duplicate_index_is_refused(self):
        with pytest.raises(ValueError, match="shared"):
            MaximizeWeightedConsumption(
                {PRIVATE_A: 1.0}, shared=np.array([PUBLIC_A, PUBLIC_A], dtype=np.int64)
            )

    def test_a_float_array_is_refused(self):
        with pytest.raises(ValueError, match="shared"):
            MaximizeWeightedConsumption({PRIVATE_A: 1.0}, shared=np.array([2.0]))

    def test_a_two_dimensional_array_is_refused(self):
        with pytest.raises(ValueError, match="shared"):
            MaximizeWeightedConsumption(
                {PRIVATE_A: 1.0}, shared=np.array([[PUBLIC_A]], dtype=np.int64)
            )

    def test_minimize_labor_takes_it_too(self):
        targets = aggregate_of(private_b=2.0, public_a=3.0)
        objective = MinimizeLabor(targets, LABOR_ONLY, shared=SHARED)
        consumption, columns, shared_use = objective.allocate(
            build_economy(), aggregate_of(private_b=12.0, public_a=3.0)
        )
        np.testing.assert_array_equal(columns, [PRIVATE_B])
        np.testing.assert_allclose(consumption, np.full((N_CONSUMERS, 1), 3.0), atol=TOLERANCE)
        expected = np.zeros(N_COMMODITIES)
        expected[PUBLIC_A] = 3.0
        np.testing.assert_array_equal(shared_use, expected)


class TestMinimizeLabor:
    def test_it_exposes_the_attributes_the_reference_solution_reads(self):
        targets = np.zeros(N_COMMODITIES)
        targets[PRIVATE_A] = 4.0
        objective = MinimizeLabor(targets, LABOR_ONLY)
        np.testing.assert_allclose(objective.final_demand_lower_bound, targets, atol=TOLERANCE)
        np.testing.assert_array_equal(objective.counted_commodities, [LABOR])
        assert objective.counted_commodities.dtype == np.int64

    def test_the_old_kind_attribute_is_gone(self):
        assert not hasattr(MinimizeLabor(np.zeros(N_COMMODITIES), LABOR_ONLY), "minimize_kind")

    def test_counted_is_required(self):
        with pytest.raises(TypeError, match="counted"):
            MinimizeLabor(np.zeros(N_COMMODITIES))

    def test_several_counted_commodities_are_kept_as_given(self):
        counted = np.array([LABOR, NATURAL], dtype=np.int64)
        objective = MinimizeLabor(np.zeros(N_COMMODITIES), counted)
        np.testing.assert_array_equal(objective.counted_commodities, [LABOR, NATURAL])

    def test_a_duplicate_counted_commodity_is_refused(self):
        with pytest.raises(ValueError, match="counted"):
            MinimizeLabor(np.zeros(N_COMMODITIES), np.array([LABOR, LABOR], dtype=np.int64))

    def test_an_empty_counted_array_is_refused(self):
        """Counting no commodity makes the cost zero for every plan."""
        with pytest.raises(ValueError, match="counted"):
            MinimizeLabor(np.zeros(N_COMMODITIES), np.zeros(0, dtype=np.int64))

    def test_a_single_counted_commodity_is_enough(self):
        objective = MinimizeLabor(np.zeros(N_COMMODITIES), np.array([NATURAL], dtype=np.int64))
        np.testing.assert_array_equal(objective.counted_commodities, [NATURAL])

    def test_a_float_counted_array_is_refused(self):
        with pytest.raises(ValueError, match="counted"):
            MinimizeLabor(np.zeros(N_COMMODITIES), np.array([5.0]))

    def test_a_two_dimensional_counted_array_is_refused(self):
        with pytest.raises(ValueError, match="counted"):
            MinimizeLabor(np.zeros(N_COMMODITIES), np.array([[LABOR]], dtype=np.int64))

    @pytest.mark.parametrize("bad", [-1, N_COMMODITIES])
    def test_a_counted_commodity_outside_the_range_is_refused(self, bad):
        objective = MinimizeLabor(np.zeros(N_COMMODITIES), np.array([bad], dtype=np.int64))
        with pytest.raises(ValueError, match="counted"):
            objective.weights(build_economy())

    def test_the_lower_bound_is_a_float64_vector(self):
        objective = MinimizeLabor(np.zeros(N_COMMODITIES), LABOR_ONLY)
        assert objective.final_demand_lower_bound.dtype == np.float64
        assert objective.final_demand_lower_bound.ndim == 1

    def test_weights_are_zero_because_the_objective_is_not_a_weighted_sum(self):
        economy = build_economy()
        targets = np.zeros(N_COMMODITIES)
        targets[PRIVATE_A] = 4.0
        weights = MinimizeLabor(targets, LABOR_ONLY).weights(economy)
        assert weights.shape == (N_COMMODITIES,)
        np.testing.assert_array_equal(weights, np.zeros(N_COMMODITIES))

    def test_a_target_on_an_intermediate_good_is_the_researchers_statement(self):
        economy = build_economy()
        targets = np.zeros(N_COMMODITIES)
        targets[INTERMEDIATE] = 1.0
        np.testing.assert_array_equal(
            MinimizeLabor(targets, LABOR_ONLY).weights(economy), np.zeros(N_COMMODITIES)
        )

    def test_a_target_vector_of_the_wrong_length_is_refused(self):
        economy = build_economy()
        with pytest.raises(ValueError, match="length|shape|commodit"):
            MinimizeLabor(np.zeros(N_COMMODITIES + 2), LABOR_ONLY).weights(economy)

    def test_a_negative_target_is_refused_and_the_message_names_the_commodity(self):
        targets = np.zeros(N_COMMODITIES)
        targets[PRIVATE_A] = 6.0
        targets[PRIVATE_B] = -3.0
        with pytest.raises(ValueError, match=f"commodity {PRIVATE_B}"):
            MinimizeLabor(targets, LABOR_ONLY)

    def test_a_target_of_zero_or_more_is_accepted(self):
        targets = np.zeros(N_COMMODITIES)
        targets[PRIVATE_A] = 6.0
        objective = MinimizeLabor(targets, LABOR_ONLY)
        np.testing.assert_allclose(objective.final_demand_lower_bound, targets, atol=TOLERANCE)

    def test_it_splits_the_targeted_commodities_equally_like_the_other_objective(self):
        economy = build_economy()
        targets = np.zeros(N_COMMODITIES)
        targets[PRIVATE_B] = 1.0
        targets[PUBLIC_A] = 1.0
        consumption, columns, shared_use = MinimizeLabor(targets, LABOR_ONLY).allocate(
            economy, aggregate_of(private_b=12.0, public_a=3.0)
        )
        np.testing.assert_array_equal(columns, [PRIVATE_B, PUBLIC_A])
        np.testing.assert_allclose(
            consumption, np.tile([[3.0, 0.75]], (N_CONSUMERS, 1)), atol=TOLERANCE
        )
        np.testing.assert_array_equal(shared_use, np.zeros(N_COMMODITIES))


class TestDeclarationsAreCopied:
    """An objective keeps its own read-only copy of every array or mapping it is given.

    A caller who edits a declaration after building the objective has made a new statement,
    and the objective already carries the old one; reading the caller's buffer would let the
    edit change a result the run records as the old statement's.
    """

    def test_editing_minimize_labor_targets_afterwards_changes_nothing(self):
        economy = build_economy()
        targets = np.zeros(N_COMMODITIES)
        targets[PRIVATE_A] = 4.0
        objective = MinimizeLabor(targets, LABOR_ONLY)
        targets[PRIVATE_A] = 0.0
        targets[PRIVATE_B] = 9.0
        assert objective.final_demand_lower_bound[PRIVATE_A] == 4.0
        assert objective.final_demand_lower_bound[PRIVATE_B] == 0.0
        _, columns, _ = objective.allocate(economy, aggregate_of(private_a=8.0))
        np.testing.assert_array_equal(columns, [PRIVATE_A])

    def test_editing_minimize_labor_counted_afterwards_changes_nothing(self):
        counted = np.array([LABOR], dtype=np.int64)
        objective = MinimizeLabor(np.zeros(N_COMMODITIES), counted)
        counted[0] = NATURAL
        np.testing.assert_array_equal(objective.counted_commodities, [LABOR])

    @pytest.mark.parametrize("build", ["minimize_labor", "maximize_weighted_consumption"])
    def test_editing_shared_afterwards_changes_nothing(self, build):
        economy = build_economy()
        shared = np.array([PUBLIC_A], dtype=np.int64)
        declared = np.zeros(N_COMMODITIES)
        declared[[PRIVATE_A, PUBLIC_A]] = 1.0
        if build == "minimize_labor":
            objective = MinimizeLabor(declared, LABOR_ONLY, shared=shared)
        else:
            objective = MaximizeWeightedConsumption(declared, shared=shared)
        shared[0] = PRIVATE_A
        np.testing.assert_array_equal(objective.shared_commodities, [PUBLIC_A])
        _, columns, shared_use = objective.allocate(
            economy, aggregate_of(private_a=4.0, public_a=2.0)
        )
        np.testing.assert_array_equal(columns, [PRIVATE_A])
        np.testing.assert_array_equal(shared_use, aggregate_of(public_a=2.0))

    def test_editing_a_weight_vector_afterwards_changes_nothing(self):
        economy = build_economy()
        weights = np.zeros(N_COMMODITIES)
        weights[PRIVATE_A] = 2.5
        objective = MaximizeWeightedConsumption(weights)
        weights[PRIVATE_A] = 0.0
        weights[PRIVATE_B] = 7.0
        expected = np.zeros(N_COMMODITIES)
        expected[PRIVATE_A] = 2.5
        np.testing.assert_array_equal(objective.weights(economy), expected)

    def test_editing_a_weight_mapping_afterwards_changes_nothing(self):
        economy = build_economy()
        weights = {PRIVATE_A: 2.5}
        objective = MaximizeWeightedConsumption(weights)
        weights[PRIVATE_A] = 0.0
        weights[PRIVATE_B] = 7.0
        expected = np.zeros(N_COMMODITIES)
        expected[PRIVATE_A] = 2.5
        np.testing.assert_array_equal(objective.weights(economy), expected)

    def test_the_stored_arrays_are_read_only(self):
        minimize = MinimizeLabor(np.zeros(N_COMMODITIES), LABOR_ONLY, shared=SHARED)
        maximize = MaximizeWeightedConsumption(np.ones(N_COMMODITIES), shared=SHARED)
        for stored in (
            minimize.final_demand_lower_bound,
            minimize.counted_commodities,
            minimize.shared_commodities,
            maximize.declared_weights,
            maximize.shared_commodities,
        ):
            with pytest.raises(ValueError):
                stored[0] = 1

    def test_a_stored_weight_mapping_is_read_only(self):
        objective = MaximizeWeightedConsumption({PRIVATE_A: 2.5})
        with pytest.raises(TypeError):
            objective.declared_weights[PRIVATE_B] = 1.0

    def test_the_stored_arrays_share_no_memory_with_the_callers(self):
        targets, counted, shared = np.zeros(N_COMMODITIES), LABOR_ONLY.copy(), SHARED.copy()
        weights = np.ones(N_COMMODITIES)
        minimize = MinimizeLabor(targets, counted, shared=shared)
        maximize = MaximizeWeightedConsumption(weights, shared=shared)
        pairs = (
            (minimize.final_demand_lower_bound, targets),
            (minimize.counted_commodities, counted),
            (minimize.shared_commodities, shared),
            (maximize.declared_weights, weights),
            (maximize.shared_commodities, shared),
        )
        for stored, given in pairs:
            assert not np.shares_memory(stored, given)
