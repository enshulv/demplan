"""The parts of ``research/bench/hahnel_book.py`` that decide what it reports.

The script needs the 40 archives and a long run, so its readings are checked here on their own:
which round counts as the first one below a threshold, how the Table 9.5 statistic is formed
from those rounds, and the numbers it copies from Hahnel (2021), ch. 9.

The book is not redistributable, so its tables are not repeated here. Each table is pinned by
two totals counted from the book's pages 178-185: the plain sum of its 40 entries, and
the sum of ``n * entry`` over experiments ``n = 1..40``, which also moves when two entries
trade places.
"""

from __future__ import annotations

import sys
from fractions import Fraction

import pytest

from reference import synthetic
from reference.dep1ex_numpy import Dep1exLayout, reference_run
from reference.paths import BENCH_DIR

if str(BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(BENCH_DIR))

import hahnel_book  # noqa: E402  (needs the sys.path entry above)

EXPERIMENTS = range(1, 41)

SYNTHETIC_LAYOUT = Dep1exLayout(
    n_priv=synthetic.N_PER_CLASS, n_pub=synthetic.N_PER_CLASS, n_goods=synthetic.N_PER_CLASS
)

BOOK_TOTALS = {
    # book_row key: (sum over the 40 experiments, sum of experiment number times entry)
    "table_9_1_first_below_5": (474, 9700),
    "table_9_2_first_below_3": (769, 15740),
    "table_9_4_rounds": (261, 5321),
    "table_9_4_gdp": (Fraction("97.843"), Fraction("1992.821")),
    "table_9_5_rounds": (151, 3079),
    "table_9_6_rounds": (251, 5060),
    "table_9_6_gdp": (Fraction("74.391"), Fraction("1519.077")),
}
"""Totals of each table of Hahnel (2021), ch. 9, pp. 178-185, as the book prints it.

The GDP columns are printed with at most three decimals, so their totals are exact fractions;
an entry is compared through ``Fraction(str(value))``, the decimal the script wrote.
"""


def exact(value) -> Fraction:
    """A book entry as an exact decimal: an int stays itself, a float is read as written."""
    return Fraction(str(value)) if isinstance(value, float) else Fraction(value)


class TestFirstRoundBelow:
    def test_the_first_round_under_the_threshold_counted_from_one(self):
        assert hahnel_book.first_round_below([12.0, 7.5, 4.0, 2.0], 5.0) == 3

    def test_a_round_exactly_at_the_threshold_is_not_below_it(self):
        assert hahnel_book.first_round_below([12.0, 5.0, 4.999, 2.0], 5.0) == 3

    def test_a_round_at_the_threshold_as_the_last_one_leaves_none(self):
        assert hahnel_book.first_round_below([12.0, 5.0], 5.0) is None

    def test_a_later_round_back_above_does_not_undo_the_first(self):
        assert hahnel_book.first_round_below([12.0, 4.0, 6.0, 2.0], 5.0) == 2

    def test_no_round_below_gives_none(self):
        assert hahnel_book.first_round_below([12.0, 9.0, 5.5], 5.0) is None

    def test_no_rounds_gives_none(self):
        assert hahnel_book.first_round_below([], 5.0) is None

    def test_the_first_round_itself_can_be_the_answer(self):
        assert hahnel_book.first_round_below([2.0, 1.0], 3.0) == 1


class TestThresholdReadings:
    """What one cold run is read as: Tables 9.1, 9.2 and 9.5."""

    WORST = [40.0, 18.0, 10.0, 9.99, 7.0, 5.0, 4.2, 3.1, 3.0, 2.5]
    # below 10: round 4 (10.0 is not below 10); below 5: round 7; below 3: round 10

    def test_the_first_round_below_each_threshold(self):
        readings = hahnel_book.threshold_readings(self.WORST)
        assert readings["first_below_10"] == 4
        assert readings["first_below_5"] == 7
        assert readings["first_below_3"] == 10

    def test_table_9_5_counts_the_rounds_from_below_10_to_below_5(self):
        assert hahnel_book.threshold_readings(self.WORST)["rounds_10_to_5"] == 3

    def test_table_9_5_is_zero_when_one_round_passes_both(self):
        readings = hahnel_book.threshold_readings([30.0, 4.0, 2.0])
        assert readings["first_below_10"] == readings["first_below_5"] == 2
        assert readings["rounds_10_to_5"] == 0

    def test_table_9_5_is_none_when_the_run_never_gets_below_5(self):
        readings = hahnel_book.threshold_readings([30.0, 9.0, 6.0])
        assert readings["first_below_10"] == 2
        assert readings["first_below_5"] is None
        assert readings["rounds_10_to_5"] is None

    def test_table_9_5_is_none_when_the_run_never_gets_below_10(self):
        readings = hahnel_book.threshold_readings([30.0, 20.0])
        assert readings == {
            "first_below_10": None,
            "first_below_5": None,
            "first_below_3": None,
            "rounds_10_to_5": None,
        }

    def test_the_readings_come_in_the_order_the_script_writes_them(self):
        assert list(hahnel_book.threshold_readings(self.WORST)) == [
            "first_below_10",
            "first_below_5",
            "first_below_3",
            "rounds_10_to_5",
        ]


@pytest.fixture(scope="module")
def cold():
    """``cold_start`` on the synthetic economy."""
    return hahnel_book.cold_start(synthetic.build_economy())


@pytest.fixture(scope="module")
def reference_rounds():
    """The reference's round count on the synthetic economy, run to 10, 5 and 3 percent."""
    wc, cc, _, endowment = synthetic.build_reference_inputs()
    return {
        threshold: reference_run(
            wc, cc, SYNTHETIC_LAYOUT, threshold=threshold, endowment_per_commodity=endowment
        )[0]
        for threshold in (10.0, 5.0, 3.0)
    }


class TestColdStartOnTheSyntheticEconomy:
    """``cold_start`` against separate reference runs stopped at 10, 5 and 3 percent.

    The reference is ``research/bench/endowment.py`` in mode ``cljs_lagged``. A run stopped at
    a threshold ends on the first round whose worst imbalance is below it, so its round count
    is what the one cold run to 3 percent has to report for that threshold.
    """

    def test_the_run_reaches_three_percent(self, cold, reference_rounds):
        assert cold["converged"] is True
        assert cold["rounds"] == reference_rounds[3.0]

    def test_each_reading_is_the_round_a_run_to_that_threshold_stops_at(
        self, cold, reference_rounds
    ):
        assert cold["first_below_10"] == reference_rounds[10.0]
        assert cold["first_below_5"] == reference_rounds[5.0]
        assert cold["first_below_3"] == reference_rounds[3.0]

    def test_table_9_5_is_the_difference_of_the_two_reference_runs(
        self, cold, reference_rounds
    ):
        assert reference_rounds[5.0] > reference_rounds[10.0]
        assert cold["rounds_10_to_5"] == reference_rounds[5.0] - reference_rounds[10.0]

    def test_one_worst_imbalance_is_kept_per_round(self, cold):
        assert len(cold["worst_pct_per_round"]) == cold["rounds"]


class TestTheBooksNumbers:
    @pytest.mark.parametrize("key", sorted(BOOK_TOTALS))
    def test_the_sum_over_the_forty_experiments(self, key):
        total, _ = BOOK_TOTALS[key]
        assert sum(exact(hahnel_book.book_row(n)[key]) for n in EXPERIMENTS) == total

    @pytest.mark.parametrize("key", sorted(BOOK_TOTALS))
    def test_the_sum_weighted_by_experiment_number(self, key):
        _, weighted = BOOK_TOTALS[key]
        assert sum(n * exact(hahnel_book.book_row(n)[key]) for n in EXPERIMENTS) == weighted

    def test_a_row_carries_every_table(self):
        assert set(hahnel_book.book_row(1)) == set(BOOK_TOTALS)

    def test_there_are_forty_experiments(self):
        assert hahnel_book.experiment_range("1-40") == list(EXPERIMENTS)
        with pytest.raises(SystemExit, match="between 1 and 40"):
            hahnel_book.experiment_range("41")
