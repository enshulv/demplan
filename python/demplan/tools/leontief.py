"""Leontief technology: ``x_j = a_j * Q``, no substitution between inputs.

Fixed input proportions are a theoretical claim about production, so this is a tool. Under it
``input_coefficient`` reads as an input-output coefficient rather than as an exponent.
"""

from __future__ import annotations

import numpy as np

from demplan.economy import Economy
from demplan.tools import _require_one_output_per_unit, unit_of_input


def input_requirements(coefficients: np.ndarray, output: float) -> np.ndarray:
    """Inputs one unit needs for a given output."""
    return np.asarray(coefficients, dtype=np.float64) * float(output)


def input_requirements_flat(economy: Economy, output: np.ndarray) -> np.ndarray:
    """:func:`input_requirements` for every producing unit at once.

    ``output`` is one quantity per unit; the result lines up with ``Economy.input_commodity``.
    Raises ``ValueError`` when a unit has more than one output entry, since one quantity per
    unit does not say which of its outputs it is.
    """
    _require_one_output_per_unit(economy, "input_requirements_flat")
    quantities = np.asarray(output, dtype=np.float64)[unit_of_input(economy)]
    return np.asarray(economy.input_coefficient, dtype=np.float64) * quantities
