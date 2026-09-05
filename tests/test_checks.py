"""The determinism self-test tool."""

from __future__ import annotations

import numpy as np
import pytest

from cyberstride import INDICATIVE_PRICE, DeterminismReport, Plan, check_determinism


class ScriptedProcedure:
    """Returns a prepared plan per call, so a test can script exactly what changes."""

    def __init__(self, plans):
        self.plans = list(plans)
        self.calls = 0
        self.seeds: list[int] = []

    def solve(self, economy, seed: int) -> Plan:
        self.seeds.append(seed)
        plan = self.plans[min(self.calls, len(self.plans) - 1)]
        self.calls += 1
        return plan


def make_plan(economy, output=None, provision=None, valuation=None) -> Plan:
    return Plan(
        output=np.ones(economy.n_units) if output is None else output,
        input_use=np.ones(economy.n_inputs),
        consumption=np.ones((economy.n_consumers, 3)),
        consumption_commodity=np.array([0, 1, 2], dtype=np.int64),
        provision=np.zeros(economy.n_commodities) if provision is None else provision,
        valuation={} if valuation is None else valuation,
    )


class TestIdenticalRuns:
    def test_a_deterministic_procedure_passes(self, synthetic_economy):
        plan = make_plan(synthetic_economy)
        report = check_determinism(
            ScriptedProcedure([plan]), synthetic_economy, seed=0, n=3
        )
        assert isinstance(report, DeterminismReport)
        assert report.identical is True
        assert report.differing_fields == []

    def test_equal_but_distinct_arrays_pass(self, synthetic_economy):
        plans = [make_plan(synthetic_economy) for _ in range(3)]
        report = check_determinism(ScriptedProcedure(plans), synthetic_economy, seed=0, n=3)
        assert report.identical is True

    def test_a_single_run_is_trivially_identical(self, synthetic_economy):
        procedure = ScriptedProcedure([make_plan(synthetic_economy)])
        report = check_determinism(procedure, synthetic_economy, seed=0, n=1)
        assert report.identical is True
        assert procedure.calls == 1

    def test_matching_non_finite_values_count_as_identical(self, synthetic_economy):
        output = np.full(synthetic_economy.n_units, np.nan)
        plans = [make_plan(synthetic_economy, output=output.copy()) for _ in range(2)]
        report = check_determinism(ScriptedProcedure(plans), synthetic_economy, seed=0, n=2)
        assert report.identical is True

    def test_every_run_gets_the_same_seed(self, synthetic_economy):
        procedure = ScriptedProcedure([make_plan(synthetic_economy)])
        check_determinism(procedure, synthetic_economy, seed=4242, n=4)
        assert procedure.seeds == [4242, 4242, 4242, 4242]
        assert procedure.calls == 4


class TestDifferingRuns:
    def test_a_changed_physical_column_is_named(self, synthetic_economy):
        first = make_plan(synthetic_economy)
        second = make_plan(synthetic_economy, output=np.full(synthetic_economy.n_units, 2.0))
        report = check_determinism(
            ScriptedProcedure([first, second]), synthetic_economy, seed=0, n=2
        )
        assert report.identical is False
        assert report.differing_fields == ["output"]

    def test_several_columns_are_all_named(self, synthetic_economy):
        first = make_plan(synthetic_economy)
        second = make_plan(
            synthetic_economy,
            output=np.full(synthetic_economy.n_units, 2.0),
            provision=np.full(synthetic_economy.n_commodities, 3.0),
        )
        report = check_determinism(
            ScriptedProcedure([first, second]), synthetic_economy, seed=0, n=2
        )
        assert report.identical is False
        assert set(report.differing_fields) == {"output", "provision"}

    def test_one_unit_in_the_last_place_is_enough(self, synthetic_economy):
        base = np.ones(synthetic_economy.n_units)
        nudged = base.copy()
        nudged[0] = np.nextafter(nudged[0], 2.0)
        report = check_determinism(
            ScriptedProcedure(
                [make_plan(synthetic_economy, output=base),
                 make_plan(synthetic_economy, output=nudged)]
            ),
            synthetic_economy,
            seed=0,
            n=2,
        )
        assert report.identical is False
        assert report.differing_fields == ["output"]

    def test_a_valuation_key_is_reported_with_its_prefix(self, synthetic_economy):
        size = synthetic_economy.n_commodities
        first = make_plan(synthetic_economy, valuation={INDICATIVE_PRICE: np.full(size, 700.0)})
        second = make_plan(synthetic_economy, valuation={INDICATIVE_PRICE: np.full(size, 701.0)})
        report = check_determinism(
            ScriptedProcedure([first, second]), synthetic_economy, seed=0, n=2
        )
        assert report.differing_fields == ["valuation.indicative_price"]

    def test_a_missing_valuation_key_is_reported(self, synthetic_economy):
        size = synthetic_economy.n_commodities
        first = make_plan(synthetic_economy, valuation={INDICATIVE_PRICE: np.full(size, 700.0)})
        second = make_plan(synthetic_economy, valuation={})
        report = check_determinism(
            ScriptedProcedure([first, second]), synthetic_economy, seed=0, n=2
        )
        assert report.identical is False
        assert report.differing_fields == ["valuation.indicative_price"]

    def test_a_difference_in_a_later_run_is_still_caught(self, synthetic_economy):
        stable = make_plan(synthetic_economy)
        drifted = make_plan(synthetic_economy, output=np.full(synthetic_economy.n_units, 5.0))
        report = check_determinism(
            ScriptedProcedure([stable, stable, drifted]), synthetic_economy, seed=0, n=3
        )
        assert report.identical is False
        assert report.differing_fields == ["output"]


class TestRejectedArguments:
    @pytest.mark.parametrize("n", [0, -1])
    def test_run_count_below_one(self, synthetic_economy, n):
        with pytest.raises(ValueError, match="n"):
            check_determinism(
                ScriptedProcedure([make_plan(synthetic_economy)]), synthetic_economy, 0, n=n
            )


def make_bare_plan(economy, output=None) -> Plan:
    """A plan that declares the consumption block and provision absent."""
    return Plan(
        output=np.ones(economy.n_units) if output is None else output,
        input_use=np.ones(economy.n_inputs),
        consumption=None,
        consumption_commodity=None,
        provision=None,
    )


class TestRunsThatDeclareFieldsAbsent:
    """Two runs agree on a field neither of them has, and disagree when only one has it.

    A run whose mechanism has no consumption block reports nothing on it, twice. That is not a
    difference between the runs, and reporting it as one would make every such procedure look
    non-deterministic. The other way round, one run carrying the field and one not is a
    disagreement about whether the quantity exists at all, which is a different finding from
    two runs that computed different numbers.
    """

    def test_two_runs_that_both_declare_a_field_absent_agree(self, synthetic_economy):
        plans = [make_bare_plan(synthetic_economy) for _ in range(3)]
        report = check_determinism(ScriptedProcedure(plans), synthetic_economy, seed=0, n=3)
        assert report.identical is True
        assert report.differing_fields == []

    def test_a_field_present_in_one_run_and_absent_in_the_other_is_reported(
        self, synthetic_economy
    ):
        report = check_determinism(
            ScriptedProcedure(
                [make_plan(synthetic_economy), make_bare_plan(synthetic_economy)]
            ),
            synthetic_economy,
            seed=0,
            n=2,
        )
        assert report.identical is False
        assert report.differing_fields == [
            "consumption (absent from one run)",
            "consumption_commodity (absent from one run)",
            "provision (absent from one run)",
        ]

    def test_the_report_reads_the_same_whichever_run_carries_the_field(
        self, synthetic_economy
    ):
        report = check_determinism(
            ScriptedProcedure(
                [make_bare_plan(synthetic_economy), make_plan(synthetic_economy)]
            ),
            synthetic_economy,
            seed=0,
            n=2,
        )
        assert report.differing_fields == [
            "consumption (absent from one run)",
            "consumption_commodity (absent from one run)",
            "provision (absent from one run)",
        ]

    def test_an_absent_field_does_not_hide_a_difference_in_a_field_that_is_present(
        self, synthetic_economy
    ):
        nudged = np.ones(synthetic_economy.n_units)
        nudged[0] = 1.5
        report = check_determinism(
            ScriptedProcedure(
                [
                    make_bare_plan(synthetic_economy),
                    make_bare_plan(synthetic_economy, output=nudged),
                ]
            ),
            synthetic_economy,
            seed=0,
            n=2,
        )
        assert report.differing_fields == ["output"]
