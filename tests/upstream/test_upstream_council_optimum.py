"""The worker-council problem and its numerical maximiser, ``research/upstream/_council_optimum.py``,
and the reader of the councils of a dep1ex archive, ``research/upstream/_dep1ex_councils.py``.

A council chooses inputs x and effort e to maximise lam * a * prod(x**b) * e**c - p @ x - s * e**k.
The reference values here come from the first-order conditions solved by hand, and from the
closed form for effort in the pattern pequod-cljs's solution-4 prints, not from the module.
"""

from __future__ import annotations

import gzip
import math

import numpy as np
import pytest

import upstream_paths  # noqa: F401  (puts the scripts on sys.path)

import _council_optimum as co  # noqa: E402
import _dep1ex_councils as dc  # noqa: E402


def _problem(rng, n):
    b = rng.uniform(0.75 / (n + 2), 0.85 / (n + 2), n)
    return co.CouncilProblem(a=rng.uniform(4, 6), s=rng.choice([1.0, 1.3]), c=rng.uniform(0.05, 0.1),
                             k=rng.uniform(3, 4), lam=rng.uniform(300, 1500), b=b,
                             p=rng.uniform(300, 1500, n))


def _effort_closed_form(problem, flip_k_and_s=False):
    """Effort as solution-4 of csvgen.clj writes it, for any number of inputs; with
    ``flip_k_and_s`` the b_i*log(k) and b_i*log(s) terms carry the sign solution-8 gives them."""
    a, s, c, k, lam, b, p = problem.a, problem.s, problem.c, problem.k, problem.lam, problem.b, problem.p
    sign = 1.0 if flip_k_and_s else -1.0
    numerator = (-math.log(a) - float(b @ np.log(b)) - math.log(c) + b.sum() * math.log(c)
                 + math.log(k) + sign * b.sum() * math.log(k) + float(b @ np.log(p))
                 + math.log(s) + sign * b.sum() * math.log(s) - math.log(lam))
    return math.exp(numerator / (c - k + k * b.sum()))


def test_single_input_optimum_matches_the_hand_solution():
    problem = co.CouncilProblem(a=5.0, s=1.2, c=0.08, k=3.5, lam=900.0, b=np.array([0.4]), p=np.array([650.0]))
    # lam b z = p x and lam c z = s k e^k, substituted into z = a x^b e^c:
    # log z (1 - b - c/k) = log a + b log(lam b / p) + (c/k) log(lam c / (s k))
    b, c, k = 0.4, 0.08, 3.5
    log_z = (math.log(5.0) + b * math.log(900.0 * b / 650.0) + (c / k) * math.log(900.0 * c / (1.2 * k))) / (1 - b - c / k)
    z = math.exp(log_z)
    output, effort, x = co.maximise(problem)
    assert output == pytest.approx(z, rel=1e-12)
    assert x[0] == pytest.approx(900.0 * b * z / 650.0, rel=1e-12)
    assert effort == pytest.approx((900.0 * c * z / (1.2 * k)) ** (1 / k), rel=1e-12)


@pytest.mark.parametrize("n", [1, 3, 5, 8, 10])
def test_maximiser_satisfies_the_first_order_conditions(n):
    problem = _problem(np.random.default_rng(n), n)
    output, effort, x = co.maximise(problem)
    assert np.max(np.abs(co.foc_residuals(problem, output, effort, x))) < 1e-12
    assert abs(co.effort_condition_residual(problem, output, effort)) < 1e-12
    best = co.objective(problem, x, effort)
    for factor in (0.99, 1.01):
        assert co.objective(problem, x * factor, effort) < best
        assert co.objective(problem, x, effort * factor) < best


@pytest.mark.parametrize("n", [2, 4, 8])
def test_maximiser_effort_equals_the_closed_form_of_the_program_pattern(n):
    problem = _problem(np.random.default_rng(100 + n), n)
    _, effort, _ = co.maximise(problem)
    assert effort == pytest.approx(_effort_closed_form(problem), rel=1e-11)


@pytest.mark.parametrize("n", [4, 8, 10])
def test_predicted_effort_ratio_is_the_ratio_the_flipped_signs_give(n):
    problem = _problem(np.random.default_rng(200 + n), n)
    flipped = _effort_closed_form(problem, flip_k_and_s=True)
    right = _effort_closed_form(problem)
    assert co.predicted_effort_ratio(problem) == pytest.approx(flipped / right, rel=1e-12)
    assert co.predicted_effort_ratio(problem) < 1.0


def test_effort_condition_residual_measures_a_wrong_effort():
    problem = _problem(np.random.default_rng(5), 5)
    output, effort, _ = co.maximise(problem)
    # With the output held fixed, effort scaled by r moves log(s k e^k) by k log r.
    assert co.effort_condition_residual(problem, output, effort * 0.5) == pytest.approx(-problem.k * math.log(0.5), rel=1e-12)


def test_foc_residuals_are_production_then_inputs_then_effort():
    problem = co.CouncilProblem(a=2.0, s=1.0, c=0.1, k=3.0, lam=10.0, b=np.array([0.3, 0.2]), p=np.array([4.0, 5.0]))
    x, effort = np.array([1.0, 2.0]), 1.5
    output = 2.0 * 1.0 ** 0.3 * 2.0 ** 0.2 * 1.5 ** 0.1
    r = co.foc_residuals(problem, output, effort, x)
    assert r[0] == pytest.approx(0.0, abs=1e-15)
    assert r[1] == pytest.approx(math.log(10 * 0.3 * output) - math.log(4.0 * 1.0))
    assert r[2] == pytest.approx(math.log(10 * 0.2 * output) - math.log(5.0 * 2.0))
    assert r[3] == pytest.approx(math.log(10 * 0.1 * output) - math.log(1.0 * 3.0 * 1.5 ** 3))


# ---------------------------------------------------------------- dep1ex councils

ARCHIVE_TEXT = """(ns pequod-cljs.dep1ex01)

(def ccs
[{:effort 1,
  :utility-exponents [0.1 0.2]}])

(def wcs
[{:effort 0.5,
  :labor-exponents [0.15 0.16],
  :industry 2,
  :output 0,
  :s 1,
  :du 3.25,
  :c 0.0744,
  :product 7,
  :production-inputs [[82 96] [81] [27 90]],
  :input-exponents [0.157 0.1507],
  :toothache false,
  :nature-exponents [0.1502],
  :a 4.85}
 {:effort 0.5,
  :labor-exponents [0.2],
  :industry 0,
  :output 0,
  :s 1,
  :du 3.8,
  :c 0.069,
  :product 1,
  :production-inputs [[5] [9] [18]],
  :input-exponents [0.2088],
  :toothache false,
  :nature-exponents [0.11],
  :a 5.5}])
"""


def test_read_worker_councils_reads_the_wcs_vector(tmp_path):
    path = tmp_path / "dep1ex01.clj.gz"
    path.write_bytes(gzip.compress(ARCHIVE_TEXT.encode()))
    councils = dc.read_worker_councils(path)
    assert len(councils) == 2
    assert councils[0]["production-inputs"] == [[82, 96], [81], [27, 90]]
    assert councils[0]["du"] == 3.25 and councils[0]["toothache"] is False
    assert councils[1]["product"] == 1


def test_council_from_dep1ex_pairs_each_input_with_its_exponent(tmp_path):
    path = tmp_path / "dep1ex01.clj.gz"
    path.write_bytes(gzip.compress(ARCHIVE_TEXT.encode()))
    council = dc.council_from_dep1ex(dc.read_worker_councils(path)[0])
    assert council == {
        "industry": 2, "product": 7, "a": 4.85, "s": 1.0, "c": 0.0744, "k": 3.25,
        "inputs": {"intermediate-inputs": [[82, 0.157], [96, 0.1507]], "nature": [[81, 0.1502]],
                   "labor": [[27, 0.15], [90, 0.16]]},
    }
    assert dc.input_count(council) == 5


def test_council_from_dep1ex_refuses_exponents_that_do_not_pair_with_inputs():
    wc = {"industry": 0, "product": 1, "a": 5.0, "s": 1, "c": 0.07, "du": 3.0,
          "production-inputs": [[1, 2], [3], [4]], "input-exponents": [0.1],
          "nature-exponents": [0.1], "labor-exponents": [0.1]}
    with pytest.raises(ValueError):
        dc.council_from_dep1ex(wc)
