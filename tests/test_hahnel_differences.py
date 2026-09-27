"""The difference report on Hahnel plans, the two valuation keys the prefab files, and its helpers.

Expected values are rebuilt from the economy's own inputs by loops written here: the councils'
stated bundle from the utility exponents, the entitlements and the plan's price, and supply and
input use entry by entry. None comes from :func:`demplan.plan_differences` or from the arrays the
prefab computed them with.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from demplan import (
    CONSUMER_DEMAND,
    EXPENDITURE,
    INCOME,
    INDICATIVE_PRICE,
    MaximizeWeightedConsumption,
    ReferenceProcedure,
    check_homogeneity,
    plan_differences,
    run,
)
from demplan.prefabs import hahnel
from demplan.prefabs.hahnel import HahnelBook2021, WarmStart
from demplan.tools.linearize import linearize
from reference import synthetic

PUBLIC = "public_good"
PRIVATE = "private_good"


def kinds_of(economy) -> np.ndarray:
    return np.asarray(economy.commodity_extra["hahnel_kind"])


def supply_by_loop(economy, plan) -> np.ndarray:
    """Endowment plus every output entry filed under its own commodity, one entry at a time."""
    supply = np.zeros(economy.n_commodities)
    for entry, commodity in enumerate(np.asarray(economy.output_commodity)):
        supply[commodity] += plan.output[entry]
    return supply + np.asarray(economy.endowment)


def input_use_by_loop(economy, plan) -> np.ndarray:
    used = np.zeros(economy.n_commodities)
    for entry, commodity in enumerate(np.asarray(economy.input_commodity)):
        used[commodity] += plan.input_use[entry]
    return used


def paid_prices(economy, price) -> np.ndarray:
    """The price each utility-exponent column is charged: listed, divided by the consumer
    units on a public good."""
    columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
    kinds = kinds_of(economy)
    paid = np.empty(columns.size)
    for column, commodity in enumerate(columns):
        listed = price[commodity]
        paid[column] = listed / economy.n_consumers if kinds[commodity] == PUBLIC else listed
    return paid


def stated_bundle_by_loop(economy, price) -> np.ndarray:
    """Each council's Cobb-Douglas demand for each column, one entry at a time."""
    entitlement = np.asarray(economy.consumer_extra["entitlement"])
    exponent = np.asarray(economy.consumer_extra["utility_exponent"])
    paid = paid_prices(economy, price)
    bundle = np.empty(exponent.shape)
    for unit in range(exponent.shape[0]):
        total = sum(exponent[unit])
        for column in range(exponent.shape[1]):
            bundle[unit, column] = entitlement[unit] * exponent[unit, column] / (
                total * paid[column]
            )
    return bundle


def expenditure_by_loop(economy, price) -> np.ndarray:
    bundle = stated_bundle_by_loop(economy, price)
    paid = paid_prices(economy, price)
    return np.array(
        [sum(bundle[unit, column] * paid[column] for column in range(paid.size))
         for unit in range(bundle.shape[0])]
    )


def converged_plan(economy):
    return run(HahnelBook2021(), economy, seed=0).plan


# --------------------------------------------------------------------------- synthetic


@pytest.fixture(scope="module")
def synthetic_run():
    economy = synthetic.build_economy()
    return economy, converged_plan(economy)


class TestTheBudgetKeys:
    def test_income_is_the_entitlement_each_council_used(self, synthetic_run):
        economy, plan = synthetic_run
        income = plan.valuation[INCOME]
        assert income.dtype == np.float64
        np.testing.assert_array_equal(income, economy.consumer_extra["entitlement"])

    def test_expenditure_is_the_cost_of_the_whole_stated_bundle_at_the_prices_paid(
        self, synthetic_run
    ):
        economy, plan = synthetic_run
        expected = expenditure_by_loop(economy, np.asarray(plan.valuation[INDICATIVE_PRICE]))
        expenditure = plan.valuation[EXPENDITURE]
        assert expenditure.shape == (economy.n_consumers,)
        np.testing.assert_allclose(expenditure, expected, rtol=1e-13, atol=0)

    def test_a_council_spends_its_whole_entitlement(self, synthetic_run):
        economy, plan = synthetic_run
        np.testing.assert_allclose(
            plan.valuation[EXPENDITURE], economy.consumer_extra["entitlement"], rtol=1e-13
        )

    def test_uneven_entitlements_reach_income_and_expenditure_per_council(self):
        economy = synthetic.build_economy_with_unordered_private_columns()
        plan = converged_plan(economy)
        np.testing.assert_array_equal(plan.valuation[INCOME], synthetic.UNEVEN_ENTITLEMENT)
        expected = expenditure_by_loop(economy, np.asarray(plan.valuation[INDICATIVE_PRICE]))
        np.testing.assert_allclose(plan.valuation[EXPENDITURE], expected, rtol=1e-13, atol=0)

    def test_every_round_of_the_trajectory_carries_both_keys(self):
        economy = synthetic.build_economy()
        result = run(HahnelBook2021(record_trajectory=True, max_rounds=3), economy, seed=0)
        for plan in result.summary.trajectory:
            assert INCOME in plan.valuation
            assert EXPENDITURE in plan.valuation


class TestTheReportOnAHahnelPlan:
    def test_the_difference_is_supply_minus_input_use_and_consumer_demand(self, synthetic_run):
        economy, plan = synthetic_run
        balance = plan_differences(economy, plan).material_balance
        expected = supply_by_loop(economy, plan) - (
            input_use_by_loop(economy, plan) + np.asarray(plan.extra[CONSUMER_DEMAND])
        )
        goods = np.isin(kinds_of(economy), [PRIVATE, PUBLIC])
        assert goods.sum() == 6
        np.testing.assert_array_equal(balance.difference[goods], expected[goods])

    def test_the_budget_difference_matches_entitlement_minus_the_cost_of_the_bundle(
        self, synthetic_run
    ):
        economy, plan = synthetic_run
        budget = plan_differences(economy, plan, price=INDICATIVE_PRICE).budget
        entitlement = np.asarray(economy.consumer_extra["entitlement"])
        expected = entitlement - expenditure_by_loop(
            economy, np.asarray(plan.valuation[INDICATIVE_PRICE])
        )
        assert budget.why_not_computed is None
        np.testing.assert_allclose(
            budget.difference, expected, rtol=0, atol=1e-9 * entitlement.max()
        )

    def test_priced_consumption_is_what_a_council_spends_on_non_shared_columns(
        self, synthetic_run
    ):
        economy, plan = synthetic_run
        price = np.asarray(plan.valuation[INDICATIVE_PRICE])
        bundle = stated_bundle_by_loop(economy, price)
        paid = paid_prices(economy, price)
        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        not_public = kinds_of(economy)[columns] != PUBLIC
        expected = (bundle[:, not_public] * paid[not_public]).sum(axis=1)
        budget = plan_differences(economy, plan, price=INDICATIVE_PRICE).budget
        np.testing.assert_allclose(budget.priced_consumption, expected, rtol=1e-13, atol=0)

    def test_the_reference_plan_has_no_material_shortfall(self, synthetic_run):
        economy, plan = synthetic_run
        linearised = linearize(economy, plan)
        consumable = np.isin(kinds_of(economy), [PRIVATE, PUBLIC])
        weights = np.where(consumable, plan.valuation[INDICATIVE_PRICE], 0.0)
        reference = run(
            ReferenceProcedure(
                MaximizeWeightedConsumption(weights, shared=hahnel.shared_goods(economy))
            ),
            linearised,
            seed=0,
        ).plan
        balance = plan_differences(linearised, reference).material_balance
        supply = supply_by_loop(linearised, reference)
        assert np.all(balance.difference >= -1e-9 * np.maximum(1.0, supply))


@pytest.fixture(scope="module")
def third_kind_run():
    economy = synthetic.build_economy_with_a_third_kind_column()
    return economy, converged_plan(economy)


class TestColumnsOfTheThirdKind:
    def test_the_column_lands_in_consumption(self, third_kind_run):
        economy, plan = third_kind_run
        columns = np.asarray(plan.consumption_commodity)
        assert synthetic.THIRD_KIND_COMMODITY in columns.tolist()
        exponent_columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        not_public = kinds_of(economy)[exponent_columns] != PUBLIC
        np.testing.assert_array_equal(columns, exponent_columns[not_public])

    def test_the_block_is_the_stated_bundle_of_every_non_public_column(self, third_kind_run):
        economy, plan = third_kind_run
        bundle = stated_bundle_by_loop(economy, np.asarray(plan.valuation[INDICATIVE_PRICE]))
        exponent_columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        not_public = kinds_of(economy)[exponent_columns] != PUBLIC
        np.testing.assert_allclose(plan.consumption, bundle[:, not_public], rtol=1e-13, atol=0)

    def test_the_material_balance_sees_it(self, third_kind_run):
        economy, plan = third_kind_run
        balance = plan_differences(economy, plan).material_balance
        expected = supply_by_loop(economy, plan) - (
            input_use_by_loop(economy, plan) + np.asarray(plan.extra[CONSUMER_DEMAND])
        )
        commodity = synthetic.THIRD_KIND_COMMODITY
        assert np.asarray(plan.extra[CONSUMER_DEMAND])[commodity] > 0.0
        assert balance.difference[commodity] == expected[commodity]
        goods = np.isin(kinds_of(economy), [PRIVATE, PUBLIC])
        np.testing.assert_array_equal(balance.difference[goods], expected[goods])

    def test_expenditure_covers_the_third_kind_column(self, third_kind_run):
        economy, plan = third_kind_run
        expected = expenditure_by_loop(economy, np.asarray(plan.valuation[INDICATIVE_PRICE]))
        np.testing.assert_allclose(plan.valuation[EXPENDITURE], expected, rtol=1e-13, atol=0)


# --------------------------------------------------------------------------- helpers


class TestDeclarationHelpers:
    def test_resources_are_the_natural_resources_and_labour_sorted(self):
        economy = synthetic.build_permuted_economy()
        kinds = kinds_of(economy)
        expected = np.array(
            [c for c in range(economy.n_commodities) if kinds[c] in ("natural_resource", "labor")],
            dtype=np.int64,
        )
        resources = hahnel.resources(economy)
        assert resources.dtype == np.int64
        np.testing.assert_array_equal(resources, expected)
        assert resources.size == 6

    def test_bads_are_empty(self):
        bads = hahnel.bads(synthetic.build_economy())
        assert bads.dtype == np.int64
        assert bads.shape == (0,)


class TestScaleStartingPrice:
    def test_the_scalar_price_is_multiplied_and_the_economy_returned_as_is(self):
        economy = synthetic.build_economy()
        procedure = HahnelBook2021(threshold_pct=3.0, initial_price=700.0)
        scaled, same = hahnel.scale_starting_price(procedure, economy, 2.5)
        assert same is economy
        assert scaled.initial_price == 1750.0
        assert scaled.threshold_pct == 3.0
        assert procedure.initial_price == 700.0

    def test_a_price_vector_is_multiplied_entry_by_entry(self):
        economy = synthetic.build_economy()
        vector = np.linspace(1.0, 15.0, economy.n_commodities)
        scaled, _ = hahnel.scale_starting_price(
            HahnelBook2021(initial_price=vector), economy, 2.0
        )
        np.testing.assert_array_equal(scaled.initial_price, vector * 2.0)
        np.testing.assert_array_equal(vector, np.linspace(1.0, 15.0, economy.n_commodities))

    def test_another_procedure_is_a_type_error_naming_it(self):
        with pytest.raises(TypeError, match="WarmStart"):
            hahnel.scale_starting_price(WarmStart(), synthetic.build_economy(), 2.0)


class TestScaleNominalQuantities:
    def test_price_and_entitlement_are_multiplied_and_nothing_else(self):
        economy = synthetic.build_economy_with_unordered_private_columns()
        procedure = HahnelBook2021(initial_price=700.0)
        scaled_procedure, scaled = hahnel.scale_nominal_quantities(procedure, economy, 3.0)
        assert scaled_procedure.initial_price == 2100.0
        np.testing.assert_array_equal(
            scaled.consumer_extra["entitlement"], np.array(synthetic.UNEVEN_ENTITLEMENT) * 3.0
        )
        np.testing.assert_array_equal(
            economy.consumer_extra["entitlement"], synthetic.UNEVEN_ENTITLEMENT
        )
        for key in ("utility_exponent", "utility_exponent_commodity"):
            np.testing.assert_array_equal(scaled.consumer_extra[key], economy.consumer_extra[key])
        assert scaled.period == economy.period
        for field in dataclasses.fields(economy):
            if field.name in ("period", "consumer_extra"):
                continue
            left, right = getattr(scaled, field.name), getattr(economy, field.name)
            if isinstance(left, np.ndarray):
                np.testing.assert_array_equal(left, right, err_msg=field.name)
            else:
                assert set(left) == set(right), field.name
                for key in left:
                    np.testing.assert_array_equal(left[key], right[key], err_msg=key)

    def test_another_procedure_is_a_type_error_naming_it(self):
        with pytest.raises(TypeError, match="ReferenceProcedure"):
            hahnel.scale_nominal_quantities(
                ReferenceProcedure(None), synthetic.build_economy(), 2.0
            )

    def test_the_scaled_run_files_the_scaled_entitlement_as_income(self):
        economy = synthetic.build_economy()
        procedure, scaled = hahnel.scale_nominal_quantities(HahnelBook2021(), economy, 2.0)
        plan = converged_plan(scaled)
        np.testing.assert_array_equal(
            plan.valuation[INCOME], np.full(economy.n_consumers, 2.0 * synthetic.ENTITLEMENT)
        )

    def test_check_homogeneity_runs_with_either_helper(self):
        economy = synthetic.build_economy()
        for rescale in (hahnel.scale_starting_price, hahnel.scale_nominal_quantities):
            report = check_homogeneity(HahnelBook2021(), economy, 0, rescale, 2.0)
            assert report.rescale == rescale.__qualname__
            assert isinstance(report.rounds, int)
            assert isinstance(report.rounds_rescaled, int)


# --------------------------------------------------------------------------- dep1ex01


@pytest.fixture(scope="module")
def dep1ex01_run(dep1ex01_economy):
    economy = dep1ex01_economy
    return economy, converged_plan(economy)


@pytest.mark.slow
class TestOnDep1ex01:
    def test_the_difference_is_supply_minus_input_use_and_consumer_demand(self, dep1ex01_run):
        economy, plan = dep1ex01_run
        supply = np.asarray(economy.endowment).copy()
        np.add.at(supply, np.asarray(economy.output_commodity), np.asarray(plan.output))
        used = np.zeros(economy.n_commodities)
        np.add.at(used, np.asarray(economy.input_commodity), np.asarray(plan.input_use))
        expected = supply - (used + np.asarray(plan.extra[CONSUMER_DEMAND]))
        goods = np.isin(kinds_of(economy), [PRIVATE, PUBLIC])
        balance = plan_differences(economy, plan).material_balance
        np.testing.assert_array_equal(balance.difference[goods], expected[goods])

    def test_the_budget_difference_matches_an_independent_computation(self, dep1ex01_run):
        economy, plan = dep1ex01_run
        price = np.asarray(plan.valuation[INDICATIVE_PRICE])
        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        public = kinds_of(economy)[columns] == PUBLIC
        paid = np.where(public, price[columns] / economy.n_consumers, price[columns])
        exponent = np.asarray(economy.consumer_extra["utility_exponent"])
        entitlement = np.asarray(economy.consumer_extra["entitlement"])
        share = exponent / exponent.sum(axis=1, keepdims=True)
        bundle = entitlement[:, None] * share / paid[None, :]
        expected = entitlement - (bundle * paid[None, :]).sum(axis=1)
        budget = plan_differences(economy, plan, price=INDICATIVE_PRICE).budget
        np.testing.assert_array_equal(budget.income, entitlement)
        np.testing.assert_allclose(
            budget.difference, expected, rtol=0, atol=1e-9 * entitlement.max()
        )

    def test_the_reference_plan_has_no_material_shortfall(self, dep1ex01_run):
        economy, plan = dep1ex01_run
        linearised = linearize(economy, plan)
        consumable = np.isin(kinds_of(economy), [PRIVATE, PUBLIC])
        weights = np.where(consumable, plan.valuation[INDICATIVE_PRICE], 0.0)
        reference = run(
            ReferenceProcedure(
                MaximizeWeightedConsumption(weights, shared=hahnel.shared_goods(economy))
            ),
            linearised,
            seed=0,
        ).plan
        balance = plan_differences(linearised, reference).material_balance
        supply = np.asarray(linearised.endowment).copy()
        np.add.at(supply, np.asarray(linearised.output_commodity), np.asarray(reference.output))
        assert np.all(balance.difference >= -1e-9 * np.maximum(1.0, supply))
