"""The coordination-procedure interface and the wrapper that runs one.

The interface is one method. Anything that implements it gets the library's data model,
timing, round accounting and self-test tools without being merged into this package.
"""

from __future__ import annotations

import dataclasses
import time
from typing import Protocol, runtime_checkable

from cyberstride.economy import Economy
from cyberstride.iterate import IterateResult, _recorder
from cyberstride.plan import Plan


@runtime_checkable
class Procedure(Protocol):
    """A coordination method: given an economy and a seed, produce a plan."""

    def solve(self, economy: Economy, seed: int) -> Plan:
        ...


@dataclasses.dataclass(frozen=True)
class RunSummary:
    """How the run went, as opposed to what it produced.

    ``rounds``, ``converged`` and ``diverged`` are ``None`` when the procedure did not use
    :func:`cyberstride.iterate`: the library has no way to count rounds it never saw. That is
    a different statement from "ran zero rounds", "did not converge" or "did not diverge".

    ``converged`` and ``diverged`` are both false when the loop spent its round cap, and a
    researcher reads the two cases differently: a run that blew up says something about the
    mechanism, a run that ran out of rounds says the cap was set too low.
    """

    rounds: int | None
    converged: bool | None
    diverged: bool | None
    wall_seconds: float
    trajectory: list[Plan] | None


@dataclasses.dataclass(frozen=True)
class RunResult:
    plan: Plan
    summary: RunSummary


def run(procedure: Procedure, economy: Economy, seed: int) -> RunResult:
    """Call ``procedure.solve``, timing it and collecting any loop it drove.

    A procedure that calls :func:`cyberstride.iterate` more than once reports the last loop:
    that is the one whose result the returned plan came out of. A nested ``run`` gets its own
    collector, so an inner procedure's loop never lands in the outer summary.
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
    return RunResult(plan=plan, summary=summary)
