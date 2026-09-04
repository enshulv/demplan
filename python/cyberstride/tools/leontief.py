"""Leontief technology: ``x_j = a_j * Q``, no substitution between inputs.

Fixed input proportions are a theoretical claim about production, so this is a tool. Under it
``input_coefficient`` reads as an input-output coefficient rather than as an exponent.
"""

from __future__ import annotations

import numpy as np

from cyberstride.economy import Economy
from cyberstride.tools import unit_of_input


def input_requirements(coefficients: np.ndarray, output: float) -> np.ndarray:
    """Inputs one unit needs for a given output."""
    return np.asarray(coefficients, dtype=np.float64) * float(output)


def input_requirements_flat(economy: Economy, output: np.ndarray) -> np.ndarray:
    """:func:`input_requirements` for every producing unit at once.

    ``output`` is one quantity per unit; the result lines up with ``Economy.input_commodity``.
    """
    quantities = np.asarray(output, dtype=np.float64)[unit_of_input(economy)]
    return np.asarray(economy.input_coefficient, dtype=np.float64) * quantities
