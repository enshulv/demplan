"""Writes the worker-council cases that `probe.closed-forms` solves with the program's closed forms.

Four groups of cases, each a worker council with its parameters and the prices it faces:

- `dep1ex01-final/<i>`: every worker council of the public archive dep1ex01 (the book's
  experiment 1), at the prices of the last round of year one in pequod-cljs's output for that
  economy (`dep1ex61.csv` at pequod-cljs commit df6dc57).
- `dep1ex01-uniform/<i>`: 100 of those councils for each number of inputs, with every price at
  700, the price every commodity starts from in pequod-plus.
- `generator/<N>/<j>`: 100 councils for each number of inputs N from 3 to 10, with parameters drawn
  from the ranges of `pequod-plus.populate` at 44a6d08 and prices drawn from the dep1ex61 prices
  above.
- `sweep/<f>`: the first five-input council of dep1ex01, every price at 700 except the price of its
  third input, which is 700·f.

The two published files are taken through `research/upstream/fetch.py` and checked against its
`manifest.tsv`.

Output: `closed-form-cases.edn` for the probe and `closed-form-cases.json` for
`verify_closed_forms.py`, with the same content, in OUT_DIR.

Usage: python make_closed_form_cases.py OUT_DIR [--cache DIR] [--data-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import _experiments  # noqa: E402
import fetch  # noqa: E402
from _dep1ex_councils import (INPUT_CATEGORIES, PRICE_CATEGORIES, PRODUCT_CATEGORY,  # noqa: E402
                              council_from_dep1ex, input_count, read_worker_councils)
from _program_output import read_year_one  # noqa: E402

INITIAL_PRICE = 700.0
SEED = 20260928
UNIFORM_SAMPLE_PER_N = 100
GENERATOR_CASES_PER_N = 100
SWEEP_FACTORS = (0.25, 0.5, 0.8, 0.9, 1.0, 1.1, 1.25, 2.0, 4.0)
EXPERIMENT = 1
"""The book experiment whose councils and prices the cases use."""
CASES_NAME = "closed-form-cases"


def generator_council(rng: random.Random, n: int) -> dict:
    """A council with n inputs, parameters in the ranges of `pequod-plus.populate` at 44a6d08.

    Ranges there: effort elasticity c in [0.05, 0.1], total factor productivity a in [4, 6],
    disutility coefficient s = 1, disutility exponent k in [3, 4], each input exponent in
    [0.75/m, 0.85/m] where m counts the inputs including 1 to 3 pollutants (which the program
    leaves out when pollutants are off). Category sizes: 1-5 intermediate inputs, 1-3 natural
    resources, 1-3 kinds of labour.
    """
    while True:
        sizes = (rng.randint(1, 5), rng.randint(1, 3), rng.randint(1, 3))
        if sum(sizes) == n:
            break
    m = n + rng.randint(1, 3)
    inputs = {
        category: [[i, rng.uniform(0.75 / m, 0.85 / m)] for i in sorted(rng.sample(range(1, 101), size))]
        for category, size in zip(INPUT_CATEGORIES, sizes, strict=True)
    }
    return {"industry": rng.randint(0, 2), "product": rng.randint(1, 100), "a": rng.uniform(4, 6),
            "s": 1.0, "c": rng.uniform(0.05, 0.1), "k": rng.uniform(3, 4), "inputs": inputs}


def edn(value) -> str:
    """EDN text for dicts (string keys become keywords unless they are numeric ids), lists,
    strings, ints and floats."""
    if isinstance(value, dict):
        def key(k):
            """An integer key as it is, any other as a keyword."""
            return str(k) if isinstance(k, int) else ":" + k
        return "{" + " ".join(f"{key(k)} {edn(v)}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + " ".join(edn(v) for v in value) + "]"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, float):
        return repr(value)
    return str(value)


def year_one_final_prices(store: fetch.Store) -> tuple[int, dict[str, dict[int, float]]]:
    """The price columns of the last round of year one of dep1ex61.csv, as
    ``(round, {category: {commodity id: price}})``."""
    year = read_year_one(store.path(_experiments.output_name(_experiments.output_number(EXPERIMENT))))
    per = year.per_category
    prices = {category: {j + 1: float(year.price[-1, block * per + j]) for j in range(per)}
              for block, category in enumerate(PRICE_CATEGORIES)}
    return int(year.iteration[-1]), prices


def build_cases(store: fetch.Store) -> dict:
    """All cases and the price sets they reference."""
    rng = random.Random(SEED)
    councils = [council_from_dep1ex(wc) for wc in
                read_worker_councils(store.path(_experiments.archive_name(EXPERIMENT)))]
    final_round, final_prices = year_one_final_prices(store)
    uniform = {category: {i: INITIAL_PRICE for i in range(1, 101)} for category in PRICE_CATEGORIES}
    price_sets = {"dep1ex61-year1-final": final_prices, "uniform-700": uniform}

    cases = []
    for i, council in enumerate(councils, start=1):
        cases.append({"id": f"dep1ex01-final/{i}", "price-set": "dep1ex61-year1-final", **council})
    by_n: dict[int, list[int]] = {}
    for i, council in enumerate(councils, start=1):
        by_n.setdefault(input_count(council), []).append(i)
    for n in sorted(by_n):
        for i in sorted(rng.sample(by_n[n], min(UNIFORM_SAMPLE_PER_N, len(by_n[n])))):
            cases.append({"id": f"dep1ex01-uniform/{i}", "price-set": "uniform-700", **councils[i - 1]})
    for n in range(3, 11):
        for j in range(1, GENERATOR_CASES_PER_N + 1):
            council = generator_council(rng, n)
            overrides = {category: {i: rng.choice(list(final_prices[category].values()))
                                    for i, _ in council["inputs"][category]}
                         for category in INPUT_CATEGORIES}
            product_category = PRODUCT_CATEGORY[council["industry"]]
            overrides.setdefault(product_category, {})[council["product"]] = rng.choice(
                list(final_prices[product_category].values()))
            cases.append({"id": f"generator/{n}/{j}", "price-set": "uniform-700", "price-overrides": overrides,
                          **council})
    first_five = next(i for i, council in enumerate(councils, start=1) if input_count(council) == 5)
    council = councils[first_five - 1]
    third_category, third_id = next(
        (category, i) for position, (category, i) in enumerate(
            (category, i) for category in INPUT_CATEGORIES for i, _ in council["inputs"][category])
        if position == 2)
    for f in SWEEP_FACTORS:
        cases.append({"id": f"sweep/{f}", "price-set": "uniform-700",
                      "price-overrides": {third_category: {third_id: INITIAL_PRICE * f}},
                      "sweep-council": first_five, **council})
    return {"price-sets": price_sets, "cases": cases, "dep1ex61-year1-final-round": final_round}


def main(argv: list[str]) -> int:
    """Write the cases to OUT_DIR and print how many each group has."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out_dir", type=Path, help="directory the two case files are written to")
    fetch.add_location_arguments(parser)
    args = parser.parse_args(argv)
    data = build_cases(fetch.Store(fetch.roots_from(args)))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"{CASES_NAME}.json").write_text(json.dumps(data), encoding="utf-8")
    (args.out_dir / f"{CASES_NAME}.edn").write_text(
        edn({"price-sets": data["price-sets"], "cases": data["cases"]}), encoding="utf-8")
    counts: dict[str, int] = {}
    for case in data["cases"]:
        group = case["id"].split("/")[0]
        counts[group] = counts.get(group, 0) + 1
    print(f"closed-form cases: {counts}; dep1ex61 prices from round {data['dep1ex61-year1-final-round']} of year one")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
