"""
Checks the effort pequod-cljs records for every worker council against the council's optimum.

Every row of an output file dep1exMM.csv of msszczep/pequod-cljs (commit df6dc57) records, per
worker council, the output and the effort of the council's proposal in that round
(wc_<id>_output, wc_<id>_effort). The program computes both with one closed form per number of
inputs, solution-1 to solution-8 of csvgen.clj at 71e44d3. This script takes one round, the
parameters of every council from the public input archive of the same economy, and the prices
the round's proposals were made at, and finds each council's optimum with a numerical
maximiser that uses no code of the program (_council_optimum.py). It prints, by number of
inputs, how far the recorded output and effort are from the optimum.

Which prices: iterate-plan (csvgen.clj lines 884-889) makes the round's proposals at the
prices held before the round's update, which are the price columns of the previous row, or 700
for the first round (lines 106-110). The script prints those lines. As a control that should
not match, the same comparison is made with the price columns of the round's own row, the
prices after the update.

Two further controls come with every council: the effort condition lam*c*z = s*k*e^k checked on
the recorded output and effort alone, and the effort the closed form gives when the sign of
its b_i*log(k) and b_i*log(s) terms is flipped, the pattern of solution-8.

The script also lists every line of csvgen.clj that mentions effort, and the lines where supply
is summed from the councils' output, so that whether the recorded effort reaches any other
quantity can be read off the program.

Book experiment N is dep1exNN.clj.gz from www.szcz.org and dep1ex(60+N).csv in the repository
(check_inputs.py, check_rules.py). Year one only: the program changes the councils' exponents
at random before year two (augmented-reset, lines 194-200).

Usage:
  python research/upstream/check_effort.py [--experiments 1] [--round last]
                                           [--cache DIR] [--data-dir DIR]

Missing files are downloaded and every file is checked against manifest.tsv (see fetch.py).
One experiment reads a 56 MB archive and a 36 MB output file and solves about 60,000 council
problems.
"""
from __future__ import annotations

import argparse
import dataclasses
import re
import sys
import time

import numpy as np

import _dep1ex_councils as councils_of
import _experiments
import _price_rules as rules
import fetch
from _council_optimum import (CouncilProblem, effort_condition_residual, maximise,
                              predicted_effort_ratio)
from _program_output import Year, read_year_one

CSVGEN = "pequod-cljs@71e44d3/csvgen.clj"

MATCH_TOLERANCE = 1e-8
"""Relative difference up to which a recorded value counts as equal to the optimum in the
``match`` column; the differences themselves are always printed."""

CODE_LINES = ((106, 110), (884, 889), (660, 680), (844, 852), (974, 979))
"""Source lines printed before the comparison: the starting prices, the prices the proposals
are made at, supply summed from the councils' output, and the columns print-csv writes."""

LINE_WIDTH = 150
SAMPLE_COUNCILS = 3
"""Councils per number of inputs whose values are printed one by one."""


@dataclasses.dataclass(frozen=True)
class RoundComparison:
    """Every council of one round: its recorded values, its optimum, and the controls."""

    n_inputs: np.ndarray
    output_recorded: np.ndarray
    effort_recorded: np.ndarray
    output_optimum: np.ndarray
    effort_optimum: np.ndarray
    effort_condition: np.ndarray
    """``log(lam c z) - log(s k e^k)`` at the recorded output and effort."""
    flipped_ratio: np.ndarray
    """Effort with the solution-8 signs divided by the optimal effort, from the algebra."""


@dataclasses.dataclass(frozen=True)
class GroupSummary:
    """The councils of one round that have the same number of inputs."""

    n_inputs: int
    count: int
    all_match: int
    """Councils whose recorded output and effort are both within :data:`MATCH_TOLERANCE`."""
    output_max: float
    """Largest ``|output_recorded / output_optimum - 1|``."""
    effort_min: float
    """Smallest ``effort_recorded / effort_optimum - 1``, signed."""
    effort_median: float
    effort_max: float
    effort_condition_max: float
    """Largest ``|effort condition|`` at the recorded values."""
    predicted_gap_max: float
    """Largest ``|effort_recorded / effort_optimum - flipped_ratio|``."""


def proposal_prices(year: Year, row: int) -> np.ndarray:
    """The prices the proposals of row ``row`` (0-based) were made at: the previous row's price
    columns, or the starting price of 700 for the first row."""
    if row == 0:
        return np.full(year.price.shape[1], rules.INITIAL_PRICE)
    return year.price[row - 1]


def council_problem(council: dict, prices: np.ndarray, per_category: int = 100) -> CouncilProblem:
    """The problem of one council at ``prices``, a row of an output file's price columns.

    Commodity ``id`` of a category is column ``id - 1`` of that category's block.
    """
    def price(category: str, commodity: int) -> float:
        """The price column of ``commodity`` in ``category``."""
        return float(prices[councils_of.PRICE_CATEGORIES.index(category) * per_category + commodity - 1])

    b, p = [], []
    for category in councils_of.INPUT_CATEGORIES:
        for commodity, exponent in council["inputs"][category]:
            b.append(exponent)
            p.append(price(category, commodity))
    lam = price(councils_of.PRODUCT_CATEGORY[council["industry"]], council["product"])
    return CouncilProblem(a=council["a"], s=council["s"], c=council["c"], k=council["k"], lam=lam,
                          b=np.array(b), p=np.array(p))


def compare_round(councils: list[dict], year: Year, row: int, prices: np.ndarray) -> RoundComparison:
    """Every council's recorded output and effort in row ``row`` against its optimum at ``prices``.

    Council i of the archive is column ``wc_<i+1>``: csvgen.clj numbers the councils in archive
    order (``add-ids``, lines 166-172) and writes the columns sorted by id. Raises
    ``ValueError`` when the columns are not ids 1 to the number of councils.
    """
    expected_ids = tuple(range(1, len(councils) + 1))
    if year.wc_ids != expected_ids:
        raise ValueError(f"the output file has worker council columns for ids {year.wc_ids[:3]}... "
                         f"({len(year.wc_ids)} councils); the archive has {len(councils)}")
    n_inputs, optimum_output, optimum_effort, condition, flipped = [], [], [], [], []
    for at, council in enumerate(councils):
        problem = council_problem(council, prices, year.per_category)
        z, e, _ = maximise(problem)
        n_inputs.append(len(problem.b))
        optimum_output.append(z)
        optimum_effort.append(e)
        condition.append(effort_condition_residual(problem, float(year.wc_output[row, at]),
                                                   float(year.wc_effort[row, at])))
        flipped.append(predicted_effort_ratio(problem))
    return RoundComparison(n_inputs=np.array(n_inputs), output_recorded=year.wc_output[row].copy(),
                           effort_recorded=year.wc_effort[row].copy(),
                           output_optimum=np.array(optimum_output), effort_optimum=np.array(optimum_effort),
                           effort_condition=np.array(condition), flipped_ratio=np.array(flipped))


def summarise(result: RoundComparison) -> list[GroupSummary]:
    """One :class:`GroupSummary` per number of inputs, in increasing order."""
    output_gap = result.output_recorded / result.output_optimum - 1.0
    effort_ratio = result.effort_recorded / result.effort_optimum
    groups = []
    for n in sorted(set(result.n_inputs.tolist())):
        at = result.n_inputs == n
        output_off = np.abs(output_gap[at])
        effort_off = effort_ratio[at] - 1.0
        match = (output_off <= MATCH_TOLERANCE) & (np.abs(effort_off) <= MATCH_TOLERANCE)
        groups.append(GroupSummary(
            n_inputs=int(n), count=int(at.sum()), all_match=int(match.sum()),
            output_max=float(output_off.max()), effort_min=float(effort_off.min()),
            effort_median=float(np.median(effort_off)), effort_max=float(effort_off.max()),
            effort_condition_max=float(np.abs(result.effort_condition[at]).max()),
            predicted_gap_max=float(np.abs(effort_ratio[at] - result.flipped_ratio[at]).max())))
    return groups


def print_groups(title: str, groups: list[GroupSummary]) -> None:
    """One line per number of inputs."""
    print(f"\n{title}")
    print(f"  {'N':>2} {'councils':>8} {'match':>6}  {'max |z_rec/z_opt - 1|':>22}  "
          f"{'e_rec/e_opt - 1: min':>21} {'median':>10} {'max':>10}  "
          f"{'max |effort cond.|':>18}  {'max |e_rec/e_opt - flipped|':>27}")
    for g in groups:
        print(f"  {g.n_inputs:>2} {g.count:>8} {g.all_match:>6}  {g.output_max:>22.3e}  "
              f"{g.effort_min:>21.3e} {g.effort_median:>10.3e} {g.effort_max:>10.3e}  "
              f"{g.effort_condition_max:>18.3e}  {g.predicted_gap_max:>27.3e}")


def print_samples(result: RoundComparison) -> None:
    """The recorded and optimal values of the first few councils of each number of inputs."""
    print(f"\nThe first {SAMPLE_COUNCILS} councils of each number of inputs, recorded next to optimum:")
    print(f"  {'column':<14} {'N':>2} {'output recorded':>22} {'output optimum':>22} "
          f"{'effort recorded':>22} {'effort optimum':>22}")
    for n in sorted(set(result.n_inputs.tolist())):
        for at in np.flatnonzero(result.n_inputs == n)[:SAMPLE_COUNCILS]:
            values = (result.output_recorded[at], result.output_optimum[at],
                      result.effort_recorded[at], result.effort_optimum[at])
            print(f"  {f'wc_{at + 1}':<14} {n:>2} " + " ".join(f"{float(v)!r:>22}" for v in values))


def enclosing_form(lines: list[str], number: int) -> str:
    """The name of the top-level ``(defn ...)`` that line ``number`` (1-based) lies in."""
    for at in range(number - 1, -1, -1):
        match = re.match(r"\(defn-? (\S+)", lines[at])
        if match:
            return match.group(1)
    return "-"


def print_code(store: fetch.Store) -> list[str]:
    """The source lines the reading rests on, and every line that mentions effort."""
    entry = store.entry(CSVGEN)
    lines = store.path(CSVGEN).read_text(encoding="utf-8").splitlines()
    print(f"\n{entry.source}:")
    for first, last in CODE_LINES:
        for number in range(first, last + 1):
            print(f"  {number:5d}  {_clip(lines[number - 1])}")
        print("  " + "-" * 5)
    mentions = [n for n, line in enumerate(lines, start=1) if "effort" in line]
    print(f"\nEvery line of csvgen.clj that contains 'effort' ({len(mentions)} lines), with the "
          "function it is in:")
    for number in mentions:
        print(f"  {number:5d}  {enclosing_form(lines, number):<16} {_clip(lines[number - 1].strip(), 110)}")
    outside = sorted({enclosing_form(lines, n) for n in mentions} - {f"solution-{i}" for i in range(1, 9)})
    print(f"  functions other than solution-1 .. solution-8 among them: {', '.join(outside) or 'none'}")
    start = next(n for n, line in enumerate(lines, start=1) if line.startswith("(defn solution-8 "))
    bindings = [(n, lines[n - 1].split()[0]) for n in range(start, start + 30)
                if re.match(r"\s+(output|x\d|effort) \(", lines[n - 1])]
    print("  let bindings of solution-8 in order (a binding sees only those above it): "
          + ", ".join(f"{name} line {n}" for n, name in bindings))
    return lines


def _clip(text: str, width: int = LINE_WIDTH) -> str:
    """``text`` cut to ``width`` characters, marked when cut."""
    return text if len(text) <= width else text[:width] + " ..."


def parse_round(text: str) -> str | int:
    """``last`` or a round number from 1."""
    if text == "last":
        return text
    number = int(text)
    if number < 1:
        raise argparse.ArgumentTypeError("rounds are numbered from 1")
    return number


def main(argv: list[str]) -> int:
    """Compare the chosen round of each selected experiment; exit status 0."""
    # Paths may hold non-ASCII characters; a Windows console or pipe defaults to a legacy code page.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="\n\n".join(__doc__.strip().split("\n\n")[1:]))
    _experiments.add_experiments_argument(parser, default="1")
    parser.add_argument("--round", type=parse_round, default="last",
                        help="round of year one to check, from 1, or 'last' (default last)")
    fetch.add_location_arguments(parser)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    store = fetch.Store(fetch.roots_from(args))
    print("Upstream files (pinned in manifest.tsv, checked by sha256):")
    print_code(store)

    everything: dict[int, list[GroupSummary]] = {}
    for n in args.experiments:
        archive = store.path(_experiments.archive_name(n))
        number = _experiments.output_number(n)
        output_path = store.path(_experiments.output_name(number))
        councils = [councils_of.council_from_dep1ex(wc) for wc in councils_of.read_worker_councils(archive)]
        year = read_year_one(output_path, worker_councils=True)
        row = len(year.iteration) - 1 if args.round == "last" else args.round - 1
        if row >= len(year.iteration):
            raise SystemExit(f"dep1ex{number}.csv has {len(year.iteration)} rounds in year one")
        print(f"\n== Experiment {n}: {archive.name}, {len(councils)} worker councils; "
              f"dep1ex{number}.csv, year one, round {year.iteration[row]} of {len(year.iteration)} "
              f"(line {year.lines[row]}) ==")
        source = "700 everywhere (the starting prices)" if row == 0 else \
            f"the price columns of round {year.iteration[row - 1]} (line {year.lines[row - 1]})"
        print(f"Proposals of this round made at {source}.")
        result = compare_round(councils, year, row, proposal_prices(year, row))
        everything[n] = summarise(result)
        print_groups("Recorded against the optimum at the prices the proposals were made at "
                     f"(match: output and effort within {MATCH_TOLERANCE:g} relative):", everything[n])
        print_samples(result)
        control = compare_round(councils, year, row, year.price[row])
        print_groups(f"Control: the same councils against the optimum at the price columns of round "
                     f"{year.iteration[row]} itself (the prices after its update), which the "
                     "proposals were not made at:", summarise(control))

    if len(args.experiments) > 1:
        print(f"\nSummary over experiments {_experiments.span(args.experiments)}, by number of inputs:")
        print(f"  {'N':>2} {'councils':>9} {'match':>9} {'max |z_rec/z_opt - 1|':>22} "
              f"{'e_rec/e_opt - 1: min':>21} {'max':>10}")
        by_n: dict[int, list[GroupSummary]] = {}
        for groups in everything.values():
            for g in groups:
                by_n.setdefault(g.n_inputs, []).append(g)
        for n_inputs, groups in sorted(by_n.items()):
            print(f"  {n_inputs:>2} {sum(g.count for g in groups):>9} {sum(g.all_match for g in groups):>9} "
                  f"{max(g.output_max for g in groups):>22.3e} {min(g.effort_min for g in groups):>21.3e} "
                  f"{max(g.effort_max for g in groups):>10.3e}")
    print(f"\nwall seconds: {time.perf_counter() - started:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
