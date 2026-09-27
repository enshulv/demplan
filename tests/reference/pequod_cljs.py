"""Read the per-round output that pequod-cljs wrote for one dep1ex run.

The program is ``msszczep/pequod-cljs``, ``src/clj/pequod_cljs/csvgen.clj`` at commit
``71e44d3``. Its repository carries no licence, so nothing copied or extracted from its output
may be committed: the files stay outside the repository, in the directory the environment
variable ``DEMPLAN_UPSTREAM_DIR`` names, and the tests that read them skip when it is unset or
a file is missing.

The program's inputs ``dep1ex61`` .. ``dep1ex65`` are the szcz.org archives ``dep1ex01`` ..
``dep1ex05`` under another namespace line, so ``dep1ex6N.csv`` is the run on ``dep1ex0N``.

Each file is a header row and then one row per round. The first column is the round number,
counted from 1, and each year ends at a row whose first column is ``exponent-sum``: the first
year, then a second year started from the first year's prices and ``pdlist`` on an economy
whose exponents the program perturbed in between. Per commodity class a row carries, for
commodities 1 to 100 of that class:

``:<class>-prices-<j>``
    the price after the round's update, the price the next round's proposals use;
``:new-deltas-<classes>-<j>``
    the step the update applied;
``:pdlist-<classes>-<j>``
    the multiplier the round hands the next one, its relative imbalance capped at 0.25;
``:supply-``, ``:demand-``, ``:surplus-<classes>-<j>``
    the balance measured at the round's price;
``:threshold-report-<classes>-<j>``
    the relative imbalance in percent.

and, per worker council ``k`` from 1, in the order of the archive's units, ``wc_<k>_output``,
the council's output in that round.
"""

from __future__ import annotations

import csv
import dataclasses
import os
from pathlib import Path

import numpy as np

UPSTREAM_DIR_VARIABLE = "DEMPLAN_UPSTREAM_DIR"

YEAR_END = "exponent-sum"
"""First column of the row that closes a year."""

_CLASSES = (
    # (Dep1exLayout section, price column prefix, prefix of every other column)
    ("priv", "private-good", "private-goods"),
    ("inter", "intermediate-good", "intermediate-goods"),
    ("nature", "nature", "nature"),
    ("labor", "labor", "labor"),
    ("pub", "public-good", "public-goods"),
)


@dataclasses.dataclass(frozen=True)
class ProgramRound:
    """One first-year round of the program, every vector in the layout's commodity order."""

    price_after: np.ndarray
    step: np.ndarray
    pdlist: np.ndarray
    supply: np.ndarray
    demand: np.ndarray
    surplus: np.ndarray
    threshold_report: np.ndarray


def upstream_csv(index: int) -> Path | None:
    """The program's output for ``dep1ex0<index>``, or ``None`` when it is not available."""
    directory = os.environ.get(UPSTREAM_DIR_VARIABLE)
    if not directory:
        return None
    path = Path(directory) / f"dep1ex6{index}.csv"
    return path if path.is_file() else None


def read_first_year(path: Path, layout) -> list[ProgramRound]:
    """Every first-year round of one output file, mapped onto ``layout``'s commodity ids."""
    csv.field_size_limit(2**31 - 1)
    with open(path, newline="", encoding="utf-8") as source:
        rows = csv.reader(source)
        header = next(rows)
        column = {name: at for at, name in enumerate(header)}
        rounds = []
        for row in rows:
            if row[0] == YEAR_END:
                break
            rounds.append(_program_round(row, column, layout))
    return rounds


@dataclasses.dataclass(frozen=True)
class ProgramYear:
    """One year of the program: every round, and each worker council's output in the last."""

    rounds: list[ProgramRound]
    last_unit_output: np.ndarray


def read_years(path: Path, layout) -> list[ProgramYear]:
    """Every year of one output file, in order, mapped onto ``layout``'s commodity ids."""
    csv.field_size_limit(2**31 - 1)
    with open(path, newline="", encoding="utf-8") as source:
        rows = csv.reader(source)
        header = next(rows)
        column = {name: at for at, name in enumerate(header)}
        n_units = sum(1 for name in header if name.startswith("wc_") and name.endswith("_output"))
        unit_output_columns = [column[f"wc_{k}_output"] for k in range(1, n_units + 1)]
        years, rounds, last_row = [], [], None
        for row in rows:
            if row[0] != YEAR_END:
                rounds.append(_program_round(row, column, layout))
                last_row = row
                continue
            last_unit_output = np.array([float(last_row[at]) for at in unit_output_columns])
            years.append(ProgramYear(rounds=rounds, last_unit_output=last_unit_output))
            rounds = []
    return years


def _program_round(row, column, layout) -> ProgramRound:
    def gather(which: str) -> np.ndarray:
        vector = np.empty(layout.n_commodities, dtype=np.float64)
        for section, price_prefix, prefix in _CLASSES:
            name = {
                "price_after": f":{price_prefix}-prices",
                "step": f":new-deltas-{prefix}",
                "pdlist": f":pdlist-{prefix}",
                "supply": f":supply-{prefix}",
                "demand": f":demand-{prefix}",
                "surplus": f":surplus-{prefix}",
                "threshold_report": f":threshold-report-{prefix}",
            }[which]
            span = layout.section(section)
            for offset in range(span.stop - span.start):
                vector[span.start + offset] = float(row[column[f"{name}-{offset + 1}"]])
        return vector

    return ProgramRound(**{field.name: gather(field.name) for field in dataclasses.fields(ProgramRound)})
