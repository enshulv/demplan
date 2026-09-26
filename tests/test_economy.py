"""Structural contract of :class:`Economy`."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from demplan import CommodityKind, Economy, SchemaError, TechnologyKind


def replaced(economy: Economy, **changes) -> Economy:
    """``dataclasses.replace``, which re-runs validation through ``__post_init__``."""
    return dataclasses.replace(economy, **changes)


def with_extra(economy: Economy, bag: str, key: str, value: np.ndarray) -> Economy:
    updated = dict(getattr(economy, bag))
    updated[key] = value
    return replaced(economy, **{bag: updated})


class TestEnums:
    def test_commodity_kind_values(self):
        assert [int(k) for k in CommodityKind] == [0, 1, 2, 3, 4]
        assert CommodityKind.PRIVATE_GOOD == 0
        assert CommodityKind.PUBLIC_GOOD == 1
        assert CommodityKind.INTERMEDIATE == 2
        assert CommodityKind.NATURAL_RESOURCE == 3
        assert CommodityKind.LABOR == 4

    def test_technology_kind_values(self):
        assert TechnologyKind.LEONTIEF == 0
        assert TechnologyKind.COBB_DOUGLAS == 1
        assert [int(k) for k in TechnologyKind] == [0, 1]


class TestImmutability:
    def test_fields_cannot_be_rebound(self, synthetic_economy):
        with pytest.raises(dataclasses.FrozenInstanceError):
            synthetic_economy.period = 7

    @pytest.mark.parametrize(
        "field",
        ["commodity_id", "commodity_kind", "endowment", "unit_id", "unit_group",
         "output_commodity", "technology_kind", "technology_scale", "input_offsets",
         "input_commodity", "input_coefficient", "consumer_id", "consumer_group"],
    )
    def test_arrays_are_read_only(self, synthetic_economy, field):
        array = getattr(synthetic_economy, field)
        assert array.flags.writeable is False
        with pytest.raises(ValueError):
            array[0] = array[0]

    @pytest.mark.parametrize("bag", ["commodity_extra", "unit_extra", "consumer_extra"])
    def test_extra_bags_are_read_only_mappings(self, synthetic_economy, bag):
        mapping = getattr(synthetic_economy, bag)
        with pytest.raises(TypeError):
            mapping["injected"] = np.zeros(1)
        for array in mapping.values():
            assert array.flags.writeable is False

    def test_construction_leaves_the_callers_column_writeable(self, synthetic_economy):
        """Freezing is the economy's own promise, not a side effect on the caller's buffer."""
        column = np.array(synthetic_economy.technology_scale, dtype=np.float64)
        replaced(synthetic_economy, technology_scale=column)
        assert column.flags.writeable is True
        column[0] = 99.0

    def test_construction_leaves_the_callers_extra_array_writeable(self, synthetic_economy):
        bag = {key: np.array(value) for key, value in synthetic_economy.unit_extra.items()}
        replaced(synthetic_economy, unit_extra=bag)
        for array in bag.values():
            assert array.flags.writeable is True

    def test_construction_does_not_share_the_caller_dict(self, synthetic_economy):
        source = dict(synthetic_economy.unit_extra)
        rebuilt = replaced(synthetic_economy, unit_extra=source)
        source["effort_c"] = np.zeros(synthetic_economy.n_units)
        assert "effort_c" in rebuilt.unit_extra
        assert rebuilt.unit_extra["effort_c"][0] != 0.0


class TestConvenienceAccessors:
    def test_counts(self, synthetic_economy):
        assert synthetic_economy.n_commodities == 15
        assert synthetic_economy.n_units == 9
        assert synthetic_economy.n_consumers == 4
        assert synthetic_economy.n_inputs == int(synthetic_economy.input_offsets[-1])
        assert synthetic_economy.n_inputs == synthetic_economy.input_commodity.shape[0]

    def test_commodities_of_kind(self, synthetic_economy):
        np.testing.assert_array_equal(
            synthetic_economy.commodities_of_kind(CommodityKind.PRIVATE_GOOD), [0, 1, 2]
        )
        np.testing.assert_array_equal(
            synthetic_economy.commodities_of_kind(CommodityKind.LABOR), [12, 13, 14]
        )
        assert synthetic_economy.commodities_of_kind(CommodityKind.PUBLIC_GOOD).dtype == np.int64

    def test_inputs_of_matches_the_offsets(self, synthetic_economy):
        for unit in range(synthetic_economy.n_units):
            window = synthetic_economy.inputs_of(unit)
            assert isinstance(window, slice)
            assert window.start == int(synthetic_economy.input_offsets[unit])
            assert window.stop == int(synthetic_economy.input_offsets[unit + 1])

    def test_inputs_of_partitions_the_flat_arrays(self, synthetic_economy):
        seen = np.concatenate(
            [synthetic_economy.input_commodity[synthetic_economy.inputs_of(u)]
             for u in range(synthetic_economy.n_units)]
        )
        np.testing.assert_array_equal(seen, synthetic_economy.input_commodity)


class TestFromArrays:
    def test_round_trip(self, synthetic_economy):
        mapping = {f.name: getattr(synthetic_economy, f.name)
                   for f in dataclasses.fields(synthetic_economy)}
        for bag in ("commodity_extra", "unit_extra", "consumer_extra"):
            mapping[bag] = dict(mapping[bag])
        rebuilt = Economy.from_arrays(mapping)
        for name in ("commodity_id", "commodity_kind", "endowment", "input_offsets",
                     "input_commodity", "input_coefficient"):
            np.testing.assert_array_equal(getattr(rebuilt, name), getattr(synthetic_economy, name))
        assert rebuilt.period == synthetic_economy.period
        assert set(rebuilt.unit_extra) == set(synthetic_economy.unit_extra)

    def test_extra_bags_default_to_empty(self, synthetic_economy):
        mapping = {f.name: getattr(synthetic_economy, f.name)
                   for f in dataclasses.fields(synthetic_economy)}
        for bag in ("commodity_extra", "unit_extra", "consumer_extra"):
            mapping.pop(bag)
        rebuilt = Economy.from_arrays(mapping)
        assert dict(rebuilt.unit_extra) == {}
        assert dict(rebuilt.consumer_extra) == {}

    def test_unknown_key_is_rejected(self, synthetic_economy):
        mapping = {f.name: getattr(synthetic_economy, f.name)
                   for f in dataclasses.fields(synthetic_economy)}
        mapping["market_clearing_residual"] = np.zeros(1)
        with pytest.raises(SchemaError, match="market_clearing_residual"):
            Economy.from_arrays(mapping)


class TestValidateLengths:
    def test_commodity_columns_must_agree(self, synthetic_economy):
        with pytest.raises(SchemaError, match="commodity_kind"):
            replaced(synthetic_economy, commodity_kind=synthetic_economy.commodity_kind[:-1])

    def test_endowment_length(self, synthetic_economy):
        with pytest.raises(SchemaError, match="endowment"):
            replaced(synthetic_economy, endowment=synthetic_economy.endowment[:-1])

    def test_unit_columns_must_agree(self, synthetic_economy):
        with pytest.raises(SchemaError, match="technology_scale"):
            replaced(synthetic_economy, technology_scale=synthetic_economy.technology_scale[:-1])

    def test_consumer_columns_must_agree(self, synthetic_economy):
        with pytest.raises(SchemaError, match="consumer_group"):
            replaced(synthetic_economy, consumer_group=synthetic_economy.consumer_group[:-1])

    def test_input_columns_must_agree(self, synthetic_economy):
        with pytest.raises(SchemaError, match="input_coefficient"):
            replaced(synthetic_economy, input_coefficient=synthetic_economy.input_coefficient[:-1])

    def test_offsets_length_must_be_units_plus_one(self, synthetic_economy):
        with pytest.raises(SchemaError, match="input_offsets"):
            replaced(synthetic_economy, input_offsets=synthetic_economy.input_offsets[:-1])


class TestValidateIdentifiers:
    @pytest.mark.parametrize("field", ["commodity_id", "unit_id", "consumer_id"])
    def test_identifier_must_equal_the_row_number(self, synthetic_economy, field):
        shuffled = getattr(synthetic_economy, field).copy()
        shuffled[0], shuffled[1] = shuffled[1], shuffled[0]
        with pytest.raises(SchemaError, match=field):
            replaced(synthetic_economy, **{field: shuffled})


class TestValidateEnums:
    def test_unknown_commodity_kind(self, synthetic_economy):
        kind = synthetic_economy.commodity_kind.copy()
        kind[2] = 9
        with pytest.raises(SchemaError, match="commodity_kind"):
            replaced(synthetic_economy, commodity_kind=kind)

    def test_unknown_technology_kind(self, synthetic_economy):
        kind = synthetic_economy.technology_kind.copy()
        kind[1] = 7
        with pytest.raises(SchemaError, match="technology_kind"):
            replaced(synthetic_economy, technology_kind=kind)

    def test_message_names_the_offending_row(self, synthetic_economy):
        kind = synthetic_economy.commodity_kind.copy()
        kind[4] = -3
        with pytest.raises(SchemaError, match=r"row 4"):
            replaced(synthetic_economy, commodity_kind=kind)


class TestValidateCommodityIndices:
    @pytest.mark.parametrize("bad", [-1, 15])
    def test_output_commodity_range(self, synthetic_economy, bad):
        column = synthetic_economy.output_commodity.copy()
        column[3] = bad
        with pytest.raises(SchemaError, match="output_commodity"):
            replaced(synthetic_economy, output_commodity=column)

    @pytest.mark.parametrize("bad", [-1, 15])
    def test_input_commodity_range(self, synthetic_economy, bad):
        column = synthetic_economy.input_commodity.copy()
        column[0] = bad
        with pytest.raises(SchemaError, match="input_commodity"):
            replaced(synthetic_economy, input_commodity=column)


class TestValidateOffsets:
    def test_first_offset_must_be_zero(self, synthetic_economy):
        offsets = synthetic_economy.input_offsets.copy()
        offsets[0] = 1
        with pytest.raises(SchemaError, match="input_offsets"):
            replaced(synthetic_economy, input_offsets=offsets)

    def test_last_offset_must_equal_the_input_count(self, synthetic_economy):
        offsets = synthetic_economy.input_offsets.copy()
        offsets[-1] -= 1
        with pytest.raises(SchemaError, match="input_offsets"):
            replaced(synthetic_economy, input_offsets=offsets)

    def test_offsets_must_not_decrease(self, synthetic_economy):
        offsets = synthetic_economy.input_offsets.copy()
        offsets[2], offsets[3] = offsets[3], offsets[2]
        with pytest.raises(SchemaError, match="input_offsets"):
            replaced(synthetic_economy, input_offsets=offsets)


class TestValidateFiniteness:
    @pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
    @pytest.mark.parametrize("field", ["endowment", "technology_scale", "input_coefficient"])
    def test_float_columns_must_be_finite(self, synthetic_economy, field, bad):
        column = getattr(synthetic_economy, field).copy()
        column[0] = bad
        with pytest.raises(SchemaError, match=field):
            replaced(synthetic_economy, **{field: column})

    def test_extra_arrays_must_be_finite(self, synthetic_economy):
        broken = synthetic_economy.unit_extra["effort_c"].copy()
        broken[0] = np.nan
        with pytest.raises(SchemaError, match="effort_c"):
            with_extra(synthetic_economy, "unit_extra", "effort_c", broken)


class TestValidateExtraShapes:
    def test_unit_extra_leading_dimension(self, synthetic_economy):
        with pytest.raises(SchemaError, match="effort_c"):
            with_extra(synthetic_economy, "unit_extra", "effort_c", np.zeros(3))

    def test_consumer_extra_leading_dimension(self, synthetic_economy):
        with pytest.raises(SchemaError, match="entitlement"):
            with_extra(synthetic_economy, "consumer_extra", "entitlement", np.zeros(99))

    def test_commodity_extra_leading_dimension(self, synthetic_economy):
        with pytest.raises(SchemaError, match="emission_factor"):
            with_extra(synthetic_economy, "commodity_extra", "emission_factor", np.zeros(2))

    def test_a_column_mapping_is_sized_by_the_array_it_indexes(self, synthetic_economy):
        """``utility_exponent_commodity`` is ``int64[k]``, not one row per consumer unit."""
        with pytest.raises(SchemaError, match="utility_exponent_commodity"):
            with_extra(
                synthetic_economy, "consumer_extra", "utility_exponent_commodity",
                np.arange(5, dtype=np.int64),
            )

    def test_a_column_mapping_of_the_right_length_is_accepted(self, synthetic_economy):
        columns = synthetic_economy.consumer_extra["utility_exponent"].shape[1]
        widened = with_extra(
            synthetic_economy, "consumer_extra", "utility_exponent_commodity",
            np.arange(columns, dtype=np.int64),
        )
        assert widened.consumer_extra["utility_exponent_commodity"].shape == (columns,)

    @pytest.mark.parametrize("bad", [-1, 15])
    def test_a_column_mapping_must_index_commodities(self, synthetic_economy, bad):
        columns = synthetic_economy.consumer_extra["utility_exponent_commodity"].copy()
        columns[0] = bad
        with pytest.raises(SchemaError, match="utility_exponent_commodity"):
            with_extra(
                synthetic_economy, "consumer_extra", "utility_exponent_commodity", columns
            )

    def test_a_column_mapping_must_be_int64(self, synthetic_economy):
        columns = synthetic_economy.consumer_extra["utility_exponent_commodity"].astype(np.int32)
        with pytest.raises(SchemaError, match="utility_exponent_commodity"):
            with_extra(
                synthetic_economy, "consumer_extra", "utility_exponent_commodity", columns
            )

    def test_two_dimensional_extra_is_accepted(self, synthetic_economy):
        widened = with_extra(
            synthetic_economy, "unit_extra", "shift_pattern",
            np.zeros((synthetic_economy.n_units, 3)),
        )
        assert widened.unit_extra["shift_pattern"].shape == (9, 3)


class TestValidateDtypes:
    @pytest.mark.parametrize(
        ("field", "dtype"),
        [("commodity_id", np.int32), ("commodity_kind", np.int64), ("endowment", np.float32),
         ("output_commodity", np.float64), ("technology_kind", np.int64),
         ("input_offsets", np.int32), ("input_coefficient", np.float32)],
    )
    def test_wrong_dtype_is_rejected(self, synthetic_economy, field, dtype):
        column = getattr(synthetic_economy, field).astype(dtype)
        with pytest.raises(SchemaError, match=field):
            replaced(synthetic_economy, **{field: column})


class TestEvolution:
    def test_replace_produces_a_new_validated_economy(self, synthetic_economy):
        grown = replaced(
            synthetic_economy,
            period=synthetic_economy.period + 1,
            technology_scale=synthetic_economy.technology_scale * 1.02,
        )
        assert grown.period == 1
        assert synthetic_economy.period == 0
        np.testing.assert_allclose(
            grown.technology_scale, np.asarray(synthetic_economy.technology_scale) * 1.02
        )
        assert grown.technology_scale.flags.writeable is False
