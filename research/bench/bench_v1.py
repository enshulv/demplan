"""
Acceptance-time end-to-end timing: how long the same set of experiments takes on each of
three paths.

  upstream pequod-plus   Clojure; the author's run log records 160 to 253 minutes per experiment,
                         measured before the SQLite version (see docs/research/reproduction.md)
  numpy reference        research/bench/{repro,endowment}.py
  demplan                this library: the Rust loader + a Python prefab

Usage:
  .venv/Scripts/python.exe research/bench/bench_v1.py [dep1ex01.clj.gz ...]
"""
import os
import sys
import time
from pathlib import Path

import numpy as np
import psutil

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data"
sys.path.insert(0, str(HERE))

import repro  # noqa: E402
import endowment as E  # noqa: E402

import demplan  # noqa: E402
from demplan.prefabs.hahnel_2020_slides import HahnelSlides2020  # noqa: E402

UPSTREAM_SECONDS = 4 * 3600.0


def rss_mb():
    return psutil.Process().memory_info().rss / 1e6


def bench_numpy(path):
    t0 = time.perf_counter()
    wc, cc = repro.parse(str(path))
    t_load = time.perf_counter() - t0
    dims = (cc["priv_exp"].shape[1], cc["pub_exp"].shape[1], int(wc["coef"].max()) + 1)
    t0 = time.perf_counter()
    rounds, _, _ = E.run(wc, cc, dims, 1000.0, "slides_capv", 5.0)
    t_run = time.perf_counter() - t0
    return t_load, t_run, rounds, rss_mb()


def bench_demplan(path):
    t0 = time.perf_counter()
    economy = demplan.load_dep1ex(path, endowment=1000.0)
    t_load = time.perf_counter() - t0
    t0 = time.perf_counter()
    result = demplan.run(HahnelSlides2020(), economy, seed=0)
    t_run = time.perf_counter() - t0
    return t_load, t_run, result.summary.rounds, rss_mb()


def main(files):
    print(f"{'file':<10} {'path':<12} {'load s':>8} {'solve s':>8} {'total s':>8} {'rounds':>6} {'rss MB':>7}")
    print("-" * 66)
    for name in files:
        path = DATA / name
        rows = []
        for label, fn in (("numpy", bench_numpy), ("demplan", bench_demplan)):
            t_load, t_run, rounds, rss = fn(path)
            rows.append((label, t_load, t_run, rounds, rss))
            print(f"{name[:8]:<10} {label:<12} {t_load:>8.2f} {t_run:>8.2f} {t_load + t_run:>8.2f} "
                  f"{rounds!s:>6} {rss:>7.0f}", flush=True)
        _, nl, nr, _, _ = rows[0]
        _, cl, cr, _, _ = rows[1]
        print(f"{'':<10} {'upstream':<12} {'':>8} {'':>8} {UPSTREAM_SECONDS:>8.0f}")
        print(f"{'':<10} speedup vs numpy {(nl + nr) / (cl + cr):.1f}x, vs upstream {UPSTREAM_SECONDS / (cl + cr):.0f}x")
        print("-" * 66)


if __name__ == "__main__":
    args = sys.argv[1:] or ["dep1ex01.clj.gz"]
    main(args)
