"""Compare the CSV files that `pequod-cljs`'s `csvgen.clj` writes, read with `_program_output`.

Each run is year one of an output file as `_program_output.read_year_one` returns it: one row
per planning round, per commodity the price, the step w applied to it (`new-deltas`), the capped
imbalance stored for the next round (`pdlist`), supply, demand, surplus and `threshold-report`
(100·|2·surplus| / (supply + demand), in percent), and per worker council its output and effort.
The step formulas come from `_price_rules`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import _price_rules as rules  # noqa: E402
from _program_output import QUANTITIES, Year, column_name  # noqa: E402

KINDS = {"price": "prices", "new_delta": "new-deltas", "pdlist": "pdlist", "supply": "supply",
         "demand": "demand", "surplus": "surplus", "threshold": "threshold-report"}
"""The label of each per-commodity quantity in the reports, in the order of the columns."""


@dataclass(frozen=True)
class GroupDiff:
    """The differences between two runs over every column of one kind."""

    kind: str
    cells: int
    #: cells whose two values are equal as numbers
    identical_cells: int
    max_abs: float
    #: (round, column name) of the largest absolute difference; None when every cell is equal
    max_abs_at: tuple[int, str] | None
    #: |a - b| / max(|a|, |b|), 0 when both are 0
    max_rel: float
    max_rel_at: tuple[int, str] | None


@dataclass(frozen=True)
class RunDiff:
    """Every numeric column kind compared, plus the rows whose colour or iteration differ."""

    rounds_compared: int
    groups: list[GroupDiff]
    #: (round, ours, theirs)
    color_mismatches: list[tuple[int, str, str]]
    #: (round, ours, theirs)
    iteration_mismatches: list[tuple[int, int, int]]


@dataclass(frozen=True)
class RoundSummary:
    iteration: int
    color: str
    #: the largest threshold-report value of the round, in percent
    worst_imbalance_pct: float
    min_step: float
    max_step: float


@dataclass(frozen=True)
class StepDiff:
    """One round of two runs: how many commodities got a different step, and by how much."""

    iteration: int
    differing: int
    max_abs_step_diff: float
    worst_imbalance_a: float
    worst_imbalance_b: float


def identical_lines(path_a: Path, path_b: Path, count: int) -> list[bool]:
    """Whether each of the first `count` lines (header included) is byte for byte the same in
    both files; a line one file does not have counts as different."""
    with open(path_a, "rb") as a, open(path_b, "rb") as b:
        return [(line_a := a.readline()) == b.readline() and line_a != b"" for _ in range(count)]


def diff_runs(ours: Year, theirs: Year, rounds: int) -> RunDiff:
    """Compare the first `rounds` rows of two runs column by column.

    Cells are grouped by kind (the seven per-commodity quantities, then the worker councils'
    output and effort when both runs carry them); for each kind the largest absolute and
    relative difference and where it occurs are kept, the first in row order on a tie. The
    colour and iteration columns are compared as values. Raises ValueError when the two runs
    do not have the same header layout or either has fewer rows.
    """
    if ours.per_category != theirs.per_category or ours.wc_ids != theirs.wc_ids:
        raise ValueError(f"the headers differ: {ours.per_category} and {theirs.per_category} commodities "
                         f"per category, {len(ours.wc_ids)} and {len(theirs.wc_ids)} worker councils")
    if rounds > len(ours.iteration) or rounds > len(theirs.iteration):
        raise ValueError(f"{rounds} rounds requested, runs have {len(ours.iteration)} and {len(theirs.iteration)}")

    groups = []
    for quantity in QUANTITIES:
        groups.append(_group(KINDS[quantity], getattr(ours, quantity)[:rounds], getattr(theirs, quantity)[:rounds],
                             lambda at: column_name(quantity, at, ours.per_category)))
    if ours.wc_ids:
        for kind, attribute in (("wc output", "wc_output"), ("wc effort", "wc_effort")):
            what = kind.split()[1]
            groups.append(_group(kind, getattr(ours, attribute)[:rounds], getattr(theirs, attribute)[:rounds],
                                 lambda at, what=what: f"wc_{ours.wc_ids[at]}_{what}"))
    color_mismatches = [(r + 1, a, b) for r, (a, b) in enumerate(zip(ours.color[:rounds], theirs.color[:rounds]))
                        if a != b]
    iteration_mismatches = [(r + 1, int(a), int(b))
                            for r, (a, b) in enumerate(zip(ours.iteration[:rounds], theirs.iteration[:rounds]))
                            if a != b]
    return RunDiff(rounds, groups, color_mismatches, iteration_mismatches)


def _group(kind: str, a: np.ndarray, b: np.ndarray, name_of) -> GroupDiff:
    """The differences between two ``(rounds, columns)`` blocks; ``name_of(column)`` names a column."""
    equal = a == b
    absolute = np.where(equal, 0.0, np.abs(a - b))
    scale = np.maximum(np.abs(a), np.abs(b))
    relative = np.where(equal, 0.0, absolute / np.where(equal, 1.0, scale))

    def where(values: np.ndarray) -> tuple[float, tuple[int, str] | None]:
        """The largest value and its (round, column name); ``None`` when all are 0."""
        if not values.size or values.max() == 0.0:
            return 0.0, None
        row, column = np.unravel_index(int(np.argmax(values)), values.shape)
        return float(values[row, column]), (int(row) + 1, name_of(int(column)))

    max_abs, max_abs_at = where(absolute)
    max_rel, max_rel_at = where(relative)
    return GroupDiff(kind, int(equal.size), int(equal.sum()), max_abs, max_abs_at, max_rel, max_rel_at)


RULES = ("program", "book", "paper")


def expected_steps(rule: str, imbalances: np.ndarray, previous_capped: np.ndarray) -> np.ndarray:
    """The step each rule of `_price_rules` gives for this round's imbalances v (fractions, not
    percent); the program's rule also takes the capped imbalance stored in the previous round."""
    if rule == "program":
        return rules.step_program(imbalances, previous_capped)
    if rule == "book":
        return rules.step_book(imbalances)
    if rule == "paper":
        return rules.step_paper(imbalances)
    raise ValueError(f"unknown rule {rule!r}")


def rule_errors(run: Year) -> dict[str, list[float]]:
    """For each rule, the largest relative error per round of the step it predicts against the
    recorded `new-deltas`.

    The imbalance v of a round is the recorded `threshold-report` / 100; the program rule's
    multiplier is the previous row's recorded `pdlist`, 0.25 before the first row.
    """
    errors: dict[str, list[float]] = {rule: [] for rule in RULES}
    previous_capped = np.full(run.pdlist.shape[1], rules.INITIAL_MULTIPLIER)
    for r in range(len(run.iteration)):
        imbalances = run.threshold[r] / 100
        for rule in RULES:
            predicted = expected_steps(rule, imbalances, previous_capped)
            errors[rule].append(float(np.max(_relative_error(predicted, run.new_delta[r]))))
        previous_capped = run.pdlist[r]
    return errors


def _relative_error(predicted: np.ndarray, recorded: np.ndarray) -> np.ndarray:
    """|predicted - recorded| / |recorded|; 0 where both are equal and infinite where only the
    recorded value is 0."""
    with np.errstate(divide="ignore", invalid="ignore"):
        error = np.abs(predicted - recorded) / np.abs(recorded)
    return np.where(predicted == recorded, 0.0, np.where(recorded == 0.0, np.inf, error))


def price_update_errors(run: Year) -> list[float]:
    """Per round, the largest relative error of the recorded price against p·(1 − w) for a
    surplus, p·(1 + w) for a shortage and p for balance, with p the previous row's price (700
    before the first row) and w the round's recorded step."""
    previous = np.full(run.price.shape[1], rules.INITIAL_PRICE)
    errors = []
    for r in range(len(run.iteration)):
        expected = rules.next_price(previous, run.surplus[r], run.new_delta[r])
        errors.append(float(np.max(_relative_error(expected, run.price[r]))))
        previous = run.price[r]
    return errors


def round_summary(run: Year) -> list[RoundSummary]:
    """Iteration, colour, worst imbalance and the range of steps of every row."""
    return [RoundSummary(int(run.iteration[r]), run.color[r], float(run.threshold[r].max()),
                         float(run.new_delta[r].min()), float(run.new_delta[r].max()))
            for r in range(len(run.iteration))]


def compare_steps(a: Year, b: Year) -> list[StepDiff]:
    """Round by round over the rows both runs have: the number of commodities whose recorded
    step differs, the largest absolute difference, and each run's worst imbalance."""
    result = []
    for r in range(min(len(a.iteration), len(b.iteration))):
        diffs = np.abs(a.new_delta[r] - b.new_delta[r])
        result.append(StepDiff(iteration=int(a.iteration[r]), differing=int(np.count_nonzero(diffs)),
                               max_abs_step_diff=float(diffs.max()),
                               worst_imbalance_a=float(a.threshold[r].max()),
                               worst_imbalance_b=float(b.threshold[r].max())))
    return result
