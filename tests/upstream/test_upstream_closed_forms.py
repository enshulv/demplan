"""The case generator and the result reader of the pequod-plus closed-form check,
``research/upstream/docker/pequod-plus/make_closed_form_cases.py`` and ``verify_closed_forms.py``.
The Docker part is not run here."""

from __future__ import annotations

import random

import numpy as np
import pytest

import upstream_paths  # noqa: F401  (puts the scripts on sys.path)

import make_closed_form_cases as mk  # noqa: E402
import verify_closed_forms as vf  # noqa: E402


def test_edn_writes_keywords_numeric_ids_vectors_and_doubles():
    text = mk.edn({"price-sets": {"uniform-700": {"labor": {1: 700.0, 2: 0.1}}},
                   "cases": [{"id": "sweep/0.5", "k": 3, "inputs": {"labor": [[7, 0.25]]}}]})
    assert text == ('{:price-sets {:uniform-700 {:labor {1 700.0 2 0.1}}} '
                    ':cases [{:id "sweep/0.5" :k 3 :inputs {:labor [[7 0.25]]}}]}')


@pytest.mark.parametrize("n", [3, 5, 8, 10])
def test_generator_council_has_n_inputs_in_the_populate_ranges(n):
    rng = random.Random(n)
    for _ in range(20):
        council = mk.generator_council(rng, n)
        sizes = [len(council["inputs"][c]) for c in mk.INPUT_CATEGORIES]
        assert sum(sizes) == n
        assert 1 <= sizes[0] <= 5 and 1 <= sizes[1] <= 3 and 1 <= sizes[2] <= 3
        assert 0.05 <= council["c"] <= 0.1 and 4 <= council["a"] <= 6 and 3 <= council["k"] <= 4
        assert council["s"] == 1.0
        exponents = [b for c in mk.INPUT_CATEGORIES for _, b in council["inputs"][c]]
        assert all(0.75 / (n + 3) <= b <= 0.85 / (n + 1) for b in exponents)
        ids = [i for c in mk.INPUT_CATEGORIES for i, _ in council["inputs"][c]]
        assert all(1 <= i <= 100 for i in ids)


def test_case_problem_applies_price_overrides_and_the_product_price():
    price_sets = {"uniform-700": {c: {str(i): 700.0 for i in range(1, 101)}
                                  for c in ("private-goods", "intermediate-inputs", "nature", "labor", "public-goods")}}
    case = {"price-set": "uniform-700", "industry": 1, "product": 9, "a": 5.0, "s": 1.0, "c": 0.07, "k": 3.5,
            "inputs": {"intermediate-inputs": [[9, 0.1]], "nature": [[2, 0.2]], "labor": [[3, 0.3]]},
            "price-overrides": {"nature": {"2": 350.0}, "intermediate-inputs": {"9": 1400.0}}}
    problem = vf.case_problem(case, price_sets)
    np.testing.assert_array_equal(problem.p, [1400.0, 350.0, 700.0])
    np.testing.assert_array_equal(problem.b, [0.1, 0.2, 0.3])
    assert problem.lam == 1400.0


def test_read_results_marks_councils_without_a_solution(tmp_path):
    path = tmp_path / "results.tsv"
    path.write_text("case_id\tentry_point\tn_inputs\toutput\teffort\tx\n"
                    "a/1\tutil/proposal\t2\t3.5\t0.25\t1.0;2.0\n"
                    "a/2\tutil/proposal\t11\t-\t-\t\n", encoding="utf-8")
    rows = vf.read_results(path)
    assert rows["a/1"]["missing"] is False and rows["a/1"]["output"] == 3.5
    np.testing.assert_array_equal(rows["a/1"]["x"], [1.0, 2.0])
    assert rows["a/2"]["missing"] is True


# ---------------------------------------------------------------- predicted x1 ratio of solution-5


def _five_inputs(p):
    """A five-input council with sum(b) = 0.8, c = 0.07 and k = 3.5, so D = c - k + k sum(b) = -0.63."""
    return vf.CouncilProblem(a=5.0, s=1.0, c=0.07, k=3.5, lam=700.0,
                             b=np.array([0.1, 0.2, 0.3, 0.15, 0.05]), p=np.array(p, dtype=float))


def test_predicted_x1_ratio_is_p2_over_p3_to_the_power_k_b3_over_d():
    # (1400 / 700) ** (3.5 * 0.3 / -0.63) = 2 ** (-5/3); b3 = 0.3 is the third exponent, b2 = 0.2 the second
    assert vf.predicted_x1_ratio(_five_inputs([700, 1400, 700, 700, 700])) == pytest.approx(2 ** (-5 / 3), rel=1e-12)
    assert vf.predicted_x1_ratio(_five_inputs([700, 700, 1400, 700, 700])) == pytest.approx(2 ** (5 / 3), rel=1e-12)


def test_predicted_x1_ratio_is_one_when_p2_equals_p3_whatever_the_other_prices():
    assert vf.predicted_x1_ratio(_five_inputs([350, 900, 900, 1400, 20])) == pytest.approx(1.0, abs=1e-15)


# ---------------------------------------------------------------- the all_match count

OPTIMUM = (10.0, 2.0, np.array([1.0, 2.0, 3.0]))
"""A maximiser's (output, effort, inputs)."""


def _row(output=10.0, effort=2.0, x=(1.0, 2.0, 3.0)):
    return {"entry_point": "csvgen/process-wc", "missing": False, "output": output, "effort": effort,
            "x": np.array(x)}


def test_largest_relative_difference_covers_output_effort_and_every_input():
    assert vf.largest_relative_difference(_row(), OPTIMUM) == 0.0
    assert vf.largest_relative_difference(_row(output=10.0 * 1.25), OPTIMUM) == pytest.approx(0.25)
    assert vf.largest_relative_difference(_row(effort=1.0), OPTIMUM) == pytest.approx(0.5)
    assert vf.largest_relative_difference(_row(x=(1.0, 2.0, 3.3)), OPTIMUM) == pytest.approx(0.1)


def test_a_case_matches_only_within_the_tolerance():
    assert vf.matches_optimum(_row(), OPTIMUM)
    assert vf.matches_optimum(_row(x=(1.0, 2.0, 3.0 * (1 + 1e-12))), OPTIMUM)
    assert not vf.matches_optimum(_row(x=(1.0, 2.0, 3.0 * (1 + 1e-6))), OPTIMUM)
    assert not vf.matches_optimum(_row(effort=2.0 * (1 - 1e-6)), OPTIMUM)
    assert not vf.matches_optimum(_row(output=10.0 * 1.01), OPTIMUM)


def test_summary_counts_as_all_match_only_the_cases_within_the_tolerance(capsys):
    problem = vf.CouncilProblem(a=5.0, s=1.0, c=0.07, k=3.5, lam=700.0,
                                b=np.array([0.2, 0.25, 0.3]), p=np.array([700.0, 900.0, 500.0]))
    optimum = vf.maximise(problem)
    output, effort, x = optimum
    rows = {"generator/1": _row(output, effort, x),
            "generator/2": _row(output, effort, x * np.array([1.0, 1.001, 1.0]))}
    ids = list(rows)
    vf.print_summary("44a6d08", rows, {("generator", 3): ids}, dict.fromkeys(ids, problem),
                     dict.fromkeys(ids, optimum))
    table = [line.split() for line in capsys.readouterr().out.splitlines() if line.startswith("44a6d08 ")]
    assert [row[:5] for row in table] == [["44a6d08", "generator", "3", "2", "1"]]
