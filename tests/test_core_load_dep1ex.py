"""Differential and timing tests for the dep1ex loader exposed by cyberstride._core.

The reference is research/bench/repro.py, the numpy parser used for the upstream
replication. Both parsers read the same decimal text, and both Rust's f64 parser
and Python's float() are correctly rounded, so every array must match bit for
bit. Assertions use np.array_equal rather than a tolerance.

The reference arrays are shaped differently from the loader output: repro pads
each unit's inputs into a rectangle and keeps the three input segments in
separate categories, so the expectations below reshape the reference rather than
restate the loader's own numbers.
"""

import os
import pathlib
import sys
import time

import numpy as np
import pytest

from cyberstride import _core

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "research" / "bench"))

import repro  # noqa: E402  (needs the sys.path entry above)

DATA_DIR = pathlib.Path(os.environ.get("CYBERSTRIDE_DATA_DIR", REPO_ROOT / "research" / "data"))
DEP1EX01 = DATA_DIR / "dep1ex01.clj.gz"

#: Natural-resource and labour endowment per commodity, the value used in the paper.
ENDOWMENT = 1000.0

#: Wall-clock ceiling for one release-build load of dep1ex01.
LOAD_SECONDS_LIMIT = 1.5

#: Number of timed loads; the fastest one is compared against the limit.
TIMED_LOADS = 3

requires_data = pytest.mark.skipif(
    not DEP1EX01.exists(),
    reason=f"scenario file not found: {DEP1EX01}",
)


@pytest.fixture(scope="module")
def loaded():
    """Loads dep1ex01 once through the Rust loader."""
    return _core.load_dep1ex(str(DEP1EX01), ENDOWMENT)


@pytest.fixture(scope="module")
def reference():
    """Parses dep1ex01 once with the numpy reference parser and derives the layout.

    Returns the two reference dicts plus the commodity section bases that the
    loader is documented to use.
    """
    wc, cc = repro.parse(str(DEP1EX01))
    n_priv = cc["priv_exp"].shape[1]
    n_pub = cc["pub_exp"].shape[1]
    n_goods = int(max(wc["coef"][wc["mask"]].max(), wc["product"].max())) + 1
    bases = {
        "priv": 0,
        "pub": n_priv,
        "inter": n_priv + n_pub,
        "nature": n_priv + n_pub + n_goods,
        "labor": n_priv + n_pub + 2 * n_goods,
    }
    return {
        "wc": wc,
        "cc": cc,
        "n_priv": n_priv,
        "n_pub": n_pub,
        "n_goods": n_goods,
        "bases": bases,
    }


# ---- commodity table ----


@requires_data
def test_commodity_count_covers_five_sections(loaded, reference):
    expected = reference["n_priv"] + reference["n_pub"] + 3 * reference["n_goods"]
    assert loaded["commodity_id"].shape == (expected,)


@requires_data
def test_commodity_id_equals_the_row_index(loaded):
    assert np.array_equal(loaded["commodity_id"], np.arange(len(loaded["commodity_id"])))


@requires_data
def test_commodity_kind_marks_the_five_sections_in_order(loaded, reference):
    n_priv, n_pub, n_goods = reference["n_priv"], reference["n_pub"], reference["n_goods"]
    expected = np.concatenate(
        [
            np.zeros(n_priv, dtype=np.int8),
            np.ones(n_pub, dtype=np.int8),
            np.full(n_goods, 2, dtype=np.int8),
            np.full(n_goods, 3, dtype=np.int8),
            np.full(n_goods, 4, dtype=np.int8),
        ]
    )
    assert np.array_equal(loaded["commodity_kind"], expected)


@requires_data
def test_endowment_covers_natural_resources_and_labour_only(loaded, reference):
    n_priv, n_pub, n_goods = reference["n_priv"], reference["n_pub"], reference["n_goods"]
    expected = np.concatenate(
        [
            np.zeros(n_priv + n_pub + n_goods),
            np.full(2 * n_goods, ENDOWMENT),
        ]
    )
    assert np.array_equal(loaded["endowment"], expected)


# ---- production units ----


@requires_data
def test_output_commodity_follows_the_industry_of_each_unit(loaded, reference):
    wc, bases = reference["wc"], reference["bases"]
    industry, product = wc["industry"], wc["product"]
    assert set(np.unique(industry).tolist()) <= {0, 1, 2}

    expected = np.where(
        industry == 0,
        bases["priv"] + product,
        np.where(industry == 1, bases["inter"] + product, bases["pub"] + product),
    )
    assert np.array_equal(loaded["output_commodity"], expected)


@requires_data
def test_unit_group_repeats_the_output_commodity(loaded):
    assert np.array_equal(loaded["unit_group"], loaded["output_commodity"])


@requires_data
def test_unit_id_equals_the_row_index(loaded, reference):
    assert np.array_equal(loaded["unit_id"], np.arange(len(reference["wc"]["a"])))


@requires_data
def test_every_unit_uses_the_cobb_douglas_technology(loaded, reference):
    expected = np.ones(len(reference["wc"]["a"]), dtype=np.int8)
    assert np.array_equal(loaded["technology_kind"], expected)


@requires_data
def test_technology_scale_matches_the_reference(loaded, reference):
    assert np.array_equal(loaded["technology_scale"], reference["wc"]["a"])


@requires_data
def test_input_offsets_match_the_per_unit_input_counts(loaded, reference):
    counts = reference["wc"]["mask"].sum(axis=1)
    expected = np.concatenate([[0], np.cumsum(counts)])
    assert np.array_equal(loaded["input_offsets"], expected)


@requires_data
def test_input_commodity_rebases_each_segment_onto_its_section(loaded, reference):
    wc, bases = reference["wc"], reference["bases"]
    mask = wc["mask"]
    segment_base = np.array([bases["inter"], bases["nature"], bases["labor"]], dtype=np.int64)
    expected = segment_base[wc["cat"][mask]] + wc["coef"][mask]
    assert np.array_equal(loaded["input_commodity"], expected)


@requires_data
def test_input_coefficient_follows_the_same_flattening_as_input_commodity(loaded, reference):
    wc = reference["wc"]
    assert np.array_equal(loaded["input_coefficient"], wc["b"][wc["mask"]])


@requires_data
@pytest.mark.parametrize(
    ("key", "reference_key"),
    [("effort_c", "c"), ("effort_s", "s"), ("effort_k", "k")],
)
def test_effort_parameters_match_the_reference(loaded, reference, key, reference_key):
    assert np.array_equal(loaded["unit_extra"][key], reference["wc"][reference_key])


# ---- consumption units ----


@requires_data
def test_consumer_id_equals_the_row_index(loaded, reference):
    assert np.array_equal(loaded["consumer_id"], np.arange(len(reference["cc"]["income"])))


@requires_data
def test_every_consumer_belongs_to_group_zero(loaded, reference):
    expected = np.zeros(len(reference["cc"]["income"]), dtype=np.int64)
    assert np.array_equal(loaded["consumer_group"], expected)


@requires_data
def test_entitlement_matches_the_income_column(loaded, reference):
    assert np.array_equal(loaded["consumer_extra"]["entitlement"], reference["cc"]["income"])


@requires_data
def test_utility_exponent_puts_private_columns_before_public_columns(loaded, reference):
    cc = reference["cc"]
    expected = np.hstack([cc["priv_exp"], cc["pub_exp"]])
    assert np.array_equal(loaded["consumer_extra"]["utility_exponent"], expected)


@requires_data
def test_utility_exponent_is_two_dimensional(loaded, reference):
    n_consumers = len(reference["cc"]["income"])
    columns = reference["n_priv"] + reference["n_pub"]
    assert loaded["consumer_extra"]["utility_exponent"].shape == (n_consumers, columns)


@requires_data
def test_utility_exponent_columns_map_to_private_then_public_commodities(loaded, reference):
    n_priv, bases = reference["n_priv"], reference["bases"]
    expected = np.concatenate(
        [
            np.arange(bases["priv"], bases["priv"] + n_priv),
            np.arange(bases["pub"], bases["pub"] + reference["n_pub"]),
        ]
    )
    assert np.array_equal(loaded["consumer_extra"]["utility_exponent_commodity"], expected)


# ---- scalar fields and dtypes ----


@requires_data
def test_period_starts_at_zero(loaded):
    assert loaded["period"] == 0


@requires_data
@pytest.mark.parametrize(
    ("key", "dtype"),
    [
        ("commodity_id", np.int64),
        ("commodity_kind", np.int8),
        ("endowment", np.float64),
        ("unit_id", np.int64),
        ("unit_group", np.int64),
        ("output_commodity", np.int64),
        ("technology_kind", np.int8),
        ("technology_scale", np.float64),
        ("input_offsets", np.int64),
        ("input_commodity", np.int64),
        ("input_coefficient", np.float64),
        ("consumer_id", np.int64),
        ("consumer_group", np.int64),
    ],
)
def test_column_dtype_follows_the_data_model(loaded, key, dtype):
    assert loaded[key].dtype == dtype


@requires_data
def test_utility_exponent_commodity_is_an_integer_mapping(loaded):
    assert loaded["consumer_extra"]["utility_exponent_commodity"].dtype == np.int64


@requires_data
def test_commodity_extra_bag_is_empty(loaded):
    assert loaded["commodity_extra"] == {}


# ---- rejected inputs ----


def test_missing_file_raises_load_error(tmp_path):
    with pytest.raises(_core.LoadError):
        _core.load_dep1ex(str(tmp_path / "absent.clj.gz"), ENDOWMENT)


def test_plain_text_input_raises_load_error(tmp_path):
    path = tmp_path / "not-gzip.clj.gz"
    path.write_text("(def ccs [])\n(def wcs [])\n", encoding="utf-8")

    with pytest.raises(_core.LoadError):
        _core.load_dep1ex(str(path), ENDOWMENT)


def test_load_error_is_a_value_error():
    assert issubclass(_core.LoadError, ValueError)


def test_schema_error_is_a_value_error():
    assert issubclass(_core.SchemaError, ValueError)


def test_load_error_message_carries_the_rust_text(tmp_path):
    path = tmp_path / "absent.clj.gz"
    with pytest.raises(_core.LoadError) as excinfo:
        _core.load_dep1ex(str(path), ENDOWMENT)

    assert "absent.clj.gz" in str(excinfo.value)


# ---- timing ----


@requires_data
@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("CYBERSTRIDE_RELEASE") is None,
    reason="timing is only meaningful against a release build; set CYBERSTRIDE_RELEASE=1",
)
def test_release_build_loads_dep1ex01_within_the_time_limit():
    timings = []
    for _ in range(TIMED_LOADS):
        start = time.perf_counter()
        _core.load_dep1ex(str(DEP1EX01), ENDOWMENT)
        timings.append(time.perf_counter() - start)

    assert min(timings) < LOAD_SECONDS_LIMIT, f"timings: {timings}"
