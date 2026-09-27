"""The coordination-procedure interface and the wrapper that runs one.

The interface is one method. Anything that implements it gets the library's data model,
timing, round accounting and self-test tools without being merged into this package.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Protocol, runtime_checkable

import numpy as np

from demplan.differences import PlanDifferences, plan_differences
from demplan.economy import Economy
from demplan.iterate import IterateResult, _recorder
from demplan.plan import Plan


@runtime_checkable
class Procedure(Protocol):
    """A coordination method: given an economy and a seed, produce a plan."""

    def solve(self, economy: Economy, seed: int) -> Plan:
        ...


@dataclasses.dataclass(frozen=True)
class RunSummary:
    """How the run went, as opposed to what it produced.

    ``rounds``, ``converged`` and ``diverged`` are ``None`` when the procedure did not use
    :func:`demplan.iterate`: the library has no way to count rounds it never saw. That is
    a different statement from "ran zero rounds", "did not converge" or "did not diverge".

    ``diverged`` is ``None`` in one more case: a loop driven without ``plan_of`` showed the
    library no plan to judge, so divergence went unwatched. ``rounds`` tells the two apart,
    since it counts the rounds of any loop the library saw.

    ``converged`` and ``diverged`` are both false when a watched loop spent its round cap, and
    a researcher reads that differently from divergence: a run that blew up says something
    about the mechanism, a run that ran out of rounds says the cap was set too low.
    """

    rounds: int | None
    converged: bool | None
    diverged: bool | None
    wall_seconds: float
    trajectory: list[Plan] | None


@dataclasses.dataclass(frozen=True)
class RunResult:
    """What one run produced, how it went, and what its plan leaves over or short."""

    plan: Plan
    summary: RunSummary
    differences: PlanDifferences | None = None
    """:func:`demplan.plan_differences` of the plan, or ``None`` when the run was asked not to
    compute it."""


def run(
    procedure: Procedure,
    economy: Economy,
    seed: int,
    bads: np.ndarray | None = None,
    price: str | None = None,
    differences: bool = True,
) -> RunResult:
    """Call ``procedure.solve``, timing it and collecting any loop it drove.

    A procedure that calls :func:`demplan.iterate` more than once reports the last loop:
    that is the one whose result the returned plan came out of. A nested ``run`` gets its own
    collector, so an inner procedure's loop never lands in the outer summary.

    With ``differences`` true, the result carries :func:`demplan.plan_differences` of the plan,
    given ``bads`` and ``price``; with it false, ``RunResult.differences`` is ``None`` and the
    plan is not read. The report is computed after the timed region, so ``wall_seconds`` is the
    time ``solve`` took and nothing else. Exceptions from ``solve`` and from the report
    propagate, among them :class:`demplan.SchemaError` for a plan not shaped for ``economy``.
    """
    collected: list[IterateResult] = []
    token = _recorder.set(collected)
    started = time.perf_counter()
    try:
        plan = procedure.solve(economy, seed)
    finally:
        wall_seconds = time.perf_counter() - started
        _recorder.reset(token)

    loop = collected[-1] if collected else None
    summary = RunSummary(
        rounds=None if loop is None else loop.rounds,
        converged=None if loop is None else loop.converged,
        diverged=None if loop is None else loop.diverged,
        wall_seconds=wall_seconds,
        trajectory=None if loop is None else loop.trajectory,
    )
    report = plan_differences(economy, plan, bads, price) if differences else None
    return RunResult(plan=plan, summary=summary, differences=report)
