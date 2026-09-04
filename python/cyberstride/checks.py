"""Self-test tools for coordination procedures.

These are tools, not gates. A procedure written by a researcher is arbitrary Python and the
library cannot enforce anything about it; a randomised procedure is legitimate research. What
the library can do is tell the researcher whether his own procedure reproduces itself.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from cyberstride.economy import Economy
from cyberstride.plan import Plan
from cyberstride.procedure import Procedure

_PHYSICAL_FIELDS = ("output", "input_use", "consumption", "consumption_commodity", "provision")


@dataclasses.dataclass(frozen=True)
class DeterminismReport:
    """Whether repeated runs agreed, and on which fields they did not."""

    identical: bool
    differing_fields: list[str]


def check_determinism(
    procedure: Procedure, economy: Economy, seed: int, n: int = 3
) -> DeterminismReport:
    """Solve ``n`` times with the same seed and compare the plans bit for bit.

    Comparison is on the raw bytes, not within a tolerance: a run that differs by one unit in
    the last place is not reproducible, and the difference grows over a multi-period
    trajectory. ``differing_fields`` names the physical columns and the ``valuation`` keys
    (as ``valuation.<key>``) on which the first disagreeing run departed from the first run.

    Raises ``ValueError`` when ``n`` is below 1.
    """
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")

    first = procedure.solve(economy, seed)
    for _ in range(n - 1):
        differing = _differing_fields(first, procedure.solve(economy, seed))
        if differing:
            return DeterminismReport(identical=False, differing_fields=differing)
    return DeterminismReport(identical=True, differing_fields=[])


def _differing_fields(first: Plan, other: Plan) -> list[str]:
    differing = [
        name
        for name in _PHYSICAL_FIELDS
        if not _bit_identical(getattr(first, name), getattr(other, name))
    ]
    for key in sorted(set(first.valuation) | set(other.valuation)):
        if key not in first.valuation or key not in other.valuation:
            differing.append(f"valuation.{key}")
        elif not _bit_identical(first.valuation[key], other.valuation[key]):
            differing.append(f"valuation.{key}")
    return differing


def _bit_identical(first: np.ndarray, other: np.ndarray) -> bool:
    if first.shape != other.shape or first.dtype != other.dtype:
        return False
    return np.ascontiguousarray(first).tobytes() == np.ascontiguousarray(other).tobytes()
