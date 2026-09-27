"""The WIOD loader on the real 2016 release, year 2014.

The release is not in the repository. These tests look for it under ``<DEMPLAN_DATA_DIR>/wiod``:
``WIOTS_in_EXCEL.zip``, ``xlsb/WIOT2014_Nov16_ROW.xlsb`` (the same table extracted),
``Socio_Economic_Accounts.xlsx`` and ``Exchange_Rates.xlsx``; they skip without them. Each load
takes about a second, so the module is in the slow layer.

What is checked against what:

- the table's own identities: every product row's intermediate and final use add up to its gross
  output (the published table satisfies this to 6e-12 relative), and every unit's coefficients
  times its output give back the intermediate use;
- counts and cells read once from the release with a separate reader (calamine, outside the
  library): 137 products without output, the negative final-demand entries, and the totals of
  the first product column;
- the socio-economic accounts, read here by ``reference.wiod_workbooks.read_xlsx_rows``, which
  shares no code with the loader.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

from demplan import load_wiod
from demplan.io import WiodLaborGap
from reference.paths import DATA_DIR
from reference.wiod_workbooks import read_xlsx_rows
from test_load_wiod import assert_identical

pytestmark = pytest.mark.slow

YEAR = 2014
WIOD_DIR = DATA_DIR / "wiod"
RELEASE_ZIP = WIOD_DIR / "WIOTS_in_EXCEL.zip"
EXTRACTED = WIOD_DIR / "xlsb" / f"WIOT{YEAR}_Nov16_ROW.xlsb"
SEA = WIOD_DIR / "Socio_Economic_Accounts.xlsx"
EXCHANGE_RATES = WIOD_DIR / "Exchange_Rates.xlsx"

N_ECONOMIES = 44
N_INDUSTRIES = 56
N_PRODUCTS = N_ECONOMIES * N_INDUSTRIES
N_WITHOUT_OUTPUT = 137


def require(*paths):
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        pytest.skip(f"WIOD release files not found: {', '.join(missing)}")


@pytest.fixture(scope="module")
def table():
    require(RELEASE_ZIP)
    return load_wiod(RELEASE_ZIP, YEAR)


@pytest.fixture(scope="module")
def compensation():
    require(RELEASE_ZIP, SEA, EXCHANGE_RATES)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", WiodLaborGap)
        return load_wiod(
            RELEASE_ZIP, YEAR, labor="compensation", sea=SEA, exchange_rates=EXCHANGE_RATES
        )


class TestTheTable:
    def test_every_product_is_a_commodity(self, table):
        economy = table.economy
        assert economy.n_commodities == N_PRODUCTS
        region = economy.commodity_extra["region"]
        industry = economy.commodity_extra["industry"]
        assert (region[0], industry[0]) == ("AUS", "A01")
        assert (region[-1], industry[-1]) == ("ROW", "U")
        assert len(set(region)) == N_ECONOMIES
        assert len(set(industry)) == N_INDUSTRIES

    def test_products_without_output_get_no_unit(self, table):
        economy, observed = table.economy, table.observed
        assert economy.n_units == N_PRODUCTS - N_WITHOUT_OUTPUT
        assert (observed.output > 0).all()
        without_unit = np.setdiff1d(np.arange(N_PRODUCTS), economy.output_commodity)
        assert without_unit.size == N_WITHOUT_OUTPUT
        # A product without output is used by no one: its row adds up to zero.
        used = np.bincount(
            economy.input_commodity, weights=observed.input_use, minlength=N_PRODUCTS
        )
        final = observed.consumption.sum(axis=0)
        assert np.abs(used + final)[without_unit].max() == 0.0

    def test_every_product_row_balances_against_its_gross_output(self, table):
        economy, observed = table.economy, table.observed
        used = np.bincount(
            economy.input_commodity, weights=observed.input_use, minlength=N_PRODUCTS
        )
        final = observed.consumption.sum(axis=0)
        gross_output = np.zeros(N_PRODUCTS)
        gross_output[economy.output_commodity] = observed.output
        produced = economy.output_commodity
        relative = np.abs(used + final - gross_output)[produced] / gross_output[produced]
        assert relative.max() <= 1e-9

    def test_coefficients_times_output_give_back_the_intermediate_use(self, table):
        economy, observed = table.economy, table.observed
        owner = np.repeat(np.arange(economy.n_units), np.diff(economy.input_offsets))
        rebuilt = economy.input_coefficient * observed.output[owner]
        np.testing.assert_allclose(rebuilt, observed.input_use, rtol=1e-12, atol=0)
        assert (observed.input_use > 0).all()

    def test_the_first_unit_carries_the_cells_of_its_column(self, table):
        extra = table.economy.unit_extra
        assert (extra["region"][0], extra["industry"][0]) == ("AUS", "A01")
        assert table.observed.output[0] == 70292.03449229615
        assert extra["taxes_less_subsidies"][0] == 501.9267544633926
        assert extra["value_added"][0] == 30489.19020396576
        assert extra["international_transport_margins"][0] == 261.67871833060394

    def test_negative_taxes_and_value_added_are_kept(self, table):
        extra = table.economy.unit_extra
        assert int((extra["taxes_less_subsidies"] < 0).sum()) == 113
        assert int((extra["value_added"] < 0).sum()) == 4

    def test_the_three_adjustment_rows_are_zero_in_2014(self, table):
        extra = table.economy.unit_extra
        for key in ("cif_fob_adjustment", "purchases_by_residents_abroad", "purchases_by_nonresidents"):
            assert (extra[key] == 0.0).all(), key

    def test_negative_final_demand_is_kept(self, table):
        economy, observed = table.economy, table.observed
        category = economy.consumer_extra["final_demand"]
        negative = observed.consumption < 0
        assert int(negative[category == "GFCF"].sum()) == 54
        assert int(negative[category == "INVEN"].sum()) == 2055
        assert int(negative[~np.isin(category, ["GFCF", "INVEN"])].sum()) == 0

    def test_consumer_units_follow_the_final_demand_columns(self, table):
        extra = table.economy.consumer_extra
        assert table.economy.n_consumers == N_ECONOMIES * 5
        assert (extra["region"][0], extra["final_demand"][0]) == ("AUS", "CONS_h")
        assert (extra["region"][-1], extra["final_demand"][-1]) == ("ROW", "INVEN")

    def test_the_observed_plan_passes_its_own_validation(self, table):
        table.observed.validate(table.economy)
        np.testing.assert_array_equal(table.observed.shared_use, np.zeros(N_PRODUCTS))


class TestFilesAndRepeatability:
    def test_the_zip_and_the_extracted_workbook_give_identical_arrays(self, table):
        require(EXTRACTED)
        assert_identical(table, load_wiod(EXTRACTED, YEAR))

    def test_two_loads_give_identical_arrays(self, table):
        assert_identical(table, load_wiod(RELEASE_ZIP, YEAR))


class TestLabor:
    def test_compensation_for_the_usa_is_the_accounts_total_at_rate_one(self, compensation):
        rows = read_xlsx_rows(SEA, "DATA")
        header = rows[0]
        year_column = header.index(float(YEAR))
        expected = sum(
            row[year_column]
            for row in rows[1:]
            if row[0] == "USA" and row[1] == "COMP"
        )
        economy = compensation.economy
        labour = np.flatnonzero(
            (economy.commodity_extra["industry"] == "labor")
            & (economy.commodity_extra["region"] == "USA")
        )
        assert labour.size == 1
        assert economy.endowment[labour[0]] == pytest.approx(expected * 1.0, rel=1e-9)

    def test_compensation_leaves_only_the_rest_of_the_world_without_labour(self):
        require(RELEASE_ZIP, SEA, EXCHANGE_RATES)
        with pytest.warns(WiodLaborGap) as record:
            loaded = load_wiod(
                RELEASE_ZIP, YEAR, labor="compensation", sea=SEA, exchange_rates=EXCHANGE_RATES
            )
        gaps = [entry for entry in record if issubclass(entry.category, WiodLaborGap)]
        assert len(gaps) == 1
        listed = str(gaps[0].message).split(": ", 1)[1]
        assert listed.startswith("ROW (") and "," not in listed
        economy = loaded.economy
        extra = economy.unit_extra
        assert set(extra["region"][extra["labor_observed"] == 0.0]) == {"ROW"}
        labour = economy.commodity_extra["industry"] == "labor"
        assert "ROU" in set(economy.commodity_extra["region"][labour])
        assert int(labour.sum()) == N_ECONOMIES - 1

    def test_compensation_passes_the_plan_validation(self, compensation):
        compensation.observed.validate(compensation.economy)

    def test_hours_warn_naming_china_and_the_rest_of_the_world(self):
        require(RELEASE_ZIP, SEA)
        with pytest.warns(WiodLaborGap) as record:
            loaded = load_wiod(RELEASE_ZIP, YEAR, labor="hours", sea=SEA)
        gaps = [entry for entry in record if issubclass(entry.category, WiodLaborGap)]
        assert len(gaps) == 1
        message = str(gaps[0].message)
        assert "CHN" in message and "ROW" in message
        regions = loaded.economy.commodity_extra["region"]
        labour_regions = set(regions[loaded.economy.commodity_extra["industry"] == "labor"])
        assert "CHN" not in labour_regions and "ROW" not in labour_regions
        assert len(labour_regions) == N_ECONOMIES - 2

