"""Optional tools.

Nothing here is on the path between an economy and a plan. Each tool carries some commitment
about how production or consumption works, so a coordination procedure picks the ones it
believes in and the base layer stays theory-neutral.

The helpers below are the exception: they only deal with the flat storage of variable-length
input and output lists and imply nothing about economics.
"""

from __future__ import annotations

import numpy as np

from demplan.economy import Economy


def unit_of_input(economy: Economy) -> np.ndarray:
    """For every entry of the flat input arrays, which producing unit owns it."""
    counts = np.diff(economy.input_offsets)
    return np.repeat(np.arange(economy.n_units, dtype=np.int64), counts)


def segment_sum(economy: Economy, values: np.ndarray, owner: np.ndarray | None = None) -> np.ndarray:
    """Sum one value per unit input into one value per unit.

    Accumulation runs over the flat arrays in storage order, which is the same order on every
    machine, so the result does not depend on how the work happens to be scheduled. Pass
    ``owner`` to reuse an index computed by :func:`unit_of_input`.
    """
    if owner is None:
        owner = unit_of_input(economy)
    return np.bincount(owner, weights=values, minlength=economy.n_units)


def _require_one_output_per_unit(economy: Economy, reader: str) -> None:
    """Refuse an economy in which some unit has more than one output entry.

    ``reader`` names what cannot read joint products, for the message. A tool that takes one
    output quantity per unit, or reads a unit's inputs per unit of its output, has no reading
    of a unit that lists two: which of the two would the quantity or the ratio be of.
    """
    joint = np.flatnonzero(np.diff(economy.output_offsets) > 1)
    if joint.size:
        unit = int(joint[0])
        entries = int(economy.output_offsets[unit + 1] - economy.output_offsets[unit])
        raise ValueError(
            f"{reader} needs exactly one output entry per producing unit, but unit {unit} has "
            f"{entries}; joint products are not supported by {reader} yet"
        )


from demplan.tools import cobb_douglas, leontief, linearize  # noqa: E402

__all__ = ["cobb_douglas", "leontief", "linearize", "segment_sum", "unit_of_input"]
