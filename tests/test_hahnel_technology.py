"""The Hahnel model's technology: ``Q = a * e**c * prod(x_j ** b_j)`` as a checkable technology.

The hand-worked cases pick numbers whose powers are exact, so each expected margin is written
out from the formula. On a plan the Hahnel councils produced, the margin is zero up to rounding,
because the councils choose output, effort and inputs on this production function. The negative
control reads the same plan as plain Cobb-Douglas, which leaves the effort factor out: every
unit then falls short by exactly the share ``1 - e**-c`` of its planned output.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from demplan import COBB_DOUGLAS, EFFORT, Economy, Plan, Technology, load_dep1ex, run
from demplan import technology_margins
from demplan.prefabs import hahnel
from demplan.prefabs.hahnel import TECHNOLOGY, HahnelBook2021
from reference import synthetic
from reference.paths import dep1ex_available, dep1ex_path

MARGIN_RTOL = 1e-12
"""Largest margin accepted on a councils' plan, relative to the unit's planned output.

The councils compute output in logarithms and this check computes it as a product of powers,
so the two agree to rounding, not bit for bit. Measured on the converged dep1ex01 plan the
largest ratio is about 3e-15.
"""

HAND_RTOL = 1e-12
"""Tolerance on the hand-worked margins, whose exact values are small integers and quarters."""

LARGE_SHORTFALL = 1e-2
"""A plain Cobb-Douglas shortfall above this share of planned output counts as large."""

N_COMMODITIES = 5

# One row per unit: (scale a, effort e, effort exponent c,
# ((input commodity, exponent b, planned use x), ...), planned output).
UNITS = (
    # 2 * 4**0.5 * (4**0.5 * 9**0.5) = 2 * 2 * 6 = 24 against 20 planned.
    (2.0, 4.0, 0.5, ((3, 0.5, 4.0), (4, 0.5, 9.0)), 20.0),
    # 1 * 1**0.3 * 5**1 = 5 against 5 planned.
    (1.0, 1.0, 0.3, ((3, 1.0, 5.0),), 5.0),
    # 3 * 9**0.5 * 0.5**2 = 3 * 3 * 0.25 = 2.25 against 2 planned.
    (3.0, 9.0, 0.5, ((4, 2.0, 0.5),), 2.0),
)

HAND_MARGINS = (4.0, 0.0, 0.25)


def build_economy(units=UNITS, **overrides) -> Economy:
    """Every unit labelled with the Hahnel technology and carrying its effort exponent."""
    input_offsets = np.zeros(len(units) + 1, dtype=np.int64)
    np.cumsum([len(inputs) for _, _, _, inputs, _ in units], out=input_offsets[1:])
    fields = dict(
        period=0,
        commodity_id=np.arange(N_COMMODITIES, dtype=np.int64),
        endowment=np.zeros(N_COMMODITIES, dtype=np.float64),
        unit_id=np.arange(len(units), dtype=np.int64),
        technology_kind=[TECHNOLOGY] * len(units),
        technology_scale=np.array([a for a, _, _, _, _ in units], dtype=np.float64),
        input_offsets=input_offsets,
        input_commodity=np.array(
            [entry[0] for _, _, _, inputs, _ in units for entry in inputs], dtype=np.int64
        ),
        input_coefficient=np.array(
            [entry[1] for _, _, _, inputs, _ in units for entry in inputs], dtype=np.float64
        ),
        output_offsets=np.arange(len(units) + 1, dtype=np.int64),
        output_commodity=np.arange(len(units), dtype=np.int64) % 3,
        output_coefficient=np.ones(len(units), dtype=np.float64),
        consumer_id=np.arange(1, dtype=np.int64),
        unit_extra={"effort_c": np.array([c for _, _, c, _, _ in units], dtype=np.float64)},
    )
    fields.update(overrides)
    return Economy(**fields)


def build_plan(units=UNITS, **overrides) -> Plan:
    """Planned inputs, output and effort of ``units``."""
    fields = dict(
        output=np.array([q for _, _, _, _, q in units], dtype=np.float64),
        input_use=np.array(
            [entry[2] for _, _, _, inputs, _ in units for entry in inputs], dtype=np.float64
        ),
        consumption=None,
        consumption_commodity=None,
        shared_use=None,
        extra={EFFORT: np.array([e for _, e, _, _, _ in units], dtype=np.float64)},
    )
    fields.update(overrides)
    return Plan(**fields)


class TestHandWorked:
    def test_it_is_a_technology_carrying_the_hahnel_label(self):
        technology = hahnel.technology()
        assert technology.label == TECHNOLOGY
        assert isinstance(technology, Technology)

    @pytest.mark.parametrize("unit", range(len(UNITS)))
    def test_margin_of_each_unit(self, unit):
        margin = hahnel.technology().margin(build_economy(), build_plan(), unit)
        assert margin.shape == (1,)
        assert margin[0] == pytest.approx(HAND_MARGINS[unit], rel=HAND_RTOL, abs=HAND_RTOL)

    def test_through_the_check_tool(self):
        report = technology_margins(
            build_economy(), build_plan(), {TECHNOLOGY: hahnel.technology()}
        )
        np.testing.assert_allclose(report.margin, HAND_MARGINS, rtol=HAND_RTOL, atol=HAND_RTOL)
        assert report.computed.all()
        assert report.missing == {}

    def test_effort_is_read_per_unit_from_the_plan(self):
        """Effort 16 instead of 4 on unit 0 doubles e**0.5 and with it the deliverable output."""
        effort = np.array([16.0, 1.0, 9.0])
        plan = build_plan(extra={EFFORT: effort})
        margin = hahnel.technology().margin(build_economy(), plan, 0)
        assert margin[0] == pytest.approx(2.0 * 4.0 * 6.0 - 20.0, rel=HAND_RTOL)

    def test_the_effort_exponent_is_read_per_unit_from_the_economy(self):
        """With c = 1 on unit 2, e**c is 9 rather than 3: 3 * 9 * 0.25 = 6.75."""
        economy = build_economy(unit_extra={"effort_c": np.array([0.5, 0.3, 1.0])})
        margin = hahnel.technology().margin(economy, build_plan(), 2)
        assert margin[0] == pytest.approx(6.75 - 2.0, rel=HAND_RTOL)

    def test_without_the_label_supplied_the_check_tool_counts_every_unit_missing(self):
        report = technology_margins(build_economy(), build_plan())
        assert report.missing == {TECHNOLOGY: len(UNITS)}
        assert not report.computed.any()
        np.testing.assert_array_equal(report.margin, np.zeros(len(UNITS)))


class TestRefusals:
    def test_a_plan_without_effort_is_refused_in_plain_words(self):
        plan = build_plan(extra={})
        with pytest.raises(ValueError) as refused:
            hahnel.technology().margin(build_economy(), plan, 0)
        message = str(refused.value)
        assert repr(EFFORT) in message
        assert "extra" in message

    def test_an_economy_without_the_effort_exponent_is_refused_in_plain_words(self):
        economy = build_economy(unit_extra={})
        with pytest.raises(ValueError) as refused:
            hahnel.technology().margin(economy, build_plan(), 0)
        assert "effort_c" in str(refused.value)
        assert "unit_extra" in str(refused.value)

    def test_a_unit_with_two_output_entries_is_refused_by_number(self):
        economy = build_economy(
            output_offsets=np.array([0, 1, 3, 4], dtype=np.int64),
            output_commodity=np.array([0, 1, 2, 2], dtype=np.int64),
            output_coefficient=np.ones(4, dtype=np.float64),
        )
        plan = build_plan(output=np.array([20.0, 5.0, 1.0, 2.0]))
        with pytest.raises(ValueError, match=r"unit 1\b"):
            hahnel.technology().margin(economy, plan, 1)


def with_output_coefficient(economy: Economy, unit: int, value: float) -> Economy:
    column = np.asarray(economy.output_coefficient).copy()
    column[unit] = value
    return dataclasses.replace(economy, output_coefficient=column)


def plan_with_unit_effort(economy: Economy) -> Plan:
    """Output zero, every input at one and every effort at one: a plan the margin can read."""
    return Plan(
        output=np.zeros(economy.n_outputs, dtype=np.float64),
        input_use=np.ones(economy.n_inputs, dtype=np.float64),
        consumption=None,
        consumption_commodity=None,
        shared_use=None,
        extra={EFFORT: np.ones(economy.n_units, dtype=np.float64)},
    )


COEFFICIENT_REASON = "which has no output coefficient"
"""Where the reason in the councils' refusal starts; the technology's refusal has the same text
from here on."""


class TestOutputCoefficientIsOne:
    """The production function gives output itself, so an output coefficient has no place in it.

    The Hahnel councils refuse such a unit; the technology that reads their plans refuses it in
    the same words, since a margin computed with the coefficient ignored describes a unit the
    economy does not have.
    """

    @pytest.mark.parametrize("value", [2.0, 0.5, 1.0 + 1e-12])
    def test_a_coefficient_other_than_one_is_refused(self, value):
        economy = with_output_coefficient(build_economy(), 1, value)
        with pytest.raises(ValueError) as refused:
            hahnel.technology().margin(economy, build_plan(), 1)
        message = str(refused.value)
        assert f"unit 1 carries output_coefficient {value}" in message
        assert "Q = a * e**c * prod(x_j ** b_j)" in message

    def test_the_check_tool_passes_the_refusal_on(self):
        economy = with_output_coefficient(build_economy(), 2, 2.0)
        with pytest.raises(ValueError, match="unit 2 carries output_coefficient 2.0"):
            technology_margins(economy, build_plan(), {TECHNOLOGY: hahnel.technology()})

    def test_another_unit_of_the_same_economy_is_still_read(self):
        """The refusal is about the unit that carries the coefficient, not the economy."""
        economy = with_output_coefficient(build_economy(), 2, 2.0)
        margin = hahnel.technology().margin(economy, build_plan(), 0)
        assert margin[0] == pytest.approx(HAND_MARGINS[0], rel=HAND_RTOL)

    def test_the_refusal_is_the_one_the_councils_give(self):
        economy = with_output_coefficient(synthetic.build_economy(), 3, 2.0)
        with pytest.raises(ValueError) as councils:
            run(HahnelBook2021(), economy, seed=0)
        with pytest.raises(ValueError) as technology:
            hahnel.technology().margin(economy, plan_with_unit_effort(economy), 3)
        councils_reason = str(councils.value).split(COEFFICIENT_REASON, 1)
        technology_reason = str(technology.value).split(COEFFICIENT_REASON, 1)
        assert len(councils_reason) == 2
        assert len(technology_reason) == 2
        assert technology_reason[1] == councils_reason[1]
        assert technology_reason[1].endswith(
            "unit 3 carries output_coefficient 2.0. Set every output_coefficient to 1, as "
            "demplan.load_dep1ex does."
        )

    def test_a_coefficient_of_one_is_read(self):
        economy = synthetic.build_economy()
        assert np.all(np.asarray(economy.output_coefficient) == 1.0)
        margin = hahnel.technology().margin(economy, plan_with_unit_effort(economy), 3)
        assert margin.shape == (1,)


def _relative_margin(report, plan: Plan) -> np.ndarray:
    return np.abs(report.margin) / plan.output


def _plain_cobb_douglas_copy(economy: Economy) -> Economy:
    """``economy`` with every unit labelled plain Cobb-Douglas, nothing else changed."""
    return dataclasses.replace(economy, technology_kind=[COBB_DOUGLAS] * economy.n_units)


def _expected_plain_shortfall(economy: Economy, plan: Plan) -> np.ndarray:
    """What plain Cobb-Douglas reads on a plan made under the effort factor.

    Leaving ``e**c`` out divides the deliverable output by it, so the margin is
    ``output * (e**-c - 1)``.
    """
    effort = np.asarray(plan.extra[EFFORT])
    exponent = np.asarray(economy.unit_extra["effort_c"])
    return plan.output * (effort ** (-exponent) - 1.0)


@pytest.fixture(scope="module")
def synthetic_solved():
    """The synthetic economy and the plan the Hahnel councils make on it."""
    economy = synthetic.build_economy()
    return economy, run(HahnelBook2021(), economy, seed=0).plan


@pytest.fixture(scope="module")
def dep1ex01_solved():
    """dep1ex01 as the loader reads it and the plan the councils converge on, in 12 rounds."""
    economy = load_dep1ex(dep1ex_path(1), endowment=1000.0)
    result = run(HahnelBook2021(), economy, seed=0)
    assert result.summary.converged
    return economy, result.plan


class TestOnTheSyntheticCouncilsPlan:
    @pytest.fixture
    def solved(self, synthetic_solved):
        return synthetic_solved

    def test_every_margin_is_zero_up_to_rounding(self, solved):
        economy, plan = solved
        report = technology_margins(economy, plan, {TECHNOLOGY: hahnel.technology()})
        assert report.computed.all()
        assert report.missing == {}
        assert _relative_margin(report, plan).max() <= MARGIN_RTOL

    def test_plain_cobb_douglas_falls_short_by_the_effort_factor(self, solved):
        economy, plan = solved
        report = technology_margins(_plain_cobb_douglas_copy(economy), plan)
        assert report.computed.all()
        np.testing.assert_allclose(
            report.margin,
            _expected_plain_shortfall(economy, plan),
            rtol=0.0,
            atol=MARGIN_RTOL * plan.output.max(),
        )


needs_dep1ex01 = pytest.mark.skipif(not dep1ex_available(1), reason="dep1ex01 archive not present")


@pytest.mark.slow
@needs_dep1ex01
class TestOnTheConvergedDep1ex01Plan:
    @pytest.fixture
    def solved(self, dep1ex01_solved):
        return dep1ex01_solved

    def test_every_margin_is_within_the_tolerance_of_zero(self, solved):
        economy, plan = solved
        report = technology_margins(economy, plan, {TECHNOLOGY: hahnel.technology()})
        assert report.computed.all()
        assert report.missing == {}
        assert _relative_margin(report, plan).max() <= MARGIN_RTOL

    def test_without_the_hahnel_technology_every_unit_is_missing(self, solved):
        economy, plan = solved
        report = technology_margins(economy, plan)
        assert report.missing == {TECHNOLOGY: economy.n_units}
        assert not report.computed.any()

    def test_plain_cobb_douglas_reports_large_margins_on_most_units(self, solved):
        economy, plan = solved
        report = technology_margins(_plain_cobb_douglas_copy(economy), plan)
        assert report.computed.all()
        relative = _relative_margin(report, plan)
        assert np.mean(relative > LARGE_SHORTFALL) > 0.99
        # Effort is above 1 on every unit of this plan, so every unit falls short.
        assert (report.margin < 0.0).all()

    def test_the_plain_cobb_douglas_gap_is_the_effort_factor(self, solved):
        economy, plan = solved
        report = technology_margins(_plain_cobb_douglas_copy(economy), plan)
        np.testing.assert_allclose(
            report.margin / plan.output,
            _expected_plain_shortfall(economy, plan) / plan.output,
            rtol=0.0,
            atol=MARGIN_RTOL,
        )


class TestExport:
    def test_technology_is_exported_from_the_prefab(self):
        assert "technology" in hahnel.__all__
        assert callable(hahnel.technology)
