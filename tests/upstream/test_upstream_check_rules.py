"""The rules, series comparisons and round counts of ``research/upstream/check_rules.py``.

The text rules are checked against the formulas written out here, not against
``_price_rules.py``; the program's rule is demplan's own ``book_2021_rule``. The one test that
runs demplan on a published economy needs the dep1ex01 archive and skips without it.
"""

import numpy as np
import pytest

import upstream_paths

import check_rules  # noqa: E402

V = np.array([0.0, 0.1, 0.25, 0.3, 1.2, 0.0005])
PRICE = np.array([700.0, 10.0, 3.0, 50.0, 2.0, 100.0])
SURPLUS = np.array([0.0, 5.0, -1.0, 7.0, -3.0, 2.0])


def expected_price(step):
    return PRICE * np.where(SURPLUS > 0, 1 - step, np.where(SURPLUS < 0, 1 + step, 1.0))


# ---------------------------------------------------------------- rules


def test_book_literal_caps_multiplier_only():
    step = np.minimum(V, 0.25) * (1.05 - 0.5 ** V)
    got = check_rules.BOOK_P181(PRICE, SURPLUS, V)
    np.testing.assert_array_equal(got, expected_price(step))


def test_paper_literal_caps_both():
    capped = np.minimum(V, 0.25)
    step = capped * (1.05 - 0.5 ** capped)
    got = check_rules.PAPER_P7(PRICE, SURPLUS, V)
    np.testing.assert_array_equal(got, expected_price(step))


def test_book_and_paper_differ_only_above_cap():
    book = check_rules.BOOK_P181(PRICE, SURPLUS, V)
    paper = check_rules.PAPER_P7(PRICE, SURPLUS, V)
    above = V > 0.25
    np.testing.assert_array_equal(book[~above], paper[~above])
    # surplus nonzero at the two entries above the cap, so the prices must differ there
    assert np.all(book[above] != paper[above])


def test_no_floor_means_tiny_step():
    # v = 0.0005: step = 0.0005 * (1.05 - 0.5**0.0005) ~ 2.5e-5, well below 0.001
    got = check_rules.BOOK_P181(PRICE, SURPLUS, V)
    assert got[5] == pytest.approx(100.0 * (1 - 0.0005 * (1.05 - 0.5 ** 0.0005)), rel=1e-15)
    assert 100.0 * (1 - 0.001) < got[5]


def test_floor_variants_apply_floor():
    for rule, capped_exp in ((check_rules.BOOK_P181_FLOORED, False), (check_rules.PAPER_P7_FLOORED, True)):
        capped = np.minimum(V, 0.25)
        exponent = capped if capped_exp else V
        step = np.maximum(0.001, capped * (1.05 - 0.5 ** exponent))
        np.testing.assert_array_equal(rule(PRICE, SURPLUS, V), expected_price(step))


def test_zero_surplus_keeps_price_even_with_floor():
    got = check_rules.BOOK_P181_FLOORED(PRICE, SURPLUS, V)
    assert got[0] == PRICE[0]


def test_rules_are_price_rules_for_the_prefab():
    from demplan.prefabs.hahnel import StatelessPriceRule
    for name, rule in check_rules.RULES.items():
        assert hasattr(rule, "initial_state") and callable(rule), name
    assert check_rules.RULES[check_rules.PROGRAM].__class__.__name__ == "Book2021Rule"
    for key in (check_rules.BOOK, check_rules.PAPER, check_rules.BOOK_FLOORED, check_rules.PAPER_FLOORED):
        assert isinstance(check_rules.RULES[key], StatelessPriceRule)
    assert list(check_rules.RULES) == [check_rules.PROGRAM, check_rules.BOOK, check_rules.PAPER,
                                       check_rules.BOOK_FLOORED, check_rules.PAPER_FLOORED]


# ---------------------------------------------------------------- counting and comparing


def test_first_round_below_is_strict_and_one_based():
    worst = [9.0, 5.0, 4.999, 3.0, 2.0]
    assert check_rules.first_round_below(worst, 5.0) == 3
    assert check_rules.first_round_below(worst, 3.0) == 5
    assert check_rules.first_round_below(worst, 1.0) is None
    assert check_rules.first_round_below([], 5.0) is None
    assert check_rules.first_round_below(np.array([6.0, 5.0, 4.99]), 5.0) == 3


def test_largest_difference_over_common_rounds():
    worst_a = [10.0, 5.0, 3.0]
    worst_b = [10.5, 5.0, 2.0, 1.0]
    got = check_rules.largest_difference(worst_a, worst_b)
    assert got.compared == 3
    assert got.value == pytest.approx(1.0)
    assert got.round == 3


def test_compare_uses_common_rounds_and_reports_location():
    c = check_rules.compare([10.0, 6.0, 4.0, 2.9], np.array([10.0, 6.5, 4.0]))
    assert c.rounds == (4, 3)
    assert c.difference.value == pytest.approx(0.5)
    assert c.difference.round == 2
    assert c.difference.compared == 3
    assert c.first_below_5 == (3, 3)


# ---------------------------------------------------------------- one run on published data


@pytest.mark.slow
@pytest.mark.skipif(not upstream_paths.dep1ex_path(1).is_file(), reason="dep1ex01 archive not available")
def test_one_run_per_rule_gives_the_round_counts_the_procedure_stops_at():
    import demplan

    economy = demplan.load_dep1ex(upstream_paths.dep1ex_path(1), endowment=check_rules.ENDOWMENT)
    program = check_rules.run_rule(economy, check_rules.RULES[check_rules.PROGRAM])
    stops = check_rules.procedure_rounds(economy, check_rules.RULES[check_rules.PROGRAM])
    assert program.diverged is False
    assert check_rules.first_round_below(program.worst_pct, 5.0) == stops[5.0] == 12
    assert check_rules.first_round_below(program.worst_pct, 3.0) == stops[3.0] == len(program.worst_pct)
    assert program.worst_pct[-1] < 3.0 <= program.worst_pct[-2]
    book = check_rules.run_rule(economy, check_rules.RULES[check_rules.BOOK])
    assert check_rules.first_round_below(book.worst_pct, 5.0) == 11


# ---------------------------------------------------------------- what the floor changes


def _counts():
    """First rounds below 5% and 3% for experiments 1-3; the floor changes experiment 2 under the
    book's rule at 5% and experiment 3 under the paper's rule at 3%, where the rule without the
    floor never gets below 3%."""
    B, BF, P, PF = check_rules.BOOK, check_rules.BOOK_FLOORED, check_rules.PAPER, check_rules.PAPER_FLOORED
    return {
        5.0: {check_rules.PROGRAM: {1: 12, 2: 12, 3: 12},
              B: {1: 11, 2: 10, 3: 11}, BF: {1: 11, 2: 12, 3: 11},
              P: {1: 14, 2: 13, 3: 13}, PF: {1: 14, 2: 13, 3: 13}},
        3.0: {check_rules.PROGRAM: {1: 19, 2: 20, 3: 19},
              B: {1: 17, 2: 18, 3: 17}, BF: {1: 17, 2: 18, 3: 17},
              P: {1: 25, 2: 24, 3: None}, PF: {1: 25, 2: 24, 3: 31}},
    }


def test_floor_changes_lists_the_experiments_per_printed_rule():
    assert check_rules.floor_changes([1, 2, 3], _counts()) == {check_rules.BOOK: [2], check_rules.PAPER: [3]}
    assert check_rules.floor_changes([1], _counts()) == {check_rules.BOOK: [], check_rules.PAPER: []}


def test_floor_summary_counts_experiments_per_rule_and_either():
    assert check_rules.floor_summary([1, 2, 3], _counts()) == (
        "Experiments where the floor of 0.001 changes the first round below 5% or 3%: "
        "book 1 of 3, paper 1 of 3, either 2 of 3")
    assert check_rules.floor_summary([1], _counts()).endswith("book 0 of 1, paper 0 of 1, either 0 of 1")


def test_floor_table_puts_each_printed_rule_next_to_its_floored_variant(capsys):
    check_rules.print_floor_table([1, 3], _counts())
    rows = [line.split() for line in capsys.readouterr().out.splitlines()]
    assert rows[-2] == ["1", "11", "11", "17", "17", "14", "14", "25", "25", "-"]
    assert rows[-1] == ["3", "11", "11", "17", "17", "13", "13", "-", "31", "paper", "<3%"]
