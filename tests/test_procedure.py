"""The coordination-procedure interface and the run wrapper that times it."""

from __future__ import annotations

import time

import numpy as np
import pytest

from cyberstride import Plan, Procedure, RunResult, RunSummary, iterate, run
from cyberstride.iterate import _recorder


def trivial_plan(economy) -> Plan:
    return Plan(
        output=np.zeros(economy.n_units),
        input_use=np.zeros(economy.n_inputs),
        consumption=np.zeros((economy.n_consumers, 0)),
        consumption_commodity=np.zeros(0, dtype=np.int64),
        provision=np.zeros(economy.n_commodities),
    )


class DirectProcedure:
    """A procedure that computes its plan in one shot, without the loop tool."""

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.seen_seed: int | None = None

    def solve(self, economy, seed: int) -> Plan:
        self.seen_seed = seed
        if self.delay:
            time.sleep(self.delay)
        return trivial_plan(economy)


class LoopingProcedure:
    """A procedure that drives its own fixed-point loop through :func:`iterate`."""

    def __init__(self, rounds_to_converge: int = 3, max_rounds: int = 10, record: bool = False):
        self.rounds_to_converge = rounds_to_converge
        self.max_rounds = max_rounds
        self.record = record

    def solve(self, economy, seed: int) -> Plan:
        plan = trivial_plan(economy)
        iterate(
            lambda: 0,
            lambda s: s + 1,
            lambda s: s >= self.rounds_to_converge,
            self.max_rounds,
            plan_of=(lambda s: plan) if self.record else None,
        )
        return plan


class TwoLoopProcedure:
    def solve(self, economy, seed: int) -> Plan:
        iterate(lambda: 0, lambda s: s + 1, lambda s: s >= 2, 10)
        iterate(lambda: 0, lambda s: s + 1, lambda s: s >= 7, 10)
        return trivial_plan(economy)


class NestingProcedure:
    """A procedure whose own loop must not be shadowed by a nested :func:`run`."""

    def __init__(self, inner, own_rounds: int | None):
        self.inner = inner
        self.own_rounds = own_rounds
        self.inner_result: RunResult | None = None

    def solve(self, economy, seed: int) -> Plan:
        if self.own_rounds is not None:
            iterate(lambda: 0, lambda s: s + 1, lambda s: s >= self.own_rounds, 20)
        self.inner_result = run(self.inner, economy, seed)
        return trivial_plan(economy)


class TestProtocol:
    def test_a_class_with_solve_satisfies_the_protocol(self):
        assert isinstance(DirectProcedure(), Procedure)

    def test_a_class_without_solve_does_not(self):
        class NotAProcedure:
            pass

        assert not isinstance(NotAProcedure(), Procedure)


class TestRunWithoutIterate:
    def test_rounds_and_convergence_are_unknown(self, synthetic_economy):
        result = run(DirectProcedure(), synthetic_economy, seed=0)
        assert isinstance(result, RunResult)
        assert isinstance(result.summary, RunSummary)
        assert result.summary.rounds is None
        assert result.summary.converged is None
        assert result.summary.trajectory is None

    def test_the_plan_is_passed_through(self, synthetic_economy):
        procedure = DirectProcedure()
        result = run(procedure, synthetic_economy, seed=0)
        assert result.plan.output.shape == (synthetic_economy.n_units,)

    def test_the_seed_reaches_the_procedure(self, synthetic_economy):
        procedure = DirectProcedure()
        run(procedure, synthetic_economy, seed=987654321)
        assert procedure.seen_seed == 987654321

    def test_wall_seconds_covers_the_solve(self, synthetic_economy):
        result = run(DirectProcedure(delay=0.05), synthetic_economy, seed=0)
        assert result.summary.wall_seconds >= 0.04


class TestRunWithIterate:
    def test_rounds_and_convergence_are_collected(self, synthetic_economy):
        result = run(LoopingProcedure(rounds_to_converge=4), synthetic_economy, seed=0)
        assert result.summary.rounds == 4
        assert result.summary.converged is True

    def test_a_loop_that_runs_out_of_rounds(self, synthetic_economy):
        result = run(
            LoopingProcedure(rounds_to_converge=99, max_rounds=6), synthetic_economy, seed=0
        )
        assert result.summary.rounds == 6
        assert result.summary.converged is False

    def test_trajectory_is_collected_when_the_procedure_asks_for_it(self, synthetic_economy):
        result = run(
            LoopingProcedure(rounds_to_converge=3, record=True), synthetic_economy, seed=0
        )
        assert result.summary.trajectory is not None
        assert len(result.summary.trajectory) == 3

    def test_the_last_loop_wins(self, synthetic_economy):
        result = run(TwoLoopProcedure(), synthetic_economy, seed=0)
        assert result.summary.rounds == 7


class TestRecorderScoping:
    def test_iterate_works_outside_run(self):
        result = iterate(lambda: 0, lambda s: s + 1, lambda s: s >= 2, 5)
        assert result.rounds == 2

    def test_a_nested_run_does_not_steal_the_outer_loop(self, synthetic_economy):
        outer = NestingProcedure(inner=LoopingProcedure(rounds_to_converge=2), own_rounds=5)
        result = run(outer, synthetic_economy, seed=0)
        assert result.summary.rounds == 5
        assert outer.inner_result.summary.rounds == 2

    def test_a_nested_run_does_not_leak_into_the_outer_summary(self, synthetic_economy):
        outer = NestingProcedure(inner=LoopingProcedure(rounds_to_converge=2), own_rounds=None)
        result = run(outer, synthetic_economy, seed=0)
        assert result.summary.rounds is None
        assert result.summary.converged is None
        assert outer.inner_result.summary.rounds == 2

    def test_the_recorder_is_cleared_after_run(self, synthetic_economy):
        """``run`` restores the collector it found, so a later loop is not recorded into it."""
        before = _recorder.get()
        run(LoopingProcedure(), synthetic_economy, seed=0)
        assert _recorder.get() is before

        standalone = iterate(lambda: 0, lambda s: s + 1, lambda s: s >= 1, 5)
        assert standalone.rounds == 1
        follow_up = run(DirectProcedure(), synthetic_economy, seed=0)
        assert follow_up.summary.rounds is None

    def test_a_failing_solve_still_clears_the_recorder(self, synthetic_economy):
        class Failing:
            def solve(self, economy, seed):
                iterate(lambda: 0, lambda s: s + 1, lambda s: s >= 3, 5)
                raise RuntimeError("procedure blew up")

        before = _recorder.get()
        with pytest.raises(RuntimeError, match="procedure blew up"):
            run(Failing(), synthetic_economy, seed=0)
        assert _recorder.get() is before
        result = run(DirectProcedure(), synthetic_economy, seed=0)
        assert result.summary.rounds is None
