"""What one program output file says for each column of the book's tables.

Round numbers are the file's own ``:iteration`` values. A threshold is met when every one of
the 500 ``threshold-report`` values is strictly below it, which is how ``show-color`` in
csvgen.clj at 71e44d3 (lines 876-882) assigns its colours:

  blue    every value < 3        green   every value < 5        yellow  every value < 10
  orange  every value < 20       red     otherwise

The same rounds are also read from the ``:color`` column two ways: the first row whose colour
is the named one or a later one in that list (``first_color_at_least``), and the first row
whose colour is exactly the named one, which is what ``getFirstColor`` and
``getYearTwoFirstGreen`` in bin/dep_data_process.py at 7757bb4 (lines 41-46) do.

Real GDP growth follows note 15 of chapter 9 of the book (p. 193) and ``computeGdp``,
``getYearOneData``, ``getYearTwoData`` and the "table 4, gdp" block of bin/dep_data_process.py
(lines 48-65 and 107-126): GDP is the sum over private and public goods of price times supply,
taken from the last row of each year; growth is computed once at each year's prices and the two
percentages are averaged.
"""
from __future__ import annotations

import dataclasses
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

import numpy as np

from _program_output import CATEGORIES, PER_CATEGORY, ProgramOutput, Year

COLOR_ORDER = (":red", ":orange", ":yellow", ":green", ":blue")
THREE_DECIMALS = Decimal("0.001")
BOOK_THRESHOLDS = (10.0, 5.0, 3.0)
YEAR_2_THRESHOLD = 5.0
COLOR_OF_THRESHOLD = {10.0: ":yellow", 5.0: ":green", 3.0: ":blue"}


def first_all_below(threshold: np.ndarray, iteration: np.ndarray, limit: float) -> int | None:
    """The first iteration whose every value is strictly below ``limit``, or ``None``."""
    below = np.all(threshold < limit, axis=1)
    return int(iteration[np.argmax(below)]) if below.any() else None


def first_color_at_least(colors: tuple[str, ...], iteration: np.ndarray, color: str) -> int | None:
    """The first iteration whose colour is ``color`` or later in :data:`COLOR_ORDER`."""
    wanted = _rank(color)
    for number, seen in zip(iteration, colors):
        if _rank(seen) >= wanted:
            return int(number)
    return None


def first_color_exact(colors: tuple[str, ...], iteration: np.ndarray, color: str) -> int | None:
    """The first iteration whose colour is exactly ``color``."""
    _rank(color)
    for number, seen in zip(iteration, colors):
        if _rank(seen) == _rank(color):
            return int(number)
    return None


def _rank(color: str) -> int:
    """Position of ``color`` in :data:`COLOR_ORDER`; ``ValueError`` for any other value."""
    if color not in COLOR_ORDER:
        raise ValueError(f"unknown colour {color!r}; csvgen.clj writes {', '.join(COLOR_ORDER)}")
    return COLOR_ORDER.index(color)


@dataclasses.dataclass(frozen=True)
class Growth:
    """Real GDP growth between two years, in percent."""

    year_1_prices: float
    year_2_prices: float
    mean: float


def gdp_growth(price_1, supply_1, price_2, supply_2) -> Growth:
    """Note 15: growth at year-1 prices and at year-2 prices, and their mean.

    The four arguments are the prices and supplies of the goods counted, in the same order.
    The sums run in that order from 0.0, as ``computeGdp`` does.
    """
    at_1 = 100 * ((_gdp(price_1, supply_2) - _gdp(price_1, supply_1)) / _gdp(price_1, supply_1))
    at_2 = 100 * ((_gdp(price_2, supply_2) - _gdp(price_2, supply_1)) / _gdp(price_2, supply_1))
    return Growth(year_1_prices=at_1, year_2_prices=at_2, mean=(at_2 + at_1) / 2)


def _gdp(price, supply) -> float:
    """``sum(price * supply)`` accumulated left to right in Python floats."""
    total = 0.0
    for p, s in zip(price, supply):
        total = total + float(p) * float(s)
    return total


def truncated(value: float) -> Decimal:
    """``value`` cut to three decimals, from its exact binary value."""
    return Decimal(value).quantize(THREE_DECIMALS, rounding=ROUND_DOWN)


def rounded(value: float) -> Decimal:
    """``value`` rounded half up to three decimals, from its exact binary value."""
    return Decimal(value).quantize(THREE_DECIMALS, rounding=ROUND_HALF_UP)


def _gdp_goods(year: Year, row: int) -> tuple[list[float], list[float]]:
    """Prices and supplies of the private and public goods in one row, in computeGdp's order.

    ``computeGdp`` adds, for n = 1..100, private good n and then public good n.
    """
    private = CATEGORIES.index("private-goods") * PER_CATEGORY
    public = CATEGORIES.index("public-goods") * PER_CATEGORY
    prices, supplies = [], []
    for n in range(PER_CATEGORY):
        for start in (private, public):
            prices.append(year.price[row, start + n])
            supplies.append(year.supply[row, start + n])
    return prices, supplies


@dataclasses.dataclass(frozen=True)
class Readings:
    """What one output file gives for the columns of Tables 9.1, 9.2, 9.4 and 9.5."""

    below: dict[float, int | None]
    """Year one: first iteration with every value below 10, 5 and 3 percent."""
    color_at_least: dict[float, int | None]
    color_exact: dict[float, int | None]
    year_1_rounds: int
    year_2_below_5: int | None
    year_2_color_at_least: int | None
    year_2_color_exact: int | None
    year_2_rounds: int
    growth: Growth
    year_1_line: int
    """Line of the row the year-1 prices and supplies are taken from."""
    year_2_line: int

    @property
    def ten_to_five(self) -> int | None:
        """Table 9.5: first iteration below 5 percent minus first below 10 percent."""
        if self.below[10.0] is None or self.below[5.0] is None:
            return None
        return self.below[5.0] - self.below[10.0]


def read_all(output: ProgramOutput) -> Readings:
    """Every reading the book's tables are compared on, from one output file with two years."""
    if len(output.years) != 2:
        raise ValueError(f"{output.path.name}: {len(output.years)} years, expected 2")
    one, two = output.years
    price_1, supply_1 = _gdp_goods(one, -1)
    price_2, supply_2 = _gdp_goods(two, -1)
    return Readings(
        below={t: first_all_below(one.threshold, one.iteration, t) for t in BOOK_THRESHOLDS},
        color_at_least={t: first_color_at_least(one.color, one.iteration, COLOR_OF_THRESHOLD[t])
                        for t in BOOK_THRESHOLDS},
        color_exact={t: first_color_exact(one.color, one.iteration, COLOR_OF_THRESHOLD[t])
                     for t in BOOK_THRESHOLDS},
        year_1_rounds=len(one.iteration),
        year_2_below_5=first_all_below(two.threshold, two.iteration, YEAR_2_THRESHOLD),
        year_2_color_at_least=first_color_at_least(two.color, two.iteration, ":green"),
        year_2_color_exact=first_color_exact(two.color, two.iteration, ":green"),
        year_2_rounds=len(two.iteration),
        growth=gdp_growth(price_1, supply_1, price_2, supply_2),
        year_1_line=int(one.lines[-1]),
        year_2_line=int(two.lines[-1]),
    )
