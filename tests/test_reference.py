"""The centralised optimum: a linear program over a Leontief economy.

Two kinds of check run here. The hand-built economy is small enough that the optimum, the
objective value and every dual variable are written out from the algebra in this module's
docstring, so the expected numbers do not come from the solver. The generated economies are
checked against the optimality conditions of a linear program -- material balance, dual
feasibility, complementary slackness and strong duality -- which are properties of the answer
rather than a second copy of the assembly code.

The hand-built economy, ``build_bread_economy``:

* commodity 0 is a private good, commodity 1 an intermediate good, commodity 2 labour;
* unit 0 makes one commodity 0 from 0.5 commodity 1 and 1.0 labour;
* unit 1 makes one commodity 1 from 2.0 labour;
* the only endowment is 12 units of labour.

Maximising final consumption of commodity 0 gives ``q = (6, 3)``, ``f = 6``. The dual of that
program is ``min 12 y_2`` subject to ``y_0 >= 1``, ``y_1 <= 2 y_2`` and
``0.5 y_1 + y_2 >= y_0``, whose optimum is ``y = (1, 1, 0.5)`` with value 6, matching the
primal. Reading the same numbers off directly: a free unit of commodity 0 adds one to final
consumption, a free unit of commodity 1 releases two units of labour and so adds one, and a
free unit of labour adds a half.

With the labour endowment raised to 20 and a lower bound of 6 on final consumption of
commodity 0, minimising labour gives the same ``q = (6, 3)`` at a cost of 12 labour. A free
unit of commodity 0 then saves 2 labour, so does a free unit of commodity 1, and labour is
slack, so its own dual is zero.
"""

from __future__ import annotations

import dataclasses
import time

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cyberstride import (
    INDICATIVE_PRICE,
    SHADOW_PRICE,
    CommodityKind,
    Economy,
    Plan,
    TechnologyKind,
    load_dep1ex,
    run,
)
from cyberstride.objectives import MaximizeWeightedConsumption, MinimizeLabor
from cyberstride.prefabs import HahnelSlides2020
from cyberstride.reference import (
    ReferenceInfeasible,
    ReferenceProcedure,
    ReferenceResult,
    reference_solution,
)
from cyberstride.tools.linearize import linearize
from reference.paths import dep1ex_available, dep1ex_path

EXACT = 1e-9
"""Tolerance the hand-built optimum is asserted to, as the construction sheet asks."""

CONDITION_TOLERANCE = 1e-7
"""Tolerance for the optimality conditions on generated economies, scaled by magnitude."""

PERTURBATION_FLOOR = 1e-4
"""Smallest extra labour draw a one-percent perturbation must cause before it is asserted on.

Below this the violation is of the same order as the solver's own residual on a binding
constraint, so the assertion would be measuring rounding rather than optimality.
"""

DEP1EX_SECONDS_ALLOWED = 60.0
"""Above this the reference solution on dep1ex01 is reported as too slow rather than passing."""

BREAD, FLOUR, WORK = 0, 1, 2
N_BREAD_COMMODITIES = 3


def build_bread_economy(labor_endowment: float = 12.0, n_consumers: int = 2) -> Economy:
    """The three-commodity economy the module docstring solves by hand."""
    return Economy(
        period=0,
        commodity_id=np.arange(N_BREAD_COMMODITIES, dtype=np.int64),
        commodity_kind=np.array(
            [CommodityKind.PRIVATE_GOOD, CommodityKind.INTERMEDIATE, CommodityKind.LABOR],
            dtype=np.int8,
        ),
        endowment=np.array([0.0, 0.0, labor_endowment]),
        unit_id=np.arange(2, dtype=np.int64),
        unit_group=np.zeros(2, dtype=np.int64),
        output_commodity=np.array([BREAD, FLOUR], dtype=np.int64),
        technology_kind=np.full(2, TechnologyKind.LEONTIEF, dtype=np.int8),
        technology_scale=np.ones(2),
        input_offsets=np.array([0, 2, 3], dtype=np.int64),
        input_commodity=np.array([FLOUR, WORK, WORK], dtype=np.int64),
        input_coefficient=np.array([0.5, 1.0, 2.0]),
        consumer_id=np.arange(n_consumers, dtype=np.int64),
        consumer_group=np.zeros(n_consumers, dtype=np.int64),
    )


def bread_weights() -> np.ndarray:
    weights = np.zeros(N_BREAD_COMMODITIES)
    weights[BREAD] = 1.0
    return weights


def commodity_slack(economy: Economy, output: np.ndarray, final: np.ndarray) -> np.ndarray:
    """``supply + endowment - input use - final use`` per commodity, computed from scratch.

    This repeats the balance the linear program constrains rather than calling the tools the
    implementation uses, so an error shared with the implementation cannot cancel out.
    """
    n_commodities = economy.n_commodities
    owner = np.repeat(np.arange(economy.n_units), np.diff(economy.input_offsets))
    supply = np.bincount(
        economy.output_commodity, weights=output, minlength=n_commodities
    ) + np.asarray(economy.endowment)
    drawn = np.bincount(
        economy.input_commodity,
        weights=np.asarray(economy.input_coefficient) * np.asarray(output)[owner],
        minlength=n_commodities,
    )
    return supply - drawn - final


def final_use_of(economy: Economy, plan: Plan) -> np.ndarray:
    """Final consumption per commodity: what consumer units get plus what is provided."""
    return plan.total_consumption(economy) + np.asarray(plan.provision)


def scaled_tolerance(magnitude: float) -> float:
    return CONDITION_TOLERANCE * max(1.0, abs(magnitude))


class TestHandSolvedMaximisation:
    def test_status_and_objective_value(self):
        result = reference_solution(
            build_bread_economy(), MaximizeWeightedConsumption(bread_weights())
        )
        assert isinstance(result, ReferenceResult)
        assert result.status == "optimal"
        assert result.objective_value == pytest.approx(6.0, abs=EXACT)

    def test_output_per_unit(self):
        result = reference_solution(
            build_bread_economy(), MaximizeWeightedConsumption(bread_weights())
        )
        np.testing.assert_allclose(result.plan.output, [6.0, 3.0], atol=EXACT)

    def test_final_consumption(self):
        result = reference_solution(
            build_bread_economy(), MaximizeWeightedConsumption(bread_weights())
        )
        final = final_use_of(build_bread_economy(), result.plan)
        np.testing.assert_allclose(final, [6.0, 0.0, 0.0], atol=EXACT)

    def test_consumption_is_split_between_the_two_consumer_units(self):
        result = reference_solution(
            build_bread_economy(), MaximizeWeightedConsumption(bread_weights())
        )
        np.testing.assert_array_equal(result.plan.consumption_commodity, [BREAD])
        np.testing.assert_allclose(result.plan.consumption, [[3.0], [3.0]], atol=EXACT)
        np.testing.assert_allclose(result.plan.provision, np.zeros(3), atol=EXACT)

    def test_input_use_follows_the_leontief_coefficients(self):
        result = reference_solution(
            build_bread_economy(), MaximizeWeightedConsumption(bread_weights())
        )
        np.testing.assert_allclose(result.plan.input_use, [3.0, 6.0, 6.0], atol=EXACT)

    def test_labour_is_used_to_the_last_unit(self):
        economy = build_bread_economy()
        result = reference_solution(economy, MaximizeWeightedConsumption(bread_weights()))
        np.testing.assert_allclose(result.plan.endowment_use(economy), [0.0, 0.0, 12.0], atol=EXACT)

    def test_shadow_prices_match_the_dual_program(self):
        result = reference_solution(
            build_bread_economy(), MaximizeWeightedConsumption(bread_weights())
        )
        np.testing.assert_allclose(result.plan.valuation[SHADOW_PRICE], [1.0, 1.0, 0.5], atol=EXACT)

    def test_the_plan_validates_against_its_economy(self):
        economy = build_bread_economy()
        result = reference_solution(economy, MaximizeWeightedConsumption(bread_weights()))
        result.plan.validate(economy)

    def test_doubling_the_labour_endowment_doubles_the_optimum(self):
        result = reference_solution(
            build_bread_economy(labor_endowment=24.0),
            MaximizeWeightedConsumption(bread_weights()),
        )
        assert result.objective_value == pytest.approx(12.0, abs=EXACT)
        np.testing.assert_allclose(result.plan.output, [12.0, 6.0], atol=EXACT)


class TestHandSolvedLabourMinimisation:
    def targets(self) -> np.ndarray:
        targets = np.zeros(N_BREAD_COMMODITIES)
        targets[BREAD] = 6.0
        return targets

    def test_it_meets_the_target_at_the_least_labour(self):
        result = reference_solution(
            build_bread_economy(labor_endowment=20.0), MinimizeLabor(self.targets())
        )
        assert result.status == "optimal"
        assert result.objective_value == pytest.approx(12.0, abs=EXACT)
        np.testing.assert_allclose(result.plan.output, [6.0, 3.0], atol=EXACT)

    def test_the_target_is_met_exactly(self):
        economy = build_bread_economy(labor_endowment=20.0)
        result = reference_solution(economy, MinimizeLabor(self.targets()))
        np.testing.assert_allclose(final_use_of(economy, result.plan), [6.0, 0.0, 0.0], atol=EXACT)

    def test_shadow_prices_are_labour_saved_per_free_unit(self):
        result = reference_solution(
            build_bread_economy(labor_endowment=20.0), MinimizeLabor(self.targets())
        )
        np.testing.assert_allclose(result.plan.valuation[SHADOW_PRICE], [2.0, 2.0, 0.0], atol=EXACT)

    def test_labour_left_over_is_not_used(self):
        economy = build_bread_economy(labor_endowment=20.0)
        result = reference_solution(economy, MinimizeLabor(self.targets()))
        np.testing.assert_allclose(result.plan.endowment_use(economy), [0.0, 0.0, 12.0], atol=EXACT)

    def test_a_target_beyond_the_endowment_is_infeasible(self):
        targets = np.zeros(N_BREAD_COMMODITIES)
        targets[BREAD] = 100.0
        with pytest.raises(ReferenceInfeasible):
            reference_solution(build_bread_economy(), MinimizeLabor(targets))

    def test_a_negative_target_is_refused_and_the_message_names_the_commodity(self):
        """A floor of -3 on the flour would report 6 labour where every feasible plan spends 12.

        The floor becomes the lower bound on that commodity's final consumption, so a negative
        one lets the program cover the 3 flour six bread draws by consuming -3 of it instead of
        producing it. Flour is a private good here, since a floor on an intermediate good is
        already refused for a different reason.
        """
        economy = dataclasses.replace(
            build_bread_economy(labor_endowment=20.0),
            commodity_kind=np.array(
                [CommodityKind.PRIVATE_GOOD, CommodityKind.PRIVATE_GOOD, CommodityKind.LABOR],
                dtype=np.int8,
            ),
        )
        targets = self.targets()
        targets[FLOUR] = -3.0
        with pytest.raises(ValueError, match=f"commodity {FLOUR}"):
            reference_solution(economy, MinimizeLabor(targets))


class TestHandSolvedChoiceBetweenTechniques:
    """Two ways to make the same good, and the objective decides which one runs.

    Commodity 0 is a private good, commodity 1 a natural resource, commodity 2 labour, with
    20 of each endowment. Unit 0 makes one commodity 0 from 3 labour. Unit 1 makes one from
    1 labour and 4 of the natural resource. Requiring 4 of commodity 0 and minimising labour
    runs unit 1 four times for 4 labour, because the natural resource is not a labour cost and
    20 of it is enough for the 16 that takes.

    An objective that totalled natural resources alongside labour would price unit 1 at 5 and
    unit 0 at 3, run unit 0 instead, and reach 12. That is why this economy is here: the
    bread economy has no natural resource, so it cannot tell the two objectives apart.
    """

    N_COMMODITIES = 3
    GOOD, NATURE, WORK = 0, 1, 2

    def build(self) -> Economy:
        return Economy(
            period=0,
            commodity_id=np.arange(self.N_COMMODITIES, dtype=np.int64),
            commodity_kind=np.array(
                [
                    CommodityKind.PRIVATE_GOOD,
                    CommodityKind.NATURAL_RESOURCE,
                    CommodityKind.LABOR,
                ],
                dtype=np.int8,
            ),
            endowment=np.array([0.0, 20.0, 20.0]),
            unit_id=np.arange(2, dtype=np.int64),
            unit_group=np.zeros(2, dtype=np.int64),
            output_commodity=np.array([self.GOOD, self.GOOD], dtype=np.int64),
            technology_kind=np.full(2, TechnologyKind.LEONTIEF, dtype=np.int8),
            technology_scale=np.ones(2),
            input_offsets=np.array([0, 1, 3], dtype=np.int64),
            input_commodity=np.array([self.WORK, self.NATURE, self.WORK], dtype=np.int64),
            input_coefficient=np.array([3.0, 4.0, 1.0]),
            consumer_id=np.arange(2, dtype=np.int64),
            consumer_group=np.zeros(2, dtype=np.int64),
        )

    def targets(self) -> np.ndarray:
        targets = np.zeros(self.N_COMMODITIES)
        targets[self.GOOD] = 4.0
        return targets

    def solved(self) -> ReferenceResult:
        return reference_solution(self.build(), MinimizeLabor(self.targets()))

    def test_it_runs_the_technique_that_spends_the_least_labour(self):
        np.testing.assert_allclose(self.solved().plan.output, [0.0, 4.0], atol=EXACT)

    def test_the_natural_resource_is_not_counted_as_a_labour_cost(self):
        result = self.solved()
        assert result.objective_value == pytest.approx(4.0, abs=EXACT)

    def test_the_objective_is_the_labour_the_plan_draws(self):
        economy = self.build()
        result = self.solved()
        drawn = result.plan.total_input_use(economy)
        np.testing.assert_allclose(drawn, [0.0, 16.0, 4.0], atol=EXACT)
        assert result.objective_value == pytest.approx(float(drawn[self.WORK]), abs=EXACT)

    def test_only_the_binding_commodity_carries_a_shadow_price(self):
        np.testing.assert_allclose(
            self.solved().plan.valuation[SHADOW_PRICE], [1.0, 0.0, 0.0], atol=EXACT
        )


class PairDeclaredObjective:
    """A researcher's own labour-minimising objective, declared by attribute rather than type.

    ``weights`` returns zeros, as a labour-minimising objective does, so an assembly that reads
    this objective as a maximisation maximises nothing. Either attribute is left off entirely
    when it is not supplied, which is what an objective that declares half the pair looks like.
    """

    name = "pair_declared"

    def __init__(self, lower_bound=None, minimize_kind=None):
        if lower_bound is not None:
            self.final_demand_lower_bound = np.asarray(lower_bound, dtype=np.float64)
        if minimize_kind is not None:
            self.minimize_kind = minimize_kind

    def weights(self, economy: Economy) -> np.ndarray:
        return np.zeros(economy.n_commodities, dtype=np.float64)

    def allocate(self, economy: Economy, aggregate: np.ndarray):
        zero_weights = np.zeros(economy.n_commodities, dtype=np.float64)
        return MaximizeWeightedConsumption(zero_weights).allocate(economy, aggregate)


class TestMinimisationDeclaredByAttribute:
    """The pair of attributes is what makes a program minimise, so half a pair is refused."""

    def targets(self) -> np.ndarray:
        targets = np.zeros(N_BREAD_COMMODITIES)
        targets[BREAD] = 6.0
        return targets

    def test_both_attributes_together_minimise_like_the_built_in_objective(self):
        objective = PairDeclaredObjective(
            lower_bound=self.targets(), minimize_kind=CommodityKind.LABOR
        )
        result = reference_solution(build_bread_economy(labor_endowment=20.0), objective)
        assert result.objective_value == pytest.approx(12.0, abs=EXACT)
        np.testing.assert_allclose(result.plan.output, [6.0, 3.0], atol=EXACT)

    def test_a_lower_bound_without_a_minimised_kind_is_refused(self):
        """Read as a maximisation, this objective maximises zero and reports an empty plan."""
        objective = PairDeclaredObjective(lower_bound=self.targets())
        with pytest.raises(ValueError, match="minimize_kind"):
            reference_solution(build_bread_economy(labor_endowment=20.0), objective)

    def test_a_minimised_kind_without_a_lower_bound_is_refused(self):
        objective = PairDeclaredObjective(minimize_kind=CommodityKind.LABOR)
        with pytest.raises(ValueError, match="final_demand_lower_bound"):
            reference_solution(build_bread_economy(labor_endowment=20.0), objective)

    def test_the_message_names_the_objective_that_declared_half_the_pair(self):
        objective = PairDeclaredObjective(lower_bound=self.targets())
        with pytest.raises(ValueError, match="pair_declared"):
            reference_solution(build_bread_economy(labor_endowment=20.0), objective)


class TestRefusedInputs:
    def test_a_cobb_douglas_economy_is_refused_and_points_at_the_linearising_tool(self):
        cobb_douglas = dataclasses.replace(
            build_bread_economy(),
            technology_kind=np.full(2, TechnologyKind.COBB_DOUGLAS, dtype=np.int8),
        )
        with pytest.raises(ValueError, match="cyberstride.tools.linearize"):
            reference_solution(cobb_douglas, MaximizeWeightedConsumption(bread_weights()))

    def test_a_commodity_produced_from_nothing_makes_the_program_unbounded(self):
        economy = Economy(
            period=0,
            commodity_id=np.arange(2, dtype=np.int64),
            commodity_kind=np.array(
                [CommodityKind.PRIVATE_GOOD, CommodityKind.LABOR], dtype=np.int8
            ),
            endowment=np.array([0.0, 10.0]),
            unit_id=np.arange(1, dtype=np.int64),
            unit_group=np.zeros(1, dtype=np.int64),
            output_commodity=np.array([0], dtype=np.int64),
            technology_kind=np.zeros(1, dtype=np.int8),
            technology_scale=np.ones(1),
            input_offsets=np.array([0, 0], dtype=np.int64),
            input_commodity=np.zeros(0, dtype=np.int64),
            input_coefficient=np.zeros(0),
            consumer_id=np.arange(1, dtype=np.int64),
            consumer_group=np.zeros(1, dtype=np.int64),
        )
        weights = np.array([1.0, 0.0])
        with pytest.raises(ReferenceInfeasible):
            reference_solution(economy, MaximizeWeightedConsumption(weights))


class TestReferenceProcedure:
    def test_it_returns_the_same_plan_as_the_function(self):
        economy = build_bread_economy()
        objective = MaximizeWeightedConsumption(bread_weights())
        by_hand = reference_solution(economy, objective)
        through_run = run(ReferenceProcedure(objective), economy, seed=0)
        np.testing.assert_allclose(through_run.plan.output, by_hand.plan.output, atol=EXACT)
        np.testing.assert_allclose(
            through_run.plan.valuation[SHADOW_PRICE],
            by_hand.plan.valuation[SHADOW_PRICE],
            atol=EXACT,
        )

    def test_the_seed_does_not_change_the_answer(self):
        economy = build_bread_economy()
        procedure = ReferenceProcedure(MaximizeWeightedConsumption(bread_weights()))
        first = procedure.solve(economy, 0)
        second = procedure.solve(economy, 2**63 - 1)
        np.testing.assert_array_equal(first.output, second.output)
        np.testing.assert_array_equal(
            first.valuation[SHADOW_PRICE], second.valuation[SHADOW_PRICE]
        )

    def test_the_run_reports_no_rounds_because_there_is_no_loop(self):
        result = run(
            ReferenceProcedure(MaximizeWeightedConsumption(bread_weights())),
            build_bread_economy(),
            seed=0,
        )
        assert result.summary.rounds is None
        assert result.summary.converged is None


COEFFICIENT = st.floats(min_value=0.05, max_value=0.9, allow_nan=False, allow_infinity=False)
ENDOWMENT = st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False)
WEIGHT = st.floats(min_value=0.1, max_value=10.0, allow_nan=False, allow_infinity=False)


@st.composite
def leontief_economy(draw):
    """A random Leontief economy with a bounded, feasible maximisation on it.

    The layout is private goods, then public goods, then intermediate goods, then one natural
    resource and one kind of labour, which is the section order dep1ex uses. Two properties are
    built in so that the optimum exists and the tests below can say something sharp about it:
    every unit draws labour, which bounds output, and unit 0 turns labour straight into private
    good 0, which is why labour is fully used at every optimum.
    """
    n_private = draw(st.integers(min_value=1, max_value=2))
    n_public = draw(st.integers(min_value=0, max_value=2))
    n_intermediate = draw(st.integers(min_value=0, max_value=2))
    natural = n_private + n_public + n_intermediate
    labor = natural + 1
    n_commodities = labor + 1

    kind = np.empty(n_commodities, dtype=np.int8)
    kind[:n_private] = CommodityKind.PRIVATE_GOOD
    kind[n_private : n_private + n_public] = CommodityKind.PUBLIC_GOOD
    kind[n_private + n_public : natural] = CommodityKind.INTERMEDIATE
    kind[natural] = CommodityKind.NATURAL_RESOURCE
    kind[labor] = CommodityKind.LABOR

    endowment = np.zeros(n_commodities)
    endowment[natural] = draw(ENDOWMENT)
    endowment[labor] = draw(ENDOWMENT)

    producible = list(range(natural))
    usable = list(range(labor))
    n_units = draw(st.integers(min_value=2, max_value=6))

    outputs = [0]
    rows = [[(labor, draw(COEFFICIENT))]]
    for _ in range(n_units - 1):
        outputs.append(draw(st.sampled_from(producible)))
        chosen = draw(
            st.lists(st.sampled_from(usable), min_size=0, max_size=3, unique=True)
        )
        rows.append([(commodity, draw(COEFFICIENT)) for commodity in chosen])
        rows[-1].append((labor, draw(COEFFICIENT)))

    offsets = np.zeros(n_units + 1, dtype=np.int64)
    np.cumsum([len(row) for row in rows], out=offsets[1:])
    n_consumers = draw(st.integers(min_value=1, max_value=3))

    economy = Economy(
        period=0,
        commodity_id=np.arange(n_commodities, dtype=np.int64),
        commodity_kind=kind,
        endowment=endowment,
        unit_id=np.arange(n_units, dtype=np.int64),
        unit_group=np.zeros(n_units, dtype=np.int64),
        output_commodity=np.array(outputs, dtype=np.int64),
        technology_kind=np.full(n_units, TechnologyKind.LEONTIEF, dtype=np.int8),
        technology_scale=np.ones(n_units),
        input_offsets=offsets,
        input_commodity=np.array(
            [commodity for row in rows for commodity, _ in row], dtype=np.int64
        ),
        input_coefficient=np.array([value for row in rows for _, value in row]),
        consumer_id=np.arange(n_consumers, dtype=np.int64),
        consumer_group=np.zeros(n_consumers, dtype=np.int64),
    )
    weights = np.zeros(n_commodities)
    for commodity in range(n_private + n_public):
        weights[commodity] = draw(WEIGHT)
    return economy, weights, labor


GENERATED = settings(
    max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)


class TestGeneratedEconomies:
    @given(leontief_economy())
    @GENERATED
    def test_the_plan_balances_every_commodity(self, case):
        economy, weights, _ = case
        result = reference_solution(economy, MaximizeWeightedConsumption(weights))
        balance = (
            result.plan.total_output(economy)
            + np.asarray(economy.endowment)
            - result.plan.total_input_use(economy)
            - result.plan.total_consumption(economy)
            - np.asarray(result.plan.provision)
        )
        assert balance.min() >= -EXACT

    @given(leontief_economy())
    @GENERATED
    def test_shadow_prices_are_not_negative(self, case):
        economy, weights, _ = case
        result = reference_solution(economy, MaximizeWeightedConsumption(weights))
        assert result.plan.valuation[SHADOW_PRICE].min() >= 0.0

    @given(leontief_economy())
    @GENERATED
    def test_the_optimum_equals_the_endowment_valued_at_its_shadow_prices(self, case):
        economy, weights, _ = case
        result = reference_solution(economy, MaximizeWeightedConsumption(weights))
        valued = float(
            np.dot(result.plan.valuation[SHADOW_PRICE], np.asarray(economy.endowment))
        )
        assert valued == pytest.approx(
            result.objective_value, abs=scaled_tolerance(result.objective_value)
        )

    @given(leontief_economy())
    @GENERATED
    def test_no_unit_can_be_run_below_the_shadow_cost_of_its_inputs(self, case):
        economy, weights, _ = case
        result = reference_solution(economy, MaximizeWeightedConsumption(weights))
        shadow = result.plan.valuation[SHADOW_PRICE]
        for unit in range(economy.n_units):
            window = economy.inputs_of(unit)
            cost = float(
                np.dot(
                    np.asarray(economy.input_coefficient)[window],
                    shadow[np.asarray(economy.input_commodity)[window]],
                )
            )
            revenue = float(shadow[economy.output_commodity[unit]])
            assert cost - revenue >= -scaled_tolerance(max(cost, revenue))
            if result.plan.output[unit] > 1e-6:
                assert cost == pytest.approx(revenue, abs=scaled_tolerance(max(cost, revenue)))

    @given(leontief_economy())
    @GENERATED
    def test_a_commodity_left_over_is_worth_nothing(self, case):
        economy, weights, _ = case
        result = reference_solution(economy, MaximizeWeightedConsumption(weights))
        shadow = result.plan.valuation[SHADOW_PRICE]
        slack = commodity_slack(
            economy, np.asarray(result.plan.output), final_use_of(economy, result.plan)
        )
        for commodity in range(economy.n_commodities):
            tolerance = scaled_tolerance(slack[commodity])
            assert slack[commodity] <= tolerance or shadow[commodity] <= tolerance

    @given(leontief_economy())
    @GENERATED
    def test_a_consumed_commodity_is_worth_at_least_its_weight(self, case):
        economy, weights, _ = case
        result = reference_solution(economy, MaximizeWeightedConsumption(weights))
        shadow = result.plan.valuation[SHADOW_PRICE]
        consumable = np.flatnonzero(weights != 0.0)
        assert np.all(
            shadow[consumable] - weights[consumable] >= -scaled_tolerance(weights.max())
        )

    @given(leontief_economy())
    @GENERATED
    def test_labour_is_used_to_the_last_unit(self, case):
        economy, weights, labor = case
        result = reference_solution(economy, MaximizeWeightedConsumption(weights))
        slack = commodity_slack(
            economy, np.asarray(result.plan.output), final_use_of(economy, result.plan)
        )
        assert abs(slack[labor]) <= scaled_tolerance(economy.endowment[labor])

    @given(leontief_economy())
    @GENERATED
    def test_raising_any_unit_by_one_percent_breaks_a_constraint(self, case):
        economy, weights, labor = case
        result = reference_solution(economy, MaximizeWeightedConsumption(weights))
        output = np.asarray(result.plan.output)
        final = final_use_of(economy, result.plan)
        coefficients = np.asarray(economy.input_coefficient)
        commodities = np.asarray(economy.input_commodity)
        for unit in range(economy.n_units):
            window = economy.inputs_of(unit)
            drawn = coefficients[window][commodities[window] == labor].sum()
            extra_labor = 0.01 * output[unit] * drawn
            if extra_labor <= PERTURBATION_FLOOR:
                continue
            raised = output.copy()
            raised[unit] *= 1.01
            assert commodity_slack(economy, raised, final).min() < -PERTURBATION_FLOOR / 2

    @given(leontief_economy())
    @GENERATED
    def test_meeting_half_the_optimum_costs_at_most_half_the_labour(self, case):
        economy, weights, labor = case
        best = reference_solution(economy, MaximizeWeightedConsumption(weights))
        targets = np.where(weights != 0.0, 0.5 * final_use_of(economy, best.plan), 0.0)
        cheapest = reference_solution(economy, MinimizeLabor(targets))
        spent = float(best.plan.total_input_use(economy)[labor])
        assert cheapest.objective_value <= 0.5 * spent + scaled_tolerance(spent)
        assert cheapest.objective_value == pytest.approx(
            float(cheapest.plan.total_input_use(economy)[labor]),
            abs=scaled_tolerance(spent),
        )


@pytest.fixture(scope="module")
def dep1ex01():
    if not dep1ex_available(1):
        pytest.skip(f"dep1ex01 archive not found at {dep1ex_path(1)}")
    return load_dep1ex(dep1ex_path(1))


@pytest.fixture(scope="module")
def comparison(dep1ex01):
    """``(economy, linearised, participatory plan, reference plan, weights, seconds)``."""
    participatory = run(HahnelSlides2020(), dep1ex01, seed=0).plan
    linearised = linearize(dep1ex01, participatory)

    kinds = np.asarray(dep1ex01.commodity_kind)
    consumable = np.isin(kinds, [int(CommodityKind.PRIVATE_GOOD), int(CommodityKind.PUBLIC_GOOD)])
    weights = np.where(consumable, participatory.valuation[INDICATIVE_PRICE], 0.0)

    started = time.perf_counter()
    reference = run(
        ReferenceProcedure(MaximizeWeightedConsumption(weights)), linearised, seed=0
    ).plan
    seconds = time.perf_counter() - started
    return dep1ex01, linearised, participatory, reference, weights, seconds


@pytest.mark.slow
class TestAgainstDep1ex:
    """The criterion the whole design rests on: two mechanisms, one economy, one set of scores.

    A participatory-planning run and a linear program are not comparable on the economy as it
    stands, because one reads the technology as Cobb-Douglas and the other as Leontief. The
    linearising tool is what closes that gap, and it does so by making the mechanism's own
    input mix the fixed technology. The comparison below is therefore between the participatory
    plan and the best plan available under the technology that participatory plan chose.
    """

    def test_both_plans_validate_against_the_linearised_economy(self, comparison):
        _, linearised, participatory, reference, _, _ = comparison
        participatory.validate(linearised)
        reference.validate(linearised)

    def test_the_same_accessors_read_both_plans(self, comparison):
        _, linearised, participatory, reference, _, _ = comparison
        for plan in (participatory, reference):
            assert plan.total_output(linearised).shape == (linearised.n_commodities,)
            assert np.all(np.isfinite(plan.total_output(linearised)))
            assert plan.endowment_use(linearised).shape == (linearised.n_commodities,)
            assert np.all(np.isfinite(plan.endowment_use(linearised)))

    def test_the_reference_scores_at_least_as_high_on_the_declared_weights(self, comparison):
        economy, linearised, participatory, reference, weights, _ = comparison
        by_participation = float(np.dot(weights, final_use_of(economy, participatory)))
        by_reference = float(np.dot(weights, final_use_of(linearised, reference)))
        assert by_reference >= by_participation

    def test_it_solves_inside_the_time_the_construction_sheet_allows(self, comparison):
        *_, seconds = comparison
        assert seconds < DEP1EX_SECONDS_ALLOWED
