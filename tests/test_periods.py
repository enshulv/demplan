"""The multi-period driver: seeds, call sequence, static mode, warnings and failure paths.

Every procedure and evolution law here is a stub written in this file. They record what they
were called with, so a test can check the driver's wiring by object identity rather than by
comparing values that two different wirings could both produce.
"""

from __future__ import annotations

import dataclasses
import warnings

import numpy as np
import pytest

import demplan
from demplan import (
    Advance,
    Economy,
    NextProcedure,
    Plan,
    PeriodResult,
    PeriodsResult,
    PeriodWarning,
    RunResult,
    iterate,
    rng,
    run_periods,
    split_seed,
)
from reference import synthetic

SEED = 20260926
"""Seed used where the value itself does not matter."""


def seeded_plan(economy: Economy, seed: int) -> Plan:
    """A plan whose output depends on ``seed`` alone, so two seeds give two distinct plans."""
    return Plan(
        output=rng(seed).random(economy.n_units),
        input_use=np.zeros(economy.n_inputs),
        consumption=np.zeros((economy.n_consumers, 0)),
        consumption_commodity=np.zeros(0, dtype=np.int64),
        shared_use=np.zeros(economy.n_commodities),
    )


class RecordingProcedure:
    """Solves with :func:`seeded_plan` and records every call and every plan it returned."""

    def __init__(self, label: str = "initial"):
        self.label = label
        self.calls: list[tuple[Economy, int]] = []
        self.plans: list[Plan] = []

    def solve(self, economy: Economy, seed: int) -> Plan:
        self.calls.append((economy, seed))
        plan = seeded_plan(economy, seed)
        self.plans.append(plan)
        return plan


class LoopingProcedure:
    """Drives a three-round loop through :func:`demplan.iterate` before returning its plan."""

    def solve(self, economy: Economy, seed: int) -> Plan:
        iterate(lambda: 0, lambda state: state + 1, lambda state: state >= 3, 10)
        return seeded_plan(economy, seed)


class RecordingAdvance:
    """Moves the economy one period on and records every call and every economy it returned.

    ``period_step`` sets how far ``period`` moves, so a test can produce a wrong period on
    purpose. The endowment is left alone.
    """

    def __init__(self, period_step: int = 1):
        self.period_step = period_step
        self.calls: list[tuple[Economy, Plan, int]] = []
        self.returned: list[Economy] = []

    def __call__(self, economy: Economy, plan: Plan, seed: int) -> Economy:
        self.calls.append((economy, plan, seed))
        following = dataclasses.replace(economy, period=economy.period + self.period_step)
        self.returned.append(following)
        return following


class RandomAdvance:
    """An evolution law whose only source of randomness is the seed it is given.

    It scales every endowed commodity by a factor drawn from that seed, so a driver that passed
    a different seed, or the same seed twice, would change the trajectory.
    """

    def __call__(self, economy: Economy, plan: Plan, seed: int) -> Economy:
        endowment = np.asarray(economy.endowment)
        factor = 1.0 + rng(seed).uniform(0.0, 0.1, endowment.shape[0])
        return dataclasses.replace(
            economy, period=economy.period + 1, endowment=endowment * factor
        )


class EndowmentSeededProcedure:
    """A procedure whose plan depends on the seed and on the economy's endowment.

    Used with :class:`RandomAdvance`, so a trajectory is identical on repeat only if both the
    solve seeds and the evolved economies are.
    """

    def solve(self, economy: Economy, seed: int) -> Plan:
        plan = seeded_plan(economy, seed)
        scale = float(np.asarray(economy.endowment).sum())
        return dataclasses.replace(plan, output=np.asarray(plan.output) * scale)


class RecordingNextProcedure:
    """Builds a fresh :class:`RecordingProcedure` per period and records what it was given."""

    def __init__(self):
        self.received: list[Plan] = []
        self.built: list[RecordingProcedure] = []

    def __call__(self, previous_plan: Plan) -> RecordingProcedure:
        self.received.append(previous_plan)
        procedure = RecordingProcedure(label=f"built-{len(self.built)}")
        self.built.append(procedure)
        return procedure


class Boom(Exception):
    """Raised by the stubs that test propagation."""


def plan_bytes(plan: Plan) -> bytes:
    return np.asarray(plan.output).tobytes()


def economy_with_period(period: int) -> Economy:
    return dataclasses.replace(synthetic.build_economy(), period=period)


class TestPublicSurface:
    def test_every_name_is_exported_from_the_package(self):
        for name in (
            "Advance",
            "NextProcedure",
            "PeriodResult",
            "PeriodWarning",
            "PeriodsResult",
            "run_periods",
        ):
            assert name in demplan.__all__
            assert getattr(demplan, name) is getattr(demplan.periods, name)

    def test_the_period_warning_is_a_user_warning(self):
        assert issubclass(PeriodWarning, UserWarning)

    def test_the_result_types_are_frozen(self):
        economy = synthetic.build_economy()
        result = run_periods(economy, RecordingProcedure(), periods=1, seed=SEED)
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.periods = ()
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.periods[0].index = 5

    def test_the_result_fields_are_the_specified_ones(self):
        assert [field.name for field in dataclasses.fields(PeriodResult)] == [
            "index",
            "economy",
            "result",
            "solve_seed",
            "advance_seed",
        ]
        assert [field.name for field in dataclasses.fields(PeriodsResult)] == [
            "periods",
            "differences",
        ]

    def test_plain_functions_pass_the_protocol_isinstance_checks(self):
        def advance(economy, plan, seed):
            return economy

        assert isinstance(advance, Advance)
        assert isinstance(lambda economy, plan, seed: economy, Advance)
        assert isinstance(lambda previous_plan: RecordingProcedure(), NextProcedure)
        assert isinstance(RecordingNextProcedure(), NextProcedure)

    def test_objects_that_cannot_be_called_fail_the_protocol_isinstance_checks(self):
        assert not isinstance(3, Advance)
        assert not isinstance(RecordingProcedure(), NextProcedure)


class TestSeedLayout:
    """Period ``i`` solves with word ``2i``; the economy of period ``i+1`` comes from word ``2i+1``.

    The expected words are recomputed here from :func:`demplan.split_seed` with the layout
    written out by hand, not read back from the driver.
    """

    @pytest.mark.parametrize("seed", [0, 1, SEED, 2**64 - 1])
    def test_solve_and_advance_seeds_follow_the_even_odd_layout(self, seed):
        periods = 4
        words = split_seed(seed, 2 * periods)
        procedure = RecordingProcedure()
        advance = RecordingAdvance()

        result = run_periods(
            synthetic.build_economy(), procedure, periods=periods, seed=seed, advance=advance
        )

        assert [call_seed for _, call_seed in procedure.calls] == [
            words[0],
            words[2],
            words[4],
            words[6],
        ]
        assert [call_seed for _, _, call_seed in advance.calls] == [words[1], words[3], words[5]]
        assert [p.solve_seed for p in result.periods] == [words[0], words[2], words[4], words[6]]
        assert [p.advance_seed for p in result.periods] == [None, words[1], words[3], words[5]]

    def test_advance_seed_is_none_everywhere_in_static_mode(self):
        result = run_periods(synthetic.build_economy(), RecordingProcedure(), periods=3, seed=SEED)
        assert [p.advance_seed for p in result.periods] == [None, None, None]

    def test_advance_seed_is_none_in_static_mode_with_a_next_procedure(self):
        result = run_periods(
            synthetic.build_economy(),
            RecordingProcedure(),
            periods=3,
            seed=SEED,
            next_procedure=RecordingNextProcedure(),
        )
        assert [p.advance_seed for p in result.periods] == [None, None, None]

    def test_solve_seeds_follow_the_layout_when_the_procedure_changes_each_period(self):
        words = split_seed(SEED, 6)
        first = RecordingProcedure()
        factory = RecordingNextProcedure()

        run_periods(
            synthetic.build_economy(), first, periods=3, seed=SEED, next_procedure=factory
        )

        assert [s for _, s in first.calls] == [words[0]]
        assert [s for _, s in factory.built[0].calls] == [words[2]]
        assert [s for _, s in factory.built[1].calls] == [words[4]]

    def test_a_longer_run_extends_a_shorter_one_without_changing_its_periods(self):
        economy = synthetic.build_economy()
        short = run_periods(
            economy, RecordingProcedure(), periods=2, seed=SEED, advance=RandomAdvance()
        )
        long = run_periods(
            economy, RecordingProcedure(), periods=3, seed=SEED, advance=RandomAdvance()
        )

        for before, after in zip(short.periods, long.periods, strict=False):
            assert after.solve_seed == before.solve_seed
            assert after.advance_seed == before.advance_seed
            assert plan_bytes(after.result.plan) == plan_bytes(before.result.plan)
            assert (
                np.asarray(after.economy.endowment).tobytes()
                == np.asarray(before.economy.endowment).tobytes()
            )
        assert len(long.periods) == 3


class TestDeterminism:
    def test_the_same_inputs_give_bit_identical_trajectories(self):
        economy = synthetic.build_economy()

        def trajectory():
            result = run_periods(
                economy,
                EndowmentSeededProcedure(),
                periods=4,
                seed=SEED,
                advance=RandomAdvance(),
            )
            return [
                (
                    p.solve_seed,
                    p.advance_seed,
                    p.economy.period,
                    np.asarray(p.economy.endowment).tobytes(),
                    plan_bytes(p.result.plan),
                )
                for p in result.periods
            ]

        first = trajectory()
        assert trajectory() == first

    def test_a_random_evolution_law_actually_changes_the_economy(self):
        """Guards the determinism test above: a law that changed nothing would make it vacuous."""
        economy = synthetic.build_economy()
        result = run_periods(
            economy, EndowmentSeededProcedure(), periods=3, seed=SEED, advance=RandomAdvance()
        )
        endowments = [np.asarray(p.economy.endowment).tobytes() for p in result.periods]
        assert len(set(endowments)) == 3

    def test_a_different_seed_gives_a_different_trajectory(self):
        economy = synthetic.build_economy()
        first = run_periods(
            economy, EndowmentSeededProcedure(), periods=2, seed=SEED, advance=RandomAdvance()
        )
        second = run_periods(
            economy, EndowmentSeededProcedure(), periods=2, seed=SEED + 1, advance=RandomAdvance()
        )
        assert np.asarray(first.periods[1].economy.endowment).tobytes() != np.asarray(
            second.periods[1].economy.endowment
        ).tobytes()


class TestCallSequence:
    def test_each_period_records_the_economy_it_solved_and_what_run_returned(self):
        economy = synthetic.build_economy()
        procedure = RecordingProcedure()
        advance = RecordingAdvance()

        result = run_periods(economy, procedure, periods=3, seed=SEED, advance=advance)

        assert isinstance(result, PeriodsResult)
        assert isinstance(result.periods, tuple)
        assert [p.index for p in result.periods] == [0, 1, 2]
        solved = [call_economy for call_economy, _ in procedure.calls]
        assert solved[0] is economy
        assert solved[1] is advance.returned[0]
        assert solved[2] is advance.returned[1]
        for period, solved_economy, plan in zip(
            result.periods, solved, procedure.plans, strict=True
        ):
            assert isinstance(period, PeriodResult)
            assert period.economy is solved_economy
            assert isinstance(period.result, RunResult)
            assert period.result.plan is plan

    def test_each_period_is_run_through_demplan_run(self):
        """A loop inside ``solve`` shows up in the period's summary only if ``run`` was used."""
        result = run_periods(synthetic.build_economy(), LoopingProcedure(), periods=2, seed=SEED)
        assert [p.result.summary.rounds for p in result.periods] == [3, 3]
        assert all(p.result.summary.converged for p in result.periods)

    def test_advance_receives_the_previous_economy_and_plan(self):
        economy = synthetic.build_economy()
        procedure = RecordingProcedure()
        advance = RecordingAdvance()

        result = run_periods(economy, procedure, periods=4, seed=SEED, advance=advance)

        assert len(advance.calls) == 3
        for i, (call_economy, call_plan, _) in enumerate(advance.calls):
            assert call_economy is result.periods[i].economy
            assert call_plan is result.periods[i].result.plan
            assert call_plan is procedure.plans[i]

    @pytest.mark.parametrize("periods", [1, 2, 5])
    def test_advance_is_called_once_between_consecutive_periods(self, periods):
        advance = RecordingAdvance()
        run_periods(
            synthetic.build_economy(), RecordingProcedure(), periods=periods, seed=SEED,
            advance=advance,
        )
        assert len(advance.calls) == periods - 1

    def test_each_period_keeps_the_economy_advance_returned(self):
        advance = RecordingAdvance()
        result = run_periods(
            synthetic.build_economy(), RecordingProcedure(), periods=3, seed=SEED, advance=advance
        )
        assert result.periods[1].economy is advance.returned[0]
        assert result.periods[2].economy is advance.returned[1]
        assert [p.economy.period for p in result.periods] == [0, 1, 2]

    def test_next_procedure_receives_the_previous_plan_and_its_procedure_solves_next(self):
        economy = synthetic.build_economy()
        first = RecordingProcedure()
        factory = RecordingNextProcedure()

        result = run_periods(economy, first, periods=3, seed=SEED, next_procedure=factory)

        assert len(first.calls) == 1
        assert len(factory.received) == 2
        assert factory.received[0] is first.plans[0]
        assert factory.received[1] is factory.built[0].plans[0]
        assert len(factory.built[0].calls) == 1
        assert len(factory.built[1].calls) == 1
        assert result.periods[1].result.plan is factory.built[0].plans[0]
        assert result.periods[2].result.plan is factory.built[1].plans[0]

    def test_next_procedure_and_advance_together(self):
        economy = synthetic.build_economy()
        first = RecordingProcedure()
        factory = RecordingNextProcedure()
        advance = RecordingAdvance()

        result = run_periods(
            economy, first, periods=3, seed=SEED, advance=advance, next_procedure=factory
        )

        assert factory.built[0].calls[0][0] is advance.returned[0]
        assert factory.built[1].calls[0][0] is advance.returned[1]
        assert factory.received == [first.plans[0], factory.built[0].plans[0]]
        assert [p.index for p in result.periods] == [0, 1, 2]

    def test_one_period_calls_neither_advance_nor_next_procedure(self):
        economy = synthetic.build_economy()
        procedure = RecordingProcedure()
        advance = RecordingAdvance()
        factory = RecordingNextProcedure()

        result = run_periods(
            economy, procedure, periods=1, seed=SEED, advance=advance, next_procedure=factory
        )

        assert advance.calls == []
        assert factory.received == []
        assert len(procedure.calls) == 1
        assert len(result.periods) == 1
        assert result.periods[0].economy is economy
        assert result.periods[0].advance_seed is None
        assert result.periods[0].solve_seed == split_seed(SEED, 2)[0]


class TestStaticMode:
    def test_every_period_solves_the_same_economy_object(self):
        economy = synthetic.build_economy()
        procedure = RecordingProcedure()

        result = run_periods(economy, procedure, periods=3, seed=SEED)

        assert all(call_economy is economy for call_economy, _ in procedure.calls)
        assert all(p.economy is economy for p in result.periods)

    def test_every_period_is_solved_by_the_same_procedure_object(self):
        procedure = RecordingProcedure()
        run_periods(synthetic.build_economy(), procedure, periods=3, seed=SEED)
        assert len(procedure.calls) == 3

    def test_the_procedure_is_reused_when_only_advance_is_given(self):
        procedure = RecordingProcedure()
        run_periods(
            synthetic.build_economy(), procedure, periods=3, seed=SEED, advance=RecordingAdvance()
        )
        assert len(procedure.calls) == 3

    def test_the_economy_is_reused_when_only_next_procedure_is_given(self):
        economy = synthetic.build_economy()
        factory = RecordingNextProcedure()
        result = run_periods(
            economy, RecordingProcedure(), periods=3, seed=SEED, next_procedure=factory
        )
        assert factory.built[0].calls[0][0] is economy
        assert factory.built[1].calls[0][0] is economy
        assert all(p.economy is economy for p in result.periods)


class TestInvalidArguments:
    @pytest.mark.parametrize("periods", [0, -1, -7, 1.0, 2.5, True, False, "2", None])
    def test_periods_must_be_a_positive_int(self, periods):
        procedure = RecordingProcedure()
        with pytest.raises(ValueError) as info:
            run_periods(synthetic.build_economy(), procedure, periods=periods, seed=SEED)
        assert repr(periods) in str(info.value)
        assert procedure.calls == []

    @pytest.mark.parametrize(
        "periods",
        [np.bool_(True), np.bool_(False), np.int64(0), np.int32(-3), np.float64(2.0)],
        ids=["np-true", "np-false", "np-int64-zero", "np-int32-negative", "np-float64"],
    )
    def test_numpy_values_other_than_positive_integers_are_refused(self, periods):
        procedure = RecordingProcedure()
        with pytest.raises(ValueError) as info:
            run_periods(synthetic.build_economy(), procedure, periods=periods, seed=SEED)
        assert repr(periods) in str(info.value)
        assert procedure.calls == []

    @pytest.mark.parametrize(
        "periods",
        [np.int64(3), np.int32(3), np.uint8(3)],
        ids=["np-int64", "np-int32", "np-uint8"],
    )
    def test_numpy_integer_periods_give_the_same_run_as_an_int(self, periods):
        economy = synthetic.build_economy()
        expected = run_periods(
            economy, RecordingProcedure(), periods=3, seed=SEED, advance=RandomAdvance()
        )
        result = run_periods(
            economy, RecordingProcedure(), periods=periods, seed=SEED, advance=RandomAdvance()
        )
        assert len(result.periods) == 3
        assert [p.solve_seed for p in result.periods] == [p.solve_seed for p in expected.periods]
        assert [p.advance_seed for p in result.periods] == [
            p.advance_seed for p in expected.periods
        ]
        assert [plan_bytes(p.result.plan) for p in result.periods] == [
            plan_bytes(p.result.plan) for p in expected.periods
        ]

    def test_a_narrow_numpy_integer_does_not_wrap_in_the_seed_count(self):
        """``2 * np.uint8(130)`` wraps to 4 in numpy arithmetic; the run still has 130 periods."""
        result = run_periods(
            synthetic.build_economy(), RecordingProcedure(), periods=np.uint8(130), seed=SEED
        )
        assert len(result.periods) == 130
        assert [p.solve_seed for p in result.periods] == split_seed(SEED, 260)[0::2]

    @pytest.mark.parametrize("seed", [-1, 2**64, 1.5, True])
    def test_an_invalid_seed_raises_the_seed_error(self, seed):
        procedure = RecordingProcedure()
        with pytest.raises(ValueError) as info:
            run_periods(synthetic.build_economy(), procedure, periods=2, seed=seed)
        assert "seed" in str(info.value)
        assert procedure.calls == []

    def test_advance_must_return_an_economy(self):
        returned = {"not": "an economy"}
        procedure = RecordingProcedure()
        calls = []

        def advance(economy, plan, seed):
            calls.append(economy.period)
            if len(calls) == 2:
                return returned
            return dataclasses.replace(economy, period=economy.period + 1)

        with pytest.raises(TypeError) as info:
            run_periods(
                synthetic.build_economy(), procedure, periods=4, seed=SEED, advance=advance
            )
        message = str(info.value)
        assert "dict" in message
        assert "period 1" in message
        assert len(procedure.calls) == 2

    def test_advance_returning_none_is_refused(self):
        with pytest.raises(TypeError) as info:
            run_periods(
                synthetic.build_economy(),
                RecordingProcedure(),
                periods=2,
                seed=SEED,
                advance=lambda economy, plan, seed: None,
            )
        assert "NoneType" in str(info.value)
        assert "period 0" in str(info.value)

    @pytest.mark.parametrize(
        "built",
        [None, object(), type("SolveIsData", (), {"solve": 3})()],
        ids=["none", "no-solve", "solve-not-callable"],
    )
    def test_next_procedure_must_return_something_with_a_callable_solve(self, built):
        first = RecordingProcedure()
        with pytest.raises(TypeError) as info:
            run_periods(
                synthetic.build_economy(),
                first,
                periods=3,
                seed=SEED,
                next_procedure=lambda previous_plan: built,
            )
        message = str(info.value)
        assert type(built).__name__ in message
        assert "period 0" in message
        assert len(first.calls) == 1

    def test_a_next_procedure_result_with_a_callable_solve_is_accepted(self):
        """Any object with a callable ``solve`` is a procedure; no base class is required."""

        class Minimal:
            def solve(self, economy, seed):
                return seeded_plan(economy, seed)

        result = run_periods(
            synthetic.build_economy(),
            RecordingProcedure(),
            periods=2,
            seed=SEED,
            next_procedure=lambda previous_plan: Minimal(),
        )
        assert len(result.periods) == 2


class TestPropagation:
    def test_an_exception_from_solve_propagates_unchanged(self):
        raised = Boom("solve failed")

        class FailsInSecondPeriod(RecordingProcedure):
            def solve(self, economy, seed):
                if self.calls:
                    raise raised
                return super().solve(economy, seed)

        with pytest.raises(Boom) as info:
            run_periods(synthetic.build_economy(), FailsInSecondPeriod(), periods=3, seed=SEED)
        assert info.value is raised

    def test_an_exception_from_advance_propagates_unchanged(self):
        raised = Boom("advance failed")
        procedure = RecordingProcedure()

        def advance(economy, plan, seed):
            raise raised

        with pytest.raises(Boom) as info:
            run_periods(
                synthetic.build_economy(), procedure, periods=3, seed=SEED, advance=advance
            )
        assert info.value is raised
        assert len(procedure.calls) == 1

    def test_an_exception_from_next_procedure_propagates_unchanged(self):
        raised = Boom("next_procedure failed")
        procedure = RecordingProcedure()

        def next_procedure(previous_plan):
            raise raised

        with pytest.raises(Boom) as info:
            run_periods(
                synthetic.build_economy(),
                procedure,
                periods=3,
                seed=SEED,
                next_procedure=next_procedure,
            )
        assert info.value is raised
        assert len(procedure.calls) == 1

    def test_a_value_error_from_solve_is_not_rewrapped(self):
        """The driver raises ``ValueError`` itself; one from ``solve`` still arrives as is."""
        raised = ValueError("from the procedure")

        class Fails:
            def solve(self, economy, seed):
                raise raised

        with pytest.raises(ValueError) as info:
            run_periods(synthetic.build_economy(), Fails(), periods=2, seed=SEED)
        assert info.value is raised


class TestStepOrder:
    """Between two periods: ``advance``, then the period warning, then ``next_procedure``."""

    def test_advance_then_warning_then_next_procedure(self):
        log: list[str] = []

        def advance(economy, plan, seed):
            log.append("advance")
            return dataclasses.replace(economy, period=economy.period + 2)

        def next_procedure(previous_plan):
            log.append("next_procedure")
            return RecordingProcedure()

        def show_warning(message, category, filename, lineno, file=None, line=None):
            log.append(f"warning:{category.__name__}")

        with warnings.catch_warnings():
            warnings.simplefilter("always")
            warnings.showwarning = show_warning
            run_periods(
                synthetic.build_economy(),
                RecordingProcedure(),
                periods=3,
                seed=SEED,
                advance=advance,
                next_procedure=next_procedure,
            )

        assert log == [
            "advance",
            "warning:PeriodWarning",
            "next_procedure",
            "advance",
            "warning:PeriodWarning",
            "next_procedure",
        ]

    def test_next_procedure_is_not_called_when_advance_raises(self):
        factory = RecordingNextProcedure()

        def advance(economy, plan, seed):
            raise Boom("advance failed")

        with pytest.raises(Boom):
            run_periods(
                synthetic.build_economy(),
                RecordingProcedure(),
                periods=3,
                seed=SEED,
                advance=advance,
                next_procedure=factory,
            )
        assert factory.received == []

    def test_next_procedure_is_not_called_when_advance_returns_a_non_economy(self):
        factory = RecordingNextProcedure()
        with pytest.raises(TypeError):
            run_periods(
                synthetic.build_economy(),
                RecordingProcedure(),
                periods=3,
                seed=SEED,
                advance=lambda economy, plan, seed: None,
                next_procedure=factory,
            )
        assert factory.received == []


def period_warnings(caught) -> list[warnings.WarningMessage]:
    return [w for w in caught if issubclass(w.category, PeriodWarning)]


class TestPeriodCheck:
    def test_a_wrong_period_emits_a_warning_naming_both_periods(self):
        economy = economy_with_period(40)

        def advance(economy, plan, seed):
            return dataclasses.replace(economy, period=97)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = run_periods(
                economy, RecordingProcedure(), periods=2, seed=SEED, advance=advance
            )

        found = period_warnings(caught)
        assert len(found) == 1
        message = str(found[0].message)
        assert "41" in message
        assert "97" in message
        assert "check_period=False" in message
        assert result.periods[1].economy.period == 97

    def test_the_warning_points_at_the_caller(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            run_periods(
                synthetic.build_economy(),
                RecordingProcedure(),
                periods=2,
                seed=SEED,
                advance=RecordingAdvance(period_step=0),
            )
        found = period_warnings(caught)
        assert len(found) == 1
        assert found[0].filename == __file__

    def test_the_run_continues_with_the_economy_as_returned(self):
        advance = RecordingAdvance(period_step=0)
        procedure = RecordingProcedure()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = run_periods(
                synthetic.build_economy(), procedure, periods=3, seed=SEED, advance=advance
            )

        assert len(period_warnings(caught)) == 2
        assert len(result.periods) == 3
        assert result.periods[1].economy is advance.returned[0]
        assert result.periods[2].economy is advance.returned[1]
        assert procedure.calls[2][0] is advance.returned[1]

    def test_the_expected_period_is_one_more_than_the_economy_actually_returned(self):
        """After a jump to 97 the next expectation is 98, not 2."""
        economy = economy_with_period(40)
        steps = iter([57, 1, 5])

        def advance(economy, plan, seed):
            return dataclasses.replace(economy, period=economy.period + next(steps))

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            run_periods(economy, RecordingProcedure(), periods=4, seed=SEED, advance=advance)

        messages = [str(w.message) for w in period_warnings(caught)]
        assert len(messages) == 2
        assert "41" in messages[0] and "97" in messages[0]
        assert "99" in messages[1] and "103" in messages[1]

    def test_a_warnings_filter_can_turn_the_warning_into_an_error(self):
        """The category is ``PeriodWarning``, so a filter on that class alone catches it."""
        with warnings.catch_warnings():
            warnings.simplefilter("error", PeriodWarning)
            with pytest.raises(PeriodWarning):
                run_periods(
                    synthetic.build_economy(),
                    RecordingProcedure(),
                    periods=2,
                    seed=SEED,
                    advance=RecordingAdvance(period_step=2),
                )

    def test_check_period_false_silences_the_warning(self):
        advance = RecordingAdvance(period_step=0)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = run_periods(
                synthetic.build_economy(),
                RecordingProcedure(),
                periods=3,
                seed=SEED,
                advance=advance,
                check_period=False,
            )
        assert period_warnings(caught) == []
        assert len(advance.calls) == 2
        assert len(result.periods) == 3

    def test_static_mode_emits_no_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            run_periods(synthetic.build_economy(), RecordingProcedure(), periods=3, seed=SEED)
        assert period_warnings(caught) == []

    def test_static_mode_with_a_next_procedure_emits_no_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            run_periods(
                synthetic.build_economy(),
                RecordingProcedure(),
                periods=3,
                seed=SEED,
                next_procedure=RecordingNextProcedure(),
            )
        assert period_warnings(caught) == []

    def test_correct_increments_emit_no_warning(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            run_periods(
                economy_with_period(7),
                RecordingProcedure(),
                periods=4,
                seed=SEED,
                advance=RecordingAdvance(),
            )
        assert period_warnings(caught) == []
