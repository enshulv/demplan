"""Recomputes every recorded price step of the program's output files under three rules.

For every row and commodity of an output file, the relative imbalance ``v`` is computed from
the row's own ``supply`` and ``demand`` columns, the step is computed from ``v`` by each rule
of :mod:`_price_rules`, and the result is compared with the row's ``new-deltas`` column. The
program's rule also needs the previous round's stored multiplier, which is the ``pdlist``
column of the previous row, 0.25 before the first row.

Four further columns are checked against what they should hold under the program's code: the
``pdlist`` is this row's ``min(v, 0.25)``, the price is the previous row's price moved by this
row's step, the surplus is supply minus demand, and the threshold report is ``100 v``.

The first row of year two is where the program's state crosses the year boundary; it is
checked twice, once with the multiplier and price carried over from the last row of year one
and once with both set back to their initial values.
"""
from __future__ import annotations

import dataclasses

import numpy as np

import _price_rules as rules
from _program_output import ProgramOutput, commodity_label

RULES = ("program", "book", "paper")


@dataclasses.dataclass
class Worst:
    """The largest error seen so far and where it was."""

    error: float = -1.0
    where: str = ""
    recorded: float = float("nan")
    computed: float = float("nan")
    cells: int = 0
    not_finite: int = 0
    """Cells whose error is NaN or infinite; they are counted, not folded into ``error``."""

    def update(self, errors: np.ndarray, recorded: np.ndarray, computed: np.ndarray,
               where: str) -> None:
        """Fold one row's errors in; ``where`` names the row, the commodity is appended."""
        self.cells += errors.size
        finite = np.isfinite(errors)
        self.not_finite += int(np.count_nonzero(~finite))
        errors = np.where(finite, errors, -1.0)
        at = int(np.argmax(errors))
        if errors[at] > self.error:
            self.error = float(errors[at])
            self.recorded = float(recorded[at])
            self.computed = float(computed[at])
            self.where = f"{where} {commodity_label(at)}"


@dataclasses.dataclass
class StepCheck:
    """All errors of all files, keyed by what was compared and the year."""

    worst: dict[tuple[str, int], Worst] = dataclasses.field(default_factory=dict)
    floor_rows: int = 0
    """Cells whose recorded step equals the floor of 0.001."""

    def at(self, what: str, year: int) -> Worst:
        """The accumulator for ``what`` in year ``year``, created empty on first use."""
        return self.worst.setdefault((what, year), Worst())

    def add(self, experiment: int, output: ProgramOutput) -> None:
        """Fold every row of both years of one output file in."""
        multiplier = np.full(output.years[0].pdlist.shape[1], rules.INITIAL_MULTIPLIER)
        price = np.full_like(multiplier, rules.INITIAL_PRICE)
        for year_number, year in enumerate(output.years, start=1):
            for row in range(len(year.iteration)):
                where = (f"exp {experiment} {output.path.name} line {year.lines[row]} "
                         f"year {year_number} round {year.iteration[row]}")
                if year_number == 2 and row == 0:
                    self._year_boundary(year, where, multiplier, price)
                self._row(year, row, year_number, where, multiplier, price)
                multiplier, price = year.pdlist[row], year.price[row]

    def _row(self, year, row, year_number, where, multiplier, price) -> None:
        """Compare one row with every rule and with the four derived columns."""
        supply, demand = year.supply[row], year.demand[row]
        v = rules.relative_imbalance(supply, demand)
        recorded = year.new_delta[row]
        self.floor_rows += int(np.count_nonzero(recorded == rules.FLOOR))
        computed = {"program": rules.step_program(v, multiplier), "book": rules.step_book(v),
                    "paper": rules.step_paper(v)}
        for name, step in computed.items():
            self.at(name, year_number).update(_relative(step, recorded), recorded, step, where)
        capped = np.minimum(v, rules.CAP)
        self.at("pdlist", year_number).update(np.abs(year.pdlist[row] - capped),
                                              year.pdlist[row], capped, where)
        moved = rules.next_price(price, year.surplus[row], recorded)
        self.at("price", year_number).update(_relative(moved, year.price[row]),
                                             year.price[row], moved, where)
        difference = supply - demand
        self.at("surplus", year_number).update(np.abs(year.surplus[row] - difference),
                                               year.surplus[row], difference, where)
        self.at("threshold", year_number).update(np.abs(year.threshold[row] - 100 * v),
                                                 year.threshold[row], 100 * v, where)

    def _year_boundary(self, year, where, carried_multiplier, carried_price) -> None:
        """Year two, round one, with the state carried over and with it set back."""
        v = rules.relative_imbalance(year.supply[0], year.demand[0])
        recorded = year.new_delta[0]
        reset_multiplier = np.full_like(carried_multiplier, rules.INITIAL_MULTIPLIER)
        for label, multiplier in (("carried", carried_multiplier), ("reset", reset_multiplier)):
            step = rules.step_program(v, multiplier)
            self.at(f"step, pdlist {label}", 2).update(_relative(step, recorded), recorded, step,
                                                       where)
        reset_price = np.full_like(carried_price, rules.INITIAL_PRICE)
        for label, price in (("carried", carried_price), ("reset", reset_price)):
            moved = rules.next_price(price, year.surplus[0], recorded)
            self.at(f"price, price {label}", 2).update(_relative(moved, year.price[0]),
                                                       year.price[0], moved, where)


def _relative(computed: np.ndarray, recorded: np.ndarray) -> np.ndarray:
    """``|computed - recorded| / |recorded|``."""
    return np.abs(computed - recorded) / np.abs(recorded)
