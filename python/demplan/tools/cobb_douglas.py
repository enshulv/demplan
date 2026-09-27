"""Cobb-Douglas technology: ``Q = scale * prod(x_j ** b_j)``.

Committing to this functional form is a theoretical choice, which is why it is a tool rather
than part of the data model. The functions here answer one question only: at these input
prices, which input bundle reaches a given output at least cost.

The dep1ex prefab does not use this form. Its production function carries an effort factor,
``Q = scale * effort**effort_c * prod(x_j ** b_j)``, so the bundle
:func:`cost_minimizing_inputs` returns for a given output is not the bundle that prefab
chose: it is the bundle for the same output with no effort factor at all.
"""

from __future__ import annotations

import numpy as np

from demplan.economy import Economy
from demplan.tools import _require_one_output_per_unit, segment_sum, unit_of_input


def cost_minimizing_inputs(
    exponents: np.ndarray, scale: float, output: float, input_prices: np.ndarray
) -> np.ndarray:
    """Least-cost input bundle of one unit for a given output.

    Cost minimisation makes spending proportional to the exponents,
    ``p_j x_j = (b_j / B) C`` with ``B = sum(b_j)``, and the production function then fixes
    total cost ``C``. The work is done in logarithms because ``C`` carries the exponent
    ``1 / B``, which is large whenever returns are far from constant.
    """
    exponents = np.asarray(exponents, dtype=np.float64)
    prices = np.asarray(input_prices, dtype=np.float64)
    exponent_sum = exponents.sum()
    log_share = np.log(exponents) - np.log(exponent_sum)
    log_cost = (
        np.log(output) - np.log(scale) - float((exponents * (log_share - np.log(prices))).sum())
    ) / exponent_sum
    return np.exp(log_share + log_cost - np.log(prices))


def cost_minimizing_inputs_flat(
    economy: Economy, output: np.ndarray, input_prices: np.ndarray
) -> np.ndarray:
    """:func:`cost_minimizing_inputs` for every producing unit at once.

    ``output`` is one quantity per unit of the unit's one output and ``input_prices`` one
    price per commodity. The result lines up with ``Economy.input_commodity``. A unit delivers
    ``output_coefficient`` of its output per unit of ``scale * prod(x_j ** b_j)``, so the
    bundle is the least-cost one reaching ``output / output_coefficient`` of that; where every
    output coefficient is 1 this is :func:`cost_minimizing_inputs` per unit. Raises
    ``ValueError`` when a unit has more than one output entry, since one quantity per unit does
    not say which of its outputs it is.
    """
    _require_one_output_per_unit(economy, "cost_minimizing_inputs_flat")
    activity = np.asarray(output, dtype=np.float64) / np.asarray(
        economy.output_coefficient, dtype=np.float64
    )
    exponents = np.asarray(economy.input_coefficient, dtype=np.float64)
    owner = unit_of_input(economy)
    prices = np.asarray(input_prices, dtype=np.float64)[economy.input_commodity]

    exponent_sum = segment_sum(economy, exponents, owner)
    log_share = np.log(exponents) - np.log(exponent_sum)[owner]
    log_price = np.log(prices)
    log_cost = (
        np.log(activity)
        - np.log(economy.technology_scale)
        - segment_sum(economy, exponents * (log_share - log_price), owner)
    ) / exponent_sum
    return np.exp(log_share + log_cost[owner] - log_price)
