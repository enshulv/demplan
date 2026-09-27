"""The Hahnel prefab's labels and the helpers that turn them into commodity indices.

The prefab reads each commodity's class from ``commodity_extra["hahnel_kind"]``. The five
helpers are how a caller turns those labels into the index arrays the library's objectives
take (``counted``, ``shared``) and :meth:`demplan.Plan.endowment_use` takes (``resources``),
so every expected index here is read off the label column directly rather than off the helpers.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from demplan.prefabs import hahnel
from reference import synthetic

HELPERS = (
    ("private_goods", "private_good"),
    ("shared_goods", "public_good"),
    ("intermediate_goods", "intermediate"),
    ("natural_resources", "natural_resource"),
    ("labor", "labor"),
)
"""Each helper and the label it selects. ``shared_goods`` is the helper of ``public_good``."""


def selected_by_hand(economy, label: str) -> np.ndarray:
    return np.flatnonzero(synthetic.kind_labels(economy) == label).astype(np.int64)


class TestTheHelpers:
    @pytest.mark.parametrize(("helper", "label"), HELPERS)
    def test_each_helper_selects_its_label(self, synthetic_economy, helper, label):
        found = getattr(hahnel, helper)(synthetic_economy)
        np.testing.assert_array_equal(found, selected_by_hand(synthetic_economy, label))
        assert found.size == synthetic.N_PER_CLASS

    @pytest.mark.parametrize(("helper", "label"), HELPERS)
    def test_the_result_is_a_sorted_one_dimensional_int64_array(
        self, synthetic_economy, helper, label
    ):
        found = getattr(hahnel, helper)(synthetic_economy)
        assert isinstance(found, np.ndarray)
        assert found.dtype == np.int64
        assert found.ndim == 1
        assert list(found) == sorted(found)

    @pytest.mark.parametrize(("helper", "label"), HELPERS)
    def test_the_labels_are_read_where_they_sit(self, helper, label):
        """The permuted economy interleaves the private and public goods at low indices."""
        economy = synthetic.build_permuted_economy()
        found = getattr(hahnel, helper)(economy)
        np.testing.assert_array_equal(found, selected_by_hand(economy, label))

    def test_the_permuted_private_goods_are_not_the_first_three(self):
        economy = synthetic.build_permuted_economy()
        assert hahnel.private_goods(economy).tolist() != [0, 1, 2]

    def test_the_five_helpers_partition_the_commodities(self, synthetic_economy):
        found = np.concatenate(
            [getattr(hahnel, helper)(synthetic_economy) for helper, _ in HELPERS]
        )
        assert sorted(found.tolist()) == list(range(synthetic_economy.n_commodities))

    def test_a_label_nobody_carries_selects_nothing(self, synthetic_economy):
        labels = [str(label) for label in synthetic.kind_labels(synthetic_economy)]
        labels = ["private_good" if label == "intermediate" else label for label in labels]
        economy = dataclasses.replace(
            synthetic_economy, commodity_extra={"hahnel_kind": labels}
        )
        found = hahnel.intermediate_goods(economy)
        assert found.shape == (0,)
        assert found.dtype == np.int64

    def test_writing_to_a_result_leaves_the_economy_alone(self, synthetic_economy):
        found = hahnel.labor(synthetic_economy)
        found[:] = 0
        np.testing.assert_array_equal(
            hahnel.labor(synthetic_economy), selected_by_hand(synthetic_economy, "labor")
        )


class TestTheHelpersRefuseWhatTheyCannotRead:
    @pytest.mark.parametrize(("helper", "label"), HELPERS)
    def test_a_missing_label_column_is_refused_naming_the_key(
        self, synthetic_economy, helper, label
    ):
        economy = dataclasses.replace(synthetic_economy, commodity_extra={})
        with pytest.raises(ValueError) as refused:
            getattr(hahnel, helper)(economy)
        message = str(refused.value)
        assert "commodity_extra['hahnel_kind']" in message
        assert helper in message

    def test_an_unknown_label_is_refused(self, synthetic_economy):
        """A misspelt label would drop its commodity from every selection without a word."""
        labels = [str(label) for label in synthetic.kind_labels(synthetic_economy)]
        labels[4] = "public good"
        economy = dataclasses.replace(
            synthetic_economy, commodity_extra={"hahnel_kind": labels}
        )
        with pytest.raises(ValueError, match="'public good'.*commodity 4"):
            hahnel.private_goods(economy)

    def test_a_numeric_column_under_the_key_is_refused(self, synthetic_economy):
        economy = dataclasses.replace(
            synthetic_economy,
            commodity_extra={"hahnel_kind": np.zeros(synthetic_economy.n_commodities)},
        )
        with pytest.raises(ValueError, match="hahnel_kind"):
            hahnel.labor(economy)


class TestThePackageSurface:
    NAMES = (
        "TECHNOLOGY",
        "PRIVATE_GOOD",
        "PUBLIC_GOOD",
        "INTERMEDIATE",
        "NATURAL_RESOURCE",
        "LABOR",
        "private_goods",
        "shared_goods",
        "intermediate_goods",
        "natural_resources",
        "labor",
    )

    @pytest.mark.parametrize("name", NAMES)
    def test_every_name_is_exported(self, name):
        assert hasattr(hahnel, name)
        assert name in hahnel.__all__

    def test_the_export_list_stays_in_ascii_order(self):
        assert list(hahnel.__all__) == sorted(hahnel.__all__)


@pytest.mark.slow
class TestOnDep1ex01:
    def test_the_helpers_give_the_five_sections(self, dep1ex01_parsed, dep1ex01_economy):
        _, _, layout = dep1ex01_parsed
        for helper, section in (
            ("private_goods", "priv"),
            ("shared_goods", "pub"),
            ("intermediate_goods", "inter"),
            ("natural_resources", "nature"),
            ("labor", "labor"),
        ):
            span = layout.section(section)
            np.testing.assert_array_equal(
                getattr(hahnel, helper)(dep1ex01_economy),
                np.arange(span.start, span.stop, dtype=np.int64),
            )
