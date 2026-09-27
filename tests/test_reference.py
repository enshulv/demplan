"""The centralised optimum: a linear program over a Leontief economy.

Two kinds of check run here. The hand-built economy is small enough that the optimum, the
objective value and every dual variable are written out from the algebra in this module's
docstring, so the expected numbers do not come from the solver. The generated economies are
checked against the optimality conditions of a linear program -- material balance, dual
feasibility, complementary slackness and strong duality -- which are properties of the answer
rather than a second copy of the assembly code.

The hand-built economy, ``build_bread_economy``:

* commodity 0 is bread, a consumption good; commodity 1 is flour, an intermediate good;
  commodity 2 is labour;
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

The economy carries no class of any commodity. Which commodities a labour count totals and
which ones are used in common are declared on the objective.
"""

from __future__ import annotations

import dataclasses
import time

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from demplan import (
    COBB_DOUGLAS,
    INDICATIVE_PRICE,
    LEONTIEF,
    SHADOW_PRICE,
    Economy,
    Plan,
    run,
)
from demplan.objectives import MaximizeWeightedConsumption, MinimizeLabor
from demplan.plan import AllocatedPlan, StatedPlan, require_comparable
from demplan.prefabs import hahnel
from demplan.prefabs.hahnel import HahnelBook2021
from demplan.reference import (
    ReferenceInfeasible,
    ReferenceProcedure,
    ReferenceResult,
    reference_solution,
)
from demplan.tools.linearize import linearize

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

COUNT_LABOUR = np.array([WORK], dtype=np.int64)
"""What a labour-minimising objective totals on the bread economy: commodity 2."""


def build_bread_economy(
    labor_endowment: float = 12.0, n_consumers: int = 2, output_coefficient=(1.0, 1.0)
) -> Economy:
    """The three-commodity economy the module docstring solves by hand."""
    return Economy(
        period=0,
        commodity_id=np.arange(N_BREAD_COMMODITIES, dtype=np.int64),
        endowment=np.array([0.0, 0.0, labor_endowment]),
        unit_id=np.arange(2, dtype=np.int64),
        technology_kind=[LEONTIEF, LEONTIEF],
        technology_scale=np.ones(2),
        input_offsets=np.array([0, 2, 3], dtype=np.int64),
        input_commodity=np.array([FLOUR, WORK, WORK], dtype=np.int64),
        input_coefficient=np.array([0.5, 1.0, 2.0]),
        output_offsets=np.array([0, 1, 2], dtype=np.int64),
        output_commodity=np.array([BREAD, FLOUR], dtype=np.int64),
        output_coefficient=np.array(output_coefficient, dtype=np.float64),
        consumer_id=np.arange(n_consumers, dtype=np.int64),
    )


def minimize_labour(targets) -> MinimizeLabor:
    """``MinimizeLabor`` over the bread economy's labour, commodity 2."""
    return MinimizeLabor(targets, COUNT_LABOUR)


def bread_weights() -> np.ndarray:
    weights = np.zeros(N_BREAD_COMMODITIES)
    weights[BREAD] = 1.0
    return weights


def commodity_slack(economy: Economy, output: np.ndarray, final: np.ndarray) -> np.ndarray:
    """``supply + endowment - input use - final use`` per commodity, computed from scratch.

    This repeats the balance the linear program constrains rather than calling the tools the
    implementation uses, so an error shared with the implementation cannot cancel out. Every
    unit here has one output entry, and ``output`` is that entry's quantity: the unit ran
    ``output / output_coefficient`` times, and each run draws ``input_coefficient``.
    """
    n_commodities = economy.n_commodities
    owner = np.repeat(np.arange(economy.n_units), np.diff(economy.input_offsets))
    activity = np.asarray(output) / np.asarray(economy.output_coefficient)
    supply = np.bincount(
        economy.output_commodity, weights=output, minlength=n_commodities
    ) + np.asarray(economy.endowment)
    drawn = np.bincount(
        economy.input_commodity,
        weights=np.asarray(economy.input_coefficient) * activity[owner],
        minlength=n_commodities,
    )
    return supply - drawn - final


def final_use_of(economy: Economy, plan: Plan) -> np.ndarray:
    """Final consumption per commodity: what consumer units get plus what they use in common."""
    return plan.total_consumption(economy) + np.asarray(plan.shared_use)


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
        np.testing.assert_allclose(result.plan.shared_use, np.zeros(3), atol=EXACT)

    def test_input_use_follows_the_leontief_coefficients(self):
        result = reference_solution(
            build_bread_economy(), MaximizeWeightedConsumption(bread_weights())
        )
        np.testing.assert_allclose(result.plan.input_use, [3.0, 6.0, 6.0], atol=EXACT)

    def test_labour_is_used_to_the_last_unit(self):
        economy = build_bread_economy()
        result = reference_solution(economy, MaximizeWeightedConsumption(bread_weights()))
        np.testing.assert_allclose(
            result.plan.endowment_use(economy, COUNT_LABOUR), [0.0, 0.0, 12.0], atol=EXACT
        )

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
            build_bread_economy(labor_endowment=20.0), minimize_labour(self.targets())
        )
        assert result.status == "optimal"
        assert result.objective_value == pytest.approx(12.0, abs=EXACT)
        np.testing.assert_allclose(result.plan.output, [6.0, 3.0], atol=EXACT)

    def test_the_target_is_met_exactly(self):
        economy = build_bread_economy(labor_endowment=20.0)
        result = reference_solution(economy, minimize_labour(self.targets()))
        np.testing.assert_allclose(final_use_of(economy, result.plan), [6.0, 0.0, 0.0], atol=EXACT)

    def test_shadow_prices_are_labour_saved_per_free_unit(self):
        result = reference_solution(
            build_bread_economy(labor_endowment=20.0), minimize_labour(self.targets())
        )
        np.testing.assert_allclose(result.plan.valuation[SHADOW_PRICE], [2.0, 2.0, 0.0], atol=EXACT)

    def test_labour_left_over_is_not_used(self):
        economy = build_bread_economy(labor_endowment=20.0)
        result = reference_solution(economy, minimize_labour(self.targets()))
        np.testing.assert_allclose(
            result.plan.endowment_use(economy, COUNT_LABOUR), [0.0, 0.0, 12.0], atol=EXACT
        )

    def test_a_target_beyond_the_endowment_is_infeasible(self):
        targets = np.zeros(N_BREAD_COMMODITIES)
        targets[BREAD] = 100.0
        with pytest.raises(ReferenceInfeasible):
            reference_solution(build_bread_economy(), minimize_labour(targets))

    def test_a_negative_target_is_refused_and_the_message_names_the_commodity(self):
        """A floor of -3 on the flour would report 6 labour where every feasible plan spends 12.

        The floor becomes the lower bound on that commodity's final consumption, so a negative
        one lets the program cover the 3 flour six bread draws by consuming -3 of it instead of
        producing it.
        """
        targets = self.targets()
        targets[FLOUR] = -3.0
        with pytest.raises(ValueError, match=f"commodity {FLOUR}"):
            minimize_labour(targets)


class TestHandSolvedChoiceBetweenTechniques:
    """Two ways to make the same good, and the objective decides which one runs.

    Commodity 0 is a consumption good, commodity 1 a natural resource, commodity 2 labour, with
    20 of each endowment. Unit 0 makes one commodity 0 from 3 labour. Unit 1 makes one from
    1 labour and 4 of the natural resource. Requiring 4 of commodity 0 and minimising labour
    runs unit 1 four times for 4 labour, because the natural resource is not a labour cost and
    20 of it is enough for the 16 that takes.

    An objective that totalled natural resources alongside labour prices unit 1 at 5 and
    unit 0 at 3, runs unit 0 instead, and reaches 12. That is why this economy is here: the
    bread economy has no natural resource, so it cannot tell the two declarations apart.
    """

    N_COMMODITIES = 3
    GOOD, NATURE, WORK = 0, 1, 2

    def build(self) -> Economy:
        return Economy(
            period=0,
            commodity_id=np.arange(self.N_COMMODITIES, dtype=np.int64),
            endowment=np.array([0.0, 20.0, 20.0]),
            unit_id=np.arange(2, dtype=np.int64),
            technology_kind=[LEONTIEF, LEONTIEF],
            technology_scale=np.ones(2),
            input_offsets=np.array([0, 1, 3], dtype=np.int64),
            input_commodity=np.array([self.WORK, self.NATURE, self.WORK], dtype=np.int64),
            input_coefficient=np.array([3.0, 4.0, 1.0]),
            output_offsets=np.array([0, 1, 2], dtype=np.int64),
            output_commodity=np.array([self.GOOD, self.GOOD], dtype=np.int64),
            output_coefficient=np.ones(2),
            consumer_id=np.arange(2, dtype=np.int64),
        )

    def targets(self) -> np.ndarray:
        targets = np.zeros(self.N_COMMODITIES)
        targets[self.GOOD] = 4.0
        return targets

    def solved(self, counted=None) -> ReferenceResult:
        if counted is None:
            counted = np.array([self.WORK], dtype=np.int64)
        return reference_solution(self.build(), MinimizeLabor(self.targets(), counted))

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

    def test_counting_the_natural_resource_too_runs_the_other_technique(self):
        """The declaration decides the answer: ``counted`` is what the objective totals."""
        both = np.array([self.NATURE, self.WORK], dtype=np.int64)
        result = self.solved(counted=both)
        assert result.objective_value == pytest.approx(12.0, abs=EXACT)
        np.testing.assert_allclose(result.plan.output, [4.0, 0.0], atol=EXACT)

    def test_the_order_of_the_counted_commodities_does_not_matter(self):
        reversed_order = np.array([self.WORK, self.NATURE], dtype=np.int64)
        assert self.solved(counted=reversed_order).objective_value == pytest.approx(
            12.0, abs=EXACT
        )


class PairDeclaredObjective:
    """A researcher's own labour-minimising objective, declared by attribute rather than type.

    ``weights`` returns zeros, as a labour-minimising objective does, so an assembly that reads
    this objective as a maximisation maximises nothing. Either attribute is left off entirely
    when it is not supplied, which is what an objective that declares half the pair looks like.
    ``allocate`` splits every commodity the floor sits on evenly, as the shipped objectives do.
    """

    name = "pair_declared"

    def __init__(self, lower_bound=None, counted_commodities=None):
        if lower_bound is not None:
            self.final_demand_lower_bound = np.asarray(lower_bound, dtype=np.float64)
        if counted_commodities is not None:
            self.counted_commodities = counted_commodities

    def weights(self, economy: Economy) -> np.ndarray:
        return np.zeros(economy.n_commodities, dtype=np.float64)

    def allocate(self, economy: Economy, aggregate: np.ndarray):
        floor = getattr(self, "final_demand_lower_bound", np.zeros(economy.n_commodities))
        return MaximizeWeightedConsumption(floor).allocate(economy, aggregate)


class TestMinimisationDeclaredByAttribute:
    """The pair of attributes is what makes a program minimise, so half a pair is refused."""

    def targets(self) -> np.ndarray:
        targets = np.zeros(N_BREAD_COMMODITIES)
        targets[BREAD] = 6.0
        return targets

    def test_both_attributes_together_minimise_like_the_built_in_objective(self):
        objective = PairDeclaredObjective(
            lower_bound=self.targets(), counted_commodities=COUNT_LABOUR
        )
        result = reference_solution(build_bread_economy(labor_endowment=20.0), objective)
        assert result.objective_value == pytest.approx(12.0, abs=EXACT)
        np.testing.assert_allclose(result.plan.output, [6.0, 3.0], atol=EXACT)

    def test_a_lower_bound_without_counted_commodities_is_refused(self):
        """Read as a maximisation, this objective maximises zero and reports an empty plan."""
        objective = PairDeclaredObjective(lower_bound=self.targets())
        with pytest.raises(ValueError, match="counted_commodities"):
            reference_solution(build_bread_economy(labor_endowment=20.0), objective)

    def test_counted_commodities_without_a_lower_bound_is_refused(self):
        objective = PairDeclaredObjective(counted_commodities=COUNT_LABOUR)
        with pytest.raises(ValueError, match="final_demand_lower_bound"):
            reference_solution(build_bread_economy(labor_endowment=20.0), objective)

    def test_the_message_names_the_objective_that_declared_half_the_pair(self):
        objective = PairDeclaredObjective(lower_bound=self.targets())
        with pytest.raises(ValueError, match="pair_declared"):
            reference_solution(build_bread_economy(labor_endowment=20.0), objective)


class TestTheDeclaredFloorIsCheckedWhereTheProgramReadsIt:
    """A floor is checked at the program, not only in the objective that happens to ship here.

    ``MinimizeLabor`` refuses a negative floor, but ``reference_solution`` recognises a
    minimisation by its two attributes, so an objective a researcher wrote reaches the program
    with that check unrun. Floor ``[6, -3, 0]`` on this economy, at a labour endowment of 20,
    reports an ``objective_value`` of 6 where the sound floor reports 12, on output ``[6, 0]``
    that draws 3 of commodity 1 while producing none of it, with status ``"optimal"``.

    Which commodities a floor sits on is the researcher's statement. A floor on flour, an
    intermediate good, is a floor like any other, and the plan records it as final use.
    """

    def floor(self, commodity: int, value: float) -> np.ndarray:
        targets = np.zeros(N_BREAD_COMMODITIES)
        targets[BREAD] = 6.0
        targets[commodity] = value
        return targets

    def solve_with(self, targets: np.ndarray) -> ReferenceResult:
        objective = PairDeclaredObjective(lower_bound=targets, counted_commodities=COUNT_LABOUR)
        return reference_solution(build_bread_economy(labor_endowment=20.0), objective)

    def test_a_well_formed_floor_still_reaches_the_optimum(self):
        """The check refuses malformed declarations without narrowing the sound ones."""
        result = self.solve_with(self.floor(BREAD, 6.0))
        assert result.status == "optimal"
        assert result.objective_value == pytest.approx(12.0, abs=EXACT)
        np.testing.assert_allclose(result.plan.output, [6.0, 3.0], atol=EXACT)

    def test_a_negative_floor_is_refused(self):
        with pytest.raises(ValueError, match="cannot be negative"):
            self.solve_with(self.floor(FLOUR, -3.0))

    def test_the_negative_floor_message_names_the_objective_and_the_commodity(self):
        with pytest.raises(ValueError, match=r"pair_declared.*commodity 1 carries -3\.0"):
            self.solve_with(self.floor(FLOUR, -3.0))

    def test_a_floor_on_an_intermediate_good_is_met_and_recorded_as_final_use(self):
        """Six bread and three flour for final use: 6 flour made, 12 + 6 labour spent."""
        result = self.solve_with(self.floor(FLOUR, 3.0))
        assert result.objective_value == pytest.approx(18.0, abs=EXACT)
        np.testing.assert_allclose(result.plan.output, [6.0, 6.0], atol=EXACT)
        economy = build_bread_economy(labor_endowment=20.0)
        np.testing.assert_allclose(
            final_use_of(economy, result.plan), [6.0, 3.0, 0.0], atol=EXACT
        )

    def test_the_built_in_objective_meets_a_floor_on_an_intermediate_good_too(self):
        economy = build_bread_economy(labor_endowment=20.0)
        result = reference_solution(economy, minimize_labour(self.floor(FLOUR, 3.0)))
        assert result.objective_value == pytest.approx(18.0, abs=EXACT)
        np.testing.assert_array_equal(result.plan.consumption_commodity, [BREAD, FLOUR])

    @pytest.mark.parametrize("targets", [(6.0, -3.0, 0.0), (6.0, np.nan, 0.0)])
    def test_no_malformed_floor_reaches_the_solver(self, targets):
        """Whatever the number would have been, a malformed floor never produces a result."""
        with pytest.raises(ValueError):
            self.solve_with(np.array(targets, dtype=np.float64))

    def test_minimize_labor_still_refuses_a_negative_floor_at_construction(self):
        """The earlier check stays: it fails nearer to where the researcher wrote the floor."""
        with pytest.raises(ValueError, match="cannot be negative"):
            minimize_labour(self.floor(FLOUR, -3.0))

    def test_a_maximising_objective_is_not_put_through_the_floor_check(self):
        """The check reads ``final_demand_lower_bound``, which a maximisation does not carry."""
        result = reference_solution(
            build_bread_economy(), MaximizeWeightedConsumption(bread_weights())
        )
        assert result.objective_value == pytest.approx(6.0, abs=EXACT)


class TestTheDeclaredFloorMustBeReadable:
    """A non-finite floor is the one malformed floor the other two checks read as well formed.

    ``NaN < 0`` is false, so the non-negative check finds nothing; ``NaN != 0`` is true, so the
    entry reads as a floor sitting on the commodity it was written on. HiGHS takes a NaN bound
    as no bound at all, so the program would report an optimum that meets none of the declared
    floor and says so nowhere.
    """

    def floor(self, commodity: int, value: float) -> np.ndarray:
        targets = np.zeros(N_BREAD_COMMODITIES)
        targets[BREAD] = 6.0
        targets[commodity] = value
        return targets

    def solve_with(self, targets: np.ndarray) -> ReferenceResult:
        objective = PairDeclaredObjective(lower_bound=targets, counted_commodities=COUNT_LABOUR)
        return reference_solution(build_bread_economy(labor_endowment=20.0), objective)

    @pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
    def test_a_non_finite_floor_on_a_private_good_is_refused(self, value):
        with pytest.raises(ValueError, match="finite"):
            self.solve_with(self.floor(BREAD, value))

    def test_the_message_names_the_objective_and_the_attribute(self):
        with pytest.raises(ValueError, match=r"pair_declared: final_demand_lower_bound"):
            self.solve_with(self.floor(BREAD, np.nan))

    def test_an_unreadable_entry_is_reported_before_the_commodity_it_sits_on(self):
        """A floor nobody can read is refused for being unreadable, whatever it sits on."""
        with pytest.raises(ValueError, match="finite"):
            self.solve_with(self.floor(FLOUR, np.nan))

    def test_a_well_formed_floor_still_reaches_the_optimum(self):
        result = self.solve_with(self.floor(BREAD, 6.0))
        assert result.status == "optimal"
        assert result.objective_value == pytest.approx(12.0, abs=EXACT)

    def test_minimize_labor_refuses_a_non_finite_floor_at_construction(self):
        """The earlier check stays: it fails nearer to where the researcher wrote the floor."""
        with pytest.raises(ValueError, match="finite"):
            minimize_labour(self.floor(BREAD, np.nan))


class TestTheCountedCommoditiesAreCommodityIndices:
    """``counted_commodities`` names the commodities whose input use the objective totals.

    The cost vector counts an input when its commodity is listed. An index outside the
    commodity table matches no input, so a list of them makes every coefficient zero and the
    program reports an objective value of zero for a plan that spends whatever it likes.
    """

    def targets(self) -> np.ndarray:
        targets = np.zeros(N_BREAD_COMMODITIES)
        targets[BREAD] = 6.0
        return targets

    def solve_with(self, counted) -> ReferenceResult:
        objective = PairDeclaredObjective(lower_bound=self.targets(), counted_commodities=counted)
        return reference_solution(build_bread_economy(labor_endowment=20.0), objective)

    @pytest.mark.parametrize("index", [99, -1, 3])
    def test_an_index_outside_the_commodity_table_is_refused(self, index):
        with pytest.raises(ValueError, match="counted_commodities"):
            self.solve_with(np.array([WORK, index], dtype=np.int64))

    def test_the_message_carries_the_index_it_was_given(self):
        with pytest.raises(ValueError, match="99"):
            self.solve_with(np.array([99], dtype=np.int64))

    def test_a_label_instead_of_indices_is_refused(self):
        with pytest.raises(ValueError, match="counted_commodities"):
            self.solve_with("labor")

    def test_a_float_array_is_refused(self):
        with pytest.raises(ValueError, match="counted_commodities"):
            self.solve_with(np.array([2.0]))

    def test_a_duplicate_index_is_refused(self):
        with pytest.raises(ValueError, match="counted_commodities"):
            self.solve_with(np.array([WORK, WORK], dtype=np.int64))

    def test_the_labour_the_built_in_objective_declares_is_accepted(self):
        result = self.solve_with(COUNT_LABOUR)
        assert result.objective_value == pytest.approx(12.0, abs=EXACT)

    def test_any_declared_commodity_is_accepted(self):
        """Totalling up the intermediate good is a different objective, not a malformed one:
        this economy draws 3 of it to meet the floor of 6 on bread."""
        result = self.solve_with(np.array([FLOUR], dtype=np.int64))
        assert result.objective_value == pytest.approx(3.0, abs=EXACT)


class DeclaredWeightingObjective:
    """A researcher's own maximisation: the weights it declared, handed over unchecked.

    ``MaximizeWeightedConsumption`` checks its own weights on the way out, and a program is
    read as a maximisation by the absence of the minimisation pair rather than by type, so an
    objective written outside this package reaches the program with whatever it declared.
    """

    name = "declared_weighting"

    def __init__(self, weights) -> None:
        self.declared = np.asarray(weights, dtype=np.float64)

    def weights(self, economy: Economy) -> np.ndarray:
        return self.declared

    def allocate(self, economy: Economy, aggregate: np.ndarray):
        return MaximizeWeightedConsumption(self.declared).allocate(economy, aggregate)


class TestTheDeclaredWeightsAreCheckedWhereTheProgramReadsThem:
    """The weights of a maximisation are a declaration the program reads, so it checks them.

    They decide the same two things the floor of a minimisation decides: which commodities
    become final-consumption variables, and what the reported objective value counts. A
    non-finite weight is not a declaration anyone can read. Which commodities carry weight is
    the researcher's statement, and each one comes back as a consumption column of the plan.
    """

    def weights(self, commodity: int, value: float) -> np.ndarray:
        weights = np.zeros(N_BREAD_COMMODITIES)
        weights[commodity] = value
        return weights

    def solve_with(self, weights: np.ndarray) -> ReferenceResult:
        return reference_solution(build_bread_economy(), DeclaredWeightingObjective(weights))

    def test_a_weight_on_labour_is_optimised_and_recorded(self):
        """Labour consumed directly: all 12 of it, and the plan says so."""
        result = self.solve_with(self.weights(WORK, 1.0))
        assert result.objective_value == pytest.approx(12.0, abs=EXACT)
        np.testing.assert_allclose(result.plan.output, [0.0, 0.0], atol=EXACT)
        np.testing.assert_array_equal(result.plan.consumption_commodity, [WORK])
        np.testing.assert_allclose(
            final_use_of(build_bread_economy(), result.plan), [0.0, 0.0, 12.0], atol=EXACT
        )

    def test_a_weight_on_an_intermediate_good_is_optimised_and_recorded(self):
        """Flour for final use: 2 labour each, so 6 of it from 12 labour."""
        result = self.solve_with(self.weights(FLOUR, 1.0))
        assert result.objective_value == pytest.approx(6.0, abs=EXACT)
        np.testing.assert_allclose(
            final_use_of(build_bread_economy(), result.plan), [0.0, 6.0, 0.0], atol=EXACT
        )

    def test_the_message_names_the_objective_and_the_attribute(self):
        with pytest.raises(ValueError, match=r"declared_weighting: weights"):
            self.solve_with(self.weights(WORK, np.nan))

    @pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
    def test_a_non_finite_weight_is_refused(self, value):
        with pytest.raises(ValueError, match="finite"):
            self.solve_with(self.weights(BREAD, value))

    def test_a_negative_weight_on_a_consumable_commodity_still_reaches_the_solver(self):
        """A negative weight is a penalty term, which is a coherent thing to declare.

        Refusing it would put a commitment about what a social welfare function may say into
        the layer that is meant to hold none, so the sign of a maximisation weight is the
        researcher's business. The program reads it as one: consumption of a penalised
        commodity goes to its lower bound of zero.
        """
        result = self.solve_with(self.weights(BREAD, -1.0))
        assert result.status == "optimal"
        assert result.objective_value == pytest.approx(0.0, abs=EXACT)

    def test_well_formed_weights_still_reach_the_optimum(self):
        result = self.solve_with(self.weights(BREAD, 1.0))
        assert result.status == "optimal"
        assert result.objective_value == pytest.approx(6.0, abs=EXACT)
        np.testing.assert_allclose(result.plan.output, [6.0, 3.0], atol=EXACT)

    def test_the_built_in_maximisation_still_reaches_the_optimum(self):
        result = reference_solution(
            build_bread_economy(), MaximizeWeightedConsumption(bread_weights())
        )
        assert result.objective_value == pytest.approx(6.0, abs=EXACT)


class TestRefusedInputs:
    def test_a_cobb_douglas_economy_is_refused_and_points_at_the_linearising_tool(self):
        cobb_douglas = dataclasses.replace(
            build_bread_economy(), technology_kind=[COBB_DOUGLAS, COBB_DOUGLAS]
        )
        with pytest.raises(ValueError, match="demplan.tools.linearize"):
            reference_solution(cobb_douglas, MaximizeWeightedConsumption(bread_weights()))

    def test_one_unit_under_another_label_is_refused_and_named(self):
        mixed = dataclasses.replace(
            build_bread_economy(), technology_kind=[LEONTIEF, "my_own_technology"]
        )
        with pytest.raises(ValueError, match=r"unit 1.*my_own_technology"):
            reference_solution(mixed, MaximizeWeightedConsumption(bread_weights()))

    def test_the_hahnel_label_is_not_leontief(self):
        relabelled = dataclasses.replace(
            build_bread_economy(), technology_kind=[hahnel.TECHNOLOGY, LEONTIEF]
        )
        with pytest.raises(ValueError, match="unit 0"):
            reference_solution(relabelled, MaximizeWeightedConsumption(bread_weights()))

    def test_a_unit_with_two_outputs_is_refused(self):
        """Unit 0 bakes bread and makes flour as a by-product: a joint product."""
        joint = dataclasses.replace(
            build_bread_economy(),
            output_offsets=np.array([0, 2, 3], dtype=np.int64),
            output_commodity=np.array([BREAD, FLOUR, FLOUR], dtype=np.int64),
            output_coefficient=np.array([1.0, 0.25, 1.0]),
        )
        with pytest.raises(ValueError) as refused:
            reference_solution(joint, MaximizeWeightedConsumption(bread_weights()))
        message = str(refused.value)
        assert "unit 0" in message
        assert "joint products are not supported by the reference solution yet" in message

    def test_a_commodity_produced_from_nothing_makes_the_program_unbounded(self):
        economy = Economy(
            period=0,
            commodity_id=np.arange(2, dtype=np.int64),
            endowment=np.array([0.0, 10.0]),
            unit_id=np.arange(1, dtype=np.int64),
            technology_kind=[LEONTIEF],
            technology_scale=np.ones(1),
            input_offsets=np.array([0, 0], dtype=np.int64),
            input_commodity=np.zeros(0, dtype=np.int64),
            input_coefficient=np.zeros(0),
            output_offsets=np.array([0, 1], dtype=np.int64),
            output_commodity=np.array([0], dtype=np.int64),
            output_coefficient=np.ones(1),
            consumer_id=np.arange(1, dtype=np.int64),
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


OUTPUT_COEFFICIENT = st.floats(
    min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False
)


@st.composite
def leontief_economy(draw, scaled_outputs: bool = False):
    """A random Leontief economy with a bounded, feasible maximisation on it.

    The layout is private goods, then public goods, then intermediate goods, then one natural
    resource and one kind of labour, which is the section order dep1ex uses. Two properties are
    built in so that the optimum exists and the tests below can say something sharp about it:
    every unit draws labour, which bounds output, and unit 0 turns labour straight into private
    good 0, which is why labour is fully used at every optimum.

    Every unit's output coefficient is 1 unless ``scaled_outputs`` is set, in which case each
    is drawn from :data:`OUTPUT_COEFFICIENT` after every other draw.
    """
    n_private = draw(st.integers(min_value=1, max_value=2))
    n_public = draw(st.integers(min_value=0, max_value=2))
    n_intermediate = draw(st.integers(min_value=0, max_value=2))
    natural = n_private + n_public + n_intermediate
    labor = natural + 1
    n_commodities = labor + 1

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
    weights = np.zeros(n_commodities)
    for commodity in range(n_private + n_public):
        weights[commodity] = draw(WEIGHT)
    output_coefficient = np.ones(n_units)
    if scaled_outputs:
        output_coefficient = np.array([draw(OUTPUT_COEFFICIENT) for _ in range(n_units)])

    economy = Economy(
        period=0,
        commodity_id=np.arange(n_commodities, dtype=np.int64),
        endowment=endowment,
        unit_id=np.arange(n_units, dtype=np.int64),
        technology_kind=[LEONTIEF] * n_units,
        technology_scale=np.ones(n_units),
        input_offsets=offsets,
        input_commodity=np.array(
            [commodity for row in rows for commodity, _ in row], dtype=np.int64
        ),
        input_coefficient=np.array([value for row in rows for _, value in row]),
        output_offsets=np.arange(n_units + 1, dtype=np.int64),
        output_commodity=np.array(outputs, dtype=np.int64),
        output_coefficient=output_coefficient,
        consumer_id=np.arange(n_consumers, dtype=np.int64),
    )
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
            - np.asarray(result.plan.shared_use)
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
            revenue = float(
                economy.output_coefficient[unit] * shadow[economy.output_commodity[unit]]
            )
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
            extra_labor = 0.01 * output[unit] / economy.output_coefficient[unit] * drawn
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
        cheapest = reference_solution(
            economy, MinimizeLabor(targets, np.array([labor], dtype=np.int64))
        )
        spent = float(best.plan.total_input_use(economy)[labor])
        assert cheapest.objective_value <= 0.5 * spent + scaled_tolerance(spent)
        assert cheapest.objective_value == pytest.approx(
            float(cheapest.plan.total_input_use(economy)[labor]),
            abs=scaled_tolerance(spent),
        )


@pytest.fixture(scope="module")
def comparison(dep1ex01_economy):
    """``(economy, linearised, participatory plan, reference plan, weights, seconds)``."""
    dep1ex01 = dep1ex01_economy
    participatory = run(HahnelBook2021(), dep1ex01, seed=0).plan
    linearised = linearize(dep1ex01, participatory)

    kinds = np.asarray(dep1ex01.commodity_extra["hahnel_kind"])
    consumable = np.isin(kinds, ["private_good", "public_good"])
    weights = np.where(consumable, participatory.valuation[INDICATIVE_PRICE], 0.0)
    shared = np.flatnonzero(kinds == "public_good").astype(np.int64)

    started = time.perf_counter()
    reference = run(
        ReferenceProcedure(MaximizeWeightedConsumption(weights, shared=shared)),
        linearised,
        seed=0,
    ).plan
    seconds = time.perf_counter() - started
    return dep1ex01, linearised, participatory, reference, weights, seconds


def participatory_final_use(economy: Economy, plan: Plan) -> np.ndarray:
    """The councils' plan read as final use: stated private consumption, public supply.

    A public good's final use here is what the worker councils produced of it, the quantity
    the reference program is also constrained by. ``plan.shared_use`` holds the councils'
    stated level instead, which the plan does not have to supply.
    """
    public = np.asarray(economy.commodity_extra["hahnel_kind"]) == "public_good"
    return plan.total_consumption(economy) + np.where(public, plan.total_output(economy), 0.0)


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
            resources = np.flatnonzero(
                np.isin(
                    np.asarray(linearised.commodity_extra["hahnel_kind"]),
                    ["natural_resource", "labor"],
                )
            ).astype(np.int64)
            used = plan.endowment_use(linearised, resources)
            assert used.shape == (linearised.n_commodities,)
            assert np.all(np.isfinite(used))

    def test_the_reference_scores_at_least_as_high_on_the_declared_weights(self, comparison):
        economy, linearised, participatory, reference, weights, _ = comparison
        by_participation = float(np.dot(weights, participatory_final_use(economy, participatory)))
        by_reference = float(np.dot(weights, final_use_of(linearised, reference)))
        assert by_reference >= by_participation

    def test_it_solves_inside_the_time_the_construction_sheet_allows(self, comparison):
        *_, seconds = comparison
        assert seconds < DEP1EX_SECONDS_ALLOWED


class TestThePlanIsAnAllocatedPlan:
    """``consumption`` here is the optimum's allocation, handed out by the objective.

    The objective's ``allocate`` divides the optimum's final consumption among the consumer
    units, which is what makes this ``consumption`` an allocation rather than a statement of
    what anyone asked for. The program's own constraints are ``A_ub x <= endowment``, which
    allows free disposal, so a commodity may end the period in surplus. A stated plan's
    consumption is the other quantity, and the two are not subtractable.
    """

    def solved(self):
        return reference_solution(
            build_bread_economy(), MaximizeWeightedConsumption(bread_weights())
        )

    def test_the_reference_files_its_plan_as_an_allocated_plan(self):
        assert isinstance(self.solved().plan, AllocatedPlan)

    def test_it_is_not_a_stated_plan(self):
        assert not isinstance(self.solved().plan, StatedPlan)

    def test_it_survives_the_procedure_seam(self):
        economy = build_bread_economy()
        result = run(
            ReferenceProcedure(MaximizeWeightedConsumption(bread_weights())), economy, seed=0
        )
        assert isinstance(result.plan, AllocatedPlan)

    def test_it_still_carries_every_fixed_field(self):
        assert self.solved().plan.absent_fields == ()

    def test_a_reference_plan_and_a_prefab_plan_are_not_comparable(self, synthetic_economy):
        stated = run(HahnelBook2021(max_rounds=2), synthetic_economy, seed=0).plan
        allocated = self.solved().plan
        with pytest.raises(ValueError, match="AllocatedPlan"):
            require_comparable(stated, allocated)


class TestHandSolvedOutputCoefficient:
    """The bread economy with unit 0 baking two loaves per run.

    The program's variable is how many times each unit runs, and ``output_coefficient`` is the
    output of one run. Maximising bread on 12 labour: unit 0 runs ``a`` times on ``0.5 a`` flour
    and ``a`` labour, unit 1 runs ``0.5 a`` times on ``a`` labour, so ``2 a = 12`` and ``a = 6``.
    Bread is ``2 a = 12``, flour ``3``, input use ``(3, 6, 6)``. The duals: bread is worth 1, so
    unit 0 breaks even at ``2 = 0.5 y_1 + y_2``, and unit 1 at ``y_1 = 2 y_2``, giving
    ``y = (1, 2, 1)``, and ``12 y_2 = 12`` is the optimum.
    """

    def solved(self) -> ReferenceResult:
        economy = build_bread_economy(output_coefficient=(2.0, 1.0))
        return reference_solution(economy, MaximizeWeightedConsumption(bread_weights()))

    def test_the_optimum(self):
        assert self.solved().objective_value == pytest.approx(12.0, abs=EXACT)

    def test_output_is_the_quantity_of_each_output_entry(self):
        np.testing.assert_allclose(self.solved().plan.output, [12.0, 3.0], atol=EXACT)

    def test_input_use_follows_the_runs_not_the_output(self):
        np.testing.assert_allclose(self.solved().plan.input_use, [3.0, 6.0, 6.0], atol=EXACT)

    def test_shadow_prices(self):
        np.testing.assert_allclose(
            self.solved().plan.valuation[SHADOW_PRICE], [1.0, 2.0, 1.0], atol=EXACT
        )

    def test_the_plan_balances(self):
        economy = build_bread_economy(output_coefficient=(2.0, 1.0))
        plan = self.solved().plan
        balance = (
            plan.total_output(economy)
            + np.asarray(economy.endowment)
            - plan.total_input_use(economy)
            - final_use_of(economy, plan)
        )
        np.testing.assert_allclose(balance, np.zeros(3), atol=EXACT)

    def test_labour_minimisation_reads_the_coefficient_too(self):
        """Six bread take three runs of unit 0: 1.5 flour, 3 labour there and 3 at the mill."""
        economy = build_bread_economy(labor_endowment=20.0, output_coefficient=(2.0, 1.0))
        targets = np.zeros(N_BREAD_COMMODITIES)
        targets[BREAD] = 6.0
        result = reference_solution(economy, minimize_labour(targets))
        assert result.objective_value == pytest.approx(6.0, abs=EXACT)
        np.testing.assert_allclose(result.plan.output, [6.0, 1.5], atol=EXACT)


class TestGeneratedEconomiesWithScaledOutputs:
    """The optimality conditions again, with every unit's output coefficient drawn."""

    @given(leontief_economy(scaled_outputs=True))
    @GENERATED
    def test_the_plan_balances_every_commodity(self, case):
        economy, weights, _ = case
        result = reference_solution(economy, MaximizeWeightedConsumption(weights))
        slack = commodity_slack(
            economy, np.asarray(result.plan.output), final_use_of(economy, result.plan)
        )
        assert slack.min() >= -scaled_tolerance(float(np.abs(slack).max()))

    @given(leontief_economy(scaled_outputs=True))
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

    @given(leontief_economy(scaled_outputs=True))
    @GENERATED
    def test_a_running_unit_breaks_even_at_the_shadow_prices(self, case):
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
            revenue = float(
                economy.output_coefficient[unit] * shadow[economy.output_commodity[unit]]
            )
            assert cost - revenue >= -scaled_tolerance(max(cost, revenue))
            if result.plan.output[unit] > 1e-6:
                assert cost == pytest.approx(revenue, abs=scaled_tolerance(max(cost, revenue)))

    @given(leontief_economy(scaled_outputs=True))
    @GENERATED
    def test_input_use_is_the_coefficients_times_the_runs(self, case):
        economy, weights, _ = case
        result = reference_solution(economy, MaximizeWeightedConsumption(weights))
        runs = np.asarray(result.plan.output) / np.asarray(economy.output_coefficient)
        owner = np.repeat(np.arange(economy.n_units), np.diff(economy.input_offsets))
        np.testing.assert_allclose(
            result.plan.input_use,
            np.asarray(economy.input_coefficient) * runs[owner],
            rtol=1e-12,
            atol=0.0,
        )
