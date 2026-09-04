"""The voluntary loop tool.

The round count is the contract that lets a prefab reproduce a published iteration count, so
these tests pin it from both sides: the number of ``step`` calls, and the fact that the
convergence test runs after ``step`` and never after ``init``.
"""

from __future__ import annotations

import numpy as np
import pytest

from cyberstride import IterateResult, Plan, iterate


def counting_step(log: list[int]):
    def step(state: int) -> int:
        log.append(state)
        return state + 1

    return step


def plan_with(value: float, field: str = "output") -> Plan:
    fields = {
        "output": np.ones(3),
        "input_use": np.ones(4),
        "consumption": np.ones((2, 2)),
        "provision": np.ones(3),
    }
    fields[field] = np.full_like(fields[field], value)
    return Plan(
        output=fields["output"],
        input_use=fields["input_use"],
        consumption=fields["consumption"],
        consumption_commodity=np.array([0, 1], dtype=np.int64),
        provision=fields["provision"],
    )


class TestRoundCounting:
    def test_rounds_equal_the_number_of_step_calls(self):
        log: list[int] = []
        result = iterate(lambda: 0, counting_step(log), lambda s: s >= 3, max_rounds=10)
        assert result.rounds == 3
        assert len(log) == 3
        assert result.state == 3
        assert result.converged is True
        assert result.diverged is False

    def test_convergence_is_not_tested_after_init(self):
        log: list[int] = []
        result = iterate(lambda: 5, counting_step(log), lambda s: s >= 5, max_rounds=10)
        assert result.rounds == 1
        assert result.state == 6
        assert log == [5]

    def test_one_step_is_enough(self):
        result = iterate(lambda: 0, lambda s: s + 1, lambda s: s == 1, max_rounds=1)
        assert result.rounds == 1
        assert result.converged is True

    def test_exhausting_max_rounds(self):
        log: list[int] = []
        result = iterate(lambda: 0, counting_step(log), lambda s: False, max_rounds=4)
        assert result.converged is False
        assert result.diverged is False
        assert result.rounds == 4
        assert len(log) == 4
        assert result.state == 4

    @pytest.mark.parametrize("max_rounds", [0, -1, -100])
    def test_max_rounds_below_one_is_rejected(self, max_rounds):
        with pytest.raises(ValueError, match="max_rounds"):
            iterate(lambda: 0, lambda s: s + 1, lambda s: True, max_rounds=max_rounds)


class TestResultShape:
    def test_fields(self):
        result = iterate(lambda: 0, lambda s: s + 1, lambda s: s == 2, max_rounds=5)
        assert isinstance(result, IterateResult)
        assert result.state == 2
        assert result.rounds == 2
        assert result.converged is True
        assert result.diverged is False
        assert result.trajectory is None


class TestTrajectory:
    def test_absent_without_plan_of(self):
        result = iterate(lambda: 0, lambda s: s + 1, lambda s: s == 3, max_rounds=5)
        assert result.trajectory is None

    def test_one_plan_per_round(self):
        result = iterate(
            lambda: 0,
            lambda s: s + 1,
            lambda s: s == 3,
            max_rounds=5,
            plan_of=lambda s: plan_with(float(s)),
        )
        assert result.trajectory is not None
        assert len(result.trajectory) == 3
        assert all(isinstance(p, Plan) for p in result.trajectory)
        assert [float(p.output[0]) for p in result.trajectory] == [1.0, 2.0, 3.0]

    def test_covers_the_rounds_that_ran_without_converging(self):
        result = iterate(
            lambda: 0,
            lambda s: s + 1,
            lambda s: False,
            max_rounds=4,
            plan_of=lambda s: plan_with(float(s)),
        )
        assert len(result.trajectory) == 4
        assert result.converged is False


class TestDivergence:
    @pytest.mark.parametrize("field", ["output", "input_use", "consumption", "provision"])
    @pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
    def test_a_non_finite_physical_array_stops_the_loop(self, field, bad):
        def plan_of(state: int) -> Plan:
            return plan_with(bad if state == 2 else 1.0, field)

        result = iterate(lambda: 0, lambda s: s + 1, lambda s: False, 10, plan_of=plan_of)
        assert result.diverged is True
        assert result.converged is False
        assert result.rounds == 2
        assert len(result.trajectory) == 2

    def test_divergence_wins_over_convergence_in_the_same_round(self):
        result = iterate(
            lambda: 0,
            lambda s: s + 1,
            lambda s: True,
            10,
            plan_of=lambda s: plan_with(np.nan),
        )
        assert result.diverged is True
        assert result.converged is False

    def test_valuation_is_not_watched(self):
        def plan_of(state: int) -> Plan:
            return Plan(
                output=np.ones(3),
                input_use=np.ones(4),
                consumption=np.ones((2, 2)),
                consumption_commodity=np.array([0, 1], dtype=np.int64),
                provision=np.ones(3),
                valuation={"indicative_price": np.full(3, np.nan)},
            )

        result = iterate(lambda: 0, lambda s: s + 1, lambda s: s == 2, 10, plan_of=plan_of)
        assert result.diverged is False
        assert result.converged is True

    def test_without_plan_of_the_library_cannot_see_divergence(self):
        result = iterate(
            lambda: 0.0, lambda s: float("nan"), lambda s: s == 0.0, max_rounds=3
        )
        assert result.diverged is False
        assert result.converged is False
        assert result.rounds == 3
