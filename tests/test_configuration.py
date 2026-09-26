"""The run configuration document, and the content digest of an economy.

The digest is the part of this module worth attacking. A digest that is computed but does not
cover what it claims to cover looks exactly like a working one: it returns a hex string, it
changes when the obvious column changes, and it stays silent about the column it never read.
So the coverage tests here are one per column rather than one for the economy as a whole, and
each one asserts that the other columns' digests stayed put, which is what tells a missed
column apart from a smeared one.

Several tests build a small dataclass of their own instead of an ``Economy``. ``Economy``
fixes the dtype and the rank of every column it holds, so nothing built from it can vary a
column's dtype, its shape or its name while holding the bytes constant, and those three are
exactly what the preimage has to carry for two different columns not to collide.

The version rules are attacked the same way. Their whole value is in telling a document from
a newer library apart from a document naming a setting this library has removed, so the tests
assert on the wording of each message, not on the exception type.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib
import importlib.metadata as metadata
import inspect
import json
import sys
import types
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pytest

import demplan
from demplan import Economy
from demplan import configuration
from demplan.configuration import (
    CONFIGURATION_VERSION,
    ECONOMY_DIGEST_ALGORITHM,
    RETIRED_KEYS,
    ConfigurationError,
    RetiredKey,
    EconomyDigestReport,
    RunConfiguration,
    compare_economy_digests,
    economy_digest,
    run_configuration,
)
from demplan.prefabs.hahnel import HahnelBook2021, book_2021_rule

DEFAULTS_BASELINE = Path(__file__).resolve().parent / "run_configuration_defaults.json"

PREFAB_MODULE = "demplan.prefabs.hahnel.book_2021"

FIELD_COLUMNS = (
    "period",
    "commodity_id",
    "commodity_kind",
    "endowment",
    "unit_id",
    "unit_group",
    "output_commodity",
    "technology_kind",
    "technology_scale",
    "input_offsets",
    "input_commodity",
    "input_coefficient",
    "consumer_id",
    "consumer_group",
)
"""Every field of ``Economy`` that is not one of the three ``extra`` bags.

Written out rather than derived from ``dataclasses.fields``: a list derived from the same
place the digest derives its own would agree with a digest that covers nothing. A field added
to ``Economy`` turns this list red, which is the point at which somebody has to decide
whether the digest algorithm's version number has to move.
"""

BAG_COLUMNS = (
    "commodity_extra.scarcity",
    "unit_extra.effort_c",
    "unit_extra.effort_k",
    "unit_extra.effort_s",
    "consumer_extra.entitlement",
    "consumer_extra.utility_exponent",
    "consumer_extra.utility_exponent_commodity",
)
"""The keys the test economy carries in its three bags, under the prefix each bag gets."""

ALL_COLUMNS = FIELD_COLUMNS + BAG_COLUMNS

SINGLE_PERIOD_OMITTED_KEYS = ("periods", "advance", "next_procedure")
"""The keys a single-period document leaves out. ``tests/test_configuration_periods.py``
covers them."""


@pytest.fixture
def economy(synthetic_economy) -> Economy:
    """The synthetic economy with one key in every bag, ``commodity_extra`` included.

    The synthetic economy leaves ``commodity_extra`` empty, and an empty bag cannot show
    whether the digest reads that bag at all.
    """
    scarcity = np.linspace(0.5, 2.0, synthetic_economy.n_commodities)
    return dataclasses.replace(synthetic_economy, commodity_extra={"scarcity": scarcity})


def with_column(subject, name: str, value):
    """A copy of ``subject`` whose ``name`` holds ``value``, built without revalidating.

    Three of the columns are row numberings and two more are checked against each other, so
    no valid economy differs from another in one of those columns alone. The digest is a
    function of the arrays whether they are valid or not, and a copy that skips
    ``__post_init__`` is the only way to vary each column one at a time.
    """
    clone = copy.copy(subject)
    object.__setattr__(clone, name, value)
    return clone


def bumped(value):
    """``value`` with its first entry moved, keeping dtype, shape and length."""
    if isinstance(value, np.ndarray):
        changed = np.array(value, copy=True)
        changed.reshape(-1)[0] += 1
        return changed
    return value + 1


def mutated(economy: Economy, column: str) -> Economy:
    """A copy of ``economy`` in which exactly one column, bag keys included, has moved."""
    bag, _, key = column.partition(".")
    if not key:
        return with_column(economy, column, bumped(getattr(economy, column)))
    contents = dict(getattr(economy, bag))
    contents[key] = bumped(contents[key])
    return with_column(economy, bag, contents)


@dataclasses.dataclass(frozen=True)
class TwoColumns:
    """A stand-in for an economy: two named columns and nothing else."""

    a: np.ndarray
    b: np.ndarray


@dataclasses.dataclass(frozen=True)
class ThreeColumns:
    """A stand-in carrying a column ``Economy`` does not have, and a bag."""

    a: np.ndarray
    b: np.ndarray
    c: np.ndarray
    bag: dict = dataclasses.field(default_factory=dict)


class ResearcherProcedure:
    """A coordination procedure of the kind a researcher writes: outside the library."""

    def solve(self, economy, seed):
        raise AssertionError("writing a configuration document must not run the procedure")


class Impostor:
    """A procedure whose module starts with the library's name but is not in the library."""

    def solve(self, economy, seed):
        raise AssertionError("writing a configuration document must not run the procedure")


Impostor.__module__ = "demplanx.impostor"


@dataclasses.dataclass(frozen=True)
class LibraryLikeProcedure:
    """A dataclass procedure that claims a library module, to reach the library branch.

    ``HahnelBook2021`` is the only procedure the library ships, and every one of its
    defaults is a JSON scalar. The parameter rules also cover values that are not, so this
    one borrows a library module name and carries an array and a callable.
    """

    threshold: float = 5.0
    label: str = "borrowed"
    enabled: bool = True
    absent: object = None
    weights: np.ndarray = dataclasses.field(
        default_factory=lambda: np.array([1.0, 2.0], dtype=np.float64)
    )
    rule: object = None

    def solve(self, economy, seed):
        raise AssertionError("writing a configuration document must not run the procedure")


LibraryLikeProcedure.__module__ = "demplan.configuration"


@dataclasses.dataclass(frozen=True)
class ResearcherDataclassProcedure:
    """The common case: a procedure a researcher wrote, holding parameters as a dataclass.

    His code is not digested, because his version control is a better record of it than a
    digest taken here. His parameters are data rather than code, and the document is worth
    nothing to him if it cannot carry them.
    """

    threshold: float = 0.02
    label: str = "mine"
    weights: np.ndarray = dataclasses.field(
        default_factory=lambda: np.array([1.0, 2.0], dtype=np.float64)
    )
    rule: object = None

    def solve(self, economy, seed):
        raise AssertionError("writing a configuration document must not run the procedure")


@dataclasses.dataclass(frozen=True)
class NestedRule:
    """A parameter that is itself a dataclass, to exercise a nested parameter path."""

    tolerance: float = 0.5


NestedRule.__module__ = "demplan.configuration"


@dataclasses.dataclass(frozen=True)
class PlanStub:
    """What ``run_configuration`` reads off a plan, and nothing else."""

    absent_fields: tuple[str, ...]


def module_file_digest(module_name: str) -> str:
    """sha256 of the source file of ``module_name``, with its line endings normalised.

    ``TestSourceDigestLineEndings`` is what pins the normalisation itself. This helper
    only has to reach the same answer for a file already in the checkout, whose line
    endings depend on how git wrote it out.
    """
    path = Path(importlib.import_module(module_name).__file__)
    raw = path.read_bytes()
    source = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(source).hexdigest()


class TestEconomyDigestShape:
    def test_the_block_carries_the_algorithm_the_digest_and_the_columns(self, economy):
        block = economy_digest(economy)
        assert set(block) == {"algorithm", "digest", "columns"}

    def test_the_algorithm_is_named_and_versioned(self, economy):
        assert economy_digest(economy)["algorithm"] == "sha256-columns-v2"
        assert ECONOMY_DIGEST_ALGORITHM == "sha256-columns-v2"

    def test_every_digest_is_sha256_in_lower_case_hex(self, economy):
        block = economy_digest(economy)
        for value in [block["digest"], *block["columns"].values()]:
            assert len(value) == 64
            assert set(value) <= set("0123456789abcdef")

    def test_the_columns_are_exactly_the_fields_and_the_bag_keys(self, economy):
        assert sorted(economy_digest(economy)["columns"]) == sorted(ALL_COLUMNS)

    def test_a_bag_key_is_prefixed_with_the_name_of_its_bag(self, economy):
        columns = economy_digest(economy)["columns"]
        assert "commodity_extra.scarcity" in columns
        assert "scarcity" not in columns

    def test_the_column_list_follows_the_dataclass_rather_than_a_fixed_list(self):
        """A column ``Economy`` does not have still gets a digest.

        The failure this guards against is a hard-coded list of column names, which would
        leave a column added to ``Economy`` out of the digest while the digest went on
        looking like it worked.
        """
        subject = ThreeColumns(
            a=np.arange(2, dtype=np.int64),
            b=np.arange(2, dtype=np.int64),
            c=np.arange(2, dtype=np.int64),
            bag={"extra_key": np.arange(2, dtype=np.int64)},
        )
        assert sorted(economy_digest(subject)["columns"]) == ["a", "b", "bag.extra_key", "c"]

    def test_the_whole_digest_is_the_column_digests_in_name_order(self, economy):
        block = economy_digest(economy)
        joined = "".join(block["columns"][name] for name in sorted(block["columns"]))
        assert block["digest"] == hashlib.sha256(joined.encode("ascii")).hexdigest()

    def test_the_same_economy_digests_the_same_twice(self, economy):
        assert economy_digest(economy) == economy_digest(economy)

    def test_two_economies_holding_equal_arrays_agree(self, synthetic_economy):
        other = dataclasses.replace(synthetic_economy)
        assert economy_digest(synthetic_economy) == economy_digest(other)


class TestEveryColumnIsCovered:
    """One test per column: move that column, and only that column's digest may move.

    A single test on the whole-economy digest is blind to a missed column, because the
    columns it does read carry it to a passing assertion.
    """

    @pytest.mark.parametrize("column", ALL_COLUMNS)
    def test_moving_a_column_moves_its_own_digest(self, economy, column):
        before = economy_digest(economy)["columns"]
        after = economy_digest(mutated(economy, column))["columns"]
        assert before[column] != after[column]

    @pytest.mark.parametrize("column", ALL_COLUMNS)
    def test_moving_a_column_moves_the_whole_digest(self, economy, column):
        moved = economy_digest(mutated(economy, column))
        assert economy_digest(economy)["digest"] != moved["digest"]

    @pytest.mark.parametrize("column", ALL_COLUMNS)
    def test_moving_a_column_leaves_the_others_alone(self, economy, column):
        before = economy_digest(economy)["columns"]
        after = economy_digest(mutated(economy, column))["columns"]
        untouched = {name: digest for name, digest in before.items() if name != column}
        assert {name: after[name] for name in untouched} == untouched


class TestNormalisation:
    """What the digest must ignore, and what it must not."""

    def test_byte_order_is_normalised_to_little_endian(self):
        big = TwoColumns(a=np.arange(4, dtype=">i8"), b=np.zeros(2, dtype=np.float64))
        little = TwoColumns(a=np.arange(4, dtype="<i8"), b=np.zeros(2, dtype=np.float64))
        assert economy_digest(big) == economy_digest(little)

    def test_a_non_contiguous_column_digests_as_its_contiguous_twin(self):
        strided = TwoColumns(
            a=np.arange(8, dtype=np.int64)[::2], b=np.zeros(2, dtype=np.float64)
        )
        packed = TwoColumns(
            a=np.array([0, 2, 4, 6], dtype=np.int64), b=np.zeros(2, dtype=np.float64)
        )
        assert economy_digest(strided) == economy_digest(packed)

    def test_the_dtype_is_part_of_the_preimage(self):
        floats = np.array([1.5, 2.5], dtype=np.float64)
        integers = floats.view(np.int64)
        assert floats.tobytes() == integers.tobytes()
        as_floats = economy_digest(TwoColumns(a=floats, b=floats))["columns"]["a"]
        as_integers = economy_digest(TwoColumns(a=integers, b=floats))["columns"]["a"]
        assert as_floats != as_integers

    def test_the_shape_is_part_of_the_preimage(self):
        flat = np.arange(6, dtype=np.int64)
        square = flat.reshape(2, 3)
        assert flat.tobytes() == square.tobytes()
        as_flat = economy_digest(TwoColumns(a=flat, b=flat))["columns"]["a"]
        as_square = economy_digest(TwoColumns(a=square, b=flat))["columns"]["a"]
        assert as_flat != as_square

    def test_the_column_name_is_part_of_the_preimage(self):
        shared = np.arange(4, dtype=np.int64)
        columns = economy_digest(TwoColumns(a=shared, b=shared))["columns"]
        assert columns["a"] != columns["b"]

    def test_swapping_two_columns_changes_the_whole_digest(self):
        first = np.array([1, 2], dtype=np.int64)
        second = np.array([3, 4], dtype=np.int64)
        straight = economy_digest(TwoColumns(a=first, b=second))["digest"]
        swapped = economy_digest(TwoColumns(a=second, b=first))["digest"]
        assert straight != swapped

    def test_the_period_is_covered_although_it_is_not_an_array(self, economy):
        later = with_column(economy, "period", economy.period + 1)
        assert economy_digest(economy)["digest"] != economy_digest(later)["digest"]


class TestTopLevelKeys:
    def test_the_document_carries_exactly_these_keys(self, economy):
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert {field.name for field in dataclasses.fields(config)} == {
            "configuration_version",
            "library_version",
            "core_version",
            "seed",
            "economy",
            "procedure",
            "loader",
            "plan_fields_absent",
            "periods",
            "advance",
            "next_procedure",
        }

    def test_the_configuration_version_is_one(self, economy):
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert config.configuration_version == 1
        assert CONFIGURATION_VERSION == 1

    def test_the_library_version_comes_from_the_installed_distribution(self, economy):
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert config.library_version == metadata.version("demplan")

    def test_an_uninstalled_library_records_an_unknown_version(self, economy, monkeypatch):
        def missing(name):
            raise metadata.PackageNotFoundError(name)

        monkeypatch.setattr(configuration.metadata, "version", missing)
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert config.library_version == "unknown"

    def test_the_core_version_is_recorded_beside_it(self, economy):
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert config.core_version == demplan.core_version()

    def test_the_seed_is_recorded(self, economy):
        assert run_configuration(ResearcherProcedure(), economy, seed=4242).seed == 4242

    def test_a_numpy_seed_is_recorded_as_a_python_integer(self, economy):
        config = run_configuration(ResearcherProcedure(), economy, seed=np.int64(9))
        assert config.seed == 9
        assert type(config.seed) is int

    @pytest.mark.parametrize("seed", [-1, 1 << 64])
    def test_a_seed_outside_the_64_bit_range_is_refused(self, economy, seed):
        with pytest.raises(ConfigurationError, match="seed"):
            run_configuration(ResearcherProcedure(), economy, seed=seed)

    def test_a_seed_that_is_not_an_integer_is_refused(self, economy):
        with pytest.raises(ConfigurationError, match="seed"):
            run_configuration(ResearcherProcedure(), economy, seed="0")

    def test_the_economy_block_is_the_content_digest(self, economy):
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert config.economy == economy_digest(economy)


class TestProcedureBlock:
    def test_a_library_procedure_is_recorded_with_its_module_and_source(self, economy):
        config = run_configuration(HahnelBook2021(), economy, seed=0)
        assert config.procedure["kind"] == "library"
        assert config.procedure["module"] == PREFAB_MODULE
        assert config.procedure["qualname"] == "HahnelBook2021"
        assert set(config.procedure) == {
            "kind",
            "module",
            "qualname",
            "source_digest",
            "parameters",
        }

    def test_the_source_digest_is_the_whole_module_file(self, economy):
        config = run_configuration(HahnelBook2021(), economy, seed=0)
        assert config.procedure["source_digest"] == module_file_digest(PREFAB_MODULE)

    def test_the_source_digest_is_not_the_source_of_the_class_alone(self, economy):
        """Module-level constants decide behaviour as much as the class body does."""
        config = run_configuration(HahnelBook2021(), economy, seed=0)
        class_source = inspect.getsource(HahnelBook2021).encode("utf-8")
        assert config.procedure["source_digest"] != hashlib.sha256(class_source).hexdigest()

    def test_the_source_digest_is_not_some_other_library_file(self, economy):
        config = run_configuration(HahnelBook2021(), economy, seed=0)
        assert config.procedure["source_digest"] != module_file_digest("demplan.seeds")

    def test_a_researcher_procedure_records_an_undeclared_origin(self, economy):
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert config.procedure == {
            "kind": "researcher",
            "declared_origin": None,
            "parameters": None,
        }

    def test_the_undeclared_origin_key_is_present_rather_than_omitted(self, economy):
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert "declared_origin" in config.procedure

    def test_a_module_merely_starting_with_the_name_is_not_the_library(self, economy):
        """The test is on ``demplan.``, dot included, so ``demplanx`` is outside."""
        config = run_configuration(Impostor(), economy, seed=0)
        assert config.procedure["kind"] == "researcher"

    def test_the_procedure_is_never_solved(self, economy):
        run_configuration(ResearcherProcedure(), economy, seed=0)


class TestParameters:
    def test_a_dataclass_procedure_records_its_fields(self, economy):
        config = run_configuration(HahnelBook2021(threshold_pct=3.0), economy, seed=0)
        assert config.procedure["parameters"] == {
            "threshold_pct": 3.0,
            "max_rounds": 250,
            "initial_price": 700.0,
            "initial_rule_state": None,
            "record_trajectory": False,
            "price_rule": None,
        }

    def test_a_procedure_that_is_not_a_dataclass_records_no_parameters(self, economy):
        class Plain:
            def solve(self, economy, seed):
                raise AssertionError("never run")

        Plain.__module__ = "demplan.configuration"
        config = run_configuration(Plain(), economy, seed=0)
        assert config.procedure["parameters"] is None

    def test_json_scalars_are_recorded_as_they_are(self, economy):
        config = run_configuration(LibraryLikeProcedure(), economy, seed=0)
        parameters = config.procedure["parameters"]
        assert parameters["threshold"] == 5.0
        assert parameters["label"] == "borrowed"
        assert parameters["enabled"] is True
        assert parameters["absent"] is None

    def test_an_array_parameter_falls_to_the_undeclared_form(self, economy):
        config = run_configuration(LibraryLikeProcedure(), economy, seed=0)
        assert config.procedure["parameters"]["weights"] == {
            "kind": "researcher",
            "declared_origin": None,
            "parameters": None,
        }

    def test_a_library_callable_parameter_is_recorded_like_a_library_procedure(self, economy):
        config = run_configuration(
            LibraryLikeProcedure(rule=book_2021_rule), economy, seed=0
        )
        rule = config.procedure["parameters"]["rule"]
        assert rule["kind"] == "library"
        assert rule["module"] == PREFAB_MODULE
        assert rule["qualname"] == "Book2021Rule"
        assert rule["source_digest"] == module_file_digest(PREFAB_MODULE)

    def test_a_researcher_callable_parameter_falls_to_the_undeclared_form(self, economy):
        def own_rule(price, surplus, imbalance):
            raise AssertionError("never called")

        config = run_configuration(LibraryLikeProcedure(rule=own_rule), economy, seed=0)
        assert config.procedure["parameters"]["rule"] == {
            "kind": "researcher",
            "declared_origin": None,
            "parameters": None,
        }


class TestLoaderBlock:
    def test_no_loader_is_recorded_as_null(self, economy):
        assert run_configuration(ResearcherProcedure(), economy, seed=0).loader is None

    def test_a_declared_loader_is_recorded_as_given(self, economy):
        declared = {"name": "load_dep1ex", "parameters": {"endowment": 1000.0}}
        config = run_configuration(ResearcherProcedure(), economy, seed=0, loader=declared)
        assert config.loader == declared

    def test_a_loader_that_is_not_a_mapping_is_refused(self, economy):
        with pytest.raises(ConfigurationError, match="loader"):
            run_configuration(ResearcherProcedure(), economy, seed=0, loader="load_dep1ex")

    def test_a_loader_that_json_cannot_hold_is_refused(self, economy):
        with pytest.raises(ConfigurationError, match="loader"):
            run_configuration(
                ResearcherProcedure(), economy, seed=0, loader={"array": np.zeros(3)}
            )


class TestPlanFieldsAbsent:
    def test_no_plan_is_recorded_as_null(self, economy):
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert config.plan_fields_absent is None

    def test_the_absent_fields_are_taken_off_the_plan(self, economy):
        plan = PlanStub(absent_fields=("consumption", "provision"))
        config = run_configuration(ResearcherProcedure(), economy, seed=0, plan=plan)
        assert config.plan_fields_absent == ("consumption", "provision")

    def test_an_empty_tuple_is_kept_apart_from_no_plan_at_all(self, economy):
        plan = PlanStub(absent_fields=())
        config = run_configuration(ResearcherProcedure(), economy, seed=0, plan=plan)
        assert config.plan_fields_absent == ()

    def test_an_object_without_absent_fields_is_refused(self, economy):
        with pytest.raises(ConfigurationError, match="absent_fields"):
            run_configuration(ResearcherProcedure(), economy, seed=0, plan=object())

    def test_field_names_that_are_not_strings_are_refused(self, economy):
        with pytest.raises(ConfigurationError, match="absent_fields"):
            run_configuration(
                ResearcherProcedure(), economy, seed=0, plan=PlanStub(absent_fields=(3,))
            )

    def test_the_module_does_not_import_the_plan_type(self):
        """The document records what the researcher declared; it does not check his plan."""
        source = Path(configuration.__file__).read_text(encoding="utf-8")
        assert "demplan.plan" not in source


class TestJsonFile:
    @pytest.fixture
    def config(self, economy):
        return run_configuration(
            HahnelBook2021(),
            economy,
            seed=17,
            loader={"name": "load_dep1ex", "parameters": {"endowment": 1000.0}},
            plan=PlanStub(absent_fields=("provision",)),
        )

    def test_a_document_reads_back_as_what_was_written(self, config, tmp_path):
        path = tmp_path / "configuration.json"
        config.to_json(path)
        assert RunConfiguration.from_json(path) == config

    def test_the_file_is_utf_8_json_with_keys_in_order_and_two_space_indent(
        self, config, tmp_path
    ):
        path = tmp_path / "configuration.json"
        config.to_json(path)
        text = path.read_text(encoding="utf-8")
        keys = [key for key, _ in json.loads(text, object_pairs_hook=lambda pairs: pairs)]
        assert keys == sorted(keys)
        assert '\n  "configuration_version": 1' in text

    def test_the_absent_fields_are_a_list_in_the_file_and_a_tuple_in_memory(
        self, config, tmp_path
    ):
        path = tmp_path / "configuration.json"
        config.to_json(path)
        assert json.loads(path.read_text(encoding="utf-8"))["plan_fields_absent"] == [
            "provision"
        ]
        assert RunConfiguration.from_json(path).plan_fields_absent == ("provision",)

    def test_a_document_that_is_not_an_object_is_refused(self, tmp_path):
        path = tmp_path / "configuration.json"
        path.write_text("[1, 2]", encoding="utf-8")
        with pytest.raises(ConfigurationError):
            RunConfiguration.from_json(path)


class TestVersionRules:
    def write(self, tmp_path, document) -> Path:
        path = tmp_path / "configuration.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_a_key_the_library_knows_is_used(self, tmp_path):
        path = self.write(tmp_path, {"seed": 11})
        assert RunConfiguration.from_json(path).seed == 11

    def test_a_missing_key_falls_back_to_its_default(self, tmp_path):
        path = self.write(tmp_path, {"seed": 11})
        loaded = RunConfiguration.from_json(path)
        assert loaded.loader is None
        assert loaded.configuration_version == CONFIGURATION_VERSION

    def test_an_empty_document_loads_as_the_defaults(self, tmp_path):
        path = self.write(tmp_path, {})
        assert RunConfiguration.from_json(path) == RunConfiguration()

    def test_an_unknown_key_says_the_document_needs_a_newer_library(self, tmp_path):
        path = self.write(tmp_path, {"tolerance": 0.01})
        with pytest.raises(ConfigurationError) as raised:
            RunConfiguration.from_json(path)
        message = str(raised.value)
        assert "tolerance" in message
        assert "newer" in message
        assert "no longer exists" not in message

    def test_a_retired_key_says_the_setting_is_gone_and_when_it_went(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setitem(
            RETIRED_KEYS,
            "tolerance",
            RetiredKey(removed_in="0.4.0", reason="the convergence test moved onto Plan"),
        )
        path = self.write(tmp_path, {"tolerance": 0.01})
        with pytest.raises(ConfigurationError) as raised:
            RunConfiguration.from_json(path)
        message = str(raised.value)
        assert "no longer exists" in message
        assert "0.4.0" in message
        assert "the convergence test moved onto Plan" in message
        assert "newer" not in message

    def test_the_two_causes_do_not_share_a_message(self, tmp_path, monkeypatch):
        unknown_path = self.write(tmp_path, {"tolerance": 0.01})
        with pytest.raises(ConfigurationError) as unknown:
            RunConfiguration.from_json(unknown_path)

        monkeypatch.setitem(
            RETIRED_KEYS, "tolerance", RetiredKey(removed_in="0.4.0", reason="it moved")
        )
        with pytest.raises(ConfigurationError) as retired:
            RunConfiguration.from_json(unknown_path)

        assert str(unknown.value) != str(retired.value)

    def test_the_retired_register_is_empty_in_this_version(self):
        assert RETIRED_KEYS == {}

    def test_a_retired_key_carries_the_version_and_the_reason(self):
        entry = RetiredKey(removed_in="0.4.0", reason="it moved")
        assert entry.removed_in == "0.4.0"
        assert entry.reason == "it moved"


class TestDefaultsBaseline:
    """The defaults are compared with a file in the repository, not with themselves.

    A new key whose default changes behaviour is the failure this guards against: an old
    document fed to a new library would load without complaint and run a different setting.
    Turning this test red is the point at which somebody has to say so out loud.
    """

    def test_the_defaults_match_the_baseline_in_the_repository(self, tmp_path):
        path = tmp_path / "defaults.json"
        RunConfiguration().to_json(path)
        written = json.loads(path.read_text(encoding="utf-8"))
        baseline = json.loads(DEFAULTS_BASELINE.read_text(encoding="utf-8"))
        assert written == baseline

    def test_the_baseline_covers_every_key_a_default_document_writes(self):
        """A default document is a single-period run, which writes no period keys."""
        baseline = json.loads(DEFAULTS_BASELINE.read_text(encoding="utf-8"))
        every_field = {field.name for field in dataclasses.fields(RunConfiguration)}
        assert set(baseline) == every_field - set(SINGLE_PERIOD_OMITTED_KEYS)

    def test_the_keys_a_default_document_omits_default_to_a_single_period_run(self):
        """The baseline cannot pin these, since the file never holds them; this does."""
        defaults = RunConfiguration()
        assert {key: getattr(defaults, key) for key in SINGLE_PERIOD_OMITTED_KEYS} == {
            "periods": 1,
            "advance": None,
            "next_procedure": None,
        }

    def test_the_baseline_reads_back_as_the_defaults(self):
        assert RunConfiguration.from_json(DEFAULTS_BASELINE) == RunConfiguration()


class TestResearcherParameters:
    """A researcher's parameters are recorded; his code is still not digested.

    The rule against digesting his code comes from his having version control of it. That
    argument does not reach his parameters, which are data the library can read off a
    dataclass exactly as it reads off its own, and which are what a rerun needs.
    """

    def test_a_researcher_dataclass_records_its_fields(self, economy):
        config = run_configuration(ResearcherDataclassProcedure(), economy, seed=0)
        parameters = config.procedure["parameters"]
        assert parameters["threshold"] == 0.02
        assert parameters["label"] == "mine"

    def test_a_researcher_procedure_that_is_not_a_dataclass_records_no_parameters(
        self, economy
    ):
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert config.procedure["parameters"] is None

    def test_the_researcher_block_carries_exactly_three_keys(self, economy):
        config = run_configuration(ResearcherDataclassProcedure(), economy, seed=0)
        assert set(config.procedure) == {"kind", "declared_origin", "parameters"}

    def test_the_researcher_block_carries_no_source_digest(self, economy):
        config = run_configuration(ResearcherDataclassProcedure(), economy, seed=0)
        assert "source_digest" not in config.procedure

    def test_a_library_callable_inside_a_researcher_procedure_is_still_pinned(self, economy):
        config = run_configuration(
            ResearcherDataclassProcedure(rule=book_2021_rule), economy, seed=0
        )
        rule = config.procedure["parameters"]["rule"]
        assert rule["kind"] == "library"
        assert rule["source_digest"] == module_file_digest(PREFAB_MODULE)

    def test_an_array_parameter_of_a_researcher_procedure_is_undeclared(self, economy):
        config = run_configuration(ResearcherDataclassProcedure(), economy, seed=0)
        assert config.procedure["parameters"]["weights"] == {
            "kind": "researcher",
            "declared_origin": None,
            "parameters": None,
        }

    def test_the_two_kinds_follow_the_same_parameter_rules(self, economy):
        """The only difference between the two blocks is what the library can pin down."""
        library = run_configuration(LibraryLikeProcedure(), economy, seed=0).procedure
        researcher = run_configuration(
            ResearcherDataclassProcedure(), economy, seed=0
        ).procedure
        assert set(library["parameters"]) == {
            "threshold",
            "label",
            "enabled",
            "absent",
            "weights",
            "rule",
        }
        assert set(researcher["parameters"]) == {"threshold", "label", "weights", "rule"}
        assert library["parameters"]["weights"] == researcher["parameters"]["weights"]


class TestDigestComparison:
    """Which column moved, not merely that something did.

    The per-column digests exist to make a mismatch diagnosable: a researcher reading
    "``input_coefficient`` differs, the other twenty agree" can tell a loader that drifted
    from a different data set, and "the two economies differ" tells him nothing at all.

    The comparison hands back a report rather than raising, on the pattern of
    ``check_determinism``: whether two economies count as the same one is the researcher's
    judgement, and the library's job is to say exactly where they part. The one refusal left
    is two digests taken under different algorithms, which is not a judgement anybody can
    make: figures from two different normalisations are not comparable at all.
    """

    def differing(self, economy, *columns):
        """The digest of ``economy`` with each of ``columns`` moved."""
        moved = economy
        for column in columns:
            moved = mutated(moved, column)
        return economy_digest(moved)

    def test_a_digest_matches_itself(self, economy):
        report = compare_economy_digests(economy_digest(economy), economy_digest(economy))
        assert isinstance(report, EconomyDigestReport)
        assert report.identical
        assert report.differing_columns == []
        assert report.only_in_recorded == []
        assert report.only_in_current == []
        assert not report.digest_contradicts_columns

    def test_a_match_lists_every_column_as_matching(self, economy):
        report = compare_economy_digests(economy_digest(economy), economy_digest(economy))
        assert sorted(report.matching_columns) == sorted(ALL_COLUMNS)

    def test_one_differing_column_is_named(self, economy):
        report = compare_economy_digests(
            economy_digest(economy), self.differing(economy, "input_coefficient")
        )
        assert report.identical is False
        assert report.differing_columns == ["input_coefficient"]

    def test_every_differing_column_is_named(self, economy):
        moved = ("period", "endowment", "unit_extra.effort_c")
        report = compare_economy_digests(
            economy_digest(economy), self.differing(economy, *moved)
        )
        assert sorted(report.differing_columns) == sorted(moved)

    def test_the_columns_that_agree_are_kept_apart_from_the_one_that_did_not(self, economy):
        report = compare_economy_digests(
            economy_digest(economy), self.differing(economy, "period")
        )
        for column in ("endowment", "technology_scale", "consumer_extra.entitlement"):
            assert column in report.matching_columns
            assert column not in report.differing_columns

    def test_how_many_columns_agree_is_stated(self, economy):
        report = compare_economy_digests(
            economy_digest(economy), self.differing(economy, "period")
        )
        assert len(report.matching_columns) == len(ALL_COLUMNS) - 1

    def test_a_column_only_one_side_carries_is_reported(self, economy):
        recorded = economy_digest(economy)
        current = economy_digest(economy)
        del current["columns"]["commodity_extra.scarcity"]
        report = compare_economy_digests(recorded, current)
        assert report.identical is False
        assert report.only_in_recorded == ["commodity_extra.scarcity"]
        assert report.only_in_current == []

    def test_a_column_only_the_economy_at_hand_carries_is_reported(self, economy):
        recorded = economy_digest(economy)
        current = economy_digest(economy)
        current["columns"]["commodity_extra.newcomer"] = "0" * 64
        report = compare_economy_digests(recorded, current)
        assert report.only_in_current == ["commodity_extra.newcomer"]
        assert report.identical is False

    def test_two_digests_under_different_algorithms_are_refused(self, economy):
        """Not a judgement to hand back: two normalisations produce incomparable figures."""
        recorded = economy_digest(economy)
        current = dict(economy_digest(economy), algorithm="sha256-columns-v1")
        with pytest.raises(ConfigurationError) as raised:
            compare_economy_digests(recorded, current)
        message = str(raised.value)
        assert "sha256-columns-v1" in message
        assert "sha256-columns-v2" in message

    def test_a_whole_digest_that_contradicts_its_columns_is_reported(self, economy):
        recorded = economy_digest(economy)
        current = dict(economy_digest(economy), digest="0" * 64)
        report = compare_economy_digests(recorded, current)
        assert report.digest_contradicts_columns
        assert report.identical is False
        assert report.differing_columns == []


class TestConfigurationVersion:
    def write(self, tmp_path, document) -> Path:
        path = tmp_path / "configuration.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_a_newer_configuration_version_is_refused(self, tmp_path):
        """A bumped version with the same keys would otherwise load as if nothing changed."""
        path = self.write(tmp_path, {"configuration_version": CONFIGURATION_VERSION + 1})
        with pytest.raises(ConfigurationError) as raised:
            RunConfiguration.from_json(path)
        message = str(raised.value)
        assert "configuration_version" in message
        assert "newer" in message

    def test_an_older_configuration_version_still_loads(self, tmp_path):
        path = self.write(tmp_path, {"configuration_version": 0, "seed": 3})
        loaded = RunConfiguration.from_json(path)
        assert loaded.configuration_version == 0
        assert loaded.seed == 3

    def test_the_version_this_library_writes_loads(self, tmp_path):
        path = self.write(tmp_path, {"configuration_version": CONFIGURATION_VERSION})
        assert RunConfiguration.from_json(path).configuration_version == CONFIGURATION_VERSION

    def test_a_version_that_is_not_an_integer_is_refused(self, tmp_path):
        path = self.write(tmp_path, {"configuration_version": "1"})
        with pytest.raises(ConfigurationError, match="configuration_version"):
            RunConfiguration.from_json(path)


class TestNonFiniteNumbers:
    """``NaN`` and ``Infinity`` are not JSON.

    Python writes them and reads them back; every other language reads a syntax error, and
    being readable from another language is why the document is JSON in the first place.
    """

    def test_a_nan_parameter_is_refused_and_named(self, economy):
        with pytest.raises(ConfigurationError) as raised:
            run_configuration(LibraryLikeProcedure(threshold=float("nan")), economy, seed=0)
        assert "threshold" in str(raised.value)

    def test_an_infinite_parameter_is_refused_and_named(self, economy):
        with pytest.raises(ConfigurationError) as raised:
            run_configuration(
                ResearcherDataclassProcedure(threshold=float("inf")), economy, seed=0
            )
        assert "threshold" in str(raised.value)

    def test_a_nested_parameter_is_named_by_its_path(self, economy):
        with pytest.raises(ConfigurationError) as raised:
            run_configuration(
                LibraryLikeProcedure(rule=NestedRule(tolerance=float("nan"))),
                economy,
                seed=0,
            )
        message = str(raised.value)
        assert "rule" in message
        assert "tolerance" in message

    def test_a_finite_parameter_is_kept(self, economy):
        config = run_configuration(LibraryLikeProcedure(threshold=1e308), economy, seed=0)
        assert config.procedure["parameters"]["threshold"] == 1e308

    def test_a_loader_holding_a_non_finite_number_is_refused(self, economy):
        with pytest.raises(ConfigurationError, match="loader"):
            run_configuration(
                ResearcherProcedure(), economy, seed=0, loader={"endowment": float("inf")}
            )

    def test_a_document_holding_a_non_finite_number_is_not_written(self, tmp_path):
        path = tmp_path / "configuration.json"
        with pytest.raises(ConfigurationError):
            RunConfiguration(loader={"endowment": float("nan")}).to_json(path)

    def test_nothing_is_left_behind_when_writing_fails(self, tmp_path):
        path = tmp_path / "configuration.json"
        with pytest.raises(ConfigurationError):
            RunConfiguration(loader={"endowment": float("nan")}).to_json(path)
        assert not path.exists()


class TestNumpyScalars:
    """A numpy scalar parameter is recorded as the number it is.

    ``np.float64`` happens to subclass ``float`` and ``np.int64`` does not, so without a
    conversion the same procedure records one parameter as a number and drops the next into
    the undeclared form, taking its value with it. Silently losing a parameter is the failure
    this whole document exists to prevent, and a researcher writing ``np.int64(250)`` has no
    way to notice.
    """

    def test_a_numpy_integer_is_recorded_as_a_number(self, economy):
        config = run_configuration(
            LibraryLikeProcedure(absent=np.int64(250)), economy, seed=0
        )
        assert config.procedure["parameters"]["absent"] == 250

    def test_a_numpy_integer_is_recorded_as_a_python_integer(self, economy):
        config = run_configuration(
            LibraryLikeProcedure(absent=np.int64(250)), economy, seed=0
        )
        assert type(config.procedure["parameters"]["absent"]) is int

    def test_a_numpy_float_is_recorded_as_a_python_float(self, economy):
        config = run_configuration(
            LibraryLikeProcedure(threshold=np.float64(2.5)), economy, seed=0
        )
        recorded = config.procedure["parameters"]["threshold"]
        assert recorded == 2.5
        assert type(recorded) is float

    def test_a_numpy_boolean_is_recorded_as_a_python_boolean(self, economy):
        config = run_configuration(
            LibraryLikeProcedure(enabled=np.bool_(False)), economy, seed=0
        )
        recorded = config.procedure["parameters"]["enabled"]
        assert recorded is False

    def test_a_numpy_scalar_survives_a_round_trip_through_the_file(self, economy, tmp_path):
        path = tmp_path / "configuration.json"
        run_configuration(
            LibraryLikeProcedure(absent=np.int64(250)), economy, seed=0
        ).to_json(path)
        loaded = RunConfiguration.from_json(path)
        assert loaded.procedure["parameters"]["absent"] == 250

    def test_a_numpy_nan_is_still_refused(self, economy):
        """The conversion must not carry a value past the check on the far side of it."""
        with pytest.raises(ConfigurationError) as raised:
            run_configuration(
                LibraryLikeProcedure(threshold=np.float64("nan")), economy, seed=0
            )
        assert "threshold" in str(raised.value)

    def test_a_numpy_infinity_is_still_refused(self, economy):
        with pytest.raises(ConfigurationError) as raised:
            run_configuration(
                LibraryLikeProcedure(threshold=np.float32("inf")), economy, seed=0
            )
        assert "threshold" in str(raised.value)

    def test_an_array_is_not_a_scalar_and_stays_undeclared(self, economy):
        config = run_configuration(
            LibraryLikeProcedure(absent=np.array([1.0, 2.0])), economy, seed=0
        )
        assert config.procedure["parameters"]["absent"]["kind"] == "researcher"


@dataclasses.dataclass(frozen=True)
class SpecColumns:
    """A stand-in whose two columns are the worked example the preimage tests spell out."""

    alpha: object
    beta: object


@dataclasses.dataclass(frozen=True)
class OneBag:
    """A stand-in carrying nothing but a bag, so that a bag key alone names a column."""

    bag: dict


SPEC_ALPHA = np.array([1, 2], dtype="<i8")
SPEC_BETA = np.array([3.5], dtype="<f8")

ALPHA_PREIMAGE = (
    b"alpha\n<i8\n2\n"
    b"\x01\x00\x00\x00\x00\x00\x00\x00"
    b"\x02\x00\x00\x00\x00\x00\x00\x00"
)
"""The bytes ``docs/decisions/reproducibility.md`` says a column of ``SPEC_ALPHA`` is hashed over.

Spelled out here rather than assembled the way the module assembles it. A test that built the
header from ``dtype.str`` and the shape the same way the module does would agree with the
module under every change to either, which is what left the separator, the field order, the
encoding and the hash function itself unguarded.
"""

BETA_PREIMAGE = b"beta\n<f8\n1\n\x00\x00\x00\x00\x00\x00\x0c\x40"

ALPHA_DIGEST = "c43cb1d4c425408af8aa237ec476878c9d9e49e9c2c978764352e7b9530f6884"
"""sha256 of :data:`ALPHA_PREIMAGE`, written down so that no change here can move it."""

BETA_DIGEST = "24840ce6c6a618f829f6e0d02305bd1e24890b77ee563ec1d38704edfb124e21"

SPEC_WHOLE_DIGEST = "44c9149f00624e5da7f51fc95868c3439aa4a97837239f2da7eea5b0f92392f9"
"""sha256 of ``ALPHA_DIGEST + BETA_DIGEST`` as ASCII: the two column digests in name order."""

UTF_8_BAG_DIGEST = "a77c1f58f2ec9778e098a819f3e57da10cf93413ce802b9c48cf9dc58f9d676c"
"""sha256 over ``b"bag.\\xcf\\x80\\n<i8\\n1\\n\\x05\\x00\\x00\\x00\\x00\\x00\\x00\\x00"``.

The column name is ``bag.π``, whose UTF-8 encoding is two bytes and whose UTF-16 encoding is
neither those bytes nor that length.
"""

TWO_DIMENSIONAL_DIGEST = "89644899311b3d694aa1abb3fe659b8b62e10dbd5153936f44681c755863b9d5"
"""sha256 over ``b"bag.grid\\n<i8\\n2,3\\n"`` and the six little-endian integers 0 to 5.

The one column here with more than one dimension. Every shape of one dimension joins to the
same string under any separator, so a suite built only from those says nothing about which
separator the shape uses, and the header is what another language has to reproduce.
"""

PERIOD_ZERO_DIGEST = "8113d5816eadf76f26daf54aa71f51fb07b8f9cbf01405b462591049c0c68840"
"""sha256 over ``b"period\\n<i8\\n1\\n" + eight zero bytes``: period 0 as a 64-bit integer."""

BOOLEAN_COLUMN_DIGEST = "25cb94084fa0961e60f619fbb4e94f3a96270983f958a69b764873178103ea87"
"""sha256 over ``b"alpha\\n|b1\\n1\\n\\x01"``: a true column keeps the boolean dtype string."""

NORMALISED_SOURCE_DIGEST = "a57d7057293d0884af041598b2fdf66fe281746e1cf34253633f57b65381ee2e"
"""sha256 over ``b"ALPHA = 1\\nBETA = 2\\n"``, the line-ending-normalised form of a module."""

DEFAULTS_DOCUMENT_BYTES = (
    b'{\n'
    b'  "configuration_version": 1,\n'
    b'  "core_version": null,\n'
    b'  "economy": null,\n'
    b'  "library_version": null,\n'
    b'  "loader": null,\n'
    b'  "plan_fields_absent": [\n'
    b'    "provision"\n'
    b'  ],\n'
    b'  "procedure": null,\n'
    b'  "seed": 7\n'
    b'}\n'
)
"""Every byte of one written document, so that "compares as bytes" has something reading them.

Sorted keys, two-space indent, a newline between every pair of lines and one at the end, and
no carriage return anywhere, on Windows as on anything else.
"""

PINNED_DIGEST_INSTRUCTION = (
    "This digest was spelled out by hand from the specification text in "
    "docs/decisions/reproducibility.md, not read off the module. It moves for one of two reasons. "
    "Either a step of the normalisation broke, and the fix belongs in the module; or a step "
    "was changed on purpose, and then ECONOMY_DIGEST_ALGORITHM takes a new version in this "
    "same commit and the decision record says which step moved. There is no third reason. A "
    "version string left behind names a normalisation it no longer describes, and every "
    "document already written under it becomes unreadable without saying so."
)
"""What to do about a pinned digest that has moved, said in the failure itself.

The specification says any change to any step of the normalisation takes a new version
string, and nothing enforces that: the version is a string somebody types. These constants
at least make the change fail loudly, and the message is what turns "the digest moved" into
"you owe a version bump".
"""

CONFIGURATION_EXPORTS = (
    "ConfigurationError",
    "EconomyDigestReport",
    "RunConfiguration",
    "compare_economy_digests",
    "economy_digest",
    "run_configuration",
)
"""What this module contributes to the package's public surface."""


def labelled(count: int) -> np.ndarray:
    """``count`` object-dtype labels built at run time, so no two arrays share a pointer.

    Short string literals are interned, which would make two separately built arrays hold the
    same pointers and hide the very failure these tests are about.
    """
    return np.array(["label " + str(index) for index in range(count)], dtype=object)


@dataclasses.dataclass(frozen=True)
class ContainerProcedure:
    """A procedure holding the JSON-native containers a researcher's parameters arrive in.

    A weight tuple is one of the commonest parameter shapes there is, and the document is
    worth nothing to whoever reruns the procedure if it records the tuple as "not declared".
    """

    weights: object = (0.1, 0.9)
    rounds: object = dataclasses.field(default_factory=lambda: [1, 2, 3])
    thresholds: object = dataclasses.field(default_factory=lambda: {"price": 0.05})

    def solve(self, economy, seed):
        raise AssertionError("writing a configuration document must not run the procedure")


class TestTheColumnPreimage:
    """What exactly goes into a column's sha256, byte for byte.

    ``sha256-columns-v2`` is a promise that another implementation, in another language, can
    read the specification and arrive at the same hex string. Nothing keeps that promise
    except a test that writes the preimage out by hand: every inequality assertion in this
    file passes just as happily under a different separator, a different field order, a
    different encoding or a different hash function.
    """

    def test_the_written_preimage_matches_the_written_digest(self):
        """A self-check on the two constants: a typo in either turns this red rather than
        turning a real assertion green for the wrong reason."""
        typo = "the written preimage and the written digest disagree: one has a typo"
        assert hashlib.sha256(ALPHA_PREIMAGE).hexdigest() == ALPHA_DIGEST, typo
        assert hashlib.sha256(BETA_PREIMAGE).hexdigest() == BETA_DIGEST, typo

    def test_a_column_digest_is_sha256_over_the_hand_written_preimage(self):
        columns = economy_digest(SpecColumns(alpha=SPEC_ALPHA, beta=SPEC_BETA))["columns"]
        assert columns["alpha"] == ALPHA_DIGEST, PINNED_DIGEST_INSTRUCTION
        assert columns["beta"] == BETA_DIGEST, PINNED_DIGEST_INSTRUCTION

    def test_the_column_digest_is_sha256_and_not_another_hash_of_the_same_length(self):
        columns = economy_digest(SpecColumns(alpha=SPEC_ALPHA, beta=SPEC_BETA))["columns"]
        assert columns["alpha"] != hashlib.sha3_256(ALPHA_PREIMAGE).hexdigest()
        assert columns["alpha"] != hashlib.blake2s(ALPHA_PREIMAGE).hexdigest()

    def test_the_whole_digest_is_sha256_over_the_column_digests_in_name_order(self):
        block = economy_digest(SpecColumns(alpha=SPEC_ALPHA, beta=SPEC_BETA))
        assert block["digest"] == SPEC_WHOLE_DIGEST, PINNED_DIGEST_INSTRUCTION
        assert block["digest"] == hashlib.sha256(
            (ALPHA_DIGEST + BETA_DIGEST).encode("ascii")
        ).hexdigest()

    def test_the_column_header_is_encoded_as_utf_8(self):
        """A column name outside ASCII, where UTF-8 and UTF-16 disagree on bytes and length."""
        digest = economy_digest(OneBag(bag={"π": np.array([5], dtype="<i8")}))
        assert digest["columns"]["bag.π"] == UTF_8_BAG_DIGEST, PINNED_DIGEST_INSTRUCTION

    def test_the_shape_is_joined_by_commas(self):
        """A column of two dimensions, which is the only kind whose join is visible."""
        grid = np.arange(6, dtype="<i8").reshape(2, 3)
        digest = economy_digest(OneBag(bag={"grid": grid}))
        assert (
            digest["columns"]["bag.grid"] == TWO_DIMENSIONAL_DIGEST
        ), PINNED_DIGEST_INSTRUCTION

    def test_a_big_endian_column_digests_as_the_hand_written_little_endian_preimage(self):
        """Normalisation to little-endian, pinned against the written bytes rather than
        against the module's own answer for the little-endian twin."""
        big = SpecColumns(alpha=np.array([1, 2], dtype=">i8"), beta=SPEC_BETA)
        assert (
            economy_digest(big)["columns"]["alpha"] == ALPHA_DIGEST
        ), PINNED_DIGEST_INSTRUCTION


class TestScalarColumns:
    """A scalar has no dtype until one is chosen for it, so the choice is pinned here.

    ``np.ascontiguousarray`` gives a Python integer whatever width the platform defaults to,
    and the width travels into the header as ``<i4`` or ``<i8``. Two people on two platforms
    would get two digests for one economy, and a Rust implementation reading the specification
    would have nothing to tell it which to write.
    """

    def test_the_period_is_recorded_as_a_64_bit_integer(self, economy):
        block = economy_digest(dataclasses.replace(economy, period=0))
        assert block["columns"]["period"] == PERIOD_ZERO_DIGEST, PINNED_DIGEST_INSTRUCTION

    def test_the_python_type_of_the_period_does_not_reach_the_digest(self, economy):
        for period in (0, np.int32(0), np.int64(0), np.int8(0)):
            replaced = dataclasses.replace(economy, period=period)
            assert (
                economy_digest(replaced)["columns"]["period"] == PERIOD_ZERO_DIGEST
            ), PINNED_DIGEST_INSTRUCTION

    def test_two_economies_of_the_same_period_agree_whatever_type_carries_it(self, economy):
        as_int = dataclasses.replace(economy, period=3)
        as_numpy = dataclasses.replace(economy, period=np.int32(3))
        assert economy_digest(as_int) == economy_digest(as_numpy)

    def test_a_different_period_still_gives_a_different_digest(self, economy):
        first = dataclasses.replace(economy, period=3)
        second = dataclasses.replace(economy, period=4)
        assert economy_digest(first)["digest"] != economy_digest(second)["digest"]

    def test_an_integer_array_keeps_the_width_it_declares(self):
        """Only a scalar's width is platform noise. An array declares its own dtype, and
        widening it here would report two genuinely different columns as one."""
        column = SpecColumns(alpha=np.array([1, 2], dtype="<i4"), beta=SPEC_BETA)
        assert economy_digest(column)["columns"]["alpha"] != ALPHA_DIGEST

    def test_a_boolean_column_keeps_the_boolean_dtype_string(self):
        block = economy_digest(SpecColumns(alpha=True, beta=SPEC_BETA))
        assert (
            block["columns"]["alpha"] == BOOLEAN_COLUMN_DIGEST
        ), PINNED_DIGEST_INSTRUCTION


class TestColumnsThatCannotBeDigestedFaithfully:
    """Dtypes whose bytes do not stand for the values, refused instead of digested.

    ``tobytes()`` on an object array hands back the pointers, not the labels behind them, so
    two economies holding equal labels digest differently and one whose label was edited in
    place digests the same. ``dtype.str`` of a structured dtype is ``|V16`` whatever its
    fields are called, so two columns whose fields have different names collide. A digest
    that answered either question would be answering one it cannot answer, and the module
    says a matching digest proves the arrays are identical.
    """

    def test_an_object_column_is_refused(self):
        with pytest.raises(ConfigurationError) as raised:
            economy_digest(SpecColumns(alpha=labelled(2), beta=SPEC_BETA))
        message = str(raised.value)
        assert "alpha" in message
        assert "|O" in message

    def test_two_economies_holding_equal_labels_are_refused_rather_than_reported_apart(self):
        """The failure this replaces: the same labels in two arrays digested differently."""
        first, second = labelled(2), labelled(2)
        assert list(first) == list(second)
        assert first.tobytes() != second.tobytes()
        for subject in (first, second):
            with pytest.raises(ConfigurationError):
                economy_digest(SpecColumns(alpha=subject, beta=SPEC_BETA))

    def test_an_object_column_in_a_bag_is_refused_under_its_prefixed_name(self):
        with pytest.raises(ConfigurationError) as raised:
            economy_digest(OneBag(bag={"label": labelled(2)}))
        assert "bag.label" in str(raised.value)

    def test_a_structured_column_is_refused(self):
        pairs = np.zeros(2, dtype=np.dtype([("alpha", "<f8"), ("beta", "<f8")]))
        with pytest.raises(ConfigurationError) as raised:
            economy_digest(SpecColumns(alpha=pairs, beta=SPEC_BETA))
        assert "alpha" in str(raised.value)

    def test_two_structured_dtypes_that_collide_are_both_refused(self):
        one = np.zeros(2, dtype=np.dtype([("alpha", "<f8"), ("beta", "<f8")]))
        other = np.zeros(2, dtype=np.dtype([("gamma", "<f8"), ("delta", "<f8")]))
        assert one.dtype.str == other.dtype.str
        assert one.tobytes() == other.tobytes()
        for subject in (one, other):
            with pytest.raises(ConfigurationError):
                economy_digest(SpecColumns(alpha=subject, beta=SPEC_BETA))

    def test_the_two_refusals_name_their_own_cause(self):
        """A structured column loses its field names; an object column never held values at
        all. The two are fixed differently, so being told the wrong one costs the reader the
        time it takes to try the wrong fix."""
        pairs = np.zeros(2, dtype=np.dtype([("alpha", "<f8"), ("beta", "<f8")]))
        with pytest.raises(ConfigurationError) as structured:
            economy_digest(SpecColumns(alpha=pairs, beta=SPEC_BETA))
        with pytest.raises(ConfigurationError) as objects:
            economy_digest(SpecColumns(alpha=labelled(2), beta=SPEC_BETA))
        assert "field names" in str(structured.value)
        assert "field names" not in str(objects.value)
        assert "bytes are not its values" in str(objects.value)
        assert "bytes are not its values" not in str(structured.value)

    def test_a_text_column_is_refused(self):
        with pytest.raises(ConfigurationError):
            economy_digest(SpecColumns(alpha=np.array(["a", "b"]), beta=SPEC_BETA))

    @pytest.mark.parametrize(
        "dtype", ["|b1", "<i2", "<u4", "<f4", "<f8", "<c16"]
    )
    def test_the_dtypes_a_digest_can_carry_are_still_carried(self, dtype):
        block = economy_digest(SpecColumns(alpha=np.zeros(2, dtype=dtype), beta=SPEC_BETA))
        assert len(block["columns"]["alpha"]) == 64


class TestSourceDigestLineEndings:
    """Line endings are not behaviour, and a checkout changes them without being asked.

    This repository sets ``core.autocrlf``, so one contributor's working tree holds a prefab
    with CRLF where another's holds the same commit with LF. A digest over the raw bytes calls
    those two different implementations, which inverts what the digest is for: it answers
    whether the library changed the code under an older scenario's feet.
    """

    def module_with_source(self, monkeypatch, tmp_path, name: str, body: bytes) -> str:
        """Register a module under ``name`` whose source file holds exactly ``body``.

        The module object is built rather than imported, so the digest is taken over a file
        whose bytes the test chose and no module-level code runs.
        """
        path = tmp_path / f"{name}.py"
        path.write_bytes(body)
        module = types.ModuleType(name)
        module.__file__ = str(path)
        monkeypatch.setitem(sys.modules, name, module)
        return name

    def test_a_file_with_crlf_digests_as_the_same_file_with_lf(self, monkeypatch, tmp_path):
        crlf = self.module_with_source(
            monkeypatch, tmp_path, "line_endings_crlf", b"ALPHA = 1\r\nBETA = 2\r\n"
        )
        lf = self.module_with_source(
            monkeypatch, tmp_path, "line_endings_lf", b"ALPHA = 1\nBETA = 2\n"
        )
        assert configuration._module_source_digest(crlf) == (
            configuration._module_source_digest(lf)
        )

    def test_a_lone_carriage_return_is_normalised_too(self, monkeypatch, tmp_path):
        old_mac = self.module_with_source(
            monkeypatch, tmp_path, "line_endings_cr", b"ALPHA = 1\rBETA = 2\r"
        )
        lf = self.module_with_source(
            monkeypatch, tmp_path, "line_endings_lf_twin", b"ALPHA = 1\nBETA = 2\n"
        )
        assert configuration._module_source_digest(old_mac) == (
            configuration._module_source_digest(lf)
        )

    def test_the_digest_is_sha256_over_the_normalised_bytes(self, monkeypatch, tmp_path):
        name = self.module_with_source(
            monkeypatch, tmp_path, "line_endings_pinned", b"ALPHA = 1\r\nBETA = 2\r\n"
        )
        assert configuration._module_source_digest(name) == NORMALISED_SOURCE_DIGEST

    def test_a_change_to_the_content_still_moves_the_digest(self, monkeypatch, tmp_path):
        first = self.module_with_source(
            monkeypatch, tmp_path, "line_endings_one", b"ALPHA = 1\nBETA = 2\n"
        )
        second = self.module_with_source(
            monkeypatch, tmp_path, "line_endings_two", b"ALPHA = 1\nBETA = 3\n"
        )
        assert configuration._module_source_digest(first) != (
            configuration._module_source_digest(second)
        )

    def test_the_whole_file_is_still_read_and_not_only_part_of_it(
        self, monkeypatch, tmp_path
    ):
        short = self.module_with_source(
            monkeypatch, tmp_path, "line_endings_short", b"ALPHA = 1\n"
        )
        long = self.module_with_source(
            monkeypatch, tmp_path, "line_endings_long", b"ALPHA = 1\nBETA = 2\n"
        )
        assert configuration._module_source_digest(short) != (
            configuration._module_source_digest(long)
        )


class TestContainerParameters:
    """Lists, tuples and string-keyed dicts are recorded by value, element by element.

    JSON has an array and an object, so nothing about these has to be dropped, and dropping
    them lands on the same failure the numpy scalar rule was written against: the value
    disappears into ``"parameters": null``, which is also what the document says when the
    researcher passed a callable. He cannot tell the two apart, and he is not told either
    happened.
    """

    def block(self, economy, procedure):
        return run_configuration(procedure, economy, seed=0).procedure["parameters"]

    def test_a_tuple_is_recorded_as_a_json_array(self, economy):
        assert self.block(economy, ContainerProcedure())["weights"] == [0.1, 0.9]

    def test_a_list_is_recorded_as_a_json_array(self, economy):
        assert self.block(economy, ContainerProcedure())["rounds"] == [1, 2, 3]

    def test_a_string_keyed_dict_is_recorded_as_a_json_object(self, economy):
        assert self.block(economy, ContainerProcedure())["thresholds"] == {"price": 0.05}

    def test_an_empty_container_is_kept_apart_from_a_parameter_not_declared(self, economy):
        parameters = self.block(economy, ContainerProcedure(weights=(), thresholds={}))
        assert parameters["weights"] == []
        assert parameters["thresholds"] == {}

    def test_containers_nest(self, economy):
        nested = ContainerProcedure(weights=[{"inner": (1, 2)}, [3]])
        assert self.block(economy, nested)["weights"] == [{"inner": [1, 2]}, [3]]

    def test_a_numpy_scalar_inside_a_container_is_unwrapped(self, economy):
        nested = ContainerProcedure(weights=(np.int64(250), np.float32(0.5)))
        recorded = self.block(economy, nested)["weights"]
        assert recorded[0] == 250
        assert type(recorded[0]) is int
        assert type(recorded[1]) is float

    def test_an_array_inside_a_container_falls_to_the_undeclared_form(self, economy):
        nested = ContainerProcedure(weights=[np.array([1.0, 2.0])])
        assert self.block(economy, nested)["weights"][0]["kind"] == "researcher"

    def test_an_array_is_still_undeclared_at_the_top_level(self, economy):
        """Its size has no bound, which is the reason the container rule stops at arrays."""
        nested = ContainerProcedure(weights=np.array([1.0, 2.0]))
        assert self.block(economy, nested)["weights"]["kind"] == "researcher"

    def test_a_dict_whose_keys_are_not_strings_falls_to_the_undeclared_form(self, economy):
        """JSON objects are keyed by strings, and a document that wrote ``1`` as ``"1"``
        would read back as a different dict without saying so."""
        nested = ContainerProcedure(thresholds={1: 0.5})
        assert self.block(economy, nested)["thresholds"]["kind"] == "researcher"

    def test_a_non_finite_number_in_a_list_is_named_by_its_index(self, economy):
        with pytest.raises(ConfigurationError) as raised:
            run_configuration(
                ContainerProcedure(weights=[0.1, float("nan")]), economy, seed=0
            )
        assert "parameters.weights[1]" in str(raised.value)

    def test_a_non_finite_number_in_a_dict_is_named_by_its_key(self, economy):
        with pytest.raises(ConfigurationError) as raised:
            run_configuration(
                ContainerProcedure(thresholds={"price": float("inf")}), economy, seed=0
            )
        assert "parameters.thresholds['price']" in str(raised.value)

    def test_a_non_finite_number_nested_two_deep_is_named_by_the_whole_path(self, economy):
        with pytest.raises(ConfigurationError) as raised:
            run_configuration(
                ContainerProcedure(weights=[{"inner": [float("nan")]}]), economy, seed=0
            )
        assert "parameters.weights[0]['inner'][0]" in str(raised.value)

    def test_a_container_parameter_survives_a_round_trip_through_the_file(
        self, economy, tmp_path
    ):
        path = tmp_path / "configuration.json"
        run_configuration(ContainerProcedure(), economy, seed=0).to_json(path)
        loaded = RunConfiguration.from_json(path)
        assert loaded.procedure["parameters"]["weights"] == [0.1, 0.9]
        assert loaded.procedure["parameters"]["thresholds"] == {"price": 0.05}


class TestTheDocumentAsBytes:
    """The docstring says a document can be compared as bytes; this reads the bytes."""

    def test_the_file_holds_exactly_these_bytes(self, tmp_path):
        path = tmp_path / "configuration.json"
        RunConfiguration(seed=7, plan_fields_absent=("provision",)).to_json(path)
        assert path.read_bytes() == DEFAULTS_DOCUMENT_BYTES

    def test_no_carriage_return_reaches_the_file(self, tmp_path):
        path = tmp_path / "configuration.json"
        RunConfiguration(seed=7).to_json(path)
        assert b"\r" not in path.read_bytes()

    def test_the_file_ends_in_a_newline(self, tmp_path):
        path = tmp_path / "configuration.json"
        RunConfiguration(seed=7).to_json(path)
        assert path.read_bytes().endswith(b"}\n")

    def test_a_value_outside_ascii_is_written_as_utf_8_rather_than_escaped(self, tmp_path):
        """UTF-8 is what the specification names, and escapes would change every byte after
        the first non-ASCII character without changing what the document says."""
        path = tmp_path / "configuration.json"
        RunConfiguration(loader={"name": "价格"}).to_json(path)
        assert "价格".encode("utf-8") in path.read_bytes()


class TestExportedNames:
    """``__all__`` membership, which resolving every listed name does not check.

    The list is scanned by a reader looking for what the library offers, so a name dropped
    from it is a function that stops existing as far as that reader is concerned while every
    test of the function itself goes on passing.
    """

    @pytest.mark.parametrize("name", CONFIGURATION_EXPORTS)
    def test_the_name_is_exported(self, name):
        assert name in demplan.__all__

    @pytest.mark.parametrize("name", CONFIGURATION_EXPORTS)
    def test_the_name_is_reachable_on_the_package(self, name):
        assert getattr(demplan, name) is getattr(configuration, name)


class TestBooleanIsNotAnInteger:
    """``bool`` subclasses ``int``, so every integer check has to say so out loud.

    A document carrying ``true`` where a version belongs, or a run seeded with ``True``,
    would otherwise be read as the number 1 and recorded as a deliberate choice.
    """

    def test_a_boolean_configuration_version_is_refused(self, tmp_path):
        path = tmp_path / "configuration.json"
        path.write_text(json.dumps({"configuration_version": True}), encoding="utf-8")
        with pytest.raises(ConfigurationError) as raised:
            RunConfiguration.from_json(path)
        assert "configuration_version" in str(raised.value)

    def test_a_boolean_seed_is_refused(self, economy):
        with pytest.raises(ConfigurationError) as raised:
            run_configuration(ResearcherProcedure(), economy, seed=True)
        assert "seed" in str(raised.value)


class TestAbsentFieldsThatAreNotFieldNames:
    """What ``absent_fields`` is read as when it is not a sequence of field names."""

    def test_a_bare_string_is_refused_rather_than_split_into_characters(self, economy):
        """``tuple("provision")`` is eleven one-character field names, and each of them is a
        string, so a per-element type check passes on every one of them."""
        with pytest.raises(ConfigurationError) as raised:
            run_configuration(
                ResearcherProcedure(),
                economy,
                seed=0,
                plan=PlanStub(absent_fields="provision"),
            )
        message = str(raised.value)
        assert "absent_fields" in message
        assert "provision" in message

    def test_a_value_that_cannot_be_iterated_is_refused_as_a_configuration_error(
        self, economy
    ):
        """Every other refusal in this module is a ``ConfigurationError``; a bare
        ``TypeError`` from ``tuple`` would be the one that escapes a caller's except."""
        with pytest.raises(ConfigurationError) as raised:
            run_configuration(
                ResearcherProcedure(), economy, seed=0, plan=PlanStub(absent_fields=7)
            )
        assert "absent_fields" in str(raised.value)

    def test_a_sequence_of_field_names_is_still_taken(self, economy):
        config = run_configuration(
            ResearcherProcedure(),
            economy,
            seed=0,
            plan=PlanStub(absent_fields=["provision", "consumption"]),
        )
        assert config.plan_fields_absent == ("provision", "consumption")


class TestEveryUnknownKeyIsNamed:
    """A document with three unknown keys costs three edits, so it has to name three.

    Naming one leaves the reader to fix it, rerun, and be told about the next.
    """

    def write(self, tmp_path, document) -> Path:
        path = tmp_path / "configuration.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_all_of_them_appear_in_the_message(self, tmp_path):
        path = self.write(tmp_path, {"alpha": 1, "beta": 2, "gamma": 3})
        with pytest.raises(ConfigurationError) as raised:
            RunConfiguration.from_json(path)
        message = str(raised.value)
        for key in ("alpha", "beta", "gamma"):
            assert repr(key) in message

    def test_a_retired_key_beside_an_unknown_one_keeps_both_explanations(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setitem(
            RETIRED_KEYS, "alpha", RetiredKey(removed_in="0.4.0", reason="it moved")
        )
        path = self.write(tmp_path, {"alpha": 1, "beta": 2})
        with pytest.raises(ConfigurationError) as raised:
            RunConfiguration.from_json(path)
        message = str(raised.value)
        assert "no longer exists" in message
        assert "0.4.0" in message
        assert "newer" in message
        assert "'alpha'" in message
        assert "'beta'" in message


class TestDigestComparisonInputs:
    """A diagnostic tool answers "these are the same" only about two things it was given.

    ``compare_economy_digests({}, {})`` reading as identical is the shape of answer that gets
    written into a paper's methods section.
    """

    def test_two_empty_mappings_are_refused(self):
        with pytest.raises(ConfigurationError):
            compare_economy_digests({}, {})

    @pytest.mark.parametrize("missing", ["algorithm", "digest", "columns"])
    def test_a_block_missing_one_of_its_keys_is_refused(self, economy, missing):
        incomplete = {
            key: value for key, value in economy_digest(economy).items() if key != missing
        }
        with pytest.raises(ConfigurationError) as raised:
            compare_economy_digests(incomplete, economy_digest(economy))
        assert missing in str(raised.value)

    def test_the_block_at_hand_is_checked_as_well_as_the_recorded_one(self, economy):
        incomplete = {
            key: value
            for key, value in economy_digest(economy).items()
            if key != "columns"
        }
        with pytest.raises(ConfigurationError):
            compare_economy_digests(economy_digest(economy), incomplete)

    def test_columns_that_are_not_a_mapping_are_refused(self, economy):
        broken = dict(economy_digest(economy), columns=["period"])
        with pytest.raises(ConfigurationError) as raised:
            compare_economy_digests(broken, economy_digest(economy))
        assert "columns" in str(raised.value)

    def test_a_pair_of_real_blocks_is_still_compared(self, economy):
        report = compare_economy_digests(economy_digest(economy), economy_digest(economy))
        assert report.identical


class TestAnEditedDocumentIsReportedBothWays:
    """The whole digest and the columns contradicting each other, in either direction.

    Columns that agree under two different whole digests and columns that differ under one
    whole digest are the same fact: one of the two blocks was written by hand. Reporting only
    the first left the second reading as an ordinary difference.
    """

    def test_agreeing_columns_under_differing_whole_digests_are_reported(self, economy):
        current = dict(economy_digest(economy), digest="0" * 64)
        report = compare_economy_digests(economy_digest(economy), current)
        assert report.digest_contradicts_columns

    def test_differing_columns_under_one_whole_digest_are_reported(self, economy):
        recorded = economy_digest(economy)
        current = economy_digest(economy)
        current["columns"]["period"] = "0" * 64
        report = compare_economy_digests(recorded, current)
        assert report.differing_columns == ["period"]
        assert report.digest_contradicts_columns

    def test_two_blocks_that_agree_throughout_report_no_contradiction(self, economy):
        report = compare_economy_digests(economy_digest(economy), economy_digest(economy))
        assert not report.digest_contradicts_columns

    def test_two_genuinely_different_economies_report_no_contradiction(self, economy):
        moved = economy_digest(mutated(economy, "endowment"))
        report = compare_economy_digests(economy_digest(economy), moved)
        assert report.differing_columns == ["endowment"]
        assert not report.digest_contradicts_columns


class TestARealEconomy:
    """The digest, once, on an economy nobody wrote for a test.

    Every other test here builds its economy from a synthetic fixture or a two-column
    stand-in. dep1ex01 is 53.3 MB of somebody else's data, and it is what turns "the columns
    are the dataclass fields" from a statement about a fixture into a statement about the
    library.
    """

    def test_a_real_economy_digests_and_matches_itself(self, dep1ex01_economy):
        block = economy_digest(dep1ex01_economy)
        assert set(block) == {"algorithm", "digest", "columns"}
        assert block["algorithm"] == ECONOMY_DIGEST_ALGORITHM
        report = compare_economy_digests(block, economy_digest(dep1ex01_economy))
        assert report.identical

    def test_every_field_of_a_real_economy_reaches_the_columns(self, dep1ex01_economy):
        columns = economy_digest(dep1ex01_economy)["columns"]
        for field in dataclasses.fields(dep1ex01_economy):
            value = getattr(dep1ex01_economy, field.name)
            if isinstance(value, Mapping):
                for key in value:
                    assert f"{field.name}.{key}" in columns
            else:
                assert field.name in columns

    def test_every_column_of_a_real_economy_carries_a_sha256(self, dep1ex01_economy):
        for digest in economy_digest(dep1ex01_economy)["columns"].values():
            assert len(digest) == 64
            assert set(digest) <= set("0123456789abcdef")

    def test_moving_one_value_in_a_real_economy_moves_one_column(self, dep1ex01_economy):
        before = economy_digest(dep1ex01_economy)
        after = economy_digest(mutated(dep1ex01_economy, "endowment"))
        report = compare_economy_digests(before, after)
        assert report.differing_columns == ["endowment"]

    def test_a_real_economy_goes_into_a_document_that_reads_back(
        self, dep1ex01_economy, tmp_path
    ):
        path = tmp_path / "configuration.json"
        config = run_configuration(ResearcherProcedure(), dep1ex01_economy, seed=5)
        config.to_json(path)
        assert RunConfiguration.from_json(path) == config
