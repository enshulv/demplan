"""Supply minus use, the budget difference and non-negativity, on any plan and across periods.

Every expected number here is written out by hand for a three-commodity economy small enough to
check on paper, or built by a loop over entries in this file. None is recomputed with the
accessor under test.

The economy (``small_economy``):

* commodities 0, 1, 2; endowment ``[0, 0, 10]``;
* unit 0 takes commodity 2 and has two output entries, commodity 1 then commodity 0 (a joint
  product listed out of commodity order);
* unit 1 takes commodities 0 and 2 and has one output entry, commodity 1;
* two consumer units.

The plan (``small_plan``): ``output = [8, 4, 2]`` on output entries of commodities ``[1, 0, 1]``,
so production is ``[4, 10, 0]``; ``input_use = [4, 1, 2]`` on inputs of commodities
``[2, 0, 2]``, so input use is ``[1, 0, 6]``; ``consumption = [[3, 1], [4, 2]]`` on columns of
commodities ``[1, 0]``, so consumption is ``[3, 7, 0]``; ``shared_use = [0, 2, 0]``.
Supply is ``[4, 10, 10]``, use ``[4, 9, 6]``, supply minus use ``[0, 1, 4]``.
"""

from __future__ import annotations

import dataclasses
import time

import numpy as np
import pytest

from demplan import (
    EXPENDITURE,
    INCOME,
    INDICATIVE_PRICE,
    LABOR_VALUE,
    SHADOW_PRICE,
    BudgetDifference,
    Coverage,
    Economy,
    MaterialBalance,
    NonNegativity,
    PeriodDifferences,
    PeriodsResult,
    Plan,
    PlanDifferences,
    RunResult,
    SchemaError,
    iterate,
    period_differences,
    plan_differences,
    run,
    run_periods,
)
from demplan.differences import (
    CAPITAL_STOCK_NON_NEGATIVITY,
    CONSUMER_UNIT_COUNT,
    CUMULATIVE_RESOURCE_USE,
    STOCK_FLOW_IDENTITY,
)

ABSENT_REASON_TAIL = (
    "declared absent, so use by consumer units is not known and supply minus use cannot be "
    "formed; output, input use and endowment are still reported"
)

BUDGET_REASON_HEAD = (
    "the budget difference needs a price, income per consumer unit and total expenditure per "
    "consumer unit, all filed by the mechanism in Plan.valuation; this plan has "
)

NO_RESOURCES_REASON = (
    "no resources were declared: pass resources= with the commodities whose input use draws "
    "on the initial endowment"
)
NO_CAPITAL_STOCK_REASON = "the data model has no capital stock, so there is no stock to test"
NO_STOCK_FLOW_REASON = (
    "the data model has no stock carried from one period to the next, so there is no identity "
    "to form"
)


def small_economy(
    endowment=(0.0, 0.0, 10.0), n_consumers: int = 2, period: int = 0
) -> Economy:
    """The three-commodity economy of the module docstring."""
    return Economy(
        period=period,
        commodity_id=np.arange(3, dtype=np.int64),
        endowment=np.array(endowment, dtype=np.float64),
        unit_id=np.arange(2, dtype=np.int64),
        technology_kind=np.array(["leontief", "leontief"]),
        technology_scale=np.ones(2),
        input_offsets=np.array([0, 1, 3], dtype=np.int64),
        input_commodity=np.array([2, 0, 2], dtype=np.int64),
        input_coefficient=np.array([1.0, 0.5, 1.0]),
        output_offsets=np.array([0, 2, 3], dtype=np.int64),
        output_commodity=np.array([1, 0, 1], dtype=np.int64),
        output_coefficient=np.array([2.0, 1.0, 1.0]),
        consumer_id=np.arange(n_consumers, dtype=np.int64),
    )


def four_commodity_economy(n_consumers: int = 2) -> Economy:
    """A one-unit economy with four commodities, for a commodity count that changes."""
    return Economy(
        period=0,
        commodity_id=np.arange(4, dtype=np.int64),
        endowment=np.array([0.0, 0.0, 10.0, 3.0]),
        unit_id=np.arange(1, dtype=np.int64),
        technology_kind=np.array(["leontief"]),
        technology_scale=np.ones(1),
        input_offsets=np.array([0, 1], dtype=np.int64),
        input_commodity=np.array([2], dtype=np.int64),
        input_coefficient=np.array([1.0]),
        output_offsets=np.array([0, 1], dtype=np.int64),
        output_commodity=np.array([0], dtype=np.int64),
        output_coefficient=np.array([1.0]),
        consumer_id=np.arange(n_consumers, dtype=np.int64),
    )


def small_plan(**changes) -> Plan:
    """The plan of the module docstring, with any field replaced."""
    fields = dict(
        output=np.array([8.0, 4.0, 2.0]),
        input_use=np.array([4.0, 1.0, 2.0]),
        consumption=np.array([[3.0, 1.0], [4.0, 2.0]]),
        consumption_commodity=np.array([1, 0], dtype=np.int64),
        shared_use=np.array([0.0, 2.0, 0.0]),
        valuation={},
        extra={},
    )
    fields.update(changes)
    return Plan(**fields)


def priced_plan(**changes) -> Plan:
    """:func:`small_plan` carrying a price, income and expenditure."""
    valuation = {
        INDICATIVE_PRICE: np.array([2.0, 3.0, 5.0]),
        INCOME: np.array([30.0, 40.0]),
        EXPENDITURE: np.array([25.0, 45.0]),
    }
    valuation.update(changes.pop("valuation", {}))
    return small_plan(valuation=valuation, **changes)


def assert_read_only_float64(array: np.ndarray) -> None:
    assert array.dtype == np.float64
    assert not array.flags.writeable


# --------------------------------------------------------------------------- material balance


class TestMaterialBalance:
    def test_every_component_is_the_hand_computed_vector(self):
        balance = plan_differences(small_economy(), small_plan()).material_balance
        np.testing.assert_array_equal(balance.total_output, [4.0, 10.0, 0.0])
        np.testing.assert_array_equal(balance.endowment, [0.0, 0.0, 10.0])
        np.testing.assert_array_equal(balance.total_input_use, [1.0, 0.0, 6.0])
        np.testing.assert_array_equal(balance.total_consumption, [3.0, 7.0, 0.0])
        np.testing.assert_array_equal(balance.shared_use, [0.0, 2.0, 0.0])
        np.testing.assert_array_equal(balance.supply, [4.0, 10.0, 10.0])
        np.testing.assert_array_equal(balance.use, [4.0, 9.0, 6.0])
        np.testing.assert_array_equal(balance.difference, [0.0, 1.0, 4.0])
        assert balance.why_not_computed is None

    def test_a_balanced_commodity_is_zero_and_not_none(self):
        balance = plan_differences(small_economy(), small_plan()).material_balance
        assert balance.difference is not None
        assert balance.difference[0] == 0.0

    def test_the_sign_is_supply_minus_use(self):
        """Use above supply on commodity 0 gives a negative entry; no absolute value is taken."""
        plan = small_plan(shared_use=np.array([2.0, 2.0, 0.0]))
        balance = plan_differences(small_economy(), plan).material_balance
        np.testing.assert_array_equal(balance.difference, [-2.0, 1.0, 4.0])

    def test_joint_product_outputs_land_on_their_own_commodities(self):
        """Output entry 0 is commodity 1 and entry 1 is commodity 0, both of unit 0."""
        plan = small_plan(output=np.array([8.0, 0.0, 0.0]))
        balance = plan_differences(small_economy(), plan).material_balance
        np.testing.assert_array_equal(balance.total_output, [0.0, 8.0, 0.0])
        plan = small_plan(output=np.array([0.0, 4.0, 0.0]))
        balance = plan_differences(small_economy(), plan).material_balance
        np.testing.assert_array_equal(balance.total_output, [4.0, 0.0, 0.0])

    def test_consumption_is_filed_under_the_commodity_each_column_names(self):
        plan = small_plan(consumption=np.array([[3.0, 0.0], [0.0, 0.0]]))
        balance = plan_differences(small_economy(), plan).material_balance
        np.testing.assert_array_equal(balance.total_consumption, [0.0, 3.0, 0.0])

    def test_repeated_consumption_columns_add_up_on_their_commodity(self):
        """Both columns name commodity 1: 3 + 1 and 4 + 2 make 10, and use of it is 0 + 10 + 2."""
        plan = small_plan(consumption_commodity=np.array([1, 1], dtype=np.int64))
        balance = plan_differences(small_economy(), plan).material_balance
        np.testing.assert_array_equal(balance.total_consumption, [0.0, 10.0, 0.0])
        np.testing.assert_array_equal(balance.use, [1.0, 12.0, 6.0])
        np.testing.assert_array_equal(balance.difference, [3.0, -2.0, 4.0])

    def test_the_arrays_are_read_only_float64(self):
        balance = plan_differences(small_economy(), small_plan()).material_balance
        for name in (
            "total_output", "endowment", "total_input_use", "total_consumption",
            "shared_use", "supply", "use", "difference",
        ):
            assert_read_only_float64(getattr(balance, name))

    def test_the_report_is_frozen(self):
        differences = plan_differences(small_economy(), small_plan())
        with pytest.raises(dataclasses.FrozenInstanceError):
            differences.material_balance = None
        with pytest.raises(dataclasses.FrozenInstanceError):
            differences.material_balance.difference = None

    def test_the_library_reads_no_extra_key(self):
        """A plan-side ``consumer_demand`` that disagrees with the fixed fields changes nothing."""
        economy = small_economy()
        plain = plan_differences(economy, small_plan()).material_balance
        with_extra = plan_differences(
            economy, small_plan(extra={"consumer_demand": np.array([100.0, 100.0, 100.0])})
        ).material_balance
        np.testing.assert_array_equal(with_extra.difference, plain.difference)
        np.testing.assert_array_equal(with_extra.use, plain.use)

    def test_nan_in_the_plan_is_carried_into_the_difference(self):
        """A plan is not refused for a non-finite value; IEEE arithmetic carries it."""
        plan = small_plan(shared_use=np.array([0.0, np.nan, 0.0]))
        balance = plan_differences(small_economy(), plan).material_balance
        assert np.isnan(balance.difference[1])
        assert balance.difference[0] == 0.0
        assert balance.difference[2] == 4.0


class TestMaterialBalanceWhenUseIsNotKnown:
    def test_absent_consumption_leaves_use_and_difference_none(self):
        plan = small_plan(consumption=None, consumption_commodity=None)
        balance = plan_differences(small_economy(), plan).material_balance
        assert balance.use is None
        assert balance.difference is None
        assert balance.total_consumption is None
        assert balance.why_not_computed == f"Plan.consumption is {ABSENT_REASON_TAIL}"

    def test_absent_shared_use_leaves_use_and_difference_none(self):
        plan = small_plan(shared_use=None)
        balance = plan_differences(small_economy(), plan).material_balance
        assert balance.use is None
        assert balance.difference is None
        assert balance.shared_use is None
        assert balance.why_not_computed == f"Plan.shared_use is {ABSENT_REASON_TAIL}"

    def test_both_absent_are_named_in_declaration_order(self):
        plan = small_plan(consumption=None, consumption_commodity=None, shared_use=None)
        balance = plan_differences(small_economy(), plan).material_balance
        assert balance.use is None
        assert balance.difference is None
        assert balance.why_not_computed == (
            f"Plan.consumption and shared_use are {ABSENT_REASON_TAIL}"
        )

    def test_the_components_the_plan_carries_are_still_filled_in(self):
        plan = small_plan(shared_use=None)
        balance = plan_differences(small_economy(), plan).material_balance
        np.testing.assert_array_equal(balance.total_output, [4.0, 10.0, 0.0])
        np.testing.assert_array_equal(balance.endowment, [0.0, 0.0, 10.0])
        np.testing.assert_array_equal(balance.total_input_use, [1.0, 0.0, 6.0])
        np.testing.assert_array_equal(balance.total_consumption, [3.0, 7.0, 0.0])
        np.testing.assert_array_equal(balance.supply, [4.0, 10.0, 10.0])

        plan = small_plan(consumption=None, consumption_commodity=None)
        balance = plan_differences(small_economy(), plan).material_balance
        np.testing.assert_array_equal(balance.shared_use, [0.0, 2.0, 0.0])
        np.testing.assert_array_equal(balance.supply, [4.0, 10.0, 10.0])


class TestTheInputs:
    def test_a_non_plan_is_a_type_error(self):
        with pytest.raises(TypeError, match="Plan"):
            plan_differences(small_economy(), {"output": np.zeros(3)})

    def test_a_plan_shaped_for_another_economy_raises_schema_error(self):
        plan = small_plan(output=np.array([8.0, 4.0]))
        with pytest.raises(SchemaError, match="output"):
            plan_differences(small_economy(), plan)

    def test_a_consumption_block_of_the_wrong_shape_raises_schema_error(self):
        plan = small_plan(consumption=np.array([[3.0, 1.0]]))
        with pytest.raises(SchemaError, match="consumption"):
            plan_differences(small_economy(), plan)

    def test_a_registered_valuation_of_the_wrong_length_raises_schema_error(self):
        plan = small_plan(valuation={INCOME: np.array([1.0, 2.0, 3.0])})
        with pytest.raises(SchemaError, match="income"):
            plan_differences(small_economy(), plan)

    @pytest.mark.parametrize(
        "bads, match",
        [
            (np.array([3], dtype=np.int64), r"bads.*\b3\b"),
            (np.array([0, -1], dtype=np.int64), r"bads.*-1"),
            (np.array([1, 1], dtype=np.int64), r"bads.*\b1\b"),
            (np.array([1.0]), "bads"),
            (np.array([[1]], dtype=np.int64), "bads"),
            ([1], "bads"),
        ],
    )
    def test_a_malformed_bads_declaration_is_a_value_error(self, bads, match):
        with pytest.raises(ValueError, match=match):
            plan_differences(small_economy(), small_plan(), bads=bads)

    def test_the_result_is_bit_identical_across_calls(self):
        economy, plan = small_economy(), priced_plan()
        first = plan_differences(economy, plan, price=INDICATIVE_PRICE)
        second = plan_differences(economy, plan, price=INDICATIVE_PRICE)
        assert first.material_balance.difference.tobytes() == (
            second.material_balance.difference.tobytes()
        )
        assert first.budget.difference.tobytes() == second.budget.difference.tobytes()

    def test_the_report_carries_the_three_parts(self):
        differences = plan_differences(small_economy(), small_plan())
        assert isinstance(differences, PlanDifferences)
        assert isinstance(differences.material_balance, MaterialBalance)
        assert isinstance(differences.budget, BudgetDifference)
        assert isinstance(differences.non_negativity, NonNegativity)


# --------------------------------------------------------------------------- budget


def budget_reason(*missing: str) -> str:
    return BUDGET_REASON_HEAD + "; ".join(missing)


NO_PRICE_DECLARED = (
    "no declared price (pass price= naming the valuation key the prices are filed under; "
    "this plan carries {keys})"
)


class TestBudgetDifference:
    def test_all_three_present_gives_income_minus_expenditure(self):
        budget = plan_differences(small_economy(), priced_plan(), price=INDICATIVE_PRICE).budget
        assert budget.price_key == INDICATIVE_PRICE
        np.testing.assert_array_equal(budget.income, [30.0, 40.0])
        np.testing.assert_array_equal(budget.expenditure, [25.0, 45.0])
        np.testing.assert_array_equal(budget.difference, [5.0, -5.0])
        assert budget.why_not_computed is None

    def test_priced_consumption_is_each_units_consumption_at_the_declared_price(self):
        """Unit 0: 3 of commodity 1 at 3 plus 1 of commodity 0 at 2 is 11; unit 1: 12 + 4."""
        budget = plan_differences(small_economy(), priced_plan(), price=INDICATIVE_PRICE).budget
        np.testing.assert_array_equal(budget.priced_consumption, [11.0, 16.0])

    def test_the_price_is_the_key_the_caller_names(self):
        plan = priced_plan(valuation={LABOR_VALUE: np.array([1.0, 10.0, 100.0])})
        budget = plan_differences(small_economy(), plan, price=LABOR_VALUE).budget
        assert budget.price_key == LABOR_VALUE
        np.testing.assert_array_equal(budget.priced_consumption, [31.0, 42.0])

    def test_an_unregistered_key_serves_as_the_price_when_named(self):
        plan = priced_plan(valuation={"my_price": np.array([1.0, 1.0, 1.0])})
        budget = plan_differences(small_economy(), plan, price="my_price").budget
        np.testing.assert_array_equal(budget.priced_consumption, [4.0, 6.0])
        np.testing.assert_array_equal(budget.difference, [5.0, -5.0])

    def test_absent_consumption_leaves_priced_consumption_none_but_the_difference_stands(self):
        plan = priced_plan(consumption=None, consumption_commodity=None)
        budget = plan_differences(small_economy(), plan, price=INDICATIVE_PRICE).budget
        assert budget.priced_consumption is None
        np.testing.assert_array_equal(budget.difference, [5.0, -5.0])
        assert budget.why_not_computed is None

    def test_the_price_is_never_picked_automatically(self):
        """The plan carries a registered price, income and expenditure, and no price= is given."""
        budget = plan_differences(small_economy(), priced_plan()).budget
        assert budget.difference is None
        assert budget.priced_consumption is None
        assert budget.price_key is None
        assert budget.why_not_computed == budget_reason(
            NO_PRICE_DECLARED.format(keys="'expenditure', 'income', 'indicative_price'")
        )

    def test_there_is_no_fallback_to_entitlement(self):
        economy = dataclasses.replace(
            small_economy(), consumer_extra={"entitlement": np.array([30.0, 40.0])}
        )
        plan = small_plan(
            valuation={
                INDICATIVE_PRICE: np.array([2.0, 3.0, 5.0]),
                EXPENDITURE: np.array([25.0, 45.0]),
            }
        )
        budget = plan_differences(economy, plan, price=INDICATIVE_PRICE).budget
        assert budget.difference is None
        assert budget.income is None
        assert budget.why_not_computed == budget_reason("no valuation['income']")

    def test_a_plan_with_no_valuation_says_so(self):
        budget = plan_differences(small_economy(), small_plan()).budget
        assert budget.why_not_computed == budget_reason(
            NO_PRICE_DECLARED.format(keys="no valuation key"),
            "no valuation['income']",
            "no valuation['expenditure']",
        )

    def test_the_components_the_plan_carries_are_filled_in_when_the_difference_is_not(self):
        plan = small_plan(valuation={INCOME: np.array([30.0, 40.0])})
        budget = plan_differences(small_economy(), plan, price=INDICATIVE_PRICE).budget
        np.testing.assert_array_equal(budget.income, [30.0, 40.0])
        assert budget.expenditure is None
        assert budget.difference is None
        assert budget.priced_consumption is None
        assert budget.price_key == INDICATIVE_PRICE

    def test_a_price_that_is_not_one_entry_per_commodity_is_a_value_error(self):
        with pytest.raises(ValueError, match="income"):
            plan_differences(small_economy(), priced_plan(), price=INCOME)

    @pytest.mark.parametrize("key", [INCOME, EXPENDITURE])
    def test_a_per_consumer_key_is_refused_as_a_price_even_when_the_counts_coincide(self, key):
        """Three consumer units and three commodities: the shape check alone would pass it."""
        plan = small_plan(
            consumption=np.ones((3, 2)),
            valuation={INCOME: np.array([1.0, 2.0, 3.0]), EXPENDITURE: np.zeros(3)},
        )
        with pytest.raises(ValueError, match=rf"price='{key}'.*one entry per consumer unit"):
            plan_differences(small_economy(n_consumers=3), plan, price=key)

    def test_a_per_consumer_key_is_refused_as_a_price_when_the_plan_lacks_it(self):
        with pytest.raises(ValueError, match="price='income'"):
            plan_differences(small_economy(), small_plan(), price=INCOME)

    def test_the_arrays_are_read_only_float64(self):
        budget = plan_differences(small_economy(), priced_plan(), price=INDICATIVE_PRICE).budget
        for name in ("income", "expenditure", "difference", "priced_consumption"):
            assert_read_only_float64(getattr(budget, name))


def _budget_case_plan(price_state: str, has_income: bool, has_expenditure: bool):
    valuation = {"other_key": np.array([1.0, 1.0, 1.0])}
    if price_state == "present":
        valuation[INDICATIVE_PRICE] = np.array([2.0, 3.0, 5.0])
    if has_income:
        valuation[INCOME] = np.array([30.0, 40.0])
    if has_expenditure:
        valuation[EXPENDITURE] = np.array([25.0, 45.0])
    return small_plan(valuation=valuation), valuation


BUDGET_CASES = [
    (price_state, has_income, has_expenditure)
    for price_state in ("undeclared", "declared_but_missing", "present")
    for has_income in (True, False)
    for has_expenditure in (True, False)
    if not (price_state == "present" and has_income and has_expenditure)
]


@pytest.mark.parametrize("price_state, has_income, has_expenditure", BUDGET_CASES)
def test_every_combination_of_missing_items_gives_its_exact_reason(
    price_state, has_income, has_expenditure
):
    plan, valuation = _budget_case_plan(price_state, has_income, has_expenditure)
    price = None if price_state == "undeclared" else INDICATIVE_PRICE
    missing = []
    if price_state == "undeclared":
        keys = ", ".join(repr(key) for key in sorted(valuation))
        missing.append(NO_PRICE_DECLARED.format(keys=keys))
    elif price_state == "declared_but_missing":
        missing.append("no valuation['indicative_price'] (the declared price)")
    if not has_income:
        missing.append("no valuation['income']")
    if not has_expenditure:
        missing.append("no valuation['expenditure']")

    budget = plan_differences(small_economy(), plan, price=price).budget
    assert budget.difference is None
    assert budget.why_not_computed == budget_reason(*missing)


def test_a_declared_price_key_missing_from_the_plan_names_that_key():
    plan = small_plan(valuation={INCOME: np.array([30.0, 40.0]), EXPENDITURE: np.zeros(2)})
    budget = plan_differences(small_economy(), plan, price="sale_price").budget
    assert budget.why_not_computed == budget_reason(
        "no valuation['sale_price'] (the declared price)"
    )
    assert budget.price_key == "sale_price"


# --------------------------------------------------------------------------- non-negativity


class TestNonNegativity:
    def test_the_minimum_and_count_of_each_quantity(self):
        plan = small_plan(
            output=np.array([8.0, -4.0, -2.0]),
            input_use=np.array([4.0, 1.0, 2.0]),
            consumption=np.array([[3.0, -1.0], [4.0, 2.0]]),
            shared_use=np.array([0.0, -0.5, 0.0]),
        )
        report = plan_differences(small_economy(), plan).non_negativity
        assert dict(report.minimum) == {
            "output": -4.0, "input_use": 1.0, "consumption": -1.0, "shared_use": -0.5,
        }
        assert dict(report.negative_count) == {
            "output": 2, "input_use": 0, "consumption": 1, "shared_use": 1,
        }
        assert dict(report.not_checked) == {}
        assert list(report.minimum) == ["output", "input_use", "consumption", "shared_use"]

    def test_every_registered_price_key_present_is_checked(self):
        plan = small_plan(
            valuation={
                INDICATIVE_PRICE: np.array([2.0, -3.0, 5.0]),
                LABOR_VALUE: np.array([-1.0, -2.0, 0.0]),
                SHADOW_PRICE: np.array([0.0, 0.0, 0.0]),
            }
        )
        report = plan_differences(small_economy(), plan).non_negativity
        assert report.minimum[f"valuation.{INDICATIVE_PRICE}"] == -3.0
        assert report.negative_count[f"valuation.{INDICATIVE_PRICE}"] == 1
        assert report.minimum[f"valuation.{LABOR_VALUE}"] == -2.0
        assert report.negative_count[f"valuation.{LABOR_VALUE}"] == 2
        assert report.minimum[f"valuation.{SHADOW_PRICE}"] == 0.0
        assert report.negative_count[f"valuation.{SHADOW_PRICE}"] == 0

    def test_nan_is_ignored_in_the_minimum_and_the_count(self):
        plan = small_plan(
            output=np.array([np.nan, -1.0, 3.0]),
            valuation={INDICATIVE_PRICE: np.array([np.nan, 4.0, 2.0])},
        )
        report = plan_differences(small_economy(), plan).non_negativity
        assert report.minimum["output"] == -1.0
        assert report.negative_count["output"] == 1
        assert report.minimum[f"valuation.{INDICATIVE_PRICE}"] == 2.0

    def test_bads_exempt_their_prices(self):
        """Commodity 1 is a bad: its negative price is skipped, commodity 0's is counted."""
        plan = small_plan(valuation={INDICATIVE_PRICE: np.array([-2.0, -30.0, 5.0])})
        report = plan_differences(
            small_economy(), plan, bads=np.array([1], dtype=np.int64)
        ).non_negativity
        assert report.minimum[f"valuation.{INDICATIVE_PRICE}"] == -2.0
        assert report.negative_count[f"valuation.{INDICATIVE_PRICE}"] == 1

    def test_bads_never_exempt_a_quantity(self):
        """Output entry 0 and consumption column 0 are commodity 1, the declared bad."""
        plan = small_plan(
            output=np.array([-8.0, 4.0, 2.0]),
            consumption=np.array([[-3.0, 1.0], [4.0, 2.0]]),
        )
        report = plan_differences(
            small_economy(), plan, bads=np.array([1], dtype=np.int64)
        ).non_negativity
        assert report.minimum["output"] == -8.0
        assert report.negative_count["output"] == 1
        assert report.minimum["consumption"] == -3.0
        assert report.negative_count["consumption"] == 1

    def test_bads_never_exempt_shared_use(self):
        """``shared_use`` is one entry per commodity like a price, and still a quantity."""
        plan = small_plan(shared_use=np.array([0.0, -2.0, 0.0]))
        report = plan_differences(
            small_economy(), plan, bads=np.array([1], dtype=np.int64)
        ).non_negativity
        assert report.minimum["shared_use"] == -2.0
        assert report.negative_count["shared_use"] == 1
        assert "shared_use" not in report.not_checked

    def test_no_bads_means_every_price_is_checked(self):
        plan = small_plan(valuation={INDICATIVE_PRICE: np.array([-2.0, -30.0, 5.0])})
        report = plan_differences(small_economy(), plan).non_negativity
        assert report.minimum[f"valuation.{INDICATIVE_PRICE}"] == -30.0
        assert report.negative_count[f"valuation.{INDICATIVE_PRICE}"] == 2

    def test_an_absent_field_is_not_checked_and_says_why(self):
        plan = small_plan(consumption=None, consumption_commodity=None, shared_use=None)
        report = plan_differences(small_economy(), plan).non_negativity
        assert report.not_checked["consumption"] == "declared absent by the plan"
        assert report.not_checked["shared_use"] == "declared absent by the plan"
        assert "consumption" not in report.minimum
        assert "shared_use" not in report.negative_count

    def test_an_unregistered_valuation_key_is_not_checked_and_says_why(self):
        plan = small_plan(valuation={"my_price": np.array([-1.0, -1.0, -1.0])})
        report = plan_differences(small_economy(), plan).non_negativity
        assert report.not_checked["valuation.my_price"] == (
            "unregistered valuation key: the library does not know what it holds"
        )
        assert "valuation.my_price" not in report.minimum

    def test_a_price_whose_every_commodity_is_a_bad_has_no_entries_to_check(self):
        plan = small_plan(valuation={INDICATIVE_PRICE: np.array([-1.0, -1.0, -1.0])})
        report = plan_differences(
            small_economy(), plan, bads=np.array([2, 0, 1], dtype=np.int64)
        ).non_negativity
        assert report.minimum[f"valuation.{INDICATIVE_PRICE}"] is None
        assert report.negative_count[f"valuation.{INDICATIVE_PRICE}"] == 0
        assert report.not_checked[f"valuation.{INDICATIVE_PRICE}"] == "no entries to check"

    def test_an_all_nan_quantity_has_no_minimum_and_says_every_entry_is_nan(self):
        plan = small_plan(shared_use=np.full(3, np.nan))
        report = plan_differences(small_economy(), plan).non_negativity
        assert report.minimum["shared_use"] is None
        assert report.negative_count["shared_use"] == 0
        assert report.not_checked["shared_use"] == "every entry is NaN"

    def test_a_price_whose_every_entry_left_after_bads_is_nan_says_so(self):
        plan = small_plan(valuation={INDICATIVE_PRICE: np.array([np.nan, -5.0, np.nan])})
        report = plan_differences(
            small_economy(), plan, bads=np.array([1], dtype=np.int64)
        ).non_negativity
        entry = f"valuation.{INDICATIVE_PRICE}"
        assert report.minimum[entry] is None
        assert report.negative_count[entry] == 0
        assert report.not_checked[entry] == "every entry is NaN"

    def test_a_quantity_with_no_entries_has_no_entries_to_check(self):
        """No consumer unit: the consumption block has no entry at all."""
        plan = small_plan(consumption=np.zeros((0, 2)))
        report = plan_differences(small_economy(n_consumers=0), plan).non_negativity
        assert report.minimum["consumption"] is None
        assert report.negative_count["consumption"] == 0
        assert report.not_checked["consumption"] == "no entries to check"

    def test_income_and_expenditure_are_not_prices(self):
        plan = small_plan(valuation={INCOME: np.array([-1.0, 1.0]), EXPENDITURE: np.zeros(2)})
        report = plan_differences(small_economy(), plan).non_negativity
        for key in (INCOME, EXPENDITURE):
            assert f"valuation.{key}" not in report.minimum
            assert f"valuation.{key}" not in report.not_checked

    def test_the_mappings_are_read_only(self):
        report = plan_differences(small_economy(), small_plan()).non_negativity
        with pytest.raises(TypeError):
            report.minimum["output"] = 0.0
        with pytest.raises(TypeError):
            report.not_checked["x"] = "y"


# --------------------------------------------------------------------------- run


class ReturningProcedure:
    """Returns a fixed plan and counts its calls."""

    def __init__(self, plan: Plan):
        self.plan = plan

    def solve(self, economy, seed):
        return self.plan


class SlowTotalsPlan(Plan):
    """A plan whose ``total_output`` sleeps, so time spent in the difference report shows.

    It counts its calls, so a test can tell that the difference computation reached it.
    """

    calls: list = []

    def total_output(self, economy):
        SlowTotalsPlan.calls.append(1)
        time.sleep(SLOW_SECONDS)
        return super().total_output(economy)


SLOW_SECONDS = 0.3


def slow_totals_plan() -> SlowTotalsPlan:
    """:func:`small_plan` as a :class:`SlowTotalsPlan`."""
    base = small_plan()
    return SlowTotalsPlan(**{f.name: getattr(base, f.name) for f in dataclasses.fields(Plan)})


class TestRunAttachesTheReport:
    def test_the_report_is_attached_with_the_hand_computed_difference(self):
        result = run(ReturningProcedure(small_plan()), small_economy(), seed=0)
        assert isinstance(result.differences, PlanDifferences)
        np.testing.assert_array_equal(result.differences.material_balance.difference, [0, 1, 4])

    def test_bads_and_price_reach_the_report(self):
        plan = priced_plan(valuation={INDICATIVE_PRICE: np.array([-2.0, -30.0, 5.0])})
        result = run(
            ReturningProcedure(plan), small_economy(), seed=0,
            bads=np.array([1], dtype=np.int64), price=INDICATIVE_PRICE,
        )
        np.testing.assert_array_equal(result.differences.budget.difference, [5.0, -5.0])
        assert result.differences.non_negativity.minimum[f"valuation.{INDICATIVE_PRICE}"] == -2.0

    def test_differences_false_gives_none_and_computes_nothing(self):
        SlowTotalsPlan.calls = []
        plan = slow_totals_plan()
        result = run(ReturningProcedure(plan), small_economy(), seed=0, differences=False)
        assert result.differences is None
        assert SlowTotalsPlan.calls == []

    def test_wall_seconds_excludes_the_difference_computation(self):
        SlowTotalsPlan.calls = []
        plan = slow_totals_plan()
        started = time.perf_counter()
        result = run(ReturningProcedure(plan), small_economy(), seed=0)
        elapsed = time.perf_counter() - started
        assert SlowTotalsPlan.calls, "the difference computation never reached the plan"
        assert elapsed >= SLOW_SECONDS
        assert result.summary.wall_seconds < SLOW_SECONDS / 2

    def test_a_malformed_plan_raises_schema_error_from_run(self):
        plan = small_plan(output=np.array([1.0]))
        with pytest.raises(SchemaError):
            run(ReturningProcedure(plan), small_economy(), seed=0)

    def test_a_malformed_plan_passes_through_when_differences_are_off(self):
        plan = small_plan(output=np.array([1.0]))
        result = run(ReturningProcedure(plan), small_economy(), seed=0, differences=False)
        assert result.plan is plan

    def test_run_result_defaults_differences_to_none(self):
        summary = run(ReturningProcedure(small_plan()), small_economy(), 0).summary
        assert RunResult(plan=small_plan(), summary=summary).differences is None

    def test_the_loop_summary_is_unchanged(self):
        class Looping:
            def solve(self, economy, seed):
                iterate(lambda: 0, lambda s: s + 1, lambda s: s >= 3, 10)
                return small_plan()

        result = run(Looping(), small_economy(), seed=0)
        assert result.summary.rounds == 3
        assert result.differences is not None


# --------------------------------------------------------------------------- period differences


def resource_plan(input_use) -> Plan:
    """:func:`small_plan` with its input use replaced; inputs are commodities 2, 0, 2."""
    return small_plan(input_use=np.array(input_use, dtype=np.float64))


class TestPeriodDifferences:
    def test_cumulative_use_is_the_running_sum_of_each_periods_input_use(self):
        """Resources 2 and 0. Period input use of 2: 4+2, 1+1, 0+5; of 0: 1, 3, 0."""
        economies = [small_economy(), small_economy(), small_economy()]
        plans = [
            resource_plan([4.0, 1.0, 2.0]),
            resource_plan([1.0, 3.0, 1.0]),
            resource_plan([0.0, 0.0, 5.0]),
        ]
        report = period_differences(
            economies, plans, resources=np.array([2, 0], dtype=np.int64)
        )
        np.testing.assert_array_equal(report.initial_endowment, [10.0, 0.0])
        np.testing.assert_array_equal(
            report.cumulative_use, [[6.0, 1.0], [8.0, 4.0], [13.0, 4.0]]
        )
        np.testing.assert_array_equal(
            report.resource_difference, [[4.0, -1.0], [2.0, -4.0], [-3.0, -4.0]]
        )
        assert report.why_resources_not_computed is None

    def test_the_initial_endowment_is_period_zeros(self):
        economies = [
            small_economy(endowment=(0.0, 0.0, 10.0)),
            small_economy(endowment=(0.0, 0.0, 99.0)),
        ]
        plans = [resource_plan([1.0, 0.0, 0.0]), resource_plan([1.0, 0.0, 0.0])]
        report = period_differences(economies, plans, resources=np.array([2], dtype=np.int64))
        np.testing.assert_array_equal(report.initial_endowment, [10.0])
        np.testing.assert_array_equal(report.resource_difference, [[9.0], [8.0]])

    def test_no_resources_is_not_computed_and_says_why(self):
        report = period_differences([small_economy()], [small_plan()])
        assert report.initial_endowment is None
        assert report.cumulative_use is None
        assert report.resource_difference is None
        assert report.why_resources_not_computed == NO_RESOURCES_REASON

    def test_a_changed_commodity_count_is_not_computed_and_says_where(self):
        economies = [small_economy(), small_economy(), four_commodity_economy()]
        plans = [
            small_plan(),
            small_plan(),
            Plan(
                output=np.array([1.0]),
                input_use=np.array([1.0]),
                consumption=None,
                consumption_commodity=None,
                shared_use=None,
            ),
        ]
        report = period_differences(economies, plans, resources=np.array([2], dtype=np.int64))
        assert report.cumulative_use is None
        assert report.initial_endowment is None
        assert report.resource_difference is None
        assert report.why_resources_not_computed == (
            "the number of commodities changed from 3 in period 0 to 4 in period 2, so the same "
            "index does not name the same commodity across periods"
        )

    def test_consumer_units_and_their_change(self):
        economies = [small_economy(n_consumers=n) for n in (2, 5, 1)]
        plans = [
            small_plan(consumption=np.zeros((n, 2))) for n in (2, 5, 1)
        ]
        report = period_differences(economies, plans)
        np.testing.assert_array_equal(report.consumer_units, [2, 5, 1])
        np.testing.assert_array_equal(report.consumer_unit_change, [3, -4])
        assert report.consumer_units.dtype == np.int64
        assert report.consumer_unit_change.dtype == np.int64

    def test_one_period_has_an_empty_change(self):
        report = period_differences([small_economy()], [small_plan()])
        np.testing.assert_array_equal(report.consumer_units, [2])
        assert report.consumer_unit_change.shape == (0,)
        assert report.consumer_unit_change.dtype == np.int64

    def test_the_arrays_are_read_only(self):
        report = period_differences(
            [small_economy()], [small_plan()], resources=np.array([2], dtype=np.int64)
        )
        for name in (
            "initial_endowment", "cumulative_use", "resource_difference",
            "consumer_units", "consumer_unit_change",
        ):
            assert not getattr(report, name).flags.writeable

    @pytest.mark.parametrize("economies, plans", [([], []), ([small_economy()], [])])
    def test_unequal_or_empty_trajectories_are_a_value_error(self, economies, plans):
        with pytest.raises(ValueError):
            period_differences(economies, plans)

    def test_out_of_range_resources_are_a_value_error(self):
        with pytest.raises(ValueError, match=r"resources.*\b7\b"):
            period_differences(
                [small_economy()], [small_plan()], resources=np.array([7], dtype=np.int64)
            )


class TestCoverage:
    def test_four_rows_in_order_with_their_reasons(self):
        report = period_differences([small_economy()], [small_plan()])
        assert report.coverage == (
            Coverage(CUMULATIVE_RESOURCE_USE, False, NO_RESOURCES_REASON, False),
            Coverage(CONSUMER_UNIT_COUNT, True, None, False),
            Coverage(CAPITAL_STOCK_NON_NEGATIVITY, False, NO_CAPITAL_STOCK_REASON, False),
            Coverage(STOCK_FLOW_IDENTITY, False, NO_STOCK_FLOW_REASON, False),
        )

    def test_the_resource_row_is_computed_when_resources_are_declared(self):
        report = period_differences(
            [small_economy()], [small_plan()], resources=np.array([2], dtype=np.int64)
        )
        assert report.coverage[0] == Coverage(CUMULATIVE_RESOURCE_USE, True, None, False)

    def test_the_constraint_declarations_are_echoed(self):
        report = period_differences(
            [small_economy()],
            [small_plan()],
            constraints=(STOCK_FLOW_IDENTITY, CUMULATIVE_RESOURCE_USE),
        )
        assert [row.declared_constraint for row in report.coverage] == [True, False, False, True]
        assert [row.computed for row in report.coverage] == [False, True, False, False]

    def test_the_constants_are_their_names(self):
        assert CUMULATIVE_RESOURCE_USE == "cumulative_resource_use"
        assert CONSUMER_UNIT_COUNT == "consumer_unit_count"
        assert CAPITAL_STOCK_NON_NEGATIVITY == "capital_stock_non_negativity"
        assert STOCK_FLOW_IDENTITY == "stock_flow_identity"

    def test_an_unknown_constraint_is_a_value_error_listing_the_four(self):
        with pytest.raises(ValueError) as caught:
            period_differences([small_economy()], [small_plan()], constraints=("budget",))
        message = str(caught.value)
        assert "budget" in message
        for name in (
            CUMULATIVE_RESOURCE_USE, CONSUMER_UNIT_COUNT,
            CAPITAL_STOCK_NON_NEGATIVITY, STOCK_FLOW_IDENTITY,
        ):
            assert name in message


# --------------------------------------------------------------------------- run_periods


class RecordingAdvance:
    """Adds one consumer unit every period and records nothing else."""

    def __call__(self, economy, plan, seed):
        return small_economy(n_consumers=economy.n_consumers + 1, period=economy.period + 1)


class ConsumersProcedure:
    """Returns :func:`small_plan` sized for however many consumer units the economy has."""

    def solve(self, economy, seed):
        return priced_plan(
            consumption=np.ones((economy.n_consumers, 2)),
            valuation={
                INCOME: np.full(economy.n_consumers, 10.0),
                EXPENDITURE: np.full(economy.n_consumers, 4.0),
                INDICATIVE_PRICE: np.array([-1.0, -2.0, 3.0]),
            },
        )


class TestRunPeriods:
    def test_each_period_carries_its_report_and_the_run_its_period_report(self):
        result = run_periods(
            small_economy(), ConsumersProcedure(), 3, seed=1, advance=RecordingAdvance(),
            bads=np.array([1], dtype=np.int64), price=INDICATIVE_PRICE,
            resources=np.array([2], dtype=np.int64),
            constraints=(CUMULATIVE_RESOURCE_USE,),
        )
        assert isinstance(result.differences, PeriodDifferences)
        for period in result.periods:
            budget = period.result.differences.budget
            np.testing.assert_array_equal(
                budget.difference, np.full(period.economy.n_consumers, 6.0)
            )
            assert period.result.differences.non_negativity.minimum[
                f"valuation.{INDICATIVE_PRICE}"
            ] == -1.0
        np.testing.assert_array_equal(result.differences.consumer_units, [2, 3, 4])
        np.testing.assert_array_equal(
            result.differences.cumulative_use, [[6.0], [12.0], [18.0]]
        )
        assert result.differences.coverage[0].declared_constraint is True

    def test_differences_false_turns_off_both(self):
        result = run_periods(
            small_economy(), ConsumersProcedure(), 2, seed=1, differences=False,
        )
        assert result.differences is None
        assert all(period.result.differences is None for period in result.periods)

    def test_without_resources_the_period_report_says_why(self):
        result = run_periods(small_economy(), ConsumersProcedure(), 2, seed=1)
        assert result.differences.why_resources_not_computed == NO_RESOURCES_REASON

    def test_an_unknown_constraint_raises_from_run_periods(self):
        with pytest.raises(ValueError, match="stock_flow"):
            run_periods(
                small_economy(), ConsumersProcedure(), 1, seed=1, constraints=("nonsense",)
            )

    def test_periods_result_defaults_differences_to_none(self):
        assert PeriodsResult(periods=()).differences is None


class CountingProcedure:
    """:func:`small_plan` every period, counting the periods that ran."""

    def __init__(self):
        self.solves = 0

    def solve(self, economy, seed):
        self.solves += 1
        return small_plan()


@pytest.mark.parametrize("differences", [True, False])
class TestRunPeriodsChecksItsDeclarationsFirst:
    """A declaration that would be refused after the last period is refused before the first."""

    @pytest.mark.parametrize(
        "resources, match",
        [
            (np.array([7], dtype=np.int64), r"resources.*\b7\b"),
            (np.array([2, 2], dtype=np.int64), r"resources.*\b2\b"),
            (np.array([2.0]), "resources"),
        ],
    )
    def test_malformed_resources_are_refused_before_any_period_runs(
        self, differences, resources, match
    ):
        procedure = CountingProcedure()
        with pytest.raises(ValueError, match=match):
            run_periods(
                small_economy(), procedure, 3, seed=1, resources=resources,
                differences=differences,
            )
        assert procedure.solves == 0

    def test_an_unknown_constraint_is_refused_before_any_period_runs(self, differences):
        procedure = CountingProcedure()
        with pytest.raises(ValueError, match="nonsense"):
            run_periods(
                small_economy(), procedure, 3, seed=1, constraints=("nonsense",),
                differences=differences,
            )
        assert procedure.solves == 0

    def test_well_formed_declarations_let_every_period_run(self, differences):
        procedure = CountingProcedure()
        result = run_periods(
            small_economy(), procedure, 3, seed=1, resources=np.array([2], dtype=np.int64),
            constraints=(CUMULATIVE_RESOURCE_USE,), differences=differences,
        )
        assert procedure.solves == 3
        assert (result.differences is None) is (not differences)
