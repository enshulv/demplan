"""
Checks the output files of msszczep/pequod-cljs against three price rules and the book's tables.

Uses only the program's own files: the output files dep1ex51.csv to dep1ex100.csv at commit
df6dc57, csvgen.clj at commit 71e44d3 (the program that wrote them), and
bin/dep_data_process.py at commit 7757bb4 (the author's script that reads them). demplan is
not used.

Part 1, the price rule. Every row of an output file records, per commodity, the supply and
demand at the round's price, the step the price was moved by (new-deltas), the stored
multiplier (pdlist) and the new price. The step is recomputed from the same row's supply and
demand under three rules and compared with the recorded one:

  program  max(0.001, min(v_{k-1}, 0.25) * (1.05 - 0.5^v_k)), v_{k-1} = previous row's pdlist
  book     min(v_k, 0.25) * (1.05 - 0.5^v_k)                     Hahnel (2021), p. 181
  paper    min(v_k, 0.25) * (1.05 - 0.5^min(v_k, 0.25))          Szczepanczyk (2023), p. 7

Part 2, the book's tables. From each output file: the first year-one round with every
imbalance below 10%, 5% and 3%, the first year-two round below 5%, and real GDP growth as note
15 of the book (p. 193) describes it. These are set against Hahnel (2021) Tables 9.1, 9.2,
9.4 and 9.5 as printed (book_tables.csv), and against the means the book's text gives. Book
experiment N is read from dep1ex(60+N).csv. As a control, every output file, including
dep1ex51.csv to dep1ex60.csv, which that numbering leaves out, is scored against every row of
the tables.

Usage:
  python research/upstream/check_outputs.py [--experiments 1-40] [--no-control]
                                            [--cache DIR] [--data-dir DIR]

Missing files are downloaded and every file is checked against manifest.tsv (see fetch.py).
"""
from __future__ import annotations

import argparse
import dataclasses
import statistics
import sys
import time
from decimal import Decimal

import numpy as np

import _book
import _experiments
import fetch
from _program_output import ProgramOutput, commodity_label, read_output
from _readings import Readings, read_all, rounded, truncated
from _step_check import RULES, StepCheck

CSVGEN = "pequod-cljs@71e44d3/csvgen.clj"
DEP_DATA_PROCESS = "pequod-cljs@7757bb4/dep_data_process.py"
CONTROL_OUTPUTS = range(51, 61)

CODE_LINES = {
    "csvgen.clj": ((106, 110), (164, 164), (646, 647), (717, 718), (724, 726), (787, 798),
                   (862, 865), (876, 882), (885, 886), (890, 890), (899, 900), (925, 925),
                   (1039, 1040)),
    "dep_data_process.py": ((41, 53), (55, 65), (107, 126)),
}
"""The source lines printed at the top of the output, so that each claim can be read off them."""

LINE_WIDTH = 150

TEXT_FIGURES = (
    ("p. 179", "mean first round < 5% (Table 9.1)", "11.85"),
    ("p. 179", "mean first round < 3% (Table 9.2)", "19.2"),
    ("p. 179", "difference of these two means", "7.35"),
    ("p. 183", "mean year-2 first round < 5% (Table 9.4)", "6.575"),
    ("p. 183", "mean real GDP growth, % (Table 9.4)", "2.446"),
    ("p. 185", "mean rounds from < 10% to < 5% (Table 9.5)", "3.77"),
)
"""Means the book's text states, Hahnel (2021), with the page each is on."""

COMPARED = (("9.1", "#I"), ("9.2", "#I"), ("9.5", "#I"), ("9.4", "#I"), ("9.4", "GDP"))


def output_values(r: Readings) -> dict[tuple[str, str], Decimal | int | None]:
    """The five compared cells as an output file gives them; GDP truncated to three decimals."""
    return {("9.1", "#I"): r.below[5.0], ("9.2", "#I"): r.below[3.0],
            ("9.5", "#I"): r.ten_to_five, ("9.4", "#I"): r.year_2_below_5,
            ("9.4", "GDP"): truncated(r.growth.mean)}


def equal(book_cell: _book.Cell, value) -> bool:
    """Whether a printed cell equals an output value, as numbers."""
    return value is not None and book_cell.value == Decimal(value)


def differing_cells(experiments, readings, tables) -> list[tuple]:
    """Every compared cell whose printed value differs from the output, as
    ``(experiment, table, column, printed, output value)``, by experiment and then in the order
    of :data:`COMPARED`. ``readings`` is keyed by output file number."""
    differing = []
    for n in experiments:
        values = output_values(readings[_experiments.output_number(n)])
        for key in COMPARED:
            cell = tables[key][n]
            if not equal(cell, values[key]):
                differing.append((n, key[0], key[1], cell.printed, values[key]))
    return differing


@dataclasses.dataclass(frozen=True)
class ColumnTotal:
    """One round-count column over a set of experiments, by the output and as printed."""

    output_sum: int
    """Sum of the output's values that exist."""
    output_mean: float | None
    """Mean of the output's values that exist; ``None`` when none does."""
    missing: int
    """Experiments whose output never gets below the threshold."""
    printed_sum: int
    printed_mean: float


def column_totals(experiments, readings, tables) -> dict[tuple[str, str], ColumnTotal]:
    """Sums and means of the four round-count columns, from the readings the cells are compared
    on (:func:`output_values`) and from the printed cells."""
    rows = [readings[_experiments.output_number(n)] for n in experiments]
    columns = {
        ("9.1", "#I"): [r.below[5.0] for r in rows],
        ("9.2", "#I"): [r.below[3.0] for r in rows],
        ("9.5", "#I"): [r.ten_to_five for r in rows],
        ("9.4", "#I"): [r.year_2_below_5 for r in rows],
    }
    totals = {}
    for key, values in columns.items():
        printed = [int(tables[key][n].value) for n in experiments]
        present = [v for v in values if v is not None]
        totals[key] = ColumnTotal(output_sum=sum(present),
                                  output_mean=statistics.fmean(present) if present else None,
                                  missing=len(values) - len(present),
                                  printed_sum=sum(printed), printed_mean=statistics.fmean(printed))
    return totals


def gdp_means(experiments, readings, tables) -> tuple[float, float]:
    """The mean real GDP growth of the output, not truncated, and the mean of the printed cells."""
    output = statistics.fmean(readings[_experiments.output_number(n)].growth.mean for n in experiments)
    printed = statistics.fmean(float(tables[("9.4", "GDP")][n].value) for n in experiments)
    return output, printed


def gdp_rounding_counts(experiments, readings, tables) -> tuple[int, int]:
    """How many printed GDP cells equal the output's growth truncated to three decimals, and how
    many equal it rounded half up."""
    truncated_equal = rounded_equal = 0
    for n in experiments:
        growth = readings[_experiments.output_number(n)].growth.mean
        cell = tables[("9.4", "GDP")][n]
        t, o = truncated(growth), rounded(growth)
        truncated_equal += cell.value == t
        rounded_equal += cell.value == o
    return truncated_equal, rounded_equal


def print_code(store: fetch.Store) -> None:
    """The source lines this script's readings rest on, from the pinned files."""
    for name, manifest_name in (("csvgen.clj", CSVGEN), ("dep_data_process.py", DEP_DATA_PROCESS)):
        entry = store.entry(manifest_name)
        lines = store.path(manifest_name).read_text(encoding="utf-8").splitlines()
        print(f"\n{entry.source}:")
        for first, last in CODE_LINES[name]:
            for number in range(first, last + 1):
                text = lines[number - 1].rstrip()
                if len(text) > LINE_WIDTH:
                    text = text[:LINE_WIDTH] + " ..."
                print(f"  {number:5d}  {text}")
            print("  " + "-" * 5)


def print_step_check(check: StepCheck, outputs: int, digits: int) -> None:
    """Part 1: the largest error of each rule and each derived column."""
    print("\n== Part 1: the price step recorded in the output files ==")
    print(f"Output files: {outputs}. The longest printed number has {digits} significant digits;")
    print("17 is the most a float64 needs to be written without loss. The recomputation runs in")
    print("float64, whose rounding is about 1e-16 relative per operation.")
    print("\nStep recomputed from the row's own supply and demand, relative error |w - w_csv| / w_csv:")
    header = f"{'rule':<34} {'year':>4} {'cells':>8} {'max error':>11}   {'recorded':>22} {'computed':>22}   where"
    print(header)
    for rule in RULES:
        for year in (1, 2):
            _print_worst(check, rule, year)
    print("\nYear two, round one, with the program's rule, the stored state carried over from the")
    print("last row of year one or set back to its initial value (multiplier 0.25, price 700):")
    print(header)
    for what in ("step, pdlist carried", "step, pdlist reset", "price, price carried",
                 "price, price reset"):
        _print_worst(check, what, 2)
    print("\nOther columns of the same rows (errors absolute, except price, which is relative):")
    print("  pdlist    = min(v, 0.25) of the same row")
    print("  price     = previous row's price * (1 - w) if surplus > 0, * (1 + w) if < 0, w from new-deltas")
    print("  surplus   = supply - demand")
    print("  threshold = 100 v")
    print(header)
    for what in ("pdlist", "price", "surplus", "threshold"):
        for year in (1, 2):
            _print_worst(check, what, year)
    print(f"\nCells whose recorded step equals the floor 0.001: {check.floor_rows}")
    not_finite = sum(w.not_finite for w in check.worst.values())
    print(f"Cells with a NaN or infinite error (not counted in the maxima): {not_finite}")


def _print_worst(check: StepCheck, what: str, year: int) -> None:
    """One line of a Part 1 table: the largest error, the two values and where they are."""
    w = check.at(what, year)
    if w.error == 0:
        print(f"{what:<34} {year:>4} {w.cells:>8} {w.error:>11.3e}   every cell equal")
        return
    print(f"{what:<34} {year:>4} {w.cells:>8} {w.error:>11.3e}   {w.recorded!r:>22} "
          f"{w.computed!r:>22}   {w.where}")


def print_mapping_note() -> None:
    """The heading of Part 2 and how each reading is taken."""
    print("\n== Part 2: the book's Tables 9.1, 9.2, 9.4 and 9.5 against the output files ==")
    print("Book experiment N is read from dep1ex(60+N).csv. The correspondence is established by")
    print("check_inputs.py (N = 1..18, input hashes) and check_rules.py (N = 1..40, the")
    print("worst imbalance of every round); the control at the end of this part scores every")
    print("output file against every row of the tables.")
    print("\nReadings: first year-one round with all 500 threshold-report values < 10%, < 5% and")
    print("< 3%; Table 9.5 is the < 5% round minus the < 10% round; first year-two round < 5%.")
    print("GDP: note 15, p. 193, as bin/dep_data_process.py lines 48-65 and 107-126 compute it:")
    print("sum of price * supply over the 100 private and 100 public goods, taken from the last")
    print("row of each year (the row before each exponent-sum line); the price columns of that")
    print("row are the prices the row's step moved to, the supply columns the supply at the")
    print("row's own price. Growth at year-1 prices and at year-2 prices, then their mean.")


def print_comparison(experiments, readings, tables) -> list[tuple]:
    """The 40-row table; returns the differing cells as (experiment, table, column, printed, output)."""
    print(f"\n{'exp':>3} {'output file':<14}| {'9.1 <5%':>9} | {'9.2 <3%':>9} | {'9.5':>7} | "
          f"{'9.4 #I':>8} | {'9.4 GDP printed':>15} {'output':>12} {'trunc':>6} {'round':>6} "
          f"| {'y1 rows':>7} {'y2 rows':>7}")
    print(f"{'':>18}| {'book out':>9} | {'book out':>9} | {'bk out':>7} | {'book out':>8} |")
    differing = differing_cells(experiments, readings, tables)
    marked = {(n, (table, column)) for n, table, column, _, _ in differing}
    for n in experiments:
        r = readings[_experiments.output_number(n)]
        values = output_values(r)
        marks = {key: "*" if (n, key) in marked else " " for key in COMPARED}
        gdp_cell = tables[("9.4", "GDP")][n]
        print(f"{n:>3} {f'dep1ex{_experiments.output_number(n)}.csv':<14}| "
              f"{tables[('9.1', '#I')][n].printed:>3} {_fmt(values[('9.1', '#I')]):>3}{marks[('9.1', '#I')]} | "
              f"{tables[('9.2', '#I')][n].printed:>3} {_fmt(values[('9.2', '#I')]):>3}{marks[('9.2', '#I')]} | "
              f"{tables[('9.5', '#I')][n].printed:>2} {_fmt(values[('9.5', '#I')]):>2}{marks[('9.5', '#I')]} | "
              f"{tables[('9.4', '#I')][n].printed:>3} {_fmt(values[('9.4', '#I')]):>2}{marks[('9.4', '#I')]} | "
              f"{gdp_cell.printed:>15} {r.growth.mean:>12.8f} {'yes' if gdp_cell.value == truncated(r.growth.mean) else 'no':>6} "
              f"{'yes' if gdp_cell.value == rounded(r.growth.mean) else 'no':>6} | "
              f"{r.year_1_rounds:>7} {r.year_2_rounds:>7}")
    print("  * the printed cell differs from the output; trunc/round: the printed GDP equals the")
    print("    output truncated / rounded half up to three decimals")
    return differing


def _fmt(value) -> str:
    """A round number, or ``-`` for ``None``."""
    return "-" if value is None else str(value)


def print_differences(differing, outputs: dict[int, ProgramOutput],
                      readings: dict[int, Readings]) -> None:
    """Each differing cell, with the worst imbalance of the rounds on either side of it."""
    print(f"\nCells where the printed table differs from the output: {len(differing)}")
    for n, table, column, printed, value in differing:
        number = _experiments.output_number(n)
        output = outputs[number]
        print(f"\n  Table {table} {column}, experiment {n}: printed {printed}, "
              f"dep1ex{number}.csv gives {value}")
        if column == "GDP":
            continue
        year = output.years[1] if table == "9.4" else output.years[0]
        if table == "9.5":
            rounds = [readings[number].below[10.0] or 1, readings[number].below[5.0] or 1]
        else:
            rounds = [int(printed), int(value) if value is not None else len(year.iteration)]
        low, high = max(1, min(rounds) - 1), min(len(year.iteration), max(rounds) + 1)
        print(f"    year {2 if table == '9.4' else 1}, per round: line, colour, worst threshold-report, "
              f"its commodity, values >= 10 / >= 5 / >= 3")
        for at in range(low - 1, high):
            values = year.threshold[at]
            worst = int(np.argmax(values))
            counts = [int(np.count_nonzero(values >= t)) for t in (10.0, 5.0, 3.0)]
            print(f"    round {year.iteration[at]:>2}  line {year.lines[at]:>3}  {year.color[at]:<8} "
                  f"{float(values[worst])!r:>22}  {commodity_label(worst):<22} {counts}")
        if high == len(year.iteration):
            print(f"    line {year.end_line}: exponent-sum (the year ends)")


def print_means(experiments, readings, tables) -> None:
    """Sums and means by the output and as printed, and the book text's figures."""
    totals = column_totals(experiments, readings, tables)
    print(f"\nSums and means over experiments {_experiments.span(experiments)}:")
    print(f"  {'table':<10} {'output sum':>10} {'mean':>9}   {'printed sum':>11} {'mean':>9}")
    means = {}
    for key, total in totals.items():
        means[key] = (total.output_mean, total.printed_mean)
        missing = f"  ({total.missing} missing)" if total.missing else ""
        print(f"  {key[0] + ' ' + key[1]:<10} {total.output_sum:>10} {_num(total.output_mean):>9}   "
              f"{total.printed_sum:>11} {total.printed_mean:>9.4f}{missing}")
    gdp_out, gdp_printed = gdp_means(experiments, readings, tables)
    print(f"  {'9.4 GDP':<10} {'':>10} {gdp_out:>9.4f}   {'':>11} {gdp_printed:>9.4f}")

    print("\nThe book's text (Hahnel 2021), against the means above:")
    derived = {
        "11.85": means[("9.1", "#I")], "19.2": means[("9.2", "#I")],
        "7.35": (_minus(means[("9.2", "#I")][0], means[("9.1", "#I")][0]),
                 means[("9.2", "#I")][1] - means[("9.1", "#I")][1]),
        "6.575": means[("9.4", "#I")], "2.446": (gdp_out, gdp_printed),
        "3.77": means[("9.5", "#I")],
    }
    print(f"  {'page':<7} {'figure':<45} {'text':>6} {'output':>9} {'printed':>9}")
    for page, what, text in TEXT_FIGURES:
        out, printed = derived[text]
        print(f"  {page:<7} {what:<45} {text:>6} {_num(out):>9} {printed:>9.4f}")
    if len(experiments) != _experiments.LAST:
        print("  (the text's figures are over all 40 experiments; these means are over a subset)")


def _minus(a, b):
    """``a - b``, or ``None`` when either is ``None``."""
    return None if a is None or b is None else a - b


def _num(value) -> str:
    """A mean to four decimals, or ``-`` for ``None``."""
    return "-" if value is None else f"{value:.4f}"


def print_gdp(experiments, readings, tables) -> None:
    """The two growth rates behind each GDP cell and how the printed value relates to them."""
    print("\nReal GDP growth per experiment (percent): rows used, growth at each year's prices,")
    print("their mean, and the printed cell")
    print(f"  {'exp':>3} {'y1 line':>7} {'y2 line':>7} {'at y1 prices':>14} {'at y2 prices':>14} "
          f"{'mean':>14} {'printed':>8} {'truncated':>9} {'rounded':>8}")
    for n in experiments:
        r = readings[_experiments.output_number(n)]
        cell = tables[("9.4", "GDP")][n]
        t, o = truncated(r.growth.mean), rounded(r.growth.mean)
        print(f"  {n:>3} {r.year_1_line:>7} {r.year_2_line:>7} {r.growth.year_1_prices:>14.8f} "
              f"{r.growth.year_2_prices:>14.8f} {r.growth.mean:>14.8f} {cell.printed:>8} "
              f"{str(t):>9} {str(o):>8}")
    truncated_equal, rounded_equal = gdp_rounding_counts(experiments, readings, tables)
    print(f"  printed GDP equals the output truncated to three decimals: {truncated_equal} of "
          f"{len(experiments)}; rounded half up: {rounded_equal} of {len(experiments)}")


def print_reading_agreement(experiments, readings) -> None:
    """Whether the threshold-report values and the colour column give the same rounds."""
    disagreements = []
    for number in sorted(readings):
        r = readings[number]
        for t in (10.0, 5.0, 3.0):
            trio = (r.below[t], r.color_at_least[t], r.color_exact[t])
            if len(set(trio)) > 1:
                disagreements.append(f"dep1ex{number}.csv year 1 < {t:g}%: values {trio[0]}, "
                                     f"colour at least {trio[1]}, colour exactly {trio[2]}")
        trio = (r.year_2_below_5, r.year_2_color_at_least, r.year_2_color_exact)
        if len(set(trio)) > 1:
            disagreements.append(f"dep1ex{number}.csv year 2 < 5%: values {trio[0]}, "
                                 f"colour at least {trio[1]}, colour exactly {trio[2]}")
    print(f"\nThe same rounds read three ways (threshold-report values; first :color at that level "
          f"or better; first :color exactly that level, as bin/dep_data_process.py reads it), "
          f"{len(readings)} files: {len(disagreements)} disagreements")
    for line in disagreements:
        print(f"  {line}")


def print_control(readings, tables) -> None:
    """Every output file scored against every row of the tables."""
    print("\nControl: each output file against every row N of the tables. Score = how many of the")
    print("five cells (9.1, 9.2, 9.5, 9.4 #I, 9.4 GDP truncated) are equal. The four round counts")
    print("take few distinct values, so the GDP cell is the one that tells rows apart.")
    print(f"  {'file':<14} {'N = M-60':>8} {'score':>5}   {'best other score':>16} {'rows with it':>12}   "
          f"{'rows scoring 5':<16} rows whose GDP cell is equal (their score)")
    for number in sorted(readings):
        values = output_values(readings[number])
        scores = {n: sum(equal(tables[key][n], values[key]) for key in COMPARED)
                  for n in range(_experiments.FIRST, _experiments.LAST + 1)}
        own = number - _experiments.OUTPUT_OFFSET
        own_text = f"{own:>8} {scores[own]:>5}" if own in scores else f"{'-':>8} {'-':>5}"
        best_other = max(s for n, s in scores.items() if n != own)
        how_many = sum(1 for n, s in scores.items() if n != own and s == best_other)
        full = [n for n, s in scores.items() if s == len(COMPARED)]
        gdp_rows = [f"{n}({scores[n]})" for n in scores
                    if equal(tables[("9.4", "GDP")][n], values[("9.4", "GDP")])]
        print(f"  {f'dep1ex{number}.csv':<14}{own_text}   {best_other:>16} {how_many:>12}   "
              f"{str(full or '-'):<16} {', '.join(gdp_rows) or '-'}")


def main(argv: list[str]) -> int:
    """Read the pinned files, print Part 1 and Part 2; exit status 0."""
    # Paths may hold non-ASCII characters; a Windows console or pipe defaults to a legacy code page.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="\n\n".join(__doc__.strip().split("\n\n")[1:]))
    _experiments.add_experiments_argument(parser)
    parser.add_argument("--no-control", action="store_true",
                        help="skip the control files dep1ex51.csv to dep1ex60.csv")
    fetch.add_location_arguments(parser)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    store = fetch.Store(fetch.roots_from(args))
    experiments = args.experiments
    tables = _book.load_tables()

    print("Upstream files (pinned in manifest.tsv, checked by sha256):")
    print_code(store)

    numbers = [_experiments.output_number(n) for n in experiments]
    if not args.no_control:
        numbers = list(CONTROL_OUTPUTS) + numbers
    outputs, readings, check, digits = {}, {}, StepCheck(), 0
    print(f"\nReading {len(numbers)} output files", flush=True)
    for number in numbers:
        output = read_output(store.path(_experiments.output_name(number)))
        outputs[number] = output
        readings[number] = read_all(output)
        digits = max(digits, output.max_significant_digits)
        if number not in CONTROL_OUTPUTS:
            check.add(number - _experiments.OUTPUT_OFFSET, output)

    print_step_check(check, len(experiments), digits)
    print_mapping_note()
    differing = print_comparison(experiments, readings, tables)
    print_differences(differing, outputs, readings)
    print_means(experiments, readings, tables)
    print_gdp(experiments, readings, tables)
    print_reading_agreement(experiments, readings)
    print_control(readings, tables)
    print("\nTable 9.6 is not compared: its runs (dep2ex61 to dep2ex100 in bin/dep_data_process.py)")
    print("are not among the files in manifest.tsv.")
    print(f"\nwall seconds: {time.perf_counter() - started:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
