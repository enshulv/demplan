"""
验收用的端到端计时：同一组实验，三条路各花多久。

  上游 pequod-plus   Clojure + SQLite，约 4 小时一组（见 研究/复现记录.md）
  numpy 参考         research/bench/{repro,endowment}.py
  cyberstride        本库：Rust 加载器 + Python prefab

用法：
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

import cyberstride  # noqa: E402
from cyberstride.prefabs.hahnel_2020_slides import HahnelSlides2020  # noqa: E402

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


def bench_cyberstride(path):
    t0 = time.perf_counter()
    economy = cyberstride.load_dep1ex(path, endowment=1000.0)
    t_load = time.perf_counter() - t0
    t0 = time.perf_counter()
    result = cyberstride.run(HahnelSlides2020(), economy, seed=0)
    t_run = time.perf_counter() - t0
    return t_load, t_run, result.summary.rounds, rss_mb()


def main(files):
    print(f"{'file':<10} {'path':<12} {'load s':>8} {'solve s':>8} {'total s':>8} {'rounds':>6} {'rss MB':>7}")
    print("-" * 66)
    for name in files:
        path = DATA / name
        rows = []
        for label, fn in (("numpy", bench_numpy), ("cyberstride", bench_cyberstride)):
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
