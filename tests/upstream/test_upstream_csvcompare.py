"""``research/upstream/docker/pequod-cljs/csvcompare.py`` on small synthetic CSVs laid out like
csvgen.clj's output, read back with ``_program_output.read_year_one``.

The expected steps below are written out from the rules' definitions, not taken from
csvcompare.py or ``_price_rules.py``.
"""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path

import numpy as np
import pytest

import upstream_paths  # noqa: F401  (puts the scripts on sys.path)

import csvcompare as cc  # noqa: E402
from _program_output import read_year_one  # noqa: E402

CATEGORIES = ("private-goods", "intermediate-goods", "nature", "labor", "public-goods")
PRICE_KEYS = ("private-good-prices", "intermediate-good-prices", "nature-prices", "labor-prices", "public-good-prices")
KINDS = ("new-deltas", "pdlist", "supply", "demand", "surplus", "threshold-report")


def header(goods: int, wcs: int) -> list[str]:
    """The header csvgen.clj's get-csv-header writes, with `goods` commodities per category."""
    names = [":iteration", ":color"]
    names += [f":{key}-{i}" for key in PRICE_KEYS for i in range(1, goods + 1)]
    names += [f":{kind}-{cat}-{i}" for kind in KINDS for cat in CATEGORIES for i in range(1, goods + 1)]
    for wc in range(1, wcs + 1):
        names += [f"wc_{wc}_output", f"wc_{wc}_effort"]
    return names


def book_step(v: float) -> float:
    return min(v, 0.25) * (1.05 - 0.5 ** v)


def paper_step(v: float) -> float:
    return min(v, 0.25) * (1.05 - 0.5 ** min(v, 0.25))


def program_step(v: float, previous_capped: float) -> float:
    base = 1.05 - 0.5 ** v
    return max(0.001, min(base, abs(base * previous_capped)))


def build_rows(imbalances: list[list[float]], surpluses: list[list[float]], step_rule: str) -> list[list[str]]:
    """Rows for one commodity per category (five commodities), no worker councils.

    `imbalances[k][j]` is v of commodity j in round k+1 as a fraction; the step recorded in the
    row follows `step_rule`, and prices follow p_k = p_{k-1}(1 -/+ w_k) from 700.
    """
    rows = []
    prices = [700.0] * 5
    previous_capped = [0.25] * 5
    for k, (vs, ss) in enumerate(zip(imbalances, surpluses), start=1):
        steps = []
        for j, v in enumerate(vs):
            if step_rule == "program":
                steps.append(program_step(v, previous_capped[j]))
            elif step_rule == "book":
                steps.append(book_step(v))
            else:
                steps.append(paper_step(v))
        for j, s in enumerate(ss):
            if s > 0:
                prices[j] *= 1 - steps[j]
            elif s < 0:
                prices[j] *= 1 + steps[j]
        capped = [min(v, 0.25) for v in vs]
        supply = [1000.0] * 5
        demand = [1000.0 - s for s in ss]
        threshold = [100 * v for v in vs]
        color = ":blue" if max(threshold) < 3 else ":red"
        row = [str(k), color] + [repr(p) for p in prices] + [repr(w) for w in steps]
        row += [repr(c) for c in capped] + [repr(x) for x in supply] + [repr(x) for x in demand]
        row += [repr(x) for x in ss] + [repr(x) for x in threshold]
        rows.append(row)
        previous_capped = capped
    return rows


IMBALANCES = [
    [1.2, 0.4, 0.3, 0.2, 0.05],
    [0.6, 0.1, 0.01, 0.26, 0.01],
    [0.3, 0.05, 0.0004, 0.12, 0.2],
]
SURPLUSES = [
    [5.0, -3.0, 2.0, -1.0, 0.5],
    [-2.0, 1.0, -0.5, 3.0, -0.1],
    [1.0, -1.0, 0.0, 2.0, -2.0],
]


def write_csv(path: Path, head: list[str], rows: list[list[str]], trailer: bool = True) -> Path:
    lines = [",".join(head)] + [",".join(r) for r in rows]
    if trailer:
        # csvgen.clj pads the exponent-sum line to the header's width.
        lines.append(",".join(["exponent-sum"] + [""] * (len(head) - 1)))
        lines.append(",".join(rows[0]))  # a year-two row that must not be read
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def year(tmp_path: Path, rows: list[list[str]], wcs: int = 0, name: str = "a.csv"):
    """The rows written as a csvgen.clj output file and read back as year one."""
    if wcs:
        rows = [r + ["2.5", "0.5"] * wcs for r in rows]
    return read_year_one(write_csv(tmp_path / name, header(1, wcs), rows), worker_councils=wcs > 0)


def program_rows():
    return build_rows(IMBALANCES, SURPLUSES, "program")


class TestIdenticalLines:
    def test_reports_each_of_the_first_lines_as_equal_or_not(self, tmp_path):
        rows = program_rows()
        a = write_csv(tmp_path / "a.csv", header(1, 0), rows)
        changed = [list(r) for r in rows]
        changed[1][2] = changed[1][2] + "0"  # the same number written with one more digit
        b = write_csv(tmp_path / "b.csv", header(1, 0), changed)
        assert cc.identical_lines(a, b, 4) == [True, True, False, True]

    def test_a_file_shorter_than_asked_counts_as_different_there(self, tmp_path):
        rows = program_rows()
        a = write_csv(tmp_path / "a.csv", header(1, 0), rows, trailer=False)
        b = write_csv(tmp_path / "b.csv", header(1, 0), rows[:1], trailer=False)
        assert cc.identical_lines(a, b, 3) == [True, True, False]
        assert cc.identical_lines(b, b, 3) == [True, True, False]


class TestDiffRuns:
    def runs(self, tmp_path, wcs: int = 0, ours_rows=None, theirs_rows=None):
        ours = year(tmp_path, ours_rows or program_rows(), wcs, "ours.csv")
        theirs = year(tmp_path, theirs_rows or program_rows(), wcs, "theirs.csv")
        return ours, theirs

    def test_identical_runs_have_zero_differences(self, tmp_path):
        ours, theirs = self.runs(tmp_path, wcs=2)
        diff = cc.diff_runs(ours, theirs, rounds=3)
        assert diff.rounds_compared == 3
        assert diff.color_mismatches == []
        assert diff.iteration_mismatches == []
        for group in diff.groups:
            assert group.max_abs == 0.0
            assert group.max_rel == 0.0
            assert group.identical_cells == group.cells
        kinds = {g.kind: g.cells for g in diff.groups}
        assert list(kinds) == ["prices", "new-deltas", "pdlist", "supply", "demand", "surplus",
                               "threshold-report", "wc output", "wc effort"]
        assert kinds["prices"] == 5 * 3
        assert kinds["wc output"] == 2 * 3
        assert kinds["wc effort"] == 2 * 3

    def test_without_worker_councils_there_are_seven_kinds(self, tmp_path):
        ours, theirs = self.runs(tmp_path)
        assert [g.kind for g in cc.diff_runs(ours, theirs, 3).groups] == [
            "prices", "new-deltas", "pdlist", "supply", "demand", "surplus", "threshold-report"]

    def test_locates_the_largest_difference(self, tmp_path):
        col = header(1, 0).index(":demand-nature-1")
        rows = program_rows()
        base = float(rows[1][col])
        changed = [list(r) for r in rows]
        changed[1][col] = repr(base + 0.25)
        ours, theirs = self.runs(tmp_path, ours_rows=changed)
        diff = cc.diff_runs(ours, theirs, rounds=3)
        demand = next(g for g in diff.groups if g.kind == "demand")
        assert demand.max_abs == pytest.approx(0.25, rel=1e-12)
        assert demand.max_abs_at == (2, ":demand-nature-1")
        assert demand.max_rel == pytest.approx(0.25 / (base + 0.25), rel=1e-12)
        assert demand.identical_cells == demand.cells - 1
        others = [g for g in diff.groups if g.kind != "demand"]
        assert all(g.max_abs == 0.0 for g in others)

    def test_locates_a_worker_council_column_by_its_header_name(self, tmp_path):
        rows = [r + ["2.5", "0.5", "2.5", "0.5"] for r in program_rows()]
        changed = [list(r) for r in rows]
        changed[2][-1] = "0.75"
        ours = read_year_one(write_csv(tmp_path / "o.csv", header(1, 2), changed), worker_councils=True)
        theirs = read_year_one(write_csv(tmp_path / "t.csv", header(1, 2), rows), worker_councils=True)
        effort = next(g for g in cc.diff_runs(ours, theirs, 3).groups if g.kind == "wc effort")
        assert effort.max_abs_at == (3, "wc_2_effort")
        assert effort.max_abs == pytest.approx(0.25)

    def test_relative_difference_of_two_zeros_is_zero_and_zero_versus_nonzero_is_one(self, tmp_path):
        col = header(1, 0).index(":surplus-nature-1")
        zeroed = [list(r) for r in program_rows()]
        zeroed[2][col] = "0.0"
        ours, theirs = self.runs(tmp_path, ours_rows=zeroed, theirs_rows=zeroed)
        assert next(g for g in cc.diff_runs(ours, theirs, 3).groups if g.kind == "surplus").max_rel == 0.0
        tiny = [list(r) for r in zeroed]
        tiny[2][col] = "1.0e-9"
        ours, theirs = self.runs(tmp_path, ours_rows=tiny, theirs_rows=zeroed)
        surplus = next(g for g in cc.diff_runs(ours, theirs, 3).groups if g.kind == "surplus")
        assert surplus.max_rel == 1.0
        assert surplus.max_abs == pytest.approx(1e-9)

    def test_numbers_written_differently_but_equal_count_as_identical_values(self, tmp_path):
        col = header(1, 0).index(":supply-labor-1")
        ours_rows = [list(r) for r in program_rows()]
        theirs_rows = [list(r) for r in program_rows()]
        ours_rows[0][col] = "1000"
        theirs_rows[0][col] = "1000.0"
        ours, theirs = self.runs(tmp_path, ours_rows=ours_rows, theirs_rows=theirs_rows)
        supply = next(g for g in cc.diff_runs(ours, theirs, 3).groups if g.kind == "supply")
        assert supply.max_abs == 0.0

    def test_records_colour_and_iteration_mismatches(self, tmp_path):
        ours, theirs = self.runs(tmp_path)
        ours = dataclasses.replace(ours, color=(*ours.color[:2], ":green"),
                                   iteration=np.array([1, 7, 3]))
        diff = cc.diff_runs(ours, theirs, rounds=3)
        assert diff.color_mismatches == [(3, ":green", theirs.color[2])]
        assert diff.iteration_mismatches == [(2, 7, 2)]

    def test_compares_only_the_requested_rounds(self, tmp_path):
        col = header(1, 0).index(":demand-nature-1")
        changed = [list(r) for r in program_rows()]
        changed[2][col] = "123456.0"
        ours, theirs = self.runs(tmp_path, ours_rows=changed)
        diff = cc.diff_runs(ours, theirs, rounds=2)
        assert diff.rounds_compared == 2
        assert all(g.max_abs == 0.0 for g in diff.groups)

    def test_refuses_more_rounds_than_either_run_has(self, tmp_path):
        ours, _ = self.runs(tmp_path)
        shorter = year(tmp_path, program_rows()[:2], name="short.csv")
        with pytest.raises(ValueError):
            cc.diff_runs(ours, shorter, rounds=3)

    def test_refuses_different_headers(self, tmp_path):
        ours = year(tmp_path, program_rows(), wcs=1, name="one.csv")
        other = year(tmp_path, program_rows(), wcs=2, name="two.csv")
        with pytest.raises(ValueError, match="header"):
            cc.diff_runs(ours, other, rounds=3)


class TestRuleErrors:
    @pytest.mark.parametrize("recorded_rule", ["program", "book", "paper"])
    def test_only_the_rule_that_produced_the_steps_reproduces_them(self, tmp_path, recorded_rule):
        run = year(tmp_path, build_rows(IMBALANCES, SURPLUSES, recorded_rule))
        errors = cc.rule_errors(run)
        assert set(errors) == {"program", "book", "paper"}
        for rule, per_round in errors.items():
            assert len(per_round) == 3
            if rule == recorded_rule:
                assert max(per_round) < 1e-12
            else:
                assert max(per_round) > 1e-3

    def test_program_rule_uses_the_previous_rounds_capped_imbalance(self, tmp_path):
        # Round 2, commodity 1: v_1 = 1.2 capped to 0.25, v_2 = 0.6. The step is
        # (1.05 - 0.5^0.6) * 0.25; with this round's cap (0.25 as well) the book rule agrees,
        # so commodity 2 is the discriminating case: v_1 = 0.4 -> 0.25, v_2 = 0.1.
        expected = (1.05 - 0.5**0.1) * 0.25
        assert program_step(0.1, 0.25) == pytest.approx(expected, rel=1e-15)
        assert book_step(0.1) == pytest.approx((1.05 - 0.5**0.1) * 0.1, rel=1e-15)
        rows = program_rows()
        col = header(1, 0).index(":new-deltas-intermediate-goods-1")
        assert float(rows[1][col]) == pytest.approx(expected, rel=1e-15)
        assert max(cc.rule_errors(year(tmp_path, rows))["program"]) < 1e-12

    def test_program_rule_applies_the_floor(self, tmp_path):
        # Commodity 3, round 3: v_3 = 0.0004 after v_2 = 0.01, so base * 0.01 is below 0.001.
        assert (1.05 - 0.5**0.0004) * 0.01 < 0.001
        rows = program_rows()
        col = header(1, 0).index(":new-deltas-nature-1")
        assert float(rows[2][col]) == 0.001
        assert max(cc.rule_errors(year(tmp_path, rows))["program"]) < 1e-12

    def test_a_zero_step_is_matched_by_zero_and_missed_by_anything_else(self, tmp_path):
        balanced = [[0.0] * 5, [0.0] * 5]
        run = year(tmp_path, build_rows(balanced, [[0.0] * 5] * 2, "book"))
        errors = cc.rule_errors(run)
        assert errors["book"] == [0.0, 0.0]
        assert errors["program"] == [math.inf, math.inf]

    def test_a_single_wrong_step_shows_in_its_round(self, tmp_path):
        rows = program_rows()
        col = header(1, 0).index(":new-deltas-labor-1")
        rows[1][col] = repr(float(rows[1][col]) * 1.01)
        errors = cc.rule_errors(year(tmp_path, rows))["program"]
        assert errors[0] < 1e-12
        assert errors[1] == pytest.approx(0.01 / 1.01, rel=1e-9)
        assert errors[2] < 1e-12


class TestPriceUpdateErrors:
    def test_consistent_prices_have_no_error(self, tmp_path):
        run = year(tmp_path, build_rows(IMBALANCES, SURPLUSES, "book"))
        assert max(cc.price_update_errors(run)) < 1e-12

    def test_a_price_moved_the_wrong_way_is_found(self, tmp_path):
        rows = program_rows()
        head = header(1, 0)
        price = head.index(":private-good-prices-1")
        step = head.index(":new-deltas-private-goods-1")
        # Round 1 has a surplus on commodity 1, so the price should fall from 700.
        rows[0][price] = repr(700 * (1 + float(rows[0][step])))
        errors = cc.price_update_errors(year(tmp_path, rows))
        assert errors[0] > 1e-2


class TestRoundSummary:
    def test_reports_worst_imbalance_and_step_range(self, tmp_path):
        run = year(tmp_path, build_rows(IMBALANCES, SURPLUSES, "book"))
        summary = cc.round_summary(run)
        assert [s.iteration for s in summary] == [1, 2, 3]
        assert summary[0].worst_imbalance_pct == pytest.approx(120.0)
        assert summary[2].worst_imbalance_pct == pytest.approx(30.0)
        steps = [book_step(v) for v in IMBALANCES[1]]
        assert summary[1].min_step == pytest.approx(min(steps), rel=1e-15)
        assert summary[1].max_step == pytest.approx(max(steps), rel=1e-15)


class TestCompareSteps:
    def test_counts_commodities_whose_step_differs(self, tmp_path):
        a = year(tmp_path, build_rows(IMBALANCES, SURPLUSES, "program"), name="a.csv")
        b = year(tmp_path, build_rows(IMBALANCES, SURPLUSES, "book"), name="b.csv")
        rounds = cc.compare_steps(a, b)
        assert len(rounds) == 3
        # Round 1: the program multiplies by 0.25 and the book by min(v, 0.25); they agree
        # for the commodities with v >= 0.25 (1.2, 0.4, 0.3) and differ for 0.2 and 0.05.
        assert rounds[0].differing == 2
        expected = max(abs(program_step(v, 0.25) - book_step(v)) for v in IMBALANCES[0])
        assert rounds[0].max_abs_step_diff == pytest.approx(expected, rel=1e-12)
        assert rounds[0].worst_imbalance_a == pytest.approx(120.0)
        assert rounds[0].worst_imbalance_b == pytest.approx(120.0)

    def test_identical_runs_differ_nowhere(self, tmp_path):
        a = year(tmp_path, build_rows(IMBALANCES, SURPLUSES, "paper"))
        rounds = cc.compare_steps(a, a)
        assert all(r.differing == 0 and r.max_abs_step_diff == 0.0 for r in rounds)
        assert all(math.isclose(r.worst_imbalance_a, r.worst_imbalance_b) for r in rounds)
