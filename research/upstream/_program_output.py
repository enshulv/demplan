"""Reads an output file ``dep1exMM.csv`` of msszczep/pequod-cljs into per-round arrays.

The layout is set by ``-main``, ``print-csv`` and ``get-csv-header`` in csvgen.clj at 71e44d3
(lines 974-1060). The header is ``:iteration``, ``:color``, then 35 blocks with one column per
commodity, then two columns per worker council. Each block is one quantity for one of the five
categories, in the order private goods, intermediate goods, nature, labor, public goods:

  prices            the prices the round's step moved to, which the next round's proposals
                    are made at (``iterate-plan`` stores the updated prices, line 904)
  new-deltas        the step of that update
  pdlist            this round's imbalance capped at 0.25, which the next round's step
                    multiplies by (line 899, stored at line 925)
  supply, demand    at the prices the round's proposals were made at
  surplus           supply minus demand
  threshold-report  100 * |2 surplus| / (demand + supply), in percent (lines 862-865)

The worker-council columns are ``wc_<id>_output`` and ``wc_<id>_effort``, ids in increasing
order: each council's output and effort in the proposal of the round (``print-csv``, lines
974-979).

The program's files have 100 commodities per category; the number is read from the header, so
that files written by the same layout with fewer commodities read the same way.

A row whose first field is ``exponent-sum`` closes a year. The program runs two years; the
iteration counter restarts at 1 in the second (``augmented-reset``, line 195).

By default only the commodity blocks of a row are read; the worker-council columns, 60,000 in
the program's files, are read when asked for.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import numpy as np

CATEGORIES = ("private-goods", "intermediate-goods", "nature", "labor", "public-goods")
PER_CATEGORY = 100
"""Commodities per category in the program's files (csvgen.clj, lines 112-116)."""
N_COMMODITIES = len(CATEGORIES) * PER_CATEGORY

PRICE_PREFIXES = (":private-good-prices", ":intermediate-good-prices", ":nature-prices",
                  ":labor-prices", ":public-good-prices")
QUANTITIES = ("price", "new_delta", "pdlist", "supply", "demand", "surplus", "threshold")
"""The field names of :class:`Year`, in the order the blocks appear in a row."""
_BLOCK_PREFIXES = {
    "price": PRICE_PREFIXES,
    "new_delta": tuple(f":new-deltas-{c}" for c in CATEGORIES),
    "pdlist": tuple(f":pdlist-{c}" for c in CATEGORIES),
    "supply": tuple(f":supply-{c}" for c in CATEGORIES),
    "demand": tuple(f":demand-{c}" for c in CATEGORIES),
    "surplus": tuple(f":surplus-{c}" for c in CATEGORIES),
    "threshold": tuple(f":threshold-report-{c}" for c in CATEGORIES),
}
LEADING = (":iteration", ":color")
YEAR_END = "exponent-sum"
FIELDS_READ = len(LEADING) + len(QUANTITIES) * N_COMMODITIES
"""Fields of a row up to the end of the commodity blocks, in the program's files."""

_WORKER_COUNCIL = re.compile(r"wc_(\d+)_(output|effort)")


def expected_header(per_category: int = PER_CATEGORY) -> list[str]:
    """The header names csvgen.clj writes before the worker-council columns."""
    names = list(LEADING)
    for quantity in QUANTITIES:
        for prefix in _BLOCK_PREFIXES[quantity]:
            names += [f"{prefix}-{n}" for n in range(1, per_category + 1)]
    return names


def commodity_label(index: int, per_category: int = PER_CATEGORY) -> str:
    """The name the header uses for commodity ``index`` (0-based), e.g. ``labor-32``."""
    category, number = divmod(index, per_category)
    return f"{CATEGORIES[category]}-{number + 1}"


def column_name(quantity: str, index: int, per_category: int = PER_CATEGORY) -> str:
    """The header name of commodity ``index`` (0-based) in the block of ``quantity``."""
    category, number = divmod(index, per_category)
    return f"{_BLOCK_PREFIXES[quantity][category]}-{number + 1}"


@dataclasses.dataclass(frozen=True)
class Year:
    """The rows of one year. Every array is indexed by row; the quantities are ``(rows, commodities)``."""

    lines: np.ndarray
    """1-based line number of each row in the file."""
    iteration: np.ndarray
    color: tuple[str, ...]
    price: np.ndarray
    new_delta: np.ndarray
    pdlist: np.ndarray
    supply: np.ndarray
    demand: np.ndarray
    surplus: np.ndarray
    threshold: np.ndarray
    end_line: int | None
    """Line number of the ``exponent-sum`` row that closes the year; ``None`` for a run stopped
    before the year ended."""
    per_category: int = PER_CATEGORY
    wc_ids: tuple[int, ...] = ()
    """Worker-council ids in column order; empty when the worker-council columns were not read."""
    wc_output: np.ndarray | None = None
    """``(rows, councils)``: each council's output in the round's proposal."""
    wc_effort: np.ndarray | None = None
    """``(rows, councils)``: each council's effort in the round's proposal."""

    @property
    def worst(self) -> np.ndarray:
        """Each row's largest ``threshold-report`` value, in percent."""
        return self.threshold.max(axis=1)


@dataclasses.dataclass(frozen=True)
class ProgramOutput:
    """One output file: its years, in file order."""
    path: Path
    years: tuple[Year, ...]
    max_significant_digits: int
    """The most significant digits any numeric field read was printed with."""


@dataclasses.dataclass(frozen=True)
class _Layout:
    """What the header says about the rows below it."""

    per_category: int
    wc_ids: tuple[int, ...]
    header_fields: int

    @property
    def block_fields(self) -> int:
        """Fields up to the end of the commodity blocks."""
        return len(LEADING) + len(QUANTITIES) * len(CATEGORIES) * self.per_category


def read_output(path: Path, *, worker_councils: bool = False) -> ProgramOutput:
    """Parse one whole output file.

    With ``worker_councils`` every row is read to its end and each :class:`Year` carries the
    worker-council columns.

    Raises ``ValueError`` naming the file and line when the header is not the layout csvgen.clj
    writes, a field does not parse as a number, a row is shorter than the header, a year's
    iteration column is not 1, 2, 3, ..., a colour is not a keyword, or rows follow the last
    ``exponent-sum``.
    """
    years, rows, most_digits = [], [], 0
    with open(path, encoding="utf-8", newline="") as stream:
        layout = _read_header(path, stream.readline(), worker_councils)
        for number, line in enumerate(stream, start=2):
            fields = _fields(line, layout, worker_councils)
            if fields[0] == YEAR_END:
                years.append(_year(path, rows, number, layout))
                rows = []
                continue
            row, digits = _row(path, number, fields, layout, worker_councils)
            most_digits = max(most_digits, digits)
            rows.append(row)
    if rows:
        raise ValueError(f"{path.name}: line {rows[0][0]} and after follow the last {YEAR_END} row")
    return ProgramOutput(path, tuple(years), most_digits)


def read_year_one(path: Path, *, max_rows: int | None = None, worker_councils: bool = False) -> Year:
    """The rows before the first ``exponent-sum`` row, or before the end of the file.

    Reads the file of a run that was stopped early as well as a complete one: a last line
    without its line break was cut off while it was written and is left out. ``max_rows``
    stops after that many rows. Raises ``ValueError`` as :func:`read_output` does, and when
    there is no row to read.
    """
    rows = []
    end_line = None
    with open(path, encoding="utf-8", newline="") as stream:
        layout = _read_header(path, stream.readline(), worker_councils)
        for number, line in enumerate(stream, start=2):
            if not line.endswith("\n"):
                break
            fields = _fields(line, layout, worker_councils)
            if fields[0] == YEAR_END:
                end_line = number
                break
            rows.append(_row(path, number, fields, layout, worker_councils)[0])
            if max_rows is not None and len(rows) == max_rows:
                break
    return _year(path, rows, end_line, layout)


def _read_header(path: Path, line: str, worker_councils: bool) -> _Layout:
    """The layout the header line describes; ``ValueError`` when it is not csvgen.clj's."""
    names = line.rstrip("\r\n").split(",")
    per_category = sum(1 for name in names if name.startswith(f"{PRICE_PREFIXES[0]}-"))
    blocks = expected_header(per_category)
    if per_category == 0 or names[:len(blocks)] != blocks:
        raise ValueError(f"{path.name}: header differs from the layout of csvgen.clj")
    wc_ids: tuple[int, ...] = ()
    if worker_councils:
        wc_ids = _worker_council_ids(path, names[len(blocks):])
    return _Layout(per_category, wc_ids, len(names))


def _worker_council_ids(path: Path, names: list[str]) -> tuple[int, ...]:
    """The ids of ``wc_<id>_output, wc_<id>_effort, ...``; ``ValueError`` for any other names."""
    if len(names) % 2:
        raise ValueError(f"{path.name}: header has an odd number of worker-council columns")
    ids = []
    for output, effort in zip(names[0::2], names[1::2]):
        first, second = _WORKER_COUNCIL.fullmatch(output), _WORKER_COUNCIL.fullmatch(effort)
        if (not first or not second or first.group(2) != "output" or second.group(2) != "effort"
                or first.group(1) != second.group(1)):
            raise ValueError(f"{path.name}: header has {output!r}, {effort!r} where a worker "
                             "council's output and effort columns should be")
        ids.append(int(first.group(1)))
    return tuple(ids)


def _fields(line: str, layout: _Layout, worker_councils: bool) -> list[str]:
    """The fields of one line that are read: all of them, or up to the end of the blocks."""
    text = line.rstrip("\r\n")
    if worker_councils:
        return text.split(",")
    return text.split(",", layout.block_fields)[:layout.block_fields]


def _row(path: Path, line: int, fields: list[str], layout: _Layout, worker_councils: bool) -> tuple[tuple, int]:
    """One data row as ``(line, iteration, colour, values)`` and its most significant digits."""
    wanted = layout.header_fields if worker_councils else layout.block_fields
    if len(fields) != wanted:
        raise ValueError(f"{path.name}: line {line} has {len(fields)} fields, expected {wanted}")
    numbers = fields[len(LEADING):]
    try:
        values = np.array([float(field) for field in numbers], dtype=np.float64)
    except ValueError as error:
        raise ValueError(f"{path.name}: line {line}: {error}") from None
    blocks = layout.block_fields - len(LEADING)
    digits = max(_significant_digits(field) for field in numbers[:blocks])
    return (line, fields[0], fields[1], values), digits


def _significant_digits(field: str) -> int:
    """Digits of the mantissa of a printed number, without leading or trailing zeros."""
    mantissa = field.upper().split("E")[0].lstrip("-")
    return max(1, len(mantissa.replace(".", "").strip("0")))


def _year(path: Path, rows: list, end_line: int | None, layout: _Layout) -> Year:
    """The rows between two ``exponent-sum`` lines as a :class:`Year`."""
    if not rows:
        raise ValueError(f"{path.name}: line {end_line}: a year with no rows")
    iterations = []
    for line, iteration, color, _ in rows:
        if not iteration.isdigit():
            raise ValueError(f"{path.name}: line {line}: iteration {iteration!r} is not a count")
        if not color.startswith(":"):
            raise ValueError(f"{path.name}: line {line}: colour {color!r} is not a keyword")
        iterations.append(int(iteration))
    if iterations != list(range(1, len(rows) + 1)):
        raise ValueError(f"{path.name}: lines {rows[0][0]}-{rows[-1][0]}: iteration column is "
                         f"{iterations}, expected 1..{len(rows)}")
    table = np.stack([values for *_, values in rows])
    width = len(CATEGORIES) * layout.per_category
    blocks = {quantity: table[:, at * width:(at + 1) * width] for at, quantity in enumerate(QUANTITIES)}
    councils = {}
    if layout.wc_ids:
        pairs = table[:, len(QUANTITIES) * width:]
        councils = {"wc_ids": layout.wc_ids, "wc_output": pairs[:, 0::2], "wc_effort": pairs[:, 1::2]}
    return Year(lines=np.array([r[0] for r in rows]), iteration=np.array(iterations),
                color=tuple(r[2] for r in rows), end_line=end_line,
                per_category=layout.per_category, **blocks, **councils)
