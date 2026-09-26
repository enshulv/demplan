"""Where the run configuration meets a real plan and a real procedure.

Two units were built side by side: ``Plan`` gained absent fields, and ``configuration``
gained a document that records which fields a plan declares absent. Neither could see the
other, because ``configuration`` reads ``absent_fields`` by duck typing and its own tests
stand a stub in for the plan. These tests are the join: a real ``Plan``, a real subclass and
a real library prefab, put through the document.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

import demplan
from demplan import (
    AllocatedPlan,
    Plan,
    RunConfiguration,
    StatedPlan,
    run_configuration,
)
from demplan.prefabs.hahnel import HahnelBook2021

from reference import synthetic


@pytest.fixture
def economy():
    return synthetic.build_economy()


def _full_plan(economy, cls=Plan):
    """A plan carrying every field, shaped for ``economy``."""
    private = np.flatnonzero(
        np.asarray(economy.commodity_kind) == int(demplan.CommodityKind.PRIVATE_GOOD)
    ).astype(np.int64)
    return cls(
        output=np.zeros(economy.n_units, dtype=np.float64),
        input_use=np.zeros(economy.n_inputs, dtype=np.float64),
        consumption=np.zeros((economy.n_consumers, private.size), dtype=np.float64),
        consumption_commodity=private,
        provision=np.zeros(economy.n_commodities, dtype=np.float64),
    )


def _sparse_plan(economy, cls=Plan):
    """A plan whose mechanism has no consumption block and no public provision."""
    return cls(
        output=np.zeros(economy.n_units, dtype=np.float64),
        input_use=np.zeros(economy.n_inputs, dtype=np.float64),
        consumption=None,
        consumption_commodity=None,
        provision=None,
    )


class TestARealPlanReachesTheDocument:
    """``absent_fields`` is a property on ``Plan`` and a duck-typed read in the document."""

    def test_a_plan_that_carries_everything_declares_nothing_absent(self, economy):
        document = run_configuration(
            HahnelBook2021(), economy, seed=0, plan=_full_plan(economy)
        )
        assert document.plan_fields_absent == ()

    def test_a_plan_that_declares_fields_absent_names_them_in_order(self, economy):
        document = run_configuration(
            HahnelBook2021(), economy, seed=0, plan=_sparse_plan(economy)
        )
        assert document.plan_fields_absent == (
            "consumption",
            "consumption_commodity",
            "provision",
        )

    def test_absent_fields_is_read_as_a_property_not_called(self, economy):
        """A method would reach the document as a bound method, or raise on the call."""
        assert isinstance(Plan.absent_fields, property)

    def test_no_plan_at_all_is_the_undeclared_form(self, economy):
        document = run_configuration(HahnelBook2021(), economy, seed=0)
        assert document.plan_fields_absent is None

    @pytest.mark.parametrize("cls", [StatedPlan, AllocatedPlan])
    def test_a_subclass_reaches_the_document_the_same_way(self, economy, cls):
        document = run_configuration(
            HahnelBook2021(), economy, seed=0, plan=_sparse_plan(economy, cls)
        )
        assert document.plan_fields_absent == (
            "consumption",
            "consumption_commodity",
            "provision",
        )


class TestTheContainerConventionHoldsAcrossTheSeam:
    """A tuple in memory on both sides of the write, a list in the file.

    ``Plan.absent_fields`` is a tuple and the document keeps it as one, so a reader who holds
    a configuration before and after a write compares the same type. JSON has no tuple, so
    the file carries a list; ``from_json`` puts the tuple back rather than leaving the two
    forms of the same document unequal.
    """

    def test_the_plan_and_the_document_agree_on_the_type(self, economy):
        plan = _sparse_plan(economy)
        document = run_configuration(HahnelBook2021(), economy, seed=0, plan=plan)
        assert isinstance(plan.absent_fields, tuple)
        assert isinstance(document.plan_fields_absent, tuple)

    def test_the_file_carries_a_list_and_reading_it_back_gives_a_tuple(
        self, economy, tmp_path
    ):
        path = tmp_path / "configuration.json"
        run_configuration(
            HahnelBook2021(), economy, seed=0, plan=_sparse_plan(economy)
        ).to_json(path)
        assert isinstance(json.loads(path.read_text(encoding="utf-8"))["plan_fields_absent"], list)
        assert isinstance(RunConfiguration.from_json(path).plan_fields_absent, tuple)


class TestARealPrefabReachesTheDocument:
    """The library's own procedure is a dataclass, so its parameters are recorded."""

    def test_the_prefab_is_recorded_as_library_code(self, economy):
        document = run_configuration(HahnelBook2021(), economy, seed=0)
        assert document.procedure["kind"] == "library"
        assert document.procedure["qualname"] == "HahnelBook2021"

    def test_the_prefabs_parameters_are_recorded_by_value(self, economy):
        document = run_configuration(
            HahnelBook2021(threshold_pct=3.0, max_rounds=100), economy, seed=0
        )
        assert document.procedure["parameters"]["threshold_pct"] == 3.0
        assert document.procedure["parameters"]["max_rounds"] == 100


class TestTheDocumentSurvivesARoundTrip:
    def test_a_written_document_reads_back_the_same(self, economy, tmp_path):
        path = tmp_path / "configuration.json"
        written = run_configuration(
            HahnelBook2021(), economy, seed=7, plan=_sparse_plan(economy)
        )
        written.to_json(path)
        read = RunConfiguration.from_json(path)
        assert read.plan_fields_absent == written.plan_fields_absent
        assert read.economy == written.economy
        assert read.seed == written.seed

    def test_the_file_is_json_a_second_reader_can_parse(self, economy, tmp_path):
        path = tmp_path / "configuration.json"
        run_configuration(HahnelBook2021(), economy, seed=7).to_json(path)
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert parsed["economy"]["algorithm"] == "sha256-columns-v2"


class TestTheDocumentTracksTheEconomyItWasGiven:
    def test_two_economies_that_differ_get_different_digests(self, economy):
        other = synthetic.build_permuted_economy()
        first = run_configuration(HahnelBook2021(), economy, seed=0)
        second = run_configuration(HahnelBook2021(), other, seed=0)
        assert first.economy["digest"] != second.economy["digest"]

    def test_the_same_economy_gets_the_same_digest_twice(self, economy):
        first = run_configuration(HahnelBook2021(), economy, seed=0)
        second = run_configuration(HahnelBook2021(), economy, seed=0)
        assert first.economy == second.economy
