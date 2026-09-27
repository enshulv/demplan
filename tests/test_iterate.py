"""The voluntary loop tool.

The round count is the contract that lets a prefab reproduce a published iteration count, so
these tests pin it from both sides: the number of ``step`` calls, and the fact that the
convergence test runs after ``step`` and never after ``init``.
"""

from __future__ import annotations

import numpy as np
import pytest

from demplan import IterateResult, Plan, SchemaError, iterate


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
        "shared_use": np.ones(3),
    }
    fields[field] = np.full_like(fields[field], value)
    return Plan(
        output=fields["output"],
        input_use=fields["input_use"],
        consumption=fields["consumption"],
        consumption_commodity=np.array([0, 1], dtype=np.int64),
        shared_use=fields["shared_use"],
    )


class TestRoundCounting:
    def test_rounds_equal_the_number_of_step_calls(self):
        log: list[int] = []
        result = iterate(lambda: 0, counting_step(log), lambda s: s >= 3, max_rounds=10)
        assert result.rounds == 3
        assert len(log) == 3
        assert result.state == 3
        assert result.converged is True
        assert result.diverged is None

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
        assert result.diverged is None
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
        assert result.diverged is None
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
    @pytest.mark.parametrize("field", ["output", "input_use", "consumption", "shared_use"])
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
                shared_use=np.ones(3),
                valuation={"indicative_price": np.full(3, np.nan)},
            )

        result = iterate(lambda: 0, lambda s: s + 1, lambda s: s == 2, 10, plan_of=plan_of)
        assert result.diverged is False
        assert result.converged is True

    def test_divergence_is_seen_without_keeping_the_trajectory(self):
        """Watching for divergence costs one ``plan_of`` call a round, not one plan kept."""
        def plan_of(state: int) -> Plan:
            return plan_with(np.inf if state == 3 else 1.0)

        result = iterate(
            lambda: 0,
            lambda s: s + 1,
            lambda s: False,
            10,
            plan_of=plan_of,
            keep_trajectory=False,
        )
        assert result.diverged is True
        assert result.converged is False
        assert result.rounds == 3
        assert result.trajectory is None

    def test_not_keeping_the_trajectory_leaves_the_round_count_alone(self):
        plans = []

        def plan_of(state: int) -> Plan:
            plans.append(state)
            return plan_with(float(state))

        result = iterate(
            lambda: 0, lambda s: s + 1, lambda s: s == 4, 10, plan_of=plan_of,
            keep_trajectory=False,
        )
        assert result.rounds == 4
        assert result.converged is True
        assert result.trajectory is None
        assert plans == [1, 2, 3, 4]

    def test_keeping_the_trajectory_is_the_default_when_plan_of_is_given(self):
        result = iterate(
            lambda: 0, lambda s: s + 1, lambda s: s == 2, 10, plan_of=lambda s: plan_with(1.0)
        )
        assert result.trajectory is not None
        assert len(result.trajectory) == 2

    def test_keeping_the_trajectory_without_plan_of_still_yields_nothing(self):
        result = iterate(lambda: 0, lambda s: s + 1, lambda s: s == 2, 10, keep_trajectory=True)
        assert result.trajectory is None

    def test_without_plan_of_the_library_cannot_see_divergence(self):
        result = iterate(
            lambda: 0.0, lambda s: float("nan"), lambda s: s == 0.0, max_rounds=3
        )
        assert result.diverged is None
        assert result.converged is False
        assert result.rounds == 3


class TestDivergenceHasThreeAnswers:
    """Diverged, did not diverge, and nobody looked -- the third is ``None``, not ``False``.

    ``plan_of`` is the library's only window into the state, so a loop driven without one is
    watched by nothing. Reporting that as ``False`` puts it in with the loops that ran under
    the watch and stayed finite, which is the reading ``converged=False, diverged=False``
    carries: the round cap ran out.
    """

    def watched(self, converge_at: int, max_rounds: int):
        return iterate(
            lambda: 0,
            lambda s: s + 1,
            lambda s: s >= converge_at,
            max_rounds,
            plan_of=lambda s: plan_with(1.0),
        )

    def unwatched(self, converge_at: int, max_rounds: int):
        return iterate(lambda: 0, lambda s: s + 1, lambda s: s >= converge_at, max_rounds)

    def test_an_unwatched_loop_that_converges_reports_divergence_as_unknown(self):
        result = self.unwatched(converge_at=3, max_rounds=10)
        assert result.converged is True
        assert result.diverged is None
        assert result.rounds == 3

    def test_an_unwatched_loop_that_spends_its_round_cap_reports_divergence_as_unknown(self):
        result = self.unwatched(converge_at=99, max_rounds=4)
        assert result.converged is False
        assert result.diverged is None
        assert result.rounds == 4

    def test_a_watched_loop_that_converges_reports_no_divergence(self):
        result = self.watched(converge_at=3, max_rounds=10)
        assert result.converged is True
        assert result.diverged is False

    def test_a_watched_loop_that_spends_its_round_cap_reports_no_divergence(self):
        result = self.watched(converge_at=99, max_rounds=4)
        assert result.converged is False
        assert result.diverged is False

    def test_watching_without_keeping_the_trajectory_still_answers_the_question(self):
        """``keep_trajectory`` decides what is stored, not whether the library looked."""
        result = iterate(
            lambda: 0,
            lambda s: s + 1,
            lambda s: s >= 2,
            10,
            plan_of=lambda s: plan_with(1.0),
            keep_trajectory=False,
        )
        assert result.diverged is False
        assert result.trajectory is None


def bare_plan_with(value: float) -> Plan:
    """A plan that declares the consumption block and shared_use absent."""
    return Plan(
        output=np.full(3, value),
        input_use=np.ones(4),
        consumption=None,
        consumption_commodity=None,
        shared_use=None,
    )


class TestDivergenceOnAPlanWithAbsentFields:
    """A field the mechanism does not have is not a field that went non-finite.

    The watch reads the physical columns the plan carries. Reading an absent one as
    non-finite would report divergence on every round of a mechanism that has no consumption
    block, and reading it as a zero would say the loop stayed finite on evidence nobody
    produced.
    """

    def test_a_plan_with_absent_fields_runs_the_loop(self):
        result = iterate(
            lambda: 0,
            lambda s: s + 1,
            lambda s: s == 3,
            10,
            plan_of=lambda s: bare_plan_with(float(s)),
        )
        assert result.rounds == 3
        assert result.converged is True
        assert result.diverged is False

    def test_absence_is_not_divergence(self):
        result = iterate(
            lambda: 0,
            lambda s: s + 1,
            lambda s: False,
            4,
            plan_of=lambda s: bare_plan_with(1.0),
        )
        assert result.diverged is False
        assert result.rounds == 4

    def test_a_non_finite_value_in_a_field_that_is_present_still_stops_the_loop(self):
        def plan_of(state: int) -> Plan:
            return bare_plan_with(np.nan if state == 2 else 1.0)

        result = iterate(lambda: 0, lambda s: s + 1, lambda s: False, 10, plan_of=plan_of)
        assert result.diverged is True
        assert result.rounds == 2

    def test_the_trajectory_keeps_the_plans_as_they_were_filed(self):
        result = iterate(
            lambda: 0,
            lambda s: s + 1,
            lambda s: s == 2,
            10,
            plan_of=lambda s: bare_plan_with(float(s)),
        )
        assert [p.absent_fields for p in result.trajectory] == [
            ("consumption", "consumption_commodity", "shared_use")
        ] * 2


class TestTheWatchAlwaysHasAColumnToRead:
    """``diverged=False`` is never the answer for want of an array to test.

    ``all()`` over an empty sequence is ``True``, so a plan carrying no physical column at all
    would clear the watch on no evidence and the loop would report a finite run it never saw.
    ``Plan`` refuses such a plan at construction, so every plan the watch reads carries at
    least ``output`` and ``input_use``.
    """

    def test_a_plan_with_no_physical_column_cannot_reach_the_watch(self):
        def plan_of(state: int) -> Plan:
            return Plan(
                output=None,
                input_use=None,
                consumption=None,
                consumption_commodity=None,
                shared_use=None,
            )

        with pytest.raises(SchemaError, match=r"Plan\.output"):
            iterate(lambda: 0, lambda s: s + 1, lambda s: False, 3, plan_of=plan_of)
