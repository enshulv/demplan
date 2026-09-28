"""``research/upstream/_step_check.py`` on synthetic output files built by the program's rule."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import upstream_paths  # noqa: F401  (puts the scripts on sys.path)

import _step_check as sc  # noqa: E402
from _program_output import ProgramOutput, Year  # noqa: E402


def _year(rng, rounds, multiplier, price, first_line):
    rows = {k: [] for k in ("price", "new_delta", "pdlist", "supply", "demand", "surplus", "threshold")}
    for _ in range(rounds):
        s = rng.uniform(50, 150, 500)
        d = rng.uniform(50, 150, 500)
        v = np.abs(2 * (s - d)) / (s + d)
        w = np.maximum(0.001, np.minimum(multiplier, 0.25) * (1.05 - 0.5 ** v))
        sur = s - d
        price = price * np.where(sur > 0, 1 - w, np.where(sur < 0, 1 + w, 1.0))
        multiplier = np.minimum(v, 0.25)
        for k, a in (("price", price), ("new_delta", w), ("pdlist", multiplier), ("supply", s),
                     ("demand", d), ("surplus", sur), ("threshold", 100 * v)):
            rows[k].append(a)
    year = Year(lines=np.arange(first_line, first_line + rounds), iteration=np.arange(1, rounds + 1),
                color=(":red",) * rounds, end_line=first_line + rounds,
                **{k: np.array(v) for k, v in rows.items()})
    return year, multiplier, price


def _output(carry=True):
    rng = np.random.default_rng(1)
    y1, m, p = _year(rng, 4, np.full(500, 0.25), np.full(500, 700.0), 2)
    if not carry:
        m, p = np.full(500, 0.25), np.full(500, 700.0)
    y2, _, _ = _year(rng, 3, m, p, 7)
    return ProgramOutput(Path("dep1ex61.csv"), (y1, y2), 17)


def test_program_rule_reproduces_its_own_output():
    check = sc.StepCheck()
    check.add(1, _output())
    for year in (1, 2):
        assert check.at("program", year).error < 1e-14
        assert check.at("pdlist", year).error < 1e-15
        assert check.at("price", year).error < 1e-14
        assert check.at("book", year).error > 1e-2
        assert check.at("paper", year).error > 1e-2
    assert check.at("step, pdlist carried", 2).error < 1e-14
    assert check.at("step, pdlist reset", 2).error > 1e-3
    assert check.at("price, price carried", 2).error < 1e-14
    assert check.at("price, price reset", 2).error > 1e-3
    assert check.at("program", 1).cells == 4 * 500


def test_reset_state_is_detected_at_the_year_boundary():
    check = sc.StepCheck()
    check.add(1, _output(carry=False))
    assert check.at("step, pdlist reset", 2).error < 1e-14
    assert check.at("step, pdlist carried", 2).error > 1e-3
    assert check.at("price, price reset", 2).error < 1e-14
    assert check.at("price, price carried", 2).error > 1e-3
    assert check.at("program", 2).error > 1e-3  # the default reading carries the state


def test_location_names_file_line_round_and_commodity():
    out = _output()
    out.years[0].new_delta[2, 331] *= 1.5
    check = sc.StepCheck()
    check.add(7, out)
    w = check.at("program", 1)
    assert w.error == pytest.approx(1 / 3, rel=1e-9)
    assert w.where == "exp 7 dep1ex61.csv line 4 year 1 round 3 labor-32"


def test_not_finite_errors_are_counted():
    out = _output()
    out.years[0].supply[0, 5] = np.nan
    check = sc.StepCheck()
    check.add(1, out)
    assert check.at("program", 1).not_finite >= 1
    assert np.isfinite(check.at("program", 1).error)


def test_wrong_pdlist_column_is_detected():
    out = _output()
    out.years[0].pdlist[1, 10] += 0.01
    check = sc.StepCheck()
    check.add(1, out)
    assert check.at("pdlist", 1).error == pytest.approx(0.01)
