"""How the library's messages name fields, count things and put an article before a type.

Three rules, each pinned with the whole message where the message is short enough to write out:

- a message about a ``Plan`` field names it ``Plan.<field>``, and one that lists several fields
  names each of them that way;
- a count agrees with its noun: ``1 entry``, ``2 entries``;
- a type name read off a value takes ``an`` before a vowel letter: ``an int``, ``a list``.

The package also calls what turns one period's economy into the next an evolution rule, the
term the glossary uses.

The economies here are as small as each message needs: one of a thing for the singular, two
for the plural.
"""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import numpy as np
import pytest

import demplan
from demplan import (
    INCOME,
    LEONTIEF,
    ConfigurationError,
    Economy,
    Plan,
    SchemaError,
    compare_economy_digests,
    economy_digest,
    period_differences,
    plan_differences,
    run_configuration,
    technology_margins,
)
from demplan.io import WiodLaborGap
from demplan.prefabs.hahnel import book_2021
from reference.wiod_workbooks import WiotTable, write_xlsb, write_xlsx
from test_load_wiod import sea_rows

PACKAGE_DIR = Path(demplan.__file__).resolve().parent

PLAN_FIELDS = ("output", "input_use", "consumption", "consumption_commodity", "shared_use")

BARE_PLAN_FIELD = re.compile(
    r"(?<![\w.])(" + "|".join(sorted(PLAN_FIELDS, key=len, reverse=True)) + r")\b"
)
"""A ``Plan`` field name not preceded by ``Plan.`` (or by any other qualifier)."""


def economy_of(n_commodities: int = 1, n_units: int = 1, n_consumers: int = 1, **overrides):
    """Every unit uses commodity 0 and makes commodity ``unit % n_commodities``."""
    fields = dict(
        period=0,
        commodity_id=np.arange(n_commodities, dtype=np.int64),
        endowment=np.zeros(n_commodities, dtype=np.float64),
        unit_id=np.arange(n_units, dtype=np.int64),
        technology_kind=[LEONTIEF] * n_units,
        technology_scale=np.ones(n_units, dtype=np.float64),
        input_offsets=np.arange(n_units + 1, dtype=np.int64),
        input_commodity=np.zeros(n_units, dtype=np.int64),
        input_coefficient=np.ones(n_units, dtype=np.float64),
        output_offsets=np.arange(n_units + 1, dtype=np.int64),
        output_commodity=np.arange(n_units, dtype=np.int64) % n_commodities,
        output_coefficient=np.ones(n_units, dtype=np.float64),
        consumer_id=np.arange(n_consumers, dtype=np.int64),
    )
    fields.update(overrides)
    return Economy(**fields)


def plan_for(economy: Economy, **overrides) -> Plan:
    """A plan shaped for ``economy``: zeros everywhere, one consumption column per commodity."""
    fields = dict(
        output=np.zeros(economy.n_outputs, dtype=np.float64),
        input_use=np.zeros(economy.n_inputs, dtype=np.float64),
        consumption=np.zeros((economy.n_consumers, economy.n_commodities), dtype=np.float64),
        consumption_commodity=np.arange(economy.n_commodities, dtype=np.int64),
        shared_use=np.zeros(economy.n_commodities, dtype=np.float64),
    )
    fields.update(overrides)
    return Plan(**fields)


def message_of(error_type, call, *args, **kwargs) -> str:
    with pytest.raises(error_type) as raised:
        call(*args, **kwargs)
    return str(raised.value)


def schema_message(economy: Economy, plan: Plan) -> str:
    return message_of(SchemaError, plan.validate, economy)


# ------------------------------------------------------------------------ Plan field prefix


class TestPlanFieldPrefix:
    @pytest.mark.parametrize("field", ["output", "input_use", "shared_use"])
    def test_a_non_finite_vector_field_is_named_with_the_plan_prefix(self, field):
        economy = economy_of()
        plan = plan_for(economy, **{field: np.array([np.nan])})
        assert schema_message(economy, plan) == f"Plan.{field}: row 0 is not finite"

    def test_a_non_finite_consumption_row_is_named_with_the_plan_prefix(self):
        economy = economy_of(n_consumers=2)
        plan = plan_for(economy, consumption=np.array([[0.0], [np.inf]]))
        assert schema_message(economy, plan) == "Plan.consumption: row 1 is not finite"

    def test_the_material_balance_names_both_absent_fields_with_the_prefix(self):
        economy = economy_of()
        plan = plan_for(economy, consumption=None, consumption_commodity=None, shared_use=None)
        reason = plan_differences(economy, plan).material_balance.why_not_computed
        assert reason.startswith(
            "Plan.consumption and Plan.shared_use are declared absent, so use by consumer "
            "units is not known"
        )

    @pytest.mark.parametrize(
        "absent, overrides",
        [
            ("consumption", dict(consumption=None, consumption_commodity=None)),
            ("shared_use", dict(shared_use=None)),
        ],
    )
    def test_the_material_balance_names_one_absent_field_with_the_prefix(
        self, absent, overrides
    ):
        economy = economy_of()
        reason = plan_differences(economy, plan_for(economy, **overrides))
        assert reason.material_balance.why_not_computed.startswith(
            f"Plan.{absent} is declared absent, so use by consumer units is not known"
        )

    @pytest.mark.parametrize("missing", ["output", "input_use"])
    def test_the_required_field_message_names_every_field_with_the_prefix(self, missing):
        economy = economy_of()
        message = message_of(SchemaError, plan_for, economy, **{missing: None})
        assert f"Plan.{missing} is None" in message
        for field in PLAN_FIELDS:
            assert f"Plan.{field}" in message
        assert BARE_PLAN_FIELD.findall(message) == []

    def test_the_pairing_message_names_both_fields_with_the_prefix(self):
        economy = economy_of()
        message = message_of(SchemaError, plan_for, economy, consumption=None)
        assert BARE_PLAN_FIELD.findall(message) == []
        assert "Plan.consumption is None while Plan.consumption_commodity" in message


# ------------------------------------------------------------------------ counts


class TestPlanCounts:
    def test_one_output_entry_in_the_economy(self):
        economy = economy_of()
        plan = plan_for(economy, output=np.zeros(2))
        assert schema_message(economy, plan) == (
            "Plan.output has 2 entries but the economy has 1 output entry"
        )

    def test_one_entry_in_the_plan(self):
        economy = economy_of(n_commodities=2, n_units=2)
        plan = plan_for(economy, output=np.zeros(1))
        assert schema_message(economy, plan) == (
            "Plan.output has 1 entry but the economy has 2 output entries"
        )

    def test_one_unit_input(self):
        economy = economy_of()
        plan = plan_for(economy, input_use=np.zeros(3))
        assert schema_message(economy, plan) == (
            "Plan.input_use has 3 entries but the economy has 1 unit input"
        )

    def test_one_commodity_for_shared_use(self):
        economy = economy_of()
        plan = plan_for(economy, shared_use=np.zeros(2))
        assert schema_message(economy, plan) == (
            "Plan.shared_use has 2 entries but the economy has 1 commodity"
        )

    def test_one_consumer_unit_and_one_consumption_column(self):
        economy = economy_of()
        plan = plan_for(economy, consumption=np.zeros((2, 1)))
        assert schema_message(economy, plan) == (
            "Plan.consumption has shape (2, 1) but the economy has 1 consumer unit and the "
            "plan has 1 consumption column"
        )

    def test_two_consumer_units_and_two_consumption_columns(self):
        economy = economy_of(n_commodities=2, n_consumers=2)
        plan = plan_for(economy, consumption=np.zeros((3, 2)))
        assert schema_message(economy, plan) == (
            "Plan.consumption has shape (3, 2) but the economy has 2 consumer units and the "
            "plan has 2 consumption columns"
        )

    def test_a_registered_valuation_key_against_one_consumer_unit(self):
        economy = economy_of()
        plan = plan_for(economy, valuation={INCOME: np.zeros(2)})
        assert schema_message(economy, plan) == (
            "Plan.valuation['income'] has shape (2,), but this key is registered as one entry "
            "per consumer unit and the economy has 1 consumer unit"
        )

    @pytest.mark.parametrize("bag", ["valuation", "extra"])
    def test_an_unregistered_key_against_one_of_each_row_count(self, bag):
        economy = economy_of()
        plan = plan_for(economy, **{bag: {"mine": np.zeros(2)}})
        assert schema_message(economy, plan) == (
            f"Plan.{bag}['mine'] has shape (2,), expected a leading dimension of 1 producing "
            "unit, 1 consumer unit or 1 commodity"
        )

    def test_an_unregistered_key_against_two_of_each_row_count(self):
        economy = economy_of(n_commodities=2, n_units=2, n_consumers=2)
        plan = plan_for(economy, extra={"mine": np.zeros(3)})
        assert schema_message(economy, plan) == (
            "Plan.extra['mine'] has shape (3,), expected a leading dimension of 2 producing "
            "units, 2 consumer units or 2 commodities"
        )


class TestOtherCounts:
    def test_period_differences_with_one_economy(self):
        economy = economy_of()
        plan = plan_for(economy)
        assert message_of(ValueError, period_differences, [economy], [plan, plan]) == (
            "period_differences takes one plan per economy, got 1 economy and 2 plans"
        )

    def test_period_differences_with_one_plan(self):
        economy = economy_of()
        message = message_of(ValueError, period_differences, [economy, economy], [plan_for(economy)])
        assert message == (
            "period_differences takes one plan per economy, got 2 economies and 1 plan"
        )

    def test_an_economy_column_with_one_row(self):
        message = message_of(
            SchemaError, economy_of, n_units=2, technology_scale=np.ones(1, dtype=np.float64)
        )
        assert message == "technology_scale: has 1 row, expected 2 (one row per producing unit)"

    def test_an_economy_column_expected_to_have_one_row(self):
        message = message_of(SchemaError, economy_of, technology_scale=np.ones(2))
        assert message == "technology_scale: has 2 rows, expected 1 (one row per producing unit)"

    def test_an_extra_array_expected_to_have_one_row(self):
        message = message_of(SchemaError, economy_of, unit_extra={"mine": np.zeros(2)})
        assert message == (
            "unit_extra['mine']: leading dimension is (2,), expected 1 row (one per producing "
            "unit)"
        )

    def test_an_extra_array_expected_to_have_two_rows(self):
        message = message_of(SchemaError, economy_of, n_units=2, unit_extra={"mine": np.zeros(3)})
        assert message == (
            "unit_extra['mine']: leading dimension is (3,), expected 2 rows (one per producing "
            "unit)"
        )

    def test_a_column_mapping_with_one_entry(self):
        message = message_of(
            SchemaError,
            economy_of,
            consumer_extra={
                "utility_exponent": np.zeros((1, 2)),
                "utility_exponent_commodity": np.zeros(1, dtype=np.int64),
            },
        )
        assert message == (
            "consumer_extra['utility_exponent_commodity']: has 1 entry, expected one per "
            "column of utility_exponent, which has 2"
        )

    def test_an_index_declaration_with_one_dimension_of_the_wrong_dtype(self):
        economy = economy_of()
        message = message_of(
            ValueError, plan_for(economy).endowment_use, economy, np.array([0], dtype=np.int32)
        )
        assert message == (
            "resources: expected a one-dimensional int64 array of commodity indices, got dtype "
            "int32 with 1 dimension"
        )

    def test_an_index_declaration_with_two_dimensions(self):
        economy = economy_of()
        message = message_of(
            ValueError, plan_for(economy).endowment_use, economy, np.zeros((1, 1), dtype=np.int64)
        )
        assert message.endswith("got dtype int64 with 2 dimensions")

    def test_a_margin_of_the_wrong_shape_for_a_unit_with_one_output_entry(self):
        class TwoNumbers:
            label = "two_numbers"

            def margin(self, economy, plan, unit):
                return np.zeros(2)

        economy = economy_of(technology_kind=["two_numbers"])
        technologies = {"two_numbers": TwoNumbers()}
        message = message_of(
            ValueError, technology_margins, economy, plan_for(economy), technologies
        )
        assert message == (
            "the technology for 'two_numbers' returned a margin of shape (2,) for unit 0, which "
            "has 1 output entry; a margin is one number per output entry"
        )

    def test_one_unit_without_a_labour_figure(self, tmp_path):
        table = WiotTable(
            economies=["ROW"],
            industries=["A01"],
            z=[[1.0]],
            final_demand=[[9.0, 0.0, 0.0, 0.0, 0.0]],
            gross_output=[10.0],
        )
        path = write_xlsb(tmp_path / "row.xlsb", {"2014": table.cells()})
        sea = write_xlsx(
            tmp_path / "Socio_Economic_Accounts.xlsx", {"Notes": [["notes"]], "DATA": sea_rows()}
        )
        with pytest.warns(WiodLaborGap) as record:
            demplan.load_wiod(path, 2014, labor="hours", sea=sea)
        gaps = [entry for entry in record if issubclass(entry.category, WiodLaborGap)]
        assert str(gaps[0].message) == (
            "1 producing unit has no labour figure, so it has no labour input and "
            "unit_extra['labor_observed'] is 0.0: ROW (1 unit)"
        )

    def test_perturb_exponents_counts_one_entry_in_the_singular(self):
        message = message_of(
            ValueError, book_2021._refuse_non_positive, {"input_coefficient": np.array([-1.0])}
        )
        assert message.startswith(
            "perturb_exponents left 1 of 1 entry of input_coefficient at or below zero"
        )

    def test_perturb_exponents_counts_several_entries_in_the_plural(self):
        message = message_of(
            ValueError,
            book_2021._refuse_non_positive,
            {"input_coefficient": np.array([-1.0, 1.0, 0.0])},
        )
        assert message.startswith(
            "perturb_exponents left 2 of 3 entries of input_coefficient at or below zero"
        )


# ------------------------------------------------------------------------ articles


class TestArticles:
    def test_a_list_holding_an_int_as_a_text_column(self):
        message = message_of(SchemaError, economy_of, technology_kind=[3])
        assert message == (
            "technology_kind: a list is accepted as a text column only when it holds str, and "
            "position 0 holds an int"
        )

    def test_a_list_holding_a_float_as_a_text_column(self):
        message = message_of(SchemaError, economy_of, technology_kind=[3.0])
        assert message.endswith("position 0 holds a float")

    @pytest.mark.parametrize("given, article", [(0, "an int"), ((0,), "a tuple")])
    def test_an_index_declaration_that_is_not_an_array(self, given, article):
        economy = economy_of()
        message = message_of(ValueError, plan_for(economy).endowment_use, economy, given)
        assert message.endswith(f"commodity indices, got {article}")

    @pytest.mark.parametrize("given, article", [(0, "an int"), ([], "a list")])
    def test_a_digest_block_that_is_not_a_mapping(self, given, article):
        block = economy_digest(economy_of())
        message = message_of(ConfigurationError, compare_economy_digests, given, block)
        assert message == f"recorded: expected an economy digest block, got {article}"

    def test_digest_columns_that_are_not_a_mapping(self):
        block = economy_digest(economy_of())
        edited = {**block, "columns": 1}
        message = message_of(ConfigurationError, compare_economy_digests, block, edited)
        assert message == (
            "current: columns maps a column name to its digest, this one is an int"
        )

    @pytest.mark.parametrize("document, article", [(3, "an int"), ([], "a list")])
    def test_a_configuration_document_that_is_not_an_object(self, tmp_path, document, article):
        path = tmp_path / "configuration.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        message = message_of(ConfigurationError, demplan.RunConfiguration.from_json, path)
        assert message == f"a configuration document is a JSON object, this one is {article}"

    def test_a_plan_without_absent_fields(self):
        message = message_of(
            ConfigurationError, run_configuration, _NoProcedure(), economy_of(), 0, plan=3
        )
        assert message.endswith(
            "which is the one attribute of a plan this document records, and an int has none"
        )

    def test_absent_fields_that_are_not_a_sequence(self):
        class Declares:
            absent_fields = 5

        message = message_of(
            ConfigurationError, run_configuration, _NoProcedure(), economy_of(), 0,
            plan=Declares(),
        )
        assert message == "plan.absent_fields: expected a sequence of field names, got an int"

    @pytest.mark.parametrize(
        "helper", [book_2021.scale_starting_price, book_2021.scale_nominal_quantities]
    )
    def test_a_rescale_helper_given_something_other_than_the_book_procedure(self, helper):
        message = message_of(TypeError, helper, 7, economy_of(), 2.0)
        assert message.endswith("rescales the initial price of a HahnelBook2021, and got an int")


class _NoProcedure:
    """A procedure object that a configuration document describes and never runs."""

    def solve(self, economy, seed):
        raise AssertionError("never called")


# ------------------------------------------------------------------------ terminology


class TestEvolutionRule:
    def test_the_single_period_refusal_says_evolution_rule(self):
        def advance(economy, plan, seed):
            raise AssertionError("never called")

        message = message_of(
            ConfigurationError, run_configuration, _NoProcedure(), economy_of(), 0,
            advance=advance,
        )
        assert "evolution rule" in message
        assert "evolution law" not in message

    def test_no_source_file_of_the_package_says_evolution_law(self):
        """Docstrings and messages alike: the glossary's term is the one a reader looks up."""
        offenders = []
        for path in sorted(PACKAGE_DIR.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            # A docstring can break the phrase across two lines, so the whole text is searched.
            for found in re.finditer(r"evolution\s+laws?\b", text, re.IGNORECASE):
                line = text.count("\n", 0, found.start()) + 1
                offenders.append(f"{path.relative_to(PACKAGE_DIR)}:{line}")
        assert offenders == []

    def test_the_scan_reads_the_package_sources(self):
        """The control for the scan above: it finds the files it claims to read."""
        names = {path.name for path in PACKAGE_DIR.rglob("*.py")}
        assert {"periods.py", "configuration.py", "book_2021.py"} <= names
