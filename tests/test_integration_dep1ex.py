"""End-to-end checks that cross the Rust/Python boundary on real dep1ex data.

The Rust loader and the numpy adapter in ``tests/reference`` are two independent readings of
the same archive; they must agree bit for bit. The prefab must then reproduce the published
round count on the economy the Rust loader produced.
"""

from __future__ import annotations

import numpy as np
import pytest

from demplan import load_dep1ex, run
from demplan.prefabs import HahnelSlides2020
from reference import dep1ex_numpy
from reference.paths import dep1ex_available, dep1ex_path

pytestmark = pytest.mark.slow

needs_data = pytest.mark.skipif(not dep1ex_available(1), reason="dep1ex01 archive not present")


@pytest.fixture(scope="module")
def rust_economy():
    return load_dep1ex(dep1ex_path(1), endowment=1000.0)


@pytest.fixture(scope="module")
def adapter_economy():
    wc, cc, layout = dep1ex_numpy.parse_dep1ex(dep1ex_path(1))
    return dep1ex_numpy.economy_from_repro(wc, cc, layout, endowment=1000.0)


@needs_data
def test_rust_loader_matches_the_numpy_adapter_bit_for_bit(rust_economy, adapter_economy):
    fixed_columns = [
        "commodity_id", "commodity_kind", "endowment",
        "unit_id", "unit_group", "output_commodity", "technology_kind", "technology_scale",
        "input_offsets", "input_commodity", "input_coefficient",
        "consumer_id", "consumer_group",
    ]
    assert rust_economy.period == adapter_economy.period
    for name in fixed_columns:
        left, right = getattr(rust_economy, name), getattr(adapter_economy, name)
        assert left.dtype == right.dtype, name
        assert np.array_equal(left, right), name
    for bag in ("commodity_extra", "unit_extra", "consumer_extra"):
        left, right = getattr(rust_economy, bag), getattr(adapter_economy, bag)
        assert set(left) == set(right), bag
        for key in left:
            assert left[key].shape == right[key].shape, f"{bag}[{key}]"
            assert np.array_equal(left[key], right[key]), f"{bag}[{key}]"


@needs_data
def test_prefab_reproduces_the_published_round_count_on_the_rust_loaded_economy(rust_economy):
    result = run(HahnelSlides2020(), rust_economy, seed=0)
    assert result.summary.converged is True
    assert result.summary.rounds == 14
    result.plan.validate(rust_economy)
