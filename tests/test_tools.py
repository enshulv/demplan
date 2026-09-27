"""Theory-neutral technology tools.

The closed forms are checked against their defining conditions rather than against a second
copy of the same algebra: a Cobb-Douglas input bundle is fed back through the production
function, and the first-order condition is read off the result.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from demplan import (
    COBB_DOUGLAS,
    LEONTIEF,
    CobbDouglas,
    Economy,
    Leontief,
    Plan,
    SeparableTechnology,
    SingleOutput,
)
from demplan.tools import cobb_douglas, leontief
from reference import synthetic

RELATIVE_TOLERANCE = 1e-9

exponent = st.floats(min_value=0.2, max_value=1.0, allow_nan=False, allow_infinity=False)
price = st.floats(min_value=0.5, max_value=200.0, allow_nan=False, allow_infinity=False)
quantity = st.floats(min_value=0.5, max_value=100.0, allow_nan=False, allow_infinity=False)
scale = st.floats(min_value=0.5, max_value=10.0, allow_nan=False, allow_infinity=False)


@st.composite
def technology(draw):
    width = draw(st.integers(min_value=1, max_value=8))
    exponents = np.array(draw(st.lists(exponent, min_size=width, max_size=width)))
    prices = np.array(draw(st.lists(price, min_size=width, max_size=width)))
    return exponents, draw(scale), draw(quantity), prices


class TestCobbDouglasClosedForm:
    def test_symmetric_case(self):
        inputs = cobb_douglas.cost_minimizing_inputs(
            np.array([0.5, 0.5]), 1.0, 10.0, np.array([1.0, 1.0])
        )
        np.testing.assert_allclose(inputs, [10.0, 10.0], rtol=RELATIVE_TOLERANCE)

    def test_the_dearer_input_is_used_less(self):
        inputs = cobb_douglas.cost_minimizing_inputs(
            np.array([0.5, 0.5]), 1.0, 10.0, np.array([1.0, 4.0])
        )
        np.testing.assert_allclose(inputs, [20.0, 5.0], rtol=RELATIVE_TOLERANCE)

    @given(technology())
    @settings(max_examples=200, deadline=None)
    def test_the_bundle_produces_the_requested_output(self, spec):
        exponents, scale_value, output, prices = spec
        inputs = cobb_douglas.cost_minimizing_inputs(exponents, scale_value, output, prices)
        produced = scale_value * np.exp(float((exponents * np.log(inputs)).sum()))
        assert produced == pytest.approx(output, rel=RELATIVE_TOLERANCE)

    @given(technology())
    @settings(max_examples=200, deadline=None)
    def test_first_order_condition(self, spec):
        exponents, scale_value, output, prices = spec
        inputs = cobb_douglas.cost_minimizing_inputs(exponents, scale_value, output, prices)
        ratios = prices * inputs / exponents
        assert ratios.max() == pytest.approx(ratios.min(), rel=RELATIVE_TOLERANCE)

    @given(technology())
    @settings(max_examples=100, deadline=None)
    def test_inputs_are_positive(self, spec):
        exponents, scale_value, output, prices = spec
        inputs = cobb_douglas.cost_minimizing_inputs(exponents, scale_value, output, prices)
        assert np.all(np.isfinite(inputs))
        assert np.all(inputs > 0.0)


class TestCobbDouglasFlat:
    @given(st.data())
    @settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_flat_matches_the_per_unit_form(self, synthetic_economy, data):
        economy = synthetic_economy
        output = np.array(
            data.draw(st.lists(quantity, min_size=economy.n_units, max_size=economy.n_units))
        )
        prices = np.array(
            data.draw(
                st.lists(price, min_size=economy.n_commodities, max_size=economy.n_commodities)
            )
        )
        flat = cobb_douglas.cost_minimizing_inputs_flat(economy, output, prices)
        assert flat.shape == (economy.n_inputs,)
        for unit in range(economy.n_units):
            window = economy.inputs_of(unit)
            one = cobb_douglas.cost_minimizing_inputs(
                np.asarray(economy.input_coefficient[window]),
                float(economy.technology_scale[unit]),
                float(output[unit]),
                prices[np.asarray(economy.input_commodity[window])],
            )
            np.testing.assert_allclose(flat[window], one, rtol=1e-12)

    def test_each_unit_reproduces_its_own_output(self, synthetic_economy):
        economy = synthetic_economy
        output = np.linspace(1.0, 9.0, economy.n_units)
        prices = np.linspace(10.0, 24.0, economy.n_commodities)
        flat = cobb_douglas.cost_minimizing_inputs_flat(economy, output, prices)
        for unit in range(economy.n_units):
            window = economy.inputs_of(unit)
            exponents = np.asarray(economy.input_coefficient[window])
            produced = float(economy.technology_scale[unit]) * np.exp(
                float((exponents * np.log(flat[window])).sum())
            )
            assert produced == pytest.approx(output[unit], rel=RELATIVE_TOLERANCE)


class TestLeontief:
    def test_requirements_scale_with_output(self):
        np.testing.assert_allclose(
            leontief.input_requirements(np.array([2.0, 3.0]), 5.0), [10.0, 15.0]
        )

    @given(technology())
    @settings(max_examples=200, deadline=None)
    def test_the_binding_ratio_returns_the_output(self, spec):
        coefficients, _, output, _ = spec
        inputs = leontief.input_requirements(coefficients, output)
        ratios = inputs / coefficients
        assert ratios.min() == pytest.approx(output, rel=RELATIVE_TOLERANCE)
        assert ratios.max() == pytest.approx(output, rel=RELATIVE_TOLERANCE)

    def test_zero_output_needs_nothing(self):
        np.testing.assert_array_equal(
            leontief.input_requirements(np.array([2.0, 3.0]), 0.0), [0.0, 0.0]
        )

    def test_flat_matches_the_per_unit_form(self, synthetic_economy):
        economy = synthetic_economy
        output = np.linspace(0.5, 12.0, economy.n_units)
        flat = leontief.input_requirements_flat(economy, output)
        assert flat.shape == (economy.n_inputs,)
        for unit in range(economy.n_units):
            window = economy.inputs_of(unit)
            one = leontief.input_requirements(
                np.asarray(economy.input_coefficient[window]), float(output[unit])
            )
            np.testing.assert_array_equal(flat[window], one)


class TestJointProductsAreRefused:
    """Both flat forms take one output quantity per unit, which a joint product does not have."""

    def test_leontief_requirements_refuse_a_unit_with_two_outputs(self):
        economy = synthetic.build_joint_product_economy()
        with pytest.raises(ValueError) as refused:
            leontief.input_requirements_flat(economy, np.ones(economy.n_units))
        message = str(refused.value)
        assert "unit 0" in message
        assert "joint products are not supported by input_requirements_flat yet" in message

    def test_cobb_douglas_bundles_refuse_a_unit_with_two_outputs(self):
        economy = synthetic.build_joint_product_economy()
        with pytest.raises(ValueError) as refused:
            cobb_douglas.cost_minimizing_inputs_flat(
                economy, np.ones(economy.n_units), np.ones(economy.n_commodities)
            )
        message = str(refused.value)
        assert "unit 0" in message
        assert "joint products are not supported by cost_minimizing_inputs_flat yet" in message

    def test_the_refusal_names_the_first_joint_unit_whichever_it_is(self, synthetic_economy):
        """Only unit 4 lists two outputs here."""
        economy = dataclasses.replace(
            synthetic_economy,
            output_offsets=np.array([0, 1, 2, 3, 4, 6, 7, 8, 9, 10], dtype=np.int64),
            output_commodity=np.array([0, 1, 2, 3, 4, 8, 5, 6, 7, 8], dtype=np.int64),
            output_coefficient=np.ones(10),
        )
        with pytest.raises(ValueError, match=r"unit 4\b"):
            leontief.input_requirements_flat(economy, np.ones(economy.n_units))


def _one_unit_economy(coefficients, output_coefficient: float, scale: float = 1.0):
    """One unit using commodities 1, 2, ... with ``coefficients`` and making commodity 0."""
    n_inputs = len(coefficients)
    return Economy(
        period=0,
        commodity_id=np.arange(n_inputs + 1, dtype=np.int64),
        endowment=np.zeros(n_inputs + 1, dtype=np.float64),
        unit_id=np.zeros(1, dtype=np.int64),
        technology_kind=[LEONTIEF],
        technology_scale=np.array([scale], dtype=np.float64),
        input_offsets=np.array([0, n_inputs], dtype=np.int64),
        input_commodity=np.arange(1, n_inputs + 1, dtype=np.int64),
        input_coefficient=np.array(coefficients, dtype=np.float64),
        output_offsets=np.array([0, 1], dtype=np.int64),
        output_commodity=np.zeros(1, dtype=np.int64),
        output_coefficient=np.array([output_coefficient], dtype=np.float64),
        consumer_id=np.zeros(0, dtype=np.int64),
    )


OUTPUT_COEFFICIENTS = (0.5, 2.0, 1.5, 4.0, 0.25, 1.0, 3.0, 0.8, 1.25)
"""One output coefficient per unit of the synthetic economy, none of them 1 but one."""


def _plan_of(economy, output, input_use) -> Plan:
    return Plan(
        output=np.asarray(output, dtype=np.float64),
        input_use=np.asarray(input_use, dtype=np.float64),
        consumption=None,
        consumption_commodity=None,
        shared_use=None,
    )


class TestTheOutputCoefficientIsOutputPerRun:
    """Both flat forms read ``output`` as a quantity of the unit's output, which is
    ``output_coefficient`` per unit of activity, as the technology interface and the reference
    solution read it."""

    def test_leontief_requirements_by_hand(self):
        """Output 10 at 2 per run is 5 runs, needing 5 * (2, 3)."""
        economy = _one_unit_economy([2.0, 3.0], output_coefficient=2.0)
        np.testing.assert_allclose(
            leontief.input_requirements_flat(economy, np.array([10.0])),
            [10.0, 15.0],
            rtol=RELATIVE_TOLERANCE,
        )

    def test_cobb_douglas_bundle_by_hand(self):
        """Output 12 at 4 per run is 3 runs; with exponents (1, 1) at equal prices and scale 1
        the bundle is (3**0.5, 3**0.5)."""
        economy = _one_unit_economy([1.0, 1.0], output_coefficient=4.0)
        bundle = cobb_douglas.cost_minimizing_inputs_flat(
            economy, np.array([12.0]), np.ones(3, dtype=np.float64)
        )
        np.testing.assert_allclose(bundle, [3.0**0.5, 3.0**0.5], rtol=RELATIVE_TOLERANCE)

    def test_leontief_requirements_agree_with_the_leontief_technology(self, synthetic_economy):
        economy = dataclasses.replace(
            synthetic_economy, output_coefficient=np.array(OUTPUT_COEFFICIENTS)
        )
        output = np.linspace(1.0, 9.0, economy.n_units)
        plan = _plan_of(economy, output, leontief.input_requirements_flat(economy, output))
        technology = SeparableTechnology(LEONTIEF, Leontief(), SingleOutput())
        for unit in range(economy.n_units):
            margin = technology.margin(economy, plan, unit)
            assert margin[0] == pytest.approx(0.0, abs=RELATIVE_TOLERANCE * output[unit])

    def test_cobb_douglas_bundles_agree_with_the_cobb_douglas_technology(self, synthetic_economy):
        economy = dataclasses.replace(
            synthetic_economy, output_coefficient=np.array(OUTPUT_COEFFICIENTS)
        )
        output = np.linspace(1.0, 9.0, economy.n_units)
        prices = np.linspace(10.0, 24.0, economy.n_commodities)
        plan = _plan_of(
            economy, output, cobb_douglas.cost_minimizing_inputs_flat(economy, output, prices)
        )
        technology = SeparableTechnology(COBB_DOUGLAS, CobbDouglas(), SingleOutput())
        for unit in range(economy.n_units):
            margin = technology.margin(economy, plan, unit)
            assert margin[0] == pytest.approx(0.0, abs=RELATIVE_TOLERANCE * output[unit])
