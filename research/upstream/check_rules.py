"""
Runs Hahnel's councils in demplan under the program's price rule and under the rules as printed,
and compares every run with the program's output files.

Hahnel (2021), the 2020 slides and Szczepanczyk (2023) each describe the price-update rule of
the participatory-planning simulations, and none states the rule the program behind the
book's tables used (msszczep/pequod-cljs, src/clj/pequod_cljs/csvgen.clj at 71e44d3). This
script runs one model of the councils, demplan's demplan.prefabs.hahnel, on the public dep1ex
economies and changes only the price rule (the formulas are in _price_rules.py):

  program             w_k = max(0.001, min(v_{k-1}, 0.25) * (1.05 - 0.5**v_k)),  v_{-1} = 0.25
                      (demplan's book_2021_rule)
  book p.181          w_k = min(v_k, 0.25) * (1.05 - 0.5**v_k)
  paper p.7           w_k = min(v_k, 0.25) * (1.05 - 0.5**min(v_k, 0.25))
  book/paper + floor  the two above with the program's floor of 0.001 under the step

v is a commodity's relative imbalance |2(s - d)| / (s + d) in the round; the price falls to
p * (1 - w) in surplus and rises to p * (1 + w) in shortage. The texts state no lag and no
floor; the two floored rules show how much the floor alone changes: per experiment, each
printed rule's first rounds below 5% and 3% are printed next to those of the same rule with the
floor, and the summary counts the experiments where the floor changes one.

Each rule runs once per experiment, cold from price 700 until every imbalance is below 3%, and
records the worst imbalance of every round. From that series come the first round below 5%
(Table 9.1 of the book) and below 3% (Table 9.2). Under the program's rule the procedure
HahnelBook2021 is also run to 5% and to 3%, to confirm it stops at the rounds read from the
series.

Book experiment N is dep1exNN.clj.gz from www.szcz.org and the program's output file
dep1ex(60+N).csv at commit df6dc57 (check_inputs.py; the comparison below for experiments
19 to 40). Every rule's series is compared round by round with year one of that file, the
largest threshold-report value of each row: the program's rule should match and the text
rules should not. As a control that should not match either, the program's rule is also
compared with the output file of the next experiment, dep1ex(60+N+1).csv.

Usage:
  python research/upstream/check_rules.py [--experiments 1-5] [--cache DIR] [--data-dir DIR]

Missing files are downloaded and every file is checked against manifest.tsv (see fetch.py).
Each archive decompresses to about 160 MB and is loaded once per experiment.
"""
from __future__ import annotations

import argparse
import dataclasses
import importlib.metadata
import sys
import time
from typing import Callable, Sequence

import numpy as np

import demplan
from demplan import iterate, run
from demplan.prefabs.hahnel import (
    CouncilModel,
    HahnelBook2021,
    book_2021_rule,
    relative_imbalance,
    stateless,
)

import _book
import _experiments
import _price_rules as rules
import fetch
from _program_output import read_output
from _readings import first_color_exact

ENDOWMENT = 1000.0
"""Per-commodity endowment of every natural resource and kind of labour (csvgen.clj lines 212-213)."""

START_PRICE = rules.INITIAL_PRICE
"""Book p. 179: "an initial price vector where all prices were arbitrarily set equal to 700"."""

THRESHOLDS_PCT = (5.0, 3.0)
TABLE_OF_THRESHOLD = {5.0: "9.1", 3.0: "9.2"}
COLOR_OF_THRESHOLD = {5.0: ":green", 3.0: ":blue"}
MAX_ROUNDS = 250
PERCENT = 100.0


@dataclasses.dataclass(frozen=True)
class TextRule:
    """Moves each price by a step computed from this round's imbalance alone.

    Called with ``(price, surplus, imbalance)`` it returns the next price: ``price * (1 - w)``
    where the surplus is positive, ``price * (1 + w)`` where it is negative, and ``price``
    where it is zero, with ``w = step(imbalance)``. It keeps nothing between rounds.
    """

    step: Callable[[np.ndarray], np.ndarray]

    def __call__(self, price: np.ndarray, surplus: np.ndarray, imbalance: np.ndarray) -> np.ndarray:
        """The next price for every commodity."""
        return rules.next_price(price, surplus, self.step(imbalance))


BOOK_P181 = TextRule(rules.step_book)
PAPER_P7 = TextRule(rules.step_paper)
BOOK_P181_FLOORED = TextRule(rules.step_book_floored)
PAPER_P7_FLOORED = TextRule(rules.step_paper_floored)

PROGRAM = "program (book_2021_rule)"
BOOK = "book p.181 as printed"
PAPER = "paper p.7 as printed"
BOOK_FLOORED = "book p.181 + floor 0.001"
PAPER_FLOORED = "paper p.7 + floor 0.001"

RULES = {
    PROGRAM: book_2021_rule,
    BOOK: stateless(BOOK_P181),
    PAPER: stateless(PAPER_P7),
    BOOK_FLOORED: stateless(BOOK_P181_FLOORED),
    PAPER_FLOORED: stateless(PAPER_P7_FLOORED),
}
"""Every rule run, by the label the report prints; each is a demplan.prefabs.hahnel.PriceRule."""

SHORT = {PROGRAM: "program", BOOK: "book", PAPER: "paper", BOOK_FLOORED: "book+fl", PAPER_FLOORED: "paper+fl"}
"""Column headings of the summary tables."""

FLOORED = {BOOK: BOOK_FLOORED, PAPER: PAPER_FLOORED}
"""Each rule as printed and the same rule with the program's floor under the step."""


@dataclasses.dataclass(frozen=True)
class RuleRun:
    """One rule on one economy, from the start price until 3% or the round cap."""

    worst_pct: list[float]
    """The worst relative imbalance of every round, in percent, rebuilt from the round's plan."""
    diverged: bool | None


@dataclasses.dataclass(frozen=True)
class Difference:
    """The largest absolute difference between two per-round series over their common rounds."""

    value: float
    round: int
    compared: int


@dataclasses.dataclass(frozen=True)
class Comparison:
    """One demplan series against one output file's year one."""

    rounds: tuple[int, int]
    """Rounds in the demplan run and rows in the output file's year one."""
    first_below_5: tuple[int | None, int | None]
    difference: Difference


def first_round_below(worst_pct: Sequence[float], threshold_pct: float) -> int | None:
    """The first round, counted from 1, whose worst imbalance is below ``threshold_pct``."""
    for number, value in enumerate(worst_pct, start=1):
        if value < threshold_pct:
            return number
    return None


def largest_difference(first: Sequence[float], second: Sequence[float]) -> Difference:
    """The largest ``|first[k] - second[k]|`` over the rounds both series have."""
    compared = min(len(first), len(second))
    gaps = np.abs(np.asarray(first[:compared]) - np.asarray(second[:compared]))
    at = int(np.argmax(gaps))
    return Difference(float(gaps[at]), at + 1, compared)


def compare(ours: Sequence[float], theirs: Sequence[float]) -> Comparison:
    """A demplan series against an output file's series: lengths, first round below 5%, and
    the largest difference over the rounds both have."""
    return Comparison(rounds=(len(ours), len(theirs)),
                      first_below_5=(first_round_below(ours, 5.0), first_round_below(theirs, 5.0)),
                      difference=largest_difference(ours, theirs))


def run_rule(economy, rule) -> RuleRun:
    """Run ``rule`` on ``economy`` from 700 to 3% and record every round's worst imbalance.

    The loop is built the way HahnelBook2021.solve builds its own, with each round's plan read
    by relative_imbalance and then dropped, so that the run holds one plan at a time.
    """
    model = CouncilModel(economy, min(THRESHOLDS_PCT), rule)
    worst: list[float] = []

    def plan_recording_worst(state):
        """The round's plan, with its worst imbalance appended to ``worst``."""
        plan = model.plan_of(state)
        worst.append(float(np.max(relative_imbalance(economy, plan))) * PERCENT)
        return plan

    loop = iterate(
        lambda: model.initial_state(START_PRICE, None),
        model.step,
        model.converged,
        MAX_ROUNDS,
        plan_of=plan_recording_worst,
        keep_trajectory=False,
    )
    return RuleRun(worst, loop.diverged)


def procedure_rounds(economy, rule) -> dict[float, int | None]:
    """Per threshold, the round demplan.run on HahnelBook2021 stops at, or ``None`` at the cap."""
    stops = {}
    for threshold in THRESHOLDS_PCT:
        procedure = HahnelBook2021(threshold_pct=threshold, max_rounds=MAX_ROUNDS,
                                   initial_price=START_PRICE, price_rule=rule)
        summary = run(procedure, economy, seed=0).summary
        stops[threshold] = summary.rounds if summary.converged else None
    return stops


def cell(value) -> str:
    """A round count for the tables, ``-`` when there is none."""
    return "-" if value is None else str(value)


def floor_changes(experiments, counts) -> dict[str, list[int]]:
    """Per printed rule, the experiments whose first round below 5% or below 3% differs between
    the rule and the rule with the floor. ``counts[threshold][rule label][experiment]`` holds
    the first rounds, ``None`` where the run never got below the threshold."""
    return {rule: [n for n in experiments
                   if any(counts[t][rule][n] != counts[t][floored][n] for t in THRESHOLDS_PCT)]
            for rule, floored in FLOORED.items()}


def floor_summary(experiments, counts) -> str:
    """One line: how many experiments the floor changes a round count of, per printed rule and
    under either."""
    changed = floor_changes(experiments, counts)
    either = set().union(*changed.values())
    per_rule = ", ".join(f"{SHORT[rule]} {len(found)} of {len(experiments)}" for rule, found in changed.items())
    return (f"Experiments where the floor of 0.001 changes the first round below 5% or 3%: "
            f"{per_rule}, either {len(either)} of {len(experiments)}")


def print_floor_table(experiments, counts) -> None:
    """Per experiment, the first rounds below 5% and 3% of each printed rule next to the same
    rule with the floor, and which of them the floor changes."""
    print("\nFirst round below 5% and below 3% under each printed rule, without and with the program's "
          "floor of 0.001 under the step ('-': not within the cap)")
    columns = [(rule, threshold) for rule in FLOORED for threshold in THRESHOLDS_PCT]
    heading = "  ".join(f"{SHORT[rule] + ' <' + format(t, 'g') + '%':>10} {'+floor':>6}" for rule, t in columns)
    print(f"  {'exp':>3}  {heading}  floor changes")
    for n in experiments:
        values = "  ".join(f"{cell(counts[t][rule][n]):>10} {cell(counts[t][FLOORED[rule]][n]):>6}"
                           for rule, t in columns)
        changed = [f"{SHORT[rule]} <{t:g}%" for rule, t in columns
                   if counts[t][rule][n] != counts[t][FLOORED[rule]][n]]
        print(f"  {n:>3}  {values}  {', '.join(changed) or '-'}")


def print_rounds(output_label: str, output_worst, runs: dict[str, RuleRun]) -> None:
    """Every round's worst imbalance for one experiment: the program's output and each rule."""
    labels = [output_label] + [SHORT[label] for label in runs]
    series = [list(output_worst)] + [runs[label].worst_pct for label in runs]
    length = max(len(s) for s in series)
    print("  worst relative imbalance per round, percent")
    print("  round  " + "  ".join(f"{label:>22}" for label in labels))
    for k in range(length):
        values = [f"{s[k]:22.15g}" if k < len(s) else f"{'':22}" for s in series]
        print(f"  {k + 1:5d}  " + "  ".join(values))


def main(argv: list[str]) -> int:
    """Run every selected experiment under the five rules and print the comparisons; exit status 0."""
    # Paths may hold non-ASCII characters; a Windows console or pipe defaults to a legacy code page.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="\n\n".join(__doc__.strip().split("\n\n")[1:]))
    _experiments.add_experiments_argument(parser, default="1-5")
    fetch.add_location_arguments(parser)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    store = fetch.Store(fetch.roots_from(args))
    tables = _book.load_tables()
    experiments = args.experiments

    print(f"demplan {importlib.metadata.version('demplan')} at {demplan.__file__}, numpy {np.__version__}, "
          f"Python {sys.version.split()[0]}")
    print(f"Councils: demplan.prefabs.hahnel.CouncilModel, cold start at {START_PRICE:g}, "
          f"endowment {ENDOWMENT:g}, round cap {MAX_ROUNDS}.")
    print("Program output: year one of dep1ex(60+N).csv (rows before the first 'exponent-sum' row); "
          "worst = largest :threshold-report-* value of the row.")

    outputs: dict[int, object] = {}

    def year_one(experiment: int):
        """Year one of the output file of ``experiment``, read once."""
        if experiment not in outputs:
            path = store.path(_experiments.output_name(_experiments.output_number(experiment)))
            outputs[experiment] = read_output(path).years[0]
        return outputs[experiment]

    counts = {t: {label: {} for label in RULES} for t in THRESHOLDS_PCT}
    confirmed: dict[int, dict[float, int | None]] = {}
    comparisons: dict[str, dict[int, Comparison]] = {label: {} for label in (*RULES, "next file")}
    seconds = {"load": 0.0, "run": 0.0}
    for n in experiments:
        own_name = f"dep1ex{_experiments.output_number(n)}.csv"
        following = _experiments.next_experiment(n)
        next_name = f"dep1ex{_experiments.output_number(following)}.csv"
        print(f"\n== Experiment {n}: dep1ex{n:02d}.clj.gz against {own_name} ==", flush=True)
        archive = store.path(_experiments.archive_name(n))
        output = year_one(n)
        t = time.perf_counter()
        economy = demplan.load_dep1ex(archive, endowment=ENDOWMENT)
        seconds["load"] += time.perf_counter() - t
        print(f"  loaded in {time.perf_counter() - t:.1f} s: {economy.n_commodities} commodities, "
              f"{economy.n_units} producing units; {own_name}: {len(output.iteration)} year-one rows")
        runs = {}
        for label, rule in RULES.items():
            t = time.perf_counter()
            runs[label] = outcome = run_rule(economy, rule)
            seconds["run"] += time.perf_counter() - t
            below = {th: first_round_below(outcome.worst_pct, th) for th in THRESHOLDS_PCT}
            for th in THRESHOLDS_PCT:
                counts[th][label][n] = below[th]
            comparisons[label][n] = c = compare(outcome.worst_pct, output.worst)
            print(f"  {label:<26} {len(outcome.worst_pct):>3} rounds, diverged={outcome.diverged}, "
                  f"{time.perf_counter() - t:5.1f} s; first < 5% / < 3%: {cell(below[5.0])} / {cell(below[3.0])}; "
                  f"vs {own_name}: max |diff| {c.difference.value:.3e} pp at round {c.difference.round} "
                  f"of {c.difference.compared}", flush=True)
            if label == PROGRAM:
                t = time.perf_counter()
                confirmed[n] = procedure_rounds(economy, rule)
                seconds["run"] += time.perf_counter() - t
                same = all(confirmed[n][th] == below[th] for th in THRESHOLDS_PCT)
                print(f"  {'':<26} HahnelBook2021 stops at {cell(confirmed[n][5.0])} (5%) and "
                      f"{cell(confirmed[n][3.0])} (3%); same as the series: {same}", flush=True)
                comparisons["next file"][n] = c = compare(outcome.worst_pct, year_one(following).worst)
                print(f"  {'':<26} control, vs {next_name}: max |diff| {c.difference.value:.3e} pp at "
                      f"round {c.difference.round} of {c.difference.compared}", flush=True)
        del economy
        print_rounds(own_name, output.worst, runs)

    for threshold in THRESHOLDS_PCT:
        table = TABLE_OF_THRESHOLD[threshold]
        color = COLOR_OF_THRESHOLD[threshold]
        print(f"\nFirst round with every relative imbalance below {threshold:g}% (Table {table}). demplan: "
              f"read from each rule's series ('-': not within the cap); output: first year-one row "
              f"with every threshold-report below {threshold:g}, and first row whose :color is {color}")
        heading = "  ".join(f"{SHORT[label]:>8}" for label in RULES)
        print(f"  {'exp':>3}  {heading}  {'output':>6} {color:>7}  {'printed':>7}")
        for n in experiments:
            output = year_one(n)
            values = "  ".join(f"{cell(counts[threshold][label][n]):>8}" for label in RULES)
            print(f"  {n:>3}  {values}  {cell(first_round_below(output.worst, threshold)):>6} "
                  f"{cell(first_color_exact(output.color, output.iteration, color)):>7}  "
                  f"{tables[(table, '#I')][n].printed:>7}")

    print_floor_table(experiments, counts)

    print("\nWorst imbalance per round against the output files, largest |difference| in percentage "
          "points over the rounds both have; last column: the program's rule against the next "
          "experiment's file")
    heading = "  ".join(f"{SHORT[label]:>10}" for label in RULES)
    print(f"  {'exp':>3}  {heading}  {'next file':>10}")
    for n in experiments:
        values = "  ".join(f"{comparisons[label][n].difference.value:>10.3e}" for label in (*RULES, "next file"))
        print(f"  {n:>3}  {values}")

    print(f"\nSummary over experiments {_experiments.span(experiments)}")
    print(f"  {'comparison':<46} {'largest max |diff|':>18} {'smallest max |diff|':>20}  "
          f"{'rounds equal':>12} {'first < 5% equal':>16}")
    for label, rows in comparisons.items():
        diffs = {n: c.difference.value for n, c in rows.items()}
        worst_n = max(diffs, key=diffs.get)
        best_n = min(diffs, key=diffs.get)
        same_rounds = sum(c.rounds[0] == c.rounds[1] for c in rows.values())
        same_first = sum(c.first_below_5[0] == c.first_below_5[1] for c in rows.values())
        name = "program rule vs next experiment's file" if label == "next file" else f"{SHORT[label]} rule vs own file"
        print(f"  {name:<46} {diffs[worst_n]:>11.3e} (#{worst_n:>2}) {diffs[best_n]:>13.3e} (#{best_n:>2})  "
              f"{same_rounds:>6}/{len(rows):<5} {same_first:>9}/{len(rows):<6}")
    agree = sum(all(confirmed[n][th] == counts[th][PROGRAM][n] for th in THRESHOLDS_PCT) for n in experiments)
    print(f"  HahnelBook2021 under the program's rule stops where its series first falls below 5% and 3%: "
          f"{agree}/{len(experiments)}")
    print(f"  {floor_summary(experiments, counts)}")
    wall = time.perf_counter() - started
    print(f"\nwall seconds: {wall:.0f} (loading archives {seconds['load']:.0f}, demplan runs "
          f"{seconds['run']:.0f}, the rest reading and checking files)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
