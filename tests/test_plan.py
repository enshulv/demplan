"""Structural contract of :class:`Plan` and its derived accessors.

The expected aggregates are recomputed here with plain Python loops rather than with the
same numpy calls the library uses, so that a wrong aggregation column in the library shows up
as a failure instead of cancelling out.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect

import numpy as np
import pytest

import cyberstride.plan
from cyberstride.plan import (
    AllocatedPlan,
    PlanFieldAbsent,
    StatedPlan,
    require_comparable,
)
from cyberstride import (
    CONSUMER_DEMAND,
    EFFORT,
    INCOME,
    INDICATIVE_PRICE,
    LABOR_VALUE,
    SHADOW_PRICE,
    CommodityKind,
    Plan,
    SchemaError,
)


CONSUMPTION_COMMODITY = (2, 0, 1)
"""Commodity each column of the ``plan`` fixture's consumption block stands for.

The three private goods of ``synthetic_economy``, in an order that is not the column order.
Under the identity mapping ``(0, 1, 2)`` an implementation that dropped the mapping and filed
column ``j`` under commodity ``j`` produces the same totals, so the aggregation tests here
would pass on code that never reads the mapping.
"""

REQUIRED_FIELDS = ("output", "input_use")
"""The fixed fields no mechanism may declare absent."""


@pytest.fixture
def plan(synthetic_economy):
    economy = synthetic_economy
    return Plan(
        output=np.arange(1, economy.n_units + 1, dtype=np.float64),
        input_use=np.arange(1, economy.n_inputs + 1, dtype=np.float64),
        consumption=np.array(
            [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0], [10.0, 11.0, 12.0]]
        ),
        consumption_commodity=np.array(CONSUMPTION_COMMODITY, dtype=np.int64),
        provision=np.array([0.0] * 3 + [11.0, 12.0, 13.0] + [0.0] * 9),
        valuation={INDICATIVE_PRICE: np.full(economy.n_commodities, 700.0)},
    )


def expected_scatter(indices, weights, size) -> np.ndarray:
    totals = [0.0] * size
    for index, weight in zip(indices, weights):
        totals[int(index)] += float(weight)
    return np.array(totals)


def expected_column_sums(block) -> list[float]:
    """Column totals of a consumption block, added with a plain loop."""
    return [sum(float(row[column]) for row in block) for column in range(len(block[0]))]


class TestValuationKeys:
    def test_predefined_keys(self):
        assert INDICATIVE_PRICE == "indicative_price"
        assert LABOR_VALUE == "labor_value"
        assert SHADOW_PRICE == "shadow_price"
        assert INCOME == "income"


class TestExtraKeys:
    """The two ``extra`` keys :class:`Plan` documents, addressed by constant."""

    def test_predefined_keys(self):
        assert EFFORT == "effort"
        assert CONSUMER_DEMAND == "consumer_demand"

    def test_the_package_re_exports_the_names_the_plan_module_defines(self):
        assert EFFORT is cyberstride.plan.EFFORT
        assert CONSUMER_DEMAND is cyberstride.plan.CONSUMER_DEMAND

    def test_a_bag_written_under_the_constants_reads_back_under_them(
        self, plan, synthetic_economy
    ):
        carried = dataclasses.replace(
            plan,
            extra={
                EFFORT: np.ones(synthetic_economy.n_units),
                CONSUMER_DEMAND: np.ones(synthetic_economy.n_commodities),
            },
        )
        carried.validate(synthetic_economy)
        assert sorted(carried.extra) == sorted([EFFORT, CONSUMER_DEMAND])


class TestImmutability:
    def test_fields_cannot_be_rebound(self, plan):
        with pytest.raises(dataclasses.FrozenInstanceError):
            plan.output = np.zeros(1)

    @pytest.mark.parametrize(
        "field", ["output", "input_use", "consumption", "consumption_commodity", "provision"]
    )
    def test_arrays_are_read_only(self, plan, field):
        array = getattr(plan, field)
        assert array.flags.writeable is False

    def test_construction_leaves_the_callers_arrays_writeable(self, synthetic_economy):
        """Freezing is the plan's own promise, not a side effect on the caller's buffer."""
        output = np.ones(synthetic_economy.n_units)
        price = np.full(synthetic_economy.n_commodities, 700.0)
        Plan(
            output=output,
            input_use=np.ones(synthetic_economy.n_inputs),
            consumption=np.ones((synthetic_economy.n_consumers, 0)),
            consumption_commodity=np.zeros(0, dtype=np.int64),
            provision=np.zeros(synthetic_economy.n_commodities),
            valuation={INDICATIVE_PRICE: price},
        )
        assert output.flags.writeable is True
        assert price.flags.writeable is True

    def test_valuation_is_a_read_only_mapping(self, plan):
        with pytest.raises(TypeError):
            plan.valuation["injected"] = np.zeros(1)
        assert plan.valuation[INDICATIVE_PRICE].flags.writeable is False

    def test_valuation_defaults_to_empty(self, synthetic_economy):
        bare = Plan(
            output=np.zeros(synthetic_economy.n_units),
            input_use=np.zeros(synthetic_economy.n_inputs),
            consumption=np.zeros((synthetic_economy.n_consumers, 0)),
            consumption_commodity=np.zeros(0, dtype=np.int64),
            provision=np.zeros(synthetic_economy.n_commodities),
        )
        assert dict(bare.valuation) == {}


class TestValidate:
    def test_a_well_formed_plan_passes(self, plan, synthetic_economy):
        plan.validate(synthetic_economy)

    def test_output_length(self, plan, synthetic_economy):
        broken = dataclasses.replace(plan, output=plan.output[:-1])
        with pytest.raises(SchemaError, match="output"):
            broken.validate(synthetic_economy)

    def test_input_use_length(self, plan, synthetic_economy):
        broken = dataclasses.replace(plan, input_use=plan.input_use[:-1])
        with pytest.raises(SchemaError, match="input_use"):
            broken.validate(synthetic_economy)

    def test_provision_length(self, plan, synthetic_economy):
        broken = dataclasses.replace(plan, provision=plan.provision[:-1])
        with pytest.raises(SchemaError, match="provision"):
            broken.validate(synthetic_economy)

    def test_consumption_row_count(self, plan, synthetic_economy):
        broken = dataclasses.replace(plan, consumption=plan.consumption[:-1])
        with pytest.raises(SchemaError, match="consumption"):
            broken.validate(synthetic_economy)

    def test_consumption_column_count_must_match_the_mapping(self, plan, synthetic_economy):
        broken = dataclasses.replace(plan, consumption=plan.consumption[:, :-1])
        with pytest.raises(SchemaError, match="consumption"):
            broken.validate(synthetic_economy)

    @pytest.mark.parametrize("bad", [-1, 15])
    def test_consumption_commodity_range(self, plan, synthetic_economy, bad):
        columns = plan.consumption_commodity.copy()
        columns[1] = bad
        broken = dataclasses.replace(plan, consumption_commodity=columns)
        with pytest.raises(SchemaError, match="consumption_commodity"):
            broken.validate(synthetic_economy)

    @pytest.mark.parametrize("field", ["output", "input_use", "consumption", "provision"])
    @pytest.mark.parametrize("bad", [np.nan, np.inf])
    def test_physical_layer_must_be_finite(self, plan, synthetic_economy, field, bad):
        array = getattr(plan, field).copy()
        array.reshape(-1)[0] = bad
        broken = dataclasses.replace(plan, **{field: array})
        with pytest.raises(SchemaError, match=field):
            broken.validate(synthetic_economy)

    def test_consumption_must_be_two_dimensional(self, plan, synthetic_economy):
        broken = dataclasses.replace(plan, consumption=plan.consumption.reshape(-1))
        with pytest.raises(SchemaError, match="consumption"):
            broken.validate(synthetic_economy)


class TestExtraBag:
    """``extra`` carries physical quantities the fixed fields have no column for."""

    def test_it_defaults_to_empty(self, plan):
        assert dict(plan.extra) == {}

    def test_it_is_a_read_only_mapping(self, plan, synthetic_economy):
        carried = dataclasses.replace(
            plan, extra={"effort": np.ones(synthetic_economy.n_units)}
        )
        with pytest.raises(TypeError):
            carried.extra["injected"] = np.zeros(1)
        assert carried.extra["effort"].flags.writeable is False

    @pytest.mark.parametrize("rows", ["n_units", "n_consumers", "n_commodities"])
    def test_each_of_the_three_row_counts_is_accepted(self, plan, synthetic_economy, rows):
        length = getattr(synthetic_economy, rows)
        carried = dataclasses.replace(plan, extra={"whatever": np.ones(length)})
        carried.validate(synthetic_economy)

    def test_a_leading_dimension_matching_none_of_the_three_is_rejected(
        self, plan, synthetic_economy
    ):
        odd = 1 + max(
            synthetic_economy.n_units,
            synthetic_economy.n_consumers,
            synthetic_economy.n_commodities,
        )
        carried = dataclasses.replace(plan, extra={"effort": np.ones(odd)})
        with pytest.raises(SchemaError, match=r"Plan\.extra\['effort'\]"):
            carried.validate(synthetic_economy)

    @pytest.mark.parametrize("bad", [np.nan, np.inf])
    def test_a_non_finite_entry_is_rejected(self, plan, synthetic_economy, bad):
        values = np.ones(synthetic_economy.n_units)
        values[0] = bad
        carried = dataclasses.replace(plan, extra={"effort": values})
        with pytest.raises(SchemaError, match=r"Plan\.extra\['effort'\]"):
            carried.validate(synthetic_economy)

    def test_a_non_array_value_is_rejected(self, plan, synthetic_economy):
        carried = dataclasses.replace(plan, extra={"effort": [1.0, 2.0]})
        with pytest.raises(SchemaError, match=r"Plan\.extra\['effort'\]"):
            carried.validate(synthetic_economy)

    def test_a_zero_dimensional_array_is_named_rather_than_crashing(
        self, plan, synthetic_economy
    ):
        """``np.array(1.0)`` is a float64 array with no leading dimension to read."""
        carried = dataclasses.replace(plan, extra={"effort": np.array(1.0)})
        with pytest.raises(SchemaError, match=r"Plan\.extra\['effort'\]"):
            carried.validate(synthetic_economy)

    def test_a_second_dimension_is_left_alone(self, plan, synthetic_economy):
        """An array per consumer unit and producing unit is one row per consumer unit."""
        carried = dataclasses.replace(
            plan,
            extra={
                "utility": np.ones((synthetic_economy.n_consumers, synthetic_economy.n_units))
            },
        )
        carried.validate(synthetic_economy)

    def test_it_is_the_leading_dimension_that_is_checked(self, plan, synthetic_economy):
        """The trailing dimension matching one of the three counts does not stand in for it."""
        odd = 1 + max(
            synthetic_economy.n_units,
            synthetic_economy.n_consumers,
            synthetic_economy.n_commodities,
        )
        carried = dataclasses.replace(
            plan, extra={"utility": np.ones((odd, synthetic_economy.n_units))}
        )
        with pytest.raises(SchemaError, match=r"Plan\.extra\['utility'\]"):
            carried.validate(synthetic_economy)


THREE_EXTRA_KEYS = ("effort", "consumer_demand", "utility")
"""Three ``extra`` keys, so that a check can be shown to reach the middle and the last one."""


class TestEveryExtraKeyIsChecked:
    """Each key of a three-key bag, not the one that happens to come first.

    A check that stopped after the first key passes every single-key case, and a bag with one
    key is what a mechanism writes only until it writes a second quantity.
    """

    def bag(self, economy, position, value):
        rows = {key: np.ones(economy.n_units) for key in THREE_EXTRA_KEYS}
        rows[THREE_EXTRA_KEYS[position]] = value
        return rows

    @pytest.mark.parametrize("position", [0, 1, 2])
    def test_a_leading_dimension_matching_none_of_the_three_is_found(
        self, plan, synthetic_economy, position
    ):
        odd = 1 + max(
            synthetic_economy.n_units,
            synthetic_economy.n_consumers,
            synthetic_economy.n_commodities,
        )
        carried = dataclasses.replace(
            plan, extra=self.bag(synthetic_economy, position, np.ones(odd))
        )
        with pytest.raises(SchemaError, match=THREE_EXTRA_KEYS[position]):
            carried.validate(synthetic_economy)

    @pytest.mark.parametrize("position", [1, 2])
    def test_a_non_array_value_behind_a_good_key_is_found(
        self, plan, synthetic_economy, position
    ):
        carried = dataclasses.replace(
            plan, extra=self.bag(synthetic_economy, position, [1.0, 2.0])
        )
        with pytest.raises(SchemaError, match=THREE_EXTRA_KEYS[position]):
            carried.validate(synthetic_economy)

    @pytest.mark.parametrize("position", [1, 2])
    def test_a_non_finite_entry_behind_a_good_key_is_found(
        self, plan, synthetic_economy, position
    ):
        values = np.ones(synthetic_economy.n_units)
        values[0] = np.nan
        carried = dataclasses.replace(
            plan, extra=self.bag(synthetic_economy, position, values)
        )
        with pytest.raises(SchemaError, match=THREE_EXTRA_KEYS[position]):
            carried.validate(synthetic_economy)

    @pytest.mark.parametrize("position", [1, 2])
    def test_a_zero_dimensional_array_behind_a_good_key_is_found(
        self, plan, synthetic_economy, position
    ):
        carried = dataclasses.replace(
            plan, extra=self.bag(synthetic_economy, position, np.array(1.0))
        )
        with pytest.raises(SchemaError, match=THREE_EXTRA_KEYS[position]):
            carried.validate(synthetic_economy)


class TestAccessorsRejectMisshapenPlans:
    """A plan built for a different economy has to be named, not silently aggregated.

    ``total_consumption`` in particular scatters into a commodity-length vector whatever the
    consumption block's shape, so without a check it answers with a wrong vector rather than
    an error.
    """

    ACCESSORS = ("total_output", "total_input_use", "total_consumption", "endowment_use")

    @pytest.mark.parametrize("accessor", ACCESSORS)
    def test_a_short_output_column_is_named(self, plan, synthetic_economy, accessor):
        broken = dataclasses.replace(plan, output=np.zeros(5))
        with pytest.raises(SchemaError) as excinfo:
            getattr(broken, accessor)(synthetic_economy)
        message = str(excinfo.value)
        assert "Plan.output" in message
        assert "5" in message
        assert str(synthetic_economy.n_units) in message

    @pytest.mark.parametrize("accessor", ACCESSORS)
    def test_a_short_input_use_column_is_named(self, plan, synthetic_economy, accessor):
        broken = dataclasses.replace(plan, input_use=np.zeros(2))
        with pytest.raises(SchemaError, match=r"Plan\.input_use"):
            getattr(broken, accessor)(synthetic_economy)

    @pytest.mark.parametrize("accessor", ACCESSORS)
    def test_a_short_provision_column_is_named(self, plan, synthetic_economy, accessor):
        broken = dataclasses.replace(plan, provision=np.zeros(2))
        with pytest.raises(SchemaError, match=r"Plan\.provision"):
            getattr(broken, accessor)(synthetic_economy)

    @pytest.mark.parametrize("accessor", ACCESSORS)
    def test_a_consumption_block_with_the_wrong_row_count_is_named(
        self, plan, synthetic_economy, accessor
    ):
        broken = dataclasses.replace(plan, consumption=plan.consumption[:-1])
        with pytest.raises(SchemaError, match=r"Plan\.consumption"):
            getattr(broken, accessor)(synthetic_economy)

    @pytest.mark.parametrize("accessor", ACCESSORS)
    def test_a_consumption_commodity_outside_the_commodity_range_is_named(
        self, plan, synthetic_economy, accessor
    ):
        columns = plan.consumption_commodity.copy()
        columns[0] = synthetic_economy.n_commodities
        broken = dataclasses.replace(plan, consumption_commodity=columns)
        with pytest.raises(SchemaError, match=r"Plan\.consumption_commodity"):
            getattr(broken, accessor)(synthetic_economy)

    def test_total_consumption_does_not_answer_for_a_plan_of_another_size(
        self, plan, synthetic_economy
    ):
        """A five-unit plan is refused against a nine-unit economy, not aggregated into one."""
        broken = dataclasses.replace(
            plan,
            output=np.zeros(5),
            consumption=np.ones((2, 3)),
        )
        with pytest.raises(SchemaError):
            broken.total_consumption(synthetic_economy)


class TestDerivedAccessors:
    def test_total_output(self, plan, synthetic_economy):
        expected = expected_scatter(
            synthetic_economy.output_commodity, plan.output, synthetic_economy.n_commodities
        )
        np.testing.assert_array_equal(plan.total_output(synthetic_economy), expected)

    def test_total_output_ignores_unit_group(self, plan, synthetic_economy):
        by_group = expected_scatter(
            synthetic_economy.unit_group, plan.output, synthetic_economy.n_commodities
        )
        assert not np.array_equal(plan.total_output(synthetic_economy), by_group)

    def test_total_input_use(self, plan, synthetic_economy):
        expected = expected_scatter(
            synthetic_economy.input_commodity, plan.input_use, synthetic_economy.n_commodities
        )
        np.testing.assert_array_equal(plan.total_input_use(synthetic_economy), expected)

    def test_total_consumption(self, plan, synthetic_economy):
        expected = expected_scatter(
            CONSUMPTION_COMMODITY,
            expected_column_sums(plan.consumption),
            synthetic_economy.n_commodities,
        )
        np.testing.assert_allclose(plan.total_consumption(synthetic_economy), expected)

    def test_total_consumption_reads_the_column_mapping(self, plan, synthetic_economy):
        """Filing column ``j`` under commodity ``j`` is a different answer on this fixture."""
        ignoring_the_mapping = expected_scatter(
            range(len(CONSUMPTION_COMMODITY)),
            expected_column_sums(plan.consumption),
            synthetic_economy.n_commodities,
        )
        assert not np.array_equal(
            plan.total_consumption(synthetic_economy), ignoring_the_mapping
        )

    def test_endowment_use_covers_only_natural_resources_and_labor(self, plan, synthetic_economy):
        used = plan.endowment_use(synthetic_economy)
        total = plan.total_input_use(synthetic_economy)
        kinds = np.asarray(synthetic_economy.commodity_kind)
        endowed = (kinds == CommodityKind.NATURAL_RESOURCE) | (kinds == CommodityKind.LABOR)
        np.testing.assert_array_equal(used[endowed], total[endowed])
        np.testing.assert_array_equal(used[~endowed], np.zeros(int((~endowed).sum())))

    def test_endowment_use_excludes_intermediates(self, plan, synthetic_economy):
        used = plan.endowment_use(synthetic_economy)
        total = plan.total_input_use(synthetic_economy)
        intermediates = np.asarray(synthetic_economy.commodity_kind) == CommodityKind.INTERMEDIATE
        assert total[intermediates].sum() > 0.0
        assert used[intermediates].sum() == 0.0

    def test_accessors_return_commodity_length_vectors(self, plan, synthetic_economy):
        for accessor in (plan.total_output, plan.total_input_use, plan.total_consumption,
                         plan.endowment_use):
            result = accessor(synthetic_economy)
            assert result.shape == (synthetic_economy.n_commodities,)
            assert result.dtype == np.float64


OPTIONAL_FIELDS = ("consumption", "consumption_commodity", "provision")
"""The fixed fields a mechanism may declare absent, in the order :class:`Plan` declares them."""


@pytest.fixture
def bare_plan(plan):
    """``plan`` with every optional fixed field declared absent."""
    return dataclasses.replace(
        plan, consumption=None, consumption_commodity=None, provision=None
    )


class TestAbsenceIsDeclaredNotDefaulted:
    """``None`` says the mechanism has no such quantity; leaving the argument out is an error."""

    @pytest.mark.parametrize("field", OPTIONAL_FIELDS)
    def test_leaving_the_argument_out_is_still_a_missing_argument(self, plan, field):
        arguments = {
            name: getattr(plan, name)
            for name in ("output", "input_use", *OPTIONAL_FIELDS)
            if name != field
        }
        with pytest.raises(TypeError, match=field):
            Plan(**arguments)

    def test_a_plan_may_declare_the_consumption_pair_and_provision_absent(
        self, bare_plan, synthetic_economy
    ):
        bare_plan.validate(synthetic_economy)
        assert bare_plan.consumption is None
        assert bare_plan.consumption_commodity is None
        assert bare_plan.provision is None

    def test_provision_alone_may_be_absent(self, plan, synthetic_economy):
        dataclasses.replace(plan, provision=None).validate(synthetic_economy)

    def test_the_consumption_pair_alone_may_be_absent(self, plan, synthetic_economy):
        dataclasses.replace(
            plan, consumption=None, consumption_commodity=None
        ).validate(synthetic_economy)

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_a_required_field_may_not_be_declared_absent(self, plan, field):
        """The two required fields are refused where absence would be declared, not later."""
        with pytest.raises(SchemaError, match=rf"Plan\.{field}"):
            dataclasses.replace(plan, **{field: None})


class TestTheRequiredArraysAreRefusedAtConstruction:
    """``output`` and ``input_use`` carry arrays, or the plan does not come into existence.

    The refusal is at construction rather than in :meth:`Plan.validate` because nothing obliges
    a mechanism to call ``validate`` and ``run`` does not. A plan holding ``None`` in both has
    no physical column at all, and every tool that reads "the columns this plan carries" then
    reads nothing: the divergence watch of ``iterate`` finds no array to test and reports the
    loop as finite, and ``check_determinism`` finds no column to compare.
    """

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_the_refusal_names_the_field(self, plan, field):
        with pytest.raises(SchemaError) as excinfo:
            dataclasses.replace(plan, **{field: None})
        assert f"Plan.{field}" in str(excinfo.value)

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_the_refusal_names_the_fields_that_may_be_absent(self, plan, field):
        """A researcher who reaches this needs to know which absences are available."""
        with pytest.raises(SchemaError) as excinfo:
            dataclasses.replace(plan, **{field: None})
        message = str(excinfo.value)
        for optional in OPTIONAL_FIELDS:
            assert optional in message

    def test_both_absent_together_is_refused_as_well(self, plan):
        with pytest.raises(SchemaError, match=r"Plan\.output"):
            dataclasses.replace(plan, output=None, input_use=None)

    @pytest.mark.parametrize("subclass", [StatedPlan, AllocatedPlan])
    def test_a_subclass_refuses_it_too(self, plan, subclass):
        with pytest.raises(SchemaError, match=r"Plan\.output"):
            subclass(
                output=None,
                input_use=plan.input_use,
                consumption=None,
                consumption_commodity=None,
                provision=None,
            )

    def test_it_answers_before_the_consumption_pairing_check(self, plan):
        """A plan missing a required column says so, rather than naming the pair it also lacks."""
        with pytest.raises(SchemaError) as excinfo:
            Plan(
                output=None,
                input_use=None,
                consumption=None,
                consumption_commodity=plan.consumption_commodity,
                provision=None,
            )
        assert "Plan.output" in str(excinfo.value)

    def test_the_widest_absence_a_plan_may_declare_still_leaves_two_columns(self, bare_plan):
        """What the divergence watch and the determinism comparison are left to read."""
        carried = [
            name
            for name in ("output", "input_use", "consumption", "provision")
            if getattr(bare_plan, name) is not None
        ]
        assert carried == ["output", "input_use"]


class TestConsumptionPairing:
    """``consumption`` and ``consumption_commodity`` describe one quantity, so they go together."""

    def test_consumption_without_its_commodity_column_is_refused(self, plan):
        with pytest.raises(SchemaError, match="consumption_commodity"):
            dataclasses.replace(plan, consumption_commodity=None)

    def test_a_commodity_column_without_consumption_is_refused(self, plan):
        with pytest.raises(SchemaError, match="consumption"):
            dataclasses.replace(plan, consumption=None)

    def test_the_refusal_names_both_sides(self, plan):
        with pytest.raises(SchemaError) as excinfo:
            dataclasses.replace(plan, consumption=None)
        message = str(excinfo.value)
        assert "Plan.consumption" in message
        assert "Plan.consumption_commodity" in message

    def test_both_absent_together_is_accepted(self, plan):
        paired = dataclasses.replace(plan, consumption=None, consumption_commodity=None)
        assert paired.consumption is None
        assert paired.consumption_commodity is None


class TestAbsentFields:
    """``absent_fields`` is how a reader finds out which quantities a plan does not carry."""

    def test_a_full_plan_declares_nothing_absent(self, plan):
        assert plan.absent_fields == ()

    def test_every_absent_field_is_listed(self, bare_plan):
        assert bare_plan.absent_fields == (
            "consumption",
            "consumption_commodity",
            "provision",
        )

    def test_one_absent_field_is_listed_alone(self, plan):
        assert dataclasses.replace(plan, provision=None).absent_fields == ("provision",)

    def test_the_order_is_the_order_the_fields_are_declared_in(self, bare_plan):
        declared = [field.name for field in dataclasses.fields(Plan)]
        listed = list(bare_plan.absent_fields)
        assert listed == sorted(listed, key=declared.index)

    def test_it_is_a_tuple_of_strings(self, bare_plan):
        assert isinstance(bare_plan.absent_fields, tuple)
        assert all(isinstance(name, str) for name in bare_plan.absent_fields)

    def test_it_reads_as_an_attribute(self, plan):
        """The declared signature is ``Plan.absent_fields``, not a call."""
        assert not callable(plan.absent_fields)


class TestAccessorsOnAPlanWithAbsentFields:
    """An accessor either answers unchanged or refuses; nothing reads an absent field as zero."""

    UNAFFECTED = ("total_output", "total_input_use", "endowment_use")

    @pytest.mark.parametrize("accessor", UNAFFECTED)
    def test_an_accessor_that_needs_neither_answers_unchanged(
        self, plan, bare_plan, synthetic_economy, accessor
    ):
        np.testing.assert_array_equal(
            getattr(bare_plan, accessor)(synthetic_economy),
            getattr(plan, accessor)(synthetic_economy),
        )

    @pytest.mark.parametrize("accessor", UNAFFECTED)
    @pytest.mark.parametrize("absent", OPTIONAL_FIELDS)
    def test_each_absent_field_alone_leaves_those_accessors_unchanged(
        self, plan, synthetic_economy, accessor, absent
    ):
        fields = {absent: None}
        if absent in ("consumption", "consumption_commodity"):
            fields = {"consumption": None, "consumption_commodity": None}
        partial = dataclasses.replace(plan, **fields)
        np.testing.assert_array_equal(
            getattr(partial, accessor)(synthetic_economy),
            getattr(plan, accessor)(synthetic_economy),
        )

    def test_total_consumption_refuses_instead_of_answering_zero(
        self, bare_plan, synthetic_economy
    ):
        with pytest.raises(PlanFieldAbsent):
            bare_plan.total_consumption(synthetic_economy)

    def test_the_refusal_names_the_field_the_accessor_and_the_way_out(
        self, bare_plan, synthetic_economy
    ):
        with pytest.raises(PlanFieldAbsent) as excinfo:
            bare_plan.total_consumption(synthetic_economy)
        message = str(excinfo.value)
        assert "Plan.consumption" in message
        assert "total_consumption" in message
        assert "does not apply" in message

    def test_the_exception_is_a_schema_error(self):
        assert issubclass(PlanFieldAbsent, SchemaError)

    def test_a_plan_with_absent_fields_validates(self, bare_plan, synthetic_economy):
        bare_plan.validate(synthetic_economy)

    def test_validate_still_checks_the_fields_that_are_present(
        self, bare_plan, synthetic_economy
    ):
        broken = dataclasses.replace(bare_plan, output=bare_plan.output[:-1])
        with pytest.raises(SchemaError, match=r"Plan\.output"):
            broken.validate(synthetic_economy)

    def test_a_non_finite_entry_is_still_caught_beside_an_absent_field(
        self, bare_plan, synthetic_economy
    ):
        values = np.asarray(bare_plan.input_use).copy()
        values[0] = np.nan
        broken = dataclasses.replace(bare_plan, input_use=values)
        with pytest.raises(SchemaError, match="input_use"):
            broken.validate(synthetic_economy)


class TestValuationIsCheckedOnTheWayIn:
    """Every ``valuation`` array is ``f64[n_commodities]``, refused rather than converted."""

    def test_an_int64_array_is_refused_at_construction(self, plan, synthetic_economy):
        prices = np.full(synthetic_economy.n_commodities, 700, dtype=np.int64)
        with pytest.raises(SchemaError, match="float64"):
            dataclasses.replace(plan, valuation={INDICATIVE_PRICE: prices})

    def test_a_float32_array_is_refused_at_construction(self, plan, synthetic_economy):
        prices = np.full(synthetic_economy.n_commodities, 700.0, dtype=np.float32)
        with pytest.raises(SchemaError, match="float64"):
            dataclasses.replace(plan, valuation={INDICATIVE_PRICE: prices})

    def test_a_plain_list_is_refused_at_construction(self, plan, synthetic_economy):
        with pytest.raises(SchemaError, match="float64"):
            dataclasses.replace(
                plan, valuation={INDICATIVE_PRICE: [700.0] * synthetic_economy.n_commodities}
            )

    def test_the_refusal_names_the_key(self, plan, synthetic_economy):
        prices = np.full(synthetic_economy.n_commodities, 700, dtype=np.int64)
        with pytest.raises(SchemaError, match="indicative_price"):
            dataclasses.replace(plan, valuation={INDICATIVE_PRICE: prices})

    def test_a_wrong_dtype_is_not_quietly_converted(self, plan, synthetic_economy):
        """The library reports the type the mechanism computed, it does not paper over it."""
        prices = np.full(synthetic_economy.n_commodities, 700, dtype=np.int64)
        with pytest.raises(SchemaError):
            dataclasses.replace(plan, valuation={INDICATIVE_PRICE: prices})
        assert plan.valuation[INDICATIVE_PRICE].dtype == np.float64

    @pytest.mark.parametrize("offset", [-1, 1])
    def test_a_wrong_length_is_refused_by_validate(self, plan, synthetic_economy, offset):
        prices = np.full(synthetic_economy.n_commodities + offset, 700.0)
        broken = dataclasses.replace(plan, valuation={INDICATIVE_PRICE: prices})
        with pytest.raises(SchemaError, match="indicative_price"):
            broken.validate(synthetic_economy)

    def test_the_length_refusal_states_both_counts(self, plan, synthetic_economy):
        prices = np.full(synthetic_economy.n_commodities + 1, 700.0)
        broken = dataclasses.replace(plan, valuation={INDICATIVE_PRICE: prices})
        with pytest.raises(SchemaError) as excinfo:
            broken.validate(synthetic_economy)
        message = str(excinfo.value)
        assert str(synthetic_economy.n_commodities + 1) in message
        assert str(synthetic_economy.n_commodities) in message

    def test_a_two_dimensional_array_is_refused(self, plan, synthetic_economy):
        prices = np.full((synthetic_economy.n_commodities, 2), 700.0)
        broken = dataclasses.replace(plan, valuation={INDICATIVE_PRICE: prices})
        with pytest.raises(SchemaError, match="indicative_price"):
            broken.validate(synthetic_economy)

    def test_a_well_formed_valuation_passes(self, plan, synthetic_economy):
        plan.validate(synthetic_economy)

    def test_every_key_is_checked_not_only_the_first(self, plan, synthetic_economy):
        broken = dataclasses.replace(
            plan,
            valuation={
                INDICATIVE_PRICE: np.full(synthetic_economy.n_commodities, 700.0),
                LABOR_VALUE: np.full(synthetic_economy.n_commodities + 1, 1.0),
            },
        )
        with pytest.raises(SchemaError, match="labor_value"):
            broken.validate(synthetic_economy)

    @pytest.mark.parametrize("position", [0, 1, 2])
    def test_the_dtype_check_reaches_every_key_whatever_its_position(
        self, plan, synthetic_economy, position
    ):
        """Three keys, one of them integer-typed, taking each place in the bag in turn."""
        keys = [INDICATIVE_PRICE, LABOR_VALUE, SHADOW_PRICE]
        bag = {key: np.full(synthetic_economy.n_commodities, 700.0) for key in keys}
        bag[keys[position]] = np.full(synthetic_economy.n_commodities, 700, dtype=np.int64)
        with pytest.raises(SchemaError, match=keys[position]):
            dataclasses.replace(plan, valuation=bag)

    @pytest.mark.parametrize("position", [1, 2])
    def test_a_float32_key_behind_a_float64_one_is_still_refused(
        self, plan, synthetic_economy, position
    ):
        keys = [INDICATIVE_PRICE, LABOR_VALUE, SHADOW_PRICE]
        bag = {key: np.full(synthetic_economy.n_commodities, 700.0) for key in keys}
        bag[keys[position]] = np.full(
            synthetic_economy.n_commodities, 700.0, dtype=np.float32
        )
        with pytest.raises(SchemaError, match=keys[position]):
            dataclasses.replace(plan, valuation=bag)

    @pytest.mark.parametrize("position", [1, 2])
    def test_a_plain_list_behind_an_array_is_still_refused(
        self, plan, synthetic_economy, position
    ):
        keys = [INDICATIVE_PRICE, LABOR_VALUE, SHADOW_PRICE]
        bag = {key: np.full(synthetic_economy.n_commodities, 700.0) for key in keys}
        bag[keys[position]] = [700.0] * synthetic_economy.n_commodities
        with pytest.raises(SchemaError, match=keys[position]):
            dataclasses.replace(plan, valuation=bag)


class TestPlanSubclasses:
    """``StatedPlan`` and ``AllocatedPlan`` add an identity and nothing else."""

    @pytest.mark.parametrize("subclass", [StatedPlan, AllocatedPlan])
    def test_it_is_a_plan(self, subclass):
        assert issubclass(subclass, Plan)

    @pytest.mark.parametrize("subclass", [StatedPlan, AllocatedPlan])
    def test_it_adds_no_field(self, subclass):
        assert [field.name for field in dataclasses.fields(subclass)] == [
            field.name for field in dataclasses.fields(Plan)
        ]

    @pytest.mark.parametrize("subclass", [StatedPlan, AllocatedPlan])
    def test_it_takes_everything_a_plan_takes(self, plan, synthetic_economy, subclass):
        typed = subclass(
            output=plan.output,
            input_use=plan.input_use,
            consumption=plan.consumption,
            consumption_commodity=plan.consumption_commodity,
            provision=plan.provision,
            valuation=dict(plan.valuation),
        )
        typed.validate(synthetic_economy)
        for accessor in ("total_output", "total_input_use", "total_consumption", "endowment_use"):
            np.testing.assert_array_equal(
                getattr(typed, accessor)(synthetic_economy),
                getattr(plan, accessor)(synthetic_economy),
            )

    @pytest.mark.parametrize("subclass", [StatedPlan, AllocatedPlan])
    def test_it_accepts_an_absent_field_like_its_base(self, plan, synthetic_economy, subclass):
        typed = subclass(
            output=plan.output,
            input_use=plan.input_use,
            consumption=None,
            consumption_commodity=None,
            provision=None,
        )
        typed.validate(synthetic_economy)
        assert typed.absent_fields == ("consumption", "consumption_commodity", "provision")

    @pytest.mark.parametrize("subclass", [StatedPlan, AllocatedPlan])
    def test_replacing_a_field_keeps_the_identity(self, plan, subclass):
        typed = dataclasses.replace(
            subclass(
                output=plan.output,
                input_use=plan.input_use,
                consumption=plan.consumption,
                consumption_commodity=plan.consumption_commodity,
                provision=plan.provision,
            ),
            provision=None,
        )
        assert isinstance(typed, subclass)

    def test_the_two_identities_are_distinct(self):
        assert not issubclass(StatedPlan, AllocatedPlan)
        assert not issubclass(AllocatedPlan, StatedPlan)


class TestRequireComparable:
    """Comparing a stated quantity against an allocated one is refused, not silently done."""

    def typed(self, plan, subclass):
        return subclass(
            output=plan.output,
            input_use=plan.input_use,
            consumption=plan.consumption,
            consumption_commodity=plan.consumption_commodity,
            provision=plan.provision,
        )

    @pytest.mark.parametrize("subclass", [StatedPlan, AllocatedPlan])
    def test_two_of_the_same_identity_are_comparable(self, plan, subclass):
        require_comparable(self.typed(plan, subclass), self.typed(plan, subclass))

    def test_two_plain_plans_are_comparable(self, plan):
        require_comparable(plan, plan)

    @pytest.mark.parametrize("subclass", [StatedPlan, AllocatedPlan])
    def test_a_plain_plan_on_either_side_is_comparable(self, plan, subclass):
        require_comparable(plan, self.typed(plan, subclass))
        require_comparable(self.typed(plan, subclass), plan)

    @pytest.mark.parametrize("order", [(StatedPlan, AllocatedPlan), (AllocatedPlan, StatedPlan)])
    def test_a_stated_plan_and_an_allocated_plan_are_refused(self, plan, order):
        left, right = (self.typed(plan, subclass) for subclass in order)
        with pytest.raises(ValueError):
            require_comparable(left, right)

    @pytest.mark.parametrize("order", [(StatedPlan, AllocatedPlan), (AllocatedPlan, StatedPlan)])
    def test_the_refusal_names_both_identities_and_what_differs(self, plan, order):
        left, right = (self.typed(plan, subclass) for subclass in order)
        with pytest.raises(ValueError) as excinfo:
            require_comparable(left, right)
        message = str(excinfo.value)
        assert "StatedPlan" in message
        assert "AllocatedPlan" in message
        assert "consumption" in message


class TestValuationLengthFollowsTheKey:
    """A key the library registered is checked against the row count it registered.

    ``indicative_price`` is one entry per commodity and ``income`` one per consumer unit, so a
    single row count for the whole bag would refuse one of the two. A key the library does not
    know carries a meaning it cannot read, so all it can ask is that the leading dimension is
    one of the three the data model counts.
    """

    def valued(self, plan, key, array):
        return dataclasses.replace(plan, valuation={key: array})

    @pytest.mark.parametrize("key", [INDICATIVE_PRICE, LABOR_VALUE, SHADOW_PRICE])
    def test_a_per_commodity_key_takes_one_entry_per_commodity(
        self, plan, synthetic_economy, key
    ):
        carried = self.valued(plan, key, np.zeros(synthetic_economy.n_commodities))
        carried.validate(synthetic_economy)

    @pytest.mark.parametrize("key", [INDICATIVE_PRICE, LABOR_VALUE, SHADOW_PRICE])
    def test_a_per_commodity_key_refuses_one_entry_per_consumer_unit(
        self, plan, synthetic_economy, key
    ):
        carried = self.valued(plan, key, np.zeros(synthetic_economy.n_consumers))
        with pytest.raises(SchemaError, match=key):
            carried.validate(synthetic_economy)

    def test_income_takes_one_entry_per_consumer_unit(self, plan, synthetic_economy):
        carried = self.valued(plan, INCOME, np.zeros(synthetic_economy.n_consumers))
        carried.validate(synthetic_economy)

    def test_income_refuses_one_entry_per_commodity(self, plan, synthetic_economy):
        """The two counts differ on this economy, so the wrong one cannot pass by accident."""
        assert synthetic_economy.n_consumers != synthetic_economy.n_commodities
        carried = self.valued(plan, INCOME, np.zeros(synthetic_economy.n_commodities))
        with pytest.raises(SchemaError, match="income"):
            carried.validate(synthetic_economy)

    def test_the_refusal_for_a_registered_key_states_what_that_key_counts(
        self, plan, synthetic_economy
    ):
        carried = self.valued(plan, INCOME, np.zeros(synthetic_economy.n_commodities))
        with pytest.raises(SchemaError) as excinfo:
            carried.validate(synthetic_economy)
        message = str(excinfo.value)
        assert "one entry per consumer unit" in message
        assert str(synthetic_economy.n_consumers) in message

    @pytest.mark.parametrize("rows", ["n_units", "n_consumers", "n_commodities"])
    def test_an_unregistered_key_takes_any_of_the_three_row_counts(
        self, plan, synthetic_economy, rows
    ):
        carried = self.valued(plan, "utility", np.zeros(getattr(synthetic_economy, rows)))
        carried.validate(synthetic_economy)

    def test_an_unregistered_key_refuses_a_leading_dimension_matching_none_of_them(
        self, plan, synthetic_economy
    ):
        odd = 1 + max(
            synthetic_economy.n_units,
            synthetic_economy.n_consumers,
            synthetic_economy.n_commodities,
        )
        carried = self.valued(plan, "utility", np.zeros(odd))
        with pytest.raises(SchemaError, match="utility"):
            carried.validate(synthetic_economy)

    def test_the_refusal_for_an_unregistered_key_states_all_three_counts(
        self, plan, synthetic_economy
    ):
        carried = self.valued(plan, "utility", np.zeros(1))
        with pytest.raises(SchemaError) as excinfo:
            carried.validate(synthetic_economy)
        message = str(excinfo.value)
        assert "one entry per" not in message
        for rows in ("n_units", "n_consumers", "n_commodities"):
            assert str(getattr(synthetic_economy, rows)) in message

    def test_an_unregistered_key_may_carry_a_second_dimension(self, plan, synthetic_economy):
        """The library cannot know what a key it does not recognise counts across."""
        carried = self.valued(plan, "utility", np.zeros((synthetic_economy.n_consumers, 2)))
        carried.validate(synthetic_economy)

    def test_an_unregistered_key_refuses_a_zero_dimensional_array(
        self, plan, synthetic_economy
    ):
        """A scalar array has no leading dimension, so the rank guard has to answer first."""
        carried = self.valued(plan, "utility", np.array(1.0))
        with pytest.raises(SchemaError, match="utility"):
            carried.validate(synthetic_economy)

    @pytest.mark.parametrize("position", [1, 2])
    def test_the_length_check_reaches_every_key_whatever_its_position(
        self, plan, synthetic_economy, position
    ):
        keys = [INDICATIVE_PRICE, LABOR_VALUE, SHADOW_PRICE]
        bag = {key: np.zeros(synthetic_economy.n_commodities) for key in keys}
        bag[keys[position]] = np.zeros(synthetic_economy.n_commodities + 1)
        carried = dataclasses.replace(plan, valuation=bag)
        with pytest.raises(SchemaError, match=keys[position]):
            carried.validate(synthetic_economy)

    def test_a_registered_key_may_not(self, plan, synthetic_economy):
        carried = self.valued(
            plan, INDICATIVE_PRICE, np.zeros((synthetic_economy.n_commodities, 2))
        )
        with pytest.raises(SchemaError, match="indicative_price"):
            carried.validate(synthetic_economy)

    def test_the_dtype_check_covers_a_registered_and_an_unregistered_key_alike(
        self, plan, synthetic_economy
    ):
        for key in (INCOME, "utility"):
            with pytest.raises(SchemaError, match="float64"):
                self.valued(plan, key, np.zeros(synthetic_economy.n_consumers, dtype=np.int64))


def key_constants_documented_as(role: str) -> set[str]:
    """The string constants of :mod:`cyberstride.plan` whose docstring opens with ``role``.

    The role is read from the source because a module-level constant's docstring is not kept
    at runtime. Reading it is what makes this a check on the module rather than on a list
    written out beside it: a constant added under ``role`` joins the set without anyone
    editing the test.
    """
    module = ast.parse(inspect.getsource(cyberstride.plan))
    found = set()
    for statement, following in zip(module.body, module.body[1:]):
        if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
            continue
        if not isinstance(statement.targets[0], ast.Name):
            continue
        if not isinstance(statement.value, ast.Constant) or not isinstance(
            statement.value.value, str
        ):
            continue
        if (
            isinstance(following, ast.Expr)
            and isinstance(following.value, ast.Constant)
            and isinstance(following.value.value, str)
            and following.value.value.startswith(role)
        ):
            found.add(statement.value.value)
    return found


def published_key_constants() -> set[str]:
    """The public upper-case string constants :mod:`cyberstride.plan` exports."""
    return {
        value
        for name, value in vars(cyberstride.plan).items()
        if not name.startswith("_") and name.isupper() and isinstance(value, str)
    }


class TestTheValuationRegistryIsComplete:
    """Every valuation key the module publishes is registered with a row count.

    An unregistered key falls through to the loose check that any of the three row counts
    passes, so a per-consumer-unit key would be accepted at commodity length and back. The
    cases above name their keys one by one, so a fifth constant added without a registration
    turns nothing red there; this is where it does.
    """

    def test_the_source_carries_both_roles(self):
        """The reading is a check only while it finds something to read."""
        assert key_constants_documented_as("Valuation key:")
        assert key_constants_documented_as("Extra key:")

    def test_every_valuation_key_constant_is_registered(self):
        assert key_constants_documented_as("Valuation key:") == set(
            cyberstride.plan._VALUATION_ROWS
        )

    def test_every_published_key_constant_declares_which_bag_it_belongs_to(self):
        roles = key_constants_documented_as("Valuation key:") | key_constants_documented_as(
            "Extra key:"
        )
        assert published_key_constants() == roles
