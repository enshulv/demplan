"""Structural contract of :class:`Economy`."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

import demplan
from demplan import Economy, SchemaError
from reference import synthetic


def replaced(economy: Economy, **changes) -> Economy:
    """``dataclasses.replace``, which re-runs validation through ``__post_init__``."""
    return dataclasses.replace(economy, **changes)


def with_extra(economy: Economy, bag: str, key: str, value) -> Economy:
    updated = dict(getattr(economy, bag))
    updated[key] = value
    return replaced(economy, **{bag: updated})


FIELDS = (
    "period",
    "commodity_id",
    "endowment",
    "unit_id",
    "technology_kind",
    "technology_scale",
    "input_offsets",
    "input_commodity",
    "input_coefficient",
    "output_offsets",
    "output_commodity",
    "output_coefficient",
    "consumer_id",
    "commodity_extra",
    "unit_extra",
    "consumer_extra",
)
"""Every field of ``Economy``, written out rather than read off the class."""

ARRAY_FIELDS = (
    "commodity_id",
    "endowment",
    "unit_id",
    "technology_kind",
    "technology_scale",
    "input_offsets",
    "input_commodity",
    "input_coefficient",
    "output_offsets",
    "output_commodity",
    "output_coefficient",
    "consumer_id",
)


class TestTheFields:
    def test_the_field_set_is_the_documented_one(self):
        assert {field.name for field in dataclasses.fields(Economy)} == set(FIELDS)

    @pytest.mark.parametrize("removed", ["commodity_kind", "unit_group", "consumer_group"])
    def test_a_removed_column_is_not_a_field(self, removed):
        assert removed not in {field.name for field in dataclasses.fields(Economy)}

    @pytest.mark.parametrize("removed", ["commodity_kind", "unit_group", "consumer_group"])
    def test_a_removed_column_is_refused_by_from_arrays(self, synthetic_economy, removed):
        mapping = {f.name: getattr(synthetic_economy, f.name)
                   for f in dataclasses.fields(synthetic_economy)}
        mapping[removed] = np.zeros(1, dtype=np.int64)
        with pytest.raises(SchemaError, match=removed):
            Economy.from_arrays(mapping)

    def test_commodities_of_kind_is_gone(self, synthetic_economy):
        assert not hasattr(synthetic_economy, "commodities_of_kind")

    @pytest.mark.parametrize("name", ["CommodityKind", "TechnologyKind"])
    def test_the_kind_enums_are_gone_from_the_package(self, name):
        assert not hasattr(demplan, name)
        assert name not in demplan.__all__


class TestImmutability:
    def test_fields_cannot_be_rebound(self, synthetic_economy):
        with pytest.raises(dataclasses.FrozenInstanceError):
            synthetic_economy.period = 7

    @pytest.mark.parametrize("field", ARRAY_FIELDS)
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

    def test_n_outputs_counts_output_entries(self, synthetic_economy):
        assert synthetic_economy.n_outputs == 9
        assert synthetic_economy.n_outputs == synthetic_economy.output_commodity.shape[0]

    def test_n_outputs_is_not_the_unit_count_once_a_unit_has_two_outputs(self):
        joint = synthetic.build_joint_product_economy()
        assert joint.n_units == 9
        assert joint.n_outputs == 11
        assert joint.n_outputs == int(joint.output_offsets[-1])
        assert isinstance(joint.n_outputs, int)

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
        for name in ("commodity_id", "endowment", "technology_kind", "input_offsets",
                     "input_commodity", "input_coefficient", "output_offsets",
                     "output_commodity", "output_coefficient"):
            np.testing.assert_array_equal(getattr(rebuilt, name), getattr(synthetic_economy, name))
        assert rebuilt.period == synthetic_economy.period
        assert set(rebuilt.unit_extra) == set(synthetic_economy.unit_extra)

    def test_the_mapping_the_loader_hands_over_is_accepted(self, synthetic_economy):
        """Text columns arrive from the Rust binding as lists of ``str``."""
        mapping = {f.name: getattr(synthetic_economy, f.name)
                   for f in dataclasses.fields(synthetic_economy)}
        mapping["technology_kind"] = [str(label) for label in synthetic_economy.technology_kind]
        mapping["commodity_extra"] = {
            key: [str(label) for label in value]
            for key, value in synthetic_economy.commodity_extra.items()
        }
        mapping["unit_extra"] = dict(mapping["unit_extra"])
        mapping["consumer_extra"] = dict(mapping["consumer_extra"])
        rebuilt = Economy.from_arrays(mapping)
        np.testing.assert_array_equal(rebuilt.technology_kind, synthetic_economy.technology_kind)
        np.testing.assert_array_equal(
            rebuilt.commodity_extra["hahnel_kind"], synthetic_economy.commodity_extra["hahnel_kind"]
        )

    def test_extra_bags_default_to_empty(self, synthetic_economy):
        mapping = {f.name: getattr(synthetic_economy, f.name)
                   for f in dataclasses.fields(synthetic_economy)}
        for bag in ("commodity_extra", "unit_extra", "consumer_extra"):
            mapping.pop(bag)
        rebuilt = Economy.from_arrays(mapping)
        assert dict(rebuilt.commodity_extra) == {}
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
        with pytest.raises(SchemaError, match="endowment"):
            replaced(synthetic_economy, endowment=synthetic_economy.endowment[:-1])

    def test_unit_columns_must_agree(self, synthetic_economy):
        with pytest.raises(SchemaError, match="technology_scale"):
            replaced(synthetic_economy, technology_scale=synthetic_economy.technology_scale[:-1])

    def test_the_technology_label_column_must_agree(self, synthetic_economy):
        with pytest.raises(SchemaError, match="technology_kind"):
            replaced(synthetic_economy, technology_kind=synthetic_economy.technology_kind[:-1])

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


class TestTechnologyLabels:
    """``technology_kind`` is one text label per producing unit, any label but the empty one."""

    def test_the_column_is_a_text_array(self, synthetic_economy):
        assert synthetic_economy.technology_kind.dtype.kind == "U"
        assert synthetic_economy.technology_kind.shape == (synthetic_economy.n_units,)

    def test_a_label_the_library_does_not_know_is_accepted(self, synthetic_economy):
        labels = ["my_own_production_function"] * synthetic_economy.n_units
        economy = replaced(synthetic_economy, technology_kind=np.array(labels))
        assert list(economy.technology_kind) == labels

    def test_the_two_library_labels_are_accepted(self, synthetic_economy):
        labels = np.array(["leontief", "cobb_douglas"] * 4 + ["leontief"])
        economy = replaced(synthetic_economy, technology_kind=labels)
        np.testing.assert_array_equal(economy.technology_kind, labels)

    def test_a_list_of_str_is_stored_as_a_read_only_text_array(self, synthetic_economy):
        labels = [f"technology {unit}" for unit in range(synthetic_economy.n_units)]
        economy = replaced(synthetic_economy, technology_kind=labels)
        column = economy.technology_kind
        assert isinstance(column, np.ndarray)
        assert column.dtype.kind == "U"
        assert column.flags.writeable is False
        assert list(column) == labels

    def test_editing_the_callers_list_afterwards_changes_nothing(self, synthetic_economy):
        labels = ["first"] * synthetic_economy.n_units
        economy = replaced(synthetic_economy, technology_kind=labels)
        labels[0] = "edited"
        assert economy.technology_kind[0] == "first"

    @pytest.mark.parametrize("row", [0, 4, 8])
    def test_an_empty_label_is_refused_and_the_message_names_the_row(
        self, synthetic_economy, row
    ):
        labels = ["leontief"] * synthetic_economy.n_units
        labels[row] = ""
        with pytest.raises(SchemaError, match=rf"technology_kind.*row {row}"):
            replaced(synthetic_economy, technology_kind=np.array(labels))

    def test_an_empty_label_in_a_list_is_refused(self, synthetic_economy):
        labels = ["leontief"] * synthetic_economy.n_units
        labels[3] = ""
        with pytest.raises(SchemaError, match="technology_kind"):
            replaced(synthetic_economy, technology_kind=labels)

    def test_a_label_of_blanks_is_a_label(self, synthetic_economy):
        """Only the empty label is refused; the library reads no label's meaning."""
        economy = replaced(synthetic_economy, technology_kind=[" "] * synthetic_economy.n_units)
        assert economy.technology_kind[0] == " "

    def test_an_integer_code_is_refused(self, synthetic_economy):
        with pytest.raises(SchemaError, match="technology_kind"):
            replaced(
                synthetic_economy,
                technology_kind=np.ones(synthetic_economy.n_units, dtype=np.int8),
            )

    def test_a_list_holding_something_other_than_str_is_refused(self, synthetic_economy):
        labels = ["leontief"] * synthetic_economy.n_units
        labels[2] = 1
        with pytest.raises(SchemaError, match="technology_kind"):
            replaced(synthetic_economy, technology_kind=labels)

    def test_a_bytes_array_is_refused(self, synthetic_economy):
        with pytest.raises(SchemaError, match="technology_kind"):
            replaced(
                synthetic_economy,
                technology_kind=np.array([b"leontief"] * synthetic_economy.n_units),
            )

    def test_an_object_array_of_str_is_refused(self, synthetic_economy):
        with pytest.raises(SchemaError, match="technology_kind"):
            replaced(
                synthetic_economy,
                technology_kind=np.array(["leontief"] * synthetic_economy.n_units, dtype=object),
            )

    def test_a_two_dimensional_text_array_is_refused(self, synthetic_economy):
        with pytest.raises(SchemaError, match="technology_kind"):
            replaced(
                synthetic_economy,
                technology_kind=np.full((synthetic_economy.n_units, 2), "leontief"),
            )

    def test_a_label_ending_in_nul_is_refused_rather_than_shortened(self, synthetic_economy):
        """A numpy text array drops trailing NUL characters, so storing one changes the label."""
        labels = ["leontief"] * synthetic_economy.n_units
        labels[5] = "leontief\x00"
        with pytest.raises(SchemaError, match="technology_kind"):
            replaced(synthetic_economy, technology_kind=labels)


class TestTextExtras:
    """An ``extra`` array may be one text label per row, as an array or as a list of ``str``."""

    @pytest.mark.parametrize(
        ("bag", "rows"),
        [("commodity_extra", "n_commodities"), ("unit_extra", "n_units"),
         ("consumer_extra", "n_consumers")],
    )
    def test_a_text_array_is_accepted_in_every_bag(self, synthetic_economy, bag, rows):
        labels = np.array([f"label {row}" for row in range(getattr(synthetic_economy, rows))])
        economy = with_extra(synthetic_economy, bag, "region", labels)
        np.testing.assert_array_equal(getattr(economy, bag)["region"], labels)

    @pytest.mark.parametrize(
        ("bag", "rows"),
        [("commodity_extra", "n_commodities"), ("unit_extra", "n_units"),
         ("consumer_extra", "n_consumers")],
    )
    def test_a_list_of_str_is_stored_as_a_read_only_text_array(self, synthetic_economy, bag, rows):
        labels = [f"label {row}" for row in range(getattr(synthetic_economy, rows))]
        economy = with_extra(synthetic_economy, bag, "region", labels)
        stored = getattr(economy, bag)["region"]
        assert isinstance(stored, np.ndarray)
        assert stored.dtype.kind == "U"
        assert stored.flags.writeable is False
        assert list(stored) == labels

    def test_non_ascii_labels_survive(self, synthetic_economy):
        labels = ["π"] + ["数量"] * (synthetic_economy.n_commodities - 1)
        economy = with_extra(synthetic_economy, "commodity_extra", "name", labels)
        assert list(economy.commodity_extra["name"]) == labels

    def test_an_empty_label_is_refused_and_the_message_names_the_key_and_row(
        self, synthetic_economy
    ):
        labels = ["x"] * synthetic_economy.n_commodities
        labels[6] = ""
        with pytest.raises(SchemaError, match=r"commodity_extra\['region'\].*row 6"):
            with_extra(synthetic_economy, "commodity_extra", "region", np.array(labels))

    def test_an_empty_label_in_a_list_is_refused(self, synthetic_economy):
        labels = ["x"] * synthetic_economy.n_units
        labels[-1] = ""
        with pytest.raises(SchemaError, match="region"):
            with_extra(synthetic_economy, "unit_extra", "region", labels)

    def test_a_text_array_of_the_wrong_length_is_refused(self, synthetic_economy):
        with pytest.raises(SchemaError, match="region"):
            with_extra(synthetic_economy, "commodity_extra", "region", np.array(["x", "y"]))

    def test_a_list_of_the_wrong_length_is_refused(self, synthetic_economy):
        with pytest.raises(SchemaError, match="region"):
            with_extra(synthetic_economy, "consumer_extra", "region", ["x"])

    def test_a_two_dimensional_text_array_is_refused(self, synthetic_economy):
        with pytest.raises(SchemaError, match="region"):
            with_extra(
                synthetic_economy, "unit_extra", "region",
                np.full((synthetic_economy.n_units, 2), "x"),
            )

    def test_a_list_holding_something_other_than_str_is_refused(self, synthetic_economy):
        values = [1.0] * synthetic_economy.n_units
        with pytest.raises(SchemaError, match="region"):
            with_extra(synthetic_economy, "unit_extra", "region", values)

    def test_a_list_mixing_str_and_numbers_is_refused(self, synthetic_economy):
        values = ["x"] * synthetic_economy.n_units
        values[4] = 3
        with pytest.raises(SchemaError, match="region"):
            with_extra(synthetic_economy, "unit_extra", "region", values)

    def test_a_label_ending_in_nul_is_refused_rather_than_shortened(self, synthetic_economy):
        labels = ["x"] * synthetic_economy.n_units
        labels[1] = "x\x00"
        with pytest.raises(SchemaError, match="region"):
            with_extra(synthetic_economy, "unit_extra", "region", labels)

    def test_the_finiteness_check_still_reaches_a_numeric_key_beside_a_text_one(
        self, synthetic_economy
    ):
        broken = synthetic_economy.unit_extra["effort_c"].copy()
        broken[0] = np.nan
        bag = dict(synthetic_economy.unit_extra)
        bag["region"] = ["x"] * synthetic_economy.n_units
        bag["effort_c"] = broken
        with pytest.raises(SchemaError, match="effort_c"):
            replaced(synthetic_economy, unit_extra=bag)

    def test_editing_the_callers_list_afterwards_changes_nothing(self, synthetic_economy):
        labels = ["x"] * synthetic_economy.n_consumers
        economy = with_extra(synthetic_economy, "consumer_extra", "region", labels)
        labels[0] = "edited"
        assert economy.consumer_extra["region"][0] == "x"


class TestOutputEntries:
    """Outputs are a flat array per output entry, laid out like the inputs."""

    def test_the_joint_product_economy_validates(self):
        joint = synthetic.build_joint_product_economy()
        np.testing.assert_array_equal(joint.output_offsets, [0, 2, 3, 4, 5, 7, 8, 9, 10, 11])
        np.testing.assert_array_equal(joint.output_commodity, [0, 7, 1, 2, 3, 8, 4, 5, 6, 7, 8])
        np.testing.assert_array_equal(
            joint.output_coefficient, [1.0, 0.5, 1.0, 1.0, 1.0, 0.25, 1.0, 1.0, 1.0, 1.0, 1.0]
        )

    def test_the_same_commodity_may_be_an_output_of_two_units(self):
        """Commodity 7 is unit 0's by-product and unit 7's only output."""
        joint = synthetic.build_joint_product_economy()
        assert list(joint.output_commodity).count(7) == 2

    def test_output_offsets_must_start_at_zero(self, synthetic_economy):
        offsets = synthetic_economy.output_offsets.copy()
        offsets[0] = 1
        with pytest.raises(SchemaError, match="output_offsets"):
            replaced(synthetic_economy, output_offsets=offsets)

    def test_output_offsets_must_end_at_the_output_count(self, synthetic_economy):
        offsets = synthetic_economy.output_offsets.copy()
        offsets[-1] = 8
        with pytest.raises(SchemaError, match="output_offsets"):
            replaced(synthetic_economy, output_offsets=offsets)

    def test_output_offsets_must_not_decrease(self):
        joint = synthetic.build_joint_product_economy()
        offsets = joint.output_offsets.copy()
        offsets[1], offsets[2] = offsets[2], offsets[1]
        with pytest.raises(SchemaError, match="output_offsets"):
            replaced(joint, output_offsets=offsets)

    def test_output_offsets_must_have_one_bound_per_unit_plus_one(self, synthetic_economy):
        with pytest.raises(SchemaError, match="output_offsets"):
            replaced(synthetic_economy, output_offsets=synthetic_economy.output_offsets[:-1])

    @pytest.mark.parametrize("unit", [0, 3, 8])
    def test_a_unit_without_an_output_entry_is_refused_and_named(self, synthetic_economy, unit):
        """Offsets that repeat leave a unit owning nothing, which the schema does not allow."""
        counts = np.ones(synthetic_economy.n_units, dtype=np.int64)
        counts[unit] = 0
        counts[(unit + 1) % synthetic_economy.n_units] += 1
        offsets = np.concatenate([[0], np.cumsum(counts)]).astype(np.int64)
        with pytest.raises(SchemaError, match=rf"output_offsets.*unit {unit}\b"):
            replaced(synthetic_economy, output_offsets=offsets)

    @pytest.mark.parametrize("bad", [-1, 15])
    def test_output_commodity_range(self, synthetic_economy, bad):
        column = synthetic_economy.output_commodity.copy()
        column[3] = bad
        with pytest.raises(SchemaError, match="output_commodity"):
            replaced(synthetic_economy, output_commodity=column)

    def test_a_unit_listing_one_commodity_twice_is_refused_and_named(self):
        joint = synthetic.build_joint_product_economy()
        column = joint.output_commodity.copy()
        column[6] = column[5]
        with pytest.raises(SchemaError, match=r"output_commodity.*unit 4.*commodity 8"):
            replaced(joint, output_commodity=column)

    @pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
    def test_output_coefficients_must_be_finite(self, synthetic_economy, bad):
        column = synthetic_economy.output_coefficient.copy()
        column[2] = bad
        with pytest.raises(SchemaError, match="output_coefficient"):
            replaced(synthetic_economy, output_coefficient=column)

    def test_output_commodity_and_coefficient_must_agree_in_length(self):
        joint = synthetic.build_joint_product_economy()
        with pytest.raises(SchemaError, match="output_coefficient"):
            replaced(joint, output_coefficient=joint.output_coefficient[:-1])

    def test_a_zero_or_negative_coefficient_is_a_number_the_schema_leaves_alone(
        self, synthetic_economy
    ):
        """What an output coefficient means is set by the unit's technology, not the schema."""
        column = synthetic_economy.output_coefficient.copy()
        column[0], column[1] = 0.0, -2.0
        economy = replaced(synthetic_economy, output_coefficient=column)
        assert economy.output_coefficient[1] == -2.0


class TestValidateCommodityIndices:
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
    @pytest.mark.parametrize(
        "field", ["endowment", "technology_scale", "input_coefficient", "output_coefficient"]
    )
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
        [("commodity_id", np.int32), ("endowment", np.float32),
         ("output_commodity", np.float64), ("input_offsets", np.int32),
         ("input_coefficient", np.float32), ("output_offsets", np.int32),
         ("output_coefficient", np.float32)],
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

    def test_replace_keeps_the_text_columns(self, synthetic_economy):
        grown = replaced(synthetic_economy, period=1)
        np.testing.assert_array_equal(grown.technology_kind, synthetic_economy.technology_kind)
        np.testing.assert_array_equal(
            grown.commodity_extra["hahnel_kind"], synthetic_economy.commodity_extra["hahnel_kind"]
        )


class TestTechnologyLabelConstants:
    def test_the_two_library_labels(self):
        assert demplan.LEONTIEF == "leontief"
        assert demplan.COBB_DOUGLAS == "cobb_douglas"

    def test_both_are_exported(self):
        assert "LEONTIEF" in demplan.__all__
        assert "COBB_DOUGLAS" in demplan.__all__
