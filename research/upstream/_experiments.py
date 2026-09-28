"""The book's experiment numbers, the files each one corresponds to, and the --experiments option."""
from __future__ import annotations

import argparse

FIRST, LAST = 1, 40
OUTPUT_OFFSET = 60
"""Book experiment N is the program's experiment 60 + N (check_inputs.py, check_rules.py)."""


def output_number(experiment: int) -> int:
    """The number of the program's output file ``dep1exMM.csv`` for book experiment ``experiment``."""
    return OUTPUT_OFFSET + experiment


def output_name(number: int) -> str:
    """Manifest name of the program's output file ``dep1ex<number>.csv``."""
    return f"pequod-cljs@df6dc57/dep1ex{number}.csv"


def next_experiment(experiment: int) -> int:
    """The book experiment after ``experiment``, wrapping from the last to the first.

    Its output file is the control that belongs to another economy.
    """
    return experiment % LAST + FIRST


def archive_name(experiment: int) -> str:
    """Manifest name of the public input archive of book experiment ``experiment``."""
    return f"dep1ex{experiment:02d}.clj.gz"


def parse_experiments(text: str) -> list[int]:
    """``"1-40"``, ``"1,3,7"`` or a mix, as a sorted list; exits naming any number out of range."""
    numbers = set()
    for part in text.split(","):
        low, _, high = part.partition("-")
        numbers.update(range(int(low), int(high or low) + 1))
    wrong = sorted(n for n in numbers if not FIRST <= n <= LAST)
    if wrong:
        raise SystemExit(f"experiments must be between {FIRST} and {LAST}, got {wrong}")
    return sorted(numbers)


def add_experiments_argument(parser: argparse.ArgumentParser, default: str = f"{FIRST}-{LAST}") -> None:
    """The ``--experiments`` option, defaulting to ``default`` (all 40 unless given)."""
    parser.add_argument("--experiments", default=default, type=parse_experiments,
                        help=f"book experiments, e.g. 1-3 or 1,5,38 (default {default})")


def span(experiments: list[int]) -> str:
    """``"1-40"`` for a contiguous run, otherwise the numbers separated by commas."""
    if experiments == list(range(experiments[0], experiments[-1] + 1)):
        return f"{experiments[0]}-{experiments[-1]}"
    return ",".join(map(str, experiments))
