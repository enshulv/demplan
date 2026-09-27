"""The technology interface: what a unit's planned inputs can deliver, against what the plan says.

Every expected number below is worked out by hand from the definitions of the shipped pieces,
on one small economy whose units each exercise one case: a Leontief unit with a zero
coefficient, a two-output unit read with fixed ratios, a Cobb-Douglas unit, a Leontief unit
whose coefficients are all zero, units whose inputs are all zero, and two units whose label no
implementation answers to. The two-output unit sits second, so output entry and unit index
part ways from there on and a check that reads one entry per unit misfiles every later entry.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

import demplan
from demplan import (
    COBB_DOUGLAS,
    LEONTIEF,
    CobbDouglas,
    Economy,
    FixedRatios,
    InputSide,
    Leontief,
    OutputSide,
    Plan,
    SchemaError,
    SeparableTechnology,
    SingleOutput,
    Technology,
    TechnologyReport,
    technology_margins,
)

FIXED_RATIOS_LABEL = "leontief_fixed_ratios"
"""A label the library does not recognise, for the two-output unit read with fixed ratios."""

UNKNOWN_LABEL = "putty_clay"
"""A label nobody implements in these tests."""

# Commodities: 0, 1, 2 are produced; 3 and 4 are used as inputs.
N_COMMODITIES = 5

# One row per unit: (label, scale, ((input commodity, coefficient, planned use), ...),
# ((output commodity, coefficient, planned output), ...)).
UNITS = (
    # Unit 0. Leontief with a zero coefficient on commodity 4: activity min(6 / 2) = 3, the zero
    # coefficient left out; 3 * 1.5 = 4.5 deliverable against 4 planned.
    (LEONTIEF, 1.0, ((3, 2.0, 6.0), (4, 0.0, 0.0)), ((0, 1.5, 4.0),)),
    # Unit 1. Two outputs read with fixed ratios: activity 2 / 1 = 2, deliverable 2 * (2, 3)
    # = (4, 6) against (3, 7) planned.
    (FIXED_RATIOS_LABEL, 1.0, ((3, 1.0, 2.0),), ((1, 2.0, 3.0), (2, 3.0, 7.0))),
    # Unit 2. Cobb-Douglas: activity 2 * 4**0.5 * 9**0.5 = 12, 12 * 0.5 = 6 deliverable
    # against 7 planned.
    (COBB_DOUGLAS, 2.0, ((3, 0.5, 4.0), (4, 0.5, 9.0)), ((1, 0.5, 7.0),)),
    # Unit 3. Leontief whose only coefficient is zero: no input limits it, activity infinite.
    (LEONTIEF, 1.0, ((4, 0.0, 5.0),), ((2, 1.0, 1.0),)),
    # Unit 4. Leontief whose planned inputs are all zero: activity 0, nothing deliverable
    # against 2.5 planned.
    (LEONTIEF, 1.0, ((3, 1.0, 0.0), (4, 2.0, 0.0)), ((0, 1.0, 2.5),)),
    # Units 5 and 6. A label nobody implements; unit 5 has two output entries.
    (UNKNOWN_LABEL, 1.0, ((3, 1.0, 1.0),), ((0, 1.0, 1.0), (1, 1.0, 1.0))),
    (UNKNOWN_LABEL, 1.0, ((4, 1.0, 1.0),), ((2, 1.0, 1.0),)),
    # Unit 7. Cobb-Douglas whose planned input is zero: activity 3 * 0**0.5 = 0, nothing
    # deliverable against 2 planned.
    (COBB_DOUGLAS, 3.0, ((3, 0.5, 0.0),), ((2, 1.0, 2.0),)),
)

N_OUTPUTS = 10

MARGIN_WITH_FIXED_RATIOS = np.array(
    [0.5, 1.0, -1.0, -1.0, np.inf, -2.5, 0.0, 0.0, 0.0, -2.0], dtype=np.float64
)
"""Margin per output entry when the caller supplies fixed ratios for unit 1's label."""

COMPUTED_WITH_FIXED_RATIOS = np.array(
    [True, True, True, True, True, True, False, False, False, True]
)
"""Entries 6 to 8 belong to units 5 and 6, whose label no implementation answers to."""


def build_economy(units=UNITS) -> Economy:
    """The economy of ``units``, laid out in the flat arrays the data model uses."""
    input_counts = [len(inputs) for _, _, inputs, _ in units]
    output_counts = [len(outputs) for _, _, _, outputs in units]
    input_offsets = np.zeros(len(units) + 1, dtype=np.int64)
    output_offsets = np.zeros(len(units) + 1, dtype=np.int64)
    np.cumsum(input_counts, out=input_offsets[1:])
    np.cumsum(output_counts, out=output_offsets[1:])
    return Economy(
        period=0,
        commodity_id=np.arange(N_COMMODITIES, dtype=np.int64),
        endowment=np.zeros(N_COMMODITIES, dtype=np.float64),
        unit_id=np.arange(len(units), dtype=np.int64),
        technology_kind=[label for label, _, _, _ in units],
        technology_scale=np.array([scale for _, scale, _, _ in units], dtype=np.float64),
        input_offsets=input_offsets,
        input_commodity=np.array(
            [entry[0] for _, _, inputs, _ in units for entry in inputs], dtype=np.int64
        ),
        input_coefficient=np.array(
            [entry[1] for _, _, inputs, _ in units for entry in inputs], dtype=np.float64
        ),
        output_offsets=output_offsets,
        output_commodity=np.array(
            [entry[0] for _, _, _, outputs in units for entry in outputs], dtype=np.int64
        ),
        output_coefficient=np.array(
            [entry[1] for _, _, _, outputs in units for entry in outputs], dtype=np.float64
        ),
        consumer_id=np.arange(1, dtype=np.int64),
    )


def build_plan(units=UNITS) -> Plan:
    """The planned input use and output of ``units``, with no consumption side."""
    return Plan(
        output=np.array(
            [entry[2] for _, _, _, outputs in units for entry in outputs], dtype=np.float64
        ),
        input_use=np.array(
            [entry[2] for _, _, inputs, _ in units for entry in inputs], dtype=np.float64
        ),
        consumption=None,
        consumption_commodity=None,
        shared_use=None,
    )


def relabelled(units, unit: int, label: str):
    """``units`` with unit ``unit`` carrying ``label``."""
    rows = list(units)
    _, scale, inputs, outputs = rows[unit]
    rows[unit] = (label, scale, inputs, outputs)
    return tuple(rows)


def fixed_ratios_technology() -> SeparableTechnology:
    return SeparableTechnology(FIXED_RATIOS_LABEL, Leontief(), FixedRatios())


class ConstantMargin:
    """A technology that reports the same margin on every output entry of every unit."""

    def __init__(self, label: str, value: float):
        self.label = label
        self.value = value

    def margin(self, economy: Economy, plan: Plan, unit: int) -> np.ndarray:
        entries = int(economy.output_offsets[unit + 1] - economy.output_offsets[unit])
        return np.full(entries, self.value, dtype=np.float64)


@pytest.fixture
def economy() -> Economy:
    return build_economy()


@pytest.fixture
def plan() -> Plan:
    return build_plan()


class TestLeontiefInputSide:
    def test_activity_is_the_binding_ratio_with_the_zero_coefficient_left_out(self, economy, plan):
        assert Leontief().activity(economy, plan, 0) == 3.0

    def test_a_unit_whose_coefficients_are_all_zero_has_infinite_activity(self, economy, plan):
        assert Leontief().activity(economy, plan, 3) == np.inf

    def test_a_unit_whose_inputs_are_all_zero_has_no_activity(self, economy, plan):
        assert Leontief().activity(economy, plan, 4) == 0.0

    def test_the_smallest_ratio_binds(self):
        units = ((LEONTIEF, 1.0, ((3, 2.0, 10.0), (4, 4.0, 12.0)), ((0, 1.0, 1.0),)),)
        assert Leontief().activity(build_economy(units), build_plan(units), 0) == 3.0

    def test_a_negative_coefficient_is_not_among_the_limiting_inputs(self):
        units = ((LEONTIEF, 1.0, ((3, 2.0, 6.0), (4, -1.0, 1.0)), ((0, 1.0, 1.0),)),)
        assert Leontief().activity(build_economy(units), build_plan(units), 0) == 3.0

    def test_activity_is_a_python_float(self, economy, plan):
        assert type(Leontief().activity(economy, plan, 0)) is float


class TestCobbDouglasInputSide:
    def test_activity_is_the_scale_times_the_product_of_powers(self, economy, plan):
        assert CobbDouglas().activity(economy, plan, 2) == 12.0

    def test_a_unit_whose_inputs_are_all_zero_has_no_activity(self, economy, plan):
        assert CobbDouglas().activity(economy, plan, 7) == 0.0

    def test_the_scale_multiplies(self):
        units = ((COBB_DOUGLAS, 5.0, ((3, 1.0, 2.0),), ((0, 1.0, 1.0),)),)
        assert CobbDouglas().activity(build_economy(units), build_plan(units), 0) == 10.0

    def test_activity_is_a_python_float(self, economy, plan):
        assert type(CobbDouglas().activity(economy, plan, 2)) is float


class TestSingleOutput:
    def test_deliverable_is_activity_times_the_output_coefficient(self, economy):
        np.testing.assert_array_equal(SingleOutput().deliverable(economy, 0, 3.0), [4.5])

    def test_a_unit_with_two_output_entries_is_refused_by_number(self, economy):
        with pytest.raises(ValueError, match=r"unit 1\b"):
            SingleOutput().deliverable(economy, 1, 2.0)

    def test_the_refusal_names_the_unit_it_was_asked_about(self, economy):
        with pytest.raises(ValueError, match=r"unit 5\b"):
            SingleOutput().deliverable(economy, 5, 1.0)

    def test_deliverable_reads_the_unit_s_own_entry_after_a_joint_unit(self, economy):
        """Unit 2 owns entry 3, not entry 2."""
        np.testing.assert_array_equal(SingleOutput().deliverable(economy, 2, 12.0), [6.0])


class TestFixedRatios:
    def test_every_output_entry_is_activity_times_its_coefficient(self, economy):
        np.testing.assert_array_equal(FixedRatios().deliverable(economy, 1, 2.0), [4.0, 6.0])

    def test_a_single_output_unit_is_read_the_same_way(self, economy):
        np.testing.assert_array_equal(FixedRatios().deliverable(economy, 0, 3.0), [4.5])


class RecordingInputSide:
    """An input side that records what it is asked and answers a fixed activity."""

    def __init__(self, activity: float):
        self.answer = activity
        self.calls: list = []

    def activity(self, economy, plan, unit):
        self.calls.append((economy, plan, unit))
        return self.answer


class RecordingOutputSide:
    """An output side that records what it is asked and delivers ``activity`` per entry."""

    def __init__(self):
        self.calls: list = []

    def deliverable(self, economy, unit, activity):
        self.calls.append((economy, unit, activity))
        entries = int(economy.output_offsets[unit + 1] - economy.output_offsets[unit])
        return np.full(entries, activity, dtype=np.float64)


class TestSeparableTechnology:
    def test_it_carries_its_label(self):
        assert SeparableTechnology("my_label", Leontief(), SingleOutput()).label == "my_label"

    def test_margin_is_deliverable_minus_the_planned_output(self, economy, plan):
        technology = SeparableTechnology(LEONTIEF, Leontief(), SingleOutput())
        np.testing.assert_array_equal(technology.margin(economy, plan, 0), [0.5])

    def test_fixed_ratios_margins_on_a_two_output_unit(self, economy, plan):
        np.testing.assert_array_equal(
            fixed_ratios_technology().margin(economy, plan, 1), [1.0, -1.0]
        )

    def test_the_input_side_s_activity_is_what_the_output_side_receives(self, economy, plan):
        inputs = RecordingInputSide(10.0)
        outputs = RecordingOutputSide()
        margin = SeparableTechnology("recorded", inputs, outputs).margin(economy, plan, 1)
        assert len(inputs.calls) == 1
        asked_economy, asked_plan, asked_unit = inputs.calls[0]
        assert asked_economy is economy and asked_plan is plan and asked_unit == 1
        assert len(outputs.calls) == 1
        asked_economy, asked_unit, asked_activity = outputs.calls[0]
        assert asked_economy is economy and asked_unit == 1 and asked_activity == 10.0
        # Unit 1 plans (3, 7).
        np.testing.assert_array_equal(margin, [7.0, 3.0])

    def test_the_unit_s_own_planned_output_is_subtracted_after_a_joint_unit(self, economy, plan):
        """Unit 2's planned output is entry 3, 7.0."""
        technology = SeparableTechnology("recorded", RecordingInputSide(0.0), RecordingOutputSide())
        np.testing.assert_array_equal(technology.margin(economy, plan, 2), [-7.0])

    def test_the_shipped_pieces_satisfy_the_protocols(self):
        assert isinstance(SeparableTechnology("x", Leontief(), SingleOutput()), Technology)
        assert isinstance(Leontief(), InputSide)
        assert isinstance(CobbDouglas(), InputSide)
        assert isinstance(SingleOutput(), OutputSide)
        assert isinstance(FixedRatios(), OutputSide)


class TestTechnologyMargins:
    def test_hand_worked_margins_with_fixed_ratios_supplied(self, economy, plan):
        report = technology_margins(
            economy, plan, {FIXED_RATIOS_LABEL: fixed_ratios_technology()}
        )
        np.testing.assert_array_equal(report.margin, MARGIN_WITH_FIXED_RATIOS)
        np.testing.assert_array_equal(report.computed, COMPUTED_WITH_FIXED_RATIOS)
        assert report.missing == {UNKNOWN_LABEL: 2}

    def test_without_supplied_technologies_only_the_library_labels_are_computed(
        self, economy, plan
    ):
        report = technology_margins(economy, plan)
        expected_computed = COMPUTED_WITH_FIXED_RATIOS.copy()
        expected_computed[[1, 2]] = False
        expected_margin = np.where(expected_computed, MARGIN_WITH_FIXED_RATIOS, 0.0)
        np.testing.assert_array_equal(report.computed, expected_computed)
        np.testing.assert_array_equal(report.margin, expected_margin)
        assert report.missing == {FIXED_RATIOS_LABEL: 1, UNKNOWN_LABEL: 2}

    def test_an_empty_mapping_is_the_same_as_none(self, economy, plan):
        report = technology_margins(economy, plan, {})
        assert report.missing == {FIXED_RATIOS_LABEL: 1, UNKNOWN_LABEL: 2}

    def test_missing_counts_units_not_output_entries(self, economy, plan):
        """Unit 5 has two output entries and unit 6 one: two units, three entries."""
        report = technology_margins(economy, plan)
        assert report.missing[UNKNOWN_LABEL] == 2

    def test_nothing_missing_is_an_empty_mapping(self):
        units = UNITS[:1] + UNITS[2:5]
        report = technology_margins(build_economy(units), build_plan(units))
        assert report.missing == {}
        assert report.computed.all()

    def test_a_caller_supplied_technology_overrides_a_library_label(self, economy, plan):
        report = technology_margins(economy, plan, {LEONTIEF: ConstantMargin(LEONTIEF, 42.0)})
        # Entries 0, 4 and 5 belong to the Leontief units 0, 3 and 4.
        np.testing.assert_array_equal(report.margin[[0, 4, 5]], [42.0, 42.0, 42.0])
        # The Cobb-Douglas units keep the library's reading.
        np.testing.assert_array_equal(report.margin[[3, 9]], [-1.0, -2.0])

    def test_an_override_does_not_outlive_the_call(self, economy, plan):
        technology_margins(economy, plan, {LEONTIEF: ConstantMargin(LEONTIEF, 42.0)})
        report = technology_margins(economy, plan)
        assert report.margin[0] == 0.5

    def test_a_supplied_technology_can_answer_an_unknown_label(self, economy, plan):
        supplied = {UNKNOWN_LABEL: ConstantMargin(UNKNOWN_LABEL, 9.0)}
        report = technology_margins(economy, plan, supplied)
        np.testing.assert_array_equal(report.margin[6:9], [9.0, 9.0, 9.0])
        assert report.computed[6:9].all()
        assert UNKNOWN_LABEL not in report.missing

    def test_fixed_ratios_is_not_attached_to_a_two_output_leontief_unit(self):
        """Unit 1 relabelled Leontief fails through SingleOutput, naming the unit."""
        units = relabelled(UNITS, 1, LEONTIEF)
        with pytest.raises(ValueError, match=r"unit 1\b"):
            technology_margins(build_economy(units), build_plan(units))

    def test_fixed_ratios_is_not_attached_to_a_two_output_cobb_douglas_unit(self):
        units = relabelled(UNITS, 1, COBB_DOUGLAS)
        with pytest.raises(ValueError, match=r"unit 1\b"):
            technology_margins(build_economy(units), build_plan(units))

    def test_a_plan_shaped_for_another_economy_is_refused(self, economy):
        plan = build_plan(UNITS[:4])
        with pytest.raises(SchemaError):
            technology_margins(economy, plan)

    def test_a_technology_answering_the_wrong_number_of_entries_is_refused(self, economy, plan):
        class OneNumber:
            label = FIXED_RATIOS_LABEL

            def margin(self, economy, plan, unit):
                return np.zeros(1, dtype=np.float64)

        with pytest.raises(ValueError, match=r"unit 1\b") as refused:
            technology_margins(economy, plan, {FIXED_RATIOS_LABEL: OneNumber()})
        assert FIXED_RATIOS_LABEL in str(refused.value)


class TestTechnologyReport:
    @pytest.fixture
    def report(self, economy, plan) -> TechnologyReport:
        return technology_margins(economy, plan, {FIXED_RATIOS_LABEL: fixed_ratios_technology()})

    def test_it_is_a_frozen_dataclass(self, report):
        assert dataclasses.is_dataclass(report)
        with pytest.raises(dataclasses.FrozenInstanceError):
            report.margin = np.zeros(N_OUTPUTS)

    def test_the_arrays_are_read_only(self, report):
        with pytest.raises(ValueError):
            report.margin[0] = 1.0
        with pytest.raises(ValueError):
            report.computed[6] = True

    def test_shapes_and_dtypes(self, report):
        assert report.margin.shape == (N_OUTPUTS,)
        assert report.margin.dtype == np.float64
        assert report.computed.shape == (N_OUTPUTS,)
        assert report.computed.dtype == np.bool_

    def test_missing_is_a_dict_of_label_to_unit_count(self, report):
        assert isinstance(report.missing, dict)
        assert all(type(label) is str for label in report.missing)


class TestExports:
    NAMES = (
        "CobbDouglas",
        "FixedRatios",
        "InputSide",
        "Leontief",
        "OutputSide",
        "SeparableTechnology",
        "SingleOutput",
        "Technology",
        "TechnologyReport",
        "technology_margins",
    )

    def test_every_name_is_exported_from_the_package(self):
        for name in self.NAMES:
            assert name in demplan.__all__
            assert hasattr(demplan, name)
