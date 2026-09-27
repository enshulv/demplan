"""The dep1ex loader.

The parsing itself lives in the Rust core. These tests pin the Python side of the boundary:
what happens while the core does not export the loader yet, and what the Python wrapper does
with the mapping the core hands back.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from demplan import Economy, load_dep1ex

CORE_LOADER = "load_dep1ex"


def mapping_of(economy: Economy) -> dict:
    mapping = {f.name: getattr(economy, f.name) for f in dataclasses.fields(economy)}
    for bag in ("commodity_extra", "unit_extra", "consumer_extra"):
        mapping[bag] = dict(mapping[bag])
    mapping["period"] = int(mapping["period"])
    return mapping


@pytest.fixture
def core():
    from demplan import _core

    return _core


class TestCoreNotReady:
    def test_missing_loader_raises_not_implemented(self, core, monkeypatch):
        monkeypatch.delattr(core, CORE_LOADER, raising=False)
        with pytest.raises(NotImplementedError, match="load_dep1ex"):
            load_dep1ex("dep1ex01.clj.gz")

    def test_the_message_points_at_the_core(self, core, monkeypatch):
        monkeypatch.delattr(core, CORE_LOADER, raising=False)
        with pytest.raises(NotImplementedError, match="core"):
            load_dep1ex("dep1ex01.clj.gz")


class TestDelegation:
    def test_the_mapping_becomes_an_economy(self, core, monkeypatch, synthetic_economy):
        monkeypatch.setattr(
            core, CORE_LOADER, lambda path, endowment: mapping_of(synthetic_economy), raising=False
        )
        economy = load_dep1ex("dep1ex01.clj.gz")
        assert isinstance(economy, Economy)
        assert economy.n_commodities == synthetic_economy.n_commodities
        np.testing.assert_array_equal(economy.endowment, synthetic_economy.endowment)

    def test_default_endowment(self, core, monkeypatch, synthetic_economy):
        seen = {}

        def fake(path, endowment):
            seen["path"] = path
            seen["endowment"] = endowment
            return mapping_of(synthetic_economy)

        monkeypatch.setattr(core, CORE_LOADER, fake, raising=False)
        load_dep1ex("dep1ex01.clj.gz")
        assert seen["endowment"] == 1000.0

    def test_endowment_is_passed_through(self, core, monkeypatch, synthetic_economy):
        seen = {}

        def fake(path, endowment):
            seen["endowment"] = endowment
            return mapping_of(synthetic_economy)

        monkeypatch.setattr(core, CORE_LOADER, fake, raising=False)
        load_dep1ex("dep1ex01.clj.gz", endowment=250.0)
        assert seen["endowment"] == 250.0

    def test_a_path_object_reaches_the_core_as_text(self, core, monkeypatch, synthetic_economy):
        seen = {}

        def fake(path, endowment):
            seen["path"] = path
            return mapping_of(synthetic_economy)

        monkeypatch.setattr(core, CORE_LOADER, fake, raising=False)
        load_dep1ex(Path("a") / "dep1ex01.clj.gz")
        assert isinstance(seen["path"], str)
        assert seen["path"].endswith("dep1ex01.clj.gz")


CORE_KEYS = (
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
)
"""The keys of the mapping ``_core.load_dep1ex`` returns, as the binding's contract lists them."""


def core_mapping_of(economy: Economy) -> dict:
    """``economy`` in the form the binding hands it over: text columns as lists of ``str``."""
    mapping = mapping_of(economy)
    mapping["technology_kind"] = [str(label) for label in economy.technology_kind]
    mapping["commodity_extra"] = {
        key: [str(label) for label in value] if value.dtype.kind == "U" else value
        for key, value in economy.commodity_extra.items()
    }
    return mapping


class TestTheCoreMapping:
    def test_the_contract_keys_are_the_economy_fields(self):
        assert set(CORE_KEYS) == {field.name for field in dataclasses.fields(Economy)}

    def test_text_columns_handed_over_as_lists_become_text_arrays(
        self, core, monkeypatch, synthetic_economy
    ):
        handed = core_mapping_of(synthetic_economy)
        assert set(handed) == set(CORE_KEYS)
        assert isinstance(handed["technology_kind"], list)
        assert isinstance(handed["commodity_extra"]["hahnel_kind"], list)
        monkeypatch.setattr(
            core, CORE_LOADER, lambda path, endowment: handed, raising=False
        )
        economy = load_dep1ex("dep1ex01.clj.gz")
        assert economy.technology_kind.dtype.kind == "U"
        assert list(economy.technology_kind) == handed["technology_kind"]
        labels = economy.commodity_extra["hahnel_kind"]
        assert labels.dtype.kind == "U"
        assert list(labels) == handed["commodity_extra"]["hahnel_kind"]
        np.testing.assert_array_equal(economy.output_offsets, synthetic_economy.output_offsets)
        np.testing.assert_array_equal(
            economy.output_coefficient, synthetic_economy.output_coefficient
        )
