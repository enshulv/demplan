"""The voluntary loop tool.

A coordination procedure may compute its plan any way it likes. If it drives a fixed point,
running that loop through :func:`iterate` lets the library see the round count, apply a round
cap and watch for divergence, none of which it can observe from the outside.

The state is the procedure's own object. The library never looks inside it; the only window
is the optional ``plan_of``.
"""

from __future__ import annotations

import contextvars
import dataclasses
from typing import Any, Callable, Iterator

import numpy as np

from cyberstride.plan import Plan

_recorder: contextvars.ContextVar[list["IterateResult"] | None] = contextvars.ContextVar(
    "cyberstride_iterate_recorder", default=None
)
"""Where :func:`cyberstride.procedure.run` collects the results of the loops it wraps."""


@dataclasses.dataclass(frozen=True)
class IterateResult:
    """What one loop reports back."""

    state: Any
    rounds: int
    converged: bool
    diverged: bool
    trajectory: list[Plan] | None


def iterate(
    init: Callable[[], Any],
    step: Callable[[Any], Any],
    converged: Callable[[Any], bool],
    max_rounds: int,
    plan_of: Callable[[Any], Plan] | None = None,
) -> IterateResult:
    """Run ``step`` from ``init()`` until ``converged`` holds or ``max_rounds`` is spent.

    ``rounds`` is the number of times ``step`` was called. Convergence is tested after every
    ``step`` and never after ``init``, so a starting state that already satisfies ``converged``
    still costs one round. Published iteration counts depend on this: a prefab that reproduces
    "converged in 14 rounds" is reporting 14 calls to ``step``.

    ``plan_of`` turns a state into a :class:`Plan`. Given one, the loop records a trajectory of
    one plan per round and stops as soon as a plan's physical layer holds a non-finite value,
    returning ``diverged=True``. Without it the library cannot see the state, so it detects no
    divergence.

    Raises ``ValueError`` when ``max_rounds`` is below 1.
    """
    if max_rounds < 1:
        raise ValueError(f"max_rounds must be at least 1, got {max_rounds}")

    trajectory: list[Plan] | None = [] if plan_of is not None else None
    state = init()
    round_number = 0
    for round_number in range(1, max_rounds + 1):
        state = step(state)
        if plan_of is not None:
            plan = plan_of(state)
            trajectory.append(plan)
            if not _physically_finite(plan):
                return _record(IterateResult(state, round_number, False, True, trajectory))
        if converged(state):
            return _record(IterateResult(state, round_number, True, False, trajectory))
    return _record(IterateResult(state, round_number, False, False, trajectory))


def _physical_arrays(plan: Plan) -> Iterator[np.ndarray]:
    yield plan.output
    yield plan.input_use
    yield plan.consumption
    yield plan.provision


def _physically_finite(plan: Plan) -> bool:
    return all(bool(np.isfinite(array).all()) for array in _physical_arrays(plan))


def _record(result: IterateResult) -> IterateResult:
    collected = _recorder.get()
    if collected is not None:
        collected.append(result)
    return result
