"""The step formulas of ``research/upstream/_price_rules.py``, and the line edits that put the
book's and the paper's rules into pequod-cljs.

The edits under ``docker/pequod-cljs/edits`` are the only other place a text rule is written
down. Their replacement lines are evaluated here with a small reader for the arithmetic forms
they use, and the result is set against the Python formula, so that the rule run in the program
and the rule run in demplan cannot drift apart without a failing test.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

import upstream_paths

import _price_rules as rules  # noqa: E402
import _source_edits as se  # noqa: E402

EDITS = upstream_paths.PEQUOD_CLJS_DOCKER_DIR / "edits"

LOCAL_NAMES = {"surplus", "demand", "supply", "price-delta-to-use"}
"""The let-bound names of csvgen.clj a replacement line may read."""


# ---------------------------------------------------------------- formulas


def test_relative_imbalance():
    assert rules.relative_imbalance(np.array([3.0]), np.array([1.0]))[0] == pytest.approx(1.0)
    assert rules.relative_imbalance(np.array([1.0]), np.array([3.0]))[0] == pytest.approx(1.0)


def test_program_step_uses_previous_multiplier_and_floor():
    v = np.array([0.1, 0.0, 2.0])
    prev = np.array([0.25, 0.0001, 0.5])
    w = rules.step_program(v, prev)
    assert w[0] == pytest.approx(0.25 * (1.05 - 0.5 ** 0.1))
    assert w[1] == 0.001                                   # floor binds
    assert w[2] == pytest.approx(0.25 * (1.05 - 0.5 ** 2.0))  # previous capped at 0.25


def test_book_step_this_round_capped_multiplier_uncapped_exponent():
    v = np.array([0.1, 0.5])
    w = rules.step_book(v)
    assert w[0] == pytest.approx(0.1 * (1.05 - 0.5 ** 0.1))
    assert w[1] == pytest.approx(0.25 * (1.05 - 0.5 ** 0.5))


def test_book_step_has_no_floor():
    assert rules.step_book(np.array([0.0]))[0] == 0.0


def test_paper_step_caps_both():
    v = np.array([0.1, 0.5])
    w = rules.step_paper(v)
    assert w[0] == pytest.approx(0.1 * (1.05 - 0.5 ** 0.1))
    assert w[1] == pytest.approx(0.25 * (1.05 - 0.5 ** 0.25))
    assert w[1] != pytest.approx(rules.step_book(v)[1])


@pytest.mark.parametrize(("floored", "plain"), [
    (rules.step_book_floored, rules.step_book),
    (rules.step_paper_floored, rules.step_paper),
])
def test_floored_steps_are_the_text_steps_with_the_program_floor(floored, plain):
    v = np.array([0.0, 0.0005, 0.004, 0.1, 0.3, 1.2])
    np.testing.assert_array_equal(floored(v), np.maximum(0.001, plain(v)))
    assert floored(np.array([0.0]))[0] == 0.001
    assert floored(np.array([0.3]))[0] == plain(np.array([0.3]))[0]


def test_next_price_zero_surplus_keeps_price_even_with_a_step():
    p = rules.next_price(np.array([10.0, 10.0, 10.0]), np.array([0.0, 1.0, -1.0]), np.array([0.5, 0.5, 0.5]))
    assert list(p) == [10.0, 5.0, 15.0]


def test_program_start_values():
    assert rules.INITIAL_MULTIPLIER == 0.25
    assert rules.INITIAL_PRICE == 700.0


# ---------------------------------------------------------------- the edits


def _tokens(text):
    return re.findall(r"\(|\)|[^\s()]+", text)


def _read(tokens, at=0):
    """One form from ``tokens[at]``: a nested list, a number or a symbol."""
    token = tokens[at]
    if token == "(":
        form, at = [], at + 1
        while tokens[at] != ")":
            item, at = _read(tokens, at)
            form.append(item)
        return form, at + 1
    try:
        return float(token), at + 1
    except ValueError:
        return token, at + 1


OPERATORS = {"*", "+", "-", "/", "min", "Math/abs", "Math/pow"}


def _evaluate(form, env):
    """The arithmetic subset of Clojure the replacement lines use, evaluated on numpy arrays."""
    if isinstance(form, float):
        return form
    if isinstance(form, str):
        return env[form]
    head, *args = form
    values = [_evaluate(a, env) for a in args]
    if head == "*":
        out = values[0]
        for v in values[1:]:
            out = out * v
        return out
    if head == "+":
        out = values[0]
        for v in values[1:]:
            out = out + v
        return out
    if head == "-":
        return -values[0] if len(values) == 1 else values[0] - values[1]
    if head == "/":
        return values[0] / values[1]
    if head == "min":
        return np.minimum(values[0], values[1])
    if head in ("Math/abs", "abs"):
        return np.abs(values[0])
    if head == "Math/pow":
        return np.power(values[0], values[1])
    raise ValueError(f"form not supported by this reader: {head}")


def _symbols(form):
    """Every symbol in ``form``, operators included."""
    if isinstance(form, float):
        return set()
    if isinstance(form, str):
        return {form}
    return set().union(*(_symbols(f) for f in form))


def _bindings(edit_name):
    """``{name: form}`` of the let bindings the edit set's replacement lines write."""
    out = {}
    for edit in se.load(EDITS / edit_name).edits:
        name, _, rest = edit.text.partition(" ")
        tokens = _tokens(rest)
        form, end = _read(tokens)
        assert end == len(tokens), edit.text
        assert name not in out
        out[name] = form
    return out


def _step_from_edits(edit_name, surplus, demand, supply):
    """The step the replaced ``delta`` binding computes for the given commodity values.

    A binding the edits leave alone is the program's own: ``price-delta-to-use`` on line 718 is
    ``1.05 - 0.5 ** v`` with this round's v (``_price_rules.step_program``'s base).
    """
    written = _bindings(edit_name)
    env = {"surplus": surplus, "demand": demand, "supply": supply}
    if "price-delta-to-use" in written:
        env["price-delta-to-use"] = _evaluate(written["price-delta-to-use"], env)
    else:
        env["price-delta-to-use"] = rules.CEILING - rules.DECAY_BASE ** rules.relative_imbalance(supply, demand)
    return _evaluate(written["delta"], env)


def _commodities():
    rng = np.random.default_rng(7)
    supply = rng.uniform(1.0, 2000.0, 400)
    demand = supply * rng.choice([0.2, 0.7, 0.9, 0.99, 1.0, 1.01, 1.1, 1.5, 3.0], 400)
    return supply - demand, demand, supply


@pytest.mark.parametrize(("edit_name", "step"), [
    ("rule-book-p181.json", rules.step_book),
    ("rule-paper-p7.json", rules.step_paper),
])
def test_edit_computes_the_step_of_price_rules(edit_name, step):
    surplus, demand, supply = _commodities()
    from_edit = _step_from_edits(edit_name, surplus, demand, supply)
    expected = step(rules.relative_imbalance(supply, demand))
    np.testing.assert_allclose(from_edit, expected, rtol=1e-15, atol=0)
    assert np.any(rules.relative_imbalance(supply, demand) > rules.CAP)
    assert np.any(expected < rules.FLOOR)


def test_the_two_edits_give_different_steps_above_the_cap():
    surplus, demand, supply = _commodities()
    book = _step_from_edits("rule-book-p181.json", surplus, demand, supply)
    paper = _step_from_edits("rule-paper-p7.json", surplus, demand, supply)
    above = rules.relative_imbalance(supply, demand) > rules.CAP
    assert np.all(book[above] != paper[above])
    np.testing.assert_array_equal(book[~above], paper[~above])


@pytest.mark.parametrize(("edit_name", "changed"), [
    ("rule-book-p181.json", {"delta"}),
    ("rule-paper-p7.json", {"price-delta-to-use", "delta"}),
])
def test_edit_rebinds_only_the_step_names(edit_name, changed):
    assert set(_bindings(edit_name)) == changed


@pytest.mark.parametrize("edit_name", ["rule-book-p181.json", "rule-paper-p7.json"])
def test_edit_reads_only_local_names_and_arithmetic(edit_name):
    for form in _bindings(edit_name).values():
        assert _symbols(form) <= LOCAL_NAMES | OPERATORS


@pytest.mark.skipif(upstream_paths.cached_upstream_file("pequod-cljs@71e44d3/csvgen.clj") is None,
                    reason="csvgen.clj at 71e44d3 not in research/data/upstream "
                    "(python research/upstream/fetch.py pequod-cljs@71e44d3/csvgen.clj)")
def test_the_program_line_the_book_edit_keeps_is_the_base_it_assumes():
    """Line 718, which the book's edit reads as price-delta-to-use, computes 1.05 - 0.5 ** v."""
    path = upstream_paths.cached_upstream_file("pequod-cljs@71e44d3/csvgen.clj")
    line = path.read_bytes().split(b"\n")[717].decode()
    name, _, rest = line.strip().partition(" ")
    assert name == "price-delta-to-use"
    tokens = _tokens(rest)
    form, end = _read(tokens)
    assert end == len(tokens)
    surplus, demand, supply = _commodities()
    np.testing.assert_allclose(
        _evaluate(form, {"surplus": surplus, "demand": demand, "supply": supply}),
        rules.CEILING - rules.DECAY_BASE ** rules.relative_imbalance(supply, demand), rtol=1e-15, atol=0)
