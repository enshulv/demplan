"""Read a plan's own input mix back as a fixed Leontief technology.

This tool carries a theoretical commitment, and a heavy one: it declares that the input
proportions one mechanism happened to choose *are* the technology. Under Cobb-Douglas the
input mix moves with relative prices, so a different price vector would have produced a
different mix and therefore a different linearised economy. The economy this returns is
"the technology as of that plan", not the technology the original economy described.

That is the price of comparison. A linear program needs constant coefficients, so comparing a
price-iterating mechanism with a centralised optimum means fixing the technology at some point,
and fixing it at the mechanism's own choice is the reading that gives the mechanism its own
terms. Report the linearisation alongside the comparison; a result that would flip under a
different anchor plan is a result about the anchor.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from demplan.economy import Economy, TechnologyKind
from demplan.plan import Plan
from demplan.tools import unit_of_input

UNIT_SCALE = 1.0
"""Every linearised unit has scale one: the coefficients already carry the whole technology."""


def linearize(economy: Economy, plan: Plan) -> Economy:
    """The same economy with every unit's technology replaced by the plan's input ratios.

    Each coefficient becomes ``input_use / output`` for the unit that owns it, so asking
    :func:`demplan.tools.leontief.input_requirements_flat` for the plan's own output
    returns the plan's own input use.

    A unit that produced nothing has no ratios to read, and gets zero coefficients. Read that
    as "this unit needs nothing", not as "this unit is unavailable": in the returned economy an
    idle unit produces its output commodity out of thin air, which makes a reference solution
    over that economy unbounded whenever the commodity carries weight. Drop idle units, or give
    them coefficients of your own, before optimising over the result.

    Everything else -- the commodity table, the endowment, the unit grouping, the input layout,
    the consumer table and all three ``extra`` bags -- is carried over unchanged.
    """
    plan.validate(economy)
    output = np.asarray(plan.output, dtype=np.float64)
    negative = np.flatnonzero(output < 0.0)
    if negative.size:
        unit = int(negative[0])
        raise ValueError(
            f"linearize: unit {unit} has negative output {output[unit]}, which has no reading "
            "as a technology"
        )

    per_input_output = output[unit_of_input(economy)]
    producing = per_input_output > 0.0
    coefficients = np.zeros(economy.n_inputs, dtype=np.float64)
    with np.errstate(over="ignore"):
        np.divide(
            np.asarray(plan.input_use, dtype=np.float64),
            per_input_output,
            out=coefficients,
            where=producing,
        )
    overflowed = np.flatnonzero(~np.isfinite(coefficients))
    if overflowed.size:
        entry = int(overflowed[0])
        unit = int(unit_of_input(economy)[entry])
        raise ValueError(
            f"linearize: unit {unit} produced {output[unit]} while drawing "
            f"{plan.input_use[entry]} of commodity {int(economy.input_commodity[entry])}, a "
            "ratio too large for a float64 coefficient"
        )
    return dataclasses.replace(
        economy,
        technology_kind=np.full(economy.n_units, TechnologyKind.LEONTIEF, dtype=np.int8),
        technology_scale=np.full(economy.n_units, UNIT_SCALE, dtype=np.float64),
        input_coefficient=coefficients,
    )
