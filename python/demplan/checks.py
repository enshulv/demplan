"""Self-test tools for coordination procedures.

These are tools, not gates. A procedure written by a researcher is arbitrary Python and the
library cannot enforce anything about it; a randomised procedure is legitimate research. What
the library can do is tell the researcher whether his own procedure reproduces itself.
"""

from __future__ import annotations

import dataclasses
import math
import numbers
from typing import Callable, Mapping

import numpy as np

from demplan.economy import Economy
from demplan.indicators import PlanComparison, compare_plans
from demplan.plan import Plan
from demplan.procedure import Procedure, run

_PHYSICAL_FIELDS = ("output", "input_use", "consumption", "consumption_commodity", "shared_use")


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


Rescale = Callable[[Procedure, Economy, float], "tuple[Procedure, Economy]"]
"""``rescale(procedure, economy, factor) -> (procedure, economy)``: the rescaled run's inputs."""


@dataclasses.dataclass(frozen=True)
class HomogeneityReport:
    """How far a run moved when its inputs were rescaled by ``factor``.

    ``comparison`` compares the plan of the original run with the plan of the rescaled one.
    ``rescale`` is the rescaling function's qualified name. The round and convergence fields
    come from each run's summary and are ``None`` when the procedure did not use
    :func:`demplan.iterate`. The report states the numbers; which gap counts as homogeneous is
    the researcher's statement.
    """

    factor: float
    rescale: str
    comparison: PlanComparison
    rounds: int | None
    rounds_rescaled: int | None
    converged: bool | None
    converged_rescaled: bool | None


def check_homogeneity(
    procedure: Procedure, economy: Economy, seed: int, rescale: Rescale, factor: float
) -> HomogeneityReport:
    """Run once, run again on what ``rescale`` makes of the inputs, and compare the two plans.

    ``rescale(procedure, economy, factor)`` returns the procedure and economy of the second
    run. Two uses:

    * start-independence: ``rescale`` changes only the procedure's starting valuations, and a
      procedure whose result does not depend on where it starts compares at zero;
    * zero-degree homogeneity: ``rescale`` scales every nominal quantity the researcher
      declares, and a procedure whose real result does not depend on the unit of account
      compares at zero.

    Both runs go through :func:`demplan.run` with the same ``seed`` and ``differences=False``;
    the plans are compared with :func:`demplan.compare_plans`.

    Raises ``ValueError`` when ``factor`` is not a finite number above zero other than 1, before
    anything runs, and ``TypeError`` when ``rescale`` returns anything but a tuple of two.
    """
    factor = _rescale_factor(factor)
    original = run(procedure, economy, seed, differences=False)
    rescaled_inputs = rescale(procedure, economy, factor)
    if not isinstance(rescaled_inputs, tuple) or len(rescaled_inputs) != 2:
        raise TypeError(
            f"rescale must return a pair (procedure, economy), got "
            f"{type(rescaled_inputs).__name__}"
        )
    rescaled = run(*rescaled_inputs, seed, differences=False)
    return HomogeneityReport(
        factor=factor,
        rescale=_qualified_name(rescale),
        comparison=compare_plans(original.plan, rescaled.plan),
        rounds=original.summary.rounds,
        rounds_rescaled=rescaled.summary.rounds,
        converged=original.summary.converged,
        converged_rescaled=rescaled.summary.converged,
    )


def _rescale_factor(factor) -> float:
    """``factor`` as a float, refusing anything but a finite number above zero other than 1.

    A factor of 1 rescales nothing, so the check would compare a run with itself.
    """
    is_number = isinstance(factor, numbers.Real) and not isinstance(factor, bool)
    if not is_number or not math.isfinite(factor) or factor <= 0 or factor == 1:
        raise ValueError(
            f"factor must be a finite number above zero other than 1, got {factor!r}"
        )
    return float(factor)


def _qualified_name(function) -> str:
    """``__qualname__`` of a function, or of the class of a callable object."""
    return getattr(function, "__qualname__", type(function).__qualname__)
