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
    """What one loop reports back.

    ``diverged`` is ``None`` when the loop ran without ``plan_of``: the library saw no plan, so
    it has no answer rather than a negative one. ``converged=False`` with ``diverged=False``
    says the round cap ran out on a loop that was watched throughout.
    """

    state: Any
    rounds: int
    converged: bool
    diverged: bool | None
    trajectory: list[Plan] | None


def iterate(
    init: Callable[[], Any],
    step: Callable[[Any], Any],
    converged: Callable[[Any], bool],
    max_rounds: int,
    plan_of: Callable[[Any], Plan] | None = None,
    keep_trajectory: bool = True,
) -> IterateResult:
    """Run ``step`` from ``init()`` until ``converged`` holds or ``max_rounds`` is spent.

    ``rounds`` is the number of times ``step`` was called. Convergence is tested after every
    ``step`` and never after ``init``, so a starting state that already satisfies ``converged``
    still costs one round. Published iteration counts depend on this: a prefab that reproduces
    "converged in 14 rounds" is reporting 14 calls to ``step``.

    ``plan_of`` turns a state into a :class:`Plan`. Given one, the loop calls it once a round
    and stops as soon as a plan's physical layer holds a non-finite value, returning
    ``diverged=True``. Without it the library cannot see the state, and ``diverged`` is
    ``None``: a loop nobody watched is not a loop that stayed finite.

    ``keep_trajectory`` decides whether those plans are also kept. Set it to ``False`` to watch
    for divergence on a long run without holding one plan per round; ``trajectory`` is then
    ``None``, as it is whenever ``plan_of`` is absent.

    Raises ``ValueError`` when ``max_rounds`` is below 1.
    """
    if max_rounds < 1:
        raise ValueError(f"max_rounds must be at least 1, got {max_rounds}")

    trajectory: list[Plan] | None = [] if plan_of is not None and keep_trajectory else None
    # The verdict a loop that ends without a non-finite plan carries: False under the watch of
    # a ``plan_of``, and unknown without one.
    divergence_verdict: bool | None = None if plan_of is None else False
    state = init()
    round_number = 0
    for round_number in range(1, max_rounds + 1):
        state = step(state)
        if plan_of is not None:
            plan = plan_of(state)
            if trajectory is not None:
                trajectory.append(plan)
            if not _physically_finite(plan):
                return _record(IterateResult(state, round_number, False, True, trajectory))
        if converged(state):
            return _record(IterateResult(state, round_number, True, divergence_verdict, trajectory))
    return _record(IterateResult(state, round_number, False, divergence_verdict, trajectory))


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
