"""Structural contract of :class:`Plan` and its derived accessors.

The expected aggregates are recomputed here with plain Python loops rather than with the
same numpy calls the library uses, so that a wrong aggregation column in the library shows up
as a failure instead of cancelling out.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from cyberstride import (
    INCOME,
    INDICATIVE_PRICE,
    LABOR_VALUE,
    SHADOW_PRICE,
    CommodityKind,
    Plan,
    SchemaError,
)


@pytest.fixture
def plan(synthetic_economy):
    economy = synthetic_economy
    return Plan(
        output=np.arange(1, economy.n_units + 1, dtype=np.float64),
        input_use=np.arange(1, economy.n_inputs + 1, dtype=np.float64),
        consumption=np.array(
            [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0], [10.0, 11.0, 12.0]]
        ),
        consumption_commodity=np.array([0, 1, 2], dtype=np.int64),
        provision=np.array([0.0] * 3 + [11.0, 12.0, 13.0] + [0.0] * 9),
        valuation={INDICATIVE_PRICE: np.full(economy.n_commodities, 700.0)},
    )


def expected_scatter(indices, weights, size) -> np.ndarray:
    totals = [0.0] * size
    for index, weight in zip(indices, weights):
        totals[int(index)] += float(weight)
    return np.array(totals)


class TestValuationKeys:
    def test_predefined_keys(self):
        assert INDICATIVE_PRICE == "indicative_price"
        assert LABOR_VALUE == "labor_value"
        assert SHADOW_PRICE == "shadow_price"
        assert INCOME == "income"


class TestImmutability:
    def test_fields_cannot_be_rebound(self, plan):
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.output = np.zeros(1)

    @pytest.mark.parametrize(
        "field", ["output", "input_use", "consumption", "consumption_commodity", "provision"]
    )
    def test_arrays_are_read_only(self, plan, field):
        array = getattr(plan, field)
        assert array.flags.writeable is False

    def test_construction_leaves_the_callers_arrays_writeable(self, synthetic_economy):
        """Freezing is the plan's own promise, not a side effect on the caller's buffer."""
        output = np.ones(synthetic_economy.n_units)
        price = np.full(synthetic_economy.n_commodities, 700.0)
        Plan(
            output=output,
            input_use=np.ones(synthetic_economy.n_inputs),
            consumption=np.ones((synthetic_economy.n_consumers, 0)),
            consumption_commodity=np.zeros(0, dtype=np.int64),
            provision=np.zeros(synthetic_economy.n_commodities),
            valuation={INDICATIVE_PRICE: price},
        )
        assert output.flags.writeable is True
        assert price.flags.writeable is True

    def test_valuation_is_a_read_only_mapping(self, plan):
        with pytest.raises(TypeError):
            plan.valuation["injected"] = np.zeros(1)
        assert plan.valuation[INDICATIVE_PRICE].flags.writeable is False

    def test_valuation_defaults_to_empty(self, synthetic_economy):
        bare = Plan(
            output=np.zeros(synthetic_economy.n_units),
            input_use=np.zeros(synthetic_economy.n_inputs),
            consumption=np.zeros((synthetic_economy.n_consumers, 0)),
            consumption_commodity=np.zeros(0, dtype=np.int64),
            provision=np.zeros(synthetic_economy.n_commodities),
        )
        assert dict(bare.valuation) == {}


class TestValidate:
    def test_a_well_formed_plan_passes(self, plan, synthetic_economy):
        plan.validate(synthetic_economy)

    def test_output_length(self, plan, synthetic_economy):
        broken = dataclasses.replace(plan, output=plan.output[:-1])
        with pytest.raises(SchemaError, match="output"):
            broken.validate(synthetic_economy)

    def test_input_use_length(self, plan, synthetic_economy):
        broken = dataclasses.replace(plan, input_use=plan.input_use[:-1])
        with pytest.raises(SchemaError, match="input_use"):
            broken.validate(synthetic_economy)

    def test_provision_length(self, plan, synthetic_economy):
        broken = dataclasses.replace(plan, provision=plan.provision[:-1])
        with pytest.raises(SchemaError, match="provision"):
            broken.validate(synthetic_economy)

    def test_consumption_row_count(self, plan, synthetic_economy):
        broken = dataclasses.replace(plan, consumption=plan.consumption[:-1])
        with pytest.raises(SchemaError, match="consumption"):
            broken.validate(synthetic_economy)

    def test_consumption_column_count_must_match_the_mapping(self, plan, synthetic_economy):
        broken = dataclasses.replace(plan, consumption=plan.consumption[:, :-1])
        with pytest.raises(SchemaError, match="consumption"):
            broken.validate(synthetic_economy)

    @pytest.mark.parametrize("bad", [-1, 15])
    def test_consumption_commodity_range(self, plan, synthetic_economy, bad):
        columns = plan.consumption_commodity.copy()
        columns[1] = bad
        broken = dataclasses.replace(plan, consumption_commodity=columns)
        with pytest.raises(SchemaError, match="consumption_commodity"):
            broken.validate(synthetic_economy)

    @pytest.mark.parametrize("field", ["output", "input_use", "consumption", "provision"])
    @pytest.mark.parametrize("bad", [np.nan, np.inf])
    def test_physical_layer_must_be_finite(self, plan, synthetic_economy, field, bad):
        array = getattr(plan, field).copy()
        array.reshape(-1)[0] = bad
        broken = dataclasses.replace(plan, **{field: array})
        with pytest.raises(SchemaError, match=field):
            broken.validate(synthetic_economy)

    def test_consumption_must_be_two_dimensional(self, plan, synthetic_economy):
        broken = dataclasses.replace(plan, consumption=plan.consumption.reshape(-1))
        with pytest.raises(SchemaError, match="consumption"):
            broken.validate(synthetic_economy)


class TestExtraBag:
    """``extra`` carries physical quantities the fixed fields have no column for."""

    def test_it_defaults_to_empty(self, plan):
        assert dict(plan.extra) == {}

    def test_it_is_a_read_only_mapping(self, plan, synthetic_economy):
        carried = dataclasses.replace(
            plan, extra={"effort": np.ones(synthetic_economy.n_units)}
        )
        with pytest.raises(TypeError):
            carried.extra["injected"] = np.zeros(1)
        assert carried.extra["effort"].flags.writeable is False

    @pytest.mark.parametrize("rows", ["n_units", "n_consumers", "n_commodities"])
    def test_each_of_the_three_row_counts_is_accepted(self, plan, synthetic_economy, rows):
        length = getattr(synthetic_economy, rows)
        carried = dataclasses.replace(plan, extra={"whatever": np.ones(length)})
        carried.validate(synthetic_economy)

    def test_a_leading_dimension_matching_none_of_the_three_is_rejected(
        self, plan, synthetic_economy
    ):
        odd = 1 + max(
            synthetic_economy.n_units,
            synthetic_economy.n_consumers,
            synthetic_economy.n_commodities,
        )
        carried = dataclasses.replace(plan, extra={"effort": np.ones(odd)})
        with pytest.raises(SchemaError, match=r"Plan\.extra\['effort'\]"):
            carried.validate(synthetic_economy)

    @pytest.mark.parametrize("bad", [np.nan, np.inf])
    def test_a_non_finite_entry_is_rejected(self, plan, synthetic_economy, bad):
        values = np.ones(synthetic_economy.n_units)
        values[0] = bad
        carried = dataclasses.replace(plan, extra={"effort": values})
        with pytest.raises(SchemaError, match=r"Plan\.extra\['effort'\]"):
            carried.validate(synthetic_economy)

    def test_a_non_array_value_is_rejected(self, plan, synthetic_economy):
        carried = dataclasses.replace(plan, extra={"effort": [1.0, 2.0]})
        with pytest.raises(SchemaError, match=r"Plan\.extra\['effort'\]"):
            carried.validate(synthetic_economy)


class TestAccessorsRejectMisshapenPlans:
    """A plan built for a different economy has to be named, not silently aggregated.

    ``total_consumption`` in particular scatters into a commodity-length vector whatever the
    consumption block's shape, so without a check it answers with a wrong vector rather than
    an error.
    """

    ACCESSORS = ("total_output", "total_input_use", "total_consumption", "endowment_use")

    @pytest.mark.parametrize("accessor", ACCESSORS)
    def test_a_short_output_column_is_named(self, plan, synthetic_economy, accessor):
        broken = dataclasses.replace(plan, output=np.zeros(5))
        with pytest.raises(SchemaError) as excinfo:
            getattr(broken, accessor)(synthetic_economy)
        message = str(excinfo.value)
        assert "Plan.output" in message
        assert "5" in message
        assert str(synthetic_economy.n_units) in message

    @pytest.mark.parametrize("accessor", ACCESSORS)
    def test_a_short_input_use_column_is_named(self, plan, synthetic_economy, accessor):
        broken = dataclasses.replace(plan, input_use=np.zeros(2))
        with pytest.raises(SchemaError, match=r"Plan\.input_use"):
            getattr(broken, accessor)(synthetic_economy)

    @pytest.mark.parametrize("accessor", ACCESSORS)
    def test_a_short_provision_column_is_named(self, plan, synthetic_economy, accessor):
        broken = dataclasses.replace(plan, provision=np.zeros(2))
        with pytest.raises(SchemaError, match=r"Plan\.provision"):
            getattr(broken, accessor)(synthetic_economy)

    @pytest.mark.parametrize("accessor", ACCESSORS)
    def test_a_consumption_block_with_the_wrong_row_count_is_named(
        self, plan, synthetic_economy, accessor
    ):
        broken = dataclasses.replace(plan, consumption=plan.consumption[:-1])
        with pytest.raises(SchemaError, match=r"Plan\.consumption"):
            getattr(broken, accessor)(synthetic_economy)

    @pytest.mark.parametrize("accessor", ACCESSORS)
    def test_a_consumption_commodity_outside_the_commodity_range_is_named(
        self, plan, synthetic_economy, accessor
    ):
        columns = plan.consumption_commodity.copy()
        columns[0] = synthetic_economy.n_commodities
        broken = dataclasses.replace(plan, consumption_commodity=columns)
        with pytest.raises(SchemaError, match=r"Plan\.consumption_commodity"):
            getattr(broken, accessor)(synthetic_economy)

    def test_total_consumption_does_not_answer_for_a_plan_of_another_size(
        self, plan, synthetic_economy
    ):
        """A five-unit plan is refused against a nine-unit economy, not aggregated into one."""
        broken = dataclasses.replace(
            plan,
            output=np.zeros(5),
            consumption=np.ones((2, 3)),
        )
        with pytest.raises(SchemaError):
            broken.total_consumption(synthetic_economy)


class TestDerivedAccessors:
    def test_total_output(self, plan, synthetic_economy):
        expected = expected_scatter(
            synthetic_economy.output_commodity, plan.output, synthetic_economy.n_commodities
        )
        np.testing.assert_array_equal(plan.total_output(synthetic_economy), expected)

    def test_total_output_ignores_unit_group(self, plan, synthetic_economy):
        by_group = expected_scatter(
            synthetic_economy.unit_group, plan.output, synthetic_economy.n_commodities
        )
        assert not np.array_equal(plan.total_output(synthetic_economy), by_group)

    def test_total_input_use(self, plan, synthetic_economy):
        expected = expected_scatter(
            synthetic_economy.input_commodity, plan.input_use, synthetic_economy.n_commodities
        )
        np.testing.assert_array_equal(plan.total_input_use(synthetic_economy), expected)

    def test_total_consumption(self, plan, synthetic_economy):
        expected = expected_scatter(
            plan.consumption_commodity,
            plan.consumption.sum(axis=0),
            synthetic_economy.n_commodities,
        )
        np.testing.assert_allclose(plan.total_consumption(synthetic_economy), expected)

    def test_endowment_use_covers_only_natural_resources_and_labor(self, plan, synthetic_economy):
        used = plan.endowment_use(synthetic_economy)
        total = plan.total_input_use(synthetic_economy)
        kinds = np.asarray(synthetic_economy.commodity_kind)
        endowed = (kinds == CommodityKind.NATURAL_RESOURCE) | (kinds == CommodityKind.LABOR)
        np.testing.assert_array_equal(used[endowed], total[endowed])
        np.testing.assert_array_equal(used[~endowed], np.zeros(int((~endowed).sum())))

    def test_endowment_use_excludes_intermediates(self, plan, synthetic_economy):
        used = plan.endowment_use(synthetic_economy)
        total = plan.total_input_use(synthetic_economy)
        intermediates = np.asarray(synthetic_economy.commodity_kind) == CommodityKind.INTERMEDIATE
        assert total[intermediates].sum() > 0.0
        assert used[intermediates].sum() == 0.0

    def test_accessors_return_commodity_length_vectors(self, plan, synthetic_economy):
        for accessor in (plan.total_output, plan.total_input_use, plan.total_consumption,
                         plan.endowment_use):
            result = accessor(synthetic_economy)
            assert result.shape == (synthetic_economy.n_commodities,)
            assert result.dtype == np.float64
