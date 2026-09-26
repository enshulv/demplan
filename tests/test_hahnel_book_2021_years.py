"""The two-year experiment of Hahnel (2021), ch. 9, on top of the multi-period driver.

The program behind the book's tables, ``msszczep/pequod-cljs``, ``src/clj/pequod_cljs/
csvgen.clj`` at commit ``71e44d3``, runs a first year to 3 percent, perturbs the councils'
exponents (``augmented-reset``), and runs a second year from the prices and the multiplier the
first year ended with. The pieces tested here are the library's form of that: an evolution law
that perturbs the exponents, a next-procedure slot that starts year two where year one ended,
the ``create-toothaches`` change behind Table 9.6, the real GDP growth the book reports, and
the relative imbalance rebuilt from a plan.

Every expected value comes from the statement of the rule: random draws are recomputed from an
independent ``numpy.random.default_rng``, sums and ratios are worked out by hand.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from demplan import (
    CONSUMER_DEMAND,
    INDICATIVE_PRICE,
    Advance,
    CommodityKind,
    Economy,
    NextProcedure,
    StatedPlan,
    TechnologyKind,
    run,
    run_periods,
    split_seed,
)
from demplan.prefabs import hahnel
from demplan.prefabs.hahnel import (
    NEXT_INDICATIVE_PRICE,
    PRICE_RULE_STATE,
    HahnelBook2021,
    WarmStart,
    book_2021_rule,
    increasing_returns,
    perturb_exponents,
    real_gdp_growth,
    relative_imbalance,
)
from demplan.tools import unit_of_input
from reference import synthetic

INPUT_STEPS = (0.0, 0.001, 0.002, 0.003, 0.004)
"""``augment-wc``: what may be added to one worker-council exponent."""

UTILITY_STEPS = (-0.002, -0.001, 0.0, 0.001, 0.002)
"""``augment-cc``: what may be added to one consumer-council exponent."""

SEEDS = (0, 1, 7, 2**63 + 5)

PHYSICAL_FIELDS = ("output", "input_use", "consumption", "consumption_commodity", "provision")


def expected_draws(economy: Economy, seed: int) -> tuple[np.ndarray, np.ndarray]:
    """The two perturbations, drawn in the stated order from an independent generator."""
    generator = np.random.default_rng(seed)
    inputs = generator.choice(np.array(INPUT_STEPS), size=economy.n_inputs)
    utility = generator.choice(
        np.array(UTILITY_STEPS), size=economy.consumer_extra["utility_exponent"].shape
    )
    return inputs, utility


def with_utility_exponent(economy: Economy, exponent: np.ndarray) -> Economy:
    return dataclasses.replace(
        economy, consumer_extra={**economy.consumer_extra, "utility_exponent": exponent}
    )


def with_input_coefficient(economy: Economy, coefficient: np.ndarray) -> Economy:
    return dataclasses.replace(economy, input_coefficient=coefficient)


def assert_same_buffer(left: np.ndarray, right: np.ndarray, label: str) -> None:
    """``left`` holds ``right``'s numbers in ``right``'s memory: not a copy, not a new array."""
    assert np.shares_memory(left, right), label
    np.testing.assert_array_equal(left, right, err_msg=label)


class RecordingRule:
    """:data:`book_2021_rule`, keeping a copy of what every call was handed and returned."""

    def __init__(self):
        self.price = []
        self.imbalance = []
        self.state = []
        self.next_price = []
        self.next_state = []

    def initial_state(self, n_commodities):
        return book_2021_rule.initial_state(n_commodities)

    def __call__(self, price, surplus, imbalance, state):
        next_price, next_state = book_2021_rule(price, surplus, imbalance, state)
        self.price.append(np.array(price, copy=True))
        self.imbalance.append(np.array(imbalance, copy=True))
        self.state.append(np.array(state, copy=True))
        self.next_price.append(np.array(next_price, copy=True))
        self.next_state.append(np.array(next_state, copy=True))
        return next_price, next_state


# --------------------------------------------------------------------------- a tiny economy
#
# Five commodities, one of each kind that matters here, and four producing units, two of them
# producing the private good. Built by hand so that GDP and imbalance can be worked out on
# paper. The private good carries an endowment so that "supply of a good" (output only) and
# "supply in the material balance" (output plus endowment) give different numbers.

PRIVATE, PUBLIC, INTERMEDIATE, LABOR, NATURE = range(5)
TINY_KINDS = (
    CommodityKind.PRIVATE_GOOD,
    CommodityKind.PUBLIC_GOOD,
    CommodityKind.INTERMEDIATE,
    CommodityKind.LABOR,
    CommodityKind.NATURAL_RESOURCE,
)
TINY_ENDOWMENT = (7.0, 0.0, 0.0, 50.0, 0.0)
TINY_OUTPUT_COMMODITY = (PRIVATE, PUBLIC, INTERMEDIATE, PRIVATE)
TINY_INPUT_COMMODITY = (INTERMEDIATE, LABOR, INTERMEDIATE, LABOR, LABOR, LABOR)
TINY_INPUT_OFFSETS = (0, 2, 4, 5, 6)


def tiny_economy(kinds=TINY_KINDS) -> Economy:
    n_commodities = len(kinds)
    n_units = len(TINY_OUTPUT_COMMODITY)
    return Economy(
        period=0,
        commodity_id=np.arange(n_commodities, dtype=np.int64),
        commodity_kind=np.array([int(kind) for kind in kinds], dtype=np.int8),
        endowment=np.array(
            TINY_ENDOWMENT + (0.0,) * (n_commodities - len(TINY_ENDOWMENT)), dtype=np.float64
        ),
        unit_id=np.arange(n_units, dtype=np.int64),
        unit_group=np.zeros(n_units, dtype=np.int64),
        output_commodity=np.array(TINY_OUTPUT_COMMODITY, dtype=np.int64),
        technology_kind=np.full(n_units, TechnologyKind.COBB_DOUGLAS, dtype=np.int8),
        technology_scale=np.ones(n_units, dtype=np.float64),
        input_offsets=np.array(TINY_INPUT_OFFSETS, dtype=np.int64),
        input_commodity=np.array(TINY_INPUT_COMMODITY, dtype=np.int64),
        input_coefficient=np.full(len(TINY_INPUT_COMMODITY), 0.3, dtype=np.float64),
        consumer_id=np.arange(1, dtype=np.int64),
        consumer_group=np.zeros(1, dtype=np.int64),
    )


def tiny_plan(economy, output, next_price=None, indicative_price=None, input_use=None,
              consumer_demand=None) -> StatedPlan:
    valuation = {}
    if next_price is not None:
        valuation[NEXT_INDICATIVE_PRICE] = np.array(next_price, dtype=np.float64)
    if indicative_price is not None:
        valuation[INDICATIVE_PRICE] = np.array(indicative_price, dtype=np.float64)
    extra = {}
    if consumer_demand is not None:
        extra[CONSUMER_DEMAND] = np.array(consumer_demand, dtype=np.float64)
    if input_use is None:
        input_use = np.ones(economy.n_inputs)
    return StatedPlan(
        output=np.array(output, dtype=np.float64),
        input_use=np.array(input_use, dtype=np.float64),
        consumption=None,
        consumption_commodity=None,
        provision=None,
        valuation=valuation,
        extra=extra,
    )


# Year one: the private good totals 6 + 4 = 10, the public good 4, the intermediate 100.
# Year two: the private good totals 8 + 3 = 11, the public good 5, the intermediate 300.
YEAR_1_OUTPUT = (6.0, 4.0, 100.0, 4.0)
YEAR_2_OUTPUT = (8.0, 5.0, 300.0, 3.0)
YEAR_1_PRICE = (2.0, 5.0, 9.0, 1.0, 1.0)
YEAR_2_PRICE = (3.0, 4.0, 1.0, 1.0, 1.0)
DECOY_PRICE = (100.0, 1.0, 1.0, 1.0, 1.0)
"""Filed as ``indicative_price``: GDP is valued at the prices after the last update instead."""

TWO_GOOD_GROWTH = (100.0 * 7.0 / 40.0 + 100.0 * 7.0 / 46.0) / 2.0
"""Growth for the years above, worked out by hand.

At year one's prices (2, 5): 2*10 + 5*4 = 40 and 2*11 + 5*5 = 47, so 17.5 percent.
At year two's prices (3, 4): 3*10 + 4*4 = 46 and 3*11 + 4*5 = 53, so 700/46 percent.
The mean is 16.358695652173913.
"""


def two_years(economy=None, year_1_output=YEAR_1_OUTPUT, year_2_output=YEAR_2_OUTPUT,
              year_1_price=YEAR_1_PRICE, year_2_price=YEAR_2_PRICE):
    economy = tiny_economy() if economy is None else economy
    return (
        economy,
        tiny_plan(economy, year_1_output, year_1_price, DECOY_PRICE),
        economy,
        tiny_plan(economy, year_2_output, year_2_price, DECOY_PRICE),
    )


# --------------------------------------------------------------------------- perturb_exponents


class TestPerturbExponents:
    @pytest.mark.parametrize("seed", SEEDS)
    def test_input_draws_come_first_then_utility_draws(self, synthetic_economy, seed):
        inputs, utility = expected_draws(synthetic_economy, seed)
        perturbed = perturb_exponents(synthetic_economy, None, seed)
        np.testing.assert_array_equal(
            perturbed.input_coefficient, np.asarray(synthetic_economy.input_coefficient) + inputs
        )
        np.testing.assert_array_equal(
            perturbed.consumer_extra["utility_exponent"],
            np.asarray(synthetic_economy.consumer_extra["utility_exponent"]) + utility,
        )

    def test_every_step_is_one_of_the_stated_values_and_every_value_occurs(
        self, synthetic_economy
    ):
        seen_input, seen_utility = set(), set()
        base_input = np.asarray(synthetic_economy.input_coefficient)
        base_utility = np.asarray(synthetic_economy.consumer_extra["utility_exponent"])
        for seed in range(20):
            perturbed = perturb_exponents(synthetic_economy, None, seed)
            for step in np.round(perturbed.input_coefficient - base_input, 12).ravel():
                assert step in INPUT_STEPS
                seen_input.add(float(step))
            utility = perturbed.consumer_extra["utility_exponent"] - base_utility
            for step in np.round(utility, 12).ravel():
                assert step in UTILITY_STEPS
                seen_utility.add(float(step))
        assert seen_input == set(INPUT_STEPS)
        assert seen_utility == set(UTILITY_STEPS)

    def test_the_draws_are_independent_per_exponent(self, synthetic_economy):
        """Not one draw per unit or per consumer: a unit's inputs get different steps."""
        perturbed = perturb_exponents(synthetic_economy, None, 0)
        steps = np.asarray(perturbed.input_coefficient) - np.asarray(
            synthetic_economy.input_coefficient
        )
        owner = unit_of_input(synthetic_economy)
        assert any(np.unique(np.round(steps[owner == unit], 12)).size > 1 for unit in range(9))

    def test_the_period_moves_on_by_one(self, synthetic_economy):
        assert perturb_exponents(synthetic_economy, None, 0).period == 1
        later = dataclasses.replace(synthetic_economy, period=7)
        assert perturb_exponents(later, None, 0).period == 8

    def test_every_other_column_is_the_original_buffer(self, synthetic_economy):
        perturbed = perturb_exponents(synthetic_economy, None, 3)
        for field in dataclasses.fields(Economy):
            name = field.name
            if name in ("period", "input_coefficient", "consumer_extra"):
                continue
            value = getattr(synthetic_economy, name)
            if isinstance(value, np.ndarray):
                assert_same_buffer(getattr(perturbed, name), value, name)
            else:
                assert set(getattr(perturbed, name)) == set(value), name
                for key in value:
                    assert_same_buffer(getattr(perturbed, name)[key], value[key], f"{name}[{key}]")
        assert set(perturbed.consumer_extra) == set(synthetic_economy.consumer_extra)
        for key in ("entitlement", "utility_exponent_commodity"):
            assert_same_buffer(
                perturbed.consumer_extra[key], synthetic_economy.consumer_extra[key], key
            )

    def test_the_effort_exponent_is_untouched(self, synthetic_economy):
        perturbed = perturb_exponents(synthetic_economy, None, 11)
        np.testing.assert_array_equal(
            perturbed.unit_extra["effort_c"], np.array(synthetic.EFFORT_C)
        )

    def test_the_input_economy_is_left_as_it_was(self, synthetic_economy):
        before_input = np.array(synthetic_economy.input_coefficient, copy=True)
        before_utility = np.array(synthetic_economy.consumer_extra["utility_exponent"], copy=True)
        perturb_exponents(synthetic_economy, None, 5)
        np.testing.assert_array_equal(synthetic_economy.input_coefficient, before_input)
        np.testing.assert_array_equal(
            synthetic_economy.consumer_extra["utility_exponent"], before_utility
        )
        assert synthetic_economy.period == 0

    def test_the_plan_is_not_read(self, synthetic_economy):
        with_none = perturb_exponents(synthetic_economy, None, 9)
        with_object = perturb_exponents(synthetic_economy, object(), 9)
        np.testing.assert_array_equal(with_none.input_coefficient, with_object.input_coefficient)
        np.testing.assert_array_equal(
            with_none.consumer_extra["utility_exponent"],
            with_object.consumer_extra["utility_exponent"],
        )

    def test_it_is_an_evolution_law(self):
        assert isinstance(perturb_exponents, Advance)

    def test_a_utility_exponent_brought_to_zero_is_refused_with_its_count(
        self, synthetic_economy
    ):
        """0.002 plus a draw of -0.002 is exactly zero, and zero is refused."""
        flat = np.full(synthetic_economy.consumer_extra["utility_exponent"].shape, 0.002)
        economy = with_utility_exponent(synthetic_economy, flat)
        seed = 4
        _, utility = expected_draws(economy, seed)
        count = int(np.sum(utility == -0.002))
        assert count > 0
        with pytest.raises(ValueError, match="utility_exponent") as info:
            perturb_exponents(economy, None, seed)
        assert f" {count} " in f" {info.value} "
        assert "input_coefficient" not in str(info.value)

    def test_an_input_coefficient_left_at_or_below_zero_is_refused_with_its_count(
        self, synthetic_economy
    ):
        """No input step is negative, so a coefficient of -0.01 stays below zero whatever the draw."""
        coefficient = np.array(synthetic_economy.input_coefficient, copy=True)
        coefficient[[3, 17]] = -0.01
        economy = with_input_coefficient(synthetic_economy, coefficient)
        with pytest.raises(ValueError, match="input_coefficient") as info:
            perturb_exponents(economy, None, 0)
        assert " 2 " in f" {info.value} "
        assert "utility_exponent" not in str(info.value)

    def test_a_zero_input_coefficient_that_draws_zero_is_refused(self, synthetic_economy):
        coefficient = np.zeros(synthetic_economy.n_inputs)
        economy = with_input_coefficient(synthetic_economy, coefficient)
        seed = 0
        inputs, _ = expected_draws(economy, seed)
        count = int(np.sum(inputs == 0.0))
        assert 0 < count < economy.n_inputs
        with pytest.raises(ValueError, match="input_coefficient") as info:
            perturb_exponents(economy, None, seed)
        assert f" {count} " in f" {info.value} "

    def test_both_arrays_are_named_when_both_fail(self, synthetic_economy):
        coefficient = np.array(synthetic_economy.input_coefficient, copy=True)
        coefficient[5] = -1.0
        economy = with_input_coefficient(synthetic_economy, coefficient)
        economy = with_utility_exponent(
            economy, np.full(economy.consumer_extra["utility_exponent"].shape, -1.0)
        )
        with pytest.raises(ValueError) as info:
            perturb_exponents(economy, None, 0)
        message = f" {info.value} "
        assert "input_coefficient" in message and " 1 " in message
        assert "utility_exponent" in message
        assert f" {economy.consumer_extra['utility_exponent'].size} " in message

    def test_an_economy_without_utility_exponents_is_refused(self, synthetic_economy):
        bag = {k: v for k, v in synthetic_economy.consumer_extra.items()
               if k not in ("utility_exponent", "utility_exponent_commodity")}
        economy = dataclasses.replace(synthetic_economy, consumer_extra=bag)
        with pytest.raises(ValueError, match="utility_exponent"):
            perturb_exponents(economy, None, 0)

    def test_a_small_positive_result_is_accepted_unclipped(self, synthetic_economy):
        flat = np.full(synthetic_economy.consumer_extra["utility_exponent"].shape, 0.0021)
        economy = with_utility_exponent(synthetic_economy, flat)
        _, utility = expected_draws(economy, 4)
        perturbed = perturb_exponents(economy, None, 4)
        np.testing.assert_array_equal(perturbed.consumer_extra["utility_exponent"], flat + utility)
        assert np.min(perturbed.consumer_extra["utility_exponent"]) < 0.001


# --------------------------------------------------------------------------- WarmStart


def a_finished_plan(economy):
    return run(HahnelBook2021(threshold_pct=3.0), economy, seed=0).plan


class TestWarmStart:
    def test_the_fields_in_order_with_their_defaults(self):
        assert [(field.name, field.default) for field in dataclasses.fields(WarmStart)] == [
            ("threshold_pct", 3.0),
            ("max_rounds", 250),
            ("record_trajectory", False),
            ("price_rule", None),
        ]

    def test_it_is_frozen(self):
        with pytest.raises(dataclasses.FrozenInstanceError):
            WarmStart().threshold_pct = 5.0

    def test_it_is_a_next_procedure(self):
        assert isinstance(WarmStart(), NextProcedure)

    def test_it_hands_on_the_previous_plans_own_arrays(self, synthetic_economy):
        plan = a_finished_plan(synthetic_economy)
        built = WarmStart()(plan)
        assert type(built) is HahnelBook2021
        assert built.initial_price is plan.valuation[NEXT_INDICATIVE_PRICE]
        assert built.initial_rule_state is plan.extra[PRICE_RULE_STATE]

    def test_it_forwards_its_own_fields(self, synthetic_economy):
        plan = a_finished_plan(synthetic_economy)
        rule = RecordingRule()
        built = WarmStart(threshold_pct=4.5, max_rounds=17, record_trajectory=True,
                          price_rule=rule)(plan)
        assert built.threshold_pct == 4.5
        assert built.max_rounds == 17
        assert built.record_trajectory is True
        assert built.price_rule is rule

    def test_the_defaults_reach_the_procedure(self, synthetic_economy):
        built = WarmStart()(a_finished_plan(synthetic_economy))
        assert built.threshold_pct == 3.0
        assert built.max_rounds == 250
        assert built.record_trajectory is False
        assert built.price_rule is None

    @pytest.mark.parametrize("missing", ["valuation", "extra"])
    def test_a_plan_without_the_keys_is_refused(self, synthetic_economy, missing):
        plan = a_finished_plan(synthetic_economy)
        if missing == "valuation":
            plan = dataclasses.replace(
                plan, valuation={INDICATIVE_PRICE: plan.valuation[INDICATIVE_PRICE]}
            )
        else:
            plan = dataclasses.replace(
                plan, extra={k: v for k, v in plan.extra.items() if k != PRICE_RULE_STATE}
            )
        with pytest.raises(ValueError, match="HahnelBook2021"):
            WarmStart()(plan)

    def test_a_plan_from_another_procedure_is_refused(self):
        economy = tiny_economy()
        with pytest.raises(ValueError, match="HahnelBook2021"):
            WarmStart()(tiny_plan(economy, YEAR_1_OUTPUT))


# --------------------------------------------------------------------------- two years


def two_year_run(economy, seed, rule=None, threshold_pct=3.0):
    return run_periods(
        economy,
        HahnelBook2021(threshold_pct=threshold_pct, price_rule=rule),
        periods=2,
        seed=seed,
        advance=perturb_exponents,
        next_procedure=WarmStart(threshold_pct=threshold_pct, record_trajectory=True,
                                 price_rule=rule),
    )


def assert_the_same_plan(left, right, label):
    for name in PHYSICAL_FIELDS:
        a, b = getattr(left, name), getattr(right, name)
        assert (a is None) == (b is None), f"{label}: {name}"
        if a is not None:
            np.testing.assert_array_equal(a, b, err_msg=f"{label}: {name}")
    assert set(left.valuation) == set(right.valuation), label
    for key in left.valuation:
        np.testing.assert_array_equal(left.valuation[key], right.valuation[key], err_msg=key)
    assert set(left.extra) == set(right.extra), label
    for key in left.extra:
        np.testing.assert_array_equal(left.extra[key], right.extra[key], err_msg=key)


class TestTwoYears:
    SEED = 20260926

    def test_year_two_starts_where_year_one_ended(self, synthetic_economy):
        rule = RecordingRule()
        result = two_year_run(synthetic_economy, self.SEED, rule)
        first, second = result.periods
        year_1_rounds = first.result.summary.rounds
        assert first.result.summary.converged is True
        assert second.result.summary.converged is True
        assert len(rule.price) == year_1_rounds + second.result.summary.rounds

        np.testing.assert_array_equal(
            rule.price[year_1_rounds], first.result.plan.valuation[NEXT_INDICATIVE_PRICE]
        )
        np.testing.assert_array_equal(
            rule.state[year_1_rounds], first.result.plan.extra[PRICE_RULE_STATE]
        )
        np.testing.assert_array_equal(
            first.result.plan.valuation[NEXT_INDICATIVE_PRICE], rule.next_price[year_1_rounds - 1]
        )
        assert not np.array_equal(rule.state[year_1_rounds], rule.state[0])

    def test_year_two_solves_the_perturbed_economy(self, synthetic_economy):
        result = two_year_run(synthetic_economy, self.SEED)
        _, advance_seed, _, _ = split_seed(self.SEED, 4)
        second = result.periods[1]
        expected = perturb_exponents(synthetic_economy, None, advance_seed)
        np.testing.assert_array_equal(second.economy.input_coefficient, expected.input_coefficient)
        np.testing.assert_array_equal(
            second.economy.consumer_extra["utility_exponent"],
            expected.consumer_extra["utility_exponent"],
        )
        assert second.economy.period == 1

    def test_the_same_as_building_year_two_by_hand(self, synthetic_economy):
        _, advance_seed, _, _ = split_seed(self.SEED, 4)
        year_1 = run(HahnelBook2021(threshold_pct=3.0), synthetic_economy, seed=0)
        economy_2 = perturb_exponents(synthetic_economy, year_1.plan, advance_seed)
        year_2 = run(
            HahnelBook2021(
                threshold_pct=3.0,
                initial_price=np.array(year_1.plan.valuation[NEXT_INDICATIVE_PRICE]),
                initial_rule_state=np.array(year_1.plan.extra[PRICE_RULE_STATE]),
                record_trajectory=True,
            ),
            economy_2,
            seed=0,
        )

        result = two_year_run(synthetic_economy, self.SEED)
        first, second = result.periods
        assert first.result.summary.rounds == year_1.summary.rounds
        assert second.result.summary.rounds == year_2.summary.rounds
        assert_the_same_plan(first.result.plan, year_1.plan, "year 1")
        assert_the_same_plan(second.result.plan, year_2.plan, "year 2")
        assert len(second.result.summary.trajectory) == year_2.summary.rounds

    def test_a_warm_start_is_not_a_cold_start(self, synthetic_economy):
        """Year two from 700 and the rule's own state runs another course than the warm one."""
        result = two_year_run(synthetic_economy, self.SEED)
        second = result.periods[1]
        cold = run(
            HahnelBook2021(threshold_pct=3.0, record_trajectory=True), second.economy, seed=0
        )
        assert not np.array_equal(
            cold.summary.trajectory[0].valuation[INDICATIVE_PRICE],
            second.result.summary.trajectory[0].valuation[INDICATIVE_PRICE],
        )

    def test_the_same_seed_twice_is_bit_identical(self, synthetic_economy):
        first = two_year_run(synthetic_economy, self.SEED)
        again = two_year_run(synthetic_economy, self.SEED)
        for a, b in zip(first.periods, again.periods):
            assert a.result.summary.rounds == b.result.summary.rounds
            assert_the_same_plan(a.result.plan, b.result.plan, f"period {a.index}")
            np.testing.assert_array_equal(a.economy.input_coefficient, b.economy.input_coefficient)
            np.testing.assert_array_equal(
                a.economy.consumer_extra["utility_exponent"],
                b.economy.consumer_extra["utility_exponent"],
            )

    def test_another_seed_perturbs_differently(self, synthetic_economy):
        first = two_year_run(synthetic_economy, self.SEED)
        other = two_year_run(synthetic_economy, self.SEED + 1)
        assert not np.array_equal(
            first.periods[1].economy.input_coefficient, other.periods[1].economy.input_coefficient
        )


# --------------------------------------------------------------------------- increasing returns


def changed_units(economy, returned) -> set[int]:
    owner = unit_of_input(economy)
    moved = np.asarray(returned.input_coefficient) != np.asarray(economy.input_coefficient)
    return {int(unit) for unit in np.unique(owner[moved])}


class TestIncreasingReturns:
    @pytest.mark.parametrize(
        "share, count", [(0.2, 2), (0.5, 5), (1 / 3, 3), (0.0, 0), (1.0, 9), (0.01, 1)]
    )
    def test_the_count_is_the_ceiling_of_the_share(self, synthetic_economy, share, count):
        returned = increasing_returns(synthetic_economy, seed=3, share=share)
        assert len(changed_units(synthetic_economy, returned)) == count

    @pytest.mark.parametrize("seed", SEEDS)
    def test_the_units_are_the_first_of_a_seeded_permutation(self, synthetic_economy, seed):
        returned = increasing_returns(synthetic_economy, seed=seed)
        expected = np.random.default_rng(seed).permutation(synthetic_economy.n_units)[:2]
        assert changed_units(synthetic_economy, returned) == {int(unit) for unit in expected}

    def test_every_input_of_a_chosen_unit_gains_the_increment_and_nothing_else_moves(
        self, synthetic_economy
    ):
        seed = 12
        chosen = np.random.default_rng(seed).permutation(synthetic_economy.n_units)[:5]
        returned = increasing_returns(synthetic_economy, seed=seed, share=0.5, increment=0.25)
        owner = unit_of_input(synthetic_economy)
        base = np.asarray(synthetic_economy.input_coefficient)
        expected = np.where(np.isin(owner, chosen), base + 0.25, base)
        np.testing.assert_array_equal(returned.input_coefficient, expected)

    def test_the_default_increment_is_a_tenth(self, synthetic_economy):
        returned = increasing_returns(synthetic_economy, seed=1)
        moved = np.asarray(returned.input_coefficient) - np.asarray(
            synthetic_economy.input_coefficient
        )
        np.testing.assert_allclose(moved[moved != 0], 0.1, rtol=1e-12)

    def test_everything_else_is_untouched(self, synthetic_economy):
        returned = increasing_returns(synthetic_economy, seed=1)
        assert returned.period == synthetic_economy.period
        for field in dataclasses.fields(Economy):
            name = field.name
            if name in ("period", "input_coefficient"):
                continue
            value = getattr(synthetic_economy, name)
            if isinstance(value, np.ndarray):
                assert_same_buffer(getattr(returned, name), value, name)
            else:
                for key in value:
                    assert_same_buffer(getattr(returned, name)[key], value[key], f"{name}[{key}]")

    def test_the_input_economy_is_left_as_it_was(self, synthetic_economy):
        before = np.array(synthetic_economy.input_coefficient, copy=True)
        increasing_returns(synthetic_economy, seed=1, share=1.0)
        np.testing.assert_array_equal(synthetic_economy.input_coefficient, before)

    @pytest.mark.parametrize("share", [-0.01, 1.01, float("nan"), float("inf")])
    def test_a_share_outside_zero_to_one_is_refused(self, synthetic_economy, share):
        with pytest.raises(ValueError, match="share"):
            increasing_returns(synthetic_economy, seed=0, share=share)

    @pytest.mark.parametrize("increment", [float("nan"), float("inf"), float("-inf")])
    def test_a_non_finite_increment_is_refused(self, synthetic_economy, increment):
        with pytest.raises(ValueError, match="increment"):
            increasing_returns(synthetic_economy, seed=0, increment=increment)


# --------------------------------------------------------------------------- real GDP growth


class TestRealGdpGrowth:
    """Growth in percent, the mean of the growth valued at each year's final prices.

    Swapping the two years does not negate the result: at one price vector ``p`` the growth
    and the swapped growth satisfy ``(1 + g/100) * (1 + g'/100) = 1``, and with two price
    vectors that holds only when they are proportional. The tests below check the properties
    that hold for any prices.
    """

    def test_the_two_good_example_worked_by_hand(self):
        assert math.isclose(real_gdp_growth(*two_years()), TWO_GOOD_GROWTH, rel_tol=1e-14)
        assert math.isclose(TWO_GOOD_GROWTH, 16.358695652173913, rel_tol=1e-15)

    def test_the_result_is_a_float(self):
        assert type(real_gdp_growth(*two_years())) is float

    def test_commodities_other_than_goods_do_not_count(self):
        base = real_gdp_growth(*two_years())
        moved = real_gdp_growth(
            *two_years(
                year_2_output=(8.0, 5.0, 1.0, 3.0),
                year_1_price=(2.0, 5.0, 0.5, 70.0, 3.0),
                year_2_price=(3.0, 4.0, 40.0, 0.1, 9.0),
            )
        )
        assert moved == base

    def test_unchanged_quantities_are_zero_growth(self):
        assert real_gdp_growth(*two_years(year_2_output=YEAR_1_OUTPUT)) == 0.0

    def test_doubled_quantities_are_a_hundred_percent(self):
        doubled = tuple(2.0 * q for q in YEAR_1_OUTPUT)
        assert math.isclose(real_gdp_growth(*two_years(year_2_output=doubled)), 100.0,
                            rel_tol=1e-14)

    def test_swapping_the_two_price_vectors_changes_nothing(self):
        swapped = real_gdp_growth(
            *two_years(year_1_price=YEAR_2_PRICE, year_2_price=YEAR_1_PRICE)
        )
        assert swapped == real_gdp_growth(*two_years())

    def test_scaling_one_years_prices_changes_nothing(self):
        scaled = tuple(1000.0 * p for p in YEAR_2_PRICE)
        assert math.isclose(
            real_gdp_growth(*two_years(year_2_price=scaled)),
            real_gdp_growth(*two_years()),
            rel_tol=1e-13,
        )

    def test_swapping_the_years_under_one_price_vector_inverts_the_growth_factor(self):
        forward = real_gdp_growth(*two_years(year_2_price=YEAR_1_PRICE))
        backward = real_gdp_growth(
            *two_years(year_1_output=YEAR_2_OUTPUT, year_2_output=YEAR_1_OUTPUT,
                       year_2_price=YEAR_1_PRICE)
        )
        assert math.isclose((1 + forward / 100) * (1 + backward / 100), 1.0, rel_tol=1e-14)
        assert math.isclose(forward, 17.5, rel_tol=1e-14)

    def test_quantities_are_read_through_each_years_own_economy(self):
        """Year two's plan is aggregated over year two's economy, not year one's."""
        economy_1 = tiny_economy()
        economy_2 = dataclasses.replace(
            economy_1, output_commodity=np.array((PUBLIC, PRIVATE, INTERMEDIATE, PUBLIC))
        )
        plan_1 = tiny_plan(economy_1, YEAR_1_OUTPUT, YEAR_1_PRICE)
        plan_2 = tiny_plan(economy_2, YEAR_2_OUTPUT, YEAR_2_PRICE)
        # Year two's goods: private 5, public 8 + 3 = 11.
        expected = (100.0 * (2 * 5 + 5 * 11 - 40) / 40 + 100.0 * (3 * 5 + 4 * 11 - 46) / 46) / 2
        assert math.isclose(
            real_gdp_growth(economy_1, plan_1, economy_2, plan_2), expected, rel_tol=1e-14
        )

    def test_a_different_commodity_count_is_refused(self):
        economy_1 = tiny_economy()
        economy_2 = tiny_economy(TINY_KINDS + (CommodityKind.LABOR,))
        plan_1 = tiny_plan(economy_1, YEAR_1_OUTPUT, YEAR_1_PRICE)
        plan_2 = tiny_plan(economy_2, YEAR_2_OUTPUT, YEAR_2_PRICE + (1.0,))
        with pytest.raises(ValueError, match="n_commodities"):
            real_gdp_growth(economy_1, plan_1, economy_2, plan_2)

    def test_a_different_commodity_kind_is_refused(self):
        economy_1 = tiny_economy()
        economy_2 = tiny_economy(TINY_KINDS[:4] + (CommodityKind.LABOR,))
        plan_1 = tiny_plan(economy_1, YEAR_1_OUTPUT, YEAR_1_PRICE)
        plan_2 = tiny_plan(economy_2, YEAR_2_OUTPUT, YEAR_2_PRICE)
        with pytest.raises(ValueError, match="commodity_kind"):
            real_gdp_growth(economy_1, plan_1, economy_2, plan_2)

    @pytest.mark.parametrize("which", [1, 2])
    def test_a_plan_without_the_final_price_is_refused(self, which):
        economy, plan_1, _, plan_2 = two_years()
        bare = tiny_plan(economy, YEAR_1_OUTPUT, indicative_price=DECOY_PRICE)
        if which == 1:
            plan_1 = bare
        else:
            plan_2 = bare
        with pytest.raises(ValueError, match=NEXT_INDICATIVE_PRICE):
            real_gdp_growth(economy, plan_1, economy, plan_2)


# --------------------------------------------------------------------------- relative imbalance

# Supply is output plus endowment: private 6 + 4 + 7 = 17, public 4, intermediate 100,
# labour 50 (endowment), nature 0. Demand is input use plus the consumer councils' demand:
# private 13, public 6, intermediate 30 + 50 = 80, labour 10 + 5 + 20 + 15 = 50, nature 0.
IMBALANCE_INPUT_USE = (30.0, 10.0, 50.0, 5.0, 20.0, 15.0)
IMBALANCE_CONSUMER_DEMAND = (13.0, 6.0, 0.0, 0.0, 0.0)
IMBALANCE_BY_HAND = (8.0 / 30.0, 4.0 / 10.0, 40.0 / 180.0, 0.0, 0.0)


def imbalance_plan(output=YEAR_1_OUTPUT, consumer_demand=IMBALANCE_CONSUMER_DEMAND):
    economy = tiny_economy()
    return economy, tiny_plan(
        economy, output, input_use=IMBALANCE_INPUT_USE, consumer_demand=consumer_demand
    )


class TestRelativeImbalance:
    def test_a_plan_worked_by_hand(self):
        economy, plan = imbalance_plan()
        np.testing.assert_allclose(
            relative_imbalance(economy, plan), IMBALANCE_BY_HAND, rtol=1e-15, atol=0
        )

    def test_it_is_a_float64_vector_of_the_commodity_count(self):
        economy, plan = imbalance_plan()
        measured = relative_imbalance(economy, plan)
        assert isinstance(measured, np.ndarray)
        assert measured.dtype == np.float64
        assert measured.shape == (economy.n_commodities,)

    def test_a_non_finite_supply_counts_as_fully_imbalanced(self):
        economy, plan = imbalance_plan(output=(6.0, 4.0, np.inf, 4.0))
        measured = relative_imbalance(economy, plan)
        assert measured[INTERMEDIATE] == np.inf
        np.testing.assert_allclose(
            np.delete(measured, INTERMEDIATE), np.delete(IMBALANCE_BY_HAND, INTERMEDIATE),
            rtol=1e-15, atol=0,
        )

    def test_a_plan_without_consumer_demand_is_refused(self):
        economy, plan = imbalance_plan(consumer_demand=None)
        with pytest.raises(ValueError, match=CONSUMER_DEMAND):
            relative_imbalance(economy, plan)

    @pytest.mark.parametrize("threshold", [5.0, 3.0])
    def test_it_is_what_the_model_measured_in_every_round(self, synthetic_economy, threshold):
        rule = RecordingRule()
        result = run(
            HahnelBook2021(threshold_pct=threshold, record_trajectory=True, price_rule=rule),
            synthetic_economy,
            seed=0,
        )
        trajectory = result.summary.trajectory
        assert len(trajectory) == len(rule.imbalance) == result.summary.rounds > 3
        for number, (plan, measured) in enumerate(zip(trajectory, rule.imbalance), start=1):
            np.testing.assert_array_equal(
                relative_imbalance(synthetic_economy, plan), measured, err_msg=f"round {number}"
            )

    def test_it_is_what_the_model_measured_in_year_two(self, synthetic_economy):
        rule = RecordingRule()
        result = two_year_run(synthetic_economy, 5, rule)
        first, second = result.periods
        offset = first.result.summary.rounds
        for number, plan in enumerate(second.result.summary.trajectory):
            np.testing.assert_array_equal(
                relative_imbalance(second.economy, plan), rule.imbalance[offset + number]
            )


# --------------------------------------------------------------------------- package surface


class TestPackageSurface:
    def test_the_package_re_exports_the_new_names(self):
        from demplan.prefabs.hahnel import book_2021, councils

        for name in ("perturb_exponents", "WarmStart", "increasing_returns", "real_gdp_growth"):
            assert getattr(hahnel, name) is getattr(book_2021, name), name
            assert name in hahnel.__all__
        assert hahnel.relative_imbalance is councils.relative_imbalance
        assert "relative_imbalance" in hahnel.__all__
        assert list(hahnel.__all__) == sorted(hahnel.__all__)


# --------------------------------------------------------------------------- dep1ex01


@pytest.fixture(scope="module")
def dep1ex01_two_years(dep1ex01_economy):
    rule = RecordingRule()
    return two_year_run(dep1ex01_economy, 0, rule), rule


@pytest.mark.slow
class TestDep1ex01TwoYears:
    def test_both_years_reach_three_percent(self, dep1ex01_two_years):
        result, _ = dep1ex01_two_years
        first, second = result.periods
        assert first.result.summary.converged is True
        assert first.result.summary.rounds == 19
        assert second.result.summary.converged is True

    def test_year_two_starts_from_year_ones_price_and_multiplier(self, dep1ex01_two_years):
        result, rule = dep1ex01_two_years
        first, _ = result.periods
        offset = first.result.summary.rounds
        np.testing.assert_array_equal(
            rule.price[offset], first.result.plan.valuation[NEXT_INDICATIVE_PRICE]
        )
        np.testing.assert_array_equal(rule.state[offset], first.result.plan.extra[PRICE_RULE_STATE])

    def test_relative_imbalance_repeats_the_models_measurement(self, dep1ex01_two_years):
        result, rule = dep1ex01_two_years
        first, second = result.periods
        offset = first.result.summary.rounds
        assert len(second.result.summary.trajectory) == second.result.summary.rounds
        for number, plan in enumerate(second.result.summary.trajectory):
            np.testing.assert_array_equal(
                relative_imbalance(second.economy, plan), rule.imbalance[offset + number]
            )

    def test_growth_computes_on_the_full_economy(self, dep1ex01_two_years):
        """A smoke test: no figure to check against, the book's draws being unrecoverable."""
        result, _ = dep1ex01_two_years
        first, second = result.periods
        growth = real_gdp_growth(
            first.economy, first.result.plan, second.economy, second.result.plan
        )
        assert math.isfinite(growth)
