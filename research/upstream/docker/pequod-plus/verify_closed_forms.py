"""Checks the worker-council proposals `probe.closed-forms` obtained from pequod-plus.

The problem each proposal should solve (a worker council choosing inputs x_1..x_N and effort e) is
stated in `research/upstream/_council_optimum.py`:

    maximise  λ·a·x_1^b_1···x_N^b_N·e^c  −  Σ p_i·x_i  −  s·e^k

For each case this script, without using any pequod-plus code:
1. evaluates the first-order conditions at the program's solution, as log residuals
   log(λ·b_i·z) − log(p_i·x_i), log(λ·c·z) − log(s·k·e^k) and the production function
   log z − log(a·Πx_i^b_i·e^c);
2. maximises the objective numerically with scipy (trust-region Newton on log x, log e, started
   at x = e = 1, then plain Newton steps) and compares the program's output, effort and inputs
   with the maximiser.

Usage: python verify_closed_forms.py CASES.json LABEL=RESULTS.tsv [LABEL=RESULTS.tsv ...]
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _council_optimum import (CouncilProblem, foc_residuals, maximise, objective,  # noqa: E402
                              predicted_effort_ratio)
from _dep1ex_councils import INPUT_CATEGORIES, PRODUCT_CATEGORY  # noqa: E402

MATCH_TOLERANCE = 1e-8
"""Relative difference below which the program's value and the maximiser are counted as equal.
The first-order-condition residuals at the maximiser are printed; the values are always printed."""


def case_problem(case: dict, price_sets: dict) -> CouncilProblem:
    """The problem of one case: its price set with the case's overrides on top."""
    prices = {category: dict(values) for category, values in price_sets[case["price-set"]].items()}
    for category, values in case.get("price-overrides", {}).items():
        prices[category].update(values)
    b, p = [], []
    for category in INPUT_CATEGORIES:
        for commodity, exponent in case["inputs"][category]:
            b.append(exponent)
            p.append(prices[category][str(commodity)])
    lam = prices[PRODUCT_CATEGORY[case["industry"]]][str(case["product"])]
    return CouncilProblem(a=case["a"], s=case["s"], c=case["c"], k=case["k"], lam=lam,
                          b=np.array(b), p=np.array(p))


def predicted_x1_ratio(problem: CouncilProblem) -> float:
    """x1 from an expression with b3·k·log(p2) in place of b3·k·log(p3), divided by the correct x1.

    In log x1 = (numerator)/D the substitution adds b3·k·(log p2 − log p3)/D, so the ratio is
    exp(b3·k·(log p2 − log p3)/D), D = c − k + k·Σb. This is derived by hand from the expression,
    and is printed next to the measured ratio.
    """
    b, p, c, k = problem.b, problem.p, problem.c, problem.k
    denominator = c - k + k * float(b.sum())
    return math.exp(b[2] * k * (math.log(p[1]) - math.log(p[2])) / denominator)


def read_results(path: Path) -> dict[str, dict]:
    """Rows of a probe results file keyed by case id."""
    rows = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if row["output"] == "-":
                rows[row["case_id"]] = {"entry_point": row["entry_point"], "missing": True}
                continue
            rows[row["case_id"]] = {"entry_point": row["entry_point"], "missing": False,
                                    "output": float(row["output"]), "effort": float(row["effort"]),
                                    "x": np.array([float(v) for v in row["x"].split(";")])}
    return rows


def rel(program: np.ndarray | float, reference: np.ndarray | float) -> np.ndarray:
    """Relative difference program/reference − 1."""
    return np.asarray(program) / np.asarray(reference) - 1.0


def largest_relative_difference(row: dict, optimum: tuple[float, float, np.ndarray]) -> float:
    """The largest |program/maximiser - 1| over the output, the effort and every input of one case.

    ``row`` is a case as :func:`read_results` returns it; ``optimum`` is ``(output, effort,
    inputs)`` from the maximiser.
    """
    output, effort, x = optimum
    return max(abs(float(rel(row["output"], output))), abs(float(rel(row["effort"], effort))),
               float(np.max(np.abs(rel(row["x"], x)))))


def matches_optimum(row: dict, optimum: tuple[float, float, np.ndarray]) -> bool:
    """Whether the output, the effort and every input are within MATCH_TOLERANCE of the maximiser."""
    return largest_relative_difference(row, optimum) <= MATCH_TOLERANCE


def fmt(value: float) -> str:
    """Compact scientific notation for the tables."""
    return f"{value:.2e}"


def print_table(header: list[str], rows: list[list]) -> None:
    """Prints rows under header in space-padded columns."""
    cells = [header] + [[str(v) for v in row] for row in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(header))]
    for n, row in enumerate(cells):
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)).rstrip())
        if n == 0:
            print("  ".join("-" * w for w in widths))


def group_of(case_id: str) -> str:
    """Case group: dep1ex01-final, dep1ex01-uniform, generator or sweep."""
    return case_id.split("/")[0]


def by_group_and_n(cases: list[dict], problems: dict) -> dict[tuple[str, int], list[str]]:
    """Case ids grouped by (case group, number of inputs)."""
    groups: dict[tuple[str, int], list[str]] = {}
    for case in cases:
        groups.setdefault((group_of(case["id"]), len(problems[case["id"]].b)), []).append(case["id"])
    return groups


def print_summary(label: str, rows: dict, groups: dict, problems: dict, optima: dict) -> None:
    """One line per (case group, N): count, cases matching throughout, largest differences."""
    table = []
    for (group, n), ids in sorted(groups.items()):
        present = [i for i in ids if not rows[i]["missing"]]
        if group == "sweep":
            continue
        if not present:
            table.append([label, group, n, len(ids), 0, "-", "-", "-", "-", "-",
                          f"{rows[ids[0]]['entry_point']} returned no solution"])
            continue
        d_out = [abs(float(rel(rows[i]["output"], optima[i][0]))) for i in present]
        d_eff = [abs(float(rel(rows[i]["effort"], optima[i][1]))) for i in present]
        d_x = [np.abs(rel(rows[i]["x"], optima[i][2])) for i in present]
        foc = max(float(np.max(np.abs(foc_residuals(problems[i], rows[i]["output"], rows[i]["effort"], rows[i]["x"]))))
                  for i in present)
        all_match = sum(1 for i in present if matches_optimum(rows[i], optima[i]))
        table.append([label, group, n, len(ids), all_match, fmt(max(d_out)), fmt(max(d_eff)),
                      fmt(max(float(d[0]) for d in d_x)), fmt(max(float(np.max(d[1:])) for d in d_x)), fmt(foc),
                      rows[present[0]]["entry_point"]])
    print()
    print(f"{label}: largest |program/maximiser - 1| by case group and number of inputs N")
    print("all_match = cases whose output, effort and every input are within the tolerance")
    print_table(["commit", "cases", "N", "count", "all_match", "output", "effort", "x1", "x2..xN",
                 "max_FOC_residual", "entry_point"], table)


def print_five_input_x1(label: str, rows: dict, cases: list[dict], problems: dict, optima: dict) -> None:
    """Distribution of the x1 error over the five-input councils of dep1ex01 at real prices."""
    five = [c["id"] for c in cases if group_of(c["id"]) == "dep1ex01-final" and len(problems[c["id"]].b) == 5]
    errors = np.array([float(rel(rows[i]["x"][0], optima[i][2][0])) for i in five])
    ratio_p2_p3 = np.array([problems[i].p[1] / problems[i].p[2] for i in five])
    predicted = np.array([predicted_x1_ratio(problems[i]) - 1.0 for i in five])
    shortfall = np.array([1.0 - objective(problems[i], rows[i]["x"], rows[i]["effort"])
                          / objective(problems[i], optima[i][2], optima[i][1]) for i in five])
    print()
    print(f"{label}: x1 of the {len(five)} five-input councils of dep1ex01 at the dep1ex61 year-one final prices")
    print_table(["statistic", "x1_program/x1_max - 1", "p2/p3"], [
        ["min", fmt(errors.min()), f"{ratio_p2_p3.min():.4f}"],
        ["median", fmt(float(np.median(errors))), f"{float(np.median(ratio_p2_p3)):.4f}"],
        ["max", fmt(errors.max()), f"{ratio_p2_p3.max():.4f}"],
        ["median of |x1_program/x1_max - 1|", fmt(float(np.median(np.abs(errors)))), ""],
        ["share with |x1_program/x1_max - 1| > 0.01", f"{float(np.mean(np.abs(errors) > 0.01)):.4f}", ""],
        ["share with |x1_program/x1_max - 1| > 0.10", f"{float(np.mean(np.abs(errors) > 0.10)):.4f}", ""],
    ])
    print("predicted_with_log_p2 = (p2/p3)^(k*b3/D) - 1, D = c - k + k*sum(b): the ratio that b3*k*log(p2) in place")
    print("of b3*k*log(p3) gives (algebra on the expression, see predicted_x1_ratio);")
    print(f"largest |observed - predicted_with_log_p2|: {fmt(float(np.max(np.abs(errors - predicted))))}")
    print(f"objective at the program's proposal, 1 - value/maximum: median {fmt(float(np.median(shortfall)))}, "
          f"max {fmt(float(shortfall.max()))}")


def print_effort(label: str, rows: dict, cases: list[dict], problems: dict, optima: dict) -> None:
    """Effort error of the councils with 8 and 10 inputs, next to the value predicted from the
    sign of the b_i·log k and b_i·log s terms."""
    table = []
    for n in (8, 10):
        ids = [c["id"] for c in cases if len(problems[c["id"]].b) == n and group_of(c["id"]) != "sweep"
               and not rows[c["id"]]["missing"]]
        if not ids:
            continue
        errors = np.array([float(rel(rows[i]["effort"], optima[i][1])) for i in ids])
        predicted = np.array([predicted_effort_ratio(problems[i]) - 1.0 for i in ids])
        table.append([label, n, len(ids), fmt(errors.min()), fmt(float(np.median(errors))), fmt(errors.max()),
                      fmt(float(np.max(np.abs(errors - predicted))))])
    print()
    print(f"{label}: effort of the councils with 8 and 10 inputs, effort_program/effort_max - 1")
    print("predicted_with_flipped_signs = exp(2*sum(b)*(log k + log s)/D) - 1: the ratio that +b_i*log(k) and")
    print("+b_i*log(s) in place of -b_i*log(k) and -b_i*log(s) give (algebra on the expression, see predicted_effort_ratio)")
    print_table(["commit", "N", "count", "min", "median", "max", "max |observed - predicted_with_flipped_signs|"], table)


def print_sweep(label: str, rows: dict, cases: list[dict], problems: dict, optima: dict) -> None:
    """x1 of one five-input council as the price of its third input moves away from the second's."""
    sweep = [c for c in cases if group_of(c["id"]) == "sweep"]
    print()
    print(f"{label}: dep1ex01 worker council {sweep[0]['sweep-council']}, every price 700 except the "
          "third input's (p3)")
    print_table(["p3/700", "p2/p3", "x1_program", "x1_max", "x1_program/x1_max - 1", "predicted_with_log_p2",
                 "x2..x5 max |program/max - 1|"], [
        [c["id"].split("/")[1], f"{problems[c['id']].p[1] / problems[c['id']].p[2]:.4f}",
         repr(float(rows[c["id"]]["x"][0])), repr(float(optima[c["id"]][2][0])),
         fmt(float(rel(rows[c["id"]]["x"][0], optima[c["id"]][2][0]))),
         fmt(predicted_x1_ratio(problems[c["id"]]) - 1.0),
         fmt(float(np.max(np.abs(rel(rows[c["id"]]["x"][1:], optima[c["id"]][2][1:])))))]
        for c in sweep])


def main() -> int:
    """Solve every case and print the comparisons for each results file."""
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    runs = [arg.split("=", 1) for arg in sys.argv[2:]]
    cases = data["cases"]
    problems = {case["id"]: case_problem(case, data["price-sets"]) for case in cases}
    optima = {case["id"]: maximise(problems[case["id"]]) for case in cases}
    groups = by_group_and_n(cases, problems)

    print("Closed forms: pequod-plus worker-council solutions against the first-order conditions and a")
    print("numerical maximiser (scipy trust-exact, then Newton steps; independent of pequod-plus).")
    print(f"Cases: {len(cases)}. Tolerance of the all_match counts: {MATCH_TOLERANCE} relative.")
    concave = sum(1 for p in problems.values() if float(p.b.sum()) + p.c < 1 and p.k > 1)
    print(f"Cases with sum(b) + c < 1 and k > 1 (objective strictly concave, one maximum): {concave} of {len(cases)}")
    optimum_foc = max(float(np.max(np.abs(foc_residuals(problems[i], *optima[i])))) for i in problems)
    print(f"Largest first-order-condition residual at the numerical maximiser: {fmt(optimum_foc)}")

    for label, path in runs:
        rows = read_results(Path(path))
        print_summary(label, rows, groups, problems, optima)
        print_five_input_x1(label, rows, cases, problems, optima)
        print_effort(label, rows, cases, problems, optima)
        print_sweep(label, rows, cases, problems, optima)
    return 0


if __name__ == "__main__":
    sys.exit(main())
