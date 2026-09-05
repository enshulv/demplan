"""The 2020 slides prefab, measured against the numpy reference in ``research/bench``.

Every expected number here is produced by running ``endowment.py``, which is an independent
implementation of the same price rule over a different data layout. The two published
constants that appear literally are the 2020 slides' own figures for the five dep1ex
experiments; they enter through the reference run, not through the prefab.
"""

from __future__ import annotations

import dataclasses
import gc
import statistics
import time

import numpy as np
import pytest

from cyberstride import (
    INDICATIVE_PRICE,
    CommodityKind,
    TechnologyKind,
    check_determinism,
    iterate,
    run,
)
from cyberstride.prefabs import HahnelSlides2020
from cyberstride.prefabs.hahnel_2020_slides import (
    CouncilModel,
    _relative_imbalance,
    slides_2020_rule,
)
from cyberstride.tools import segment_sum, unit_of_input
from reference import synthetic
from reference.dep1ex_numpy import (
    Dep1exLayout,
    economy_from_repro,
    parse_dep1ex,
    reference_first_round,
    reference_run,
    unified_price,
)
from reference.paths import dep1ex_available, dep1ex_path

DEP1EX_COUNT = 5
COLD_5_PERCENT_ROUNDS = [13, 13, 13, 14, 14]
COLD_3_PERCENT_MEAN = 22.8
TIMING_ALLOWANCE = 1.3

SYNTHETIC_LAYOUT = Dep1exLayout(
    n_priv=synthetic.N_PER_CLASS, n_pub=synthetic.N_PER_CLASS, n_goods=synthetic.N_PER_CLASS
)


@pytest.fixture
def synthetic_reference_rounds(synthetic_reference_inputs):
    """``endowment.run`` on the synthetic economy: ``(rounds, prices, worst_percent)``."""
    wc, cc, _, endowment = synthetic_reference_inputs
    return reference_run(wc, cc, SYNTHETIC_LAYOUT, threshold=5.0, endowment_per_commodity=endowment)


class TestSyntheticEconomy:
    def test_it_converges(self, synthetic_economy):
        result = run(HahnelSlides2020(), synthetic_economy, seed=0)
        assert result.summary.converged is True
        assert result.summary.rounds is not None
        assert result.summary.rounds < HahnelSlides2020().max_rounds

    def test_the_fixture_exercises_the_effort_scale_term(self, synthetic_economy):
        """``c * log(effort_s)`` vanishes from the closed form when every ``effort_s`` is 1,
        which would leave the differential tests below blind to that term."""
        effort_s = np.asarray(synthetic_economy.unit_extra["effort_s"])
        assert np.count_nonzero(np.log(effort_s)) > 0

    def test_round_count_matches_the_reference(self, synthetic_economy, synthetic_reference_rounds):
        expected_rounds, _, _ = synthetic_reference_rounds
        result = run(HahnelSlides2020(), synthetic_economy, seed=0)
        assert result.summary.rounds == expected_rounds

    def test_final_prices_match_the_reference(self, synthetic_economy, synthetic_reference_rounds):
        _, expected_prices, _ = synthetic_reference_rounds
        result = run(HahnelSlides2020(), synthetic_economy, seed=0)
        np.testing.assert_allclose(
            result.plan.valuation[INDICATIVE_PRICE],
            unified_price(expected_prices, SYNTHETIC_LAYOUT),
            rtol=1e-9,
            atol=0,
        )

    def test_the_plan_satisfies_the_schema(self, synthetic_economy):
        result = run(HahnelSlides2020(), synthetic_economy, seed=0)
        result.plan.validate(synthetic_economy)

    def test_material_balance_at_the_reported_threshold(self, synthetic_economy):
        """Public goods sit at zero here by construction; the reference run covers them."""
        procedure = HahnelSlides2020()
        plan = run(procedure, synthetic_economy, seed=0).plan
        supply = plan.total_output(synthetic_economy) + np.asarray(synthetic_economy.endowment)
        demand = (
            plan.total_input_use(synthetic_economy)
            + plan.total_consumption(synthetic_economy)
            + np.asarray(plan.provision)
        )
        total = supply + demand
        imbalance = np.where(total > 0, np.abs(2 * (supply - demand)) / np.where(total > 0, total, 1.0), 0.0)
        assert imbalance.max() * 100 < procedure.threshold_pct

    def test_consumption_columns_are_the_private_goods(self, synthetic_economy):
        plan = run(HahnelSlides2020(), synthetic_economy, seed=0).plan
        kinds = np.asarray(synthetic_economy.commodity_kind)
        columns = np.asarray(plan.consumption_commodity)
        assert np.all(kinds[columns] == CommodityKind.PRIVATE_GOOD)
        np.testing.assert_array_equal(
            columns, synthetic_economy.commodities_of_kind(CommodityKind.PRIVATE_GOOD)
        )
        assert plan.consumption.shape == (synthetic_economy.n_consumers, columns.shape[0])
        assert np.all(plan.consumption > 0.0)

    def test_provision_is_confined_to_public_goods(self, synthetic_economy):
        plan = run(HahnelSlides2020(), synthetic_economy, seed=0).plan
        kinds = np.asarray(synthetic_economy.commodity_kind)
        public = kinds == CommodityKind.PUBLIC_GOOD
        provision = np.asarray(plan.provision)
        assert np.all(provision[public] > 0.0)
        assert provision[~public].sum() == 0.0
        np.testing.assert_allclose(
            provision[public], plan.total_output(synthetic_economy)[public]
        )

    def test_the_reported_price_is_the_one_the_proposals_used(self, synthetic_economy):
        """The published round count is reached at the price of that round, before adjustment."""
        procedure = HahnelSlides2020(record_trajectory=True)
        result = run(procedure, synthetic_economy, seed=0)
        one_round_less = HahnelSlides2020(max_rounds=result.summary.rounds - 1)
        earlier = run(one_round_less, synthetic_economy, seed=0)
        assert earlier.summary.converged is False
        assert not np.allclose(
            earlier.plan.valuation[INDICATIVE_PRICE], result.plan.valuation[INDICATIVE_PRICE]
        )

    def test_trajectory_is_off_by_default(self, synthetic_economy):
        result = run(HahnelSlides2020(), synthetic_economy, seed=0)
        assert result.summary.trajectory is None

    def test_trajectory_has_one_plan_per_round(self, synthetic_economy):
        result = run(HahnelSlides2020(record_trajectory=True), synthetic_economy, seed=0)
        assert result.summary.trajectory is not None
        assert len(result.summary.trajectory) == result.summary.rounds
        for plan in result.summary.trajectory:
            plan.validate(synthetic_economy)

    def test_the_returned_plan_is_the_last_round_recorded_or_not(self, synthetic_economy):
        """The plan a run answers with is the round that stopped it, either way it is driven."""
        recorded = run(HahnelSlides2020(record_trajectory=True), synthetic_economy, seed=0)
        quiet = run(HahnelSlides2020(), synthetic_economy, seed=0)
        last = recorded.summary.trajectory[-1]
        assert len(recorded.summary.trajectory) > 1

        for field in ("output", "input_use", "consumption", "consumption_commodity", "provision"):
            np.testing.assert_array_equal(getattr(recorded.plan, field), getattr(last, field))
            np.testing.assert_array_equal(getattr(quiet.plan, field), getattr(last, field))
        np.testing.assert_array_equal(
            recorded.plan.valuation[INDICATIVE_PRICE], last.valuation[INDICATIVE_PRICE]
        )
        np.testing.assert_array_equal(
            quiet.plan.valuation[INDICATIVE_PRICE], last.valuation[INDICATIVE_PRICE]
        )
        for key in ("effort", "consumer_demand"):
            np.testing.assert_array_equal(quiet.plan.extra[key], last.extra[key])

    def test_the_first_trajectory_entry_is_priced_at_the_initial_price(self, synthetic_economy):
        procedure = HahnelSlides2020(record_trajectory=True, initial_price=640.0)
        result = run(procedure, synthetic_economy, seed=0)
        np.testing.assert_array_equal(
            result.summary.trajectory[0].valuation[INDICATIVE_PRICE],
            np.full(synthetic_economy.n_commodities, 640.0),
        )

    def test_a_round_cap_stops_the_loop(self, synthetic_economy):
        result = run(HahnelSlides2020(max_rounds=3), synthetic_economy, seed=0)
        assert result.summary.rounds == 3
        assert result.summary.converged is False

    def test_a_tighter_threshold_needs_more_rounds(self, synthetic_economy):
        loose = run(HahnelSlides2020(threshold_pct=5.0), synthetic_economy, seed=0)
        tight = run(HahnelSlides2020(threshold_pct=3.0), synthetic_economy, seed=0)
        assert tight.summary.rounds > loose.summary.rounds

    def test_the_seed_does_not_change_the_result(self, synthetic_economy):
        first = run(HahnelSlides2020(), synthetic_economy, seed=0).plan
        second = run(HahnelSlides2020(), synthetic_economy, seed=2**63).plan
        np.testing.assert_array_equal(first.output, second.output)

    def test_determinism_report(self, synthetic_economy):
        report = check_determinism(HahnelSlides2020(), synthetic_economy, 0, n=3)
        assert report.identical is True
        assert report.differing_fields == []


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
    """``slides_2020_rule`` that keeps the imbalance vector of every round it is handed."""

    def __init__(self):
        self.imbalance = []

    def __call__(self, price, surplus, imbalance):
        self.imbalance.append(np.asarray(imbalance).copy())
        return slides_2020_rule(price, surplus, imbalance)


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


class TestTechnologyGuard:
    """The closed form is Cobb-Douglas; on a Leontief unit it would be a different theory."""

    def test_an_all_leontief_economy_is_refused(self, synthetic_economy):
        leontief = dataclasses.replace(
            synthetic_economy,
            technology_kind=np.full(
                synthetic_economy.n_units, TechnologyKind.LEONTIEF, dtype=np.int8
            ),
        )
        with pytest.raises(ValueError, match="Cobb-Douglas"):
            run(HahnelSlides2020(), leontief, seed=0)

    def test_one_leontief_unit_is_enough_and_the_message_names_it(self, synthetic_economy):
        kinds = np.array(synthetic_economy.technology_kind, dtype=np.int8)
        kinds[2] = TechnologyKind.LEONTIEF
        mixed = dataclasses.replace(synthetic_economy, technology_kind=kinds)
        with pytest.raises(ValueError, match="unit 2"):
            run(HahnelSlides2020(), mixed, seed=0)


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
            run(HahnelSlides2020(), economy, seed=0)

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
            run(HahnelSlides2020(), economy, seed=0)

    def test_the_message_names_every_absent_key_at_once(self, synthetic_economy):
        economy = dataclasses.replace(synthetic_economy, unit_extra={})
        with pytest.raises(ValueError, match="effort_c.*effort_s.*effort_k"):
            run(HahnelSlides2020(), economy, seed=0)


class TestPermutedCommodityOrder:
    """The private goods are picked by ``commodity_kind``, not by where they sit in the table."""

    def test_the_fixture_does_not_put_the_private_goods_first(self):
        economy = synthetic.build_permuted_economy()
        kinds = np.asarray(economy.commodity_kind)
        assert kinds[0] != CommodityKind.PRIVATE_GOOD

        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        private_columns = np.flatnonzero(kinds[columns] == CommodityKind.PRIVATE_GOOD)
        assert private_columns.tolist() != list(range(private_columns.size))

    def test_the_consumption_columns_are_still_the_private_goods(self):
        economy = synthetic.build_permuted_economy()
        plan = run(HahnelSlides2020(), economy, seed=0).plan
        kinds = np.asarray(economy.commodity_kind)
        columns = np.asarray(plan.consumption_commodity)

        assert np.all(kinds[columns] == CommodityKind.PRIVATE_GOOD)
        np.testing.assert_array_equal(
            columns, economy.commodities_of_kind(CommodityKind.PRIVATE_GOOD)
        )
        plan.validate(economy)

    def test_the_provision_is_still_confined_to_the_public_goods(self):
        economy = synthetic.build_permuted_economy()
        plan = run(HahnelSlides2020(), economy, seed=0).plan
        public = np.asarray(economy.commodity_kind) == CommodityKind.PUBLIC_GOOD
        provision = np.asarray(plan.provision)
        assert np.all(provision[public] > 0.0)
        assert provision[~public].sum() == 0.0

    def test_renumbering_the_commodities_does_not_change_the_round_count(
        self, synthetic_economy
    ):
        permuted = synthetic.build_permuted_economy()
        assert (
            run(HahnelSlides2020(), permuted, seed=0).summary.rounds
            == run(HahnelSlides2020(), synthetic_economy, seed=0).summary.rounds
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
            result = run(HahnelSlides2020(), economy, seed=0)
        assert result.summary.converged is False

    def test_the_default_configuration_stops_at_the_non_finite_round(self, synthetic_economy):
        economy = with_a_negative_denominator(synthetic_economy)
        model = CouncilModel(economy, 5.0)
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
            quiet = run(HahnelSlides2020(), economy, seed=0)
            recorded = run(HahnelSlides2020(record_trajectory=True), economy, seed=0)
        assert quiet.summary.converged == recorded.summary.converged
        assert quiet.summary.rounds == recorded.summary.rounds


class TestPlanRecordsWhatTheMechanismChose:
    """Whatever the mechanism decided has to be readable back off the plan."""

    def test_the_plan_reproduces_its_own_production_function(self, synthetic_economy):
        plan = run(HahnelSlides2020(), synthetic_economy, seed=0).plan
        np.testing.assert_allclose(
            np.asarray(plan.output),
            output_from_the_production_function(synthetic_economy, plan),
            rtol=1e-9,
            atol=0,
        )

    def test_effort_matches_the_upstream_closed_form(self, synthetic_economy):
        model = CouncilModel(synthetic_economy, 5.0)
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
        model = CouncilModel(synthetic_economy, 5.0)
        price = 100.0 + 800.0 * np.arange(
            synthetic_economy.n_commodities, dtype=np.float64
        ) / synthetic_economy.n_commodities
        _, effort, _ = model._propose(price)

        _, expected_effort = upstream_output_and_effort(synthetic_economy, price)
        np.testing.assert_allclose(effort, expected_effort, rtol=1e-12, atol=0)

    def test_effort_is_one_positive_value_per_unit(self, synthetic_economy):
        plan = run(HahnelSlides2020(), synthetic_economy, seed=0).plan
        effort = np.asarray(plan.extra["effort"])
        assert effort.shape == (synthetic_economy.n_units,)
        assert effort.dtype == np.float64
        assert np.all(effort > 0.0)

    def test_dropping_effort_would_not_reproduce_the_output(self, synthetic_economy):
        """Without the effort factor the identity is off by a factor the tolerance rejects."""
        plan = run(HahnelSlides2020(), synthetic_economy, seed=0).plan
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
        result = run(HahnelSlides2020(price_rule=rule), synthetic_economy, seed=0)
        public = np.asarray(synthetic_economy.commodity_kind) == CommodityKind.PUBLIC_GOOD

        rebuilt = imbalance_rebuilt_from(synthetic_economy, result.plan)
        np.testing.assert_allclose(
            rebuilt[public], rule.imbalance[-1][public], rtol=1e-12, atol=0
        )
        assert rebuilt[public].max() > 0.0

    def test_consumer_demand_is_zero_where_no_column_names_the_commodity(
        self, synthetic_economy
    ):
        """No utility-exponent column names the commodity, so the councils ask for none of it."""
        plan = run(HahnelSlides2020(), synthetic_economy, seed=0).plan
        stated = np.asarray(plan.extra["consumer_demand"])
        columns = np.asarray(synthetic_economy.consumer_extra["utility_exponent_commodity"])
        named = np.zeros(synthetic_economy.n_commodities, dtype=bool)
        named[columns] = True

        assert stated.shape == (synthetic_economy.n_commodities,)
        assert stated.dtype == np.float64
        assert named.any() and not named.all()
        assert np.all(stated[named] > 0.0)
        np.testing.assert_array_equal(stated[~named], np.zeros(int((~named).sum())))

    def test_provision_alone_says_nothing_about_the_public_good_balance(
        self, synthetic_economy
    ):
        """The gap that ``provision`` produces is identically zero: it is the supply side."""
        plan = run(HahnelSlides2020(), synthetic_economy, seed=0).plan
        supply = plan.total_output(synthetic_economy) + np.asarray(synthetic_economy.endowment)
        demand = (
            plan.total_input_use(synthetic_economy)
            + plan.total_consumption(synthetic_economy)
            + np.asarray(plan.provision)
        )
        public = np.asarray(synthetic_economy.commodity_kind) == CommodityKind.PUBLIC_GOOD
        np.testing.assert_array_equal(supply[public], demand[public])


class TestPriceRuleSeam:
    """Swapping the price rule is the one change the slides procedure is built to take."""

    def test_the_default_is_the_named_2020_rule(self, synthetic_economy):
        default = run(HahnelSlides2020(), synthetic_economy, seed=0)
        named = run(
            HahnelSlides2020(price_rule=slides_2020_rule), synthetic_economy, seed=0
        )
        assert default.summary.rounds == named.summary.rounds
        np.testing.assert_array_equal(default.plan.output, named.plan.output)
        np.testing.assert_array_equal(
            default.plan.valuation[INDICATIVE_PRICE], named.plan.valuation[INDICATIVE_PRICE]
        )

    def test_a_rule_that_never_moves_the_price_never_converges(self, synthetic_economy):
        def frozen(price, surplus, imbalance):
            return price

        result = run(
            HahnelSlides2020(price_rule=frozen, max_rounds=6), synthetic_economy, seed=0
        )
        assert result.summary.converged is False
        assert result.summary.rounds == 6
        np.testing.assert_array_equal(
            result.plan.valuation[INDICATIVE_PRICE],
            np.full(synthetic_economy.n_commodities, HahnelSlides2020().initial_price),
        )

    def test_the_rule_is_handed_the_surplus_and_the_imbalance_of_that_round(
        self, synthetic_economy
    ):
        """Checked on the private goods, whose supply and demand the plan alone accounts for."""
        seen = []

        def recording(price, surplus, imbalance):
            seen.append((price.copy(), surplus.copy(), imbalance.copy()))
            return slides_2020_rule(price, surplus, imbalance)

        result = run(
            HahnelSlides2020(price_rule=recording, max_rounds=1, record_trajectory=True),
            synthetic_economy,
            seed=0,
        )
        plan = result.summary.trajectory[0]
        _, surplus, imbalance = seen[0]

        private = np.asarray(synthetic_economy.commodity_kind) == CommodityKind.PRIVATE_GOOD
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
        def proportional(price, surplus, imbalance):
            return price * (1 - 0.2 * np.sign(surplus) * imbalance)

        through_the_seam = run(
            HahnelSlides2020(price_rule=proportional, max_rounds=60),
            synthetic_economy,
            seed=0,
        )

        model = CouncilModel(synthetic_economy, 5.0, price_rule=proportional)
        by_hand = iterate(
            lambda: model.initial_state(HahnelSlides2020().initial_price),
            model.step,
            model.converged,
            60,
        )
        assert through_the_seam.summary.rounds == by_hand.rounds
        assert through_the_seam.summary.converged == by_hand.converged
        np.testing.assert_array_equal(
            through_the_seam.plan.output, model.plan_of(by_hand.state).output
        )


@pytest.mark.skipif(not dep1ex_available(1), reason="dep1ex01 archive not available")
class TestDep1ex01:
    def test_round_count_matches_the_reference(self, dep1ex01_parsed, dep1ex01_economy):
        wc, cc, layout = dep1ex01_parsed
        expected_rounds, _, _ = reference_run(wc, cc, layout)
        result = run(HahnelSlides2020(), dep1ex01_economy, seed=0)
        assert result.summary.converged is True
        assert result.summary.rounds == expected_rounds

    def test_final_prices_match_the_reference(self, dep1ex01_parsed, dep1ex01_economy):
        wc, cc, layout = dep1ex01_parsed
        _, expected_prices, _ = reference_run(wc, cc, layout)
        result = run(HahnelSlides2020(), dep1ex01_economy, seed=0)
        np.testing.assert_allclose(
            result.plan.valuation[INDICATIVE_PRICE],
            unified_price(expected_prices, layout),
            rtol=1e-9,
            atol=0,
        )

    def test_first_round_proposals_match_the_reference(self, dep1ex01_parsed, dep1ex01_economy):
        wc, cc, layout = dep1ex01_parsed
        expected_output, expected_input_use = reference_first_round(wc, cc, layout)
        first = run(
            HahnelSlides2020(max_rounds=1, record_trajectory=True), dep1ex01_economy, seed=0
        ).plan
        np.testing.assert_allclose(first.output, expected_output, rtol=1e-12, atol=0)
        np.testing.assert_allclose(first.input_use, expected_input_use, rtol=1e-12, atol=0)

    def test_not_slower_than_the_reference(self, dep1ex01_parsed, dep1ex01_economy):
        wc, cc, layout = dep1ex01_parsed
        started = time.perf_counter()
        reference_run(wc, cc, layout)
        reference_seconds = time.perf_counter() - started
        result = run(HahnelSlides2020(), dep1ex01_economy, seed=0)
        assert result.summary.wall_seconds <= TIMING_ALLOWANCE * reference_seconds, (
            f"prefab {result.summary.wall_seconds:.2f}s "
            f"vs reference {reference_seconds:.2f}s"
        )

    def test_the_plan_reproduces_its_own_production_function(self, dep1ex01_economy):
        plan = run(HahnelSlides2020(), dep1ex01_economy, seed=0).plan
        np.testing.assert_allclose(
            np.asarray(plan.output),
            output_from_the_production_function(dep1ex01_economy, plan),
            rtol=1e-9,
            atol=0,
        )

    def test_effort_matches_the_upstream_closed_form(self, dep1ex01_economy):
        model = CouncilModel(dep1ex01_economy, 5.0)
        price = np.full(dep1ex01_economy.n_commodities, 700.0)
        _, effort, _ = model._propose(price)

        _, expected_effort = upstream_output_and_effort(dep1ex01_economy, price)
        np.testing.assert_allclose(effort, expected_effort, rtol=1e-12, atol=0)

    def test_the_public_good_imbalance_is_the_one_the_mechanism_measured(
        self, dep1ex01_economy
    ):
        rule = RecordingRule()
        result = run(HahnelSlides2020(price_rule=rule), dep1ex01_economy, seed=0)
        public = np.asarray(dep1ex01_economy.commodity_kind) == CommodityKind.PUBLIC_GOOD

        rebuilt = imbalance_rebuilt_from(dep1ex01_economy, result.plan)
        np.testing.assert_allclose(
            rebuilt[public], rule.imbalance[-1][public], rtol=1e-12, atol=0
        )
        assert rebuilt[public].max() > 0.01

    def test_determinism_report(self, dep1ex01_economy):
        report = check_determinism(HahnelSlides2020(), dep1ex01_economy, 0, n=2)
        assert report.identical is True
        assert report.differing_fields == []


@pytest.mark.slow
@pytest.mark.skipif(
    not all(dep1ex_available(i) for i in range(1, DEP1EX_COUNT + 1)),
    reason="the full dep1ex set is not available",
)
class TestPublishedExperiments:
    def test_all_five_experiments(self):
        cold5_ours, cold5_reference, cold3_ours = [], [], []
        for index in range(1, DEP1EX_COUNT + 1):
            wc, cc, layout = parse_dep1ex(dep1ex_path(index))
            economy = economy_from_repro(wc, cc, layout)
            reference5, _, _ = reference_run(wc, cc, layout, threshold=5.0)
            cold5_reference.append(reference5)
            cold5_ours.append(run(HahnelSlides2020(), economy, seed=0).summary.rounds)
            cold3_ours.append(
                run(HahnelSlides2020(threshold_pct=3.0), economy, seed=0).summary.rounds
            )
            del wc, cc, economy
            gc.collect()

        assert cold5_ours == cold5_reference
        assert sorted(cold5_ours) == COLD_5_PERCENT_ROUNDS
        assert abs(statistics.fmean(cold3_ours) - COLD_3_PERCENT_MEAN) < 0.05


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
    public = np.asarray(economy.commodity_kind)[columns] == CommodityKind.PUBLIC_GOOD
    listed = np.asarray(price)[columns]
    paid = np.where(public, listed / economy.n_consumers, listed)
    return (entitlement[:, None] * exponent) / (
        exponent.sum(axis=1)[:, None] * paid[None, :]
    )


def commodity_demand_rebuilt_from(economy, plan, price):
    """Demand per commodity: the units' input use plus the councils' stated consumption.

    A public good's stated demand counts once for the whole society, so its column total is
    divided by the number of consumer units before it is scattered onto its commodity. Every
    other column is scattered whole, whatever kind its commodity is.
    """
    columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
    public = np.asarray(economy.commodity_kind)[columns] == CommodityKind.PUBLIC_GOOD
    stated = stated_bundle(economy, price).sum(axis=0)
    shared = np.where(public, stated / economy.n_consumers, stated)
    return plan.total_input_use(economy) + np.bincount(
        columns, weights=shared, minlength=economy.n_commodities
    )


class TestConsumptionBlockIsNotCopied:
    """``plan_of`` hands over the block the round produced rather than a copy of it.

    The block is ``f64[n_consumers, n_private_columns]``: 24 MB on dep1ex01, and the default
    configuration turns every round's state into a plan, so a copy here is a copy per round.
    """

    def test_the_plan_shares_the_state_consumption_block(self, synthetic_economy):
        model = CouncilModel(synthetic_economy, 5.0)
        state = model.step(model.initial_state(700.0))
        plan = model.plan_of(state)
        assert np.shares_memory(np.asarray(plan.consumption), state.consumption)

    def test_it_shares_when_the_private_columns_are_not_contiguous(self):
        """Non-contiguous columns are where a split by position would fall back to a copy."""
        economy = synthetic.build_permuted_economy()
        model = CouncilModel(economy, 5.0)
        state = model.step(model.initial_state(700.0))
        plan = model.plan_of(state)
        assert np.shares_memory(np.asarray(plan.consumption), state.consumption)

    def test_it_shares_when_a_column_is_neither_private_nor_public(self):
        economy = synthetic.build_economy_with_a_third_kind_column()
        model = CouncilModel(economy, 5.0)
        state = model.step(model.initial_state(700.0))
        plan = model.plan_of(state)
        assert np.shares_memory(np.asarray(plan.consumption), state.consumption)


class TestColumnsThatAreNeitherPrivateNorPublic:
    """A utility-exponent column names a commodity of any kind, and there are five kinds.

    A column on an intermediate good is priced at the listed price and counts into that
    commodity's demand, like a private-good column. It stays out of the plan's consumption
    block and out of ``provision``, because both are defined by ``commodity_kind``;
    ``extra["consumer_demand"]`` is where it reaches the plan.
    """

    @pytest.fixture
    def third_kind_economy(self):
        return synthetic.build_economy_with_a_third_kind_column()

    @pytest.fixture
    def second_round(self, third_kind_economy):
        """``(plan, price, surplus)`` of the second round, whose price is no longer flat."""
        seen = []

        def recording(price, surplus, imbalance):
            seen.append((price.copy(), surplus.copy()))
            return slides_2020_rule(price, surplus, imbalance)

        result = run(
            HahnelSlides2020(price_rule=recording, max_rounds=2, record_trajectory=True),
            third_kind_economy,
            seed=0,
        )
        assert len(result.summary.trajectory) == 2
        price, surplus = seen[-1]
        assert np.unique(price).size > 1
        return result.summary.trajectory[-1], price, surplus

    def test_the_fixture_holds_a_column_of_each_of_the_three_cases(self, third_kind_economy):
        kinds = np.asarray(third_kind_economy.commodity_kind)
        columns = np.asarray(third_kind_economy.consumer_extra["utility_exponent_commodity"])
        column_kinds = set(kinds[columns].tolist())
        assert CommodityKind.PRIVATE_GOOD in column_kinds
        assert CommodityKind.PUBLIC_GOOD in column_kinds
        assert column_kinds - {CommodityKind.PRIVATE_GOOD, CommodityKind.PUBLIC_GOOD}

        private = np.flatnonzero(kinds[columns] == CommodityKind.PRIVATE_GOOD)
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

        Masking ``consumer_demand`` down to the public goods is what the plan used to report
        on its own, so the mask is asserted here as well as the value.
        """
        plan, price, _ = second_round
        kinds = np.asarray(third_kind_economy.commodity_kind)
        columns = np.asarray(third_kind_economy.consumer_extra["utility_exponent_commodity"])
        public = np.flatnonzero(kinds[columns] == CommodityKind.PUBLIC_GOOD)
        stated = stated_bundle(third_kind_economy, price).sum(axis=0)

        expected = np.bincount(
            columns[public],
            weights=stated[public] / third_kind_economy.n_consumers,
            minlength=third_kind_economy.n_commodities,
        )
        assert expected[kinds == CommodityKind.PUBLIC_GOOD].min() > 0.0
        consumer_demand = np.asarray(plan.extra["consumer_demand"])
        np.testing.assert_array_equal(
            np.where(kinds == CommodityKind.PUBLIC_GOOD, consumer_demand, 0.0), expected
        )

    def test_the_private_columns_reach_consumer_demand_whole(
        self, third_kind_economy, second_round
    ):
        """A private-good column contributes its whole total, the one ``consumption`` holds."""
        plan, price, _ = second_round
        kinds = np.asarray(third_kind_economy.commodity_kind)
        columns = np.asarray(third_kind_economy.consumer_extra["utility_exponent_commodity"])
        private = np.flatnonzero(kinds[columns] == CommodityKind.PRIVATE_GOOD)
        stated = stated_bundle(third_kind_economy, price).sum(axis=0)

        expected = np.bincount(
            columns[private],
            weights=stated[private],
            minlength=third_kind_economy.n_commodities,
        )
        on_private = kinds == CommodityKind.PRIVATE_GOOD
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

    def test_the_column_stays_out_of_the_consumption_block(
        self, third_kind_economy, second_round
    ):
        plan, _, _ = second_round
        columns = np.asarray(plan.consumption_commodity)
        assert synthetic.THIRD_KIND_COMMODITY not in columns.tolist()
        np.testing.assert_array_equal(
            columns, third_kind_economy.commodities_of_kind(CommodityKind.PRIVATE_GOOD)
        )
        plan.validate(third_kind_economy)

    def test_provision_stays_zero_on_the_third_kind_commodity(
        self, third_kind_economy, second_round
    ):
        plan, _, _ = second_round
        assert np.asarray(plan.provision)[synthetic.THIRD_KIND_COMMODITY] == 0.0

    def test_the_consumption_block_is_the_private_columns_of_the_stated_bundle(
        self, third_kind_economy, second_round
    ):
        plan, price, _ = second_round
        kinds = np.asarray(third_kind_economy.commodity_kind)
        columns = np.asarray(third_kind_economy.consumer_extra["utility_exponent_commodity"])
        private = np.flatnonzero(kinds[columns] == CommodityKind.PRIVATE_GOOD)
        np.testing.assert_array_equal(
            np.asarray(plan.consumption),
            stated_bundle(third_kind_economy, price)[:, private],
        )

    def test_a_run_over_the_three_cases_converges(self, third_kind_economy):
        result = run(HahnelSlides2020(), third_kind_economy, seed=0)
        assert result.summary.converged is True
        result.plan.validate(third_kind_economy)


class TestStatedDemandSplit:
    """``_demand`` returns the private-good columns and the rest as two separate blocks.

    Per column is the only place the public-good price is visible. A council facing a public
    good states ``n_consumers`` times as much at ``price / n_consumers``, and the aggregation
    divides that column's total by ``n_consumers`` again, so the two halves of the rule cancel
    in every commodity-level number the plan reports.
    """

    @pytest.fixture
    def model_and_price(self):
        economy = synthetic.build_economy_with_a_third_kind_column()
        return CouncilModel(economy, 5.0), economy, uneven_price(economy)

    def test_the_two_blocks_are_the_stated_bundle_split_by_commodity_kind(
        self, model_and_price
    ):
        model, economy, price = model_and_price
        private_block, other_block = model._demand(price)

        kinds = np.asarray(economy.commodity_kind)
        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        private = np.flatnonzero(kinds[columns] == CommodityKind.PRIVATE_GOOD)
        other = np.flatnonzero(kinds[columns] != CommodityKind.PRIVATE_GOOD)
        expected = stated_bundle(economy, price)

        np.testing.assert_array_equal(private_block, expected[:, private])
        np.testing.assert_array_equal(other_block, expected[:, other])

    def test_a_public_good_column_pays_the_listed_price_per_consumer_unit(
        self, model_and_price
    ):
        model, economy, price = model_and_price
        _, other_block = model._demand(price)

        kinds = np.asarray(economy.commodity_kind)
        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        other = np.flatnonzero(kinds[columns] != CommodityKind.PRIVATE_GOOD)
        at = int(np.flatnonzero(kinds[columns[other]] == CommodityKind.PUBLIC_GOOD)[0])

        entitlement = np.asarray(economy.consumer_extra["entitlement"])
        exponent = np.asarray(economy.consumer_extra["utility_exponent"])
        paid = price[columns[other[at]]] / economy.n_consumers
        expected = entitlement * exponent[:, other[at]] / (exponent.sum(axis=1) * paid)
        np.testing.assert_array_equal(other_block[:, at], expected)

    def test_a_column_that_is_neither_pays_the_whole_listed_price(self, model_and_price):
        model, economy, price = model_and_price
        _, other_block = model._demand(price)

        kinds = np.asarray(economy.commodity_kind)
        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        other = np.flatnonzero(kinds[columns] != CommodityKind.PRIVATE_GOOD)
        at = int(np.flatnonzero(columns[other] == synthetic.THIRD_KIND_COMMODITY)[0])

        entitlement = np.asarray(economy.consumer_extra["entitlement"])
        exponent = np.asarray(economy.consumer_extra["utility_exponent"])
        paid = price[synthetic.THIRD_KIND_COMMODITY]
        expected = entitlement * exponent[:, other[at]] / (exponent.sum(axis=1) * paid)
        np.testing.assert_array_equal(other_block[:, at], expected)

    def test_a_private_good_column_pays_the_whole_listed_price(self, model_and_price):
        model, economy, price = model_and_price
        private_block, _ = model._demand(price)

        kinds = np.asarray(economy.commodity_kind)
        columns = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        private = np.flatnonzero(kinds[columns] == CommodityKind.PRIVATE_GOOD)

        entitlement = np.asarray(economy.consumer_extra["entitlement"])
        exponent = np.asarray(economy.consumer_extra["utility_exponent"])
        paid = price[columns[private[0]]]
        expected = entitlement * exponent[:, private[0]] / (exponent.sum(axis=1) * paid)
        np.testing.assert_array_equal(private_block[:, 0], expected)
