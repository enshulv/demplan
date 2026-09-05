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
from pathlib import Path

import numpy as np
import pytest

import cyberstride
from cyberstride import Economy
from cyberstride import configuration
from cyberstride.configuration import (
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
from cyberstride.prefabs import HahnelSlides2020
from cyberstride.prefabs.hahnel_2020_slides import slides_2020_rule

DEFAULTS_BASELINE = Path(__file__).resolve().parent / "run_configuration_defaults.json"

PREFAB_MODULE = "cyberstride.prefabs.hahnel_2020_slides"

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


Impostor.__module__ = "cyberstridex.impostor"


@dataclasses.dataclass(frozen=True)
class LibraryLikeProcedure:
    """A dataclass procedure that claims a library module, to reach the library branch.

    ``HahnelSlides2020`` is the only procedure the library ships, and every one of its
    parameters is a JSON scalar. The parameter rules also cover values that are not, so this
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


LibraryLikeProcedure.__module__ = "cyberstride.configuration"


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


NestedRule.__module__ = "cyberstride.configuration"


@dataclasses.dataclass(frozen=True)
class PlanStub:
    """What ``run_configuration`` reads off a plan, and nothing else."""

    absent_fields: tuple[str, ...]


def module_file_digest(module_name: str) -> str:
    """sha256 of the source file of ``module_name``, read as bytes."""
    path = Path(importlib.import_module(module_name).__file__)
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestEconomyDigestShape:
    def test_the_block_carries_the_algorithm_the_digest_and_the_columns(self, economy):
        block = economy_digest(economy)
        assert set(block) == {"algorithm", "digest", "columns"}

    def test_the_algorithm_is_named_and_versioned(self, economy):
        assert economy_digest(economy)["algorithm"] == "sha256-columns-v1"
        assert ECONOMY_DIGEST_ALGORITHM == "sha256-columns-v1"

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
        }

    def test_the_configuration_version_is_one(self, economy):
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert config.configuration_version == 1
        assert CONFIGURATION_VERSION == 1

    def test_the_library_version_comes_from_the_installed_distribution(self, economy):
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert config.library_version == metadata.version("cyberstride")

    def test_an_uninstalled_library_records_an_unknown_version(self, economy, monkeypatch):
        def missing(name):
            raise metadata.PackageNotFoundError(name)

        monkeypatch.setattr(configuration.metadata, "version", missing)
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert config.library_version == "unknown"

    def test_the_core_version_is_recorded_beside_it(self, economy):
        config = run_configuration(ResearcherProcedure(), economy, seed=0)
        assert config.core_version == cyberstride.core_version()

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
        config = run_configuration(HahnelSlides2020(), economy, seed=0)
        assert config.procedure["kind"] == "library"
        assert config.procedure["module"] == PREFAB_MODULE
        assert config.procedure["qualname"] == "HahnelSlides2020"
        assert set(config.procedure) == {
            "kind",
            "module",
            "qualname",
            "source_digest",
            "parameters",
        }

    def test_the_source_digest_is_the_whole_module_file(self, economy):
        config = run_configuration(HahnelSlides2020(), economy, seed=0)
        assert config.procedure["source_digest"] == module_file_digest(PREFAB_MODULE)

    def test_the_source_digest_is_not_the_source_of_the_class_alone(self, economy):
        """Module-level constants decide behaviour as much as the class body does."""
        config = run_configuration(HahnelSlides2020(), economy, seed=0)
        class_source = inspect.getsource(HahnelSlides2020).encode("utf-8")
        assert config.procedure["source_digest"] != hashlib.sha256(class_source).hexdigest()

    def test_the_source_digest_is_not_some_other_library_file(self, economy):
        config = run_configuration(HahnelSlides2020(), economy, seed=0)
        assert config.procedure["source_digest"] != module_file_digest("cyberstride.seeds")

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
        """The test is on ``cyberstride.``, dot included, so ``cyberstridex`` is outside."""
        config = run_configuration(Impostor(), economy, seed=0)
        assert config.procedure["kind"] == "researcher"

    def test_the_procedure_is_never_solved(self, economy):
        run_configuration(ResearcherProcedure(), economy, seed=0)


class TestParameters:
    def test_a_dataclass_procedure_records_its_fields(self, economy):
        config = run_configuration(HahnelSlides2020(threshold_pct=3.0), economy, seed=0)
        assert config.procedure["parameters"] == {
            "threshold_pct": 3.0,
            "max_rounds": 250,
            "initial_price": 700.0,
            "record_trajectory": False,
            "price_rule": None,
        }

    def test_a_procedure_that_is_not_a_dataclass_records_no_parameters(self, economy):
        class Plain:
            def solve(self, economy, seed):
                raise AssertionError("never run")

        Plain.__module__ = "cyberstride.configuration"
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
            LibraryLikeProcedure(rule=slides_2020_rule), economy, seed=0
        )
        rule = config.procedure["parameters"]["rule"]
        assert rule["kind"] == "library"
        assert rule["module"] == PREFAB_MODULE
        assert rule["qualname"] == "slides_2020_rule"
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
        assert "cyberstride.plan" not in source


class TestJsonFile:
    @pytest.fixture
    def config(self, economy):
        return run_configuration(
            HahnelSlides2020(),
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

    def test_the_baseline_covers_every_key(self):
        baseline = json.loads(DEFAULTS_BASELINE.read_text(encoding="utf-8"))
        assert set(baseline) == {field.name for field in dataclasses.fields(RunConfiguration)}


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
            ResearcherDataclassProcedure(rule=slides_2020_rule), economy, seed=0
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
        current = dict(economy_digest(economy), algorithm="sha256-columns-v2")
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
