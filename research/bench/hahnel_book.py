"""
Runs the chapter-9 experiments of Hahnel (2021) with demplan and prints them next to the book.

Hahnel (2021), *Democratic Economic Planning*, Routledge, Tables 9.1, 9.2, 9.4, 9.5, 9.6,
pp. 178-185. Per experiment:

  cold start          one run from 700 to the 3% threshold, keeping every round's plan; the
                      first round whose every relative imbalance is below 10%, 5% and 3%.
                      Table 9.1 is the 5% round, Table 9.2 the 3% round, and Table 9.5 the
                      rounds from all below 10% to all below 5%.
  warm start          (Table 9.4) per seed, two years through demplan.run_periods: year one
                      to 3%, the exponents perturbed, year two to 3% from year one's final
                      price and multiplier. Reported: year two's first round below 5% (the
                      book's #I), year two's rounds to 3%, and real GDP growth between the
                      two years.
  increasing returns  (Table 9.6) the same two-year run on an economy where a fifth of the
                      producing units get 0.1 added to every input exponent.

Experiment n is taken to be dep1ex{n:02d}. That is verified byte for byte for n = 1..5
against the program's repository, where the same economies are dep1ex61..65 under another
namespace line; for the other 35 it is assumed. The program behind the book's tables
(msszczep/pequod-cljs, csvgen.clj at 71e44d3) reached 3% on experiments 1-5 after 19, 20,
19, 19 and 19 rounds; Table 9.2 prints 19, 19, 20, 19, 19, experiments 2 and 3 transposed in
print. The random draws behind the book's warm-start and Table 9.6 runs are not recoverable,
so those two are compared as distributions over seeds, not experiment by experiment.

Usage:
  python research/bench/hahnel_book.py [--experiments 1-40] [--seeds 10] [--jobs 1]
                                       [--out hahnel_book.json]

The archives are read from DEMPLAN_DATA_DIR, or research/data when it is unset.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

import demplan
from demplan import run, run_periods, split_seed
from demplan.prefabs.hahnel import (
    HahnelBook2021,
    WarmStart,
    increasing_returns,
    perturb_exponents,
    real_gdp_growth,
    relative_imbalance,
)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "upstream"))
from _book import load_tables  # noqa: E402  (needs the sys.path entry above)

DATA = Path(os.environ.get("DEMPLAN_DATA_DIR", HERE.parent / "data"))

ENDOWMENT = 1000.0
PERCENT = 100.0
COLD_THRESHOLDS = (10.0, 5.0, 3.0)
YEAR_THRESHOLD = 3.0
WARM_REPORT_THRESHOLD = 5.0

INCREASING_RETURNS_SEED_WORD = 4
"""Which word of split_seed(s, 5) seeds the choice of units for Table 9.6.

A two-period run_periods call uses words 0-3 of split_seed(s, 4); word 4 is the first one it
never hands out, and split_seed is a prefix chain, so the unit choice draws from a seed of its
own.
"""

BOOK_TABLES = load_tables()
"""Hahnel (2021), Democratic Economic Planning, Routledge, Tables 9.1, 9.2, 9.4, 9.5, 9.6,
pp. 178-185, as printed, from research/upstream/book_tables.csv."""

BOOK_COLUMNS = {
    "table_9_1_first_below_5": ("9.1", "#I"),
    "table_9_2_first_below_3": ("9.2", "#I"),
    "table_9_4_rounds": ("9.4", "#I"),
    "table_9_4_gdp": ("9.4", "GDP"),
    "table_9_5_rounds": ("9.5", "#I"),
    "table_9_6_rounds": ("9.6", "#I"),
    "table_9_6_gdp": ("9.6", "GDP"),
}
"""book_row key: (table, column) of book_tables.csv. Round counts are ints, GDP growth in %
is a float."""


def book_row(n: int) -> dict:
    """The book's numbers for experiment ``n``."""
    row = {}
    for key, (table, column) in BOOK_COLUMNS.items():
        value = BOOK_TABLES[table, column][n].value
        row[key] = float(value) if column == "GDP" else int(value)
    return row


def worst_imbalance_pct(economy, trajectory) -> list[float]:
    """Every round's worst relative imbalance, in percent, rebuilt from its plan."""
    return [float(np.max(relative_imbalance(economy, plan))) * PERCENT for plan in trajectory]


def first_round_below(worst: list[float], threshold: float) -> int | None:
    """The first round, counted from 1, whose worst imbalance is below ``threshold`` percent."""
    for number, value in enumerate(worst, start=1):
        if value < threshold:
            return number
    return None


def threshold_readings(worst: list[float]) -> dict:
    """What one cold run's worst imbalance per round is read as in Tables 9.1, 9.2 and 9.5.

    ``first_below_10``, ``first_below_5`` and ``first_below_3`` are the first rounds below
    10%, 5% and 3%. ``rounds_10_to_5`` is the Table 9.5 count, the rounds from the first one
    below 10% to the first one below 5%; it is ``None`` when either of those two is ``None``.
    """
    below = {threshold: first_round_below(worst, threshold) for threshold in COLD_THRESHOLDS}
    ten_to_five = None
    if below[10.0] is not None and below[5.0] is not None:
        ten_to_five = below[5.0] - below[10.0]
    return {
        "first_below_10": below[10.0],
        "first_below_5": below[5.0],
        "first_below_3": below[3.0],
        "rounds_10_to_5": ten_to_five,
    }


def cold_start(economy) -> dict:
    """Tables 9.1, 9.2 and 9.5: one run from 700 to 3%, read at three thresholds."""
    result = run(
        HahnelBook2021(threshold_pct=YEAR_THRESHOLD, record_trajectory=True), economy, seed=0
    )
    worst = worst_imbalance_pct(economy, result.summary.trajectory)
    return {
        "rounds": result.summary.rounds,
        "converged": result.summary.converged,
        **threshold_readings(worst),
        "worst_pct_per_round": worst,
    }


def two_years(economy, seed: int) -> dict:
    """Table 9.4 for one seed: year two from year one's final price and multiplier."""
    result = run_periods(
        economy,
        HahnelBook2021(threshold_pct=YEAR_THRESHOLD),
        periods=2,
        seed=seed,
        advance=perturb_exponents,
        next_procedure=WarmStart(record_trajectory=True),
    )
    first, second = result.periods
    worst = worst_imbalance_pct(second.economy, second.result.summary.trajectory)
    return {
        "seed": seed,
        "year_1_rounds": first.result.summary.rounds,
        "year_1_converged": first.result.summary.converged,
        "year_2_first_below_5": first_round_below(worst, WARM_REPORT_THRESHOLD),
        "year_2_rounds": second.result.summary.rounds,
        "year_2_converged": second.result.summary.converged,
        "gdp_growth_pct": real_gdp_growth(
            first.economy, first.result.plan, second.economy, second.result.plan
        ),
    }


def run_experiment(n: int, n_seeds: int) -> dict:
    """Every phase for experiment ``n``, with the wall time of each."""
    path = DATA / f"dep1ex{n:02d}.clj.gz"
    started = time.perf_counter()
    economy = demplan.load_dep1ex(path, endowment=ENDOWMENT)
    seconds = {"load": time.perf_counter() - started}

    started = time.perf_counter()
    cold = cold_start(economy)
    seconds["cold"] = time.perf_counter() - started

    started = time.perf_counter()
    warm = [two_years(economy, seed) for seed in range(n_seeds)]
    seconds["warm"] = time.perf_counter() - started

    started = time.perf_counter()
    raised = []
    for seed in range(n_seeds):
        unit_seed = split_seed(seed, INCREASING_RETURNS_SEED_WORD + 1)[INCREASING_RETURNS_SEED_WORD]
        row = two_years(increasing_returns(economy, seed=unit_seed), seed)
        row["unit_seed"] = unit_seed
        raised.append(row)
    seconds["increasing_returns"] = time.perf_counter() - started

    print(f"  dep1ex{n:02d} done in {sum(seconds.values()):.0f}s", flush=True)
    return {
        "experiment": n,
        "file": path.name,
        "book": book_row(n),
        "cold": cold,
        "warm": warm,
        "increasing_returns": raised,
        "seconds": seconds,
    }


def spread(values: list) -> dict:
    """Mean, min, max and count of the values that are not None, and how many were None."""
    present = [v for v in values if v is not None]
    if not present:
        return {"mean": None, "min": None, "max": None, "n": 0, "missing": len(values)}
    return {
        "mean": statistics.fmean(present),
        "min": min(present),
        "max": max(present),
        "n": len(present),
        "missing": len(values) - len(present),
    }


def distribution(values: list) -> dict:
    """How often each value occurs, as ``{value: count}`` with ``None`` written as ``"none"``."""
    counts = Counter("none" if v is None else v for v in values)
    return {str(k): counts[k] for k in sorted(counts, key=lambda k: (k == "none", k))}


def summarise(rows: list[dict]) -> dict:
    """The per-experiment rows reduced to what the tables compare."""
    ns = [row["experiment"] for row in rows]
    cold = [row["cold"] for row in rows]
    warm = [seed_row for row in rows for seed_row in row["warm"]]
    raised = [seed_row for row in rows for seed_row in row["increasing_returns"]]
    book = [book_row(n) for n in ns]

    def per_experiment_mean(key, phase):
        return [statistics.fmean([r[key] for r in row[phase] if r[key] is not None])
                if any(r[key] is not None for r in row[phase]) else None for row in rows]

    return {
        "experiments": ns,
        "table_9_1": {"book": spread([b["table_9_1_first_below_5"] for b in book]),
                      "ours": spread([c["first_below_5"] for c in cold])},
        "table_9_2": {"book": spread([b["table_9_2_first_below_3"] for b in book]),
                      "ours": spread([c["first_below_3"] for c in cold])},
        "table_9_5": {"book": spread([b["table_9_5_rounds"] for b in book]),
                      "ours": spread([c["rounds_10_to_5"] for c in cold])},
        "table_9_4_rounds": {
            "book": spread([b["table_9_4_rounds"] for b in book]),
            "ours_all_seeds": spread([r["year_2_first_below_5"] for r in warm]),
            "ours_per_experiment_mean": spread(per_experiment_mean("year_2_first_below_5", "warm")),
            "book_distribution": distribution([b["table_9_4_rounds"] for b in book]),
            "ours_distribution": distribution([r["year_2_first_below_5"] for r in warm]),
        },
        "table_9_4_year_2_rounds_to_3": {"ours_all_seeds": spread([r["year_2_rounds"] for r in warm])},
        "table_9_4_gdp": {
            "book": spread([b["table_9_4_gdp"] for b in book]),
            "ours_all_seeds": spread([r["gdp_growth_pct"] for r in warm]),
            "ours_per_experiment_mean": spread(per_experiment_mean("gdp_growth_pct", "warm")),
        },
        "table_9_6_rounds": {
            "book": spread([b["table_9_6_rounds"] for b in book]),
            "ours_all_seeds": spread([r["year_2_first_below_5"] for r in raised]),
            "ours_per_experiment_mean": spread(
                per_experiment_mean("year_2_first_below_5", "increasing_returns")),
            "book_distribution": distribution([b["table_9_6_rounds"] for b in book]),
            "ours_distribution": distribution([r["year_2_first_below_5"] for r in raised]),
        },
        "table_9_6_year_1_rounds_to_3": {"ours_all_seeds": spread([r["year_1_rounds"] for r in raised])},
        "table_9_6_gdp": {
            "book": spread([b["table_9_6_gdp"] for b in book]),
            "ours_all_seeds": spread([r["gdp_growth_pct"] for r in raised]),
            "ours_per_experiment_mean": spread(
                per_experiment_mean("gdp_growth_pct", "increasing_returns")),
        },
        "not_converged": {
            "cold": sum(1 for c in cold if not c["converged"]),
            "warm_year_1": sum(1 for r in warm if not r["year_1_converged"]),
            "warm_year_2": sum(1 for r in warm if not r["year_2_converged"]),
            "increasing_returns_year_1": sum(1 for r in raised if not r["year_1_converged"]),
            "increasing_returns_year_2": sum(1 for r in raised if not r["year_2_converged"]),
        },
        "seconds": {phase: sum(row["seconds"][phase] for row in rows)
                    for phase in ("load", "cold", "warm", "increasing_returns")},
    }


def _fmt(value, width=6, digits=2) -> str:
    if value is None:
        return "-".rjust(width)
    if isinstance(value, float):
        return f"{value:{width}.{digits}f}"
    return f"{value:>{width}}"


def print_rows(rows: list[dict]) -> None:
    """One line per experiment: book value, then ours, per table."""
    print("\nPer experiment: book / demplan. Warm start and Table 9.6 as the mean over seeds "
          "[min-max].")
    print(f"{'exp':>3} | {'9.1':>9} | {'9.2':>9} | {'9.5':>9} | {'9.4 rounds':>20} | "
          f"{'9.4 gdp':>16} | {'9.6 rounds':>20} | {'9.6 gdp':>16}")
    for row in rows:
        book, cold = row["book"], row["cold"]
        cells = [
            f"{row['experiment']:>3}",
            f"{book['table_9_1_first_below_5']:>3} / {_fmt(cold['first_below_5'], 3)}",
            f"{book['table_9_2_first_below_3']:>3} / {_fmt(cold['first_below_3'], 3)}",
            f"{book['table_9_5_rounds']:>3} / {_fmt(cold['rounds_10_to_5'], 3)}",
        ]
        for phase, round_key, gdp_key in (("warm", "table_9_4_rounds", "table_9_4_gdp"),
                                          ("increasing_returns", "table_9_6_rounds",
                                           "table_9_6_gdp")):
            rounds = spread([r["year_2_first_below_5"] for r in row[phase]])
            gdp = spread([r["gdp_growth_pct"] for r in row[phase]])
            cells.append(f"{book[round_key]:>3} / {_fmt(rounds['mean'], 4)} "
                         f"[{_fmt(rounds['min'], 1)}-{_fmt(rounds['max'], 1)}]")
            cells.append(f"{book[gdp_key]:5.3f} / {_fmt(gdp['mean'], 5, 3)}")
        print(" | ".join(cells))


def print_summary(summary: dict) -> None:
    print("\nSummary over experiments " + ", ".join(map(str, summary["experiments"])))
    print(f"{'table':<30} {'book mean':>10} {'min':>6} {'max':>6}   {'demplan mean':>12} "
          f"{'min':>6} {'max':>6} {'n':>4}")
    lines = (
        ("9.1 first round < 5%", "table_9_1", "ours"),
        ("9.2 first round < 3%", "table_9_2", "ours"),
        ("9.5 rounds 10% -> 5%", "table_9_5", "ours"),
        ("9.4 year-2 rounds to 5%", "table_9_4_rounds", "ours_all_seeds"),
        ("9.4 GDP growth %", "table_9_4_gdp", "ours_all_seeds"),
        ("9.6 year-2 rounds to 5%", "table_9_6_rounds", "ours_all_seeds"),
        ("9.6 GDP growth %", "table_9_6_gdp", "ours_all_seeds"),
    )
    for label, key, ours_key in lines:
        book, ours = summary[key]["book"], summary[key][ours_key]
        print(f"{label:<30} {_fmt(book['mean'], 10, 3)} {_fmt(book['min'], 6, 3)} "
              f"{_fmt(book['max'], 6, 3)}   {_fmt(ours['mean'], 12, 3)} {_fmt(ours['min'], 6, 3)} "
              f"{_fmt(ours['max'], 6, 3)} {ours['n']:>4}")
    for key in ("table_9_4_rounds", "table_9_6_rounds"):
        print(f"\n{key} distribution  book: {summary[key]['book_distribution']}")
        print(f"{key} distribution  ours: {summary[key]['ours_distribution']}")
    print(f"\nyear-2 rounds to 3% (warm): {summary['table_9_4_year_2_rounds_to_3']['ours_all_seeds']}")
    print(f"not converged: {summary['not_converged']}")
    print("wall seconds per phase: " + ", ".join(
        f"{phase} {seconds:.0f}" for phase, seconds in summary["seconds"].items()))


def experiment_range(text: str) -> list[int]:
    """``"1-40"`` or ``"1,3,7"`` or a mix, as a sorted list of experiment numbers."""
    numbers = set()
    for part in text.split(","):
        if "-" in part:
            low, high = part.split("-")
            numbers.update(range(int(low), int(high) + 1))
        else:
            numbers.add(int(part))
    last = len(BOOK_TABLES["9.1", "#I"])
    wrong = [n for n in numbers if not 1 <= n <= last]
    if wrong:
        raise SystemExit(f"experiments must be between 1 and {last}, got {wrong}")
    return sorted(numbers)


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    parser.add_argument("--experiments", default="1-40", help="e.g. 1-40 or 1,2,5 (default 1-40)")
    parser.add_argument("--seeds", type=int, default=10, help="seeds per experiment (default 10)")
    parser.add_argument("--jobs", type=int, default=1, help="experiments run in parallel")
    parser.add_argument("--out", default="hahnel_book.json", help="output JSON path")
    args = parser.parse_args(argv)

    experiments = experiment_range(args.experiments)
    print(f"demplan {demplan.__file__}")
    print(f"data {DATA}; experiments {experiments}; {args.seeds} seeds each; {args.jobs} jobs",
          flush=True)
    started = time.perf_counter()
    if args.jobs > 1:
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            rows = list(pool.map(run_experiment, experiments, [args.seeds] * len(experiments)))
    else:
        rows = [run_experiment(n, args.seeds) for n in experiments]
    wall = time.perf_counter() - started

    summary = summarise(rows)
    summary["wall_seconds"] = wall
    print_rows(rows)
    print_summary(summary)
    print(f"total wall seconds: {wall:.0f}")
    Path(args.out).write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=1), encoding="utf-8"
    )
    print(f"written to {args.out}")


if __name__ == "__main__":
    main(sys.argv[1:])
