"""The source-independent half of the Hahnel prefab: the councils, the board and the rule seam.

``CouncilModel`` is driven here through :class:`HahnelBook2021` or directly through
:func:`demplan.iterate`. What is checked is the councils' closed forms, the aggregation, the
plan the board files, and the contract between the board and a price rule that carries state
from one round to the next. The numbers of the program's own rule are checked in
``test_hahnel_book_2021.py``.
"""

from __future__ import annotations

import dataclasses
import importlib
import pickle

import numpy as np
import pytest

import demplan.prefabs
from demplan import (
    COBB_DOUGLAS,
    CONSUMER_DEMAND,
    EFFORT,
    EXPENDITURE,
    INCOME,
    INDICATIVE_PRICE,
    LEONTIEF,
    SchemaError,
    check_determinism,
    iterate,
    run,
    run_configuration,
)
from demplan.plan import AllocatedPlan, StatedPlan
from demplan.prefabs import hahnel
from demplan.prefabs.hahnel import (
    NEXT_INDICATIVE_PRICE,
    PRICE_RULE_STATE,
    CouncilModel,
    HahnelBook2021,
    StatelessPriceRule,
    book_2021_rule,
    stateless,
)
from demplan.prefabs.hahnel.councils import _relative_imbalance
from demplan.tools import segment_sum, unit_of_input
from reference import synthetic
from reference.paths import dep1ex_available

COUNCILS_MODULE = "demplan.prefabs.hahnel.councils"
BOOK_MODULE = "demplan.prefabs.hahnel.book_2021"


def proportional(price, surplus, imbalance):
    """A stateless rule in the three-argument shape: a fifth of the imbalance per round."""
    return price * (1 - 0.2 * np.sign(surplus) * imbalance)


def model_of(economy, rule=book_2021_rule, threshold_pct=5.0):
    return CouncilModel(economy, threshold_pct, rule)


def output_from_the_production_function(economy, plan):
    """``a * effort**c * prod(x_j ** b_j)`` per unit, read back from the plan.

    Written out here rather than taken from the prefab, so that a prefab that dropped the
    effort factor would not also drop it from the expectation.
    """
    owner = unit_of_input(economy)
    exponent = np.asarray(economy.input_coefficient)
    log_output = (
        np.log(np.asarray(economy.technology_scale))
        + np.asarray(economy.unit_extra["effort_c"])
        * np.log(np.asarray(plan.extra["effort"]))
        + segment_sum(economy, exponent * np.log(np.asarray(plan.input_use)), owner)
    )
    return np.exp(log_output)


def upstream_output_and_effort(economy, price):
    """``:output`` and ``:effort`` of the upstream closed form, at ``price``.

    Transcribed from ``upstream/pequod-plus/src/clj/pequod_plus/csvgen.clj``, ``solution-3``,
    whose ``output`` and ``effort`` are written out term by term for three inputs. The eight
    ``solution-N`` bodies repeat the same terms once per input, so the sums below are that
    same expression for any input count.

    This is what pins the effort the prefab records. Reading it back off the production
    function cannot: any value defined as the residual of that function satisfies it.
    """
    owner = unit_of_input(economy)
    scale = np.asarray(economy.technology_scale)
    exponent = np.asarray(economy.input_coefficient)
    effort_c = np.asarray(economy.unit_extra["effort_c"])
    effort_s = np.asarray(economy.unit_extra["effort_s"])
    effort_k = np.asarray(economy.unit_extra["effort_k"])

    log_own_price = np.log(price[np.asarray(economy.output_commodity)])
    log_input_price = np.log(price[np.asarray(economy.input_commodity)])
    exponent_sum = segment_sum(economy, exponent, owner)

    numerator = (
        -effort_k * np.log(scale)
        - effort_k * segment_sum(economy, exponent * np.log(exponent), owner)
        - effort_c * np.log(effort_c)
        + effort_c * np.log(effort_k)
        + effort_k * segment_sum(economy, exponent * log_input_price, owner)
        + effort_c * np.log(effort_s)
        - (effort_c + effort_k * exponent_sum) * log_own_price
    )
    denominator = effort_c - effort_k + effort_k * exponent_sum
    log_output = numerator / denominator

    log_effort = (
        -np.log(scale)
        - segment_sum(economy, exponent * np.log(exponent), owner)
        + segment_sum(economy, exponent * log_input_price, owner)
        - exponent_sum * log_own_price
        + (1.0 - exponent_sum) * log_output
    ) / effort_c
    return np.exp(log_output), np.exp(log_effort)


def imbalance_rebuilt_from(economy, plan):
    """The relative imbalance per commodity, using nothing but the economy and the plan."""
    supply = plan.total_output(economy) + np.asarray(economy.endowment)
    demand = plan.total_input_use(economy) + np.asarray(plan.extra["consumer_demand"])
    total = supply + demand
    return np.where(
        total > 0, np.abs(2 * (supply - demand)) / np.where(total > 0, total, 1.0), 0.0
    )


class RecordingRule:
    """``book_2021_rule`` that keeps a copy of every argument and result of every round."""

    def __init__(self, inner=book_2021_rule):
        self.inner = inner
        self.price = []
        self.surplus = []
        self.imbalance = []
        self.state = []
        self.next_price = []
        self.next_state = []

    def initial_state(self, n_commodities):
        return self.inner.initial_state(n_commodities)

    def __call__(self, price, surplus, imbalance, state):
        self.price.append(np.array(price, copy=True))
        self.surplus.append(np.array(surplus, copy=True))
        self.imbalance.append(np.array(imbalance, copy=True))
        self.state.append(np.array(state, copy=True))
        next_price, next_state = self.inner(price, surplus, imbalance, state)
        self.next_price.append(np.array(next_price, copy=True))
        self.next_state.append(np.array(next_state, copy=True))
        return next_price, next_state


class BufferReusingRule:
    """``book_2021_rule`` computed into two buffers the rule keeps and rewrites every round.

    A rule is free to do this: the arithmetic it hands back is the arithmetic of the named
    rule, and reusing its output buffers is how a rule avoids allocating per round. Each call
    first overwrites both buffers with numbers of its own, so that a board which still held
    either buffer as the last round's price or state would see those numbers instead.
    """

    SCRIBBLE_PRICE = 1.0
    SCRIBBLE_STATE = 7.0

    def __init__(self):
        self.price_buffer = None
        self.state_buffer = None
        self.handed_price = []
        self.handed_state = []

    def initial_state(self, n_commodities):
        return book_2021_rule.initial_state(n_commodities)

    def __call__(self, price, surplus, imbalance, state):
        if self.price_buffer is not None:
            self.price_buffer[:] = self.SCRIBBLE_PRICE
            self.state_buffer[:] = self.SCRIBBLE_STATE
        self.handed_price.append(np.array(price, copy=True))
        self.handed_state.append(np.array(state, copy=True))
        next_price, next_state = book_2021_rule(price, surplus, imbalance, state)
        if self.price_buffer is None:
            self.price_buffer = np.empty_like(next_price)
            self.state_buffer = np.empty_like(next_state)
        self.price_buffer[:] = next_price
        self.state_buffer[:] = next_state
        return self.price_buffer, self.state_buffer


RULE_ARGUMENTS = ("price", "surplus", "imbalance", "state")


def scribbling_through_the_base_of(argument: str):
    """``book_2021_rule`` that writes zeros through one argument's ``base``, if it has one.

    ``base`` is whatever array a view was taken of. A rule that reaches it writes to memory the
    board is still using, and the read-only flag on the view says nothing about it. The write
    is skipped rather than forced when the argument owns its memory, so that the test around
    this rule measures what the run produced and not which exception a write raised.
    """

    class Scribbling:
        def initial_state(self, n_commodities):
            return book_2021_rule.initial_state(n_commodities)

        def __call__(self, price, surplus, imbalance, state):
            stepped = book_2021_rule(price, surplus, imbalance, state)
            target = dict(zip(RULE_ARGUMENTS, (price, surplus, imbalance, state)))[argument]
            if target.base is not None:
                target.base[:] = 0.0
            return stepped

    return Scribbling()


def plan_arrays(plan) -> dict:
    """Every array a plan carries, keyed by where it sits, for comparing two runs."""
    arrays = {
        name: np.asarray(getattr(plan, name))
        for name in ("output", "input_use", "consumption", "consumption_commodity", "shared_use")
    }
    arrays.update({f"valuation.{key}": np.asarray(v) for key, v in plan.valuation.items()})
    arrays.update({f"extra.{key}": np.asarray(v) for key, v in plan.extra.items()})
    return arrays


def assert_the_same_plan(actual, expected, label="plan") -> None:
    left, right = plan_arrays(actual), plan_arrays(expected)
    assert sorted(left) == sorted(right), label
    for name, array in left.items():
        np.testing.assert_array_equal(array, right[name], err_msg=f"{label}: {name}")


def assert_the_same_run(actual, expected) -> None:
    """Assert two runs agree on the round count, the verdict, the plan and any trajectory."""
    assert actual.summary.rounds == expected.summary.rounds
    assert actual.summary.converged == expected.summary.converged
    assert actual.summary.diverged == expected.summary.diverged
    assert_the_same_plan(actual.plan, expected.plan)
    if expected.summary.trajectory is None:
        assert actual.summary.trajectory is None
        return
    assert len(actual.summary.trajectory) == len(expected.summary.trajectory)
    for number, (left, right) in enumerate(
        zip(actual.summary.trajectory, expected.summary.trajectory), start=1
    ):
        assert_the_same_plan(left, right, f"round {number}")


def with_a_negative_denominator(economy):
    """Pushes one unit's ``effort_c`` just below ``effort_k * (1 - sum of exponents)``.

    The worker councils' closed form divides by ``effort_c - effort_k + effort_k * B``. Just
    below zero the exponentials overflow and the whole plan comes out non-finite.
    """
    effort_k = np.asarray(economy.unit_extra["effort_k"])
    owner = unit_of_input(economy)
    exponent_sum = segment_sum(economy, np.asarray(economy.input_coefficient), owner)
    effort_c = np.array(economy.unit_extra["effort_c"], dtype=np.float64)
    effort_c[0] = effort_k[0] - effort_k[0] * exponent_sum[0] - 1e-5
    bag = dict(economy.unit_extra)
    bag["effort_c"] = effort_c
    return dataclasses.replace(economy, unit_extra=bag)


class TestPackageSurface:
    def test_the_two_plan_keys(self):
        assert NEXT_INDICATIVE_PRICE == "next_indicative_price"
        assert PRICE_RULE_STATE == "price_rule_state"

    def test_the_package_re_exports_both_modules(self):
        councils = importlib.import_module(COUNCILS_MODULE)
        book = importlib.import_module(BOOK_MODULE)
        for name in ("PriceRule", "stateless", "CouncilModel", "NEXT_INDICATIVE_PRICE",
                     "PRICE_RULE_STATE"):
            assert getattr(hahnel, name) is getattr(councils, name), name
        for name in ("Book2021Rule", "book_2021_rule", "HahnelBook2021"):
            assert getattr(hahnel, name) is getattr(book, name), name
        assert set(hahnel.__all__) >= {
            "PriceRule", "stateless", "CouncilModel", "NEXT_INDICATIVE_PRICE",
            "PRICE_RULE_STATE", "Book2021Rule", "book_2021_rule", "HahnelBook2021",
        }

    def test_the_prefabs_package_exports_the_hahnel_package(self):
        assert demplan.prefabs.hahnel is hahnel
        assert "hahnel" in demplan.prefabs.__all__

    def test_the_slides_names_are_gone(self):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("demplan.prefabs.hahnel_2020_slides")
        assert not hasattr(demplan.prefabs, "HahnelSlides2020")
        assert not hasattr(hahnel, "slides_2020_rule")
        assert not hasattr(hahnel, "HahnelSlides2020")


class TestSyntheticEconomy:
    def test_it_converges(self, synthetic_economy):
        result = run(HahnelBook2021(), synthetic_economy, seed=0)
        assert result.summary.converged is True
        assert result.summary.rounds is not None
        assert result.summary.rounds < HahnelBook2021().max_rounds

    def test_the_fixture_exercises_the_effort_scale_term(self, synthetic_economy):
        """``c * log(effort_s)`` vanishes from the closed form when every ``effort_s`` is 1,
        which would leave the differential tests blind to that term."""
        effort_s = np.asarray(synthetic_economy.unit_extra["effort_s"])
        assert np.count_nonzero(np.log(effort_s)) > 0

    def test_the_plan_satisfies_the_schema(self, synthetic_economy):
        result = run(HahnelBook2021(), synthetic_economy, seed=0)
        result.plan.validate(synthetic_economy)

    def test_material_balance_at_the_reported_threshold(self, synthetic_economy):
        """Consumption and shared use are the whole of the consumer side on this economy."""
        procedure = HahnelBook2021()
        plan = run(procedure, synthetic_economy, seed=0).plan
        supply = plan.total_output(synthetic_economy) + np.asarray(synthetic_economy.endowment)
        demand = (
            plan.total_input_use(synthetic_economy)
            + plan.total_consumption(synthetic_economy)
            + np.asarray(plan.shared_use)
        )
        total = supply + demand
        imbalance = np.where(
            total > 0, np.abs(2 * (supply - demand)) / np.where(total > 0, total, 1.0), 0.0
        )
        assert imbalance.max() * 100 < procedure.threshold_pct

    def test_consumption_columns_are_the_private_goods(self, synthetic_economy):
        plan = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        kinds = synthetic.kind_labels(synthetic_economy)
        columns = np.asarray(plan.consumption_commodity)
        assert np.all(kinds[columns] == hahnel.PRIVATE_GOOD)
        np.testing.assert_array_equal(
            columns, np.flatnonzero(synthetic.kind_labels(synthetic_economy) == hahnel.PRIVATE_GOOD)
        )
        assert plan.consumption.shape == (synthetic_economy.n_consumers, columns.shape[0])
        assert np.all(plan.consumption > 0.0)

    def test_shared_use_is_confined_to_public_goods(self, synthetic_economy):
        plan = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        kinds = synthetic.kind_labels(synthetic_economy)
        public = kinds == hahnel.PUBLIC_GOOD
        shared_use = np.asarray(plan.shared_use)
        assert np.all(shared_use[public] > 0.0)
        np.testing.assert_array_equal(shared_use[~public], np.zeros(int((~public).sum())))

    def test_shared_use_is_the_councils_stated_level_bit_for_bit(self, synthetic_economy):
        """The same number ``extra["consumer_demand"]`` carries for each public good."""
        plan = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        public = synthetic.kind_labels(synthetic_economy) == hahnel.PUBLIC_GOOD
        expected = np.where(public, np.asarray(plan.extra[CONSUMER_DEMAND]), 0.0)
        assert np.asarray(plan.shared_use).tobytes() == expected.tobytes()

    def test_shared_use_is_a_use_and_not_the_supply(self, synthetic_economy):
        """Supply and stated use of a public good differ until the run balances them exactly."""
        plan = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        public = synthetic.kind_labels(synthetic_economy) == hahnel.PUBLIC_GOOD
        supply = plan.total_output(synthetic_economy)[public]
        assert not np.array_equal(np.asarray(plan.shared_use)[public], supply)

    def test_shared_use_is_the_sum_of_stated_demands_over_the_consumer_units(
        self, synthetic_economy
    ):
        """Worked from the stated bundle at the plan's own price, not read off the prefab."""
        plan = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        bundle = stated_bundle(synthetic_economy, plan.valuation[INDICATIVE_PRICE])
        columns = np.asarray(synthetic_economy.consumer_extra["utility_exponent_commodity"])
        public = synthetic.kind_labels(synthetic_economy) == hahnel.PUBLIC_GOOD
        expected = np.zeros(synthetic_economy.n_commodities)
        for column, commodity in enumerate(columns):
            if public[commodity]:
                expected[commodity] += bundle[:, column].sum() / synthetic_economy.n_consumers
        np.testing.assert_allclose(plan.shared_use, expected, rtol=1e-12, atol=0.0)

    def test_the_reported_price_is_the_one_the_proposals_used(self, synthetic_economy):
        """The published round count is reached at the price of that round, before adjustment."""
        procedure = HahnelBook2021(record_trajectory=True)
        result = run(procedure, synthetic_economy, seed=0)
        one_round_less = HahnelBook2021(max_rounds=result.summary.rounds - 1)
        earlier = run(one_round_less, synthetic_economy, seed=0)
        assert earlier.summary.converged is False
        assert not np.allclose(
            earlier.plan.valuation[INDICATIVE_PRICE], result.plan.valuation[INDICATIVE_PRICE]
        )

    def test_trajectory_is_off_by_default(self, synthetic_economy):
        result = run(HahnelBook2021(), synthetic_economy, seed=0)
        assert result.summary.trajectory is None

    def test_trajectory_has_one_plan_per_round(self, synthetic_economy):
        result = run(HahnelBook2021(record_trajectory=True), synthetic_economy, seed=0)
        assert result.summary.trajectory is not None
        assert len(result.summary.trajectory) == result.summary.rounds
        for plan in result.summary.trajectory:
            plan.validate(synthetic_economy)

    def test_the_returned_plan_is_the_last_round_recorded_or_not(self, synthetic_economy):
        """The plan a run answers with is the round that stopped it, either way it is driven."""
        recorded = run(HahnelBook2021(record_trajectory=True), synthetic_economy, seed=0)
        quiet = run(HahnelBook2021(), synthetic_economy, seed=0)
        last = recorded.summary.trajectory[-1]
        assert len(recorded.summary.trajectory) > 1
        assert_the_same_plan(recorded.plan, last, "recorded")
        assert_the_same_plan(quiet.plan, last, "quiet")

    def test_the_first_trajectory_entry_is_priced_at_the_initial_price(self, synthetic_economy):
        procedure = HahnelBook2021(record_trajectory=True, initial_price=640.0)
        result = run(procedure, synthetic_economy, seed=0)
        np.testing.assert_array_equal(
            result.summary.trajectory[0].valuation[INDICATIVE_PRICE],
            np.full(synthetic_economy.n_commodities, 640.0),
        )

    def test_a_round_cap_stops_the_loop(self, synthetic_economy):
        result = run(HahnelBook2021(max_rounds=3), synthetic_economy, seed=0)
        assert result.summary.rounds == 3
        assert result.summary.converged is False

    def test_a_tighter_threshold_needs_more_rounds(self, synthetic_economy):
        loose = run(HahnelBook2021(threshold_pct=5.0), synthetic_economy, seed=0)
        tight = run(HahnelBook2021(threshold_pct=3.0), synthetic_economy, seed=0)
        assert tight.summary.rounds > loose.summary.rounds


class TestTechnologyGuard:
    """The closed form is the technology labelled ``hahnel.TECHNOLOGY`` and no other."""

    def test_an_all_leontief_economy_is_refused(self, synthetic_economy):
        leontief = dataclasses.replace(
            synthetic_economy, technology_kind=[LEONTIEF] * synthetic_economy.n_units
        )
        with pytest.raises(ValueError, match="Cobb-Douglas"):
            run(HahnelBook2021(), leontief, seed=0)

    def test_plain_cobb_douglas_is_not_the_label_either(self, synthetic_economy):
        """dep1ex's technology carries an effort factor, so ``cobb_douglas`` does not describe it."""
        plain = dataclasses.replace(
            synthetic_economy, technology_kind=[COBB_DOUGLAS] * synthetic_economy.n_units
        )
        with pytest.raises(ValueError, match="hahnel_cobb_douglas_effort"):
            run(HahnelBook2021(), plain, seed=0)

    def test_one_leontief_unit_is_enough_and_the_message_names_it(self, synthetic_economy):
        labels = [str(label) for label in synthetic_economy.technology_kind]
        labels[2] = LEONTIEF
        mixed = dataclasses.replace(synthetic_economy, technology_kind=labels)
        with pytest.raises(ValueError, match="unit 2"):
            run(HahnelBook2021(), mixed, seed=0)

    def test_the_message_names_the_label_found_and_the_label_wanted(self, synthetic_economy):
        labels = [str(label) for label in synthetic_economy.technology_kind]
        labels[5] = "my_own_technology"
        mixed = dataclasses.replace(synthetic_economy, technology_kind=labels)
        with pytest.raises(ValueError) as refused:
            model_of(mixed)
        message = str(refused.value)
        assert "unit 5" in message
        assert "'my_own_technology'" in message
        assert "'hahnel_cobb_douglas_effort'" in message
        assert "TECHNOLOGY" in message

    def test_the_label_constant(self):
        assert hahnel.TECHNOLOGY == "hahnel_cobb_douglas_effort"


class TestOneOutputPerUnit:
    def test_a_unit_with_two_outputs_is_refused_and_named(self):
        joint = synthetic.build_joint_product_economy()
        with pytest.raises(ValueError) as refused:
            model_of(joint)
        message = str(refused.value)
        assert "unit 0" in message
        assert "joint products" in message

    def test_the_prefab_refuses_it_too(self):
        with pytest.raises(ValueError, match="joint products"):
            run(HahnelBook2021(), synthetic.build_joint_product_economy(), seed=0)


def with_output_coefficient(economy, unit, value):
    column = np.asarray(economy.output_coefficient).copy()
    column[unit] = value
    return dataclasses.replace(economy, output_coefficient=column)


class TestOutputCoefficientIsOne:
    """The production function sets output itself, so an output coefficient has no place in it."""

    @pytest.mark.parametrize("value", [2.0, 0.5, 1.0 + 1e-12])
    def test_a_coefficient_other_than_one_is_refused(self, synthetic_economy, value):
        with pytest.raises(ValueError, match="output_coefficient"):
            model_of(with_output_coefficient(synthetic_economy, 3, value))

    def test_the_message_names_the_unit_the_value_and_why(self, synthetic_economy):
        with pytest.raises(ValueError) as refused:
            model_of(with_output_coefficient(synthetic_economy, 3, 2.0))
        message = str(refused.value)
        assert "unit 3" in message
        assert "output_coefficient 2.0" in message
        assert "ignored" in message
        assert "Q = a * e**c * prod(x_j ** b_j)" in message

    def test_the_prefab_refuses_it_too(self, synthetic_economy):
        with pytest.raises(ValueError, match="output_coefficient"):
            run(HahnelBook2021(), with_output_coefficient(synthetic_economy, 0, 2.0), seed=0)

    def test_every_coefficient_at_one_is_accepted(self, synthetic_economy):
        assert np.all(np.asarray(synthetic_economy.output_coefficient) == 1.0)
        model_of(synthetic_economy)


def without_kind_labels(economy):
    bag = {key: value for key, value in economy.commodity_extra.items() if key != "hahnel_kind"}
    return dataclasses.replace(economy, commodity_extra=bag)


def with_kind_labels(economy, labels):
    return dataclasses.replace(
        economy, commodity_extra={**economy.commodity_extra, "hahnel_kind": labels}
    )


class TestKindLabelsAreRequired:
    """``hahnel_kind`` is what the councils read the five commodity classes from."""

    def test_a_missing_label_column_is_refused_with_a_way_to_fill_it(self, synthetic_economy):
        with pytest.raises(ValueError) as refused:
            model_of(without_kind_labels(synthetic_economy))
        message = str(refused.value)
        assert "commodity_extra['hahnel_kind']" in message
        for label in ("private_good", "public_good", "intermediate", "natural_resource", "labor"):
            assert f"'{label}'" in message
        assert "load_dep1ex" in message

    def test_the_prefab_refuses_it_before_running(self, synthetic_economy):
        with pytest.raises(ValueError, match="hahnel_kind"):
            run(HahnelBook2021(), without_kind_labels(synthetic_economy), seed=0)

    @pytest.mark.parametrize("row", [0, 7, 14])
    def test_an_unknown_label_is_refused_and_named_with_its_commodity(
        self, synthetic_economy, row
    ):
        labels = [str(label) for label in synthetic.kind_labels(synthetic_economy)]
        labels[row] = "privte_good"
        with pytest.raises(ValueError) as refused:
            model_of(with_kind_labels(synthetic_economy, labels))
        message = str(refused.value)
        assert "'privte_good'" in message
        assert f"commodity {row}" in message
        assert "'private_good'" in message

    def test_a_numeric_label_column_is_refused(self, synthetic_economy):
        codes = np.zeros(synthetic_economy.n_commodities, dtype=np.int64)
        with pytest.raises(ValueError, match="hahnel_kind"):
            model_of(with_kind_labels(synthetic_economy, codes))

    def test_the_five_label_constants(self):
        assert hahnel.PRIVATE_GOOD == "private_good"
        assert hahnel.PUBLIC_GOOD == "public_good"
        assert hahnel.INTERMEDIATE == "intermediate"
        assert hahnel.NATURAL_RESOURCE == "natural_resource"
        assert hahnel.LABOR == "labor"


class TestRequiredExtraKeys:
    """The closed form reads named columns out of the extra bags, and says which one is absent.

    Every key here carries a parameter of the councils' behaviour that the physical columns of
    the data model do not hold. Reaching the arithmetic without one raises ``KeyError`` naming
    a string, which leaves the reader to work out that the economy is missing a column the
    prefab needs rather than that the prefab is broken.
    """

    @pytest.mark.parametrize("key", ["effort_c", "effort_s", "effort_k"])
    def test_a_missing_unit_key_is_refused_and_the_message_names_it(self, synthetic_economy, key):
        kept = {name: value for name, value in synthetic_economy.unit_extra.items() if name != key}
        economy = dataclasses.replace(synthetic_economy, unit_extra=kept)
        with pytest.raises(ValueError, match=key):
            run(HahnelBook2021(), economy, seed=0)

    @pytest.mark.parametrize(
        "key", ["entitlement", "utility_exponent", "utility_exponent_commodity"]
    )
    def test_a_missing_consumer_key_is_refused_and_the_message_names_it(
        self, synthetic_economy, key
    ):
        kept = {
            name: value for name, value in synthetic_economy.consumer_extra.items() if name != key
        }
        economy = dataclasses.replace(synthetic_economy, consumer_extra=kept)
        with pytest.raises(ValueError, match=key):
            run(HahnelBook2021(), economy, seed=0)

    def test_the_message_names_every_absent_key_at_once(self, synthetic_economy):
        economy = dataclasses.replace(synthetic_economy, unit_extra={})
        with pytest.raises(ValueError, match="effort_c.*effort_s.*effort_k"):
            run(HahnelBook2021(), economy, seed=0)


class TestPermutedCommodityOrder:
    """The private goods are picked by ``hahnel_kind``, not by where they sit in the table."""

    def test_the_fixture_does_not_put_the_private_goods_first(self):
        economy = synthetic.build_permuted_economy()
        kinds = synthetic.kind_labels(economy)
        assert kinds[0] != hahnel.PRIVATE_GOOD

        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        private_columns = np.flatnonzero(kinds[columns] == hahnel.PRIVATE_GOOD)
        assert private_columns.tolist() != list(range(private_columns.size))

    def test_the_consumption_columns_are_still_the_private_goods(self):
        economy = synthetic.build_permuted_economy()
        plan = run(HahnelBook2021(), economy, seed=0).plan
        kinds = synthetic.kind_labels(economy)
        columns = np.asarray(plan.consumption_commodity)

        assert np.all(kinds[columns] == hahnel.PRIVATE_GOOD)
        np.testing.assert_array_equal(
            columns, np.flatnonzero(synthetic.kind_labels(economy) == hahnel.PRIVATE_GOOD)
        )
        plan.validate(economy)

    def test_the_shared_use_is_still_confined_to_the_public_goods(self):
        economy = synthetic.build_permuted_economy()
        plan = run(HahnelBook2021(), economy, seed=0).plan
        public = synthetic.kind_labels(economy) == hahnel.PUBLIC_GOOD
        shared_use = np.asarray(plan.shared_use)
        assert np.all(shared_use[public] > 0.0)
        assert shared_use[~public].sum() == 0.0
        expected = np.where(public, np.asarray(plan.extra[CONSUMER_DEMAND]), 0.0)
        assert shared_use.tobytes() == expected.tobytes()

    def test_renumbering_the_commodities_does_not_change_the_round_count(
        self, synthetic_economy
    ):
        permuted = synthetic.build_permuted_economy()
        assert (
            run(HahnelBook2021(), permuted, seed=0).summary.rounds
            == run(HahnelBook2021(), synthetic_economy, seed=0).summary.rounds
        )


class TestNonFiniteRuns:
    """A plan of NaN is not a feasible plan, whatever the imbalance arithmetic says about it."""

    def test_a_non_finite_supply_counts_as_fully_imbalanced(self):
        supply = np.array([np.inf, 1.0, np.nan, 3.0])
        demand = np.array([1.0, 1.0, 1.0, np.inf])
        imbalance = _relative_imbalance(supply, demand)
        assert imbalance[0] == np.inf
        assert imbalance[1] == 0.0
        assert imbalance[2] == np.inf
        assert imbalance[3] == np.inf

    def test_an_untouched_commodity_is_still_balanced(self):
        imbalance = _relative_imbalance(np.array([0.0]), np.array([0.0]))
        assert imbalance[0] == 0.0

    def test_a_run_that_goes_non_finite_does_not_report_convergence(self, synthetic_economy):
        economy = with_a_negative_denominator(synthetic_economy)
        with np.errstate(all="ignore"):
            result = run(HahnelBook2021(), economy, seed=0)
        assert result.summary.converged is False

    def test_the_default_configuration_stops_at_the_non_finite_round(self, synthetic_economy):
        economy = with_a_negative_denominator(synthetic_economy)
        model = model_of(economy)
        with np.errstate(all="ignore"):
            result = iterate(
                lambda: model.initial_state(700.0),
                model.step,
                model.converged,
                250,
                plan_of=model.plan_of,
                keep_trajectory=False,
            )
        assert result.diverged is True
        assert result.converged is False
        assert result.trajectory is None

    def test_recording_the_trajectory_does_not_change_the_verdict(self, synthetic_economy):
        economy = with_a_negative_denominator(synthetic_economy)
        with np.errstate(all="ignore"):
            quiet = run(HahnelBook2021(), economy, seed=0)
            recorded = run(HahnelBook2021(record_trajectory=True), economy, seed=0)
        assert quiet.summary.converged == recorded.summary.converged
        assert quiet.summary.rounds == recorded.summary.rounds


class TestPlanRecordsWhatTheMechanismChose:
    """Whatever the mechanism decided has to be readable back off the plan."""

    def test_the_extra_bag_holds_exactly_the_three_documented_keys(self, synthetic_economy):
        """Addressed through the exported constants, so the prefab and a reader cannot drift."""
        plan = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        assert sorted(plan.extra) == sorted([CONSUMER_DEMAND, EFFORT, PRICE_RULE_STATE])
        assert plan.extra[EFFORT].shape == (synthetic_economy.n_units,)
        assert plan.extra[CONSUMER_DEMAND].shape == (synthetic_economy.n_commodities,)
        assert plan.extra[PRICE_RULE_STATE].shape == (synthetic_economy.n_commodities,)

    def test_the_valuation_bag_holds_the_two_prices_and_the_budget(self, synthetic_economy):
        plan = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        assert sorted(plan.valuation) == sorted(
            [INDICATIVE_PRICE, NEXT_INDICATIVE_PRICE, INCOME, EXPENDITURE]
        )
        for key in (INDICATIVE_PRICE, NEXT_INDICATIVE_PRICE):
            assert plan.valuation[key].dtype == np.float64
            assert plan.valuation[key].shape == (synthetic_economy.n_commodities,)
        for key in (INCOME, EXPENDITURE):
            assert plan.valuation[key].dtype == np.float64
            assert plan.valuation[key].shape == (synthetic_economy.n_consumers,)

    def test_every_trajectory_plan_carries_the_same_keys(self, synthetic_economy):
        result = run(HahnelBook2021(record_trajectory=True), synthetic_economy, seed=0)
        for plan in result.summary.trajectory:
            assert sorted(plan.valuation) == sorted(
                [INDICATIVE_PRICE, NEXT_INDICATIVE_PRICE, INCOME, EXPENDITURE]
            )
            assert sorted(plan.extra) == sorted([CONSUMER_DEMAND, EFFORT, PRICE_RULE_STATE])

    def test_the_plan_reproduces_its_own_production_function(self, synthetic_economy):
        plan = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        np.testing.assert_allclose(
            np.asarray(plan.output),
            output_from_the_production_function(synthetic_economy, plan),
            rtol=1e-9,
            atol=0,
        )

    def test_effort_matches_the_upstream_closed_form(self, synthetic_economy):
        model = model_of(synthetic_economy)
        price = np.full(synthetic_economy.n_commodities, 700.0)
        _, effort, _ = model._propose(price)

        expected_output, expected_effort = upstream_output_and_effort(synthetic_economy, price)
        np.testing.assert_allclose(effort, expected_effort, rtol=1e-12, atol=0)
        np.testing.assert_allclose(
            model._propose(price)[0], expected_output, rtol=1e-12, atol=0
        )

    def test_effort_matches_the_upstream_closed_form_at_an_uneven_price(
        self, synthetic_economy
    ):
        """A flat price hides a term that only shows when the prices differ."""
        model = model_of(synthetic_economy)
        price = uneven_price(synthetic_economy)
        _, effort, _ = model._propose(price)

        _, expected_effort = upstream_output_and_effort(synthetic_economy, price)
        np.testing.assert_allclose(effort, expected_effort, rtol=1e-12, atol=0)

    def test_effort_is_one_positive_value_per_unit(self, synthetic_economy):
        plan = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        effort = np.asarray(plan.extra["effort"])
        assert effort.shape == (synthetic_economy.n_units,)
        assert effort.dtype == np.float64
        assert np.all(effort > 0.0)

    def test_dropping_effort_would_not_reproduce_the_output(self, synthetic_economy):
        """Without the effort factor the identity is off by a factor the tolerance rejects."""
        plan = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        owner = unit_of_input(synthetic_economy)
        exponent = np.asarray(synthetic_economy.input_coefficient)
        without_effort = np.exp(
            np.log(np.asarray(synthetic_economy.technology_scale))
            + segment_sum(
                synthetic_economy, exponent * np.log(np.asarray(plan.input_use)), owner
            )
        )
        assert not np.allclose(np.asarray(plan.output), without_effort, rtol=1e-9, atol=0)

    def test_the_public_good_imbalance_is_the_one_the_mechanism_measured(
        self, synthetic_economy
    ):
        rule = RecordingRule()
        result = run(HahnelBook2021(price_rule=rule), synthetic_economy, seed=0)
        public = synthetic.kind_labels(synthetic_economy) == hahnel.PUBLIC_GOOD

        rebuilt = imbalance_rebuilt_from(synthetic_economy, result.plan)
        np.testing.assert_allclose(
            rebuilt[public], rule.imbalance[-1][public], rtol=1e-12, atol=0
        )
        assert rebuilt[public].max() > 0.0

    def test_consumer_demand_is_zero_where_no_column_names_the_commodity(
        self, synthetic_economy
    ):
        """No utility-exponent column names the commodity, so the councils ask for none of it."""
        plan = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        stated = np.asarray(plan.extra["consumer_demand"])
        columns = np.asarray(synthetic_economy.consumer_extra["utility_exponent_commodity"])
        named = np.zeros(synthetic_economy.n_commodities, dtype=bool)
        named[columns] = True

        assert stated.shape == (synthetic_economy.n_commodities,)
        assert stated.dtype == np.float64
        assert named.any() and not named.all()
        assert np.all(stated[named] > 0.0)
        np.testing.assert_array_equal(stated[~named], np.zeros(int((~named).sum())))

    def test_shared_use_is_the_demand_side_of_the_public_good_balance(
        self, synthetic_economy
    ):
        """Supply against input use plus shared use is the imbalance the board measured."""
        rule = RecordingRule()
        plan = run(HahnelBook2021(price_rule=rule), synthetic_economy, seed=0).plan
        supply = plan.total_output(synthetic_economy) + np.asarray(synthetic_economy.endowment)
        demand = (
            plan.total_input_use(synthetic_economy)
            + plan.total_consumption(synthetic_economy)
            + np.asarray(plan.shared_use)
        )
        public = synthetic.kind_labels(synthetic_economy) == hahnel.PUBLIC_GOOD
        total = supply + demand
        imbalance = np.abs(2 * (supply - demand)) / total
        np.testing.assert_allclose(
            imbalance[public], rule.imbalance[-1][public], rtol=1e-12, atol=0
        )
        assert not np.array_equal(supply[public], demand[public])


class TestPriceRuleSeam:
    """Swapping the price rule is the one change the procedure is built to take."""

    def test_a_rule_that_never_moves_the_price_never_converges(self, synthetic_economy):
        def frozen(price, surplus, imbalance):
            return price

        result = run(
            HahnelBook2021(price_rule=stateless(frozen), max_rounds=6), synthetic_economy, seed=0
        )
        assert result.summary.converged is False
        assert result.summary.rounds == 6
        np.testing.assert_array_equal(
            result.plan.valuation[INDICATIVE_PRICE],
            np.full(synthetic_economy.n_commodities, HahnelBook2021().initial_price),
        )

    def test_the_rule_is_handed_the_surplus_and_the_imbalance_of_that_round(
        self, synthetic_economy
    ):
        """Checked on the private goods, whose supply and demand the plan alone accounts for."""
        rule = RecordingRule()
        result = run(
            HahnelBook2021(price_rule=rule, max_rounds=1, record_trajectory=True),
            synthetic_economy,
            seed=0,
        )
        plan = result.summary.trajectory[0]
        surplus, imbalance = rule.surplus[0], rule.imbalance[0]

        private = synthetic.kind_labels(synthetic_economy) == hahnel.PRIVATE_GOOD
        supply = plan.total_output(synthetic_economy) + np.asarray(synthetic_economy.endowment)
        demand = plan.total_input_use(synthetic_economy) + plan.total_consumption(
            synthetic_economy
        )
        np.testing.assert_allclose(surplus[private], (supply - demand)[private], rtol=1e-12)
        total = (supply + demand)[private]
        np.testing.assert_allclose(
            imbalance[private], np.abs(2 * (supply - demand)[private]) / total, rtol=1e-12
        )

    def test_a_custom_rule_matches_a_loop_assembled_from_the_council_model(
        self, synthetic_economy
    ):
        """Driving ``CouncilModel`` through ``iterate`` by hand reaches the same fixed point."""
        rule = stateless(proportional)
        through_the_seam = run(
            HahnelBook2021(price_rule=rule, max_rounds=60), synthetic_economy, seed=0
        )

        model = model_of(synthetic_economy, rule)
        by_hand = iterate(
            lambda: model.initial_state(HahnelBook2021().initial_price),
            model.step,
            model.converged,
            60,
        )
        assert through_the_seam.summary.rounds == by_hand.rounds
        assert through_the_seam.summary.converged == by_hand.converged
        np.testing.assert_array_equal(
            through_the_seam.plan.output, model.plan_of(by_hand.state).output
        )


class TestTheStateLivesInTheBoard:
    """A rule carries state from one round to the next, and the board is what carries it.

    The rule object is reused across runs, so any state it kept on itself would leak from one
    run into the next. The board asks the rule for a starting state once per run, hands each
    round the state the previous round returned, and files what the rule returned on the plan.
    """

    class CountingState:
        """Starts every commodity at zero and returns the state it was handed plus one."""

        initial_calls = 0

        def initial_state(self, n_commodities):
            type(self).initial_calls += 1
            return np.zeros(n_commodities)

        def __call__(self, price, surplus, imbalance, state):
            return proportional(price, surplus, imbalance), state + 1.0

    def test_the_initial_state_is_asked_for_once_per_run(self, synthetic_economy):
        rule = self.CountingState()
        type(rule).initial_calls = 0
        run(HahnelBook2021(price_rule=rule, max_rounds=5), synthetic_economy, seed=0)
        assert type(rule).initial_calls == 1
        run(HahnelBook2021(price_rule=rule, max_rounds=5), synthetic_economy, seed=0)
        assert type(rule).initial_calls == 2

    def test_round_one_is_handed_the_rules_initial_state(self, synthetic_economy):
        class Distinct(RecordingRule):
            def initial_state(self, n_commodities):
                return np.linspace(0.05, 0.2, n_commodities)

        rule = Distinct()
        run(HahnelBook2021(price_rule=rule, max_rounds=2), synthetic_economy, seed=0)
        np.testing.assert_array_equal(
            rule.state[0], np.linspace(0.05, 0.2, synthetic_economy.n_commodities)
        )

    def test_each_round_is_handed_the_state_the_round_before_returned(self, synthetic_economy):
        rule = RecordingRule(self.CountingState())
        run(HahnelBook2021(price_rule=rule, max_rounds=6), synthetic_economy, seed=0)
        assert len(rule.state) == 6
        for number, handed in enumerate(rule.state):
            np.testing.assert_array_equal(
                handed, np.full(synthetic_economy.n_commodities, float(number))
            )

    def test_the_plan_files_what_the_rule_returned(self, synthetic_economy):
        rule = RecordingRule()
        result = run(
            HahnelBook2021(price_rule=rule, record_trajectory=True), synthetic_economy, seed=0
        )
        trajectory = result.summary.trajectory
        assert len(trajectory) == len(rule.next_price) > 3
        for number, plan in enumerate(trajectory):
            np.testing.assert_array_equal(
                plan.valuation[NEXT_INDICATIVE_PRICE], rule.next_price[number]
            )
            np.testing.assert_array_equal(plan.extra[PRICE_RULE_STATE], rule.next_state[number])
            np.testing.assert_array_equal(plan.valuation[INDICATIVE_PRICE], rule.price[number])

    @pytest.mark.parametrize("rounds", [1, 2, 5])
    def test_the_two_new_entries_are_the_next_rounds_inputs(self, synthetic_economy, rounds):
        """A run of ``rounds`` rounds, and one of ``rounds + 1`` with every round recorded."""
        shorter = run(HahnelBook2021(max_rounds=rounds), synthetic_economy, seed=0)
        rule = RecordingRule()
        longer = run(
            HahnelBook2021(price_rule=rule, max_rounds=rounds + 1, record_trajectory=True),
            synthetic_economy,
            seed=0,
        )
        assert shorter.summary.rounds == rounds
        assert len(rule.price) == rounds + 1
        np.testing.assert_array_equal(
            shorter.plan.valuation[NEXT_INDICATIVE_PRICE], rule.price[rounds]
        )
        np.testing.assert_array_equal(shorter.plan.extra[PRICE_RULE_STATE], rule.state[rounds])
        np.testing.assert_array_equal(
            shorter.plan.valuation[NEXT_INDICATIVE_PRICE],
            longer.summary.trajectory[rounds].valuation[INDICATIVE_PRICE],
        )
        assert_the_same_plan(shorter.plan, longer.summary.trajectory[rounds - 1])

    def test_the_same_procedure_solved_again_is_bit_identical(self, synthetic_economy):
        report = check_determinism(HahnelBook2021(max_rounds=8), synthetic_economy, 0, n=3)
        assert report.identical is True

    def test_a_run_in_between_on_another_economy_changes_nothing(self, synthetic_economy):
        """The same rule object, used on another economy between two runs on this one."""
        procedure = HahnelBook2021(price_rule=book_2021_rule, record_trajectory=True)
        first = run(procedure, synthetic_economy, seed=0)
        run(procedure, synthetic.build_economy_with_unordered_private_columns(), seed=0)
        second = run(procedure, synthetic_economy, seed=0)
        assert_the_same_run(second, first)

    def test_a_two_column_state_is_carried_and_filed(self, synthetic_economy):
        """The state's first dimension is the commodity count; the rest is the rule's."""

        class TwoColumns:
            def initial_state(self, n_commodities):
                return np.zeros((n_commodities, 2))

            def __call__(self, price, surplus, imbalance, state):
                return proportional(price, surplus, imbalance), state + [1.0, 2.0]

        result = run(
            HahnelBook2021(price_rule=TwoColumns(), max_rounds=3), synthetic_economy, seed=0
        )
        expected = np.tile([3.0, 6.0], (synthetic_economy.n_commodities, 1))
        np.testing.assert_array_equal(result.plan.extra[PRICE_RULE_STATE], expected)
        result.plan.validate(synthetic_economy)


def rule_with_initial_state(state_of):
    class Rule(RecordingRule):
        def initial_state(self, n_commodities):
            return state_of(n_commodities)

    return Rule()


def rule_returning_state(state_of):
    class Rule(RecordingRule):
        def __call__(self, price, surplus, imbalance, state):
            next_price, _ = super().__call__(price, surplus, imbalance, state)
            return next_price, state_of(len(price))

    return Rule()


INVALID_STATES = [
    ("too short", "n_commodities", lambda n: np.full(n - 1, 0.25)),
    ("too long", "n_commodities", lambda n: np.full(n + 1, 0.25)),
    ("zero-dimensional", "n_commodities", lambda n: np.array(0.25)),
    ("float32", "float64", lambda n: np.full(n, 0.25, dtype=np.float32)),
    ("integer", "float64", lambda n: np.zeros(n, dtype=np.int64)),
    ("a list", "float64", lambda n: [0.25] * n),
    ("NaN", "finite", lambda n: np.where(np.arange(n) == 3, np.nan, 0.25)),
    ("infinite", "finite", lambda n: np.where(np.arange(n) == 3, np.inf, 0.25)),
]


class TestTheStateIsValidated:
    """A state that cannot be filed on a plan, or carried to the next round, is refused.

    The message names the problem: the dtype, the commodity count, or a value that is not
    finite.
    """

    @pytest.mark.parametrize(
        "problem, named, make", INVALID_STATES, ids=[case[0] for case in INVALID_STATES]
    )
    def test_an_invalid_initial_state_from_the_rule_is_refused(
        self, synthetic_economy, problem, named, make
    ):
        rule = rule_with_initial_state(make)
        with pytest.raises(ValueError, match=named):
            run(HahnelBook2021(price_rule=rule), synthetic_economy, seed=0)
        assert rule.state == []

    @pytest.mark.parametrize(
        "problem, named, make", INVALID_STATES, ids=[case[0] for case in INVALID_STATES]
    )
    def test_an_invalid_returned_state_is_refused(self, synthetic_economy, problem, named, make):
        rule = rule_returning_state(make)
        with pytest.raises(ValueError, match=named):
            run(HahnelBook2021(price_rule=rule), synthetic_economy, seed=0)
        assert len(rule.state) == 1

    @pytest.mark.parametrize(
        "problem, named, make", INVALID_STATES, ids=[case[0] for case in INVALID_STATES]
    )
    def test_an_invalid_supplied_state_is_refused(self, synthetic_economy, problem, named, make):
        rule = RecordingRule()
        state = make(synthetic_economy.n_commodities)
        with pytest.raises(ValueError, match=named):
            run(
                HahnelBook2021(price_rule=rule, initial_rule_state=state),
                synthetic_economy,
                seed=0,
            )
        assert rule.state == []


class TestPriceRuleArgumentsAreReadOnly:
    """The board hands its price rule read-only copies, so a rule that writes to one is stopped.

    Three of the four arguments feed numbers the run reports, and a rule that wrote to one
    changed those numbers with nothing raised. Measured on ``synthetic_economy`` with the
    copies replaced by the board's own arrays, against an honest run of 20 rounds ending at
    prices ``[897.312008, 942.589276, 711.670185, ...]``:

    * a rule writing to ``price`` left the run's own output untouched and
      ``valuation["indicative_price"]`` holding ``[0, 0, 0, ...]`` on all 20 plans -- plans
      filed under a price their proposals were never made at;
    * a rule writing to ``imbalance`` decided the convergence test, and the run stopped after
      1 round instead of 20, reporting ``converged=True`` on the initial flat price of 700;
    * a rule writing to ``state`` left every price and quantity as it was and 19 of the 20
      plans filing ``extra["price_rule_state"]`` as zeros: the state a round is handed is the
      one the round before filed.

    ``surplus`` reaches nothing the run reports; it is handed over read-only because the
    contract covers the argument list, not because a corruption through it was observed.
    """

    def scribble_on(self, argument: str):
        """``book_2021_rule`` that writes zeros over one of the arguments it was handed."""

        class Scribbling:
            def initial_state(self, n_commodities):
                return book_2021_rule.initial_state(n_commodities)

            def __call__(self, price, surplus, imbalance, state):
                stepped = book_2021_rule(price, surplus, imbalance, state)
                dict(zip(RULE_ARGUMENTS, (price, surplus, imbalance, state)))[argument][:] = 0.0
                return stepped

        return Scribbling()

    def test_all_four_arguments_arrive_read_only(self, synthetic_economy):
        seen = []

        class Inspecting(RecordingRule):
            def __call__(self, price, surplus, imbalance, state):
                seen.append(
                    tuple(bool(a.flags.writeable) for a in (price, surplus, imbalance, state))
                )
                return super().__call__(price, surplus, imbalance, state)

        run(HahnelBook2021(price_rule=Inspecting(), max_rounds=3), synthetic_economy, seed=0)
        assert seen == [(False, False, False, False)] * 3

    @pytest.mark.parametrize("argument", RULE_ARGUMENTS)
    def test_a_rule_that_writes_to_an_argument_is_stopped(self, synthetic_economy, argument):
        with pytest.raises(ValueError, match="read-only"):
            run(
                HahnelBook2021(price_rule=self.scribble_on(argument), max_rounds=25),
                synthetic_economy,
                seed=0,
            )

    def test_the_price_the_plan_records_is_the_price_the_rule_was_handed(
        self, synthetic_economy
    ):
        """What writing to ``price`` breaks, stated as the property it breaks."""
        rule = RecordingRule()
        result = run(HahnelBook2021(price_rule=rule), synthetic_economy, seed=0)
        np.testing.assert_array_equal(result.plan.valuation[INDICATIVE_PRICE], rule.price[-1])

    def test_the_round_count_is_the_one_the_measured_imbalance_produces(
        self, synthetic_economy
    ):
        """What writing to ``imbalance`` breaks: it decides when the loop stops."""
        rule = RecordingRule()
        result = run(HahnelBook2021(price_rule=rule), synthetic_economy, seed=0)

        assert result.summary.converged is True
        assert len(rule.imbalance) == result.summary.rounds
        threshold = HahnelBook2021().threshold_pct / 100.0
        assert rule.imbalance[-1].max() < threshold
        assert all(measured.max() >= threshold for measured in rule.imbalance[:-1])

    def test_the_state_keeps_the_array_it_was_stepped_with(self, synthetic_economy):
        """The read-only copies are for the rule alone and do not become the recorded state."""
        model = model_of(synthetic_economy)
        start = model.initial_state(700.0)
        stepped = model.step(start)
        assert stepped.price is start.next_price

    def test_a_rule_that_returns_its_own_arguments_still_runs(self, synthetic_economy):
        """A rule may hand an argument straight back; only writing to one is refused."""

        class Unmoving:
            def initial_state(self, n_commodities):
                return np.zeros(n_commodities)

            def __call__(self, price, surplus, imbalance, state):
                return price, state

        result = run(
            HahnelBook2021(price_rule=Unmoving(), max_rounds=4), synthetic_economy, seed=0
        )
        assert result.summary.rounds == 4
        np.testing.assert_array_equal(
            result.plan.valuation[INDICATIVE_PRICE],
            np.full(synthetic_economy.n_commodities, HahnelBook2021().initial_price),
        )


class TestThePriceRuleCannotReachTheBoardsState:
    """What a rule does to its arguments and to its own buffers decides nothing the run reports.

    The read-only flag alone covers one way in. Two more run through ownership: an argument
    that is a view keeps the board's live array reachable as ``base``, and a return value the
    board keeps is a buffer the rule can go on writing to. Both decide reported numbers -- the
    plan is filed under the price the board stepped with, the next round is stepped with the
    state the board carries, and the round count is the convergence test on the measured
    imbalance -- so each one is asserted against a run of the same rule's arithmetic that
    reaches for neither.
    """

    def honest_run(self, economy, **settings):
        return run(HahnelBook2021(**settings), economy, seed=0)

    def test_no_argument_is_a_view_of_anything(self, synthetic_economy):
        """An array that owns its memory has no ``base``, and so nothing behind it."""
        seen = []

        class Inspecting(RecordingRule):
            def __call__(self, price, surplus, imbalance, state):
                seen.append(tuple(a.base for a in (price, surplus, imbalance, state)))
                return super().__call__(price, surplus, imbalance, state)

        run(HahnelBook2021(price_rule=Inspecting(), max_rounds=3), synthetic_economy, seed=0)
        assert len(seen) == 3
        assert all(base is None for round_of_bases in seen for base in round_of_bases)

    def test_a_supplied_state_is_not_the_array_the_rule_is_handed(self, synthetic_economy):
        supplied = np.full(synthetic_economy.n_commodities, 0.2)
        seen = []

        class Inspecting(RecordingRule):
            def __call__(self, price, surplus, imbalance, state):
                seen.append(np.shares_memory(state, supplied))
                return super().__call__(price, surplus, imbalance, state)

        run(
            HahnelBook2021(price_rule=Inspecting(), initial_rule_state=supplied, max_rounds=2),
            synthetic_economy,
            seed=0,
        )
        assert seen == [False, False]

    @pytest.mark.parametrize("argument", RULE_ARGUMENTS)
    def test_writing_through_an_arguments_base_changes_nothing(
        self, synthetic_economy, argument
    ):
        scribbled = run(
            HahnelBook2021(price_rule=scribbling_through_the_base_of(argument)),
            synthetic_economy,
            seed=0,
        )
        assert_the_same_run(scribbled, self.honest_run(synthetic_economy))

    def test_a_rule_that_rewrites_its_returned_buffers_changes_nothing(self, synthetic_economy):
        """Every round, the plans of every round, and the verdict, as an honest run has them."""
        reusing = run(
            HahnelBook2021(price_rule=BufferReusingRule(), record_trajectory=True),
            synthetic_economy,
            seed=0,
        )
        assert_the_same_run(reusing, self.honest_run(synthetic_economy, record_trajectory=True))

    def test_each_round_is_stepped_with_the_state_returned_not_the_buffer_after(
        self, synthetic_economy
    ):
        rule = BufferReusingRule()
        run(HahnelBook2021(price_rule=rule), synthetic_economy, seed=0)
        honest = RecordingRule()
        run(HahnelBook2021(price_rule=honest), synthetic_economy, seed=0)
        assert len(rule.handed_state) == len(honest.state) > 2
        for number, (handed, expected) in enumerate(zip(rule.handed_state, honest.state)):
            np.testing.assert_array_equal(handed, expected, err_msg=f"round {number + 1}")
            assert not np.any(handed == BufferReusingRule.SCRIBBLE_STATE)

    def test_a_rule_that_reuses_its_output_buffer_files_the_price_it_proposed_at(
        self, synthetic_economy
    ):
        """The plan's price is the price the last round's proposals were made at."""
        rule = BufferReusingRule()
        result = run(HahnelBook2021(price_rule=rule), synthetic_economy, seed=0)

        assert len(rule.handed_price) == result.summary.rounds
        np.testing.assert_array_equal(
            result.plan.valuation[INDICATIVE_PRICE], rule.handed_price[-1]
        )

    def test_the_rule_writing_to_its_buffers_after_the_run_moves_no_number(
        self, synthetic_economy
    ):
        """The board holds a price and a state of its own, not the buffers the rule handed it."""
        rule = BufferReusingRule()
        result = run(HahnelBook2021(price_rule=rule), synthetic_economy, seed=0)
        filed = {
            key: np.array(result.plan.valuation[key], copy=True)
            for key in (INDICATIVE_PRICE, NEXT_INDICATIVE_PRICE)
        }
        filed_state = np.array(result.plan.extra[PRICE_RULE_STATE], copy=True)

        rule.price_buffer[:] = 0.0
        rule.state_buffer[:] = 0.0
        for key, value in filed.items():
            np.testing.assert_array_equal(result.plan.valuation[key], value)
            assert value.max() > 0.0
        np.testing.assert_array_equal(result.plan.extra[PRICE_RULE_STATE], filed_state)
        assert filed_state.max() > 0.0


class TestStatelessAdapter:
    """``stateless`` turns a three-argument price function into a rule with no state to carry."""

    def test_the_state_is_zero_per_commodity(self):
        state = stateless(proportional).initial_state(5)
        assert isinstance(state, np.ndarray)
        assert state.dtype == np.float64
        np.testing.assert_array_equal(state, np.zeros(5))

    def test_one_call_is_the_function_and_the_state_unchanged(self):
        price = np.array([700.0, 650.0, 720.0])
        surplus = np.array([1.0, -2.0, 0.0])
        imbalance = np.array([0.3, 0.1, 0.0])
        state = np.array([0.0, 0.5, -1.0])
        next_price, next_state = stateless(proportional)(price, surplus, imbalance, state)
        np.testing.assert_array_equal(next_price, proportional(price, surplus, imbalance))
        np.testing.assert_array_equal(next_state, state)

    def test_a_run_moves_the_price_as_the_function_does(self, synthetic_economy):
        handed = []

        def recording(price, surplus, imbalance):
            handed.append((price.copy(), surplus.copy(), imbalance.copy()))
            return proportional(price, surplus, imbalance)

        result = run(
            HahnelBook2021(price_rule=stateless(recording), max_rounds=6, record_trajectory=True),
            synthetic_economy,
            seed=0,
        )
        assert len(handed) == 6
        for plan, (price, surplus, imbalance) in zip(result.summary.trajectory, handed):
            np.testing.assert_array_equal(plan.valuation[INDICATIVE_PRICE], price)
            np.testing.assert_array_equal(
                plan.valuation[NEXT_INDICATIVE_PRICE], proportional(price, surplus, imbalance)
            )
            np.testing.assert_array_equal(
                plan.extra[PRICE_RULE_STATE], np.zeros(synthetic_economy.n_commodities)
            )

    def test_it_is_the_same_run_as_the_rule_written_out(self, synthetic_economy):
        class WrittenOut:
            def initial_state(self, n_commodities):
                return np.zeros(n_commodities)

            def __call__(self, price, surplus, imbalance, state):
                return proportional(price, surplus, imbalance), state

        adapted = run(
            HahnelBook2021(price_rule=stateless(proportional), max_rounds=40),
            synthetic_economy,
            seed=0,
        )
        written = run(
            HahnelBook2021(price_rule=WrittenOut(), max_rounds=40), synthetic_economy, seed=0
        )
        assert_the_same_run(adapted, written)

    def test_it_is_a_dataclass_holding_the_function_rather_than_a_closure(self):
        rule = stateless(proportional)
        assert isinstance(rule, StatelessPriceRule)
        assert dataclasses.is_dataclass(rule)
        assert [field.name for field in dataclasses.fields(rule)] == ["price_function"]
        assert rule.price_function is proportional

    def test_it_survives_pickling_when_the_function_does(self):
        rule = pickle.loads(pickle.dumps(stateless(proportional)))
        price = np.array([700.0, 650.0])
        surplus = np.array([1.0, -1.0])
        imbalance = np.array([0.2, 0.4])
        next_price, _ = rule(price, surplus, imbalance, rule.initial_state(2))
        np.testing.assert_array_equal(next_price, proportional(price, surplus, imbalance))


class TestConfigurationRecordsTheRule:
    """What a run configuration document says about the price rule a run used."""

    @pytest.fixture
    def economy(self):
        return synthetic.build_economy()

    def test_the_default_records_no_rule(self, economy):
        document = run_configuration(HahnelBook2021(), economy, seed=0)
        assert document.procedure["parameters"]["price_rule"] is None

    def test_the_programs_rule_is_recorded_as_the_librarys(self, economy):
        document = run_configuration(HahnelBook2021(price_rule=book_2021_rule), economy, seed=0)
        rule = document.procedure["parameters"]["price_rule"]
        assert rule["kind"] == "library"
        assert rule["module"] == BOOK_MODULE
        assert rule["qualname"] == "Book2021Rule"
        assert rule["parameters"] == {}
        assert rule["source_digest"] == document.procedure["source_digest"]

    def test_a_wrapped_researcher_function_is_recorded_as_undeclared_inside_the_wrapper(
        self, economy
    ):
        document = run_configuration(
            HahnelBook2021(price_rule=stateless(proportional)), economy, seed=0
        )
        rule = document.procedure["parameters"]["price_rule"]
        assert rule["kind"] == "library"
        assert rule["module"] == COUNCILS_MODULE
        assert rule["qualname"] == "StatelessPriceRule"
        assert rule["parameters"] == {
            "price_function": {"kind": "researcher", "declared_origin": None, "parameters": None}
        }

    def test_a_wrapped_library_function_is_pinned_inside_the_wrapper(self, economy):
        document = run_configuration(
            HahnelBook2021(price_rule=stateless(_relative_imbalance)), economy, seed=0
        )
        wrapped = document.procedure["parameters"]["price_rule"]["parameters"]["price_function"]
        assert wrapped["kind"] == "library"
        assert wrapped["module"] == COUNCILS_MODULE
        assert wrapped["qualname"] == "_relative_imbalance"

    def test_the_document_writes_as_json(self, economy, tmp_path):
        run_configuration(
            HahnelBook2021(price_rule=stateless(proportional)), economy, seed=0
        ).to_json(tmp_path / "configuration.json")


@pytest.mark.slow
@pytest.mark.skipif(not dep1ex_available(1), reason="dep1ex01 archive not available")
class TestDep1ex01:
    def test_the_plan_reproduces_its_own_production_function(self, dep1ex01_economy):
        plan = run(HahnelBook2021(), dep1ex01_economy, seed=0).plan
        np.testing.assert_allclose(
            np.asarray(plan.output),
            output_from_the_production_function(dep1ex01_economy, plan),
            rtol=1e-9,
            atol=0,
        )

    def test_effort_matches_the_upstream_closed_form(self, dep1ex01_economy):
        model = model_of(dep1ex01_economy)
        price = np.full(dep1ex01_economy.n_commodities, 700.0)
        _, effort, _ = model._propose(price)

        _, expected_effort = upstream_output_and_effort(dep1ex01_economy, price)
        np.testing.assert_allclose(effort, expected_effort, rtol=1e-12, atol=0)

    def test_the_public_good_imbalance_is_the_one_the_mechanism_measured(
        self, dep1ex01_economy
    ):
        rule = RecordingRule()
        result = run(HahnelBook2021(price_rule=rule), dep1ex01_economy, seed=0)
        public = synthetic.kind_labels(dep1ex01_economy) == hahnel.PUBLIC_GOOD

        rebuilt = imbalance_rebuilt_from(dep1ex01_economy, result.plan)
        np.testing.assert_allclose(
            rebuilt[public], rule.imbalance[-1][public], rtol=1e-12, atol=0
        )
        assert rebuilt[public].max() > 0.01

    def test_shared_use_is_the_consumer_demand_of_the_public_goods(self, dep1ex01_economy):
        plan = run(HahnelBook2021(), dep1ex01_economy, seed=0).plan
        public = synthetic.kind_labels(dep1ex01_economy) == hahnel.PUBLIC_GOOD
        assert int(public.sum()) == 100
        expected = np.where(public, np.asarray(plan.extra[CONSUMER_DEMAND]), 0.0)
        assert np.asarray(plan.shared_use).tobytes() == expected.tobytes()


def uneven_price(economy):
    """A price vector whose commodities do not all cost the same.

    A flat price hides every term that only shows when two commodities are priced apart.
    """
    return 100.0 + 800.0 * np.arange(economy.n_commodities, dtype=np.float64) / (
        economy.n_commodities
    )


def stated_bundle(economy, price):
    """Consumer councils' stated demand at ``price``: row per council, column per exponent.

    ``demand[i, j] = entitlement[i] * utility_exponent[i, j] / (total_exponent[i] * paid[j])``,
    where ``paid[j]`` is the listed price of the commodity column ``j`` names, divided by the
    number of consumer units when that commodity is a public good and left whole otherwise.

    Written out from the rule rather than read off the prefab, so that a prefab which priced a
    column differently would not also move the expectation.
    """
    entitlement = np.asarray(economy.consumer_extra["entitlement"])
    exponent = np.asarray(economy.consumer_extra["utility_exponent"])
    columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
    public = synthetic.kind_labels(economy)[columns] == hahnel.PUBLIC_GOOD
    listed = np.asarray(price)[columns]
    paid = np.where(public, listed / economy.n_consumers, listed)
    return (entitlement[:, None] * exponent) / (
        exponent.sum(axis=1)[:, None] * paid[None, :]
    )


def stated_bundle_at_a_shared_entitlement(economy, price):
    """``stated_bundle`` with every consumer unit spending the mean entitlement.

    On an economy that entitles every unit to the same amount this equals ``stated_bundle``,
    which is what makes the distinction between the two invisible there.
    """
    entitlement = np.asarray(economy.consumer_extra["entitlement"])
    exponent = np.asarray(economy.consumer_extra["utility_exponent"])
    columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
    public = synthetic.kind_labels(economy)[columns] == hahnel.PUBLIC_GOOD
    listed = np.asarray(price)[columns]
    paid = np.where(public, listed / economy.n_consumers, listed)
    return (entitlement.mean() * exponent) / (
        exponent.sum(axis=1)[:, None] * paid[None, :]
    )


def stated_quantity_of(economy, price, commodity):
    """What each consumer unit states for one commodity, written out from the rule.

    ``entitlement[i] * utility_exponent[i, j] / (total_exponent[i] * price[commodity])``, where
    ``j`` is the utility-exponent column naming the commodity; a private good pays the listed
    price, so nothing here is divided over the consumer units. The commodity has to be named by
    exactly one column for the answer to be that column's own quantity.

    The expectation is keyed by commodity rather than by column position, so it stays put when
    the columns are reordered.
    """
    columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
    at = np.flatnonzero(columns == commodity)
    assert at.size == 1, f"commodity {commodity} is named by {at.size} columns, expected 1"
    entitlement = np.asarray(economy.consumer_extra["entitlement"])
    exponent = np.asarray(economy.consumer_extra["utility_exponent"])
    return entitlement * exponent[:, at[0]] / (
        exponent.sum(axis=1) * np.asarray(price)[commodity]
    )


def assert_consumption_columns_are_paired_with_their_labels(economy, plan, price):
    """Check column ``j`` of the consumption block against ``consumption_commodity[j]``.

    The contract of the block is a pairing: column ``j`` holds what the consumer units state
    for the commodity the label at ``j`` names. Reordering one side without the other keeps
    both sides individually correct as sets, so only a column-by-column comparison sees it.
    """
    columns = np.asarray(plan.consumption_commodity)
    consumption = np.asarray(plan.consumption)
    assert columns.size > 0
    assert consumption.shape == (economy.n_consumers, columns.size)
    for at, commodity in enumerate(columns.tolist()):
        np.testing.assert_array_equal(
            consumption[:, at],
            stated_quantity_of(economy, price, commodity),
            err_msg=f"consumption column {at} does not hold commodity {commodity}",
        )


def commodity_demand_rebuilt_from(economy, plan, price):
    """Demand per commodity: the units' input use plus the councils' stated consumption.

    A public good's stated demand counts once for the whole society, so its column total is
    divided by the number of consumer units before it is scattered onto its commodity. Every
    other column is scattered whole, whatever kind its commodity is.
    """
    columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
    public = synthetic.kind_labels(economy)[columns] == hahnel.PUBLIC_GOOD
    stated = stated_bundle(economy, price).sum(axis=0)
    shared = np.where(public, stated / economy.n_consumers, stated)
    return plan.total_input_use(economy) + np.bincount(
        columns, weights=shared, minlength=economy.n_commodities
    )


def second_round_of(economy):
    """``(plan, price, surplus)`` of the second round, whose price is no longer flat."""
    rule = RecordingRule()
    result = run(
        HahnelBook2021(price_rule=rule, max_rounds=2, record_trajectory=True),
        economy,
        seed=0,
    )
    assert len(result.summary.trajectory) == 2
    price, surplus = rule.price[-1], rule.surplus[-1]
    assert np.unique(price).size > 1
    return result.summary.trajectory[-1], price, surplus


class TestConsumptionBlockIsNotCopied:
    """``plan_of`` hands over the block the round produced rather than a copy of it.

    The block is ``f64[n_consumers, n_private_columns]``: 24 MB on dep1ex01, and the default
    configuration turns every round's state into a plan, so a copy here is a copy per round.
    """

    def test_the_plan_shares_the_state_consumption_block(self, synthetic_economy):
        model = model_of(synthetic_economy)
        state = model.step(model.initial_state(700.0))
        plan = model.plan_of(state)
        assert np.shares_memory(np.asarray(plan.consumption), state.consumption)

    def test_it_shares_when_the_private_columns_are_not_contiguous(self):
        """Non-contiguous columns are where a split by position would fall back to a copy."""
        economy = synthetic.build_permuted_economy()
        model = model_of(economy)
        state = model.step(model.initial_state(700.0))
        plan = model.plan_of(state)
        assert np.shares_memory(np.asarray(plan.consumption), state.consumption)

    def test_it_shares_when_a_column_is_neither_private_nor_public(self):
        economy = synthetic.build_economy_with_a_third_kind_column()
        model = model_of(economy)
        state = model.step(model.initial_state(700.0))
        plan = model.plan_of(state)
        assert np.shares_memory(np.asarray(plan.consumption), state.consumption)


class TestColumnsThatAreNeitherPrivateNorPublic:
    """A utility-exponent column names a commodity of any kind, and there are five kinds.

    A column on an intermediate good is priced at the listed price and counts into that
    commodity's demand, like a private-good column. It is a column of the plan's consumption
    block, which holds every column whose commodity is not a public good, so the material
    balance of the plan counts it; it stays out of ``shared_use``.
    """

    @pytest.fixture
    def third_kind_economy(self):
        return synthetic.build_economy_with_a_third_kind_column()

    @pytest.fixture
    def second_round(self, third_kind_economy):
        return second_round_of(third_kind_economy)

    def test_the_fixture_holds_a_column_of_each_of_the_three_cases(self, third_kind_economy):
        kinds = synthetic.kind_labels(third_kind_economy)
        columns = np.asarray(third_kind_economy.consumer_extra["utility_exponent_commodity"])
        column_kinds = set(kinds[columns].tolist())
        assert hahnel.PRIVATE_GOOD in column_kinds
        assert hahnel.PUBLIC_GOOD in column_kinds
        assert column_kinds - {hahnel.PRIVATE_GOOD, hahnel.PUBLIC_GOOD}

        private = np.flatnonzero(kinds[columns] == hahnel.PRIVATE_GOOD)
        assert private.tolist() != list(range(private.size))

    def test_the_surplus_accounts_for_every_column(self, third_kind_economy, second_round):
        """The demand the board measured is the one the three kinds of column add up to."""
        plan, price, surplus = second_round
        supply = plan.total_output(third_kind_economy) + np.asarray(
            third_kind_economy.endowment
        )
        np.testing.assert_array_equal(
            surplus,
            supply - commodity_demand_rebuilt_from(third_kind_economy, plan, price),
        )

    def test_the_third_kind_commodity_is_counted_whole(self, third_kind_economy, second_round):
        plan, price, surplus = second_round
        commodity = synthetic.THIRD_KIND_COMMODITY
        supply = plan.total_output(third_kind_economy) + np.asarray(
            third_kind_economy.endowment
        )
        demand = (supply - surplus)[commodity]

        columns = np.asarray(third_kind_economy.consumer_extra["utility_exponent_commodity"])
        stated = stated_bundle(third_kind_economy, price).sum(axis=0)
        from_the_councils = stated[columns == commodity].sum()
        from_the_units = plan.total_input_use(third_kind_economy)[commodity]

        assert from_the_councils > 0.0
        np.testing.assert_allclose(
            demand, from_the_units + from_the_councils, rtol=1e-12, atol=0
        )
        per_consumer_unit = (
            from_the_units + from_the_councils / third_kind_economy.n_consumers
        )
        assert not np.isclose(demand, per_consumer_unit, rtol=1e-9, atol=0)

    def test_the_public_columns_are_still_shared_over_the_consumer_units(
        self, third_kind_economy, second_round
    ):
        """A public-good column contributes its total divided by the number of consumer units.

        The value and the mask are both asserted: dividing over the consumer units is the only
        thing that separates a public-good column from the other two cases, so a check that
        did not also pin which commodities carry the divided total would pass on an
        implementation that divided the wrong ones.
        """
        plan, price, _ = second_round
        kinds = synthetic.kind_labels(third_kind_economy)
        columns = np.asarray(third_kind_economy.consumer_extra["utility_exponent_commodity"])
        public = np.flatnonzero(kinds[columns] == hahnel.PUBLIC_GOOD)
        stated = stated_bundle(third_kind_economy, price).sum(axis=0)

        expected = np.bincount(
            columns[public],
            weights=stated[public] / third_kind_economy.n_consumers,
            minlength=third_kind_economy.n_commodities,
        )
        assert expected[kinds == hahnel.PUBLIC_GOOD].min() > 0.0
        consumer_demand = np.asarray(plan.extra["consumer_demand"])
        np.testing.assert_array_equal(
            np.where(kinds == hahnel.PUBLIC_GOOD, consumer_demand, 0.0), expected
        )

    def test_the_private_columns_reach_consumer_demand_whole(
        self, third_kind_economy, second_round
    ):
        """A private-good column contributes its whole total, the one ``consumption`` holds."""
        plan, price, _ = second_round
        kinds = synthetic.kind_labels(third_kind_economy)
        columns = np.asarray(third_kind_economy.consumer_extra["utility_exponent_commodity"])
        private = np.flatnonzero(kinds[columns] == hahnel.PRIVATE_GOOD)
        stated = stated_bundle(third_kind_economy, price).sum(axis=0)

        expected = np.bincount(
            columns[private],
            weights=stated[private],
            minlength=third_kind_economy.n_commodities,
        )
        on_private = kinds == hahnel.PRIVATE_GOOD
        consumer_demand = np.asarray(plan.extra["consumer_demand"])
        assert expected[on_private].min() > 0.0
        np.testing.assert_allclose(
            consumer_demand[on_private], expected[on_private], rtol=1e-13, atol=0
        )
        np.testing.assert_array_equal(
            consumer_demand[on_private],
            plan.total_consumption(third_kind_economy)[on_private],
        )

    def test_the_third_kind_column_reaches_consumer_demand_whole(
        self, third_kind_economy, second_round
    ):
        """A column on a commodity of neither kind contributes its whole total, undivided."""
        plan, price, _ = second_round
        commodity = synthetic.THIRD_KIND_COMMODITY
        columns = np.asarray(third_kind_economy.consumer_extra["utility_exponent_commodity"])
        stated = stated_bundle(third_kind_economy, price).sum(axis=0)
        expected = stated[columns == commodity].sum()

        consumer_demand = np.asarray(plan.extra["consumer_demand"])
        assert expected > 0.0
        np.testing.assert_allclose(consumer_demand[commodity], expected, rtol=1e-13, atol=0)
        assert not np.isclose(
            consumer_demand[commodity],
            expected / third_kind_economy.n_consumers,
            rtol=1e-9,
            atol=0,
        )

    def test_input_use_and_consumer_demand_are_the_whole_of_demand(
        self, third_kind_economy, second_round
    ):
        """Supply minus those two is the surplus the board measured, so no column is missing
        from ``consumer_demand`` and none is counted twice."""
        plan, _, surplus = second_round
        supply = plan.total_output(third_kind_economy) + np.asarray(
            third_kind_economy.endowment
        )
        rebuilt = supply - (
            plan.total_input_use(third_kind_economy)
            + np.asarray(plan.extra["consumer_demand"])
        )
        np.testing.assert_array_equal(rebuilt, surplus)

    def test_the_plan_carries_consumer_demand_and_not_a_public_good_key(
        self, third_kind_economy, second_round
    ):
        plan, _, _ = second_round
        assert "consumer_demand" in plan.extra
        assert "public_demand" not in plan.extra

    def test_the_column_is_in_the_consumption_block(self, third_kind_economy, second_round):
        plan, price, _ = second_round
        columns = np.asarray(plan.consumption_commodity)
        assert synthetic.THIRD_KIND_COMMODITY in columns.tolist()
        exponent_columns = np.asarray(
            third_kind_economy.consumer_extra["utility_exponent_commodity"]
        )
        kinds = synthetic.kind_labels(third_kind_economy)
        np.testing.assert_array_equal(
            columns, exponent_columns[kinds[exponent_columns] != hahnel.PUBLIC_GOOD]
        )
        assert_consumption_columns_are_paired_with_their_labels(
            third_kind_economy, plan, price
        )
        plan.validate(third_kind_economy)

    def test_shared_use_stays_zero_on_the_third_kind_commodity(
        self, third_kind_economy, second_round
    ):
        plan, _, _ = second_round
        assert np.asarray(plan.shared_use)[synthetic.THIRD_KIND_COMMODITY] == 0.0
        assert np.asarray(plan.extra[CONSUMER_DEMAND])[synthetic.THIRD_KIND_COMMODITY] > 0.0

    def test_the_consumption_block_is_the_non_public_columns_of_the_stated_bundle(
        self, third_kind_economy, second_round
    ):
        plan, price, _ = second_round
        kinds = synthetic.kind_labels(third_kind_economy)
        columns = np.asarray(third_kind_economy.consumer_extra["utility_exponent_commodity"])
        not_public = np.flatnonzero(kinds[columns] != hahnel.PUBLIC_GOOD)
        np.testing.assert_array_equal(
            np.asarray(plan.consumption),
            stated_bundle(third_kind_economy, price)[:, not_public],
        )

    def test_a_run_over_the_three_cases_converges(self, third_kind_economy):
        result = run(HahnelBook2021(), third_kind_economy, seed=0)
        assert result.summary.converged is True
        result.plan.validate(third_kind_economy)


class TestPrivateColumnsOutOfCommodityOrder:
    """The consumption block is paired with its labels one column at a time.

    Column ``j`` of ``Plan.consumption`` holds what the consumer units state for the commodity
    ``consumption_commodity[j]`` names. The other economies here name the private commodities
    in ascending order, as dep1ex does, which makes the labels equal to the private goods in
    ascending order and makes sorting either side a no-op. This economy
    names them 2, 0, 1.

    It also entitles each consumer unit to a different amount, so a stated bundle built from
    the mean entitlement rather than each unit's own is a different bundle here.
    """

    @pytest.fixture
    def economy(self):
        return synthetic.build_economy_with_unordered_private_columns()

    @pytest.fixture
    def second_round(self, economy):
        """``(plan, price)`` of the second round, whose price is no longer flat."""
        plan, price, _ = second_round_of(economy)
        return plan, price

    def test_the_fixture_is_out_of_order_and_unevenly_entitled(self, economy, second_round):
        _, price = second_round
        kinds = synthetic.kind_labels(economy)
        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        private = columns[kinds[columns] == hahnel.PRIVATE_GOOD]
        assert private.tolist() != sorted(private.tolist())

        entitlement = np.asarray(economy.consumer_extra["entitlement"])
        assert np.unique(entitlement).size == entitlement.size

        # How far the mean-entitlement bundle sits from the per-unit one, which is the margin
        # the expectations below hold over an implementation that spent the mean.
        bundle = stated_bundle(economy, price)
        shared = stated_bundle_at_a_shared_entitlement(economy, price)
        assert np.max(np.abs(bundle - shared) / np.abs(bundle)) > 0.05

    def test_the_labels_are_the_private_columns_in_column_order(self, economy, second_round):
        plan, _ = second_round
        kinds = synthetic.kind_labels(economy)
        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        private = columns[kinds[columns] == hahnel.PRIVATE_GOOD]
        np.testing.assert_array_equal(plan.consumption_commodity, private)
        assert np.asarray(plan.consumption_commodity).tolist() != np.asarray(
            np.flatnonzero(synthetic.kind_labels(economy) == hahnel.PRIVATE_GOOD)
        ).tolist()
        plan.validate(economy)

    def test_each_consumption_column_holds_the_commodity_its_label_names(
        self, economy, second_round
    ):
        plan, price = second_round
        assert_consumption_columns_are_paired_with_their_labels(economy, plan, price)

    def test_consumer_demand_spends_each_unit_own_entitlement(self, economy, second_round):
        """Per commodity, so that the private columns and the rest are both accounted for."""
        plan, price = second_round
        kinds = synthetic.kind_labels(economy)
        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        public = kinds[columns] == hahnel.PUBLIC_GOOD
        stated = stated_bundle(economy, price).sum(axis=0)
        shared = np.where(public, stated / economy.n_consumers, stated)
        expected = np.bincount(columns, weights=shared, minlength=economy.n_commodities)

        assert expected[np.unique(columns)].min() > 0.0
        np.testing.assert_allclose(
            np.asarray(plan.extra["consumer_demand"]), expected, rtol=1e-13, atol=0
        )

    def test_a_run_over_the_unordered_columns_converges(self, economy):
        result = run(HahnelBook2021(), economy, seed=0)
        assert result.summary.converged is True
        result.plan.validate(economy)
        assert_consumption_columns_are_paired_with_their_labels(
            economy, result.plan, result.plan.valuation[INDICATIVE_PRICE]
        )


class TestStatedDemandSplit:
    """``_demand`` returns the public-good columns and the rest as two separate blocks.

    Per column is the only place the public-good price is visible. A council facing a public
    good states ``n_consumers`` times as much at ``price / n_consumers``, and the aggregation
    divides that column's total by ``n_consumers`` again, so the two halves of the rule cancel
    in every commodity-level number the plan reports.

    The tests below are therefore the whole of the coverage of the public-good pricing rule,
    and they reach it through the private method ``_demand`` because no public surface exposes
    it. Changing that method's signature rewrites the only check the rule has.
    """

    @pytest.fixture
    def model_and_price(self):
        economy = synthetic.build_economy_with_a_third_kind_column()
        return model_of(economy), economy, uneven_price(economy)

    def test_the_two_blocks_are_the_stated_bundle_split_by_hahnel_kind(
        self, model_and_price
    ):
        model, economy, price = model_and_price
        consumption_block, public_block = model._demand(price)

        kinds = synthetic.kind_labels(economy)
        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        not_public = np.flatnonzero(kinds[columns] != hahnel.PUBLIC_GOOD)
        public = np.flatnonzero(kinds[columns] == hahnel.PUBLIC_GOOD)
        expected = stated_bundle(economy, price)

        np.testing.assert_array_equal(consumption_block, expected[:, not_public])
        np.testing.assert_array_equal(public_block, expected[:, public])

    def test_a_public_good_column_pays_the_listed_price_per_consumer_unit(
        self, model_and_price
    ):
        model, economy, price = model_and_price
        _, public_block = model._demand(price)

        kinds = synthetic.kind_labels(economy)
        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        public = np.flatnonzero(kinds[columns] == hahnel.PUBLIC_GOOD)

        entitlement = np.asarray(economy.consumer_extra["entitlement"])
        exponent = np.asarray(economy.consumer_extra["utility_exponent"])
        paid = price[columns[public[0]]] / economy.n_consumers
        expected = entitlement * exponent[:, public[0]] / (exponent.sum(axis=1) * paid)
        np.testing.assert_array_equal(public_block[:, 0], expected)

    def test_a_column_that_is_neither_pays_the_whole_listed_price(self, model_and_price):
        model, economy, price = model_and_price
        consumption_block, _ = model._demand(price)

        kinds = synthetic.kind_labels(economy)
        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        not_public = np.flatnonzero(kinds[columns] != hahnel.PUBLIC_GOOD)
        at = int(np.flatnonzero(columns[not_public] == synthetic.THIRD_KIND_COMMODITY)[0])

        entitlement = np.asarray(economy.consumer_extra["entitlement"])
        exponent = np.asarray(economy.consumer_extra["utility_exponent"])
        paid = price[synthetic.THIRD_KIND_COMMODITY]
        expected = entitlement * exponent[:, not_public[at]] / (exponent.sum(axis=1) * paid)
        np.testing.assert_array_equal(consumption_block[:, at], expected)

    def test_a_private_good_column_pays_the_whole_listed_price(self, model_and_price):
        model, economy, price = model_and_price
        private_block, _ = model._demand(price)

        kinds = synthetic.kind_labels(economy)
        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        private = np.flatnonzero(kinds[columns] == hahnel.PRIVATE_GOOD)

        entitlement = np.asarray(economy.consumer_extra["entitlement"])
        exponent = np.asarray(economy.consumer_extra["utility_exponent"])
        paid = price[columns[private[0]]]
        expected = entitlement * exponent[:, private[0]] / (exponent.sum(axis=1) * paid)
        np.testing.assert_array_equal(private_block[:, 0], expected)


class TestThePlanIsAStatedPlan:
    """``consumption`` here is what the consumer councils asked for at the last price.

    It is not an allocation: the councils' stated bundles are what the price rule iterates on,
    and the run stops on a relative imbalance threshold rather than on a balance, so supply and
    the stated demand still differ by up to that threshold. Filing it as a plain ``Plan`` let a
    reader subtract it from a reference solution's allocated consumption and read the gap as
    economics.
    """

    def test_the_prefab_files_its_plan_as_a_stated_plan(self, synthetic_economy):
        result = run(HahnelBook2021(max_rounds=2), synthetic_economy, seed=0)
        assert isinstance(result.plan, StatedPlan)

    def test_the_council_model_files_the_same_identity(self, synthetic_economy):
        model = model_of(synthetic_economy)
        stepped = model.step(model.initial_state(700.0))
        assert isinstance(model.plan_of(stepped), StatedPlan)

    def test_a_state_that_was_never_stepped_has_no_plan(self, synthetic_economy):
        """``initial_state`` carries a price and no proposals, so there is nothing to file.

        ``iterate`` runs at least one round, so it never hands that state to ``plan_of``.
        Building one from it directly is refused rather than answered with a plan whose
        fields are all empty.
        """
        model = model_of(synthetic_economy)
        with pytest.raises(SchemaError, match="consumption"):
            model.plan_of(model.initial_state(700.0))

    def test_it_is_not_an_allocated_plan(self, synthetic_economy):
        result = run(HahnelBook2021(max_rounds=2), synthetic_economy, seed=0)
        assert not isinstance(result.plan, AllocatedPlan)

    def test_it_still_carries_every_fixed_field(self, synthetic_economy):
        result = run(HahnelBook2021(max_rounds=2), synthetic_economy, seed=0)
        assert result.plan.absent_fields == ()
        result.plan.validate(synthetic_economy)
