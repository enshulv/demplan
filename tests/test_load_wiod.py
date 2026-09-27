"""The WIOD loader on small workbooks written by the test.

Every test here goes through the real Rust core: the workbooks are laid out like the WIOD 2016
release (see ``reference/wiod_workbooks.py``) but hold a few cells, so reading them takes
milliseconds. What the real release adds -- its size and its data -- is in
``test_load_wiod_real_data.py``.

The standard table has three economies, ``AAA``, ``BBB`` and ``ROW``, and two industries, ``A01``
and ``U``. Products, in row order: 0 AAA A01, 1 AAA U, 2 BBB A01, 3 BBB U, 4 ROW A01, 5 ROW U.
Products 1 and 5 have no output, so the producing units make products 0, 2, 3 and 4. Every row
satisfies ``sum of intermediate use + sum of final demand = gross output``.
"""

from __future__ import annotations

import dataclasses
import warnings
from pathlib import Path

import numpy as np
import pytest

import demplan
from demplan import AllocatedPlan, Economy, WiodTable, load_wiod
from demplan.io import WiodLaborGap
from reference.wiod_workbooks import (
    FINAL_DEMAND,
    TOTALS,
    Integer,
    WiotTable,
    release_entry,
    write_release_zip,
    write_xlsb,
    write_xlsx,
)

YEAR = 2014

UNIT_PRODUCTS = [0, 2, 3, 4]
"""Products of the standard table with positive gross output, in row order."""


def standard_table() -> WiotTable:
    z = [
        [10.0, 0.0, 20.0, 5.0, 0.0, 0.0],
        [0.0] * 6,
        [0.0, 0.0, 30.0, 0.0, 40.0, 0.0],
        [3.0, 0.0, 0.0, 0.0, 25.0, 0.0],
        [0.0, 0.0, 7.0, 2.0, 1.0, 0.0],
        [0.0] * 6,
    ]
    final_demand = [[0.0] * 15 for _ in range(6)]
    final_demand[0][:5] = [40.0, 5.0, 10.0, 15.0, -5.0]
    final_demand[2][5] = 100.0
    final_demand[2][8] = 30.0
    final_demand[3][0] = 22.0
    final_demand[4][10] = 400.0
    final_demand[4][14] = -10.0
    return WiotTable(
        economies=["AAA", "BBB", "ROW"],
        industries=["A01", "U"],
        z=z,
        final_demand=final_demand,
        gross_output=[100.0, 0.0, 200.0, 50.0, 400.0, 0.0],
    )


def other_year_table() -> WiotTable:
    """The standard table with every value doubled, to tell two years apart."""
    table = standard_table()
    return WiotTable(
        economies=table.economies,
        industries=table.industries,
        z=[[2 * value for value in row] for row in table.z],
        final_demand=[[2 * value for value in row] for row in table.final_demand],
        gross_output=[2 * value for value in table.gross_output],
    )


def sea_rows() -> list[list[object]]:
    """Socio-economic accounts: ``AAA`` has both variables, ``BBB`` has no hours, no ``ROW``."""
    header = ["country", "variable", "description", "code", 2013.0, 2014.0]
    return [
        header,
        ["AAA", "COMP", "Compensation of employees", "A01", 1.0, 10.0],
        ["AAA", "COMP", "Compensation of employees", "U", 1.0, 3.0],
        ["AAA", "H_EMPE", "Hours worked by employees", "A01", 1.0, 40.0],
        ["AAA", "H_EMPE", "Hours worked by employees", "U", 1.0, 0.0],
        ["BBB", "COMP", "Compensation of employees", "A01", 1.0, 20.0],
        ["BBB", "COMP", "Compensation of employees", "U", 1.0, 6.0],
        ["BBB", "H_EMPE", "Hours worked by employees", "A01", "NA", "NA"],
        ["BBB", "H_EMPE", "Hours worked by employees", "U", "NA", "NA"],
    ]


def exchange_rate_rows() -> list[list[object]]:
    return [
        ["Exchange rates"],
        [" US$ per Unit of Local currency"],
        [],
        ["Country", "Acronym", "_2013", "_2014"],
        ["Aland", "AAA", 0.5, 0.25],
        ["Bland", "BBB", 2.0, 4.0],
    ]


@pytest.fixture
def xlsb(tmp_path) -> Path:
    return write_xlsb(tmp_path / release_entry(YEAR), {str(YEAR): standard_table().cells()})


@pytest.fixture
def release_zip(tmp_path) -> Path:
    return write_release_zip(
        tmp_path / "WIOTS_in_EXCEL.zip", {2013: other_year_table(), YEAR: standard_table()}
    )


@pytest.fixture
def sea(tmp_path) -> Path:
    return write_xlsx(tmp_path / "Socio_Economic_Accounts.xlsx", {"Notes": [["notes"]], "DATA": sea_rows()})


@pytest.fixture
def exchange_rates(tmp_path) -> Path:
    return write_xlsx(
        tmp_path / "Exchange_Rates.xlsx", {"Notes": [["notes"]], "EXR": exchange_rate_rows()}
    )


def load_quietly(*args, **kwargs) -> WiodTable:
    """``load_wiod`` with the labour-gap warning silenced, for tests about something else."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", WiodLaborGap)
        return load_wiod(*args, **kwargs)


def gap_warnings(record) -> list[warnings.WarningMessage]:
    return [entry for entry in record if issubclass(entry.category, WiodLaborGap)]


def window(economy: Economy, unit: int) -> slice:
    return economy.inputs_of(unit)


# ------------------------------------------------------------------------------ result


class TestTheResult:
    def test_it_is_a_frozen_dataclass_of_the_economy_and_the_observed_plan(self, xlsb):
        table = load_wiod(xlsb, YEAR)
        assert isinstance(table, WiodTable)
        assert [field.name for field in dataclasses.fields(WiodTable)] == ["economy", "observed"]
        assert isinstance(table.economy, Economy)
        assert isinstance(table.observed, AllocatedPlan)
        with pytest.raises(dataclasses.FrozenInstanceError):
            table.economy = table.economy

    def test_the_package_exports_the_loader_and_its_result(self):
        assert "load_wiod" in demplan.__all__
        assert "WiodTable" in demplan.__all__
        assert demplan.load_wiod is load_wiod
        assert issubclass(WiodLaborGap, UserWarning)

    def test_the_economy_is_in_the_period_of_the_year(self, xlsb):
        assert load_wiod(xlsb, YEAR).economy.period == YEAR

    def test_the_observed_plan_passes_its_own_validation(self, xlsb):
        table = load_wiod(xlsb, YEAR)
        table.observed.validate(table.economy)

    def test_a_path_given_as_text_is_accepted(self, xlsb):
        assert load_wiod(str(xlsb), YEAR).economy.n_commodities == 6


# ------------------------------------------------------------------------------ economy


class TestCommodities:
    def test_every_product_is_a_commodity_in_row_order_labelled_by_region_and_industry(
        self, xlsb
    ):
        economy = load_wiod(xlsb, YEAR).economy
        assert economy.n_commodities == 6
        np.testing.assert_array_equal(economy.endowment, np.zeros(6))
        region = economy.commodity_extra["region"]
        industry = economy.commodity_extra["industry"]
        assert region.dtype.kind == "U" and industry.dtype.kind == "U"
        assert list(region) == ["AAA", "AAA", "BBB", "BBB", "ROW", "ROW"]
        assert list(industry) == ["A01", "U", "A01", "U", "A01", "U"]


class TestProducingUnits:
    def test_only_products_with_positive_output_get_a_unit(self, xlsb):
        economy = load_wiod(xlsb, YEAR).economy
        np.testing.assert_array_equal(economy.output_commodity, UNIT_PRODUCTS)
        np.testing.assert_array_equal(economy.output_offsets, np.arange(5))
        np.testing.assert_array_equal(economy.output_coefficient, np.ones(4))

    def test_every_unit_is_labelled_leontief_at_scale_one(self, xlsb):
        economy = load_wiod(xlsb, YEAR).economy
        assert list(economy.technology_kind) == [demplan.LEONTIEF] * 4
        np.testing.assert_array_equal(economy.technology_scale, np.ones(4))

    def test_inputs_are_the_positive_intermediate_uses_over_the_unit_output(self, xlsb):
        table = standard_table()
        economy = load_wiod(xlsb, YEAR).economy
        for unit, j in enumerate(UNIT_PRODUCTS):
            rows = [i for i in range(6) if table.z[i][j] > 0]
            expected = [table.z[i][j] / table.gross_output[j] for i in rows]
            np.testing.assert_array_equal(economy.input_commodity[window(economy, unit)], rows)
            np.testing.assert_array_equal(economy.input_coefficient[window(economy, unit)], expected)

    def test_unit_extra_carries_labels_and_the_totals_rows(self, xlsb):
        table = standard_table()
        extra = load_wiod(xlsb, YEAR).economy.unit_extra
        assert list(extra["region"]) == ["AAA", "BBB", "BBB", "ROW"]
        assert list(extra["industry"]) == ["A01", "A01", "U", "A01"]
        for k, (_, key) in enumerate(TOTALS):
            assert extra[key].dtype == np.float64
            np.testing.assert_array_equal(extra[key], [table.totals[k][j] for j in UNIT_PRODUCTS])
        assert "labor_observed" not in extra


class TestConsumerUnits:
    def test_one_consumer_unit_per_final_demand_column(self, xlsb):
        economy = load_wiod(xlsb, YEAR).economy
        assert economy.n_consumers == 15
        assert list(economy.consumer_extra["region"]) == ["AAA"] * 5 + ["BBB"] * 5 + ["ROW"] * 5
        assert list(economy.consumer_extra["final_demand"]) == list(FINAL_DEMAND) * 3


# ------------------------------------------------------------------------------ observed plan


class TestObservedPlan:
    def test_output_is_the_gross_output_of_each_unit(self, xlsb):
        observed = load_wiod(xlsb, YEAR).observed
        np.testing.assert_array_equal(observed.output, [100.0, 200.0, 50.0, 400.0])

    def test_input_use_is_the_intermediate_use_of_each_entry(self, xlsb):
        table = standard_table()
        loaded = load_wiod(xlsb, YEAR)
        economy = loaded.economy
        for unit, j in enumerate(UNIT_PRODUCTS):
            used = [table.z[i][j] for i in economy.input_commodity[window(economy, unit)]]
            np.testing.assert_array_equal(loaded.observed.input_use[window(economy, unit)], used)

    def test_consumption_is_final_demand_with_negative_values_kept(self, xlsb):
        table = standard_table()
        observed = load_wiod(xlsb, YEAR).observed
        expected = np.array(table.final_demand).T
        assert observed.consumption.shape == (15, 6)
        np.testing.assert_array_equal(observed.consumption, expected)
        assert observed.consumption[4, 0] == -5.0
        assert observed.consumption[14, 4] == -10.0
        np.testing.assert_array_equal(observed.consumption_commodity, np.arange(6))

    def test_shared_use_is_zero_and_the_bags_are_empty(self, xlsb):
        observed = load_wiod(xlsb, YEAR).observed
        np.testing.assert_array_equal(observed.shared_use, np.zeros(6))
        assert dict(observed.valuation) == {}
        assert dict(observed.extra) == {}

    def test_every_product_row_balances_against_its_gross_output(self, xlsb):
        table = standard_table()
        loaded = load_wiod(xlsb, YEAR)
        economy, observed = loaded.economy, loaded.observed
        used = np.bincount(economy.input_commodity, weights=observed.input_use, minlength=6)
        final = observed.consumption.sum(axis=0)
        np.testing.assert_allclose(used + final, table.gross_output, rtol=0, atol=1e-12)


class TestIntegerCells:
    def test_integer_cells_are_read_as_numbers(self, tmp_path):
        table = standard_table()
        cells = table.cells()
        cells[(8, 6)] = Integer(30)  # product 2's use by product 2, written as an RK cell
        cells[(8, 4 + 6 + 15)] = Integer(200)  # product 2's gross output
        path = write_xlsb(tmp_path / "ints.xlsb", {str(YEAR): cells})
        loaded = load_wiod(path, YEAR)
        assert loaded.observed.output[1] == 200.0
        assert 30.0 in loaded.observed.input_use[window(loaded.economy, 1)]


# ------------------------------------------------------------------------------ files and years


class TestFilesAndYears:
    def test_the_release_zip_is_read_at_the_year_entry(self, release_zip, xlsb):
        from_zip = load_wiod(release_zip, YEAR)
        np.testing.assert_array_equal(from_zip.observed.output, [100.0, 200.0, 50.0, 400.0])
        earlier = load_wiod(release_zip, 2013)
        np.testing.assert_array_equal(earlier.observed.output, [200.0, 400.0, 100.0, 800.0])
        assert earlier.economy.period == 2013

    def test_the_zip_and_the_extracted_workbook_give_identical_arrays(self, release_zip, xlsb):
        assert_identical(load_wiod(release_zip, YEAR), load_wiod(xlsb, YEAR))

    def test_two_loads_give_identical_arrays(self, xlsb):
        assert_identical(load_wiod(xlsb, YEAR), load_wiod(xlsb, YEAR))

    def test_a_zip_without_the_year_is_refused(self, tmp_path):
        path = write_release_zip(tmp_path / "WIOTS_in_EXCEL.zip", {2013: standard_table()})
        with pytest.raises(ValueError, match=release_entry(YEAR)):
            load_wiod(path, YEAR)

    def test_a_workbook_whose_sheet_is_another_year_is_refused(self, tmp_path):
        path = write_xlsb(tmp_path / "table.xlsb", {"2013": standard_table().cells()})
        with pytest.raises(ValueError, match="2013"):
            load_wiod(path, YEAR)

    @pytest.mark.parametrize("year", [1999, 2015])
    def test_a_year_outside_the_release_is_refused_before_the_file_is_read(self, tmp_path, year):
        with pytest.raises(ValueError, match="2000 to 2014"):
            load_wiod(tmp_path / "does_not_exist.zip", year)

    def test_a_missing_file_is_refused_with_its_path(self, tmp_path):
        with pytest.raises(ValueError, match="does_not_exist"):
            load_wiod(tmp_path / "does_not_exist.xlsb", YEAR)


def assert_identical(first: WiodTable, second: WiodTable) -> None:
    """Every array of the two economies and plans is equal in dtype, shape and bits."""
    for name in [field.name for field in dataclasses.fields(Economy)]:
        left, right = getattr(first.economy, name), getattr(second.economy, name)
        if name.endswith("_extra"):
            assert sorted(left) == sorted(right), name
            for key in left:
                assert_same_array(left[key], right[key], f"{name}[{key!r}]")
        elif isinstance(left, np.ndarray):
            assert_same_array(left, right, name)
        else:
            assert left == right, name
    for name in ("output", "input_use", "consumption", "consumption_commodity", "shared_use"):
        assert_same_array(getattr(first.observed, name), getattr(second.observed, name), name)


def assert_same_array(left: np.ndarray, right: np.ndarray, name: str) -> None:
    assert left.dtype == right.dtype, name
    assert left.shape == right.shape, name
    if left.dtype.kind == "U":
        assert list(left) == list(right), name
    else:
        assert left.tobytes() == right.tobytes(), name


# ------------------------------------------------------------------------------ labour


class TestLaborArgument:
    def test_an_unknown_measure_is_refused_listing_the_three(self, xlsb):
        with pytest.raises(ValueError) as caught:
            load_wiod(xlsb, YEAR, labor="wages")
        message = str(caught.value)
        for choice in ("None", "'compensation'", "'hours'"):
            assert choice in message

    def test_compensation_without_the_accounts_names_sea(self, xlsb, exchange_rates):
        with pytest.raises(ValueError, match=r"\bsea\b.*Socio_Economic_Accounts"):
            load_wiod(xlsb, YEAR, labor="compensation", exchange_rates=exchange_rates)

    def test_compensation_without_the_rates_names_exchange_rates(self, xlsb, sea):
        with pytest.raises(ValueError, match=r"\bexchange_rates\b.*Exchange_Rates"):
            load_wiod(xlsb, YEAR, labor="compensation", sea=sea)

    def test_hours_without_the_accounts_names_sea(self, xlsb):
        with pytest.raises(ValueError, match=r"\bsea\b.*Socio_Economic_Accounts"):
            load_wiod(xlsb, YEAR, labor="hours")

    def test_the_docstring_says_what_each_measure_counts_and_who_lacks_it(self):
        text = " ".join(load_wiod.__doc__.split())
        for phrase in (
            "compensation",
            "hours worked by employees",
            "self-employed",
            "theoretical choice",
            "ROW",
            "CHN",
        ):
            assert phrase in text, phrase


class TestWithoutLabor:
    def test_no_labour_commodity_no_flag_and_no_warning(self, xlsb):
        with warnings.catch_warnings(record=True) as record:
            warnings.simplefilter("always")
            economy = load_wiod(xlsb, YEAR).economy
        assert gap_warnings(record) == []
        assert economy.n_commodities == 6
        assert "labor_observed" not in economy.unit_extra


class TestCompensation:
    @pytest.fixture
    def loaded(self, xlsb, sea, exchange_rates):
        return load_quietly(
            xlsb, YEAR, labor="compensation", sea=sea, exchange_rates=exchange_rates
        )

    def test_one_labour_commodity_per_economy_with_data_after_the_products(self, loaded):
        extra = loaded.economy.commodity_extra
        assert list(extra["region"][6:]) == ["AAA", "BBB"]
        assert list(extra["industry"][6:]) == ["labor", "labor"]

    def test_labour_is_compensation_in_us_dollars_at_the_year_rate(self, loaded):
        economy, observed = loaded.economy, loaded.observed
        # AAA A01: 10 x 0.25. BBB A01: 20 x 4. BBB U: 6 x 4.
        expected = {0: (6, 10.0 * 0.25), 1: (7, 20.0 * 4.0), 2: (7, 6.0 * 4.0)}
        for unit, (commodity, labour) in expected.items():
            entries = window(economy, unit)
            assert economy.input_commodity[entries][-1] == commodity
            assert observed.input_use[entries][-1] == labour
            assert economy.input_coefficient[entries][-1] == labour / observed.output[unit]

    def test_the_labour_endowment_is_the_economy_total(self, loaded):
        np.testing.assert_array_equal(loaded.economy.endowment[6:], [10.0 * 0.25, 26.0 * 4.0])

    def test_the_unit_without_data_is_flagged(self, loaded):
        np.testing.assert_array_equal(
            loaded.economy.unit_extra["labor_observed"], [1.0, 1.0, 1.0, 0.0]
        )

    def test_one_warning_names_the_economy_without_data(
        self, xlsb, sea, exchange_rates
    ):
        with pytest.warns(WiodLaborGap) as record:
            load_wiod(xlsb, YEAR, labor="compensation", sea=sea, exchange_rates=exchange_rates)
        gaps = gap_warnings(record)
        assert len(gaps) == 1
        message = str(gaps[0].message)
        assert "ROW (1 unit)" in message
        assert "AAA" not in message and "BBB" not in message

    def test_the_observed_plan_still_validates(self, loaded):
        loaded.observed.validate(loaded.economy)


class TestHours:
    def test_labour_is_hours_worked_by_employees(self, xlsb, sea):
        loaded = load_quietly(xlsb, YEAR, labor="hours", sea=sea)
        economy = loaded.economy
        assert list(economy.commodity_extra["region"][6:]) == ["AAA"]
        entries = window(economy, 0)
        assert economy.input_commodity[entries][-1] == 6
        assert loaded.observed.input_use[entries][-1] == 40.0
        assert economy.endowment[6] == 40.0

    def test_one_warning_names_every_economy_without_hours_and_its_unit_count(self, xlsb, sea):
        with pytest.warns(WiodLaborGap) as record:
            load_wiod(xlsb, YEAR, labor="hours", sea=sea)
        gaps = gap_warnings(record)
        assert len(gaps) == 1
        message = str(gaps[0].message)
        assert "BBB (2 units)" in message
        assert "ROW (1 unit)" in message
        assert message.index("BBB") < message.index("ROW")

    def test_the_warning_lists_economies_in_the_table_order(self, tmp_path, sea):
        table = WiotTable(
            economies=["ROW", "BBB"],
            industries=["A01"],
            z=[[1.0, 0.0], [0.0, 1.0]],
            final_demand=[[9.0] + [0.0] * 9, [0.0] * 5 + [9.0] + [0.0] * 4],
            gross_output=[10.0, 10.0],
        )
        path = write_xlsb(tmp_path / "row_first.xlsb", {str(YEAR): table.cells()})
        with pytest.warns(WiodLaborGap) as record:
            load_wiod(path, YEAR, labor="hours", sea=sea)
        message = str(gap_warnings(record)[0].message)
        assert message.index("ROW (1 unit)") < message.index("BBB (1 unit)")

    def test_the_units_without_hours_are_flagged(self, xlsb, sea):
        economy = load_quietly(xlsb, YEAR, labor="hours", sea=sea).economy
        np.testing.assert_array_equal(economy.unit_extra["labor_observed"], [1.0, 0.0, 0.0, 0.0])

    def test_a_table_every_unit_of_which_has_data_emits_no_warning(self, tmp_path, sea):
        table = WiotTable(
            economies=["AAA"],
            industries=["A01", "U"],
            z=[[10.0, 0.0], [0.0, 0.0]],
            final_demand=[[90.0, 0.0, 0.0, 0.0, 0.0], [0.0] * 5],
            gross_output=[100.0, 0.0],
        )
        path = write_xlsb(tmp_path / "aaa.xlsb", {str(YEAR): table.cells()})
        with warnings.catch_warnings(record=True) as record:
            warnings.simplefilter("always")
            economy = load_wiod(path, YEAR, labor="hours", sea=sea).economy
        assert gap_warnings(record) == []
        np.testing.assert_array_equal(economy.unit_extra["labor_observed"], [1.0])


class TestRomaniaExchangeRate:
    """The exchange-rate workbook lists Romania as ``ROM``; the table and the accounts use ``ROU``."""

    def test_compensation_for_rou_uses_the_rate_listed_under_rom(self, tmp_path):
        table = WiotTable(
            economies=["ROU"],
            industries=["A01", "U"],
            z=[[10.0, 0.0], [0.0, 0.0]],
            final_demand=[[90.0, 0.0, 0.0, 0.0, 0.0], [0.0] * 5],
            gross_output=[100.0, 0.0],
        )
        path = write_xlsb(tmp_path / "rou.xlsb", {str(YEAR): table.cells()})
        sea = write_xlsx(
            tmp_path / "Socio_Economic_Accounts.xlsx",
            {"DATA": [
                ["country", "variable", "description", "code", 2014.0],
                ["ROU", "COMP", "Compensation of employees", "A01", 30.0],
            ]},
        )
        rates = write_xlsx(
            tmp_path / "Exchange_Rates.xlsx",
            {"EXR": [["Country", "Acronym", "_2014"], ["Romania", "ROM", 0.3]]},
        )
        with warnings.catch_warnings(record=True) as record:
            warnings.simplefilter("always")
            loaded = load_wiod(path, YEAR, labor="compensation", sea=sea, exchange_rates=rates)
        assert gap_warnings(record) == []
        economy = loaded.economy
        assert list(economy.commodity_extra["region"][2:]) == ["ROU"]
        assert economy.endowment[2] == 30.0 * 0.3
        np.testing.assert_array_equal(economy.unit_extra["labor_observed"], [1.0])


class TestNegativeIntermediateUse:
    def test_a_negative_entry_is_refused_naming_year_products_and_value(self, tmp_path):
        table = standard_table()
        table.z[3][0] = -1.5  # BBB U used by the industry making AAA A01
        path = write_xlsb(tmp_path / "negative.xlsb", {str(YEAR): table.cells()})
        with pytest.raises(ValueError) as caught:
            load_wiod(path, YEAR)
        message = str(caught.value)
        for part in (str(YEAR), "BBB U", "AAA A01", "-1.5"):
            assert part in message, part
