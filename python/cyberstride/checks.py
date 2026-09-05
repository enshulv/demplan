"""Self-test tools for coordination procedures.

These are tools, not gates. A procedure written by a researcher is arbitrary Python and the
library cannot enforce anything about it; a randomised procedure is legitimate research. What
the library can do is tell the researcher whether his own procedure reproduces itself.
"""

from __future__ import annotations

import dataclasses
from typing import Mapping

import numpy as np

from cyberstride.economy import Economy
from cyberstride.plan import Plan
from cyberstride.procedure import Procedure

_PHYSICAL_FIELDS = ("output", "input_use", "consumption", "consumption_commodity", "provision")


@dataclasses.dataclass(frozen=True)
class DeterminismReport:
    """Whether repeated runs agreed, and on which fields they did not.

    Agreement covers everything a plan carries: the fixed physical columns, the ``valuation``
    bag and the ``extra`` bag. A quantity a mechanism files in ``extra`` is one the physical
    layer cannot be rebuilt without, so a report that passed over the bag would answer a
    narrower question than the one it is read as answering.
    """

    identical: bool
    differing_fields: list[str]


def check_determinism(
    procedure: Procedure, economy: Economy, seed: int, n: int = 3
) -> DeterminismReport:
    """Solve ``n`` times with the same seed and compare the plans bit for bit.

    Comparison is on the raw bytes, not within a tolerance: a run that differs by one unit in
    the last place is not reproducible, and the difference grows over a multi-period
    trajectory. ``differing_fields`` names three classes of entry on which the first
    disagreeing run departed from the first run, in this order: the fixed physical columns,
    the ``valuation`` keys as ``valuation.<key>``, and the ``extra`` keys as ``extra.<key>``.
    Within each bag the keys are in sorted order.

    A physical column one run declares absent and the other carries is named as
    ``<column> (absent from one run)``, the two runs having disagreed on whether the quantity
    exists rather than on its value. A bag key only one run carries is named as the key alone,
    a bag having no fixed set of keys for a missing one to stand out against.

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
        entry
        for entry in (
            _physical_verdict(name, getattr(first, name), getattr(other, name))
            for name in _PHYSICAL_FIELDS
        )
        if entry is not None
    ]
    differing += _differing_bag_keys("valuation", first.valuation, other.valuation)
    differing += _differing_bag_keys("extra", first.extra, other.extra)
    return differing


def _differing_bag_keys(
    bag: str, first: Mapping[str, np.ndarray], other: Mapping[str, np.ndarray]
) -> list[str]:
    """What one named-array bag contributes to ``differing_fields``.

    A key only one run carries and a key both carry with different bytes are both reported as
    ``<bag>.<key>``. The two read the same way because a bag has no fixed set of keys for a
    missing one to stand out against: a mechanism decides per run what it files there.
    """
    return [
        f"{bag}.{key}"
        for key in sorted(set(first) | set(other))
        if key not in first
        or key not in other
        or not _bit_identical(first[key], other[key])
    ]


def _physical_verdict(name: str, first, other) -> str | None:
    """What ``name`` contributes to ``differing_fields``, or ``None`` when the two runs agree.

    A field both runs declare absent is a field neither run has, which is agreement: reporting
    it would make every mechanism that leaves a quantity out look non-deterministic. One run
    carrying the field and the other not is a disagreement about whether the quantity exists,
    so the entry says that rather than reading as a difference between two sets of numbers.
    """
    if first is None and other is None:
        return None
    if first is None or other is None:
        return f"{name} (absent from one run)"
    return None if _bit_identical(first, other) else name


def _bit_identical(first: np.ndarray, other: np.ndarray) -> bool:
    if first.shape != other.shape or first.dtype != other.dtype:
        return False
    return np.ascontiguousarray(first).tobytes() == np.ascontiguousarray(other).tobytes()
