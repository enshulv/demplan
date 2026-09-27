"""Two plans compared field by field, and input use totalled over declared commodities.

Expected values are written out by hand. The economy and plan are the three-commodity ones of
``tests/test_differences.py``.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from demplan import (
    AllocatedPlan,
    Plan,
    PlanComparison,
    StatedPlan,
    compare_plans,
    input_use_on,
    require_comparable,
)
from test_differences import small_economy, small_plan

FIELDS = ("output", "input_use", "consumption", "shared_use")


def plan_of(kind=Plan, **changes) -> Plan:
    base = small_plan(**changes)
    return kind(**{f.name: getattr(base, f.name) for f in dataclasses.fields(Plan)})


class TestCompareValues:
    def test_identical_plans_compare_at_zero_on_every_field(self):
        comparison = compare_plans(small_plan(), small_plan())
        assert isinstance(comparison, PlanComparison)
        assert dict(comparison.max_relative_difference) == {name: 0.0 for name in FIELDS}
        assert dict(comparison.not_compared) == {}

    def test_the_fields_come_in_their_fixed_order(self):
        comparison = compare_plans(small_plan(), small_plan())
        assert list(comparison.max_relative_difference) == list(FIELDS)

    def test_each_entry_is_divided_by_the_larger_magnitude(self):
        """Output ``[8, 4, 2]`` against ``[8, 1, -2]``: entries 0, 3/4 and 4/2; the max is 2."""
        comparison = compare_plans(small_plan(), small_plan(output=np.array([8.0, 1.0, -2.0])))
        assert comparison.max_relative_difference["output"] == 2.0

    def test_the_field_value_is_the_maximum_over_entries(self):
        """Input use ``[4, 1, 2]`` against ``[5, 1, 1]``: entries 0.2, 0 and 0.5."""
        comparison = compare_plans(small_plan(), small_plan(input_use=np.array([5.0, 1.0, 1.0])))
        assert comparison.max_relative_difference["input_use"] == 0.5
        assert comparison.max_relative_difference["output"] == 0.0

    def test_zero_against_zero_is_zero(self):
        """Shared use is zero on commodities 0 and 2 in both; entry 1 differs by 1/4."""
        comparison = compare_plans(
            small_plan(shared_use=np.array([0.0, 4.0, 0.0])),
            small_plan(shared_use=np.array([0.0, 3.0, 0.0])),
        )
        assert comparison.max_relative_difference["shared_use"] == 0.25

    def test_an_all_zero_field_is_zero_not_nan(self):
        zeros = np.zeros(3)
        comparison = compare_plans(small_plan(shared_use=zeros), small_plan(shared_use=zeros))
        assert comparison.max_relative_difference["shared_use"] == 0.0

    def test_the_consumption_block_is_compared_entry_by_entry(self):
        comparison = compare_plans(
            small_plan(consumption=np.array([[3.0, 1.0], [4.0, 2.0]])),
            small_plan(consumption=np.array([[3.0, 1.0], [4.0, 8.0]])),
        )
        assert comparison.max_relative_difference["consumption"] == 0.75

    def test_nan_propagates(self):
        comparison = compare_plans(
            small_plan(output=np.array([np.nan, 4.0, 2.0])), small_plan()
        )
        assert np.isnan(comparison.max_relative_difference["output"])
        assert comparison.max_relative_difference["input_use"] == 0.0

    def test_the_comparison_is_symmetric(self):
        first = small_plan(output=np.array([8.0, 1.0, -2.0]), input_use=np.array([3.0, 7.0, 0.5]))
        second = small_plan(
            consumption=np.array([[1.0, 1.0], [9.0, 2.0]]), shared_use=np.array([1.0, 2.0, 3.0])
        )
        forward = compare_plans(first, second)
        backward = compare_plans(second, first)
        assert dict(forward.max_relative_difference) == dict(backward.max_relative_difference)
        assert dict(forward.not_compared) == dict(backward.not_compared)
        assert all(value > 0.0 for value in forward.max_relative_difference.values())

    def test_the_mappings_are_read_only(self):
        comparison = compare_plans(small_plan(), small_plan())
        with pytest.raises(TypeError):
            comparison.max_relative_difference["output"] = 1.0
        with pytest.raises(dataclasses.FrozenInstanceError):
            comparison.not_compared = {}


class TestNotCompared:
    def test_absent_from_both_plans(self):
        plan = small_plan(shared_use=None)
        comparison = compare_plans(plan, plan)
        assert comparison.not_compared == {"shared_use": "absent from both plans"}
        assert "shared_use" not in comparison.max_relative_difference

    def test_absent_from_one_plan(self):
        comparison = compare_plans(
            small_plan(consumption=None, consumption_commodity=None), small_plan()
        )
        assert comparison.not_compared == {"consumption": "absent from one plan"}
        backward = compare_plans(
            small_plan(), small_plan(consumption=None, consumption_commodity=None)
        )
        assert backward.not_compared == {"consumption": "absent from one plan"}

    def test_different_consumption_columns_are_not_compared(self):
        comparison = compare_plans(
            small_plan(), small_plan(consumption_commodity=np.array([0, 1], dtype=np.int64))
        )
        assert comparison.not_compared == {
            "consumption": "the two plans' consumption columns name different commodities"
        }
        assert list(comparison.max_relative_difference) == ["output", "input_use", "shared_use"]

    def test_a_different_number_of_columns_names_different_commodities(self):
        comparison = compare_plans(
            small_plan(),
            small_plan(
                consumption=np.zeros((2, 1)), consumption_commodity=np.array([1], dtype=np.int64)
            ),
        )
        assert comparison.not_compared == {
            "consumption": "the two plans' consumption columns name different commodities"
        }

    def test_stated_against_allocated_leaves_only_consumption_out(self):
        stated = plan_of(StatedPlan)
        allocated = plan_of(AllocatedPlan, output=np.array([4.0, 4.0, 2.0]))
        with pytest.raises(ValueError) as caught:
            require_comparable(stated, allocated)
        comparison = compare_plans(stated, allocated)
        assert comparison.not_compared == {"consumption": str(caught.value)}
        assert comparison.max_relative_difference == {
            "output": 0.5, "input_use": 0.0, "shared_use": 0.0,
        }

    def test_stated_against_a_plain_plan_is_compared(self):
        comparison = compare_plans(plan_of(StatedPlan), small_plan())
        assert comparison.not_compared == {}


class TestShapeMismatch:
    @pytest.mark.parametrize(
        "field, value",
        [
            ("output", np.array([1.0, 2.0])),
            ("input_use", np.array([1.0])),
            ("shared_use", np.zeros(4)),
        ],
    )
    def test_a_present_field_of_another_shape_is_a_value_error(self, field, value):
        with pytest.raises(ValueError, match=field):
            compare_plans(small_plan(), small_plan(**{field: value}))

    def test_a_consumption_block_with_other_rows_is_a_value_error(self):
        with pytest.raises(ValueError, match="consumption"):
            compare_plans(small_plan(), small_plan(consumption=np.zeros((3, 2))))


class TestInputUseOn:
    def test_the_sum_over_the_listed_commodities(self):
        """Input use ``[4, 1, 2]`` on commodities ``[2, 0, 2]``."""
        economy, plan = small_economy(), small_plan()
        assert input_use_on(economy, plan, np.array([2], dtype=np.int64)) == 6.0
        assert input_use_on(economy, plan, np.array([0], dtype=np.int64)) == 1.0
        assert input_use_on(economy, plan, np.array([0, 2], dtype=np.int64)) == 7.0
        assert input_use_on(economy, plan, np.array([1], dtype=np.int64)) == 0.0
        assert input_use_on(economy, plan, np.zeros(0, dtype=np.int64)) == 0.0

    def test_it_returns_a_python_float(self):
        value = input_use_on(small_economy(), small_plan(), np.array([2], dtype=np.int64))
        assert type(value) is float

    @pytest.mark.parametrize(
        "commodities, match",
        [
            (np.array([3], dtype=np.int64), r"commodities.*\b3\b"),
            (np.array([2, 2], dtype=np.int64), r"commodities.*\b2\b"),
            (np.array([2.0]), "commodities"),
        ],
    )
    def test_the_commodities_are_validated(self, commodities, match):
        with pytest.raises(ValueError, match=match):
            input_use_on(small_economy(), small_plan(), commodities)
