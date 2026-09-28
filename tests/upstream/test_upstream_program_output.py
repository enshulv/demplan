"""The reader of the pequod-cljs output files, ``research/upstream/_program_output.py``.

The files are written here in the layout ``get-csv-header`` and ``print-csv`` of csvgen.clj at
71e44d3 produce: ``:iteration``, ``:color``, 35 blocks of per-commodity columns, then an output
and an effort column per worker council. No file of the program is read.
"""

from __future__ import annotations

import numpy as np
import pytest

import upstream_paths  # noqa: F401  (puts the scripts on sys.path)

import _program_output as po  # noqa: E402

CATS = ("private-goods", "intermediate-goods", "nature", "labor", "public-goods")
PRICE_NAMES = ("private-good-prices", "intermediate-good-prices", "nature-prices", "labor-prices",
               "public-good-prices")
BLOCK_PREFIXES = ("new-deltas", "pdlist", "supply", "demand", "surplus", "threshold-report")


def _header(per_category=100, wc_ids=(1,)):
    names = [":iteration", ":color"]
    blocks = [f":{p}" for p in PRICE_NAMES]
    for prefix in BLOCK_PREFIXES:
        blocks += [f":{prefix}-{c}" for c in CATS]
    for b in blocks:
        names += [f"{b}-{n}" for n in range(1, per_category + 1)]
    for i in wc_ids:
        names += [f"wc_{i}_output", f"wc_{i}_effort"]
    return names


def _row(iteration, color, base, per_category=100, wc_ids=(1,)):
    """Block b, commodity j holds base + b + j/1000; worker council i has output 10 i + base, effort i/10."""
    values = [str(iteration), color]
    for block in range(35):
        values += [repr(base + block + j / 1000) for j in range(per_category)]
    for i in wc_ids:
        values += [repr(10.0 * i + base), repr(i / 10)]
    return values


def _exponent_sum(per_category=100, wc_ids=(1,)):
    return ["exponent-sum"] + [""] * (1 + 35 * per_category) + [x for i in wc_ids for x in ("2.5", "")]


def _write_csv(path, years, per_category=100, wc_ids=(1,), close_last_year=True, tail=""):
    lines = [",".join(_header(per_category, wc_ids))]
    for y, rows in enumerate(years):
        for it, color in rows:
            lines.append(",".join(_row(it, color, float(it + 10 * y), per_category, wc_ids)))
        if close_last_year or y < len(years) - 1:
            lines.append(",".join(_exponent_sum(per_category, wc_ids)))
    path.write_text("\n".join(lines) + "\n" + tail, encoding="utf-8")


# ---------------------------------------------------------------- read_output


def test_read_output_splits_years_and_blocks(tmp_path):
    p = tmp_path / "dep1ex61.csv"
    _write_csv(p, [[(1, ":red"), (2, ":blue")], [(1, ":green")]])
    out = po.read_output(p)
    assert len(out.years) == 2
    y1, y2 = out.years
    assert list(y1.iteration) == [1, 2] and list(y2.iteration) == [1]
    assert y1.color == (":red", ":blue")
    assert y1.price.shape == (2, 500)
    # block order: price block 0..4 are categories of price, new_delta starts at block 5
    assert y1.price[0, 0] == 1.0 and y1.new_delta[0, 0] == 1.0 + 5
    assert y1.threshold[0, 0] == 1.0 + 30
    assert list(y1.lines) == [2, 3] and list(y2.lines) == [5]
    assert y1.end_line == 4 and y2.end_line == 6


def test_read_output_leaves_worker_councils_out_unless_asked(tmp_path):
    p = tmp_path / "dep1ex61.csv"
    _write_csv(p, [[(1, ":red")], [(1, ":green")]], wc_ids=(1, 2))
    plain = po.read_output(p).years[0]
    assert plain.wc_ids == () and plain.wc_output is None and plain.wc_effort is None
    year = po.read_output(p, worker_councils=True).years[0]
    assert year.wc_ids == (1, 2)
    np.testing.assert_array_equal(year.wc_output, [[11.0, 21.0]])
    np.testing.assert_array_equal(year.wc_effort, [[0.1, 0.2]])


def test_read_output_rejects_non_consecutive_iterations(tmp_path):
    p = tmp_path / "x.csv"
    _write_csv(p, [[(1, ":red"), (3, ":blue")]])
    with pytest.raises(ValueError, match="iteration"):
        po.read_output(p)


def test_read_output_rejects_unparseable_number(tmp_path):
    p = tmp_path / "x.csv"
    _write_csv(p, [[(1, ":red")]])
    text = p.read_text(encoding="utf-8").splitlines()
    fields = text[1].split(",")
    fields[5] = "3/4"
    text[1] = ",".join(fields)
    p.write_text("\n".join(text) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 2"):
        po.read_output(p)


def test_read_output_rejects_wrong_header(tmp_path):
    p = tmp_path / "x.csv"
    _write_csv(p, [[(1, ":red")]])
    text = p.read_text(encoding="utf-8").replace(":pdlist-labor-7,", ":pdlist-labor-8,", 1)
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        po.read_output(p)


def test_read_output_rejects_malformed_worker_council_columns(tmp_path):
    p = tmp_path / "x.csv"
    _write_csv(p, [[(1, ":red")]], wc_ids=(1, 2))
    text = p.read_text(encoding="utf-8").replace("wc_2_effort", "wc_3_effort", 1)
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        po.read_output(p, worker_councils=True)


def test_read_output_rejects_rows_after_the_last_year(tmp_path):
    p = tmp_path / "x.csv"
    _write_csv(p, [[(1, ":red")], [(1, ":green")]], close_last_year=False)
    with pytest.raises(ValueError, match="exponent-sum"):
        po.read_output(p)


def test_read_output_infers_commodities_per_category_from_the_header(tmp_path):
    p = tmp_path / "small.csv"
    _write_csv(p, [[(1, ":red"), (2, ":blue")]], per_category=2, wc_ids=(1, 2, 3))
    year = po.read_output(p, worker_councils=True).years[0]
    assert year.per_category == 2
    assert year.price.shape == (2, 10) and year.threshold.shape == (2, 10)
    assert year.threshold[1, 9] == 2.0 + 34 + 1 / 1000
    assert year.wc_ids == (1, 2, 3)


@pytest.mark.parametrize(("text", "digits"), [
    ("0.00012345", 5), ("-1.2300E5", 3), ("700", 1), ("0", 1), ("48.51500977245734", 16),
])
def test_significant_digits_of_a_printed_number(text, digits):
    assert po._significant_digits(text) == digits


# ---------------------------------------------------------------- read_year_one


def test_read_year_one_stops_before_exponent_sum(tmp_path):
    p = tmp_path / "a.csv"
    _write_csv(p, [[(1, ":red"), (2, ":blue")], [(1, ":green")]], wc_ids=(1, 2))
    year = po.read_year_one(p, worker_councils=True)
    assert list(year.iteration) == [1, 2] and year.end_line == 4
    np.testing.assert_array_equal(year.wc_output[:, 1], [21.0, 22.0])


def test_read_year_one_reads_every_row_of_a_run_stopped_before_the_year_ended(tmp_path):
    p = tmp_path / "a.csv"
    _write_csv(p, [[(1, ":red"), (2, ":blue"), (3, ":blue")]], close_last_year=False)
    year = po.read_year_one(p)
    assert list(year.iteration) == [1, 2, 3] and year.end_line is None


def test_read_year_one_drops_a_last_line_written_only_in_part(tmp_path):
    p = tmp_path / "a.csv"
    partial = ",".join(_row(3, ":blue", 3.0))[:5000]
    _write_csv(p, [[(1, ":red"), (2, ":blue")]], close_last_year=False, tail=partial)
    year = po.read_year_one(p)
    assert list(year.iteration) == [1, 2]


def test_read_year_one_max_rows_limits_the_rows_read(tmp_path):
    p = tmp_path / "a.csv"
    _write_csv(p, [[(1, ":red"), (2, ":blue"), (3, ":blue")]])
    year = po.read_year_one(p, max_rows=2)
    assert list(year.iteration) == [1, 2]
    np.testing.assert_array_equal(year.supply[:, 0], [1.0 + 15, 2.0 + 15])


def test_read_year_one_rejects_a_complete_line_that_is_too_short(tmp_path):
    p = tmp_path / "a.csv"
    short = ",".join(_row(2, ":blue", 2.0)[:-3])
    _write_csv(p, [[(1, ":red")]], close_last_year=False, tail=short + "\n")
    with pytest.raises(ValueError, match="line 3"):
        po.read_year_one(p, worker_councils=True)


# ---------------------------------------------------------------- names


def test_commodity_label():
    assert po.commodity_label(0) == "private-goods-1"
    assert po.commodity_label(331) == "labor-32"
    assert po.commodity_label(499) == "public-goods-100"
    assert po.commodity_label(3, per_category=2) == "intermediate-goods-2"


def test_column_name_is_the_header_name_of_the_cell():
    header = _header(per_category=2, wc_ids=())
    for at, quantity in enumerate(po.QUANTITIES):
        for index in range(10):
            assert po.column_name(quantity, index, per_category=2) == header[2 + at * 10 + index]
