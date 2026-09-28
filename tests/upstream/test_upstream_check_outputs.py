"""The book-table part of ``research/upstream/check_outputs.py``: which output reading each
printed cell is compared with, the cells that differ, the sums and means, and how the printed
GDP relates to the output truncated or rounded.

Three synthetic output files with two years each are written in the layout of csvgen.clj at
71e44d3 and read with the scripts' own reader; the printed tables are a small ``book_tables.csv``
written next to them. Book experiment N reads ``dep1ex(60+N).csv``.

Readings of the three files, by construction:

  exp  worst per round, year one   <10 <5 <3  10->5   year two (colour)                <5  green  GDP growth
   1   50, 8, 4, 2.5                 2  3  4    1     7 yellow, 4.9 blue, 4.0 green     2    3    2.5496
   2   30, 9, 6, 4.5, 2              2  4  5    2     4.0 green                         1    1    1.2341
   3   30, 8, 4                      2  3  -    1     3.0 blue                          1    -    0

"green" is the first year-two row whose colour is exactly ``:green``; the tables are read from
the threshold-report values, so year two of experiment 1 deliberately disagrees with its colour.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import numpy as np
import pytest

import upstream_paths  # noqa: F401  (puts the scripts on sys.path)

import _book as book  # noqa: E402
import _program_output as po  # noqa: E402
import _readings as rd  # noqa: E402
import check_outputs as co  # noqa: E402

PRIVATE_GOOD_1 = 0
"""Column of private good 1 within a block; the GDP sums private and public goods."""
BASE_SUPPLY = 1000.0

EXPERIMENTS = {
    1: {"year_1": ((50.0, ":red"), (8.0, ":yellow"), (4.0, ":green"), (2.5, ":blue")),
        "year_2": ((7.0, ":yellow"), (4.9, ":blue"), (4.0, ":green")),
        "year_2_supply": 1025.496},
    2: {"year_1": ((30.0, ":orange"), (9.0, ":yellow"), (6.0, ":yellow"), (4.5, ":green"), (2.0, ":blue")),
        "year_2": ((4.0, ":green"),),
        "year_2_supply": 1012.341},
    3: {"year_1": ((30.0, ":orange"), (8.0, ":yellow"), (4.0, ":green")),
        "year_2": ((3.0, ":blue"),),
        "year_2_supply": BASE_SUPPLY},
}

BOOK_ROWS = (
    # table, experiment, column, printed
    ("9.1", 1, "#I", "3"), ("9.1", 2, "#I", "5"), ("9.1", 3, "#I", "3"),
    ("9.2", 1, "#I", "4"), ("9.2", 2, "#I", "5"), ("9.2", 3, "#I", "20"),
    ("9.5", 1, "#I", "1"), ("9.5", 2, "#I", "2"), ("9.5", 3, "#I", "1"),
    ("9.4", 1, "#I", "2"), ("9.4", 2, "#I", "3"), ("9.4", 3, "#I", "1"),
    ("9.4", 1, "GDP", "2.549%"), ("9.4", 2, "GDP", "1.234%"), ("9.4", 3, "GDP", "0.0%"),
)
"""Printed cells: experiment 2 differs in 9.1 (5, output 4) and 9.4 (3, output 1), experiment 3
in 9.2 (20, output none); every GDP cell equals the output truncated, and experiment 1's differs
from the output rounded (2.550)."""


def _row(iteration: int, color: str, worst: float, supply: float) -> str:
    """One data row: every threshold-report value is ``worst``, every price 1, and private good 1
    the only good with a supply."""
    blocks = {quantity: np.zeros(po.N_COMMODITIES) for quantity in po.QUANTITIES}
    blocks["price"][:] = 1.0
    blocks["supply"][PRIVATE_GOOD_1] = supply
    blocks["threshold"][:] = worst
    values = [repr(float(v)) for quantity in po.QUANTITIES for v in blocks[quantity]]
    return ",".join([str(iteration), color, *values])


def _write_output(path, spec) -> None:
    """A two-year output file; only the last row of each year carries the supply the GDP reads."""
    lines = [",".join(po.expected_header())]
    for rows, supply in ((spec["year_1"], BASE_SUPPLY), (spec["year_2"], spec["year_2_supply"])):
        for number, (worst, color) in enumerate(rows, start=1):
            lines.append(_row(number, color, worst, supply if number == len(rows) else 0.0))
        lines.append(",".join(["exponent-sum"] + [""] * (1 + len(po.QUANTITIES) * po.N_COMMODITIES)))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture(scope="module")
def readings(tmp_path_factory):
    """``{output number: Readings}`` of the three synthetic files."""
    directory = tmp_path_factory.mktemp("outputs")
    found = {}
    for n, spec in EXPERIMENTS.items():
        path = directory / f"dep1ex{60 + n}.csv"
        _write_output(path, spec)
        found[60 + n] = rd.read_all(po.read_output(path))
    return found


@pytest.fixture(scope="module")
def tables(tmp_path_factory):
    """The printed cells of BOOK_ROWS, read by the scripts' own table reader."""
    path = tmp_path_factory.mktemp("book") / "book_tables.csv"
    rows = ["table,experiment,column,printed,page"]
    rows += [f"{table},{n},{column},{printed},178" for table, n, column, printed in BOOK_ROWS]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return book.load_tables(path)


def test_the_synthetic_files_read_as_constructed(readings):
    one = readings[61]
    assert one.below == {10.0: 2, 5.0: 3, 3.0: 4}
    assert one.year_2_below_5 == 2 and one.year_2_color_exact == 3
    assert one.growth.mean == pytest.approx(2.5496, abs=1e-12)
    assert readings[63].below[3.0] is None and readings[63].year_2_color_exact is None


def test_output_values_reads_each_table_from_its_own_threshold(readings):
    assert co.output_values(readings[61]) == {
        ("9.1", "#I"): 3, ("9.2", "#I"): 4, ("9.5", "#I"): 1, ("9.4", "#I"): 2,
        ("9.4", "GDP"): Decimal("2.549"),
    }
    assert co.output_values(readings[63])[("9.2", "#I")] is None


def test_differing_cells_are_exactly_the_cells_whose_print_differs(readings, tables):
    assert co.differing_cells([1, 2, 3], readings, tables) == [
        (2, "9.1", "#I", "5", 4),
        (2, "9.4", "#I", "3", 1),
        (3, "9.2", "#I", "20", None),
    ]
    assert co.differing_cells([1], readings, tables) == []


def test_column_totals_sum_the_compared_readings_and_the_printed_cells(readings, tables):
    totals = co.column_totals([1, 2, 3], readings, tables)
    assert list(totals) == [("9.1", "#I"), ("9.2", "#I"), ("9.5", "#I"), ("9.4", "#I")]
    expected = {
        ("9.1", "#I"): (10, 10 / 3, 0, 11, 11 / 3),
        ("9.2", "#I"): (9, 4.5, 1, 29, 29 / 3),
        ("9.5", "#I"): (4, 4 / 3, 0, 4, 4 / 3),
        ("9.4", "#I"): (4, 4 / 3, 0, 6, 2.0),
    }
    for key, (output_sum, output_mean, missing, printed_sum, printed_mean) in expected.items():
        total = totals[key]
        assert (total.output_sum, total.missing, total.printed_sum) == (output_sum, missing, printed_sum), key
        assert total.output_mean == pytest.approx(output_mean, rel=1e-15), key
        assert total.printed_mean == pytest.approx(printed_mean, rel=1e-15), key


def test_gdp_means_average_the_output_growth_and_the_printed_cells(readings, tables):
    output_mean, printed_mean = co.gdp_means([1, 2, 3], readings, tables)
    assert output_mean == pytest.approx((2.5496 + 1.2341 + 0.0) / 3, rel=1e-12)
    assert printed_mean == pytest.approx((2.549 + 1.234 + 0.0) / 3, rel=1e-15)


def test_gdp_means_take_the_mean_of_the_growth_at_both_years_prices(readings, tables):
    # every price is 1 in the synthetic files, so growth is the same at both years' prices there
    uneven = {**readings, 61: dataclasses.replace(readings[61], growth=rd.Growth(1.0, 3.0, 2.0))}
    assert co.gdp_means([1], uneven, tables)[0] == 2.0


def test_gdp_rounding_counts_count_truncated_and_rounded_matches_separately(readings, tables):
    # truncated: 2.549, 1.234, 0.000 all equal the print; rounded: 2.550 does not
    assert co.gdp_rounding_counts([1, 2, 3], readings, tables) == (3, 2)
    assert co.gdp_rounding_counts([1], readings, tables) == (1, 0)
