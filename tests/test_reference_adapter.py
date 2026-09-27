"""The numpy reference adapters that the differential tests are measured against.

``tests/reference/dep1ex_numpy.py`` is also the baseline the Rust loader will be compared to,
so its own translation from ``repro.parse`` output to :class:`Economy` is checked here against
the raw parse arrays.
"""

from __future__ import annotations

import numpy as np
import pytest

from reference import dep1ex_numpy, synthetic

SAMPLE_UNITS = (0, 1, 7, 1234, 15000, 29999)
SAMPLE_CONSUMERS = (0, 3, 9999, 29999)


@pytest.mark.slow
class TestDep1exLayout:
    def test_sections_are_contiguous_and_cover_everything(self, dep1ex01_parsed):
        _, _, layout = dep1ex01_parsed
        bounds = [layout.section(name) for name in ("priv", "pub", "inter", "nature", "labor")]
        assert bounds[0].start == 0
        for earlier, later in zip(bounds, bounds[1:]):
            assert earlier.stop == later.start
        assert bounds[-1].stop == layout.n_commodities

    def test_dep1ex01_dimensions(self, dep1ex01_parsed):
        _, _, layout = dep1ex01_parsed
        assert (layout.n_priv, layout.n_pub, layout.n_goods) == (100, 100, 100)
        assert layout.n_commodities == 500


@pytest.mark.slow
class TestCommodityTable:
    def test_counts(self, dep1ex01_parsed, dep1ex01_economy):
        wc, cc, layout = dep1ex01_parsed
        assert dep1ex01_economy.n_commodities == layout.n_commodities
        assert dep1ex01_economy.n_units == wc["a"].shape[0]
        assert dep1ex01_economy.n_consumers == cc["income"].shape[0]
        assert dep1ex01_economy.n_inputs == int(wc["mask"].sum())

    def test_kinds_follow_the_section_order(self, dep1ex01_parsed, dep1ex01_economy):
        _, _, layout = dep1ex01_parsed
        kinds = np.asarray(dep1ex01_economy.commodity_extra["hahnel_kind"])
        expected = {
            "priv": "private_good",
            "pub": "public_good",
            "inter": "intermediate",
            "nature": "natural_resource",
            "labor": "labor",
        }
        for name, kind in expected.items():
            assert np.all(kinds[layout.section(name)] == kind)

    def test_endowment_only_on_natural_resources_and_labor(self, dep1ex01_parsed, dep1ex01_economy):
        _, _, layout = dep1ex01_parsed
        endowment = np.asarray(dep1ex01_economy.endowment)
        assert np.all(endowment[layout.section("nature")] == 1000.0)
        assert np.all(endowment[layout.section("labor")] == 1000.0)
        assert endowment[: layout.nature_base].sum() == 0.0

    def test_the_endowment_argument_is_honoured(self, dep1ex01_parsed):
        wc, cc, layout = dep1ex01_parsed
        economy = dep1ex_numpy.economy_from_repro(wc, cc, layout, endowment=250.0)
        assert np.all(np.asarray(economy.endowment)[layout.section("labor")] == 250.0)


@pytest.mark.slow
class TestProducingUnits:
    def test_output_commodity_matches_industry_and_product(self, dep1ex01_parsed, dep1ex01_economy):
        wc, _, layout = dep1ex01_parsed
        base_of_industry = {0: layout.priv_base, 1: layout.inter_base, 2: layout.pub_base}
        for unit in SAMPLE_UNITS:
            expected = base_of_industry[int(wc["industry"][unit])] + int(wc["product"][unit])
            assert int(dep1ex01_economy.output_commodity[unit]) == expected

    def test_every_unit_has_one_output_entry_of_coefficient_one(self, dep1ex01_economy):
        economy = dep1ex01_economy
        np.testing.assert_array_equal(
            economy.output_offsets, np.arange(economy.n_units + 1, dtype=np.int64)
        )
        np.testing.assert_array_equal(economy.output_coefficient, np.ones(economy.n_units))

    def test_technology(self, dep1ex01_parsed, dep1ex01_economy):
        wc, _, _ = dep1ex01_parsed
        assert np.all(
            np.asarray(dep1ex01_economy.technology_kind) == "hahnel_cobb_douglas_effort"
        )
        np.testing.assert_array_equal(dep1ex01_economy.technology_scale, wc["a"])

    def test_effort_parameters_are_carried_in_unit_extra(self, dep1ex01_parsed, dep1ex01_economy):
        wc, _, _ = dep1ex01_parsed
        np.testing.assert_array_equal(dep1ex01_economy.unit_extra["effort_c"], wc["c"])
        np.testing.assert_array_equal(dep1ex01_economy.unit_extra["effort_s"], wc["s"])
        np.testing.assert_array_equal(dep1ex01_economy.unit_extra["effort_k"], wc["k"])


@pytest.mark.slow
class TestFlatInputs:
    def test_offsets_follow_the_padding_mask(self, dep1ex01_parsed, dep1ex01_economy):
        wc, _, _ = dep1ex01_parsed
        counts = wc["mask"].sum(axis=1)
        np.testing.assert_array_equal(np.diff(dep1ex01_economy.input_offsets), counts)
        assert int(dep1ex01_economy.input_offsets[0]) == 0
        assert int(dep1ex01_economy.input_offsets[-1]) == int(counts.sum())

    def test_row_order_is_preserved(self, dep1ex01_parsed, dep1ex01_economy):
        wc, _, layout = dep1ex01_parsed
        base_of_class = {0: layout.inter_base, 1: layout.nature_base, 2: layout.labor_base}
        for unit in SAMPLE_UNITS:
            window = dep1ex01_economy.inputs_of(unit)
            row_mask = wc["mask"][unit]
            expected_commodity = [
                base_of_class[int(wc["cat"][unit, column])] + int(wc["coef"][unit, column])
                for column in np.flatnonzero(row_mask)
            ]
            np.testing.assert_array_equal(
                dep1ex01_economy.input_commodity[window], expected_commodity
            )
            np.testing.assert_array_equal(
                dep1ex01_economy.input_coefficient[window], wc["b"][unit][row_mask]
            )

    def test_every_input_lands_in_a_usable_section(self, dep1ex01_parsed, dep1ex01_economy):
        _, _, layout = dep1ex01_parsed
        commodities = np.asarray(dep1ex01_economy.input_commodity)
        assert commodities.min() >= layout.inter_base
        assert commodities.max() < layout.n_commodities


@pytest.mark.slow
class TestConsumerUnits:
    def test_entitlement_is_the_reference_income(self, dep1ex01_parsed, dep1ex01_economy):
        _, cc, _ = dep1ex01_parsed
        np.testing.assert_array_equal(
            dep1ex01_economy.consumer_extra["entitlement"], cc["income"]
        )

    def test_utility_exponents_are_private_then_public(self, dep1ex01_parsed, dep1ex01_economy):
        _, cc, layout = dep1ex01_parsed
        exponents = dep1ex01_economy.consumer_extra["utility_exponent"]
        assert exponents.shape == (cc["income"].shape[0], layout.n_priv + layout.n_pub)
        for consumer in SAMPLE_CONSUMERS:
            np.testing.assert_array_equal(
                exponents[consumer, : layout.n_priv], cc["priv_exp"][consumer]
            )
            np.testing.assert_array_equal(
                exponents[consumer, layout.n_priv :], cc["pub_exp"][consumer]
            )

    def test_exponent_columns_map_to_the_private_and_public_sections(
        self, dep1ex01_parsed, dep1ex01_economy
    ):
        _, _, layout = dep1ex01_parsed
        columns = np.asarray(dep1ex01_economy.consumer_extra["utility_exponent_commodity"])
        kinds = np.asarray(dep1ex01_economy.commodity_extra["hahnel_kind"])[columns]
        assert np.all(kinds[: layout.n_priv] == "private_good")
        assert np.all(kinds[layout.n_priv :] == "public_good")


@pytest.mark.slow
class TestUnifiedPrice:
    def test_round_trips_through_the_sections(self, dep1ex01_parsed):
        _, _, layout = dep1ex01_parsed
        per_class = {
            "priv": np.arange(layout.n_priv, dtype=np.float64),
            "pub": np.full(layout.n_pub, 2.0),
            "inter": np.full(layout.n_goods, 3.0),
            "nature": np.full(layout.n_goods, 4.0),
            "labor": np.full(layout.n_goods, 5.0),
        }
        unified = dep1ex_numpy.unified_price(per_class, layout)
        assert unified.shape == (layout.n_commodities,)
        for name, values in per_class.items():
            np.testing.assert_array_equal(unified[layout.section(name)], values)


class TestSyntheticBuildersAgree:
    """The two synthetic builders must describe one economy, or the differential test is empty."""

    def test_unit_count_and_technology(self, synthetic_economy, synthetic_reference_inputs):
        wc, _, _, _ = synthetic_reference_inputs
        assert wc["a"].shape[0] == synthetic_economy.n_units
        np.testing.assert_array_equal(wc["a"], synthetic_economy.technology_scale)
        np.testing.assert_array_equal(wc["c"], synthetic_economy.unit_extra["effort_c"])
        np.testing.assert_array_equal(wc["s"], synthetic_economy.unit_extra["effort_s"])
        np.testing.assert_array_equal(wc["k"], synthetic_economy.unit_extra["effort_k"])

    def test_output_commodities_agree(self, synthetic_economy, synthetic_reference_inputs):
        wc, _, _, _ = synthetic_reference_inputs
        base_of_industry = {0: synthetic.PRIV_BASE, 1: synthetic.INTER_BASE, 2: synthetic.PUB_BASE}
        expected = [
            base_of_industry[int(industry)] + int(product)
            for industry, product in zip(wc["industry"], wc["product"])
        ]
        np.testing.assert_array_equal(synthetic_economy.output_commodity, expected)

    def test_inputs_agree(self, synthetic_economy, synthetic_reference_inputs):
        wc, _, _, _ = synthetic_reference_inputs
        base_of_class = {
            0: synthetic.INTER_BASE,
            1: synthetic.NATURE_BASE,
            2: synthetic.LABOR_BASE,
        }
        for unit in range(synthetic_economy.n_units):
            window = synthetic_economy.inputs_of(unit)
            columns = np.flatnonzero(wc["mask"][unit])
            expected = [
                base_of_class[int(wc["cat"][unit, column])] + int(wc["coef"][unit, column])
                for column in columns
            ]
            np.testing.assert_array_equal(synthetic_economy.input_commodity[window], expected)
            np.testing.assert_array_equal(
                synthetic_economy.input_coefficient[window], wc["b"][unit][columns]
            )

    def test_consumers_agree(self, synthetic_economy, synthetic_reference_inputs):
        _, cc, _, _ = synthetic_reference_inputs
        np.testing.assert_array_equal(
            cc["income"], synthetic_economy.consumer_extra["entitlement"]
        )
        exponents = synthetic_economy.consumer_extra["utility_exponent"]
        np.testing.assert_array_equal(cc["priv_exp"], exponents[:, : synthetic.N_PER_CLASS])
        np.testing.assert_array_equal(cc["pub_exp"], exponents[:, synthetic.N_PER_CLASS :])

    def test_endowment_agrees(self, synthetic_economy, synthetic_reference_inputs):
        _, _, _, endowment = synthetic_reference_inputs
        endowed = np.asarray(synthetic_economy.endowment)[synthetic.NATURE_BASE :]
        assert np.all(endowed == endowment)
        assert np.asarray(synthetic_economy.endowment)[: synthetic.NATURE_BASE].sum() == 0.0

    def test_the_kind_labels_follow_the_section_bases(self, synthetic_economy):
        kinds = synthetic.kind_labels(synthetic_economy)
        for base, label in (
            (synthetic.PRIV_BASE, "private_good"),
            (synthetic.PUB_BASE, "public_good"),
            (synthetic.INTER_BASE, "intermediate"),
            (synthetic.NATURE_BASE, "natural_resource"),
            (synthetic.LABOR_BASE, "labor"),
        ):
            assert np.all(kinds[base : base + synthetic.N_PER_CLASS] == label)


class TestTheJointProductEconomy:
    """The one synthetic economy whose output entries do not line up with its units."""

    def test_entries_and_units_part_after_the_first_joint_unit(self):
        joint = synthetic.build_joint_product_economy()
        base = synthetic.build_economy()
        assert joint.n_outputs > joint.n_units
        owner = np.repeat(np.arange(joint.n_units), np.diff(joint.output_offsets))
        assert not np.array_equal(owner[: joint.n_units], np.arange(joint.n_units))
        for unit in range(joint.n_units):
            window = slice(int(joint.output_offsets[unit]), int(joint.output_offsets[unit + 1]))
            assert int(base.output_commodity[unit]) in joint.output_commodity[window]

    def test_everything_but_the_outputs_is_the_base_economy(self):
        joint = synthetic.build_joint_product_economy()
        base = synthetic.build_economy()
        for name in ("commodity_id", "endowment", "technology_kind", "input_offsets",
                     "input_commodity", "input_coefficient", "consumer_id"):
            np.testing.assert_array_equal(getattr(joint, name), getattr(base, name))
