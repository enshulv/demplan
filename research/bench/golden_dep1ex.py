"""Bit-for-bit fingerprint of the prefab's plans on dep1ex01..05.

Run it once before a refactor and once after; the two JSON files must be identical.
Usage: python golden_dep1ex.py <out.json>
"""

from __future__ import annotations

import gc
import hashlib
import json
import pathlib
import sys

import numpy as np

import demplan

# The reference implementation has to come from the same checkout as the package under
# measurement, so the tests directory is resolved from where demplan was imported rather
# than from where this script sits.
sys.path.insert(0, str(pathlib.Path(demplan.__file__).resolve().parents[2] / "tests"))

from demplan import run
from demplan.prefabs.hahnel import HahnelBook2021
from reference.dep1ex_numpy import economy_from_repro, parse_dep1ex
from reference.paths import dep1ex_path


def digest(array) -> str:
    array = np.ascontiguousarray(np.asarray(array))
    return hashlib.sha256(array.tobytes()).hexdigest()[:32]


def fingerprint(plan) -> dict:
    fields = {
        name: digest(getattr(plan, name))
        for name in ("output", "input_use", "consumption", "consumption_commodity", "shared_use")
    }
    fields.update({f"valuation.{k}": digest(v) for k, v in sorted(plan.valuation.items())})
    fields.update({f"extra.{k}": digest(v) for k, v in sorted(plan.extra.items())})
    return fields


def main(out: str) -> None:
    report = {}
    for index in range(1, 6):
        wc, cc, layout = parse_dep1ex(dep1ex_path(index))
        economy = economy_from_repro(wc, cc, layout)
        five = run(HahnelBook2021(), economy, seed=0)
        three = run(HahnelBook2021(threshold_pct=3.0), economy, seed=0)
        report[f"dep1ex{index:02d}"] = {
            "rounds_5pct": five.summary.rounds,
            "rounds_3pct": three.summary.rounds,
            "converged_5pct": five.summary.converged,
            "plan_5pct": fingerprint(five.plan),
        }
        del wc, cc, economy, five, three
        gc.collect()
    pathlib.Path(out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({k: {"rounds_5pct": v["rounds_5pct"], "rounds_3pct": v["rounds_3pct"]}
                      for k, v in report.items()}, indent=2))


if __name__ == "__main__":
    main(sys.argv[1])
