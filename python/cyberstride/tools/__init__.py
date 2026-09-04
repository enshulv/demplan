"""Optional tools.

Nothing here is on the path between an economy and a plan. Each tool carries some commitment
about how production or consumption works, so a coordination procedure picks the ones it
believes in and the base layer stays theory-neutral.

The two helpers below are the exception: they only deal with the flat storage of
variable-length input lists and imply nothing about economics.
"""

from __future__ import annotations

import numpy as np

from cyberstride.economy import Economy


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


from cyberstride.tools import cobb_douglas, leontief  # noqa: E402

__all__ = ["cobb_douglas", "leontief", "segment_sum", "unit_of_input"]
