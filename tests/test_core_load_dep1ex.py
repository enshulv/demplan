"""Differential and timing tests for the dep1ex loader exposed by demplan._core.

The reference is research/bench/repro.py, the numpy parser used for the upstream
replication. Both parsers read the same decimal text, and both Rust's f64 parser
and Python's float() are correctly rounded, so every array must match bit for
bit. Assertions use np.array_equal rather than a tolerance.

The reference arrays are shaped differently from the loader output: repro pads
each unit's inputs into a rectangle and keeps the three input segments in
separate categories, so the expectations below reshape the reference rather than
restate the loader's own numbers.

The dictionary the loader returns is the contract between the Rust core and the
Python package, so its key set is checked exactly, on a hand-written archive as
well as on dep1ex01.
"""

import gzip
import hashlib
import os
import pathlib
import sys
import time

import numpy as np
import pytest

from demplan import _core

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "research" / "bench"))

import repro  # noqa: E402  (needs the sys.path entry above)

DATA_DIR = pathlib.Path(os.environ.get("DEMPLAN_DATA_DIR", REPO_ROOT / "research" / "data"))
DEP1EX01 = DATA_DIR / "dep1ex01.clj.gz"

#: Natural-resource and labour endowment per commodity, the value used in the paper.
ENDOWMENT = 1000.0

#: Wall-clock ceiling for one release-build load of dep1ex01.
LOAD_SECONDS_LIMIT = 1.5

#: Number of timed loads; the fastest one is compared against the limit.
TIMED_LOADS = 3

#: Every key of the dictionary `_core.load_dep1ex` returns, and no other.
LOADER_KEYS = {
    "period",
    "commodity_id",
    "endowment",
    "commodity_extra",
    "unit_id",
    "technology_kind",
    "technology_scale",
    "input_offsets",
    "input_commodity",
    "input_coefficient",
    "output_offsets",
    "output_commodity",
    "output_coefficient",
    "unit_extra",
    "consumer_id",
    "consumer_extra",
}

#: Technology label the loader writes for every unit: `Q = a * e^c * prod(x^b)`.
HAHNEL_TECHNOLOGY = "hahnel_cobb_douglas_effort"

#: `commodity_extra` key holding one Hahnel commodity class label per commodity.
HAHNEL_KIND = "hahnel_kind"

#: Label written on each of the five commodity sections, in section order.
SECTION_LABELS = ("private_good", "public_good", "intermediate", "natural_resource", "labor")

#: Labels of the commodities that carry the endowment.
ENDOWED_LABELS = {"natural_resource", "labor"}

#: Label of the section each `:industry` value places its output in.
INDUSTRY_LABEL = {0: "private_good", 1: "intermediate", 2: "public_good"}

#: SHA-256 fingerprints of the numeric dep1ex01 columns at endowment 1000, taken over
#: `fingerprint` below. They pin every numeric column bit for bit, including those
#: the reference parser does not produce (the commodity identifier and endowment).
DEP1EX01_FINGERPRINTS = {
    "commodity_id": "05c56a2424009843bf954cb635c42c5b8b203a32cf60940e3aa96fda7ccf6aa8",
    "consumer_extra.entitlement": "383d230bc070532921520998399d1b577e8ddf25def92d5403b800ead48b07bd",
    "consumer_extra.utility_exponent": (
        "7b1f53772fd97260457d62761b144319ffb054c69d8180ee7a65c0d6c5b4792c"
    ),
    "consumer_extra.utility_exponent_commodity": (
        "ebc99cd9dde9ac810839a36cc878c44da0a4b8d3d0e38ee3a413a2b6f4d4511c"
    ),
    "consumer_id": "56497c92afc5c3576bb101fa2996587d515e363c4de99e23a829723db5ba95f1",
    "endowment": "d08c034f42b940069d1f33056c04ff672b9ad36c49c3cdb8ae345ab05649d08c",
    "input_coefficient": "51478c923f543df902ed66770093f697630e3ca6b34b8ccca74207acb070b2a2",
    "input_commodity": "1f4e4f34f7b6bbd940072762ddbb99b3b91c096438ca75766515f8e25584c5f5",
    "input_offsets": "e4bd16219cac3f762227c6e19f4fcf0a34159e07fa2c385bd601d00f925e8fa6",
    "output_commodity": "25cc616b9bfca7b0eddfd4a7a5bd3f308b45e19f3a62148548289a7785d8e534",
    "technology_scale": "41bf8a98e8f8b49214d6361e39c96c89d2da0f574bf9c8aa044d36b24fec437e",
    "unit_extra.effort_c": "e5eda7916d41c59784cb2f956c468a9ca805ead190a6a5735f58ecdce7ee663a",
    "unit_extra.effort_k": "d5a06f418e0014088d0221a0531b9deb843c6eb47cda2ea70c6324e35d8c4e5f",
    "unit_extra.effort_s": "86d8ce7fd13f4e70294c03a665118f1e909890608b31b9e1ea8fcfc330ea1f92",
    "unit_id": "56497c92afc5c3576bb101fa2996587d515e363c4de99e23a829723db5ba95f1",
}

_skip_without_data = pytest.mark.skipif(
    not DEP1EX01.exists(),
    reason=f"scenario file not found: {DEP1EX01}",
)


def requires_data(test):
    """Skip ``test`` without dep1ex01, and mark it slow: reading the archive takes seconds."""
    return pytest.mark.slow(_skip_without_data(test))


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
    n_goods = int(wc["coef"][wc["mask"]].max()) + 1
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


def fingerprint(array) -> str:
    """SHA-256 over the dtype, the shape and the raw bytes of a numeric array."""
    array = np.ascontiguousarray(array)
    header = f"{array.dtype.str}|{array.shape}|".encode()
    return hashlib.sha256(header + array.tobytes()).hexdigest()


def section_labels(n_priv, n_pub, n_goods) -> list[str]:
    """The `hahnel_kind` column for sections of the given lengths."""
    lengths = (n_priv, n_pub, n_goods, n_goods, n_goods)
    return [label for label, length in zip(SECTION_LABELS, lengths) for _ in range(length)]


def is_list_of_str(value) -> bool:
    """True when ``value`` is a plain ``list`` whose every element is a ``str``."""
    return type(value) is list and all(type(item) is str for item in value)


# ---- dictionary contract ----


@requires_data
def test_loader_returns_exactly_the_contract_keys(loaded):
    assert set(loaded) == LOADER_KEYS


@requires_data
@pytest.mark.parametrize("column", sorted(DEP1EX01_FINGERPRINTS))
def test_numeric_column_is_bit_identical_to_its_fingerprint(loaded, column):
    bag, _, key = column.rpartition(".")
    array = loaded[bag][key] if bag else loaded[column]
    assert fingerprint(array) == DEP1EX01_FINGERPRINTS[column]


# ---- commodity table ----


@requires_data
def test_commodity_count_covers_five_sections(loaded, reference):
    expected = reference["n_priv"] + reference["n_pub"] + 3 * reference["n_goods"]
    assert loaded["commodity_id"].shape == (expected,)


@requires_data
def test_commodity_id_equals_the_row_index(loaded):
    assert np.array_equal(loaded["commodity_id"], np.arange(len(loaded["commodity_id"])))


@requires_data
def test_hahnel_kind_labels_the_five_sections_in_order(loaded, reference):
    expected = section_labels(reference["n_priv"], reference["n_pub"], reference["n_goods"])
    assert loaded["commodity_extra"][HAHNEL_KIND] == expected


@requires_data
def test_hahnel_kind_arrives_as_a_list_of_str(loaded):
    assert is_list_of_str(loaded["commodity_extra"][HAHNEL_KIND])


@requires_data
def test_endowment_sits_exactly_on_the_commodities_labelled_as_endowed(loaded):
    labels = np.array(loaded["commodity_extra"][HAHNEL_KIND])
    expected = np.where(np.isin(labels, list(ENDOWED_LABELS)), ENDOWMENT, 0.0)
    assert np.array_equal(loaded["endowment"], expected)


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
def test_output_offsets_give_every_unit_exactly_one_output_entry(loaded, reference):
    n_units = len(reference["wc"]["a"])
    assert np.array_equal(loaded["output_offsets"], np.arange(n_units + 1))


@requires_data
def test_every_output_coefficient_is_one(loaded, reference):
    n_units = len(reference["wc"]["a"])
    assert np.array_equal(loaded["output_coefficient"], np.ones(n_units))


@requires_data
def test_each_output_lands_on_the_label_its_industry_names(loaded, reference):
    labels = loaded["commodity_extra"][HAHNEL_KIND]
    output_labels = [labels[commodity] for commodity in loaded["output_commodity"].tolist()]
    expected = [INDUSTRY_LABEL[industry] for industry in reference["wc"]["industry"].tolist()]
    assert output_labels == expected


@requires_data
def test_unit_id_equals_the_row_index(loaded, reference):
    assert np.array_equal(loaded["unit_id"], np.arange(len(reference["wc"]["a"])))


@requires_data
def test_every_unit_carries_the_hahnel_effort_technology_label(loaded, reference):
    assert loaded["technology_kind"] == [HAHNEL_TECHNOLOGY] * len(reference["wc"]["a"])


@requires_data
def test_technology_kind_arrives_as_a_list_of_str(loaded):
    assert is_list_of_str(loaded["technology_kind"])


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
        ("endowment", np.float64),
        ("unit_id", np.int64),
        ("technology_scale", np.float64),
        ("input_offsets", np.int64),
        ("input_commodity", np.int64),
        ("input_coefficient", np.float64),
        ("output_offsets", np.int64),
        ("output_commodity", np.int64),
        ("output_coefficient", np.float64),
        ("consumer_id", np.int64),
    ],
)
def test_column_dtype_follows_the_data_model(loaded, key, dtype):
    assert loaded[key].dtype == dtype


@requires_data
def test_utility_exponent_commodity_is_an_integer_mapping(loaded):
    assert loaded["consumer_extra"]["utility_exponent_commodity"].dtype == np.int64


@requires_data
def test_commodity_extra_bag_holds_only_the_label_column(loaded):
    assert set(loaded["commodity_extra"]) == {HAHNEL_KIND}


@requires_data
def test_unit_extra_bag_holds_only_the_effort_parameters(loaded):
    assert set(loaded["unit_extra"]) == {"effort_c", "effort_s", "effort_k"}


@requires_data
def test_consumer_extra_bag_holds_entitlement_and_utility_exponents(loaded):
    expected = {"entitlement", "utility_exponent", "utility_exponent_commodity"}
    assert set(loaded["consumer_extra"]) == expected


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


# ---- hand-written archives ----

# The archives above are the published ones, where the largest `:product` happens
# not to exceed the largest input number. These archives separate the two, and
# push section numbers past their section, which no published archive does.


def unit_record(industry, product, inter, nature, labor):
    """One `wcs` map with the given industry, product and three input segments."""
    segments = " ".join(
        "[" + " ".join(str(number) for number in segment) + "]"
        for segment in (inter, nature, labor)
    )
    exponents = [
        f":{name}-exponents [" + " ".join("0.1" for _ in segment) + "]"
        for name, segment in (("input", inter), ("nature", nature), ("labor", labor))
    ]
    return (
        f"{{:industry {industry}, :product {product}, :s 1, :du 3.0, :c 0.61, :a 2.0, "
        f":production-inputs [{segments}], " + ", ".join(exponents) + "}"
    )


def consumer_record(private_exponents, public_exponents, income):
    """One `ccs` map with the given utility exponents and income."""
    private = " ".join(str(value) for value in private_exponents)
    public = " ".join(str(value) for value in public_exponents)
    return (
        f"{{:utility-exponents [{private}], :public-good-exponents [{public}], "
        f":income {income}}}"
    )


def write_scenario(path, consumers, units) -> str:
    """Gzips a dep1ex source file built from the two record lists and returns its path."""
    separator = "\n "
    body = "(ns fixture)\n\n(def ccs \n[{}]\n)\n\n(def wcs \n[{}]\n)\n".format(
        separator.join(consumers), separator.join(units)
    )
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(body)
    return str(path)


def test_goods_sections_are_sized_by_the_input_numbers_not_by_product(tmp_path):
    """`:product` numbers the private and public sections, which have their own lengths."""
    n_priv, n_pub, largest_input = 4, 2, 3
    consumers = [consumer_record([0.2] * n_priv, [0.2] * n_pub, 5000) for _ in range(2)]
    units = [unit_record(0, product, [1, 2], [1, 2, 3], [1, 2, 3]) for product in range(1, 5)]
    units += [unit_record(1, product, [1, 2], [1, 2, 3], [1, 2, 3]) for product in range(1, 4)]
    units += [unit_record(2, product, [1, 2], [1, 2, 3], [1, 2, 3]) for product in range(1, 3)]
    path = write_scenario(tmp_path / "product-past-inputs.clj.gz", consumers, units)

    loaded = _core.load_dep1ex(path, ENDOWMENT)

    assert loaded["commodity_id"].shape == (n_priv + n_pub + 3 * largest_input,)
    expected = section_labels(n_priv, n_pub, largest_input)
    assert loaded["commodity_extra"][HAHNEL_KIND] == expected


# Section lengths chosen so that no two of the private, public and goods sections
# are equal: a label column built with any two of those lengths swapped puts at
# least one label on the wrong row. The three goods sections share one length by
# construction of the format.
UNEVEN_PRIV, UNEVEN_PUB, UNEVEN_GOODS = 2, 5, 3


@pytest.fixture
def uneven_sections(tmp_path):
    """Loads a hand-written archive whose sections have lengths 2, 5, 3, 3, 3.

    Units, as (industry, product): (0, 2), (2, 5), (1, 3), (0, 1), (2, 1). The
    largest input number is 3, which sets the goods count.
    """
    consumers = [
        consumer_record([0.1 * (i + 1)] * UNEVEN_PRIV, [0.05] * UNEVEN_PUB, 1000 + i)
        for i in range(3)
    ]
    units = [
        unit_record(0, 2, [1], [2], [3]),
        unit_record(2, 5, [2, 3], [1], [1, 2]),
        unit_record(1, 3, [3], [3], [2]),
        unit_record(0, 1, [1, 2], [2, 3], [1]),
        unit_record(2, 1, [2], [1, 2, 3], [3]),
    ]
    path = write_scenario(tmp_path / "uneven-sections.clj.gz", consumers, units)
    return _core.load_dep1ex(path, ENDOWMENT)


def test_loader_returns_exactly_the_contract_keys_on_a_hand_written_archive(uneven_sections):
    assert set(uneven_sections) == LOADER_KEYS


def test_hahnel_kind_follows_sections_of_different_lengths(uneven_sections):
    assert uneven_sections["commodity_extra"][HAHNEL_KIND] == [
        "private_good",
        "private_good",
        "public_good",
        "public_good",
        "public_good",
        "public_good",
        "public_good",
        "intermediate",
        "intermediate",
        "intermediate",
        "natural_resource",
        "natural_resource",
        "natural_resource",
        "labor",
        "labor",
        "labor",
    ]


def test_hahnel_kind_is_the_only_commodity_extra_and_a_list_of_str(uneven_sections):
    assert set(uneven_sections["commodity_extra"]) == {HAHNEL_KIND}
    assert is_list_of_str(uneven_sections["commodity_extra"][HAHNEL_KIND])


def test_output_rows_follow_industry_and_product_on_uneven_sections(uneven_sections):
    # Rows: private 0-1, public 2-6, intermediate 7-9.
    assert uneven_sections["output_commodity"].tolist() == [1, 6, 9, 0, 2]


def test_output_labels_match_the_industry_on_uneven_sections(uneven_sections):
    labels = uneven_sections["commodity_extra"][HAHNEL_KIND]
    output_labels = [labels[row] for row in uneven_sections["output_commodity"].tolist()]
    assert output_labels == [
        "private_good",
        "public_good",
        "intermediate",
        "private_good",
        "public_good",
    ]


def test_input_rows_follow_their_segment_on_uneven_sections(uneven_sections):
    # Rows: intermediate 7-9, natural resource 10-12, labour 13-15; one line per unit.
    assert uneven_sections["input_commodity"].tolist() == [
        7, 11, 15,
        8, 9, 10, 13, 14,
        9, 12, 14,
        7, 8, 11, 12, 13,
        8, 10, 11, 12, 15,
    ]


def test_input_labels_follow_their_segment_on_uneven_sections(uneven_sections):
    labels = uneven_sections["commodity_extra"][HAHNEL_KIND]
    input_labels = [labels[row] for row in uneven_sections["input_commodity"].tolist()]
    segment_counts = [(1, 1, 1), (2, 1, 2), (1, 1, 1), (2, 2, 1), (1, 3, 1)]
    expected = []
    for inter, nature, labor in segment_counts:
        expected += ["intermediate"] * inter + ["natural_resource"] * nature + ["labor"] * labor
    assert input_labels == expected


def test_output_layout_on_a_hand_written_archive(uneven_sections):
    assert uneven_sections["output_offsets"].tolist() == [0, 1, 2, 3, 4, 5]
    assert uneven_sections["output_offsets"].dtype == np.int64
    assert uneven_sections["output_coefficient"].tolist() == [1.0] * 5
    assert uneven_sections["output_coefficient"].dtype == np.float64


def test_technology_label_on_a_hand_written_archive(uneven_sections):
    assert uneven_sections["technology_kind"] == [HAHNEL_TECHNOLOGY] * 5
    assert is_list_of_str(uneven_sections["technology_kind"])


def test_endowment_follows_the_labels_on_uneven_sections(uneven_sections):
    assert uneven_sections["endowment"].tolist() == [0.0] * 10 + [ENDOWMENT] * 6


def test_every_commodity_is_reachable_from_some_unit_or_consumer(tmp_path):
    """A section sized by the wrong rule leaves commodities nothing produces or uses."""
    consumers = [consumer_record([0.2] * 4, [0.2] * 2, 5000) for _ in range(2)]
    units = [unit_record(0, product, [1, 2], [1, 2, 3], [1, 2, 3]) for product in range(1, 5)]
    units += [unit_record(1, product, [1, 2], [1, 2, 3], [1, 2, 3]) for product in range(1, 4)]
    units += [unit_record(2, product, [1, 2], [1, 2, 3], [1, 2, 3]) for product in range(1, 3)]
    path = write_scenario(tmp_path / "no-phantoms.clj.gz", consumers, units)

    loaded = _core.load_dep1ex(path, ENDOWMENT)

    touched = set(loaded["input_commodity"].tolist())
    touched |= set(loaded["output_commodity"].tolist())
    touched |= set(loaded["consumer_extra"]["utility_exponent_commodity"].tolist())
    assert sorted(touched) == list(range(loaded["commodity_id"].shape[0]))


def test_a_product_number_past_its_section_is_rejected(tmp_path):
    """Unchecked, `:product` 3 with two private goods makes a private unit produce a public good."""
    consumers = [consumer_record([0.5, 0.25], [0.125, 0.0625], 5000) for _ in range(2)]
    units = [
        unit_record(0, 3, [1], [1], [1]),
        unit_record(1, 1, [1], [1], [1]),
        unit_record(2, 1, [1], [1], [1]),
    ]
    path = write_scenario(tmp_path / "product-past-section.clj.gz", consumers, units)

    with pytest.raises(_core.LoadError) as excinfo:
        _core.load_dep1ex(path, ENDOWMENT)

    message = str(excinfo.value)
    assert "production unit 0" in message
    assert "private" in message
    assert "[1, 2]" in message


def test_an_input_number_below_one_is_rejected(tmp_path):
    """Unchecked, intermediate input 0 lands in the public section."""
    consumers = [consumer_record([0.5, 0.25], [0.125, 0.0625], 5000) for _ in range(2)]
    units = [
        unit_record(0, 1, [0], [1], [1]),
        unit_record(1, 1, [1], [1], [1]),
        unit_record(2, 1, [1], [1], [1]),
    ]
    path = write_scenario(tmp_path / "input-below-one.clj.gz", consumers, units)

    with pytest.raises(_core.LoadError) as excinfo:
        _core.load_dep1ex(path, ENDOWMENT)

    message = str(excinfo.value)
    assert "production unit 0" in message
    assert "intermediate" in message


def test_an_input_number_is_attributed_to_the_unit_whose_record_carries_it(tmp_path):
    """The bad number sits in the third unit, so a fixed unit number in the message shows up."""
    consumers = [consumer_record([0.5, 0.25], [0.125, 0.0625], 5000) for _ in range(2)]
    units = [
        unit_record(0, 1, [1], [1], [1]),
        unit_record(1, 1, [1], [1], [1]),
        unit_record(2, 1, [1], [0], [1]),
    ]
    path = write_scenario(tmp_path / "input-below-one-third-unit.clj.gz", consumers, units)

    with pytest.raises(_core.LoadError) as excinfo:
        _core.load_dep1ex(path, ENDOWMENT)

    message = str(excinfo.value)
    assert "production unit 2" in message
    assert "nature" in message


# ---- timing ----


@requires_data
@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("DEMPLAN_RELEASE") is None,
    reason="timing is only meaningful against a release build; set DEMPLAN_RELEASE=1",
)
def test_release_build_loads_dep1ex01_within_the_time_limit():
    timings = []
    for _ in range(TIMED_LOADS):
        start = time.perf_counter()
        _core.load_dep1ex(str(DEP1EX01), ENDOWMENT)
        timings.append(time.perf_counter() - start)

    assert min(timings) < LOAD_SECONDS_LIMIT, f"timings: {timings}"
