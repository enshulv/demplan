"""The multi-period keys of the run configuration document: ``periods``, ``advance``,
``next_procedure``.

The single-period document is pinned as bytes: it is the document of a library without the
period keys. Three values in it depend on the checkout rather than on the document layout (the
library version, the core version and the digest of the prefab's source file), so the golden
text carries placeholders for them and the test fills them in from the installed distribution,
the core and the source file itself.

Every evolution law and next-procedure slot here raises when called: writing a document
describes the run and never runs any part of it.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import importlib.metadata as metadata
import json
from pathlib import Path

import numpy as np
import pytest

import demplan
from demplan.configuration import (
    CONFIGURATION_VERSION,
    ConfigurationError,
    RunConfiguration,
    run_configuration,
)
from demplan.prefabs.hahnel import HahnelBook2021, book_2021_rule

PREFAB_MODULE = "demplan.prefabs.hahnel.book_2021"

PERIOD_KEYS = ("periods", "advance", "next_procedure")

LOADER = {"name": "load_dep1ex", "parameters": {"endowment": 1000.0}}

SINGLE_PERIOD_GOLDEN = (
    '{\n'
    '  "configuration_version": 1,\n'
    '  "core_version": "<CORE_VERSION>",\n'
    '  "economy": {\n'
    '    "algorithm": "sha256-columns-v2",\n'
    '    "columns": {\n'
    '      "commodity_id": '
    '"28df027aaeddc17d8d0c040002ff412e988a3d2a13e2376a82524245153254c1",\n'
    '      "commodity_kind": '
    '"c81cecc64d18883ed31c96bd10cc7058c0bd07d78918f0da0e6875b263d9ae46",\n'
    '      "consumer_extra.entitlement": '
    '"20168ca3260ff438703b640a1c56fda3284c0fa6d92e9e17e43cfeacb251d8fd",\n'
    '      "consumer_extra.utility_exponent": '
    '"14b5ccca1e0776136bf746ff5b52e14f65979305577bd9a2e5d5da2e8e39fdd4",\n'
    '      "consumer_extra.utility_exponent_commodity": '
    '"db3aefa8a65d6627df6b4ef4a5e86f4c63b9eda6897ca35ef7c12c80ce523e16",\n'
    '      "consumer_group": '
    '"2c92fccf7240978a5b84e0dc5538f2084689fd1497a57862e9605c9dc381c817",\n'
    '      "consumer_id": '
    '"95eb6a95a0249bc95e630212b969d49a78077641252dafeafa45b2128830a99a",\n'
    '      "endowment": '
    '"1ca60d799f409b632fad3efe83132ee39eaf9c60e21fa410935ce6e8f03d67b4",\n'
    '      "input_coefficient": '
    '"c01213e3578c47318d8ab5b9c84de950edea9f25ef0d2d921952ded3e0f1efe0",\n'
    '      "input_commodity": '
    '"b93195bf87822b49bd88ddea615ac144ea527527dcc418cb8d55eed766f0a77b",\n'
    '      "input_offsets": '
    '"58b2fbd7c650d4fcbce9b1154ff653fedbca00ac224ea64412f2465b3d4709d3",\n'
    '      "output_commodity": '
    '"32b4621330949c8e06a4efca02ec433b7b9095d2e35076469c680b959a034f9d",\n'
    '      "period": '
    '"8113d5816eadf76f26daf54aa71f51fb07b8f9cbf01405b462591049c0c68840",\n'
    '      "technology_kind": '
    '"d59467cfb1ff5b849ed46495fd6f784854f7fff77015b3641e12d56f792f1582",\n'
    '      "technology_scale": '
    '"431009f8073d3a61dcd12a3087636368bfc55d9ee8e35da292d330cc475d9920",\n'
    '      "unit_extra.effort_c": '
    '"b9a99fc70da687533352789d4343e52dd7df53a1da91d5df8d5913eac518a0e2",\n'
    '      "unit_extra.effort_k": '
    '"74f685d2b599c87463b865c22338ce061c6e0741dabe7e51346d97386972a69f",\n'
    '      "unit_extra.effort_s": '
    '"800f44d5db17402ad4bb7efa619936200bab639ac08011ebaf19821802797ae1",\n'
    '      "unit_group": '
    '"edc992c1ba2d07cbf308aaaa18c5a91cf44d678b573217651d3f505dedf66a2e",\n'
    '      "unit_id": '
    '"8365b4d9c59b5e49a81e1f389da8763cde16eb282c649b86fad1338f2cf9f476"\n'
    '    },\n'
    '    "digest": "29361be1cba5b17c755449494aec6551acc5b6de1e39c40fed067e187316d4d0"\n'
    '  },\n'
    '  "library_version": "<LIBRARY_VERSION>",\n'
    '  "loader": {\n'
    '    "name": "load_dep1ex",\n'
    '    "parameters": {\n'
    '      "endowment": 1000.0\n'
    '    }\n'
    '  },\n'
    '  "plan_fields_absent": [\n'
    '    "provision"\n'
    '  ],\n'
    '  "procedure": {\n'
    '    "kind": "library",\n'
    '    "module": "demplan.prefabs.hahnel.book_2021",\n'
    '    "parameters": {\n'
    '      "initial_price": 700.0,\n'
    '      "initial_rule_state": null,\n'
    '      "max_rounds": 250,\n'
    '      "price_rule": null,\n'
    '      "record_trajectory": false,\n'
    '      "threshold_pct": 3.0\n'
    '    },\n'
    '    "qualname": "HahnelBook2021",\n'
    '    "source_digest": "<SOURCE_DIGEST>"\n'
    '  },\n'
    '  "seed": 17\n'
    '}\n'
)
"""The document a library without the period keys writes for :func:`single_period_arguments`,
captured from such a library.

The economy is the synthetic one from ``tests/reference/synthetic.py``, so its digests are
literal. The three placeholders are filled by :func:`expected_single_period_bytes`.
"""


def module_file_digest(module_name: str) -> str:
    """sha256 of the source file of ``module_name``, line endings read as LF."""
    raw = Path(importlib.import_module(module_name).__file__).read_bytes()
    return hashlib.sha256(raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def expected_single_period_bytes() -> bytes:
    """:data:`SINGLE_PERIOD_GOLDEN` with this checkout's versions and prefab source digest."""
    text = (
        SINGLE_PERIOD_GOLDEN.replace("<CORE_VERSION>", demplan.core_version())
        .replace("<LIBRARY_VERSION>", metadata.version("demplan"))
        .replace("<SOURCE_DIGEST>", module_file_digest(PREFAB_MODULE))
    )
    return text.encode("utf-8")


@dataclasses.dataclass(frozen=True)
class PlanStub:
    """What ``run_configuration`` reads off a plan, and nothing else."""

    absent_fields: tuple[str, ...]


def single_period_arguments(synthetic_economy) -> dict:
    """The arguments the golden document was captured with, except ``periods`` and the slots."""
    return {
        "procedure": HahnelBook2021(threshold_pct=3.0),
        "economy": synthetic_economy,
        "seed": 17,
        "loader": dict(LOADER),
        "plan": PlanStub(("provision",)),
    }


def written_bytes(config: RunConfiguration, tmp_path: Path, name: str = "doc.json") -> bytes:
    """The bytes ``config.to_json`` writes, read back from ``tmp_path / name``."""
    path = tmp_path / name
    config.to_json(path)
    return path.read_bytes()


def written_document(config: RunConfiguration, tmp_path: Path) -> dict:
    """The document ``config.to_json`` writes, parsed by ``json`` rather than by the library."""
    return json.loads(written_bytes(config, tmp_path).decode("utf-8"))


@dataclasses.dataclass(frozen=True)
class LinearGrowth:
    """An evolution law of the kind a researcher writes: a frozen dataclass outside the library."""

    rate: float = 0.02
    label: str = "linear"

    def __call__(self, economy, plan, seed):
        raise AssertionError("writing a configuration document must not call the evolution law")


@dataclasses.dataclass(frozen=True)
class WarmStartFromPlan:
    """A next-procedure slot of the kind a researcher writes."""

    threshold_pct: float = 3.0
    rounds: tuple[int, ...] = (10, 20)

    def __call__(self, previous_plan):
        raise AssertionError("writing a configuration document must not build a procedure")


def researcher_advance_function(economy, plan, seed):
    """An evolution law written as a plain function outside the library."""
    raise AssertionError("writing a configuration document must not call the evolution law")


class ResearcherProcedure:
    """A procedure outside the library, so its block carries nothing that varies by checkout."""

    def solve(self, economy, seed):
        raise AssertionError("writing a configuration document must not run the procedure")


@pytest.fixture
def economy(synthetic_economy):
    """The economy the golden document was captured with."""
    return synthetic_economy


class TestASinglePeriodDocumentIsUnchanged:
    def test_the_capture_is_what_this_checkout_would_have_written(self):
        """The fill-in values are real ones, not empty strings that would match anything."""
        expected = expected_single_period_bytes()
        assert b"<" not in expected
        assert len(module_file_digest(PREFAB_MODULE)) == 64

    def test_without_the_period_arguments_the_bytes_are_those_of_the_old_function(
        self, economy, tmp_path
    ):
        config = run_configuration(**single_period_arguments(economy))
        assert written_bytes(config, tmp_path) == expected_single_period_bytes()

    @pytest.mark.parametrize("periods", [1, np.int64(1), np.uint8(1)])
    def test_one_period_given_explicitly_writes_the_same_bytes(
        self, economy, tmp_path, periods
    ):
        config = run_configuration(**single_period_arguments(economy), periods=periods)
        assert written_bytes(config, tmp_path) == expected_single_period_bytes()

    def test_none_of_the_three_keys_is_written(self, economy, tmp_path):
        config = run_configuration(**single_period_arguments(economy), periods=1)
        document = written_document(config, tmp_path)
        assert not set(PERIOD_KEYS) & set(document)

    def test_the_fields_in_memory_hold_the_defaults(self, economy):
        config = run_configuration(**single_period_arguments(economy))
        assert config.periods == 1
        assert type(config.periods) is int
        assert config.advance is None
        assert config.next_procedure is None

    def test_the_configuration_version_stays_one(self, economy):
        assert run_configuration(**single_period_arguments(economy)).configuration_version == 1


class TestAMultiPeriodDocumentCarriesAllThreeKeys:
    def test_all_three_keys_are_written_even_when_both_slots_are_empty(self, economy, tmp_path):
        config = run_configuration(ResearcherProcedure(), economy, seed=0, periods=2)
        document = written_document(config, tmp_path)
        assert document["periods"] == 2
        assert "advance" in document
        assert "next_procedure" in document
        assert document["advance"] is None
        assert document["next_procedure"] is None

    def test_periods_is_written_as_a_json_integer(self, economy, tmp_path):
        config = run_configuration(ResearcherProcedure(), economy, seed=0, periods=3)
        path = tmp_path / "doc.json"
        config.to_json(path)
        text = path.read_text(encoding="utf-8")
        assert '\n  "periods": 3,\n' in text
        assert type(json.loads(text)["periods"]) is int

    @pytest.mark.parametrize("periods", [np.int64(4), np.uint8(4), np.int32(4)])
    def test_a_numpy_integer_is_recorded_as_a_python_integer(self, economy, tmp_path, periods):
        config = run_configuration(ResearcherProcedure(), economy, seed=0, periods=periods)
        assert config.periods == 4
        assert type(config.periods) is int
        assert written_document(config, tmp_path)["periods"] == 4

    def test_a_large_period_count_is_recorded_exactly(self, economy):
        config = run_configuration(ResearcherProcedure(), economy, seed=0, periods=10**6)
        assert config.periods == 10**6

    def test_the_rest_of_the_document_is_what_a_single_period_run_writes(
        self, economy, tmp_path
    ):
        """The period keys are added beside the others, not written in place of any."""
        single = json.loads(expected_single_period_bytes().decode("utf-8"))
        config = run_configuration(**single_period_arguments(economy), periods=5)
        document = written_document(config, tmp_path)
        assert {key: document[key] for key in single} == single
        assert set(document) == set(single) | set(PERIOD_KEYS)

    def test_the_configuration_version_stays_one(self, economy, tmp_path):
        config = run_configuration(ResearcherProcedure(), economy, seed=0, periods=2)
        assert config.configuration_version == CONFIGURATION_VERSION == 1
        assert written_document(config, tmp_path)["configuration_version"] == 1

    def test_the_other_arguments_are_still_checked(self, economy):
        with pytest.raises(ConfigurationError, match="seed"):
            run_configuration(ResearcherProcedure(), economy, seed=-1, periods=2)


class TestTheSlotsAreRecordedAsOriginBlocks:
    def test_a_library_evolution_law_gets_module_qualname_digest_and_parameters(self, economy):
        config = run_configuration(
            ResearcherProcedure(), economy, seed=0, periods=2, advance=book_2021_rule
        )
        assert config.advance == {
            "kind": "library",
            "module": PREFAB_MODULE,
            "qualname": "Book2021Rule",
            "source_digest": module_file_digest(PREFAB_MODULE),
            "parameters": {},
        }

    def test_a_library_next_procedure_gets_module_qualname_digest_and_parameters(self, economy):
        config = run_configuration(
            ResearcherProcedure(), economy, seed=0, periods=2, next_procedure=book_2021_rule
        )
        assert config.next_procedure == {
            "kind": "library",
            "module": PREFAB_MODULE,
            "qualname": "Book2021Rule",
            "source_digest": module_file_digest(PREFAB_MODULE),
            "parameters": {},
        }

    def test_a_library_function_is_recorded_under_its_own_name_without_parameters(
        self, economy
    ):
        config = run_configuration(
            ResearcherProcedure(), economy, seed=0, periods=2, next_procedure=demplan.split_seed
        )
        assert config.next_procedure == {
            "kind": "library",
            "module": "demplan.seeds",
            "qualname": "split_seed",
            "source_digest": module_file_digest("demplan.seeds"),
            "parameters": None,
        }

    def test_a_researcher_dataclass_gets_its_parameters_and_an_undeclared_origin(
        self, economy
    ):
        config = run_configuration(
            ResearcherProcedure(),
            economy,
            seed=0,
            periods=3,
            advance=LinearGrowth(rate=np.float64(0.05)),
            next_procedure=WarmStartFromPlan(),
        )
        assert config.advance == {
            "kind": "researcher",
            "declared_origin": None,
            "parameters": {"rate": 0.05, "label": "linear"},
        }
        assert config.next_procedure == {
            "kind": "researcher",
            "declared_origin": None,
            "parameters": {"threshold_pct": 3.0, "rounds": [10, 20]},
        }

    def test_a_researcher_function_gets_an_undeclared_origin_and_no_parameters(self, economy):
        config = run_configuration(
            ResearcherProcedure(), economy, seed=0, periods=2, advance=researcher_advance_function
        )
        assert config.advance == {"kind": "researcher", "declared_origin": None, "parameters": None}

    def test_each_slot_is_recorded_from_its_own_object(self, economy):
        """Two different objects in the two slots, so that a crossed wiring shows."""
        config = run_configuration(
            ResearcherProcedure(),
            economy,
            seed=0,
            periods=2,
            advance=LinearGrowth(),
            next_procedure=book_2021_rule,
        )
        assert config.advance["kind"] == "researcher"
        assert config.next_procedure["kind"] == "library"

    def test_an_empty_slot_stays_empty_when_the_other_is_filled(self, economy):
        only_advance = run_configuration(
            ResearcherProcedure(), economy, seed=0, periods=2, advance=LinearGrowth()
        )
        only_next = run_configuration(
            ResearcherProcedure(), economy, seed=0, periods=2, next_procedure=WarmStartFromPlan()
        )
        assert only_advance.next_procedure is None
        assert only_next.advance is None

    def test_the_procedure_block_is_not_affected_by_the_slots(self, economy):
        config = run_configuration(
            HahnelBook2021(), economy, seed=0, periods=2, advance=LinearGrowth()
        )
        assert config.procedure["qualname"] == "HahnelBook2021"

    def test_the_slots_are_written_into_the_file(self, economy, tmp_path):
        config = run_configuration(
            ResearcherProcedure(),
            economy,
            seed=0,
            periods=2,
            advance=LinearGrowth(),
            next_procedure=book_2021_rule,
        )
        document = written_document(config, tmp_path)
        assert document["advance"]["parameters"] == {"rate": 0.02, "label": "linear"}
        assert document["next_procedure"]["qualname"] == "Book2021Rule"

    @pytest.mark.parametrize("slot", ["advance", "next_procedure"])
    def test_a_non_finite_parameter_in_a_slot_is_refused_naming_the_slot(self, economy, slot):
        with pytest.raises(ConfigurationError, match=rf"{slot}\.parameters\.rate"):
            run_configuration(
                ResearcherProcedure(),
                economy,
                seed=0,
                periods=2,
                **{slot: LinearGrowth(rate=float("nan"))},
            )


REFUSED_PERIODS = (
    0,
    -1,
    np.int64(0),
    np.uint8(0),
    True,
    False,
    np.bool_(True),
    2.0,
    np.float64(2.0),
    "2",
    None,
)
"""Period counts :func:`demplan.run_periods` refuses, and so must the document."""


class TestPeriodsIsValidatedLikeRunPeriods:
    @pytest.mark.parametrize("periods", REFUSED_PERIODS, ids=repr)
    def test_anything_but_an_integer_of_at_least_one_is_refused(self, economy, periods):
        with pytest.raises(ConfigurationError, match="periods"):
            run_configuration(ResearcherProcedure(), economy, seed=0, periods=periods)

    @pytest.mark.parametrize("periods", REFUSED_PERIODS, ids=repr)
    def test_the_same_values_are_refused_by_run_periods(self, economy, periods):
        """The list above is the run's rule, not one written to fit the document."""
        with pytest.raises(ValueError):
            demplan.run_periods(economy, ResearcherProcedure(), periods, seed=0)

    def test_the_refusal_is_a_value_error_as_well(self, economy):
        with pytest.raises(ValueError):
            run_configuration(ResearcherProcedure(), economy, seed=0, periods=0)


class TestASinglePeriodRunRefusesTheSlots:
    @pytest.mark.parametrize("slot", ["advance", "next_procedure"])
    @pytest.mark.parametrize("periods", [None, 1, np.int64(1)], ids=repr)
    def test_a_slot_given_to_a_single_period_run_is_refused(self, economy, slot, periods):
        arguments = {slot: LinearGrowth()}
        if periods is not None:
            arguments["periods"] = periods
        with pytest.raises(ConfigurationError) as raised:
            run_configuration(ResearcherProcedure(), economy, seed=0, **arguments)
        message = str(raised.value)
        assert slot in message
        assert "single-period run never calls" in message

    def test_both_slots_are_named_when_both_are_given(self, economy):
        with pytest.raises(ConfigurationError) as raised:
            run_configuration(
                ResearcherProcedure(),
                economy,
                seed=0,
                advance=LinearGrowth(),
                next_procedure=WarmStartFromPlan(),
            )
        message = str(raised.value)
        assert "advance" in message
        assert "next_procedure" in message

    def test_a_library_object_is_refused_the_same_way(self, economy):
        with pytest.raises(ConfigurationError, match="single-period run never calls"):
            run_configuration(ResearcherProcedure(), economy, seed=0, advance=book_2021_rule)


class TestReadingDocuments:
    def write(self, tmp_path: Path, text: str) -> Path:
        """``text`` as a document file, byte for byte."""
        path = tmp_path / "configuration.json"
        path.write_bytes(text.encode("utf-8"))
        return path

    def test_a_document_without_the_keys_reads_as_a_single_period_run(self, tmp_path):
        path = self.write(tmp_path, expected_single_period_bytes().decode("utf-8"))
        loaded = RunConfiguration.from_json(path)
        assert loaded.periods == 1
        assert loaded.advance is None
        assert loaded.next_procedure is None

    def test_a_document_without_the_keys_is_written_back_byte_for_byte(self, tmp_path):
        path = self.write(tmp_path, expected_single_period_bytes().decode("utf-8"))
        loaded = RunConfiguration.from_json(path)
        assert written_bytes(loaded, tmp_path, "again.json") == expected_single_period_bytes()

    def test_an_old_document_reads_as_what_the_function_writes_now(self, economy, tmp_path):
        path = self.write(tmp_path, expected_single_period_bytes().decode("utf-8"))
        assert RunConfiguration.from_json(path) == run_configuration(
            **single_period_arguments(economy)
        )

    def test_a_one_period_document_with_the_keys_written_out_is_accepted(self, tmp_path):
        document = json.loads(expected_single_period_bytes().decode("utf-8"))
        explicit = dict(document, periods=1, advance=None, next_procedure=None)
        without = RunConfiguration.from_json(self.write(tmp_path, json.dumps(document)))
        path = tmp_path / "explicit.json"
        path.write_text(json.dumps(explicit), encoding="utf-8")
        with_keys = RunConfiguration.from_json(path)
        assert with_keys == without
        assert with_keys.periods == 1

    def test_a_multi_period_document_round_trips(self, economy, tmp_path):
        written = run_configuration(
            HahnelBook2021(),
            economy,
            seed=5,
            loader=dict(LOADER),
            plan=PlanStub(("provision",)),
            periods=7,
            advance=LinearGrowth(rate=0.1),
            next_procedure=book_2021_rule,
        )
        path = tmp_path / "configuration.json"
        written.to_json(path)
        read = RunConfiguration.from_json(path)
        assert read == written
        assert read.periods == 7
        assert read.advance == written.advance
        assert read.next_procedure == written.next_procedure

    def test_a_multi_period_document_with_empty_slots_round_trips(self, economy, tmp_path):
        written = run_configuration(ResearcherProcedure(), economy, seed=5, periods=2)
        path = tmp_path / "configuration.json"
        written.to_json(path)
        assert RunConfiguration.from_json(path) == written

    def test_a_round_tripped_document_writes_the_same_bytes_again(self, economy, tmp_path):
        written = run_configuration(
            ResearcherProcedure(),
            economy,
            seed=5,
            periods=3,
            advance=LinearGrowth(),
            next_procedure=WarmStartFromPlan(),
        )
        first = written_bytes(written, tmp_path, "first.json")
        read = RunConfiguration.from_json(tmp_path / "first.json")
        assert written_bytes(read, tmp_path, "second.json") == first

    def test_a_hand_written_multi_period_document_loads(self, tmp_path):
        path = self.write(
            tmp_path,
            json.dumps(
                {
                    "seed": 3,
                    "periods": 4,
                    "advance": {"kind": "researcher", "declared_origin": None, "parameters": None},
                    "next_procedure": None,
                }
            ),
        )
        loaded = RunConfiguration.from_json(path)
        assert loaded.periods == 4
        assert loaded.advance == {"kind": "researcher", "declared_origin": None, "parameters": None}
        assert loaded.next_procedure is None

    def test_the_defaults_of_an_empty_document_are_a_single_period_run(self, tmp_path):
        loaded = RunConfiguration.from_json(self.write(tmp_path, "{}"))
        assert (loaded.periods, loaded.advance, loaded.next_procedure) == (1, None, None)


class TestUnknownKeysAreStillRefused:
    def write(self, tmp_path: Path, document: dict) -> Path:
        """``document`` serialised by ``json`` into a document file."""
        path = tmp_path / "configuration.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_an_unknown_key_beside_the_period_keys_is_named_as_from_a_newer_library(
        self, tmp_path
    ):
        path = self.write(
            tmp_path, {"periods": 2, "advance": None, "next_procedure": None, "tolerance": 0.1}
        )
        with pytest.raises(ConfigurationError) as raised:
            RunConfiguration.from_json(path)
        message = str(raised.value)
        assert "'tolerance'" in message
        assert "newer" in message
        for key in PERIOD_KEYS:
            assert f"'{key}'" not in message

    @pytest.mark.parametrize("key", ["period", "evolution_law", "next_procedures"])
    def test_a_near_miss_of_a_period_key_is_unknown(self, tmp_path, key):
        with pytest.raises(ConfigurationError, match=rf"'{key}'"):
            RunConfiguration.from_json(self.write(tmp_path, {key: 2}))


RESEARCHER_BLOCK = {"kind": "researcher", "declared_origin": None, "parameters": None}


class TestASinglePeriodDocumentCannotCarryASlot:
    """Neither writing nor reading drops a slot of a single-period run, or carries it."""

    @pytest.mark.parametrize("slot", ["advance", "next_procedure"])
    def test_writing_a_hand_built_single_period_configuration_with_a_slot_is_refused(
        self, tmp_path, slot
    ):
        config = RunConfiguration(seed=1, periods=1, **{slot: dict(RESEARCHER_BLOCK)})
        path = tmp_path / "configuration.json"
        with pytest.raises(ConfigurationError) as raised:
            config.to_json(path)
        message = str(raised.value)
        assert slot in message
        assert "single-period run never calls" in message
        assert not path.exists()

    def test_writing_with_both_slots_names_both(self, tmp_path):
        config = RunConfiguration(
            advance=dict(RESEARCHER_BLOCK), next_procedure=dict(RESEARCHER_BLOCK)
        )
        with pytest.raises(ConfigurationError) as raised:
            config.to_json(tmp_path / "configuration.json")
        assert "advance" in str(raised.value)
        assert "next_procedure" in str(raised.value)

    def test_writing_a_multi_period_configuration_with_slots_is_accepted(self, tmp_path):
        config = RunConfiguration(
            periods=2, advance=dict(RESEARCHER_BLOCK), next_procedure=dict(RESEARCHER_BLOCK)
        )
        path = tmp_path / "configuration.json"
        config.to_json(path)
        assert json.loads(path.read_text(encoding="utf-8"))["advance"] == RESEARCHER_BLOCK

    @pytest.mark.parametrize("slot", ["advance", "next_procedure"])
    @pytest.mark.parametrize("periods_key", [{"periods": 1}, {}], ids=["explicit", "absent"])
    def test_reading_a_single_period_document_with_a_slot_is_refused(
        self, tmp_path, slot, periods_key
    ):
        path = tmp_path / "configuration.json"
        document = {"seed": 1, **periods_key, slot: dict(RESEARCHER_BLOCK)}
        path.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(ConfigurationError) as raised:
            RunConfiguration.from_json(path)
        message = str(raised.value)
        assert slot in message
        assert "single-period run never calls" in message

    def test_reading_a_single_period_document_with_null_slots_is_accepted(self, tmp_path):
        path = tmp_path / "configuration.json"
        path.write_text(
            json.dumps({"periods": 1, "advance": None, "next_procedure": None}), encoding="utf-8"
        )
        assert RunConfiguration.from_json(path) == RunConfiguration()


class TestReadingValidatesPeriods:
    @pytest.mark.parametrize(
        "periods", [True, False, 0, -1, "3", 2.0, 1.0, None, [2], {"n": 2}], ids=repr
    )
    def test_a_period_count_the_run_would_refuse_is_refused_on_reading(self, tmp_path, periods):
        path = tmp_path / "configuration.json"
        path.write_text(json.dumps({"seed": 1, "periods": periods}), encoding="utf-8")
        with pytest.raises(ConfigurationError, match="periods"):
            RunConfiguration.from_json(path)

    @pytest.mark.parametrize("periods", [1, 2, 250])
    def test_an_integer_of_at_least_one_is_read_as_that_integer(self, tmp_path, periods):
        path = tmp_path / "configuration.json"
        path.write_text(json.dumps({"periods": periods}), encoding="utf-8")
        loaded = RunConfiguration.from_json(path)
        assert loaded.periods == periods
        assert type(loaded.periods) is int
