"""The centralised optimum a declared objective picks out, as a linear program.

This is the benchmark the library compares planning mechanisms against. It is not a market
baseline and not a claim about what a planning board could compute; it is the best plan that
exists under the stated technology and the stated objective, so that the distance between a
mechanism's plan and this one is measurable in the units the researcher declared.

The program has one variable per producing unit, how many times the unit runs, and one per
commodity the objective declares final consumption of, and one constraint per commodity::

    sum of output of c  +  endowment of c  -  input use of c  -  final consumption of c  >= 0

One run of a unit uses ``input_coefficient`` of each input and yields ``output_coefficient`` of
its one output, so a unit's output in the plan is its runs times its output coefficient. On a
linearised or dep1ex-derived economy every output coefficient is 1 and runs equal output.

Nothing else is imposed. There is no budget, no price and no behavioural equation, because a
linear program over a Leontief technology needs none of them; the shadow prices come out of
the constraints rather than going in.

Leontief technology is required, every unit labelled :data:`demplan.LEONTIEF`, since the
constraint above is linear in the runs only when the coefficients are constants. Feed a
Cobb-Douglas economy through :func:`demplan.tools.linearize.linearize` first, and read that
tool's docstring for what the conversion assumes. Each unit has exactly one output entry: a
unit with joint products is refused.
"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from demplan.economy import LEONTIEF, Economy, _index_array, _require_indices_in_range
from demplan.objectives import (
    Objective,
    _require_finite_declaration,
    _require_non_negative,
)
from demplan.plan import SHADOW_PRICE, AllocatedPlan, Plan
from demplan.tools import _require_one_output_per_unit, unit_of_input

REFERENCE_SOLUTION = "the reference solution"
"""How refusals of an economy the program cannot read name the program."""

SOLVER_METHOD = "highs"

OPTIMAL = "optimal"
"""The only status a :class:`ReferenceResult` is ever built with."""

_DUAL_NOISE = 1e-12
"""Magnitude below which a dual variable is read as zero rather than as a sign.

A commodity whose constraint is slack has a dual of exactly zero in exact arithmetic, and the
solver returns it as a value a few ulp either side of zero. Rounding those to zero keeps the
promise that shadow prices are non-negative without hiding a dual that is genuinely negative,
which would mean the constraints were assembled the wrong way round.
"""


class ReferenceInfeasible(RuntimeError):
    """The linear program has no optimum: it is infeasible, unbounded, or the solver gave up.

    Unbounded is the common one on a first run, and it usually means some commodity can be
    produced without inputs while carrying weight in the objective. An idle unit that has been
    through :func:`demplan.tools.linearize.linearize` is one way to arrive there.
    """


class ReferenceResult(NamedTuple):
    """The optimum: the plan, the value the objective reached, and the solver's verdict."""

    plan: Plan
    objective_value: float
    status: str


MINIMISATION_ATTRIBUTES = ("final_demand_lower_bound", "counted_commodities")
"""The pair of attributes an objective declares to be read as a minimisation."""

WEIGHTS_ATTRIBUTE = "weights"
"""What a maximisation declares: the coefficient it puts on each commodity."""


def _require_the_whole_minimisation_pair(objective, lower_bound, counted) -> None:
    """Refuse an objective that declares one attribute of the minimisation pair and not both.

    Half a pair is read as a maximisation of ``weights``, and a minimising objective returns
    zero weights, so the program would maximise nothing: it reports the plan that produces
    nothing as optimal, meets none of the declared floor, and says so nowhere in its result.
    """
    if (lower_bound is None) == (counted is None):
        return
    if lower_bound is None:
        absent, present = MINIMISATION_ATTRIBUTES
    else:
        present, absent = MINIMISATION_ATTRIBUTES
    raise ValueError(
        f"{objective.name}: declares {present} without {absent}; an objective is read as a "
        f"minimisation only when it carries both of {', '.join(MINIMISATION_ATTRIBUTES)}"
    )


def _require_a_well_formed_floor(objective, economy: Economy, floor: np.ndarray) -> None:
    """Check the floor of any objective read as a minimisation, whoever wrote that objective.

    :class:`demplan.objectives.MinimizeLabor` checks its own targets, but a minimisation is
    recognised here by :data:`MINIMISATION_ATTRIBUTES` and not by type, so an objective a
    researcher wrote reaches the program with those checks unrun. Each malformed floor comes
    back with status ``"optimal"``: a non-finite entry is no bound at all to the solver, and a
    negative entry lets the plan cover part of its own input use out of the floor and report a
    lower cost than any plan meeting the floor as written.

    The unreadable entry is refused first, because the other question is about a number the
    reader can compare: ``NaN < 0`` is false, so a NaN floor reads as a non-negative floor.
    Which commodities the floor sits on is the researcher's statement and is not checked.

    This checks that the declaration is well formed rather than that the plan satisfies an
    invariant, so it applies whatever the researcher enabled from the invariant toolbox.
    """
    lower_bound_attribute, _ = MINIMISATION_ATTRIBUTES
    label = f"{objective.name}: {lower_bound_attribute}"
    _require_finite_declaration(floor, label)
    _require_non_negative(floor, label)


def _require_a_well_formed_weighting(objective, economy: Economy, weights: np.ndarray) -> None:
    """Check the weights of any objective read as a maximisation, whoever wrote it.

    A maximisation is recognised by the absence of the minimisation pair, so the weights of an
    objective a researcher wrote reach the program unchecked as well, and they decide the same
    two things the floor decides: which commodities become final-consumption variables, and
    what the reported objective value counts. A non-finite weight is not a declaration anyone
    can read. Which commodities carry weight is the researcher's statement and is not checked.

    The sign is left alone. A negative weight is a penalty term, which is a coherent thing for
    a social welfare function to say, and refusing it would put a commitment about what such a
    function may say into the layer that is meant to hold none.
    """
    label = f"{objective.name}: {WEIGHTS_ATTRIBUTE}"
    _require_finite_declaration(weights, label)


def _counted_commodity_indices(objective, counted, n_commodities: int) -> np.ndarray:
    """``counted_commodities`` checked as distinct commodity indices, whoever declared it.

    The cost vector counts an input when its commodity is listed, so an index outside the
    commodity table matches nothing: a list of them makes the program minimise an all-zero
    cost and report an objective value of zero for a plan that spends whatever it likes.
    """
    _, counted_attribute = MINIMISATION_ATTRIBUTES
    label = f"{objective.name}: {counted_attribute}"
    indices = _index_array(label, counted)
    _require_indices_in_range(label, indices, n_commodities)
    return indices


class _Program:
    """One assembled linear program, plus what is needed to read its answer back as a plan."""

    def __init__(self, economy: Economy, objective: Objective):
        self.economy = economy
        self.objective = objective
        self.weights = objective.weights(economy)

        lower_bound_attribute, counted_attribute = MINIMISATION_ATTRIBUTES
        self.lower_bound = getattr(objective, lower_bound_attribute, None)
        counted = getattr(objective, counted_attribute, None)
        _require_the_whole_minimisation_pair(objective, self.lower_bound, counted)
        self.minimises = self.lower_bound is not None and counted is not None
        if self.minimises:
            self.counted = _counted_commodity_indices(objective, counted, economy.n_commodities)

        declared = np.asarray(self.lower_bound) if self.minimises else self.weights
        if declared.shape != (economy.n_commodities,):
            raise ValueError(
                f"{objective.name}: the declaration it optimises has shape {declared.shape}, "
                f"expected one entry per commodity ({economy.n_commodities},)"
            )
        if self.minimises:
            _require_a_well_formed_floor(objective, economy, declared)
        else:
            _require_a_well_formed_weighting(objective, economy, declared)
        self.consumable = np.flatnonzero(declared != 0.0).astype(np.int64)
        self.n_variables = economy.n_units + self.consumable.shape[0]
        self.unit_of_output = np.repeat(
            np.arange(economy.n_units, dtype=np.int64), np.diff(economy.output_offsets)
        )

    def cost(self) -> np.ndarray:
        """Coefficients of the objective, always written as something to minimise."""
        cost = np.zeros(self.n_variables, dtype=np.float64)
        if self.minimises:
            counted = np.isin(np.asarray(self.economy.input_commodity), self.counted)
            np.add.at(
                cost[: self.economy.n_units],
                unit_of_input(self.economy)[counted],
                np.asarray(self.economy.input_coefficient)[counted],
            )
            return cost
        cost[self.economy.n_units :] = -self.weights[self.consumable]
        return cost

    def constraints(self) -> coo_matrix:
        """``A_ub`` for ``A_ub x <= endowment``: input use minus output plus final consumption.

        A unit's column holds minus its output coefficient in its output commodity's row and
        its input coefficients in its inputs' rows, one run of the unit each.
        """
        n_units = self.economy.n_units
        rows = np.concatenate(
            [
                np.asarray(self.economy.output_commodity),
                np.asarray(self.economy.input_commodity),
                self.consumable,
            ]
        )
        columns = np.concatenate(
            [
                self.unit_of_output,
                unit_of_input(self.economy),
                n_units + np.arange(self.consumable.shape[0], dtype=np.int64),
            ]
        )
        values = np.concatenate(
            [
                -np.asarray(self.economy.output_coefficient, dtype=np.float64),
                np.asarray(self.economy.input_coefficient, dtype=np.float64),
                np.ones(self.consumable.shape[0]),
            ]
        )
        return coo_matrix(
            (values, (rows, columns)),
            shape=(self.economy.n_commodities, self.n_variables),
        )

    def bounds(self) -> list[tuple[float, None]]:
        """Runs are non-negative; final consumption is non-negative or above its floor."""
        floors = np.zeros(self.consumable.shape[0], dtype=np.float64)
        if self.minimises:
            floors = np.asarray(self.lower_bound, dtype=np.float64)[self.consumable]
        return [(0.0, None)] * self.economy.n_units + [(float(floor), None) for floor in floors]

    def value_of(self, minimised: float) -> float:
        """The objective as the researcher declared it, undoing the sign the solver needed."""
        return float(minimised) if self.minimises else float(-minimised)

    def plan_of(self, solution: np.ndarray, shadow_price: np.ndarray) -> AllocatedPlan:
        """The solved program as a plan. ``consumption`` is what the optimum allocates.

        The objective's ``allocate`` divides the optimum's final consumption among the consumer
        units, so this block is a division of what the program produced rather than a
        statement of what anyone asked for. The program itself constrains each commodity by
        ``A_ub x <= endowment``, which allows free disposal: a commodity may end the period in
        surplus, so a balance is not what makes this an allocation.

        ``output`` is each unit's runs times its output coefficient, and ``input_use`` each
        input coefficient times its unit's runs.
        """
        runs = np.ascontiguousarray(solution[: self.economy.n_units], dtype=np.float64)
        output = runs[self.unit_of_output] * np.asarray(
            self.economy.output_coefficient, dtype=np.float64
        )
        input_use = (
            np.asarray(self.economy.input_coefficient, dtype=np.float64)
            * runs[unit_of_input(self.economy)]
        )
        aggregate = np.zeros(self.economy.n_commodities, dtype=np.float64)
        aggregate[self.consumable] = solution[self.economy.n_units :]
        consumption, columns, shared_use = self.objective.allocate(self.economy, aggregate)
        return AllocatedPlan(
            output=output,
            input_use=input_use,
            consumption=np.ascontiguousarray(consumption, dtype=np.float64),
            consumption_commodity=np.ascontiguousarray(columns, dtype=np.int64),
            shared_use=np.ascontiguousarray(shared_use, dtype=np.float64),
            valuation={SHADOW_PRICE: shadow_price},
        )


def _require_leontief(economy: Economy) -> None:
    wrong = np.flatnonzero(np.asarray(economy.technology_kind) != LEONTIEF)
    if wrong.size:
        unit = int(wrong[0])
        raise ValueError(
            f"reference_solution needs Leontief technology, every unit labelled "
            f"{LEONTIEF!r}, but unit {unit} carries technology_kind "
            f"{str(economy.technology_kind[unit])!r}; convert the economy with "
            "demplan.tools.linearize.linearize first"
        )


def _shadow_prices(result, n_commodities: int) -> np.ndarray:
    """Read the commodity constraints' duals as "how much a free unit improves the objective".

    The solver reports marginals of ``A_ub x <= b_ub`` as the change in the minimised value per
    unit of ``b_ub``, so they are zero or negative: relaxing a constraint cannot make a minimum
    worse. Improvement is the other sign, and it means the same thing whichever way the
    researcher's own objective ran, because the minimised value is that objective negated when
    the objective was a maximisation.

    Commodities are NaN when the solver reported no duals at all, which is a statement that the
    number is unavailable rather than that it is zero.
    """
    marginals = getattr(getattr(result, "ineqlin", None), "marginals", None)
    if marginals is None:
        return np.full(n_commodities, np.nan, dtype=np.float64)
    shadow = -np.asarray(marginals, dtype=np.float64)
    return np.where(np.abs(shadow) < _DUAL_NOISE, 0.0, shadow)


def reference_solution(economy: Economy, objective: Objective) -> ReferenceResult:
    """Solve the economy to optimality under ``objective``.

    Raises ``ValueError`` when the economy is not Leontief, when a unit has more than one
    output entry, or when the objective does not fit the economy, and
    :class:`ReferenceInfeasible` when the program has no optimum. A result is only ever
    returned with status ``"optimal"``.
    """
    _require_leontief(economy)
    _require_one_output_per_unit(economy, REFERENCE_SOLUTION)
    program = _Program(economy, objective)
    solved = linprog(
        program.cost(),
        A_ub=program.constraints(),
        b_ub=np.asarray(economy.endowment, dtype=np.float64),
        bounds=program.bounds(),
        method=SOLVER_METHOD,
    )
    if solved.status != 0 or solved.x is None:
        raise ReferenceInfeasible(
            f"the reference program for {objective.name} has no optimum: {solved.message}"
        )
    return ReferenceResult(
        plan=program.plan_of(solved.x, _shadow_prices(solved, economy.n_commodities)),
        objective_value=program.value_of(solved.fun),
        status=OPTIMAL,
    )


class ReferenceProcedure:
    """:func:`reference_solution` as a :class:`demplan.Procedure`.

    The linear program is deterministic, so ``seed`` is accepted and ignored: two runs on the
    same economy and objective return the same plan whatever seed they are given. The parameter
    stays in the signature because the procedure interface is one method for every mechanism,
    including the randomised ones.
    """

    def __init__(self, objective: Objective) -> None:
        self.objective = objective

    def solve(self, economy: Economy, seed: int) -> Plan:
        return reference_solution(economy, self.objective).plan
