"""The book's chapter-9 tables as printed, read from book_tables.csv.

Hahnel, R. (2021). *Democratic Economic Planning*. Routledge. Tables 9.1 (p. 178), 9.2
(p. 179), 9.4 (p. 183), 9.5 (p. 184) and 9.6 (p. 185). Each cell is kept as the string
printed, including the ``%`` of the GDP columns.
"""
from __future__ import annotations

import csv
import dataclasses
from decimal import Decimal
from pathlib import Path

TABLES = Path(__file__).resolve().parent / "book_tables.csv"
COLUMNS = ("table", "experiment", "column", "printed", "page")


@dataclasses.dataclass(frozen=True)
class Cell:
    """One printed cell and the page it is on."""
    printed: str
    page: int

    @property
    def value(self) -> Decimal:
        """The printed number without its ``%``."""
        return Decimal(self.printed.rstrip("%"))


def load_tables(path: Path = TABLES) -> dict[tuple[str, str], dict[int, Cell]]:
    """``{(table, column): {experiment: Cell}}``; ``ValueError`` on a repeated or bad row."""
    tables: dict[tuple[str, str], dict[int, Cell]] = {}
    with open(path, encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream)
        if tuple(next(reader)) != COLUMNS:
            raise ValueError(f"{path.name}: header must be {','.join(COLUMNS)}")
        for number, (table, experiment, column, printed, page) in enumerate(reader, start=2):
            cells = tables.setdefault((table, column), {})
            key = int(experiment)
            if key in cells:
                raise ValueError(f"{path.name}:{number}: {table} {column} experiment {key} repeats")
            if not _is_number(printed.rstrip("%")):
                raise ValueError(f"{path.name}:{number}: {printed!r} is not a printed number")
            cells[key] = Cell(printed, int(page))
    return tables


def _is_number(text: str) -> bool:
    """Whether ``text`` is digits with at most one decimal point."""
    whole, _, fraction = text.partition(".")
    return whole.isdigit() and (fraction == "" or fraction.isdigit())
