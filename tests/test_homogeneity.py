"""The homogeneity check: one run, a rescaled run, and the comparison between their plans.

The procedures are stubs whose plans are known functions of a price attribute, so the value the
comparison must report is known in closed form.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from demplan import HomogeneityReport, PlanComparison, check_homogeneity, iterate
from test_differences import small_economy, small_plan


@dataclasses.dataclass(frozen=True)
class PricedProcedure:
    """Output is ``price * [8, 4, 2]``; nothing else depends on the price.

    ``calls`` records every solve, so a test can tell the procedure was not run.
    """

    price: float = 1.0
    output_scales: bool = True
    loop_rounds: int | None = None
    calls: list = dataclasses.field(default_factory=list, compare=False, init=False)

    def solve(self, economy, seed):
        self.calls.append((self.price, seed))
        if self.loop_rounds is not None:
            iterate(lambda: 0, lambda s: s + 1, lambda s: s >= self.loop_rounds, 50)
        factor = self.price if self.output_scales else 1.0
        return small_plan(output=np.array([8.0, 4.0, 2.0]) * factor)


def scale_price(procedure, economy, factor):
    return dataclasses.replace(procedure, price=procedure.price * factor), economy


class TestValues:
    def test_a_homogeneous_procedure_gives_zero_on_every_field(self):
        report = check_homogeneity(
            PricedProcedure(output_scales=False), small_economy(), 0, scale_price, 3.0
        )
        assert isinstance(report, HomogeneityReport)
        assert isinstance(report.comparison, PlanComparison)
        assert dict(report.comparison.max_relative_difference) == {
            "output": 0.0, "input_use": 0.0, "consumption": 0.0, "shared_use": 0.0,
        }

    @pytest.mark.parametrize("factor, expected", [(2.0, 0.5), (4.0, 0.75), (0.5, 0.5)])
    def test_output_proportional_to_the_price_gives_one_minus_the_smaller_ratio(
        self, factor, expected
    ):
        """``|p - f p| / max(p, f p)`` is ``1 - 1/f`` above 1 and ``1 - f`` below."""
        report = check_homogeneity(PricedProcedure(), small_economy(), 0, scale_price, factor)
        assert report.comparison.max_relative_difference["output"] == expected
        assert report.comparison.max_relative_difference["input_use"] == 0.0

    def test_the_report_names_the_factor_and_the_rescale(self):
        report = check_homogeneity(PricedProcedure(), small_economy(), 0, scale_price, 2)
        assert report.factor == 2.0
        assert report.rescale == "scale_price"

    def test_both_runs_use_the_seed_and_the_rescaled_procedure(self):
        procedure = PricedProcedure(price=1.5)
        seen = []

        def recording(p, economy, factor):
            rescaled = dataclasses.replace(p, price=p.price * factor)
            seen.append(rescaled)
            return rescaled, economy

        check_homogeneity(procedure, small_economy(), 17, recording, 2.0)
        assert procedure.calls == [(1.5, 17)]
        assert seen[0].calls == [(3.0, 17)]


class TestRounds:
    def test_rounds_are_none_for_a_procedure_without_iterate(self):
        report = check_homogeneity(PricedProcedure(), small_economy(), 0, scale_price, 2.0)
        assert report.rounds is None
        assert report.rounds_rescaled is None
        assert report.converged is None
        assert report.converged_rescaled is None

    def test_rounds_come_from_each_run(self):
        def rescale(procedure, economy, factor):
            return dataclasses.replace(procedure, loop_rounds=7), economy

        report = check_homogeneity(
            PricedProcedure(loop_rounds=4), small_economy(), 0, rescale, 2.0
        )
        assert report.rounds == 4
        assert report.rounds_rescaled == 7
        assert report.converged is True
        assert report.converged_rescaled is True


class TestRefusals:
    @pytest.mark.parametrize("factor", [1.0, 1, 0.0, -2.0, math.nan, math.inf, -math.inf])
    def test_a_factor_that_is_not_finite_positive_and_other_than_one_is_refused(self, factor):
        procedure = PricedProcedure()
        with pytest.raises(ValueError, match="factor"):
            check_homogeneity(procedure, small_economy(), 0, scale_price, factor)
        assert procedure.calls == []

    @pytest.mark.parametrize(
        "returned", [None, (PricedProcedure(),), [PricedProcedure(), None], "ab"]
    )
    def test_a_rescale_that_does_not_return_a_pair_is_a_type_error(self, returned):
        with pytest.raises(TypeError, match="pair"):
            check_homogeneity(
                PricedProcedure(), small_economy(), 0, lambda p, e, f: returned, 2.0
            )

    def test_the_factor_is_required(self):
        with pytest.raises(TypeError):
            check_homogeneity(PricedProcedure(), small_economy(), 0, scale_price)


def test_the_runs_do_not_compute_the_difference_report():
    """A plan that ``plan_differences`` would refuse still gets compared."""

    class Malformed:
        def solve(self, economy, seed):
            return small_plan(output=np.array([1.0]))

    report = check_homogeneity(
        Malformed(), small_economy(), 0, lambda p, e, f: (p, e), 2.0
    )
    assert report.comparison.max_relative_difference["output"] == 0.0
