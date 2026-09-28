"""Readings of the output files, the book's printed tables and the experiment numbering:
``_readings.py``, ``_book.py`` and ``_experiments.py`` in ``research/upstream``."""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

import upstream_paths  # noqa: F401  (puts the scripts on sys.path)

import _book as book  # noqa: E402
import _experiments as ex  # noqa: E402
import _readings as rd  # noqa: E402


def test_first_all_below_is_strict():
    thr = np.array([[12.0, 1.0], [5.0, 1.0], [4.9, 2.0]])
    it = np.array([1, 2, 3])
    assert rd.first_all_below(thr, it, 5.0) == 3
    assert rd.first_all_below(thr, it, 12.5) == 1
    assert rd.first_all_below(thr, it, 1.0) is None


def test_first_color_at_least_and_exact():
    colors = (":red", ":yellow", ":blue", ":green")
    it = np.array([1, 2, 3, 4])
    assert rd.first_color_at_least(colors, it, ":green") == 3
    assert rd.first_color_exact(colors, it, ":green") == 4
    assert rd.first_color_at_least(colors, it, ":yellow") == 2
    with pytest.raises(ValueError):
        rd.first_color_at_least((":purple",), np.array([1]), ":green")


def test_gdp_growth_matches_note_15_formula():
    p1, s1 = np.array([1.0, 2.0]), np.array([10.0, 10.0])
    p2, s2 = np.array([1.5, 2.0]), np.array([11.0, 12.0])
    typ = 100 * ((p2 @ s2) - (p2 @ s1)) / (p2 @ s1)
    lyp = 100 * ((p1 @ s2) - (p1 @ s1)) / (p1 @ s1)
    g = rd.gdp_growth(p1, s1, p2, s2)
    assert g.mean == pytest.approx((typ + lyp) / 2)
    assert g.year_2_prices == pytest.approx(typ)
    assert g.year_1_prices == pytest.approx(lyp)


def test_truncate_and_round_to_three_decimals():
    assert rd.truncated(2.5495713360) == Decimal("2.549")
    assert rd.rounded(2.5495713360) == Decimal("2.550")
    assert rd.truncated(2.6007) == Decimal("2.6")
    assert rd.rounded(2.2394042) == Decimal("2.239")


def test_parse_experiments():
    assert ex.parse_experiments("1-3,7") == [1, 2, 3, 7]
    assert ex.parse_experiments("40") == [40]
    assert ex.parse_experiments("2,4-5") == [2, 4, 5]
    for text in ("0-2", "41", "0-3", "39-41"):
        with pytest.raises(SystemExit):
            ex.parse_experiments(text)


def test_experiments_argument_default_can_be_set():
    import argparse
    parser = argparse.ArgumentParser()
    ex.add_experiments_argument(parser, default="1-5")
    assert parser.parse_args([]).experiments == [1, 2, 3, 4, 5]
    assert parser.parse_args(["--experiments", "38"]).experiments == [38]
    everything = argparse.ArgumentParser()
    ex.add_experiments_argument(everything)
    assert everything.parse_args([]).experiments == list(range(1, 41))


def test_output_number():
    assert ex.output_number(1) == 61 and ex.output_number(40) == 100


def test_next_experiment_wraps():
    assert ex.next_experiment(1) == 2
    assert ex.next_experiment(39) == 40
    assert ex.next_experiment(40) == 1


def test_book_tables_complete():
    t = book.load_tables()
    for key in (("9.1", "#I"), ("9.2", "#I"), ("9.4", "#I"), ("9.4", "GDP"), ("9.5", "#I"),
                ("9.6", "#I"), ("9.6", "GDP")):
        assert sorted(t[key]) == list(range(1, 41)), key
    assert t[("9.2", "#I")][38].printed == "19"
    assert t[("9.4", "GDP")][1].printed == "2.6%"
    assert t[("9.4", "GDP")][1].value == Decimal("2.6")
    assert t[("9.1", "#I")][1].page == 178
    assert sum(int(c.value) for c in t[("9.2", "#I")].values()) == 769
    assert sum(int(c.value) for c in t[("9.4", "#I")].values()) == 261


def test_book_tables_reject_repeated_cell(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("table,experiment,column,printed,page\n9.1,1,#I,12,178\n9.1,1,#I,12,178\n", encoding="utf-8")
    with pytest.raises(ValueError, match="repeats"):
        book.load_tables(p)


def test_book_tables_reject_non_number(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("table,experiment,column,printed,page\n9.1,1,#I,1 2,178\n", encoding="utf-8")
    with pytest.raises(ValueError, match="t.csv:2"):
        book.load_tables(p)


def test_gdp_adds_private_good_n_then_public_good_n_from_zero():
    # computeGdp in bin/dep_data_process.py at 7757bb4 adds, for n = 1..100, private good n and
    # then public good n. With these four products the float sum depends on that order:
    # ((0.9 + 0.3) + 8.4) + 4.3 = 13.899999999999999, ((0.3 + 0.9) + 4.3) + 8.4 = 13.9.
    from _program_output import CATEGORIES, N_COMMODITIES, PER_CATEGORY, Year

    private, public = CATEGORIES.index("private-goods") * PER_CATEGORY, CATEGORIES.index("public-goods") * PER_CATEGORY
    supply = np.zeros((1, N_COMMODITIES))
    supply[0, [private, public, private + 1, public + 1]] = [0.9, 0.3, 8.4, 4.3]
    price = np.ones((1, N_COMMODITIES))
    zeros = np.zeros((1, N_COMMODITIES))
    year = Year(lines=np.array([2]), iteration=np.array([1]), color=(":red",), price=price, new_delta=zeros,
                pdlist=zeros, supply=supply, demand=zeros, surplus=zeros, threshold=zeros, end_line=3)
    prices, supplies = rd._gdp_goods(year, -1)
    assert len(supplies) == 2 * PER_CATEGORY
    assert supplies[:4] == [0.9, 0.3, 8.4, 4.3] and not any(supplies[4:])
    assert rd._gdp(prices, supplies) == ((0.9 + 0.3) + 8.4) + 4.3 != ((0.3 + 0.9) + 4.3) + 8.4
