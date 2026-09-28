"""``research/upstream/check_effort.py`` on a synthetic output file.

The recorded output and effort of each council are made here: by the council optimum at the
prices of the row before (what csvgen.clj at 71e44d3 does, lines 884-889), and, for an
eight-input council, with the effort solution-8 prints. The tests check that the script reads
the right row's prices, maps every input and product to its price column, and reports the
eight-input effort as off by the predicted ratio while the other councils match.
"""

from __future__ import annotations

import numpy as np
import pytest

import upstream_paths  # noqa: F401  (puts the scripts on sys.path)

import _council_optimum as co  # noqa: E402
import check_effort as ce  # noqa: E402
from _program_output import Year  # noqa: E402

PER = 100


def _council(industry, product, inputs, rng):
    n = sum(len(v) for v in inputs.values())
    return {"industry": industry, "product": product, "a": rng.uniform(4, 6), "s": 1.0,
            "c": rng.uniform(0.05, 0.1), "k": rng.uniform(3, 4),
            "inputs": {cat: [[i, rng.uniform(0.75 / (n + 2), 0.85 / (n + 2))] for i in ids]
                       for cat, ids in inputs.items()}}


def _councils():
    rng = np.random.default_rng(3)
    return [
        _council(0, 4, {"intermediate-inputs": [2], "nature": [5], "labor": [9]}, rng),
        _council(1, 100, {"intermediate-inputs": [1, 3], "nature": [100], "labor": [7, 8]}, rng),
        _council(2, 1, {"intermediate-inputs": [10, 20, 30], "nature": [40, 50], "labor": [60, 70, 80]}, rng),
    ]


def _prices(seed):
    return np.random.default_rng(seed).uniform(400.0, 1100.0, 5 * PER)


def _year(councils, price_rows, recorded_at, flip_eight=True):
    """A year whose row r records each council's optimum at ``recorded_at[r]``."""
    outputs, efforts = [], []
    for prices in recorded_at:
        row_out, row_eff = [], []
        for council in councils:
            problem = ce.council_problem(council, prices)
            z, e, _ = co.maximise(problem)
            if flip_eight and len(problem.b) == 8:
                e = e * co.predicted_effort_ratio(problem)
            row_out.append(z)
            row_eff.append(e)
        outputs.append(row_out)
        efforts.append(row_eff)
    rows = len(price_rows)
    zeros = np.zeros((rows, 5 * PER))
    return Year(lines=np.arange(2, 2 + rows), iteration=np.arange(1, rows + 1), color=(":red",) * rows,
                price=np.array(price_rows), new_delta=zeros, pdlist=zeros, supply=zeros, demand=zeros,
                surplus=zeros, threshold=zeros, end_line=None, per_category=PER,
                wc_ids=tuple(range(1, len(councils) + 1)), wc_output=np.array(outputs),
                wc_effort=np.array(efforts))


def test_proposal_prices_are_the_previous_rows_prices_and_700_before_the_first():
    councils = _councils()
    first, second = _prices(1), _prices(2)
    year = _year(councils, [first, second], [np.full(500, 700.0), first])
    np.testing.assert_array_equal(ce.proposal_prices(year, 0), np.full(500, 700.0))
    np.testing.assert_array_equal(ce.proposal_prices(year, 1), first)


def test_council_problem_takes_each_price_from_its_category_block():
    prices = np.arange(1.0, 501.0)
    council = {"industry": 2, "product": 3, "a": 5.0, "s": 1.0, "c": 0.07, "k": 3.5,
               "inputs": {"intermediate-inputs": [[4, 0.1]], "nature": [[5, 0.2], [100, 0.05]],
                          "labor": [[1, 0.15]]}}
    problem = ce.council_problem(council, prices)
    # blocks: private 1-100, intermediate 101-200, nature 201-300, labour 301-400, public 401-500
    np.testing.assert_array_equal(problem.p, [104.0, 205.0, 300.0, 301.0])
    np.testing.assert_array_equal(problem.b, [0.1, 0.2, 0.05, 0.15])
    assert problem.lam == 403.0
    assert (problem.a, problem.s, problem.c, problem.k) == (5.0, 1.0, 0.07, 3.5)
    assert ce.council_problem({**council, "industry": 0}, prices).lam == 3.0
    assert ce.council_problem({**council, "industry": 1}, prices).lam == 103.0


def test_only_the_eight_input_effort_differs_and_by_the_predicted_ratio():
    councils = _councils()
    first, second = _prices(1), _prices(2)
    year = _year(councils, [first, second], [np.full(500, 700.0), first])
    result = ce.compare_round(councils, year, 1, ce.proposal_prices(year, 1))
    groups = {g.n_inputs: g for g in ce.summarise(result)}
    assert sorted(groups) == [3, 5, 8]
    for n in (3, 5):
        assert groups[n].all_match == groups[n].count == 1
        assert groups[n].output_max < 1e-12
        assert max(abs(groups[n].effort_min), abs(groups[n].effort_max)) < 1e-12
        assert groups[n].effort_condition_max < 1e-11
    eight = groups[8]
    assert eight.all_match == 0
    assert eight.output_max < 1e-12
    assert eight.effort_max < -0.5
    assert eight.predicted_gap_max < 1e-12
    assert eight.effort_condition_max > 1.0


def test_the_rows_own_prices_do_not_reproduce_the_recorded_output():
    councils = _councils()
    first, second = _prices(1), _prices(2)
    year = _year(councils, [first, second], [np.full(500, 700.0), first])
    result = ce.compare_round(councils, year, 1, year.price[1])
    groups = ce.summarise(result)
    assert all(g.all_match == 0 for g in groups)
    assert min(g.output_max for g in groups) > 1e-3


def test_compare_round_refuses_councils_that_do_not_line_up_with_the_columns():
    councils = _councils()
    year = _year(councils, [_prices(1)], [np.full(500, 700.0)])
    with pytest.raises(ValueError, match="worker council"):
        ce.compare_round(councils[:2], year, 0, ce.proposal_prices(year, 0))
