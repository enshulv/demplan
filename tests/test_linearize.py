"""Reading a plan's own input mix back as a fixed technology.

The tool's whole job is one identity: after linearising, asking the Leontief requirements for
the plan's own output has to return the plan's own input use. The tests check that identity on
a Cobb-Douglas economy, where the two technologies genuinely disagree, so an implementation
that forgot to divide or divided by the wrong thing cannot pass by coincidence.

The idle-unit case is checked on its own because a unit that produced nothing has no input
proportions to read, and the coefficients it gets say the unit needs nothing rather than that
it needs the same as before.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from demplan import COBB_DOUGLAS, LEONTIEF, Economy, Plan, run
from demplan.prefabs.hahnel import HahnelBook2021
from demplan.tools.leontief import input_requirements_flat
from demplan.tools.linearize import linearize

EXACT = 1e-9

N_COMMODITIES = 4
PRIVATE, INTERMEDIATE, NATURAL, LABOR = range(N_COMMODITIES)


def build_two_unit_economy(output_coefficient=(1.0, 1.0)) -> Economy:
    """Two Cobb-Douglas units, extra keys in each ``extra`` bag to watch them survive."""
    return Economy(
        period=7,
        commodity_id=np.arange(N_COMMODITIES, dtype=np.int64),
        endowment=np.array([0.0, 0.0, 8.0, 9.0]),
        unit_id=np.arange(2, dtype=np.int64),
        technology_kind=[COBB_DOUGLAS, COBB_DOUGLAS],
        technology_scale=np.array([2.5, 4.0]),
        input_offsets=np.array([0, 3, 5], dtype=np.int64),
        input_commodity=np.array([INTERMEDIATE, NATURAL, LABOR, NATURAL, LABOR], dtype=np.int64),
        input_coefficient=np.array([0.3, 0.2, 0.4, 0.5, 0.5]),
        output_offsets=np.array([0, 1, 2], dtype=np.int64),
        output_commodity=np.array([PRIVATE, INTERMEDIATE], dtype=np.int64),
        output_coefficient=np.array(output_coefficient, dtype=np.float64),
        consumer_id=np.arange(2, dtype=np.int64),
        commodity_extra={
            "tag": np.arange(N_COMMODITIES, dtype=np.int64),
            "name": ["bread", "flour", "land", "work"],
        },
        unit_extra={"effort_c": np.array([0.08, 0.09])},
        consumer_extra={"entitlement": np.array([100.0, 200.0])},
    )


def build_plan(economy: Economy, output: np.ndarray, input_use: np.ndarray) -> Plan:
    return Plan(
        output=np.asarray(output, dtype=np.float64),
        input_use=np.asarray(input_use, dtype=np.float64),
        consumption=np.zeros((economy.n_consumers, 0)),
        consumption_commodity=np.zeros(0, dtype=np.int64),
        shared_use=np.zeros(economy.n_commodities),
    )


class TestCoefficients:
    def test_each_coefficient_is_input_use_per_unit_of_output(self):
        economy = build_two_unit_economy()
        plan = build_plan(economy, [4.0, 10.0], [1.2, 0.8, 2.0, 5.0, 2.5])
        linearised = linearize(economy, plan)
        np.testing.assert_allclose(
            linearised.input_coefficient, [0.3, 0.2, 0.5, 0.5, 0.25], atol=EXACT
        )

    def test_the_technology_becomes_leontief_at_unit_scale(self):
        economy = build_two_unit_economy()
        plan = build_plan(economy, [4.0, 10.0], [1.2, 0.8, 2.0, 5.0, 2.5])
        linearised = linearize(economy, plan)
        assert list(linearised.technology_kind) == ["leontief", "leontief"]
        assert LEONTIEF == "leontief"
        np.testing.assert_array_equal(linearised.technology_scale, np.ones(2))

    def test_every_output_coefficient_becomes_one(self):
        """The coefficients read ``input_use / output``, so one run is one unit of output."""
        economy = build_two_unit_economy(output_coefficient=(2.0, 0.5))
        plan = build_plan(economy, [4.0, 10.0], [1.2, 0.8, 2.0, 5.0, 2.5])
        linearised = linearize(economy, plan)
        np.testing.assert_array_equal(linearised.output_coefficient, [1.0, 1.0])
        np.testing.assert_allclose(
            linearised.input_coefficient, [0.3, 0.2, 0.5, 0.5, 0.25], atol=EXACT
        )

    def test_an_idle_unit_gets_zero_coefficients(self):
        economy = build_two_unit_economy()
        plan = build_plan(economy, [0.0, 10.0], [0.0, 0.0, 0.0, 5.0, 2.5])
        linearised = linearize(economy, plan)
        np.testing.assert_allclose(linearised.input_coefficient[:3], np.zeros(3), atol=EXACT)
        np.testing.assert_allclose(linearised.input_coefficient[3:], [0.5, 0.25], atol=EXACT)

    def test_everything_but_the_technology_survives(self):
        economy = build_two_unit_economy()
        plan = build_plan(economy, [4.0, 10.0], [1.2, 0.8, 2.0, 5.0, 2.5])
        linearised = linearize(economy, plan)
        assert linearised.period == economy.period
        for column in (
            "commodity_id",
            "endowment",
            "unit_id",
            "input_offsets",
            "input_commodity",
            "output_offsets",
            "output_commodity",
            "consumer_id",
        ):
            np.testing.assert_array_equal(
                getattr(linearised, column), getattr(economy, column), err_msg=column
            )

    def test_the_extra_bags_survive(self):
        economy = build_two_unit_economy()
        plan = build_plan(economy, [4.0, 10.0], [1.2, 0.8, 2.0, 5.0, 2.5])
        linearised = linearize(economy, plan)
        for bag in ("commodity_extra", "unit_extra", "consumer_extra"):
            source, result = getattr(economy, bag), getattr(linearised, bag)
            assert set(result) == set(source)
            for key in source:
                np.testing.assert_array_equal(result[key], source[key], err_msg=f"{bag}[{key}]")

    def test_the_source_economy_is_left_alone(self):
        economy = build_two_unit_economy()
        plan = build_plan(economy, [4.0, 10.0], [1.2, 0.8, 2.0, 5.0, 2.5])
        before = np.array(economy.input_coefficient, copy=True)
        linearize(economy, plan)
        np.testing.assert_array_equal(economy.input_coefficient, before)
        assert list(economy.technology_kind) == [COBB_DOUGLAS, COBB_DOUGLAS]


class TestTheIdentityItGuarantees:
    def test_the_hand_built_plan_is_reproduced(self):
        economy = build_two_unit_economy()
        input_use = np.array([1.2, 0.8, 2.0, 5.0, 2.5])
        plan = build_plan(economy, [4.0, 10.0], input_use)
        linearised = linearize(economy, plan)
        np.testing.assert_allclose(
            input_requirements_flat(linearised, plan.output), input_use, atol=EXACT
        )

    def test_a_participatory_plan_is_reproduced(self, synthetic_economy):
        plan = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        linearised = linearize(synthetic_economy, plan)
        assert np.all(np.asarray(plan.output) > 0.0)
        np.testing.assert_allclose(
            input_requirements_flat(linearised, plan.output),
            np.asarray(plan.input_use),
            rtol=1e-12,
            atol=0.0,
        )

    def test_the_cobb_douglas_reading_of_the_same_numbers_is_different(self, synthetic_economy):
        """Without this the identity above would hold for any economy, tool or no tool."""
        plan = run(HahnelBook2021(), synthetic_economy, seed=0).plan
        as_leontief = input_requirements_flat(synthetic_economy, plan.output)
        assert not np.allclose(as_leontief, np.asarray(plan.input_use), rtol=1e-3)

    @given(
        st.lists(
            st.one_of(
                st.just(0.0),
                st.floats(
                    min_value=1e-3, max_value=50.0, allow_nan=False, allow_infinity=False
                ),
            ),
            min_size=2,
            max_size=2,
        ),
        st.lists(
            st.floats(min_value=0.0, max_value=20.0, allow_nan=False, allow_infinity=False),
            min_size=5,
            max_size=5,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_the_identity_holds_wherever_the_unit_produced_something(self, output, input_use):
        economy = build_two_unit_economy()
        plan = build_plan(economy, np.array(output), np.array(input_use))
        linearised = linearize(economy, plan)
        produced = np.repeat(np.asarray(output), np.diff(economy.input_offsets)) > 0.0
        requirements = input_requirements_flat(linearised, plan.output)
        np.testing.assert_allclose(
            requirements[produced], np.asarray(input_use)[produced], rtol=1e-12, atol=1e-12
        )
        np.testing.assert_array_equal(requirements[~produced], np.zeros(int((~produced).sum())))


class TestRefusedInputs:
    def test_a_plan_of_the_wrong_shape_is_refused(self):
        economy = build_two_unit_economy()
        plan = Plan(
            output=np.array([4.0]),
            input_use=np.array([1.2, 0.8, 2.0, 5.0, 2.5]),
            consumption=np.zeros((2, 0)),
            consumption_commodity=np.zeros(0, dtype=np.int64),
            shared_use=np.zeros(N_COMMODITIES),
        )
        with pytest.raises(ValueError):
            linearize(economy, plan)

    def test_a_negative_output_is_refused(self):
        economy = build_two_unit_economy()
        plan = build_plan(economy, [-4.0, 10.0], [1.2, 0.8, 2.0, 5.0, 2.5])
        with pytest.raises(ValueError, match="negative"):
            linearize(economy, plan)

    def test_a_ratio_too_large_for_a_coefficient_is_reported_against_its_unit(self):
        """Output far below its input use overflows the division; the message says whose.

        Without the check the overflow reaches the schema as a non-finite coefficient, and the
        error names a row of the flat input array rather than the unit that caused it.
        """
        economy = build_two_unit_economy()
        plan = build_plan(economy, [5e-320, 10.0], [1.0, 0.0, 0.0, 5.0, 2.5])
        with pytest.raises(ValueError, match="unit 0"):
            linearize(economy, plan)

    def test_a_unit_with_two_outputs_is_refused(self):
        """Unit 1 makes flour and, as a by-product, bread: input ratios per output are not
        defined for it, and the message says so rather than dividing by one of the two."""
        economy = dataclasses.replace(
            build_two_unit_economy(),
            output_offsets=np.array([0, 1, 3], dtype=np.int64),
            output_commodity=np.array([PRIVATE, INTERMEDIATE, PRIVATE], dtype=np.int64),
            output_coefficient=np.array([1.0, 1.0, 0.1]),
        )
        plan = build_plan(economy, [4.0, 10.0, 1.0], [1.2, 0.8, 2.0, 5.0, 2.5])
        with pytest.raises(ValueError) as refused:
            linearize(economy, plan)
        message = str(refused.value)
        assert "unit 1" in message
        assert "joint products are not supported by linearize yet" in message
